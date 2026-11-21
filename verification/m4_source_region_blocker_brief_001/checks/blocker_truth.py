"""Independently audit the six blocker facts in the retained P1 call 4."""

import argparse
import ast
import base64
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
from PIL import Image


RUN = Path("D:/he_perf050_dual_region_occlusion_transfer_001")
INDEX = Path(__file__).resolve().parents[2] / "perf050_dual_region_occlusion_transfer_001/RUNTIME_INDEX.json"
ARCHIVE_SHA = "a750e623fee4737c14eeef3552deb59ddfc2bc5cc70ebd4009606a58d2ebcf36"
SLOT = "slots/P1"


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ArchivedRun:
    def __init__(self, path, index, archive):
        self.path = path
        self.index = {row["path"]: row for row in index["files"]}
        self.archive = archive
        self.checked = {}

    def bytes(self, relative):
        member = f"{SLOT}/{relative}"
        raw = self.archive.read(member)
        receipt = self.index[member]
        require(len(raw) == receipt["bytes"] and sha(raw) == receipt["sha256"], f"index mismatch {relative}")
        require(raw == (self.path / member).read_bytes(), f"retained file mismatch {relative}")
        self.checked[member] = receipt
        return raw

    def document(self, relative):
        return json.loads(self.bytes(relative))

    def events(self, relative):
        return [json.loads(line) for line in self.bytes(relative).splitlines() if line.strip()]


def clip_polygon(points, signed_distance):
    """Clip a convex polygon by an affine half-space with exact crossings."""
    result = []
    if not points:
        return result
    start = points[-1]
    start_value = signed_distance(start)
    for end in points:
        end_value = signed_distance(end)
        if (start_value < 0 < end_value) or (end_value < 0 < start_value):
            t = start_value / (start_value - end_value)
            result.append(tuple(a + t * (b - a) for a, b in zip(start, end, strict=True)))
        if end_value >= 0:
            result.append(end)
        start = end
        start_value = end_value
    return result


def matrix_times(matrix, vector):
    return tuple(sum(a * b for a, b in zip(row, vector, strict=True)) for row in matrix)


def camera_transform(pose):
    view = [tuple(map(Fraction, row)) for row in pose["view_matrix"]]
    projection = [tuple(map(Fraction, row)) for row in pose["projection_matrix"]]

    def transform(point):
        return matrix_times(projection, matrix_times(view, (*point, Fraction(1))))

    return transform


def frustum_clip(points, transform):
    def distance(point, axis, sign):
        camera = transform(point)
        return camera[3] + sign * camera[axis]

    for axis in range(3):
        for sign in (-1, 1):
            points = clip_polygon(points, lambda point: distance(point, axis, sign))
    return points


def area_xy(points):
    if not points:
        return Fraction(0)
    edges = zip(points, points[1:] + points[:1], strict=True)
    return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in edges)) / 2


def overlap_on_selection(points, direction, height, rectangle, transform):
    """Pull the clipped blocker along parallel rays to the selection's z-plane."""
    if max(vertex[2] for vertex in points) <= height:
        return Fraction(0)
    points = clip_polygon(frustum_clip(points, transform), lambda point: point[2] - height)
    if not points or max(vertex[2] for vertex in points) <= height:
        return Fraction(0)
    dx, dy, dz = direction
    projected = [(x - dx * (z - height) / dz, y - dy * (z - height) / dz) for x, y, z in points]
    for axis, (low, high) in enumerate(rectangle):
        projected = clip_polygon(projected, lambda point: point[axis] - low)
        projected = clip_polygon(projected, lambda point: high - point[axis])
    return area_xy(projected)


