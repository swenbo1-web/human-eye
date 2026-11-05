"""Independent native-geometry and pixel audit for the frozen VG fixtures.

The verifier never calls VG's camera, clipping, projection, or visibility
helpers. It consumes the encoded HUD, pre-overlay readback, and saved camera
records. Blender's BVHTree independently supplies the first surface hit.
"""

from dataclasses import replace
from hashlib import sha256
from math import floor
import struct
import zlib

import numpy as np

SIZE = 512
EPS32 = np.finfo(np.float32).eps
CAMERA_TOLERANCE = 8 * EPS32
FIXED_DIRECTION = np.array((1., -1., 1.)) / np.sqrt(3.)
TARGET_COLORS = ((.82, .24, .15, 1.), (.16, .60, .90, 1.))
OBSTACLE = (.36, .40, .45, 1.)
BACKGROUND = (.08, .10, .14, 1.)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PIXEL_ERROR = 1


def _rgba(color):
    return np.rint(255 * np.asarray(color)).astype(np.int16)


def _same_color(pixel, expected):
    return bool(np.all(np.abs(pixel.astype(np.int16) - expected) <= PIXEL_ERROR))


def _paeth(a, b, c):
    guess = a + b - c
    da, db, dc = abs(guess - a), abs(guess - b), abs(guess - c)
    if da <= db and da <= dc:
        return a
    return b if db <= dc else c


def decode_png(png):
    """Decode the PNG independently of Blender's image writer and GPU buffer."""
    if not png.startswith(PNG_MAGIC):
        raise ValueError("PNG signature missing")
    offset = len(PNG_MAGIC)
    compressed = []
    width = height = channels = None
    while offset + 12 <= len(png):
        length, kind = struct.unpack_from(">I4s", png, offset)
        start = offset + 8
        data = png[start:start + length]
        checksum = struct.unpack_from(">I", png, start + length)[0]
        if zlib.crc32(kind + data) != checksum:
            raise ValueError("invalid PNG CRC")
        offset += length + 12
        if kind == b"IHDR":
            width, height, bits, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if bits != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise ValueError("expected non-interlaced 8-bit RGB or RGBA PNG")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            compressed.append(data)
        elif kind == b"IEND":
            break
    if (width, height) != (2 * SIZE, SIZE) or channels is None:
        raise ValueError("PNG is not a 1024x512 dual panel")
    stride = width * channels
    raw = zlib.decompress(b"".join(compressed))
    if len(raw) != height * (stride + 1):
        raise ValueError("invalid PNG scanline lengths")
    pixels = np.empty((height, stride), dtype=np.uint8)
    above = bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind = raw[start]
        data = raw[start + 1:start + stride + 1]
        if kind == 0:
            decoded = data
        elif kind == 1:
            samples = np.frombuffer(data, dtype=np.uint8).reshape(width, channels)
            decoded = np.cumsum(samples, axis=0, dtype=np.uint8).tobytes()
        elif kind == 2:
            decoded = (np.frombuffer(data, dtype=np.uint8) +
                       np.frombuffer(above, dtype=np.uint8)).tobytes()
        elif kind in (3, 4):
            decoded = bytearray(stride)
            for i, value in enumerate(data):
                left = decoded[i - channels] if i >= channels else 0
                up_left = above[i - channels] if i >= channels else 0
                predictor = ((left + above[i]) // 2 if kind == 3 else
                             _paeth(left, above[i], up_left))
                decoded[i] = (value + predictor) & 255
        else:
            raise ValueError("unknown PNG scanline filter")
        pixels[y] = np.frombuffer(decoded, dtype=np.uint8)
        above = decoded
    pixels = pixels.reshape(height, width, channels)
    if channels == 4:
        return pixels
    return np.concatenate((pixels, np.full((height, width, 1), 255, dtype=np.uint8)), axis=2)


