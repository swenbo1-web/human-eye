"""M3 BVH-042 Phase 2 (042-P2): Exact Admission, Common-Exponent Dyadic Frame & Fast Triangle Prep Harness.

Evaluates isolated P2 candidate arms:
  - K (P2-A only: Direct common-exponent exact dyadic frame + inlined vertex reader + dense index table)
  - L (P2-B only: Tightened _build_fast_triangles with -d2 reuse, 3-way bounds, tuple edges)
  - M (P2-C only: Integer-packed undirected edge keys in _admit_one)
  - N (P2-A + P2-B + P2-C combined)
against frozen 041 Arm A (119327bbb) and Phase-1 Arm I (8d68d1a13).
"""
from __future__ import annotations

import argparse
import gc
import io
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.bvh_eval import _surface_sig, _work_summary
from benchmarks.run_kernel_042_research import (
    FROZEN_COMMIT,
    FROZEN_RUNTIME_SHA,
    NOOP,
    _require,
    _sha256_json,
    _win32_env_info,
    activate_arm,
    assert_raw_trees_equal,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
    run_paired_timing,
)

BENCH_DIR = Path(__file__).resolve().parent
P2_ARMS_ROOT = ROOT / "scratch" / "042_p2_arms"
FROZEN_ARM_I_COMMIT = "8d68d1a133cb2635920ddd83b8b7f12bdc6e3869"
FROZEN_ARM_I_RUNTIME_SHA = "1db11b89a8513e571faf55fbd9bccc183c82c12b6bf43159cb7b1f28b1f7f7ab"

_RUNTIME_FILES = [
    "pyproject.toml",
    "human_eye_hook.py",
    "human_eye_foveated_renderer.py",
    "native_3d_spatial_scratchpad.py",
    "module_2_low_token_mcp_scene_bridge.py",
    "module_3_1_mcp_protocol_ipc_engine.py",
    "module_3_2_vlm_grounding_closed_loop_agent.py",
    "module_3_3_closed_loop_control_engine.py",
    "human_eye_plugin",
    "human_eye_module1_operators",
]


def ensure_frozen_arm_i() -> Path:
    """Materialize Arm I (8d68d1a13) into scratch/042_p2_arms/arm_i_042_p1 via git archive."""
    arm_i = P2_ARMS_ROOT / "arm_i_042_p1"
    marker = arm_i / "human_eye_plugin/surface_proximity.py"
    if marker.exists():
        return arm_i
    arm_i.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "archive", "--format=tar", FROZEN_ARM_I_COMMIT, "--", *_RUNTIME_FILES],
        cwd=str(ROOT), check=True, stdout=subprocess.PIPE,
    )
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(path=arm_i)
    _require(marker.exists(), f"Failed to extract frozen Arm I commit {FROZEN_ARM_I_COMMIT}")
    return arm_i


def _patch_sp_target(sp_path: Path, old_block: str, new_block: str, label: str) -> None:
    raw = sp_path.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    old_n = old_block.replace("\r\n", "\n")
    new_n = new_block.replace("\r\n", "\n")
    _require(old_n in text, f"{label}: target block missing in {sp_path}")
    updated = text.replace(old_n, new_n, 1)
    sp_path.write_bytes(updated.encode("utf-8").replace(b"\n", eol))


_P2_A_OLD = """def _integer_frame(records, budget, *, holder=None):
    verts_info = []
    for mesh, _, _ in records:
        verts = mesh.vertices
        verts_info.append((verts, _is_numpy_2d_vertices(verts)))
    first_verts, first_np = verts_info[0]
    budget.checkpoint('surface_proximity_referenced_vertices')
    fx, fy, fz = _read_vertex_xyz(first_verts, records[0][2][0], first_np)
    origin = (_bounded(Fraction.from_float(fx)),
              _bounded(Fraction.from_float(fy)),
              _bounded(Fraction.from_float(fz)))
    o0 = _float_dyadic(fx)
    o1 = _float_dyadic(fy)
    o2 = _float_dyadic(fz)
    relative, exponent = [], 0
    tick = budget.tick
    for (_, faces, indices), (verts, is_np) in zip(records, verts_info):
        coordinates = {}
        for index in indices:
            tick('referenced_vertices')
            vx, vy, vz = _read_vertex_xyz(verts, index, is_np)
            dx = _sub_dyadic(_float_dyadic(vx), o0)
            dy = _sub_dyadic(_float_dyadic(vy), o1)
            dz = _sub_dyadic(_float_dyadic(vz), o2)
            if dx[0] and -dx[1] > exponent:
                exponent = -dx[1]
            if dy[0] and -dy[1] > exponent:
                exponent = -dy[1]
            if dz[0] and -dz[1] > exponent:
                exponent = -dz[1]
            coordinates[index] = (dx, dy, dz)
        relative.append((faces, coordinates))
    factor, prepared = _prepare_triangles_from_relative(relative, exponent, budget, holder=holder)
    return origin, factor, prepared"""

