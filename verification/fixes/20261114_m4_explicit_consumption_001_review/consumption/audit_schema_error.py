"""Independent offline current-delivery and consumption witness audit."""
import base64
import hashlib
import io
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
import numpy as np
from PIL import Image

RUN = Path('D:/he_explicit_001/formal/P1')
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = AUTHOR / 'verification/m4_explicit_observation_consumption_001'
OUT = Path('D:/hefe/verification/fixes/20261114_m4_explicit_consumption_001_review/consumption')
inputs = {}
checks = []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    return data

def read(path):
    return json.loads(raw(path))

def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})

def req(i):
    return read(RUN / f'c/owner_turn/tool_{i:02}/REQUEST.json')

def resp(i):
    return read(RUN / f'c/owner_turn/tool_{i:02}/RESPONSE.json')

def text(i):
    return json.loads(resp(i)['result']['content'][0]['text'])

events = [json.loads(line) for line in raw(RUN/'c/stdout.raw.bin').splitlines() if line]
calls = [e['item'] for e in events if e['type'] == 'item.completed' and e.get('item',{}).get('type') == 'mcp_tool_call']
check('13_completed_call_events', len(calls) == 13)
check('active_then_twelve_execute_python', [x['tool'] for x in calls] == ['active_observation'] + ['execute_python']*12)
for i, item in enumerate(calls, 1):
    request = req(i)['params']
    check(f'call_{i}_request_bound', item['arguments'] == request['arguments'] and item['tool'] == request['name'])
    check(f'call_{i}_result_bound', item['result'] == resp(i)['result'])

response = resp(1)
brief = text(1)
service = read(RUN/'o/product_call_01/SERVICE_RESULT.json')
regions = brief['regions']['rows']
pixels = brief['pixels']['rows']
images = brief['images']['rows']
region_columns = brief['regions']['columns']
region_dicts = [dict(zip(region_columns, row)) for row in regions]
check('138_regions_414_pixels_3_frames', (len(regions),len(pixels),len(images)) == (138,414,3))
check('115_covered_23_unknown', Counter(r['status'] for r in region_dicts) == {'covered':115,'unknown':23})
check('all_three_current_images', [row[0] for row in images] == ['SCENE','BACK','LEFT'])
check('unsupported_48_preserved', brief['scope']['patch_support']['unsupported_components']['rows'] == [[0,0,1,'insufficient_faces','unknown',[[48,48]]]])
for i, (compact, fact) in enumerate(zip(region_dicts, service['facts']['regions'])):
    check(f'region_{i}_producer_fields', all(compact[k] == fact[k] for k in compact if k != 'triangle_count'))
for pi, pixel in enumerate(pixels):
    image_index, region_index, *values = pixel
    roi = regions[region_index][0]
    rows = service['facts']['observations'][image_index]['pixel_rows']
    fact = next(x for x in rows if x['roi_id'] == roi)
    check(f'pixel_{pi}_producer_fields', values == [fact[k] for k in brief['pixels']['columns'][2:]])

