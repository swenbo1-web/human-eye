"""Account for binary64 world-coordinate multiply/add after actual affine truth.

This does not execute a product function or solve distances. It compares the
explicit arithmetic expression with exact Fraction arithmetic on frozen inputs.
"""
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "run_01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def endpoint(value, upper):
    result = float(value)
    if (F(result) < value if upper else F(result) > value):
        result = math.nextafter(result, math.inf if upper else -math.inf)
    return result


def main():
    started = time.perf_counter_ns()
    deadline = started + 10 * 10**9
    names = ["scene.blend", "SNAPSHOT.json", "TRUTH.json", "ORACLE.json"]
    raw = {name: (OUTPUT / name).read_bytes() for name in names}
    expected = {"scene.blend": "e123b5578dbb1629778a72d889509ff986328724b463a7db0fc8ea9d470b5630",
                "SNAPSHOT.json": "0aab174aa37e7e662234c7f0cdf7bb1fd1e0a747d597e891f2155b504ab11d5b"}
    assert all(sha(raw[name]) == digest for name, digest in expected.items())
    snapshot, truth = json.loads(raw["SNAPSHOT.json"]), json.loads(raw["TRUTH.json"])
    bounds, rows = {}, []
    for obj in snapshot["objects"]:
        matrix = obj["matrix_world"]
        errors = []
        for vertex in obj["vertices_local"]:
            exact = [(sum(F(matrix[row][column]) * F(vertex[column]) for column in range(3)) + F(matrix[row][3])) * F(snapshot["unit_scale_m"]) for row in range(3)]
            rounded = [(sum(matrix[row][column] * vertex[column] for column in range(3)) + matrix[row][3]) * snapshot["unit_scale_m"] for row in range(3)]
            errors.append(sum(abs(F(value) - ideal) for value, ideal in zip(rounded, exact)))
        bound = max(errors)
        bounds[obj["name"]] = bound
        rows.append({"name": obj["name"], "vertices_checked": len(errors),
            "max_L1_world_roundoff_m": str(bound), "outward_upper_m": endpoint(bound, True),
            "worst_vertex_index": errors.index(bound)})
    intervals = []
    for fact in truth["facts"]:
        if fact["relation"] == "separated":
            extra = bounds[truth["target_name"]] + bounds[fact["name"]]
            lower, upper = map(F, fact["distance_interval_fraction_m"])
            intervals.append({"name": fact["name"], "extra_roundoff_bound_m": str(extra),
                "captured_world_distance_interval_m": [endpoint(lower - extra, False), endpoint(upper + extra, True)]})
    assert time.perf_counter_ns() < deadline
    assert all((OUTPUT / name).read_bytes() == value for name, value in raw.items())
    result = {"schema": "T1-binary64-world-roundoff-v1", "passed": True,
        "input_hashes": {name: sha(value) for name, value in raw.items()}, "objects": rows,
        "separated_distance_intervals_with_binary64_world_roundoff": intervals,
        "source_script_sha256": sha(Path(__file__).read_bytes()), "python": sys.executable,
        "python_version": sys.version, "elapsed_ns": time.perf_counter_ns() - started,
        "original_deadline_ns": deadline, "product_calls": 0, "model_calls": 0,
        "expression": "(sum(matrix[r][c] * local[c] for c in range(3)) + matrix[r][3]) * unit_scale_m",
        "scope": "exact comparison for this recorded CPython and actual input floats; triangle barycentric correspondence extends per-vertex L1 bounds to surfaces; original affine truth is unchanged"}
    with (OUTPUT / "WORLD_ROUNDOFF.json").open("xb") as stream:
        stream.write((json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
    assert time.perf_counter_ns() < deadline
    print(json.dumps({"passed": True, "maximum_L1_roundoff_m": endpoint(max(bounds.values()), True)}))


if __name__ == "__main__":
    main()
