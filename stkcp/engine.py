"""Deterministic local reference implementation; this does not execute COBOL."""

from dataclasses import dataclass
from datetime import datetime

from .contracts import (
    AUDIT_LENGTH, MAX_AGE_SECONDS, MAX_HOLDINGS, MAX_HOLDING_QUANTITY,
    MAX_ORDERS, MAX_PRICES, ORDER_LENGTH, digits, identifier,
    read_records, timestamp,
)
from .errors import InfrastructureError


@dataclass
class Holding:
    client: str
    symbol: str
    final: int
    available: int


@dataclass
class Order:
    raw: str
    order_id: str = ""
    client: str = ""
    symbol: str = ""
    side: str = ""
    quantity: int = 0
    limit: int = 0
    time: datetime | None = None
    reason: str = "DATA001"
    reference: int = 0
    execution: int = 0

    def audit(self):
        status = "SETTLED" if self.reason == "OK000" else "PENDING" if self.reason == "PEND01" else "REJECTED"
        notional = self.quantity * self.reference
        record = f"{self.raw[:59]:<59}{status:<8}{self.reason:<7}{self.reference:010d}{self.execution:010d}{notional:016d}"
        if len(record) != AUDIT_LENGTH:
            raise InfrastructureError("audit field overflow")
        return record


def load_holdings(path):
    holdings = {}
    for number, raw in enumerate(read_records(path), 1):
        if len(raw) != 26 or not identifier(raw[:8]) or not identifier(raw[8:16]) or not digits(raw[16:26]):
            raise InfrastructureError(f"holdings record {number}: invalid layout")
        key = (raw[:8].rstrip(), raw[8:16].rstrip())
        if key in holdings:
            raise InfrastructureError(f"holdings record {number}: duplicate client/stock")
        if len(holdings) >= MAX_HOLDINGS:
            raise InfrastructureError("holdings table capacity exceeded")
        quantity = int(raw[16:26])
        holdings[key] = Holding(*key, quantity, quantity)
    return holdings


def load_prices(path):
    prices = {}
    previous = None
    for number, raw in enumerate(read_records(path), 1):
        if number > MAX_PRICES:
            raise InfrastructureError("price table capacity exceeded")
        if len(raw) != 32 or not identifier(raw[:8]) or not digits(raw[22:32]) or int(raw[22:32]) == 0:
            raise InfrastructureError(f"price record {number}: invalid layout")
        try:
            time = timestamp(raw[8:22])
        except ValueError as error:
            raise InfrastructureError(f"price record {number}: {error}") from error
        symbol = raw[:8].rstrip()
        key = (symbol, time)
        if previous is not None and key <= previous:
            raise InfrastructureError(f"price record {number}: records must be unique and sorted by stock/time")
        previous = key
        prices.setdefault(symbol, []).append((time, int(raw[22:32])))
    return prices


def reference_price(prices, symbol, time):
    if time is None:
        return 0
    for quoted_at, price in reversed(prices.get(symbol, [])):
        if quoted_at <= time:
            return price if (time - quoted_at).total_seconds() <= MAX_AGE_SECONDS else 0
    return 0


def process(orders_path, holdings_path, prices_path, *, event_callback=None):
    """Return actual audit and holdings records, or fail without publishing.

    An optional callback receives detached snapshots from the actual engine:
    initial state, each order validation, each atomic matched pair, and completion.
    Validation still precedes batch matching; callbacks do not alter that model.
    """
    try:
        holdings = load_holdings(holdings_path)
        prices = load_prices(prices_path)
        orders = []
        seen = set()
        as_of = None

        def emit(phase, *, active=(), current_time=None):
            if event_callback is None:
                return
            event_callback({
                "phase": phase,
                "active_rows": tuple(active),
                "as_of": current_time.isoformat() if current_time else None,
                "orders": tuple({**vars(order), "time": order.time.isoformat() if order.time else None}
                                for order in orders),
                "holdings": tuple(vars(holding).copy() for holding in holdings.values()),
            })

        emit("initial")
        for number, raw in enumerate(read_records(orders_path), 1):
            if number > MAX_ORDERS:
                raise InfrastructureError("order table capacity exceeded")
            order = Order(raw=raw)
            orders.append(order)
            try:
                if len(raw) != ORDER_LENGTH or not all(identifier(raw[a:b]) for a, b in ((0, 12), (12, 20), (20, 28))):
                    continue
                if not digits(raw[29:35]) or not digits(raw[35:45]):
                    continue
                quantity, limit = int(raw[29:35]), int(raw[35:45])
                if quantity == 0 or limit == 0:
                    continue
                try:
                    time = timestamp(raw[45:59])
                except ValueError:
                    continue
                order.order_id, order.client, order.symbol = (raw[:12].rstrip(), raw[12:20].rstrip(), raw[20:28].rstrip())
                order.side, order.quantity, order.limit, order.time = raw[28], quantity, limit, time
                as_of = max(as_of, time) if as_of else time
                if order.order_id in seen:
                    order.reason = "DUP001"
                    continue
                seen.add(order.order_id)
                if order.side not in ("B", "S"):
                    order.reason = "SIDE001"
                    continue
                order.reference = reference_price(prices, order.symbol, time)
                if not order.reference or not 90 * order.reference <= 100 * order.limit <= 110 * order.reference:
                    order.reason = "PRICE01"
                    continue
                key = (order.client, order.symbol)
                holding = holdings.get(key)
                if order.side == "S":
                    if holding is None or order.quantity > holding.available:
                        order.reason = "HOLD01"
                        continue
                    holding.available -= order.quantity
                elif holding is None:
                    if len(holdings) >= MAX_HOLDINGS:
                        raise InfrastructureError("holdings table capacity exceeded for buyer")
                    holdings[key] = Holding(*key, 0, 0)
                order.reason = "PEND01"
            finally:
                emit("validation", active=(number,), current_time=order.time)

        for index, order in enumerate(orders):
            if order.reason != "PEND01":
                continue
            for other_index, other in enumerate(orders[index + 1:], index + 1):
                if other.reason != "PEND01" or order.symbol != other.symbol or order.side == other.side or order.client == other.client or order.quantity != other.quantity:
                    continue
                buy, sell = (order, other) if order.side == "B" else (other, order)
                if buy.limit < sell.limit:
                    continue
                buyer = holdings[(buy.client, buy.symbol)]
                seller = holdings[(sell.client, sell.symbol)]
                if buyer.final + buy.quantity > MAX_HOLDING_QUANTITY or seller.final < sell.quantity:
                    raise InfrastructureError("settlement holdings arithmetic overflow or underflow")
                buyer.final += buy.quantity
                seller.final -= sell.quantity
                for matched in (buy, sell):
                    matched.reason = "OK000"
                    matched.execution = sell.limit
                emit("settlement", active=(index + 1, other_index + 1), current_time=as_of)
                break
        audit = [order.audit() for order in orders]
        holdout = []
        for holding in holdings.values():
            price = reference_price(prices, holding.symbol, as_of)
            holdout.append(f"{holding.client:<8}{holding.symbol:<8}{holding.final:010d}{price:010d}{holding.final * price:020d}")
        emit("complete", current_time=as_of)
        return audit, holdout
    except (OSError, UnicodeError) as error:
        raise InfrastructureError(str(error)) from error
