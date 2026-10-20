"""Offline historical CSV adapters and deterministic fixed-width snapshots.

This module deliberately has no HTTP client, credentials, or download operation.
An operator supplies a previously exported, licensed CSV file. No price is
invented and an import failure never selects the synthetic demonstration data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext


PRICE_WIDTH = 32
MAX_PRICES = 5000
MAX_PRICE = 9_999_999_999
SYMBOL_PATTERN = re.compile(r"[A-Z0-9_-]{1,8}\Z", re.ASCII)


class MarketDataError(ValueError):
    """An import cannot be safely used as a reference-price snapshot."""


@dataclass(frozen=True, order=True)
class Price:
    stock_code: str
    timestamp: datetime
    paise: int

    def fixed_record(self) -> str:
        return (f"{self.stock_code:<8}" + self.timestamp.strftime("%Y%m%d%H%M%S")
                + f"{self.paise:010d}")


def parse_utc_timestamp(value: str) -> datetime:
    """Parse the contract's exact UTC14 representation, including real dates."""
    if not re.fullmatch(r"[0-9]{14}", value, re.ASCII):
        raise MarketDataError("timestamp must contain exactly 14 ASCII digits")
    try:
        result = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise MarketDataError(f"invalid UTC timestamp: {value}") from exc
    if result.year < 1601:
        raise MarketDataError("timestamps before 1601 are unsupported")
    return result


def _symbol(value: str) -> str:
    if not SYMBOL_PATTERN.fullmatch(value):
        raise MarketDataError("stock code must be 1–8 uppercase ASCII letters, digits, _ or -")
    return value


def _date(value: str, label: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value, re.ASCII):
        raise MarketDataError(f"{label} must use YYYY-MM-DD")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise MarketDataError(f"invalid {label}: {value}") from exc
    if result.year < 1601:
        raise MarketDataError(f"{label} must be in year 1601 or later")
    return result


def decimal_paise(value: str, label: str = "price") -> int:
    """Reject missing, nonfinite, nonpositive and fractional-paise prices."""
    if not value or value.strip() != value or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value, re.ASCII):
        raise MarketDataError(f"{label}: missing or invalid decimal price")
    try:
        # Do not let Decimal's default 28-digit context hide tiny fractions.
        with localcontext() as context:
            context.prec = max(28, len(value) + 3)
            paise = Decimal(value) * 100
    except InvalidOperation as exc:
        raise MarketDataError(f"{label}: invalid decimal price") from exc
    if not paise.is_finite() or paise <= 0 or paise > MAX_PRICE:
        raise MarketDataError(f"{label}: price must be positive and fit ten paise digits")
    if paise != paise.to_integral_value():
        raise MarketDataError(f"{label}: fractional paise cannot be represented without rounding")
    return int(paise)


def validate_prices(prices: list[Price], *, as_of: datetime,
                    max_age_days: int = 7) -> list[Price]:
    """Validate then sort a replay; no future or stale final quote is accepted."""
    if as_of.tzinfo is None or as_of.utcoffset() != timedelta(0):
        raise MarketDataError("as_of must be timezone-aware UTC")
    if not 0 <= max_age_days <= 7:
        raise MarketDataError("max_age_days must be between zero and seven")
    if not prices:
        raise MarketDataError("source contains no price records")
    if len(prices) > MAX_PRICES:
        raise MarketDataError(f"snapshot exceeds {MAX_PRICES} prices")
    seen = set()
    latest = {}
    for price in prices:
        _symbol(price.stock_code)
        if (price.timestamp.tzinfo is None or price.timestamp.utcoffset() != timedelta(0)
                or price.timestamp.year < 1601 or price.timestamp.microsecond):
            raise MarketDataError("price timestamps must be UTC, whole-second values from 1601 onward")
        if isinstance(price.paise, bool) or not isinstance(price.paise, int) or not 0 < price.paise <= MAX_PRICE:
            raise MarketDataError("price must be an integer within ten positive paise digits")
        key = (price.stock_code, price.timestamp)
        if key in seen:
            raise MarketDataError(f"duplicate symbol/timestamp: {price.stock_code} {price.timestamp.isoformat()}")
        seen.add(key)
        if price.timestamp > as_of:
            raise MarketDataError(f"future price exceeds replay cutoff: {price.stock_code} {price.timestamp.isoformat()}")
        latest[price.stock_code] = max(latest.get(price.stock_code, price.timestamp), price.timestamp)
    for symbol, stamp in latest.items():
        if as_of - stamp > timedelta(days=max_age_days):
            raise MarketDataError(f"stale final reference for {symbol}; exceeds {max_age_days} days")
    return sorted(prices)


