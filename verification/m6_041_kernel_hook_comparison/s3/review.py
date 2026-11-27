"""Independently re-score raw stdio and Hook receipts against the frozen 040/041 manifests."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=Path("D:/HumanEye/runs/M3-BVH-DEEP-COMPARE-040/entry_runs/live_matrix_001/r1/032")
def read(p):
    return json.loads(p.read_bytes())

def check(v,s):
    if not v:
        raise ValueError(s)

def put(p,obj):
    with p.open("x",encoding="utf8",newline="\n") as f:
        json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write("\n")

def norm(obj,src):
    b=dict(obj["binding"])
    check(b.pop("runtime_source_sha256")==src and len(obj["trace_id"])==32,"source or trace")
    return {**{k:v for k,v in obj.items() if k not in ("binding","trace_id")},"binding":b}

def geom(obj):
    return {k:v for k,v in obj.items() if k!="binding"}

def native_response(folder,label):
    response=read(next(folder.glob("*_"+label+"_RESPONSE.json")))
    check(response["result"].get("isError",False) is False and len(response["result"]["content"])==1,"stdio envelope")
    content=response["result"]["content"][0]
    check(content["type"]=="text", "real text receipt")
    return json.loads(content["text"])

def quant(data,q):
    vals=sorted(data)
    k=(len(vals)-1)*q
    i=int(k)
    return vals[i]+(vals[min(i+1,len(vals)-1)]-vals[i])*(k-i)

def stat(vals):
    rng=random.Random(41041)
    boot=[median(rng.choices(vals,k=len(vals))) for _ in range(20000)]
    return dict(raw=vals,n=len(vals),median=median(vals),observed_p95=quant(vals,.95),
                paired_bootstrap_percentile95=[quant(boot,.025),quant(boot,.975)])

def main(screen,resource):
    frozen=read(HERE/"FROZEN.json")
    pins=read(ROOT/"install/PINS.json")
    check(frozen["pins_sha256"]==hashlib.sha256((ROOT/"install/PINS.json").read_bytes()).hexdigest(),"installed pins")
    blocks=[]
    attempts=[]
    historical={label:norm(read(OLD/"MCP"/(label+"_first.json")),
                            "0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241") for label in ("nearest","scan")}
    ho=json.loads(read(OLD/"RETURN.json")["output"]["hookSpecificOutput"]["additionalContext"])
    for folder,orders in [(screen,frozen["orders"]),(resource,["BCAD"])]:
        listed=read(folder/"RESULT.json")
        check(listed["expected"]==[[i,a] for i,o in enumerate(orders,1) for a in o] and
              listed["expected"]==[[x["block"],x["arm"]] for x in listed["slots"]],"external count/order")
        for i,order in enumerate(orders,1):
            block={}
            for a in order:
                slot=folder/(f"{i:02d}"+a)
                result=read(slot/"RECEIPT.json")
                job=read(slot/"JOB.json")
                native=read(slot/"native/TERMINAL_OWNERSHIP.json")
                h=json.loads((slot/"hook/STDOUT.bin").read_bytes())
                hv=json.loads(h["hookSpecificOutput"]["additionalContext"])
                role,dispatch=frozen["arms"][a]
                src=pins["identities"][role]["source_sha256"]
                check(hv["runtime_identity"]["build_id"]=="sha256:"+src and
                      hv["observation"]["objects"]==ho["observation"]["objects"] and len(hv["observation"]["objects"])==12
                      and h["hookSpecificOutput"]["hookEventName"]=="UserPromptSubmit","complete 12 native boxes")
                audit=[json.loads(l) for l in (slot/"hook/audit.jsonl").read_bytes().splitlines()]
                check([r["event"] for r in audit]==["observe","host_hook","request_trace"] and
                      audit[-1]["trace"]["trace_id"]==hv["correlation"]["trace_id"],"hook route and trace")
                for q in historical:
                    sides=[]
                    for sub,key in [("mcp",role),("reference","032")]:
                        d=slot/sub
                        stored=read(d/(q+".json"))
                        raw=native_response(d/"stdio",q)
                        check(stored==raw,"actual stdio wire "+q)
                        sides.append(norm(stored,pins["identities"][key]["source_sha256"]))
                    check(sides[0]==sides[1] and geom(sides[0])==geom(historical[q]),"complete response, current scene, frozen geometry")
                check(native["status"]=="pass" and native["source_unchanged"] and native["process_reaped"] and
                      not native["released_port"]["owned_listener"] and job["job"]["active_processes"]==0 and
                      not job["pids_end"] and job["code"]==0 and not job["timeout"] and result["good"],"closure")
                stamps=result["timing"]
                calls=read(slot/"mcp/CALLS.json")
                close=read(slot/"mcp/CLOSED.json")
                check([x["label"] for x in calls]==[None,None,"nearest","scan"],"request order")
                last=calls[-1]
                floor=(last["arrived_ns"]-stamps["t0_ns"]+last["response_parsed_and_archived_ns"]-last["rtt_ns"]+close["close_ns"])/1e6
                check(floor<=stamps["workflow_ms"] and abs(stamps["workflow_ms"]-stamps["through_reply_ms"]-stamps["product_close_ms"])<1e-7,"continuous business window")
                row=dict(arm=a,block=i,phase=folder.name,**result["timing"],job_cpu_ms=job["job"]["cpu_ns"]/1e6,
                         independently_timestamped_floor_ms=floor,receipt_validation_and_clock_gap_ms=stamps["workflow_ms"]-floor,
                         peak_group_working_set=job.get("peak_group_working_set"),
                         peak_group_private_bytes=job.get("peak_group_private_bytes"))
                block[a]=row
                attempts.append(row)
            if folder==screen:
                blocks.append(block)
    denom=["BA","DC","CA","DB","DA"]
    metrics=["workflow_ms","through_reply_ms","hook_ms","nearest_ms","scan_ms","actual_full_host_and_QA_ms","job_cpu_ms"]
    base={}
    for m in metrics:
        base[m]={a:stat([b[a][m] for b in blocks]) for a in "ABCD"}
    benefit={}
    for m in metrics:
        benefit[m]={}
        for x,y in denom:
            ratios=[100*(1-b[x][m]/b[y][m]) for b in blocks]
            benefit[m][x+"/"+y]={**stat(ratios),"faster":sum(r>0 for r in ratios)}
    interaction=stat([b["D"]["workflow_ms"]-b["B"]["workflow_ms"]-b["C"]["workflow_ms"]+b["A"]["workflow_ms"] for b in blocks])
    answers=benefit["workflow_ms"]["D/A"]
    output={"external_checks":"all", "phase":"screening","denom":{"complete_paired_blocks":len(blocks),
            "paired_scientific_slots":4*len(blocks),"separate_resource_slots":4},"by_arm":base,
            "paired_reductions_percent":benefit,"interaction_ms":interaction,"raw":attempts,
            "combined_performance_screen_pass":answers["median"]>=10 and answers["faster"]>=5,
            "CI":"percentile on 20000 bootstrap block resamples; only seven independent paired blocks; descriptive",
            "p95":"observed linear interpolation, not a qualified tail estimate"}
    put(HERE/"REVIEW.json",output)
    print(json.dumps({"n":len(blocks),"pass":output["combined_performance_screen_pass"],"medians":{a:v["median"] for a,v in base["workflow_ms"].items()},"D/A":answers["median"],"interaction":interaction["median"]}))
if __name__=="__main__":
    main(HERE/sys.argv[1],HERE/sys.argv[2])

