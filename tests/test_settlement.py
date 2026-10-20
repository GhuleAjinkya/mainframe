import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from stkcp.audit_to_json import convert, parse_audit
from stkcp.contracts import EXPLANATIONS, order_record, read_records, write_records
from stkcp.engine import process
from stkcp.errors import AuditError, InfrastructureError
from stkcp.pipeline import run
from stkcp.report import report
from stkcp.reconciliation import reconcile_holdings

ROOT = Path(__file__).resolve().parents[1]


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.orders = self.root / "orders.txt"
        self.holdings = self.root / "holdings.txt"
        self.prices = self.root / "prices.txt"
        write_records(self.holdings, [f"{'SELLER':<8}{'ALPHA':<8}{20:010d}"])
        write_records(self.prices, [f"{'ALPHA':<8}20260102090000{10000:010d}"])

    def order(self, name, client="BUYER", side="B", qty=5, price=10000, time="20260102100000", symbol="ALPHA"):
        return order_record(name, client, symbol, side, qty, price, time)

    def execute(self, records):
        write_records(self.orders, records)
        audit, holdings = process(self.orders, self.holdings, self.prices)
        return [parse_audit(raw) for raw in audit], holdings

    def test_fixture_end_to_end(self):
        output, summary = run(ROOT / "data/orders.txt", ROOT / "data/holdings.txt", ROOT / "data/prices.txt", self.root / "run")
        self.assertEqual(summary["totals"], {"total": 14, "settled": 4, "pending": 2, "rejected": 8, "input": 14, "settlement": 14})
        audit = list(read_records(output / "audit.dat"))
        self.assertTrue(all(len(raw) == 110 for raw in audit))
        self.assertEqual(audit, list(read_records(output / "settlement.dat")))
        documents = [json.loads(line) for line in (output / "audit.jsonl").read_text().splitlines()]
        self.assertEqual(len(documents), 14)
        self.assertEqual({record["reason_code"] for record in documents}, set(EXPLANATIONS))
        holdings = {(entry["client_id"], entry["stock_code"]): entry for entry in summary["holdings"]}
        self.assertEqual(holdings[("SELLER1", "ALPHA")]["quantity"], 90)
        self.assertEqual(holdings[("SELLER2", "BETA")]["quantity"], 15)
        self.assertEqual(holdings[("BUYER1", "ALPHA")]["quantity"], 15)
        self.assertIsNone(holdings[("FUTCLNT", "FUTURE")]["valuation_paise"])
        self.assertIn("BALANCE=PASS", (output / "report.txt").read_text())

    def test_whole_order_matching_and_price(self):
        rows, holdings = self.execute([self.order("B1", price=10500), self.order("S1", "SELLER", "S", price=9900)])
        self.assertEqual([row["status"] for row in rows], ["SETTLED", "SETTLED"])
        self.assertEqual([row["execution_price_paise"] for row in rows], [9900, 9900])
        self.assertEqual(int(holdings[0][16:26]), 15)
        self.assertEqual(int(holdings[1][16:26]), 5)

    def test_pending_sells_reserve_and_do_not_reduce_final_holdings(self):
        rows, holdings = self.execute([self.order("S1", "SELLER", "S", 15), self.order("S2", "SELLER", "S", 6)])
        self.assertEqual([row["reason_code"] for row in rows], ["PEND01", "HOLD01"])
        self.assertEqual(int(holdings[0][16:26]), 20)

    def test_rejected_sell_does_not_reserve(self):
        rows, holdings = self.execute([self.order("S0", "SELLER", "S", 21), self.order("S1", "SELLER", "S", 20), self.order("B1", qty=20)])
        self.assertEqual([row["reason_code"] for row in rows], ["HOLD01", "OK000", "OK000"])
        self.assertEqual(int(holdings[0][16:26]), 0)

    def test_no_partial_fill_no_self_trade_no_uncrossed_trade(self):
        rows, _ = self.execute([self.order("B1", "SELLER", qty=5), self.order("S1", "SELLER", "S", 5), self.order("B2", qty=4), self.order("B3", qty=5, price=9500)])
        self.assertTrue(all(row["reason_code"] == "PEND01" for row in rows))

    def test_fifo_earliest_compatible_and_single_use(self):
        rows, _ = self.execute([self.order("B1"), self.order("B2", "BUYER2"), self.order("S1", "SELLER", "S")])
        self.assertEqual([row["reason_code"] for row in rows], ["OK000", "PEND01", "OK000"])

    def test_duplicate_precedence_and_malformed_does_not_reserve(self):
        valid = self.order("ID1")
        malformed = valid[:29] + "00X001" + valid[35:]
        badside = valid[:28] + "X" + valid[29:]
        rows, _ = self.execute([malformed, badside, valid])
        self.assertEqual([row["reason_code"] for row in rows], ["DATA001", "SIDE001", "DUP001"])

    def test_no_future_and_stale_lookup(self):
        rows, _ = self.execute([self.order("EARLY", time="20260102085959"), self.order("STALE", time="20260109090001"), self.order("BOUNDARY", time="20260109090000")])
        self.assertEqual([row["reason_code"] for row in rows], ["PRICE01", "PRICE01", "PEND01"])
        self.assertEqual([row["reference_price_paise"] for row in rows], [None, None, 10000])

    def test_latest_reference_and_band_inclusive(self):
        write_records(self.prices, [f"{'ALPHA':<8}20260101090000{9000:010d}", f"{'ALPHA':<8}20260102090000{10000:010d}", f"{'ALPHA':<8}20260102110000{20000:010d}"])
        rows, _ = self.execute([self.order("LOW", price=9000), self.order("HIGH", price=11000), self.order("OUT", price=11001)])
        self.assertEqual([row["reason_code"] for row in rows], ["PEND01", "PEND01", "PRICE01"])
        self.assertTrue(all(row["reference_price_paise"] == 10000 for row in rows))

    def test_empty_orders_and_empty_prices(self):
        rows, holdings = self.execute([])
        self.assertEqual(rows, [])
        self.assertEqual(int(holdings[0][26:36]), 0)
        write_records(self.prices, [])
        rows, _ = self.execute([self.order("B1")])
        self.assertEqual(rows[0]["reason_code"], "PRICE01")

    def test_malformed_calendar_and_lengths(self):
        valid = self.order("B1")
        rows, _ = self.execute(["", "SHORT", valid + "X", valid[:45] + "20260230090000", valid[:45] + "20260102240000"])
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["reason_code"] == "DATA001" for row in rows))

    def test_price_input_invalid_sort_duplicate_and_missing(self):
        write_records(self.orders, [])
        price = f"{'ALPHA':<8}20260102090000{10000:010d}"
        for values in ([price, price], [price, price[:8] + "20260101090000" + price[22:]], [price[:-1]], [price[:22] + "0000000000"]):
            with self.subTest(values=values):
                write_records(self.prices, values)
                with self.assertRaises(InfrastructureError):
                    process(self.orders, self.holdings, self.prices)

    def test_order_table_overflow_is_fatal_without_publication(self):
        write_records(self.orders, [self.order(f"O{i}") for i in range(1001)])
        output = self.root / "failed"
        with self.assertRaises(InfrastructureError):
            run(self.orders, self.holdings, self.prices, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".stkcp-*")), [])

    def test_holdings_overflow_and_bad_seed_fatal(self):
        write_records(self.holdings, [f"{'BUYER':<8}{'ALPHA':<8}{9999999999:010d}", f"{'SELLER':<8}{'ALPHA':<8}{20:010d}"])
        with self.assertRaises(InfrastructureError):
            self.execute([self.order("B1"), self.order("S1", "SELLER", "S")])
        write_records(self.holdings, ["broken"])
        with self.assertRaises(InfrastructureError):
            self.execute([])

    def test_fatal_cli_returns12_and_gates_converter_report(self):
        output = self.root / "failed-cli"
        result = subprocess.run([sys.executable, "-m", "stkcp", "run", "--orders", str(self.root / "missing"), "--holdings", str(self.holdings), "--prices", str(self.prices), "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 12)
        self.assertIn("BATCH FAILED", result.stderr)
        self.assertFalse(output.exists())

    def test_determinism_and_existing_output_protected(self):
        sources = (ROOT / "data/orders.txt", ROOT / "data/holdings.txt", ROOT / "data/prices.txt")
        first, _ = run(*sources, self.root / "one")
        second, _ = run(*sources, self.root / "two")
        for name in ("audit.dat", "settlement.dat", "holdings.dat", "audit.jsonl", "report.txt", "summary.json"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
        before = (first / "audit.jsonl").read_bytes()
        with self.assertRaises(InfrastructureError):
            run(*sources, first)
        self.assertEqual((first / "audit.jsonl").read_bytes(), before)

    def test_converter_atomic_and_json_escaping(self):
        audit, destination = self.root / "audit", self.root / "json"
        raw = 'BAD"\\' + " " * 54 + "REJECTED" + "DATA001" + "0" * 36
        self.assertEqual(len(raw), 110)
        write_records(audit, [raw])
        self.assertEqual(convert(audit, destination), 1)
        self.assertEqual(json.loads(destination.read_text())["raw_order"][:5], 'BAD"\\')
        previous = destination.read_bytes()
        write_records(audit, [raw, "broken"])
        with self.assertRaises(AuditError):
            convert(audit, destination)
        self.assertEqual(destination.read_bytes(), previous)
        self.assertEqual(list(self.root.glob(".audit-*")), [])

    def test_unknown_reason_safe_fallback_and_balance_failure(self):
        rows, _ = self.execute([self.order("B1")])
        audit, _ = process(self.orders, self.holdings, self.prices)
        unknown = audit[0][:67] + "NEW001 " + audit[0][74:]
        self.assertIn("Unrecognized", parse_audit(unknown)["explanation"])
        audit_path, settle_path = self.root / "a", self.root / "s"
        write_records(audit_path, audit)
        write_records(settle_path, [])
        with self.assertRaisesRegex(AuditError, "BALANCE=FAIL"):
            report(audit_path, self.orders, settle_path)

    def test_converter_cli_returns8_and_preserves_existing_output(self):
        source, destination = self.root / "bad", self.root / "existing"
        source.write_text("short\n", encoding="ascii")
        destination.write_text("previous\n")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/audit_to_json.py"), "--input", str(source), "--output", str(destination)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 8)
        self.assertIn("record 1", result.stderr)
        self.assertEqual(destination.read_text(), "previous\n")

    def test_independent_holdings_reconciliation_rejects_tampering(self):
        self.execute([self.order("B1"), self.order("S1", "SELLER", "S")])
        audit, holdings = process(self.orders, self.holdings, self.prices)
        audit_path, holdout_path = self.root / "audit", self.root / "holdout"
        write_records(audit_path, audit)
        write_records(holdout_path, holdings)
        self.assertEqual(len(reconcile_holdings(self.holdings, audit_path, holdout_path)), 2)
        for bad in ([holdings[0]], holdings + [holdings[0]], [holdings[0][:16] + "0000000016" + holdings[0][26:]] + holdings[1:]):
            with self.subTest(rows=bad):
                write_records(holdout_path, bad)
                with self.assertRaises(InfrastructureError):
                    reconcile_holdings(self.holdings, audit_path, holdout_path)

    def test_trade_quantities_cannot_be_settled_without_counterpart(self):
        self.execute([self.order("B1"), self.order("S1", "SELLER", "S")])
        audit, holdings = process(self.orders, self.holdings, self.prices)
        audit_path, holdout_path = self.root / "audit", self.root / "holdout"
        write_records(audit_path, audit[:1])
        write_records(holdout_path, holdings)
        with self.assertRaisesRegex(InfrastructureError, "do not balance"):
            reconcile_holdings(self.holdings, audit_path, holdout_path)

    def test_converter_rejects_corrupted_classification_and_prices(self):
        self.execute([self.order("B1"), self.order("S1", "SELLER", "S")])
        audit, _ = process(self.orders, self.holdings, self.prices)
        for bad in (audit[0][:59] + "PENDING " + audit[0][67:], audit[0][:84] + "0000010001" + audit[0][94:], audit[0][:94] + "0" * 16):
            with self.subTest(record=bad), self.assertRaises(AuditError):
                parse_audit(bad)


if __name__ == "__main__":
    unittest.main()
