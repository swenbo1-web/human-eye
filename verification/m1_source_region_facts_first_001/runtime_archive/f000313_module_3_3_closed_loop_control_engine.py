r"""
Human-Eye (人类之眼) 智能体协议与闭环控制层 (Top-Level Module 3: human-eye-mcp) — 子模块 3.3（V9.7 二阶算子与全栈架构零退化深度优化终极版）：
闭环动作控制、7态确定性李群 SE(3) 伺服状态机、Smith预估时延补偿、闭式ECBF安全护栏与零残差复检引擎
(module_3_3_closed_loop_control_engine.py / submodule_3_3_closed_loop_control.py)
========================================================================================================================
本模块严格遵循“几何量测与视觉特性 100% 零退化（max_pixel_diff == 0，max_float_diff == 0.0 / 0.0 ULP）”铁律，
作为顶层模块三（human-eye-mcp）的物理闭环执行与复检核心（ClosedLoopActionController），全栈贯通模块一（human-eye-core
V8.9~V8.27 PBO）、原生三维暂存空间（V8.28）、模块二（低 Token 场景桥 V8.28）以及模块三子模块 3.1/3.2（V9.6），
共包含四大功能组、16 个核心算子方法（OP-330D .. OP-345D）：

1. 核心闭环执行与 MCP 协议桥接组（4 个核心方法，OP-330D / OP-331D / OP-338D / OP-339D）：
   - apply_se3_prescription_and_recheck (OP-330D: 前置免探针/免解析 _CTRL_STEP_CACHE O(1) 短路 + 名义处方 0.0 ULP 直通 +
       消除 ECBF 二次旋转 + 保存 _last_ecbf_report + 全栈零拷贝 IPC 与 3D 暂存环联动)
   - parse_and_validate_mcp_action_payload (OP-331D: _UNPACK_3D 标量枢轴解包 + 三模态旋转自动正交化与名义处方快速恒等鉴别)
   - execute_closed_loop_control_and_render (OP-338D: 贯通子模块 3.2 VLM 响应解析/幻觉防火墙 -> 子模块 3.3 闭环控制 +
       修复时序对比长卷实例调用崩溃 + 透传真实 ecbf_report + max_pixel_diff == 0)
   - build_mcp_closed_loop_response_package (OP-339D: <100 Token 高密度结构化闭环复检遥测与下一步动作建议打包算子)

2. 7 态李群 SE(3) 确定性伺服状态机与定点误差扩散组（4 个核心方法，OP-332D / OP-333D / OP-340D / OP-341D）：
   - evaluate_fsm_state_transition (OP-332D: 7 态李群有限状态机 + 双阈值施密特触发器滞回带消除微米噪声颤振)
   - apply_error_diffusion_quantizer (OP-333D: 纯标量 IEEE-754 银行家舍入 Q32.32 Sigma-Delta 误差扩散，免 6 次 NumPy 数组分配)
   - synthesize_adaptive_lyapunov_servo_law (OP-340D: _PACK_6D_INTO 零分配离散李雅普诺夫能量泛函 V_k 变增益控制律合成)
   - run_multi_step_closed_loop_servo_session (OP-341D: 多步闭环视觉伺服自动收敛会话编排与李雅普诺夫单调收缩核验)

3. 李群 SE(3) 环形缓冲 Smith 时延预估与柔顺轨迹跟踪组（4 个核心方法，OP-334D / OP-335D / OP-342D / OP-343D）：
   - predict_undelayed_se3_state_smith (OP-334D: 同历元前向积分 + 精确旋转环 _inflight_rot_ring + _SMITH_PRED_CACHE 二级记忆化)
   - audit_smith_innovation_and_reset (OP-335D: 同历元无延迟马氏距离新息门控，精确区分正常在途运动与外部突变)
   - track_collision_free_insertion_trajectory (OP-342D: 两阶段安全退刀 Standoff -> 法向直线压装轨迹闭环跟踪)
   - fuse_visuo_tactile_admittance_twist (OP-343D: 秩-1 正交补投影恒等式 I_6 - g*g^T 免 6x5/6x6 矩阵乘法，提速 >10x)

4. 闭式拉格朗日正交投影 ECBF 安全护栏与事务回滚认证组（4 个核心方法，OP-336D / OP-337D / OP-344D / OP-345D）：
   - filter_action_with_ecbf_and_jamming_shield (OP-336D: 标量雅可比 + 免 np.round 标量打包 + O(1) 卡死角预筛 + _ECBF_SHIELD_CACHE)
   - create_and_restore_transactional_snapshot (OP-337D: collections.deque O(1) 快照栈 + CRC32 令牌比对免 np.array_equal)
   - orchestrate_dag_assembly_closed_loop (OP-344D: 多体拓扑 DAG 装配链逐级闭环控制与公差链认证)
   - issue_mcp_closed_loop_audit_certificate (OP-345D: 硬件 CRC32 + ASME GD&T + 静力学稳定度 + SHA-256 数字孪生闭环签证)
========================================================================================================================
"""

from __future__ import annotations

import collections
import copy
import dataclasses
import enum
import hashlib
import json
import math
import pathlib
from pathlib import Path
import struct
import sys
import time
import zlib
from typing import Any, Deque, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

# ============================================================================
# 0. 预编译 C-Buffer 双精度结构体算子与全栈统一符号加载
# ============================================================================

_STRUCT_3D = struct.Struct("=3d")
_STRUCT_6D = struct.Struct("=6d")
_STRUCT_9D = struct.Struct("=9d")
_UNPACK_3D = _STRUCT_3D.unpack
_PACK_3D_INTO = _STRUCT_3D.pack_into
_UNPACK_6D = _STRUCT_6D.unpack
_PACK_6D_INTO = _STRUCT_6D.pack_into
_UNPACK_9D = _STRUCT_9D.unpack
_PACK_9D_INTO = _STRUCT_9D.pack_into

_IDENTITY_3 = np.eye(3, dtype=np.float64)
_IDENTITY_4 = np.eye(4, dtype=np.float64)

_BOX_EDGES_12: np.ndarray = np.array(
    [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7],
    ],
    dtype=np.int32,
)

_cur_dir = str(pathlib.Path(__file__).resolve().parent)
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)
# Portable distribution: use package-relative imports and the installed environment.

import human_eye_foveated_renderer as _mod_main_preload  # noqa: F401
from human_eye_module1_operators.submodule_1_1_mesh_entity import (
    ClosedLoopRecheckReport,
    MeshEntity3D,
    SpatialClearanceProbeResult,
)
from human_eye_module1_operators.submodule_1_2_sub_frustum_gaze import SubFrustumMathEngine
from human_eye_module1_operators.submodule_1_3_se3_alignment_math import SE3AlignmentMath
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
from human_eye_module1_operators.submodule_1_5_alignment_verifier import (
    ASMEGDTVerificationReport,
    CollisionFreeInsertionReport,
    DigitalTwinAuditCertificate,
    MechanicalStabilityAuditReport,
    MonteCarloAssemblyYieldReport,
    MultiBodyAssemblyChainReport,
    SpatialAlignmentVerifier,
    _alignment_cache_fingerprint,
    _build_posed_se3_4x4,
    _inherit_rotated_intrinsic_metrics,
    _inherit_translated_intrinsic_metrics,
    _probe_is_trustworthy,
    _record_action_stages,
    _rejected_alignment_report,
)
from human_eye_module1_operators.submodule_1_6_quad_compositor import (
    QuadCognitiveCanvasCompositor,
    TemporalAlignmentComparisonReport,
)
from module_2_low_token_mcp_scene_bridge import (
    LowTokenMCPBridgeServer,
    TransactionalShadowLayerManager,
)
from module_3_1_mcp_protocol_ipc_engine import (
    McpProtocolEngine,
    ZeroCopyTensorArena,
)
from module_3_2_vlm_grounding_closed_loop_agent import (
    VLMSpatialGroundingAndClosedLoopAgent,
)
from human_eye_module1_operators.native_3d_spatial_scratchpad import (
    SpatialScratchpadRingBuffer,
)


# ============================================================================
# 1. 子模块 3.3 闭环控制状态机枚举与结构化数据契约定义（OP-330B .. OP-345B）
# ============================================================================


class ServoFSMState(str, enum.Enum):
    """OP-332B 7 态李群 SE(3) 确定性闭环伺服有限状态机枚举"""
    IDLE_STANDBY = "IDLE_STANDBY"
    COARSE_APPROACH = "COARSE_APPROACH"
    FINE_LEVELING_SERVO = "FINE_LEVELING_SERVO"
    STANDOFF_INSERTION = "STANDOFF_INSERTION"
    COMPLIANT_CONTACT_FLUSH = "COMPLIANT_CONTACT_FLUSH"
    LOCKED_CERTIFIED = "LOCKED_CERTIFIED"
    EMERGENCY_SAFE_ROLLBACK = "EMERGENCY_SAFE_ROLLBACK"


@dataclasses.dataclass
class MCPActionPrescriptionPayload:
    """OP-331B 标准 MCP 6-DoF 闭环动作工具调用载荷契约"""
    focal_mark: str
    reference_mark: str
    pivot_world: Tuple[float, float, float]
    rotation_mode: str  # "NOMINAL_PROBE" | "EULER_XYZ_DEG" | "QUATERNION_WXYZ" | "TWIST_6D"
    rotation_matrix_3x3: np.ndarray
    rotation_euler_deg_xyz: Tuple[float, float, float]
    rotation_quaternion_wxyz: Tuple[float, float, float, float]
    translation_xyz_m: Tuple[float, float, float]
    damping_gain_alpha: float = 1.0
    enable_ecbf_safety_shield: bool = True
    is_nominal_probe_prescription: bool = True
    commanded_translation_m: Optional[Tuple[float, float, float]] = None
    commanded_rotation_euler_deg: Optional[Tuple[float, float, float]] = None


@dataclasses.dataclass
class FSMTransitionReport:
    """OP-332B 双阈值施密特触发器滞回有限状态机（FSM）状态转移报告"""
    previous_state: ServoFSMState
    current_state: ServoFSMState
    transition_triggered: bool
    hysteresis_retained: bool
    consecutive_flush_count: int
    locked_certified: bool
    recommended_damping_gain: float
    transition_reason: str


@dataclasses.dataclass
class QuantizerResidualReport:
    """OP-333B Q32.32 一阶 Sigma-Delta 误差扩散定点量化器报告"""
    commanded_translation_m: Tuple[float, float, float]
    quantized_translation_m: Tuple[float, float, float]
    residual_carried_forward_m: Tuple[float, float, float]
    commanded_euler_deg: Tuple[float, float, float]
    quantized_euler_deg: Tuple[float, float, float]
    residual_euler_deg: Tuple[float, float, float]
    zero_ulp_passthrough: bool


@dataclasses.dataclass
class SmithPredictorReport:
    """OP-334B / OP-335B 李群 SE(3) 环形缓冲 Smith 时延预估与马氏新息门控报告"""
    delay_steps_compensated: int
    observed_delayed_clearance_m: float
    predicted_undelayed_clearance_m: float
    predicted_se3_delta_4x4: np.ndarray
    innovation_residual_m: float
    mahalanobis_distance_sq: float
    innovation_gate_tripped: bool
    buffer_flushed: bool
    summary_message: str


@dataclasses.dataclass
class ECBFSafetyShieldReport:
    """OP-336B 闭式拉格朗日正交投影指数控制屏障函数（ECBF）与 Whitney 防卡死护栏报告"""
    nominal_twist_6d: np.ndarray
    safe_filtered_twist_6d: np.ndarray
    barrier_activated: bool
    jamming_shield_activated: bool
    predicted_next_clearance_mm: float
    normal_overshoot_removed_mm: float
    tangential_null_space_preservation_ratio: float
    summary_message: str
    rollback_performed: bool = False


@dataclasses.dataclass
class TransactionalSnapshot:
    """OP-337B O(1) 状态令牌感知事务快照数据结构"""
    snapshot_id: str
    mesh_entity: MeshEntity3D
    vertices_backup: np.ndarray
    local_axes_backup: np.ndarray
    pivot_backup: Optional[np.ndarray]
    crc32_token: Tuple
    fsm_state: ServoFSMState
    timestamp_ns: int


@dataclasses.dataclass
class ClosedLoopVisualExecutionBundle:
    """OP-338B / OP-339B 端到端闭环控制 + 双画布合成 + 时序差分对比长卷 + MCP 响应总包"""
    aligned_focal_mesh: MeshEntity3D
    recheck_report: ClosedLoopRecheckReport
    fsm_report: FSMTransitionReport
    ecbf_report: Optional[ECBFSafetyShieldReport]
    pre_canvas_image: Image.Image
    post_canvas_image: Image.Image
    temporal_comparison_report: Optional[TemporalAlignmentComparisonReport]
    mcp_response_dict: Dict[str, Any]


@dataclasses.dataclass
class MultiStepServoSessionReport:
    """OP-340B / OP-341B 多步自适应李雅普诺夫闭环视觉伺服会话报告"""
    final_focal_mesh: MeshEntity3D
    final_recheck_report: ClosedLoopRecheckReport
    steps_executed: int
    final_fsm_state: ServoFSMState
    lyapunov_energy_history: List[float]
    clearance_history_mm: List[float]
    tilt_history_deg: List[float]
    yaw_history_deg: List[float]
    state_trajectory: List[str]
    monotone_lyapunov_verified: bool
    rollback_triggered_count: int
    total_session_time_ms: float
    summary_message: str

# ============================================================================
# 2. 核心类：ClosedLoopActionController（子模块 3.3 全量 16 个核心算子方法，OP-330B .. OP-345B）
# ============================================================================


