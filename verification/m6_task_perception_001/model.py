"""Shared five-scale surface encoder and point localization output."""

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
SCALES = 5
CHANNELS = 16
PARAMETERS = 11969
_TORCH_CONFIGURED = False


def configure_torch():
    global _TORCH_CONFIGURED
    if _TORCH_CONFIGURED:
        return
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    _TORCH_CONFIGURED = True


class SurfacePerception(nn.Module):
    """Accept raw current descriptors [points, five scales, sixteen channels]."""

    def __init__(self, mean=None, divisor=None):
        super().__init__()
        mean = np.zeros(CHANNELS) if mean is None else np.asarray(mean)
        divisor = np.ones(CHANNELS) if divisor is None else np.asarray(divisor)
        if mean.shape != (CHANNELS,) or divisor.shape != (CHANNELS,):
            raise ValueError("normalization_channel_shape_mismatch")
        if not np.isfinite(mean).all() or not np.isfinite(divisor).all() or np.any(divisor <= 0):
            raise ValueError("invalid_development_normalization")
        self.register_buffer("feature_mean", torch.as_tensor(mean, dtype=torch.float32).clone())
        self.register_buffer("feature_divisor", torch.as_tensor(divisor, dtype=torch.float32).clone())
        self.encoder = nn.Sequential(nn.Linear(CHANNELS, 32), nn.GELU(), nn.Linear(32, 32), nn.GELU())
        self.output = nn.Sequential(nn.Linear(SCALES * 32, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, features):
        if features.ndim != 3 or features.shape[1:] != (SCALES, CHANNELS):
            raise ValueError("features_require_points_by_5_by_16")
        standardized = (features - self.feature_mean) / self.feature_divisor
        encoded = self.encoder(standardized)
        return self.output(encoded.flatten(start_dim=1)).squeeze(-1)


def tensor_digest(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = json.dumps(dict(name=name, dtype=str(tensor.dtype), shape=list(tensor.shape)),
                              sort_keys=True, separators=(",", ":")).encode("utf8")
        digest.update(len(metadata).to_bytes(8, "little"))
        digest.update(metadata)
        payload = tensor.numpy().tobytes(order="C")
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
    return digest.hexdigest()


def file_record(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def load_model(version="v1", directory=HERE):
    """Load a complete trained model, including its development-only buffers."""
    if version not in ("v1", "v2"):
        raise ValueError("unknown_fixed_candidate_version")
    configure_torch()
    directory = Path(directory)
    path = directory / "private/model" / (version + "_final.pth")
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint["architecture"] != "shared16to32to32_five_scales_concat160to64to1":
        raise ValueError("checkpoint_architecture_mismatch")
    model = SurfacePerception()
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    if tensor_digest(model.state_dict()) != checkpoint["tensor_sha256"]:
        raise ValueError("checkpoint_tensor_identity_mismatch")
    model.eval()
    model.requires_grad_(False)
    return model, dict(version=version, checkpoint=file_record(path), tensor_sha256=checkpoint["tensor_sha256"],
                       architecture=checkpoint["architecture"], parameters=PARAMETERS)


def predict_features(model, features, valid_mask=None, chunk_size=4096):
    """Run raw descriptors through the saved normalization and shared encoder."""
    features = np.asarray(features, dtype=np.float32)
    if features.ndim != 3 or features.shape[1:] != (SCALES, CHANNELS):
        raise ValueError("features_require_points_by_5_by_16")
    valid = np.ones(len(features), dtype=bool) if valid_mask is None else np.asarray(valid_mask, dtype=bool)
    if valid.shape != (len(features),):
        raise ValueError("valid_mask_shape_mismatch")
    if not np.isfinite(features).all() or chunk_size <= 0:
        raise ValueError("nonfinite_features_or_invalid_chunk_size")
    logits = np.empty(len(features), dtype=np.float32)
    scores = np.empty(len(features), dtype=np.float32)
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(features), chunk_size):
            stop = min(start + chunk_size, len(features))
            values = model(torch.from_numpy(features[start:stop]))
            logits[start:stop] = values.numpy()
            scores[start:stop] = torch.sigmoid(values).numpy()
    if not np.isfinite(logits).all() or not np.isfinite(scores).all():
        raise ValueError("nonfinite_prediction")
    logits[~valid] = 0
    scores[~valid] = 0
    return dict(logits=logits, scores=scores, valid_mask=valid)
