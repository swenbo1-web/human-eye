"""Independent box/plane geometry for the paired subagent experiment.

The scoring math does not call the plugin's clearance probe or pass/fail flag.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


LIMITS = {
    "bottom_face_rms_m": 0.0005,
    "rotation_deg": 1.0,
    "tangential_drift_m": 0.005,
    "penetration_tolerance_m": 0.0001,
    "region_tolerance_m": 0.0005,
}

SIGNS = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                  [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=float)
FACES = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                  [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]], dtype=np.int32)
EDGES = np.array([[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6],
                  [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]], dtype=np.int32)


def euler_matrix(euler_deg):
    """World fixed-axis XYZ: Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    x, y, z = [math.radians(float(v)) for v in euler_deg]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return np.array([[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
                     [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx],
                     [-sy, cy*sx, cy*cx]], dtype=float)


def vertices(primitive):
    local = SIGNS * np.asarray(primitive["size"], dtype=float) / 2
    return local @ np.asarray(primitive["rotation"], dtype=float).T + np.asarray(primitive["center"], dtype=float)


def build_meshes(case):
    """Only the render/actuation adapter imports the product's mesh class."""
    from human_eye_foveated_renderer import MeshEntity3D
    primitives = [case["reference"], case["focal"], *case.get("occluders", [])]
    meshes = []
    for i, box in enumerate(primitives):
        mark = "#" + chr(ord("A") + i)
        color = (70, 130, 190) if i == 0 else ((225, 115, 65) if i == 1 else (85, 180, 120))
        meshes.append(MeshEntity3D(
            f"part_{i}", mark, f"Part_{chr(ord('A') + i)}", vertices(box),
            FACES.copy(), EDGES.copy(), color, i == 1,
            local_axes=np.asarray(box["rotation"], dtype=float).T.copy(),
            pivot_world=np.asarray(box["center"], dtype=float).copy(),
        ))
    return meshes


def validate_action(value: Any, trial_id: str):
    if not isinstance(value, dict):
        raise ValueError("Response must be a JSON object")
    if value.get("trial_id") != trial_id:
        raise ValueError("Missing or mismatched trial_id")
    if value.get("focal_mark") != "#B" or value.get("reference_mark") != "#A":
        raise ValueError("Wrong or missing part marks")
    for key in ("rotation_euler_deg_xyz", "translation_xyz_m"):
        data = value.get(key)
        if not isinstance(data, list) or len(data) != 3:
            raise ValueError(f"{key} must contain exactly three numbers")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in data):
            raise ValueError(f"{key} contains invalid/non-finite numbers")
    if max(abs(x) for x in value["rotation_euler_deg_xyz"]) > 360:
        raise ValueError("Rotation outside the registered +/-360 degree action bounds")
    if float(np.linalg.norm(value["translation_xyz_m"])) > 5:
        raise ValueError("Translation exceeds the registered 5m action bound")
    return value


def obb_intersection(a, b, tolerance=LIMITS["penetration_tolerance_m"]):
    """15-axis separating-axis test; contact within tolerance is not penetration."""
    ra, rb = np.asarray(a["rotation"]), np.asarray(b["rotation"])
    ha, hb = np.asarray(a["size"])/2, np.asarray(b["size"])/2
    separation = np.asarray(b["center"]) - np.asarray(a["center"])
    axes = [ra[:, i] for i in range(3)] + [rb[:, i] for i in range(3)]
    axes += [np.cross(ra[:, i], rb[:, j]) for i in range(3) for j in range(3)]
    overlaps = []
    for axis in axes:
        length = float(np.linalg.norm(axis))
        if length < 1e-10:
            continue
        axis = axis / length
        radius_a = float(np.sum(ha * np.abs(axis @ ra)))
        radius_b = float(np.sum(hb * np.abs(axis @ rb)))
        overlap = radius_a + radius_b - abs(float(axis @ separation))
        if overlap < -tolerance:
            return False, 0.0
        overlaps.append(overlap)
    depth = max(0.0, min(overlaps))
    return bool(depth > tolerance), depth


