"""One frozen multi-ROI, multi-center dent matrix, retaining all outcomes."""

from pathlib import Path
import json
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write, identity
import numpy as np
from scipy.sparse.csgraph import dijkstra
from geometry import mesh_geometry, select_rois, select_centers


def bitwise_equal(left, right):
    return left.dtype == right.dtype and left.shape == right.shape and left.tobytes() == right.tobytes()


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "DATASET_INDEX.json").exists() or (HERE / "private/generation_attempts.jsonl").exists():
        raise RuntimeError("matrix_already_attempted_inspect_before_recovery")
    plan, sources, orientations = read("PLAN.json"), read("SOURCE_INDEX.json")["meshes"], read("ORIENTATION_SOURCE.json")["cases"]
    orientation = {row["source_id"]: row for row in orientations}
    for directory in ("inputs", "supervision", "regions"):
        (HERE / "private" / directory).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(plan["seed"])
    dataset = dict(cycle_id=plan["cycle_id"], sources=sources, rois=[], observations=[], pairs=[], attempts=[], missing=[],
                   status="running_single_frozen_matrix", training=0, model_forwards=0, repair_outputs=0)
    attempts_path = HERE / "private/generation_attempts.jsonl"
    for source in sources:
        with np.load(HERE / source["array_path"]) as data:
            arrays = dict(data)
        vertices, faces = arrays["vertices"], arrays["faces"]
        geometry = mesh_geometry(**arrays)
        patch_sizes = geometry["stats"]["orientation_patches"]
        confirmed_patch = orientation[source["id"]]["patch"]
        component_stats = {row["component"]: row for row in geometry["stats"]["components"]}
        selected_rois = select_rois(geometry, rng, plan["roi"]["target_vertices"])
        if len(selected_rois) < plan["roi"]["per_posture"]:
            dataset["missing"].append(dict(source_id=source["id"], missing_roi_slots=plan["roi"]["per_posture"]-len(selected_rois),
                                           reason="no_eligible_uncovered_source_region", replacement_attempts=0))
        for selected in selected_rois:
            source_ids, slot = selected["source_ids"], selected["slot"]
            roi_id = source["id"] + "_roi" + str(slot)
            mapping = "private/regions/" + roi_id + ".npy"
            np.save(HERE / mapping, source_ids.astype(np.int32), allow_pickle=False)
            selection = select_centers(geometry, source_ids)
            centers = selection["centers"]
            inside = np.zeros(len(vertices), dtype=bool)
            inside[source_ids] = True
            roi = dict(id=roi_id, source_id=source["id"], mesh_id=source["asset"], pose_id=source["id"], group=source["group"], split=source["split"],
                       region_mapping=mapping, mapping_identity=identity(HERE / mapping), points=len(source_ids), shortfall=selected["shortfall"],
                       seed_source_id=selected["seed"], centers=centers, center_shortfall=4-len(centers), boundary_count=len(selection["boundary_ids"]),
                       center_selection_reason=selection["reason"], source_boundary_or_nonmanifold_vertices_in_F=int(np.isin(source_ids, geometry["boundary_vertices"]).sum()),
                       source_geometry=geometry["stats"], usable_for_training=False)
            dataset["rois"].append(roi)
            normal_id = roi_id + "_normal"
            normal_positions = "private/inputs/" + normal_id + ".npz"
            normal_supervision = "private/supervision/" + normal_id + ".npz"
            np.savez_compressed(HERE / normal_positions, positions=vertices[source_ids])
            np.savez_compressed(HERE / normal_supervision, normal_positions=vertices[source_ids], actual_delta=np.zeros((len(source_ids),3)),
                                changed_mask=np.zeros(len(source_ids), dtype=bool), displacement_norm=np.zeros(len(source_ids)))
            common = dict(mesh_id=source["asset"], source_id=source["id"], pose_id=source["id"], group=source["group"], split=source["split"], roi_id=roi_id)
            normal = dict(common, id=normal_id, state="normal", input=dict(base_mesh=source["array_path"], region_mapping=mapping, current_local_positions=normal_positions),
                          supervision=normal_supervision, numerical_valid=True, usable_for_training=False,
                          labels="synthetic displacement zero including natural concavities")
            dataset["observations"].append(normal)
            for center in centers:
                center_id = center["source_id"]
                distances = dijkstra(geometry["graph"], directed=False, indices=center_id)
                component = component_stats[int(geometry["component"][center_id])]
                outward_sign = component["volume_outward_sign"]
                if outward_sign is None:
                    outward_sign = orientation[source["id"]]["outward_sign"]
                if outward_sign not in (-1, 1):
                    raise ValueError("source_outward_sign_unconfirmed")
                center_normal = geometry["normals"][center_id] * outward_sign
                center["outward_normal"] = center_normal.tolist()
                center["source_component"] = component["component"]
                for radius_index, radius_fraction in enumerate(plan["matrix"]["radius_over_D"]):
                    radius = radius_fraction * center["D"]
                    support_ideal = np.flatnonzero(distances < radius)
                    for depth_index, depth_fraction in enumerate(plan["matrix"]["depth_over_radius"]):
                        depth = radius * depth_fraction
                        combo = "c" + str(center["slot"]) + "_r" + str(radius_index) + "_a" + str(depth_index)
                        damaged_id = roi_id + "_" + combo
                        attempt = dict(id=damaged_id, source_id=source["id"], roi_id=roi_id, combo_id=combo, status="started")
                        with attempts_path.open("a", encoding="utf8", newline="\n") as log:
                            log.write(json.dumps(attempt) + "\n")
                        current = vertices.copy()
                        profile = (1 - (distances[support_ideal] / radius)**2)**2
                        requested = -depth * profile[:, None] * center_normal
                        local_current = current[support_ideal].copy()
                        nonzero = requested != 0
                        local_current[nonzero] = local_current[nonzero] + requested[nonzero]
                        current[support_ideal] = local_current
                        actual = current - vertices
                        changed = np.any(actual != 0, axis=1)
                        support = np.flatnonzero(changed)
                        affected_faces = np.any(changed[faces], axis=1)
                        cross = np.cross(current[faces[:,1]] - current[faces[:,0]], current[faces[:,2]] - current[faces[:,0]])
                        degenerate = np.linalg.norm(cross, axis=1) <= geometry["stats"]["cross_norm_tolerance"]
                        new_degenerate = degenerate & ~geometry["degenerate"]
                        reversed_faces = (np.einsum("ij,ij->i", cross, geometry["cross"]) <= 0) & ~geometry["degenerate"]
                        affected_patches = np.unique(geometry["face_patch"][affected_faces])
                        if component["closed_consistent"] and component["volume_outward_sign"] is not None:
                            direction, direction_basis = True, "closed_consistent_component_signed_volume"
                        else:
                            direction = bool(len(affected_patches) and np.all(affected_patches == confirmed_patch))
                            direction_basis = "visual_source_orientation_same_consistent_patch" if direction else "unknown_unanchored_or_multiple_patches"
                        full_reconstruction = vertices.copy()
                        full_reconstruction[source_ids] = current[source_ids]
                        checks = dict(finite=bool(np.isfinite(current).all()), support_minimum=len(support) >= plan["matrix"]["minimum_true_support"],
                                      support_inside_F=bool(inside[support].all()), no_new_degeneracy=not new_degenerate.any(),
                                      no_face_reversal=not reversed_faces.any(), range_bitwise=bitwise_equal(current[~changed], vertices[~changed]),
                                      outside_ideal_support_bitwise=bitwise_equal(current[distances >= radius], vertices[distances >= radius]),
                                      exact_compact_reconstruction=bitwise_equal(current, full_reconstruction))
                        numerical = all(checks.values())
                        positions_path = "private/inputs/" + damaged_id + ".npz"
                        supervision_path = "private/supervision/" + damaged_id + ".npz"
                        np.savez_compressed(HERE / positions_path, positions=current[source_ids])
                        delta_F = actual[source_ids]
                        np.savez_compressed(HERE / supervision_path, actual_delta=delta_F, changed_mask=changed[source_ids],
                                            displacement_norm=np.linalg.norm(delta_F, axis=1), normal_positions=vertices[source_ids])
                        encoder_radius = .05 * source["bbox_diagonal"]
                        neighborhood = np.linalg.norm(vertices - vertices[center_id], axis=1) < encoder_radius
                        observation = dict(common, id=damaged_id, state="damaged", combo_id=combo, center_slot=center["slot"], center_source_id=center_id,
                            radius_index=radius_index, depth_index=depth_index, radius_over_D=radius_fraction, depth_over_radius=depth_fraction,
                            radius=radius, depth=depth, D=center["D"], radius_over_encoder_radius=radius/encoder_radius, depth_over_encoder_radius=depth/encoder_radius,
                            encoder_neighborhood_points=int(neighborhood.sum()), encoder_neighborhood_damaged_points=int((neighborhood & changed).sum()),
                            encoder_neighborhood_damaged_fraction=float((neighborhood & changed).sum()/neighborhood.sum()),
                            true_support_points=len(support), ideal_support_points=len(support_ideal), target_lumped_area=float(geometry["vertex_area"][support].sum()),
                            max_true_displacement=float(np.linalg.norm(actual, axis=1).max()), new_degenerate_faces=int(new_degenerate.sum()), reversed_faces=int(reversed_faces.sum()),
                            direction_confirmed=direction, direction_basis=direction_basis, affected_orientation_patches=affected_patches.tolist(), checks=checks,
                            input=dict(base_mesh=source["array_path"], region_mapping=mapping, current_local_positions=positions_path), supervision=supervision_path,
                            numerical_valid=bool(numerical), usable_for_training=False,
                            failures=[key for key, value in checks.items() if not value] + ([] if direction else ["direction_unknown"]))
                        dataset["observations"].append(observation)
                        pair = dict(common, id=damaged_id + "_pair", combo_id=combo, normal_observation_id=normal_id,
                                    damaged_observation_id=damaged_id, center_source_id=center_id,
                                    candidate_valid=bool(numerical and direction), usable_for_training=False,
                                    region_mapping=mapping, mapping_sha256=roi["mapping_identity"]["sha256"], F_count=len(source_ids))
                        dataset["pairs"].append(pair)
                        attempt.update(status="completed", numerical_valid=bool(numerical), direction_confirmed=direction, failures=observation["failures"])
                        dataset["attempts"].append(attempt)
                        with attempts_path.open("a", encoding="utf8", newline="\n") as log:
                            log.write(json.dumps(attempt) + "\n")
            pairs = [row for row in dataset["pairs"] if row["roi_id"] == roi_id]
            valid_centers = sorted({row["center_source_id"] for row in pairs if row["candidate_valid"]})
            roi["valid_centers"] = valid_centers
            roi["usable_for_training"] = bool(len(source_ids) == 384 and len(valid_centers) >= 2)
            for row in pairs:
                row["usable_for_training"] = roi["usable_for_training"] and row["candidate_valid"]
            usable_dent_ids = {row["damaged_observation_id"] for row in pairs if row["usable_for_training"]}
            normal["usable_for_training"] = roi["usable_for_training"]
            for observation in dataset["observations"]:
                if observation["roi_id"] == roi_id and observation["state"] == "damaged":
                    observation["usable_for_training"] = observation["id"] in usable_dent_ids
            print(roi_id, "points", len(source_ids), "centers", len(centers), "valid_centers", len(valid_centers), "usable_pairs", len(usable_dent_ids), flush=True)
        write("GENERATION_PROGRESS.json", dataset)
    dataset.update(status="completed_single_frozen_matrix", wall_s_before_write=time.perf_counter()-started, cpu_s_before_write=time.process_time()-cpu)
    write("DATASET_INDEX.json", dataset)


if __name__ == "__main__":
    main()
