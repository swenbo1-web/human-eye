"""Privately score a completed, byte-identified image/current-mesh correspondence."""

import argparse
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, write
import numpy as np


def score_correspondence(arrays_path, packet_path, target_path, output_path):
    started, cpu = time.perf_counter(), time.process_time()
    if not Path(output_path).resolve().is_relative_to(HERE):
        raise ValueError("private_correspondence_score_output_outside_current_batch")
    frozen = identity(arrays_path)
    with np.load(arrays_path, allow_pickle=False) as archive:
        observed = dict(archive)
    with np.load(packet_path, allow_pickle=False) as archive:
        current = dict(archive)
    frozen_before_private_target_read_epoch = time.time()
    with np.load(target_path, allow_pickle=False) as archive:
        target = dict(archive)
    support, editable, region = target["support_ids"], current["I_ids"], current["F_source_ids"]
    attention = observed["attention"]
    ranked = editable[np.lexsort((editable, -attention[editable]))]
    chosen = observed["active_core_source_ids"]
    true_positive, false_positive = np.intersect1d(chosen, support), np.setdiff1d(chosen, support)
    false_negative = np.setdiff1d(support, chosen)
    vertices, faces = current["vertices_world"], current["faces"]
    triangles = vertices[faces]
    triangle_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) / 2
    lumped = np.zeros(len(vertices))
    for corner in range(3):
        np.add.at(lumped, faces[:, corner], triangle_area / 3)
    visible = np.any(observed["incident_face_visible"], axis=1)
    positive = np.flatnonzero(attention > 0)
    fit_support = observed["fit_support_source_ids"]
    point_recall = len(true_positive) / len(support)
    area_recall = float(lumped[true_positive].sum() / lumped[support].sum())
    checks = dict(fixed_editable_274=len(editable) == 274, fixed_support_47=len(support) == 47,
        fixed_core_budget_69=len(chosen) == 69, stable_attention_ranking=np.array_equal(chosen, ranked[:69]),
        score_shape=attention.shape == (len(vertices),), score_finite_nonnegative=bool(np.isfinite(attention).all() and np.all(attention >= 0)),
        full_mesh_positive_exclusion_identity=np.array_equal(np.sort(observed["positive_attention_source_ids"]), positive),
        fit_support_excludes_all_positive=not np.isin(fit_support, positive).any(),
        fit_support_excludes_active_core=not np.isin(fit_support, chosen).any(),
        fit_support_observable=bool(visible[fit_support].all()),
        point_recall_at_least_80_percent=point_recall >= .8, area_recall_at_least_80_percent=area_recall >= .8,
        array_bytes_unchanged_after_private_scoring=identity(arrays_path) == frozen)
    touches_region = np.isin(faces, region).any(axis=1)
    pixel_denominators = []
    for index, name in enumerate(("forearm_front", "forearm_side", "forearm_45")):
        owners = observed["pixel_center_face_ids"][index]
        mapped = owners >= 0
        changed = observed["pixel_center_energy"][index] > 0
        boundary = observed["pixel_center_boundary"][index]
        pixel_denominators.append(dict(view=name, all_pixels=int(owners.size), mapped_current_mesh_pixels=int(mapped.sum()),
            changed_pixels=int(changed.sum()), changed_mapped_pixels=int((changed & mapped).sum()),
            changed_without_current_mesh_pixels=int((changed & ~mapped).sum()),
            changed_mapped_outside_observation_faces_pixels=int((~touches_region[owners[changed & mapped]]).sum()),
            geometric_boundary_pixels=int(boundary.sum()), changed_geometric_boundary_pixels=int((changed & boundary).sum()),
            geometric_boundary_role="Pixel center near a raster triangle edge. Renderer antialiasing can mix coverage around such boundaries.",
            depth_tie_event_pixels=int(observed["pixel_center_depth_tie_event"][index].sum()),
            multiple_covered_triangle_pixels=int((observed["pixel_center_coverage_count"][index] > 1).sum())))
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", status="pass" if all(checks.values()) else "fail",
        checks={key: bool(value) for key, value in checks.items()}, candidate_budget=69,
        TP=len(true_positive), FP=len(false_positive), FN=len(false_negative),
        precision=len(true_positive) / len(chosen), point_recall=point_recall, area_recall=area_recall,
        denominators=dict(full_source_points=len(vertices), observation_points=len(region), editable_points=len(editable),
            full_support_points=len(support), incident_face_visible_editable_points=int(visible[editable].sum()),
            incident_face_visible_support_points=int(visible[support].sum()), positive_attention_editable_points=int((attention[editable] > 0).sum()),
            positive_attention_full_mesh_points=len(positive), positive_attention_outside_editable_points=len(np.setdiff1d(positive, editable)),
            support_lumped_current_surface_area_m2=float(lumped[support].sum()),
            true_positive_lumped_current_surface_area_m2=float(lumped[true_positive].sum())),
        selected_source_ids=chosen.tolist(), true_positive_source_ids=true_positive.tolist(),
        false_positive_source_ids=false_positive.tolist(), false_negative_source_ids=false_negative.tolist(),
        reference_regions=dict(fit_support_points=len(fit_support), transition_points=len(observed["transition_source_ids"]),
            unobserved_editable_points=len(observed["unobserved_source_ids"]), fit_support_damaged_pollution_points=int(np.isin(fit_support, support).sum())),
        pixel_denominators=pixel_denominators,
        visibility_definition="Incident source triangle has visible pixel-center area; vertex-point visibility has its own ray evidence.",
        scoring_input_frozen_before_private_target_read_epoch=frozen_before_private_target_read_epoch,
        identities=dict(correspondence_arrays=frozen, current_packet=identity(packet_path), private_target=identity(target_path), source=identity(Path(__file__))),
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, actual_Pro_calls=0, actual_Blender_calls=0)
    write(output_path, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arrays", type=Path, default=HERE / "private/correspondence_preflight/baseline/ARRAYS.npz")
    parser.add_argument("--packet", type=Path, default=HERE / "private/cases/repair/initial.npz")
    parser.add_argument("--target", type=Path, default=HERE / "private/scoring/target.npz")
    parser.add_argument("--output", type=Path, default=HERE / "CORRESPONDENCE_SCORE.json")
    args = parser.parse_args()
    result = score_correspondence(args.arrays, args.packet, args.target, args.output)
    print({key: result[key] for key in ("status", "TP", "FP", "FN", "point_recall", "area_recall", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
