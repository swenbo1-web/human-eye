"""Finite read queries: explicit selectors, structured facts, bounded kernels.

No prompt parsing, scene reconstruction or action token.
Selectors bind only against this call's validated capture. Pair order is A to B.
"""
from __future__ import annotations

import math
import sys

from .geometry_safety import COLLISION_TOLERANCE_M, measure_pair_geometry
from .measurement_presentation import finite_metric, valid_unrounded_measurement
from .query_policy import measurement_contract
from .surface_proximity import MAX_FACES, measure_surface_proximity, measure_spatial_relation, _rank_surface_results
from .surface_geometry import classify_closed_solids


FACTS = ('aabb', 'center_delta', 'axis_gap', 'surface_clearance',
         'solid_relation', 'nearest_witness', 'pair_relation', 'surface_proximity', 'closed_solid_relation',
         'spatial_relation')
PAIR_FACTS = frozenset(FACTS) - {'aabb'}
SET_SCOPE = 'explicit_target_candidates'
SET_FACTS = frozenset({'closed_solid_relation', 'spatial_relation', 'surface_proximity', 'aabb'})
SELECTOR_SCHEMA = {
    'type': 'object', 'properties': {'id': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                                   'name': {'type': 'string', 'minLength': 1, 'maxLength': 256}},
    'oneOf': [{'required': ['id']}, {'required': ['name']}],
    'additionalProperties': False,
}
_EXACT_HALF_MIN = 2 * sys.float_info.min


def _aabb_center_delta_component(a0, a1, b0, b1):
    # Sum endpoint contributions together, before rounding either world center.
    endpoints = (float(b0), float(b1), -float(a0), -float(a1))
    if all(value == 0 or abs(value) >= _EXACT_HALF_MIN for value in endpoints):
        try:
            return math.fsum(value * .5 for value in endpoints)
        except OverflowError:
            # An intermediate partial sum can overflow even if the result fits.
            pass
    # Halving tiny endpoints can lose a subnormal bit. Preserve their exact
    # dyadic values here, and round only the final relative quantity.
    from fractions import Fraction
    exact = sum(Fraction.from_float(value) for value in endpoints) / 2
    rounded = float(exact)
    return None if exact and rounded == 0 else rounded


def validate_object_selector(selector):
    if (type(selector) is not dict or set(selector) not in ({'id'}, {'name'})
            or any(type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256
                   for value in selector.values())):
        raise ValueError('task selector must contain exactly one nonempty id or name of at most 256 UTF-8 bytes')
    return dict(selector)


def validate_task_query(query):
    query_fields = set(query) if type(query) is dict else set()
    if (query_fields - {'geometry'} == {'mode', 'target', 'candidates', 'requested_facts'}
            or query_fields - {'geometry'} == {'mode', 'scope', 'objects', 'requested_facts'}):
        if 'target' in query:
            candidates = query['candidates']
            if type(candidates) is not list or not 1 <= len(candidates) <= 3:
                raise ValueError('task candidates must contain 1..3 explicit selectors')
            selectors = [query['target'], *candidates]
        else:
            if query['scope'] != SET_SCOPE:
                raise ValueError('Invalid canonical task set scope')
            selectors = query['objects']
        if query['mode'] != 'task' or type(selectors) is not list or not 2 <= len(selectors) <= 4:
            raise ValueError('task set requires one target and 1..3 candidates')
        selectors = [validate_object_selector(selector) for selector in selectors]
        facts = query['requested_facts']
        if (type(facts) is not list or any(type(f) is not str for f in facts)
                or len(facts) != len(set(facts)) or not set(facts) <= SET_FACTS
                or 'surface_proximity' not in facts
                or not {'closed_solid_relation', 'spatial_relation'}.intersection(facts)):
            raise ValueError('task set requires surface_proximity with closed_solid_relation or spatial_relation and optional aabb')
        result = {'mode': 'task', 'scope': SET_SCOPE, 'objects': selectors, 'requested_facts': list(facts)}
        if 'geometry' in query:
            geometry = query['geometry']
            if (type(geometry) is not dict or set(geometry) - {'objects', 'include_triangles'}
                    or type(geometry.get('objects')) is not list or not 1 <= len(geometry['objects']) <= 4
                    or type(geometry.get('include_triangles', False)) is not bool):
                raise ValueError('task geometry requires 1..4 object selectors and optional boolean include_triangles')
            result['geometry'] = {
                'objects': [validate_object_selector(selector) for selector in geometry['objects']],
                'include_triangles': geometry.get('include_triangles', False),
            }
        return result
    if type(query) is not dict or set(query) != {'mode', 'objects', 'requested_facts'}:
        raise ValueError('task query requires only mode, objects and requested_facts')
    selectors, facts = query['objects'], query['requested_facts']
    if type(selectors) is not list or not 1 <= len(selectors) <= 4:
        raise ValueError('task objects must contain 1..4 explicit selectors')
    for selector in selectors:
        validate_object_selector(selector)
    if (type(facts) is not list or not facts or any(type(f) is not str or f not in FACTS for f in facts)
            or len(facts) != len(set(facts))):
        raise ValueError('task requested_facts must be a nonempty unique finite fact list')
    if PAIR_FACTS.intersection(facts) and len(selectors) != 2:
        raise ValueError('pair facts require exactly two selectors, ordered A to B')
    return {'mode': 'task', 'objects': [dict(s) for s in selectors], 'requested_facts': list(facts)}


