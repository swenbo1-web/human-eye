"""Check official preprocessing and a fixed Tetrahedron transfer workflow."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import contextlib
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")


def main():
    timings, checks = {}, []

    @contextlib.contextmanager
    def stage(name):
        wall, cpu = time.perf_counter(), time.process_time()
        yield
        timings[name] = {"wall_s": time.perf_counter() - wall, "CPU_s": time.process_time() - cpu}

    def check(name, passed, **values):
        checks.append({"name": name, "passed": bool(passed), **values})
        if not passed:
            raise ValueError(name)

    with stage("frozen_plan_and_dependency_import"):
        frozen = json.loads((HERE / "PLAN_FREEZE.json").read_bytes())
        for row in frozen["files"]:
            check("frozen_" + row["path"], digest(HERE / row["path"]) == row["sha256"])
        sys.path.insert(0, str(HERE))
        import adapter
        adapter.configure_dependencies()
        import numpy as np
        import scipy.spatial as spatial
        import torch
        import inference
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        source = HERE / "private/pointfilter"
        sys.path.insert(0, str(source))
        from Pointfilter_DataLoader import PointcloudPatchDataset
        pca_alignment = adapter.load_official_pca()

    with stage("checkpoint_load"):
        load_timings = {}
        model = inference.load_model(load_timings)

    def stats(values):
        values = np.asarray(values, dtype=np.float64)
        return {"count": len(values), "RMSE": float(np.sqrt(np.mean(values ** 2))),
                "p95": float(np.percentile(values, 95)), "max": float(np.max(values))}

    data_directory = source / "Dataset/Test"
    pointsets, input_identity = {}, []
    with stage("official_pair_read_and_identity"):
        source_index = json.loads((HERE / "SOURCE_INDEX.json").read_bytes())
        check("pinned_official_source_commit", source_index["commit"]
              == "6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2")
        upstream = {row["upstream_path"]: row for row in source_index["files"]}
        for stem in ("Tetrahedron", "Tetrahedron_0.005"):
            path = data_directory / (stem + ".npy")
            raw = path.read_bytes()
            expected = upstream["Dataset/Test/" + path.name]
            git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            check(stem + "_official_blob", git_blob == expected["git_blob"] and len(raw) == expected["bytes"]
                  and hashlib.sha256(raw).hexdigest() == expected["sha256"])
            original = np.load(path, allow_pickle=False)
            check(stem + "_finite_three_coordinates", original.ndim == 2 and original.shape[1] == 3
                  and bool(np.isfinite(original).all()) and len(original) >= 128)
            pointsets[stem] = original.astype(np.float64)
            input_identity.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                                   "bytes": len(raw), "git_blob": git_blob, "shape": list(original.shape),
                                   "saved_dtype": str(original.dtype), "current_dtype": "float64"})

    qa_directory = HERE / "private/adapter_qa"
    qa_directory.mkdir(parents=True, exist_ok=True)
    results, details = {}, {}
    for stem in ("Tetrahedron", "Tetrahedron_0.005"):
        vertices = pointsets[stem]
        query_ids = np.floor(np.linspace(0, len(vertices) - 1, 128)).astype(np.int64)
        rng = np.random.RandomState(1729)
        method_timings = {}
        with stage(stem + "_single_iteration_filter"):
            candidate, detail, statistics = adapter.run_iteration(
                vertices, query_ids, "pointfilter", rng, pca_alignment, model=model, timings=method_timings)
        check(stem + "_128_queries", len(detail["query_source_ids"]) == 128
              and np.array_equal(detail["query_source_ids"], query_ids))
        check(stem + "_finite_candidate", bool(np.isfinite(candidate).all()))
        fixed = np.ones(len(vertices), dtype=bool)
        fixed[query_ids] = False
        check(stem + "_only_requested_queries_changed", np.array_equal(candidate[fixed], vertices[fixed]))
        expected_radius = 0.05 * float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)))
        check(stem + "_full_current_bbox_radius", float(detail["radius"]) == expected_radius,
              actual=float(detail["radius"]), expected=expected_radius)

        with stage(stem + "_official_Dataset_preprocessing_comparison"):
            # The contract preserves the current centers in binary64. Keep the
            # official Dataset/PCA/sampling path while giving it those same values.
            official = PointcloudPatchDataset(root=str(data_directory), shape_name=stem,
                                              train_state="evaluation", seed=1729)
            original_radius = official.patch_radius_absolute[0]
            official.noise_shapes[0] = {"noise_pts": vertices, "noise_kdtree": spatial.cKDTree(vertices)}
            official.patch_radius_absolute[0] = expected_radius
            captured_samples = []
            original_sampling = official.patch_sampling

            def capture_sampling(points):
                chosen = original_sampling(points)
                captured_samples.append(chosen.copy())
                return chosen

            official.patch_sampling = capture_sampling
            np.random.seed(1729)
            maximum_preprocessing_difference = 0.0
            maximum_inverse_difference = 0.0
            reference_inv = []
            for row, source_id in enumerate(query_ids):
                sample = official[int(source_id)]
                check(stem + "_official_query_available_" + str(row), sample is not None)
                points, inverse, center = sample
                points32 = points.numpy().astype(np.float32)
                inverse64 = inverse.numpy()
                maximum_preprocessing_difference = max(maximum_preprocessing_difference,
                    float(np.max(np.abs(points32.astype(np.float64) - detail["normalized_points"][row]))))
                maximum_inverse_difference = max(maximum_inverse_difference,
                    float(np.max(np.abs(inverse64 - detail["pca_inverse"][row]))))
                check(stem + "_official_normalized_query_" + str(row),
                      np.array_equal(points32, detail["normalized_points"][row]))
                check(stem + "_official_inverse_query_" + str(row),
                      np.array_equal(inverse64, detail["pca_inverse"][row]))
                neighbor_ids = np.asarray(official.noise_shapes[0]["noise_kdtree"].query_ball_point(
                    center, expected_radius), dtype=np.int64)
                begin, end = detail["neighbor_offsets"][row:row + 2]
                check(stem + "_full_neighbor_ids_" + str(row),
                      np.array_equal(neighbor_ids, detail["neighbor_source_ids"][begin:end]))
                check(stem + "_official_sample_ids_" + str(row), np.array_equal(
                    neighbor_ids[captured_samples[-1]], detail["sampled_source_ids"][row]))
                # The inverse must reconstruct every unscaled sampled offset.
                reconstructed = (inverse64 @ (points.numpy() * expected_radius).T).T
                expected = vertices[neighbor_ids[captured_samples[-1]]] - center
                error = float(np.max(np.abs(reconstructed - expected)))
                check(stem + "_PCA_roundtrip_query_" + str(row), error <= 1e-10,
                      maximum_absolute_difference=error)
                reference_inv.append(inverse64)

        with stage(stem + "_candidate_and_details_save"):
            np.save(qa_directory / (stem + "_candidate.npy"), candidate, allow_pickle=False)
            np.savez_compressed(qa_directory / (stem + "_details.npz"), **detail)
        results[stem] = {"queries": 128, "iterations": 1, "radius": expected_radius,
                         "official_original_dtype_radius": float(original_radius),
                         "original_dtype_vs_binary64_radius_difference": expected_radius - original_radius,
                         "maximum_preprocessing_difference": maximum_preprocessing_difference,
                         "maximum_inverse_difference": maximum_inverse_difference,
                         "candidate_path": str(qa_directory / (stem + "_candidate.npy")),
                         "candidate_sha256": digest(qa_directory / (stem + "_candidate.npy")),
                         "details_path": str(qa_directory / (stem + "_details.npz")),
                         "details_sha256": digest(qa_directory / (stem + "_details.npz")),
                         "statistics": statistics, "adapter_stage_timings": method_timings}
        details[stem] = detail

    with stage("fixed_existing_query_forward_and_inverse_equivalence"):
        detail = details["Tetrahedron"]
        fixed_batch = np.ascontiguousarray(detail["normalized_points"][:4].transpose(0, 2, 1))
        with torch.inference_mode():
            predicted = model(torch.from_numpy(fixed_batch)).cpu().numpy()
        expected_prediction = detail["network_prediction"][:4]
        forward_difference = float(np.max(np.abs(predicted - expected_prediction)))
        check("four_existing_query_direct_official_forward", bool(np.allclose(predicted, expected_prediction,
              atol=1e-6, rtol=1e-6)), maximum_absolute_difference=forward_difference)
        inverse32 = torch.from_numpy(detail["pca_inverse"].astype(np.float32))
        with torch.inference_mode():
            rotated = torch.bmm(inverse32, torch.from_numpy(detail["network_prediction"]).unsqueeze(2)).squeeze(2).numpy()
        query_ids = detail["query_source_ids"]
        centers = pointsets["Tetrahedron"][query_ids]
        delta = rotated.astype(np.float64) * float(detail["radius"])
        preserved = centers + delta
        saved = np.load(results["Tetrahedron"]["candidate_path"], allow_pickle=False)[query_ids]
        check("official_inverse_float32_then_binary64_center_increment", np.array_equal(preserved, saved))
        official_save32 = (centers + rotated * float(detail["radius"])).astype(np.float32)
        save_difference = float(np.max(np.abs(preserved - official_save32.astype(np.float64))))
        results["Tetrahedron"]["official_float32_save_vs_preserved_center_max_abs_difference"] = save_difference

    with stage("pair_pointset_and_clean_movement_evaluation"):
        clean, noisy = pointsets["Tetrahedron"], pointsets["Tetrahedron_0.005"]
        clean_query = details["Tetrahedron"]["query_source_ids"]
        noisy_query = details["Tetrahedron_0.005"]["query_source_ids"]
        clean_candidate = np.load(results["Tetrahedron"]["candidate_path"], allow_pickle=False)
        noisy_candidate = np.load(results["Tetrahedron_0.005"]["candidate_path"], allow_pickle=False)
        tree = spatial.cKDTree(clean)
        before = tree.query(noisy[noisy_query], k=1, workers=1)[0]
        after = tree.query(noisy_candidate[noisy_query], k=1, workers=1)[0]
        movement = np.linalg.norm(clean_candidate[clean_query] - clean[clean_query], axis=1)
        clean_diagonal = float(np.linalg.norm(clean.max(axis=0) - clean.min(axis=0)))
        pair_evaluation = {
            "pointwise_correspondence": "unverified; fixed official files have no supplied index mapping provenance",
            "file_shapes_equal": clean.shape == noisy.shape,
            "metric": "128 fixed noisy query vertices to the complete clean point set, finite nearest-point samples",
            "normalization": "complete clean bounding-box diagonal",
            "clean_bbox_diagonal": clean_diagonal,
            "noisy_noop_to_clean_pointset": stats(before / clean_diagonal),
            "noisy_filtered_to_clean_pointset": stats(after / clean_diagonal),
            "noisy_pointset_RMSE_ratio": float(np.sqrt(np.mean(after ** 2) / np.mean(before ** 2))),
            "clean_input_requested_point_movement": stats(movement / clean_diagonal),
            "scope": "official noise-domain workflow check; local dent acceptance evaluated separately"}
        np.savez_compressed(qa_directory / "pair_evaluation.npz", noisy_query_source_ids=noisy_query,
                            clean_query_source_ids=clean_query, noisy_before_distance=before,
                            noisy_after_distance=after, clean_input_movement=movement)

    report = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": "passed_official_adapter_workflow_QA",
              "checks": checks, "check_count": len(checks), "failures": [], "input_identities": input_identity,
              "results": results, "pair_evaluation": pair_evaluation, "timings": timings,
              "checkpoint_load_substages": load_timings,
              "real_dent_case_predictions": 0, "official_unique_query_points": 256,
              "official_filtered_queries": 256, "additional_repeated_forward_queries": 4,
              "training": 0, "Bunny_arrays": 0,
              "dtype_adaptation": "official current point values promoted to float64 for radius, PCA and preserved centers; network/input and inverse rotation float32; full cloud float32 serialization omitted",
              "source_sha256": {name: digest(HERE / name) for name in
                                ("verify_adapter.py", "adapter.py", "inference.py")},
              "body_wall_s_before_final_write": time.perf_counter() - BOOT_WALL,
              "body_CPU_s_before_final_write": time.process_time() - BOOT_CPU,
              "own_process_before_final_write": adapter.process_resources(),
              "measurement_scope": "self stages and imports included before final JSON serialization/write/exit; outer tree ledger supplies process startup/exit and RSS"}
    write("TETRAHEDRON_CHECK.json", report)
    print(json.dumps({"status": report["status"], "checks": len(checks),
                      "noise_pointset_RMSE_ratio": pair_evaluation["noisy_pointset_RMSE_ratio"]}))


if __name__ == "__main__":
    main()
