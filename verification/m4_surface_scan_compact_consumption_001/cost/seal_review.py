"""Seal the fixed nine-cell offline review after cross-checking its evidence paths.

Adapted from verification/m4_surface_scan_consumption_001/cost/seal_review.py.
This script reads existing evidence and writes only this cost directory.
"""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")


def verify_records(base, records):
    for record in records:
        data = (base / record["path"]).read_bytes()
        assert len(data) == record["bytes"] and sha(data) == record["sha256"], record["path"]


def main():
    root = read(HERE / "ROOT_RECONCILIATION.json")
    ledger = read(HERE / "accounting/LEDGER.json")
    validation = read(HERE / "accounting/VALIDATION.json")
    mechanism = read(HERE / "mechanism/MECHANISM.json")
    binding = read(HERE / "binding/BINDING_RESULT.json")
    work = read(HERE / "WORK_ORDER.json")
    plan = read(BATCH / "PLAN.json")
    original_manifest = BATCH / "DELIVERY_MANIFEST.json"
    assert sha(original_manifest.read_bytes()) == "2523d79a28a0d144a8a50a7da66d1612121560abacef434a45fc08fc8499df5d"
    verify_records(BATCH, read(original_manifest)["files"])
    assert root["original_content_files_preserved"] == 2335
    assert binding["status"] == "pass" and binding["source_mismatch_affecting_quality"] is False
    assert binding["verifier_script_sha256"] == sha((HERE / "binding/verify_binding.py").read_bytes())
    assert binding["strict_failed_cells_retained"] == ["N2", "O2"]
    assert binding["original_cell_archives_verified"] == 9
    assert binding["actual_initial_final_snapshots_verified"] == 18
    assert binding["owner_business_attempts_verified"] == 27
    assert binding["consumer_business_events_verified"] == 54
    assert binding["new_model_Blender_product_API_runs"] == ledger["new_Blender_model_API_runs"] == mechanism["new_blender_model_api_runs"] == 0
    assert validation["independent_root_reconciliation_sha256"] == sha((HERE / "ROOT_RECONCILIATION.json").read_bytes())
    assert validation["identical_LEDGER_and_REPORT_bytes"] is True
    for filename, expected in validation["output_sha256"].items():
        assert sha((HERE / "accounting" / filename).read_bytes()) == expected
    for field in ("quality_seal_sha256", "cost_plan_sha256"):
        assert ledger[field] == mechanism[field] == binding[field]

    accounting_cells = {row["cell"]: row for row in ledger["cells"]}
    mechanism_cells = {row["cell"]: row for row in mechanism["cells"]}
    binding_cells = {row["cell"]: row for row in binding["cells"]}
    assert len(root["cells"]) == len(accounting_cells) == len(mechanism_cells) == len(binding_cells) == 9
    for row in root["cells"]:
        cell = row["cell"]
        account, facts, identity = accounting_cells[cell], mechanism_cells[cell], binding_cells[cell]
        assert row["full_cell_wall_ns"] == account["full_cell_wall_ns"] == facts["full_cell_wall_ns"] == identity["full_cell_wall_ns"]
        assert row["input_plus_output_tokens"] == account["total_input_plus_output_tokens"]
        assert row["thread_id"] == account["thread_id"] == identity["thread_id"]
        assert row["recorded_tool_attempts"] == account["tool_attempts"] == identity["business_attempts"] == len(facts["attempts"])
        assert row["final_sha256"] == facts["final_sha256"] == identity["final_sha256"]
        assert row["anonymous_id"] == account["anonymous_id"] == facts["anonymous_id"] == identity["anonymous_id"]
        assert row["primary_quality"] == account["quality"] == facts["primary_classification"] == identity["primary_classification"]
        assert row["content_quality"] == account["final_content_quality"] == facts["content_classification"] == identity["final_content_classification"] == "complete_correct"
        assert row["valid_completion"] == account["consumer_valid_completion"] == facts["valid_completion"] == identity["valid_completion"]
        assert facts["first_complete_cli_receipt_to_final_ns"] == facts["later_tool_event_wall_ns"] + facts["remaining_non_tool_tail_ns"]
        assert identity["thin_client_EXIT"] == "unknown"
    for group in ("N", "O", "C"):
        summary, account, facts = root["groups"][group], ledger["groups"][group], mechanism["group_summaries"][group]
        assert summary["full_wall_sum_ns"] == account["sum"]["full_cell_wall_ns"]
        assert summary["input_plus_output_tokens"] == account["sum"]["total_input_plus_output_tokens"]
        assert summary["effective_complete_correct"] == account["valid_complete_correct"] == facts["valid_correct"]
        assert summary["recorded_tool_attempts"] == account["sum"]["tool_attempts"] == facts["tool_calls"]
        assert account["sum"]["recorded_model_facing_tool_text_utf8_bytes"] == facts["observed_tool_text_bytes"]
    for baseline in ("N", "O"):
        comparison = root["comparisons"]["C_vs_" + baseline]
        account = ledger["comparisons"]["C_over_" + baseline]
        assert comparison["quality_execution_prerequisites_met"] == account["formal_execution_quality_precondition"] == mechanism["formal_comparison_quality_prerequisite"]["C_vs_" + baseline] is False
        assert comparison["formal_gate_pass"] == account["formal_gate_pass"] is False
        descriptive = account["descriptive_all_cells"]
        assert comparison["paired_wall_median"] == descriptive["median_paired_full_wall_ratio"]
        assert comparison["total_token_ratio"] == descriptive["reported_token_ratio"]
        assert comparison["numeric_wall_condition"] == descriptive["time_numeric_condition"] is True
        assert comparison["numeric_token_condition"] == descriptive["token_numeric_condition"] is True
        assert descriptive["includes_all_error_cells"] is True
        assert descriptive["network_duration_subtracted_ns"] == 0

    verify_records(BATCH, ledger["sources"])
    verify_records(ROOT, [{"path": name, **record} for name, record in mechanism["source_inventory"].items()])
    verify_records(ROOT, binding["input_inventory"])
    helper = ROOT / "verification/m4_surface_scan_consumption_001/cost/seal_review.py"
    ready = {
        "callback": "M4-SURFACE-SCAN-COMPACT-CONSUMPTION-001_COST_READY",
        "phase": "same_nine_originals_cost_and_mechanism_review_after_quality_seal",
        "original_delivery_commit": work["original_delivery_commit"],
        "preparation_commit": work["preparation_commit"],
        "admin_quality_and_plan_commit": work["admin_commit"],
        "fixed_product_commits": plan["fixed_product_commits"],
        "candidate_source_sha256": plan["candidate_source_sha256"],
        "quality_seal_sha256": binding["quality_seal_sha256"],
        "cost_plan_sha256": binding["cost_plan_sha256"],
        "quality": {
            "final_content_complete_correct": 9,
            "primary_complete_correct": 7,
            "primary_execution_failure": 2,
            "not_run": 0,
            "strict_failed_cells_retained": ["N2", "O2"],
            "by_cell": root["cells"],
        },
        "groups": root["groups"],
        "comparisons": root["comparisons"],
        "formal_gates": "Both lack the original 3/3 valid-completion prerequisite; numerical conditions are descriptive only.",
        "review_checks": {
            "accounting": ledger["checks"], "accounting_input_files": len(ledger["sources"]),
            "mechanism": mechanism["assertions_passed"], "mechanism_input_files": mechanism["source_file_count"],
            "binding": binding["checks"], "binding_input_files": binding["input_file_count"],
            "overlapping_checks_are_not_task_samples": True,
        },
        "confirmed_findings": [
            "All three compact consumers explicitly requested brief, received 7911 bytes and 71 complete rows, then delivered correct finals after one observe.",
            "All three old OPT1 consumers received complete detailed facts twice, then performed native full-scene recomputation.",
            "O3 native intermediate output missed one pair and miscomputed two zero distances; its correction and all costs are retained.",
            "The whole candidate includes representation and actual tool-description changes; bytes-only causality is not isolated.",
            "Final UTF-8 bytes and cumulative output tokens are separate; compact finals remain flat 71-row tables.",
        ],
        "mechanism_group_summaries": mechanism["group_summaries"],
        "limitations": binding["limitations"] + [
            "Final reported usage coverage of interrupted provider streams is unconfirmed.",
            "Provider caching was uncontrolled; total tokens do not identify cash savings or peak context.",
            "Non-tool timing mixes generation, provider, network, scheduling and CLI handling.",
            "One fixed static scene and task repeated three times does not establish broad generalization or tails.",
            "AL remains unbound, so task synchronization is unavailable.",
        ],
        "analyzer_failures_preserved": ["mechanism/ANALYSIS_FAILURE_01.json", "binding/CHECK_HISTORY.json"],
        "new_Blender_product_model_API_runs": 0,
        "seal_script_reused_from": {"path": helper.relative_to(ROOT).as_posix(), "sha256": sha(helper.read_bytes())},
        "artifacts": ["REPORT.md", "ROOT_RECONCILIATION.json", "accounting/REPORT.md", "accounting/LEDGER.json",
                      "mechanism/REPORT.md", "mechanism/MECHANISM.json", "binding/REPORT.md", "binding/BINDING_RESULT.json",
                      "DELIVERY_MANIFEST.json"],
        "next_action": "Send the authorized administrator callback and end this batch for independent review.",
    }
    write(HERE / "COST_READY.json", ready)
    records = []
    for path in sorted(HERE.rglob("*"), key=lambda item: item.relative_to(HERE).as_posix()):
        if not path.is_file() or path.name == "DELIVERY_MANIFEST.json":
            continue
        assert "__pycache__" not in path.parts and path.suffix != ".pyc"
        data = path.read_bytes()
        if path.suffix == ".json":
            json.loads(data)
        if path.suffix == ".py":
            ast.parse(data.decode("utf8"), filename=str(path))
        records.append({"path": path.relative_to(HERE).as_posix(), "bytes": len(data), "sha256": sha(data)})
    manifest = {
        "callback": ready["callback"], "manifest_scope": "All cost/ files except this manifest itself",
        "original_delivery_commit": work["original_delivery_commit"], "file_count": len(records),
        "total_bytes": sum(row["bytes"] for row in records), "files": records,
    }
    destination = HERE / "DELIVERY_MANIFEST.json"
    write(destination, manifest)
    print(json.dumps({"content_files": len(records), "total_delivery_files": len(records) + 1,
                      "manifest_sha256": sha(destination.read_bytes()), "formal_gates": ready["formal_gates"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
