"""Separate profiled H3 reselection. Times here are diagnostic only."""
from __future__ import annotations

from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
import sys
from time import perf_counter_ns, monotonic

from common import activate, base_install, installation, dump, pin, read, replay_inputs

GROUPS = {
    "_integer_frame": "integer_frame", "_distance_roots": "distance_tree_build",
    "_compile_bvh_node": "compile_tree_nodes", "_nearest_tree": "traversal",
    "_node_queue_bounds": "node_pair_priority", "_queue_distance": "node_pair_priority",
    "_nearest_pair": "narrow_exact", "_triangle_plane_bounds": "leaf_plane_bounds",
    "_aabb_exceeds_best": "unshifted_aabb_bounds",
    "ensure_fast_proj": "projection_outer", "attempt": "projection_outer",
    "prunes_nodes": "projection_outer", "prunes_triangles": "projection_outer",
}


class Probe:
    def __init__(self):
        self.scopes=[]
        self.counts=defaultdict(lambda: {"calls":0,"outer_ns":0,"top_level_exclusive_ns":0})
        self.root_ns=0

    def add(self, group, key):
        self.scopes.append([group,key,perf_counter_ns(),0])

    def close(self, key):
        if not self.scopes or self.scopes[-1][1]!=key:
            return
        group, _, started, children = self.scopes.pop()
        end = perf_counter_ns()
        elapsed = end-started
        row = self.counts[group]
        row["calls"] += 1
        row["top_level_exclusive_ns"] += elapsed-children
        if not any(a[0]==group for a in self.scopes):
            row["outer_ns"] += elapsed
        if self.scopes:
            self.scopes[-1][3]+=elapsed
        else:
            self.root_ns+=elapsed

    def observe(self, frame, event, arg):
        module = frame.f_globals.get("__name__")
        if module!="human_eye_plugin.surface_proximity":
            return
        if event=="call":
            group = GROUPS.get(frame.f_code.co_name)
            if group:
                self.add(group,frame)
        elif event=="return":
            self.close(frame)
        elif event=="c_call" and getattr(arg, "__name__", "") in ("heappush","heappop"):
            self.add("heap_operations", (frame,arg))
        elif event in ("c_return","c_exception"):
            if getattr(arg,"__name__","") in ("heappush","heappop"):
                self.close((frame,arg))


def run(arm, binding, output):
    selected=base_install(arm) if arm in ("A","B") else installation(binding)
    activate(selected)
    from human_eye_plugin import source_region
    plan, capture_path=replay_inputs()
    captured = read(capture_path)
    bind=captured["binding"]
    query=source_region.validate_scoped_measurement_arguments({"include_image":False,"query":plan["query"]})
    def once():
        deadline=monotonic()+30
        def checkpoint(phase):
            if monotonic()>=deadline:
                raise TimeoutError(phase)
        return source_region.measure_selective_region(captured,bind["target_selector"],bind["reference_selector"],
                    bind["world_box_m"],bind["host_source_sha256"],checkpoint)
    initial=once()
    check=Probe()
    started=perf_counter_ns()
    prior=sys.getprofile()
    try:
        sys.setprofile(check.observe)
        result=once()
    finally:
        sys.setprofile(prior)
    wall=perf_counter_ns()-started
    body=source_region.project_scoped_measurement(result,query)
    assert body==plan["expected_public"]==source_region.project_scoped_measurement(initial,query)
    work=result["work"]["task_query"]["surface_work"]
    assert work==initial["work"]["task_query"]["surface_work"] and not check.scopes
    assert sum(x["top_level_exclusive_ns"] for x in check.counts.values())==check.root_ns
    assert 0<=check.root_ns<=wall
    write={"status":"pass","scope":"instrumented repeat; profiler overhead not subtracted; never scored",
        "arm":arm,"installation":selected,"capture":pin(capture_path),"wall_ns":wall,"subscopes":dict(check.counts),
        "unassigned_wall_ns":wall-check.root_ns,"work":work}
    print(dump(output,write))


if __name__=="__main__":
    p=ArgumentParser(description=__doc__)
    p.add_argument("arm",choices=("A","B","C"))
    p.add_argument("output",type=Path)
    p.add_argument("--candidate-binding",type=Path)
    a=p.parse_args()
    run(a.arm,a.candidate_binding,a.output)
