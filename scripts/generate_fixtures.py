"""Regenerate explicitly synthetic inputs; expected results are hand reasoned.

Run from any directory: python scripts/generate_fixtures.py. This script never
reads settlement implementation output and never downloads market data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def order(order_id, client, stock, side, quantity, limit, stamp="20260102100000"):
    assert 1 <= len(order_id) <= 12 and 1 <= len(client) <= 8 and 1 <= len(stock) <= 8
    return f"{order_id:<12}{client:<8}{stock:<8}{side}{quantity:06d}{limit:010d}{stamp}"


def generate() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    orders = [
        order("A-BUY1", "BUYER1", "ALPHA", "B", 10, 10400),
        order("A-SELL1", "SELLER1", "ALPHA", "S", 10, 10100),
        order("B-SELL1", "SELLER2", "BETA", "S", 5, 20300),
        order("B-BUY1", "BUYER2", "BETA", "B", 5, 20600),
        order("PENDING1", "BUYER3", "ALPHA", "B", 7, 10300),
        order("HOLDFAIL", "SELLER1", "ALPHA", "S", 999, 10200),
        order("A-BUY1", "BUYER1", "ALPHA", "B", 1, 10200),
        order("BADSIDE", "BUYER1", "ALPHA", "X", 1, 10200),
        order("BADPRICE", "BUYER1", "ALPHA", "B", 1, 20000),
        order("BADQTY", "BUYER1", "ALPHA", "B", 1, 10200),
        "SHORT",
        order("FUTURE1", "BUYER4", "FUTURE", "B", 1, 30000, "20260102080000"),
        order("BADDATE", "BUYER1", "ALPHA", "B", 1, 10200, "20260230090000"),
        order("PENDING2", "SELLER2", "BETA", "S", 6, 20400),
    ]
    orders[9] = orders[9][:29] + "00X001" + orders[9][35:]
    assert all(len(row) == 59 for index, row in enumerate(orders) if index != 10)
    holdings = [
        ("SELLER1", "ALPHA", 100), ("SELLER2", "BETA", 20),
        ("BUYER1", "ALPHA", 5), ("FUTCLNT", "FUTURE", 2),
    ]
    prices = [
        ("ALPHA", "20260101090000", 10000),
        ("ALPHA", "20260102090000", 10200),
        ("BETA", "20260101090000", 20000),
        ("BETA", "20260102090000", 20500),
        ("FUTURE", "20260103090000", 30000),
    ]
    files = {
        "orders.txt": "\n".join(orders) + "\n",
        "holdings.txt": "".join(f"{client:<8}{stock:<8}{quantity:010d}\n"
                                  for client, stock, quantity in holdings),
        "prices.txt": "".join(f"{stock:<8}{stamp}{paise:010d}\n" for stock, stamp, paise in prices),
        "synthetic-history.csv": ("Date,Open,High,Low,Close,Adj Close,Volume,Symbol,Currency\n"
                                  "2026-01-01,99.00,101.00,98.00,100.00,100.00,1000,ALPHA,INR\n"
                                  "2026-01-02,100.00,103.00,99.00,102.00,102.00,1200,ALPHA,INR\n"),
    }
    for name, content in files.items():
        (DATA / name).write_bytes(content.encode("ascii"))
    metadata = {
        "schema_version": 1,
        "dataset_kind": "synthetic_fixture",
        "contains_real_market_data": False,
        "source_provider": None,
        "retrieved_at_utc": None,
        "prepared_date": "2026-10-19",
        "provenance": "Hand-designed coursework fixtures; all symbols, clients, quantities and prices are synthetic.",
        "currency": "INR",
        "money_unit": "paise",
        "timestamps_timezone": "UTC",
        "market_session": "Synthetic 09:00 UTC observations; no real exchange calendar is asserted.",
        "adjustment_policy": "Not applicable to fictional instruments; no corporate actions or adjusted prices.",
        "record_count": len(prices),
        "prices_sha256": hashlib.sha256(files["prices.txt"].encode("ascii")).hexdigest(),
        "future_reference_case": "FUTURE has only 2026-01-03 data; FUTURE1 at 2026-01-02 08:00 UTC must reject with PRICE01.",
        "historical_import_status": "No real historical export was supplied or retrieved; local-only instructions prohibit network retrieval.",
        "fallback_policy": "Explicitly selected by local demo defaults; never substituted by the CSV importer.",
    }
    (DATA / "market-data-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    # Manually derived from the published matching/reservation rules. This list
    # is deliberately independent of the executable settlement implementation.
    outcomes = [
        ("A-BUY1", "SETTLED", "OK000", 10200, 10100, 102000),
        ("A-SELL1", "SETTLED", "OK000", 10200, 10100, 102000),
        ("B-SELL1", "SETTLED", "OK000", 20500, 20300, 102500),
        ("B-BUY1", "SETTLED", "OK000", 20500, 20300, 102500),
        ("PENDING1", "PENDING", "PEND01", 10200, 0, 71400),
        ("HOLDFAIL", "REJECTED", "HOLD01", 10200, 0, 10189800),
        ("A-BUY1", "REJECTED", "DUP001", 0, 0, 0),
        ("BADSIDE", "REJECTED", "SIDE001", 0, 0, 0),
        ("BADPRICE", "REJECTED", "PRICE01", 10200, 0, 10200),
        ("BADQTY", "REJECTED", "DATA001", 0, 0, 0),
        ("SHORT", "REJECTED", "DATA001", 0, 0, 0),
        ("FUTURE1", "REJECTED", "PRICE01", 0, 0, 0),
        ("BADDATE", "REJECTED", "DATA001", 0, 0, 0),
        ("PENDING2", "PENDING", "PEND01", 20500, 0, 123000),
    ]
    expected = {
        "schema_version": 1,
        "derivation": "Manually reasoned, independently of settlement program output; amounts are integer paise.",
        "input_count": 14,
        "return_code": 0,
        "counts": {"SETTLED": 4, "PENDING": 2, "REJECTED": 8},
        "orders": [dict(line=index, order_id=oid, status=status, reason_code=reason,
                        reference_price=reference or None, execution_price=execution or None,
                        reference_notional=notional if reference else None)
                   for index, (oid, status, reason, reference, execution, notional) in enumerate(outcomes, 1)],
        "settled_pairs": [
            {"buy_line": 1, "sell_line": 2, "stock_code": "ALPHA", "quantity": 10, "execution_price": 10100},
            {"buy_line": 4, "sell_line": 3, "stock_code": "BETA", "quantity": 5, "execution_price": 20300},
        ],
        "final_holdings": [
            {"client_id": "SELLER1", "stock_code": "ALPHA", "quantity": 90, "reference_price": 10200, "valuation": 918000},
            {"client_id": "SELLER2", "stock_code": "BETA", "quantity": 15, "reference_price": 20500, "valuation": 307500},
            {"client_id": "BUYER1", "stock_code": "ALPHA", "quantity": 15, "reference_price": 10200, "valuation": 153000},
            {"client_id": "FUTCLNT", "stock_code": "FUTURE", "quantity": 2, "reference_price": None, "valuation": None},
            {"client_id": "BUYER2", "stock_code": "BETA", "quantity": 5, "reference_price": 20500, "valuation": 102500},
            {"client_id": "BUYER3", "stock_code": "ALPHA", "quantity": 0, "reference_price": 10200, "valuation": 0},
        ],
        "valuation_timestamp": "20260102100000",
        "notes": [
            "Line 6 rejects before matching and reserves nothing; line 14 pending SELL does not reduce final holdings.",
            "Line 11 is deliberately short; upload into FB59 pads it, but its missing basic fields still yield DATA001.",
            "FUTURE prices cannot value FUTCLNT or evaluate FUTURE1 before their observation timestamp.",
            "Reference notional values the order quantity; settled execution notional differs when seller limit differs from reference.",
        ],
    }
    (DATA / "expected-results.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generate()
    print(f"Wrote explicitly synthetic fixtures to {DATA}")
