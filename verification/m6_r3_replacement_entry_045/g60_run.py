"""Run the frozen G60 ordinary entry and mark the original client's full lifecycle."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys
import traceback
from types import SimpleNamespace

from g60_client import client_class
from g60_windows import NOW, mark, OS_BRACKET_100NS, DRIFT_TOLERANCE_NS

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY")
RAW=ROOT/"g60"
CYCLE=ROOT.name
CONTRACT="3e9e06ea381d3ad3669f7ac14e5ba25e4ba245f0"
OLD_PLAN=ROOT.parent/"M6-043-R3-REGION-ATTRIBUTION/live/g60/PLAN_03.json"
OLD_SHA="ca14c4f0147da180d330e947689cd411ac56310e5e860d1c197e78e9ab5f585e"
CURRENT=RAW/"PLAN.json"


def original():
    path=HERE.parent/"m6_r3_region_attribution_043/live_g60/run.py"
    spec=importlib.util.spec_from_file_location("_045_original_043_g60",path)
    driver=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver,sys.modules["common"]


OLD,shared=original()
read,pin,check,need,dump=OLD.read,OLD.pin,OLD.check,OLD.need,OLD.dump
ORDERS,STEPS=OLD.ORDERS,OLD.STEPS


def setup():
    _,gui,svc=OLD.api()
    # Source bindings and business/clientInfo stay at 043; the GUI owns just 045 paths.
    shared.RAW=RAW
    gui.PRIVATE,gui.CYCLE=RAW,CYCLE
    OLD.cell=cell
    return gui,svc


def freeze():
    assert pin(OLD_PLAN)["sha256"]==OLD_SHA
    plan=OLD.validate_plan(OLD_PLAN)
    setup()
    RAW.mkdir(parents=True,exist_ok=False)
    verified={p.name:pin(p) for p in (Path(__file__),HERE/"g60_windows.py",HERE/"g60_client.py")}
    data=dict(plan)
    data.update(schema="m6-045-g60-plan-v1",status="frozen_not_launched",cycle_id=CYCLE,contract=CONTRACT,
                inherited=pin(OLD_PLAN),  # 043 request and archival sequence are preserved.
                source_045=verified,preflight={"no_Blender":True,"arm":"A","only_initialize_and_tools_list":True},
                clocks={"workflow":"original 043 client creation before CONFIG through EOF, archive and CLOSE readback",
                        "business":"original first overview stdio write through complete scan decode",
                        "process":"max(actual interpreter,wrapper OS exit FILETIME) minus wrapper OS creation FILETIME",
                        "reader":"original reader target return on parent monotonic clock plus actual join/inactive",
                        "wall_clock_tolerance_ns":DRIFT_TOLERANCE_NS,"os_exit_bracket_100ns":OS_BRACKET_100NS,
                        "all_trace_marks_in_memory_before_post_workflow_report":True,
                        "reported_filetime_clock_comparisons_use_same_clock_only":True},
                sampling={"owned_processes":"held from live audited identity/ancestry until GetProcessTimes after full client close",
                          "cpu":"GetProcessTimes totals; existing actual process boundary counters preserved",
                          "memory":"per-PID original observed process boundary samples, not a simultaneous tree peak",
                          "debug_clock_quality_failure":"unmeasured lifecycle; valid original business still reported"},
                lifecycle_gate={"minimum_saving_C_vs_A_strictly_above":0,"maximum_relative_C_vs_B":.05,
                                "expected_triplets":6},
                ordinary_read_only=True, model_turns=0)
    print(dump(CURRENT,data),flush=True)


def current():
    assert pin(OLD_PLAN)["sha256"]==OLD_SHA
    expected=read(OLD_PLAN)
    plan=read(CURRENT)
    assert plan["cycle_id"]==CYCLE and plan["contract"]==CONTRACT
    assert check(plan["inherited"])==OLD_PLAN.resolve()
    for source in (*plan["source_045"].values(),*expected["sources"].values(),*expected["support"].values(),
                   *expected["truth"].values(),*expected["release_bindings"].values(),
                   expected["candidate"],expected["asset"],expected["snapshot_fixture"]):
        check(source)
    for key in ("orders","requests","arms","asset","support","truth","release_bindings","expected_snapshot"):
        assert plan[key]==expected[key], key
    assert OLD.arms()==expected["arms"] and OLD.requests()==expected["requests"]
    setup()
    return plan


def close_original_readback(client,record):
    if client.worker is None:
        if hasattr(client,"stderr"):
            client.stderr.close()
        return
    code=client.close()
    client.mark("close_readback_begin")
    raw=(client.folder/"CLOSE.json").read_bytes()
    record["product_close"]=json.loads(raw)
    client.read_bytes["close_readback"]=[len(raw)]
    client.mark("close_readback_end")
    assert code==0 and record["product_close"]["method"]=="eof" and not client.reader.is_alive()


def preflight():
    plan=current()
    folder=RAW/"preflight_001"
    folder.mkdir()
    client=client_class(OLD.api()[2])(folder/"client",SimpleNamespace(host="127.0.0.1",port=9),plan["arms"]["A"])
    rec={"status":"failed","plan":pin(CURRENT),"geometry_requests":0,"Blender":0,"errors":[]}
    started=NOW()
    try:
        client.launch()
        client.open("G60")
    except Exception:
        rec["errors"].append(traceback.format_exc())
    finally:
        try:
            close_original_readback(client,rec)
        except Exception:
            rec["errors"].append(traceback.format_exc())
    finished=NOW()
    client.mark("client_end")
    rec["lifecycle"]=client.lifecycle()
    lc=rec["lifecycle"]
    rec.update(workflow_start_ns=started,workflow_end_ns=finished,workflow_ns=finished-started)
    if lc["valid"] and not rec["errors"]:
        assert lc["archive"]["files"]==5 and lc["reader"]["joined_and_inactive"]
        assert lc["exit_at_wrapper_wait"]=={"wrapper":0,"service":0}
        rec["status"]="pass"
    marks=[e["filetime_observation_after_ns"]-e["at_ns"] for e in lc["events"] if "filetime_100ns" in e]
    rec["lightweight_timestamp_probes"]={"count":len(marks),"within_bracket_ns_sum":sum(marks),
                                         "within_bracket_ns_max":max(marks,default=0),"excluded_from_reduction":False}
    print(dump(folder/"RESULTS.json",rec),flush=True)
    return int(rec["status"]!="pass")


def cell(folder,host,before,arm,plan):
    svc=OLD.api()[2]
    folder.mkdir()
    rec=dict(arm=arm,host_pid=host.pid,host=host.host,port=host.port,rows=[],errors=[],
             started_ns=NOW(),validation_outside_primary=True)
    workflow_start=NOW()
    client=client_class(svc)(folder/"client",host,plan["arms"][arm])
    try:
        client.launch()
        client.open("G60")
        rec.update(product_pid=client.server_pid,wrapper_pid=client.worker.pid,ready_ns=NOW())
        mark_cpu=NOW()
        rec["product_before"]=svc.transport.counters(client.server_pid)
        rec["resource_before_ns"]=NOW()-mark_cpu
        client.mark("before_first_observe")
        for step in STEPS:
            row=client.observe(plan["requests"][step])
            row.update(step=step,body_decoded_ns=NOW())
            rec["rows"].append(row)
        rec["last_reply_ns"]=rec["rows"][-1]["body_decoded_ns"]
        client.mark("last_business_decode")
        mark_cpu=NOW()
        rec["product_after"]=svc.transport.counters(client.server_pid)
        rec["resource_after_ns"]=NOW()-mark_cpu
    except Exception:
        rec["errors"].append(dict(stage="business",traceback=traceback.format_exc()))
    finally:
        try:
            close_original_readback(client,rec)
        except Exception:
            rec["errors"].append(dict(stage="product_close",traceback=traceback.format_exc()))
    end=NOW()
    client.mark("client_end")
    rec.update(workflow_start_ns=workflow_start,workflow_end_ns=end,workflow_ns=end-workflow_start)
    try:
        rec["lifecycle"]=client.lifecycle()
    except Exception:
        rec["lifecycle"]={"valid":False,"errors":[traceback.format_exc()],"os_survival_ns":None}
    if len(rec["rows"])==3:
        first=rec["rows"][0]["timing"]["started_ns"]
        rec.update(through_scan_reply_ns=rec["last_reply_ns"]-workflow_start,business_ns=rec["last_reply_ns"]-first,
                   startup_discovery_ns=first-workflow_start,product_close_and_final_counter_ns=end-rec["last_reply_ns"])
    if not rec["errors"]:
        try:
            rec["semantic"]=OLD.audit_rows(folder,rec,plan,before)
            for row in rec["rows"]:
                dump(folder/(row["step"]+".json"),row)
        except Exception:
            rec["errors"].append(dict(stage="after_eof_validation",traceback=traceback.format_exc()))
    rec.update(ended_ns=NOW(),valid=not rec["errors"] and len(rec["rows"])==3)
    dump(folder/"CELL.json",rec)
    print(folder.name,"business",rec["valid"],"lifetime",rec["lifecycle"]["valid"],flush=True)
    return rec


def evaluation(rows,col,threshold,faster,expected=6):
    valid=[r[col] for r in rows if isinstance(r.get(col),dict)]
    result={"complete_groups":len(valid),"planned_groups":expected,"status":"incomplete_or_unmeasured"}
    if len(valid)==expected:
        saving=median(1-r["C"]/r["A"] for r in valid)
        change=median(r["C"]/r["B"]-1 for r in valid)
        count=sum(r["C"]<r["A"] for r in valid)
        gate=(saving>0 if col=="process_ns" else saving>=threshold and count>=faster) and change<=.05
        result.update(status="pass" if gate else "fail",median_saving_C_vs_A=saving,median_delta_C_vs_B=change,
                      median_saving_B_vs_A=median(1-r["B"]/r["A"] for r in valid),C_faster_A=count,
                      C_faster_B=sum(r["C"]<r["B"] for r in valid),
                      B_faster_A=sum(r["B"]<r["A"] for r in valid),
                      medians_ns={a:median(r[a] for r in valid) for a in "ABC"})
    return result


def run(window_path):
    plan=current()
    window=read(window_path)
    assert window["cycle_id"]==CYCLE and window["status"]=="available" and window["token"]
    preflight_path=RAW/"preflight_001/RESULTS.json"
    pre=read(preflight_path)
    assert pre["status"]=="pass" and pre["plan"]==pin(CURRENT) and pre["geometry_requests"]==0
    out=RAW/"main_001"
    out.mkdir()
    dump(out/"WINDOW.json",window)
    started=NOW()
    groups=[]
    for idx,order in enumerate(ORDERS,1):
        path=out/(f"G{idx:02d}-{order}")
        group=OLD.group(path,idx,order,plan,window)
        g={"group":idx,"order":order,"valid":group["valid"],"raw":pin(path/"GROUP.json"),
           "full_gui_ns":group["full_native_and_QA_lifecycle_ns"],"lifetime_valid":False}
        if group["valid"]:
            cells=group["cells"]
            g["business_ns"]={a:cells[a]["business_ns"] for a in "ABC"}
            g["workflow_ns"]={a:cells[a]["workflow_ns"] for a in "ABC"}
            g["lifetime_valid"]=all(cells[a]["lifecycle"]["valid"] for a in "ABC")
            if g["lifetime_valid"]:
                g["process_ns"]={a:cells[a]["lifecycle"]["os_survival_ns"] for a in "ABC"}
        groups.append(g)
        if not group["valid"]:
            break
    result={"status":"observed","planned":list(ORDERS),"groups":groups,"plan":pin(CURRENT),
            "preflight":pin(preflight_path),"window":pin(window_path),"complete_window_ns":NOW()-started,
            "business":evaluation(groups,"business_ns",.10,5),
            "process_lifetime":evaluation(groups,"process_ns",0,0),
            "client_full_descriptive":evaluation(groups,"workflow_ns",.10,5)}
    print(dump(out/"RESULTS.json",result),flush=True)
    return int(not all(r["valid"] for r in groups))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("freeze","preflight","run"))
    parser.add_argument("--window",type=Path)
    cmd=parser.parse_args()
    if cmd.action=="freeze":
        freeze()
    else:
        raise SystemExit(preflight() if cmd.action=="preflight" else run(cmd.window))
