"""Offline v1 export and functional equivalence for the three sealed CF models."""

import argparse
from gzip import GzipFile
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys

import numpy as np

from human_eye_fast.cf_deployment import load_cf_deployment
from verification.cf_training import load_frozen


ROOT = Path(__file__).resolve().parents[1]
SEEDS = ("20261105", "79463", "310519")
DECISION = ROOT / "docs/radical_acceptance_cf.json"
DESTINATION = ROOT / "artifacts/integration/production_functional_001/deployments"


def _relative(path):
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def _identity(data):
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


def _read(path, receipt, expected=None):
    data = path.read_bytes()
    identity = _identity(data)
    if expected is not None and identity != expected:
        raise ValueError(f"Frozen input differs from the acceptance record: {path}")
    receipt[_relative(path)] = identity
    return data


def _live_rows(bank):
    count = len(bank)
    oldest = bank.writes % bank.capacity if count == bank.capacity else 0
    return np.r_[oldest:count, :oldest]


def deployment_fields(model):
    """Snapshot only the two selected heads and live ordered feedback banks."""
    result = {"version": np.asarray(1, dtype=np.int64),
              "retrieval_scale": model.retrieval_scale.copy()}
    for prefix, head, bank in (("v", model.view_head, model.views),
                               ("a", model.action_head, model.actions)):
        result.update({
            f"{prefix}_mean": head.mean.copy(),
            f"{prefix}_scale": head.scale.copy(),
            f"{prefix}_weights": head.weights.copy(),
            f"{prefix}_quadratic": np.asarray(head.quadratic, dtype=np.bool_),
            f"{prefix}_lambda": np.asarray(head.regularization, dtype=np.float64),
        })
        live = _live_rows(bank)
        for name in ("keys", "values", "known"):
            result[f"{prefix}_{name}"] = getattr(bank, name)[live]
    return result


def _check_arrays(expected, actual):
    if expected.keys() != actual.keys():
        raise AssertionError("Different deployment field names")
    identities = {}
    for name, original in expected.items():
        restored = np.asarray(actual[name])
        if (original.shape != restored.shape or original.dtype != restored.dtype
                or original.tobytes() != restored.tobytes()):
            raise AssertionError(f"Different field bytes: {name}")
        identities[name] = {"dtype": str(original.dtype), "shape": list(original.shape),
                            **_identity(original.tobytes())}
    return identities


def _action_archive(folder, seed):
    evaluation = "evaluation-completion" if seed == "20261105" else "evaluation"
    return folder / evaluation / "prequential/records.jsonl.gz"


def _first_record(data, *, action=False):
    with GzipFile(fileobj=BytesIO(data)) as stream:
        for line in stream:
            row = json.loads(line)
            if not action or "outcome" in row:
                return row
    raise ValueError("Expected feedback record missing")


def _equivalent_update(old, new, initial, folder, seed, reads):
    view = _first_record(_read(folder / "train/records.jsonl.gz", reads))
    action = _first_record(_read(_action_archive(folder, seed), reads), action=True)
    v_key = initial["v_keys"][0]
    index, safe, rays = view["candidate"], view["safe"], view["selected_rays"]
    assert view["id"].startswith(f"V-{seed}-train-") and view["score"]["safe"] == safe
    assert view["score"]["png_sha256"] == view["png_sha256"]
    assert initial["v_known"][0, index]
    np.testing.assert_array_equal(initial["v_values"][0, index], (safe, rays))
    a_key = np.asarray(action["features"], dtype=np.float64)
    meters = action["feature_scale_m"]
    delta = action["outcome"]["measured_delta_m"]
    assert action["id"].startswith(f"A-{seed}-evaluation-") and delta == action["measured_delta_m"]
    before = old.predict_delta(a_key, meters)
    assert before == new.predict_delta(a_key, meters)
    np.testing.assert_allclose(before, action["outcome"]["action"]["predicted_delta_m"],
                               rtol=1e-12, atol=1e-15)
    for model in (old, new):
        model.learn_view(v_key, index, safe, rays)
        model.learn_action(a_key, meters, delta)
    updated = _check_arrays(deployment_fields(old), deployment_fields(new))
    assert old.views.writes == new.views.writes == len(initial["v_keys"]) + 1
    assert old.actions.writes == new.actions.writes == len(initial["a_keys"]) + 1
    assert old.rank_view(v_key, "L") == new.rank_view(v_key, "L")
    assert old.rank_view(v_key, "R") == new.rank_view(v_key, "R")
    after = old.predict_delta(a_key, meters)
    assert after == new.predict_delta(a_key, meters)
    return {"view": {"id": view["id"], "candidate": index, "safe": safe, "rays": rays,
                     "png_sha256": view["png_sha256"]},
            "action": {"id": action["id"], "meters": meters, "actual_delta_m": delta,
                       "before_prediction_m": before, "after_prediction_m": after},
            "exact_updated_fields": updated}