buffers = {}
pixel_witnesses = {}
image_blocks = [c for c in response['result']['content'] if c['type'] == 'image']
for j, frame in enumerate(service['frames']):
    data = raw(frame['arrays_path'])
    check(f'{j}_npz_sha', hashlib.sha256(data).hexdigest() == frame['arrays_sha256'])
    a = dict(np.load(io.BytesIO(data), allow_pickle=False))
    buffers[frame['view_name']] = a
    png = raw(frame['image_path'])
    check(f'{j}_png_current_delivery', base64.b64decode(image_blocks[j]['data']) == png)
    check(f'{j}_png_hash', hashlib.sha256(png).hexdigest() == frame['image_sha256'])
    rgb = a['color']
    check(f'{j}_png_buffer_equal', np.array_equal(np.array(Image.open(io.BytesIO(png)).convert('RGB')),rgb))
    check(f'{j}_roi_order', list(a['patch_roi_ids']) == [r[0] for r in regions])
    labels = a['patch_owners']
    marked = np.zeros(labels.shape, dtype=bool)
    rgb_int = rgb.astype(np.int32)
    for one,two in [((slice(None,-1),slice(None)),(slice(1,None),slice(None))),
                    ((slice(None),slice(None,-1)),(slice(None),slice(1,None)))]:
        different = (labels[one] != labels[two]) & (np.sum((rgb_int[one]-rgb_int[two])**2,axis=2)>=576)
        marked[one] |= different
        marked[two] |= different
    counts = np.bincount(labels[labels>=0],minlength=len(regions))
    boundaries = np.bincount(labels[(labels>=0)&marked],minlength=len(regions))
    for row in (p for p in pixels if p[0] == j):
        ri = row[1]
        check(f'{j}_{ri}_independent_pixel_counts', row[3:5] == [int(counts[ri]),int(boundaries[ri])])
        if row[7] is not None:
            x,y = row[7]
            check(f'{j}_{ri}_owned_anchor', int(labels[y,x]) == ri)
    pixel_witnesses[frame['view_name']] = {'counts': counts.tolist(), 'boundaries':boundaries.tolist()}

sources = read(BATCH/'inputs/SOURCES.json')
scene = read(sources['scene']['path'])
camera = read(sources['cameras']['path'])
obj = scene['objects'][0]
verts = [[Fraction(x) for x in v] for v in obj['vertices']]
tris = obj['triangles']
target_ids = list(range(1133,1645))
mapped = buffers['BACK']['face_patch_ids'][target_ids]
check('missed_surface_is_one_patch', len(set(map(int,mapped))) == 1)
ri = int(mapped[0])
check('missed_surface_index7', ri == 7)
row = region_dicts[ri]
used_vertices = {v for t in target_ids for v in tris[t]}
mins = [min(verts[v][k] for v in used_vertices) for k in range(3)]
maxs = [max(verts[v][k] for v in used_vertices) for k in range(3)]
center = [float((lo+hi)/2) for lo,hi in zip(mins,maxs)]
check('missed_surface_source_center', center == row['center_world_m'] == [0.3515625,0,0])
check('missed_surface_source_extent', [float(hi-lo) for lo,hi in zip(mins,maxs)] == [0.05859375,0.05859375,0])
check('missed_surface_was_covered', row['status'] == 'covered')
missed_back = next(p for p in pixels if p[:2] == [1,ri])
check('missed_back_468_84', missed_back[2:6] == [True,468,84,True])
check('missed_back_actual_pixels', [pixel_witnesses['BACK']['counts'][ri],pixel_witnesses['BACK']['boundaries'][ri]] == [468,84])

position = {}
for label,center in [('click',[.15625,-.15625,.11865234375]),('origin',[0,0,0]),('bottom',[.15625,-.15625,.11572265625])]:
    ix = next(i for i,r in enumerate(region_dicts) if r['center_world_m'] == center)
    rows = [p for p in pixels if p[1] == ix]
    position[label] = {'region_index':ix,'region':region_dicts[ix],'pixels':rows}
check('click_current_owned_region', int(buffers['SCENE']['patch_owners'][247,109]) == position['click']['region_index'])
check('click_current_anchor', position['click']['pixels'][0][7] == [109,247])
check('click_center_normal', position['click']['region']['front_direction_world'] == [0,0,1])
check('click_extent', position['click']['region']['half_edge_u_world_m'] == [.03515625,0,0] and position['click']['region']['half_edge_v_world_m'] == [0,.03515625,0])
check('origin_scene_front_zero', position['origin']['pixels'][0][2:6] == [True,0,0,False])
check('origin_LEFT_readable', position['origin']['pixels'][2][2:6] == [True,792,110,True])
check('bottom_all_actual_back', all(not p[2] and p[3] == 0 for p in position['bottom']['pixels']))
normal = position['bottom']['region']['front_direction_world']
camera_dot = {v['name']:sum(a*b for a,b in zip(normal,v['direction_rational'])) for v in camera['views']}
check('bottom_all_registered_back_from_camera_data', all(v<0 for v in camera_dot.values()))
check('camera_directions_not_in_brief', not any(k in brief['binding'] for k in ['camera_specification','camera_policy']))

