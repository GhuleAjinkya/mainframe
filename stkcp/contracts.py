"""Fixed-width contracts shared by the reference engine and audit tools."""

from datetime import datetime
from pathlib import Path
import re

ORDER_LENGTH = 59
AUDIT_LENGTH = 110
HOLDING_LENGTH = 26
PRICE_LENGTH = 32
HOLDOUT_LENGTH = 56
MAX_ORDERS = 1000
MAX_HOLDINGS = 1000
MAX_PRICES = 5000
MAX_AGE_SECONDS = 604800
MAX_HOLDING_QUANTITY = 9999999999
EXPLANATIONS = {
    "OK000": "Order settled under the deterministic batch matching rules.",
    "PEND01": "No compatible counter-order was available in this batch.",
    "DUP001": "Order ID duplicates an earlier structurally valid order.",
    "HOLD01": "SELL quantity exceeds available seeded holdings after reservations.",
    "PRICE01": "Historical reference is missing, stale, or outside the allowed price band.",
    "DATA001": "Order record has invalid length, identifiers, numeric fields, or timestamp.",
    "SIDE001": "Side must be B (BUY) or S (SELL).",
}
REASON_STATUS = {code: ("SETTLED" if code == "OK000" else "PENDING" if code == "PEND01" else "REJECTED") for code in EXPLANATIONS}
UNKNOWN_EXPLANATION = "Unrecognized reason code; inspect the audit record."


def identifier(field):
    return bool(re.fullmatch(r"[A-Z0-9_-]+ *", field))


def digits(field):
    return bool(field) and all("0" <= char <= "9" for char in field)


def timestamp(field):
    if len(field) != 14 or not digits(field) or not 1601 <= int(field[:4]) <= 9999:
        raise ValueError("timestamp must be UTC YYYYMMDDhhmmss, years 1601–9999")
    return datetime(int(field[:4]), int(field[4:6]), int(field[6:8]), int(field[8:10]), int(field[10:12]), int(field[12:14]))


def read_records(path, encoding="ascii"):
    """Preserve spaces and empty records; remove only the line terminator."""
    with Path(path).open("r", encoding=encoding, newline="") as stream:
        for line in stream:
            if line.endswith("\n"):
                line = line[:-1]
                if line.endswith("\r"):
                    line = line[:-1]
            yield line


def write_records(path, records):
    with Path(path).open("w", encoding="ascii", newline="\n") as stream:
        for record in records:
            stream.write(record + "\n")


def order_record(order_id, client_id, stock_code, side, quantity, limit_price, order_timestamp):
    fields = (order_id, client_id, stock_code)
    if any(not identifier(value) or value != value.rstrip() for value in fields):
        raise ValueError("identifiers must contain uppercase ASCII letters, digits, _ or -")
    if len(order_id) > 12 or len(client_id) > 8 or len(stock_code) > 8 or side not in ("B", "S"):
        raise ValueError("invalid identifier width or side")
    if not 1 <= quantity <= 999999 or not 1 <= limit_price <= 9999999999:
        raise ValueError("quantity or price out of range")
    timestamp(order_timestamp)
    return f"{order_id:<12}{client_id:<8}{stock_code:<8}{side}{quantity:06d}{limit_price:010d}{order_timestamp}"
