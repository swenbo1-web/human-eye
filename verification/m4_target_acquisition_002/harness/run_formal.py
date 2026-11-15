"""Root-only, once-per-batch twelve-slot comparison after source-bound qualification."""

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
from run_case import load, request_sequence, run, verify_install


ORDER = [(asset, label) for asset in ("main", "target_only")
         for label in ("A1", "B1", "B2", "A2", "A3", "B3")]
PREREGISTRATION_SHA256 = "5013cc3402410dab014bff5b54c2c342f2146aa7c282332fb291174af920167e"
CASE_SOURCE_SHA256 = "107958fd211958a969a40dce39d6a19e3cb59325734b1075d7475e42cd573595"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(result, folder):
    main = next(row for row in result["requests"] if row["id"] == "target_observation")
    receipts = [load(path) for path in (folder / "stdio").glob("rpc_*/RECEIPT.json")]
    original = next(row for row in receipts if row.get("id") == "target_observation")
    return {"server_request_to_reply_ns": main["server_request_to_reply_ns"],
            "client_flush_to_received_ns": main["client_flush_to_received_ns"],
            "complete_client_call_ns": main["client_outer_including_recording_ns"],
            "client_pre_receipt_span_ns": original["closed_ns"] - original["started_ns"],
            "client_call_interval_scope": "original call and its finally receipt publication, measured by enclosing requests timestamps",
            "complete_session_ns": result["complete_session_ns"],
            "postrun_saved_validation_ns": result["postrun_validation_ns"],
            "raw_MCP_reply_bytes": main["raw_RX_bytes"], "public_text_UTF8_bytes": main["public_text_UTF8_bytes"],
            "image_blocks": main["image_blocks"],
            "raster_actual": next(row for row in result["io_audit"] if row["id"] == "target_observation").get("raster_actual")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-binding", type=Path, default=HERE.parent / "A_RUN_BINDING.json")
    parser.add_argument("--b-binding", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=Path("D:/he_m4_target_002/assets_01/ASSETS.json"))
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, default=HERE.parent / "PREREGISTRATION.json")
    parser.add_argument("--output", type=Path, default=Path("D:/he_m4_target_002/formal"))
    parser.add_argument("--ledger", type=Path, default=Path("D:/he_m4_target_002/budget"))
    args = parser.parse_args()
    external = Path("D:/he_m4_target_002").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(external):
        raise ValueError("formal_output_outside_frozen_batch")
    a, b = load(args.a_binding), load(args.b_binding)
    verify_install(a)
    verify_install(b)
    preregistration = load(args.preregistration)
    if (digest(args.preregistration) != PREREGISTRATION_SHA256
            or preregistration["formal_slots"] != 12 or preregistration["formal_repetitions"] != 1
            or digest(args.a_binding) != preregistration["A_binding_sha256"]
            or digest(args.assets) != preregistration["assets_manifest_sha256"]
            or digest(HERE / "run_case.py") != CASE_SOURCE_SHA256):
        raise ValueError("frozen_preregistration_A_assets_or_case_changed")
    schedule = preregistration["formal_schedule"]
    if [(row["input"], row["variant"] + str(row["pair"])) for row in schedule] != ORDER:
        raise ValueError("formal_order_differs_from_frozen_preregistration")
    gate = load(args.qualification)
    if (gate.get("formal_allowed") is not True or gate.get("A_source_sha256") != a["source_sha256"]
            or gate.get("B_source_sha256") != b["source_sha256"]
            or gate.get("assets_manifest_sha256", gate.get("assets_sha256")) != digest(args.assets)):
        raise ValueError("root_qualification_not_bound_to_current_sources_assets")
    pins = gate.get("qualification_evidence_pins")
    if not isinstance(pins, list) or not pins:
        raise ValueError("root_qualification_evidence_pins_required")
    for pin in pins:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("qualification_evidence_changed")
    for name, expected in gate.get("harness_sha256", {}).items():
        if digest(HERE / name) != expected:
            raise ValueError("qualified_formal_harness_source_changed")
    assets = {row["name"]: row for row in load(args.assets)["inputs"]}
    budget = Budget(args.ledger)
    counts = budget.snapshot()["counts"]
    if (counts["Blender_start_attempts"] + 12 > 24 or counts["formal_raster_upper"] != 0
            or counts["all_raster_upper"] + 72 > 120):
        raise RuntimeError("remaining_frozen_formal_budget_insufficient")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    intent = {"schema": "m4-selective-002-formal-once-v1", "started_ns": started, "order": ORDER,
              "formal_schedule": schedule, "preregistration_sha256": digest(args.preregistration),
              "A_binding_sha256": digest(args.a_binding), "B_binding_sha256": digest(args.b_binding),
              "A_source_sha256": a["source_sha256"], "B_source_sha256": b["source_sha256"],
              "assets_sha256": digest(args.assets), "qualification_sha256": digest(args.qualification),
              "requests_per_input": {name: request_sequence(assets[name]["target"]) for name in ("main", "target_only")},
              "harness_sources": [{"path": str(path), "sha256": digest(path)} for path in sorted(HERE.rglob("*.py"))],
              "formal_slots": 12, "retries": 0, "replacement_samples": 0}
    save(external / "FORMAL_ONCE.json", intent)
    save(output / "INTENT.json", intent)
    results = []
    dispatches = []
    for slot in schedule:
        asset_name, label, variant = slot["input"], slot["label"], slot["variant"]
        folder = output / label
        dispatched = {"asset": asset_name, "label": label, "variant": variant, "pair": slot["pair"], "output": str(folder)}
        dispatches.append(dispatched)
        try:
            result = run(binding_path=args.a_binding if variant == "A" else args.b_binding,
                         asset=assets[asset_name], output=folder, ledger=args.ledger,
                         phase="formal", label=label, variant=variant)
            summary = summarize(result, folder) if result["passed"] else None
            results.append({"asset": asset_name, "label": label, "passed_operationally": result["passed"],
                            "variant": variant, "pair": slot["pair"],
                            "result": str(folder / "RESULT.json"), "result_sha256": digest(folder / "RESULT.json"),
                            "metrics": summary})
        except BaseException as error:
            dispatched["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            save(output / "DISPATCH_FAILURE.json", dispatched)
            break
    gates = {}
    for name in ("main", "target_only"):
        rows = {row["variant"] + str(row["pair"]): row for row in results if row["asset"] == name}
        if len(rows) != 6 or any(row["metrics"] is None for row in rows.values()):
            gates[name] = {"status": "not_evaluable_failed_or_missing_slots"}
            continue
        pairs = [{"pair": index, "A": rows["A" + str(index)]["metrics"],
                  "B": rows["B" + str(index)]["metrics"]} for index in (1, 2, 3)]
        server_ratios = [pair["B"]["server_request_to_reply_ns"] / pair["A"]["server_request_to_reply_ns"] for pair in pairs]
        session_ratios = [pair["B"]["complete_session_ns"] / pair["A"]["complete_session_ns"] for pair in pairs]
        server_median = statistics.median(server_ratios)
        session_median = statistics.median(session_ratios)
        faster = sum(ratio < 1 for ratio in server_ratios)
        server_limit = .90 if name == "main" else 1.05
        gates[name] = {"status": "timing_only_independent_quality_pending", "pairs": pairs,
                       "server_paired_B_over_A": server_ratios, "server_paired_median": server_median,
                       "session_paired_B_over_A": session_ratios, "session_paired_median": session_median,
                       "server_limit": server_limit, "server_B_faster_pairs": faster,
                       "timing_gate_passed": server_median <= server_limit and
                           (name != "main" or faster >= 2 and session_median <= 1)}
    record = {"schema": "m4-selective-002-formal-results-v1", "started_ns": started,
              "closed_before_publication_ns": time.perf_counter_ns(), "planned_slots": 12,
              "dispatches": dispatches, "results": results, "remaining_not_dispatched": schedule[len(dispatches):],
              "retries": 0, "replacement_samples": 0, "timing_gates": gates,
              "quality": "root must verify all original outputs; timing gates do not establish quality",
              "budget": budget.snapshot(), "experimental_model_tokens_and_cost": "not_run",
              "coordinator_reviewer_cost": None}
    save(output / "RESULT.json", record)
    print(json.dumps({"output": str(output), "dispatched": len(dispatches), "retries": 0,
                      "timing_gates": {name: row.get("timing_gate_passed") for name, row in gates.items()}, "quality": "pending"}))


if __name__ == "__main__":
    main()
