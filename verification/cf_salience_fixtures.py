"""Portable CF-S specs and train-only geometry for protocol preflight."""

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import pi
from pathlib import Path

import numpy as np


SEEDS = (20261105, 79463, 310519)
TRAIN_FAMILIES = ("square-lattice", "zigzag-strip", "annular-sector")
EVALUATION_FAMILIES = ("apex-fan", "closed-torus", "creased-prism")
FAMILIES = TRAIN_FAMILIES + EVALUATION_FAMILIES
SPLITS = ("train", "validation", "evaluation", "diagnostic")
SCALES_M = (.01, .04, .16)
METERS_PER_UNIT = (.001, 1.)
MECHANISMS = ("stretch", "dilate", "buckle", "drift")


@dataclass(frozen=True, slots=True)
class EpisodeSpec:
    seed: int
    split: str
    family: str
    ordinal: int
    episode_id: str
    group_id: str
    scale_m: float
    meters_per_unit: float
    resolution: tuple[int, int]
    phase_rad: float
    center: tuple[float, float]
    width: float
    amplitude: float
    mechanism: str
    variant: str = "base"


@dataclass(frozen=True, slots=True)
class BucketChart:
    axes: tuple[int, int]
    lower: tuple[float, float]
    span: tuple[float, float]


@dataclass(frozen=True, slots=True)
class Fixture:
    spec: EpisodeSpec
    reference_m: np.ndarray
    current_m: np.ndarray
    triangles: np.ndarray
    chart: BucketChart


