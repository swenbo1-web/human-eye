"""Independent S1 raw response, completeness, resource-custody and work-count review."""
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
def read(p):
    return json.loads(p.read_bytes())
def geom(value):
    return {k:v for k,v in value.items() if k not in {"binding","trace_id"}}
def main():
    base=root/"s1"
    plan=read(base/"PLAN.json")
    pins=read(root/"install/PINS.json")
    complete={}
    rows={}
    for scenario in plan["sequence"]:
        seq=[x for x in plan["sequence"][scenario] if x!="edit"]
        pairs=[]
        for role in ("032","r3"):
            folder=base/("slots_recovery_02" if scenario=="Yanyite" else "slots_recovery_01")/(scenario+"_"+role)
            slot=read(folder/"SLOT.json")
            assert slot["completed"] and not slot["errors"] and slot["geometry_binds"] and slot["geometry_preserved"]
            assert [x["label"] for x in slot["rows"]]==seq
            gui=slot["close"]["GUI"]["result"]
            assert gui["status"]=="pass" and gui["source_unchanged"] and gui["process_reaped"] and not gui["released_port"]["owned_listener"]
            assert read(folder/"client/CLOSE.json")["method"]=="eof"
            reduced={}
            for r in slot["rows"]:
                tag=r["label"]
                val=r["value"]
                n=r["timing"]["id"]
                raw=read(folder/"client"/(n+".RX.bin"))
                assert json.loads(raw["result"]["content"][0]["text"])==val
                assert r["audit"]["source"]==pins["identities"][role]["source_sha256"]
                if "binding" in val:
                    assert val["binding"]["runtime_source_sha256"]==r["audit"]["source"]
                wk=r["audit"]["work"]
                reduced[tag]={"ms":r["business_ns"]/1e6,"bytes":[r["timing"]["tx_bytes"],r["timing"]["rx_bytes"]],
                              "status":val.get("status"),"coverage":val.get("coverage"),
                              "kernel_calls":wk[0].get("kernel_calls") if wk else None}
            pairs.append(slot["rows"])
            rows[scenario+"_"+role]=reduced
        for a,b in zip(*pairs,strict=True):
            assert a["label"]==b["label"]
            assert geom(a["value"])==geom(b["value"]), (scenario,a["label"])
        complete[scenario]=len(seq)
    d=rows["D48_032"]["nearest"]; e=rows["D48_r3"]["nearest"]
    assert d["kernel_calls"]==e["kernel_calls"]==47 and rows["B02_r3"]["nearest"]["kernel_calls"]==10
    assert sum(complete.values())==22
    result={"complete_scenarios":complete,"paired_queries":sum(complete.values()),"complete_primary_responses":44,"rows":rows,
            "cross_host_scope":"All geometrical content/ordering/status compared. Per-session source and custody validated separately. S3 additionally checks the FULL result against 032 on the same live host."}
    with (root/"review/S1_INDEPENDENT.json").open("x",encoding="utf8") as f:
        json.dump(result,f,indent=2)
    print(complete)
if __name__=="__main__":
    main()

