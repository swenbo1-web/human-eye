"""Independent saved-data check. No candidate/scorer imports or raster executions."""
from pathlib import Path
from fractions import Fraction as F
import hashlib, io, json, math, re
import numpy as np
from PIL import Image

BASE = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_complete_witness_consumption_001')
OUT = Path(__file__).resolve().parent
checks, inputs, details = [], {}, {}

def read(path):
    path = Path(path)
    raw = path.read_bytes()
    inputs[str(path)] = {'path':str(path), 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
    return raw

def js(path): return json.loads(read(path))
def check(name, value): checks.append({'name': name, 'pass': bool(value)})
archive = js(BASE/'RUNTIME_ARCHIVE.json')['files']
by_rel = {r['relative_path']:r for r in archive}
by_original = {r['original_path'].replace('\\','/'):r for r in archive}

def archived(row):
    raw = read(BASE/row['archive_path'])
    check('archive:' + row['relative_path'], len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'])
    return raw

def ar(rel): return archived(by_rel[rel])
def aj(rel): return json.loads(ar(rel))
def original(path): return archived(by_original[path.replace('\\','/')])
def rows(table): return [dict(zip(table['columns'], row)) for row in table['rows']]

scene = js(BASE/'inputs/SCENE_GEOMETRY_RATIONAL.json')
cameras = js(BASE/'inputs/CAMERAS.json')['views']
prompt = read(BASE/'inputs/PROMPT.txt').decode('utf-8')
objects = scene['objects']
check('two_exact_source_objects', [o['name'] for o in objects]==['Panel_A','Panel_B'])
bounds = []
for i,obj in enumerate(objects):
    verts = [[F(str(x)) for x in v] for v in obj['vertices']]
    faces = obj['triangles']
    bx = (min(v[0] for v in verts),max(v[0] for v in verts))
    by = (min(v[1] for v in verts),max(v[1] for v in verts))
    z = verts[0][2]
    check(f'object{i}:rectangular_corners', set(map(tuple,verts))=={(x,y,z) for x in bx for y in by})
    edges = {}
    for face in faces:
        a,b,c = [verts[k] for k in face]
        ab=[b[j]-a[j] for j in range(3)]; ac=[c[j]-a[j] for j in range(3)]
        normal=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
        check(f'object{i}:face{face}:positive_planar', normal[0]==normal[1]==0 and normal[2]>0)
        for a,b in zip(face,face[1:]+face[:1]): edges[tuple(sorted((a,b)))]=edges.get(tuple(sorted((a,b))),0)+1
    check(f'object{i}:shared_edge_rectangle', sorted(edges.values())==[1,1,1,1,2])
    bounds.append((bx,by,z))
check('all_four_source_triangles_supported', sum(len(o['triangles']) for o in objects)==4)

# Independent plane shadow construction: higher B is in front for every +Z viewing direction.
geometry = {}
for cam in cameras:
    name=cam['name']; d=list(map(F,cam['direction_rational']))
    check(name+':positive_z_view',d[2]>0)
    dz=bounds[1][2]-bounds[0][2]
    shadow_x=tuple(x-dz*d[0]/d[2] for x in bounds[1][0])
    shadow_y=tuple(y-dz*d[1]/d[2] for y in bounds[1][1])
    wx=max(F(0),min(bounds[0][0][1],shadow_x[1])-max(bounds[0][0][0],shadow_x[0]))
    wy=max(F(0),min(bounds[0][1][1],shadow_y[1])-max(bounds[0][1][0],shadow_y[0]))
    area=wx*wy
    inside=[]
    for obj in objects:
        vals=[]
        for v in obj['vertices']:
            h=list(map(lambda x:F(str(x)),v))+[F(1)]
            camera=[sum(F(str(cam['view_matrix'][r][k]))*h[k] for k in range(4)) for r in range(4)]
            ndc=[sum(F(str(cam['projection_matrix'][r][k]))*camera[k] for k in range(4)) for r in range(4)]
            vals.append(all(-1<ndc[k]<1 for k in range(3)) and camera[2]<0)
        inside.append(all(vals))
    check(name+':whole_objects_in_frustum',all(inside))
    complete=[bool(inside[0] and area==0),bool(inside[1])]
    geometry[name]={'A_shadow_area':str(area),'A_shadow_x':list(map(str,shadow_x)),
                    'A_shadow_y':list(map(str,shadow_y)),'complete':complete,'front':[True,True]}
check('SCENE_A_positive_quarter_occlusion',geometry['SCENE']['A_shadow_area']=='4')
check('other_five_A_no_area_occlusion',all(g['A_shadow_area']=='0' for n,g in geometry.items() if n!='SCENE'))
details['independent_geometry']=geometry

def pixel_metrics(arr):
    raw=arr['triangle_ids']; owned=arr['owners']; rgb=arr['color']
    sid=np.full(raw.shape,-1,dtype=np.int32)
    sid[(raw>=0)&(raw<2)]=0; sid[(raw>=2)&(raw<4)]=1
    check('raw_owner_range',np.all((raw>=-1)&(raw<4)) and np.array_equal(sid,owned))
    check('patch_matches_independent_object_surface',np.array_equal(sid,arr['patch_owners']))
    mark=np.zeros(raw.shape,bool)
    colors=rgb.astype(np.int32)
    for a,b in [((slice(None),slice(None,-1)),(slice(None),slice(1,None))),
                ((slice(None,-1),slice(None)),(slice(1,None),slice(None)))]:
        delta=colors[a]-colors[b]
        edge=(sid[a]!=sid[b])&((delta*delta).sum(axis=2)>=576)
        mark[a]|=edge;mark[b]|=edge
    result=[]
    for idx in range(2):
        mask=sid==idx; yy,xx=np.where(mask)
        result.append({'surface':int(mask.sum()),'boundary':int((mask&mark).sum()),
                       'bounds':[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],
                       'readable':bool(mask.sum()>=16 and (mask&mark).sum()>=4)})
    return result

phase_summaries={}; arrays_by_phase={}; publics={}
for phase,folder in [('Q','preparation/Q1'),('P','formal/P1')]:
    ledger=aj(folder+'/o/OBSERVATIONS.json')
    response=aj(folder+'/o/tool_01/RESPONSE.json')
    public=json.loads(next(c['text'] for c in response['result']['content'] if c['type']=='text'))
    publics[phase]=public
    region=rows(public['regions']); pixels=rows(public['pixels']); images=rows(public['images'])
    check(phase+':two_source_regions',[r['object_index'] for r in region]==[0,1])
    check(phase+':SCENE_then_TOP', [f['view_name'] for f in ledger['frames']]==['SCENE','TOP'])
    check(phase+':two_rasters',len(ledger['render_attempts'])==2)
    observed={}; arrays_by_phase[phase]={}
    for frame in ledger['frames']:
        name=frame['view_name']; npzraw=original(frame['NPZ']); pngraw=original(frame['PNG'])
        check(phase+name+':PNG_SHA',hashlib.sha256(pngraw).hexdigest()==frame['PNG_sha256'])
        check(phase+name+':NPZ_SHA',hashlib.sha256(npzraw).hexdigest()==frame['NPZ_sha256'])
        with np.load(io.BytesIO(npzraw),allow_pickle=False) as npz: arr={k:npz[k] for k in npz.files}
        arrays_by_phase[phase][name]=arr
        check(phase+name+':PNG_actual_RGB',np.array_equal(np.asarray(Image.open(io.BytesIO(pngraw)).convert('RGB')),arr['color']))
        check(phase+name+':source_offsets',arr['face_patch_offsets'].tolist()==[0,2,4])
        check(phase+name+':source_to_patch',arr['face_patch_ids'].tolist()==[0,0,1,1])
        obs=pixel_metrics(arr);observed[name]=obs
        imgidx=next(i for i,x in enumerate(images) if x['view_name']==name)
        check(phase+name+':image_ref',images[imgidx]['image_ref']==frame['ref'])
        for idx in range(2):
            p=next(x for x in pixels if x['image_index']==imgidx and x['region_index']==idx)
            actual=obs[idx]
            check(f'{phase}{name}{idx}:public_pixels',
                  (p['visible_surface_pixels'],p['contrasting_boundary_pixels'],p['readable'],p['visible_pixel_bounds'])==
                  (actual['surface'],actual['boundary'],actual['readable'],actual['bounds']))
            x,y=p['visible_pixel_anchor'];check(f'{phase}{name}{idx}:anchor_owned',int(arr['owners'][y,x])==idx)
    first=next(i for i,p in enumerate(pixels) if p['region_index']==0 and p['readable'])
    witness=region[0]['complete_witness_pixel_index'];wp=pixels[witness];wn=images[wp['image_index']]['view_name']
    check(phase+':first_readable_not_complete',first==0 and not geometry[images[pixels[first]['image_index']]['view_name']]['complete'][0])
    check(phase+':witness_correct_later_index',witness==2 and wn=='TOP' and geometry[wn]['complete'][0] and observed[wn][0]['readable'])
    for i,r in enumerate(region):
        pi=r['complete_witness_pixel_index'];p=pixels[pi];n=images[p['image_index']]['view_name']
        check(phase+f':complete_witness_region{i}',p['region_index']==i and geometry[n]['complete'][i] and observed[n][i]['readable'])
        check(phase+f':location_region{i}',r['center_world_m']==([0,0,0] if i==0 else [4,-4,3]) and r['front_direction_world']==[0,0,1])
    check(phase+':covered_exact',[r['status'] for r in region]==['covered','covered'] and public['coverage']['covered_region_indices']==[0,1])
    support=rows(public['scope']['patch_support']['object_support'])
    check(phase+':unsupported_zero',sum(r['unsupported_triangle_count'] for r in support)==0)
    check(phase+':remaining_zero',public['inspection']['counts']['unobserved']==0)
    phase_summaries[phase]={'pid':ledger['process_id'],'actual_rasters':len(ledger['render_attempts']),
                            'observed':observed,'first_readable':first,'complete_witness':witness}
check('separate_phase_owners',phase_summaries['Q']['pid']!=phase_summaries['P']['pid'])
details['phases']=phase_summaries

final=ar('formal/P1/c/final.txt').decode('utf-8')
requests=[aj(f'formal/P1/o/tool_{i:02}/REQUEST.json') for i in range(1,4)]
responses=[aj(f'formal/P1/o/tool_{i:02}/RESPONSE.json') for i in range(1,4)]
check('three_tool_sequence',[r['params']['name'] for r in requests]==['active_observation','execute_python','execute_python'])
check('tool_calls_successful',all(r['result']['isError'] is False for r in responses))
codes=[r['params']['arguments'].get('code','') for r in requests]
check('actual_public_JSON_parse','json.loads(last_observation_json)' in codes[1])
check('extra_geometry_and_camera_read',"print('GEOMETRY', geometry)" in codes[1] and "print('CAMERAS', cameras)" in codes[1])
check('extra_full_pixel_recompute',all(t in codes[2] for t in ["frame['triangle_ids']",'np.isin','marked = np.zeros','TOP_METRICS','np.cross']))
ledger=aj('formal/P1/o/OBSERVATIONS.json')
check('TOP_reuse_without_raster',len(ledger['cache_requests'])==1 and ledger['cache_requests'][0]['new_raster_attempts']==0)
reg=rows(publics['P']['regions']);topref=next(i['image_ref'] for i in rows(publics['P']['images']) if i['view_name']=='TOP')
check('final_source_binding',publics['P']['binding']['source_binding_sha256'] in final)
check('final_identity_both',all(r['roi_id'] in final for r in reg))
check('final_correct_witness_ref',topref in final and '**View:** `TOP`' in final and '**Public `complete_witness_pixel_index`:** `2`' in final)
check('final_correct_counts',all(x in final for x in ['70,756 / 1,060','17,689 / 528']))
check('final_scope_and_unknown',all(x in final for x in ['No supported surfaces remain unknown','no unsupported geometry exists','does not extend beyond that pool']))
check('final_six_view_scope',all('`'+v['name']+'`' in final for v in cameras))
arr=arrays_by_phase['P']['TOP']
check('final_owned_anchor',int(arr['owners'][155,155])==0 and int(arr['triangle_ids'][155,155])==1 and arr['color'][155,155].tolist()==[164,173,187])
contrast=float(np.linalg.norm(arr['color'][155,23].astype(float)-arr['color'][155,22].astype(float)))
check('final_contrast_pair',arr['owners'][155,23]==0 and arr['owners'][155,22]==-1 and round(contrast,2)==262.23)
check('prompt_not_revealing_expected_witness',not any(x in prompt for x in ['70756','707,56','37917','roi_','`TOP`','witness_pixel_index=2']))
auto=js(BASE/'admin/QUALITY.json')
details['original_auto_quality']=auto
details['final_contrast']=contrast
details['actual_tool_codes']=codes
result={'method':'Independent Fraction shadow/frustum calculation and saved NPZ/PNG/public/final review. No product/scorer imports or new raster/model calls.',
        'new_product_model_Blender_raster':0,'checks':len(checks),'passed':sum(c['pass'] for c in checks),
        'failures':[c for c in checks if not c['pass']],'details':details,
        'semantic_conclusion':{'case_realized':True,'product_facts_correct':True,'final_answer_correct':True,
                               'current_product_facts_used':True,'pure_direct_product_consumption':False,
                               'native_recomputation':'extra verification; no observed product error correction',
                               'automatic_original_status':'failed before content judgement; retained separately'}}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(list(inputs.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'passed':result['passed'],'failures':result['failures']}))
raise SystemExit(bool(result['failures']))
