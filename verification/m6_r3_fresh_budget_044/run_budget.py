"""New-account public measurements plus a separate, passive queue diagnostic."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import heapq
import math
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")
OLD = ROOT.parent/"M6-043-R3-REGION-ATTRIBUTION"
sys.path.insert(0,str(HERE.parent/"m6_r3_region_attribution_043"))
from common import activate, check, dump, installation, pin, read

FROZEN_043_PLAN_SHA = "0bcc54db5f7e437d8bba3317f96fb8a22a1d4aea8569cf2969ed434cd06a18cb"
LIMITS = {"faces":4096,"narrow_phase_pairs":16384,"work_units":1179648}


def inherited():
    prior = OLD/"timing/PLAN.json"
    assert pin(prior)["sha256"]==FROZEN_043_PLAN_SHA
    return read(prior)


def runtime(arm):
    install = inherited()["release_bindings"][arm]
    assert installation(check(install["binding"]))==install
    activate(install)
    from human_eye_plugin import surface_proximity as kernel
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity(mode="live")
    assert identity["source_sha256"]==install["identity"]["source_sha256"]
    assert identity["distribution_version"]==install["identity"]["distribution_version"]
    assert len(identity["source_files"])==143
    assert Path(kernel.__file__).resolve().parent.parent==Path(install["site"]).resolve()
    limits={"faces":kernel.MAX_FACES,"narrow_phase_pairs":kernel.MAX_NARROW_PHASE_PAIRS,"work_units":kernel.MAX_WORK_UNITS}
    assert limits==LIMITS
    return install, kernel, {k:identity[k] for k in ("source_sha256","distribution_version","implementation_revision")}, limits


class QueueObserver:
    """Counts actual tie decisions against the original center rule on the same pending set."""

    def __init__(self, kernel, arm):
        self.kernel, self.arm = kernel, arm
        self.summary = Counter()
        self.events = []
        self.trees = []
        self.ledgers = []
        self.current = None
        self.heap_by_center = []
        self.live_serials = set()

    @staticmethod
    def root_bounds(roots):
        return [[list(r[0]),list(r[1])] for r in roots]

    def profile(self, frame, event, arg):
        if frame.f_globals is not self.kernel.__dict__:
            return
        name = frame.f_code.co_name
        if name=="__init__" and event=="return" and type(frame.f_locals.get("self")) is self.kernel._Work:
            counts=frame.f_locals["self"].counts
            self.ledgers.append({k:counts[k] for k in ("work_units","narrow_phase_pairs","node_pair_visits")})
        if frame.f_code is not self.kernel._nearest_tree.__code__:
            return
        local=frame.f_locals
        if event=="call":
            assert self.current is None
            bounds=self.root_bounds(local["roots"])
            strict=any(all(bounds[a][0][k]<bounds[b][0][k]<=bounds[b][1][k]<bounds[a][1][k]
                           for k in range(3)) for a,b in ((0,1),(1,0)))
            self.current={"roots":bounds,"strict_root_containment":strict}
            self.heap_by_center=[]
            self.live_serials=set()
        elif event=="return":
            self.current.update(shift=local.get("shift"),candidate_guard=local.get("contained_zero_fifo"),
                                completed_tree=arg is not None)
            if arg is not None and local.get("best_pair") is not None:
                self.current["returned_native_face_pair"]=list(local["best_pair"])
            if self.arm=="C":
                assert self.current["candidate_guard"]==(self.current["strict_root_containment"] and self.current["shift"]==0)
            self.trees.append(self.current)
            self.current=None

    @staticmethod
    def ids(node, arm):
        if arm=="A":
            return [node[0],node[1],node[2],node[3]]
        return [node[:3],node[3:6],node[6],node[10],node[7]]

    def unpack(self, item):
        if self.arm=="A":
            key, serial, a, b=item
            return key,None,None,serial,a,b
        key, second, serial, a,b=item
        center=sum((u-v)**2 for u,v in zip(a[11:14],b[11:14]))
        return key,second,center,serial,a,b

    def push(self, queue, item):
        heapq.heappush(queue,item)
        key, second, center, serial, a,b=self.unpack(item)
        self.summary["pushes"]+=1
        if key==0:
            self.summary["zero_keys_enqueued"]+=1
        if self.arm!="A":
            assert serial not in self.live_serials
            self.live_serials.add(serial)
            heapq.heappush(self.heap_by_center,(key,center,serial))
            if second!=center:
                assert self.arm=="C" and key==0 and second==0
                self.summary["changed_secondary_enqueues"]+=1

    def pop(self, queue):
        item=heapq.heappop(queue)
        key, second, center, serial,a,b=self.unpack(item)
        self.summary["pops"]+=1
        rule_pick=None
        if key==0:
            self.summary["zero_keys_popped"]+=1
        if self.arm!="A":
            while self.heap_by_center[0][2] not in self.live_serials:
                heapq.heappop(self.heap_by_center)
            rule_pick=self.heap_by_center[0]
            self.live_serials.remove(serial)
            if rule_pick[2]!=serial:
                assert rule_pick[0]==key==0 and self.arm=="C"
                self.summary["pop_differs_from_original_rule_on_same_queue"]+=1
        self.events.append({"key":key,"second":second,"center":center,"serial":serial,
                            "left":self.ids(a,self.arm),"right":self.ids(b,self.arm),
                            "original_rule_first":rule_pick,"pending_after":len(queue)})
        return item

    def execute(self, fn):
        previous=sys.getprofile()
        with patch.object(self.kernel,"heapq",SimpleNamespace(heappush=self.push,heappop=self.pop)):
            try:
                sys.setprofile(self.profile)
                return fn()
            finally:
                sys.setprofile(previous)


def solver_mesh(record):
    return SimpleNamespace(name=record["name"], object_id=record["name"],
                           vertices=tuple(map(tuple,record["vertices_world"])), faces=tuple(map(tuple,record["faces"])))


def rank(key):
    n,d,e=key
    return Fraction(int(n),int(d))*(Fraction(2)**int(e))


def witness_pair(result):
    exact=result.get("exact_witness_triangles")
    return exact["indices"] if exact is not None else result.get("witness_triangle_indices")


def pressure_eval(kernel, data, clock):
    a,b=map(lambda k:solver_mesh(data[k]),("left","right"))
    return kernel.measure_surface_proximity(a,b,clock,retain_exact_rank=True,retain_witness_triangles=True)


def verify_pressure(value, truth):
    if not value["measurement_valid"]:
        assert value["distance_m"] is None and value["point_a_world"] is None and value["point_b_world"] is None
        return "unknown"
    sq=Fraction(truth["distance_squared_exact"])
    assert rank(value["_exact_distance_sq"])==sq
    assert value["distance_m"]==math.sqrt(float(sq))
    assert witness_pair(value)==truth["canonical_native_face_pair"]
    ordered=[value["point_a_world"],value["point_b_world"]]
    assert [list(map(Fraction,p)) for p in ordered]==[list(map(Fraction,p)) for p in truth["unique_witness_world_exact"]]
    return "known_exact"


def family_eval(data, req, clock):
    from human_eye_plugin import task_query
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.scene_cache import SpatialSceneCache
    ordered=[(data[k]["vertices_world"], data[k]["faces"], ("044",k), data[k]["name"]) for k in ("left","right")]
    a,b=_meshes_from_objects(ordered)
    diagnostic={}
    facts,surface=task_query._closed_surface_facts(a,b,set(req),SpatialSceneCache(),clock,
                                                  {"source":"044_sealed_author_world_array"},diagnostic)
    return {"surface":surface,"facts":facts,"diagnostics":diagnostic}


def make_clock(deadline):
    state={"first":None,"last":None}
    def checkpoint(stage):
        if state["first"] is None:
            state["first"]=stage
        state["last"]=stage
        if time.monotonic_ns()>=deadline:
            raise TimeoutError(stage)
    return checkpoint,state


def main(args):
    installation_ref,kernel,actual,limits=runtime(args.arm)
    path=args.output
    path.mkdir(parents=True,exist_ok=False)
    receipt={"arm":args.arm,"status":"invalid",
             "identity":actual,"source_verification":installation_ref,"kernel":pin(kernel.__file__),
             "limits":limits,"input":pin(args.input),"independent_truth":pin(args.truth),"deadline_s":30.0,
             "pid":os.getpid(),"prepaid":0,"algorithm":"installed public default","phase":args.phase,
             "instrumented":args.phase.endswith("diagnostic")}
    data=read(args.input)
    truth=read(args.truth)
    initial=Path(args.freeze) if args.freeze else None
    if initial is not None:
        frozen=read(initial)
        in_key,truth_key=(("calibration_geometry","calibration_truth") if args.phase=="calibrate" else ("geometry","exact_truth"))
        assert receipt["input"]==frozen[in_key] and receipt["independent_truth"]==frozen[truth_key]
        receipt["freeze"]=pin(initial)
    if args.phase=="calibrate":
        assert args.arm=="B" and initial is not None and data["subdivision_n"]==48
    if args.phase.startswith("pressure"):
        assert initial is not None and read(initial)["status"]=="frozen_before_final_C"
    observer=QueueObserver(kernel,args.arm) if receipt["instrumented"] else None
    receipt["scope"]="shared_task_facts_offline_diagnostic" if args.phase=="family-diagnostic" else (
        "public_kernel_with_separate_queue_observer" if observer else "plain_public_kernel")
    try:
        if args.phase=="family-diagnostic":
            records=data.get("meshes", data["objects"] if "objects" in data else None)
            if isinstance(records,dict):
                records=[records[n] for n in ("Object_01","Object_02")]
            if records is None and "left" in data and "right" in data:
                records=[data["left"],data["right"]]
            assert records is not None and len(records)==2
            data={label:{"name":mesh["name"],"vertices_world":mesh.get("vertices_world_m",mesh.get("vertices_world")),
                         "faces":mesh.get("triangles",mesh.get("faces"))}
                  for label,mesh in zip(("left","right"),records,strict=True)}
            assert [len(data[k]["faces"]) for k in ("left","right")]==[96,12]
            maker=lambda:family_eval(data,("closed_solid_relation","surface_proximity"),clock)
        else:
            maker=lambda:pressure_eval(kernel,data,clock)
        began=time.monotonic_ns()
        cpu=time.process_time_ns()
        deadline=began+30_000_000_000
        clock,stages=make_clock(deadline)
        receipt.update(start_ns=began,deadline_ns=deadline)
        result=observer.execute(maker) if observer else maker()
        stopped=time.monotonic_ns()
        receipt.update(end_ns=stopped,cost_wall_ns=stopped-began,cost_cpu_ns=time.process_time_ns()-cpu,checkpoints=stages)
        assert stopped<deadline
        if args.phase=="family-diagnostic":
            receipt["result"]=result
            receipt["work"]=result["surface"]["work"]
            receipt["outcome"]="known" if result["surface"]["measurement_valid"] else "unknown"
        else:
            receipt.update(result=result,work=result["work"])
            receipt["outcome"]=verify_pressure(result,truth)
        receipt["status"]="observed"
    except TimeoutError as exc:
        stopped=time.monotonic_ns()
        receipt.update(status="observed",end_ns=stopped,cost_wall_ns=stopped-began,cost_cpu_ns=time.process_time_ns()-cpu,
                       checkpoints=stages,outcome="deadline",reason=str(exc),result=None)
    except Exception:
        receipt["error"]=traceback.format_exc()
    if observer:
        receipt["observed_new_ledgers"]=observer.ledgers
        assert all(not any(ledger.values()) for ledger in observer.ledgers)
        receipt["queue"]={"counters":observer.summary,"trees":observer.trees,
                          "events":dump(path/"POP_EVENTS.json",observer.events)}
        if "work" in receipt and "queue_pushes" in receipt["work"]:
            assert observer.summary["pushes"]==receipt["work"]["queue_pushes"]
    print(dump(path/"RESULT.json",receipt))
    return int(receipt["status"]!="observed")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("calibrate","pressure","family-diagnostic","pressure-diagnostic"),required=True)
    parser.add_argument("--arm",choices=("A","B","C"),required=True)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--truth",type=Path,required=True)
    parser.add_argument("--freeze",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    raise SystemExit(main(parser.parse_args()))
