"""Summarize sealed CF evaluation and timing outputs by frozen acceptance rules."""

from argparse import ArgumentParser
import json
from pathlib import Path

import numpy as np


SEEDS = (20261105, 79463, 310519)
ARMS = ("F", "R", "L")
VIEW_DIAGNOSTICS = ("zero", "shuffle")
ACTION_METHODS = ("C", "G", "L", "shuffle")
STAGES = ("total_ns", "V_ns", "A_ns")
ORDERS = (("F", "R", "L"), ("R", "L", "F"), ("L", "F", "R"),
          ("L", "R", "F"), ("F", "L", "R"), ("R", "F", "L"))
CASE_COUNT = 60
BOOTSTRAP_COUNT = 10_000


def _p95(values, axis=None):
    return np.quantile(values, .95, axis=axis, method="linear")


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator > 0 else None


def _read(path):
    return json.loads(path.read_bytes())


def _groups(rows, key):
    labels = [key(row) for row in rows]
    return {label: [i for i, value in enumerate(labels) if value == label]
            for label in sorted(set(labels))}


def _view_slice(rays, success, mask):
    return {
        "cases": len(mask),
        "rays_median": float(np.median(rays[mask])),
        "pixel_success_count": int(success[mask].sum()),
        "pixel_success_rate": float(success[mask].mean()),
    }


def _view_report(arms):
    baseline = arms["F"]
    ids = [row["id"] for row in baseline]
    if len(ids) != CASE_COUNT or len(set(ids)) != CASE_COUNT:
        raise ValueError("view evaluation requires 60 distinct group records per seed")
    by_family = _groups(baseline, lambda row: row["family"])
    by_mode = _groups(baseline, lambda row: row["mode"])
    base_rays = np.asarray([row["rays"] for row in baseline], dtype=np.int64)
    base_success = np.asarray([row["success"] for row in baseline], dtype=bool)
    report = {}
    all_rays = {}
    for arm in (*ARMS, *VIEW_DIAGNOSTICS):
        by_id = {row["id"]: row for row in arms[arm]}
        if len(arms[arm]) != len(by_id) or by_id.keys() != set(ids):
            raise ValueError(f"view arm {arm} does not have exactly the baseline groups")
        aligned = [by_id[case_id] for case_id in ids]
        if any((left["family"], left["mode"]) != (right["family"], right["mode"])
               for left, right in zip(baseline, aligned)):
            raise ValueError(f"view arm {arm} changed a family or mode binding")
        if any(left.get("group") != right.get("group") for left, right in zip(baseline, aligned)):
            raise ValueError(f"view arm {arm} changed a group binding")
        rays = np.asarray([row["rays"] for row in aligned], dtype=np.int64)
        success = np.asarray([row["success"] for row in aligned], dtype=bool)
        all_rays[arm] = rays
        lost = [case for case, dropped in zip(ids, base_success & ~success) if dropped]
        declined = [family for family, idx in by_family.items()
                    if success[idx].sum() < base_success[idx].sum()]
        ratio = _ratio(np.median(rays), np.median(base_rays))
        state = {
            **_view_slice(rays, success, np.arange(CASE_COUNT)),
            "ray_ratio_to_F": ratio,
            "F_success_lost": lost,
            "families_declined": declined,
            "by_family": {label: _view_slice(rays, success, idx) for label, idx in by_family.items()},
            "by_mode": {label: _view_slice(rays, success, idx) for label, idx in by_mode.items()},
            "by_F_success": {str(label): _view_slice(rays, success, idx)
                             for label in (False, True)
                             if (idx := np.flatnonzero(base_success == label)).size},
        }
        if arm in ("R", "L"):
            state["ray_gate"] = ratio is not None and ratio <= .75
            state["pixel_gate"] = not lost and not declined and success.sum() >= base_success.sum()
            state["passed"] = bool(state["ray_gate"] and state["pixel_gate"])
            state["pixel_gate"] = bool(state["pixel_gate"])
        for field in ("solvable", "native_stop"):
            if all(field in row for row in aligned):
                groups = _groups(aligned, lambda row: str(bool(row[field])))
                state[f"by_{field}"] = {
                    label: _view_slice(rays, success, idx) for label, idx in groups.items()
                }
        report[arm] = state
    return report, all_rays, ids


