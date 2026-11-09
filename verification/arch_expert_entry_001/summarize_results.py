"""Summarize saved evidence with stdlib only; does not import or execute product."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


rounds = []
for name in ("entry_tests_01", "entry_tests_02", "entry_lazy_03", "affected_01", "affected_02", "affected_03"):
    saved = read(name + ".json")
    row = {key: saved.get(key, 0) for key in ("tests", "failures", "errors", "skipped")}
    row.update(name=name, passed=saved["passed"], source_sha256=saved.get("source_sha256"))
    row["passed_methods"] = row["tests"] - row["failures"] - row["errors"] - row["skipped"]
    rounds.append(row)

actual = read("actual_run_02/RESULTS.json")
first = read("actual_run_01/RESULTS.json")
modes = {}
for mode in ("owned", "shared", "owned_task"):
    rows = [row for row in actual["records"] if row["mode"] == mode]
    modes[mode] = dict(tool_attempts=len(rows),
                       estimated=sum(row["result"].get("status") == "estimated" for row in rows),
                       expected_errors=sum(row["label"] == "out_of_domain" for row in rows),
                       ordinary_positive=sum(row["label"].startswith("ordinary_") for row in rows))

work = {}
for row in actual["records"]:
    for event in row["blender_events"]:
        for key, value in event.get("work_delta", {}).items():
            work[key] = work.get(key, 0) + value

m5_keys = ("label", "passed", "setter_count", "loop_ms", "lifecycle_ms", "loop_host_requests",
           "loop_transport_bytes", "worker_pid", "worker_returncode", "worker_closed", "native_check", "post_loop_delta")
summary = {
    "task": "ARCH-EXPERT-ENTRY-001",
    "disposition": "implementation_and_fixed_source_qa_complete_pending_mainline_deep_review",
    "passed": True,
    "workspace": "C:/Users/Administrator/.codex/worktrees/2c7d/hefe",
    "branch": "codex/architecture-expert-entry",
    "product_commit": actual["product_commit"],
    "source_sha256": actual["source_sha256"], "source_members": actual["source_members"],
    "source_adapter_sha256": "653eaaa9ee3292a1a490ba4a01637e495977bd9f668e1c584c9649927cf92715",
    "lineage": {
        "base": "76375c0dd4c274120918b9984ec4829ac56740ed",
        "cherry_picks": [
            {"accepted": "ef84ecc59f107321225d0d832fde119ed0b91e3f", "local": "f447baef5c56367a5b1d26561832a7016daefe60"},
            {"accepted": "9508a1d5cbdcadad80a42c4922501c855d5ae570", "local": "968436ce5de316bef33ebc47d9147ae584945fd7"},
            {"accepted": "b2d92bb5802cc86b855f5a7179fdff80812c2e25", "local": "539c277daa0088e30b0073d40aeb5e4368b44f6c"}],
        "rejected_evidence_not_integrated": "3ff76aba2a8f1592a5109ca91430496db57e1773"},
    "cpu": {
        "rounds": rounds,
        "totals": {key: sum(row[key] for row in rounds) for key in ("tests", "passed_methods", "failures", "errors", "skipped")},
        "final_distinct_methods": 165, "final_passed": 165, "new_entry_methods": 14,
        "historical_accepted_tests_added_to_total": False,
        "affected_02_source_snapshot": "reconstructed_not_original",
        "final_test_sha256": "458684ef669c936c0b4e659be96a2635c1dbc09ce6df8aaf2fa5d6adfe7d55ca"},
    "actual_attempts": [
        {"name": "actual_run_01", "passed": False, "tool_attempts": 2, "positive_records": first["record_count"],
         "unexpected_errors": 1, "expert_calls": 0, "setters": 0,
         "cause": "ordinary nearest rejected existing static-only source domain because Armature was linked",
         "fix": "verification scene unlink/relink controls only; no product modification"},
        {"name": "actual_run_02", "passed": actual["passed"], "tool_attempts": 25, "positive": 23, "expected_errors": 2,
         "by_mode": modes, "successful_real_model_estimates": 14, "unknown_actual_runs": 0,
         "oracle_region_comparisons": 350, "oracle_scores_exact": True,
         "successful_capture_work_count": 14, "capture_method_entry_count": 16,
         "work_delta_totals": work, "runner_sequence_ms": actual["runner_sequence_ms"]}],
    "fixture": {key: actual["fixture_spec"][key] for key in ("total_vertices", "selected_vertices", "selected_triangles",
                 "total_triangles", "selection_bytes", "initial_case", "pose_case", "dataset_sha256")},
    "m5_same_source": {"passed": actual["m5_same_source"]["passed"], "source_sha256": actual["m5_same_source"]["source_sha256"],
                       "cases": [{key: case[key] for key in m5_keys} for case in actual["m5_same_source"]["cases"]],
                       "scheduler_attempts": 3, "physical_setters_total": 5, "separate_post_loop_reads": 9},
    "processes": actual["processes"], "model_api_calls": 0, "user_assets": 0,
    "evidence": {"report": "REPORT.md", "actual_report": "ACTUAL_QA_REPORT.md", "costs": "ACTUAL_COSTS.json",
                 "cleanup": "PROCESS_CLEANUP.json", "independent_review": "REVIEW.md", "index": "EVIDENCE_INDEX.json"},
    "limitations": [
        "Synthetic training estimate on explicitly selected closed arm sections; no repair or automatic selection.",
        "Unknown normal-report semantics statically reviewed; neither this CPU group nor actual Blender dynamically covers unknown.",
        "Local Python row counters do not bound whole-mesh BMesh from_mesh or lookup costs.",
        "Tool RTT includes unquantified observer/oracle overhead; product_method_ms excludes oracle. No native performance target inferred.",
        "Ordinary task/nearest positive reads use a static-only scene with verification unlink/relink outside tool timing.",
        "Shared uses a real socket addon-shaped generated fixture, not an existing human interactive scene.",
        "Shared controlled terminate/wait returncode is 1; PID identity is checked because Windows reused one PID.",
        "Original affected_02 pre-fix test bytes unavailable; reconstruction is explicitly labeled."]}
assert summary["cpu"]["totals"] == dict(tests=521, passed_methods=517, failures=3, errors=1, skipped=0)
assert sum(row["estimated"] for row in modes.values()) == 14
assert work["captures"] == 14
(ROOT / "RESULTS.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"written": "RESULTS.json", "cpu": summary["cpu"]["totals"], "work_totals": work}))
