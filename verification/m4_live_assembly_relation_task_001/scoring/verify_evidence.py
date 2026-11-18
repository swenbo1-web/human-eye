"""Verify frozen assembly inputs and owned readbacks without the product solver."""

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import stat


HERE = Path(__file__).resolve().parent
HISTORICAL = HERE.parents[1] / "closed_solid_read_001" / "inputs"
ARM_LABELS = ("N1", "P1")
EXPECTED = json.loads((HERE / "EXPECTED.json").read_bytes())
EPSILON = EXPECTED["world_arithmetic_bound_m"]
NAMES = [EXPECTED["target"], *EXPECTED["candidate_order"]]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(scalar, vector):
    return tuple(scalar * value for value in vector)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    x, y, z = a
    u, v, w = b
    return (y * w - z * v, z * u - x * w, x * v - y * u)


def unit(vector):
    length = math.hypot(*vector)
    require(length > EPSILON, "degenerate direction")
    return scale(1.0 / length, vector)


def transform(point, matrix, unit_scale):
    return [(dot(row[:3], point) + row[3]) * unit_scale for row in matrix[:3]]


def segment_projection(point, a, b):
    edge = sub(b, a)
    t = max(0.0, min(1.0, dot(sub(point, a), edge) / dot(edge, edge)))
    return add(a, scale(t, edge))


def triangle_projection(point, triangle):
    a, b, c = triangle
    u, v, d = sub(b, a), sub(c, a), sub(point, a)
    uu, uv, vv = dot(u, u), dot(u, v), dot(v, v)
    du, dv = dot(d, u), dot(d, v)
    determinant = uu * vv - uv * uv
    s = (du * vv - dv * uv) / determinant
    t = (dv * uu - du * uv) / determinant
    if s >= 0.0 and t >= 0.0 and s + t <= 1.0:
        return add(a, add(scale(s, u), scale(t, v)))
    candidates = [segment_projection(point, start, end) for start, end in ((a, b), (b, c), (c, a))]
    return min(candidates, key=lambda candidate: math.dist(candidate, point))


def triangles(mesh):
    vertices = mesh["world_vertices"]
    return [[vertices[index] for index in face] for face in mesh["faces"]]


def surface_projection(point, mesh, triangle_index=None):
    faces = triangles(mesh)
    if triangle_index is not None:
        require(type(triangle_index) is int and 0 <= triangle_index < len(faces),
                "source triangle index outside the named object's zero-based rows")
        faces = [faces[triangle_index]]
    candidates = [triangle_projection(point, face) for face in faces]
    return min(candidates, key=lambda candidate: math.dist(point, candidate))


def check_closed_mesh(mesh):
    edges = Counter()
    for a, b, c in mesh["faces"]:
        points = mesh["world_vertices"]
        require(math.hypot(*cross(sub(points[b], points[a]), sub(points[c], points[a]))) > EPSILON,
                f"{mesh['name']}: degenerate triangle")
        edges.update(((a, b), (b, c), (c, a)))
    require(all(value == 1 and edges[b, a] == 1 for (a, b), value in edges.items()),
            f"{mesh['name']}: inconsistent closed-shell edge orientation")


def overlaps_aabb(mesh_a, mesh_b):
    for a, b in zip(zip(*mesh_a["world_vertices"]), zip(*mesh_b["world_vertices"])):
        if max(min(a), min(b)) > min(max(a), max(b)):
            return False
    return True


def half_step(printed):
    decimal = Decimal(printed)
    require(decimal.is_finite(), "nonfinite coordinate")
    return float(decimal), 0.5 * 10.0 ** decimal.as_tuple().exponent


def interval_contains(value, interval, uncertainty):
    low, high = interval
    return low - uncertainty - EPSILON <= value <= high + uncertainty + EPSILON


