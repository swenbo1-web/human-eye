"""Independent offline semantic probes for frozen compact scan display code.

Runs only AST-extracted pure functions from fixed Git blobs. No service, model,
Blender, product package import, author checker, or installed entry is invoked.
"""
from pathlib import Path
from contextlib import nullcontext
from fractions import Fraction
import ast
import base64
import copy
import hashlib
import json
import math
import statistics
import struct
import subprocess
import sys
import time

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
BASE = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
CANDIDATE = '452b44d2'
DELIVERY = '6ab4e53409e539c71a377f48708f2f8725db6dde'
REL = 'human_eye_plugin/live_spatial_mcp.py'
SOURCES = {}
CHECKS = []
OBSERVATIONS = []
PROBES = []


def remember(name, data):
    SOURCES[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def read(path):
    return remember(str(path), path.read_bytes())


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def fingerprint(value):
    # Preserve distinctions that Python == collapses: bool/int/float, +0/-0.
    if type(value) is float:
        return ['float64', struct.pack('>d', value).hex()]
    if type(value) is dict:
        return ['object', sorted((str(k), fingerprint(v)) for k, v in value.items())]
    if type(value) is list:
        return ['array', [fingerprint(v) for v in value]]
    return [type(value).__name__, value]


def check(label, okay, details=None):
    CHECKS.append({'name': label, 'passed': bool(okay), **({'details': details} if details else {})})


def load_functions(revision):
    source = remember(revision + ':' + REL, git('show', revision + ':' + REL))
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {
        'project_surface_scan_brief', '_tool_result', '_project_capability_aliases',
        '_project_support_plane_discovery_aliases'}]
    namespace = {'Any': object, 'json': json, 'copy': copy, 'math': math,
                 'time': time, 'base64': base64,
                 'span': lambda *a, **kw: nullcontext(),
                 'annotate': lambda **kw: None,
                 'record_image_artifact': lambda *a, **kw: None}
    exec(compile(ast.Module(body=selected, type_ignores=[]), revision + ':' + REL, 'exec'), namespace)
    return namespace, source


def result_text(namespace, value, **kwargs):
    return namespace['_tool_result'](value, is_error=kwargs.pop('is_error', False), **kwargs)['content'][0]['text']


def decode(compact):
    # Consumer-style independent decoder: interpret advertised columns, indices,
    # and merge rule, without knowing implementation's common-field selection.
    columns = compact['match_columns']
    table = compact['objects']
    patches = {e['match_index']: e['metadata'] for e in compact['match_exceptions']}
    assert len(patches) == len(compact['match_exceptions'])
    rows = []
    for index, vector in enumerate(compact['matches']):
        assert len(vector) == len(columns)
        row = dict(zip(columns, vector))
        a, b = table[row['object_a_ref']], table[row['object_b_ref']]
        assert a['name'] == row['object_a'] and b['name'] == row['object_b']
        metadata = copy.deepcopy(compact['match_metadata'])
        metadata.update(copy.deepcopy(patches.get(index, {})))
        metadata.update(objects=[copy.deepcopy(a), copy.deepcopy(b)], distance_m=row['distance_m'])
        rows.append(metadata)
    return rows


def expected_rows(full):
    return [{k: v for k, v in row.items() if k not in ('point_a_world', 'point_b_world')}
            for row in full['matches']]


def check_value(label, full, namespace):
    before = fingerprint(full)
    compact = namespace['project_surface_scan_brief'](full)
    check(label + '.projected', compact is not None)
    if compact is None:
        return
    wire = json.loads(encode(compact))
    check(label + '.all_rows_and_metadata_roundtrip', fingerprint(decode(wire)) == fingerprint(expected_rows(full)))
    check(label + '.all_original_top_fields', all(fingerprint(wire[k]) == fingerprint(v)
          for k, v in full.items() if k != 'matches'))
    check(label + '.input_unchanged', fingerprint(full) == before)
    check(label + '.default_equals_brief', result_text(namespace, full) == result_text(namespace, full, response_detail='brief'))
    check(label + '.full_equals_original_bytes', result_text(namespace, full, response_detail='full') == encode(full))
    check(label + '.error_equals_original_bytes', result_text(namespace, full, is_error=True) == encode(full))
    check(label + '.table_scope', wire['object_table_scope'] == 'matched_endpoints_only')
    check(label + '.fresh_full_notice', 'new current observation' in wire['detail'])
    PROBES.append({'name': label, 'full_bytes': len(encode(full).encode('utf8')),
                   'compact_bytes': len(encode(compact).encode('utf8')), 'rows': len(full['matches'])})
    return compact


