"""Analyze the local native export and optionally freeze a spatial arm region."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def survey(vertices, selected, out):
    image = Image.new("RGB", (1260, 820), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 12), "Native vertex projections in world coordinates; red marks selected spatial region", fill="black")
    for panel, (a, b) in enumerate(((0, 2), (1, 2), (0, 1))):
        lower = vertices[:, [a, b]].min(axis=0)
        upper = vertices[:, [a, b]].max(axis=0)
        scale = min(370 / max(upper[0] - lower[0], 1e-12), 700 / max(upper[1] - lower[1], 1e-12))
        pixels = (vertices[:, [a, b]] - lower) * scale
        pixels[:, 0] += 25 + panel * 420
        pixels[:, 1] = 760 - pixels[:, 1]
        draw.text((25 + panel * 420, 40), f"{'XYZ'[a]} / {'XYZ'[b]} world m", fill="black")
        draw.text((25 + panel * 420, 780), f"min {lower.round(4).tolist()} max {upper.round(4).tolist()}", fill="black")
        for x, y in pixels:
            draw.point((int(x), int(y)), fill="#64778b")
        for x, y in pixels[selected]:
            draw.ellipse((int(x) - 1, int(y) - 1, int(x) + 1, int(y) + 1), fill="#cb382e")
    image.save(out / "private" / "SURVEY.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bounds", type=float, nargs=6, metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"))
    parser.add_argument("--evidence-root", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.evidence_root.resolve()
    started = time.perf_counter()
    manifest = json.loads((out / "SOURCE_MANIFEST.json").read_bytes())
    capture = next(row for row in reversed(manifest["captures"]) if row["selected_object"] is not None and row["status"] == "collected")
    private = out / "private" / capture["capture_id"]
    native = json.loads((private / "native_inventory.json").read_bytes())
    raw = json.loads((private / "raw_selected.json").read_bytes())
    evaluated = json.loads((private / "evaluated_selected.json").read_bytes())
    vertices = np.asarray(raw["vertices_world"], dtype=np.float64)
    local = np.asarray(raw["vertices_object"], dtype=np.float64)
    triangles = np.asarray(raw["triangles"], dtype=np.int64)
    assert vertices.shape == local.shape == (len(raw["vertex_ids"]), 3)
    assert np.isfinite(vertices).all() and len(set(raw["vertex_ids"])) == len(vertices)
    assert triangles.min() >= 0 and triangles.max() < len(vertices)
    same = raw["vertices_object"] == evaluated["vertices_object"] and raw["triangles"] == evaluated["triangles"]
    selected = np.zeros(len(vertices), dtype=bool)
    if args.bounds:
        lower = np.array(args.bounds[::2])
        upper = np.array(args.bounds[1::2])
        assert np.all(lower < upper)
        selected = np.all((vertices >= lower) & (vertices <= upper), axis=1)
    survey(vertices, selected, out)
    print(json.dumps({"world_min": vertices.min(axis=0).tolist(), "world_max": vertices.max(axis=0).tolist(),
                      "selected_vertices": int(selected.sum()), "survey": str(out / 'private/SURVEY.png')}))
    if not args.bounds:
        return
    ids = np.flatnonzero(selected)
    assert len(ids) >= 3
    selected_triangle_ids = np.flatnonzero(selected[triangles].all(axis=1))
    crossing = np.any(selected[triangles], axis=1) & ~np.all(selected[triangles], axis=1)
    lookup = np.full(len(vertices), -1, dtype=np.int64)
    lookup[ids] = np.arange(len(ids))
    patch_triangles = lookup[triangles[selected_triangle_ids]]
    assert len(patch_triangles) > 0 and np.min(patch_triangles) >= 0
    edges = Counter(tuple(sorted((int(a), int(b)))) for triangle in patch_triangles
                    for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])))
    patch = {"schema": "native-mesh-aabb-patch-v1", "source_sha256": manifest["source"]["sha256"],
             "object_name": raw["object_name"], "mesh_name": raw["mesh_name"], "unit": "m",
             "source_vertex_ids": ids.tolist(), "vertices_world": vertices[ids].tolist(),
             "vertices_object": local[ids].tolist(), "source_triangle_ids": selected_triangle_ids.tolist(),
             "source_polygon_ids": [raw["polygon_ids_by_triangle"][index] for index in selected_triangle_ids],
             "triangles_local": patch_triangles.tolist(), "matrix_world": raw["matrix_world"],
             "selection": {"kind": "world_axis_aligned_box", "bounds_xyz_minmax": args.bounds,
                           "basis": "Assistant visual inspection of native XZ/YZ/XY vertex projections; positive-Y forearm-side spatial sample",
                           "semantic_label_status": "provisional_spatial_region_requires_author_confirmation"},
             "bone_chain": None, "weights": None, "sections": None, "paired_reference": None,
             "supervision_label": None}
    patch_path = out / "private" / "ARM_REGION.json"
    patch_path.write_text(json.dumps(patch, separators=(",", ":"), allow_nan=False), encoding="utf8")
    mesh = next(obj for obj in native["objects"] if obj["name"] == raw["object_name"])
    check_rows = [
        {"name": "source remains dispatch identity", "passed": manifest["source"]["sha256"] == "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"},
        {"name": "full native indices finite and valid", "passed": True},
        {"name": "raw/evaluated arrays exactly equal and modifier-free", "passed": same and mesh["modifiers"] == []},
        {"name": "patch coordinates preserve original source indices", "passed": np.array_equal(vertices[ids], np.asarray(patch["vertices_world"]))},
        {"name": "patch triangles preserve original source connectivity", "passed": np.array_equal(ids[patch_triangles], triangles[selected_triangle_ids])},
        {"name": "automatic scripts disabled", "passed": native["autoexec_enabled"] is False},
        {"name": "no source or copy saved by collector", "passed": all(row["source_after"] == manifest["source"] for row in manifest["captures"])}]
    assert all(row["passed"] for row in check_rows)
    inventory = {"cycle_id": "M6-REAL-DATA-001", "source_sha256": manifest["source"]["sha256"],
                 "native": native, "mesh_world_bounds_m": [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
                 "source_objects": len(native["objects"]), "source_mesh_objects": sum(obj["type"] == "MESH" for obj in native["objects"]),
                 "arm_region": {"selection": patch["selection"], "vertices": len(ids), "triangles": len(patch_triangles),
                                "crossing_source_triangles_excluded": int(crossing.sum()),
                                "one_incident_triangle_edges": sum(count == 1 for count in edges.values()),
                                "more_than_two_incident_triangle_edges": sum(count > 2 for count in edges.values()),
                                "private_patch": record(patch_path), "private_survey": record(out / "private/SURVEY.png")},
                 "missing": ["armature", "bone rest/pose matrices", "skin weights", "distinct neutral or accepted correction reference",
                             "explicit anatomical region and closed sections", "repair task and allowed actions", "pose/corrective labels"],
                 "available_supervision": {"accepted_correction_pairs": 0, "rigged_pose_pairs": 0, "temporal_sequences": 0,
                                           "shape_key_targets": 0, "independent_real_assets": 1},
                 "raw_evaluated_correspondence": native["exported_object"]}
    manifest["private_cache_bytes"] = sum(path.stat().st_size for path in (out / "private").rglob("*") if path.is_file())
    results = {"cycle_id": "M6-REAL-DATA-001", "status": "passed_input_and_supervision_audit",
               "native_acquisition": {"status": "collected", "source_identity_verified": True, "object_exported": raw["object_name"]},
               "product_adapter": {"status": "ineligible_from_native_evidence", "actual_runtime_adapter_calls": 0,
                                   "failed_structural_requirement": "single_armature_required", "actual_armature_modifiers": 0,
                                   "other_missing": ["selected bone chain", "normalized skin weights", "closed section selection", "paired bone rest/pose"],
                                   "scope": "Code-domain precheck, not an adapter execution receipt"},
               "correction_task": {"status": "missing_task_and_supervision", "geometric_control": "not_run_missing_rig_and_task",
                                   "independent_shape_deformation_check": "not_run_missing_pose_or_corrective_pair",
                                   "observable": ["static positions and triangles", "connected components", "spatial region", "raw/evaluated equality"],
                                   "native_topology_components_are_fault_labels": False},
               "checks": check_rows, "model_candidates": [],
               "costs": {"native_processes": len(manifest["captures"]), "copies_created": manifest["copies_created"],
                         "native_process_wall_s": [row["full_process_wall_s"] for row in manifest["captures"]],
                         "native_process_total_wall_s": sum(row["full_process_wall_s"] for row in manifest["captures"]),
                         "collector_wall_s": [json.loads((out / 'private' / row['capture_id'] / 'native_inventory.json').read_bytes())["collector_wall_s"] for row in manifest["captures"]],
                         "export_file_bytes": sum(item["bytes"] for row in manifest["captures"] for item in row["export_files"]),
                         "private_cache_bytes": manifest["private_cache_bytes"],
                         "full_mesh_coordinate_numpy_bytes": vertices.nbytes + local.nbytes,
                         "full_mesh_triangle_numpy_bytes": triangles.nbytes,
                         "selected_patch_json_bytes": patch_path.stat().st_size,
                         "native_peak_working_set_bytes": [json.loads((out / 'private' / row['capture_id'] / 'native_inventory.json').read_bytes())["memory_at_end"]["peak_working_set_bytes"] for row in manifest["captures"]],
                         "analysis_wall_s_before_final_json_publication": time.perf_counter() - started,
                         "whole_agent_task_wall_s": None, "controller_manifest_publication_cost": "not_separately_measured",
                         "formal_performance_comparisons": 0, "model_calls": 0, "model_tokens": None, "model_fees": None},
               "not_run": ["adapter runtime request", "geometric correction", "FK/LBS deformation control", "training/search",
                           "model consumer", "formal benchmark", "asset editing or save", "paid API"],
               "next_step": "Obtain one accepted same-index target for the source-bound forearm-side region plus the task, allowed actions and protection constraints. Resolve the intended output before model selection."}
    for name, value in (("INVENTORY.json", inventory), ("RESULTS.json", results), ("SOURCE_MANIFEST.json", manifest)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": results["status"], "checks": len(check_rows), "vertices": len(ids), "triangles": len(patch_triangles)}))


if __name__ == "__main__":
    main()