def native_capture(evidence):
    resources = {}
    for sequence in (2, 3, 4, 5):
        folder = f"native/WIRE/{sequence:03}"
        tx = evidence.document(f"{folder}/REQUEST.bin")
        rx = evidence.document(f"{folder}/RESPONSE.bin")
        request = re.search(r"_request = _json.loads\((.+)\)\n", tx["params"]["code"])
        require(request is not None, "no native request in execute_code")
        command = json.loads(ast.literal_eval(request.group(1)))
        prefix = "HUMAN_EYE_BLENDER_MCP:"
        packets = [json.loads(line[len(prefix):]) for line in rx["result"]["result"].splitlines()
                   if line.startswith(prefix)]
        require(rx["status"] == "success" and len(packets) == 1, f"bad native capture {sequence}")
        packet = packets[0]
        require(command["command"] == "capture" and packet.get("error") is None, f"unexpected native operation {sequence}")
        require(packet["id"] == command["id"], f"native request/response ID mismatch {sequence}")
        value = packet["result"]
        for row in value["resources"]:
            key = row["id"], row["revision"]
            require(key not in resources or resources[key] == row, "native resources changed at fixed revision")
            resources[key] = row
    capture = value["capture"]
    meshes = []
    for mesh in capture["meshes"]:
        reference = mesh["_scene_resource"]
        resource = resources[reference["id"], reference["revision"]]
        matrix = [tuple(map(Fraction, row)) for row in reference["matrix"]]
        scale = Fraction(reference["scale"])
        vertices = [
            tuple(c * scale for c in matrix_times(matrix, (*map(Fraction, vertex), Fraction(1)))[:3])
            for vertex in resource["vertices_local"]
        ]
        meshes.append((mesh["object_id"], mesh["name"], vertices, resource["faces"]))
    return capture, meshes


def verify_sources(evidence, producer):
    capture, meshes = native_capture(evidence)
    binding = producer["binding"]
    terminal = evidence.document("TERMINAL_SOURCE.json")
    initial = evidence.document("initial_capture/TERMINAL_SOURCE.json")
    require(capture["revision"] == binding["scene_revision"] and capture["capture_state"] == binding["capture_state"]
            and capture["host_identity"]["document_epoch"] == binding["document_epoch"], "capture generation mismatch")
    require(capture["source"] == binding["source"] == "blender" and capture["unit"] == binding["unit"] == "m"
            and capture["coordinate_frame"] == binding["coordinate_frame"] == "world", "source coordinates mismatch")
    display_rows = binding["image_scope"]["objects"]
    snapshot = capture["display_snapshot"]
    require(len(meshes) == len(display_rows) == 9 and sum(len(mesh[3]) for mesh in meshes) == 56, "scene size changed")
    for index, (mesh, source, before, binding_row, display_row) in enumerate(
        zip(meshes, terminal["objects"], initial["objects"], binding["objects"], display_rows, strict=True)
    ):
        host_id, name, vertices, faces = mesh
        instance = capture["host_identity"]["object_instances"][host_id]
        expected_row = {"host_id": host_id, "object_name": name, "object_index": index, "instance_id": instance}
        require(binding_row == expected_row and all(display_row[key] == value for key, value in expected_row.items()),
                f"display/source directory mismatch at {index}")
        require(all(display_row[key] == value for key, value in snapshot["objects"][index].items()),
                f"display snapshot row mismatch at {index}")
        for check_source in (source, before):
            require((check_source["object_id"], check_source["name"], check_source["instance_id"]) == (host_id, name, instance),
                    f"independent source object mismatch at {index}")
            evaluated = check_source["evaluated"]
            require(vertices == [tuple(map(Fraction, row)) for row in evaluated["vertices_world_m"]]
                    and faces == evaluated["triangles"], f"independent source geometry mismatch at {index}")
            require(check_source["visible_get"] is display_row["visible_get"] is display_row["participates"],
                    f"independent source display mismatch at {index}")
    require(binding["display_identity"] == binding["image_scope"]["identity"] == snapshot["sha256"],
            "source display snapshot mismatch")
    return meshes, terminal


