"""
Human-Eye (人类之眼) 全栈三维空间智能插件 — 核心统一门面与大模型 A/B 效果对比引擎 (plugin_facade.py)
========================================================================================================
将模块一（human-eye-core 1.1~1.6 + 3D 暂存空间）、模块二（低 Token 场景桥）、模块三（3.1 零拷贝 IPC +
3.2 VLM 接地智能体 + 3.3 闭环动作控制器）封装为单一即插即用插件类 `HumanEyeLLMPlugin`，
原生支持 OpenAI / DeepSeek / Qwen-VL / Claude / Gemini / MCP 多模态消息构建、工具路由与 A/B 效果对比测试。
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import pathlib
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

_ROOT_DIR = str(pathlib.Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from human_eye_module1_operators import (
    ClosedLoopActionController,
    CompactScenePatchDSLSerializer,
    LowTokenMCPBridgeServer,
    McpProtocolEngine,
    MeshEntity3D,
    QuadCognitiveCanvasCompositor,
    SE3AlignmentMath,
    SpatialAlignmentVerifier,
    SpatialAnomalySniffer,
    SpatialScratchpadRingBuffer,
    SphericalIoRMultiLocusSniffer,
    SubFrustumMathEngine,
    VLMSpatialGroundingAndClosedLoopAgent,
    ZeroCopyTensorArena,
)
from .llm_tool_schemas import (
    ANTHROPIC_TOOLS_SCHEMA,
    GEMINI_TOOLS_SCHEMA,
    HUMAN_EYE_CORE_TOOLS_SPEC,
    MCP_TOOLS_SCHEMA,
    OPENAI_TOOLS_SCHEMA,
    get_llm_tools_schema,
)
from human_eye_module1_operators.submodule_1_5_alignment_verifier import _probe_is_trustworthy


@dataclasses.dataclass
class LLMABComparisonResult:
    """大模型接入 Human-Eye 插件前后的 A/B 效果对比结构化评估报告"""
    scenario_name: str
    baseline_residual_clearance_mm: float
    plugin_residual_clearance_mm: float
    baseline_residual_tilt_deg: float
    plugin_residual_tilt_deg: float
    baseline_residual_yaw_deg: float
    plugin_residual_yaw_deg: float
    baseline_passed: bool
    plugin_passed: bool
    plugin_hallucination_intercepted: bool
    plugin_ecbf_shield_activated: bool
    plugin_total_tokens: int
    baseline_estimated_scene_json_tokens: int
    token_saving_ratio_pct: float
    plugin_execution_time_ms: float
    summary_message: str
    baseline_total_tokens: int = 0
    token_count_basis: str = "estimated_observation"
    evaluation_mode: str = "provided_responses"


class HumanEyeLLMPlugin:
    """
    Human-Eye (人类之眼 V9.7) 面向多模态大语言模型（LLM/VLM）的全栈即插即用插件总控类：
    - 支持一键生成 OpenAI / DeepSeek / Claude / Gemini / MCP 工具定义与多模态视觉-文本提示词载荷；
    - 内置 `enable_human_eye_plugin=True/False` 双模态开关，供后续直接接入大模型开展 A/B 效果对比评测。
    """

    VERSION: str = "9.7.2"

    def __init__(
        self,
        meshes: Optional[List[MeshEntity3D]] = None,
        quad_size: int = 384,
        enable_zero_copy_ipc: bool = True,
    ) -> None:
        self.quad_size = int(quad_size)
        self.vlm_agent = VLMSpatialGroundingAndClosedLoopAgent(
            quad_size=self.quad_size, enable_zero_copy_ipc=enable_zero_copy_ipc
        )
        self.controller = ClosedLoopActionController(
            quad_size=self.quad_size, enable_zero_copy_ipc=enable_zero_copy_ipc
        )
        self.ior_sniffer = SphericalIoRMultiLocusSniffer()
        if meshes is not None:
            self.meshes: List[MeshEntity3D] = list(meshes)
        else:
            scenarios = self.vlm_agent._get_or_build_benchmark_scenarios()
            self.meshes = list(scenarios[0][1])
        self.set_scene_meshes(self.meshes)

    @staticmethod
    def get_tools_schema(vendor: str = "openai") -> List[Dict[str, Any]]:
        """获取指定大模型厂商格式（openai / deepseek / anthropic / gemini / mcp）的工具调用 Schema"""
        return get_llm_tools_schema(vendor)

    def set_scene_meshes(self, meshes: List[MeshEntity3D]) -> None:
        """更新当前插件托管的 3D 场景构件列表"""
        self.scene_bridge = LowTokenMCPBridgeServer(meshes=list(meshes), quad_size=self.quad_size)
        # Keep one list for actions and observations; preserve it across moves so
        # the Merkle tracker can compare the scene before and after each action.
        self.meshes = self.scene_bridge.meshes
        self.scratchpad = self.scene_bridge.scratchpad
        for owner in (self.vlm_agent, self.controller):
            owner._scene_bridge = self.scene_bridge
            if owner._mcp_ipc_engine is not None:
                owner._mcp_ipc_engine.bridge_server = self.scene_bridge
        self.controller._vlm_agent = self.vlm_agent
        self.controller._scratchpad_ring = self.scratchpad

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        """Content-dependent UTF-8 byte estimate; actual usage must come from the caller."""
        return max(1, (len(text.encode("utf-8")) + 3) // 4)

    def build_llm_observation_bundle(
        self,
        meshes: Optional[List[MeshEntity3D]] = None,
        task_instruction: str = "Align the focal part flush with the reference base without collision.",
        enable_human_eye_plugin: bool = True,
        yaw_symmetry_order: int = 2,
    ) -> Dict[str, Any]:
        """
        构建发往大语言模型（LLM/VLM）的多模态观测载荷：
        - 当 `enable_human_eye_plugin=True`（插件开启组）：输出 768x768 四宫格认知画布 + 256-Token 极简接地提示词 + SoM 锚点表；
        - 当 `enable_human_eye_plugin=False`（裸大模型基线对照组）：仅输出单张普通全局透视图（Q3）与原始顶点/包围盒 JSON 描述。
        """
        active_meshes = self.meshes if meshes is None else meshes
        yaw_symmetry_order = SE3AlignmentMath.resolve_yaw_symmetry_order(yaw_symmetry_order=yaw_symmetry_order)
        eye = self.vlm_agent.default_cam_eye
        target = self.vlm_agent.default_cam_target

        quad_canvas, tele = self.vlm_agent.compositor.render_quad_cognitive_canvas(
            meshes=active_meshes, cam_eye=eye, cam_target=target, fov_y_deg=self.vlm_agent.fov_y_deg,
            yaw_symmetry_order=yaw_symmetry_order,
        )

        if enable_human_eye_plugin:
            prompt_bundle = self.vlm_agent.compile_256_token_quad_grounding_prompt(
                meshes=active_meshes, telemetry=tele, cam_eye=eye, cam_target=target, task_instruction=task_instruction,
                yaw_symmetry_order=yaw_symmetry_order,
            )
            mm_payload = self.vlm_agent.encode_quad_canvas_zero_copy_multimodal_blocks(quad_canvas, prompt_bundle)
            som_table = self.vlm_agent.build_som_pixel_anchor_lookup_table(
                active_meshes, cam_eye=eye, cam_target=target, yaw_symmetry_order=yaw_symmetry_order)
            anchors = {k: dataclasses.asdict(v) for k, v in som_table.items()}
            text_tokens = self._estimate_text_tokens(
                prompt_bundle.system_prompt + "\n" + prompt_bundle.user_prompt_markdown
                + "\n" + json.dumps(anchors, ensure_ascii=False, separators=(",", ":"))
            )
            return {
                "mode": "HUMAN_EYE_PLUGIN_ENABLED",
                "canvas_image": quad_canvas,
                "prompt_bundle": prompt_bundle,
                "multimodal_payload": mm_payload,
                "som_anchor_table": anchors,
                "mcp_image_content": dict(mm_payload.mcp_image_content),
                "estimated_text_tokens": text_tokens,
                "estimated_visual_tokens": 256,
                "token_count_basis": "estimated_observation",
                "total_tokens": 256 + text_tokens,
            }

        # Baseline Control Group: 仅截取左下角 Q3 普通全局透视图，不含正交投影与中央凹子视锥体放大，也不含解析 SE(3) 探针
        Q = self.quad_size
        q3_only_img = quad_canvas.crop((0, Q, Q, Q * 2)).resize((Q * 2, Q * 2), resample=Image.Resampling.BILINEAR)
        raw_scene_desc = [
            {
                "object_id": m.object_id,
                "mark_label": m.mark_label,
                "name": m.name,
                "is_focal_target": m.is_focal_target,
                "bbox_min": [round(float(x), 4) for x in m.bbox_min],
                "bbox_max": [round(float(x), 4) for x in m.bbox_max],
                "vertices_sample": m.vertices.round(4).tolist(),
            }
            for m in active_meshes
        ]
        baseline_md = (
            f"[Task] {task_instruction}\n"
            f"[Raw Scene JSON] {json.dumps(raw_scene_desc)}\n"
            "Output a JSON tool call to `apply_se3_prescription_and_recheck` with `rotation_euler_deg_xyz` and `translation_xyz_m`."
        )
        buf = io.BytesIO()
        q3_only_img.save(buf, format="PNG", compress_level=1)
        b64_q3 = base64.b64encode(buf.getvalue()).decode("ascii")
        text_tokens = self._estimate_text_tokens(baseline_md)
        return {
            "mode": "BASELINE_RAW_VLM_NO_PLUGIN",
            "canvas_image": q3_only_img,
            "user_prompt_markdown": baseline_md,
            "base64_png_str": b64_q3,
            "mcp_image_content": {"type": "image", "data": b64_q3, "mimeType": "image/png"},
            "som_anchor_table": {},
            "estimated_text_tokens": text_tokens,
            "estimated_visual_tokens": 256,
            "token_count_basis": "estimated_observation",
            "total_tokens": 256 + text_tokens,
        }

    def dispatch_tool_call(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """统一分发并执行来自大模型或 MCP 客户端的 6 大空间智能工具调用"""
        args = arguments or {}
        yaw_order = SE3AlignmentMath.resolve_yaw_symmetry_order(yaw_symmetry_order=args.get("yaw_symmetry_order", 2))
        f_mark = str(args.get("focal_mark", "#B"))
        r_mark = str(args.get("reference_mark", "#A"))
        focal_mesh = next((m for m in self.meshes if m.mark_label == f_mark), next((m for m in self.meshes if m.is_focal_target), self.meshes[0]))
        ref_mesh = next((m for m in self.meshes if m.mark_label == r_mark and m.object_id != focal_mesh.object_id), next((m for m in self.meshes if m.object_id != focal_mesh.object_id), self.meshes[0]))

        if tool_name == "human_eye_inspect_scene_quad_canvas":
            enable_plg = bool(args.get("enable_human_eye_plugin", True))
            obs = self.build_llm_observation_bundle(
                meshes=self.meshes,
                task_instruction=str(args.get("task_instruction", "Align the focal part flush with the reference base.")),
                enable_human_eye_plugin=enable_plg,
                yaw_symmetry_order=yaw_order,
            )
            canonical = dict(obs["prompt_bundle"].canonical_mcp_tool_call) if enable_plg else None
            if canonical is not None:
                canonical["tool"] = "human_eye_apply_se3_closed_loop"
            return {
                "tool": tool_name,
                "mode": obs["mode"],
                "total_tokens": obs["total_tokens"],
                "prompt_markdown": obs["prompt_bundle"].user_prompt_markdown if enable_plg else obs["user_prompt_markdown"],
                "canonical_mcp_tool_call": canonical,
                "som_anchor_table": obs["som_anchor_table"],
                "mcp_image_content": obs["mcp_image_content"],
                "token_count_basis": obs["token_count_basis"],
                "estimated_text_tokens": obs["estimated_text_tokens"],
                "estimated_visual_tokens": obs["estimated_visual_tokens"],
            }

        if tool_name == "human_eye_probe_spatial_clearance":
            probe = SpatialAnomalySniffer.probe_closest_clearance(focal_mesh, ref_mesh, yaw_symmetry_order=yaw_order)
            res: Dict[str, Any] = {
                "pair": f"{probe.mark_a} <-> {probe.mark_b}",
                "alignment_state": probe.alignment_state,
                "signed_clearance_mm": round(probe.signed_clearance_m * 1000.0, 3),
                "contact_normal_angle_deg": probe.contact_normal_angle_deg,
                "tangent_yaw_mismatch_deg": probe.tangent_yaw_mismatch_deg,
                "rotation_euler_deg_xyz": list(probe.rotation_euler_deg_xyz),
                "rotation_quaternion_wxyz": list(probe.rotation_quaternion_wxyz),
                "translation_xyz_m": list(probe.axis_delta_m),
                "yaw_symmetry_order": yaw_order,
                "measurement_valid": probe.measurement_valid,
                "measurement_method": probe.measurement_method,
                "axes_valid": probe.axes_valid,
                "axes_check": probe.axes_check,
            }
            if args.get("enable_multi_locus_ior", False):
                v_mat = SubFrustumMathEngine.build_look_at_view_matrix(
                    self.vlm_agent.default_cam_eye, self.vlm_agent.default_cam_target
                )
                p_mat = SubFrustumMathEngine.build_perspective_matrix(
                    self.vlm_agent.fov_y_deg, 1.0, 0.1, 25.0
                )
                loci = SphericalIoRMultiLocusSniffer.extract_multilocus_ior(
                    focal_mesh, ref_mesh, v_mat, p_mat, self.meshes, num_loci_k=3
                )
                res["multi_locus_contacts_count"] = len(loci)
            return res

        if tool_name == "human_eye_sync_low_token_scene_delta":
            return self.scene_bridge.dispatch_mcp_tool_call(
                "mcp_scene_observe_delta",
                {"focal_mark": focal_mesh.mark_label, "full_sync": bool(args.get("full_sync", False))},
            )

        if tool_name in ("human_eye_apply_se3_closed_loop", "apply_se3_prescription_and_recheck"):
            aligned_m, rc_rep, fsm_rep = self.controller.apply_se3_prescription_and_recheck(
                focal_mesh=focal_mesh,
                reference_mesh=ref_mesh,
                mcp_arguments=args,
                scene_meshes=self.meshes,
                enable_ecbf_shield=bool(args.get("enable_ecbf_shield", True)),
            )
            self.meshes[:] = [aligned_m if m.object_id == focal_mesh.object_id else m for m in self.meshes]
            return self.controller.build_mcp_closed_loop_response_package(
                rc_rep, fsm_rep, self.controller._last_ecbf_report,
                detail_level=str(args.get("detail_level", "compact")),
            )

        if tool_name == "human_eye_unproject_2d_click_to_3d":
            resolved = self.vlm_agent.resolve_2d_pixel_click_to_3d_se3_prescription(
                focal_click_or_box=args.get("focal_click_or_box", [560, 560]),
                reference_click_or_box=args.get("reference_click_or_box"),
                meshes=self.meshes,
                coord_convention=str(args.get("coord_convention", "PIXEL_UV")),
                yaw_symmetry_order=yaw_order,
            )
            resolved["mcp_tool_call"]["tool"] = "human_eye_apply_se3_closed_loop"
            return resolved

        if tool_name == "human_eye_issue_digital_twin_certificate":
            _, _, cert_pkg = self.controller.issue_mcp_closed_loop_audit_certificate(focal_mesh, ref_mesh)
            return cert_pkg

        raise ValueError(f"Unknown Human-Eye tool: {tool_name}")

    def evaluate_llm_response_ab_comparison(
        self,
        raw_llm_response_baseline: Union[str, Dict[str, Any]],
        raw_llm_response_plugin: Optional[Union[str, Dict[str, Any]]] = None,
        meshes: Optional[List[MeshEntity3D]] = None,
        scenario_name: str = "S01_Horizontal_Table",
        *,
        baseline_token_usage: Optional[int] = None,
        plugin_token_usage: Optional[int] = None,
        yaw_symmetry_order: int = 2,
    ) -> LLMABComparisonResult:
        """
        面向后续大模型接入的 A/B 效果对比评测器：
        - 对照组（Baseline）：不启用 Human-Eye 物理幻觉防火墙与 ECBF 护栏，直接执行大模型原始预测的 SE(3) 参数；
        - 实验组：解析与几何审计后，实际通过子模块 3.3 ECBF 护栏和闭环复检。
        - 缺省用量仅为观测内容估算；可同时传入两组实际调用的 Token 总量。
        - 未传实验组响应时明确标记 analytical_reference，仅验证解析几何参考路径。
        """
        if (baseline_token_usage is None) != (plugin_token_usage is None):
            raise ValueError("Provide both baseline_token_usage and plugin_token_usage, or neither.")
        if baseline_token_usage is not None:
            if (type(baseline_token_usage) is not int or baseline_token_usage <= 0
                    or type(plugin_token_usage) is not int or plugin_token_usage < 0):
                raise ValueError("Token usage must be integers: baseline > 0 and plugin >= 0.")
        sc_meshes = list(self.meshes if meshes is None else meshes)
        yaw_symmetry_order = SE3AlignmentMath.resolve_yaw_symmetry_order(yaw_symmetry_order=yaw_symmetry_order)
        baseline_obs = self.build_llm_observation_bundle(meshes=sc_meshes, enable_human_eye_plugin=False,
                                                       yaw_symmetry_order=yaw_symmetry_order)
        plugin_obs = self.build_llm_observation_bundle(meshes=sc_meshes, enable_human_eye_plugin=True,
                                                     yaw_symmetry_order=yaw_symmetry_order)
        focal_mesh = next((m for m in sc_meshes if m.is_focal_target), sc_meshes[0])
        ref_mesh = next((m for m in sc_meshes if m.object_id != focal_mesh.object_id), sc_meshes[0])

        # 1. 评估 Baseline（无幻觉防火墙覆写，直接执行大模型原始旋转与平移）
        parsed_base = self.vlm_agent.parse_vlm_response_to_mcp_tool_call(raw_llm_response_baseline)
        b_args = parsed_base.arguments
        b_euler = b_args.get("rotation_euler_deg_xyz")
        b_trans = b_args.get("translation_xyz_m", [0.0, 0.0, 0.0])
        if b_euler is not None:
            r_b = SE3AlignmentMath.euler_xyz_to_matrix(float(b_euler[0]), float(b_euler[1]), float(b_euler[2]))
        else:
            ok, message, r_b, _, _, _ = McpProtocolEngine.validate_and_project_se3_prescription(
                quat_wxyz=b_args.get("rotation_quaternion_wxyz", [1.0, 0.0, 0.0, 0.0]),
                translation_xyz=b_trans,
            )
            if not ok:
                raise ValueError(message)
        t_b = (float(b_trans[0]), float(b_trans[1]), float(b_trans[2]))  # type: ignore
        base_aligned = focal_mesh.rotated_around_pivot(r_b).translated(t_b)
        base_post_probe = SpatialAnomalySniffer.probe_closest_clearance(base_aligned, ref_mesh,
                                                                     yaw_symmetry_order=yaw_symmetry_order)
        base_res_mm = round(abs(base_post_probe.signed_clearance_m) * 1000.0, 3)
        base_tilt_deg = base_post_probe.contact_normal_angle_deg
        base_yaw_deg = base_post_probe.tangent_yaw_mismatch_deg
        base_ok = bool(_probe_is_trustworthy(base_post_probe) and base_post_probe.is_aligned_flush
                       and not base_post_probe.is_penetrating and base_tilt_deg <= 1.0 and base_yaw_deg <= 1.0)

        # Use a fresh controller so evaluation cannot affect the live servo FSM.
        evaluation_mode = "analytical_reference" if raw_llm_response_plugin is None else "provided_responses"
        raw_plugin = (plugin_obs["prompt_bundle"].canonical_mcp_tool_call
                      if raw_llm_response_plugin is None else raw_llm_response_plugin)
        t0 = time.perf_counter()
        parsed_plugin = self.vlm_agent.parse_vlm_response_to_mcp_tool_call(raw_plugin)
        fused_call, audit_rep = self.vlm_agent.fuse_vlm_semantic_intent_with_analytical_se3(
            parsed_plugin, sc_meshes, yaw_symmetry_order=yaw_symmetry_order
        )
        action_args = fused_call["arguments"]
        plugin_focal = next(m for m in sc_meshes if m.mark_label == action_args["focal_mark"])
        plugin_ref = next(m for m in sc_meshes if m.mark_label == action_args["reference_mark"])
        controller = ClosedLoopActionController(
            quad_size=self.quad_size, enable_zero_copy_ipc=self.controller.enable_zero_copy_ipc
        )
        _, rc_plg, _ = controller.apply_se3_prescription_and_recheck(
            focal_mesh=plugin_focal, reference_mesh=plugin_ref,
            mcp_arguments=action_args, scene_meshes=sc_meshes, enable_ecbf_shield=True,
        )
        shield = controller._last_ecbf_report
        shield_activated = bool(shield is not None and (shield.barrier_activated or shield.jamming_shield_activated))
        plg_tokens = plugin_obs["total_tokens"] if plugin_token_usage is None else plugin_token_usage
        base_tokens = baseline_obs["total_tokens"] if baseline_token_usage is None else baseline_token_usage
        token_basis = "estimated_observation" if baseline_token_usage is None else "caller_reported_usage"
        saving_pct = round((1.0 - plg_tokens / base_tokens) * 100.0, 2)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        msg = (
            f"[{scenario_name}] Baseline: Gap={base_res_mm:.2f}mm, Tilt={base_tilt_deg:.2f}deg (Passed={base_ok}) "
            f"vs. Human-Eye Plugin: Gap={rc_plg.residual_error_mm:.2f}mm, Tilt={rc_plg.residual_angle_deg:.2f}deg "
            f"(Passed={rc_plg.verification_passed}, HallucinationIntercepted={audit_rep.hallucination_detected}, "
            f"TokenSaving={saving_pct}%, TokenBasis={token_basis}, EvaluationMode={evaluation_mode})"
        )
        return LLMABComparisonResult(
            scenario_name=scenario_name,
            baseline_residual_clearance_mm=base_res_mm,
            plugin_residual_clearance_mm=rc_plg.residual_error_mm,
            baseline_residual_tilt_deg=base_tilt_deg,
            plugin_residual_tilt_deg=rc_plg.residual_angle_deg,
            baseline_residual_yaw_deg=base_yaw_deg,
            plugin_residual_yaw_deg=rc_plg.residual_yaw_deg,
            baseline_passed=base_ok,
            plugin_passed=rc_plg.verification_passed,
            plugin_hallucination_intercepted=audit_rep.hallucination_detected,
            plugin_ecbf_shield_activated=shield_activated,
            plugin_total_tokens=plg_tokens,
            baseline_estimated_scene_json_tokens=baseline_obs["total_tokens"],
            token_saving_ratio_pct=saving_pct,
            plugin_execution_time_ms=elapsed_ms,
            summary_message=msg,
            baseline_total_tokens=base_tokens,
            token_count_basis=token_basis,
            evaluation_mode=evaluation_mode,
        )
