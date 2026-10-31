"""Isolated old/new in-memory router observation benchmark for T06.

The frozen T04 source is read only as a runtime baseline. No model requests,
host connections, prompts/answers from the experiment, or original scores are
opened. Percentiles cover child-process in-memory observations, not interpreter
startup, IPC, model inference, image delivery, or end-to-end host latency.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time


_SIGNS = ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
          (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
_FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
          [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]


def make_scene(count, step=0, mode="cold"):
    if type(count) is not int or not 3 <= count <= 256:
        raise ValueError("Fixture count must be 3..256")
    def box(identity, center, focal=False):
        return {"object_id": identity, "mark_label": "#" + identity, "name": identity,
            "vertices": [[center[k] + sign[k] / 2 for k in range(3)] for sign in _SIGNS],
            "faces": _FACES, "edges": None, "color_rgb": [70,140,210],
            "is_focal_target": focal, "local_axes": [[1,0,0],[0,1,0],[0,0,1]],
            "pivot_world": center}
    shift = step * .001 if mode == "focal_move" else 0.
    values = [box("focal", [shift,0,0], True), box("reference", [0,0,1.01])]
    values += [box("obstacle-" + str(i), [3*i,
        step*.001 if mode == "unrelated_move" and i == count-2 else 0., 0])
        for i in range(1, count-1)]
    return {"revision": "r" + str(0 if mode == "whole_cache" else step),
        "source": "t06_independent_axis_box_fixture", "unit": "m", "coordinate_frame": "world",
        "meshes": values}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _percentiles(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None}
    def at(fraction):
        position = (len(values)-1) * fraction
        left = int(position)
        right = min(left+1, len(values)-1)
        return values[left] + (values[right]-values[left]) * (position-left)
    return {"count": len(values), "p50_ms": at(.5), "p95_ms": at(.95), "p99_ms": at(.99)}


def _worker(runtime_root):
    chosen = Path(runtime_root).resolve()
    workspace = Path(__file__).resolve().parents[1]
    # The worker script itself is outside the chosen frozen runtime. Remove
    # its workspace path and empty cwd entries before importing engine code.
    sys.path[:] = [entry for entry in sys.path if entry and not Path(entry).resolve().is_relative_to(workspace)]
    sys.path.insert(0, str(chosen))
    os.environ.pop("PYTHONPATH", None)
    import human_eye_plugin.auto_router as router_module
    import human_eye_plugin.geometry_safety as geometry_module
    import human_eye_foveated_renderer as renderer_module
    from human_eye_plugin.runtime_identity import runtime_identity
    modules = [router_module, geometry_module, renderer_module]
    counter = {"strict_pair_calls": 0, "single_support_checks": 0}
    original_measure = router_module.measure_pair_geometry
    def counted_measure(*args, **kwargs):
        counter["strict_pair_calls"] += 1
        return original_measure(*args, **kwargs)
    router_module.measure_pair_geometry = counted_measure
    try:
        import human_eye_plugin.spatial_index as index_module
    except ModuleNotFoundError as exc:
        if exc.name != "human_eye_plugin.spatial_index":
            raise
    else:
        modules.append(index_module)
        original_support = index_module.solid_support_status
        def counted_support(*args, **kwargs):
            counter["single_support_checks"] += 1
            return original_support(*args, **kwargs)
        index_module.solid_support_status = counted_support
    paths = {module.__name__: Path(module.__file__).resolve() for module in modules}
    if any(not path.is_relative_to(chosen) for path in paths.values()):
        raise RuntimeError("Worker imported engine code outside selected runtime")
    identity = runtime_identity(mode="router")
    manifest = {item["path"]: item["sha256"] for item in identity["source_files"]}
    print(json.dumps({"ready": True, "runtime_root": str(chosen), "cwd": str(Path.cwd()),
        "module_paths": {key: str(value) for key, value in paths.items()},
        "source_sha256": manifest, "build_id": identity["build_id"],
        "implementation_revision": identity["implementation_revision"],
        "pythonpath_removed": "PYTHONPATH" not in os.environ}), flush=True)
    router = None
    case = None
    for line in sys.stdin:
        command = json.loads(line)
        if command["command"] == "init":
            case = command["case"]
            router = None if case["mode"] == "cold" else router_module.HumanEyeAutoRouter(quad_size=64)
            output = {"initialized": True}
        elif command["command"] == "sample":
            counter.update(strict_pair_calls=0, single_support_checks=0)
            event = {"event": "before_model", "session_id": "t06-router-benchmark",
                "task_kind": "spatial_3d", "task_instruction": "Measure the known focal/reference clearance.",
                "focal_id": "focal", "reference_id": "reference", "include_image": False,
                "scene": make_scene(case["objects"], command["step"], case["mode"])}
            started = time.perf_counter_ns()
            if case["mode"] == "cold":
                router = router_module.HumanEyeAutoRouter(quad_size=64)
            result = router.handle_event(event)
            elapsed = time.perf_counter_ns() - started
            facts = json.loads(result["context_text"]) if result.get("context_text") else {}
            output = {"duration_ms": elapsed / 1_000_000,
                "route": result["route"], "reason_codes": result["reason_codes"],
                "measurement_valid": result["measurement_valid"], "cache_hit": result["cache_hit"],
                "requires_reobserve": result["requires_reobserve"],
                "reference_signed_clearance_m": facts.get("measurement", {}).get("signed_clearance_m"),
                "measurement_cache": {key: facts.get("measurement_cache", {}).get(key)
                    for key in ("hits", "misses", "scope")}, **counter}
        elif command["command"] == "geometry_reference":
            # This test/helper is intentionally loaded only from current root.
            from verification.test_spatial_index import benchmark_spatial_index
            output = benchmark_spatial_index(repeats=command["repeats"])
        elif command["command"] == "finish":
            current = {relative: _sha(chosen / relative) for relative in manifest}
            output = {"source_stable": current == manifest, "source_sha256_after": current}
        else:
            raise ValueError("Unknown benchmark worker command")
        print(json.dumps(output, allow_nan=False), flush=True)


class IsolatedWorker:
    def __init__(self, runtime_root, neutral_cwd):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        self.process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()),
            "--worker", "--runtime-root", str(Path(runtime_root).resolve())],
            cwd=neutral_cwd, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, encoding="utf-8", text=True, bufsize=1)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.ready = self._read()

    def _read(self):
        try:
            line = self.pool.submit(self.process.stdout.readline).result(timeout=60)
        except Exception:
            self.process.kill()
            raise
        if not line:
            self.process.wait(timeout=5)
            raise RuntimeError("Benchmark worker exited: " + self.process.stderr.read()[-2000:])
        return json.loads(line)

    def ask(self, command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        return self._read()

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.pool.shutdown(wait=True)


def run_benchmark(*, frozen_runtime, current_runtime, repeats=20, warmup=3, seed=20261023,
                  include_geometry=True):
    if type(repeats) is not int or repeats < 2 or type(warmup) is not int or warmup < 1:
        raise ValueError("Use repeats>=2 and warmup>=1")
    workers = {}
    rows, order_log, finishes = [], [], {}
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="human-eye-t06-neutral-") as neutral:
        try:
            for name, root in (("frozen_p0", frozen_runtime), ("current", current_runtime)):
                workers[name] = IsolatedWorker(root, neutral)
            for count in (10, 20, 100):
                for mode in ("cold", "whole_cache", "focal_move", "unrelated_move"):
                    case = {"objects": count, "mode": mode}
                    for worker in workers.values():
                        worker.ask({"command": "init", "case": case})
                    for step in range(repeats + warmup):
                        order = list(workers)
                        rng.shuffle(order)
                        order_log.append({**case, "step": step, "warmup": step < warmup, "order": order})
                        for name in order:
                            result = workers[name].ask({"command": "sample", "step": step})
                            rows.append({**case, "runtime": name, "step": step,
                                "included_in_percentiles": step >= warmup, **result})
            geometry = workers["current"].ask({"command": "geometry_reference", "repeats": repeats}) if include_geometry else None
            for name, worker in workers.items():
                finishes[name] = worker.ask({"command": "finish"})
            identities = {name: worker.ready for name, worker in workers.items()}
        finally:
            for worker in workers.values():
                worker.close()
    summary = []
    for count in (10, 20, 100):
        for mode in ("cold", "whole_cache", "focal_move", "unrelated_move"):
            group = {"objects": count, "mode": mode, "runtimes": {}}
            for name in workers:
                selected = [row for row in rows if row["objects"] == count and row["mode"] == mode
                            and row["runtime"] == name and row["included_in_percentiles"]]
                completed = [row for row in selected if row["route"] == "engine" and row["measurement_valid"] is True]
                rejected = [row for row in selected if row not in completed]
                group["runtimes"][name] = {"completed_observations": len(completed), "rejected_observations": len(rejected),
                    "completed_timing": _percentiles([row["duration_ms"] for row in completed]),
                    "rejection_timing": _percentiles([row["duration_ms"] for row in rejected]),
                    "strict_pair_calls": sorted({row["strict_pair_calls"] for row in selected}),
                    "single_support_checks": sorted({row["single_support_checks"] for row in selected}),
                    "cache_hit_count": sum(row["cache_hit"] is True for row in selected),
                    "reason_codes": sorted({reason for row in rejected for reason in row["reason_codes"]})}
            baseline, current = group["runtimes"]["frozen_p0"], group["runtimes"]["current"]
            group["both_production_runtimes_complete"] = (baseline["completed_observations"] == repeats
                and current["completed_observations"] == repeats)
            old_p95, new_p95 = baseline["completed_timing"]["p95_ms"], current["completed_timing"]["p95_ms"]
            group["p95_reduction_fraction"] = (1-new_p95/old_p95 if group["both_production_runtimes_complete"] and old_p95 else None)
            summary.append(group)
    checks = {"loaded_only_selected_runtime_roots": all(item["ready"] and item["pythonpath_removed"] for item in identities.values()),
        "sources_unchanged_during_measurement": all(item["source_stable"] for item in finishes.values()),
        "all_current_observations_valid": all(row["route"] == "engine" and row["measurement_valid"] is True for row in rows if row["runtime"] == "current"),
        "baseline_10_20_observations_valid": all(row["route"] == "engine" and row["measurement_valid"] is True for row in rows if row["runtime"] == "frozen_p0" and row["objects"] in (10,20)),
        "baseline_100_rejection_recorded": all(row["route"] == "blocked" and "geometry_resource_limit" in row["reason_codes"] for row in rows if row["runtime"] == "frozen_p0" and row["objects"] == 100),
        "independent_reference_clearance_matches": all(abs(row["reference_signed_clearance_m"]-.01) < 1e-10 for row in rows if row["route"] == "engine")}
    return {"schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "isolated_in_memory_router_observations_no_images_no_host_no_model",
        "excluded_stages": ["interpreter_startup", "IPC", "host_capture", "image_rendering", "provider_inference"],
        "cold_scope": "router_construction_plus_handle_event", "warm_scope": "handle_event_only",
        "representations_byte_identical": False,
        "representation_difference": "far_objects_exact_clearance_in_frozen_vs_explicit_lower_bounds_in_current",
        "model_requests": 0, "provider_usage": None, "seed": seed, "repeats": repeats, "warmup": warmup,
        "runtime_identities": identities, "source_finish_checks": finishes, "summary": summary,
        "sample_order": order_log, "samples": rows, "geometry_reference": geometry,
        "checks": checks, "all_checks_passed": all(checks.values()),
        "interpretation": "report_negative_results_no_universal_speedup_or_token_savings_claim"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--runtime-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--frozen-runtime", type=Path)
    parser.add_argument("--current-runtime", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--skip-geometry-reference", action="store_true")
    args = parser.parse_args(argv)
    if args.worker:
        _worker(args.runtime_root)
        return 0
    if args.frozen_runtime is None or args.output_dir is None:
        parser.error("--frozen-runtime and --output-dir are required")
    # Do not overwrite old proof or experiment artifacts.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = run_benchmark(frozen_runtime=args.frozen_runtime, current_runtime=args.current_runtime,
        repeats=args.repeats, warmup=args.warmup, seed=args.seed, include_geometry=not args.skip_geometry_reference)
    report["benchmark_script_sha256"] = _sha(__file__)
    target = args.output_dir / "spatial_index_benchmark.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"report": str(target.resolve()), "all_checks_passed": report["all_checks_passed"],
        "comparisons": [{"objects": row["objects"], "mode": row["mode"], "p95_reduction_fraction": row["p95_reduction_fraction"]}
                        for row in report["summary"]]}, indent=2))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
