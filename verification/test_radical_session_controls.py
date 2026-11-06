"""Production-session controls separate from the 24-case Blender replay."""

from contextlib import ExitStack, nullcontext
from dataclasses import replace
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

from verification.integration_fixtures import build_fixture, fixture_manifest
from verification.test_blender_radical_session import _decoded, _model_digest, _reference_vertices
from verification.test_integration_preflight import (
    _StubBridge, _StubObject, _command, _materialize, _native_snapshot, _pngs, _write,
)


def _open(scene, objects, fixture, *, deployment=None, goal=None, generations=None):
    from human_eye_fast import BlenderRadicalSession, Goal, ReferenceFrame

    if goal is None:
        goal = Goal(*fixture.target_ids, fixture.goal_distance_m, fixture.goal_tolerance_m)
    if generations is None:
        generations = {key: index + 1 for index, key in enumerate(objects)}
    moving = fixture.target_ids[0]
    reference = ReferenceFrame(scene.frame_current, generations[moving], _reference_vertices(scene, objects[moving]))
    return BlenderRadicalSession(scene, scene.view_layers[0], objects, goal, generations,
                                 reference=reference, deployment=deployment)


def _masks(objects, *, after=False, default=None, extra=None):
    from human_eye_fast import CaptureChange, MeshChange

    if default is None:
        default = MeshChange.VERTICES | MeshChange.TRANSFORM
        if not after:
            default |= MeshChange.UNITS
    return {key: (extra or {}).get(key, CaptureChange(default)) for key in objects}


def _observe(session, objects, name, mode=None, arm="F", *, changes=None):
    from human_eye_fast import ObservationRequest

    return session.observe(ObservationRequest(name, mode, arm), changes=changes or _masks(objects))


def _execute(session, objects, plan, name, mode=None, arm="F", *, changes=None):
    from human_eye_fast import ObservationRequest

    return session.execute(plan, ObservationRequest(name, mode, arm),
                           changes=changes or _masks(objects, after=True))


def _reject(function):
    try:
        function()
    except ValueError as error:
        return str(error)
    raise AssertionError("Operation accepted an invalid binding")


def _artifact(folder, result, schema, name):
    _pngs(folder, name, result)
    package = _decoded(result, schema)
    row = package["observations"][-1]
    assert row["observation_id"] == result.observation_id
    assert row["frame_id"] == result.frame_id
    return package, row


def _no_image(result, expected):
    assert result.image_status == expected
    assert result.view_ticket is None and result.view_audit is None
    assert not result.attachments


def _empty_and_goal(folder, schema, cases):
    from human_eye_fast import NoAction, Translate
    from human_eye_fast.raycast_saccade_gpu import VGRenderer

    evidence = []
    for name in ("empty-reference", "already-reached"):
        fixture = cases[name]
        with _materialize(fixture) as (scene, objects), _open(scene, objects, fixture) as session:
            if name == "empty-reference":
                with patch.object(VGRenderer, "__init__", side_effect=AssertionError("empty scene initialized VG")):
                    result = _observe(session, objects, name, "NATURAL")
                _no_image(result, "empty_surface")
                reason = "NO_SURFACE"
            else:
                result = _observe(session, objects, name, "NATURAL")
                assert result.image_status == "rendered"
                reason = "GOAL_REACHED"
            before = _native_snapshot(scene, objects)
            no_action = session.predict_action(result.observation_id, "invalid", Translate((.0001, 0., 0.)),
                                               predictor="NONE")
            assert no_action == NoAction(reason)
            for key, (vertices, faces) in _native_snapshot(scene, objects).items():
                np.testing.assert_array_equal(vertices, before[key][0])
                np.testing.assert_array_equal(faces, before[key][1])
            _, row = _artifact(folder, result, schema, name)
            assert (row["clearance"]["distance_m"] is None) == (reason == "NO_SURFACE")
            evidence.append({"id": name, "reason": reason, "status": result.image_status})
    return evidence


