"""Independent saved-data audit; no product/Blender/consumer or timing calls."""
import ast
import collections
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT/'verification/m4_batch_observation_coverage_001'
PIN = '0bcd1660d1ddb43869d077e2c1b63240cb670826'
sha = lambda blob: hashlib.sha256(blob).hexdigest()
read = lambda path: json.loads(path.read_bytes())
checks = []

def check(value, name):
    checks.append({'check': name, 'passed': bool(value)})

def save(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

snapshot = HERE/'snapshot'
snapshot.mkdir(exist_ok=True)
copies = {}
for relative in ('prototype/final.py','prototype/draft.py','validation/verify_projection.py',
                 'validation/native_projection.py','validation/MANIFEST.json',
                 'validation/SPEC.json','validation/prepare_validation.py'):
    blob = (BATCH/relative).read_bytes()
    destination = snapshot/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as stream: stream.write(blob)
    copies[relative] = {'sha256': sha(blob), 'bytes': len(blob)}
save(HERE/'SOURCE_COPIES.json', {'declared_fixed_commit': PIN, 'copies': copies})

# Replay the frozen verifier once, from copied code. It reads original evidence;
# writes only this review directory. Its native implementation is the copy.
verifier = module(snapshot/'validation/verify_projection.py', 'copied_coverage_verifier')
verifier.BATCH, verifier.ROOT = BATCH, ROOT
sys.argv = ['verify_projection.py', '--prototype', str(snapshot/'prototype/final.py'),
            '--output', str(HERE/'REPLAY_674.json')]
exit_status = verifier.main()
check(exit_status == 0, 'frozen_verifier_offline_replay')
replay = read(HERE/'REPLAY_674.json')
old = read(BATCH/'validation/RESULTS_01.json')
check(replay['checks'] == old['checks'], 'same_674_assertions_and_results')

final = module(snapshot/'prototype/final.py','copied_batch_final')
draft = module(snapshot/'prototype/draft.py','copied_batch_draft')
bundle = read(BATCH/'input_02/BUNDLE.json')
binding = read(BATCH/'input_02/SOURCE_BINDING.json')
primary = read(BATCH/'input_02/REQUEST_PRIMARY.json')
optional = read(BATCH/'input_02/REQUEST_OPTIONAL_UNION.json')
directory = final.directory(bundle)
selected = final.selected_observation(bundle, primary)
named = {row['object_id']: row['name'] for row in bundle['objects']}
primary_union = {row['object_id'] for row in primary['objects']}
for row in primary['relation_pairs']: primary_union.update((row['target_id'], row['candidate_id']))
optional_union = {row['object_id'] for row in optional['objects']}
for row in optional['relation_pairs']: optional_union.update((row['target_id'], row['candidate_id']))
check(len(primary['objects']) == 2 and len(primary['relation_pairs']) == 3 and len(primary_union) == 4,
      'primary_two_geometry_three_relation_four_host_objects')
check(len(optional_union) == 8, 'optional_union_requires_eight_objects')
check(selected['status']=='observed' and not selected['gaps'], 'explicit_primary_request_fully_projected')

# Independently verify the host ID mapping omitted by verify_saved_base's
# relation-to-name reconstruction, and unchanged initial/final saved state.
paths = binding['source_paths_sha256']
initial = read(ROOT/next(path for path in paths if path.endswith('/INITIAL.json')))
last = read(ROOT/next(path for path in paths if path.endswith('/FINAL.json')))
check(initial == last, 'saved_initial_final_state_equal')
response = read(ROOT/next(path for path in paths if path.endswith('/tool_02/RESPONSE.json')))
body = json.loads(response['result']['content'][0]['text'])
ids = {row['name']: row['host_object_id'] for row in binding['selected_geometry_binding']}
check(body['target']['object_id']==ids[body['target']['name']], 'response_target_host_ID_matches_captured_name')
for row in body['candidates']:
    check(row['object_id']==ids[row['name']], 'response_candidate_host_ID_matches_captured_name.'+row['name'])
check(bundle['source']['kind']=='offline_frozen_inputs', 'no_live_capture_source_claim')

# Check correction changed topology only, not coordinates or relation facts.
old_bundle = read(BATCH/'input/BUNDLE.json')
def without_topology(value):
    result = copy.deepcopy(value)
    for row in result['objects']:
        row.pop('faces',None); row.pop('face_kind',None)
    return result
check(without_topology(old_bundle)==without_topology(bundle), 'input02_changes_only_face_topology_metadata')
topology_changes = [new['name'] for previous,new in zip(old_bundle['objects'],bundle['objects'])
                    if previous.get('faces')!=new.get('faces') or previous.get('face_kind')!=new.get('face_kind')]
check(set(topology_changes)==set(ids), 'topology_correction_exactly_four_captured_objects')

# Source ledger vs actual public tool payloads, independently of ledger generator.
ledger = read(BATCH/'ledger/DEMAND_LEDGER.json')
matrix = read(BATCH/'COVERAGE_MATRIX.json')
check(sha((BATCH/'ledger/DEMAND_LEDGER.json').read_bytes())==matrix['ledger_sha256'], 'coverage_matrix_binds_ledger')
check({row['anonymous_id'] for row in ledger['observations']}==
      {row['anonymous_id'] for row in matrix['observations']}, 'matrix_maps_same_six_observations')
ledger_summary = []
for row in ledger['observations']:
    name = row['anonymous_id']; source = row['tool_evidence_source']
    original_blob = Path(source['path']).read_bytes()
    check(sha(original_blob)==source['sha256'], 'ledger_public_source_hash.'+name)
    evidence = json.loads(original_blob)
    attempts = evidence['owner_attempts']
    check([a['request']['params']['name'] for a in attempts]==
          ['execute_blender_code','human_eye_spatial_relations','execute_blender_code'], 'actual_three_call_route.'+name)
    code = attempts[2]['request']['params']['arguments']['code']
    decoded = json.loads(attempts[2]['responses'][0]['value']['result']['content'][0]['text'])
    stdout = decoded['result']['result']
    check(sha(code.encode('utf8'))==row['last_code_utf8_sha256'], 'last_code_hash.'+name)
    check(sha(stdout.encode('utf8'))==row['last_stdout_utf8_sha256'], 'last_stdout_hash.'+name)
    extract_blob = (BATCH/row['extraction']).read_bytes()
    check(sha(extract_blob)==row['extraction_sha256'], 'extraction_hash.'+name)
    extraction = json.loads(extract_blob)
    check(extraction['last_native_read']['code']==code and extraction['last_native_read']['stdout']==stdout,
          'extraction_matches_actual_code_and_stdout.'+name)
    attributes = {node.attr for node in ast.walk(ast.parse(code)) if isinstance(node,ast.Attribute)}
    check(not {'polygons','loop_triangles'} & attributes and row['topology_returned'] is False,
          'no_topology_read.'+name)
    geometry_names = [item['object_name'] for item in extraction['parsed_last_geometry']]
    check(geometry_names==row['geometry_objects'], 'actual_selected_geometry_names.'+name)
    relation = json.loads(attempts[1]['responses'][0]['value']['result']['content'][0]['text'])
    crossing = 'local_evidence' in relation['candidates'][0]['closed_solid_relation']
    check(crossing==row['local_crossing_evidence_already_present'], 'historical_local_evidence_presence.'+name)
    ledger_summary.append({'id':name,'geometry_field':row['geometry_field'],'geometry_names':geometry_names,
                           'geometry_not_in_primary':[n for n in geometry_names if n not in {named[o['object_id']] for o in primary['objects']}],
                           'local_evidence_already_present':crossing,'stage1_decimal_rounding':row['stage1_decimal_rounding']})

# AABB-derived values exist, but require downstream arithmetic: the prototype
# itself does not return these target conditions or identify the target.
rows = {row['name']:row for row in directory['objects']}
centers = {name:[(Fraction.from_float(a)+Fraction.from_float(b))/2 for a,b in zip(row['aabb']['min'],row['aabb']['max'])]
           for name,row in rows.items()}
rail = (centers['N12'][2]+centers['N24'][2])/2
beam = Fraction.from_float(rows['N10']['aabb']['max'][1])
pipe = [(centers['N04'][axis]+centers['N19'][axis])/2 for axis in range(2)]
condition_rows = []
for name in ('N15','N16','N18','N25'):
    c=centers[name]; radius_sq=sum((c[k]-pipe[k])**2 for k in range(2))
    truth=[c[2]<rail,c[1]>beam,radius_sq<=Fraction(7,10)**2]
    condition_rows.append({'name':name,'center':[float(x) for x in c],
                           'radius_squared':float(radius_sq),'three_conditions':truth})
check([row['name'] for row in condition_rows if all(row['three_conditions'])]==['N16'],
      'explicit_named_reference_arithmetic_recovers_current_target')
check(all('center' not in row for row in directory['objects']), 'final_removes_center_from_all_directory_rows')
draft_directory = draft.directory(bundle)
for row in draft_directory['objects']: row.pop('center',None)
check(draft_directory==directory and draft.selected_observation(bundle,primary)==selected,
      'draft_final_only_directory_center_removal')

# Serialization deltas only; do not rerun timing or memory benchmarks.
serialize=lambda x: json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
without_faces=copy.deepcopy(primary)
for row in without_faces['objects']: row['fields'].remove('faces')
size = {'directory':len(serialize(directory)),'selected_primary':len(serialize(selected)),
        'selected_primary_without_faces':len(serialize(final.selected_observation(bundle,without_faces))),
        'draft_directory':len(serialize(draft.directory(bundle)))}
size['center_removed_bytes']=size['draft_directory']-size['directory']
size['two_objects_topology_added_bytes']=size['selected_primary']-size['selected_primary_without_faces']
count_prefix=collections.Counter(row['check'].split('.')[0] for row in replay['checks'])
result={'declared_fixed_commit':PIN,'passed':all(row['passed'] for row in checks),
        'independent_check_count':len(checks),'checks':checks,
        'frozen_replay':{'passed':replay['passed'],'assertions':replay['check_count'],
                         'unique_labels':len({row['check'] for row in replay['checks']}),
                         'group_counts':dict(count_prefix),
                         'single_rotation_vertex_assertions':sum(row['check'].startswith('rotation.exact_coordinate.') for row in replay['checks'])},
        'source_snapshot_type':bundle['source'],'topology_correction_objects':topology_changes,
        'primary_geometry':[named[row['object_id']] for row in primary['objects']],
        'primary_host_union':[named[key] for key in sorted(primary_union)],
        'optional_host_union_count':len(optional_union),'ledger_summary':ledger_summary,
        'caller_arithmetic_with_known_reference_ids':condition_rows,'output_sizes_bytes':size,
        'interpretation':'coverage only for an explicit supplied request; no autonomous discovery/consumer/host currentness proof',
        'product_calls':0,'Blender_sessions':0,'new_model_consumers':0,'performance_measurements':0}
save(HERE/'INDEPENDENT_CHECKS.json',result)
print(json.dumps({'independent_passed':result['passed'],'checks':len(checks),'sizes':size}))
raise SystemExit(0 if result['passed'] else 1)
