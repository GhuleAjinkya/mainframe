"""Behavioral tests for offline import validation and atomic publication."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from stkcp.market_data import (MarketDataError, Price, YahooExportCsvAdapter,
                               decimal_paise, import_csv_snapshot,
                               parse_utc_timestamp, validate_prices)


CSV_HEADER = "Date,Open,High,Low,Close,Volume,Symbol,Currency\n"
ROW = "2026-01-02,100.00,103.00,99.00,102.00,1200,ALPHA,INR\n"
CUTOFF = parse_utc_timestamp("20260102100000")


class OfflineAdapterTests(unittest.TestCase):
    def read(self, source, **overrides):
        options = dict(symbol="ALPHA", provider_symbol="ALPHA",
                       start_date=date(2026, 1, 1), end_date=date(2026, 1, 2),
                       session_close_utc=time(9), as_of=CUTOFF)
        options.update(overrides)
        return YahooExportCsvAdapter().read(source.encode("utf-8"), **options)

    def test_exact_money_without_rounding(self):
        self.assertEqual(decimal_paise("102.00"), 10200)
        self.assertEqual(decimal_paise("0.01"), 1)
        self.assertEqual(decimal_paise("99999999.99"), 9999999999)
        self.assertEqual(decimal_paise("1.23000"), 123)
        for value in ("", "null", "NaN", "Infinity", "0", "-1", "1.001", "1e2", " 1.00", "100000000", "100.00000000000000000000000001"):
            with self.subTest(value=value), self.assertRaises(MarketDataError):
                decimal_paise(value)

    def test_read_close_and_explicit_session_timestamp(self):
        records, metadata = self.read(CSV_HEADER + ROW)
        self.assertEqual(records, [Price("ALPHA", parse_utc_timestamp("20260102090000"), 10200)])
        self.assertEqual(records[0].fixed_record(), "ALPHA   202601020900000000010200")
        self.assertEqual(len(records[0].fixed_record()), 32)
        self.assertIn("checked", metadata["symbol_verification"])

    def test_sorted_deterministically_instead_of_preserving_export_order(self):
        earlier = ROW.replace("2026-01-02", "2026-01-01")
        prices, _ = self.read(CSV_HEADER + ROW + earlier)
        self.assertLess(prices[0].timestamp, prices[1].timestamp)

    def test_metadata_admits_missing_symbol_column(self):
        _, metadata = self.read("Date,Open,High,Low,Close\n2026-01-02,100,103,99,102\n")
        self.assertIn("operator supplied", metadata["symbol_verification"])

    def test_duplicate_missing_and_invalid_csv_fail(self):
        invalid = {
            "empty": CSV_HEADER,
            "duplicate": CSV_HEADER + ROW + ROW,
            "symbol": CSV_HEADER + ROW.replace("ALPHA", "OTHER"),
            "currency": CSV_HEADER + ROW.replace("INR", "USD"),
            "missing_close": CSV_HEADER + ROW.replace("102.00", ""),
            "fractional_ohlc": CSV_HEADER + ROW.replace("100.00", "100.001"),
            "ohlc_bounds": CSV_HEADER + ROW.replace("103.00", "101.00"),
            "negative_volume": CSV_HEADER + ROW.replace("1200", "-1"),
            "missing_columns": "Date,Close\n2026-01-02,102.00\n",
            "short_row": CSV_HEADER + "2026-01-02,100.00\n",
            "extra_column": CSV_HEADER + ROW.rstrip() + ",extra\n",
            "duplicate_columns": "Date,Open,High,Low,Close,Close\n2026-01-02,100,103,99,102,102\n",
            "bad_date": CSV_HEADER + ROW.replace("2026-01-02", "2026-02-30"),
            "out_of_range": CSV_HEADER + ROW.replace("2026-01-02", "2025-12-31"),
        }
        for case, source in invalid.items():
            with self.subTest(case=case), self.assertRaises(MarketDataError):
                self.read(source)

    def test_future_and_stale_quotes_fail(self):
        with self.assertRaisesRegex(MarketDataError, "future"):
            self.read(CSV_HEADER + ROW, as_of=parse_utc_timestamp("20260102080000"))
        with self.assertRaisesRegex(MarketDataError, "stale"):
            self.read(CSV_HEADER + ROW, as_of=parse_utc_timestamp("20260110090001"))
        # Exactly seven days is allowed, consistent with settlement lookup.
        self.read(CSV_HEADER + ROW, as_of=parse_utc_timestamp("20260109090000"))

    def test_snapshot_limits_and_utc_validation(self):
        quote = Price("ALPHA", parse_utc_timestamp("20260102090000"), 10200)
        with self.assertRaisesRegex(MarketDataError, "5000"):
            validate_prices([quote] * 5001, as_of=CUTOFF)
        with self.assertRaisesRegex(MarketDataError, "UTC"):
            validate_prices([quote], as_of=CUTOFF.replace(tzinfo=None))
        with self.assertRaisesRegex(MarketDataError, "duplicate"):
            validate_prices([quote, quote], as_of=CUTOFF)
        for stamp in ("20260230090000", "2026010209000", "16000101090000", "２０２６0102090000"):
            with self.subTest(stamp=stamp), self.assertRaises(MarketDataError):
                parse_utc_timestamp(stamp)


class AtomicImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "local.csv"
        self.source.write_text(CSV_HEADER + ROW, encoding="utf-8")
        self.destination = self.directory / "snapshot"

    def run_import(self, **overrides):
        options = dict(symbol="ALPHA", provider_symbol="ALPHA",
                       provider="Synthetic unit-test input", data_kind="synthetic",
                       retrieved_at=parse_utc_timestamp("20260103000000"),
                       start_date=date(2026, 1, 1), end_date=date(2026, 1, 2),
                       session_close_utc=time(9), market_session="Synthetic session", as_of=CUTOFF)
        options.update(overrides)
        return import_csv_snapshot(self.source, self.destination, **options)

    def test_complete_directory_contains_provenance_and_unchanged_source(self):
        metadata = self.run_import()
        self.assertEqual(set(path.name for path in self.destination.iterdir()),
                         {"prices.txt", "source.csv", "market-data-metadata.json"})
        self.assertEqual((self.destination / "source.csv").read_bytes(), self.source.read_bytes())
        published = (self.destination / "prices.txt").read_bytes()
        self.assertEqual(metadata["prices_sha256"], hashlib.sha256(published).hexdigest())
        self.assertEqual(metadata["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.destination / "market-data-metadata.json").read_text()), metadata)
        self.assertEqual(metadata["dataset_kind"], "synthetic_fixture")
        self.assertFalse(metadata["contains_real_market_data"])
        self.assertFalse(metadata["real_data_provenance_verified_by_software"])

    def test_validation_failure_publishes_nothing_and_never_uses_fallback(self):
        self.source.write_text(CSV_HEADER + ROW.replace("102.00", "NaN"), encoding="utf-8")
        with self.assertRaises(MarketDataError):
            self.run_import()
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.directory.iterdir()), [self.source])

    def test_existing_output_is_preserved(self):
        self.destination.mkdir()
        marker = self.destination / "keep.txt"
        marker.write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(MarketDataError, "already exists"):
            self.run_import()
        self.assertEqual(marker.read_text(), "original")

    def test_future_retrieval_is_rejected(self):
        with self.assertRaisesRegex(MarketDataError, "retrieval time"):
            self.run_import(retrieved_at=datetime.now(timezone.utc) + timedelta(days=1))
        self.assertFalse(self.destination.exists())

    def test_price_cannot_postdate_declared_retrieval(self):
        with self.assertRaisesRegex(MarketDataError, "later than.*retrieval"):
            self.run_import(retrieved_at=parse_utc_timestamp("20260102080000"))
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
