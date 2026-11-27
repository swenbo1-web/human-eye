"""Exact pre-tree cross-pair root separation proofs for batch nearest queries.

All arithmetic operates strictly over exact binary64 dyadic integers via
frexp/ldexp common-exponent alignment and bounded integer bit budgets.
No floating-point tolerance or approximate bounding is used in any exclusion.
"""
from __future__ import annotations

import math

MAX_BITS = 4096
MAX_AXIS_BITS = 512
MAX_PREPROOF_EXP_SPAN = 450
MIN_PREPROOF_EXP = -900
MAX_PREPROOF_EXP = 900
MAX_MULTI_AXES = 4

VALID_PREPROOF_MODES = frozenset({
    'NONE',
    'B1_ROOT_AABB',
    'B2_INCUMBENT_AXIS',
    'B3_TARGET_MEMO_AXIS',
    'B4_BOUNDED_MULTI_AXIS',
})


def _float_dyadic_exp(val: float) -> int | None:
    if val == 0.0:
        return None
    _, exp = math.frexp(val)
    return exp - 53


def canonicalize_exact_axis(axis) -> tuple[int, int, int] | None:
    """Validate and canonicalize a nonzero primitive integer direction."""
    if type(axis) not in (list, tuple) or len(axis) != 3:
        return None
    if any(type(c) is not int for c in axis):
        return None
    g = math.gcd(abs(axis[0]), math.gcd(abs(axis[1]), abs(axis[2])))
    if g == 0:
        return None
    ux, uy, uz = axis[0] // g, axis[1] // g, axis[2] // g
    first_nz = ux if ux != 0 else (uy if uy != 0 else uz)
    if first_nz < 0:
        ux, uy, uz = -ux, -uy, -uz
    if (ux.bit_length() > MAX_AXIS_BITS
            or uy.bit_length() > MAX_AXIS_BITS
            or uz.bit_length() > MAX_AXIS_BITS):
        return None
    return (ux, uy, uz)


def _strict_dyadic_gt(lhs_int: int, rhs_int: int, diff_exp: int) -> tuple[bool | None, str | None]:
    """Return exact truth of (lhs_int * 2^diff_exp) > rhs_int for non-negative ints."""
    if lhs_int <= 0:
        return False, None
    if rhs_int == 0:
        return True, None
    l_top = lhs_int.bit_length() + diff_exp
    r_top = rhs_int.bit_length()
    if l_top > r_top:
        return True, None
    if l_top < r_top:
        return False, None
    if abs(diff_exp) > MAX_BITS:
        return None, 'preproof_bit_limit'
    if diff_exp >= 0:
        if lhs_int.bit_length() + diff_exp > 2 * MAX_BITS:
            return None, 'preproof_bit_limit'
        return ((lhs_int << diff_exp) > rhs_int), None
    shift = -diff_exp
    if rhs_int.bit_length() + shift > 2 * MAX_BITS:
        return None, 'preproof_bit_limit'
    return (lhs_int > (rhs_int << shift)), None


