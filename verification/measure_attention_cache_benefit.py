"""Reproducible observation-only timings, with raw samples and exact inputs.

Run from any directory: python -B verification/measure_attention_cache_benefit.py
No live Blender or external model is called. The baseline uses the saved router
source with the same geometry kernels as the current implementation.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = ROOT / "verification/baseline/20261022_before_attention_cache/human_eye_plugin/auto_router.py"

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_auto_router import box, scene
from verification.test_live_service import SelfLockingHost


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def content_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def source_hashes():
    files = [BASELINE, Path(__file__), ROOT / "human_eye_foveated_renderer.py",
             ROOT / "verification/test_auto_router.py", ROOT / "verification/test_host_runtime.py",
             ROOT / "verification/test_live_service.py"]
    files += [ROOT / "human_eye_plugin" / name for name in (
        "auto_router.py", "scene_cache.py", "geometry_safety.py", "scene_rendering.py",
        "attention_rendering.py", "attention_policy.py", "host_runtime.py", "live_service.py",
        "agent_hooks.py", "agent_adapters.py")]
    files += sorted((ROOT / "human_eye_module1_operators").glob("*.py"))
    return {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.exists()}


def baseline_class():
    spec = importlib.util.spec_from_file_location("human_eye_plugin.baseline_perf", BASELINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.HumanEyeAutoRouter


def make_scene(count):
    value = scene()
    value["source"] = "attention_cache_benchmark_complete_known_mesh_fixture"
    for index in range(count - 2):
        value["meshes"].append(box("other_" + str(index),
            [2 + index * .6, (index % 2) * .5, .35], [.15, .2, .1]))
    return value


def sample_scene(initial, iteration, motion):
    value = copy.deepcopy(initial)
    if motion:
        identity = "part" if motion == "focal" else "other_0"
        index = next(i for i, mesh in enumerate(value["meshes"]) if mesh["object_id"] == identity)
        delta = [0, 0, (iteration + 1) * 0.0001] if motion == "focal" else [(iteration + 1) * 0.0001, 0, 0]
        value["meshes"][index] = MeshEntity3D.from_dict(value["meshes"][index]).translated(delta).to_dict()
        value["revision"] = "benchmark-motion-" + str(iteration)
    return value


def percentile(values, quantile):
    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile
    lower, upper = int(rank), min(len(ordered) - 1, int(rank) + 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def summary(values):
    return {"sample_count": len(values), "median_ms": statistics.median(values),
            "p90_ms": percentile(values, .9), "minimum_ms": min(values), "maximum_ms": max(values)}


def measured_call(callback):
    began = time.perf_counter_ns()
    result = callback()
    return result, (time.perf_counter_ns() - began) / 1_000_000


def check_observation(result):
    if result["route"] != "engine" or result["measurement_valid"] is not True or result["cache_hit"]:
        raise AssertionError("Benchmark must compute a new valid observation: " + repr(result))
    if result["image"] is not None:
        raise AssertionError("Text-only benchmark unexpectedly rendered an image")
    return json.loads(result["context_text"])


def comparable_measurements(facts):
    fields = ("measurement_valid", "signed_clearance_m", "is_penetrating", "axes_valid",
              "contact_normal_angle_deg", "tangent_yaw_mismatch_deg")
    return {contact["object_id"]: {field: contact[field] for field in fields}
            for contact in facts["scene_contacts"]}


def router_case(baseline, *, count, motion, samples, warmup):
    initial = make_scene(count)
    routers = {"baseline": baseline(quad_size=64), "current": HumanEyeAutoRouter(quad_size=64)}
    rows, warmup_rows = [], []
    for iteration in range(warmup + samples):
        value = sample_scene(initial, iteration, motion)
        event = {"event": "before_model", "session_id": "benchmark", "scene": value,
            "task_kind": "spatial_3d", "focal_id": "part", "reference_id": "base",
            "include_image": False, "task_instruction": "Measure current gap; benchmark sample " + str(iteration)}
        order = ["baseline", "current"] if iteration % 2 == 0 else ["current", "baseline"]
        row = {"iteration": iteration, "execution_order": order, "scene_sha256": content_hash(value),
               "task_instruction": event["task_instruction"]}
        result_facts = {}
        for label in order:
            result, elapsed = measured_call(lambda label=label: routers[label].handle_event(event))
            result_facts[label] = check_observation(result)
            row[label + "_ms"] = elapsed
        if comparable_measurements(result_facts["baseline"]) != comparable_measurements(result_facts["current"]):
            raise AssertionError("Baseline/current actual geometry measurement mismatch")
        current = result_facts["current"]
        row["measurement_cache_hits"] = current["measurement_cache"]["hits"]
        row["measurement_cache_misses"] = current["measurement_cache"]["misses"]
        row["retained_history_frames"] = current["scene_memory"]["stats"]["frames"]
        row["signed_clearance_m"] = current["measurement"]["signed_clearance_m"]
        (warmup_rows if iteration < warmup else rows).append(row)
    previous = summary([row["baseline_ms"] for row in rows])
    current = summary([row["current_ms"] for row in rows])
    return {"mesh_count": count, "motion": motion or "static", "initial_scene": initial,
        "initial_scene_sha256": content_hash(initial), "sample_scene_recipe":
            "No change if static. Otherwise move focal upward or other_0 right by (iteration+1)*0.0001 metre from initial geometry; replace revision with benchmark-motion-<iteration>.",
        "configuration": {"quad_size": 64, "include_image": False, "focal_id": "part", "reference_id": "base"},
        "baseline": previous, "current": current,
        "current_minus_baseline_median_ms": current["median_ms"] - previous["median_ms"],
        "median_ratio_baseline_over_current": previous["median_ms"] / current["median_ms"],
        "benefit_observed_in_this_fixture": current["median_ms"] < previous["median_ms"],
        "measurement_values_identical": True, "whole_observation_cache_hits": 0,
        "warmup_samples": warmup_rows, "samples": rows,
        "scope": "Full local router.handle_event includes event copy, validation, hashing, geometry or memo, scene history and response serialization; excludes host capture, disk state, rendering, CLI startup and model latency."}


def service_cases(*, samples, warmup, temporary_root):
    active, result = {}, {}
    for count in (2, 8):
        for frames in (1, 16):
            name = str(count) + "_objects_static_" + str(frames) + "_history_frames"
            base = temporary_root / name
            base.mkdir()
            config = {"schema_version": "1.0", "enabled": True, "project_root": str(ROOT),
                      "state_file": "state.json", "audit_file": "events.jsonl", "quad_size": 64}
            path = base / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            host = SelfLockingHost()
            host.scene = make_scene(count)
            service = LiveSpatialService(path, host=host)
            for seed in range(frames):
                host.scene["revision"] = "seed-revision-" + str(seed)
                seeded = service.observe("benchmark", "seed " + str(seed), focal_id="part",
                                         reference_id="base", include_image=False)
                if seeded["status"] != "observed":
                    raise AssertionError("Could not seed service history")
            active[name] = (host, service, base)
            result[name] = {"mesh_count": count, "seeded_history_frames": frames,
                "initial_scene": copy.deepcopy(host.scene), "initial_scene_sha256": content_hash(host.scene),
                "warmup_samples": [], "samples": [], "baseline_comparison": None,
                "scope": "Complete current LiveSpatialService.observe: in-memory fake-host capture, state/audit locks, persisted authority validation, exact hashes, history import/save, response and atomic disk writes. No actual Blender TCP or external model. No prior-version service speedup claim."}
    for iteration in range(warmup + samples):
        names = list(active)
        if iteration % 2:
            names.reverse()
        for name in names:
            host, service, base = active[name]
            task = "Service benchmark new observation " + str(iteration)
            observed, elapsed = measured_call(lambda: service.observe("benchmark", task,
                focal_id="part", reference_id="base", include_image=False))
            if observed["status"] != "observed":
                raise AssertionError(observed)
            actual = check_observation(observed["routing"])
            row = {"iteration": iteration, "task_instruction": task, "elapsed_ms": elapsed,
                   "scene_sha256": content_hash(host.scene),
                   "history_frames": actual["scene_memory"]["stats"]["frames"],
                   "measurement_cache_hits": actual["measurement_cache"]["hits"],
                   "measurement_cache_misses": actual["measurement_cache"]["misses"],
                   "state_file_bytes": (base / "state.json").stat().st_size}
            if row["history_frames"] != result[name]["seeded_history_frames"]:
                raise AssertionError("History frame count changed during static benchmark")
            result[name]["warmup_samples" if iteration < warmup else "samples"].append(row)
    for value in result.values():
        value["timing"] = summary([row["elapsed_ms"] for row in value["samples"]])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "verification/fixes/20261022_attention_cache/cache_benchmark.json")
    options = parser.parse_args()
    if options.samples < 20 or options.warmup < 3:
        parser.error("at least 20 samples and 3 warmup rounds required")
    started = datetime.now(timezone.utc).isoformat()
    hashes_before = source_hashes()
    baseline = baseline_class()
    cases = {}
    for name, count, motion in (("two_objects_static", 2, None), ("two_objects_focal_moves", 2, "focal"),
                               ("eight_objects_static", 8, None), ("eight_objects_third_moves", 8, "third")):
        cases[name] = router_case(baseline, count=count, motion=motion,
                                 samples=options.samples, warmup=options.warmup)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cache-benchmark-", dir=options.output.parent) as temporary:
        services = service_cases(samples=options.samples, warmup=options.warmup, temporary_root=Path(temporary))
    hashes_after = source_hashes()
    if hashes_after != hashes_before:
        raise RuntimeError("Measured source changed during benchmark; rerun against stable files")
    report = {"schema_version": "1.0", "kind": "local_observation_cache_benefit_benchmark",
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"platform": platform.platform(), "python": sys.version,
                        "executable": sys.executable, "processor": platform.processor()},
        "method": {"samples_per_case": options.samples, "warmup_per_case": options.warmup,
            "timer": "perf_counter_ns", "p90_definition": "linear interpolation at sorted index (n-1)*0.9",
            "router_execution_order": "alternates baseline,current and current,baseline per paired iteration",
            "baseline_load_name": "human_eye_plugin.baseline_perf", "baseline_path": str(BASELINE),
            "whole_observation_reuse": "disabled by unique task_instruction in every sample",
            "include_image": False, "measurement_equivalence": "all pair clearances, collision flags and axes/angles asserted equal",
            "costs_are_measured": True, "estimated_compute_ms_avoided_used": False},
        "source_sha256": hashes_before, "source_stable_during_run": True,
        "router_cases": cases, "current_live_service_cases": services,
        "limitations": ["Synthetic complete known box meshes, one local machine and one run.",
            "No rendering, attention-shift view costs, live Blender transport, CLI startup, model inference, or billing measured.",
            "Changing geometry can eliminate memo benefit while history/hash work still incurs cost; negative results are retained.",
            "Baseline router is the saved pre-change source using the same current geometry kernels; source hashes identify both.",
            "Service timings include persisted state and audit I/O with a fake capture host; there is no prior-service comparison.",
            "Reported ratios apply only to these fixtures, not general scenes or end-to-end agent speedup."],
        "blender_calls": 0, "model_api_calls": 0}
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(options.output), "router": {name: {
        "baseline_median_ms": value["baseline"]["median_ms"], "current_median_ms": value["current"]["median_ms"],
        "ratio": value["median_ratio_baseline_over_current"]} for name, value in cases.items()},
        "service": {name: value["timing"] for name, value in services.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
