"""Bounded observation-only labels selected from existing task evidence.

This module does not measure geometry, infer visibility, remember a previous
frame or grant an action. Full object IDs remain the execution identifiers.
"""
from __future__ import annotations

import copy
import hashlib

from .measurement_presentation import finite_metric, valid_unrounded_measurement


TASK_LABEL_REVISION = 'observation-task-labels-v3-core-focus-20261027'
TASK_LABEL_SCOPE = 'observation_display_only_not_visibility_or_execution_authority'
MAX_RELATED_LABELS = 2
MAX_VISUAL_FOCUS_IDS = 6
_FIELDS = frozenset({
    'schema_revision', 'scope', 'execution_authority', 'scene_revision',
    'scene_fingerprint', 'focal_id', 'reference_id', 'core_object_ids',
    'related_object_ids', 'related_reasons', 'related_candidate_count',
    'max_related_labels', 'related_alias_hex_chars',
    'visual_focus_object_ids', 'candidate_reason_counts',
})
_REASON_RANK = {
    'known_penetration': 0,
    'explicit_query': 1,
    'near_exact_clearance': 2,
    'potential_neighbor_lower_bound': 3,
    'explicit_visual_focus': 4,
}


def _valid_id(value):
    return type(value) is str and bool(value.strip())


def _object_ids(meshes):
    identities = []
    for mesh in meshes:
        if len(identities) >= 256:
            raise ValueError('Task labels require at most 256 known objects')
        identity = mesh.get('object_id') if type(mesh) is dict else getattr(mesh, 'object_id', None)
        if not _valid_id(identity):
            raise ValueError('Task labels require nonempty object IDs')
        identities.append(identity)
    if not identities or len(set(identities)) != len(identities):
        raise ValueError('Task labels require unique known object IDs')
    return frozenset(identities)


def _validate_pair(identities, focal_id, reference_id):
    if (not _valid_id(focal_id) or not _valid_id(reference_id)
            or focal_id == reference_id or focal_id not in identities or reference_id not in identities):
        raise ValueError('Task labels require a distinct known focal and reference pair')


def _optional_text(value, name):
    if value is not None and not _valid_id(value):
        raise ValueError('Task label ' + name + ' must be nonempty text or None')


def _alias_digest(object_id):
    return hashlib.sha256(object_id.encode('utf-8')).hexdigest().upper()


def _prefix_length(identities, focal_id, reference_id):
    # Compute against the whole current scene, including unlabelled objects,
    # so CONTACT can reuse this namespace for a different attention partner.
    digests = [_alias_digest(identity) for identity in sorted(identities - {focal_id, reference_id})]
    for width in range(4, 9):
        if len({digest[:width] for digest in digests}) == len(digests):
            return width
    raise ValueError('Task label aliases collide within the eight-character budget')


def _records(contacts, identities, focal_id):
    if type(contacts) not in (list, tuple):
        return {}
    if len(contacts) > 256:
        raise ValueError('Task label contact evidence exceeds the object budget')
    records, duplicates = {}, set()
    for record in contacts:
        if type(record) is not dict:
            continue
        identity = record.get('object_id')
        if not _valid_id(identity) or identity not in identities or identity == focal_id:
            continue
        if identity in records:
            duplicates.add(identity)
        records[identity] = record
    # Conflicting duplicate records cannot promote an object or set the near
    # threshold. Explicit query selection is independently preserved below.
    return {identity: record for identity, record in records.items() if identity not in duplicates}


def _negative_measurement(record):
    return (valid_unrounded_measurement(record)
            and record.get('measurement_kind') == 'certified_penetration'
            and record.get('clearance_exact') is False
            and record.get('is_penetrating') is True and record['signed_clearance_m'] < 0)


def _exact_nonnegative(record):
    return (valid_unrounded_measurement(record)
            and record.get('measurement_kind') == 'exact'
            and record.get('clearance_exact') is True
            and record.get('is_penetrating') is False and record['signed_clearance_m'] >= 0)


def _reference_threshold(record):
    if record is not None and (_negative_measurement(record) or _exact_nonnegative(record)):
        return max(0., record['signed_clearance_m'])
    return None


def _selection_key(identity, reasons, visual_focus):
    # Selecting a requested visual identity is distinct from its geometric
    # reason. A known penetration stays a penetration when pinned for display.
    return (identity not in visual_focus, _REASON_RANK[reasons[identity]], identity)


