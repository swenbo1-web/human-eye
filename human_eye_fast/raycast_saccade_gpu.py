"""Orthographic active vision from resident world-meter geometry in Blender."""

from dataclasses import dataclass
from math import cos, hypot, pi, sin
import struct
import zlib

import blf
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


PANEL = 512
BACKGROUND = (0.08, 0.10, 0.14, 1.0)
_FIXED = Vector((1, -1, 1)).normalized()
_ORBIT = tuple((cos(k * pi / 8), sin(k * pi / 8)) for k in (
    0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8
))
_EPS32 = float(np.finfo(np.float32).eps)
_ZERO = (0.0, 0.0, 0.0)


def _png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(payload, zlib.crc32(kind))))


# Preserve the established display/color and resolution semantics. Only the
# lossless scanline representation changes: this renderer is fully opaque.
_PNG_PREFIX = b"\x89PNG\r\n\x1a\n" + _png_chunk(
    b"IHDR", struct.pack(">IIBBBBB", 2 * PANEL, PANEL, 8, 2, 0, 0, 0))
_PNG_PREFIX += b"".join(_png_chunk(kind, bytes.fromhex(payload)) for kind, payload in (
    (b"sRGB", "03"),
    (b"gAMA", "0000b18f"),
    (b"cHRM", "00007a26000080840000fa00000080e8000075300000ea6000003a9800001770"),
    (b"eXIf", "4d4d002a00000018000000480000000100000048000000010002011a00050000000100000008011b0005000000010000001000000000"),
    (b"oFFs", "000000000000000000"),
    (b"pHYs", "00000b1200000b1201"),
))
_PNG_END = _png_chunk(b"IEND", b"")


@dataclass(slots=True)
class PreparedScene:
    """GPU geometry and native ray index rebuilt on explicit fact updates."""

    mesh_ids: tuple
    batch: object
    rays: BVHTree
    triangle_owners: tuple
    face_colors: dict
    center: Vector
    radius: float
    max_side: float


@dataclass(slots=True)
class Observation:
    png: bytes
    metadata: dict
    bottom_rgba: np.ndarray | None


def _surface_shader():
    interface = gpu.types.GPUStageInterfaceInfo("vg_surface")
    interface.smooth("VEC3", "worldPosition")
    interface.flat("VEC4", "baseColor")
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant("MAT4", "viewProjection")
    info.push_constant("VEC3", "sectionPoint")
    info.push_constant("VEC3", "sectionNormal")
    info.vertex_in(0, "VEC3", "position")
    info.vertex_in(1, "VEC4", "color")
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "fragColor")
    info.vertex_source("""
        void main() {
            worldPosition = position;
            baseColor = color;
            gl_Position = viewProjection * vec4(position, 1.0);
        }
    """)
    info.fragment_source("""
        void main() {
            if (dot(sectionNormal, worldPosition - sectionPoint) > 0.0) discard;
            fragColor = vec4(baseColor.rgb, 1.0);
        }
    """)
    return gpu.shader.create_from_info(info)


def _face_colors(mesh):
    appearance = mesh.appearance
    slots = np.asarray([appearance.object_color] + [
        appearance.object_color if slot is None else slot[1]
        for slot in appearance.material_slots
    ], dtype=np.float32)
    if len(slots) == 1:
        return np.broadcast_to(slots, (len(mesh.triangles), 4))
    materials = appearance.polygon_material_indices[appearance.triangle_polygon_indices]
    return slots[materials + 1]


def _camera(name):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    return bpy.data.objects.new(name, data)


def _matrix_rows(matrix):
    return [list(row) for row in matrix]


def _view(camera, depsgraph, center, direction, width, radius, scale, x):
    distance = 2.5 * radius
    rotation = direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
    rotation.translation = (center + distance * direction) / scale
    camera.matrix_world = rotation
    data = camera.data
    data.ortho_scale = width / scale
    data.clip_start = (distance - 1.25 * radius) / scale
    data.clip_end = (distance + 1.25 * radius) / scale
    rna_world = camera.matrix_world.copy()
    world = np.asarray(rna_world, dtype=np.float64)
    world[:3, 3] *= scale
    view = np.linalg.inv(world)
    # Correct the small lateral error from storing a distant camera location
    # in float32 RNA. Orthographic lens shifts keep the viewing rays parallel.
    center_view = view[:2, :3] @ np.asarray(center) + view[:2, 3]
    data.shift_x, data.shift_y = center_view / (data.ortho_scale * scale)
    rna_projection = camera.calc_matrix_camera(depsgraph, x=PANEL, y=PANEL)
    projection = np.asarray(rna_projection, dtype=np.float64)
    projection[:, :3] /= scale
    view_projection = Matrix(projection @ view)
    return view_projection, {
        "viewport": [x, 0, PANEL, PANEL],
        "rna": {
            "name": camera.name, "type": data.type,
            "matrix_world": _matrix_rows(rna_world),
            "ortho_scale": data.ortho_scale, "clip_start": data.clip_start,
            "clip_end": data.clip_end, "shift_x": data.shift_x, "shift_y": data.shift_y,
            "projection": _matrix_rows(rna_projection),
        },
        "gpu": {
            "view": _matrix_rows(Matrix(view)), "projection": _matrix_rows(Matrix(projection)),
            "view_projection": _matrix_rows(view_projection),
        },
    }


