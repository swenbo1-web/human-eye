"""Check each sealed slot against independent geometry and saved frame evidence."""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
SLOTS = ("N1", "P1")
SOURCE_DOMAIN = "zero_based_object_local_current_evaluated_capture_triangle_rows"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def array_sha(array, dtype):
    return sha(np.ascontiguousarray(array, dtype=dtype).tobytes())


def compact_sha(value):
    return sha(json.dumps(value, separators=(",", ":")).encode())


def read(path):
    return json.loads(path.read_bytes())


def require(check, detail):
    if not check:
        raise ValueError(detail)


def bind_seal(seal_path):
    rows = read(seal_path)["answers"]
    require([row["slot"] for row in rows] == list(SLOTS), "missing or misordered paired seal")
    for row in rows:
        require(row.get("status"), f"missing final status for {row['slot']}")
        if row["path"] is None:
            require(row["sha256"] is None and row["bytes"] in (None, 0), "invalid missing final")
            continue
        path = Path(row["path"])
        require(path.is_file() and path.stat().st_size == row["bytes"], "sealed final missing or wrong size")
        require(len(row["sha256"]) == 64, "missing sealed final hash")
    return rows


def mesh_checks(mesh, expected, transform, scale):
    for field, dtype in (("vertices", "<f8"), ("triangles", "<i8"), ("triangle_polygons", "<i8")):
        value = np.asarray(mesh[field])
        require(list(value.shape) == expected[field]["shape"], f"{field} shape differs")
        require(array_sha(value, dtype) == expected[field]["sha256"], f"{field} order or values differ")
    polygons = mesh["polygons"]
    require(len(polygons) == expected["polygon_count"], "polygon count differs")
    require(compact_sha(polygons) == expected["polygon_rows_sha256"], "polygon rows differ")
    coords = np.asarray(mesh["vertices"], dtype=np.float64)
    world = (coords @ transform[:3, :3].T + transform[:3, 3]) * scale
    require(np.allclose(world, mesh["vertices_world_m"], rtol=0, atol=1e-12), "stored metric coordinates differ")
    return world, np.asarray(mesh["triangles"], dtype=np.int64), np.asarray(mesh["triangle_polygons"])


def geometry_truth(terminal, region, expected):
    source = terminal["source"]
    for key, value in (("asset_sha256", expected["asset_sha256"]), ("frame", expected["source_frame"]),
                       ("subframe", expected["source_subframe"]), ("scale_length", expected["unit_scale"]),
                       ("view_layer", expected["active_view_layer"]),
                       ("source_index_domain", SOURCE_DOMAIN)):
        require(source[key] == value, f"source {key} differs from the registered scene")
    require(terminal["source_face_offsets"] == expected["source_face_offsets"], "source offsets differ")
    objects = terminal["objects"]
    require([o["name"] for o in objects] == [o["name"] for o in expected["objects"]], "mesh order differs")
    geometries = []
    for obj, history in zip(objects, expected["objects"]):
        require(obj["visible_get"] is history["visible_get"], f"{obj['name']} display participation differs")
        require(obj["matrix_world"] == history["matrix_world"], f"{obj['name']} transform differs")
        require(obj["native_matrix_world"] == history["matrix_world"], f"{obj['name']} native transform differs")
        matrix = np.asarray(obj["matrix_world"])
        mesh_checks(obj["native"], history["native"], matrix, source["scale_length"])
        geometries.append(mesh_checks(obj["evaluated"], history["evaluated"], matrix, source["scale_length"]))

    target, reference = objects
    require(region["object"] == {"name": target["name"]} and region["reference"] == {"name": reference["name"]}
            and region["object_id"] == target["object_id"] and region["index_domain"] == SOURCE_DOMAIN,
            "selection operands or source namespace differ")
    region_ids = region["source_triangle_ids"]
    require(len(region_ids) == expected["region_triangle_count"], "selection count differs")
    require(compact_sha(region_ids) == expected["region_ids_compact_json_sha256"], "selection order or membership differs")
    target_world, target_triangles, target_polygons = geometries[0]
    cube_world, cube_triangles, cube_polygons = geometries[1]
    selected_triangles = target_triangles[region_ids]
    selected_vertex_ids = np.unique(selected_triangles)
    region_world = target_world[selected_vertex_ids]
    require(len(region_world) == expected["region_vertex_count"], "selection vertex count differs")

    low, high, faces = prove_cube(cube_world, cube_triangles)
    region_low, region_high = region_world.min(axis=0), region_world.max(axis=0)
    face_clearances = np.vstack((region_low - low, high - region_high))
    side, axis = np.unravel_index(np.argmin(face_clearances), face_clearances.shape)
    distance = float(face_clearances[side, axis])
    require(distance > 0, "strict interior premise failed")
    plane = (low, high)[side][axis]
    extrema = (region_low, region_high)[side][axis]
    vertex_ids = selected_vertex_ids[region_world[:, axis] == extrema]
    require(vertex_ids.tolist() == [expected["expected_source_vertex_id"]], "closest vertex differs")
    vertex = int(vertex_ids[0])
    source_point = target_world[vertex]
    reference_point = source_point.copy()
    reference_point[axis] = plane
    a_ids = np.asarray(region_ids)[np.any(selected_triangles == vertex, axis=1)].tolist()
    b_ids = []
    for face_id in faces[side, axis]:
        coords = cube_world[cube_triangles[face_id]]
        edges = (coords[1:] - coords[0]).T
        weights = np.linalg.lstsq(edges, reference_point - coords[0], rcond=None)[0]
        if np.min(weights) >= -1e-12 and np.sum(weights) <= 1 + 1e-12:
            b_ids.append(int(face_id))
    require(a_ids == expected["expected_source_triangle_ids"] and b_ids == expected["expected_reference_triangle_ids"],
            "source witness mapping differs")
    for key, value in (("distance_m", distance), ("source_point_world_m", source_point),
                       ("reference_point_world_m", reference_point)):
        require(np.allclose(value, expected[f"expected_{key}"], rtol=0, atol=1e-12), f"historical {key} differs")

    return {
        "source": source, "object_names": [o["name"] for o in objects],
        "object_ids": [o["object_id"] for o in objects], "display_object_mask": [o["visible_get"] for o in objects],
        "object_instance_ids": [o["instance_id"] for o in objects],
        "indexed_source_mapping_verified": True,
        "distance_m": distance, "source_point_world_m": source_point.tolist(),
        "reference_point_world_m": reference_point.tolist(), "source_vertex_id": vertex,
        "source_triangle_ids": a_ids, "reference_triangle_ids": b_ids,
        "source_polygon_ids": np.unique(target_polygons[a_ids]).tolist(),
        "reference_polygon_ids": np.unique(cube_polygons[b_ids]).tolist(),
        "source_triangle_count": len(region_ids), "source_vertex_count": len(region_world),
        "reference_triangle_count": len(cube_triangles),
        "cube_bounds_m": [low.tolist(), high.tolist()], "region_bounds_m": [region_low.tolist(), region_high.tolist()],
        "closed_axis_aligned_cube_surface_verified": True, "complete_selected_surface_strictly_inside_cube": True,
        "face_clearances_m_xyz_min_then_max": face_clearances.tolist(),
    }


