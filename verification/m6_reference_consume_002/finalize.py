"""Collect bounded-run costs and verify the immutable delivery evidence."""

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
TASK_STARTED_EPOCH = 1794767579.4681473
ORDER = [("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native")]


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf8",
        newline="\n",
    )


def resolve(name):
    path = Path(name)
    return path if path.is_absolute() else HERE / path


def identity(path):
    path = resolve(path)
    data = path.read_bytes()
    return {
        "path": path.relative_to(HERE).as_posix() if path.is_relative_to(HERE) else str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def metered_fields(record):
    fields = ("wall_s", "cpu_s", "CPU_s", "parent_CPU_s", "body_wall_s", "body_CPU_s",
              "analyzer_wall_s", "last_invocation_wall_s", "nested_Blender_wall_s",
              "measured_shell_wall_s", "successful_script_wall_s", "successful_parent_CPU_s")
    return {key: record[key] for key in fields if key in record}


def process_fields(record):
    fields = ("pid", "status", "returncode", "full_process_wall_s", "full_process_cpu_s",
              "peak_working_set_bytes", "tree_cpu_s", "tree_sampled_peak_working_set_bytes",
              "memory_samples", "memory_scope", "tree_scope")
    return {key: record[key] for key in fields if key in record}


def costs():
    started = time.perf_counter()
    parent_cpu = time.process_time()
    sessions = []
    usage = Counter()
    tool_totals = Counter()
    image_totals = Counter()
    python_totals = Counter()
    bridges = []
    for stage, route in ORDER:
        folder = Path("private/consumers") / stage / "forearm" / route
        record = read(folder / "CONSUMER.json")
        bridge = read(folder / "bridge/BRIDGE_RESULT.json")
        stats = next(row for row in read("CONSUMER_STATS_all.json")["sessions"]
                     if row["stage"] == stage and row["route"] == route)
        usage.update(record["usage"])
        for call in bridge["calls"]:
            tool_totals["wall_s"] += call["wall_s"]
            for key in ("public_text_UTF8_bytes", "complete_text_UTF8_bytes", "stdio_response_UTF8_bytes"):
                tool_totals[key] += call.get(key, 0)
            for key in ("public_image_count", "public_image_bytes", "image_base64_bytes"):
                image_totals[key] += call.get(key, 0)
        for key, value in stats["python"].items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and key != "maximum_worker_peak_bytes":
                python_totals[key] += value
        bridges.append({"stage": stage, "route": route, "process_id": bridge["process_id"],
                        "process_metrics": bridge["process_metrics"], "closed": bridge["closed"]})
        sessions.append({
            "stage": stage, "route": route,
            "record": identity(folder / "CONSUMER.json"),
            "bridge_record": identity(folder / "bridge/BRIDGE_RESULT.json"),
            "wall_s": record["wall_s"], "usage": record["usage"],
            "tools": stats["tools"], "tool_names": stats["tool_names"],
            "tool_wall_s": stats["tool_wall_s"],
            "public_text_UTF8_bytes": stats["public_text_UTF8_bytes"],
            "input_prompt_UTF8_bytes": record["input_prompt_UTF8_bytes"],
            "output_text_UTF8_bytes": record["output_text_UTF8_bytes"],
            "image_delivery": stats["images"], "python": stats["python"],
            "facts_wall_s": stats["facts_wall_s"],
            "facts_text_UTF8_bytes": stats["facts_text_UTF8_bytes"],
            "readback_Blender": stats["API"], "cleanup": stats["cleanup"],
            "fees": record["fees"],
        })
    jobs = []
    for path in sorted(HERE.glob("private/jobs/*/run.json")):
        record = json.loads(path.read_bytes())
        jobs.append({"record": identity(path), "script": record["script"]["path"],
                     "wall_s": record["wall_s"], "process": process_fields(record["process"])})
    roots = []
    for path in sorted(HERE.glob("private/processes/*.json")):
        record = json.loads(path.read_bytes())
        if "command" in record and not path.name.startswith("b_"):
            roots.append({"record": identity(path), **process_fields(record)})
    evidence_names = [
        "CASE_BINDING.json", "IMAGE_BINDING.json", "QUALITY_PREFLIGHT.json",
        "FACTS_DELIVERY_PREFLIGHT.json", "FACTS_DESCRIPTOR_CHECKS.json",
        "OPTIMIZATION_PREFLIGHT.json", "private/consumer_preflight/RUNS.json",
        "private/api_preflight/RUNS.json", "private/api_preflight/recovered_run02/DETAIL.json",
        "private/results/render_v1_SUMMARY.json", "private/results/render_v2_SUMMARY.json",
        "private/results/render_v1_PIXEL_VERIFICATION.json",
        "private/results/render_v2_PIXEL_VERIFICATION.json",
        "private/results/IMAGE_EVENT_SCHEMA_PREFLIGHT.json", "RESULT_VERIFICATION_all.json",
        "CONSUMER_STATS_v1.json", "CONSUMER_STATS_v2.json", "CONSUMER_STATS_all.json",
        "private/analysis/SELF_CHECK.json", "private/analysis/FINAL_VERIFICATION.json",
        "private/analysis/v1/history/001_summary.json",
        "private/analysis/v2_source_compatibility/CHECK_RESULT.json",
        "private/FINAL_SUPPORT_CHECK.json",
        "CONTOUR_COSTS.json",
    ]
    evidence = [{"record": identity(name), "metered": metered_fields(read(name))}
                for name in evidence_names]
    analysis = read("private/analysis/FINAL_VERIFICATION.json")
    local_deliveries = []
    for scope in ("api_preflight", "consumer_preflight"):
        calls = []
        for path in sorted((HERE / "private" / scope).rglob("COST.json")):
            record = json.loads(path.read_bytes())
            scalars = {key: value for key, value in record.items()
                       if isinstance(value, (str, int, float, bool)) or value is None}
            calls.append({"record": identity(path), **scalars})
        local_deliveries.append({
            "scope": scope, "calls": calls, "tool_calls": len(calls),
            "names": dict(Counter(row["name"] for row in calls)),
            "nested_tool_wall_s": sum(row.get("wall_s", 0) for row in calls),
            "PNG_blocks": sum(row.get("public_image_count", 0) for row in calls),
            "PNG_bytes": sum(row.get("public_image_bytes", 0) for row in calls),
            "base64_bytes": sum(row.get("image_base64_bytes", 0) for row in calls),
            "public_text_UTF8_bytes": sum(row.get("public_text_UTF8_bytes", 0) for row in calls),
            "stdio_response_UTF8_bytes": sum(row.get("stdio_response_UTF8_bytes", 0) for row in calls),
        })
    now = time.time()
    result = {
        "cycle_id": "M6-REFERENCE-CONSUME-002",
        "snapshot_UTC": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "end_to_end": {
            "start_epoch": TASK_STARTED_EPOCH,
            "start_source": "AL task registration write_version 41",
            "snapshot_epoch": now,
            "elapsed_through_this_cost_snapshot_s": now - TASK_STARTED_EPOCH,
            "scope": "Includes preparation, four consumers, review, code writing and waits through snapshot. Git commit and final callback occur afterward. Whole-task CPU and memory are unmeasured.",
        },
        "actual_Pro": {
            "started": len(sessions), "completed": len(sessions), "failed": 0,
            "requested_model": "gpt-6.1-sol", "requested_reasoning_effort": "medium",
            "resolved_provider_settings": None,
            "wall_s": sum(row["wall_s"] for row in sessions),
            "usage": dict(usage), "tool_calls": sum(row["tools"] for row in sessions),
            "fees": None,
            "usage_accounting": "Cached input is a subset of input tokens. Reasoning output is a subset of output tokens. Do not add these subsets again.",
            "sessions": sessions,
        },
        "actual_consumer_delivery": {
            "tool_totals": dict(tool_totals), "image_totals": dict(image_totals),
            "image_scope": "Complete server-to-active-CLI MCP ImageContent blocks. CLI JSON serializations middle-truncate image bodies at 1 MiB. Provider image encoding and resolution are unmeasured.",
            "initial_CLI_images": 0,
            "python_worker_totals": dict(python_totals),
            "maximum_python_worker_peak_bytes": max(row["python"]["maximum_worker_peak_bytes"] for row in sessions),
            "bridge_processes": bridges,
            "bridge_CPU_s": sum(row["process_metrics"]["CPU_s"] for row in bridges),
            "maximum_bridge_peak_bytes": max(row["process_metrics"]["peak_working_set_bytes"] for row in bridges),
            "cache_scope": "Packet cold creations and warm hits are per consumer session. Four formal sessions start independently. Token cache values are provider usage observations.",
        },
        "actual_Blender": {
            "calls": len(jobs), "by_script": dict(Counter(row["script"] for row in jobs)),
            "formal_consumer_edits": 0, "preflight_sparse_edits": 1,
            "all_exit_zero": all(row["process"]["returncode"] == 0 for row in jobs),
            "nested_job_wall_s": sum(row["wall_s"] for row in jobs),
            "nested_tree_CPU_s": sum(row["process"]["tree_cpu_s"] for row in jobs),
            "maximum_sampled_tree_peak_bytes": max(row["process"]["tree_sampled_peak_working_set_bytes"] for row in jobs),
            "jobs": jobs,
        },
        "monitored_numerical_roots": roots,
        "API_preflight_attempts_and_recovery": read("private/api_preflight/RUNS.json"),
        "local_consumer_preflight": read("private/consumer_preflight/RUNS.json"),
        "local_preflight_delivery": local_deliveries,
        "overlays": read("CONTOUR_COSTS.json"),
        "stage_costs": analysis["stage_costs"],
        "stage_comparison": analysis["stage_comparison"],
        "analysis_support_failures": analysis["support_attempts"],
        "review_support_failure": read("private/FINAL_SUPPORT_CHECK.json"),
        "process_cleanup": {"record": identity("private/PROCESS_CLEANUP.json"),
                            "observation": read("private/PROCESS_CLEANUP.json")},
        "metered_evidence": evidence,
        "accounting": [
            "Pro session wall includes bridge tools, Python workers and consumer Blender reads. Tool, executor, snapshot, worker and Blender durations are nested observations.",
            "API preflight attempt 02 includes its five Blender calls. Final result verifier includes its four fresh Blender calls. Do not add the job subset to enclosing roots.",
            "Render v2 SUMMARY contains cumulative four-session Blender wall. Use its per-invocation wall for v2, and count each unique job once for total Blender work.",
            "Result verifier and v2 rendering ran concurrently. Their wall durations are non-exclusive.",
            "Metered preparation and preflight script bodies sit inside launch wall. There is no additive grand total across nested timers.",
            "All four bridge closed flags retain false from the last per-call snapshot. Parent exits and separate process cleanup are recorded. No final closed=true receipt exists.",
        ],
        "unmeasured": [
            "Provider fees, internal request/retry count, resolved model settings and image preprocessing",
            "Whole Codex CLI process-tree CPU and RSS, whole-task CPU and RSS",
            "Some code-authoring, AST/import/source-inspection shell CPU and individual launch durations",
            "Manual image interpretation time, root and collaboration model token usage and fees",
            "Brief process descendants missed by the 50 ms process-tree sampler",
        ],
        "training": 0, "Google_API_calls": 0,
        "collector_wall_s": time.perf_counter() - started,
        "collector_parent_CPU_s": time.process_time() - parent_cpu,
    }
    write("COSTS.json", result)
    print(json.dumps({"Pro": result["actual_Pro"]["started"], "wall_s": result["actual_Pro"]["wall_s"],
                      "usage": dict(usage), "Blender": len(jobs), "images": dict(image_totals),
                      "elapsed_s": result["end_to_end"]["elapsed_through_this_cost_snapshot_s"]}))


def verify():
    started = time.perf_counter()
    checks = []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})

    def check_identity(name, expected):
        actual = identity(expected["path"])
        check(name, actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"])

    for row in read("PLAN_FREEZE.json")["files"]:
        check_identity("PLAN frozen " + row["path"], row)
    for stage, name in [("v1", "TOOL_FREEZE.json"), ("v2", "TOOL_FREEZE_v2.json")]:
        for row in read(name)["files"]:
            check_identity(stage + " archive " + row["path"], row["archived"])
            if row["path"] != "session_api.py":
                check_identity(stage + " current " + row["path"], row)
    selection = read("API_SELECTION.json")
    check("selected default V1", selection["default"] == "v1")
    check_identity("current API restored V1", selection["default_API"])
    for key in ("executed_v1_source", "executed_v2_source", "candidate_patch"):
        check_identity(key, selection[key])
    binding = read("OPTIMIZATION_BINDING.json")
    check_identity("immutable v1 analysis", binding["initial_analysis"])
    check_identity("immutable v1 tools", binding["initial_tools"])
    for row in binding["initial_results"]:
        for key in ("consumer", "session"):
            check_identity("immutable v1 " + row["route"] + " " + key, row[key])
    for row in read("CASE_BINDING.json")["originals"]:
        check_identity("original asset " + row["path"], row)
    case = read("CASE_BINDING.json")
    check("nonempty shared domain", case["F_points"] == 599 and case["editable_points"] == 347)
    totals = read("CONSUMER_STATS_all.json")["totals"]
    check("four real completed consumers", totals["sessions"] == totals["terminal_sessions"] == 4)
    check("36 complete bridge PNG blocks", totals["server_image_blocks"] == 36)
    check("four actual independent consumer reads", totals["independent_readbacks"] == 4)
    check("544 numeric claims", totals["numeric_claims_checked"] == totals["numeric_claims_verified"] == 544)
    check("four concrete no-edit decisions", totals["modification_decisions"] == {"no_edit": 4})
    for row in read("CONSUMER_STATS_all.json")["sessions"]:
        label = row["stage"] + " " + row["route"]
        check(label + " actual zero-change saved file", row["actual_saved_copy_verified"] and row["changed_vertices"] == 0)
        check(label + " technical QA", row["technical_status"] == "pass")
        check(label + " geometric improvement unestablished", not any(row["geometry_improvement_established"].values()))
    check("fresh Blender verification pass", read("RESULT_VERIFICATION_all.json")["status"] == "pass")
    check("contour evidence pass", read("private/contour_audit/VERIFICATION.json")["status"] == "pass")
    check("analysis final verification pass", read("private/analysis/FINAL_VERIFICATION.json")["status"] == "pass")
    cleanup = read("private/PROCESS_CLEANUP.json")
    check("owned consumer and bridge processes absent", cleanup["query_succeeded"] and cleanup["owned_process_count"] == 0)
    check("all 17 actual Blender exits zero", read("COSTS.json")["actual_Blender"]["calls"] == 17 and read("COSTS.json")["actual_Blender"]["all_exit_zero"])
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        check("AST " + path.name, True)
    result = {"status": "pass" if all(row["pass"] for row in checks) else "fail",
              "checks_passed": sum(row["pass"] for row in checks), "checks_total": len(checks),
              "checks": checks, "wall_s": time.perf_counter() - started,
              "API_selection": selection["default_API"],
              "historical_result_snapshot": "RESULT_VERIFICATION_all current_exact fields describe its pre-restoration snapshot. Final current source is checked against API_SELECTION V1 here.",
              "additional_Pro": 0, "additional_Blender": 0}
    write("FINAL_VERIFICATION.json", result)
    print(json.dumps({key: result[key] for key in ("status", "checks_passed", "checks_total", "wall_s")}))
    if result["status"] != "pass":
        raise SystemExit("Delivery verification failed")


def manifest():
    files = [identity(path) for path in sorted(HERE.rglob("*"))
             if path.is_file() and path.name not in {"MANIFEST.json", "HANDOFF.json"}]
    result = {"cycle_id": "M6-REFERENCE-CONSUME-002", "files": files,
              "file_count": len(files), "bytes": sum(row["bytes"] for row in files),
              "scope": "Every batch file, including private raw records. MANIFEST excludes itself and the ignored post-commit HANDOFF to avoid circular identity.",
              "local_private_artifacts": "Large blend, NPZ, PNG and complete RPC/consumer logs are retained at the recorded local paths and SHA256 identities. Public Git commit tracks the root delivery files.",
              "external_originals": read("CASE_BINDING.json")["originals"]}
    write("MANIFEST.json", result)
    print(json.dumps({"files": len(files), "bytes": result["bytes"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["costs", "verify", "manifest"])
    arguments = parser.parse_args()
    {"costs": costs, "verify": verify, "manifest": manifest}[arguments.action]()