_P2_A_NEW = """def _integer_frame(records, budget, *, holder=None):
    verts_info = []
    for mesh, _, _ in records:
        verts = mesh.vertices
        verts_info.append((verts, _is_numpy_2d_vertices(verts)))
    first_verts, first_np = verts_info[0]
    budget.checkpoint('surface_proximity_referenced_vertices')
    fx, fy, fz = _read_vertex_xyz(first_verts, records[0][2][0], first_np)
    origin = (_bounded(Fraction.from_float(fx)),
              _bounded(Fraction.from_float(fy)),
              _bounded(Fraction.from_float(fz)))

    frexp = math.frexp
    ldexp = math.ldexp
    isfinite = math.isfinite
    tick = budget.tick
    checkpoint = budget.checkpoint

    # Pass 1: inline finite extract + exact (mant, e_raw) decomposition across referenced vertices
    min_e = None
    max_e = None
    if fx != 0.0:
        m, e = frexp(fx); om0 = int(ldexp(m, 53)); oe0 = e - 53
        min_e = max_e = oe0
    else:
        om0 = oe0 = 0
    if fy != 0.0:
        m, e = frexp(fy); om1 = int(ldexp(m, 53)); oe1 = e - 53
        if min_e is None: min_e = max_e = oe1
        else:
            if oe1 < min_e: min_e = oe1
            if oe1 > max_e: max_e = oe1
    else:
        om1 = oe1 = 0
    if fz != 0.0:
        m, e = frexp(fz); om2 = int(ldexp(m, 53)); oe2 = e - 53
        if min_e is None: min_e = max_e = oe2
        else:
            if oe2 < min_e: min_e = oe2
            if oe2 > max_e: max_e = oe2
    else:
        om2 = oe2 = 0

    raw_sides = []
    for (_, faces, indices), (verts, is_np) in zip(records, verts_info):
        raw_coords = []
        app = raw_coords.append
        if is_np:
            item = verts.item
            for index in indices:
                tick('referenced_vertices')
                vx = float(item((index, 0)))
                vy = float(item((index, 1)))
                vz = float(item((index, 2)))
                if not (isfinite(vx) and isfinite(vy) and isfinite(vz)):
                    raise _DomainError('surface_nonfinite_vertex')
                if vx != 0.0:
                    m, e = frexp(vx); mx = int(ldexp(m, 53)); ex = e - 53
                    if min_e is None: min_e = max_e = ex
                    else:
                        if ex < min_e: min_e = ex
                        if ex > max_e: max_e = ex
                else:
                    mx = ex = 0
                if vy != 0.0:
                    m, e = frexp(vy); my = int(ldexp(m, 53)); ey = e - 53
                    if min_e is None: min_e = max_e = ey
                    else:
                        if ey < min_e: min_e = ey
                        if ey > max_e: max_e = ey
                else:
                    my = ey = 0
                if vz != 0.0:
                    m, e = frexp(vz); mz = int(ldexp(m, 53)); ez = e - 53
                    if min_e is None: min_e = max_e = ez
                    else:
                        if ez < min_e: min_e = ez
                        if ez > max_e: max_e = ez
                else:
                    mz = ez = 0
                app((index, mx, ex, my, ey, mz, ez))
        else:
            for index in indices:
                tick('referenced_vertices')
                values = verts[index]
                if len(values) != 3:
                    raise _DomainError('surface_nonfinite_vertex')
                vx, vy, vz = values[0], values[1], values[2]
                if type(vx) is not float: vx = float(vx)
                if type(vy) is not float: vy = float(vy)
                if type(vz) is not float: vz = float(vz)
                if not (isfinite(vx) and isfinite(vy) and isfinite(vz)):
                    raise _DomainError('surface_nonfinite_vertex')
                if vx != 0.0:
                    m, e = frexp(vx); mx = int(ldexp(m, 53)); ex = e - 53
                    if min_e is None: min_e = max_e = ex
                    else:
                        if ex < min_e: min_e = ex
                        if ex > max_e: max_e = ex
                else:
                    mx = ex = 0
                if vy != 0.0:
                    m, e = frexp(vy); my = int(ldexp(m, 53)); ey = e - 53
                    if min_e is None: min_e = max_e = ey
                    else:
                        if ey < min_e: min_e = ey
                        if ey > max_e: max_e = ey
                else:
                    my = ey = 0
                if vz != 0.0:
                    m, e = frexp(vz); mz = int(ldexp(m, 53)); ez = e - 53
                    if min_e is None: min_e = max_e = ez
                    else:
                        if ez < min_e: min_e = ez
                        if ez > max_e: max_e = ez
                else:
                    mz = ez = 0
                app((index, mx, ex, my, ey, mz, ez))
        raw_sides.append((faces, indices, raw_coords))

    if min_e is None:
        min_e = max_e = 0

    if max_e - min_e <= 900 and -min_e <= 900:
        E_upper = 0 if min_e >= 0 else -min_e
        ox_u = om0 << (E_upper + oe0) if om0 else 0
        oy_u = om1 << (E_upper + oe1) if om1 else 0
        oz_u = om2 << (E_upper + oe2) if om2 else 0
        or_all = 0
        shifted_sides = []
        for faces, indices, raw_coords in raw_sides:
            sc = []
            sapp = sc.append
            for index, mx, ex, my, ey, mz, ez in raw_coords:
                dx_u = (mx << (E_upper + ex) if mx else 0) - ox_u
                dy_u = (my << (E_upper + ey) if my else 0) - oy_u
                dz_u = (mz << (E_upper + ez) if mz else 0) - oz_u
                or_all |= dx_u | dy_u | dz_u
                sapp((index, dx_u, dy_u, dz_u))
            shifted_sides.append((faces, indices, sc))

        common_tz = E_upper if or_all == 0 else min(E_upper, (or_all & -or_all).bit_length() - 1)
        exponent = E_upper - common_tz
        factor = _bounded(1 << exponent)
        limit = _FAST_COORD_LIMIT
        prepared = []
        retained = [] if holder is not None else None
        for faces, indices, sc in shifted_sides:
            max_idx = indices[-1] if indices else -1
            use_list = (holder is None and 0 <= max_idx < 65536 and max_idx < 4 * len(indices))
            integers = [None] * (max_idx + 1) if use_list else {}
            fast_side = True
            if common_tz:
                for index, dx_u, dy_u, dz_u in sc:
                    checkpoint('surface_proximity_referenced_vertices')
                    ix = dx_u >> common_tz
                    iy = dy_u >> common_tz
                    iz = dz_u >> common_tz
                    if ix <= -limit or ix >= limit or iy <= -limit or iy >= limit or iz <= -limit or iz >= limit:
                        fast_side = False
                        _bounded(ix); _bounded(iy); _bounded(iz)
                    integers[index] = (ix, iy, iz)
            else:
                for index, ix, iy, iz in sc:
                    checkpoint('surface_proximity_referenced_vertices')
                    if ix <= -limit or ix >= limit or iy <= -limit or iy >= limit or iz <= -limit or iz >= limit:
                        fast_side = False
                        _bounded(ix); _bounded(iy); _bounded(iz)
                    integers[index] = (ix, iy, iz)
            if fast_side:
                triangles = _build_fast_triangles(faces, integers, budget=budget)
            else:
                triangles = []
                for face in faces:
                    checkpoint('surface_proximity_triangle_prepare')
                    tick('prepared_triangles')
                    points = tuple(integers[index] for index in face)
                    normal = _normal(points)
                    if not any(normal):
                        start, end = min(points), max(points)
                        points = (start,) if start == end else (start, end)
                    squared = _dot(normal, normal)
                    edges = []
                    for i in range(3 if squared else len(points) - 1):
                        start, end = points[i], points[(i + 1) % len(points)]
                        delta = _sub(end, start)
                        edges.append((start, end, delta, _dot(delta, delta)))
                    bounds = tuple((min(point[k] for point in points),
                                    max(point[k] for point in points)) for k in range(3))
                    triangles.append((points, normal, squared, edges, bounds))
            prepared.append(triangles)
            if retained is not None:
                retained.append(integers)
        if holder is not None:
            holder['coordinates'] = tuple(retained)
        return origin, factor, prepared

    # Fallback path for extreme binary64 exponent spread > 900 bits
    def _norm_dy(m_raw, e_raw):
        if m_raw == 0:
            return 0, 0
        tz = (m_raw & -m_raw).bit_length() - 1
        return m_raw >> tz, e_raw + tz

    o0 = _norm_dy(om0, oe0)
    o1 = _norm_dy(om1, oe1)
    o2 = _norm_dy(om2, oe2)
    relative, exponent = [], 0
    for faces, _, raw_coords in raw_sides:
        coordinates = {}
        for index, mx, ex, my, ey, mz, ez in raw_coords:
            dx = _sub_dyadic(_norm_dy(mx, ex), o0)
            dy = _sub_dyadic(_norm_dy(my, ey), o1)
            dz = _sub_dyadic(_norm_dy(mz, ez), o2)
            if dx[0] and -dx[1] > exponent: exponent = -dx[1]
            if dy[0] and -dy[1] > exponent: exponent = -dy[1]
            if dz[0] and -dz[1] > exponent: exponent = -dz[1]
            coordinates[index] = (dx, dy, dz)
        relative.append((faces, coordinates))
    factor, prepared = _prepare_triangles_from_relative(relative, exponent, budget, holder=holder)
    return origin, factor, prepared"""


