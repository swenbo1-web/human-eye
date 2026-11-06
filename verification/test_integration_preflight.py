"""Portable fixture checks and bounded Blender smoke for the thin reference."""

from argparse import ArgumentParser
from collections import Counter
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from struct import unpack
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verification.integration_fixtures import build_fixture, fixture_manifest
from verification.test_bc_acceptance import surface_tolerance


MAIN_PROBES = (0, 1, 20)
CONTROL_PROBES = ("contact-zero", "empty-reference", "already-reached", "nonbasis-key")


def _world_arrays(fixture, *, after=False):
    """Independent fixture-space evaluation in meters, with no host or bridge."""
    items = {item.object_id: item for item in (*fixture.parents, *fixture.meshes)}
    moving = fixture.target_ids[0]
    command = fixture.command

    def world(object_id):
        item = items[object_id]
        local = np.asarray(item.local_matrix_m)
        matrix = local.copy() if item.parent_id is None else world(item.parent_id) @ local
        if after and object_id == moving and command is not None and command.kind == "translate":
            matrix[:3, 3] += command.delta_world_m
        return matrix

    result = {}
    for mesh in fixture.meshes:
        vertices = np.asarray(mesh.vertices_local_m, dtype=np.float64).reshape(-1, 3)
        if mesh.shape_basis_local_m is not None:
            q = command.target_value if after else command.control_before
            vertices = vertices + q * np.asarray(mesh.shape_basis_local_m)
        matrix = world(mesh.object_id)
        result[mesh.object_id] = (vertices @ matrix[:3, :3].T + matrix[:3, 3],
                                  np.asarray(mesh.triangles, dtype=np.int32).reshape(-1, 3))
    return result


def _pair_truth(meshes, target_ids):
    """Prove a matching lower and upper bound for the analytic tip fixtures."""
    a, b = (meshes[key] for key in target_ids)
    if len(a[1]) == 0 or len(b[1]) == 0:
        return float("inf"), 0.
    assert (a[1] == 0).any() and (b[1] == 0).any()
    origin, tip = a[0][0], b[0][0]
    axis = tip - origin
    distance = float(np.linalg.norm(axis))
    tolerance = surface_tolerance(*a, *b)
    if distance:
        axis /= distance
        front_a = ((a[0][np.unique(a[1])] - origin) @ axis).max()
        front_b = ((b[0][np.unique(b[1])] - origin) @ axis).min()
        assert abs(front_b - front_a - distance) <= tolerance
    return distance, tolerance


class IntegrationDesignPreflight(unittest.TestCase):
    def test_manifest_group_and_command_coverage(self):
        main = fixture_manifest(partition="main")
        control = fixture_manifest(partition="control")
        self.assertEqual(len(main), 24)
        self.assertEqual(len({spec.case_id for spec in (*main, *control)}), len(main) + len(control))
        self.assertTrue(set(CONTROL_PROBES).issubset({spec.case_id for spec in control}))
        self.assertEqual([build_fixture(main[i]).command.kind for i in MAIN_PROBES],
                         ["translate", "set_shape_key", "translate"])

    def test_selected_same_scene_action_gaps_against_independent_geometry(self):
        for ordinal in MAIN_PROBES:
            fixture = build_fixture(fixture_manifest(partition="main")[ordinal])
            with self.subTest(case=fixture.spec.case_id):
                before = _world_arrays(fixture)
                after = _world_arrays(fixture, after=True)
                for state, expected in ((before, fixture.expected_before_m),
                                        (after, fixture.expected_after_m)):
                    actual, tolerance = _pair_truth(state, fixture.target_ids)
                    self.assertAlmostEqual(actual, expected, delta=max(tolerance, 1e-12))
                for object_id, delta in fixture.expected_obstacle_delta_m.items():
                    a, b = before[object_id][0], after[object_id][0]
                    np.testing.assert_allclose(b - a, np.broadcast_to(delta, a.shape), atol=1e-12)

    def test_portable_staged_failures(self):
        self.assertEqual(len(_stub_failure_probes()), 6)


class _StubMatrix:
    def __init__(self, x):
        self.translation = (x, 0., 0.)

    def copy(self):
        clone = _StubMatrix(0.)
        clone.translation = self.translation
        return clone


class _StubObject:
    def __init__(self, name, x, events):
        self.name = name
        self.events = events
        self._matrix = _StubMatrix(x)

    def evaluated_get(self, graph):
        return self

    @property
    def matrix_world(self):
        return self._matrix

    @matrix_world.setter
    def matrix_world(self, matrix):
        self.events.append(("write", self.name, matrix.translation[0]))
        self._matrix = matrix


