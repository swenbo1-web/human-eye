"""Recompute the frozen 044 kernel and actual host receipts without new queries."""
from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")
sys.path.insert(0,str(HERE.parent/"m6_r3_region_attribution_043"))
from common import check, dump, pin, read

LIMITS={"faces":4096,"narrow_phase_pairs":16384,"work_units":1179648}
ZERO_LEDGER={"work_units":0,"narrow_phase_pairs":0,"node_pair_visits":0}


def process_group(path, arms):
    result=read(path/"RESULT.json")
    assert result["status"]=="complete" and result["all_reaped"]
    assert [p["arm"] for p in result["launched"]]==list(arms)
    rows={}
    for p in result["launched"]:
        a=p["arm"]
        assert p["exit_code"]==0 and p["launcher_reaped"]
        process_ns=p["full_end_ns"]-p["full_start_ns"]
        assert p["full_process_ns"]==process_ns
        for key in ("stdout","stderr","receipt"):
            check(p[key])
        row=read(p["receipt"]["path"])
        assert row["status"]=="observed" and row["arm"]==a
        assert row["limits"]==LIMITS and row["prepaid"]==0
        assert p["full_start_ns"]<=row["start_ns"]<row["end_ns"]<=p["full_end_ns"]
        assert row["end_ns"]<row["deadline_ns"]
        assert row["cost_wall_ns"]==row["end_ns"]-row["start_ns"]
        assert row["identity"]=={k:row["source_verification"]["identity"][k] for k in row["identity"]}
        row["complete_process_ns"]=process_ns
        rows[a]=row
    return rows,result["complete_window_ns"]


def deep_queue_pair(b,c):
    assert b["observed_new_ledgers"]==c["observed_new_ledgers"]==[ZERO_LEDGER]
    q=[r["queue"] for r in (b,c)]
    trees=[x["trees"][0] for x in q]
    assert trees[0]["roots"]==trees[1]["roots"] and trees[1]["candidate_guard"]
    assert all(x["strict_root_containment"] and x["shift"]==0 and x["completed_tree"] for x in trees)
    assert trees[0]["returned_native_face_pair"]==trees[1]["returned_native_face_pair"]
    events=[read(check(x["events"])) for x in q]
    assert all(len(e)==x["counters"]["pops"] for e,x in zip(events,q,strict=True))
    labels=lambda e:(e["left"],e["right"])
    first=next((i for i,(p,r) in enumerate(zip(*events),1) if labels(p)!=labels(r)),None)
    changed=sum(e["key"]==0 and e["serial"]!=e["original_rule_first"][2] for e in events[1])
    assert changed==q[1]["counters"]["pop_differs_from_original_rule_on_same_queue"] and changed>0
    assert all(p["serial"]==p["original_rule_first"][2] for p in events[0])
    return {"first_B_C_divergent_pop":first,"case_rule_changed_pop_count":changed,
            "counters_B":q[0]["counters"],"counters_C":q[1]["counters"],
            "native_pair":trees[1]["returned_native_face_pair"],"roots":trees[1]["roots"],
            "start":ZERO_LEDGER}


def rounded_rational_points(values):
    return [[float(Fraction(v)) for v in point] for point in values]


def sums(work):
    return {k:work.get(k) for k in ("work_units","narrow_phase_pairs","node_pair_visits",
             "witness_projection_credit_node_units","witness_projection_credit_narrow_units",
             "witness_projection_credit_node_prune_units","witness_projection_credit_spent_units",
             "witness_projection_credit_balance")}


