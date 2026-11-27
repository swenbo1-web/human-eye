"""Deterministic counterfactual on the frozen 042 H3 packet; no performance samples."""

import hashlib
import inspect
import json
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


PLAN = Path("D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/replay/PLAN_02.json")
PLAN_SHA = "e4052259504ee5b15f1a4315b294d91ac8759b8e6301673c1057e7433902743d"
CAPTURE_SHA = "6f6274e27ce2a3a1137a1dc817aca2413362d31027416bff3aff45fb831090b9"
FIELDS = ("tree_build_units", "node_pair_visits", "leaf_pair_visits", "queue_pushes",
          "narrow_phase_pairs", "work_units", "witness_projection_tests", "witness_projection_pruned_pairs")


def verify(ok, message):
    if not ok:
        raise ValueError(message)


def pinned(path, sha):
    data = Path(path).read_bytes()
    verify(hashlib.sha256(data).hexdigest() == sha, str(path))
    return data


def isolate_priority(kernel, priority):
    """Change only a comparison consumer; preserve the original bounds and saved sibling priorities."""
    if priority == "neutral_seed_center":
        before = "(k0, cd0, c0[10]) <= (k1, cd1, c1[10])"
        after = "(k0, c0[10]) <= (k1, c1[10])"
        occurrences = 2
    else:
        secondary_keys = {
            "neutral_queue_center": "0",
            "neutral_zero_queue_center": "(0 if shift == 0 and key == 0 else cdist)",
            "neutral_positive_queue_center": "(0 if shift == 0 and key > 0 else cdist)",
        }
        verify(priority in secondary_keys, "priority control name")
        before = "heapq.heappush(pending, (key, cdist, serial, sl, sr))"
        after = f"heapq.heappush(pending, (key, {secondary_keys[priority]}, serial, sl, sr))"
        occurrences = 1
    source = inspect.getsource(kernel._nearest_tree)
    verify(source.count(before) == occurrences, "fixed priority substitution")
    test_functions = {}
    exec(compile(source.replace(before, after), "<043-priority-diagnostic>", "exec"),
         vars(kernel), test_functions)
    return test_functions["_nearest_tree"]


def probe(arm, left_size, right_size, *, layout="native", priority="native"):
    plan = json.loads(pinned(PLAN, PLAN_SHA))
    capture = json.loads(pinned(plan["capture"]["path"], CAPTURE_SHA))
    binding_ref = plan["arms"][arm]["binding"]
    install = json.loads(pinned(binding_ref["path"], binding_ref["sha256"]))
    site = Path(install["site_packages"])
    verify(len(install["source_files"]) == 143, "installed file count")
    for file in install["source_files"]:
        pinned(site / file["path"], file["sha256"])
    sys.path.insert(0, str(site))
    from human_eye_plugin import source_region, surface_geometry, surface_proximity

    query = source_region.validate_scoped_measurement_arguments({"include_image": False, "query": plan["query"]})
    binding = capture["binding"]
    deadline = time.monotonic() + plan["request_budget_s"]

    def checkpoint(stage):
        if time.monotonic() >= deadline:
            raise TimeoutError(stage)

    def run():
        return source_region.measure_selective_region(
            capture, binding["target_selector"], binding["reference_selector"], binding["world_box_m"],
            binding["host_source_sha256"], checkpoint)

    original = surface_geometry._bvh if layout == "native" else surface_geometry._bvh_median
    original_queue_bounds = getattr(surface_proximity, "_node_queue_bounds", None)
    sizes = [left_size, right_size]
    builds = []

    def build(bounds, budget, *, leaf_size):
        i = len(builds)
        verify(i < 2 and leaf_size == 2 and len(bounds) == (262, 12)[i], "unexpected R3 builder call")
        builds.append([len(bounds), sizes[i]])
        return original(bounds, budget, leaf_size=sizes[i])

    def neutral_center(*args, **kwargs):
        lower, _ = original_queue_bounds(*args, **kwargs)
        return lower, 0

    override_build = arm == "r3" and (sizes != [2, 2] or layout == "median")
    with ExitStack() as replacements:
        if override_build:
            replacements.enter_context(patch.object(surface_geometry, "_bvh", build))
        if priority == "neutral_center":
            verify(arm == "r3", "R3 priority control")
            replacements.enter_context(patch.object(surface_proximity, "_node_queue_bounds", neutral_center))
        elif priority != "native":
            replacements.enter_context(patch.object(surface_proximity, "_nearest_tree",
                                                     isolate_priority(surface_proximity, priority)))
        value = run()
    if override_build:
        verify(len(builds) == 2, "both builder calls")
    public = source_region.project_scoped_measurement(value, query)
    query_work = value["work"]["task_query"]
    verify(query_work["surface_pair_count"] == 1 and query_work["surface_pair_cache_hit"] is False,
           "expected one fresh pair")
    expected = plan["expected_public"]
    verify(json.dumps(public, sort_keys=True) == json.dumps(expected, sort_keys=True), "complete public oracle")
    counters = query_work["surface_work"]
    return {"arm": arm, "leaf_capacity": sizes, "layout": layout, "priority": priority,
            "binding": install["identity"]["source_sha256"],
            "native_build_overrides": builds, "work": {k: counters.get(k, 0) for k in FIELDS},
            "public_sha256": hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()}


if __name__ == "__main__":
    if len(sys.argv) in (4, 6):
        options = dict(zip(("layout", "priority"), sys.argv[4:]))
        print(json.dumps(probe(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), **options)))
    else:
        leaf_cases = [("032", 4, 4), ("r3", 2, 2), ("r3", 4, 2), ("r3", 2, 4), ("r3", 4, 4)]
        cases = [(*case, "native", "native") for case in leaf_cases]
        for layout, priority in (("median", "native"), ("native", "neutral_center"), ("median", "neutral_center")):
            cases.append(("r3", 2, 2, layout, priority))
        cases.extend(("r3", 2, 2, "native", phase) for phase in ("neutral_seed_center", "neutral_queue_center"))
        cases.extend(("r3", 2, 2, "native", phase)
                     for phase in ("neutral_zero_queue_center", "neutral_positive_queue_center"))
        rows = []
        for arm, a, b, layout, priority in cases:
            command = [sys.executable, "-I", "-B", __file__, arm, str(a), str(b), layout, priority]
            rows.append(json.loads(subprocess.check_output(command)))
        print(json.dumps({"sample": "042 H3, 262 selected vs 12 reference triangles", "capture_sha256": CAPTURE_SHA,
                          "mode": "one deterministic call per arm, no timing or host qualification",
                          "rows": rows}, indent=2))