def fixture():
    return {'result_kind': 'surface_scan', 'status': 'partial', 'unit': 'm', 'coordinate_frame': 'world',
        'scope': 'all_scene_mesh_triangle_surfaces', 'threshold_m': 0.002,
        'source_envelope': {'geometry': 'fixture_only'},
        'binding': {'scene_revision': 'r1', 'source': 'fixed-fixture'}, 'trace_id': 'fixture',
        'execution_authority': {'allow_action': False},
        'coverage': {'objects': 4, 'total_pairs': 6, 'measured_match': 3, 'unknown': 1, 'deferred': 1},
        'scope_issues': ['fixture_unknown'], 'unsupported_objects': [{'id': 'D', 'reason': 'unsupported'}],
        'unresolved': [{'objects': ['C', 'D'], 'status': 'unknown'}],
        'delivery': {'matches_total': 5, 'delivered_matches': 3, 'complete': False, 'scope': 'upstream_only'},
        'matches': [
            {'objects': [{'id': 'A', 'name': '重复名'}, {'id': 'B', 'name': '重复名'}],
             'distance_m': -0.0, 'point_a_world': [0.0, 0.0, 0.0], 'point_b_world': [0.0, 0.0, 0.0],
             'witness_status': 'measured', 'method': 'known', 'future': {'a': 1, 'b': False}},
            {'objects': [{'id': 'B', 'name': '重复名'}, {'id': 'C', 'name': '对象\n"é😀'}],
             'distance_m': math.nextafter(0.002, 0), 'method': 'known', 'witness_status': 'uncertain',
             'reason': 'uncertain_boundary', 'future': {'a': 1.0, 'b': 0}},
            {'objects': [{'id': 'A', 'name': '重复名'}, {'id': 'C', 'name': '对象\n"é😀'}],
             'distance_m': math.nextafter(0.002, math.inf), 'method': 'known', 'witness_status': None,
             'future': {'a': True, 'b': -0.0}}]}