def gap_check(printed, truth_row):
    value, rounding = half_step(printed)
    interval = truth_row["distance_interval_m"]
    certified_error = abs(value - truth_row["minimum_gap_m"]) + truth_row["distance_error_bound_m"]
    decimal_places_ok = rounding <= 0.5e-6
    return {
        "printed": printed, "interval_m": interval, "rounding_bound_m": rounding,
        "certified_absolute_error_m": certified_error, "decimal_places_ok": decimal_places_ok,
        "pass": (decimal_places_ok and interval_contains(value, interval, rounding)
                 and certified_error <= EXPECTED["separated_answer_absolute_bound_m"]),
    }


def printed_point(values):
    require(len(values) == 3, "world point must have three coordinates")
    pairs = [half_step(value) for value in values]
    coordinates, half_steps = zip(*pairs)
    return coordinates, math.hypot(*half_steps), max(half_steps)


def closest_pair_check(a_printed, b_printed, a_mesh, b_mesh, truth_row, *, support=(None, None)):
    a, a_round, a_axis_bound = printed_point(a_printed)
    b, b_round, b_axis_bound = printed_point(b_printed)
    a_projected = surface_projection(a, a_mesh, support[0])
    b_projected = surface_projection(b, b_mesh, support[1])
    a_error, b_error = math.dist(a, a_projected), math.dist(b, b_projected)
    raw_distance = math.dist(a, b)
    surface_distance = math.dist(a_projected, b_projected)
    interval = truth_row["distance_interval_m"]
    flags = {
        "decimal_places_ok": max(a_axis_bound, b_axis_bound) <= 0.5e-6,
        "target_on_surface": a_error <= a_round + EPSILON,
        "candidate_on_surface": b_error <= b_round + EPSILON,
        "printed_separation_matches": interval_contains(raw_distance, interval, a_round + b_round),
        "surface_separation_matches": interval_contains(surface_distance, interval,
                                                        a_round + b_round + a_error + b_error),
    }
    return dict(flags, **{
        "pass": all(flags.values()), "printed": [a_printed, b_printed],
        "endpoint_rounding_m": [a_round, b_round], "support_triangles": support,
        "endpoint_surface_error_m": [a_error, b_error], "projected_endpoints_world_m": [a_projected, b_projected],
        "printed_separation_m": raw_distance, "projected_separation_m": surface_distance,
    })


def plane_clip(triangle, plane_point, plane_normal):
    signed = [dot(sub(vertex, plane_point), plane_normal) for vertex in triangle]
    require(min(signed) < -EPSILON and max(signed) > EPSILON, "triangle lacks strict transverse sidedness")
    points = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = signed[i], signed[j]
        if abs(a) <= EPSILON:
            points.append(triangle[i])
        if (a < -EPSILON and b > EPSILON) or (a > EPSILON and b < -EPSILON):
            points.append(add(triangle[i], scale(a / (a - b), sub(triangle[j], triangle[i]))))
    require(len(points) == 2, "plane clip did not produce a segment")
    return points


def crossing_check(a_mesh, b_mesh, a_index, b_index, localization=None):
    faces_a, faces_b = triangles(a_mesh), triangles(b_mesh)
    require(type(a_index) is int and 0 <= a_index < len(faces_a)
            and type(b_index) is int and 0 <= b_index < len(faces_b), "invalid crossing support triangle index")
    a, b = faces_a[a_index], faces_b[b_index]
    n_a = unit(cross(sub(a[1], a[0]), sub(a[2], a[0])))
    n_b = unit(cross(sub(b[1], b[0]), sub(b[2], b[0])))
    direction = unit(cross(n_a, n_b))
    a_clip = plane_clip(a, b[0], n_b)
    b_clip = plane_clip(b, a[0], n_a)
    a_interval, b_interval = [sorted(dot(vertex, direction) for vertex in clip) for clip in (a_clip, b_clip)]
    low, high = max(a_interval[0], b_interval[0]), min(a_interval[1], b_interval[1])
    require(high - low > EPSILON, "intersection of triangle interiors has no positive length")
    origin_offset = dot(a_clip[0], direction)
    segment = [add(a_clip[0], scale(endpoint - origin_offset, direction)) for endpoint in (low, high)]
    result = {"pass": True, "crossing_support_triangles": [a_index, b_index],
              "crossing_segment_world_m": segment, "crossing_segment_length_m": high - low}
    if localization is not None:
        point, rounding, _ = printed_point(localization)
        residual = math.dist(point, segment_projection(point, *segment))
        result.update(localization_printed=localization, localization_rounding_m=rounding,
                      localization_residual_m=residual)
        result["pass"] = residual <= rounding + EPSILON
    return result