def _pixel(matrix, point):
    x, y, _, _ = matrix @ point.to_4d()
    return ((1 + x) * PANEL / 2 - 0.5, (1 - y) * PANEL / 2 - 0.5)


def _transverse(direction, axis):
    return direction - direction.dot(axis) * axis


def _select(prepared, a, b, axis, midpoint, gap, radius, target_ids, section, rank_directions=None):
    # Phase the orbit around the fixed view's perpendicular projection. An
    # exactly axial view leaves the phase free, so use any orthogonal vector.
    u = _transverse(_FIXED, axis)
    u = u.normalized() if u.length_squared > _EPS32**2 else axis.orthogonal().normalized()
    v = axis.cross(u).normalized()
    step = 32 * gap / PANEL
    tol = 8 * _EPS32 * prepared.max_side
    distance = 2.5 * radius
    ray_cast = prepared.rays.ray_cast
    owners = prepared.triangle_owners
    rays = 0
    probes = []
    best_direction, best_score = u, (-1, -1)
    directions = ((c * u + s * v).normalized() for c, s in _ORBIT)
    if rank_directions is not None:
        canonical = tuple(directions)
        directions = map(canonical.__getitem__, rank_directions(canonical))
    for direction in directions:
        start_rays = rays
        forward = -direction
        lift = direction * (0 if section else distance)
        witness_depth = 0 if section else distance
        sideways = direction.cross(axis) * step
        along = axis * step
        open_pixels = 0
        # Keep a pixel of clearance on both sides of the witness line. A ray
        # on the line itself can graze an occluder that covers raster centers.
        for dx, dy in ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)):
            _, _, index, depth = ray_cast(midpoint + lift + dx * along + dy * sideways, forward)
            rays += 1
            if index is not None and (depth <= witness_depth + tol or owners[index] in target_ids):
                break
            open_pixels += 1
        if open_pixels < 9:
            probes.append({"direction": list(direction), "ray_count": rays - start_rays,
                           "aperture_taps": open_pixels, "target_support": 0})
            if (0, open_pixels) > best_score:
                best_direction, best_score = direction, (0, open_pixels)
            continue
        supported = 0
        for point, sign, target in zip((a, b), (-1, 1), target_ids):
            hits = 0
            for dx, dy in ((1, 0), (2, 0), (2, -1), (2, 1), (1, -1), (1, 1)):
                _, _, index, _ = ray_cast(point + lift + sign * dx * along + dy * sideways, forward)
                rays += 1
                hits += index is not None and owners[index] == target
                if hits == 2:
                    supported += 1
                    break
        probes.append({"direction": list(direction), "ray_count": rays - start_rays,
                       "aperture_taps": open_pixels, "target_support": supported})
        if supported == 2:
            return direction, rays, probes
        if (supported, open_pixels) > best_score:
            best_direction, best_score = direction, (supported, open_pixels)
    return best_direction, rays, probes


