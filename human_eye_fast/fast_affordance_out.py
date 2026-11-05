"""Pack selected RB, BC, TD and VG facts into one versioned JSON observation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from .control import Translate

if TYPE_CHECKING:
    from numpy import ndarray

    from .control import Outcome
    from .fast_bvh_clearance import SurfaceDistance
    from .raycast_saccade_gpu import Observation as VGObservation


@dataclass(frozen=True, slots=True)
class ObjectFact:
    object_id: str
    topology_generation: int
    center_m: tuple[float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class ClearanceFact:
    target_ids: tuple[str, str]
    surface: SurfaceDistance


@dataclass(frozen=True, slots=True)
class DeformationFact:
    object_id: str
    reference_frame: int
    sample_frames: Sequence[int]
    metrics: dict[str, ndarray]
    triangles: ndarray
    position_frame: int
    position_vertices_m: ndarray
    selected_face_ids: Sequence[int] = ()


@dataclass(frozen=True, slots=True)
class ImageFact:
    path: str
    rendered: VGObservation


@dataclass(frozen=True, slots=True)
class ObservationFact:
    observation_id: str
    frame_id: int
    objects: Sequence[ObjectFact]
    clearance: ClearanceFact | None = None
    deformation: DeformationFact | None = None
    image: ImageFact | None = None


@dataclass(frozen=True, slots=True)
class AffordancePackage:
    observations: Sequence[ObservationFact]
    outcome: Outcome | None = None


_CANDIDATE = "he-ao/1"
_BASELINE = "he-ao-json/1"
_PACKAGE = ("version", "length_unit", "object_ids", "observations", "outcome")
_OBSERVATION = ("observation_id", "frame_id", "objects", "clearance", "deformation", "image")
_OBJECT = ("object_index", "topology_generation", "center_m")
_CLEARANCE = ("status", "target_object_indices", "distance_m", "witness_a", "witness_b")
_WITNESS = ("original_face_id", "point_m")
_DEFORMATION = ("object_index", "reference_frame", "sample_frames", "reduced_face_count",
                "top_face_ids", "position_kind", "position_frame", "faces")
_METRICS = ("max_principal_stretch", "min_principal_stretch", "max_area_strain",
            "max_normal_angle_deg", "max_centroid_displacement", "score")
_FACE = ("original_face_id", *_METRICS, "position_m")
_IMAGE = ("path", "width_px", "height_px", "meters_per_blender_unit", "mode",
          "target_object_indices", "mesh_object_indices", "section", "global_view", "local_view")
_SECTION = ("point_m", "normal", "kept_side")
_VIEW = ("viewport", "camera_type", "matrix_world_blender", "ortho_scale_blender",
         "clip_start_blender", "clip_end_blender", "shift_x", "shift_y", "projection_blender",
         "gpu_view_m", "gpu_projection_m", "gpu_view_projection_m")
_OUTCOME = ("action_id", "before_observation_id", "after_observation_id", "goal", "command",
            "control_before", "control_after", "distance_before_m", "distance_after_m",
            "measured_delta_m", "predicted_delta_m", "goal_reached")
_GOAL = ("moving_object_index", "reference_object_index", "target_distance_m", "tolerance_m")
_COMMAND = ("kind", "delta_world_m", "key_name", "target_value")


def public_schema():
    """Return standalone decoding information to publish once per version."""
    return {
        "versions": {"candidate": _CANDIDATE, "baseline": _BASELINE},
        "columns": {
            "package": _PACKAGE, "observation": _OBSERVATION, "object": _OBJECT,
            "clearance": _CLEARANCE, "witness": _WITNESS, "deformation": _DEFORMATION,
            "face": _FACE, "image": _IMAGE, "section": _SECTION, "view": _VIEW,
            "outcome": _OUTCOME, "goal": _GOAL, "command": _COMMAND,
        },
        "semantics": {
            "records": "Candidate records are arrays in column order. Baseline records are objects with those keys.",
            "length_unit": "m. Physical positions, displacements and distances are in world meters.",
            "object_index": "Zero-based index into the package object_ids table. IDs are stable across observations.",
            "original_face_id": "Zero-based input triangle row within its object, frame and topology generation.",
            "clearance": "Unsigned minimum surface distance. positive_gap is positive; zero_distance does not classify contact or intersection. empty_surface has null distance and witnesses. The two witnesses follow the order of target_object_indices.",
            "deformation": "Reference frame and complete sampling frames are distinct from selected faces. faces lists Top-K first then additional requested faces. Each position is the world centroid at position_frame. Null TD metrics are undefined. Area strain is max(abs(area_ratio - 1)); angle is oriented world-normal change in degrees.",
            "image": "PNG path relative to the package. Image inherits its observation ID and frame. Global and local occupy the left and right panels respectively. Camera matrices are row-major. The gpu_view_projection_m matrix projects world-meter points to homogeneous clip coordinates.",
            "section": "NATURAL is unclipped by a section plane; SECTION retains the negative half-space including the plane in the local panel only.",
            "outcome": "Bound to its before and after observations. Measured delta is after distance minus before distance. Command kind is translate or set_shape_key. Actual control is the evaluated world translation in meters or evaluated shape key value respectively. Prediction is separate.",
            "null": "Absent optional record, empty surface distance/witness, undefined TD metric or unavailable measured delta, depending on the field.",
        },
    }


def _finite_or_none(value):
    value = float(value)
    return value if isfinite(value) else None


def _clearance(row, fact, object_indices):
    a, b = fact.target_ids
    targets = (object_indices[a], object_indices[b])
    surface = fact.surface
    if surface.triangle_a is None:
        return row(_CLEARANCE, "empty_surface", targets, None, None, None)
    distance = surface.distance_m
    return row(_CLEARANCE, "positive_gap" if distance > 0 else "zero_distance", targets, distance,
               row(_WITNESS, surface.triangle_a, surface.point_a),
               row(_WITNESS, surface.triangle_b, surface.point_b))


def _deformation(row, fact, object_indices):
    top = fact.metrics["witness_triangle_ids"].tolist()
    face_ids = tuple(dict.fromkeys((*top, *map(int, fact.selected_face_ids))))
    rows = []
    if len(face_ids) == 1:
        face_id = face_ids[0]
        triangle = fact.position_vertices_m[fact.triangles[face_id]]
        origin = triangle[0]
        center = (origin + ((triangle[1] - origin) / 3 + (triangle[2] - origin) / 3)).tolist()
        rows = [row(_FACE, face_id,
                    *(_finite_or_none(fact.metrics[name][face_id]) for name in _METRICS), center)]
    elif face_ids:
        indices = list(face_ids)
        columns = [fact.metrics[name][indices].tolist() for name in _METRICS]
        positions = fact.position_vertices_m[fact.triangles[indices]]
        origin = positions[:, 0]
        centers = origin + ((positions[:, 1] - origin) / 3 + (positions[:, 2] - origin) / 3)
        rows = [
            row(_FACE, face_id, *map(_finite_or_none, metrics), center)
            for face_id, metrics, center in zip(face_ids, zip(*columns), centers.tolist())
        ]
    return row(_DEFORMATION, object_indices[fact.object_id], fact.reference_frame,
               tuple(fact.sample_frames), len(fact.triangles), top, "face_centroid",
               fact.position_frame, rows)


def _view(row, view):
    rna, gpu = view["rna"], view["gpu"]
    return row(_VIEW, view["viewport"], rna["type"], rna["matrix_world"], rna["ortho_scale"],
               rna["clip_start"], rna["clip_end"], rna["shift_x"], rna["shift_y"], rna["projection"],
               gpu["view"], gpu["projection"], gpu["view_projection"])


def _image(row, fact, object_indices):
    metadata = fact.rendered.metadata
    section = metadata["section"]
    views = metadata["views"]
    return row(_IMAGE, fact.path, 1024, 512, metadata["meters_per_blender_unit"], metadata["mode"],
               [object_indices[key] for key in metadata["target_ids"]],
               [object_indices[key] for key in metadata["mesh_ids"]],
               row(_SECTION, section["point_m"], section["normal"], section["kept_side"]) if section else None,
               _view(row, views["global"]), _view(row, views["local"]))


def _outcome(row, outcome, object_indices):
    goal, action = outcome.goal, outcome.action
    command = action.command
    if isinstance(command, Translate):
        command_row = row(_COMMAND, "translate", command.delta_world_m, None, None)
    else:
        command_row = row(_COMMAND, "set_shape_key", None, command.key_name, command.value)
    return row(_OUTCOME, action.action_id, outcome.before.observation_id, outcome.after.observation_id,
               row(_GOAL, object_indices[goal.moving_id], object_indices[goal.reference_id],
                   goal.distance_m, goal.tolerance_m),
               command_row, outcome.control_before, outcome.control_after,
               _finite_or_none(outcome.before.surface.distance_m),
               _finite_or_none(outcome.after.surface.distance_m),
               outcome.measured_delta_m, action.predicted_delta_m, outcome.goal_reached)


def _project(package, row, version):
    object_indices = {}
    for observation in package.observations:
        for obj in observation.objects:
            object_indices.setdefault(obj.object_id, len(object_indices))
    observations = [
        row(_OBSERVATION, obs.observation_id, obs.frame_id,
            [row(_OBJECT, object_indices[obj.object_id], obj.topology_generation, obj.center_m)
             for obj in obs.objects],
            _clearance(row, obs.clearance, object_indices) if obs.clearance is not None else None,
            _deformation(row, obs.deformation, object_indices) if obs.deformation is not None else None,
            _image(row, obs.image, object_indices) if obs.image is not None else None)
        for obs in package.observations
    ]
    outcome = _outcome(row, package.outcome, object_indices) if package.outcome is not None else None
    return row(_PACKAGE, version, "m", list(object_indices), observations, outcome)


def _row(_columns, *values):
    return values


# Facts form a trusted, acyclic tree. Reuse encoding configuration, never
# projected rows or final text. Every call performs a fresh C JSON traversal.
_ENCODER = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                            check_circular=False, separators=(",", ":"))


def _json_bytes(document):
    return _ENCODER.encode(document).encode("utf-8")


def encode(package: AffordancePackage) -> bytes:
    """Encode the selected facts once, detaching the result from borrowed buffers."""
    return _json_bytes(_project(package, _row, _CANDIDATE))
