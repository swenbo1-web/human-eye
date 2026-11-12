"""Independently reconcile the nine originals, sealed quality and cost gates."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
SEQUENCE = ("N1", "O1", "C1", "O2", "C2", "N2", "C3", "N3", "O3")


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator, "value": float(value)}


def main():
    original = read(BATCH / "DELIVERY_MANIFEST.json")
    assert original["file_count"] == len(original["files"]) == 2335
    for item in original["files"]:
        raw = (BATCH / item["path"]).read_bytes()
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"], item["path"]
    order = read(HERE / "WORK_ORDER.json")
    for item in order["inputs"]:
        raw = (HERE / item["local"]).read_bytes()
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    seal = read(HERE / "inputs/QUALITY_SEAL.json")
    answers = {item["anonymous_id"]: item for item in seal["answers"]}
    mapping = read(BATCH / "private/ANON_MAP.json")["rows"]
    assert tuple(item["cell"] for item in mapping) == SEQUENCE
    assert len(answers) == len(mapping) == 9
    rows = []
    for slot in mapping:
        folder = BATCH / "cells" / slot["cell"]
        consumer = read(folder / "CONSUMER.json")
        timing = read(folder / "CELL_FINAL_TIMING.json")
        quality = answers[slot["anonymous_id"]]
        assert sha((folder / "final.txt").read_bytes()) == quality["final_sha256"]
        assert (folder / "PUBLIC_FINAL.txt").read_bytes() == consumer["final"].encode("utf8")
        assert quality["final_content_classification"] == "complete_correct"
        assert consumer["status"] == quality["execution_state"]
        assert consumer["valid_completion"] == quality["consumer_valid_completion"]
        assert timing["within_570s"] and timing["owner_cleanup_confirmed"]
        assert timing["full_cell_wall_ns"] == timing["business_receipts_closed_ns"] - timing["cell_started_ns"]
        events = [json.loads(line) for line in (folder / "events.jsonl").read_bytes().splitlines()]
        raw_usage = [item["event"]["usage"] for item in events if item["event"].get("type") == "turn.completed"]
        assert len(raw_usage) == 1 and raw_usage == consumer["usage_rows"]
        assert raw_usage[0] == consumer["usage"]
        usage = raw_usage[0]
        assert usage["cached_input_tokens"] <= usage["input_tokens"]
        assert usage["reasoning_output_tokens"] <= usage["output_tokens"]
        assert consumer["bridge_cleanup"]["confirmed"] is None
        assert consumer["fees"] is None and consumer["provider_requests"] is None
        assert consumer["resolved_effort"] is None
        rows.append({
            "cell": slot["cell"], "group": slot["group"], "round": slot["round"],
            "anonymous_id": slot["anonymous_id"], "final_sha256": quality["final_sha256"],
            "content_quality": quality["final_content_classification"],
            "primary_quality": quality["primary_classification"],
            "execution_state": consumer["status"], "valid_completion": consumer["valid_completion"],
            "full_cell_wall_ns": timing["full_cell_wall_ns"], "prefix_ns": consumer["total_task_wall_ns"],
            "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            "input_plus_output_tokens": usage["input_tokens"] + usage["output_tokens"],
            "cached_input_tokens_subset": usage["cached_input_tokens"],
            "reasoning_output_tokens_subset": usage["reasoning_output_tokens"],
            "recorded_tool_attempts": len(consumer["tool_calls"]), "thread_id": consumer["thread_id"],
        })
    assert len({item["thread_id"] for item in rows}) == 9
    groups = {}
    for name in ("N", "O", "C"):
        selected = [item for item in rows if item["group"] == name]
        groups[name] = {
            "cells": [item["cell"] for item in selected], "final_content_correct": len(selected),
            "effective_complete_correct": sum(item["primary_quality"] == "complete_correct" for item in selected),
            "failed_cells": [item["cell"] for item in selected if not item["valid_completion"]],
            "full_wall_sum_ns": sum(item["full_cell_wall_ns"] for item in selected),
            "full_wall_median_ns": median(item["full_cell_wall_ns"] for item in selected),
            "input_tokens": sum(item["input_tokens"] for item in selected),
            "output_tokens": sum(item["output_tokens"] for item in selected),
            "input_plus_output_tokens": sum(item["input_plus_output_tokens"] for item in selected),
            "recorded_tool_attempts": sum(item["recorded_tool_attempts"] for item in selected),
        }
    by_cell = {item["cell"]: item for item in rows}
    comparisons = {}
    for baseline, threshold, inclusive in (("N", Fraction(7, 10), True), ("O", Fraction(1), False)):
        pairs = []
        exact_ratios = []
        for index in range(1, 4):
            candidate, reference = by_cell[f"C{index}"], by_cell[f"{baseline}{index}"]
            value = Fraction(candidate["full_cell_wall_ns"], reference["full_cell_wall_ns"])
            exact_ratios.append(value)
            pairs.append({"round": index, "candidate": candidate["cell"], "baseline": reference["cell"],
                          "wall_ratio": ratio(value), "wall_delta_ns": candidate["full_cell_wall_ns"] - reference["full_cell_wall_ns"],
                          "both_effective_complete_correct": candidate["primary_quality"] == reference["primary_quality"] == "complete_correct"})
        midpoint = median(exact_ratios)
        prerequisites = groups["C"]["effective_complete_correct"] == groups[baseline]["effective_complete_correct"] == 3
        time_condition = midpoint <= threshold if inclusive else midpoint < threshold
        token_condition = groups["C"]["input_plus_output_tokens"] <= groups[baseline]["input_plus_output_tokens"]
        comparisons["C_vs_" + baseline] = {
            "quality_execution_prerequisites_met": prerequisites,
            "formal_gate_pass": prerequisites and time_condition and token_condition,
            "formal_gate_status": "not_met_valid_completion_prerequisite" if not prerequisites else "passed" if time_condition and token_condition else "failed_cost_condition",
            "descriptive_scope": "All nine correct final contents; failed cells remain fully included, with no latency subtraction.",
            "paired_wall": pairs, "paired_wall_median": ratio(midpoint),
            "numeric_wall_condition": time_condition, "numeric_token_condition": token_condition,
            "total_token_ratio": ratio(Fraction(groups["C"]["input_plus_output_tokens"], groups[baseline]["input_plus_output_tokens"])),
        }
    result = {"schema": "tri_consumer_root_cost_reconciliation_v1", "original_content_files_preserved": 2335,
              "cells": rows, "groups": groups, "comparisons": comparisons,
              "quality_source": "Administrator seal; this script does not regrade answers.",
              "usage_scope": "Final reported cumulative turn usage; cached and reasoning are overlapping subsets; pre-reconnect provider accounting coverage is unconfirmed.",
              "new_Blender_model_API_runs": 0}
    (HERE / "ROOT_RECONCILIATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"groups": groups, "comparisons": comparisons}, ensure_ascii=False))


if __name__ == "__main__":
    main()