def _spec(seed, split, family, ordinal, variant="base"):
    index = FAMILIES.index(family)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        (seed, SPLITS.index(split), index, ordinal),
    )))
    first = ((8, 12), (9, 16), (9, 16), (17, 35), (13, 24), (5, 10))[index]
    second = ((8, 12), (4, 7), (4, 7), (1, 1), (8, 14), (6, 6))[index]
    rows = int(rng.integers(first[0], first[1] + 1))
    cols = rows if index == 0 else int(rng.integers(second[0], second[1] + 1))
    group = f"S-{seed}-{split}-{family}-{ordinal:03d}"
    return EpisodeSpec(
        seed=seed,
        split=split,
        family=family,
        ordinal=ordinal,
        episode_id=group if variant == "base" else f"{group}-{variant}",
        group_id=group,
        scale_m=SCALES_M[(ordinal + index) % len(SCALES_M)],
        meters_per_unit=METERS_PER_UNIT[(ordinal // 2 + index + SEEDS.index(seed)) % 2],
        resolution=(rows, cols),
        phase_rad=float(rng.uniform(0., 2 * pi)),
        center=tuple(map(float, rng.uniform(.18, .82, 2))),
        width=float(rng.uniform(.11, .23)),
        amplitude=float(rng.uniform(.08, .30)),
        mechanism=MECHANISMS[ordinal % len(MECHANISMS)],
        variant=variant,
    )


def fixture_manifest(*, seed=None, split=None):
    """List specs by seed, split, family, ordinal. Listing never builds geometry."""
    specs = []
    for current_seed in SEEDS if seed is None else (seed,):
        for partition in SPLITS if split is None else (split,):
            if partition == "diagnostic":
                for family, variants in (
                    ("square-lattice", ("reference", "rigid-pose", "unit-recode", "scale-recode")),
                    ("apex-fan", ("no-faces",)),
                    ("creased-prism", ("topology-replacement",)),
                ):
                    specs.extend(_spec(current_seed, partition, family, 0, variant)
                                 for variant in variants)
                continue
            families = EVALUATION_FAMILIES if partition == "evaluation" else TRAIN_FAMILIES
            count = 80 if partition == "train" else 20
            specs.extend(_spec(current_seed, partition, family, ordinal)
                         for family in families for ordinal in range(count))
    return tuple(specs)


def bucket_chart(reference_m, triangles):
    """Rank the indexed reference AABB spans, using x/y/z index on exact ties."""
    if len(triangles) == 0:
        return None
    indexed = reference_m[np.unique(triangles)]
    lower = indexed.min(axis=0)
    span = indexed.max(axis=0) - lower
    axes = tuple(sorted(range(3), key=lambda i: (-span[i], i))[:2])
    return BucketChart(axes, tuple(float(lower[i]) for i in axes),
                       tuple(float(span[i]) for i in axes))


def bucket_ids(reference_m, triangles):
    """Return bucket ID 4*u+v for each original face row in the fixed chart."""
    chart = bucket_chart(reference_m, triangles)
    if chart is None:
        return np.empty(0, dtype=np.int8)
    p0, p1, p2 = reference_m[triangles][:, :, chart.axes].transpose(1, 0, 2)
    centroids = p0 + ((p1 - p0) / 3 + (p2 - p0) / 3)
    relative = centroids - chart.lower
    normalized = np.divide(relative, chart.span, out=np.zeros_like(relative),
                           where=np.asarray(chart.span) > 0)
    cells = np.clip(np.floor(4 * normalized), 0, 3).astype(np.int8)
    return 4 * cells[:, 0] + cells[:, 1]


def _grid_faces(rows, cols, *, alternate=False, closed_rows=False, closed_cols=False):
    triangles = []
    row_limit = rows if closed_rows else rows - 1
    col_limit = cols if closed_cols else cols - 1
    for i in range(row_limit):
        for j in range(col_limit):
            r, c = (i + 1) % rows, (j + 1) % cols
            a, b, d, e = i * cols + j, i * cols + c, r * cols + j, r * cols + c
            if alternate and (i + j) % 2:
                triangles.extend(((a, b, d), (b, e, d)))
            else:
                triangles.extend(((a, b, e), (a, e, d)))
    return np.asarray(triangles, dtype=np.int32)


def _square_lattice(spec):
    rows, cols = spec.resolution
    u, v = np.meshgrid(np.linspace(-.5, .5, cols), np.linspace(-.5, .5, rows))
    z = .06 * np.sin(2 * pi * u + spec.phase_rad) * np.cos(pi * v)
    return np.stack((u, v, z), axis=-1).reshape(-1, 3), _grid_faces(rows, cols)


def _zigzag(spec):
    rows, cols = spec.resolution
    u, v = np.meshgrid(np.linspace(-.5, .5, cols), np.linspace(-.5, .5, rows))
    stagger = .055 * (-1.) ** np.arange(rows)[:, None]
    x = u + stagger * (1 - 4 * u**2)
    y = .40 * v + .038 * np.sin(2 * pi * u + spec.phase_rad)
    z = .045 * np.sin(pi * u + spec.phase_rad) * np.cos(pi * v)
    return np.stack((x, y, z), axis=-1).reshape(-1, 3), _grid_faces(rows, cols, alternate=True)


def _annular(spec):
    rows, cols = spec.resolution
    radius, angle = np.meshgrid(np.linspace(.34, .76, cols),
                                np.linspace(-.77 * pi, .77 * pi, rows) + spec.phase_rad)
    vertices = np.stack((radius * np.cos(angle), .86 * radius * np.sin(angle),
                         .045 * np.sin(2 * angle) * radius), axis=-1)
    return vertices.reshape(-1, 3), _grid_faces(rows, cols, alternate=True)


def _apex_fan(spec):
    rings, _ = spec.resolution
    theta = np.linspace(0., 2 * pi, rings, endpoint=False) + spec.phase_rad
    radius = .60 * (1 + .09 * np.cos(3 * theta))
    boundary = np.column_stack((radius * np.cos(theta), .82 * radius * np.sin(theta),
                                .033 * np.sin(2 * theta)))
    points = np.vstack(([0., 0., .24], boundary))
    triangles = [(0, i + 1, (i + 1) % rings + 1) for i in range(rings)]
    return points, np.asarray(triangles, dtype=np.int32)


def _torus(spec):
    rows, cols = spec.resolution
    major, minor = np.meshgrid(np.linspace(0., 2 * pi, cols, endpoint=False),
                               np.linspace(0., 2 * pi, rows, endpoint=False))
    major += spec.phase_rad
    radius = .58 + .16 * np.cos(minor)
    vertices = np.stack((radius * np.cos(major), .87 * radius * np.sin(major),
                         .16 * np.sin(minor) + .05 * np.cos(2 * major)), axis=-1)
    return vertices.reshape(-1, 3), _grid_faces(rows, cols, closed_rows=True, closed_cols=True)


def _creased_prism(spec):
    rows, cols = spec.resolution
    yz = np.array(((-.30, -.14), (.28, -.14), (.34, .04), (.10, .25),
                   (-.09, .07), (-.33, .08)))
    x = np.linspace(-.57, .57, rows)
    profile = np.broadcast_to(yz, (rows, cols, 2)).copy()
    profile[:, :, 1] += .028 * np.sin(2 * pi * x + spec.phase_rad)[:, None]
    side = np.column_stack((np.repeat(x, cols), profile.reshape(-1, 2)))
    caps = [[x[i], *profile[i].mean(axis=0)] for i in (0, -1)]
    start, last = rows * cols, (rows - 1) * cols
    first_fan = [(start, (i + 1) % cols, i) for i in range(cols)]
    second_fan = [(start + 1, last + i, last + (i + 1) % cols) for i in range(cols)]
    triangles = np.vstack((_grid_faces(rows, cols, closed_cols=True), first_fan, second_fan))
    return np.vstack((side, caps)), triangles.astype(np.int32)


_BUILDERS = dict(zip(FAMILIES, (_square_lattice, _zigzag, _annular, _apex_fan, _torus, _creased_prism)))


def _deform(reference_m, chart, spec):
    first, second = chart.axes
    normal_axis = next(i for i in range(3) if i not in chart.axes)
    uv = (reference_m[:, chart.axes] - chart.lower) / chart.span
    u, v = (uv - spec.center).T
    weight = np.exp(-.5 * (u**2 + v**2) / spec.width**2)
    push = spec.amplitude * spec.scale_m * weight
    displacement = np.zeros_like(reference_m)
    if spec.mechanism == "stretch":
        displacement[:, first] = 2 * u * push
        displacement[:, second] = -1.1 * v * push
    elif spec.mechanism == "dilate":
        displacement[:, first] = 1.7 * u * push
        displacement[:, second] = 1.7 * v * push
    elif spec.mechanism == "buckle":
        displacement[:, normal_axis] = .48 * np.sin(6 * pi * u) * push
    else:
        displacement[:, chart.axes] = push[:, None] * (.62, -.25)
        displacement[:, normal_axis] = .73 * push
    return reference_m + displacement


def build_fixture(spec):
    """Materialize one explicitly requested train preflight case."""
    if spec.split != "train":
        raise ValueError("CF-S preflight permits train geometry only")
    vertices, triangles = _BUILDERS[spec.family](spec)
    reference_m = np.ascontiguousarray(vertices * spec.scale_m, dtype=np.float64)
    chart = bucket_chart(reference_m, triangles)
    current_m = _deform(reference_m, chart, spec)
    return Fixture(spec, reference_m, current_m, triangles, chart)


def manifest_document(*, seed=None, split=None):
    return {
        "schema": "cf-salience-specs-v1",
        "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "geometry_access": "train-only",
        "coordinates": "reference-local meters; meters_per_unit is separate host recoding metadata",
        "episodes": [asdict(spec) for spec in fixture_manifest(seed=seed, split=split)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--split", choices=SPLITS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(manifest_document(seed=args.seed, split=args.split),
                      ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
