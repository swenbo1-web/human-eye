"""Frozen official encoder loading and the single perception head."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRETRAIN = HERE.parent / "m6_shape_pretrain_001"
environment = json.loads((PRETRAIN / "ENVIRONMENT.json").read_bytes())
for directory in reversed(environment["dependency_paths"]):
    if directory not in sys.path:
        sys.path.insert(0, directory)

import numpy as np
import torch
from torch import nn

spec = importlib.util.spec_from_file_location("_perception_saved_adapter", PRETRAIN / "adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
measure = adapter.measure
process_resources = adapter.process_resources


class PerceptionHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.network = nn.Sequential(nn.Linear(1024, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, features):
        return self.network(features).squeeze(1)


def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def file_record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def tensor_digest(state):
    """Hash all parameters and buffers by name, dtype, shape and tensor bytes."""
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = json.dumps({"name": name, "dtype": str(tensor.dtype), "shape": list(tensor.shape)},
                              sort_keys=True, separators=(",", ":")).encode("utf8")
        digest.update(len(metadata).to_bytes(8, "little"))
        digest.update(metadata)
        payload = tensor.numpy().tobytes(order="C")
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return digest.hexdigest()


def load_frozen_encoder(timings):
    with measure(timings, "official_architecture_import"):
        path = PRETRAIN / "private/pointfilter/Pointfilter_Network_Architecture.py"
        spec = importlib.util.spec_from_file_location("_perception_official_architecture", path)
        architecture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(architecture)
    with measure(timings, "official_checkpoint_hash_and_load"):
        checkpoint_path = PRETRAIN / "private/pointfilter/model_full_ae.pth"
        record = file_record(checkpoint_path)
        if record["sha256"] != "86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee":
            raise ValueError("official_checkpoint_identity_changed")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    with measure(timings, "official_model_creation_strict_load_and_freeze"):
        model = architecture.pointfilternet().cpu()
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        model.requires_grad_(False)
        model.eval()
        if any(parameter.requires_grad for parameter in model.parameters()):
            raise ValueError("frozen_encoder_has_trainable_parameters")
        if any(module.training for module in model.modules()):
            raise ValueError("frozen_model_has_training_module")
        if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
            raise ValueError("nonfinite_official_checkpoint_tensor")
    guard = {"decoder_forward_calls": 0}

    def prohibit_decoder(module, inputs):
        guard["decoder_forward_calls"] += 1
        raise RuntimeError("displacement_decoder_execution_is_outside_this_batch")

    model.decoder.register_forward_pre_hook(prohibit_decoder)
    return model, guard, record


def configure_torch():
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)


def save_predictions(cases, model, normalization, destination_name, timings, head_identity):
    """Run only the trained head on saved frozen features, without labels."""
    rows = []
    mean = normalization["mean"].astype(np.float64)
    divisor = normalization["divisor"].astype(np.float64)
    model.eval()
    for case in cases:
        case_timings = {}
        with measure(case_timings, "feature_read_and_identity"):
            if file_record(case["path"])["sha256"] != case["sha256"]:
                raise ValueError("feature_cache_identity_changed_" + case["id"])
            with np.load(case["path"], allow_pickle=False) as package:
                features = package["features"].astype(np.float32)
                source_ids = package["free_source_ids"].copy()
                valid = package["valid_mask"].astype(bool)
        with measure(case_timings, "head_normalization_and_inference"):
            normalized = ((features.astype(np.float64) - mean) / divisor).astype(np.float32)
            logits = np.zeros(len(features), dtype=np.float32)
            with torch.inference_mode():
                for start in range(0, len(features), 1024):
                    stop = min(start + 1024, len(features))
                    logits[start:stop] = model(torch.from_numpy(normalized[start:stop])).numpy()
            if not np.isfinite(logits).all():
                raise ValueError("nonfinite_head_logits_" + case["id"])
            scores = torch.sigmoid(torch.from_numpy(logits)).numpy()
            logits[~valid] = 0.0
            scores[~valid] = 0.0
        with measure(case_timings, "prediction_save_hash"):
            path = HERE / "private/predictions" / (case["id"] + ".npz")
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, free_source_ids=source_ids, logits=logits, scores=scores, valid_mask=valid)
            row = {key: case[key] for key in ("id", "patch_id", "source", "purpose", "normal_control", "position_group")}
            row.update(file_record(path), points=len(features), valid_points=int(np.count_nonzero(valid)),
                       unavailable_points=int(np.count_nonzero(~valid)), feature_path=case["path"],
                       feature_sha256=case["sha256"], head_final_sha256=head_identity, timings=case_timings)
            rows.append(row)
        for name, values in case_timings.items():
            target = timings.setdefault(name, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
            for key in target:
                target[key] += values[key]
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "completed_saved_feature_head_predictions",
              "cases": rows, "case_count": len(rows), "head_final_sha256": head_identity,
              "invalid_prediction_policy": "fixed score0 and logits0, validity and full F denominators retained",
              "reference_or_label_arrays_read": 0, "encoder_or_decoder_forwards_in_head_prediction": 0,
              "timings": timings}
    write_json(destination_name, report)
    return report
