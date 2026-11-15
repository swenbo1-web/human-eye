"""One root-invoked, twelve-slot A/B engineering matrix after frozen qualification."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import Budget, save
from run_case import load, request, run, verify_install


SCHEDULE = [(name, arm) for name in ("peripheral", "focal_only")
            for arm in ("A1", "B1", "B2", "A2", "A3", "B3")]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timings(result):
    rows = [row for row in result.get("io_audit", []) if row.get("id") == "target_observation"]
    if len(rows) != 1:
        return None
    row = rows[0]
    return {"business_ns": row["request_to_reply_ns"], "session_ns": result["complete_session_ns"],
            "client_outer_ns": result["requests"][0]["client_outer_including_recording_ns"],
            "raster_actual": row.get("raster_actual"), "MCP_TX_bytes": row["TX_bytes"],
            "MCP_RX_bytes": row["RX_bytes"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-binding", type=Path, required=True)
    parser.add_argument("--b-binding", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("D:/he_m4_target_001/formal"))
    parser.add_argument("--ledger", type=Path, default=Path("D:/he_m4_target_001/budget"))
    args = parser.parse_args()
    external = Path("D:/he_m4_target_001").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(external):
        raise ValueError("formal_output_outside_batch")
    a, b = load(args.a_binding), load(args.b_binding)
    verify_install(a)
    verify_install(b)
    qualification = load(args.qualification)
    if (qualification.get("formal_allowed") is not True
            or qualification.get("A_source_sha256") != a["source_sha256"]
            or qualification.get("B_source_sha256") != b["source_sha256"]
            or qualification.get("assets_sha256") != digest(args.assets)):
        raise ValueError("root_frozen_qualification_not_bound_to_this_matrix")
    pins = qualification.get("qualification_evidence_pins")
    if not isinstance(pins, list) or not pins:
        raise ValueError("frozen_qualification_evidence_required")
    for pin in pins:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("qualification_evidence_changed")
    assets = {row["name"]: row for row in load(args.assets)["inputs"]}
    budget = Budget(args.ledger)
    counts = budget.snapshot()["counts"]
    if (counts["Blender_start_attempts"] + 12 > 24 or counts["formal_raster_upper"]
            or counts["all_raster_upper"] + 72 > 120):
        raise RuntimeError("insufficient_unchanged_formal_budget")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    intent = {"schema": "m4-target-formal-once-v1", "started_ns": started,
              "schedule": SCHEDULE, "A_source_sha256": a["source_sha256"],
              "B_source_sha256": b["source_sha256"], "assets_sha256": digest(args.assets),
              "qualification_sha256": digest(args.qualification), "output": str(output),
              "request_templates": {name: request(assets[name]["target"]) for name in ("peripheral", "focal_only")},
              "harness_sources": [{"path": str(path), "sha256": digest(path)}
                                  for path in sorted(HERE.rglob("*.py"))],
              "retry_policy": "one dispatch per slot; no retry, replacement or extra sample"}
    # One batch-wide exclusive marker, independent of a chosen output directory.
    save(external / "FORMAL_ONCE.json", intent)
    save(output / "INTENT.json", intent)
    results = []
    fatal = None
    for name, arm in SCHEDULE:
        path = output / (name + "_" + arm)
        binding_path = args.a_binding if arm.startswith("A") else args.b_binding
        try:
            case = run(binding_path=binding_path, asset=assets[name], output=path,
                       ledger=args.ledger, phase="formal", label=name + "_" + arm)
            results.append({"asset": name, "arm": arm, "path": str(path),
                            "passed_operationally": case["passed"], "timings": timings(case),
                            "result_sha256": digest(path / "RESULT.json")})
        except BaseException as error:
            fatal = {"asset": name, "arm": arm, "type": type(error).__name__,
                     "message": str(error), "traceback": traceback.format_exc()}
            save(output / "DISPATCH_FAILURE.json", fatal)
            break
    gates = {}
    for name in ("peripheral", "focal_only"):
        selected = {row["arm"]: row for row in results if row["asset"] == name}
        if len(selected) != 6 or any(not row["passed_operationally"] or row["timings"] is None for row in selected.values()):
            gates[name] = {"status": "not_evaluable_incomplete_or_failed_slots"}
            continue
        pairs = [{"pair": i, "A": selected["A" + str(i)]["timings"],
                  "B": selected["B" + str(i)]["timings"]} for i in (1, 2, 3)]
        ratios = [row["B"]["business_ns"] / row["A"]["business_ns"] for row in pairs]
        session_a = statistics.median(row["A"]["session_ns"] for row in pairs)
        session_b = statistics.median(row["B"]["session_ns"] for row in pairs)
        threshold = .90 if name == "peripheral" else 1.05
        faster_pairs = sum(ratio < 1 for ratio in ratios)
        timing_passed = (statistics.median(ratios) <= threshold and
                         (name != "peripheral" or faster_pairs >= 2 and session_b <= session_a))
        gates[name] = {"status": "engineering_timings_only_quality_pending", "pairs": pairs,
                       "paired_business_B_over_A": ratios,
                       "paired_business_median_B_over_A": statistics.median(ratios),
                       "paired_business_threshold": threshold,
                       "business_threshold_passed": statistics.median(ratios) <= threshold,
                       "B_faster_pairs": faster_pairs,
                       "timing_gates_passed": timing_passed,
                       "complete_session_A_median_ns": session_a,
                       "complete_session_B_median_ns": session_b,
                       "complete_session_B_not_above_A": session_b <= session_a}
    result = {"started_ns": started, "closed_before_publication_ns": time.perf_counter_ns(),
              "dispatched_slots": len(results) + (fatal is not None), "planned_slots": 12,
              "remaining_not_dispatched": SCHEDULE[len(results) + (fatal is not None):],
              "formal_retries": 0, "replacement_samples": 0, "results": results,
              "fatal_dispatch_failure": fatal, "engineering_time_gates": gates,
              "quality": "independent postrun comparison required before any acceptance decision",
              "budget": budget.snapshot(), "experiment_model_tokens_and_cost": "not_run",
              "coordinator_reviewer_model_usage_and_cash": None}
    save(output / "MATRIX.json", result)
    print(json.dumps({"output": str(output), "dispatched_slots": result["dispatched_slots"],
                      "formal_retries": 0, "quality": "pending"}))


if __name__ == "__main__":
    main()