class YahooExportCsvAdapter:
    """Read the Date/Open/High/Low/Close schema of an existing local export.

    This adapter does not fetch Yahoo data or imply permission to redistribute
    it. An absent symbol column is recorded as operator-supplied provenance.
    The same documented schema can be supplied by another named provider.
    """

    required_columns = {"Date", "Open", "High", "Low", "Close"}

    def read(self, source: bytes, *, symbol: str, provider_symbol: str,
             start_date: date, end_date: date, session_close_utc: time,
             as_of: datetime) -> tuple[list[Price], dict]:
        _symbol(symbol)
        if not provider_symbol or provider_symbol.strip() != provider_symbol:
            raise MarketDataError("provider_symbol must be explicit and nonempty")
        if start_date > end_date:
            raise MarketDataError("start date is after end date")
        try:
            decoded = source.decode("utf-8-sig")
        except UnicodeError as exc:
            raise MarketDataError("source CSV must be UTF-8") from exc
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise MarketDataError("duplicate CSV column names")
        if not self.required_columns.issubset(columns):
            raise MarketDataError("CSV requires Date, Open, High, Low and Close columns")
        records = []
        for number, row in enumerate(reader, 2):
            if None in row or any(row.get(column) is None for column in columns):
                raise MarketDataError(f"CSV row {number}: field count differs from header")
            try:
                if "Symbol" in row and row["Symbol"] != provider_symbol:
                    raise MarketDataError("symbol does not match explicit provider symbol")
                if "Currency" in row and row["Currency"] != "INR":
                    raise MarketDataError("currency must be INR; currency conversion is not implemented")
                day = _date(row["Date"], "Date")
                if not start_date <= day <= end_date:
                    raise MarketDataError("date outside the explicitly requested inclusive range")
                fields = {name: decimal_paise(row[name], name) for name in ("Open", "High", "Low", "Close")}
                if (fields["Low"] > min(fields["Open"], fields["Close"])
                        or fields["High"] < max(fields["Open"], fields["Close"])
                        or fields["Low"] > fields["High"]):
                    raise MarketDataError("OHLC prices are inconsistent")
                if "Volume" in row and not re.fullmatch(r"[0-9]+", row["Volume"], re.ASCII):
                    raise MarketDataError("Volume must be a nonnegative integer")
                timestamp = datetime.combine(day, session_close_utc, timezone.utc)
                records.append(Price(symbol, timestamp, fields["Close"]))
            except MarketDataError as exc:
                raise MarketDataError(f"CSV row {number}: {exc}") from exc
        result = validate_prices(records, as_of=as_of)
        return result, {
            "source_columns": columns,
            "symbol_verification": ("explicit provider symbol checked against Symbol column"
                                    if "Symbol" in columns else
                                    "operator supplied; CSV has no Symbol column"),
            "adjustment_policy": "unadjusted Close only; Adj Close is ignored if present",
        }


