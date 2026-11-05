"""Measure a VG refinement directly against the frozen implementation.

Four independent renderer/resource sets run in balanced order. All PNG
decoding, comparisons, hashes, writes, and scoring happen outside observe.
Exit zero means complete evidence, not final reviewer acceptance.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import struct
import subprocess
import sys
from time import perf_counter_ns
import traceback


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
sys.path.insert(0, str(ROOT))
from verification import benchmark_raycast_saccade_gpu as author

BASELINE = "verification/baselines/vg_implementation.py"
BASELINE_SHA256 = "d8067ddab30d56d381c39251eb5270bf41b63b863bd6604ce0348ba2ba468bb6"
RUNTIME = "human_eye_fast/raycast_saccade_gpu.py"
ROUTES = ("A_fixed", "A_active", "R_fixed", "R_active")
VERSIONS = ("A", "R")
METHODS = ("fixed", "active")
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
SOURCES = tuple(dict.fromkeys((*author.SOURCES, "docs/VG_REFINEMENT_PROTOCOL.md", BASELINE,
                              SCRIPT.relative_to(ROOT).as_posix())))
BOOTSTRAP_SEED = 721091
BOOTSTRAP_REPLICATES = 6000
PNG_SIZE_LIMIT = 1.00


def _sources():
    result = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    if result[BASELINE] != BASELINE_SHA256:
        raise RuntimeError("Frozen VG implementation does not match author_002")
    if result[author.BC_SOURCE] != author.BC_SHA256:
        raise RuntimeError("Accepted BC source changed")
    return result


def _order(index, worker):
    # Each 4-call block is a Williams order. Rotate again after 24 scenes,
    # so a repeated scene does not retain its previous call position.
    return tuple(ROUTES[i] for i in ORDERS[(index + worker + index // 24) % 4])


def _versions():
    name = "_vg_frozen_implementation"
    spec = importlib.util.spec_from_file_location(name, ROOT / BASELINE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    from human_eye_fast import raycast_saccade_gpu
    return {"A": module, "R": raycast_saccade_gpu}


def _metadata(metadata):
    result = deepcopy(metadata)
    for view in result["views"].values():
        view["rna"].pop("name", None)
    return result


def _ancillary(png):
    """Compare color and physical-display semantics as well as pixel bytes."""
    result = {}
    offset = 8
    while offset + 12 <= len(png):
        length, kind = struct.unpack_from(">I4s", png, offset)
        data = png[offset + 8:offset + 8 + length]
        if kind not in (b"IHDR", b"IDAT"):
            result.setdefault(kind.decode("ascii"), []).append(data.hex())
        offset += length + 12
    return result


def _compare(observations, audit):
    import numpy as np

    result = {}
    for method in METHODS:
        before, after = (observations[f"{version}_{method}"] for version in VERSIONS)
        pixels_a, pixels_r = audit.decode_png(before.png), audit.decode_png(after.png)
        mismatch = np.any(pixels_a != pixels_r, axis=2)
        size_ratio = len(after.png) / len(before.png)
        entry = {
            "rgba_equal": bool(not mismatch.any()),
            "mismatched_pixel_count": int(mismatch.sum()),
            "max_channel_difference": int(np.abs(pixels_a.astype(np.int16) - pixels_r).max()),
            "metadata_equal_except_camera_name": _metadata(before.metadata) == _metadata(after.metadata),
            "ancillary_chunks_equal": _ancillary(before.png) == _ancillary(after.png),
            "png_bytes_A": len(before.png), "png_bytes_R": len(after.png),
            "png_bytes_ratio_R_over_A": size_ratio,
            "png_size_limit_passed": size_ratio <= PNG_SIZE_LIMIT,
        }
        if mismatch.any():
            entry["first_mismatched_yx"] = np.argwhere(mismatch)[:8].tolist()
        if before.bottom_rgba is not None and after.bottom_rgba is not None:
            entry["bottom_rgba_equal"] = bool(np.array_equal(before.bottom_rgba, after.bottom_rgba))
        entry["passed"] = all(entry[key] for key in (
            "rgba_equal", "metadata_equal_except_camera_name", "ancillary_chunks_equal", "png_size_limit_passed"
        )) and entry.get("bottom_rgba_equal", True)
        result[method] = entry
    result["passed"] = all(result[method]["passed"] for method in METHODS)
    return result


def _paired(renderers, prepared, fixture, order, index, *, audit=False, relation=None):
    results = {}
    for route in order:
        method = route.split("_", 1)[1]
        results[route] = author._call(
            renderers[route], prepared[route], fixture, method, audit=audit, relation=relation)
    # Serialization and hashes are deliberately after the complete 4-call group.
    record = {"index": index, "scene_id": fixture.scene_id, "family": fixture.family,
              "mode": fixture.mode, "order": list(order),
              "routes": {route: author._observation_record(*results[route]) for route in order}}
    return record, {route: observation for route, (_, observation) in results.items()}


def _bootstrap_difference(values):
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draw = rng.integers(0, len(array), size=(BOOTSTRAP_REPLICATES, len(array)))
    interval = np.quantile(np.median(array[draw], axis=1), (.025, .975))
    return {"statistic": "median paired R minus A elapsed ns", "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES, "confidence": .95,
            "lower_ns": float(interval[0]), "upper_ns": float(interval[1])}


def _stats(pairs):
    elapsed = {route: [item["routes"][route]["elapsed_ns"] for item in pairs] for route in ROUTES}
    result = {"count": len(pairs), "elapsed": {route: author._distribution(values)
                                               for route, values in elapsed.items()},
              "refinement": {}, "within_version": {}}
    for method in METHODS:
        a, r = elapsed[f"A_{method}"], elapsed[f"R_{method}"]
        differences = [after - before for before, after in zip(a, r)]
        sizes = [item["routes"][f"R_{method}"]["hud_png_bytes"] /
                 item["routes"][f"A_{method}"]["hud_png_bytes"] for item in pairs]
        result["refinement"][method] = {
            "median_ratio_R_over_A": statistics.median(r) / statistics.median(a),
            "p95_ratio_R_over_A": author._p95(r) / author._p95(a),
            "paired_difference_ns": author._distribution(differences),
            "paired_median_difference_ci95": _bootstrap_difference(differences),
            "png_bytes_ratio": {"median": statistics.median(sizes), "p95": author._p95(sizes),
                                "min": min(sizes), "max": max(sizes)},
        }
    for version in VERSIONS:
        fixed, active = elapsed[f"{version}_fixed"], elapsed[f"{version}_active"]
        result["within_version"][version] = {
            "active_over_fixed_p95": author._p95(active) / author._p95(fixed),
            "active_over_fixed_median": statistics.median(active) / statistics.median(fixed),
        }
    return result


def _group_stats(pairs):
    result = {"total": _stats(pairs)}
    for key in ("family", "mode"):
        groups = defaultdict(list)
        for pair in pairs:
            groups[pair[key]].append(pair)
        result[f"by_{key}"] = {name: _stats(items) for name, items in sorted(groups.items())}
    return result


def _quality(cases, version):
    mapped = [{"scene_id": item["scene_id"], "family": item["family"], "mode": item["mode"],
               "quality": {method: item["quality"][f"{version}_{method}"] for method in METHODS}}
              for item in cases]
    return author._quality(mapped)


def _save_cold(directory, record, observations):
    for route, observation in observations.items():
        author._save_observation(directory / route, record["routes"][route], observation)


def _worker(worker, directory, sample_count):
    sys.dont_write_bytecode = True
    import bpy
    import gpu
    from verification import test_raycast_saccade_gpu as audit
    from verification.vg_fixtures import build_fixture, build_no_gap_fixture

    record = {"worker": worker, "pid": os.getpid(), "status": "running", "command": sys.argv,
              "blender_version": bpy.app.version_string, "blender_build_hash": bpy.app.build_hash.decode(),
              "python": sys.version, "platform": platform.platform(), "source_sha256_before": _sources(),
              "renderer_init_ns": {}, "cases": [], "warmups": [], "hot_pairs": [], "no_gap": {}}
    path = directory / "raw.json"
    fixtures, cold, renderers = [], [], {}
    try:
        versions = _versions()
        for route in _order(0, worker):
            start = perf_counter_ns()
            renderers[route] = versions[route[0]].VGRenderer()
            record["renderer_init_ns"][route] = perf_counter_ns() - start
        record["gpu"] = {"vendor": gpu.platform.vendor_get(), "renderer": gpu.platform.renderer_get(),
                         "backend": gpu.platform.backend_type_get(), "version": gpu.platform.version_get()}
        author._json(path, record)
        for scene_id in range(author.SCENES):
            start = perf_counter_ns()
            fixture = build_fixture(scene_id)
            create_ns = perf_counter_ns() - start
            fixtures.append(fixture)
            oracle = audit.SceneOracle(fixture)
            prepared, prepare_ns = {}, {}
            for route in _order(scene_id, worker):
                start = perf_counter_ns()
                prepared[route] = renderers[route].prepare(fixture.meshes)
                prepare_ns[route] = perf_counter_ns() - start
            pair, observations = _paired(renderers, prepared, fixture, _order(scene_id, worker),
                                         scene_id, audit=True)
            entry = {"scene_id": scene_id, "family": fixture.family, "mode": fixture.mode,
                     "angle_deg": fixture.angle_deg, "expected_gap_m": fixture.expected_gap_m,
                     "scale_length": fixture.scale_length, "frame_id": fixture.frame_id,
                     "target_ids": fixture.target_ids, "witness": asdict(fixture.witness),
                     "cold_ns": {"complete_fixture_build": create_ns, "scene_build": fixture.build_ns,
                                 "rb_capture": fixture.rb_ns, "bc_index_and_query": fixture.bc_ns,
                                 "prepare_per_route": prepare_ns},
                     "first_observation": pair}
            record["cases"].append(entry)
            cold.append((fixture, prepared, observations, oracle))
            _save_cold(directory / "cases" / f"{scene_id:02d}_{fixture.family}", pair, observations)
        author._json(path, record)
        print(f"VG refinement worker {worker}: 24 four-route cold observations ready", flush=True)
        for index in range(author.WARMUPS):
            fixture, prepared, _, _ = cold[index]
            pair, _ = _paired(renderers, prepared, fixture, _order(index, worker), index)
            record["warmups"].append(pair)
        hot_observations = []
        for index in range(sample_count):
            fixture, prepared, _, _ = cold[author._scene_id(index, worker)]
            pair, observations = _paired(renderers, prepared, fixture, _order(index, worker), index)
            record["hot_pairs"].append(pair)
            hot_observations.append(observations)
        # All measured calls have finished before any PNG decoding/comparison.
        record["cost"] = _group_stats(record["hot_pairs"])
        author._json(path, record)
        print(f"VG refinement worker {worker}: {sample_count} measured four-route groups complete", flush=True)
        for pair, observations in zip(record["hot_pairs"], hot_observations):
            pair["equivalence"] = _compare(observations, audit)
        hot_observations.clear()
        for entry, (fixture, _, observations, oracle) in zip(record["cases"], cold):
            entry["equivalence"] = _compare(observations, audit)
            entry["quality"] = {
                route: author._audited_call(lambda route=route, observation=observation:
                    audit.score_observation(fixture, observation, oracle=oracle,
                                            baseline=route.endswith("fixed")))
                for route, observation in observations.items()}
            author._json(path, record)
        record["negative_controls"] = {}
        for version in VERSIONS:
            blocked, _, observations, oracle = cold[4]
            record["negative_controls"][version] = author._audited_call(lambda:
                audit.negative_controls(blocked, observations[f"{version}_fixed"],
                    observations[f"{version}_active"], oracle=oracle,
                    blocker_free_observation=cold[0][2][f"{version}_fixed"]))
        for control_id, relation in enumerate(("CONTACT", "INTERSECTION")):
            fixture = build_no_gap_fixture(relation)
            fixtures.append(fixture)
            prepared = {route: renderer.prepare(fixture.meshes) for route, renderer in renderers.items()}
            oracle = audit.SceneOracle(fixture)
            pair, observations = _paired(renderers, prepared, fixture, _order(control_id, worker),
                                         control_id, audit=True, relation=relation)
            record["no_gap"][relation] = pair
            _save_cold(directory / "controls" / relation, pair, observations)
            pair["equivalence"] = _compare(observations, audit)
            pair["quality"] = {
                route: author._audited_call(lambda route=route, observation=observation:
                    audit.score_no_gap(fixture, observation, oracle=oracle,
                                       baseline=route.endswith("fixed")))
                for route, observation in observations.items()}
        record["quality"] = {version: _quality(record["cases"], version) for version in VERSIONS}
        record["source_sha256_after"] = _sources()
        record["sources_unchanged"] = record["source_sha256_before"] == record["source_sha256_after"]
        record["status"] = "completed"
        author._json(path, record)
    except BaseException:
        record["status"] = "failed"
        record["exception"] = traceback.format_exc()
        author._json(path, record)
        raise
    finally:
        for renderer in reversed(list(renderers.values())):
            renderer.close()
        for fixture in reversed(fixtures):
            fixture.close()


def _contact_sheets(directory, cases):
    for version in VERSIONS:
        target = directory / "contact_sheets" / version
        target.mkdir(parents=True)
        normalized = [{"scene_id": item["scene_id"], "family": item["family"],
                       "quality": {method: item["quality"][f"{version}_{method}"] for method in METHODS},
                       "first_observation": {"methods": {
                           method: item["first_observation"]["routes"][f"{version}_{method}"]
                           for method in METHODS}}} for item in cases]
        author._contact_sheets(target, normalized)


def _gates(records, cost, pilot):
    equivalence = all(item["equivalence"]["passed"] for record in records
                      for item in (*record["cases"], *record["hot_pairs"], *record["no_gap"].values()))
    quality = all(record["quality"][version]["total"]["passed_gate"]
                  for record in records for version in VERSIONS)
    no_gap = all(item["passed"] for record in records for control in record["no_gap"].values()
                 for item in control["quality"].values())
    negatives = all(author.REQUIRED_NEGATIVES.issubset(controls)
                    and all(item["rejected"] for item in controls.values())
                    for record in records for controls in record["negative_controls"].values())
    per_process_gain = all(record["cost"]["total"]["refinement"]["active"]["median_ratio_R_over_A"] < 1
                           for record in records)
    pooled_p95 = cost["total"]["refinement"]["active"]["p95_ratio_R_over_A"] <= 1
    supported_gain = cost["total"]["refinement"]["active"]["paired_median_difference_ci95"]["upper_ns"] < 0
    family_p95 = all(item["refinement"]["active"]["p95_ratio_R_over_A"] <= 1.10
                     for item in cost["by_family"].values())
    original_cost = cost["total"]["within_version"]["R"]["active_over_fixed_p95"] <= author.P95_LIMIT
    return {"formal_run": not pilot, "pixel_metadata_size_equivalence": equivalence,
            "original_quality_gate": quality, "zero_gap_controls": no_gap,
            "negative_controls": negatives, "each_process_active_median_faster": per_process_gain,
            "pooled_active_paired_median_ci_supports_gain": supported_gain,
            "pooled_active_p95_no_regression": pooled_p95, "each_family_active_p95_limit": family_p95,
            "original_active_over_fixed_p95_limit": original_cost,
            "sources_unchanged": all(record["sources_unchanged"] for record in records)}


def _launch(blender, directory, pilot):
    directory.mkdir(parents=True, exist_ok=False)
    workers, samples = (1, 5) if pilot else (author.PROCESSES, author.SAMPLES)
    sources = _sources()
    for name in sources:
        target = directory / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    manifest = {"status": "running", "mode": "pilot" if pilot else "formal",
                "command": [sys.executable, *sys.argv], "cwd": str(ROOT), "source_sha256": sources,
                "settings": {"workers": workers, "samples": samples, "warmups": author.WARMUPS,
                             "routes": ROUTES, "order": "Williams rows; extra rotation after each 24 cases",
                             "p95": "nearest rank", "png_size_limit_R_over_A": PNG_SIZE_LIMIT,
                             "timing": "Complete synchronous observe with ready independent per-route resources; all four calls finish before hashes; PNG decoding/comparison occurs after entire hot sequence.",
                             "same_pixels": "RGBA equality, RGB decoded with alpha 255; identical semantic ancillary PNG chunks; camera RNA names excluded from metadata comparison"},
                "processes": []}
    path = directory / "run.json"
    author._json(path, manifest)
    records = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for worker in range(workers):
        target = directory / f"process_{worker:02d}"
        target.mkdir()
        command = [str(blender), "--background", "--factory-startup", "--disable-autoexec",
                   "--python-exit-code", "10", "--python", str(SCRIPT), "--", "--worker", str(worker),
                   "--output-dir", str(target), "--sample-count", str(samples)]
        print(f"Starting VG refinement worker {worker}: {target}", flush=True)
        started = perf_counter_ns()
        with (target / "blender.log").open("wb") as stream:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        manifest["processes"].append({"worker": worker, "command": command, "exit_code": process.returncode,
                                      "process_wall_ns": perf_counter_ns() - started,
                                      "raw": str(target / "raw.json"), "log": str(target / "blender.log")})
        if process.returncode:
            manifest["status"] = "worker_failed"
            author._json(path, manifest)
            return process.returncode
        record = json.loads((target / "raw.json").read_text(encoding="utf-8"))
        if record["status"] != "completed" or record["source_sha256_before"] != sources:
            manifest["status"] = "inconsistent_evidence"
            author._json(path, manifest)
            return 1
        records.append(record)
        _contact_sheets(target, record["cases"])
        author._json(path, manifest)
    pairs = [pair for record in records for pair in record["hot_pairs"]]
    manifest["cost"] = _group_stats(pairs)
    coverage = defaultdict(Counter)
    for pair in pairs:
        coverage[pair["scene_id"]]["/".join(pair["order"])] += 1
    manifest["scene_order_coverage"] = dict(sorted(coverage.items()))
    manifest["sample_count_distribution"] = dict(Counter(sum(orders.values()) for orders in coverage.values()))
    manifest["per_process"] = [{key: record[key] for key in ("worker", "pid", "gpu", "cost", "quality")}
                                for record in records]
    manifest["gates"] = _gates(records, manifest["cost"], pilot)
    manifest["gates"]["formal_schedule"] = (not pilot and len(records) == 3 and len(pairs) == 93
        and len(coverage) == 24 and Counter(sum(orders.values()) for orders in coverage.values()) == {3: 3, 4: 21}
        and all(len(orders) >= 2 for orders in coverage.values()))
    manifest["all_declared_gates_passed"] = all(manifest["gates"].values())
    manifest["reviewer_acceptance"] = "PENDING; complete evidence is not adoption"
    manifest["status"] = "completed"
    author._json(path, manifest)
    print(f"VG refinement complete: {path}; declared gates={manifest['all_declared_gates_passed']}", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--sample-count", type=int, default=author.SAMPLES, help=argparse.SUPPRESS)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    args = parser.parse_args(argv)
    if args.worker is not None:
        _worker(args.worker, args.output_dir.resolve(), args.sample_count)
        return 0
    if args.blender is None:
        parser.error("--blender is required")
    return _launch(args.blender.resolve(), args.output_dir.resolve(), args.pilot)


if __name__ == "__main__":
    status = main()
    if "--" not in sys.argv:
        raise SystemExit(status)
