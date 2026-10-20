"""Run an offline settlement demo without installing dependencies."""

import argparse
from pathlib import Path
import sys

from .errors import AuditError, InfrastructureError
from .pipeline import next_output, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the explicitly synthetic offline fixture")
    custom = sub.add_parser("run", help="run your own fixed-width input files")
    dashboard = sub.add_parser("dashboard", help="open the local graphical order and trade replay")
    dashboard.add_argument("--interval-ms", type=int, default=80, help="milliseconds between replay steps (default: 80)")
    dashboard.add_argument("--sample", action="store_true", help="replay the original 14-order acceptance sample instead of the 550-order dashboard demo")
    for name in ("orders", "holdings", "prices"):
        dashboard.add_argument(f"--{name}", type=Path)
    for command in (demo, custom):
        command.add_argument("--output", type=Path)
        command.add_argument("--engine", choices=("python", "cobol"), default="python")
        command.add_argument("--cobol-program", type=Path)
    for name in ("orders", "holdings", "prices"):
        custom.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.command == "dashboard":
        custom_paths = [getattr(args, name) for name in ("orders", "holdings", "prices")]
        if any(path is not None for path in custom_paths) and not all(path is not None for path in custom_paths):
            parser.error("dashboard custom inputs require --orders, --holdings, and --prices together")
        if args.sample and any(path is not None for path in custom_paths):
            parser.error("--sample cannot be combined with custom dashboard inputs")
        if args.interval_ms < 1:
            parser.error("--interval-ms must be a positive integer")
        fixture = root / "data" if args.sample else root / "data" / "dashboard-demo"
        sources = {
            name: getattr(args, name) or fixture / f"{name}.txt"
            for name in ("orders", "holdings", "prices")
        }
        try:
            from .dashboard import launch_dashboard

            return launch_dashboard(**sources, interval_ms=args.interval_ms)
        except (ImportError, RuntimeError, InfrastructureError) as error:
            print(f"DASHBOARD FAILED (RC12): {error}", file=sys.stderr)
            return 12
    if args.command == "demo":
        sources = {name: root / "data" / f"{name}.txt" for name in ("orders", "holdings", "prices")}
        print("Price source: checked-in SYNTHETIC fixture; historical-price import is available separately.")
    else:
        sources = {name: getattr(args, name) for name in ("orders", "holdings", "prices")}
    output = args.output or next_output(root / "build" / "runs")
    try:
        result, summary = run(**sources, output=output, engine=args.engine, cobol_program=args.cobol_program)
    except AuditError as error:
        print(f"DOWNSTREAM STEP FAILED (RC8): {error}", file=sys.stderr)
        return 8
    except InfrastructureError as error:
        print(f"BATCH FAILED (RC12): {error}", file=sys.stderr)
        return 12
    totals = summary["totals"]
    print(f"RC0 TOTAL={totals['total']} SETTLED={totals['settled']} PENDING={totals['pending']} REJECTED={totals['rejected']} BALANCE=PASS")
    print(f"Artifacts: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
