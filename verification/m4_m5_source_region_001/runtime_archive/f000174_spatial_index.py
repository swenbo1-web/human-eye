"""Immutable conservative object AABBs for complete terminal-geometry queries.

All scene objects require existing solid-support validation of their complete
current contents before pruning. Observations may reuse exact-content results;
execution indexes always validate afresh. Bounds use current vertices and expand
outward. An L-infinity AABB gap is a lower bound, never an exact mesh distance;
using it avoids squaring/normalization errors in separation decisions. This
module does not write a host, cache measurements, or certify swept motion.
"""
from __future__ import annotations

import copy
import math
import numpy as np

from .geometry_safety import COLLISION_TOLERANCE_M, solid_support_status, work_budget_status


ALGORITHM_VERSION = "outward-object-aabb-linf-v1-20261023"


def _vertices(mesh):
    raw = mesh.get("vertices") if isinstance(mesh, dict) else mesh.vertices
    values = np.asarray(raw, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,) or len(values) < 3 or not np.isfinite(values).all():
        raise ValueError("Spatial index requires finite world-space Nx3 vertices")
    return values


def _identity(mesh):
    value = mesh.get("object_id") if isinstance(mesh, dict) else mesh.object_id
    if not isinstance(value, str) or not value:
        raise ValueError("Spatial index requires stable nonempty object IDs")
    return value


def _bounds(mesh):
    values = _vertices(mesh)
    lower, upper = values.min(axis=0), values.max(axis=0)
    # Padding addresses floating-point arithmetic, not physical uncertainty.
    # It only adds narrow-phase candidates; collision tolerance is unchanged.
    scale = np.maximum(1.0, np.maximum(np.abs(lower), np.abs(upper)))
    padding = np.maximum(COLLISION_TOLERANCE_M, scale * (64 * np.finfo(np.float64).eps))
    with np.errstate(over="ignore", invalid="ignore"):
        lower = np.nextafter(lower - padding, -np.inf)
        upper = np.nextafter(upper + padding, np.inf)
    return lower.copy(), upper.copy()


