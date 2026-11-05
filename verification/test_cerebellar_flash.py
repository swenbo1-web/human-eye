"""CF preflight checks and three predeclared native training-fixture smokes."""

from contextlib import contextmanager
from dataclasses import asdict, replace
import json
from math import cos, pi, sin
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SMOKE_SEED = 20261105
SMOKE_V_ORDINALS = (0, 1)
SMOKE_A_ORDINAL = 0
STEPS = (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8)


def _write(path, result):
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _assert_permutation(order):
    if tuple(sorted(order)) != tuple(range(16)):
        raise ValueError(f"Expected a complete candidate permutation: {order}")


def _quantization(*points):
    """Source analytic geometry versus one finite Blender float32 update."""
    magnitude = max(float(np.abs(array).max()) for array in points if len(array))
    return 16 * np.finfo(np.float32).eps * magnitude


@contextmanager
def _materialize(fixture):
    import bpy
    from verification.test_blender_control import _mesh_object, _scene

    with _scene(7, fixture.scale_length) as scene:
        scale = scene.unit_settings.scale_length
        objects = {}
        for mesh in fixture.meshes:
            obj = _mesh_object(scene, mesh.object_id, (mesh.vertices_m / scale).tolist(),
                               mesh.triangles.tolist(), mesh.color)
            objects[mesh.object_id] = obj
            if mesh.shape_basis_m is not None:
                obj.shape_key_add(name="Basis", from_mix=False)
                key = obj.shape_key_add(name=fixture.command.key_name, from_mix=False)
                keyed = ((mesh.vertices_m + mesh.shape_basis_m) / scale).astype(np.float32)
                key.data.foreach_set("co", keyed.ravel())
                key.value = fixture.command.control_before
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            bpy.context.evaluated_depsgraph_get()
            yield scene, objects


class _TraceRays:
    def __init__(self, prepared):
        self.rays = prepared.rays
        self.owners = prepared.triangle_owners
        self.trace = []

    def ray_cast(self, origin, direction):
        hit = self.rays.ray_cast(origin, direction)
        _, _, index, depth = hit
        self.trace.append({
            "origin_m": list(origin), "direction": list(direction),
            "triangle": index, "owner": None if index is None else self.owners[index],
            "depth_m": depth,
        })
        return hit


def _native_directions(witness):
    """Test-side reconstruction of the published ring, using Blender arithmetic."""
    from mathutils import Vector

    axis = (Vector(witness.point_b) - Vector(witness.point_a)).normalized()
    fixed = Vector((1, -1, 1)).normalized()
    u = fixed - fixed.dot(axis) * axis
    eps = np.finfo(np.float32).eps
    u = u.normalized() if u.length_squared > eps ** 2 else axis.orthogonal().normalized()
    v = axis.cross(u).normalized()
    return np.asarray([(cos(k * pi / 8) * u + sin(k * pi / 8) * v).normalized()
                       for k in STEPS], dtype=np.float64)


def _bind_trace(trace, selection, canonical, witness):
    a, b = np.asarray([witness.point_a, witness.point_b], dtype=float)
    midpoint = (a + b) * .5
    axis = (b - a) / witness.distance_m
    offset = 0
    for candidate, probe in enumerate(selection["probes"]):
        np.testing.assert_allclose(probe["direction"], canonical[candidate], rtol=0, atol=2e-6)
        count = probe["ray_count"]
        aperture = probe["aperture_taps"]
        calls = trace[offset:offset + count]
        for index, call in enumerate(calls):
            np.testing.assert_allclose(call["direction"], -canonical[candidate], rtol=0, atol=2e-6)
            axial_offset = (np.asarray(call["origin_m"]) - midpoint) @ axis
            purpose = "aperture" if index < min(9, aperture + 1) else (
                "support_a" if axial_offset < 0 else "support_b")
            call.update(candidate=candidate, purpose=purpose)
        offset += count
    assert len(trace) == selection["ray_count"] == offset