def check_pretree_root_aabb_exclusion(
    target_entry: dict,
    peer_entry: dict,
    upper_bound_sq_key,
    checkpoint,
) -> dict:
    """Exact pre-tree root AABB separation test over captured referenced bounds."""
    checkpoint('surface_proximity_preproof_aabb')
    work = {'preproof_aabb_checks': 1, 'preproof_work_units': 1, 'work_units': 1}
    if not (target_entry.get('preproof_eligible') and peer_entry.get('preproof_eligible')):
        return {'excluded': False, 'deferred_reason': 'preproof_extreme_exponent', 'work': work}

    (tx0, ty0, tz0), (tx1, ty1, tz1) = target_entry['referenced_bounds']
    (px0, py0, pz0), (px1, py1, pz1) = peer_entry['referenced_bounds']
    pairs = (
        (tx1, px0) if tx1 < px0 else ((px1, tx0) if px1 < tx0 else None),
        (ty1, py0) if ty1 < py0 else ((py1, ty0) if py1 < ty0 else None),
        (tz1, pz0) if tz1 < pz0 else ((pz1, tz0) if pz1 < tz0 else None),
    )
    if all(p is None for p in pairs):
        return {'excluded': False, 'deferred_reason': None, 'work': work}

    min_e = max_e = None
    for pair in pairs:
        if pair is None:
            continue
        for val in pair:
            ev = _float_dyadic_exp(val)
            if ev is not None:
                if min_e is None:
                    min_e = max_e = ev
                else:
                    if ev < min_e:
                        min_e = ev
                    elif ev > max_e:
                        max_e = ev

    if min_e is not None and (
        max_e - min_e > MAX_PREPROOF_EXP_SPAN or min_e < MIN_PREPROOF_EXP or max_e > MAX_PREPROOF_EXP
    ):
        return {'excluded': False, 'deferred_reason': 'preproof_extreme_exponent', 'work': work}

    e_c = min_e if min_e is not None else 0
    shift = -e_c
    ldexp = math.ldexp
    gap_sq_int = 0
    for pair in pairs:
        if pair is None:
            continue
        lo_f, hi_f = pair
        d_int = int(ldexp(hi_f, shift)) - int(ldexp(lo_f, shift))
        if d_int <= 0:
            continue
        if d_int.bit_length() > MAX_BITS:
            return {'excluded': False, 'deferred_reason': 'preproof_bit_limit', 'work': work}
        gap_sq_int += d_int * d_int

    if gap_sq_int <= 0 or gap_sq_int.bit_length() > 2 * MAX_BITS:
        return {'excluded': False, 'deferred_reason': None if gap_sq_int <= 0 else 'preproof_bit_limit', 'work': work}

    cn, cd, ce = upper_bound_sq_key
    gt, def_reason = _strict_dyadic_gt(gap_sq_int * cd, cn, 2 * e_c - ce)
    if def_reason is not None:
        return {'excluded': False, 'deferred_reason': def_reason, 'work': work}
    if not gt:
        return {'excluded': False, 'deferred_reason': None, 'work': work}

    return {
        'excluded': True,
        'deferred_reason': None,
        'proof_kind': 'pretree_root_aabb',
        'proof_receipt': {
            'box_a': [[tx0, tx1], [ty0, ty1], [tz0, tz1]],
            'box_b': [[px0, px1], [py0, py1], [pz0, pz1]],
            'common_exp': e_c,
            'aabb_gap_sq_int': gap_sq_int,
            'upper_bound_sq_key': [cn, cd, ce],
            'strict_inequality_verified': True,
        },
        'work': work,
    }


def project_mesh_exact_interval(
    compact_verts,
    min_exp: int | None,
    axis: tuple[int, int, int],
    checkpoint,
) -> tuple[int, int, int]:
    """Compute exact dyadic-integer dot-product [min, max] over compacted vertices."""
    e_m = min_exp if min_exp is not None else 0
    shift = -e_m
    ux, uy, uz = axis
    ldexp = math.ldexp
    lo = hi = None
    n_verts = len(compact_verts)
    for start in range(0, n_verts, 256):
        checkpoint('surface_proximity_preproof_axis_proj')
        chunk = compact_verts[start:start + 256]
        if shift == 0:
            for vx, vy, vz in chunk:
                d = int(vx) * ux + int(vy) * uy + int(vz) * uz
                if lo is None:
                    lo = hi = d
                elif d < lo:
                    lo = d
                elif d > hi:
                    hi = d
        else:
            for vx, vy, vz in chunk:
                d = int(ldexp(vx, shift)) * ux + int(ldexp(vy, shift)) * uy + int(ldexp(vz, shift)) * uz
                if lo is None:
                    lo = hi = d
                elif d < lo:
                    lo = d
                elif d > hi:
                    hi = d
    if lo is None:
        return 0, 0, e_m
    return lo, hi, e_m