class SpatialSceneIndex:
    """A snapshot-derived index with full support and obstacle accounting.

    Query focal geometry may differ from the indexed original focal; this is
    necessary for a proposed transform. Execution queries freshly validate it.
    Indexed arrays and support facts are detached from caller-owned meshes.
    A scene fingerprint is provenance only and never a substitute for content.
    """

    def __init__(self, meshes, *, scene_fingerprint=None, observation_cache=None):
        meshes = list(meshes)
        if not 1 <= len(meshes) <= 256:
            raise ValueError("Spatial index requires 1..256 scene objects")
        self._ids = tuple(_identity(mesh) for mesh in meshes)
        if len(set(self._ids)) != len(self._ids):
            raise ValueError("Spatial index object IDs must be unique")
        if scene_fingerprint is not None and not isinstance(scene_fingerprint, str):
            raise ValueError("scene_fingerprint must be text or None")
        self.scene_fingerprint = scene_fingerprint
        # Observations may opt into exact-content memoization. Default indexes,
        # especially every before/after-action index, freshly validate solids.
        self._support_evaluator = (solid_support_status if observation_cache is None
                                  else observation_cache._observation_solid_support)
        self.work_budget = work_budget_status(meshes, purpose="mesh_validation")
        self._support = {}
        lowers, uppers = [], []
        for identity, mesh in zip(self._ids, meshes):
            if self.work_budget["within_budget"]:
                lower, upper = _bounds(mesh)
            else:
                lower, upper = np.full(3, -np.inf), np.full(3, np.inf)
            lowers.append(lower)
            uppers.append(upper)
            if self.work_budget["within_budget"]:
                self._support[identity] = self._support_evaluator(mesh)
            else:
                self._support[identity] = {"supported": False, "component_count": None,
                    "reason": "scene_solid_validation_resource_limit"}
        self._lower = np.array(lowers, dtype=np.float64)
        self._upper = np.array(uppers, dtype=np.float64)
        self._lower.setflags(write=False)
        self._upper.setflags(write=False)
        self._supported = all(value["supported"] is True for value in self._support.values())

    @classmethod
    def from_meshes(cls, meshes, *, scene_fingerprint=None):
        return cls(meshes, scene_fingerprint=scene_fingerprint)

    @property
    def supported(self):
        return self._supported

    @property
    def support_status(self):
        return copy.deepcopy(self._support)

    @property
    def object_ids(self):
        return self._ids

    def query(self, focal, *, max_distance_m=0.0, force_ids=()):
        if (type(max_distance_m) not in (int, float) or not math.isfinite(max_distance_m)
                or max_distance_m < 0):
            raise ValueError("max_distance_m must be finite and nonnegative")
        if not isinstance(force_ids, (list, tuple, set, frozenset)):
            raise ValueError("force_ids must be an explicit collection of object IDs")
        identity = _identity(focal)
        if any(not isinstance(value, str) or value not in self._ids or value == identity for value in force_ids):
            raise ValueError("Unknown or focal force_ids")
        forced = set(force_ids)
        focal_support = self._support_evaluator(focal)
        supported = self.supported and focal_support["supported"] is True
        if focal_support.get("work_budget", {}).get("within_budget") is False:
            lower, upper = np.full(3, -np.inf), np.full(3, np.inf)
        else:
            lower, upper = _bounds(focal)
        # For exact represented endpoints each subtraction is rounded down
        # once. Max of the three nonnegative axis gaps is an L-infinity lower
        # bound on Euclidean mesh clearance. There is no sqrt or sum to round.
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            gaps = np.maximum(np.maximum(self._lower - upper, lower - self._upper), 0.0)
            gaps = np.maximum(np.nextafter(gaps, -np.inf), 0.0)
        finite = np.isfinite(gaps).all(axis=1) & np.isfinite(self._lower).all(axis=1) & np.isfinite(self._upper).all(axis=1)
        focal_finite = bool(np.isfinite(lower).all() and np.isfinite(upper).all())
        bounds = np.max(np.where(np.isfinite(gaps), gaps, 0.0), axis=1)
        candidates, separated, pairs = [], [], []
        for position, other_id in enumerate(self._ids):
            if other_id == identity:
                continue
            numeric_valid = bool(finite[position] and focal_finite)
            bound = float(bounds[position]) if numeric_valid else 0.0
            supported_pair = focal_support["supported"] is True and self._support[other_id]["supported"] is True
            candidate = (not supported_pair or not numeric_valid or other_id in forced
                         or bound <= max_distance_m)
            item = {"object_id": other_id, "is_candidate": bool(candidate),
                "signed_clearance_m": None, "clearance_lower_bound_m": bound,
                "clearance_exact": False, "measurement_valid": False,
                "clearance_method": "outward_aabb_linf_lower_bound",
                "measurement_kind": "lower_bound" if numeric_valid else "unknown",
                "method": "outward_aabb_linf_lower_bound" if numeric_valid else "measurement_unavailable",
                "clearance_scope": "unsigned_surface_distance_lower_bound" if numeric_valid else "unknown",
                "numeric_bound_valid": numeric_valid,
                "collision_assessment_valid": bool(supported_pair and not candidate),
                "is_penetrating": False if supported_pair and not candidate else None,
                "point_a_world": None, "point_b_world": None,
                "independent_ground_truth": False, "evaluator_source": "engine_aabb_bounds"}
            pairs.append(item)
            if candidate:
                candidates.append(other_id)
            else:
                separated.append(copy.deepcopy(item))
        reasons = []
        if not self.supported:
            reasons.append("scene_solid_support_unknown")
        if focal_support["supported"] is not True:
            reasons.append("focal_solid_support_unknown")
        if not focal_finite or not bool(finite.all()):
            reasons.append("numeric_bounds_retained_conservatively")
        return {"schema_version": "1.0", "algorithm_version": ALGORITHM_VERSION,
            "supported": supported, "focal_id": identity, "scene_fingerprint": self.scene_fingerprint,
            "max_distance_m": float(max_distance_m), "candidate_ids": candidates,
            "query_pairs": [[identity, value] for value in candidates],
            "separated_records": separated, "pairs": pairs, "reason_codes": reasons,
            "focal_support_status": focal_support, "coverage_object_count": len(pairs),
            "scope": "terminal_known_solid_geometry_only_not_swept_path",
            "collision_tolerance_m": COLLISION_TOLERANCE_M}


__all__ = ["SpatialSceneIndex", "ALGORITHM_VERSION"]