def _fact(value=None, *, reason=None, **metadata):
    return {'status': 'unknown' if reason else 'measured', 'value': value,
            **({'reason': reason} if reason else {}), **metadata}


def _nearest_witness(strict):
    # Only the strict kernel's original-surface witness is eligible.
    points = [strict.get('point_a_world'), strict.get('point_b_world')]
    if (strict.get('measurement_valid') is True
            and strict.get('witness_scope') == 'nearest_original_surface_points_not_internal_cell_boundaries'
            and all(type(p) is list and len(p) == 3 and all(type(v) in (int, float)
                and math.isfinite(v) for v in p) for p in points)):
        delta = [b - a for a, b in zip(*points)]
        length = math.hypot(*delta)
        distance = strict.get('signed_clearance_m')
        direction_defined = (type(distance) in (int, float) and distance > 0
            and math.isfinite(length) and length > 0)
        return _fact({'a': points[0], 'b': points[1],
            'direction_a_to_b': [v / length for v in delta] if direction_defined else None},
            semantics='strict_nearest_original_surface_points',
            direction_status='measured' if direction_defined else 'unknown',
            **({} if direction_defined else {'direction_reason':
                'undefined_zero_distance' if distance == 0 else 'world_direction_unavailable'}))
    return _fact(reason=strict.get('reason', 'strict_measurement_unavailable')
        if strict.get('measurement_valid') is not True else
        strict.get('witness_reason', 'strict_nearest_witness_unavailable'))


def _pair_relation(strict):
    """Project one strict measurement into the evidence needed by this fact."""
    distance = strict.get('signed_clearance_m')
    if not valid_unrounded_measurement(strict):
        reason = ('strict_measurement_conflict' if strict.get('measurement_valid') is True
                  else strict.get('reason', 'strict_measurement_unavailable'))
        return _fact(reason=reason)
    evidence = strict.get('relation_evidence')
    if (distance >= 0 and type(evidence) is dict
            and evidence.get('zero_tolerance_is_penetrating') is True):
        return _fact(reason='strict_relation_conflict')
    if distance < 0:
        value = {'relation': 'penetrating'}
        if type(evidence) is not dict or not evidence:
            method = strict.get('clearance_method')
            if not method:
                return _fact(value, reason='penetration_evidence_unavailable', relation_tolerance_m=0.0)
            evidence = {'method': method, 'escape_distance_m': -distance,
                'escape_scope': strict.get('penetration_metric_scope',
                    'certified_separating_translation_not_global_minimum'),
                'world_apply_verified': False}
            if 'escape_vector_world_m' in strict:
                evidence['escape_vector_a_world_m'] = strict['escape_vector_world_m']
        value['evidence'] = evidence
    else:
        value = {'relation': 'separated' if distance > 0 else 'touching', 'surface_gap_m': distance}
        if distance > 0:
            witness = _nearest_witness(strict)
            if witness['status'] == 'unknown':
                return _fact(value, reason=witness['reason'], relation_tolerance_m=0.0)
            value['nearest_witness'] = witness['value']
            if witness['direction_status'] != 'measured':
                return _fact(value, reason=witness['direction_reason'], relation_tolerance_m=0.0)
    return _fact(value, relation_tolerance_m=0.0)


def _surface_proximity_fact(measured):
    metadata = {'semantics': 'current_evaluated_triangle_surfaces_world_metres',
                'method': measured.get('method', 'exact_triangle_surface_features')}
    topology = measured.get('topology')
    distance = measured.get('distance_m')
    if measured.get('measurement_valid') is not True or not finite_metric(distance) or distance < 0:
        value = {'topology': topology} if topology is not None else None
        return _fact(value, reason=measured.get('reason') or 'surface_measurement_unavailable', **metadata)
    value = {'distance_m': distance,
        'nearest_witness': {'a': measured.get('point_a_world'), 'b': measured.get('point_b_world'),
                            'direction_a_to_b': measured.get('direction_a_to_b')},
        'topology': topology}
    metadata.update(witness_status=measured['witness_status'], direction_status=measured['direction_status'])
    for field in ('witness_reason', 'direction_reason'):
        if measured.get(field):
            metadata[field] = measured[field]
    reason = None
    if measured['witness_status'] != 'measured':
        reason = measured.get('witness_reason') or 'surface_witness_unavailable'
    elif measured['direction_status'] == 'unknown':
        reason = measured.get('direction_reason') or 'surface_direction_unavailable'
    return _fact(value, reason=reason, **metadata)


