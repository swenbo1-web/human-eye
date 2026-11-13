"""Independent offline geometry/pixel/answer audit. Never imports workload code."""
from pathlib import Path
from fractions import Fraction as F
from itertools import product
from collections import Counter
import base64, hashlib, io, json
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
V = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
B = V / 'm4_active_coverage_consumption_002'
OLD = V / 'm4_active_coverage_consumption_001'
INPUTS, CHECKS = {}, []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def read(path):
    return json.loads(raw(path))

def check(name, passed, **detail):
    CHECKS.append(dict(check=name, passed=bool(passed), **detail))

def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def hull(points):
    points=sorted(set(points))
    lo=[];hi=[]
    for group,source in ((lo,points),(hi,reversed(points))):
        for p in source:
            while len(group)>1 and orient(group[-2],group[-1],p)<=0: group.pop()
            group.append(p)
    return lo[:-1]+hi[:-1]
def clip(poly, axis, bound, greater):
    if not poly: return []
    out=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da=(a[axis]-bound)*(1 if greater else -1)
        db=(b[axis]-bound)*(1 if greater else -1)
        if da>=0: out.append(a)
        if (da<0<db) or (db<0<da):
            t=da/(da-db);out.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
    return out
def area(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if len(poly)>2 else F(0)
def matvec(m,v): return tuple(sum(F(x)*y for x,y in zip(row,v)) for row in m)

prompt=raw(OLD/'inputs/PROMPT.txt')
schema=read(B/'admin/SCORING_SCHEMA.json')
truth=read(B/'admin/TRUTH.json')
scene=read(OLD/'inputs/SCENE_GEOMETRY_RATIONAL.json')
cameras=read(OLD/'inputs/CAMERAS.json')
check('frozen_prompt',hashlib.sha256(prompt).hexdigest()=='a063914f32409ef33015c50751ea96a5d7646a672d5570d5eb5c725154c62583')
check('same_six_slots_no_optimal_view_gate',schema['slots']==['N1','P1','P2','N2','N3','P3'] and 'No optimal-view-count gate' in schema['cost_gate'])
objects=[];panels=[];boxes=[]
for oi,obj in enumerate(scene['objects']):
    verts=[tuple(F(x) for x in p) for p in obj['vertices']]
    tris=obj['triangles'];kind='other'
    if len(verts)==4 and len(set(verts))==4 and len(tris)==2:
        normals=[cross(sub(verts[t[1]],verts[t[0]]),sub(verts[t[2]],verts[t[0]])) for t in tris]
        edges=Counter(tuple(sorted((t[i],t[(i+1)%3]))) for t in tris for i in range(3))
        boundary=[e for e,n in edges.items() if n==1]
        adj={i:[] for i in range(4)}
        for a,b in boundary:adj[a].append(b);adj[b].append(a)
        rectangle=(all(len(adj[i])==2 for i in adj) and len(boundary)==4 and
                   all(dot(sub(verts[adj[i][0]],verts[i]),sub(verts[adj[i][1]],verts[i]))==0 for i in adj) and
                   dot(normals[0],normals[1])>0 and all(dot(normals[0],sub(p,verts[0]))==0 for p in verts))
        if rectangle:
            kind='panel';panels.append(oi)
            check('fixture_panel_is_xy_z0',all(p[2]==0 for p in verts),object=obj['name'])
    if len(verts)==8 and len(tris)==12:
        axes=[sorted({p[k] for p in verts}) for k in range(3)]
        box=(all(len(a)==2 for a in axes) and set(verts)==set(product(*axes)))
        faces={}
        for t in tris:
            vv=[verts[i] for i in t]
            normal=cross(sub(vv[1],vv[0]),sub(vv[2],vv[0]))
            plane=[k for k in range(3) if len({p[k] for p in vv})==1]
            if len(plane)!=1:box=False;continue
            k=plane[0];key=(k,vv[0][k]);faces[key]=faces.get(key,F(0))+abs(normal[k])/2
        for k in range(3):
            others=[j for j in range(3) if j!=k]
            full=(axes[others[0]][1]-axes[others[0]][0])*(axes[others[1]][1]-axes[others[1]][0])
            for v in axes[k]:box=box and faces.get((k,v))==full
        if box:kind='box';boxes.append(oi)
        check('occluder_closed_axis_aligned_box_above_targets',box and min(p[2] for p in verts)>0,object=obj['name'])
    objects.append({'name':obj['name'],'verts':verts,'tris':tris,'kind':kind})
check('independent_target_discovery',len(objects)==28 and len(panels)==6 and len(boxes)==22 and not any(o['kind']=='other' for o in objects))
cammap={c['name']:c for c in cameras['views']}
geometric={}
for oi in panels:
    obj=objects[oi];xs=[p[0] for p in obj['verts']];ys=[p[1] for p in obj['verts']]
    bounds=[min(xs),max(xs),min(ys),max(ys)]
    normal=cross(sub(obj['verts'][1],obj['verts'][0]),sub(obj['verts'][2],obj['verts'][0]))
    geometric[obj['name']]={}
    for name,cam in cammap.items():
        d=tuple(F(x) for x in cam['direction_rational']);front=dot(normal,d)>0
        contained=True
        for p in obj['verts']:
            vp=matvec(cam['view_matrix'],(*p,F(1)));cp=matvec(cam['projection_matrix'],vp)
            contained=contained and vp[2]<0 and cp[3]>0 and all(-cp[3]<=x<=cp[3] for x in cp[:3])
        blockers=[]
        for bi in boxes:
            poly=hull([(p[0]-p[2]*d[0]/d[2],p[1]-p[2]*d[1]/d[2]) for p in objects[bi]['verts']])
            for ax,limit,greater in [(0,bounds[0],True),(0,bounds[1],False),(1,bounds[2],True),(1,bounds[3],False)]:poly=clip(poly,ax,limit,greater)
            a=area(poly)
            if a>0:blockers.append({'object':objects[bi]['name'],'area':str(a)})
        complete=bool(front and contained and not blockers)
        geometric[obj['name']][name]={'front':bool(front),'inside':bool(contained),'complete':complete,'blockers':blockers}
        expected=next(t for t in truth['targets'] if t['object_name']==obj['name'])['by_view'][name]
        check('independent_geometry_vs_frozen_truth',complete==expected['geometry_complete'] and bool(front)==expected['front_facing'] and bool(contained)==expected['inside_viewport'] and {b['object'] for b in blockers}=={b['occluder'] for b in expected['positive_area_blockers']},object=obj['name'],view=name)

SLOTS=[];pixel_claims=[];blocker_claims=[];frames_all=[];tool_schemas={}
for slot in schema['slots']:
    S=B/'r'/slot
    answer_raw=raw(S/'c/final.txt');public=raw(S/'c/PUBLIC_FINAL.txt')
    answer=json.loads(answer_raw)
    events=[json.loads(line) for line in raw(S/'c/stdout.raw.bin').splitlines()]
    msg=[e['item'].get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    check('raw_final_bound_to_original_stdout',answer_raw.strip()==public.strip() and msg[-1].strip()==answer_raw.decode().strip(),slot=slot)
    obs=read(S/'o/OBSERVATIONS.json');ident=read(S/'o/IDENTITY.json');ts=read(S/'o/TOOLS_SCHEMA.json');tool_schemas[slot]=ts
    check('current_source_identity',all(ident['source_inputs'][k]==v for k,v in truth['source_binding'].items()),slot=slot)
    check('no_old_evidence_reads_reported',obs['audit']['forbidden_old_evidence_reads']==0 and obs['audit']['forbidden_old_writes']==0,slot=slot)
    check('targets_exact',sorted(p['object'] for p in answer['panels'])==sorted(objects[i]['name'] for i in panels),slot=slot)
    frames={};counts={}
    for frame in obs['frames']:
        name=frame['view_name'];frames[frame['ref']]=frame
        png=raw(frame['PNG']);npz=raw(frame['NPZ'])
        check('frame_files_current_slot',Path(frame['PNG']).is_relative_to(S) and Path(frame['NPZ']).is_relative_to(S),slot=slot,view=name)
        check('frame_hashes_pose',hashlib.sha256(png).hexdigest()==frame['PNG_sha256'] and hashlib.sha256(npz).hexdigest()==frame['NPZ_sha256'] and frame['pose']==cammap[name],slot=slot,view=name)
        with np.load(io.BytesIO(npz),allow_pickle=False) as z: arrays={k:z[k] for k in z.files}
        rgb,owners,depth=arrays['color'],arrays['owners'],arrays['depth']
        check('PNG_exact_RGB',np.array_equal(np.asarray(Image.open(io.BytesIO(png)).convert('RGB')),rgb),slot=slot,view=name)
        check('owner_depth_consistency',np.all((owners>=-1)&(owners<len(objects))) and np.all(np.isfinite(depth[owners>=0])) and np.all(depth[owners>=0]>0) and np.all(np.isinf(depth[owners<0])),slot=slot,view=name)
        for key,a in arrays.items():
            meta=frame['arrays'][key]
            check('array_full_bytes',hashlib.sha256(a.tobytes()).hexdigest()==meta['sha256'] and list(a.shape)==meta['shape'] and a.dtype.str==meta['dtype_str'],slot=slot,view=name,array=key)
        colors=rgb.astype(np.int32)
        hit=np.zeros(owners.shape,dtype=bool)
        delta=colors[:,1:]-colors[:,:-1];edges=(owners[:,1:]!=owners[:,:-1])&(np.sum(delta*delta,axis=2)>=576)
        hit[:,1:]|=edges;hit[:,:-1]|=edges
        delta=colors[1:]-colors[:-1];edges=(owners[1:]!=owners[:-1])&(np.sum(delta*delta,axis=2)>=576)
        hit[1:]|=edges;hit[:-1]|=edges
        for oi in panels:
            mask=owners==oi;counts[(frame['ref'],oi)]=(int(np.count_nonzero(mask)),int(np.count_nonzero(mask&hit)))
            t=next(t for t in truth['targets'] if t['object_index']==oi)['by_view'][name]
            check('actual_frame_pixels_vs_registered_truth',counts[(frame['ref'],oi)]==(t['visible_surface_pixels'],t['contrasting_boundary_pixels']),slot=slot,view=name,object=objects[oi]['name'])
        if slot.startswith('P'):
            for row in frame['pixel_rows']:
                actual=counts[(frame['ref'],row['object_index'])]
                check('active_pixel_feedback_actual',actual==(row['visible_surface_pixels'],row['contrasting_boundary_pixels']) and row['readable']==(actual[0]>=16 and actual[1]>=4),slot=slot,view=name,object=objects[row['object_index']]['name'])
        frames_all.append({'slot':slot,'view':name,'ref':frame['ref'],'PNG_sha256':frame['PNG_sha256'],'NPZ_sha256':frame['NPZ_sha256']})
    start=len(CHECKS)
    for panel in answer['panels']:
        oi=next(i for i,o in enumerate(objects) if o['name']==panel['object']);valid=[]
        for vr in panel['views']:
            frame=frames.get(vr['ref']);check('answer_ref_in_current_session',frame is not None and frame['view_name']==vr['view'],slot=slot,object=panel['object'],ref=vr['ref'])
            if frame is None:continue
            n=counts[(vr['ref'],oi)];g=geometric[panel['object']][vr['view']]
            if g['complete'] and n[0]>=16 and n[1]>=4:valid.append(vr['ref'])
            for key,ix in [('surface_pixels',0),('owner_surface_pixels',0),('boundary_pixels',1),('contrasting_boundary_pixels',1)]:
                if key in vr:
                    pixel_claims.append({'slot':slot,'object':panel['object'],'view':vr['view'],'field':key,'claimed':vr[key],'actual':n[ix]})
                    check('explicit_pixel_claim',type(vr[key])==int and vr[key]==n[ix],slot=slot,object=panel['object'],view=vr['view'],field=key)
            if 'occluder' in vr:
                valid_blocker=vr['occluder'] in {b['object'] for b in g['blockers']}
                blocker_claims.append({'slot':slot,'view':vr['view'],'object':panel['object'],'occluder':vr['occluder'],'positive_area_verified':valid_blocker})
                check('explicit_positive_area_blocker',valid_blocker,slot=slot,view=vr['view'])
        coverable=any(v['complete'] for v in geometric[panel['object']].values())
        check('panel_answer_status_and_evidence',panel['status']==('covered' if coverable else 'uncovered') and (bool(valid) if coverable else not valid),slot=slot,object=panel['object'])
        if not coverable:
            reason=panel['reason'].lower()
            check('uncovered_scoped_and_justified',('finite' in reason or 'registered' in reason) and 'occlusion' in reason and all(v['blockers'] for v in geometric[panel['object']].values()),slot=slot)
    tool_requests=[read(p) for p in sorted((S/'o').glob('tool_*/REQUEST.json'))]
    captured_codes=[x['params']['arguments']['code'] for x in tool_requests if x['params']['name']=='execute_python']
    check('no_captured_admin_answer_read',not any(any(word in code for word in ['TRUTH','ADMIN_ORACLE','QUALITY_AUTHOR','review/','verification/']) for code in captured_codes),slot=slot)
    if slot.startswith('P'):
        check('P_online_single_active_request',len(tool_requests)==1 and tool_requests[0]['params']['name']=='active_coverage',slot=slot)
        trace=[json.loads(x) for x in raw(S/'o/TRACE.jsonl').splitlines()]
        index=[x for x in trace if x.get('name')=='active_index']
        tools=read(S/'o/TOOLS.json')['tools']
        check('index_built_inside_actual_tool',len(index)==1 and tools[0]['started_ns']<=index[0]['started_ns']<index[0]['closed_ns']<=tools[0]['closed_ns'],slot=slot)
        check('P_active_state_closed_over_current_pixels',obs['active']['final_state']['observed_views']==['SCENE','BACK'] and obs['active']['final_state']['state_updates']==2 and len(obs['active']['final_state']['covered_roi_ids'])==5,slot=slot)
        for step in obs['active']['steps']:
            check('P_current_image_receipt',step['receipt']['image_sha256']==frames[step['ref']]['PNG_sha256'],slot=slot,view=step['view_name'])
        response=read(S/'o/tool_01/RESPONSE.json')
        images=[base64.b64decode(x['data'],validate=True) for x in response['result']['content'] if x['type']=='image']
        check('P_real_generated_image_blocks',sorted(hashlib.sha256(x).hexdigest() for x in images)==sorted(f['PNG_sha256'] for f in frames.values()),slot=slot)
    else:
        check('N_self_programmed_no_active_endpoint',captured_codes and all(x['params']['name']!='active_coverage' for x in tool_requests) and obs['active'] is None,slot=slot)
    SLOTS.append({'slot':slot,'content_quality_passed':all(c['passed'] for c in CHECKS[start:]),'answer_sha256':hashlib.sha256(answer_raw).hexdigest(),'targets':len(answer['panels']),'covered':sum(p['status']=='covered' for p in answer['panels'])})

reference=tool_schemas['N1']
for slot,ts in tool_schemas.items():
    check('identical_common_tools',ts[:4]==reference and len(ts)==(5 if slot.startswith('P') else 4),slot=slot)
actor=raw(OLD/'actor.py').decode();common=raw(OLD/'common_observation.py').decode()
check('public_native_batch_python_images_arrays',all(x in actor for x in ['"geometry": copy.deepcopy(self.session.scene)','"cameras": copy.deepcopy(self.session.cameras)','"render_views": self.python_render_views','"read_images": self.request_images','"attach_images": self.request_images','"buffers": MappingProxyType(self.session.buffers)']))
check('active_actual_source_algorithm',all(x in common for x in ['self.core.build_index(self.scene, self.cameras, "optimized")','self.state.next_view()','self.render_views([name])','rows = self.qualify_frame(frame)','self.state.observe(receipt)']))
check('explicit_claim_denominators',len(pixel_claims)==72 and len(blocker_claims)==18)
failed=[x for x in CHECKS if not x['passed']]
result={'candidate_commit':'c556d29156e7d65fc02238dca63321ac062d2c1a','scope':'Independent offline answer, geometry, PNG/NPZ and source-text audit; no author modules imported or captured code executed.',
        'checks':CHECKS,'total':len(CHECKS),'passed':len(CHECKS)-len(failed),'failed':failed,
        'slots':SLOTS,'independent_geometry':geometric,'frames':frames_all,'explicit_pixel_claims':pixel_claims,'explicit_blocker_claims':blocker_claims,
        'new_model_CLI_actor_renderer_Blender_calls':0,'author_quality_and_cost_reports_used':False,
        'limits':['Current fixed geometry consists of six axis-aligned xy rectangles and 22 closed boxes; independent projected convex-box audit is limited to this verified shape class.','Frame bytes and logs were inspected; no historic process was observed live.','No texture recognition, general scene scan, free camera synthesis or arbitrary curved/concave surface completeness was tested.']}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(INPUTS,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(CHECKS),'passed':len(CHECKS)-len(failed),'failed':failed,'slots':SLOTS,'frames':len(frames_all),'pixel_claims':len(pixel_claims),'blocker_claims':len(blocker_claims)}))
