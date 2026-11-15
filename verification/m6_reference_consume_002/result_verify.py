"""Reopen actual completed models and re-evaluate both reference definitions."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import PYTHON,identity,read,write


def packet(path):
    import numpy as np
    with np.load(path,allow_pickle=False) as archive:
        return {key:archive[key] for key in archive.files}


def images_delivered(consumer_directory,receipt):
    available=receipt["available_image_inputs"]
    expected=[row["sha256"] for row in available]
    deliveries=[]
    checks={}
    bridge=read(consumer_directory/"bridge/BRIDGE_RESULT.json")
    actual_tool_events=[row["item"] for row in receipt["tool_calls"] if row["item"].get("server")=="task_geometry" and row["item"].get("tool")=="images"]
    calls=[call for call in bridge["calls"] if call["name"]=="images" and call["status"]=="completed"]
    checks["image_tool_events_match_bridge_calls"]=len(actual_tool_events)==len(calls)>0
    for call in calls:
        folder=consumer_directory/"bridge"/("tool_"+str(call["index"]).zfill(2))
        response=read(folder/"RESPONSE.json")
        blocks=[block for block in response["content"] if block["type"]=="image"]
        hashes=[hashlib.sha256(base64.b64decode(block["data"])).hexdigest() for block in blocks]
        checks["images_exact_original_bytes_call_"+str(call["index"])]=hashes==expected and not response.get("isError")
        deliveries.append(dict(call_index=call["index"],images=len(blocks),PNG_bytes=sum(len(base64.b64decode(block["data"])) for block in blocks),
            source=identity(folder/"RESPONSE.json"),scope="Complete Bridge response during an actual Pro tool call, server-to-client image bytes. CLI log text may truncate and is not used to count image blocks. Provider-internal image encoding remains unmeasured."))
    checks["actual_Pro_image_call_recorded"]=receipt.get("actual_image_delivery_verified") is True and receipt.get("first_tool_images") is True
    checks["original_image_files_preserved"]=all(identity(row["path"])["sha256"]==row["sha256"] for row in available)
    return checks,deliveries


def verify_session(name,output,attempt):
    from background import run_job
    from evaluate import evaluate_packets
    from render_results import final_readback
    started,cpu=time.perf_counter(),time.process_time()
    stage,task_id,route=name.split("_")
    directory=HERE/"private/sessions"/name
    consumer_directory=HERE/"private/consumers"/stage/task_id/route
    consumer=read(consumer_directory/"CONSUMER.json")
    state=read(directory/"session.json")
    if consumer["status"]=="running" or state.get("pending"):
        raise ValueError("consumer_or_edit_still_running")
    state_before=identity(directory/"session.json")
    model_before=identity(state["current_blend"])
    spec=read(Path(state["source_spec"]))
    output.mkdir(parents=True,exist_ok=False)
    label="verify_"+hashlib.sha256((name+":"+attempt).encode()).hexdigest()[:16]
    job=run_job("blender_read.py",dict(current_blend=state["current_blend"],object_name=spec["object_name"],
        source_original=spec["source_original"],expected_input_sha256=model_before["sha256"],base_npz=state["initial_npz"],
        readback_npz=str(output/"readback.npz"),scene_signature_json=str(output/"scene.json"),local_obj=str(output/"local.obj")),label)
    quality=evaluate_packets(state["initial_npz"],output/"readback.npz",state["initial_npz"],state["source_spec"],
        before_state_path=spec["baseline_scene"],after_state_path=output/"scene.json")
    write(output/"QUALITY.json",quality)
    exported=packet(output/"readback.npz")
    consumer_packet=final_readback(directory,state)
    retained=packet(consumer_packet)
    checks,deliveries=images_delivered(consumer_directory,consumer)
    for key in ("vertices","vertices_world","vertices_local","matrix_world","faces","source_ids","poly_offsets","poly_vertices","triangle_polygon_ids"):
        first,second=exported[key],retained[key]
        checks["fresh_saved_read_matches_consumer_packet_"+key]=first.shape==second.shape and first.dtype==second.dtype and first.tobytes()==second.tobytes()
    receipt=job["receipt"]
    checks["fresh_Blender_process_exported_actual_blocks"]=bool(receipt["input_unchanged"] and receipt["writer_arrays_or_receipts_read"] is False and job["process"]["returncode"]==0)
    checks["saved_model_identity_matches_state"]=model_before["sha256"]==state["current_blend_identity"]["sha256"]
    checks["saved_model_unchanged_during_audit"]=identity(state["current_blend"])==model_before
    checks["session_state_unchanged_during_audit"]=identity(directory/"session.json")==state_before
    checks["dual_five_station_contours_measured"]=set(quality["contours"].get("definitions",{}))=={"primary","alternative"} and all(len(row["after"]["stations"])==5 for row in quality["contours"]["definitions"].values())
    original=packet(state["initial_npz"])
    changed=int((exported["vertices_local"]!=original["vertices_local"]).any(axis=1).sum())
    checks["changed_vertex_count_matches_fresh_geometry"]=changed==quality["displacement"]["changed_vertices"]
    if not changed:
        checks["zero_edit_improvement_remains_false"]=all(row["improvement_established"] is False for row in quality["contours"]["definitions"].values())
    status="pass" if all(checks.values()) else "fail"
    result=dict(session=name,stage=stage,route=route,version=state["version"],audit_status=status,checks=checks,
        checks_passed=sum(checks.values()),checks_total=len(checks),technical_status=quality["status"],geometry_changed_vertices=changed,
        dual_reference_improvement=quality["contours"]["geometry_improvement_established"],artistic_acceptance=None,
        actual_image_deliveries=deliveries,consumer_image_total=sum(row["images"] for row in deliveries),
        source_session=state_before,saved_model=model_before,original_consumer=identity(consumer_directory/"CONSUMER.json"),
        consumer_readback=identity(consumer_packet),fresh_readback=identity(output/"readback.npz"),full_quality=identity(output/"QUALITY.json"),
        new_Blender_job=identity(HERE/"private/jobs"/label/"run.json"),Blender_wall_s=job["wall_s"],
        Blender_tree_CPU_s=job["process"].get("tree_cpu_s"),Blender_tree_peak_RSS_bytes=job["process"].get("tree_sampled_peak_working_set_bytes"),
        wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,
        inputs="Only actual saved blend, immutable initial target, independent reader blocks and original actual-consumer image responses",consumer_shape_claims_used_as_geometry_input=False)
    write(output/"AUDIT.json",result)
    print(name,status,"technical",quality["status"],"changed",changed,flush=True)
    return result


def worker(stage,attempt):
    started,cpu=time.perf_counter(),time.process_time()
    directory=HERE/"private/result_verification"/attempt
    directory.mkdir(parents=True,exist_ok=False)
    source_versions={}
    for version,filename in (("v1","TOOL_FREEZE.json"),("v2","TOOL_FREEZE_v2.json")):
        frozen=read(filename)
        entry=next(row for row in frozen["files"] if row["path"]=="session_api.py")
        archive=identity(HERE/entry["archived"]["path"])
        source_versions[version]=dict(expected_sha256=entry["sha256"],archive=archive,archive_exact=archive["sha256"]==entry["sha256"])
        if version=="v2":
            current=identity(HERE/"session_api.py")
            source_versions[version].update(current=current,current_exact=current["sha256"]==entry["sha256"])
    if not all(row["archive_exact"] and row.get("current_exact",True) for row in source_versions.values()):
        raise ValueError("fixed_API_source_version_changed")
    results=[]
    names=[candidate+"_forearm_"+route for candidate,routes in (("v1",("native","facts")),("v2",("facts","native"))) if stage in ("all",candidate) for route in routes]
    for name in names:
        results.append(verify_session(name,directory/name,attempt))
        write(directory/"PROGRESS.json",dict(sessions=[dict(session=row["session"],audit_status=row["audit_status"],technical_status=row["technical_status"]) for row in results]))
    summary=dict(status="pass" if all(row["audit_status"]=="pass" for row in results) else "fail",stage=stage,
        sessions=[{key:row[key] for key in ("session","audit_status","checks_passed","checks_total","technical_status","geometry_changed_vertices","dual_reference_improvement","consumer_image_total","full_quality","fresh_readback")} for row in results],
        actual_new_Blender_reads=len(results),actual_new_Pro_sessions=0,wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,
        nested_Blender_wall_s=sum(row["Blender_wall_s"] for row in results),
        source_identities=[identity(HERE/name) for name in ("result_verify.py","blender_read.py","blender_common.py","evaluate.py","quality.py")],
        fixed_API_versions=source_versions,
        accounting="Fresh saved-model reader and reused task evaluator, independent of consumer shape claims. Technical QA and reference improvement reported separately.")
    write(directory/"SUMMARY.json",summary)
    write("RESULT_VERIFICATION_"+stage+".json",summary)
    if summary["status"]!="pass":
        raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("v1","v2","all"),required=True)
    parser.add_argument("--attempt")
    parser.add_argument("--worker",action="store_true")
    args=parser.parse_args()
    attempt=args.attempt or ("result_verify_"+args.stage)
    if not attempt.replace("_","").replace("-","").isalnum() or len(attempt)>48:
        raise ValueError("safe_verify_attempt_required")
    if args.worker:
        worker(args.stage,attempt)
        return
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    os.environ["PYTHONDONTWRITEBYTECODE"]="1"
    specification=importlib.util.spec_from_file_location("_consume_result_monitor",HERE.parent/"m6_shape_train_001/process_runner.py")
    monitor=importlib.util.module_from_spec(specification)
    specification.loader.exec_module(monitor)
    monitor.HERE=HERE
    if (HERE/"private/processes"/(attempt+".json")).exists():
        raise ValueError("verification_attempt_already_exists")
    record=monitor.run([str(PYTHON),"-I","-B","-X","utf8",str(Path(__file__)),"--stage",args.stage,"--attempt",attempt,"--worker"],attempt,timeout_s=7200,rss_limit_bytes=4*1024**3)
    write("RESULT_VERIFICATION_PROCESS_"+args.stage+".json",record)
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__=="__main__":
    main()