class _StubBridge:
    """A fixture-only bridge with independently observable capture failure points."""

    def __init__(self, case, events):
        self.case = case
        self.events = events
        self.meshes = {}

    def capture(self, key, obj, graph, scale, changes=0):
        from human_eye_fast.resident_bridge import ResidentMesh

        written = any(event[0] == "write" for event in self.events)
        self.events.append(("capture", key, "after" if written else "before"))
        if written and ((self.case == "target-readback" and key == "moving")
                        or (self.case == "after-context" and key == "context")):
            raise RuntimeError(f"injected {self.case}")
        x = 1. if key == "moving" else 0.
        local = np.array([[x, 0., 0.], [x, 1., 0.], [x, 0., 1.]])
        transform = np.eye(4)
        transform[:3, 3] = obj.matrix_world.translation
        world = local + transform[:3, 3]
        result = ResidentMesh(local, world, np.array([[0, 1, 2]]), transform, None)
        self.meshes[key] = result
        return result

    def get(self, key):
        written = any(event[0] == "write" for event in self.events)
        if written and key == "moving":
            self.events.append(("get", key, "after"))
            if self.case == "control-after":
                raise RuntimeError("injected control-after")
        return self.meshes[key]

    def clear(self):
        self.meshes.clear()


def _stub_failure_probes():
    """Run proposed B seam against a fake host; no outcome is supplied by the stub."""
    from human_eye_fast.control import Goal, Translate
    from verification import integration_reference as ref

    rows = []
    for case in ("stale-plan", "target-readback", "control-after", "after-context",
                 "post-render", "post-ao"):
        events = []
        objects = {key: _StubObject(key, x, events)
                   for key, x in (("moving", 0.), ("reference", 2.), ("context", 4.))}
        scene = SimpleNamespace(frame_current=17, view_layers=[object()],
                                unit_settings=SimpleNamespace(scale_length=1.))
        graph = object()
        bpy = SimpleNamespace(context=SimpleNamespace(
            temp_override=lambda **_: nullcontext(), evaluated_depsgraph_get=lambda: graph))
        goal = Goal("moving", "reference", 0., 0.)
        with patch.dict(sys.modules, {"bpy": bpy}):
            control = ref.SharedCaptureControl(scene, objects, goal)
        control.bridge = _StubBridge(case, events)
        initial = control.observe("reference")
        reference = ref.reference_from_capture(control, initial)
        before = ref.observe(control, None, reference, "before", mode=None, view_arm="F")
        plan = ref.predict(control, before, Translate((.25, 0., 0.)), "act", action_arm="NONE")
        if case == "stale-plan":
            ref.observe(control, None, reference, "superseding", mode=None, view_arm="F")
        if case == "post-render":
            inject = patch.object(ref, "_render", side_effect=RuntimeError("injected post-render"))
        elif case == "post-ao":
            inject = patch.object(ref, "encode", side_effect=RuntimeError("injected post-ao"))
        else:
            inject = nullcontext()
        with inject:
            try:
                ref.execute(control, None, reference, before, plan, "after",
                            mode="NATURAL" if case == "post-render" else None, view_arm="F")
            except (ValueError, ref.ActionStageError) as error:
                writes = [event for event in events if event[0] == "write"]
                stage = getattr(error, "stage", "rejected")
                status = getattr(error, "write_status", "not_written")
                outcome = getattr(error, "outcome", None)
                if case == "stale-plan":
                    assert not writes and status == "not_written" and outcome is None
                else:
                    assert writes == [("write", "moving", .25)] and status == "written"
                    assert stage in {"target-readback": ("target_readback",),
                                     "control-after": ("target_readback", "control_after"),
                                     "after-context": ("context",), "post-render": ("render", "vg"),
                                     "post-ao": ("ao",)}[case], (case, stage)
                    if case in ("target-readback", "control-after"):
                        assert outcome is None
                    else:
                        assert outcome is not None and outcome.measured_delta_m == -.25
                        assert outcome.control_after == (.25, 0., 0.)
                        assert outcome.before.observation_id == "before"
                        assert outcome.after.observation_id == "after"
                    if case == "after-context":
                        assert events.index(("get", "moving", "after")) < events.index(
                            ("capture", "context", "after"))
                rows.append({"case": case, "stage": stage, "write_status": status,
                             "observed_moving_x_m": objects["moving"].matrix_world.translation[0],
                             "measured_delta_m": outcome.measured_delta_m if outcome else None,
                             "events": events.copy()})
            else:
                raise AssertionError(f"Missing injected failure: {case}")
        try:
            ref.execute(control, None, reference, before, plan, "again", mode=None, view_arm="F")
        except (ValueError, ref.ActionStageError):
            assert [event for event in events if event[0] == "write"] == writes
        else:
            raise AssertionError(f"Stale before reusable: {case}")
        finally:
            control.close()
    return rows


