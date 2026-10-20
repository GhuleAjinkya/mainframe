import json
from pathlib import Path
import tempfile
import unittest

from stkcp.audit_to_json import parse_audit
from stkcp.contracts import order_record, write_records
from stkcp.engine import process
from stkcp.errors import InfrastructureError
from stkcp.replay import load_replay


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = tuple(ROOT / "data" / name for name in ("orders.txt", "holdings.txt", "prices.txt"))


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = tuple(self.root / name for name in ("orders", "holdings", "prices"))
        write_records(self.paths[1], [f"{'SELLER':<8}{'ALPHA':<8}{20:010d}"])
        write_records(self.paths[2], [f"{'ALPHA':<8}20260102090000{10000:010d}"])

    def order(self, name, client="BUYER", side="B", quantity=5, price=10000, time="20260102100000"):
        return order_record(name, client, "ALPHA", side, quantity, price, time)

    def replay(self, records):
        write_records(self.paths[0], records)
        return load_replay(*self.paths)

    def test_fixture_final_state_matches_actual_engine_audit_and_holdings(self):
        replay = load_replay(*FIXTURE)
        actual_audit, actual_holdout = process(*FIXTURE)
        self.assertEqual(replay.audit, tuple(actual_audit))
        self.assertEqual(replay.holdout, tuple(actual_holdout))
        final = replay.state(len(replay) - 1)
        self.assertEqual(final["counts"], {"total": 14, "queued": 0, "awaiting": 0,
                                         "settled": 4, "pending": 2, "rejected": 8, "processed": 14})
        self.assertEqual(final["executed_pairs"], 2)
        self.assertEqual(final["executed_notional_paise"], 10 * 10100 + 5 * 20300)
        self.assertEqual(len(replay), 18)
        for row, raw in zip(final["orders"], actual_audit):
            audit = parse_audit(raw)
            for field in ("order_id", "status", "reason_code", "reference_price_paise", "execution_price_paise"):
                self.assertEqual(row[field], audit[field])
        for holding, raw in zip(final["holdings"], actual_holdout):
            self.assertEqual(holding["quantity"], int(raw[16:26]))
            self.assertEqual(holding["reference_price_paise"] or 0, int(raw[26:36]))

    def test_validation_precedes_matching_and_pair_settlement_is_atomic(self):
        replay = self.replay([self.order("B1", price=10500),
                              self.order("S1", "SELLER", "S", price=9900)])
        self.assertEqual([state["phase"] for state in replay.events],
                         ["initial", "validation", "validation", "settlement", "complete"])
        initial, first, validated, settled, final = replay.events
        self.assertEqual([row["status"] for row in first["orders"]], ["AWAITING", "QUEUED"])
        self.assertEqual(validated["counts"]["pending"], 0)
        self.assertEqual(validated["counts"]["awaiting"], 2)
        self.assertEqual(validated["holdings"][0]["quantity"], 20)
        self.assertEqual(validated["holdings"][0]["reserved"], 5)
        self.assertEqual(validated["holdings"][0]["available"], 15)
        self.assertEqual(settled["active_rows"], (1, 2))
        self.assertEqual([row["status"] for row in settled["orders"]], ["SETTLED", "SETTLED"])
        self.assertEqual([holding["quantity"] for holding in settled["holdings"]], [15, 5])
        self.assertEqual(settled["holdings"][0]["reserved"], 0)
        self.assertEqual(settled["executed_notional_paise"], 49500)
        self.assertEqual(len(settled["price_series"]["ALPHA"]["executions"]), 1)
        self.assertIsNone(initial["valuation_paise"])

    def test_pending_reserved_and_rejected_sell_does_not_reserve(self):
        replay = self.replay([self.order("S1", "SELLER", "S", quantity=15),
                              self.order("S2", "SELLER", "S", quantity=6)])
        final = replay.events[-1]
        self.assertEqual([row["status"] for row in final["orders"]], ["PENDING", "REJECTED"])
        self.assertEqual(final["holdings"][0]["quantity"], 20)
        self.assertEqual(replay.events[-2]["holdings"][0]["reserved"], 15)
        self.assertEqual(replay.events[-2]["holdings"][0]["available"], 5)
        self.assertEqual(final["holdings"][0]["reserved"], 0)
        self.assertEqual(final["holdings"][0]["available"], 20)
        self.assertEqual(final["executed_pairs"], 0)

    def test_quotes_follow_current_order_time_without_looking_ahead(self):
        write_records(self.paths[2], [f"{'ALPHA':<8}20260102090000{10000:010d}",
                                      f"{'ALPHA':<8}20260102110000{20000:010d}"])
        replay = self.replay([self.order("LATE", time="20260102110000", price=20000),
                              self.order("EARLY", time="20260102100000"),
                              self.order("BEFORE", time="20260102085959"),
                              self.order("STALE", time="20260110090000")])
        self.assertEqual([state["quotes"]["ALPHA"] for state in replay.events[1:5]],
                         [20000, 10000, None, None])
        self.assertEqual(replay.events[2]["as_of"], "2026-01-02T10:00:00")
        self.assertEqual(replay.events[2]["valuation_paise"], 200000)
        self.assertIsNone(replay.events[3]["valuation_paise"])
        self.assertEqual(replay.events[3]["known_valuation_paise"], 0)
        self.assertFalse(replay.events[3]["valuation_series"][-1]["complete"])
        self.assertEqual([point["price_paise"] for point in replay.events[-1]["price_series"]["ALPHA"]["reference"]],
                         [20000, 10000])

    def test_snapshots_are_deeply_immutable_and_prior_steps_unchanged(self):
        replay = self.replay([self.order("B1"), self.order("S1", "SELLER", "S")])
        first = replay.events[1]
        with self.assertRaises(TypeError):
            first["orders"][0]["status"] = "SETTLED"
        with self.assertRaises(TypeError):
            first["counts"]["settled"] = 100
        with self.assertRaises(TypeError):
            first["price_series"]["ALPHA"]["orders"][0]["price_paise"] = 1
        self.assertEqual(first["orders"][0]["status"], "AWAITING")
        self.assertEqual(first["counts"]["settled"], 0)
        self.assertEqual(len(first["price_series"]["ALPHA"]["orders"]), 1)
        with self.assertRaises(IndexError):
            replay.state(-1)

    def test_duplicate_order_ids_still_have_distinct_row_identity(self):
        replay = self.replay([self.order("SAME"), self.order("SAME")])
        self.assertEqual([row["row"] for row in replay.events[-1]["orders"]], [1, 2])
        self.assertEqual(replay.events[2]["active_rows"], (2,))
        self.assertEqual(replay.events[-1]["orders"][1]["reason_code"], "DUP001")

    def test_engine_callback_is_detached_and_preserves_return_values(self):
        write_records(self.paths[0], [self.order("B1"), self.order("S1", "SELLER", "S")])
        expected = process(*self.paths)
        captured = []

        def capture(event):
            json.dumps(event)  # Engine callback payloads also support JSON export.
            captured.append(event)
            for order in event["orders"]:
                order["reason"] = "MUTATED"
            for holding in event["holdings"]:
                holding["final"] = -1

        self.assertEqual(process(*self.paths, event_callback=capture), expected)
        self.assertEqual([event["phase"] for event in captured],
                         ["initial", "validation", "validation", "settlement", "complete"])

    def test_empty_and_malformed_records_remain_visible_and_missing_input_fails(self):
        replay = self.replay(["", "SHORT"])
        self.assertEqual([row["status"] for row in replay.events[-1]["orders"]], ["REJECTED", "REJECTED"])
        empty = self.replay([])
        self.assertEqual([event["phase"] for event in empty.events], ["initial", "complete"])
        self.assertEqual(empty.events[-1]["counts"]["total"], 0)
        self.assertIn("ALPHA", empty.symbols)
        with self.assertRaises(InfrastructureError):
            load_replay(self.root / "missing", self.paths[1], self.paths[2])

    def test_malformed_only_orders_do_not_establish_a_valuation_clock(self):
        valid = self.order("BADNUM")
        malformed = valid[:29] + "00X001" + valid[35:]
        replay = self.replay([malformed])
        final = replay.events[-1]
        self.assertEqual(final["orders"][0]["reason_code"], "DATA001")
        self.assertIsNone(final["as_of"])
        self.assertIsNone(final["quotes"]["ALPHA"])
        self.assertIsNone(final["holdings"][0]["reference_price_paise"])
        self.assertIsNone(final["valuation_paise"])
        self.assertEqual(int(replay.holdout[0][26:36]), 0)

    def test_malformed_order_does_not_plot_a_reference_at_its_raw_time(self):
        write_records(self.paths[2], [f"{'ALPHA':<8}20260102090000{10000:010d}",
                                      f"{'ALPHA':<8}20260102110000{20000:010d}"])
        malformed = self.order("BADNUM")
        malformed = malformed[:29] + "00X001" + malformed[35:]
        replay = self.replay([self.order("VALID", time="20260102110000", price=20000), malformed])
        self.assertIsNone(replay.events[2]["orders"][1]["reference_price_paise"])
        points = replay.events[2]["price_series"]["ALPHA"]["reference"]
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["time"], "2026-01-02T11:00:00")


if __name__ == "__main__":
    unittest.main()