table_stdout = text(12)['stdout']
table = json.loads(table_stdout)
check('tool12_real_table_114_24', Counter(r[2] for r in table['rows']) == {'observed':114,'remaining':24})
badrow = next(r for r in table['rows'] if r[1] == [[1133,1644]])
check('tool12_false_remaining_row56', badrow == [56,[[1133,1644]],'remaining','positive_area_occlusion_all_six'])
check('table_only_3_product_view_refs', list(table['view_references']) == ['SCENE','BACK','LEFT'])
check('tool4_full_native_rediscovery', 'for ti,t in enumerate(T)' in req(4)['params']['arguments']['code'])
check('tool4_all_six_render_request', "render_views(['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']" in req(4)['params']['arguments']['code'])
check('tool4_raster_cap_error', 'raster' in str(text(4)['error']).lower())
check('tool7_global_geom_and_pixels', "for cam in cameras['views']" in req(7)['params']['arguments']['code'] and 'for name,b in buffers.items()' in req(7)['params']['arguments']['code'])
check('tool9_actual_png_reads', 'Image.open(image_files[ref])' in req(9)['params']['arguments']['code'])
check('tool10_back_subset_only', "back_only=[si for si in remaining" in req(10)['params']['arguments']['code'])
check('tool10_115_preexisting', 'all supported verified readable 115' in text(10)['stdout'])
check('tool11_KeyError', text(11)['error'] == {'type':'KeyError','message':"(5, 'BACK')"})
check('tool12_defaults_missing_to_zero', "pixel_facts.get((si,name),{}).get('pixels',0)" in req(12)['params']['arguments']['code'])
last = read(RUN/'c/owner_turn/tool_13/RECEIPT.json')
check('tool13_prebusiness_refusal', last['error']['message'] == 'route_twelve_tool_call_limit')
check('tool13_correction_attempt_not_result', 'replace surface 56' in req(13)['params']['arguments']['code'] and resp(13)['result']['isError'] is True)
check('no_formal_final_file', not (RUN/'c/PUBLIC_FINAL.txt').exists())
check('no_turn_terminal', not any(e['type'] in ['turn.completed','turn.failed'] for e in events))
messages = [e['item']['text'] for e in events if e.get('item',{}).get('type')=='agent_message']
check('public_gaps_then_115_claim', any('first pass leaves gaps' in m for m in messages) and any('All 115' in m for m in messages))
check('product_no_python_variable_exposed', "available ['geometry', 'cameras', 'np', 'Fraction', 'buffers', 'scratch', 'render_views', 'read_images', 'attach_images', 'image_files']" in text(2)['stdout'])
check('product_no_public_native_buffer', text(3)['stdout'].startswith('buffers []'))

results = {'passed':all(x['passed'] for x in checks), 'checks':len(checks),
           'failures':[x for x in checks if not x['passed']],
           'product_delivery':{'regions':len(regions),'pixels':len(pixels),'current_frames':len(images)},
           'position_witnesses':position,'bottom_camera_dots_from_raw_metadata':camera_dot,
           'consumption_failure':{'tool12_wrong_row':badrow,'product_region':row,'product_BACK_pixel_row':missed_back,
                                  'tool13_admitted':False,'formal_final_present':False},
           'public_progress_messages':messages,
           'new_product_model_Blender_raster_benchmark_calls':0,
           'limits':['Did not run author scorer or product code.',
                     'Did not independently regenerate raster; verified existing current buffers and delivery.',
                     'Observed state and commands do not establish internal model motive.',
                     'The brief lacks full camera directions and individual uncovered reasons; small metadata lookup may still be justified.'],
           'inputs':inputs}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:results[k] for k in ['passed','checks','failures']},ensure_ascii=False))