def export_one(seed, source):
    """Return deployment bytes and provenance after all per-seed checks."""
    path = ROOT / source["path"]
    reads = {}
    source_bytes = _read(path, reads, {"sha256": source["sha256"], "bytes": source["bytes"]})
    old = load_frozen(BytesIO(source_bytes)).session()
    initial = deployment_fields(old)
    stream = BytesIO()
    np.savez(stream, **initial)
    exported = stream.getvalue()
    deployment = load_cf_deployment(BytesIO(exported))
    restored = {name: getattr(deployment, name) for name in initial}
    restored["version"] = np.asarray(deployment.version, dtype=initial["version"].dtype)
    loaded = _check_arrays(initial, restored)
    new = deployment.session()
    instantiated = _check_arrays(initial, deployment_fields(new))
    assert old.views.writes == new.views.writes == len(initial["v_keys"])
    assert old.actions.writes == new.actions.writes == len(initial["a_keys"])

    for key in initial["v_keys"]:
        for arm in ("F", "R", "L"):
            assert old.rank_view(key, arm) == new.rank_view(key, arm)

    folder = path.parents[1]
    action_train = _read(folder / "train/action.npz", reads)
    with np.load(BytesIO(action_train), allow_pickle=False) as inputs:
        np.testing.assert_array_equal(inputs["keys"], initial["a_keys"])
        scales = inputs["scales"]
    old_delta = [old.predict_delta(key, scale) for key, scale in zip(initial["a_keys"], scales, strict=True)]
    new_delta = [new.predict_delta(key, scale) for key, scale in zip(initial["a_keys"], scales, strict=True)]
    np.testing.assert_array_equal(old_delta, new_delta)

    feedback = _equivalent_update(old, new, initial, folder, seed, reads)
    _check_arrays(initial, deployment_fields(deployment.session()))
    return exported, {
        "sealed_input": source, "verification_reads": reads,
        "exact_loaded_fields": loaded, "exact_instantiated_fields": instantiated,
        "view_rank_checks_per_arm": {arm: len(initial["v_keys"]) for arm in ("F", "R", "L")},
        "exact_action_predictions": len(old_delta), "one_feedback_per_head": feedback,
        "fresh_session_unchanged_after_feedback": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DESTINATION)
    args = parser.parse_args()
    destination = args.out_dir.resolve()
    paths = {seed: destination / f"{seed}.npz" for seed in SEEDS}
    summary = destination / "summary.json"
    if any(path.exists() for path in (*paths.values(), summary)):
        parser.error("Choose an output directory without existing deployment evidence")
    decision_bytes = DECISION.read_bytes()
    decision = json.loads(decision_bytes)
    assert decision["decision"] == "ACCEPT_VA" and set(decision["frozen_snapshots"]) == set(SEEDS)
    exports = {seed: export_one(seed, decision["frozen_snapshots"][seed]) for seed in SEEDS}
    source_files = (
        "human_eye_fast/cf_deployment.py",
        "human_eye_fast/cerebellar_flash.py",
        "human_eye_fast/_cf_features.py",
        "verification/cf_training.py",
        "verification/export_cf_deployment.py",
    )
    report = {
        "scope": "Offline v1 export from sealed weights and live banks; CPU functional equivalence.",
        "acceptance_record": {"path": _relative(DECISION), **_identity(decision_bytes)},
        "source_files": {name: _identity((ROOT / name).read_bytes()) for name in source_files},
        "runtime": {"python": sys.version, "executable": sys.executable, "numpy": np.__version__,
                    "numpy_path": np.__file__,
                    "threads_env": {key: os.environ.get(key) for key in
                                    ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}},
        "seeds": {},
    }
    destination.mkdir(parents=True, exist_ok=True)
    for seed, (data, provenance) in exports.items():
        path = paths[seed]
        with path.open("xb") as stream:
            stream.write(data)
        report["seeds"][seed] = {"deployment_file": {"path": _relative(path), **_identity(data)},
                                 **provenance}
    with summary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(_relative(summary))


if __name__ == "__main__":
    main()
