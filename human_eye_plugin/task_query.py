"""Finite read queries: explicit selectors, structured facts, existing kernels.

No prompt parsing, scene reconstruction, action token or new geometry solver.
Selectors bind only against this call's validated capture. Pair order is A to B.
"""
from __future__ import annotations

import math

from .geometry_safety import COLLISION_TOLERANCE_M, measure_pair_geometry
from .query_policy import measurement_contract


FACTS = ('aabb', 'center_delta', 'axis_gap', 'surface_clearance',
         'solid_relation', 'nearest_witness')
PAIR_FACTS = frozenset(FACTS) - {'aabb'}
SELECTOR_SCHEMA = {
    'type': 'object', 'properties': {'id': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                                   'name': {'type': 'string', 'minLength': 1, 'maxLength': 256}},
    'oneOf': [{'required': ['id']}, {'required': ['name']}],
    'additionalProperties': False,
}


def validate_task_query(query):
    if type(query) is not dict or set(query) != {'mode', 'objects', 'requested_facts'}:
        raise ValueError('task query requires only mode, objects and requested_facts')
    selectors, facts = query['objects'], query['requested_facts']
    if type(selectors) is not list or not 1 <= len(selectors) <= 4:
        raise ValueError('task objects must contain 1..4 explicit selectors')
    for selector in selectors:
        if (type(selector) is not dict or set(selector) not in ({'id'}, {'name'})
                or any(type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256
                       for value in selector.values())):
            raise ValueError('task selector must contain exactly one nonempty id or name of at most 256 UTF-8 bytes')
    if (type(facts) is not list or not facts or any(type(f) is not str or f not in FACTS for f in facts)
            or len(facts) != len(set(facts))):
        raise ValueError('task requested_facts must be a nonempty unique finite fact list')
    if PAIR_FACTS.intersection(facts) and len(selectors) != 2:
        raise ValueError('pair facts require exactly two selectors, ordered A to B')
    return {'mode': 'task', 'objects': [dict(s) for s in selectors], 'requested_facts': list(facts)}


def _fact(value=None, *, reason=None, **metadata):
    return {'status': 'unknown' if reason else 'measured', 'value': value,
            **({'reason': reason} if reason else {}), **metadata}


def bind_objects(scene, selectors):
    """Never interpret a name as an ID, choose an active object or break ties."""
    bound, rows = [], []
    for selector in selectors:
        key = 'object_id' if 'id' in selector else 'name'
        matches = [m for m in scene['meshes'] if m.get(key) == next(iter(selector.values()))]
        reason = 'object_not_found' if not matches else 'object_name_ambiguous' if len(matches) > 1 else None
        item = matches[0] if reason is None else None
        bound.append(item)
        rows.append({'status': 'bound' if item else 'unknown',
                     **({'object_id': item['object_id'], 'name': item['name']} if item
                        else {'selector': dict(selector), 'reason': reason})})
    if len(bound) == 2 and all(bound) and bound[0]['object_id'] == bound[1]['object_id']:
        return bound, rows, 'pair_selectors_resolve_to_same_object'
    return bound, rows, None


