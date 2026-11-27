"""Verify planned S2 stdout, audit, ownership and paired costs from raw per-slot files."""
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parent.parent
read=lambda p: json.loads(p.read_bytes())
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    base=ROOT/"s2"
    plan=read(base/"PLAN.json")
    pins=read(ROOT/"install/PINS.json")
    seen=set()
    data={}
    for spec in plan["slots"]:
        case,a,b=spec["event_case"],spec["arm"],spec["block"]
        key=(b,case,a)
        assert key not in seen
        seen.add(key)
        p=base/"formal"/f"block{b:02}"/case/a
        row=read(p/"RESULT.json")
        identity=pins["identities"][spec["kernel"]]
        assert row["source_sha256"]==identity["source_sha256"]
        assert sha(p/"INPUT.bin")==plan["inputs"][case]["input_040"][0]["sha256"]
        assert json.loads((p/"STDOUT.bin").read_bytes())=={} and not (p/"STDERR.bin").read_bytes()
        assert row["returncode"]==0 and row["valid"] and row["job_pids_at_cleanup"]==[] and row["job_accounting"]["active_processes"]==0
        assert row["loopback_connections"]==0 and not (p/"state.json").exists() and not (p/"state.json.lock").exists()
        logs=[json.loads(s) for s in (p/"audit.jsonl").read_bytes().splitlines()]
        assert [r["event"] for r in logs]==["host_hook_skip","request_trace"]
        assert all(r["runtime_identity"]["build_id"]==identity["build_id"] for r in logs)
        assert row["T_ns"]>0 and row["job_accounting"]["cpu_ns"]>0
        data[key]=row
    assert len(seen)==84
    cases=sorted({k[1] for k in data})
    metrics={}
    for case in cases:
        for x,y in ["CA","DB"]:
            times=[(data[i,case,y]["T_ns"]/1e6,data[i,case,x]["T_ns"]/1e6) for i in range(1,8)]
            gain=[100*(1-b/a) for a,b in times]
            faster=sum(x>0 for x in gain)
            metrics[case+"_"+x+y]={"H0_ms":median(t[0] for t in times),"H1_ms":median(t[1] for t in times),
                          "paired_reduction_pct":median(gain),"faster":faster,"pairs_ms":times,
                          "gate":median(gain)>=10 and faster>=5}
    out={"slots":len(seen),"audited_events":2*len(seen),"cases":metrics,"all_manual_gates":all(v["gate"] for v in metrics.values())}
    with (ROOT/"review/S2_INDEPENDENT.json").open("x",encoding="utf8") as f:
        json.dump(out,f,indent=2)
    print(json.dumps({k:[round(v["paired_reduction_pct"],1),v["faster"],v["gate"]] for k,v in metrics.items()}))
if __name__=="__main__":
    main()

