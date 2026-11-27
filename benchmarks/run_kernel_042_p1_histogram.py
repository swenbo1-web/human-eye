"""M3 BVH-042 Phase 1 (042-P1): Exact 11-Cut Division-Free Histogram & SAH Eval Research Harness.

Evaluates isolated P1 candidate arms G (H1: 11-cut histogram), H (H2: scratch reuse +
empty-bin skip + scalar-first SAH compare), I (H1+H2), and J (H1+H2+H3 fused 3-axis
histogram) against frozen 041 reference Arm A (119327bbb) and promoted 042 Phase-0
baseline Arm F (5102f1fef).
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
    _win32_process_mem,
    activate_arm,
    assert_raw_trees_equal,
    build_042_workloads,
    ensure_frozen_arm_a,
    load_arm_modules,
    measure_raw_trees_for_arm,
    profile_phases_single_pair,
    run_paired_timing,
)

BENCH_DIR = Path(__file__).resolve().parent
P1_ARMS_ROOT = ROOT / "scratch" / "042_p1_arms"
FROZEN_ARM_F_COMMIT = "5102f1fefc6ebee8b0ca5d7ad0c03530b672add4"
FROZEN_ARM_F_RUNTIME_SHA = "b0e4093dadf3eff8c9be18442922d802a4fa59adf2035f37958e8d5f32597dcd"

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


def ensure_frozen_arm_f() -> Path:
    """Materialize Arm F (5102f1fef) into scratch/042_p1_arms/arm_f_042 via git archive."""
    arm_f = P1_ARMS_ROOT / "arm_f_042"
    marker = arm_f / "human_eye_plugin/surface_geometry.py"
    if marker.exists():
        return arm_f
    arm_f.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "archive", "--format=tar", FROZEN_ARM_F_COMMIT, "--", *_RUNTIME_FILES],
        cwd=str(ROOT), check=True, stdout=subprocess.PIPE,
    )
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
        tf.extractall(path=arm_f)
    _require(marker.exists(), f"Failed to extract frozen Arm F commit {FROZEN_ARM_F_COMMIT}")
    return arm_f


def _patch_sg_target(sg_path: Path, old_block: str, new_block: str, label: str) -> None:
    raw = sg_path.read_bytes()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    old_n = old_block.replace("\r\n", "\n")
    new_n = new_block.replace("\r\n", "\n")
    _require(old_n in text, f"{label}: target block missing in {sg_path}")
    updated = text.replace(old_n, new_n, 1)
    sg_path.write_bytes(updated.encode("utf-8").replace(b"\n", eol))


# Exact H1 patch block replacing lines 229..246 of Arm F surface_geometry.py
_H1_OLD = """            ck = 6 + axis
            max_bin = _SAH_BINS - 1
            for idx in ids:
                row = flat_bounds[idx]
                b = ((row[ck] - cmin) * _SAH_BINS) // cspan
                if b > max_bin:
                    b = max_bin
                c = bcnt[b]
                if c == 0:
                    blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                else:
                    if row[0] < blx[b]: blx[b] = row[0]
                    if row[1] < bly[b]: bly[b] = row[1]
                    if row[2] < blz[b]: blz[b] = row[2]
                    if row[3] > bhx[b]: bhx[b] = row[3]
                    if row[4] > bhy[b]: bhy[b] = row[4]
                    if row[5] > bhz[b]: bhz[b] = row[5]
                bcnt[b] = c + 1"""

_H1_NEW = """            ck = 6 + axis
            acc = cspan + 11
            t1 = cmin + acc // 12; acc += cspan
            t2 = cmin + acc // 12; acc += cspan
            t3 = cmin + acc // 12; acc += cspan
            t4 = cmin + acc // 12; acc += cspan
            t5 = cmin + acc // 12; acc += cspan
            t6 = cmin + acc // 12; acc += cspan
            t7 = cmin + acc // 12; acc += cspan
            t8 = cmin + acc // 12; acc += cspan
            t9 = cmin + acc // 12; acc += cspan
            t10 = cmin + acc // 12; acc += cspan
            t11 = cmin + acc // 12
            if cp is None:
                for idx in ids:
                    row = flat_bounds[idx]
                    cval = row[ck]
                    if cval < t6:
                        if cval < t3:
                            b = 0 if cval < t1 else (1 if cval < t2 else 2)
                        else:
                            b = 3 if cval < t4 else (4 if cval < t5 else 5)
                    else:
                        if cval < t9:
                            b = 6 if cval < t7 else (7 if cval < t8 else 8)
                        else:
                            b = 9 if cval < t10 else (10 if cval < t11 else 11)
                    c = bcnt[b]
                    if c == 0:
                        blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                    else:
                        if row[0] < blx[b]: blx[b] = row[0]
                        if row[1] < bly[b]: bly[b] = row[1]
                        if row[2] < blz[b]: blz[b] = row[2]
                        if row[3] > bhx[b]: bhx[b] = row[3]
                        if row[4] > bhy[b]: bhy[b] = row[4]
                        if row[5] > bhz[b]: bhz[b] = row[5]
                    bcnt[b] = c + 1
            else:
                for start in range(0, n, 256):
                    cp('surface_proximity_surface_bvh_build')
                    for idx in ids[start:start + 256]:
                        row = flat_bounds[idx]
                        cval = row[ck]
                        if cval < t6:
                            if cval < t3:
                                b = 0 if cval < t1 else (1 if cval < t2 else 2)
                            else:
                                b = 3 if cval < t4 else (4 if cval < t5 else 5)
                        else:
                            if cval < t9:
                                b = 6 if cval < t7 else (7 if cval < t8 else 8)
                            else:
                                b = 9 if cval < t10 else (10 if cval < t11 else 11)
                        c = bcnt[b]
                        if c == 0:
                            blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                        else:
                            if row[0] < blx[b]: blx[b] = row[0]
                            if row[1] < bly[b]: bly[b] = row[1]
                            if row[2] < blz[b]: blz[b] = row[2]
                            if row[3] > bhx[b]: bhx[b] = row[3]
                            if row[4] > bhy[b]: bhy[b] = row[4]
                            if row[5] > bhz[b]: bhz[b] = row[5]
                        bcnt[b] = c + 1"""


def _patch_h1(sg_path: Path) -> None:
    _patch_sg_target(sg_path, _H1_OLD, _H1_NEW, "H1")


def _patch_h2(sg_path: Path) -> None:
    _patch_sg_target(
        sg_path,
        "_SAH_BINS = 12\n_SAH_MIN_N = 12\n_SAH_MAX_DEPTH = 20\n\n\ndef _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth):",
        """_SAH_BINS = 12