def task_result(scene, meshes, fingerprint, query, cache, checkpoint):
    """Build only selected fields; cache and solver are the existing instances."""
    bound, bindings, pair_reason = bind_objects(scene, query['objects'])
    by_id = {m.object_id: m for m in meshes}
    facts, metrics = {}, {'exact_pair_count': 0, 'pair_cache_hit': False}
    if 'aabb' in query['requested_facts']:
        boxes = []
        for item in bound:
            if item is None:
                boxes.append(_fact(reason='selector_unresolved'))
                continue
            mesh = by_id[item['object_id']]
            low, high = mesh.bbox_min.tolist(), mesh.bbox_max.tolist()
            value = {'min': low, 'max': high,
                'dimensions': [b - a for a, b in zip(low, high)]}
            boxes.append(_fact(value) if all(math.isfinite(v) for vector in value.values() for v in vector)
                         else _fact(reason='world_arithmetic_not_finite'))
        facts['aabb'] = boxes
    requested_pair = PAIR_FACTS.intersection(query['requested_facts'])
    if requested_pair:
        reason = pair_reason or ('selector_unresolved' if not all(bound) else None)
        if reason:
            facts.update({key: _fact(reason=reason) for key in query['requested_facts'] if key in PAIR_FACTS})
        else:
            left, right = [by_id[item['object_id']] for item in bound]
            if 'center_delta' in requested_pair:
                # Half first avoids overflow from adding world coordinates.
                delta = ((right.bbox_min / 2 + right.bbox_max / 2)
                         - (left.bbox_min / 2 + left.bbox_max / 2)).tolist()
                facts['center_delta'] = _fact(delta, semantics='B_AABB_center_minus_A_AABB_center')
            if 'axis_gap' in requested_pair:
                gaps = [max(float(b0 - a1), float(a0 - b1), 0.) for a0, a1, b0, b1 in
                        zip(left.bbox_min, left.bbox_max, right.bbox_min, right.bbox_max)]
                facts['axis_gap'] = _fact(gaps, semantics='unsigned_world_AABB_interval_gaps_XYZ_not_surface_distance')
            strict = {}
            if requested_pair.intersection({'surface_clearance', 'solid_relation', 'nearest_witness'}):
                need_clearance = bool(requested_pair.intersection({'surface_clearance', 'nearest_witness'}))
                checkpoint('before_task_pair_measurement')
                def compute():
                    metrics['exact_pair_count'] += 1
                    return measure_pair_geometry(left, right, need_clearance=need_clearance)
                strict, metrics['pair_cache_hit'] = cache.pair_measurement(left, right, compute,
                    parameters={'need_clearance': need_clearance, 'source': scene['source'],
                        'unit': 'm', 'coordinate_frame': 'world', 'collision_tolerance_m': COLLISION_TOLERANCE_M},
                    algorithm_version='task-query-existing-strict-kernel-v1')
                checkpoint('after_task_pair_measurement')
            unknown = strict.get('reason', 'strict_measurement_unavailable')
            valid = strict.get('measurement_valid') is True
            if 'surface_clearance' in requested_pair:
                measured = measurement_contract(strict)
                value = strict.get('signed_clearance_m')
                if valid and type(value) in (int, float) and math.isfinite(value):
                    facts['surface_clearance'] = _fact(value, kind=measured['measurement_kind'],
                        method=measured['method'], semantics=measured['clearance_scope'])
                else:
                    facts['surface_clearance'] = _fact(reason=unknown)
            if 'solid_relation' in requested_pair:
                facts['solid_relation'] = (_fact('penetrating' if strict['is_penetrating'] else 'not_penetrating',
                    tolerance_m=COLLISION_TOLERANCE_M,
                    semantics='certified_solid_overlap_at_tolerance_not_physical_contact') if valid
                    else _fact(reason=unknown))
            if 'nearest_witness' in requested_pair:
                # Only the strict kernel's original-surface witness is eligible.
                # Convex scalar-only and display-probe points are never promoted.
                points = [strict.get('point_a_world'), strict.get('point_b_world')]
                if (valid and strict.get('witness_scope') == 'nearest_original_surface_points_not_internal_cell_boundaries'
                        and all(type(p) is list and len(p) == 3 and all(type(v) in (int, float)
                            and math.isfinite(v) for v in p) for p in points)):
                    delta = [b - a for a, b in zip(*points)]
                    length = math.hypot(*delta)
                    facts['nearest_witness'] = _fact({'a': points[0], 'b': points[1],
                        'direction_a_to_b': [v / length for v in delta] if length > 0 else None},
                        semantics='strict_nearest_original_surface_points',
                        direction_status='measured' if length > 0 else 'unknown',
                        **({} if length > 0 else {'direction_reason': 'undefined_zero_distance'}))
                else:
                    facts['nearest_witness'] = _fact(reason=unknown if not valid else 'strict_nearest_witness_unavailable')
    # Numerical overflow must not turn the otherwise known fields into a JSON
    # failure or silently provide infinite world-space values.
    for key in ('center_delta', 'axis_gap'):
        if key in facts and facts[key]['status'] == 'measured' and not all(math.isfinite(v) for v in facts[key]['value']):
            facts[key] = _fact(reason='world_arithmetic_not_finite')
    complete = all(row['status'] == 'bound' for row in bindings) and all(
        all(row['status'] == 'measured' for row in value) if type(value) is list else value['status'] == 'measured'
        for value in facts.values())
    return {'result_kind': 'task_query', 'schema_version': 'task-query-v1',
        'status': 'observed' if complete else 'partial',
        'binding': {'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint, 'source': scene['source'],
                    'objects': bindings},
        'unit': 'm', 'coordinate_frame': 'world', 'pair_order': 'A_to_B',
        'facts': facts, 'work': metrics, 'execution_authority': False}
