"""Independent diagnostic of exact best updates and actual heap order."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from fractions import Fraction
import heapq
import inspect
from pathlib import Path
import sys
import time
from types import CodeType, SimpleNamespace
from unittest.mock import patch

from common import activate, base_install, dump, installation, pin, read, replay_inputs


def counterfactual(proximity, surface, choice, stack):
    source = inspect.getsource(proximity._nearest_tree)
    if choice == "leaf4":
        build = surface._bvh
        calls = []
        def larger(bounds, budget, *, leaf_size):
            calls.append(len(bounds))
            assert leaf_size == 2 and calls in ([262], [262, 12])
            return build(bounds, budget, leaf_size=4 if len(calls) == 1 else 2)
        stack.enter_context(patch.object(surface, "_bvh", larger))
    elif choice == "median":
        stack.enter_context(patch.object(surface, "_bvh", surface._bvh_median))
    elif choice in ("zero", "positive", "seed"):
        if choice == "seed":
            a = "(k0, cd0, c0[10]) <= (k1, cd1, c1[10])"
            b = "(k0, c0[10]) <= (k1, c1[10])"
            count = 2
        else:
            operator = "==" if choice == "zero" else ">"
            a = "heapq.heappush(pending, (key, cdist, serial, sl, sr))"
            b = f"heapq.heappush(pending, (key, (0 if shift == 0 and key {operator} 0 else cdist), serial, sl, sr))"
            count = 1
        assert source.count(a) == count
        override = {}
        exec(compile(source.replace(a, b), "<independent-043-diagnostic>", "exec"), vars(proximity), override)
        stack.enter_context(patch.object(proximity, "_nearest_tree", override["_nearest_tree"]))


class Trace:
    def __init__(self, proximity, arm, capture):
        self.kernel = proximity
        self.old = arm == "A"
        self.native_left = capture["region"]["source_triangle_indices"]
        self.events = []
        self.pops = self.pushes = self.narrow = 0
        self.factor = None
        self.trees = 0
        self.last = None
        self.final = None
        self.root = {}

    def source_pair(self, indices):
        if indices is None:
            return None
        i, j = indices
        return [self.native_left[i], j]

    def squared(self, best):
        return None if best is None else str(Fraction(best[0], best[1] * self.factor ** 2))

    def event(self, name, **row):
        self.events.append(dict(event=name, step=len(self.events)+1, pops=self.pops, exact=self.narrow, **row))

    def node(self, node):
        if self.old:
            return {"lo": node[0], "hi": node[1], "count": node[2], "leaf": node[3]}
        return {"lo": node[:3], "hi": node[3:6], "count": node[6], "leaf": node[7], "first_leaf": node[10]}

    def entry(self, item):
        if self.old:
            key, serial, left, right = item
            secondary = None
        else:
            key, secondary, serial, left, right = item
        return {"key": key, "secondary": secondary, "serial": serial, "left": self.node(left), "right": self.node(right)}

    def push(self, queue, item):
        heapq.heappush(queue, item)
        self.pushes += 1
        self.event("push", entry=self.entry(item), queue_size=len(queue))

    def pop(self, queue):
        item = heapq.heappop(queue)
        self.pops += 1
        self.event("pop", entry=self.entry(item), queue_size=len(queue))
        return item

    def start(self, frame, event, arg):
        if event != "call":
            return None
        code = frame.f_code
        if code is self.tree_code:
            self.trees += 1
            roots = frame.f_locals["roots"]
            bounds = [{"lo": r[0], "hi": r[1]} for r in roots]
            left, right = bounds
            def strictly_in(a, b):
                return all(bl < al <= ah < bh for al, ah, bl, bh in zip(a["lo"], a["hi"], b["lo"], b["hi"]))
            self.root = {"bounds": bounds, "strict_inclusion": strictly_in(left, right) or strictly_in(right, left)}
            return self.tree_lines
        if code in self.eval_codes:
            return self.tree_lines
        if code is self.kernel._integer_frame.__code__:
            return self.frame_return
        if code is self.kernel._nearest_pair.__code__:
            parent = frame.f_back.f_locals
            idx = (parent["i"], parent["j"])
            line = {"native_pair": self.source_pair(idx), "compact_pair": idx,
                    "enter_sq_m2": self.squared(parent.get("best"))}
            self.narrow += 1
            self.event("exact_start", **line)
            def exact_return(_frame, kind, result):
                if kind == "return":
                    self.event("exact_return", native_pair=line["native_pair"], result_sq_m2=self.squared(result))
                return exact_return
            return exact_return
        return None

    def frame_return(self, frame, event, result):
        if event == "return":
            self.factor = result[1]
        return self.frame_return

    def tree_lines(self, frame, event, result):
        local = frame.f_locals
        if self.factor is not None and local.get("best") is not None and local.get("best_pair") is not None:
            pair = tuple(local["best_pair"])
            sq = self.squared(local["best"])
            key = (sq, pair)
            if key != self.last:
                improvement = "first_upper" if self.last is None else (
                    "strict_improvement" if Fraction(sq) < Fraction(self.last[0]) else "equal_distance_earlier_witness")
                if self.last is not None:
                    assert Fraction(sq) <= Fraction(self.last[0])
                    if improvement.startswith("equal"):
                        assert pair < self.last[1]
                self.event("best_accepted", kind=improvement, square_m2=sq,
                           compact_pair=pair, native_pair=self.source_pair(pair))
                self.last = key
        if frame.f_code is self.tree_code and event == "return":
            self.root["shift"] = local["shift"]
            self.final = {"square_m2": self.squared(result), "native_pair": self.source_pair(local["best_pair"])}
        return self.tree_lines

    def run(self, task):
        self.tree_code = self.kernel._nearest_tree.__code__
        self.eval_codes = {v for v in self.tree_code.co_consts if isinstance(v, CodeType) and v.co_name == "eval_leaf"}
        with patch.object(self.kernel, "heapq", SimpleNamespace(heappush=self.push, heappop=self.pop)):
            previous = sys.gettrace()
            try:
                sys.settrace(self.start)
                return task()
            finally:
                sys.settrace(previous)


def main(arm, binding, diagnostic, output):
    installed = base_install(arm) if arm in ("A", "B") else installation(binding)
    activate(installed)
    from human_eye_plugin import source_region, surface_geometry, surface_proximity
    from human_eye_plugin.runtime_identity import runtime_identity
    actual = runtime_identity(mode="live")
    assert actual["source_sha256"] == installed["identity"]["source_sha256"]
    old, capture_path = replay_inputs()
    capture = read(capture_path)
    target = capture["binding"]
    query = source_region.validate_scoped_measurement_arguments({"include_image": False, "query": old["query"]})
    deadline = time.monotonic() + old["request_budget_s"]
    def checkpoint(stage):
        if time.monotonic() >= deadline:
            raise TimeoutError(stage)
    def run():
        return source_region.measure_selective_region(
            capture, target["target_selector"], target["reference_selector"], target["world_box_m"],
            target["host_source_sha256"], checkpoint)
    trace = Trace(surface_proximity, arm, capture)
    with ExitStack() as stack:
        if diagnostic != "native":
            assert arm == "B"
            counterfactual(surface_proximity, surface_geometry, diagnostic, stack)
        value = trace.run(run)
    public = source_region.project_scoped_measurement(value, query)
    work = value["work"]["task_query"]["surface_work"]
    assert public == old["expected_public"] and trace.final["native_pair"] == [49114, 0]
    assert trace.trees == 1 and work["narrow_phase_pairs"] == trace.narrow and work["queue_pushes"] == trace.pushes
    changes = [row for row in trace.events if row["event"] == "best_accepted"]
    first_upper = next(row for row in changes if row["square_m2"] == trace.final["square_m2"])
    canonical = next(row for row in changes if row["square_m2"] == trace.final["square_m2"] and row["native_pair"] == [49114, 0])
    result = dict(arm=arm, diagnostic=diagnostic, installation=installed, capture=pin(capture_path), scope="instrumented",
        root=trace.root, counters=work, final=trace.final, first_final_upper=first_upper, first_final_canonical=canonical,
        accepted=changes, events=trace.events)
    print(dump(output, result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("A", "B", "C"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--candidate-binding", type=Path)
    parser.add_argument("--diagnostic", choices=("native", "leaf4", "median", "zero", "positive", "seed"), default="native")
    args = parser.parse_args()
    main(args.arm, args.candidate_binding, args.diagnostic, args.output)