_P2_B_OLD = """        if nx or ny or nz:
            points = (p0, p1, p2)
            normal = (nx, ny, nz)
            squared = nx * nx + ny * ny + nz * nz
            d3x, d3y, d3z = p0x - p2x, p0y - p2y, p0z - p2z
            d23x, d23y, d23z = p2x - p1x, p2y - p1y, p2z - p1z
            edges = [
                (p0, p1, (d1x, d1y, d1z), d1x * d1x + d1y * d1y + d1z * d1z),
                (p1, p2, (d23x, d23y, d23z), d23x * d23x + d23y * d23y + d23z * d23z),
                (p2, p0, (d3x, d3y, d3z), d3x * d3x + d3y * d3y + d3z * d3z),
            ]
            bounds = (
                (min(p0x, p1x, p2x), max(p0x, p1x, p2x)),
                (min(p0y, p1y, p2y), max(p0y, p1y, p2y)),
                (min(p0z, p1z, p2z), max(p0z, p1z, p2z)),
            )"""

_P2_B_NEW = """        if nx or ny or nz:
            points = (p0, p1, p2)
            normal = (nx, ny, nz)
            squared = nx * nx + ny * ny + nz * nz
            d23x, d23y, d23z = p2x - p1x, p2y - p1y, p2z - p1z
            edges = (
                (p0, p1, (d1x, d1y, d1z), d1x * d1x + d1y * d1y + d1z * d1z),
                (p1, p2, (d23x, d23y, d23z), d23x * d23x + d23y * d23y + d23z * d23z),
                (p2, p0, (-d2x, -d2y, -d2z), d2x * d2x + d2y * d2y + d2z * d2z),
            )
            if p0x <= p1x: lx, hx = p0x, p1x
            else: lx, hx = p1x, p0x
            if p2x < lx: lx = p2x
            elif p2x > hx: hx = p2x
            if p0y <= p1y: ly, hy = p0y, p1y
            else: ly, hy = p1y, p0y
            if p2y < ly: ly = p2y
            elif p2y > hy: hy = p2y
            if p0z <= p1z: lz, hz = p0z, p1z
            else: lz, hz = p1z, p0z
            if p2z < lz: lz = p2z
            elif p2z > hz: hz = p2z
            bounds = ((lx, hx), (ly, hy), (lz, hz))"""


