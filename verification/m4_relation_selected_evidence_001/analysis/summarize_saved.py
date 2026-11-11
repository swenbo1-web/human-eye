"""Summarize saved engineering analysis without starting runtime processes."""

import hashlib
import json
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
ANALYSIS = HERE / "run_02" / "RESULTS.json"


def distribution(values):
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "maximum": max(values) if values else None,
        "sum": sum(values),
    }


def save(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    raw = ANALYSIS.read_bytes()
    analysis = json.loads(raw)
    sessions = analysis["sessions"]
    rows = [row for session in sessions for row in session["rows"]]
    original_candidate = [
        session for session in sessions
        if session["case"]["role"] == "candidate" and not session["case"]["transformed"]
    ]
    comparisons = []
    engineering = []
    for session in original_candidate:
        by_label = {row["label"]: row for row in session["rows"]}
        for cycle in range(1, 6):
            off = by_label[f"warm_{cycle}_OFF"]
            for mode in ("vertices", "full"):
                selected = by_label[f"warm_{cycle}_{mode}"]
                comparisons.append({
                    "case_id": session["case"]["id"],
                    "cycle": cycle,
                    "mode": mode,
                    "entry_delta_ns": selected["entry_elapsed_ns"] - off["entry_elapsed_ns"],
                    "Peer_delta_ns": selected["Peer_elapsed_ns"] - off["Peer_elapsed_ns"],
                    "content_encode_inclusive_delta_ns": selected["content_encode_inclusive_ns"] - off["content_encode_inclusive_ns"],
                    "body_delta_utf8_bytes": selected["body_utf8_bytes"] - off["body_utf8_bytes"],
                    "geometry_value_bytes": selected["geometry_value_bytes"],
                })
        engineering.extend(session["engineering_FULL_comparisons"])
    mode_deltas = {}
    for mode in ("vertices", "full"):
        selected = [row for row in comparisons if row["mode"] == mode]
        mode_deltas[mode] = {
            field: distribution([row[field] for row in selected])
            for field in (
                "entry_delta_ns", "Peer_delta_ns", "content_encode_inclusive_delta_ns",
                "body_delta_utf8_bytes", "geometry_value_bytes",
            )
        }
    engineering_summary = {
        "comparison_count": len(engineering),
        "same_fields": "two selected objects, full current world vertices and triangles",
        "OFF_plus_native_entry_sum_ns": distribution([row["sum_entry_elapsed_ns"] for row in engineering]),
        "OFF_plus_native_pair_window_ns": distribution([row["pair_window_elapsed_ns"] for row in engineering]),
        "FULL_entry_ns": distribution([row["candidate_FULL_entry_elapsed_ns"] for row in engineering]),
        "paired_FULL_minus_OFF_plus_native_ns": distribution([row["FULL_minus_sequential_entry_sum_ns"] for row in engineering]),
        "OFF_plus_native_body_bytes": distribution([row["response_body_utf8_bytes"] for row in engineering]),
        "FULL_body_bytes": distribution([row["candidate_FULL_body_utf8_bytes"] for row in engineering]),
        "OFF_plus_native_worker_RPC": sorted({row["worker_received_RPC_count"] for row in engineering}),
        "FULL_worker_RPC": sorted({row["worker_received_RPC_count"] for session in original_candidate for row in session["rows"] if row["mode"] == "full" and row["label"].startswith("warm_")}),
    }
    oracle_rows = [row for row in rows if row["kind"] == "native_supplement" and row["oracle_retained"]]
    changes = [row for row in rows if row["kind"] == "registered_QA_change"]
    summary = {
        "cycle_id": analysis["cycle_id"],
        "analysis_result_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_script_sha256": analysis["analysis_script_sha256"],
        "summary_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "engineering_checks_passed": analysis["passed"],
        "check_count": analysis["check_count"],
        "failed_check_count": analysis["failed_check_count"],
        "unmeasured_checks": analysis["unmeasured_checks"],
        "frozen_source_pin_count": len(analysis["source_files_checked"]),
        "candidate_commit": analysis["candidate_commit"],
        "source_canonical": analysis["candidate_source_sha256"],
        "same_cycle_zero_extra_work_comparisons": sum(len(session["warm_work_comparisons"]) for session in sessions),
        "row_counts": {kind: sum(row["kind"] == kind for row in rows) for kind in ("relation", "native_supplement", "registered_QA_change")},
        "worker_received_RPC_total": sum(session["session_received_worker_RPC_total"] for session in sessions),
        "unassigned_control_worker_RPC_total": sum(len(session["unassigned_control_worker_events"]) for session in sessions),
        "product_stdio_record_total": sum(session["product_stdio_all_record_count"] for session in sessions),
        "session_wall_ns_total": sum(session["session_wall_ns"] for session in sessions),
        "QA_oracle_count": len(oracle_rows),
        "QA_oracle_entry_ns": distribution([row["entry_elapsed_ns"] for row in oracle_rows]),
        "QA_registered_change_entry_ns": distribution([row["entry_elapsed_ns"] for row in changes]),
        "QA_inclusion": "Eight oracle RPCs and one change RPC remain in all-worker/session totals. Seven unassigned close/control RPCs remain counted.",
        "mode_vs_same_cycle_OFF": mode_deltas,
        "same_field_FULL_vs_OFF_plus_native": engineering_summary,
        "schema_byte_delta": analysis["schema_descriptor_byte_delta"],
        "product_lifetime_peak_RSS_bytes": distribution([session["product_lifetime_peak_rss_max_bytes"] for session in sessions]),
        "default_latency_review": analysis["default_latency_review"],
        "admission": "Engineering counts pass. Default warm OFF latency preservation remains unproven and observed regression requires explicit root review. Independent numeric/rigid/source verification is recorded separately.",
        "limits": analysis["unmeasured"] + ["Direct bpy C-call profile channel", "Native tool schema descriptor freshly listed in these seven sessions"],
        "external_processes_started_by_analysis": 0,
        "new_runtime_measurements": 0,
    }
    save(HERE / "run_02" / "SUMMARY.json", summary)
    latency = summary["default_latency_review"]
    lines = [
        "# Saved engineering analysis",
        "",
        f"The saved-record checks passed with {analysis['check_count']} checks, zero failures and one optional unmeasured channel. All {len(analysis['source_files_checked'])} source pins matched.",
        "",
        f"The seven sessions contain {summary['row_counts']['relation']} relation requests, {summary['row_counts']['native_supplement']} native reads and one registered QA change. All {summary['worker_received_RPC_total']} received worker RPCs include eight oracle reads and seven close/control requests. Session wall time totals {summary['session_wall_ns_total']/1e9:.6f} seconds.",
        "",
        "## Preparation and kernel work",
        "",
        "All 42 same-cycle vertices/full versus OFF comparisons have zero extra received RPC, capture calls, resource builds, triangulation, world preparation, successful normalization/hash work or kernel/rank work. The six original cold sessions perform the same existing work. A geometry change rebuilds one changed resource and recomputes three pairs. FULL then reuses the new generation without additional preparation or solving.",
        "",
        "## Default latency",
        "",
        f"Baseline warm OFF has ten samples with median {latency['baseline']['entry_elapsed_ns']['median']/1e6:.5f} ms. Candidate warm OFF has twenty samples with median {latency['candidate']['entry_elapsed_ns']['median']/1e6:.5f} ms. The observed increase is {latency['median_candidate_minus_baseline_ns']['entry_elapsed_ns']/1e6:.3f} ms, or {latency['entry_median_change_percent']:.5f}%. Every original candidate session has a higher OFF median than either baseline session.",
        "",
        f"The host.capture median increases by {latency['median_candidate_minus_baseline_ns']['host_capture_inclusive_ns']/1e6:.5f} ms and the inclusive worker profile scope by {latency['median_candidate_minus_baseline_ns']['profile_scope_ns']/1e6:.5f} ms. The trace interval outside host.capture changes by {latency['median_candidate_minus_baseline_ns']['trace_outside_host_capture_ns']/1e6:.5f} ms. These overlapping scopes and their median differences describe the saved run. They do not establish a cause. Default latency preservation remains unproven. The frozen contract has no numeric tolerance to apply.",
        "",
        "## Same-field engineering route",
        "",
        f"Across twenty paired candidate cycles, FULL has median entry time {engineering_summary['FULL_entry_ns']['median']/1e6:.5f} ms. OFF plus the sequential native full-geometry read has median summed entry time {engineering_summary['OFF_plus_native_entry_sum_ns']['median']/1e6:.5f} ms. The median paired difference is {engineering_summary['paired_FULL_minus_OFF_plus_native_ns']['median']/1e6:.5f} ms. FULL uses one worker RPC while the sequential route uses two. Both carry two objects' world vertices and triangles.",
        "",
        "Original-state bodies are 5,361 bytes for OFF, 8,192 for vertices and 9,015 for FULL. OFF plus native bodies total 9,004 bytes. The relation tool descriptor grows by 563 bytes, and the nearest descriptor has zero byte change. Geometry field values occupy 2,819 bytes for vertices and 3,642 for FULL. Actual per-field sizes and per-request response envelopes remain in RESULTS.json.",
        "",
        "## Measurement limits",
        "",
        "mcp.content_encode includes relation projection and content preparation. Peer timing ends before its final receipt publication, while entry timing includes it. Product RSS records OS process-lifetime high-water marks. QA profiling remains active in every measured runtime request. Its callback-only overhead, worker OS peak, isolated allocations, pure JSON-only duration and model-task benefit are unmeasured. The direct C profiler is empty even when host residency counters show actual mesh work.",
        "",
        "The first analysis invocation had a QA-script syntax error before any input processing. Its source and stderr remain under history and attempt_01.stderr.txt. The corrected saved-only analysis is run_02. No runtime request was repeated.",
    ]
    with (HERE / "run_02" / "SUMMARY.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print(json.dumps({"summary": str(HERE / "run_02" / "SUMMARY.json"), "external_processes": 0}))


if __name__ == "__main__":
    main()
