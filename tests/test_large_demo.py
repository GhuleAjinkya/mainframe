"""Exercise actual processing of the reproducible large offline demonstration."""

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.generate_dashboard_demo import generate
from stkcp.contracts import read_records
from stkcp.pipeline import run
from stkcp.replay import load_replay


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dashboard-demo"


class LargeDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((DATA / "expected-results.json").read_text(encoding="utf-8"))
        cls.metadata = json.loads((DATA / "market-data-metadata.json").read_text(encoding="utf-8"))
        cls.replay = load_replay(DATA / "orders.txt", DATA / "holdings.txt", DATA / "prices.txt")

    def test_generator_regenerates_all_bytes_and_provenance_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = generate(Path(temporary))
            self.assertEqual({path.name for path in DATA.iterdir()}, {path.name for path in generated.iterdir()})
            for source in DATA.iterdir():
                self.assertEqual(source.read_bytes(), (generated / source.name).read_bytes(), source.name)
        self.assertEqual(self.metadata["dataset_kind"], "synthetic_fixture")
        self.assertFalse(self.metadata["contains_real_market_data"])
        self.assertIsNone(self.metadata["source_provider"])
        self.assertIsNone(self.metadata["retrieved_at_utc"])
        for name, spec in self.metadata["source_files"].items():
            self.assertEqual(hashlib.sha256((DATA / name).read_bytes()).hexdigest(), spec["sha256"], name)
        self.assertEqual(hashlib.sha256((ROOT / "scripts/generate_dashboard_demo.py").read_bytes()).hexdigest(),
                         self.metadata["generator_sha256"])

    def test_dataset_layout_and_independent_pair_construction(self):
        orders = list(read_records(DATA / "orders.txt"))
        holdings = list(read_records(DATA / "holdings.txt"))
        prices = list(read_records(DATA / "prices.txt"))
        self.assertEqual(len(orders), 550)
        self.assertTrue(all(len(row) == 59 for row in orders))
        self.assertEqual(len(holdings), 50)
        self.assertTrue(all(len(row) == 26 for row in holdings))
        self.assertEqual(len(prices), 250)
        self.assertTrue(all(len(row) == 32 for row in prices))
        self.assertEqual(prices, sorted(prices))
        pairs = self.expected["settled_pairs"]
        self.assertEqual([pair["quantity"] for pair in pairs], list(range(1, 251)))
        self.assertEqual(sum(pair["quantity"] for pair in pairs), 31375)
        for pair in pairs:
            buy, sell = (orders[pair[key] - 1] for key in ("buy_line", "sell_line"))
            self.assertEqual(buy[28], "B")
            self.assertEqual(sell[28], "S")
            self.assertNotEqual(buy[12:20], sell[12:20])
            self.assertEqual(buy[20:28], sell[20:28])
            self.assertEqual(int(buy[29:35]), pair["quantity"])
            self.assertEqual(buy[29:35], sell[29:35])
            self.assertGreater(int(buy[35:45]), int(sell[35:45]))

    def test_real_pipeline_matches_every_expected_order_and_final_holding(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination, summary = run(DATA / "orders.txt", DATA / "holdings.txt", DATA / "prices.txt",
                                       Path(temporary) / "run")
            actual = [json.loads(line) for line in (destination / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(actual), 550)
            self.assertEqual(Counter(row["reason_code"] for row in actual), self.expected["reason_counts"])
            self.assertEqual(Counter(row["status"] for row in actual), {"SETTLED": 500, "REJECTED": 50})
            for spec, row in zip(self.expected["orders"], actual):
                for key, value in spec.items():
                    if key != "line":
                        self.assertEqual(row[key], value, (spec["line"], key))
            self.assertEqual(summary["totals"], {"input": 550, "total": 550, "settlement": 550,
                                                "settled": 500, "pending": 0, "rejected": 50})
            self.assertTrue(summary["holdings_reconciled"])
            self.assertEqual(summary["holdings"], self.expected["final_holdings"])
            self.assertEqual(list(read_records(destination / "audit.dat")), list(self.replay.audit))
            self.assertEqual(list(read_records(destination / "holdings.dat")), list(self.replay.holdout))
            report = (destination / "report.txt").read_text(encoding="utf-8")
            self.assertIn("TOTAL=550 SETTLED=500 PENDING=0 REJECTED=50", report)
            self.assertIn("BALANCE=PASS", report)

    def test_replay_has_250_atomic_matches_and_exact_execution_value(self):
        self.assertEqual(len(self.replay), 802)  # initial + 550 validation + 250 pair + complete
        settlements = [event for event in self.replay.events if event["phase"] == "settlement"]
        self.assertEqual(len(settlements), 250)
        previous_notional = 0
        for number, (event, pair) in enumerate(zip(settlements, self.expected["settled_pairs"]), 1):
            self.assertEqual(event["active_rows"], (pair["buy_line"], pair["sell_line"]))
            self.assertEqual(event["counts"]["settled"], 2 * number)
            self.assertEqual(event["executed_pairs"], number)
            self.assertEqual(event["executed_notional_paise"] - previous_notional, pair["execution_notional_paise"])
            previous_notional = event["executed_notional_paise"]
        final = self.replay.state(len(self.replay) - 1)
        self.assertEqual(final["executed_pairs"], 250)
        self.assertEqual(final["executed_notional_paise"], self.expected["executed_notional_paise"])
        self.assertEqual(final["valuation_paise"], self.expected["final_valuation_paise"])
        self.assertEqual({key: final["counts"][key] for key in ("total", "settled", "pending", "rejected")},
                         {"total": 550, "settled": 500, "pending": 0, "rejected": 50})
        self.assertEqual(Counter(row["reason_code"] for row in final["orders"]), self.expected["reason_counts"])

    def test_no_snapshot_oversells_or_changes_stock_inventory(self):
        prior = None
        for event in self.replay.events:
            stock_totals = defaultdict(int)
            for holding in event["holdings"]:
                self.assertGreaterEqual(holding["quantity"], 0)
                self.assertGreaterEqual(holding["available"], 0)
                self.assertGreaterEqual(holding["validation_available"], 0)
                self.assertLessEqual(holding["reserved"], holding["quantity"])
                stock_totals[holding["stock_code"]] += holding["quantity"]
            self.assertEqual(stock_totals, self.expected["initial_stock_quantities"])
            if event["phase"] == "validation":
                row = event["orders"][event["active_rows"][0] - 1]
                if row["status"] == "REJECTED":
                    self.assertEqual(event["holdings"], prior["holdings"])
            prior = event
        self.assertTrue(all(holding["reserved"] == 0 for holding in prior["holdings"]))

    def test_charts_have_varying_prices_and_never_use_future_quotes(self):
        quotes = defaultdict(list)
        for raw in read_records(DATA / "prices.txt"):
            quotes[raw[:8].rstrip()].append((datetime.strptime(raw[8:22], "%Y%m%d%H%M%S"), int(raw[22:32])))
        for event in self.replay.events:
            at = datetime.fromisoformat(event["as_of"]) if event["as_of"] else None
            for symbol, actual in event["quotes"].items():
                eligible = [price for quoted_at, price in quotes[symbol] if at and quoted_at <= at]
                self.assertEqual(actual, eligible[-1] if eligible else None)
        final = self.replay.state(len(self.replay) - 1)
        for symbol, series in final["price_series"].items():
            self.assertEqual(len(series["executions"]), 50)
            values = [point["price_paise"] for point in series["reference"]]
            self.assertGreater(len(set(values)), 30, symbol)
            self.assertTrue(any(first > second for first, second in zip(values, values[1:])), symbol)
            self.assertTrue(any(first < second for first, second in zip(values, values[1:])), symbol)


if __name__ == "__main__":
    unittest.main()
