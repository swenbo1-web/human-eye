"""Exercise the actual image/Python/NPZ/edit/save/readback path on extra copies."""

import base64
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import PYTHON, identity, read, write


def value(response):
    if response.get("isError"):
        raise RuntimeError(str(response))
    return json.loads(next(block["text"] for block in response["content"] if block["type"] == "text"))


def clone_session(template, name):
    state = read(template / "session.json")
    if state["version"] != 0 or state.get("pending") or state["operations"]:
        raise ValueError("preflight_requires_untouched_formal_template")
    directory = HERE / "private/sessions" / name
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(state["current_blend"], directory / "before.blend")
    state.update(current_blend=str(directory / "before.blend"), current_blend_identity=identity(directory / "before.blend"),
        stage="local_preflight", route="facts")
    state.pop("next_readback_attempt", None)
    write(directory / "session.json", state)
    return directory, state


def worker(attempt):
    import numpy as np
    from consumer_bridge import Bridge
    started, cpu = time.perf_counter(), time.process_time()
    checks, exceptions = {}, []
    output = HERE / "private/api_preflight" / attempt
    output.mkdir(parents=True, exist_ok=False)
    for name in ("real_api_preflight.py", "session_api.py"):
        (output / name).write_bytes((HERE / name).read_bytes())
    previous_jobs = {path.parent.name for path in (HERE / "private/jobs").glob("*/run.json")}
    template = HERE / "private/sessions/v1_forearm_native"
    template_before = identity(template / "session.json")
    session, state = clone_session(template, attempt+"_forearm")
    spec = read(Path(state["source_spec"]))
    case = HERE / "private/consumer_cases/forearm"
    inputs_before = [identity(case / name) for name in ("task.json", "input.npz")]
    source_before = identity(Path(spec["source_original"]))
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="facts",
        max_tool_calls=12, python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000))
    images = bridge.call(dict(name="images", arguments={}))
    image_blocks = [block for block in images["content"] if block["type"] == "image"]
    checks["actual_image_result_is_MCP_blocks"] = not images.get("isError") and len(image_blocks) == len(bridge.images)
    checks["all_actual_image_bytes_exact"] = all(hashlib.sha256(base64.b64decode(block["data"])).hexdigest() == metadata["sha256"]
        for block, metadata in zip(image_blocks, bridge.images))
    amplitude = min(1e-6, float(spec["max_cumulative_displacement_m"])*.01)
    code = """import math
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
print(type(V),repr(V[:2]),len(F_ids),len(I_ids),version,math.sqrt(4))
print(cKDTree(V[I_ids]).query(V[I_ids[0]],k=2))
A=csr_matrix(np.array([[2.,-1.],[-1.,2.]]))
print(dijkstra(abs(A),directed=False),spsolve(A,np.ones(2)))
print(save_edit(I_ids[:1],np.array([[0.,AMPLITUDE,0.]]),mode='displacements_world'))
""".replace("AMPLITUDE", repr(amplitude))
    result = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
    payload = result["created_payloads"][0]
    checks["ordinary_Python_SciPy_actual_geometry"] = result["error"] is None
    value(bridge.call(dict(name="execute_python", arguments=dict(code="print(type(V),V.dtype,faces.dtype,len(I_ids),version)"))))
    checks["actual_version0_NPZ_packet_warm_hit"] = bridge.calls[-1]["snapshot"]["cache_hit"]
    api = bridge.load_api()
    submitted = value(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=payload["payload_id"],
        expected_version=0, operation_id="actual_api_preflight_probe"))))
    checks["sparse_submit_saved_and_independently_reopened"] = submitted.get("independently_reopened") is True and submitted["version"] == 1
    checks["new_task_quality_has_both_correspondences"] = set(submitted["quality"].get("contours", {}).get("definitions", {})) >= {"primary", "alternative"}
    checks["submit_return_not_truncated"] = not bridge.calls[-1]["truncated"]
    payload_path = session / "payloads" / (payload["payload_id"]+".npz")
    job_count = len(list((HERE / "private/jobs").iterdir()))
    replay = api.submit_edit(session, payload_path, 0, "actual_api_preflight_probe")
    checks["same_operation_replay_no_new_job"] = replay.get("idempotent_receipt") is True and len(list((HERE / "private/jobs").iterdir())) == job_count
    try:
        api.submit_edit(session, payload_path, 0, "stale_version_probe")
    except ValueError as error:
        checks["stale_version_rejected"] = str(error) == "stale_expected_version"
    state = api.load_state(session)
    with np.load(state["initial_npz"],allow_pickle=False) as initial, np.load(state["current_npz"],allow_pickle=False) as current, np.load(payload_path,allow_pickle=False) as proposal:
        ids = proposal["source_ids"]
        requested = initial["vertices"][ids] + proposal["displacements_world"]
        inverse = np.linalg.inv(initial["matrix_world"])
        native = (requested @ inverse[:3,:3].T + inverse[:3,3]).astype(np.float32)
        checks["submitted_values_only_quantized_by_saved_float32"] = native.tobytes() == current["vertices_local"][ids].tobytes()
        outside = np.setdiff1d(np.arange(len(initial["vertices"])), ids)
        checks["all_unsubmitted_native_coordinates_bitwise"] = initial["vertices_local"][outside].tobytes() == current["vertices_local"][outside].tobytes()
        checks["nonempty_shared_edit_domain"] = len(initial["I_ids"]) > 0 and np.isin(initial["I_ids"],initial["F_source_ids"]).all()
        blocked_path = session / "payloads/outside.npz"
        np.savez_compressed(blocked_path,source_ids=initial["protected_ids"][:1],displacements_world=np.zeros((1,3)))
        budget_path = session / "payloads/over_budget.npz"
        np.savez_compressed(budget_path,source_ids=ids,displacements_world=np.array([[0.,2*float(spec["max_cumulative_displacement_m"]),0.]]))
    for name, path, expected in (("outside_I",blocked_path,"sparse_source_ids_require_unique_nonempty_subset_of_I"),
                                 ("fixed_step_budget",budget_path,"submitted_operation_exceeds_fixed_displacement_budget")):
        before = read(session / "session.json")
        try:
            api.submit_edit(session,path,1,"reject_"+name)
        except ValueError as error:
            checks[name+"_rejected_without_state_mutation"] = str(error) == expected and read(session / "session.json") == before
    normal = value(bridge.call(dict(name="save_readback",arguments={})))
    checks["normal_public_saved_readback"] = normal["independently_reopened"] and normal["version"] == 1
    checks["normal_readback_return_not_truncated"] = not bridge.calls[-1]["truncated"]
    focus = value(bridge.call(dict(name="focus",arguments={})))
    reference = focus["target"]["reference"]
    resolved = value(bridge.call(dict(name="resolve_ref",arguments=dict(reference=reference))))
    sections = value(bridge.call(dict(name="project_sections",arguments={})))
    checks["actual_focus_resolve_and_sections_complete"] = bool(resolved) and bool(sections) and not any(call["status"] != "completed" or call["truncated"] for call in bridge.calls)
    read_before = read(session / "session.json")
    api_real_run = api.run_job
    injected = []
    def fail_reader_before_output(script,job,label):
        if script == "blender_read.py" and not injected:
            folder = HERE / "private/jobs" / label
            folder.mkdir(parents=True, exist_ok=False)
            write(folder / "job.json",dict(job,receipt_path=str(folder / "receipt.json")))
            event = dict(label=label,script=script,output=job["readback_npz"],stage="after_label_reservation_before_Blender_start",actual_Blender_process=False)
            injected.append(event)
            write(folder / "INJECTED_FAULT.json",event)
            raise RuntimeError("expected_actual_api_prelaunch_reader_fault")
        return api_real_run(script,job,label)
    api.run_job = fail_reader_before_output
    try:
        api.save_readback(session)
    except RuntimeError as error:
        exceptions.append(dict(type=type(error).__name__,message=str(error),expected=True))
        checks["public_prelaunch_failure_observed"] = str(error) == "expected_actual_api_prelaunch_reader_fault"
    finally:
        api.run_job = api_real_run
    state_failed = read(session / "session.json")
    checks["attempt_increment_persisted_on_failure"] = state_failed["next_readback_attempt"] == read_before["next_readback_attempt"]+1
    recovered = api.save_readback(session)
    state_recovered = read(session / "session.json")
    checks["failure_recovers_new_label_actual_Blender"] = recovered["reader_job"] != injected[0]["label"] and recovered["independently_reopened"]
    checks["standalone_recovery_preserves_version_operations_blend"] = all(state_recovered[key] == read_before[key] for key in ("version","operations","current_blend","current_blend_identity"))
    legacy, legacy_state = clone_session(template,attempt+"_legacy")
    old_label = "q" + hashlib.sha256((legacy.name+":1").encode()).hexdigest()[:16]
    (HERE / "private/jobs" / old_label).mkdir(parents=True,exist_ok=False)
    write(HERE / "private/jobs" / old_label / "LEGACY_RESERVED_LABEL.json",dict(actual_Blender_process=False,output_created=False))
    legacy_result = api.save_readback(legacy)
    checks["legacy_missing_counter_reserved_job_recovers"] = legacy_result["reader_job"] != old_label and read(legacy/"session.json")["next_readback_attempt"] == 3
    checks["formal_session_unchanged"] = identity(template/"session.json") == template_before
    checks["actual_shared_inputs_unchanged"] = [identity(case/name) for name in ("task.json","input.npz")] == inputs_before
    checks["original_model_file_unchanged"] = identity(Path(spec["source_original"])) == source_before
    bridge.save(True)
    checks = {key:bool(result) for key,result in checks.items()}
    write(output / "FAULTS.json",dict(exceptions=exceptions,injections=injected))
    jobs=[read(path) for path in sorted((HERE/"private/jobs").glob("*/run.json")) if path.parent.name not in previous_jobs]
    summary=dict(status="pass" if all(checks.values()) else "fail",checks=checks,checks_total=len(checks),
        actual_Pro_sessions=0,actual_Blender_processes=len(jobs),actual_Blender_edits=sum(row["script"]["path"]=="blender_edit.py" for row in jobs),
        actual_Blender_reads=sum(row["script"]["path"]=="blender_read.py" for row in jobs),
        true_image_blocks=len(image_blocks),true_image_bytes=sum(row["bytes"] for row in bridge.images),
        actual_sparse_probe_displacement_m=amplitude,hidden_final_consumer_displacement_provided=False,
        injected_prelaunch_faults=1,legacy_reserved_jobs=1,wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,
        nested_Blender_wall_s=sum(row["wall_s"] for row in jobs),nested_Blender_tree_CPU_s=sum(row["process"].get("tree_cpu_s",0) for row in jobs),
        raw_evidence=str(output.relative_to(HERE)),source_identities=[identity(HERE/name) for name in ("session_api.py","real_api_preflight.py","consumer_bridge.py","python_executor.py")])
    write(output / "SUMMARY.json",summary)
    write("API_PREFLIGHT.json",summary)
    print(json.dumps(dict(status=summary["status"],checks=len(checks),Blender_jobs=len(jobs),wall_s=summary["wall_s"])),flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--worker",action="store_true")
    parser.add_argument("--attempt",default="real_api_preflight")
    args=parser.parse_args()
    if not args.attempt.replace("_", "").replace("-", "").isalnum() or len(args.attempt)>48:
        raise ValueError("safe_attempt_label_required")
    if args.worker:
        worker(args.attempt)
        return
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    os.environ["PYTHONDONTWRITEBYTECODE"]="1"
    spec=importlib.util.spec_from_file_location("_consume_actual_monitor",HERE.parent/"m6_shape_train_001/process_runner.py")
    monitor=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    monitor.HERE=HERE
    if (HERE/"private/processes"/(args.attempt+".json")).exists():
        raise ValueError("attempt_already_exists_preserve_and_inspect_before_recovery")
    result=monitor.run([str(PYTHON),"-I","-B","-X","utf8",str(Path(__file__)),"--worker","--attempt",args.attempt],args.attempt,timeout_s=7200,rss_limit_bytes=4*1024**3)
    write("API_PREFLIGHT_PROCESS.json",result)
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__ == "__main__":
    main()