def _action_slice(errors, scales, idx):
    return {
        method: {
            "MAE_m": float(np.mean(values[idx])),
            "normalized_MAE": float(np.mean(values[idx] / scales[idx])),
            "absolute_error_p95_m": float(_p95(values[idx])),
            "absolute_error_max_m": float(np.max(values[idx])),
        }
        for method, values in errors.items()
    }


def _action_report(rows):
    ids = [row["id"] for row in rows]
    if len(ids) != CASE_COUNT or len(set(ids)) != CASE_COUNT:
        raise ValueError("action evaluation requires 60 distinct group records per seed")
    truth = np.asarray([row["measured_delta_m"] for row in rows])
    scales = np.asarray([row.get("feature_scale_m", row["scale_m"]) for row in rows])
    budgets = np.asarray([row["delta_budget_m"] for row in rows])
    methods = ACTION_METHODS
    if all("ungrouped" in row["comparison"] for row in rows):
        methods += ("ungrouped",)
    errors = {method: np.abs(np.asarray([row["comparison"][method] for row in rows]) - truth)
              for method in methods}
    metrics = _action_slice(errors, scales, np.arange(CASE_COUNT))
    best = min(("G", "C"), key=lambda name: metrics[name]["MAE_m"])
    strong = metrics[best]["MAE_m"]
    noise_floor = float(budgets.mean())
    ratio = _ratio(metrics["L"]["MAE_m"], strong)
    strata = (
        ("by_family", lambda row: row["family"]),
        ("by_amplitude", lambda row: f"{abs(row['amplitude']):g}"),
        ("by_sign", lambda row: str(row["sign"])),
        ("by_contact", lambda row: "contact" if row["contact"] else "separated"),
    )
    return {
        "metrics": metrics,
        "strata": {label: {group: _action_slice(errors, scales, idx)
                           for group, idx in _groups(rows, key).items()} for label, key in strata},
        "strongest_baseline": best,
        "strongest_baseline_MAE_m": strong,
        "mean_delta_budget_m": noise_floor,
        "MAE_ratio_to_strongest": ratio,
        "passed": ratio is not None and ratio <= .8 and strong > noise_floor,
        "result": "UNPROVEN_AT_NUMERICAL_FLOOR" if strong <= noise_floor
                  else "PASS" if ratio <= .8 else "FAIL",
    }, errors, ids


def _time_slice(arms, idx):
    ref = arms["F"][idx]
    baseline = float(_p95(ref))
    summary = {}
    for arm, samples in arms.items():
        values = samples[idx]
        p95 = float(_p95(values))
        ratio = _ratio(p95, baseline)
        summary[arm] = {
            "episode_count": len(idx),
            "p95_ns": p95,
            "p95_ratio_to_F": ratio,
            "p95_difference_ns": p95 - baseline,
            "paired_increment_p95_ns": float(_p95(values - ref)),
            "passed": ratio is not None and ratio <= 1.10,
        }
    return summary