def verify_line_packets(evidence, producer):
    tx = evidence.document("mcp/rpc_07/TX.bin")
    rx = evidence.document("mcp/rpc_07/RX.bin")
    receipt = evidence.document("mcp/rpc_07/RECEIPT.json")
    launch = evidence.events("PUBLIC_REQUESTS.jsonl")[3]
    owner_rx = evidence.document("owner/tool_04/RESPONSE.json")
    owner_tx = evidence.document("owner/tool_04/REQUEST.json")
    product_rx = evidence.document("owner/tool_04/PRODUCT_RESPONSE.json")
    content = rx["result"]["content"]
    calls = [row["item"] for row in evidence.events("consumer/stdout.raw.bin")
             if row.get("type") == "item.completed" and row.get("item", {}).get("type") == "mcp_tool_call"]
    cli = calls[3]
    require(receipt == launch["receipt"] and tx["id"] == rx["id"] == receipt["id"] == launch["id"] == "observe-4"
            and receipt["RX_sha256"] == sha(evidence.bytes("mcp/rpc_07/RX.bin"))
            and sha(evidence.bytes("product_full/call_004/SERVICE_RESULT.json")) == launch["producer_archive"]["sha256"],
            "public receipt chain changed")
    require(tx == evidence.document("owner/tool_04/PRODUCT_REQUEST.json") and rx == product_rx
            and content == owner_rx["result"]["content"] == cli["result"]["content"], "line packet content changed")
    require(owner_tx["id"] == owner_rx["id"]
            and tx["params"]["name"] == owner_tx["params"]["name"] == cli["tool"] == "human_eye_scene_observe",
            "tool and outer request/response binding mismatch")
    require(owner_tx["params"]["arguments"] == cli["arguments"], "consumer request changed")
    arguments = tx["params"]["arguments"]
    require(arguments["query"]["mode"] == "source_region"
            and arguments["query"]["region"]["object"]["name"] == "Obj_06", "call four did not select Obj_06")
    require(len(content) == 2 and [block["type"] for block in content] == ["text", "image"],
            "historical brief content types changed")
    text = content[0]["text"]
    document = json.loads(text)
    require(len(text.encode()) == 7360 and document["region_ref"] == producer["region_ref"], "brief region binding mismatch")
    require(document["visibility"]["complete_witness"] is None
            and document["visibility"]["geometry_status"] == "positive_area_occlusion"
            and document["visibility"]["selected_surface_pixels"] == 0 and "blocker_evidence" not in document,
            "original brief semantics changed")
    require(content[1]["mimeType"] == "image/png", "historical original image type changed")
    return document, base64.b64decode(content[1]["data"], validate=True), cli["id"]


def verify_frame(evidence, producer, brief, wire_png, terminal, target_index, selected):
    frame, = producer["frames"]
    require(producer["constructed_frames"] == [frame] and producer["generation_work"]["raster_attempts"] == 1
            and producer["generation_work"]["raster_completed"] == 1, "not exactly one constructed frame")
    private_vis = producer["facts"]["visibility"]
    frame_row, = [row for row in evidence.document("DEVICE_EVIDENCE.json")["frames"] if row["ref"] == frame["image_ref"]]
    require(frame_row["frame_identity"] == frame["frame_identity"] == private_vis["frame_identity"]
            and frame_row["view"] == frame["view_name"] == frame["pose"]["name"] == "SCENE"
            and frame["display_identity"] == producer["binding"]["display_identity"] and frame["pose"] == frame_row["pose"],
            "only actual frame not bound to SCENE and current display")
    require(frame_row["source_face_offsets"] == terminal["source_face_offsets"], "frame source triangle offsets mismatch")
    public_image, = brief["images"]
    require(public_image["image_ref"] == private_vis["image_ref"] == frame["image_ref"], "brief original image ref mismatch")
    png_path = Path(frame["image_path"]).relative_to(evidence.path / SLOT).as_posix()
    npz_path = Path(frame["arrays_path"]).relative_to(evidence.path / SLOT).as_posix()
    raw_png = evidence.bytes(png_path)
    raw_npz = evidence.bytes(npz_path)
    require(raw_png == wire_png and sha(raw_png) == frame["image_sha256"] == frame_row["PNG_sha256"]
            and sha(raw_npz) == frame["arrays_sha256"] == frame_row["NPZ_sha256"], "archived/wire image bytes mismatch")
    with np.load(BytesIO(raw_npz), allow_pickle=False) as arrays:
        triangle_ids = arrays["triangle_ids"]
        color = arrays["color"]
        require(sha(triangle_ids.tobytes()) == frame["arrays"]["triangle_ids"]["sha256"]
                and sha(color.tobytes()) == frame["arrays"]["color"]["sha256"], "frame array checksum mismatch")
        first = terminal["source_face_offsets"][target_index]
        pixel_count = int(np.isin(triangle_ids, [first + face for face in selected]).sum())
        require(pixel_count == private_vis["selected_surface_pixels"] == 0
                and np.array_equal(color, np.asarray(Image.open(BytesIO(raw_png)).convert("RGB"))),
                "SCENE independent source pixels or RGB mismatch")
    return {"view": "SCENE", "frame_identity": frame["frame_identity"], "image_ref": frame["image_ref"],
            "source_revision": frame["source_revision"], "bytes_PNG": len(raw_png), "sha256_PNG": sha(raw_png),
            "bytes_NPZ": len(raw_npz), "sha256_NPZ": sha(raw_npz), "selected_surface_pixels": pixel_count}