def _forged_png(pixels):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data)))
    rows = b"".join(b"\0" + row.tobytes() for row in pixels)
    header = struct.pack(">IIBBBBB", 2 * SIZE, SIZE, 8, 6, 0, 0, 0)
    return PNG_MAGIC + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _source_snapshot(fixture):
    """Read original Blender objects, independently of the borrowed RB arrays."""
    snapshot = {}
    for object_id, obj in fixture.objects.items():
        mesh = obj.data
        coords = np.empty(3 * len(mesh.vertices), dtype=np.float32)
        mesh.vertices.foreach_get("co", coords)
        indices = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", indices)
        snapshot[object_id] = (
            obj.as_pointer(), obj.name, mesh.as_pointer(), bool(obj.hide_render),
            bool(obj.hide_viewport), tuple(obj.color),
            tuple((slot.name, tuple(slot.material.diffuse_color) if slot.material else None)
                  for slot in obj.material_slots),
            tuple(tuple(row) for row in obj.matrix_world),
            sha256(coords.tobytes()).hexdigest(), sha256(indices.tobytes()).hexdigest(),
            tuple((p.loop_start, p.loop_total, p.material_index) for p in mesh.polygons),
        )
    return (
        fixture.scene.frame_current,
        fixture.scene.unit_settings.scale_length,
        tuple(sorted(obj.as_pointer() for obj in fixture.scene.objects if obj.type == "MESH")),
        snapshot,
    )


def _native_meshes(fixture):
    import bpy

    result = {}
    with bpy.context.temp_override(scene=fixture.scene, view_layer=fixture.scene.view_layers[0]):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for object_id, obj in fixture.objects.items():
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.data
            coordinates = np.empty((len(mesh.vertices), 3), dtype=np.float32)
            mesh.vertices.foreach_get("co", coordinates.reshape(-1))
            transform = np.asarray(evaluated.matrix_world, dtype=np.float64)
            world = (coordinates @ transform[:3, :3].T + transform[:3, 3]) * fixture.scale_length
            triangles = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", triangles.reshape(-1))
            result[object_id] = world, triangles
    return result


def _clip_polygon(triangle, point, normal):
    """Clip an original triangle to the closed declared halfspace in float64."""
    signed = (triangle - point) @ normal
    polygon = []
    for previous, current in ((2, 0), (0, 1), (1, 2)):
        a, b = signed[previous], signed[current]
        if (a <= 0) != (b <= 0):
            weight = a / (a - b)
            polygon.append(triangle[previous] + weight * (triangle[current] - triangle[previous]))
        if b <= 0:
            polygon.append(triangle[current])
    return polygon


class _RayOracle:
    def __init__(self, meshes, section=None):
        from mathutils.bvhtree import BVHTree

        positions = []
        triangles = []
        self.owners = []
        self.counts = {object_id: 0 for object_id in meshes}
        for object_id, (vertices, source_triangles) in meshes.items():
            for face, indices in enumerate(source_triangles):
                triangle = vertices[indices]
                polygon = triangle if section is None else _clip_polygon(triangle, *section)
                for j in range(1, len(polygon) - 1):
                    a, b, c = polygon[0], polygon[j], polygon[j + 1]
                    if not np.any(np.cross(b - a, c - a)):
                        continue
                    start = len(positions)
                    positions.extend((a, b, c))
                    triangles.append((start, start + 1, start + 2))
                    self.owners.append((object_id, face))
                    self.counts[object_id] += 1
        self.bvh = BVHTree.FromPolygons(positions, triangles, all_triangles=True)

    def cast(self, camera, x, y):
        from mathutils import Vector

        origin = camera.unproject(x, y, -1.)
        point, _, index, _ = self.bvh.ray_cast(
            Vector(origin), Vector(camera.ray_direction), camera.ray_length
        )
        if index is None:
            return None, None, None
        owner, face = self.owners[index]
        return owner, face, float(-(camera.view[2, :3] @ np.asarray(point) + camera.view[2, 3]))


