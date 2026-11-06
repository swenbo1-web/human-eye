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


def manifest_document():
    return {
        "schema": "human-eye-integration-fixtures-v1",
        "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "coordinates": "local meters; parent-relative dimensionless linear transforms and meter translations",
        "main": [asdict(spec) for spec in fixture_manifest()],
        "controls": [asdict(spec) for spec in fixture_manifest(partition="control")],
        "native_probe_indices": PROBE_INDICES,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(manifest_document(), ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