def bind_objects(scene, selectors):
    """Never interpret a name as an ID, choose an active object or break ties."""
    if scene.get('capture_scope') == 'selected_objects':
        selection = scene['task_selection']
        if selection['selectors'] != selectors:
            raise ValueError('Task selectors differ from the captured selection')
        by_id = {item['object_id']: item for item in scene['meshes']}
        rows = [dict(row) for row in selection['bindings']]
        return ([by_id.get(row.get('object_id')) for row in rows], rows, selection['pair_reason'])
    bound, rows = [], []
    for selector in selectors:
        key = 'object_id' if 'id' in selector else 'name'
        matches = [m for m in scene['meshes'] if m.get(key) == next(iter(selector.values()))]
        reason = 'object_not_found' if not matches else 'object_name_ambiguous' if len(matches) > 1 else None
        item = matches[0] if reason is None else None
        bound.append(item)
        rows.append({'object_id': item['object_id'], 'name': item['name']} if item else
                    {'status': 'unknown', 'selector': dict(selector), 'reason': reason})
    if len(bound) == 2 and all(bound) and bound[0]['object_id'] == bound[1]['object_id']:
        return bound, rows, 'pair_selectors_resolve_to_same_object'
    return bound, rows, None


def project_task_geometry(result, meshes, request, checkpoint):
    """Project only the original task bindings from its normalized capture."""
    bindings = result['binding']['objects']
    identities = {row['object_id']: row for row in bindings if 'object_id' in row}
    by_id = {mesh.object_id: mesh for mesh in meshes}
    rows = []
    for selector in request['objects']:
        checkpoint('before_task_geometry_object')
        unresolved = next((row for row in bindings if row.get('status') == 'unknown'
                           and row.get('selector') == selector), None)
        if unresolved is not None:
            rows.append({'selector': dict(selector), 'status': 'unknown', 'reason': unresolved['reason']})
            continue
        field = 'object_id' if 'id' in selector else 'name'
        value = next(iter(selector.values()))
        matches = [row for row in identities.values() if row[field] == value]
        if not matches:
            raise ValueError('task geometry selector is outside the original task bindings')
        if len(matches) > 1:
            rows.append({'selector': dict(selector), 'status': 'unknown', 'reason': 'object_name_ambiguous'})
            continue
        binding = matches[0]
        mesh = by_id[binding['object_id']]
        row = {'object_id': binding['object_id'], 'name': binding['name'],
               'vertices_world': mesh.vertices.tolist()}
        if request['include_triangles']:
            row['triangles'] = mesh.faces.tolist()
        rows.append(row)
    checkpoint('after_task_geometry')
    contract = {'vertices_world': 'current_evaluated_vertices_world_metres_in_captured_order'}
    if request['include_triangles']:
        contract['triangles'] = 'zero_based_triplets_index_vertices_world_in_captured_order'
    return {'objects': rows, 'contract': contract}


def _surface_pair_measurement(left, right, cache, checkpoint, *, source,
                              diagnostics, retain_exact_rank=False, prepared_pair=None,
                              boundary_contact=None, prepared_trees=None):
    """Internal opt-in rank results use a distinct, fully serialized cache key."""
    diagnostics['surface_pair_count'] = 0
    diagnostics['surface_pair_cache_hit'] = False
    surface_work = {}
    diagnostics['surface_work'] = surface_work
    def compute_surface():
        diagnostics['surface_pair_count'] += 1
        options = {'retain_exact_rank': True} if retain_exact_rank else {}
        if prepared_pair is not None:
            options['_prepared_pair'] = prepared_pair
        if boundary_contact is not None:
            options['_boundary_contact'] = boundary_contact
        if prepared_trees is not None:
            options['_prepared_trees'] = prepared_trees
        return measure_surface_proximity(left, right, checkpoint, diagnostics=surface_work, **options)
    face_counts = len(left.faces), len(right.faces)
    if (sum(face_counts) > MAX_FACES
            or any(len(mesh.vertices) > 3 * count
                   for mesh, count in zip((left, right), face_counts))):
        return compute_surface()
    parameters = {'source': source, 'unit': 'm', 'coordinate_frame': 'world',
                  'world_witness_tolerance_m': COLLISION_TOLERANCE_M}
    version = 'task-surface-proximity-exact-bvh-v4'
    if retain_exact_rank:
        parameters['retain_exact_rank'] = True
        version = 'task-surface-proximity-exact-world-rank-v3'
    result, diagnostics['surface_pair_cache_hit'] = cache.pair_measurement(
        left, right, compute_surface, parameters=parameters, algorithm_version=version)
    return result


