"""Frozen E1 recipes and a quality-only oracle over independent RNA snapshots."""

from dataclasses import asdict, dataclass, replace
import json

import numpy as np

from verification.integration_fixtures import IntegrationFixture, build_fixture, fixture_manifest
from verification.test_bc_acceptance import convex_pair_oracle


@dataclass(frozen=True, slots=True)
class TaskCase:
    case_id: str
    family: str
    source_id: str
    target_fraction: float
    subdivisions: int = 0
    image_mode: str | None = None
    witness: str = "tip-tip"


@dataclass(frozen=True, slots=True)
class PreparedEpisode:
    case: TaskCase
    fixture: IntegrationFixture
    axis: np.ndarray
    witness_indices: tuple[tuple[int, ...], tuple[int, ...]]
    initial_gap_m: float
    target_gap_m: float
    tolerance_m: float

    def request(self):
        arguments = {"task": "close_gap", "target_gap_m": self.target_gap_m, "tolerance_m": self.tolerance_m}
        if self.case.image_mode is not None:
            arguments["image_mode"] = self.case.image_mode
        return arguments


_CASES = (
    TaskCase("D01", "dense-nonconvex", "I-open-tip-0", 0.5, 2),
    TaskCase("D02", "dense-nonconvex", "I-open-tip-2", 0.375, 3, witness="edge-edge"),
    TaskCase("D03", "dense-nonconvex", "I-single-panel-0", 0.25, 3, witness="vertex-face"),
    TaskCase("D04", "dense-nonconvex", "I-staggered-wings-2", 0.75, 2),
    TaskCase("T01", "transformed", "I-open-tip-1", 0.5),
    TaskCase("T02", "transformed", "I-single-panel-1", 0.25),
    TaskCase("T03", "transformed", "I-staggered-wings-3", 0.75),
    TaskCase("T04", "transformed", "I-nested-drums-3", 0.375),
    TaskCase("V01", "occluded-visual", "I-single-panel-2", 0.5, image_mode="SECTION"),
    TaskCase("V02", "occluded-visual", "I-staggered-wings-0", 0.625, image_mode="NATURAL"),
    TaskCase("V03", "occluded-visual", "I-slotted-drum-0", 0.375, image_mode="NATURAL"),
    TaskCase("V04", "occluded-visual", "I-nested-drums-2", 0.25, image_mode="SECTION"),
    TaskCase("C01", "control", "I-open-tip-0", 0.75),
    TaskCase("C02", "control", "I-open-tip-2", 1.0),
)


def case_manifest():
    return _CASES


def _refine_tip(vertices, faces, levels):
    points = [point.copy() for point in vertices]
    # The fixed tip recipe orders the twelve rear vertices after two full rings.
    rear = np.arange(25, 37)
    center = vertices[rear].mean(axis=0)
    for index in rear[::2]:
        points[index] = (points[index] + center) / 2
    # A center fan stays inside the dented star-shaped rear boundary.
    center_index = len(points)
    points.append(center)
    if faces[-10][1] > faces[-10][2]:
        rear = rear[::-1]
    faces = list(faces[:-10]) + [(center_index, a, b) for a, b in zip(rear, np.roll(rear, -1))]
    for _ in range(levels):
        midpoints = {}

        def split(a, b):
            edge = (min(a, b), max(a, b))
            if edge not in midpoints:
                midpoints[edge] = len(points)
                points.append((points[a] + points[b]) / 2)
            return midpoints[edge]

        refined = []
        for a, b, c in faces:
            ab, bc, ca = split(a, b), split(b, c), split(c, a)
            refined.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
        faces = refined
    return np.asarray(points), np.asarray(faces, dtype=np.int32)


_EDGE_A = ((0., -.32, 0.), (0., .43, 0.), (.20, .02, .31), (.20, .10, -.33))
_EDGE_B = ((0., 0., -.37), (0., 0., .53), (.20, -.31, .05), (.20, .31, .05))
_FACE_B = ((0., -.43, -.29), (0., .54, -.20), (0., .08, .58), (.20, 0., 0.))


