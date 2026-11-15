"""Train exactly one frozen-feature perception head for the fixed1200 steps."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from head import PerceptionHead, configure_torch, file_record, load_frozen_encoder, measure, process_resources, save_predictions, tensor_digest, write_json
import numpy as np
import torch


def numpy_rng_json(generator):
    name, state, position, has_gaussian, cached_gaussian = generator.get_state()
    return {"algorithm": name, "keys": state.tolist(), "position": int(position),
            "has_gaussian": int(has_gaussian), "cached_gaussian": float(cached_gaussian)}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    configure_torch()
    if (HERE / "TRAIN_LOG.json").exists() or (HERE / "private/model/head_final.pth").exists():
        raise RuntimeError("training_artifact_exists_inspect_before_any_recovery")
    timings, identities = {}, {}

    def record(path, expected=None):
        row = file_record(path)
        if expected is not None and row["sha256"] != expected:
            raise ValueError("training_input_identity_changed_" + str(path))
        identities[row["path"]] = row
        return row

    with measure(timings, "development_feature_index_and_whitelist_read"):
        feature_index = json.loads((HERE / "FEATURES.json").read_bytes())
        if feature_index["status"] != "completed_fixed348_encoder_features":
            raise ValueError("all_fixed_features_not_complete")
        record(HERE / "FEATURES.json")
        whitelist = {row["id"]: row for row in json.loads((HERE / "INPUT_WHITELIST.json").read_bytes())["cases"]}
        cases = sorted([row for row in feature_index["cases"] if row["purpose"] == "development_train_pool"], key=lambda row: row["id"])
        if len(cases) != 231 or sum(row["normal_control"] for row in cases) != 33:
            raise ValueError("training_requires231_development_cases33_normal")
    frozen_model, decoder_guard, checkpoint = load_frozen_encoder(timings)
    encoder_before = tensor_digest(frozen_model.encoder.state_dict())
    if encoder_before != feature_index["encoder_initial_tensor_sha256"]:
        raise ValueError("encoder_differs_from_feature_generation")
    with measure(timings, "development_only_normalization_first_pass"):
        total = np.zeros(1024, dtype=np.float64)
        total_points = 0
        for case in cases:
            record(case["path"], case["sha256"])
            with np.load(case["path"], allow_pickle=False) as saved:
                values = saved["features"].astype(np.float64)
            total += np.sum(values, axis=0, dtype=np.float64)
            total_points += len(values)
        mean = total / total_points
    with measure(timings, "development_only_normalization_second_pass"):
        squared = np.zeros(1024, dtype=np.float64)
        for case in cases:
            with np.load(case["path"], allow_pickle=False) as saved:
                delta = saved["features"].astype(np.float64) - mean
            squared += np.sum(delta * delta, axis=0, dtype=np.float64)
        standard_deviation = np.sqrt(squared / total_points)
        divisor = standard_deviation.copy()
        divisor[standard_deviation < 1.0e-6] = 1.0
        if not np.isfinite(mean).all() or not np.isfinite(divisor).all():
            raise ValueError("nonfinite_development_normalization")
    with measure(timings, "normalization_save_and_hash"):
        path = HERE / "private/model/normalization.npz"
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, mean=mean, standard_deviation=standard_deviation, divisor=divisor)
        normalization_record = file_record(path)
        normalization_report = {"cycle_id": "M6-PERCEPTION-001", "source_cases": [row["id"] for row in cases],
                                "case_count": 231, "F_points": total_points, "channels": 1024,
                                "ddof": 0, "threshold": 1.0e-6,
                                "divisor_replaced_channels": int(np.count_nonzero(standard_deviation < 1.0e-6)),
                                "formula": "two float64 streaming passes; divisor1 when std<1e-6; standardize float64 then cast float32",
                                "path": str(path), "sha256": normalization_record["sha256"], "validation_statistics_used": 0}
        write_json("NORMALIZATION.json", normalization_report)
        normalization_record.update(json_path=str(HERE / "NORMALIZATION.json"), json_sha256=file_record(HERE / "NORMALIZATION.json")["sha256"])
    with measure(timings, "development_feature_standardization_and_label_read"):
        values, targets, offsets, case_sizes, positive_fractions = [], [], [0], [], []
        invalid_points = 0
        for case in cases:
            with np.load(case["path"], allow_pickle=False) as saved:
                feature = ((saved["features"].astype(np.float64) - mean) / divisor).astype(np.float32)
                free_context = saved["free_context_ids"].copy()
                invalid_points += int(np.count_nonzero(~saved["valid_mask"]))
            observed = Path(whitelist[case["id"]]["observed"]["path"])
            label_path = observed.parents[1] / "labels" / (observed.stem + ".npz")
            record(label_path)
            with np.load(label_path, allow_pickle=False) as labels:
                target = labels["damaged_mask"][free_context].astype(np.float32)
            values.append(feature)
            targets.append(target)
            case_sizes.append(len(feature))
            offsets.append(offsets[-1] + len(feature))
            positive_fractions.append(float(np.count_nonzero(target) / len(target)))
        train_features = torch.from_numpy(np.concatenate(values))
        train_targets = torch.from_numpy(np.concatenate(targets))
        del values, targets
        offsets = np.asarray(offsets, dtype=np.int64)
        case_sizes = np.asarray(case_sizes, dtype=np.int64)
        pi = float(np.mean(positive_fractions))
        if not 0 < pi < 1:
            raise ValueError("development_case_equal_class_prior_invalid")
        positive_weight = (1.0 - pi) / pi
    with measure(timings, "head_initialization_and_initial_checkpoint"):
        torch.manual_seed(1729)
        model = PerceptionHead().cpu()
        if sum(parameter.numel() for parameter in model.parameters()) != 65665:
            raise ValueError("head_parameter_count_changed")
        optimizer = torch.optim.AdamW(model.parameters(), lr=1.0e-3, weight_decay=1.0e-4,
                                     betas=(0.9, 0.999), eps=1.0e-8, foreach=False)
        loss_function = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(positive_weight, dtype=torch.float32))
        sampler = np.random.RandomState(1729)
        initial_tensor_hash = tensor_digest(model.state_dict())
        initial_path = HERE / "private/model/head_initial.pth"
        torch.save({"step": 0, "state_dict": model.state_dict(), "optimizer": optimizer.state_dict(),
                    "torch_rng_state": torch.get_rng_state(), "sampling_rng": numpy_rng_json(sampler)}, initial_path)
        initial_record = file_record(initial_path)
    training_log = {"cycle_id": "M6-PERCEPTION-001", "status": "training", "steps_requested": 1200,
                    "seed": 1729, "batch_size": 1024, "development_cases": 231, "development_F_points": total_points,
                    "case_ids": [row["id"] for row in cases], "case_sizes": case_sizes.tolist(),
                    "sampling": "independent RandomState1729, alternate uniform case then uniform F row for each sample",
                    "case_equal_pi": pi, "positive_weight": positive_weight, "case_positive_fractions": positive_fractions,
                    "invalid_feature_points_in_training": invalid_points, "invalid_feature_policy": "zeros included in full-F normalization and sampling, inference score0",
                    "head_parameters": 65665, "encoder_parameters": 702464, "active_parameters": 768129,
                    "head_architecture": "Linear1024to64 GELU Linear64to1", "initial_checkpoint": initial_record,
                    "normalization": normalization_record, "steps": [], "timings": timings,
                    "validation_labels_read": 0, "encoder_parameters_trained": 0, "decoder_forward_calls": 0,
                    "training_runs": 1, "source_sha256": {name: file_record(HERE / name)["sha256"] for name in ("head.py", "train_head.py")}}
    write_json("TRAIN_LOG.json", training_log)
    case_trajectory = np.empty((1200, 1024), dtype=np.int32)
    row_trajectory = np.empty((1200, 1024), dtype=np.int32)
    model.train()
    for step in range(1200):
        with measure(timings, "uniform_case_then_F_sampling"):
            for sample in range(1024):
                case_id = int(sampler.randint(len(cases)))
                row_id = int(sampler.randint(case_sizes[case_id]))
                case_trajectory[step, sample] = case_id
                row_trajectory[step, sample] = row_id
            global_rows = offsets[case_trajectory[step]] + row_trajectory[step]
            indices = torch.from_numpy(global_rows)
        with measure(timings, "head_forward_loss_backward_optimizer"):
            optimizer.zero_grad(set_to_none=True)
            logits = model(train_features[indices])
            target = train_targets[indices]
            loss = loss_function(logits, target)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite_training_loss_at_step" + str(step + 1))
            loss.backward()
            optimizer.step()
        training_log["steps"].append({"step": step + 1, "loss": float(loss.detach()),
                                      "positive_samples": int(torch.count_nonzero(target)),
                                      "sampled_case_count": int(len(np.unique(case_trajectory[step])))})
        if (step + 1) % 100 == 0:
            training_log["completed_steps"] = step + 1
            write_json("TRAIN_LOG.json", training_log)
            print(json.dumps({"step": step + 1, "loss": training_log["steps"][-1]["loss"]}), flush=True)
    with measure(timings, "final_head_optimizer_RNG_and_sampling_save"):
        final_path = HERE / "private/model/head_final.pth"
        torch.save({"step": 1200, "state_dict": model.state_dict(), "optimizer": optimizer.state_dict(),
                    "torch_rng_state": torch.get_rng_state(), "sampling_rng": numpy_rng_json(sampler)}, final_path)
        final_record = file_record(final_path)
        sampling_path = HERE / "private/training/sampling.npz"
        sampling_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(sampling_path, case_index=case_trajectory, F_row_index=row_trajectory)
        sampling_record = file_record(sampling_path)
        encoder_after = tensor_digest(frozen_model.encoder.state_dict())
        if encoder_after != encoder_before or decoder_guard["decoder_forward_calls"]:
            raise ValueError("frozen_encoder_mutated_during_head_training")
        encoder_path = HERE / "private/model/encoder_after_head_training.pth"
        torch.save(frozen_model.encoder.state_dict(), encoder_path)
    del train_features, train_targets
    identity = {"cycle_id": "M6-PERCEPTION-001", "encoder_parameters": 702464, "head_parameters": 65665,
                "active_parameters": 768129, "official_full_checkpoint_parameters": feature_index["full_upstream_checkpoint_parameters"],
                "official_checkpoint_sha256": checkpoint["sha256"],
                "encoder_initial_tensor_sha256": encoder_before, "encoder_final_tensor_sha256": encoder_after,
                "encoder_feature_initial_tensor_sha256": feature_index["encoder_initial_tensor_sha256"],
                "encoder_feature_final_tensor_sha256": feature_index["encoder_final_tensor_sha256"],
                "encoder_post_training_checkpoint": file_record(encoder_path),
                "head_initial_sha256": initial_record["sha256"], "head_final_sha256": final_record["sha256"],
                "head_initial_tensor_sha256": initial_tensor_hash, "head_final_tensor_sha256": tensor_digest(model.state_dict()),
                "normalization_sha256": normalization_record["sha256"], "decoder_forward_calls": 0,
                "encoder_parameter_or_BN_training_updates": 0, "training_runs": 1, "head_steps": 1200,
                "scope": "active encoder and head identities, official full payload also contains an unused displacement decoder"}
    write_json("MODEL_IDENTITY.json", identity)
    training_log.update(status="completed_exact1200_step_head_training", completed_steps=1200,
                        final_checkpoint=final_record, sampling_trajectory=sampling_record,
                        encoder_initial_tensor_sha256=encoder_before, encoder_final_tensor_sha256=encoder_after,
                        model_identity_path=str(HERE / "MODEL_IDENTITY.json"),
                        model_identity_sha256=file_record(HERE / "MODEL_IDENTITY.json")["sha256"],
                        development_predictions_status="pending")
    write_json("TRAIN_LOG.json", training_log)
    prediction_timings = {}
    with measure(timings, "development_head_prediction_total"):
        save_predictions(cases, model, {"mean": mean, "divisor": divisor}, "PREDICTIONS_DEVELOPMENT.json",
                         prediction_timings, final_record["sha256"])
    training_log.update(status="completed_exact1200_step_head_training", completed_steps=1200,
                        final_checkpoint=final_record, sampling_trajectory=sampling_record,
                        encoder_initial_tensor_sha256=encoder_before, encoder_final_tensor_sha256=encoder_after,
                        model_identity_path=str(HERE / "MODEL_IDENTITY.json"),
                        model_identity_sha256=file_record(HERE / "MODEL_IDENTITY.json")["sha256"],
                        input_file_identities=list(identities.values()),
                        development_predictions_status="completed231",
                        development_prediction_timings=prediction_timings,
                        wall_s_before_final_report=time.perf_counter() - started,
                        CPU_s_before_final_report=time.process_time() - cpu,
                        bootstrap_wall_s_before_final_report=time.perf_counter() - BOOT_WALL,
                        bootstrap_CPU_s_before_final_report=time.process_time() - BOOT_CPU,
                        own_process_before_report=process_resources(),
                        measurement_scope="feature first-extraction cost in FEATURES and root phase, train timings include imports/load/normalization/training/checkpoints/development head prediction")
    write_json("TRAIN_LOG.json", training_log)
    print(json.dumps({"status": training_log["status"], "steps": 1200, "pi": pi,
                      "head_final_sha256": final_record["sha256"]}))


if __name__ == "__main__":
    main()
