"""Read-only re-scoring of the 041 evidence, Python 3.10+ standard library only."""
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
def read(name):
    return json.loads((HERE/name).read_bytes())
def need(condition, message):
    if not condition:
        raise ValueError(message)
def main():
    idx=read("WIRE_INDEX.json")
    blob=HERE/idx["artifact"]
    need(hashlib.sha256(blob.read_bytes()).hexdigest()==idx["sha256"],"archive byte identity")
    plan=read("PLAN.json")
    releases=read("install/PINS.json")["identities"]
    slots,geometry,light,warm={},{},{},{}
    for line in gzip.open(blob,"rt",encoding="utf8"):
        rec=json.loads(line); p=Path(rec["path"]); v=rec["value"]; kind=rec["kind"]
        if kind=="S3-RECEIPT.json" and p.parts[1]=="screen01":
            key=p.parts[2]
            need(key not in slots and v["native_reaped"] and v["source_unchanged"] and v["good"],"complete workflow")
            slots[key]=v
        if kind=="S3-actual-stdio" and p.parts[1]=="screen01" and p.name.endswith("RESPONSE.json"):
            key,side=p.parts[2:4]
            k=plan["arms"][key[-1]][0] if side=="mcp" else "032"
            envelope=v["result"]
            need(not envelope.get("isError") and len(envelope["content"])==1,"error in geometry receipt")
            val=json.loads(envelope["content"][0]["text"])
            need(val["binding"].pop("runtime_source_sha256")==releases[k]["source_sha256"] and
                 len(val.pop("trace_id"))==32,"result bound to expected install")
            q=val["result_kind"]
            if q=="surface_nearest":
                need(val["coverage"]["targets_excluding_focal"]==11 and val["nearest_objects"][0]["name"]=="Peer_000","nearest coverage")
            else:
                cv=val["coverage"]
                need(q=="surface_scan" and (cv["total_pairs"],cv["measured_match"],cv["measured_nonmatch"],cv["unknown"],cv["deferred"])==(66,57,9,0,0),"scan coverage")
            need((key,side,q) not in geometry,"duplicate response")
            geometry[key,side,q]=val
        if kind=="S2-slot" and p.parts[1]=="formal":
            key=v["block"],v["event_case"],v["arm"]
            need(key not in light and v["valid"] and v["returncode"]==0 and v["cleaned"] and
                 v["loopback_connections"]==0 and v["source_sha256"]==releases[v["kernel"]]["source_sha256"],"light Hook")
            light[key]=v["T_ns"]
        if kind=="S1-diagnostic-cell":
            for row in v["rows"]:
                tag=row["label"]
                if not tag.startswith("warm"):
                    continue
                if (tag=="warm_scan") != (p.parts[1]=="warm_scan_recovery"):
                    continue
                key=(v["asset"],tag,v["group"],v["arm"])
                need(key not in warm,"duplicate warm comparison")
                warm[key]=row["response_ms"]
    order=plan["s3"]["orders"]
    need(set(slots)=={f"{n:02d}{a}" for n,arms in enumerate(order,1) for a in arms},"planned 28 slots")
    for key in slots:
        for q in ("surface_nearest","surface_scan"):
            need(geometry[key,"mcp",q]==geometry[key,"reference",q],"same-host 032 and timed result differ")
    need(len(geometry)==112 and len(light)==84 and len(warm)==42,"external denominators")
    times=[{a:slots[f"{n:02d}{a}"]["timing"]["workflow_ms"] for a in "ABCD"} for n in range(1,8)]
    print("Full workflow paired reduction (%)")
    for x,y in ("BA","DC","CA","DB","DA"):
        vals=[100*(1-g[x]/g[y]) for g in times]
        print(f"  {x}/{y}: {median(vals):.4f}%, {sum(v>0 for v in vals)}/7 faster")
    print("Interaction (ms):",round(median(g["D"]-g["B"]-g["C"]+g["A"] for g in times),3))
    print("Manual Hook paired reduction (%)")
    for case in sorted({k[1] for k in light}):
        for x,y in ("CA","DB"):
            vals=[100*(1-light[n,case,x]/light[n,case,y]) for n in range(1,8)]
            print(f"  {case} {x}/{y}: {median(vals):.4f}%, {sum(v>0 for v in vals)}/7 faster")
    print("Warm control paired change")
    for asset,task in sorted({k[:2] for k in warm}):
        dif=[]; pct=[]
        for i in range(1,8):
            a,b=warm[asset,task,i,"032"],warm[asset,task,i,"r3"]
            dif.append(b-a); pct.append(100*(b/a-1))
        print(f"  {asset} {task}: {median(dif):+.4f} ms, {median(pct):+.4f}%, regression={median(dif)>5 and median(pct)>5}")
if __name__=="__main__":
    main()