def _time_report(episodes, view_ids=None, action_ids=None, *, seed=None):
    if len(episodes) != CASE_COUNT or [row["ordinal"] for row in episodes] != list(range(CASE_COUNT)):
        raise ValueError("timing requires 60 ordered episode ordinals")
    for label, ids in (("view_id", view_ids), ("action_id", action_ids)):
        timed = [episode[label] for episode in episodes]
        if len(set(timed)) != CASE_COUNT or (ids is not None and timed != ids):
            raise ValueError(f"timed {label} does not match evaluation order")
    summaries = {stage: {arm: [] for arm in ARMS} for stage in STAGES}
    for episode in episodes:
        all_samples = episode["samples"]
        samples = [sample for sample in all_samples if not sample["warmup"]]
        if len(samples) != 5 or len(all_samples) != 10:
            raise ValueError("timing requires five warmup and five measured repeats")
        if len({row["repeat"] for row in all_samples}) != len(all_samples):
            raise ValueError("duplicate timing repeat")
        for sample in all_samples:
            if sorted(sample["order"]) != sorted(ARMS) or set(sample["arms"]) != set(ARMS):
                raise ValueError("timing sample does not contain every arm exactly once")
            repeat = sample["repeat"]
            if not 0 <= repeat < 10 or sample["warmup"] != (repeat < 5):
                raise ValueError("timing sample has an incorrect repeat or warmup binding")
            if seed is not None:
                expected = ORDERS[(SEEDS.index(seed) + episode["ordinal"] + repeat) % len(ORDERS)]
                if tuple(sample["order"]) != expected:
                    raise ValueError("timing sample changed the frozen arm schedule")
            if any(row["total_ns"] != row["V_ns"] + row["A_ns"] for row in sample["arms"].values()):
                raise ValueError("V and A timing intervals do not span the complete episode")
        for stage in STAGES:
            for arm in ARMS:
                durations = [sample["arms"][arm][stage] for sample in samples]
                if any(value <= 0 for value in durations):
                    raise ValueError("timing sample duration must be positive")
                summaries[stage][arm].append(float(np.median(durations)))

    data = {stage: {arm: np.asarray(samples) for arm, samples in arms.items()}
            for stage, arms in summaries.items()}
    family_key = {
        "total_ns": lambda row: f"{row['view_family']}/{row['action_family']}",
        "V_ns": lambda row: row["view_family"],
        "A_ns": lambda row: row["action_family"],
    }
    report = {
        stage: {
            "all": _time_slice(arms, np.arange(CASE_COUNT)),
            "by_family": {label: _time_slice(arms, idx)
                          for label, idx in _groups(episodes, family_key[stage]).items()},
        } for stage, arms in data.items()
    }
    return report, data


def _pooled(samples, arms):
    return {arm: np.concatenate([sample[arm] for sample in samples]) for arm in arms}


def _bootstrap_indices(seed_count):
    rng = np.random.Generator(np.random.PCG64(271828))
    blocks = [rng.integers(0, CASE_COUNT, size=(BOOTSTRAP_COUNT, CASE_COUNT)) + offset * CASE_COUNT
              for offset in range(seed_count)]
    return np.concatenate(blocks, axis=1)


def _interval(numerator, denominator):
    valid = denominator > 0
    if not valid.any():
        return {"interval_95": None, "replicates": int(valid.size), "valid_replicates": 0}
    bounds = np.quantile(numerator[valid] / denominator[valid], (.025, .975), method="linear")
    return {
        "interval_95": bounds.tolist(),
        "replicates": int(valid.size),
        "valid_replicates": int(valid.sum()),
        "includes_no_benefit": bool(bounds[0] <= 1 <= bounds[1]),
    }


def _bootstrap(view_samples, action_samples, time_samples):
    result = {
        "sampling": "paired groups with replacement within each seed block",
        "rng": "PCG64(271828)",
    }
    if view_samples:
        draws = _bootstrap_indices(len(view_samples))
        rays = _pooled(view_samples, (*ARMS, *VIEW_DIAGNOSTICS))
        base = np.median(rays["F"][draws], axis=1)
        result["view"] = {
            arm: {"pooled_ratio": _ratio(np.median(rays[arm]), np.median(rays["F"])),
                  **_interval(np.median(rays[arm][draws], axis=1), base)}
            for arm in ("R", "L", *VIEW_DIAGNOSTICS)
        }
    if action_samples:
        draws = _bootstrap_indices(len(action_samples))
        errors = _pooled(action_samples, ACTION_METHODS)
        means = {arm: values[draws].mean(axis=1) for arm, values in errors.items()}
        strong = min(errors["C"].mean(), errors["G"].mean())
        result["action"] = {
            arm: {"pooled_ratio_to_strongest": _ratio(errors[arm].mean(), strong),
                  **_interval(means[arm], np.minimum(means["C"], means["G"]))}
            for arm in ("L", "shuffle")
        }
    if time_samples:
        draws = _bootstrap_indices(len(time_samples))
        result["time"] = {}
        for stage in STAGES:
            pooled = _pooled([sample[stage] for sample in time_samples], ARMS)
            base = _p95(pooled["F"][draws], axis=1)
            result["time"][stage] = {
                "pooled": _time_slice(pooled, np.arange(len(pooled["F"]))),
                "ratios": {arm: _interval(_p95(pooled[arm][draws], axis=1), base) for arm in ("R", "L")},
            }
    return result


