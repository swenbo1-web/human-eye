"""Read-only support-plane clearance candidates, separate from live execution.

An explicit original reference triangle must support the complete reference
mesh. A lowest focal vertex must project into that finite triangle. These
predicates use exact rational arithmetic on represented float64 coordinates;
no tolerance repairs a plane, convex hull, or outside projection. Complete
closed connected outward topology and every original convex halfspace are
also checked exactly before the existing strict numerical pair kernel.
Current and rounded proposed geometry are independently remeasured by the
existing strict pair kernel. Nothing here commands a host or certifies a scene,
motion path, object incarnation, external edit, or the user's task.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from .auto_router import _ValidatedObservation, _validated_scene
from .geometry_safety import measure_pair_geometry, work_budget_status
from .rigid_frame import pair_rigid_frame_status

CONTRACT_REVISION = "readonly-original-support-triangle-clearance-v1-20261028"
MAX_VERTICES = 64
MAX_FACES = 128
MAX_SCENE_VERTICES = 2048
MAX_SCENE_FACES = 4096
MAX_RATIONAL_BITS = 512
MIN_DIRECTIONAL_DERIVATIVE = 1e-8
_MAX_INWARD_FEATURE_PROPOSALS = 4
_REQUIRED = ("focal_id", "reference_id", "reference_triangle_index", "direction_world",
             "target_clearance_m", "clearance_tolerance_m")
_DEFAULTS = {"max_step_translation_m": .01, "max_total_translation_m": .04}
_ALLOWED = frozenset(_REQUIRED) | frozenset(_DEFAULTS)
REQUEST_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": list(_REQUIRED),
    "description": "Read-only pair candidate; no execution or whole-scene authority. The selected original reference triangle is explicit. direction_world is normalized by the SDK.",
    "properties": {
        "focal_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "reference_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "reference_triangle_index": {"type": "integer", "minimum": 0},
        "direction_world": {"type": "array", "minItems": 3, "maxItems": 3,
                            "items": {"type": "number"}},
        "target_clearance_m": {"type": "number", "minimum": 0},
        "clearance_tolerance_m": {"type": "number", "minimum": 0},
        "max_step_translation_m": {"type": "number", "exclusiveMinimum": 0,
                                   "maximum": 1, "default": .01},
        "max_total_translation_m": {"type": "number", "exclusiveMinimum": 0,
                                    "maximum": 4, "default": .04}}}


def _number(value, field, *, positive=False, maximum=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(field + " must be a finite number, not a boolean")
    value = float(value)
    if value < 0 or positive and value <= 0 or maximum is not None and value > maximum:
        raise ValueError(field + " is outside its supported range")
    return value


def validate_support_plane_request(request):
    """Validate explicit intent and normalize a nonzero world direction."""
    if not isinstance(request, dict) or set(request) - _ALLOWED or not set(_REQUIRED).issubset(request):
        raise ValueError("Support-plane request requires only supported explicit fields")
    result = {}
    for field in ("focal_id", "reference_id"):
        value = request[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(field + " requires a nonempty identity of at most 256 characters")
        result[field] = value
    if result['focal_id'] == result['reference_id']:
        raise ValueError("Support-plane request requires distinct objects")
    index = request['reference_triangle_index']
    if type(index) is not int or index < 0:
        raise ValueError("reference_triangle_index requires a nonnegative integer")
    result['reference_triangle_index'] = index
    direction = request['direction_world']
    if not isinstance(direction, (list, tuple)) or len(direction) != 3:
        raise ValueError("direction_world requires three finite numbers")
    raw = []
    for value in direction:
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("direction_world requires finite numbers, not booleans")
        raw.append(float(value))
    length = math.hypot(*raw)
    if not math.isfinite(length) or length == 0:
        raise ValueError("direction_world must have a finite nonzero norm")
    result['direction_world'] = [value / length for value in raw]
    for field in ('target_clearance_m', 'clearance_tolerance_m'):
        result[field] = _number(request[field], field)
    for field, maximum in (('max_step_translation_m', 1), ('max_total_translation_m', 4)):
        result[field] = _number(request.get(field, _DEFAULTS[field]), field,
                                positive=True, maximum=maximum)
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()


def _sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _rational(value):
    ratio = Fraction(float(value))
    if max(abs(ratio.numerator).bit_length(), ratio.denominator.bit_length()) > MAX_RATIONAL_BITS:
        raise ArithmeticError('support_plane_rational_resource_limit')
    return ratio


def _preflight(scene, request):
    """Count before conversion/classification; reject coercible nonnumeric vertices."""
    if not isinstance(scene, dict) or not isinstance(scene.get('meshes'), list):
        raise ValueError('scene requires meshes')
    items = scene['meshes']
    if not 1 <= len(items) <= 256:
        raise ValueError('scene requires 1..256 meshes')
    total_v = total_f = 0
    pair = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('mesh must be an object')
        vertices, faces = item.get('vertices'), item.get('faces')
        if not isinstance(vertices, (list, tuple, np.ndarray)) or not isinstance(faces, (list, tuple, np.ndarray)):
            raise ValueError('mesh vertices and faces must be arrays')
        if isinstance(vertices, np.ndarray) and (vertices.ndim != 2 or vertices.shape[1:] != (3,)):
            raise ValueError('vertices require Nx3 numeric coordinates')
        if isinstance(faces, np.ndarray) and (faces.ndim != 2 or faces.shape[1:] != (3,)):
            raise ValueError('faces require Nx3 triangle indices')
        total_v += len(vertices); total_f += len(faces)
        if total_v > MAX_SCENE_VERTICES or total_f > MAX_SCENE_FACES:
            return 'support_plane_scene_resource_limit'
        if isinstance(vertices, np.ndarray):
            if vertices.dtype.kind not in 'ifu':
                raise ValueError('vertices require numeric coordinates, not booleans or strings')
        else:
            for vertex in vertices:
                if not isinstance(vertex, (list, tuple, np.ndarray)) or len(vertex) != 3:
                    raise ValueError('vertices require Nx3 numeric coordinates')
                for coordinate in vertex:
                    if isinstance(coordinate, (bool, np.bool_)) or not isinstance(coordinate, (int, float, np.integer, np.floating)):
                        raise ValueError('vertices require numeric coordinates, not booleans or strings')
        if item.get('object_id') in (request['focal_id'], request['reference_id']):
            pair.append(item)
            if len(vertices) > MAX_VERTICES or len(faces) > MAX_FACES:
                return 'support_plane_pair_resource_limit'
    if len(pair) != 2:
        raise ValueError('Support-plane objects must be present once each')
    budget = work_budget_status(pair)
    return None if budget['within_budget'] else 'geometry_resource_limit'


def _rational_mesh(mesh):
    vertices = [tuple(_rational(value) for value in vertex) for vertex in mesh.vertices]
    faces = [[int(index) for index in face] for face in mesh.faces]
    if len(set(vertices)) != len(vertices):
        raise ArithmeticError('distinct_original_vertices_required')
    used, edges, face_keys = set(), {}, set()
    volume = Fraction(0)
    neighbours = [set() for _ in faces]
    origin = vertices[0]
    for position, face in enumerate(faces):
        key = tuple(sorted(face))
        if len(set(face)) != 3 or key in face_keys:
            raise ArithmeticError('closed_single_convex_shell_required')
        face_keys.add(key); used.update(face)
        a, b, c = (vertices[index] for index in face)
        normal = _cross(_sub(b, a), _sub(c, a))
        if _dot(normal, normal) == 0:
            raise ArithmeticError('degenerate_original_triangle')
        if any(_dot(normal, _sub(vertex, a)) > 0 for vertex in vertices):
            raise ArithmeticError('exact_convex_original_halfspaces_required')
        volume += _dot(_sub(a, origin), normal)
        for start, end in zip(face, face[1:]+face[:1]):
            edges.setdefault(tuple(sorted((start, end))), []).append((position, start < end))
    if len(used) != len(vertices) or volume <= 0:
        raise ArithmeticError('closed_outward_single_shell_required')
    for incident in edges.values():
        if len(incident) != 2 or incident[0][1] == incident[1][1]:
            raise ArithmeticError('closed_outward_single_shell_required')
        left, right = incident[0][0], incident[1][0]
        neighbours[left].add(right); neighbours[right].add(left)
    seen, pending = set(), [0]
    while pending:
        face = pending.pop()
        if face not in seen:
            seen.add(face); pending.extend(neighbours[face] - seen)
    if len(seen) != len(faces):
        raise ArithmeticError('closed_outward_single_shell_required')
    return vertices, faces


def _certificate(focal, reference, index):
    fv, ff = _rational_mesh(focal)
    rv, rf = _rational_mesh(reference)
    return _certificate_from_rationals(fv, rv, rf, index)


def _certificate_from_rationals(fv, rv, rf, index):
    """Internal proof from already validated exact mesh contents.

    Discovery reuses the same immutable, locally prepared rational pair while
    examining original triangles. Public candidate solving still prepares and
    validates both meshes on each current/candidate invocation above.
    """
    if index >= len(rf):
        raise ValueError('reference_triangle_index is outside the original mesh')
    ids = rf[index]; a, b, c = (rv[i] for i in ids)
    ab, ac = _sub(b, a), _sub(c, a)
    normal = _cross(ab, ac); normal_sq = _dot(normal, normal)
    if normal_sq <= 0:
        raise ArithmeticError('degenerate_original_triangle')
    if any(_dot(normal, _sub(vertex, a)) > 0 for vertex in rv):
        raise ArithmeticError('original_triangle_is_not_exact_global_support')
    heights = [_dot(normal, _sub(vertex, a)) for vertex in fv]
    height = min(heights)
    if height <= 0:
        raise ArithmeticError('strict_positive_support_gap_required')
    support = [i for i, value in enumerate(heights) if value == height]
    witness = None
    for vertex_index in support:
        vertex = fv[vertex_index]
        foot = tuple(vertex[k]-normal[k]*height/normal_sq for k in range(3))
        offset = _sub(foot, a)
        d00, d01, d11 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac)
        d20, d21 = _dot(offset, ab), _dot(offset, ac)
        v = (d11*d20-d01*d21)/normal_sq
        w = (d00*d21-d01*d20)/normal_sq
        barycentric = (1-v-w, v, w)
        if all(weight >= 0 for weight in barycentric):
            witness = (vertex_index, vertex, foot, barycentric)
            break
    if witness is None:
        raise ArithmeticError('minimum_support_projects_outside_original_triangle')
    scale = max(abs(value) for value in normal)
    scaled_normal = [float(value/scale) for value in normal]
    length = math.hypot(*scaled_normal)
    unit_normal = [value/length for value in scaled_normal]
    gap = float(height/scale)/length
    if not math.isfinite(gap) or gap <= 0:
        raise ArithmeticError('support_gap_not_representable')
    vertex_index, vertex, foot, barycentric = witness
    certificate = {'proof': 'exact_binary_rational_halfspaces_and_original_triangle_foot',
        'reference_triangle_index': index, 'reference_triangle_vertex_indices': ids,
        'support_vertex_indices': support, 'witness_vertex_index': vertex_index,
        'point_a_world': [float(x) for x in vertex], 'point_b_world': [float(x) for x in foot],
        'witness_export': 'rounded_display_coordinates_predicates_used_exact_rationals',
        'barycentric_exact': [str(x) for x in barycentric], 'plane_normal_world': unit_normal,
        'plane_clearance_m': gap, 'predicate_tolerance_m': 0.0,
        'convex_admission': 'exact_original_halfspaces_and_closed_connected_outward_topology',
        'distance_proof_independent_of_convexity_tolerance': True,
        'scope': 'represented_pair_surface_distance_only', 'execution_authority': False}
    return certificate


def _strict(mesh_a, mesh_b, certificate, *, _observation=None):
    if _observation is not None:
        if type(_observation) is not _ValidatedObservation:
            raise ValueError('Validated observation required for measurement reuse')
        _observation._require_scene(_observation.scene)
    try:
        measured = (measure_pair_geometry(mesh_a, mesh_b, need_clearance=True)
            if _observation is None else _observation._measure_pair(
                mesh_a, mesh_b, measure_pair_geometry, need_clearance=True))
    except (ValueError, IndexError, TypeError, AttributeError, FloatingPointError, OverflowError) as exc:
        raise ArithmeticError('strict_pair_measurement_failed') from exc
    metric = measured.get('signed_clearance_m')
    if (measured.get('measurement_valid') is not True or measured.get('is_penetrating') is not False
            or type(metric) not in (int, float) or not math.isfinite(metric) or metric <= 0):
        raise ArithmeticError('strict_pair_clearance_unavailable')
    gap = certificate['plane_clearance_m']
    # Arithmetic agreement only, independent of caller goal tolerance. Exact
    # halfspace / footprint predicates above never consume this allowance.
    # A huge world origin must not buy a huge agreement tolerance. The
    # comparison scale comes from local extents, with a hard 1e-10 m ceiling.
    extent = max(float(np.ptp(mesh.vertices, axis=0).max()) for mesh in (mesh_a, mesh_b))
    agreement = min(1e-10, 64 * max(math.ulp(gap), math.ulp(float(metric)), math.ulp(extent)))
    if not math.isfinite(agreement) or abs(float(metric)-gap) > agreement:
        raise ArithmeticError('support_gap_disagrees_with_strict_clearance')
    return measured, agreement


def _failed(result, code, status='unsupported'):
    result.update(status=status, supported=False, candidate=None, reason_codes=[code])
    return result


def solve_support_plane_candidate(scene, request, *, expected_feature_signature=None,
                                  _observation=None):
    """Propose one bounded translation from a snapshot; never execute it.

    The contact-feature signature binds reference geometry, selected triangle,
    focal topology/support vertex identity, and direction. It deliberately is
    not a focal shape/instance/external-edit proof or a cross-step write gate.
    """
    request = validate_support_plane_request(request)
    if _observation is not None:
        if type(_observation) is not _ValidatedObservation:
            raise ValueError('Validated observation required for scene reuse')
        _observation._require_scene(scene)
    if expected_feature_signature is not None and (
            not isinstance(expected_feature_signature, str) or len(expected_feature_signature) != 64
            or any(c not in '0123456789abcdef' for c in expected_feature_signature)):
        raise ValueError('expected_feature_signature requires a lowercase SHA256 digest')
    result = {'schema_version': '1.0', 'contract_revision': CONTRACT_REVISION,
        'status': 'unsupported', 'supported': False, 'measurement_valid': False,
        'goal_satisfied': False, 'candidate': None, 'feature_signature': None,
        'current_clearance_m': None, 'signed_error_m': None, 'absolute_error_m': None,
        'request': copy.deepcopy(request), 'focal_id': request['focal_id'],
        'reference_id': request['reference_id'], 'unit': 'm', 'coordinate_frame': 'world',
        'scope': 'readonly_exact_original_support_triangle_pair_candidate',
        'measurement_kind': 'unknown', 'execution_authority': False,
        'whole_scene_collision_certified': False, 'swept_path_certified': False,
        'task_success_certified': False, 'ground_truth_independent': False,
        'requires_fresh_execution_gate': True, 'reason_codes': [],
        'contact_signature_scope': 'reference_geometry_and_contact_features_not_focal_shape_instance_or_edit_proof',
        'resource_limits': {'pair_vertices_per_mesh': MAX_VERTICES, 'pair_faces_per_mesh': MAX_FACES,
            'scene_vertices': MAX_SCENE_VERTICES, 'scene_faces': MAX_SCENE_FACES,
            'input_rational_numerator_denominator_bits': MAX_RATIONAL_BITS}}
    limit_reason = _preflight(scene, request)
    if limit_reason:
        return _failed(result, limit_reason, 'unknown')
    if _observation is None:
        normalized, meshes, fingerprint = _validated_scene(scene)
    else:
        normalized, meshes, fingerprint = (
            _observation.scene, _observation.meshes, _observation.fingerprint)
    result.update(scene_revision=normalized['revision'], scene_fingerprint=fingerprint,
                  scene_source=normalized['source'])
    by_id = {m.object_id: m for m in meshes}
    focal, reference = by_id[request['focal_id']], by_id[request['reference_id']]
    index = request['reference_triangle_index']
    if index >= len(reference.faces):
        raise ValueError('reference_triangle_index is outside the original mesh')
    if normalized.get('host_execution', {}).get('supported') is False:
        return _failed(result, 'host_rigid_execution_unsupported')
    if pair_rigid_frame_status(focal, reference)['valid'] is not True:
        return _failed(result, 'rigid_frame_unavailable')
    if request['target_clearance_m'] == 0:
        return _failed(result, 'positive_target_clearance_required')
    try:
        certificate = _certificate(focal, reference, index)
        result['current_certificate'] = certificate
        strict_options = {} if _observation is None else {'_observation': _observation}
        measured, agreement = _strict(focal, reference, certificate, **strict_options)
        metric = float(measured['signed_clearance_m'])
        features = {'reference_id': reference.object_id, 'reference_vertices': reference.vertices.tolist(),
            'reference_faces': reference.faces.tolist(), 'reference_triangle_index': index,
            'focal_id': focal.object_id, 'focal_faces': focal.faces.tolist(),
            'focal_support_vertex_indices': certificate['support_vertex_indices'],
            'direction_world': request['direction_world']}
        signature = _digest(features);result['feature_signature'] = signature
        if expected_feature_signature is not None and signature != expected_feature_signature:
            return _failed(result, 'contact_feature_changed', 'feature_changed')
        residual = metric-request['target_clearance_m']
        if not math.isfinite(residual):
            return _failed(result, 'target_residual_nonfinite', 'unknown')
        result.update(supported=True, measurement_valid=True, measurement_kind='exact',
            current_clearance_m=metric, signed_error_m=residual, absolute_error_m=abs(residual),
            current_strict_geometry=measured, metric_agreement_tolerance_m=agreement)
        if abs(residual) <= request['clearance_tolerance_m']:
            result.update(status='goal_satisfied', goal_satisfied=True)
            return result
        direction = request['direction_world']
        derivative = math.fsum(a*b for a, b in zip(certificate['plane_normal_world'], direction))
        result['directional_derivative'] = derivative
        if not math.isfinite(derivative) or abs(derivative) < MIN_DIRECTIONAL_DERIVATIVE:
            return _failed(result, 'direction_nearly_parallel_to_support_plane')
        scalar = (request['target_clearance_m']-certificate['plane_clearance_m'])/derivative
        budget = min(request['max_step_translation_m'], request['max_total_translation_m'])
        clipped_scalar = math.copysign(min(abs(scalar), budget), scalar)
        translation = [value*clipped_scalar for value in direction]
        # Round toward the safe side if normalization/multiplication overshot
        # the caller's Euclidean length bound by an ULP.
        for _ in range(8):
            if math.hypot(*translation) <= budget:
                break
            previous = clipped_scalar
            clipped_scalar = math.nextafter(clipped_scalar, 0.0)
            if clipped_scalar == previous:
                return _failed(result, 'no_representable_progress', 'precision_floor')
            translation = [value*clipped_scalar for value in direction]
        else:
            return _failed(result, 'requested_vector_exceeds_translation_budget', 'precision_floor')
        if not all(math.isfinite(value) for value in translation) or not any(translation):
            return _failed(result, 'no_representable_progress', 'precision_floor')
        detached = focal.to_dict()
        # A bound on requested vector length does not alone bound rounded
        # vertex motion. Shrink a limited number of times instead of accepting
        # an over-budget ULP or rejecting ordinary clipped millimetre steps.
        rounding_margin = max(math.hypot(*(math.ulp(float(value)) for value in vertex))
                              for vertex in focal.vertices)
        actual_max = math.inf
        for attempt in range(8):
            vertices = np.asarray(focal.vertices, dtype=np.float64)+np.asarray(translation)
            if not np.isfinite(vertices).all() or np.array_equal(vertices, focal.vertices):
                return _failed(result, 'no_representable_progress', 'precision_floor')
            actual_max = max(math.hypot(*(float(a)-float(b) for a, b in zip(new, old)))
                             for new, old in zip(vertices, focal.vertices))
            if actual_max <= budget:
                break
            magnitude = max(0.0, abs(clipped_scalar)-rounding_margin)
            clipped_scalar = math.copysign(math.nextafter(magnitude, 0.0), clipped_scalar)
            translation = [value*clipped_scalar for value in direction]
        else:
            return _failed(result, 'rounded_geometry_exceeds_translation_budget', 'precision_floor')
        detached['vertices'] = vertices.tolist()
        if detached.get('pivot_world') is not None:
            detached['pivot_world'] = [float(value)+translation[k] for k, value in enumerate(detached['pivot_world'])]
        candidate_mesh = MeshEntity3D.from_dict(detached)
        candidate_certificate = _certificate(candidate_mesh, reference, index)
        result['candidate_certificate'] = candidate_certificate
        candidate_measurement = None
        if candidate_certificate['support_vertex_indices'] != certificate['support_vertex_indices']:
            # Exact rounding can change which vertices attain the minimum,
            # even when the intended rigid translation is tiny. Do not merge
            # these features or inherit an ideal-translation certificate.
            # Instead, try at most four strictly smaller read-only proposals;
            # every accepted proposal proves the same original support set on
            # its actual rounded coordinates and passes all original checks.
            search = {'schema_version': 'bounded-inward-rounded-proposals-v1',
                'trigger_reason': 'contact_feature_changed_after_rounded_translation',
                'original_scalar_m': clipped_scalar, 'rounding_margin_m': rounding_margin,
                'original_support_vertex_indices': list(certificate['support_vertex_indices']),
                'first_candidate_support_vertex_indices': list(candidate_certificate['support_vertex_indices']),
                'max_attempts': _MAX_INWARD_FEATURE_PROPOSALS, 'attempts': [],
                'accepted_attempt': None, 'execution_authority': False}
            original_scalar = clipped_scalar
            for attempt in range(1, _MAX_INWARD_FEATURE_PROPOSALS + 1):
                magnitude = abs(original_scalar) - attempt * rounding_margin
                trial = {'attempt': attempt, 'status': 'refused'}
                search['attempts'].append(trial)
                if not math.isfinite(magnitude) or not 0 < magnitude < abs(original_scalar):
                    trial['reason'] = 'no_smaller_representable_proposal'
                    break
                trial_scalar = math.copysign(magnitude, original_scalar)
                trial_translation = [value * trial_scalar for value in direction]
                trial['scalar_m'] = trial_scalar
                if (not all(math.isfinite(value) for value in trial_translation)
                        or not any(trial_translation) or math.hypot(*trial_translation) > budget):
                    trial['reason'] = 'invalid_or_over_budget_proposal'
                    break
                trial_vertices = focal.vertices + np.asarray(trial_translation)
                if not np.isfinite(trial_vertices).all() or np.array_equal(trial_vertices, focal.vertices):
                    trial['reason'] = 'no_representable_progress'
                    break
                trial_max = max(math.hypot(*(float(a)-float(b) for a, b in zip(new, old)))
                    for new, old in zip(trial_vertices, focal.vertices))
                if trial_max > budget:
                    trial['reason'] = 'rounded_geometry_exceeds_translation_budget'
                    break
                trial_detached = focal.to_dict()
                trial_detached['vertices'] = trial_vertices.tolist()
                if trial_detached.get('pivot_world') is not None:
                    trial_detached['pivot_world'] = [float(value)+trial_translation[k]
                        for k, value in enumerate(trial_detached['pivot_world'])]
                try:
                    trial_mesh = MeshEntity3D.from_dict(trial_detached)
                    trial_certificate = _certificate(trial_mesh, reference, index)
                    trial['support_vertex_indices'] = list(trial_certificate['support_vertex_indices'])
                    if trial_certificate['support_vertex_indices'] != certificate['support_vertex_indices']:
                        trial['reason'] = 'contact_feature_changed_after_rounded_translation'
                        continue
                    trial_measurement, trial_agreement = _strict(
                        trial_mesh, reference, trial_certificate, **strict_options)
                except (ArithmeticError, FloatingPointError, OverflowError) as exc:
                    # A numerical/resource/unsupported failure is not a
                    # reason to search around an unproved geometry domain.
                    trial['reason'] = str(exc) or 'support_plane_numeric_failure'
                    break
                trial_gap = float(trial_measurement['signed_clearance_m'])
                trial_prediction = certificate['plane_clearance_m'] + trial_scalar * derivative
                if (not math.isfinite(trial_prediction)
                        or abs(trial_gap-trial_prediction) > max(agreement, trial_agreement)):
                    trial['reason'] = 'rounded_candidate_disagrees_with_linear_prediction'
                    break
                if not abs(trial_gap-request['target_clearance_m']) < abs(residual):
                    trial['reason'] = 'no_representable_progress'
                    break
                clipped_scalar, translation, vertices, actual_max = (
                    trial_scalar, trial_translation, trial_vertices, trial_max)
                candidate_mesh, candidate_certificate = trial_mesh, trial_certificate
                candidate_measurement, after_agreement = trial_measurement, trial_agreement
                result['candidate_certificate'] = candidate_certificate
                trial['status'] = 'candidate'
                search['accepted_attempt'] = attempt
                break
            result['rounded_proposal_search'] = search
            if candidate_measurement is None:
                return _failed(result, 'contact_feature_changed_after_rounded_translation', 'feature_changed')
        if candidate_measurement is None:
            candidate_measurement, after_agreement = _strict(
                candidate_mesh, reference, candidate_certificate, **strict_options)
        actual_gap = float(candidate_measurement['signed_clearance_m'])
        predicted = certificate['plane_clearance_m']+clipped_scalar*derivative
        if not math.isfinite(predicted) or abs(actual_gap-predicted) > max(agreement, after_agreement):
            return _failed(result, 'rounded_candidate_disagrees_with_linear_prediction', 'unknown')
        error = abs(actual_gap-request['target_clearance_m'])
        if not error < abs(residual):
            return _failed(result, 'no_representable_progress', 'precision_floor')
        result.update(status='candidate', candidate={'focal_id': focal.object_id,
            'reference_id': reference.object_id, 'translation': translation,
            'rotation_euler_deg': [0.0, 0.0, 0.0]},
            candidate_strict_geometry=candidate_measurement,
            proposed_translation_m=math.hypot(*translation), actual_max_vertex_translation_m=actual_max,
            predicted_plane_clearance_m=predicted, candidate_clearance_m=actual_gap,
            predicted_absolute_error_m=error, candidate_metric_agreement_tolerance_m=after_agreement,
            step_clipped=abs(scalar)>budget)
        return result
    except (ArithmeticError, FloatingPointError, OverflowError) as exc:
        code = str(exc) or 'support_plane_numeric_failure'
        unknown = code in {'strict_pair_clearance_unavailable',
            'strict_pair_measurement_failed', 'support_gap_disagrees_with_strict_clearance', 'support_plane_rational_resource_limit',
            'support_gap_not_representable'} or isinstance(exc, (FloatingPointError, OverflowError))
        return _failed(result, code, 'unknown' if unknown else 'unsupported')


__all__ = ['CONTRACT_REVISION', 'REQUEST_SCHEMA', 'validate_support_plane_request',
           'solve_support_plane_candidate']
