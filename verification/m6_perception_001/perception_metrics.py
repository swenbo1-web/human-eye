"""Same-F ranking and strict area-prefix attention metrics."""

import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RING = HERE.parent / "m6_shape_ring_001"
sys.path.append(str(RING))
from ring_metrics import components, distribution, measure, operating_metrics, process_resources, rank_metrics

spec = importlib.util.spec_from_file_location("_perception_ring_evaluation_helpers", RING / "evaluate.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
patch_macro = previous.patch_macro
base_operation_summary = previous.operation_summary

import numpy as np

CONFIGURATIONS = ("perception", "old_p", "solid_point", "ring_point")


def budget_selection(scores, source_ids, area, fraction=.25):
    scores = np.asarray(scores, dtype=np.float64)
    source_ids = np.asarray(source_ids, dtype=np.int64)
    area = np.asarray(area, dtype=np.float64)
    if scores.shape != source_ids.shape or scores.shape != area.shape:
        raise ValueError("budget_shape_mismatch")
    if not np.isfinite(scores).all() or not np.isfinite(area).all() or np.any(area < 0):
        raise ValueError("budget_nonfinite_or_negative_area")
    if len(np.unique(source_ids)) != len(source_ids):
        raise ValueError("duplicate_query_source_IDs")
    order = np.lexsort((source_ids, -scores))
    selected = np.zeros(len(scores), dtype=bool)
    total = float(area.sum())
    budget, used, count = total * fraction, 0.0, 0
    if total > 0:
        for row in order:
            proposed = used + float(area[row])
            if proposed > budget:
                break
            used = proposed
            selected[row] = True
            count += 1
    stop = int(source_ids[order[count]]) if count < len(order) else None
    return selected, {"budget_fraction": fraction, "budget_area_native": budget,
                      "total_F_area_native": total, "selected_prefix_area_native": used,
                      "actual_area_fraction": used / total if total > 0 else None,
                      "selected_points": count, "next_stopping_source_id": stop,
                      "score_tied_points": len(scores) - len(np.unique(scores)),
                      "area_budget_applicable": total > 0,
                      "rule": "descending score, ascending source ID ties, strict nonexceeding prefix, stop at first excess"}


def detection_metrics(labels, selected, area, ell, edge_index):
    result = operating_metrics(labels, selected, area, ell, edge_index)
    missed = components(np.asarray(labels, dtype=bool) & ~np.asarray(selected, dtype=bool), edge_index)
    largest = max(missed, key=lambda rows: (float(np.asarray(area)[rows].sum()), len(rows), -int(rows.min()))) if missed else np.empty(0, dtype=np.int64)
    maximum_area = float(np.asarray(area)[largest].sum())
    total_area = float(np.asarray(area).sum())
    selected_area = float(np.asarray(area)[selected].sum())
    result.update(largest_missed_component_points=len(largest),
                  largest_missed_component_area_native=maximum_area,
                  largest_missed_component_area_over_ell2=maximum_area / ell ** 2,
                  missed_component_count=len(missed), total_F_area_native=total_area,
                  selected_F_area_native=selected_area,
                  total_F_area_over_ell2=total_area / ell ** 2,
                  selected_F_area_over_ell2=selected_area / ell ** 2,
                  selected_F_area_fraction=selected_area / total_area if total_area else None)
    return result


def operation_summary(rows):
    result = base_operation_summary(rows)
    for key in ("total_F_area_native", "selected_F_area_native", "total_F_area_over_ell2", "selected_F_area_over_ell2"):
        result[key] = sum(row[key] for row in rows)
    result["selected_F_area_fraction"] = result["selected_F_area_native"] / result["total_F_area_native"] if result["total_F_area_native"] else None
    result["selected_F_area_fraction_ell_normalized_pool"] = result["selected_F_area_over_ell2"] / result["total_F_area_over_ell2"] if result["total_F_area_over_ell2"] else None
    result["per_case_selected_F_area_fraction"] = distribution(row["selected_F_area_fraction"] for row in rows)
    for key in ("largest_missed_component_points", "largest_missed_component_area_native", "largest_missed_component_area_over_ell2"):
        result["per_case_" + key] = distribution(row[key] for row in rows)
    return result
