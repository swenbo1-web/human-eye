"""Compact, read-only original support-plane discovery for a current mesh pair.

The module's imports stay lightweight: query validation imports this module
before the router's scene validator exists. Exact geometry helpers are loaded
only when discovery actually runs. A returned selector binds a current scene;
it is neither an authorization nor a stable semantic face across rebuilds.
"""
from __future__ import annotations

import copy
import math


CONTRACT_REVISION = 'compact-original-support-plane-discovery-v1-20261028'
MAX_CANDIDATES = 6
DEFAULT_MAX_CANDIDATES = 4
SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'description': 'Read-only discovery of bounded original support-plane selectors for the current focal/reference pair. Omit direction for geometry only; no action direction is invented.',
    'properties': {
        'direction_world': {'type': 'array', 'minItems': 3, 'maxItems': 3,
                            'items': {'type': 'number'}},
        'max_candidates': {'type': 'integer', 'minimum': 1,
                           'maximum': MAX_CANDIDATES, 'default': DEFAULT_MAX_CANDIDATES},
    },
}
REQUEST_SCHEMA = SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA


def validate_support_plane_discovery_request(request):
    """Normalize only shape and finite values, without geometry or host work.

    Retain the original finite direction as floats so repeated query validation
    is idempotent. The calculation normalizes its separate local copy once.
    """
    if not isinstance(request, dict) or set(request) - {'direction_world', 'max_candidates'}:
        raise ValueError('support_plane_discovery accepts only direction_world and max_candidates')
    limit = request.get('max_candidates', DEFAULT_MAX_CANDIDATES)
    if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError('support_plane_discovery.max_candidates must be an integer in 1..6')
    result = {'max_candidates': limit}
    if 'direction_world' in request:
        direction = request['direction_world']
        if not isinstance(direction, (list, tuple)) or len(direction) != 3:
            raise ValueError('support_plane_discovery.direction_world requires three finite numbers')
        raw = []
        for value in direction:
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('support_plane_discovery.direction_world rejects nonfinite and boolean values')
            raw.append(float(value))
        length = math.hypot(*raw)
        if not math.isfinite(length) or length == 0:
            raise ValueError('support_plane_discovery.direction_world needs a finite nonzero norm')
        result['direction_world'] = raw
    return result