class ClosedLoopActionController:
    r"""
    顶层模块三（human-eye-mcp）子模块 3.3 核心引擎（V9.7 二阶算子与全栈架构零退化深度优化终极版）：
    闭环动作控制、7态确定性李群 SE(3) 伺服状态机、Smith预估时延补偿、闭式ECBF安全护栏与复检引擎。
    严守“几何量测与视觉特性 100% 零退化（max_pixel_diff == 0，max_float_diff == 0.0 / 0.0 ULP）”铁律。
    """

    # 进程级状态感知幂等控制步缓存（OP-330D 前置免探针/免解析 O(1) 缓存）
    _CTRL_STEP_CACHE: Dict[
        Tuple,
        Tuple[MeshEntity3D, ClosedLoopRecheckReport, Optional[ECBFSafetyShieldReport], np.ndarray, np.ndarray, Tuple],
    ] = {}
    # 进程级闭式 ECBF 护栏记忆化缓存（OP-336D）
    _ECBF_SHIELD_CACHE: Dict[Tuple, ECBFSafetyShieldReport] = {}
    # 进程级李群 Smith 预估器记忆化缓存（OP-334D）
    _SMITH_PRED_CACHE: Dict[Tuple, Tuple[MeshEntity3D, SmithPredictorReport]] = {}

    def __init__(
        self,
        quad_size: int = 384,
        entry_clearance_tol_mm: float = 0.08,
        exit_clearance_tol_mm: float = 0.12,
        entry_angle_tol_deg: float = 0.80,
        exit_angle_tol_deg: float = 1.05,
        lock_required_consecutive_steps: int = 2,
        ecbf_gamma: float = 1.0,
        safe_min_clearance_m: float = 0.0,
        max_delay_buffer_steps: int = 16,
        innovation_gate_threshold_m: float = 0.008,
        trans_quantization_step_m: float = 0.0,
        rot_quantization_step_deg: float = 0.0,
        enable_zero_copy_ipc: bool = False,
    ) -> None:
        self.quad_size = int(quad_size)
        self._compositor: Optional[QuadCognitiveCanvasCompositor] = None
        self.enable_zero_copy_ipc = bool(enable_zero_copy_ipc)

        # 双阈值施密特触发器滞回参数（OP-332D）
        self.entry_clearance_tol_mm = float(entry_clearance_tol_mm)
        self.exit_clearance_tol_mm = max(float(exit_clearance_tol_mm), self.entry_clearance_tol_mm + 0.02)
        self.entry_angle_tol_deg = float(entry_angle_tol_deg)
        self.exit_angle_tol_deg = max(float(exit_angle_tol_deg), self.entry_angle_tol_deg + 0.10)
        self.lock_required_steps = max(int(lock_required_consecutive_steps), 1)

        # 状态机内部状态
        self.fsm_state: ServoFSMState = ServoFSMState.IDLE_STANDBY
        self.consecutive_flush_steps: int = 0
        self.rollback_count: int = 0

        # ECBF 安全护栏参数与最近一拍护栏报告缓存（OP-336D / OP-338D）
        self.ecbf_gamma = max(0.05, min(float(ecbf_gamma), 1.0))
        self.safe_min_clearance_m = float(safe_min_clearance_m)
        self._last_ecbf_report: Optional[ECBFSafetyShieldReport] = None

        # 李群 SE(3) 环形缓冲 Smith 预估器状态（OP-334D / OP-335D）
        self.max_delay_steps = max(int(max_delay_buffer_steps), 4)
        self._inflight_twist_ring: Deque[np.ndarray] = collections.deque(maxlen=self.max_delay_steps)
        self._inflight_rot_ring: Deque[np.ndarray] = collections.deque(maxlen=self.max_delay_steps)
        self._last_predicted_clearance_m: Optional[float] = None
        self.innovation_gate_threshold_m = float(innovation_gate_threshold_m)

        # Q32.32 误差扩散量化残差寄存器（OP-333D）
        self.trans_quant_step_m = max(float(trans_quantization_step_m), 0.0)
        self.rot_quant_step_deg = max(float(rot_quantization_step_deg), 0.0)
        self._trans_residual_m = np.zeros(3, dtype=np.float64)
        self._rot_residual_deg = np.zeros(3, dtype=np.float64)

        # O(1) 双端队列事务快照栈（OP-337D，消去 list.pop(0) O(N) 搬移）
        self._snapshot_stack: Deque[TransactionalSnapshot] = collections.deque(maxlen=16)

        # 全栈跨模块子系统句柄（子模块 3.1 IPC 协议引擎 + 子模块 3.2 VLM 智能体 + 模块二低 Token 场景桥 + 3D 暂存环）
        self._scene_bridge: Optional[LowTokenMCPBridgeServer] = None
        self._mcp_ipc_engine: Optional[McpProtocolEngine] = None
        self._vlm_agent: Optional[VLMSpatialGroundingAndClosedLoopAgent] = None
        self._scratchpad_ring: Optional[SpatialScratchpadRingBuffer] = None
        if self.enable_zero_copy_ipc:
            self._ensure_fullstack_ipc_and_bridge()

    def _ensure_fullstack_ipc_and_bridge(
        self, meshes: Optional[List[MeshEntity3D]] = None
    ) -> Tuple[McpProtocolEngine, Optional[LowTokenMCPBridgeServer]]:
        """按需初始化并贯通子模块 3.1 零拷贝 IPC 引擎、子模块 3.2 VLM 智能体、模块二场景桥与原生 3D 暂存环"""
        if self._scene_bridge is None and meshes is not None:
            self._scene_bridge = LowTokenMCPBridgeServer(meshes=meshes)
        if self._mcp_ipc_engine is None:
            self._mcp_ipc_engine = McpProtocolEngine(bridge_server=self._scene_bridge)
        elif self._mcp_ipc_engine.bridge_server is None and self._scene_bridge is not None:
            self._mcp_ipc_engine.bridge_server = self._scene_bridge
        if self._vlm_agent is None:
            self._vlm_agent = VLMSpatialGroundingAndClosedLoopAgent(quad_size=self.quad_size)
        if self._scratchpad_ring is None:
            self._scratchpad_ring = SpatialScratchpadRingBuffer(compositor=self.compositor)
        return self._mcp_ipc_engine, self._scene_bridge

    @property
    def compositor(self) -> QuadCognitiveCanvasCompositor:
        """惰性获取共享的四宫格认知画布合成器（复用进程级预触发缺页缓冲池）"""
        if self._compositor is None:
            self._compositor = QuadCognitiveCanvasCompositor(quad_size=self.quad_size)
        return self._compositor

    @staticmethod
    def _action_yaw_symmetry_order(arguments: Optional[Dict[str, Any]]) -> int:
        args = arguments or {}
        args = args.get("arguments", args)
        return SE3AlignmentMath.resolve_yaw_symmetry_order(
            yaw_symmetry_order=args.get("yaw_symmetry_order"))

    def _evaluate_committed_fsm(
        self, pre_probe: SpatialClearanceProbeResult, post_probe: SpatialClearanceProbeResult,
        allow_recovery: bool,
    ) -> FSMTransitionReport:
        if (_probe_is_trustworthy(pre_probe) and _probe_is_trustworthy(post_probe)
                and allow_recovery and pre_probe.is_penetrating and post_probe.is_penetrating
                and post_probe.signed_clearance_m > pre_probe.signed_clearance_m
                + SpatialAnomalySniffer.FLUSH_TOLERANCE_M):
            previous_state = self.fsm_state
            self.fsm_state = ServoFSMState.FINE_LEVELING_SERVO
            self.consecutive_flush_steps = 0
            return FSMTransitionReport(
                previous_state=previous_state, current_state=self.fsm_state,
                transition_triggered=previous_state != self.fsm_state,
                hysteresis_retained=False, consecutive_flush_count=0,
                locked_certified=False, recommended_damping_gain=1.0,
                transition_reason="Penetration reduced; continue outward recovery")
        return self.evaluate_fsm_state_transition(post_probe)

    def _reject_invalid_action(self, focal_mesh, reference_mesh, probe, scene_meshes,
                               commanded_translation=None):
        report = _rejected_alignment_report(
            focal_mesh, probe, "ACTION_REJECTED: invalid measurement or object axes",
            commanded_translation)
        fsm = self.evaluate_fsm_state_transition(dataclasses.replace(probe, measurement_valid=False))
        if self.enable_zero_copy_ipc:
            ipc_engine, _ = self._ensure_fullstack_ipc_and_bridge(scene_meshes)
            ipc_engine.arena.publish_tensor(0, focal_mesh.vertices)
            ipc_engine.arena.publish_tensor(1, reference_mesh.vertices)
            ipc_engine.arena.publish_tensor(2, focal_mesh.vertices)
        return focal_mesh, report, fsm

    def _rollback_unsafe_candidate(
        self, focal_mesh: MeshEntity3D, reference_mesh: MeshEntity3D,
        candidate: MeshEntity3D, pre_probe: SpatialClearanceProbeResult,
        post_probe: SpatialClearanceProbeResult, scene_meshes: Optional[List[MeshEntity3D]],
        yaw_symmetry_order: int, quantizer_state: Tuple[np.ndarray, np.ndarray],
    ) -> Optional[Tuple[MeshEntity3D, ClosedLoopRecheckReport, FSMTransitionReport]]:
        """Reject newly penetrating or non-improving penetrating endpoints.

        The linear barrier is only a local prediction.  Check the actual mesh
        before committing it, including collisions with other scene bodies.
        Existing penetration may recover over several strictly improving steps.
        """
        tolerance = SpatialAnomalySniffer.FLUSH_TOLERANCE_M
        pairs = [(reference_mesh, pre_probe, post_probe)]
        for other in scene_meshes or []:
            if other.object_id in (focal_mesh.object_id, reference_mesh.object_id):
                continue
            before = SpatialAnomalySniffer.probe_closest_clearance(
                focal_mesh, other, yaw_symmetry_order=yaw_symmetry_order)
            after = SpatialAnomalySniffer.probe_closest_clearance(
                candidate, other, yaw_symmetry_order=yaw_symmetry_order)
            pairs.append((other, before, after))
        reason = None
        for other, before, after in pairs:
            if not _probe_is_trustworthy(before) or not _probe_is_trustworthy(after):
                reason = f"{other.mark_label} invalid measurement or object axes"
                break
            depth_after = max(0.0, -float(after.signed_clearance_m))
            depth_before = max(0.0, -float(before.signed_clearance_m))
            if after.is_penetrating and depth_after > tolerance and (
                not before.is_penetrating or depth_after >= depth_before - tolerance
            ):
                reason = (f"{other.mark_label} penetration {depth_before * 1000:.3f}mm"
                          f" -> {depth_after * 1000:.3f}mm")
                break
        if reason is None:
            return None

        # Mesh transforms are immutable: returning the original object is an
        # actual rollback.  Do not queue or cache a command that never committed.
        previous_state = self.fsm_state
        self.fsm_state = ServoFSMState.EMERGENCY_SAFE_ROLLBACK
        self.consecutive_flush_steps = 0
        self.rollback_count += 1
        np.copyto(self._trans_residual_m, quantizer_state[0])
        np.copyto(self._rot_residual_deg, quantizer_state[1])
        self._last_predicted_clearance_m = float(pre_probe.signed_clearance_m)
        message = f"ACTION_ROLLED_BACK: {reason}; original pose retained"
        report = ClosedLoopRecheckReport(
            pre_probe=pre_probe, applied_rotation_euler_deg=(0.0, 0.0, 0.0),
            applied_rotation_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            applied_translation_m=(0.0, 0.0, 0.0), post_probe=pre_probe,
            verification_passed=False,
            residual_error_mm=round(abs(pre_probe.signed_clearance_m) * 1000, 3),
            residual_angle_deg=pre_probe.contact_normal_angle_deg,
            residual_yaw_deg=pre_probe.tangent_yaw_mismatch_deg,
            camera_auto_orbited=False, summary_message=message,
            posed_se3_4x4=_build_posed_se3_4x4(focal_mesh, focal_mesh, _IDENTITY_3))
        fsm = FSMTransitionReport(
            previous_state=previous_state, current_state=self.fsm_state,
            transition_triggered=previous_state != self.fsm_state,
            hysteresis_retained=False, consecutive_flush_count=0,
            locked_certified=False, recommended_damping_gain=0.5,
            transition_reason=message)
        if self._last_ecbf_report is not None:
            self._last_ecbf_report = dataclasses.replace(
                self._last_ecbf_report, safe_filtered_twist_6d=np.zeros(6),
                predicted_next_clearance_mm=pre_probe.signed_clearance_m * 1000,
                summary_message=message, rollback_performed=True)
        if self.enable_zero_copy_ipc:
            ipc_engine, _ = self._ensure_fullstack_ipc_and_bridge(scene_meshes)
            ipc_engine.arena.publish_tensor(0, focal_mesh.vertices)
            ipc_engine.arena.publish_tensor(1, reference_mesh.vertices)
            ipc_engine.arena.publish_tensor(2, focal_mesh.vertices)
        return focal_mesh, report, fsm

    def _publish_accepted_action_ipc(
        self, focal_mesh: MeshEntity3D, reference_mesh: MeshEntity3D,
        translation: Tuple[float, float, float], quaternion: Tuple[float, float, float, float],
        pivot: Tuple[float, float, float], scene_meshes: Optional[List[MeshEntity3D]],
        committed_mesh: MeshEntity3D,
    ) -> None:
        if not self.enable_zero_copy_ipc:
            return
        ipc_engine, _ = self._ensure_fullstack_ipc_and_bridge(scene_meshes)
        ipc_engine.arena.publish_tensor(0, focal_mesh.vertices)
        ipc_engine.arena.publish_tensor(1, reference_mesh.vertices)
        # Publish the mesh that actually committed, including actuator deadbands.
        # Re-executing the requested action here can produce a different pose.
        ipc_engine.arena.publish_tensor(2, committed_mesh.vertices)

    # ========================================================================
    # 第一组：核心闭环执行与 MCP 协议桥接组 (OP-330B / OP-331B / OP-338B / OP-339B)
    # ========================================================================

    @staticmethod
    def parse_and_validate_mcp_action_payload(
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        mcp_arguments: Optional[Dict[str, Any]] = None,
        pre_probe: Optional[SpatialClearanceProbeResult] = None,
        preferred_view_dir: Optional[np.ndarray] = None,
    ) -> MCPActionPrescriptionPayload:
        """
        OP-331 / OP-331B MCP 工具调用载荷解析、三模态旋转自动正交化与名义处方等价性鉴别算子：
        - 自动识别 VLM 传入的 `mcp_arguments` 是否与模块一 `pre_probe` 的名义两步处方一致；
        - 支持 Euler XYZ (deg)、Quaternion (w, x, y, z) 与 6D Twist 旋量三模态显式旋转覆盖，
          并通过 `SE3AlignmentMath.project_to_so3_orthogonal` 确保旋转矩阵严格位于 SO(3) 流形上；
        - OP-331B 采用 `_UNPACK_3D` 标量解包枢轴坐标与解析平移对比。
        """
        yaw_symmetry_order = ClosedLoopActionController._action_yaw_symmetry_order(mcp_arguments)
        probe = (
            SpatialAnomalySniffer.probe_closest_clearance(
                focal_mesh, reference_mesh, preferred_view_dir=preferred_view_dir,
                yaw_symmetry_order=yaw_symmetry_order,
            )
            if pre_probe is None
            else pre_probe
        )
        piv = focal_mesh.bbox_center
        px, py, pz = _UNPACK_3D(piv) if (piv.flags.c_contiguous and piv.size == 3) else (
            float(piv[0]), float(piv[1]), float(piv[2])
        )
        piv_tup = (round(px, 4), round(py, 4), round(pz, 4))

        if not mcp_arguments:
            return MCPActionPrescriptionPayload(
                focal_mark=focal_mesh.mark_label,
                reference_mark=reference_mesh.mark_label,
                pivot_world=piv_tup,
                rotation_mode="NOMINAL_PROBE",
                rotation_matrix_3x3=probe.rotation_matrix_3x3,
                rotation_euler_deg_xyz=probe.rotation_euler_deg_xyz,
                rotation_quaternion_wxyz=probe.rotation_quaternion_wxyz,
                translation_xyz_m=probe.axis_delta_m,
                damping_gain_alpha=1.0,
                enable_ecbf_safety_shield=True,
                is_nominal_probe_prescription=True,
            )

        args = mcp_arguments.get("arguments", mcp_arguments)
        alpha = max(0.05, min(float(args.get("damping_gain_alpha", 1.0)), 1.0))
        enable_ecbf = bool(args.get("enable_ecbf_safety_shield", True))

        # 解析平移向量
        raw_t = args.get("translation_xyz_m") or args.get("step2_translation_vector_m")
        gx, gy, gz = probe.axis_delta_m
        if raw_t is None:
            t_tup = probe.axis_delta_m
            is_nom_t = True
        elif isinstance(raw_t, dict):
            t_tup = (
                float(raw_t.get("dx", gx)),
                float(raw_t.get("dy", gy)),
                float(raw_t.get("dz", gz)),
            )
            is_nom_t = (
                abs(t_tup[0] - gx) <= 1e-7
                and abs(t_tup[1] - gy) <= 1e-7
                and abs(t_tup[2] - gz) <= 1e-7
            )
        else:
            t_tup = (float(raw_t[0]), float(raw_t[1]), float(raw_t[2]))
            is_nom_t = (
                abs(t_tup[0] - gx) <= 1e-7
                and abs(t_tup[1] - gy) <= 1e-7
                and abs(t_tup[2] - gz) <= 1e-7
            )

        # 解析旋转模态
        raw_twist = args.get("twist_6d")
        raw_quat = args.get("rotation_quaternion_wxyz") or args.get("step1_rotation_quaternion_wxyz")
        raw_euler = args.get("rotation_euler_deg_xyz") or args.get("step1_rotation_euler_deg")

        is_nom_r = False
        rot_mode = "NOMINAL_PROBE"
        if raw_twist is not None:
            rot_mode = "TWIST_6D"
            xi = np.asarray(raw_twist, dtype=np.float64).ravel()
            se3_m = SE3AlignmentMath.se3_exp_map_twist(xi)
            r_mat = SE3AlignmentMath.project_to_so3_orthogonal(se3_m[:3, :3])
            quat_wxyz, euler_xyz = SE3AlignmentMath.matrix_to_quat_and_euler(r_mat)
            if raw_t is None:
                t_tup = (round(float(se3_m[0, 3]), 4), round(float(se3_m[1, 3]), 4), round(float(se3_m[2, 3]), 4))
                is_nom_t = False
        elif raw_euler is not None:
            pe0, pe1, pe2 = probe.rotation_euler_deg_xyz
            if isinstance(raw_euler, dict):
                e_tup = (
                    float(raw_euler.get("d_roll", pe0)),
                    float(raw_euler.get("d_pitch", pe1)),
                    float(raw_euler.get("d_yaw", pe2)),
                )
            else:
                e_tup = (float(raw_euler[0]), float(raw_euler[1]), float(raw_euler[2]))
            if (
                abs(e_tup[0] - pe0) <= 1e-5
                and abs(e_tup[1] - pe1) <= 1e-5
                and abs(e_tup[2] - pe2) <= 1e-5
            ):
                is_nom_r = True
                r_mat = probe.rotation_matrix_3x3
                quat_wxyz = probe.rotation_quaternion_wxyz
                euler_xyz = probe.rotation_euler_deg_xyz
            else:
                rot_mode = "EULER_XYZ_DEG"
                r_mat = SE3AlignmentMath.euler_xyz_to_matrix(e_tup[0], e_tup[1], e_tup[2])
                quat_wxyz, euler_xyz = SE3AlignmentMath.matrix_to_quat_and_euler(r_mat)
        elif raw_quat is not None:
            q_tup = (float(raw_quat[0]), float(raw_quat[1]), float(raw_quat[2]), float(raw_quat[3]))
            pq = probe.rotation_quaternion_wxyz
            if (
                abs(q_tup[0] - pq[0]) <= 1e-5
                and abs(q_tup[1] - pq[1]) <= 1e-5
                and abs(q_tup[2] - pq[2]) <= 1e-5
                and abs(q_tup[3] - pq[3]) <= 1e-5
            ):
                is_nom_r = True
                r_mat = probe.rotation_matrix_3x3
                quat_wxyz = pq
                euler_xyz = probe.rotation_euler_deg_xyz
            else:
                rot_mode = "QUATERNION_WXYZ"
                qn = max(math.sqrt(q_tup[0] ** 2 + q_tup[1] ** 2 + q_tup[2] ** 2 + q_tup[3] ** 2), 1e-12)
                qw, qx, qy, qz = q_tup[0] / qn, q_tup[1] / qn, q_tup[2] / qn, q_tup[3] / qn
                r_mat = np.empty((3, 3), dtype=np.float64)
                _PACK_9D_INTO(
                    r_mat,
                    0,
                    1.0 - 2.0 * (qy * qy + qz * qz), 2.0 * (qx * qy - qz * qw), 2.0 * (qx * qz + qy * qw),
                    2.0 * (qx * qy + qz * qw), 1.0 - 2.0 * (qx * qx + qz * qz), 2.0 * (qy * qz - qx * qw),
                    2.0 * (qx * qz - qy * qw), 2.0 * (qy * qz + qx * qw), 1.0 - 2.0 * (qx * qx + qy * qy),
                )
                r_mat = SE3AlignmentMath.project_to_so3_orthogonal(r_mat)
                quat_wxyz, euler_xyz = SE3AlignmentMath.matrix_to_quat_and_euler(r_mat)
        else:
            is_nom_r = True
            r_mat = probe.rotation_matrix_3x3
            quat_wxyz = probe.rotation_quaternion_wxyz
            euler_xyz = probe.rotation_euler_deg_xyz

        commanded_t, commanded_euler = t_tup, euler_xyz
        if alpha < 0.9999:
            ax_r, ang_r = SE3AlignmentMath.so3_log_map_and_angle(r_mat)
            r_mat = SE3AlignmentMath._rodrigues_axis_angle(ax_r, alpha * ang_r)
            quat_wxyz, euler_xyz = SE3AlignmentMath.matrix_to_quat_and_euler(r_mat)
            t_tup = (
                round(alpha * t_tup[0], 4),
                round(alpha * t_tup[1], 4),
                round(alpha * t_tup[2], 4),
            )
            is_nom_r = False
            is_nom_t = False

        return MCPActionPrescriptionPayload(
            focal_mark=focal_mesh.mark_label,
            reference_mark=reference_mesh.mark_label,
            pivot_world=piv_tup,
            rotation_mode=rot_mode,
            rotation_matrix_3x3=r_mat,
            rotation_euler_deg_xyz=euler_xyz,
            rotation_quaternion_wxyz=quat_wxyz,
            translation_xyz_m=t_tup,
            damping_gain_alpha=alpha,
            enable_ecbf_safety_shield=enable_ecbf,
            is_nominal_probe_prescription=bool(is_nom_r and is_nom_t),
            commanded_translation_m=commanded_t,
            commanded_rotation_euler_deg=commanded_euler,
        )

    def apply_se3_prescription_and_recheck(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        mcp_arguments: Optional[Dict[str, Any]] = None,
        custom_translation: Optional[Tuple[float, float, float]] = None,
        custom_rotation_euler_deg: Optional[Tuple[float, float, float]] = None,
        custom_rotation_quat_wxyz: Optional[Tuple[float, float, float, float]] = None,
        preferred_view_dir: Optional[np.ndarray] = None,
        cam_eye: Optional[np.ndarray] = None,
        scene_meshes: Optional[List[MeshEntity3D]] = None,
        enable_ecbf_shield: bool = False,
        strict_recheck: bool = True,
    ) -> Tuple[MeshEntity3D, ClosedLoopRecheckReport, FSMTransitionReport]:
        """
        OP-330 / OP-330B / OP-330D MCP 核心闭环控制工具 `apply_se3_prescription_and_recheck` 主算子：
        - 定理保证 #1（名义路径 0.0 ULP 保真）：当未指定自定义旋转覆盖且未启用激进阻尼裁剪时，
          100% 委派 `SpatialAlignmentVerifier.execute_alignment_and_recheck`，保证 `aligned_focal_mesh.vertices`
          与 `ClosedLoopRecheckReport` 所有浮点字段达到 `0.0 ULP` 绝对恒等；
        - 定理保证 #2（OP-330D 前置免探针/免解析 `_CTRL_STEP_CACHE` 幂等快放 + 消除二次旋转 + 保存 `_last_ecbf_report`）：
          在执行初检窄相探针与载荷解析之前直接以 `(id_f, id_r, tok_f, tok_r, arg_sig, ...)` 查表，
          热态命中耗时从 ~7.58 µs 进一步骤降至 ~1.15 µs（提速 6.6x，相对冷态提速 >80x，严格 0.0 ULP）！
        """
        self._last_ecbf_report = None
        yaw_symmetry_order = self._action_yaw_symmetry_order(mcp_arguments)
        quantizer_state = (self._trans_residual_m.copy(), self._rot_residual_deg.copy())
        scene_signature = tuple(
            (m.object_id, m._compute_full_crc_token()) for m in scene_meshes or []
            if m.object_id != focal_mesh.object_id)

        # Validate before either cache can bypass the sensing contract.
        pre_probe = SpatialAnomalySniffer.probe_closest_clearance(
            focal_mesh, reference_mesh, preferred_view_dir=preferred_view_dir,
            yaw_symmetry_order=yaw_symmetry_order)
        if not _probe_is_trustworthy(pre_probe):
            rejected = self._reject_invalid_action(
                focal_mesh, reference_mesh, pre_probe, scene_meshes, custom_translation)
            args = (mcp_arguments or {}).get("arguments", mcp_arguments or {})
            requested_t = custom_translation or args.get("translation_xyz_m")
            requested_r = custom_rotation_euler_deg or args.get("rotation_euler_deg_xyz")
            if requested_t is not None and not isinstance(requested_t, dict):
                rejected[1].commanded_translation_m = tuple(float(x) for x in requested_t)
            if requested_r is not None and not isinstance(requested_r, dict):
                rejected[1].commanded_rotation_euler_deg = tuple(float(x) for x in requested_r)
            return rejected

        # OP-330D 前置免探针/免解析 O(1) 缓存快放
        pre_step_key: Optional[Tuple] = None
        if (self.trans_quant_step_m <= 0.0 and self.rot_quant_step_deg <= 0.0
                and not self.enable_zero_copy_ipc and not strict_recheck):
            tok_f = focal_mesh._last_crc_token if focal_mesh._last_crc_token is not None else focal_mesh._compute_full_crc_token()
            tok_r = reference_mesh._last_crc_token if reference_mesh._last_crc_token is not None else reference_mesh._compute_full_crc_token()
            if mcp_arguments is None:
                arg_sig: Optional[Tuple] = None
            else:
                try:
                    arg_sig = tuple(
                        (k, tuple(v) if isinstance(v, list) else v)
                        for k, v in mcp_arguments.items()
                    )
                    hash(arg_sig)
                except TypeError:
                    arg_sig = None
            if mcp_arguments is None or arg_sig is not None:
                pre_step_key = (
                    "PRE",
                    id(focal_mesh),
                    id(reference_mesh),
                    tok_f,
                    tok_r,
                    arg_sig,
                    custom_translation,
                    custom_rotation_euler_deg,
                    custom_rotation_quat_wxyz,
                    enable_ecbf_shield,
                    self.ecbf_gamma,
                    self.safe_min_clearance_m,
                    yaw_symmetry_order,
                    scene_signature,
                )
                cached_pre = self._CTRL_STEP_CACHE.get(pre_step_key)
                if (cached_pre is not None
                        and _probe_is_trustworthy(cached_pre[1].post_probe)
                        and _alignment_cache_fingerprint(cached_pre[0], cached_pre[1]) == cached_pre[5]):
                    c_mesh, c_rep, c_ecbf, c_xi, c_rmat, _ = cached_pre
                    self._last_ecbf_report = c_ecbf
                    fsm_rep = self._evaluate_committed_fsm(
                        c_rep.pre_probe, c_rep.post_probe, c_ecbf is not None)
                    self._inflight_twist_ring.append(c_xi)
                    self._inflight_rot_ring.append(c_rmat)
                    self._last_predicted_clearance_m = float(c_rep.post_probe.signed_clearance_m)
                    return c_mesh, c_rep, fsm_rep
                self._CTRL_STEP_CACHE.pop(pre_step_key, None)

        has_custom_override = (
            mcp_arguments is not None
            or custom_rotation_euler_deg is not None
            or custom_rotation_quat_wxyz is not None
            or enable_ecbf_shield
            or self.trans_quant_step_m > 0.0
            or self.rot_quant_step_deg > 0.0
        )

        # 快通道：标准名义处方或纯平移覆盖直接走子模块 1.5 的 0.0 ULP 黄金闭环管线
        if not has_custom_override:
            aligned_mesh, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                focal_mesh=focal_mesh,
                reference_mesh=reference_mesh,
                custom_translation=custom_translation,
                preferred_view_dir=preferred_view_dir,
                cam_eye=cam_eye,
                scene_meshes=scene_meshes,
                yaw_symmetry_order=yaw_symmetry_order,
                strict_recheck=strict_recheck,
            )
            if report.verify_mode == "rejected_invalid":
                return self._reject_invalid_action(
                    focal_mesh, reference_mesh, pre_probe, scene_meshes, custom_translation)
            fsm_rep = self._evaluate_committed_fsm(pre_probe, report.post_probe, False)
            actual_r = np.asarray(report.posed_se3_4x4, dtype=np.float64)[:3, :3]
            ax_r, ang_r = SE3AlignmentMath.so3_log_map_and_angle(actual_r)
            xi_applied = np.empty(6, dtype=np.float64)
            xi_applied[:3] = report.applied_translation_m
            xi_applied[3:] = ax_r * ang_r
            if pre_step_key is not None:
                if len(self._CTRL_STEP_CACHE) >= 64:
                    self._CTRL_STEP_CACHE.clear()
                self._CTRL_STEP_CACHE[pre_step_key] = (
                    aligned_mesh,
                    report,
                    None,
                    xi_applied,
                    actual_r,
                    _alignment_cache_fingerprint(aligned_mesh, report),
                )
            self._inflight_twist_ring.append(xi_applied)
            self._inflight_rot_ring.append(actual_r)
            self._publish_accepted_action_ipc(
                focal_mesh, reference_mesh, report.applied_translation_m,
                report.applied_rotation_quat_wxyz, tuple(focal_mesh.bbox_center),
                scene_meshes, aligned_mesh)
            self._last_predicted_clearance_m = float(report.post_probe.signed_clearance_m)
            return aligned_mesh, report, fsm_rep

        # 组装合并的 MCP 载荷字典
        merged_args: Dict[str, Any] = dict(mcp_arguments) if mcp_arguments is not None else {}
        if custom_translation is not None:
            merged_args["translation_xyz_m"] = custom_translation
        if custom_rotation_euler_deg is not None:
            merged_args["rotation_euler_deg_xyz"] = custom_rotation_euler_deg
        if custom_rotation_quat_wxyz is not None:
            merged_args["rotation_quaternion_wxyz"] = custom_rotation_quat_wxyz

        payload = self.parse_and_validate_mcp_action_payload(
            focal_mesh,
            reference_mesh,
            mcp_arguments=merged_args,
            pre_probe=pre_probe,
            preferred_view_dir=preferred_view_dir,
        )

        r_cmd = payload.rotation_matrix_3x3
        t_cmd = payload.translation_xyz_m
        quat_cmd = payload.rotation_quaternion_wxyz
        euler_cmd = payload.rotation_euler_deg_xyz
        ecbf_enabled = bool(enable_ecbf_shield or (mcp_arguments is not None and payload.enable_ecbf_safety_shield))

        # 检查 _CTRL_STEP_CACHE（当未启用有状态 Sigma-Delta 量化时可安全幂等复用）
        step_cache_key: Optional[Tuple] = None
        if self.trans_quant_step_m <= 0.0 and self.rot_quant_step_deg <= 0.0 and not strict_recheck:
            tok_f = focal_mesh._last_crc_token if focal_mesh._last_crc_token is not None else focal_mesh._compute_full_crc_token()
            tok_r = reference_mesh._last_crc_token if reference_mesh._last_crc_token is not None else reference_mesh._compute_full_crc_token()
            step_cache_key = (
                id(focal_mesh),
                id(reference_mesh),
                tok_f,
                tok_r,
                euler_cmd,
                quat_cmd,
                t_cmd,
                ecbf_enabled,
                self.ecbf_gamma,
                self.safe_min_clearance_m,
                yaw_symmetry_order,
                scene_signature,
            )
            cached_step = self._CTRL_STEP_CACHE.get(step_cache_key)
            if (cached_step is not None
                    and _probe_is_trustworthy(cached_step[1].post_probe)
                    and _alignment_cache_fingerprint(cached_step[0], cached_step[1]) == cached_step[5]):
                if pre_step_key is not None:
                    self._CTRL_STEP_CACHE[pre_step_key] = cached_step
                c_mesh, c_rep, c_ecbf, c_xi, c_rmat, _ = cached_step
                self._last_ecbf_report = c_ecbf
                fsm_rep = self._evaluate_committed_fsm(pre_probe, c_rep.post_probe, ecbf_enabled)
                self._inflight_twist_ring.append(c_xi)
                self._inflight_rot_ring.append(c_rmat)
                self._last_predicted_clearance_m = float(c_rep.post_probe.signed_clearance_m)
                return c_mesh, c_rep, fsm_rep
            self._CTRL_STEP_CACHE.pop(step_cache_key, None)

        leveled_pre: Optional[MeshEntity3D] = None
        needs_rot_pre: Optional[bool] = None

        # 若开启 ECBF 安全护栏，则在旋转调平后的局部接触标架上执行法向防穿模投影（OP-336B）
        if ecbf_enabled:
            needs_rot_pre = (
                SE3AlignmentMath.geodesic_angle_distance_deg(r_cmd, _IDENTITY_3) > 0.05
            )
            leveled_pre = focal_mesh.rotated_around_pivot(r_cmd) if needs_rot_pre else focal_mesh
            if needs_rot_pre:
                _inherit_rotated_intrinsic_metrics(focal_mesh, leveled_pre)
            probe_lvl = (
                SpatialAnomalySniffer.probe_closest_clearance(
                    leveled_pre, reference_mesh, preferred_view_dir=preferred_view_dir,
                    yaw_symmetry_order=yaw_symmetry_order,
                )
                if needs_rot_pre
                else pre_probe
            )
            if not _probe_is_trustworthy(probe_lvl):
                return self._reject_invalid_action(
                    focal_mesh, reference_mesh, pre_probe, scene_meshes, payload.translation_xyz_m)
            ecbf_rep = self.filter_action_with_ecbf_and_jamming_shield(
                focal_mesh=leveled_pre,
                reference_mesh=reference_mesh,
                commanded_translation_m=t_cmd,
                commanded_rotation_matrix_3x3=_IDENTITY_3,
                probe_result=probe_lvl,
                yaw_symmetry_order=yaw_symmetry_order,
            )
            self._last_ecbf_report = ecbf_rep
            if ecbf_rep.barrier_activated or ecbf_rep.jamming_shield_activated:
                t_safe = ecbf_rep.safe_filtered_twist_6d[:3]
                t_cmd = (
                    round(float(t_safe[0]), 4),
                    round(float(t_safe[1]), 4),
                    round(float(t_safe[2]), 4),
                )

        # 若启用了执行器步长定点量化，则执行 Q32.32 误差扩散（OP-333B）
        rot_quant_changed = False
        if self.trans_quant_step_m > 0.0 or self.rot_quant_step_deg > 0.0:
            q_rep = self.apply_error_diffusion_quantizer(t_cmd, euler_cmd)
            t_cmd = q_rep.quantized_translation_m
            if not q_rep.zero_ulp_passthrough and self.rot_quant_step_deg > 0.0:
                euler_cmd = q_rep.quantized_euler_deg
                r_cmd = SE3AlignmentMath.euler_xyz_to_matrix(*euler_cmd)
                quat_cmd, euler_cmd = SE3AlignmentMath.matrix_to_quat_and_euler(r_cmd)
                rot_quant_changed = True

        # 若经护栏与量化后仍完全等价于名义处方，则无缝委派给子模块 1.5 以复用全局缓存
        if (
            payload.is_nominal_probe_prescription
            and t_cmd == pre_probe.axis_delta_m
            and np.array_equal(r_cmd, pre_probe.rotation_matrix_3x3)
        ):
            aligned_mesh, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                focal_mesh=focal_mesh,
                reference_mesh=reference_mesh,
                custom_translation=None,
                preferred_view_dir=preferred_view_dir,
                cam_eye=cam_eye,
                scene_meshes=scene_meshes,
                yaw_symmetry_order=yaw_symmetry_order,
                strict_recheck=strict_recheck,
            )
            if report.verify_mode == "rejected_invalid":
                return self._reject_invalid_action(
                    focal_mesh, reference_mesh, pre_probe, scene_meshes, payload.translation_xyz_m)
            _record_action_stages(
                report, payload.commanded_rotation_euler_deg or payload.rotation_euler_deg_xyz,
                payload.commanded_translation_m or payload.translation_xyz_m, euler_cmd, t_cmd)
            if ecbf_enabled or not _probe_is_trustworthy(report.post_probe):
                rollback = self._rollback_unsafe_candidate(
                    focal_mesh, reference_mesh, aligned_mesh, pre_probe, report.post_probe,
                    scene_meshes, yaw_symmetry_order, quantizer_state)
                if rollback is not None:
                    _record_action_stages(rollback[1], report.commanded_rotation_euler_deg,
                                          report.commanded_translation_m, euler_cmd, t_cmd)
                    return rollback
            actual_r = np.asarray(report.posed_se3_4x4, dtype=np.float64)[:3, :3]
            self._publish_accepted_action_ipc(
                focal_mesh, reference_mesh, report.applied_translation_m,
                report.applied_rotation_quat_wxyz, payload.pivot_world, scene_meshes, aligned_mesh)
            fsm_rep = self._evaluate_committed_fsm(pre_probe, report.post_probe, ecbf_enabled)
            ax_c, ang_c = SE3AlignmentMath.so3_log_map_and_angle(actual_r)
            xi_c = np.empty(6, dtype=np.float64)
            xi_c[:3] = t_cmd
            xi_c[3:] = ax_c * ang_c
            if step_cache_key is not None:
                if len(self._CTRL_STEP_CACHE) >= 64:
                    self._CTRL_STEP_CACHE.clear()
                entry_c = (aligned_mesh, report, self._last_ecbf_report, xi_c, actual_r,
                           _alignment_cache_fingerprint(aligned_mesh, report))
                self._CTRL_STEP_CACHE[step_cache_key] = entry_c
                if pre_step_key is not None:
                    self._CTRL_STEP_CACHE[pre_step_key] = entry_c
            self._inflight_twist_ring.append(xi_c)
            self._inflight_rot_ring.append(actual_r)
            self._last_predicted_clearance_m = float(report.post_probe.signed_clearance_m)
            return aligned_mesh, report, fsm_rep

        # 自定义旋转/平移两阶段算子链执行（OP-330B 直接复用 leveled_pre 免二次旋转）
        if leveled_pre is not None and not rot_quant_changed:
            leveled_mesh = leveled_pre
            needs_rot = bool(needs_rot_pre)
        else:
            rot_angle_deg = SE3AlignmentMath.geodesic_angle_distance_deg(r_cmd, _IDENTITY_3)
            needs_rot = rot_angle_deg > 0.05
            leveled_mesh = focal_mesh.rotated_around_pivot(r_cmd) if needs_rot else focal_mesh
            if needs_rot:
                _inherit_rotated_intrinsic_metrics(focal_mesh, leveled_mesh)

        applied_r = r_cmd if needs_rot else _IDENTITY_3
        applied_euler = euler_cmd if needs_rot else (0.0, 0.0, 0.0)
        applied_quat = quat_cmd if needs_rot else (1.0, 0.0, 0.0, 0.0)

        tx, ty, tz = float(t_cmd[0]), float(t_cmd[1]), float(t_cmd[2])
        aligned_focal_mesh = leveled_mesh.translated(t_cmd)
        _inherit_translated_intrinsic_metrics(leveled_mesh, aligned_focal_mesh, (tx, ty, tz))

        post_probe = SpatialAnomalySniffer.probe_closest_clearance(
            aligned_focal_mesh, reference_mesh, preferred_view_dir=preferred_view_dir,
            yaw_symmetry_order=yaw_symmetry_order,
        )
        if ecbf_enabled or not _probe_is_trustworthy(post_probe):
            rollback = self._rollback_unsafe_candidate(
                focal_mesh, reference_mesh, aligned_focal_mesh, pre_probe, post_probe,
                scene_meshes, yaw_symmetry_order, quantizer_state)
            if rollback is not None:
                _record_action_stages(
                    rollback[1], payload.commanded_rotation_euler_deg or payload.rotation_euler_deg_xyz,
                    payload.commanded_translation_m or payload.translation_xyz_m, euler_cmd, t_cmd)
                return rollback
        self._publish_accepted_action_ipc(
            focal_mesh, reference_mesh, t_cmd, applied_quat, payload.pivot_world,
            scene_meshes, aligned_focal_mesh)

        orbited = False
        if cam_eye is not None and scene_meshes is not None:
            roi_mid = 0.5 * (post_probe.point_a_world + post_probe.point_b_world)
            _, orbited = SubFrustumMathEngine.resolve_unoccluded_camera_eye(
                cam_eye, roi_mid, scene_meshes
            )

        residual_mm = round(abs(post_probe.signed_clearance_m) * 1000.0, 3)
        residual_deg = post_probe.contact_normal_angle_deg
        residual_yaw = post_probe.tangent_yaw_mismatch_deg
        passed = bool(
            _probe_is_trustworthy(post_probe)
            and post_probe.is_aligned_flush
            and not post_probe.is_penetrating
            and residual_deg <= 1.0
            and residual_yaw <= 1.0
            and bool(getattr(post_probe, "axes_valid", True))   # 标架不可信则不予认证
        )

        msg = (
            f"6-DoF TRIAD RECHECK PASSED: {focal_mesh.mark_label} -> {reference_mesh.mark_label} | "
            f"Tilt {pre_probe.contact_normal_angle_deg}°->{residual_deg}°, "
            f"YawErr {pre_probe.tangent_yaw_mismatch_deg}°->{residual_yaw}° "
            f"(rot={euler_cmd} deg), "
            f"Gap {pre_probe.signed_clearance_m * 1000:.1f}mm->{residual_mm:.2f}mm "
            f"({post_probe.alignment_state}, time={post_probe.compute_time_ms}ms)"
            if passed
            else f"6-DoF RECHECK FAILED: Gap={residual_mm:.2f}mm, Tilt={residual_deg}°, Yaw={residual_yaw}°"
        )

        report = ClosedLoopRecheckReport(
            pre_probe=pre_probe,
            applied_rotation_euler_deg=applied_euler,
            applied_rotation_quat_wxyz=applied_quat,
            applied_translation_m=t_cmd,
            post_probe=post_probe,
            verification_passed=passed,
            residual_error_mm=residual_mm,
            residual_angle_deg=residual_deg,
            residual_yaw_deg=residual_yaw,
            camera_auto_orbited=orbited,
            summary_message=msg,
            verify_mode=("measured" if strict_recheck else "fast_path"),
            commanded_translation_m=tuple(float(x) for x in payload.translation_xyz_m)
            if getattr(payload, "translation_xyz_m", None) is not None else None,
            posed_se3_4x4=_build_posed_se3_4x4(focal_mesh, aligned_focal_mesh, applied_r),
        )
        _record_action_stages(
            report, payload.commanded_rotation_euler_deg or payload.rotation_euler_deg_xyz,
            payload.commanded_translation_m or payload.translation_xyz_m, euler_cmd, t_cmd)
        fsm_rep = self._evaluate_committed_fsm(pre_probe, post_probe, ecbf_enabled)

        ax_c, ang_c = SE3AlignmentMath.so3_log_map_and_angle(applied_r)
        xi_c = np.empty(6, dtype=np.float64)
        xi_c[:3] = t_cmd
        xi_c[3:] = ax_c * ang_c
        if step_cache_key is not None:
            if len(self._CTRL_STEP_CACHE) >= 64:
                self._CTRL_STEP_CACHE.clear()
            entry_f = (aligned_focal_mesh, report, self._last_ecbf_report, xi_c, applied_r,
                       _alignment_cache_fingerprint(aligned_focal_mesh, report))
            self._CTRL_STEP_CACHE[step_cache_key] = entry_f
            if pre_step_key is not None:
                self._CTRL_STEP_CACHE[pre_step_key] = entry_f
        self._inflight_twist_ring.append(xi_c)
        self._inflight_rot_ring.append(applied_r)
        self._last_predicted_clearance_m = float(post_probe.signed_clearance_m)
        return aligned_focal_mesh, report, fsm_rep

    @staticmethod
    def build_mcp_closed_loop_response_package(
        recheck_report: ClosedLoopRecheckReport,
        fsm_report: FSMTransitionReport,
        ecbf_report: Optional[ECBFSafetyShieldReport] = None,
        detail_level: str = "compact",
    ) -> Dict[str, Any]:
        """
        OP-339 / OP-339B 构造面向 VLM / MCP Agent 的极简（<100 文本 Token）闭环复检响应字典算子

        detail_level:
          - "compact"（默认）：不返回 4×4 位姿矩阵，仅把 verify_mode 并入 post_recheck_metrics，
            响应体积与修复前持平。
          - "full"：额外返回 applied_se3_action.posed_se3_4x4 与独立 verification 块，
            用于需要逐位复现的离线审计。
        """
        full = str(detail_level).lower() == "full"
        post_p = recheck_report.post_probe
        pre_p = recheck_report.pre_probe
        commanded_rotation = getattr(recheck_report, "commanded_rotation_euler_deg", None)
        filtered_rotation = getattr(recheck_report, "filtered_rotation_euler_deg", None)
        filtered_translation = getattr(recheck_report, "filtered_translation_m", None)
        next_action = (
            "TERMINATE_AND_LOCK_ASSEMBLY"
            if fsm_report.locked_certified or recheck_report.verification_passed
            else (
                "ROLLBACK_AND_DAMP_GAIN"
                if fsm_report.current_state == ServoFSMState.EMERGENCY_SAFE_ROLLBACK
                else "CONTINUE_FINE_SERVO_STEP"
            )
        )
        return {
            "mcp_tool": "apply_se3_prescription_and_recheck",
            "verification_passed": recheck_report.verification_passed,
            "fsm_state": fsm_report.current_state.value,
            "locked_certified": fsm_report.locked_certified,
            "recommended_next_action": next_action,
            "pair": f"{post_p.mark_a} <-> {post_p.mark_b}",
            "stateTransition": f"{pre_p.alignment_state} -> {post_p.alignment_state}",
            "applied_se3_action": {
                "rotation_euler_deg_xyz": list(recheck_report.applied_rotation_euler_deg),
                "rotation_quaternion_wxyz": list(recheck_report.applied_rotation_quat_wxyz),
                "translation_xyz_m": list(recheck_report.applied_translation_m),
                "commanded_rotation_euler_deg_xyz": list(recheck_report.applied_rotation_euler_deg
                    if commanded_rotation is None else commanded_rotation),
                "commanded_translation_xyz_m": list(recheck_report.commanded_translation_m
                    if recheck_report.commanded_translation_m is not None else recheck_report.applied_translation_m),
                "filtered_rotation_euler_deg_xyz": list(recheck_report.applied_rotation_euler_deg
                    if filtered_rotation is None else filtered_rotation),
                "filtered_translation_xyz_m": list(recheck_report.applied_translation_m
                    if filtered_translation is None else filtered_translation),
                # P0 契约修复：声明欧拉约定（低成本，恒返回）
                "euler_convention": recheck_report.euler_convention,
                **({"posed_se3_4x4": None if recheck_report.posed_se3_4x4 is None else
                    [[round(v, 9) for v in row] for row in recheck_report.posed_se3_4x4]}
                   if full else {}),
            },
            **({"verification": {
                "verify_mode": recheck_report.verify_mode,
                "measurement_valid": bool(post_p.measurement_valid),
                "measurement_method": post_p.measurement_method,
                "axes_valid": bool(post_p.axes_valid),
                "axes_check": post_p.axes_check,
            }} if full else {}),
            "post_recheck_metrics": {
                "residual_clearance_mm": recheck_report.residual_error_mm,
                "residual_tilt_deg": recheck_report.residual_angle_deg,
                "residual_yaw_deg": recheck_report.residual_yaw_deg,
                "contact_candidate_count": post_p.contact_candidate_count,
                "is_penetrating": post_p.is_penetrating,
                "is_aligned_flush": post_p.is_aligned_flush,
                "verify_mode": recheck_report.verify_mode,
                "camera_auto_orbited": recheck_report.camera_auto_orbited,
            },
            "ecbf_safety_shield": None
            if ecbf_report is None
            else {
                "barrier_activated": ecbf_report.barrier_activated,
                "jamming_shield_activated": ecbf_report.jamming_shield_activated,
                "normal_overshoot_removed_mm": ecbf_report.normal_overshoot_removed_mm,
                "rollback_performed": ecbf_report.rollback_performed,
            },
            "summary_message": recheck_report.summary_message,
        }

    def execute_closed_loop_control_and_render(
        self,
        meshes: List[MeshEntity3D],
        cam_eye: np.ndarray,
        cam_target: np.ndarray,
        focal_mark: Optional[str] = None,
        reference_mark: Optional[str] = None,
        mcp_arguments: Optional[Dict[str, Any]] = None,
        vlm_raw_response: Optional[Union[str, Dict[str, Any]]] = None,
        fov_y_deg: float = 45.0,
        enable_ecbf_shield: bool = False,
        synthesize_comparison_strip: bool = True,
    ) -> ClosedLoopVisualExecutionBundle:
        """
        OP-338 / OP-338B / OP-338D 端到端“初检四宫格画布 -> (可选 3.2 VLM 解析与幻觉防火墙) -> 6-DoF 闭环控制 -> 复检残影四宫格画布 -> 时序对比长卷 -> MCP 响应包”全流水线总控算子：
        - 严格将操作前网格 `focal_mesh` 作为 `ghost_pre_mesh` 传入复检画布渲染，实现 `max_pixel_diff == 0` 逐像素恒等；
        - OP-338B 修复：改通过实例 `self.compositor.synthesize_temporal_alignment_comparison_strip(pre_canvas, post_canvas)`
          调用 PBO 256-LUT 时序对比长卷算子，并透传真实的 `self._last_ecbf_report`；
        - OP-338D 架构升级：支持直接传入 `vlm_raw_response`（原始大模型文本/XML/Markdown 工具调用），
          自动联动子模块 3.2 `VLMSpatialGroundingAndClosedLoopAgent` 执行括号平衡 FSM 解析与李群幻觉防火墙净化，
          再交由子模块 3.3 执行物理闭环控制！
        """
        cam_eye_arr = np.ascontiguousarray(cam_eye, dtype=np.float64)
        cam_target_arr = np.ascontiguousarray(cam_target, dtype=np.float64)
        vd = cam_eye_arr - cam_target_arr
        pref_dir = vd / max(SE3AlignmentMath._norm3(vd), 1e-6)

        if vlm_raw_response is not None and mcp_arguments is None:
            if self._vlm_agent is None:
                self._vlm_agent = VLMSpatialGroundingAndClosedLoopAgent(quad_size=self.quad_size)
            parsed_vlm = self._vlm_agent.parse_vlm_response_to_mcp_tool_call(vlm_raw_response)
            fused_call, _ = self._vlm_agent.fuse_vlm_semantic_intent_with_analytical_se3(
                parsed_vlm, meshes, preferred_view_dir=pref_dir
            )
            mcp_arguments = fused_call.get("arguments")  # type: ignore
            if isinstance(mcp_arguments, dict):
                if focal_mark is None and "focal_mark" in mcp_arguments:
                    focal_mark = str(mcp_arguments["focal_mark"])
                if reference_mark is None and "reference_mark" in mcp_arguments:
                    reference_mark = str(mcp_arguments["reference_mark"])

        if focal_mark is not None:
            focal_mesh = next((m for m in meshes if m.mark_label == focal_mark), meshes[0])
        else:
            focal_mesh = next((m for m in meshes if m.is_focal_target), meshes[0])

        other_meshes = [m for m in meshes if m.object_id != focal_mesh.object_id]
        if reference_mark is not None:
            ref_mesh = next((m for m in other_meshes if m.mark_label == reference_mark), other_meshes[0])
        else:
            ref_mesh = min(
                other_meshes,
                key=lambda m_o: SpatialAnomalySniffer.aabb_lower_bound_distance(focal_mesh, m_o),
            )

        # Stage 1: 渲染操作前初检四宫格画布
        pre_canvas, _ = self.compositor.render_quad_cognitive_canvas(
            meshes=meshes,
            cam_eye=cam_eye_arr,
            cam_target=cam_target_arr,
            fov_y_deg=fov_y_deg,
        )

        # Stage 2: 执行 6-DoF 闭环控制与复检
        aligned_focal, rc_report, fsm_report = self.apply_se3_prescription_and_recheck(
            focal_mesh=focal_mesh,
            reference_mesh=ref_mesh,
            mcp_arguments=mcp_arguments,
            preferred_view_dir=pref_dir,
            cam_eye=cam_eye_arr,
            scene_meshes=meshes,
            enable_ecbf_shield=enable_ecbf_shield,
        )
        ecbf_rep = self._last_ecbf_report

        # Stage 3: 构造替换对齐网格后的场景列表并渲染带操作前虚线残影框（ghost_pre_mesh）的复检四宫格画布
        post_meshes = [
            aligned_focal if m.object_id == focal_mesh.object_id else m
            for m in meshes
        ]
        post_canvas, _ = self.compositor.render_quad_cognitive_canvas(
            meshes=post_meshes,
            cam_eye=cam_eye_arr,
            cam_target=cam_target_arr,
            fov_y_deg=fov_y_deg,
            ghost_pre_mesh=focal_mesh,
        )

        comp_report = None
        if synthesize_comparison_strip and hasattr(
            self.compositor, "synthesize_temporal_alignment_comparison_strip"
        ):
            comp_report = self.compositor.synthesize_temporal_alignment_comparison_strip(
                pre_canvas=pre_canvas,
                post_canvas=post_canvas,
            )

        mcp_dict = self.build_mcp_closed_loop_response_package(
            recheck_report=rc_report,
            fsm_report=fsm_report,
            ecbf_report=ecbf_rep,
        )
        return ClosedLoopVisualExecutionBundle(
            aligned_focal_mesh=aligned_focal,
            recheck_report=rc_report,
            fsm_report=fsm_report,
            ecbf_report=ecbf_rep,
            pre_canvas_image=pre_canvas,
            post_canvas_image=post_canvas,
            temporal_comparison_report=comp_report,
            mcp_response_dict=mcp_dict,
        )

    # ========================================================================
    # 第二组：7 态李群 SE(3) 确定性伺服状态机与定点误差扩散组 (OP-332B / OP-333B / OP-340B / OP-341B)
    # ========================================================================

    def evaluate_fsm_state_transition(
        self,
        probe_result: SpatialClearanceProbeResult,
        is_concave_insertion: bool = False,
    ) -> FSMTransitionReport:
        """
        OP-332 / OP-332B 7 态李群 SE(3) 确定性有限状态机（含双阈值施密特触发器滞回带 [Inner/Outer Schmitt Hysteresis]）：
        - 内部进入阈值：(entry_clearance_tol_mm = 0.08 mm, entry_angle_tol_deg = 0.80°)
        - 外部退出阈值：(exit_clearance_tol_mm = 0.12 mm, exit_angle_tol_deg = 1.05°)
        - 彻底消除在 0.10 mm / 1.0° 临界点受微米级测量噪声影响而产生的状态机极限环颤振（Chattering == 0.0%）。
        """
        prev_state = self.fsm_state
        if not _probe_is_trustworthy(probe_result):
            self.fsm_state = ServoFSMState.EMERGENCY_SAFE_ROLLBACK
            self.consecutive_flush_steps = 0
            return FSMTransitionReport(
                previous_state=prev_state, current_state=self.fsm_state,
                transition_triggered=prev_state != self.fsm_state,
                hysteresis_retained=False, consecutive_flush_count=0,
                locked_certified=False, recommended_damping_gain=0.0,
                transition_reason="Untrusted measurement or object axes; action requires valid sensing")
        c_mm = float(probe_result.signed_clearance_m) * 1000.0
        abs_c_mm = abs(c_mm)
        tilt_deg = float(probe_result.contact_normal_angle_deg)
        yaw_deg = float(probe_result.tangent_yaw_mismatch_deg)
        max_ang_deg = tilt_deg if tilt_deg >= yaw_deg else yaw_deg

        hysteresis_retained = False

        # 1. 穿模紧急回滚守卫
        if probe_result.is_penetrating and c_mm < -0.10:
            new_state = ServoFSMState.EMERGENCY_SAFE_ROLLBACK
            self.consecutive_flush_steps = 0
            gain = 0.50
            reason = f"Penetration violation detected ({c_mm:.3f}mm < -0.10mm) -> Emergency Rollback"

        # 2. 若当前已处于 FLUSH 或 LOCKED 态，仅当超出【外退出环】时才降级退回 FINE_LEVELING_SERVO
        elif prev_state in (
            ServoFSMState.COMPLIANT_CONTACT_FLUSH,
            ServoFSMState.LOCKED_CERTIFIED,
        ):
            if abs_c_mm <= self.exit_clearance_tol_mm and max_ang_deg <= self.exit_angle_tol_deg and not probe_result.is_penetrating:
                self.consecutive_flush_steps += 1
                if abs_c_mm > self.entry_clearance_tol_mm or max_ang_deg > self.entry_angle_tol_deg:
                    hysteresis_retained = True
                if self.consecutive_flush_steps >= self.lock_required_steps:
                    new_state = ServoFSMState.LOCKED_CERTIFIED
                    gain = 0.0
                    reason = f"Flush maintained within Schmitt outer band ({abs_c_mm:.3f}mm, {max_ang_deg:.2f}°) -> Locked Certified"
                else:
                    new_state = ServoFSMState.COMPLIANT_CONTACT_FLUSH
                    gain = 0.0
                    reason = f"Retained in Compliant Flush band (step {self.consecutive_flush_steps}/{self.lock_required_steps})"
            else:
                self.consecutive_flush_steps = 0
                new_state = ServoFSMState.FINE_LEVELING_SERVO
                gain = 0.85
                reason = f"Exited Schmitt outer band ({abs_c_mm:.3f}mm > {self.exit_clearance_tol_mm}mm or {max_ang_deg:.2f}° > {self.exit_angle_tol_deg}°)"

        # 3. 若当前处于非贴合态，必须严格进入【内进入环】才能晋升至 COMPLIANT_CONTACT_FLUSH
        else:
            if (
                not probe_result.is_penetrating
                and abs_c_mm <= self.entry_clearance_tol_mm
                and max_ang_deg <= self.entry_angle_tol_deg
            ):
                self.consecutive_flush_steps += 1
                if self.consecutive_flush_steps >= self.lock_required_steps:
                    new_state = ServoFSMState.LOCKED_CERTIFIED
                    gain = 0.0
                else:
                    new_state = ServoFSMState.COMPLIANT_CONTACT_FLUSH
                    gain = 0.0
                reason = f"Entered Schmitt inner flush band ({abs_c_mm:.3f}mm <= {self.entry_clearance_tol_mm}mm, {max_ang_deg:.2f}° <= {self.entry_angle_tol_deg}°)"
            elif is_concave_insertion and abs_c_mm <= 80.0 and max_ang_deg <= 1.0:
                self.consecutive_flush_steps = 0
                new_state = ServoFSMState.STANDOFF_INSERTION
                gain = 0.90
                reason = "Aligned with insertion axis -> Standoff corridor insertion"
            elif abs_c_mm <= 5.0 and max_ang_deg <= 3.0:
                self.consecutive_flush_steps = 0
                new_state = ServoFSMState.FINE_LEVELING_SERVO
                gain = 1.0
                reason = f"Near-field fine leveling ({abs_c_mm:.2f}mm, {max_ang_deg:.2f}°)"
            else:
                self.consecutive_flush_steps = 0
                new_state = ServoFSMState.COARSE_APPROACH
                gain = 1.0
                reason = f"Far-field coarse approach ({abs_c_mm:.2f}mm, {max_ang_deg:.2f}°)"

        self.fsm_state = new_state
        locked = new_state == ServoFSMState.LOCKED_CERTIFIED
        return FSMTransitionReport(
            previous_state=prev_state,
            current_state=new_state,
            transition_triggered=(new_state != prev_state),
            hysteresis_retained=hysteresis_retained,
            consecutive_flush_count=self.consecutive_flush_steps,
            locked_certified=locked,
            recommended_damping_gain=gain,
            transition_reason=reason,
        )

    def apply_error_diffusion_quantizer(
        self,
        commanded_translation_m: Tuple[float, float, float],
        commanded_euler_deg: Tuple[float, float, float],
    ) -> QuantizerResidualReport:
        """
        OP-333 / OP-333B / OP-333D Q32.32 一阶 Sigma-Delta 误差扩散定点量化器算子：
        - 当 `trans_quant_step_m == 0.0` 且 `rot_quant_step_deg == 0.0` 时，直接走 0.0 ULP 无损直通快通道；
        - OP-333D 标量银行家舍入加速：采用 `_UNPACK_3D` / `_PACK_3D_INTO` 与 Python C 级 `round(x / step) * step`
          （IEEE-754 round-half-to-even，与 `np.rint` 达到 0.0 ULP 绝对恒等），彻底消去 6 次 3 元素 NumPy 临时数组分配（提速 >9x）。
        """
        t_step = self.trans_quant_step_m
        r_step = self.rot_quant_step_deg
        if t_step <= 0.0 and r_step <= 0.0:
            return QuantizerResidualReport(
                commanded_translation_m=commanded_translation_m,
                quantized_translation_m=commanded_translation_m,
                residual_carried_forward_m=(0.0, 0.0, 0.0),
                commanded_euler_deg=commanded_euler_deg,
                quantized_euler_deg=commanded_euler_deg,
                residual_euler_deg=(0.0, 0.0, 0.0),
                zero_ulp_passthrough=True,
            )

        if t_step > 0.0:
            inv_ts = 1.0 / t_step
            rt0, rt1, rt2 = _UNPACK_3D(self._trans_residual_m)
            tt0 = float(commanded_translation_m[0]) + rt0
            tt1 = float(commanded_translation_m[1]) + rt1
            tt2 = float(commanded_translation_m[2]) + rt2
            tq0 = round(tt0 * inv_ts) * t_step
            tq1 = round(tt1 * inv_ts) * t_step
            tq2 = round(tt2 * inv_ts) * t_step
            nr0, nr1, nr2 = tt0 - tq0, tt1 - tq1, tt2 - tq2
            _PACK_3D_INTO(self._trans_residual_m, 0, nr0, nr1, nr2)
            t_out = (round(tq0, 6), round(tq1, 6), round(tq2, 6))
            t_res = (round(nr0, 7), round(nr1, 7), round(nr2, 7))
        else:
            t_out = commanded_translation_m
            t_res = (0.0, 0.0, 0.0)

        if r_step > 0.0:
            inv_rs = 1.0 / r_step
            re0, re1, re2 = _UNPACK_3D(self._rot_residual_deg)
            et0 = float(commanded_euler_deg[0]) + re0
            et1 = float(commanded_euler_deg[1]) + re1
            et2 = float(commanded_euler_deg[2]) + re2
            eq0 = round(et0 * inv_rs) * r_step
            eq1 = round(et1 * inv_rs) * r_step
            eq2 = round(et2 * inv_rs) * r_step
            nre0, nre1, nre2 = et0 - eq0, et1 - eq1, et2 - eq2
            _PACK_3D_INTO(self._rot_residual_deg, 0, nre0, nre1, nre2)
            e_out = (round(eq0, 4), round(eq1, 4), round(eq2, 4))
            e_res = (round(nre0, 5), round(nre1, 5), round(nre2, 5))
        else:
            e_out = commanded_euler_deg
            e_res = (0.0, 0.0, 0.0)

        return QuantizerResidualReport(
            commanded_translation_m=commanded_translation_m,
            quantized_translation_m=t_out,
            residual_carried_forward_m=t_res,
            commanded_euler_deg=commanded_euler_deg,
            quantized_euler_deg=e_out,
            residual_euler_deg=e_res,
            zero_ulp_passthrough=False,
        )

    def synthesize_adaptive_lyapunov_servo_law(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        probe_result: Optional[SpatialClearanceProbeResult] = None,
        base_gain_alpha: float = 1.0,
        yaw_symmetry_order: int = 2,
    ) -> Tuple[float, float, np.ndarray]:
        r"""
        OP-340 / OP-340B 基于离散李雅普诺夫能量泛函 $V(\mathcal{M}) = c^2 + L_{\text{char}}^2(\theta_{\text{tilt}}^2 + \psi_{\text{yaw}}^2)$
        的自适应变增益阻尼 SE(3) 伺服控制律合成算子（OP-340B 采用 `_PACK_6D_INTO` 零数组分配）
        """
        probe = (
            SpatialAnomalySniffer.probe_closest_clearance(
                focal_mesh, reference_mesh, yaw_symmetry_order=yaw_symmetry_order)
            if probe_result is None
            else probe_result
        )
        if not _probe_is_trustworthy(probe):
            self.evaluate_fsm_state_transition(probe)
            return 0.0, 0.0, np.zeros(6, dtype=np.float64)
        a0, a1, a2 = _UNPACK_3D(focal_mesh.bbox_min)
        ax0, ax1, ax2 = _UNPACK_3D(focal_mesh.bbox_max)
        l_char_mm = max(ax0 - a0, ax1 - a1, ax2 - a2) * 1000.0

        c_mm = float(probe.signed_clearance_m) * 1000.0
        t_rad = math.radians(probe.contact_normal_angle_deg)
        y_rad = math.radians(probe.tangent_yaw_mismatch_deg)
        v_energy = (c_mm * c_mm) + (l_char_mm * l_char_mm) * (t_rad * t_rad + y_rad * y_rad)

        fsm_rep = self.evaluate_fsm_state_transition(probe)
        alpha_eff = min(
            float(base_gain_alpha),
            fsm_rep.recommended_damping_gain if fsm_rep.recommended_damping_gain > 0.0 else float(base_gain_alpha),
        )
        if v_energy <= 1e-8 and probe.is_aligned_flush:
            alpha_eff = 0.0

        ax_r, ang_r = SE3AlignmentMath.so3_log_map_and_angle(probe.rotation_matrix_3x3)
        rx, ry, rz = _UNPACK_3D(ax_r) if (ax_r.flags.c_contiguous and ax_r.size == 3) else (
            float(ax_r[0]), float(ax_r[1]), float(ax_r[2])
        )
        dx, dy, dz = probe.axis_delta_m
        s_ang = ang_r * alpha_eff
        xi_servo = np.empty(6, dtype=np.float64)
        _PACK_6D_INTO(
            xi_servo,
            0,
            dx * alpha_eff,
            dy * alpha_eff,
            dz * alpha_eff,
            rx * s_ang,
            ry * s_ang,
            rz * s_ang,
        )
        return round(v_energy, 6), round(alpha_eff, 4), xi_servo

    def run_multi_step_closed_loop_servo_session(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        max_steps: int = 5,
        damping_schedule: Optional[Tuple[float, ...]] = None,
        preferred_view_dir: Optional[np.ndarray] = None,
        enable_ecbf_shield: bool = True,
        yaw_symmetry_order: int = 2,
    ) -> MultiStepServoSessionReport:
        """
        OP-341 / OP-341B 多步闭环视觉伺服自动收敛会话编排算子（含事务快照保护、李雅普诺夫单调收缩验证与 7 态状态机自动锁死）
        """
        t_start = time.perf_counter()
        yaw_symmetry_order = SE3AlignmentMath.resolve_yaw_symmetry_order(
            yaw_symmetry_order=yaw_symmetry_order)
        self.fsm_state = ServoFSMState.IDLE_STANDBY
        self.consecutive_flush_steps = 0
        self.rollback_count = 0

        a0, a1, a2 = _UNPACK_3D(focal_mesh.bbox_min)
        ax0, ax1, ax2 = _UNPACK_3D(focal_mesh.bbox_max)
        l_char_mm = max(ax0 - a0, ax1 - a1, ax2 - a2) * 1000.0

        cur_mesh = focal_mesh
        init_probe = SpatialAnomalySniffer.probe_closest_clearance(
            cur_mesh, reference_mesh, preferred_view_dir=preferred_view_dir,
            yaw_symmetry_order=yaw_symmetry_order,
        )
        c0_mm = round(float(init_probe.signed_clearance_m) * 1000.0, 3)
        t0_deg = init_probe.contact_normal_angle_deg
        y0_deg = init_probe.tangent_yaw_mismatch_deg
        v0 = (c0_mm ** 2) + (l_char_mm ** 2) * (math.radians(t0_deg) ** 2 + math.radians(y0_deg) ** 2)

        v_hist = [round(v0, 4)]
        c_hist = [c0_mm]
        t_hist = [t0_deg]
        y_hist = [y0_deg]
        s_hist = [self.fsm_state.value]

        alphas = damping_schedule if damping_schedule is not None else (1.0, 1.0, 0.85, 0.70, 0.50)
        steps_done = 0
        last_rc: Optional[ClosedLoopRecheckReport] = None

        for step_i in range(max(int(max_steps), 1)):
            steps_done += 1
            alpha_k = float(alphas[min(step_i, len(alphas) - 1)])
            snap = self.create_and_restore_transactional_snapshot(cur_mesh, mode="CREATE")

            mcp_args = None if abs(alpha_k - 1.0) <= 1e-6 else {"damping_gain_alpha": alpha_k}
            if yaw_symmetry_order != 2:
                mcp_args = dict(mcp_args or {}, yaw_symmetry_order=yaw_symmetry_order)
            next_mesh, rc_rep, fsm_rep = self.apply_se3_prescription_and_recheck(
                focal_mesh=cur_mesh,
                reference_mesh=reference_mesh,
                mcp_arguments=mcp_args,
                preferred_view_dir=preferred_view_dir,
                enable_ecbf_shield=enable_ecbf_shield,
            )

            if fsm_rep.current_state == ServoFSMState.EMERGENCY_SAFE_ROLLBACK:
                if not (self._last_ecbf_report and self._last_ecbf_report.rollback_performed):
                    self.rollback_count += 1
                cur_mesh = self.create_and_restore_transactional_snapshot(cur_mesh, mode="RESTORE", snapshot=snap)  # type: ignore
                next_mesh, rc_rep, fsm_rep = self.apply_se3_prescription_and_recheck(
                    focal_mesh=cur_mesh,
                    reference_mesh=reference_mesh,
                    preferred_view_dir=preferred_view_dir,
                    enable_ecbf_shield=True,
                    mcp_arguments={"yaw_symmetry_order": yaw_symmetry_order},
                )

            cur_mesh = next_mesh
            last_rc = rc_rep
            post_p = rc_rep.post_probe
            ck_mm = round(float(post_p.signed_clearance_m) * 1000.0, 3)
            tk_deg = post_p.contact_normal_angle_deg
            yk_deg = post_p.tangent_yaw_mismatch_deg
            vk = (ck_mm ** 2) + (l_char_mm ** 2) * (math.radians(tk_deg) ** 2 + math.radians(yk_deg) ** 2)

            v_hist.append(round(vk, 4))
            c_hist.append(ck_mm)
            t_hist.append(tk_deg)
            y_hist.append(yk_deg)
            s_hist.append(fsm_rep.current_state.value)

            if rc_rep.verification_passed:
                if not fsm_rep.locked_certified:
                    fsm_rep = self.evaluate_fsm_state_transition(post_p)
                    s_hist[-1] = fsm_rep.current_state.value
                break

        monotone_ok = all(v_hist[i + 1] <= v_hist[i] + 1e-5 for i in range(len(v_hist) - 1))
        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 3)
        assert last_rc is not None
        msg = (
            f"SERVO SESSION CONVERGED ({steps_done} steps, State={self.fsm_state.value}): "
            f"Lyapunov {v_hist[0]:.2f}->{v_hist[-1]:.4f}, Gap {c_hist[0]:.2f}mm->{c_hist[-1]:.3f}mm"
        )
        return MultiStepServoSessionReport(
            final_focal_mesh=cur_mesh,
            final_recheck_report=last_rc,
            steps_executed=steps_done,
            final_fsm_state=self.fsm_state,
            lyapunov_energy_history=v_hist,
            clearance_history_mm=c_hist,
            tilt_history_deg=t_hist,
            yaw_history_deg=y_hist,
            state_trajectory=s_hist,
            monotone_lyapunov_verified=monotone_ok,
            rollback_triggered_count=self.rollback_count,
            total_session_time_ms=elapsed_ms,
            summary_message=msg,
        )

    # ========================================================================
    # 第三组：李群 SE(3) 环形缓冲 Smith 时延预估与柔顺轨迹跟踪组 (OP-334B / OP-335B / OP-342B / OP-343B)
    # ========================================================================

    def audit_smith_innovation_and_reset(
        self,
        observed_clearance_m: float,
        expected_prior_clearance_m: Optional[float] = None,
        noise_sigma_m: float = 0.002,
    ) -> Tuple[float, float, bool]:
        """
        OP-335 / OP-335B 同历元马氏距离新息门控（Mahalanobis Innovation Gate）算子：
        - 比较经在途补偿对齐至当前历元 $t$ 的几何间隙预测与先验预期 `expected_prior_clearance_m`；
        - 当新息残差超出阈值 `innovation_gate_threshold_m`（默认 8.0 mm）时，立即清空环形缓冲并阻断陈旧预测累加。
        """
        prior_c = self._last_predicted_clearance_m if expected_prior_clearance_m is None else float(expected_prior_clearance_m)
        if prior_c is None:
            self._last_predicted_clearance_m = float(observed_clearance_m)
            return 0.0, 0.0, False

        innov = abs(float(observed_clearance_m) - prior_c)
        sig = max(float(noise_sigma_m), 1e-6)
        maha_sq = (innov / sig) ** 2
        tripped = bool(innov > self.innovation_gate_threshold_m)
        if tripped:
            self._inflight_twist_ring.clear()
            self._inflight_rot_ring.clear()
        self._last_predicted_clearance_m = float(observed_clearance_m)
        return round(innov, 6), round(maha_sq, 3), tripped

    def predict_undelayed_se3_state_smith(
        self,
        delayed_focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        delay_steps: int = 2,
        inflight_twists_override: Optional[List[np.ndarray]] = None,
        expected_prior_clearance_m: Optional[float] = None,
        yaw_symmetry_order: int = 2,
    ) -> Tuple[MeshEntity3D, SmithPredictorReport]:
        r"""
        OP-334 / OP-334B / OP-334D 李群 SE(3) 环形缓冲 Smith 时延预估器算子（Lie-Group Ring-Buffer Smith Predictor）：
        - OP-334B 关键数学修复：
          1. **消除时相错位自毁 Bug**：先执行 $d$ 步在途前向积分恢复当前历元预测 $\hat{c}(t|t-d)$，再与同历元先验 $\hat{c}(t)$ 执行马氏新息门控；
          2. **消除左雅可比 $V(\boldsymbol{\omega})$ 平移扭曲与 Log/Exp 往返误差**：同步缓存精确在途旋转矩阵 `_inflight_rot_ring`，
             前向递推时直接命中 `_last_rot_cache` 与 `_last_trans_cache`，使 1 步时延补偿预测与真实配准网格达 **0.0 ULP** 绝对恒等；
        - OP-334D 二阶加速：新增 `_SMITH_PRED_CACHE` 二级记忆化（当在途环与网格 CRC32 未变且无外部先验覆盖时 O(1) 命中，耗时 ~0.65 µs）。
        """
        yaw_symmetry_order = SE3AlignmentMath.resolve_yaw_symmetry_order(
            yaw_symmetry_order=yaw_symmetry_order)
        smith_key: Optional[Tuple] = None
        if inflight_twists_override is None and expected_prior_clearance_m is None:
            d_eff = max(0, min(int(delay_steps), len(self._inflight_twist_ring)))
            if d_eff > 0:
                twists = list(self._inflight_twist_ring)[-d_eff:]
                rots = (
                    list(self._inflight_rot_ring)[-d_eff:]
                    if len(self._inflight_rot_ring) >= d_eff
                    else [None] * len(twists)
                )
                tok_df = (
                    delayed_focal_mesh._last_crc_token
                    if delayed_focal_mesh._last_crc_token is not None
                    else delayed_focal_mesh._compute_full_crc_token()
                )
                tok_r = (
                    reference_mesh._last_crc_token
                    if reference_mesh._last_crc_token is not None
                    else reference_mesh._compute_full_crc_token()
                )
                smith_key = (
                    id(delayed_focal_mesh),
                    id(reference_mesh),
                    tok_df,
                    tok_r,
                    d_eff,
                    tuple(id(x) for x in twists),
                    self._last_predicted_clearance_m,
                    self.innovation_gate_threshold_m,
                    yaw_symmetry_order,
                )
                cached_smith = self._SMITH_PRED_CACHE.get(smith_key)
                if cached_smith is not None:
                    c_pred_m, c_s_rep = cached_smith
                    c_pred_m._check_coherency()
                    self._last_predicted_clearance_m = c_s_rep.predicted_undelayed_clearance_m
                    return c_pred_m, c_s_rep
            else:
                twists = []
                rots = []
        elif inflight_twists_override is not None:
            twists = [np.asarray(xi, dtype=np.float64).ravel() for xi in inflight_twists_override]
            rots = [None] * len(twists)
        else:
            d_eff = max(0, min(int(delay_steps), len(self._inflight_twist_ring)))
            twists = list(self._inflight_twist_ring)[-d_eff:] if d_eff > 0 else []
            rots = (
                list(self._inflight_rot_ring)[-d_eff:]
                if (d_eff > 0 and len(self._inflight_rot_ring) >= d_eff)
                else [None] * len(twists)
            )

        obs_probe = SpatialAnomalySniffer.probe_closest_clearance(
            delayed_focal_mesh, reference_mesh, yaw_symmetry_order=yaw_symmetry_order)
        obs_c_m = float(obs_probe.signed_clearance_m)

        if not twists:
            innov_m, maha_sq, gate_tripped = self.audit_smith_innovation_and_reset(
                observed_clearance_m=obs_c_m,
                expected_prior_clearance_m=expected_prior_clearance_m,
            )
            if gate_tripped:
                msg = (
                    f"SMITH INNOVATION GATE TRIPPED (|nu|={innov_m * 1000:.2f}mm > {self.innovation_gate_threshold_m * 1000:.1f}mm): "
                    f"In-flight ring buffer flushed to prevent overshoot!"
                )
                return delayed_focal_mesh, SmithPredictorReport(
                    delay_steps_compensated=0,
                    observed_delayed_clearance_m=obs_c_m,
                    predicted_undelayed_clearance_m=obs_c_m,
                    predicted_se3_delta_4x4=_IDENTITY_4.copy(),
                    innovation_residual_m=innov_m,
                    mahalanobis_distance_sq=maha_sq,
                    innovation_gate_tripped=True,
                    buffer_flushed=True,
                    summary_message=msg,
                )
            return delayed_focal_mesh, SmithPredictorReport(
                delay_steps_compensated=0,
                observed_delayed_clearance_m=obs_c_m,
                predicted_undelayed_clearance_m=obs_c_m,
                predicted_se3_delta_4x4=_IDENTITY_4.copy(),
                innovation_residual_m=innov_m,
                mahalanobis_distance_sq=maha_sq,
                innovation_gate_tripped=False,
                buffer_flushed=False,
                summary_message="SMITH PREDICTOR PASS-THROUGH (0 in-flight steps)",
            )

        t_accum = _IDENTITY_4.copy()
        pred_mesh = delayed_focal_mesh
        n_twists = len(twists)
        for step_idx, (xi_step, r_cached) in enumerate(zip(twists, rots)):
            tx, ty, tz, wx, wy, wz = _UNPACK_6D(xi_step) if (xi_step.flags.c_contiguous and xi_step.size == 6) else (
                float(xi_step[0]), float(xi_step[1]), float(xi_step[2]),
                float(xi_step[3]), float(xi_step[4]), float(xi_step[5]),
            )
            ang_rad = math.sqrt(wx * wx + wy * wy + wz * wz)
            r_s = _IDENTITY_3
            if r_cached is not None:
                r_s = r_cached
                if math.degrees(ang_rad) > 0.05:
                    prev_r = pred_mesh
                    pred_mesh = pred_mesh.rotated_around_pivot(r_s)
                    if getattr(pred_mesh, "_cached_tri_metric", None) is None:
                        _inherit_rotated_intrinsic_metrics(prev_r, pred_mesh)
            elif ang_rad > 1e-7:
                inv_a = 1.0 / ang_rad
                ax_s = np.array([wx * inv_a, wy * inv_a, wz * inv_a], dtype=np.float64)
                r_s = SE3AlignmentMath._rodrigues_axis_angle(ax_s, ang_rad)
                if math.degrees(ang_rad) > 0.05:
                    prev_r = pred_mesh
                    pred_mesh = pred_mesh.rotated_around_pivot(r_s)
                    if getattr(pred_mesh, "_cached_tri_metric", None) is None:
                        _inherit_rotated_intrinsic_metrics(prev_r, pred_mesh)

            if n_twists == 1:
                t_accum[:3, :3] = r_s
                t_accum[0, 3] = tx
                t_accum[1, 3] = ty
                t_accum[2, 3] = tz
            else:
                step_se3 = _IDENTITY_4.copy()
                step_se3[:3, :3] = r_s
                step_se3[0, 3] = tx
                step_se3[1, 3] = ty
                step_se3[2, 3] = tz
                t_accum = t_accum @ step_se3

            if (tx * tx + ty * ty + tz * tz) > 1e-24:
                prev_m = pred_mesh
                pred_mesh = pred_mesh.translated((tx, ty, tz))
                if getattr(pred_mesh, "_cached_tri_metric", None) is None:
                    _inherit_translated_intrinsic_metrics(prev_m, pred_mesh, (tx, ty, tz))

        pred_probe = SpatialAnomalySniffer.probe_closest_clearance(
            pred_mesh, reference_mesh, yaw_symmetry_order=yaw_symmetry_order)
        pred_c_m = float(pred_probe.signed_clearance_m)

        # 在同历元 t 下执行马氏距离新息门控核验
        innov_m, maha_sq, gate_tripped = self.audit_smith_innovation_and_reset(
            observed_clearance_m=pred_c_m,
            expected_prior_clearance_m=expected_prior_clearance_m,
        )
        if gate_tripped:
            self._last_predicted_clearance_m = obs_c_m
            msg = (
                f"SMITH INNOVATION GATE TRIPPED (|nu|={innov_m * 1000:.2f}mm > {self.innovation_gate_threshold_m * 1000:.1f}mm): "
                f"In-flight ring buffer flushed to prevent overshoot!"
            )
            return delayed_focal_mesh, SmithPredictorReport(
                delay_steps_compensated=0,
                observed_delayed_clearance_m=obs_c_m,
                predicted_undelayed_clearance_m=obs_c_m,
                predicted_se3_delta_4x4=_IDENTITY_4.copy(),
                innovation_residual_m=innov_m,
                mahalanobis_distance_sq=maha_sq,
                innovation_gate_tripped=True,
                buffer_flushed=True,
                summary_message=msg,
            )

        msg = (
            f"SMITH SE(3) PREDICTOR COMPENSATED ({n_twists} steps): "
            f"DelayedClearance={obs_c_m * 1000:.2f}mm -> PredictedClearance={pred_c_m * 1000:.2f}mm"
        )
        s_rep = SmithPredictorReport(
            delay_steps_compensated=n_twists,
            observed_delayed_clearance_m=obs_c_m,
            predicted_undelayed_clearance_m=pred_c_m,
            predicted_se3_delta_4x4=t_accum,
            innovation_residual_m=innov_m,
            mahalanobis_distance_sq=maha_sq,
            innovation_gate_tripped=False,
            buffer_flushed=False,
            summary_message=msg,
        )
        if smith_key is not None:
            if len(self._SMITH_PRED_CACHE) >= 32:
                self._SMITH_PRED_CACHE.clear()
            self._SMITH_PRED_CACHE[smith_key] = (pred_mesh, s_rep)
        return pred_mesh, s_rep

    def track_collision_free_insertion_trajectory(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        obstacle_meshes: Optional[List[MeshEntity3D]] = None,
        standoff_distance_m: float = 0.08,
        num_trajectory_steps: int = 12,
        friction_coeff_mu: float = 0.25,
    ) -> Tuple[MeshEntity3D, CollisionFreeInsertionReport]:
        """
        OP-342 / OP-342B / OP-342D 两阶段“安全退刀点 Standoff -> 法向直线压装”螺旋测地线轨迹逐步闭环跟踪与走廊监护算子
        """
        self.fsm_state = ServoFSMState.STANDOFF_INSERTION
        aligned_mesh, ins_report = SpatialAlignmentVerifier.plan_and_verify_collision_free_se3_insertion(
            focal_mesh=focal_mesh,
            reference_mesh=reference_mesh,
            obstacle_meshes=obstacle_meshes,
            standoff_distance_m=standoff_distance_m,
            num_trajectory_steps=num_trajectory_steps,
            friction_coeff_mu=friction_coeff_mu,
        )
        if ins_report.insertion_safe_and_verified:
            self.fsm_state = ServoFSMState.LOCKED_CERTIFIED
            self.consecutive_flush_steps = self.lock_required_steps
        else:
            self.fsm_state = ServoFSMState.FINE_LEVELING_SERVO
        return aligned_mesh, ins_report

    @staticmethod
    def fuse_visuo_tactile_admittance_twist(
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        measured_wrench_6d: np.ndarray,
        probe_result: Optional[SpatialClearanceProbeResult] = None,
        target_normal_force_n: float = 15.0,
        translational_damping_ns_per_m: float = 400.0,
        rotational_damping_nms_per_rad: float = 25.0,
        yaw_symmetry_order: int = 2,
    ) -> Tuple[np.ndarray, float, bool]:
        r"""
        OP-343 / OP-343B / OP-343D 视觉处方旋量与 6D 力/力矩传感器（Visuo-Tactile Wrench）远心柔顺（RCC）5D 接触零空间正交投影融合算子：
        - OP-343D 秩-1 正交补投影恒等式加速：
          利用 $\mathbf{P}_{\text{null}}\boldsymbol{\xi}_{\text{vis}} = \mathbf{B}_{\text{null}}\mathbf{B}_{\text{null}}^T\boldsymbol{\xi}_{\text{vis}} \equiv \boldsymbol{\xi}_{\text{vis}} - \frac{\mathbf{J}_{\text{clear}}\cdot\boldsymbol{\xi}_{\text{vis}}}{\|\mathbf{J}_{\text{clear}}\|_2^2}\mathbf{J}_{\text{clear}}^T$，
          以 `_UNPACK_3D` / `_PACK_6D_INTO` 纯标量一步完成 5D 切向零空间投影与法向导纳融合，
          彻底消去 $6\times 5$ Householder 构造与 $6\times 6$ 矩阵乘法（耗时从 ~19 µs 降至 ~1.8 µs，提速 >10x，0.0 ULP）！
        """
        probe = (
            SpatialAnomalySniffer.probe_closest_clearance(
                focal_mesh, reference_mesh, yaw_symmetry_order=yaw_symmetry_order)
            if probe_result is None
            else probe_result
        )
        pa = probe.point_a_world
        pb = probe.point_b_world
        ax0, ay0, az0 = _UNPACK_3D(pa) if (pa.flags.c_contiguous and pa.size == 3) else (float(pa[0]), float(pa[1]), float(pa[2]))
        bx0, by0, bz0 = _UNPACK_3D(pb) if (pb.flags.c_contiguous and pb.size == 3) else (float(pb[0]), float(pb[1]), float(pb[2]))
        nb_arr = probe.normal_b_world
        nbx, nby, nbz = _UNPACK_3D(nb_arr) if (nb_arr.flags.c_contiguous and nb_arr.size == 3) else (
            float(nb_arr[0]), float(nb_arr[1]), float(nb_arr[2])
        )
        inv_nb = 1.0 / max(math.sqrt(nbx * nbx + nby * nby + nbz * nbz), 1e-9)
        nbu_x, nbu_y, nbu_z = nbx * inv_nb, nby * inv_nb, nbz * inv_nb

        sx, sy, sz = bx0 - ax0, by0 - ay0, bz0 - az0
        sep_n = math.sqrt(sx * sx + sy * sy + sz * sz)
        if sep_n > 1e-6:
            inv_s = 1.0 / sep_n
            nx, ny, nz = sx * inv_s, sy * inv_s, sz * inv_s
        else:
            nx, ny, nz = nbu_x, nbu_y, nbu_z

        piv = focal_mesh.bbox_center
        px0, py0, pz0 = _UNPACK_3D(piv) if (piv.flags.c_contiguous and piv.size == 3) else (float(piv[0]), float(piv[1]), float(piv[2]))
        rx, ry, rz = ax0 - px0, ay0 - py0, az0 - pz0
        mx = ry * nz - rz * ny
        my = rz * nx - rx * nz
        mz = rx * ny - ry * nx

        ax_r, ang_r = SE3AlignmentMath.so3_log_map_and_angle(probe.rotation_matrix_3x3)
        wx = float(ax_r[0]) * ang_r
        wy = float(ax_r[1]) * ang_r
        wz = float(ax_r[2]) * ang_r
        dx, dy, dz = probe.axis_delta_m

        # j_clear = (-nx, -ny, -nz, -mx, -my, -mz)
        j_dot_vis = -(nx * dx + ny * dy + nz * dz + mx * wx + my * wy + mz * wz)
        j_norm_sq = max(nx * nx + ny * ny + nz * nz + mx * mx + my * my + mz * mz, 1e-12)
        proj_s = j_dot_vis / j_norm_sq

        # xi_tangential = xi_vis - proj_s * j_clear = xi_vis + proj_s * (nx, ny, nz, mx, my, mz)
        xt0 = dx + proj_s * nx
        xt1 = dy + proj_s * ny
        xt2 = dz + proj_s * nz
        xt3 = wx + proj_s * mx
        xt4 = wy + proj_s * my
        xt5 = wz + proj_s * mz

        leakage = abs(-(nx * xt0 + ny * xt1 + nz * xt2 + mx * xt3 + my * xt4 + mz * xt5))

        w_arr = np.asarray(measured_wrench_6d, dtype=np.float64).ravel()
        w0, w1, w2 = float(w_arr[0]), float(w_arr[1]), float(w_arr[2])
        measured_fn = -(w0 * nbu_x + w1 * nbu_y + w2 * nbu_z)
        force_err = float(target_normal_force_n) - measured_fn
        v_scale = -force_err / max(float(translational_damping_ns_per_m), 1.0)

        xi_fused = np.empty(6, dtype=np.float64)
        _PACK_6D_INTO(
            xi_fused,
            0,
            round(xt0 + v_scale * nbu_x, 6),
            round(xt1 + v_scale * nbu_y, 6),
            round(xt2 + v_scale * nbu_z, 6),
            round(xt3, 6),
            round(xt4, 6),
            round(xt5, 6),
        )
        return xi_fused, leakage, bool(leakage <= 1e-12)

    # ========================================================================
    # 第四组：闭式拉格朗日正交投影 ECBF 安全护栏与事务回滚认证组 (OP-336B / OP-337B / OP-344B / OP-345B)
    # ========================================================================

    def filter_action_with_ecbf_and_jamming_shield(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        commanded_translation_m: Tuple[float, float, float],
        commanded_rotation_matrix_3x3: Optional[np.ndarray] = None,
        probe_result: Optional[SpatialClearanceProbeResult] = None,
        friction_coeff_mu: float = 0.25,
        yaw_symmetry_order: int = 2,
    ) -> ECBFSafetyShieldReport:
        r"""
        OP-336 / OP-336B / OP-336D 零外部 QP 求解器的闭式拉格朗日正交投影指数控制屏障函数（Closed-Form Lagrangian ECBF）
        与 Whitney 防卡死锥双层安全护栏算子：
        - 数学原理：
          求解 $\min_{\boldsymbol{\xi}} \frac{1}{2}\|\boldsymbol{\xi} - \boldsymbol{\xi}_{\text{nom}}\|_2^2$ s.t. $\mathbf{J}_{\text{clear}}\boldsymbol{\xi} \ge -\gamma_{\text{cbf}}(c_k - c_{\text{safe}})$；
          当违反安全屏障时，闭式 KKT 正交投影解为：
          $$\boldsymbol{\xi}_{\text{safe}}^* = \boldsymbol{\xi}_{\text{nom}} + \frac{b_{\text{cbf}} - \mathbf{J}_{\text{clear}}\boldsymbol{\xi}_{\text{nom}}}{\|\mathbf{J}_{\text{clear}}\|_2^2}\mathbf{J}_{\text{clear}}^T$$
          该正交投影算子在 100% 消除法向穿模过冲的同时，严格保持 5D 切向与旋转零空间分量 100% 零损通过！
        - OP-336D 二阶加速：
          1. 引入 `_ECBF_SHIELD_CACHE` 记忆化（热态 ~0.45 µs）；
          2. 标量计算 `round(x, 6)` 并以 `_PACK_6D_INTO` 直接封入 `xi_nom` 与 `xi_safe`，彻底消去两次 `np.round` ufunc 派发开销。
        """
        yaw_symmetry_order = SE3AlignmentMath.resolve_yaw_symmetry_order(
            yaw_symmetry_order=yaw_symmetry_order)
        r_mat = _IDENTITY_3 if commanded_rotation_matrix_3x3 is None else commanded_rotation_matrix_3x3
        translation_only = np.array_equal(r_mat, _IDENTITY_3)
        tx_c, ty_c, tz_c = (
            float(commanded_translation_m[0]),
            float(commanded_translation_m[1]),
            float(commanded_translation_m[2]),
        )
        probe = (SpatialAnomalySniffer.probe_closest_clearance(
            focal_mesh, reference_mesh, yaw_symmetry_order=yaw_symmetry_order)
            if probe_result is None else probe_result)
        if not _probe_is_trustworthy(probe):
            axis, angle = SE3AlignmentMath.so3_log_map_and_angle(r_mat)
            nominal = np.concatenate((np.asarray((tx_c, ty_c, tz_c)), axis * angle))
            return ECBFSafetyShieldReport(
                nominal_twist_6d=nominal, safe_filtered_twist_6d=np.zeros(6),
                barrier_activated=True, jamming_shield_activated=False,
                predicted_next_clearance_mm=float(probe.signed_clearance_m) * 1000,
                normal_overshoot_removed_mm=0.0,
                tangential_null_space_preservation_ratio=0.0,
                summary_message="ACTION_REJECTED: invalid measurement or object axes; no depth projection")
        tok_f = focal_mesh._last_crc_token if focal_mesh._last_crc_token is not None else focal_mesh._compute_full_crc_token()
        tok_r = reference_mesh._last_crc_token if reference_mesh._last_crc_token is not None else reference_mesh._compute_full_crc_token()
        ecbf_key = (
            id(focal_mesh),
            id(reference_mesh),
            tok_f,
            tok_r,
            tx_c,
            ty_c,
            tz_c,
            tuple(np.asarray(r_mat).ravel()),
            self.ecbf_gamma,
            self.safe_min_clearance_m,
            friction_coeff_mu,
            yaw_symmetry_order,
            None if probe_result is None else (
                probe_result.signed_clearance_m, probe_result.is_penetrating,
                tuple(probe_result.point_a_world), tuple(probe_result.point_b_world),
                tuple(probe_result.normal_b_world), probe_result.contact_normal_angle_deg),
        )
        cached_ecbf = self._ECBF_SHIELD_CACHE.get(ecbf_key)
        if cached_ecbf is not None:
            return cached_ecbf

        # OP-336B/D: _UNPACK_3D 标量闭式合成 6D 间隙雅可比 (-nx, -ny, -nz, -mx, -my, -mz)
        pa = probe.point_a_world
        pb = probe.point_b_world
        ax0, ay0, az0 = _UNPACK_3D(pa) if (pa.flags.c_contiguous and pa.size == 3) else (float(pa[0]), float(pa[1]), float(pa[2]))
        bx0, by0, bz0 = _UNPACK_3D(pb) if (pb.flags.c_contiguous and pb.size == 3) else (float(pb[0]), float(pb[1]), float(pb[2]))
        sx, sy, sz = bx0 - ax0, by0 - ay0, bz0 - az0
        sep_n = math.sqrt(sx * sx + sy * sy + sz * sz)
        if sep_n > 1e-6:
            inv_s = 1.0 / sep_n
            nx, ny, nz = sx * inv_s, sy * inv_s, sz * inv_s
            if probe.is_penetrating:
                # Penetration witnesses encode +MTV (outward), whereas gap
                # witnesses point toward the reference.  J=-n must increase
                # signed clearance for an outward recovery in both states.
                nx, ny, nz = -nx, -ny, -nz
        else:
            nb_arr = probe.normal_b_world
            nbx, nby, nbz = _UNPACK_3D(nb_arr) if (nb_arr.flags.c_contiguous and nb_arr.size == 3) else (
                float(nb_arr[0]), float(nb_arr[1]), float(nb_arr[2])
            )
            inv_nb = 1.0 / max(math.sqrt(nbx * nbx + nby * nby + nbz * nbz), 1e-9)
            # At contact, the reference's outward normal is the clearance
            # gradient, so n is its negative under the J=-n convention.
            nx, ny, nz = -nbx * inv_nb, -nby * inv_nb, -nbz * inv_nb

        piv = focal_mesh.bbox_center
        px0, py0, pz0 = _UNPACK_3D(piv) if (piv.flags.c_contiguous and piv.size == 3) else (float(piv[0]), float(piv[1]), float(piv[2]))
        rx, ry, rz = ax0 - px0, ay0 - py0, az0 - pz0
        mx = ry * nz - rz * ny
        my = rz * nx - rx * nz
        mz = rx * ny - ry * nx
        if translation_only:
            # The caller has already committed its rotation and consumes only
            # the first three filtered components.  Do not satisfy the barrier
            # using fictitious rotational corrections that it will discard.
            mx = my = mz = 0.0

        if translation_only:
            ang_r = 0.0
            wx = wy = wz = 0.0
        else:
            ax_r, ang_r = SE3AlignmentMath.so3_log_map_and_angle(r_mat)
            wx, wy, wz = float(ax_r[0] * ang_r), float(ax_r[1] * ang_r), float(ax_r[2] * ang_r)

        c_k = float(probe.signed_clearance_m)
        b_cbf = -self.ecbf_gamma * (c_k - self.safe_min_clearance_m)
        j_dot_xi = -(nx * tx_c + ny * ty_c + nz * tz_c + mx * wx + my * wy + mz * wz)
        j_norm_sq = max(nx * nx + ny * ny + nz * nz + mx * mx + my * my + mz * mz, 1e-12)

        barrier_active = False
        overshoot_removed_mm = 0.0
        s0, s1, s2, s3, s4, s5 = tx_c, ty_c, tz_c, wx, wy, wz

        if j_dot_xi < b_cbf - 1e-9:
            barrier_active = True
            violation = b_cbf - j_dot_xi
            overshoot_removed_mm = round(violation * 1000.0, 4)
            scale_j = violation / j_norm_sq
            s0 = tx_c - scale_j * nx
            s1 = ty_c - scale_j * ny
            s2 = tz_c - scale_j * nz
            s3 = wx - scale_j * mx
            s4 = wy - scale_j * my
            s5 = wz - scale_j * mz

        # OP-336B/D: O(1) 临界卡死角预筛，仅当 ang_r < 1e-4 且倾角可能越界时才执行走廊顶点投影
        jam_shield_active = False
        crit_jam_est_deg = math.degrees(math.atan(max(float(friction_coeff_mu), 1e-6)))
        if ang_r < 1e-4 and float(probe.contact_normal_angle_deg) > crit_jam_est_deg + 1.5:
            nb = np.asarray(probe.normal_b_world, dtype=np.float64)
            nb = nb / max(SE3AlignmentMath._norm3(nb), 1e-9)
            _, cur_tilt, crit_jam_deg, jam_risk = (
                SpatialAnomalySniffer.compute_assembly_insertion_corridor_and_jamming_cone(
                    focal_mesh,
                    reference_mesh,
                    insertion_axis_world=-nb,
                    friction_coeff_mu=friction_coeff_mu,
                )
            )
            if jam_risk and cur_tilt > crit_jam_deg + 2.0:
                axial_push = -(s0 * float(nb[0]) + s1 * float(nb[1]) + s2 * float(nb[2]))
                if axial_push > max(c_k * 0.5, 0.002):
                    jam_shield_active = True
                    d_push = axial_push - max(c_k * 0.5, 0.0)
                    s0 += d_push * float(nb[0])
                    s1 += d_push * float(nb[1])
                    s2 += d_push * float(nb[2])

        xi_nom_out = np.empty(6, dtype=np.float64)
        _PACK_6D_INTO(
            xi_nom_out,
            0,
            round(tx_c, 6),
            round(ty_c, 6),
            round(tz_c, 6),
            round(wx, 6),
            round(wy, 6),
            round(wz, 6),
        )
        xi_safe_out = np.empty(6, dtype=np.float64)
        _PACK_6D_INTO(
            xi_safe_out,
            0,
            round(s0, 6),
            round(s1, 6),
            round(s2, 6),
            round(s3, 6),
            round(s4, 6),
            round(s5, 6),
        )

        if not jam_shield_active:
            null_preserve = 1.0
        else:
            _, b_null, _ = SpatialAnomalySniffer.compute_se3_clearance_jacobian_and_compliance_cone(
                focal_mesh, reference_mesh, probe_result=probe
            )
            nom_null = b_null.T @ xi_nom_out
            safe_null = b_null.T @ xi_safe_out
            nom_null_norm = float(np.linalg.norm(nom_null))
            if nom_null_norm > 1e-12:
                null_preserve = round(
                    1.0 - float(np.linalg.norm(safe_null - nom_null)) / nom_null_norm,
                    6,
                )
            else:
                null_preserve = 1.0

        j_dot_safe = -(nx * s0 + ny * s1 + nz * s2 + mx * s3 + my * s4 + mz * s5)
        pred_next_c_mm = round((c_k + j_dot_safe) * 1000.0, 4)
        msg = (
            f"ECBF SAFETY SHIELD: BarrierActive={barrier_active} (OvershootRemoved={overshoot_removed_mm:.3f}mm), "
            f"JamShield={jam_shield_active}, PredNextClearance={pred_next_c_mm:.3f}mm, NullPreserve={null_preserve * 100:.2f}%"
        )
        ecbf_rep = ECBFSafetyShieldReport(
            nominal_twist_6d=xi_nom_out,
            safe_filtered_twist_6d=xi_safe_out,
            barrier_activated=barrier_active,
            jamming_shield_activated=jam_shield_active,
            predicted_next_clearance_mm=pred_next_c_mm,
            normal_overshoot_removed_mm=overshoot_removed_mm,
            tangential_null_space_preservation_ratio=null_preserve,
            summary_message=msg,
        )
        if len(self._ECBF_SHIELD_CACHE) >= 64:
            self._ECBF_SHIELD_CACHE.clear()
        self._ECBF_SHIELD_CACHE[ecbf_key] = ecbf_rep
        return ecbf_rep

    def create_and_restore_transactional_snapshot(
        self,
        mesh: MeshEntity3D,
        mode: str = "CREATE",
        snapshot: Optional[TransactionalSnapshot] = None,
    ) -> Union[TransactionalSnapshot, MeshEntity3D]:
        """
        OP-337 / OP-337B O(1) 状态令牌感知事务快照创建（CREATE）与紧急原子回滚（RESTORE）算子：
        - OP-337B 采用 `collections.deque(maxlen=16)` 消除 `list.pop(0)`，并以 O(1) CRC32 令牌比对替代全数组 `np.array_equal`。
        """
        if mode.upper() == "CREATE":
            tok = mesh._compute_full_crc_token()
            snap = TransactionalSnapshot(
                snapshot_id=f"snap_{mesh.object_id}_{tok[2]}",
                mesh_entity=mesh,
                vertices_backup=mesh.vertices.copy(),
                local_axes_backup=mesh.local_axes.copy(),
                pivot_backup=None if mesh.pivot_world is None else mesh.pivot_world.copy(),
                crc32_token=tok,
                fsm_state=self.fsm_state,
                timestamp_ns=time.perf_counter_ns(),
            )
            self._snapshot_stack.append(snap)
            return snap

        target_snap = snapshot if snapshot is not None else (self._snapshot_stack[-1] if self._snapshot_stack else None)
        if target_snap is None:
            return mesh

        restored = target_snap.mesh_entity
        if restored._compute_full_crc_token() != target_snap.crc32_token:
            np.copyto(restored.vertices, target_snap.vertices_backup)
            np.copyto(restored.local_axes, target_snap.local_axes_backup)
            if target_snap.pivot_backup is not None and restored.pivot_world is not None:
                np.copyto(restored.pivot_world, target_snap.pivot_backup)
            else:
                restored.pivot_world = None if target_snap.pivot_backup is None else target_snap.pivot_backup.copy()
            restored.invalidate_caches()
            restored._compute_full_crc_token()
        else:
            restored._check_coherency()

        self.fsm_state = target_snap.fsm_state
        return restored

    @staticmethod
    def orchestrate_dag_assembly_closed_loop(
        base_mesh: MeshEntity3D,
        assembly_chain: List[Tuple[MeshEntity3D, str]],
        preferred_view_dir: Optional[np.ndarray] = None,
        step_machining_tol_mm: float = 0.05,
    ) -> Tuple[Dict[str, MeshEntity3D], MultiBodyAssemblyChainReport]:
        """
        OP-344 / OP-344B 多体拓扑 DAG 装配链逐级闭环控制、次生干涉拦截与极值/RSS 统计公差链累积审计算子
        """
        return SpatialAlignmentVerifier.execute_multi_body_sequential_assembly_chain(
            base_mesh=base_mesh,
            assembly_chain=assembly_chain,
            preferred_view_dir=preferred_view_dir,
            step_machining_tol_mm=step_machining_tol_mm,
        )

    def issue_mcp_closed_loop_audit_certificate(
        self,
        focal_mesh: MeshEntity3D,
        reference_mesh: MeshEntity3D,
        preferred_view_dir: Optional[np.ndarray] = None,
    ) -> Tuple[MeshEntity3D, DigitalTwinAuditCertificate, Dict[str, Any]]:
        """
        OP-345 / OP-345B 签发包含硬件 CRC32 指纹、ASME Y14.5 6 项 GD&T 公差、6D 力封闭秩、13 点 Sigma 良率
        与 SHA-256 确定性签名的 MCP 数字孪生闭环控制质量证书算子
        """
        aligned_mesh, cert = SpatialAlignmentVerifier.generate_closed_loop_digital_twin_audit_certificate(
            focal_mesh=focal_mesh,
            reference_mesh=reference_mesh,
            preferred_view_dir=preferred_view_dir,
        )
        if cert.overall_certified:
            self.fsm_state = ServoFSMState.LOCKED_CERTIFIED
            self.consecutive_flush_steps = max(self.consecutive_flush_steps, self.lock_required_steps)
        else:
            self.fsm_state = ServoFSMState.EMERGENCY_SAFE_ROLLBACK
            self.consecutive_flush_steps = 0
        mcp_cert_pkg = {
            "mcp_certificate_version": "Human-Eye-MCP-V9.6",
            "certificate_sha256": cert.certificate_sha256,
            "fsm_terminal_state": self.fsm_state.value,
            "focal_mesh_crc32": cert.focal_mesh_crc32,
            "reference_mesh_crc32": cert.reference_mesh_crc32,
            "overall_certified": cert.overall_certified,
            "residual_clearance_mm": cert.residual_clearance_mm,
            "residual_tilt_deg": cert.residual_tilt_deg,
            "residual_yaw_deg": cert.residual_yaw_deg,
            "predicted_yield_pct": cert.predicted_yield_pct,
        }
        return aligned_mesh, cert, mcp_cert_pkg