def prove_cube(vertices, triangles):
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    require(len(vertices) == 8 and len(triangles) == 12 and np.all(high > low), "Cube box dimensions differ")
    corners = vertices == high
    require(np.all((vertices == low) | corners) and len(np.unique(corners, axis=0)) == 8, "Cube corner set is incomplete")
    faces = {}
    for side, bounds in enumerate((low, high)):
        for axis, bound in enumerate(bounds):
            ids = np.flatnonzero(np.all(vertices[triangles, axis] == bound, axis=1))
            require(len(ids) == 2, "Cube plane lacks two triangles")
            edges = Counter()
            for a, b, c in triangles[ids]:
                edges.update(tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a)))
            signature = Counter((count, int(np.count_nonzero(corners[a] != corners[b])))
                                for (a, b), count in edges.items())
            require(signature == {(1, 1): 4, (2, 2): 1}, "Cube plane is not covered by the expected two triangles")
            faces[side, axis] = ids
    require(sorted(int(i) for ids in faces.values() for i in ids) == list(range(12)), "Cube plane assignment overlaps")
    return low, high, faces


def captured_geometry_binding(frame, device, terminal, region, slot_dir):
    source_ref = frame["source_ref"]
    if frame["origin"] == "common_native":
        receipt = next((r for r in device["sources"] if r["source_ref"] == source_ref), None)
        require(receipt is not None and receipt["status"] == "complete" and not receipt["terminal"],
                "native frame source capture is absent")
        path = Path(receipt["path"]).resolve()
        require(path.is_relative_to(slot_dir.resolve()), "native frame source is outside the slot")
        raw = path.read_bytes()
        require(sha(raw) == receipt["sha256"], "native frame source hash differs")
        scene = json.loads(raw)
        require(scene["source"] == terminal["source"], "native frame and terminal Blender context differ")
        for raw_obj, final_obj in zip(scene["objects"], terminal["objects"], strict=True):
            require(all(raw_obj[key] == final_obj[key] for key in ("object_id", "instance_id", "matrix_world", "visible_get")),
                    "native frame object or display state differs from terminal source")
            final_mesh = final_obj["evaluated"]
            require(all(raw_obj[raw_key] == final_mesh[final_key] for raw_key, final_key in (
                ("vertices_local", "vertices"), ("vertices", "vertices_world_m"), ("triangles", "triangles"))),
                "native frame geometry differs from terminal source")
        return {"source_ref": source_ref, "source_capture_sha256": receipt["sha256"]}

    require(frame["origin"] == "product", "unknown frame origin")
    receipt = frame["full_result"]
    path = Path(receipt["path"]).resolve()
    require(path.is_relative_to(slot_dir.resolve()), "product source result is outside the slot")
    raw = path.read_bytes()
    require(sha(raw) == receipt["sha256"], "product source result hash differs")
    result = json.loads(raw)
    producer = next((f for f in result["frames"] if f["image_ref"] == frame["ref"]), None)
    require(producer == frame["producer"], "frame metadata differs from original product result")
    binding, region_ref = result["binding"], result["region_ref"]
    records = [{"host_id": o["object_id"], "instance_id": o["instance_id"],
                "vertices": o["evaluated"]["vertices_world_m"], "faces": o["evaluated"]["triangles"]}
               for o in terminal["objects"]]
    digest = sha(json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
    require(binding["capture_scope"] == "complete_scene_meshes" and binding["coordinate_frame"] == "world"
            and binding["unit"] == "m", "product measurement capture scope differs")
    require(binding["ordered_geometry_sha256"] == region_ref["ordered_geometry_sha256"] == digest,
            "product captured geometry differs from terminal source")
    require(region_ref["host_id"] == terminal["objects"][0]["object_id"]
            and region_ref["source_triangle_indices"] == sorted(region["source_triangle_ids"]),
            "product selection differs from registered source IDs")
    require(binding["image_scope"]["participation_mask"] == terminal["display_object_mask"], "product display scope differs")
    return {"source_ref": source_ref, "region_ref": region_ref["region_id"],
            "scene_revision": binding["scene_revision"], "capture_state": binding["capture_state"],
            "ordered_geometry_sha256": digest, "complete_result_sha256": receipt["sha256"]}


def frame_truth(frame, device, terminal, geometry, region, expected, slot_dir):
    require(frame["view_name"] == "SCENE", "saved frame is not SCENE")
    for key in ("view_matrix", "projection_matrix"):
        require(np.allclose(frame["pose"][key], expected["camera"][key], rtol=0, atol=1e-12), f"first-frame {key} differs")
    size = expected["camera"]["size_px"]
    require(frame["size_px"] == size, "first-frame resolution differs")
    require(frame["object_names"] == geometry["object_names"], "frame mesh order differs")
    require(frame["object_ids"] == geometry["object_ids"], "frame mesh identity differs")
    require(frame["object_instance_ids"] == geometry["object_instance_ids"], "frame mesh instances differ")
    require(frame["source_face_offsets"] == expected["source_face_offsets"], "frame source offsets differ")
    require(frame["display_object_mask"] == geometry["display_object_mask"], "frame participation differs")

    png = Path(frame["PNG"]).read_bytes()
    require(sha(png) == frame["PNG_sha256"], "PNG hash mismatch")
    npz = Path(frame["NPZ"])
    require(sha(npz.read_bytes()) == frame["NPZ_sha256"], "NPZ hash mismatch")
    with np.load(npz, allow_pickle=False) as arrays:
        tri, owners, depth, color = (arrays[key] for key in ("triangle_ids", "owners", "depth", "color"))
        require(arrays["face_patch_offsets"].tolist() == frame["source_face_offsets"], "NPZ source offsets differ")
        require(arrays["display_object_mask"].tolist() == frame["display_object_mask"], "NPZ display mask differs")
    shape = tuple(reversed(size))
    require(tri.shape == owners.shape == depth.shape == shape and color.shape == (*shape, 3), "buffer dimensions differ")
    require(tri.dtype == owners.dtype == np.dtype("int32") and depth.dtype == np.dtype("float64")
            and color.dtype == np.dtype("uint8"), "unexpected buffer encodings")
    with Image.open(io.BytesIO(png)) as image:
        require(image.format == "PNG" and list(image.size) == size, "PNG format or dimensions differ")
        require(np.array_equal(np.asarray(image.convert("RGB")), color), "PNG pixels differ from retained RGB")
    offsets = frame["source_face_offsets"]
    require(np.all((tri >= -1) & (tri < offsets[-1])), "triangle owners fall outside source namespace")
    fg = tri >= 0
    remapped_object = np.full(shape, -1, dtype=np.int32)
    remapped_object[fg] = np.searchsorted(offsets[1:], tri[fg], side="right")
    require(np.array_equal(remapped_object, owners), "triangle owner to object owner mapping disagrees")
    require(np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)) and np.all(depth[~fg] == np.inf), "depth/owner coverage differs")
    require(np.all(np.asarray(frame["display_object_mask"])[remapped_object[fg]]), "excluded mesh owns pixels")
    local_triangle = tri[fg] - np.asarray(offsets)[remapped_object[fg]]
    target_source = local_triangle[remapped_object[fg] == 0]
    selected = np.isin(target_source, region["source_triangle_ids"])
    sampled = np.unique(target_source[selected])
    counts = {"selected_pixels": int(selected.sum()), "sampled_source_triangles": len(sampled),
              "unsampled_source_triangles": len(region["source_triangle_ids"]) - len(sampled)}
    ids_sha = array_sha(tri, "<i4")
    objects_sha = array_sha(owners, "<i4")
    return {
        "frame_ref": frame["ref"], "frame_identity": frame["frame_identity"],
        "origin": frame["origin"], "capture": captured_geometry_binding(frame, device, terminal, region, slot_dir),
        "PNG_sha256": frame["PNG_sha256"], "NPZ_sha256": frame["NPZ_sha256"],
        "display_object_mask": frame["display_object_mask"], "size_px": size,
        "pixel_convention": expected["camera_pixel_convention"],
        "triangle_owner_sha256_le_i32": ids_sha, "object_owner_sha256_le_i32": objects_sha,
        "same_source_mapped_owners_as_prior_SCENE": (
            ids_sha == expected["prior_frame_global_triangle_owner_sha256_le_i32"]
            and objects_sha == expected["prior_frame_object_owner_sha256_le_i32"]),
        "counts": counts, "counts_match_prior_SCENE": counts == expected["expected_frame_counts"],
        "sampled_source_triangle_ids": sampled.tolist(),
    }


