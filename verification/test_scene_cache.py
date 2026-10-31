"""Retained scene history is descriptive; exact memo never grants authority."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import unittest

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.scene_cache import SpatialSceneCache
from verification.test_auto_router import box, scene


def shifted(value, identity, delta, revision="r2"):
    result = copy.deepcopy(value)
    result["revision"] = revision
    index = next(i for i, mesh in enumerate(result["meshes"]) if mesh["object_id"] == identity)
    result["meshes"][index] = MeshEntity3D.from_dict(result["meshes"][index]).translated(delta).to_dict()
    return result


class SceneCacheHistoryTests(unittest.TestCase):
    def test_input_output_and_export_are_detached(self):
        value = scene()
        expected = copy.deepcopy(value)
        cache = SpatialSceneCache()
        cache.record_scene(value)
        value["meshes"][0]["vertices"][0][0] = 800
        loaded = cache.snapshot()
        loaded["meshes"][0]["vertices"][0][0] = 900
        exported = cache.export_state()
        exported["blobs"].clear()
        self.assertEqual(cache.snapshot(), expected)

    def test_revision_change_shares_geometry_but_keeps_provenance(self):
        cache = SpatialSceneCache()
        first = cache.record_scene(scene())
        value = scene()
        value["revision"] = "r2"
        value["source"] = "new-capture-source"
        second = cache.record_scene(value)
        self.assertEqual(second["geometry_blobs_reused"], 2)
        self.assertEqual(second["object_blobs_reused"], 2)
        self.assertEqual(first["stats"]["content_blobs"], second["stats"]["content_blobs"])
        self.assertEqual(second["changes"]["unchanged"], ["base", "part"])
        self.assertEqual(cache.snapshot(0)["revision"], "r1")
        self.assertEqual(cache.snapshot()["source"], "new-capture-source")

    def test_identical_scene_does_not_fill_frames(self):
        cache = SpatialSceneCache()
        for _ in range(20):
            result = cache.record_scene(scene())
        self.assertTrue(result["duplicate_frame"])
        self.assertEqual(cache.stats()["frames"], 1)

    def test_identity_addition_removal_and_label_change(self):
        cache = SpatialSceneCache()
        value = scene()
        cache.record_scene(value)
        value["meshes"][0]["mark_label"] = "renamed"
        value["meshes"][1]["object_id"] = "replacement"
        changed = cache.record_scene(value)["changes"]
        self.assertEqual(changed["metadata"], ["base"])
        self.assertEqual(changed["added"], ["replacement"])
        self.assertEqual(changed["removed"], ["part"])

    def test_translation_rotation_and_deformation_classify_without_tolerant_reuse(self):
        cache = SpatialSceneCache()
        value = scene()
        cache.record_scene(value)
        translated = shifted(value, "part", [.01, .02, .03])
        self.assertEqual(cache.record_scene(translated)["changes"]["transform"], ["part"])
        rotated = copy.deepcopy(translated)
        rotated["meshes"][1] = MeshEntity3D.from_dict(rotated["meshes"][1]).rotated_around_pivot(
            SE3AlignmentMath.euler_xyz_to_matrix(10, 20, 30)).to_dict()
        result = cache.record_scene(rotated)
        self.assertEqual(result["changes"]["transform"], ["part"])
        self.assertFalse(result["changes"]["details"]["part"]["classification_used_for_reuse"])
        rotated["meshes"][1]["vertices"][0][0] += 1e-7
        self.assertEqual(cache.record_scene(rotated)["changes"]["geometry"], ["part"])

    def test_empty_complete_scene_records_removals(self):
        cache = SpatialSceneCache()
        value = scene()
        cache.record_scene(value)
        value["meshes"] = []
        self.assertEqual(cache.record_scene(value)["changes"]["removed"], ["base", "part"])
        self.assertEqual(cache.snapshot()["meshes"], [])

    def test_frame_budget_releases_unreferenced_geometry(self):
        cache = SpatialSceneCache(max_frames=2)
        for i in range(6):
            cache.record_scene(shifted(scene(), "part", [i * .01, 0, 0], revision=str(i)))
        self.assertEqual(cache.stats()["frames"], 2)
        self.assertEqual(cache.snapshot(0)["revision"], "4")
        # One unchanged mesh (two blobs), plus two changed meshes (four blobs).
        self.assertEqual(cache.stats()["content_blobs"], 6)

    def test_metadata_and_manifest_consume_byte_budget(self):
        cache = SpatialSceneCache(max_bytes=32 * 1024)
        first = cache.record_scene(scene())
        value = scene()
        value["source"] = "x" * 20_000
        large = cache.record_scene(value)
        self.assertGreater(large["stats"]["accounted_bytes"], first["stats"]["accounted_bytes"] + 19_000)
        self.assertLessEqual(large["stats"]["accounted_bytes"], 32 * 1024)
        value["source"] = "x" * 100_000
        rejected = cache.record_scene(value)
        self.assertFalse(rejected["retained"])
        self.assertEqual(cache.snapshot()["source"], "x" * 20_000)

    def test_bounded_cache_many_revisions(self):
        cache = SpatialSceneCache(max_bytes=12 * 1024, max_frames=20)
        for i in range(40):
            result = cache.record_scene(shifted(scene(), "part", [i * .01, 0, 0], revision=str(i)))
            self.assertLessEqual(result["stats"]["accounted_bytes"], cache.max_bytes)
        self.assertTrue(result["retained"])
        self.assertLess(result["stats"]["frames"], 20)

    def test_invalid_provenance_identity_and_geometry_rejected(self):
        for mutate in (lambda v: v.update(unit="cm"),
                       lambda v: v.update(revision=""),
                       lambda v: v["meshes"][1].update(object_id="base"),
                       lambda v: v["meshes"][1].update(pivot_world=[1, 2]),
                       lambda v: v["meshes"][1].update(local_axes=[1, 2, 3]),
                       lambda v: v["meshes"][0]["vertices"][0].__setitem__(0, float("nan")),
                       lambda v: v["meshes"][0]["faces"][0].__setitem__(0, 99999)):
            value = scene()
            mutate(value)
            with self.assertRaises(ValueError):
                SpatialSceneCache().record_scene(value)

    def test_extreme_numeric_fit_cannot_poison_history(self):
        cache = SpatialSceneCache()
        value = scene()
        cache.record_scene(value)
        value["meshes"][1]["vertices"][0][0] = 1e308
        result = cache.record_scene(value)
        self.assertEqual(result["changes"]["geometry"], ["part"])
        self.assertEqual(result["changes"]["details"]["part"]["reason"], "rigid_fit_numeric_range")
        self.assertTrue(result["retained"])


class SceneMeasurementMemoTests(unittest.TestCase):
    def setUp(self):
        self.cache = SpatialSceneCache()
        self.a, self.b = [MeshEntity3D.from_dict(v) for v in scene()["meshes"]]
        self.calls = 0

    def measure(self, a=None, b=None, **kwargs):
        def compute():
            self.calls += 1
            return measure_pair_geometry(a or self.a, b or self.b, need_clearance=True)
        return self.cache.pair_measurement(a or self.a, b or self.b, compute,
            parameters=kwargs.pop("parameters", {"need_clearance": True, "collision_tolerance_m": 1e-9}),
            algorithm_version=kwargs.pop("algorithm_version", "strict-v1"), **kwargs)

    def test_exact_repeat_avoids_real_geometry_evaluator(self):
        first, hit = self.measure()
        second, second_hit = self.measure()
        self.assertFalse(hit)
        self.assertTrue(second_hit)
        self.assertEqual(first, second)
        self.assertAlmostEqual(second["signed_clearance_m"], .1)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.cache.stats()["measurement_hits"], 1)

    def test_returned_nested_data_cannot_poison_memo(self):
        first, _ = self.measure()
        original = copy.deepcopy(first)
        first["signed_clearance_m"] = -500
        first["injected"] = {"allow_action": True}
        second, hit = self.measure()
        self.assertTrue(hit)
        self.assertEqual(second, original)

    def test_pair_is_ordered_and_algorithm_parameters_version_bound(self):
        self.measure()
        self.measure(self.b, self.a)
        self.measure(parameters={"need_clearance": False})
        self.measure(algorithm_version="strict-v2")
        self.assertEqual(self.calls, 4)

    def test_geometry_pivot_axes_identity_and_provenance_invalidate(self):
        self.measure()
        changes = [{"pivot_world": [1, 0, 0]}, {"axes_source": "different-source"},
                   {"object_id": "other-id"}, {"local_axes": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]}]
        for change in changes:
            altered = self.a.to_dict()
            altered.update(change)
            _, hit = self.measure(MeshEntity3D.from_dict(altered), self.b)
            self.assertFalse(hit)
        _, hit = self.measure(self.a.translated([1e-11, 0, 0]), self.b)
        self.assertFalse(hit)
        self.assertEqual(self.calls, 6)

    def test_revision_reuse_and_unrelated_object_change_do_not_invalidate_pair(self):
        self.cache.record_scene(scene())
        self.measure()
        value = scene()
        value["revision"] = "r9"
        value["meshes"].append(box("third", [10, 0, 0], [1, 1, 1]))
        self.cache.record_scene(value)
        _, hit = self.measure()
        self.assertTrue(hit)
        self.assertEqual(self.calls, 1)

    def test_unknown_and_failed_measurements_not_cached(self):
        count = []
        for _ in range(2):
            result, hit = self.cache.pair_measurement(self.a, self.b,
                lambda: (count.append(1) or {"measurement_valid": False}), algorithm_version="unknown")
            self.assertFalse(hit)
        self.assertEqual(len(count), 2)
        self.assertEqual(self.cache.stats()["measurement_entries"], 0)

    def test_exceptions_and_nonfinite_results_not_cached(self):
        def fail():
            raise RuntimeError("fixture failure")
        with self.assertRaises(RuntimeError):
            self.cache.pair_measurement(self.a, self.b, fail, algorithm_version="failure")
        with self.assertRaises(ValueError):
            self.cache.pair_measurement(self.a, self.b,
                lambda: {"measurement_valid": True, "distance": float("nan")}, algorithm_version="nan")
        self.assertEqual(self.cache.stats()["measurement_entries"], 0)

    def test_lru_limit_evicts_without_reusing_wrong_result(self):
        self.cache = SpatialSceneCache(max_measurements=1)
        self.measure()
        self.measure(self.a.translated([.01, 0, 0]), self.b)
        _, hit = self.measure()
        self.assertFalse(hit)
        self.assertEqual(self.calls, 3)
        self.assertEqual(self.cache.stats()["measurement_entries"], 1)

    def test_concurrent_identical_calls_compute_once(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.measure(), range(8)))
        self.assertEqual(sum(hit for _, hit in results), 7)
        self.assertEqual(self.calls, 1)


class SceneCachePersistenceTests(unittest.TestCase):
    def test_roundtrip_preserves_history_but_no_measurements_or_authority(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        mesh = scene()["meshes"]
        cache.pair_measurement(*mesh, lambda: {"measurement_valid": True, "value": 12}, algorithm_version="test")
        state = cache.export_state()
        self.assertEqual(set(state), {"schema_version", "purpose", "blobs", "frames"})
        restored = SpatialSceneCache()
        restored.import_state(state)
        self.assertEqual(restored.snapshot(), scene())
        result, hit = restored.pair_measurement(*mesh,
            lambda: {"measurement_valid": True, "value": 13}, algorithm_version="test")
        self.assertFalse(hit)
        self.assertEqual(result["value"], 13)

    def test_preserve_retains_only_same_process_computed_memo(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        mesh = scene()["meshes"]
        cache.pair_measurement(*mesh, lambda: {"measurement_valid": True, "value": 12}, algorithm_version="test")
        cache.import_state(cache.export_state(), preserve_measurements=True)
        _, hit = cache.pair_measurement(*mesh,
            lambda: self.fail("in-process memo was discarded"), algorithm_version="test")
        self.assertTrue(hit)
        cache.import_state(cache.export_state())
        self.assertEqual(cache.stats()["measurement_entries"], 0)

    def test_tampered_blob_and_forged_measurement_state_are_rejected_atomically(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        state = cache.export_state()
        key = next(iter(state["blobs"]))
        state["blobs"][key] += " "
        with self.assertRaises(ValueError):
            cache.import_state(state)
        self.assertEqual(cache.snapshot(), scene())
        state = cache.export_state()
        state["measurements"] = {"forged": {"measurement_valid": True}}
        with self.assertRaises(ValueError):
            cache.import_state(state)

    def test_hash_valid_invalid_geometry_is_revalidated(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        state = cache.export_state()
        geometry_key = next(key for key, value in state["blobs"].items() if "\"vertices\"" in value)
        obj = json.loads(state["blobs"][geometry_key])
        obj["faces"][0][0] = 999999
        canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        new_geometry_key = hashlib.sha256(canonical.encode()).hexdigest()
        del state["blobs"][geometry_key]
        state["blobs"][new_geometry_key] = canonical
        replacements = {}
        for key, value in list(state["blobs"].items()):
            if geometry_key in value:
                replacement = value.replace(geometry_key, new_geometry_key)
                new_key = hashlib.sha256(replacement.encode()).hexdigest()
                replacements[key] = new_key
                del state["blobs"][key]
                state["blobs"][new_key] = replacement
        for old, new in replacements.items():
            state["frames"] = [frame.replace(old, new) for frame in state["frames"]]
        with self.assertRaises(ValueError):
            SpatialSceneCache().import_state(state)

    def test_unreferenced_blob_and_duplicate_frames_rejected(self):
        cache = SpatialSceneCache()
        cache.record_scene(scene())
        state = cache.export_state()
        payload = "{}"
        state["blobs"][hashlib.sha256(payload.encode()).hexdigest()] = payload
        with self.assertRaises(ValueError):
            cache.import_state(state)
        state = cache.export_state()
        state["frames"].append(state["frames"][0])
        with self.assertRaises(ValueError):
            cache.import_state(state)


if __name__ == "__main__":
    unittest.main()
