"""Exact tied-score binary metrics and equal-case/equal-patch summaries."""

import numpy as np


def binary_metrics(labels, scores):
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=np.float64)
    if labels.shape != scores.shape or labels.ndim != 1 or not np.isfinite(scores).all():
        raise ValueError("binary_metrics_requires_finite_aligned_vectors")
    positives = int(labels.sum())
    negatives = len(labels) - positives
    result = {"points": len(labels), "positive": positives, "negative": negatives,
              "ROC_AUC": None, "AP": None, "score_groups": 0}
    if not len(scores):
        return result
    order = np.argsort(scores, kind="stable")
    ordered_scores, ordered_labels = scores[order], labels[order]
    starts = np.r_[0, np.flatnonzero(ordered_scores[1:] != ordered_scores[:-1]) + 1]
    ends = np.r_[starts[1:], len(scores)]
    group_positive = np.asarray([ordered_labels[start:end].sum() for start, end in zip(starts, ends)], dtype=np.float64)
    group_count = (ends - starts).astype(np.float64)
    group_negative = group_count - group_positive
    result["score_groups"] = len(starts)
    if not positives or not negatives:
        return result
    negative_before = np.cumsum(group_negative) - group_negative
    result["ROC_AUC"] = float(np.sum(group_positive * (negative_before + .5 * group_negative))
                              / (positives * negatives))
    descending_positive = group_positive[::-1]
    cumulative_positive = np.cumsum(descending_positive)
    cumulative_count = np.cumsum(group_count[::-1])
    result["AP"] = float(np.sum((descending_positive / positives) * (cumulative_positive / cumulative_count)))
    return result


def quantiles(values):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    return {"count": len(values), "min": float(values.min()), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95, method="linear")), "max": float(values.max())}


def patch_macro(case_rows, method, domain="common_valid", strength="all_support"):
    """Average damaged-case metrics within patches, then patches equally."""
    selected = [row for row in case_rows if not row["normal_control"]]
    patches = sorted({row["patch_id"] for row in selected})
    patch_rows = []
    for patch in patches:
        rows = [row for row in selected if row["patch_id"] == patch]
        values = [row["metrics"][domain][strength][method] for row in rows]
        summary = {"patch_id": patch, "dented_cases": len(rows), "ROC_AUC": None, "AP": None,
                   "valid_AUC_cases": 0, "valid_AP_cases": 0}
        for key, count_key in (("ROC_AUC", "valid_AUC_cases"), ("AP", "valid_AP_cases")):
            usable = [value[key] for value in values if value[key] is not None]
            summary[count_key] = len(usable)
            if usable:
                summary[key] = float(np.mean(usable))
        patch_rows.append(summary)
    result = {"damaged_cases": len(selected), "patches": len(patches), "valid_AUC_patches": 0,
              "valid_AP_patches": 0, "ROC_AUC": None, "AP": None, "per_patch": patch_rows}
    for key, count_key in (("ROC_AUC", "valid_AUC_patches"), ("AP", "valid_AP_patches")):
        usable = [row[key] for row in patch_rows if row[key] is not None]
        result[count_key] = len(usable)
        if usable:
            result[key] = float(np.mean(usable))
    return result
