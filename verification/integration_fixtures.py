"""Predeclared same-scene integration cases and independent analytic expectations.

Mesh coordinates and affine translations are in meters. Every affine matrix is
relative to its named parent, with identity matrix_parent_inverse. The linear
part is dimensionless. This module does not import Blender or any engine code.
"""

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import cos, pi, sin
from pathlib import Path

import numpy as np


FAMILIES = ("open-tip", "single-panel", "staggered-wings", "slotted-drum",
            "nested-drums", "carried-screen")
PROBE_INDICES = (0, 1, 20)
TARGET_IDS = ("moving", "reference")
COLORS = ((.82, .24, .15, 1.), (.16, .60, .90, 1.), (.36, .40, .45, 1.))
COMMANDS = ("translate", "set_shape_key", "translate", "set_shape_key")
MODES = ("NATURAL", "SECTION", "SECTION", "NATURAL")
LENGTHS_M = (.012, .035, .080, .150)
GAP_RATIOS = (.004, .009, .015, .025)
METERS_PER_UNIT = (1., .001, .001, 1.)
CONTROL_CASES = (
    ("contact-zero", 0),
    ("empty-reference", 0),
    ("already-reached", 0),
    ("reference-follows", 0),
    ("nonbasis-key", 1),
    ("unit-recode", 1),
    ("topology-renumber", 0),
)
DEPLOYMENT_SNAPSHOTS = (
    ("20261105", "076112b8a7bc6f5b2c267e61a0dc683873e43fb5a68bbd9b1342a2d15a5a3698"),
    ("79463", "d585ac84b6167de560d05b11c5d612925b68af1319b2d35303e0237fb80c663e"),
    ("310519", "9a2df9a97d33ed9c0ddf87f0dedabf0aa8c878c0bfdbc8dc96eba7c1c4e7162b"),
)
_OBSERVE_TARGETS = ("VERTICES", "TRANSFORM", "UNITS")
_AFTER_TARGETS = ("VERTICES", "TRANSFORM")


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    partition: str
    ordinal: int
    family: str
    variant: int
    scale_m: float
    gap_m: float
    scale_length: float
    mode: str
    command_kind: str | None
    frame_id: int = 17


@dataclass(frozen=True, slots=True)
class ParentSpec:
    object_id: str
    local_matrix_m: np.ndarray
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class MeshSpec:
    object_id: str
    vertices_local_m: np.ndarray
    triangles: np.ndarray
    color: tuple[float, float, float, float]
    local_matrix_m: np.ndarray
    parent_id: str | None = None
    shape_basis_local_m: np.ndarray | None = None
    shape_relative_local_m: np.ndarray | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    kind: str
    delta_world_m: tuple[float, float, float] | None = None
    key_name: str | None = None
    control_before: float | None = None
    target_value: float | None = None


@dataclass(frozen=True, slots=True)
class IntegrationFixture:
    spec: CaseSpec
    meshes: tuple[MeshSpec, ...]
    parents: tuple[ParentSpec, ...]
    target_ids: tuple[str, str]
    command: CommandSpec | None
    followup_command: CommandSpec | None
    goal_distance_m: float
    goal_tolerance_m: float
    expected_before_m: float | None
    expected_after_m: float | None
    expected_followup_gap_m: float | None
    action_supported_for_prediction: bool
    expected_obstacle_delta_m: dict[str, tuple[float, float, float]]
    replacement_triangles: dict[str, np.ndarray] | None = None

    @property
    def mode(self):
        return self.spec.mode

    @property
    def scale_length(self):
        return self.spec.scale_length

    @property
    def host_tolerance_m(self):
        return float(64 * np.finfo(np.float32).eps * self.spec.scale_m)


def fixture_manifest(*, partition="main"):
    """List cases in timing order, or list the separate untimed controls."""
    if partition == "main":
        return tuple(
            CaseSpec(f"I-{family}-{variant}", "main", 4 * i + variant, family, variant,
                     length, length * GAP_RATIOS[variant], METERS_PER_UNIT[variant],
                     MODES[variant], COMMANDS[variant])
            for i, family in enumerate(FAMILIES)
            for variant, length in enumerate(LENGTHS_M)
        )
    if partition != "control":
        raise ValueError(f"Unknown fixture partition {partition!r}")
    return tuple(
        CaseSpec(case_id, "control", i, FAMILIES[0], variant, LENGTHS_M[variant],
                 0. if case_id == "contact-zero" else LENGTHS_M[variant] * GAP_RATIOS[variant],
                 1. if case_id == "unit-recode" else METERS_PER_UNIT[variant],
                 MODES[variant], None if case_id == "empty-reference" else COMMANDS[variant])
        for i, (case_id, variant) in enumerate(CONTROL_CASES)
    )


