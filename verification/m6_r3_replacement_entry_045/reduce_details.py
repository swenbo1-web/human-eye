"""Recompute the fixed boundary divergence and G60 per-slot clock decomposition."""
from __future__ import annotations

from fractions import Fraction
from hashlib import file_digest
import json
from pathlib import Path
from statistics import median

ROOT=Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY")


def pin(path):
    with path.open("rb") as f:
        return {"path":str(path.resolve()),"bytes":path.stat().st_size,"sha256":file_digest(f,"sha256").hexdigest()}


def load(ref):
    path=Path(ref["path"])
    assert pin(path)==ref
    return read(path)


def read(path):
    return json.loads(path.read_bytes())


def save(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(value,f,indent=2,ensure_ascii=False)
        f.write("\n")
    return pin(path)


def boundary():
    root=ROOT/"boundary_diagnostic"
    r={a:read(root/a/"RESULT.json") for a in "ABC"}
    queue={a:load(d["queue"]) for a,d in r.items()}
    exact={a:load(d["narrow"]) for a,d in r.items()}
    summary={}
    for arm,d in r.items():
        assert d["status"]=="observed"
        attempts=exact[arm]
        result=read(ROOT/"boundary/attempt_001"/arm/"CELL.json")
        assert d["work"]==result["work"]["surface_work"]
        projection=d["work"].get("witness_projection_pruned_pairs",0)
        n=sum(x["completed"] for x in attempts)
        assert n==d["work"]["narrow_phase_pairs"]
        assert d["ledgers"]==[{"work_units":0,"narrow_phase_pairs":0,"node_pair_visits":0}]
        if arm=="A":
            assert n+projection==16641
            assert len(attempts)==n and d["first_projection_exclusion"] and d["reason"] is None
        else:
            assert not attempts[-1]["completed"] and len(attempts)==n+1 and n==16384 and not projection
            assert attempts[-1]["pair"]==d["first_cap_guard"]["pair"] and d["reason"]=="surface_pair_budget"
        summary[arm]={"result":pin(root/arm/"RESULT.json"),"first_narrow_attempt":attempts[0],
                      "narrow_attempted":len(attempts),"narrow_completed":n,"projection_excluded":projection,
                      "first_projection_exclusion":d["first_projection_exclusion"],"first_cap_guard":d["first_cap_guard"],
                      "measured_work":d["work"]["work_units"],"reason":d["reason"],"diagnostic_wall_ns":d["cost_wall_ns"]}
    first=next((i,p,q) for i,(p,q) in enumerate(zip(exact["B"],exact["C"]),1) if p["pair"]!=q["pair"])
    pop=next((i,p,q) for i,(p,q) in enumerate(zip(queue["B"],queue["C"]),1)
             if (p["left"],p["right"])!=(q["left"],q["right"]))
    assert first[0]==3 and pop[0]==1
    return {"status":"pass","possible_pairs":16641,"scope":"same frozen input separate installed diagnostic",
            "A_B_C":summary,"first_B_C_narrow_attempt_difference":first,
            "first_B_C_pop_difference":pop,"C_changed_actual_pop_selections":r["C"]["zero_order"]["pop_differs_from_original_rule_on_same_queue"]}


def timings():
    folder=ROOT/"g60/main_001"
    source=read(folder/"RESULTS.json")
    groups=[]
    for g in source["groups"]:
        record=load(g["raw"])
        group={"group":g["group"],"order":g["order"],"arm":{}}
        for a in "ABC":
            c=record["cells"][a]
            lc=c["lifecycle"]
            assert lc["valid"] and lc["exit_at_wrapper_wait"]=={"wrapper":0,"service":0}
            events={e["name"]:e for e in lc["events"]}
            f=lambda name:events[name]["filetime_100ns"]*100
            q=lambda name:events[name]["at_ns"]
            ps=lc["processes"]
            end=max(z["exit_time_100ns"] for z in ps.values())*100
            created=ps["wrapper"]["creation_time_100ns"]*100
            assert end-created==g["process_ns"][a]
            # These adjacent caller anchors are intentionally different from the exact
            # original business QPC metric. Their terms sum in the FILETIME domain.
            phases={"os_create_to_first_observe_anchor_ns":f("before_first_observe")-created,
                    "os_observe_anchor_to_last_decode_anchor_ns":f("last_business_decode")-f("before_first_observe"),
                    "os_last_decode_anchor_to_final_exit_ns":end-f("last_business_decode")}
            assert all(v>0 for v in phases.values()) and sum(phases.values())==g["process_ns"][a]
            archive=lc["archive"]
            assert archive["files"]==len(archive["entries"])==11
            assert all((folder/(f"G{g['group']:02d}-{g['order']}")/a/"client"/x["path"]).stat().st_size==x["bytes"]
                       for x in archive["entries"])
            assert sum(x["bytes"] for x in archive["entries"])==archive["bytes"]
            assert q("reader_receive_return")<=q("reader_join_end")<=archive["started_ns"]<archive["closed_ns"]
            phases.update(archive_ns=archive["closed_ns"]-archive["started_ns"],archive_bytes=archive["bytes"],
                          archive_files=archive["files"],workflow_ns=c["workflow_ns"],business_ns=c["business_ns"],
                          process_ns=lc["os_survival_ns"],
                          wrapper_wait_observed_ns=q("wrapper_wait_end")-q("wrapper_wait_begin"),
                          observed_wait_return_after_os_exit_ns=f("wrapper_wait_end")-end,
                          observed_reader_return_after_os_exit_ns=f("reader_receive_return")-end,
                          close_readback_ns=q("close_readback_end")-q("close_readback_begin"),
                          init_receipt_IO_ns=sum(row["closed_ns"]-row["started_ns"] for row in lc["experiment_io"]
                                                 if row["name"] in ("config","launch_receipt","constructor_audit","startup_receipt")),
                          observed_handle_bind_ns=q("handle_bind_end")-q("handle_bind_begin"))
            uniq={v["pid"]:v for v in ps.values()}
            phases.update(total_process_CPU_ns=sum((x["kernel_100ns"]+x["user_100ns"])*100 for x in uniq.values()),
                          product_boundary_peak_RSS_bytes=c["product_after"]["peak_working_set_bytes"],
                          wrapper_os_exit_ns_since_filetime_epoch=ps["wrapper"]["exit_time_100ns"]*100,
                          product_os_exit_ns_since_filetime_epoch=ps["service"]["exit_time_100ns"]*100,
                          host_boundary_peak_RSS_bytes=record["host_after_business"]["peak_working_set_bytes"])
            group["arm"][a]=phases
        subtraction=("os_create_to_first_observe_anchor_ns","os_observe_anchor_to_last_decode_anchor_ns",
                     "os_last_decode_anchor_to_final_exit_ns","archive_ns","workflow_ns","business_ns","process_ns")
        group["C_minus_B_ns"]={k:group["arm"]["C"][k]-group["arm"]["B"][k] for k in subtraction}
        groups.append(group)
    assert len(groups)==6
    metrics=("archive_ns","init_receipt_IO_ns","observed_handle_bind_ns","wrapper_wait_observed_ns",
             "os_create_to_first_observe_anchor_ns","os_last_decode_anchor_to_final_exit_ns")
    return {"status":"pass","result":pin(folder/"RESULTS.json"),"groups":groups,
            "medians_ns":{a:{k:median(g["arm"][a][k] for g in groups) for k in metrics} for a in "ABC"},
            "scope":{"lifetime":"one FILETIME domain", "business":"original QPC write-to-decoded-body",
                     "archive":"original closure writes, after verified process exits, on parent QPC",
                     "CPU":"unique held handle totals", "RSS":"observed boundaries per PID",
                     "paired_phases":"same FILETIME markers decompose individual slots; no aggregation by adding medians"}}


if __name__=="__main__":
    print(save(ROOT/"BOUNDARY_DIAGNOSTIC.json",boundary()))
    print(save(ROOT/"G60_TIMING_DETAIL.json",timings()))
