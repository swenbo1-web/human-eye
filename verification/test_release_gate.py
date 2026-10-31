"""Failure-sensitive tests for release acceptance infrastructure."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verification.release_gate_helpers import (
    AnalyticalMemoryHost, REPAIR_SCENES, ROOT, analytical_case, analytical_exact_target_action,
    checked_inventory, evaluate_case, json_file, sha, strict_candidate_penetrates)
from verification.run_release_gate import create_output, negative_controls, run_gate


class ReleaseGateTests(unittest.TestCase):
    def test_inventory_accepts_original_and_rejects_modified_or_missing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = folder / "source.py"
            path.write_text("approved", encoding="utf-8")
            inventory = {path.name: sha(path)}
            self.assertTrue(checked_inventory(folder, inventory)["passed"])
            path.write_text("modified", encoding="utf-8")
            self.assertFalse(checked_inventory(folder, inventory)["passed"])
            path.unlink()
            self.assertEqual(checked_inventory(folder, inventory)["problems"][0]["reason"], "missing")

    def test_inventory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertFalse(checked_inventory(temporary, {"../outside": "unknown"})["passed"])

    def test_output_cannot_overwrite_old_evidence(self):
        existing = ROOT / "verification/fixes/20261021_optimized_merge"
        with self.assertRaises(FileExistsError):
            create_output(existing)
        with self.assertRaises(ValueError):
            create_output(ROOT / "dist/unwanted_release_gate")
        with self.assertRaises(ValueError):
            create_output(ROOT / "verification/blind_test/runs/unwanted_release_gate")

    def test_negative_controls_reject_zero_rms_wrong_rotation_and_altered_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            controls = negative_controls(Path(temporary))
            self.assertTrue(controls["passed"])
            self.assertFalse(controls["zero_rms_wrong_pose_rejected"]["success"])
            self.assertLess(controls["zero_rms_wrong_pose_rejected"]["bottom_face_rms_mm"], 1e-9)
            self.assertFalse(controls["tampered_inventory"]["passed"])

    def test_new_strict_gate_does_not_relabel_legacy_tolerance_as_no_penetration(self):
        replay = json_file(ROOT / "verification/fixes/20261021_optimized_merge/replay_results.json")
        cases = {case["scene_id"]: case for case in json_file(
            ROOT / "verification/blind_test/runs/20261021_01/private/cases.json")}
        penetrations = [row["scene_id"] for row in replay["replayed_answers"]
            if row["condition"] == "plugin" and row["assisted"]["success"]
            and strict_candidate_penetrates(cases[row["scene_id"]], row["assisted"]["applied_action"])]
        self.assertEqual(set(penetrations).intersection(REPAIR_SCENES), {"S006", "S010", "S022", "S025"})
        self.assertEqual(len(penetrations), 14)

    def test_independent_host_uses_actual_vertices_to_reject_shape_corruption(self):
        host = AnalyticalMemoryHost(analytical_case())
        action = analytical_exact_target_action(host.case)
        from human_eye_plugin.auto_router import _validated_scene
        with host.transaction():
            host.apply_transform(action, host.scene["revision"], _validated_scene(host.scene)[2])
        self.assertTrue(host.independent_score()["success"])
        host.scene["meshes"][1]["vertices"][0][0] += .001
        self.assertFalse(host.independent_score()["success"])

    def test_valid_execution_is_not_a_successful_90_degree_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = evaluate_case(Path(temporary) / "mcp", analytical_case(),
                {"focal_id": "part_1", "reference_id": "part_0",
                 "translation": [0, 0, -.1], "rotation_euler_deg": [0, 0, 90]},
                entry="live_mcp", expected_task=False)
            self.assertTrue(result["passed"], result)
            self.assertTrue(result["execution_consistency"])
            self.assertFalse(result["engine_task_succeeded"])
            self.assertFalse(result["independent_joint_task"]["success"])

    def test_missing_production_capability_does_not_call_host_or_quarantine(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = evaluate_case(Path(temporary) / "service", analytical_case(),
                analytical_exact_target_action(analytical_case()), entry="live_service",
                expected_task=False, expected_execution=False, missing_capability=True)
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["mutations"], 0)
            self.assertFalse(result["host_quarantined"])

    def test_incorrect_readback_fails_even_if_requested_goal_pose_looks_correct(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = evaluate_case(Path(temporary) / "service", analytical_case(),
                analytical_exact_target_action(analytical_case()), entry="live_service",
                expected_task=False, expected_execution=False, corrupt_readback=True)
            self.assertTrue(result["passed"], result)
            self.assertTrue(result["host_quarantined"])
            self.assertFalse(result["independent_joint_task"]["actual_vertices_consistent_with_box_pose"])

    def test_preservation_failure_stops_replay_and_fails_entire_gate(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch("verification.run_release_gate.preservation_checks", return_value={"passed": False}), \
                patch("verification.run_release_gate.replay_locked_answers") as replay:
            result = run_gate(Path(temporary))
            self.assertFalse(result["passed"])
            replay.assert_not_called()

    def test_source_change_during_validation_fails_even_if_every_check_passes(self):
        good = {"passed": True}
        before = {"build_id": "sha256:before", "source_sha256": {}}
        after = {"build_id": "sha256:after", "source_sha256": {}}
        with tempfile.TemporaryDirectory() as temporary, \
                patch("verification.run_release_gate.source_manifest", side_effect=[before, after]), \
                patch("verification.run_release_gate.preservation_checks", return_value=good), \
                patch("verification.run_release_gate.replay_locked_answers", return_value=(good, {})), \
                patch("verification.run_release_gate.repaired_cross_entry", return_value=good), \
                patch("verification.run_release_gate.strict_historical_threshold_audit", return_value=good), \
                patch("verification.run_release_gate.analytical_cross_entry", return_value=good), \
                patch("verification.run_release_gate.negative_controls", return_value=good), \
                patch("verification.run_release_gate.production_entry_contract", return_value=good):
            result = run_gate(Path(temporary))
            self.assertFalse(result["passed"])
            self.assertFalse(result["sections"]["same_source_revision"]["passed"])
            self.assertTrue(all(section["passed"] for key, section in result["sections"].items()
                                if key != "same_source_revision"))

    def test_all_mandatory_sections_and_stable_revision_allow_success(self):
        good = {"passed": True}
        source = {"build_id": "sha256:fixed", "source_sha256": {}}
        with tempfile.TemporaryDirectory() as temporary, \
                patch("verification.run_release_gate.source_manifest", return_value=source), \
                patch("verification.run_release_gate.preservation_checks", return_value=good), \
                patch("verification.run_release_gate.replay_locked_answers", return_value=(good, {})), \
                patch("verification.run_release_gate.repaired_cross_entry", return_value=good), \
                patch("verification.run_release_gate.strict_historical_threshold_audit", return_value=good), \
                patch("verification.run_release_gate.analytical_cross_entry", return_value=good), \
                patch("verification.run_release_gate.negative_controls", return_value=good), \
                patch("verification.run_release_gate.production_entry_contract", return_value=good):
            result = run_gate(Path(temporary))
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["sections"]), 9)


if __name__ == "__main__":
    unittest.main()
