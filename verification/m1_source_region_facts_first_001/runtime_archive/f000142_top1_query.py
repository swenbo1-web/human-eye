"""Opt-in nearest-set proof using current exact results and outward bounds.

This is a query scheduler, never a collision gate or an execution permission.
Equal unrounded engine distances are retained as ties, not physical equivalence.
"""
from __future__ import annotations

import math

from .measurement_presentation import finite_metric, valid_unrounded_measurement


def _exact_distance(record):
    value = record.get('signed_clearance_m')
    if (record.get('measurement_kind') == 'exact'
            and record.get('clearance_exact') is True
            and valid_unrounded_measurement(record)
            and value >= 0 and record.get('is_penetrating') is not True):
        return value
    return None


def _threshold(best, guard):
    # This guard enlarges the pruning envelope only; it never merges ties,
    # changes reported clearances or relaxes a collision tolerance.
    return None if best is None else math.nextafter(best + guard, math.inf)


def _excluded(record, threshold, supported):
    bound = record.get('clearance_lower_bound_m')
    return (supported and threshold is not None
            and record.get('measurement_kind') == 'lower_bound'
            and record.get('numeric_bound_valid') is True
            and record.get('method', record.get('clearance_method')) == 'outward_aabb_linf_lower_bound'
            and finite_metric(bound) and bound >= 0 and bound > threshold)


def select_top1_pairs(*, requested_ids, reference_id, reference_measurement,
                      bounds_by_id, supported_ids, max_exact_pairs, measure,
                      admit, comparison_guard_m):
    """Spend reference-inclusive slots only on candidates not yet excluded.

    ``admit`` checks cumulative geometry work before each extra measurement.
    Callbacks and bounds belong to this fresh router operation, not model input.
    """
    supported = set(supported_ids)
    selected = [reference_id]
    measurements = {reference_id: reference_measurement}
    best = (_exact_distance(reference_measurement) if reference_id in requested_ids else None)
    deferred, resource = [], []

    def order(identity):
        record = bounds_by_id[identity]
        value = record.get('clearance_lower_bound_m')
        return (value if record.get('numeric_bound_valid') is True
                and finite_metric(value) and value >= 0 else -math.inf, identity)

    for identity in sorted((item for item in requested_ids if item != reference_id), key=order):
        if identity not in supported:
            continue
        if _excluded(bounds_by_id[identity], _threshold(best, comparison_guard_m), True):
            continue
        if len(selected) >= max_exact_pairs:
            deferred.append(identity)
            continue
        if not admit(selected + [identity]):
            resource.append(identity)
            continue
        selected.append(identity)
        record = measure(identity)
        measurements[identity] = record
        distance = _exact_distance(record)
        if distance is not None and (best is None or distance < best):
            best = distance
    return {'selected_ids': selected, 'measurements': measurements,
            'budget_deferred': deferred, 'resource_deferred': resource}


def summarize_top1(*, requested_ids, contacts, supported_ids, comparison_guard_m):
    """Recheck proof coverage from actual returned contacts, not a plan claim."""
    by_id = {record['object_id']: record for record in contacts}
    supported = set(supported_ids)
    exact = {identity: _exact_distance(by_id[identity]) for identity in requested_ids}
    values = [value for value in exact.values() if value is not None]
    best = min(values) if values else None
    threshold = _threshold(best, comparison_guard_m)
    excluded = [identity for identity in requested_ids if exact[identity] is None
                and _excluded(by_id[identity], threshold, identity in supported)]
    unresolved = [identity for identity in requested_ids if exact[identity] is None and identity not in excluded]
    complete = bool(requested_ids) and best is not None and not unresolved
    winners = sorted(identity for identity, distance in exact.items() if distance == best) if complete else None
    return {
        'status': 'complete' if complete else 'unknown',
        'nearest_object_ids': winners,
        'unique': len(winners) == 1 if complete else None,
        'signed_clearance_m': best if complete else None,
        'excluded_by_lower_bound_ids': excluded,
        'comparison_guard_m': comparison_guard_m,
        'pruning_threshold_m': threshold if threshold is not None and math.isfinite(threshold) else None,
        'proof_method': 'exact_candidates_and_strict_outward_aabb_lower_bounds',
        'tie_scope': 'equal_unrounded_engine_distances_not_physical_equivalence',
        'execution_authority': False,
    }, unresolved


__all__ = ['select_top1_pairs', 'summarize_top1']