def check_pretree_root_axis_exclusion(
    target_entry: dict,
    peer_entry: dict,
    axis,
    upper_bound_sq_key,
    checkpoint,
    *,
    target_memo: dict | None = None,
    axis_epoch: int = 0,
    axis_source_peer_id: str | None = None,
) -> dict:
    """Exact pre-tree shared-axis root separation test using exact integer projections."""
    canon_axis = canonicalize_exact_axis(axis)
    if canon_axis is None:
        return {
            'excluded': False,
            'deferred_reason': 'preproof_invalid_axis',
            'work': {'preproof_axis_checks': 1, 'preproof_work_units': 1, 'work_units': 1},
        }
    if not (target_entry.get('preproof_eligible') and peer_entry.get('preproof_eligible')):
        return {
            'excluded': False,
            'deferred_reason': 'preproof_extreme_exponent',
            'work': {'preproof_axis_checks': 1, 'preproof_work_units': 1, 'work_units': 1},
        }

    t_verts = target_entry['mesh'].vertices
    p_verts = peer_entry['mesh'].vertices
    memo_hit = 0
    proj_verts = 0
    if target_memo is not None:
        memo_key = (target_entry.get('source_sha256'), canon_axis)
        cached_t = target_memo.get(memo_key)
    else:
        memo_key = None
        cached_t = None

    if cached_t is not None:
        la, ha, e_t = cached_t
        memo_hit = 1
    else:
        la, ha, e_t = project_mesh_exact_interval(t_verts, target_entry.get('min_exp'), canon_axis, checkpoint)
        proj_verts += len(t_verts)
        if memo_key is not None:
            target_memo[memo_key] = (la, ha, e_t)

    lb, hb, e_p = project_mesh_exact_interval(p_verts, peer_entry.get('min_exp'), canon_axis, checkpoint)
    proj_verts += len(p_verts)
    wu = 1 + ((proj_verts + 63) // 64)
    work = {
        'preproof_axis_checks': 1,
        'preproof_axis_proj_verts': proj_verts,
        'preproof_target_memo_hits': memo_hit,
        'preproof_work_units': wu,
        'work_units': wu,
    }

    if abs(e_t - e_p) > 900:
        return {'excluded': False, 'deferred_reason': 'preproof_exponent_spread', 'work': work}

    e_c = e_t if e_t <= e_p else e_p
    if e_t > e_c:
        st = e_t - e_c
        la <<= st
        ha <<= st
    elif e_p > e_c:
        sp_shift = e_p - e_c
        lb <<= sp_shift
        hb <<= sp_shift

    if lb > ha:
        gap_int = lb - ha
    elif la > hb:
        gap_int = la - hb
    else:
        return {'excluded': False, 'deferred_reason': None, 'work': work}

    if gap_int.bit_length() > MAX_BITS:
        return {'excluded': False, 'deferred_reason': 'preproof_bit_limit', 'work': work}

    ux, uy, uz = canon_axis
    norm2 = ux * ux + uy * uy + uz * uz
    cn, cd, ce = upper_bound_sq_key
    gt, def_reason = _strict_dyadic_gt(gap_int * gap_int * cd, cn * norm2, 2 * e_c - ce)
    if def_reason is not None:
        return {'excluded': False, 'deferred_reason': def_reason, 'work': work}
    if not gt:
        return {'excluded': False, 'deferred_reason': None, 'work': work}

    return {
        'excluded': True,
        'deferred_reason': None,
        'proof_kind': 'pretree_root_axis',
        'proof_receipt': {
            'axis': [ux, uy, uz],
            'axis_norm_sq': norm2,
            'target_interval': [la, ha],
            'peer_interval': [lb, hb],
            'common_exp': e_c,
            'gap_int': gap_int,
            'upper_bound_sq_key': [cn, cd, ce],
            'strict_inequality_verified': True,
            'axis_epoch': axis_epoch,
            'axis_source_peer_id': axis_source_peer_id,
            'target_memo_hit': bool(memo_hit),
        },
        'work': work,
    }