def _zero(folder, schema, fixture):
    from human_eye_fast import Goal, NoAction, Translate
    from human_eye_fast.raycast_saccade_gpu import VGRenderer

    with _materialize(fixture) as (scene, objects), _open(scene, objects, fixture) as reached:
        natural = _observe(reached, objects, "zero-natural", "NATURAL")
        assert natural.view_ticket is None and natural.view_audit.total_rays == 0
        assert natural.image_status == "rendered" and not natural.view_audit.native_stop
        _, initial = _artifact(folder, natural, schema, "zero-natural")
        assert initial["clearance"]["distance_m"] == 0.
        assert reached.predict_action("zero-natural", "stop", Translate((-.0001, 0., 0.)),
                                      predictor="NONE") == NoAction("GOAL_REACHED")

    opening = -abs(fixture.command.delta_world_m[0])
    goal = Goal(*fixture.target_ids, abs(opening), fixture.host_tolerance_m)
    with _materialize(fixture) as (scene, objects), _open(scene, objects, fixture, goal=goal) as session:
        with patch.object(VGRenderer, "__init__", side_effect=AssertionError("zero SECTION initialized VG")):
            blocked = _observe(session, objects, "zero-section", "SECTION")
        _no_image(blocked, "section_requires_positive_gap")
        _, no_image = _artifact(folder, blocked, schema, "zero-section")
        assert no_image["image"] is None and no_image["clearance"]["distance_m"] == 0.
        plan = session.predict_action(blocked.observation_id, "open-gap", Translate((opening, 0., 0.)),
                                      predictor="NONE")
        assert plan.predicted_delta_m is None
        opened = _execute(session, objects, plan, "zero-open", "SECTION")
        package, after = _artifact(folder, opened, schema, "zero-open")
        assert opened.image_status == "rendered" and after["image"]["section"] is not None
        outcome = package["outcome"]
        assert outcome["distance_before_m"] == 0. and outcome["measured_delta_m"] > 0.
        assert abs(outcome["measured_delta_m"] - abs(opening)) <= fixture.host_tolerance_m
        assert outcome["goal_reached"]
        return [{"id": "contact-zero", "rays": natural.view_audit.total_rays},
                {"id": "zero-section", "status": blocked.image_status},
                {"id": "zero-open", "measured_delta_m": outcome["measured_delta_m"]}]


def _follows(folder, schema, fixture):
    with _materialize(fixture) as (scene, objects), _open(scene, objects, fixture) as session:
        before = _observe(session, objects, "before")
        prior = _native_snapshot(scene, objects)
        command = _command(fixture.command)
        prepared = session.predict_action(before.observation_id, "act", command, predictor="NONE")
        assert prepared.predicted_delta_m is None
        after = _execute(session, objects, prepared, "after")
        snapshot = _native_snapshot(scene, objects)
        for key in fixture.target_ids:
            displacement = snapshot[key][0] - prior[key][0]
            np.testing.assert_allclose(displacement, np.broadcast_to(command.delta_world_m, displacement.shape),
                                       atol=fixture.host_tolerance_m, rtol=0)
        package, _ = _artifact(folder, after, schema, "transition")
        outcome = package["outcome"]
        assert abs(outcome["distance_before_m"] - fixture.expected_before_m) <= fixture.host_tolerance_m
        assert abs(outcome["measured_delta_m"]) <= fixture.host_tolerance_m
        assert outcome["predicted_delta_m"] is None and after.action_ticket is None
        return {"id": "reference-follows", "measured_delta_m": outcome["measured_delta_m"]}


def _unit_recode(folder, schema, fixture):
    observations = []
    for scale, code in ((.001, "scaled"), (1., "unscaled")):
        encoded = replace(fixture, spec=replace(fixture.spec, scale_length=scale))
        with _materialize(encoded) as (scene, objects), _open(scene, objects, encoded) as session:
            session.prepare_relative_basis(encoded.command.key_name)
            before = _observe(session, objects, f"{code}-before")
            pre = _native_snapshot(scene, objects)
            plan = session.predict_action(before.observation_id, "act", _command(encoded.command), predictor="G")
            after = _execute(session, objects, plan, f"{code}-after")
            post = _native_snapshot(scene, objects)
            package, _ = _artifact(folder, after, schema, code)
            observations.append((pre, post, package["outcome"], float(scene.unit_settings.scale_length)))
    (pre_small, post_small, small, scale_small), (pre_large, post_large, large, scale_large) = observations
    assert scale_small != scale_large and scale_large == 1.
    for small_rows, large_rows in ((pre_small, pre_large), (post_small, post_large)):
        for key in fixture.target_ids:
            np.testing.assert_allclose(small_rows[key][0], large_rows[key][0], rtol=0, atol=fixture.host_tolerance_m)
            np.testing.assert_array_equal(small_rows[key][1], large_rows[key][1])
    fields = ("distance_before_m", "distance_after_m", "predicted_delta_m", "measured_delta_m")
    for key in fields:
        assert abs(small[key] - large[key]) <= fixture.host_tolerance_m, (key, small[key], large[key])
    assert small["control_before"] == large["control_before"]
    assert small["control_after"] == large["control_after"]
    return {"id": "unit-recode", "actual_scales_m_per_bu": [scale_small, scale_large],
            "outcome_small": {key: small[key] for key in fields}, "outcome_large": {key: large[key] for key in fields}}