_P2_C_OLD = """def _admit_one(mesh, tick, valid_int_types, *, checkpoint=None, verts=None, faces=None):
    verts_src = mesh.vertices if verts is None else verts
    faces_src = mesh.faces if faces is None else faces
    num_verts = len(verts_src)
    out_faces, used, incidence = [], set(), {}
    add_used = used.add
    if checkpoint is not None:
        checkpoint('surface_proximity_validated_faces')
    raw_faces = _numpy_2d_list(faces_src, ('i', 'u'))
    face_iter = raw_faces if raw_faces is not None else faces_src
    for row in face_iter:
        tick('validated_faces')
        if len(row) != 3:
            raise _DomainError('surface_invalid_triangle_indices')
        a, b, c = row[0], row[1], row[2]
        if type(a) is int and type(b) is int and type(c) is int:
            if not (0 <= a < num_verts and 0 <= b < num_verts and 0 <= c < num_verts):
                raise _DomainError('surface_invalid_triangle_indices')
        else:
            for index in (a, b, c):
                t = type(index)
                if t not in valid_int_types:
                    if not isinstance(index, Integral) or isinstance(index, bool):
                        raise _DomainError('surface_invalid_triangle_indices')
                    valid_int_types.add(t)
                if not 0 <= index < num_verts:
                    raise _DomainError('surface_invalid_triangle_indices')
            a, b, c = int(a), int(b), int(c)
        out_faces.append((a, b, c))
        add_used(a)
        add_used(b)
        add_used(c)
        e0 = (a, b) if a <= b else (b, a)
        e1 = (b, c) if b <= c else (c, b)
        e2 = (c, a) if c <= a else (a, c)
        incidence[e0] = incidence.get(e0, 0) + 1
        incidence[e1] = incidence.get(e1, 0) + 1
        incidence[e2] = incidence.get(e2, 0) + 1"""

