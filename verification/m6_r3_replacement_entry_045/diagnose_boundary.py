"""Replay only the fixed 129/side packet to locate the original cap and order differences."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY")
FROZEN_SHA="3b283ad99ae043aac13151ca70feffd042a332575e68889860073b2805ce85a3"


def previous():
    source=HERE.parent/"m6_r3_fresh_budget_044/run_budget.py"
    spec=importlib.util.spec_from_file_location("_045_bound_reuse",source)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prior=previous()
pin,check,dump,read=prior.pin,prior.check,prior.dump,prior.read


class Observer(prior.QueueObserver):
    def __init__(self,kernel,arm):
        super().__init__(kernel,arm)
        self.exact_attempts=[]
        self.first_projection_exclusion=None
        self.work=None
        self.first_budget_check=None

    def profile(self,frame,event,arg):
        super().profile(frame,event,arg)
        if frame.f_globals is not self.kernel.__dict__:
            return
        name=frame.f_code.co_name
        if name=="__init__" and event=="return":
            d=frame.f_locals
            if type(d.get("self")) is self.kernel._Work:
                self.work=d["self"].counts
        if frame.f_code is self.kernel._nearest_pair.__code__:
            if event=="call":
                parent=frame.f_back.f_locals
                a,b=parent["i"],parent["j"]
                self.exact_attempts.append({"pair":[a,b],"popped_nodes":self.summary["pops"],"completed":False})
            elif event=="return":
                self.exact_attempts[-1]["completed"]=arg is not None
        if event=="return" and name=="attempt" and not self.first_projection_exclusion:
            values=frame.f_locals
            if type(values.get("self")) is self.kernel._ProjectionCredit and isinstance(arg,tuple) and arg[-1] is True:
                self.first_projection_exclusion={"pair":[values["i"],values["j"]],
                                                  "after_completed_exact":len(self.exact_attempts),
                                                  "source":"return of installed credit.attempt"}
        if frame.f_code is self.kernel._Work.narrow_pair.__code__ and event=="call":
            d=frame.f_locals["self"].counts
            if d["narrow_phase_pairs"]==self.kernel.MAX_NARROW_PHASE_PAIRS and self.first_budget_check is None:
                self.first_budget_check={"pair":self.exact_attempts[-1]["pair"],
                    "observed_narrow_before_original_guard":d["narrow_phase_pairs"],
                    "observed_work_before_original_guard":d["work_units"]}


def main(arm):
    freeze=ROOT/"oracle/FINAL_FREEZE.json"
    assert pin(freeze)["sha256"]==FROZEN_SHA
    spec=read(freeze)
    src=check(spec["geometry"])
    truth=read(check(spec["exact_truth"]))
    data=read(src)
    assert [len(data[k]["faces"]) for k in ("left","right")]==[129,129]
    _,kernel,identity,limits=prior.runtime(arm)
    out=ROOT/"boundary_diagnostic"/arm
    out.mkdir(parents=True)
    row={"status":"failed","arm":arm,"type":"same bytes, installed public function with separate passive diagnostic",
         "source":pin(src),"freeze":pin(freeze),"identity":identity,"limits":limits,"pid":os.getpid()}
    observer=Observer(kernel,arm)
    try:
        left,right=map(lambda k:prior.solver_mesh(data[k]),("left","right"))
        begin=time.monotonic_ns()
        cpu=time.process_time_ns()
        deadline=begin+30_000_000_000
        checkpoint,checkpoints=prior.make_clock(deadline)
        result=observer.execute(lambda:kernel.measure_surface_proximity(left,right,checkpoint))
        end=time.monotonic_ns()
        row.update(cost_wall_ns=end-begin,cost_cpu_ns=time.process_time_ns()-cpu,deadline_ns=deadline,
                   checkpoints=checkpoints,distance_m=result["distance_m"],reason=result.get("reason"),work=result["work"])
        assert end<deadline
        ordinary=read(ROOT/"boundary/attempt_001"/arm/"CELL.json")
        assert row["work"]==ordinary["work"]["surface_work"]
        assert observer.ledgers==[{"work_units":0,"narrow_phase_pairs":0,"node_pair_visits":0}]
        assert sum(e["completed"] for e in observer.exact_attempts)==row["work"]["narrow_phase_pairs"]
        if result["measurement_valid"]:
            assert row["distance_m"]==ordinary["distance_m"]
            assert observer.trees[0]["returned_native_face_pair"]==truth["canonical_native_face_pair"]
            row.update(witness_a=result["point_a_world"],witness_b=result["point_b_world"])
        else:
            assert row["distance_m"] is None and result["point_a_world"] is None and result["point_b_world"] is None
            assert observer.first_budget_check is not None and not observer.exact_attempts[-1]["completed"]
            assert ordinary["surface_fact"]["reason"]==row["reason"]=="surface_pair_budget"
        row["status"]="observed"
    except Exception:
        row["error"]=traceback.format_exc()
    row.update(ledgers=observer.ledgers,zero_order=observer.summary,trees=observer.trees,
               first_cap_guard=observer.first_budget_check,
               first_projection_exclusion=observer.first_projection_exclusion,
               queue= dump(out/"POP_EVENTS.json",observer.events),
               narrow=dump(out/"NARROW_ATTEMPTS.json",observer.exact_attempts))
    print(dump(out/"RESULT.json",row))
    return int(row["status"]!="observed")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm",choices=("A","B","C"))
    raise SystemExit(main(parser.parse_args().arm))
