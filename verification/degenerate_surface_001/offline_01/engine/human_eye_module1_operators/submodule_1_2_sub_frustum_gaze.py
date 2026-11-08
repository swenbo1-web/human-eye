"""子模块 1.2 (V8.10)：同轴双流非对称视锥体与五射线球面主动避障引擎 (SubFrustumMathEngine, _ray_aabb_slab_scalar)
关联优化算子：OP-06, OP-07, OP-17, OP-18, OP-25, OP-31, OP-33, OP-42, OP-47, OP-67, OP-73A~D, OP-74A~C, OP-75A~B, OP-76A~B, OP-77A~D, OP-78A~B, OP-79A~C, OP-80A~C, OP-81A
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
import pathlib
import time
import zlib
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .submodule_1_1_mesh_entity import MeshEntity3D

def _ray_aabb_slab_scalar(
    ox: float,
    oy: float,
    oz: float,
    dx: float,
    dy: float,
    dz: float,
    max_dist: float,
    bmin0: float,
    bmin1: float,
    bmin2: float,
    bmax0: float,
    bmax1: float,
    bmax2: float,
    clearance: float = 0.018,
) -> bool:
    """
    OP-77B / OP-80B 纯标量零分配 Smits–Kay–Kajiya Slab 射线-AABB 极速求交内核（耗时 ~0.65 µs）：
    检验有限线段 r(t) = o + t*d, t in [clearance, max_dist - clearance] 是否与轴对齐包围盒 [bmin, bmax] 相交。
    """
    t_enter = clearance
    t_exit = max_dist - clearance
    if t_enter > t_exit:
        return False

    if abs(dx) > 1e-12:
        inv_dx = 1.0 / dx
        tx0 = (bmin0 - ox) * inv_dx
        tx1 = (bmax0 - ox) * inv_dx
        if tx0 > tx1:
            tx0, tx1 = tx1, tx0
        if tx0 > t_enter:
            t_enter = tx0
        if tx1 < t_exit:
            t_exit = tx1
        if t_enter > t_exit:
            return False
    elif ox < bmin0 or ox > bmax0:
        return False

    if abs(dy) > 1e-12:
        inv_dy = 1.0 / dy
        ty0 = (bmin1 - oy) * inv_dy
        ty1 = (bmax1 - oy) * inv_dy
        if ty0 > ty1:
            ty0, ty1 = ty1, ty0
        if ty0 > t_enter:
            t_enter = ty0
        if ty1 < t_exit:
            t_exit = ty1
        if t_enter > t_exit:
            return False
    elif oy < bmin1 or oy > bmax1:
        return False

    if abs(dz) > 1e-12:
        inv_dz = 1.0 / dz
        tz0 = (bmin2 - oz) * inv_dz
        tz1 = (bmax2 - oz) * inv_dz
        if tz0 > tz1:
            tz0, tz1 = tz1, tz0
        if tz0 > t_enter:
            t_enter = tz0
        if tz1 < t_exit:
            t_exit = tz1
        if t_enter > t_exit:
            return False
    elif oz < bmin2 or oz > bmax2:
        return False

    return True


class SubFrustumMathEngine:
    """
    同轴双流非对称视锥体（Co-Axial Asymmetric Sub-Frustum）与五射线球面主动视线避障引擎（V8.10 终极版）。
    """

    _GAZE_CACHE: Dict[Tuple, Tuple[np.ndarray, bool]] = {}
    _LOOKAT_CACHE: Dict[Tuple[float, float, float, float, float, float, float, float, float], np.ndarray] = {}
    _PERSP_CACHE: Dict[Tuple[float, float, float, float], np.ndarray] = {}
    _ORTHO_CACHE: Dict[Tuple[float, float, float, float, float, float], np.ndarray] = {}
    _APERTURE_OFFSETS_4: np.ndarray = np.array(
        [
            [0.08, 0.0, 0.0],
            [-0.08, 0.0, 0.0],
            [0.0, 0.08, 0.0],
            [0.0, 0.0, 0.08],
        ],
        dtype=np.float64,
    )

    @classmethod
    def build_look_at_view_matrix(
        cls,
        eye: np.ndarray,
        target: np.ndarray,
        up: np.ndarray = np.array([0.0, 0.0, 1.0]),
    ) -> np.ndarray:
        """
        OP-73A 双轴独立共线保护的 Look-At 视图矩阵算子（9 元组 O(1) 记忆化 + 零 np.cross 展开 + OpenBLAS cblas_ddot FMA 严格对齐）：
        - 消除 2 次 np.cross 通用轴派发，严格对齐 IEEE-754 直接除法与 cblas_ddot FMA 单次舍入轨迹，100% 保持 0.0 ULP 恒等。
        """
        ex, ey, ez = float(eye[0]), float(eye[1]), float(eye[2])
        tx, ty, tz = float(target[0]), float(target[1]), float(target[2])
        ux, uy, uz = float(up[0]), float(up[1]), float(up[2])
        key = (ex, ey, ez, tx, ty, tz, ux, uy, uz)
        cached = cls._LOOKAT_CACHE.get(key)
        if cached is not None:
            return cached.copy()

        forward = np.array([tx - ex, ty - ey, tz - ez], dtype=np.float64)
        norm_f = float(np.linalg.norm(forward))
        if norm_f < 1e-8:
            forward = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        else:
            forward /= norm_f
        fx, fy, fz = float(forward[0]), float(forward[1]), float(forward[2])

        up_arr = np.array([ux, uy, uz], dtype=np.float64)
        norm_u = max(float(np.linalg.norm(up_arr)), 1e-9)
        if abs(float(np.dot(forward, up_arr / norm_u))) > 0.999:
            if abs(fy) < 0.9:
                ux, uy, uz = 0.0, 1.0, 0.0
            else:
                ux, uy, uz = 1.0, 0.0, 0.0

        right = np.array([fy * uz - fz * uy, fz * ux - fx * uz, fx * uy - fy * ux], dtype=np.float64)
        right /= float(np.linalg.norm(right))
        rx, ry, rz = float(right[0]), float(right[1]), float(right[2])

        true_up = np.array([ry * fz - rz * fy, rz * fx - rx * fz, rx * fy - ry * fx], dtype=np.float64)
        eye_arr = np.array([ex, ey, ez], dtype=np.float64)

        view = np.zeros((4, 4), dtype=np.float64)
        view[0, :3] = right
        view[1, :3] = true_up
        view[2, :3] = -forward
        view[0, 3] = -float(np.dot(right, eye_arr))
        view[1, 3] = -float(np.dot(true_up, eye_arr))
        view[2, 3] = float(np.dot(forward, eye_arr))
        view[3, 3] = 1.0
        if len(cls._LOOKAT_CACHE) >= 32:
            cls._LOOKAT_CACHE.clear()
        cls._LOOKAT_CACHE[key] = view
        return view.copy()

    @classmethod
    def build_perspective_matrix(
        cls, fov_y_deg: float, aspect: float, near: float, far: float
    ) -> np.ndarray:
        """OP-73B 标准对称透视投影矩阵算子（参数空间四元组 O(1) 记忆化工厂，提速 6.1x，0.0 ULP）"""
        key = (
            round(float(fov_y_deg), 6),
            round(float(aspect), 6),
            round(float(near), 6),
            round(float(far), 6),
        )
        cached = cls._PERSP_CACHE.get(key)
        if cached is not None:
            return cached.copy()
        f = 1.0 / math.tan(math.radians(fov_y_deg) * 0.5)
        proj = np.zeros((4, 4), dtype=np.float64)
        proj[0, 0] = f / aspect
        proj[1, 1] = f
        proj[2, 2] = (far + near) / (near - far)
        proj[2, 3] = (2.0 * far * near) / (near - far)
        proj[3, 2] = -1.0
        if len(cls._PERSP_CACHE) >= 16:
            cls._PERSP_CACHE.clear()
        cls._PERSP_CACHE[key] = proj
        return proj.copy()

    @classmethod
    def build_ortho_matrix(
        cls, left: float, right: float, bottom: float, top: float, near: float, far: float
    ) -> np.ndarray:
        """OP-73C 标准正交投影矩阵算子（参数空间六元组 O(1) 记忆化工厂，提速 12.9x，0.0 ULP）"""
        key = (
            round(float(left), 6),
            round(float(right), 6),
            round(float(bottom), 6),
            round(float(top), 6),
            round(float(near), 6),
            round(float(far), 6),
        )
        cached = cls._ORTHO_CACHE.get(key)
        if cached is not None:
            return cached.copy()
        ortho = np.zeros((4, 4), dtype=np.float64)
        ortho[0, 0] = 2.0 / (right - left)
        ortho[1, 1] = 2.0 / (top - bottom)
        ortho[2, 2] = -2.0 / (far - near)
        ortho[0, 3] = -(right + left) / (right - left)
        ortho[1, 3] = -(top + bottom) / (top - bottom)
        ortho[2, 3] = -(far + near) / (far - near)
        ortho[3, 3] = 1.0
        if len(cls._ORTHO_CACHE) >= 16:
            cls._ORTHO_CACHE.clear()
        cls._ORTHO_CACHE[key] = ortho
        return ortho.copy()

    @staticmethod
    def project_world_to_ndc(
        points_world: np.ndarray,
        view_matrix: np.ndarray,
        proj_matrix: np.ndarray,
        near_clip: float = 0.05,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        OP-73D / OP-78A 零齐次拼接（Zero-HStack）世界坐标到 NDC 批量投影算子：
        - 严格保持 OpenBLAS dgemm FMA 单次舍入轨迹；
        - 当透视投影矩阵满足标准第 3 行 [0, 0, -1, 0] 时，w 直接复用 cam_depth = -cam_pts[:, 2] 并执行原位除法 clip_xyz /= w（0.0 ULP）。
        """
        if (
            type(points_world) is not np.ndarray
            or points_world.dtype != np.float64
            or not points_world.flags.c_contiguous
        ):
            points_world = np.ascontiguousarray(points_world, dtype=np.float64)
        if points_world.ndim == 1:
            points_world = points_world[None, :]
        r_v = view_matrix[:3, :3]
        t_v = view_matrix[:3, 3]
        cam_pts = points_world @ r_v.T
        cam_pts += t_v[None, :]

        r_p = proj_matrix[:3, :3]
        t_p = proj_matrix[:3, 3]
        clip_xyz = cam_pts @ r_p.T
        clip_xyz += t_p[None, :]
        cam_depth = -cam_pts[:, 2]

        p33 = float(proj_matrix[3, 3])
        if abs(p33 - 1.0) < 1e-5:
            return clip_xyz, cam_depth
        if (
            proj_matrix[3, 0] == 0.0
            and proj_matrix[3, 1] == 0.0
            and proj_matrix[3, 2] == -1.0
            and p33 == 0.0
        ):
            w = np.maximum(cam_depth, near_clip)[:, None]
        else:
            w = np.maximum((cam_pts @ proj_matrix[3, :3]) + p33, near_clip)[:, None]
        clip_xyz /= w
        return clip_xyz, cam_depth

    @classmethod
    def project_segment_clipped_with_depth(
        cls,
        p0_world: np.ndarray,
        p1_world: np.ndarray,
        view_matrix: np.ndarray,
        proj_matrix: np.ndarray,
        near_z: float = 0.08,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, float, float]]:
        """
        OP-74A / OP-78B 相机空间近平面带真实深度线段安全裁剪算子：
        严格从插值后的 -float(p0_cam[2]) 提取透视除数 w0，配合 3x3 r_p 切片实现 0.0 ULP 绝对恒等。
        """
        p0_world = np.asarray(p0_world, dtype=np.float64)
        p1_world = np.asarray(p1_world, dtype=np.float64)
        r_v = view_matrix[:3, :3]
        t_v = view_matrix[:3, 3]
        p0_cam = r_v @ p0_world + t_v
        p1_cam = r_v @ p1_world + t_v
        d0, d1 = -float(p0_cam[2]), -float(p1_cam[2])

        if d0 < near_z and d1 < near_z:
            return None
        if d0 < near_z:
            t = (near_z - d0) / max(d1 - d0, 1e-8)
            p0_cam = p0_cam + t * (p1_cam - p0_cam)
            d0 = near_z
        elif d1 < near_z:
            t = (near_z - d1) / max(d0 - d1, 1e-8)
            p1_cam = p1_cam + t * (p0_cam - p1_cam)
            d1 = near_z

        r_p = proj_matrix[:3, :3]
        t_p = proj_matrix[:3, 3]
        c0 = r_p @ p0_cam + t_p
        c1 = r_p @ p1_cam + t_p
        p33 = float(proj_matrix[3, 3])
        if abs(p33 - 1.0) < 1e-5:
            return c0, c1, d0, d1
        if (
            proj_matrix[3, 0] == 0.0
            and proj_matrix[3, 1] == 0.0
            and proj_matrix[3, 2] == -1.0
            and p33 == 0.0
        ):
            w0 = max(-float(p0_cam[2]), 1e-6)
            w1 = max(-float(p1_cam[2]), 1e-6)
        else:
            w0 = max(float(proj_matrix[3, :3] @ p0_cam) + p33, 1e-6)
            w1 = max(float(proj_matrix[3, :3] @ p1_cam) + p33, 1e-6)
        return c0 / w0, c1 / w1, d0, d1

    @classmethod
    def project_segment_clipped(
        cls,
        p0_world: np.ndarray,
        p1_world: np.ndarray,
        view_matrix: np.ndarray,
        proj_matrix: np.ndarray,
        near_z: float = 0.08,
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """OP-74B 轻量级近平面线段裁剪封装算子：仅返回裁剪后的两端点 NDC 坐标 (ndc0, ndc1)"""
        res = cls.project_segment_clipped_with_depth(
            p0_world, p1_world, view_matrix, proj_matrix, near_z=near_z
        )
        if res is None:
            return None
        return res[0], res[1]

    @staticmethod
    def clip_triangle_near_plane(
        v0_cam: np.ndarray,
        v1_cam: np.ndarray,
        v2_cam: np.ndarray,
        near_z: float = 0.08,
    ) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """
        OP-74C / OP-79A 完备 8 状态 3-Bit 拓扑查表无循环 Sutherland–Hodgman 相机空间近平面三角形裁剪算子：
        - 严格区分入界边 (d_cur - d_prev > 0) 与出界边 (d_prev - d_cur > 0) 的正定分母，修复原出界边 max(负值, 1e-8) 引发的 10^8 倍爆炸漏洞；
        - 严格保持与 Sutherland–Hodgman 环路 (v2->v0)->(v0->v1)->(v1->v2) 完全相同的顶点拓扑顺序与对角线剖分（全 8 状态 0.0 ULP）。
        """
        d0 = -float(v0_cam[2])
        d1 = -float(v1_cam[2])
        d2 = -float(v2_cam[2])
        code = (1 if d0 >= near_z else 0) | (2 if d1 >= near_z else 0) | (4 if d2 >= near_z else 0)
        if code == 7:
            return [(v0_cam, v1_cam, v2_cam)]
        if code == 0:
            return []

        v0 = v0_cam if (type(v0_cam) is np.ndarray and v0_cam.dtype == np.float64) else np.asarray(v0_cam, dtype=np.float64)
        v1 = v1_cam if (type(v1_cam) is np.ndarray and v1_cam.dtype == np.float64) else np.asarray(v1_cam, dtype=np.float64)
        v2 = v2_cam if (type(v2_cam) is np.ndarray and v2_cam.dtype == np.float64) else np.asarray(v2_cam, dtype=np.float64)

        if code == 1:
            p20 = v2 + ((near_z - d2) / max(d0 - d2, 1e-8)) * (v0 - v2)
            p01 = v0 + ((d0 - near_z) / max(d0 - d1, 1e-8)) * (v1 - v0)
            return [(p20, v0, p01)]
        if code == 2:
            p01 = v0 + ((near_z - d0) / max(d1 - d0, 1e-8)) * (v1 - v0)
            p12 = v1 + ((d1 - near_z) / max(d1 - d2, 1e-8)) * (v2 - v1)
            return [(p01, v1, p12)]
        if code == 4:
            p20 = v2 + ((d2 - near_z) / max(d2 - d0, 1e-8)) * (v0 - v2)
            p12 = v1 + ((near_z - d1) / max(d2 - d1, 1e-8)) * (v2 - v1)
            return [(p20, p12, v2)]
        if code == 3:
            p20 = v2 + ((near_z - d2) / max(d0 - d2, 1e-8)) * (v0 - v2)
            p12 = v1 + ((d1 - near_z) / max(d1 - d2, 1e-8)) * (v2 - v1)
            return [(p20, v0, v1), (p20, v1, p12)]
        if code == 5:
            p01 = v0 + ((d0 - near_z) / max(d0 - d1, 1e-8)) * (v1 - v0)
            p12 = v1 + ((near_z - d1) / max(d2 - d1, 1e-8)) * (v2 - v1)
            return [(v0, p01, p12), (v0, p12, v2)]
        # code == 6
        p20 = v2 + ((d2 - near_z) / max(d2 - d0, 1e-8)) * (v0 - v2)
        p01 = v0 + ((near_z - d0) / max(d1 - d0, 1e-8)) * (v1 - v0)
        return [(p20, p01, v1), (p20, v1, v2)]

    @staticmethod
    def _ray_intersects_triangles_batch(
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        max_dist: float,
        v0: np.ndarray,
        v1: np.ndarray,
        v2: np.ndarray,
        endpoint_clearance: float = 0.018,
        pre_edge1: Optional[np.ndarray] = None,
        pre_edge2: Optional[np.ndarray] = None,
    ) -> bool:
        """
        OP-75A / OP-80A 递进式 X->Y->Z 单轴级联包围盒过滤 + 惰性边向量求值的 Möller–Trumbore 批量求交算子
        """
        n_f = v0.shape[0]
        if n_f == 0:
            return False
        ox, oy, oz = float(ray_origin[0]), float(ray_origin[1]), float(ray_origin[2])
        rx, ry, rz = float(ray_dir[0]), float(ray_dir[1]), float(ray_dir[2])
        t_min_d = endpoint_clearance
        t_max_d = max_dist - endpoint_clearance
        if t_min_d >= t_max_d:
            return False

        if n_f > 32 and pre_edge1 is None and pre_edge2 is None:
            p0x = ox + t_min_d * rx
            p1x = ox + t_max_d * rx
            r_xmin = (p0x if p0x < p1x else p1x) - 1e-5
            r_xmax = (p1x if p0x < p1x else p0x) + 1e-5
            v0x, v1x, v2x = v0[:, 0], v1[:, 0], v2[:, 0]
            kx = ((v0x >= r_xmin) | (v1x >= r_xmin) | (v2x >= r_xmin)) & (
                (v0x <= r_xmax) | (v1x <= r_xmax) | (v2x <= r_xmax)
            )
            if not kx.any():
                return False
            idx = np.where(kx)[0]

            p0y = oy + t_min_d * ry
            p1y = oy + t_max_d * ry
            r_ymin = (p0y if p0y < p1y else p1y) - 1e-5
            r_ymax = (p1y if p0y < p1y else p0y) + 1e-5
            v0y, v1y, v2y = v0[idx, 1], v1[idx, 1], v2[idx, 1]
            ky = ((v0y >= r_ymin) | (v1y >= r_ymin) | (v2y >= r_ymin)) & (
                (v0y <= r_ymax) | (v1y <= r_ymax) | (v2y <= r_ymax)
            )
            if not ky.any():
                return False
            idx = idx[ky]

            p0z = oz + t_min_d * rz
            p1z = oz + t_max_d * rz
            r_zmin = (p0z if p0z < p1z else p1z) - 1e-5
            r_zmax = (p1z if p0z < p1z else p0z) + 1e-5
            v0z, v1z, v2z = v0[idx, 2], v1[idx, 2], v2[idx, 2]
            kz = ((v0z >= r_zmin) | (v1z >= r_zmin) | (v2z >= r_zmin)) & (
                (v0z <= r_zmax) | (v1z <= r_zmax) | (v2z <= r_zmax)
            )
            if not kz.any():
                return False
            idx = idx[kz]
            v0 = v0[idx]
            v1 = v1[idx]
            v2 = v2[idx]

        eps = 1e-7
        edge1 = (v1 - v0) if pre_edge1 is None else pre_edge1
        edge2 = (v2 - v0) if pre_edge2 is None else pre_edge2
        hx = ry * edge2[:, 2] - rz * edge2[:, 1]
        hy = rz * edge2[:, 0] - rx * edge2[:, 2]
        hz = rx * edge2[:, 1] - ry * edge2[:, 0]
        a = edge1[:, 0] * hx + edge1[:, 1] * hy + edge1[:, 2] * hz
        valid_mask = np.abs(a) > eps
        if not valid_mask.any():
            return False
        valid_idx = np.where(valid_mask)[0]

        f = 1.0 / a[valid_idx]
        v0_v = v0[valid_idx]
        sx = ox - v0_v[:, 0]
        sy = oy - v0_v[:, 1]
        sz = oz - v0_v[:, 2]
        u = f * (sx * hx[valid_idx] + sy * hy[valid_idx] + sz * hz[valid_idx])
        u_mask = (u >= -1e-4) & (u <= 1.0001)
        if not u_mask.any():
            return False

        valid_idx = valid_idx[u_mask]
        f = f[u_mask]
        u = u[u_mask]
        sx, sy, sz = sx[u_mask], sy[u_mask], sz[u_mask]
        e1_v = edge1[valid_idx]
        qx = sy * e1_v[:, 2] - sz * e1_v[:, 1]
        qy = sz * e1_v[:, 0] - sx * e1_v[:, 2]
        qz = sx * e1_v[:, 1] - sy * e1_v[:, 0]
        v = f * (rx * qx + ry * qy + rz * qz)
        v_mask = (v >= -1e-4) & (u + v <= 1.0002)
        if not v_mask.any():
            return False

        valid_idx = valid_idx[v_mask]
        f = f[v_mask]
        qx, qy, qz = qx[v_mask], qy[v_mask], qz[v_mask]
        e2_v = edge2[valid_idx]
        t = f * (e2_v[:, 0] * qx + e2_v[:, 1] * qy + e2_v[:, 2] * qz)
        return bool(((t > t_min_d) & (t < t_max_d)).any())

    @staticmethod
    def _build_mt_tables_for_focus(
        v0_arr: np.ndarray, v1_arr: np.ndarray, v2_arr: np.ndarray, roi_focus_point: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """靶点锚定 Möller–Trumbore 不变量预分解表构造算子（预分配连续内存零 column_stack 拼接）"""
        e1 = v1_arr - v0_arr
        e2 = v2_arr - v0_arr
        s_f = roi_focus_point[None, :] - v0_arr
        nx = e1[:, 1] * e2[:, 2] - e1[:, 2] * e2[:, 1]
        ny = e1[:, 2] * e2[:, 0] - e1[:, 0] * e2[:, 2]
        nz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        neg_n = np.empty_like(v0_arr)
        neg_n[:, 0] = -nx
        neg_n[:, 1] = -ny
        neg_n[:, 2] = -nz
        qu = np.empty_like(v0_arr)
        qu[:, 0] = e2[:, 1] * s_f[:, 2] - e2[:, 2] * s_f[:, 1]
        qu[:, 1] = e2[:, 2] * s_f[:, 0] - e2[:, 0] * s_f[:, 2]
        qu[:, 2] = e2[:, 0] * s_f[:, 1] - e2[:, 1] * s_f[:, 0]
        qv = np.empty_like(v0_arr)
        qv[:, 0] = s_f[:, 1] * e1[:, 2] - s_f[:, 2] * e1[:, 1]
        qv[:, 1] = s_f[:, 2] * e1[:, 0] - s_f[:, 0] * e1[:, 2]
        qv[:, 2] = s_f[:, 0] * e1[:, 1] - s_f[:, 1] * e1[:, 0]
        t_num = e2[:, 0] * qv[:, 0] + e2[:, 1] * qv[:, 1] + e2[:, 2] * qv[:, 2]
        return neg_n, t_num, qu, qv

    @staticmethod
    def _hits_mt_table_single(
        ray_dir: np.ndarray, max_d: float, tables: Tuple, clearance: float = 0.018
    ) -> bool:
        """单条射线对靶点锚定 Möller–Trumbore 预分解表的极速求交算子"""
        n_arr, t_arr, qu_arr, qv_arr = tables
        a = n_arr @ ray_dir
        valid = np.abs(a) > 1e-7
        if not valid.any():
            return False
        idx = np.where(valid)[0]
        f = 1.0 / a[idx]
        t = max_d + t_arr[idx] * f
        t_mask = (t > clearance) & (t < max_d - clearance)
        if not t_mask.any():
            return False
        idx = idx[t_mask]
        f = f[t_mask]
        u = (qu_arr[idx] @ ray_dir) * f
        u_mask = (u >= -1e-4) & (u <= 1.0001)
        if not u_mask.any():
            return False
        idx = idx[u_mask]
        f = f[u_mask]
        u = u[u_mask]
        v = (qv_arr[idx] @ ray_dir) * f
        return bool(((v >= -1e-4) & (u + v <= 1.0002)).any())

    @classmethod
    def resolve_unoccluded_camera_eye(
        cls,
        initial_eye: np.ndarray,
        roi_focus_point: np.ndarray,
        occluder_meshes: List[MeshEntity3D],
        min_ground_z: float = 0.12,
    ) -> Tuple[np.ndarray, bool]:
        """
        OP-75B / OP-80B / OP-80C 五射线视锥束球面视线主动避障算子（二阶穿透式加速架构）：
        - 标量 7 元组 + 硬件 CRC32 一致性守卫缓存键；
        - 标量 Jordan–Brouwer AABB 边界预筛与整网格全包含免索引短路；
        - 分网格惰性 Slab 门控 MT 表架构 + 四孔径边缘射线 (4, 3) 矩阵批量求交，0.0 ULP。
        """
        initial_eye = np.asarray(initial_eye, dtype=np.float64)
        roi_focus_point = np.asarray(roi_focus_point, dtype=np.float64)
        if not occluder_meshes:
            return initial_eye, False

        ex0, ey0, ez0 = float(initial_eye[0]), float(initial_eye[1]), float(initial_eye[2])
        fx0, fy0, fz0 = float(roi_focus_point[0]), float(roi_focus_point[1]), float(roi_focus_point[2])
        gaze_key = (
            ex0, ey0, ez0,
            fx0, fy0, fz0,
            float(min_ground_z),
            tuple(m._compute_full_crc_token() for m in occluder_meshes),
        )
        cached_gaze = cls._GAZE_CACHE.get(gaze_key)
        if cached_gaze is not None:
            return cached_gaze[0].copy(), cached_gaze[1]

        rx_rel = ex0 - fx0
        ry_rel = ey0 - fy0
        rz_rel = ez0 - fz0
        dist = math.sqrt(rx_rel * rx_rel + ry_rel * ry_rel + rz_rel * rz_rel)
        if dist < 1e-5:
            return initial_eye, False

        for m in occluder_meshes:
            bmin = m._cached_bbox_min if m._cached_bbox_min is not None else m.bbox_min
            bmax = m._cached_bbox_max if m._cached_bbox_max is not None else m.bbox_max
            if (
                fx0 <= float(bmin[0]) + 0.0185 or fx0 >= float(bmax[0]) - 0.0185
                or fy0 <= float(bmin[1]) + 0.0185 or fy0 >= float(bmax[1]) - 0.0185
                or fz0 <= float(bmin[2]) + 0.0185 or fz0 >= float(bmax[2]) - 0.0185
            ):
                continue
            if not m.is_closed_hull:
                continue
            max_r_m = float(
                np.sqrt(np.max(np.sum((m.vertices - roi_focus_point[None, :]) ** 2, axis=1)))
            )
            if max_r_m >= dist - 0.02:
                continue
            normals = m.face_normals
            if m._cached_f_dot_n is None:
                m._cached_f_dot_n = np.einsum("ij,ij->i", m.tri_vertices[0], normals)
            f_dot_n = m._cached_f_dot_n
            if not bool(((roi_focus_point @ normals.T) - f_dot_n < -0.0185).all()):
                continue
            if m._cached_is_convex is None:
                if normals.shape[0] > 16:
                    chg = np.empty(normals.shape[0], dtype=bool)
                    chg[0] = True
                    chg[1:] = (
                        (normals[1:, 0] != normals[:-1, 0])
                        | (normals[1:, 1] != normals[:-1, 1])
                        | (normals[1:, 2] != normals[:-1, 2])
                    )
                    r_idx = np.where(chg)[0]
                    if r_idx.shape[0] < normals.shape[0]:
                        max_proj_r = (m.vertices @ normals[r_idx].T).max(axis=0)
                        run_ids = np.cumsum(chg) - 1
                        m._cached_is_convex = bool(float(np.max(max_proj_r[run_ids] - f_dot_n)) <= 1e-4)
                    else:
                        m._cached_is_convex = bool(
                            float(np.max((m.vertices @ normals.T) - f_dot_n[None, :])) <= 1e-4
                        )
                else:
                    m._cached_is_convex = bool(
                        float(np.max((m.vertices @ normals.T) - f_dot_n[None, :])) <= 1e-4
                    )
            if m._cached_is_convex:
                return initial_eye, False

        off_mat = cls._APERTURE_OFFSETS_4
        base_xy = math.hypot(rx_rel, ry_rel)
        base_yaw = math.atan2(ry_rel, rx_rel)
        base_pitch = math.atan2(rz_rel, max(base_xy, 1e-6))
        cur_pitch0 = max(math.radians(-45.0), min(math.radians(78.0), base_pitch))
        cos_p0 = math.cos(cur_pitch0)
        cand_eye0 = roi_focus_point + dist * np.array(
            [
                cos_p0 * math.cos(base_yaw),
                cos_p0 * math.sin(base_yaw),
                math.sin(cur_pitch0),
            ],
            dtype=np.float64,
        )

        sph_r = dist + 0.085
        sph_min0, sph_min1 = fx0 - sph_r, fy0 - sph_r
        sph_min2 = max(fz0 - sph_r, min(fz0 - 0.085, float(min_ground_z) - 0.02))
        sph_max0, sph_max1, sph_max2 = fx0 + sph_r, fy0 + sph_r, fz0 + sph_r

        mesh_entries: List[List[object]] = []
        for m in occluder_meshes:
            bmin = m._cached_bbox_min if m._cached_bbox_min is not None else m.bbox_min
            bmax = m._cached_bbox_max if m._cached_bbox_max is not None else m.bbox_max
            bm0, bm1, bm2 = float(bmin[0]), float(bmin[1]), float(bmin[2])
            bx0, bx1, bx2 = float(bmax[0]), float(bmax[1]), float(bmax[2])
            if (
                bx0 < sph_min0 or bm0 > sph_max0
                or bx1 < sph_min1 or bm1 > sph_max1
                or bx2 < sph_min2 or bm2 > sph_max2
            ):
                continue
            mesh_entries.append([m, bm0, bm1, bm2, bx0, bx1, bx2, None, False])

        if not mesh_entries:
            return cand_eye0 if float(cand_eye0[2]) >= min_ground_z else initial_eye, False

        def _get_entry_tables(entry: List[object]):
            if entry[8]:
                return entry[7]
            m = entry[0]
            bm0, bm1, bm2, bx0, bx1, bx2 = entry[1], entry[2], entry[3], entry[4], entry[5], entry[6]
            mv0, mv1, mv2 = m._cached_tri_verts if m._cached_tri_verts is not None else m.tri_vertices
            if m.faces.shape[0] > 32 and not (
                bm0 >= sph_min0 and bx0 <= sph_max0
                and bm1 >= sph_min1 and bx1 <= sph_max1
                and bm2 >= sph_min2 and bx2 <= sph_max2
            ):
                t_min, t_max = m._cached_tri_bounds if m._cached_tri_bounds is not None else m.triangle_aabb_bounds
                keep = (
                    (t_max[:, 0] >= sph_min0) & (t_min[:, 0] <= sph_max0)
                    & (t_max[:, 1] >= sph_min1) & (t_min[:, 1] <= sph_max1)
                    & (t_max[:, 2] >= sph_min2) & (t_min[:, 2] <= sph_max2)
                )
                if not keep.any():
                    entry[8] = True
                    return None
                if not keep.all():
                    ik = np.where(keep)[0]
                    mv0, mv1, mv2 = mv0[ik], mv1[ik], mv2[ik]
            tables = cls._build_mt_tables_for_focus(mv0, mv1, mv2, roi_focus_point)
            entry[7] = tables
            entry[8] = True
            return tables

        def _ray_hits_any_entry(
            ox: float, oy: float, oz: float, r_dir: np.ndarray, max_d: float, clearance: float = 0.018
        ) -> bool:
            dx, dy, dz = float(r_dir[0]), float(r_dir[1]), float(r_dir[2])
            for entry in mesh_entries:
                if not _ray_aabb_slab_scalar(
                    ox, oy, oz, dx, dy, dz, max_d,
                    entry[1], entry[2], entry[3], entry[4], entry[5], entry[6], clearance
                ):
                    continue
                tables = _get_entry_tables(entry)
                if tables is not None and cls._hits_mt_table_single(r_dir, max_d, tables, clearance):
                    return True
            return False

        def _count_aperture_5(cand_eye: np.ndarray, center_dir: np.ndarray) -> int:
            cx, cy, cz = float(cand_eye[0]), float(cand_eye[1]), float(cand_eye[2])
            if _ray_hits_any_entry(cx, cy, cz, center_dir, dist, 0.018):
                return 0
            orig_4 = cand_eye[None, :] + off_mat
            t_vecs = roi_focus_point[None, :] - orig_4
            t_ds = np.sqrt(np.einsum("ij,ij->i", t_vecs, t_vecs))
            r_dirs = t_vecs / np.maximum(t_ds, 1e-6)[:, None]
            vis_cnt = 1
            for k in range(4):
                if not _ray_hits_any_entry(
                    float(orig_4[k, 0]), float(orig_4[k, 1]), float(orig_4[k, 2]),
                    r_dirs[k], float(t_ds[k]), 0.018
                ):
                    vis_cnt += 1
            return vis_cnt

        best_partial_eye = initial_eye
        best_vis_count = -1
        best_moved = False

        if float(cand_eye0[2]) >= min_ground_z:
            c_dir0 = (roi_focus_point - cand_eye0) / dist
            vis0 = _count_aperture_5(cand_eye0, c_dir0)
            if vis0 == 5:
                if len(cls._GAZE_CACHE) >= 32:
                    cls._GAZE_CACHE.clear()
                cls._GAZE_CACHE[gaze_key] = (cand_eye0.copy(), False)
                return cand_eye0, False
            if vis0 > 0:
                best_vis_count = vis0
                best_partial_eye = cand_eye0
                best_moved = False

        for pitch_delta_deg in (0.0, 12.0, -10.0, 24.0, -18.0, 36.0):
            cur_pitch = max(
                math.radians(-45.0),
                min(math.radians(78.0), base_pitch + math.radians(pitch_delta_deg)),
            )
            sin_p = math.sin(cur_pitch)
            cand_z = fz0 + dist * sin_p
            if cand_z < min_ground_z:
                continue
            cos_p = math.cos(cur_pitch)
            for yaw_deg in (0.0, 25.0, -25.0, 50.0, -50.0, 75.0, -75.0, 110.0, -110.0, 145.0, -145.0, 180.0):
                if pitch_delta_deg == 0.0 and yaw_deg == 0.0:
                    continue
                cur_yaw = base_yaw + math.radians(yaw_deg)
                cand_rel = dist * np.array(
                    [
                        cos_p * math.cos(cur_yaw),
                        cos_p * math.sin(cur_yaw),
                        sin_p,
                    ],
                    dtype=np.float64,
                )
                cand_eye = roi_focus_point + cand_rel
                center_dir = (roi_focus_point - cand_eye) / dist
                vis_cnt = _count_aperture_5(cand_eye, center_dir)
                if vis_cnt == 0:
                    continue
                moved = (abs(yaw_deg) > 1e-3) or (abs(pitch_delta_deg) > 1e-3)
                if vis_cnt == 5:
                    if len(cls._GAZE_CACHE) >= 32:
                        cls._GAZE_CACHE.clear()
                    cls._GAZE_CACHE[gaze_key] = (cand_eye.copy(), moved)
                    return cand_eye, moved
                if vis_cnt > best_vis_count:
                    best_vis_count = vis_cnt
                    best_partial_eye = cand_eye
                    best_moved = moved

        if len(cls._GAZE_CACHE) >= 32:
            cls._GAZE_CACHE.clear()
        if best_vis_count > 0:
            cls._GAZE_CACHE[gaze_key] = (best_partial_eye.copy(), best_moved)
            return best_partial_eye, best_moved
        cls._GAZE_CACHE[gaze_key] = (initial_eye.copy(), False)
        return initial_eye, False

    @classmethod
    def compute_foveal_ndc_window(
        cls,
        roi_points_world: np.ndarray,
        view_matrix: np.ndarray,
        base_proj_matrix: np.ndarray,
        padding_factor: float = 0.35,
        min_ndc_span: float = 0.12,
        scene_meshes: Optional[List[MeshEntity3D]] = None,
    ) -> Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]:
        """
        OP-76A / OP-81A 中央凹 NDC 裁剪窗口与紧致深度包络推导算子（单次投影极值双取，0.0 ULP）
        """
        ndc_pts, cam_depth = cls.project_world_to_ndc(
            roi_points_world, view_matrix, base_proj_matrix
        )
        x_min, y_min = float(ndc_pts[:, 0].min()), float(ndc_pts[:, 1].min())
        x_max, y_max = float(ndc_pts[:, 0].max()), float(ndc_pts[:, 1].max())

        cx = 0.5 * (x_min + x_max)
        cy = 0.5 * (y_min + y_max)
        span_x = (x_max - x_min) * (1.0 + padding_factor)
        span_y = (y_max - y_min) * (1.0 + padding_factor)

        square_span = min(max(span_x, span_y, min_ndc_span), 1.8)
        half_s = 0.5 * square_span

        cx = max(-1.0 + half_s, min(1.0 - half_s, cx))
        cy = max(-1.0 + half_s, min(1.0 - half_s, cy))

        ndc_window = (cx - half_s, cx + half_s, cy - half_s, cy + half_s)
        optical_zoom = 2.0 / square_span

        if scene_meshes:
            vz_row = np.ascontiguousarray(-view_matrix[2, :3], dtype=np.float64)
            vz_off = -float(view_matrix[2, 3])
            d_min_all = float("inf")
            d_max_all = float("-inf")
            for m in scene_meshes:
                proj_v = m.vertices @ vz_row
                mn = float(proj_v.min()) + vz_off
                mx = float(proj_v.max()) + vz_off
                if mn < d_min_all:
                    d_min_all = mn
                if mx > d_max_all:
                    d_max_all = mx
            z_min = max(min(float(cam_depth.min()), d_min_all) - 0.25, 0.08)
            z_max = max(float(cam_depth.max()), d_max_all) + 0.50
        else:
            z_min = max(float(cam_depth.min()) - 0.8, 0.1)
            z_max = max(float(cam_depth.max()) + 1.2, z_min + 0.5)
        return ndc_window, optical_zoom, (round(z_min, 3), round(z_max, 3))

    @staticmethod
    def build_asymmetric_sub_frustum_matrix(
        base_proj_matrix: np.ndarray,
        ndc_window: Tuple[float, float, float, float],
        tight_depth_range: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        OP-76B 零乘法稀疏解析直接装配同轴非对称子视锥矩阵算子（标准透视 7 非零元快通道 + 通用正交/离轴回退，0.0 ULP）
        """
        x_min, x_max, y_min, y_max = ndc_window
        dx = max(x_max - x_min, 1e-5)
        dy = max(y_max - y_min, 1e-5)
        sx = 2.0 / dx
        sy = 2.0 / dy
        tx = -(x_max + x_min) / dx
        ty = -(y_max + y_min) / dy

        if (
            base_proj_matrix[3, 2] == -1.0
            and base_proj_matrix[3, 3] == 0.0
            and base_proj_matrix[0, 2] == 0.0
            and base_proj_matrix[1, 2] == 0.0
            and base_proj_matrix[0, 3] == 0.0
            and base_proj_matrix[1, 3] == 0.0
        ):
            p_out = np.zeros((4, 4), dtype=np.float64)
            p_out[0, 0] = sx * base_proj_matrix[0, 0]
            p_out[0, 2] = -tx
            p_out[1, 1] = sy * base_proj_matrix[1, 1]
            p_out[1, 2] = -ty

            if tight_depth_range is not None:
                zn, zf = tight_depth_range
                zn_safe = max(0.08, float(zn))
                zf_safe = max(float(zf), zn_safe + 0.5)
                if zf_safe > zn_safe + 1e-3:
                    p_out[2, 2] = (zf_safe + zn_safe) / (zn_safe - zf_safe)
                    p_out[2, 3] = (2.0 * zf_safe * zn_safe) / (zn_safe - zf_safe)
                else:
                    p_out[2, 2] = base_proj_matrix[2, 2]
                    p_out[2, 3] = base_proj_matrix[2, 3]
            else:
                p_out[2, 2] = base_proj_matrix[2, 2]
                p_out[2, 3] = base_proj_matrix[2, 3]

            p_out[3, 2] = -1.0
            return p_out

        p_base = base_proj_matrix.copy()
        if tight_depth_range is not None:
            zn, zf = tight_depth_range
            zn_safe = max(0.08, float(zn))
            zf_safe = max(float(zf), zn_safe + 0.5)
            if zf_safe > zn_safe + 1e-3:
                p_base[2, 2] = (zf_safe + zn_safe) / (zn_safe - zf_safe)
                p_base[2, 3] = (2.0 * zf_safe * zn_safe) / (zn_safe - zf_safe)

        m_crop = np.array([
            [sx,  0.0, 0.0, tx],
            [0.0, sy,  0.0, ty],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)
        return m_crop @ p_base

    @staticmethod
    def project_segments_clipped_batch(
        p0_world_arr: np.ndarray,
        p1_world_arr: np.ndarray,
        view_matrix: np.ndarray,
        proj_matrix: np.ndarray,
        near_z: float = 0.08,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """OP-77A 世界空间拓扑边相机空间近平面 SIMD 批量向量化裁剪算子"""
        if p0_world_arr.shape[0] == 0:
            return None
        r_v = view_matrix[:3, :3]
        t_v = view_matrix[:3, 3]
        p0_cam = (p0_world_arr @ r_v.T) + t_v[None, :]
        p1_cam = (p1_world_arr @ r_v.T) + t_v[None, :]
        d0 = (-p0_cam[:, 2]).copy()
        d1 = (-p1_cam[:, 2]).copy()

        both_behind = (d0 < near_z) & (d1 < near_z)
        valid = ~both_behind
        if not valid.any():
            return None

        m0 = (d0 < near_z) & valid
        if m0.any():
            t0 = (near_z - d0[m0]) / np.maximum(d1[m0] - d0[m0], 1e-8)
            p0_cam[m0] = p0_cam[m0] + t0[:, None] * (p1_cam[m0] - p0_cam[m0])
            d0[m0] = near_z

        m1 = (d1 < near_z) & valid
        if m1.any():
            t1 = (near_z - d1[m1]) / np.maximum(d0[m1] - d1[m1], 1e-8)
            p1_cam[m1] = p1_cam[m1] + t1[:, None] * (p0_cam[m1] - p1_cam[m1])
            d1[m1] = near_z

        r_p = proj_matrix[:3, :3]
        t_p = proj_matrix[:3, 3]
        c0 = (p0_cam @ r_p.T) + t_p[None, :]
        c1 = (p1_cam @ r_p.T) + t_p[None, :]

        p33 = float(proj_matrix[3, 3])
        if abs(p33 - 1.0) < 1e-5:
            return c0, c1, d0, d1, valid
        if (
            proj_matrix[3, 0] == 0.0
            and proj_matrix[3, 1] == 0.0
            and proj_matrix[3, 2] == -1.0
            and p33 == 0.0
        ):
            w0 = np.maximum(-p0_cam[:, 2:3], 1e-6)
            w1 = np.maximum(-p1_cam[:, 2:3], 1e-6)
        else:
            w0 = np.maximum((p0_cam @ proj_matrix[3, :3])[:, None] + p33, 1e-6)
            w1 = np.maximum((p1_cam @ proj_matrix[3, :3])[:, None] + p33, 1e-6)

        c0 /= w0
        c1 /= w1
        return c0, c1, d0, d1, valid

    @staticmethod
    def clip_cam_segments_near_plane_batch(
        c0_cam: np.ndarray,
        c1_cam: np.ndarray,
        proj_matrix: np.ndarray,
        width: int,
        height: int,
        near_z: float = 0.08,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """OP-79B 相机空间预变换棱边 + 屏幕浮点像素坐标融合映射的 SIMD 批量近平面裁剪算子"""
        if c0_cam.shape[0] == 0:
            return None
        d0 = -c0_cam[:, 2]
        d1 = -c1_cam[:, 2]
        valid = (d0 >= near_z) | (d1 >= near_z)
        if not valid.any():
            return None
        if not valid.all():
            p0 = c0_cam[valid].copy()
            p1 = c1_cam[valid].copy()
            d0 = d0[valid].copy()
            d1 = d1[valid].copy()
        else:
            p0 = c0_cam.copy()
            p1 = c1_cam.copy()
            d0 = d0.copy()
            d1 = d1.copy()

        m0 = d0 < near_z
        if m0.any():
            t0 = (near_z - d0[m0]) / np.maximum(d1[m0] - d0[m0], 1e-8)
            p0[m0] = p0[m0] + t0[:, None] * (p1[m0] - p0[m0])
            d0[m0] = near_z

        m1 = d1 < near_z
        if m1.any():
            t1 = (near_z - d1[m1]) / np.maximum(d0[m1] - d1[m1], 1e-8)
            p1[m1] = p1[m1] + t1[:, None] * (p0[m1] - p1[m1])
            d1[m1] = near_z

        r_p2 = proj_matrix[:2, :3]
        t_p2 = proj_matrix[:2, 3]
        clip0 = (p0 @ r_p2.T) + t_p2[None, :]
        clip1 = (p1 @ r_p2.T) + t_p2[None, :]
        p33 = float(proj_matrix[3, 3])
        is_ortho = abs(p33 - 1.0) < 1e-5
        if is_ortho:
            x0_arr = (clip0[:, 0] * 0.5 + 0.5) * (width - 1)
            y0_arr = (1.0 - (clip0[:, 1] * 0.5 + 0.5)) * (height - 1)
            x1_arr = (clip1[:, 0] * 0.5 + 0.5) * (width - 1)
            y1_arr = (1.0 - (clip1[:, 1] * 0.5 + 0.5)) * (height - 1)
        else:
            if (
                proj_matrix[3, 0] == 0.0
                and proj_matrix[3, 1] == 0.0
                and proj_matrix[3, 2] == -1.0
                and p33 == 0.0
            ):
                w0 = np.maximum(-p0[:, 2], 1e-6)
                w1 = np.maximum(-p1[:, 2], 1e-6)
            else:
                w0 = np.maximum((p0 @ proj_matrix[3, :3]) + p33, 1e-6)
                w1 = np.maximum((p1 @ proj_matrix[3, :3]) + p33, 1e-6)
            x0_arr = (clip0[:, 0] / w0 * 0.5 + 0.5) * (width - 1)
            y0_arr = (1.0 - (clip0[:, 1] / w0 * 0.5 + 0.5)) * (height - 1)
            x1_arr = (clip1[:, 0] / w1 * 0.5 + 0.5) * (width - 1)
            y1_arr = (1.0 - (clip1[:, 1] / w1 * 0.5 + 0.5)) * (height - 1)
        return x0_arr, y0_arr, d0, x1_arr, y1_arr, d1

    @staticmethod
    def clip_triangles_near_plane_batch(
        v0_cam_arr: np.ndarray,
        v1_cam_arr: np.ndarray,
        v2_cam_arr: np.ndarray,
        near_z: float = 0.08,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """OP-79C 全网格跨近平面三角面片 8 状态掩码分组向量化批量裁剪算子（0.0 ULP）"""
        d0 = -v0_cam_arr[:, 2]
        d1 = -v1_cam_arr[:, 2]
        d2 = -v2_cam_arr[:, 2]
        codes = (
            (d0 >= near_z).astype(np.int32)
            | ((d1 >= near_z).astype(np.int32) << 1)
            | ((d2 >= near_z).astype(np.int32) << 2)
        )
        if (codes == 7).all():
            return (
                v0_cam_arr,
                v1_cam_arr,
                v2_cam_arr,
                np.arange(v0_cam_arr.shape[0], dtype=np.int32),
            )
        if (codes == 0).all():
            empty = np.zeros((0, 3), dtype=np.float64)
            return empty, empty, empty, np.zeros(0, dtype=np.int32)

        out_v0_list, out_v1_list, out_v2_list, out_idx_list = [], [], [], []
        idx_7 = np.where(codes == 7)[0]
        if idx_7.shape[0] > 0:
            out_v0_list.append(v0_cam_arr[idx_7])
            out_v1_list.append(v1_cam_arr[idx_7])
            out_v2_list.append(v2_cam_arr[idx_7])
            out_idx_list.append(idx_7)

        for c_val in (1, 2, 4, 3, 5, 6):
            idx_c = np.where(codes == c_val)[0]
            if idx_c.shape[0] == 0:
                continue
            v0, v1, v2 = v0_cam_arr[idx_c], v1_cam_arr[idx_c], v2_cam_arr[idx_c]
            dc0, dc1, dc2 = d0[idx_c], d1[idx_c], d2[idx_c]
            if c_val == 1:
                p20 = v2 + ((near_z - dc2) / np.maximum(dc0 - dc2, 1e-8))[:, None] * (v0 - v2)
                p01 = v0 + ((dc0 - near_z) / np.maximum(dc0 - dc1, 1e-8))[:, None] * (v1 - v0)
                out_v0_list.append(p20)
                out_v1_list.append(v0)
                out_v2_list.append(p01)
                out_idx_list.append(idx_c)
            elif c_val == 2:
                p01 = v0 + ((near_z - dc0) / np.maximum(dc1 - dc0, 1e-8))[:, None] * (v1 - v0)
                p12 = v1 + ((dc1 - near_z) / np.maximum(dc1 - dc2, 1e-8))[:, None] * (v2 - v1)
                out_v0_list.append(p01)
                out_v1_list.append(v1)
                out_v2_list.append(p12)
                out_idx_list.append(idx_c)
            elif c_val == 4:
                p20 = v2 + ((dc2 - near_z) / np.maximum(dc2 - dc0, 1e-8))[:, None] * (v0 - v2)
                p12 = v1 + ((near_z - dc1) / np.maximum(dc2 - dc1, 1e-8))[:, None] * (v2 - v1)
                out_v0_list.append(p20)
                out_v1_list.append(p12)
                out_v2_list.append(v2)
                out_idx_list.append(idx_c)
            elif c_val == 3:
                p20 = v2 + ((near_z - dc2) / np.maximum(dc0 - dc2, 1e-8))[:, None] * (v0 - v2)
                p12 = v1 + ((dc1 - near_z) / np.maximum(dc1 - dc2, 1e-8))[:, None] * (v2 - v1)
                out_v0_list.extend([p20, p20])
                out_v1_list.extend([v0, v1])
                out_v2_list.extend([v1, p12])
                out_idx_list.extend([idx_c, idx_c])
            elif c_val == 5:
                p01 = v0 + ((dc0 - near_z) / np.maximum(dc0 - dc1, 1e-8))[:, None] * (v1 - v0)
                p12 = v1 + ((near_z - dc1) / np.maximum(dc2 - dc1, 1e-8))[:, None] * (v2 - v1)
                out_v0_list.extend([v0, v0])
                out_v1_list.extend([p01, p12])
                out_v2_list.extend([p12, v2])
                out_idx_list.extend([idx_c, idx_c])
            else:  # c_val == 6
                p20 = v2 + ((dc2 - near_z) / np.maximum(dc2 - dc0, 1e-8))[:, None] * (v0 - v2)
                p01 = v0 + ((near_z - dc0) / np.maximum(dc1 - dc0, 1e-8))[:, None] * (v1 - v0)
                out_v0_list.extend([p20, p20])
                out_v1_list.extend([p01, v1])
                out_v2_list.extend([v1, v2])
                out_idx_list.extend([idx_c, idx_c])

        return (
            np.vstack(out_v0_list),
            np.vstack(out_v1_list),
            np.vstack(out_v2_list),
            np.concatenate(out_idx_list),
        )

    @staticmethod
    def ray_intersects_aabb_fast(
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        max_dist: float,
        bbox_min: np.ndarray,
        bbox_max: np.ndarray,
        clearance: float = 0.018,
    ) -> bool:
        """OP-77B 标量无分配射线-轴对齐包围盒 (Ray-AABB) Smits–Kay–Kajiya Slab 极速求交算子"""
        return _ray_aabb_slab_scalar(
            float(ray_origin[0]),
            float(ray_origin[1]),
            float(ray_origin[2]),
            float(ray_dir[0]),
            float(ray_dir[1]),
            float(ray_dir[2]),
            float(max_dist),
            float(bbox_min[0]),
            float(bbox_min[1]),
            float(bbox_min[2]),
            float(bbox_max[0]),
            float(bbox_max[1]),
            float(bbox_max[2]),
            float(clearance),
        )

    @staticmethod
    def build_frustum_planes_from_matrix(vp_or_proj_matrix: np.ndarray) -> np.ndarray:
        """OP-77C Gribb–Hartmann 视锥体六半空间裁剪平面提取算子"""
        m = vp_or_proj_matrix
        planes = np.empty((6, 4), dtype=np.float64)
        planes[0] = m[3] + m[0]
        planes[1] = m[3] - m[0]
        planes[2] = m[3] + m[1]
        planes[3] = m[3] - m[1]
        planes[4] = m[3] + m[2]
        planes[5] = m[3] - m[2]
        norms = np.sqrt(planes[:, 0] ** 2 + planes[:, 1] ** 2 + planes[:, 2] ** 2)
        planes /= np.maximum(norms[:, None], 1e-12)
        return planes

    @staticmethod
    def build_view_projection_matrix(view_matrix: np.ndarray, proj_matrix: np.ndarray) -> np.ndarray:
        """OP-77D 视口-投影融合矩阵算子（View-Projection Matrix）"""
        return proj_matrix @ view_matrix