_P2_C_NEW = """def _admit_one(mesh, tick, valid_int_types, *, checkpoint=None, verts=None, faces=None):
    verts_src = mesh.vertices if verts is None else verts
    faces_src = mesh.faces if faces is None else faces
    num_verts = len(verts_src)
    edge_shift = max(1, num_verts.bit_length())
    out_faces, used, incidence = [], set(), {}
    out_append = out_faces.append
    add_used = used.add
    inc_get = incidence.get
    if checkpoint is not None:
        checkpoint('surface_proximity_validated_faces')
    raw_faces = _numpy_2d_list(faces_src, ('i', 'u'))
    face_iter = raw_faces if raw_faces is not None else faces_src
    for row in face_iter:
        tick('validated_faces')
        if len(row) != 3:
            raise _DomainError('surface_invalid_triangle_indices')
        a, b, c = row[0], row[1], row[2]
        if type(a) is int and type(b) is int and type(c) is int:
            if not (0 <= a < num_verts and 0 <= b < num_verts and 0 <= c < num_verts):
                raise _DomainError('surface_invalid_triangle_indices')
        else:
            for index in (a, b, c):
                t = type(index)
                if t not in valid_int_types:
                    if not isinstance(index, Integral) or isinstance(index, bool):
                        raise _DomainError('surface_invalid_triangle_indices')
                    valid_int_types.add(t)
                if not 0 <= index < num_verts:
                    raise _DomainError('surface_invalid_triangle_indices')
            a, b, c = int(a), int(b), int(c)
        out_append((a, b, c))
        add_used(a)
        add_used(b)
        add_used(c)
        e0 = (a << edge_shift) | b if a <= b else (b << edge_shift) | a
        e1 = (b << edge_shift) | c if b <= c else (c << edge_shift) | b
        e2 = (c << edge_shift) | a if c <= a else (a << edge_shift) | c
        incidence[e0] = inc_get(e0, 0) + 1
        incidence[e1] = inc_get(e1, 0) + 1
        incidence[e2] = inc_get(e2, 0) + 1"""


def _patch_p2_a(sp_path: Path) -> None:
    _patch_sp_target(sp_path, _P2_A_OLD, _P2_A_NEW, "P2_A")


def _patch_p2_b(sp_path: Path) -> None:
    _patch_sp_target(sp_path, _P2_B_OLD, _P2_B_NEW, "P2_B")


def _patch_p2_c(sp_path: Path) -> None:
    _patch_sp_target(sp_path, _P2_C_OLD, _P2_C_NEW, "P2_C")


def make_p2_arms() -> dict[str, Path]:
    arm_a = ensure_frozen_arm_a()
    arm_i = ensure_frozen_arm_i()

    def clone_from_i(dirname: str) -> Path:
        dst = P2_ARMS_ROOT / dirname
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(arm_i, dst)
        return dst

    arm_k = clone_from_i("arm_k_p2a_frame")
    _patch_p2_a(arm_k / "human_eye_plugin/surface_proximity.py")

    arm_l = clone_from_i("arm_l_p2b_fast_tris")
    _patch_p2_b(arm_l / "human_eye_plugin/surface_proximity.py")

    arm_m = clone_from_i("arm_m_p2c_admit")
    _patch_p2_c(arm_m / "human_eye_plugin/surface_proximity.py")

    arm_n = clone_from_i("arm_n_p2_all")
    _patch_p2_a(arm_n / "human_eye_plugin/surface_proximity.py")
    _patch_p2_b(arm_n / "human_eye_plugin/surface_proximity.py")
    _patch_p2_c(arm_n / "human_eye_plugin/surface_proximity.py")

    return {"A": arm_a, "I": arm_i, "K": arm_k, "L": arm_l, "M": arm_m, "N": arm_n}