def _replace_faces(obj, faces):
    mesh = obj.data
    coordinates = [tuple(vertex.co) for vertex in mesh.vertices]
    mesh.clear_geometry()
    mesh.from_pydata(coordinates, [], np.asarray(faces).tolist())


def _topology(folder, schema, fixture):
    from human_eye_fast import CaptureChange, MeshChange
    from human_eye_fast.fast_bvh_clearance import SurfaceDistance
    from verification.test_blender_control import _assert_witness

    moving = fixture.target_ids[0]
    with _materialize(fixture) as (scene, objects):
        first = {key: index + 1 for index, key in enumerate(objects)}
        with _open(scene, objects, fixture, generations=first) as session:
            before = _observe(session, objects, "topology-original")
            _, prior = _artifact(folder, before, schema, "topology-original")
            wrong = _masks(objects, extra={moving: CaptureChange(MeshChange.TOPOLOGY, 11)})
            rejection = _reject(lambda: _observe(session, objects, "illegal-target-change", changes=wrong))
        _replace_faces(objects[moving], fixture.replacement_triangles[moving])
        second = {**first, moving: 11}
        with _open(scene, objects, fixture, generations=second) as session:
            reordered = _observe(session, objects, "topology-renumber")
            package, row = _artifact(folder, reordered, schema, "topology-renumber")
            snapshot = _native_snapshot(scene, objects)
            np.testing.assert_array_equal(snapshot[moving][1], fixture.replacement_triangles[moving])
            clearance = row["clearance"]
            witnesses = clearance["witness_a"], clearance["witness_b"]
            faces = tuple(w["original_face_id"] for w in witnesses)
            points = tuple(tuple(w["point_m"]) for w in witnesses)
            actual = SurfaceDistance(clearance["distance_m"], *faces, *points)
            mesh_data = {key: {"world_vertices_m": vertices, "triangles": triangles}
                         for key, (vertices, triangles) in snapshot.items()}
            _assert_witness(SimpleNamespace(surface=actual, target_ids=fixture.target_ids),
                            mesh_data, prior["clearance"]["distance_m"], fixture.host_tolerance_m)
            assert faces[0] != prior["clearance"]["witness_a"]["original_face_id"]
            assert {package["object_ids"][obj["object_index"]]: obj["topology_generation"]
                    for obj in row["objects"]} == second
    return {"id": "topology-renumber", "generations_before": first, "generations_after": second,
            "moving_face_before": prior["clearance"]["witness_a"]["original_face_id"],
            "moving_face_after": faces[0], "in_place_rejected": rejection}


