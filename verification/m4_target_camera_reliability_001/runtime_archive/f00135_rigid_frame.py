"""Validate an explicitly supplied host frame for world-space rigid deltas.

A host object frame need not coincide with polyhedron face normals. This
contract deliberately says nothing about the legacy face-alignment controller,
contact-angle goals, solid support, collision, or execution permission.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np


RIGID_FRAME_CONTRACT_REVISION = "host-explicit-world-rigid-frame-v1-20261023"
_ORTHONORMAL_TOLERANCE = 1e-6
_RAW_REJECTION_PREFIX = "raw_rigid_frame_rejected:"
_FIELDS = ("local_axes", "pivot_world", "axes_source", "axes_confidence", "axes_reason")


def _values(mesh):
    if isinstance(mesh, Mapping):
        return {key: mesh.get(key) for key in _FIELDS}
    return {key: getattr(mesh, key, None) for key in _FIELDS}


def rigid_frame_status(mesh):
    """Describe current raw values without filling, fitting, or repairing them.

    Read-only geometry-inferred frames remain useful for observations but do
    not acquire host-authoritative execution semantics. Numeric strings and
    booleans are not accepted as frame entries, even if NumPy can coerce them.
    """
    values = _values(mesh)
    reasons = []
    for key in _FIELDS:
        if values[key] is None:
            reasons.append("missing_" + key)
    source, confidence, reason = (values[key] for key in
                                  ("axes_source", "axes_confidence", "axes_reason"))
    if not isinstance(source, str) or source != "host":
        reasons.append("axes_source_not_host")
    if not isinstance(confidence, str) or confidence != "explicit":
        reasons.append("axes_not_explicit")
    if not isinstance(reason, str) or not reason.strip():
        reasons.append("axes_provenance_reason_missing")
    upstream = (reason[len(_RAW_REJECTION_PREFIX):].split(",")
                if isinstance(reason, str) and reason.startswith(_RAW_REJECTION_PREFIX) else [])
    error = determinant = None
    basis = pivot = None
    for key, shape in (("local_axes", (3, 3)), ("pivot_world", (3,))):
        if values[key] is None:
            continue
        try:
            raw = np.asarray(values[key])
            if (raw.shape != shape or raw.dtype.kind not in "ifu"
                    or any(isinstance(value, (bool, np.bool_))
                           for value in np.asarray(values[key], dtype=object).flat)):
                reasons.append(key + "_shape_or_non_numeric")
                continue
            numeric = np.asarray(raw, dtype=np.float64)
            if not np.isfinite(numeric).all():
                reasons.append(key + "_non_finite")
                continue
            if key == "local_axes":
                basis = numeric.tolist()
                with np.errstate(over="raise", invalid="raise"):
                    error = float(np.max(np.abs(numeric @ numeric.T - np.eye(3))))
                    determinant = float(np.linalg.det(numeric))
                if not math.isfinite(error) or not math.isfinite(determinant):
                    error = determinant = None
                    reasons.append("local_axes_non_finite_check")
                else:
                    if error > _ORTHONORMAL_TOLERANCE:
                        reasons.append("local_axes_not_orthonormal")
                    if determinant <= 0:
                        reasons.append("local_axes_not_right_handed")
            else:
                pivot = numeric.tolist()
        except (TypeError, ValueError, OverflowError, FloatingPointError, np.linalg.LinAlgError):
            error = determinant = None
            reasons.append(key + "_evaluation_failed")
    return {
        "schema_version": "1.0", "contract_revision": RIGID_FRAME_CONTRACT_REVISION,
        "valid": not reasons, "reason_codes": list(dict.fromkeys(reasons)),
        "raw_rejection_reason_codes": list(upstream),
        "axes_source": source if isinstance(source, str) else None,
        "axes_confidence": confidence if isinstance(confidence, str) else None,
        "axes_reason": reason if isinstance(reason, str) else None,
        "local_axes_row_basis": basis, "pivot_world_m": pivot,
        "orthonormal_max_error": error, "determinant": determinant,
        "orthonormal_tolerance": _ORTHONORMAL_TOLERANCE,
        "scope": "provided_host_world_rigid_frame_not_face_alignment",
        "face_normal_alignment_required": False, "execution_authority": False,
    }


def preserve_raw_frame_rejection(raw_status, normalized_mesh):
    """Prevent a core default/coercion from laundering rejected raw metadata.

    Only a rejection that would become valid after construction is marked.
    Existing inferred/ambiguous provenance and unmodified bad numeric bases
    retain their original legacy diagnostics. Markers survive serialization.
    """
    if raw_status["valid"] is not True and rigid_frame_status(normalized_mesh)["valid"] is True:
        normalized_mesh.axes_source = "unverified_imported_frame"
        normalized_mesh.axes_confidence = "ambiguous"
        normalized_mesh.axes_reason = _RAW_REJECTION_PREFIX + ",".join(raw_status["reason_codes"])


def pair_rigid_frame_status(focal, reference):
    """Validate both independently supplied frames; never grant authority."""
    checks = {"focal": rigid_frame_status(focal), "reference": rigid_frame_status(reference)}
    reasons = [role + ":" + reason for role, status in checks.items()
               for reason in status["reason_codes"]]
    return {"schema_version": "1.0", "contract_revision": RIGID_FRAME_CONTRACT_REVISION,
            "valid": not reasons, "reason_codes": reasons, "objects": checks,
            "scope": "provided_host_world_rigid_pair_frames_not_face_alignment",
            "execution_authority": False}


__all__ = ["RIGID_FRAME_CONTRACT_REVISION", "rigid_frame_status",
           "pair_rigid_frame_status", "preserve_raw_frame_rejection"]
