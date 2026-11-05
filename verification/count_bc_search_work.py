"""Count BC search work on the frozen 16 grid states; never measure latency.

Each implementation loads in its own module. Counters wrap complete
update+query calls and are removed afterwards. A face-pair count means pairs
submitted to the exact narrow-phase batch, not fully evaluated features: an
intersection can return early, and the compact kernel skips redundant edge
features. Node counts cover _node_bounds AABB evaluations, including seeding;
they do not count projection/refit arithmetic performed outside that helper.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from verification.benchmark_fast_bvh_clearance import _grid_case
from verification.test_bc_acceptance import surface_tolerance


SOURCES = {
    "A": "verification/baselines/bc_implementation.py",
    "projected_order": "verification/candidates/bc_projected_order.py",
    "projected_compact": "verification/candidates/bc_projected_compact.py",
    "projected_beam": "verification/candidates/bc_projected_beam.py",
    "projected_seed16": "verification/candidates/bc_projected_seed16.py",
}
BASELINE_SHA256 = "03bb9ce3bd5da99299a55d47122b38ceb2bef04aba37d998b80e0ad8de4ffa09"
SEEDS = (20261105, 79463)


def _file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_digest(case):
    digest = hashlib.sha256()
    for array in (case.faces_a, case.faces_b, *(a for state in case.states for a in state)):
        digest.update(repr((array.shape, array.dtype.str)).encode("ascii"))
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _load(name, relative):
    module_name = "_bc_work_counter_" + name
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _count_update_query(module, indexes, state, record):
    original_closest = module._closest_pairs
    original_nodes = module._node_bounds
    counts = record["work"] = {
        "closest_pairs_calls": 0,
        "exact_face_pairs_submitted": 0,
        "seed_exact_face_pairs_submitted": None,
        "seed_upper_bound_m": None,
        "node_bounds_calls_including_seed": 0,
        "node_pairs_including_seed": 0,
    }

    def closest(a, b, ids_a, ids_b):
        if len(ids_a) != len(ids_b):
            raise AssertionError("Mismatched narrow-phase pair arrays")
        first = counts["closest_pairs_calls"] == 0
        counts["closest_pairs_calls"] += 1
        counts["exact_face_pairs_submitted"] += len(ids_a)
        result = original_closest(a, b, ids_a, ids_b)
        if first:
            counts["seed_exact_face_pairs_submitted"] = len(ids_a)
            value = float(result[0])
            counts["seed_upper_bound_m"] = value if np.isfinite(value) else str(value)
        return result

    def nodes(a, b, depth_a, depth_b, ids_a, ids_b):
        if len(ids_a) != len(ids_b):
            raise AssertionError("Mismatched node-pair arrays")
        counts["node_bounds_calls_including_seed"] += 1
        counts["node_pairs_including_seed"] += len(ids_a)
        return original_nodes(a, b, depth_a, depth_b, ids_a, ids_b)

    module._closest_pairs, module._node_bounds = closest, nodes
    try:
        indexes[0].update(state[0])
        indexes[1].update(state[1])
        result = module.surface_distance(*indexes)
        if not np.isfinite(result.distance_m):
            raise AssertionError("Frozen positive-distance grid returned a nonfinite distance")
        record["result"] = {
            "distance_m": float(result.distance_m),
            "triangle_a": int(result.triangle_a), "triangle_b": int(result.triangle_b),
            "point_a": list(map(float, result.point_a)),
            "point_b": list(map(float, result.point_b)),
        }
        counts["post_seed_exact_face_pairs_submitted"] = (
            counts["exact_face_pairs_submitted"] - counts["seed_exact_face_pairs_submitted"])
    finally:
        module._closest_pairs, module._node_bounds = original_closest, original_nodes
        record["wrappers_restored"] = (module._closest_pairs is original_closest
                                       and module._node_bounds is original_nodes)


def _summary(report):
    lines = [
        "BC structural work counts; no instrumented duration is a performance result.",
        "Pairs are narrow-phase submissions, not individual feature operations.",
        "Columns: A / projected_order / projected_compact / projected_beam / projected_seed16.",
        "seed | case | phase | submitted face pairs (ratio to A)",
    ]
    for case in report["cases"]:
        for phase in (0, 1):
            state = case["states"][phase]
            baseline = state["methods"].get("A", {}).get("work", {}).get("exact_face_pairs_submitted")
            values = []
            for name in SOURCES:
                work = state["methods"].get(name, {}).get("work", {})
                count = work.get("exact_face_pairs_submitted")
                values.append("missing" if count is None or not baseline else
                              f"{count} ({count / baseline:.4f}x)")
            lines.append(f"{case['seed']} | {case['case']} | {phase} | " + " / ".join(values))
    lines.extend((
        "Seed upper bounds, seed face counts, call counts, node counts and outputs are in raw JSON.",
        "Compact-kernel feature reductions can improve cost even when submitted pair counts are identical.",
        "Distance agreement here is a consistency check against frozen A, not independent quality acceptance.",
        "Status: " + report["status"],
    ))
    return "\n".join(lines) + "\n"


def _collect(report):
    hashes = report["source_sha256_before"]
    if hashes[SOURCES["A"]] != BASELINE_SHA256:
        raise AssertionError("Frozen A differs from the accepted implementation")
    modules = {name: _load(name, relative) for name, relative in SOURCES.items()}
    for seed in SEEDS:
        for cells in (8, 16):
            for offset in (.5, .05):
                fixture = _grid_case(cells, offset, seed)
                digest = _input_digest(fixture)
                case = {"seed": seed, "case": fixture.name, "face_counts": [len(fixture.faces_a), len(fixture.faces_b)],
                        "z_offset_m": offset, "input_sha256": digest,
                        "states": [{"phase": phase, "methods": {}} for phase in (0, 1)]}
                report["cases"].append(case)
                for name, module in modules.items():
                    indexes = (module.SurfaceIndex(fixture.states[0][0], fixture.faces_a),
                               module.SurfaceIndex(fixture.states[0][1], fixture.faces_b))
                    if _input_digest(fixture) != digest:
                        raise AssertionError(f"{name} mutated fixture input during construction")
                    for phase, state in enumerate(fixture.states):
                        record = case["states"][phase]["methods"][name] = {
                            "input_sha256_before": _input_digest(fixture),
                        }
                        if record["input_sha256_before"] != digest:
                            raise AssertionError("Input was changed before counted query")
                        _count_update_query(module, indexes, state, record)
                        record["input_sha256_after"] = _input_digest(fixture)
                        record["input_unchanged"] = record["input_sha256_after"] == digest
                        if not record["input_unchanged"]:
                            raise AssertionError(f"{name} mutated fixture input during update/query")
                        baseline = case["states"][phase]["methods"]["A"]["result"]["distance_m"]
                        difference = abs(record["result"]["distance_m"] - baseline)
                        tolerance = surface_tolerance(state[0], fixture.faces_a, state[1], fixture.faces_b)
                        record["distance_comparison_to_A"] = {
                            "absolute_delta_m": difference, "tolerance_m": tolerance,
                            "passed": difference <= tolerance,
                        }
                        if difference > tolerance:
                            raise AssertionError(f"{name} disagrees with A on {fixture.name} phase {phase}")
    report["source_sha256_after"] = {name: _file_digest(ROOT / name) for name in hashes}
    report["sources_unchanged"] = hashes == report["source_sha256_after"]
    if not report["sources_unchanged"]:
        raise AssertionError("Source changed during structural counting")
    report["status"] = "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New raw JSON path; existing files are not overwritten")
    parser.add_argument("--summary", type=Path, help="New text summary path; defaults to OUTPUT.with_suffix('.summary.txt')")
    args = parser.parse_args()
    summary_path = args.summary or args.output.with_suffix(".summary.txt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    sources = [*SOURCES.values(), "verification/benchmark_fast_bvh_clearance.py",
               "verification/test_bc_acceptance.py", Path(__file__).resolve().relative_to(ROOT).as_posix()]
    report = {
        "status": "running", "measurement": "untimed structural instrumentation",
        "command": [sys.executable, *sys.argv],
        "source_sha256_before": {name: _file_digest(ROOT / name) for name in sources},
        "count_semantics": {
            "exact_face_pairs_submitted": "Pairs passed to _closest_pairs; includes seed and any repeated faces; early zero exits and feature-level work are not separately counted.",
            "node_pairs_including_seed": "AABB node-pair evaluations inside _node_bounds, including initial seeding; excludes projection/refit work outside the helper.",
            "boundary": "Index built from phase 0; wrap complete update+query for phases 0 and 1; restore original functions after each query.",
            "distance_consistency": "Compare to frozen A with the existing geometry-scale tolerance; not a replacement for an independent oracle.",
            "latency": "No duration recorded or reported. Instrumentation is not a performance benchmark.",
        },
        "cases": [],
    }
    failed = False
    # Reserve new evidence files before execution and preserve partial records
    # if an assertion or candidate exception interrupts the diagnostic.
    with args.output.open("x", encoding="utf-8", newline="\n") as raw_stream, \
            summary_path.open("x", encoding="utf-8", newline="\n") as summary_stream:
        try:
            _collect(report)
        except BaseException:
            failed = True
            report["status"] = "failed"
            report["exception"] = traceback.format_exc()
        finally:
            json.dump(report, raw_stream, indent=2, allow_nan=False,
                      default=lambda value: value.item() if isinstance(value, np.generic) else value.tolist())
            raw_stream.write("\n")
            summary = _summary(report)
            summary_stream.write(summary)
            print(summary, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