def _context(folder, schema, fixture):
    from human_eye_fast import CaptureChange, MeshChange
    from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
    from human_eye_fast.raycast_saccade_gpu import VGRenderer

    phase = None
    calls = []
    original = BlenderResidentBridge.capture

    def tracked(bridge, key, obj, graph, scale, changes=0):
        calls.append((phase, key, int(changes), graph.as_pointer(), id(bridge)))
        return original(bridge, key, obj, graph, scale, changes)

    with (_materialize(fixture) as (scene, objects), _open(scene, objects, fixture) as session,
          patch.object(BlenderResidentBridge, "capture", tracked),
          patch.object(VGRenderer, "__init__", side_effect=AssertionError("disabled image initialized VG"))):
        phase = "static"
        static = _observe(session, objects, "static", changes=_masks(objects, default=MeshChange.NONE))
        _no_image(static, "disabled")
        _artifact(folder, static, schema, "static")
        prepared = session.predict_action(static.observation_id, "act", _command(fixture.command), predictor="NONE")
        phase = "after"
        targets = MeshChange.VERTICES | MeshChange.TRANSFORM
        after = _execute(session, objects, prepared, "after", changes=_masks(
            objects, default=MeshChange.NONE,
            extra={**dict.fromkeys(fixture.target_ids, CaptureChange(targets)),
                   "moving-screen": CaptureChange(MeshChange.TRANSFORM)}))
        _no_image(after, "disabled")
        _artifact(folder, after, schema, "transition")
        screen = objects["moving-screen"]
        before_topology = _native_snapshot(scene, objects)
        reverse = before_topology["moving-screen"][1][::-1]
        _replace_faces(screen, reverse)
        phase = "invalid"
        invalid = _masks(objects, default=MeshChange.NONE,
                         extra={"moving-screen": CaptureChange(MeshChange.TOPOLOGY)})
        rejection = _reject(lambda: _observe(session, objects, "invalid-generation", changes=invalid))
        phase = "context"
        changes = _masks(objects, default=MeshChange.NONE,
                         extra={"moving-screen": CaptureChange(MeshChange.TOPOLOGY, 19)})
        new = _observe(session, objects, "context", changes=changes)
        package, row = _artifact(folder, new, schema, "context")
        assert {package["object_ids"][obj["object_index"]]: obj["topology_generation"]
                for obj in row["objects"]} == {"moving": 1, "reference": 2, "moving-screen": 19, "fixed-screen": 4}
        np.testing.assert_array_equal(session._controller.bridge.get("moving-screen").triangles, reverse)
        assert not any(row[0] == "invalid" for row in calls)
        for name, expected in (("static", (0, 0, 0, 0)), ("after", (5, 5, 4, 0)),
                               ("context", (0, 0, 2, 0))):
            batch = [row for row in calls if row[0] == name]
            assert [row[1] for row in batch] == list(objects)
            assert [row[2] for row in batch] == list(expected)
            assert len({(row[3], row[4]) for row in batch}) == 1
        assert len({row[4] for row in calls}) == 1
    return {"id": "context-topology", "rejection": rejection, "capture_calls": calls}


