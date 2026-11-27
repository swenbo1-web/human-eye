"""Read-only second view of the fixed failed 129 run's actual credit prefixes."""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import sys
import time

from numeric_first import ROOT, BASE, bound_D, clock, inputs, pin, prior_mesh_pair, read, write


class LedgerObserver:
    def __init__(self,kernel):
        self.kernel=kernel
        self.work=None
        self.credit=None
        self.pending=None
        self.rows=[]
        self.prefixes=0
        self.last_work=0
        self.capture=None
        self.activation=None
        self.boundary=None
        self.tick_codes={kernel._Work.tick.__code__,kernel._Work.consume.__code__}

    @staticmethod
    def role(fn):
        names=fn.__code__.co_names
        for name,label in (("_make_previous","previous_build"),("_reserve","previous_selection"),("_gap","previous_test")):
            if name in names:
                return label
        return "current"

    def observer(self,frame,event,arg):
        if frame.f_globals is not self.kernel.__dict__:
            return
        name=frame.f_code.co_name
        if name=="__init__" and event=="return":
            obj=frame.f_locals.get("self")
            if type(obj) is self.kernel._Work:
                assert self.work is None and obj.counts["work_units"]==obj.counts["narrow_phase_pairs"]==0
                self.work=obj
            if type(obj) is self.kernel._ProjectionCredit:
                assert self.credit is None and obj.balance==obj.spent==0
                self.credit=obj
            if type(obj) is self.kernel._PreviousWitnessTrial:
                parent=frame.f_back.f_locals
                self.capture={"past_pair":list(obj.pair),"new_pair":list(parent["pair"]),
                    "past_descriptor":obj.descriptor,"current_descriptor":parent["candidate"][2],
                    "completed_exact":self.work.counts["narrow_phase_pairs"],
                    "credit_before":self.credit.balance,
                    "work":self.work.counts["work_units"]}
        if frame.f_code in self.tick_codes and event=="return":
            w=self.work.counts
            self.prefixes+=1
            assert self.last_work<=w["work_units"]<=self.kernel.MAX_WORK_UNITS
            self.last_work=w["work_units"]
            assert w["narrow_phase_pairs"]<=self.kernel.MAX_NARROW_PHASE_PAIRS
            if self.credit is not None:
                c=self.credit
                if c.pending_work_start is not None:
                    actual=w["work_units"]-c.pending_work_start
                    assert 0<=actual<=c.pending_upper<=c.balance
                assert c.balance==c.earned_bounds+c.earned_narrow+c.earned_node_prune-c.spent
        if frame.f_code is self.kernel._ProjectionCredit.try_run.__code__:
            if event=="call":
                l=frame.f_locals
                c=l["self"]
                assert self.pending is None and c.pending_work_start is None
                w=c.budget.counts
                self.pending={"role":self.role(l["fn"]),"upper":l["upper"],"credit_before":c.balance,
                    "work_before":w["work_units"],"narrow_at_admission":w["narrow_phase_pairs"],
                    "earned":c.earned_bounds+c.earned_narrow+c.earned_node_prune,"spent_before":c.spent}
            if event=="return":
                c=self.credit
                proof=self.pending
                headroom=self.kernel.MAX_WORK_UNITS-proof["work_before"]
                expected=proof["upper"]<=min(headroom,proof["credit_before"])
                assert isinstance(arg,tuple) and len(arg)==2 and arg[0]==expected
                paid=self.work.counts["work_units"]-proof["work_before"]
                assert 0<=paid<=(proof["upper"] if expected else 0)
                assert c.pending_work_start is None and c.pending_upper is None
                assert c.balance==proof["credit_before"]-paid and c.spent==proof["spent_before"]+paid
                proof.update(admitted=expected,actual=paid,credit_after=c.balance,
                             work_after=self.work.counts["work_units"])
                self.rows.append(proof)
                self.pending=None
        if frame.f_code is self.kernel._PreviousWitnessProjection._make_previous.__code__ and event=="return":
            projection,reason=arg
            cur=frame.f_locals["best"]
            self.activation={"axis":list(projection.axis) if projection else None,"failure":reason,
                             "current_axis":self.kernel._PreviousWitnessProjection._bounded_axis(cur[2]),
                             "current_internal_bound":str(Fraction(cur[0],cur[1])),
                             "completed_exact":self.work.counts["narrow_phase_pairs"]}
        if frame.f_code is self.kernel._Work.narrow_pair.__code__ and event=="call":
            if self.work.counts["narrow_phase_pairs"]==self.kernel.MAX_NARROW_PHASE_PAIRS:
                parent=frame.f_back.f_back.f_locals
                self.boundary={"next_native_pair":[parent["i"],parent["j"]],
                    "already_completed":self.work.counts["narrow_phase_pairs"],
                    "work_units":self.work.counts["work_units"],"credit_balance":self.credit.balance}


def main():
    out=ROOT/"numeric/same_input_diagnostic_02"
    out.mkdir(parents=True)
    kernel=bound_D()
    data,_=inputs()
    left,right=prior_mesh_pair(data)
    observer=LedgerObserver(kernel)
    stamps={}
    original=sys.getprofile()
    began=time.monotonic_ns()
    cpu=time.process_time_ns()
    deadline=began+30_000_000_000
    try:
        sys.setprofile(observer.observer)
        value=kernel.measure_surface_proximity(left,right,clock(deadline,stamps),
                                               retain_exact_rank=True,retain_witness_triangles=True)
    finally:
        sys.setprofile(original)
    elapsed=time.monotonic_ns()-began
    assert elapsed<30_000_000_000
    plain=ROOT/"numeric/first_129/RESULT.json"
    assert json.loads(json.dumps(value, allow_nan=False))==read(plain)["result"], "probe must reproduce exact first attempt receipt"
    assert observer.boundary and observer.capture and observer.activation
    rows={name:[r for r in observer.rows if r["role"]==name]
          for name in ("current","previous_build","previous_selection","previous_test")}
    phase={}
    for name,items in rows.items():
        started=[x for x in items if x["admitted"]]
        phase[name]={"requests":len(items),"admitted":len(started),"paid":sum(x["actual"] for x in items),
                    "maximum_credit_before":max((p["credit_before"] for p in items),default=None),
                    "minimum_required_upper":min((p["upper"] for p in items),default=None),
                    "first":items[0] if items else None,"last":items[-1] if items else None}
    assert phase["previous_build"]["admitted"]==1
    assert phase["previous_test"]["admitted"]==0
    paid=phase["previous_build"]["paid"]+phase["previous_selection"]["paid"]+phase["previous_test"]["paid"]
    assert paid==value["work"]["previous_witness_work_units"]
    receipt={"status":"pass_diagnostic_of_numeric_failure","scope":"same frozen source, profiling only",
             "plain":pin(plain),"geometry":pin(BASE),"observed_work_prefixes":observer.prefixes,
             "credit_attempts":write(out/"CREDIT_PREFIXES.json",observer.rows),"by_phase":phase,
             "capture":observer.capture,"activation":observer.activation,
             "narrow_cap":observer.boundary,"new_actually_proved_prune_obligations":0,
             "deadline_ns":deadline,"checkpoints":stamps,"measured_wall_ns":elapsed,
             "measured_cpu_ns":time.process_time_ns()-cpu}
    print(write(out/"RESULT.json",receipt))


if __name__=="__main__":
    main()
