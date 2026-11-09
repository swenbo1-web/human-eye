"""Human-Eye (人类之眼) 核心计算层 — 子模块 1.3：李群 SO(3)/SE(3) 计算架构（再导出层）

本模块**不再保留实现副本**。唯一真源位于 ``human_eye_foveated_renderer``，
本文件仅做再导出，以保证 ``from ...submodule_1_3_se3_alignment_math import X``
与 ``from human_eye_foveated_renderer import X`` 拿到**同一个对象**。

为什么真源放在单体而不是包内（与其他子模块不同）：
    该类是探针、渲染与闭环求解的热路径核心。单体内部调用点有 100 余处，
    ``_cross3`` / ``_norm3`` 直接出现在 GJK / EPA 内层迭代里。
    实测「惰性访问器」每次调用多约 52 ns（Python 函数调用 + 全局查找），
    在探针路径上单次约 8–9 次调用（~0.5 µs），在多边形内层循环中会被放大。
    因此这里选择「真源留在原地 + 本模块再导出」，做到**零调用开销**，
    而重复副本依然被消除（全项目只剩一份实现）。

历史实现要点（详细推导见 ``human_eye_foveated_renderer.SE3AlignmentMath`` 的
类与方法 docstring，本节仅列结论）：
    1. 标量几何基元：预编译 ``struct.Struct('=3d')`` C-Buffer 零列表解包与原位打包，
       叉积较 ``np.cross`` 提速 45.3x；范数严守 ``math.sqrt(v0*v0+v1*v1+v2*v2)``
       求值轨迹（已证伪 ``math.hypot`` 缩放引起的 3.55e-15 / 8 ULP 漂移），均 0.0 ULP。
    2. 李群旋转与全标架消扭：欧拉角合成走 ``R_z @ R_y`` 零加法解析预乘 +
       ``_PACK_9D_INTO`` 零下标直写，热态记忆化提速 48.0x。
    3. 批量算子：``_batch_matvec`` 走 C-gufunc ``(mats @ vecs[:, :, None])[..., 0]``，
       严格对齐标量路径的 OpenBLAS/AVX2 FMA 舍入轨迹，保持 0.0 ULP 逐位恒等。
"""

from human_eye_foveated_renderer import (  # noqa: F401
    SE3AlignmentMath,
    _IDENTITY_9_TUPLE,
    _PACK_3D_INTO,
    _PACK_6D_INTO,
    _PACK_9D_INTO,
    _PACK_16D_INTO,
    _STRUCT_3D,
    _STRUCT_6D,
    _STRUCT_9D,
    _STRUCT_16D,
    _UNPACK_3D,
    _UNPACK_6D,
    _UNPACK_9D,
    _UNPACK_16D,
    _batch_matvec,
)

__all__ = [
    "SE3AlignmentMath",
    "_batch_matvec",
    "_IDENTITY_9_TUPLE",
    "_PACK_3D_INTO",
    "_PACK_6D_INTO",
    "_PACK_9D_INTO",
    "_PACK_16D_INTO",
    "_STRUCT_3D",
    "_STRUCT_6D",
    "_STRUCT_9D",
    "_STRUCT_16D",
    "_UNPACK_3D",
    "_UNPACK_6D",
    "_UNPACK_9D",
    "_UNPACK_16D",
]
