"""Evaluate explicit Blender adjustment goals against a current mesh snapshot.

This evaluator is separate from action execution verification.  Its pairwise
geometry comes from Human-Eye, so its result is not independent ground truth,
a certification of every scene object, or a guarantee about a motion path.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from human_eye_module1_operators import SpatialAnomalySniffer
from .auto_router import _validated_scene
from .geometry_safety import measure_pair_geometry


_ALLOWED_GOAL_FIELDS = {
    "focal_id", "reference_id", "target_clearance_m", "clearance_tolerance_m",
    "max_contact_normal_angle_deg", "max_tangent_yaw_mismatch_deg",
    "yaw_symmetry_order", "target_focal_pivot_world_m", "position_tolerance_m",
}
_TARGET_FIELDS = {
    "target_clearance_m", "max_contact_normal_angle_deg",
    "max_tangent_yaw_mismatch_deg", "target_focal_pivot_world_m",
}


def _number(value, name, *, minimum=None, maximum=None):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + " must be a finite number")
    value = float(value)
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(name + " is outside the supported range")
    return value


def _goal(value):
    if not isinstance(value, dict) or set(value) - _ALLOWED_GOAL_FIELDS:
        raise ValueError("Goal must be an object containing only supported fields")
    for key in ("focal_id", "reference_id"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(key + " must be a nonempty object identity")
    if value["focal_id"] == value["reference_id"]:
        raise ValueError("Goal requires distinct focal and reference objects")
    if not _TARGET_FIELDS.intersection(value):
        raise ValueError("At least one explicit spatial goal is required")
    result = {key: value[key] for key in ("focal_id", "reference_id")}
    order = value.get("yaw_symmetry_order", 2)
    if type(order) is not int or order not in (1, 2, 4):
        raise ValueError("yaw_symmetry_order must be 1, 2 or 4")
    result["yaw_symmetry_order"] = order
    for target, tolerance in (("target_clearance_m", "clearance_tolerance_m"),
                              ("target_focal_pivot_world_m", "position_tolerance_m")):
        if (target in value) != (tolerance in value):
            raise ValueError(target + " and " + tolerance + " must be provided together")
        if target not in value:
            continue
        result[tolerance] = _number(value[tolerance], tolerance, minimum=0)
        if target == "target_focal_pivot_world_m":
            vector = value[target]
            if not isinstance(vector, (list, tuple)) or len(vector) != 3:
                raise ValueError(target + " must contain three finite world-metre coordinates")
            result[target] = [_number(item, target) for item in vector]
        else:
            result[target] = _number(value[target], target, minimum=0)
    for field in ("max_contact_normal_angle_deg", "max_tangent_yaw_mismatch_deg"):
        if field in value:
            result[field] = _number(value[field], field, minimum=0, maximum=180)
    return result


def _finite_measurement(value):
    return type(value) in (int, float) and math.isfinite(value)


def _unrounded_contact_angles(focal, reference, probe, symmetry_order):
    """Use the probe's contact faces, without its display-angle rounding.

    The tangent-axis selection follows the existing triad's 0.65/0.45
    projection policy.  Normals and host axes remain engine-derived data.
    """
    def unit(vector):
        vector = np.asarray(vector, dtype=float)
        length = float(np.linalg.norm(vector))
        if vector.shape != (3,) or not np.isfinite(vector).all() or length <= 1e-12:
            raise ValueError("Invalid contact direction")
        return vector / length
    normal_a, normal_b = unit(probe.normal_a_world), unit(probe.normal_b_world)
    target = -normal_b
    cross = np.cross(normal_a, target)
    sine, cosine = float(np.linalg.norm(cross)), float(np.clip(normal_a @ target, -1, 1))
    angle = math.atan2(sine, cosine)
    rotation = np.eye(3)
    if angle > 0:
        if sine <= 1e-12:
            seed = focal.local_axes[0]
            if abs(float(normal_a @ seed)) >= 0.9:
                seed = focal.local_axes[1]
            axis = unit(np.cross(normal_a, seed))
        else:
            axis = cross / sine
        skew = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]],
                         [-axis[1], axis[0], 0]])
        rotation = np.eye(3) + math.sin(angle) * skew + (1 - math.cos(angle)) * (skew @ skew)
    focal_axes = np.asarray(focal.local_axes) @ rotation.T
    reference_axes = np.asarray(reference.local_axes)
    def projected(axes):
        values = axes - (axes @ normal_b)[:, None] * normal_b[None, :]
        return values, np.linalg.norm(values, axis=1)
    candidates, lengths = projected(focal_axes)
    selected = 0 if lengths[0] > 0.65 else int(np.argmax(lengths))
    if lengths[selected] <= 0.45:
        raise ValueError("No trustworthy focal tangent")
    tangent_a = candidates[selected] / lengths[selected]
    candidates_b, lengths_b = projected(reference_axes)
    selected_b = selected if lengths_b[selected] > 0.65 else int(np.argmax(lengths_b))
    if lengths_b[selected_b] <= 0.45:
        raise ValueError("No trustworthy reference tangent")
    tangent_b = candidates_b[selected_b] / lengths_b[selected_b]
    yaw = math.atan2(float(np.cross(tangent_a, tangent_b) @ normal_b),
                     float(np.clip(tangent_a @ tangent_b, -1, 1)))
    period = 2 * math.pi / symmetry_order
    yaw = (yaw + period / 2) % period - period / 2
    return {"contact_normal_angle_deg": math.degrees(angle),
            "tangent_yaw_mismatch_deg": abs(math.degrees(yaw))}


def evaluate_spatial_goal(scene, goal):
    """Return a conservative pairwise goal assessment without changing the host.

    Invalid input/identity raises ValueError.  Unsupported or invalid geometry,
    penetration, and untrusted axes for a requested angular goal cannot satisfy
    a task.  All requested goals are combined with AND; the pair must also be
    nonpenetrating.  A position goal uses the exported world object pivot, not
    the AABB centre, and requires an explicit pivot in the snapshot.  Clearances
    use the strict unrounded measurement, never the display probe's flush value.
    """
    normalized_goal = _goal(goal)
    try:
        normalized_scene, meshes, fingerprint = _validated_scene(scene)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid spatial scene: " + str(exc)) from exc
    by_id = {mesh.object_id: mesh for mesh in meshes}
    for key in ("focal_id", "reference_id"):
        if normalized_goal[key] not in by_id:
            raise ValueError("Unknown " + key)
    focal = by_id[normalized_goal["focal_id"]]
    reference = by_id[normalized_goal["reference_id"]]
    result = {
        "schema_version": "1.0", "status": "measurement_unavailable",
        "task_succeeded": False, "measurement_valid": False, "axes_valid": None,
        "evaluator_source": "human_eye_engine_geometry",
        "ground_truth_independent": False,
        "evaluation_scope": "known_mesh_pair_clearance_alignment_and_world_pivot",
        "scene_revision": normalized_scene["revision"], "scene_fingerprint": fingerprint,
        "focal_id": focal.object_id, "reference_id": reference.object_id,
        "goal": copy.deepcopy(normalized_goal), "measurements": {}, "checks": {},
        "reason_codes": [],
    }
    try:
        geometry = measure_pair_geometry(focal, reference, need_clearance=True)
    except Exception as exc:
        result["reason_codes"] = ["geometry_measurement_failed"]
        result["error_type"] = type(exc).__name__
        return result
    clearance = geometry.get("signed_clearance_m")
    penetrating = geometry.get("is_penetrating")
    if (geometry.get("measurement_valid") is not True
            or not _finite_measurement(clearance) or type(penetrating) is not bool):
        result["reason_codes"] = ["geometry_measurement_invalid"]
        result["measurements"]["measurement_method"] = geometry.get("measurement_method")
        return result
    clearance = float(clearance)
    result["measurement_valid"] = True
    result["measurements"].update(
        signed_clearance_m=clearance, is_penetrating=penetrating,
        measurement_method=geometry.get("measurement_method"),
        collision_tolerance_m=geometry.get("collision_tolerance_m"))
    result["checks"]["pair_nonpenetrating"] = {"passed": not penetrating}
    if penetrating:
        result["reason_codes"].append("pair_penetrating")
    if "target_clearance_m" in normalized_goal:
        error = abs(clearance - normalized_goal["target_clearance_m"])
        passed = error <= normalized_goal["clearance_tolerance_m"]
        result["checks"]["clearance"] = {"passed": passed, "absolute_error_m": error,
            "tolerance_m": normalized_goal["clearance_tolerance_m"]}
        if not passed:
            result["reason_codes"].append("target_clearance_not_met")
    if "target_focal_pivot_world_m" in normalized_goal:
        original = next(mesh for mesh in scene["meshes"]
                        if mesh["object_id"] == focal.object_id)
        pivot = original.get("pivot_world")
        if pivot is None:
            result["checks"]["position"] = {"passed": False, "absolute_error_m": None,
                "tolerance_m": normalized_goal["position_tolerance_m"]}
            result["reason_codes"].append("focal_pivot_unavailable")
            result["measurement_valid"] = False
        else:
            error = math.dist(pivot, normalized_goal["target_focal_pivot_world_m"])
            finite = math.isfinite(error)
            passed = finite and error <= normalized_goal["position_tolerance_m"]
            result["measurements"]["focal_pivot_world_m"] = list(pivot)
            result["checks"]["position"] = {"passed": bool(passed), "absolute_error_m": error if finite else None,
                "tolerance_m": normalized_goal["position_tolerance_m"]}
            if not finite:
                result["measurement_valid"] = False
                result["reason_codes"].append("position_residual_nonfinite")
            if not passed:
                result["reason_codes"].append("target_position_not_met")
    angular = [("max_contact_normal_angle_deg", "contact_normal_angle_deg", "contact_normal"),
               ("max_tangent_yaw_mismatch_deg", "tangent_yaw_mismatch_deg", "tangent_yaw")]
    requested = [(target, metric, name) for target, metric, name in angular if target in normalized_goal]
    if requested:
        try:
            probe = SpatialAnomalySniffer.probe_closest_clearance(focal, reference,
                yaw_symmetry_order=normalized_goal["yaw_symmetry_order"])
            result["axes_valid"] = bool(probe.axes_valid)
            angles_valid = (bool(probe.measurement_valid) and bool(probe.axes_valid)
                            and all(_finite_measurement(getattr(probe, metric, None))
                                    for _, metric, _ in requested))
            angles = _unrounded_contact_angles(focal, reference, probe,
                normalized_goal["yaw_symmetry_order"]) if angles_valid else {}
        except Exception as exc:
            probe = None
            angles_valid = False
            result["axes_valid"] = False
            result["error_type"] = type(exc).__name__
        if not angles_valid:
            result["reason_codes"].append("angular_measurement_invalid")
            result["measurement_valid"] = False
        for target, metric, name in requested:
            actual = angles[metric] if angles_valid else None
            passed = bool(angles_valid and abs(actual) <= normalized_goal[target])
            result["measurements"][metric] = actual
            result["checks"][name] = {"passed": passed, "maximum_deg": normalized_goal[target]}
            if angles_valid and not passed:
                result["reason_codes"].append("target_" + name + "_not_met")
    result["task_succeeded"] = all(check["passed"] for check in result["checks"].values())
    result["status"] = ("measurement_unavailable" if not result["measurement_valid"]
                        else "goal_satisfied" if result["task_succeeded"] else "goal_not_satisfied")
    return result


__all__ = ["evaluate_spatial_goal"]
