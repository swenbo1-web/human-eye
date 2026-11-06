"""Native fixtures with independent evaluated RNA and gap checks."""

from base64 import b64decode
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from math import pi

import numpy as np

from verification.test_bc_acceptance import box, exhaustive_convex_oracle


MOVING = "moving"
REFERENCE = "reference"
_TOLERANCE_M = 8e-9
_OCCLUDER_COLOR = (0.22, 0.78, 0.32, 1.)


@dataclass(frozen=True, slots=True)
class Episode:
    name: str
    scale: float
    target_gap_m: float
    expected_status: str
    expected_before_m: float | None
    expected_after_m: float | None
    delta_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    kind: str = "box"


EPISODES = {
    spec.name: spec for spec in (
        Episode("parented", 0.001, 0.00075, "reached", 0.001, 0.00075, (0., -0.00025, 0.)),
        Episode("parented-rescaled", 0.01, 0.0075, "reached", 0.01, 0.0075, (0., -0.0025, 0.)),
        Episode("already-reached", 0.001, 0.001, "no_action", 0.001, None),
        Episode("nonconvex", 0.001, 0.0006, "reached", 0.001, 0.0006, (0., -0.0004, 0.), "nonconvex"),
        Episode("occluded", 0.001, 0.00075, "reached", 0.001, 0.00075, (0., -0.00025, 0.), "occluded"),
    )
}


@dataclass(frozen=True, slots=True)
class Fixture:
    scene: object
    view_layer: object
    objects: dict
    parent: object
    context: dict

    def snapshot(self):
        import bpy

        result = {}
        with bpy.context.temp_override(scene=self.scene, view_layer=self.view_layer):
            graph = bpy.context.evaluated_depsgraph_get()
            scale = self.scene.unit_settings.scale_length
            for name, obj in (self.objects | self.context).items():
                evaluated = obj.evaluated_get(graph)
                matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
                mesh = evaluated.to_mesh()
                try:
                    local = np.asarray([tuple(v.co) for v in mesh.vertices], dtype=np.float64).reshape(-1, 3)
                    world = (local @ matrix[:3, :3].T + matrix[:3, 3]) * scale
                    mesh.calc_loop_triangles()
                    result[name] = {
                        "matrix_world_bu": matrix.tolist(), "world_vertices_m": world.tolist(),
                        "triangles": [list(tri.vertices) for tri in mesh.loop_triangles],
                    }
                finally:
                    evaluated.to_mesh_clear()
            result["parent_matrix_world_bu"] = np.asarray(
                self.parent.evaluated_get(graph).matrix_world, dtype=np.float64).tolist()
        return result


def _mesh_object(scene, key, points, triangles, color):
    import bpy

    mesh = bpy.data.meshes.new(key)
    mesh.from_pydata(points, [], triangles)
    obj = bpy.data.objects.new(key, mesh)
    obj.color = color
    scene.collection.objects.link(obj)
    return obj


def _notched_prism():
    ring = [(-.5, -.5), (.5, -.5), (.5, .05), (0., .05), (0., .5), (-.5, .5)]
    points = [(x, y, z) for z in (-.5, .5) for x, y in ring]
    faces = [(5, 4, 3, 2, 1, 0), (6, 7, 8, 9, 10, 11)]
    for edge in range(6):
        next_edge = (edge + 1) % 6
        faces.append((edge, next_edge, 6 + next_edge, 6 + edge))
    return points, faces


