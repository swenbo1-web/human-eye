"""Explicit, bounded observation queries; never an execution permission.

Query validation is pure and can run before connecting to a host. All object
membership checks require the caller's freshly validated scene namespace.
"""
from __future__ import annotations

from .measurement_presentation import finite_metric, present_measurement, valid_unrounded_measurement
from .top1_query import summarize_top1
from .support_plane_discovery import validate_support_plane_discovery_request


MAX_EXACT_PAIRS = 255
MAX_VISUAL_LABEL_IDS = 6
QUERY_POLICY_REVISION = 'bounded-observation-query-v5-support-plane-discovery-20261028'
_MODES = {'overview', 'exact_pairs', 'nearest', 'top1'}
NATIVE_VISUAL_SCHEMA = {
    'type': 'object',
    'description': 'Display policy only; never execution permission. Auto uses a negotiated read-only native host, otherwise the analytical projection. Projection skips negotiation; multiscale requires support. Labels and contact sections require projection.',
    'properties': {
        'mode': {'type': 'string', 'enum': ['auto', 'projection', 'multiscale']},
        'view': {'type': 'string', 'enum': ['SCENE', 'XY', 'XZ']},
    },
    'additionalProperties': False,
}


def _native_visual(value):
    if type(value) is not dict or set(value)-{'mode','view'}:
        raise ValueError('query.native_visual contains unsupported fields')
    mode, view = value.get('mode','auto'), value.get('view','SCENE')
    if type(mode) is not str or mode not in {'auto','projection','multiscale'}:
        raise ValueError('query.native_visual.mode must be auto, projection or multiscale')
    if type(view) is not str or view not in {'SCENE','XY','XZ'}:
        raise ValueError('query.native_visual.view must be SCENE, XY or XZ')
    return {'mode': mode, 'view': view}


def validate_query(query, *, object_ids=None, focal_id=None):
    """Normalize structure, optionally checking the fresh scene's object IDs.

    None preserves the existing near-pair overview. A reference pair always
    uses one exact-pair slot, even if a requested subset omits that reference.
    Measurement IDs retain their specified order for deterministic budget
    allocation. Explicit label IDs are a separately bounded visual request,
    normalized by full ID; they do not consume exact-pair work slots.
    """
    if type(query) is dict and query.get('mode')=='mesh_structure':
        from .structure_task import query as validate_structure_query
        return validate_structure_query(query)
    if query is None:
        query = {}
    if not isinstance(query, dict) or set(query) - {'mode', 'object_ids', 'max_exact_pairs', 'visual_diagnostic', 'label_object_ids', 'alignment_evidence', 'support_plane_discovery', 'native_visual'}:
        raise ValueError('query contains unsupported observation fields')
    mode = query.get('mode', 'overview')
    if not isinstance(mode, str) or mode not in _MODES:
        raise ValueError('query.mode must be overview, exact_pairs, nearest or top1')
    budget = query.get('max_exact_pairs', MAX_EXACT_PAIRS)
    if type(budget) is not int or not 1 <= budget <= MAX_EXACT_PAIRS:
        raise ValueError('query.max_exact_pairs must be an integer in 1..255')
    normalized = {'mode': mode, 'max_exact_pairs': budget}
    if 'native_visual' in query:
        normalized['native_visual'] = _native_visual(query['native_visual'])
        if (normalized['native_visual']['mode']=='multiscale'
                and ('label_object_ids' in query or 'visual_diagnostic' in query)):
            raise ValueError('native multiscale does not provide analytical labels or contact sections; use projection')
    if 'support_plane_discovery' in query:
        normalized['support_plane_discovery'] = validate_support_plane_discovery_request(query['support_plane_discovery'])
    if 'alignment_evidence' in query:
        if type(query['alignment_evidence']) is not bool:
            raise ValueError('query.alignment_evidence must be boolean')
        normalized['alignment_evidence'] = query['alignment_evidence']
    if 'visual_diagnostic' in query:
        if query['visual_diagnostic'] != 'contact_section' or not isinstance(query['visual_diagnostic'], str):
            raise ValueError('query.visual_diagnostic must be contact_section')
        normalized['visual_diagnostic'] = 'contact_section'
    if 'object_ids' in query:
        requested = query['object_ids']
        if mode == 'overview':
            raise ValueError('overview does not accept object_ids')
        if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_EXACT_PAIRS
                or any(not isinstance(identity, str) or not identity.strip() for identity in requested)
                or len(set(requested)) != len(requested)):
            raise ValueError('query.object_ids must be a nonempty list of unique object IDs')
        if focal_id is not None and focal_id in requested:
            raise ValueError('query.object_ids cannot include the focal object')
        if object_ids is not None and not set(requested).issubset(object_ids):
            raise ValueError('query.object_ids contains an unknown scene object')
        normalized['object_ids'] = list(requested)
    if 'label_object_ids' in query:
        # Visual focus is a separate, small request. A large measurement query
        # does not implicitly cover the scene with extra annotations.
        requested = query['label_object_ids']
        if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_VISUAL_LABEL_IDS
                or any(not isinstance(identity, str) or not identity.strip() for identity in requested)
                or len(set(requested)) != len(requested)):
            raise ValueError('query.label_object_ids must contain 1..6 unique object IDs')
        if object_ids is not None and not set(requested).issubset(object_ids):
            raise ValueError('query.label_object_ids contains an unknown scene object')
        normalized['label_object_ids'] = sorted(requested)
    return normalized


