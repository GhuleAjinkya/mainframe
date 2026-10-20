"""Validated batch artifacts for the local dashboard, kept entirely in memory.

The dashboard uses the same converter, report, and holdings reconciliation as
the command-line pipeline. Temporary files only adapt their file interfaces;
they are deleted before this module returns its model.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .audit_to_json import convert
from .contracts import EXPLANATIONS, REASON_STATUS, read_records, timestamp, write_records
from .engine import process
from .errors import AuditError, InfrastructureError
from .reconciliation import reconcile_holdings
from .report import report


@dataclass(frozen=True)
class DashboardReports:
    report_text: str
    jsonl_text: str
    audit_documents: tuple[dict, ...]
    audit_records: tuple[str, ...]
    settlement_records: tuple[str, ...]
    holdings_records: tuple[str, ...]
    holdings: tuple[dict, ...]
    summary: dict
    checks: dict[str, str]
    rejections: tuple[dict, ...]
    trade_pairs: tuple[dict, ...]
    inputs: dict[str, tuple[str, ...]]
    prices: tuple[dict, ...]


def _snapshot_bytes(replay):
    snapshots = getattr(replay, "input_snapshots", None)
    if snapshots is not None:
        return {name: snapshots[name] for name in ("orders", "holdings", "prices")}
    # Support older callers that construct Replay directly. Output equality is
    # checked below before any source-file contents can be presented as this run.
    return {name: Path(getattr(replay, f"{name}_path")).read_bytes()
            for name in ("orders", "holdings", "prices")}


def _trade_pairs(replay, documents):
    pairs = []
    seen = set()
    for event in replay.events:
        if event["phase"] != "settlement":
            continue
        active = tuple(event["active_rows"])
        if len(active) != 2 or len(set(active)) != 2:
            raise InfrastructureError("dashboard settlement trace requires two distinct order rows")
        if any(row < 1 or row > len(documents) or row in seen for row in active):
            raise InfrastructureError("dashboard settlement trace duplicates or omits an audit row")
        first, second = (documents[row - 1] for row in active)
        if {first["side"], second["side"]} != {"B", "S"}:
            raise InfrastructureError("dashboard settlement trace has no BUY/SELL pair")
        buy, sell = (first, second) if first["side"] == "B" else (second, first)
        buy_row, sell_row = active if first["side"] == "B" else tuple(reversed(active))
        if (buy["status"] != "SETTLED" or sell["status"] != "SETTLED"
                or buy["stock_code"] != sell["stock_code"]
                or buy["client_id"] == sell["client_id"]
                or buy["quantity"] != sell["quantity"]
                or buy["execution_price_paise"] != sell["execution_price_paise"]):
            raise InfrastructureError("dashboard settlement trace differs from the engine audit")
        seen.update(active)
        pairs.append({
            "pair": len(pairs) + 1, "step": event["step"],
            "as_of": event["as_of"], "stock_code": buy["stock_code"],
            "buy_row": buy_row, "sell_row": sell_row,
            "buy_order_id": buy["order_id"], "sell_order_id": sell["order_id"],
            "buyer": buy["client_id"], "seller": sell["client_id"],
            "quantity": buy["quantity"],
            "execution_price_paise": buy["execution_price_paise"],
            "notional_paise": buy["quantity"] * buy["execution_price_paise"],
        })
    settled = {number for number, record in enumerate(documents, 1) if record["status"] == "SETTLED"}
    if seen != settled:
        raise InfrastructureError("dashboard settlement trace does not cover all settled audit rows")
    return tuple(pairs)


def _money(paise):
    if paise is None:
        return "UNPRICED"
    return f"INR {paise // 100:,}.{paise % 100:02d}"


def _full_report(base_report, pairs, holdings, checks, summary):
    lines = [base_report.rstrip(), "", "EXECUTED TRADE PAIRS (each pair contains two settled orders)"]
    for pair in pairs:
        lines.append(
            f"{pair['pair']:04d} {pair['stock_code']} QTY={pair['quantity']} "
            f"PRICE={_money(pair['execution_price_paise'])} VALUE={_money(pair['notional_paise'])} "
            f"BUY={pair['buy_order_id']} ({pair['buyer']}, row {pair['buy_row']}) "
            f"SELL={pair['sell_order_id']} ({pair['seller']}, row {pair['sell_row']})"
        )
    lines.append(f"MATCHED_PAIRS={len(pairs)} EXECUTED_VALUE={_money(sum(pair['notional_paise'] for pair in pairs))}")
    lines.extend(["", "FINAL HOLDINGS AND VALUATION"])
    for holding in holdings:
        lines.append(
            f"{holding['client_id']:<8} {holding['stock_code']:<8} "
            f"QTY={holding['quantity']} REFERENCE={_money(holding['reference_price_paise'])} "
            f"VALUE={_money(holding['valuation_paise'])}"
        )
    lines.extend(["", "VALIDATION CHECKS"])
    lines.extend(f"{name.upper()}={result}" for name, result in checks.items())
    lines.extend(["", "INPUT SNAPSHOT SHA-256"])
    lines.extend(f"{name.upper()}={details['sha256']}" for name, details in summary["inputs"].items())
    lines.extend(["", "Engine: Python reference. REXX executed: false.",
                  "COBOL and JCL source templates are available; this dashboard runs locally in Python."])
    return "\n".join(lines) + "\n"


def build_dashboard_reports(replay):
    """Create a complete, checked report model for the replay's exact batch.

    A replay with captured input bytes continues to work if its original files
    move or change. Older manually constructed replays require matching source
    files and fail visibly when their outputs no longer match.
    """
    try:
        snapshots = _snapshot_bytes(replay)
        with TemporaryDirectory(prefix="stkcp-dashboard-") as temporary:
            root = Path(temporary)
            paths = {}
            inputs = {}
            manifest = {}
            for name, data in snapshots.items():
                paths[name] = root / f"{name}.txt"
                paths[name].write_bytes(data)
                inputs[name] = tuple(read_records(paths[name]))
                manifest[name] = {"sha256": hashlib.sha256(data).hexdigest()}
            audit, holdout = process(paths["orders"], paths["holdings"], paths["prices"])
            same_batch = tuple(audit) == replay.audit and tuple(holdout) == replay.holdout
            if not same_batch:
                raise InfrastructureError("dashboard input snapshots do not match the replay audit and holdings")
            audit_path, settlement_path, holdings_path = (root / name for name in ("audit.dat", "settlement.dat", "holdings.dat"))
            # The reference engine emits an identical settlement and audit row
            # per order, as in the normal local pipeline.
            write_records(audit_path, audit)
            write_records(settlement_path, audit)
            write_records(holdings_path, holdout)
            json_path = root / "audit.jsonl"
            converted = convert(audit_path, json_path)
            jsonl_text = json_path.read_text(encoding="utf-8")
            documents = tuple(json.loads(line) for line in jsonl_text.splitlines())
            base_report, totals = report(audit_path, paths["orders"], settlement_path)
            holdings = tuple(reconcile_holdings(paths["holdings"], audit_path, holdings_path))
            settlement = tuple(read_records(settlement_path))
        pairs = _trade_pairs(replay, documents)
        quantities = defaultdict(int)
        notionals = defaultdict(int)
        for record in documents:
            if record["status"] == "SETTLED":
                signed = record["quantity"] * (1 if record["side"] == "B" else -1)
                quantities[record["stock_code"]] += signed
                notionals[record["stock_code"]] += signed * record["execution_price_paise"]
        final = replay.events[-1]
        reconciled = {(item["client_id"], item["stock_code"]): item["quantity"] for item in holdings}
        displayed = {(item["client_id"], item["stock_code"]): item["quantity"] for item in final["holdings"]}
        report_balanced = (totals["input"] == totals["total"] == totals["settlement"]
                           and totals["total"] == sum(totals[name] for name in ("settled", "pending", "rejected")))
        checks = {
            "input_snapshot_match": "PASS" if same_batch else "FAIL",
            "report_balance": "PASS" if report_balanced else "FAIL",
            "json_record_count": "PASS" if converted == len(documents) == totals["total"] else "FAIL",
            "settlement_content": "PASS" if tuple(audit) == settlement else "FAIL",
            "holdings_reconciliation": "PASS" if reconciled == displayed else "FAIL",
            "trade_balance": "PASS" if (not any(quantities.values()) and not any(notionals.values())
                and len(pairs) * 2 == totals["settled"]
                and len(pairs) == final["executed_pairs"]
                and sum(pair["notional_paise"] for pair in pairs) == final["executed_notional_paise"]) else "FAIL",
        }
        if any(result != "PASS" for result in checks.values()):
            raise InfrastructureError("dashboard artifact validation failed: " + ", ".join(name for name, result in checks.items() if result != "PASS"))
        reason_counts = Counter(record["reason_code"] for record in documents if record["status"] == "REJECTED")
        rejections = tuple({"reason_code": code, "count": reason_counts[code], "explanation": explanation}
                           for code, explanation in EXPLANATIONS.items() if REASON_STATUS[code] == "REJECTED")
        prices = tuple({"row": number, "stock_code": raw[:8].rstrip(),
                        "timestamp": timestamp(raw[8:22]).isoformat(),
                        "price_paise": int(raw[22:32]), "raw_record": raw}
                       for number, raw in enumerate(inputs["prices"], 1))
        summary = {"schema_version": 1, "engine": "python-reference", "rexx_executed": False,
                   "holdings_reconciled": checks["holdings_reconciliation"] == "PASS",
                   "totals": totals, "inputs": manifest, "holdings": list(holdings)}
        return DashboardReports(
            report_text=_full_report(base_report, pairs, holdings, checks, summary),
            jsonl_text=jsonl_text, audit_documents=documents,
            audit_records=tuple(audit), settlement_records=settlement,
            holdings_records=tuple(holdout), holdings=holdings, summary=summary,
            checks=checks, rejections=rejections, trade_pairs=pairs, inputs=inputs, prices=prices,
        )
    except (AuditError, OSError, UnicodeError) as error:
        raise InfrastructureError(str(error)) from error
