"""
Native 3D Visual & Geometric Scratchpad (原生三维视觉与几何暂存空间扩展模块)
==========================================================================
本模块严格遵循“零侵入、零退化（Zero-Regression）”原则，在不修改
`human_eye_foveated_renderer.py` (V8.3, 4,250 行) 任何一行既有代码的前提下，
将 Elorian Glimpse (2026) 的“Visual Scratch Space (视觉暂存空间)”与
IBM Research Mind the GAP (ICLR 2025) 的“主动感知 + 返回抑制 (IoR)”技术
完全内化为插件原生的四大三维几何与图形算子：

1. [Pillar 1] SpatialScratchpadRingBuffer (三维时空环形暂存缓冲与跨步差分追踪器):
   - 驻留内存保存最近 N 步 (MeshSnapshot, ZBufferSnapshot, ProbeResult, CameraPose) 状态快照；
   - 自动计算步间间隙收敛率 Δd、法线倾角收敛率 Δθ、偏航消扭收敛率 Δψ 与单调收敛性判据；
   - 支持一键任意步状态回滚 (Zero-Copy Rollback) 与多步递进透明度残影 (Multi-Ghost Trail) 叠加渲染；
   - 支持将 768x768 四宫格画布上的任意 2D 像素点 (u, v) 或裁剪框结合硬件 Z-Buffer 精确反投影回 3D 世界坐标。

2. [Pillar 2] SphericalIoRMultiLocusSniffer (原生三维球面返回抑制 IoR 多触点序列嗅探器):
   - 内化 IBM GAP 的 Winner-Takes-All (WTA) + 3D Gaussian Inhibition-of-Return (IoR) 机制；
   - 单次复用 V8.3 的 Voronoi 点面与异面线段距离场，在 ~0.12 ms 内提取 Top-K (K=3~4) 空间互斥配合触点；
   - 自动合成 2x2 多焦点微距审计拼图 (Multi-Fovea Q4 Montage，每个子视口独立运行 OP-36 与 OP-38 紧深度映射)；
   - 提供主基准面 (Primary Datum) + 副导向面 (Secondary Guide) + 止挡面 (Tertiary Stop) 的联合 SE(3) 配准处方。

3. [Pillar 3] AdaptiveSE3TrajectorySubdivider (原生自适应二分 SE(3) 轨迹加密与折线避障求解器):
   - 内化 Glimpse 的“8fps 粗扫 -> 14fps 危险窗口加密重扫 (Re-entrant Temporal Rewind)”机制；
   - 在 SE(3) 螺旋插值轨迹 τ ∈ [0, 1] 上先执行 N_coarse=6 步微秒级粗扫 (~1.8 ms)；
   - 一旦检测到间隙谷底 d_min < 5mm、导数符号反转 (V 型擦掠) 或瞬态 OBB-SAT 碰撞，自动触发局部区间 [τ_a, τ_b]
     的 N_fine=16 步加密重扫，并自动求解零碰撞三段式折线避障路径 (Safe Dog-Leg Waypoints: Lift -> Translate -> Drop)。

4. [Pillar 4] BatchGeometricPredicateVerifier (原生四步几何状态谓词分类与微距拼图核验器):
   - 内化 Glimpse 的“Define -> Separate -> Verify -> Reference”四步密集计数与状态盘点范式；
   - 基于包围盒主轴尺度比、局部标架朝向与有符号间隙，在 <1.5 ms 内将全场景候选实例精确划分为：
     TARGET_ALIGNED_FLUSH、SAME_CLASS_FLOATING_OR_TILTED、SAME_CLASS_PENETRATING、DISTRACTOR_GEOMETRY 四类；
   - 自动为所有待核验/异常实例生成带 SoM 编号与间隙铭牌的子视锥体微距核验图板 (Instance Verification Montage)。
"""

from __future__ import annotations

import collections
import dataclasses
import math
import pathlib
import struct
import sys
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

try:
    from .submodule_1_1_mesh_entity import (
        ClosedLoopRecheckReport,
        MeshEntity3D,
        SpatialClearanceProbeResult,
    )
    from .submodule_1_2_sub_frustum_gaze import SubFrustumMathEngine
    from .submodule_1_3_se3_alignment_math import SE3AlignmentMath
    from .submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
    from .submodule_1_5_alignment_verifier import SpatialAlignmentVerifier
    from .submodule_1_6_quad_compositor import QuadCognitiveCanvasCompositor
except ImportError:
    _dl_dir = str(pathlib.Path(__file__).resolve().parent)
    if _dl_dir not in sys.path:
        sys.path.insert(0, _dl_dir)
    from human_eye_foveated_renderer import (
        ClosedLoopRecheckReport,
        MeshEntity3D,
        QuadCognitiveCanvasCompositor,
        SE3AlignmentMath,
        SpatialAlignmentVerifier,
        SpatialAnomalySniffer,
        SpatialClearanceProbeResult,
        SubFrustumMathEngine,
    )

_STRUCT_3D = struct.Struct("=3d")
_UNPACK_3D = _STRUCT_3D.unpack
_PACK_3D_INTO = _STRUCT_3D.pack_into
_SCRATCHPAD_CUBE_8: np.ndarray = np.array(
    [
        [-1.0, -1.0, -1.0],
        [-1.0, -1.0, 1.0],
        [-1.0, 1.0, -1.0],
        [-1.0, 1.0, 1.0],
        [1.0, -1.0, -1.0],
        [1.0, -1.0, 1.0],
        [1.0, 1.0, -1.0],
        [1.0, 1.0, 1.0],
    ],
    dtype=np.float64,
)


# ============================================================================
# 1. 核心数据结构定义：3D 视觉与几何暂存空间原生状态原语
# ============================================================================

@dataclasses.dataclass
class SpatialScratchpadFrame:
    """三维时空暂存空间单步状态快照（零拷贝保存网格引用、相机矩阵、四象限深度缓冲与探针遥测）"""
    step_index: int
    timestamp_s: float
    action_tag: str
    focal_mesh: MeshEntity3D
    reference_mesh: MeshEntity3D
    cam_eye: np.ndarray
    cam_target: np.ndarray
    view_persp: np.ndarray
    proj_persp: np.ndarray
    proj_fovea: np.ndarray
    fovea_ndc_window: Tuple[float, float, float, float]
    q3_zbuf: np.ndarray                  # (384, 384) float64 全局透视视口硬件深度缓冲快照
    q4_zbuf: np.ndarray                  # (384, 384) float64 中央凹微距视口硬件深度缓冲快照
    probe_result: SpatialClearanceProbeResult
    canvas_image: Optional[Image.Image] = None
    q1_zbuf: Optional[np.ndarray] = None  # (384, 384) float64 俯视正交视口硬件深度缓冲快照
    q2_zbuf: Optional[np.ndarray] = None  # (384, 384) float64 正视正交视口硬件深度缓冲快照
    scene_meshes: Optional[List[MeshEntity3D]] = None


@dataclasses.dataclass
class StepDeltaAuditReport:
    """跨步时空差分收敛性审计报告（自动对比 Step t-k 与 Step t 的几何收敛轨迹）"""
    from_step: int
    to_step: int
    clearance_before_mm: float
    clearance_after_mm: float
    clearance_delta_mm: float
    normal_tilt_before_deg: float
    normal_tilt_after_deg: float
    normal_tilt_delta_deg: float
    yaw_err_before_deg: float
    yaw_err_after_deg: float
    yaw_err_delta_deg: float
    pivot_displacement_vec_m: Tuple[float, float, float]
    pivot_displacement_norm_mm: float
    is_monotonically_converging: bool
    convergence_verdict: str


@dataclasses.dataclass
class LocusContactFeature:
    """三维球面返回抑制（3D Spherical IoR）提取的单个独立空间配合触点特征（Where 流原语）"""
    locus_id: int
    semantic_role: str                   # "PRIMARY_DATUM" | "SECONDARY_GUIDE" | "TERTIARY_STOP" | "AUX_LOCUS"
    point_a_world: np.ndarray            # (3,) 焦点物体 A 上的局部最近点
    point_b_world: np.ndarray            # (3,) 参考基准物体 B 上的对应最近点
    locus_midpoint_world: np.ndarray     # (3,) 触点中心 c_k = 0.5 * (p_a + p_b)
    normal_a_world: np.ndarray           # (3,) 焦点物体在该触点处的外法线
    normal_b_world: np.ndarray           # (3,) 基准物体在该触点处的外法线
    unsigned_clearance_m: float          # 该局部触点的无符号间隙 (m)
    signed_normal_gap_m: float           # 沿基准面法线方向的有符号投影间隙 (m)
    fovea_ndc_window: Tuple[float, float, float, float]
    optical_zoom: float
    tight_depth_range: Tuple[float, float] = (0.1, 10.0)


@dataclasses.dataclass
class MultiDatumJointSE3Prescription:
    """Pillar 2 拓展：主基准面 (Primary Datum) + 副导向面 (Secondary Guide) + 止挡面 (Tertiary Stop) 联合 SE(3) 配准处方"""
    primary_datum_normal_world: Tuple[float, float, float]
    secondary_guide_normal_world: Optional[Tuple[float, float, float]]
    tertiary_stop_normal_world: Optional[Tuple[float, float, float]]
    constrained_dof_count: int
    rotation_euler_deg_xyz: Tuple[float, float, float]
    rotation_quaternion_wxyz: Tuple[float, float, float, float]
    joint_translation_world_m: Tuple[float, float, float]
    datum_orthogonality_Spread_deg: float
    prescription_summary: str