def _build_task_label_bundle(meshes, *, focal_id, reference_id, contacts=(), requested_ids=(),
                             visual_focus_ids=(),
                             scene_revision=None, scene_fingerprint=None):
    """Build a deterministic display plan without evaluating additional pairs.

    Selection uses only existing evidence and explicit IDs. A separately
    bounded visual request pins identities without changing their geometric
    reasons or measuring more pairs. Lower bounds remain possible neighbours,
    never exact distances or collisions. Scene bindings are provenance, not
    freshness or permissions.
    """
    identities = _object_ids(meshes)
    _validate_pair(identities, focal_id, reference_id)
    _optional_text(scene_revision, 'scene_revision')
    _optional_text(scene_fingerprint, 'scene_fingerprint')
    if (type(requested_ids) not in (list, tuple) or len(requested_ids) > 256
            or any(not _valid_id(identity) or identity not in identities for identity in requested_ids)
            or len(set(requested_ids)) != len(requested_ids)):
        raise ValueError('Task label query IDs must be unique known object IDs')
    if (type(visual_focus_ids) not in (list, tuple) or len(visual_focus_ids) > MAX_VISUAL_FOCUS_IDS
            or any(not _valid_id(identity) or identity not in identities for identity in visual_focus_ids)
            or len(set(visual_focus_ids)) != len(visual_focus_ids)):
        raise ValueError('Visual focus must contain at most six unique known object IDs')
    requested_visual_focus = set(visual_focus_ids)
    # Core identities are already prioritised as A/B, but must remain in the
    # display request so visibility/delivery receipts can report their absence.
    # Only noncore requests consume the bounded related-label budget.
    visual_focus = requested_visual_focus - {focal_id, reference_id}
    related_budget = max(MAX_RELATED_LABELS, len(visual_focus))
    records = _records(contacts, identities, focal_id)
    threshold = _reference_threshold(records.get(reference_id))
    requested = set(requested_ids)
    reasons = {}
    for identity in sorted(identities - {focal_id, reference_id}):
        record = records.get(identity, {})
        reason = None
        if _negative_measurement(record):
            reason = 'known_penetration'
        elif identity in requested:
            reason = 'explicit_query'
        elif threshold is not None:
            if _exact_nonnegative(record) and record['signed_clearance_m'] <= threshold:
                reason = 'near_exact_clearance'
            else:
                bound = record.get('clearance_lower_bound_m')
                if (record.get('measurement_kind') == 'lower_bound'
                        and record.get('measurement_valid') is False
                        and record.get('clearance_exact') is False
                        and record.get('numeric_bound_valid') is True and finite_metric(bound)
                        and 0 <= bound <= threshold):
                    reason = 'potential_neighbor_lower_bound'
        if reason is None and identity in visual_focus:
            reason = 'explicit_visual_focus'
        if reason is not None:
            reasons[identity] = reason
    ordered = sorted(reasons, key=lambda identity: _selection_key(identity, reasons, visual_focus))
    related = ordered[:related_budget]
    reason_counts = {reason: sum(value == reason for value in reasons.values())
                     for reason in _REASON_RANK if reason in reasons.values()}
    plan = {
        'schema_revision': TASK_LABEL_REVISION,
        'scope': TASK_LABEL_SCOPE,
        'execution_authority': False,
        'scene_revision': scene_revision,
        'scene_fingerprint': scene_fingerprint,
        'focal_id': focal_id,
        'reference_id': reference_id,
        'core_object_ids': [focal_id, reference_id],
        'related_object_ids': related,
        'related_reasons': {identity: reasons[identity] for identity in related},
        'related_candidate_count': len(reasons),
        'max_related_labels': related_budget,
        'visual_focus_object_ids': sorted(requested_visual_focus),
        'candidate_reason_counts': reason_counts,
        'related_alias_hex_chars': _prefix_length(identities, focal_id, reference_id),
    }
    # Private operation-local display input. It is deliberately absent from
    # the public plan/context and reuses this exact evidence interpretation.
    return plan, tuple((identity, reasons[identity]) for identity in ordered)


def build_task_label_plan(meshes, *, focal_id, reference_id, contacts=(), requested_ids=(),
                          visual_focus_ids=(),
                          scene_revision=None, scene_fingerprint=None):
    """Build the compatible bounded display plan without another geometry query."""
    return _build_task_label_bundle(meshes, focal_id=focal_id, reference_id=reference_id,
        contacts=contacts, requested_ids=requested_ids, visual_focus_ids=visual_focus_ids,
        scene_revision=scene_revision, scene_fingerprint=scene_fingerprint)[0]


