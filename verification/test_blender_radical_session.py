"""Background Blender functional replay for all frozen integration fixtures.

This runner checks public outputs and strict pixel/ray evidence. It measures
neither production latency nor resource increments.
"""

from argparse import ArgumentParser
from contextlib import ExitStack, contextmanager
from functools import partial
from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verification.integration_fixtures import PROBE_INDICES, _formal_plan, build_fixture, fixture_manifest
from verification.test_integration_preflight import (
    _command, _materialize, _native_snapshot, _pair_truth, _pngs, _world_arrays, _write,
)


def _reference_vertices(scene, moving):
    """External reference producer, with explicit world-meter conversion."""
    import bpy

    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = moving.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            local = np.array([tuple(row.co) for row in mesh.vertices], dtype=np.float64)
            matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
            scale = scene.unit_settings.scale_length
            return (local * scale) @ matrix[:3, :3].T + matrix[:3, 3] * scale
        finally:
            evaluated.to_mesh_clear()


def _changes(phase, capture_change):
    from human_eye_fast.blender_resident_bridge import MeshChange

    result = {}
    for key, flags in phase["changes"].items():
        mask = MeshChange.NONE
        for flag in flags:
            mask |= MeshChange[flag]
        result[key] = capture_change(mask)
    return result


def _decoded(result, schema):
    from verification.test_fast_affordance_out import decode_public

    package = decode_public(result.ao_bytes, schema)
    keys = [row["image"]["path"] for row in package["observations"] if row["image"] is not None]
    assert list(result.attachments) == keys
    assert all(isinstance(value, bytes) for value in result.attachments.values())
    assert isinstance(result.ao_bytes, bytes)
    return package


def _verify_public(package, snapshot, fixture, expected, phase, generations):
    from human_eye_fast.fast_bvh_clearance import SurfaceDistance
    from verification.test_blender_control import _assert_witness

    observation = package["observations"][-1]
    assert observation["observation_id"] == phase["observation_id"]
    assert observation["frame_id"] == phase["frame_id"]
    ids = package["object_ids"]
    assert list(ids) == list(generations)
    assert {ids[obj["object_index"]]: obj["topology_generation"]
            for obj in observation["objects"]} == generations
    clearance = observation["clearance"]
    distance, tolerance = _pair_truth(snapshot, fixture.target_ids)
    assert clearance["status"] == "positive_gap"
    assert tuple(ids[i] for i in clearance["target_object_indices"]) == fixture.target_ids
    assert abs(distance - expected) <= fixture.host_tolerance_m
    witnesses = (clearance["witness_a"], clearance["witness_b"])
    surface = SurfaceDistance(clearance["distance_m"],
                              *(w["original_face_id"] for w in witnesses),
                              *(tuple(w["point_m"]) for w in witnesses))
    witness_geometry = {key: {"world_vertices_m": v, "triangles": t}
                        for key, (v, t) in snapshot.items()}
    _assert_witness(SimpleNamespace(surface=surface, target_ids=fixture.target_ids),
                    witness_geometry, distance, max(tolerance, 1e-12))

    td = observation["deformation"]
    vertices, triangles = snapshot[fixture.target_ids[0]]
    assert ids[td["object_index"]] == fixture.target_ids[0]
    assert td["reference_frame"] == fixture.spec.frame_id
    assert td["sample_frames"] == [fixture.spec.frame_id]
    assert td["position_frame"] == fixture.spec.frame_id
    assert td["reduced_face_count"] == len(triangles)
    assert td["top_face_ids"] == [row["original_face_id"] for row in td["faces"]]
    assert len(td["top_face_ids"]) == min(phase["td_top_k"], len(triangles))
    for row in td["faces"]:
        centroid = vertices[triangles[row["original_face_id"]]].mean(axis=0)
        np.testing.assert_allclose(row["position_m"], centroid, rtol=0, atol=fixture.host_tolerance_m)

    image = observation["image"]
    assert image["mode"] == fixture.mode and image["path"] == phase["attachment_key_if_applicable"]
    assert (image["section"] is None) == (fixture.mode == "NATURAL")
    return observation


def _verify_meshes(snapshot, fixture, *, after=False):
    authored = _world_arrays(fixture, after=after)
    for key, (vertices, faces) in snapshot.items():
        np.testing.assert_array_equal(faces, authored[key][1])
        np.testing.assert_allclose(vertices, authored[key][0], rtol=0, atol=fixture.host_tolerance_m)


