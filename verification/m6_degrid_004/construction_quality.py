"""Compare the two fresh constructed states to their fixed saved predecessors."""

import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from evaluate import packet
from quality import CORE, geometry_quality
import facts_api
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    root = HERE / "private/construction_quality"
    root.mkdir(parents=True, exist_ok=True)
    output = root / ("attempt_" + str(len(list(root.glob("attempt_*"))) + 1).zfill(3))
    output.mkdir(exist_ok=False)
    result = dict(status="running", started_unix_s=time.time(), actual_Blender_calls=0,
                  actual_Pro_calls=0, checks={}, comparisons=[])
    write(output / "ATTEMPT.json", result)
    try:
        hidden = HERE / "private/construction"
        case = HERE / "private/cases/repair"
        initial = packet(case / "initial.npz")
        spec = read(case / "spec.json")
        F = initial["F_source_ids"]
        for name, before_path, after_path, before_scene, after_scene in (
            ("normal", hidden / "base_normal.npz", hidden / "normal_readback.npz",
             hidden / "base_scene.json", hidden / "normal_scene.json"),
            ("damaged", hidden / "old_damaged.npz", case / "actual_initial_readback.npz",
             hidden / "old_damaged_scene.json", case / "baseline_scene.json"),
        ):
            before, after = packet(before_path), packet(after_path)
            domains = dict(F_source_ids=F, I_ids=F,
                           protected_ids=np.setdiff1d(initial["source_ids"], F))
            evaluated = geometry_quality(before, after, domains, spec, read(before_scene), read(after_scene))
            old_keys, old_unique = CORE._triangle_keys(before["faces"], before["triangle_polygon_ids"])
            new_keys, new_unique = CORE._triangle_keys(after["faces"], after["triangle_polygon_ids"])
            removed = sorted(set(old_keys) - set(new_keys))
            added = sorted(set(new_keys) - set(old_keys))
            evaluated["derived_tessellation"] = dict(before_keys_unique=old_unique, after_keys_unique=new_unique,
                removed_triangle_keys=removed, added_triangle_keys=added,
                affected_native_polygon_ids=sorted({key[0] for key in removed + added}),
                role="Derived triangles are recomputed on saved coordinates. Native polygon preservation is checked independently.")
            evaluated["comparison"] = dict(state=name, before=identity(before_path), after=identity(after_path),
                construction_allowed_points=len(F), exact_pair_scope="all pairs incident to fixed 410 points or actually changed vertices")
            write(output / (name.upper() + ".json"), evaluated)
            result["comparisons"].append(dict(state=name, status=evaluated["status"],
                checks=evaluated["checks"], displacement=evaluated["displacement"],
                geometry=evaluated["geometry"], derived_tessellation=dict(removed_triangle_keys=len(removed),
                    added_triangle_keys=len(added), affected_native_polygon_ids=evaluated["derived_tessellation"]["affected_native_polygon_ids"]),
                report=identity(output / (name.upper() + ".json"))))
        normal = packet(hidden / "normal_readback.npz")
        target = packet(HERE / "private/scoring/target.npz")
        checks = result["checks"]
        checks["target_is_new_normal_actual_world"] = np.array_equal(target["clean_vertices_world"], normal["vertices_world"])
        checks["target_initial_is_new_damaged_actual_world"] = np.array_equal(target["initial_vertices_world"], initial["vertices_world"])
        checks["normal_damaged_native_topology_preserved"] = all(np.array_equal(normal[key], initial[key])
            for key in ("source_ids", "matrix_world", "poly_offsets", "poly_vertices"))
        support = target["support_ids"]
        unchanged = np.setdiff1d(initial["source_ids"], support)
        checks["normal_to_damaged_native_change_within_old_47"] = normal["vertices_local"][unchanged].tobytes() == initial["vertices_local"][unchanged].tobytes()
        result["normal_to_damaged"] = dict(intended_support_points=len(support),
            actually_changed_native_source_ids=np.flatnonzero(np.any(normal["vertices_local"].view(np.uint32)
                != initial["vertices_local"].view(np.uint32), axis=1)).tolist(),
            actual_derived_triangle_arrays_identical=bool(np.array_equal(normal["faces"], initial["faces"])),
            maximum_support_displacement_m=float(np.linalg.norm(initial["vertices_world"][support]
                - normal["vertices_world"][support], axis=1).max()))
        statuses = [row["status"] for row in result["comparisons"]]
        result["status"] = "fail" if not all(checks.values()) or "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    except BaseException as error:
        result.update(status="error", error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
    result.update(wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
                  resources=facts_api.FOCUS.process_resources(),
                  sources=[identity(HERE / name) for name in ("construction_quality.py", "quality.py", "evaluate.py")])
    write(output / "ATTEMPT.json", result)
    attempts = [read(path) for path in sorted(root.glob("attempt_*/ATTEMPT.json"))]
    write("CONSTRUCTION_GEOMETRY_QA.json", dict(status=result["status"], attempts=attempts,
        wall_s_total=sum(row["wall_s"] for row in attempts), cpu_s_total=sum(row["cpu_s"] for row in attempts),
        actual_Blender_calls=0, actual_Pro_calls=0))
    print(json.dumps(dict(status=result["status"], comparisons=[dict(state=row["state"], status=row["status"])
        for row in result["comparisons"]], checks=result["checks"])), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
