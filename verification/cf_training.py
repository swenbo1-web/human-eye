"""Portable fit and seal workers for the frozen CF experiment.

Fit consumes only two train arrays. Seal joins prior fits to validation
evidence, freezes the selection, then fits the prespecified ablations from
the original train arrays. Neither command takes a scene manifest.
"""

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from human_eye_fast.cerebellar_flash import CerebellarFlash, EXPERIENCE_CAPACITY, LinearHead, sigmoid
from verification.cf_baselines import ConditionalConstant


CONFIGS = ((False, .001), (False, .01), (True, .001), (True, .01))
VIEW_UPDATES = 200
TRAIN_ROWS = 240
VALIDATION_ROWS = 60
VIEW_ARMS = ("F", "R", *(f"L{i}" for i in range(len(CONFIGS))))


def _std_or_one(values, axis=0):
    std = np.std(values, axis=axis)
    return np.where(std == 0., 1., std)


def _new_head(features, config, *, view):
    quadratic, regularization = CONFIGS[config]
    columns = features.shape[-1]
    flat = np.asarray(features, dtype=np.float64).reshape(-1, columns)
    transformed = LinearHead.transform(flat, view=view)
    width = columns + (columns * (columns + 1) // 2 if quadratic else 0) + 1
    return LinearHead(transformed.mean(axis=0), _std_or_one(transformed), np.zeros(width),
                      quadratic=quadratic, regularization=regularization, view=view)


def _fit_view(head, keys, safe):
    design = head.design(keys.reshape(-1, keys.shape[-1]))
    labels = np.asarray(safe, dtype=np.float64).ravel()
    count = len(labels)
    gram = design.T @ design / count
    step = 1. / (.25 * np.linalg.eigvalsh(gram)[-1] + head.regularization)
    weights = head.weights
    for _ in range(VIEW_UPDATES):
        logits = design @ weights
        probabilities = sigmoid(logits)
        gradient = design.T @ (probabilities - labels) / count
        gradient[:-1] += head.regularization * weights[:-1]
        weights -= step * gradient
    return head


def _fit_action(head, keys, residuals):
    design = head.design(keys)
    count = len(keys)
    normal = design.T @ design / count
    diag = np.arange(normal.shape[0] - 1)
    normal[diag, diag] += head.regularization
    head.weights[:] = np.linalg.solve(normal, design.T @ residuals / count)
    return head


def fit_view(keys, feedback, configs=range(len(CONFIGS))):
    keys = np.asarray(keys, dtype=np.float64)
    safe = np.asarray(feedback)[..., 0]
    return tuple(_fit_view(_new_head(keys, config, view=True), keys, safe) for config in configs)


def action_residuals(keys, scales, labels_m):
    return np.asarray(labels_m, dtype=np.float64) / scales - keys[:, 1]


def fit_action(keys, scales, labels_m, configs=range(len(CONFIGS))):
    keys = np.asarray(keys, dtype=np.float64)
    residuals = action_residuals(keys, scales, labels_m)
    return tuple(_fit_action(_new_head(keys, config, view=False), keys, residuals)
                 for config in configs)


def select_view(rows):
    """Lexicographic validation gate on independently measured native outcomes."""
    reference = rows["F"]
    reference_order = [(row["id"], row["family"]) for row in reference]
    if len({key for key, _ in reference_order}) != len(reference_order):
        raise ValueError("Duplicate view validation episode")
    families = np.array([family for _, family in reference_order])
    family_masks = [families == family for family in np.unique(families)]
    baseline = np.array([bool(row["success"]) for row in reference])
    base_rays = np.median([row["rays"] for row in reference])
    scores = {}
    for name in VIEW_ARMS[1:]:
        arm = rows[name]
        if [(row["id"], row["family"]) for row in arm] != reference_order:
            raise ValueError(f"View validation binding mismatch for {name}")
        success = np.array([bool(row["success"]) for row in arm])
        scores[name] = (
            int(np.count_nonzero(baseline & ~success)),
            sum(int(np.count_nonzero(success[mask]) < np.count_nonzero(baseline[mask]))
                for mask in family_masks),
            float(np.median([row["rays"] for row in arm]) / base_rays),
            -int(np.count_nonzero(success)),
        )
    winner = min(range(len(CONFIGS)), key=lambda i: (*scores[f"L{i}"], i))
    return winner, scores


def select_action(heads, constant, keys, scales, labels_m, groups):
    """Use validation MAE in meters, with the frozen tie decisions."""
    predictions = {
        "C": np.array([constant.predict(group) for group in groups]),
        "G": keys[:, 1] * scales,
    }
    for i, head in enumerate(heads):
        predictions[f"L{i}"] = np.array([head.predict_delta(key, scale)
                                        for key, scale in zip(keys, scales, strict=True)])
    mae = {name: float(np.mean(np.abs(values - labels_m))) for name, values in predictions.items()}
    return (min(range(len(CONFIGS)), key=lambda i: (mae[f"L{i}"], i)),
            "G" if mae["G"] <= mae["C"] else "C", mae)


@dataclass(frozen=True)
class _Banks:
    view_keys: np.ndarray
    view_feedback: np.ndarray
    retrieval_scale: np.ndarray
    action_keys: np.ndarray
    action_labels: np.ndarray

    def session(self, view_head, action_head):
        session = CerebellarFlash(view_head, action_head, retrieval_scale=self.retrieval_scale)
        for keys, feedback in zip(self.view_keys, self.view_feedback, strict=True):
            session.views.append(keys, feedback)
        for keys, label in zip(self.action_keys, self.action_labels, strict=True):
            session.actions.append(keys, [label])
        return session


@dataclass(frozen=True)
class Candidates:
    view_heads: tuple
    action_heads: tuple
    reference: ConditionalConstant
    banks: _Banks

    def session(self, view=0, action=0):
        return self.banks.session(self.view_heads[view], self.action_heads[action])


@dataclass(frozen=True)
class FrozenModels:
    view_head: LinearHead
    action_head: LinearHead
    view_zero: LinearHead
    view_shuffle: LinearHead
    action_shuffle: LinearHead
    reference: ConditionalConstant
    reference_arm: str
    view_config: int
    action_config: int
    banks: _Banks

    def session(self, view="frozen", action="frozen"):
        views = {"frozen": self.view_head, "zero": self.view_zero, "shuffle": self.view_shuffle}
        actions = {"frozen": self.action_head, "shuffle": self.action_shuffle}
        return self.banks.session(views[view], actions[action])


def _pack_head(data, prefix, head):
    data[f"{prefix}_mean"] = head.mean
    data[f"{prefix}_scale"] = head.scale
    data[f"{prefix}_weights"] = head.weights
    data[f"{prefix}_quadratic"] = np.asarray(head.quadratic)
    data[f"{prefix}_lambda"] = np.asarray(head.regularization)


def _unpack_head(data, prefix, *, view):
    return LinearHead(data[f"{prefix}_mean"], data[f"{prefix}_scale"], data[f"{prefix}_weights"],
                      quadratic=bool(data[f"{prefix}_quadratic"]),
                      regularization=float(data[f"{prefix}_lambda"]), view=view)


def _pack_shared(data, banks, reference):
    data.update(vars(banks))
    groups = tuple(reference.by_group_m)
    kinds = tuple(reference.by_kind_m)
    data.update(
        c_groups=np.asarray(groups, dtype=str),
        c_medians=np.asarray([reference.by_group_m[group] for group in groups]),
        c_counts=np.asarray([reference.train_counts[group] for group in groups]),
        c_kinds=np.asarray(kinds, dtype=str),
        c_kind_medians=np.asarray([reference.by_kind_m[kind] for kind in kinds]),
        c_global=np.asarray(reference.global_median_m),
    )


def _groups(values):
    return [(str(kind), int(sign), int(band)) for kind, sign, band in values]


def _unpack_shared(data):
    banks = _Banks(*(data[name] for name in _Banks.__dataclass_fields__))
    reference = object.__new__(ConditionalConstant)
    groups = _groups(data["c_groups"])
    reference.by_group_m = dict(zip(groups, map(float, data["c_medians"]), strict=True))
    reference.train_counts = dict(zip(groups, map(int, data["c_counts"]), strict=True))
    reference.by_kind_m = dict(zip(map(str, data["c_kinds"]),
                                   map(float, data["c_kind_medians"]), strict=True))
    reference.global_median_m = float(data["c_global"])
    return banks, reference


def _write_candidates(path, models):
    data = {}
    _pack_shared(data, models.banks, models.reference)
    for prefix, heads in (("v", models.view_heads), ("a", models.action_heads)):
        for i, head in enumerate(heads):
            _pack_head(data, f"{prefix}{i}", head)
    np.savez(path, **data)


def load_candidates(path):
    with np.load(path, allow_pickle=False) as data:
        banks, reference = _unpack_shared(data)
        return Candidates(tuple(_unpack_head(data, f"v{i}", view=True) for i in range(len(CONFIGS))),
                          tuple(_unpack_head(data, f"a{i}", view=False) for i in range(len(CONFIGS))),
                          reference, banks)


def _write_frozen(path, models):
    data = {
        "reference_arm": np.asarray(models.reference_arm),
        "view_config": np.asarray(models.view_config),
        "action_config": np.asarray(models.action_config),
    }
    _pack_shared(data, models.banks, models.reference)
    for name in ("view_head", "action_head", "view_zero", "view_shuffle", "action_shuffle"):
        _pack_head(data, name, getattr(models, name))
    np.savez(path, **data)


def load_frozen(path):
    with np.load(path, allow_pickle=False) as data:
        banks, reference = _unpack_shared(data)
        return FrozenModels(_unpack_head(data, "view_head", view=True),
                            _unpack_head(data, "action_head", view=False),
                            _unpack_head(data, "view_zero", view=True),
                            _unpack_head(data, "view_shuffle", view=True),
                            _unpack_head(data, "action_shuffle", view=False),
                            reference, str(data["reference_arm"]), int(data["view_config"]),
                            int(data["action_config"]), banks)


def capacity_check(models):
    """Exercise both full production rings using only repeat draws from train rows."""
    bank = models.banks
    session = CerebellarFlash(None, None, retrieval_scale=bank.retrieval_scale)
    independent = session.clone()
    query = bank.view_keys[0]
    counts = [[len(session.views), len(session.actions)]]
    cold_rank = session.rank_view(query, "R")
    capacity = EXPERIENCE_CAPACITY
    for i in range(capacity + 1):
        v = i % len(bank.view_keys)
        a = i % len(bank.action_keys)
        session.views.append(bank.view_keys[v], bank.view_feedback[v])
        session.actions.append(bank.action_keys[a], bank.action_labels[a])
        if i in (0, capacity - 1, capacity):
            counts.append([len(session.views), len(session.actions)])
    v = capacity % len(bank.view_keys)
    a = capacity % len(bank.action_keys)
    assert session.views.writes == session.actions.writes == capacity + 1
    assert counts == [[0, 0], [1, 1], [capacity, capacity], [capacity, capacity]]
    assert np.array_equal(session.views.keys[0], bank.view_keys[v])
    assert np.array_equal(session.actions.keys[0], bank.action_keys[a])
    assert np.array_equal(session.views.values[0], bank.view_feedback[v])
    assert session.actions.values[0, 0] == bank.action_labels[a]
    assert len(independent.views) == len(independent.actions) == 0
    full_rank = session.rank_view(query, "R")
    reserved = {head: sum(getattr(state, name).nbytes for name in ("keys", "values", "known"))
                for head, state in (("V", session.views), ("A", session.actions))}
    session.close()
    independent.close()
    assert all(getattr(state, name) is None for state in (session.views, session.actions)
               for name in ("keys", "values", "known"))
    return {"capacity": capacity, "occupancy": counts, "reserved_bank_bytes": reserved,
            "cold_rank": cold_rank, "full_rank": full_rank,
            "overwritten_slot_train_rows": {"V": v, "A": a},
            "session_isolation": True, "closed": True}


class _Reads:
    """Record exact application data bytes opened by a portable worker."""

    def __init__(self):
        self.entries = []

    def read(self, path):
        path = Path(path).resolve()
        content = path.read_bytes()
        self.entries.append({"path": str(path), "sha256": sha256(content).hexdigest(),
                             "bytes": len(content)})
        return content

    def arrays(self, path, *names):
        with np.load(BytesIO(self.read(path)), allow_pickle=False) as data:
            return tuple(data[name] for name in names)

    def json(self, path):
        return json.loads(self.read(path))


def _write_json(path, record):
    Path(path).write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _array_shape(arrays, shapes):
    for array, shape in zip(arrays, shapes, strict=True):
        if array.shape != shape or (array.dtype.kind in "fiub" and not np.isfinite(array).all()):
            raise ValueError(f"Expected finite data of shape {shape}, got {array.shape}")


def fit_worker(view_train, action_train, output):
    inputs = _Reads()
    view_keys, feedback = inputs.arrays(view_train, "keys", "feedback")
    action_keys, scales, labels, groups = inputs.arrays(action_train, "keys", "scales", "labels_m",
                                                       "groups")
    n = TRAIN_ROWS
    _array_shape((view_keys, feedback, action_keys, scales, labels, groups),
                 ((n, 16, 5), (n, 16, 2), (n, 23), (n,), (n,), (n, 3)))
    if np.any(scales <= 0.) or not np.isin(feedback[..., 0], (0, 1)).all():
        raise ValueError("Invalid train scale or view label")
    begin = perf_counter_ns()
    view_heads = fit_view(view_keys, feedback)
    view_fit_ns = perf_counter_ns() - begin
    begin = perf_counter_ns()
    action_heads = fit_action(action_keys, scales, labels)
    action_fit_ns = perf_counter_ns() - begin
    constant = ConditionalConstant(_groups(groups), labels)
    banks = _Banks(view_keys, feedback, _std_or_one(view_keys), action_keys,
                   action_residuals(action_keys, scales, labels))
    output = Path(output)
    _write_candidates(output, Candidates(view_heads, action_heads, constant, banks))
    report = {
        "file_whitelist": [str(Path(path).resolve()) for path in (view_train, action_train)],
        "actual_reads": inputs.entries,
        "configs": CONFIGS,
        "view_updates_per_config": VIEW_UPDATES,
        "view_fit_ns": view_fit_ns,
        "action_fit_ns": action_fit_ns,
        "candidate_sha256": _digest(output),
        "reference_C_train_counts": [[*group, count] for group, count in constant.train_counts.items()],
        "reference_ungrouped_m": constant.global_median_m,
        "numpy": np.__version__,
    }
    _write_json(output.with_suffix(".json"), report)
    return report


def _check_provenance(provenance, seed):
    for head, prefix in (("view", "V"), ("action", "A")):
        ids = list(map(str, provenance[head]))
        if (len(ids) != TRAIN_ROWS or len(set(ids)) != len(ids)
                or any(not id_.startswith(f"{prefix}-{seed}-train-") for id_ in ids)):
            raise ValueError(f"Invalid {head} train-bank provenance")
        provenance[head] = ids
    return provenance


def seal_worker(seed, candidates, view_validation, action_validation, view_train, action_train,
                output, *, provenance=None):
    inputs = _Reads()
    fit_report_path = Path(candidates).with_suffix(".json")
    fit_report = inputs.json(fit_report_path)
    candidate_bytes = inputs.read(candidates)
    if sha256(candidate_bytes).hexdigest() != fit_report["candidate_sha256"]:
        raise ValueError("Candidate snapshot does not match the fit receipt")
    models = load_candidates(BytesIO(candidate_bytes))
    validation = inputs.json(view_validation)
    if any(len(validation[arm]) != VALIDATION_ROWS for arm in VIEW_ARMS):
        raise ValueError("Incomplete view validation")
    if any(not row["id"].startswith(f"V-{seed}-validation-") for row in validation["F"]):
        raise ValueError("Unexpected view validation provenance")
    keys, scales, labels, groups = inputs.arrays(action_validation, "keys", "scales", "labels_m",
                                                "groups")
    n = VALIDATION_ROWS
    _array_shape((keys, scales, labels, groups), ((n, 23), (n,), (n,), (n, 3)))
    if np.any(scales <= 0.):
        raise ValueError("Invalid validation scale")

    train_paths = (view_train, action_train)
    train_bytes = [inputs.read(path) for path in train_paths]
    for content, fit_read in zip(train_bytes, fit_report["actual_reads"], strict=True):
        if sha256(content).hexdigest() != fit_read["sha256"]:
            raise ValueError("Train inputs changed between fitting and sealing")
    if provenance is not None:
        bank_ids = inputs.json(provenance)
    else:
        bank_ids = {}
        for head, content in zip(("view", "action"), train_bytes, strict=True):
            with np.load(BytesIO(content), allow_pickle=False) as data:
                bank_ids[head] = data["episode_ids"].tolist()
    bank_ids = _check_provenance(bank_ids, seed)
    v, v_scores = select_view(validation)
    a, reference, a_scores = select_action(models.action_heads, models.reference, keys, scales,
                                          labels, _groups(groups))
    output = Path(output)
    paths = (fit_report_path, candidates, view_validation, action_validation, *train_paths)
    if provenance is not None:
        paths = (*paths, provenance)
    selection = {
        "seed": seed,
        "view_config": v,
        "action_config": a,
        "reference_arm": reference,
        "view_validation_scores": v_scores,
        "action_validation_mae_m": a_scores,
        "train_bank_rows": bank_ids,
        "file_whitelist": [str(Path(path).resolve()) for path in paths],
        "actual_reads": inputs.entries,
    }
    # Persist the selection before running either post-selection shuffled fit.
    selection_path = output.with_suffix(".selection.json")
    _write_json(selection_path, selection)
    bank = models.banks
    permutations = [np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, i, 2718])))
                    .permutation(len(keys_)) for i, keys_ in enumerate((bank.view_keys, bank.action_keys))]
    view_order, action_order = permutations
    begin = perf_counter_ns()
    view_shuffle, = fit_view(bank.view_keys, bank.view_feedback[view_order], (v,))
    action_shuffle = _fit_action(_new_head(bank.action_keys, a, view=False), bank.action_keys,
                                 bank.action_labels[action_order])
    shuffle_ns = perf_counter_ns() - begin
    zero = _new_head(bank.view_keys, v, view=True)
    _write_frozen(output, FrozenModels(models.view_heads[v], models.action_heads[a], zero,
                                      view_shuffle, action_shuffle, models.reference, reference, v,
                                      a, bank))
    report = {**selection, "selection_sha256": _digest(selection_path), "shuffle_fit_ns": shuffle_ns,
              "shuffle_view_train_indices": view_order.tolist(),
              "shuffle_action_train_indices": action_order.tolist(),
              "snapshot_sha256": _digest(output), "numpy": np.__version__}
    _write_json(output.with_suffix(".json"), report)
    return report


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest="stage", required=True)
    fit = stages.add_parser("fit")
    for field in ("view_train", "action_train", "output"):
        fit.add_argument(field, type=Path)
    seal = stages.add_parser("seal")
    seal.add_argument("seed", type=int)
    for field in ("candidates", "view_validation", "action_validation", "view_train", "action_train",
                  "output"):
        seal.add_argument(field, type=Path)
    seal.add_argument("--provenance", type=Path)
    arguments = vars(parser.parse_args(argv))
    stage = arguments.pop("stage")
    report = (fit_worker if stage == "fit" else seal_worker)(**arguments)
    print(json.dumps(report, allow_nan=False))


if __name__ == "__main__":
    main()
