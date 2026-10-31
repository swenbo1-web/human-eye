"""Optional identity binding: schema checks and read-only Blender test doubles.

These tests do not validate the installed Blender version's session_uid or
file-load events. Actual host capability still requires separate integration.
"""
import copy
from types import SimpleNamespace as NS
import unittest

from human_eye_plugin.auto_router import _validated_scene
from verification.test_auto_router import scene
from verification.test_blender_host_contracts import (
    BlenderHostError, BlenderSceneHost, FakeObject, host_fixture,
)


def identity_scene():
    value = scene()
    value["host_identity"] = {"schema_version": "1.0", "document_epoch": "fixture-document-1",
        "object_instances": {"base": "11", "part": "12"},
        "capture_scope": "complete_scene_meshes"}
    return value


def identity_host():
    host, focal, reference, graph = host_fixture()
    host.bpy.app = NS(driver_namespace={})
    host.bpy.data = NS(filepath="fixture.blend")
    host.scene.session_uid = 100
    focal.session_uid, reference.session_uid = 101, 102
    host.identity_metadata = True
    return host, focal, reference, graph


class HostIdentityNormalizationTests(unittest.TestCase):
    def test_absent_identity_preserves_old_normalized_shape(self):
        value = scene()
        normalized, _, fingerprint = _validated_scene(value)
        self.assertNotIn("host_identity", normalized)
        self.assertEqual(normalized, value)
        self.assertEqual(len(fingerprint), 64)

    def test_valid_identity_is_detached_and_in_fingerprint(self):
        value = identity_scene()
        before = copy.deepcopy(value)
        normalized, _, fingerprint = _validated_scene(value)
        self.assertEqual(value, before)
        self.assertEqual(normalized["host_identity"], value["host_identity"])
        normalized["host_identity"]["object_instances"]["part"] = "changed-return"
        self.assertEqual(value["host_identity"]["object_instances"]["part"], "12")
        changed = copy.deepcopy(value)
        changed["host_identity"]["object_instances"]["part"] = "new-incarnation"
        self.assertNotEqual(fingerprint, _validated_scene(changed)[2])
        changed = copy.deepcopy(value)
        changed["host_identity"]["document_epoch"] = "new-document"
        self.assertNotEqual(fingerprint, _validated_scene(changed)[2])

    def test_identity_schema_and_capture_scope_are_strict(self):
        for field, bad in (("schema_version", "2.0"), ("schema_version", True),
                           ("capture_scope", "partial_scene_meshes"),
                           ("capture_scope", ""), ("capture_scope", None)):
            value = identity_scene()
            value["host_identity"][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                _validated_scene(value)

    def test_identity_requires_exact_declared_fields(self):
        for omitted in identity_scene()["host_identity"]:
            value = identity_scene()
            value["host_identity"].pop(omitted)
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                _validated_scene(value)
        value = identity_scene()
        value["host_identity"]["execution_authority"] = True
        with self.assertRaises(ValueError):
            _validated_scene(value)
        for bad in (None, [], "declared", True):
            value["host_identity"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _validated_scene(value)

    def test_document_epoch_requires_nonempty_bounded_text(self):
        for bad in (None, True, 123, "", "d" * 257):
            value = identity_scene()
            value["host_identity"]["document_epoch"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _validated_scene(value)

    def test_instance_map_exactly_covers_scene_ids(self):
        for mapping in ({"base": "11"}, {"base": "11", "part": "12", "extra": "13"},
                        {"base": "11", "renamed": "12"}, [], None):
            value = identity_scene()
            value["host_identity"]["object_instances"] = mapping
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                _validated_scene(value)

    def test_duplicate_or_nontext_instance_tokens_are_rejected(self):
        for bad in ("11", True, False, 12, None, "", "u" * 257, []):
            value = identity_scene()
            value["host_identity"]["object_instances"]["part"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _validated_scene(value)


class BlenderOptionalIdentityTests(unittest.TestCase):
    def test_identity_option_defaults_false_without_namespace_mutation(self):
        host, focal, reference, _ = host_fixture()
        host.bpy.app = NS(driver_namespace={})
        host.bpy.data = NS(filepath="fixture.blend")
        host.scene.session_uid = 100
        focal.session_uid, reference.session_uid = 101, 102
        self.assertFalse(host.identity_metadata)
        value = host.capture_scene()
        self.assertNotIn("host_identity", value)
        self.assertEqual(host.bpy.app.driver_namespace, {})

    def test_identity_option_is_not_truthy_coercion(self):
        host, _, _, _ = host_fixture()
        for invalid in (1, 0, "true", None):
            with self.subTest(invalid=invalid), self.assertRaises(BlenderHostError):
                BlenderSceneHost(host.bpy, identity_metadata=invalid)

    def test_supported_identity_is_stable_runtime_only_and_readonly(self):
        host, focal, reference, _ = identity_host()
        matrices = copy.deepcopy([focal.matrix_world, reference.matrix_world])
        names = (focal.name, reference.name)
        first, second = host.capture_scene(), host.capture_scene()
        self.assertEqual(first, second)
        identity = first["host_identity"]
        self.assertEqual(identity["capture_scope"], "complete_scene_meshes")
        self.assertEqual(identity["object_instances"], {
            host.object_id(focal): "101", host.object_id(reference): "102"})
        self.assertEqual(len(identity["document_epoch"]), 64)
        self.assertEqual(set(host.bpy.app.driver_namespace), {"_human_eye_document_epoch_v1"})
        self.assertEqual(focal.assignments + reference.assignments, 0)
        self.assertEqual([focal.matrix_world, reference.matrix_world], matrices)
        self.assertEqual((focal.name, reference.name), names)
        self.assertEqual(_validated_scene(first)[0], first)

    def test_new_gateway_same_live_document_keeps_epoch(self):
        host, _, _, _ = identity_host()
        first = host.capture_scene()
        another = BlenderSceneHost(host.bpy, identity_metadata=True)
        self.assertEqual(first["host_identity"], another.capture_scene()["host_identity"])

    def test_rename_changes_lookup_id_but_keeps_instance_token(self):
        host, focal, _, _ = identity_host()
        first = host.capture_scene()
        old_id = host.object_id(focal)
        focal.name = focal.name_full = "Renamed"
        changed = host.capture_scene()
        new_id = host.object_id(focal)
        self.assertNotEqual(old_id, new_id)
        self.assertNotIn(old_id, changed["host_identity"]["object_instances"])
        self.assertEqual(changed["host_identity"]["object_instances"][new_id],
                         first["host_identity"]["object_instances"][old_id])
        self.assertEqual(changed["host_identity"]["document_epoch"], first["host_identity"]["document_epoch"])
        self.assertNotEqual(changed["revision"], first["revision"])
        self.assertEqual(focal.assignments, 0)

    def test_same_name_reincarnation_changes_revision_without_geometry_change(self):
        host, focal, _, _ = identity_host()
        first = host.capture_scene()
        old_id = host.object_id(focal)
        replacement = FakeObject("Focal", (2, 3, 4))
        replacement.session_uid = 201
        host.scene.objects = [replacement if obj is focal else obj for obj in host.scene.objects]
        host.view_layer.objects.active = replacement
        changed = host.capture_scene()
        self.assertEqual(host.object_id(replacement), old_id)
        self.assertEqual(first["meshes"], changed["meshes"])
        self.assertNotEqual(first["host_identity"]["object_instances"][old_id],
                            changed["host_identity"]["object_instances"][old_id])
        self.assertNotEqual(first["revision"], changed["revision"])
        self.assertNotEqual(_validated_scene(first)[2], _validated_scene(changed)[2])

    def test_deleted_object_is_absent_from_complete_identity_inventory(self):
        host, focal, reference, _ = identity_host()
        first = host.capture_scene()
        host.scene.objects.remove(reference)
        changed = host.capture_scene()
        self.assertNotIn(host.object_id(reference), changed["host_identity"]["object_instances"])
        self.assertEqual(set(changed["host_identity"]["object_instances"]), {host.object_id(focal)})
        self.assertNotEqual(first["revision"], changed["revision"])
        self.assertEqual(focal.assignments + reference.assignments, 0)

    def test_namespace_reset_scene_change_and_file_change_invalidate_document(self):
        for change in ("namespace", "scene", "file"):
            host, _, _, _ = identity_host()
            first = host.capture_scene()
            if change == "namespace":
                host.bpy.app.driver_namespace.clear()
            elif change == "scene":
                host.scene.session_uid = 200
            else:
                host.bpy.data.filepath = "different.blend"
            changed = host.capture_scene()
            with self.subTest(change=change):
                self.assertNotEqual(first["host_identity"]["document_epoch"], changed["host_identity"]["document_epoch"])
                self.assertNotEqual(first["revision"], changed["revision"])

    def test_unavailable_or_invalid_runtime_identity_is_omitted(self):
        for change in ("namespace_missing", "namespace_wrong_type", "scene_uid_missing",
                       "scene_uid_bool", "object_uid_missing", "object_uid_bool",
                       "object_uid_zero", "duplicate_uid", "bad_stored_epoch"):
            host, focal, reference, _ = identity_host()
            if change == "namespace_missing":
                del host.bpy.app
            elif change == "namespace_wrong_type":
                host.bpy.app.driver_namespace = []
            elif change == "scene_uid_missing":
                del host.scene.session_uid
            elif change == "scene_uid_bool":
                host.scene.session_uid = True
            elif change == "object_uid_missing":
                del focal.session_uid
            elif change == "object_uid_bool":
                focal.session_uid = True
            elif change == "object_uid_zero":
                focal.session_uid = 0
            elif change == "duplicate_uid":
                focal.session_uid = reference.session_uid
            else:
                host.bpy.app.driver_namespace['_human_eye_document_epoch_v1'] = "not-a-valid-epoch"
            with self.subTest(change=change):
                value = host.capture_scene()
                self.assertNotIn("host_identity", value)
                self.assertEqual(focal.assignments + reference.assignments, 0)


if __name__ == "__main__":
    unittest.main()
