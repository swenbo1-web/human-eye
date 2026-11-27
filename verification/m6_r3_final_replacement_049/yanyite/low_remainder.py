"""Fixed internal 8356-remaining control, independent of ordinary live reads.

Only _Work initialization receives the inherited 1171292 synthetic debit.
This is a correctness/accounting observation, never a latency comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/yanyite")
INPUT = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/holdouts/inputs/Yanyite_low.json")
INPUT_SHA = "57bf59c7ddf2bc61451cf62c30e32db6a456ced6bed92adb69956f498f5236a7"
A_BINDING = Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/032/.human-eye/releases/9.7.2+k041hook032/admin/RUNTIME_BINDING.json")
A_SOURCE = "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d"
LIMIT, REMAINING, PREPAID = 1179648, 8356, 1171292


def pin(path):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def save(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(RAW.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as out:
        json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write("\n")
    return pin(path)


def run(binding_path, output, arm):
    output = Path(output).resolve()
    assert output.is_relative_to(RAW.resolve())
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "m6-049-yanyite-fixed-remainder-v1", "status": "failed", "arm": arm,
        "source": pin(__file__), "binding": pin(binding_path), "input": pin(INPUT),
        "scope": "Internal initializer debit only; ordinary production requests use their original fresh per-pair Work. No deadline/limit mutation or performance conclusion.",
        "fixed_limit": LIMIT, "fixed_remaining": REMAINING, "prepaid": PREPAID,
        "calls": {}, "Blender": 0, "MCP": 0, "errors": []}
    try:
        assert result["input"]["sha256"] == INPUT_SHA
        binding = json.loads(Path(binding_path).read_bytes())
        if arm == "A":
            assert binding["identity"]["source_sha256"] == A_SOURCE
        site = Path(binding["site_packages"])
        for row in binding["source_files"]:
            assert pin(site/row["path"])["sha256"] == row["sha256"]
        result["identity"] = binding["identity"]
        result["verified_sources"] = len(binding["source_files"])
        sys.path.insert(0, str(site))
        from human_eye_plugin import surface_proximity as kernel
        from human_eye_plugin.active_observation_images import _meshes_from_objects
        from human_eye_plugin.runtime_identity import runtime_identity
        assert Path(kernel.__file__).resolve() == (site/"human_eye_plugin/surface_proximity.py").resolve()
        assert runtime_identity(mode="live")["source_sha256"] == binding["identity"]["source_sha256"]
        assert kernel.MAX_WORK_UNITS == LIMIT and kernel.MAX_NARROW_PHASE_PAIRS == 16384
        case = json.loads(INPUT.read_bytes())
        result["kernel"] = pin(kernel.__file__)
        original = kernel._Work
        class WithPriorWork(original):
            def __init__(self, checkpoint, stats):
                super().__init__(checkpoint, stats)
                self.consume(PREPAID, "diagnostic_prior_work")
        for name, work in (("fresh", original), ("one_precharge", WithPriorWork)):
            objects = [(m["vertices_world"], m["faces"], (case["case_id"], side), m["name"])
                       for side in ("left", "right") for m in [case[side]]]
            left, right = _meshes_from_objects(objects)
            stats, checkpoints = {}, {}
            started, cpu = time.perf_counter_ns(), time.process_time_ns()
            deadline = time.monotonic()+30.0
            def checkpoint(stage):
                checkpoints.setdefault("first", stage)
                checkpoints["last"] = stage
                if time.monotonic() >= deadline:
                    raise TimeoutError(stage)
            kernel._Work = work
            try:
                measured = kernel.measure_surface_proximity(left, right, checkpoint,
                    diagnostics=stats, retain_witness_triangles=True, _prepared_holder={})
            finally:
                kernel._Work = original
            row = {"result": measured, "work": stats, "checkpoints": checkpoints,
                "request_deadline_s": deadline, "initializer_only_prepaid": PREPAID if name == "one_precharge" else 0,
                "wall_ns": time.perf_counter_ns()-started, "cpu_ns": time.process_time_ns()-cpu,
                "counts": {"left_faces": len(left.faces), "right_faces": len(right.faces)}}
            if not measured["measurement_valid"]:
                assert measured["distance_m"] is None and measured["point_a_world"] is None and measured["point_b_world"] is None
            assert stats["work_units"] <= LIMIT and stats["narrow_phase_pairs"] <= 16384
            result["calls"][name] = row
            save(output/(name+".json"), row)
        result["status"] = "observed"
    except BaseException:
        result["errors"].append(traceback.format_exc())
    ref = save(output/"RESULTS.json", result)
    print(json.dumps({"receipt": ref, "status": result["status"], "outcomes": {
        k: {"valid": v["result"]["measurement_valid"], "reason": v["result"].get("reason"),
            "work": v["work"]["work_units"], "narrow": v["work"]["narrow_phase_pairs"]}
        for k, v in result["calls"].items()}}), flush=True)
    return int(bool(result["errors"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, default=A_BINDING)
    parser.add_argument("--arm", choices=("A", "F"), default="A")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.binding, args.output, args.arm))
