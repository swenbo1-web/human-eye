"""Complete scene transport round trips and refuses stale or partial deltas."""
import copy
import json
import unittest

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.scene_delta import apply_scene_delta, make_scene_delta
from verification.test_auto_router import box, scene


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fixture():
    value = scene()
    value["meshes"].extend([box("side_a", [1, 0, 0], [.1, .1, .1]),
                             box("side_b", [-1, 0, 0], [.1, .1, .1])])
    value["source"] = {"provider": "detached_fixture", "note": "完整观察"}
    value["host_identity"] = {"schema_version": "1.0", "document_epoch": "document-1",
        "capture_scope": "complete_scene_meshes", "object_instances": {
            mesh["object_id"]: str(i + 10) for i, mesh in enumerate(value["meshes"])}}
    return _validated_scene(value)[0]


def changed_scene(value=None):
    value = copy.deepcopy(fixture() if value is None else value)
    value["revision"] = "r2"
    value["meshes"][1]["color_rgb"] = [20, 40, 60]
    return value


def restamp(envelope):
    """Repair transport counts so malicious-content checks run independently."""
    envelope["byte_counts"]["payload_bytes"] = len(encode(envelope["payload"]))
    for _ in range(16):
        count = len(encode(envelope))
        if count == envelope["byte_counts"]["envelope_bytes"]:
            return envelope
        envelope["byte_counts"]["envelope_bytes"] = count
    raise RuntimeError("Test envelope byte count did not stabilize")


class SceneDeltaRoundTripTests(unittest.TestCase):
    def test_complete_changed_object_round_trip_has_real_wire_savings(self):
        before, after = fixture(), changed_scene()
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta", packet)
        self.assertEqual(set(packet["payload"]["updated"]), {"part"})
        self.assertEqual(packet["invalidation"]["object_ids"], ["part"])
        self.assertEqual(apply_scene_delta(before, packet), after)
        self.assertLess(len(encode(packet)), len(encode(make_scene_delta(None, after))))
        self.assertEqual(packet["byte_counts"]["envelope_bytes"], len(encode(packet)))
        self.assertEqual(packet["byte_counts"]["full_snapshot_bytes"], len(encode(after)))
        self.assertEqual(packet["byte_counts"]["payload_bytes"], len(encode(packet["payload"])))

    def test_cache_detached_snapshots_are_accepted_without_changing_cache(self):
        cache = SpatialSceneCache()
        cache.record_scene(fixture())
        cache.record_scene(changed_scene())
        original = cache.export_state()
        packet = make_scene_delta(cache.snapshot(-2), cache.snapshot(-1))
        rebuilt = apply_scene_delta(cache.snapshot(-2), packet)
        self.assertEqual(rebuilt, cache.snapshot(-1))
        self.assertEqual(cache.export_state(), original)

    def test_revision_only_update_preserves_every_other_field(self):
        before, after = fixture(), fixture()
        after["revision"] = "r2"
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta")
        self.assertEqual(packet["payload"]["updated"], {})
        self.assertEqual(packet["invalidation"]["object_ids"], [])
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_unchanged_snapshot_remains_observation_only(self):
        before = fixture()
        packet = make_scene_delta(before, before)
        self.assertEqual(packet["purpose"], "observation_only")
        self.assertFalse(packet["execution_authority"])
        self.assertEqual(packet["base"], packet["target"])
        self.assertEqual(apply_scene_delta(before, packet), before)

    def test_add_remove_update_and_explicit_mesh_order_round_trip(self):
        before, after = fixture(), changed_scene()
        after["meshes"] = [mesh for mesh in after["meshes"] if mesh["object_id"] != "side_b"]
        added = box("new", [2, 0, 0], [.1, .1, .1])
        after["meshes"].insert(0, added)
        after["host_identity"]["object_instances"].pop("side_b")
        after["host_identity"]["object_instances"]["new"] = "90"
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta")
        self.assertEqual(packet["payload"]["removed"], ["side_b"])
        self.assertEqual(set(packet["payload"]["added"]), {"new"})
        self.assertEqual(packet["payload"]["mesh_order"], [m["object_id"] for m in after["meshes"]])
        self.assertEqual(apply_scene_delta(before, packet), _validated_scene(after)[0])

    def test_mesh_reordering_is_preserved_without_fake_updates(self):
        before, after = fixture(), fixture()
        after["meshes"].reverse()
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta")
        self.assertEqual(packet["payload"]["updated"], {})
        self.assertEqual(apply_scene_delta(before, packet)["meshes"], after["meshes"])

    def test_same_name_same_geometry_new_incarnation_is_replacement(self):
        before, after = fixture(), fixture()
        after["revision"] = "r2"
        after["host_identity"]["object_instances"]["part"] = "new-object"
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta")
        self.assertEqual(set(packet["payload"]["replaced"]), {"part"})
        self.assertEqual(packet["payload"]["updated"], {})
        self.assertIn("part", packet["invalidation"]["object_ids"])
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_renamed_lookup_id_is_removed_and_added(self):
        before, after = fixture(), fixture()
        mesh = after["meshes"][1]
        mesh["object_id"] = "renamed"
        mesh["name"], mesh["mark_label"] = "Renamed", "#renamed"
        instances = after["host_identity"]["object_instances"]
        instances["renamed"] = instances.pop("part")
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "delta")
        self.assertEqual(packet["payload"]["removed"], ["part"])
        self.assertEqual(set(packet["payload"]["added"]), {"renamed"})
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_global_source_metadata_invalidates_complete_observation_scope(self):
        before, after = fixture(), fixture()
        after["source"]["note"] = "新的完整来源信息"
        packet = make_scene_delta(before, after)
        self.assertTrue(packet["invalidation"]["scene_metadata_changed"])
        self.assertEqual(packet["invalidation"]["object_ids"], sorted(m["object_id"] for m in after["meshes"]))
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_full_resync_for_missing_base_accepts_unrelated_or_missing_local_base(self):
        after = fixture()
        packet = make_scene_delta(None, after)
        self.assertEqual(packet["status"], "full")
        for base in (None, {"unusable_old_state": True}, changed_scene()):
            self.assertEqual(apply_scene_delta(base, packet), after)

    def test_changed_document_forces_full_without_merging_history(self):
        before, after = fixture(), changed_scene()
        after["host_identity"]["document_epoch"] = "document-2"
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "full")
        self.assertEqual(packet["invalidation"]["mode"], "full_resync")
        self.assertEqual(apply_scene_delta(None, packet), after)

    def test_legacy_identity_missing_uses_full_compatible_payload(self):
        for omit in ("before", "after", "both"):
            before, after = fixture(), changed_scene()
            if omit in ("before", "both"):
                before.pop("host_identity")
            if omit in ("after", "both"):
                after.pop("host_identity")
            with self.subTest(omit=omit):
                packet = make_scene_delta(before, after)
                self.assertEqual(packet["status"], "full")
                self.assertEqual(apply_scene_delta(before, packet), after)

    def test_no_savings_or_all_objects_updated_selects_full(self):
        before, after = fixture(), changed_scene()
        packet = make_scene_delta(before, after, min_savings_bytes=100_000)
        self.assertEqual(packet["status"], "full")
        for i, mesh in enumerate(after["meshes"]):
            mesh["color_rgb"] = [i, 4, 6]
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "full")
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_input_and_result_aliases_do_not_modify_snapshots(self):
        before, after = fixture(), changed_scene()
        saved = copy.deepcopy((before, after))
        packet = make_scene_delta(before, after)
        reconstructed = apply_scene_delta(before, packet)
        self.assertEqual((before, after), saved)
        reconstructed["meshes"][0]["vertices"][0][0] = 999
        packet["payload"]["updated"]["part"]["color_rgb"][0] = 255
        self.assertEqual((before, after), saved)