def _verify_exact_frame_and_tree_parity(arm_objs: list, workloads: dict) -> dict:
    """Verify exact (origin, factor, prepared bounds, topology) and raw trees across A, I, K, L, M, N."""
    ref = arm_objs[0]  # Arm A
    digests = {}
    for w in workloads["singles"]:
        wid = w["id"]
        for mode_label, pair_key in (("tuple", "tuple_pair"), ("ndarray", "ndarray_pair")):
            l_m, r_m = w[pair_key]
            activate_arm(ref)
            b0 = ref.sp._Work(NOOP, {})
            recs0, topo0 = ref.sp._admit((l_m, r_m), b0)
            orig0, fac0, prep0 = ref.sp._integer_frame(recs0, b0)
            ta = measure_raw_trees_for_arm(ref, l_m, r_m)
            for arm in arm_objs[1:]:
                activate_arm(arm)
                bx = arm.sp._Work(NOOP, {})
                recsx, topox = arm.sp._admit((l_m, r_m), bx)
                origx, facx, prepx = arm.sp._integer_frame(recsx, bx)
                _require(topo0 == topox, f"{wid}.{mode_label}.{arm.name}: topology mismatch")
                _require(orig0 == origx and fac0 == facx, f"{wid}.{mode_label}.{arm.name}: origin/factor mismatch")
                _require(b0.counts["work_units"] == bx.counts["work_units"], f"{wid}.{mode_label}.{arm.name}: prep work mismatch")
                for side in (0, 1):
                    _require(len(prep0[side]) == len(prepx[side]), f"{wid}.{arm.name}: side {side} len mismatch")
                    for idx, (t0, tx) in enumerate(zip(prep0[side], prepx[side])):
                        _require(
                            t0[0] == tx[0] and t0[1] == tx[1] and t0[2] == tx[2]
                            and tuple(t0[3]) == tuple(tx[3]) and t0[4] == tx[4],
                            f"{wid}.{mode_label}.{arm.name}: tri {side}/{idx} mismatch",
                        )
                t_other = measure_raw_trees_for_arm(arm, l_m, r_m)
                assert_raw_trees_equal(ta["roots"][0], t_other["roots"][0], f"{wid}.{mode_label}.{arm.name}.L")
                assert_raw_trees_equal(ta["roots"][1], t_other["roots"][1], f"{wid}.{mode_label}.{arm.name}.R")
            if mode_label == "tuple":
                digests[wid] = ta["combined_tree_sha256"]
    return digests


def _run_3shot_prep_probe(arm_objs: list, workloads: dict) -> dict:
    """Separate 3-shot median measurement of _admit + _integer_frame (tuple & ndarray)."""
    out = {}
    targets = ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Sheet_Parallel_5um", "Rotated_30deg_Spheres", "Tube_Coiled_Loose", "G508_Peer_000", "Sparse_100kV_Degenerate_MixedBit")
    for wid in targets:
        spec = next(x for x in workloads["singles"] if x["id"] == wid)
        row = {}
        for kind in ("tuple", "ndarray"):
            l_m, r_m = spec["tuple_pair"] if kind == "tuple" else spec["ndarray_pair"]
            krow = {}
            for arm in arm_objs:
                ad_shots, fr_shots, tot_shots = [], [], []
                for _ in range(3):
                    activate_arm(arm)
                    bd = arm.sp._Work(NOOP, {})
                    t0 = time.perf_counter_ns()
                    recs, _ = arm.sp._admit((l_m, r_m), bd)
                    t1 = time.perf_counter_ns()
                    _ = arm.sp._integer_frame(recs, bd)
                    t2 = time.perf_counter_ns()
                    ad_shots.append((t1 - t0) / 1e6)
                    fr_shots.append((t2 - t1) / 1e6)
                    tot_shots.append((t2 - t0) / 1e6)
                krow[arm.name] = {
                    "admit_med_ms": round(statistics.median(ad_shots), 4),
                    "frame_plus_tris_med_ms": round(statistics.median(fr_shots), 4),
                    "total_prep_med_ms": round(statistics.median(tot_shots), 4),
                }
            i_med = krow["I"]["total_prep_med_ms"]
            for arm in arm_objs:
                if arm.name not in ("A", "I"):
                    krow[arm.name]["prep_reduction_vs_I_pct"] = round(((i_med - krow[arm.name]["total_prep_med_ms"]) / i_med) * 100.0, 2) if i_med > 0 else 0.0
            row[kind] = krow
        out[wid] = row
        kt = row["tuple"]
        print(
            f"  [prep-3shot {wid:<32}] I={kt['I']['total_prep_med_ms']:.2f}ms "
            + " ".join(f"{a.name}={kt[a.name]['total_prep_med_ms']:.2f}ms({kt[a.name]['prep_reduction_vs_I_pct']:+.1f}%)" for a in arm_objs if a.name not in ("A", "I")),
            flush=True,
        )
    return out


