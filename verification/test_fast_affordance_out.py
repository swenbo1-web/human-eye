"""Independent AO public reader and author acceptance scoring.

The reader uses a published row schema and actual PNGs. Source evidence is
passed only to the scoring functions, after the public answer is recovered.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
from time import perf_counter_ns
import unittest


_METRICS = (
    "max_principal_stretch",
    "min_principal_stretch",
    "max_area_strain",
    "max_normal_angle_deg",
    "max_centroid_displacement",
    "score",
)
_VIEW_FIELDS = {
    "matrix_world_blender": ("rna", "matrix_world"),
    "camera_type": ("rna", "type"),
    "ortho_scale_blender": ("rna", "ortho_scale"),
    "clip_start_blender": ("rna", "clip_start"),
    "clip_end_blender": ("rna", "clip_end"),
    "shift_x": ("rna", "shift_x"),
    "shift_y": ("rna", "shift_y"),
    "projection_blender": ("rna", "projection"),
    "gpu_view_m": ("gpu", "view"),
    "gpu_projection_m": ("gpu", "projection"),
    "gpu_view_projection_m": ("gpu", "view_projection"),
}
_VISUAL_FIELDS = ("global_view", "local_view")
_CHILDREN = {
    "package": (("observations", "observation", True), ("outcome", "outcome", False)),
    "observation": (
        ("objects", "object", True), ("clearance", "clearance", False),
        ("deformation", "deformation", False), ("image", "image", False),
    ),
    "clearance": (("witness_a", "witness", False), ("witness_b", "witness", False)),
    "deformation": (("faces", "face", True),),
    "image": (
        ("section", "section", False), ("global_view", "view", False), ("local_view", "view", False),
    ),
    "outcome": (("goal", "goal", False), ("command", "command", False)),
}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _constant(token):
    raise ValueError(f"Non-finite JSON number {token}")


def _row(record, name, columns, compact):
    if record is None:
        return None
    keys = columns[name]
    if compact:
        _require(isinstance(record, list) and len(record) == len(keys), f"Wrong {name} column count")
        record = dict(zip(keys, record))
    else:
        _require(isinstance(record, dict) and record.keys() == set(keys), f"Wrong {name} fields")
    for key, child, many in _CHILDREN.get(name, ()):
        value = record[key]
        if many:
            _require(isinstance(value, list), f"{key} must be a row array")
            record[key] = [_row(item, child, columns, compact) for item in value]
        else:
            record[key] = _row(value, child, columns, compact)
    return record


def decode_public(payload, schema):
    """Decode one arm using only its public bytes and the shared schema."""
    wire = json.loads(payload, parse_constant=_constant)
    compact = isinstance(wire, list)
    package = _row(wire, "package", schema["columns"], compact)
    arm = "candidate" if compact else "baseline"
    _require(package["version"] == schema["versions"][arm], "Unsupported AO version")
    _require(package["length_unit"] == "m", "Expected world length unit m")
    ids = package["object_ids"]
    _require(isinstance(ids, list) and all(isinstance(key, str) and key for key in ids)
             and len(set(ids)) == len(ids), "Invalid stable object table")
    return package


def _id(index, ids):
    _require(type(index) is int and 0 <= index < len(ids), f"Invalid object index {index}")
    return ids[index]


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _xyz(point):
    return isinstance(point, list) and len(point) == 3 and all(map(_finite, point))


def _clearance(row, ids, observed):
    pair = [_id(index, ids) for index in row["target_object_indices"]]
    _require(len(pair) == 2 and len(set(pair)) == 2 and all(key in observed for key in pair),
             "Clearance targets are absent from this observation")
    witnesses = [row["witness_a"], row["witness_b"]]
    distance = row["distance_m"]
    if row["status"] == "empty_surface":
        _require(distance is None and witnesses == [None, None], "Empty surface has no witnesses")
    else:
        _require(_finite(distance) and distance >= 0, "Invalid surface distance")
        status = "positive_gap" if distance > 0 else "zero_distance"
        _require(row["status"] == status, "Clearance status does not match distance")
        for witness in witnesses:
            face = witness["original_face_id"]
            _require(type(face) is int and face >= 0 and _xyz(witness["point_m"]),
                     "Invalid raw triangle row or world witness")
        _require(math.isclose(math.dist(*(w["point_m"] for w in witnesses)), distance,
                              rel_tol=1e-9, abs_tol=1e-12),
                 "Witness separation disagrees with distance")
    return pair


def _deformation(row, ids, observed):
    object_id = _id(row["object_index"], ids)
    _require(object_id in observed, "TD object absent from this observation")
    sample_frames = row["sample_frames"]
    _require(all(type(frame) is int for frame in [row["reference_frame"], *sample_frames])
             and row["position_frame"] in [row["reference_frame"], *sample_frames],
             "Invalid TD reference/sample/position frames")
    _require(row["position_kind"] == "face_centroid", "Invalid TD position kind")
    reduced = row["reduced_face_count"]
    _require(type(reduced) is int and reduced >= 0, "Invalid TD reduction scope")
    rows = row["faces"]
    face_ids = [face["original_face_id"] for face in rows]
    top = row["top_face_ids"]
    _require(all(type(face) is int and 0 <= face < reduced for face in face_ids)
             and len(face_ids) == len(set(face_ids)) and face_ids[:len(top)] == top,
             "TD original triangle rows or Top-K association are invalid")
    for face in rows:
        _require(_xyz(face["position_m"]) and all(face[name] is None or _finite(face[name]) for name in _METRICS),
                 "TD row has an invalid metric or position")
    return object_id


def _project(view, point):
    matrix = view["gpu_view_projection_m"]
    world = (*point, 1.0)
    x, y, z, w = (sum(a * b for a, b in zip(row, world)) for row in matrix)
    offset_x, offset_y, width, height = view["viewport"]
    return [
        offset_x + (1 + x / w) * width / 2 - .5,
        offset_y + (1 - y / w) * height / 2 - .5,
        z / w,
    ]


def _view(view, offset_x, scale):
    import numpy as np

    _require(view["viewport"] == [offset_x, 0, 512, 512] and view["camera_type"] == "ORTHO",
             "Invalid orthographic panel layout")
    for key in ("matrix_world_blender", "projection_blender", "gpu_view_m",
                "gpu_projection_m", "gpu_view_projection_m"):
        array = np.asarray(view[key], dtype=np.float64)
        _require(array.shape == (4, 4) and np.isfinite(array).all(), f"Invalid camera matrix {key}")
    _require(0 < view["clip_start_blender"] < view["clip_end_blender"]
             and view["ortho_scale_blender"] > 0
             and _finite(view["shift_x"]) and _finite(view["shift_y"]),
             "Invalid orthographic scale, clip, or lens shift")
    world = np.array(view["matrix_world_blender"], dtype=np.float64)
    world[:3, 3] *= scale
    projection = np.array(view["projection_blender"], dtype=np.float64)
    projection[:, :3] /= scale
    _require(np.allclose(np.linalg.inv(world), view["gpu_view_m"], rtol=1e-6, atol=1e-7),
             "RNA world matrix and meter-space GPU view disagree")
    _require(np.allclose(projection, view["gpu_projection_m"], rtol=1e-6, atol=1e-7),
             "RNA and GPU orthographic projection disagree")
    _require(np.allclose(projection @ np.linalg.inv(world), view["gpu_view_projection_m"],
                         rtol=1e-6, atol=1e-7),
             "Camera does not reproduce the actual GPU view-projection")


def _matches(pixels, point, color, radius=3):
    import numpy as np

    x, y = (round(v) for v in point[:2])
    x0, x1 = max(0, x - radius), min(pixels.shape[1], x + radius + 1)
    y0, y1 = max(0, y - radius), min(pixels.shape[0], y + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return 0
    patch = pixels[y0:y1, x0:x1].astype(np.int16)
    return int(np.count_nonzero(np.all(np.abs(patch - color) <= 1, axis=2)))


def _image(row, obs, ids, observed, clearance_pair, public_dir, task):
    import numpy as np
    from PIL import Image

    scale = row["meters_per_blender_unit"]
    _require(_finite(scale) and scale > 0, "Invalid image meter scale")
    dimensions = (row["width_px"], row["height_px"])
    _require(dimensions == (1024, 512), "Invalid image dimensions")
    target_ids = [_id(index, ids) for index in row["target_object_indices"]]
    mesh_ids = [_id(index, ids) for index in row["mesh_object_indices"]]
    _require(clearance_pair == target_ids and len(set(mesh_ids)) == len(mesh_ids)
             and set(mesh_ids) == observed.keys() and set(target_ids) <= observed.keys(),
             "Image geometry and BC targets must belong to this observation")
    for offset, name in zip((0, 512), _VISUAL_FIELDS):
        _view(row[name], offset, scale)

    clearance = obs["clearance"]
    points = [clearance[name]["point_m"] for name in ("witness_a", "witness_b")]
    section = row["section"]
    if row["mode"] == "NATURAL":
        _require(section is None, "NATURAL image has a section plane")
    else:
        _require(row["mode"] == "SECTION" and section["kept_side"] == "<=0", "Invalid section mode or side")
        normal = section["normal"]
        midpoint = [(a + b) / 2 for a, b in zip(*points)]
        _require(_xyz(normal) and _xyz(section["point_m"]) and abs(math.hypot(*normal) - 1) < 1e-6
                 and math.dist(midpoint, section["point_m"]) < 1e-7, "Section plane misses the witness midpoint")

    relative = Path(row["path"])
    _require(not relative.is_absolute() and ".." not in relative.parts and relative.suffix == ".png",
             "Invalid public PNG path")
    raw = (public_dir / relative).read_bytes()
    with Image.open(BytesIO(raw)) as image:
        _require(image.format == "PNG" and image.size == dimensions, "Public file is not the declared PNG")
        image.verify()
    with Image.open(BytesIO(raw)) as image:
        pixels = np.asarray(image.convert("RGB"))
    for x in (0, 512):
        body = pixels[44:465, x:x+512]
        _require(bool(np.any(body != body[0, 0])), "Blank public image panel")

    local_points = [_project(row["local_view"], point) for point in points]
    for x, y, z in local_points:
        _require(511.5 <= x < 1023.5 and 43.5 <= y < 464.5 and abs(z) <= 1,
                 "Witness projects outside the public local image")
    colors = [pixels[y, 19].astype(np.int16) for y in (482, 497)]
    support = [_matches(pixels, point, color) for point, color in zip(local_points, colors)]
    if clearance["status"] == "positive_gap":
        _require(all(value >= 2 for value in support), "Published local pixels do not show the two witness surfaces")

    _require(all(_xyz(observed[key]["center_m"]) for key in mesh_ids), "Image object position missing")
    context_points = {
        key: _project(row["global_view"], observed[key]["center_m"]) for key in mesh_ids
    }
    result = {
        "observation_id": obs["observation_id"],
        "frame_id": obs["frame_id"],
        "target_ids": target_ids,
        "mesh_ids": mesh_ids,
        "path": row["path"],
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
        "dimensions": list(dimensions),
        "mode": row["mode"],
        "section": section,
        "global_view": row["global_view"],
        "local_view": row["local_view"],
        "local_witness_pixels": local_points,
        "local_witness_support": support,
        "context_object_pixels": context_points,
    }
    if task["id"] == "16":
        # The frozen F6 shell occludes the witnesses in context. The two
        # color swatches are public HUD marks for the actual local surfaces.
        global_witnesses = [_project(row["global_view"], point) for point in points]
        _require(row["mode"] == "SECTION"
                 and not any(_matches(pixels, point, color) for point, color in zip(global_witnesses, colors)),
                 "Frozen F6 context must show the original occluded assembly")
    if task["id"] == "17":
        target, decoy = task["target_id"], task["decoy_id"]
        _require(target in target_ids and decoy in context_points and decoy not in target_ids,
                 "Task's target and decoy do not identify distinct public mesh objects")
        target_pixel, decoy_pixel = context_points[target], context_points[decoy]
        _require(math.dist(target_pixel[:2], decoy_pixel[:2]) > 8, "Target/decoy positions are not separated")
        color = colors[target_ids.index(target)]
        target_support = _matches(pixels, target_pixel, color, radius=4)
        decoy_support = _matches(pixels, decoy_pixel, color, radius=4)
        _require(min(target_support, decoy_support) >= 2, "Public image does not show the same-color target and decoy")
        result["target_and_decoy"] = {
            target: {"pixel": target_pixel, "same_color_pixels": target_support},
            decoy: {"pixel": decoy_pixel, "same_color_pixels": decoy_support},
        }
    return result


def _outcome(row, ids, observations):
    before, after = (observations[row[key]] for key in ("before_observation_id", "after_observation_id"))
    _require(before is not after and isinstance(row["action_id"], str) and row["action_id"],
             "Outcome observation or action identity is invalid")
    goal, command = row["goal"], row["command"]
    moving = _id(goal["moving_object_index"], ids)
    reference = _id(goal["reference_object_index"], ids)
    _require(moving != reference and _finite(goal["target_distance_m"]) and goal["target_distance_m"] >= 0
             and _finite(goal["tolerance_m"]) and goal["tolerance_m"] >= 0, "Outcome goal is invalid")
    for observation, key in ((before, "distance_before_m"), (after, "distance_after_m")):
        clearance = observation["clearance"]
        _require(set(_id(index, ids) for index in clearance["target_object_indices"]) == {moving, reference}
                 and row[key] == clearance["distance_m"], "Outcome distance or targets disagree with observation")
    distance_before, distance_after = row["distance_before_m"], row["distance_after_m"]
    delta = None if None in (distance_before, distance_after) else distance_after - distance_before
    _require(row["measured_delta_m"] == delta, "Outcome measured delta does not match readback")
    reached = distance_after is not None and abs(distance_after - goal["target_distance_m"]) <= goal["tolerance_m"]
    _require(row["goal_reached"] is reached, "Outcome goal status does not match actual readback")
    _require(row["predicted_delta_m"] is None or _finite(row["predicted_delta_m"]), "Invalid predicted delta")
    if command["kind"] == "translate":
        _require(_xyz(command["delta_world_m"]) and command["key_name"] is None
                 and command["target_value"] is None and _xyz(row["control_before"]) and _xyz(row["control_after"]),
                 "Invalid world-translation command or readback")
        actual = [after - before for before, after in zip(row["control_before"], row["control_after"])]
        scale = max(1, *map(abs, row["control_before"]), *map(abs, row["control_after"]))
        _require(math.dist(actual, command["delta_world_m"]) <= 4 * 2**-23 * scale,
                 "Actual world translation disagrees with the explicit command")
    else:
        _require(command["kind"] == "set_shape_key" and command["delta_world_m"] is None
                 and isinstance(command["key_name"], str) and bool(command["key_name"])
                 and _finite(command["target_value"]) and _finite(row["control_before"]) and _finite(row["control_after"]),
                 "Invalid Shape Key command or readback")
        _require(math.isclose(row["control_after"], command["target_value"], rel_tol=1e-7, abs_tol=1e-8),
                 "Actual Shape Key value disagrees with the explicit command")
    return {"moving_id": moving, "reference_id": reference}


def consume_public(payload, schema, public_dir, task):
    """Recover the requested answer with the public task, wire, schema and PNGs."""
    package = decode_public(payload, schema)
    ids = package["object_ids"]
    observations = {}
    visuals = []
    for obs in package["observations"]:
        observation_id = obs["observation_id"]
        _require(isinstance(observation_id, str) and observation_id and observation_id not in observations
                 and type(obs["frame_id"]) is int, "Invalid or repeated observation identity")
        observed = {_id(obj["object_index"], ids): obj for obj in obs["objects"]}
        _require(len(observed) == len(obs["objects"])
                 and all(type(obj["topology_generation"]) is int and obj["topology_generation"] >= 0
                         for obj in observed.values()), "Invalid observation topology binding")
        clearance_pair = None
        if obs["clearance"] is not None:
            clearance_pair = _clearance(obs["clearance"], ids, observed)
        if obs["deformation"] is not None:
            _deformation(obs["deformation"], ids, observed)
        if obs["image"] is not None:
            _require(clearance_pair is not None and obs["clearance"]["status"] != "empty_surface",
                     "Image cannot present an empty surface as a witness")
            visuals.append(_image(obs["image"], obs, ids, observed, clearance_pair, public_dir, task))
        observations[observation_id] = obs
    _require(bool(observations), "No observation to consume")

    selected = next(iter(observations.values()))
    if "requested_frame" in task:
        matches = [obs for obs in observations.values() if obs["frame_id"] == task["requested_frame"]]
        _require(len(matches) == 1, "Cannot resolve the public requested frame")
        selected = matches[0]
    outcome = package["outcome"]
    targets = _outcome(outcome, ids, observations) if outcome is not None else None
    image = next((visual for visual in visuals if visual["observation_id"] == selected["observation_id"]), None)
    clearance, deformation = selected["clearance"], selected["deformation"]
    return {
        "package": package,
        "images": visuals,
        "answer": {
            "observation_id": selected["observation_id"],
            "frame_id": selected["frame_id"],
            "objects": {ids[obj["object_index"]]: obj for obj in selected["objects"]},
            "clearance_target_ids": None if clearance is None else [ids[i] for i in clearance["target_object_indices"]],
            "clearance": clearance,
            "deformation_object_id": None if deformation is None else ids[deformation["object_index"]],
            "deformation": deformation,
            "image": image,
            "action_targets": targets,
            "outcome": outcome,
        },
    }


def _exact(actual, expected, name):
    """Check binary float round trips and recursive field/row equality."""
    if isinstance(expected, dict):
        _require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"{name} field set differs")
        for key, value in expected.items():
            _exact(actual[key], value, f"{name}.{key}")
    elif isinstance(expected, (list, tuple)):
        _require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), f"{name} row length differs")
        for index, value in enumerate(expected):
            _exact(actual[index], value, f"{name}[{index}]")
    elif isinstance(expected, float):
        _require(_finite(actual) and struct.pack(">d", actual) == struct.pack(">d", expected),
                 f"{name} did not round trip")
    else:
        _require(type(actual) is type(expected) and actual == expected, f"{name} value differs")


def _on_face(point, face):
    import numpy as np

    triangle = np.asarray(face)
    p = np.asarray(point)
    a, b, c = triangle
    tolerance = 1e-9 * max(1, np.abs(triangle).max())
    edges = np.column_stack((b - a, c - a))
    bary, _, rank, _ = np.linalg.lstsq(edges, p - a, rcond=None)
    if rank == 2:
        return bool(np.linalg.norm(a + edges @ bary - p) <= tolerance
                    and bary.min() >= -1e-8 and bary.sum() <= 1 + 1e-8)
    for start, stop in ((a, b), (b, c), (c, a)):
        segment = stop - start
        size_sq = segment @ segment
        t = np.clip((p - start) @ segment / size_sq, 0, 1) if size_sq else 0
        if np.linalg.norm(start + t * segment - p) <= tolerance:
            return True
    return False


def _score_clearance(row, ids, expected):
    distance = expected["distance_m"]
    status = "empty_surface" if distance is None else ("positive_gap" if distance > 0 else "zero_distance")
    _exact(row["status"], status, "clearance.status")
    _exact([_id(index, ids) for index in row["target_object_indices"]], expected["target_ids"], "clearance.targets")
    _exact(row["distance_m"], distance, "clearance.distance_m")
    if distance is None:
        return
    _require(math.isclose(distance, expected["analytic_distance_m"], rel_tol=0,
                          abs_tol=expected["analytic_tol_m"]), "Surface distance disagrees with analytic case")
    for suffix in ("a", "b"):
        witness = row[f"witness_{suffix}"]
        face = witness["original_face_id"]
        point = witness["point_m"]
        _exact(face, expected[f"triangle_{suffix}"], f"clearance.{suffix}.face")
        _exact(point, expected[f"point_{suffix}"], f"clearance.{suffix}.point")
        _require(_on_face(point, expected[f"triangles_{suffix}"][face]),
                 f"Witness {suffix} is outside its original triangle row")


def _score_deformation(row, ids, expected):
    actual = {key: value for key, value in row.items() if key not in {"object_index", "faces"}}
    actual["object_id"] = _id(row["object_index"], ids)
    metadata = {key: value for key, value in expected.items() if key != "faces" and not key.startswith("analytic_")}
    _exact(actual, metadata, "deformation")
    _require(len(row["faces"]) == len(expected["faces"]), "TD selected row count differs")
    for face, source in zip(row["faces"], expected["faces"]):
        _exact({key: value for key, value in face.items() if key != "position_m"},
               {key: value for key, value in source.items() if key != "position_m"}, "deformation.face")
        # The fixture computes the independent three-point mean in a
        # different floating-point order from AO's edge-based centroid.
        _require(math.dist(face["position_m"], source["position_m"]) <= 1e-14, "TD centroid differs")
    faces = {str(face["original_face_id"]): face for face in row["faces"]}
    if "analytic_top_face_ids" in expected:
        _exact(row["top_face_ids"], expected["analytic_top_face_ids"], "deformation.analytic_top_face_ids")
    for face_id, point in expected.get("analytic_positions_m", {}).items():
        _require(math.dist(faces[face_id]["position_m"], point) <= 1e-14, "TD analytic centroid differs")
    for face_id, metrics in expected["analytic_metrics"].items():
        for metric, value in metrics.items():
            received = faces[face_id][metric]
            if value is None:
                _require(received is None, f"{metric} on {face_id} must be undefined")
            else:
                _require(_finite(received) and math.isclose(received, value, rel_tol=1e-7, abs_tol=1e-8),
                         f"{metric} on {face_id} differs from the analytic value")


def _score_image(row, obs, ids, expected, received):
    meta = expected["metadata"]
    _exact(row["path"], expected["path"], "image.path")
    _exact(received["sha256"], expected["png_sha256"], "image.PNG hash")
    _exact(obs["frame_id"], meta["frame_id"], "image.frame")
    _exact(row["meters_per_blender_unit"], meta["meters_per_blender_unit"], "image.scale")
    _exact(row["mode"], meta["mode"], "image.mode")
    _exact(row["section"], meta["section"], "image.section")
    for public, native in (("target_object_indices", "target_ids"), ("mesh_object_indices", "mesh_ids")):
        _exact([_id(index, ids) for index in row[public]], meta[native], f"image.{public}")
    for name, panel in zip(_VISUAL_FIELDS, ("global", "local")):
        native = meta["views"][panel]
        expected_view = {
            "viewport": native["viewport"],
            **{key: native[group][field] for key, (group, field) in _VIEW_FIELDS.items()},
        }
        _exact(row[name], expected_view, f"image.{name}")


def _score_facts(consumed, task, oracle):
    package = consumed["package"]
    ids = package["object_ids"]
    observations = package["observations"]
    visuals = {image["observation_id"]: image for image in consumed["images"]}
    _require(len(observations) == len(oracle["observations"]), "Observation count differs")
    _require(set(ids) == {key for expected in oracle["observations"] for key in expected["objects"]},
             "Stable object table differs")
    for obs, expected in zip(observations, oracle["observations"]):
        for field in ("observation_id", "frame_id"):
            _exact(obs[field], expected[field], field)
        objects = {
            _id(obj["object_index"], ids): {key: value for key, value in obj.items() if key != "object_index"}
            for obj in obs["objects"]
        }
        _exact(objects, expected["objects"], "observation.objects")
        for kind in ("clearance", "deformation", "image"):
            _require((obs[kind] is None) == (expected[kind] is None), f"Missing or invented {kind} row")
        if obs["clearance"] is not None:
            _score_clearance(obs["clearance"], ids, expected["clearance"])
        if obs["deformation"] is not None:
            _score_deformation(obs["deformation"], ids, expected["deformation"])
        if obs["image"] is not None:
            _score_image(obs["image"], obs, ids, expected["image"], visuals[obs["observation_id"]])

    actual_outcome = deepcopy(package["outcome"])
    if actual_outcome is not None:
        goal = actual_outcome["goal"]
        goal["moving_id"] = _id(goal.pop("moving_object_index"), ids)
        goal["reference_id"] = _id(goal.pop("reference_object_index"), ids)
    _exact(actual_outcome, oracle["outcome"], "outcome")

    case = task["id"]
    answer = consumed["answer"]
    if case == "15":
        _require(answer["image"]["mode"] == "NATURAL", "F1/V1 natural mode missing")
    elif case == "18":
        _require(len(visuals) == 2 and len({image["sha256"] for image in visuals.values()}) == 2,
                 "Frame comparison requires distinct actual PNGs")
        a, b = observations
        _require(a["image"]["local_view"] != b["image"]["local_view"] and a["clearance"] != b["clearance"]
                 and answer["frame_id"] == task["requested_frame"], "Frame views/witnesses are not distinct or selected")
    elif case in ("19", "20"):
        _require(actual_outcome["goal_reached"] and actual_outcome["measured_delta_m"] is not None,
                 "Real action outcome did not reach its fixed goal")


def score_public(payload, schema, public_dir, task, oracle):
    """Score one arm. Parsing/image timing ends before private scoring starts."""
    start = perf_counter_ns()
    try:
        consumed = consume_public(payload, schema, public_dir, task)
        consume_ns = perf_counter_ns() - start
        _score_facts(consumed, task, oracle)
    except (ValueError, KeyError, TypeError, IndexError, OSError, ArithmeticError) as error:
        return {"task": task["id"], "passed": False, "error": f"{type(error).__name__}: {error}"}
    return {
        "task": task["id"], "passed": True, "consume_ns": consume_ns,
        "answer": consumed["answer"], "images": consumed["images"],
    }


def exercise_negative_controls(payload, schema, public_dir, task, oracle):
    """Mutate one non-empty BC case in either wire format and verify rejection."""
    wire = json.loads(payload)
    columns = schema["columns"]

    def key(name, field):
        return columns[name].index(field) if isinstance(wire, list) else field

    def observation(package):
        return package[key("package", "observations")][0]

    def unit(package):
        package[key("package", "length_unit")] = "mm"

    def missing(package):
        obs = observation(package)
        del obs[key("observation", "frame_id")]

    def wrong_frame(package):
        obs = observation(package)
        obs[key("observation", "frame_id")] += 1

    def wrong_face(package):
        clearance = observation(package)[key("observation", "clearance")]
        witness = clearance[key("clearance", "witness_a")]
        witness[key("witness", "original_face_id")] += 1

    results = {}
    for mutate in (unit, missing, wrong_frame, wrong_face):
        variant = deepcopy(wire)
        mutate(variant)
        bad = json.dumps(variant, separators=(",", ":")).encode("utf-8")
        report = score_public(bad, schema, public_dir, task, oracle)
        results[mutate.__name__] = {"rejected": not report["passed"], "error": report.get("error")}
    return results


class PublicWireReaderTest(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "versions": {"candidate": "he-ao/1", "baseline": "he-ao-json/1"},
            "columns": {
                "package": ("version", "length_unit", "object_ids", "observations", "outcome"),
                "observation": ("observation_id", "frame_id", "objects", "clearance", "deformation", "image"),
                "object": ("object_index", "topology_generation", "center_m"),
                "clearance": ("status", "target_object_indices", "distance_m", "witness_a", "witness_b"),
                "witness": ("original_face_id", "point_m"),
            },
        }
        gap = 2**-22
        point_a, point_b = [-0.0, .125, .25], [gap, .125, .25]
        self.wire = [
            "he-ao/1", "m", ["a", "b"],
            [["capture", 7, [[0, 1, None], [1, 3, None]],
              ["positive_gap", [0, 1], gap, [0, point_a], [0, point_b]], None, None]],
            None,
        ]
        self.named = {
            "version": "he-ao-json/1", "length_unit": "m", "object_ids": ["a", "b"], "outcome": None,
            "observations": [{
                "observation_id": "capture", "frame_id": 7,
                "objects": [
                    {"object_index": 0, "topology_generation": 1, "center_m": None},
                    {"object_index": 1, "topology_generation": 3, "center_m": None},
                ],
                "clearance": {
                    "status": "positive_gap", "target_object_indices": [0, 1], "distance_m": gap,
                    "witness_a": {"original_face_id": 0, "point_m": point_a},
                    "witness_b": {"original_face_id": 0, "point_m": point_b},
                },
                "deformation": None, "image": None,
            }],
        }
        self.oracle = {
            "observations": [{
                "observation_id": "capture", "frame_id": 7,
                "objects": {
                    "a": {"topology_generation": 1, "center_m": None},
                    "b": {"topology_generation": 3, "center_m": None},
                },
                "clearance": {
                    "target_ids": ["a", "b"], "distance_m": gap, "triangle_a": 0, "triangle_b": 0,
                    "point_a": point_a, "point_b": point_b,
                    "triangles_a": [[[0, 0, 0], [0, 1, 0], [0, 0, 1]]],
                    "triangles_b": [[[gap, 0, 0], [gap, 1, 0], [gap, 0, 1]]],
                    "analytic_distance_m": gap, "analytic_tol_m": 0,
                },
                "deformation": None, "image": None,
            }],
            "outcome": None,
        }

    def test_public_both_arms_and_negative_controls(self):
        answers = []
        for wire in (self.wire, self.named):
            payload = json.dumps(wire).encode()
            result = score_public(payload, self.schema, Path(), {"id": "02"}, self.oracle)
            self.assertTrue(result["passed"], result.get("error"))
            answers.append(result["answer"])
            failures = exercise_negative_controls(payload, self.schema, Path(), {"id": "02"}, self.oracle)
            self.assertEqual(set(failures), {"unit", "missing", "wrong_frame", "wrong_face"})
            self.assertTrue(all(item["rejected"] for item in failures.values()), failures)
        self.assertEqual(*answers)

    def test_nonfinite_json_is_rejected(self):
        self.wire[3][0][3][2] = float("nan")
        with self.assertRaisesRegex(ValueError, "Non-finite JSON"):
            decode_public(json.dumps(self.wire).encode(), self.schema)