def _sessions(folder, schema, fixture, deployment):
    import bpy
    from human_eye_fast import ReferenceFrame, ViewFeedback

    mode, arm = "SECTION", "L"
    with (_materialize(fixture) as (scene_a, objects_a), _materialize(fixture) as (scene_b, objects_b),
          _open(scene_a, objects_a, fixture, deployment=deployment) as a,
          _open(scene_b, objects_b, fixture, deployment=deployment) as b):
        key_name = fixture.command.key_name
        for session in (a, b):
            session.prepare_relative_basis(key_name)
        key = objects_a["moving"].data.shape_keys.key_blocks[key_name]
        assert key.relative_key.name == "Relative"
        initial = _model_digest(a._model)
        assert _model_digest(b._model) == initial
        first_a = _observe(a, objects_a, "a-before", mode, arm)
        first_b = _observe(b, objects_b, "b-before", mode, arm)
        assert first_a.frame_id == first_b.frame_id
        command = _command(fixture.command)
        pa = a.predict_action(first_a.observation_id, "a-act", command, predictor="L")
        pb = b.predict_action(first_b.observation_id, "b-act", command, predictor="L")
        rejected = {"foreign_plan": _reject(lambda: _execute(b, objects_b, pa, "foreign", mode, arm))}
        second_a = _execute(a, objects_a, pa, "a-after", mode, arm)
        assert objects_b["moving"].data.shape_keys.key_blocks[key_name].value == fixture.command.control_before
        second_b = _execute(b, objects_b, pb, "b-after", mode, arm)
        packed, initial_after = _artifact(folder, second_a, schema, "a-transition")
        assert packed["outcome"]["control_before"] == fixture.command.control_before
        assert packed["outcome"]["control_after"] == fixture.command.target_value
        assert packed["outcome"]["measured_delta_m"] is not None
        assert _model_digest(a._model) == _model_digest(b._model) == initial
        assert second_a.frame_id == first_a.frame_id and second_a.observation_id != first_a.observation_id

        stale = a.predict_action(second_a.observation_id, "stale", _command(fixture.followup_command), predictor="L")
        reference_vertices = _reference_vertices(scene_a, objects_a["moving"])
        replacement = ReferenceFrame(301, 1, reference_vertices)
        reference_vertices.fill(123.)
        assert not replacement.moving_world_m.flags.writeable
        a.replace_reference(replacement)
        rejected["reference_stale_plan"] = _reject(lambda: _execute(a, objects_a, stale, "stale", mode, arm))

        def feedback(result):
            # Deliberately negative synthetic labels exercise the state machine.
            return ViewFeedback(result.observation_id, f"{result.observation_id}.png",
                                result.view_audit.canonical_index, False)

        fv = feedback(first_a)
        rejected["foreign_view"] = _reject(lambda: b.view_feedback(first_a.view_ticket, fv))
        rejected["foreign_action"] = _reject(lambda: b.action_feedback(second_a.action_ticket))
        for name, wrong in (("observation", replace(fv, observation_id="wrong")),
                            ("attachment", replace(fv, attachment_key="wrong.png")),
                            ("direction", replace(fv, index=(fv.index + 1) % 16))):
            rejected[f"wrong_{name}"] = _reject(lambda: a.view_feedback(first_a.view_ticket, wrong))
        a.view_feedback(first_a.view_ticket, fv)
        a.view_feedback(second_a.view_ticket, feedback(second_a))
        a.action_feedback(second_a.action_ticket)
        state_a = _model_digest(a._model)
        assert state_a["writes"] == {"v": 242, "a": 241}
        assert _model_digest(b._model) == initial
        rejected["duplicate_view"] = _reject(lambda: a.view_feedback(first_a.view_ticket, fv))
        rejected["duplicate_action"] = _reject(lambda: a.action_feedback(second_a.action_ticket))
        b.view_feedback(first_b.view_ticket, feedback(first_b))
        assert _model_digest(b._model)["writes"] == {"v": 241, "a": 240}
        assert _model_digest(a._model) == state_a

        authored = a._bases[key_name].delta_bu.copy()
        key.data[0].co.x += .125
        key.id_data.update_tag()
        a.prepare_relative_basis(key_name)
        np.testing.assert_allclose(a._bases[key_name].delta_bu[0] - authored[0], (.125, 0., 0.),
                                   rtol=0, atol=1e-5)
        next_a = _observe(a, objects_a, "a-next", mode, arm)
        _, next_row = _artifact(folder, next_a, schema, "a-next")
        assert initial_after["deformation"]["reference_frame"] != next_row["deformation"]["reference_frame"] == 301
        assert a.predict_action(next_a.observation_id, "next-act", _command(fixture.followup_command),
                                predictor="L").predicted_delta_m is not None
        camera_names = [camera.name for camera in b._renderer.cameras]
        prior_bytes = dict(second_b.attachments)
        b.close()
        assert all(bpy.data.objects.get(name) is None for name in camera_names)
        assert b._renderer is b._reference is b._model is None
        assert not len(b._controller.bridge)
        assert dict(second_b.attachments) == prior_bytes
        rejected["closed_view"] = _reject(lambda: b.view_feedback(second_b.view_ticket, feedback(second_b)))
        rejected["closed_action"] = _reject(lambda: b.action_feedback(second_b.action_ticket))
        with _open(scene_b, objects_b, fixture, deployment=deployment) as reopened:
            assert _model_digest(reopened._model) == initial
            fresh = _observe(reopened, objects_b, "b-reopen", mode, arm)
            assert fresh.view_ticket is not None
            rejected["reopened_view"] = _reject(
                lambda: reopened.view_feedback(second_b.view_ticket, feedback(second_b)))
            rejected["reopened_action"] = _reject(lambda: reopened.action_feedback(second_b.action_ticket))
            assert _model_digest(reopened._model) == initial
        return [{"id": "nonbasis-key", "relative": key.relative_key.name, "outcome": packed["outcome"]},
                {"id": "reference-replacement", "after_frame": 301},
                {"id": "same-frame-observation-ids", "frame": second_a.frame_id},
                {"id": "wrong-and-repeated-feedback", "rejected": rejected},
                {"id": "two-sessions-close-reopen", "isolated": True, "old_bytes_readable": True}]


