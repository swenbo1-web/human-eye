"""Freeze one new target and the shared two-consumer runtime before either launch."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BLENDER, PYTHON, identity, read, write


TOOLS = (
    "common.py", "background.py", "blender_common.py", "blender_edit.py", "blender_read.py", "blender_render.py",
    "session_api.py", "facts_api.py", "quality.py", "evaluate.py", "score.py",
    "consumer_runner.py", "consumer_bridge.py", "python_executor.py", "image_inputs.py",
)


def main():
    if (HERE / "PLAN_FREEZE.json").exists() or (HERE / "TOOL_FREEZE.json").exists():
        raise ValueError("single_task_already_frozen")
    for name in ("API_PREFLIGHT.json", "CONSTRUCTION_GEOMETRY_QA.json", "QUALITY_PREFLIGHT.json",
                 "CONSUMER_PREFLIGHT.json", "CONSUMER_CASE_PREFLIGHT.json", "CONSUMER_PREVIEW_PREFLIGHT.json",
                 "CONSUMER_PUBLIC_INPUT_AUDIT.json"):
        if read(name)["status"] != "pass":
            raise ValueError("required_preflight_incomplete_" + name)
    plan = read("PLAN.json")
    expected = [dict(stage="run", task_id="repair", route="facts"), dict(stage="run", task_id="repair", route="native")]
    if plan["sequence"] != expected or plan["actual_session_limit"] != 2:
        raise ValueError("fixed_two_consumer_sequence_required")
    if identity(HERE / plan["old_program_diagnostics"]["path"])["sha256"] != plan["old_program_diagnostics"]["sha256"]:
        raise ValueError("bound_old_program_diagnostics_changed")
    files = [HERE / name for name in ("PLAN.json", "CONTRACT.md", "PRIOR_REVIEW.md", "PLANNING_PREFLIGHT.py",
        "PLANNING_PREFLIGHT.json", "CASE_BINDING.json", "IMAGE_BINDING.json", "CAMERAS.json", "API_PREFLIGHT.json",
        "CONSTRUCTION_GEOMETRY_QA.json", "QUALITY_PREFLIGHT.json", "DIAGNOSTICS.json", "PREVIOUS_ERRATUM.md")]
    files += [HERE / "private/cases/repair" / name for name in ("before.blend", "actual_initial_readback.npz", "initial.npz", "baseline_scene.json", "spec.json")]
    files += [HERE / "private/construction" / name for name in ("normal.blend", "normal_readback.npz", "normal_scene.json", "noise.npy", "normal_requested.npy", "damaged_requested.npy", "old_damage_vectors.npy")]
    files += [HERE / "private/consumer_cases/repair" / name for name in ("task.json", "input.npz")]
    files += [HERE / "private/scoring/target.npz"]
    files += [Path(row["path"]) for row in read("IMAGE_BINDING.json")["images"]]
    write("PLAN_FREEZE.json", dict(UTC=datetime.now(timezone.utc).isoformat(), files=[identity(path) for path in files],
        actual_Pro_before_freeze=0, target_and_both_initial_inputs_frozen=True))
    extra = [HERE.parent / "m6_task_perception_001/interfaces.py", HERE.parent / "m6_task_perception_001/python_sandbox.py",
        HERE.parent / "m6_perception_001/region_common.py", HERE.parent / "m6_refine_001/quality.py",
        HERE.parent / "m6_coupled_probe_001/evaluate.py", HERE.parents[1] / "human_eye_plugin/surface_geometry.py",
        HERE.parent / "m6_shape_train_001/process_runner.py", HERE.parent / "plugin_version_llm_ab_001/run_consumers.py"]
    folder = HERE / "private/tool_versions/run"
    folder.mkdir(parents=True, exist_ok=False)
    sources = []
    for index, path in enumerate([HERE / name for name in TOOLS] + extra):
        snapshot = folder / (str(index).zfill(2) + "_" + path.name)
        shutil.copyfile(path, snapshot)
        sources.append(dict(identity(path), archived=identity(snapshot)))
    write("TOOL_FREEZE.json", dict(stage="run", UTC=datetime.now(timezone.utc).isoformat(), files=sources,
        python=identity(PYTHON), Blender=identity(BLENDER),
        interpretation="One shared carried V2 runtime with neutral public path representations. Both consumer launches verify these exact source bytes."))
    print("single target, diagnostics and two-route runtime frozen", flush=True)


if __name__ == "__main__":
    main()
