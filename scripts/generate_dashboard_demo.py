"""Build the reproducible 550-order, fully offline dashboard demonstration.

This generator uses only the standard library and never invokes the settlement
engine or reads its output. Expected results follow directly from 250 disjoint
BUY/SELL pairs and 50 deliberately invalid rows. The original 14-row acceptance
fixture in ``data/`` is preserved.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dashboard-demo"
SYMBOLS = ("ALPHA", "BETA", "GAMMA", "DELTA", "OMEGA")
BASE_PRICES = (10000, 20500, 12075, 33200, 8050)
PRICE_STEPS = (7, 11, 5, 13, 3)
WAVE = (0, 13, -7, 19, 5, -10, 9)
START = datetime(2026, 1, 2, 9)
SELL_SEED = 2000
REJECTIONS = ("DUP001", "HOLD01", "PRICE01", "SIDE001", "DATA001")


def synthetic_price(symbol_index: int, minute: int) -> int:
    """A fictional moving price in integer paise, never an exchange quote."""
    return BASE_PRICES[symbol_index] + minute * PRICE_STEPS[symbol_index] + 2 * WAVE[minute % len(WAVE)]


def _order(order_id, client, symbol, side, quantity, limit, stamp):
    return f"{order_id:<12}{client:<8}{symbol:<8}{side}{quantity:06d}{limit:010d}{stamp:%Y%m%d%H%M%S}"


def _json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def generate(destination: Path = DATA) -> Path:
    """Write deterministic inputs and independently derived expectations."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    orders, outcomes, pairs = [], [], []
    changes = defaultdict(int)
    # Every buyer and seller has one holding per instrument: only 50 keys.
    seeds = {(f"{role}{client:02d}", symbol): SELL_SEED if role == "SELLER" else 0
             for role in ("BUYER", "SELLER") for client in range(1, 6) for symbol in SYMBOLS}

    def append(raw, reason, reference=None, execution=None):
        orders.append(raw)
        quantity = int(raw[29:35]) if raw[29:35].isascii() and raw[29:35].isdigit() else None
        outcomes.append({
            "line": len(orders), "order_id": raw[:12].rstrip(),
            "status": "SETTLED" if reason == "OK000" else "REJECTED",
            "reason_code": reason, "reference_price_paise": reference,
            "execution_price_paise": execution,
            "reference_notional_paise": quantity * reference if reference is not None else None,
        })

    for minute in range(50):
        for symbol_index, symbol in enumerate(SYMBOLS):
            # Each quantity occurs in exactly one pair; accidental cross-pair
            # matching is impossible even when an instrument/client is reused.
            quantity = minute * 5 + symbol_index + 1
            client = minute % 5 + 1
            buyer, seller = f"BUYER{client:02d}", f"SELLER{client:02d}"
            reference = synthetic_price(symbol_index, minute)
            sell_limit = reference - 20 - quantity % 7
            buy_limit = reference + 40 + quantity % 11
            at = START + timedelta(minutes=minute, seconds=3 + symbol_index * 8)
            buy_id, sell_id = f"BUY{quantity:06d}", f"SELL{quantity:06d}"
            buy_line = len(orders) + 1
            append(_order(buy_id, buyer, symbol, "B", quantity, buy_limit, at), "OK000", reference, sell_limit)
            sell_line = len(orders) + 1
            append(_order(sell_id, seller, symbol, "S", quantity, sell_limit, at + timedelta(seconds=2)),
                   "OK000", reference, sell_limit)
            pairs.append({"buy_line": buy_line, "sell_line": sell_line, "stock_code": symbol,
                          "quantity": quantity, "execution_price_paise": sell_limit,
                          "execution_notional_paise": quantity * sell_limit})
            changes[(buyer, symbol)] += quantity
            changes[(seller, symbol)] -= quantity

        # One rejection after each ten valid rows. Each of the five reasons
        # appears ten times. None can create a reservation or a settlement.
        reason = REJECTIONS[minute % len(REJECTIONS)]
        symbol_index = minute % len(SYMBOLS)
        symbol = SYMBOLS[symbol_index]
        reference = synthetic_price(symbol_index, minute)
        at = START + timedelta(minutes=minute, seconds=58)
        rejection_id = f"REJ{minute + 1:06d}"
        if reason == "DUP001":
            raw = _order(buy_id, buyer, symbol, "B", 1, reference, at)
            append(raw, reason)
        elif reason == "HOLD01":
            raw = _order(rejection_id, f"SELLER{minute % 5 + 1:02d}", symbol, "S", 999999, reference, at)
            append(raw, reason, reference)
        elif reason == "PRICE01":
            append(_order(rejection_id, "BUYER01", symbol, "B", 1, reference * 2, at), reason, reference)
        elif reason == "SIDE001":
            append(_order(rejection_id, "BUYER01", symbol, "X", 1, reference, at), reason)
        else:
            raw = _order(rejection_id, "BUYER01", symbol, "B", 1, reference, at)
            append(raw[:29] + "00X001" + raw[35:], reason)

    final_holdings = []
    for (client, symbol), seed in sorted(seeds.items()):
        final_quantity = seed + changes[(client, symbol)]
        price = synthetic_price(SYMBOLS.index(symbol), 49)
        final_holdings.append({"client_id": client, "stock_code": symbol, "quantity": final_quantity,
                               "reference_price_paise": price, "valuation_paise": final_quantity * price})
    final_as_of = max(raw[45:59] for raw in orders if "X" not in raw[29:35])
    expected = {
        "schema_version": 1,
        "derivation": ("Derived from constructed disjoint pairs, without invoking the engine: quantities 1..250 "
                       "each have one BUY and one SELL at the same minute/stock reference; BUY limits exceed "
                       "SELL limits and both are inside the 10% band. Each seller starts with 2000 shares per "
                       "stock and sells at most 1375. Each rejected row is invalid before reservation. "
                       "Each pair executes at its SELL limit, transfers its quantity once, and contributes "
                       "quantity times SELL limit to trade value. Final valuation uses minute-49 quotes."),
        "input_count": 550, "return_code": 0,
        "counts": {"SETTLED": 500, "PENDING": 0, "REJECTED": 50},
        "accepted_orders": 500, "matched_pairs": 250,
        "reason_counts": {"OK000": 500, **{reason: 10 for reason in REJECTIONS}},
        "executed_quantity": 31375,
        "executed_notional_paise": sum(pair["execution_notional_paise"] for pair in pairs),
        "final_valuation_paise": sum(row["valuation_paise"] for row in final_holdings),
        "initial_stock_quantities": {symbol: 10000 for symbol in SYMBOLS},
        "valuation_timestamp": final_as_of,
        "orders": outcomes, "settled_pairs": pairs, "final_holdings": final_holdings,
    }
    files = {
        "orders.txt": ("\n".join(orders) + "\n").encode("ascii"),
        "holdings.txt": "".join(f"{client:<8}{symbol:<8}{seed:010d}\n"
                                  for (client, symbol), seed in sorted(seeds.items())).encode("ascii"),
        "prices.txt": "".join(f"{symbol:<8}{START + timedelta(minutes=minute):%Y%m%d%H%M%S}{synthetic_price(index, minute):010d}\n"
                                for index, symbol in sorted(enumerate(SYMBOLS), key=lambda item: item[1])
                                for minute in range(50)).encode("ascii"),
        "expected-results.json": _json_bytes(expected),
    }
    metadata = {
        "schema_version": 1, "dataset_kind": "synthetic_fixture",
        "contains_real_market_data": False, "source_provider": None, "retrieved_at_utc": None,
        "prepared_date": "2026-10-19", "currency": "INR", "money_unit": "paise",
        "timestamps_timezone": "UTC", "symbols": list(SYMBOLS),
        "provenance": ("Deterministic fictional coursework data generated locally by "
                       "scripts/generate_dashboard_demo.py; no exchange, account, IBM Cloud, "
                       "API, random source, or network data is used."),
        "market_session": "Fictional 2026-01-02 09:00..09:49 UTC, one synthetic quote per minute per stock.",
        "adjustment_policy": "Not applicable to fictional instruments; no corporate actions.",
        "fallback_policy": "Explicit dashboard demo fixture; never a fallback for supplied inputs.",
        "record_count": 250, "order_count": 550, "holding_count": 50,
        "expected_counts": expected["counts"], "expected_matched_pairs": 250,
        "prices_sha256": hashlib.sha256(files["prices.txt"]).hexdigest(),
        "source_files": {name: {"sha256": hashlib.sha256(content).hexdigest()}
                         for name, content in files.items()},
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "expected_results_policy": "Algebraic construction independent of engine output; tests compare actual output to this contract.",
    }
    files["market-data-metadata.json"] = _json_bytes(metadata)
    for name, content in files.items():
        (destination / name).write_bytes(content)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()
    print(f"Wrote 550 synthetic orders (500 accepted, 50 rejected) to {generate(args.output)}")
