"""Success-gated local batch pipeline; publish only a complete new run directory."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .audit_to_json import convert
from .contracts import write_records
from .engine import process
from .errors import InfrastructureError
from .report import report
from .reconciliation import reconcile_holdings


def next_output(root):
    root = Path(root)
    index = 1
    while (root / f"run-{index:04d}").exists():
        index += 1
    return root / f"run-{index:04d}"


def run(orders, holdings, prices, output, engine="python", cobol_program=None):
    destination = Path(output).resolve()
    if destination.exists():
        raise InfrastructureError(f"output already exists; choose a new run directory: {destination}")
    paths = {name: Path(value).resolve() for name, value in (("orders", orders), ("holdings", holdings), ("prices", prices))}
    staging = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".stkcp-", dir=destination.parent))
        # Snapshot input bytes so the manifest and all steps use identical inputs.
        inputs = staging / "inputs"
        inputs.mkdir()
        manifest = {}
        for name, source in paths.items():
            copied = inputs / f"{name}.txt"
            shutil.copyfile(source, copied)
            manifest[name] = {"sha256": hashlib.sha256(copied.read_bytes()).hexdigest()}
            paths[name] = copied
        audit_path, settle_path, holdout_path = (staging / name for name in ("audit.dat", "settlement.dat", "holdings.dat"))
        if engine == "python":
            audit, holdout = process(paths["orders"], paths["holdings"], paths["prices"])
            write_records(audit_path, audit)
            write_records(settle_path, audit)
            write_records(holdout_path, holdout)
        elif engine == "cobol":
            if not cobol_program or not Path(cobol_program).is_file():
                raise InfrastructureError("--cobol-program must name an existing locally compiled executable")
            environment = dict(os.environ)
            for dd, path in (("ORDERS", paths["orders"]), ("HOLDINGS", paths["holdings"]), ("PRICES", paths["prices"]), ("AUDIT", audit_path), ("SETTLE", settle_path), ("HOLDOUT", holdout_path)):
                environment[f"DD_{dd}"] = str(path)
            result = subprocess.run([str(Path(cobol_program).resolve())], env=environment, capture_output=True, text=True, check=False)
            (staging / "cobol.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise InfrastructureError(f"COBOL step RC={result.returncode}: {(result.stdout + result.stderr).strip()}")
        else:
            raise InfrastructureError(f"unsupported engine {engine!r}")
        count = convert(audit_path, staging / "audit.jsonl")
        text, totals = report(audit_path, paths["orders"], settle_path)
        if count != totals["total"]:
            raise InfrastructureError("JSON/audit record count mismatch")
        (staging / "report.txt").write_text(text, encoding="utf-8")
        portfolio = reconcile_holdings(paths["holdings"], audit_path, holdout_path)
        summary = {"schema_version": 1, "engine": "python-reference" if engine == "python" else "compiled-local-cobol", "rexx_executed": False, "holdings_reconciled": True, "totals": totals, "inputs": manifest, "holdings": portfolio}
        (staging / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        # A rename on the same filesystem publishes all artifacts together.
        staging.rename(destination)
        staging = None
        return destination, summary
    except (OSError, UnicodeError) as error:
        raise InfrastructureError(str(error)) from error
    finally:
        if staging is not None:
            shutil.rmtree(staging)
