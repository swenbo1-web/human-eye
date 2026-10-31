"""Human-Eye 9.7.2 回归测试（P0 修复验收）

覆盖本次审计暴露的四类问题：
  1. 凹形参考件（U 槽 / L 角）的假穿模    -> test_concave_*
  2. 间隙判据在贴合边界的不连续          -> test_clearance_continuity
  3. 复检来源不可识别 / 报告不可复现      -> test_verify_mode_* / test_posed_se3_*
  4. 场景交换丢失姿态元数据（local_axes） -> test_scene_roundtrip_*

运行：
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import unittest

import numpy as np

from human_eye_plugin import HumanEyeLLMPlugin
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import validate_local_axes
from human_eye_module1_operators import (
    MeshEntity3D,
    SE3AlignmentMath,
    SpatialAnomalySniffer,
)

SCENARIOS = {
    "S04_Deep_Penetration",
    "S06_Crease_Lateral_Wall",
    "S07_Cross_Lap_Beams",
    "S11_Extreme_180_Singularity",
    "S12_Full_Burial_Inside",
    "S13_U_Channel_Slot",
    "S16_L_Bracket_Corner",
}


def _scene(name):
    """返回场景的深拷贝：避免用例之间互相污染（场景模板是类级缓存）。"""
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    table = {row[0]: row[1] for row in p.vlm_agent._get_or_build_benchmark_scenarios()}
    return [MeshEntity3D.from_dict(m.to_dict()) for m in table[name]]


def _prescription(meshes):
    p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
    bundle = p.build_llm_observation_bundle(meshes=p.meshes)
    return dict(bundle["prompt_bundle"].canonical_mcp_tool_call["arguments"])


def _apply_literal(meshes, args):
    focal = next(m for m in meshes if m.is_focal_target)
    ref = next(m for m in meshes if m.object_id != focal.object_id)
    rot = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
    piv = np.array(args["pivot_world"], dtype=np.float64) if "pivot_world" in args else None
    aligned = focal.rotated_around_pivot(rot, pivot=piv).translated(tuple(args["translation_xyz_m"]))
    probe = SpatialAnomalySniffer.probe_closest_clearance(aligned, ref, yaw_symmetry_order=2)
    return aligned, ref, probe


def _rot_diff_deg(a, b):
    ra = SE3AlignmentMath.euler_xyz_to_matrix(*a)
    rb = SE3AlignmentMath.euler_xyz_to_matrix(*b)
    d = ra.T @ rb
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(d) - 1.0) / 2.0))))


class TestConcaveReference(unittest.TestCase):
    """P0-1：凹形参考件不得再报出零件尺寸量级的"穿透深度"。"""

    def test_concave_scenarios_reach_flush(self):
        for name in ("S13_U_Channel_Slot", "S16_L_Bracket_Corner"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                args = _prescription(meshes)
                _, _, probe = _apply_literal(meshes, args)
                self.assertLessEqual(abs(probe.signed_clearance_m) * 1000.0, 0.5,
                                     f"{name}: |gap| 应 ≤0.5mm，实际 {probe.signed_clearance_m*1000:.2f}mm")
                self.assertFalse(probe.is_penetrating, f"{name}: 不应判穿模")
                self.assertEqual(probe.alignment_state, "ALIGNED_FLUSH")

    def test_convex_scenarios_unchanged(self):
        for name in ("S04_Deep_Penetration", "S06_Crease_Lateral_Wall", "S07_Cross_Lap_Beams",
                     "S11_Extreme_180_Singularity", "S12_Full_Burial_Inside"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                args = _prescription(meshes)
                _, _, probe = _apply_literal(meshes, args)
                self.assertLessEqual(abs(probe.signed_clearance_m) * 1000.0, 0.5)
                self.assertFalse(probe.is_penetrating)

    def test_penetration_depth_bounded_by_part_size(self):
        """任何测量结果都不得超过焦点件最小边长（物理上界校验）。"""
        for name in sorted(SCENARIOS):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                args = _prescription(meshes)
                _, _, probe = _apply_literal(meshes, args)
                focal = next(m for m in meshes if m.is_focal_target)
                limit = float(np.min(focal.bbox_max - focal.bbox_min)) * 1000.0
                self.assertLessEqual(abs(probe.signed_clearance_m) * 1000.0, limit + 0.5,
                                     f"{name}: 深度超出零件尺寸 {limit:.1f}mm")


class TestClearanceContinuity(unittest.TestCase):
    """P0-1：贴合边界处判据必须连续（历史缺陷：0.1mm 位移导致 420mm 跳变）。"""

    def test_clearance_continuity(self):
        meshes = _scene("S13_U_Channel_Slot")
        args = _prescription(meshes)
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        rot = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
        piv = np.array(args["pivot_world"], dtype=np.float64)
        tx, ty, z0 = args["translation_xyz_m"]

        prev = None
        for k in range(0, 21):
            dz = z0 + k * 0.0005          # 从处方落点起，每次抬高 0.5 mm
            probe = SpatialAnomalySniffer.probe_closest_clearance(
                focal.rotated_around_pivot(rot, pivot=piv).translated((tx, ty, dz)),
                ref, yaw_symmetry_order=2)
            gap_mm = probe.signed_clearance_m * 1000.0
            self.assertLessEqual(abs(gap_mm), 25.0,
                                 f"抬升 {k*0.5:.1f}mm 处读数 {gap_mm:.1f}mm 超出合理范围")
            if prev is not None:
                self.assertLessEqual(abs(gap_mm - prev), 5.5,
                                     f"抬升 {k*0.5:.1f}mm 处出现跳变：{prev:.2f} -> {gap_mm:.2f}mm")
            prev = gap_mm


class TestRecheckContract(unittest.TestCase):
    """P0-2 / P0-3：复检必须标明来源，且报告里的位姿必须可复现。"""

    def test_verify_mode_measured_by_default(self):
        meshes = _scene("S13_U_Channel_Slot")
        p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
        focal = next(m for m in p.meshes if m.is_focal_target)
        ref = next(m for m in p.meshes if m.object_id != focal.object_id)
        args = _prescription(meshes)
        _, report, _ = p.controller.apply_se3_prescription_and_recheck(
            focal_mesh=focal, reference_mesh=ref, mcp_arguments=args,
            scene_meshes=p.meshes, enable_ecbf_shield=True)
        self.assertEqual(report.verify_mode, "measured")
        self.assertTrue(report.verification_passed)

    def test_posed_se3_reproduces_final_state(self):
        for name in ("S13_U_Channel_Slot", "S16_L_Bracket_Corner", "S07_Cross_Lap_Beams"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
                focal = next(m for m in p.meshes if m.is_focal_target)
                ref = next(m for m in p.meshes if m.object_id != focal.object_id)
                before = np.asarray(focal.vertices, dtype=np.float64).copy()
                args = _prescription(meshes)
                aligned, report, _ = p.controller.apply_se3_prescription_and_recheck(
                    focal_mesh=focal, reference_mesh=ref, mcp_arguments=args,
                    scene_meshes=p.meshes, enable_ecbf_shield=True)
                se3 = np.array(report.posed_se3_4x4, dtype=np.float64)
                self.assertEqual(se3.shape, (4, 4))
                recon = before @ se3[:3, :3].T + se3[:3, 3]
                err = float(np.abs(recon - np.asarray(aligned.vertices)).max())
                self.assertLess(err, 1e-9, f"{name}: 由 posed_se3_4x4 复原误差 {err:.3e} m")


class TestSceneExchange(unittest.TestCase):
    """P0-3：场景交换不得丢失 local_axes；缺失时应推断并标注。"""

    def test_roundtrip_preserves_prescription(self):
        for name in ("S08_Inclined_30deg_Ramp", "S13_U_Channel_Slot", "S16_L_Bracket_Corner"):
            with self.subTest(scenario=name):
                native = _scene(name)
                c_native = _prescription(native)
                full = [MeshEntity3D.from_dict(m.to_dict()) for m in native]
                c_full = _prescription(full)
                self.assertLess(
                    _rot_diff_deg(c_native["rotation_euler_deg_xyz"], c_full["rotation_euler_deg_xyz"]), 1e-5)
                self.assertEqual(getattr(full[0], "axes_source", "host"), "host")

    def test_vertices_only_scene_infers_or_explicitly_rejects_ambiguous_frame(self):
        for name in ("S08_Inclined_30deg_Ramp", "S13_U_Channel_Slot"):
            with self.subTest(scenario=name):
                native = _scene(name)
                c_native = _prescription(native)
                stripped = []
                for m in native:
                    d = m.to_dict()
                    d.pop("local_axes", None)
                    stripped.append(MeshEntity3D.from_dict(d))
                if name == "S13_U_Channel_Slot":
                    # 凹形件不能从几何唯一恢复宿主的工程基准；必须拒绝认证。
                    reference = next(m for m in stripped if not m.is_focal_target)
                    focal = next(m for m in stripped if m.is_focal_target)
                    self.assertEqual(reference.axes_source, "ambiguous_geometry")
                    self.assertEqual(reference.axes_confidence, "ambiguous")
                    probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference)
                    self.assertFalse(probe.axes_valid)
                    from human_eye_module1_operators import SpatialAlignmentVerifier
                    _, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                        focal_mesh=focal, reference_mesh=reference, scene_meshes=stripped)
                    self.assertFalse(report.verification_passed)
                    continue
                self.assertEqual(getattr(stripped[0], "axes_source", ""), "inferred_surface")
                self.assertTrue(all(validate_local_axes(m)[0] for m in stripped))
                c_inf = _prescription(stripped)
                # 历史缺陷：漂移 4.5°~42°；修复后应 < 0.5°
                drift = _rot_diff_deg(c_native["rotation_euler_deg_xyz"], c_inf["rotation_euler_deg_xyz"])
                self.assertLess(drift, 0.5, f"{name}: 仅顶点重建后处方漂移 {drift:.2f}°")

    def test_single_source_of_truth(self):
        """单体与分包必须是同一套类对象（历史缺陷：同名不同类）。"""
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        self.assertIs(pkg.MeshEntity3D, mono.MeshEntity3D)
        self.assertIs(pkg.SpatialClearanceProbeResult, mono.SpatialClearanceProbeResult)
        self.assertIs(pkg.ClosedLoopRecheckReport, mono.ClosedLoopRecheckReport)


class TestSmokeFlow(unittest.TestCase):
    """端到端：观测 -> 执行 -> 复检。"""

    def test_observe_apply_recheck(self):
        p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
        obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas",
                                   {"focal_mark": "#B", "reference_mark": "#A"})
        self.assertEqual(obs["mcp_image_content"]["mimeType"], "image/png")
        self.assertTrue(obs["som_anchor_table"])
        action = obs["canonical_mcp_tool_call"]
        result = p.dispatch_tool_call(action["tool"], action["arguments"])
        self.assertTrue(result["verification_passed"])
        probe = p.dispatch_tool_call("human_eye_probe_spatial_clearance",
                                     {"focal_mark": "#B", "reference_mark": "#A"})
        self.assertEqual(probe["alignment_state"], "ALIGNED_FLUSH")


class TestRaycastDepth(unittest.TestCase):
    """P0-1b：真正穿透时必须有可靠的完整几何判定和有界深度。"""

    def test_certified_convex_metric_used_for_true_penetration(self):
        for name in ("S04_Deep_Penetration", "S12_Full_Burial_Inside"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                focal = next(m for m in meshes if m.is_focal_target)
                ref = next(m for m in meshes if m.object_id != focal.object_id)
                probe = SpatialAnomalySniffer.probe_closest_clearance(focal, ref, yaw_symmetry_order=2)
                self.assertTrue(probe.is_penetrating, f"{name}: 初始应为穿模态")
                self.assertEqual(probe.measurement_method, "convex_sat")
                self.assertGreater(abs(probe.signed_clearance_m), 1e-3)
                self.assertTrue(probe.measurement_valid)

    def test_contact_is_not_reported_as_deep_penetration(self):
        for name in ("S13_U_Channel_Slot", "S16_L_Bracket_Corner"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                args = _prescription(meshes)
                _, _, probe = _apply_literal(meshes, args)
                self.assertLessEqual(abs(probe.signed_clearance_m) * 1000.0, 0.5)
                self.assertFalse(probe.is_penetrating)
                self.assertEqual(probe.measurement_method, "convex_components_sat")
                self.assertTrue(probe.measurement_valid)


class TestResponseDetail(unittest.TestCase):
    """P2：默认 compact 保持响应体积，full 才返回 4×4 位姿。"""

    def _apply(self, detail=None):
        p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
        obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas",
                                   {"focal_mark": "#B", "reference_mark": "#A"})
        act = obs["canonical_mcp_tool_call"]
        args = dict(act["arguments"])
        if detail:
            args["detail_level"] = detail
        return p.dispatch_tool_call(act["tool"], args)

    def test_compact_omits_pose_matrix(self):
        resp = self._apply()
        self.assertNotIn("posed_se3_4x4", resp["applied_se3_action"])
        self.assertNotIn("verification", resp)
        self.assertIn("verify_mode", resp["post_recheck_metrics"])
        self.assertEqual(resp["applied_se3_action"]["euler_convention"], "extrinsic_XYZ")

    def test_full_returns_pose_matrix(self):
        resp = self._apply("full")
        self.assertIn("posed_se3_4x4", resp["applied_se3_action"])
        self.assertEqual(len(resp["applied_se3_action"]["posed_se3_4x4"]), 4)
        self.assertEqual(resp["verification"]["verify_mode"], "measured")


class TestAxesValidation(unittest.TestCase):
    """P1：宿主 local_axes 必须与几何自洽，否则不予认证（防"轴错了 + 自检也错"）。"""

    def test_all_benchmark_parts_have_valid_axes(self):
        for name in ("S01_Horizontal_Table", "S08_Inclined_30deg_Ramp", "S13_U_Channel_Slot",
                     "S16_L_Bracket_Corner"):
            with self.subTest(scenario=name):
                for m in _scene(name):
                    ok, why = validate_local_axes(m)
                    self.assertTrue(ok, f"{name}/{m.mark_label}: {why}")

    def test_twisted_axes_are_rejected(self):
        for name in ("S08_Inclined_30deg_Ramp", "S16_L_Bracket_Corner"):
            with self.subTest(scenario=name):
                meshes = _scene(name)
                focal = next(m for m in meshes if m.is_focal_target)
                spin = SE3AlignmentMath.euler_xyz_to_matrix(0.0, 0.0, 25.0)
                focal.local_axes = focal.local_axes @ spin.T
                ok, why = validate_local_axes(focal)
                self.assertFalse(ok)
                self.assertIn("axis", why)

    def test_invalid_axes_blocks_certification(self):
        """轴被拧过之后，即便几何上贴平，闭环也不得判通过。"""
        meshes = _scene("S08_Inclined_30deg_Ramp")
        args = _prescription(meshes)
        focal = next(m for m in meshes if m.is_focal_target)
        spin = SE3AlignmentMath.euler_xyz_to_matrix(0.0, 0.0, 25.0)
        focal.local_axes = focal.local_axes @ spin.T
        foc = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != foc.object_id)
        p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
        f2 = next(m for m in p.meshes if m.is_focal_target)
        r2 = next(m for m in p.meshes if m.object_id != f2.object_id)
        _, report, _ = p.controller.apply_se3_prescription_and_recheck(
            focal_mesh=f2, reference_mesh=r2, mcp_arguments=args,
            scene_meshes=p.meshes, enable_ecbf_shield=True)
        self.assertFalse(report.verification_passed)
        self.assertFalse(report.post_probe.axes_valid)


class TestImplementationUnification(unittest.TestCase):
    """D1：产品链路必须使用包内（已修）实现，不得混用单体里的旧副本。"""

    def test_product_modules_use_package_implementations(self):
        import human_eye_module1_operators as pkg
        import module_2_low_token_mcp_scene_bridge as m2
        import module_3_2_vlm_grounding_closed_loop_agent as m32
        import human_eye_plugin.plugin_facade as facade
        self.assertIs(m32.SpatialAnomalySniffer, pkg.SpatialAnomalySniffer)
        self.assertIs(m32.SpatialAlignmentVerifier, pkg.SpatialAlignmentVerifier)
        self.assertIs(m32.SE3AlignmentMath, pkg.SE3AlignmentMath)
        self.assertIs(m2.MeshEntity3D, pkg.MeshEntity3D)
        self.assertIs(facade.SpatialAnomalySniffer, pkg.SpatialAnomalySniffer)

    def test_legacy_copy_is_detectably_different_on_concave_case(self):
        """单体旧副本对已对齐的槽位件会误判穿模；产品路径不得复现该结论。"""
        import numpy as np
        from human_eye_module1_operators import SE3AlignmentMath
        meshes = _scene("S13_U_Channel_Slot")
        args = _prescription(meshes)
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        rot = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
        piv = np.array(args["pivot_world"], dtype=np.float64)
        aligned = focal.rotated_around_pivot(rot, pivot=piv).translated(tuple(args["translation_xyz_m"]))
        probe = SpatialAnomalySniffer.probe_closest_clearance(aligned, ref, yaw_symmetry_order=2)
        self.assertFalse(probe.is_penetrating)
        self.assertLessEqual(abs(probe.signed_clearance_m), 5e-4)


class TestCompositorSingleSource(unittest.TestCase):
    """D1：四宫格合成器只应存在于包内，单体通过惰性访问器获取。"""

    def test_compositor_lives_in_package_only(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        self.assertIs(mono._quad_compositor_cls(), pkg.QuadCognitiveCanvasCompositor)
        self.assertIs(mono.QuadCognitiveCanvasCompositor, pkg.QuadCognitiveCanvasCompositor,
                         "单体不应再定义模块级合成器")

    def test_render_unchanged_after_extraction(self):
        """迁移不应改变渲染结果：同一场景两次渲染应完全一致。"""
        import base64
        import hashlib
        p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
        obs1 = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
        p2 = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
        obs2 = p2.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
        h1 = hashlib.sha256(base64.b64decode(obs1["mcp_image_content"]["data"])).hexdigest()
        h2 = hashlib.sha256(base64.b64decode(obs2["mcp_image_content"]["data"])).hexdigest()
        self.assertEqual(h1, h2)


class TestSubFrustumSingleSource(unittest.TestCase):
    """D1：视锥投影数学只应存在于包内，单体通过惰性访问器获取。"""

    def test_class_lives_in_package_only(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        self.assertIs(mono._stf(), pkg.SubFrustumMathEngine)
        self.assertIs(mono.SubFrustumMathEngine, pkg.SubFrustumMathEngine,
                         "单体不应再定义模块级视锥投影类")

    def test_every_member_is_forwarded(self):
        """惰性访问器必须能取到全部成员（漏一个就会在渲染时 AttributeError）。"""
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        target = pkg.SubFrustumMathEngine
        for name in dir(target):
            if name.startswith("__"):
                continue
            self.assertTrue(hasattr(mono._stf(), name), f"未转发: {name}")

    def test_class_cache_is_singleton(self):
        """访问器必须缓存，避免每次渲染重复 import。"""
        import human_eye_foveated_renderer as mono
        self.assertIs(mono._stf(), mono._stf())
        self.assertIsNotNone(mono._SUB_FRUSTUM_CLS)

    def test_camera_math_matches_package(self):
        """单体的相机计算路径与包内直接调用必须给出逐位相同的结果。"""
        import numpy as np
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        eye = np.array([1.2, 1.1, 0.9])
        target = np.array([0.0, 0.0, 0.1])
        a = mono._stf().build_look_at_view_matrix(eye, target)
        b = pkg.SubFrustumMathEngine.build_look_at_view_matrix(eye, target)
        np.testing.assert_array_equal(np.asarray(a), np.asarray(b))


class TestVerifierSingleSource(unittest.TestCase):
    """D1：闭环验证器与其 13 个报表契约只应存在于包内，单体通过惰性访问器 + 再导出。"""

    REPORTS = (
        "ASMEGDTVerificationReport", "AdmittanceControlLawReport",
        "ClosedLoopIdempotencyLyapunovReport", "CollisionFreeInsertionReport",
        "DigitalTwinAuditCertificate", "IterativeSE3AlignmentReport",
        "MechanicalStabilityAuditReport", "MonteCarloAssemblyYieldReport",
        "MultiBodyAssemblyChainReport", "MultiBoltPreloadSequenceReport",
        "ObservabilityFisherInformationReport", "ThermoElasticPreloadReport",
        "VisualServoHandEyeCalibrationReport",
    )

    def test_verifier_lives_in_package_only(self):
        """单体源码不得再定义该类（访问器与再导出仍可用，故不能用 hasattr 判断）。"""
        import pathlib
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        self.assertIs(mono._sav(), pkg.SpatialAlignmentVerifier)
        src = pathlib.Path(mono.__file__).read_text(encoding="utf-8")
        self.assertNotIn("class SpatialAlignmentVerifier(", src,
                         "单体源码不应再定义验证器类")
        for name in self.REPORTS:
            self.assertNotIn(f"class {name}:", src, f"单体源码不应再定义 {name}")

    def test_report_contracts_are_same_objects(self):
        """13 个报表类必须与包内是同一对象，不得是"同名不同类"。"""
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators.submodule_1_5_alignment_verifier as s5
        for name in self.REPORTS:
            with self.subTest(report=name):
                self.assertIs(getattr(mono, name), getattr(s5, name))

    def test_helpers_are_same_objects(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators.submodule_1_5_alignment_verifier as s5
        for name in ("_inherit_translated_intrinsic_metrics", "_inherit_rotated_intrinsic_metrics"):
            self.assertIs(getattr(mono, name), getattr(s5, name))

    def test_module_getattr_keeps_from_import_working(self):
        """PEP 562：`from 单体 import X` 必须仍然可用（向后兼容）。"""
        from human_eye_foveated_renderer import (  # noqa: F401
            ASMEGDTVerificationReport,
            IterativeSE3AlignmentReport,
            SpatialAlignmentVerifier,
        )
        import human_eye_module1_operators.submodule_1_5_alignment_verifier as s5
        self.assertIs(SpatialAlignmentVerifier, s5.SpatialAlignmentVerifier)
        self.assertIs(IterativeSE3AlignmentReport, s5.IterativeSE3AlignmentReport)

    def test_unknown_attribute_still_raises(self):
        import human_eye_foveated_renderer as mono
        with self.assertRaises(AttributeError):
            _ = mono.DefinitelyNotARealName

    def test_verifier_executes_through_accessor(self):
        """经惰性访问器实际执行一次闭环，确认调用路径完好。"""
        meshes = _scene("S01_Horizontal_Table")
        p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
        foc = next(m for m in p.meshes if m.is_focal_target)
        ref = next(m for m in p.meshes if m.object_id != foc.object_id)
        import human_eye_foveated_renderer as mono
        _, report = mono._sav().execute_alignment_and_recheck(
            focal_mesh=foc, reference_mesh=ref, scene_meshes=[ref, foc])
        self.assertTrue(report.verification_passed)
        self.assertLessEqual(report.residual_error_mm, 1e-6)
        self.assertEqual(report.verify_mode, "measured")


class TestSE3SingleSource(unittest.TestCase):
    """D1：李群数学只应有一份实现，1_3 为再导出层（热路径，要求零调用开销）。"""

    HELPERS = (
        "_batch_matvec", "_IDENTITY_9_TUPLE", "_PACK_3D_INTO", "_PACK_6D_INTO",
        "_PACK_9D_INTO", "_PACK_16D_INTO", "_STRUCT_3D", "_STRUCT_6D", "_STRUCT_9D",
        "_STRUCT_16D", "_UNPACK_3D", "_UNPACK_6D", "_UNPACK_9D", "_UNPACK_16D",
    )

    def test_single_identity(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        import human_eye_module1_operators.submodule_1_3_se3_alignment_math as leaf
        self.assertIs(mono.SE3AlignmentMath, leaf.SE3AlignmentMath)
        self.assertIs(pkg.SE3AlignmentMath, mono.SE3AlignmentMath)

    def test_shim_holds_no_implementation(self):
        """1_3 不得再有类定义，否则又会出现"同名不同类"。"""
        import pathlib
        import human_eye_module1_operators.submodule_1_3_se3_alignment_math as leaf
        src = pathlib.Path(leaf.__file__).read_text(encoding="utf-8")
        self.assertNotIn("class SE3AlignmentMath", src)

    def test_helpers_shared(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators.submodule_1_3_se3_alignment_math as leaf
        for name in self.HELPERS:
            with self.subTest(symbol=name):
                self.assertIs(getattr(leaf, name), getattr(mono, name))

    def test_scalar_primitive_bit_fidelity(self):
        """标量基元必须与标量公式逐位相同（0.0 ULP 契约）。"""
        import math
        import numpy as np
        from human_eye_foveated_renderer import SE3AlignmentMath as C
        rng = np.random.default_rng(20261021)
        for _ in range(200):
            a = rng.normal(size=3) * 10.0
            b = rng.normal(size=3) * 10.0
            cross = C._cross3(a, b)
            self.assertEqual(cross[0], a[1] * b[2] - a[2] * b[1])
            self.assertEqual(cross[1], a[2] * b[0] - a[0] * b[2])
            self.assertEqual(cross[2], a[0] * b[1] - a[1] * b[0])
            # 范数必须走 math.sqrt(平方和)，而非 hypot / np.linalg.norm
            self.assertEqual(C._norm3(a),
                             math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]))

    def test_euler_and_triad_residual(self):
        """欧拉合成与全标架配准的数值残差必须保持在浮点噪声内。"""
        import numpy as np
        from human_eye_foveated_renderer import SE3AlignmentMath as C
        R = C.euler_xyz_to_matrix(11.0, -9.5, 14.25)
        self.assertLess(float(np.abs(R @ R.T - np.eye(3)).max()), 1e-12)
        self.assertAlmostEqual(float(np.linalg.det(R)), 1.0, places=12)

        na = np.array([0.3, -0.4, 0.8660254])
        na /= np.linalg.norm(na)
        axes = np.eye(3)
        rot_mat, quat, euler, tilt, yaw = C.compute_full_triad_alignment(
            na, np.array([0.0, 0.0, 1.0]), axes, axes, yaw_symmetry_order=2)
        # 不变量 1：把 na 旋到 -nb
        np.testing.assert_allclose(rot_mat @ na, np.array([0.0, 0.0, -1.0]), atol=1e-9)
        # 不变量 2：返回值 tilt 即 angle(na, -nb)（本例 150°）
        self.assertAlmostEqual(tilt, 150.0, places=6)
        # 不变量 3：四元数为单位四元数
        self.assertLess(abs(float(np.linalg.norm(quat)) - 1.0), 1e-5)
        # 不变量 4：欧拉角回代能复原同一旋转。
        # 注意 euler 三元组是回报值（四舍五入到 4 位小数），回代误差量级 ~1e-4，
        # 这里校验的是"语义一致"而非 0 ULP；0 ULP 由 rot_mat 本身保证。
        np.testing.assert_allclose(C.euler_xyz_to_matrix(*euler), rot_mat, atol=1e-4)

    def test_no_accessor_on_hot_path(self):
        """热路径不得引入惰性访问器：类必须在模块级直接可见。"""
        import human_eye_foveated_renderer as mono
        self.assertIn("SE3AlignmentMath", vars(mono))


class TestSnifferSingleSource(unittest.TestCase):
    """D1：空间嗅探引擎只应有一份实现，且单体路径必须走已修复版本。"""

    def test_single_identity(self):
        import human_eye_foveated_renderer as mono
        import human_eye_module1_operators as pkg
        import human_eye_module1_operators.submodule_1_4_spatial_sniffer as leaf
        self.assertIs(mono._snf(), pkg.SpatialAnomalySniffer)
        self.assertIs(leaf.SpatialAnomalySniffer, pkg.SpatialAnomalySniffer)

    def test_monolith_holds_no_implementation(self):
        import pathlib
        import human_eye_foveated_renderer as mono
        src = pathlib.Path(mono.__file__).read_text(encoding="utf-8")
        self.assertNotIn("class SpatialAnomalySniffer", src,
                         "单体源码不应再定义空间嗅探引擎")

    def test_from_import_compatible(self):
        from human_eye_foveated_renderer import SpatialAnomalySniffer  # noqa: F401
        import human_eye_module1_operators as pkg
        self.assertIs(SpatialAnomalySniffer, pkg.SpatialAnomalySniffer)

    def test_monolith_path_uses_fixed_penetration_metric(self):
        """单体路径必须给出修复后的结论：凹形件贴合态不再是 −370mm。"""
        import numpy as np
        import human_eye_foveated_renderer as mono
        from human_eye_module1_operators import SE3AlignmentMath
        meshes = _scene("S13_U_Channel_Slot")
        args = _prescription(meshes)
        rot = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        aligned = focal.rotated_around_pivot(rot, pivot=np.array(args["pivot_world"])) \
            .translated(tuple(args["translation_xyz_m"]))
        probe = mono.SpatialAnomalySniffer.probe_closest_clearance(
            aligned, ref, yaw_symmetry_order=2)
        self.assertFalse(probe.is_penetrating)
        self.assertLessEqual(abs(probe.signed_clearance_m), 5e-4)
        self.assertEqual(probe.measurement_method, "convex_components_sat")
        self.assertTrue(probe.measurement_valid)

    def test_probe_stable_over_200_consecutive_calls(self):
        """连续 200 次探针必须给出逐位相同的结果（缓存不得引入漂移）。"""
        from human_eye_module1_operators import MeshEntity3D
        meshes = [MeshEntity3D.from_dict(m.to_dict()) for m in _scene("S01_Horizontal_Table")]
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        first = SpatialAnomalySniffer.probe_closest_clearance(focal, ref, yaw_symmetry_order=2)
        sig0 = (first.alignment_state, first.signed_clearance_m, first.contact_normal_angle_deg,
                first.tangent_yaw_mismatch_deg, first.measurement_method, bool(first.is_penetrating))
        for i in range(200):
            p = SpatialAnomalySniffer.probe_closest_clearance(focal, ref, yaw_symmetry_order=2)
            sig = (p.alignment_state, p.signed_clearance_m, p.contact_normal_angle_deg,
                   p.tangent_yaw_mismatch_deg, p.measurement_method, bool(p.is_penetrating))
            self.assertEqual(sig, sig0, f"第 {i+1} 次探针出现漂移")

    def test_probe_cache_does_not_leak_between_meshes(self):
        """缓存按网格状态键隔离：换参考件后必须重新测量。"""
        from human_eye_module1_operators import MeshEntity3D
        a = [MeshEntity3D.from_dict(m.to_dict()) for m in _scene("S01_Horizontal_Table")]
        b = [MeshEntity3D.from_dict(m.to_dict()) for m in _scene("S13_U_Channel_Slot")]
        fa = next(m for m in a if m.is_focal_target)
        ra = next(m for m in a if m.object_id != fa.object_id)
        pa1 = SpatialAnomalySniffer.probe_closest_clearance(fa, ra, yaw_symmetry_order=2)
        fb = next(m for m in b if m.is_focal_target)
        rb = next(m for m in b if m.object_id != fb.object_id)
        SpatialAnomalySniffer.probe_closest_clearance(fb, rb, yaw_symmetry_order=2)
        pa2 = SpatialAnomalySniffer.probe_closest_clearance(fa, ra, yaw_symmetry_order=2)
        self.assertEqual(pa1.signed_clearance_m, pa2.signed_clearance_m)
        self.assertEqual(pa1.alignment_state, pa2.alignment_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
