"""Verify single-variable (vision-only) double-blind experiment invariants."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "verification" / "blind_test" / "runs" / "20261021_02_vision_only"
FROZEN_RUNTIME_DIR = ROOT / "verification" / "baseline" / "20261023_before_routing_spatial" / "frozen_runtime"
# The historical runtime snapshot contains every pinned runtime module and the
# original geometry/scorer/generator. These two omitted support scripts are
# accepted only while their bytes still match the original experiment pins.
PINNED_CURRENT_SUPPORT = {"verification/blind_test/aggregate.py", "verification/blind_test/write_report.py"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_packet(pkt: dict) -> dict:
    cloned = json.loads(json.dumps(pkt, ensure_ascii=False))
    cloned["trial_id"] = "<TRIAL_ID>"
    cloned["image_path"] = "<IMAGE_PATH>"
    cloned["action_convention"]["output"]["trial_id"] = "<TRIAL_ID>"
    return cloned


def _verified_historical_sources(protocol: dict) -> dict[str, Path]:
    verified = {}
    for relative, expected_hash in protocol["frozen_source_sha256"].items():
        path = FROZEN_RUNTIME_DIR / relative
        if not path.is_file() and relative in PINNED_CURRENT_SUPPORT:
            path = ROOT / relative
        if not path.is_file() or _sha256(path) != expected_hash:
            raise AssertionError("Historical frozen source unavailable or changed: " + relative)
        verified[relative] = path
    return verified


def _copy_historical_scoring_runtime(destination: Path, protocol: dict) -> Path:
    # Copy only the exact original pins. No protocol, source hash or historical
    # artifact is updated to accommodate changes in the current engine.
    for relative, source in _verified_historical_sources(protocol).items():
        target = destination / relative
        if not target.resolve().is_relative_to(destination.resolve()):
            raise AssertionError("Historical source path escaped temporary runtime")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination / "verification" / "blind_test"


class TestSingleVariableBlindRun(unittest.TestCase):
    def test_protocol_and_manifest_integrity(self) -> None:
        self.assertTrue(RUN_DIR.exists(), f"Missing run dir: {RUN_DIR}")
        protocol = json.loads((RUN_DIR / "protocol.json").read_text(encoding="utf-8"))
        self.assertEqual(protocol["experiment_mode"], "vision_only")
        self.assertEqual(protocol["primary_endpoint"], {"control": "raw.success", "plugin": "raw.success"})
        self.assertEqual(protocol["paired_scenes"], 10)
        self.assertEqual(protocol["trials"], 20)
        frozen_sources = _verified_historical_sources(protocol)
        for rel_path, expected_hash in protocol["frozen_source_sha256"].items():
            self.assertEqual(_sha256(frozen_sources[rel_path]), expected_hash, f"Hash mismatch for {rel_path}")

        manifest = json.loads((RUN_DIR / "private" / "generation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["experiment_mode"], "vision_only")
        self.assertEqual(manifest["scene_count"], 10)
        self.assertEqual(manifest["trial_count"], 20)
        self.assertEqual(len(manifest["artifact_sha256"]), 43)
        for rel_artifact, expected_hash in manifest["artifact_sha256"].items():
            self.assertEqual(_sha256(RUN_DIR / rel_artifact), expected_hash, f"Artifact hash mismatch: {rel_artifact}")

    def test_sole_variable_and_double_blind_invariants(self) -> None:
        cases = {c["scene_id"]: c for c in json.loads((RUN_DIR / "private" / "cases.json").read_text(encoding="utf-8"))}
        trial_map = json.loads((RUN_DIR / "private" / "trial_map.json").read_text(encoding="utf-8"))
        eval_index = json.loads((RUN_DIR / "private" / "evaluation_index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 10)
        self.assertEqual(len(trial_map), 20)
        self.assertEqual(len(eval_index), 20)

        # Scorer blinding: evaluation_index must not contain condition labels.
        for entry in eval_index:
            self.assertEqual(set(entry.keys()), {"trial_id", "scene_id"})
            self.assertRegex(entry["trial_id"], r"^T[0-9a-f]{16}$")

        by_scene: dict[str, dict[str, dict]] = {}
        for item in trial_map:
            by_scene.setdefault(item["scene_id"], {})[item["condition"]] = item

        forbidden_keys = {
            "observation",
            "suggested_action",
            "canonical_mcp_tool_call",
            "measurements",
            "som_anchor_table",
            "telemetry",
        }
        forbidden_tokens_re = re.compile(r"\b(control|plugin|baseline|human[ _-]?eye|group[ _-]?[xy]|S0[0-3][0-9])\b", re.IGNORECASE)

        for scene_id, pair in sorted(by_scene.items()):
            self.assertEqual(set(pair.keys()), {"control", "plugin"}, f"Incomplete pair for {scene_id}")
            ctrl_pkt = json.loads(Path(pair["control"]["packet_path"]).read_text(encoding="utf-8"))
            plg_pkt = json.loads(Path(pair["plugin"]["packet_path"]).read_text(encoding="utf-8"))

            for cond, pkt in (("control", ctrl_pkt), ("plugin", plg_pkt)):
                self.assertFalse(forbidden_keys.intersection(pkt.keys()), f"Leaked keys in {scene_id} {cond}")
                raw_text = json.dumps(pkt, ensure_ascii=False)
                self.assertIsNone(
                    forbidden_tokens_re.search(raw_text),
                    f"Condition or scene identifier leaked in {scene_id} {cond} packet",
                )

            # Non-visual packet content must be 100% byte-identical across paired conditions.
            self.assertEqual(
                json.dumps(_normalize_packet(ctrl_pkt), sort_keys=True, ensure_ascii=False),
                json.dumps(_normalize_packet(plg_pkt), sort_keys=True, ensure_ascii=False),
                f"Packet text/metadata mismatch for {scene_id}",
            )

            # Only the 768x768 view.png rendered by the 3D visual engine differs.
            with Image.open(pair["control"]["image_path"]) as img_c, Image.open(pair["plugin"]["image_path"]) as img_p:
                self.assertEqual(img_c.size, (768, 768))
                self.assertEqual(img_p.size, (768, 768))
                self.assertEqual(img_c.mode, "RGB")
                self.assertEqual(img_p.mode, "RGB")
                arr_c = np.asarray(img_c, dtype=np.int16)
                arr_p = np.asarray(img_p, dtype=np.int16)
                max_diff = int(np.max(np.abs(arr_c - arr_p)))
                self.assertGreater(max_diff, 0, f"Identical images for {scene_id}")
                self.assertEqual(max_diff, cases[scene_id]["render_metadata"]["max_pixel_diff_between_conditions"])

    def test_blind_scoring_and_aggregation_use_raw_primary_endpoint(self) -> None:
        trial_map = json.loads((RUN_DIR / "private" / "trial_map.json").read_text(encoding="utf-8"))
        protocol = json.loads((RUN_DIR / "protocol.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            frozen_runtime = Path(tmp) / "historical_runtime"
            scorer_directory = _copy_historical_scoring_runtime(frozen_runtime, protocol)
            tmp_run = Path(tmp) / "run_check"
            shutil.copytree(RUN_DIR, tmp_run)
            locks_file = tmp_run / "private" / "response_locks.json"
            if locks_file.exists():
                locks_file.unlink()
            for item in trial_map:
                # Submit zero action for every trial to verify symmetric raw.success scoring (only the 2 negative controls pass raw).
                resp = {
                    "trial_id": item["trial_id"],
                    "focal_mark": "#B",
                    "reference_mark": "#A",
                    "rotation_euler_deg_xyz": [0.0, 0.0, 0.0],
                    "translation_xyz_m": [0.0, 0.0, 0.0],
                    "confidence": 1.0,
                    "note": "zero_action_smoke_test",
                }
                (tmp_run / "responses" / f"{item['trial_id']}.json").write_text(
                    json.dumps(resp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            for script, extra_args in (
                ("lock_responses.py", []),
                ("score.py", []),
                ("aggregate.py", ["--reveal"]),
                ("write_report.py", []),
            ):
                # The response-lock utility does not use engine geometry. Its
                # current copy remains separate from the pinned scoring tree.
                script_path = ((ROOT / "verification" / "blind_test" / script)
                               if script == "lock_responses.py" else scorer_directory / script)
                proc = subprocess.run(
                    [sys.executable, "-I", "-B", str(script_path), str(tmp_run), *extra_args],
                    cwd=frozen_runtime,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
            revealed = json.loads((tmp_run / "results_revealed.json").read_text(encoding="utf-8"))
            self.assertEqual(revealed["experiment_mode"], "vision_only")
            self.assertEqual(revealed["primary_endpoint"], {"control": "raw.success", "plugin": "raw.success"})
            # Under zero action, both groups must be evaluated on raw.success (exactly the 1 negative control succeeds in both arms).
            for group_summary in revealed["groups"].values():
                self.assertEqual(group_summary["successes"], 1)
                self.assertEqual(group_summary["raw_successes"], 1)
            self.assertTrue((tmp_run / "report.md").exists())

    def test_historical_scorer_rejects_tampered_frozen_runtime(self) -> None:
        protocol = json.loads((RUN_DIR / "protocol.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            frozen_runtime = Path(tmp) / "historical_runtime"
            scripts = _copy_historical_scoring_runtime(frozen_runtime, protocol)
            run = Path(tmp) / "run_check"
            shutil.copytree(RUN_DIR, run)
            changed = frozen_runtime / "human_eye_module1_operators/submodule_1_6_quad_compositor.py"
            changed.write_bytes(changed.read_bytes() + b"\n# deliberate temporary source tamper\n")
            previous_scores = _sha256(run / "blind_scores.json")
            proc = subprocess.run([sys.executable, "-I", "-B", str(scripts / "score.py"), str(run)],
                                  cwd=frozen_runtime, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Scoring source changed after protocol freeze", proc.stderr)
            self.assertIn("submodule_1_6_quad_compositor.py", proc.stderr)
            self.assertEqual(_sha256(run / "blind_scores.json"), previous_scores)

    def test_historical_aggregation_rejects_tampered_input_artifact(self) -> None:
        protocol = json.loads((RUN_DIR / "protocol.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            frozen_runtime = Path(tmp) / "historical_runtime"
            scripts = _copy_historical_scoring_runtime(frozen_runtime, protocol)
            run = Path(tmp) / "run_check"
            shutil.copytree(RUN_DIR, run)
            manifest = json.loads((run / "private/generation_manifest.json").read_text(encoding="utf-8"))
            relative = next(iter(manifest["artifact_sha256"]))
            changed = run / relative
            changed.write_bytes(changed.read_bytes() + b"\n")
            previous_reveal = _sha256(run / "results_revealed.json")
            proc = subprocess.run([sys.executable, "-I", "-B", str(scripts / "aggregate.py"), str(run), "--reveal"],
                                  cwd=frozen_runtime, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Frozen input was modified", proc.stderr)
            self.assertIn(relative, proc.stderr)
            self.assertEqual(_sha256(run / "results_revealed.json"), previous_reveal)


if __name__ == "__main__":
    unittest.main()