def _rx(theta):
    c, s = cos(theta), sin(theta)
    return np.array(((1., 0., 0.), (0., c, -s), (0., s, c)))


def _ry(theta):
    c, s = cos(theta), sin(theta)
    return np.array(((c, 0., s), (0., 1., 0.), (-s, 0., c)))


def _rz(theta):
    c, s = cos(theta), sin(theta)
    return np.array(((c, -s, 0.), (s, c, 0.), (0., 0., 1.)))


def _affine(rotation, stretch, offset):
    transform = np.eye(4)
    transform[:3, :3] = rotation * np.asarray(stretch)
    transform[:3, 3] = offset
    return transform


def _quad_strip(a, b):
    return [(a[i], a[(i + 1) % len(a)], b[(i + 1) % len(a)], b[i])
            for i in range(len(a))]


def _triangulate(quads):
    return [(a, b, c) for a, b, c, _ in quads] + [(a, c, d) for a, _, c, d in quads]


def _tip(length, gap, side):
    """Closed radial cone with one axial extreme at side * gap/2."""
    ring_size = 12
    angles = 2 * pi * np.arange(ring_size) / ring_size
    points = [(side * gap / 2, 0., 0.)]
    # Contact uses the same bodies with a small nonzero axial ring scale.
    taper_gap = gap or .004 * length
    for depth, radius in ((.14 * taper_gap, .42 * taper_gap),
                          (.32 * taper_gap, .78 * taper_gap), (.18 * length, .14 * length)):
        points.extend((side * (gap / 2 + depth), radius * cos(theta), radius * sin(theta))
                      for theta in angles)
    rings = [list(range(1 + j * ring_size, 1 + (j + 1) * ring_size)) for j in range(3)]
    first, second, back = rings
    triangles = [(0, first[(i + 1) % ring_size], first[i]) for i in range(ring_size)]
    triangles += _triangulate(_quad_strip(first, second) + _quad_strip(second, back))
    triangles += [(back[0], back[i], back[i + 1]) for i in range(1, ring_size - 1)]
    if side < 0:
        triangles = [(a, c, b) for a, b, c in triangles]
    return np.asarray(points), np.asarray(triangles, dtype=np.int32)


def _panel(length, phi, radius, half_width, shift=0.):
    """A rectangular radial screen, with optional axial/tangent shear."""
    rings = []
    for x in (-.23, .23):
        for dr, dt in ((-.013, -half_width), (.013, -half_width),
                       (.013, half_width), (-.013, half_width)):
            tangent = dt + shift * x
            radial = radius + dr
            rings.append((x, radial * cos(phi) - tangent * sin(phi),
                          radial * sin(phi) + tangent * cos(phi)))
    quads = _quad_strip(tuple(range(4)), tuple(range(4, 8)))
    quads.extend(((3, 2, 1, 0), (4, 5, 6, 7)))
    return length * np.asarray(rings), np.asarray(_triangulate(quads), dtype=np.int32)


def _drum(length, phi, radius, segments, window, wave=0.):
    """One slotted cylindrical wrap, closed by walls and both slit caps."""
    rings = []
    theta = phi + np.linspace(window / 2, 2 * pi - window / 2, segments + 1)
    for angle in theta:
        radial = radius * (1 + wave * cos(3 * angle))
        rings.extend((x, (radial + dr) * cos(angle), (radial + dr) * sin(angle))
                     for x, dr in ((-.18, 0.), (-.18, .022), (.18, .022), (.18, 0.)))
    quads = []
    for i in range(segments):
        quads += _quad_strip(tuple(range(4 * i, 4 * i + 4)),
                             tuple(range(4 * (i + 1), 4 * (i + 1) + 4)))
    last = 4 * segments
    quads.extend(((3, 2, 1, 0), (last, last + 1, last + 2, last + 3)))
    return length * np.asarray(rings), np.asarray(_triangulate(quads), dtype=np.int32)