def _model_digest(model):
    arrays = {"v_weights": model.view_head.weights, "a_weights": model.action_head.weights,
              "retrieval_scale": model.retrieval_scale}
    writes = {}
    for tag, bank in (("v", model.views), ("a", model.actions)):
        writes[tag] = bank.writes
        for key in ("keys", "values", "known"):
            arrays[f"{tag}_{key}"] = getattr(bank, key)[:len(bank)]
    return {"writes": writes, "fields": {key: sha256(value.tobytes()).hexdigest()
                                         for key, value in arrays.items()}}


@contextmanager
def _audit(scene, objects, phase):
    from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
    from human_eye_fast.cerebellar_flash import CerebellarFlash
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification.cf_visual_acceptance import VisualAudit, observe

    records, captures, model_calls = {}, [], []
    original_capture = BlenderResidentBridge.capture
    original_observe = VGRenderer.observe

    def capture(bridge, key, obj, graph, scale, changes=0):
        captures.append({"phase": phase.name, "object": key, "mask": int(changes),
                         "bridge": id(bridge), "graph": graph.as_pointer()})
        return original_capture(bridge, key, obj, graph, scale, changes)

    def audited(renderer, prepared, witness, *, target_ids, frame_id, scale_length,
                mode="NATURAL", method="active", audit=False, relation=None, rank_directions=None):
        assert method == "active" and phase.name not in records
        independent = VisualAudit(_native_snapshot(scene, objects), target_ids, frame_id, mode,
                                  scale_length, witness)
        adapter = SimpleNamespace(observe=partial(original_observe, renderer))
        rendered, visual = observe(adapter, prepared, independent, rank_directions, relation=relation)
        records[phase.name] = (rendered, visual)
        return rendered

    def trace(name, operation):
        def run(model, features, *args, **kwargs):
            before = [model.views.writes, model.actions.writes]
            result = operation(model, features, *args, **kwargs)
            model_calls.append({"phase": phase.name, "method": name, "input": features.tolist(),
                                "args": args, "kwargs": kwargs, "writes_before": before,
                                "result": result,
                                "writes_after": [model.views.writes, model.actions.writes]})
            phase.model = model
            return result
        return run

    with ExitStack() as stack:
        stack.enter_context(patch.object(BlenderResidentBridge, "capture", capture))
        stack.enter_context(patch.object(VGRenderer, "observe", audited))
        for name in ("rank_view", "predict_delta", "learn_view", "learn_action"):
            stack.enter_context(patch.object(CerebellarFlash, name, trace(name, getattr(CerebellarFlash, name))))
        yield records, captures, model_calls


def _assert_captures(rows, scene_plan, objects):
    from human_eye_fast.blender_resident_bridge import MeshChange

    assert {row["phase"] for row in rows} == {"before", "after", "next"}
    assert len({row["bridge"] for row in rows}) == 1
    for phase in ("before", "after_readback_and_publication", "next"):
        spec = scene_plan[phase]
        batch = [row for row in rows if row["phase"] == spec["observation_id"]]
        assert [row["object"] for row in batch] == list(objects)
        assert len({row["graph"] for row in batch}) == 1
        expected = [sum(int(MeshChange[flag]) for flag in spec["changes"][key]) for key in objects]
        assert [row["mask"] for row in batch] == expected


