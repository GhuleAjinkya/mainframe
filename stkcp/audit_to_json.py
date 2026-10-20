"""Strict, atomic fixed-width audit to UTF-8 JSON Lines conversion."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from .contracts import (
    AUDIT_LENGTH, EXPLANATIONS, REASON_STATUS, UNKNOWN_EXPLANATION,
    digits, identifier, read_records, timestamp,
)
from .errors import AuditError


def parse_audit(raw, number=1):
    def fail(message):
        raise AuditError(f"audit record {number}: {message}")

    if len(raw) != AUDIT_LENGTH:
        fail(f"expected {AUDIT_LENGTH} characters, got {len(raw)}")
    if any(ord(char) > 127 or char in "\r\n" for char in raw):
        fail("expected an ASCII record without embedded line terminators")
    status, reason = raw[59:67].rstrip(), raw[67:74].rstrip()
    if status not in ("SETTLED", "PENDING", "REJECTED"):
        fail(f"invalid status {status!r}")
    if not reason or not identifier(raw[67:74]):
        fail("invalid reason code")
    if raw[59:67] != status.ljust(8) or raw[67:74] != reason.ljust(7):
        fail("noncanonical status/reason padding")
    if reason in REASON_STATUS and REASON_STATUS[reason] != status:
        fail("reason/status mismatch")
    for start, end, name in ((74, 84, "reference price"), (84, 94, "execution price"), (94, 110, "reference notional")):
        if not digits(raw[start:end]):
            fail(f"invalid {name}")
    quantity = int(raw[29:35]) if digits(raw[29:35]) else None
    requested = int(raw[35:45]) if digits(raw[35:45]) else None
    if reason != "DATA001":
        if not all(identifier(raw[a:b]) for a, b in ((0, 12), (12, 20), (20, 28))) or not quantity or not requested:
            fail("malformed order fields without DATA001")
        try:
            timestamp(raw[45:59])
        except ValueError:
            fail("invalid timestamp without DATA001")
        if reason != "SIDE001" and raw[28] not in ("B", "S"):
            # Duplicate detection precedes side validation.
            if reason != "DUP001":
                fail("invalid side without SIDE001 or DUP001")
    reference, execution, notional = int(raw[74:84]), int(raw[84:94]), int(raw[94:110])
    if notional != (quantity or 0) * reference:
        fail("reference notional does not equal quantity times reference")
    if reason in ("DATA001", "DUP001", "SIDE001") and reference:
        fail("reference present before reference validation")
    if status == "SETTLED":
        if not execution or not reference or (raw[28] == "B" and execution > requested) or (raw[28] == "S" and execution != requested):
            fail("invalid settled execution or reference price")
    elif execution:
        fail("unsettled order has an execution price")
    if reason in ("OK000", "PEND01", "HOLD01") and not reference:
        fail("validated order requires a reference price")
    if reason in ("OK000", "PEND01", "HOLD01") and not 90 * reference <= 100 * requested <= 110 * reference:
        fail("validated order limit is outside the reference band")
    return {
        "schema_version": 1,
        "order_id": raw[:12].rstrip(),
        "client_id": raw[12:20].rstrip(),
        "stock_code": raw[20:28].rstrip(),
        "side": raw[28].strip(),
        "quantity": quantity,
        "order_timestamp": raw[45:59].strip() or None,
        "requested_price_paise": requested,
        "status": status,
        "reason_code": reason,
        "explanation": EXPLANATIONS.get(reason, UNKNOWN_EXPLANATION),
        "reference_price_paise": reference or None,
        "execution_price_paise": execution or None,
        "reference_notional_paise": notional if reference else None,
        "raw_order": raw[:59],
    }


def convert(input_path, output_path, encoding="ascii"):
    source, destination = Path(input_path), Path(output_path)
    if source.resolve() == destination.resolve():
        raise AuditError("input and output paths must differ")
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=destination.parent, prefix=".audit-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            count = 0
            for count, raw in enumerate(read_records(source, encoding), 1):
                parsed = parse_audit(raw, count)
                stream.write(json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return count
    except (OSError, UnicodeError, LookupError) as error:
        raise AuditError(str(error)) from error
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--encoding", default="ascii", help="input encoding after explicit dataset export (default: ascii)")
    args = parser.parse_args(argv)
    try:
        count = convert(args.input, args.output, args.encoding)
    except AuditError as error:
        print(f"CONVERSION FAILED: {error}", file=sys.stderr)
        return 8
    print(f"Converted {count} audit records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
