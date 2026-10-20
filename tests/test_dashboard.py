"""CLI isolation and native dashboard control checks; no external packages."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from stkcp.__main__ import main


ROOT = Path(__file__).resolve().parents[1]


class DashboardCommandTests(unittest.TestCase):
    def test_dashboard_uses_fixture_and_supplied_interval(self):
        launch = mock.Mock(return_value=0)
        module = types.SimpleNamespace(launch_dashboard=launch)
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": module}):
            self.assertEqual(main(["dashboard", "--interval-ms", "1250"]), 0)
        launch.assert_called_once_with(
            orders=ROOT / "data/dashboard-demo/orders.txt",
            holdings=ROOT / "data/dashboard-demo/holdings.txt",
            prices=ROOT / "data/dashboard-demo/prices.txt",
            interval_ms=1250,
        )

    def test_dashboard_defaults_to_large_demo_and_faster_replay(self):
        launch = mock.Mock(return_value=0)
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": types.SimpleNamespace(launch_dashboard=launch)}):
            self.assertEqual(main(["dashboard"]), 0)
        launch.assert_called_once_with(
            orders=ROOT / "data/dashboard-demo/orders.txt",
            holdings=ROOT / "data/dashboard-demo/holdings.txt",
            prices=ROOT / "data/dashboard-demo/prices.txt",
            interval_ms=80,
        )

    def test_sample_flag_keeps_original_acceptance_fixture_available(self):
        launch = mock.Mock(return_value=0)
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": types.SimpleNamespace(launch_dashboard=launch)}):
            self.assertEqual(main(["dashboard", "--sample"]), 0)
        launch.assert_called_once_with(
            orders=ROOT / "data/orders.txt", holdings=ROOT / "data/holdings.txt",
            prices=ROOT / "data/prices.txt", interval_ms=80,
        )

    def test_sample_flag_cannot_silently_override_custom_inputs(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["dashboard", "--sample", "--orders", "orders.txt", "--holdings", "holdings.txt", "--prices", "prices.txt"])
        self.assertEqual(raised.exception.code, 2)

    def test_dashboard_custom_inputs_require_all_three(self):
        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(["dashboard", "--orders", "orders.txt"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("require --orders, --holdings, and --prices together", error.getvalue())

    def test_dashboard_passes_custom_files_without_creating_batch_output(self):
        launch = mock.Mock(return_value=0)
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": types.SimpleNamespace(launch_dashboard=launch)}):
            self.assertEqual(main([
                "dashboard", "--orders", "custom-orders.txt", "--holdings", "custom-holdings.txt",
                "--prices", "custom-prices.txt",
            ]), 0)
        launch.assert_called_once_with(
            orders=Path("custom-orders.txt"), holdings=Path("custom-holdings.txt"),
            prices=Path("custom-prices.txt"), interval_ms=80,
        )

    def test_dashboard_interval_must_be_positive(self):
        for value in ("0", "-1"):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["dashboard", "--interval-ms", value])
            self.assertEqual(raised.exception.code, 2)

    def test_missing_gui_module_is_a_clear_failure(self):
        error = io.StringIO()
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": None}), redirect_stderr(error):
            self.assertEqual(main(["dashboard"]), 12)
        self.assertIn("DASHBOARD FAILED (RC12)", error.getvalue())

    def test_unavailable_desktop_is_a_clear_failure(self):
        launch = mock.Mock(side_effect=RuntimeError("Tk cannot open a desktop display"))
        error = io.StringIO()
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": types.SimpleNamespace(launch_dashboard=launch)}), redirect_stderr(error):
            self.assertEqual(main(["dashboard"]), 12)
        self.assertIn("Tk cannot open a desktop display", error.getvalue())

    def test_batch_command_works_when_gui_modules_are_unavailable(self):
        summary = {"totals": {"total": 0, "settled": 0, "pending": 0, "rejected": 0}}
        with mock.patch.dict(sys.modules, {"stkcp.dashboard": None, "tkinter": None}), \
                mock.patch("stkcp.__main__.run", return_value=(Path("unused"), summary)), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["demo", "--output", "unused"]), 0)
        self.assertIn("RC0 TOTAL=0", output.getvalue())


class NativeDashboardTests(unittest.TestCase):
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
        cls.tk = tk

    def setUp(self):
        from stkcp.dashboard import SettlementDashboard
        from stkcp.replay import load_replay

        self.root = self.tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.close)
        self.replay = load_replay(ROOT / "data/orders.txt", ROOT / "data/holdings.txt", ROOT / "data/prices.txt")
        self.dashboard = SettlementDashboard(self.root, self.replay, interval_ms=20)
        self.root.update()

    def close(self):
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None:
            dashboard.pause()
        self.root.destroy()

    def process_events_for(self, milliseconds):
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.002)
        self.root.update()

    def tree_values(self, tree):
        return tuple(tuple(tree.item(item, "values")) for item in tree.get_children())

    def finish(self):
        while self.dashboard.index < len(self.replay.events) - 1:
            self.dashboard.next_step()
        self.root.update()

    def test_starts_paused_and_next_advances_one_step(self):
        self.assertEqual(self.dashboard.index, 0)
        self.assertFalse(self.dashboard.is_playing)
        self.assertIsNone(self.dashboard.timer_id)
        self.process_events_for(30)
        self.assertEqual(self.dashboard.index, 0)
        self.dashboard.next_step()
        self.root.update()
        self.assertEqual(self.dashboard.index, 1)
        self.assertFalse(self.dashboard.is_playing)

    def test_play_progresses_and_pause_cancels_future_steps(self):
        self.dashboard.play()
        self.process_events_for(55)
        self.assertGreater(self.dashboard.index, 0)
        self.dashboard.pause()
        paused_index = self.dashboard.index
        self.assertFalse(self.dashboard.is_playing)
        self.assertIsNone(self.dashboard.timer_id)
        self.process_events_for(55)
        self.assertEqual(self.dashboard.index, paused_index)

    def test_restart_restores_holdings_and_repeat_does_not_duplicate_trades(self):
        initial_holdings = self.tree_values(self.dashboard.holding_tree)
        self.finish()
        final_holdings = self.tree_values(self.dashboard.holding_tree)
        self.assertNotEqual(final_holdings, initial_holdings)
        self.assertEqual(self.dashboard.counts_vars["settled"].get(), "4")
        self.assertEqual(self.dashboard.counts_vars["pending"].get(), "2")
        self.assertEqual(self.dashboard.counts_vars["rejected"].get(), "8")
        self.assertEqual(self.dashboard.counts_vars["matched"].get(), "2")
        final_events = self.tree_values(self.dashboard.event_tree)
        self.dashboard.restart()
        self.root.update()
        self.assertEqual(self.dashboard.index, 0)
        self.assertFalse(self.dashboard.is_playing)
        self.assertEqual(self.tree_values(self.dashboard.holding_tree), initial_holdings)
        self.finish()
        self.assertEqual(self.tree_values(self.dashboard.holding_tree), final_holdings)
        self.assertEqual(self.tree_values(self.dashboard.event_tree), final_events)

    def test_completion_cancels_timer_and_extra_next_is_harmless(self):
        self.dashboard.timeline.set(len(self.replay.events) - 2)
        self.root.update()
        self.dashboard.play()
        self.process_events_for(55)
        final_index = self.dashboard.index
        self.assertEqual(final_index, len(self.replay.events) - 1)
        self.dashboard.play()
        self.dashboard.next_step()
        self.root.update()
        self.assertEqual(self.dashboard.index, final_index)
        self.assertFalse(self.dashboard.is_playing)
        self.assertIsNone(self.dashboard.timer_id)
        self.assertTrue(self.dashboard.price_canvas.find_all())
        self.assertTrue(self.dashboard.volume_canvas.find_all())

    def test_slider_and_event_selection_pause_and_revisit_steps(self):
        self.dashboard.play()
        self.dashboard.timeline.set(6)
        self.root.update()
        self.assertEqual(self.dashboard.index, 6)
        self.assertFalse(self.dashboard.is_playing)
        self.assertIsNone(self.dashboard.timer_id)
        self.dashboard.event_tree.selection_set("e2")
        self.root.update()
        self.assertEqual(self.dashboard.index, 2)
        self.assertFalse(self.dashboard.is_playing)

    def test_speed_change_replaces_timer_without_restarting(self):
        self.dashboard.interval_ms = 900
        self.dashboard.next_step()
        self.dashboard.play()
        old_timer = self.dashboard.timer_id
        self.dashboard.speed_var.set("2x")
        self.dashboard._speed_changed()
        self.assertTrue(self.dashboard.is_playing)
        self.assertEqual(self.dashboard.index, 1)
        self.assertIsNotNone(self.dashboard.timer_id)
        self.assertNotEqual(old_timer, self.dashboard.timer_id)

    def test_window_creation_failure_returns_clean_cli_diagnostic(self):
        error = io.StringIO()
        with mock.patch("stkcp.dashboard.tk.Tk", side_effect=self.tk.TclError("display not available")), redirect_stderr(error):
            self.assertEqual(main(["dashboard"]), 12)
        self.assertIn("Tkinter could not open a desktop window", error.getvalue())

    def test_small_window_keeps_graphs_readable_and_lower_panels_reachable(self):
        self.root.geometry("1280x720")
        self.root.deiconify()
        self.root.update()
        self.assertGreaterEqual(self.dashboard.price_canvas.winfo_height(), 120)
        self.assertGreaterEqual(self.dashboard.volume_canvas.winfo_height(), 120)
        top, bottom = self.dashboard.viewport.yview()
        self.assertLess(bottom - top, 1)
        self.dashboard.viewport.yview_moveto(1)
        self.root.update()
        viewport = self.dashboard.viewport
        event_top = self.dashboard.event_tree.winfo_rooty()
        event_bottom = event_top + self.dashboard.event_tree.winfo_height()
        self.assertGreaterEqual(event_top, viewport.winfo_rooty())
        self.assertLessEqual(event_bottom, viewport.winfo_rooty() + viewport.winfo_height())

    def test_empty_local_inputs_render_and_complete(self):
        from stkcp.dashboard import SettlementDashboard
        from stkcp.replay import load_replay

        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / name for name in ("orders", "holdings", "prices")]
            for path in paths:
                path.write_text("", encoding="ascii")
            replay = load_replay(*paths)
        self.close()
        self.root = self.tk.Tk()
        self.root.withdraw()
        self.replay = replay
        self.dashboard = SettlementDashboard(self.root, replay, interval_ms=20)
        self.root.update()
        self.assertEqual(self.dashboard.order_tree.get_children(), ())
        self.assertEqual(self.dashboard.holding_tree.get_children(), ())
        self.finish()
        self.assertEqual(self.dashboard.counts_vars["processed"].get(), "0 / 0")
        self.assertEqual(self.dashboard.counts_vars["matched"].get(), "0")
        self.assertIn("Batch complete", self.dashboard.status_var.get())


if __name__ == "__main__":
    unittest.main()
