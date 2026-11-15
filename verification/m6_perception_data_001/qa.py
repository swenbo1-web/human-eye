"""Rebuild every observation and audit labels, ranges, lineage and coverage."""

from collections import Counter
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write, identity
import numpy as np
from scipy.sparse.csgraph import dijkstra
from data_io import read_current, read_supervision
from geometry import mesh_geometry


def same_bits(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def main():
    started, cpu = time.perf_counter(), time.process_time()
    dataset = read("DATASET_INDEX.json")
    observations = {row["id"]: row for row in dataset["observations"]}
    all_checks, failures, coverage, center_distribution, intersections = [], [], [], [], []
    output = HERE / "private/qa"
    output.mkdir(parents=True, exist_ok=True)

    def check(name, condition, case=None):
        row = dict(name=name, passed=bool(condition), case=case)
        all_checks.append(row)
        if not condition:
            failures.append(row)

    check("six_source_identities_three_disjoint_families", len({r["asset"] for r in dataset["sources"]}) == 6 and len({r["group"] for r in dataset["sources"]}) == 3)
    dev = {r["group"] for r in dataset["sources"] if r["split"] == "development"}
    val = {r["group"] for r in dataset["sources"] if r["split"] == "validation"}
    check("derived_group_leakage_zero", not (dev & val) and dev == {"horse_transfer", "face_transfer"} and val == {"cat_transfer"})
    check("600_observation_cap", len(dataset["observations"]) <= 600)
    check("all_attempts_completed_and_indexed", len(dataset["attempts"]) == len(dataset["pairs"]) and all(r["status"] == "completed" for r in dataset["attempts"]))
    for source in dataset["sources"]:
        with np.load(HERE / source["array_path"]) as arrays:
            source_arrays = dict(arrays)
        vertices, faces = source_arrays["vertices"], source_arrays["faces"]
        geometry = mesh_geometry(**source_arrays)
        frequency, usable_frequency = np.zeros(len(vertices), dtype=np.int32), np.zeros(len(vertices), dtype=np.int32)
        adjacency = geometry["graph"].copy()
        adjacency.data[:] = 1
        degrees = np.asarray(adjacency.sum(axis=1)).ravel()
        neighbor_mean = np.divide(adjacency @ vertices, degrees[:,None], out=vertices.copy(), where=degrees[:,None] > 0)
        offset = np.einsum("ij,ij->i", neighbor_mean - vertices, geometry["normals"])
        tolerance = geometry["stats"]["length_tolerance"]
        concavity = np.where(offset > tolerance, 1, np.where(offset < -tolerance, -1, 0)).astype(np.int8)
        source_rois = [r for r in dataset["rois"] if r["source_id"] == source["id"]]
        mappings = []
        for roi in source_rois:
            ids = np.load(HERE / roi["region_mapping"], allow_pickle=False)
            mappings.append(ids)
            normal = observations[roi["id"] + "_normal"]
            normal_current, normal_truth = read_current(normal), read_supervision(normal)
            check("normal_full_source_bitwise", same_bits(normal_current["vertices"], vertices), normal["id"])
            check("normal_topology_bitwise", same_bits(normal_current["faces"], faces), normal["id"])
            check("normal_natural_concavity_labels_zero", not normal_truth["changed_mask"].any() and not normal_truth["actual_delta"].any(), normal["id"])
            for center in roi["centers"]:
                point = vertices[center["source_id"]]
                center_distribution.append(dict(roi_id=roi["id"], source_id=source["id"], center_source_id=center["source_id"],
                                                normalized_bbox_position=((point-vertices.min(axis=0))/np.maximum(np.ptp(vertices,axis=0),1e-30)).tolist(),
                                                D=center["D"], D_over_bboxdiag=center["D"]/source["bbox_diagonal"]))
            check("used_ROI_has_two_distinct_valid_centers", not roi["usable_for_training"] or len(set(roi["valid_centers"])) >= 2, roi["id"])
            roi_pairs = [p for p in dataset["pairs"] if p["roi_id"] == roi["id"]]
            check("fixed_matrix_attempt_count", len(roi_pairs) == len(roi["centers"])*6, roi["id"])
            for pair in roi_pairs:
                observation = observations[pair["damaged_observation_id"]]
                current, truth = read_current(observation), read_supervision(observation)
                actual = current["vertices"] - vertices
                changed = np.any(actual != 0, axis=1)
                frequency += changed
                if pair["usable_for_training"]:
                    usable_frequency += changed
                allowed = np.zeros(len(vertices), dtype=bool)
                allowed[ids] = True
                distance = dijkstra(geometry["graph"], directed=False, indices=observation["center_source_id"])
                check("pair_same_source_topology_mapping", pair["source_id"] == normal["source_id"] == observation["source_id"] and same_bits(current["faces"], faces)
                      and same_bits(current["region_source_ids"], normal_current["region_source_ids"]), pair["id"])
                check("current_input_whitelist", set(current) == {"vertices","faces","region_source_ids","mesh_id","pose_id"}, pair["id"])
                check("true_labels_exact_delta", same_bits(actual[ids], truth["actual_delta"]) and np.array_equal(changed[ids], truth["changed_mask"])
                      and same_bits(np.linalg.norm(actual[ids],axis=1), truth["displacement_norm"]), pair["id"])
                check("supervision_normal_coords_exact", same_bits(vertices[ids], truth["normal_positions"]), pair["id"])
                check("outside_F_bitwise", same_bits(current["vertices"][~allowed], vertices[~allowed]), pair["id"])
                check("outside_radius_bitwise", same_bits(current["vertices"][distance >= observation["radius"]], vertices[distance >= observation["radius"]]), pair["id"])
                check("outside_true_domain_bitwise", same_bits(current["vertices"][~changed], vertices[~changed]), pair["id"])
                check("support_count_matches", int(changed.sum()) == observation["true_support_points"], pair["id"])
                ideal = distance < observation["radius"]
                center = next(c for c in roi["centers"] if c["source_id"] == observation["center_source_id"])
                expected = vertices.copy()
                ids_ideal = np.flatnonzero(ideal)
                profile = (1-(distance[ideal]/observation["radius"])**2)**2
                delta = -observation["depth"]*profile[:,None]*np.array(center["outward_normal"])
                local = expected[ideal].copy()
                components = delta != 0
                local[components] += delta[components]
                expected[ids_ideal] = local
                check("specified_dent_exact_reconstruction", same_bits(expected, current["vertices"]), pair["id"])
                cross = np.cross(current["vertices"][faces[:,1]]-current["vertices"][faces[:,0]],current["vertices"][faces[:,2]]-current["vertices"][faces[:,0]])
                degenerate = (np.linalg.norm(cross,axis=1) <= geometry["stats"]["cross_norm_tolerance"]) & ~geometry["degenerate"]
                reverse = (np.einsum("ij,ij->i",cross,geometry["cross"]) <= 0) & ~geometry["degenerate"]
                check("new_problem_counts_match", int(degenerate.sum()) == observation["new_degenerate_faces"] and int(reverse.sum()) == observation["reversed_faces"], pair["id"])
                check("usability_matches_fixed_definition", pair["usable_for_training"] == (roi["usable_for_training"] and observation["numerical_valid"] and observation["direction_confirmed"]), pair["id"])
                check("failed_dents_excluded_and_retained", not observation["failures"] or not pair["usable_for_training"], pair["id"])
            categories = {name: int(np.sum(concavity[ids] == value)) for name,value in (("concave",1),("convex",-1),("flat",0))}
            coverage.append(dict(roi_id=roi["id"], source_id=source["id"], F_points=len(ids), natural_shape_counts=categories,
                                 natural_concave_normal_negative_points=categories["concave"], all_normal_points_negative=len(ids)))
        if len(mappings) == 2:
            intersection, union = len(np.intersect1d(*mappings)), len(np.union1d(*mappings))
            intersections.append(dict(source_id=source["id"], intersection_points=intersection, union_points=union, intersection_over_union=intersection/union))
        path = output / (source["id"] + "_frequency.npz")
        np.savez_compressed(path, all_attempt_damage_frequency=frequency, usable_damage_frequency=usable_frequency,
                            source_concavity=concavity, mean_neighbor_offset_dot_normal=offset)
        for row in coverage:
            if row["source_id"] != source["id"]:
                continue
            roi = next(r for r in source_rois if r["id"] == row["roi_id"])
            ids = np.load(HERE / roi["region_mapping"], allow_pickle=False)
            row.update(frequency_file=identity(path), damage_frequency_min=int(frequency[ids].min()),
                       damage_frequency_max=int(frequency[ids].max()), ever_damaged_points=int((frequency[ids]>0).sum()),
                       usable_ever_damaged_points=int((usable_frequency[ids]>0).sum()),
                       natural_concave_ever_damaged_points=int(((concavity[ids] == 1)&(frequency[ids]>0)).sum()))
    usable = [p for p in dataset["pairs"] if p["usable_for_training"]]
    check("all_three_families_have_usable_pairs", {p["group"] for p in usable} == dev | val)
    report = dict(cycle_id=dataset["cycle_id"], status="passed_data_engineering_QA" if not failures else "failed", checks=len(all_checks), failures=failures,
                  actual=dict(sources=6, derived_groups=3, poses=len(dataset["sources"]), rois=len(dataset["rois"]),
                              centers=sum(len(r["centers"]) for r in dataset["rois"]), normal_observations=sum(r["state"]=="normal" for r in dataset["observations"]),
                              damaged_observations=len(dataset["pairs"]), unique_observations=len(observations), usable_pairs=len(usable),
                              failed_dents=len(dataset["pairs"])-len(usable)),
                  usable_pairs_by_group=dict(Counter(p["group"] for p in usable)),
                  usable_pairs_by_split=dict(Counter(p["split"] for p in usable)),
                  failure_reasons=dict(Counter(reason for o in observations.values() for reason in o.get("failures",[]))),
                  failure_observation_ids=[o["id"] for o in observations.values() if o.get("failures")],
                  direction_unknown_dents=sum(o.get("state")=="damaged" and not o["direction_confirmed"] for o in observations.values()),
                  total_new_degenerate_faces=sum(o.get("new_degenerate_faces",0) for o in observations.values()),
                  total_reversed_face_instances=sum(o.get("reversed_faces",0) for o in observations.values()),
                  coverage=coverage, center_distribution=center_distribution, roi_intersections=intersections,
                  limitations=["Local face dot-product reversal measured. Global triangle self-intersection unverified.",
                               "Natural concavity sign is a coverage diagnostic, synthetic normal labels remain zero.",
                               "Open-source direction uses viewed external-surface anchor plus consistent face patch, no closed-solid proof.",
                               "One research corpus, no independent final test, unknown pretraining overlap."],
                  wall_s_before_write=time.perf_counter()-started, cpu_s_before_write=time.process_time()-cpu)
    write("DATA_QA.json", report)
    write("QA_CHECKS.json", dict(checks=all_checks))
    print(report["status"], report["actual"], "check_failures",len(failures), flush=True)


def render_pairs():
    started, cpu = time.perf_counter(), time.process_time()
    from PIL import Image
    from render_views import panel
    dataset = read("DATASET_INDEX.json")
    observations = {row["id"]:row for row in dataset["observations"]}
    directory = HERE / "private/views/pairs"
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for source in dataset["sources"]:
        roi_id = source["id"] + "_roi0"
        roi = next(r for r in dataset["rois"] if r["id"] == roi_id)
        if not roi["centers"]:
            results.append(dict(source_id=source["id"], status="no_fixed_center", roi_id=roi_id))
            continue
        damaged = observations[roi_id + "_c0_r1_a2"]
        normal = observations[roi_id + "_normal"]
        current, undamaged = read_current(damaged), read_current(normal)
        center = roi["centers"][0]
        point = undamaged["vertices"][center["source_id"]]
        outward = np.array(center["outward_normal"])
        faces = undamaged["faces"]
        ids = undamaged["region_source_ids"]
        keep = np.isin(faces, ids).any(axis=1)
        local_faces = faces[keep]
        local_ids, inverse = np.unique(local_faces, return_inverse=True)
        local_faces = inverse.reshape(-1,3)
        reference_vertices = undamaged["vertices"][local_ids]
        damaged_vertices = current["vertices"][local_ids]
        tangent = np.cross(outward, (0,1,0))
        if np.linalg.norm(tangent) < .1:
            tangent = np.cross(outward,(1,0,0))
        tangent /= np.linalg.norm(tangent)
        views = [outward + .35*tangent, tangent + .15*outward]
        colors = np.tile((125,151,173), (len(local_faces),1))
        mask = read_supervision(damaged)["changed_mask"]
        changed_ids = ids[mask]
        colors[np.isin(local_ids[local_faces],changed_ids).any(axis=1)] = (215,134,104)
        image = Image.new("RGB",(1100,840),"white")
        for view_slot, view in enumerate(views):
            extent = None
            for state, vertices in enumerate((reference_vertices,damaged_vertices)):
                arrows = [(point, outward*damaged["radius"]*.7, "+outward", "#245bbb"),
                          (point,-outward*damaged["depth"],"dent", "#d02335")]
                tile, extent = panel(vertices,local_faces,view,size=(550,420),colors=colors,arrows=arrows,
                                      title=source["id"]+ (" normal" if state==0 else " damaged")+" c0 r=.55D a=.30r",extent=extent)
                image.paste(tile,(state*550,view_slot*420))
        path = directory / (source["id"]+".png")
        image.save(path)
        results.append(dict(source_id=source["id"],roi_id=roi_id,normal_observation_id=normal["id"],damaged_observation_id=damaged["id"],
                            usable_pair=damaged["usable_for_training"], image=identity(path), geometry="actual coordinates, same scale within each view pair, orange identifies same planned support faces in both states"))
    write("REPRESENTATIVE_VIEWS.json",dict(cases=results, selection="frozen firstROI firstcenter .55D .30r for every selected posture",
                                          wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))


if __name__ == "__main__":
    main()
