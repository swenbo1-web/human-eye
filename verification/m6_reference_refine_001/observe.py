"""Verify reference correspondence and the fixed contract uncertainty branch."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from reference_geometry import normalized_coordinates, measure_projected_sections, measure_polyline_sections


def metric_rows(projected, faces, annotation, anchors):
    reference = measure_polyline_sections(annotation["reference_foreground"]["inner_polyline"],
        annotation["reference_foreground"]["outer_polyline"], anchors["reference"]["E"], anchors["reference"]["W"], annotation["stations"])
    model = measure_projected_sections(projected, faces, anchors["model"]["E"], anchors["model"]["W"], annotation["stations"])
    return [dict(t=first["t"], reference_outer=first["outer"], model_outer=second["outer"],
        signed_outer=second["outer"]-first["outer"], reference_inner=first["inner"], model_inner=second["inner"],
        signed_inner=second["inner"]-first["inner"], reference_width=first["width"], model_width=second["width"],
        signed_width=second["width"]-first["width"], outer_source_face=second["outer_source_face"]) for first, second in zip(reference, model)]


def main():
    started, cpu = time.perf_counter(), time.process_time()
    annotation = read("ANNOTATION_DRAFT.json")
    independent = read("INDEPENDENT_ANCHORS.json")
    with np.load(HERE / "private/cases/s01/baseline_readback.npz", allow_pickle=False) as archive:
        arrays = {key:archive[key] for key in archive.files}
    vertices, faces = arrays["vertices"], arrays["faces"]
    projection = annotation["source_projection"]
    projected = vertices @ np.asarray(projection["affine_2_by_3"]).T + np.asarray(projection["offset"])
    primary = dict(reference={key:annotation["anchors"]["reference"][key] for key in ("E", "W")},
        model={key:annotation["anchors"]["model_local"][key] for key in ("E", "W")})
    alternative = dict(reference={key:independent["reference"][key]["pixel_xy"] for key in ("E", "W")},
        model={key:independent["model_front"][key]["pixel_xy"] for key in ("E", "W")})
    rows, alt_rows = (metric_rows(projected, faces, annotation, anchors) for anchors in (primary, alternative))
    for actual, expected in zip(rows, annotation["signed_residual_model_minus_reference"]):
        if abs(actual["signed_outer"]-expected) > 1e-12:
            raise AssertionError("primary_annotation_measurement_changed")
    coordinates = normalized_coordinates(projected, primary["model"]["E"], primary["model"]["W"])
    candidates = (coordinates[:,0] >= -.08) & (coordinates[:,0] <= 1.08) & (np.abs(coordinates[:,1]) <= .4) & (vertices[:,1] > .09)
    edges = np.unique(np.sort(np.concatenate((faces[:,[0,1]], faces[:,[1,2]], faces[:,[2,0]])), axis=1), axis=0)
    edges = edges[candidates[edges].all(axis=1)]
    graph = csr_matrix((np.ones(len(edges)*2), (np.r_[edges[:,0], edges[:,1]], np.r_[edges[:,1], edges[:,0]])), shape=(len(vertices), len(vertices)))
    _, labels = connected_components(graph, directed=False)
    with np.load(HERE / "private/cases/s01/seed.npz", allow_pickle=False) as seed:
        seed_ids = seed["F_source_ids"]
    values, counts = np.unique(labels[seed_ids[candidates[seed_ids]]], return_counts=True)
    chosen = values[np.argmax(counts)]
    F = np.flatnonzero((labels == chosen) & candidates)
    mapping = []
    for row in rows:
        face_id = row["outer_source_face"]
        ids = faces[face_id]
        triangle = coordinates[ids]
        intersections = []
        for first, second in ((0,1), (1,2), (2,0)):
            a, b = triangle[first], triangle[second]
            if min(a[0], b[0]) <= row["t"] <= max(a[0], b[0]) and a[0] != b[0]:
                ratio = (row["t"]-a[0])/(b[0]-a[0])
                weights = np.zeros(3)
                weights[first], weights[second] = 1-ratio, ratio
                intersections.append((float(weights @ triangle[:,1]), weights))
        outer, weights = max(intersections, key=lambda item:item[0])
        point = weights @ vertices[ids]
        if abs(outer-row["model_outer"]) > 1e-10:
            raise AssertionError("outer_station_source_triangle_mapping_mismatch")
        mapping.append(dict(t=row["t"], triangle_row=int(face_id), native_polygon_id=int(arrays["triangle_polygon_ids"][face_id]),
            source_ids=ids.tolist(), barycentric_weights=weights.tolist(), world=point.tolist(), image_pixel=(weights @ projected[ids]).tolist()))
    F = np.union1d(F, np.unique([record["source_ids"] for record in mapping])).astype(np.int64)
    np.savez_compressed(HERE / "private/cases/s01/observation.npz", **arrays, F_source_ids=F,
        I_ids=np.empty(0, dtype=np.int64), protected_ids=np.arange(len(vertices)), projected_pixels=projected, normalized_EW=coordinates)
    write("private/annotation/STATION_SOURCE_MAPPING.json", dict(stations=mapping, F_source_ids=F.tolist(), editable_I=[], protected_source_ids="all27304"))
    lower = np.array(annotation["sensitivity"]["residual_minimum"])
    upper = np.array(annotation["sensitivity"]["residual_maximum"])
    checks = dict(primary_matches_saved_annotation=True, five_sampled_uncertainty_intervals_contain_zero=bool(np.all((lower <= 0)&(upper >= 0))),
        source_mapping_verified=True, model_source_ID_domain=bool(np.array_equal(arrays["source_ids"], np.arange(len(vertices)))))
    destination = HERE / "private/results/corresponding_model.blend"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(HERE / "private/cases/s01/before.blend", destination)
    checks["whole_model_copy_matches_original_SHA"] = identity(destination)["sha256"] == "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
    result = dict(status="correspondence_completed_uncertainty_branch", checks=checks, primary_anchors=primary,
        primary_stations=rows, alternative_anchors=alternative, alternative_stations=alt_rows,
        primary_outer_MAE=float(np.mean([abs(row["signed_outer"]) for row in rows])),
        alternative_outer_MAE=float(np.mean([abs(row["signed_outer"]) for row in alt_rows])),
        uncertainty=dict(sampled_minimum=lower.tolist(), sampled_maximum=upper.tolist(), boundary_pixels=3.,
            interpretation="Finite deterministic sensitivity envelopes from plausible manual landmarks, separate reference/model radius samples and a conservative image-boundary allowance. No statistical confidence claim."),
        observed_source_points=len(F), editable_source_points=0, protected_source_points=len(vertices),
        whole_model=identity(destination), source_mapping=identity(HERE / "private/annotation/STATION_SOURCE_MAPPING.json"),
        source_scope="EW-normalized forearm component overlapping the fixed410-point seed, with full-mesh station intersections mapped to native polygons and source vertices",
        actual_Pro_sessions=0, geometry_edits=0, target_improvement_percent=None,
        execution_branch="Fixed contract permits observation, measurement and correspondence when deviations fall within annotation uncertainty. Current signed edit direction lacks stable support.",
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu)
    write("OBSERVATION.json", result)
    if not all(checks.values()):
        raise AssertionError(str(checks))
    print(result["status"], len(F), result["primary_outer_MAE"], result["alternative_outer_MAE"])


if __name__ == "__main__":
    main()