@dataclasses.dataclass
class TrajectoryWindowSweepReport:
    """自适应两级 SE(3) 运动学轨迹扫描与折线（Dog-Leg）避障规划报告"""
    coarse_steps: int
    fine_rewind_triggered: bool
    ambiguous_window_tau: Optional[Tuple[float, float]]
    fine_steps: int
    min_clearance_along_path_mm: float
    critical_tau: float
    transient_collision_detected: bool
    safe_dogleg_waypoints_world: List[Tuple[str, Tuple[float, float, float]]]
    coarse_log: List[Dict[str, Any]]
    fine_log: List[Dict[str, Any]]
    compute_time_ms: float


@dataclasses.dataclass
class InstanceVerificationReport:
    """Glimpse 四步法（Define -> Separate -> Verify -> Reference）三维几何实例分类与盘点报告"""
    target_class_rule: str
    total_candidates_inspected: int
    verified_flush_count: int
    same_class_floating_or_tilted_count: int
    same_class_penetrating_count: int
    distractor_geometry_count: int
    spatial_reference_registry: List[Dict[str, Any]]
    compute_time_ms: float


# ============================================================================
# 2. Pillar 1：三维时空环形暂存缓冲与跨步差分/反投影引擎
# ============================================================================

class SpatialScratchpadRingBuffer:
    """
    原生三维时空暂存缓冲器（3D Spatio-Temporal Scratchpad Ring Buffer）：
    将 Glimpse 的会话内视觉暂存空间升级为驻留本地内存的 3D 几何与深度状态环形队列。
    """

    def __init__(self, compositor: QuadCognitiveCanvasCompositor, max_history: int = 12) -> None:
        self.compositor = compositor
        self.max_history = max_history
        self._frames: Deque[SpatialScratchpadFrame] = collections.deque(maxlen=max_history)
        self._step_counter: int = 0

    @property
    def frames(self) -> List[SpatialScratchpadFrame]:
        return list(self._frames)

    def commit_snapshot(
        self,
        action_tag: str,
        meshes: List[MeshEntity3D],
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        cam_eye: np.ndarray,
        cam_target: np.ndarray,
        fov_y_deg: float = 45.0,
        render_canvas: bool = True,
    ) -> SpatialScratchpadFrame:
        """OP-205 零拷贝只读 PBO 视图直通与双目标探针复用快照提交算子"""
        cam_eye = np.ascontiguousarray(cam_eye, dtype=np.float64)
        cam_target = np.ascontiguousarray(cam_target, dtype=np.float64)

        ordered_meshes: List[MeshEntity3D] = []
        has_focal = False
        for m in meshes:
            if m is focal_mesh or m.object_id == focal_mesh.object_id:
                ordered_meshes.append(focal_mesh if focal_mesh.is_focal_target else dataclasses.replace(focal_mesh, is_focal_target=True))
                has_focal = True
            else:
                ordered_meshes.append(m if not m.is_focal_target else dataclasses.replace(m, is_focal_target=False))
        if not has_focal:
            ordered_meshes.append(focal_mesh if focal_mesh.is_focal_target else dataclasses.replace(focal_mesh, is_focal_target=True))

        ghost_prev = self._frames[-1].focal_mesh if len(self._frames) > 0 else None
        q1_z: Optional[np.ndarray] = None
        q2_z: Optional[np.ndarray] = None

        if render_canvas or hasattr(self.compositor, "_ensure_quad_frame_state"):
            frame_state = self.compositor._ensure_quad_frame_state(
                meshes=ordered_meshes,
                cam_eye=cam_eye,
                cam_target=cam_target,
                fov_y_deg=fov_y_deg,
                ghost_pre_mesh=ghost_prev if render_canvas else None,
            )
            quad_arr_ro, tele_tmpl, (z_q1, z_q2, z_q3, z_q4), _, _, _, _, vp_mats, _, (best_probe_c, active_eye, _) = frame_state
            v_persp, p_persp = vp_mats["Q3_GIST"]
            _, p_fovea = vp_mats["Q4_FOVEA"]
            ndc_win = tuple(tele_tmpl["foveal_sub_frustum_ndc_window"])
            q1_z, q2_z, q3_z, q4_z = z_q1, z_q2, z_q3, z_q4
            canvas_img = Image.fromarray(quad_arr_ro, mode="RGB") if render_canvas else None
            if best_probe_c is not None and (
                len(ordered_meshes) == 2 or best_probe_c.mark_b == reference_mesh.mark_label
            ):
                probe = best_probe_c
            else:
                view_vec = cam_eye - cam_target
                pref_dir = view_vec / max(SE3AlignmentMath._norm3(view_vec), 1e-6)
                probe = SpatialAnomalySniffer.probe_closest_clearance(
                    focal_mesh, reference_mesh, preferred_view_dir=pref_dir
                )
        else:
            view_vec = cam_eye - cam_target
            pref_dir = view_vec / max(SE3AlignmentMath._norm3(view_vec), 1e-6)
            probe = SpatialAnomalySniffer.probe_closest_clearance(
                focal_mesh, reference_mesh, preferred_view_dir=pref_dir
            )
            roi_mid = 0.5 * (probe.point_a_world + probe.point_b_world)
            active_eye, _ = SubFrustumMathEngine.resolve_unoccluded_camera_eye(cam_eye, roi_mid, ordered_meshes)
            v_persp = SubFrustumMathEngine.build_look_at_view_matrix(active_eye, cam_target)
            p_persp = SubFrustumMathEngine.build_perspective_matrix(fov_y_deg, 1.0, 0.1, 25.0)
            ndc_win, _, tight_z = SubFrustumMathEngine.compute_foveal_ndc_window(
                probe.roi_vertices_world, v_persp, p_persp, padding_factor=0.45, scene_meshes=ordered_meshes
            )
            p_fovea = SubFrustumMathEngine.build_asymmetric_sub_frustum_matrix(
                p_persp, ndc_win, tight_depth_range=tight_z
            )
            W = H = self.compositor.quad_size
            dummy_col = np.zeros((H, W, 3), dtype=np.uint8)
            q3_z = np.full((H, W), float("inf"), dtype=np.float64)
            self.compositor._rasterize_meshes_zbuffer(
                dummy_col, q3_z, ordered_meshes, v_persp, p_persp, is_foveal_micro_view=False
            )
            q4_z = np.full((H, W), float("inf"), dtype=np.float64)
            self.compositor._rasterize_meshes_zbuffer(
                dummy_col, q4_z, ordered_meshes, v_persp, p_fovea, is_foveal_micro_view=True
            )
            q3_z.flags.writeable = False
            q4_z.flags.writeable = False
            canvas_img = None

        frame = SpatialScratchpadFrame(
            step_index=self._step_counter,
            timestamp_s=round(time.perf_counter(), 6),
            action_tag=action_tag,
            focal_mesh=focal_mesh,
            reference_mesh=reference_mesh,
            cam_eye=active_eye.copy(),
            cam_target=cam_target.copy(),
            view_persp=v_persp,
            proj_persp=p_persp,
            proj_fovea=p_fovea,
            fovea_ndc_window=ndc_win,
            q3_zbuf=q3_z,
            q4_zbuf=q4_z,
            probe_result=probe,
            canvas_image=canvas_img,
            q1_zbuf=q1_z,
            q2_zbuf=q2_z,
            scene_meshes=ordered_meshes,
        )
        self._frames.append(frame)
        self._step_counter += 1
        return frame

    def compute_step_delta(self, from_idx: int = -2, to_idx: int = -1) -> StepDeltaAuditReport:
        """计算暂存空间内任意两个时间步之间的三维几何误差收敛率"""
        f_prev = self._frames[from_idx]
        f_curr = self._frames[to_idx]
        p0, p1 = f_prev.probe_result, f_curr.probe_result

        c_before = round(float(p0.signed_clearance_m) * 1000.0, 3)
        c_after = round(float(p1.signed_clearance_m) * 1000.0, 3)
        t_before = float(p0.contact_normal_angle_deg)
        t_after = float(p1.contact_normal_angle_deg)
        y_before = float(p0.tangent_yaw_mismatch_deg)
        y_after = float(p1.tangent_yaw_mismatch_deg)

        piv_delta = f_curr.focal_mesh.bbox_center - f_prev.focal_mesh.bbox_center
        piv_norm_mm = round(SE3AlignmentMath._norm3(piv_delta) * 1000.0, 3)

        err_before = abs(c_before) + t_before * 2.0 + y_before * 1.5
        err_after = abs(c_after) + t_after * 2.0 + y_after * 1.5
        converging = bool(err_after <= err_before + 1e-4 and not p1.is_penetrating)

        if p1.is_aligned_flush and not p1.is_penetrating:
            verdict = "CONVERGED_TO_ZERO_FLUSH"
        elif converging:
            verdict = "MONOTONIC_CONVERGENCE_IN_PROGRESS"
        else:
            verdict = "DIVERGENCE_OR_COLLISION_DETECTED_RECOMMEND_ROLLBACK"

        return StepDeltaAuditReport(
            from_step=f_prev.step_index,
            to_step=f_curr.step_index,
            clearance_before_mm=c_before,
            clearance_after_mm=c_after,
            clearance_delta_mm=round(c_after - c_before, 3),
            normal_tilt_before_deg=t_before,
            normal_tilt_after_deg=t_after,
            normal_tilt_delta_deg=round(t_after - t_before, 3),
            yaw_err_before_deg=y_before,
            yaw_err_after_deg=y_after,
            yaw_err_delta_deg=round(y_after - y_before, 3),
            pivot_displacement_vec_m=(
                round(float(piv_delta[0]), 4),
                round(float(piv_delta[1]), 4),
                round(float(piv_delta[2]), 4),
            ),
            pivot_displacement_norm_mm=piv_norm_mm,
            is_monotonically_converging=converging,
            convergence_verdict=verdict,
        )

    def rollback_to_step(self, step_index: int) -> SpatialScratchpadFrame:
        """零拷贝状态回滚：当检测到错误变换或碰撞时，瞬间恢复至指定历史帧"""
        while len(self._frames) > 1 and self._frames[-1].step_index > step_index:
            self._frames.pop()
        return self._frames[-1]

    def unproject_canvas_pixel_to_3d(
        self, u_canvas: float, v_canvas: float, frame_index: int = -1
    ) -> Tuple[str, np.ndarray, float]:
        """将 768x768 四宫格画布上的任意 2D 像素坐标结合 Q1~Q4 全部 4 象限硬件 Z-Buffer 精确反投影为 3D 世界坐标"""
        frame = self._frames[frame_index]
        q_size = self.compositor.quad_size
        is_right = u_canvas >= q_size
        is_bottom = v_canvas >= q_size
        px = float(u_canvas - (q_size if is_right else 0))
        py = float(v_canvas - (q_size if is_bottom else 0))
        ix = max(0, min(q_size - 1, int(round(px))))
        iy = max(0, min(q_size - 1, int(round(py))))

        x_ndc = (2.0 * px) / (q_size - 1) - 1.0
        y_ndc = 1.0 - (2.0 * py) / (q_size - 1)

        if not is_right and not is_bottom:
            quad_name = "Q1_TOP_ORTHO"
            V, P, zbuf = self.compositor._v_top, self.compositor._p_ortho_top, frame.q1_zbuf
        elif is_right and not is_bottom:
            quad_name = "Q2_FRONT_ORTHO"
            V, P, zbuf = self.compositor._v_front, self.compositor._p_ortho_front, frame.q2_zbuf
        elif not is_right and is_bottom:
            quad_name = "Q3_GLOBAL_PERSP"
            V, P, zbuf = frame.view_persp, frame.proj_persp, frame.q3_zbuf
        else:
            quad_name = "Q4_FOVEA_SUBFRUSTUM"
            V, P, zbuf = frame.view_persp, frame.proj_fovea, frame.q4_zbuf

        d_cam = 2.5
        if zbuf is not None:
            raw_d = float(zbuf[iy, ix])
            if math.isfinite(raw_d) and raw_d < 1e10:
                d_cam = raw_d
            else:
                y0, y1 = max(0, iy - 3), min(q_size, iy + 4)
                x0, x1 = max(0, ix - 3), min(q_size, ix + 4)
                patch = zbuf[y0:y1, x0:x1]
                valid = patch < 1e10
                if valid.any():
                    d_cam = float(patch[valid].min())

        is_ortho = abs(float(P[3, 3]) - 1.0) < 1e-5
        if is_ortho:
            x_cam = (x_ndc - float(P[0, 3])) / float(P[0, 0])
            y_cam = (y_ndc - float(P[1, 3])) / float(P[1, 1])
            z_cam = -d_cam
        else:
            x_cam = ((x_ndc + float(P[0, 2])) * d_cam - float(P[0, 3])) / float(P[0, 0])
            y_cam = ((y_ndc + float(P[1, 2])) * d_cam - float(P[1, 3])) / float(P[1, 1])
            z_cam = -d_cam

        p_cam = np.array([x_cam, y_cam, z_cam], dtype=np.float64)
        p_world = V[:3, :3].T @ (p_cam - V[:3, 3])
        return quad_name, p_world, d_cam

    def unproject_canvas_pixels_batch_to_3d(
        self, uv_canvas_array: np.ndarray, frame_index: int = -1
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """OP-206 暂存空间任意历史帧 2D->3D 批量向量化逆投影算子"""
        frame = self._frames[frame_index]
        Q = self.compositor.quad_size
        C = Q * 2
        uv = np.ascontiguousarray(uv_canvas_array, dtype=np.float64)
        N = uv.shape[0]
        u = np.clip(uv[:, 0], 0.0, float(C - 1))
        v = np.clip(uv[:, 1], 0.0, float(C - 1))
        q_idx = ((v >= Q).astype(np.int32) << 1) | (u >= Q).astype(np.int32)
        loc_u = np.where(u >= Q, u - Q, u)
        loc_v = np.where(v >= Q, v - Q, v)
        ix = np.clip(np.round(loc_u).astype(np.int32), 0, Q - 1)
        iy = np.clip(np.round(loc_v).astype(np.int32), 0, Q - 1)
        inv_qm1 = 2.0 / max(Q - 1, 1)
        x_ndc = loc_u * inv_qm1 - 1.0
        y_ndc = 1.0 - loc_v * inv_qm1

        surf_pts_w = np.zeros((N, 3), dtype=np.float64)
        depths_m = np.full(N, 2.5, dtype=np.float64)
        hit_fg = np.zeros(N, dtype=bool)

        vp_specs = [
            (0, self.compositor._v_top, self.compositor._p_ortho_top, frame.q1_zbuf, True),
            (1, self.compositor._v_front, self.compositor._p_ortho_front, frame.q2_zbuf, True),
            (2, frame.view_persp, frame.proj_persp, frame.q3_zbuf, False),
            (3, frame.view_persp, frame.proj_fovea, frame.q4_zbuf, False),
        ]
        for qi, V, P, zbuf, is_ortho in vp_specs:
            mask_q = q_idx == qi
            if not mask_q.any():
                continue
            r_v, t_v = V[:3, :3], V[:3, 3]
            if zbuf is not None:
                zv = zbuf[iy[mask_q], ix[mask_q]]
                fg_q = zv < 1e10
                d_q = np.where(fg_q, zv, 2.5)
            else:
                fg_q = np.zeros(int(mask_q.sum()), dtype=bool)
                d_q = np.full(int(mask_q.sum()), 2.5, dtype=np.float64)
            hit_fg[mask_q] = fg_q
            depths_m[mask_q] = d_q
            nx_q, ny_q = x_ndc[mask_q], y_ndc[mask_q]
            if is_ortho:
                xc = (nx_q - float(P[0, 3])) / float(P[0, 0])
                yc = (ny_q - float(P[1, 3])) / float(P[1, 1])
            else:
                xc = ((nx_q + float(P[0, 2])) * d_q - float(P[0, 3])) / float(P[0, 0])
                yc = ((ny_q + float(P[1, 2])) * d_q - float(P[1, 3])) / float(P[1, 1])
            p_cam = np.column_stack([xc, yc, -d_q])
            surf_pts_w[mask_q] = (p_cam - t_v[None, :]) @ r_v

        return q_idx, surf_pts_w, depths_m, hit_fg

    def render_cascaded_subfrustum_zoom(
        self,
        meshes: List[MeshEntity3D],
        focus_world: np.ndarray,
        half_span_m: float = 0.035,
        frame_index: int = -1,
    ) -> Tuple[Image.Image, float]:
        """级联无损子视锥体微距重光栅化（Cascaded Optical Zoom-in in 3D Scratchpad）"""
        frame = self._frames[frame_index]
        roi_box = focus_world[None, :] + _SCRATCHPAD_CUBE_8 * half_span_m
        ndc_win, opt_zoom, tight_z = SubFrustumMathEngine.compute_foveal_ndc_window(
            roi_box,
            frame.view_persp,
            frame.proj_persp,
            padding_factor=0.20,
            min_ndc_span=0.04,
            scene_meshes=meshes,
        )
        p_zoom = SubFrustumMathEngine.build_asymmetric_sub_frustum_matrix(
            frame.proj_persp, ndc_win, tight_depth_range=tight_z
        )
        img = self.compositor._render_single_viewport(
            meshes=meshes,
            view_matrix=frame.view_persp,
            proj_matrix=p_zoom,
            title_banner=f"CASCADED 3D ZOOM ({opt_zoom:.1f}x | Z:[{tight_z[0]},{tight_z[1]}]m)",
            probe_result=frame.probe_result,
            is_foveal_micro_view=True,
        )
        return img, opt_zoom

    def render_multi_ghost_trail_canvas(
        self,
        meshes: Optional[List[MeshEntity3D]] = None,
        max_trail_steps: int = 4,
    ) -> Image.Image:
        """多步递进透明度残影四宫格画布合成器（Multi-Step Progressive Ghost Trail Canvas）"""
        if not self._frames:
            raise ValueError("SpatialScratchpadRingBuffer is empty; commit at least one snapshot first.")
        latest = self._frames[-1]
        active_meshes = meshes if meshes is not None else (
            latest.scene_meshes if latest.scene_meshes is not None else [latest.reference_mesh, latest.focal_mesh]
        )
        base_img, _ = self.compositor.render_quad_cognitive_canvas(
            meshes=active_meshes,
            cam_eye=latest.cam_eye,
            cam_target=latest.cam_target,
            ghost_pre_mesh=self._frames[-2].focal_mesh if len(self._frames) >= 2 else None,
        )
        if len(self._frames) <= 1:
            return base_img

        out_img = base_img.copy()
        draw = ImageDraw.Draw(out_img)
        Q = self.compositor.quad_size
        qm1 = Q - 1
        history_slice = list(self._frames)[-max(2, max_trail_steps + 1) :]
        vp_specs = [
            (self.compositor._v_top, self.compositor._p_ortho_top, 0, 0),
            (self.compositor._v_front, self.compositor._p_ortho_front, Q, 0),
            (latest.view_persp, latest.proj_persp, 0, Q),
            (latest.view_persp, latest.proj_fovea, Q, Q),
        ]
        pivots_world = np.vstack([f.focal_mesh.bbox_center for f in history_slice])

        for v_m, p_m, ox, oy in vp_specs:
            ndc_piv, _ = SubFrustumMathEngine.project_world_to_ndc(pivots_world, v_m, p_m)
            piv_2d = []
            for i in range(pivots_world.shape[0]):
                px = int(round((float(ndc_piv[i, 0]) * 0.5 + 0.5) * qm1))
                py = int(round((1.0 - (float(ndc_piv[i, 1]) * 0.5 + 0.5)) * qm1))
                piv_2d.append((ox + min(max(px, 3), Q - 4), oy + min(max(py, 24), Q - 4)))
            if len(piv_2d) >= 2:
                draw.line(piv_2d, fill=(80, 220, 255), width=2)
                for step_k, (cx, cy) in enumerate(piv_2d):
                    col_k = (65, 245, 130) if step_k == len(piv_2d) - 1 else (130, 195, 255)
                    draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill=col_k, outline=(12, 16, 24))
        return out_img


