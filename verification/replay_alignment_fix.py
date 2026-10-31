"""Replay locked model answers after the fix; this is not a new model trial."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "verification/blind_test"))
from geometry import build_meshes
from score import score_trial
from human_eye_plugin import HumanEyeLLMPlugin, __version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "verification/fixes/20261021_alignment_recovery")
    args = parser.parse_args()
    original = ROOT / "verification/blind_test/runs/20261021_01"
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((original / "final_manifest.json").read_text(encoding="utf-8"))["file_sha256"]
    def verify_original():
        for path, digest in inventory.items():
            assert hashlib.sha256((original / path).read_bytes()).hexdigest() == digest, path
    verify_original()
    cases = {c["scene_id"]: c for c in json.loads((original / "private/cases.json").read_text(encoding="utf-8"))}
    mapping = json.loads((original / "private/trial_map.json").read_text(encoding="utf-8"))
    old = {r["trial_id"]: r for r in json.loads((original / "blind_scores.json").read_text(encoding="utf-8"))["results"]}
    replay = []
    for trial in mapping:
        response = json.loads((original / "responses" / (trial["trial_id"] + ".json")).read_text(encoding="utf-8-sig"))
        row = score_trial(cases[trial["scene_id"]], response, trial["trial_id"])
        assert row["raw"] == old[trial["trial_id"]]["raw"], "Raw scoring changed"
        row.update(condition=trial["condition"], original_assisted_success=old[trial["trial_id"]]["assisted"]["success"])
        replay.append(row)
    canonical = []
    for case in cases.values():
        plugin = HumanEyeLLMPlugin(meshes=build_meshes(case))
        obs = plugin.build_llm_observation_bundle()
        response = dict(obs["prompt_bundle"].canonical_mcp_tool_call["arguments"], trial_id=case["scene_id"])
        canonical.append(score_trial(case, response, case["scene_id"]))
    plugin_rows = [r for r in replay if r["condition"] == "plugin"]
    summary = {
        "version": __version__, "evaluation_kind": "locked-answer replay and analytical canonical regression; no new model calls",
        "original_files_verified": len(inventory), "new_model_calls": 0,
        "plugin_original_successes": sum(r["original_assisted_success"] for r in plugin_rows),
        "plugin_replayed_successes": sum(r["assisted"]["success"] for r in plugin_rows),
        "plugin_trials": len(plugin_rows),
        "plugin_replayed_terminal_collisions": sum(r["assisted"].get("penetrating", False) for r in plugin_rows),
        "regressions": [r["scene_id"] for r in plugin_rows if r["original_assisted_success"] and not r["assisted"]["success"]],
        "repaired_scenes": [r["scene_id"] for r in plugin_rows if not r["original_assisted_success"] and r["assisted"]["success"]],
        "canonical_raw_successes": sum(r["raw"]["success"] for r in canonical),
        "canonical_assisted_successes": sum(r["assisted"]["success"] for r in canonical),
        "canonical_trials": len(canonical),
        "business_source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(ROOT.glob("*.py")) + sorted((ROOT / "human_eye_plugin").glob("*.py"))
                                   + sorted((ROOT / "human_eye_module1_operators").glob("*.py"))},
    }
    verify_original()
    (output / "replay_results.json").write_text(json.dumps({"summary": summary, "replayed_answers": replay,
                                                          "canonical_regressions": canonical}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["plugin_replayed_successes"] == 30 and summary["canonical_assisted_successes"] == 30 and not summary["regressions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
