"""Complete-scene unsigned surface threshold reduction over one host capture."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
from itertools import combinations
import json
import math

from .surface_proximity import MAX_BITS, _compare_distance_keys, _exact_distance_key


MAX_OBJECTS = 256
DEFAULT_NEW_PAIR_BUDGET = 512
DEFAULT_DELIVERY_BYTES = 512 * 1024


class _PairDeferred(Exception):
    pass


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf8')


def validate_surface_scan_query(query):
    if (type(query) is not dict or set(query) != {'mode', 'threshold_m'}
            or query['mode'] != 'surface_scan'):
        raise ValueError('surface_scan requires only mode and threshold_m')
    value = query['threshold_m']
    if type(value) not in (int, float):
        raise ValueError('surface_scan threshold_m must be finite and nonnegative')
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError('surface_scan threshold_m must be finite and nonnegative') from error
    if not math.isfinite(value) or value < 0:
        raise ValueError('surface_scan threshold_m must be finite and nonnegative')
    return {'mode': 'surface_scan', 'threshold_m': 0. if value == 0 else value}


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _bounds(value):
    return (type(value) is list and len(value) == 2
            and all(type(v) is list and len(v) == 3 for v in value)
            and all(_finite_number(x) for v in value for x in v)
            and all(lo <= hi for lo, hi in zip(*value)))


def _packet(packet, checkpoint, identity):
    from .blender_host import _acquisition_lower
    host_sha = next(row['sha256'] for row in identity['source_files']
                    if row['path'] == 'human_eye_plugin/blender_host.py')
    if (type(packet) is not dict or packet.get('protocol') != 'single-read-surface-scan-v1'
            or packet.get('result_kind') != 'acquisition_only_not_surface_scan_result'
            or packet.get('scope') != 'independent_static_triangle_meshes_current_evaluated_surfaces'
            or packet.get('M3_qualification_performed') is not False
            or packet.get('execution_authority') is not False):
        raise ValueError('Invalid surface scan acquisition contract')
    query = validate_surface_scan_query({'mode': 'surface_scan', 'threshold_m': packet.get('threshold_m')})
    threshold = query['threshold_m']
    coverage, binding = packet.get('coverage'), packet.get('binding')
    issues = packet.get('scope_issues')
    if (type(coverage) is not list or len(coverage) > MAX_OBJECTS
            or type(issues) is not list or type(binding) is not dict
            or binding.get('host_source_sha256') != host_sha
            or binding.get('unit') != 'm' or binding.get('coordinate_frame') != 'world'
            or binding.get('same_main_thread_read') is not True
            or type(binding.get('frame')) is not int
            or not _finite_number(binding.get('scale_length')) or binding['scale_length'] <= 0):
        raise ValueError('Invalid surface scan directory binding')
    directory = {}
    for row in coverage:
        checkpoint('surface_scan_directory')
        if (type(row) is not dict or any(type(row.get(k)) is not str or not row[k]
                                        for k in ('object_id', 'name'))
                or len(row['object_id'].encode('utf8')) > 256 or row['object_id'] in directory
                or row.get('source_status') not in ('supported', 'unsupported')
                or row.get('source_mode') not in ('evaluated_static', 'static_original_hidden', None)
                or row.get('bounds_status') not in ('enclosed', 'unknown')
                or row.get('reason') is not None and (type(row['reason']) is not str or not row['reason'])):
            raise ValueError('Invalid surface scan directory object')
        if ((row['bounds_status'] == 'enclosed' and not _bounds(row.get('bounds_world_m')))
                or (row['bounds_status'] == 'unknown' and row.get('bounds_world_m') is not None)
                or (row['source_status'] == 'unsupported' and not row.get('reason'))):
            raise ValueError('Invalid surface scan source or bounds')
        directory[row['object_id']] = row
    if binding.get('directory_sha256') != hashlib.sha256(_encoded(coverage)).hexdigest():
        raise ValueError('Surface scan directory digest mismatch')
    full = binding.get('host_identity')
    if (type(full) is not dict or full.get('schema_version') != '1.0'
            or full.get('capture_scope') != 'complete_scene_meshes'
            or type(full.get('document_epoch')) is not str or not full['document_epoch']
            or type(full.get('object_instances')) is not dict
            or set(full['object_instances']) != set(directory)
            or any(type(v) is not str or not v for v in full['object_instances'].values())
            or len(set(full['object_instances'].values())) != len(directory)):
        raise ValueError('Surface scan full directory identity mismatch')
    pairs = packet.get('pairs')
    expected = set(combinations(sorted(directory), 2))
    if type(pairs) is not list or len(pairs) != len(expected):
        raise ValueError('Surface scan pair coverage mismatch')
    seen, retained = set(), set()
    for row in pairs:
        checkpoint('surface_scan_pair_binding')
        ids = row.get('object_ids') if type(row) is dict else None
        if (type(ids) is not list or len(ids) != 2 or any(type(v) is not str for v in ids)
                or tuple(ids) not in expected or tuple(ids) in seen):
            raise ValueError('Surface scan duplicate or invalid pair')
        seen.add(tuple(ids))
        left, right = (directory[oid] for oid in ids)
        unsupported = left['source_status'] != 'supported' or right['source_status'] != 'supported'
        lower = _acquisition_lower(left['bounds_world_m'], right['bounds_world_m'])
        disposition = ('unknown_source' if unsupported else
                       'excluded_strict_bound' if lower > threshold else 'retained')
        claimed_lower = row.get('lower_bound_m')
        if (not _finite_number(claimed_lower) or claimed_lower < 0
                or claimed_lower != lower or row.get('disposition') != disposition):
            raise ValueError('Surface scan conservative disposition mismatch')
        if disposition == 'retained':
            retained.update(ids)
    return directory, pairs, retained, threshold, full, host_sha


def _threshold_state(measured, threshold_key, checkpoint):
    if measured.get('measurement_valid') is not True:
        return None, measured.get('reason') or 'surface_measurement_unavailable'
    key = measured.get('_exact_distance_sq')
    if (type(key) not in (list, tuple) or len(key) != 3
            or any(type(value) is not int for value in key) or key[0] < 0 or key[1] <= 0
            or key[0].bit_length() > MAX_BITS or key[1].bit_length() > MAX_BITS):
        return None, 'surface_exact_rank_key_unavailable'
    return _compare_distance_keys(key, threshold_key, checkpoint) <= 0, None


def _summary(measured):
    fields = ('measurement_valid', 'distance_m', '_exact_distance_sq', 'point_a_world',
              'point_b_world', 'witness_status', 'witness_reason', 'method')
    return {key: copy.deepcopy(measured[key]) for key in fields if key in measured}


def _deliver(result, matches, budget, checkpoint):
    result['matches'] = matches
    result['delivery'] = {'matches_total': len(matches), 'delivered_matches': len(matches),
                          'complete': True, 'byte_budget': budget}
    if len(_encoded(result)) <= budget:
        return
    result['status'] = 'unknown' if result['status'] == 'unknown' else 'partial'
    result['delivery'].update(complete=False, reason='surface_scan_delivery_budget')
    lo, hi = 0, len(matches) - 1
    while lo < hi:
        checkpoint('surface_scan_delivery')
        middle = (lo + hi + 1) // 2
        result['matches'] = matches[:middle]
        result['delivery']['delivered_matches'] = middle
        if len(_encoded(result)) <= budget:
            lo = middle
        else:
            hi = middle - 1
    result['matches'] = matches[:lo]
    result['delivery']['delivered_matches'] = lo
    if len(_encoded(result)) > budget:
        raise ValueError('surface_scan_delivery_budget_too_small')


def surface_scan_result(packet, cache, checkpoint, *, diagnostics=None, _normalize=None,
                        _identity=None, max_new_pairs=DEFAULT_NEW_PAIR_BUDGET,
                        _progress=None, max_delivery_bytes=DEFAULT_DELIVERY_BYTES):
    from .auto_router import _validated_scene
    from .runtime_identity import runtime_identity
    from .task_query import _surface_pair_measurement
    if type(max_new_pairs) is not int or not 0 <= max_new_pairs <= MAX_OBJECTS * (MAX_OBJECTS - 1) // 2:
        raise ValueError('Invalid surface scan pair work budget')
    if type(max_delivery_bytes) is not int or not 1 <= max_delivery_bytes <= 8 * 1024 * 1024:
        raise ValueError('Invalid surface scan delivery budget')
    checkpoint('surface_scan_binding')
    identity = runtime_identity() if _identity is None else _identity
    directory, pairs, retained, threshold, full, host_sha = _packet(packet, checkpoint, identity)
    scene, meshes, fingerprint = (_validated_scene(packet.get('capture'), _surface_scan_capture=True,
        _annotate_scene=False) if _normalize is None else _normalize())
    by_id = {mesh.object_id: mesh for mesh in meshes}
    current = scene.get('host_identity')
    if (scene['source'] != 'blender' or set(by_id) != retained or type(current) is not dict
            or current['document_epoch'] != full['document_epoch']
            or any(token != full['object_instances'][oid] for oid, token in current['object_instances'].items())):
        raise ValueError('Surface scan endpoint union identity mismatch')
    progress = {} if _progress is None else _progress
    key = (fingerprint, packet['binding']['directory_sha256'], threshold)
    if progress.get('binding') != key:
        progress.clear()
        progress.update(binding=key, measured={}, unknown={})
    known, unknown = progress['measured'], progress['unknown']
    numerator, denominator = threshold.as_integer_ratio()
    threshold_key = _exact_distance_key(numerator * numerator, 1, denominator)
    metrics = {} if diagnostics is None else diagnostics
    metrics.update(pair_calls=0, kernel_calls=0, cache_hits=0, continuation_hits=0,
                   directory_objects=len(directory), bound_pairs=len(pairs),
                   candidate_pairs=sum(p['disposition'] == 'retained' for p in pairs),
                   endpoint_union=len(retained), pairs={}, dispositions=[])
    counts = dict(total_pairs=len(pairs), bound_excluded=0, measured_match=0,
                  measured_nonmatch=0, unknown=0, deferred=0)
    reasons, matches = Counter(), []

    def named(oid):
        return {'id': oid, 'name': directory[oid]['name']}

    def reserve():
        checkpoint('surface_scan_before_new_pair')
        if metrics['kernel_calls'] >= max_new_pairs:
            raise _PairDeferred()
        metrics['kernel_calls'] += 1

    ordered = sorted(pairs, key=lambda row: (tuple(row['object_ids']) in unknown,
                                             row['lower_bound_m'], row['object_ids']))
    for row in ordered:
        checkpoint('surface_scan_pair')
        ids = tuple(row['object_ids'])
        entry = {'object_ids': list(ids), 'lower_bound_m': row['lower_bound_m']}
        state, reason = row['disposition'], None
        if state == 'excluded_strict_bound':
            counts['bound_excluded'] += 1
            state = 'bound_excluded'
        elif state == 'unknown_source':
            counts['unknown'] += 1
            state, reason = 'unknown', 'surface_scan_source_unsupported'
        else:
            work = {}
            if ids in known:
                measured = known[ids]
                metrics['continuation_hits'] += 1
            else:
                metrics['pair_calls'] += 1
                try:
                    measured = _surface_pair_measurement(by_id[ids[0]], by_id[ids[1]], cache,
                        checkpoint, source=scene['source'], diagnostics=work,
                        retain_exact_rank=True, before_compute=reserve)
                except _PairDeferred:
                    measured = None
                metrics['cache_hits'] += int(work.get('surface_pair_cache_hit', False))
                metrics['pairs'][json.dumps(ids, separators=(',', ':'))] = work
            if measured is None:
                state = 'unknown' if ids in unknown else 'deferred'
                reason = unknown.get(ids, 'surface_scan_pair_work_budget')
                counts[state] += 1
            else:
                match, reason = _threshold_state(measured, threshold_key, checkpoint)
                if match is None:
                    state = 'unknown'
                    unknown[ids] = reason
                    counts['unknown'] += 1
                else:
                    known[ids] = _summary(measured)
                    unknown.pop(ids, None)
                    state = 'measured_match' if match else 'measured_nonmatch'
                    counts[state] += 1
                    entry['distance_m'] = measured['distance_m']
                    if match:
                        value = {'objects': [named(oid) for oid in ids],
                                 **{key: copy.deepcopy(measured[key]) for key in (
                                     'distance_m', 'point_a_world', 'point_b_world',
                                     'witness_status', 'witness_reason', 'method') if key in measured}}
                        matches.append(value)
        entry['status'] = state
        if reason:
            entry['reason'] = reason
            reasons[(state, reason)] += 1
        metrics['dispositions'].append(entry)
    assert counts['total_pairs'] == sum(counts[key] for key in (
        'bound_excluded', 'measured_match', 'measured_nonmatch', 'unknown', 'deferred'))
    matches.sort(key=lambda row: tuple(item['id'] for item in row['objects']))
    scope_issues = copy.deepcopy(packet['scope_issues'])
    complete = not scope_issues and counts['unknown'] == counts['deferred'] == 0
    result = {'result_kind': 'surface_scan', 'status': 'unknown' if scope_issues else
              'complete' if complete else 'partial',
        'scope': 'all_scene_mesh_triangle_surfaces', 'threshold_m': threshold,
        'source_envelope': {'max_objects': MAX_OBJECTS,
                            'geometry': 'independent_static_triangle_meshes'},
        'unit': 'm', 'coordinate_frame': 'world',
        'coverage': {'objects': len(directory), **counts, 'catalog_scope_confirmed': not scope_issues},
        'scope_issues': scope_issues,
        'unsupported_objects': [dict(named(oid), reason=row['reason']) for oid, row in sorted(directory.items())
                                if row['source_status'] == 'unsupported'],
        'unresolved': [{'status': status, 'reason': reason, 'pairs': count}
                       for (status, reason), count in sorted(reasons.items())],
        'measurement_semantics': {'distance': 'unsigned_triangle_surface_distance',
                                  'predicate': 'exact_surface_distance_lte_threshold',
                                  'pair_order': 'lexical_object_id', 'solid_relation': 'not_evaluated'},
        'binding': {'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
                    'document_epoch': full['document_epoch'],
                    'directory_sha256': packet['binding']['directory_sha256'],
                    'host_source_sha256': host_sha, 'runtime_source_sha256': identity['source_sha256']},
        'execution_authority': False}
    _deliver(result, matches, max_delivery_bytes, checkpoint)
    metrics['progress_measurements'] = len(known)
    metrics['progress_unknown'] = len(unknown)
    checkpoint('surface_scan_result')
    return result