def audit_blockers(producer, meshes):
    binding = producer["binding"]
    directory = binding["image_scope"]["objects"]
    region = producer["region_ref"]
    target_index, = [i for i, row in enumerate(directory) if row["host_id"] == region["host_id"]
                     and row["instance_id"] == region["instance_id"]]
    selected = region["source_triangle_indices"]
    generation = {key: binding["capture_state"][key] for key in ("instance_id", "epoch", "revision")}
    require(region["document_epoch"] == binding["document_epoch"] and region["capture_generation"] == generation
            and target_index == 2 and directory[target_index]["object_name"] == "Obj_06" and selected == [0, 1],
            "selected current region identity mismatch")
    _, _, vertices, faces = meshes[target_index]
    selected_vertices = {vertices[index] for face in selected for index in faces[face]}
    height, = {point[2] for point in selected_vertices}
    rectangle = tuple((min(point[axis] for point in selected_vertices), max(point[axis] for point in selected_vertices))
                      for axis in (0, 1))
    selection_area = (rectangle[0][1] - rectangle[0][0]) * (rectangle[1][1] - rectangle[1][0])
    require(height == 1 and len(selected_vertices) == 4 and selection_area == Fraction(1, 64), "frozen selected rectangle changed")
    require(sum(area_xy([vertices[index][:2] for index in faces[face]]) for face in selected) == selection_area,
            "selected triangles do not partition the rectangle")
    poses = binding["camera_specification"]["views"]
    attempts = producer["view_attempts"]
    require([attempt["view_name"] for attempt in attempts] == [pose["name"] for pose in poses]
            == ["SCENE", "TOP", "LEFT", "RIGHT", "FRONT", "BACK"], "original camera order mismatch")
    evidence = []
    for pose, attempt in zip(poses, attempts, strict=True):
        name = pose["name"]
        transform = camera_transform(pose)
        require(all(all(abs(c) <= v[3] for c in v[:3]) for v in map(transform, selected_vertices)),
                f"selected corners outside camera in {name}")
        direction = tuple(pose["direction_rational"])
        require(direction[2] > 0 and attempt["status"] == "positive_area_occlusion", f"non-forward outcome in {name}")
        area_scale = direction[2] * (direction[0] ** 2 + direction[1] ** 2 or direction[2] ** 2)
        overlaps = []
        for object_index, (_, _, object_vertices, object_faces) in enumerate(meshes):
            if not directory[object_index]["participates"]:
                continue
            for face, indices in enumerate(object_faces):
                if object_index == target_index and face in selected:
                    continue
                points = [object_vertices[index] for index in indices]
                overlap = overlap_on_selection(points, direction, height, rectangle, transform)
                if overlap > 0:
                    overlaps.append((object_index, face, overlap))
        first_object, first_face, overlap = overlaps[0]
        reported = attempt["first_blocker"]
        require((first_object, first_face, overlap * area_scale) ==
                (reported["object_index"], reported["source_triangle_index"], Fraction(reported["overlap_area_screen_exact"])),
                f"independent first blocker/overlap disagrees in {name}")
        require(first_object == 8 and directory[first_object]["object_name"] == "Obj_03", f"unexpected blocker in {name}")
        require(bool(attempt["constructed"]) == (name == "SCENE"), f"unexpected additional frame in {name}")
        blocker = meshes[first_object]
        source_triangle = blocker[3][first_face]
        face_points = [blocker[2][index] for index in source_triangle]
        require({point[2] for point in face_points} == {Fraction(9, 8)}, f"unexpected first blocker depth in {name}")
        evidence.append({
            "view": name, "direction": list(direction), "object_index": first_object,
            "object_name": blocker[1], "object_id": blocker[0], "instance_id": directory[first_object]["instance_id"],
            "source_triangle": first_face, "source_triangle_count": len(blocker[3]),
            "source_vertices": source_triangle, "source_points_world_m": [list(map(str, row)) for row in face_points],
            "depth_above_selection_world_m": "1/8", "positive_area_on_selection_plane_m2": str(overlap),
            "positive_area_in_reported_screen_basis": str(overlap * area_scale),
            "selection_plane_fraction": str(overlap / selection_area), "actual_sampling": attempt["constructed"],
            "other_positive_triangles": [[index, face] for index, face, _ in overlaps[1:]],
        })
    return evidence, target_index, selected