def _closed_solid_pair_measurement(left, right, cache, checkpoint, *, source,
                                   diagnostics, prepared_holder=None, prepared_pair=None,
                                   prepared_trees=None):
    """Use the current ordered pair cache; preparation is query-local only."""
    diagnostics['closed_solid_pair_count'] = 0
    diagnostics['closed_solid_pair_cache_hit'] = False
    work = {}
    diagnostics['closed_solid_work'] = work
    def compute():
        diagnostics['closed_solid_pair_count'] += 1
        options = {'prepared_holder': prepared_holder} if prepared_holder is not None else {}
        if prepared_pair is not None:
            options['prepared_pair'] = prepared_pair
        if prepared_trees is not None:
            options['prepared_trees'] = prepared_trees
        return classify_closed_solids(left, right, checkpoint, diagnostics=work, **options)
    counts = len(left.faces), len(right.faces)
    if (sum(counts) > MAX_FACES
            or any(len(mesh.vertices) > 3 * count for mesh, count in zip((left, right), counts))):
        return compute()
    result, diagnostics['closed_solid_pair_cache_hit'] = cache.pair_measurement(
        left, right, compute, parameters={'source': source, 'unit': 'm', 'coordinate_frame': 'world',
            'relation_tolerance_m': 0.0}, algorithm_version='task-closed-solid-exact-local-evidence-v3')
    return result


def _closed_solid_fact(measured):
    metadata = dict(method=measured.get('method', 'exact_closed_triangle_shell_v1'),
        relation_tolerance_m=0.0,
        geometry_scope='finite_connected_closed_orientable_non_self_intersecting_triangle_shells')
    relation = measured.get('relation')
    if measured.get('measurement_valid') is True and relation in ('separated', 'touching', 'penetrating'):
        if 'certificate' in measured:
            metadata['certificate'] = measured['certificate']
        if 'local_evidence' in measured:
            metadata['local_evidence'] = measured['local_evidence']
        return _fact(relation, **metadata)
    return _fact(reason=measured.get('reason') or 'closed_solid_relation_unavailable', **metadata)


def _spatial_pair_measurement(left, right, cache, checkpoint, *, source,
                              diagnostics, retain_exact_rank=False, prepared_holder=None):
    """Cache only the new spatial/surface bundle, with query-local preparation."""
    diagnostics.update(spatial_pair_count=0, spatial_pair_cache_hit=False,
        surface_pair_count=0, surface_pair_cache_hit=False,
        closed_solid_pair_count=0, closed_solid_pair_cache_hit=False,
        surface_work={}, support_work={}, closed_solid_work={})

    def compute():
        diagnostics['spatial_pair_count'] += 1
        return measure_spatial_relation(left, right, checkpoint, diagnostics=diagnostics,
            retain_exact_rank=retain_exact_rank, prepared_holder=prepared_holder)

    counts = len(left.faces), len(right.faces)
    if (sum(counts) > MAX_FACES
            or any(len(mesh.vertices) > 3 * count for mesh, count in zip((left, right), counts))):
        return compute()
    result, diagnostics['spatial_pair_cache_hit'] = cache.pair_measurement(
        left, right, compute,
        parameters={'source': source, 'unit': 'm', 'coordinate_frame': 'world',
                    'retain_exact_rank': retain_exact_rank},
        algorithm_version='task-spatial-relation-strict-support-v1')
    return result


def _spatial_relation_fact(measured):
    metadata = dict(
        method=measured.get('method', 'exact_sufficient_spatial_relation_v1'),
        geometry_scope=measured.get('geometry_scope',
            'referenced_triangle_unions_and_their_vertex_convex_hulls'),
        relation_tolerance_m=measured.get('relation_tolerance_m', 0.0))
    for key in ('certificate', 'support_evidence', 'local_evidence'):
        if key in measured:
            metadata[key] = measured[key]
    relation = measured.get('relation')
    if measured.get('measurement_valid') is True and relation in ('separated', 'touching', 'penetrating'):
        return _fact(relation, **metadata)
    return _fact(reason=measured.get('reason') or 'spatial_relation_unavailable', **metadata)


def _closed_surface_facts(left, right, requested, cache, checkpoint, source, diagnostics, *, rank=False):
    """The existing ordered-pair helpers, with preparation local to this pair."""
    facts, surface = {}, None
    if 'spatial_relation' in requested:
        holder = {}
        checkpoint('before_spatial_pair_measurement')
        bundle = _spatial_pair_measurement(left, right, cache, checkpoint,
            source=source, diagnostics=diagnostics, retain_exact_rank=rank, prepared_holder=holder)
        checkpoint('after_spatial_pair_measurement')
        surface = bundle['surface']
        facts['spatial_relation'] = _spatial_relation_fact(bundle['spatial'])
        if 'surface_proximity' in requested:
            facts['surface_proximity'] = _surface_proximity_fact(surface)
        if 'closed_solid_relation' in requested:
            closed = bundle['closed']
            if closed is None:
                if bundle['budget_stopped']:
                    closed = {'measurement_valid': False,
                        'reason': bundle.get('stop_reason') or 'spatial_pair_work_budget_stopped'}
                else:
                    checkpoint('before_closed_solid_pair_measurement')
                    closed = _closed_solid_pair_measurement(left, right, cache, checkpoint,
                        source=source, diagnostics=diagnostics, prepared_holder=holder,
                        prepared_pair=holder.get('pair'), prepared_trees=holder.get('trees'))
                    checkpoint('after_closed_solid_pair_measurement')
            facts['closed_solid_relation'] = _closed_solid_fact(closed)
        return facts, surface
    holder = {} if {'closed_solid_relation', 'surface_proximity'} <= requested else None
    if 'closed_solid_relation' in requested:
        checkpoint('before_closed_solid_pair_measurement')
        closed = _closed_solid_pair_measurement(left, right, cache, checkpoint,
            source=source, diagnostics=diagnostics, prepared_holder=holder)
        checkpoint('after_closed_solid_pair_measurement')
        facts['closed_solid_relation'] = _closed_solid_fact(closed)
    if 'surface_proximity' in requested:
        checkpoint('before_surface_pair_measurement')
        surface = _surface_pair_measurement(left, right, cache, checkpoint,
            source=source, diagnostics=diagnostics, retain_exact_rank=rank,
            prepared_pair=holder.get('pair') if holder is not None else None,
            prepared_trees=holder.get('trees') if holder is not None else None,
            boundary_contact=holder.get('boundary_contact') if holder is not None else None)
        checkpoint('after_surface_pair_measurement')
        facts['surface_proximity'] = _surface_proximity_fact(surface)
    return facts, surface