def _support_lobe(mesh, matrix, anchor, basis, gap, coordinates, support_size):
    """Add a closed support feature in front of the dense rear component."""
    basis = np.asarray(basis)
    linear = matrix[:3, :3]
    lobe_world = anchor + gap * (np.asarray(coordinates) @ basis)
    lobe_local = np.linalg.solve(linear, (lobe_world - matrix[:3, 3]).T).T
    shifted = mesh.vertices_local_m + np.linalg.solve(linear, .32 * gap * basis[0])
    tetra = np.asarray(((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)))
    if np.linalg.det(lobe_local[1:] - lobe_local[0]) < 0:
        tetra = tetra[:, ::-1]
    offset = len(shifted)
    supported = replace(mesh, vertices_local_m=np.vstack((shifted, lobe_local)),
                        triangles=np.vstack((mesh.triangles, offset + tetra)).astype(np.int32))
    return supported, tuple(range(offset, offset + support_size))


def build_episode(case):
    """Return scene inputs, plus evaluator-only axis and numeric expectations."""
    spec = next(spec for spec in fixture_manifest() if spec.case_id == case.source_id)
    original = build_fixture(spec)
    meshes = []
    for mesh in original.meshes:
        vertices, triangles = mesh.vertices_local_m, mesh.triangles
        if mesh.shape_basis_local_m is not None:
            vertices = vertices + original.command.control_before * mesh.shape_basis_local_m
        if case.subdivisions and mesh.object_id in original.target_ids:
            vertices, triangles = _refine_tip(vertices, triangles, case.subdivisions)
        meshes.append(replace(mesh, vertices_local_m=vertices, triangles=triangles,
                              shape_basis_local_m=None, shape_relative_local_m=None))

    parent_matrices = {parent.object_id: parent.local_matrix_m for parent in original.parents}
    endpoints = []
    matrices = []
    for mesh in meshes[:2]:
        matrix = mesh.local_matrix_m
        if mesh.parent_id is not None:
            matrix = parent_matrices[mesh.parent_id] @ matrix
        matrices.append(matrix)
        endpoints.append(matrix[:3, :3] @ mesh.vertices_local_m[0] + matrix[:3, 3])
    axis = endpoints[1] - endpoints[0]
    axis /= np.linalg.norm(axis)
    supports = [(0,), (0,)]
    if case.witness != "tip-tip":
        transverse = np.eye(3)[np.argmin(np.abs(axis))]
        across = np.cross(axis, transverse)
        across /= np.linalg.norm(across)
        vertical = np.cross(axis, across)
        if case.witness == "edge-edge":
            meshes[0], supports[0] = _support_lobe(meshes[0], matrices[0], endpoints[0],
                                                 (-axis, across, vertical), spec.gap_m, _EDGE_A, 2)
        coordinates, size = (_EDGE_B, 2) if case.witness == "edge-edge" else (_FACE_B, 3)
        meshes[1], supports[1] = _support_lobe(meshes[1], matrices[1], endpoints[1],
                                             (axis, across, vertical), spec.gap_m, coordinates, size)
    target = case.target_fraction * spec.gap_m
    fixture = replace(original, spec=replace(spec, command_kind=None), meshes=tuple(meshes),
                      command=None, followup_command=None, goal_distance_m=target,
                      expected_after_m=target, expected_followup_gap_m=None,
                      action_supported_for_prediction=False)
    return PreparedEpisode(case, fixture, axis, tuple(supports), spec.gap_m, target, fixture.host_tolerance_m)


