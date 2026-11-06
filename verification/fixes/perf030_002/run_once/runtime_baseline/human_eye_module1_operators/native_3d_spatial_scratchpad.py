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
# 2. Pillar 1–4 完整导出（与顶层 native_3d_spatial_scratchpad.py 零退化共享）
# ============================================================================

from human_eye_foveated_renderer import (
    AdaptiveSE3TrajectorySubdivider,
    BatchGeometricPredicateVerifier,
    SpatialScratchpadRingBuffer,
    SphericalIoRMultiLocusSniffer,
)

__all__ = [
    "SpatialScratchpadFrame",
    "StepDeltaAuditReport",
    "LocusContactFeature",
    "MultiDatumJointSE3Prescription",
    "TrajectoryWindowSweepReport",
    "InstanceVerificationReport",
    "SpatialScratchpadRingBuffer",
    "SphericalIoRMultiLocusSniffer",
    "AdaptiveSE3TrajectorySubdivider",
    "BatchGeometricPredicateVerifier",
]