@contextmanager
def case(spec):
    import bpy

    scene = bpy.data.scenes.new("Close gap verification")
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = spec.scale
    scene.frame_set(7)
    window = bpy.context.window if not bpy.app.background else None
    previous = None if window is None else window.scene
    parent = bpy.data.objects.new("Fixed rotated parent", None)
    scene.collection.objects.link(parent)
    parent.location = (10., 20., 30.)
    parent.rotation_euler.z = pi / 2
    if spec.kind == "nonconvex":
        points, faces = _notched_prism()
    else:
        vertices, triangles = box((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
        points, faces = vertices.tolist(), triangles.tolist()
    moving = _mesh_object(scene, MOVING, points, faces, (0.86, 0.20, 0.10, 1.))
    reference = _mesh_object(scene, REFERENCE, points, faces, (0.08, 0.51, 0.91, 1.))
    moving.parent = reference.parent = parent
    moving.location = (3., 0., 0.)
    moving.scale = reference.scale = (-2., 0.5, 1.25)
    context = {}
    if spec.kind == "occluded":
        vertices, triangles = box((9.35, 20.55, 29.4), (9.66, 22.45, 30.85))
        context["screen"] = _mesh_object(scene, "screen", vertices.tolist(), triangles.tolist(), _OCCLUDER_COLOR)
        vertices, triangles = box((10.18, 21.20, 30.66), (10.8, 22.65, 30.94))
        context["overhang"] = _mesh_object(scene, "overhang", vertices.tolist(), triangles.tolist(),
                                           (0.85, 0.68, 0.15, 1.))
    if window is not None:
        window.scene = scene
    try:
        yield Fixture(scene, scene.view_layers[0], {MOVING: moving, REFERENCE: reference}, parent, context)
    finally:
        if window is not None:
            window.scene = previous
        scene_objects = (moving, reference, *context.values())
        meshes = [obj.data for obj in scene_objects]
        bpy.data.scenes.remove(scene)
        for obj in (*scene_objects, parent):
            bpy.data.objects.remove(obj)
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)


def request_arguments(spec):
    arguments = {"task": "close_gap", "target_gap_m": spec.target_gap_m, "tolerance_m": _TOLERANCE_M}
    if spec.kind == "occluded":
        arguments["image_mode"] = "SECTION"
    return arguments


def _oracle(snapshot):
    moving, reference = snapshot[MOVING], snapshot[REFERENCE]
    if not moving["triangles"] or not reference["triangles"]:
        return None
    return exhaustive_convex_oracle(moving["world_vertices_m"], moving["triangles"],
                                    reference["world_vertices_m"], reference["triangles"])[0]


def _check_gap(actual, expected):
    if expected is None:
        assert actual is None, (actual, expected)
    else:
        assert actual is not None and abs(actual - expected) <= _TOLERANCE_M, (actual, expected)


def validate(spec, result, before, after):
    assert result["status"] == spec.expected_status, result
    expected_write = "written" if spec.expected_after_m is not None else "not_written"
    assert result["write_status"] == expected_write, result
    assert result["goal_reached"] == (spec.name == "already-reached" or expected_write == "written")
    assert all(after[key] == value for key, value in before.items() if key != MOVING), (
        "Reference, context or parent changed"
    )
    initial, final = before[MOVING], after[MOVING]
    assert initial["triangles"] == final["triangles"], "The moving topology changed"
    delta = np.asarray(final["world_vertices_m"]) - np.asarray(initial["world_vertices_m"])
    if expected_write == "written":
        np.testing.assert_allclose(delta, np.broadcast_to(spec.delta_m, delta.shape), rtol=0, atol=_TOLERANCE_M)
        np.testing.assert_allclose(result["delta_world_m"], spec.delta_m, rtol=0, atol=_TOLERANCE_M)
        np.testing.assert_allclose(result["actual_delta_world_m"], spec.delta_m, rtol=0, atol=_TOLERANCE_M)
    else:
        assert initial == final, "The no-write case changed the moving surface"
    np.testing.assert_allclose(np.asarray(final["matrix_world_bu"])[:3, :3],
                               np.asarray(initial["matrix_world_bu"])[:3, :3], rtol=0, atol=5e-7)
    _check_gap(result["before_gap_m"], spec.expected_before_m)
    _check_gap(result["after_gap_m"], spec.expected_after_m)
    oracle_before, oracle_after = _oracle(before), _oracle(after)
    if spec.expected_before_m is not None:
        _check_gap(result["before_gap_m"], oracle_before)
    if spec.expected_after_m is not None:
        _check_gap(result["after_gap_m"], oracle_after)
    return {"independent_before_gap_m": oracle_before, "independent_after_gap_m": oracle_after,
            "maximum_vertex_displacement_m": float(np.linalg.norm(delta, axis=1).max()) if delta.size else 0.0}


def validate_image(spec, result, run_fields, after, *, mode="SECTION"):
    from verification.test_raycast_saccade_gpu import decode_png

    assert spec.kind == "occluded" and not result["isError"], run_fields
    assert run_fields["frame_id"] == 7 and run_fields["observation_id"].endswith("-after")
    text, block = result["content"]
    assert text["type"] == "text" and "structuredContent" not in result
    fields = json.loads(text["text"])
    for key in ("task_id", "frame_id", "observation_id"):
        assert fields[key] == run_fields[key], (key, fields, run_fields)
    image = fields.get("image", fields)
    assert image["status"] == "available" and image["mode"] == mode, image
    assert image["scene_object_ids"] == [MOVING, REFERENCE, "screen", "overhang"], image
    assert image["panels"] == ["scene_context", "witness"], image
    section = image["section"]
    if mode == "SECTION":
        assert section["kept_side"] == "<=0" and abs(np.linalg.norm(section["normal"]) - 1) <= 1e-6
        moving_y = np.asarray(after[MOVING]["world_vertices_m"])[:, 1].min()
        reference_y = np.asarray(after[REFERENCE]["world_vertices_m"])[:, 1].max()
        _check_gap(section["point_m"][1], (moving_y + reference_y) / 2)
    else:
        assert mode == "NATURAL" and section is None, image
    assert block["type"] == "image" and block["mimeType"] == "image/png"
    png = b64decode(block["data"], validate=True)
    pixels = decode_png(png)
    interior = pixels[45:465, :512, :3].astype(np.int16)
    color = np.rint(255 * np.asarray(_OCCLUDER_COLOR[:3])).astype(np.int16)
    visible_context_pixels = int(np.count_nonzero(np.max(np.abs(interior - color), axis=2) <= 3))
    assert visible_context_pixels > 25, "The terminal PNG omits the bound screen in its scene panel"
    return {"png_sha256": sha256(png).hexdigest(), "png_bytes": len(png), "size": [1024, 512],
            "visible_context_pixels": visible_context_pixels, "terminal_frame_id": 7,
            "mode": image["mode"], "section_midpoint_y_m": None if section is None else section["point_m"][1]}
