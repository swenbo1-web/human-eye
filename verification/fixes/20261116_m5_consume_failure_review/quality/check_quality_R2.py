"""Independent five-answer, source, image and blocked-delivery reconstruction."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
RUN = Path('D:/he_m5_task_consume_001')
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = AUTHOR / 'verification/m5_task_consumption_001'
FIXED = 'baf8799d9e1cb411d39da58c28171b00ac76f12f'
SLOTS = ['A1', 'B1', 'B2', 'A2', 'A3']
checks = 0

def read(path):
    return json.loads(Path(path).read_bytes())

def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line.strip()]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(condition, label):
    global checks
    if not condition:
        raise AssertionError(label)
    checks += 1

def payload(response):
    return json.loads(response['result']['content'][0]['text'])

def point_on_triangle(point, mesh):
    p = [F(x) for x in point]
    for face in mesh['triangles']:
        a,b,c = [[F(x) for x in mesh['vertices'][i]] for i in face]
        u,v,w = ([b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)], [p[i]-a[i] for i in range(3)])
        n = [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(n[i]*w[i] for i in range(3)):
            continue
        dot = lambda x,y: sum(x[i]*y[i] for i in range(3))
        uu,uv,vv,wu,wv = dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
        det = uu*vv-uv*uv
        if det:
            alpha,beta = (vv*wu-uv*wv)/det,(uu*wv-uv*wu)/det
            if alpha >= 0 and beta >= 0 and alpha+beta <= 1:
                return True
    return False

frozen = read('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')
originals = {o['name']: {'vertices': [[float(F(v)) for v in p] for p in o['world_vertices_m']],
                         'triangles': o['triangles']} for o in frozen['objects']}
a = F(originals['M4_Near']['vertices'][0][0])
distance = 1-a
check(distance == F(2138893713,2147483648), 'independent whole-object x lower bound')
check(all(F(p[0]) >= 1 for p in originals['M4_Far_00']['vertices']), 'all target vertices above lower plane')
check(all(F(p[0]) == a for p in originals['M4_Near']['vertices']), 'all reference vertices on upper plane')
summary = []
blocked = {}
custom_hashes = []

for slot in SLOTS:
    base = RUN/'formal'/slot
    final = read(base/'consumer/PUBLIC_FINAL.txt')
    calls = rows(base/'PUBLIC_REQUESTS.jsonl')
    entries = rows(base/'product_full/INDEX.jsonl')
    tools = read(base/'owner/TOOLS.json')['tools']
    observed = read(entries[0]['path'])
    pub = payload(calls[0]['response'])
    check(pub['schema']=='active-observation-brief-v5', slot+' public observation')
    check(pub['binding']['binding_sha256']==observed['binding']['binding_sha256'], slot+' producer/public binding')
    raw_sources = list((base/'raw_sources').glob('*.json'))
    if raw_sources:
        raw = read(raw_sources[0])
        for mesh in raw['objects']:
            check(mesh['vertices']==originals[mesh['name']]['vertices'] and mesh['triangles']==originals[mesh['name']]['triangles'], slot+' raw source '+mesh['name'])
    else:
        resources = {}
        capture = None
        for path in sorted((base/'native/WIRE').glob('*/RESPONSE.bin')):
            text = read(path).get('result',{}).get('result')
            if not isinstance(text,str) or not text.startswith('HUMAN_EYE_BLENDER_MCP:'):
                continue
            packet = json.loads(text.split(':',1)[1])['result']
            if packet.get('schema')!='human-eye-scene-delta-v1':
                continue
            for resource in packet['resources']:
                resources[resource['id']] = resource
            capture = copy.deepcopy(packet['capture'])
            for mesh in capture['meshes']:
                ref = mesh['_scene_resource']
                resource = resources[ref['id']]
                matrix,scale = ref['matrix'],ref['scale']
                mesh['vertices'] = [[sum(matrix[k][j]*p[j] for j in range(3))*scale+matrix[k][3]*scale for k in range(3)] for p in resource['vertices_local']]
                mesh['triangles'] = resource['faces']
                check(mesh['vertices']==originals[mesh['name']]['vertices'] and mesh['triangles']==originals[mesh['name']]['triangles'], slot+' wire source '+mesh['name'])
        check(capture is not None, slot+' actual source reconstructed')
    check(final['object_name']=='M4_Far_00' and final['unit']=='m' and final['coordinate_frame']=='world' and final['finite_view_pool_only'], slot+' answer source scope')
    check(len(final['regions'])==2, slot+' region denominator')
    mapped = {tuple(tuple(v) for v in r['identity']['source_triangle_index_ranges']):r for r in final['regions']}
    check(set(mapped)=={((0,511),),((512,513),)},slot+' complete source sets')
    for key,center,bounds,normal,complete in [(((0,511),),[1,.5,.5],[[1,0,0],[1,1,1]],[-1,0,0],False),(((512,513),),[1.5,.5,2],[[1,0,2],[2,1,2]],[0,0,1],True)]:
        region = mapped[key]
        check(region['center_world_m']==center and region['bounds_world_m']==bounds and region['unit_normal_world']==normal,slot+' region geometry')
        check(region['geometry_complete_in_pool']==complete and region['complete_readable']==complete,slot+' complete state')
        check(bool(region['source_references']),slot+' original source references')
        if not complete:
            check(region['complete_witness'] is None and 'LEFT' in region['notes'] and '正面积' in region['notes'],slot+' explicit occlusion reason in original notes')
    measured = final['measurement']
    check(measured['object_a_name']=='M4_Far_00' and measured['object_b_name']=='M4_Near' and measured['measurement_scope']=='whole_objects',slot+' quantitative whole objects')
    check(F(measured['distance_m'])==distance,slot+' exact published distance')
    witness=measured['nearest_witness']
    check(point_on_triangle(witness['a'],originals['M4_Far_00']) and point_on_triangle(witness['b'],originals['M4_Near']),slot+' exact source-triangle witnesses')
    check(sum((F(witness['b'][k])-F(witness['a'][k]))**2 for k in range(3))==distance**2,slot+' witness reaches independent global bound')
    check(witness['direction_a_to_b']==[-1,0,0],slot+' direction')
    check(final['observation_measurement_correspondence']['same_current_source'] and measured['source_references'],slot+' source association')
    for source in measured['object_source_bindings']:
        name=source['object_name']; check(source['source_triangle_count']==len(originals[name]['triangles']),slot+' whole face count '+name)
        check(source['source_triangle_index_ranges']==[[0,len(originals[name]['triangles'])-1]],slot+' whole source face ranges '+name)
        if 'ordered_geometry_sha256' in source and slot in ('A2','A3'):
            check('vertices' in str(final['source_references']) and 'triangles' in str(final['source_references']) and 'separators' in str(final['source_references']),slot+' explicit hash definition')
            d=originals[name]; actual=hashlib.sha256(json.dumps({'vertices':d['vertices'],'triangles':d['triangles']},separators=(',',':')).encode()).hexdigest()
            check(source['ordered_geometry_sha256']==actual,slot+' independently rebuilt declared hash '+name)
            custom_hashes.append({'slot':slot,'object':name,'sha256':actual})
    frame=observed['frames'][0]
    check(sha(frame['arrays_path'])==frame['arrays_sha256'] and sha(frame['image_path'])==frame['image_sha256'],slot+' actual frame original hashes')
    with np.load(frame['arrays_path'],allow_pickle=False) as z:
        arrays={k:z[k] for k in z.files}
    check(np.array_equal(np.asarray(Image.open(frame['image_path'])),arrays['color']),slot+' actual PNG/RGB')
    ids=arrays['patch_roi_ids'].tolist()
    for region in final['regions']:
        mask=arrays['patch_owners']==ids.index(region['identity']['roi_id'])
        count=int(np.count_nonzero(mask)); contrast=np.zeros(mask.shape,dtype=bool)
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            ys,ye=max(0,-dy),min(512,512-dy);xs,xe=max(0,-dx),min(512,512-dx)
            src=(slice(ys,ye),slice(xs,xe));nbr=(slice(ys+dy,ye+dy),slice(xs+dx,xe+dx))
            delta=arrays['color'][src].astype(np.int32)-arrays['color'][nbr].astype(np.int32)
            contrast[src] |= mask[src] & ~mask[nbr] & (np.sum(delta*delta,axis=2)>=24**2)
        boundary=int(np.count_nonzero(contrast))
        if region['complete_witness']:
            w=region['complete_witness'];check(w['frame_ref']==frame['image_ref'] and w['view_name']=='SCENE',slot+' current actual witness reference')
            check(w['surface_pixels']==count==17131 and w['boundary_pixels']==boundary==538,slot+' actual independent readable pixels')
    image_blocks=[v for v in calls[0]['response']['result']['content'] if v['type']=='image']
    check(len(image_blocks)==1 and base64.b64decode(image_blocks[0]['data'],validate=True)==Path(frame['image_path']).read_bytes(),slot+' actual public image bytes')
    mapping=[]; blocked_count=0
    for call in calls:
        check(sha(call['actual_RX_path'])==call['actual_RX_sha256'],slot+' raw public MCP receipt')
        public=payload(call['response'])
        matches=[entry for entry in entries if call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=entry['saved_ns']<=call['closed_ns']]
        if call['response']['result']['isError']:
            check(not matches,slot+' pre-service rejected request creates no archive')
            mapping.append(None)
            continue
        check(len(matches)==1,slot+' unique actual archive in call window')
        entry=matches[0];check(sha(entry['path'])==entry['sha256'],slot+' actual archive hash')
        full=read(entry['path'])
        check(full['result_kind']==public['result_kind'],slot+' actual archive kind')
        full_binding, public_binding = full.get('binding',{}), public.get('binding',{})
        if public['result_kind']=='active_observation':
            check(all(full_binding.get(k)==v for k,v in public_binding.items() if k not in ('capture_state','observation_target')),slot+' archive public scalar binding')
            check(all(full_binding['capture_state'].get(k)==v for k,v in public_binding['capture_state'].items()),slot+' archive public generation')
            target_full,target_public=full_binding['observation_target'],public_binding['observation_target']
            check(all(target_full.get(k)==v for k,v in target_public.items() if k!='full_scene_identity_sha256'),slot+' archive target projection')
            identity_sha=hashlib.sha256(json.dumps(target_full['full_scene_identity'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
            check(identity_sha==target_public['full_scene_identity_sha256'],slot+' projected complete scene identity digest')
        else:
            check(full_binding==public_binding,slot+' actual archive full source binding')
        mapping.append(entry['index'])
        tool=next(t for t in tools if call['internal_public_call_index'] in t['internal_public_call_indices'])
        outer=read(base/'owner'/('tool_'+str(tool['attempt']).zfill(2))/'RESPONSE.json')
        if outer['result']['isError']:
            check('same_producer_archive_receipt_missing' in str(outer),slot+' bridge blocks a successful backend reply')
            check(entry['index']!=call['producer_archive_index'],slot+' wrong expected producer counter')
            blocked_count+=1
    blocked[slot]=blocked_count
    if slot.startswith('A'):
        first=tools[0]['internal_public_call_indices']
        check(len(first)==2 and calls[first[0]-1]['request']['params']['arguments']['query']['mode']=='active_observation' and calls[first[1]-1]['request']['params']['arguments']['query']['mode']=='task',slot+' actual batch attempt')
    joint = 'task_result' in pub
    check(joint==(slot=='B1'),slot+' actual public joint delivery')
    if joint:
        actual=pub['task_result']['facts']['surface_proximity']['value']
        check(measured['distance_m']==actual['distance_m'] and witness==actual['nearest_witness'],slot+' jointly delivered fact used in final answer')
    else:
        check('原始' in measured['notes'] and ('失败' in measured['notes'] or '未取得' in str(final['limitations'])),slot+' final explicitly uses raw fallback rather than backend-only fact')
    summary.append({'slot':slot,'actual_archive_indices':mapping,'blocked_valid_replies':blocked_count,'joint_public_fact_adoption':joint,'final_correct':True})

check(blocked=={'A1':2,'B1':0,'B2':2,'A2':3,'A3':2},'nine blocked valid replies')
check(sum(blocked.values())==9,'all blocked denominator')
check(not (RUN/'formal/B3/consumer/PUBLIC_FINAL.txt').exists() and not (RUN/'formal/B3/SLOT_RESULT.json').exists(),'B3 no fabricated final or slot result')
check(len(custom_hashes)==4,'four explicitly declared hash preimages')
for relative in ['SCORING_PLAN.md','inputs/ANSWER_SCHEMA.json']:
    raw=subprocess.check_output(['git','show','99c5ba3ebcd62cbb94174a06e0a419912257bc91:verification/m5_task_consumption_001/'+relative],cwd=AUTHOR)
    check(raw==(NS/relative).read_bytes(),'preformal scoring byte identity '+relative)
scoring=(NS/'SCORING_PLAN.md').read_text(encoding='utf8')
check('notes' in scoring and '等价' in scoring and '可选' in scoring and 'hash' in scoring,'preformal semantic/hash source contract')
result={'status':'passed_checked_scope','checks':checks,'fixed_git':FIXED,'actual_answers':5,'planned_slots':6,'blocked_valid_replies':blocked,'slots':summary,'declared_hashes':custom_hashes,'new_Blender':0,'new_raster':0,'new_models':0,'scope':'Five complete raw finals independently read; raw geometry/lower-bound/witness/pixels/current public delivery and archive windows reconstructed. No counterfactual consumer answers.'}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'status':result['status'],'checks':checks,'blocked':blocked}))
