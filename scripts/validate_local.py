"""Run local tests and save an actual demo plus machine-readable observations."""

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stkcp.pipeline import next_output, run


def main():
    directory = next_output(ROOT / "build" / "validation")
    directory.mkdir(parents=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    (directory / "tests.txt").write_text(log.getvalue(), encoding="utf-8")
    print(log.getvalue(), end="")
    observations = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "tests_passed": result.wasSuccessful(),
        "native_cobol_compiled": False,
        "native_rexx_executed": False,
        "zos_submitted": False,
        "cobol_compiler_on_path": shutil.which("cobc") is not None,
        "data_kind": "synthetic_fixture",
    }
    if result.wasSuccessful():
        try:
            destination, summary = run(ROOT / "data/orders.txt", ROOT / "data/holdings.txt", ROOT / "data/prices.txt", directory / "demo")
            observations["demo"] = {"return_code": 0, "path": "demo", "totals": summary["totals"], "holdings_reconciled": summary["holdings_reconciled"]}
            print(f"Verified demo: {destination}")
        except Exception as error:
            observations["demo"] = {"return_code": 12, "error": str(error)}
    (directory / "validation-results.json").write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
    print(f"Validation evidence: {directory}")
    return 0 if result.wasSuccessful() and observations.get("demo", {}).get("return_code") == 0 else 12


if __name__ == "__main__":
    sys.exit(main())
