"""Independent AO consumer: schema, questions, one public arm and its PNGs.

No encoder, Blender, fixture, private truth or alternate-arm package import.
Validation establishes public consistency, not unseen geometry or host history.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


class PublicDataError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PublicDataError(reason)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def vector(value, length=3):
    require(isinstance(value, list) and len(value) == length and all(number(v) for v in value),
            f"Expected a finite {length}-component vector")
    return np.asarray(value, dtype=float)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


class Reader:
    def __init__(self):
        self.files = {}
        self.images = {}

    def bytes(self, path, kind):
        path = Path(path).resolve()
        require("private" not in {part.lower() for part in path.parts}, "Private input is forbidden")
        data = path.read_bytes()
        self.files[str(path)] = {"path": str(path), "kind": kind, "bytes": len(data),
                                 "sha256": hashlib.sha256(data).hexdigest()}
        return data

    def json(self, path, kind):
        return json.loads(self.bytes(path, kind), parse_constant=lambda value: (_ for _ in ()).throw(
            PublicDataError("Nonfinite JSON literal: " + value)))

    def png(self, path):
        path = Path(path).resolve()
        require(path.suffix.lower() == ".png", "Public image reference must be a PNG")
        if str(path) not in self.images:
            data = self.bytes(path, "package-referenced PNG")
            with Image.open(BytesIO(data)) as image:
                require(image.format == "PNG", "Image contents are not PNG")
                image.load()
                pixels = np.asarray(image.convert("RGBA"))
                info = {"path": str(path), "format": image.format, "mode": image.mode,
                        "width_px": image.width, "height_px": image.height,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            self.images[str(path)] = pixels, info
        return self.images[str(path)]


CHILDREN = {
    "package": {"observations": ("observation", True), "outcome": ("outcome", False)},
    "observation": {"objects": ("object", True), "clearance": ("clearance", False),
                    "deformation": ("deformation", False), "image": ("image", False)},
    "clearance": {"witness_a": ("witness", False), "witness_b": ("witness", False)},
    "deformation": {"faces": ("face", True)},
    "image": {"section": ("section", False), "global_view": ("view", False), "local_view": ("view", False)},
    "outcome": {"goal": ("goal", False), "command": ("command", False)},
}


def unpack(schema, kind, value):
    if value is None:
        return None
    columns = schema["columns"][kind]
    if isinstance(value, list):
        require(len(value) == len(columns), f"{kind}: missing or extra column")
        result = dict(zip(columns, deepcopy(value)))
    else:
        require(isinstance(value, dict) and set(value) == set(columns), f"{kind}: missing or extra named field")
        result = deepcopy(value)
    for key, (child, many) in CHILDREN.get(kind, {}).items():
        if many:
            require(isinstance(result[key], list), f"{kind}.{key} must be a list")
            result[key] = [unpack(schema, child, row) for row in result[key]]
        else:
            result[key] = unpack(schema, child, result[key])
    return result


def _matrix(value):
    require(isinstance(value, list) and len(value) == 4, "Expected a 4x4 matrix")
    return np.asarray([vector(row, 4) for row in value])


def _project(view, point, image_height):
    matrix = _matrix(view["gpu_view_projection_m"])
    clip = matrix @ np.r_[vector(point), 1.]
    require(clip[3] != 0, "Point projects to infinity")
    ndc = clip[:3] / clip[3]
    x, y, width, height = view["viewport"]
    pixel = (x + (ndc[0] + 1) * width / 2 - .5,
             image_height - y - (ndc[1] + 1) * height / 2 - .5)
    return {"pixel_top_left": list(map(float, pixel)), "ndc_depth": float(ndc[2]),
            "inside_panel": bool(x - .5 <= pixel[0] < x + width - .5
                                 and image_height - y - height - .5 <= pixel[1] < image_height - y - .5)}


def _camera_checks(view, scale, expected_viewport):
    require(view["viewport"] == expected_viewport, "Incorrect dual-panel layout")
    require(view["camera_type"] == "ORTHO", "Expected an orthographic camera")
    require(number(view["ortho_scale_blender"]) and view["ortho_scale_blender"] > 0, "Invalid camera width")
    require(0 < view["clip_start_blender"] < view["clip_end_blender"], "Invalid camera depth range")
    world = _matrix(view["matrix_world_blender"]).copy()
    world[:3, 3] *= scale
    projection = _matrix(view["projection_blender"]) @ np.diag((1 / scale, 1 / scale, 1 / scale, 1.))
    actual_view = _matrix(view["gpu_view_m"])
    actual_projection = _matrix(view["gpu_projection_m"])
    actual_combined = _matrix(view["gpu_view_projection_m"])
    # Matrix storage is float32 in Blender. This is a public cross-record
    # consistency tolerance, not an independent native-camera measurement.
    close = lambda a, b: bool(np.allclose(a, b, rtol=2e-6, atol=2e-6))
    require(close(actual_view, np.linalg.inv(world)), "Camera world/GPU view mismatch")
    require(close(actual_projection, projection), "Camera unit/projection mismatch")
    require(close(actual_combined, actual_projection @ actual_view), "GPU matrix product mismatch")
    return {"public_matrices_consistent": True, "native_camera_execution_verified": False}


def normalize(schema, raw, package_path, reader):
    package = unpack(schema, "package", raw)
    require(package is not None, "Missing package")
    require(package["version"] in schema["versions"].values(), "Unknown schema version")
    require(package["length_unit"] == "m", "Physical length unit must be m")
    ids = package["object_ids"]
    require(isinstance(ids, list) and all(isinstance(i, str) and i for i in ids)
            and len(set(ids)) == len(ids), "Object table must have unique stable IDs")

    def object_id(index, present=None):
        require(integer(index) and 0 <= index < len(ids), "Object index outside public table")
        require(present is None or index in present, "Object absent from this observation")
        return ids[index]

    observations = package["observations"]
    require(observations and len({o["observation_id"] for o in observations}) == len(observations),
            "Observations must be present and uniquely identified")
    for observation in observations:
        require(isinstance(observation["observation_id"], str) and observation["observation_id"], "Missing observation ID")
        require(integer(observation["frame_id"]), "Frame must be an integer")
        present = {item["object_index"] for item in observation["objects"]}
        require(len(present) == len(observation["objects"]), "Duplicate observation object")
        objects = {}
        for item in observation["objects"]:
            item["object_id"] = object_id(item["object_index"])
            require(integer(item["topology_generation"]) and item["topology_generation"] >= 0, "Invalid topology generation")
            if item["center_m"] is not None:
                vector(item["center_m"])
            objects[item["object_index"]] = item
        clearance = observation["clearance"]
        if clearance is not None:
            require(len(clearance["target_object_indices"]) == 2, "Clearance requires two targets")
            clearance["target_object_ids"] = [object_id(i, present) for i in clearance["target_object_indices"]]
            status, distance = clearance["status"], clearance["distance_m"]
            if status == "empty_surface":
                require(all(clearance[k] is None for k in ("distance_m", "witness_a", "witness_b")), "Empty surface has defined distance/witness")
            else:
                require(status in ("positive_gap", "zero_distance") and number(distance), "Invalid clearance status/distance")
                require((distance > 0) if status == "positive_gap" else distance == 0, "Status contradicts surface distance")
                for key, index in zip(("witness_a", "witness_b"), clearance["target_object_indices"]):
                    witness = clearance[key]
                    require(witness is not None and integer(witness["original_face_id"])
                            and witness["original_face_id"] >= 0, "Invalid original triangle row")
                    vector(witness["point_m"])
                    witness["binding"] = {"object_id": ids[index], "frame_id": observation["frame_id"],
                                          "observation_id": observation["observation_id"],
                                          "topology_generation": objects[index]["topology_generation"]}
                points = np.asarray([clearance[k]["point_m"] for k in ("witness_a", "witness_b")])
                magnitude = float(np.abs(points).max())
                require(math.isclose(float(np.linalg.norm(points[1] - points[0])), distance,
                                     rel_tol=1e-10, abs_tol=64 * np.finfo(float).eps * magnitude),
                        "Witness separation contradicts distance")
        deformation = observation["deformation"]
        if deformation is not None:
            deformation["object_id"] = object_id(deformation["object_index"], present)
            require(integer(deformation["reference_frame"]) and all(integer(f) for f in deformation["sample_frames"]), "Invalid TD frame scope")
            require(deformation["position_frame"] in deformation["sample_frames"], "TD position frame outside sampling scope")
            require(deformation["position_kind"] == "face_centroid", "Unsupported TD position semantics")
            count = deformation["reduced_face_count"]
            require(integer(count) and count >= 0, "Invalid reduced-face count")
            face_ids = [face["original_face_id"] for face in deformation["faces"]]
            require(len(face_ids) == len(set(face_ids)) and all(integer(f) and 0 <= f < count for f in face_ids), "TD face outside declared reduction range")
            top = deformation["top_face_ids"]
            require(face_ids[:len(top)] == top and len(top) == len(set(top)), "Top-K rows/order do not match transmitted faces")
            metrics = schema["columns"]["face"][1:-1]
            for face in deformation["faces"]:
                require(all(face[key] is None or number(face[key]) for key in metrics), "Invalid TD metric")
                vector(face["position_m"])
                face["undefined_metrics"] = [key for key in metrics if face[key] is None]
            deformation["peak_occurrence_frame"] = {"available": False, "reason": "No peak-occurrence field in public schema"}
        image = observation["image"]
        if image is not None:
            require((image["width_px"], image["height_px"]) == (1024, 512), "Incorrect declared image dimensions")
            scale = image["meters_per_blender_unit"]
            require(number(scale) and scale > 0, "Invalid Blender length scale")
            image["target_object_ids"] = [object_id(i, present) for i in image["target_object_indices"]]
            image["mesh_object_ids"] = [object_id(i, present) for i in image["mesh_object_indices"]]
            require(clearance is not None and image["target_object_indices"] == clearance["target_object_indices"], "Image/clearance targets differ")
            require(set(image["target_object_indices"]).issubset(image["mesh_object_indices"]), "Image target absent from mesh list")
            require(image["mode"] in ("NATURAL", "SECTION"), "Unknown visual mode")
            image["panel_semantics"] = {
                "global_view": "Original unsectioned scene",
                "local_view": "Declared section half-space" if image["mode"] == "SECTION" else "Original unsectioned geometry",
                "basis": "Public schema semantics; not independent reconstruction of source geometry",
            }
            section = image["section"]
            if image["mode"] == "NATURAL":
                require(section is None, "Natural image declares a section")
            else:
                require(section is not None and section["kept_side"] == "<=0", "Missing or invalid section declaration")
                point, normal = vector(section["point_m"]), vector(section["normal"])
                require(np.linalg.norm(normal) > 0, "Zero section normal")
                for key in ("witness_a", "witness_b"):
                    require(abs((vector(clearance[key]["point_m"]) - point) @ normal) <= 1e-8,
                            "Section plane does not contain witnesses")
            path = Path(package_path).parent / image["path"]
            pixels, opened = reader.png(path)
            require((opened["width_px"], opened["height_px"]) == (image["width_px"], image["height_px"]), "PNG dimensions disagree with package")
            image["opened_png"] = opened
            image["binding"] = {"observation_id": observation["observation_id"], "frame_id": observation["frame_id"],
                                "source": "Inherited from the enclosing observation per public schema"}
            image["camera_checks"] = {name: _camera_checks(image[name], scale, [offset, 0, 512, 512])
                                      for name, offset in (("global_view", 0), ("local_view", 512))}
            image["witness_projection"] = {
                name: [_project(image[name], clearance[key]["point_m"], 512) for key in ("witness_a", "witness_b")]
                for name in ("global_view", "local_view")}
            image["object_center_projection"] = {}
            for item in observation["objects"]:
                if item["center_m"] is None:
                    continue
                projected = _project(image["global_view"], item["center_m"], 512)
                if projected["inside_panel"]:
                    x, y = (math.floor(v + .5) for v in projected["pixel_top_left"])
                    projected["actual_png_rgba_at_projected_center"] = pixels[y, x].tolist()
                image["object_center_projection"][item["object_id"]] = projected
    outcome = package["outcome"]
    if outcome is not None:
        by_id = {o["observation_id"]: o for o in observations}
        require(outcome["before_observation_id"] in by_id and outcome["after_observation_id"] in by_id,
                "Outcome refers to an absent observation")
        require(outcome["before_observation_id"] != outcome["after_observation_id"], "Outcome before/after must differ")
        for label in ("before", "after"):
            observation = by_id[outcome[label + "_observation_id"]]
            require(outcome["distance_" + label + "_m"] == observation["clearance"]["distance_m"], "Outcome distance/observation mismatch")
        delta = outcome["distance_after_m"] - outcome["distance_before_m"]
        require(outcome["measured_delta_m"] == delta, "Measured delta is not after minus before")
        goal = outcome["goal"]
        goal["moving_object_id"] = object_id(goal["moving_object_index"])
        goal["reference_object_id"] = object_id(goal["reference_object_index"])
        for label in ("before", "after"):
            clearance = by_id[outcome[label + "_observation_id"]]["clearance"]
            require(set(clearance["target_object_ids"]) == {goal["moving_object_id"], goal["reference_object_id"]},
                    "Outcome goal objects differ from clearance targets")
        command = outcome["command"]
        require(command["kind"] in ("translate", "set_shape_key"), "Unknown command kind")
        if command["kind"] == "translate":
            vector(command["delta_world_m"])
            vector(outcome["control_before"])
            vector(outcome["control_after"])
        else:
            require(isinstance(command["key_name"], str) and command["key_name"]
                    and number(command["target_value"]) and number(outcome["control_before"])
                    and number(outcome["control_after"]), "Invalid shape-key command/readback")
        reached = abs(outcome["distance_after_m"] - goal["target_distance_m"]) <= goal["tolerance_m"]
        require(outcome["goal_reached"] is reached, "Goal result contradicts public measured distance")
        outcome["recomputed_goal_reached"] = reached
    return package


def answer_task(task, package, *, before_only=False):
    observations = package["observations"]
    task_id = int(task["id"])
    if before_only:
        require(len(observations) == 1 and package["outcome"] is None, "Action-before package already contains an outcome")
        goal = task["goal"]
        require(goal["moving_id"] in package["object_ids"] and goal["reference_id"] in package["object_ids"], "Task goal objects absent from initial package")
        require(set(observations[0]["clearance"]["target_object_ids"]) == {goal["moving_id"], goal["reference_id"]}, "Task targets and initial clearance differ")
        return {"before_observation_id": observations[0]["observation_id"], "frame_id": observations[0]["frame_id"],
                "clearance": observations[0]["clearance"], "requested_goal": goal, "explicit_command": task["command"],
                "execution_performed_by_this_consumer": False}
    if task_id <= 8:
        require(len(observations) == 1 and observations[0]["clearance"] is not None, "Task requires one clearance observation")
        return {"observation_id": observations[0]["observation_id"], "frame_id": observations[0]["frame_id"],
                "clearance": observations[0]["clearance"],
                "interpretation": "Unsigned surface distance; zero does not establish a contact/intersection class or penetration depth."}
    if task_id <= 14:
        deformation = observations[0]["deformation"]
        require(deformation is not None, "Task requires TD facts")
        result = {"observation_id": observations[0]["observation_id"], "deformation": deformation}
        if task_id == 9:
            result["interpretation"] = "Principal stretches describe directional extension/compression independently of area strain."
        if task_id == 10:
            result["angle_semantics"] = "World normal rotation in degrees, not intrinsic inversion"
        return result
    if task_id in (15, 16, 17, 18):
        selected = observations
        if "requested_frame" in task:
            selected = [o for o in observations if o["frame_id"] == task["requested_frame"]]
            require(len(selected) == 1, "Requested frame is absent or ambiguous")
        require(all(o["image"] is not None for o in selected), "Visual task has no public PNG")
        result = {"selected_observations": selected}
        if task_id == 17:
            image = selected[0]["image"]
            result["locations"] = {}
            for key in ("target_id", "decoy_id"):
                object_id = task[key]
                require(object_id in image["object_center_projection"], "Requested object has no public position")
                center = next(item["center_m"] for item in selected[0]["objects"] if item["object_id"] == object_id)
                result["locations"][key] = {"object_id": object_id, "world_center_m": center,
                                            **image["object_center_projection"][object_id]}
            result["identity_basis"] = "Public stable IDs and projected world centers; sampled color alone is not identity proof"
        return result
    require(task_id in (19, 20) and package["outcome"] is not None, "Action task has no outcome")
    outcome = package["outcome"]
    goal = outcome["goal"]
    expected = task["goal"]
    require((goal["moving_object_id"], goal["reference_object_id"], goal["target_distance_m"], goal["tolerance_m"])
            == (expected["moving_id"], expected["reference_id"], expected["distance_m"], expected["tolerance_m"]),
            "Outcome goal differs from the public task")
    require(outcome["command"] == task["command"], "Outcome command differs from the public task")
    return {"outcome": outcome, "execution_performed_by_this_consumer": False,
            "host_readbacks": "Reported actual controls/distances; host execution is not independently observable from this package"}


def consume(schema, task, raw, path, reader, before_only=False):
    package = normalize(schema, raw, path, reader)
    return {"task_id": task["id"], "question": task["question"], "source_package": str(Path(path).resolve()),
            "public_consistency_passed": True, "answer": answer_task(task, package, before_only=before_only),
            "normalized_facts": package}


def negatives(schema, tasks, raws, paths, reader):
    tests = []
    def trial(name, task_id, mutate):
        raw = deepcopy(raws[task_id])
        mutate(raw)
        try:
            consume(schema, tasks[task_id], raw, paths[task_id], reader)
        except (PublicDataError, KeyError, TypeError, ValueError) as error:
            tests.append({"name": name, "rejected": True, "reason": str(error)})
        else:
            tests.append({"name": name, "rejected": False})
    # Convert the already-read arm to schema-named public records for mutation;
    # this does not read or reconstruct the other arm's bytes.
    raws = {key: unpack(schema, "package", value) for key, value in raws.items()}
    trial("missing_required_distance_field", "01", lambda r: r["observations"][0]["clearance"].pop("distance_m"))
    trial("wrong_declared_length_unit", "01", lambda r: r.update(length_unit="mm"))
    trial("object_index_outside_public_table", "01", lambda r: r["observations"][0]["clearance"]["target_object_indices"].__setitem__(0, len(r["object_ids"])))
    trial("negative_original_triangle_row", "01", lambda r: r["observations"][0]["clearance"]["witness_a"].update(original_face_id=-1))
    trial("requested_frame_missing", "18", lambda r: r["observations"][1].update(frame_id=9))
    trial("local_panel_has_global_viewport", "15", lambda r: r["observations"][0]["image"]["local_view"].update(viewport=[0, 0, 512, 512]))
    trial("gpu_camera_matrix_inconsistent", "15", lambda r: r["observations"][0]["image"]["local_view"]["gpu_view_m"][0].__setitem__(3, 10.))
    trial("outcome_references_missing_observation", "19", lambda r: r["outcome"].update(after_observation_id="missing"))
    return tests


LIMITS = [
    "No private geometry: BC triangle-row upper bounds, witness-on-face membership and true global distance are not independently verifiable here.",
    "PNG opens and its declared dimensions/cameras/object/observation links are checked. The PNG has no independently authenticated frame or observation provenance; package association does not prove host rendering history.",
    "Object-center projection locates the declared center in the actual PNG. A sampled pixel color does not independently identify the underlying mesh or prove visibility.",
    "TD peak occurrence frames are absent. Null metrics remain undefined; no missing extrema or locations are invented.",
    "Action outcomes are public reported readbacks, not execution by this consumer. Independent host evidence must establish that Blender performed them.",
    "A self-consistent replacement of a value and all redundant public fields may be undetectable without external truth. Negative controls only claim publicly decidable inconsistencies.",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, action="append", required=True)
    parser.add_argument("--arm", choices=("c", "b"), default="c")
    parser.add_argument("--before-prefix", help="Explicit prefix for public action-before packages; omit to read none")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reader = Reader()
    if args.protocol:
        reader.bytes(args.protocol, "public acceptance protocol")
    schema = reader.json(args.schema, "public schema")
    states = []
    for directory in args.state_dir:
        tasks_list = reader.json(directory / "tasks.json", "public task questions")
        tasks = {task["id"]: task for task in tasks_list}
        require(set(tasks) == {f"{n:02d}" for n in range(1, 21)}, "Expected the 20 public tasks")
        paths = {key: directory / f"{key}.{args.arm}.json" for key in tasks}
        raws = {key: reader.json(path, "single-arm public package") for key, path in paths.items()}
        answers = []
        for key, task in tasks.items():
            try:
                answers.append(consume(schema, task, raws[key], paths[key], reader))
            except Exception as error:
                answers.append({"task_id": key, "source_package": str(paths[key].resolve()),
                                "public_consistency_passed": False, "error": f"{type(error).__name__}: {error}"})
        before = []
        if args.before_prefix:
            for key in ("19", "20"):
                path = directory / f"{args.before_prefix}-before-{key}.json"
                raw = reader.json(path, "single-arm public action-before package")
                try:
                    item = consume(schema, tasks[key], raw, path, reader, before_only=True)
                    final = next(answer for answer in answers if answer["task_id"] == key)
                    final_observation = final["normalized_facts"]["observations"][0]
                    require(item["normalized_facts"]["observations"][0] == final_observation,
                            "Before package differs from the final package's prior observation")
                    item["matches_final_before_observation"] = True
                    before.append(item)
                except Exception as error:
                    before.append({"task_id": key, "public_consistency_passed": False, "error": str(error)})
        controls = negatives(schema, tasks, raws, paths, reader)
        states.append({"state_directory": str(directory.resolve()), "answers": answers,
                       "action_before_answers": before, "negative_controls": controls})
    result = {"arm": args.arm, "consumer_scope": "Independent public-only script; no encoder, private truth, alternate arm or Blender execution",
              "states": states, "limitations": LIMITS, "files_read": list(reader.files.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    summary = {"arm": args.arm, "states": [{"state": s["state_directory"],
               "public_answers": sum(a["public_consistency_passed"] for a in s["answers"]),
               "before_packages": sum(a["public_consistency_passed"] for a in s["action_before_answers"]),
               "negatives_rejected": sum(n["rejected"] for n in s["negative_controls"])} for s in states],
               "files_read": len(reader.files), "limitations": LIMITS}
    review = args.output.with_name(args.output.stem + "_review.md")
    review_lines = ["# AO 独立单臂公开消费", "", f"本次只消费 {args.arm} 臂。未读取编码器、场景夹具、作者消费实现、私有真值或另一臂包。",
                    "", "| 状态 | 可恢复答案 | 动作前包 | 拒绝的公开负例 |", "| --- | ---: | ---: | ---: |"]
    review_lines += [f"| {Path(item['state']).name} | {item['public_answers']}/20 | {item['before_packages']}/2 | {item['negatives_rejected']}/8 |"
                     for item in summary["states"]]
    review_lines += ["", f"实际读取 {len(reader.files)} 份公开文件，其中 {len(reader.images)} 张PNG已由Pillow完整解码。",
                     "归一化事实保留原有有限浮点值、null与完整字段；见证绑定对象/帧/拓扑代次，TD位置与采样范围分开，峰值发生帧明确不可恢复。",
                     "图像核验实际文件、尺寸、左右布局、公开相机矩阵一致性、米制变换、目标表和观察继承关系。目标/同色诱饵依靠公开ID与中心投影定位，颜色采样不充当身份真值。",
                     "动作前包须与最终公开包中对应的前观察完整一致。动作答案恢复明确命令、前后观测、实际控制读数、实测距离差和目标结果；本消费者没有执行动作。",
                     "", "负例均从本臂已读事实在内存中修改：缺必需字段、错单位声明、对象索引越界、负三角行号、请求帧缺失、错误左右布局、矩阵不一致、Outcome引用不存在观察。",
                     "没有把仅凭私有几何才能判断的错误数值、合法但错误的BC面号、或自洽篡改的帧标签列为已检测。", "", "剩余证据边界：", ""]
    review_lines += ["- " + limit for limit in LIMITS]
    review_lines += ["", "仅为脚本公开消费结果，未运行外部模型。公开一致性不等于私有几何或宿主执行验收。完整文件读取清单、逐题答案和归一化事实见" + args.output.name + "。", ""]
    review.write_text("\n".join(review_lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    passed = all(all(answer["public_consistency_passed"] for answer in state["answers"])
                 and all(answer["public_consistency_passed"] for answer in state["action_before_answers"])
                 and all(control["rejected"] for control in state["negative_controls"])
                 for state in states)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