def _smoke_view(fixture, renderer, out, ordinal):
    from verification.cf_baselines import view_features
    from verification.test_raycast_saccade_gpu import (
        SceneOracle, _Camera, _RayOracle, _digital_line, _image_rays, _neighbors, _pixel_record,
    )
    from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
    from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance

    import bpy

    with _materialize(fixture) as (scene, objects):
        bridge = BlenderResidentBridge()
        graph = bpy.context.evaluated_depsgraph_get()
        scale = scene.unit_settings.scale_length
        meshes = {key: bridge.capture(key, obj, graph, scale) for key, obj in objects.items()}
        targets = fixture.target_ids
        indexes = tuple(SurfaceIndex(meshes[key].world_m, meshes[key].triangles) for key in targets)
        witness = surface_distance(*indexes)
        tolerance = _quantization(*(meshes[key].world_m for key in targets))
        assert abs(witness.distance_m - fixture.expected_gap_m) <= tolerance

        snapshot = SimpleNamespace(scene=scene, scale_length=scale, target_ids=targets,
                                   objects=objects, meshes=meshes)
        oracle = SceneOracle(snapshot)
        assert oracle.matches_rb and oracle.palette_matches_rb
        prepared = renderer.prepare(meshes)
        wrapped = _TraceRays(prepared)
        canonical = _native_directions(witness)
        context = tuple((mesh.world_m, mesh.triangles) for key, mesh in meshes.items()
                        if key not in targets)
        features = view_features(witness.point_a, witness.point_b, canonical, context,
                                 section=fixture.mode == "SECTION")
        assert not wrapped.trace
        assert features.shape == (16, 5) and np.all(np.isfinite(features))
        observed = renderer.observe(replace(prepared, rays=wrapped), witness, target_ids=targets,
                                    frame_id=scene.frame_current, scale_length=scale,
                                    mode=fixture.mode, audit=True)
        meta = observed.metadata
        _bind_trace(wrapped.trace, meta["selection"], canonical, witness)
        assert oracle.unchanged(snapshot)

        local = _Camera(meta["views"]["local"], scale)
        world = _Camera(meta["views"]["global"], scale)
        assert all(local.agreement.values()) and all(world.agreement.values())
        assert abs(local.width - 32 * witness.distance_m) <= tolerance
        section = meta["section"]
        if section is None:
            assert fixture.mode == "NATURAL"
            local_rays = oracle.original
        else:
            assert fixture.mode == "SECTION" and section["kept_side"] == "<=0"
            a, b = np.asarray([witness.point_a, witness.point_b])
            normal = np.asarray(section["normal"])
            np.testing.assert_allclose(section["point_m"], (a + b) * .5, rtol=0, atol=tolerance)
            assert abs(normal @ (b - a)) <= 2e-6 * witness.distance_m
            np.testing.assert_allclose(normal, meta["selection"]["direction"], rtol=0, atol=2e-6)
            local_rays = _RayOracle(oracle.meshes, (np.asarray(section["point_m"]), normal))
        global_bottom, local_bottom = np.split(observed.bottom_rgba, 2, axis=1)
        image_audit = {
            "global": _image_rays(world, global_bottom, oracle, oracle.original),
            "local": _image_rays(local, local_bottom, oracle, local_rays),
        }
        pixels, _ = local.project(np.asarray([witness.point_a, witness.point_b]))
        quality = {
            "depth_tolerance_m": oracle.depth_tolerance,
            "witness_neighborhood_rays": {
                key: [_pixel_record(local_rays, local, local_bottom, x, y)
                      for x, y in _neighbors(point)] for key, point in zip(targets, pixels)
            },
            "interior_gap_rays": [_pixel_record(local_rays, local, local_bottom, x, y)
                                  for x, y in _digital_line(*pixels)[1:-1]],
        }
        name = f"V-{ordinal}"
        (out / f"{name}.png").write_bytes(observed.png)
        np.save(out / f"{name}-bottom.npy", observed.bottom_rgba)
        return {
            "episode_id": fixture.spec.episode_id, "sample": name, "mode": fixture.mode,
            "target_ids": list(targets), "frame_id": scene.frame_current, "scale_length": scale,
            "expected_gap_m": fixture.expected_gap_m, "analytic_gap_tolerance_m": float(tolerance),
            "witness": asdict(witness),
            "meshes": {key: {"triangles": len(mesh.triangles)} for key, mesh in meshes.items()},
            "first_observation": {"methods": {"F": {"observation": meta}}},
            "quality": {"F": quality},
            "camera_agreement": {
                name: {key: bool(ok) for key, ok in camera.agreement.items()}
                for name, camera in (("local", local), ("global", world))
            },
            "audit_image_grid": image_audit, "ray_trace": wrapped.trace,
            "feature_rows": features.tolist(),
        }