def validate_task_label_plan(plan, meshes, *, focal_id, reference_id):
    """Validate a display representation against the current mesh namespace.

    This checks no historical scene or original contact computation; callers
    must supply a current plan before binding their prepared render. Returning
    a detached dictionary prevents later mutation of the caller's plan.
    """
    identities = _object_ids(meshes)
    _validate_pair(identities, focal_id, reference_id)
    if type(plan) is not dict or set(plan) != _FIELDS:
        raise ValueError('Invalid task label plan fields')
    if (plan['schema_revision'] != TASK_LABEL_REVISION or plan['scope'] != TASK_LABEL_SCOPE
            or plan['execution_authority'] is not False
            or plan['focal_id'] != focal_id or plan['reference_id'] != reference_id
            or type(plan['core_object_ids']) is not list
            or plan['core_object_ids'] != [focal_id, reference_id]
            or type(plan['max_related_labels']) is not int):
        raise ValueError('Task label plan pair or policy binding differs')
    visual_focus = plan['visual_focus_object_ids']
    if (type(visual_focus) is not list or len(visual_focus) > MAX_VISUAL_FOCUS_IDS
            or any(not _valid_id(identity) or identity not in identities
                   for identity in visual_focus)
            or len(set(visual_focus)) != len(visual_focus)
            or visual_focus != sorted(visual_focus)
            or plan['max_related_labels'] != max(MAX_RELATED_LABELS,
                len(set(visual_focus) - {focal_id, reference_id}))):
        raise ValueError('Invalid visual focus or related label budget')
    visual_focus = set(visual_focus) - {focal_id, reference_id}
    _optional_text(plan['scene_revision'], 'scene_revision')
    _optional_text(plan['scene_fingerprint'], 'scene_fingerprint')
    related, reasons = plan['related_object_ids'], plan['related_reasons']
    if (type(related) is not list or len(related) > plan['max_related_labels']
            or any(not _valid_id(identity) or identity not in identities
                   or identity in {focal_id, reference_id} for identity in related)
            or len(set(related)) != len(related) or type(reasons) is not dict
            or set(reasons) != set(related)
            or any(type(reason) is not str or reason not in _REASON_RANK for reason in reasons.values())
            or not visual_focus.issubset(related)
            or any(reason == 'explicit_visual_focus' and identity not in visual_focus
                   for identity, reason in reasons.items())):
        raise ValueError('Invalid related task label identities or reasons')
    if related != sorted(related, key=lambda identity: _selection_key(identity, reasons, visual_focus)):
        raise ValueError('Related task label priority must be deterministic')
    count = plan['related_candidate_count']
    if (type(count) is not int or not len(related) <= count <= len(identities) - 2
            or len(related) != min(plan['max_related_labels'], count)):
        raise ValueError('Invalid related task label count')
    counts = plan['candidate_reason_counts']
    selected_counts = {reason: sum(value == reason for value in reasons.values()) for reason in _REASON_RANK}
    if (type(counts) is not dict or any(reason not in _REASON_RANK for reason in counts)
            or any(type(value) is not int or value <= 0 for value in counts.values())
            or sum(counts.values()) != count
            or any(counts.get(reason, 0) < selected for reason, selected in selected_counts.items())
            or counts.get('explicit_visual_focus', 0) != selected_counts['explicit_visual_focus']):
        raise ValueError('Invalid related candidate reason counts')
    width = plan['related_alias_hex_chars']
    if type(width) is not int or width != _prefix_length(identities, focal_id, reference_id):
        raise ValueError('Task label alias namespace differs from the current object set')
    return copy.deepcopy(plan)


def task_display_label(object_id, plan):
    """Display a known object's alias; never resolve a label into an action ID.

    The caller supplies an object from its current mesh list. The plan stores
    a compact namespace rule instead of another full copy of every scene ID.
    """
    if not _valid_id(object_id) or type(plan) is not dict:
        raise ValueError('Task display labels need a known object ID and validated plan')
    if object_id == plan.get('focal_id'):
        return 'A'
    if object_id == plan.get('reference_id'):
        return 'B'
    width = plan.get('related_alias_hex_chars')
    if type(width) is not int or not 4 <= width <= 8:
        raise ValueError('Invalid task display alias width')
    return 'R' + _alias_digest(object_id)[:width]


__all__ = ['TASK_LABEL_REVISION', 'build_task_label_plan', 'validate_task_label_plan', 'task_display_label']
