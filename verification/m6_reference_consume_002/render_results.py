"""Render completed saved-model sessions with identical frozen context cameras."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
import numpy as np


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else HERE / path


def final_readback(directory, state):
    matches=[]
    for path in sorted((directory / "readbacks").glob("*/READBACK.json")):
        receipt=read(path)
        if receipt["version"]==state["version"] and receipt["saved_blend"]["sha256"]==state["current_blend_identity"]["sha256"]:
            matches.append(absolute(receipt["readback"]["path"]))
    if matches:
        return matches[-1]
    for operation in reversed(state["operations"]):
        if operation.get("status")=="saved_and_independently_read" and operation["version"]==state["version"]:
            return absolute(operation["readback"]["path"])
    raise ValueError("completed_session_requires_actual_final_independent_readback")


def local_obj(packet, initial, destination):
    with np.load(packet,allow_pickle=False) as source:
        vertices,faces,source_ids=source["vertices"],source["faces"],source["source_ids"]
    with np.load(initial,allow_pickle=False) as source:
        F=source["F_source_ids"]
    selected=faces[np.isin(faces,F).all(axis=1)]
    ids=np.unique(selected)
    lookup={int(value):index+1 for index,value in enumerate(ids)}
    with destination.open("x",encoding="utf8",newline="\n") as stream:
        stream.write("# Actual independent Blender readback world coordinates\n")
        for value in ids:
            stream.write("# source_id "+str(int(source_ids[value]))+"\n")
            stream.write("v "+" ".join(format(float(component),".17g") for component in vertices[value])+"\n")
        for face in selected:
            stream.write("f "+" ".join(str(lookup[int(value)]) for value in face)+"\n")
    return dict(file=identity(destination),packet=identity(packet),source_points=len(ids),local_triangles=len(selected),coordinate_space="Blender_world")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("v1","v2"),required=True)
    parser.add_argument("--attempt")
    args=parser.parse_args()
    attempt=args.attempt or ("render_"+args.stage)
    if not attempt.replace("_","").replace("-","").isalnum() or len(attempt)>48:
        raise ValueError("safe_render_attempt_required")
    for variable in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[variable]="1"
    started,cpu=time.perf_counter(),time.process_time()
    baseline=read(HERE.parent/"m6_reference_refine_001/BASE_VIEWS.json")
    baseline_job=baseline["job"]
    baseline_receipt=baseline_job["receipt"]
    if identity(HERE/"blender_render.py")["sha256"] != baseline_receipt["execution"]["script"]["sha256"]:
        raise ValueError("frozen_baseline_renderer_bytes_differ")
    if identity(HERE/"blender_common.py")["sha256"] != baseline_receipt["execution"]["shared_helper"]["sha256"]:
        raise ValueError("frozen_baseline_render_helper_bytes_differ")
    specifications=[row["specification"] for row in baseline["views"]]
    index_path=HERE/"VIEWABLES.json"
    previous=read(index_path) if index_path.exists() else dict(sessions=[])
    if index_path.exists():
        archive=HERE/"private/results/index_history"/(identity(index_path)["sha256"]+".json")
        if not archive.exists():
            archive.parent.mkdir(parents=True,exist_ok=True)
            archive.write_bytes(index_path.read_bytes())
    rows=[]
    for route in (("native","facts") if args.stage=="v1" else ("facts","native")):
        name=args.stage+"_forearm_"+route
        session=HERE/"private/sessions"/name
        consumer_path=HERE/"private/consumers"/args.stage/"forearm"/route/"CONSUMER.json"
        consumer=read(consumer_path)
        state=read(session/"session.json")
        if consumer["status"]=="running" or state.get("pending"):
            raise ValueError("session_not_final_"+name)
        before_state=identity(session/"session.json")
        current_before=identity(state["current_blend"])
        if current_before["sha256"] != state["current_blend_identity"]["sha256"]:
            raise ValueError("final_saved_blend_identity_changed")
        spec=read(Path(state["source_spec"]))
        before_blend=session/"before.blend"
        if identity(before_blend)["sha256"] != baseline_receipt["current_blend"]["sha256"]:
            raise ValueError("before_blend_does_not_match_verified_baseline_render")
        output=HERE/"private/results"/name/attempt
        output.mkdir(parents=True,exist_ok=False)
        before_images=output/"before_views"
        before_images.mkdir()
        copies=[]
        for row in baseline["views"]:
            source=Path(row["image"]["path"])
            if identity(source)["sha256"] != row["image"]["sha256"]:
                raise ValueError("verified_baseline_PNG_changed")
            destination=before_images/source.name
            shutil.copyfile(source,destination)
            copies.append(dict(role=row["specification"]["name"],image=identity(destination),source=row["image"],render_wall_s=0.,mode="copy_of_exact_SHA_matched_baseline"))
        label="render_"+hashlib.sha256((name+":"+attempt).encode()).hexdigest()[:16]
        rendering=run_job("blender_render.py",dict(current_blend=state["current_blend"],source_original=spec["source_original"],
            object_name=spec["object_name"],output_dir=str(output/"after_views"),views=specifications),label)
        final_packet=final_readback(session,state)
        before_obj=local_obj(state["initial_npz"],state["initial_npz"],output/"before_local.obj")
        after_obj=local_obj(final_packet,state["initial_npz"],output/"after_local.obj")
        preserved=identity(session/"session.json")==before_state and identity(state["current_blend"])==current_before
        if not preserved:
            raise ValueError("render_changed_saved_session_state")
        result=dict(session=name,stage=args.stage,route=route,version=state["version"],consumer_status=consumer["status"],
            consumer=identity(consumer_path),session_state=before_state,before_blend=identity(before_blend),after_blend=current_before,
            artifact_directory=str(output),before_images=copies,after_images=rendering["receipt"]["views"],
            before_local_OBJ=before_obj,after_local_OBJ=after_obj,
            render_job=identity(HERE/"private/jobs"/label/"run.json"),
            nested_Blender_wall_s=rendering["wall_s"],Blender_tree_CPU_s=rendering["process"].get("tree_cpu_s"),
            peak_Blender_tree_RSS_bytes=rendering["process"].get("tree_sampled_peak_working_set_bytes"),
            state_and_model_preserved=preserved,displacement_scale=1.,camera_specifications=specifications)
        write(output/"RESULT.json",result)
        rows.append(result)
        print(name,"actual four-view render complete",flush=True)
    retained=[row for row in previous["sessions"] if row["stage"] != args.stage]
    combined=retained+rows
    final=dict(cycle_id="M6-REFERENCE-CONSUME-002",sessions=combined,session_count=len(combined),image_count=8*len(combined),
        last_stage=args.stage,last_attempt=attempt,last_invocation_wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,
        nested_Blender_wall_s=sum(row["nested_Blender_wall_s"] for row in combined),
        original_geometry_scale=1.,displacement_scale=1.,before_render_reuse="Complete baseline blend, renderer/helper SHA and frozen camera specifications match; copied PNGs have zero new render cost")
    write(index_path,final)
    write(HERE/"private/results"/(attempt+"_SUMMARY.json"),final)
    print("viewable sessions",len(combined),"images",8*len(combined),flush=True)


if __name__=="__main__":
    main()
