"""Pure, bounded candidate solving with explicit clearance-constraint domains.

This module never writes a host, grants authority, certifies a whole scene or
claims independent task success. Legacy requests accept only exact world-axis
boxes. Explicit support_plane requests select an original supporting triangle
and a world direction; their candidates retain the separately proven finite
surface certificate. Neither domain silently substitutes fitted AABBs or an
arbitrary nearest-point distance for the selected constraint.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from .auto_router import _validated_scene
from .geometry_safety import measure_pair_geometry
from .rigid_frame import pair_rigid_frame_status
from .support_plane_candidate import (
    REQUEST_SCHEMA as SUPPORT_PLANE_REQUEST_SCHEMA,
    solve_support_plane_candidate, validate_support_plane_request,
)


SEGMENT_CONTRACT_REVISION = "bounded-world-box-clearance-v1-20261026"
_AXES = {"+x": (0, 1), "-x": (0, -1), "+y": (1, 1),
         "-y": (1, -1), "+z": (2, 1), "-z": (2, -1)}
_DEFAULTS = {"max_steps": 4, "max_step_translation_m": .01,
             "max_total_translation_m": .04, "max_duration_s": 5.0}
_REQUIRED = ("focal_id", "reference_id", "axis", "target_clearance_m",
             "clearance_tolerance_m")
_ALLOWED = frozenset(_REQUIRED) | frozenset(_DEFAULTS)

_BOX_SEGMENT_REQUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(_REQUIRED),
    "description": "A bounded goal request, never an execution permission. Version one supports exact world-axis box faces only. Axis points from reference toward focal; each correction may move either way along that axis.",
    "properties": {
        "focal_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "reference_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "axis": {"type": "string", "enum": list(_AXES)},
        "target_clearance_m": {"type": "number", "minimum": 0},
        "clearance_tolerance_m": {"type": "number", "minimum": 0},
        "max_steps": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4},
        "max_step_translation_m": {"type": "number", "exclusiveMinimum": 0,
                                   "maximum": 1, "default": .01},
        "max_total_translation_m": {"type": "number", "exclusiveMinimum": 0,
                                    "maximum": 4, "default": .04},
        "max_duration_s": {"type": "number", "exclusiveMinimum": 0,
                           "maximum": 30, "default": 5},
    },
}

_SUPPORT_REQUIRED = ("focal_id", "reference_id", "solver", "reference_triangle_index",
                     "direction_world", "target_clearance_m", "clearance_tolerance_m")
_SUPPORT_ALLOWED = frozenset(_SUPPORT_REQUIRED) | frozenset(_DEFAULTS) | {'selection_binding'}
_SUPPORT_SOLVER_FIELDS = tuple(SUPPORT_PLANE_REQUEST_SCHEMA["properties"])
_SELECTION_BINDING_FIELDS = ("scene_revision", "scene_fingerprint", "focal_id", "reference_id")
SELECTION_BINDING_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(_SELECTION_BINDING_FIELDS),
    "description": "Initial captured-scene freshness and pair binding, never execution authority or verified user intent. Later steps retain their separate fresh checks.",
    "properties": {
        "scene_revision": {"type": "string", "minLength": 1, "maxLength": 256},
        "scene_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "focal_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "reference_id": {"type": "string", "minLength": 1, "maxLength": 256},
    },
}
_SUPPORT_SEGMENT_REQUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": list(_SUPPORT_REQUIRED),
    "properties": {**copy.deepcopy(SUPPORT_PLANE_REQUEST_SCHEMA["properties"]),
        "solver": {"type": "string", "enum": ["support_plane"]},
        "selection_binding": copy.deepcopy(SELECTION_BINDING_SCHEMA),
        "max_steps": copy.deepcopy(_BOX_SEGMENT_REQUEST_SCHEMA["properties"]["max_steps"]),
        "max_duration_s": copy.deepcopy(_BOX_SEGMENT_REQUEST_SCHEMA["properties"]["max_duration_s"])},
}
CLEARANCE_SEGMENT_REQUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "description": "A bounded goal request, never execution permission. Use the legacy explicit world-axis box constraint, or solver=support_plane with an explicitly selected original reference triangle and world direction. Each actual step still needs fresh whole-scene checks and readback.",
    "required": ["focal_id", "reference_id", "target_clearance_m", "clearance_tolerance_m"],
    "properties": {**copy.deepcopy(_BOX_SEGMENT_REQUEST_SCHEMA["properties"]),
                   **copy.deepcopy(_SUPPORT_SEGMENT_REQUEST_SCHEMA["properties"])},
    "oneOf": [copy.deepcopy(_BOX_SEGMENT_REQUEST_SCHEMA),
              copy.deepcopy(_SUPPORT_SEGMENT_REQUEST_SCHEMA)],
}


def _number(value, field, *, positive=False, maximum=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(field + " must be a finite number, not a boolean")
    result = float(value)
    if result < 0 or positive and result <= 0 or maximum is not None and result > maximum:
        raise ValueError(field + " is outside the supported range")
    return result


def _validate_box_clearance_segment_request(request):
    """Normalize only finite, explicit goal and budget fields; no defaults for intent."""
    if not isinstance(request, dict) or set(request) - _ALLOWED or not set(_REQUIRED).issubset(request):
        raise ValueError("Clearance segment requires only the supported goal and budget fields")
    result = {}
    for field in ("focal_id", "reference_id"):
        value = request[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(field + " must be a nonempty object identity of at most 256 characters")
        result[field] = value
    if result["focal_id"] == result["reference_id"]:
        raise ValueError("Clearance segment requires distinct objects")
    if not isinstance(request["axis"], str) or request["axis"] not in _AXES:
        raise ValueError("axis must be one of +x, -x, +y, -y, +z, -z")
    result["axis"] = request["axis"]
    for field in ("target_clearance_m", "clearance_tolerance_m"):
        result[field] = _number(request[field], field)
    steps = request.get("max_steps", _DEFAULTS["max_steps"])
    if type(steps) is not int or not 1 <= steps <= 8:
        raise ValueError("max_steps must be an integer in 1..8")
    result["max_steps"] = steps
    for field, maximum in (("max_step_translation_m", 1),
                           ("max_total_translation_m", 4), ("max_duration_s", 30)):
        result[field] = _number(request.get(field, _DEFAULTS[field]), field,
                                positive=True, maximum=maximum)
    return result


def _validate_support_plane_segment_request(request):
    if (set(request) - _SUPPORT_ALLOWED
            or not set(_SUPPORT_REQUIRED).issubset(request)):
        raise ValueError("Support-plane segment requires only its explicit constraint and budget fields")
    # The pure solver validates and normalizes a direction for calculation.
    # Persistence must instead retain its original finite vector, converted
    # once to floats. Re-normalizing unit vectors on every ledger load is not
    # guaranteed to be bitwise idempotent and could invalidate old receipts.
    solver_request = {field: request[field] for field in _SUPPORT_SOLVER_FIELDS if field in request}
    validated = validate_support_plane_request(solver_request)
    result = {"focal_id": validated["focal_id"], "reference_id": validated["reference_id"],
        "solver": "support_plane", "reference_triangle_index": validated["reference_triangle_index"],
        "direction_world": [float(value) for value in request["direction_world"]],
        "target_clearance_m": validated["target_clearance_m"],
        "clearance_tolerance_m": validated["clearance_tolerance_m"]}
    steps = request.get("max_steps", _DEFAULTS["max_steps"])
    if type(steps) is not int or not 1 <= steps <= 8:
        raise ValueError("max_steps must be an integer in 1..8")
    result["max_steps"] = steps
    for field, maximum in (("max_step_translation_m", 1),
                           ("max_total_translation_m", 4), ("max_duration_s", 30)):
        result[field] = _number(request.get(field, _DEFAULTS[field]), field,
                                positive=True, maximum=maximum)
    if 'selection_binding' in request:
        binding = request['selection_binding']
        if not isinstance(binding, dict) or set(binding) != set(_SELECTION_BINDING_FIELDS):
            raise ValueError('selection_binding requires only its captured scene and pair fields')
        normalized_binding = {}
        for field in _SELECTION_BINDING_FIELDS:
            value = binding[field]
            if field == 'scene_fingerprint':
                if (not isinstance(value, str) or len(value) != 64
                        or any(c not in '0123456789abcdef' for c in value)):
                    raise ValueError('selection_binding.scene_fingerprint requires lowercase SHA256')
            elif not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError('selection_binding.' + field + ' requires a nonempty string of at most 256 characters')
            normalized_binding[field] = value
        result['selection_binding'] = normalized_binding
    return result


def validate_clearance_segment_request(request):
    """Validate one explicit domain, preserving legacy request normalization."""
    if isinstance(request, dict) and request.get("solver") == "support_plane":
        return _validate_support_plane_segment_request(request)
    return _validate_box_clearance_segment_request(request)


def solve_segment_candidate(scene, request, *, expected_feature_signature=None):
    """Dispatch a pure constraint, not a write gate or binding validation.

    The live segment entry checks an optional initial selection binding before
    creating any running ledger. It must not reapply that initial revision to
    later captured snapshots produced by its own verified movement.
    """
    request = validate_clearance_segment_request(request)
    if request.get("solver") == "support_plane":
        solver_request = {field: request[field] for field in _SUPPORT_SOLVER_FIELDS}
        return solve_support_plane_candidate(scene, solver_request,
            expected_feature_signature=expected_feature_signature)
    return solve_clearance_candidate(scene, request,
        expected_feature_signature=expected_feature_signature)


def selection_binding_rejection(scene, request):
    """Compare discovery freshness with the initial capture; grant no rights.

    A matching binding does not authenticate its caller, the chosen surface,
    or human intent. It catches stale/mixed discovery results before planning;
    all geometry, host, version, instance and readback checks remain required.
    """
    request = validate_clearance_segment_request(request)
    binding = request.get('selection_binding')
    if binding is None:
        return None
    if any(binding[field] != request[field] for field in ('focal_id', 'reference_id')):
        return 'support_plane_selection_pair_mismatch'
    normalized, _, fingerprint = _validated_scene(scene)
    if binding['scene_revision'] != normalized['revision']:
        return 'support_plane_selection_stale_revision'
    if binding['scene_fingerprint'] != fingerprint:
        return 'support_plane_selection_stale_fingerprint'
    return None


def clearance_segment_goal(request):
    """Return criteria for the separate existing task verifier, not its verdict."""
    request = validate_clearance_segment_request(request)
    return {field: request[field] for field in (
        "focal_id", "reference_id", "target_clearance_m", "clearance_tolerance_m")}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _box_boundary(mesh):
    """Prove six complete rectangles from exact represented vertex coordinates.

    No coordinate snapping, fitted OBB, convex hull or epsilon plane test is
    used.  Each side has two triangles joined on its rectangle diagonal.
    Extra/subdivided vertices are deliberately outside this first contract.
    """
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if vertices.shape != (8, 3) or faces.shape != (12, 3):
        return None
    lower, upper = np.min(vertices, axis=0), np.max(vertices, axis=0)
    if not np.all(upper > lower):
        return None
    corners = []
    for vertex in vertices:
        bits = []
        for axis in range(3):
            if vertex[axis] == lower[axis]:
                bits.append(0)
            elif vertex[axis] == upper[axis]:
                bits.append(1)
            else:
                return None
        corners.append(tuple(bits))
    if len(set(corners)) != 8:
        return None
    groups = {(axis, side): [] for axis in range(3) for side in (0, 1)}
    seen, oriented_edges = set(), {}
    for position, raw_face in enumerate(faces):
        face = [int(value) for value in raw_face]
        if len(set(face)) != 3 or tuple(sorted(face)) in seen:
            return None
        seen.add(tuple(sorted(face)))
        planes = [(axis, corners[face[0]][axis]) for axis in range(3)
                  if len({corners[index][axis] for index in face}) == 1]
        if len(planes) != 1:
            return None
        groups[planes[0]].append((position, face))
        for start, end in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((start, end)))
            count, orientation = oriented_edges.get(edge, (0, 0))
            oriented_edges[edge] = (count + 1, orientation + (1 if start < end else -1))
    if any(count != 2 or orientation != 0 for count, orientation in oriented_edges.values()):
        return None
    for (axis, side), triangles in groups.items():
        if len(triangles) != 2:
            return None
        left, right = map(lambda value: set(value[1]), triangles)
        shared = left & right
        expected = {index for index, bits in enumerate(corners) if bits[axis] == side}
        if len(shared) != 2 or left | right != expected:
            return None
        start, end = sorted(shared)
        # Two opposite corners, rather than a boundary edge, divide a rectangle.
        if any(corners[start][other] == corners[end][other] for other in range(3) if other != axis):
            return None
    return {"lower": lower, "upper": upper, "corners": corners,
            "faces": faces.tolist(), "groups": groups}


def _failed(result, code, *, status="unsupported"):
    result.update(status=status, supported=False, candidate=None, reason_codes=[code])
    return result


def solve_clearance_candidate(scene, request, *, expected_feature_signature=None):
    """Read a snapshot and propose at most one clipped, pure-translation action.

    The feature signature binds face topology, corner identity and the overlap
    rectangle; it remains stable under an allowed focal axial translation.
    It is not an object-incarnation proof, host version check or authority.
    The caller separately owns step identities, elapsed/cumulative budgets,
    external-edit detection, fresh full-scene gates and actual readback.
    """
    request = _validate_box_clearance_segment_request(request)
    if (expected_feature_signature is not None
            and (not isinstance(expected_feature_signature, str)
                 or len(expected_feature_signature) != 64
                 or any(character not in "0123456789abcdef" for character in expected_feature_signature))):
        raise ValueError("expected_feature_signature must be a lower-case SHA256 digest")
    normalized, meshes, fingerprint = _validated_scene(scene)
    by_id = {mesh.object_id: mesh for mesh in meshes}
    if any(request[field] not in by_id for field in ("focal_id", "reference_id")):
        raise ValueError("Clearance segment object is not in the captured scene")
    result = {"schema_version": "1.0", "contract_revision": SEGMENT_CONTRACT_REVISION,
        "status": "unsupported", "supported": False, "measurement_valid": False,
        "goal_satisfied": False, "candidate": None, "feature_signature": None,
        "current_clearance_m": None, "signed_error_m": None, "absolute_error_m": None,
        "scene_revision": normalized["revision"], "scene_fingerprint": fingerprint,
        "scene_source": copy.deepcopy(normalized["source"]), "unit": "m",
        "coordinate_frame": "world", "focal_id": request["focal_id"],
        "reference_id": request["reference_id"], "request": copy.deepcopy(request),
        "scope": "exact_world_axis_box_pair_face_gap_candidate_only",
        "measurement_kind": "unknown", "execution_authority": False,
        "whole_scene_collision_certified": False, "swept_path_certified": False,
        "task_success_certified": False, "ground_truth_independent": False,
        "requires_fresh_execution_gate": True, "reason_codes": []}
    capability = normalized.get("host_execution", {}).get("supported")
    result["host_execution_capability"] = capability
    if capability is False:
        return _failed(result, "host_rigid_execution_unsupported")
    focal, reference = by_id[request["focal_id"]], by_id[request["reference_id"]]
    frames = pair_rigid_frame_status(focal, reference)
    if frames["valid"] is not True:
        return _failed(result, "rigid_frame_unavailable")
    boxes = [_box_boundary(mesh) for mesh in (focal, reference)]
    if any(box is None for box in boxes):
        return _failed(result, "exact_axis_box_boundary_required")
    focal_box, reference_box = boxes
    axis, sign = _AXES[request["axis"]]
    focal_side, reference_side = ((0, 1) if sign > 0 else (1, 0))
    focal_plane = float(focal_box["lower" if sign > 0 else "upper"][axis])
    reference_plane = float(reference_box["upper" if sign > 0 else "lower"][axis])
    plane_gap = sign * (focal_plane - reference_plane)
    if not math.isfinite(plane_gap) or plane_gap < 0:
        return _failed(result, "faces_not_separated_in_requested_axis")
    overlap = []
    for other in range(3):
        if other == axis:
            continue
        low = float(max(focal_box["lower"][other], reference_box["lower"][other]))
        high = float(min(focal_box["upper"][other], reference_box["upper"][other]))
        if not high > low:
            return _failed(result, "positive_face_overlap_required")
        overlap.append({"axis": other, "lower_m": low, "upper_m": high})
    features = {"proof": "exact_eight_corner_six_rectangle_boundary_v1",
        "axis": request["axis"], "overlap": overlap, "objects": []}
    for mesh, box, side in ((focal, focal_box, focal_side),
                            (reference, reference_box, reference_side)):
        features["objects"].append({"object_id": mesh.object_id,
            "corner_identity_by_vertex": box["corners"], "faces": box["faces"],
            "contact_face_triangle_indices": [entry[0] for entry in box["groups"][(axis, side)]],
            "tangent_bounds": [[float(box["lower"][other]), float(box["upper"][other])]
                               for other in range(3) if other != axis]})
    feature_signature = _digest(features)
    result.update(feature_signature=feature_signature, contact_features=features,
                  plane_clearance_m=plane_gap)
    if expected_feature_signature is not None and expected_feature_signature != feature_signature:
        return _failed(result, "contact_feature_changed", status="feature_changed")
    try:
        measured = measure_pair_geometry(focal, reference, need_clearance=True)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        return _failed(result, "strict_pair_measurement_failed", status="unknown")
    metric = measured.get("signed_clearance_m")
    if (measured.get("measurement_valid") is not True or type(metric) not in (int, float)
            or not math.isfinite(metric) or measured.get("is_penetrating") is not False or metric < 0):
        return _failed(result, "strict_pair_clearance_unavailable", status="unknown")
    metric = float(metric)
    # Numeric agreement is independent of the user's goal tolerance.  Neither
    # a generous tolerance nor AABB separation can launder a disagreeing metric.
    agreement = 32 * max(math.ulp(focal_plane), math.ulp(reference_plane),
                         math.ulp(plane_gap), math.ulp(metric))
    if not math.isfinite(agreement) or abs(metric - plane_gap) > agreement:
        return _failed(result, "face_gap_disagrees_with_strict_clearance", status="unknown")
    signed_error = metric - request["target_clearance_m"]
    error = abs(signed_error)
    if not math.isfinite(signed_error):
        return _failed(result, "target_residual_nonfinite", status="unknown")
    result.update(supported=True, measurement_valid=True, measurement_kind="exact",
        current_clearance_m=metric, signed_error_m=signed_error, absolute_error_m=error,
        metric_agreement_tolerance_m=agreement,
        measurement_method=measured.get("clearance_method", measured.get("measurement_method")))
    if error <= request["clearance_tolerance_m"]:
        result.update(status="goal_satisfied", goal_satisfied=True)
        return result
    correction = request["target_clearance_m"] - plane_gap
    limit = min(request["max_step_translation_m"], request["max_total_translation_m"])
    delta = math.copysign(min(abs(correction), limit), correction)
    translation = [0.0, 0.0, 0.0]
    translation[axis] = sign * delta
    next_plane = focal_plane + translation[axis]
    predicted_gap = sign * (next_plane - reference_plane)
    predicted_error = abs(predicted_gap - request["target_clearance_m"])
    if (not math.isfinite(predicted_gap) or next_plane == focal_plane
            or predicted_gap < 0 or predicted_error >= abs(plane_gap - request["target_clearance_m"])):
        result.update(status="precision_floor", reason_codes=["no_representable_progress"])
        return result
    result.update(status="candidate", candidate={"focal_id": focal.object_id,
        "reference_id": reference.object_id, "translation": translation,
        "rotation_euler_deg": [0.0, 0.0, 0.0]},
        proposed_translation_m=abs(delta), predicted_plane_clearance_m=predicted_gap,
        predicted_absolute_error_m=predicted_error,
        step_clipped=abs(correction) > limit)
    return result


__all__ = ["SEGMENT_CONTRACT_REVISION", "CLEARANCE_SEGMENT_REQUEST_SCHEMA",
           "validate_clearance_segment_request", "clearance_segment_goal",
           "solve_clearance_candidate", "solve_segment_candidate",
           "SELECTION_BINDING_SCHEMA", "selection_binding_rejection"]
