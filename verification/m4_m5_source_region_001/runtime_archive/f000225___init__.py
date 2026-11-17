"""Canonical geometry operators with lazy product-layer compatibility exports.

Geometry imports do not eagerly import controllers that themselves depend on
this package. Genuine import errors propagate when an exported name is used.
"""

import importlib as _importlib

from .submodule_1_1_mesh_entity import MeshEntity3D, SpatialClearanceProbeResult, ClosedLoopRecheckReport
from .submodule_1_2_sub_frustum_gaze import SubFrustumMathEngine
from .submodule_1_3_se3_alignment_math import SE3AlignmentMath
from .submodule_1_4_spatial_sniffer import SpatialAnomalySniffer
from .submodule_1_5_alignment_verifier import SpatialAlignmentVerifier
from .submodule_1_6_quad_compositor import QuadCognitiveCanvasCompositor

_EXPORT_GROUPS = {'.native_3d_spatial_scratchpad': ['AdaptiveSE3TrajectorySubdivider',
                                   'BatchGeometricPredicateVerifier',
                                   'InstanceVerificationReport',
                                   'LocusContactFeature',
                                   'MultiDatumJointSE3Prescription',
                                   'SpatialScratchpadFrame',
                                   'SpatialScratchpadRingBuffer',
                                   'SphericalIoRMultiLocusSniffer',
                                   'StepDeltaAuditReport',
                                   'TrajectoryWindowSweepReport'],
 'module_2_low_token_mcp_scene_bridge': ['BinarySharedMemoryFrameBus',
                                         'ChiralityConversionReport',
                                         'CompactScenePatchDSLSerializer',
                                         'DualEngineChiralityBridge',
                                         'DualEngineHostCodeGenerator',
                                         'HorizonFilteredSceneState',
                                         'LOW_TOKEN_MCP_BRIDGE_TOOLS_SCHEMA',
                                         'LowTokenMCPBridgeServer',
                                         'MerkleDAGSceneStateTracker',
                                         'MerkleNodeDigest',
                                         'MerkleSceneDeltaReport',
                                         'MortonMacroClusterToken',
                                         'ScenePatchDSLPackage',
                                         'ShadowTransactionCommitReport',
                                         'TaskConditionedHorizonFilter',
                                         'TransactionalShadowLayerManager'],
 'module_3_1_mcp_protocol_ipc_engine': ['DeterministicJsonRpcScanner',
                                        'LockFreeSpscBipRingBuffer',
                                        'McpErrorCode',
                                        'McpProtocolEngine',
                                        'McpSessionState',
                                        'McpTelemetryHealthReport',
                                        'ParsedJsonRpcEnvelope',
                                        'TensorSlotDescriptor',
                                        'ZeroCopyMcpFrame',
                                        'ZeroCopyTensorArena'],
 'module_3_2_vlm_grounding_closed_loop_agent': ['AgentStepExecutionRecord',
                                                'AutonomousClosedLoopEpisodeReport',
                                                'CompactGroundingPromptBundle',
                                                'MultimodalMessagePayload',
                                                'ParsedVLMToolCall',
                                                'SoMPixelAnchorEntry',
                                                'VLMGroundingEvaluationMetrics',
                                                'VLMHallucinationAuditReport',
                                                'VLMSpatialGroundingAndClosedLoopAgent'],
 'module_3_3_closed_loop_control_engine': ['ClosedLoopActionController',
                                           'ClosedLoopVisualExecutionBundle',
                                           'ECBFSafetyShieldReport',
                                           'FSMTransitionReport',
                                           'MCPActionPrescriptionPayload',
                                           'MultiStepServoSessionReport',
                                           'QuantizerResidualReport',
                                           'ServoFSMState',
                                           'SmithPredictorReport',
                                           'TransactionalSnapshot']}
_EXPORT_MODULES = {name: module for module, names in _EXPORT_GROUPS.items() for name in names}
__all__ = ['MeshEntity3D', 'SpatialClearanceProbeResult', 'ClosedLoopRecheckReport', 'SubFrustumMathEngine', 'SE3AlignmentMath', 'SpatialAnomalySniffer', 'SpatialAlignmentVerifier', 'QuadCognitiveCanvasCompositor'] + list(_EXPORT_MODULES)


def __getattr__(name):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = _importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
