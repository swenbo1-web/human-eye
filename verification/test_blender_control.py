"""Native action scenarios and evidence. Run only in a background test process."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import json
from math import hypot, pi
from pathlib import Path
import sys
from time import perf_counter_ns
import unittest

import numpy as np

try:
    import bpy
except ModuleNotFoundError:
    bpy = None

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from human_eye_fast.control import Action, BlenderControl, Goal, SetShapeKey, Translate
from human_eye_fast.fast_affordance_out import (
    AffordancePackage, ClearanceFact, ObjectFact, ObservationFact, encode, public_schema,
)


_KEY = "Actuator"
_TIP_TRAVEL_M = 0.003


@dataclass(frozen=True, slots=True)
class ActionCase:
    scene: object
    objects: dict
    goal: Goal
    command: Translate | SetShapeKey
    expected_before_m: float
    expected_after_m: float


@contextmanager
def _scene(frame, scale):
    if not bpy.app.background:
        raise RuntimeError("AO fixtures require an independent background Blender process")
    scene = bpy.data.scenes.new("AO action fixture")
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = scale
    scene.frame_set(frame)
    try:
        yield scene
    finally:
        objects = list(scene.objects)
        meshes = [obj.data for obj in objects if obj.type == "MESH"]
        bpy.data.scenes.remove(scene)
        for obj in objects:
            bpy.data.objects.remove(obj)
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)


def _mesh_object(scene, name, points, triangles, color):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], triangles)
    obj = bpy.data.objects.new(name, mesh)
    obj.color = color
    scene.collection.objects.link(obj)
    return obj


@contextmanager
def translation_case(*, frame=7, start=(2.0, 0.0, 0.0),
                     delta=(0.025, 0.0, 0.0), scale=1.0, parented=False):
    from verification.vg_fixtures import COLOR_A, COLOR_B, _box

    with _scene(frame, scale) as scene:
        span = (-0.5, 0.5) if parented else (0, 1)
        points, triangles = _box(span, span, span)
        a = _mesh_object(scene, "A", points, triangles, COLOR_A)
        b = _mesh_object(scene, "B", points, triangles, COLOR_B)
        b.location = start
        if parented:
            parent = bpy.data.objects.new("Parent", None)
            scene.collection.objects.link(parent)
            parent.location = (10, 20, 30)
            parent.rotation_euler.z = pi / 2
            a.parent = b.parent = parent
            a.scale = b.scale = (-2.0, 0.5, 1.25)
            before = (start[0] - 2.0) * scale
            after = before + delta[1]
        else:
            before = hypot((start[0] - 1.0) * scale, max(abs(start[1]) - 1.0, 0) * scale)
            after = hypot((start[0] - 1.0) * scale + delta[0],
                          max(abs(start[1] * scale + delta[1]) - scale, 0))
        goal = Goal("B", "A", after, 3e-6 * scale)
        yield ActionCase(scene, {"A": a, "B": b}, goal, Translate(delta), before, after)


@contextmanager
def shape_key_case(*, frame=7, gap=0.004, initial=0.0, target=0.5):
    from verification.vg_fixtures import COLOR_A, COLOR_B, S, TETRA_FACES, TETRA_POINTS

    with _scene(frame, 1.0) as scene:
        points_a = [(S * x, S * y, S * z) for x, y, z in TETRA_POINTS]
        points_b = [(gap - x, y, z) for x, y, z in points_a]
        a = _mesh_object(scene, "A", points_a, TETRA_FACES, COLOR_A)
        b = _mesh_object(scene, "B", points_b, [(i, k, j) for i, j, k in TETRA_FACES], COLOR_B)
        a.shape_key_add(name="Basis", from_mix=False)
        key = a.shape_key_add(name=_KEY, from_mix=False)
        key.data[0].co.x += _TIP_TRAVEL_M
        key.value = initial
        before = gap - initial * _TIP_TRAVEL_M
        after = gap - target * _TIP_TRAVEL_M
        goal = Goal("A", "B", after, 3e-9)
        yield ActionCase(scene, {"A": a, "B": b}, goal, SetShapeKey(_KEY, target), before, after)


def _native_snapshot(case):
    """Read evaluated Blender data independently of RB, including original face order."""
    scene = case.scene
    scale = scene.unit_settings.scale_length
    snapshot = {}
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        graph = bpy.context.evaluated_depsgraph_get()
        for object_id, obj in case.objects.items():
            evaluated = obj.evaluated_get(graph)
            matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
            mesh = evaluated.to_mesh()
            try:
                local = np.asarray([tuple(vertex.co) for vertex in mesh.vertices], dtype=np.float64)
                world = (local @ matrix[:3, :3].T + matrix[:3, 3]) * scale
                mesh.calc_loop_triangles()
                snapshot[object_id] = {
                    "world_vertices_m": world.tolist(),
                    "triangles": [list(triangle.vertices) for triangle in mesh.loop_triangles],
                    "matrix_world_blender": matrix.tolist(),
                }
            finally:
                evaluated.to_mesh_clear()
            if obj.data.shape_keys is not None:
                snapshot[object_id]["key_value"] = obj.data.shape_keys.key_blocks[_KEY].value
            if obj.parent is not None:
                snapshot[object_id]["parent_matrix_world_blender"] = [
                    list(row) for row in obj.parent.evaluated_get(graph).matrix_world
                ]
    return snapshot


def _assert_witness(readback, native, expected, tolerance):
    surface = readback.surface
    assert abs(surface.distance_m - expected) <= tolerance, (surface, expected, tolerance)
    assert abs(np.linalg.norm(np.subtract(surface.point_a, surface.point_b)) -
               surface.distance_m) <= tolerance
    for object_id, face, point in zip(readback.target_ids, (surface.triangle_a, surface.triangle_b),
                                     (surface.point_a, surface.point_b)):
        values = native[object_id]
        assert 0 <= face < len(values["triangles"])
        triangle = np.asarray(values["world_vertices_m"])[values["triangles"][face]]
        origin = triangle[0]
        edges = (triangle[1:] - origin).T
        weights = np.linalg.lstsq(edges, np.asarray(point) - origin, rcond=None)[0]
        assert np.all(weights >= -1e-6) and weights.sum() <= 1 + 1e-6
        np.testing.assert_allclose(origin + edges @ weights, point, rtol=0, atol=tolerance)


def _fact(readback):
    return ObservationFact(
        readback.observation_id, readback.frame_id,
        tuple(ObjectFact(object_id, 0) for object_id in readback.target_ids),
        ClearanceFact(readback.target_ids, readback.surface),
    )


def _select_action(payload, schema, action_id, goal, task_command):
    """Select using the public initial observation and the explicit task command."""
    columns = schema["columns"]
    package = dict(zip(columns["package"], json.loads(payload), strict=True))
    assert package["length_unit"] == "m"
    observation = dict(zip(columns["observation"], package["observations"][0], strict=True))
    clearance = dict(zip(columns["clearance"], observation["clearance"], strict=True))
    targets = tuple(package["object_ids"][i] for i in clearance["target_object_indices"])
    assert targets == (goal.moving_id, goal.reference_id)
    assert abs(clearance["distance_m"] - goal.distance_m) > goal.tolerance_m
    # Zero is an intentionally simple comparison value, independent of execution.
    return Action(action_id, observation["observation_id"], task_command, predicted_delta_m=0.0)


def _run_case(case_id, case, schema):
    controller = BlenderControl(case.scene, case.objects, case.goal)
    start = perf_counter_ns()
    before = controller.observe(f"{case_id}-before")
    observed = perf_counter_ns()
    before_wire = encode(AffordancePackage((_fact(before),)))
    encoded_before = perf_counter_ns()
    action = _select_action(before_wire, schema, case_id, case.goal, case.command)
    selected = perf_counter_ns()
    before_native = _native_snapshot(case)
    start_execute = perf_counter_ns()
    outcome = controller.execute(action, f"{case_id}-after")
    executed = perf_counter_ns()
    assert outcome is not None
    after_wire = encode(AffordancePackage((_fact(before), _fact(outcome.after)), outcome))
    encoded_after = perf_counter_ns()
    after_native = _native_snapshot(case)

    goal, command = case.goal, case.command
    tolerance = goal.tolerance_m
    assert outcome.before == before
    assert outcome.after.observation_id == f"{case_id}-after"
    assert outcome.before.frame_id == outcome.after.frame_id == case.scene.frame_current
    assert outcome.before.target_ids == outcome.after.target_ids == (goal.moving_id, goal.reference_id)
    assert outcome.goal_reached
    _assert_witness(before, before_native, case.expected_before_m, tolerance)
    _assert_witness(outcome.after, after_native, case.expected_after_m, tolerance)
    assert outcome.measured_delta_m == outcome.after.surface.distance_m - before.surface.distance_m
    assert outcome.measured_delta_m != action.predicted_delta_m
    assert after_native[goal.reference_id] == before_native[goal.reference_id]
    moving_before = before_native[goal.moving_id]
    moving_after = after_native[goal.moving_id]
    displacement = np.subtract(moving_after["world_vertices_m"], moving_before["world_vertices_m"])
    if isinstance(command, Translate):
        scale = case.scene.unit_settings.scale_length
        before_matrix = np.asarray(moving_before["matrix_world_blender"])
        after_matrix = np.asarray(moving_after["matrix_world_blender"])
        np.testing.assert_allclose(before_matrix[:3, :3], after_matrix[:3, :3], rtol=0, atol=3e-6)
        np.testing.assert_array_equal(outcome.control_before, before_matrix[:3, 3] * scale)
        np.testing.assert_array_equal(outcome.control_after, after_matrix[:3, 3] * scale)
        expected = np.broadcast_to(command.delta_world_m, displacement.shape)
        terminal_probe = Translate(tuple(-v for v in command.delta_world_m))
    else:
        assert outcome.control_before == moving_before["key_value"]
        assert outcome.control_after == moving_after["key_value"] == command.value
        expected = np.zeros_like(displacement)
        expected[0, 0] = (command.value - moving_before["key_value"]) * _TIP_TRAVEL_M
        terminal_probe = SetShapeKey(command.key_name, 1.0 - command.value if command.value != 0.5 else 0.0)
    np.testing.assert_allclose(displacement, expected, rtol=0, atol=tolerance)
    if case_id in ("T04", "T20"):
        assert before.surface.distance_m == 0.0

    terminal = controller.execute(
        Action(f"{case_id}-terminal-probe", outcome.after.observation_id, terminal_probe),
        f"{case_id}-must-not-be-created",
    )
    assert terminal is None and _native_snapshot(case) == after_native

    timing = {
        "observe_rb_bc_ns": observed - start,
        "encode_initial_ns": encoded_before - observed,
        "consume_select_ns": selected - encoded_before,
        "host_write_rb_bc_outcome_ns": executed - start_execute,
        "encode_outcome_ns": encoded_after - executed,
    }
    return {
        "case_id": case_id,
        "meters_per_blender_unit": case.scene.unit_settings.scale_length,
        "expected_distance_before_m": case.expected_before_m,
        "expected_distance_after_m": case.expected_after_m,
        "public_before": json.loads(before_wire),
        "public_after": json.loads(after_wire),
        "native_before": before_native,
        "native_after": after_native,
        "outcome": asdict(outcome),
        "terminal_probe": asdict(terminal_probe),
        "terminal_probe_zero_write": True,
        "timing": dict(timing, action_chain_ns=sum(timing.values())),
    }


def run_action_cases():
    """Execute and independently score the 20 preregistered supplemental scenarios."""
    if bpy is None:
        raise RuntimeError("AO action cases require Blender")
    translation_inputs = (
        {},
        {"delta": (-0.025, 0, 0)},
        {"delta": (0.125, 0, 0)},
        {"start": (1, 0, 0)},
        {"start": (3, 0, 0), "parented": True, "scale": 0.001, "delta": (0, 0.00025, 0)},
        {"start": (3, 0, 0), "parented": True, "scale": 0.001, "delta": (0, -0.00025, 0)},
        {"start": (3, 0, 0), "parented": True, "scale": 0.01, "delta": (0, 0.0025, 0)},
        {"start": (3, 0, 0), "parented": True, "scale": 0.01, "delta": (0, -0.0025, 0)},
        {"delta": (0, 1.25, 0)},
        {"delta": (0, 1.5, 0)},
        {"delta": (0, 2, 0)},
        {"start": (2, 1.25, 0), "delta": (0, -1.25, 0)},
    )
    shape_inputs = (
        {},
        {"target": 0.25},
        {"target": 0.75},
        {"target": 1.0},
        {"initial": 0.75, "target": 0.25},
        {"initial": 0.5, "target": 0.0},
        {"initial": 1.0, "target": 0.5},
        {"gap": 0.003, "initial": 1.0, "target": 0.5},
    )
    schema = public_schema()
    cases = [(translation_case, inputs) for inputs in translation_inputs]
    cases.extend((shape_key_case, inputs) for inputs in shape_inputs)
    evidence = []
    for index, (factory, inputs) in enumerate(cases, 1):
        case_id = f"T{index:02d}"
        with factory(frame=10 + index, **inputs) as case:
            try:
                evidence.append(_run_case(case_id, case, schema))
            except (AssertionError, ValueError) as error:
                raise AssertionError(f"AO action case {case_id} failed") from error
    return evidence


@unittest.skipUnless(bpy is not None and bpy.app.background, "needs independent Blender")
class NativeActions(unittest.TestCase):
    def test_fixed_action_matrix(self):
        self.assertEqual(len(run_action_cases()), 20)

    def test_stale_observation_cannot_issue_action(self):
        with translation_case() as case:
            controller = BlenderControl(case.scene, case.objects, case.goal)
            controller.observe("original")
            controller.observe("current")
            before = _native_snapshot(case)
            with self.assertRaisesRegex(ValueError, "current observation"):
                controller.execute(Action("stale", "original", case.command), "invalid")
            self.assertEqual(_native_snapshot(case), before)

    def test_empty_surface_never_labels_measured_distance(self):
        with translation_case() as case:
            case.objects["A"].data.clear_geometry()
            controller = BlenderControl(case.scene, case.objects, case.goal)
            initial = controller.observe("empty-before")
            outcome = controller.execute(Action("explicit", "empty-before", case.command), "empty-after")
            self.assertEqual(initial.surface.distance_m, float("inf"))
            self.assertEqual(outcome.after.surface.distance_m, float("inf"))
            self.assertIsNone(outcome.measured_delta_m)
            self.assertFalse(outcome.goal_reached)

    def test_moving_reference_and_prediction_do_not_define_goal_result(self):
        with translation_case() as case:
            moving = case.objects["B"]
            reference = case.objects["A"]
            reference.parent = moving
            reference.location.x = -2.0
            controller = BlenderControl(case.scene, case.objects, case.goal)
            before = controller.observe("linked-before")
            outcome = controller.execute(
                Action("linked", before.observation_id, case.command, predicted_delta_m=0.025),
                "linked-after",
            )
            self.assertAlmostEqual(outcome.before.surface.distance_m, 1.0)
            self.assertAlmostEqual(outcome.after.surface.distance_m, 1.0)
            self.assertAlmostEqual(outcome.measured_delta_m, 0.0)
            self.assertFalse(outcome.goal_reached)


if __name__ == "__main__":
    results = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeActions))
    if not results.wasSuccessful():
        raise RuntimeError("AO native action checks failed")
