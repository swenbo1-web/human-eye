"""Reconcile sealed originals and the frozen cost gates without live execution."""

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
DELIVERY = "e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3"
SEQUENCE = ("N1", "P1", "P2", "N2", "N3", "P3")


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ratio_record(value):
    return {"numerator": value.numerator, "denominator": value.denominator,
            "decimal": float(value)}


def main():
    manifest_path = BATCH / "DELIVERY_MANIFEST.json"
    original_manifest = subprocess.check_output(
        ["git", "show", f"{DELIVERY}:verification/m4_surface_scan_consumption_001/DELIVERY_MANIFEST.json"],
        cwd=ROOT,
    )
    assert manifest_path.read_bytes() == original_manifest
    manifest = read(manifest_path)
    assert manifest["file_count"] == len(manifest["files"]) == 1974
    for row in manifest["files"]:
        data = (ROOT / row["path"]).read_bytes()
        assert len(data) == row["bytes"], row["path"]
        assert digest(data) == row["sha256"], row["path"]

    order = read(HERE / "WORK_ORDER.json")
    for row in order["inputs"]:
        data = (HERE / row["copied_to"]).read_bytes()
        assert len(data) == row["bytes"] and digest(data) == row["sha256"]
    seal = read(HERE / "inputs/QUALITY_SEAL.json")
    sealed = {row["anonymous_id"]: row for row in seal["answers"]}
    mapping = read(BATCH / "private/ANON_MAP.json")["rows"]
    assert tuple(row["cell"] for row in mapping) == SEQUENCE
    assert len(sealed) == len(mapping) == 6

    rows = []
    for slot in mapping:
        cell = slot["cell"]
        folder = BATCH / "cells" / cell
        consumer = read(folder / "CONSUMER.json")
        final_timing = read(folder / "CELL_FINAL_TIMING.json")
        assert final_timing["full_cell_wall_ns"] == (
            final_timing["business_receipts_closed_ns"] - final_timing["cell_started_ns"]
        )
        assert final_timing["within_570s"] is True
        assert final_timing["owner_cleanup_confirmed"] is True
        assert consumer["total_task_wall_ns"] < final_timing["full_cell_wall_ns"]
        assert digest((folder / "final.txt").read_bytes()) == sealed[slot["anonymous_id"]]["answer_sha256"]
        assert sealed[slot["anonymous_id"]]["status"] == "complete_correct"

        events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf8").splitlines()]
        usage_events = [event["event"]["usage"] for event in events if event["event"]["type"] == "turn.completed"]
        assert len(usage_events) == 1
        assert usage_events[-1] == consumer["usage"]
        assert consumer["usage_rows"] == usage_events
        completed = [event for event in events
                     if event["event"].get("type") == "item.completed"
                     and event["event"].get("item", {}).get("type") == "mcp_tool_call"]
        assert len(completed) == len(consumer["tool_calls"])
        started_ids = [event["event"]["item"]["id"] for event in events
                       if event["event"].get("type") == "item.started"
                       and event["event"].get("item", {}).get("type") == "mcp_tool_call"]
        assert set(started_ids) == {event["event"]["item"]["id"] for event in completed}
        assert len(started_ids) == len(set(started_ids))
        assert consumer["bridge_cleanup"]["confirmed"] is None
        assert consumer["bridge_cleanup"]["missing_exit_count"] == 1
        assert consumer["provider_requests"] is None
        assert consumer["resolved_effort"] is None
        assert consumer["fees"] is None
        usage = consumer["usage"]
        rows.append({
            "cell": cell, "group": slot["group"], "round": slot["round"],
            "anonymous_id": slot["anonymous_id"], "quality": sealed[slot["anonymous_id"]]["status"],
            "full_cell_wall_ns": final_timing["full_cell_wall_ns"],
            "prefix_ns": consumer["total_task_wall_ns"],
            "final_accounting_tail_ns": final_timing["full_cell_wall_ns"] - consumer["total_task_wall_ns"],
            "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            "input_plus_output_tokens": usage["input_tokens"] + usage["output_tokens"],
            "cached_input_tokens_subset": usage["cached_input_tokens"],
            "reasoning_output_tokens_subset": usage["reasoning_output_tokens"],
            "tool_attempts": len(completed),
            "tool_names": dict(Counter(event["event"]["item"]["tool"] for event in completed)),
            "thread_id": consumer["thread_id"],
        })

    assert len({row["thread_id"] for row in rows}) == 6
    by_cell = {row["cell"]: row for row in rows}
    pairs = []
    for index in range(1, 4):
        native, plugin = by_cell[f"N{index}"], by_cell[f"P{index}"]
        ratio = Fraction(plugin["full_cell_wall_ns"], native["full_cell_wall_ns"])
        pairs.append({"round": index, "native": native["cell"], "plugin": plugin["cell"],
                      "wall_ratio": ratio_record(ratio),
                      "wall_delta_ns": plugin["full_cell_wall_ns"] - native["full_cell_wall_ns"]})
    ratios = [Fraction(row["wall_ratio"]["numerator"], row["wall_ratio"]["denominator"]) for row in pairs]
    paired_median = median(ratios)
    groups = {}
    for group in ("N", "P"):
        selected = [row for row in rows if row["group"] == group]
        groups[group] = {
            "cells": [row["cell"] for row in selected], "complete_correct": len(selected),
            "full_wall_sum_ns": sum(row["full_cell_wall_ns"] for row in selected),
            "full_wall_median_ns": median(row["full_cell_wall_ns"] for row in selected),
            "input_tokens": sum(row["input_tokens"] for row in selected),
            "output_tokens": sum(row["output_tokens"] for row in selected),
            "input_plus_output_tokens": sum(row["input_plus_output_tokens"] for row in selected),
            "tool_attempts": sum(row["tool_attempts"] for row in selected),
        }
    quality_gate = all(group["complete_correct"] == 3 for group in groups.values())
    time_gate = paired_median <= Fraction(7, 10)
    token_gate = groups["P"]["input_plus_output_tokens"] <= groups["N"]["input_plus_output_tokens"]
    result = {
        "schema": "m4_surface_scan_cost_root_reconciliation_v1", "original_content_files_verified": 1974,
        "original_manifest_verified_against_commit": DELIVERY,
        "root_cost_input_files_verified": len(order["inputs"]), "six_original_cells": rows,
        "groups": groups, "paired_full_wall": pairs,
        "median_paired_full_wall_ratio": ratio_record(paired_median),
        "token_ratio": ratio_record(Fraction(groups["P"]["input_plus_output_tokens"], groups["N"]["input_plus_output_tokens"])),
        "gate": {"quality": quality_gate, "paired_wall_median_le_0_70": time_gate,
                 "plugin_total_tokens_le_native": token_gate,
                 "same_quality_net_benefit": quality_gate and time_gate and token_gate},
        "usage_semantics": "Final cumulative input+output per cell; cached input and reasoning output remain overlapping subsets.",
        "unmeasured": ["actual resolved model/version/effort", "provider input rendering", "thin-client EXIT receipts",
                       "cash fees/subscription debits", "complete preparation/coordinator cost"],
        "live_execution_count": {"Blender": 0, "model_consumer": 0, "business_API": 0},
    }
    path = HERE / "ROOT_RECONCILIATION.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"output": str(path), "original_files": 1974, "gate": result["gate"],
                      "paired_median": float(paired_median), "groups": groups}, ensure_ascii=False))


if __name__ == "__main__":
    main()