def _identity(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(field + ' requires a nonempty identity of at most 256 characters')
    return value


def _failed(result, code, *, status='unsupported'):
    result.update(status=status, candidates=[], total_candidate_count=0,
                  returned_candidate_count=0, omitted_candidate_count=0,
                  all_candidates_returned=False, enumeration_complete=False,
                  ambiguous=False, reason_codes=[code])
    return result


def discover_support_planes(scene, focal_id, reference_id, request, *, _observation=None):
    """Scan bounded original reference triangles using one exact pair preparation.

    Each admitted group has an exact global support plane and an attained foot
    on at least one original triangle. Grouping uses exact oriented equations,
    never rounded normals, plane fitting, or a convex hull. A single strict
    pair measurement must independently agree with every admitted group.
    """
    request = validate_support_plane_discovery_request(request)
    focal_id = _identity(focal_id, 'focal_id')
    reference_id = _identity(reference_id, 'reference_id')
    if focal_id == reference_id:
        raise ValueError('Support-plane discovery requires distinct objects')
    direction = request.get('direction_world')
    if direction is not None:
        length = math.hypot(*direction)
        direction = [value / length for value in direction]
    result = {'schema_version': '1.0', 'contract_revision': CONTRACT_REVISION,
        'status': 'unsupported', 'candidates': [], 'total_candidate_count': 0,
        'returned_candidate_count': 0, 'omitted_candidate_count': 0,
        'all_candidates_returned': False, 'enumeration_complete': False, 'ambiguous': False,
        'request': copy.deepcopy(request), 'direction_world': direction,
        'scene_revision': None, 'scene_fingerprint': None,
        'focal_id': focal_id, 'reference_id': reference_id, 'unit': 'm',
        'coordinate_frame': 'world', 'scope': 'current_represented_pair_original_support_planes',
        'measurement_valid': False, 'current_clearance_m': None,
        'execution_authority': False, 'whole_scene_collision_certified': False,
        'swept_path_certified': False, 'task_success_certified': False,
        'selector_scope': 'current_scene_pair_selection_not_authorization_or_cross_rebuild_identity',
        'reason_codes': []}
    # Lazy imports are essential: query_policy is itself imported by auto_router.
    from .auto_router import _ValidatedObservation, _validated_scene
    from .rigid_frame import pair_rigid_frame_status
    from .support_plane_candidate import (
        _preflight, _rational_mesh, _certificate_from_rationals, _strict,
        _sub, _dot, _cross, MIN_DIRECTIONAL_DERIVATIVE,
    )
    if _observation is not None:
        if type(_observation) is not _ValidatedObservation:
            raise ValueError('Validated observation required for scene reuse')
        _observation._require_scene(scene)
    limit_reason = _preflight(scene, {'focal_id': focal_id, 'reference_id': reference_id})
    if limit_reason:
        return _failed(result, limit_reason, status='unknown')
    if _observation is None:
        normalized, meshes, fingerprint = _validated_scene(scene)
    else:
        normalized, meshes, fingerprint = (
            _observation.scene, _observation.meshes, _observation.fingerprint)
    result.update(scene_revision=normalized['revision'], scene_fingerprint=fingerprint)
    if len(normalized['revision']) > 256:
        return _failed(result, 'selection_binding_revision_outside_supported_range', status='unknown')
    by_id = {mesh.object_id: mesh for mesh in meshes}
    if focal_id not in by_id or reference_id not in by_id:
        raise ValueError('Support-plane discovery objects must be present in the captured scene')
    focal, reference = by_id[focal_id], by_id[reference_id]
    if normalized.get('host_execution', {}).get('supported') is False:
        return _failed(result, 'host_rigid_execution_unsupported')
    if pair_rigid_frame_status(focal, reference)['valid'] is not True:
        return _failed(result, 'rigid_frame_unavailable')
    try:
        fv, _ = _rational_mesh(focal)
        rv, rf = _rational_mesh(reference)
        # The key retains orientation via a positive divisor. Coefficients are
        # exact ratios, so near-coplanar original faces are never merged.
        groups = {}
        for index, face in enumerate(rf):
            a, b, c = (rv[i] for i in face)
            normal = _cross(_sub(b, a), _sub(c, a))
            scale = max(abs(value) for value in normal)
            key = tuple(value / scale for value in normal) + (_dot(normal, a) / scale,)
            group = groups.setdefault(key, {'triangle_count': 0, 'certificate': None,
                                            'nonpositive_gap': False})
            group['triangle_count'] += 1
            # The exact oriented plane key differs only by a positive normal
            # scale, so the sign of every focal height is shared by the group.
            # A successful original-triangle foot is already its first valid
            # witness. Still scan/count every face and every other plane.
            if group['certificate'] is not None or group['nonpositive_gap']:
                continue
            try:
                certificate = _certificate_from_rationals(fv, rv, rf, index)
            except ArithmeticError as exc:
                if str(exc) == 'strict_positive_support_gap_required':
                    group['nonpositive_gap'] = True
                    continue
                if str(exc) == 'minimum_support_projects_outside_original_triangle':
                    continue
                raise
            # Original indices are scanned in order. Never choose the lowest
            # index unless that particular finite triangle has a valid foot.
            group['certificate'] = certificate
        eligible = [group for group in groups.values() if group['certificate'] is not None]
        if not eligible:
            return _failed(result, 'no_exact_support_plane_witness')
        strict_options = {} if _observation is None else {'_observation': _observation}
        measured, _ = _strict(focal, reference, eligible[0]['certificate'], **strict_options)
        metric = float(measured['signed_clearance_m'])
        extent = max(float((mesh.vertices.max(axis=0)-mesh.vertices.min(axis=0)).max())
                     for mesh in (focal, reference))
        binding = {'scene_revision': normalized['revision'], 'scene_fingerprint': fingerprint,
                   'focal_id': focal_id, 'reference_id': reference_id}
        candidates = []
        parallel_count = 0
        for group in eligible:
            certificate = group['certificate']; gap = certificate['plane_clearance_m']
            agreement = min(1e-10, 64 * max(math.ulp(gap), math.ulp(metric), math.ulp(extent)))
            if not math.isfinite(agreement) or abs(metric-gap) > agreement:
                raise ArithmeticError('support_gap_disagrees_with_strict_clearance')
            normal = certificate['plane_normal_world']
            derivative = math.fsum(a*b for a, b in zip(normal, direction)) if direction is not None else None
            if derivative is not None and (not math.isfinite(derivative)
                                          or abs(derivative) < MIN_DIRECTIONAL_DERIVATIVE):
                parallel_count += 1
                continue
            index = certificate['reference_triangle_index']
            candidates.append({'candidate_id': 'support:' + str(index),
                'selector': {'reference_triangle_index': index,
                             'selection_binding': copy.deepcopy(binding)},
                'plane_normal_world': list(normal), 'clearance_m': metric,
                'directional_derivative': derivative,
                'coplanar_triangle_count': group['triangle_count'],
                'execution_authority': False})
        candidates.sort(key=lambda row: row['selector']['reference_triangle_index'])
        total = len(candidates); maximum = request['max_candidates']
        result.update(measurement_valid=True, current_clearance_m=metric,
            enumeration_complete=True, total_candidate_count=total,
            returned_candidate_count=min(total, maximum), omitted_candidate_count=max(0, total-maximum),
            all_candidates_returned=total <= maximum, ambiguous=total > 1,
            candidates=candidates[:maximum], scanned_reference_triangle_count=len(rf),
            exact_plane_group_count=len(groups), direction_filtered_plane_count=parallel_count)
        if candidates:
            result.update(status='complete', reason_codes=[])
        else:
            result.update(status='unsupported', reason_codes=['direction_nearly_parallel_to_support_plane'])
        return result
    except (ArithmeticError, FloatingPointError, OverflowError) as exc:
        code = str(exc) or 'support_plane_discovery_numeric_failure'
        unknown = code in {'strict_pair_clearance_unavailable', 'strict_pair_measurement_failed',
            'support_gap_disagrees_with_strict_clearance', 'support_plane_rational_resource_limit',
            'support_gap_not_representable'} or isinstance(exc, (FloatingPointError, OverflowError))
        return _failed(result, code, status='unknown' if unknown else 'unsupported')


__all__ = ['CONTRACT_REVISION', 'MAX_CANDIDATES', 'SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA',
           'REQUEST_SCHEMA', 'validate_support_plane_discovery_request', 'discover_support_planes']
