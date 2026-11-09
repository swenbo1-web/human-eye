"""Independent contracts for the fixed first arm expert, not retraining/search.

Uses small numerical patches and the one frozen synthetic dataset. Never opens
Blender or calls an external model/API. Only explicit expert calls load weights.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from human_eye_plugin import arm_twist_expert as expert


@lru_cache(maxsize=1)
def cases():
    spec = importlib.util.spec_from_file_location(
        "independent_arm_synthetic", Path(__file__).with_name("synthetic.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate_dataset()


def one_case(*, split="test", family="anomalous_twist"):
    return next(c for c in cases() if c["metadata"]["split"] == split
                and c["metadata"]["pose_family"] == family)


def tiny_parameters(bias=0.2):
    count = len(expert.FEATURE_NAMES)
    return dict(schema="arm-twist-mlp-v1", feature_names=list(expert.FEATURE_NAMES),
                mean=[0.] * count, scale=[1.] * count,
                w1=[[0., 0.] for _ in range(count)], b1=[0., 0.],
                w2=[0., 0.], b2=[bias], training={"scope": "contract-test-only"})


def scores(report):
    return np.array([r["predicted_severity"] for r in report["regions"]])


class ArmExpertContractTests(unittest.TestCase):
    def test_actual_two_and_three_bone_patches_exceed_old_global_asset_cap(self):
        seen = set()
        for case in cases():
            packet = case["packet"]
            count = len(packet["bone_chain"])
            if count in seen:
                continue
            features, context = expert.extract_features(packet)
            self.assertGreater(len(packet["rest_vertices"]), 256)
            self.assertEqual(features.shape, (len(packet["sections"]), len(expert.FEATURE_NAMES)))
            self.assertIsNone(context["reason"])
            self.assertTrue(np.isfinite(features).all())
            seen.add(count)
        self.assertEqual(seen, {2, 3})

    def test_invalid_correspondence_weights_indices_chain_and_units_are_rejected(self):
        base = one_case()["packet"]
        mutations = [
            lambda p: p["current_vertices"].pop(),
            lambda p: p["vertex_ids"].__setitem__(1, p["vertex_ids"][0]),
            lambda p: p["weights"][0].__setitem__(0, -0.5),
            lambda p: p["weights"].__setitem__(0, [0.] * len(p["bone_chain"])),
            lambda p: p["triangles"][0].__setitem__(0, len(p["rest_vertices"])),
            lambda p: p["sections"][0].__setitem__(1, p["sections"][0][0]),
            lambda p: p["bone_chain"][0].__setitem__("parent", p["bone_chain"][-1]["name"]),
            lambda p: p["bone_chain"][0]["pose_matrix"][0].__setitem__(0, 2.),
            lambda p: p["rest_vertices"][0].__setitem__(0, float("nan")),
            lambda p: p.__setitem__("unit", "cm"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                packet = copy.deepcopy(base)
                mutate(packet)
                with self.assertRaises(ValueError):
                    expert.extract_features(packet)

    def test_degenerate_reference_section_yields_unknown_not_healthy_success(self):
        packet = copy.deepcopy(one_case()["packet"])
        section = packet["sections"][0]
        anchor = packet["rest_vertices"][section[0]][:]
        for vertex in section:
            packet["rest_vertices"][vertex] = anchor[:]
        report = expert.ArmTwistExpert(tiny_parameters()).predict(packet)
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(report["reason"])
        self.assertEqual(report["regions"], [])
        self.assertIs(report["execution_authority"], False)

    def test_supervision_and_family_metadata_are_not_model_features(self):
        packet = copy.deepcopy(one_case()["packet"])
        expected, _ = expert.extract_features(packet)
        packet["label_severity"] = [1.] * len(packet["sections"])
        packet["reference_vertices"] = [[9e5, -9e5, 9e5]] * len(packet["rest_vertices"])
        packet["metadata"] = {"pose_family": "arbitrary_label", "split": "test", "asset_id": "label"}
        actual, _ = expert.extract_features(packet)
        np.testing.assert_array_equal(actual, expected)
        for case in cases():
            self.assertTrue({"label_severity", "reference_vertices", "metadata"}.isdisjoint(case["packet"]))

    def test_global_vertex_ids_do_not_change_features_and_are_returned_exactly(self):
        packet = copy.deepcopy(one_case()["packet"])
        expected, _ = expert.extract_features(packet)
        packet["vertex_ids"] = [10**9 + 7 * i for i in range(len(packet["rest_vertices"]))]
        actual, _ = expert.extract_features(packet)
        np.testing.assert_array_equal(actual, expected)
        report = expert.ArmTwistExpert(tiny_parameters()).predict(packet)
        for index, region in enumerate(report["regions"]):
            self.assertEqual(region["section_index"], index)
            self.assertEqual(region["vertex_ids"],
                             [packet["vertex_ids"][j] for j in packet["sections"][index]])

    def test_common_rigid_world_change_does_not_create_a_deformation_feature(self):
        packet = copy.deepcopy(one_case()["packet"])
        expected, _ = expert.extract_features(packet)
        transform = np.array([[0., -1., 0., .31], [1., 0., 0., -.23],
                              [0., 0., 1., .47], [0., 0., 0., 1.]])
        for name in ("rest_vertices", "current_vertices"):
            points = np.asarray(packet[name])
            packet[name] = (points @ transform[:3, :3].T + transform[:3, 3]).tolist()
        for bone in packet["bone_chain"]:
            for name in ("rest_matrix", "pose_matrix"):
                bone[name] = (transform @ np.asarray(bone[name])).tolist()
        actual, _ = expert.extract_features(packet)
        np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-9)

    def test_uniform_physical_scaling_preserves_dimensionless_features(self):
        packet = copy.deepcopy(one_case()["packet"])
        expected, _ = expert.extract_features(packet)
        for name in ("rest_vertices", "current_vertices"):
            packet[name] = (np.asarray(packet[name]) * 10.).tolist()
        for bone in packet["bone_chain"]:
            for name in ("rest_matrix", "pose_matrix"):
                value = np.array(bone[name])
                value[:3, 3] *= 10.
                bone[name] = value.tolist()
        actual, _ = expert.extract_features(packet)
        np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-9)

    def test_parameter_tensors_drive_output_and_are_detached_from_input_container(self):
        packet = one_case()["packet"]
        params = tiny_parameters(.2)
        model = expert.ArmTwistExpert(params)
        before = scores(model.predict(packet))
        np.testing.assert_allclose(before, .2)
        params["b2"][0] = .8
        np.testing.assert_array_equal(scores(model.predict(packet)), before)
        np.testing.assert_allclose(scores(expert.ArmTwistExpert(params).predict(packet)), .8)

    def test_report_is_diagnostic_and_does_not_mutate_patch_or_imply_authority(self):
        packet = copy.deepcopy(one_case()["packet"])
        before = json.dumps(packet, sort_keys=True, allow_nan=False)
        report = expert.ArmTwistExpert(tiny_parameters()).predict(packet)
        self.assertEqual(report["schema"], "arm-twist-expert-report-v1")
        self.assertEqual(report["status"], "estimated")
        self.assertIn("not_damage", report["assessment"])
        self.assertIs(report["execution_authority"], False)
        self.assertEqual(report["source_binding"], "caller_supplied_patch_not_verified_scene")
        self.assertEqual(json.dumps(packet, sort_keys=True, allow_nan=False), before)
        report["regions"][0]["vertex_ids"][0] = -1
        self.assertNotEqual(packet["vertex_ids"][packet["sections"][0][0]], -1)


class SyntheticSplitAndWeightsTests(unittest.TestCase):
    def test_serialized_preprocessing_is_fitted_to_train_assets_only(self):
        from human_eye_plugin.arm_twist_weights import PARAMETERS
        train = [case for case in cases() if case["metadata"]["split"] == "train"]
        values = np.concatenate([expert.extract_features(case["packet"])[0] for case in train])
        np.testing.assert_allclose(PARAMETERS["mean"], values.mean(axis=0), rtol=0., atol=1e-14)
        std = values.std(axis=0)
        variable = std > 1e-12
        np.testing.assert_allclose(np.asarray(PARAMETERS["scale"])[variable], std[variable],
                                   rtol=0., atol=1e-14)
        self.assertTrue(np.all(np.asarray(PARAMETERS["scale"])[~variable] > 0.))
        self.assertEqual(set(PARAMETERS["training"]["train_assets"]),
                         {case["metadata"]["asset_id"] for case in train})

    def test_assets_and_actual_rest_weight_signatures_do_not_cross_splits(self):
        assets, signatures = {}, {}
        marginals = {split: {name: set() for name in ("shape_family", "skeleton_family", "weight_family")}
                     for split in ("train", "validation", "test")}
        for case in cases():
            p, metadata = case["packet"], case["metadata"]
            split, asset = metadata["split"], metadata["asset_id"]
            assets.setdefault(asset, set()).add(split)
            identity = dict(rest=p["rest_vertices"], weights=p["weights"],
                            bones=[{k: b[k] for k in ("name", "parent", "rest_matrix")} for b in p["bone_chain"]])
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            signatures.setdefault(digest, set()).add(split)
            for field in marginals[split]:
                marginals[split][field].add(metadata[field])
        self.assertTrue(all(len(s) == 1 for s in assets.values()))
        self.assertTrue(all(len(s) == 1 for s in signatures.values()))
        for field in marginals["train"]:
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
                self.assertTrue(marginals[a][field].isdisjoint(marginals[b][field]), (field, a, b))

    def test_same_angle_controls_keep_all_pose_weights_rest_and_ids_identical(self):
        pairs = {}
        for case in cases():
            metadata = case["metadata"]
            if metadata["pose_family"] in ("anomalous_twist", "same_angle_preserved"):
                pairs.setdefault(metadata["pair_id"], {})[metadata["pose_family"]] = case
        self.assertTrue(pairs)
        angle_columns = [i for i, name in enumerate(expert.FEATURE_NAMES)
                         if "twist" in name or "swing" in name]
        for pair in pairs.values():
            abnormal, normal = pair["anomalous_twist"], pair["same_angle_preserved"]
            for key in ("rest_vertices", "weights", "bone_chain", "triangles", "sections", "vertex_ids"):
                self.assertEqual(abnormal["packet"][key], normal["packet"][key])
            xa, _ = expert.extract_features(abnormal["packet"])
            xn, _ = expert.extract_features(normal["packet"])
            np.testing.assert_array_equal(xa[:, angle_columns], xn[:, angle_columns])
            self.assertFalse(np.allclose(xa, xn))
            self.assertTrue(any(v > 0 for v in abnormal["label_severity"]))
            self.assertTrue(all(v == 0 for v in normal["label_severity"]))

    def test_actual_learned_default_weights_and_single_model_load(self):
        from human_eye_plugin.arm_twist_weights import PARAMETERS
        self.assertGreater(np.count_nonzero(PARAMETERS["w1"]), 0)
        self.assertGreater(np.count_nonzero(PARAMETERS["w2"]), 0)
        expert.get_default_expert.cache_clear()
        real_class = expert.ArmTwistExpert
        try:
            with patch.object(expert, "ArmTwistExpert", wraps=real_class) as constructor:
                first = expert.get_default_expert()
                self.assertIs(expert.get_default_expert(), first)
                first.predict(one_case()["packet"])
                self.assertEqual(constructor.call_count, 1)
        finally:
            expert.get_default_expert.cache_clear()

    def test_heldout_same_angle_preserved_control_is_not_an_angle_threshold_rule(self):
        model = expert.get_default_expert()
        test_cases = [case for case in cases() if case["metadata"]["split"] == "test"]
        for normal in (c for c in test_cases if c["metadata"]["pose_family"] == "same_angle_preserved"):
            abnormal = next(c for c in test_cases if c["metadata"]["pair_id"] == normal["metadata"]["pair_id"]
                            and c["metadata"]["pose_family"] == "anomalous_twist")
            healthy, changed = model.predict(normal["packet"]), model.predict(abnormal["packet"])
            self.assertEqual(healthy["status"], "estimated")
            self.assertEqual(changed["status"], "estimated")
            self.assertTrue(all(not row["flagged"] for row in healthy["regions"]))
            self.assertTrue(any(row["flagged"] for row in changed["regions"]))
            index = int(np.argmax(scores(changed)))
            self.assertGreater(abnormal["label_severity"][index], 0.)
            for row in changed["regions"]:
                self.assertTrue(0. <= row["predicted_severity"] <= 1.)
                self.assertEqual(row["vertex_ids"], [abnormal["packet"]["vertex_ids"][j]
                                                     for j in abnormal["packet"]["sections"][row["section_index"]]])

    def test_trained_predictions_really_change_when_valid_tensor_bias_changes(self):
        from human_eye_plugin.arm_twist_weights import PARAMETERS
        packet = one_case(family="same_angle_preserved")["packet"]
        original = expert.ArmTwistExpert(PARAMETERS)
        changed = copy.deepcopy(PARAMETERS)
        changed["b2"][0] += .5
        other = expert.ArmTwistExpert(changed)
        self.assertGreater(float(np.max(np.abs(scores(original.predict(packet)) - scores(other.predict(packet))))), .1)

    def test_normal_service_import_does_not_eagerly_load_trained_expert(self):
        code = ("import sys;sys.path.insert(0,sys.argv[1]);"
                "import human_eye_plugin.live_service;"
                "assert 'human_eye_plugin.arm_twist_weights' not in sys.modules;"
                "m=sys.modules.get('human_eye_plugin.arm_twist_expert');"
                "assert m is None or m.get_default_expert.cache_info().currsize==0")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