@contextmanager
def _api(kind, scene, objects, goal, generations, reference, fixture, frozen, deployment, arm):
    """Use production public calls for I and explicit old component calls for B."""
    import bpy
    from human_eye_fast import (
        BlenderRadicalSession, CaptureChange, ObservationRequest, ReferenceFrame, ViewFeedback,
    )
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification import integration_reference as ref

    basis_name = fixture.command.key_name
    if kind == "I":
        with BlenderRadicalSession(
                scene, scene.view_layers[0], objects, goal, generations,
                reference=ReferenceFrame(fixture.spec.frame_id, generations[fixture.target_ids[0]], reference),
                deployment=deployment if arm != "F" else None) as session:
            if basis_name is not None:
                session.prepare_relative_basis(basis_name)
            yield SimpleNamespace(
                observe=lambda phase: session.observe(
                    ObservationRequest(phase["observation_id"], phase["mode"], arm),
                    changes=_changes(phase, CaptureChange)),
                predict=lambda current, command, action_id, predictor: session.predict_action(
                    current.observation_id, action_id, command, predictor=predictor),
                execute=lambda before, plan, phase: session.execute(
                    plan, ObservationRequest(phase["observation_id"], phase["mode"], arm),
                    changes=_changes(phase, CaptureChange)),
                view_feedback=lambda result, feedback: session.view_feedback(
                    result.view_ticket, ViewFeedback(*feedback)),
                action_feedback=lambda result: session.action_feedback(result.action_ticket),
            )
        return

    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        renderer = VGRenderer()
    model = frozen.session() if arm != "F" else None
    control = ref.SharedCaptureControl(scene, objects, goal, generations=generations,
                                       renderer=renderer, model=model)
    world_reference = ref.WorldReference(fixture.spec.frame_id, generations[fixture.target_ids[0]], reference)
    basis = ref.relative_basis_from_rna(objects[fixture.target_ids[0]], basis_name) if basis_name else None
    try:
        yield SimpleNamespace(
            observe=lambda phase: ref.observe(
                control, renderer, world_reference, phase["observation_id"], mode=phase["mode"],
                view_arm=arm, model=model, changes=_changes(phase, ref.CaptureChange)),
            predict=lambda current, command, action_id, predictor: ref.predict(
                control, current, command, action_id, action_arm=predictor, model=model, basis=basis),
            execute=lambda before, plan, phase: ref.execute(
                control, renderer, world_reference, before, plan, phase["observation_id"],
                mode=phase["mode"], view_arm=arm, model=model, changes=_changes(phase, ref.CaptureChange)),
            view_feedback=lambda result, feedback: ref.view_feedback(
                control, model, result.view, ref.ViewFeedback(*feedback)),
            action_feedback=lambda result: ref.action_feedback(control, model, result.action_ticket),
        )
    finally:
        with control.scene_context():
            control.close()


def _verify_image(public, native, scored, kind, arm):
    rendered, evidence = native
    assert rendered.png == public.attachments[next(iter(public.attachments))]
    assert scored["checks"]["native_ray_accounting"]
    if kind == "B":
        assert (public.view is None) == (arm == "F")
        if public.view is not None:
            assert public.view.index == evidence["candidate"]
        return

    assert public.image_status == "rendered"
    assert (public.view_ticket is None) == (arm == "F")
    audit = public.view_audit
    selection = evidence["metadata"]["selection"]
    assert audit.canonical_index == (evidence["candidate"] if arm != "F" else None)
    assert list(audit.direction) == selection["direction"]
    assert audit.total_rays == evidence["ray_count"]
    assert audit.native_stop == evidence["native_stop"]
    if arm != "F":
        assert list(audit.order) == evidence["order"]
    assert [{"direction": list(probe.direction), "ray_count": probe.ray_count,
             "aperture_taps": probe.aperture_taps, "target_support": probe.target_support}
            for probe in audit.probes] == selection["probes"]


