"""044 real ordinary closed-family A/B/C, original issue and fresh full budgets."""
from __future__ import annotations

from copy import deepcopy
from hashlib import file_digest
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
VER = HERE.parents[1]
RAW = Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_family")
OLD = RAW.parent.parent / "M6-041-KERNEL-HOOK"
CANDIDATE = RAW.parent.parent / "M6-043-R3-REGION-ATTRIBUTION/candidate/PINS.json"
INPUT = VER / "closed_solid_read_001/inputs"
PLAN = RAW / "PLAN_02.json"
CYCLE = "M6-044-R3-FRESH-BUDGET"
NOW = time.perf_counter_ns
FIXED = {"scene.blend":"a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb",
         "author_mesh_snapshots.json":"5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14",
         "TRUTH.json":"d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff"}


def need(value, message):
    if not value:
        raise ValueError("044_family_" + message)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def check(ref):
    need(pin(ref["path"]) == ref, "changed_source:" + ref["path"])
    return Path(ref["path"])


def save(path, data):
    path = Path(path).resolve()
    need(path.is_relative_to(RAW), "output_scope")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(data,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write("\n")
    return pin(path)


def binary(value):
    if type(value) is float:return {"f64":value.hex()}
    if isinstance(value,list):return [binary(v) for v in value]
    if isinstance(value,dict):return {k:binary(v) for k,v in value.items()}
    return value


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def api():
    s1=load("_044_family_original_s1",OLD/"s1/s1.py")
    gui,service=s1.api()
    gui.PRIVATE,gui.CYCLE=RAW,CYCLE
    gui.ASSET_SHAS={FIXED["scene.blend"]:"closed_solid_read_001_initial"}
    service.CYCLE=CYCLE
    return s1,gui,service


def installed(s1):
    old=s1.source_plan()
    candidate=read(CANDIDATE)
    check(candidate["binding"]);check(candidate["launcher"]);check(candidate["admin"])
    binding=read(candidate["binding"]["path"])
    need(binding["identity"]["source_sha256"]==candidate["source_sha256"]==
         "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e","fixed_candidate")
    for ref in binding["source_files"]:
        need(pin(Path(candidate["site"])/ref["path"])["sha256"]==ref["sha256"],"candidate_file")
    c=dict(source_sha256=candidate["source_sha256"],version=candidate["identity"]["distribution_version"],
           role="044 actual unchanged installed stdio",site_packages=candidate["site"],
           command_prefix=[candidate["dependency_python"],"-I","-B",candidate["launcher"]["path"]])
    return {"A":old["032"],"B":old["r3"],"C":c}


def original():
    path=VER/"closed_solid_read_001/qa_01/RESULTS.json"
    calls=read(path)["public_calls"]
    call,=[v for v in calls if v["state"]=="initial" and v["candidate"]=="Object_02"]
    args=call["arguments"]
    need(args=={"session_id":"closed-solid-read","include_image":False,"query":{
        "mode":"task","objects":[{"name":"Object_01"},{"name":"Object_02"}],
        "requested_facts":["closed_solid_relation","surface_proximity"]}},"unchanged_original_query")
    return path, {"name":"human_eye_scene_observe","arguments":args}, call["public_value"]


def freeze():
    RAW.mkdir(parents=True,exist_ok=True)
    s1,_,_=api()
    refs={name:pin(INPUT/name) for name in FIXED}
    need(all(refs[name]["sha256"]==sha for name,sha in FIXED.items()),"fixed_contract_inputs")
    prior=read(OLD/"s1/PLAN_recovery_01.json")
    support=prior["support"]
    for ref in support.values():check(ref)
    original_path,request,old_reply=original()
    oracle_root=RAW.parent/"oracle"
    oracle={name:pin(oracle_root/name) for name in ("INPUTS.json","GEOMETRY.json","TRUTH.json")}
    need(read(oracle_root/"TRUTH.json")["status"]=="pass","independent_exact_truth_ready")
    sources={str(path):pin(path) for path in (Path(__file__),HERE/"capture.py",OLD/"s1/s1.py",
             *map(Path,prior["sources"]),VER/"m6_post032_profile_036/inputs.py",VER/"m6_same_frame_scoped_batch_034/inputs.py")}
    plan=dict(schema="m6-044-ordinary-family-plan-v1",cycle_id=CYCLE,contract="3fe87bcf50bad31866ebeaf53272d1796dd62a6f",
        status="frozen_before_launch",inputs=refs,asset=refs["scene.blend"],support=support,sources=sources,
        arms=installed(s1),candidate=pin(CANDIDATE),original_request_ref=pin(original_path),request=request,independent_oracle=oracle,
        original_reply=old_reply,order="ABC",query_pair_order=["Object_01","Object_02"],triangle_counts=[96,12],
        request_budget_s=30.0,work_budget="Unchanged installed ordinary task path; no prepay, patch, counter replacement or continuation",
        host_condition="one fresh ordinary private GUI; each arm new installed service/state/audit; one original task call per arm",
        primary="descriptive original tool stdio write through full original business decode, product launch/EOF and GUI/QA separate",
        instrumentation="none in real product; preserve all original task_work/closed shared contact and witness diagnostics for separate offline audit",
        engineering_recovery=pin(RAW/"recovery_01/RECOVERY.json"),
        no_candidate_change=True,no_G60=True,no_auto_retry=True)
    print(save(PLAN,plan),flush=True)


def capture(host,folder,label,plan):
    reply=host.run((HERE/"capture.py").read_text(encoding="utf-8"),timeout_s=30)
    save(folder/(label+"_RPC.json"),reply)
    need(reply["response"]["status"]=="success","native_readback_success")
    text=reply["response"]["result"]["result"]
    line,=[line for line in text.splitlines() if line.startswith("M6_044_CAPTURE:")]
    data=json.loads(line.split(":",1)[1])
    save(folder/(label+".json"),data)
    source=data["source"]
    need(source["pid"]==host.pid and source["main_thread"] and not source["background"] and
         Path(source["asset"]).resolve()==host.workspace/"input.blend","actual_ordinary_owned_source")
    author=read(plan["inputs"]["author_mesh_snapshots.json"]["path"])["initial"]
    expected={row["name"]:row for row in author["objects"]}
    actual={row["name"]:row for row in data["objects"] if row["type"]=="MESH"}
    need(set(actual)==set(expected),"source_mesh_inventory")
    need(source["scale_length"]==author["unit_scale_m"]==1 and source["frame"]==1 and source["subframe"]==0,
         "source_units_frame")
    for name,old in expected.items():
        got=actual[name]
        need(binary(got["matrix_world"])==binary(old["matrix_world"]),"matrix:"+name)
        for mode in ("native","evaluated"):
            need(binary(got[mode]["vertices_local"])==binary(old["vertices_local"]),"local:"+name)
            need(binary(got[mode]["vertices_world_m"])==binary(old["world_vertices"]),"world:"+name)
            need(got[mode]["triangles"]==old["faces"],"source_faces:"+name)
    need([len(actual[name]["evaluated"]["triangles"]) for name in plan["query_pair_order"]]==[96,12],"pair_order_native_faces")
    return data


def facts(body):
    if isinstance(body.get("pairs"),list):
        need(len(body["pairs"])==1,"single_original_pair")
        return body["pairs"][0]["facts"],"pairs[0].facts"
    return body["facts"],"facts"


def validate(folder,record,plan):
    start=read(folder/"client/STARTUP.json")
    arm=plan["arms"][record["arm"]]
    ident=start["hello"]["result"]["_meta"]["human_eye"]
    need(ident["source_sha256"]==arm["source_sha256"] and ident["source_file_count"]==143 and
         ident["production_mode"] and ident["distribution_version"]==arm["version"],"actual_install")
    config=read(folder/"client/CONFIG.json")
    need(config["project_root"]==arm["site_packages"] and config["expected_identity"]=={
         "source_sha256":arm["source_sha256"]} and config["request_budget_s"]==config["blender"]["timeout_s"]==30.0 and
         config["blender"]["host"]==record["host"] and config["blender"]["port"]==record["port"],"original_deadline_and_endpoint")
    logs=[json.loads(line) for line in (folder/"client/AUDIT.jsonl").read_bytes().splitlines() if line]
    answer=record["answer"];body=answer["result"];mid=answer["timing"]["id"]
    need(not answer["tool_error"] and answer["rpc_error"] is None,"ordinary_rpc_result")
    tx,rx=folder/"client"/(mid+".TX.bin"),folder/"client"/(mid+".RX.bin")
    request,response=read(tx),read(rx)
    need(request["params"]==plan["request"] and request["id"]==response["id"]==mid,"original_query_wire")
    need(json.loads(response["result"]["content"][0]["text"])==body and len(response["result"]["content"])==1,
         "original_response_form")
    event,=[e for e in logs if e.get("event")=="request_trace" and str(e["trace"]["annotations"].get("mcp_request_id"))==mid]
    trace=event["trace"]
    need(event["pid"]==trace["pid"]==record["product_pid"] and event["runtime_identity"]["build_id"]=="sha256:"+arm["source_sha256"]
         and event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"]==arm["source_sha256"],"trace_source")
    need(trace["annotations"]["delivery"]=="stdio_write_completed" and trace["annotations"]["include_image"] is False
         and not trace["image_events"],"original_publication")
    need(body["binding"]["runtime_source_sha256"]==arm["source_sha256"] and body["trace_id"]==trace["trace_id"],"body_source_trace")
    observed,=[e for e in logs if e.get("event")=="observe" and e.get("request_id")==trace["request_id"]]
    need(observed["scene_revision"]==body["binding"]["scene_revision"] and observed["pid"]==record["product_pid"],"current_source")
    fs,location=facts(body)
    relation_fact,surface_fact=fs["closed_solid_relation"],fs["surface_proximity"]
    relation=relation_fact.get("value")
    if isinstance(relation,dict):relation=relation.get("relation")
    surface_value=surface_fact.get("value")
    distance=surface_value.get("distance_m") if isinstance(surface_value,dict) else None
    distance_known=surface_fact.get("status")=="measured" and type(distance) in (int,float) and math.isfinite(distance) and distance>=0
    relation_known=relation_fact.get("status")=="measured" and relation in ("separated","touching","penetrating")
    truth=read(plan["inputs"]["TRUTH.json"]["path"])["states"]["initial"]["probes"]["Object_02"]
    distance_check=(truth["distance_interval_m"][0] <= distance <= truth["distance_interval_m"][1]) if distance_known else None
    need(not relation_known or relation==truth["relation"],"no_wrong_closed_relation")
    need(not distance_known or distance_check,"no_wrong_surface_distance")
    exact=read(check(plan["independent_oracle"]["TRUTH.json"]))
    need(not distance_known or binary(distance)==binary(exact["distance_m"]),"independent_exact_rounded_distance")
    need(distance_known or distance is None,"no_partial_unknown_distance")
    record.update(public_status=body["status"],facts_location=location,relation_fact=relation_fact,surface_fact=surface_fact,
        relation=relation,relation_known=relation_known,distance_m=distance,distance_known=distance_known,
        original_interval_check=distance_check,independent_exact_distance_check=(binary(distance)==binary(exact["distance_m"]) if distance_known else None),
        independent_canonical_source_rows=exact["canonical_source_triangle_pair"],original_necessary_facts_available=relation_known and
        (relation!="separated" or distance_known),work=observed.get("task_work"),trace=trace,
        request=pin(tx),response=pin(rx))


def cell(folder,host,arm,plan,service):
    folder.mkdir()
    record=dict(arm=arm,host_pid=host.pid,host=host.host,port=host.port,errors=[],started_ns=NOW())
    client=None
    try:
        client=service.Client(folder/"client",host,"ClosedFamily",plan["arms"][arm]);client.open("ClosedFamily")
        record.update(product_pid=client.server_pid,wrapper_pid=client.worker.pid,ready_ns=NOW())
        record["product_before"]=service.transport.counters(client.server_pid)
        answer=client.observe(plan["request"])
        record["body_decoded_ns"]=NOW()
        record["answer"]=answer
        record["business_ns"]=record["body_decoded_ns"]-answer["timing"]["started_ns"]
        record["product_after"]=service.transport.counters(client.server_pid)
    except BaseException:record["errors"].append(dict(stage="ordinary_request",traceback=traceback.format_exc()))
    finally:
        if client is not None:
            try:
                ret=client.close();record["product_close"]=read(folder/"client/CLOSE.json")
                need(ret==0 and record["product_close"]["method"]=="eof" and not client.reader.is_alive(),"product_EOF")
            except BaseException:record["errors"].append(dict(stage="product_close",traceback=traceback.format_exc()))
    record["through_EOF_ns"]=NOW()-record["started_ns"]
    if not record["errors"]:
        try:validate(folder,record,plan)
        except BaseException:record["errors"].append(dict(stage="post_EOF_validation",traceback=traceback.format_exc()))
    record.update(ended_ns=NOW(),valid=not record["errors"])
    save(folder/"CELL.json",record)
    print(arm,record["valid"],record.get("relation"),record.get("distance_m"),flush=True)
    return record


def run(window_path):
    plan=read(PLAN)
    for ref in (*plan["sources"].values(),*plan["inputs"].values(),*plan["support"].values(),*plan["independent_oracle"].values(),
                plan["candidate"],plan["original_request_ref"],plan["engineering_recovery"]):check(ref)
    window=read(window_path)
    need(window["cycle_id"]==CYCLE and window["status"]=="available" and window.get("token"),"fresh_exclusive_window")
    s1,gui,service=api()
    need(installed(s1)==plan["arms"],"source_still_frozen")
    out=RAW/"attempt_002";out.mkdir()
    report=dict(schema="m6-044-ordinary-family-result-v1",plan=pin(PLAN),window=pin(window_path),started_ns=NOW(),cells={},errors=[])
    host=None
    try:
        host=gui.Owned(out/"native",plan["asset"],plan["support"],window)
        report.update(host_pid=host.pid,port=host.port,host_ready_ns=NOW())
        before=capture(host,out,"BEFORE",plan)
        report["source_geometry_verified"]=True
        report["host_before"]=service.transport.counters(host.pid)
        for arm in plan["order"]:
            report["cells"][arm]=cell(out/arm,host,arm,plan,service)
            need(report["cells"][arm]["valid"],"invalid_arm:"+arm)
        report["host_after"]=service.transport.counters(host.pid)
        after=capture(host,out,"AFTER",plan)
        need(binary(before)==binary(after),"full_scene_unchanged")
        report["source_geometry_preserved"]=True
        report["necessary_facts"]={arm:r["original_necessary_facts_available"] for arm,r in report["cells"].items()}
        report["B_success_C_unknown"]=report["necessary_facts"]["B"] and not report["necessary_facts"]["C"]
    except BaseException:report["errors"].append(traceback.format_exc())
    finally:
        if host is not None:
            try:
                report["gui_close"]=host.close()
                need(report["gui_close"]["status"]=="pass" and report["gui_close"]["process_reaped"] and
                     report["gui_close"]["forced"] is None,"normal_GUI_close")
            except BaseException:report["errors"].append("GUI close:"+traceback.format_exc())
    report.update(ended_ns=NOW(),status="pass" if not report["errors"] and len(report["cells"])==3 else "failed_or_incomplete")
    report["full_lifecycle_wall_ns"]=report["ended_ns"]-report["started_ns"]
    report["before_capture"]=pin(out/"BEFORE.json") if (out/"BEFORE.json").exists() else None
    report["after_capture"]=pin(out/"AFTER.json") if (out/"AFTER.json").exists() else None
    print(save(out/"RESULTS.json",report),flush=True)
    return int(report["status"]!="pass")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("freeze","run"));parser.add_argument("--window",type=Path)
    args=parser.parse_args()
    freeze() if args.mode=="freeze" else sys.exit(run(args.window))
