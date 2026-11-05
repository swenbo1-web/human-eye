"""Reproduce concrete counterexamples in the supplied Radical V1 specification.

Only five reviewed function/class ASTs are compiled. Module imports, initializers,
the Blender branch and the specification's macro entry point are never executed.
The AST hashes pin that reviewed code; this is an audit tool, not engine policy.
Run: python -B verification/review_radical_spec.py [--spec PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_fast.kernels import deformation_metrics, prepare_reference

REVIEWED_FUNCTIONS = {
    "_closest_point_on_triangles_vectorized":
        "834a87ce29612aa7bb55e8e1846af989352d1d0a8bea666832cb3111df0549be",
    "compute_cross_frame_deformation_tensor":
        "6ef790e835929de26be149972106786bd1ec3363b801fee9a8082c236313a276",
    "FlashCerebellarCell":
        "55569b821c5db54e2efa1711c046b9d46d3c5e2aafc6644a6f091881e3af0581",
    "_build_orthogonal_basis":
        "095659779bb3375f5404f5b04c0527f903ea49d5c2f638bcff0364694d6f2361",
    "solve_saccade_and_render_dual_hud":
        "0251bf84b094cbdf7900f11f1a0cec0753a8ec1a13996e3425b892e51c1762bd",
}


def reviewed_functions(source):
    functions, locations = {}, {}
    namespace = {"np": np}
    for block in re.finditer(r"```python\n(.*?)```", source, re.S):
        first_line = source[:block.start(1)].count("\n")
        for node in ast.parse(block.group(1)).body:
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)) or node.name not in REVIEWED_FUNCTIONS:
                continue
            digest = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
            if digest != REVIEWED_FUNCTIONS[node.name] or node.name in functions:
                raise ValueError(f"Function differs from reviewed AST: {node.name}")
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, "<reviewed-spec-function>", "exec"), namespace)
            functions[node.name] = namespace[node.name]
            locations[node.name] = {
                "first_line": first_line + node.lineno,
                "last_line": first_line + node.end_lineno,
                "ast_sha256": digest,
            }
    if set(functions) != set(REVIEWED_FUNCTIONS):
        raise ValueError("The specification must contain all reviewed function/class ASTs")
    return functions, locations


def independent_point_triangle(point, triangle):
    """Interior plane projection plus all three closed edges, for these fixtures."""
    origin, one, two = triangle
    basis = np.column_stack((one - origin, two - origin))
    uv = np.linalg.solve(basis.T @ basis, basis.T @ (point - origin))
    candidates = []
    if uv[0] >= 0 and uv[1] >= 0 and uv.sum() <= 1:
        candidates.append(origin + basis @ uv)
    for a, b in ((origin, one), (one, two), (two, origin)):
        edge = b - a
        fraction = np.clip(np.dot(point - a, edge) / np.dot(edge, edge), 0, 1)
        candidates.append(a + fraction * edge)
    candidates = np.array(candidates)
    index = np.argmin(np.linalg.norm(candidates - point, axis=1))
    return candidates[index], float(np.linalg.norm(candidates[index] - point))


def source_lines(source, text):
    return [i for i, line in enumerate(source.splitlines(), 1) if text in line]


def review(spec):
    raw = spec.read_bytes()
    source = raw.decode("utf-8-sig").replace("\r\n", "\n")
    functions, locations = reviewed_functions(source)
    point_kernel = functions["_closest_point_on_triangles_vectorized"]
    deformation = functions["compute_cross_frame_deformation_tensor"]

    triangle = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0]])
    point = np.array([2., 2, 1])
    actual_projection, actual_distance, _ = point_kernel(
        point, triangle[None, 0], triangle[None, 1], triangle[None, 2])
    expected_projection, expected_distance = independent_point_triangle(point, triangle)
    assert np.allclose(expected_projection, [.5, .5, 0])
    assert np.isclose(expected_distance, np.sqrt(5.5))
    assert np.isclose(actual_distance, 1.)
    projection_case = {
        "id": "point_projection_outside_triangle",
        "input": {"point": point.tolist(), "triangle": triangle.tolist()},
        "actual": {"projection": actual_projection.tolist(), "distance": actual_distance},
        "expected": {"projection": expected_projection.tolist(), "distance": expected_distance},
        "reason": "Outside plane projection remains closer than every edge and is never excluded.",
        "evidence_lines": source_lines(source, "proj = v0 + ab * v[:, None] + ac * w[:, None]"),
    }

    faces = np.array([[0, 1, 2]])
    reference = np.array([[-1., -1, 0], [1, -1, 0], [0, 2, 0]])
    cases = [projection_case]
    for name, transform, expected_stretches in (
        ("area_preserving_anisotropic_stretch", [2., .5, 1.], [2., .5]),
        ("rigid_rotation_reported_as_flip", [1., -1., -1.], [1., 1.]),
    ):
        current = reference * transform
        observed = deformation(np.stack((reference, current)), faces)
        fast = deformation_metrics(prepare_reference(reference, faces), current)
        assert np.allclose(fast["stretches"][0], expected_stretches)
        assert np.isclose(observed["witness_max_area_strain"][0], 0.)
        cases.append({
            "id": name,
            "input": {"reference": reference.tolist(), "diagonal_transform": transform},
            "actual": {
                "spec_area_strain": observed["witness_max_area_strain"].tolist(),
                "spec_normal_degrees": observed["witness_max_normal_deg"].tolist(),
                "spec_displacement_m": observed["witness_max_disp_m"].tolist(),
                "spec_flipped_faces": observed["flipped_face_ids"].tolist(),
            },
            "expected": {"principal_stretches": expected_stretches, "area_ratio": 1.,
                         "rigid_motion": name == "rigid_rotation_reported_as_flip"},
            "existing_fast_kernel": {"stretches": fast["stretches"].tolist(),
                                     "area_ratio": fast["area_ratio"].tolist()},
            "reason": ("Area and normal alone miss compensating stretch/compression."
                       if name == "area_preserving_anisotropic_stretch" else
                       "Normal rotation relative to a world reference does not establish intrinsic inversion."),
            "evidence_lines": source_lines(source, "max_area_strain =") +
                              source_lines(source, '"flipped_face_ids":'),
        })
    assert cases[1]["actual"]["spec_normal_degrees"] == [0.]
    assert cases[1]["actual"]["spec_displacement_m"] == [0.]
    assert cases[2]["actual"]["spec_flipped_faces"] == [0]

    # Both triangles have a point with the same x,y at z=0 and z=1. Since all
    # points of B have z>=1, these edge-interior witnesses attain the lower bound.
    a = np.array([[-1., 0, 0], [1, 0, 0], [0, -.1, 0]])
    b = np.array([[.9, -1, 1], [.9, 1, 1], [.9, 0, 2]])
    probes_a = np.vstack((a, a.mean(axis=0)))
    probes_b = np.vstack((b, b.mean(axis=0)))
    sampled_distance = min(
        [independent_point_triangle(p, b)[1] for p in probes_a] +
        [independent_point_triangle(p, a)[1] for p in probes_b])
    assert np.isclose(sampled_distance, np.sqrt(1.01))
    cases.append({
        "id": "vertex_and_centroid_probes_miss_edge_edge_minimum",
        "execution": "Analytic reconstruction of the documented probe set; Blender is not executed.",
        "input": {"triangle_a": a.tolist(), "triangle_b": b.tolist()},
        "actual": {"best_distance_over_all_documented_probes": sampled_distance},
        "expected": {"distance": 1., "witness_a": [.9, 0, 0], "witness_b": [.9, 0, 1]},
        "reason": "The global closest pair lies in the interiors of two edges; vertex/centroid sampling omits it.",
        "evidence_lines": source_lines(source, "probes_a = np.vstack") +
                          source_lines(source, "probes_b = np.vstack"),
    })

    cell = functions["FlashCerebellarCell"](seed=42)
    fingerprint = np.arange(1, 33, dtype=np.float32)
    prior = cell.infer_prior(fingerprint)
    predicted_before = prior["expected_delta_clearance_m"]
    cell.climbing_fiber_update(prior, best_angle_rad=0., best_tilt_rad=0.,
                               actual_delta_clearance_m=123., lr=0.)
    recalled = cell.infer_prior(fingerprint)
    assert cell.bank_vals[0, 5] == 123.
    assert recalled["memory_bank_similarity"] > .85
    assert recalled["expected_delta_clearance_m"] == predicted_before
    cases.append({
        "id": "memory_delta_written_to_unread_head_column",
        "input": {"seed": 42, "fingerprint": fingerprint.tolist(),
                  "observed_delta_clearance_m": 123., "learning_rate": 0.},
        "actual": {"prediction_before": predicted_before,
                   "prediction_after_matching_memory_hit": recalled["expected_delta_clearance_m"],
                   "memory_similarity": recalled["memory_bank_similarity"],
                   "stored_value_column_5": float(cell.bank_vals[0, 5])},
        "expected": "Head C prediction reads the observed delta from a matching memory record; current retrieval only blends output columns 0:6.",
        "reason": "Disabling weight learning isolates recall: stored delta enters out[5], while prediction reads out[25].",
        "evidence_lines": source_lines(source, "out[:6] =") +
                          source_lines(source, '"expected_delta_clearance_m":') +
                          source_lines(source, "self.bank_vals[idx, 5] ="),
    })

    hud = functions["solve_saccade_and_render_dual_hud"](
        triangle, faces, (1., 0., 0.), triangle, faces, (0., 1., 0.),
        clearance_info={"witness_midpoint_m": np.zeros(3),
                        "witness_delta_m": np.array([.001, 0., 0.]),
                        "signed_clearance_m": .001},
        cerebellar_prior=prior, render_pixels=True)
    assert set(hud) == {"hud_resolution", "left_panel_panorama", "right_panel_witness_closeup"}
    cases.append({
        "id": "render_pixels_true_returns_only_configuration",
        "input": {"render_pixels": True, "gap_m": .001, "occluder_count": 0},
        "actual": {"returned_keys": sorted(hud), "output": hud,
                   "raster_or_gpu_image_handle_returned": False},
        "expected": "The claimed rendered HUD requires image data or a usable GPU image handle; camera configuration alone does not render it.",
        "reason": "The reviewed function neither renders pixels nor uses render_pixels; its return value contains only configuration.",
        "evidence_lines": source_lines(source, "render_pixels: bool = True") +
                          source_lines(source, '"hud_resolution": (1024, 512)'),
    })
    return {
        "schema": "human-eye-radical-spec-review-v1",
        "source": {"path": str(spec.resolve()), "sha256": hashlib.sha256(raw).hexdigest()},
        "reviewed_functions": locations,
        "numpy_version": np.__version__,
        "counterexample_count": len(cases),
        "cases": cases,
        "scope": "Numerical and source-code behavior counterexamples; no end-to-end timing, Blender execution, actual GPU rendering or learned-prior quality evaluation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=ROOT / "docs" / "RADICAL_V1_SOURCE_SPEC.md")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(review(args.spec), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
