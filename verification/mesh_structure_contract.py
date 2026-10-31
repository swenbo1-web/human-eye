"""Executable M1-01 acceptance contract; NOT a production diagnostic endpoint.

Validates bounded report consistency and scores fixed, independent fixtures.
It cannot prove that a host captured truth or that a producer scanned geometry.
M1-02/M1-04 must implement source attestation and service admission separately.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter

from verification.mesh_structure_fixtures import CATEGORIES, NOT_CHECKED

SCHEMA = 'mesh-structure-evidence-v1'
LIMITS = dict(vertices=16384, edges=32768, polygons=16384, corners=65536,
              source_bytes=4*1024*1024, report_bytes=64*1024,
              regions=128, members_per_region=64, work_units=262144,
              task_queries=2, task_images=4, call_images=2, image_side=384,
              task_duration_ms=30000, retained_cache_bytes=8*1024*1024)
_EDGE_CATEGORIES = {'boundary_edges', 'nonmanifold_edges', 'loose_edges', 'winding_conflicts'}
_VERTEX_CATEGORIES = {'nonmanifold_vertices', 'isolated_vertices', 'duplicate_positions'}
_COUNTS = {'vertices', 'edges', 'polygons', 'corners'}


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value, low=0, high=2**31-1):
    return type(value) is int and low <= value <= high


def text_id(value):
    return type(value) is str and 0 < len(value) <= 256 and bool(value.strip())


def validate_task(value):
    require(type(value) is dict and set(value) ==
            {'schema', 'kind', 'task_id', 'object_ids', 'read_only', 'categories'}, 'task_fields')
    require(value['schema'] == 'spatial-readonly-task-v1' and value['read_only'] is True,
            'readonly_task_required')
    require(text_id(value['task_id']), 'task_id')
    objects = value['object_ids']
    require(type(objects) is list and all(text_id(v) for v in objects), 'object_ids')
    require(type(value['kind']) is str and value['kind'] in ('mesh_structure', 'clearance'), 'task_kind')
    require(len(objects) == (1 if value['kind'] == 'mesh_structure' else 2)
            and len(set(objects)) == len(objects), 'object_arity')
    categories = value['categories']
    allowed = set(CATEGORIES) if value['kind'] == 'mesh_structure' else {'clearance'}
    require(type(categories) is list and 1 <= len(categories) <= len(allowed)
            and all(type(v) is str and v in allowed for v in categories)
            and len(set(categories)) == len(categories), 'categories')
    # This spec describes evidence only, never a TaskApproval/TrustedTaskAuthority.
    return copy.deepcopy(value)


def validate_source(value, task):
    keys = {'object_id', 'object_instance', 'document_epoch', 'capture_id',
            'raw_sha256', 'source_kind', 'coordinate_frame', 'length_unit',
            'counts', 'capture_scope', 'geometry_complete'}
    require(type(value) is dict and set(value) == keys, 'source_fields')
    require(value['object_id'] == task['object_ids'][0], 'source_object_binding')
    require(all(text_id(value[k]) for k in ('object_instance','document_epoch','capture_id')), 'source_identity')
    require(type(value['raw_sha256']) is str and
            re.fullmatch('[0-9a-f]{64}', value['raw_sha256']) is not None, 'source_digest')
    require(value['source_kind'] == 'raw_mesh' and value['coordinate_frame'] == 'local'
            and value['length_unit'] == 'm' and value['capture_scope'] == 'target_mesh_only'
            and value['geometry_complete'] is True, 'raw_complete_target_required')
    counts = value['counts']
    require(type(counts) is dict and set(counts) == _COUNTS
            and all(integer(counts[k], high=LIMITS[k]) for k in _COUNTS), 'source_counts')
    # No inference about other objects, natural visibility, history or authority.
    return copy.deepcopy(value)


def _cluster(value, category, source):
    require(type(value) is list and 1 <= len(value) <= LIMITS['members_per_region'], 'cluster_size')
    if category in _EDGE_CATEGORIES:
        require(all(type(edge) is list and len(edge) == 2
                    and all(integer(v, high=source['vertices']-1) for v in edge)
                    and edge[0] != edge[1] for edge in value), 'edge_witness')
        result = tuple(sorted(tuple(sorted(edge)) for edge in value))
    else:
        extent = source['vertices'] if category in _VERTEX_CATEGORIES else source['polygons']
        require(all(integer(v, high=extent-1) for v in value), 'index_witness')
        result = tuple(sorted(value))
    require(len(set(result)) == len(result), 'duplicate_cluster_members')
    return result


def _bounded_json(value):
    def visit(item, depth=0):
        require(depth <= 16, 'json_depth')
        if type(item) is dict:
            require(len(item) <= 128 and all(type(k) is str and len(k) <= 256 for k in item), 'json_keys')
            for child in item.values(): visit(child, depth+1)
        elif type(item) is list:
            require(len(item) <= 1024, 'json_list_size')
            for child in item: visit(child, depth+1)
        elif type(item) is str:
            require(len(item) <= 4096, 'json_string_size')
        elif type(item) is int:
            require(abs(item) <= 2**53, 'json_integer')
        elif type(item) is float:
            require(math.isfinite(item), 'json_nonfinite')
        else:
            require(item is None or type(item) is bool, 'plain_json_only')
    visit(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(',', ':')).encode('utf8')
    except (UnicodeError, ValueError, OverflowError) as exc:
        raise ValueError('invalid_json') from exc
    require(len(raw) <= LIMITS['report_bytes'], 'report_byte_budget')
    return raw


def validate_report(value, *, expected_source=None):
    _bounded_json(value)
    require(type(value) is dict and set(value) ==
            {'schema','task','source','checks','not_checked','execution_authority','natural_visibility'},
            'report_fields')
    require(value['schema'] == SCHEMA and value['execution_authority'] is False
            and value['natural_visibility'] == 'not_checked', 'report_capabilities')
    task = validate_task(value['task'])
    require(task['kind'] == 'mesh_structure', 'structure_report_only')
    source = validate_source(value['source'], task)
    if expected_source is not None:
        require(source == expected_source, 'stale_or_mismatched_source')
    unchecked = [c for c in CATEGORIES if c not in task['categories']] + list(NOT_CHECKED)
    require(type(value['not_checked']) is list and value['not_checked'] == unchecked, 'unchecked_domains')
    checks = value['checks']
    require(type(checks) is dict and set(checks) == set(task['categories']), 'category_coverage')
    total_regions = 0
    for category, record in checks.items():
        require(type(record) is dict and set(record) ==
                {'state','scanned','found','total','regions','omitted','reason','omission_reason'}, 'check_fields')
        state = record['state']
        require(type(state) is str and state in ('complete','partial','unknown','unsupported','not_checked'), 'check_state')
        scanned = record['scanned']
        require(type(scanned) is dict and set(scanned) == _COUNTS and
                all(integer(scanned[k], high=source['counts'][k]) for k in _COUNTS), 'scanned_counts')
        require(integer(record['found']) and integer(record['omitted']), 'fact_counts')
        regions = record['regions']
        require(type(regions) is list and len(regions) <= LIMITS['regions'], 'regions')
        canonical = [_cluster(region, category, source['counts']) for region in regions]
        require(len(set(canonical)) == len(canonical), 'duplicate_regions')
        total_regions += len(regions)
        require(record['found'] == len(regions) + record['omitted'], 'omission_accounting')
        require(record['omission_reason'] == ('output_budget' if record['omitted'] else None), 'omission_reason')
        if state == 'complete':
            require(scanned == source['counts'] and integer(record['total'])
                    and record['total'] == record['found'] and record['reason'] is None, 'complete_scan')
        else:
            require(record['total'] is None and text_id(record['reason']), 'unknown_total_or_reason')
            if state != 'partial':
                require(not any(scanned.values()) and record['found'] == 0, 'unperformed_check')
    require(total_regions <= LIMITS['regions'], 'total_region_budget')
    return copy.deepcopy(value)


def score(expected, checks):
    """Exact one-to-one cluster matching. Unknown/truncation never erase FN.

    This scores delivered localization, not an unobserved hidden result. A
    bounded summary can be valid while localization acceptance remains pending.
    Partial category oracles are permitted but explicitly not full task truth.
    """
    totals = dict(tp=0, fp=0, fn=0, expected_clusters=0, scored_categories=len(expected),
                  answered_categories=0, abstained_categories=0, partial_categories=0)
    for category, wanted in expected.items():
        require(category in CATEGORIES, 'oracle_category')
        def canon(region):
            return tuple(sorted(tuple(sorted(v)) for v in region)) if category in _EDGE_CATEGORIES else tuple(sorted(region))
        truth = Counter(canon(region) for region in wanted)
        record = checks.get(category, {})
        state = record.get('state', 'not_checked')
        delivered = record.get('regions', []) if state in ('complete','partial') else []
        actual = Counter(canon(region) for region in delivered)
        tp = sum((truth & actual).values())
        totals['tp'] += tp
        totals['fp'] += sum(actual.values()) - tp
        totals['fn'] += sum(truth.values()) - tp
        totals['expected_clusters'] += sum(truth.values())
        totals['answered_categories'] += state == 'complete'
        totals['partial_categories'] += state == 'partial'
        totals['abstained_categories'] += state not in ('complete','partial')
    totals['recall'] = totals['tp']/totals['expected_clusters'] if totals['expected_clusters'] else None
    totals['answer_coverage'] = totals['answered_categories']/len(expected) if expected else None
    return totals
