#!/usr/bin/env python3
"""Optionally compile and compare real local COBOL with the Python reference.

No compiler is installed or downloaded. An unavailable native compiler is RC12,
never a passing test. This script does not execute REXX or contact IBM services.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_cobol import build
from stkcp.contracts import order_record, write_records
from stkcp.engine import process
from stkcp.errors import AuditError, InfrastructureError
from stkcp.pipeline import run


def record_bytes(path: Path) -> list[bytes]:
    """Compare actual record bytes, allowing platform LF versus CRLF endings."""
    data = path.read_bytes()
    rows = data.split(b"\n")
    if rows[-1] == b"":
        rows.pop()
    return [row[:-1] if row.endswith(b"\r") else row for row in rows]


def holding(client="SELLER", symbol="ALPHA", quantity=20):
    return f"{client:<8}{symbol:<8}{quantity:010d}"


def price(symbol="ALPHA", time="20260102090000", value=10000):
    return f"{symbol:<8}{time}{value:010d}"


def order(name, client="BUYER", side="B", quantity=5, limit=10000,
          time="20260102100000", symbol="ALPHA"):
    return order_record(name, client, symbol, side, quantity, limit, time)


def native_case(program, directory, orders, holdings, prices, fatal=False,
                missing_orders=False):
    directory.mkdir()
    sources = {name: directory / f"{name}.txt" for name in ("orders", "holdings", "prices")}
    for name, values in (("orders", orders), ("holdings", holdings), ("prices", prices)):
        if name != "orders" or not missing_orders:
            write_records(sources[name], values)
    outputs = {dd: directory / name for dd, name in
               (("SETTLE", "settlement.dat"), ("AUDIT", "audit.dat"), ("HOLDOUT", "holdings.dat"))}
    environment = dict(os.environ)
    for name, path in sources.items():
        environment[f"DD_{name.upper()}"] = str(path)
    for name, path in outputs.items():
        environment[f"DD_{name}"] = str(path)
    result = subprocess.run([str(program)], env=environment, capture_output=True,
                            text=True, check=False, timeout=60)
    if fatal:
        try:
            process(sources["orders"], sources["holdings"], sources["prices"])
        except InfrastructureError:
            pass
        else:
            raise AssertionError(f"{directory.name}: Python did not classify case as fatal")
        if result.returncode != 12:
            raise AssertionError(f"{directory.name}: native RC {result.returncode}, expected 12\n"
                                 f"{result.stdout}{result.stderr}")
        if any(path.exists() for path in outputs.values()):
            raise AssertionError(f"{directory.name}: native fatal input opened output files")
    else:
        if result.returncode:
            raise AssertionError(f"{directory.name}: native RC {result.returncode}\n"
                                 f"{result.stdout}{result.stderr}")
        expected_audit, expected_holdings = process(
            sources["orders"], sources["holdings"], sources["prices"])
        for dd, expected in (("AUDIT", expected_audit), ("SETTLE", expected_audit),
                             ("HOLDOUT", expected_holdings)):
            actual = record_bytes(outputs[dd])
            wanted = [row.encode("ascii") for row in expected]
            if actual != wanted:
                first = next((index for index, pair in enumerate(zip(actual, wanted), 1)
                              if pair[0] != pair[1]), min(len(actual), len(wanted)) + 1)
                raise AssertionError(f"{directory.name}: {dd} differs at record {first}")
        if outputs["AUDIT"].read_bytes() != outputs["SETTLE"].read_bytes():
            raise AssertionError(f"{directory.name}: native AUDIT and SETTLE bytes differ")
    print(f"PASS native {directory.name}")


def validate(program: Path, temporary: Path) -> int:
    count = 0
    reference, _ = run(ROOT / "data/orders.txt", ROOT / "data/holdings.txt",
                       ROOT / "data/prices.txt", temporary / "python-fixture")
    native, _ = run(ROOT / "data/orders.txt", ROOT / "data/holdings.txt",
                    ROOT / "data/prices.txt", temporary / "native-fixture",
                    engine="cobol", cobol_program=program)
    for name in ("audit.dat", "settlement.dat", "holdings.dat"):
        if record_bytes(reference / name) != record_bytes(native / name):
            raise AssertionError(f"fixture: {name} differs from Python reference")
    print("PASS native fixture end-to-end pipeline")
    count += 1

    def case(name, rows, holdings=None, prices=None, **kwargs):
        nonlocal count
        native_case(program, temporary / name, rows,
                    [holding()] if holdings is None else holdings,
                    [price()] if prices is None else prices, **kwargs)
        count += 1

    good = order("DUP")
    case("malformed-and-priority", ["", "SHORT", good + "X",
         good[:29] + "00X005" + good[35:], good[:28] + "X" + good[29:], good,
         order("CAL")[:45] + "20260230090000", order("TIME")[:45] + "20260102240000"])
    case("sell-reservations", [order("S1", "SELLER", "S", 15),
         order("S2", "SELLER", "S", 6), order("B1", quantity=15)])
    case("rejected-sell-no-reservation", [order("S0", "SELLER", "S", 21),
         order("S1", "SELLER", "S", 20), order("B1", quantity=20)])
    case("first-compatible-single-use", [order("B1", limit=10500),
         order("B2", "BUYER2"), order("S1", "SELLER", "S", limit=9900)])
    case("purchases-cannot-fund-sells", [order("B1"),
         order("S1", "SELLER", "S"), order("S2", "BUYER", "S"),
         order("B2", "BUYER2")])
    case("no-self-trade-no-partial", [order("B1", "SELLER"),
         order("S1", "SELLER", "S"), order("B2", quantity=4),
         order("B3", limit=9500)])
    case("historical-boundaries", [order("EARLY", time="20260102085959"),
         order("STALE", time="20260109090001"),
         order("BOUNDARY", time="20260109090000"),
         order("LOW", limit=9000), order("HIGH", limit=11000),
         order("OUT", limit=11001)])
    case("empty-orders", [])
    case("empty-prices", [order("B1")], prices=[])
    case("ascii-symbol-sorting", [order("B1", symbol="1ST")],
         prices=[price("-SYM"), price("1ST"), price("A"), price("A0"), price("_LAST")])
    case("valid-leap-and-date-extremes", [order("MIN", time="16010101000000"),
         order("LEAP", time="20000229120000"), order("MAX", time="99991231235959")],
         prices=[price(time="16010101000000"), price(time="20000229115959"),
                 price(time="99991231235959")])
    case("missing-orders", [], fatal=True, missing_orders=True)
    case("malformed-holdings", [], holdings=["broken"], fatal=True)
    case("duplicate-holdings", [], holdings=[holding(), holding()], fatal=True)
    case("malformed-prices", [], prices=[price()[:-1]], fatal=True)
    case("zero-price", [], prices=[price(value=0)], fatal=True)
    case("invalid-price-calendar", [], prices=[price(time="20260229090000")], fatal=True)
    case("duplicate-prices", [], prices=[price(), price()], fatal=True)
    case("unsorted-prices", [], prices=[price(), price(time="20260101090000")], fatal=True)
    case("orders-overflow", [order(f"O{i}") for i in range(1001)], fatal=True)
    case("holdings-overflow", [], holdings=[holding(f"C{i}") for i in range(1001)], fatal=True)
    case("new-buyer-overflow", [order("B1")],
         holdings=[holding(f"C{i}") for i in range(1000)], fatal=True)
    case("prices-overflow", [],
         prices=[price(f"S{i:07}") for i in range(5001)], fatal=True)
    case("holdings-arithmetic-overflow", [order("B1"), order("S1", "SELLER", "S")],
         holdings=[holding("BUYER", quantity=9999999999), holding()], fatal=True)
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="cobc", help="Already installed GnuCOBOL compiler")
    parser.add_argument("--cobol-program", type=Path, help="Validate an existing executable instead of compiling")
    args = parser.parse_args(argv)
    compiler = None if args.cobol_program else shutil.which(args.compiler)
    if not args.cobol_program and compiler is None:
        print("UNAVAILABLE: no local GnuCOBOL compiler; native COBOL validation was not run.",
              file=sys.stderr)
        return 12
    try:
        with tempfile.TemporaryDirectory(prefix="stkcp-native-") as temporary_name:
            temporary = Path(temporary_name)
            program = args.cobol_program.resolve() if args.cobol_program else temporary / (
                "settle.exe" if sys.platform == "win32" else "settle")
            if not args.cobol_program and build(compiler, program):
                return 12
            if not program.is_file():
                raise OSError(f"COBOL executable does not exist: {program}")
            count = validate(program, temporary)
        print(f"PASS {count} native COBOL comparisons and fatal cases; REXX/z/OS remain unverified.")
        return 0
    except (OSError, AssertionError, AuditError, InfrastructureError,
            subprocess.TimeoutExpired) as exc:
        print(f"Native COBOL validation failed: {exc}", file=sys.stderr)
        return 12


if __name__ == "__main__":
    raise SystemExit(main())