class SceneDeltaRefusalTests(unittest.TestCase):
    def test_partial_current_never_emits_removals_or_merges_authority(self):
        before, partial = fixture(), fixture()
        partial["meshes"] = partial["meshes"][:1]
        packet = make_scene_delta(before, partial, capture_scope="partial_scene_meshes")
        self.assertEqual(packet["status"], "needs_full_resync")
        self.assertIsNone(packet["payload"])
        self.assertEqual(packet["invalidation"]["object_ids"], [])
        self.assertFalse(packet["execution_authority"])
        with self.assertRaises(ValueError):
            apply_scene_delta(before, packet)

    def test_partial_identity_claim_cannot_override_complete_argument(self):
        partial = fixture()
        partial["host_identity"]["capture_scope"] = "partial_scene_meshes"
        self.assertEqual(make_scene_delta(fixture(), partial)["status"], "needs_full_resync")

    def test_partial_base_requires_full_current_resync(self):
        before, after = fixture(), changed_scene()
        before["host_identity"]["capture_scope"] = "partial_scene_meshes"
        packet = make_scene_delta(before, after)
        self.assertEqual(packet["status"], "full")
        self.assertIsNone(packet["base"])
        self.assertEqual(apply_scene_delta(before, packet), after)

    def test_empty_result_and_too_many_meshes_follow_existing_scene_limits(self):
        for count in (0, 257):
            value = fixture()
            value["meshes"] = [] if count == 0 else [copy.deepcopy(value["meshes"][0]) for _ in range(count)]
            with self.subTest(count=count), self.assertRaises(ValueError):
                make_scene_delta(fixture(), value)

    def test_bad_budget_or_savings_values_are_not_coerced(self):
        for options in ({"max_bytes": True}, {"max_bytes": 1023}, {"max_bytes": 70_000_000},
                        {"min_savings_bytes": True}, {"min_savings_bytes": -1},
                        {"min_savings_bytes": 9_000_000}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                make_scene_delta(fixture(), changed_scene(), **options)

    def test_byte_budget_refuses_oversized_full_input_and_envelope(self):
        with self.assertRaises(ValueError):
            make_scene_delta(None, fixture(), max_bytes=1024)
        packet = make_scene_delta(None, fixture())
        with self.assertRaises(ValueError):
            apply_scene_delta(None, packet, max_bytes=1024)

    def test_delta_requires_matching_complete_base_not_just_revision(self):
        before, after = fixture(), changed_scene()
        packet = make_scene_delta(before, after)
        for kind in ("revision", "geometry", "epoch", "instance", "missing"):
            wrong = copy.deepcopy(before)
            if kind == "revision":
                wrong["revision"] = "different"
            elif kind == "geometry":
                wrong["meshes"][0]["vertices"][0][0] -= .01
            elif kind == "epoch":
                wrong["host_identity"]["document_epoch"] = "wrong-document"
            elif kind == "instance":
                wrong["host_identity"]["object_instances"]["part"] = "recreated"
            else:
                wrong = None
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                apply_scene_delta(wrong, packet)

    def test_wrong_hash_or_revision_declaration_is_refused(self):
        for side, field, value in (("base", "scene_fingerprint", "0" * 64),
                                   ("target", "scene_fingerprint", "0" * 64),
                                   ("target", "scene_revision", "r999"),
                                   ("target", "document_epoch", "changed-epoch")):
            packet = make_scene_delta(fixture(), changed_scene())
            packet[side][field] = value
            with self.subTest(side=side, field=field), self.assertRaises(ValueError):
                apply_scene_delta(fixture(), restamp(packet))

    def test_incarnation_change_cannot_be_labeled_ordinary_update(self):
        before, after = fixture(), changed_scene()
        after["host_identity"]["object_instances"]["part"] = "new-object"
        packet = make_scene_delta(before, after)
        packet["payload"]["updated"]["part"] = packet["payload"]["replaced"].pop("part")
        with self.assertRaisesRegex(ValueError, "incarnation"):
            apply_scene_delta(before, restamp(packet))

    def test_duplicate_conflicting_or_unknown_operations_are_refused(self):
        for kind in ("overlap", "wrong_key", "extra_remove", "duplicate_order", "missing_order", "duplicate_remove"):
            before = fixture()
            packet = make_scene_delta(before, changed_scene())
            payload = packet["payload"]
            if kind == "overlap":
                payload["added"]["part"] = copy.deepcopy(payload["updated"]["part"])
            elif kind == "wrong_key":
                payload["updated"]["part"]["object_id"] = "base"
            elif kind == "extra_remove":
                payload["removed"] = ["absent"]
            elif kind == "duplicate_order":
                payload["mesh_order"][0] = payload["mesh_order"][1]
            elif kind == "missing_order":
                payload["mesh_order"].pop()
            else:
                payload["removed"] = ["side_a", "side_a"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                apply_scene_delta(before, restamp(packet))

    def test_hidden_mesh_inventory_and_extra_metadata_are_refused(self):
        for field, value in (("meshes", []), ("execution_authority", True)):
            packet = make_scene_delta(fixture(), changed_scene())
            packet["payload"]["metadata"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                apply_scene_delta(fixture(), restamp(packet))

    def test_full_payload_target_hash_and_normalized_shape_are_verified(self):
        for kind in ("content", "extra"):
            packet = make_scene_delta(None, fixture())
            if kind == "content":
                packet["payload"]["meshes"][0]["color_rgb"] = [1, 2, 3]
            else:
                packet["payload"]["hidden_meshes"] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                apply_scene_delta(None, restamp(packet))

    def test_invalidation_list_and_byte_counts_cannot_be_forged(self):
        for kind in ("invalidation", "payload_size", "wire_size", "full_size"):
            packet = make_scene_delta(fixture(), changed_scene())
            if kind == "invalidation":
                packet["invalidation"]["object_ids"] = []
                restamp(packet)
            elif kind == "payload_size":
                packet["byte_counts"]["payload_bytes"] += 1
            elif kind == "wire_size":
                packet["byte_counts"]["envelope_bytes"] += 1
            else:
                packet["byte_counts"]["full_snapshot_bytes"] += 1
                restamp(packet)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                apply_scene_delta(fixture(), packet)

    def test_execution_authority_or_bad_schema_is_not_accepted(self):
        for field, value in (("execution_authority", True), ("execution_authority", 0),
                             ("purpose", "execution"), ("schema_version", "2.0"),
                             ("capture_scope", "partial_scene_meshes"), ("status", [])):
            packet = make_scene_delta(fixture(), changed_scene())
            packet[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                apply_scene_delta(fixture(), restamp(packet))

    def test_delta_replay_against_already_changed_base_refuses_stale_base(self):
        before, after = fixture(), changed_scene()
        packet = make_scene_delta(before, after)
        rebuilt = apply_scene_delta(before, packet)
        with self.assertRaises(ValueError):
            apply_scene_delta(rebuilt, packet)


if __name__ == "__main__":
    unittest.main()
