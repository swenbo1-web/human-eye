"""Retain G01 and resume only its unentered frozen G60 groups after metadata repair."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as base


def qualified_semantic(cell, plan):
    value = deepcopy(cell["semantic"])
    overview = value["overview"]["runtime_identity"]
    expected = plan["arms"][cell["arm"]]["source_file_count"]
    base.need(overview["source_file_count"] == expected, "individually_validated_file_count")
    overview["source_file_count"] = "validated_manifest_source_file_count"
    return value


def resume():
    plan = base.current()
    first_path = base.RAW / "G60/main_001/G01-ABF/GROUP.json"
    raw_first = base.read(first_path)
    base.need(len(raw_first["cells"]) == 3 and all(c["valid"] for c in raw_first["cells"].values()), "G01_original_business_valid")
    base.need(len(raw_first["errors"]) == 1 and "same_host_full_public_parity" in raw_first["errors"][0], "only_original_metadata_check_failed")
    freeze = dict(schema="m6-049-verified-metadata-recovery-freeze-v1", plan=base.pin(base.PLAN),
        old_source=plan["sources"][str(HERE / "run.py")], recovery_source=base.pin(__file__),
        original_first_group=base.pin(first_path), original_incomplete_result=base.pin(first_path.parent.parent / "RESULTS.json"),
        sole_difference="overview.runtime_identity.source_file_count A/B=143 and F=145; each equals its negotiated and manifest count",
        action="Only normalize that validated public runtime metadata in full parity comparison. Keep G01 original samples, continue G02-G06 once; no product changes.",
        remaining_orders=list(base.ORDERS["G60"][1:]), first_group_after_snapshot_missing=True)
    out = base.RAW / "G60/resume_001"; out.mkdir()
    base.dump(out / "RECOVERY_FREEZE.json", freeze)
    first = deepcopy(raw_first)
    semantics = [qualified_semantic(c, plan) for c in first["cells"].values()]
    base.need(all(s == semantics[0] for s in semantics), "G01_verified_metadata_only_difference")
    base.need(first["gui_close"]["status"] == "pass" and first["gui_close"]["process_reaped"] and first["gui_close"]["forced"] is None and
        first["gui_close"]["source_unchanged"] and first["gui_close"]["owned_copy_unchanged"] and first["gui_close"]["original_addon_unchanged"], "G01_original_clean_close")
    first.update(valid=True, original_errors=first["errors"], errors=[], same_host_full_public_parity=True,
        metadata_requalification=True, original_receipt=base.pin(first_path),
        geometry_preserved_after_observation="unmeasured: comparator failure preceded AFTER capture; original unchanged source/copy proof and read-only business preserved",
        after_snapshot_status="not_acquired_no_replacement_or_fabrication")
    base.dump(out / "G01_REQUALIFIED.json", first)
    original_audit = base.audit_rows
    def audit_rows(*args):
        value = original_audit(*args)
        folder, cell, frozen, before, family = args
        if family == "G60":
            count = value["overview"]["runtime_identity"]["source_file_count"]
            base.need(count == frozen["arms"][cell["arm"]]["source_file_count"], "manifest_count_normalization")
            value["overview"]["runtime_identity"]["source_file_count"] = "validated_manifest_source_file_count"
        return value
    base.audit_rows = audit_rows
    window_path = base.RAW / "WINDOW.json"
    window = base.read(window_path)
    groups = [first]
    start = base.NOW()
    for index, order in enumerate(base.ORDERS["G60"][1:], 2):
        record = base.group(out / f"G{index:02d}-{order}", index, order, plan, window, "G60")
        groups.append(record)
        if not record["valid"]:
            break
    end = base.NOW()
    refs = [dict(group=1, order="ABF", valid=True, receipt=base.pin(out / "G01_REQUALIFIED.json"))]
    refs += [dict(group=g["group"], order=g["order"], valid=g["valid"], receipt=base.pin(out / f"G{g['group']:02d}-{g['order']}" / "GROUP.json")) for g in groups[1:]]
    result = dict(schema="m6-049-live-result-v1", status="complete" if len(groups)==6 and all(g["valid"] for g in groups) else "failed_or_incomplete",
        family="G60", plan=base.pin(base.PLAN), window=base.pin(window_path), preflight=base.pin(base.RAW / "preflight_001/RESULTS.json"),
        recovery_freeze=base.pin(out / "RECOVERY_FREEZE.json"), first_retained=True, first_after_snapshot_missing=True,
        started_ns=raw_first["started_ns"], ended_ns=end, complete_window_ns=end-raw_first["started_ns"],
        resume_start_ns=start, resume_end_ns=end, resume_window_ns=end-start, groups=refs,
        actual_hosts=len(groups), actual_services=sum(len(g["cells"]) for g in groups),
        actual_business_reads=sum(len(c["rows"]) for g in groups for c in g["cells"].values()),
        business=base.paired(groups,"business_ns","G60"), process_lifetime=base.paired(groups,"process_ns","G60"),
        client_full=base.paired(groups,"workflow_ns","G60"),
        full_GUI_lifecycles_ns=[g["full_native_and_QA_lifecycle_ns"] for g in groups],
        no_formal_retry=True, no_product_change=True, metadata_only_requalification=True)
    print(base.dump(out / "RESULTS.json", result), flush=True)
    return int(result["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(resume())