def _native_snapshot(scene, objects):
    """Read evaluated mesh via Blender's temporary mesh API independently of RB."""
    import bpy

    snapshot = {}
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        graph = bpy.context.evaluated_depsgraph_get()
        scale = scene.unit_settings.scale_length
        for object_id, obj in objects.items():
            evaluated = obj.evaluated_get(graph)
            matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
            mesh = evaluated.to_mesh()
            try:
                local = np.array([tuple(v.co) for v in mesh.vertices]).reshape(-1, 3)
                faces = np.array([tuple(face.vertices) for face in mesh.loop_triangles],
                                 dtype=np.int32).reshape(-1, 3)
                snapshot[object_id] = ((local @ matrix[:3, :3].T + matrix[:3, 3]) * scale, faces)
            finally:
                evaluated.to_mesh_clear()
    return snapshot


@contextmanager
def _materialize(fixture):
    import bpy
    from mathutils import Matrix
    from verification.test_blender_control import _scene

    with _scene(fixture.spec.frame_id, fixture.scale_length) as scene:
        scale = scene.unit_settings.scale_length
        objects = {}
        for spec in fixture.parents:
            obj = bpy.data.objects.new(spec.object_id, None)
            scene.collection.objects.link(obj)
            objects[spec.object_id] = obj
        for spec in fixture.meshes:
            mesh = bpy.data.meshes.new(spec.object_id)
            mesh.from_pydata((np.asarray(spec.vertices_local_m) / scale).tolist(),
                             [], np.asarray(spec.triangles).tolist())
            obj = bpy.data.objects.new(spec.object_id, mesh)
            obj.color = spec.color
            scene.collection.objects.link(obj)
            objects[spec.object_id] = obj
            if spec.shape_basis_local_m is not None:
                obj.shape_key_add(name="Basis", from_mix=False)
                basis = obj.data.shape_keys.key_blocks["Basis"]
                relative = basis
                coordinates = np.asarray(spec.vertices_local_m, dtype=float)
                if spec.shape_relative_local_m is not None:
                    coordinates = np.asarray(spec.shape_relative_local_m, dtype=float)
                    relative = obj.shape_key_add(name="Relative", from_mix=False)
                    for vertex, co in zip(relative.data, coordinates / scale, strict=True):
                        vertex.co = co
                    relative.value = 0.
                key = obj.shape_key_add(name=fixture.command.key_name, from_mix=False)
                key.relative_key = relative
                for vertex, co in zip(key.data,
                                      (coordinates + spec.shape_basis_local_m) / scale, strict=True):
                    vertex.co = co
                key.value = fixture.command.control_before
        for spec in (*fixture.parents, *fixture.meshes):
            obj = objects[spec.object_id]
            if spec.parent_id is not None:
                obj.parent = objects[spec.parent_id]
            matrix = np.array(spec.local_matrix_m, dtype=float, copy=True)
            matrix[:3, 3] /= scale
            obj.matrix_basis = Matrix(matrix)
        yield scene, {item.object_id: objects[item.object_id] for item in fixture.meshes}


def _command(spec):
    from human_eye_fast.control import SetShapeKey, Translate

    if spec is None:
        return None
    if spec.kind == "translate":
        return Translate(tuple(spec.delta_world_m))
    return SetShapeKey(spec.key_name, spec.target_value)