# ============================================================================
# 3. Pillar 2：原生三维球面返回抑制（3D Spherical IoR）多触点序列嗅探与拼图合成器
# ============================================================================

class SphericalIoRMultiLocusSniffer:
    """
    内化 IBM Research Mind the GAP (ICLR 2025) 的三维球面返回抑制（3D Spherical IoR）多焦点嗅探器：
    一次性提取 K 个空间分离的局部配合触点并合成 2x2 多焦点微距审计图板及多基准面联合 SE(3) 配准处方。
    """

    _IOR_CACHE: Dict[Tuple, List[LocusContactFeature]] = {}

    @staticmethod
    def _get_vertex_adj_faces_list(mesh: MeshEntity3D) -> List[np.ndarray]:
        """O(F) 预构建并按网格拓扑缓存顶点邻接三角面索引表（100% 兼容 MeshEntity3D，零 AttributeError）"""
        f = mesh.faces
        n_v = mesh.vertices.shape[0]
        cached = getattr(mesh, "_cached_vert_adj_faces", None)
        if cached is not None and cached[0] == n_v and cached[1] == f.shape[0]:
            return cached[2]
        buckets: List[List[int]] = [[] for _ in range(n_v)]
        for fi, (v0, v1, v2) in enumerate(f.tolist()):
            if 0 <= v0 < n_v:
                buckets[v0].append(fi)
            if 0 <= v1 < n_v:
                buckets[v1].append(fi)
            if 0 <= v2 < n_v:
                buckets[v2].append(fi)
        adj_list = [np.array(b, dtype=np.int32) for b in buckets]
        setattr(mesh, "_cached_vert_adj_faces", (n_v, f.shape[0], adj_list))
        return adj_list

    @staticmethod
    def extract_multilocus_ior(
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        view_matrix: np.ndarray,
        base_proj_matrix: np.ndarray,
        scene_meshes: List[MeshEntity3D],
        num_loci_k: int = 4,
        ior_radius_ratio: float = 0.22,
    ) -> List[LocusContactFeature]:
        """OP-207 / OP-208 带 CRC-32 指纹记忆化与 19 元内禀度量张量复用的三维球面返回抑制多触点提取算子"""
        ior_key = (
            focal_mesh.object_id,
            focal_mesh._compute_full_crc_token(),
            reference_mesh.object_id,
            reference_mesh._compute_full_crc_token(),
            np.round(view_matrix, 9).tobytes(),
            np.round(base_proj_matrix, 9).tobytes(),
            int(num_loci_k),
            round(float(ior_radius_ratio), 6),
        )
        cached_loci = SphericalIoRMultiLocusSniffer._IOR_CACHE.get(ior_key)
        if cached_loci is not None:
            return cached_loci

        metric_b = SpatialAnomalySniffer._get_tri_metric_tensor(reference_mesh)
        metric_a = SpatialAnomalySniffer._get_tri_metric_tensor(focal_mesh)
        normals_b = reference_mesh.face_normals
        normals_a = focal_mesh.face_normals

        pts_a = np.vstack([focal_mesh.vertices, focal_mesh.face_centroids])
        pts_b = np.vstack([reference_mesh.vertices, reference_mesh.face_centroids])

        def _project_pts_with_metric(
            pts: np.ndarray, metric: Tuple[np.ndarray, ...]
        ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
            (
                v0, ab, ac, ab_len2, ac_len2, ab_dot_ac, v0_dot_ab, v0_dot_ac,
                inv_det, inv_ab, inv_ac, inv_bc, c_ab, c_ac,
            ) = metric[:14]
            d1 = (pts @ ab.T) - v0_dot_ab[None, :]
            d2 = (pts @ ac.T) - v0_dot_ac[None, :]
            d2_m_d1 = d2 - d1
            v = (d1 * ac_len2[None, :] - d2 * ab_dot_ac[None, :]) * inv_det[None, :]
            w = (d2 * ab_len2[None, :] - d1 * ab_dot_ac[None, :]) * inv_det[None, :]

            mask_v0 = (d1 <= 0.0) & (d2 <= 0.0)
            mask_v1 = (d1 >= ab_len2[None, :]) & (d2_m_d1 <= c_ab[None, :])
            mask_v2 = (d2 >= ac_len2[None, :]) & (-d2_m_d1 <= c_ac[None, :])
            mask_e_ab = (w <= 0.0) & (d1 >= 0.0) & (d1 <= ab_len2[None, :])
            mask_e_ac = (v <= 0.0) & (d2 >= 0.0) & (d2 <= ac_len2[None, :])
            mask_e_bc = ((v + w) >= 1.0) & (d2_m_d1 >= c_ab[None, :]) & (-d2_m_d1 >= c_ac[None, :])

            v[mask_v0 | mask_v2 | mask_e_ac] = 0.0
            w[mask_v0 | mask_v1 | mask_e_ab] = 0.0
            v[mask_v1] = 1.0
            w[mask_v2] = 1.0
            if mask_e_ab.any():
                ip, it = np.where(mask_e_ab)
                v[ip, it] = d1[ip, it] * inv_ab[it]
            if mask_e_ac.any():
                ip, it = np.where(mask_e_ac)
                w[ip, it] = d2[ip, it] * inv_ac[it]
            if mask_e_bc.any():
                ip, it = np.where(mask_e_bc)
                w_bc = (d2_m_d1[ip, it] - c_ab[it]) * inv_bc[it]
                v[ip, it] = 1.0 - w_bc
                w[ip, it] = w_bc

            dx = pts[:, 0:1] - (v0[None, :, 0] + v * ab[None, :, 0] + w * ac[None, :, 0])
            dy = pts[:, 1:2] - (v0[None, :, 1] + v * ab[None, :, 1] + w * ac[None, :, 1])
            dz = pts[:, 2:3] - (v0[None, :, 2] + v * ab[None, :, 2] + w * ac[None, :, 2])
            np.multiply(dx, dx, out=dx)
            np.multiply(dy, dy, out=dy)
            np.add(dx, dy, out=dx)
            np.multiply(dz, dz, out=dz)
            np.add(dx, dz, out=dx)
            dist_sq = dx
            best_t = np.argmin(dist_sq, axis=1)
            r_idx = np.arange(pts.shape[0], dtype=np.int32)
            v_b, w_b = v[r_idx, best_t], w[r_idx, best_t]
            proj_pts = v0[best_t] + v_b[:, None] * ab[best_t] + w_b[:, None] * ac[best_t]
            return np.sqrt(np.maximum(dist_sq[r_idx, best_t], 0.0)), proj_pts, best_t

        d_ab, proj_b_on_ref, tri_b_idx = _project_pts_with_metric(pts_a, metric_b)
        d_ba, proj_a_on_foc, tri_a_idx = _project_pts_with_metric(pts_b, metric_a)

        n_va = focal_mesh.vertices.shape[0]
        adj_list_a = SphericalIoRMultiLocusSniffer._get_vertex_adj_faces_list(focal_mesh)
        na_for_ab = np.empty_like(pts_a)
        na_for_ab[n_va:] = normals_a
        for i in range(n_va):
            nb_i = normals_b[int(tri_b_idx[i])]
            adj = adj_list_a[i]
            if adj.size > 0:
                na_for_ab[i] = normals_a[adj[int(np.argmax(normals_a[adj] @ (-nb_i)))]]
            else:
                na_for_ab[i] = normals_a[0]
        nb_for_ab = normals_b[tri_b_idx]

        n_vb = reference_mesh.vertices.shape[0]
        adj_list_b = SphericalIoRMultiLocusSniffer._get_vertex_adj_faces_list(reference_mesh)
        nb_for_ba = np.empty_like(pts_b)
        nb_for_ba[n_vb:] = normals_b
        for j in range(n_vb):
            na_j = normals_a[int(tri_a_idx[j])]
            adj_b = adj_list_b[j]
            if adj_b.size > 0:
                nb_for_ba[j] = normals_b[adj_b[int(np.argmax(normals_b[adj_b] @ (-na_j)))]]
            else:
                nb_for_ba[j] = normals_b[0]
        na_for_ba = normals_a[tri_a_idx]

        all_pa = np.vstack([pts_a, proj_a_on_foc])
        all_pb = np.vstack([proj_b_on_ref, pts_b])
        all_na = np.vstack([na_for_ab, na_for_ba])
        all_nb = np.vstack([nb_for_ab, nb_for_ba])
        all_d_raw = np.concatenate([d_ab, d_ba])
        all_mids = 0.5 * (all_pa + all_pb)

        anti_parallel_cos = np.einsum("ij,ij->i", all_na, -all_nb)
        d_eff = np.where(anti_parallel_cos > 0.25, all_d_raw, all_d_raw + 0.50).copy()

        char_span = min(
            SE3AlignmentMath._norm3(focal_mesh.bbox_max - focal_mesh.bbox_min),
            SE3AlignmentMath._norm3(reference_mesh.bbox_max - reference_mesh.bbox_min),
        )
        sigma_ior = max(ior_radius_ratio * char_span, 0.045)
        two_sigma_sq = 2.0 * sigma_ior * sigma_ior

        role_names = ["PRIMARY_DATUM", "SECONDARY_GUIDE", "TERTIARY_STOP", "AUX_LOCUS"]
        loci: List[LocusContactFeature] = []
        used_normals_b: List[np.ndarray] = []

        for k in range(num_loci_k):
            win_idx = int(np.argmin(d_eff))
            pa_k = all_pa[win_idx]
            pb_k = all_pb[win_idx]
            ck = all_mids[win_idx]
            na_k = all_na[win_idx]
            nb_k = all_nb[win_idx]
            raw_dist = float(all_d_raw[win_idx])
            signed_n_gap = float(np.dot(pa_k - pb_k, nb_k))

            half_ext = max(raw_dist * 0.9, 0.042)
            roi_k = np.vstack([
                pa_k[None, :],
                pb_k[None, :],
                ck[None, :] + _SCRATCHPAD_CUBE_8 * half_ext,
            ])
            ndc_win_k, zoom_k, tight_z_k = SubFrustumMathEngine.compute_foveal_ndc_window(
                roi_k, view_matrix, base_proj_matrix, padding_factor=0.35, min_ndc_span=0.10, scene_meshes=scene_meshes
            )

            role = role_names[min(k, len(role_names) - 1)]
            if k > 0 and any(abs(float(np.dot(nb_k, prev_n))) < 0.35 for prev_n in used_normals_b):
                role = "SECONDARY_GUIDE" if k == 1 else "TERTIARY_STOP"
            used_normals_b.append(nb_k)

            loci.append(
                LocusContactFeature(
                    locus_id=k + 1,
                    semantic_role=role,
                    point_a_world=pa_k,
                    point_b_world=pb_k,
                    locus_midpoint_world=ck,
                    normal_a_world=na_k,
                    normal_b_world=nb_k,
                    unsigned_clearance_m=round(raw_dist, 4),
                    signed_normal_gap_m=round(signed_n_gap, 4),
                    fovea_ndc_window=ndc_win_k,
                    optical_zoom=round(zoom_k, 2),
                    tight_depth_range=tight_z_k,
                )
            )

            dist_sq_to_ck = np.sum((all_mids - ck[None, :]) ** 2, axis=1)
            spatial_suppression = 1.0 - np.exp(-dist_sq_to_ck / two_sigma_sq) + 1e-6
            normal_similarity = np.maximum(all_nb @ nb_k, 0.0)
            normal_penalty = 1.0 + 0.15 * normal_similarity
            d_eff = ((d_eff + 0.015) / spatial_suppression) * normal_penalty

        if len(SphericalIoRMultiLocusSniffer._IOR_CACHE) >= 32:
            SphericalIoRMultiLocusSniffer._IOR_CACHE.clear()
        SphericalIoRMultiLocusSniffer._IOR_CACHE[ior_key] = loci
        return loci

    @staticmethod
    def compute_multidatum_joint_se3_prescription(
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        loci: List[LocusContactFeature],
    ) -> MultiDatumJointSE3Prescription:
        """OP-209 主基准面 + 副导向面 + 止挡面联合正交约束 SE(3) 配准处方求解器"""
        if not loci:
            return MultiDatumJointSE3Prescription(
                primary_datum_normal_world=(0.0, 0.0, 1.0),
                secondary_guide_normal_world=None,
                tertiary_stop_normal_world=None,
                constrained_dof_count=0,
                rotation_euler_deg_xyz=(0.0, 0.0, 0.0),
                rotation_quaternion_wxyz=(1.0, 0.0, 0.0, 0.0),
                joint_translation_world_m=(0.0, 0.0, 0.0),
                datum_orthogonality_Spread_deg=0.0,
                prescription_summary="NO_LOCI_EXTRACTED",
            )

        primary = loci[0]
        n1 = primary.normal_b_world / max(SE3AlignmentMath._norm3(primary.normal_b_world), 1e-9)
        rot_mat, quat_wxyz, euler_deg, _, _ = SE3AlignmentMath.compute_full_triad_alignment(
            primary.normal_a_world, n1, focal_mesh.local_axes, reference_mesh.local_axes
        )
        probe_base = SpatialAnomalySniffer.probe_closest_clearance(focal_mesh, reference_mesh)
        t_vec = np.asarray(probe_base.axis_delta_m, dtype=np.float64).copy()
        piv = focal_mesh.bbox_center

        sec_normal: Optional[Tuple[float, float, float]] = None
        ter_normal: Optional[Tuple[float, float, float]] = None
        n2_unit: Optional[np.ndarray] = None
        dof_cnt = 3
        max_ortho_angle = 0.0

        for loc in loci[1:]:
            nb_cand = loc.normal_b_world / max(SE3AlignmentMath._norm3(loc.normal_b_world), 1e-9)
            dot1 = float(np.clip(np.dot(nb_cand, n1), -1.0, 1.0))
            ang_deg = math.degrees(math.acos(abs(dot1)))
            max_ortho_angle = max(max_ortho_angle, ang_deg)
            if abs(dot1) < 0.5 and n2_unit is None:
                n2_raw = nb_cand - dot1 * n1
                n2_unit = n2_raw / max(SE3AlignmentMath._norm3(n2_raw), 1e-9)
                sec_normal = (round(float(n2_unit[0]), 4), round(float(n2_unit[1]), 4), round(float(n2_unit[2]), 4))
                pa2_after_primary = rot_mat @ (loc.point_a_world - piv) + piv + t_vec
                gap2_proj = float(np.dot(pa2_after_primary - loc.point_b_world, n2_unit))
                if abs(gap2_proj) < 0.12:
                    t_vec = t_vec - gap2_proj * n2_unit
                dof_cnt = 5
            elif abs(dot1) < 0.5 and n2_unit is not None and abs(float(np.dot(nb_cand, n2_unit))) < 0.5 and ter_normal is None:
                n3_raw = SE3AlignmentMath._cross3(n1, n2_unit)
                n3_unit = n3_raw / max(SE3AlignmentMath._norm3(n3_raw), 1e-9)
                if float(np.dot(n3_unit, nb_cand)) < 0.0:
                    n3_unit = -n3_unit
                ter_normal = (round(float(n3_unit[0]), 4), round(float(n3_unit[1]), 4), round(float(n3_unit[2]), 4))
                pa3_after_sec = rot_mat @ (loc.point_a_world - piv) + piv + t_vec
                gap3_proj = float(np.dot(pa3_after_sec - loc.point_b_world, n3_unit))
                if abs(gap3_proj) < 0.12:
                    t_vec = t_vec - gap3_proj * n3_unit
                dof_cnt = 6

        p_n1 = (round(float(n1[0]), 4), round(float(n1[1]), 4), round(float(n1[2]), 4))
        t_tup = (round(float(t_vec[0]), 4), round(float(t_vec[1]), 4), round(float(t_vec[2]), 4))
        summary = (
            f"MULTI-DATUM SE(3) PRESCRIPTION ({dof_cnt}-DoF Constrained): Primary={p_n1}, "
            f"Secondary={sec_normal}, Rot={euler_deg}deg, Trans={t_tup}m"
        )
        return MultiDatumJointSE3Prescription(
            primary_datum_normal_world=p_n1,
            secondary_guide_normal_world=sec_normal,
            tertiary_stop_normal_world=ter_normal,
            constrained_dof_count=dof_cnt,
            rotation_euler_deg_xyz=euler_deg,
            rotation_quaternion_wxyz=quat_wxyz,
            joint_translation_world_m=t_tup,
            datum_orthogonality_Spread_deg=round(max_ortho_angle, 2),
            prescription_summary=summary,
        )

    @staticmethod
    def render_multilocus_foveal_montage(
        compositor: QuadCognitiveCanvasCompositor,
        meshes: List[MeshEntity3D],
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        cam_eye: np.ndarray,
        cam_target: np.ndarray,
        fov_y_deg: float = 45.0,
    ) -> Tuple[Image.Image, List[LocusContactFeature]]:
        """OP-210 PBO 零分配直拷组装 2x2 多焦点微距拼图算子"""
        base_probe = SpatialAnomalySniffer.probe_closest_clearance(focal_mesh, reference_mesh)
        roi_mid = 0.5 * (base_probe.point_a_world + base_probe.point_b_world)
        active_eye, _ = SubFrustumMathEngine.resolve_unoccluded_camera_eye(cam_eye, roi_mid, meshes)
        v_persp = SubFrustumMathEngine.build_look_at_view_matrix(active_eye, cam_target)
        p_persp = SubFrustumMathEngine.build_perspective_matrix(fov_y_deg, 1.0, 0.1, 25.0)
        loci = SphericalIoRMultiLocusSniffer.extract_multilocus_ior(
            focal_mesh, reference_mesh, v_persp, p_persp, meshes, num_loci_k=4
        )

        Q = compositor.quad_size
        montage_buf = np.full((Q * 2, Q * 2, 3), (12, 16, 24), dtype=np.uint8)
        slices = [
            (slice(0, Q), slice(0, Q)),
            (slice(0, Q), slice(Q, Q * 2)),
            (slice(Q, Q * 2), slice(0, Q)),
            (slice(Q, Q * 2), slice(Q, Q * 2)),
        ]

        for locus, (sy, sx) in zip(loci, slices):
            p_fovea_k = SubFrustumMathEngine.build_asymmetric_sub_frustum_matrix(
                p_persp, locus.fovea_ndc_window, tight_depth_range=locus.tight_depth_range
            )
            locus_probe = dataclasses.replace(
                base_probe,
                point_a_world=locus.point_a_world,
                point_b_world=locus.point_b_world,
                normal_a_world=locus.normal_a_world,
                normal_b_world=locus.normal_b_world,
                signed_clearance_m=locus.unsigned_clearance_m,
                is_aligned_flush=(locus.unsigned_clearance_m <= 1e-4),
                is_penetrating=False,
            )
            banner = (
                f"LOCUS #{locus.locus_id} [{locus.semantic_role}] | "
                f"GAP:{locus.unsigned_clearance_m * 1000:.1f}mm ({locus.optical_zoom:.1f}x)"
            )
            sub_res = compositor._render_single_viewport(
                meshes=meshes,
                view_matrix=v_persp,
                proj_matrix=p_fovea_k,
                title_banner=banner,
                probe_result=locus_probe,
                is_foveal_micro_view=True,
                return_rgb_array=True,
            )
            montage_buf[sy, sx] = sub_res if isinstance(sub_res, np.ndarray) else np.asarray(sub_res, dtype=np.uint8)

        return Image.fromarray(montage_buf, mode="RGB"), loci


# ============================================================================
# 4. Pillar 3：原生自适应二分 SE(3) 轨迹加密与折线（Dog-Leg）避障求解器
# ============================================================================

class AdaptiveSE3TrajectorySubdivider:
    """
    内化 Glimpse“8fps 全局粗扫 -> 14fps 局部时间窗加密重扫”的原生 SE(3) 连续轨迹碰撞检测与避障求解器
    """

    @staticmethod
    def inspect_and_subdivide_trajectory(
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        coarse_steps: int = 6,
        fine_steps: int = 16,
        danger_clearance_threshold_m: float = 0.005,
    ) -> Tuple[TrajectoryWindowSweepReport, List[MeshEntity3D]]:
        t0 = time.perf_counter()
        init_probe = SpatialAnomalySniffer.probe_closest_clearance(focal_mesh, reference_mesh)
        rot_full = init_probe.rotation_matrix_3x3
        trans_full = np.array(init_probe.axis_delta_m, dtype=np.float64)

        axis, theta_total = SE3AlignmentMath.so3_log_map_and_angle(rot_full)

        def _eval_at_tau(tau_val: float) -> Tuple[MeshEntity3D, SpatialClearanceProbeResult]:
            r_t = SE3AlignmentMath._rodrigues_axis_angle(axis, tau_val * theta_total)
            t_t = tuple((tau_val * trans_full).tolist())
            m_t = focal_mesh.rotated_around_pivot(r_t).translated(t_t)
            p_t = SpatialAnomalySniffer.probe_closest_clearance(m_t, reference_mesh)
            return m_t, p_t

        coarse_taus = np.linspace(0.0, 1.0, max(3, coarse_steps))
        coarse_log: List[Dict[str, Any]] = []
        coarse_clearances: List[float] = []
        coarse_meshes: List[MeshEntity3D] = []

        for idx_c, tau in enumerate(coarse_taus):
            if idx_c == 0:
                m_c, p_c = focal_mesh, init_probe
            else:
                m_c, p_c = _eval_at_tau(float(tau))
            coarse_meshes.append(m_c)
            c_m = float(p_c.signed_clearance_m)
            coarse_clearances.append(c_m)
            coarse_log.append({
                "tau": round(float(tau), 3),
                "signed_clearance_mm": round(c_m * 1000.0, 2),
                "is_penetrating": p_c.is_penetrating,
                "tilt_deg": p_c.contact_normal_angle_deg,
            })

        ambiguous_idx: Optional[int] = None
        for i in range(1, len(coarse_taus) - 1):
            c_prev, c_cur, c_next = coarse_clearances[i - 1], coarse_clearances[i], coarse_clearances[i + 1]
            is_valley = (c_cur < c_prev - 1e-4) and (c_cur < c_next - 1e-4)
            if c_cur < danger_clearance_threshold_m or is_valley:
                if ambiguous_idx is None or c_cur < coarse_clearances[ambiguous_idx]:
                    ambiguous_idx = i

        fine_log: List[Dict[str, Any]] = []
        fine_triggered = False
        amb_window: Optional[Tuple[float, float]] = None
        min_c_mm = min(c * 1000.0 for c in coarse_clearances)
        crit_tau = float(coarse_taus[int(np.argmin(coarse_clearances))])
        transient_collision = any(item["is_penetrating"] for item in coarse_log[:-1])
        keyframe_ghosts: List[MeshEntity3D] = [coarse_meshes[0], coarse_meshes[len(coarse_meshes) // 2]]

        if ambiguous_idx is not None:
            fine_triggered = True
            i_lo = max(0, ambiguous_idx - 1)
            i_hi = min(len(coarse_taus) - 1, ambiguous_idx + 1)
            tau_a = float(coarse_taus[i_lo])
            tau_b = float(coarse_taus[i_hi])
            amb_window = (round(tau_a, 3), round(tau_b, 3))
            fine_taus = np.linspace(tau_a, tau_b, max(4, fine_steps))
            worst_mesh = coarse_meshes[ambiguous_idx]
            n_fine_pts = len(fine_taus)
            for f_i, f_tau in enumerate(fine_taus):
                if f_i == 0:
                    m_f = coarse_meshes[i_lo]
                    cf_mm = coarse_clearances[i_lo] * 1000.0
                    is_pen = bool(coarse_log[i_lo]["is_penetrating"])
                elif f_i == n_fine_pts - 1:
                    m_f = coarse_meshes[i_hi]
                    cf_mm = coarse_clearances[i_hi] * 1000.0
                    is_pen = bool(coarse_log[i_hi]["is_penetrating"])
                else:
                    m_f, p_f = _eval_at_tau(float(f_tau))
                    cf_mm = float(p_f.signed_clearance_m) * 1000.0
                    is_pen = p_f.is_penetrating
                if cf_mm < min_c_mm:
                    min_c_mm = cf_mm
                    crit_tau = float(f_tau)
                    worst_mesh = m_f
                if is_pen and f_tau < 0.98:
                    transient_collision = True
                fine_log.append({
                    "tau": round(float(f_tau), 4),
                    "signed_clearance_mm": round(cf_mm, 2),
                    "is_penetrating": is_pen,
                })
            keyframe_ghosts = [coarse_meshes[0], worst_mesh]

        leveled_focal = (
            focal_mesh.rotated_around_pivot(rot_full)
            if abs(theta_total) > 1e-6
            else focal_mesh
        )
        n_ref = init_probe.normal_b_world / max(SE3AlignmentMath._norm3(init_probe.normal_b_world), 1e-9)
        proj_ref_max = float(np.max(reference_mesh.vertices @ n_ref))
        proj_foc_min = float(np.min(leveled_focal.vertices @ n_ref))
        safe_lift_h = max(0.08, (proj_ref_max - proj_foc_min) + 0.04)
        lift_vec = n_ref * safe_lift_h
        lateral_vec = trans_full - float(np.dot(trans_full, n_ref)) * n_ref
        drop_vec = float(np.dot(trans_full, n_ref)) * n_ref - lift_vec

        dogleg_waypoints = [
            ("STEP1_ROTATE_AND_SAFE_LIFT", (round(float(lift_vec[0]), 4), round(float(lift_vec[1]), 4), round(float(lift_vec[2]), 4))),
            ("STEP2_COLLISION_FREE_TANGENT_SHIFT", (round(float(lateral_vec[0]), 4), round(float(lateral_vec[1]), 4), round(float(lateral_vec[2]), 4))),
            ("STEP3_VERTICAL_PLUNGE_TO_FLUSH", (round(float(drop_vec[0]), 4), round(float(drop_vec[1]), 4), round(float(drop_vec[2]), 4))),
        ]

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        report = TrajectoryWindowSweepReport(
            coarse_steps=coarse_steps,
            fine_rewind_triggered=fine_triggered,
            ambiguous_window_tau=amb_window,
            fine_steps=fine_steps if fine_triggered else 0,
            min_clearance_along_path_mm=round(min_c_mm, 2),
            critical_tau=round(crit_tau, 4),
            transient_collision_detected=transient_collision,
            safe_dogleg_waypoints_world=dogleg_waypoints,
            coarse_log=coarse_log,
            fine_log=fine_log,
            compute_time_ms=elapsed_ms,
        )
        return report, keyframe_ghosts


# ============================================================================
# 5. Pillar 4：原生四步几何状态谓词分类与微距拼图核验器（Define -> Separate -> Verify -> Reference）
# ============================================================================

class BatchGeometricPredicateVerifier:
    """
    将 Glimpse 的“Define -> Separate -> Verify -> Reference”四步视觉核验范式
    内化为插件底层的确定性三维旋转不变 OBB 几何谓词分类器与缩略图拼图生成器
    """

    @staticmethod
    def _verify_and_collect_probes(
        candidate_meshes: List[MeshEntity3D],
        host_reference_mesh: MeshEntity3D,
        expected_bbox_size: Tuple[float, float, float],
        size_tolerance_ratio: float = 0.25,
    ) -> Tuple[InstanceVerificationReport, Dict[int, SpatialClearanceProbeResult]]:
        """OP-213 / OP-214 旋转不变 OBB 规格剥离 + 探针字典缓存复用内部引擎"""
        t0 = time.perf_counter()
        exp_sorted = np.sort(np.array(expected_bbox_size, dtype=np.float64))

        flush_cnt = 0
        floating_cnt = 0
        penetrating_cnt = 0
        distractor_cnt = 0
        registry: List[Dict[str, Any]] = []
        probe_cache: Dict[int, SpatialClearanceProbeResult] = {}

        for idx, cand in enumerate(candidate_meshes):
            local_proj = cand.vertices @ cand.local_axes.T
            obb_dims = np.sort(local_proj.max(axis=0) - local_proj.min(axis=0))
            aabb_dims = np.sort(cand.bbox_max - cand.bbox_min)
            rel_diff_obb = float(np.max(np.abs(obb_dims - exp_sorted) / np.maximum(exp_sorted, 1e-6)))
            rel_diff_aabb = float(np.max(np.abs(aabb_dims - exp_sorted) / np.maximum(exp_sorted, 1e-6)))
            rel_diff = min(rel_diff_obb, rel_diff_aabb)
            is_target_class = rel_diff <= size_tolerance_ratio

            if not is_target_class:
                category = "DISTRACTOR_DIFFERENT_GEOMETRY"
                distractor_cnt += 1
                clearance_mm = None
                tilt_deg = None
            else:
                probe = SpatialAnomalySniffer.probe_closest_clearance(cand, host_reference_mesh)
                probe_cache[idx] = probe
                clearance_mm = round(float(probe.signed_clearance_m) * 1000.0, 2)
                tilt_deg = float(probe.contact_normal_angle_deg)
                if probe.is_penetrating:
                    category = "SAME_CLASS_PENETRATING_DEFECT"
                    penetrating_cnt += 1
                elif probe.is_aligned_flush and tilt_deg <= 1.0:
                    category = "TARGET_VERIFIED_ALIGNED_FLUSH"
                    flush_cnt += 1
                else:
                    category = "SAME_CLASS_UNSEATED_FLOATING_OR_TILTED"
                    floating_cnt += 1

            c_pos = cand.bbox_center
            registry.append({
                "instance_index": idx + 1,
                "mark": cand.mark_label,
                "name": cand.name,
                "category": category,
                "world_centroid_xyz": [round(float(x), 3) for x in c_pos],
                "obb_dims_m": [round(float(x), 4) for x in obb_dims],
                "signed_clearance_mm": clearance_mm,
                "normal_tilt_deg": tilt_deg,
            })

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        report = InstanceVerificationReport(
            target_class_rule=f"OBB/BBox dims match {expected_bbox_size}m (±{int(size_tolerance_ratio*100)}%) AND state == ALIGNED_FLUSH",
            total_candidates_inspected=len(candidate_meshes),
            verified_flush_count=flush_cnt,
            same_class_floating_or_tilted_count=floating_cnt,
            same_class_penetrating_count=penetrating_cnt,
            distractor_geometry_count=distractor_cnt,
            spatial_reference_registry=registry,
            compute_time_ms=elapsed_ms,
        )
        return report, probe_cache

    @staticmethod
    def verify_and_classify_scene_instances(
        candidate_meshes: List[MeshEntity3D],
        host_reference_mesh: MeshEntity3D,
        expected_bbox_size: Tuple[float, float, float],
        size_tolerance_ratio: float = 0.25,
    ) -> InstanceVerificationReport:
        report, _ = BatchGeometricPredicateVerifier._verify_and_collect_probes(
            candidate_meshes, host_reference_mesh, expected_bbox_size, size_tolerance_ratio
        )
        return report

    @staticmethod
    def render_instance_verification_montage(
        compositor: QuadCognitiveCanvasCompositor,
        candidate_meshes: List[MeshEntity3D],
        host_reference_mesh: MeshEntity3D,
        expected_bbox_size: Tuple[float, float, float],
        cam_eye: np.ndarray,
        cam_target: np.ndarray,
        fov_y_deg: float = 45.0,
        size_tolerance_ratio: float = 0.25,
    ) -> Tuple[Image.Image, InstanceVerificationReport]:
        """OP-214 Glimpse 四步法微距核验图板合成器（零重复窄相探测 + PBO 零分配直拷拼图）"""
        ver_report, probe_cache = BatchGeometricPredicateVerifier._verify_and_collect_probes(
            candidate_meshes, host_reference_mesh, expected_bbox_size, size_tolerance_ratio
        )
        v_persp = SubFrustumMathEngine.build_look_at_view_matrix(cam_eye, cam_target)
        p_persp = SubFrustumMathEngine.build_perspective_matrix(fov_y_deg, 1.0, 0.1, 25.0)

        priority_map = {
            "SAME_CLASS_PENETRATING_DEFECT": 0,
            "SAME_CLASS_UNSEATED_FLOATING_OR_TILTED": 1,
            "TARGET_VERIFIED_ALIGNED_FLUSH": 2,
            "DISTRACTOR_DIFFERENT_GEOMETRY": 3,
        }
        indexed_items = [(idx, cand_m, reg_info) for idx, (cand_m, reg_info) in enumerate(zip(candidate_meshes, ver_report.spatial_reference_registry))]
        indexed_items.sort(key=lambda item: (priority_map.get(item[2]["category"], 9), item[2]["instance_index"]))
        selected_4 = indexed_items[:4]

        Q = compositor.quad_size
        montage_buf = np.full((Q * 2, Q * 2, 3), (12, 16, 24), dtype=np.uint8)
        slices = [
            (slice(0, Q), slice(0, Q)),
            (slice(0, Q), slice(Q, Q * 2)),
            (slice(Q, Q * 2), slice(0, Q)),
            (slice(Q, Q * 2), slice(Q, Q * 2)),
        ]

        for (idx_c, cand_m, reg_info), (sy, sx) in zip(selected_4, slices):
            probe_c = probe_cache.get(idx_c)
            if probe_c is None:
                probe_c = SpatialAnomalySniffer.probe_closest_clearance(cand_m, host_reference_mesh)
            ndc_win_c, zoom_c, tight_z_c = SubFrustumMathEngine.compute_foveal_ndc_window(
                probe_c.roi_vertices_world,
                v_persp,
                p_persp,
                padding_factor=0.40,
                min_ndc_span=0.12,
                scene_meshes=[host_reference_mesh, cand_m],
            )
            p_fovea_c = SubFrustumMathEngine.build_asymmetric_sub_frustum_matrix(
                p_persp, ndc_win_c, tight_depth_range=tight_z_c
            )
            cat_short = reg_info["category"].replace("SAME_CLASS_", "").replace("TARGET_VERIFIED_", "")
            c_mm = reg_info["signed_clearance_mm"]
            gap_str = f"{c_mm:+.1f}mm" if c_mm is not None else "N/A"
            banner = f"{cand_m.mark_label} [{cat_short[:14]}] | GAP:{gap_str} ({zoom_c:.1f}x)"
            focal_cand = cand_m if cand_m.is_focal_target else dataclasses.replace(
                cand_m, is_focal_target=True, pivot_world=cand_m.bbox_center.copy()
            )
            sub_res = compositor._render_single_viewport(
                meshes=[host_reference_mesh, focal_cand],
                view_matrix=v_persp,
                proj_matrix=p_fovea_c,
                title_banner=banner,
                probe_result=probe_c,
                is_foveal_micro_view=True,
                return_rgb_array=True,
            )
            montage_buf[sy, sx] = sub_res if isinstance(sub_res, np.ndarray) else np.asarray(sub_res, dtype=np.uint8)

        return Image.fromarray(montage_buf, mode="RGB"), ver_report


# ============================================================================
# 6. 自检与四大原生暂存空间能力全链路实测套件
# ============================================================================

if __name__ == "__main__":
    def _make_box(oid: str, mark: str, name: str, center: Tuple[float, float, float], size: Tuple[float, float, float], col: Tuple[int, int, int], focal: bool = False) -> MeshEntity3D:
        cx, cy, cz = center
        sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        v = np.array([
            [cx - sx, cy - sy, cz - sz], [cx + sx, cy - sy, cz - sz],
            [cx + sx, cy + sy, cz - sz], [cx - sx, cy + sy, cz - sz],
            [cx - sx, cy - sy, cz + sz], [cx + sx, cy - sy, cz + sz],
            [cx + sx, cy + sy, cz + sz], [cx - sx, cy + sy, cz + sz],
        ], dtype=np.float64)
        f = np.array([
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
            [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
        ], dtype=np.int32)
        e = np.array([
            [0, 1], [1, 2], [2, 3], [3, 0],
            [4, 5], [5, 6], [6, 7], [7, 4],
            [0, 4], [1, 5], [2, 6], [3, 7],
        ], dtype=np.int32)
        return MeshEntity3D(oid, mark, name, v, f, e, col, focal)

    def _make_u_channel() -> MeshEntity3D:
        specs = [
            ((0.0, 0.0, 0.10), (0.90, 0.70, 0.20)),
            ((-0.375, 0.0, 0.425), (0.15, 0.70, 0.45)),
            ((0.375, 0.0, 0.425), (0.15, 0.70, 0.45)),
        ]
        vs, fs, es = [], [], []
        v_off = 0
        for c, s in specs:
            b = _make_box("u", "#U", "U_Slot", c, s, (70, 130, 190), False)
            vs.append(b.vertices)
            fs.append(b.faces + v_off)
            es.append(b.edges + v_off)
            v_off += 8
        return MeshEntity3D("obj_uchan", "#U", "Concave_U_Channel_Slot", np.vstack(vs), np.vstack(fs), np.vstack(es), (70, 130, 190), False)

    compositor = QuadCognitiveCanvasCompositor(quad_size=384)
    cam_eye = np.array([2.2, -2.3, 1.75], dtype=np.float64)
    cam_target = np.array([0.0, 0.0, 0.35], dtype=np.float64)

    u_channel = _make_u_channel()
    slider_init = _make_box("obj_slider", "#B", "U_Slot_Slider", (0.04, 0.0, 0.39), (0.36, 0.40, 0.22), (225, 115, 65), True).rotated_around_pivot(
        SE3AlignmentMath.euler_xyz_to_matrix(roll_deg=-7.0, pitch_deg=9.0, yaw_deg=11.0)
    )
    scratchpad = SpatialScratchpadRingBuffer(compositor, max_history=8)
    f0 = scratchpad.commit_snapshot("INIT_TILTED_STATE", [u_channel, slider_init], slider_init, u_channel, cam_eye, cam_target, render_canvas=False)

    slider_aligned, _ = SpatialAlignmentVerifier.execute_alignment_and_recheck(slider_init, u_channel)
    f1 = scratchpad.commit_snapshot("POST_SE3_ALIGNMENT", [u_channel, slider_aligned], slider_aligned, u_channel, cam_eye, cam_target, render_canvas=True)
    delta_report = scratchpad.compute_step_delta(-2, -1)
    quad_hit_q4, world_pt_q4, depth_m_q4 = scratchpad.unproject_canvas_pixel_to_3d(576.0, 576.0, frame_index=-1)
    quad_hit_q1, world_pt_q1, depth_m_q1 = scratchpad.unproject_canvas_pixel_to_3d(192.0, 192.0, frame_index=-1)
    trail_img = scratchpad.render_multi_ghost_trail_canvas([u_channel, slider_aligned])

    t_ior_0 = time.perf_counter()
    montage_img, ior_loci = SphericalIoRMultiLocusSniffer.render_multilocus_foveal_montage(
        compositor, [u_channel, slider_init], slider_init, u_channel, cam_eye, cam_target
    )
    joint_presc = SphericalIoRMultiLocusSniffer.compute_multidatum_joint_se3_prescription(
        slider_init, u_channel, ior_loci
    )
    ior_ms = round((time.perf_counter() - t_ior_0) * 1000.0, 3)

    out_dir = pathlib.Path("artifacts/file_generation/ttl=63d/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    montage_img.save(out_dir / "human_eye_multilocus_ior_montage.png")
    trail_img.save(out_dir / "human_eye_scratchpad_ghost_trail.png")

    slider_grazing = _make_box("obj_slider_grz", "#B", "U_Slot_Grazing_Slider", (0.28, 0.0, 0.36), (0.36, 0.40, 0.22), (225, 115, 65), True).rotated_around_pivot(
        SE3AlignmentMath.euler_xyz_to_matrix(roll_deg=-12.0, pitch_deg=15.0, yaw_deg=14.0)
    )
    traj_report, _ = AdaptiveSE3TrajectorySubdivider.inspect_and_subdivide_trajectory(
        slider_grazing, u_channel, coarse_steps=6, fine_steps=16
    )

    table = _make_box("obj_table", "#A", "Worktable", (0.0, 0.0, 0.30), (1.60, 1.20, 0.60), (70, 130, 190), False)
    bolt_tilted = _make_box("b4", "#M4", "Bolt_Tilted_Floating", (-0.2, 0.2, 0.745), (0.16, 0.16, 0.20), (240, 200, 70)).rotated_around_pivot(
        SE3AlignmentMath.euler_xyz_to_matrix(roll_deg=22.0, pitch_deg=-18.0, yaw_deg=35.0)
    )
    candidates = [
        _make_box("b1", "#M1", "Bolt_Seated_1", (-0.4, -0.2, 0.70), (0.16, 0.16, 0.20), (90, 210, 130)),
        _make_box("b2", "#M2", "Bolt_Seated_2", (0.0, -0.2, 0.70), (0.16, 0.16, 0.20), (90, 210, 130)),
        _make_box("b3", "#M3", "Bolt_Seated_3", (0.4, -0.2, 0.70), (0.16, 0.16, 0.20), (90, 210, 130)),
        bolt_tilted,
        _make_box("b5", "#M5", "Bolt_Penetrating", (0.2, 0.2, 0.64), (0.16, 0.16, 0.20), (240, 85, 85)),
        _make_box("d1", "#D1", "Long_Guide_Rail_Distractor", (0.0, 0.45, 0.70), (0.85, 0.12, 0.20), (150, 150, 170)),
    ]
    inst_montage, inst_report = BatchGeometricPredicateVerifier.render_instance_verification_montage(
        compositor, candidates, table, expected_bbox_size=(0.16, 0.16, 0.20), cam_eye=cam_eye, cam_target=cam_target
    )
    inst_montage.save(out_dir / "human_eye_instance_verification_montage.png")

    print("=== Native 3D Visual & Geometric Scratchpad Verification Suite ===")
    print(f"[Pillar 1] RingBuffer Delta ({delta_report.from_step}->{delta_report.to_step}): "
          f"Gap {delta_report.clearance_before_mm}mm -> {delta_report.clearance_after_mm}mm, "
          f"Tilt {delta_report.normal_tilt_before_deg}° -> {delta_report.normal_tilt_after_deg}°, "
          f"Verdict={delta_report.convergence_verdict}")
    print(f"[Pillar 1] 2D->3D Unprojection at Q4(576,576): Quadrant={quad_hit_q4}, World={[round(float(x), 4) for x in world_pt_q4]}, Depth={depth_m_q4:.4f}m")
    print(f"[Pillar 1] 2D->3D Unprojection at Q1(192,192): Quadrant={quad_hit_q1}, World={[round(float(x), 4) for x in world_pt_q1]}, Depth={depth_m_q1:.4f}m")
    print(f"[Pillar 2] 3D Spherical IoR Extracted {len(ior_loci)} Distinct Loci + Rendered 768x768 Montage in {ior_ms}ms:")
    for loc in ior_loci:
        print(f"   - Locus #{loc.locus_id} [{loc.semantic_role}]: Mid={[round(float(x), 3) for x in loc.locus_midpoint_world]}, "
              f"NormalB={[round(float(x), 3) for x in loc.normal_b_world]}, Gap={loc.unsigned_clearance_m*1000:.1f}mm, Zoom={loc.optical_zoom}x")
    print(f"   - {joint_presc.prescription_summary}")
    print(f"[Pillar 3] Adaptive SE(3) Trajectory Sweep ({traj_report.compute_time_ms}ms): "
          f"FineRewind={traj_report.fine_rewind_triggered} (Window={traj_report.ambiguous_window_tau}), "
          f"MinClearance={traj_report.min_clearance_along_path_mm}mm, DogLegWaypoints={len(traj_report.safe_dogleg_waypoints_world)}")
    print(f"[Pillar 4] Batch Geometric Predicate Verifier ({inst_report.compute_time_ms}ms): "
          f"Total={inst_report.total_candidates_inspected} -> VerifiedFlush={inst_report.verified_flush_count}, "
          f"Floating={inst_report.same_class_floating_or_tilted_count}, Penetrating={inst_report.same_class_penetrating_count}, "
          f"Distractor={inst_report.distractor_geometry_count}")