def measurement_contract(record):
    """Give observation records one explicit precision/method vocabulary.

    A negative engine clearance is a certified separating translation for
    component unions, not a globally minimal penetration-depth guarantee.
    Legacy display aliases are retained in ``legacy_display`` diagnostics;
    model-facing wording follows the unrounded metric, never the flush display
    threshold.  Conflicting or malformed strict evidence remains unknown.
    """
    result = dict(record)
    strict = result.get('strict_geometry')
    strict = strict if isinstance(strict, dict) else {}
    value = result.get('signed_clearance_m')
    if valid_unrounded_measurement(result):
        penetrating = result.get('is_penetrating') is True or value < 0
        result.update(measurement_kind='certified_penetration' if penetrating else 'exact',
            clearance_exact=not penetrating,
            method=strict.get('clearance_method', result.get('clearance_method',
                result.get('measurement_method', 'engine_geometry'))),
            clearance_scope=('certified_separating_translation_not_global_minimum'
                if penetrating else 'represented_mesh_surface_clearance'))
    elif (result.get('numeric_bound_valid') is True
            and finite_metric(result.get('clearance_lower_bound_m'))):
        result.update(measurement_kind='lower_bound', clearance_exact=False,
            method='outward_aabb_linf_lower_bound', clearance_scope='unsigned_surface_distance_lower_bound')
    else:
        result.update(measurement_kind='unknown', clearance_exact=False,
            method='measurement_unavailable', clearance_scope='unknown')
    return present_measurement(result)


def summarize_query(query, *, requested_ids, reference_id, contacts,
                    budget_deferred=(), resource_deferred=(), top1_supported_ids=(),
                    comparison_guard_m=0.):
    """Rank only a complete set of finite exact nonpenetrating clearances."""
    by_id = {record['object_id']: record for record in contacts}
    exact_ids = [identity for identity, record in by_id.items()
                 if record.get('measurement_kind') == 'exact' and record.get('clearance_exact') is True]
    unresolved = [identity for identity in requested_ids if (identity not in exact_ids
        and not (query['mode'] == 'overview' and by_id[identity].get('measurement_valid') is True))]
    top1 = None
    if query['mode'] == 'top1':
        top1, unresolved = summarize_top1(requested_ids=requested_ids, contacts=contacts,
            supported_ids=top1_supported_ids, comparison_guard_m=comparison_guard_m)
    reasons = []
    if any(identity in budget_deferred for identity in unresolved):
        reasons.append('query_exact_pair_budget_exhausted')
    if any(identity in resource_deferred for identity in unresolved):
        reasons.append('query_geometry_resource_limit')
    if any(by_id[identity].get('measurement_kind') == 'certified_penetration' for identity in unresolved):
        reasons.append('exact_penetration_depth_not_certified')
    if any(identity not in budget_deferred and identity not in resource_deferred
           and by_id[identity].get('measurement_kind') != 'certified_penetration' for identity in unresolved):
        reasons.append('query_geometry_or_measurement_unknown')
    ranked = None
    if query['mode'] == 'nearest' and not unresolved:
        ranked = sorted(requested_ids, key=lambda identity: (by_id[identity]['signed_clearance_m'], identity))
    result = {'policy_revision': QUERY_POLICY_REVISION, 'mode': query['mode'],
        'status': 'unknown' if unresolved else 'complete', 'scope': 'focal_to_requested_objects',
        'requested_object_ids': list(requested_ids), 'reference_object_id': reference_id,
        'exact_object_ids': exact_ids, 'unresolved_object_ids': unresolved,
        'ranked_object_ids': ranked, 'ranking_metric': 'nonnegative_exact_surface_clearance_m',
        'max_exact_pairs': query['max_exact_pairs'],
        'exact_pair_count': len(exact_ids),
        'measured_pair_count': sum(record.get('measurement_valid') is True for record in contacts),
        'reason_codes': reasons, 'execution_authority': False}
    if top1 is not None:
        result['top1'] = top1
        result['status'] = top1['status']
    return result


__all__ = ['MAX_EXACT_PAIRS', 'MAX_VISUAL_LABEL_IDS', 'QUERY_POLICY_REVISION', 'validate_query',
           'measurement_contract', 'summarize_query']