class SceneOracle:
    """Retain facts before either renderer observes the scene."""

    def __init__(self, fixture):
        self.source_snapshot = _source_snapshot(fixture)
        self.meshes = _native_meshes(fixture)
        self.captured_meshes = {
            object_id: (np.array(mesh.world_m), np.array(mesh.triangles),
                        tuple(mesh.appearance.object_color))
            for object_id, mesh in fixture.meshes.items()
        }
        self.positions = np.concatenate([coords for coords, _ in self.meshes.values()])
        self.max_side = float(np.ptp(self.positions, axis=0).max())
        self.depth_tolerance = float(8 * EPS32 * self.max_side)
        self.matches_rb = all(
            np.allclose(vertices, self.captured_meshes[object_id][0], rtol=0,
                        atol=8 * np.finfo(np.float64).eps * self.max_side)
            and np.array_equal(triangles, self.captured_meshes[object_id][1])
            for object_id, (vertices, triangles) in self.meshes.items()
        )
        self.palette = {object_id: _rgba(OBSTACLE) for object_id in self.meshes}
        self.palette.update(zip(fixture.target_ids, map(_rgba, TARGET_COLORS)))
        self.palette[None] = _rgba(BACKGROUND)
        self.palette_matches_rb = all(
            _same_color(_rgba(mesh.appearance.object_color), self.palette[object_id])
            for object_id, mesh in fixture.meshes.items()
        )
        self.original = _RayOracle(self.meshes)

    def unchanged(self, fixture):
        return self.source_snapshot == _source_snapshot(fixture) and all(
            np.array_equal(vertices, fixture.meshes[object_id].world_m) and
            np.array_equal(triangles, fixture.meshes[object_id].triangles) and
            color == tuple(fixture.meshes[object_id].appearance.object_color)
            for object_id, (vertices, triangles, color) in self.captured_meshes.items()
        )


def _close(first, second, atol=CAMERA_TOLERANCE):
    return bool(np.allclose(first, second, atol=atol, rtol=CAMERA_TOLERANCE))


def _blender_projection(rna):
    """Read Blender's projection for the recorded camera settings anew."""
    import bpy

    data = bpy.data.cameras.new("VG verifier")
    obj = bpy.data.objects.new("VG verifier", data)
    try:
        data.type = rna["type"]
        data.ortho_scale = rna["ortho_scale"]
        data.shift_x = rna["shift_x"]
        data.shift_y = rna["shift_y"]
        data.clip_start = rna["clip_start"]
        data.clip_end = rna["clip_end"]
        return np.array(obj.calc_matrix_camera(
            bpy.context.evaluated_depsgraph_get(), x=SIZE, y=SIZE, scale_x=1., scale_y=1.
        ))
    finally:
        bpy.data.objects.remove(obj)
        bpy.data.cameras.remove(data)


class _Camera:
    def __init__(self, record, scale):
        rna = record["rna"]
        gpu = record["gpu"]
        world = np.asarray(rna["matrix_world"], dtype=np.float64).copy()
        world[:3, 3] *= scale
        self.center = world[:3, 3]
        self.backward = world[:3, 2]
        self.near = rna["clip_start"] * scale
        self.far = rna["clip_end"] * scale
        self.width = rna["ortho_scale"] * scale
        self.viewport = list(record["viewport"])
        self.view = np.asarray(gpu["view"], dtype=np.float64)
        self.projection = np.asarray(gpu["projection"], dtype=np.float64)
        self.view_projection = np.asarray(gpu["view_projection"], dtype=np.float64)
        self.inverse = np.linalg.inv(self.view_projection)
        half_ray = self.inverse[:3, 2]
        half_length = np.linalg.norm(half_ray)
        self.ray_direction = half_ray / half_length
        self.ray_length = float(2 * half_length)
        rna_projection = np.asarray(rna["projection"], dtype=np.float64)
        projection_m = rna_projection @ np.diag((1. / scale, 1. / scale, 1. / scale, 1.))
        rotation = world[:3, :3]
        self.agreement = {
            "orthographic": bool(rna["type"] == "ORTHO" and rna["name"]
                                 and 0 < self.near < self.far and self.width > 0),
            "rotation": _close(rotation.T @ rotation, np.eye(3)) and np.linalg.det(rotation) > 0,
            "native_rna_projection": _close(rna_projection, _blender_projection(rna)),
            "gpu_view": _close(self.view, np.linalg.inv(world)),
            "gpu_projection": _close(self.projection, projection_m),
            "gpu_view_projection": _close(self.view_projection, self.projection @ self.view),
        }

    def project(self, positions):
        points = np.column_stack((positions, np.ones(len(positions))))
        clip = points @ self.view_projection.T
        ndc = clip[:, :3] / clip[:, 3, None]
        pixels = (ndc[:, :2] * (1, -1) + 1) * (SIZE / 2) - .5
        depth = -(points @ self.view[2])
        return pixels, depth

    def unproject(self, x, y, ndc_depth):
        clip = ((2 * x + 1) / SIZE - 1, 1 - (2 * y + 1) / SIZE, ndc_depth, 1)
        world = self.inverse @ clip
        return world[:3] / world[3]


