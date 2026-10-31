"""Aggregate a completed blind scoring file; reveal labels only on explicit flag."""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--reveal", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    scores = json.loads((run/"blind_scores.json").read_text(encoding="utf-8"))
    manifest = json.loads((run/"private/generation_manifest.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["artifact_sha256"].items():
        if hashlib.sha256((run/relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Frozen input was modified: {relative}")
    protocol = json.loads((run/"protocol.json").read_text(encoding="utf-8"))
    mapping = json.loads((run/"private/trial_map.json").read_text(encoding="utf-8"))
    cases = {c["scene_id"]: c for c in json.loads((run/"private/cases.json").read_text(encoding="utf-8"))}
    expected_trials = len(mapping)
    expected_scenes = len(cases)
    if (not scores["complete"] or len(scores["results"]) != expected_trials) and not args.allow_incomplete:
        raise RuntimeError(f"All {expected_trials} responses must be scored before aggregation or unblinding")
    results = {r["trial_id"]: r for r in scores["results"]}
    complete_scenes = {
        scene_id for scene_id in cases
        if sum(1 for t in mapping if t["scene_id"] == scene_id and t["trial_id"] in results) == 2
    }
    active_mapping = [t for t in mapping if t["scene_id"] in complete_scenes] if args.allow_incomplete else mapping
    unpaired_records = [
        {"trial_id": t["trial_id"], "scene_id": t["scene_id"], "condition": t["condition"], "result": results[t["trial_id"]]}
        for t in mapping if t["trial_id"] in results and t["scene_id"] not in complete_scenes
    ]
    expected_scenes = len(complete_scenes) if args.allow_incomplete else expected_scenes
    expected_trials = len(active_mapping) if args.allow_incomplete else expected_trials
    primary_cfg = protocol.get("primary_endpoint", {"control": "raw.success", "plugin": "assisted.success"})
    experiment_mode = protocol.get("experiment_mode", "full_product")
    # A deterministic arbitrary label assignment, separate from participant IDs.
    label_key = {"control": "Group X", "plugin": "Group Y"}
    if int(hashlib.sha256((run/"protocol.json").read_bytes()).hexdigest()[-1], 16) % 2:
        label_key = {"control": "Group Y", "plugin": "Group X"}
    rows = []
    for trial in active_mapping:
        result = results[trial["trial_id"]]
        condition = trial["condition"]
        endpoint_spec = str(primary_cfg.get(condition, "raw.success"))
        metric = result["assisted"] if endpoint_spec.startswith("assisted") else result["raw"]
        rows.append({"trial_id": trial["trial_id"], "scene_id": trial["scene_id"],
                     "category": cases[trial["scene_id"]]["category"], "group": label_key[condition],
                     "primary_endpoint": endpoint_spec,
                     "valid_action": result["valid_action"], "success": bool(metric["success"]),
                     "penetrating": metric.get("penetrating"),
                     "bottom_face_rms_mm": metric.get("bottom_face_rms_mm"),
                     "rotation_error_deg": metric.get("rotation_error_deg"),
                     "tangential_drift_mm": metric.get("tangential_drift_mm"),
                     "raw_success": bool(result["raw"]["success"]),
                     "assisted_success": bool(result["assisted"]["success"]),
                     "assistance_changed_action": result["assisted"].get("action_changed", False)})
    groups = {}
    for group in ("Group X", "Group Y"):
        selected = [r for r in rows if r["group"] == group]
        assert len(selected) == expected_scenes
        summary = {"trials": len(selected), "successes": sum(r["success"] for r in selected),
                   "invalid_answers": sum(not r["valid_action"] for r in selected),
                   "terminal_collisions": sum(r["penetrating"] is True for r in selected),
                   "raw_successes": sum(r["raw_success"] for r in selected),
                   "assisted_successes": sum(r["assisted_success"] for r in selected),
                   "changed_actions": sum(r["assistance_changed_action"] for r in selected)}
        summary["success_rate_pct"] = round(summary["successes"] / len(selected)*100, 2)
        for key in ("bottom_face_rms_mm", "rotation_error_deg", "tangential_drift_mm"):
            values = [r[key] for r in selected if r[key] is not None]
            summary["median_"+key] = statistics.median(values) if values else None
        summary["by_category"] = {category: {"successes": sum(r["success"] for r in selected if r["category"] == category),
                                               "trials": sum(r["category"] == category for r in selected)}
                                  for category in sorted({r["category"] for r in selected})}
        groups[group] = summary
    paired = collections.Counter()
    for scene in (complete_scenes if args.allow_incomplete else cases):
        pair = {r["group"]: r["success"] for r in rows if r["scene_id"] == scene}
        assert len(pair) == 2
        key = "both" if all(pair.values()) else ("neither" if not any(pair.values()) else "only_"+next(k for k,v in pair.items() if v))
        paired[key] += 1
    blind = {"experiment_mode": experiment_mode, "primary_endpoint": primary_cfg,
             "complete": bool(scores["complete"]), "scored_trials_total": len(scores["results"]),
             "missing_trials": scores.get("missing", []),
             "groups": groups, "paired": dict(paired), "criteria": scores["scoring_limits"],
             "trials": expected_trials, "scenes": expected_scenes, "token_usage_available": False,
             "records": rows, "protocol_sha256": hashlib.sha256((run/"protocol.json").read_bytes()).hexdigest(),
             "wall_time_from_protocol_freeze_to_last_response_s": max((run/"responses"/(r["trial_id"]+".json")).stat().st_mtime for r in rows)-protocol["registered_at_utc_epoch"]}
    if args.reveal and unpaired_records:
        blind["unpaired_records_revealed"] = unpaired_records
    (run/"cohort_summary_blind.json").write_text(json.dumps(blind, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if args.reveal:
        blind["reveal_key"] = label_key
        blind["model_configuration"] = protocol["participant_model_configuration"]
        (run/"results_revealed.json").write_text(json.dumps(blind, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        inverse = {value:key for key,value in label_key.items()}
        with (run/"results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[*rows[0], "condition"])
            writer.writeheader()
            writer.writerows({**row,"condition":inverse[row["group"]]} for row in rows)
    print(json.dumps({"groups":groups,"paired":dict(paired),"revealed":args.reveal,
                      **({"reveal_key":label_key} if args.reveal else {})}))


if __name__ == "__main__":
    main()
