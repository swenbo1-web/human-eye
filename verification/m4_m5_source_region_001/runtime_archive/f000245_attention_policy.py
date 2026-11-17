"""Budgeted visual attention proposals for known 3D geometry.

The gain is a measurable screen-space sampling gain for a *positive clearance
segment*. It is not predicted model quality, physical safety, or a substitute
for collision checking. A proposal must be confirmed against a real rendered
depth buffer and measured extra cost before it becomes persistent attention.
The execution focal/reference pair is never changed by this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass

import numpy as np

from .geometry_safety import work_budget_status


@dataclass(frozen=True)
class AttentionLimits:
    """Explicit engineering tradeoffs, not learned or universal utilities."""

    target_gap_px: float = 12.0
    min_gain_px: float = 4.0
    min_gain_ratio: float = 1.5
    min_net_gain_px: float = 2.0
    switch_cost_px: float = 1.0
    cost_px_per_ms: float = 0.1
    max_additional_cost_ms: float = 40.0
    min_dwell_s: float = 1.0
    max_candidates: int = 24
    max_gap_fraction_of_smaller_extent: float = 0.25
    max_follow_center_fraction: float = 0.25
    max_follow_span_ratio: float = 1.25

    def __post_init__(self):
        for key, value in asdict(self).items():
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError('Attention limits must be finite nonnegative numbers')
        if (not 1 <= self.target_gap_px <= 64 or self.min_gain_ratio < 1
                or self.min_gain_px <= 0 or self.min_net_gain_px <= 0
                or self.max_additional_cost_ms <= 0
                or type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 96
                or not 0 < self.max_gap_fraction_of_smaller_extent <= 1
                or not 0 <= self.max_follow_center_fraction <= 1
                or not 1 <= self.max_follow_span_ratio <= 2):
            raise ValueError('Invalid attention gain or resource limits')


def _finite_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _point(value):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError('Witness points must be finite world metre xyz vectors')
    return array


def _projected_gap(pa, pb, view, projection, size):
    points = np.c_[np.array([pa, pb]), np.ones(2)]
    clip = (projection @ view @ points.T).T
    if np.any(clip[:, 3] <= 0) or not np.isfinite(clip).all():
        return 0.0, False
    ndc = clip[:, :3] / clip[:, 3:]
    inside = bool(np.all(np.abs(ndc) <= 1 + 1e-10))
    return (float(np.linalg.norm(ndc[1, :2] - ndc[0, :2]) * (size - 1) / 2)
            if inside else 0.0), inside


def _focus_key(plan):
    return json.dumps([plan['target_object_ids'], plan['direction']], separators=(',', ':'))


def _plan_signature(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _prior_state(previous):
    # State is observational, nevertheless malformed/future state must not
    # bypass hysteresis or inject a camera. Never reuse its old geometry.
    if not isinstance(previous, dict) or previous.get('schema_version') != '1.0':
        return None
    if (not isinstance(previous.get('focus_key'), str)
            or not _finite_number(previous.get('last_shift_s'))):
        return None
    try:
        plan = previous['camera_plan']
        _point(plan['target_world_m'])
        direction, up = _point(plan['direction']), _point(plan['up'])
        if (not _finite_number(plan['view_span_m']) or plan['view_span_m'] <= 0
                or abs(float(np.linalg.norm(direction)) - 1) > 1e-8
                or float(np.linalg.norm(np.cross(direction, up))) < 1e-8
                or previous['focus_key'] != _focus_key(plan)
                or _plan_signature(plan) != previous['plan_signature']):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return previous


def _same_focus(plan, previous, limits):
    if not previous or previous['focus_key'] != _focus_key(plan):
        return False
    old = previous['camera_plan']
    ratio = plan['view_span_m'] / old['view_span_m']
    displacement = float(np.linalg.norm(np.array(plan['target_world_m']) - old['target_world_m']))
    return bool(1 / limits.max_follow_span_ratio <= ratio <= limits.max_follow_span_ratio
                and displacement <= old['view_span_m'] * limits.max_follow_center_fraction)


def _orthographic_plan_gap(plan, pa, pb, size):
    """Current witnesses projected in a previous camera, without stale pixels.

    Visibility is conservatively assumed when in frame. This can suppress a
    useful shift, but cannot claim gain by pretending the current view is bad.
    """
    direction, up = np.array(plan['direction']), np.array(plan['up'])
    right = np.cross(-direction, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, -direction)
    relative = np.array([pa, pb]) - plan['target_world_m']
    coordinates = np.c_[relative @ right, relative @ true_up]
    inside = bool(np.all(np.abs(coordinates) <= plan['view_span_m'] / 2 + 1e-12))
    pixels = float(np.linalg.norm(coordinates[1] - coordinates[0]) * (size - 1) / plan['view_span_m'])
    return (pixels if inside else 0.), inside


def _contact_directions(pa, pb, legacy_directions, budget):
    """Append bounded contact-frame views after the unchanged legacy prefix.

    These are sampling proposals, not visibility evidence. A shallow normal
    component avoids exact grazing at an inner wall; diagonal tangents also
    allow a ray to leave a finite cavity before hitting its opposite wall.
    Full-scene visibility and rendered confirmation still decide adoption.
    """
    directions = legacy_directions[:budget]
    if budget <= len(legacy_directions):
        return directions
    vector = pb - pa
    length = float(np.linalg.norm(vector))
    if not math.isfinite(length) or length <= 0:
        return directions
    normal = vector / length
    axis = np.zeros(3)
    axis[int(np.argmin(np.abs(normal)))] = 1.
    tangent_u = axis - np.dot(axis, normal) * normal
    tangent_u /= np.linalg.norm(tangent_u)
    tangent_v = np.cross(normal, tangent_u)
    # The two diagonal tangent axes give eight shallow views. For example,
    # an x-directed witness segment can need both y and z motion to clear a
    # probe edge and then escape a through-hole, rather than hit another wall.
    for tangent in (tangent_u + tangent_v, tangent_u - tangent_v):
        tangent /= np.linalg.norm(tangent)
        for tangent_sign in (1., -1.):
            for normal_sign in (1., -1.):
                direction = tangent_sign * tangent + normal_sign * .3 * normal
                direction /= np.linalg.norm(direction)
                value = tuple(float(component) for component in direction)
                # This tolerance only removes equivalent unit directions;
                # witness coordinates and actual camera values stay intact.
                if any(all(abs(a - b) <= 1e-12 for a, b in zip(value, old))
                       for old in directions):
                    continue
                directions.append(value)
                if len(directions) >= budget:
                    return directions
    return directions


def _supplement_score_bounds(considered, *, previous, quad_size, limits,
                             legacy_count):
    """Conservative scores for unbuilt views, without a contact-frame basis.

    The added family has projected length |B-A|/sqrt(1+.3**2). Use the actual
    validated witness norm, which need only agree with strict clearance within
    its stated tolerance. Ill-conditioned normalization falls back to the
    universal capped-gain bound instead of assuming the family identity.
    """
    bounds = []
    stable_norm_min = math.sqrt(np.finfo(np.float64).tiny) * 8.
    stable_norm_max = math.sqrt(np.finfo(np.float64).max) / 8.
    for contact_index, (_, distance, _identity, pa, pb, baseline_px, _) in enumerate(considered):
        span = max(distance * 4, distance * (quad_size - 1) / limits.target_gap_px)
        if not math.isfinite(span) or span <= 0:
            continue
        vector = pb - pa
        measured = float(np.linalg.norm(vector))
        if not math.isfinite(measured) or measured <= 0:
            continue  # The direction helper cannot append a frame here either.
        upper_gap = limits.target_gap_px
        if stable_norm_min <= measured <= stable_norm_max:
            normal = vector / measured
            normal_squared = float(np.dot(normal, normal))
            if math.isfinite(normal_squared) and abs(normal_squared - 1.) <= 1e-13:
                projected = measured * (quad_size - 1) / span / math.sqrt(1.09)
                if math.isfinite(projected):
                    margin = max(1e-12, abs(projected) * 1e-12)
                    upper_gap = min(upper_gap, math.nextafter(projected + margin, math.inf))
        switch_lower = 0. if previous else limits.switch_cost_px
        upper_net = upper_gap - min(baseline_px, limits.target_gap_px) - switch_lower
        bounds.append((round(upper_net, 10), (contact_index, legacy_count)))
    return bounds


def _beats_supplement_bounds(candidate, order, bounds, previous):
    """Prove that no unbuilt candidate can precede this one in stable order."""
    score = round(candidate['projected_net_gain_px_before_compute'], 10)
    for upper_score, earliest_order in bounds:
        if upper_score > score:
            return False
        if upper_score == score:
            if previous and not candidate['same_focus']:
                return False  # A possible same-focus tie can take precedence.
            if earliest_order < order:
                return False  # An earlier contact's new view wins a stable tie.
    return True


class AttentionPolicy:
    def __init__(self, limits: AttentionLimits | None = None):
        self.limits = limits or AttentionLimits()

    def propose(self, meshes, *, focal_id, reference_id, contacts,
                quad_size=128, include_image=True, scene_fingerprint,
                previous=None, now_s=None, candidate_visible=None):
        """Propose a replacement for Q4; Q1-Q3 retain navigation/work context.

        ``contacts`` contains existing engine measurements, never additional
        probes: object_id, measurement_valid, signed_clearance_m and the two
        point_a_world / point_b_world witnesses. Witness distance must agree
        with the strict unrounded clearance. AABB witnesses are not fabricated.
        Candidate work is bounded and deterministic. ``propose``/``retain``
        are not application claims; only ``confirm_attention`` commits state.
        Optional ``candidate_visible(plan)`` prefilters candidates using current
        full-scene geometry, within the same candidate budget. A true result is
        not rendered confirmation. Exceptions stop selection without a shift.
        Supplemental contact-frame views are omitted only when a current visible
        view provably precedes their conservative score bounds. Otherwise the
        full pool keeps the original global stable order across contacts.
        """
        if type(include_image) is not bool or type(quad_size) is not int or not 64 <= quad_size <= 512:
            raise ValueError('Invalid attention image options')
        if not isinstance(scene_fingerprint, str) or not scene_fingerprint:
            raise ValueError('Attention requires a current scene fingerprint')
        timestamp = time.time() if now_s is None else now_s
        if not _finite_number(timestamp):
            raise ValueError('Attention time must be finite')
        if not isinstance(meshes, (list, tuple)) or not 1 <= len(meshes) <= 256:
            raise ValueError('Attention requires 1..256 validated meshes')
        by_id = {mesh.object_id: mesh for mesh in meshes}
        if (len(by_id) != len(meshes) or focal_id not in by_id or reference_id not in by_id
                or focal_id == reference_id):
            raise ValueError('Attention requires distinct known focal and reference IDs')
        if not isinstance(contacts, (list, tuple)) or len(contacts) > 255:
            raise ValueError('Attention requires at most 255 contact measurements')
        if candidate_visible is not None and not callable(candidate_visible):
            raise ValueError('Attention visibility precheck must be callable')
        result = {'schema_version': '1.0', 'decision': 'hold', 'camera_plan': None,
                  'scene_fingerprint': scene_fingerprint, 'policy': asdict(self.limits),
                  'reason_codes': [], 'state_to_commit': None, 'candidate_count': 0,
                  'visibility_precheck_count': 0,
                  'benefit_scope': 'positive_clearance_segment_screen_sampling_only',
                  'visibility_verified': False, 'model_quality_gain_proven': False,
                  'execution_pair_unchanged': True, 'proposed_at_s': float(timestamp),
                  'baseline_scope': 'existing_default_target_pair_q4',
                  'cost_policy': 'measured_extra_ms_times_explicit_pixel_tradeoff_plus_switch_cost'}
        if not include_image:
            result['reason_codes'] = ['text_only_no_visual_shift']
            return result
        previous = _prior_state(previous)
        if previous and timestamp < previous['last_shift_s']:
            result['reason_codes'] = ['attention_clock_reversed']
            return result
        if not work_budget_status(meshes, purpose='attention')['within_budget']:
            result['reason_codes'] = ['attention_geometry_budget_exceeded']
            return result
        # Lazy import keeps rendering free to import the confirmation function.
        from .scene_rendering import _camera
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            baseline_view, baseline_projection, baseline_meta = _camera(
                'Q4 TARGET', meshes, [by_id[focal_id], by_id[reference_id]],
                quad_size, 'perspective', [2.4, -3.2, 2.4])
        result['baseline_camera'] = baseline_meta
        eligible = []
        rejected = 0
        for contact in contacts:
            try:
                identity = contact['object_id']
                distance = contact['signed_clearance_m']
                if (identity not in by_id or identity == focal_id
                        or contact.get('measurement_valid') is not True
                        or not _finite_number(distance) or distance <= 0):
                    rejected += 1
                    continue
                pa, pb = _point(contact['point_a_world']), _point(contact['point_b_world'])
                vector = pb - pa
                measured = float(np.linalg.norm(vector))
                agreement = max(1e-9, distance * 1e-5)
                if not math.isfinite(measured) or abs(measured - distance) > agreement:
                    rejected += 1
                    continue
                smaller_extent = min(float(np.linalg.norm(by_id[identity].bbox_max - by_id[identity].bbox_min)),
                                     float(np.linalg.norm(by_id[focal_id].bbox_max - by_id[focal_id].bbox_min)))
                if distance > smaller_extent * self.limits.max_gap_fraction_of_smaller_extent:
                    rejected += 1
                    continue
                for point, mesh in ((pa, by_id[focal_id]), (pb, by_id[identity])):
                    if np.any(point < mesh.bbox_min - agreement) or np.any(point > mesh.bbox_max + agreement):
                        raise ValueError('Witness outside its mesh bounds')
                baseline_px, in_frame = _projected_gap(pa, pb, baseline_view, baseline_projection, quad_size)
                eligible.append((identity != reference_id, distance, identity, pa, pb, baseline_px, in_frame))
            except (TypeError, KeyError, ValueError, OverflowError, FloatingPointError):
                rejected += 1
        eligible.sort(key=lambda item: item[:3])
        result['rejected_contact_count'] = rejected
        result['eligible_contact_count'] = len(eligible)
        candidates = []
        candidate_order = {}
        raw_directions = ((1., 0., .3), (-1., 0., .3), (0., -1., .3), (0., 1., .3),
                          (1., 0., -.3), (-1., 0., -.3), (0., -1., -.3), (0., 1., -.3),
                          (1., 0., 0.), (-1., 0., 0.), (0., -1., 0.),
                          (0., 1., 0.), (0., 0., 1.), (0., 0., -1.))
        directions = [tuple(float(component) for component in np.array(value) / np.linalg.norm(value))
                      for value in raw_directions]
        considered = eligible[:min(4, max(1, self.limits.max_candidates // 6))]
        result['examined_contact_count'] = len(considered)
        previous_candidate = None
        if previous:
            # Retaining the actual previous camera during a dwell interval is
            # preferable to oscillating back to default Q4 while a new optimum
            # waits. Rebuild its witnesses and recheck current scene visibility.
            for _, distance, identity, pa, pb, baseline_px, in_frame in considered:
                old = previous['camera_plan']
                if old['target_object_ids'] != [focal_id, identity]:
                    continue
                current_px, current_in_frame = _orthographic_plan_gap(old, pa, pb, quad_size)
                gain = min(current_px, self.limits.target_gap_px) - min(baseline_px, self.limits.target_gap_px)
                if (not current_in_frame or gain + 1e-10 < self.limits.min_gain_px
                        or current_px < baseline_px * self.limits.min_gain_ratio
                        or gain < self.limits.min_net_gain_px):
                    continue
                plan = copy.deepcopy(old)
                plan.update(witness_points_world_m=[pa.tolist(), pb.tolist()], quad_size=quad_size)
                previous_candidate = {'camera_plan': plan, 'baseline_projected_gap_px': baseline_px,
                    'baseline_default_projected_gap_px': baseline_px, 'previous_projected_gap_px': current_px,
                    'previous_witnesses_in_frame': True, 'baseline_witnesses_in_frame': in_frame,
                    'baseline_scope': 'default_q4_for_retention_value',
                    'candidate_projected_gap_px': current_px, 'capped_gain_px': gain,
                    'projected_net_gain_px_before_compute': gain, 'same_focus': True,
                    'switch_cost_px': 0., 'strict_clearance_m': distance}
                candidates.append(previous_candidate)
                candidate_order[id(previous_candidate)] = (-1, -1)
                result['candidate_count'] += 1
                break
        per_contact_budget = (max(1, (self.limits.max_candidates - result['candidate_count']) // len(considered))
                              if considered else 0)
        dwell_active = bool(previous and timestamp - previous['last_shift_s'] < self.limits.min_dwell_s)
        had_candidates, had_selectable = False, False
        selected = None
        failed_visible_plans = []
        supplement_bounds = None
        for supplement in (False, True):
            if supplement:
                if per_contact_budget <= len(directions):
                    break
                # Keep old candidates for the original global stable ordering;
                # only their operation-local failed checks can be reused.
            for contact_index, (_, distance, identity, pa, pb, baseline_px, in_frame) in enumerate(considered):
                if result['candidate_count'] >= self.limits.max_candidates:
                    break
                # Keep enough local context to contain the whole segment, even
                # at very large resolution. No geometry rescaling occurs.
                span = max(distance * 4, distance * (quad_size - 1) / self.limits.target_gap_px)
                if not math.isfinite(span) or span <= 0:
                    continue
                current_px, current_in_frame = (_orthographic_plan_gap(previous['camera_plan'], pa, pb, quad_size)
                                                if previous else (0., False))
                direction_budget = (per_contact_budget if supplement
                                    else min(per_contact_budget, len(directions)))
                stage_directions = _contact_directions(pa, pb, directions, direction_budget)
                if supplement:
                    stage_directions = stage_directions[len(directions):]
                direction_offset = len(directions) if supplement else 0
                for direction_index, direction in enumerate(stage_directions, start=direction_offset):
                    if result['candidate_count'] >= self.limits.max_candidates:
                        break
                    result['candidate_count'] += 1
                    up = [0., 1., 0.] if abs(direction[2]) > .99 else [0., 0., 1.]
                    perpendicular = (pb - pa) - np.dot(pb - pa, direction) * np.array(direction)
                    candidate_px = float(np.linalg.norm(perpendicular) * (quad_size - 1) / span)
                    plan = {'schema_version': '1.0', 'projection': 'orthographic',
                            'target_world_m': ((pa + pb) / 2).tolist(), 'direction': list(direction),
                            'up': up, 'view_span_m': span, 'target_object_ids': [focal_id, identity],
                            'witness_points_world_m': [pa.tolist(), pb.tolist()], 'quad_size': quad_size}
                    # Keep distinct score evaluations even for identical
                    # plans: 2D retained projection and perpendicular norm may
                    # round into different ordering buckets. Only a measured
                    # failed visibility check is shared below, by full plan.
                    same_focus = _same_focus(plan, previous, self.limits)
                    comparison_px = baseline_px if same_focus else max(baseline_px, current_px)
                    gain = min(candidate_px, self.limits.target_gap_px) - min(comparison_px, self.limits.target_gap_px)
                    cost = 0.0 if same_focus else self.limits.switch_cost_px
                    net_gain = gain - cost
                    ratio_ok = candidate_px >= comparison_px * self.limits.min_gain_ratio
                    if gain + 1e-10 < self.limits.min_gain_px or not ratio_ok or net_gain < self.limits.min_net_gain_px:
                        continue
                    candidate = {'camera_plan': plan, 'baseline_projected_gap_px': comparison_px,
                                       'baseline_default_projected_gap_px': baseline_px,
                                       'previous_projected_gap_px': current_px,
                                       'previous_witnesses_in_frame': current_in_frame,
                                       'baseline_scope': ('default_q4_for_retention_value' if same_focus else
                                                          'max_default_and_previous_camera_current_witness_projection'),
                                       'baseline_witnesses_in_frame': in_frame,
                                       'candidate_projected_gap_px': candidate_px,
                                       'capped_gain_px': gain, 'projected_net_gain_px_before_compute': net_gain,
                                       'same_focus': same_focus, 'switch_cost_px': cost,
                                       'strict_clearance_m': distance}
                    candidates.append(candidate)
                    candidate_order[id(candidate)] = (contact_index, direction_index)
            result['candidate_budget_exhausted'] = result['candidate_count'] >= self.limits.max_candidates
            had_candidates = had_candidates or bool(candidates)
            # Explicit local sequence keys restore each contact's canonical
            # then supplemental order, even though construction is lazy.
            candidates.sort(key=lambda candidate: (-round(candidate['projected_net_gain_px_before_compute'], 10),
                                                   not candidate['same_focus'],
                                                   candidate_order[id(candidate)]))
            selectable = [candidate for candidate in candidates if not dwell_active or candidate['same_focus']]
            had_selectable = had_selectable or bool(selectable)
            for candidate in selectable:
                if not supplement and per_contact_budget > len(directions):
                    if supplement_bounds is None:
                        supplement_bounds = _supplement_score_bounds(considered,
                            previous=previous, quad_size=quad_size,
                            limits=self.limits, legacy_count=len(directions))
                    if not _beats_supplement_bounds(candidate, candidate_order[id(candidate)],
                                                     supplement_bounds, previous):
                        # Expand before paying for a possibly losing successful
                        # ray check, preserving the renderer's successful memo.
                        break
                if candidate_visible is not None:
                    if any(candidate['camera_plan'] == plan for plan in failed_visible_plans):
                        continue
                    result['visibility_precheck_count'] += 1
                    try:
                        visible = candidate_visible(copy.deepcopy(candidate['camera_plan']))
                        if type(visible) is not bool:
                            raise ValueError('Visibility precheck must return bool')
                    except Exception as exc:
                        result['reason_codes'] = ['attention_visibility_precheck_failed']
                        result['visibility_precheck_error_type'] = type(exc).__name__
                        return result
                    if not visible:
                        failed_visible_plans.append(candidate['camera_plan'])
                        continue
                selected = candidate
                break
            if selected is not None:
                break
        result['candidate_budget_exhausted'] = result['candidate_count'] >= self.limits.max_candidates
        if selected is None:
            result['reason_codes'] = [
                'no_proven_projected_sampling_gain' if not had_candidates else
                'attention_dwell_active' if not had_selectable else
                'no_visible_candidate_with_projected_gain']
            return result
        result.update(selected)
        result.update(decision='retain' if selected['same_focus'] else 'propose',
                      reason_codes=['projected_sampling_gain_requires_render_confirmation'],
                      previous_last_shift_s=previous['last_shift_s'] if selected['same_focus'] else None,
                      plan_signature=_plan_signature(selected['camera_plan']))
        return result


def confirm_attention(proposal, *, witness_visible, actual_projected_gap_px,
                       additional_cost_ms, scene_fingerprint, now_s=None, readability=None):
    """Confirm visible sampling gain after rasterization, or discard proposal.

    ``witness_visible`` must come from current *full-scene* depth or exact
    ray/triangle visibility, including self-occlusion and other scene meshes.
    ``additional_cost_ms`` includes proposal, extra render, and visibility
    validation work. Callers must not present zero cost for an unmeasured run.
    This function never authorizes scene mutations and never changes proposal.
    Production callers also provide pre-annotation ``readability``; sampling
    confirmation without it does not establish rendered object readability.
    """
    result = {'schema_version': '1.0', 'decision': 'hold', 'applied': False,
              'state_to_commit': None, 'reason_codes': [], 'visibility_verified': False,
               'readability_verified': False, 'model_quality_gain_proven': False}
    if not isinstance(proposal, dict) or proposal.get('decision') not in ('propose', 'retain'):
        result['reason_codes'] = ['no_attention_proposal']
        return result
    if scene_fingerprint != proposal.get('scene_fingerprint'):
        result['reason_codes'] = ['attention_scene_changed_before_confirmation']
        return result
    if (not isinstance(witness_visible, (tuple, list)) or len(witness_visible) != 2
            or any(type(value) is not bool for value in witness_visible)):
        raise ValueError('Confirmation requires two measured visibility booleans')
    if (not _finite_number(actual_projected_gap_px) or actual_projected_gap_px < 0
            or not _finite_number(additional_cost_ms) or additional_cost_ms < 0):
        raise ValueError('Confirmation requires finite nonnegative pixels and measured milliseconds')
    timestamp = time.time() if now_s is None else now_s
    if not _finite_number(timestamp):
        raise ValueError('Attention time must be finite')
    limits = AttentionLimits(**proposal['policy'])
    if _plan_signature(proposal['camera_plan']) != proposal['plan_signature']:
        result['reason_codes'] = ['attention_plan_changed_before_confirmation']
        return result
    result.update(actual_projected_gap_px=float(actual_projected_gap_px),
                  additional_cost_ms=float(additional_cost_ms), witness_visible=list(witness_visible))
    if not all(witness_visible):
        result['reason_codes'] = ['contact_witness_occluded_or_outside_render']
        return result
    result['visibility_verified'] = True
    # Production rendering supplies measurements from the unannotated depth
    # winner/RGB buffers. The optional argument preserves the pure sampling
    # policy API; absent evidence never claims rendered readability.
    if readability is not None:
        if not isinstance(readability, dict) or type(readability.get('passed')) is not bool:
            raise ValueError('Readability requires measured pre-annotation evidence')
        result['readability'] = copy.deepcopy(readability)
        if not readability['passed']:
            result['reason_codes'] = ['candidate_surface_readability_insufficient']
            return result
        result['readability_verified'] = True
    # A different camera/scale is not confirmation of the proposed camera.
    if abs(actual_projected_gap_px - proposal['candidate_projected_gap_px']) > max(1e-7, actual_projected_gap_px * 1e-6):
        result['reason_codes'] = ['rendered_projection_disagrees_with_proposal']
        return result
    baseline = proposal['baseline_projected_gap_px']
    gain = min(actual_projected_gap_px, limits.target_gap_px) - min(baseline, limits.target_gap_px)
    compute_cost = additional_cost_ms * limits.cost_px_per_ms
    net = gain - proposal['switch_cost_px'] - compute_cost
    result.update(capped_gain_px=gain, compute_cost_equivalent_px=compute_cost, net_gain_px=net)
    if additional_cost_ms > limits.max_additional_cost_ms:
        result['reason_codes'] = ['attention_additional_compute_budget_exceeded']
        return result
    if (gain + 1e-10 < limits.min_gain_px or actual_projected_gap_px < baseline * limits.min_gain_ratio
            or net < limits.min_net_gain_px):
        result['reason_codes'] = ['attention_measured_gain_does_not_cover_cost']
        return result
    retained = proposal['decision'] == 'retain'
    state = {'schema_version': '1.0', 'scene_fingerprint': scene_fingerprint,
             'focus_key': _focus_key(proposal['camera_plan']),
             'last_shift_s': proposal['previous_last_shift_s'] if retained else float(timestamp),
             'confirmed_at_s': float(timestamp), 'camera_plan': copy.deepcopy(proposal['camera_plan']),
             'plan_signature': proposal['plan_signature'], 'measured_net_gain_px': net,
             'scope': 'visual_attention_only_no_execution_authority'}
    result.update(decision='retained' if retained else 'applied', applied=True,
                  shifted=not retained, state_to_commit=state,
                  reason_codes=['visible_sampling_gain_covers_measured_cost'])
    return result


__all__ = ['AttentionLimits', 'AttentionPolicy', 'confirm_attention']