class VGRenderer:
    """Render dual-panel observations in the calling Blender GPU context."""

    def __init__(self):
        if bpy.app.background:
            gpu.init()
        self.offscreen = gpu.types.GPUOffScreen(2 * PANEL, PANEL, format="RGBA8")
        self.shader = _surface_shader()
        self.hud_shader = gpu.shader.from_builtin("SMOOTH_COLOR")
        self.cameras = (_camera("VG Context"), _camera("VG Witness"))
        self.scanlines = np.empty((PANEL, 1 + 2 * PANEL * 3), dtype=np.uint8)
        self.scanlines[:, 0] = 2  # PNG Up: subtract the preceding top-down row.
        self.rgb_deltas = self.scanlines[:, 1:].reshape(PANEL, 2 * PANEL, 3)
        self.rgb = np.empty((64, 2 * PANEL, 3), dtype=np.uint8)
        self.previous_row = np.empty((2 * PANEL, 3), dtype=np.uint8)

    def prepare(self, meshes):
        positions, colors, polygons, points, owners = [], [], [], [], []
        object_face_colors = {}
        offset = 0
        for object_id, mesh in meshes.items():
            vertices = mesh.world_m
            face_colors = _face_colors(mesh)
            positions.append(vertices[mesh.triangles].reshape(-1, 3))
            colors.append(np.repeat(face_colors, 3, axis=0))
            polygons.append(mesh.triangles + offset)
            points.append(vertices)
            owners.extend([object_id] * len(mesh.triangles))
            object_face_colors[object_id] = face_colors
            offset += len(vertices)
        world = np.concatenate(points)
        lower, upper = world.min(axis=0), world.max(axis=0)
        spans = upper - lower
        return PreparedScene(
            tuple(meshes), batch_for_shader(self.shader, "TRIS", {
                "position": np.concatenate(positions).astype(np.float32),
                "color": np.concatenate(colors),
            }),
            BVHTree.FromPolygons(world.tolist(), np.concatenate(polygons).tolist(), all_triangles=True),
            tuple(owners), object_face_colors, Vector((lower + upper) / 2),
            float(np.linalg.norm(spans)) / 2, float(spans.max()),
        )

    def _surface(self, prepared, matrix, x, section_point, section_normal):
        gpu.state.viewport_set(x, 0, PANEL, PANEL)
        shader = self.shader
        shader.bind()
        shader.uniform_float("viewProjection", matrix)
        shader.uniform_float("sectionPoint", section_point)
        shader.uniform_float("sectionNormal", section_normal)
        prepared.batch.draw(shader)

    def _hud(self, metadata, global_center, local_points, colors):
        positions, rgba = [], []
        slate = (0.04, 0.06, 0.09, 1)
        ink = (0.87, 0.92, 0.98, 1)
        cyan = (0.49, 0.89, 0.97, 1)

        def rect(x0, y0, x1, y1, color):
            # Pixel coordinates here are top-left, while GPU rows are bottom-up.
            corners = ((x0, PANEL-y0), (x1, PANEL-y0), (x1, PANEL-y1), (x0, PANEL-y1))
            positions.extend(corners[i] for i in (0, 1, 2, 0, 2, 3))
            rgba.extend([color] * 6)

        rect(0, 0, 2 * PANEL, 44, slate)
        rect(0, 465, 2 * PANEL, PANEL, slate)
        rect(PANEL, 0, PANEL + 1, PANEL, cyan)
        rect(14, 478, 24, 488, colors[0])
        rect(14, 493, 24, 503, colors[1])
        x, y = global_center
        for dx in (-12, 12):
            rect(x + dx, y - 12, x + dx + 1, y + 13, cyan)
        for dy in (-12, 12):
            rect(x - 12, y + dy, x + 13, y + dy + 1, cyan)
        if local_points is not None:
            for (x, y), sign, color in zip(local_points, (-1, 1), colors):
                x += PANEL
                rect(x - 1, y - 14, x + 1, y - 7, color)
                rect(x - 1, y + 7, x + 1, y + 14, color)
                rect(x + min(0, sign*8), y + 13, x + max(1, sign*8), y + 15, color)

        ortho = Matrix(((1 / PANEL, 0, 0, -1), (0, 2 / PANEL, 0, -1),
                        (0, 0, -1, 0), (0, 0, 0, 1)))
        witness = metadata["witness"]
        target_a, target_b = metadata["target_ids"]
        section = metadata["section"]
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(ortho)
            batch_for_shader(self.hud_shader, "TRIS", {"pos": positions, "color": rgba}).draw(self.hud_shader)

            def label(x, y, size, message, color=ink):
                blf.size(0, size)
                blf.position(0, x, PANEL - y, 0)
                blf.color(0, *color)
                blf.draw(0, message)

            label(14, 19, 15, "SCENE CONTEXT  /  01", cyan)
            label(14, 36, 12, f"Frame {metadata['frame_id']}   |   Outlined location -> panel 02")
            label(526, 19, 15, f"WITNESS DETAIL  /  02   {metadata['mode']}", cyan)
            label(526, 36, 12, f"{witness['status']}   |   Distance {witness['distance_m']!r} m")
            label(31, 487, 12, f"A  {target_a}   /   face {witness['face_a']}")
            label(31, 502, 12, f"B  {target_b}   /   face {witness['face_b']}")
            width = metadata["views"]["local"]["rna"]["ortho_scale"] * metadata["meters_per_blender_unit"]
            label(526, 486, 12, f"Orthographic width {width:.9g} m   |   source frame {metadata['frame_id']}")
            if section:
                normal = ", ".join(f"{x:+.4f}" for x in section["normal"])
                label(526, 503, 12, f"Plane through witness midpoint   |   n=({normal})   |   keep <= 0")
            else:
                label(526, 503, 12, "Original geometry  /  no section")

    def observe(self, prepared, witness, *, target_ids, frame_id, scale_length,
                mode="NATURAL", method="active", audit=False, relation=None, rank_directions=None):
        gap = witness.distance_m
        a, b = Vector(witness.point_a), Vector(witness.point_b)
        midpoint = (a + b) / 2
        radius = prepared.radius + (midpoint - prepared.center).length
        axis = (b - a).normalized() if gap > 0 else None
        direction, count, probes = _FIXED, 0, []
        section = None
        if mode == "SECTION" and axis is None:
            raise ValueError("SECTION requires a positive-distance witness")
        if method == "active" and axis is not None:
            direction, count, probes = _select(
                prepared, a, b, axis, midpoint, gap, radius, target_ids, mode == "SECTION",
                rank_directions)
        if mode == "SECTION":
            normal = _transverse(direction, axis).normalized()
            if not normal.length_squared:
                raise ValueError("SECTION requires a direction transverse to the gap")
            section = {"point_m": list(midpoint), "normal": list(normal), "kept_side": "<=0"}
        depsgraph = bpy.context.evaluated_depsgraph_get()
        global_matrix, global_view = _view(self.cameras[0], depsgraph, prepared.center, _FIXED,
                                          2.6 * prepared.radius, prepared.radius, scale_length, 0)
        local_matrix, local_view = _view(self.cameras[1], depsgraph, midpoint, direction,
                                        32 * gap if gap else 0.25 * prepared.max_side,
                                        radius, scale_length, PANEL)
        pa, pb = _pixel(local_matrix, a), _pixel(local_matrix, b)
        metadata = {
            "target_ids": list(target_ids), "mesh_ids": list(prepared.mesh_ids), "frame_id": frame_id,
            "meters_per_blender_unit": scale_length, "mode": mode, "method": method,
            "section": section, "witness": {
                "point_a": list(witness.point_a), "point_b": list(witness.point_b),
                "face_a": witness.triangle_a, "face_b": witness.triangle_b, "distance_m": gap,
                "status": "POSITIVE_GAP" if gap else relation or "ZERO_GAP",
            },
            "selection": {
                "direction": list(direction), "ray_count": count, "probes": probes,
                "gap_pixels": hypot(pa[0] - pb[0], pa[1] - pb[1]),
            },
            "views": {"global": global_view, "local": local_view},
        }
        colors = [(*prepared.face_colors[key][face, :3], 1.0)
                  for key, face in zip(target_ids, (witness.triangle_a, witness.triangle_b))]
        bottom = None
        with self.offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            previous_test = gpu.state.depth_test_get()
            previous_mask = gpu.state.depth_mask_get()
            previous_blend = gpu.state.blend_get()
            try:
                gpu.state.blend_set("NONE")
                gpu.state.face_culling_set("NONE")
                gpu.state.depth_test_set("LESS")
                gpu.state.depth_mask_set(True)
                fb.clear(color=BACKGROUND, depth=1.0)
                self._surface(prepared, global_matrix, 0, _ZERO, _ZERO)
                self._surface(prepared, local_matrix, PANEL, midpoint, section["normal"] if section else _ZERO)
                if audit:
                    data = fb.read_color(0, 0, 2 * PANEL, PANEL, 4, 0, "UBYTE")
                    bottom = np.asarray(memoryview(data))[::-1].copy()
                gpu.state.viewport_set(0, 0, 2 * PANEL, PANEL)
                gpu.state.depth_test_set("NONE")
                gpu.state.depth_mask_set(False)
                self._hud(metadata, _pixel(global_matrix, midpoint), (pa, pb) if gap else None, colors)
                data = fb.read_color(0, 0, 2 * PANEL, PANEL, 4, 0, "UBYTE")
            finally:
                gpu.state.depth_test_set(previous_test)
                gpu.state.depth_mask_set(previous_mask)
                gpu.state.blend_set(previous_blend)
        # Compact one stripe at a time: vectorized Up filtering gets contiguous
        # RGB while the scratch buffer stays smaller than a full source image.
        source = np.asarray(memoryview(data))[::-1, :, :3]
        for start in range(0, PANEL, len(self.rgb)):
            stop = start + len(self.rgb)
            np.copyto(self.rgb, source[start:stop])
            if start:
                np.subtract(self.rgb[0], self.previous_row, out=self.rgb_deltas[start])
            else:
                self.rgb_deltas[0] = self.rgb[0]
            np.subtract(self.rgb[1:], self.rgb[:-1], out=self.rgb_deltas[start+1:stop])
            self.previous_row[:] = self.rgb[-1]
        compressed = zlib.compress(self.scanlines, 1)
        png = _PNG_PREFIX + _png_chunk(b"IDAT", compressed) + _PNG_END
        return Observation(png, metadata, bottom)

    def close(self):
        self.offscreen.free()
        self.rgb = self.rgb_deltas = self.scanlines = self.previous_row = None
        for camera in self.cameras:
            data = camera.data
            bpy.data.objects.remove(camera)
            bpy.data.cameras.remove(data)
