"""Post-run raw-only recomputation; imports no product and starts no process."""
from __future__ import annotations

from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/yanyite")
ORDERS = (("AF","FA","AF","FA"),("FA","AF","FA","AF"),("FA","AF","AF","FA"))
def read(p): return json.loads(Path(p).read_bytes())
def need(v,s):
    if not v:raise ValueError("049_recompute_"+s)
def pin(p):
    p=Path(p).resolve(strict=True)
    with p.open("rb") as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
    return {"path":str(p),"bytes":p.stat().st_size,"sha256":sha}
def check(r):need(pin(r["path"])==r,"file_changed");return Path(r["path"])

def main():
    result=read(RAW/"main_001/RESULTS.json");plan=read(check(result["plan"]))
    out={"schema":"m6-049-yanyite-independent-recomputation-v1","status":"failed",
        "source":pin(__file__),"raw":pin(RAW/"main_001/RESULTS.json"),"plan":result["plan"],"errors":[],
        "no_product_imports_or_calls":True}
    try:
        need(plan["orders"]==[list(x) for x in ORDERS],"fixed_orders")
        for ref in plan["sources"]:check(ref)
        check(plan["candidate"])
        hosts=[read(check(ref)) for ref in result["hosts"]]
        need(len(hosts)==3,"three_hosts")
        pairs=[];resources=[];archive={"files":0,"bytes":0};generations=set();releases=[]
        for h in hosts:
            hi=h["host"];folder=RAW/"main_001"/f"H{hi}"
            before,after=read(folder/"BEFORE.json"),read(folder/"AFTER_TIMED.json")
            need(before["pid"]==h["pid"]==after["pid"] and before["background"] is False,"ordinary_owned_host")
            for key in ("geometry","frame","subframe","scale"):need(before[key]==after[key],"native_geometry_unchanged")
            need(h["GUI_close"]["status"]=="pass" and h["GUI_close"]["exit_code"]==0 and h["GUI_close"]["forced"] is None,"GUI_normal_exit")
            released=h["GUI_close"]["released_port"];need(not released["owned_listener"] and not released["any_listener"],"released_port")
            releases.append(released)
            for pi,order in enumerate(ORDERS[hi-1],1):
                cells=h["cells"][str(pi)];starts=[cells[a]["started_ns"] for a in order]
                need(starts==sorted(starts) and cells[order[0]]["ended_ns"]<=cells[order[1]]["started_ns"],"serial_order")
                values={}
                for arm in "AF":
                    c=cells[arm];cf=folder/f"P{pi}-{arm}"/"client"
                    need(c["valid"] and not c["errors"] and [r["step"] for r in c["rows"]]==["first_high","warm_high"],"valid_cell")
                    startup=read(cf/"STARTUP.json");ident=startup["hello"]["result"]["_meta"]["human_eye"]
                    need(ident["source_sha256"]==plan["arms"][arm]["source_sha256"] and ident["source_file_count"]==plan["arms"][arm]["source_count"],"actual_source_identity")
                    cfg=read(cf/"CONFIG.json");need(cfg["expected_identity"]["source_sha256"]==ident["source_sha256"] and cfg["request_budget_s"]==cfg["blender"]["timeout_s"]==30,"original_budget")
                    cmd=[*plan["arms"][arm]["command_prefix"],"serve","--config",str(cf/"CONFIG.json"),"--source-region-measurement"]
                    need(read(cf/"LAUNCH.json")["command"]==cmd,"plain_installed_launch")
                    need(c["close"]["method"]=="eof" and c["close"]["exit_code"]==0,"normal_EOF")
                    for row in c["rows"]:
                        t=row["timing"];req,resp=read(check(row["request"])),read(check(row["response"]))
                        need(req["method"]=="tools/call" and req["params"]==plan["requests"]["high"] and req["id"]==resp["id"]==t["id"],"actual_request")
                        body=json.loads(resp["result"]["content"][0]["text"])
                        need(body==row["result"] and not resp["result"].get("isError"),"actual_public_body")
                        need(row["business_ns"]==row["body_decoded_ns"]-t["started_ns"]>0 and row["body_decoded_ns"]>=t["closed_ns"],"complete_body_clock")
                        need(t["client_full_ns"]==t["wire_wait_ns"]+t["client_decode_ns"]==t["closed_ns"]-t["started_ns"],"wire_clock")
                        tr=row["telemetry"];need(tr["pid"]==c["product_pid"] and tr["annotations"]["delivery"]=="stdio_write_completed" and tr["annotations"]["include_image"] is False,"trace_publication")
                    need(c["rows"][0]["result"]==c["rows"][1]["result"],"first_repeat_geometry")
                    procs=c["processes"];need(procs["wrapper"]["pid"]==c["wrapper_pid"] and procs["service"]["pid"]==c["product_pid"],"actual_PIDs")
                    unique={}
                    for p in procs.values():
                        need(p["owned_held_handle"] and p["alive_at_bind"] and p["wait_result"]==0 and p["exit_code"]==0 and p["creation_time_100ns"]==p["bind_times"]["creation_time_100ns"]<p["exit_time_100ns"],"held_handle_exit")
                        unique[(p["pid"],p["creation_time_100ns"])]=p
                    need(not (set(unique)&generations),"independent_service_generations");generations.update(unique)
                    lifetime=(max(p["exit_time_100ns"] for p in unique.values())-procs["wrapper"]["creation_time_100ns"])*100
                    need(lifetime==c["os_survival_ns"]>0,"OS_survival_clock")
                    files=[*cf.glob("*.TX.bin"),*cf.glob("*.RX.bin")];need(len(files)==9,"raw_wire_inventory")
                    archive["files"]+=len(files);archive["bytes"]+=sum(p.stat().st_size for p in files)
                    resources.append({"host":hi,"pair":pi,"arm":arm,"os_survival_ns":lifetime,"client_full_ns":c["client_full_ns"],
                        "CPU_s":sum(p["user_100ns"]+p["kernel_100ns"] for p in unique.values())/1e7,
                        "last_business_peak_working_set_bytes":c["rows"][-1]["counters_after"].get("peak_working_set_bytes")})
                    values[arm]=c["rows"][1]["business_ns"]
                for j in (0,1):need(cells["A"]["rows"][j]["result"]==cells["F"]["rows"][j]["result"],"same_host_A_F_geometry")
                pairs.append({"host":hi,"pair":pi,"order":order,"A_ns":values["A"],"F_ns":values["F"],
                    "delta_ns":values["F"]-values["A"],"relative":Q(values["F"]-values["A"],values["A"])})
        need(len(pairs)==12,"all12_no_filter")
        delta=median(p["delta_ns"] for p in pairs);rel=median(p["relative"] for p in pairs)
        by_host=[{"host":i,"delta_ns":median(p["delta_ns"] for p in pairs if p["host"]==i)} for i in (1,2,3)]
        stable=delta>5_000_000 and rel>Q(1,20) and sum(p["delta_ns"]>0 for p in by_host)>=2
        need(result["timing"]["median_delta_ms"]==delta/1e6 and result["timing"]["stable_regression"]==stable,"recomputed_gate")
        out.update(status="pass",pairs=[dict(p,relative=float(p["relative"])) for p in pairs],
            median_delta_ms=delta/1e6,median_relative=float(rel),stable_regression=stable,by_host=by_host,
            resources=resources,raw_wire=archive,process_generations=len(generations),ports=releases,
            functional_status=result["H3_functional"],actual_timed_services=24,actual_timed_reads=48,
            limits="No summed process-tree peak; memory only original observed individual process peaks through final business boundary. Native lifetime clock is OS FILETIME. Client close includes reader, raw archive and receipt work; isolated archive duration was not measured. H3 total GUI lifespan also includes untimed functional reads/edit.")
    except Exception as exc:out["errors"].append(type(exc).__name__+": "+str(exc))
    target=RAW/"RECOMPUTED.json"
    with target.open("x",encoding="utf8",newline="\n") as f:json.dump(out,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps(pin(target)));return int(out["status"]!="pass")

if __name__=="__main__":raise SystemExit(main())
