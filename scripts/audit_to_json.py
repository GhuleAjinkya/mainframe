"""USS/local entrypoint; deploy the sibling stkcp package with this script."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stkcp.audit_to_json import main

if __name__ == "__main__":
    sys.exit(main())
