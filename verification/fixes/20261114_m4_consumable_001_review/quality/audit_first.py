"""Independent offline consumer and pixel audit. No product/scorer imports."""
from pathlib import Path
from fractions import Fraction
import json, hashlib, base64
import numpy as np
from PIL import Image

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_consumable_observation_001'
S=Path('D:/he_consume_001/formal/P1'); O=Path(__file__).parent
inputs={}; checks=[]
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]=hashlib.sha256(b).hexdigest(); return b
def js(p):return json.loads(raw(p))
def ck(n,v):checks.append({'name':n,'passed':bool(v)})
def rows(t):return [dict(zip(t['columns'],r)) for r in t['rows']]
def answer(i):return js(S/f'o/tool_{i:02}/RESPONSE.json')['result']
def stdout(i):return json.loads(answer(i)['content'][0]['text'])['stdout']

events=[json.loads(l) for l in raw(S/'c/stdout.raw.bin').splitlines() if l.strip()]
calls=[e['item'] for e in events if e['type']=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
ck('seven_actual_calls',len(calls)==7)
ck('actual_sequence',[c['tool'] for c in calls]==['active_observation','execute_python','execute_python','render_views','execute_python','execute_python','execute_python'])
for i,c in enumerate(calls,1):
    req=js(S/f'o/tool_{i:02}/REQUEST.json')['params']; response=answer(i)
    ck(f'call_binding_{i}',c['tool']==req['name'] and c['arguments']==req['arguments'])
    ck(f'content_binding_{i}',c['result']['content']==response['content'])
    ck(f'error_{i}',response.get('isError',False)==(i==5))
final=raw(S/'c/PUBLIC_FINAL.txt').decode('utf-8')
messages=[e['item']['text'] for e in events if e['type']=='item.completed' and e.get('item',{}).get('type')=='agent_message']
ck('actual_final',messages[-1].strip()==final.strip())
ck('normal_turn_complete',sum(e['type']=='turn.completed' for e in events)==1)
for phrase in ['138','115','23','triangle **48**','113', '0.15625']:
    if phrase!='113':ck('final_phrase_'+phrase,phrase in final)
ck('final_explicit_tool_facts','tool facts retain the complete coverage sets' in final)
ck('observed_statement','115 completely observed and readable' in final)
ck('unobserved_scope','unobserved, not proven uninspectable' in final)

body=answer(1)['content'][0]['text']; b=json.loads(body)
regions=rows(b['regions']); pixels=rows(b['pixels']); images=rows(b['images'])
ck('schema',b['schema']=='active-observation-brief-v4')
ck('counts',len(regions)==138 and len(pixels)==414 and len(images)==3)
service=js(S/'o/product_call_01/SERVICE_RESULT.json')
ck('source_pin',service['binding']['runtime_source_sha256']=='6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f')
for i,(pub,internal) in enumerate(zip(regions,service['facts']['regions'])):
    common=['roi_id','object_index','status','reason','center_world_m','half_edge_u_world_m','half_edge_v_world_m','front_direction_world']
    ck(f'producer_region_{i}',all(pub[k]==internal[k] for k in common))
for vi,ob in enumerate(service['facts']['observations']):
    ck(f'image_reference_{vi}',ob['image_ref']==images[vi]['image_ref'] and ob['view_name']==images[vi]['view_name'])
    for ri,pub in enumerate(pixels[vi*138:(vi+1)*138]):
        internal=ob['pixel_rows'][ri]
        ck(f'producer_pixel_{vi}_{ri}',pub['region_index']==ri and pub['image_index']==vi and all(pub[k]==internal[k] for k in pub if k not in ('region_index','image_index')))

# Reuse a prior independently recomputed full finite-pool geometry table only
# after verifying its prior recorded hash and identical scene/camera bytes.
previous=js('D:/hefe/verification/fixes/20261114_m4_localization_consumption_001_review/quality/RESULTS.json')
gp=Path('D:/he_loc_001/formal/P3/o/scratch/scene_inspection.json')
g=js(gp)
ck('prior_independent_geometry_source',previous['passed'] and inputs[str(gp)]==previous['inputs'][str(gp)])
sources=js(H/'inputs/SOURCES.json')
for name in ('scene','cameras'):
    source=sources[name]; data=raw(source['path'])
    ck('same_'+name,hashlib.sha256(data).hexdigest()==source['sha256']==previous['inputs'][str(Path(source['path']))])
geometry=js(sources['scene']['path']); cameras=js(sources['cameras']['path'])
truth={(tuple(t['center_world']),tuple(t['front_normal'])):t for t in g['surfaces']}
ck('reference_unique138',len(truth)==138)
source_to_region=np.full(3337,-1,dtype=np.int32); mapped=[]
for i,r in enumerate(regions):
    t=truth[(tuple(r['center_world_m']),tuple(r['front_direction_world']))];mapped.append(t)
    center=np.array(r['center_world_m']);u=np.array(r['half_edge_u_world_m']);v=np.array(r['half_edge_v_world_m'])
    corners={tuple(center+a*u+c*v) for a,c in [(-1,-1),(1,-1),(1,1),(-1,1)]}
    ids=t['source_triangle_indices']
    ck(f'geometry_identity_{i}',corners=={tuple(x) for x in t['world_corners']} and len(ids)==r['triangle_count'])
    ck(f'nonoverlap_sources_{i}',np.all(source_to_region[ids]==-1))
    source_to_region[ids]=i
    ck(f'coverage_truth_{i}',(r['status']=='covered')==(t['status']=='observed'))
ck('unsupported48',np.flatnonzero(source_to_region<0).tolist()==[48])

obs=js(S/'o/OBSERVATIONS.json');frames=obs['frames'];ck('four_frames',len(frames)==4)
data_by_view={}
for k,f in enumerate(frames):
    raw(f['NPZ']);png=raw(f['PNG'])
    ck(f'frame_file_hash_{k}',inputs[str(Path(f['NPZ']))]==f['NPZ_sha256'] and hashlib.sha256(png).hexdigest()==f['PNG_sha256'])
    with np.load(f['NPZ'],allow_pickle=False) as z:data={key:z[key] for key in z.files}
    for key,row in f['arrays'].items():
        ck(f'array_{k}_{key}',hashlib.sha256(data[key].tobytes()).hexdigest()==row['sha256'] and data[key].dtype.name==np.dtype(row['dtype']).name and list(data[key].shape)==row['shape'])
    rgb=data['color']; ck(f'PNG_RGB_{k}',np.array_equal(np.array(Image.open(f['PNG']).convert('RGB')),rgb))
    if k<3:
        ids=data['patch_owners'];ck(f'patch_rois_{k}',data['patch_roi_ids'].tolist()==[r['roi_id'] for r in regions])
        ck(f'face_mapping_{k}',np.array_equal(data['face_patch_ids'],source_to_region))
        data_by_view[f['view_name']]=data
    else:
        ids=np.full(data['triangle_ids'].shape,-2,dtype=np.int32);valid=data['triangle_ids']>=0;ids[valid]=source_to_region[data['triangle_ids'][valid]]
        ck('repeat_SCENE_patch_identity',np.array_equal(ids,data_by_view['SCENE']['patch_owners']))
        ck('repeat_SCENE_pixels',np.array_equal(rgb,data_by_view['SCENE']['color']))
        ck('repeat_SCENE_png_and_pose',f['PNG_sha256']==frames[0]['PNG_sha256'] and f['pose']==frames[0]['pose'])
    boundary=np.zeros(ids.shape,dtype=bool);rgb=rgb.astype(np.int32)
    for a,z in [((slice(None),slice(None,-1)),(slice(None),slice(1,None))),((slice(None,-1),slice(None)),(slice(1,None),slice(None)))]:
        mark=(ids[a]!=ids[z]) & (((rgb[a]-rgb[z])**2).sum(axis=2)>=576);boundary[a]|=mark;boundary[z]|=mark
    pi=k if k<3 else 0
    for ri,p in enumerate(pixels[pi*138:(pi+1)*138]):
        mask=ids==ri;surface=int(mask.sum());edge=int((mask&boundary).sum())
        ck(f'pixels_{k}_{ri}',surface==p['visible_surface_pixels'] and edge==p['contrasting_boundary_pixels'])
        y,x=np.nonzero(mask)
        bounds=[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if surface else None
        ck(f'pixel_bounds_{k}_{ri}',p['visible_pixel_bounds']==bounds)
        anchor=p['visible_pixel_anchor']
        ck(f'owned_anchor_{k}_{ri}',anchor is None if not surface else anchor is not None and ids[anchor[1],anchor[0]]==ri)
        ck(f'front_facing_{k}_{ri}',p['front_facing']==mapped[ri]['evidence_by_view'][f['view_name']]['front_facing'])
    if k<3:ck(f'CLI_PNG_{k}',base64.b64decode(answer(1)['content'][k+1]['data'])==png)
    else:ck('CLI_repeat_PNG',base64.b64decode(answer(4)['content'][2]['data'])==png)

covered=[];unknown=[]
for i,r in enumerate(regions):
    wi=r['complete_witness_pixel_index']; t=mapped[i]
    if r['status']=='covered':
        covered.append(i);p=pixels[wi];view=images[p['image_index']]['view_name']
        ck(f'complete_current_witness_{i}',p['region_index']==i and p['readable'] and t['evidence_by_view'][view]['complete'] and p['visible_surface_pixels']>=16 and p['contrasting_boundary_pixels']>=4)
    else:
        unknown.append(i);ck(f'no_witness_{i}',wi is None)
        e=t['evidence_by_view'];front=[v for v in e.values() if v['front_facing']]
        expected='no_front_facing_candidate' if not front else 'all_front_facing_candidates_occluded'
        ck(f'unknown_reason_{i}',r['unobserved_reason']==expected and (not front or all(v['occluders'] for v in front)))
ck('coverage115_23',len(covered)==115 and len(unknown)==23 and covered==b['coverage']['covered_region_indices'] and unknown==b['coverage']['unresolved_region_indices'])
table=json.loads(stdout(7))
ck('actual_table138',len(table['rows'])==138)
for i,row in enumerate(table['rows']):
    ids=[n for a,z in row[1] for n in range(a,z+1)]
    ck(f'final_table_identity_{i}',row[0]==i and ids==mapped[i]['source_triangle_indices'] and row[2]==regions[i]['status'])
    if row[2]=='covered':
        w=row[3];vi=[im['view_name'] for im in images].index(w[0]);p=pixels[vi*138+i]
        ck(f'final_table_witness_{i}',w[1]==images[vi]['image_ref'] and w[2:]==[p['visible_surface_pixels'],p['contrasting_boundary_pixels'],p['visible_pixel_anchor']] and mapped[i]['evidence_by_view'][w[0]]['complete'])
    else:ck(f'final_table_reason_{i}',row[3]==regions[i]['unobserved_reason'])

ck('click_owned_anchor',pixels[72]['visible_pixel_anchor']==[109,247] and int(data_by_view['SCENE']['patch_owners'][247,109])==72)
ck('click_world',regions[72]['center_world_m']==[.15625,-.15625,.11865234375] and regions[72]['front_direction_world']==[0,0,1])
ck('origin_SCENE_zero',regions[131]['center_world_m']==[0,0,0] and pixels[131]['front_facing'] and pixels[131]['visible_surface_pixels']==0)
ck('origin_BACK',pixels[269]['visible_pixel_anchor']==[419,224] and pixels[269]['visible_surface_pixels']==468 and pixels[269]['contrasting_boundary_pixels']==84)
ck('bottom',regions[107]['center_world_m']==[.15625,-.15625,.11572265625] and regions[107]['unobserved_reason']=='no_front_facing_candidate')
ck('actual_JSON_load','obs=json.loads(last_observation_json)' in calls[1]['arguments']['code'] and 'inspection' in stdout(2))
ck('actual_JSON_queries',"obs['pixels']" in calls[2]['arguments']['code'] and 'TARGET 131' in stdout(3))
ck('duplicate_raster_request',calls[3]['arguments']=={'names':['SCENE'],'include_images':True})
ck('provided_regions_used_for_mapping',"enumerate(regions)" in calls[5]['arguments']['code'] and "region['center_world_m']" in calls[5]['arguments']['code'])
bridge=raw(H/'bridge.py').decode();ck('direct_public_string_assignment','self.namespace["last_observation_json"] = content[0]["text"]' in bridge)
result={'passed':all(c['passed'] for c in checks),'checks':len(checks),'failures':[c for c in checks if not c['passed']], 'inputs':inputs,'actual_quality':'1/1','actual_direct_efficiency':'fail_duplicate_SCENE','covered':115,'unobserved':23,'unsupported_triangles':[48],'geometry_reference':'Prior root independently recomputed P3 table, same scene/camera bytes; current pixels independently recomputed from saved arrays.','actual_JSON_copy_limit':'No independent namespace dump; binding code and real parse/query show public-result reuse, not provider internal byte visibility.','new_product_model_Blender_raster_benchmark_calls':0}
(O/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
(O/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='inputs'},ensure_ascii=False))