def _screens(spec):
    family = FAMILIES.index(spec.family)
    length = spec.scale_m
    phi = .19 + .55 * family + .43 * spec.variant
    if family == 0:
        return ()
    if family == 1:
        return (("panel", _panel(length, phi, .27, .13), None),)
    if family == 2:
        return (("first-wing", _panel(length, phi, .28, .10, .24), None),
                ("second-wing", _panel(length, phi + 1.8, .32, .14, -.16), None))
    if family == 3:
        return (("drum", _drum(length, phi, .28, 18, 1.31, .05), None),)
    if family == 4:
        return (("inner-drum", _drum(length, phi, .25, 12, 1.34), None),
                ("outer-drum", _drum(length, phi + .21, .37, 23, 1.37, .08), None))
    return (("moving-screen", _panel(length, phi, .26, .11, .28), TARGET_IDS[0]),
            ("fixed-screen", _panel(length, phi + 2.1, .31, .16, -.12), None))


def _local_points(world, matrix):
    return (world - matrix[:3, 3]) @ np.linalg.inv(matrix[:3, :3]).T


def _vector(values):
    return tuple(map(float, values))


def build_fixture(spec):
    """Build one immutable spec's independent reference geometry and action."""
    length, gap = spec.scale_m, spec.gap_m
    variant = spec.variant
    shape = spec.command_kind == "set_shape_key"
    parent_id = "rig-parent" if shape else None
    parent_matrix = (_affine(_rz(-.34) @ _ry(.30), (1.4, .72, 1.18),
                             length * np.array((-.13, .18, .03))) if shape else np.eye(4))
    moving_local = _affine(_rz(.37) @ _rx(.27), (.87, 1.21, .92),
                           length * np.array((.04, -.03, .02)))
    moving_world = parent_matrix @ moving_local
    follows = spec.case_id == "reference-follows"
    # Empty/zero controls and open family retain deterministic clear semantics.
    family = FAMILIES.index(spec.family)
    scene_rotation = _rz(.31 * family + .53 * variant) @ _ry(.13 * variant)
    scene_offset = length * np.array((.23, -.17, .11))
    if spec.case_id == "contact-zero":
        # Place the common tip at exact local/world zero on both objects.
        moving_local = moving_world = np.eye(4)
        scene_offset = np.zeros(3)
    axis = scene_rotation[:, 0]

    command = followup = None
    after = followup_gap = None
    basis = relative = None
    positive_task = spec.case_id not in ("empty-reference", "contact-zero", "already-reached")
    if shape:
        q, target = ((.25, .625) if variant == 1 else (.625, .25))
        command = CommandSpec("set_shape_key", key_name="Actuate", control_before=q, target_value=target)
        travel = .40 * gap
        after = gap - travel * (target - q)
        followup = CommandSpec("set_shape_key", key_name="Actuate", control_before=target, target_value=q)
        followup_gap = gap
    elif spec.command_kind == "translate":
        signed = .20 * (gap or .004 * length) * (1. if variant == 0 else -1.)
        delta = signed * axis
        command = CommandSpec("translate", _vector(delta))
        if positive_task:
            after = gap if follows else gap - signed
            followup = CommandSpec("translate", _vector(-delta))
            followup_gap = gap

    points, faces = _tip(length, gap, -1)
    moving_current = _local_points(points @ scene_rotation.T + scene_offset, moving_world)
    moving_rest = moving_current
    if shape:
        weights = np.repeat((1., .65, .35, 0.), (1, 12, 12, 12))
        basis_world = weights[:, None] * travel * axis
        basis = basis_world @ np.linalg.inv(moving_world[:3, :3]).T
        moving_rest = moving_current - q * basis
        if spec.case_id == "nonbasis-key":
            relative = moving_rest + length * np.array((.021, -.017, .033))
    moving = MeshSpec(TARGET_IDS[0], moving_rest, faces, COLORS[0], moving_local,
                      parent_id, basis, relative)

    if spec.case_id == "empty-reference":
        points = np.empty((0, 3))
        faces = np.empty((0, 3), dtype=np.int32)
    else:
        points, faces = _tip(length, gap, 1)
    reference_local = np.eye(4)
    reference_world = moving_world if follows else reference_local
    reference = MeshSpec(TARGET_IDS[1], _local_points(points @ scene_rotation.T + scene_offset,
                                                    reference_world), faces, COLORS[1],
                         reference_local, TARGET_IDS[0] if follows else None)

    meshes = [moving, reference]
    obstacle_delta = {}
    for object_id, (points, faces), parent in _screens(spec):
        world = points @ scene_rotation.T + scene_offset
        vertices = _local_points(world, moving_world) if parent else world
        meshes.append(MeshSpec(object_id, vertices, faces, COLORS[2], np.eye(4), parent))
        if parent and command is not None and command.kind == "translate":
            obstacle_delta[object_id] = command.delta_world_m

    parents = (ParentSpec(parent_id, parent_matrix),) if shape else ()
    goal = gap if spec.case_id == "already-reached" else 0.
    expected_before = None if spec.case_id == "empty-reference" else gap
    replacement = {TARGET_IDS[0]: moving.triangles[::-1].copy()} if spec.case_id == "topology-renumber" else None
    return IntegrationFixture(spec, tuple(meshes), parents, TARGET_IDS, command, followup,
                              goal, float(64 * np.finfo(np.float32).eps * length), expected_before, after,
                              followup_gap, positive_task and not follows, obstacle_delta, replacement)


