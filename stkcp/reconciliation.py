"""Independent inventory/trade-notional checks over actual output candidates."""

from collections import defaultdict

from .audit_to_json import parse_audit
from .contracts import MAX_HOLDINGS, digits, identifier, read_records
from .engine import load_holdings
from .errors import InfrastructureError


def reconcile_holdings(seed_path, audit_path, holdout_path):
    expected = {key: holding.final for key, holding in load_holdings(seed_path).items()}
    stock_quantity = defaultdict(int)
    execution_notional = defaultdict(int)
    for number, raw in enumerate(read_records(audit_path), 1):
        record = parse_audit(raw, number)
        key = (record["client_id"], record["stock_code"])
        if record["status"] in ("SETTLED", "PENDING") and record["side"] == "B":
            expected.setdefault(key, 0)
        if record["status"] != "SETTLED":
            continue
        change = record["quantity"] * (1 if record["side"] == "B" else -1)
        expected[key] = expected.get(key, 0) + change
        stock_quantity[record["stock_code"]] += change
        execution_notional[record["stock_code"]] += change * record["execution_price_paise"]
    if any(stock_quantity.values()) or any(execution_notional.values()):
        raise InfrastructureError("settled BUY/SELL quantities or execution notionals do not balance by stock")
    portfolio = []
    found = set()
    for number, raw in enumerate(read_records(holdout_path), 1):
        if number > MAX_HOLDINGS or len(raw) != 56 or not identifier(raw[:8]) or not identifier(raw[8:16]) or not digits(raw[16:]):
            raise InfrastructureError(f"final holdings record {number}: invalid layout or capacity")
        key = (raw[:8].rstrip(), raw[8:16].rstrip())
        if key in found:
            raise InfrastructureError(f"final holdings record {number}: duplicate client/stock")
        found.add(key)
        quantity, price, valuation = int(raw[16:26]), int(raw[26:36]), int(raw[36:56])
        if key not in expected or quantity != expected[key]:
            raise InfrastructureError(f"final holdings record {number}: quantity does not reconcile with settled orders")
        if quantity * price != valuation:
            raise InfrastructureError(f"final holdings record {number}: invalid valuation")
        portfolio.append({"client_id": key[0], "stock_code": key[1], "quantity": quantity, "reference_price_paise": price or None, "valuation_paise": valuation if price else None})
    if found != set(expected):
        raise InfrastructureError("final holdings omit an expected client/stock entry")
    return portfolio