def _quality_checks(quality):
    checks = {}
    for label, count in (("controls", 24), ("diagnostic", 7), ("prequential", 2)):
        rows = quality.get(label, ())
        checks[label] = {"cases": len(rows), "expected": count,
                         "passed": len(rows) == count and all(row["success"] for row in rows)}
    negatives = quality.get("negative_controls", {})
    for head, count in (("V", 9), ("A", 5)):
        controls = negatives.get(head, {})
        rejected = {name: (result is True if head == "A"
                           else result.get("rejected", result.get("passed") is False))
                    for name, result in controls.items()}
        checks[f"{head}_negative_controls"] = {
            "rejected": rejected, "expected": count,
            "passed": len(rejected) == count and all(rejected.values()),
        }
    return checks


def summarize(root: Path):
    """Read all complete seed artifacts without opening model or fixture inputs."""
    root = Path(root)
    per_seed = {}
    missing = []
    failed = []
    view_samples = []
    action_samples = []
    time_samples = []
    for seed in SEEDS:
        paths = root / str(seed)
        record = per_seed[str(seed)] = {}
        view_ids = action_ids = None
        quality_path = paths / "evaluation" / "summary.json"
        if not quality_path.is_file():
            quality_path = paths / "evaluation-completion" / "summary.json"
        if quality_path.is_file():
            quality = _read(quality_path)
            views, rays, view_ids = _view_report(quality["views"])
            actions, errors, action_ids = _action_report(quality["actions"])
            view_samples.append(rays)
            action_samples.append(errors)
            checks = _quality_checks(quality)
            record["evaluation"] = {"views": views, "actions": actions, "verification": checks}
            record["evaluation"].update(
                (key, quality[key]) for key in (
                    "controls", "diagnostic", "prequential", "negative_controls", "environment")
                if key in quality
            )
            if not views["L"]["passed"]:
                failed.append(f"{seed}:V")
            if not actions["passed"]:
                failed.append(f"{seed}:A")
            failed.extend(f"{seed}:{key}" for key, item in checks.items() if not item["passed"])
        else:
            missing.append(f"{seed}:evaluation")
        time_path = paths / "performance" / "timing.json"
        if time_path.is_file():
            timing = _read(time_path)
            if timing["seed"] != seed:
                raise ValueError(f"timing seed binding mismatch for {seed}")
            report, timings = _time_report(timing["episodes"], view_ids, action_ids, seed=seed)
            time_samples.append(timings)
            record["timing"] = report
            record["timing_environment"] = {
                key: timing[key] for key in ("initialization_ns", "environment") if key in timing
            }
            for stage, timing_stage in report.items():
                if not timing_stage["all"]["L"]["passed"]:
                    failed.append(f"{seed}:{stage}")
        else:
            missing.append(f"{seed}:timing")
        memory_path = paths / "memory" / "memory.json"
        if memory_path.is_file():
            memory = _read(memory_path)
            capacity = memory["capacity"]
            record["memory"] = memory
            if (capacity["capacity"] != 4096 or not capacity["session_isolation"] or
                    not capacity["closed"] or
                    capacity["occupancy"] != [[0, 0], [1, 1], [4096, 4096], [4096, 4096]]):
                failed.append(f"{seed}:capacity_and_lifecycle")
        else:
            missing.append(f"{seed}:memory")
    return {
        "decision": "INCOMPLETE" if missing else "FAIL" if failed else "PASS",
        "missing": missing,
        "failed_deployment_gates": failed,
        "thresholds": {"view_median_ray_ratio": .75, "action_MAE_ratio": .8, "tail_ratio": 1.10},
        "per_seed": per_seed,
        "pooled_and_bootstrap": _bootstrap(view_samples, action_samples, time_samples),
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = summarize(args.root)
    out = args.output or args.root / "summary.json"
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(report["decision"], out, flush=True)


if __name__ == "__main__":
    main()