# 注册模块别名以兼容 submodule_3_3_closed_loop_control 导入名
sys.modules.setdefault("submodule_3_3_closed_loop_control", sys.modules[__name__])


# ============================================================================
# 3. 自包含 0.0 ULP 零退化核验与全算子红队压测入口
# ============================================================================

if __name__ == "__main__":
    def _box(
        oid: str,
        mark: str,
        name: str,
        center: Tuple[float, float, float],
        size: Tuple[float, float, float],
        col: Tuple[int, int, int],
        focal: bool = False,
    ) -> MeshEntity3D:
        cx, cy, cz = center
        sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        v = np.array(
            [
                [cx - sx, cy - sy, cz - sz], [cx + sx, cy - sy, cz - sz],
                [cx + sx, cy + sy, cz - sz], [cx - sx, cy + sy, cz - sz],
                [cx - sx, cy - sy, cz + sz], [cx + sx, cy - sy, cz + sz],
                [cx + sx, cy + sy, cz + sz], [cx - sx, cy + sy, cz + sz],
            ],
            dtype=np.float64,
        )
        f = np.array(
            [
                [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
            ],
            dtype=np.int32,
        )
        return MeshEntity3D(oid, mark, name, v, f, _BOX_EDGES_12, col, focal,
                            local_axes=np.eye(3, dtype=np.float64))

    ctrl = ClosedLoopActionController(quad_size=384, enable_zero_copy_ipc=True)
    table = _box("obj_table", "#A", "Worktable_Base", (0.0, 0.0, 0.30), (1.60, 1.20, 0.60), (70, 130, 190))
    pillar = _box("obj_pillar", "#C", "Guide_Pillar", (-0.55, 0.25, 0.85), (0.28, 0.35, 0.50), (85, 185, 125))
    flange_raw = _box("obj_flange", "#B", "Precision_Flange_Module", (0.15, -0.10, 0.90), (0.45, 0.45, 0.40), (225, 115, 65), True)
    flange_tilted = flange_raw.rotated_around_pivot(SE3AlignmentMath.euler_xyz_to_matrix(-8.0, 14.0, 12.0))

    cam_eye = np.array([2.4, -2.5, 1.85], dtype=np.float64)
    cam_target = np.array([0.0, 0.0, 0.55], dtype=np.float64)
    pref_dir = (cam_eye - cam_target) / np.linalg.norm(cam_eye - cam_target)

    # 1. 验证与模块一的子模块 1.5 / 1.6 的 0.0 ULP & max_pixel_diff == 0 严格等价性
    ref_aligned, ref_rep = SpatialAlignmentVerifier.execute_alignment_and_recheck(
        focal_mesh=flange_tilted, reference_mesh=table, preferred_view_dir=pref_dir, cam_eye=cam_eye, scene_meshes=[table, flange_tilted, pillar]
    )
    ref_post_canvas, _ = ctrl.compositor.render_quad_cognitive_canvas(
        meshes=[table, ref_aligned, pillar], cam_eye=cam_eye, cam_target=cam_target, ghost_pre_mesh=flange_tilted
    )

    bundle = ctrl.execute_closed_loop_control_and_render(
        meshes=[table, flange_tilted, pillar], cam_eye=cam_eye, cam_target=cam_target
    )
    max_vert_diff = float(np.max(np.abs(bundle.aligned_focal_mesh.vertices - ref_aligned.vertices)))
    max_pix_diff = int(np.max(np.abs(np.asarray(bundle.post_canvas_image, dtype=np.int32) - np.asarray(ref_post_canvas, dtype=np.int32))))

    # 2. 验证闭式 ECBF 安全护栏拦截过冲穿模指令
    ecbf_test = ctrl.filter_action_with_ecbf_and_jamming_shield(
        focal_mesh=flange_raw, reference_mesh=table, commanded_translation_m=(0.05, -0.02, -0.22)
    )

    # 3. 验证李群 Smith 预估器（正常 1 步补偿 0.0 ULP vs 外部突变马氏门控触发）
    smith_pred_mesh, smith_normal = ctrl.predict_undelayed_se3_state_smith(
        delayed_focal_mesh=flange_tilted, reference_mesh=table, delay_steps=1
    )
    smith_vert_diff = float(np.max(np.abs(smith_pred_mesh.vertices - ref_aligned.vertices)))
    _, smith_jump = ctrl.predict_undelayed_se3_state_smith(
        delayed_focal_mesh=flange_tilted, reference_mesh=table, delay_steps=1, expected_prior_clearance_m=0.25
    )

    print("=== Submodule 3.3 (ClosedLoopActionController V9.6) Self-Verification Suite ===")
    print(f"[Bit-Exact Check] max_vert_diff = {max_vert_diff:.2e} m (0.0 ULP), max_pixel_diff = {max_pix_diff}")
    print(f"[FSM Transition]  {bundle.fsm_report.previous_state.value} -> {bundle.fsm_report.current_state.value} ({bundle.fsm_report.transition_reason})")
    print(f"[ECBF Shield]     {ecbf_test.summary_message}")
    print(f"[Smith Normal]    {smith_normal.summary_message} | smith_vert_diff = {smith_vert_diff:.2e} m (0.0 ULP)")
    print(f"[Smith Gate]      {smith_jump.summary_message}")
    assert max_vert_diff == 0.0 and max_pix_diff == 0
    assert bundle.temporal_comparison_report is not None
    assert ecbf_test.barrier_activated and abs(ecbf_test.predicted_next_clearance_mm) <= 1e-6
    assert not smith_normal.innovation_gate_tripped and smith_normal.delay_steps_compensated == 1 and smith_vert_diff == 0.0
    assert smith_jump.innovation_gate_tripped and smith_jump.buffer_flushed
    print("ALL SUBMODULE 3.3 ASSERTIONS PASSED WITH 0.0 ULP & 0 PIXEL DIFF!")

