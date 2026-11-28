"""Exercise task-region geometry using only synthetic current source rows."""

import argparse
import json
import math
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product_path", type=Path)
    path = parser.parse_args().product_path.resolve(strict=True)
    sys.path.insert(0, str(path))
    from human_eye_plugin import observation_focus

    implementation = Path(observation_focus.__file__).resolve(strict=True)
    if not implementation.is_relative_to(path):
        raise RuntimeError(f"wrong implementation: {implementation}")

    def plane(x):
        return [[x, -1., -1.], [x, 1., -1.], [x, 1., 1.], [x, -1., 1.]]

    captured = {"meshes": [
        {"vertices": plane(-2.) + plane(2.),
         "faces": [[0, 3, 1], [1, 3, 2], [4, 5, 7], [5, 6, 7]]},
        {"vertices": plane(-3.), "faces": [[0, 1, 2], [0, 2, 3]]},
        {"vertices": plane(3.), "faces": [[0, 1, 2], [0, 2, 3]]},
    ]}
    binding = {"objects": [
        {"host_id": "target", "object_name": "target", "instance_id": "target.1"},
        {"host_id": "left", "object_name": "left", "instance_id": "left.1"},
        {"host_id": "right", "object_name": "right", "instance_id": "right.1"},
    ]}
    checks = []
    stages = []

    def box(low, high, zmax=1.):
        return {"min": [low, -1., -1.], "max": [high, 1., zmax]}

    def select(name, bounds=None, *, selector="id"):
        query = {"reference": {selector: name}}
        if bounds is not None:
            query["world_box_m"] = bounds
        return observation_focus.select_task_region(captured, binding, 0, query, stages.append)

    def check(label, actual, expected):
        if actual != expected:
            raise AssertionError(f"{label}: {actual!r} != {expected!r}")
        checks.append({"check": label, "actual": actual})

    def group_and_primary(selected):
        return [selected["source_triangle_indices"], selected["primary_source_triangle_index"]]

    left, right = select("left"), select("right", selector="name")
    check("reference_only_left", group_and_primary(left), [[0, 1], 0])
    check("reference_only_right", group_and_primary(right), [[2, 3], 2])
    check("reference_only_left_orientation", left["front_normal_world"], [-1., 0., 0.])
    check("reference_only_right_orientation", right["front_normal_world"], [1., 0., 0.])
    check("reference_instance", right["reference"]["instance_id"], "right.1")
    check("reference_only_effect", right["selection_policy"]["reference_effect"], "group_and_primary")

    left_all, right_all = select("left", box(-2., 2.)), select("right", box(-2., 2.))
    check("boxed_left", group_and_primary(left_all), [[0, 1, 2, 3], 0])
    check("boxed_right", group_and_primary(right_all), [[0, 1, 2, 3], 2])
    check("boxed_effect", right_all["selection_policy"]["reference_effect"], "primary_only")
    check("included_closed_boundary", group_and_primary(select("right", box(-2., -2.))), [[0, 1], 0])
    check("outside_by_one_binary64_step", group_and_primary(select(
        "right", box(-2.5, math.nextafter(-2., -math.inf)))), [[], None])
    check("one_outside_vertex_prevents_membership", group_and_primary(select(
        "right", box(-2., -2., math.nextafter(1., 0.)))), [[], None])
    empty = select("left", box(-1., 1.))
    check("empty_box_reason", empty["empty_reason"], "no_source_triangles_in_task_world_box")

    captured["meshes"][0]["faces"] = [[0, 0, 1], [1, 3, 2], [4, 5, 7], [5, 6, 7]]
    check("degenerate_cannot_be_primary", group_and_primary(select("left", box(-2., -2.))), [[0, 1], 1])
    check("degenerate_cannot_nominate", group_and_primary(select("left")), [[1], 1])

    try:
        select("target")
    except ValueError as exc:
        check("distinct_reference", str(exc), "focus_task_region_distinct_reference_required")
    else:
        raise AssertionError("same target and reference was accepted")

    check("source_selection_deadline_checkpoints", sorted(set(stages)), sorted([
        "before_task_region_selection", "after_task_region_candidates",
        "focus_task_region_reference_ranking", "after_task_region_selection",
    ]))
    print(json.dumps({"implementation": str(implementation), "passed": len(checks), "checks": checks},
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

