"""Native UI checks for the full batch and reports embedded in the dashboard."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "dashboard-demo"


class LargeDashboardGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
        except ImportError as error:
            raise unittest.SkipTest(f"Tkinter unavailable: {error}") from error
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.update()
            probe.destroy()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Interactive Tk display unavailable: {error}") from error
        from stkcp.replay import load_replay

        cls.tk = tk
        cls.replay = load_replay(*(FIXTURE / f"{name}.txt" for name in ("orders", "holdings", "prices")))

    def setUp(self):
        from stkcp.dashboard import SettlementDashboard

        self.root = self.tk.Tk()
        self.root.withdraw()
        self.dashboard = SettlementDashboard(self.root, self.replay, interval_ms=80)
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        self.dashboard.pause()
        self.root.destroy()

    def tree_values(self, tree):
        return tuple(tuple(tree.item(item, "values")) for item in tree.get_children())

    def test_all_reports_are_available_in_window_before_playback(self):
        dashboard = self.dashboard
        self.assertEqual(dashboard.index, 0)
        tabs = {dashboard.notebook.tab(tab, "text") for tab in dashboard.notebook.tabs()}
        self.assertEqual(tabs, {
            "Replay & Charts", "Full Report", "Trade Tape", "Audit & Settlement", "Holdings", "Inputs & Checks",
        })
        self.assertEqual(len(dashboard.audit_tree.get_children()), 550)
        self.assertEqual(len(dashboard.trade_tree.get_children()), 250)
        self.assertEqual(len(dashboard.report_holdings_tree.get_children()), len(self.replay.state(len(self.replay) - 1)["holdings"]))
        report = dashboard.report_text.get("1.0", "end")
        for value in ("550", "500", "50"):
            self.assertIn(value, report)
        self.assertTrue(dashboard.summary_text.get("1.0", "end").strip())
        self.assertTrue(dashboard.inputs_tree.get_children())
        checks = self.tree_values(dashboard.checks_tree)
        self.assertTrue(checks)
        self.assertTrue(all(row[1] == "PASS" for row in checks))

    def test_large_replay_completes_and_restarts_without_changing_final_reports(self):
        dashboard = self.dashboard
        audit = self.tree_values(dashboard.audit_tree)
        trades = self.tree_values(dashboard.trade_tree)
        holdings = self.tree_values(dashboard.report_holdings_tree)
        report = dashboard.report_text.get("1.0", "end")
        dashboard._seek(len(self.replay) - 2)
        self.assertEqual(dashboard.counts_vars["settled"].get(), "500")
        self.assertEqual(dashboard.counts_vars["matched"].get(), "250")
        dashboard.next_step()
        self.root.update()
        self.assertEqual(dashboard.index, len(self.replay) - 1)
        self.assertEqual(dashboard.counts_vars["processed"].get(), "550 / 550")
        self.assertEqual(dashboard.counts_vars["settled"].get(), "500")
        self.assertEqual(dashboard.counts_vars["rejected"].get(), "50")
        self.assertEqual(dashboard.counts_vars["pending"].get(), "0")
        self.assertFalse(dashboard.is_playing)
        self.assertIsNone(dashboard.timer_id)
        self.assertEqual(len(dashboard.event_tree.get_children()), len(self.replay))
        dashboard.restart()
        self.root.update()
        self.assertEqual(dashboard.index, 0)
        self.assertEqual(dashboard.counts_vars["settled"].get(), "0")
        self.assertEqual(len(dashboard.event_tree.get_children()), 1)
        self.assertEqual(self.tree_values(dashboard.audit_tree), audit)
        self.assertEqual(self.tree_values(dashboard.trade_tree), trades)
        self.assertEqual(self.tree_values(dashboard.report_holdings_tree), holdings)
        self.assertEqual(dashboard.report_text.get("1.0", "end"), report)

    def test_report_tabs_can_be_selected_and_scrolled_with_large_batch(self):
        dashboard = self.dashboard
        self.root.geometry("1280x720")
        self.root.deiconify()
        for tab in dashboard.notebook.tabs():
            dashboard.notebook.select(tab)
            self.root.update()
        for tree in (dashboard.audit_tree, dashboard.trade_tree, dashboard.report_holdings_tree, dashboard.inputs_tree):
            tree.yview_moveto(1)
            tree.xview_moveto(1)
            self.root.update()
            self.assertTrue(tree.get_children())
        dashboard.notebook.select(0)
        dashboard.next_step()
        self.root.update()
        self.assertEqual(dashboard.index, 1)

    def test_audit_filters_reveal_the_actual_settled_and_rejected_rows(self):
        views = self.dashboard.report_views
        for status, count in (("SETTLED", 500), ("REJECTED", 50), ("PENDING", 0)):
            with self.subTest(status=status):
                views.audit_status_var.set(status)
                views._filter_audit()
                self.assertEqual(len(views.audit_tree.get_children()), count)
                self.assertTrue(all(row[6] == status for row in self.tree_values(views.audit_tree)))
        views.audit_status_var.set("REJECTED")
        views.audit_search_var.set("HOLD01")
        self.assertEqual(len(views.audit_tree.get_children()), 10)
        self.assertTrue(all(row[7] == "HOLD01" for row in self.tree_values(views.audit_tree)))
        views.audit_status_var.set("ALL")
        views.audit_search_var.set("")
        self.assertEqual(len(views.audit_tree.get_children()), 550)

    def test_audit_modes_display_every_json_and_fixed_width_record(self):
        views = self.dashboard.report_views
        views.audit_mode_var.set("JSON Lines")
        views._audit_mode_changed()
        documents = tuple(json.loads(line) for line in views.audit_raw_text.get("1.0", "end").splitlines() if line)
        self.assertEqual(documents, self.dashboard.reports.audit_documents)
        self.assertEqual(len(documents), 550)
        self.assertEqual(sum(row["status"] == "SETTLED" for row in documents), 500)
        for mode, expected in (
            ("Audit fixed-width", self.dashboard.reports.audit_records),
            ("Settlement fixed-width", self.dashboard.reports.settlement_records),
        ):
            with self.subTest(mode=mode):
                views.audit_mode_var.set(mode)
                views._audit_mode_changed()
                records = tuple(views.audit_raw_text.get("1.0", "end").splitlines())
                if records and records[-1] == "":
                    records = records[:-1]
                self.assertEqual(records, expected)
                self.assertEqual(len(records), 550)
                self.assertTrue(all(len(row) == 110 for row in records))

    def test_input_selector_and_trade_search_keep_all_records_accessible(self):
        views = self.dashboard.report_views
        for kind in ("orders", "holdings", "prices"):
            with self.subTest(kind=kind):
                views.input_kind_var.set(kind)
                views._input_changed()
                rows = self.tree_values(views.inputs_tree)
                self.assertEqual(tuple(row[2] for row in rows), self.dashboard.reports.inputs[kind])
                self.assertEqual(len(rows), len(self.dashboard.reports.inputs[kind]))
        views.trade_search_var.set("ALPHA")
        expected = tuple(pair for pair in self.dashboard.reports.trade_pairs if pair["stock_code"] == "ALPHA")
        rows = self.tree_values(views.trade_tree)
        self.assertEqual(len(rows), len(expected))
        self.assertTrue(all(row[2] == "ALPHA" for row in rows))
        views.trade_search_var.set("")
        self.assertEqual(len(views.trade_tree.get_children()), 250)

    def test_finish_batch_pauses_and_report_keyboard_does_not_control_replay(self):
        dashboard = self.dashboard
        dashboard.next_step()
        dashboard.play()
        self.assertIsNotNone(dashboard.timer_id)
        dashboard.finish_batch()
        self.assertEqual(dashboard.index, len(self.replay) - 1)
        self.assertFalse(dashboard.is_playing)
        self.assertIsNone(dashboard.timer_id)
        dashboard.restart()
        dashboard.next_step()
        dashboard.notebook.select(1)
        self.root.update()
        dashboard._toggle()
        dashboard._shortcut_next()
        dashboard._shortcut_restart()
        self.assertEqual(dashboard.index, 1)
        self.assertFalse(dashboard.is_playing)
        self.assertIsNone(dashboard.timer_id)


if __name__ == "__main__":
    unittest.main()