def deployment_inputs():
    """Identify existing sealed sources, before the separate v1 deployment export."""
    return [
        {"process_index": index, "seed": seed,
         "sealed_path": f"artifacts/cf/formal_001/{seed}/seal/frozen.npz",
         "sealed_sha256": digest,
         "deployment_v1": "pending_export_and_per_field_equivalence_before_formal_run"}
        for index, (seed, digest) in enumerate(DEPLOYMENT_SNAPSHOTS)
    ]


def _observation(fixture, observation_id, mode, masks, generations):
    return {
        "observation_id": observation_id,
        "frame_id": fixture.spec.frame_id,
        "mode": mode,
        "changes": masks,
        "topology_generations": generations,
        "attachment_key_if_applicable": None if mode is None else f"{observation_id}.png",
        "td_top_k": 12,
        "selected_face_ids": [],
    }


def _formal_plan(spec):
    fixture = build_fixture(spec)
    target_ids = fixture.target_ids
    meshes = tuple(mesh.object_id for mesh in fixture.meshes)
    context_ids = tuple(key for key in meshes if key not in target_ids)
    generations = {key: index + 1 for index, key in enumerate(meshes)}
    reset_context = fixture.expected_obstacle_delta_m

    def masks(target, moved=()):
        return {**dict.fromkeys(target_ids, target),
                **{key: ("TRANSFORM",) if key in moved else () for key in context_ids}}

    reference = _observation(fixture, "reference", None, masks(_OBSERVE_TARGETS), generations)
    before = _observation(fixture, "before", fixture.mode,
                          masks(_OBSERVE_TARGETS, reset_context), generations)
    after = _observation(fixture, "after", fixture.mode,
                         masks(_AFTER_TARGETS, reset_context), generations)
    next_observation = _observation(fixture, "next", fixture.mode,
                                    masks(_OBSERVE_TARGETS), generations)
    is_shape = fixture.command is not None and fixture.command.kind == "set_shape_key"
    return {
        "case_id": spec.case_id,
        "target_ids": target_ids,
        "context_ids_in_order": context_ids,
        "meters_per_blender_unit_requested": spec.scale_length,
        "goal": {"distance_m": fixture.goal_distance_m, "tolerance_m": fixture.goal_tolerance_m},
        "reference_capture": {
            **reference,
            "object_id": target_ids[0],
            "reference_frame_id": spec.frame_id,
            "coordinate_space": "evaluated_world_m_owned_snapshot",
            "state": "fixture_initial_channels",
            "view_arm": "F",
            "first_capture_reads_all_mesh_attributes_even_for_NONE": True,
        },
        "before": before,
        "first_command": None if fixture.command is None else {
            "action_id": "act", "before_observation_id": "before",
            "command": asdict(fixture.command),
        },
        "after_readback_and_publication": after,
        "next": next_observation,
        "next_command_prediction_only": None if fixture.followup_command is None else {
            "action_id": "next-act", "before_observation_id": "next",
            "command": asdict(fixture.followup_command),
        },
        "arms": {"fixed": {"view": "F", "predictor": "G"},
                 "retrieval": {"view": "R", "predictor": "G"},
                 "deployment": {"view": "L", "predictor": "L" if is_shape else "G"}},
        "feedback": {
            "view_observations_in_order": ["before", "after"],
            "view_attachment_keys": ["before.png", "after.png"],
            "action": "actual_finite_Outcome_only_if_learned_action_ticket",
            "no_feedback_for_next": True,
            "recording": "independently_score_actual_png_before_timing; seal_report_hash_before_replay",
            "required_view_fields": [
                "observation_id", "attachment_key", "canonical_index", "selected_direction",
                "selected_probe_rays", "native_stop", "png_sha256", "strict_verdict",
            ],
        },
    }


