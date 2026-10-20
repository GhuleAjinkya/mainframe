"""Local equivalent of the dataset-based REXX report, with real count checks."""

from collections import Counter

from .audit_to_json import parse_audit
from .contracts import EXPLANATIONS, MAX_ORDERS, read_records
from .errors import AuditError


def report(audit_path, orders_path, settlement_path):
    try:
        raw_audit = list(read_records(audit_path))
        raw_settlement = list(read_records(settlement_path))
        raw_orders = list(read_records(orders_path))
        input_count = len(raw_orders)
        if max(len(raw_audit), len(raw_settlement), input_count) > MAX_ORDERS:
            raise AuditError("report input exceeds supported 1000-record batch")
        records = [parse_audit(raw, index) for index, raw in enumerate(raw_audit, 1)]
    except (OSError, UnicodeError) as error:
        raise AuditError(str(error)) from error
    counts = Counter(record["status"] for record in records)
    lines = ["STKCP EXPLAINABLE RECONCILIATION", "Local Python report (REXX equivalent; REXX has not been executed)."]
    for index, record in enumerate(records, 1):
        if record["status"] != "SETTLED" or record["reason_code"] not in EXPLANATIONS:
            lines.append(f"{index:04d} {record['order_id'] or '(blank)'} {record['status']} {record['reason_code']}: {record['explanation']}")
    totals = {"total": len(records), "settled": counts["SETTLED"], "pending": counts["PENDING"], "rejected": counts["REJECTED"], "input": input_count, "settlement": len(raw_settlement)}
    lines.append(f"TOTAL={totals['total']} SETTLED={totals['settled']} PENDING={totals['pending']} REJECTED={totals['rejected']}")
    lines.append(f"INPUT={input_count} AUDIT={len(records)} SETTLEMENT={len(raw_settlement)}")
    trace_matches = len(raw_orders) == len(raw_audit) and all(raw[:59] == original[:59].ljust(59) for raw, original in zip(raw_audit, raw_orders))
    balanced = input_count == len(records) == len(raw_settlement) and raw_audit == raw_settlement and trace_matches
    known = all(record["reason_code"] in EXPLANATIONS for record in records)
    lines.append("BALANCE=" + ("PASS" if balanced else "FAIL") + " (input/audit/settlement counts, audit/settlement content, input tracing)")
    if not known:
        lines.append("REPORT=FAIL (unrecognized reason code)")
    text = "\n".join(lines) + "\n"
    if not balanced or not known:
        raise AuditError(text)
    return text, totals
