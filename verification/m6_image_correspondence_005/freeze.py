"""Freeze common inputs once and archive the exact runtime for each stage."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BLENDER, PYTHON, identity, read, write


RUNTIME_FILES = (
    "common.py", "background.py", "blender_common.py", "blender_edit.py", "blender_read.py", "blender_render.py",
    "session_api.py", "facts_api.py", "correspondence.py", "quality.py", "evaluate.py", "score.py",
    "consumer_runner.py", "consumer_bridge.py", "python_executor.py", "image_inputs.py",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    stage = parser.parse_args().stage
    destination = HERE / ("TOOL_FREEZE_" + stage + ".json")
    if destination.exists():
        raise RuntimeError("stage_runtime_already_frozen")
    preflights = ("API_PREFLIGHT.json", "QUALITY_PREFLIGHT.json", "DELIVERY_HELPER_PREFLIGHT.json",
        "CORRESPONDENCE_PREFLIGHT.json", "RAY_PREFLIGHT.json", "CORRESPONDENCE_SCORE.json",
        "IMAGE_PIXEL_PREFLIGHT.json",
        "CONSUMER_PREFLIGHT_v2.json" if stage == "v2" else "CONSUMER_PREFLIGHT.json",
        "CONSUMER_CASE_PREFLIGHT.json", "CONSUMER_PREVIEW_PREFLIGHT.json",
        "CONSUMER_PUBLIC_INPUT_AUDIT_" + stage + ".json")
    for name in preflights:
        if read(name)["status"] != "pass":
            raise RuntimeError("required_preflight_not_passed_" + name)
    if stage == "v2":
        preflights += ("OPTIMIZED_SUPPORT_PREFLIGHT.json", "OPTIMIZED_SUPPORT_AUDIT.json", "LOCAL_SUPPORT_RUNTIME_PREFLIGHT.json")
        for name in preflights[-3:]:
            if read(name)["status"] != "pass":
                raise RuntimeError("optimized_support_preflight_not_passed_" + name)
    if stage == "v1":
        if (HERE / "PLAN_FREEZE.json").exists():
            raise RuntimeError("common_inputs_already_frozen")
        files = [HERE / name for name in ("PLAN.json", "CONTRACT.md", "PRIOR_REVIEW.md", "PLANNING_PROBE.py",
            "PLANNING_PREFLIGHT.json", "CASE_BINDING.json", "IMAGE_BINDING.json", "CAMERAS.json")]
        files += [HERE / "private/cases/repair" / name for name in ("before.blend", "actual_initial_readback.npz", "initial.npz", "baseline_scene.json", "spec.json")]
        files += [HERE / "private/construction" / name for name in ("normal.blend", "normal_readback.npz", "normal_scene.json")]
        files += [HERE / "private/consumer_cases/repair" / name for name in ("task.json", "input.npz")]
        files += [HERE / "private/scoring/target.npz"]
        files += [Path(row["path"]) for row in read("IMAGE_BINDING.json")["images"]]
        write("PLAN_FREEZE.json", dict(UTC=datetime.now(timezone.utc).isoformat(), files=[identity(path) for path in files],
            actual_Pro_before_freeze=0, fixed_two_stage_inputs=True))
    else:
        for row in read("PLAN_FREEZE.json")["files"]:
            if identity(HERE / row["path"])["sha256"] != row["sha256"]:
                raise RuntimeError("common_input_changed_" + row["path"])
        binding = read("OPTIMIZATION_BINDING.json")
        if binding.get("status") != "ready_for_v2":
            raise RuntimeError("optimization_evidence_binding_required")
        for route in ("native", "facts"):
            if read(HERE / "private/consumers/v1/repair" / route / "CONSUMER.json")["status"] not in ("completed", "failed"):
                raise RuntimeError("both_v1_consumers_must_be_terminal")
    extra = [HERE.parent / "m6_task_perception_001/interfaces.py", HERE.parent / "m6_task_perception_001/python_sandbox.py",
        HERE.parent / "m6_perception_001/region_common.py", HERE.parent / "m6_refine_001/quality.py",
        HERE.parent / "m6_coupled_probe_001/evaluate.py", HERE.parents[1] / "human_eye_plugin/surface_geometry.py",
        HERE.parent / "m6_shape_train_001/process_runner.py", HERE.parent / "plugin_version_llm_ab_001/run_consumers.py"]
    folder = HERE / "private/tool_versions" / stage
    evidence = HERE / "private/freeze_evidence" / stage
    folder.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    sources = []
    runtime_paths = [HERE / name for name in RUNTIME_FILES]
    if stage == "v2":
        runtime_paths.append(HERE / "localized_support.py")
    for index, path in enumerate(runtime_paths + extra):
        archived = folder / (str(index).zfill(2) + "_" + path.name)
        shutil.copyfile(path, archived)
        sources.append(dict(identity(path), archived=identity(archived)))
    if stage == "v2":
        optimization = HERE / "OPTIMIZATION_BINDING.json"
        archived = folder / optimization.name
        shutil.copyfile(optimization, archived)
        sources.append(dict(identity(optimization), archived=identity(archived)))
    validation = []
    for name in preflights:
        archived = evidence / name
        shutil.copyfile(HERE / name, archived)
        validation.append(dict(original=identity(HERE / name), archived=identity(archived)))
    write(destination, dict(stage=stage, UTC=datetime.now(timezone.utc).isoformat(), files=sources,
        validation=validation, python=identity(PYTHON), Blender=identity(BLENDER),
        interpretation="Exact per-stage executed source archive. Common input bytes remain fixed across all four actual consumers."))
    print(stage + " runtime and validation evidence frozen")


if __name__ == "__main__":
    main()
