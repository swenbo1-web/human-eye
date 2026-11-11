"""P0 结构修复：网格实体与结果契约的单一真源位于 human_eye_foveated_renderer。

本文件不再重复定义，仅做再导出，避免"同名不同类"导致 isinstance / hasattr 失效。
"""
from human_eye_foveated_renderer import (  # noqa: F401
    ClosedLoopRecheckReport,
    MeshEntity3D,
    SpatialClearanceProbeResult,
    _fast_bbox_min_max,
)

__all__ = [
    "MeshEntity3D",
    "SpatialClearanceProbeResult",
    "ClosedLoopRecheckReport",
    "_fast_bbox_min_max",
]
