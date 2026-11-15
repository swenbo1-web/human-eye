"""Freeze exact targets and archive each executed tool version before consumers."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BLENDER, PYTHON, identity, read, write


TOOLS = ("common.py", "background.py", "blender_common.py", "blender_edit.py", "blender_read.py", "blender_render.py",
    "session_api.py", "facts_api.py", "python_executor.py", "consumer_bridge.py", "consumer_runner.py", "quality.py", "evaluate.py")


def freeze_tools(stage):
    name = "TOOL_FREEZE.json" if stage == "v1" else "TOOL_FREEZE_v2.json"
    if (HERE / name).exists():
        raise ValueError("tool_version_already_frozen")
    dependencies = [HERE.parent / "m6_shape_train_001/process_runner.py",
        HERE.parent / "m6_task_perception_001/python_sandbox.py", HERE.parent / "plugin_version_llm_ab_001/run_consumers.py",
        HERE.parent / "m6_coupled_probe_001/evaluate.py", HERE.parents[1] / "human_eye_plugin/surface_geometry.py",
        HERE.parent / "m6_task_perception_001/interfaces.py", HERE.parent / "m6_perception_001/region_common.py"]
    sources = [HERE / name for name in TOOLS] + dependencies
    sources = list(dict.fromkeys(path.resolve() for path in sources))
    rows = []
    archive = HERE / "private/tool_versions" / stage
    archive.mkdir(parents=True, exist_ok=False)
    for index, source in enumerate(sources):
        destination = archive / (str(index).zfill(2) + "_" + source.name)
        shutil.copyfile(source, destination)
        rows.append(dict(identity(source), archived=identity(destination)))
    write(name, dict(stage=stage, frozen_at_UTC=datetime.now(timezone.utc).isoformat(), files=rows,
        python=identity(PYTHON), blender=identity(BLENDER),
        interpretation="active source hashes checked before every stage launch, archived exact bytes retain v1 identities after the single permitted optimization"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("v1", "v2"))
    args = parser.parse_args()
    if args.stage == "v2":
        if not (HERE / "OPTIMIZATION_BINDING.json").exists():
            raise ValueError("actual_initial_results_and_optimization_binding_required")
        freeze_tools("v2")
        return
    if (HERE / "PLAN.json").exists():
        raise ValueError("initial_plan_already_frozen")
    reference, preflight, facts = read("REFERENCE_CONTROL.json"), read("TOOL_PREFLIGHT.json"), read("FACTS_PREFLIGHT.json")
    if any(case["status"] != "pass" for case in reference["cases"]) or preflight["status"] != "pass" or facts["status"] != "pass":
        raise ValueError("feasibility_or_real_protocol_preflight_incomplete")
    render = read("RENDER_PREFLIGHT.json")
    geometry = read("GEOMETRY.json")
    plan = dict(cycle_id="M6-REFINE-001", baseline_commit="fb529836f3b665be4f22eee886690d583aa9dc31",
        contract_commit="2ef3ce26d1e7a821170eecefcd22714a65a06e40", authorized_write_scope="verification/m6_refine_001/",
        cases=geometry["cases"],
        objective="actual LLM-directed normal-field local refinement, full isolated Blender save and independent fresh-process readback",
        normal_definition="full-source area-weighted unit normals, then normalize(0.5 self + 0.5 mean one-ring unit normals), initial directions fixed",
        amplitude="h=0.1 median initial full-world local-edge length for edges whose two endpoints lie in I",
        targets="F/B0/B1/I/C/center and numerical goals identical for native and facts routes, task JSON is shared byte-for-byte",
        preservation="outside-I local float32 coordinates bitwise equal, full source mapping and native polygon loops, matrices and scene fingerprints fixed",
        world_tolerance="max(case native precision floor, 8*eps_float32*max(abs(initial world coordinates))), exact values fixed in each spec",
        safety="all full-source edges incident to I, template affected normal angle <=5 degrees, no new degenerate/reversed triangles, exact affected-triangle versus full-source self-contact candidates with shared-simplex handling",
        retessellation="native polygon loops are authoritative topology, actual loop triangles and stable polygon+vertex triangle keys separately checked; unprovable new-contact attribution remains unknown",
        face_unreachable="source IDs 20928 and 25860 remain in I and are fixed at zero displacement, excluded from finite distance maximum and C",
        reference_control="independent hidden smoothstep distance construction, used before consumers to confirm feasibility, omitted from supplied consumer geometry namespace and packets",
        consumer=dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=10, max_session_seconds=480,
            python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000,
            answer_schema=dict(task_id="s01 or s02", status="pass, fail or unknown from actual readback", operation_id="actual submitted operation", version="saved version integer",
                saved_blend="actual saved artifact identity", readback="independent record reference", center_over_h="measured number", core_median_over_h="measured number", remaining="unmet or unknown checks")),
        initial_sequence=[["s01", "native"], ["s01", "facts"], ["s02", "facts"], ["s02", "native"]],
        optimization_sequence=[["s02", "facts"], ["s01", "facts"]],
        optimization="one evidence-selected intervention after all four v1 results are immutable, preserve original native results, never copy their final displacement to facts",
        limits=dict(real_Pro_sessions=6, training=0, numerical_seconds=7200, numerical_RSS_bytes=4*1024**3, threads=1),
        costs="inclusive numerical and consumer controllers, nested Blender/Python/facts scopes separately stated, disjoint enclosing roots summed without double counting, full bytes/cache/images/tokens and unknown fees",
        rendering="same initial frozen three cameras, actual saved geometry at original displacement scale and shared neutral clay lighting, full blends and local OBJ also delivered",
        preflight=dict(actual_protocol=identity(HERE / "TOOL_PREFLIGHT.json"), hidden_feasibility=identity(HERE / "REFERENCE_CONTROL.json"), render=identity(HERE / "RENDER_PREFLIGHT.json")),
        human_visual_judgement="Engineering task chosen by planning contract. Human artistic acceptance remains unmeasured.",
        completion="fixed public commit, private artifacts and one completion callback to planning chat, independent review selects next M6 task")
    write("PLAN.json", plan)
    paths = [HERE / name for name in ("PLAN.json", "CONTRACT.md", "PLANNING_PREFLIGHT.json", "SOURCES.json", "GEOMETRY.json", "REFERENCE_CONTROL.json", "TOOL_PREFLIGHT.json", "FACTS_PREFLIGHT.json", "RENDER_PREFLIGHT.json")]
    for case_id in ("s01", "s02"):
        paths += [HERE / "private/cases" / case_id / name for name in ("initial.npz", "spec.json", "before.blend", "baseline_scene.json")]
        paths += [HERE / "private/consumer_cases" / case_id / name for name in ("task.json", "input.npz")]
        paths.append(HERE / "private/reference" / case_id / "render_spec.json")
        paths.append(HERE / "private/reference" / case_id / "render_spec_v2_16_4.json")
    write("PLAN_FREEZE.json", dict(frozen_at_UTC=datetime.now(timezone.utc).isoformat(), files=[identity(path) for path in paths],
        actual_consumer_sessions_before_freeze=0))
    freeze_tools("v1")
    print("v1 plan and tools frozen", flush=True)


if __name__ == "__main__":
    main()
