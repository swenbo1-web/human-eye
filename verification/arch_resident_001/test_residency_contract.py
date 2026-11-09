"""Independent resident-scene regressions using bpy doubles, never Blender.

Real dependency notifications are modelled explicitly for geometry edits. A
host without notification hooks is checked only for freshness, not reuse.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "arch_resident_contract_bpy_doubles", ROOT / "verification/test_blender_host_contracts.py")
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
Host = fixture.BlenderSceneHost
HostError = fixture.BlenderHostError


def prepare_object(obj, uid):
    obj.session_uid = uid
    obj.data.session_uid = uid + 10000
    obj.is_evaluated = True
    obj.bound_box = list(itertools.product((0., 1.), repeat=3))
    obj.data.polygons = [NS(vertices=tuple(t.vertices), loop_start=i * 3,
                            loop_total=3) for i, t in enumerate(obj.data.loop_triangles)]
    obj.data.loops = [NS(vertex_index=j) for p in obj.data.polygons for j in p.vertices]
    return obj


def make_host(*, hooks=True):
    original, focal, reference, graph = fixture.host_fixture()
    bpy = original.bpy
    for uid, obj in enumerate((focal, reference), 101):
        prepare_object(obj, uid)
    bpy.context.scene.session_uid = 41
    bpy.context.scene.name = "ResidentQA"
    bpy.context.scene.frame_subframe = 0.
    bpy.data = NS(filepath="resident-qa.blend")
    bpy.app = NS(driver_namespace={})
    if hooks:
        bpy.app.handlers = NS(depsgraph_update_post=[], undo_post=[], redo_post=[],
                              load_post=[], persistent=lambda callback: callback)
    graph.updates = []
    host = Host(bpy, execution_metadata=True, identity_metadata=True)
    fixture._module._READONLY_LOADED_HOST_SHA256 = hashlib.sha256(
        (ROOT / "human_eye_plugin/blender_host.py").read_bytes()).hexdigest()
    return host, focal, reference, graph


def notify_geometry(host, graph, obj, *, via_data=False):
    graph.updates = [NS(id=obj.data if via_data else obj, is_updated_geometry=True,
                        is_updated_transform=False)]
    for callback in tuple(host.bpy.app.handlers.depsgraph_update_post):
        callback(host.bpy.context.scene, graph)
    graph.updates = []


def selected(host, names=("Focal", "Reference")):
    return host.capture_task_scene([{"name": name} for name in names])


def by_name(capture, name):
    return next(mesh for mesh in capture["meshes"] if mesh["name"] == name)


def delta_module():
    path = ROOT / "human_eye_plugin/scene_residency.py"
    spec = importlib.util.spec_from_file_location("arch_resident_delta_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def codec_fixture(*, offset=0., instance="source-A", epoch=1, revision=1):
    local = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
    resource = dict(resource_id="mesh-A", revision=1, vertices_local=local,
                    faces=[[0, 1, 2]], edges=[[0, 1], [0, 2], [1, 2]])
    matrix = fixture.matrix((offset, 0., 0.))
    scene = dict(unit="m", coordinate_frame="world", source="blender", revision="r" + str(revision),
                 capture_scope="selected_objects",
                 capture_state=dict(instance_id=instance, epoch=epoch, revision=revision,
                                    selection_key="same-selection"),
                 meshes=[dict(object_id="object-A", name="A", vertices=[[p[0] + offset, p[1], p[2]]
                             for p in local], faces=copy.deepcopy(resource["faces"]),
                             edges=copy.deepcopy(resource["edges"]))])
    return scene, {"object-A": (resource, matrix, 1.)}


class DeltaReconstructionTests(unittest.TestCase):
    def test_full_then_pose_delta_reconstructs_exact_public_capture(self):
        module = delta_module()
        decoder = module.SceneDeltaDecoder()
        scene, binding = codec_fixture()
        first = module.encode_capture(scene, None, binding)
        self.assertEqual(decoder.apply(first), scene)
        moved, changed_binding = codec_fixture(offset=2., revision=2)
        second = module.encode_capture(moved, decoder.baseline(), changed_binding)
        self.assertLess(len(json.dumps(second)), len(json.dumps(first)))
        self.assertEqual(decoder.apply(second), moved)
        self.assertEqual(scene["meshes"][0]["vertices"][0], [0., 0., 0.])

    def test_nearest_outer_packet_preserves_full_coverage_and_binding(self):
        module = delta_module()
        decoder = module.SceneDeltaDecoder()
        scene, binding = codec_fixture()
        scene["capture_scope"] = "surface_nearest_candidates"
        packet = dict(protocol="single-read-surface-candidates-v1", capture=scene,
                      focal_id="object-A", coverage=[dict(object_id="object-A", disposition="retained"),
                      dict(object_id="object-B", disposition="excluded_strict_bound")],
                      binding=dict(frame=4, unit="m"), execution_authority=False,
                      result_kind="acquisition_only_not_nearest_result")
        self.assertEqual(decoder.apply(module.encode_capture(packet, None, binding)), packet)
        self.assertEqual(decoder.apply(module.encode_capture(packet, decoder.baseline(), binding)), packet)

    def test_new_epoch_or_instance_cannot_reuse_old_resource_implicitly(self):
        module = delta_module()
        for new_instance, new_epoch in (("source-A", 2), ("source-B", 1)):
            with self.subTest(instance=new_instance, epoch=new_epoch):
                decoder = module.SceneDeltaDecoder()
                scene, binding = codec_fixture()
                decoder.apply(module.encode_capture(scene, None, binding))
                old = decoder.baseline()
                other, next_binding = codec_fixture(instance=new_instance, epoch=new_epoch)
                wire = module.encode_capture(other, old, next_binding)
                self.assertEqual(decoder.apply(wire), other)
                decoder = module.SceneDeltaDecoder()
                decoder.apply(module.encode_capture(scene, None, binding))
                corrupted = copy.deepcopy(wire)
                corrupted["resources"] = []
                with self.assertRaises(ValueError):
                    decoder.apply(corrupted)
                self.assertEqual(decoder.baseline(), old)

    def test_rejected_delta_does_not_commit_partial_resource_revisions(self):
        module = delta_module()
        decoder = module.SceneDeltaDecoder()
        scene, binding = codec_fixture()
        first = module.encode_capture(scene, None, binding)
        decoder.apply(first)
        old = decoder.baseline()
        bad = copy.deepcopy(first)
        bad["resources"][0]["revision"] = 2
        bad["capture"]["meshes"][0]["_scene_resource"]["id"] = "missing"
        with self.assertRaises(ValueError):
            decoder.apply(bad)
        self.assertEqual(decoder.baseline(), old)
        self.assertEqual(decoder.apply(module.encode_capture(scene, old, binding)), scene)


class ResidencyContractTests(unittest.TestCase):
    def state(self, capture):
        value = capture["capture_state"]
        self.assertEqual(set(value), {"instance_id", "epoch", "revision", "selection_key"})
        for key in ("instance_id", "selection_key"):
            self.assertIs(type(value[key]), str)
            self.assertTrue(value[key])
        for key in ("epoch", "revision"):
            self.assertIs(type(value[key]), int)
            self.assertGreaterEqual(value[key], 0)
        return value

    def assert_source_changed(self, before, after):
        a, b = self.state(before), self.state(after)
        self.assertNotEqual(tuple(a[k] for k in ("instance_id", "epoch", "revision")),
                            tuple(b[k] for k in ("instance_id", "epoch", "revision")))

    def test_unchanged_selected_capture_reuses_expansion_and_token(self):
        host, focal, reference, _ = make_host()
        first = selected(host)
        expanded = focal.clears + reference.clears
        second = selected(host)
        self.assertEqual(self.state(first), self.state(second))
        self.assertEqual(first, second)
        self.assertEqual(focal.clears + reference.clears, expanded)

    def test_rename_and_old_name_binding_are_not_cached(self):
        host, focal, _, _ = make_host()
        first = selected(host)
        focal.name = focal.name_full = "Renamed"
        second = selected(host, ("Renamed", "Reference"))
        self.assert_source_changed(first, second)
        self.assertEqual({m["name"] for m in second["meshes"]}, {"Renamed", "Reference"})
        missing = selected(host)
        self.assertEqual(missing["task_selection"]["bindings"][0]["status"], "unknown")
        self.assertNotIn("Focal", {m["name"] for m in missing["meshes"]})

    def test_delete_and_same_name_replacement_change_incarnation(self):
        host, focal, _, _ = make_host()
        first = selected(host)
        host.scene.objects.remove(focal)
        deleted = selected(host)
        self.assert_source_changed(first, deleted)
        self.assertEqual(deleted["task_selection"]["bindings"][0]["status"], "unknown")
        replacement = prepare_object(fixture.FakeObject("Focal", (2, 3, 4)), 777)
        host.scene.objects.append(replacement)
        replaced = selected(host)
        self.assert_source_changed(first, replaced)
        oid = host.object_id(replacement)
        self.assertEqual(replaced["host_identity"]["object_instances"][oid], "777")
        self.assertEqual(by_name(first, "Focal")["vertices"],
                         by_name(replaced, "Focal")["vertices"])

    def test_same_count_vertex_edit_via_mesh_event_is_fresh(self):
        host, focal, _, graph = make_host()
        first = selected(host)
        focal.data.vertices[0].co = (0.25, 0., 0.)
        notify_geometry(host, graph, focal, via_data=True)
        second = selected(host)
        self.assert_source_changed(first, second)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [2.25, 3., 4.])

    def test_transform_updates_pose_without_reexpanding_unchanged_mesh(self):
        host, focal, reference, _ = make_host()
        first = selected(host)
        expanded = focal.clears + reference.clears
        focal._matrix_world[0][3] += 1.
        second = selected(host)
        self.assert_source_changed(first, second)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [3., 3., 4.])
        self.assertEqual(focal.clears + reference.clears, expanded)

    def test_evaluated_transform_event_is_fresh_when_original_matrix_does_not_move(self):
        host, focal, _, graph = make_host()
        evaluated = prepare_object(fixture.FakeObject("Focal", (2, 3, 4)), 301)
        evaluated.data = focal.data
        focal.evaluated_get = lambda _graph: evaluated
        first = selected(host)
        expanded = evaluated.clears
        evaluated._matrix_world[0][3] += 4.
        graph.updates = [NS(id=focal, is_updated_geometry=False, is_updated_transform=True)]
        for callback in tuple(host.bpy.app.handlers.depsgraph_update_post):
            callback(host.scene, graph)
        graph.updates = []
        second = selected(host)
        self.assert_source_changed(first, second)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [6., 3., 4.])
        self.assertEqual(evaluated.clears, expanded)

    def test_shared_mesh_notification_updates_every_object_using_that_data(self):
        host, focal, reference, graph = make_host()
        reference.data = focal.data
        selected(host)
        focal.data.vertices[0].co = (0.25, 0., 0.)
        notify_geometry(host, graph, focal, via_data=True)
        second = selected(host)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [2.25, 3., 4.])
        self.assertEqual(by_name(second, "Reference")["vertices"][0], [5.25, 0., 0.])

    def test_units_and_frame_invalidate_even_with_same_local_mesh(self):
        host, _, _, _ = make_host()
        first = selected(host)
        host.scene.unit_settings.scale_length = 0.01
        scaled = selected(host)
        self.assert_source_changed(first, scaled)
        self.assertEqual(by_name(scaled, "Focal")["vertices"][0], [0.02, 0.03, 0.04])
        host.scene.frame_current += 1
        framed = selected(host)
        self.assert_source_changed(scaled, framed)

    def test_undo_redo_and_load_handlers_reset_epoch_with_identical_geometry(self):
        host, _, _, _ = make_host()
        previous = selected(host)
        for name in ("undo_post", "redo_post", "load_post"):
            callbacks = tuple(getattr(host.bpy.app.handlers, name))
            self.assertTrue(callbacks, name + " residency lifecycle hook missing")
            for callback in callbacks:
                callback(None)
            current = selected(host)
            self.assert_source_changed(previous, current)
            self.assertNotEqual((self.state(previous)["instance_id"], self.state(previous)["epoch"]),
                                (self.state(current)["instance_id"], self.state(current)["epoch"]))
            previous = current

    def test_implicit_host_tracks_scene_switch_but_not_old_geometry(self):
        host, _, _, _ = make_host()
        first = selected(host)
        focal = prepare_object(fixture.FakeObject("Focal", (20, 0, 0)), 201)
        reference = prepare_object(fixture.FakeObject("Reference", (30, 0, 0)), 202)
        graph = NS(object_instances=[], updates=[])
        layer = NS(update=lambda: None, depsgraph=graph, objects=NS(active=focal))
        scene = NS(objects=[focal, reference], unit_settings=NS(scale_length=1.),
                   frame_current=1, frame_subframe=0., view_layers=[layer], session_uid=42,
                   name="OtherScene")
        graph.scene_eval = NS(original=scene)
        host.bpy.context.scene, host.bpy.context.view_layer = scene, layer
        host.bpy.context.evaluated_depsgraph_get = lambda: graph
        second = selected(host)
        self.assert_source_changed(first, second)
        self.assertNotEqual((self.state(first)["instance_id"], self.state(first)["epoch"]),
                            (self.state(second)["instance_id"], self.state(second)["epoch"]))
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [20., 0., 0.])

    def test_selection_key_distinguishes_role_order(self):
        host, _, _, _ = make_host()
        first = selected(host)
        inverse = selected(host, ("Reference", "Focal"))
        self.assertNotEqual(self.state(first)["selection_key"],
                            self.state(inverse)["selection_key"])
        self.assertEqual(inverse["task_selection"]["selectors"],
                         [{"name": "Reference"}, {"name": "Focal"}])

    def test_capture_return_value_cannot_poison_resident_vertices(self):
        host, _, _, _ = make_host()
        first = selected(host)
        by_name(first, "Focal")["vertices"][0][0] = -9999.
        by_name(first, "Focal")["faces"][0][0] = 9999
        second = selected(host)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [2., 3., 4.])
        self.assertTrue(all(max(face) < len(by_name(second, "Focal")["vertices"])
                            for face in by_name(second, "Focal")["faces"]))

    def test_no_hooks_fake_still_reads_direct_edits_fresh(self):
        host, focal, _, _ = make_host(hooks=False)
        selected(host)
        focal.data.vertices[0].co = (0.5, 0., 0.)
        second = selected(host)
        self.assertEqual(by_name(second, "Focal")["vertices"][0], [2.5, 3., 4.])

    def test_selected_subset_does_not_narrow_nearest_coverage(self):
        host, _, _, _ = make_host()
        far = prepare_object(fixture.FakeObject("Far", (100, 0, 0)), 103)
        host.scene.objects.append(far)
        selected(host)
        result = host.capture_nearest_candidates(None, time.perf_counter_ns() + 5_000_000_000,
                                                  2_000_000, selector={"name": "Focal"})
        expected = {host.object_id(o) for o in host.scene.objects}
        self.assertEqual({r["object_id"] for r in result["coverage"]}, expected)
        self.assertEqual(result["work"]["directory_objects"], 3)
        self.assertEqual(result["result_kind"], "acquisition_only_not_nearest_result")
        self.assertIs(result["execution_authority"], False)
        self.state(result["capture"])

    def test_warm_nearest_does_not_keep_old_candidate_directory(self):
        host, _, _, _ = make_host()
        first = host.capture_nearest_candidates(None, time.perf_counter_ns() + 5_000_000_000,
                                                 2_000_000, selector={"name": "Focal"})
        new = prepare_object(fixture.FakeObject("NewNear", (2, 3, 4)), 778)
        host.scene.objects.append(new)
        second = host.capture_nearest_candidates(None, time.perf_counter_ns() + 5_000_000_000,
                                                  2_000_000, selector={"name": "Focal"})
        self.assert_source_changed(first["capture"], second["capture"])
        self.assertEqual({r["object_id"] for r in second["coverage"]},
                         {host.object_id(o) for o in host.scene.objects})
        self.assertIn(host.object_id(new), {m["object_id"] for m in second["capture"]["meshes"]})

    def test_late_encoding_old_capture_does_not_mix_new_resource_binding(self):
        host, focal, _, graph = make_host()
        decoder = delta_module().SceneDeltaDecoder()
        first = selected(host)
        focal.data.vertices[0].co = (0.5, 0., 0.)
        notify_geometry(host, graph, focal)
        second = selected(host)
        self.assertEqual(decoder.apply(host.capture_delta(first)), first)
        self.assertEqual(decoder.apply(host.capture_delta(second, decoder.baseline())), second)

    def test_legacy_write_rejects_old_revision_after_cached_pose_change(self):
        host, focal, _, _ = make_host()
        before = host.capture_scene()
        selected(host)
        focal._matrix_world[0][3] += 1.
        with self.assertRaises(HostError):
            host.apply_transform({"focal_id": host.object_id(focal), "translation": [1., 0., 0.]},
                                 before["revision"])
        self.assertEqual(focal.assignments, 0)

    def test_native_evidence_does_not_reuse_stale_selected_mesh(self):
        host, focal, _, graph = make_host()
        selected(host)
        focal.data.vertices[0].co = (0.375, 0., 0.)
        notify_geometry(host, graph, focal)
        packet = host.capture_readonly_evidence()
        native = next(o for o in packet["native_scene"]["objects"] if o["name"] == "Focal")
        self.assertEqual(native["world_vertices"][0], [2.375, 3., 4.])
        self.assertIs(packet["coherence"]["raw_original_mesh_verified"], True)


class LegacyNormalizerCompatibilityTests(unittest.TestCase):
    def test_resident_capture_normalizes_then_zero_apply_succeeds(self):
        # This integration check needs the project's installed dependencies;
        # run with the verification venv's normal site configuration, not -S.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from human_eye_plugin.auto_router import _validated_scene
        host, focal, _, _ = make_host()
        capture = host.capture_scene()
        self.assertIn("capture_state", capture)
        normalized, _, fingerprint = _validated_scene(capture)
        self.assertNotIn("capture_state", normalized)
        result = host.apply_transform(
            {"focal_id": host.object_id(focal), "translation": [0., 0., 0.]},
            capture["revision"], fingerprint)
        self.assertEqual(result["scene"], normalized)


if __name__ == "__main__":
    unittest.main()