def _planned_controls():
    """Keep bounded current probes and later controls distinct from the formal main set."""
    return [
        {"id": "contact-zero", "scope": "prior_native_001_and_fixed_replay", "expected": "NATURAL no ray; no action at goal"},
        {"id": "empty-reference", "scope": "prior_native_001_and_fixed_replay", "expected": "empty_surface; no image; no action"},
        {"id": "already-reached", "scope": "prior_native_001_and_fixed_replay", "expected": "goal_reached; no write"},
        {"id": "nonbasis-key", "scope": "prior_native_001_and_fixed_replay", "expected": "actual non-Basis relative-key readback"},
        {"id": "reference-follows", "scope": "formal_pending", "expected": "actual explicit NONE; both targets follow; finite delta"},
        {"id": "unit-recode", "scope": "formal_pending", "expected": "physically equivalent meters under separate .001 and 1 RNA encodings"},
        {"id": "topology-renumber", "scope": "formal_pending", "expected": "new target session/generation with reversed original triangle rows"},
        {"id": "reference-replacement", "scope": "rework_probe_and_formal", "expected": "owned reference; old plan revoked; late feedback eligible"},
        {"id": "zero-open", "scope": "formal_pending", "expected": "finite positive target; execute explicit opening command from contact"},
        {"id": "zero-section", "scope": "formal_pending", "expected": "section_requires_positive_gap; no image/ticket"},
        {"id": "same-frame-observation-ids", "scope": "rework_probe_and_formal", "expected": "phase IDs distinct with same frame"},
        {"id": "wrong-and-repeated-feedback", "scope": "rework_probe_and_formal", "expected": "owner, binding, and single consumption"},
        {"id": "model-deployment-equivalence", "scope": "formal_pending", "expected": "three exported v1 deployments, ring/order/initial and one-step update"},
        {"id": "two-sessions-close-reopen", "scope": "formal_pending", "expected": "two isolated sessions; late/foreign tickets reject after close/reopen"},
        {"id": "context-topology", "scope": "rework_probe_and_formal", "expected": "one same-capture context generation update; target generations fixed"},
    ]