def verify_slot(slot_dir, region, expected):
    result = {"errors": {}}
    terminal_path = slot_dir / "TERMINAL_SOURCE.json"
    device_path = slot_dir / "DEVICE_EVIDENCE.json"
    try:
        terminal_bytes = terminal_path.read_bytes()
        terminal = json.loads(terminal_bytes)
        device = read(device_path)
        receipt = device["terminal_source"]
        terminal_sha = sha(terminal_bytes)
        require(receipt["status"] == "complete" and receipt["sha256"] == terminal_sha
                and receipt["worker"]["pid"] == terminal["source"]["pid"], "terminal source receipt differs")
        result["geometry"] = geometry_truth(terminal, region, expected)
        result["terminal_source_sha256"] = terminal_sha
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        result["errors"]["geometry"] = str(exc)
    try:
        require("geometry" in result, "verified fresh geometry is required to remap owners")
        require(device["asset_sha256"] == expected["asset_sha256"], "device asset hash differs")
        require(device["camera"]["pixel_convention"] == expected["camera_pixel_convention"], "pixel convention differs")
        require(device["frames"], "no saved SCENE frame")
        result["frames"] = []
        for frame in device["frames"]:
            try:
                result["frames"].append(frame_truth(frame, device, terminal, result["geometry"], region, expected, slot_dir))
            except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
                result["frames"].append({"frame_ref": frame.get("ref"), "error": str(exc)})
        first = result["frames"][0]
        require("error" not in first, first.get("error"))
        result["frame"] = first
        result["device_evidence_sha256"] = sha(device_path.read_bytes())
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        result["errors"]["frame"] = str(exc)
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seal", type=Path, required=True)
    cli.add_argument("--slots", type=Path, required=True)
    cli.add_argument("--region", type=Path, default=HERE.parent / "inputs/REGION.json")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()

    seals = bind_seal(args.seal)
    expected = read(HERE / "EXPECTED.json")
    region = read(args.region)
    slots = {}
    for row in seals:
        slot_dir = args.slots / row["slot"]
        checked = verify_slot(slot_dir, region, expected)
        if row["path"] is not None:
            sealed = Path(row["path"]).read_bytes()
            require(sha(sealed) == row["sha256"], "sealed answer hash mismatch")
            require(sealed == (slot_dir / "consumer/PUBLIC_FINAL.txt").read_bytes(), "sealed and original final differ")
        checked["sealed_answer"] = row
        slots[row["slot"]] = checked
    frames = [slot.get("frame") for slot in slots.values()]
    owners_equal = all(frames) and frames[0]["triangle_owner_sha256_le_i32"] == frames[1]["triangle_owner_sha256_le_i32"]
    result = {"schema": "m4-live-source-region-evidence-verification-v1",
              "seal_sha256": sha(args.seal.read_bytes()), "region_sha256": sha(args.region.read_bytes()),
              "expected_sha256": sha((HERE / "EXPECTED.json").read_bytes()),
              "slots": slots, "same_device_first_frame_source_owners": bool(owners_equal),
              "same_device_pair_eligible": bool(owners_equal and [f["origin"] for f in frames]
                  == ["common_native", "product"] and all(f["same_source_mapped_owners_as_prior_SCENE"] for f in frames))}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