def _screen_suite(arm_objs: list, workloads: dict, *, warmup: int, repeats: int) -> dict:
    singles_out = {}
    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]
        l_np, r_np = w["ndarray_pair"]

        tup_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_tup, r=r_tup: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        np_res = run_paired_timing(
            arm_objs,
            lambda a, l=l_np, r=r_np: (lambda: a.sp.measure_surface_proximity(l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True)),
            warmup=warmup, repeats=repeats, sig_fn=_surface_sig,
        )
        work_by_arm = {a.name: _work_summary(tup_res["last_outs"][a.name]["work"]) for a in arm_objs}
        base_n = arm_objs[0].name
        for a in arm_objs[1:]:
            _require(work_by_arm[a.name]["work_units"] == work_by_arm[base_n]["work_units"],
                     f"{wid}.{a.name}: work_units mismatch vs {base_n}")
        singles_out[wid] = {
            "classification": w["classification"],
            "role": w["role"],
            "uncached_tuple": {"arms": tup_res["arms"], "paired_vs_ref": tup_res["paired_vs_ref"], "work": work_by_arm},
            "uncached_ndarray": {"arms": np_res["arms"], "paired_vs_ref": np_res["paired_vs_ref"]},
        }
        line = " ".join(f"{a.name}={tup_res['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [p2-single {wid:<32}] {line}", flush=True)

    batches_out = {}
    for b in workloads["batches"]:
        bid = b["id"]
        t_tup, peers_tup = b["tuple_batch"]
        t_np, peers_np = b["ndarray_batch"]

        def run_batch(arm, tg, ps, use_cache: bool):
            cache = {} if use_cache else None
            sigs = []
            agg = {}
            for p in ps:
                kw = {"_mesh_cache": cache} if use_cache else {}
                r = arm.sp.measure_surface_proximity(tg, p, NOOP, retain_exact_rank=True, retain_witness_triangles=True, **kw)
                sigs.append(_surface_sig(r))
                for k, v in _work_summary(r["work"]).items():
                    if isinstance(v, int):
                        agg[k] = agg.get(k, 0) + v
            return sigs, agg

        unc_t = run_paired_timing(arm_objs, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, False)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        unc_n = run_paired_timing(arm_objs, lambda a, tg=t_np, ps=peers_np: (lambda: run_batch(a, tg, ps, False)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        cac_t = run_paired_timing(arm_objs, lambda a, tg=t_tup, ps=peers_tup: (lambda: run_batch(a, tg, ps, True)), warmup=min(1, warmup), repeats=repeats, sig_fn=lambda p: p[0])
        batches_out[bid] = {
            "classification": b["classification"],
            "pair_count": b["pair_count"],
            "uncached_tuple": {"arms": unc_t["arms"], "paired_vs_ref": unc_t["paired_vs_ref"], "work_agg": {a.name: unc_t["last_outs"][a.name][1] for a in arm_objs}},
            "uncached_ndarray": {"arms": unc_n["arms"], "paired_vs_ref": unc_n["paired_vs_ref"]},
            "secondary_cached_tuple": {"arms": cac_t["arms"], "paired_vs_ref": cac_t["paired_vs_ref"], "work_agg": {a.name: cac_t["last_outs"][a.name][1] for a in arm_objs}},
        }
        line = " ".join(f"{a.name}={unc_t['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [p2-batch  {bid:<32}] {line}", flush=True)

    return {"singles": singles_out, "batches": batches_out}


def main() -> int:
    parser = argparse.ArgumentParser(description="BVH-042-P2 Admission & Dyadic Frame Ablation")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--screen-repeats", type=int, default=7)
    parser.add_argument("--confirm-repeats", type=int, default=30)
    parser.add_argument("--skip-confirm", action="store_true")
    args = parser.parse_args()

    arm_paths = make_p2_arms()
    arm_a = load_arm_modules("A", arm_paths["A"])
    arm_i = load_arm_modules("I", arm_paths["I"])
    _require(arm_a.source_sha256 == FROZEN_RUNTIME_SHA, f"Arm A sha mismatch: {arm_a.source_sha256}")
    _require(arm_i.source_sha256 == FROZEN_ARM_I_RUNTIME_SHA, f"Arm I sha mismatch: {arm_i.source_sha256}")
    arm_k = load_arm_modules("K", arm_paths["K"])
    arm_l = load_arm_modules("L", arm_paths["L"])
    arm_m = load_arm_modules("M", arm_paths["M"])
    arm_n = load_arm_modules("N", arm_paths["N"])

    workloads = build_042_workloads()
    print("=== Verifying 100% Exact Frame, Coordinates, Bounds, Topology & Tree Parity Across A, I, K, L, M, N ===", flush=True)
    digests = _verify_exact_frame_and_tree_parity([arm_a, arm_i, arm_k, arm_l, arm_m, arm_n], workloads)

    print("\n=== Separate 3-Shot Direct Prep (_admit + _integer_frame) Probe ===", flush=True)
    prep_probe = _run_3shot_prep_probe([arm_a, arm_i, arm_k, arm_l, arm_m, arm_n], workloads)

    print(f"\n=== Paired P2 Screening vs Arm I (warmup={args.warmup}, repeats={args.screen_repeats}) ===", flush=True)
    screen = _screen_suite([arm_i, arm_k, arm_l, arm_m, arm_n], workloads, warmup=args.warmup, repeats=args.screen_repeats)

    heavy_ids = ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Sheet_Parallel_5um", "Rotated_30deg_Spheres", "Tube_Coiled_Loose")
    guard_ids = ("G508_Peer_000", "G508_Competing_001", "Control_12F_Linear", "Sparse_100kV_Degenerate_MixedBit", "D48_Real_47pairs", "Assembly24_Obj014_23pairs")
    decisions = {}
    for cname in ("K", "L", "M", "N"):
        prep_ge15 = sum(1 for hid in heavy_ids if prep_probe[hid]["tuple"][cname]["prep_reduction_vs_I_pct"] >= 15.0)
        wall_reds = [{"id": hid, "tuple_vs_I_pct": screen["singles"][hid]["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"],
                      "ndarray_vs_I_pct": screen["singles"][hid]["uncached_ndarray"]["paired_vs_ref"][cname]["median_reduction_pct"]} for hid in heavy_ids]
        any_wall_gain = sum(1 for r in wall_reds if r["tuple_vs_I_pct"] >= 3.0)
        max_reg = 0.0
        for gid in guard_ids:
            sec = screen["singles"] if gid in screen["singles"] else screen["batches"]
            for kind in ("uncached_tuple", "uncached_ndarray"):
                pct = sec[gid][kind]["paired_vs_ref"][cname]["median_reduction_pct"]
                if -pct > max_reg:
                    max_reg = round(-pct, 2)
        decisions[cname] = {
            "prep_reductions_vs_I_pct": {hid: prep_probe[hid]["tuple"][cname]["prep_reduction_vs_I_pct"] for hid in heavy_ids},
            "heavy_wall_reductions_vs_I_pct": wall_reds,
            "count_prep_ge_15pct": prep_ge15,
            "count_heavy_wall_ge_3pct": any_wall_gain,
            "max_guard_regression_vs_I_pct": max_reg,
            "meets_p2_bar": (prep_ge15 >= 2 and any_wall_gain >= 2 and max_reg < 5.0),
        }
    print("P2 Decisions:", json.dumps(decisions, indent=2), flush=True)

    winner = None
    best_avg = -1.0
    for cname in ("K", "L", "M", "N"):
        if not decisions[cname]["meets_p2_bar"]:
            continue
        avg = statistics.mean(x["tuple_vs_I_pct"] for x in decisions[cname]["heavy_wall_reductions_vs_I_pct"])
        if cname == "N":
            # Prefer a simpler single-technique winner (K/L/M) if within 1.5pp of combined N
            best_single = max((statistics.mean(x["tuple_vs_I_pct"] for x in decisions[s]["heavy_wall_reductions_vs_I_pct"])
                               for s in ("K", "L", "M") if decisions[s]["meets_p2_bar"]), default=-999.0)
            if avg < best_single + 1.5:
                continue
        if avg > best_avg:
            best_avg = avg
            winner = cname

    confirm30 = None
    if not args.skip_confirm and winner is not None:
        win_arm = {"K": arm_k, "L": arm_l, "M": arm_m, "N": arm_n}[winner]
        print(f"\n=== Stage 30-Repeat Paired Confirmation (A vs I vs {winner}) ===", flush=True)
        confirm30 = _screen_suite([arm_a, arm_i, win_arm], workloads, warmup=args.warmup, repeats=args.confirm_repeats)

    verdict = f"CANDIDATE_{winner}_VALIDATED_P2_RESEARCH_ONLY" if winner is not None else "NO_GAIN_KEEP_ARM_I"
    out = {
        "schema": "m3-bvh-kernel-042-p2-results-v1",
        "branch": "codex/m3-bvh-exact-build-pipeline-042",
        "frozen_041_commit": FROZEN_COMMIT,
        "frozen_041_runtime_sha256": FROZEN_RUNTIME_SHA,
        "frozen_arm_i_commit": FROZEN_ARM_I_COMMIT,
        "frozen_arm_i_runtime_sha256": FROZEN_ARM_I_RUNTIME_SHA,
        "environment": _win32_env_info(),
        "arm_identities": {
            a.name: {"runtime_source_sha256": a.source_sha256, "surface_geometry_sha256": a.sg_raw_sha256, "surface_proximity_sha256": a.sp_raw_sha256}
            for a in (arm_a, arm_i, arm_k, arm_l, arm_m, arm_n)
        },
        "tree_digests": digests,
        "prep_3shot_probe": prep_probe,
        "p2_screening": screen,
        "p2_decisions": decisions,
        "selected_winner": winner,
        "confirm_30_repeats_A_I_Winner": confirm30,
        "verdict": verdict,
    }
    (BENCH_DIR / "KERNEL_042_P2_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE 042-P2. Verdict={verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