def solid_angle(point, triangle):
    a, b, c = [sub(vertex, point) for vertex in triangle]
    la, lb, lc = [math.hypot(*vector) for vector in (a, b, c)]
    return 2 * math.atan2(dot(a, cross(b, c)), la * lb * lc + dot(a, b) * lc + dot(a, c) * lb + dot(b, c) * la)


def shared_interior_check(a_mesh, b_mesh, localization):
    point, rounding, _ = printed_point(localization)
    sites = []
    for mesh in (a_mesh, b_mesh):
        check_closed_mesh(mesh)
        clearance = math.dist(point, surface_projection(point, mesh))
        winding = math.fsum(solid_angle(point, face) for face in triangles(mesh)) / (4.0 * math.pi)
        sites.append({"object": mesh["name"], "clearance_m": clearance, "winding": winding,
                      "pass": clearance > rounding + EPSILON and abs(abs(winding) - 1.0) <= 1e-8})
    return {"pass": all(site["pass"] for site in sites), "point_printed": localization,
            "rounding_m": rounding, "shells": sites}


def frozen_inputs(inputs=HISTORICAL):
    expected_digests = EXPECTED["historical_inputs"]
    before = {name: sha256((inputs / name).read_bytes()) for name in expected_digests}
    require(before == expected_digests, "historical scene, snapshot or truth byte hash mismatch")
    truth_doc = read_json(inputs / "TRUTH.json")
    require(truth_doc["product_solver_calls"] == truth_doc["model_answers"] == 0,
            "historical truth depends on the product or a model answer")
    require(truth_doc["input_snapshot_sha256"] == before["author_mesh_snapshots.json"],
            "historical truth and snapshot hashes do not bind")
    snapshot = read_json(inputs / "author_mesh_snapshots.json")[EXPECTED["state"]]
    truth = truth_doc["states"][EXPECTED["state"]]
    require(snapshot["unit_scale_m"] == EXPECTED["world_unit_scale_m"]
            and truth_doc["geometry_arithmetic_bound_m"] == EPSILON
            and truth_doc["answer_distance_tolerance_m"] == EXPECTED["separated_answer_absolute_bound_m"],
            "frozen arithmetic allowances or units differ")
    objects = {mesh["name"]: mesh for mesh in snapshot["objects"]}
    require(len(objects) == len(snapshot["objects"]) == len(NAMES) and sorted(objects) == NAMES
            and truth["target"] == NAMES[0] and sorted(truth["probes"]) == NAMES[1:],
            "frozen operands differ")
    for name, mesh in objects.items():
        expected_count = EXPECTED["mesh_counts"][name]
        require([len(mesh["vertices_local"]), len(mesh["faces"])] == expected_count,
                f"{name}: frozen mesh count mismatch")
        reconstructed = [transform(point, mesh["matrix_world"], snapshot["unit_scale_m"])
                         for point in mesh["vertices_local"]]
        require(len(mesh["world_vertices"]) == len(reconstructed)
                and all(math.dist(a, b) <= EPSILON for a, b in zip(reconstructed, mesh["world_vertices"])),
                f"{name}: frozen world coordinates do not match the transform")
        check_closed_mesh(mesh)
    aabbs = [overlaps_aabb(objects[NAMES[0]], objects[name]) for name in NAMES[1:]]
    require(aabbs == EXPECTED["world_aabb_overlap"]
            and aabbs == [truth["probes"][name]["world_aabb_overlap"] for name in NAMES[1:]],
            "frozen input bounds differ")
    separated = {name: row["distance_interval_m"] for name, row in truth["probes"].items()
                 if row["relation"] == "separated"}
    nearest = EXPECTED["nearest_separated"]
    require(nearest == truth["nearest_separated_probe"]
            and all(interval[0] > separated[nearest][1] for name, interval in separated.items() if name != nearest),
            "frozen separated order is not certified")
    penetration = truth["probes"]["Object_03"]
    require(penetration["relation"] == "penetrating" and penetration["certified_witness"],
            "frozen shared-interior certificate missing")
    witness = shared_interior_check(objects[NAMES[0]], objects["Object_03"],
                                    [str(value) for value in penetration["shared_interior_point_world_m"]])
    require(witness["pass"], "frozen shared-interior witness did not recheck")
    summary = {"pass": True, "historical_asset_sha256": before["scene.blend"],
               "historical_truth_sha256": before["TRUTH.json"], "historical_snapshot_sha256": before["author_mesh_snapshots.json"],
               "world_aabb_overlap": aabbs, "separated_intervals_m": separated, "nearest_separated": nearest,
               "shared_interior_certificate": witness}
    return summary, truth, objects


