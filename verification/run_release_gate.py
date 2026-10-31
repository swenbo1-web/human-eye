"""Reproducible release gate: frozen evidence, locked answers and live contracts.

Creates a new evidence directory and never writes into an old trial or package.
No model requests, cloud upload, Blender connection, or package creation occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from verification.release_gate_helpers import (
    REPAIR_SCENES, analytical_case, analytical_exact_target_action, checked_inventory,
    evaluate_case, json_file, preservation_checks, sha, source_manifest, strict_candidate_penetrates)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def create_output(path):
    path = Path(path).resolve()
    allowed = (ROOT / "verification/fixes", ROOT / "verification/release_runs")
    if not any(path.is_relative_to(base) and path != base for base in allowed):
        raise ValueError("Output must be a new descendant of verification/fixes or verification/release_runs")
    path.mkdir(parents=True, exist_ok=False)
    return path


def replay_locked_answers(output):
    destination = output / "locked_answer_replay"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-B", str(ROOT / "verification/replay_alignment_fix.py"),
        "--output-dir", str(destination)], cwd=ROOT, env=env, capture_output=True,
        encoding="utf-8", errors="replace", timeout=180)
    (output / "locked_answer_replay.stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / "locked_answer_replay.stderr.log").write_text(result.stderr, encoding="utf-8")
    data = json_file(destination / "replay_results.json") if (destination / "replay_results.json").is_file() else {}
    summary = data.get("summary", {})
    passed = (result.returncode == 0 and summary.get("plugin_replayed_successes") == 30
        and summary.get("plugin_trials") == 30 and summary.get("plugin_replayed_terminal_collisions") == 0
        and summary.get("canonical_assisted_successes") == 30
        and summary.get("canonical_raw_successes") == 30 and not summary.get("regressions")
        and set(summary.get("repaired_scenes", [])) == REPAIR_SCENES)
    return {"passed": passed, "returncode": result.returncode,
            "evaluation_kind": "locked_historical_answers_not_new_model_trials",
            "summary": summary}, data


def repaired_cross_entry(output, replay):
    original = ROOT / "verification/blind_test/runs/20261021_01"
    cases = {case["scene_id"]: case for case in json_file(original / "private/cases.json")}
    source_rows = [row for row in replay.get("replayed_answers", [])
                   if row.get("condition") == "plugin" and row["scene_id"] in REPAIR_SCENES]
    rows = []
    for replay_row in source_rows:
        corrected = replay_row["assisted"]["applied_action"]
        action = {"focal_id": "part_1", "reference_id": "part_0",
                  "rotation_euler_deg": corrected["rotation_euler_deg_xyz"],
                  "translation": corrected["translation_xyz_m"]}
        strict_penetration = strict_candidate_penetrates(cases[replay_row["scene_id"]], corrected)
        for entry in ("guarded_runtime", "live_service", "live_mcp"):
            row = evaluate_case(output / (replay_row["scene_id"] + "_" + entry),
                cases[replay_row["scene_id"]], action, entry=entry,
                expected_task=not strict_penetration, expected_execution=not strict_penetration)
            row.update(scene_id=replay_row["scene_id"], trial_id=replay_row["trial_id"],
                evaluation_kind="locked_answer_corrected_action_cross_entry_replay",
                model_original_action=replay_row["raw"]["applied_action"],
                model_original_joint_task=replay_row["raw"],
                engine_recommendation=replay_row["assisted"]["fused_arguments"],
                legacy_controller_actual_action=corrected,
                independently_detected_strict_penetration=strict_penetration,
                legacy_controller_joint_task=replay_row["assisted"])
            rows.append(row)
            # Legacy controller rounds translations to 0.1 mm. Four accepted
            # historical answers penetrate 2-36 micrometres and must be rejected
            # by the strict live gate. A separate full-precision fixture answer
            # demonstrates reachability; never relabel it as the model's answer.
            exact = evaluate_case(output / (replay_row["scene_id"] + "_exact_" + entry),
                cases[replay_row["scene_id"]], analytical_exact_target_action(cases[replay_row["scene_id"]]),
                entry=entry, expected_task=True)
            exact.update(scene_id=replay_row["scene_id"], trial_id=None,
                evaluation_kind="independent_full_precision_fixture_reachability_not_model_answer")
            rows.append(exact)
    return {"passed": len(rows) == 36 and all(row["passed"] for row in rows),
            "expected_cases": 6, "entry_count": 3, "rows": rows}


def strict_historical_threshold_audit(replay):
    """Report the new threshold independently; do not change historical scores."""
    cases = {case["scene_id"]: case for case in json_file(
        ROOT / "verification/blind_test/runs/20261021_01/private/cases.json")}
    rows = []
    for row in replay.get("replayed_answers", []):
        if row.get("condition") == "plugin":
            rows.append({"scene_id": row["scene_id"], "trial_id": row["trial_id"],
                "historical_joint_success": row["assisted"]["success"],
                "historical_terminal_penetration": row["assisted"]["penetrating"],
                "strict_analytical_terminal_penetration": strict_candidate_penetrates(
                    cases[row["scene_id"]], row["assisted"]["applied_action"]),
                "actual_legacy_controller_action": row["assisted"]["applied_action"]})
    return {"passed": len(rows) == 30, "meaning_of_passed": "audit_completed_not_task_success",
            "historical_collision_tolerance_m": .0001, "strict_collision_tolerance_m": 1e-9,
            "strict_terminal_penetrations": sum(row["strict_analytical_terminal_penetration"] for row in rows),
            "legacy_scores_preserved": True, "rows": rows}


def analytical_cross_entry(output):
    case = analytical_case()
    rows = []
    for entry in ("guarded_runtime", "live_service", "live_mcp"):
        for yaw in (0, 180, 90, -90):
            action = {"focal_id": "part_1", "reference_id": "part_0",
                      "translation": [0, 0, -.1], "rotation_euler_deg": [0, 0, yaw]}
            row = evaluate_case(output / (entry + "_yaw_" + str(yaw)), case, action,
                entry=entry, expected_task=yaw in (0, 180))
            row["case_id"] = "yaw_" + str(yaw)
            rows.append(row)
        for name, translation, expected_execution in (
                ("wrong_clearance", [0, 0, -.05], True),
                ("wrong_region", [.8, 0, -.1], True),
                ("penetration", [0, 0, -.15], False)):
            action = {"focal_id": "part_1", "reference_id": "part_0", "translation": translation}
            row = evaluate_case(output / (entry + "_" + name), case, action,
                entry=entry, expected_task=False, expected_execution=expected_execution)
            row["case_id"] = name
            rows.append(row)
        action = {"focal_id": "part_1", "reference_id": "part_0", "translation": [0, 0, -.1]}
        for name, kwargs in (("unsupported_capability", {"supported": False}),
                             ("missing_capability", {"missing_capability": True}),
                             ("incorrect_readback", {"corrupt_readback": True})):
            row = evaluate_case(output / (entry + "_" + name), case, action,
                entry=entry, expected_task=False, expected_execution=False, **kwargs)
            row["case_id"] = name
            rows.append(row)
    return {"passed": len(rows) == 30 and all(row["passed"] for row in rows), "rows": rows,
            "scope": "analytical_box_fixtures_not_new_general_mesh_truth_set",
            "joint_criteria": ["bottom_face_distance", "pose_mod_180", "target_region", "terminal_collision"],
            "native_goal_region_note": "production point goal plus independent box region score; no native arbitrary region claim"}


def negative_controls(output):
    # Exercise rejection logic with altered bytes, and explicitly prove that the
    # joint scorer rejects a 90-degree pose that has zero bottom-face RMS.
    from geometry import euler_matrix, score_pose
    folder = output / "negative_controls"
    folder.mkdir()
    sample = folder / "tampered.bin"
    sample.write_bytes(b"registered")
    inventory = {sample.name: sha(sample)}
    clean = checked_inventory(folder, inventory)
    sample.write_bytes(b"tampered")
    altered = checked_inventory(folder, inventory)
    case = analytical_case()
    wrongly_rotated = score_pose(case, euler_matrix([0, 0, 90]), case["target"]["center"])
    bad_distance = score_pose(case, euler_matrix([0, 0, 0]), [0, 0, .26])
    passed = (clean["passed"] and not altered["passed"] and not wrongly_rotated["success"]
              and wrongly_rotated["bottom_face_rms_mm"] < 1e-9 and not bad_distance["success"])
    return {"passed": bool(passed), "clean_inventory": clean, "tampered_inventory": altered,
            "zero_rms_wrong_pose_rejected": wrongly_rotated, "wrong_distance_rejected": bad_distance,
            "scope": "negative_controls_must_reject_bad_cases"}


def production_entry_contract(output):
    """Actual default launcher + MCP handshake, without reading a live host."""
    from human_eye_plugin.runtime_identity import runtime_identity
    folder = output / "production_entry"
    folder.mkdir()
    config = folder / "connector.json"
    write_json(config, {"schema_version": "1.0", "project_root": str(ROOT),
        "state_file": "state.json", "audit_file": "events.jsonl", "quad_size": 64,
        "blender": {"host": "127.0.0.1", "port": 1, "timeout_s": .2}})
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    process = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.production_server",
        "--config", str(config)], cwd=ROOT, env=env, capture_output=True, encoding="utf-8",
        input="\n".join(json.dumps(row) for row in requests) + "\n", timeout=30)
    (folder / "stdout.jsonl").write_text(process.stdout, encoding="utf-8")
    (folder / "stderr.log").write_text(process.stderr, encoding="utf-8")
    responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    initialize = next((row.get("result", {}) for row in responses if row.get("id") == 1), {})
    identity = initialize.get("_meta", {}).get("human_eye", {})
    expected = runtime_identity(mode="live")
    fields = ("base_version", "implementation_revision", "build_id", "source_sha256", "source_kind",
              "protocol_version", "mode")
    tools = next((row.get("result", {}).get("tools", []) for row in responses if row.get("id") == 2), [])
    checks = {
        "launcher_clean_exit": process.returncode == 0,
        "identity_matches_current_runtime": all(identity.get(key) == expected.get(key) for key in fields),
        "production_mode_explicit": identity.get("production_mode") is True,
        "protocol_matches_identity": initialize.get("protocolVersion") == identity.get("protocol_version"),
        "unconnected_status_truthful": identity.get("capabilities", {}).get("host_connection") == "not_checked",
        "identity_does_not_certify_model_benefit": identity.get("capabilities", {}).get("model_task_benefit_certified") is False,
        "no_host_state_written_on_handshake": not (folder / "state.json").exists(),
        "exact_live_tools": {tool.get("name") for tool in tools} == {
            "human_eye_scene_observe", "human_eye_transform", "human_eye_connection_status"},
    }
    # An invalid live configuration must terminate; legacy demo must never be
    # selected as an exception fallback by the production launcher.
    missing = subprocess.run([sys.executable, "-B", "-m", "human_eye_plugin.production_server",
        "--config", str(folder / "missing.json")], cwd=ROOT, env=env, capture_output=True,
        encoding="utf-8", input="\n".join(json.dumps(row) for row in requests) + "\n", timeout=30)
    checks["missing_live_config_fails_without_demo"] = missing.returncode != 0 and not missing.stdout.strip()
    return {"passed": all(checks.values()), "checks": checks, "identity": identity,
            "host_connection_attempted": False, "method_scope": ["initialize", "tools/list"],
            "scope": "real_production_launcher_handshake_no_blender_read"}


def run_gate(output):
    before = source_manifest()
    sections = {"preservation_before": preservation_checks()}
    write_json(output / "source_manifest.json", before)
    if sections["preservation_before"]["passed"]:
        sections["locked_answer_replay"], replay = replay_locked_answers(output)
        if sections["locked_answer_replay"]["passed"]:
            sections["repaired_cross_entry"] = repaired_cross_entry(output, replay)
            sections["strict_historical_threshold_audit"] = strict_historical_threshold_audit(replay)
        sections["analytical_cross_entry"] = analytical_cross_entry(output)
        sections["negative_controls"] = negative_controls(output)
        sections["production_entry_contract"] = production_entry_contract(output)
    sections["preservation_after"] = preservation_checks()
    after = source_manifest()
    sections["same_source_revision"] = {"passed": before == after,
        "before_build_id": before["build_id"], "after_build_id": after["build_id"]}
    passed = (len(sections) == 9 and all(value["passed"] for value in sections.values()))
    report = {"schema_version": "1.0", "passed": passed,
        "evaluation_kind": "release_regression_gate_not_new_model_benchmark",
        "new_model_calls": 0, "real_blender_connected": False,
        "package_rebuilt": False, "uploaded_release_modified": False,
        "build_id": before["build_id"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sections": sections}
    write_json(output / "release_gate.json", report)
    legacy = sections.get("locked_answer_replay", {}).get("summary", {})
    strict = sections.get("strict_historical_threshold_audit", {})
    repaired = sections.get("repaired_cross_entry", {}).get("rows", [])
    analytical = sections.get("analytical_cross_entry", {}).get("rows", [])
    lines = ["# Human Eye release regression gate", "",
        "Result: **" + ("PASS" if passed else "FAIL") + "**", "",
        "Build: `" + before["build_id"] + "`", "",
        "No new model calls, Blender connection, package rebuild or cloud upload.", "",
        "| Check | Result |", "|---|---|",
        *["| " + name + " | " + ("PASS" if section["passed"] else "FAIL") + " |"
          for name, section in sections.items()], "",
        "Historical locked-answer replay: " + str(legacy.get("plugin_replayed_successes", "not_run")) + "/30.",
        "Historical analytical canonical replay: " + str(legacy.get("canonical_assisted_successes", "not_run")) + "/30.",
        "Repaired-case cross-entry rows: " + str(sum(row["passed"] for row in repaired)) + "/" + str(len(repaired)) + ".",
        "Analytical cross-entry rows: " + str(sum(row["passed"] for row in analytical)) + "/" + str(len(analytical)) + ".", "",
        "The historical experiment permits 100 micrometres of terminal penetration. "
        "Its original scores remain unchanged. Under the current 1 nanometre numerical gate, "
        + str(strict.get("strict_terminal_penetrations", "not_run")) +
        "/30 replayed controller endpoints have shallow penetration. This threshold is an algorithm "
        "acceptance threshold, not a claim of physical sensing precision.", "",
        "Four of the six repaired historical examples must therefore be rejected unchanged by "
        "the strict live gate. Separate full-precision analytical fixture actions demonstrate "
        "reachability and are never attributed to the model or legacy controller.", "",
        "The integration host is an independently mutable in-memory box fixture. "
        "It exercises the production service and MCP handler, with actual state readback, "
        "but does not establish real Blender, general concave-mesh or model-task performance.", "",
        "Joint scoring combines local-bottom distance, pose modulo 180 degrees, target region "
        "and terminal collision. Native production point criteria and independent box-region "
        "scoring are recorded separately. Zero RMS alone cannot pass the task.", "",
        "Full evidence: `release_gate.json`; current source binding: `source_manifest.json`.", ""]
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
        default=ROOT / "verification/release_runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    args = parser.parse_args(argv)
    output = create_output(args.output_dir)
    try:
        report = run_gate(output)
    except Exception as exc:
        report = {"schema_version": "1.0", "passed": False, "error_type": type(exc).__name__,
                  "error": str(exc), "traceback": traceback.format_exc()}
        write_json(output / "release_gate.json", report)
    print(json.dumps({"passed": report["passed"], "output": str(output),
                      "build_id": report.get("build_id"), "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
