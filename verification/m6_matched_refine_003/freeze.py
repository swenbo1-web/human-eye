"""Freeze the fixed sample, hidden scorer, public inputs and executed tool sources."""

import argparse
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


def freeze_tools(stage):
    output = "TOOL_FREEZE.json" if stage == "v1" else "TOOL_FREEZE_v2.json"
    if (HERE / output).exists():
        raise ValueError("tool_stage_already_frozen")
    extra = [
        HERE.parent / "m6_task_perception_001/interfaces.py",
        HERE.parent / "m6_task_perception_001/python_sandbox.py",
        HERE.parent / "m6_perception_001/region_common.py",
        HERE.parent / "m6_refine_001/quality.py",
        HERE.parent / "m6_coupled_probe_001/evaluate.py",
        HERE.parents[1] / "human_eye_plugin/surface_geometry.py",
        HERE.parent / "m6_shape_train_001/process_runner.py",
        HERE.parent / "plugin_version_llm_ab_001/run_consumers.py",
    ]
    folder = HERE / "private/tool_versions" / stage
    folder.mkdir(parents=True, exist_ok=False)
    files = []
    for index, path in enumerate([HERE / name for name in TOOLS] + extra):
        destination = folder / (str(index).zfill(2) + "_" + path.name)
        shutil.copyfile(path, destination)
        files.append(dict(identity(path), archived=identity(destination)))
    write(output, dict(stage=stage, UTC=datetime.now(timezone.utc).isoformat(), files=files,
        python=identity(PYTHON), Blender=identity(BLENDER),
        interpretation="Exact executed sources, including the private fixed scorer. No private target is supplied to consumers."))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("v1", "v2"))
    args = parser.parse_args()
    if args.stage == "v2":
        if not (HERE / "OPTIMIZATION_BINDING.json").exists():
            raise ValueError("actual_first_stage_optimization_binding_required")
        binding = read("OPTIMIZATION_BINDING.json")
        if read("PREVIEW_PREFLIGHT.json")["status"] != "pass":
            raise ValueError("actual_preview_preflight_required")
        for row in read("TOOL_FREEZE.json")["files"]:
            path = Path(row["path"])
            path = path if path.is_absolute() else HERE / path
            if identity(path)["sha256"] != row["sha256"] and path.name not in binding["permitted_source_changes"]:
                raise ValueError("source_change_outside_one_bound_optimization_" + path.name)
        if identity(HERE / binding["initial_analysis"]["path"])["sha256"] != binding["initial_analysis"]["sha256"]:
            raise ValueError("bound_first_stage_analysis_changed")
        freeze_tools("v2")
        return
    if (HERE / "PLAN.json").exists():
        raise ValueError("plan_already_frozen")
    for name in ("API_PREFLIGHT.json", "BRIDGE_PREFLIGHT.json", "CONSUMER_PREFLIGHT.json", "QUALITY_PREFLIGHT.json"):
        if read(name)["status"] != "pass":
            raise ValueError("required_preflight_incomplete_" + name)
    budget = read("CASE_BINDING.json")["budget_m"]
    plan = dict(
        cycle_id="M6-MATCHED-REFINE-003", baseline_commit="159181eede633063e8a5becbaa33210ebb4223a0",
        contract_commit="99497e8ea6a9f57fd9ac31ad2b98abf80422fba6", fixed_sample="PAIRS001/sample_05",
        objective="Actual local restoration of the saved damaged forearm toward normal same-camera rendered PNGs",
        consumer=dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12,
            max_session_seconds=600, image_transport="mcp", required_API_preflight="API_PREFLIGHT.json",
            python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000,
            answer_schema=dict(task_id="matched", decision_status="completed or incomplete",
                modification_decision="edit or no_edit", visual_evidence="brief actual normal/current comparison",
                active_region="own region or stable reference with transition", operation_id="actual operation or null",
                version="actual final version", saved_blend="actual saved artifact reference",
                readback="independent saved-model readback reference", target_result="observed result",
                remaining_issues="actual limitations or incomplete repair")),
        input=dict(current_3D="Actual saved damaged Blender readback only, including damaged initial V0 and recomputed normals",
            target="Eight actual normal/current whole/front/side/45 PNGs, identical cameras and shading",
            shared_domains=dict(F=410, I=274), images=identity(HERE / "IMAGE_BINDING.json")),
        displacement_budget=dict(operation_m=budget, cumulative_m=budget,
            definition="Mean of the fixed old normal region's 1158 undirected edges"),
        technical_quality="Native coordinates outside I, source IDs, topology, UVs, materials, matrix, finite coordinates, new degeneracy/reversal and exact local contact. Gradient and normal change are observations.",
        scoring=dict(private_target="private/scoring/target.npz", support_points=47,
            support_RMSE_reduction_minimum=.30, F_RMSE="strictly decreases",
            normal_editable_points=227, normal_editable_displacement_RMS_maximum_m=.00010,
            additional="363 normal points and 227 normal editable points RMSE/p95/max, support p95/max, transitions, depth/inner observations",
            final_input="Final actual saved-file independent Blender readback",
            no_edit="support improvement zero and restoration quality fails"),
        hidden_information="Clean3D, true support, generation parameters and inverse displacement remain in construction/scoring processes. Python and public tool fields restrict access and retain file audit records.",
        initial_sequence=["native", "facts"], second_sequence=["facts", "native"], actual_session_limit=4,
        optimization="One evidence-bound dominant first-stage failure or cost. Same sample, cameras, images, damage and scoring. No third stage.",
        limits=dict(numerical_Blender_s=7200, target_RSS_bytes=4 * 1024**3, threads=1, training=0, Google_API=0),
        completion="Fixed Git commit, local actual artifacts and full costs, one authorized planner callback, independent review",
        case_binding=identity(HERE / "CASE_BINDING.json"),
    )
    write("PLAN.json", plan)
    files = [HERE / name for name in ("PLAN.json", "CONTRACT.md", "PRIOR_REVIEW.md", "PLANNING_PREFLIGHT.json",
        "CASE_BINDING.json", "IMAGE_BINDING.json", "CAMERAS.json", "API_PREFLIGHT.json", "BRIDGE_PREFLIGHT.json")]
    files += [HERE / "private/cases/matched" / name for name in ("before.blend", "actual_initial_readback.npz", "initial.npz", "baseline_scene.json", "spec.json")]
    files += [HERE / "private/consumer_cases/matched" / name for name in ("task.json", "input.npz")]
    files += [HERE / "private/scoring/target.npz"]
    files += [Path(row["path"]) for row in read("IMAGE_BINDING.json")["images"]]
    write("PLAN_FREEZE.json", dict(UTC=datetime.now(timezone.utc).isoformat(), files=[identity(path) for path in files],
        actual_Pro_before_freeze=0, private_scoring_frozen_before_consumers=True))
    freeze_tools("v1")
    print("fixed matched task, current-only inputs, hidden scorer and V1 tools frozen", flush=True)


if __name__ == "__main__":
    main()
