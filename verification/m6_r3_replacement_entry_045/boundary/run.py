"""045 sole frozen 129 boundary: ordinary genesis, independent reopen, ABC task calls."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import file_digest
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
RAW=Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/boundary")
ROOT=RAW.parent
FINAL=ROOT/"oracle"
FAMILY=HERE.parents[1]/"m6_r3_fresh_budget_044/live_family"
CYCLE="M6-045-R3-REPLACEMENT-ENTRY"
PLAN=RAW/"PLAN.json"
NOW=time.perf_counter_ns
EXPECTED={"FINAL_FREEZE.json":"3b283ad99ae043aac13151ca70feffd042a332575e68889860073b2805ce85a3",
          "FINAL_GEOMETRY.json":"4f2ed6c63e01feae64f1f952cdb26e9151a882ce1e066da045abe990b868549a",
          "FINAL_INDEPENDENT_TRUTH.json":"e2907348751c42ce0eb972e73ef30888eff795cb2dd7d9c4456a50c417f9e90c"}


def need(value,reason):
    if not value:raise ValueError("044_pressure_"+reason)


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def check(ref):
    need(pin(ref["path"])==ref,"changed:"+ref["path"])
    return Path(ref["path"])


def save(path,data):
    path=Path(path).resolve();need(path.is_relative_to(RAW),"output_scope")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(data,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def binary(value):
    if type(value) is float:return {"f64":value.hex()}
    if isinstance(value,list):return [binary(x) for x in value]
    if isinstance(value,dict):return {k:binary(x) for k,x in value.items()}
    return value


def family():
    spec=importlib.util.spec_from_file_location("_044_pressure_frozen_family",FAMILY/"run.py")
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def api():
    original=family();s1,gui,service=original.api()
    gui.PRIVATE,gui.CYCLE=RAW,CYCLE
    return original,s1,gui,service


def request():
    return {"name":"human_eye_scene_observe","arguments":{"session_id":"m6-044-pressure-normal",
        "include_image":False,"query":{"mode":"task","objects":[{"name":"Pressure_Inner"},{"name":"Pressure_Outer"}],
        "requested_facts":["surface_proximity"]}}}


def freeze():
    RAW.mkdir(parents=True,exist_ok=True)
    fixed={name:pin(FINAL/name) for name in EXPECTED}
    need(all(ref["sha256"]==EXPECTED[name] for name,ref in fixed.items()),"one_fixed_density")
    geom=read(FINAL/"FINAL_GEOMETRY.json")
    need([geom[k]["name"] for k in ("left","right")]==["Pressure_Inner","Pressure_Outer"],"original_order")
    for key in ("left","right"):
        item=geom[key]
        need(len(item["faces"])==129 and len({tuple(f) for f in item["faces"]})==129,"unique_source_faces")
        for vertex in item["vertices_world"]:
            for value in vertex:
                need(type(value) in (int,float) and math.isfinite(value) and
                     struct.pack("<d",struct.unpack("<f",struct.pack("<f",value))[0])==struct.pack("<d",value),"exact_binary32")
    prior=read(Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_family/PLAN_02.json"))
    original_pressure_plan=Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_pressure/PLAN.json")
    need(request()==read(original_pressure_plan)["request"],"exact_preserved_ordinary_request")
    original,s1,_,_=api()
    arms=original.installed(s1)
    need(arms==prior["arms"],"same_unchanged_installs")
    sources={str(path):pin(path) for path in (Path(__file__),HERE/"build_scene.py",FAMILY/"capture.py",FAMILY/"run.py")}
    sources.update(prior["sources"])
    plan=dict(schema="m6-045-ordinary-boundary-plan-v1",cycle_id=CYCLE,status="frozen_before_native_genesis",
        contract="3e9e06ea381d3ad3669f7ac14e5ba25e4ba245f0",fixed=fixed,family_plan=pin(Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_family/PLAN_02.json")),
        original_pressure_plan=pin(original_pressure_plan),n=129,possible_triangle_pairs=16641,
        original_limits=dict(faces=4096,narrow_phase_pairs=16384,work_units=1179648,request_budget_s=30.0),
        reused_044_tooling={name:pin(HERE.parents[1]/"m6_r3_fresh_budget_044/live_pressure"/name) for name in ("run.py","build_scene.py")},
        base_asset=prior["asset"],support=prior["support"],sources=sources,arms=arms,request=request(),order="ABC",
        genesis="one ordinary owned GUI from exact family asset copy; replace only private RAM objects with fixed world arrays, identity transforms, unit1/frame1; save one new pressure.blend copy; close",
        reopen="different ordinary GUI PID opens the saved private artifact, recaptures all original vertices/faces bitwise before any ABC call",
        query="same task objects order, surface_proximity only, one fresh service/state/audit per arm",
        limits="unchanged original request30s, face4096, narrow16384, work1179648, no prepay, no candidate patch",
        primary="descriptive original tool write through complete original business decode; startup, save/reopen, EOF and cleanup separate",
        source_kind="sole fixed synthetic distinct non-degenerate triangle unions, not a changed density",model_turns=0)
    print(save(PLAN,plan),flush=True)


def capture(host,folder,label,plan):
    reply=host.run((FAMILY/"capture.py").read_text(encoding="utf-8"),timeout_s=30)
    save(folder/(label+"_RPC.json"),reply)
    need(reply["response"]["status"]=="success","actual_capture_success")
    lines=reply["response"]["result"]["result"].splitlines()
    text,=[line.split(":",1)[1] for line in lines if line.startswith("M6_044_CAPTURE:")]
    value=json.loads(text);save(folder/(label+".json"),value)
    source=value["source"]
    need(source["pid"]==host.pid and source["main_thread"] and not source["background"] and source["scale_length"]==1.0
         and source["frame"]==1 and source["subframe"]==0.0 and Path(source["asset"]).resolve()==host.workspace/"input.blend",
         "ordinary_current_geometry")
    geom=read(plan["fixed"]["FINAL_GEOMETRY.json"]["path"])
    items={row["name"]:row for row in value["objects"] if row["type"]=="MESH"}
    need(set(items)=={"Pressure_Inner","Pressure_Outer"},"only_fixed_meshes")
    identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    for key in ("left","right"):
        expected=geom[key];actual=items[expected["name"]]
        need(binary(actual["matrix_world"])==binary(identity) and actual["modifier_types"]==[] and actual["parent"] is None,
             "identity_transform")
        for mode in ("native","evaluated"):
            got=actual[mode]
            need(binary(got["vertices_local"])==binary(expected["vertices_world"])==binary(got["vertices_world_m"]),"source_coordinate_bytes")
            need(got["triangles"]==expected["faces"]==got["native_polygon_vertices"] and
                 got["source_triangle_rows"]==got["triangle_polygons"]==list(range(129)),"native_source_order")
    return value


def normalize(body,source):
    value=deepcopy(body)
    if "binding" in value:
        need(value["binding"]["runtime_source_sha256"]==source,"normalizer_source")
        value["binding"]["runtime_source_sha256"]="validated_runtime"
    if "trace_id" in value:value["trace_id"]="validated_trace"
    return binary(value)


def validate(folder,record,plan):
    source=plan["arms"][record["arm"]]["source_sha256"]
    answer=record["answer"];body=answer["result"];mid=answer["timing"]["id"]
    startup=read(folder/"client/STARTUP.json")
    ident=startup["hello"]["result"]["_meta"]["human_eye"]
    need(ident["source_sha256"]==source and ident["source_file_count"]==143 and ident["production_mode"],"actual_install")
    cfg=read(folder/"client/CONFIG.json")
    need(cfg["request_budget_s"]==cfg["blender"]["timeout_s"]==30.0 and cfg["expected_identity"]=={"source_sha256":source},"original_budget")
    tx,rx=folder/"client"/(mid+".TX.bin"),folder/"client"/(mid+".RX.bin")
    sent,received=read(tx),read(rx)
    need(sent["params"]==plan["request"] and sent["id"]==received["id"]==mid,"exact_original_wire")
    record.update(request=pin(tx),response=pin(rx))
    logs=[json.loads(line) for line in (folder/"client/AUDIT.jsonl").read_bytes().splitlines() if line]
    trace_events=[e for e in logs if e.get("event")=="request_trace" and str(e["trace"]["annotations"].get("mcp_request_id"))==mid]
    need(len(trace_events)==1,"one_trace")
    event=trace_events[0];trace=event["trace"]
    need(event["pid"]==trace["pid"]==record["product_pid"] and event["runtime_identity"]["build_id"]=="sha256:"+source and
         event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"]==source,"source_bound_trace")
    record["trace"]=trace
    observed=[e for e in logs if e.get("event")=="observe" and e.get("request_id")==trace["request_id"]]
    record["observe_records"]=observed
    record["work"]=observed[0].get("task_work") if len(observed)==1 else None
    record["entry_rejected"]=bool(answer["tool_error"] or answer["rpc_error"])
    if record["entry_rejected"]:
        record.update(distance_known=False,distance_m=None,entry_reason=body,unknown_reason="original_entry_rejection")
        return
    need(json.loads(received["result"]["content"][0]["text"])==body and len(received["result"]["content"])==1,"original_reply_form")
    need(body["binding"]["runtime_source_sha256"]==source and body["trace_id"]==trace["trace_id"],"body_source_trace")
    need(len(observed)==1 and observed[0]["scene_revision"]==body["binding"]["scene_revision"],"current_revision")
    fs,_=family().facts(body);sf=fs["surface_proximity"]
    need(set(fs)=={"surface_proximity"},"surface_only_original_question")
    value=sf.get("value");distance=value.get("distance_m") if isinstance(value,dict) else None
    known=sf.get("status")=="measured" and type(distance) in (int,float) and math.isfinite(distance)
    truth=read(plan["fixed"]["FINAL_INDEPENDENT_TRUTH.json"]["path"])
    expected=math.sqrt(float(Fraction(truth["distance_squared_exact"])))
    if known:
        need(binary(distance)==binary(expected),"exact_published_distance")
        points=value["nearest_witness"]
        want=[[float(Fraction(c)) for c in point] for point in truth["unique_witness_world_exact"]]
        need(binary([points["a"],points["b"]])==binary(want),"unique_exact_published_points")
    else:need(distance is None,"no_partial_unknown_distance")
    record.update(public_status=body["status"],surface_fact=sf,distance_known=known,distance_m=distance,
        unknown_reason=sf.get("reason") if not known else None,no_partial_unknown_distance=known or distance is None,
        work=observed[0].get("task_work"),independent_canonical_native_face_pair=truth["canonical_native_face_pair"],
        native_index_scope="public original task fact has point witness; canonical native pair follows the frozen unique witness and verified source mapping",
        semantic=normalize(body,source))


def cell(folder,host,arm,plan,service):
    folder.mkdir();client=None
    record=dict(arm=arm,host_pid=host.pid,errors=[],started_ns=NOW())
    try:
        client=service.Client(folder/"client",host,"Pressure",plan["arms"][arm]);client.open("Pressure")
        record.update(product_pid=client.server_pid,wrapper_pid=client.worker.pid,ready_ns=NOW(),
                      product_before=service.transport.counters(client.server_pid))
        answer=client.observe(plan["request"]);record["body_decoded_ns"]=NOW();record["answer"]=answer
        record["business_ns"]=record["body_decoded_ns"]-answer["timing"]["started_ns"]
        record["product_after"]=service.transport.counters(client.server_pid)
    except BaseException:record["errors"].append(dict(stage="business",traceback=traceback.format_exc()))
    finally:
        if client:
            try:
                code=client.close();record["product_close"]=read(folder/"client/CLOSE.json")
                need(code==0 and record["product_close"]["method"]=="eof" and not client.reader.is_alive(),"normal_EOF")
            except BaseException:record["errors"].append(dict(stage="product_close",traceback=traceback.format_exc()))
    record["through_EOF_ns"]=NOW()-record["started_ns"]
    if not record["errors"]:
        try:validate(folder,record,plan)
        except BaseException:record["errors"].append(dict(stage="after_EOF_validation",traceback=traceback.format_exc()))
    record.update(valid=not record["errors"],ended_ns=NOW())
    save(folder/"CELL.json",record);print(arm,record["valid"],record.get("distance_known"),record.get("distance_m"),flush=True)
    return record


def run(window_path):
    plan=read(PLAN)
    for ref in (*plan["fixed"].values(),*plan["sources"].values(),*plan["support"].values(),
                *plan["reused_044_tooling"].values(),plan["base_asset"],plan["family_plan"],plan["original_pressure_plan"]):check(ref)
    window=read(window_path)
    need(window["cycle_id"]==CYCLE and window["status"]=="available" and window.get("token"),"new_pressure_window")
    original,s1,gui,service=api();need(original.installed(s1)==plan["arms"],"unchanged_installs")
    output=RAW/"attempt_001";output.mkdir()
    report=dict(schema="m6-045-boundary-ordinary-result-v1",plan=pin(PLAN),window=pin(window_path),started_ns=NOW(),errors=[],cells={})
    writer=reader=None
    destination=RAW/"authored/boundary.blend";destination.parent.mkdir()
    try:
        gui.ASSET_SHAS={plan["base_asset"]["sha256"]:"closed_family_genesis_copy"}
        writer=gui.Owned(output/"genesis",plan["base_asset"],plan["support"],window)
        report["writer_pid"]=writer.pid
        job=save(output/"BUILD_INPUT.json",dict(geometry=plan["fixed"]["FINAL_GEOMETRY.json"],destination=str(destination),owned_root=str(RAW)))
        script="M6_044_PRESSURE_BUILD_JOB="+repr(job["path"])+"\n"+(HERE/"build_scene.py").read_text(encoding="utf-8")
        built=writer.run(script,timeout_s=30);save(output/"BUILD_RPC.json",built)
        need(built["response"]["status"]=="success" and destination.is_file(),"saved_private_pressure")
        writer_capture=capture(writer,output,"SAVED_RAM",plan)
        artifact=pin(destination);save(output/"SAVED_ARTIFACT.json",dict(asset=artifact,geometry=plan["fixed"]["FINAL_GEOMETRY.json"],
            writer_pid=writer.pid,writer_capture=pin(output/"SAVED_RAM.json")))
        report["writer_close"]=writer.close();writer=None
        need(report["writer_close"]["status"]=="pass","writer_normal_exit")
        gui.ASSET_SHAS={artifact["sha256"]:"044_fixed_pressure_saved_artifact"}
        reader=gui.Owned(output/"reopen",artifact,plan["support"],window)
        report.update(reader_pid=reader.pid,port=reader.port,saved_artifact=artifact)
        need(report["writer_pid"]!=reader.pid,"independent_fresh_process_reopen")
        before=capture(reader,output,"BEFORE",plan)
        report["actual_saved_geometry_verified"]=True
        report["host_before"]=service.transport.counters(reader.pid)
        for arm in plan["order"]:
            report["cells"][arm]=cell(output/arm,reader,arm,plan,service)
            need(report["cells"][arm]["valid"],"invalid_arm_"+arm)
        report["host_after"]=service.transport.counters(reader.pid)
        after=capture(reader,output,"AFTER",plan)
        need(binary(before)==binary(after),"read_only_scene_preserved")
        report["scene_preserved"]=True
        report["B_success_C_unknown"]=report["cells"]["B"]["distance_known"] and not report["cells"]["C"]["distance_known"]
        report["coverage_comparisons"]={left+"_to_"+right:dict(
            left_known=report["cells"][left]["distance_known"],right_known=report["cells"][right]["distance_known"],
            newly_unknown=report["cells"][left]["distance_known"] and not report["cells"][right]["distance_known"],
            right_original_reason=report["cells"][right].get("unknown_reason")) for left,right in (("A","B"),("A","C"),("B","C"))}
        report["all_known"]=all(c["distance_known"] for c in report["cells"].values())
        if report["all_known"]:
            need(all(report["cells"][a]["semantic"]==report["cells"]["A"]["semantic"] for a in "BC"),"same_host_original_public_equality")
    except BaseException:report["errors"].append(traceback.format_exc())
    finally:
        for name,host in (("reader_close",reader),("writer_close",writer)):
            if host:
                try:
                    report[name]=host.close();need(report[name]["status"]=="pass" and report[name]["process_reaped"] and
                         report[name]["forced"] is None,"normal_native_close")
                except BaseException:report["errors"].append(name+":"+traceback.format_exc())
    report.update(ended_ns=NOW(),status="pass" if not report["errors"] and len(report["cells"])==3 else "failed_or_incomplete")
    report["full_lifecycle_wall_ns"]=report["ended_ns"]-report["started_ns"]
    print(save(output/"RESULTS.json",report),flush=True)
    return int(report["status"]!="pass")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("mode",choices=("freeze","run"));parser.add_argument("--window",type=Path)
    args=parser.parse_args()
    freeze() if args.mode=="freeze" else sys.exit(run(args.window))