_SAH_MIN_N = 12
_SAH_MAX_DEPTH = 20
_ZERO_SAH_BINS = [0] * _SAH_BINS


def _alloc_sah_scratch():
    return (
        [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
        [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
        [0] * _SAH_BINS, [0] * _SAH_BINS,
    )


def _build_sah_bvh(flat_bounds, budget, ids, leaf_size, depth, scratch=None):""",
        "H2_hdr",
    )
    _patch_sg_target(
        sg_path,
        """    if sah_eligible:
        best_cost = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        for axis in (0, 1, 2):
            cmin, cmax = cbounds[axis]
            if cmax <= cmin:
                continue
            cspan = cmax - cmin
            bcnt = [0] * _SAH_BINS
            blx = [0] * _SAH_BINS
            bly = [0] * _SAH_BINS
            blz = [0] * _SAH_BINS
            bhx = [0] * _SAH_BINS
            bhy = [0] * _SAH_BINS
            bhz = [0] * _SAH_BINS""",
        """    if sah_eligible:
        if scratch is None:
            scratch = _alloc_sah_scratch()
        best_cost = None
        best_tie = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        bcnt, blx, bly, blz, bhx, bhy, bhz, right_area, right_cnt = scratch
        for axis in (0, 1, 2):
            cmin, cmax = cbounds[axis]
            if cmax <= cmin:
                continue
            cspan = cmax - cmin
            bcnt[:] = _ZERO_SAH_BINS""",
        "H2_scratch",
    )
    _patch_sg_target(
        sg_path,
        """            right_area = [0] * _SAH_BINS
            right_cnt = [0] * _SAH_BINS
            rc = 0
            has_r = False
            rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
            for b in range(_SAH_BINS - 1, 0, -1):
                cnt = bcnt[b]
                if cnt:
                    rc += cnt
                    if not has_r:
                        rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_r = True
                    else:
                        if blx[b] < rx0: rx0 = blx[b]
                        if bly[b] < ry0: ry0 = bly[b]
                        if blz[b] < rz0: rz0 = blz[b]
                        if bhx[b] > rx1: rx1 = bhx[b]
                        if bhy[b] > ry1: ry1 = bhy[b]
                        if bhz[b] > rz1: rz1 = bhz[b]
                right_cnt[b - 1] = rc
                if has_r:
                    dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                    right_area[b - 1] = dx * dy + dy * dz + dz * dx
            lc = 0
            has_l = False
            lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
            for b in range(_SAH_BINS - 1):
                cnt = bcnt[b]
                if cnt:
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: ly1 = bhy[b]
                        if bhz[b] > lz1: lz1 = bhz[b]
                rc_s = right_cnt[b]
                if lc >= min_side and rc_s >= min_side:
                    dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                    larea = dx * dy + dy * dz + dz * dx
                    key = (lc * larea + rc_s * right_area[b], abs(lc - rc_s), axis, b + 1)
                    if best_cost is None or key < best_cost:
                        best_cost = key
                        best_axis = axis
                        best_split = b + 1
                        best_cmin = cmin
                        best_cspan = cspan""",
        """            rc = 0
            has_r = False
            cur_rarea = 0
            rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
            for b in range(_SAH_BINS - 1, 0, -1):
                cnt = bcnt[b]
                if cnt:
                    rc += cnt
                    if not has_r:
                        rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_r = True
                    else:
                        if blx[b] < rx0: rx0 = blx[b]
                        if bly[b] < ry0: ry0 = bly[b]
                        if blz[b] < rz0: rz0 = blz[b]
                        if bhx[b] > rx1: rx1 = bhx[b]
                        if bhy[b] > ry1: ry1 = bhy[b]
                        if bhz[b] > rz1: rz1 = bhz[b]
                    dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                    cur_rarea = dx * dy + dy * dz + dz * dx
                right_cnt[b - 1] = rc
                right_area[b - 1] = cur_rarea
            lc = 0
            has_l = False
            lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
            for b in range(_SAH_BINS - 1):
                cnt = bcnt[b]
                if not cnt:
                    continue
                lc += cnt
                if not has_l:
                    lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                    has_l = True
                else:
                    if blx[b] < lx0: lx0 = blx[b]
                    if bly[b] < ly0: ly0 = bly[b]
                    if blz[b] < lz0: lz0 = blz[b]
                    if bhx[b] > lx1: lx1 = bhx[b]
                    if bhy[b] > ly1: ly1 = bhy[b]
                    if bhz[b] > lz1: lz1 = bhz[b]
                rc_s = right_cnt[b]
                if lc >= min_side and rc_s >= min_side:
                    dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                    larea = dx * dy + dy * dz + dz * dx
                    cost = lc * larea + rc_s * right_area[b]
                    if best_cost is None or cost < best_cost:
                        best_cost = cost
                        best_tie = (abs(lc - rc_s), axis, b + 1)
                        best_axis = axis
                        best_split = b + 1
                        best_cmin = cmin
                        best_cspan = cspan
                    elif cost == best_cost:
                        tie = (abs(lc - rc_s), axis, b + 1)
                        if tie < best_tie:
                            best_tie = tie
                            best_axis = axis
                            best_split = b + 1
                            best_cmin = cmin
                            best_cspan = cspan""",
        "H2_eval",
    )
    _patch_sg_target(
        sg_path,
        """                    _build_sah_bvh(flat_bounds, budget, left_ids, leaf_size, depth + 1),
                    _build_sah_bvh(flat_bounds, budget, right_ids, leaf_size, depth + 1),""",
        """                    _build_sah_bvh(flat_bounds, budget, left_ids, leaf_size, depth + 1, scratch),
                    _build_sah_bvh(flat_bounds, budget, right_ids, leaf_size, depth + 1, scratch),""",
        "H2_rec_sah",
    )
    _patch_sg_target(
        sg_path,
        """        _build_sah_bvh(flat_bounds, budget, ids[:mid], leaf_size, depth + 1),
        _build_sah_bvh(flat_bounds, budget, ids[mid:], leaf_size, depth + 1),""",
        """        _build_sah_bvh(flat_bounds, budget, ids[:mid], leaf_size, depth + 1, scratch),
        _build_sah_bvh(flat_bounds, budget, ids[mid:], leaf_size, depth + 1, scratch),""",
        "H2_rec_med",
    )


def _patch_h3_3axis(sg_path: Path) -> None:
    """Apply H1+H2 first, then fuse 3-axis 11-Cut binning into one pass when all 3 spans > 0."""
    _patch_h1(sg_path)
    _patch_h2(sg_path)
    _patch_sg_target(
        sg_path,
        """def _alloc_sah_scratch():
    return (
        [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
        [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
        [0] * _SAH_BINS, [0] * _SAH_BINS,
    )""",
        """def _alloc_sah_scratch():
    def bank():
        return (
            [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
            [0] * _SAH_BINS, [0] * _SAH_BINS, [0] * _SAH_BINS,
            [0] * _SAH_BINS, [0] * _SAH_BINS,
        )
    return (bank(), bank(), bank())""",
        "H3_scratch",
    )
    old_axis_section = """        bcnt, blx, bly, blz, bhx, bhy, bhz, right_area, right_cnt = scratch
        for axis in (0, 1, 2):"""
    _require(old_axis_section in sg_path.read_text(encoding="utf-8"), "H3_axis_hdr missing")
    # Build H3 around the H2 axis loop cleanly by replacing the entire SAH_ELIGIBLE axis block
    text = sg_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    marker_start = "    if sah_eligible:\n        if scratch is None:\n            scratch = _alloc_sah_scratch()\n        best_cost = None"
    marker_end = "        if best_axis >= 0:\n"
    i0 = text.index(marker_start)
    i1 = text.index(marker_end)
    h3_block = '''    if sah_eligible:
        if scratch is None:
            scratch = _alloc_sah_scratch()
        best_cost = None
        best_tie = None
        best_axis = -1
        best_split = 0
        best_cmin = 0
        best_cspan = 1
        min_side = max(1, n >> 4)
        cbounds = ((c0x, c1x), (c0y, c1y), (c0z, c1z))
        if c1x > c0x and c1y > c0y and c1z > c0z:
            # Fused 3-axis 11-Cut binning: unpack flat_bounds[idx] once per triangle.
            sp0 = c1x - c0x; acc = sp0 + 11
            x1 = c0x + acc // 12; acc += sp0; x2 = c0x + acc // 12; acc += sp0
            x3 = c0x + acc // 12; acc += sp0; x4 = c0x + acc // 12; acc += sp0
            x5 = c0x + acc // 12; acc += sp0; x6 = c0x + acc // 12; acc += sp0
            x7 = c0x + acc // 12; acc += sp0; x8 = c0x + acc // 12; acc += sp0
            x9 = c0x + acc // 12; acc += sp0; x10 = c0x + acc // 12; acc += sp0; x11 = c0x + acc // 12

            sp1 = c1y - c0y; acc = sp1 + 11
            y1 = c0y + acc // 12; acc += sp1; y2 = c0y + acc // 12; acc += sp1
            y3 = c0y + acc // 12; acc += sp1; y4 = c0y + acc // 12; acc += sp1
            y5 = c0y + acc // 12; acc += sp1; y6 = c0y + acc // 12; acc += sp1
            y7 = c0y + acc // 12; acc += sp1; y8 = c0y + acc // 12; acc += sp1
            y9 = c0y + acc // 12; acc += sp1; y10 = c0y + acc // 12; acc += sp1; y11 = c0y + acc // 12

            sp2 = c1z - c0z; acc = sp2 + 11
            z1 = c0z + acc // 12; acc += sp2; z2 = c0z + acc // 12; acc += sp2
            z3 = c0z + acc // 12; acc += sp2; z4 = c0z + acc // 12; acc += sp2
            z5 = c0z + acc // 12; acc += sp2; z6 = c0z + acc // 12; acc += sp2
            z7 = c0z + acc // 12; acc += sp2; z8 = c0z + acc // 12; acc += sp2
            z9 = c0z + acc // 12; acc += sp2; z10 = c0z + acc // 12; acc += sp2; z11 = c0z + acc // 12

            b0 = scratch[0]; b1 = scratch[1]; b2 = scratch[2]
            xc, xlx, xly, xlz, xhx, xhy, xhz, _, _ = b0
            yc, ylx, yly, ylz, yhx, yhy, yhz, _, _ = b1
            zc, zlx, zly, zlz, zhx, zhy, zhz, _, _ = b2
            xc[:] = _ZERO_SAH_BINS; yc[:] = _ZERO_SAH_BINS; zc[:] = _ZERO_SAH_BINS

            if cp is None:
                for idx in ids:
                    r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                    if cx < x6:
                        if cx < x3: bx = 0 if cx < x1 else (1 if cx < x2 else 2)
                        else: bx = 3 if cx < x4 else (4 if cx < x5 else 5)
                    else:
                        if cx < x9: bx = 6 if cx < x7 else (7 if cx < x8 else 8)
                        else: bx = 9 if cx < x10 else (10 if cx < x11 else 11)
                    c = xc[bx]
                    if c == 0: xlx[bx], xly[bx], xlz[bx], xhx[bx], xhy[bx], xhz[bx] = r0, r1, r2, r3, r4, r5
                    else:
                        if r0 < xlx[bx]: xlx[bx] = r0
                        if r1 < xly[bx]: xly[bx] = r1
                        if r2 < xlz[bx]: xlz[bx] = r2
                        if r3 > xhx[bx]: xhx[bx] = r3
                        if r4 > xhy[bx]: xhy[bx] = r4
                        if r5 > xhz[bx]: xhz[bx] = r5
                    xc[bx] = c + 1

                    if cy < y6:
                        if cy < y3: by = 0 if cy < y1 else (1 if cy < y2 else 2)
                        else: by = 3 if cy < y4 else (4 if cy < y5 else 5)
                    else:
                        if cy < y9: by = 6 if cy < y7 else (7 if cy < y8 else 8)
                        else: by = 9 if cy < y10 else (10 if cy < y11 else 11)
                    c = yc[by]
                    if c == 0: ylx[by], yly[by], ylz[by], yhx[by], yhy[by], yhz[by] = r0, r1, r2, r3, r4, r5
                    else:
                        if r0 < ylx[by]: ylx[by] = r0
                        if r1 < yly[by]: yly[by] = r1
                        if r2 < ylz[by]: ylz[by] = r2
                        if r3 > yhx[by]: yhx[by] = r3
                        if r4 > yhy[by]: yhy[by] = r4
                        if r5 > yhz[by]: yhz[by] = r5
                    yc[by] = c + 1

                    if cz < z6:
                        if cz < z3: bz = 0 if cz < z1 else (1 if cz < z2 else 2)
                        else: bz = 3 if cz < z4 else (4 if cz < z5 else 5)
                    else:
                        if cz < z9: bz = 6 if cz < z7 else (7 if cz < z8 else 8)
                        else: bz = 9 if cz < z10 else (10 if cz < z11 else 11)
                    c = zc[bz]
                    if c == 0: zlx[bz], zly[bz], zlz[bz], zhx[bz], zhy[bz], zhz[bz] = r0, r1, r2, r3, r4, r5
                    else:
                        if r0 < zlx[bz]: zlx[bz] = r0
                        if r1 < zly[bz]: zly[bz] = r1
                        if r2 < zlz[bz]: zlz[bz] = r2
                        if r3 > zhx[bz]: zhx[bz] = r3
                        if r4 > zhy[bz]: zhy[bz] = r4
                        if r5 > zhz[bz]: zhz[bz] = r5
                    zc[bz] = c + 1
            else:
                for start in range(0, n, 256):
                    cp('surface_proximity_surface_bvh_build')
                    for idx in ids[start:start + 256]:
                        r0, r1, r2, r3, r4, r5, cx, cy, cz = flat_bounds[idx]
                        if cx < x6:
                            if cx < x3: bx = 0 if cx < x1 else (1 if cx < x2 else 2)
                            else: bx = 3 if cx < x4 else (4 if cx < x5 else 5)
                        else:
                            if cx < x9: bx = 6 if cx < x7 else (7 if cx < x8 else 8)
                            else: bx = 9 if cx < x10 else (10 if cx < x11 else 11)
                        c = xc[bx]
                        if c == 0: xlx[bx], xly[bx], xlz[bx], xhx[bx], xhy[bx], xhz[bx] = r0, r1, r2, r3, r4, r5
                        else:
                            if r0 < xlx[bx]: xlx[bx] = r0
                            if r1 < xly[bx]: xly[bx] = r1
                            if r2 < xlz[bx]: xlz[bx] = r2
                            if r3 > xhx[bx]: xhx[bx] = r3
                            if r4 > xhy[bx]: xhy[bx] = r4
                            if r5 > xhz[bx]: xhz[bx] = r5
                        xc[bx] = c + 1

                        if cy < y6:
                            if cy < y3: by = 0 if cy < y1 else (1 if cy < y2 else 2)
                            else: by = 3 if cy < y4 else (4 if cy < y5 else 5)
                        else:
                            if cy < y9: by = 6 if cy < y7 else (7 if cy < y8 else 8)
                            else: by = 9 if cy < y10 else (10 if cy < y11 else 11)
                        c = yc[by]
                        if c == 0: ylx[by], yly[by], ylz[by], yhx[by], yhy[by], yhz[by] = r0, r1, r2, r3, r4, r5
                        else:
                            if r0 < ylx[by]: ylx[by] = r0
                            if r1 < yly[by]: yly[by] = r1
                            if r2 < ylz[by]: ylz[by] = r2
                            if r3 > yhx[by]: yhx[by] = r3
                            if r4 > yhy[by]: yhy[by] = r4
                            if r5 > yhz[by]: yhz[by] = r5
                        yc[by] = c + 1

                        if cz < z6:
                            if cz < z3: bz = 0 if cz < z1 else (1 if cz < z2 else 2)
                            else: bz = 3 if cz < z4 else (4 if cz < z5 else 5)
                        else:
                            if cz < z9: bz = 6 if cz < z7 else (7 if cz < z8 else 8)
                            else: bz = 9 if cz < z10 else (10 if cz < z11 else 11)
                        c = zc[bz]
                        if c == 0: zlx[bz], zly[bz], zlz[bz], zhx[bz], zhy[bz], zhz[bz] = r0, r1, r2, r3, r4, r5
                        else:
                            if r0 < zlx[bz]: zlx[bz] = r0
                            if r1 < zly[bz]: zly[bz] = r1
                            if r2 < zlz[bz]: zlz[bz] = r2
                            if r3 > zhx[bz]: zhx[bz] = r3
                            if r4 > zhy[bz]: zhy[bz] = r4
                            if r5 > zhz[bz]: zhz[bz] = r5
                        zc[bz] = c + 1

            for axis, cmin, cspan, bank in ((0, c0x, sp0, b0), (1, c0y, sp1, b1), (2, c0z, sp2, b2)):
                bcnt, blx, bly, blz, bhx, bhy, bhz, right_area, right_cnt = bank
                rc = 0
                has_r = False
                cur_rarea = 0
                rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
                for b in range(_SAH_BINS - 1, 0, -1):
                    cnt = bcnt[b]
                    if cnt:
                        rc += cnt
                        if not has_r:
                            rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                            has_r = True
                        else:
                            if blx[b] < rx0: rx0 = blx[b]
                            if bly[b] < ry0: ry0 = bly[b]
                            if blz[b] < rz0: rz0 = blz[b]
                            if bhx[b] > rx1: rx1 = bhx[b]
                            if bhy[b] > ry1: ry1 = bhy[b]
                            if bhz[b] > rz1: rz1 = bhz[b]
                        dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                        cur_rarea = dx * dy + dy * dz + dz * dx
                    right_cnt[b - 1] = rc
                    right_area[b - 1] = cur_rarea
                lc = 0
                has_l = False
                lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
                for b in range(_SAH_BINS - 1):
                    cnt = bcnt[b]
                    if not cnt:
                        continue
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: ly1 = bhy[b]
                        if bhz[b] > lz1: lz1 = bhz[b]
                    rc_s = right_cnt[b]
                    if lc >= min_side and rc_s >= min_side:
                        dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                        larea = dx * dy + dy * dz + dz * dx
                        cost = lc * larea + rc_s * right_area[b]
                        if best_cost is None or cost < best_cost:
                            best_cost = cost
                            best_tie = (abs(lc - rc_s), axis, b + 1)
                            best_axis = axis
                            best_split = b + 1
                            best_cmin = cmin
                            best_cspan = cspan
                        elif cost == best_cost:
                            tie = (abs(lc - rc_s), axis, b + 1)
                            if tie < best_tie:
                                best_tie = tie
                                best_axis = axis
                                best_split = b + 1
                                best_cmin = cmin
                                best_cspan = cspan
        else:
            bcnt, blx, bly, blz, bhx, bhy, bhz, right_area, right_cnt = scratch[0]
            for axis in (0, 1, 2):
                cmin, cmax = cbounds[axis]
                if cmax <= cmin:
                    continue
                cspan = cmax - cmin
                bcnt[:] = _ZERO_SAH_BINS
                ck = 6 + axis
                acc = cspan + 11
                t1 = cmin + acc // 12; acc += cspan
                t2 = cmin + acc // 12; acc += cspan
                t3 = cmin + acc // 12; acc += cspan
                t4 = cmin + acc // 12; acc += cspan
                t5 = cmin + acc // 12; acc += cspan
                t6 = cmin + acc // 12; acc += cspan
                t7 = cmin + acc // 12; acc += cspan
                t8 = cmin + acc // 12; acc += cspan
                t9 = cmin + acc // 12; acc += cspan
                t10 = cmin + acc // 12; acc += cspan
                t11 = cmin + acc // 12
                for idx in ids:
                    row = flat_bounds[idx]
                    cval = row[ck]
                    if cval < t6:
                        if cval < t3: b = 0 if cval < t1 else (1 if cval < t2 else 2)
                        else: b = 3 if cval < t4 else (4 if cval < t5 else 5)
                    else:
                        if cval < t9: b = 6 if cval < t7 else (7 if cval < t8 else 8)
                        else: b = 9 if cval < t10 else (10 if cval < t11 else 11)
                    c = bcnt[b]
                    if c == 0:
                        blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b] = row[0], row[1], row[2], row[3], row[4], row[5]
                    else:
                        if row[0] < blx[b]: blx[b] = row[0]
                        if row[1] < bly[b]: bly[b] = row[1]
                        if row[2] < blz[b]: blz[b] = row[2]
                        if row[3] > bhx[b]: bhx[b] = row[3]
                        if row[4] > bhy[b]: bhy[b] = row[4]
                        if row[5] > bhz[b]: bhz[b] = row[5]
                    bcnt[b] = c + 1
                rc = 0
                has_r = False
                cur_rarea = 0
                rx0 = ry0 = rz0 = rx1 = ry1 = rz1 = 0
                for b in range(_SAH_BINS - 1, 0, -1):
                    cnt = bcnt[b]
                    if cnt:
                        rc += cnt
                        if not has_r:
                            rx0, ry0, rz0, rx1, ry1, rz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                            has_r = True
                        else:
                            if blx[b] < rx0: rx0 = blx[b]
                            if bly[b] < ry0: ry0 = bly[b]
                            if blz[b] < rz0: rz0 = blz[b]
                            if bhx[b] > rx1: rx1 = bhx[b]
                            if bhy[b] > ry1: ry1 = bhy[b]
                            if bhz[b] > rz1: rz1 = bhz[b]
                        dx, dy, dz = rx1 - rx0, ry1 - ry0, rz1 - rz0
                        cur_rarea = dx * dy + dy * dz + dz * dx
                    right_cnt[b - 1] = rc
                    right_area[b - 1] = cur_rarea
                lc = 0
                has_l = False
                lx0 = ly0 = lz0 = lx1 = ly1 = lz1 = 0
                for b in range(_SAH_BINS - 1):
                    cnt = bcnt[b]
                    if not cnt:
                        continue
                    lc += cnt
                    if not has_l:
                        lx0, ly0, lz0, lx1, ly1, lz1 = blx[b], bly[b], blz[b], bhx[b], bhy[b], bhz[b]
                        has_l = True
                    else:
                        if blx[b] < lx0: lx0 = blx[b]
                        if bly[b] < ly0: ly0 = bly[b]
                        if blz[b] < lz0: lz0 = blz[b]
                        if bhx[b] > lx1: lx1 = bhx[b]
                        if bhy[b] > ly1: ly1 = bhy[b]
                        if bhz[b] > lz1: lz1 = bhz[b]
                    rc_s = right_cnt[b]
                    if lc >= min_side and rc_s >= min_side:
                        dx, dy, dz = lx1 - lx0, ly1 - ly0, lz1 - lz0
                        larea = dx * dy + dy * dz + dz * dx
                        cost = lc * larea + rc_s * right_area[b]
                        if best_cost is None or cost < best_cost:
                            best_cost = cost
                            best_tie = (abs(lc - rc_s), axis, b + 1)
                            best_axis = axis
                            best_split = b + 1
                            best_cmin = cmin
                            best_cspan = cspan
                        elif cost == best_cost:
                            tie = (abs(lc - rc_s), axis, b + 1)
                            if tie < best_tie:
                                best_tie = tie
                                best_axis = axis
                                best_split = b + 1
                                best_cmin = cmin
                                best_cspan = cspan
'''
    eol = b"\r\n" if b"\r\n" in sg_path.read_bytes() else b"\n"
    sg_path.write_bytes((text[:i0] + h3_block + text[i1:]).encode("utf-8").replace(b"\n", eol))


def make_p1_arms() -> dict[str, Path]:
    arm_a = ensure_frozen_arm_a()
    arm_f = ensure_frozen_arm_f()

    def clone_from_f(dirname: str) -> Path:
        dst = P1_ARMS_ROOT / dirname
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(arm_f, dst)
        return dst

    arm_g = clone_from_f("arm_g_h1_11cut")
    _patch_h1(arm_g / "human_eye_plugin/surface_geometry.py")

    arm_h = clone_from_f("arm_h_h2_eval_scratch")
    _patch_h2(arm_h / "human_eye_plugin/surface_geometry.py")

    arm_i = clone_from_f("arm_i_h1_h2")
    _patch_h1(arm_i / "human_eye_plugin/surface_geometry.py")
    _patch_h2(arm_i / "human_eye_plugin/surface_geometry.py")

    arm_j = clone_from_f("arm_j_h1_h2_h3_3axis")
    _patch_h3_3axis(arm_j / "human_eye_plugin/surface_geometry.py")

    return {"A": arm_a, "F": arm_f, "G": arm_g, "H": arm_h, "I": arm_i, "J": arm_j}


def _verify_all_trees_and_sigs(arm_objs: list, workloads: dict) -> dict:
    """Verify exact recursive raw tree identity and signature identity across A, F, and all P1 arms."""
    arm_a = arm_objs[0]
    tree_digests = {}
    for w in workloads["singles"]:
        wid = w["id"]
        l_tup, r_tup = w["tuple_pair"]
        ta = measure_raw_trees_for_arm(arm_a, l_tup, r_tup)
        digs = {arm_a.name: ta["combined_tree_sha256"]}
        for arm in arm_objs[1:]:
            tx = measure_raw_trees_for_arm(arm, l_tup, r_tup)
            assert_raw_trees_equal(ta["roots"][0], tx["roots"][0], f"{wid}.{arm.name}.L")
            assert_raw_trees_equal(ta["roots"][1], tx["roots"][1], f"{wid}.{arm.name}.R")
            _require(tx["combined_tree_sha256"] == ta["combined_tree_sha256"], f"{wid}.{arm.name}: tree digest mismatch")
            digs[arm.name] = tx["combined_tree_sha256"]
        tree_digests[wid] = digs
    return tree_digests


def _run_3shot_build_probe(arm_objs: list, workloads: dict) -> dict:
    """Separate instrumented build breakdown (3-shot median) on heavy + G508 fixtures."""
    out = {}
    targets = ("HighRes_1536F_Pair", "Sheet_Dented_2mm", "Sheet_Parallel_5um", "Rotated_30deg_Spheres", "Tube_Coiled_Loose", "G508_Peer_000")
    for wid in targets:
        spec = next(x for x in workloads["singles"] if x["id"] == wid)
        l, r = spec["tuple_pair"]
        row = {}
        for arm in arm_objs:
            bmode = "baseline" if arm.name == "A" else "b1_b2"
            dflat = arm.name != "A"
            # Note: instrumented twin measures F's B1+B2+B4 phases for A/F comparison; for direct G-J real wall time we measure total build_phase directly via _distance_roots!
            shots = []
            for _ in range(3):
                activate_arm(arm)
                budget = arm.sp._Work(NOOP, {})
                recs, _ = arm.sp._admit((l, r), budget)
                _, _, prep = arm.sp._integer_frame(recs, budget)
                t0 = time.perf_counter_ns()
                _ = arm.sp._distance_roots(prep, budget)
                t1 = time.perf_counter_ns()
                shots.append((t1 - t0) / 1e6)
            row[arm.name] = {
                "distance_roots_3shot_median_ms": round(statistics.median(shots), 4),
                "distance_roots_shots_ms": [round(x, 4) for x in shots],
            }
            if arm.name in ("A", "F"):
                row[arm.name]["phase_sample"] = profile_phases_single_pair(arm, l, r, builder_mode=bmode, direct_flat=dflat)
        f_med = row["F"]["distance_roots_3shot_median_ms"]
        for arm in arm_objs:
            if arm.name not in ("A", "F"):
                c_med = row[arm.name]["distance_roots_3shot_median_ms"]
                row[arm.name]["build_reduction_vs_F_pct"] = round(((f_med - c_med) / f_med) * 100.0, 2) if f_med > 0 else 0.0
                a_med = row["A"]["distance_roots_3shot_median_ms"]
                row[arm.name]["build_reduction_vs_A_pct"] = round(((a_med - c_med) / a_med) * 100.0, 2) if a_med > 0 else 0.0
        out[wid] = row
        print(f"  [build-3shot {wid:<24}] A={row['A']['distance_roots_3shot_median_ms']:.2f}ms F={f_med:.2f}ms " + " ".join(f"{a.name}={row[a.name]['distance_roots_3shot_median_ms']:.2f}ms({row[a.name]['build_reduction_vs_F_pct']:+.1f}%)" for a in arm_objs if a.name not in ("A", "F")), flush=True)
    return out


def _screen_suite(arm_objs: list, workloads: dict, *, warmup: int, repeats: int) -> dict:
    """Screen arms with arm_objs[0] (Arm F) as pairing reference."""
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
        if wid == "Control_12F_Linear":
            for a in arm_objs:
                _require(work_by_arm[a.name]["tree_builds"] == 0, f"Control_12F_Linear built trees on {a.name}")

        singles_out[wid] = {
            "classification": w["classification"],
            "role": w["role"],
            "uncached_tuple": {"arms": tup_res["arms"], "paired_vs_ref": tup_res["paired_vs_ref"], "work": work_by_arm},
            "uncached_ndarray": {"arms": np_res["arms"], "paired_vs_ref": np_res["paired_vs_ref"]},
        }
        line = " ".join(f"{a.name}={tup_res['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [p1-single {wid:<32}] {line}", flush=True)

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
        for a in arm_objs:
            _require(cac_t["last_outs"][a.name][1].get("mesh_cache_hits", 0) > 0, f"{bid}.{a.name}: cached 0 hits")
            _require(unc_t["last_outs"][a.name][1].get("mesh_cache_hits", 0) == 0, f"{bid}.{a.name}: uncached hit")
        batches_out[bid] = {
            "classification": b["classification"],
            "pair_count": b["pair_count"],
            "uncached_tuple": {"arms": unc_t["arms"], "paired_vs_ref": unc_t["paired_vs_ref"], "work_agg": {a.name: unc_t["last_outs"][a.name][1] for a in arm_objs}},
            "uncached_ndarray": {"arms": unc_n["arms"], "paired_vs_ref": unc_n["paired_vs_ref"]},
            "secondary_cached_tuple": {"arms": cac_t["arms"], "paired_vs_ref": cac_t["paired_vs_ref"], "work_agg": {a.name: cac_t["last_outs"][a.name][1] for a in arm_objs}},
        }
        line = " ".join(f"{a.name}={unc_t['arms'][a.name]['timing']['median_ms']:.2f}ms" for a in arm_objs)
        print(f"  [p1-batch  {bid:<32}] {line}", flush=True)

    return {"singles": singles_out, "batches": batches_out}


def main() -> int:
    parser = argparse.ArgumentParser(description="BVH-042-P1 Histogram & SAH Eval Ablation")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--screen-repeats", type=int, default=7)
    parser.add_argument("--confirm-repeats", type=int, default=30)
    parser.add_argument("--skip-confirm", action="store_true")
    args = parser.parse_args()

    arm_paths = make_p1_arms()
    arm_a = load_arm_modules("A", arm_paths["A"])
    arm_f = load_arm_modules("F", arm_paths["F"])
    _require(arm_a.source_sha256 == FROZEN_RUNTIME_SHA, f"Arm A sha mismatch: {arm_a.source_sha256}")
    _require(arm_f.source_sha256 == FROZEN_ARM_F_RUNTIME_SHA, f"Arm F sha mismatch: {arm_f.source_sha256}")
    arm_g = load_arm_modules("G", arm_paths["G"])
    arm_h = load_arm_modules("H", arm_paths["H"])
    arm_i = load_arm_modules("I", arm_paths["I"])
    arm_j = load_arm_modules("J", arm_paths["J"])

    workloads = build_042_workloads()
    print("=== Verifying 100% Complete Raw-Tree Equivalence Across A, F, G, H, I, J ===", flush=True)
    tree_digests = _verify_all_trees_and_sigs([arm_a, arm_f, arm_g, arm_h, arm_i, arm_j], workloads)

    print("\n=== Separate 3-Shot Direct Build (_distance_roots) Probe ===", flush=True)
    build_probe = _run_3shot_build_probe([arm_a, arm_f, arm_g, arm_h, arm_i, arm_j], workloads)

    print(f"\n=== Paired P1 Screening vs Arm F (warmup={args.warmup}, repeats={args.screen_repeats}) ===", flush=True)
    screen = _screen_suite([arm_f, arm_g, arm_h, arm_i, arm_j], workloads, warmup=args.warmup, repeats=args.screen_repeats)

    # Evaluate screening bar vs Arm F
    heavy_ids = [w["id"] for w in workloads["singles"] if "construction_heavy" in w["role"]]
    guard_ids = ["G508_Peer_000", "G508_Competing_001", "Control_12F_Linear", "Sparse_100kV_Degenerate_MixedBit", "D48_Real_47pairs", "Assembly24_Obj014_23pairs"]
    decisions = {}
    for cname in ("G", "H", "I", "J"):
        build_ge10 = sum(1 for hid in heavy_ids if build_probe[hid][cname]["build_reduction_vs_F_pct"] >= 10.0)
        wall_reds = [{"id": hid, "tuple_vs_F_pct": screen["singles"][hid]["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"]} for hid in heavy_ids]
        wall_ge5 = sum(1 for row in wall_reds if row["tuple_vs_F_pct"] >= 5.0)
        max_reg = 0.0
        for gid in guard_ids:
            sec = screen["singles"] if gid in screen["singles"] else screen["batches"]
            pct = sec[gid]["uncached_tuple"]["paired_vs_ref"][cname]["median_reduction_pct"]
            if -pct > max_reg:
                max_reg = round(-pct, 2)
        decisions[cname] = {
            "build_reductions_vs_F_pct": {hid: build_probe[hid][cname]["build_reduction_vs_F_pct"] for hid in heavy_ids},
            "heavy_wall_reductions_vs_F_pct": wall_reds,
            "count_build_ge_10pct": build_ge10,
            "count_heavy_wall_ge_5pct": wall_ge5,
            "max_guard_regression_vs_F_pct": max_reg,
            "meets_p1_bar": (build_ge10 >= 2 and wall_ge5 >= 1 and max_reg < 5.0),
        }
    print("P1 Decisions:", json.dumps(decisions, indent=2), flush=True)

    # Pick simplest winner: prefer I over J unless J leads I by >= 2.0pp on average heavy wall reduction without reg
    winner = None
    best_avg = -1.0
    for cname in ("G", "H", "I", "J"):
        if not decisions[cname]["meets_p1_bar"]:
            continue
        avg = statistics.mean(x["tuple_vs_F_pct"] for x in decisions[cname]["heavy_wall_reductions_vs_F_pct"])
        if cname == "J" and decisions["I"]["meets_p1_bar"]:
            i_avg = statistics.mean(x["tuple_vs_F_pct"] for x in decisions["I"]["heavy_wall_reductions_vs_F_pct"])
            if avg < i_avg + 2.0:
                continue
        if avg > best_avg:
            best_avg = avg
            winner = cname

    confirm30 = None
    if not args.skip_confirm and winner is not None:
        win_arm = {"G": arm_g, "H": arm_h, "I": arm_i, "J": arm_j}[winner]
        print(f"\n=== Stage 30-Repeat Paired Confirmation (A vs F vs {winner}) ===", flush=True)
        confirm30 = _screen_suite([arm_a, arm_f, win_arm], workloads, warmup=args.warmup, repeats=args.confirm_repeats)

    verdict = f"CANDIDATE_{winner}_VALIDATED_P1_RESEARCH_ONLY" if winner is not None else "NO_GAIN_KEEP_ARM_F"
    out = {
        "schema": "m3-bvh-kernel-042-p1-results-v1",
        "branch": "codex/m3-bvh-exact-build-pipeline-042",
        "frozen_041_commit": FROZEN_COMMIT,
        "frozen_041_runtime_sha256": FROZEN_RUNTIME_SHA,
        "frozen_arm_f_commit": FROZEN_ARM_F_COMMIT,
        "frozen_arm_f_runtime_sha256": FROZEN_ARM_F_RUNTIME_SHA,
        "environment": _win32_env_info(),
        "arm_identities": {
            a.name: {"runtime_source_sha256": a.source_sha256, "surface_geometry_sha256": a.sg_raw_sha256, "surface_proximity_sha256": a.sp_raw_sha256}
            for a in (arm_a, arm_f, arm_g, arm_h, arm_i, arm_j)
        },
        "tree_digests": tree_digests,
        "build_3shot_probe": build_probe,
        "p1_screening": screen,
        "p1_decisions": decisions,
        "selected_winner": winner,
        "confirm_30_repeats_A_F_Winner": confirm30,
        "verdict": verdict,
    }
    (BENCH_DIR / "KERNEL_042_P1_RESULTS.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE 042-P1. Verdict={verdict}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
