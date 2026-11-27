"""Measure complete H3 replay first/repeat in 36 independent installed processes."""
from __future__ import annotations

import argparse
from itertools import permutations
from pathlib import Path
from statistics import median
import json
import os
import subprocess
import sys
import time
import traceback

from common import ROOT, CYCLE, PLAN_042, PYTHON, activate, base_install, check, dump, installation, pin, read, replay_inputs

HERE = Path(__file__).resolve().parent
FOLDER = ROOT / "timing"
PLAN = FOLDER / "PLAN.json"
CANDIDATE = ROOT / "candidate/PINS.json"
ACK = "46ae148425541e11280812b0a85a3de72d8f45b7"
NOW = time.perf_counter_ns


def freeze(quality, holdouts):
    FOLDER.mkdir(exist_ok=False)
    old, initial = replay_inputs()
    inputs = read(CANDIDATE)
    candidate = installation(check(inputs["binding"]))
    assert candidate["identity"]["source_sha256"] == inputs["source_sha256"]
    installed = {"A": base_install("A"), "B": base_install("B"), "C": candidate}
    assert installed["B"]["binding"] == inputs["baseline_binding"]
    assert read(ROOT/"mechanism/SUMMARY.json")["status"] == "pass"
    # Only the fixed, separately audited quality receipts admit formal timing.
    assert all(read(path)["status"] == "pass" for path in (quality, holdouts))
    plan = {"status": "prepared", "cycle_id": CYCLE, "contract": ACK, "candidate_binding": pin(CANDIDATE),
            "release_bindings": installed, "driver": pin(__file__), "common": pin(HERE/"common.py"),
            "mechanism": pin(ROOT/"mechanism/SUMMARY.json"), "quality": pin(quality), "holdouts": pin(holdouts),
            "capture": pin(initial), "initial_042": pin(PLAN_042), "query": old["query"],
            "expected_public": old["expected_public"], "request_budget_s": 30.0,
            "orders": ["".join(v) for v in permutations("ABC")] * 2,
            "process_initial_condition": "one new Windows process per cell, same imported normal installed package and full capture restoration per request, OS cache persists",
            "clock": "full decoded local replay: perf_counter_ns from restored packet request into the service through projection and MCP encoding; no live TCP/Blender or instrumented solver",
            "gate": {"minimum_save_vs_R3_ms": .75, "minimum_faster_pairs": 9,
                    "maximum_delta_vs_032_ms": .75, "maximum_relative_vs_032": .05,
                    "total_triplets": 12},
            "real_holdout": "029 original unrotated assembly Obj_014 to Obj_003, Yanyite low box as recorded in holdouts",
            "env_threads": {k:"1" for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}
    print(dump(PLAN, plan))


def worker(plan_path, group, arm, output):
    plan=read(plan_path)
    receipt={"status":"fail","group":group,"arm":arm,"plan":pin(plan_path),"rows":[],"host_calls":0,
             "native_or_gui_started":False,"mechanism_observer":False}
    try:
        expected=plan["release_bindings"][arm]
        actual_install=installation(check(expected["binding"]))
        assert actual_install==expected
        activate(actual_install)
        from human_eye_plugin import mcp_transport, source_region, surface_proximity
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.runtime_identity import runtime_identity
        identity=runtime_identity(mode="live")
        assert identity["source_sha256"]==actual_install["identity"]["source_sha256"]
        assert identity["distribution_version"]==actual_install["identity"]["distribution_version"]
        assert len(identity["source_files"])==143
        assert Path(surface_proximity.__file__).resolve()==(
            Path(actual_install["site"])/"human_eye_plugin/surface_proximity.py").resolve()
        receipt["actual_identity"]={k:identity[k] for k in ("source_sha256","distribution_version","implementation_revision")}
        receipt["kernel"]=pin(Path(surface_proximity.__file__))
        raw=check(plan["capture"]).read_bytes()
        template=json.loads(raw)
        binding=template["binding"]

        class CaptureReplay:
            _readonly_host_source_sha256=binding["host_source_sha256"]
            calls=0
            def capture_source_region_pair(self, target, reference, box, deadline_ns, max_response_bytes):
                assert NOW()<deadline_ns
                assert (target, reference, box)==(binding["target_selector"], binding["reference_selector"], binding["world_box_m"])
                self.calls+=1
                return json.loads(raw)

        host=CaptureReplay()
        config={"schema_version":"1.0","enabled":True,"observe_on_prompt":False,
            "project_root":actual_install["site"],"state_file":str(output/"STATE.json"),
            "audit_file":str(output/"AUDIT.jsonl"),"request_budget_s":plan["request_budget_s"],
            "expected_identity":{"source_sha256":actual_install["identity"]["source_sha256"]}}
        dump(output/"CONFIG.json",config)
        live=LiveSpatialService(output/"CONFIG.json",host=host)
        normalized=source_region.validate_scoped_measurement_arguments({"include_image":False,"query":plan["query"]})
        for step in ("first","repeat"):
            with live._request_budget():
                started=NOW()
                value=live._measure_selective_source_region("m6-043-fixed-H3",normalized,include_image=False)
                measured=NOW()
                public=source_region.project_scoped_measurement(value,normalized)
                projected=NOW()
                text=json.dumps(public,ensure_ascii=False,allow_nan=False,separators=(",",":"))
                serialized=NOW()
                wire=mcp_transport.encode_response({"jsonrpc":"2.0","id":"replay","result":{"content":[{"type":"text","text":text}],"isError":False}})
                finished=NOW()
                live._check_request_budget("before_replay_publication",publication=True)
            assert public==plan["expected_public"] and len(wire)>0
            stages=value["stages"]
            names=("host_read","capture_validation","region_array_preparation","task_measurement","service_total")
            native={n:stages[n] for n in names}
            measured_top=sorted((x["started_ns"],x["closed_ns"]) for k,x in native.items() if k!="service_total")
            assert all(started<=a<=b<=measured for a,b in measured_top)
            assert all(a[1]<=b[0] for a,b in zip(measured_top,measured_top[1:]))
            work=value["work"]["task_query"]
            assert work["surface_pair_count"]==1 and work["surface_pair_cache_hit"] is False
            row={"step":step,"runtime_intervals_ns":native,"started_ns":started,"finished_ns":finished,"public":public,
                "work":value["work"],"wire_bytes":len(wire),"full_ns":finished-started,
                "service_ns":measured-started,"projection_ns":projected-measured,
                "content_encode_ns":serialized-projected,"wire_encode_ns":finished-serialized,
                "service_residual_ns":(measured-started)-sum(x[1]-x[0] for x in measured_top)}
            dump(output/(step+".json"),row)
            receipt["rows"].append({"step":step,"raw":pin(output/(step+".json")),"full_ns":row["full_ns"]})
        assert host.calls==2
        receipt.update(status="pass",restored_capture_calls=host.calls)
    except Exception:
        receipt["error"]=traceback.format_exc()
    dump(output/"CELL.json",receipt)
    return int(receipt["status"]!="pass")


def run(window):
    plan=read(PLAN)
    assert window["cycle_id"]==CYCLE and window["status"]=="available" and window["token"]
    for key in ("driver","common","initial_042","mechanism","quality","holdouts","capture","candidate_binding"):
        check(plan[key])
    folder=FOLDER/"attempt_001"
    folder.mkdir()
    begin=NOW()
    groups=[]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("HUMAN_EYE_","PYTHON"))}
    env.update(plan["env_threads"])
    for index, order in enumerate(plan["orders"],1):
        cells={}
        for arm in order:
            path=folder/f"{index:02d}_{arm}"
            path.mkdir()
            command=[str(PYTHON),"-E","-s","-B",str(Path(__file__).resolve()),"worker","--arm",arm,
                     "--group",str(index),"--output",str(path),"--plan",str(PLAN)]
            started=NOW()
            with (path/"OUT.bin").open("xb") as out, (path/"ERR.bin").open("xb") as err:
                process=subprocess.Popen(command,cwd=path,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                code=process.wait()
            stopped=NOW()
            ref=pin(path/"CELL.json") if (path/"CELL.json").exists() else None
            receipt=read(ref["path"]) if ref else {}
            launch={"argv":command,"launcher_pid":process.pid,"exit":code,"reaped":process.poll() is not None,
                    "start_ns":started,"closed_ns":stopped,"lifecycle_ns":stopped-started,"cell":ref}
            cells[arm]={"process":dump(path/"PROCESS.json",launch),"valid":code==0 and receipt.get("status")=="pass",
                        "rows":receipt.get("rows",[])}
            print(index,arm,"ok" if cells[arm]["valid"] else "failed",flush=True)
        item={"group":index,"order":order,"cells":cells,"valid":all(c["valid"] for c in cells.values())}
        if item["valid"]:
            first={arm: cells[arm]["rows"][0]["full_ns"]/1e6 for arm in "ABC"}
            warm={arm: cells[arm]["rows"][1]["full_ns"]/1e6 for arm in "ABC"}
            a,b,c=(warm[arm] for arm in "ABC")
            item.update(first_ms=first,repeat_ms=warm,
                        saving_C_vs_B_ms=b-c,delta_C_vs_A_ms=c-a,relative_C_vs_A=c/a-1)
        groups.append(item)

    result={"status":"incomplete","plan":pin(PLAN),"wall_ns":NOW()-begin,"groups":groups,
            "valid_triplets":sum(g["valid"] for g in groups),"expected_triplets":12,"cells_started":36,
            "blender_started":False}
    if result["valid_triplets"]==12:
        saving=median(g["saving_C_vs_B_ms"] for g in groups)
        faster=sum(g["saving_C_vs_B_ms"]>0 for g in groups)
        delta=median(g["delta_C_vs_A_ms"] for g in groups)
        relative=median(g["relative_C_vs_A"] for g in groups)
        checks={"save_R3_at_least_0_75_ms":saving>=.75,"faster_R3_at_least_9_of_12":faster>=9,
                "slower_032_no_more_than_0_75_ms":delta<=.75,"slower_032_no_more_than_5_percent":relative<=.05}
        result.update(status="pass" if all(checks.values()) else "fail_timing_gate",
            paired_median_saving_C_vs_B_ms=saving,C_faster_than_B=faster,
            paired_median_delta_C_vs_A_ms=delta,paired_median_relative_C_vs_A=relative,
            checks=checks,first_arm_medians_ms={a:median(g["first_ms"][a] for g in groups) for a in "ABC"},
            repeat_arm_medians_ms={a:median(g["repeat_ms"][a] for g in groups) for a in "ABC"})
    print(dump(folder/"RESULTS.json",result))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("freeze","run","worker"))
    parser.add_argument("--quality",type=Path)
    parser.add_argument("--holdouts",type=Path)
    parser.add_argument("--window",type=Path)
    parser.add_argument("--plan",type=Path)
    parser.add_argument("--group",type=int)
    parser.add_argument("--arm")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.command=="freeze": freeze(args.quality,args.holdouts)
    elif args.command=="run": run(read(args.window))
    else: raise SystemExit(worker(args.plan,args.group,args.arm,args.output))