def control_truth(producer, meshes, target_index):
    binding = producer["binding"]
    top, = [pose for pose in binding["camera_specification"]["views"] if pose["name"] == "TOP"]
    transform = camera_transform(top)
    direction = tuple(top["direction_rational"])
    height = Fraction(1)
    rectangle = ((Fraction(31, 16), Fraction(33, 16)),) * 2
    base = Fraction(2)
    small = Fraction(1, 2**20)
    front = Fraction(9, 8)
    small_triangle = [(base, base, front), (base + small, base, front), (base, base + small, front)]
    area = overlap_on_selection(small_triangle, direction, height, rectangle, transform)
    require(0 < area == Fraction(1, 2**41) < Fraction(1, 64), "tiny overlap lost or not partial")
    equal_depth = [(x, y, height) for x, y, _ in small_triangle]
    require(overlap_on_selection(equal_depth, direction, height, rectangle, transform) == 0, "equal-depth billed as occlusion")
    boundary = Fraction(33, 16)
    zero_area = [(boundary, base, front), (boundary + small, base, front), (boundary, base + small, front)]
    require(overlap_on_selection(zero_area, direction, height, rectangle, transform) == 0, "edge contact billed as positive area")
    same_instance_face = len(meshes[target_index][3])
    require(same_instance_face == 2, "unexpected appended source face index")
    return {
        "scope": "derived_geometry_independent_of_PNG_and_producer_controls",
        "TOP_tiny_positive_partial": {
            "vertices_world_m": [list(map(str, row)) for row in small_triangle], "area": str(area),
            "selection_fraction": str(area * 64), "same_object_index_if_appended": target_index,
            "same_object_unselected_source_triangle_if_appended": same_instance_face,
        },
        "TOP_equal_depth_occlusion_area": "0",
        "TOP_edge_touch_occlusion_area": "0",
    }


def main(run, output):
    archive_path = run / "ORIGINAL_RUNTIME.zip"
    index = json.loads(INDEX.read_bytes())
    require(sha(archive_path.read_bytes()) == index["archive"]["sha256"] == ARCHIVE_SHA, "original runtime ZIP changed")
    with ZipFile(archive_path) as archive:
        archive_evidence = ArchivedRun(run, index, archive)
        producer = archive_evidence.document("product_full/call_004/SERVICE_RESULT.json")
        meshes, terminal = verify_sources(archive_evidence, producer)
        brief, png, cli_id = verify_line_packets(archive_evidence, producer)
        blockers, target_index, selected = audit_blockers(producer, meshes)
        frame = verify_frame(archive_evidence, producer, brief, png, terminal, target_index, selected)
        result = {
            "historical_fixture": "ac593f97 P1 call 4", "original_runtime_sha256": ARCHIVE_SHA,
            "original_runtime_index_sha256": sha(INDEX.read_bytes()), "cli_tool_item": cli_id,
            "capture": producer["binding"]["capture_state"], "document_epoch": producer["binding"]["document_epoch"],
            "current_region": producer["region_ref"], "source_triangle_count_per_object": [len(mesh[3]) for mesh in meshes],
            "first_blockers_passed_independent_exact_reconstruction": len(blockers), "first_blockers": blockers,
            "single_actual_SCENE_sample": frame, "derived_controls": control_truth(producer, meshes, target_index),
            "checked_original_member_count": len(archive_evidence.checked),
            "checked_original_members": list(archive_evidence.checked.values()),
        }
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Independent current source, transport and frame passed: {len(blockers)}/6 exact geometric directions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=RUN, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    main(args.run, args.output)
