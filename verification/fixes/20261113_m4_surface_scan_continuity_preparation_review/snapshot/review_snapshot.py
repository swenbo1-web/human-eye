"""Independent offline fixed-fixture review; no whole author checker or product import."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zlib

TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
BATCH = TREE / 'verification/m4_surface_scan_continuity_001'
EP = BATCH / 'episodes/C'
Q = TREE / 'verification/m4_surface_scan_001/qualification'
CANDIDATE = BATCH / 'postrun/qualification_review/source_snapshot_candidate.py'
OLD = TREE / 'verification/m4_surface_scan_001_opt1/engineering/common.py'
inputs = {}

def read(path):
    blob = path.read_bytes()
    inputs[str(path)] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    return blob

def load(path):
    return json.loads(read(path))

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

def require(ok, label):
    if not ok:
        raise AssertionError(label)

def extract(path, names, namespace):
    parsed = ast.parse(read(path).decode('utf-8-sig'), filename=str(path))
    selected = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace

oldns = extract(OLD, {'encoded', 'bind_snapshot'}, {'json': json, 'hashlib': hashlib})
ns = extract(CANDIDATE, {'canonical', 'bind_source_snapshot'}, {
    'json': json,
    'frozen': SimpleNamespace(require=require, digest=digest,
        previous_verifier=lambda: SimpleNamespace(bind_snapshot=oldns['bind_snapshot']))})
bind = ns['bind_source_snapshot']
canonical = ns['canonical']
reference = load(Q / 'BASE_SNAPSHOT.json')
initial = load(EP / 'owner/INITIAL.json')
final = load(EP / 'owner/FINAL.json')
turn = load(EP / 'TURN_BASE.json')
original = load(EP / 'RESULTS.json')
request = load(EP / 'owner/native/WIRE/002/REQUEST.bin')
response = load(EP / 'owner/native/WIRE/002/RESPONSE.bin')
events = [json.loads(line) for line in read(EP / 'owner/native/WORKER_EVENTS.jsonl').splitlines() if line]
host_blob = read(TREE / 'human_eye_plugin/blender_host.py')
read(BATCH / 'qualification/verify_continuity.py')
read(BATCH / 'engineering/run_episodes.py')

rows = []
def check(label, condition, **details):
    rows.append({'label': label, 'passed': bool(condition), **details})

def probe(label, value, should_accept):
    try:
        result = bind(value, reference)
        accepted, error = True, None
    except Exception as exc:
        result, accepted, error = None, False, {'type': type(exc).__name__, 'message': str(exc)}
    check(label, accepted == should_accept, accepted=accepted, expected_accept=should_accept, error=error)
    return result

initial_result = probe('actual_INITIAL_geometry_projection', initial, True)
final_result = probe('actual_FINAL_geometry_projection', final, True)
probe('frozen_rich_reference', copy.deepcopy(reference), True)
check('INITIAL_FINAL_exact_geometry_bytes', canonical(initial) == canonical(final))
try:
    oldns['bind_snapshot'](initial, reference)
    old_rejected = False
except AssertionError as exc:
    old_rejected = str(exc) == 'actual geometry or source fields differ from qualified state'
check('original_rich_rejection_independently_reproduced', old_rejected)

def mutate(label, operation, rich=False):
    value = copy.deepcopy(reference if rich else initial)
    operation(value)
    probe(label, value, False)

for label, value in [('unit_bool', True), ('unit_integer', 1), ('unit_changed', .01),
                     ('unit_NaN', float('nan')), ('unit_infinity', float('inf')), ('unit_string', '1.0')]:
    mutate(label, lambda data, v=value: data.__setitem__('unit_scale_m', v))
mutate('unit_missing', lambda data: data.pop('unit_scale_m'))
mutate('missing_object', lambda data: data['objects'].pop())
mutate('duplicate_name', lambda data: data['objects'][1].__setitem__('name', data['objects'][0]['name']))
mutate('name_changed', lambda data: data['objects'][0].__setitem__('name', 'wrong'))
mutate('object_order_reversed', lambda data: data['objects'].reverse())
mutate('missing_object_field', lambda data: data['objects'][0].pop('faces'))
mutate('unexpected_narrow_field', lambda data: data['objects'][0].__setitem__('parent', None))
mutate('unexpected_top_field', lambda data: data.__setitem__('schema', 'fake'))
for label, value in [('vertex_changed', .125), ('vertex_NaN', float('nan')),
                     ('vertex_infinity', float('inf')), ('vertex_string', '0.0')]:
    mutate(label, lambda data, v=value: data['objects'][0]['vertices_local'][0].__setitem__(0, v))
mutate('vertex_wrong_dimension', lambda data: data['objects'][0]['vertices_local'][0].pop())
mutate('face_missing', lambda data: data['objects'][0]['faces'].pop())
mutate('face_invalid_index', lambda data: data['objects'][0]['faces'][0].__setitem__(0, 9999))
mutate('face_integer_to_float', lambda data: data['objects'][0]['faces'][0].__setitem__(0, float(data['objects'][0]['faces'][0][0])))
mutate('face_integer_to_bool', lambda data: data['objects'][0]['faces'][0].__setitem__(0, bool(data['objects'][0]['faces'][0][0])))
mutate('face_wrong_dimension', lambda data: data['objects'][0]['faces'][0].append(0))
for label, value in [('matrix_translation', .125), ('matrix_NaN', float('nan')),
                     ('matrix_infinity', float('inf'))]:
    mutate(label, lambda data, v=value: data['objects'][0]['matrix_world'][0].__setitem__(3, v))
mutate('matrix_float_to_bool', lambda data: data['objects'][0]['matrix_world'][0].__setitem__(0, True))
mutate('matrix_wrong_dimension', lambda data: data['objects'][0]['matrix_world'].pop())
mutate('rich_parent_changed', lambda data: data['objects'][0].__setitem__('parent', 'wrong'), rich=True)

prefix = 'HUMAN_EYE_BLENDER_MCP:'
stdout = response['result']['result']
check('capture_single_prefixed_envelope', stdout.count(prefix) == 1 and stdout.startswith(prefix))
envelope = json.loads(stdout[len(prefix):])
delta = envelope['result']
capture = delta['capture']
binding = capture['binding']
check('actual_delta_capture_protocol', delta['schema'] == 'human-eye-scene-delta-v1' and
      capture['protocol'] == 'single-read-surface-scan-v1')
check('capture_scope_and_source_status', capture['scope'] == 'independent_static_triangle_meshes_current_evaluated_surfaces'
      and capture['scope_issues'] == [] and len(capture['coverage']) == 24
      and all(r['source_status'] == 'supported' and r['source_mode'] == 'evaluated_static' and r['reason'] is None for r in capture['coverage']))
check('capture_units_frame_and_same_thread', binding['frame'] == reference['frame_current'] == 1
      and binding['scale_length'] == initial['unit_scale_m'] == 1.0
      and binding['coordinate_frame'] == 'world' and binding['unit'] == 'm'
      and binding['same_main_thread_read'] is True)
check('capture_loaded_host_SHA_matches_read_source', binding['host_source_sha256'] == digest(host_blob))
check('capture_to_final_result_binding', all(binding[k] == turn['body']['binding'][k] for k in ['host_source_sha256', 'directory_sha256'])
      and binding['host_identity']['document_epoch'] == turn['body']['binding']['document_epoch'])
check('request_local_unique_capture_sequence_2', [e['sequence'] for e in events if turn['started_ns'] <= e['started_ns'] <= turn['ended_ns']] == [2])
check('request_script_bound_to_worker_event', digest(request['params']['code'].encode()) == [e for e in events if e['sequence'] == 2][0]['script_sha256'])

embedded = []
for node in ast.walk(ast.parse(request['params']['code'])):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'b64decode' and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        try:
            blob = zlib.decompress(base64.b64decode(node.args[0].value))
        except Exception:
            continue
        embedded.append({'bytes': len(blob), 'sha256': digest(blob)})
check('actual_request_embeds_exact_read_host_source', any(r['sha256'] == digest(host_blob) for r in embedded), embedded_sources=embedded)
resources = {r['id']: r for r in delta['resources']}
check('capture_resources_unique_24', len(resources) == len(delta['resources']) == 24)
meshes = capture['capture']['meshes']
geometry = []
for mesh in meshes:
    ref = mesh['_scene_resource']
    resource = resources[ref['id']]
    check('resource_revision_scale:' + mesh['name'], resource['revision'] == ref['revision'] and ref['scale'] == initial['unit_scale_m'])
    geometry.append({'name': mesh['name'], 'vertices_local': resource['vertices_local'],
                     'matrix_world': ref['matrix'], 'faces': resource['faces']})
projected = {'unit_scale_m': binding['scale_length'], 'objects': sorted(geometry, key=lambda r: r['name'])}
check('actual_capture_resources_match_owner_full_geometry', canonical(projected) == canonical(initial))
probe('actual_capture_full_geometry_matches_frozen_reference', projected, True)
check('narrow_not_mislabeled_rich', initial_result['rich_source_metadata_verified'] is False
      and initial_result['schema'] == 'owner_complete_geometry_projection')
check('original_C_failure_denominator_retained', original['execution_counts'] ==
      {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}, original_counts=original['execution_counts'])

result = {'scope': 'Independent offline AST-only snapshot adapter probes plus actual capture/resource/source-byte binding; no whole author checker, product, Blender, model or API execution.',
    'parent_task': '3a93462f-7821-488b-89b9-ca8d2c0bed0e',
    'parent_revision': 1, 'parent_write': 620,
    'own_AL_assignment': 'existing child assignment is stale; no parent handle borrowed or task updated',
    'candidate_source_report': initial_result, 'tests': rows,
    'summary': {'checks': len(rows), 'passed': sum(r['passed'] for r in rows), 'failed': sum(not r['passed'] for r in rows)},
    'original_C_counts': original['execution_counts']}
(OUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8')
(OUT / 'INPUT_SHA256.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(result['summary']))
for row in rows:
    if not row['passed']:
        print(json.dumps(row, ensure_ascii=False))