def rework_probe_inputs():
    """Inputs for the new CPU-stub and bounded native probes, fixed before execution."""
    main = fixture_manifest()
    carried = build_fixture(main[20])
    shape = build_fixture(next(spec for spec in fixture_manifest(partition="control")
                               if spec.case_id == "nonbasis-key"))
    ids = tuple(mesh.object_id for mesh in carried.meshes)
    generations = dict(zip(ids, (6, 7, 8, 9), strict=True))
    renewed = {**generations, "moving-screen": 10}
    no_changes = dict.fromkeys(ids, ())
    context_topology = {**no_changes, "moving-screen": ("TOPOLOGY",)}
    return {
        "schema": "human-eye-integration-rework-controls-v1",
        "cpu_stub": {
            "kind": "portable_fake_host_uses_verification_only_control_seam",
            "initial_moving_world_x_m": 0.0,
            "initial_reference_world_x_m": 2.0,
            "initial_gap_m": 1.0,
            "command": {"kind": "translate", "delta_world_m": [0.25, 0.0, 0.0]},
            "goal": {"distance_m": 0.0, "tolerance_m": 0.0},
            "before_observation_id": "before",
            "after_observation_id": "after",
            "predictor": "NONE",
            "view_arm": "F",
            "mode": None,
            "expected_measured_delta_m_when_available": -0.25,
            "cases": [
                {"id": "stale-plan-after-new-observation", "write_applied": False, "outcome_available": False},
                {"id": "after-target-capture-failure", "write_applied": True, "outcome_available": False},
                {"id": "after-control-readback-failure", "write_applied": True, "outcome_available": False},
                {"id": "after-context-capture-failure", "write_applied": True, "outcome_available": True},
                {"id": "after-vg-render-failure", "write_applied": True, "outcome_available": True,
                 "after_mode": "NATURAL"},
                {"id": "after-ao-encode-failure", "write_applied": True, "outcome_available": True},
            ],
        },
        "native": [
            {
                "id": "masks-generations-none",
                "fixture_id": carried.spec.case_id,
                "view_arm": "F",
                "predictor": "NONE",
                "command": asdict(carried.command),
                "action_id": "act",
                "capture_reference": _observation(carried, "capture-reference", None,
                                                   dict.fromkeys(ids, _OBSERVE_TARGETS), generations),
                "static": _observation(carried, "static", None, no_changes, generations),
                "after": _observation(carried, "after-none", None,
                                      {**no_changes, **dict.fromkeys(carried.target_ids, _AFTER_TARGETS),
                                       "moving-screen": ("TRANSFORM",)}, generations),
                "topology_change": "reverse moving-screen triangle row order, vertex positions unchanged",
                "reject_missing_generation": {
                    "observation_id": "bad-generation", "mode": None, "changes": context_topology,
                    "context_generations": {},
                },
                "context_topology": _observation(carried, "context-topology", None, context_topology, renewed),
                "unit_change": _observation(carried, "unit-change", None,
                                            dict.fromkeys(ids, ("UNITS",)), renewed),
                "unit_change_m_per_BU": 0.5,
            },
            {
                "id": "late-feedback-basis-reference-close",
                "fixture_id": shape.spec.case_id,
                "frame_id": shape.spec.frame_id,
                "deployment_process_index": 0,
                "topology_generations": dict.fromkeys(shape.target_ids, 1),
                "capture_reference_id": "capture-reference",
                "before_observation_id": "before",
                "action_id": "act",
                "after_observation_id": "after",
                "view_arm": "L",
                "predictor": "L",
                "mode": "SECTION",
                "command": asdict(shape.command),
                "followup": {"action_id": "revoked", "command": asdict(shape.followup_command)},
                "masks": {"reference": _OBSERVE_TARGETS, "before": _OBSERVE_TARGETS,
                          "after": _AFTER_TARGETS, "next": _OBSERVE_TARGETS},
                "replace_reference_from": "after owned actual moving world_m",
                "authored_basis_change": {"key_name": "Actuate", "relative_key": "Relative",
                                          "vertex_row": 0, "component": "x", "add_bu": 0.125},
                "next_observation_id": "next",
                "feedback_controls": [
                    "old followup plan rejects after replace_reference",
                    "before/after V and actual A tickets eligible after replace_reference",
                    "duplicate and foreign tickets reject",
                    "next V ticket rejects after close",
                ],
            },
        ],
    }


def _archived_feedback(feedback_root, case_id):
    records = []
    for phase in ("before", "after"):
        relative = Path(case_id) / f"{phase}.visual.json"
        source = feedback_root / relative
        payload = source.read_bytes()
        record = json.loads(payload)
        evidence, score = record["evidence"], record["score"]
        png = source.with_name(f"{phase}.png")
        if sha256(png.read_bytes()).hexdigest() != score["png_sha256"]:
            raise ValueError(f"Archived feedback does not identify its image: {source}")
        records.append({
            "observation_id": phase,
            "attachment_key": f"{phase}.png",
            "frame_id": evidence["metadata"]["frame_id"],
            "target_ids": evidence["metadata"]["target_ids"],
            "canonical_index": evidence["candidate"],
            "selected_direction": evidence["metadata"]["selection"]["direction"],
            "selected_probe_rays": evidence["selected_rays"],
            "native_stop": evidence["native_stop"],
            "png_sha256": score["png_sha256"],
            "strict_verdict": score["passed"],
            "safe": score["safe"],
            "archive_record": relative.as_posix(),
            "archive_record_sha256": sha256(payload).hexdigest(),
        })
    return records


