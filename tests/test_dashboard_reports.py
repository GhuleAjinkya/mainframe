"""Dashboard reports exercise the real batch artifact validation pipeline."""

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest

from stkcp.contracts import order_record, read_records, write_records
from stkcp.dashboard_reports import build_dashboard_reports
from stkcp.errors import InfrastructureError
from stkcp.pipeline import run
from stkcp.replay import load_replay


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = tuple(ROOT / "data" / name for name in ("orders.txt", "holdings.txt", "prices.txt"))


class DashboardReportTests(unittest.TestCase):
    def test_dashboard_artifacts_match_the_actual_pipeline(self):
        replay = load_replay(*FIXTURE)
        reports = build_dashboard_reports(replay)
        with tempfile.TemporaryDirectory() as temporary:
            output, summary = run(*FIXTURE, Path(temporary) / "batch")
            self.assertEqual(reports.summary, summary)
            self.assertEqual(reports.audit_records, tuple(read_records(output / "audit.dat")))
            self.assertEqual(reports.settlement_records, tuple(read_records(output / "settlement.dat")))
            self.assertTrue(reports.report_text.startswith((output / "report.txt").read_text(encoding="utf-8")))
        self.assertEqual(len(reports.audit_documents), 14)
        self.assertEqual(reports.checks, {
            "input_snapshot_match": "PASS", "report_balance": "PASS", "json_record_count": "PASS",
            "settlement_content": "PASS", "holdings_reconciliation": "PASS", "trade_balance": "PASS",
        })
        self.assertEqual(len(reports.trade_pairs), 2)
        self.assertEqual(sum(row["count"] for row in reports.rejections), 8)
        self.assertEqual(len(reports.prices), len(reports.inputs["prices"]))
        self.assertIn("MATCHED_PAIRS=2", reports.report_text)
        self.assertIn("VALIDATION CHECKS", reports.report_text)
        self.assertIn("REXX executed: false", reports.report_text)

    def test_captured_inputs_survive_deleted_source_files_and_preserve_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = tuple(Path(temporary) / name for name in ("orders", "holdings", "prices"))
            source_bytes = {}
            for name, path, source in zip(("orders", "holdings", "prices"), paths, FIXTURE):
                source_bytes[name] = source.read_bytes().replace(b"\n", b"\r\n")
                path.write_bytes(source_bytes[name])
            replay = load_replay(*paths)
            for path in paths:
                path.unlink()
            reports = build_dashboard_reports(replay)
        for name, data in source_bytes.items():
            self.assertEqual(reports.summary["inputs"][name]["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(replay.input_snapshots[name], data)
        with self.assertRaises(TypeError):
            replay.input_snapshots["orders"] = b"changed"
        self.assertEqual(reports.audit_records, replay.audit)

    def test_changed_original_file_cannot_change_a_captured_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = tuple(Path(temporary) / name for name in ("orders", "holdings", "prices"))
            for target, source in zip(paths, FIXTURE):
                target.write_bytes(source.read_bytes())
            replay = load_replay(*paths)
            paths[0].write_bytes(b"DIFFERENT\n")
            reports = build_dashboard_reports(replay)
            self.assertEqual(reports.summary["totals"]["input"], 14)
            self.assertEqual(reports.inputs["orders"][0], replay.events[0]["orders"][0]["raw_order"])
            legacy = replace(replay, input_snapshots=None)
            with self.assertRaisesRegex(InfrastructureError, "do not match"):
                build_dashboard_reports(legacy)

    def test_invalid_replay_output_is_rejected_instead_of_showing_success(self):
        replay = load_replay(*FIXTURE)
        tampered = replace(replay, audit=replay.audit[:-1])
        with self.assertRaisesRegex(InfrastructureError, "do not match"):
            build_dashboard_reports(tampered)

    def test_trace_must_cover_every_settled_audit_row(self):
        replay = load_replay(*FIXTURE)
        tampered = replace(replay, events=tuple(event for event in replay.events if event["phase"] != "settlement"))
        with self.assertRaisesRegex(InfrastructureError, "does not cover"):
            build_dashboard_reports(tampered)

    def test_all_input_records_and_all_trade_pairs_remain_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = tuple(Path(temporary) / name for name in ("orders", "holdings", "prices"))
            buy = order_record("B1", "BUYER", "ALPHA", "B", 5, 10500, "20260102100000")
            sell = order_record("S1", "SELLER", "ALPHA", "S", 5, 9900, "20260102100100")
            raw_orders = (buy, sell, "", "MALFORMED ORIGINAL ORDER " * 4)
            write_records(paths[0], raw_orders)
            write_records(paths[1], [f"{'SELLER':<8}{'ALPHA':<8}{10:010d}"])
            write_records(paths[2], [f"{'ALPHA':<8}20260102090000{10000:010d}"])
            replay = load_replay(*paths)
        reports = build_dashboard_reports(replay)
        self.assertEqual(reports.inputs["orders"], raw_orders)
        self.assertEqual(reports.audit_documents[3]["raw_order"], raw_orders[3][:59])
        pair, = reports.trade_pairs
        self.assertEqual((pair["buy_row"], pair["sell_row"], pair["quantity"]), (1, 2, 5))
        self.assertEqual(pair["execution_price_paise"], 9900)
        self.assertEqual(pair["notional_paise"], 49500)
        self.assertIn("BUY=B1", reports.report_text)
        self.assertIn("SELL=S1", reports.report_text)
        self.assertIn("DATA001", reports.report_text)
        self.assertEqual(reports.summary["totals"]["rejected"], 2)

    def test_empty_batch_has_real_balanced_empty_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = tuple(Path(temporary) / name for name in ("orders", "holdings", "prices"))
            for path in paths:
                path.write_bytes(b"")
            replay = load_replay(*paths)
        reports = build_dashboard_reports(replay)
        self.assertEqual(reports.audit_documents, ())
        self.assertEqual(reports.holdings, ())
        self.assertEqual(reports.trade_pairs, ())
        self.assertEqual(reports.summary["totals"]["total"], 0)
        self.assertTrue(all(result == "PASS" for result in reports.checks.values()))


if __name__ == "__main__":
    unittest.main()
