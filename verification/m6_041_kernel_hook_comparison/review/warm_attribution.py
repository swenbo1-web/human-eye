"""Compare per-pair host-capture time on the seven original Yanyite warm-high returns."""
import json
from pathlib import Path
from statistics import median
ROOT=Path(__file__).resolve().parent.parent
base=ROOT/"s1/warm_diagnostic"
rows=[]
for i in range(1,8):
    arms={}
    for k in ("032","r3"):
        d=base/"cells"/f"Yanyite_{i}_{k}"
        s=json.loads((d/"CELL.json").read_bytes())
        r=next(r for r in s["rows"] if r["label"]=="warm_high")
        log=[json.loads(z) for z in (d/"client/AUDIT.jsonl").read_bytes().splitlines()]
        traces=[z["trace"] for z in log if z.get("event")=="request_trace" and z["trace_id"]==r["trace"]["trace_id"]]
        assert len(traces)==1
        spans={v["name"]:v["duration_ns"]/1e6 for v in traces[0]["spans"]}
        msg=json.loads((d/"client"/(r["timing"]["id"]+".RX.bin")).read_bytes())
        assert json.loads(msg["result"]["content"][0]["text"])==r["value"] and r["response_ms"]>0
        arms[k]={"rtt_ms":r["response_ms"],"capture_ms":spans["host.capture_source_region_pair"],
                 "witness_membership_ms":spans["surface_proximity.rounded_source_membership"],
                 "duration_ms":traces[0]["duration_ns"]/1e6}
    rows.append({m:arms["r3"][m]-arms["032"][m] for m in arms["032"]}|{"raw":arms})
out={"case":"warm_high","paired_median_delta_ms":{m:median(r[m] for r in rows) for m in rows[0] if m!="raw"},
     "raw":rows,"scope":"host.capture_source_region_pair includes native work, queues and transport; no causal isolation of solver, scheduling or individual subcomponents."}
with (ROOT/"review/WARM_ATTRIBUTION.json").open("x",encoding="utf8") as f:
    json.dump(out,f,indent=2)
print(out["paired_median_delta_ms"])