def _smoke_action(fixture, out):
    from human_eye_fast.control import Action, BlenderControl, Goal, SetShapeKey
    from human_eye_fast.fast_affordance_out import (
        AffordancePackage, ClearanceFact, ObjectFact, ObservationFact, encode, public_schema,
    )
    from verification.cf_baselines import FiniteAction, action_features, geometry_delta
    from verification.test_bc_acceptance import (
        convex_pair_oracle, exhaustive_convex_oracle, surface_tolerance,
    )
    from verification.test_blender_control import _assert_witness
    from verification.test_fast_affordance_out import decode_public
    from verification.test_raycast_saccade_gpu import _native_meshes

    import bpy

    command = fixture.command
    assert command.kind == "set_shape_key"
    moving_id, reference_id = fixture.target_ids
    with _materialize(fixture) as (scene, objects):
        goal = Goal(moving_id, reference_id, 0., 0.)
        controller = BlenderControl(scene, objects, goal)
        before = controller.observe("before")
        assert before.surface.distance_m > 0
        moving, reference = (controller.bridge.get(key) for key in fixture.target_ids)
        graph = bpy.context.evaluated_depsgraph_get()
        key_data = objects[moving_id].data.shape_keys
        q = float(key_data.evaluated_get(graph).key_blocks[command.key_name].value)
        basis = np.asarray([tuple(vertex.co) for vertex in key_data.key_blocks["Basis"].data])
        keyed = np.asarray([tuple(vertex.co) for vertex in key_data.key_blocks[command.key_name].data])
        scale = scene.unit_settings.scale_length
        displacement = ((keyed - basis) * scale) @ moving.world_from_local[:3, :3].T
        known = FiniteAction.shape_key(q, command.target_value, displacement)
        a = (moving.world_m, moving.triangles)
        b = (reference.world_m, reference.triangles)
        features, length_scale = action_features(a, b, before.surface, known)
        assert features.shape == (23,) and np.all(np.isfinite(features))
        prediction = geometry_delta(a, b, before.surface, known)
        ia = a[1][before.surface.triangle_a]
        ib = b[1][before.surface.triangle_b]
        triangle_a = a[0][ia] + (command.target_value - q) * displacement[ia]
        triangle_b = b[0][ib]
        local_distance, *_ = convex_pair_oracle(triangle_a, triangle_b)
        local_tolerance = surface_tolerance(triangle_a, [[0, 1, 2]], triangle_b, [[0, 1, 2]])
        assert abs(prediction + before.surface.distance_m - local_distance) <= local_tolerance

        def fact(readback):
            return ObservationFact(readback.observation_id, readback.frame_id,
                                   tuple(ObjectFact(key, 1) for key in fixture.target_ids),
                                   ClearanceFact(readback.target_ids, readback.surface))

        def snapshot():
            meshes = _native_meshes(SimpleNamespace(scene=scene, objects=objects, scale_length=scale))
            return {key: {"world_vertices_m": vertices.tolist(), "triangles": faces.tolist()}
                    for key, (vertices, faces) in meshes.items()}

        before_fact = fact(before)
        native_before = snapshot()
        pre = encode(AffordancePackage((before_fact,)))
        action = Action("one-command", "before", SetShapeKey(command.key_name, command.target_value),
                        prediction)
        outcome = controller.execute(action, "after")
        assert outcome is not None
        after = outcome.after
        native_after = snapshot()
        native_before_a = np.asarray(native_before[moving_id]["world_vertices_m"])
        native_after_a = np.asarray(native_after[moving_id]["world_vertices_m"])
        quantization = _quantization(native_before_a, native_after_a)
        assert outcome.control_before == q and outcome.control_before != outcome.control_after
        assert abs(outcome.control_after - command.target_value) <= 2 * np.finfo(np.float32).eps
        assert key_data.key_blocks[command.key_name].value == outcome.control_after
        np.testing.assert_allclose(native_after_a - native_before_a,
                                   (outcome.control_after - q) * displacement,
                                   rtol=0, atol=quantization)
        assert outcome.measured_delta_m == after.surface.distance_m - before.surface.distance_m
        _assert_witness(before, native_before, before.surface.distance_m, quantization)
        _assert_witness(after, native_after, after.surface.distance_m, quantization)
        independent = []
        for readback, native in ((before, native_before), (after, native_after)):
            va, fa, vb, fb = (np.asarray(native[key][field]) for key in fixture.target_ids
                              for field in ("world_vertices_m", "triangles"))
            distance, *_ = exhaustive_convex_oracle(va, fa, vb, fb)
            tolerance = surface_tolerance(va, fa, vb, fb)
            assert abs(distance - readback.surface.distance_m) <= tolerance
            independent.append({"distance_m": distance, "tolerance_m": tolerance})
        post = encode(AffordancePackage((before_fact, fact(after)), outcome))
        schema = public_schema()
        public_pre = decode_public(pre, schema)
        public_post = decode_public(post, schema)
        assert public_pre["observations"][0] == public_post["observations"][0]
        wire_outcome = public_post["outcome"]
        assert (wire_outcome["before_observation_id"], wire_outcome["after_observation_id"]) == (
            before.observation_id, after.observation_id)
        assert wire_outcome["command"]["target_value"] == command.target_value
        assert wire_outcome["control_after"] == outcome.control_after
        assert wire_outcome["measured_delta_m"] == outcome.measured_delta_m
        assert wire_outcome["predicted_delta_m"] == prediction
        (out / "A-before.json").write_bytes(pre)
        (out / "A-after.json").write_bytes(post)
        _write(out / "A-schema.json", schema)
        return {
            "episode_id": fixture.spec.episode_id, "scale_length": scale,
            "command": asdict(command), "before": asdict(before), "after": asdict(after),
            "control_before": outcome.control_before, "control_after": outcome.control_after,
            "G_predicted_delta_m": prediction, "measured_delta_m": outcome.measured_delta_m,
            "local_oracle_distance_m": local_distance, "local_oracle_tolerance_m": local_tolerance,
            "host_quantization_tolerance_m": float(quantization), "current_features": features.tolist(),
            "feature_scale_m": length_scale,
            "global_convex_oracle": independent,
            "native_before": native_before, "native_after": native_after,
        }