def _longest_run(sequence):
    current = longest = 0
    for occupied in sequence:
        current = current + 1 if occupied else 0
        longest = max(current, longest)
    return longest


def _digital_line(a, b):
    """The single 8-connected Bresenham line, including both rounded endpoints."""
    x, y = (floor(v + .5) for v in a)
    last_x, last_y = (floor(v + .5) for v in b)
    dx, dy = abs(last_x - x), -abs(last_y - y)
    sx, sy = (1 if last_x > x else -1), (1 if last_y > y else -1)
    error = dx + dy
    points = []
    while True:
        points.append((x, y))
        if (x, y) == (last_x, last_y):
            return points
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += sx
        if doubled <= dx:
            error += dx
            y += sy


def _neighbors(point):
    u, v = point
    for y in range(max(0, floor(v) - 3), min(SIZE, floor(v) + 5)):
        for x in range(max(0, floor(u) - 3), min(SIZE, floor(u) + 5)):
            if (x - u) ** 2 + (y - v) ** 2 <= 9:
                yield x, y


def _pixel_record(ray, camera, image, x, y):
    owner, face, depth = ray.cast(camera, x, y)
    return {"pixel": [x, y], "object": owner, "face": face, "depth_m": depth,
            "rgba": image[y, x].tolist()}


def _image_rays(camera, image, oracle, ray):
    # Distributed across the viewport independently of witness pixels. At a
    # raster edge the native float32 ray and GPU triangle fill can disagree.
    # A different palette color is excused only at a one-pixel ownership edge.
    grid = [int(x) for x in np.linspace(8, SIZE - 9, 25)]
    mismatches = []
    edge_pixels = 0
    for y in grid:
        for x in grid:
            expected, _, _ = ray.cast(camera, x, y)
            pixel = image[y, x]
            if _same_color(pixel, oracle.palette[expected]):
                continue
            adjacent = ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            if any(_same_color(pixel, oracle.palette[ray.cast(camera, u, v)[0]])
                   for u, v in adjacent):
                edge_pixels += 1
            else:
                mismatches.append({"pixel": [x, y], "object": expected, "rgba": pixel.tolist()})
    return {"pass": not mismatches, "rays": len(grid) ** 2, "edge_pixels": edge_pixels,
            "mismatches": len(mismatches), "examples": mismatches[:16]}


def _hud_binding(hud, bottom, global_points, local_points):
    # Captions and the optional bounded annotations may differ. The image
    # remainder, including clear regions, must be the actual GPU readback.
    yy, xx = np.ogrid[:SIZE, :2 * SIZE]
    mask = np.broadcast_to((yy >= 64) & (yy <= 447), bottom.shape[:2]).copy()
    mask[:, SIZE - 1:SIZE + 1] = False
    for points, offset in ((global_points, 0), (local_points, SIZE)):
        for x, y in points:
            mask &= (xx - x - offset) ** 2 + (yy - y) ** 2 > 32 ** 2
    difference = np.any(hud != bottom, axis=2)
    return bool(np.any(difference & ~mask) and not np.any(difference & mask))


def _witness_points(fixture, oracle, metadata):
    from mathutils import Vector
    from mathutils.geometry import closest_point_on_tri

    witness = fixture.witness
    points = np.array([witness.point_a, witness.point_b], dtype=np.float64)
    expected = ((witness.triangle_a, points[0]), (witness.triangle_b, points[1]))
    valid = bool(metadata["distance_m"] == witness.distance_m and
                 metadata["face_a"] == witness.triangle_a and metadata["face_b"] == witness.triangle_b and
                 np.array_equal([metadata["point_a"], metadata["point_b"]], points) and
                 abs(np.linalg.norm(points[1] - points[0]) - witness.distance_m) <= oracle.depth_tolerance)
    for object_id, (face, point) in zip(fixture.target_ids, expected):
        vertices, triangles = oracle.meshes[object_id]
        if face is None or not 0 <= face < len(triangles):
            valid = False
            continue
        closest = closest_point_on_tri(Vector(point), *map(Vector, vertices[triangles[face]]))
        valid &= np.linalg.norm(np.asarray(closest) - point) <= oracle.depth_tolerance
    return points, bool(valid)


