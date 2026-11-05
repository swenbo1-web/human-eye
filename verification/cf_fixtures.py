"""CF experiment registry and geometry generator. Arrays use world meters.

The registry is safe to enumerate without generating a scene or a label. A
train worker receives only train/validation specs from a split-specific manifest.
Array materialization is explicit through build_fixture and never probes VG or BC.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from math import cos, pi, sin, sqrt, tau
from pathlib import Path

import numpy as np


SEEDS = (20261105, 79463, 310519)
SCALES_M = (0.01, 0.04, 0.16)
UNIT_SCALES = (0.001, 1.0)
GAP_RATIOS = (1e-4, 1e-3, 1e-2)
V_FAMILIES = (
    "straight-slot", "segmented-polygon", "offset-double-slot",
    "curved-slot", "pleated-baffle", "interleaved-channel",
)
A_FAMILIES = (
    "straight-beam", "offset-elbow", "arc-beam",
    "tapered-beam", "multifold-beam", "nonplanar-beam",
)
V_CONTROLS = ("contact", "empty", "enclosed", "unobstructed")
SPLITS = ("train", "validation", "evaluation", "control", "diagnostic")
TARGET_IDS = ("moving", "reference")
COLOR_A = (0.82, 0.24, 0.15, 1.0)
COLOR_B = (0.16, 0.60, 0.90, 1.0)
COLOR_BAFFLE = (0.36, 0.40, 0.45, 1.0)
SHAPE_KEY = "Actuate"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    kind: str
    key_name: str | None
    control_before: float | tuple[float, float, float]
    target_value: float | None
    delta_world_m: tuple[float, float, float] | None
    sign: int
    amplitude: float


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    head: str
    seed: int
    split: str
    family: str
    ordinal: int
    episode_id: str
    group_id: str
    scale_m: float
    scale_length: float
    mode: str
    # SO(3): uniform azimuth, uniform cosine of polar angle, uniform roll.
    pose: tuple[float, float, float]
    parameters: dict
    command: CommandSpec | None


@dataclass(frozen=True, slots=True)
class MeshSpec:
    object_id: str
    vertices_m: np.ndarray
    triangles: np.ndarray
    color: tuple[float, float, float, float]
    # Relative Basis -> Actuate displacement, in the same coordinates as vertices.
    shape_basis_m: np.ndarray | None = None


@dataclass(frozen=True, slots=True)
class Fixture:
    spec: EpisodeSpec
    meshes: tuple[MeshSpec, ...]
    expected_gap_m: float | None
    # Only the parallel-box control has a fixture-derived action oracle.
    expected_delta_m: float | None = None
    target_ids: tuple[str, str] = TARGET_IDS

    @property
    def scale_length(self):
        return self.spec.scale_length

    @property
    def mode(self):
        return self.spec.mode

    @property
    def command(self):
        return self.spec.command


def _rng(seed, head, split, family_index, ordinal):
    key = (seed, ("V", "A").index(head), SPLITS.index(split), family_index, ordinal)
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(key)))


def _rotation(pose):
    azimuth, polar_cos, roll = pose
    polar_sin = sqrt(1 - polar_cos ** 2)
    axis = np.array((polar_sin * cos(azimuth), polar_sin * sin(azimuth), polar_cos))
    u = np.array((-sin(azimuth), cos(azimuth), 0.0))
    v = np.cross(axis, u)
    return np.column_stack((axis, cos(roll) * u + sin(roll) * v,
                            -sin(roll) * u + cos(roll) * v))


def _shape_command(q, sign, amplitude):
    return CommandSpec("set_shape_key", SHAPE_KEY, q, round(q + sign * amplitude, 10),
                       None, sign, amplitude)


def _spec(head, seed, split, family_index, ordinal, *, variant=None):
    families = V_FAMILIES if head == "V" else A_FAMILIES
    family = families[family_index]
    geom_slot = ordinal
    if split == "control":
        family = V_CONTROLS[family_index] if head == "V" else "parallel-box"
    if split == "diagnostic" and variant == "clamp":
        family = "shape-readback-clamp"
    rng = _rng(seed, head, split, family_index, geom_slot)
    scale = SCALES_M[(ordinal + family_index) % len(SCALES_M)]
    unit = UNIT_SCALES[(ordinal // 2 + family_index + SEEDS.index(seed)) % 2]
    pose = (float(rng.uniform(0, tau)), float(rng.uniform(-1, 1)),
            float(rng.uniform(0, tau)))
    mode = "NATURAL"
    command = None
    if head == "V":
        if split != "control" and ordinal % 2:
            mode = "SECTION"
        parameters = {
            "gap_ratio": GAP_RATIOS[(ordinal // 2 + family_index) % len(GAP_RATIOS)],
            "phase_rad": float(rng.uniform(0, tau)),
            "window_rad": float(rng.uniform(.62, .96) if mode == "NATURAL"
                                else rng.uniform(1.02, 1.34)),
            "radius_factor": float(rng.uniform(.92, 1.08)),
            "skew": float(rng.uniform(-1, 1)),
        }
    elif split == "control":
        sign = (-1, 0, 1)[ordinal % 3]
        amplitude = (.0125, .025)[ordinal // 3 % 2]
        if sign == 0:
            amplitude = 0.
        translation = _rotation(pose) @ (scale * sign * amplitude, 0., 0.)
        parameters = {"gap_ratio": .075}
        command = CommandSpec("translate", None, (0., 0., 0.), None,
                              tuple(map(float, translation)), sign, amplitude)
    else:
        parameters = {
            "clearance_ratio": float(rng.uniform(.042, .067)),
            "phase_rad": float(rng.uniform(0, tau)),
            "crown_offsets": rng.uniform(0, .021, 9).tolist(),
            "basis_heights": rng.uniform(.105, .165, 9).tolist(),
            "basis_sign": int(rng.choice((-1, 1))),
            "width_factor": float(rng.uniform(.90, 1.10)),
            "offset_factor": float(rng.uniform(.80, 1.20)),
        }
        if split == "diagnostic":
            if variant == "clamp":
                command = _shape_command(.4, 1, 20.0)
            else:
                command = _shape_command(.4, -1 if variant == "minus" else 1, .2)
        else:
            condition = ordinal % 4
            sign, amplitude = ((-1, .2), (-1, .1), (1, .1), (1, .2))[condition]
            q = (.2, .4, .6, .8)[(ordinal // 4 + condition + family_index) % 4]
            command = _shape_command(q, sign, amplitude)
    group = f"{head}-{seed}-{split}-{family}-{ordinal:03d}"
    episode = group if variant is None else f"{group}-{variant}"
    return EpisodeSpec(head, seed, split, family, ordinal, episode, group, scale,
                       unit, mode, pose, parameters, command)


def fixture_manifest(*, head=None, seed=None, split=None):
    """Return specs only, ordered head, seed, split, family, ordinal, variant."""
    result = []
    for selected_head in ("V", "A") if head is None else (head,):
        for selected_seed in SEEDS if seed is None else (seed,):
            for partition in SPLITS if split is None else (split,):
                common = (selected_head, selected_seed, partition)
                if partition == "diagnostic":
                    if selected_head == "A":
                        for family in range(3, 6):
                            for variant in ("minus", "plus"):
                                result.append(_spec(*common, family, 0, variant=variant))
                        result.append(_spec(*common, 0, 0, variant="clamp"))
                    continue
                family_range, count = {
                    "train": (range(3), 80),
                    "validation": (range(3), 20),
                    "evaluation": (range(3, 6), 20),
                    "control": (range(4), 3) if selected_head == "V" else (range(1), 12),
                }[partition]
                result.extend(_spec(*common, family, ordinal) for family in family_range
                              for ordinal in range(count))
    return tuple(result)


def _quads_faces(quads):
    return [(a, b, c) for a, b, c, d in quads] + [(a, c, d) for a, b, c, d in quads]


def _stitch(first, second, count):
    return [(first + j, first + (j + 1) % count, second + (j + 1) % count, second + j)
            for j in range(count)]


def _loft(rings):
    points = np.asarray(rings, dtype=np.float64)
    length, count, _ = points.shape
    quads = [quad for k in range(length - 1) for quad in
             _stitch(k * count, (k + 1) * count, count)]
    tail = (length - 1) * count
    caps = [(0, j + 1, j) for j in range(1, count - 1)]
    caps += [(tail, tail + j, tail + j + 1) for j in range(1, count - 1)]
    return points.reshape(-1, 3), _quads_faces(quads) + caps


def _mesh(object_id, points, faces, color, transform, basis=None):
    vertices = np.asarray(points, dtype=np.float64).reshape(-1, 3) @ transform.T
    triangles = np.asarray(faces, dtype=np.int32).reshape(-1, 3)
    displacement = None if basis is None else np.asarray(basis) @ transform.T
    return MeshSpec(object_id, vertices, triangles, color, displacement)


def _v_target(gap, side):
    # Four 12-gon rings: outer front/rear and two interior-bore rings.
    # The closed bore starts beyond the conical tip at .045g; the near
    # support sample at .0625g therefore sees this bore in SECTION.
    count = 12
    circle = [(cos(tau * j / count), sin(tau * j / count)) for j in range(count)]
    rings = (
        (.045 * gap, .45 * gap), (.24 * gap, .58 * gap),
        (.21, .16), (.045 * gap, .30 * gap), (.24 * gap, .30 * gap),
    )
    points = [(side * (gap / 2), 0., 0.)]
    points.extend((side * (gap / 2 + offset), radius * y, radius * z)
                  for offset, radius in rings for y, z in circle)
    rear, cavity_front, cavity_rear = 1 + 2 * count, 1 + 3 * count, 1 + 4 * count
    quads = _stitch(1, 1 + count, count) + _stitch(1 + count, rear, count)
    quads += _stitch(cavity_rear, cavity_front, count)
    # For the negative-x target the x mirror also reverses winding.
    faces = [(0, 1 + (j + 1) % count, 1 + j) for j in range(count)]
    faces += _quads_faces(quads)
    faces += [(rear, rear + j, rear + j + 1) for j in range(1, count - 1)]
    faces += [(cavity_front, cavity_front + j, cavity_front + j + 1)
              for j in range(1, count - 1)]
    faces += [(cavity_rear, cavity_rear + j + 1, cavity_rear + j)
              for j in range(1, count - 1)]
    if side < 0:
        faces = [(a, c, b) for a, b, c in faces]
    return points, faces


def _arc_panel(start, stop, segments, x_range, radial, axial, twist, thickness):
    """Closed radial wall strip. Each section is a four-vertex (x,r) rectangle."""
    x0, x1 = x_range
    rings = []
    for j, angle in enumerate(np.linspace(start, stop, segments + 1)):
        r = radial(j, angle)
        dx = axial(j, angle)
        rings.append([(x + dx, (r + dr) * cos(angle + turn), (r + dr) * sin(angle + turn))
                      for x, dr, turn in ((x0, 0., -twist), (x0, thickness, -twist),
                                          (x1, thickness, twist), (x1, 0., twist))])
    return _loft(rings)


def _v_obstacles(spec, gap):
    p = spec.parameters
    window, phase, skew = p["window_rad"], p["phase_rad"], p["skew"]
    if spec.mode == "SECTION":
        # The mirrored baffles lie wholly in the .30g bore. Both ordinary
        # support offsets (.0625g and .125g) lie inside their axial span.
        placements = (((-.204 * gap, -.056 * gap), -.008 * skew, .156 * gap),
                      ((.056 * gap, .204 * gap), .008 * skew, .156 * gap))
        placements = tuple(((a + side * gap / 2, b + side * gap / 2), turn, radius)
                           for side, ((a, b), turn, radius) in zip((-1, 1), placements))
    else:
        placements = (((-.165, .165), 0., .47),)
    for x_range, turn, base_r in placements:
        radius = base_r * p["radius_factor"]
        center = phase + turn
        start, stop = center + window / 2, center + tau - window / 2
        thickness = .055 * radius
        axial_span = x_range[1] - x_range[0]

        def constant(_j, _angle):
            return radius

        def no_shift(_j, _angle):
            return 0.

        def panel(a, b, n, radial=constant, axial=no_shift, twist=0.):
            return _arc_panel(a, b, n, x_range, radial, axial, twist, thickness)

        family = spec.family
        if family == "straight-slot":
            # One joined coarse octagonal wrap with a single angular slit.
            yield panel(start, stop, 8)
        elif family == "segmented-polygon":
            # Independent straight shields with overlap and alternating radius.
            edges = np.linspace(start, stop, 11)
            for i in range(10):
                a = edges[i] - (.035 if i else 0.)
                b = edges[i + 1] + (.035 if i < 9 else 0.)
                tile_radius = radius * (.91 if i % 2 else 1.09)
                yield panel(a, b, 1, lambda _j, _a: tile_radius)
        elif family == "offset-double-slot":
            # Two joined polygonal wraps; both gaps must remain open.
            yield panel(start, stop, 12, lambda _j, _a: .83 * radius)
            offset = .20 * skew
            yield panel(start + offset, stop + offset, 9,
                        lambda _j, _a: 1.27 * radius)
        elif family == "curved-slot":
            # Smooth oval radial profile and continuous axial skew of the slit.
            yield panel(start, stop, 36,
                        lambda _j, a: radius * (1 + .13 * cos(2 * a - phase)),
                        lambda _j, a: .025 * axial_span * sin(a - phase),
                        .09 * skew)
        elif family == "pleated-baffle":
            # Alternating radial folds with a smaller axial corrugation.
            yield panel(start, stop, 15,
                        lambda j, _a: radius * (1 + .18 * (-1) ** j),
                        lambda j, _a: .018 * axial_span * (-1) ** j,
                        -.06 * skew)
        elif family == "interleaved-channel":
            # Offset overlapping angular tiles on alternating radial levels.
            # Axial shear and opposite side twists prevent a coplanar stack.
            edges = np.linspace(start, stop, 10)
            for i in range(9):
                handed = (-1) ** i
                a = edges[i] - (.065 if i else 0.)
                b = edges[i + 1] + (.065 if i < 8 else 0.)
                yield panel(a, b, 2,
                            lambda _j, t: radius * (1 + .19 * handed + .035 * sin(3 * t)),
                            lambda j, _t: .02 * axial_span * (j - 1) * handed,
                            .045 * (handed + .5 * skew))
        elif family == "enclosed":
            for j in range(4):
                a = phase + j * pi / 2
                yield panel(a - .02, a + pi / 2 + .02, 6,
                            lambda _j, _a: radius * (1 + .08 * (j % 2)))


def _build_v(spec, transform):
    gap = spec.parameters["gap_ratio"]
    if spec.family == "contact":
        gap = 0.
    meshes = []
    for object_id, side, color in zip(TARGET_IDS, (-1, 1), (COLOR_A, COLOR_B)):
        if spec.family == "empty" and side > 0:
            points, faces = (), ()
        elif gap == 0:
            points, faces = _solid_v_tip(side)
        else:
            points, faces = _v_target(gap, side)
        meshes.append(_mesh(object_id, points, faces, color, transform))
    for i, (points, faces) in enumerate(_v_obstacles(spec, gap)):
        meshes.append(_mesh(f"occluder-{i:02}", points, faces, COLOR_BAFFLE, transform))
    expected = None if spec.family == "empty" else gap * spec.scale_m
    return Fixture(spec, tuple(meshes), expected)


def _solid_v_tip(side):
    return ((0., 0., 0.), (side * .2, -.14, -.14), (side * .2, .14, -.14),
            (side * .2, 0., .16)), ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))


_RECT = ((-1, -1), (1, -1), (1, 0), (-1, 0))
_CHAMFER = ((-1, -.8), (-.65, -1), (.65, -1), (1, -.8), (1, -.18),
            (.70, 0), (-.70, 0), (-1, -.18))


def _ring(x, y, top, half_width, depth, profile, cross_slope=0.):
    return [(x, y + w * half_width, top + h * depth + w * half_width * cross_slope)
            for w, h in profile]


def _a_profiles(family, p):
    f = A_FAMILIES.index(family)
    n = (5, 6, 7, 7, 8, 9)[f]
    t = np.linspace(-1., 1., n)
    x = .48 * t
    width = .036 * p["width_factor"] * np.ones(n)
    depth = .065 * np.ones(n)
    cross = np.zeros(n)
    y = np.zeros(n)
    if f == 1:
        y = .125 * p["offset_factor"] * np.maximum(0., (t + .2) / 1.2)
    elif f == 2:
        x = .56 * np.sin(.98 * t)
        y = .18 * p["offset_factor"] * (1 - np.cos(.98 * t))
    elif f == 3:
        width *= .63 + .36 * (1 + t)
        depth *= .78 + .32 * (1 - t)
        y = .07 * t
    elif f == 4:
        y = .074 * p["offset_factor"] * (-1.) ** np.arange(n)
        width *= 1 + .12 * (-1.) ** np.arange(n)
    elif f == 5:
        x = .52 * t
        y = .087 * p["offset_factor"] * np.sin(pi * t + p["phase_rad"])
        width *= 1 + .22 * np.cos(pi * t)
        depth *= 1 + .22 * np.sin(2 * pi * t)
        cross = .21 * np.sin(pi * t)
    return x, y, width, depth, cross, (_RECT if f < 3 else _CHAMFER)


def _reference_profile(family, phase):
    f = A_FAMILIES.index(family)
    # Early families use flat, ramped and concave base plates. Holdout plates
    # have different station placement, support heights and lateral sections.
    x = np.asarray((
        (-.62, .62), (-.62, -.15, .62), (-.62, -.30, 0., .30, .62),
        (-.64, -.38, .08, .44, .64), (-.64, -.48, -.20, .12, .39, .64),
        (-.66, -.49, -.30, -.11, .08, .26, .43, .66),
    )[f])
    base = (
        lambda t: np.zeros_like(t),
        lambda t: .018 * np.maximum(0, t + .15),
        lambda t: .028 * t ** 2,
        lambda t: .017 * abs(t + .22) + .013 * t,
        lambda t: .016 * np.cos(7 * t + phase),
        lambda t: .013 * np.sin(5 * t + phase),
    )[f](x) + .17
    width = (.245, .245, .26, .28, .27, .28)[f] + .022 * (x if f >= 3 else 0 * x)
    center = .035 * np.sin(3 * x + phase) if f == 5 else np.zeros_like(x)
    cross = .026 * np.sin(4 * x + phase) if f == 5 else np.zeros_like(x)
    # A flat lower rim is retained even with chamfered upper corners.
    outline = _RECT if f < 3 else _CHAMFER
    rings = [_ring(t, cy, h, w, -.056, outline, slope)
             for t, cy, h, w, slope in zip(x, center, base, width, cross)]
    points, faces = _loft(rings)
    return x, base, points, [(a, c, b) for a, b, c in faces]


def _box(x0, x1):
    return _loft([_ring(x, 0., .18, .20, .36, _RECT) for x in (x0, x1)])


def _build_a(spec, transform):
    p = spec.parameters
    command = spec.command
    if spec.family == "parallel-box":
        ratio = p["gap_ratio"]
        a, af = _box(-.39, -ratio / 2)
        b, bf = _box(ratio / 2, .39)
        meshes = (_mesh(TARGET_IDS[0], a, af, COLOR_A, transform),
                  _mesh(TARGET_IDS[1], b, bf, COLOR_B, transform))
        return Fixture(spec, meshes, spec.scale_m * ratio,
                       -spec.scale_m * command.sign * command.amplitude)
    family = A_FAMILIES[0] if spec.family == "shape-readback-clamp" else spec.family
    x, y, width, depth, cross, outline = _a_profiles(family, p)
    rx, base, reference, reference_faces = _reference_profile(family, p["phase_rad"])
    count = len(x)
    station = np.arange(count)
    top = np.interp(x, rx, base) - p["clearance_ratio"] - np.asarray(p["crown_offsets"][:count])
    current, moving_faces = _loft([_ring(a, b, c, w, d, outline, slope)
                                    for a, b, c, w, d, slope in
                                    zip(x, y, top, width, depth, cross)])
    phase = p["phase_rad"]
    basis_z = np.asarray(p["basis_heights"][:count]) * (-1.) ** station * p["basis_sign"]
    basis_y = .019 * np.sin(pi * x + phase)
    basis_x = .011 * np.cos(pi * x + phase) if family == A_FAMILIES[-1] else 0 * x
    displacement = np.repeat(np.column_stack((basis_x, basis_y, basis_z)), len(outline), axis=0)
    rest = current - float(command.control_before) * displacement
    meshes = (_mesh(TARGET_IDS[0], rest, moving_faces, COLOR_A, transform, displacement),
              _mesh(TARGET_IDS[1], reference, reference_faces, COLOR_B, transform))
    return Fixture(spec, meshes, None)


def build_fixture(spec):
    """Build one assigned scene from frozen spec; no scoring or host dependencies."""
    transform = spec.scale_m * _rotation(spec.pose)
    return _build_v(spec, transform) if spec.head == "V" else _build_a(spec, transform)


def manifest_document(*, head=None, seed=None, split=None):
    return {
        "schema": "cf-fixtures-v1",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "coordinates": "world meters; Blender mesh/shape coordinates divide by active scale_length",
        "target_ids": TARGET_IDS,
        "episodes": [asdict(row) for row in fixture_manifest(head=head, seed=seed, split=split)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", choices=("V", "A"))
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--split", choices=SPLITS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    doc = manifest_document(head=args.head, seed=args.seed, split=args.split)
    payload = json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
