"""Recover report-only preflight failure from retained real jobs and fresh facts."""

import base64
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write
import numpy as np
from consumer_bridge import Bridge


def value(result):
    if result.get("isError"):
        raise RuntimeError(str(result))
    return json.loads(next(block["text"] for block in result["content"] if block["type"]=="text"))


def main():
    started,cpu=time.perf_counter(),time.process_time()
    attempt="real_api_preflight_02"
    output=HERE/"private/api_preflight/recovered_run02"
    output.mkdir(parents=True,exist_ok=False)
    session=HERE/"private/sessions"/(attempt+"_forearm")
    legacy=HERE/"private/sessions"/(attempt+"_legacy")
    case=HERE/"private/consumer_cases/forearm"
    template=HERE/"private/sessions/v1_forearm_native"
    state_before=read(session/"session.json")
    formal_before=identity(template/"session.json")
    spec=read(Path(state_before["source_spec"]))
    source_before=identity(Path(spec["source_original"]))
    checks={}
    archived=HERE/"private/api_preflight"/attempt
    checks["actual_API_source_matches_executed_run02"]=identity(archived/"session_api.py")["sha256"]==identity(HERE/"session_api.py")["sha256"]
    bridge=Bridge(SimpleNamespace(case=case,session=session,audit=output/"bridge",route="facts",max_tool_calls=12,
        python_timeout_s=45,python_output_chars=16000,fact_output_chars=50000))
    api=bridge.load_api()
    image_result=bridge.call(dict(name="images",arguments={}))
    images=[row for row in image_result["content"] if row["type"]=="image"]
    checks["fresh_MCP_all9_original_image_blocks"]=len(images)==len(bridge.images)==9 and all(hashlib.sha256(base64.b64decode(row["data"])).hexdigest()==expected["sha256"] for row,expected in zip(images,bridge.images))
    actual_python=value(bridge.call(dict(name="execute_python",arguments=dict(code="""from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve
print(type(V),V.dtype,faces.dtype,len(F_ids),len(I_ids),version)
print(cKDTree(V[I_ids]).query(V[I_ids[0]],k=2))
print(spsolve(csr_matrix(np.eye(2)),np.ones(2)))
print(save_edit(I_ids[:1],V[I_ids[:1]].copy(),mode='positions_world'))
"""))))
    checks["fresh_normal_Python_NPZ_entrypoint"]=actual_python["error"] is None and actual_python["observed_version"]==1
    focus=value(bridge.call(dict(name="focus",arguments={})))
    resolved=value(bridge.call(dict(name="resolve_ref",arguments=dict(reference=focus["target"]["reference"]))))
    sections=value(bridge.call(dict(name="project_sections",arguments={})))
    checks["final_facts_focus_resolve_sections_not_truncated"]=not any(call["truncated"] or call["status"]!="completed" for call in bridge.calls)
    checks["final_sections_has_dual_existing_definitions"]=set(sections.get("definitions",sections.get("contours",{}).get("definitions",{}))) >= {"primary","alternative"}
    operations=state_before["operations"]
    operation=operations[0]
    checks["one_actual_saved_probe_operation"]=len(operations)==1 and operation["status"]=="saved_and_independently_read" and state_before["version"]==1 and state_before["pending"] is None
    current_blend=identity(state_before["current_blend"])
    checks["saved_probe_blend_SHA_matches_operation"]=current_blend["sha256"]==operation["saved_blend"]["sha256"]==state_before["current_blend_identity"]["sha256"]
    checks["operation_readback_SHA_matches_actual_packet"]=identity(HERE/operation["readback"]["path"])["sha256"]==operation["readback"]["sha256"]
    metadata=read(archived/"bridge/tool_02/python/COMPLETE_RESULT.json")["created_payloads"][0]
    payload=session/"payloads"/(metadata["payload_id"]+".npz")
    with np.load(payload,allow_pickle=False) as proposed,np.load(state_before["initial_npz"],allow_pickle=False) as initial,np.load(state_before["current_npz"],allow_pickle=False) as current:
        ids=proposed["source_ids"]
        requested=initial["vertices"][ids]+proposed["displacements_world"]
        inverse=np.linalg.inv(initial["matrix_world"])
        native=(requested@inverse[:3,:3].T+inverse[:3,3]).astype(np.float32)
        checks["actual_saved_probe_equals_exact_payload_float32"]=current["vertices_local"][ids].tobytes()==native.tobytes()
        outside=np.setdiff1d(np.arange(len(initial["vertices"])),ids)
        checks["unsubmitted_native_positions_bitwise_preserved"]=current["vertices_local"][outside].tobytes()==initial["vertices_local"][outside].tobytes()
        checks["nonempty_F599_editable_I347"]=len(initial["F_source_ids"])==599 and len(initial["I_ids"])==347
        amplitude=float(np.linalg.norm(proposed["displacements_world"],axis=1).max())
    job_count=len(list((HERE/"private/jobs").iterdir()))
    replay=api.submit_edit(session,payload,0,operation["operation_id"])
    checks["operation_idempotent_no_new_job"]=replay["idempotent_receipt"] and len(list((HERE/"private/jobs").iterdir()))==job_count
    for name,path,version,error in (("stale",payload,0,"stale_expected_version"),
        ("outside",session/"payloads/outside.npz",1,"sparse_source_ids_require_unique_nonempty_subset_of_I"),
        ("budget",session/"payloads/over_budget.npz",1,"submitted_operation_exceeds_fixed_displacement_budget")):
        try:
            api.submit_edit(session,path,version,"recovery_reject_"+name)
        except ValueError as actual:
            checks[name+"_guard_reverified"]=str(actual)==error
    faults=read(archived/"FAULTS.json")
    failed=faults["injections"][0]
    normal=read(session/"readbacks/001/READBACK.json")
    recovered=read(session/"readbacks/003/READBACK.json")
    checks["normal_actual_public_reader_receipt"]=normal["independently_reopened"] and normal["version"]==1
    checks["prelaunch_fault_persisted_and_new_label_recovered"]=Path(HERE/"private/jobs"/failed["label"]/"INJECTED_FAULT.json").is_file() and not Path(failed["output"]).exists() and recovered["reader_job"]!=failed["label"] and recovered["independently_reopened"] and state_before["next_readback_attempt"]==4
    legacy_state=read(legacy/"session.json")
    legacy_result=read(legacy/"readbacks/002/READBACK.json")
    reserved="q"+hashlib.sha256((legacy.name+":1").encode()).hexdigest()[:16]
    checks["legacy_missing_counter_reserved_label_read"]=legacy_state["version"]==0 and not legacy_state["operations"] and legacy_state["next_readback_attempt"]==3 and legacy_result["reader_job"]!=reserved and legacy_result["independently_reopened"]
    labels={normal["reader_job"],recovered["reader_job"],legacy_result["reader_job"],operation["reader_job"],operation["reader_job"].rsplit("r",1)[0]}
    jobs=[read(HERE/"private/jobs"/label/"run.json") for label in sorted(labels)]
    checks["five_actual_Blender_jobs_exited_zero"]=len(jobs)==5 and all(job["process"]["returncode"]==0 for job in jobs)
    checks["four_independent_reader_jobs_export_actual_saved_data"]=sum(job["script"]["path"]=="blender_read.py" and job["receipt"]["writer_arrays_or_receipts_read"] is False for job in jobs)==4
    quality=read(Path(operation["quality_record"]))
    checks["actual_probe_technical_quality_pass"]=quality["status"]=="pass"
    checks["actual_probe_dual_reference_metrics"]=set(quality["contours"]["definitions"])=={"primary","alternative"}
    checks["readonly_recovery_preserved_all_session_fields"]=read(session/"session.json")==state_before
    checks["formal_case_unmodified"]=identity(template/"session.json")==formal_before
    checks["original_source_unmodified"]=identity(Path(spec["source_original"]))==source_before
    bridge.save(True)
    checks={name:bool(result) for name,result in checks.items()}
    detail=dict(checks=checks,original_executed_attempt=attempt,jobs=[identity(HERE/"private/jobs"/label/"run.json") for label in sorted(labels)],
        local_readonly_recovery_wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,
        operation=operation,sections=sections,source_identities=[identity(HERE/name) for name in ("session_api.py","consumer_bridge.py","python_executor.py","quality.py","evaluate.py","facts_api.py","recover_api_preflight.py")])
    write(output/"DETAIL.json",detail)
    summary=dict(status="pass" if all(checks.values()) else "fail",checks=checks,checks_total=len(checks),
        actual_Pro_sessions=0,actual_Blender_processes=5,actual_Blender_edits=1,actual_Blender_reads=4,
        additional_Blender_calls_during_recovery=0,true_image_blocks=len(images),true_image_bytes=sum(row["bytes"] for row in bridge.images),
        actual_sparse_probe_displacement_m=amplitude,hidden_final_consumer_displacement_provided=False,injected_prelaunch_faults=1,legacy_reserved_jobs=1,
        status_recovery="real_api_preflight_02 executed actual operations; report serialization failed. This fresh read-only bridge run validates final facts and rebuilds checks from retained actual files.",
        local_readonly_recovery_wall_s=detail["local_readonly_recovery_wall_s"],local_readonly_recovery_parent_CPU_s=detail["parent_CPU_s"],
        nested_Blender_wall_s=sum(job["wall_s"] for job in jobs),nested_Blender_tree_CPU_s=sum(job["process"].get("tree_cpu_s",0) for job in jobs),
        full_evidence=identity(output/"DETAIL.json"),source_identities=detail["source_identities"])
    write("API_PREFLIGHT.json",summary)
    attempts=[]
    for name in ("real_api_preflight","real_api_preflight_02"):
        process=read(HERE/"private/processes"/(name+".json"))
        attempts.append(dict(name=name,process=identity(HERE/"private/processes"/(name+".json")),wall_s=process["full_process_wall_s"],tree_CPU_s=process["tree_cpu_s"],
            returncode=process["returncode"],actual_Blender_jobs=0 if name=="real_api_preflight" else 5,
            failure="preflight interpreted metadata block as image" if name=="real_api_preflight" else "NumPy bool in report JSON after successful actual chain"))
    write("private/api_preflight/RUNS.json",dict(attempts=attempts,recovery=identity(output/"DETAIL.json"),additional_Blender_calls=0,
        monitored_attempt_wall_s=sum(row["wall_s"] for row in attempts),readonly_recovery_wall_s=detail["local_readonly_recovery_wall_s"],actual_Blender_total=5,
        accounting="Second attempt monitor includes all five Blender jobs. Recovery is a separate read-only scope. No numerical or geometry edit replay after report failure."))
    print(summary["status"],len(checks),"actual Blender5, recovery additional0",flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__=="__main__":
    main()