def _run_arm(kind, fixture, scene_plan, arm, predictor, frozen, deployment, scorer, schema, out):
    from human_eye_fast.control import Goal

    out.mkdir(parents=True)
    phases = {name: scene_plan[key] for name, key in
              (("before", "before"), ("after", "after_readback_and_publication"), ("next", "next"))}
    generations = dict(scene_plan["before"]["topology_generations"])
    phase = SimpleNamespace(name=None, model=None)
    scores, identity, package_bytes, png_bytes = {}, {}, {}, {}
    goal = Goal(*fixture.target_ids, fixture.goal_distance_m, fixture.goal_tolerance_m)
    with _materialize(fixture) as (scene, objects):
        reference = _reference_vertices(scene, objects[fixture.target_ids[0]])
        with (_audit(scene, objects, phase) as (rendered, captures, model_calls),
              _api(kind, scene, objects, goal, generations, reference, fixture,
                   frozen, deployment, arm) as api):
            phase.name = "before"
            before = api.observe(phases["before"])
            initial_ao, initial_pngs = before.ao_bytes, dict(before.attachments)
            initial = _decoded(before, schema)
            native_before = _native_snapshot(scene, objects)
            _verify_meshes(native_before, fixture)
            prior = _verify_public(initial, native_before, fixture, fixture.expected_before_m,
                                   phases["before"], generations)
            phase.name = "predict"
            prepared = api.predict(before, _command(fixture.command), "act", predictor)
            phase.name = "after"
            transition = api.execute(before, prepared, phases["after"])
            after = transition.after if kind == "B" else transition
            joined = _decoded(transition, schema)
            native_after = _native_snapshot(scene, objects)
            _verify_meshes(native_after, fixture, after=True)
            measured = _verify_public(joined, native_after, fixture, fixture.expected_after_m,
                                       phases["after"], generations)
            assert joined["observations"][0] == prior
            assert before.ao_bytes == initial_ao and before.attachments == initial_pngs
            assert transition.attachments["before.png"] is before.attachments["before.png"]
            outcome = joined["outcome"]
            assert (outcome["before_observation_id"], outcome["after_observation_id"]) == ("before", "after")
            assert outcome["distance_before_m"] == prior["clearance"]["distance_m"]
            assert outcome["distance_after_m"] == measured["clearance"]["distance_m"]
            assert outcome["measured_delta_m"] == outcome["distance_after_m"] - outcome["distance_before_m"]
            assert not outcome["goal_reached"]
            if fixture.command.kind == "set_shape_key":
                assert outcome["control_before"] == fixture.command.control_before
                assert outcome["control_after"] == fixture.command.target_value
            else:
                np.testing.assert_allclose(np.subtract(outcome["control_after"], outcome["control_before"]),
                                           fixture.command.delta_world_m, rtol=0, atol=fixture.host_tolerance_m)
            predicted = (prepared.action.predicted_delta_m if kind == "B" else prepared.predicted_delta_m)
            assert outcome["predicted_delta_m"] == predicted
            for name, delta in fixture.expected_obstacle_delta_m.items():
                displacement = native_after[name][0] - native_before[name][0]
                np.testing.assert_allclose(displacement, np.broadcast_to(delta, displacement.shape),
                                           rtol=0, atol=fixture.host_tolerance_m)

            phase.name = "feedback"
            for role, publication in (("before", before), ("after", after)):
                image, record = rendered[role]
                png = publication.attachments[f"{role}.png"]
                score = scorer.score(png, record)
                # For I, the after publication contains both attachments.
                audit_public = publication if role == "before" or kind == "B" else SimpleNamespace(
                    attachments={"after.png": png}, image_status=after.image_status,
                    view_ticket=after.view_ticket, view_audit=after.view_audit)
                _verify_image(audit_public, rendered[role], score, kind, arm)
                assert png == image.png
                scores[role] = score
                _write(out / f"{role}.visual.json", {"evidence": record, "score": score})
                if arm != "F":
                    api.view_feedback(publication, (role, f"{role}.png", record["candidate"], score["pixel_success"]))
            assert (transition.action_ticket is not None) == (predictor == "L")
            if transition.action_ticket is not None:
                api.action_feedback(transition)
            feedback_state = _model_digest(phase.model) if phase.model is not None else None

            phase.name = "next"
            following = api.observe(phases["next"])
            followup = api.predict(following, _command(fixture.followup_command), "next-act", predictor)
            assert followup is not None
            subsequent = _decoded(following, schema)
            next_observation = _verify_public(subsequent, native_after, fixture, fixture.expected_after_m,
                                              phases["next"], generations)
            assert next_observation["clearance"] == measured["clearance"]
            assert next_observation["deformation"] == measured["deformation"]
            following_png = following.attachments["next.png"]
            _, next_record = rendered["next"]
            scores["next"] = scorer.score(following_png, next_record)
            _verify_image(following, rendered["next"], scores["next"], kind, arm)
            _write(out / "next.visual.json", {"evidence": next_record, "score": scores["next"]})
            if feedback_state is not None:
                assert _model_digest(phase.model) == feedback_state
                assert feedback_state["writes"] == {"v": 242, "a": 240 + (predictor == "L")}
                next_calls = [event for event in model_calls if event["phase"] == "next"]
                assert [event["method"] for event in next_calls] == [
                    "rank_view", *(["predict_delta"] if predictor == "L" else [])]
                assert all(event["writes_before"] == [242, 240 + (predictor == "L")] for event in next_calls)
            else:
                assert model_calls == []

            assert before.ao_bytes == initial_ao and before.attachments == initial_pngs
            _assert_captures(captures, scene_plan, objects)
            for role, publication in (("before", before), ("transition", transition), ("next", following)):
                identity[role] = _pngs(out, role, publication)
                package_bytes[role] = publication.ao_bytes
                png_bytes.update(publication.attachments)
            next_prediction = followup.action.predicted_delta_m if kind == "B" else followup.predicted_delta_m
            report = {"capture_calls": captures, "model_calls": model_calls, "feedback_state": feedback_state,
                      "pngs": identity, "measured_delta_m": outcome["measured_delta_m"],
                      "predicted_delta_m": predicted, "next_prediction_m": next_prediction}
        assert before.ao_bytes == initial_ao and before.attachments == initial_pngs
    _write(out / "record.json", report)
    return report, package_bytes, png_bytes, scores


