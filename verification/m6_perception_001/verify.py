"""Internal formula replay of frozen features, one trained head and A/B metrics."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

from contextlib import contextmanager
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRETRAIN = HERE.parent / "m6_shape_pretrain_001"
for directory in json.loads((PRETRAIN / "ENVIRONMENT.json").read_bytes())["dependency_paths"]:
    sys.path.insert(0, directory)

import numpy as np
from sklearn.decomposition import PCA
import torch

CONFIGURATIONS = ("perception", "old_p", "solid_point", "ring_point")


@contextmanager
def timed(timings, name):
    started, cpu = time.perf_counter(), time.process_time()
    yield
    timings[name] = {"wall_s": time.perf_counter() - started, "CPU_s": time.process_time() - cpu}


def tensor_hash(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        meta = json.dumps({"name": name, "dtype": str(tensor.dtype), "shape": list(tensor.shape)},
                          sort_keys=True, separators=(",", ":")).encode()
        data = tensor.numpy().tobytes()
        digest.update(len(meta).to_bytes(8, "little"))
        digest.update(meta)
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
    return digest.hexdigest()


def rotation(source, destination, vertical):
    cross = np.cross(source, destination)
    cosine = np.dot(source, destination)
    if np.linalg.norm(cross) == 0 or abs(cosine) >= 1:
        if cosine >= 0:
            return np.eye(3)
        axis = np.asarray(vertical) / np.linalg.norm(vertical)
        return 2 * np.outer(axis, axis) - np.eye(3)
    axis = cross / np.linalg.norm(cross)
    angle = np.arccos(cosine)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) * np.cos(angle) + (1 - np.cos(angle)) * np.outer(axis, axis) + np.sin(angle) * skew


def pca_points(points):
    directions = PCA(n_components=3).fit(points).components_
    directions /= np.linalg.norm(directions, axis=0)
    first = rotation(directions[2], np.array([0., 0., 1.]), directions[1])
    moved = (first @ directions.T).T
    second = rotation(moved[1], np.array([1., 0., 0.]), moved[2])
    matrix = second @ first
    return (matrix @ points.T).T, np.linalg.inv(matrix)


def connected(mask, edges):
    adjacency = [[] for _ in mask]
    for first, second in np.asarray(edges).T:
        adjacency[first].append(int(second))
        adjacency[second].append(int(first))
    seen, result = set(), []
    for start in np.flatnonzero(mask):
        if int(start) in seen:
            continue
        pending, members = [int(start)], []
        seen.add(int(start))
        while pending:
            current = pending.pop()
            members.append(current)
            for other in adjacency[current]:
                if mask[other] and other not in seen:
                    seen.add(other)
                    pending.append(other)
        result.append(np.array(sorted(members), dtype=np.int64))
    return result


def rank_values(labels, scores):
    labels, scores = np.asarray(labels, dtype=bool), np.asarray(scores, dtype=np.float64)
    positive, negative = int(labels.sum()), int((~labels).sum())
    auc, ap = None, None
    if positive and negative:
        order = np.argsort(scores, kind="stable")
        ordered, truth = scores[order], labels[order]
        _, starts, counts = np.unique(ordered, return_index=True, return_counts=True)
        ranks = np.empty(len(scores))
        for start, count in zip(starts, counts):
            ranks[start:start + count] = start + (count + 1) / 2
        auc = float((ranks[truth].sum() - positive * (positive + 1) / 2) / (positive * negative))
    if positive:
        order = np.argsort(-scores, kind="stable")
        ordered, truth = scores[order], labels[order]
        ends = np.flatnonzero(np.r_[ordered[1:] != ordered[:-1], True])
        true_counts = np.cumsum(truth)[ends]
        ap = float(np.sum(np.diff(np.r_[0, true_counts]) / positive * true_counts / (ends + 1)))
    return {"points": len(scores), "positive": positive, "negative": negative,
            "ROC_AUC": auc, "AP": ap, "AUC_not_applicable": not (positive and negative), "AP_not_applicable": positive == 0}


def attention(scores, ids, area):
    order = sorted(range(len(scores)), key=lambda row: (-float(scores[row]), int(ids[row])))
    limit, used = .25 * float(np.sum(area)), 0.0
    chosen = np.zeros(len(scores), dtype=bool)
    if limit > 0:
        for row in order:
            if used + float(area[row]) > limit:
                break
            used += float(area[row])
            chosen[row] = True
    count = int(chosen.sum())
    return chosen, {"budget_fraction": .25, "budget_area_native": limit,
        "total_F_area_native": float(area.sum()), "selected_prefix_area_native": used,
        "actual_area_fraction": used / float(area.sum()) if area.sum() > 0 else None,
        "selected_points": count, "next_stopping_source_id": int(ids[order[count]]) if count < len(order) else None,
        "score_tied_points": len(scores) - len(np.unique(scores)), "area_budget_applicable": bool(area.sum() > 0)}


def operation(labels, selected, area, ell, edges):
    tp = int(np.count_nonzero(labels & selected))
    fp = int(np.count_nonzero(~labels & selected))
    fn = int(np.count_nonzero(labels & ~selected))
    tn = int(np.count_nonzero(~labels & ~selected))
    positive_area = float(area[labels].sum())
    true_area = float(area[labels & selected].sum())
    false_area = float(area[~labels & selected].sum())
    normal_area = float(area[~labels].sum())
    sizes = [len(component) for component in connected(selected, edges)]
    missed = connected(labels & ~selected, edges)
    largest = max(missed, key=lambda part: (float(area[part].sum()), len(part), -int(part.min()))) if missed else np.empty(0, dtype=np.int64)
    maximum = float(area[largest].sum())
    return {"points": len(labels), "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "point_recall": tp / (tp + fn) if tp + fn else None, "point_precision": tp / (tp + fp) if tp + fp else None,
        "point_FPR": fp / (fp + tn) if fp + tn else None,
        "positive_area_native": positive_area, "selected_positive_area_native": true_area,
        "missed_positive_area_native": positive_area - true_area, "selected_normal_area_native": false_area,
        "normal_area_native": normal_area, "positive_area_over_ell2": positive_area / ell ** 2,
        "selected_positive_area_over_ell2": true_area / ell ** 2,
        "missed_positive_area_over_ell2": (positive_area - true_area) / ell ** 2,
        "selected_normal_area_over_ell2": false_area / ell ** 2, "normal_area_over_ell2": normal_area / ell ** 2,
        "area_recall": true_area / positive_area if positive_area else None,
        "area_precision": true_area / (true_area + false_area) if true_area + false_area else None,
        "zero_true_detection": bool(tp == 0) if tp + fn else None,
        "normal_case_any_selection": bool(tp + fp) if not labels.any() else None,
        "selected_component_count": len(sizes), "selected_component_sizes": sizes,
        "largest_missed_component_points": len(largest), "largest_missed_component_area_native": maximum,
        "largest_missed_component_area_over_ell2": maximum / ell ** 2, "missed_component_count": len(missed),
        "total_F_area_native": float(area.sum()), "selected_F_area_native": true_area + false_area,
        "total_F_area_over_ell2": float(area.sum()) / ell ** 2,
        "selected_F_area_over_ell2": (true_area + false_area) / ell ** 2,
        "selected_F_area_fraction": (true_area + false_area) / float(area.sum()) if area.sum() else None}


def describe(values):
    raw = list(values)
    valid = np.array([value for value in raw if value is not None], dtype=np.float64)
    return {"requested_values": len(raw), "count": len(valid), "not_applicable_values": len(raw) - len(valid),
            "min": float(valid.min()) if len(valid) else None, "median": float(np.median(valid)) if len(valid) else None,
            "mean": float(valid.mean()) if len(valid) else None, "p95": float(np.quantile(valid, .95)) if len(valid) else None,
            "max": float(valid.max()) if len(valid) else None}


def macro(rows, function):
    patches = {}
    for row in rows:
        patches.setdefault(row["patch_id"], []).append(function(row))
    result = {}
    for patch, values in sorted(patches.items()):
        available = [value for value in values if value is not None]
        result[patch] = {"requested_cases": len(values), "eligible_cases": len(available),
                         "value": float(np.mean(available)) if available else None}
    available = [row["value"] for row in result.values() if row["value"] is not None]
    return {"requested_patches": len(result), "eligible_patches": len(available),
            "value": float(np.mean(available)) if available else None, "patches": result}


def aggregate_operations(rows):
    keys = ("TP", "FP", "FN", "TN", "positive_area_native", "selected_positive_area_native", "missed_positive_area_native",
            "selected_normal_area_native", "normal_area_native", "positive_area_over_ell2", "selected_positive_area_over_ell2",
            "missed_positive_area_over_ell2", "selected_normal_area_over_ell2", "normal_area_over_ell2",
            "total_F_area_native", "selected_F_area_native", "total_F_area_over_ell2", "selected_F_area_over_ell2")
    out = {key: sum(row[key] for row in rows) for key in keys}
    positive, selected = out["TP"] + out["FN"], out["TP"] + out["FP"]
    total_positive_area, total_selected_area = out["positive_area_native"], out["selected_F_area_native"]
    sizes = [size for row in rows for size in row["selected_component_sizes"]]
    out.update(points=out["TP"] + out["FP"] + out["FN"] + out["TN"],
        point_recall=out["TP"] / positive if positive else None,
        point_precision=out["TP"] / selected if selected else None,
        point_FPR=out["FP"] / (out["FP"] + out["TN"]) if out["FP"] + out["TN"] else None,
        area_recall=out["selected_positive_area_native"] / total_positive_area if total_positive_area else None,
        area_precision=out["selected_positive_area_native"] / total_selected_area if total_selected_area else None,
        area_recall_ell_normalized_pool=out["selected_positive_area_over_ell2"] / out["positive_area_over_ell2"] if out["positive_area_over_ell2"] else None,
        zero_true_detection_cases=sum(row["zero_true_detection"] is True for row in rows),
        damage_cases_with_defined_zero_detection=sum(row["zero_true_detection"] is not None for row in rows),
        selected_component_count=len(sizes), selected_component_size_distribution=describe(sizes),
        per_case_point_recall=describe(row["point_recall"] for row in rows),
        per_case_area_recall=describe(row["area_recall"] for row in rows),
        per_case_point_precision=describe(row["point_precision"] for row in rows),
        selected_F_area_fraction=total_selected_area / out["total_F_area_native"] if out["total_F_area_native"] else None,
        selected_F_area_fraction_ell_normalized_pool=out["selected_F_area_over_ell2"] / out["total_F_area_over_ell2"] if out["total_F_area_over_ell2"] else None,
        per_case_selected_F_area_fraction=describe(row["selected_F_area_fraction"] for row in rows))
    for key in ("largest_missed_component_points", "largest_missed_component_area_native", "largest_missed_component_area_over_ell2"):
        out["per_case_" + key] = describe(row[key] for row in rows)
    return out


def main():
    started, cpu = time.perf_counter(), time.process_time()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    failures, timings, identities = [], {}, {}
    count, maximum = 0, 0.0

    def check(name, passed, size=1):
        nonlocal count
        count += size
        if not bool(passed):
            failures.append(name)
            raise ValueError(name)

    def compare(name, expected, actual, atol=1e-10, rtol=1e-10):
        nonlocal maximum
        if isinstance(expected, dict):
            for key, value in expected.items():
                check(name + ".key." + key, key in actual)
                compare(name + "." + key, value, actual[key], atol, rtol)
        elif expected is None or isinstance(expected, (str, bool)):
            check(name, expected == actual)
        elif isinstance(expected, (list, tuple, np.ndarray)):
            a, b = np.asarray(expected), np.asarray(actual)
            check(name + ".shape", a.shape == b.shape)
            if a.dtype.kind in "biuUSO":
                check(name, np.array_equal(a, b), max(1, a.size))
            else:
                maximum = max(maximum, float(np.max(np.abs(a - b))) if a.size else 0.0)
                check(name, np.allclose(a, b, atol=atol, rtol=rtol, equal_nan=True), max(1, a.size))
        else:
            check(name + ".notnull", actual is not None)
            maximum = max(maximum, abs(float(expected) - float(actual)))
            check(name, np.isclose(expected, actual, atol=atol, rtol=rtol))

    def record(path, expected=None):
        path = Path(path)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if expected is not None:
            check("identity_" + str(path), sha == expected)
        identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return path

    def read(name):
        return json.loads(record(HERE / name).read_bytes())

    with timed(timings, "metadata_and_official_model_identity"):
        features, training, predictions, calibration, evaluation = (read(name) for name in
            ("FEATURES.json", "TRAIN_LOG.json", "PREDICTIONS.json", "CALIBRATION.json", "EVALUATION.json"))
        model_id, normal_info = read("MODEL_IDENTITY.json"), read("NORMALIZATION.json")
        whitelist = {row["id"]: row for row in read("INPUT_WHITELIST.json")["cases"]}
        feature_index = {row["id"]: row for row in features["cases"]}
        prediction_index = {row["id"]: row for row in predictions["cases"]}
        evaluated = {row["id"]: row for row in evaluation["cases"]}
        selections = {row["id"]: row for row in read("SELECTION_INDEX.json")["cases"]}
        check("348_same_case_IDs", len(whitelist) == 348 and set(whitelist) == set(feature_index) == set(prediction_index) == set(evaluated) == set(selections))
        for row in read("CALIBRATION_FREEZE.json")["files"]:
            record(row["path"], row["sha256"])
        spec = importlib.util.spec_from_file_location("_verified_official_pointfilter", PRETRAIN / "private/pointfilter/Pointfilter_Network_Architecture.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checkpoint_path = PRETRAIN / "private/pointfilter/model_full_ae.pth"
        record(checkpoint_path, "86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee")
        official = module.pointfilternet().cpu().eval()
        official.load_state_dict(torch.load(checkpoint_path, map_location="cpu", weights_only=True)["state_dict"], strict=True)
        official.requires_grad_(False)
        expected_encoder_hash = tensor_hash(official.encoder.state_dict())
        for path in (features["encoder_initial_checkpoint"]["path"], features["encoder_after_features_checkpoint"]["path"],
                     model_id["encoder_post_training_checkpoint"]["path"]):
            state = torch.load(record(path), map_location="cpu", weights_only=True)
            compare("encoder_tensor_digest", expected_encoder_hash, tensor_hash(state))
            for key, tensor in official.encoder.state_dict().items():
                compare("encoder_parameter_or_BN_" + key, tensor.numpy(), state[key].numpy(), 0, 0)
        for key in ("encoder_initial_tensor_sha256", "encoder_final_tensor_sha256", "encoder_feature_initial_tensor_sha256", "encoder_feature_final_tensor_sha256"):
            compare(key, expected_encoder_hash, model_id[key])
        compare("encoder_parameters", 702464, sum(value.numel() for value in official.encoder.parameters()))
        compare("decoder_calls", 0, features["decoder_forward_calls"])
        compare("encoder_training_updates", 0, model_id["encoder_parameter_or_BN_training_updates"])
        compare("training_runs", 1, training["training_runs"])
        compare("training_steps", 1200, training["completed_steps"])
        initial = torch.load(record(training["initial_checkpoint"]["path"], training["initial_checkpoint"]["sha256"]), map_location="cpu", weights_only=True)
        final = torch.load(record(training["final_checkpoint"]["path"], training["final_checkpoint"]["sha256"]), map_location="cpu", weights_only=True)
        torch.manual_seed(1729)
        initial_head = torch.nn.Sequential(torch.nn.Linear(1024, 64), torch.nn.GELU(), torch.nn.Linear(64, 1)).cpu().eval()
        initial_rng = torch.get_rng_state().numpy().copy()
        for key, value in initial_head.state_dict().items():
            compare("seed1729_initial_head_" + key, value.numpy(), initial["state_dict"]["network." + key].numpy(), 0, 0)
        compare("initial_torch_RNG", initial_rng, initial["torch_rng_state"].numpy())
        compare("head_parameters", 65665, sum(value.numel() for value in initial_head.parameters()))
        final_head = torch.nn.Sequential(torch.nn.Linear(1024, 64), torch.nn.GELU(), torch.nn.Linear(64, 1)).cpu().eval()
        final_head.load_state_dict({key.removeprefix("network."): value for key, value in final["state_dict"].items()}, strict=True)
        compare("head_initial_tensor_hash", model_id["head_initial_tensor_sha256"], tensor_hash(initial["state_dict"]))
        compare("head_final_tensor_hash", model_id["head_final_tensor_sha256"], tensor_hash(final["state_dict"]))
        compare("final_checkpoint_step", 1200, final["step"])
        for state in final["optimizer"]["state"].values():
            compare("final_optimizer_step", 1200, float(state["step"]))
        compare("optimizer_hyperparameters", {"lr": .001, "weight_decay": .0001, "betas": [.9, .999], "eps": 1e-8, "foreach": False}, final["optimizer"]["param_groups"][0])
        with np.load(record(training["normalization"]["path"], training["normalization"]["sha256"]), allow_pickle=False) as saved:
            normalization = {key: saved[key].copy() for key in saved.files}
        with np.load(record(training["sampling_trajectory"]["path"], training["sampling_trajectory"]["sha256"]), allow_pickle=False) as saved:
            trajectory = {key: saved[key].copy() for key in saved.files}
        development_ids = sorted(case_id for case_id, row in whitelist.items() if row["purpose"] == "development_train_pool")
        compare("231_development_IDs", development_ids, training["case_ids"])
        old_cases = {}
        for path in (HERE.parent / "m6_shape_data_001/DATASET_INDEX.json", HERE.parent / "m6_shape_train_001/PUBLIC_DATASET_INDEX.json"):
            old_cases.update({row["id"]: row for row in json.loads(record(path).read_bytes())["cases"] if row["purpose"] != "reserved_test"})
        ring = HERE.parent / "m6_shape_ring_001"
        ring_residuals = {row["id"]: row for row in json.loads(record(ring / "RESIDUALS.json").read_bytes())["cases"]}
        ring_scores = {row["id"]: row for row in json.loads(record(ring / "EVALUATION.json").read_bytes())["cases"]}
        old_pretrain = {row["id"]: row for row in json.loads(record(PRETRAIN / "MODEL_OUTPUTS.json").read_bytes())["cases"]}
    source_cache, patch_cache, cases, arrays = {}, {}, [], {}
    sums, squared, point_count = np.zeros(1024), np.zeros(1024), 0
    positive_fractions, case_sizes = [], []
    first_batch, first_targets = np.empty((1024, 1024), dtype=np.float32), np.empty(1024, dtype=np.float32)
    encoder_replay_queries, historical_sampling_cases = 0, 0
    with timed(timings, "all_features_geometry_sampling_head_and_case_metrics"):
        for case_id, white in sorted(whitelist.items()):
            old = old_cases[case_id]
            feature_row, predicted, actual = feature_index[case_id], prediction_index[case_id], evaluated[case_id]
            with np.load(record(feature_row["path"], feature_row["sha256"]), allow_pickle=False) as saved:
                check("label_free_feature_keys", set(saved.files) == {"features", "free_source_ids", "free_context_ids", "valid_mask"})
                feature, ids, free_context, valid = (saved[key].copy() for key in ("features", "free_source_ids", "free_context_ids", "valid_mask"))
            check("feature_float32_shape", feature.dtype == np.float32 and feature.shape == (len(ids), 1024))
            check("invalid_feature_zero", np.all(feature[~valid] == 0))
            source = white["source"]
            if source not in source_cache:
                with np.load(record(white["snapshot"]["path"], white["snapshot"]["sha256"]), allow_pickle=False) as saved:
                    source_cache[source] = (saved["vertices"].astype(np.float64), saved["triangles"].astype(np.int64))
            base, triangles = source_cache[source]
            with np.load(record(white["mapping_path"]), allow_pickle=False) as saved:
                context = saved["context_source_ids"]
            with np.load(record(white["graph_path"]), allow_pickle=False) as saved:
                expected_free = np.flatnonzero(saved["free_mask"])
            expected_free = expected_free[np.argsort(context[expected_free])]
            compare("F_context_mapping", expected_free, free_context)
            compare("F_source_mapping", context[free_context], ids)
            observed = np.load(record(white["observed"]["path"], white["observed"]["sha256"]), allow_pickle=False)
            with np.load(record(white["input"]["path"], white["input"]["sha256"]), allow_pickle=False) as saved:
                compare("saved_observation_scale", float(saved["scale_m"]), feature_row["ell"])
            current = base.copy()
            current[context] = observed
            radius = .05 * float(np.linalg.norm(current.max(0) - current.min(0)))
            with np.load(record(feature_row["detail_path"], feature_row["detail_sha256"]), allow_pickle=False) as saved:
                detail = {key: saved[key].copy() for key in saved.files}
            compare("complete_source_radius", radius, detail["radius"])
            compare("detail_query_ids", ids, detail["query_source_ids"])
            generator = np.random.RandomState(1729)
            check("sampling_shape500", detail["sampled_source_ids"].shape == (len(ids), 500))
            for query in range(len(ids)):
                first, stop = detail["neighbor_offsets"][query:query + 2]
                neighbors = detail["neighbor_source_ids"][first:stop]
                compare("neighbor_count", len(neighbors), detail["neighbor_count"][query])
                if len(neighbors) >= 3:
                    sampled = neighbors[generator.choice(range(len(neighbors)), 500, replace=len(neighbors) <= 500)]
                    compare("actual500_sampling", sampled, detail["sampled_source_ids"][query])
            selected_queries = np.unique([0, len(ids) // 2, len(ids) - 1])
            for query in selected_queries:
                first, stop = detail["neighbor_offsets"][query:query + 2]
                neighbors = detail["neighbor_source_ids"][first:stop]
                squared_distances = np.sum((current - current[ids[query]]) ** 2, axis=1)
                compare("full_source_radius_membership", np.flatnonzero(squared_distances <= radius ** 2), np.sort(neighbors))
                if len(neighbors) >= 3:
                    local, inverse = pca_points(current[neighbors] - current[ids[query]])
                    lookup = {int(source_id): index for index, source_id in enumerate(neighbors)}
                    positions = [lookup[int(source_id)] for source_id in detail["sampled_source_ids"][query]]
                    expected_points = (local[positions] / radius).astype(np.float32)
                    compare("independent_PCA_inverse", inverse, detail["pca_inverse"][query], 1e-9, 1e-9)
                    compare("independent_normalized500", expected_points, detail["normalized_points"][query], 2e-6, 2e-6)
            usable = [query for query in selected_queries if valid[query]]
            with torch.inference_mode():
                if usable:
                    tensor = torch.from_numpy(detail["normalized_points"][usable]).transpose(2, 1).contiguous()
                    replayed = official.encoder(tensor).numpy()
                    compare("official_encoder_existing_queries", replayed, feature[usable], 5e-5, 2e-5)
                    encoder_replay_queries += len(usable)
            if case_id in old_pretrain:
                first_step = old_pretrain[case_id]["methods"]["pointfilter"]["iterations"][0]
                with np.load(record(first_step["sampling_path"], first_step["sampling_sha256"]), allow_pickle=False) as saved:
                    for key in ("query_source_ids", "neighbor_offsets", "neighbor_source_ids", "sampled_source_ids", "normalized_points", "pca_inverse", "radius"):
                        compare("PRETRAIN_first_iteration_" + key, detail[key], saved[key], 0, 0)
                historical_sampling_cases += 1
            normalized = ((feature.astype(np.float64) - normalization["mean"]) / normalization["divisor"]).astype(np.float32)
            with torch.inference_mode():
                logits = final_head(torch.from_numpy(normalized)).squeeze(1).numpy()
                scores = torch.sigmoid(torch.from_numpy(logits)).numpy()
            logits[~valid], scores[~valid] = 0., 0.
            with np.load(record(predicted["path"], predicted["sha256"]), allow_pickle=False) as saved:
                compare("final_head_all_logits", logits, saved["logits"], 5e-5, 2e-5)
                compare("final_head_all_scores", scores, saved["scores"], 5e-6, 2e-5)
                compare("prediction_source_ids", ids, saved["free_source_ids"])
                compare("prediction_validity", valid, saved["valid_mask"])
                stored_scores = saved["scores"].reshape(-1).astype(np.float64)
            folder = Path(white["observed"]["path"]).parents[1]
            reference = np.load(record(folder / "reference_local.npy"), allow_pickle=False)
            with np.load(record(old["labels"]["path"], old["labels"]["sha256"]), allow_pickle=False) as saved:
                support = saved["damaged_mask"][free_context].astype(bool)
            strong = np.linalg.norm(reference[free_context] - observed[free_context], axis=1) > .10 * feature_row["ell"]
            if white["purpose"] == "development_train_pool":
                case_number = development_ids.index(case_id)
                first_rows = np.flatnonzero(trajectory["case_index"][0] == case_number)
                first_batch[first_rows] = feature[trajectory["F_row_index"][0, first_rows]]
                first_targets[first_rows] = support[trajectory["F_row_index"][0, first_rows]]
                sums += np.sum(feature, axis=0, dtype=np.float64)
                point_count += len(ids)
                positive_fractions.append(float(support.mean()))
                case_sizes.append(len(ids))
            if white["patch_id"] not in patch_cache:
                included = np.zeros(len(current), dtype=bool)
                included[ids] = True
                incident = np.flatnonzero(np.any(included[triangles], axis=1))
                patch_cache[white["patch_id"]] = incident
            faces = triangles[patch_cache[white["patch_id"]]]
            triple = current[faces]
            triangle_area = .5 * np.linalg.norm(np.cross(triple[:, 1] - triple[:, 0], triple[:, 2] - triple[:, 0]), axis=1)
            full_area = np.bincount(faces.ravel(), weights=np.repeat(triangle_area / 3, 3), minlength=len(current))
            area = full_area[ids]
            with np.load(record(ring_residuals[case_id]["path"], ring_residuals[case_id]["sha256"]), allow_pickle=False) as saved:
                compare("complete_current_vertex_area", area, saved["area"])
                edges = saved["free_edge_index"].copy()
            with np.load(record(ring_scores[case_id]["score_path"], ring_scores[case_id]["score_sha256"]), allow_pickle=False) as saved:
                all_scores = {key: saved[key].copy() for key in ("old_p", "solid_point", "ring_point")}
            all_scores["perception"] = stored_scores
            scores = stored_scores
            case = {key: old.get(key) for key in ("id", "patch_id", "source", "source_group", "purpose", "stratum", "normal_control", "radius_ratio", "amplitude_ratio")}
            case.update(position_group=white["position_group"], F_points=len(ids), support_points=int(support.sum()), strong_points=int(strong.sum()),
                        weak_damaged_as_strong_task_negative_points=int(np.count_nonzero(support & ~strong)), configurations={})
            with np.load(record(selections[case_id]["path"], selections[case_id]["sha256"]), allow_pickle=False) as saved:
                check("selection_no_embeddings_or_labels", set(saved.files) == {"free_source_ids", "free_context_ids", "free_edge_index", "area", "new_score", "valid_mask", "attention_mask", "abnormal_mask", "A_old_p_selected", "A_solid_point_selected", "A_ring_point_selected"})
                compare("selection_ids", ids, saved["free_source_ids"])
                compare("selection_area", area, saved["area"])
                for configuration in CONFIGURATIONS:
                    selected, budget = attention(all_scores[configuration], ids, area)
                    masks_key = "attention_mask" if configuration == "perception" else "A_" + configuration + "_selected"
                    compare("A_prefix_selection_" + configuration, selected, saved[masks_key])
                    entry = {"score_available": True, "unavailable_points": int((~valid).sum()) if configuration == "perception" else 0,
                             "rank": {task: rank_values(label, all_scores[configuration]) for task, label in (("support", support), ("strong", strong))},
                             "budget": budget, "A": {task: operation(label, selected, area, feature_row["ell"], edges) for task, label in (("support", support), ("strong", strong))}}
                    compare("case_A_" + case_id + configuration, entry, actual["configurations"][configuration])
                    case["configurations"][configuration] = entry
                selected = scores > calibration["threshold"]
                compare("B_strict_selection", selected, saved["abnormal_mask"])
            case["B"] = {task: operation(label, selected, area, feature_row["ell"], edges) for task, label in (("support", support), ("strong", strong))}
            case["B"]["selected_points"] = int(selected.sum())
            case["score_distribution"] = describe(scores)
            compare("case_metadata", {key: value for key, value in case.items() if key not in ("configurations", "B", "score_distribution")}, actual)
            compare("case_B", case["B"], actual["B"])
            compare("case_score_distribution", case["score_distribution"], actual["score_distribution"])
            cases.append(case)
            arrays[case_id] = {"support": support, "strong": strong, **all_scores}
    with timed(timings, "development_stats_sampling_and_initial_loss"):
        mean = sums / point_count
        for case_id in development_ids:
            with np.load(record(feature_index[case_id]["path"], feature_index[case_id]["sha256"]), allow_pickle=False) as saved:
                delta = saved["features"].astype(np.float64) - mean
            squared += np.sum(delta * delta, axis=0, dtype=np.float64)
        deviation = np.sqrt(squared / point_count)
        divisor = np.where(deviation < 1e-6, 1., deviation)
        compare("development_mean", mean, normalization["mean"])
        compare("development_std", deviation, normalization["standard_deviation"])
        compare("development_divisor", divisor, normalization["divisor"])
        compare("normalization_development_IDs", development_ids, normal_info["source_cases"])
        pi = float(np.mean(positive_fractions))
        compare("case_equal_pi", pi, training["case_equal_pi"])
        compare("case_equal_posweight", (1 - pi) / pi, training["positive_weight"])
        compare("case_F_sizes", case_sizes, training["case_sizes"])
        generator = np.random.RandomState(1729)
        replay_case, replay_row = np.empty((1200, 1024), dtype=np.int32), np.empty((1200, 1024), dtype=np.int32)
        for step in range(1200):
            for sample in range(1024):
                which = generator.randint(231)
                replay_case[step, sample] = which
                replay_row[step, sample] = generator.randint(case_sizes[which])
        compare("all_sampling_case_trajectory", replay_case, trajectory["case_index"])
        compare("all_sampling_row_trajectory", replay_row, trajectory["F_row_index"])
        _, keys, position, has_gaussian, cached_gaussian = generator.get_state()
        compare("final_sampler_state", {"algorithm": "MT19937", "keys": keys.tolist(), "position": position,
            "has_gaussian": has_gaussian, "cached_gaussian": cached_gaussian}, final["sampling_rng"])
        normalized_batch = ((first_batch.astype(np.float64) - mean) / divisor).astype(np.float32)
        with torch.inference_mode():
            first_logits = initial_head(torch.from_numpy(normalized_batch)).squeeze(1)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(first_logits, torch.from_numpy(first_targets),
                pos_weight=torch.tensor((1 - pi) / pi, dtype=torch.float32))
        compare("initial_batch_BCE_loss", float(loss), training["steps"][0]["loss"], 5e-6, 2e-5)
        for step, record_step in enumerate(training["steps"]):
            compare("logged_sampling_counts", {"step": step + 1, "positive_samples": int(sum(arrays[development_ids[int(case_index)]]["support"][int(row_index)] for case_index, row_index in zip(replay_case[step], replay_row[step]))),
                "sampled_case_count": len(np.unique(replay_case[step]))}, record_step)
    with timed(timings, "normal_calibration_and_all_group_metrics"):
        normal = [row for row in cases if row["purpose"] == "development_train_pool" and row["normal_control"]]
        threshold = float(np.quantile([arrays[row["id"]]["perception"].max() for row in normal], .95, method="linear"))
        compare("one33normal_linear_q95", threshold, calibration["threshold"])
        compare("calibration33", 33, len(normal))
        expected_false = [row["id"] for row in normal if arrays[row["id"]]["perception"].max() > threshold]
        compare("calibration_false_ids", expected_false, calibration["development_normal_false_case_ids"])
        group_rows = {"all": cases, "development_center": [row for row in cases if row["purpose"] == "development_train_pool"],
            "validation_center": [row for row in cases if row["purpose"] == "validation" and row["position_group"] == "center"],
            "validation_offcenter": [row for row in cases if row["purpose"] == "validation" and row["position_group"] == "offcenter"],
            "development_normal_controls": [row for row in cases if row["purpose"] == "development_train_pool" and row["normal_control"]],
            "validation_normal_controls": [row for row in cases if row["purpose"] == "validation" and row["normal_control"]]}
        for field in ("source", "patch_id", "stratum", "amplitude_ratio"):
            for value in sorted({row[field] for row in cases}, key=str):
                group_rows[field + "_" + str(value)] = [row for row in cases if row[field] == value]
        for name in ("development_center", "validation_center", "validation_offcenter"):
            for amplitude in (.05, .15, .3):
                group_rows[name + "_amplitude_" + str(amplitude)] = [row for row in group_rows[name] if row["amplitude_ratio"] == amplitude]
        check("all_group_keys", set(group_rows) == set(evaluation["groups"]))
        for name, members in group_rows.items():
            actual = evaluation["groups"][name]
            compare("group_denominators", {"requested_cases": len(members), "normal_controls": sum(row["normal_control"] for row in members),
                "dented_cases": sum(not row["normal_control"] for row in members), "patches": len({row["patch_id"] for row in members}),
                "F_points": sum(row["F_points"] for row in members), "support_points": sum(row["support_points"] for row in members),
                "strong_points": sum(row["strong_points"] for row in members),
                "weak_damaged_as_strong_task_negative_points": sum(row["weak_damaged_as_strong_task_negative_points"] for row in members)}, actual)
            for configuration in CONFIGURATIONS:
                for task in ("support", "strong"):
                    labels = np.concatenate([arrays[row["id"]][task] for row in members])
                    scores = np.concatenate([arrays[row["id"]][configuration] for row in members])
                    expected_rank = {"point_pool": rank_values(labels, scores),
                        "per_case_ROC_AUC": describe(row["configurations"][configuration]["rank"][task]["ROC_AUC"] for row in members),
                        "per_case_AP": describe(row["configurations"][configuration]["rank"][task]["AP"] for row in members),
                        "patch_macro_ROC_AUC": macro(members, lambda row: row["configurations"][configuration]["rank"][task]["ROC_AUC"]),
                        "patch_macro_AP": macro(members, lambda row: row["configurations"][configuration]["rank"][task]["AP"])}
                    compare("group_rank_" + name + configuration + task, expected_rank, actual["configurations"][configuration]["rank"][task])
                    expected_operation = aggregate_operations([row["configurations"][configuration]["A"][task] for row in members])
                    expected_operation["patch_macro_area_recall"] = macro(members, lambda row: row["configurations"][configuration]["A"][task]["area_recall"])
                    compare("group_A_" + name + configuration + task, expected_operation, actual["configurations"][configuration]["A"][task])
            for task in ("support", "strong"):
                expected_operation = aggregate_operations([row["B"][task] for row in members])
                expected_operation["patch_macro_area_recall"] = macro(members, lambda row: row["B"][task]["area_recall"])
                compare("group_B_" + name + task, expected_operation, actual["B"][task])
            compare("group_B_false_patch_ids", sorted({row["patch_id"] for row in members if row["normal_control"] and row["B"]["support"]["normal_case_any_selection"]}), actual["B"]["normal_false_patch_ids"])
        A_passed = []
        B_passed = []
        for position in ("validation_center", "validation_offcenter"):
            members = group_rows[position]
            auc = macro(members, lambda row: row["configurations"]["perception"]["rank"]["support"]["ROC_AUC"])["value"]
            ap = macro(members, lambda row: row["configurations"]["perception"]["rank"]["support"]["AP"])["value"]
            old_ap = macro(members, lambda row: row["configurations"]["old_p"]["rank"]["support"]["AP"])["value"]
            recall = macro(members, lambda row: row["configurations"]["perception"]["A"]["support"]["area_recall"])["value"]
            old_recall = macro(members, lambda row: row["configurations"]["old_p"]["A"]["support"]["area_recall"])["value"]
            gates = {"all_four_score_case_comparisons_available": True, "patch_macro_AUC_ge080": auc >= .8,
                "patch_macro_AP_gain_over_old_p_ge005": ap - old_ap >= .05, "patch_macro_area_recall_ge060": recall >= .60,
                "patch_macro_area_recall_gain_over_old_p_ge010": recall - old_recall >= .10}
            compare("A_gate_" + position, gates, evaluation["decision_gates"]["A_attention"]["positions"][position]["gates"])
            A_passed.append(all(gates.values()))
            b_recall = macro(members, lambda row: row["B"]["support"]["area_recall"])["value"]
            compare("B_gate_" + position, {"patch_macro_area_recall_ge060": b_recall >= .6, "value": b_recall}, evaluation["decision_gates"]["B_abnormality"]["positions"][position])
            B_passed.append(b_recall >= .6)
        false_patches = {row["patch_id"] for row in group_rows["validation_normal_controls"] if row["B"]["support"]["normal_case_any_selection"]}
        compare("A_overall_pass", all(A_passed), evaluation["decision_gates"]["A_attention"]["passed"])
        compare("B_overall_pass", len(false_patches) <= 1 and all(B_passed), evaluation["decision_gates"]["B_abnormality"]["passed"])
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in
            ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "passed_internal_perception_verification", "check_count": count,
        "failures": failures, "coverage": {"cases": len(cases), "F_point_observations": sum(row["F_points"] for row in cases),
            "encoder_existing_query_replays": encoder_replay_queries, "PRETRAIN_first_sampling_cases": historical_sampling_cases,
            "head_final_logit_points": sum(row["F_points"] for row in cases), "head_initial_loss_batches": 1,
            "optimizer_step_replays": 0, "full_training_replays": 0, "sampling_pairs_replayed": 1200 * 1024,
            "A_case_configurations": len(cases) * 4, "B_cases": len(cases), "groups": len(group_rows)},
        "largest_compared_absolute_difference": maximum, "timings": timings,
        "input_file_identities": list(identities.values()), "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "wall_s_before_final_report": time.perf_counter() - started, "CPU_s_before_final_report": time.process_time() - cpu,
        "bootstrap_wall_s_before_final_report": time.perf_counter() - BOOT_WALL, "bootstrap_CPU_s_before_final_report": time.process_time() - BOOT_CPU,
        "own_process_before_report": {"peak_working_set_bytes": counters.PeakWorkingSetSize, "working_set_bytes": counters.WorkingSetSize},
        "decoder_forward_calls": 0, "repair_outputs": 0, "Bunny_arrays": 0,
        "scope": "internal independent formula replay without importing current evaluation helpers, planner external review remains separate",
        "tolerances": {"float64_atol_rtol": 1e-10, "encoder_float32_atol": 5e-5, "encoder_float32_rtol": 2e-5,
                       "PCA_float64_atol_rtol": 1e-9, "normalized_float32_atol_rtol": 2e-6},
        "measurement_scope": "all loads and internal checks included before final report serialization, enclosing monitor covers startup/exit"}
    (HERE / "INDEPENDENT_VERIFY.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": report["status"], "checks": count, "coverage": report["coverage"]}))


if __name__ == "__main__":
    main()