def _gap_interval(episode, moving, reference):
    """Bound the true surface gap from actual evaluated supports and features."""
    left, right = episode.witness_indices
    origin = moving[left[0]]
    projection_a = (moving - origin) @ episode.axis
    projection_b = (reference - origin) @ episode.axis
    plane_a = float(np.max(projection_a))
    plane_b = float(np.min(projection_b))
    lower = max(0., plane_b - plane_a)
    if episode.case.witness != "tip-tip":
        margin = episode.tolerance_m / 4
        np.testing.assert_array_equal(np.flatnonzero(plane_a - projection_a <= margin), left)
        np.testing.assert_array_equal(np.flatnonzero(projection_b - plane_b <= margin), right)

    a, b = moving[list(left)], reference[list(right)]
    directions = np.concatenate(((a[1:] - a[0]).T, (b[0] - b[1:]).T), axis=1)
    coefficients, _, rank, _ = np.linalg.lstsq(directions, b[0] - a[0], rcond=None)
    if rank != len(coefficients):
        raise AssertionError("The registered witness features do not determine a unique closest pair")
    t, u = np.split(coefficients, [len(a) - 1])
    wa, wb = np.r_[1 - t.sum(), t], np.r_[1 - u.sum(), u]
    if min(wa.min(), wb.min()) <= .05:
        raise AssertionError("The actual closest affine points are outside the registered interiors")
    upper = float(np.linalg.norm(wa @ a - wb @ b))
    coordinate_scale = max(float(np.max(np.abs(moving))), float(np.max(np.abs(reference))))
    roundoff = 64 * np.finfo(float).eps * coordinate_scale
    lower, upper = max(0., lower - roundoff), upper + roundoff
    if lower > upper:
        raise AssertionError(("inconsistent numeric gap interval", lower, upper))
    return (lower, upper), (wa.tolist(), wb.tolist())


def _check_writes(episode, arm, writes):
    if arm not in ("I", "N") or type(writes) is not int or writes < 0:
        raise AssertionError(("invalid write audit", arm, writes))
    if episode.case.target_fraction == 1.:
        allowed = writes == 0
    elif arm == "I":
        allowed = writes == 1
    else:
        allowed = writes >= 1
    if not allowed:
        raise AssertionError(("writes", episode.case.case_id, arm, writes))


def native_surface_pair(vertices_a, triangles_a, vertices_b, triangles_b):
    """Generic native seed helper over evaluated triangle meshes, with no case hints.

    AABB lower bounds prune face pairs. The independent convex-hull primitive
    solves remaining pairs, including edge/face interiors and degenerate faces.
    The eventual native adapter may replace this with a faster generic method.
    """
    a = np.asarray(vertices_a, dtype=float)[np.asarray(triangles_a, dtype=np.intp)]
    b = np.asarray(vertices_b, dtype=float)[np.asarray(triangles_b, dtype=np.intp)]
    if not len(a) or not len(b):
        return None
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("The evaluated mesh coordinates must be finite")
    low_b, high_b = b.min(axis=1), b.max(axis=1)
    b_vertices = b.reshape(-1, 3)
    first = a[0, 0]
    right = b_vertices[np.argmin(np.linalg.norm(b_vertices - first, axis=1))]
    best = float(np.linalg.norm(right - first)), first, right
    scale = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))), np.finfo(float).tiny)
    roundoff = 64 * np.finfo(float).eps * scale
    for face, low_a, high_a in zip(a, a.min(axis=1), a.max(axis=1)):
        separation = np.maximum(np.maximum(low_a - high_b, low_b - high_a), 0.)
        lower = np.linalg.norm(separation, axis=1)
        eligible = np.flatnonzero(lower <= best[0] + roundoff)
        for index in eligible[np.argsort(lower[eligible], kind="stable")]:
            if lower[index] > best[0] + roundoff:
                break
            candidate = convex_pair_oracle(face, b[index])
            if candidate[0] < best[0]:
                best = candidate
    return best


