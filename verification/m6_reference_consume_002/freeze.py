"""Freeze one shared image task and archive both executed tool versions."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import shutil
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write,PYTHON,BLENDER

TOOLS=("common.py","background.py","blender_common.py","blender_edit.py","blender_read.py","blender_render.py",
    "session_api.py","facts_api.py","quality.py","evaluate.py","consumer_runner.py","consumer_bridge.py","python_executor.py","image_inputs.py")


def freeze_tools(stage):
    destination="TOOL_FREEZE.json" if stage=="v1" else "TOOL_FREEZE_v2.json"
    if (HERE/destination).exists():
        raise ValueError("tool_version_already_frozen")
    extra=[HERE.parent/"m6_task_perception_001/interfaces.py",HERE.parent/"m6_task_perception_001/python_sandbox.py",
        HERE.parent/"m6_perception_001/region_common.py",HERE.parent/"m6_refine_001/quality.py",
        HERE.parent/"m6_coupled_probe_001/evaluate.py",HERE.parents[1]/"human_eye_plugin/surface_geometry.py",
        HERE.parent/"m6_reference_refine_001/reference_geometry.py",HERE.parent/"m6_shape_train_001/process_runner.py",
        HERE.parent/"plugin_version_llm_ab_001/run_consumers.py"]
    archive=HERE/"private/tool_versions"/stage
    archive.mkdir(parents=True,exist_ok=False)
    rows=[]
    for index,path in enumerate([HERE/name for name in TOOLS]+extra):
        snapshot=archive/(str(index).zfill(2)+"_"+path.name)
        shutil.copyfile(path,snapshot)
        rows.append(dict(identity(path),archived=identity(snapshot)))
    write(destination,dict(stage=stage,UTC=datetime.now(timezone.utc).isoformat(),files=rows,python=identity(PYTHON),Blender=identity(BLENDER),
        interpretation="Current executable sources checked at each stage launch. Archived exact v1 bytes remain available after one evidence-bound optimization."))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("v1","v2"))
    options=parser.parse_args()
    if options.stage=="v2":
        if not (HERE/"OPTIMIZATION_BINDING.json").exists():
            raise ValueError("initial_result_optimization_binding_required")
        freeze_tools("v2")
        return
    if (HERE/"PLAN.json").exists():
        raise ValueError("plan_already_frozen")
    if read("API_PREFLIGHT.json")["status"]!="pass":
        raise ValueError("real_API_preflight_required")
    plan=dict(cycle_id="M6-REFERENCE-CONSUME-002",baseline_commit="9a759efd7d4acdbc7917fad709d350bd86b33ae2",
        contract_commit="7dbcc26e0cdc0bbe8ae984f9d56f00e43300d93d",case=read("CASE_BINDING.json"),images=read("IMAGE_BINDING.json"),
        objective="Actual image-conditioned explanation and evidence-grounded refinement decision on the original positive-Y forearm, with real isolated editing and independent saved-file readback when supported",
        consumer=dict(model="gpt-6.1-sol",reasoning_effort="medium",max_tool_calls=12,max_session_seconds=600,image_transport="mcp",
            required_API_preflight="API_PREFLIGHT.json",python_timeout_s=45,python_output_chars=16000,fact_output_chars=50000,
            answer_schema=dict(task_id="forearm",decision_status="completed or incomplete",modification_decision="edit or no_edit",
                adopted_correspondence="A, B or both with explanation",correct_part_visual_evidence="actual whole/local observations",
                wrist_structure_interpretation="explain both existing wrist levels",axis_vs_width="distinguish centerline/pose from shape using actual evidence",
                local_recommendation=dict(region="specific local region",direction="supported direction or why unsupported",basis="visual and numerical basis",transition="proposed preserved boundary"),
                operation_id="actual operation or null for no edit",version="actual saved-copy version integer",saved_blend="actual artifact identity/path",
                readback="actual independent saved-file record",reference_metrics="report both A and B, including inner/outer/width/centerline",remaining_uncertainties="specific observed limitations and follow-up needs")),
        initial_sequence=["native","facts"],second_sequence=["facts","native"],actual_session_limit=4,
        optimization="One actual first-stage issue or repeated cost chosen and bound before v2. Both routes receive the same task explanation improvement; source assets, supplied anchor sets, target, model and geometry data remain fixed.",
        interpretation="A concrete no-edit decision requires real image analysis and saved-copy readback. Technical execution, geometric change, reference metrics, consumer judgement and artistic satisfaction are separate outcomes.",
        engineering_budget="Per-operation and cumulative displacement <=0.11 median local I-edge length, fixed once in spec. Both existing EW endpoint guards and the full complement of I are protected.",
        geometry_metrics="native polygon/source IDs, matrix, local float32 protected values, scene/UV/material/packed images; max step, edge gradient0.2, affected template normal5deg, new degenerates/reversals and exact scoped contacts",
        contour_metrics="Both existing correspondence definitions at15/35/55/75/90%, inner/outer/width/centerline residuals and mean/max errors. No third hand annotation.",
        limits=dict(numerical_Blender_s=7200,target_RSS_bytes=4*1024**3,threads=1,training=0,Google_API=0),
        evidence=dict(real_API=identity(HERE/"API_PREFLIGHT.json"),consumer_local=identity(HERE/"CONSUMER_PREFLIGHT.json"),
            quality=identity(HERE/"QUALITY_PREFLIGHT.json")),
        completion="Fixed public commit and private actual records, one planning completion callback, independent review chooses next scope")
    write("PLAN.json",plan)
    paths=[HERE/name for name in ("PLAN.json","CONTRACT.md","PRIOR_REVIEW.md","CASE_BINDING.json","IMAGE_BINDING.json","API_PREFLIGHT.json")]
    paths += [HERE/"private/cases/forearm"/name for name in ("before.blend","baseline_scene.json","initial.npz","spec.json")]
    paths += [HERE/"private/consumer_cases/forearm"/name for name in ("task.json","input.npz")]
    paths += [Path(row["path"]) for row in read("IMAGE_BINDING.json")["images"]]
    for name in ("ANNOTATION_DRAFT.json","OBSERVATION.json","INDEPENDENT_ANCHORS.json"):
        paths.append(HERE.parent/"m6_reference_refine_001"/name)
    write("PLAN_FREEZE.json",dict(UTC=datetime.now(timezone.utc).isoformat(),files=[identity(path) for path in paths],actual_Pro_before_freeze=0))
    freeze_tools("v1")
    print("actual image task, API and tools frozen",flush=True)


if __name__=="__main__":
    main()