def _aabb_fact(mesh):
    if mesh is None:
        return _fact(reason='selector_unresolved')
    low, high = mesh.bbox_min.tolist(), mesh.bbox_max.tolist()
    value = {'min': low, 'max': high, 'dimensions': [b-a for a,b in zip(low,high)]}
    return (_fact(value) if all(math.isfinite(v) for vector in value.values() for v in vector)
            else _fact(reason='world_arithmetic_not_finite'))


def _task_set_result(scene, meshes, fingerprint, query, cache, checkpoint, bound, bindings, metrics):
    """Aggregate only this complete binding; never manufacture pair captures."""
    by_id = {mesh.object_id: mesh for mesh in meshes}
    requested = frozenset(query['requested_facts'])
    relation_fact = 'spatial_relation' if 'spatial_relation' in requested else 'closed_solid_relation'
    metrics.update(exact_pair_count=0, pair_cache_hit=False, surface_pair_count=0,
        closed_solid_pair_count=0, surface_pair_cache_hits=0, closed_solid_pair_cache_hits=0,
        pair_calls=0, rank_calls=0, pairs=[])
    if relation_fact == 'spatial_relation':
        metrics.update(spatial_pair_count=0, spatial_pair_cache_hits=0)
    ids = [item['object_id'] if item is not None else None for item in bound]
    repeated = {oid for oid in ids[1:] if oid is not None and ids[1:].count(oid) > 1}
    pairs, measurements, known_penetrating, unresolved = [], {}, [], []
    known_relations = 0
    for index, item in enumerate(bound[1:]):
        checkpoint('task_set_candidate')
        oid = ids[index+1]
        reason = ('selector_unresolved' if bound[0] is None or item is None else
                  'pair_selectors_resolve_to_same_object' if oid == ids[0] else
                  'duplicate_candidate_object' if oid in repeated else None)
        work = {}
        if reason:
            facts = {name: _fact(reason=reason)
                for name in ('closed_solid_relation', 'spatial_relation', 'surface_proximity') if name in requested}
            surface = None
        else:
            facts, surface = _closed_surface_facts(by_id[ids[0]], by_id[oid], requested,
                cache, checkpoint, scene['source'], work, rank=True)
            metrics['pair_calls'] += 1
            for name in ('surface_pair_count', 'closed_solid_pair_count'):
                metrics[name] += work.get(name, 0)
            for name in ('surface_pair_cache_hit', 'closed_solid_pair_cache_hit'):
                metrics[name+'s'] += int(work.get(name, False))
            if relation_fact == 'spatial_relation':
                metrics['spatial_pair_count'] += work.get('spatial_pair_count', 0)
                metrics['spatial_pair_cache_hits'] += int(work.get('spatial_pair_cache_hit', False))
            metrics['pairs'].append(dict(candidate_index=index, object_id=oid, **work))
        relation = facts[relation_fact]['value']
        if facts[relation_fact]['status'] == 'measured':
            known_relations += 1
            if relation == 'penetrating':
                known_penetrating.append(oid)
        else:
            unresolved.append({'candidate_index': index, 'reason': facts[relation_fact]['reason']})
        gap = _fact(reason=relation_fact+'_unavailable')
        if relation == 'separated':
            distance = surface.get('distance_m') if surface is not None else None
            valid = (surface is not None and surface.get('measurement_valid') is True
                     and finite_metric(distance) and distance >= 0)
            gap = _fact(distance, semantics='separated_surface_gap_m') if valid else _fact(reason='surface_distance_unavailable')
            measurements[oid] = surface if valid else {'measurement_valid': False, 'reason': 'surface_distance_unavailable'}
        elif relation in ('touching', 'penetrating'):
            gap = {'status': 'not_applicable', 'value': None, 'reason': 'pair_is_not_separated'}
        pairs.append({'candidate_index': index, 'object_id': oid, 'facts': facts, 'separation_gap': gap})
    for name in ('surface_pair_cache_hit', 'closed_solid_pair_cache_hit'):
        metrics[name] = bool(metrics['pair_calls']) and metrics[name+'s'] == metrics['pair_calls']
    if relation_fact == 'spatial_relation':
        metrics['spatial_pair_cache_hit'] = (bool(metrics['pair_calls'])
            and metrics['spatial_pair_cache_hits'] == metrics['pair_calls'])
    metrics['rank_calls'] = 1
    ranked = _rank_surface_results(measurements, checkpoint)
    groups = ranked['ordered_object_id_groups']
    best = groups[0] if groups else []
    relations_complete = known_relations == len(pairs)
    nearest_complete = relations_complete and not ranked['unresolved']
    distance = measurements[best[0]]['distance_m'] if best else None
    complete = (nearest_complete and all(all(f['status']=='measured' for f in row['facts'].values()) for row in pairs))
    boxes = ([_aabb_fact(by_id[oid]) if oid is not None else _aabb_fact(None) for oid in ids]
             if 'aabb' in query['requested_facts'] else None)
    if boxes is not None:
        complete = complete and all(box['status'] == 'measured' for box in boxes)
    available = (any(row['facts'][relation_fact]['status'] == 'measured'
        or (row['facts']['surface_proximity']['value'] is not None
            and finite_metric(row['facts']['surface_proximity']['value'].get('distance_m')))
        for row in pairs) or boxes is not None and any(box['status'] == 'measured' for box in boxes))
    binding = {'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
        'source': scene['source'], 'objects': bindings, 'currentness': 'capture_snapshot',
        'capture_scope': scene.get('capture_scope', 'complete_scene_meshes')}
    if 'host_identity' in scene:
        binding['host_identity'] = scene['host_identity']
    if scene.get('capture_scope') == 'selected_objects':
        binding.update(candidate_count=scene['task_selection']['candidate_count'], selected_count=len(meshes))
    checkpoint('task_set_complete')
    result = {'result_kind': 'task_query',
        'schema_version': 'task-query-set-v2' if relation_fact == 'spatial_relation' else 'task-query-set-v1',
        'scope': SET_SCOPE,
        'status': 'observed' if complete else 'partial' if available else 'unknown',
        'binding': binding, 'unit': 'm', 'coordinate_frame': 'world', 'pair_order': 'target_to_candidate',
        'facts': {'aabb': boxes} if boxes is not None else {},
        'pairs': pairs, 'coverage': {'requested_candidates': len(pairs),
            'resolved_candidates': sum(oid is not None for oid in ids[1:]),
            'classified_candidates': known_relations, 'unresolved_candidates': len(unresolved)},
        'summary': {'penetration_set_complete': relations_complete,
            'known_penetrating_ids': known_penetrating,
            'penetrating_ids': known_penetrating if relations_complete else None,
            'nearest_separated_complete': nearest_complete,
            'nearest_separated_ids': best if nearest_complete else None,
            'best_known_separated_ids': best, 'distance_m': distance if nearest_complete else None,
            'best_known_distance_m': distance, 'unresolved_relations': unresolved,
            'unresolved_distances': ranked['unresolved']}, 'execution_authority': False}
    if relation_fact == 'spatial_relation':
        result['relation_fact'] = relation_fact
    return result