def run_controls(out, deployment, schema):
    out.mkdir()
    fixtures = {spec.case_id: build_fixture(spec) for spec in fixture_manifest(partition="control")}
    carried = build_fixture(fixture_manifest()[20])
    checks = (
        ("empty-and-goal", lambda folder: _empty_and_goal(folder, schema, fixtures)),
        ("zero", lambda folder: _zero(folder, schema, fixtures["contact-zero"])),
        ("follows", lambda folder: _follows(folder, schema, fixtures["reference-follows"])),
        ("unit-recode", lambda folder: _unit_recode(folder, schema, fixtures["unit-recode"])),
        ("topology", lambda folder: _topology(folder, schema, fixtures["topology-renumber"])),
        ("context", lambda folder: _context(folder, schema, carried)),
        ("sessions", lambda folder: _sessions(folder, schema, fixtures["nonbasis-key"], deployment)),
    )
    records = []
    for name, check in checks:
        folder = out / name
        folder.mkdir()
        evidence = check(folder)
        records.extend(evidence if isinstance(evidence, list) else [evidence])
        _write(out / "results.json", records)
    return records


class RadicalSessionPortableFailures(unittest.TestCase):
    def test_failure_boundaries_and_actual_outcomes(self):
        from human_eye_fast import ActionStageError, BlenderRadicalSession, Goal, ReferenceFrame, Translate
        from human_eye_fast import blender_radical_session as runtime

        cases = {
            "target-readback": ("target_readback", False),
            "control-after": ("target_readback", False),
            "after-context": ("context", True),
            "post-td": ("td", True),
            "post-render": ("render", True),
            "post-ao": ("ao", True),
        }
        for case, (stage, has_outcome) in cases.items():
            with self.subTest(case=case), ExitStack() as stack:
                events = []
                objects = {key: _StubObject(key, x, events)
                           for key, x in (("moving", 0.), ("reference", 2.), ("context", 4.))}
                layer = SimpleNamespace(name="test")
                scene = SimpleNamespace(frame_current=17, view_layers={"test": layer},
                                        unit_settings=SimpleNamespace(scale_length=1.))
                graph = object()
                bpy = SimpleNamespace(context=SimpleNamespace(
                    temp_override=lambda **_: nullcontext(), evaluated_depsgraph_get=lambda: graph))
                stack.enter_context(patch.dict(sys.modules, {"bpy": bpy}))
                reference = ReferenceFrame(17, 1, np.array(((1., 0., 0.), (1., 1., 0.), (1., 0., 1.))))
                session = stack.enter_context(BlenderRadicalSession(
                    scene, layer, objects, Goal("moving", "reference", 0., 0.),
                    {"moving": 1, "reference": 2, "context": 3}, reference=reference))
                session._controller.bridge = _StubBridge(case, events)
                before = _observe(session, objects, "before")
                command = Translate((.25, 0., 0.))
                plan = session.predict_action(before.observation_id, "act", command, predictor="NONE")
                if case == "post-td":
                    stack.enter_context(patch.object(runtime, "compute_cross_frame_deformation_tensor",
                                                     side_effect=RuntimeError(case)))
                elif case == "post-render":
                    stack.enter_context(patch.object(session, "_render", side_effect=RuntimeError(case)))
                elif case == "post-ao":
                    stack.enter_context(patch.object(runtime, "encode", side_effect=RuntimeError(case)))
                with self.assertRaises(ActionStageError) as failure:
                    _execute(session, objects, plan, "after")
                error = failure.exception
                self.assertEqual((error.stage, error.write_status), (stage, "written"))
                self.assertEqual([row for row in events if row[0] == "write"], [("write", "moving", .25)])
                if has_outcome:
                    self.assertEqual(error.outcome.control_after, (.25, 0., 0.))
                    self.assertEqual(error.outcome.measured_delta_m, -.25)
                else:
                    self.assertIsNone(error.outcome)
                with self.assertRaises(ValueError):
                    _execute(session, objects, plan, "retry")