def _main_cases(out, frozen, deployment, scorer, schema):
    records = []
    specs = fixture_manifest()
    for arm, selected in (("L", specs), ("F", [specs[i] for i in PROBE_INDICES]),
                          ("R", [specs[i] for i in PROBE_INDICES])):
        for spec in selected:
            scene_plan = _formal_plan(spec)
            fixture = build_fixture(spec)
            predictor = scene_plan["arms"]["deployment"]["predictor"] if arm == "L" else "G"
            folder = out / arm / spec.case_id
            baseline = _run_arm("B", fixture, scene_plan, arm, predictor, frozen, deployment, scorer, schema, folder / "B")
            candidate = _run_arm("I", fixture, scene_plan, arm, predictor, frozen, deployment, scorer, schema, folder / "I")
            b, b_ao, b_png, b_scores = baseline
            i, i_ao, i_png, i_scores = candidate
            assert b_ao == i_ao and b_png == i_png, (spec.case_id, arm, "public bytes differ")
            assert b_scores == i_scores, (spec.case_id, arm, "strict scores differ")
            for field in ("model_calls", "feedback_state", "measured_delta_m", "predicted_delta_m", "next_prediction_m"):
                assert b[field] == i[field], (spec.case_id, arm, field)
            if arm == "L" and spec.case_id == "I-carried-screen-0":
                assert not b_scores["after"]["passed"] and not b_scores["after"]["safe"]
                assert [key for key, value in b_scores["after"]["checks"].items() if not value] == ["directions"]
            records.append({"case": spec.case_id, "view_arm": arm, "predictor": predictor,
                            "byte_exact": True, "active_state_exact": True,
                            "strict_scores": {role: {"passed": score["passed"], "safe": score["safe"],
                                                     "failed_checks": [key for key, ok in score["checks"].items() if not ok]}
                                              for role, score in b_scores.items()}})
            _write(out / "main-results.json", records)
    return records


def run(out, snapshot, deployment_path, pillow_python, group="all"):
    import bpy
    from human_eye_fast.cf_deployment import load_cf_deployment
    from human_eye_fast.fast_affordance_out import public_schema
    from verification.cf_training import load_frozen
    from verification.cf_visual_acceptance import PillowWorker
    from verification.integration_fixtures import DEPLOYMENT_SNAPSHOTS

    assert bpy.app.background
    out.mkdir(parents=True)
    snapshot_hash = sha256(snapshot.read_bytes()).hexdigest()
    assert snapshot_hash == DEPLOYMENT_SNAPSHOTS[0][1]
    frozen = load_frozen(snapshot)
    deployment = load_cf_deployment(deployment_path)
    schema = public_schema()
    _write(out / "schema.json", schema)
    with PillowWorker(pillow_python) as scorer:
        main = _main_cases(out, frozen, deployment, scorer, schema) if group in ("all", "main") else []
        if group in ("all", "controls"):
            from verification.test_radical_session_controls import run_controls
            controls = run_controls(out / "controls", deployment, schema)
        else:
            controls = []
    _write(out / "summary.json", {
        "blender": bpy.app.version_string, "scope": "functional acceptance only",
        "frozen_sha256": snapshot_hash, "deployment_sha256": sha256(deployment_path.read_bytes()).hexdigest(),
        "main": main, "controls": controls,
    })


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--pillow-python", type=Path, required=True)
    parser.add_argument("--group", choices=("all", "main", "controls"), default="all")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    run(options.out, options.snapshot, options.deployment, options.pillow_python, options.group)
