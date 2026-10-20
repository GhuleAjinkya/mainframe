"""Offline dashboard snapshots captured from the actual reference engine.

The replay animates batch processing, not a live exchange. All money remains
integer paise. Quotes are evaluated at the current order's UTC timestamp; batch
settlement and final valuation use the latest valid order timestamp, just as the
engine does. Missing or stale prices remain missing rather than being invented.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from tempfile import TemporaryDirectory
from typing import Mapping

from .contracts import EXPLANATIONS, MAX_ORDERS, digits, identifier, read_records, timestamp
from .engine import load_holdings, load_prices, process, reference_price
from .errors import InfrastructureError


def _freeze(value):
    """Freeze nested snapshots and reuse already frozen rows and chart points."""
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Replay:
    """An immutable completed batch trace; state(0) is the untouched seed state."""

    events: tuple
    symbols: tuple[str, ...]
    audit: tuple[str, ...]
    holdout: tuple[str, ...]
    orders_path: Path
    holdings_path: Path
    prices_path: Path
    input_snapshots: Mapping[str, bytes] | None = None

    def state(self, index: int) -> Mapping:
        if not 0 <= index < len(self.events):
            raise IndexError("replay step is outside the available events")
        return self.events[index]

    def __len__(self):
        return len(self.events)


def _input_row(raw, number):
    """Display original fields even when a record cannot pass engine validation."""
    try:
        time = timestamp(raw[45:59]).isoformat()
    except ValueError:
        time = None
    return {
        "row": number,
        "order_id": raw[:12].rstrip(),
        "client_id": raw[12:20].rstrip(),
        "stock_code": raw[20:28].rstrip(),
        "side": raw[28:29].strip(),
        "quantity": int(raw[29:35]) if digits(raw[29:35]) else None,
        "requested_price_paise": int(raw[35:45]) if digits(raw[35:45]) else None,
        "order_timestamp": time,
        "reference_price_paise": None,
        "execution_price_paise": None,
        "status": "QUEUED",
        "reason_code": "",
        "explanation": "Waiting for batch validation.",
        "raw_order": raw,
    }


def load_replay(orders_path, holdings_path, prices_path):
    """Capture input bytes once so replay and dashboard reports share one batch."""
    sources = tuple(Path(path) for path in (orders_path, holdings_path, prices_path))
    try:
        snapshots = {}
        for name, source in zip(("orders", "holdings", "prices"), sources):
            with source.open("rb") as stream:
                data = stream.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise InfrastructureError(f"{name} input exceeds the 64 MiB local snapshot limit")
            snapshots[name] = data
        with TemporaryDirectory(prefix="stkcp-replay-") as temporary:
            paths = []
            for name, data in snapshots.items():
                copied = Path(temporary) / f"{name}.txt"
                copied.write_bytes(data)
                paths.append(copied)
            replay = _load_replay(*paths)
        return replace(replay, orders_path=sources[0], holdings_path=sources[1],
                       prices_path=sources[2], input_snapshots=MappingProxyType(snapshots))
    except (OSError, UnicodeError) as error:
        raise InfrastructureError(str(error)) from error


def _load_replay(orders_path, holdings_path, prices_path):
    """Read local inputs and return a deterministic immutable processing replay.

    No output files are written and no network access takes place. Infrastructure
    errors propagate, so an incomplete failed batch cannot appear successful.
    """
    paths = tuple(Path(path) for path in (orders_path, holdings_path, prices_path))
    try:
        from itertools import islice
        raw_orders = tuple(islice(read_records(paths[0]), MAX_ORDERS + 1))
        if len(raw_orders) > MAX_ORDERS:
            raise InfrastructureError("order table capacity exceeded")
        seed_holdings = load_holdings(paths[1])
        prices = load_prices(paths[2])
    except (OSError, UnicodeError) as error:
        raise InfrastructureError(str(error)) from error
    rows = [_freeze(_input_row(raw, number)) for number, raw in enumerate(raw_orders, 1)]
    symbols = tuple(sorted(set(prices) | {symbol for _, symbol in seed_holdings} | {
        row["stock_code"] for row in rows
        if row["stock_code"] and identifier(row["stock_code"])
    }))
    series = {symbol: {"reference": [], "orders": [], "executions": []} for symbol in symbols}
    events = []
    valuation_series = []
    visible_time = None
    pair_count = 0
    execution_notional = 0
    holding_cache = {}

    def capture(event):
        nonlocal visible_time, pair_count, execution_notional
        step = len(events)
        phase = event["phase"]
        active = event["active_rows"]
        if event["as_of"] is not None or phase == "complete":
            visible_time = datetime.fromisoformat(event["as_of"]) if event["as_of"] else None
        for number, order in enumerate(event["orders"], 1):
            status = (
                "SETTLED" if order["reason"] == "OK000" else
                ("PENDING" if phase == "complete" else "AWAITING")
                if order["reason"] == "PEND01" else "REJECTED"
            )
            previous = rows[number - 1]
            reference = order["reference"] or None
            execution = order["execution"] or None
            if (previous["status"], previous["reason_code"],
                previous["reference_price_paise"], previous["execution_price_paise"]) == (
                    status, order["reason"], reference, execution):
                continue
            row = dict(previous)
            row.update(
                status=status,
                reason_code=order["reason"],
                reference_price_paise=reference,
                execution_price_paise=execution,
                explanation=("Validation passed; waiting for the batch matching phase."
                             if status == "AWAITING" else EXPLANATIONS[order["reason"]]),
            )
            rows[number - 1] = _freeze(row)

        quotes = {
            symbol: reference_price(prices, symbol, visible_time) or None
            for symbol in symbols
        }
        if phase == "validation":
            row = rows[active[0] - 1]
            symbol = row["stock_code"]
            if symbol in series:
                point = {"step": step, "time": row["order_timestamp"], "row": row["row"]}
                validated_time = event["orders"][active[0] - 1]["time"]
                if validated_time and quotes[symbol] is not None:
                    series[symbol]["reference"].append(_freeze({**point, "price_paise": quotes[symbol]}))
                requested = row["requested_price_paise"]
                if requested:
                    series[symbol]["orders"].append(_freeze({**point, "price_paise": requested}))
        elif phase == "settlement":
            buy, sell = (rows[number - 1] for number in active)
            pair_count += 1
            execution_notional += buy["quantity"] * buy["execution_price_paise"]
            series[buy["stock_code"]]["executions"].append(_freeze({
                "step": step,
                "time": visible_time.isoformat() if visible_time else None,
                "row": buy["row"],
                "rows": active,
                "price_paise": buy["execution_price_paise"],
            }))

        reservations = {}
        for row in rows:
            if phase != "complete" and row["status"] in ("AWAITING", "PENDING") and row["side"] == "S":
                key = (row["client_id"], row["stock_code"])
                reservations[key] = reservations.get(key, 0) + row["quantity"]
        holdings = []
        known_value = 0
        unpriced = 0
        for holding in event["holdings"]:
            key = (holding["client"], holding["symbol"])
            quote = reference_price(prices, holding["symbol"], visible_time) or None
            quantity = holding["final"]
            value = quantity * quote if quote is not None else (0 if quantity == 0 else None)
            if value is None:
                unpriced += 1
            else:
                known_value += value
            reserved = reservations.get(key, 0)
            holding_view = {
                "client_id": holding["client"], "stock_code": holding["symbol"],
                "quantity": quantity, "reserved": reserved,
                "available": quantity - reserved,
                "validation_available": holding["available"],
                "reference_price_paise": quote, "valuation_paise": value,
            }
            if holding_cache.get(key) != holding_view:
                holding_cache[key] = _freeze(holding_view)
            holdings.append(holding_cache[key])
        complete = unpriced == 0
        valuation_series.append(_freeze({"step": step, "value_paise": known_value, "complete": complete}))
        counts = {"total": len(rows), "queued": 0, "awaiting": 0, "settled": 0, "pending": 0, "rejected": 0}
        for row in rows:
            counts[row["status"].lower()] += 1
        counts["processed"] = counts["total"] - counts["queued"]

        if phase == "initial":
            title = "Ready to replay"
            message = "Local inputs loaded. Validation will run in file order before batch matching."
        elif phase == "validation":
            row = rows[active[0] - 1]
            title = f"Validate row {row['row']}: {row['order_id'] or '(blank ID)'}"
            message = row["explanation"]
            if row["status"] == "AWAITING" and row["side"] == "S":
                message += f" Reserved {row['quantity']} seeded shares for this SELL."
        elif phase == "settlement":
            first, second = (rows[number - 1] for number in active)
            title = f"Settle pair {pair_count}: {first['order_id']} + {second['order_id']}"
            price = first["execution_price_paise"]
            message = (f"Both legs settled atomically: {first['quantity']} {first['stock_code']} shares "
                       f"at INR {price // 100}.{price % 100:02d} per share (SELL limit).")
        else:
            title = "Batch complete"
            message = (f"{counts['settled']} settled orders in {pair_count} pairs; "
                       f"{counts['pending']} pending; {counts['rejected']} rejected. "
                       "Final classifications and holdings match the engine audit. "
                       "Batch SELL reservations have expired.")
        events.append(_freeze({
            "step": step, "phase": phase, "title": title, "message": message,
            "as_of": visible_time.isoformat() if visible_time else None,
            "active_rows": active, "orders": tuple(rows), "holdings": holdings,
            "counts": counts, "executed_pairs": pair_count,
            "executed_notional_paise": execution_notional, "quotes": quotes,
            "price_series": {symbol: {name: tuple(points) for name, points in lines.items()}
                             for symbol, lines in series.items()},
            "valuation_paise": known_value if complete else None,
            "known_valuation_paise": known_value, "valuation_complete": complete,
            "unpriced_holdings": unpriced, "valuation_series": tuple(valuation_series),
        }))

    audit, holdout = process(*paths, event_callback=capture)
    return Replay(tuple(events), symbols, tuple(audit), tuple(holdout), *paths)