def import_csv_snapshot(source_path: Path, output_dir: Path, *, symbol: str,
                        provider_symbol: str, provider: str, data_kind: str, retrieved_at: datetime,
                        start_date: date, end_date: date, session_close_utc: time,
                        market_session: str, as_of: datetime) -> dict:
    """Publish a complete new directory atomically; existing outputs are refused."""
    source_path, output_dir = Path(source_path), Path(output_dir)
    if not provider.strip() or not market_session.strip():
        raise MarketDataError("provider and market_session descriptions are required")
    if data_kind not in {"synthetic", "historical_export"}:
        raise MarketDataError("data_kind must explicitly be synthetic or historical_export")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != timedelta(0):
        raise MarketDataError("retrieved_at must be timezone-aware UTC")
    if retrieved_at > datetime.now(timezone.utc):
        raise MarketDataError("retrieval time cannot be in the future")
    if output_dir.exists():
        raise MarketDataError(f"output directory already exists: {output_dir}")
    source = source_path.read_bytes()
    prices, details = YahooExportCsvAdapter().read(
        source, symbol=symbol, provider_symbol=provider_symbol,
        start_date=start_date, end_date=end_date,
        session_close_utc=session_close_utc, as_of=as_of)
    if any(price.timestamp > retrieved_at for price in prices):
        raise MarketDataError("source observation is later than its declared retrieval time")
    replay = "".join(price.fixed_record() + "\n" for price in prices).encode("ascii")
    metadata = {
        "schema_version": 1,
        "dataset_kind": ("synthetic_fixture" if data_kind == "synthetic"
                         else "operator_supplied_historical_export"),
        "contains_real_market_data": False if data_kind == "synthetic" else None,
        "real_data_provenance_verified_by_software": False,
        "source_provider": provider,
        "source_filename": source_path.name,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "retrieved_at_utc": retrieved_at.isoformat().replace("+00:00", "Z"),
        "stock_code": symbol,
        "provider_symbol": provider_symbol,
        "currency": "INR",
        "money_unit": "paise",
        "market_session": market_session,
        "session_close_utc": session_close_utc.strftime("%H:%M:%S"),
        "source_date_interpretation": "Date is combined with operator-specified UTC session close",
        "replay_cutoff_utc": as_of.isoformat().replace("+00:00", "Z"),
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "first_timestamp_utc": prices[0].timestamp.isoformat().replace("+00:00", "Z"),
        "last_timestamp_utc": prices[-1].timestamp.isoformat().replace("+00:00", "Z"),
        "record_count": len(prices),
        "prices_sha256": hashlib.sha256(replay).hexdigest(),
        **details,
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.import-", dir=output_dir.parent))
    try:
        (stage / "prices.txt").write_bytes(replay)
        (stage / "source.csv").write_bytes(source)
        (stage / "market-data-metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # All validation and writes succeed before a usable directory appears.
        os.rename(stage, output_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a local INR historical CSV export; never accesses a network.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path, help="new directory; existing directories are refused")
    parser.add_argument("--symbol", required=True, help="explicit 1–8 character internal stock code")
    parser.add_argument("--provider-symbol", required=True, help="symbol identified in the original export")
    parser.add_argument("--provider", required=True, help="operator-declared source/provider")
    parser.add_argument("--data-kind", required=True, choices=["synthetic", "historical_export"],
                        help="explicit provenance declaration; software cannot authenticate a historical export")
    parser.add_argument("--currency", required=True, choices=["INR"])
    parser.add_argument("--retrieved-at", required=True, help="actual export retrieval time as UTC14")
    parser.add_argument("--start-date", required=True, help="inclusive YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="inclusive YYYY-MM-DD")
    parser.add_argument("--session-close-utc", required=True, help="explicit UTC close HHMMSS for Date-only rows")
    parser.add_argument("--market-session", required=True, help="session/exchange/time interpretation and applicable calendar limitations")
    parser.add_argument("--as-of", required=True, help="simulated replay cutoff as UTC14; latest quote must be <=7 days old")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9]{6}", args.session_close_utc, re.ASCII):
            raise MarketDataError("session-close-utc must be HHMMSS")
        try:
            close = datetime.strptime(args.session_close_utc, "%H%M%S").time()
        except ValueError as exc:
            raise MarketDataError("invalid session close time") from exc
        metadata = import_csv_snapshot(
            args.input, args.output_dir, symbol=args.symbol,
            provider_symbol=args.provider_symbol, provider=args.provider,
            data_kind=args.data_kind,
            retrieved_at=parse_utc_timestamp(args.retrieved_at),
            start_date=_date(args.start_date, "start-date"),
            end_date=_date(args.end_date, "end-date"),
            session_close_utc=close, market_session=args.market_session,
            as_of=parse_utc_timestamp(args.as_of))
    except (MarketDataError, OSError, csv.Error) as exc:
        print(f"Market-data import failed: {exc}", file=sys.stderr)
        return 12
    print(f"Imported {metadata['record_count']} local historical prices to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
