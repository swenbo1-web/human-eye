"""Seal the completed offline review after reconciling its three evidence paths."""

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


def main():
    root = read(HERE / "ROOT_RECONCILIATION.json")
    ledger = read(HERE / "accounting/LEDGER.json")
    mechanism = read(HERE / "mechanism/MECHANISM.json")
    binding = read(HERE / "binding/BINDING_RESULT.json")
    assert binding["status"] == "pass"
    assert binding["verification_script_sha256"] == sha((HERE / "binding/verify_binding.py").read_bytes())
    assert root["original_content_files_verified"] + 1 == binding["original_delivery_files"] == 1975
    assert binding["source_count"] == 138 and binding["snapshots"] == 12
    assert binding["business_attempts"] == 26
    assert binding["thin_client_exit_unknown_count"] == 6
    assert ledger["gate"]["quality_both_3_of_3"] == root["gate"]["quality"] is True
    assert ledger["gate"]["paired_full_wall_pass"] == root["gate"]["paired_wall_median_le_0_70"] is False
    assert ledger["gate"]["token_pass"] == root["gate"]["plugin_total_tokens_le_native"] is False
    assert ledger["gate"]["overall_pass"] == root["gate"]["same_quality_net_benefit"] is False
    for field in ("numerator", "denominator"):
        assert ledger["gate"]["paired_full_wall_ratio_median"][field] == root["median_paired_full_wall_ratio"][field]

    accounting_cells = {row["cell"]: row for row in ledger["cells"]}
    mechanism_cells = {row["cell"]: row for row in mechanism["cells"]}
    binding_cells = {row["cell"]: row for row in binding["cells"]}
    for row in root["six_original_cells"]:
        cell = row["cell"]
        account, facts, identity = accounting_cells[cell], mechanism_cells[cell], binding_cells[cell]
        assert row["full_cell_wall_ns"] == account["full_cell_wall_ns"] == facts["full_cell_wall_ns"] == identity["full_cell_wall_ns"]
        assert row["input_plus_output_tokens"] == account["total_input_plus_output_tokens"]
        assert row["thread_id"] == account["thread_id"] == identity["thread_id"]
        assert row["tool_attempts"] == account["tool_attempts"] == identity["tool_attempts"] == len(facts["attempts"])
        assert facts["final_sha256"] == identity["final_sha256"]
        assert facts["first_complete_list_receipt_to_final_ns"] == facts["later_tool_event_wall_ns"] + facts["remaining_non_tool_tail_ns"]
    for group in ("N", "P"):
        assert root["groups"][group]["full_wall_sum_ns"] == ledger["groups"][group]["sum"]["full_cell_wall_ns"]
        assert root["groups"][group]["input_plus_output_tokens"] == ledger["groups"][group]["sum"]["total_input_plus_output_tokens"]
    for record in ledger["sources"]:
        relative = record["path"]
        data = (BATCH / relative).read_bytes()
        assert len(data) == record["bytes"] and sha(data) == record["sha256"], relative
    for relative, record in mechanism["sources"].items():
        data = (ROOT / relative).read_bytes()
        assert len(data) == record["bytes"] and sha(data) == record["sha256"], relative

    ready = {
        "callback": "M4-SURFACE-SCAN-CONSUMPTION-001_COST_READY",
        "phase": "post_quality_seal_same_originals_cost_and_consumption_review",
        "original_delivery_commit": binding["delivery_commit"],
        "admin_quality_and_plan_commit": "91cce49cd83c5dd00bac270b2ae128a2ede5b3ba",
        "product_commit": binding["product_commit"], "product_source_sha256": binding["source_sha256"],
        "quality_seal_sha256": binding["quality_seal_sha256"], "cost_plan_sha256": binding["cost_plan_sha256"],
        "quality": {"complete_correct": 6, "execution_failed": 0, "not_run": 0},
        "gate": root["gate"], "median_paired_full_wall_ratio": root["median_paired_full_wall_ratio"],
        "native_input_plus_output": root["groups"]["N"]["input_plus_output_tokens"],
        "plugin_input_plus_output": root["groups"]["P"]["input_plus_output_tokens"],
        "token_ratio": root["token_ratio"],
        "review_checks": {"accounting": ledger["checks"], "mechanism": mechanism["assertions_passed"],
                          "binding": binding["check_count"], "check_counts_are_not_task_samples": True},
        "confirmed_findings": [
            "All six scan responses retain the full 71 matches and 34754 UTF-8 bytes through CLI result receipts.",
            "The surface_scan early-return branch bypasses brief projection.",
            "All three plugin consumers subsequently perform native full-scene recomputation.",
            "Native consumers also perform retained validation and formatting work.",
        ],
        "next_hypothesis": "Compact complete surface_scan fact delivery; actual consumer/token/time benefits remain unmeasured.",
        "limitations": root["unmeasured"] + [
            "Imperfect blinding from business tool content.",
            "Provider cache and internal shared state were not controlled.",
            "Historical process memory and reverted transient changes were not replayed.",
            "Runtime diagnostics retained; their independent blocking contribution is unmeasured.",
            "Agent Learning task synchronization remains unavailable due to unbound runtime.",
        ],
        "new_execution_count": root["live_execution_count"],
        "artifacts": ["REPORT.md", "ROOT_RECONCILIATION.json", "accounting/REPORT.md",
                      "accounting/LEDGER.json", "mechanism/REPORT.md", "mechanism/MECHANISM.json",
                      "binding/REPORT.md", "binding/BINDING_RESULT.json", "DELIVERY_MANIFEST.json"],
        "next_action": "Report to the authorized administrator chat and wait for independent review.",
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
        "original_delivery_commit": binding["delivery_commit"], "file_count": len(records),
        "total_bytes": sum(row["bytes"] for row in records), "files": records,
    }
    path = HERE / "DELIVERY_MANIFEST.json"
    write(path, manifest)
    print(json.dumps({"content_files": len(records), "total_delivery_files": len(records) + 1,
                      "manifest_sha256": sha(path.read_bytes()), "gate": root["gate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