def main():
    head = git('rev-parse', 'HEAD').decode().strip()
    check('fixed_delivery_head', head == DELIVERY, head)
    check('author_worktree_clean', not git('status', '--porcelain').strip())
    candidate, candidate_source = load_functions(CANDIDATE)
    old, old_source = load_functions(BASE)
    runtime_diff = git('diff', '--name-only', BASE, CANDIDATE, '--', 'human_eye_plugin').decode().splitlines()
    check('single_runtime_file', runtime_diff == [REL], runtime_diff)
    plan = read(Path('D:/hefe/docs/M4_SURFACE_SCAN_COMPACT_FACTS_001_PLAN.md'))
    read(ROOT / 'verification/m4_surface_scan_compact_facts_001/COMPATIBILITY.md')
    blobs = []
    for cell in ('P1', 'P2', 'P3'):
        for tool in ('tool_01', 'tool_02'):
            path = ROOT / 'verification/m4_surface_scan_consumption_001/cells' / cell / 'owner' / tool / 'RESPONSE.json'
            full = json.loads(json.loads(read(path))['result']['content'][0]['text'])
            blobs.append(full)
            compact = check_value(cell + '.' + tool, full, candidate)
            check(cell + '.' + tool + '.row_count', len(compact['matches']) == 71)
            check(cell + '.' + tool + '.body_10KiB', len(encode(compact).encode('utf8')) <= 10240)
            check(cell + '.' + tool + '.full_old_byte_parity', result_text(candidate, full, response_detail='full') == result_text(old, full))
            for i, (a, b) in enumerate(zip(full['matches'], decode(compact))):
                check(cell + '.' + tool + '.exact_distance_bits.' + str(i), fingerprint(a['distance_m']) == fingerprint(b['distance_m']))
    full = fixture()
    compact = check_value('partial_duplicate_names_future_exceptions', full, candidate)
    check('partial_retains_incomplete_delivery', compact['status'] == 'partial' and compact['delivery']['complete'] is False)
    check('same_names_different_ids', len(compact['objects']) == 3 and compact['matches'][0][2] != compact['matches'][0][3])
    check('future_typed_values_not_collapsed', 'future' not in compact['match_metadata'])
    check('only_shared_method_common', compact['match_metadata'] == {'method': 'known'})
    copy_probe = candidate['project_surface_scan_brief'](full)
    copy_probe['objects'][0]['name'] = 'MUTATED'
    copy_probe['coverage']['objects'] = 999
    copy_probe['match_exceptions'][0]['metadata']['future']['a'] = 999
    check('projection_detached', full['matches'][0]['objects'][0]['name'] == '重复名' and full['coverage']['objects'] == 4 and full['matches'][0]['future']['a'] == 1)
    for status in ('complete', 'unknown', 'partial'):
        value = fixture(); value['matches'] = []; value['status'] = status
        check_value('empty_' + status, value, candidate)
    value = fixture(); value['future_top'] = {'nested': [False, None, -0.0, {'unicode': '未来'}]}
    for row in value['matches']:
        row['future_list'] = [{'signed': -0.0}, {'nullable': None}]
        for obj in row['objects']: obj['future_endpoint'] = {'x': [0, 1]}
    check_value('future_top_row_endpoint', value, candidate)
    value = fixture()
    value['matches'][0]['nullable'] = None
    value['matches'][1]['nullable'] = None
    check_value('null_present_vs_missing', value, candidate)
    value = fixture()
    for i, row in enumerate(value['matches']): row['same_numeric_python_equality'] = [0.0, -0.0, 0][i]
    check_value('metadata_signed_zero_type', value, candidate)
    for index, distance in enumerate([0, 0.0, -0.0, 1, math.ulp(0.0), sys.float_info.min,
            math.nextafter(0.002, 0), 0.002, math.nextafter(0.002, math.inf),
            1e305, 1e306, sys.float_info.max, 10 ** 350]):
        value = fixture(); value['matches'] = [value['matches'][0]]; value['matches'][0]['distance_m'] = distance
        value['delivery'].update(matches_total=1, delivered_matches=1)
        compact = check_value('numeric_' + str(index), value, candidate)
        mm = compact['matches'][0][5]
        if type(mm) is str:
            check('numeric_' + str(index) + '.overflow_mm_exact', Fraction(mm) == Fraction(distance) * 1000)
        else:
            check('numeric_' + str(index) + '.no_nonfinite_or_false_zero',
                  type(mm) is int or math.isfinite(mm) and (distance == 0 or mm != 0))
            if type(distance) is float and distance == 0:
                check('numeric_' + str(index) + '.mm_signed_zero', math.copysign(1.0, mm) == math.copysign(1.0, distance))
    unsupported = []
    for field in ('display_encoding', 'objects', 'object_table_scope', 'object_reference', 'match_columns',
                  'match_metadata', 'match_exceptions', 'match_metadata_semantics', 'distance_mm_semantics', 'detail'):
        value = fixture(); value[field] = {'future': True}; unsupported.append(('reserved_' + field, value))
    for field, replacement in [('status', 'new_unknown_variant'), ('unit', 'mm'), ('coordinate_frame', 'object'), ('matches', {})]:
        value = fixture(); value[field] = replacement; unsupported.append(('shape_' + field, value))
    for distance in (-1.0, True, '0.1', None):
        value = fixture(); value['matches'][0]['distance_m'] = distance; unsupported.append(('bad_distance_' + repr(distance), value))
    for point in ([0.0, 0.0], [False, 0, 0], {'x': 0}, [0, None, 0]):
        value = fixture(); value['matches'][0]['point_a_world'] = point; unsupported.append(('bad_point_' + repr(point), value))
    value = fixture(); value['matches'][0]['objects'] = []; unsupported.append(('bad_endpoint_count', value))
    value = fixture(); value['matches'][0]['objects'][0]['id'] = ''; unsupported.append(('empty_endpoint_id', value))
    value = fixture(); value['matches'][2]['objects'][0]['name'] = 'conflicting_name'; unsupported.append(('same_id_conflicting_endpoint', value))
    for label, value in unsupported:
        check(label + '.projector_unsupported', candidate['project_surface_scan_brief'](value) is None)
        check(label + '.fallback_original_bytes', result_text(candidate, value) == encode(value))
    for label, modify in [('distance_nan', lambda v: v['matches'][0].update(distance_m=math.nan)),
                          ('point_infinity', lambda v: v['matches'][0].update(point_a_world=[math.inf, 0, 0])),
                          ('future_nan', lambda v: v.update(future=math.nan))]:
        value = fixture(); modify(value)
        for revision, namespace in [('old', old), ('candidate', candidate)]:
            try:
                result_text(namespace, value)
            except ValueError:
                check(label + '.' + revision + '.reject_nonfinite', True)
            else: check(label + '.' + revision + '.reject_nonfinite', False)
    original_projector = candidate['project_surface_scan_brief']
    def broken_projector(value): raise RuntimeError('independent_probe_display_exception')
    candidate['project_surface_scan_brief'] = broken_projector
    check('projection_exception_fallback_exact_full', result_text(candidate, fixture()) == encode(fixture()))
    candidate['project_surface_scan_brief'] = lambda v: {'nonfinite_generated': math.nan}
    check('projection_encoding_exception_fallback_exact_full', result_text(candidate, fixture()) == encode(fixture()))
    candidate['project_surface_scan_brief'] = original_projector
    for kind in ('task_query', 'surface_nearest', 'scene_directory', 'other_legacy', None):
        value = {'status': 'partial', 'facts': {'distance_m': -0.0}, 'error': None}
        if kind: value['result_kind'] = kind
        check('non_scan_default_' + str(kind), result_text(candidate, value) == result_text(old, value))
    arm = {'schema': 'arm-twist-expert-report-v1', 'status': 'unknown', 'reason': 'fixture'}
    check('arm_expert_default_unchanged', result_text(candidate, arm) == result_text(old, arm))
    error = {'status': 'error', 'tool_outcome': 'unknown', 'automatic_retry': False, 'error': 'receipt_failed'}
    check('generic_error_default_unchanged', result_text(candidate, error, is_error=True) == result_text(old, error, is_error=True))
    # Source-level public-schema and routing checks do not stand in for real tool invocation.
    source_text = candidate_source.decode('utf8')
    check('scan_default_schema_annotation', '"response_detail": {"default": "brief"}' in source_text)
    check('non_scan_default_schema_annotation', '"response_detail": {"default": "full"}' in source_text)
    check('route_does_not_force_full', "response_detail=args.get('response_detail')," in source_text)
    check('public_mentions_new_current_full', 'Full requests a new current observation' in source_text)
    check('public_mentions_matched_endpoint_scope', 'Its object table covers matched endpoints' in source_text)
    # A single profile probe: identify representation overhead, not an optimization sweep.
    costs = {}
    sample = blobs[0]
    for name, action in [('old_full', lambda: result_text(old, sample)),
                         ('candidate_full', lambda: result_text(candidate, sample, response_detail='full')),
                         ('candidate_default', lambda: result_text(candidate, sample))]:
        times = []
        for _ in range(60):
            started = time.perf_counter_ns(); action(); times.append((time.perf_counter_ns()-started)/1e6)
        costs[name] = {'calls': 60, 'median_ms': statistics.median(times), 'p95_ms': sorted(times)[56]}
    OBSERVATIONS.append({'kind': 'offline_function_only_cost', 'costs': costs,
                         'not_full_request_timing': True, 'telemetry_stubbed': True})
    # Identify needless fallback, but never reinterpret it as loss or a blocker.
    reorder = fixture(); reorder['matches'][2]['objects'][0] = {'name': '重复名', 'id': 'A'}
    OBSERVATIONS.append({'kind': 'equivalent_endpoint_key_order_falls_back',
                         'observed': original_projector(reorder) is None,
                         'payload_preserved': result_text(candidate, reorder) == encode(reorder)})
    small = copy.deepcopy(sample); small['matches'] = []
    OBSERVATIONS.append({'kind': 'empty_real_envelope_bytes', 'full': len(encode(small).encode('utf8')),
                         'compact': len(result_text(candidate, small).encode('utf8'))})
    check('author_worktree_still_clean', not git('status', '--porcelain').strip())
    remember(str(Path(__file__)), Path(__file__).read_bytes())
    result = {'scope': 'independent offline fixed-source display semantics', 'candidate': CANDIDATE,
              'delivery': DELIVERY, 'baseline': BASE, 'checks': len(CHECKS),
              'passed': sum(x['passed'] for x in CHECKS), 'failed': [x for x in CHECKS if not x['passed']],
              'probes': PROBES, 'observations': OBSERVATIONS,
              'exclusions': ['No Blender/model/API', 'No installed-entry verification in this script',
                             'No provider/rendered input claim', 'No historical full evidence retrieval claim']}
    for name, value in [('RESULT.json', result), ('CHECKS.json', CHECKS), ('INPUT_SHA256.json', SOURCES)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'checks': result['checks'], 'passed': result['passed'], 'failed': result['failed'],
                      'first_probe': PROBES[0], 'observations': OBSERVATIONS}, ensure_ascii=False, indent=2))
    return 0 if result['passed'] == result['checks'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