def _native_smoke(out):
    import bpy
    import gpu
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification.cf_fixtures import build_fixture, fixture_manifest

    if not bpy.app.background:
        raise RuntimeError("CF preflight requires background Blender")
    out.mkdir(parents=True, exist_ok=True)
    views = fixture_manifest(head="V", seed=SMOKE_SEED, split="train")
    actions = fixture_manifest(head="A", seed=SMOKE_SEED, split="train")
    renderer = VGRenderer()
    try:
        records = [_smoke_view(build_fixture(views[i]), renderer, out, i) for i in SMOKE_V_ORDINALS]
    finally:
        renderer.close()
    assert [record["mode"] for record in records] == ["NATURAL", "SECTION"]
    action = _smoke_action(build_fixture(actions[SMOKE_A_ORDINAL]), out)
    _write(out / "native.json", {
        "blender": bpy.app.version_string, "build_hash": bpy.app.build_hash.decode(),
        "numpy": np.__version__, "background": bpy.app.background, "seed": SMOKE_SEED,
        "gpu": {"backend": gpu.platform.backend_type_get(), "vendor": gpu.platform.vendor_get(),
                "renderer": gpu.platform.renderer_get(), "version": gpu.platform.version_get()},
        "view": records, "action": action,
    })
    print("CF native smoke: wrote 2 F views and 1 executed shape-key outcome", flush=True)


