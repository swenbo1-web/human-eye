"""Replay fixed inference and independently audit metrics without any training."""

import ctypes
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import DATA, read, write, identity
import numpy as np
import torch
from model import load_model, predict_features


def array_equal(left, right):
    return left.shape == right.shape and left.dtype == right.dtype and left.tobytes() == right.tobytes()


def state_digest(state):
    result = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        value = tensor.detach().cpu().contiguous()
        header = json.dumps(dict(name=name, dtype=str(value.dtype), shape=list(value.shape)),
                            sort_keys=True, separators=(",", ":")).encode("utf8")
        payload = value.numpy().tobytes(order="C")
        result.update(len(header).to_bytes(8, "little"))
        result.update(header)
        result.update(len(payload).to_bytes(8, "little"))
        result.update(payload)
    return result.hexdigest()


def independent_metrics(score, threshold, area, label, ids):
    ordering = sorted(range(len(score)), key=lambda row: (-float(score[row]), int(ids[row])))
    selected = np.zeros(len(score), dtype=bool)
    used, budget = 0., float(area.sum()) * .25
    for row in ordering:
        proposed = used + float(area[row])
        if proposed > budget:
            break
        selected[row] = True
        used = proposed
    predicted = np.asarray([float(value) > threshold for value in score])
    positive_area = float(area[label].sum())
    negative = ~label
    positive_count = int(label.sum())
    negative_count = int(negative.sum())
    auc, ap = None, None
    if positive_count and negative_count:
        ascending = sorted(range(len(score)), key=lambda row: float(score[row]))
        rank_sum = 0.
        start = 0
        while start < len(score):
            end = start + 1
            while end < len(score) and score[ascending[end]] == score[ascending[start]]:
                end += 1
            average_rank = (start + 1 + end) / 2
            rank_sum += average_rank * sum(bool(label[row]) for row in ascending[start:end])
            start = end
        auc = (rank_sum - positive_count * (positive_count + 1) / 2) / (positive_count * negative_count)
    if positive_count:
        true_positives, processed, ap = 0, 0, 0.
        start = 0
        while start < len(score):
            end = start + 1
            while end < len(score) and score[ordering[end]] == score[ordering[start]]:
                end += 1
            added = sum(bool(label[row]) for row in ordering[start:end])
            true_positives += added
            processed += end - start
            ap += (added / positive_count) * (true_positives / processed)
            start = end
    return dict(AUC=auc, AP=ap,
                area_budget_recall=float(area[selected & label].sum() / positive_area) if positive_area else None,
                attention_area_fraction=float(area[selected].sum() / area.sum()),
                attention_false_area_fraction=float(area[selected & negative].sum() / area[negative].sum()) if negative_count else None,
                attention_hit=bool((selected & label).any()), positive_area_native=positive_area,
                anomaly_predicted_points=int(predicted.sum()), anomaly_any=bool(predicted.any()),
                anomaly_area_recall=float(area[predicted & label].sum() / positive_area) if positive_area else None,
                anomaly_false_area_fraction=float(area[predicted & negative].sum() / area[negative].sum()) if negative_count else None,
                support_points=positive_count)


