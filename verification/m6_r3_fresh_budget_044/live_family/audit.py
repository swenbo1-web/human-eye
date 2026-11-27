"""Read-only post-run 044 ordinary family/pressure wire, source and cost audit."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import file_digest
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def need(value,reason):
    if not value:raise ValueError("044_audit_"+reason)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def save(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def normalized(body,source):
    value=deepcopy(body)
    need(value["binding"]["runtime_source_sha256"]==source,"body_source")
    value["binding"]["runtime_source_sha256"]="validated_source"
    value["trace_id"]="validated_trace"
    return value


def audit(section,attempt,plan_name):
    folder=ROOT/section/attempt
    result_path=folder/"RESULTS.json";result=read(result_path);plan_path=ROOT/section/plan_name;plan=read(plan_path)
    need(result["status"]=="pass" and not result["errors"] and result["plan"]==pin(plan_path),"complete_source_result")
    reader_path=HERE/"run.py" if section=="live_family" else HERE.parent/"live_pressure/run.py"
    runtime=load("_044_post_"+section,reader_path)
    for ref in plan["sources"].values():need(pin(ref["path"])==ref,"frozen_controller_source")
    before,after=read(folder/"BEFORE.json"),read(folder/"AFTER.json")
    need(runtime.binary(before)==runtime.binary(after),"complete_scene_readonly")
    need(before["source"]["main_thread"] and not before["source"]["background"],"actual_ordinary_capture")
    profile={};public=[];process_ids=[]
    for arm in "ABC":
        cell_folder=folder/arm;cell=read(cell_folder/"CELL.json")
        need(cell["valid"] and not cell["errors"] and result["cells"][arm]==cell,"original_cell_receipt")
        runtime.validate(cell_folder,cell,plan)
        close=read(cell_folder/"client/CLOSE.json")
        need(close["method"]=="eof" and close["exit_code"]==0 and close==cell["product_close"],"actual_EOF")
        need(cell["answer"]["timing"]["started_ns"]<cell["body_decoded_ns"] and cell["business_ns"]==
             cell["body_decoded_ns"]-cell["answer"]["timing"]["started_ns"],"descriptive_clock")
        need(cell["distance_known"] and cell["distance_m"]>=0,"exact_available_distance")
        public.append(normalized(cell["answer"]["result"],plan["arms"][arm]["source_sha256"]))
        work=cell["work"];surface=work["surface_work"]
        need(work["surface_pair_count"]==1 and work["surface_pair_cache_hit"] is False and work["result_cache_hit"] is False,
             "fresh_ordinary_pair_no_cache")
        profile[arm]=dict(business_ms=cell["business_ns"]/1e6,through_EOF_ms=cell["through_EOF_ns"]/1e6,
            distance_m=cell["distance_m"],surface_work=surface,
            closed_solid_work=work.get("closed_solid_work"),surface_pair_count=work["surface_pair_count"],
            closed_solid_pair_count=work["closed_solid_pair_count"],
            actual_product_CPU_read_window_s=cell["product_after"]["cpu_s"]-cell["product_before"]["cpu_s"],
            product_observed_lifetime_peak_working_set_bytes=cell["product_after"]["peak_working_set_bytes"],
            original_request=cell["request"],original_response=cell["response"],cell=pin(cell_folder/"CELL.json"))
        process_ids.extend((cell["product_pid"],cell["wrapper_pid"]))
    need(public[0]==public[1]==public[2],"full_same_host_business_equal")
    b,c=profile["B"]["surface_work"],profile["C"]["surface_work"]
    differences={key:{"B":b.get(key),"C":c.get(key)} for key in sorted(set(b)|set(c)) if b.get(key)!=c.get(key)}
    closes=[result["gui_close"]] if section=="live_family" else [result["writer_close"],result["reader_close"]]
    for close in closes:
        need(close["status"]=="pass" and close["process_reaped"] and close["forced"] is None and close["exit_code"]==0 and
             not close["released_port"]["owned_listener"] and close["source_unchanged"] and close["owned_copy_unchanged"],"native_cleanup")
        process_ids.append(close["pid"])
    pid_path=ROOT/section/("POST_PROCESS_CHECK_02.json" if section=="live_family" else "POST_PROCESS_CHECK.json")
    pid_check=read(pid_path)
    need(pid_check["all_expected_pids_absent"] and not pid_check["currently_existing_expected_ids"],"actual_PID_absence")
    if section=="live_family":
        truth=read(plan["independent_oracle"]["TRUTH.json"]["path"])
        expected=[[float(Fraction(v)) for v in p] for p in truth["exact_points_world_m"]]
        for arm in "ABC":
            need(result["cells"][arm]["relation_known"] and result["cells"][arm]["relation"]=="separated","original_closed_relation")
            point=result["cells"][arm]["surface_fact"]["value"]["nearest_witness"]
            need(runtime.binary([point["a"],point["b"]])==runtime.binary(expected),"independent_canonical_witness_points")
        attempts=[read(ROOT/section/(name+"/RESULTS.json")) for name in ("attempt_001","attempt_002")]
        counts=dict(native_GUI_launches=2,products=3,original_task_calls=3,pre_business_failed_native_attempts=1)
        total_wall=sum(a["full_lifecycle_wall_ns"] for a in attempts)/1e9
    else:
        need(result["actual_saved_geometry_verified"] and result["scene_preserved"] and result["all_known"] and
             not result["B_success_C_unknown"] and result["writer_pid"]!=result["reader_pid"],"independent_save_reopen")
        need(pin(result["saved_artifact"]["path"])==result["saved_artifact"],"saved_private_bytes")
        counts=dict(native_GUI_launches=2,products=3,original_task_calls=3,saved_private_assets=1)
        total_wall=result["full_lifecycle_wall_ns"]/1e9
    out=dict(schema="m6-044-ordinary-closeout-v1",status="pass",section=section,result=pin(result_path),plan=pin(plan_path),
        independent_audit_source=pin(Path(__file__)),before_capture=pin(folder/"BEFORE.json"),after_capture=pin(folder/"AFTER.json"),
        PID_absence=pin(pid_path),counts=counts,measured_attempt_lifecycle_wall_s=total_wall,profiles=profile,
        B_C_surface_work_field_differences=differences,B_C_surface_work_difference_count=len(differences),
        all_full_public_facts_equal_after_validated_source_trace_normalization=True,B_success_C_unknown=False,
        no_timing_matrix=True,no_new_density=True,no_candidate_change=True,
        resource_scope="Actual product CPU is sampled after initialization through final business decode. Working-set values are individual process-lifetime peaks observed then; no simultaneous tree peak or total start/close/controller CPU is claimed.",
        work_scope="Full original work dictionaries are retained. Equal total work/narrow/node/queue does not mean projection/slab/credit-attempt dictionaries are equal. Unchanged original full per-pair budgets and 30s request deadlines.")
    destination=ROOT/section/"CLOSEOUT.json"
    print(save(destination,out))
    repository=HERE if section=="live_family" else HERE.parent/"live_pressure"
    print(save(repository/"RESULTS.json",{key:out[key] for key in ("schema","status","section","result","plan","PID_absence",
        "counts","measured_attempt_lifecycle_wall_s","B_C_surface_work_field_differences","B_C_surface_work_difference_count",
        "all_full_public_facts_equal_after_validated_source_trace_normalization","B_success_C_unknown","resource_scope")} | {"raw_closeout":pin(destination)}))


if __name__=="__main__":
    audit("live_family","attempt_002","PLAN_02.json")
    audit("live_pressure","attempt_001","PLAN.json")
