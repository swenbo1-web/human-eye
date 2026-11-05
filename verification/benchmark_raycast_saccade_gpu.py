"""Run the frozen VG protocol in three independent factory-startup Blender processes.

Launch with the repository Python and --blender PATH --output-dir NEW_DIRECTORY.
The launcher uses Pillow only to assemble contact sheets after the worker exits.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import sys
from time import perf_counter_ns
import traceback
import zlib


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
METHODS = ("fixed", "active")
SCENES = 24
PROCESSES = 3
WARMUPS = 5
SAMPLES = 31
P95_LIMIT = 1.20
MINIMUM_GAIN = 5
REQUIRED_NEGATIVES = {
    "pure_color", "hud_only_fake_witness", "camera_image_mismatch",
    "wrong_object", "wrong_frame", "undeclared_removed_blocker",
}
BC_SHA256 = "03bb9ce3bd5da99299a55d47122b38ceb2bef04aba37d998b80e0ad8de4ffa09"
BC_SOURCE = "human_eye_fast/fast_bvh_clearance.py"
SOURCES = (
    "docs/VG_ACCEPTANCE_PROTOCOL.md",
    "docs/VG_IMPLEMENTATION.md",
    "human_eye_fast/raycast_saccade_gpu.py",
    "human_eye_fast/blender_resident_bridge.py",
    "human_eye_fast/resident_bridge.py",
    BC_SOURCE,
    "verification/vg_fixtures.py",
    "verification/test_raycast_saccade_gpu.py",
    SCRIPT.relative_to(ROOT).as_posix(),
)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _source_digests():
    digests = {name: _digest((ROOT / name).read_bytes()) for name in SOURCES}
    if digests[BC_SOURCE] != BC_SHA256:
        raise RuntimeError("VG verification requires the accepted BC implementation")
    return digests


def _json(path, value):
    def numeric(value):
        if hasattr(value, "tolist"):
            return value.tolist()
        raise TypeError(f"Cannot encode {type(value).__name__}")

    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=numeric)
        stream.write("\n")


def _order(index, worker):
    # Each scene occurs in all workers, and every worker starts at an even
    # scene ID. Reversing the starting order for worker 1 balances scene/order
    # coverage without interrupting within-process alternation.
    return METHODS[::-1] if (index + worker) % 2 else METHODS


def _scene_id(index, worker):
    return (index + 8 * worker) % SCENES


def _p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _distribution(values):
    return {
        "count": len(values), "median_ns": statistics.median(values),
        "p95_ns": _p95(values), "min_ns": min(values), "max_ns": max(values),
    }


def _cost(pairs):
    fixed = [pair["methods"]["fixed"]["elapsed_ns"] for pair in pairs]
    active = [pair["methods"]["active"]["elapsed_ns"] for pair in pairs]
    result = {"fixed": _distribution(fixed), "active": _distribution(active),
              "paired_active_minus_fixed": _distribution([b - a for a, b in zip(fixed, active)])}
    result["active_over_fixed_p95"] = result["active"]["p95_ns"] / result["fixed"]["p95_ns"]
    return result


def _cost_by_group(pairs):
    def grouped(key):
        groups = defaultdict(list)
        for pair in pairs:
            groups[pair[key]].append(pair)
        return {name: _cost(group) for name, group in sorted(groups.items())}

    return {"total": _cost(pairs), "by_family": grouped("family"), "by_mode": grouped("mode")}


def _quality(cases):
    def compare(group):
        passed = {method: [case["scene_id"] for case in group
                           if case["quality"][method]["passed"]] for method in METHODS}
        fixed, active = (set(passed[method]) for method in METHODS)
        return {"cases": len(group), "passed": passed,
                "successes": {method: len(ids) for method, ids in passed.items()},
                "gain": len(active) - len(fixed), "gained": sorted(active - fixed),
                "lost": sorted(fixed - active)}

    total = compare(cases)
    families = {family: compare([c for c in cases if c["family"] == family])
                for family in sorted({c["family"] for c in cases})}
    modes = {mode: compare([c for c in cases if c["mode"] == mode])
             for mode in sorted({c["mode"] for c in cases})}
    total["gain_percentage_points"] = 100 * total["gain"] / SCENES
    total["passed_gate"] = (
        len(cases) == SCENES and total["gain"] >= MINIMUM_GAIN and not total["lost"]
        and len(families) == 6 and all(item["successes"]["active"] for item in families.values())
    )
    return {"total": total, "by_family": families, "by_mode": modes}


def _call(renderer, prepared, fixture, method, *, audit, relation=None):
    args = {"target_ids": fixture.target_ids, "frame_id": fixture.frame_id,
            "scale_length": fixture.scale_length, "mode": fixture.mode,
            "method": method, "audit": audit}
    if relation is not None:
        args["relation"] = relation
    start = perf_counter_ns()
    observation = renderer.observe(prepared, fixture.witness, **args)
    elapsed = perf_counter_ns() - start
    return elapsed, observation


def _observation_record(elapsed, observation):
    return {"elapsed_ns": elapsed, "hud_png_bytes": len(observation.png),
            "hud_png_sha256": _digest(observation.png), "observation": observation.metadata}


def _observe_pair(renderer, prepared, fixture, order, index, *, audit=False):
    # The paired calls finish before hashing/metadata collection. Audit PNG
    # writes and independent geometry/PNG verification run after all hot pairs.
    results = {method: _call(renderer, prepared, fixture, method, audit=audit) for method in order}
    pair = {"index": index, "scene_id": fixture.scene_id, "family": fixture.family,
            "mode": fixture.mode, "order": order,
            "methods": {method: _observation_record(*results[method]) for method in order}}
    return pair, {method: result[1] for method, result in results.items()}


def _fixture_record(fixture, create_ns, prepare_ns, cold):
    return {
        "scene_id": fixture.scene_id, "family": fixture.family, "mode": fixture.mode,
        "angle_deg": fixture.angle_deg, "expected_gap_m": fixture.expected_gap_m,
        "scene_name": fixture.scene.name, "scale_length": fixture.scale_length,
        "target_ids": fixture.target_ids, "frame_id": fixture.frame_id,
        "witness": asdict(fixture.witness),
        "meshes": {key: {"vertices": len(mesh.world_m), "triangles": len(mesh.triangles),
                         "world_vertices_sha256": _digest(mesh.world_m.tobytes()),
                         "triangles_sha256": _digest(mesh.triangles.tobytes())}
                   for key, mesh in fixture.meshes.items()},
        "cold_ns": {"scene_build": fixture.build_ns, "rb_capture": fixture.rb_ns,
                    "bc_index_and_query": fixture.bc_ns, "complete_fixture_build": create_ns,
                    "shared_gpu_scene_prepare": prepare_ns,
                    "fixture_prepare_and_audited_observation_sum": {
                        method: create_ns + prepare_ns + cold["methods"][method]["elapsed_ns"]
                        for method in METHODS}},
        "first_observation": cold,
    }


def _audit_png(rgba):
    height, width, channels = rgba.shape
    if channels != 4 or rgba.dtype.name != "uint8":
        raise ValueError("Expected top-left uint8 RGBA audit pixels")
    raw = b"".join(b"\x00" + row.tobytes() for row in rgba)

    def chunk(kind, payload):
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b"")


def _save_observation(directory, record, observation):
    directory.mkdir(parents=True)
    bottom = observation.bottom_rgba
    images = {"hud": observation.png, "global": _audit_png(bottom[:, :512]),
              "local": _audit_png(bottom[:, 512:])}
    for name, image in images.items():
        path = directory / f"{name}.png"
        path.write_bytes(image)
        record.setdefault("artifacts", {})[name] = {
            "path": str(path), "sha256": _digest(image), "bytes": len(image),
        }


def _save_cold_cases(directory, cases, cold_evidence):
    for case, (_, _, observations, _) in zip(cases, cold_evidence):
        scene_directory = directory / "cases" / f"{case['scene_id']:02d}_{case['family']}"
        for method, observation in observations.items():
            observed = case["first_observation"]["methods"][method]
            if len(observed.get("artifacts", ())) != 3:
                _save_observation(scene_directory / method, observed, observation)


def _audited_call(call):
    try:
        return call()
    except Exception:
        # Malformed/undecodable evidence is a failed scene and stays visible in
        # raw evidence. Development-only scoring continues through all scenes.
        return {"passed": False, "audit_exception": traceback.format_exc()}


def _worker(worker, directory, sample_count):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    import bpy
    import gpu
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification import test_raycast_saccade_gpu as audit
    from verification.vg_fixtures import build_fixture, build_no_gap_fixture

    record = {"worker": worker, "pid": os.getpid(), "command": sys.argv,
              "status": "running", "blender_version": bpy.app.version_string,
              "blender_build_hash": bpy.app.build_hash.decode(), "python": sys.version,
              "platform": platform.platform(), "source_sha256": _source_digests(),
              "cases": [], "warmups": [], "hot_pairs": [], "no_gap": {}}
    path = directory / "raw.json"
    cold_evidence = []
    fixtures = []
    renderer = None
    try:
        start = perf_counter_ns()
        renderer = VGRenderer()
        record["cold_renderer_init_ns"] = perf_counter_ns() - start
        record["gpu"] = {"vendor": gpu.platform.vendor_get(), "renderer": gpu.platform.renderer_get(),
                         "backend": gpu.platform.backend_type_get(), "version": gpu.platform.version_get()}
        _json(path, record)
        for scene_id in range(SCENES):
            start = perf_counter_ns()
            fixture = build_fixture(scene_id)
            created = perf_counter_ns()
            fixtures.append(fixture)
            oracle = audit.SceneOracle(fixture)
            before_prepare = perf_counter_ns()
            prepared = renderer.prepare(fixture.meshes)
            ready = perf_counter_ns()
            pair, observations = _observe_pair(renderer, prepared, fixture, _order(scene_id, worker),
                                               scene_id, audit=True)
            case = _fixture_record(fixture, created - start, ready - before_prepare, pair)
            record["cases"].append(case)
            cold_evidence.append((fixture, prepared, observations, oracle))
        _save_cold_cases(directory, record["cases"], cold_evidence)
        _json(path, record)
        print(f"VG worker {worker}: completed 24 first-observation pairs", flush=True)

        for index in range(WARMUPS):
            fixture, prepared, _, _ = cold_evidence[index]
            pair, _ = _observe_pair(renderer, prepared, fixture, _order(index, worker), index)
            record["warmups"].append(pair)
        for index in range(sample_count):
            fixture, prepared, _, _ = cold_evidence[_scene_id(index, worker)]
            pair, _ = _observe_pair(renderer, prepared, fixture, _order(index, worker), index)
            record["hot_pairs"].append(pair)
        record["hot_cost"] = _cost_by_group(record["hot_pairs"])
        print(f"VG worker {worker}: completed {sample_count} full hot pairs", flush=True)
        _json(path, record)

        for case, (fixture, _, observations, oracle) in zip(record["cases"], cold_evidence):
            case["quality"] = {method: _audited_call(lambda: audit.score_observation(
                fixture, observation, oracle=oracle, baseline=method == "fixed"))
                for method, observation in observations.items()}
            _json(path, record)

        blocker_free = cold_evidence[0][2]["fixed"]
        blocked, _, observations, blocker_oracle = cold_evidence[4]
        record["negative_controls"] = _audited_call(lambda: audit.negative_controls(
            blocked, observations["fixed"], observations["active"], oracle=blocker_oracle,
            blocker_free_observation=blocker_free))
        for relation in ("CONTACT", "INTERSECTION"):
            fixture = build_no_gap_fixture(relation)
            fixtures.append(fixture)
            prepared = renderer.prepare(fixture.meshes)
            entry = record["no_gap"][relation] = {}
            oracle = audit.SceneOracle(fixture)
            for method in METHODS:
                elapsed, observation = _call(renderer, prepared, fixture, method, audit=True, relation=relation)
                result = entry[method] = _observation_record(elapsed, observation)
                _save_observation(directory / "controls" / relation / method, result, observation)
                result["quality"] = _audited_call(lambda: audit.score_no_gap(
                    fixture, observation, oracle=oracle, baseline=method == "fixed"))
        record["quality"] = _quality(record["cases"])
        record["status"] = "completed"
        _json(path, record)
    except Exception:
        record["status"] = "failed"
        record["exception"] = traceback.format_exc()
        _json(path, record)
        _save_cold_cases(directory, record["cases"], cold_evidence)
        _json(path, record)
        raise
    finally:
        if renderer is not None:
            renderer.close()
        for fixture in reversed(fixtures):
            fixture.close()


def _contact_sheets(directory, cases):
    from PIL import Image, ImageDraw

    width, height, label_height = 256, 128, 26
    for kind in ("bottom", "hud"):
        sheet = Image.new("RGB", (4 * 2 * width, 6 * (height + label_height)), "#141820")
        draw = ImageDraw.Draw(sheet)
        for case in cases:
            row, variant = divmod(case["scene_id"], 4)
            y = row * (height + label_height)
            for column, method in enumerate(METHODS):
                x = (variant * 2 + column) * width
                artifacts = case["first_observation"]["methods"][method]["artifacts"]
                if kind == "bottom":
                    for panel, name in enumerate(("global", "local")):
                        with Image.open(artifacts[name]["path"]) as image:
                            sheet.paste(image.resize((height, height), Image.Resampling.BOX),
                                        (x + panel * height, y + label_height))
                else:
                    with Image.open(artifacts["hud"]["path"]) as image:
                        sheet.paste(image.resize((width, height), Image.Resampling.BOX),
                                    (x, y + label_height))
                status = "PASS" if case["quality"][method]["passed"] else "FAIL"
                label = f"{case['scene_id']:02d} {case['family']} {variant} / {method.upper()} / {status}"
                draw.text((x + 7, y + 6), label, fill="#f4f6fa" if status == "PASS" else "#ff9f8c")
        sheet.save(directory / f"contact_sheet_{kind}.png")


def _coverage(pairs):
    by_scene = defaultdict(Counter)
    for pair in pairs:
        by_scene[pair["scene_id"]]["-".join(pair["order"])] += 1
    return dict(sorted(by_scene.items()))


def _launch(blender, directory, pilot):
    directory.mkdir(parents=True, exist_ok=False)
    process_count, sample_count = (1, 5) if pilot else (PROCESSES, SAMPLES)
    manifest = {"status": "running", "mode": "pilot" if pilot else "full",
                "command": [sys.executable, *sys.argv], "cwd": str(ROOT),
                "source_sha256": _source_digests(), "processes": [],
                "settings": {"processes": process_count, "scenes": SCENES, "warmups": WARMUPS,
                             "samples_per_process": sample_count, "p95": "nearest rank",
                             "p95_limit": P95_LIMIT, "minimum_gain": MINIMUM_GAIN},
                "timing_boundary": {"cold": "Renderer init, fixture build, shared prepare and first observations recorded separately. Both cold methods request an audit-only bottom copy.",
                                    "hot": "Synchronous observe call with existing RB and BC facts and prepared scene. Includes actual GPU completion and readback, HUD and public PNG encoding plus metadata. Excludes later artifact writes, hashes and scoring."}}
    path = directory / "run.json"
    _json(path, manifest)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    records = []
    for worker in range(process_count):
        target = directory / f"process_{worker:02d}"
        target.mkdir()
        command = [str(blender), "--background", "--factory-startup", "--disable-autoexec",
                   "--python-exit-code", "10", "--python", str(SCRIPT), "--",
                   "--worker", str(worker), "--output-dir", str(target), "--sample-count", str(sample_count)]
        log = target / "blender.log"
        print(f"Starting VG Blender worker {worker}. Evidence: {target}", flush=True)
        started = perf_counter_ns()
        with log.open("wb") as stream:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        manifest["processes"].append({"worker": worker, "command": command, "exit_code": process.returncode,
                                      "process_wall_ns": perf_counter_ns() - started,
                                      "log": str(log), "raw": str(target / "raw.json")})
        if process.returncode:
            manifest["status"] = "worker_failed"
            _json(path, manifest)
            return process.returncode
        raw = json.loads((target / "raw.json").read_text(encoding="utf-8"))
        if raw["status"] != "completed" or raw["source_sha256"] != manifest["source_sha256"]:
            manifest["status"] = "inconsistent_worker_evidence"
            _json(path, manifest)
            return 1
        records.append(raw)
        _json(path, manifest)

    pairs = [pair for record in records for pair in record["hot_pairs"]]
    coverage = _coverage(pairs)
    manifest["hot_cost"] = _cost_by_group(pairs)
    manifest["scene_order_coverage"] = coverage
    manifest["per_process"] = [
        {key: record[key] for key in ("worker", "gpu", "hot_cost", "quality", "negative_controls", "no_gap")}
        for record in records]
    manifest["quality_same_pass_sets_all_processes"] = all(
        record["quality"]["total"]["passed"] == records[0]["quality"]["total"]["passed"] for record in records)
    manifest["quality_gate_passed"] = all(record["quality"]["total"]["passed_gate"] for record in records)
    manifest["timing_gate_passed"] = manifest["hot_cost"]["total"]["active_over_fixed_p95"] <= P95_LIMIT
    manifest["per_process_timing_gate_passed"] = all(
        record["hot_cost"]["total"]["active_over_fixed_p95"] <= P95_LIMIT for record in records)
    manifest["no_gap_gate_passed"] = all(
        result["quality"]["passed"] for record in records
        for entry in record["no_gap"].values() for result in entry.values())
    manifest["negative_controls_passed"] = all(
        REQUIRED_NEGATIVES.issubset(record["negative_controls"])
        and all(control["rejected"] for control in record["negative_controls"].values())
        for record in records)
    manifest["full_schedule"] = (
        len(pairs) == PROCESSES * SAMPLES and len(coverage) == SCENES
        and all(len(orders) == 2 for orders in coverage.values())
        and Counter(sum(orders.values()) for orders in coverage.values()) == {3: 3, 4: 21})
    manifest["author_gates_passed"] = all(manifest[key] for key in (
        "quality_gate_passed", "timing_gate_passed", "per_process_timing_gate_passed",
        "no_gap_gate_passed", "negative_controls_passed", "full_schedule"))
    for record in records:
        target = directory / f"process_{record['worker']:02d}"
        _contact_sheets(target, record["cases"])
        manifest["processes"][record["worker"]]["contact_sheets"] = {
            str(sheet): _digest(sheet.read_bytes()) for sheet in sorted(target.glob("contact_sheet_*.png"))}
    manifest["status"] = "completed"
    _json(path, manifest)
    print(f"VG evidence: {path}", flush=True)
    return 0 if pilot or manifest["author_gates_passed"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pilot", action="store_true", help="One worker and five hot pairs; cannot pass the full protocol")
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--sample-count", type=int, default=SAMPLES, help=argparse.SUPPRESS)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    args = parser.parse_args(argv)
    if args.worker is not None:
        _worker(args.worker, args.output_dir.resolve(), args.sample_count)
        return 0
    if args.blender is None:
        parser.error("--blender is required for the launcher")
    return _launch(args.blender.resolve(), args.output_dir.resolve(), args.pilot)


if __name__ == "__main__":
    status = main()
    if "--" not in sys.argv:
        raise SystemExit(status)
