#!/usr/bin/env python3
"""Build the optional native local COBOL engine with an existing GnuCOBOL.

This helper never installs a compiler or makes a network request. Enterprise
COBOL uses the unmodified source without LOCAL; see the z/OS templates.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def build(compiler: str, output: Path) -> int:
    """Publish an executable only after a real, successful compilation."""
    root = Path(__file__).resolve().parents[1]
    output = output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cobol-build-", dir=output.parent) as temporary:
            staged = Path(temporary) / output.name
            result = subprocess.run(
                [compiler, "-x", "-free", "-Wall", "-DLOCAL=1", "-o", str(staged),
                 str(root / "src" / "cobol" / "SETTLE.cbl")],
                cwd=root, check=False,
            )
            if result.returncode or not staged.is_file():
                print("Native COBOL compilation failed; no successful build is claimed.",
                      file=sys.stderr)
                return 12
            os.replace(staged, output)
    except OSError as exc:
        print(f"Native COBOL build failed: {exc}", file=sys.stderr)
        return 12
    print(f"Compiled native COBOL executable: {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="cobc", help="Existing cobc executable")
    parser.add_argument(
        "--output", type=Path,
        default=root / "build" / ("settle.exe" if sys.platform == "win32" else "settle"),
        help="Output executable (default: build/settle[.exe])",
    )
    args = parser.parse_args(argv)
    compiler = shutil.which(args.compiler)
    if compiler is None:
        print(
            f"GnuCOBOL compiler not found: {args.compiler}. "
            "Native COBOL was not compiled. The local Python reference engine "
            "is available without a COBOL compiler.", file=sys.stderr,
        )
        return 12
    return build(compiler, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
