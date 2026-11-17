"""Unrounded measurement wording, separate from legacy display tolerances.

This module changes presentation only.  A positive or negative signed metric is
never called flush, and a zero metric is not a physical-contact certificate.
Original geometry, frame, tolerance and execution fields remain unchanged.
"""
from __future__ import annotations

import copy
import math


PRESENTATION_REVISION = 'strict-clearance-presentation-v1-20261024'
_LEGACY_FIELDS = ('alignment_state', 'alignment_state_is_display_only',
                  'display_signed_clearance_m')


def finite_metric(value):
    """Accept ordinary finite JSON numbers without accepting booleans."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def valid_unrounded_measurement(record):
    """Recognize a finite metric without laundering conflicting strict facts.

Records with only a method label remain supported for existing callers.  When
strict evidence explicitly supplies validity or a value, it must agree.  Bool
values are never distances, and an explicit penetrating classification cannot
certify a nonnegative separating translation.
    """
    value = record.get('signed_clearance_m')
    if record.get('measurement_valid') is not True or not finite_metric(value):
        return False
    penetrating = record.get('is_penetrating')
    if penetrating is not None and type(penetrating) is not bool:
        return False
    if penetrating is True and value >= 0:
        return False
    if 'strict_geometry' in record:
        strict = record['strict_geometry']
        if not isinstance(strict, dict):
            return False
        if 'measurement_valid' in strict and strict['measurement_valid'] is not True:
            return False
        if 'signed_clearance_m' in strict:
            strict_value = strict['signed_clearance_m']
            if not finite_metric(strict_value) or strict_value != value:
                return False
        if 'is_penetrating' in strict and strict['is_penetrating'] is not None:
            if type(strict['is_penetrating']) is not bool:
                return False
            if penetrating is not None and strict['is_penetrating'] is not penetrating:
                return False
            if strict['is_penetrating'] is True and value >= 0:
                return False
    return True


def present_measurement(record):
    """Return an idempotent, detached wording projection of a measurement.

``clearance_state`` describes the unrounded signed metric only.  In particular,
a negative value can be within the separately declared collision tolerance;
this function does not change that collision classification.  A lower bound
never becomes an exact distance or an execution permission.
    """
    result = dict(record)
    legacy = result.get('legacy_display')
    if isinstance(legacy, dict):
        legacy = copy.deepcopy(legacy)
    elif 'legacy_display' in result:
        legacy = {'previous_value': copy.deepcopy(legacy)}
    else:
        legacy = {}
    for field in _LEGACY_FIELDS:
        if field in result:
            legacy[field] = copy.deepcopy(result.pop(field))
    if legacy:
        legacy.update(scope='legacy_display_diagnostics_not_clearance_or_execution',
                      execution_authority=False)
        result['legacy_display'] = legacy

    if valid_unrounded_measurement(result):
        value = result['signed_clearance_m']
        state = ('positive_clearance' if value > 0 else
                 'negative_clearance' if value < 0 else 'zero_clearance')
    elif (result.get('numeric_bound_valid') is True
          and finite_metric(result.get('clearance_lower_bound_m'))):
        state = 'lower_bound'
    else:
        state = 'unknown'
    result['clearance_state'] = state
    return result


__all__ = ['PRESENTATION_REVISION', 'finite_metric', 'present_measurement',
           'valid_unrounded_measurement']
