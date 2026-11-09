"""Independent prepared/batched expert regressions against frozen old source.

No retraining, generator, benchmark search, Blender, GPU or external APIs.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "ef84ecc59f107321225d0d832fde119ed0b91e3f"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from human_eye_plugin import arm_twist_expert as candidate
from human_eye_plugin.arm_twist_weights import PARAMETERS


@lru_cache(maxsize=1)
def frozen_cases():
    path = ROOT / "verification/m6_arm_expert_001/run_01/dataset.json.gz"
    raw = gzip.decompress(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != PARAMETERS["training"]["dataset_sha256"]:
        raise AssertionError("The saved original dataset changed")
    result = json.loads(raw)
    if len(result) != 77:
        raise AssertionError("Expected exactly the original 77 saved poses")
    return result


@lru_cache(maxsize=1)
def old_module():
    raw = subprocess.check_output(
        ["git", "show", BASELINE + ":human_eye_plugin/arm_twist_expert.py"], cwd=ROOT)
    module = types.ModuleType("human_eye_plugin._old_prepared_arm_oracle")
    module.__package__ = "human_eye_plugin"
    module.__file__ = "git:" + BASELINE + ":human_eye_plugin/arm_twist_expert.py"
    exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
    return module


def poses(packet):
    return [copy.deepcopy(b["pose_matrix"]) for b in packet["bone_chain"]]


def static_packet(packet):
    result = copy.deepcopy(packet)
    result.pop("current_vertices")
    for bone in result["bone_chain"]:
        bone.pop("pose_matrix")
    return result


def example():
    return next(case["packet"] for case in frozen_cases()
                if case["metadata"]["split"] == "test"
                and case["metadata"]["pose_family"] == "anomalous_twist")


def hybrid(packet, current, dynamic_poses):
    result = copy.deepcopy(packet)
    result["current_vertices"] = copy.deepcopy(current)
    for bone, pose in zip(result["bone_chain"], dynamic_poses):
        bone["pose_matrix"] = copy.deepcopy(pose)
    return result


class UnreadableDynamic:
    def __array__(self, *args, **kwargs):
        raise AssertionError("prepare_patch read dynamic input")

    def __deepcopy__(self, memo):
        raise AssertionError("prepare_patch copied dynamic input")


class PreparedExpertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = old_module()
        cls.before = cls.old.ArmTwistExpert(PARAMETERS)
        cls.after = candidate.ArmTwistExpert(PARAMETERS)

    def assert_features_equal(self, expected, actual):
        (left, lc), (right, rc) = expected, actual
        self.assertEqual(lc["reason"], rc["reason"])
        self.assertEqual(left.shape, right.shape)
        if not lc["reason"]:
            np.testing.assert_allclose(right, left, rtol=1e-12, atol=1e-14)
        self.assertEqual([list(s) for s in lc["sections"]], [list(s) for s in rc["sections"]])
        self.assertEqual(list(lc["vertex_ids"]), list(rc["vertex_ids"]))

    def assert_report_equal(self, expected, actual):
        self.assertEqual(set(actual), set(expected))
        for field in expected:
            if field not in ("regions", "max_severity"):
                self.assertEqual(actual[field], expected[field], field)
        self.assertEqual(len(actual["regions"]), len(expected["regions"]))
        for left, right in zip(expected["regions"], actual["regions"]):
            self.assertEqual(set(left), set(right))
            for field in left:
                if field != "predicted_severity":
                    self.assertEqual(left[field], right[field], field)
            self.assertAlmostEqual(left["predicted_severity"], right["predicted_severity"], delta=1e-12)
        if "max_severity" in expected:
            self.assertAlmostEqual(expected["max_severity"], actual["max_severity"], delta=1e-12)

    def test_constructor_requires_only_static_fields_and_never_reads_dynamic_values(self):
        packet = example()
        prepared = candidate.prepare_patch(static_packet(packet))
        self.assert_features_equal(self.old.extract_features(packet),
                                   prepared.extract_features(packet["current_vertices"], poses(packet)))
        poisoned = copy.deepcopy(packet)
        poisoned["current_vertices"] = UnreadableDynamic()
        for bone in poisoned["bone_chain"]:
            bone["pose_matrix"] = UnreadableDynamic()
        prepared = candidate.prepare_patch(poisoned)
        self.assert_report_equal(self.before.predict(packet),
                                 prepared.analyze(packet["current_vertices"], poses(packet), model=self.after))

    def test_77_saved_poses_reuse_11_preparations_and_match_frozen_features_reports(self):
        prepared_assets = {}
        count = 0
        for case in frozen_cases():
            packet, asset = case["packet"], case["metadata"]["asset_id"]
            if asset not in prepared_assets:
                prepared_assets[asset] = candidate.prepare_patch(static_packet(packet))
            prepared = prepared_assets[asset]
            with self.subTest(asset=asset, pose=case["metadata"]["pose_family"]):
                expected = self.old.extract_features(packet)
                self.assert_features_equal(expected,
                    prepared.extract_features(packet["current_vertices"], poses(packet)))
                self.assert_features_equal(expected, candidate.extract_features(packet))
                report = self.before.predict(packet)
                self.assert_report_equal(report,
                    self.after.predict_prepared(prepared, packet["current_vertices"], poses(packet)))
                self.assert_report_equal(report, self.after.predict(packet))
                count += 1
        self.assertEqual(count, 77)
        self.assertEqual(len(prepared_assets), 11)

    def test_mixed_lengths_and_reordered_sections_restore_original_ids_and_rows(self):
        packet = copy.deepcopy(example())
        for index, section in enumerate(packet["sections"]):
            if index % 3:
                packet["triangles"].append([section[-2], section[-1], section[0]])
                section.pop()
        packet["sections"].reverse()
        packet["vertex_ids"] = [10**12 + 11 * i for i in range(len(packet["vertex_ids"]))]
        self.assertEqual({len(s) for s in packet["sections"]}, {15, 16})
        prepared = candidate.prepare_patch(static_packet(packet))
        self.assert_features_equal(self.old.extract_features(packet),
                                   prepared.extract_features(packet["current_vertices"], poses(packet)))
        result = prepared.analyze(packet["current_vertices"], poses(packet), model=self.after)
        self.assert_report_equal(self.before.predict(packet), result)
        for index, region in enumerate(result["regions"]):
            self.assertEqual(region["section_index"], index)
            self.assertEqual(region["vertex_ids"],
                             [packet["vertex_ids"][j] for j in packet["sections"][index]])

    def test_current_and_pose_inputs_can_change_independently_without_stale_features(self):
        asset = frozen_cases()[0]["metadata"]["asset_id"]
        choices = [case["packet"] for case in frozen_cases() if case["metadata"]["asset_id"] == asset]
        base = choices[0]
        changed = choices[3]
        prepared = candidate.prepare_patch(static_packet(base))
        initial, _ = prepared.extract_features(base["current_vertices"], poses(base))
        for field in ("current", "pose"):
            with self.subTest(field=field):
                current = changed["current_vertices"] if field == "current" else base["current_vertices"]
                dynamic = poses(changed) if field == "pose" else poses(base)
                source = hybrid(base, current, dynamic)
                result = prepared.extract_features(current, dynamic)
                self.assert_features_equal(self.old.extract_features(source), result)
                self.assertGreater(float(np.max(np.abs(result[0] - initial))), 1e-6)
                self.assert_report_equal(self.before.predict(source),
                                         prepared.analyze(current, dynamic, model=self.after))

    def test_original_static_lists_and_matrices_can_be_mutated_without_affecting_prepared(self):
        packet = copy.deepcopy(example())
        current, dynamic = copy.deepcopy(packet["current_vertices"]), poses(packet)
        expected = self.before.predict(packet)
        prepared = candidate.prepare_patch(packet)
        packet["schema"] = "bad"
        packet["unit"] = "bad"
        packet["rest_vertices"][0][0] = float("nan")
        packet["weights"][0][0] = float("nan")
        packet["sections"][0][0] = -1
        packet["triangles"][0][0] = -1
        packet["vertex_ids"][0] = -1
        for bone in packet["bone_chain"]:
            bone["name"] = "wrong"
            bone["parent"] = "wrong"
            bone["rest_matrix"][0][0] = float("nan")
            bone["pose_matrix"] = []
        packet["current_vertices"] = []
        self.assert_report_equal(expected, prepared.analyze(current, dynamic, model=self.after))

    def test_original_numpy_arrays_are_not_retained_as_mutable_static_views(self):
        packet = copy.deepcopy(example())
        current, dynamic = copy.deepcopy(packet["current_vertices"]), poses(packet)
        expected = self.before.predict(packet)
        packet["rest_vertices"] = np.array(packet["rest_vertices"])
        packet["weights"] = np.array(packet["weights"])
        for bone in packet["bone_chain"]:
            bone["rest_matrix"] = np.array(bone["rest_matrix"])
        prepared = candidate.prepare_patch(packet)
        packet["rest_vertices"][:] = np.nan
        packet["weights"][:] = np.nan
        for bone in packet["bone_chain"]:
            bone["rest_matrix"][:] = np.nan
        self.assert_report_equal(expected, prepared.analyze(current, dynamic, model=self.after))

    def test_returned_features_context_and_report_cannot_poison_later_calls(self):
        packet = example()
        prepared = candidate.prepare_patch(packet)
        features, context = prepared.extract_features(packet["current_vertices"], poses(packet))
        expected_features, expected_context = features.copy(), copy.deepcopy(context)
        features[:] = -999.
        for key in ("sections", "vertex_ids"):
            value = context[key]
            if isinstance(value, list):
                value[0] = [-1] if key == "sections" else -1
            elif value and isinstance(value[0], list):
                value[0][0] = -1
            context[key] = ["poison"]
        context["reason"] = "poison"
        context["joint_angles"][0]["twist_deg"] = 999.
        again, clean = prepared.extract_features(packet["current_vertices"], poses(packet))
        np.testing.assert_array_equal(again, expected_features)
        self.assertEqual(clean, expected_context)
        report = prepared.analyze(packet["current_vertices"], poses(packet), model=self.after)
        expected_report = copy.deepcopy(report)
        report["regions"][0]["vertex_ids"][0] = -1
        report["regions"][0]["predicted_severity"] = -1.
        self.assert_report_equal(expected_report,
                                 prepared.analyze(packet["current_vertices"], poses(packet), model=self.after))

    def test_structure_changes_require_new_preparation_and_raw_entry_reads_them(self):
        original = copy.deepcopy(example())
        current, dynamic = original["current_vertices"], poses(original)
        prepared = candidate.prepare_patch(static_packet(original))
        old_features = prepared.extract_features(current, dynamic)
        changed = copy.deepcopy(original)
        changed["vertex_ids"] = [10**10 + i for i in range(len(changed["vertex_ids"]))]
        changed["weights"] = [[1.] + [0.] * (len(changed["bone_chain"]) - 1)
                              for _ in changed["weights"]]
        rebuilt = candidate.prepare_patch(static_packet(changed))
        new_features = rebuilt.extract_features(current, dynamic)
        self.assertGreater(float(np.max(np.abs(new_features[0] - old_features[0]))), 1e-6)
        self.assert_features_equal(self.old.extract_features(changed), new_features)
        self.assert_features_equal(self.old.extract_features(changed), candidate.extract_features(changed))
        self.assert_features_equal(self.old.extract_features(original), prepared.extract_features(current, dynamic))
        self.assert_report_equal(self.before.predict(changed),
                                 rebuilt.analyze(current, dynamic, model=self.after))

    def test_saved_unknown_variants_preserve_original_reasons_and_reports(self):
        base = example()
        variants = []
        degenerate = copy.deepcopy(base)
        for vertex in degenerate["sections"][0]:
            degenerate["rest_vertices"][vertex] = degenerate["rest_vertices"][degenerate["sections"][0][0]][:]
        variants.append(degenerate)
        nonplanar = copy.deepcopy(base)
        nonplanar["current_vertices"][0][0] += .1
        variants.append(nonplanar)
        collapsed = copy.deepcopy(base)
        for section in collapsed["sections"]:
            center = np.array([collapsed["current_vertices"][i] for i in section]).mean(axis=0).tolist()
            for vertex in section:
                collapsed["current_vertices"][vertex] = center[:]
        variants.append(collapsed)
        for index, packet in enumerate(variants):
            with self.subTest(variant=index):
                prepared = candidate.prepare_patch(static_packet(packet))
                self.assert_features_equal(self.old.extract_features(packet),
                    prepared.extract_features(packet["current_vertices"], poses(packet)))
                self.assert_report_equal(self.before.predict(packet),
                    prepared.analyze(packet["current_vertices"], poses(packet), model=self.after))

    def test_bad_dynamic_values_are_rejected_even_when_static_geometry_is_unknown(self):
        original = copy.deepcopy(example())
        for vertex in original["sections"][0]:
            original["rest_vertices"][vertex] = [0., 0., 0.]
        prepared = candidate.prepare_patch(static_packet(original))
        variants = []
        short = copy.deepcopy(original)
        short["current_vertices"].pop()
        variants.append(short)
        invalid = copy.deepcopy(original)
        invalid["bone_chain"][0]["pose_matrix"][0][0] = 2.
        variants.append(invalid)
        bad = copy.deepcopy(original)
        bad["current_vertices"][0][0] = float("nan")
        variants.append(bad)
        for packet in variants:
            with self.subTest(current_length=len(packet["current_vertices"])):
                with self.assertRaises(ValueError) as expected:
                    self.old.extract_features(packet)
                with self.assertRaises(ValueError) as actual:
                    prepared.extract_features(packet["current_vertices"], poses(packet))
                self.assertEqual(str(actual.exception), str(expected.exception))
                with self.assertRaises(ValueError):
                    candidate.extract_features(packet)
        with self.assertRaises(ValueError):
            prepared.extract_features(original["current_vertices"], poses(original)[:-1])

    def test_finite_extreme_static_geometry_preserves_short_circuit_unknown_precedence(self):
        packet = copy.deepcopy(example())
        packet["rest_vertices"] = (np.array(packet["rest_vertices"]) * 1e200).tolist()
        for bone in packet["bone_chain"]:
            bone["rest_matrix"] = np.eye(4).tolist()
            bone["pose_matrix"] = np.eye(4).tolist()
        branch = copy.deepcopy(packet)
        branch["bone_chain"][1]["pose_matrix"] = [
            [-1., 0., 0., 0.], [0., 1., 0., 0.],
            [0., 0., -1., 0.], [0., 0., 0., 1.]]
        with np.errstate(all="ignore"):
            expected_branch = self.old.extract_features(branch)
            self.assertEqual(expected_branch[1]["reason"], "bone_twist_branch_unknown")
            expected_geometry = self.old.extract_features(packet)
            self.assertEqual(expected_geometry[1]["reason"], "section_centerline_degenerate")
            prepared = candidate.prepare_patch(static_packet(packet))
            for source, expected in ((branch, expected_branch), (packet, expected_geometry)):
                self.assert_features_equal(expected, candidate.extract_features(source))
                self.assert_features_equal(expected,
                    prepared.extract_features(source["current_vertices"], poses(source)))
                self.assert_report_equal(self.before.predict(source),
                    prepared.analyze(source["current_vertices"], poses(source), model=self.after))

    def test_public_default_and_explicit_prepared_entrypoints_share_original_report(self):
        packet = example()
        prepared = candidate.prepare_patch(static_packet(packet))
        expected = self.before.predict(packet)
        self.assert_report_equal(expected, candidate.analyze(packet))
        self.assert_report_equal(expected, prepared.analyze(packet["current_vertices"], poses(packet)))
        self.assert_report_equal(expected,
                                 self.after.predict_prepared(prepared, packet["current_vertices"], poses(packet)))


if __name__ == "__main__":
    unittest.main()
