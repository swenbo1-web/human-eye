"""Blender boundary contracts using small main-thread bpy test doubles.

These tests validate the connector contract, not real Blender evaluation. The
headless Blender integration check exercises Blender's actual matrix precision.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "human_eye_plugin" / "blender_host.py"
_spec = importlib.util.spec_from_file_location("blender_host_contract_test_module", MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
BlenderSceneHost, BlenderHostError = _module.BlenderSceneHost, _module.BlenderHostError


class FakeMatrix(list):
    pass


class FakeRNAWrapper:
    def __init__(self, target, pointer):
        self._target, self._pointer = target, pointer

    def as_pointer(self):
        return self._pointer

    def __getattr__(self, name):
        return getattr(self._target, name)


def matrix(translation=(0, 0, 0), scales=(1, 1, 1)):
    return FakeMatrix([[scales[0], 0., 0., translation[0]],
                       [0., scales[1], 0., translation[1]],
                       [0., 0., scales[2], translation[2]], [0., 0., 0., 1.]])


class FakeMesh:
    def __init__(self):
        self.vertices = [NS(co=p) for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))]
        self.loop_triangles = [NS(vertices=f) for f in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))]
        self.shape_keys = self.animation_data = None

    def calc_loop_triangles(self):
        pass


class FakeObject:
    def __init__(self, name, translation=(0, 0, 0)):
        self.name = self.name_full = name
        self.type, self.instance_type, self.mode = "MESH", "NONE", "OBJECT"
        self.is_instancer = False
        self.library = self.parent = self.animation_data = self.rigid_body = self.rigid_body_constraint = None
        self.children, self.constraints, self.modifiers = [], [], []
        self.color = (0.5, 0.25, 1., 1.)
        self.lock_location = self.lock_rotation = self.lock_scale = (False, False, False)
        self.data = FakeMesh()
        self._matrix_world = matrix(translation)
        self.assignments = self.clears = 0
        self.hide_viewport = self.hide_render = False
        self.fail_read_after_assignment = False
        self._failed_once = False

    @property
    def matrix_world(self):
        return self._matrix_world

    @matrix_world.setter
    def matrix_world(self, value):
        self.assignments += 1
        self._matrix_world = FakeMatrix([list(row) for row in value])

    def evaluated_get(self, graph):
        return self

    def to_mesh(self):
        if self.fail_read_after_assignment and self.assignments == 1 and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("Simulated evaluation failure")
        return self.data

    def to_mesh_clear(self):
        self.clears += 1


def host_fixture(scale=1):
    focal, reference = FakeObject("Focal", (2, 3, 4)), FakeObject("Reference", (5, 0, 0))
    graph = NS(object_instances=[])
    layer = NS(update=lambda: None, depsgraph=graph, objects=NS(active=focal))
    scene = NS(objects=[reference, focal], unit_settings=NS(scale_length=scale), frame_current=1, view_layers=[layer])
    graph.scene_eval = NS(original=scene)
    bpy = NS(context=NS(scene=scene, view_layer=layer, evaluated_depsgraph_get=lambda: graph))
    return BlenderSceneHost(bpy), focal, reference, graph


class BlenderHostContracts(unittest.TestCase):
    def test_standalone_file_import_has_no_engine_or_blender_dependencies(self):
        code = ("import runpy,sys; runpy.run_path(sys.argv[1]); "
                "assert not any(m in sys.modules for m in ['numpy','PIL','bpy','human_eye_plugin'])")
        result = subprocess.run([sys.executable, "-I", "-c", code, str(MODULE_PATH)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_snapshot_is_stable_finite_json_and_does_not_assign(self):
        host, focal, reference, _ = host_fixture()
        first, second = host.capture_scene(), host.capture_scene()
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)
        self.assertEqual(first["unit"], "m")
        self.assertEqual(first["source"], "blender")
        self.assertEqual(focal.assignments + reference.assignments, 0)
        self.assertEqual(focal.clears, 2)
        self.assertEqual(len(first["meshes"]), 2)

    def test_world_vertices_pivots_and_translation_use_metre_units(self):
        host, focal, _, _ = host_fixture(0.01)
        before = host.capture_scene()
        mesh = next(m for m in before["meshes"] if m["object_id"] == host.object_id(focal))
        self.assertEqual(mesh["pivot_world"], [0.02, 0.03, 0.04])
        result = host.apply_transform({"focal_id": mesh["object_id"], "translation": [0.01, 0.02, -0.01]}, before["revision"])
        after = next(m for m in result["scene"]["meshes"] if m["object_id"] == mesh["object_id"])
        for actual, expected in zip(after["pivot_world"], [0.03, 0.05, 0.03]):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(result["receipt"]["host_execution_verified"])
        self.assertNotEqual(before["revision"], result["scene"]["revision"])

    def test_rotation_is_world_xyz_about_object_origin(self):
        host, focal, reference, _ = host_fixture()
        before = host.capture_scene()
        old_reference = copy.deepcopy(reference.matrix_world)
        result = host.apply_transform({"focal_id": host.object_id(focal), "rotation_euler_deg": [0, 0, 90]}, before["revision"])
        mesh = next(m for m in result["scene"]["meshes"] if m["object_id"] == host.object_id(focal))
        self.assertEqual(mesh["pivot_world"], [2., 3., 4.])
        for actual, expected in zip(mesh["vertices"][1], [2., 4., 4.]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(mesh["local_axes"][0][1], 1.)
        self.assertEqual(reference.matrix_world, old_reference)
        self.assertEqual(reference.assignments, 0)

    def test_euler_formula_matches_engine_for_combined_rotation(self):
        from human_eye_module1_operators import SE3AlignmentMath
        expected = SE3AlignmentMath.euler_xyz_to_matrix(13., -29., 47.)
        actual = _module._euler_xyz([13., -29., 47.])
        self.assertLess(max(abs(expected[r][c] - actual[r][c]) for r in range(3) for c in range(3)), 1e-14)

    def test_snapshot_fingerprint_matches_router_normalization(self):
        from human_eye_plugin.auto_router import _validated_scene
        host, focal, _, _ = host_fixture()
        scene = host.capture_scene()
        normalized, _, fingerprint = _validated_scene(scene)
        self.assertEqual(scene, normalized)
        result = host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, 0]}, scene["revision"], fingerprint)
        self.assertEqual(result["scene"], scene)

    def test_stale_revision_and_fingerprint_prevent_all_edits(self):
        host, focal, _, _ = host_fixture()
        scene = host.capture_scene()
        action = {"focal_id": host.object_id(focal), "translation": [1, 0, 0]}
        with self.assertRaisesRegex(BlenderHostError, "revision changed"):
            host.apply_transform(action, "stale")
        with self.assertRaisesRegex(BlenderHostError, "fingerprint changed"):
            host.apply_transform(action, scene["revision"], "incorrect")
        self.assertEqual(focal.assignments, 0)

    def test_hidden_mesh_is_included_and_partial_coverage_is_rejected(self):
        host, _, reference, _ = host_fixture()
        reference.hide_viewport = reference.hide_render = True
        self.assertEqual(len(host.capture_scene()["meshes"]), 2)
        host.object_names = frozenset(["Focal"])
        with self.assertRaisesRegex(BlenderHostError, "every scene mesh"):
            host.capture_scene()

    def test_instances_and_other_geometry_fail_closed(self):
        for kind in ("instance_object", "evaluated_instance", "curve", "geometry_nodes"):
            with self.subTest(kind=kind):
                host, focal, _, graph = host_fixture()
                if kind == "instance_object":
                    focal.instance_type = "COLLECTION"
                elif kind == "evaluated_instance":
                    graph.object_instances = [NS(is_instance=True)]
                elif kind == "curve":
                    focal.type = "CURVE"
                else:
                    focal.modifiers = [NS(type="NODES", name="GeometryNodes")]
                with self.assertRaises(BlenderHostError):
                    host.capture_scene()

    def test_unavailable_hidden_or_excluded_evaluation_never_uses_original_data(self):
        host, focal, _, _ = host_fixture()
        focal.is_evaluated = False
        with self.assertRaisesRegex(BlenderHostError, "not evaluated"):
            host.capture_scene()
        self.assertEqual(focal.clears, 0)
        self.assertEqual(focal.assignments, 0)

    def test_evaluated_modifiers_can_be_read_but_not_transformed(self):
        host, focal, _, _ = host_fixture()
        focal.modifiers = [NS(type="BEVEL", name="Bevel")]
        scene = host.capture_scene()
        with self.assertRaisesRegex(BlenderHostError, "static rigid"):
            host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, 0]}, scene["revision"])
        self.assertEqual(focal.assignments, 0)

    def test_mirror_and_shear_export_ambiguous_proper_rotation(self):
        for kind in ("mirror", "shear"):
            with self.subTest(kind=kind):
                host, focal, _, _ = host_fixture()
                focal._matrix_world[0][0] = -1 if kind == "mirror" else 1
                focal._matrix_world[0][1] = 0.3 if kind == "shear" else 0
                scene = host.capture_scene()
                mesh = next(m for m in scene["meshes"] if m["object_id"] == host.object_id(focal))
                self.assertEqual(mesh["axes_confidence"], "ambiguous")
                a = mesh["local_axes"]
                self.assertAlmostEqual(_module._dot(_module._cross(a[0], a[1]), a[2]), 1.)
                with self.assertRaisesRegex(BlenderHostError, "uniform scale"):
                    host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, 0]}, scene["revision"])

    def test_nonuniform_scale_and_dependencies_prevent_edits(self):
        for kind in ("scale", "parent", "child", "animation", "constraints", "rigid_body", "shape_keys"):
            with self.subTest(kind=kind):
                host, focal, reference, _ = host_fixture()
                if kind == "scale": reference._matrix_world[0][0] = 2
                elif kind == "parent": reference.parent = focal
                elif kind == "child": focal.children = [reference]
                elif kind == "animation": reference.animation_data = NS()
                elif kind == "constraints": reference.constraints = [NS()]
                elif kind == "rigid_body": reference.rigid_body = NS()
                else: reference.data.shape_keys = NS()
                scene = host.capture_scene()
                with self.assertRaises(BlenderHostError):
                    host.apply_transform({"focal_id": host.object_id(focal), "translation": [0.1, 0, 0]}, scene["revision"])
                self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_invalid_actions_and_empty_revision_prevent_edits(self):
        host, focal, _, _ = host_fixture()
        revision = host.capture_scene()["revision"]
        for action in ({"focal_id": host.object_id(focal), "translation": [True, 0, 0]},
                       {"focal_id": host.object_id(focal), "translation": [float("inf"), 0, 0]},
                       {"focal_id": host.object_id(focal), "translation": [0, 0, 0], "script": "bad"},
                       {"translation": [0, 0, 0]}):
            with self.assertRaises(BlenderHostError):
                host.apply_transform(action, revision)
        with self.assertRaises(BlenderHostError):
            host.apply_transform({"focal_id": host.object_id(focal), "translation": [0, 0, 0]}, "")
        self.assertEqual(focal.assignments, 0)

    def test_host_readback_failure_rolls_back_focal_matrix(self):
        host, focal, _, _ = host_fixture()
        before = host.capture_scene()
        previous = copy.deepcopy(focal.matrix_world)
        focal.fail_read_after_assignment = True
        with self.assertRaisesRegex(BlenderHostError, "rollback_verified=True"):
            host.apply_transform({"focal_id": host.object_id(focal), "translation": [0.1, 0, 0]}, before["revision"])
        self.assertEqual(focal.matrix_world, previous)
        self.assertEqual(host.capture_scene(), before)

    def test_frame_unit_and_guard_changes_invalidate_revision(self):
        host, focal, _, _ = host_fixture()
        prior = host.capture_scene()["revision"]
        for change in (lambda: setattr(host.scene, "frame_current", 2),
                       lambda: setattr(host.scene.unit_settings, "scale_length", 0.1),
                       lambda: focal.constraints.append(NS())):
            change()
            current = host.capture_scene()["revision"]
            self.assertNotEqual(prior, current)
            prior = current

    def test_main_thread_and_scene_view_layer_boundaries(self):
        host, _, _, _ = host_fixture()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaisesRegex(BlenderHostError, "main thread"):
                pool.submit(host.capture_scene).result()
        alien_layer = NS()
        with self.assertRaisesRegex(BlenderHostError, "view layer"):
            BlenderSceneHost(host.bpy, scene=host.scene, view_layer=alien_layer)
        host.view_layer.depsgraph.scene_eval = NS(original=NS())
        with self.assertRaisesRegex(BlenderHostError, "different scene"):
            host.capture_scene()

    def test_distinct_rna_wrappers_of_same_datablocks_are_accepted(self):
        host, focal, _, _ = host_fixture()
        before = host.capture_scene()
        host.scene.as_pointer = lambda: 11
        host.view_layer.as_pointer = lambda: 22
        focal.as_pointer = lambda: 33
        host.view_layer.objects.active = FakeRNAWrapper(focal, 33)
        other_host = BlenderSceneHost(host.bpy, scene=FakeRNAWrapper(host.scene, 11),
                                     view_layer=FakeRNAWrapper(host.view_layer, 22))
        self.assertEqual(other_host.capture_scene(), before)


if __name__ == "__main__":
    unittest.main()
