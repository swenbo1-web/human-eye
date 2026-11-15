"""Technical QA of saved readback packets without private restoration targets."""

import argparse
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from quality import geometry_quality, status, validate_packet
import numpy as np


def packet(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def evaluate_packets(before_path, after_path, initial_path, spec_path, *, before_state_path=None,
                     after_state_path=None, deadline=None, check_intersections=True):
    started, cpu = time.perf_counter(), time.process_time()
    incoming, current, initial = packet(before_path), packet(after_path), packet(initial_path)
    spec = json.loads(Path(spec_path).read_bytes())
    before_scene = json.loads(Path(before_state_path).read_bytes()) if before_state_path else None
    after_scene = json.loads(Path(after_state_path).read_bytes()) if after_state_path else None
    result = geometry_quality(initial, current, initial, spec, before_scene, after_scene,
                              deadline=deadline, check_intersections=check_intersections)
    validate_packet(incoming)
    if incoming["vertices"].shape != current["vertices"].shape:
        raise ValueError("operation_readback_coordinate_shape_mismatch")
    operation_maximum = float(np.linalg.norm(current["vertices"] - incoming["vertices"], axis=1).max())
    operation_budget = float(spec["max_operation_displacement_m"])
    if not np.isfinite(operation_budget) or operation_budget <= 0:
        raise ValueError("positive_finite_operation_budget_required")
    result["checks"]["operation_displacement_budget"] = bool(operation_maximum <= operation_budget + spec["world_preservation_tol"])
    result["status"] = status(result["checks"])
    result["displacement"].update(input_to_after_maximum_world=operation_maximum, maximum_operation_allowed_world=operation_budget)
    result["measurement_scope"] = "Saved current geometry compared to immutable damaged initial geometry with operation displacement from incoming readback."
    result["unit"] = spec.get("unit", "m")
    result["wall_s"], result["cpu_s"] = time.perf_counter() - started, time.process_time() - cpu
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ("before", "after", "initial", "spec", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--before-state", type=Path)
    parser.add_argument("--after-state", type=Path)
    args = parser.parse_args()
    result = evaluate_packets(args.before, args.after, args.initial, args.spec,
                             before_state_path=args.before_state, after_state_path=args.after_state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps(dict(status=result["status"], checks=result["checks"])))


if __name__ == "__main__":
    main()