def _write(path, value):
    def encode(item):
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, np.ndarray):
            return item.tolist()
        raise TypeError(type(item))
    path.write_text(json.dumps(value, default=encode, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def _pngs(folder, name, published):
    (folder / f"{name}.ao.json").write_bytes(published.ao_bytes)
    identities = {}
    for path, data in published.attachments.items():
        assert Path(path).name == path and data.startswith(b"\x89PNG\r\n\x1a\n")
        assert unpack(">II", data[16:24]) == (1024, 512)
        target = folder / path
        if target.is_file():
            assert target.read_bytes() == data
        else:
            target.write_bytes(data)
        identities[path] = sha256(data).hexdigest()
    return identities


class _AuditedRenderer:
    """Test-only independent sampling of the same render used for publication."""

    def __init__(self, renderer, scene, objects):
        self.renderer = renderer
        self.scene = scene
        self.objects = objects
        self.records = []

    def prepare(self, meshes):
        return self.renderer.prepare(meshes)

    def observe(self, prepared, witness, *, target_ids, frame_id, scale_length,
                mode="NATURAL", method="active", audit=False, relation=None, rank_directions=None):
        from verification.cf_visual_acceptance import VisualAudit, observe

        assert method == "active"
        audit = VisualAudit(_native_snapshot(self.scene, self.objects), target_ids, frame_id,
                            mode, scale_length, witness)
        image, record = observe(self.renderer, prepared, audit, rank_directions, relation=relation)
        self.records.append((image, record))
        return image


def _native_case(fixture, folder, model, scorer):
    import bpy
    from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
    from human_eye_fast.control import Goal
    from human_eye_fast.fast_affordance_out import public_schema
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification.integration_reference import (
        NoAction, SharedCaptureControl, ViewFeedback, action_feedback, execute, observe, predict,
        reference_from_capture, view_feedback,
    )
    from verification.test_blender_control import _assert_witness
    from verification.test_fast_affordance_out import decode_public

    folder.mkdir()
    calls = []
    operation = "reference"
    original_capture = BlenderResidentBridge.capture

    def tracked(bridge, key, obj, graph, scale, changes=0):
        calls.append({"operation": operation, "object": key, "bridge": id(bridge),
                      "graph": graph.as_pointer(), "scale": scale, "changes": int(changes)})
        return original_capture(bridge, key, obj, graph, scale, changes)

    def assert_capture(phase, count):
        batch = [row for row in calls if row["operation"] == phase]
        assert Counter(row["object"] for row in batch) == Counter({key: count for key in objects if count})
        if count:
            assert len({row["graph"] for row in batch}) == 1
            assert {row["bridge"] for row in batch} == {id(control.bridge)}

    def verify(readback, snapshot, expected):
        actual, tolerance = _pair_truth(snapshot, fixture.target_ids)
        if not isfinite(actual):
            assert readback.surface.distance_m == float("inf")
            assert readback.surface.point_a is None and readback.surface.point_b is None
            return None
        witness_data = {key: {"world_vertices_m": vertices, "triangles": triangles}
                        for key, (vertices, triangles) in snapshot.items()}
        _assert_witness(readback, witness_data, actual, max(tolerance, 1e-12))
        # Blender stores geometry/transform channels in float32. Keep authored
        # analytic agreement separate from the stricter native-data BC check.
        max_coord = max(np.max(np.abs(vertices), initial=0.) for vertices, _ in snapshot.values())
        host_tolerance = max(3e-9, 32 * np.finfo(np.float32).eps * max_coord)
        assert abs(actual - expected) <= host_tolerance, (actual, expected, host_tolerance)
        return actual

    def verify_meshes(snapshot, *, after=False):
        expected = _world_arrays(fixture, after=after)
        assert snapshot.keys() == expected.keys()
        for key, (vertices, faces) in snapshot.items():
            np.testing.assert_array_equal(faces, expected[key][1])
            np.testing.assert_allclose(vertices, expected[key][0], rtol=0,
                                       atol=fixture.host_tolerance_m)

    def record_meshes(snapshot):
        return {key: {"world_vertices_m": vertices, "triangles": faces}
                for key, (vertices, faces) in snapshot.items()}

    schema = public_schema()
    record = {"case": fixture.spec.case_id, "mode": fixture.mode, "capture_calls": calls,
              "model_loaded": model is not None}
    with _materialize(fixture) as (scene, objects), patch.object(BlenderResidentBridge, "capture", tracked):
        goal = Goal(*fixture.target_ids, fixture.goal_distance_m, fixture.goal_tolerance_m)
        control = SharedCaptureControl(scene, objects, goal)
        reference = reference_from_capture(control, control.observe("reference"))
        assert_capture("reference", 1)
        operation = "before"
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            renderer = VGRenderer()
            audit = _AuditedRenderer(renderer, scene, objects)
            try:
                arm = "L" if model is not None else "F"
                before = observe(control, audit, reference, "before", mode=fixture.mode,
                                 view_arm=arm, model=model)
                assert_capture("before", 1)
                native_before = _native_snapshot(scene, objects)
                verify_meshes(native_before)
                record["native_before"] = record_meshes(native_before)
                record["distance_before_m"] = verify(before.readback, native_before,
                                                      fixture.expected_before_m)
                old_bytes = before.ao_bytes
                old_attachments = dict(before.attachments)
                record["before_pngs"] = _pngs(folder, "before", before)
                command = _command(fixture.command)
                operation = "predict"
                action_arm = "L" if model is not None and fixture.command is not None and (
                    fixture.command.kind == "set_shape_key") else "G"
                prediction = (None if command is None else
                              predict(control, before, command, "act", action_arm=action_arm, model=model))
                assert_capture("predict", 0)
                if prediction is None or isinstance(prediction, NoAction):
                    assert command is None or abs(before.readback.surface.distance_m - goal.distance_m) <= goal.tolerance_m
                    if isinstance(prediction, NoAction):
                        assert prediction.reason == "GOAL_REACHED"
                    for key, (vertices, faces) in _native_snapshot(scene, objects).items():
                        np.testing.assert_array_equal(vertices, native_before[key][0])
                        np.testing.assert_array_equal(faces, native_before[key][1])
                    record["action"] = "not-issued"
                else:
                    operation = "execute"
                    result = execute(control, audit, reference, before, prediction, "after",
                                     mode=fixture.mode, view_arm=arm, model=model)
                    assert result is not None
                    assert_capture("execute", 1)
                    native_after = _native_snapshot(scene, objects)
                    verify_meshes(native_after, after=True)
                    record["native_after"] = record_meshes(native_after)
                    record["distance_after_m"] = verify(result.outcome.after, native_after,
                                                         fixture.expected_after_m)
                    outcome = result.outcome
                    assert outcome.before == before.readback
                    assert outcome.before.frame_id == outcome.after.frame_id == scene.frame_current
                    assert outcome.before.observation_id != outcome.after.observation_id
                    assert outcome.measured_delta_m == outcome.after.surface.distance_m - outcome.before.surface.distance_m
                    if fixture.command.kind == "set_shape_key":
                        assert outcome.control_before == fixture.command.control_before
                        assert outcome.control_after == fixture.command.target_value
                    assert before.ao_bytes == old_bytes and before.attachments == old_attachments
                    first = decode_public(old_bytes, schema)["observations"][0]
                    transition = decode_public(result.ao_bytes, schema)
                    assert transition["observations"][0] == first
                    assert transition["outcome"]["measured_delta_m"] == outcome.measured_delta_m
                    record["measured_delta_m"] = outcome.measured_delta_m
                    record["predicted_delta_m"] = outcome.action.predicted_delta_m
                    record["transition_pngs"] = _pngs(folder, "transition", result)
                    for key, displacement in fixture.expected_obstacle_delta_m.items():
                        moved = native_after[key][0] - native_before[key][0]
                        np.testing.assert_allclose(moved, np.broadcast_to(displacement, moved.shape), atol=3e-8)

                    if model is not None:
                        operation = "feedback"
                        counts = model.views.writes, model.actions.writes
                        before_views = model.view_head.weights.copy()
                        before_actions = model.action_head.weights.copy()
                        for observation, (image, visual) in zip((before, result.after), audit.records, strict=True):
                            score = scorer.score(image.png, visual)
                            assert score["checks"]["native_ray_accounting"]
                            _write(folder / f"{observation.readback.observation_id}.visual.json",
                                   {"evidence": visual, "score": score})
                            if observation.view is not None:
                                assert observation.view.index == visual["candidate"]
                                view_feedback(control, model, observation.view, ViewFeedback(
                                    observation.readback.observation_id,
                                    f"{observation.readback.observation_id}.png",
                                    visual["candidate"], score["pixel_success"],
                                ))
                        if action_arm == "L":
                            action_feedback(control, model, result.action_ticket)
                        assert_capture("feedback", 0)
                        expected_writes = sum(row.view is not None for row in (before, result.after))
                        assert model.views.writes == counts[0] + expected_writes
                        assert model.actions.writes == counts[1] + (action_arm == "L")
                        if expected_writes:
                            assert not np.array_equal(model.view_head.weights, before_views)
                        if action_arm == "L":
                            assert not np.array_equal(model.action_head.weights, before_actions)
                        record["feedback_writes"] = [model.views.writes - counts[0],
                                                     model.actions.writes - counts[1]]

                    operation = "next"
                    next_frame = observe(control, audit, reference, "next", mode=fixture.mode,
                                         view_arm=arm, model=model)
                    assert_capture("next", 1)
                    assert next_frame.readback.surface == outcome.after.surface
                    record["next_pngs"] = _pngs(folder, "next", next_frame)
                    followup = _command(fixture.followup_command)
                    if followup is not None:
                        next_prediction = predict(control, next_frame, followup, "next-act",
                                                  action_arm=action_arm, model=model)
                        if not isinstance(next_prediction, NoAction):
                            assert next_prediction.action.before_observation_id == "next"
                            record["next_prediction_m"] = next_prediction.action.predicted_delta_m
                        assert_capture("next", 1)
            finally:
                renderer.close()
                control.close()
    _write(folder / "record.json", record)
    return record


def _smoke(out, snapshot, pillow_python):
    import bpy
    from human_eye_fast.fast_affordance_out import public_schema
    from verification.cf_training import load_frozen
    from verification.cf_visual_acceptance import PillowWorker

    assert bpy.app.background
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "schema.json", public_schema())
    frozen = load_frozen(snapshot) if snapshot is not None else None
    main = fixture_manifest(partition="main")
    controls = {spec.case_id: spec for spec in fixture_manifest(partition="control")}
    cases = tuple(main[index] for index in MAIN_PROBES) + tuple(controls[key] for key in CONTROL_PROBES)
    records = []
    with PillowWorker(pillow_python) as scorer:
        for spec in cases:
            model = frozen.session() if frozen is not None else None
            try:
                records.append(_native_case(build_fixture(spec), out / spec.case_id, model, scorer))
            finally:
                if model is not None:
                    model.close()
    _write(out / "summary.json", {"blender": bpy.app.version_string,
                                 "snapshot_sha256": sha256(snapshot.read_bytes()).hexdigest()
                                 if snapshot is not None else None, "cases": records})


def _rejected(function):
    try:
        function()
    except (ValueError, RuntimeError) as error:
        return type(error).__name__
    raise AssertionError("Operation unexpectedly accepted")


def _no_image(publication):
    assert publication.view is None
    assert publication.attachments == {}
    assert publication.image_status == "disabled"


def _public_generations(payload, schema):
    from verification.test_fast_affordance_out import decode_public

    package = decode_public(payload, schema)
    return [{package["object_ids"][obj["object_index"]]: obj["topology_generation"]
             for obj in frame["objects"]} for frame in package["observations"]]


def _native_masks(folder):
    from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange
    from human_eye_fast.control import Goal
    from human_eye_fast.fast_affordance_out import public_schema
    from verification import integration_reference as ref

    class UnavailableRenderer:
        def prepare(self, *_):
            raise AssertionError("No-image publication must not prepare VG")

        def observe(self, *_):
            raise AssertionError("No-image publication must not render VG")

    fixture = build_fixture(fixture_manifest(partition="main")[20])
    initial = {"moving": 6, "reference": 7, "moving-screen": 8, "fixed-screen": 9}
    updated = {**initial, "moving-screen": 10}
    schema = public_schema()
    calls = []
    phase = None
    original = BlenderResidentBridge.capture

    def tracked(bridge, key, obj, graph, scale, changes=0):
        calls.append({"phase": phase, "object": key, "mask": int(changes),
                      "scale": float(scale), "bridge": id(bridge), "graph": graph.as_pointer()})
        return original(bridge, key, obj, graph, scale, changes)

    def changes(default, overrides=None):
        return {key: (overrides or {}).get(key, ref.CaptureChange(default)) for key in initial}

    renderer = UnavailableRenderer()
    with _materialize(fixture) as (scene, objects), patch.object(BlenderResidentBridge, "capture", tracked):
        control = ref.SharedCaptureControl(
            scene, objects, Goal(*fixture.target_ids, fixture.goal_distance_m, fixture.goal_tolerance_m),
            generations=dict(initial),
        )
        try:
            phase = "capture-reference"
            first_mask = MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.UNITS
            original_capture = control.observe("capture-reference", changes=changes(first_mask))
            reference = ref.reference_from_capture(control, original_capture, initial["moving"])
            phase = "static"
            static = ref.observe(control, renderer, reference, "static", mode=None, view_arm="F",
                                 changes=changes(MeshChange.NONE))
            _no_image(static)
            _pngs(folder, "static", static)
            assert _public_generations(static.ao_bytes, schema) == [initial]
            plan = ref.predict(control, static, _command(fixture.command), "act", action_arm="NONE")
            assert plan.action.predicted_delta_m is None
            after_masks = {key: ref.CaptureChange(MeshChange.VERTICES | MeshChange.TRANSFORM)
                           for key in fixture.target_ids}
            after_masks["moving-screen"] = ref.CaptureChange(MeshChange.TRANSFORM)
            phase = "after-none"
            after = ref.execute(control, renderer, reference, static, plan, "after-none", mode=None,
                                view_arm="F", changes=changes(MeshChange.NONE, after_masks))
            _no_image(after.after)
            _pngs(folder, "transition", after)
            assert after.action_ticket is None and after.outcome.measured_delta_m is not None
            assert _public_generations(after.ao_bytes, schema) == [initial, initial]
            old = _native_snapshot(scene, objects)
            before = _world_arrays(fixture)
            delta = fixture.expected_obstacle_delta_m["moving-screen"]
            np.testing.assert_allclose(old["moving-screen"][0] - before["moving-screen"][0],
                                       np.broadcast_to(delta, old["moving-screen"][0].shape),
                                       rtol=0, atol=fixture.host_tolerance_m)
            moving_screen = objects["moving-screen"].data
            coords = [tuple(vertex.co) for vertex in moving_screen.vertices]
            reverse = [tuple(poly.vertices) for poly in reversed(moving_screen.polygons)]
            moving_screen.clear_geometry()
            moving_screen.from_pydata(coords, [], reverse)
            phase = "bad-generation"
            err = _rejected(lambda: ref.observe(
                control, renderer, reference, "bad-generation", mode=None, view_arm="F",
                changes=changes(MeshChange.NONE, {"moving-screen": ref.CaptureChange(MeshChange.TOPOLOGY)}),
            ))
            phase = "context-topology"
            topology = ref.observe(
                control, renderer, reference, "context-topology", mode=None, view_arm="F",
                changes=changes(MeshChange.NONE, {"moving-screen": ref.CaptureChange(MeshChange.TOPOLOGY, 10)}),
            )
            _pngs(folder, "context-topology", topology)
            _no_image(topology)
            assert _public_generations(topology.ao_bytes, schema) == [updated]
            np.testing.assert_array_equal(control.bridge.get("moving-screen").triangles, reverse)
            for key in fixture.target_ids:
                np.testing.assert_array_equal(control.bridge.get(key).triangles, old[key][1])
            scene.unit_settings.scale_length = .5
            phase = "unit-change"
            unit = ref.observe(control, renderer, reference, "unit-change", mode=None, view_arm="F",
                               changes=changes(MeshChange.UNITS))
            _pngs(folder, "unit-change", unit)
            _no_image(unit)
            assert _public_generations(unit.ao_bytes, schema) == [updated]
            for key in initial:
                np.testing.assert_allclose(control.bridge.get(key).world_m, old[key][0] * .5,
                                           rtol=0, atol=fixture.host_tolerance_m)
            np.testing.assert_allclose(unit.readback.surface.distance_m,
                                       topology.readback.surface.distance_m * .5, rtol=0,
                                       atol=fixture.host_tolerance_m)
            expected = {"capture-reference": [int(first_mask)] * len(initial), "static": [0, 0, 0, 0],
                        "after-none": [5, 5, 4, 0], "context-topology": [0, 0, 2, 0],
                        "unit-change": [8, 8, 8, 8]}
            for name, masks in expected.items():
                phase_rows = [row for row in calls if row["phase"] == name]
                actual_masks = {row["object"]: row["mask"] for row in phase_rows}
                expected_masks = dict(zip(initial, masks, strict=True))
                assert actual_masks == expected_masks, (name, actual_masks, expected_masks)
                assert len(phase_rows) == len(initial)
                assert len({(row["bridge"], row["graph"]) for row in phase_rows}) == 1
            assert not any(row["phase"] == "bad-generation" for row in calls)
            result = {"source": "native", "case": fixture.spec.case_id, "capture_calls": calls,
                      "bad_generation": err, "generations_before": initial,
                      "generations_after": updated, "actual_scale_m_per_bu": .5,
                      "distance_before_unit_m": topology.readback.surface.distance_m,
                      "distance_after_unit_m": unit.readback.surface.distance_m,
                      "measured_translation_delta_m": after.outcome.measured_delta_m}
        finally:
            control.close()
    _write(folder / "record.json", result)
    return result


def _feedback_for(scorer, observation, audited):
    from verification.integration_reference import ViewFeedback

    image, visual = audited
    verdict = scorer.score(image.png, visual)
    assert observation.view.index == visual["candidate"]
    assert image.png == observation.attachments[f"{observation.readback.observation_id}.png"]
    feedback = ViewFeedback(observation.readback.observation_id,
                            f"{observation.readback.observation_id}.png", visual["candidate"],
                            verdict["pixel_success"])
    return feedback, {"evidence": visual, "score": verdict}


def _native_tickets(folder, model, scorer):
    from human_eye_fast.control import Goal
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification import integration_reference as ref

    spec = next(row for row in fixture_manifest(partition="control") if row.case_id == "nonbasis-key")
    fixture = build_fixture(spec)
    with _materialize(fixture) as (scene, objects):
        goal = Goal(*fixture.target_ids, fixture.goal_distance_m, fixture.goal_tolerance_m)
        renderer = VGRenderer()
        audit = _AuditedRenderer(renderer, scene, objects)
        control = ref.SharedCaptureControl(scene, objects, goal, renderer=renderer, model=model)
        try:
            reference = ref.reference_from_capture(control, control.observe("capture-reference"))
            moving = objects["moving"]
            key = moving.data.shape_keys.key_blocks[fixture.command.key_name]
            assert key.relative_key.name == "Relative"
            basis = ref.relative_basis_from_rna(moving, key.name)
            native_def = np.array([tuple(row.co) for row in key.data])
            native_rel = np.array([tuple(row.co) for row in key.relative_key.data])
            np.testing.assert_array_equal(basis.local_delta_bu, native_def - native_rel)
            before = ref.observe(control, audit, reference, "before", mode="SECTION", view_arm="L",
                                 model=model)
            _pngs(folder, "before", before)
            plan = ref.predict(control, before, _command(fixture.command), "act", action_arm="L",
                               model=model, basis=basis)
            result = ref.execute(control, audit, reference, before, plan, "after", mode="SECTION",
                                 view_arm="L", model=model)
            assert result.outcome.control_after == fixture.command.target_value
            assert result.outcome.measured_delta_m is not None
            _pngs(folder, "transition", result)
            followup = _command(fixture.followup_command)
            revoked = ref.predict(control, result.after, followup, "revoked",
                                  action_arm="L", model=model, basis=basis)
            replacement = ref.reference_from_capture(control, result.outcome.after)
            reference = control.replace_reference(replacement)
            rejections = {"old_plan": _rejected(lambda: ref.execute(
                control, audit, reference, result.after, revoked, "invalid", mode="SECTION",
                view_arm="L", model=model))}
            observed_feedback = [_feedback_for(scorer, obs, raw) for obs, raw in zip(
                (before, result.after), audit.records, strict=True)]
            for observation, (_, scored) in zip((before, result.after), observed_feedback, strict=True):
                _write(folder / f"{observation.readback.observation_id}.visual.json", scored)
            foreign = ref.SharedCaptureControl(scene, objects, goal)
            try:
                first_feedback = observed_feedback[0][0]
                rejections["foreign_view"] = _rejected(lambda: ref.view_feedback(
                    foreign, model, before.view, first_feedback))
                rejections["foreign_action"] = _rejected(lambda: ref.action_feedback(
                    foreign, model, result.action_ticket))
            finally:
                foreign.close()
            counts = (model.views.writes, model.actions.writes)
            for observation, (feedback, _) in zip((before, result.after), observed_feedback, strict=True):
                ref.view_feedback(control, model, observation.view, feedback)
            ref.action_feedback(control, model, result.action_ticket)
            after_counts = (model.views.writes, model.actions.writes)
            assert after_counts == (counts[0] + 2, counts[1] + 1)
            rejections["duplicate_view"] = _rejected(lambda: ref.view_feedback(
                control, model, before.view, observed_feedback[0][0]))
            rejections["duplicate_action"] = _rejected(lambda: ref.action_feedback(
                control, model, result.action_ticket))
            assert (model.views.writes, model.actions.writes) == after_counts
            old_basis = basis.local_delta_bu.copy()
            key.data[0].co.x += .125
            key.id_data.update_tag()
            rebuilt = ref.relative_basis_from_rna(moving, key.name)
            np.testing.assert_array_equal(basis.local_delta_bu, old_basis)
            np.testing.assert_allclose(rebuilt.local_delta_bu[0] - old_basis[0], [.125, 0., 0.],
                                       rtol=0, atol=1e-5)
            next_frame = ref.observe(control, audit, reference, "next", mode="SECTION", view_arm="L",
                                     model=model)
            _pngs(folder, "next", next_frame)
            known = ref.finite_action(control, followup, basis=rebuilt)
            linear = control.bridge.get("moving").world_from_local[:3, :3]
            scale = scene.unit_settings.scale_length
            np.testing.assert_allclose(known.basis_world_m,
                                       (rebuilt.local_delta_bu * scale) @ linear.T, rtol=0, atol=1e-12)
            assert known.control_before == fixture.command.target_value
            next_feedback, scored = _feedback_for(scorer, next_frame, audit.records[-1])
            _write(folder / "next.visual.json", scored)
            control.close()
            rejections["closed_view"] = _rejected(lambda: ref.view_feedback(
                control, model, next_frame.view, next_feedback))
            rejections["closed_action"] = _rejected(lambda: ref.action_feedback(
                control, model, result.action_ticket))
            assert model.views.keys is None and model.actions.keys is None
            evidence = {"source": "native", "case": spec.case_id, "relative_key": key.relative_key.name,
                        "actual_scale_m_per_bu": float(scale), "actual_linear": linear.copy(),
                        "before_q": result.outcome.control_before, "after_q": result.outcome.control_after,
                        "measured_delta_m": result.outcome.measured_delta_m, "feedback_before": counts,
                        "feedback_after": after_counts, "rejections": rejections,
                        "basis_old_vertex0_bu": old_basis[0], "basis_new_vertex0_bu": rebuilt.local_delta_bu[0]}
        finally:
            control.close()
    _write(folder / "record.json", evidence)
    return evidence


def _native_rework(out, snapshot, pillow_python):
    import bpy
    from human_eye_fast.fast_affordance_out import public_schema
    from verification.cf_training import load_frozen
    from verification.cf_visual_acceptance import PillowWorker

    assert bpy.app.background
    out.mkdir(parents=True, exist_ok=False)
    _write(out / "schema.json", public_schema())
    masks_out = out / "masks"
    masks_out.mkdir()
    masks = _native_masks(masks_out)
    tickets_out = out / "tickets"
    tickets_out.mkdir()
    with PillowWorker(pillow_python) as scorer:
        tickets = _native_tickets(tickets_out, load_frozen(snapshot).session(), scorer)
    _write(out / "summary.json", {"source": "native", "blender": bpy.app.version_string,
                                 "snapshot_sha256": sha256(snapshot.read_bytes()).hexdigest(),
                                 "cases": [masks, tickets]})


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--pillow-python", type=Path)
    parser.add_argument("--phase", choices=("legacy", "stub", "rework"), default="legacy")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    if args.phase == "stub":
        args.out.mkdir(parents=True, exist_ok=False)
        _write(args.out / "summary.json", {"source": "portable stub", "cases": _stub_failure_probes()})
    elif args.phase == "rework":
        if args.snapshot is None or args.pillow_python is None:
            parser.error("native rework needs --snapshot and --pillow-python")
        _native_rework(args.out, args.snapshot, args.pillow_python)
    else:
        if args.pillow_python is None:
            parser.error("legacy probe needs --pillow-python")
        _smoke(args.out, args.snapshot, args.pillow_python)