def validate_family():
    base=ROOT/"live_family/attempt_002"
    live=read(base/"RESULTS.json")
    assert live["status"]=="pass" and live["necessary_facts"]==dict.fromkeys("ABC",True)
    assert live["source_geometry_verified"] and live["source_geometry_preserved"]
    assert not live["B_success_C_unknown"] and live["gui_close"]["process_reaped"]
    truth=read(ROOT/"oracle/TRUTH.json")
    archival_points=rounded_rational_points(truth["exact_points_world_m"])
    prof, diag_ns=process_group(ROOT/"family_diagnostic_001","ABC")
    q=deep_queue_pair(prof["B"],prof["C"])
    assert q["native_pair"]==truth["canonical_source_triangle_pair"]
    arms={}
    for arm in "ABC":
        row=read(base/arm/"CELL.json")
        assert row["valid"] and row["relation"]==truth["relation"]
        assert row["distance_m"].hex()==truth["distance_float_hex"]
        witness=row["surface_fact"]["value"]["nearest_witness"]
        assert [witness["a"],witness["b"]]==archival_points
        assert row["trace"]["annotations"]["delivery"]=="stdio_write_completed"
        assert row["trace"]["annotations"]["mcp_native_image_block_count"]==0
        result=row["work"]
        assert not any(result[k] for k in ("result_cache_hit","surface_pair_cache_hit","closed_solid_pair_cache_hit"))
        assert result["surface_pair_count"]==result["closed_solid_pair_count"]==1
        assert result["surface_work"]==prof[arm]["work"]
        assert prof[arm]["observed_new_ledgers"]==[ZERO_LEDGER]
        for k in ("request","response"):
            check(row[k])
        body=prof[arm]["result"]["surface"]
        assert [body["point_a_world"],body["point_b_world"]]==archival_points
        arms[arm]={"work":sums(prof[arm]["work"]),"closed_work":result["closed_solid_work"]["work_units"],
                   "business_ns":row["business_ns"],"through_EOF_ns":row["through_EOF_ns"],
                   "offline_instrumented_process_ns":prof[arm]["complete_process_ns"],
                   "source":prof[arm]["identity"]}
    return {"status":"pass","scope":"original saved real scene and historical normal requested facts",
            "independent_truth":pin(ROOT/"oracle/TRUTH.json"),"cells":arms,"queue":q,
            "true_normal_entry":pin(base/"RESULTS.json"),
            "diagnostic":pin(ROOT/"family_diagnostic_001/RESULT.json"),
            "ordinary_window_ns":live["full_lifecycle_wall_ns"],"queue_diagnostic_wall_ns":diag_ns}


def validate_pressure():
    p=ROOT/"pressure"
    freeze=read(p/"FINAL_FREEZE.json")
    for k in ("geometry","exact_truth","calibration","selection_rule"):
        check(freeze[k])
    selection=read(freeze["selection_rule"]["path"])
    for k in ("generator","runner","controller","input_inventory","calibration_geometry","calibration_truth"):
        check(selection[k])
    cal,cal_ns=process_group(p/"calibration_run","B")
    assert cal["B"]["input"]==selection["calibration_geometry"]
    plain,plain_ns=process_group(p/"final_plain_001","ABC")
    diag,diag_ns=process_group(p/"final_queue_diagnostic_001","BC")
    q=deep_queue_pair(diag["B"],diag["C"])
    expected=read(freeze["exact_truth"]["path"])
    assert freeze["n"]==125 and q["native_pair"]==expected["canonical_native_face_pair"]
    assert all(r["input"]==freeze["geometry"] for r in (*plain.values(),*diag.values()))
    for a in "BC":
        assert plain[a]["result"]==diag[a]["result"] and plain[a]["work"]==diag[a]["work"]
    limbs={}
    for a,row in plain.items():
        assert row["outcome"]=="known_exact"
        w=row["work"]
        u={k:Fraction(w[k],LIMITS[k]) for k in ("work_units","narrow_phase_pairs")}
        limbs[a]={"work":sums(w),"utilization":{k:str(v) for k,v in u.items()},
                  "boundary_reached":[k for k,v in u.items() if v>=Fraction(9,10)],
                  "source":row["identity"],"known":True,"solver_wall_ns":row["cost_wall_ns"],
                  "complete_process_ns":row["complete_process_ns"]}
    assert limbs["B"]["boundary_reached"]==limbs["C"]["boundary_reached"]==["narrow_phase_pairs"]
    return {"status":"pass","scope":"one fixed synthetic geometry and fresh-account public kernel",
            "independent_truth":freeze["exact_truth"],"cells":limbs,
            "freeze":pin(p/"FINAL_FREEZE.json"),"queue":q,
            "plain":pin(p/"final_plain_001/RESULT.json"),"diagnostic":pin(p/"final_queue_diagnostic_001/RESULT.json"),
            "calibration":{"receipt":pin(p/"calibration_run/RESULT.json"),"work":sums(cal["B"]["work"]),"wall_ns":cal_ns},
            "plain_window_ns":plain_ns,"diagnostic_window_ns":diag_ns}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(dump(args.output,{"status":"pass", "family":validate_family(),"pressure_kernel":validate_pressure()}))