def process_resources():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    value = Counters()
    value.cb = ctypes.sizeof(value)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb):
        raise ctypes.WinError()
    return dict(process_CPU_s=time.process_time(), working_set_bytes=value.WorkingSetSize,
                process_lifetime_peak_working_set_bytes=value.PeakWorkingSetSize)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "VERIFY.json").exists():
        raise RuntimeError("verification_report_already_exists_inspect_before_recovery")
    checks, failures, checked_files = [], [], {}

    def check(name, condition, alias=None):
        entry = dict(name=name, passed=bool(condition), alias=alias)
        checks.append(entry)
        if not condition:
            failures.append(entry)

    def checked_file(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = HERE / path
        key = str(path.resolve())
        if key not in checked_files:
            raw = path.read_bytes()
            checked_files[key] = dict(path=key, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if expected is not None:
            check("input_byte_identity", checked_files[key]["sha256"] == expected, key)
        return path

    def package(path, expected=None):
        with np.load(checked_file(path, expected), allow_pickle=False) as saved:
            return {key: saved[key] for key in saved.files}

    frozen = read("PLAN_FREEZE.json")
    for row in frozen["files"] + frozen["reused_data"]:
        checked_file(row["path"], row["sha256"])
    commit = read("OPTIMIZATION_COMMIT.json")
    binding = read("OPTIMIZATION_BINDING.json")
    checked_file("OPTIMIZATION_BINDING.json", commit["binding_sha256"])
    for filename in ["OPTIMIZATION_BINDING.json"] + [row["path"] for row in binding["files"]]:
        original = subprocess.check_output(["git", "show", commit["commit"] + ":verification/m6_task_perception_001/" + filename], cwd=HERE.parents[1])
        check("optimization_bound_committed_bytes", original == (HERE / filename).read_bytes(), filename)
    for row in binding["files"]:
        checked_file(row["path"], row["sha256"])
    check("one_development_evidence_optimization", binding["version"] == "v2" and binding["evidence_split"] == "development"
          and binding["architecture_or_seed_or_step_or_denominator_changes"] == 0 and not binding["validation_metric_used_to_choose_optimization"])
    old_manifest = json.loads((DATA / "MANIFEST.json").read_bytes())
    for row in old_manifest["public_files"] + old_manifest["private_files"]:
        checked_file(DATA / row["path"], row["sha256"])
    old = json.loads((DATA / "DATASET_INDEX.json").read_bytes())
    aliases = read("ALIASES.json")["observation_aliases"]
    old_observations = {aliases[row["id"]]: row for row in old["observations"]}
    cases = read("INPUT_INDEX.json")["cases"]
    features = {row["alias"]: row for row in read("FEATURES.json")["cases"]}
    prediction_index = {row["alias"]: row for row in read("PREDICTIONS.json")["cases"]}
    truth_index = {row["alias"]: row for row in read("SUPERVISION_INDEX.json")["observations"]}
    pairs = read("SUPERVISION_INDEX.json")["pairs"]
    check("600_unique_alias_inventory", len(cases) == len(features) == len(prediction_index) == len(old_observations) == 600
          and len({row["alias"] for row in cases}) == 600)
    check("600_inventory_503_dents24normals73failed", sum(row["state"] == "normal" for row in cases) == 24
          and sum(row["state"] == "damaged" and row["valid_for_learning"] for row in cases) == 503
          and sum(row["state"] == "damaged" and not row["valid_for_learning"] for row in cases) == 73)
    versions = ("v1", "v2")
    models, evaluations, calibration = {}, {}, {}
    initial_states, optimizer_state_counts = {}, {}
    for version in versions:
        identity = read("MODEL_IDENTITY_" + version + ".json")
        log = read("TRAIN_LOG_" + version + ".json")
        evaluations[version] = read("EVALUATION_" + version + ".json")
        calibration[version] = read("CALIBRATION_" + version + ".json")
        check("exact1200_completed_optimizer_steps", log["completed_steps"] == identity["completed_steps"] == 1200
              and len(log["steps"]) == 1200 and [row["step"] for row in log["steps"]] == list(range(1,1201)), version)
        check("dev_only_training_and_fixed_seed", log["validation_label_arrays_read"] == 0 and identity["seed"] == log["seed"] == 1729, version)
        for item in log["input_file_identities"]:
            checked_file(item["path"], item["sha256"])
        for key in ("initial_checkpoint", "final_checkpoint", "optimizer_checkpoint", "normalization"):
            checked_file(identity[key]["path"], identity[key]["sha256"])
        initial = torch.load(identity["initial_checkpoint"]["path"], map_location="cpu", weights_only=True)
        final = torch.load(identity["final_checkpoint"]["path"], map_location="cpu", weights_only=True)
        optimizer = torch.load(identity["optimizer_checkpoint"]["path"], map_location="cpu", weights_only=True)
        initial_states[version] = initial["state_dict"]
        check("initial_and_final_checkpoint_tensor_hashes", state_digest(initial["state_dict"]) == identity["initial_tensor_sha256"]
              and state_digest(final["state_dict"]) == identity["final_tensor_sha256"], version)
        optimizer_state_counts[version] = len(optimizer["optimizer"]["state"])
        check("stored_optimizer_stopped_at1200", optimizer["step"] == 1200 and all(float(item["step"]) == 1200 for item in optimizer["optimizer"]["state"].values()), version)
        model, _ = load_model(version)
        models[version] = model
        check("11969_trainable_architecture_parameters", sum(parameter.numel() for parameter in model.parameters()) == identity["parameters"] == 11969, version)
    first_log, second_log = read("TRAIN_LOG_v1.json"), read("TRAIN_LOG_v2.json")
    check("identical_initial_parameter_and_normalization_tensors", state_digest(initial_states["v1"]) == state_digest(initial_states["v2"]))
    check("identical_sampling_digests", first_log["logical_sampling_sha256"] == second_log["logical_sampling_sha256"])
    check("only_loss_term_changed", first_log["rank_coefficient"] == 0 and second_log["rank_coefficient"] == .1
          and all(first_log[key] == second_log[key] for key in ("seed", "steps_requested", "batch_rows", "parameters", "architecture", "learning_rate", "weight_decay")))
    sampling = package("private/TRAINING_INDICES.npz")["rows"]
    sample_columns = np.stack((sampling["pair_index"].astype(np.int64), sampling["F_row"].astype(np.int64), sampling["state"].astype(np.int64)), axis=-1)
    check("saved_training_sampling_digest", hashlib.sha256(sample_columns.astype("<i8").tobytes()).hexdigest() == first_log["logical_sampling_sha256"])
    check("1200x1024_exact_half_state_no_validation", sampling.shape == (1200,1024)
          and np.all(np.sum(sampling["state"] == 0, axis=1) == 512)
          and all(pairs[int(index)]["split"] == "development" and pairs[int(index)]["usable_for_training"] for index in np.unique(sampling["pair_index"])))
    eligible = [pair for pair in pairs if pair["split"] == "development" and pair["usable_for_training"]]
    groups = {pair["development_group"] for pair in eligible}
    case_weights = defaultdict(float)
    pair_weights = {}
    for pair in eligible:
        group = [row for row in eligible if row["development_group"] == pair["development_group"]]
        mesh = [row for row in group if row["mesh"] == pair["mesh"]]
        pose = [row for row in mesh if row["pose"] == pair["pose"]]
        roi = [row for row in pose if row["roi_alias"] == pair["roi_alias"]]
        divisor = len(groups) * len({row["mesh"] for row in group}) * len({row["pose"] for row in mesh}) * len({row["roi_alias"] for row in pose}) * len(roi)
        probability = 1. / divisor
        pair_weights[pair["index"]] = probability
        case_weights[pair["normal_alias"]] += .5 * probability
        case_weights[pair["damaged_alias"]] += .5 * probability
        check("independent_hierarchical_pair_probability", abs(probability-pair["probability_per_pair_event"]) < 1e-15, str(pair["index"]))
    check("338dev_pairs354physical_cases", len(eligible) == 338 and len(case_weights) == 354 and groups == {"horse_transfer", "face_transfer"})
    check("validation_and_invalid_zero_training_probability", all(pair["probability_per_pair_event"] == 0 for pair in pairs if pair not in eligible))
    spec = importlib.util.spec_from_file_location("_verify_data001_current_reader", DATA / "data_io.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    feature_cache, masks, replay_logits, numerical_rows = {}, {}, {version:{} for version in versions}, {version:[] for version in versions}
    ring_short, ring_minimum = Counter(), {count:1024 for count in (16,48,128,384,1024)}
    coverage_rows, wholly_changed = [], Counter()
    feature_replay_cases = {}
    two_query_aliases = {cases[0]["alias"], cases[300]["alias"]}
    maximum_prediction_error, forward_calls = 0., 0
    for case in cases:
        alias = case["alias"]
        old_case = old_observations[alias]
        check("case_split_state_and_validity_match_source", all(case[key] == old_case[old_key] for key,old_key in (("split","split"),("state","state"),("valid_for_learning","usable_for_training"))), alias)
        current = package(case["input"]["path"], case["input"]["sha256"])
        check("current_packet_whitelist", set(current) == {"vertices","faces","F_source_ids"}, alias)
        original = reader.read_current(old_case)
        check("exact_current_source_reconstruction", array_equal(current["vertices"], original["vertices"])
              and array_equal(current["faces"], original["faces"]) and array_equal(current["F_source_ids"], original["region_source_ids"]), alias)
        packet = package(features[alias]["path"], features[alias]["sha256"])
        feature_cache[alias] = packet["features"]
        F = current["F_source_ids"].astype(np.int64)
        check("complete384_feature_mapping", packet["features"].shape == (384,5,16) and array_equal(packet["source_ids"], F)
              and int(packet["valid_mask"].sum()) == features[alias]["valid_points"], alias)
        check("R16_log_spacing_first_channel_zero", np.all(packet["features"][:,0,15] == 0), alias)
        truth = package(truth_index[alias]["path"])
        with np.load(DATA / old_case["supervision"], allow_pickle=False) as saved_truth:
            check("exact_reused_supervision_mask_delta", array_equal(truth["mask"], saved_truth["changed_mask"])
                  and array_equal(truth["actual_delta"], saved_truth["actual_delta"]), alias)
        mask = truth["mask"].astype(bool)
        masks[alias] = mask
        points = current["vertices"][current["faces"]]
        face_area = np.linalg.norm(np.cross(points[:,1]-points[:,0], points[:,2]-points[:,0]), axis=1) / 2
        full_area = np.bincount(current["faces"].ravel(), weights=np.repeat(face_area/3,3), minlength=len(current["vertices"]))
        check("current_lumped_F_area_independent_reduction", np.allclose(packet["area"], full_area[F], rtol=1e-12, atol=1e-15), alias)
        context = package(features[alias]["context"]["path"], features[alias]["context"]["sha256"])["neighbor_ids"]
        check("1024_current_context_ID_domain", context.shape == (384,1024) and context.min() >= 0 and context.max() < len(current["vertices"]), alias)
        distance = np.linalg.norm(current["vertices"][context] - current["vertices"][F,None,:], axis=2)
        for position,count in enumerate((16,48,128,384,1024)):
            cached_count = packet["ring_counts"][:,position]
            ring_minimum[count] = min(ring_minimum[count], int(cached_count.min()))
            ring_short[count] += int((cached_count < 6).sum())
            radius = packet["scale_radii"][:,position]
            tolerance = 64*np.finfo(float).eps*np.maximum(radius,1e-30)
            lower = (distance[:,:count] > (.6*radius+tolerance)[:,None]).sum(axis=1)
            upper = (distance[:,:count] >= (.6*radius-tolerance)[:,None]).sum(axis=1)
            check("ring_counts_geometric_boundary_tolerance", np.all((cached_count>=lower)&(cached_count<=upper)), alias+"_k"+str(count))
        if alias in two_query_aliases:
            feature_replay_cases[alias] = dict(vertices=current["vertices"].copy(), faces=current["faces"].copy(), F=F[:1], expected=packet["features"][:1].copy())
        scale_group, old_whole = "normal", False
        if case["state"] == "damaged":
            radius = .05*float(np.linalg.norm(np.ptp(current["vertices"],axis=0)))
            near = np.linalg.norm(current["vertices"]-current["vertices"][old_case["center_source_id"]],axis=1) < radius
            changed = np.zeros(len(current["vertices"]),dtype=bool)
            changed[F] = mask
            old_whole = bool(changed[near].all())
            ratio = old_case["radius"] / radius
            scale_group = "r/R<=.5" if ratio <= .5 else ".5<r/R<=1" if ratio <= 1 else "r/R>1"
            if case["valid_for_learning"]:
                wholly_changed[case["split"]] += int(old_whole)
                fraction = changed[context].mean(axis=1)
                coverage_rows.append(dict(alias=alias,split=case["split"],changed_source_points=int(mask.sum()),
                    maximal_context_damaged_fraction_min=float(fraction.min()),maximal_context_damaged_fraction_max=float(fraction.max()),
                    maximal_context_has_unchanged_points_for_all_F=bool((fraction<1).all()),old_center_neighborhood_wholly_damaged=old_whole))
        combined = package(prediction_index[alias]["path"], prediction_index[alias]["sha256"])
        check("prediction_current_geometry_binding", prediction_index[alias]["current_input_sha256"] == case["input"]["sha256"]
              and array_equal(combined["source_ids"], F), alias)
        for version, field in (("v1","initial_probability"),("v2","optimized_probability")):
            output = predict_features(models[version], packet["features"], packet["valid_mask"])
            forward_calls += 1
            replay_logits[version][alias] = output["logits"]
            recorded = next(row for row in evaluations[version]["cases"] if row["alias"] == alias)
            separate = package(recorded["prediction"]["path"], recorded["prediction"]["sha256"])
            check("bitwise_replayed_probability_and_logits", array_equal(output["scores"], combined[field])
                  and array_equal(output["scores"], separate["probability"]) and array_equal(output["logits"], separate["logits"]), alias+"_"+version)
            maximum_prediction_error = max(maximum_prediction_error, float(np.max(np.abs(output["scores"].astype(float)-combined[field]))))
            check("retained_failed_observation_status", recorded["scored"] == case["valid_for_learning"]
                  and recorded["generator_failures"] == old_case.get("failures",[]), alias+"_"+version)
            result = dict(alias=alias,split=case["split"],state=case["state"],roi_alias=case["roi_alias"],source=old_case["mesh_id"],scale_group=scale_group,scored=case["valid_for_learning"])
            if case["valid_for_learning"]:
                for method, score in (("geometry",packet["baseline_score"]),("learned",output["scores"])):
                    result[method] = independent_metrics(score,calibration[version]["thresholds"][method],packet["area"],mask,F)
                    for key,value in result[method].items():
                        reference = recorded[method][key]
                        equal = value == reference if value is None or isinstance(value,(bool,int)) else abs(value-reference) <= 1e-12
                        check("independent_metric_"+method+"_"+key,equal,alias+"_"+version)
            numerical_rows[version].append(result)
    original_coverage = read("CONTEXT_COVERAGE.json")
    check("full503_posthoc_context_coverage", coverage_rows == original_coverage["cases"] and len(coverage_rows) == 503)
    check("old_center_context_8dev55validation", wholly_changed["development"] == 8 and wholly_changed["validation"] == 55
          and dict(wholly_changed) == original_coverage["old_center_fully_changed_counts"])
    weighted_mean = sum(weight * feature_cache[alias].astype(np.float64).mean(axis=(0,1)) for alias,weight in sorted(case_weights.items()))
    weighted_variance = sum(weight * np.square(feature_cache[alias].astype(np.float64)-weighted_mean).mean(axis=(0,1)) for alias,weight in sorted(case_weights.items()))
    expected_pi = sum(.5*probability*float(masks[pairs[index]["damaged_alias"]].mean()) for index,probability in pair_weights.items())
    norm = read("NORMALIZATION.json")
    check("development_only_weighted_normalization_mean_variance", np.allclose(weighted_mean,norm["mean"],rtol=1e-12,atol=1e-14)
          and np.allclose(np.sqrt(weighted_variance),norm["standard_deviation"],rtol=1e-12,atol=1e-14)
          and set(norm["development_case_probabilities"]) == set(case_weights) and norm["validation_statistics_used"] == 0)
    check("fresh_dev_only_positive_prior", abs(expected_pi-norm["positive_label_prior"]) < 1e-14
          and abs((1-expected_pi)/expected_pi-norm["positive_weight"]) < 1e-12)
    normal_development = [case for case in cases if case["split"]=="development" and case["state"]=="normal"]
    side_tables, independent_gates = {}, {}
    for version in versions:
        diag_violation = diag_gap = diag_unchanged = 0.
        for pair in eligible:
            probability = pair_weights[pair["index"]]
            positive = masks[pair["damaged_alias"]]
            gap = replay_logits[version][pair["damaged_alias"]] - replay_logits[version][pair["normal_alias"]]
            diag_violation += probability*float((gap[positive]<1).mean())
            diag_gap += probability*float(gap[positive].mean())
            diag_unchanged += probability*float(np.abs(gap[~positive]).mean())
        diagnostic = read("DEV_DIAGNOSTICS_"+version+".json")
        check("dev_paired_optimization_evidence_recomputed", abs(diag_violation-diagnostic["weighted_positive_margin_violation_fraction"]) < 1e-12
              and abs(diag_gap-diagnostic["weighted_positive_mean_logit_gap"]) < 1e-12
              and abs(diag_unchanged-diagnostic["weighted_unchanged_mean_absolute_logit_gap"]) < 1e-12, version)
        learned_maxima = [float(package("private/predictions/"+case["alias"]+"_"+version+".npz")["probability"].max()) for case in normal_development]
        geometry_maxima = [float(package(features[case["alias"]]["path"])["baseline_score"].max()) for case in normal_development]
        check("q95_higher16dev_normals_is_maximum", len(normal_development) == 16
              and calibration[version]["thresholds"]["learned"] == max(learned_maxima)
              and calibration[version]["thresholds"]["geometry"] == max(geometry_maxima)
              and calibration[version]["validation_labels_read"] == calibration[version]["validation_statistics_used"] == 0, version)
        valid = [row for row in numerical_rows[version] if row["split"]=="validation" and row["state"]=="damaged" and row["scored"]]
        normals = [row for row in numerical_rows[version] if row["split"]=="validation" and row["state"]=="normal"]
        check("165_validation_dents8_normals_full_denominator", len(valid)==165 and len(normals)==8, version)
        observation_macro = {method:float(np.mean([row[method]["area_budget_recall"] for row in valid])) for method in ("geometry","learned")}
        false_normal = sum(row["learned"]["anomaly_any"] for row in normals)
        independent_gates[version] = dict(macro_area_recall_ge060=observation_macro["learned"]>=.6,
            gain_over_geometry_ge010=observation_macro["learned"]-observation_macro["geometry"]>=.1,
            normal_false_cases_le1_of8=false_normal<=1,
            nonempty_anomaly_predictions_on_damaged=any(row["learned"]["anomaly_any"] for row in valid))
        check("original_observation_equal_gate_unchanged", independent_gates[version] == evaluations[version]["gates"], version)
        by_roi = {roi:{method:float(np.mean([row[method]["area_budget_recall"] for row in valid if row["roi_alias"]==roi]))
                       for method in ("geometry","learned")} for roi in sorted({row["roi_alias"] for row in valid})}
        by_source = {source:dict(count=sum(row["source"]==source for row in valid),
            **{method:float(np.mean([row[method]["area_budget_recall"] for row in valid if row["source"]==source])) for method in ("geometry","learned")})
            for source in sorted({row["source"] for row in valid})}
        by_scale = {scale:dict(count=sum(row["scale_group"]==scale for row in valid),
            **{method:float(np.mean([row[method]["area_budget_recall"] for row in valid if row["scale_group"]==scale])) for method in ("geometry","learned")})
            for scale in sorted({row["scale_group"] for row in valid})}
        side_tables[version] = dict(original165_observation_equal_area_recall=observation_macro,normal_false_cases=false_normal,
            roi_equal_area_recall={method:float(np.mean([row[method] for row in by_roi.values()])) for method in ("geometry","learned")},
            by_ROI=by_roi,by_source=by_source,by_validation_scale=by_scale,
            anomaly_damaged_report_cases=sum(row["learned"]["anomaly_any"] for row in valid),
            anomaly_damaged_area_recall=float(np.mean([row["learned"]["anomaly_area_recall"] for row in valid])))
    check("optimized_v2_final_candidate_rejected_without_selection", not all(independent_gates["v2"].values())
          and read("PREDICTIONS.json")["models"]["optimized"]["version"]=="v2")
    from features import describe_current
    transformation_checks = []
    angle = .37
    axis = np.array((1.,2.,3.)) / np.linalg.norm((1.,2.,3.))
    skew = np.array(((0.,-axis[2],axis[1]),(axis[2],0.,-axis[0]),(-axis[1],axis[0],0.)))
    rotation = np.eye(3)*np.cos(angle)+(1-np.cos(angle))*np.outer(axis,axis)+np.sin(angle)*skew
    for alias,item in feature_replay_cases.items():
        recomputed = describe_current(item["vertices"],item["faces"],item["F"])["features"]
        check("two_fixed_current_query_descriptor_replay", np.allclose(recomputed,item["expected"],rtol=1e-6,atol=1e-7), alias)
        diagonal = float(np.linalg.norm(np.ptp(item["vertices"],axis=0)))
        translation = np.array((.125,-.25,.5))*diagonal
        translated = describe_current(item["vertices"]+translation,item["faces"],item["F"])["features"]
        rotated = describe_current(item["vertices"]@rotation.T,item["faces"],item["F"])["features"]
        transformation_checks.append(dict(alias=alias,source_vertex_id=int(item["F"][0]),
            original_replay_max_abs_error=float(np.max(np.abs(recomputed-item["expected"]))),
            translation_max_abs_error=float(np.max(np.abs(translated-recomputed))),rotation_max_abs_error=float(np.max(np.abs(rotated-recomputed))),
            diagnostic_tolerance=1e-4,translation_within_tolerance=bool(np.allclose(translated,recomputed,rtol=1e-4,atol=1e-4)),
            rotation_within_tolerance=bool(np.allclose(rotated,recomputed,rtol=1e-4,atol=1e-4)),
            scope="two predetermined source-order queries only. Six-coefficient ridge and tangent-axis choice do not establish exact arbitrary-rotation invariance."))
    report = dict(cycle_id="M6-TASK-PERCEPTION-001",status="passed_fixed_inference_and_evidence_verification" if not failures else "failed",
        checks=checks,check_count=len(checks),failures=failures,input_file_identities=list(checked_files.values()),
        inventory=dict(unique_observations=600,valid_dent_pairs=503,normal_observations=24,retained_failed_dents=73,validation_dents=165,validation_normals=8),
        inference_replay=dict(versions=list(versions),observation_predictions=1200,point_predictions=1200*384,model_forward_calls=forward_calls,
                             maximum_absolute_probability_difference=maximum_prediction_error,bitwise_required=True),
        training_replays=0,optimizer_steps=0,optimizer_checkpoint_states_inspected=optimizer_state_counts,
        original_candidate_training_runs=2,original_steps_per_run=1200,model_selection="fixed v2 remains final and rejected by original gate, v1 retained as comparison",
        hierarchical_positive_label_prior=expected_pi,normalization_scope="development only, independently reconstructed group/mesh/pose/ROI/combination probabilities",
        context_coverage_cases=len(coverage_rows),old_center_context_wholly_changed=dict(wholly_changed),
        ring_counts=dict(scale_minimum_points={str(key):value for key,value in ring_minimum.items()},
                         scale_query_rows_with_fewer_than6_ring_points={str(key):ring_short[key] for key in ring_minimum},
                         total_query_scale_rows=600*384*5,interpretation="under-six ring rows use the frozen ridge solution, retain them without scale/case replacement"),
        spacing_definition="distance to the 16th returned current nearest vertex, including the query itself. First-scale log(radius/R16) is identically zero.",
        validation_side_tables=side_tables,independent_original_gates=independent_gates,two_query_rigid_transform_diagnostics=transformation_checks,
        independent_metric_scope="all per-case AUC/AP, attention and anomaly area metrics, same165 observation-equal gate. ROI/source/scale tables are explanatory side results",
        resources=process_resources(),wall_s_before_write=time.perf_counter()-started,CPU_s_before_write=time.process_time()-cpu,
        scope="inference and evidence verification only, no optimizer object, optimizer step, training replay, threshold change or model choice")
    write("private/verification/VERIFY_FULL.json",report)
    summary={key:value for key,value in report.items() if key not in ("checks","input_file_identities")}
    summary["full_evidence"]=identity(HERE/"private/verification/VERIFY_FULL.json")
    summary["detail_scope"]="full check rows and all actual reused input identities remain in the private byte-bound evidence"
    write("VERIFY.json",summary)
    print(report["status"],"checks",len(checks),"failures",len(failures),"inference forwards",forward_calls,flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
