"""Replay offline input validation using saved M6 source and an explicit test box.

The box below is synthetic.  This validation establishes checker behavior and
provides no evidence about fresh Cube geometry or a running Blender process.
"""

from copy import deepcopy
import json
from pathlib import Path
import tempfile

import numpy as np

from source_oracle import (analyze, array_identity, axis_aligned_box_proof,
                           exhaustive_triangle_distance, file_identity, read_json)


BASE = Path(__file__).resolve().parent
REGION = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_real_data_001/private/ARM_REGION.json")
RAW = REGION.parent / "capture_02/raw_selected.json"
SAVED_EVALUATED = REGION.parent / "capture_02/evaluated_selected.json"


def fixture():
    raw, region = read_json(RAW), read_json(REGION)
    polygon_rows = [set() for _ in range(max(raw["polygon_ids_by_triangle"]) + 1)]
    for triangle, polygon in zip(raw["triangles"], raw["polygon_ids_by_triangle"]):
        polygon_rows[polygon].update(triangle)
    native = {"vertices": raw["vertices_object"], "vertices_world_m": raw["vertices_world"],
              "triangles": raw["triangles"], "triangle_polygons": raw["polygon_ids_by_triangle"],
              "polygons": [sorted(row) for row in polygon_rows]}
    cube_vertices = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                     [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]]
    cube_polygons = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
                     [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5]]
    cube_triangles = [[polygon[0], polygon[1], polygon[2]] for polygon in cube_polygons]
    cube_triangles += [[polygon[0], polygon[2], polygon[3]] for polygon in cube_polygons]
    cube = {"vertices": cube_vertices, "vertices_world_m": cube_vertices,
            "triangles": cube_triangles, "triangle_polygons": list(range(6)) * 2,
            "polygons": cube_polygons}
    return {"schema": "real-asset-source-v1", "state": "initial", "source_sha256": region["source_sha256"],
            "process_id": "offline-synthetic-reference-input-validation", "frame": 1, "subframe": 0,
            "unit_scale": 1.0, "unit_settings": {"system": "METRIC", "scale_length": 1, "length_unit": "METERS"},
            "objects": [{"name": region["object_name"], "instance_id": "fixture-target", "mesh_name": region["mesh_name"],
                         "matrix_world": raw["matrix_world"], "modifiers": [], "animation": {},
                         "display": {"fixture": True}, "native": native, "evaluated": deepcopy(native)},
                        {"name": "Cube", "instance_id": "fixture-box", "mesh_name": "synthetic-unit-box",
                         "matrix_world": np.eye(4).tolist(), "modifiers": [], "animation": {},
                         "display": {"fixture": True}, "native": cube, "evaluated": deepcopy(cube)}]}


def main():
    results = []
    original = fixture()
    with tempfile.TemporaryDirectory(prefix="saved_validation_", dir=BASE) as temporary:
        temporary = Path(temporary)
        for state in ("initial", "moved", "restored"):
            snapshot = deepcopy(original)
            snapshot["state"] = state
            target = snapshot["objects"][0]
            if state == "moved":
                target["matrix_world"][0][3] += 0.25
                for domain in ("native", "evaluated"):
                    target[domain]["vertices_world_m"] = (
                        np.asarray(target[domain]["vertices_world_m"]) + [0.25, 0, 0]).tolist()
                target["native"]["triangles"].reverse()
                target["native"]["triangle_polygons"].reverse()
                target["evaluated"]["triangles"] = [row[1:] + row[:1] for row in reversed(target["evaluated"]["triangles"])]
                target["evaluated"]["triangle_polygons"].reverse()
            input_path, output_path = temporary / f"{state}.json", temporary / f"{state}_oracle.json"
            input_path.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf8")
            report = analyze(input_path, REGION, output_path)
            assert report["status"] == "passed", report.get("failure")
            assert report["distance_oracle"]["distance_m"] == 0.3701171875
            assert report["distance_oracle"]["source_to_reference_unit_direction"] == [0, 0, 1]
            assert len(report["source_correspondence"]["triangle_mapping"]) == 748
            assert len(report["source_correspondence"]["vertex_mapping"]) == 410
            first = report["source_correspondence"]["triangle_mapping"][0]
            assert first["native_triangle_row"] == (
                53263 - first["historical_source_triangle_row"] if state == "moved"
                else first["historical_source_triangle_row"])
            results.append({"case": f"saved_source_{state}_synthetic_reference",
                            "status": report["status"], "distance_m": report["distance_oracle"]["distance_m"],
                            "elapsed_seconds": report["elapsed_seconds"],
                            "first_triangle_mapping": first,
                            "ordered_region_arrays": report["ordered_region_arrays"]})
        snapshot = deepcopy(original)
        # Keep a valid readback for the modified point to reach the source-identity check.
        snapshot["objects"][0]["native"]["vertices"][16873][0] += 0.001
        snapshot["objects"][0]["native"]["vertices_world_m"][16873][0] += 0.001
        input_path.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf8")
        report = analyze(input_path, REGION, output_path)
        assert report["status"] == "failed"
        assert "local coordinates differ" in report["failure"]["reason"]
        results.append({"case": "saved_source_coordinate_mutation_detected", "status": "passed",
                        "expected_failure": report["failure"]})
    # Exercise the independent exhaustive path against the analytic box result.
    region = read_json(REGION)
    cube = original["objects"][1]["evaluated"]
    vertices = np.asarray(region["vertices_world"], dtype=float)
    triangle_rows = np.asarray(region["triangles_local"], dtype=int)
    reference_vertices = np.asarray(cube["vertices"], dtype=float)
    reference_triangles = np.asarray(cube["triangles"], dtype=int)
    analytic = axis_aligned_box_proof(vertices, reference_vertices, reference_triangles)
    exhaustive = exhaustive_triangle_distance(vertices, triangle_rows, reference_vertices, reference_triangles)
    assert abs(analytic["distance_m"] - exhaustive["distance_m"]) < 1e-12
    results.append({"case": "all_8976_triangle_pairs_agree_with_box_certificate", "status": "passed",
                    "distance_m": exhaustive["distance_m"], "certificate": exhaustive["certificate"]})
    a = np.asarray([[0, 0, 0], [2, 0, 0], [0, 2, 0]], dtype=float)
    b = np.asarray([[0.5, -1, -1], [0.5, 3, -1], [0.5, 1, 1]], dtype=float)
    crossing = exhaustive_triangle_distance(a, np.asarray([[0, 1, 2]]), b, np.asarray([[0, 1, 2]]))
    assert crossing["distance_m"] == 0
    results.append({"case": "transverse_triangle_intersection", "status": "passed",
                    "distance_m": crossing["distance_m"], "certificate": crossing["certificate"]})
    output = {"status": "passed", "scope": "Saved historical character source and explicit synthetic box only",
              "fresh_Blender_source_evidence": False, "processes_started": 0,
              "inputs": [file_identity(path) for path in (REGION, RAW, SAVED_EVALUATED)],
              "implementation": file_identity(BASE / "source_oracle.py"), "cases": results}
    path = BASE / "SAVED_INPUT_VALIDATION.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": output["status"], "cases": len(results), "output": str(path)}))


if __name__ == "__main__":
    main()