def read_verified_assets(slot, meshes):
    terminal_path = slot / "TERMINAL_SOURCE.json"
    device_path = slot / "DEVICE_EVIDENCE.json"
    worker_path = slot / "native" / "WORKER_CLOSED.json"
    raw = terminal_path.read_bytes()
    terminal = json.loads(raw)
    device = read_json(device_path)
    receipt = device["terminal_source"]
    worker = read_json(worker_path)
    source = terminal["source"]
    slot_result_path = slot / "SLOT_RESULT.json"
    published = read_json(slot / "SLOT_PUBLICATION.json")
    slot_result = read_json(slot_result_path)
    require(terminal["schema"] == "m4-live-assembly-terminal-source-v1"
            and source["kind"] == "actual_owned_Blender_evaluated_mesh"
            and source["source_index_domain"] == "zero_based_object_local_current_evaluated_capture_triangle_rows",
            "terminal readback schema or provenance differs")
    require(device["schema"] == "m4-live-assembly-device-evidence-v1" and device["label"] == slot.name
            and receipt in device["sources"] and receipt == slot_result["terminal_source"]
            and slot_result["slot"] == published["slot"] == slot.name
            and published["result_sha256"] == sha256(slot_result_path.read_bytes())
            and Path(receipt["path"]).resolve() == terminal_path.resolve()
            and receipt["sha256"] == sha256(raw) and receipt["bytes"] == len(raw)
            and receipt["status"] == "complete" and receipt["terminal"] is True,
            "terminal receipt does not bind the saved bytes")
    worker_export = Path(receipt["worker_path"]).resolve()
    require(worker_export.is_relative_to(slot / "terminal_sources") and worker_export.read_bytes() == raw,
            "terminal copy differs from owned worker export")
    receipt_worker = receipt["worker"]
    parent = receipt["parent_read"]
    require(source["pid"] == receipt_worker["pid"] == worker["pid"]
            and terminal["started_ns"] == receipt_worker["started_ns"]
            and terminal["geometry_read_closed_ns"] == receipt_worker["geometry_read_closed_ns"]
            and parent["started_ns"] <= terminal["started_ns"] <= terminal["geometry_read_closed_ns"]
            <= receipt_worker["file_closed_ns"] <= parent["closed_ns"] <= worker["closed_ns"]
            <= worker["original_deadline_ns"] == slot_result["owned_deadline_ns"],
            "terminal readback timing or process binding invalid")
    require(receipt_worker["sha256"] == receipt["sha256"] and receipt_worker["bytes"] == receipt["bytes"],
            "worker receipt digest mismatch")
    asset_copy = Path(source["asset_copy"]).resolve()
    asset_hash = EXPECTED["historical_inputs"]["scene.blend"]
    require(asset_copy.is_relative_to(slot.resolve()) and asset_copy.suffix == ".blend"
            and asset_hash == device["asset_sha256"] == source["asset_sha256"] == sha256(asset_copy.read_bytes()),
            "owned asset copy does not match the initial asset")
    if os.name == "nt":
        require(asset_copy.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY,
                "owned asset copy is writable")
    require(source["scale_length"] == EXPECTED["world_unit_scale_m"]
            and isinstance(source["frame"], int)
            and isinstance(source["scene"], str) and source["scene"]
            and isinstance(source["view_layer"], str) and source["view_layer"]
            and math.isfinite(source["subframe"]),
            "terminal scene, frame, layer or metre scale invalid")
    final_state = worker["full_final_state"]
    guard_digest = sha256(json.dumps(final_state, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False).encode("ascii") + b"\n")
    require(guard_digest == worker["initial_geometry_fingerprint"] == worker["final_geometry_fingerprint"]
            and worker["full_initial_state"] == final_state and worker["scene_unchanged"] is True
            and worker["protected_files_unchanged"] is True
            and not worker["poisoned"] and not worker["prohibited_events"]
            and all(final_state[key] == source[key] for key in
                    ("asset_copy", "scene", "frame", "subframe", "view_layer", "view_layer_id", "scale_length")),
            "owned before/after scene guard differs")
    current = {mesh["name"]: mesh for mesh in terminal["objects"]}
    guarded_meshes = {mesh["name"]: mesh for mesh in final_state["objects"] if mesh["type"] == "MESH"}
    require(list(current) == list(guarded_meshes) == NAMES
            and len(current) == len(terminal["objects"]) == len(meshes),
            "current operand names or count differ")
    for name, reference in meshes.items():
        observed = current[name]
        evaluated = observed["evaluated"]
        require(evaluated["vertices"] == reference["vertices_local"]
                and evaluated["triangles"] == reference["faces"]
                and observed["matrix_world"] == reference["matrix_world"],
                f"{name}: current ordered local vertices, triangles or transform drifted")
        reconstructed = [transform(point, observed["matrix_world"], source["scale_length"])
                         for point in evaluated["vertices"]]
        require(len(reconstructed) == len(evaluated["vertices_world_m"]) == len(reference["world_vertices"])
                and all(max(math.dist(a, b), math.dist(a, c)) <= EPSILON
                        for a, b, c in zip(reconstructed, evaluated["vertices_world_m"], reference["world_vertices"])),
                f"{name}: current world coordinates differ")
        require(observed["object_id"] and observed["instance_id"], f"{name}: current identity missing")
        require(observed["instance_id"] == guarded_meshes[name]["instance_id"]
                and observed["native_matrix_world"] == guarded_meshes[name]["matrix_world"]
                and observed["native"]["vertices"] == guarded_meshes[name]["vertices"]
                and observed["native"]["polygons"] == guarded_meshes[name]["polygons"],
                f"{name}: terminal native geometry differs from the owner guard")
        digest_payload = {"matrix_world": observed["matrix_world"], "scale_length": source["scale_length"],
                          "evaluated": evaluated}
        mesh_digest = sha256((json.dumps(digest_payload, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        require(mesh_digest == observed["mesh_sha256"] == receipt["mesh_sha256"][name],
                f"{name}: current mesh digest mismatch")
    require(len({mesh["object_id"] for mesh in current.values()}) == len(meshes)
            and len({mesh["instance_id"] for mesh in current.values()}) == len(meshes),
            "current object or session instance identity aliases")
    require(receipt["evaluated_counts"]["vertices"] == 72 and receipt["evaluated_counts"]["triangles"] == 132,
            "current receipt mesh counts differ")
    identity = {name: {field: current[name][field] for field in ("object_id", "instance_id", "mesh_sha256")}
                for name in NAMES}
    return {
        "pass": True, "asset_copy": str(asset_copy), "asset_sha256": asset_hash,
        "terminal_sha256": sha256(raw), "device_receipt_file_sha256": sha256(device_path.read_bytes()),
        "worker_close_sha256": sha256(worker_path.read_bytes()), "pid": source["pid"],
        "source": {field: source[field] for field in ("scene", "frame", "subframe", "view_layer", "view_layer_id",
                                                      "scale_length", "source_index_domain")},
        "identity": identity, "scene_unchanged": True, "evaluated_counts": receipt["evaluated_counts"],
        "ordinary_source_ref": receipt.get("ordinary_source_ref"),
        "terminal_capture_interval_ns": [terminal["started_ns"], terminal["geometry_read_closed_ns"]],
        "full_window_deadline_ns": worker["original_deadline_ns"],
        "slot_result_sha256": published["result_sha256"],
    }


def verify_slots(runtime, meshes):
    outcomes = {}
    for label in ARM_LABELS:
        try:
            outcomes[label] = read_verified_assets(runtime / "slots" / label, meshes)
        except (OSError, ValueError, KeyError, TypeError) as error:
            outcomes[label] = {"pass": False, "error": str(error)}
    eligible = all(result["pass"] for result in outcomes.values())
    reasons = []
    if eligible:
        a, b = (outcomes[label] for label in ARM_LABELS)
        for key in ("scene", "frame", "subframe", "view_layer", "scale_length", "source_index_domain"):
            if a["source"][key] != b["source"][key]:
                reasons.append(f"terminal {key} differs")
        if a["pid"] == b["pid"]:
            reasons.append("owned PIDs coincide")
        if os.path.samefile(a["asset_copy"], b["asset_copy"]):
            reasons.append("owned copies refer to the same file")
    else:
        reasons.append("one or both slot terminal bindings failed")
    return outcomes, {"same_initial_asset_and_evaluated_geometry": eligible and not reasons, "reasons": reasons}


def verify_seals(seal_path):
    sealed_doc = read_json(seal_path)
    require(sealed_doc["replacement_consumers"] == 0, "sealed pair has replacement consumers")
    entries = {entry["slot"]: entry for entry in sealed_doc["answers"]}
    require(len(entries) == len(sealed_doc["answers"]) == len(ARM_LABELS)
            and tuple(entries) == ARM_LABELS, "original answer seal does not preserve both ordered slots")
    result = {}
    for label, entry in entries.items():
        expected = entry.get("sha256")
        if expected is None:
            require(entry.get("path") is None and entry.get("original_path") is None,
                    f"{label}: an answer path has no byte seal")
        else:
            answer = Path(entry["path"])
            original = Path(entry["original_path"])
            raw = answer.read_bytes()
            require(sha256(raw) == expected and raw == original.read_bytes() and len(raw) == entry["bytes"],
                    f"{label}: original answer seal does not match preserved bytes")
        result[label] = {key: entry.get(key) for key in ("path", "sha256", "bytes", "status")}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=HISTORICAL, help="frozen historical source directory")
    parser.add_argument("--runtime", type=Path, help="owned runtime root with terminal readback")
    parser.add_argument("--seals", type=Path, help="paired original answer seal; use after both arms are sealed")
    args = parser.parse_args()
    result, _, meshes = frozen_inputs(args.inputs)
    verdict = {"schema": "m4-live-assembly-evidence-verdict-v1", "frozen_inputs": result}
    success = True
    if args.runtime is not None:
        slots, binding = verify_slots(args.runtime, meshes)
        verdict.update(slots=slots, pair=binding)
        success = binding["same_initial_asset_and_evaluated_geometry"]
    if args.seals is not None:
        verdict["sealed_answers"] = verify_seals(args.seals)
        verdict["seal_sha256"] = sha256(args.seals.read_bytes())
    print(json.dumps(verdict, sort_keys=True, indent=2, allow_nan=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
