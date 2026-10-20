"""Compare real pipeline artifacts with the hand-reasoned fixture contract."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stkcp.pipeline import run


ROOT = Path(__file__).resolve().parents[1]


class FixtureAcceptanceTests(unittest.TestCase):
    def test_every_expected_order_and_holding_against_pipeline_output(self):
        expected = json.loads((ROOT / "data/expected-results.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            destination, summary = run(ROOT / "data/orders.txt", ROOT / "data/holdings.txt",
                                       ROOT / "data/prices.txt", Path(temporary) / "run")
            actual = [json.loads(line) for line in (destination / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(actual), expected["input_count"])
            for spec, record in zip(expected["orders"], actual):
                with self.subTest(line=spec["line"]):
                    for key in ("order_id", "status", "reason_code"):
                        self.assertEqual(record[key], spec[key], key)
                    for key in ("reference_price", "execution_price", "reference_notional"):
                        self.assertEqual(record[key + "_paise"], spec[key], key)
            self.assertEqual({key.upper(): summary["totals"][key]
                              for key in ("settled", "pending", "rejected")}, expected["counts"])
            actual_holdings = {(row["client_id"], row["stock_code"]): row for row in summary["holdings"]}
            expected_holdings = {(row["client_id"], row["stock_code"]): row for row in expected["final_holdings"]}
            self.assertEqual(set(actual_holdings), set(expected_holdings))
            for key, spec in expected_holdings.items():
                with self.subTest(holding=key):
                    self.assertEqual(actual_holdings[key]["quantity"], spec["quantity"])
                    self.assertEqual(actual_holdings[key]["reference_price_paise"], spec["reference_price"])
                    self.assertEqual(actual_holdings[key]["valuation_paise"], spec["valuation"])

    def test_fixture_is_explicitly_synthetic_and_price_hash_matches(self):
        metadata = json.loads((ROOT / "data/market-data-metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["dataset_kind"], "synthetic_fixture")
        self.assertFalse(metadata["contains_real_market_data"])
        self.assertIsNone(metadata["source_provider"])
        self.assertIsNone(metadata["retrieved_at_utc"])
        self.assertEqual(hashlib.sha256((ROOT / "data/prices.txt").read_bytes()).hexdigest(), metadata["prices_sha256"])


if __name__ == "__main__":
    unittest.main()
