"""Two bounded versions of one shared surface encoder with frozen pair indices."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from model import SurfacePerception, configure_torch, file_record, predict_features, tensor_digest, PARAMETERS
import numpy as np
import torch

ARCHITECTURE = "shared16to32to32_five_scales_concat160to64to1"


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def load_array_package(path, identities, expected_sha256=None):
    path = Path(path)
    if not path.is_absolute():
        path = HERE / path
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("input_identity_changed_" + str(path))
    identities[str(path)] = dict(path=str(path), bytes=len(raw), sha256=digest)
    with np.load(io.BytesIO(raw), allow_pickle=False) as package:
        return {key: package[key] for key in package.files}


def load_training_data(identities):
    index = read("SUPERVISION_INDEX.json")
    feature_index = read("FEATURES.json")
    for name in ("SUPERVISION_INDEX.json", "FEATURES.json", "PLAN.json", "PLAN_FREEZE.json"):
        identities[name] = file_record(HERE / name)
    cases = {row["alias"]: row for row in feature_index["cases"]}
    if len(cases) != len(feature_index["cases"]):
        raise ValueError("duplicate_feature_alias")
    pairs = index["pairs"]
    probabilities = defaultdict(float)
    labels = {}
    pi = 0.
    label_reads = 0
    for position, pair in enumerate(pairs):
        if pair["index"] != position:
            raise ValueError("pair_index_order_changed")
        probability = float(pair["probability_per_pair_event"])
        if probability == 0:
            continue
        if pair["split"] != "development" or not pair["usable_for_training"] or probability < 0:
            raise ValueError("nondevelopment_or_invalid_pair_has_training_weight")
        normal, damaged = pair["normal_alias"], pair["damaged_alias"]
        truth = load_array_package(pair["mask_path"], identities)
        mask = truth["mask"].astype(bool)
        if mask.shape != (384,):
            raise ValueError("training_mask_requires_384_F_rows")
        labels[normal] = np.zeros(384, dtype=np.float32)
        labels[damaged] = mask.astype(np.float32)
        probabilities[normal] += .5 * probability
        probabilities[damaged] += .5 * probability
        pi += .5 * probability * float(mask.mean())
        label_reads += 1
    if not np.isclose(sum(probabilities.values()), 1., atol=1e-12, rtol=0) or not 0 < pi < 1:
        raise ValueError("development_pair_weights_invalid")
    aliases = sorted(probabilities)
    features, targets, source_ids, valid_masks = [], [], {}, {}
    offsets = {}
    for alias in aliases:
        case = cases[alias]
        if case["split"] != "development" or not case["valid_for_learning"]:
            raise ValueError("nondevelopment_or_unusable_feature_in_training")
        saved = load_array_package(case["path"], identities, case["sha256"])
        values = saved["features"].astype(np.float32)
        valid = saved["valid_mask"].astype(bool)
        if values.shape != (384, 5, 16) or valid.shape != (384,) or not np.isfinite(values).all():
            raise ValueError("invalid_training_feature_shape_or_values")
        offsets[alias] = len(features) * 384
        features.append(values)
        targets.append(labels[alias])
        source_ids[alias] = saved["source_ids"].copy()
        valid_masks[alias] = valid
    for pair in pairs:
        if pair["probability_per_pair_event"] > 0:
            if not np.array_equal(source_ids[pair["normal_alias"]], source_ids[pair["damaged_alias"]]):
                raise ValueError("normal_damaged_source_mapping_mismatch")
    packed_features = np.concatenate(features)
    packed_targets = np.concatenate(targets)
    return dict(pairs=pairs, aliases=aliases, probabilities=dict(probabilities), offsets=offsets,
                features=packed_features, targets=packed_targets, source_ids=source_ids, valid_masks=valid_masks,
                pi=pi, label_arrays_read=label_reads, invalid_feature_points=sum(int((~mask).sum()) for mask in valid_masks.values()))


def normalization(data, version, identities):
    path = HERE / "private/model/normalization.npz"
    if version == "v1":
        total = np.zeros(16, dtype=np.float64)
        for alias in data["aliases"]:
            start = data["offsets"][alias]
            feature = data["features"][start:start + 384].astype(np.float64)
            total += data["probabilities"][alias] * feature.mean(axis=(0, 1))
        variance = np.zeros(16, dtype=np.float64)
        for alias in data["aliases"]:
            start = data["offsets"][alias]
            delta = data["features"][start:start + 384].astype(np.float64) - total
            variance += data["probabilities"][alias] * np.square(delta).mean(axis=(0, 1))
        standard_deviation = np.sqrt(variance)
        divisor = np.where(standard_deviation < 1e-6, 1., standard_deviation)
        np.savez_compressed(path, mean=total, standard_deviation=standard_deviation, divisor=divisor)
        write("NORMALIZATION.json", dict(source="development paired-state hierarchical expectation", channels=16,
              scale_reduction="all five scale positions share per-channel statistics", mean=total.tolist(),
              standard_deviation=standard_deviation.tolist(), divisor=divisor.tolist(),
              storage_dtype="float64", model_buffer_and_arithmetic_dtype="float32",
              ddof=0, divisor_replacement_threshold=1e-6, development_case_probabilities=data["probabilities"],
              positive_label_prior=data["pi"], positive_weight=(1-data["pi"])/data["pi"], validation_statistics_used=0,
              file=file_record(path)))
    report = read("NORMALIZATION.json")
    saved = load_array_package(path, identities, report["file"]["sha256"])
    if report["development_case_probabilities"] != data["probabilities"] or abs(report["positive_label_prior"]-data["pi"]) > 1e-15:
        raise ValueError("normalization_membership_or_prior_changed")
    return saved, report


def development_diagnostics(model, data, version):
    predictions = {}
    for alias in data["aliases"]:
        start = data["offsets"][alias]
        predictions[alias] = predict_features(model, data["features"][start:start+384], data["valid_masks"][alias])
    rows = []
    weighted_violation = weighted_gap = weighted_abs_unchanged = 0.
    for pair in data["pairs"]:
        probability = float(pair["probability_per_pair_event"])
        if probability == 0:
            continue
        normal = predictions[pair["normal_alias"]]
        damaged = predictions[pair["damaged_alias"]]
        start = data["offsets"][pair["damaged_alias"]]
        positive = data["targets"][start:start+384] > 0
        gap = damaged["logits"] - normal["logits"]
        violation = float(np.mean(gap[positive] < 1.))
        positive_gap = float(np.mean(gap[positive]))
        unchanged_abs_gap = float(np.mean(np.abs(gap[~positive]))) if (~positive).any() else 0.
        rows.append(dict(pair_index=pair["index"], normal_alias=pair["normal_alias"], damaged_alias=pair["damaged_alias"],
                         pair_probability=probability, positive_points=int(positive.sum()),
                         positive_margin_violation_fraction=violation, positive_mean_logit_gap=positive_gap,
                         unchanged_mean_absolute_logit_gap=unchanged_abs_gap))
        weighted_violation += probability * violation
        weighted_gap += probability * positive_gap
        weighted_abs_unchanged += probability * unchanged_abs_gap
    report = dict(version=version, split="development", pairs=rows, validation_supervision_reads=0,
                  paired_margin=1., weighted_positive_margin_violation_fraction=weighted_violation,
                  weighted_positive_mean_logit_gap=weighted_gap,
                  weighted_unchanged_mean_absolute_logit_gap=weighted_abs_unchanged,
                  use="development evidence for one paired-ranking optimization, no validation-based candidate selection")
    write("DEV_DIAGNOSTICS_" + version + ".json", report)
    return report


def main():
    started, cpu = time.perf_counter(), time.process_time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=("v1", "v2"), required=True)
    version = parser.parse_args().version
    configure_torch()
    destination = HERE / "private/model"
    destination.mkdir(parents=True, exist_ok=True)
    if (HERE / ("TRAIN_LOG_" + version + ".json")).exists() or (destination / (version+"_initial.pth")).exists():
        raise RuntimeError("training_version_already_attempted_inspect_before_recovery")
    identities = {}
    for row in read("PLAN_FREEZE.json")["files"]:
        path = Path(row["path"])
        if not path.is_absolute():
            path = HERE / path
        if file_record(path)["sha256"] != row["sha256"]:
            raise ValueError("frozen_plan_identity_changed_"+str(path))
    optimization = None
    if version == "v2":
        if not (HERE/"DEV_DIAGNOSTICS_v1.json").exists() or not (HERE/"OPTIMIZATION_BINDING.json").exists():
            raise RuntimeError("v2_requires_fixed_v1_evidence_and_optimization_binding")
        optimization = read("OPTIMIZATION_BINDING.json")
        identities["OPTIMIZATION_BINDING.json"] = file_record(HERE/"OPTIMIZATION_BINDING.json")
        identities["DEV_DIAGNOSTICS_v1.json"] = file_record(HERE/"DEV_DIAGNOSTICS_v1.json")
    data = load_training_data(identities)
    stats, normalization_report = normalization(data, version, identities)
    sampling = load_array_package(HERE/"private/TRAINING_INDICES.npz", identities)
    rows = sampling["rows"]
    if rows.shape != (1200,1024):
        raise ValueError("fixed1200x1024_sampling_required")
    for field in ("pair_index", "F_row", "state"):
        if field not in rows.dtype.names:
            raise ValueError("sampling_field_missing_"+field)
    first, second = rows[:,::2], rows[:,1::2]
    if not np.array_equal(first["pair_index"],second["pair_index"]) or not np.array_equal(first["F_row"],second["F_row"]) or not np.all(first["state"]+second["state"] == 1):
        raise ValueError("sampling_must_keep_same_point_opposite_state_pairs")
    pair_count = len(data["pairs"])
    normal_offset, damaged_offset = np.full(pair_count,-1,dtype=np.int64), np.full(pair_count,-1,dtype=np.int64)
    for pair in data["pairs"]:
        if pair["probability_per_pair_event"] > 0:
            normal_offset[pair["index"]] = data["offsets"][pair["normal_alias"]]
            damaged_offset[pair["index"]] = data["offsets"][pair["damaged_alias"]]
    pair_indices = rows["pair_index"].astype(np.int64)
    F_rows = rows["F_row"].astype(np.int64)
    states = rows["state"].astype(np.int64)
    if pair_indices.min() < 0 or pair_indices.max() >= pair_count or F_rows.min() < 0 or F_rows.max() >= 384 or not np.isin(states,(0,1)).all():
        raise ValueError("sampling_index_out_of_range")
    selected_offsets = np.where(states == 1,damaged_offset[pair_indices],normal_offset[pair_indices])
    if np.any(selected_offsets < 0):
        raise ValueError("validation_or_unusable_pair_in_training_indices")
    global_rows = selected_offsets + F_rows
    sampling_digest = hashlib.sha256(np.stack((pair_indices,F_rows,states),axis=-1).astype("<i8").tobytes()).hexdigest()
    torch.manual_seed(1729)
    model = SurfacePerception(stats["mean"], stats["divisor"]).cpu()
    if sum(parameter.numel() for parameter in model.parameters()) != PARAMETERS:
        raise ValueError("candidate_parameter_count_changed")
    initial_tensor_digest = tensor_digest(model.state_dict())
    if version == "v2":
        first_checkpoint = torch.load(destination/"v1_initial.pth",map_location="cpu",weights_only=True)
        if initial_tensor_digest != first_checkpoint["tensor_sha256"]:
            raise ValueError("optimization_initial_tensor_differs_from_v1")
        if sampling_digest != read("TRAIN_LOG_v1.json")["logical_sampling_sha256"]:
            raise ValueError("optimization_sampling_differs_from_v1")
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3,weight_decay=1e-4,betas=(.9,.999),eps=1e-8,foreach=False)
    loss_function = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor((1-data["pi"])/data["pi"],dtype=torch.float32))
    initial_path = destination/(version+"_initial.pth")
    torch.save(dict(state_dict=model.state_dict(),tensor_sha256=initial_tensor_digest,architecture=ARCHITECTURE,
                    step=0,version=version,seed=1729,torch_rng_state=torch.get_rng_state()),initial_path)
    log = dict(cycle_id="M6-TASK-PERCEPTION-001",version=version,status="training",seed=1729,steps_requested=1200,
               batch_rows=1024,pair_events_per_step=512,parameters=PARAMETERS,architecture=ARCHITECTURE,
               learning_rate=.001,weight_decay=.0001,optimizer="AdamW foreach=False",positive_label_prior=data["pi"],
               positive_weight=(1-data["pi"])/data["pi"],loss="weighted BCE" if version=="v1" else "weighted BCE +0.1 paired positive-point margin1 ranking",
               rank_coefficient=0. if version=="v1" else .1,initial_checkpoint=file_record(initial_path),
               initial_tensor_sha256=initial_tensor_digest,normalization=normalization_report,
               logical_sampling_sha256=sampling_digest,source_sampling=file_record(HERE/"private/TRAINING_INDICES.npz"),
               training_aliases=data["aliases"],development_case_probabilities=data["probabilities"],
               development_label_arrays_read=data["label_arrays_read"],validation_label_arrays_read=0,
               invalid_feature_points_in_training=data["invalid_feature_points"],invalid_policy="all F rows retained, validity flag only affects reported inference",
               source_sha256={name:file_record(HERE/name)["sha256"] for name in ("model.py","train.py")},steps=[])
    write("TRAIN_LOG_"+version+".json",log)
    features_tensor=torch.from_numpy(data["features"])
    targets_tensor=torch.from_numpy(data["targets"])
    model.train()
    train_started=time.perf_counter()
    for step in range(1200):
        indices=torch.from_numpy(global_rows[step])
        features=features_tensor[indices]
        target=targets_tensor[indices]
        state=torch.from_numpy(states[step]).to(dtype=torch.float32)
        optimizer.zero_grad(set_to_none=True)
        logits=model(features)
        binary_loss=loss_function(logits,target)
        positive_pair=target.reshape(512,2).sum(dim=1)>0
        damaged_logits=(logits*state).reshape(512,2).sum(dim=1)
        normal_logits=(logits*(1-state)).reshape(512,2).sum(dim=1)
        ranking=torch.relu(1-(damaged_logits-normal_logits))
        rank_loss=(ranking*positive_pair).sum()/positive_pair.sum().clamp_min(1)
        loss=binary_loss+(0. if version=="v1" else .1)*rank_loss
        if not torch.isfinite(loss):
            raise ValueError("nonfinite_training_loss_step_"+str(step+1))
        loss.backward()
        optimizer.step()
        log["steps"].append(dict(step=step+1,loss=float(loss.detach()),weighted_BCE=float(binary_loss.detach()),
                                  paired_rank_loss=float(rank_loss.detach()),positive_point_pairs=int(positive_pair.sum()),
                                  positive_rows=int(torch.count_nonzero(target))))
        if (step+1)%100==0:
            log["completed_steps"]=step+1
            write("TRAIN_LOG_"+version+".json",log)
            print(json.dumps(dict(version=version,step=step+1,loss=log["steps"][-1]["loss"])),flush=True)
    log["optimizer_steps_wall_s"]=time.perf_counter()-train_started
    final_tensor_digest=tensor_digest(model.state_dict())
    final_path=destination/(version+"_final.pth")
    torch.save(dict(state_dict=model.state_dict(),tensor_sha256=final_tensor_digest,architecture=ARCHITECTURE,
                    step=1200,version=version,seed=1729,normalization_sha256=file_record(destination/"normalization.npz")["sha256"]),final_path)
    optimizer_path=destination/(version+"_optimizer.pth")
    torch.save(dict(optimizer=optimizer.state_dict(),step=1200,torch_rng_state=torch.get_rng_state(),
                    logical_sampling_sha256=sampling_digest),optimizer_path)
    diagnostics=development_diagnostics(model,data,version)
    identity=dict(version=version,parameters=PARAMETERS,architecture=ARCHITECTURE,seed=1729,completed_steps=1200,
                  initial_tensor_sha256=initial_tensor_digest,final_tensor_sha256=final_tensor_digest,
                  initial_checkpoint=file_record(initial_path),final_checkpoint=file_record(final_path),
                  optimizer_checkpoint=file_record(optimizer_path),normalization=file_record(destination/"normalization.npz"),
                  pretrained_components=0,trainable_encoders=1,trainable_heads=1,models_trained_this_version=1,
                  optimization_initialization="same initial tensors as v1" if version=="v2" else "seed1729 fixed initialization")
    write("MODEL_IDENTITY_"+version+".json",identity)
    log.update(status="completed_exact1200_steps",completed_steps=1200,final_checkpoint=identity["final_checkpoint"],
               optimizer_checkpoint=identity["optimizer_checkpoint"],final_tensor_sha256=final_tensor_digest,
               development_diagnostics=diagnostics,optimization_binding=optimization,input_file_identities=list(identities.values()),
               normal_rows=int((states==0).sum()),damaged_rows=int((states==1).sum()),
               pair_event_counts={str(key):int(value) for key,value in Counter(pair_indices[:,::2].ravel()).items()},
               wall_s_before_final_report=time.perf_counter()-started,CPU_s_before_final_report=time.process_time()-cpu,
               measurement_scope="main-body imports excluded, input hashing/read, normalization, sample validation, optimization, checkpoints and all-development diagnostics included")
    write("TRAIN_LOG_"+version+".json",log)
    print(json.dumps(dict(version=version,status=log["status"],parameters=PARAMETERS,
                          weighted_margin_violations=diagnostics["weighted_positive_margin_violation_fraction"])),flush=True)


if __name__=="__main__":
    main()