def _audit(fixture, observation, oracle, baseline, relation):
    metadata = observation.metadata
    mode = fixture.mode
    hud = decode_png(observation.png)
    bottom = np.asarray(observation.bottom_rgba)
    if bottom.shape != (SIZE, 2 * SIZE, 4) or bottom.dtype != np.uint8:
        raise ValueError("missing RGBA8 GPU readback")
    scale = fixture.scale_length
    world_points, witness_matches = _witness_points(fixture, oracle, metadata["witness"])
    global_camera = _Camera(metadata["views"]["global"], scale)
    local_camera = _Camera(metadata["views"]["local"], scale)
    global_points, _ = global_camera.project(world_points)
    local_points, witness_depths = local_camera.project(world_points)
    global_scene_pixels, global_depths = global_camera.project(oracle.positions)
    _, local_depths = local_camera.project(oracle.positions)
    local_dir = local_camera.backward
    chosen = metadata["selection"]
    center = world_points.mean(axis=0)
    gap = fixture.witness.distance_m
    expected_width = 32 * gap if relation is None else .25 * oracle.max_side
    checks = {
        "binding": bool(tuple(metadata["target_ids"]) == tuple(fixture.target_ids) and
                        metadata["frame_id"] == fixture.frame_id == fixture.scene.frame_current and
                        len(metadata["mesh_ids"]) == len(oracle.meshes) and
                        set(metadata["mesh_ids"]) == set(oracle.meshes) and
                        metadata["meters_per_blender_unit"] == scale and metadata["mode"] == mode and
                        metadata["method"] == ("fixed" if baseline else "active")),
        "original_source_unchanged": oracle.unchanged(fixture),
        "native_geometry_matches_rb": oracle.matches_rb,
        "palette_matches_rb": oracle.palette_matches_rb,
        "witness_matches_bc": witness_matches,
        "panel_viewports": (global_camera.viewport == [0, 0, SIZE, SIZE]
                            and local_camera.viewport == [SIZE, 0, SIZE, SIZE]),
        "global_camera_matrices": all(global_camera.agreement.values()),
        "local_camera_matrices": all(local_camera.agreement.values()),
        "global_direction": _close(global_camera.backward, FIXED_DIRECTION),
        "local_direction": bool(_close(local_dir, chosen["direction"]) and
                                isinstance(chosen["ray_count"], int) and chosen["ray_count"] >= 0 and
                                (not baseline or _close(local_dir, FIXED_DIRECTION))),
        "local_center_width": (_close(local_camera.width, expected_width, oracle.depth_tolerance) and
                               _close(local_camera.project(center[None, :])[0][0],
                                      ((SIZE - 1) / 2, (SIZE - 1) / 2), .005)),
        "global_complete_frame": bool(np.all(global_scene_pixels >= -.5) and
                                      np.all(global_scene_pixels <= SIZE - .5)),
        "camera_outside_and_full_depth": all(
            camera.near - oracle.depth_tolerance <= depths.min() <= depths.max()
            <= camera.far + oracle.depth_tolerance and depths.min() > 0
            for camera, depths in ((global_camera, global_depths), (local_camera, local_depths))
        ),
        "encoded_hud_binding": _hud_binding(hud, bottom, global_points, local_points),
    }
    if relation is None:
        checks["positive_gap"] = bool(gap > 0 and
                                      abs(gap - fixture.expected_gap_m) <= oracle.depth_tolerance and
                                      metadata["witness"]["status"] == "POSITIVE_GAP")
    else:
        checks["zero_gap_relation"] = gap == 0 and metadata["witness"]["status"] == relation
    section = metadata["section"]
    if mode == "SECTION" and section is not None:
        axis = (world_points[1] - world_points[0]) / gap
        normal = local_dir - (local_dir @ axis) * axis
        normal /= np.linalg.norm(normal)
        declared_normal = np.asarray(section["normal"], dtype=np.float64)
        declared_point = np.asarray(section["point_m"], dtype=np.float64)
        checks["section_declaration"] = (
            section["kept_side"] == "<=0" and _close(normal, declared_normal) and
            _close(center, declared_point, oracle.depth_tolerance) and
            bool(np.max(np.abs((world_points - declared_point) @ declared_normal)) <= oracle.depth_tolerance)
        )
        local_ray = _RayOracle(oracle.meshes, (declared_point, declared_normal))
    else:
        checks["section_declaration"] = mode == "NATURAL" and section is None
        local_ray = oracle.original
    global_image, local_image = bottom[:, :SIZE], bottom[:, SIZE:]
    global_audit = _image_rays(global_camera, global_image, oracle, oracle.original)
    local_audit = _image_rays(local_camera, local_image, oracle, local_ray)
    checks["global_image_rays"] = global_audit["pass"]
    checks["local_image_rays"] = local_audit["pass"]

    difference = local_points[1] - local_points[0]
    separation = float(np.linalg.norm(difference))
    checks["reported_projected_separation"] = abs(chosen["gap_pixels"] - separation) <= .005
    supports = {}
    line = []
    gap_run = 0
    if relation is None:
        checks["projected_witnesses"] = bool(
            np.all(local_points >= -.5) and np.all(local_points < SIZE - .5) and separation >= 4
        )
        for point, object_id in zip(local_points, fixture.target_ids):
            records = []
            for x, y in _neighbors(point):
                record = _pixel_record(local_ray, local_camera, local_image, x, y)
                record["matched"] = (record["object"] == object_id and
                                     _same_color(local_image[y, x], oracle.palette[object_id]))
                records.append(record)
            supports[object_id] = records
        checks["target_surface_pixels"] = all(
            sum(record["matched"] for record in records) >= 2 for records in supports.values()
        )
        if checks["projected_witnesses"]:
            for x, y in _digital_line(*local_points)[1:-1]:
                if not (0 <= x < SIZE and 0 <= y < SIZE):
                    continue
                fraction = np.clip((np.array([x, y]) - local_points[0]) @ difference /
                                   (separation * separation), 0., 1.)
                witness_depth = float(witness_depths[0] + fraction * (witness_depths[1] - witness_depths[0]))
                record = _pixel_record(local_ray, local_camera, local_image, x, y)
                expected = oracle.palette[record["object"]]
                pixel = local_image[y, x]
                record["witness_depth_m"] = witness_depth
                record["is_gap"] = (_same_color(pixel, expected) and
                                    not any(_same_color(pixel, oracle.palette[object_id])
                                            for object_id in fixture.target_ids) and
                                    (record["depth_m"] is None or
                                     record["depth_m"] > witness_depth + oracle.depth_tolerance))
                line.append(record)
        gap_run = _longest_run(record["is_gap"] for record in line)
        checks["consecutive_gap_pixels"] = gap_run >= 3
    else:
        checks["coincident_projection"] = separation <= CAMERA_TOLERANCE
        checks["no_reported_gap_pixels"] = chosen["gap_pixels"] == 0
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "separation_px": separation,
        "max_gap_run": gap_run,
        "mode": mode,
        "method": metadata["method"],
        "witness_pixels": {"global": global_points.tolist(), "local": local_points.tolist(),
                           "hud_local": (local_points + (SIZE, 0)).tolist()},
        "depth_tolerance_m": oracle.depth_tolerance,
        "camera_agreement": {"global": global_camera.agreement, "local": local_camera.agreement},
        "ray_image_agreement": {"global": global_audit, "local": local_audit},
        "retained_triangle_counts": local_ray.counts,
        "target_support": {object_id: sum(record["matched"] for record in records)
                           for object_id, records in supports.items()},
        "witness_neighborhood_rays": supports,
        "interior_gap_rays": line,
    }