def check_numeric(episode, before, after, result, *, arm, writes):
    """Assert geometric completion using actual evaluated vertices and matrices.

    Each snapshot maps mesh/parent IDs to matrix_world_bu, plus world_vertices_m
    and triangles for each mesh. `result` is the arm's normalized public receipt.
    `arm` is I (candidate) or N (native). `writes` is the independently recorded
    number of moving-object writes. Check unrequested intermediate writes with
    the separate audit, since endpoint snapshots cannot detect reverted writes.
    """
    fixture = episode.fixture
    moving, reference = fixture.target_ids
    tolerance = episode.tolerance_m
    scale = fixture.scale_length
    keys = {item.object_id for item in (*fixture.meshes, *fixture.parents)}
    if set(before) != keys or set(after) != keys:
        raise AssertionError("Snapshot must include exactly the registered objects and parents")

    translation = (episode.initial_gap_m - episode.target_gap_m) * episode.axis
    _check_writes(episode, arm, writes)
    for key in keys:
        matrix_before = np.asarray(before[key]["matrix_world_bu"], dtype=float)
        matrix_after = np.asarray(after[key]["matrix_world_bu"], dtype=float)
        if any(matrix.shape != (4, 4) or not np.isfinite(matrix).all()
               for matrix in (matrix_before, matrix_after)):
            raise AssertionError(("invalid evaluated matrix", key))
        expected_translation = translation if key == moving else np.zeros(3)
        np.testing.assert_allclose(matrix_after[:3, :3], matrix_before[:3, :3],
                                   atol=64 * np.finfo(np.float32).eps, rtol=0)
        np.testing.assert_allclose((matrix_after[:3, 3] - matrix_before[:3, 3]) * scale,
                                   expected_translation, atol=tolerance, rtol=0)
    for mesh in fixture.meshes:
        key = mesh.object_id
        old, new = before[key], after[key]
        np.testing.assert_array_equal(new["triangles"], old["triangles"])
        old_vertices = np.asarray(old["world_vertices_m"], dtype=float)
        new_vertices = np.asarray(new["world_vertices_m"], dtype=float)
        if any(vertices.shape != mesh.vertices_local_m.shape or not np.isfinite(vertices).all()
               for vertices in (old_vertices, new_vertices)):
            raise AssertionError(("invalid evaluated vertices", key))
        if key in fixture.target_ids:
            indices = episode.witness_indices[fixture.target_ids.index(key)]
            triangles = np.asarray(old["triangles"])
            if not np.logical_and.reduce([np.any(triangles == index, axis=1) for index in indices]).any():
                raise AssertionError(("witness feature is not part of the evaluated surface", key, indices))
        displacement = new_vertices - old_vertices
        expected = translation if key == moving else np.zeros(3)
        np.testing.assert_allclose(displacement, np.broadcast_to(expected, displacement.shape), atol=tolerance, rtol=0)

    intervals, barycentric = [], []
    for snapshot, expected in ((before, episode.initial_gap_m), (after, episode.target_gap_m)):
        vertices_a = np.asarray(snapshot[moving]["world_vertices_m"], dtype=float)
        vertices_b = np.asarray(snapshot[reference]["world_vertices_m"], dtype=float)
        interval, weights = _gap_interval(episode, vertices_a, vertices_b)
        np.testing.assert_allclose(interval, (expected, expected), atol=tolerance, rtol=0)
        intervals.append(interval)
        barycentric.append(weights)

    if (result["moving_id"], result["reference_id"], result["unit"]) != (moving, reference, "m"):
        raise AssertionError("Wrong objects or units in the receipt")
    np.testing.assert_allclose((result["target_gap_m"], result["tolerance_m"]),
                               (episode.target_gap_m, tolerance), atol=0, rtol=1e-12)
    if result["goal_reached"] is not True or result["write_status"] != ("written" if writes else "not_written"):
        raise AssertionError("Receipt does not reflect actual task completion and write status")
    np.testing.assert_allclose(result["before_gap_m"], intervals[0], atol=tolerance, rtol=0)
    measured_after = result["after_gap_m"] if writes else result["before_gap_m"]
    np.testing.assert_allclose(measured_after, intervals[1], atol=tolerance, rtol=0)
    error_m = abs(measured_after - episode.target_gap_m)
    if error_m > tolerance:
        raise AssertionError(("reported measurement is outside tolerance", error_m, tolerance))
    np.testing.assert_allclose(result["error_m"], error_m, atol=tolerance / 1000, rtol=0)
    if writes:
        np.testing.assert_allclose(result["actual_delta_world_m"], translation, atol=tolerance, rtol=0)
    return {"before_gap_interval_m": intervals[0], "after_gap_interval_m": intervals[1],
            "before_witness_barycentric": barycentric[0], "after_witness_barycentric": barycentric[1]}


def main():
    document = []
    for case in case_manifest():
        episode = build_episode(case)
        document.append({**asdict(case), "initial_gap_m": episode.initial_gap_m,
                         "request": episode.request(), "scale_length": episode.fixture.scale_length,
                         "triangle_counts": {mesh.object_id: len(mesh.triangles) for mesh in episode.fixture.meshes}})
    print(json.dumps(document, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
