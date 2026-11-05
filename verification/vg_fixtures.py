"""Frozen VG scenes with real Blender evaluated geometry and RB → BC facts."""

from dataclasses import dataclass
from math import cos, radians, sin, tau
from time import perf_counter_ns

import bpy

from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
from human_eye_fast.fast_bvh_clearance import SurfaceDistance, SurfaceIndex, surface_distance
from human_eye_fast.resident_bridge import ResidentMesh


S = 0.01
VARIANTS = ((0, 0.000025), (45, 0.0001), (90, 0.0004), (135, 0.004))
SCENE_COUNT = 24
COLOR_A = (0.82, 0.24, 0.15, 1.0)
COLOR_B = (0.16, 0.60, 0.90, 1.0)
COLOR_OBSTACLE = (0.36, 0.40, 0.45, 1.0)
TETRA_POINTS = ((0, 0, 0), (-4, -2, -2), (-4, 2, -2), (-2, 0, -4))
TETRA_FACES = ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))


@dataclass(frozen=True, slots=True)
class VGFixture:
    scene_id: int
    family: str
    angle_deg: int
    expected_gap_m: float
    mode: str
    scene: bpy.types.Scene
    scale_length: float
    frame_id: int
    target_ids: tuple[str, str]
    objects: dict[str, bpy.types.Object]
    meshes: dict[str, ResidentMesh]
    witness: SurfaceDistance
    build_ns: int
    rb_ns: int
    bc_ns: int

    def close(self):
        """Release fixture-owned native data after observation resources are closed."""
        mesh_data = [obj.data for obj in self.objects.values()]
        materials = {material for mesh in mesh_data for material in mesh.materials}
        bpy.data.scenes.remove(self.scene)
        for obj in self.objects.values():
            bpy.data.objects.remove(obj)
        for mesh in mesh_data:
            bpy.data.meshes.remove(mesh)
        for material in materials:
            bpy.data.materials.remove(material)


def _triangulate(quads):
    return [triangle for a, b, c, d in quads for triangle in ((a, b, c), (a, c, d))]


def _box(x, y, z):
    x0, x1 = x
    y0, y1 = y
    z0, z1 = z
    points = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )
    faces = _triangulate((
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ))
    return points, faces


def _centered_box(center, size):
    return _box(*(tuple((value - width / 2, value + width / 2))
                  for value, width in zip(center, size)))


def _sleeve():
    segments = 64
    circle = [(cos(tau * j / segments), sin(tau * j / segments)) for j in range(segments)]
    points = [(radius * x, radius * y, z)
              for radius, z in ((10, 0), (10, 12), (8, 0), (8, 12)) for x, y in circle]
    outer_top, inner_bottom, inner_top = segments, 2 * segments, 3 * segments
    quads = []
    for j in range(segments):
        k = (j + 1) % segments
        quads.extend((
            (j, k, outer_top + k, outer_top + j),
            (inner_bottom + k, inner_bottom + j, inner_top + j, inner_top + k),
            (outer_top + j, outer_top + k, inner_top + k, inner_top + j),
            (k, j, inner_bottom + j, inner_bottom + k),
        ))
    return points, _triangulate(quads)


def _obstacles(family):
    if family == "F2":
        yield "Board", _box((9.5, 10.5), (-12, 12), (-10, 16))
    elif family == "F3":
        yield "Canopy", _centered_box((0, 0, 8), (18, 18, 1))
        yield "Pillar-1", _centered_box((10, -6, 2), (2, 2, 12))
        yield "Pillar-2", _centered_box((-6, -10, 2), (2, 2, 12))
    elif family == "F4":
        yield "Wall-X-", _box((-6.5, -5.5), (-12, 12), (-4, 12))
        yield "Wall-X+", _box((5.5, 6.5), (-12, 12), (-4, 12))
        yield "Roof", _box((-6.5, 6.5), (-12, 12), (12, 13))
    elif family == "F5":
        yield "Sleeve", _sleeve()
    elif family == "F6":
        # Disjoint wall interiors tile the shell. Faces meet on the seams.
        outer, inner = (-10, 10), (-8, 8)
        for side, span in (("-", (-10, -8)), ("+", (8, 10))):
            yield f"Shell-X{side}", _box(span, outer, outer)
            yield f"Shell-Y{side}", _box(inner, span, outer)
            yield f"Shell-Z{side}", _box(inner, inner, span)


def _material(name, color):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    return material


def _object(scene, name, points, faces, material, angle):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj.color = material.diffuse_color
    obj.rotation_euler.z = angle
    scene.collection.objects.link(obj)
    return obj


def _build(scene_id, family, angle_deg, separation_m, mode):
    start = perf_counter_ns()
    name = f"VG-{scene_id:02d}"
    scene = bpy.data.scenes.new(name)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_set(scene_id + 1)
    angle = radians(angle_deg)

    target_ids = (f"{name}-A", f"{name}-B")
    a_id, b_id = target_ids
    points_a = [(S * x, S * y, S * z) for x, y, z in TETRA_POINTS]
    points_b = [(separation_m - x, y, z) for x, y, z in points_a]
    faces_b = [(a, c, b) for a, b, c in TETRA_FACES]
    material_a = _material(a_id, COLOR_A)
    material_b = _material(b_id, COLOR_B)
    objects = {
        a_id: _object(scene, a_id, points_a, TETRA_FACES, material_a, angle),
        b_id: _object(scene, b_id, points_b, faces_b, material_b, angle),
    }

    obstacles = list(_obstacles(family))
    if obstacles:
        material = _material(f"{name}-Obstacle", COLOR_OBSTACLE)
        for label, (points, faces) in obstacles:
            object_id = f"{name}-{label}"
            shifted_points = [(S * x + separation_m / 2, S * y, S * z) for x, y, z in points]
            objects[object_id] = _object(scene, object_id, shifted_points, faces, material, angle)
    build_ns = perf_counter_ns() - start

    start = perf_counter_ns()
    bridge = BlenderResidentBridge()
    scale_length = scene.unit_settings.scale_length
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        graph = bpy.context.evaluated_depsgraph_get()
        meshes = {key: bridge.capture(key, obj, graph, scale_length) for key, obj in objects.items()}
    rb_ns = perf_counter_ns() - start

    start = perf_counter_ns()
    a, b = meshes[a_id], meshes[b_id]
    index_a = SurfaceIndex(a.world_m, a.triangles)
    index_b = SurfaceIndex(b.world_m, b.triangles)
    witness = surface_distance(index_a, index_b)
    bc_ns = perf_counter_ns() - start
    return VGFixture(
        scene_id, family, angle_deg, max(0.0, separation_m), mode, scene, scale_length,
        scene.frame_current, target_ids, objects, meshes, witness, build_ns, rb_ns, bc_ns,
    )


def build_fixture(scene_id: int) -> VGFixture:
    """Build a fresh case in frozen family-major and then variant order."""
    if not 0 <= scene_id < SCENE_COUNT:
        raise ValueError(f"Expected a frozen case ID in [0, {SCENE_COUNT}), got {scene_id}")
    family_index, variant = divmod(scene_id, len(VARIANTS))
    family = f"F{family_index + 1}"
    angle_deg, gap_m = VARIANTS[variant]
    return _build(scene_id, family, angle_deg, gap_m, "SECTION" if family == "F6" else "NATURAL")


def build_no_gap_fixture(kind: str) -> VGFixture:
    """Build a separate contact or overlap case outside the frozen 24."""
    scene_id, separation_m = {"CONTACT": (24, 0.0), "INTERSECTION": (25, -S)}[kind]
    return _build(scene_id, kind, 0, separation_m, "NATURAL")