def _score_smoke(out):
    from PIL import Image
    from verification.vg_acceptance import verify_public_pixels

    with (out / "native.json").open(encoding="utf-8") as handle:
        records = json.load(handle)
    scores = {}
    for case in records["view"]:
        name = case["sample"]
        with Image.open(out / f"{name}.png") as image:
            hud = np.asarray(image.convert("RGBA"))
        bottom = np.load(out / f"{name}-bottom.npy", allow_pickle=False)
        quality = verify_public_pixels(case, "F", hud, bottom)
        forged = hud.copy()
        forged[44:465, 513:] = (0, 0, 0, 255)
        assert not verify_public_pixels(case, "F", forged, bottom)["passed"]
        scores[name] = {"public_pixels": quality, "audit_image_grid": case["audit_image_grid"],
                        "ray_count": len(case["ray_trace"]), "mode": case["mode"]}
    _write(out / "pixels.json", scores)
    print(json.dumps(scores, indent=2), flush=True)


class PreflightTests(unittest.TestCase):
    def test_manifest_sizes_and_group_isolation(self):
        from verification.cf_fixtures import SEEDS, fixture_manifest

        self.assertEqual(tuple(SEEDS), (20261105, 79463, 310519))
        for head in ("V", "A"):
            for seed in SEEDS:
                rows = {split: fixture_manifest(head=head, seed=seed, split=split)
                        for split in ("train", "validation", "evaluation")}
                self.assertEqual(tuple(map(len, rows.values())), (240, 60, 60))
                families = {split: {row.family for row in records} for split, records in rows.items()}
                self.assertEqual(families["train"], families["validation"])
                self.assertFalse(families["train"] & families["evaluation"])
                self.assertTrue(all(len(family) == 3 for family in families.values()))
                groups = {split: {row.group_id for row in records} for split, records in rows.items()}
                for split, records in rows.items():
                    self.assertEqual(len(groups[split]), len(records))
                self.assertEqual(len(set().union(*groups.values())), 360)
                self.assertEqual(len(fixture_manifest(head=head, seed=seed, split="control")), 12)
                for family in families["evaluation"]:
                    eval_family = [row for row in rows["evaluation"] if row.family == family]
                    if head == "V":
                        self.assertEqual(sum(row.mode == "SECTION" for row in eval_family), 10)
                    else:
                        for sign in (-1, 1):
                            for amplitude in (.1, .2):
                                self.assertEqual(sum((row.command.sign, row.command.amplitude) ==
                                                     (sign, amplitude) for row in eval_family), 5)
                for row in (row for records in rows.values() for row in records if head == "A"):
                    self.assertLessEqual(0., row.command.target_value)
                    self.assertLessEqual(row.command.target_value, 1.)

    def test_materialized_train_validation_and_control_topology(self):
        from verification.cf_fixtures import build_fixture, fixture_manifest

        checked = 0
        for split in ("train", "validation", "control"):
            for spec in fixture_manifest(split=split):
                fixture = build_fixture(spec)
                for mesh in fixture.meshes:
                    vertices, faces = mesh.vertices_m, mesh.triangles
                    self.assertEqual(vertices.shape[1:], (3,))
                    self.assertEqual(faces.shape[1:], (3,))
                    self.assertEqual(vertices.dtype, np.float64)
                    self.assertEqual(faces.dtype, np.int32)
                    if not len(faces):
                        self.assertEqual((spec.family, mesh.object_id), ("empty", "reference"))
                        continue
                    self.assertTrue(np.isfinite(vertices).all())
                    self.assertGreaterEqual(faces.min(), 0)
                    self.assertLess(faces.max(), len(vertices))
                    a, b, c = vertices[faces].transpose(1, 0, 2)
                    self.assertTrue((np.linalg.norm(np.cross(b - a, c - a), axis=1) > 0).all())
                    if mesh.shape_basis_m is not None:
                        self.assertEqual(mesh.shape_basis_m.shape, vertices.shape)
                        self.assertTrue(np.isfinite(mesh.shape_basis_m).all())
                    checked += 1
        self.assertEqual(checked, 9621)

    def test_analytic_fixture_clearance_and_box_translation(self):
        from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
        from verification.cf_baselines import FiniteAction, geometry_delta
        from verification.cf_fixtures import SEEDS, build_fixture, fixture_manifest

        for seed in SEEDS:
            views = fixture_manifest(head="V", seed=seed, split="train")
            for spec in views[:2]:
                fixture = build_fixture(spec)
                targets = [(mesh.vertices_m, mesh.triangles) for mesh in fixture.meshes[:2]]
                distance = surface_distance(*(SurfaceIndex(*mesh) for mesh in targets))
                self.assertAlmostEqual(distance.distance_m, fixture.expected_gap_m, delta=1e-14)
            for spec in fixture_manifest(head="A", seed=seed, split="control"):
                fixture = build_fixture(spec)
                a, b = [(mesh.vertices_m, mesh.triangles) for mesh in fixture.meshes]
                index_a, index_b = SurfaceIndex(*a), SurfaceIndex(*b)
                before = surface_distance(index_a, index_b)
                self.assertAlmostEqual(before.distance_m, fixture.expected_gap_m, delta=1e-14)
                command = fixture.command
                action = FiniteAction.translation(command.delta_world_m, command.control_before)
                estimate = geometry_delta(a, b, before, action)
                index_a.update(a[0] + command.delta_world_m)
                after = surface_distance(index_a, index_b)
                self.assertAlmostEqual(after.distance_m - before.distance_m,
                                       fixture.expected_delta_m, delta=1e-14)
                self.assertAlmostEqual(estimate, fixture.expected_delta_m, delta=1e-14)

    def test_canonical_ties_and_invalid_permutations(self):
        from verification.cf_baselines import CANONICAL_STEPS, FIXED_ORDER, nearest_view_order, train_scale

        self.assertEqual(CANONICAL_STEPS, STEPS)
        _assert_permutation(FIXED_ORDER)
        for corrupt in (FIXED_ORDER[:-1], (0, *FIXED_ORDER[:-1]), (*FIXED_ORDER[:-1], 16)):
            with self.assertRaises(ValueError):
                _assert_permutation(corrupt)
        query = np.zeros((16, 5))
        keys = np.stack((query, query))
        labels = np.tile((0, 1), (2, 16, 1))
        labels[0, 5] = (1, 15)
        labels[0, 9] = (1, 13)
        labels[1, 2] = (1, 13)
        scale = train_scale(keys)
        self.assertTrue(np.array_equal(scale, np.ones_like(query)))
        order = nearest_view_order(query, keys, labels, scale)
        _assert_permutation(order)
        self.assertEqual(order[:3], (9, 5, 0))
        self.assertEqual(nearest_view_order(query, keys[:0], labels[:0], scale), FIXED_ORDER)

    def test_current_occlusion_orientation_and_no_isolated_vertex_leak(self):
        from verification.cf_baselines import view_features

        a, b = np.array([-.5, 0., 0.]), np.array([.5, 0., 0.])
        directions = np.array([(0, cos(k * pi / 8), sin(k * pi / 8)) for k in STEPS])
        wall = np.array([[-2., 3., -2.], [2., 3., -2.], [0., 3., 2.]])
        indexed = np.array([[0, 1, 2]])
        raw = view_features(a, b, directions, [(wall, indexed)], section=False)
        augmented = np.vstack((wall, [1e9, -1e9, 1e9]))
        np.testing.assert_array_equal(raw, view_features(a, b, directions, [(augmented, indexed)],
                                                         section=False))
        self.assertGreater(raw[0, 2], raw[0, 3])
        self.assertGreater(raw[15, 3], raw[15, 2])
        no_obstacles = view_features(a, b, directions, (), section=True)
        self.assertTrue((no_obstacles[:, 1] == 1.).all())
        self.assertTrue((no_obstacles[:, (0, 2, 3, 4)] == 0.).all())

    def test_triangle_narrow_phase_against_independent_convex_support(self):
        from verification.cf_baselines import triangle_pair_distance
        from verification.test_bc_acceptance import convex_pair_oracle, surface_tolerance

        first = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        rng = np.random.default_rng(314)
        pairs = [
            (first, first + [0, 0, .5]), (first, first + [.2, .2, 0]),
            (first, np.array([[.2, .2, -1.], [.2, .2, 1.], [.3, .2, 1.]])),
            (first, np.repeat([[.2, .2, .2]], 3, axis=0)),
            (first, np.array([[.2, .2, -1.], [.2, .2, 1.], [.2, .2, 1.]])),
            *rng.normal(size=(24, 2, 3, 3)),
        ]
        tri = [[0, 1, 2]]
        for a, b in pairs:
            expected, *_ = convex_pair_oracle(a, b)
            self.assertAlmostEqual(triangle_pair_distance(a, b), expected,
                                   delta=surface_tolerance(a, tri, b, tri))

    def test_moving_witness_pair_and_action_time_boundary(self):
        from human_eye_fast.fast_bvh_clearance import SurfaceDistance
        from verification.cf_baselines import FiniteAction, action_features, geometry_delta

        for meters in (.001, 1.):
            a = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]) * meters
            b = a + [0, 0, .3 * meters]
            tri = np.array([[0, 1, 2]])
            witness = SurfaceDistance(.3 * meters, 0, 0, tuple(a[0]), tuple(b[0]))
            positive = FiniteAction.translation([0, 0, .1 * meters], (0, 0, 0))
            negative = FiniteAction.translation([0, 0, -.1 * meters], (0, 0, 0))
            zero = FiniteAction.translation([0, 0, 0], (0, 0, 0))
            shape = FiniteAction.shape_key(.4, .5, np.tile([0, 0, meters], (3, 1)))
            for action, expected in ((positive, -.1), (negative, .1), (zero, 0.), (shape, -.1)):
                features, length = action_features((a, tri), (b, tri), witness, action)
                delta = geometry_delta((a, tri), (b, tri), witness, action)
                self.assertAlmostEqual(delta / meters, expected, delta=2e-13)
                self.assertAlmostEqual(features[1] * length, delta, delta=2e-13 * meters)
                self.assertTrue(np.isfinite(features).all())
                self.assertFalse(hasattr(action, "control_after"))

    def test_conditional_medians_and_group_definition(self):
        from verification.cf_baselines import ConditionalConstant, FiniteAction, command_group

        small = command_group(FiniteAction.shape_key(.4, .5, []))
        large = command_group(FiniteAction.shape_key(.4, .6, []))
        opposite = command_group(FiniteAction.shape_key(.4, .2, []))
        translate = command_group(FiniteAction.translation((0, 0, -.01), (0, 0, 0)),
                                  normal=(0, 0, 1), scale=1.)
        self.assertEqual((small[1:], large[1:], opposite[1:], translate[1:]),
                         ((1, 1), (1, 2), (-1, 2), (-1, 1)))
        fit = ConditionalConstant([small, small, large], [1., 3., 10.])
        self.assertEqual(fit.predict(small), 2.)
        self.assertEqual(fit.predict(large), 10.)
        self.assertEqual(fit.predict(opposite), 3.)
        self.assertEqual(fit.predict(translate), 3.)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if argv and argv[0] == "native-smoke":
        _native_smoke(Path(argv[1]).resolve())
    elif argv and argv[0] == "score-smoke":
        _score_smoke(Path(argv[1]).resolve())
    else:
        unittest.main(argv=[sys.argv[0], *argv])