def angle_between_rotations(a, b):
    cosine = float((np.trace(np.asarray(a).T @ np.asarray(b))-1)/2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def score_pose(case, rotation, center):
    """Score the prescribed local bottom face and target region, not any close face."""
    pose = {"center": np.asarray(center), "rotation": np.asarray(rotation), "size": case["focal"]["size"]}
    corners = vertices(pose)
    bottom = corners[:4]
    target = case["target"]
    normal = np.asarray(target["normal"])
    point = np.asarray(target["plane_point"])
    distances = (bottom-point) @ normal
    rms = float(np.sqrt(np.mean(distances**2)))
    target_rotation = np.asarray(target["rotation"])
    # The moving rectangle has no directed key: a 180deg in-plane turn is equivalent.
    symmetry_180 = np.diag([-1.0, -1.0, 1.0])
    angular_error = min(angle_between_rotations(target_rotation, rotation),
                        angle_between_rotations(target_rotation @ symmetry_180, rotation))
    center_delta = np.asarray(center)-np.asarray(target["center"])
    tangent_delta = center_delta-normal*float(center_delta @ normal)
    tangent_error = float(np.linalg.norm(tangent_delta))
    reference = case["reference"]
    ref_local = (bottom-np.asarray(reference["center"])) @ np.asarray(reference["rotation"])
    in_region = bool(np.all(np.abs(ref_local[:, :2]) <= np.asarray(reference["size"][:2])/2 + LIMITS["region_tolerance_m"]))
    collisions = []
    for i, other in enumerate([reference, *case.get("occluders", [])]):
        penetrating, depth = obb_intersection(pose, other)
        if penetrating:
            collisions.append({"object": "#A" if i == 0 else "#"+chr(ord('C')+i-1),
                               "depth_mm": round(depth*1000, 6)})
    passed = (rms <= LIMITS["bottom_face_rms_m"] and angular_error <= LIMITS["rotation_deg"]
              and tangent_error <= LIMITS["tangential_drift_m"] and in_region and not collisions)
    return {"success": bool(passed), "bottom_face_rms_mm": rms*1000,
            "signed_bottom_distances_mm": (distances*1000).tolist(),
            "rotation_error_deg": angular_error, "tangential_drift_mm": tangent_error*1000,
            "in_target_region": in_region, "penetrating": bool(collisions), "collisions": collisions,
            "position_error_mm": float(np.linalg.norm(center_delta))*1000}


def apply_raw_action(case, action):
    rotation = euler_matrix(action["rotation_euler_deg_xyz"]) @ np.asarray(case["focal"]["rotation"])
    center = np.asarray(case["focal"]["center"]) + np.asarray(action["translation_xyz_m"])
    return rotation, center


def self_check():
    case = {"reference": {"center": [0, 0, 0.175], "rotation": np.eye(3).tolist(), "size": [1.4, 1.2, .35]},
            "focal": {"center": [0, 0, .44], "rotation": np.eye(3).tolist(), "size": [.28, .20, .14]},
            "target": {"plane_point": [0, 0, .35], "normal": [0, 0, 1], "rotation": np.eye(3).tolist(), "center": [0, 0, .42]},
            "occluders": []}
    assert score_pose(case, np.eye(3), [0, 0, .42])["success"]
    assert not score_pose(case, np.eye(3), [0, 0, .44])["success"]
    assert score_pose(case, np.eye(3), [0, 0, .416])["penetrating"]
    assert score_pose(case, np.diag([-1., -1., 1.]), [0, 0, .42])["success"]
    assert not score_pose(case, np.diag([1., -1., -1.]), [0, 0, .42])["success"]
    assert not score_pose(case, np.eye(3), [.03, 0, .42])["success"]


if __name__ == "__main__":
    self_check()
    print("Independent geometry checks passed")