def surface_nearest_result(packet, cache, checkpoint, *, diagnostics=None, _normalize=None, _identity=None):
    """Internal same-capture nearest summary; never a history/action entry."""
    from .auto_router import _validated_scene
    from .runtime_identity import runtime_identity
    checkpoint('surface_nearest_binding')
    identity = runtime_identity() if _identity is None else _identity
    host_sha = next(row['sha256'] for row in identity['source_files']
                    if row['path'] == 'human_eye_plugin/blender_host.py')
    if (type(packet) is not dict or packet.get('protocol') != 'single-read-surface-candidates-v1'
            or packet.get('result_kind') != 'acquisition_only_not_nearest_result'
            or packet.get('scope') != 'independent_static_triangle_meshes_current_evaluated_surfaces'
            or packet.get('M3_qualification_performed') is not False
            or packet.get('execution_authority') is not False):
        raise ValueError('Invalid nearest acquisition contract')
    binding, coverage = packet.get('binding'), packet.get('coverage')
    if (type(binding) is not dict or binding.get('host_source_sha256') != host_sha
            or binding.get('unit') != 'm' or binding.get('coordinate_frame') != 'world'
            or binding.get('same_main_thread_read') is not True
            or not finite_metric(binding.get('scale_length')) or binding['scale_length'] <= 0
            or type(binding.get('frame')) is not int
            or type(binding.get('directory_sha256')) is not str
            or len(binding['directory_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in binding['directory_sha256'])
            or type(coverage) is not list or len(coverage) < 2):
        raise ValueError('Invalid nearest source binding')
    directory = {}
    for row in coverage:
        checkpoint('surface_nearest_directory')
        if (type(row) is not dict or type(row.get('object_id')) is not str
                or not row['object_id'] or row['object_id'] in directory):
            raise ValueError('Invalid nearest directory IDs')
        directory[row['object_id']] = row
    full = binding.get('host_identity')
    if (type(full) is not dict or full.get('schema_version') != '1.0'
            or full.get('capture_scope') != 'complete_scene_meshes'
            or type(full.get('document_epoch')) is not str or not full['document_epoch']
            or type(full.get('object_instances')) is not dict
            or set(full['object_instances']) != set(directory)
            or any(type(v) is not str or not v for v in full['object_instances'].values())
            or len(set(full['object_instances'].values())) != len(directory)):
        raise ValueError('Nearest directory differs from instance binding')
    focal, seed, upper = packet.get('focal_id'), packet.get('upper_seed_id'), packet.get('witness_upper_bound_m')
    if (type(focal) is not str or focal not in directory
            or (seed is not None and type(seed) is not str) or (upper is None and seed is not None)
            or (upper is not None and (not finite_metric(upper) or upper < 0
                or seed not in directory or seed == focal
                or directory[focal].get('witness') is None or directory[seed].get('witness') is None))):
        raise ValueError('Invalid nearest focal/upper seed')
    retained, excluded = set(), []
    for oid, row in directory.items():
        if row.get('disposition') == 'retained':
            retained.add(oid)
        elif row.get('disposition') == 'excluded_strict_bound':
            lower = row.get('lower_bound_m')
            if (oid in (focal, seed) or upper is None or not finite_metric(lower)
                    or not lower > upper or row.get('bounds_status') != 'enclosed'
                    or row.get('bounds_world_m') is None or row.get('witness') is None
                    or directory[focal].get('bounds_status') != 'enclosed'
                    or directory[focal].get('bounds_world_m') is None):
                raise ValueError('Invalid nearest strict-bound exclusion')
            excluded.append({'object_id': oid, 'status': 'not_evaluated_pruned',
                             'reason': 'strict_current_bound'})
        else:
            raise ValueError('Invalid nearest directory disposition')
    scene, meshes, fingerprint = (_validated_scene(packet.get('capture'),
        _surface_nearest_capture=True, _annotate_scene=False) if _normalize is None else _normalize())
    current = scene['host_identity']
    by_id = {mesh.object_id: mesh for mesh in meshes}
    if (scene['source'] != 'blender' or set(by_id) != retained or focal not in retained
            or (seed is not None and seed not in retained)
            or current['document_epoch'] != full['document_epoch']
            or any(token != full['object_instances'][oid] for oid, token in current['object_instances'].items())):
        raise ValueError('Nearest retained capture/source does not match directory')
    metrics = {} if diagnostics is None else diagnostics
    metrics.update(pair_calls=0, kernel_calls=0, cache_hits=0, exact_rank_calls=0, pairs={})
    measurements = {}
    for oid in sorted(retained - {focal}):
        checkpoint('before_surface_nearest_pair')
        work = {}
        measurements[oid] = _surface_pair_measurement(by_id[focal], by_id[oid], cache,
            checkpoint, source=scene['source'], diagnostics=work, retain_exact_rank=True)
        metrics['pair_calls'] += 1
        metrics['kernel_calls'] += work['surface_pair_count']
        metrics['cache_hits'] += int(work['surface_pair_cache_hit'])
        metrics['pairs'][oid] = work
        checkpoint('after_surface_nearest_pair')
    metrics['exact_rank_calls'] = 1
    ranked = _rank_surface_results(measurements, checkpoint)
    groups, unresolved = ranked['ordered_object_id_groups'], ranked['unresolved']
    best = groups[0] if groups else []
    distance = measurements[best[0]]['distance_m'] if best else None
    complete = bool(best) and not unresolved
    notes = {}
    for oid in (item for group in groups for item in group):
        result = measurements[oid]
        if result['witness_status'] == 'unknown' or result['direction_status'] == 'unknown':
            notes[oid] = {key: result[key] for key in ('witness_status', 'witness_reason',
                'direction_status', 'direction_reason') if key in result}
    evidence = []
    for oid in best:
        measured = measurements[oid]
        evidence.append({'object_id': oid,
            **{key: measured.get(key) for key in ('point_a_world', 'point_b_world',
                'direction_a_to_b', 'witness_status', 'direction_status')},
            **{key: measured[key] for key in ('witness_reason', 'direction_reason') if key in measured}})
    checkpoint('surface_nearest_complete')
    return dict(result_kind='surface_nearest', status='complete' if complete else 'partial' if best else 'unknown',
        scope='surface_nearest_candidates', focal_id=focal, nearest_ids=best if complete else None,
        best_known_ids=best, distance_m=distance if complete else None, best_known_distance_m=distance,
        unit='m', coverage={'targets_excluding_focal': len(directory)-1,
            'distance_valid': sum(len(group) for group in groups), 'strictly_excluded': len(excluded),
            'unresolved': len(unresolved)}, unresolved=unresolved, excluded=sorted(excluded, key=lambda row: row['object_id']),
        measurement_notes=notes, best_known_evidence=evidence,
        measurement_semantics={'distance': 'unsigned_surface_distance_not_penetration_depth',
            'coordinate_frame': 'world', 'pair_order': 'focal_to_candidate',
            'method': measurements[best[0]].get('method') if best else None},
        binding={'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
            'document_epoch': full['document_epoch'], 'directory_sha256': binding.get('directory_sha256'),
            'host_source_sha256': host_sha, 'runtime_source_sha256': identity['source_sha256']},
        execution_authority=False)


def task_result(scene, meshes, fingerprint, query, cache, checkpoint, *, diagnostics=None):
    """Build only selected fields; cache and solver are the existing instances."""
    bound, bindings, pair_reason = bind_objects(scene, query['objects'])
    by_id = {m.object_id: m for m in meshes}
    facts = {}
    metrics = {} if diagnostics is None else diagnostics
    if query.get('scope') == SET_SCOPE:
        return _task_set_result(scene, meshes, fingerprint, query, cache, checkpoint, bound, bindings, metrics)
    metrics['exact_pair_count'] = 0
    metrics['pair_cache_hit'] = False
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
                try:
                    delta = [_aabb_center_delta_component(*bounds) for bounds in
                        zip(left.bbox_min, left.bbox_max, right.bbox_min, right.bbox_max)]
                    facts['center_delta'] = (_fact(reason='world_arithmetic_below_float_resolution')
                        if any(value is None for value in delta) else
                        _fact(delta, semantics='B_AABB_center_minus_A_AABB_center'))
                except OverflowError:
                    facts['center_delta'] = _fact(reason='world_arithmetic_not_finite')
            if 'axis_gap' in requested_pair:
                gaps = [max(float(b0 - a1), float(a0 - b1), 0.) for a0, a1, b0, b1 in
                        zip(left.bbox_min, left.bbox_max, right.bbox_min, right.bbox_max)]
                facts['axis_gap'] = _fact(gaps, semantics='unsigned_world_AABB_interval_gaps_XYZ_not_surface_distance')
            strict = {}
            if requested_pair.intersection({'surface_clearance', 'solid_relation', 'nearest_witness', 'pair_relation'}):
                need_clearance = bool(requested_pair.intersection({'surface_clearance', 'nearest_witness', 'pair_relation'}))
                need_witness = bool(requested_pair.intersection({'nearest_witness', 'pair_relation'}))
                need_relation_evidence = bool(requested_pair.intersection({'solid_relation', 'pair_relation'}))
                checkpoint('before_task_pair_measurement')
                def compute():
                    metrics['exact_pair_count'] += 1
                    return measure_pair_geometry(left, right, need_clearance=need_clearance,
                        need_witness=need_witness, need_relation_evidence=need_relation_evidence)
                strict, metrics['pair_cache_hit'] = cache.pair_measurement(left, right, compute,
                    parameters={'need_clearance': need_clearance, 'need_witness': need_witness,
                        'need_relation_evidence': need_relation_evidence, 'source': scene['source'],
                        'unit': 'm', 'coordinate_frame': 'world', 'collision_tolerance_m': COLLISION_TOLERANCE_M},
                    algorithm_version='task-query-demanded-strict-evidence-v2')
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
                if valid and 'relation_evidence' in strict:
                    facts['solid_relation']['evidence'] = strict['relation_evidence']
            if 'nearest_witness' in requested_pair:
                facts['nearest_witness'] = _nearest_witness(strict)
            if 'pair_relation' in requested_pair:
                facts['pair_relation'] = _pair_relation(strict)
            pair_facts, _ = _closed_surface_facts(left, right, requested_pair, cache,
                checkpoint, scene['source'], metrics)
            facts.update(pair_facts)
    # Numerical overflow must not turn the otherwise known fields into a JSON
    # failure or silently provide infinite world-space values.
    for key in ('center_delta', 'axis_gap'):
        if key in facts and facts[key]['status'] == 'measured' and not all(math.isfinite(v) for v in facts[key]['value']):
            facts[key] = _fact(reason='world_arithmetic_not_finite')
    complete = all(bound) and all(
        all(row['status'] == 'measured' for row in value) if type(value) is list else value['status'] == 'measured'
        for value in facts.values())
    binding = {'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
               'source': scene['source'], 'objects': bindings}
    if scene.get('capture_scope') == 'selected_objects':
        binding.update(capture_scope='selected_objects',
            candidate_count=scene['task_selection']['candidate_count'], selected_count=len(meshes))
    return {'result_kind': 'task_query', 'schema_version': 'task-query-v3',
        'status': 'observed' if complete else 'partial',
        'binding': binding,
        'unit': 'm', 'coordinate_frame': 'world', 'pair_order': 'A_to_B',
        'facts': facts, 'execution_authority': False}