def method_probe_inputs(feedback_root=None):
    cases = [fixture_manifest()[i].case_id for i in PROBE_INDICES]
    archived = (None if feedback_root is None else
                {key: _archived_feedback(Path(feedback_root), key) for key in cases})
    return {
        "schema": "human-eye-integration-method-probe-v1",
        "purpose": "qualify_instrumentation_only_no_I_measurement",
        "clock": {"name": "time.perf_counter_ns", "consecutive_empty_pairs": 1000},
        "bb": {
            "same_reference_implementation_both_lanes": True,
            "case_ids": cases,
            "deployment_process_index": 0,
            "warm_pairs_per_case": 5,
            "measured_pairs_per_case": 31,
            "warm_pair_indices": list(range(5)),
            "measured_pair_indices": list(range(5, 36)),
            "lane_labels": [0, 1],
            "arm_order": "0,1 when (main_case_ordinal + pair_index) % 2 == 0, else 1,0",
            "observation_id_templates": {
                name: f"{name}.{{pair:02d}}.{{lane}}" for name in ("before", "after", "next")
            },
            "action_id_templates": {
                name: f"{name}.{{pair:02d}}.{{lane}}" for name in ("act", "next-act")
            },
            "attachment_key_rule": "actual current observation ID followed by .png",
            "segments": ["before", "action", "feedback", "next", "continuous_total"],
            "state": "one warm B session per case/lane; restore host channels and private weight/ring active state outside each timed interval",
            "tickets": "fresh plans and feedback tickets inside each repeat; feedback uses its current ticket binding",
            "score_identity_checks": "outside timing, compare PNG SHA/frame/target/direction/candidate/rays against archived strict audit; public generation metadata need not match historical replay",
            "actual_feedback_binding_and_consumption": "inside feedback timing",
            "archived_feedback": archived,
            "archived_feedback_root": None if feedback_root is None else Path(feedback_root).as_posix(),
            "known_strict_failure": {"case_id": cases[2], "observation_id": "after",
                                     "strict_verdict": False, "safe": False},
            "statistics": "median within case then across-case linear p95; disclose each paired timing and both ratio directions",
            "qualification": "each segment max(p95_lane_0/p95_lane_1, p95_lane_1/p95_lane_0) <= 1.05",
        },
        "resource": {
            "case_id": cases[0],
            "deployment_process_index": 0,
            "separate_process_from_latency": True,
            "sampling_points": ["cold_start", "after_init", "prepared", "observed", "close"],
            "managed": "deduplicate NumPy backing allocations and take tracemalloc peak in bounded draw/close",
            "RSS": "Win32 PROCESS_MEMORY_COUNTERS WorkingSetSize and PeakWorkingSetSize",
            "GPU": "DXGI adapter3 QueryVideoMemoryInfo LOCAL and NON_LOCAL current process usage and budget",
            "nvidia_smi": "availability-only if DXGI unavailable",
            "formal_gates": False,
        },
    }


def manifest_document(*, feedback_root=None):
    main = fixture_manifest()
    return {
        "schema": "human-eye-integration-fixtures-v2",
        "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "coordinates": "local meters; parent-relative dimensionless linear transforms and meter translations",
        "main": [asdict(spec) for spec in main],
        "controls": [asdict(spec) for spec in fixture_manifest(partition="control")],
        "native_probe_indices": PROBE_INDICES,
        "formal_plans": [_formal_plan(spec) for spec in main],
        "formal_performance": {
            "processes": 3, "warm_pairs_per_case": 5, "measured_pairs_per_case": 31,
            "arm_order": "(process_index + case_ordinal + repeat_index) modulo 2",
            "statistics": "per-case median then linear p95 across 24 cases",
            "cost_segments": ["before", "action", "feedback", "next", "continuous_total"],
            "I_over_B_limit_per_process_per_segment": 1.05,
            "old_CF_separate_V_A_and_total_limit": 1.10,
            "new_per_case_hard_gate": False,
            "pre_run_identity": "seal actual project import/source closure, dirty/untracked bytes, exact argv/env, deployment-v1 export and scored feedback identities",
        },
        "deployments": deployment_inputs(),
        "control_plans": _planned_controls(),
        "rework_controls": rework_probe_inputs(),
        "method_probe": method_probe_inputs(feedback_root),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--feedback-root", type=Path,
                        help="Original preflight_001 native_002 tree to bind preregistered B/B feedback.")
    args = parser.parse_args()
    text = json.dumps(manifest_document(feedback_root=args.feedback_root),
                      ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
