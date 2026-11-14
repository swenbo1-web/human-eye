"""Read-only response design audit. No product imports or observation execution."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT / 'verification/m4_explicit_observation_consumption_001'
SLOT = Path('D:/he_explicit_001/formal/P1')
OUT = Path(__file__).parent
inputs = {}
checks = []

def raw(p):
    p = Path(p)
    data = p.read_bytes()
    inputs[str(p)] = hashlib.sha256(data).hexdigest()
    return data

def js(p):
    return json.loads(raw(p))

def ck(name, value):
    checks.append({'name': name, 'passed': bool(value)})

response = js(SLOT / 'o/tool_01/RESPONSE.json')
text = response['result']['content'][0]['text']
brief = json.loads(text)
full = js(SLOT / 'o/product_call_01/SERVICE_RESULT.json')
prompt = raw(BATCH / 'inputs/PROMPT.txt').decode()
sources = js(BATCH / 'inputs/SOURCES.json')
reference_path = Path('D:/he_loc_001/formal/P3/o/scratch/scene_inspection.json')
reference = js(reference_path)
old_audit = js('D:/hefe/verification/fixes/20261114_m4_localization_consumption_001_review/quality/RESULTS.json')
ck('reuse_previous_independently_verified_geometry_only', old_audit['passed'] and old_audit['checks'] == 9150)
ck('reference_matches_prior_audit_bytes', inputs[str(reference_path)] == old_audit['inputs'][str(reference_path)])
for k in ('scene', 'cameras'):
    p = Path(sources[k]['path'])
    h = hashlib.sha256(raw(p)).hexdigest()
    ck('same_frozen_reference_input_' + k, h == sources[k]['sha256'] == old_audit['inputs'][str(p)])

def quad(row):
    c, u, v = [list(map(F, x)) for x in row[5:8]]
    return frozenset(tuple(c[i] + su * u[i] + sv * v[i] for i in range(3))
                     for su, sv in ((-1,-1), (1,-1), (1,1), (-1,1)))

by_quad = {frozenset(tuple(map(F, p)) for p in r['world_corners_rational']): r
           for r in reference['surfaces']}
regions = brief['regions']['rows']
images = brief['images']['rows']
mapped = {i: by_quad[quad(r)] for i,r in enumerate(regions)}
ck('all_138_regions_mapped', len(mapped) == len(by_quad) == 138)
counterexamples = []
for p in brief['pixels']['rows']:
    g = mapped[p[1]]['evidence_by_view'][images[p[0]][0]]
    if p[5] and not g['complete']:
        counterexamples.append({'region': p[1], 'view': images[p[0]][0], 'pixels': p})
ck('414_rows_current_response', len(brief['pixels']['rows']) == 414)
ck('all_161_pixel_readable_are_complete_in_this_scene',
   sum(p[5] for p in brief['pixels']['rows']) == 161 and not counterexamples)

remaining = set(brief['coverage']['unresolved_region_indices'])
unavailable = set(brief['coverage']['candidate_pool_uncovered_region_indices'])
ck('remaining_set_equals_pool_geometric_unavailable', remaining == unavailable and len(remaining) == 23)
no_front = [i for i in remaining if not any(v['front_facing'] for v in mapped[i]['evidence_by_view'].values())]
occluded = [i for i in remaining if i not in no_front and all(
    v['front_facing'] and not v['complete'] and v['occluders']
    for v in mapped[i]['evidence_by_view'].values())]
ck('remaining_reason_partition', len(no_front) == 22 and len(occluded) == 1)
ck('all_public_remaining_reason_is_generic', all(regions[i][3] == 'finite_camera_pool_uncovered' for i in remaining))
ck('no_public_geometry_classification', 'classifications' not in brief and all(
    key not in brief['pixels']['columns'] for key in ('complete', 'geometrically_complete', 'geometry_status')))
ck('prompt_accepts_actual_tool_facts_as_complete_coverage', 'complete coverage set may be carried by actual tool facts' in prompt)

missed = next(i for i,r in mapped.items() if r['source_triangle_indices'] == list(range(1133,1645)))
missed_pixel = next(p for p in brief['pixels']['rows'] if p[1] == missed and images[p[0]][0] == 'BACK')
ck('misreported_face_already_covered', missed in brief['coverage']['covered_region_indices'])
ck('misreported_face_actual_BACK_witness', missed_pixel[3:6] == [468,84,True] and mapped[missed]['evidence_by_view']['BACK']['complete'])
step_witness = next(s['view_name'] for s in full['steps'] if regions[missed][0] in s['update']['new_roi_ids'])
ck('first_cover_witness_BACK', step_witness == 'BACK')

reqs = []
for number in range(1,14):
    req = js(SLOT / f'o/tool_{number:02d}/REQUEST.json')['params']
    reqs.append({'number': number, 'tool': req['name'], 'arguments': req['arguments']})
namespace_reply = js(SLOT / 'o/tool_02/RESPONSE.json')['result']['content'][0]['text']
ck('namespace_query_was_real', 'globals()' in reqs[1]['arguments']['code'])
ck('no_observation_object_advertised', 'last_observation' not in namespace_reply)
ck('all_native_batch_requested_after_product', "['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']" in reqs[3]['arguments']['code'])
events = [json.loads(line) for line in raw(SLOT / 'c/stdout.raw.bin').decode().splitlines()]
messages = [e['item']['text'] for e in events if e.get('item',{}).get('type') == 'agent_message']
ck('public_gap_interpretation_present', any('first pass leaves gaps' in m for m in messages))

source_paths = [ROOT / 'human_eye_plugin' / n for n in (
    'active_observation.py', 'active_observation_images.py', 'active_observation_host.py', 'live_spatial_mcp.py')]
source_paths += [ROOT / 'verification/m4_region_localization_consumption_001' / n for n in ('bridge.py', 'native_tools.py')]
for p in source_paths:
    raw(p)
ck('brief_v3_source_schema', brief['schema'] == 'active-observation-brief-v3')
result = {
    'passed': all(c['passed'] for c in checks), 'checks': len(checks),
    'failures': [c for c in checks if not c['passed']],
    'public_text_bytes': len(text.encode()),
    'regions_bytes': len(json.dumps(brief['regions'], separators=(',',':')).encode()),
    'pixels_bytes': len(json.dumps(brief['pixels'], separators=(',',':')).encode()),
    'pixel_readable_not_geometry_complete_examples_in_this_scene': counterexamples,
    'geometric_remaining_count': len(remaining - unavailable),
    'unobserved_no_front_count': len(no_front), 'unobserved_occluded_count': len(occluded),
    'misreported_face_product_region_index': missed,
    'misreported_face_world': regions[missed][5:],
    'misreported_face_BACK_pixel_row': missed_pixel,
    'misreported_face_first_cover_view': step_witness,
    'public_progress': messages,
    'evidence_limit': 'Current response and source reviewed directly; same-source per-view geometric classifications reused from the preceding independently certified six-slot audit. No new raster or product calculation.',
    'new_product_model_Blender_raster_calls': 0,
    'inputs': inputs,
}
(OUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(OUT / 'CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k != 'inputs'}, ensure_ascii=False))