def score_observation(fixture, observation, *, oracle, baseline):
    """Check one original PNG, audit readback, recorded cameras, and source."""
    return _audit(fixture, observation, oracle, baseline, relation=None)


def score_no_gap(fixture, observation, *, oracle, baseline):
    """Separate zero-distance semantics and camera check, outside the 24 cases."""
    return _audit(fixture, observation, oracle, baseline, relation=fixture.family)


def negative_controls(fixture, baseline_obs, candidate_obs, *, oracle, blocker_free_observation):
    """Inject distinct forgeries into a valid F2 case and retain failed checks."""
    def fake_pixels(bottom):
        hud = decode_png(candidate_obs.png)
        hud[64:448] = bottom[64:448]
        return replace(candidate_obs, png=_forged_png(hud), bottom_rgba=bottom)

    candidate_bottom = candidate_obs.bottom_rgba
    solid = np.broadcast_to(_rgba(BACKGROUND), candidate_bottom.shape).astype(np.uint8)
    empty_local = candidate_bottom.copy()
    empty_local[:, SIZE:] = _rgba(BACKGROUND)
    cross_only = fake_pixels(empty_local)
    hud = decode_png(cross_only.png)
    view = _Camera(candidate_obs.metadata["views"]["local"], fixture.scale_length)
    witness_points, _ = view.project(np.array([fixture.witness.point_a, fixture.witness.point_b]))
    for point, color in zip(witness_points, TARGET_COLORS):
        x, y = (floor(v + .5) for v in point)
        hud[y - 2:y + 3, x + SIZE] = _rgba(color)
        hud[y, x + SIZE - 2:x + SIZE + 3] = _rgba(color)
    cross_only = replace(cross_only, png=_forged_png(hud))

    altered_camera = dict(candidate_obs.metadata["views"])
    altered_camera["local"] = baseline_obs.metadata["views"]["local"]
    altered_choice = dict(candidate_obs.metadata["selection"])
    altered_choice["direction"] = baseline_obs.metadata["selection"]["direction"]
    wrong_camera = replace(candidate_obs, metadata={
        **candidate_obs.metadata, "views": altered_camera, "selection": altered_choice
    })
    matrix_views = dict(candidate_obs.metadata["views"])
    matrix_local = dict(matrix_views["local"])
    matrix_gpu = dict(matrix_local["gpu"])
    changed_view = np.array(matrix_gpu["view"])
    changed_view[0, 3] += .01
    matrix_gpu["view"] = changed_view.tolist()
    matrix_local["gpu"] = matrix_gpu
    matrix_views["local"] = matrix_local
    wrong_matrix = replace(candidate_obs, metadata={
        **candidate_obs.metadata, "views": matrix_views
    })
    wrong_object = replace(candidate_obs, metadata={
        **candidate_obs.metadata, "target_ids": list(reversed(fixture.target_ids))
    })
    wrong_frame = replace(candidate_obs, metadata={
        **candidate_obs.metadata, "frame_id": fixture.frame_id + 1
    })

    # The baseline F1 and F2 variants share the same gap, targets, and fixed
    # orthographic direction. Substitute F1's real unblocked local panel only.
    without_blocker = baseline_obs.bottom_rgba.copy()
    without_blocker[:, SIZE:] = blocker_free_observation.bottom_rgba[:, SIZE:]
    deleted_blocker_hud = decode_png(baseline_obs.png)
    deleted_blocker_hud[64:448, SIZE:] = without_blocker[64:448, SIZE:]
    deleted_blocker = replace(baseline_obs, png=_forged_png(deleted_blocker_hud),
                              bottom_rgba=without_blocker)

    forgeries = {
        "pure_color": (replace(candidate_obs, png=_forged_png(solid), bottom_rgba=solid),
                       False, "target_surface_pixels"),
        "hud_only_fake_witness": (cross_only, False, "target_surface_pixels"),
        "camera_image_mismatch": (wrong_camera, False, "local_image_rays"),
        "rna_gpu_matrix_mismatch": (wrong_matrix, False, "local_camera_matrices"),
        "wrong_object": (wrong_object, False, "binding"),
        "wrong_frame": (wrong_frame, False, "binding"),
        "undeclared_removed_blocker": (deleted_blocker, True, "local_image_rays"),
    }
    verdicts = {}
    for name, (observation, baseline, expected_check) in forgeries.items():
        result = score_observation(fixture, observation, oracle=oracle, baseline=baseline)
        verdicts[name] = {
            "rejected": not result["passed"] and not result["checks"][expected_check],
            "expected_failed_check": expected_check,
            "failed_checks": [key for key, value in result["checks"].items() if not value],
            "separation_px": result["separation_px"],
            "max_gap_run": result["max_gap_run"],
            "target_support": result["target_support"],
            "local_ray_mismatches": result["ray_image_agreement"]["local"]["mismatches"],
        }
    return verdicts
