"""Independent offline six-answer/24-frame review. No author module imports."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
BASE=ROOT/'m4_active_coverage_consumption_001'
OLD=ROOT/'m4_active_coverage_001'
checks=[]; inputs={}; results={}
def raw(p):
    p=Path(p);b=p.read_bytes();inputs[str(p)]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return b
def doc(p):return json.loads(raw(p))
def ck(n,x,detail=None):checks.append(dict(name=n,passed=bool(x),detail=detail))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def scale(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
scene=doc(BASE/'inputs/SCENE_GEOMETRY_RATIONAL.json');cameras=doc(BASE/'inputs/CAMERAS.json')
old_scene=doc(OLD/'inputs/SCENE_GEOMETRY_RATIONAL.json');old_cameras=doc(OLD/'inputs/CAMERAS.json')
ck('same_geometry_as_accepted001',scene==old_scene);ck('same_cameras_as_accepted001',cameras==old_cameras)
objects=scene['objects'];verts=[[tuple(F(x) for x in p) for p in obj['vertices']] for obj in objects]
targets={}
for idx,obj in enumerate(objects):
    ps=verts[idx];ts=obj['triangles']
    if len(ps)!=4 or len(set(ps))!=4 or len(ts)!=2:continue
    normals=[cross(sub(ps[t[1]],ps[t[0]]),sub(ps[t[2]],ps[t[0]])) for t in ts]
    if not all(dot(n,n)>0 for n in normals) or cross(*normals)!=(0,0,0) or dot(*normals)<=0:continue
    if any(dot(normals[0],sub(p,ps[0])) for p in ps):continue
    edge_counts=Counter(tuple(sorted((t[i],t[(i+1)%3]))) for t in ts for i in range(3))
    boundary=[e for e,count in edge_counts.items() if count==1]
    if len(boundary)!=4 or sum(count==2 for count in edge_counts.values())!=1:continue
    adjacency={i:[] for i in range(4)}
    for a,b in boundary:adjacency[a].append(b);adjacency[b].append(a)
    if any(len(v)!=2 for v in adjacency.values()):continue
    if any(dot(sub(ps[a],ps[i]),sub(ps[b],ps[i])) for i,(a,b) in adjacency.items()):continue
    targets[obj['name']]=dict(index=idx,normal=normals[0])
old_index=doc(OLD/'results/optimized.json')
roi_names={r['roi_id']:r['display_name'] for r in old_index['regions']}
complete={v['view_name']:{roi_names[r] for r in v['geometric_complete_roi_ids']} for v in old_index['per_view']}
ck('independent_target_discovery_matches_accepted001',set(targets)==set(roi_names.values()))
visible=set().union(*complete.values());uncovered=set(targets)-visible
ck('target_count',len(targets)==6);ck('finite_pool_uncovered',uncovered=={'Obj_006'})

# Exact ray/triangle witnesses for specific blockers. Several strict interior
# target points ensure the claim is not only a boundary tangency observation.
target_ps=verts[targets['Obj_006']['index']]
p0=target_ps[0];u=sub(target_ps[1],p0);v=sub(target_ps[3],p0)
probes=[add(p0,add(scale(u,a),scale(v,b))) for a,b in [(F(1,3),F(2,5)),(F(2,3),F(2,5)),(F(2,5),F(2,3))]]
blockers={}
for camera in cameras['views']:
    d=tuple(F(x) for x in camera['direction_rational']);names=[];witnesses=[]
    for origin in probes:
        hits=[]
        for oi,obj in enumerate(objects):
            if obj['name']=='Obj_006':continue
            for ti,t in enumerate(obj['triangles']):
                a,b,c=[verts[oi][i] for i in t];e1=sub(b,a);e2=sub(c,a)
                h=cross(d,e2);det=dot(e1,h)
                if not det:continue
                s=sub(origin,a);bu=dot(s,h)/det;q=cross(s,e1);bv=dot(d,q)/det;distance=dot(e2,q)/det
                if distance>0 and bu>=0 and bv>=0 and bu+bv<=1:hits.append((distance,obj['name'],ti,bu,bv))
        assert hits
        hit=min(hits);names.append(hit[1]);witnesses.append(dict(object=hit[1],triangle=hit[2],ray_t=str(hit[0]),barycentric=[str(hit[3]),str(hit[4])]))
    ck('strict_blocker_witness_'+camera['name'],len(set(names))==1 and all(F(w['barycentric'][0])>0 and F(w['barycentric'][1])>0 and sum(map(F,w['barycentric']))<1 for w in witnesses))
    blockers[camera['name']]=dict(object=names[0],witnesses=witnesses)

tools_spec=doc(BASE/'PUBLIC_TOOLS.json')
ck('same_four_common_schemas',tools_spec['P'][:4]==tools_spec['N'] and len(tools_spec['N'])==4)
ck('P_only_extra_active',len(tools_spec['P'])==5 and tools_spec['P'][4]['name']=='active_coverage')
prompt=raw(BASE/'inputs/PROMPT.txt')
total_frames=0;scalar_count=0;blocker_count=0;all_quality=[]
for slot in ('N1','P1','P2','N2','N3','P3'):
    start=len(checks);folder=BASE/'r'/slot;final=doc(folder/'c/final.txt');text=raw(folder/'c/PUBLIC_FINAL.txt')
    ck(slot+'/public_final_identical',text==raw(folder/'c/final.txt'))
    rows=final['panels'];names=[p['object'] for p in rows]
    ck(slot+'/complete_unique_target_set',len(names)==len(set(names)) and set(names)==set(targets))
    obs=doc(folder/'o/OBSERVATIONS.json');outer=doc(folder/'RESULT.json')
    ck(slot+'/no_forbidden_old_reads',obs['audit']['forbidden_old_evidence_reads']==0)
    ck(slot+'/actual_input_identity',obs['source_inputs']['scene_sha256']==hashlib.sha256(raw(BASE/'inputs/SCENE_GEOMETRY_RATIONAL.json')).hexdigest() and obs['source_inputs']['camera_sha256']==hashlib.sha256(raw(BASE/'inputs/CAMERAS.json')).hexdigest())
    ck(slot+'/common_tools_match',doc(folder/'o/TOOLS_SCHEMA.json')==tools_spec[slot[0]])
    frames={f['view_name']:f for f in obs['frames']};counts={}
    ck(slot+'/fresh_distinct_views',len(frames)==len(obs['frames'])==len(obs['render_attempts']))
    for view,frame in frames.items():
        total_frames+=1
        raw(frame['NPZ']);raw(frame['PNG'])
        with np.load(frame['NPZ'],allow_pickle=False) as a:color,owners,depth=[a[k] for k in ('color','owners','depth')]
        with Image.open(frame['PNG']) as im:rgb=np.array(im.convert('RGB'))
        with np.load(OLD/'render'/(view+'.npz'),allow_pickle=False) as old:
            ck(slot+'/'+view+'/arrays_same_accepted001',all(np.array_equal(x,old[k]) for x,k in [(color,'color'),(owners,'owners'),(depth,'depth')]))
        ck(slot+'/'+view+'/PNG_matches_array',np.array_equal(color,rgb))
        ck(slot+'/'+view+'/current_run_path',Path(frame['NPZ']).is_relative_to(folder/'o') and Path(frame['PNG']).is_relative_to(folder/'o'))
        edge=np.zeros(owners.shape,dtype=bool);color64=color.astype(np.int64)
        for axis in (0,1):
            changed=np.diff(owners,axis=axis)!=0;delta=np.diff(color64,axis=axis)
            good=changed & (np.einsum('ijk,ijk->ij',delta,delta)>=576)
            if axis==0:edge[:-1,:]|=good;edge[1:,:]|=good
            else:edge[:,:-1]|=good;edge[:,1:]|=good
        counts[view]={name:dict(surface=int(np.count_nonzero(owners==target['index'])),boundary=int(np.count_nonzero(edge & (owners==target['index'])))) for name,target in targets.items()}
    slot_scalars=0;slot_blockers=0
    for row in rows:
        name=row['object'];covered=name in visible
        ck(slot+'/'+name+'/status',row['status']==('covered' if covered else 'uncovered'))
        ck(slot+'/'+name+'/covered_has_evidence',bool(row['views']) if covered else True)
        for ev in row['views']:
            view=ev['view'];f=frames.get(view);prefix=slot+'/'+name+'/'+view
            ck(prefix+'/real_image_ref',f is not None and ev['ref']==f['ref'])
            if f is None:continue
            if covered:
                ck(prefix+'/accepted_geometry_complete',name in complete[view])
                ck(prefix+'/actual_pixels_pass',counts[view][name]['surface']>=16 and counts[view][name]['boundary']>=4)
            for key in ('surface_pixels','owner_surface_pixels','visible_surface_pixels'):
                if key in ev:ck(prefix+'/'+key,ev[key]==counts[view][name]['surface']);slot_scalars+=1
            for key in ('boundary_pixels','contrasting_boundary_pixels'):
                if key in ev:ck(prefix+'/'+key,ev[key]==counts[view][name]['boundary']);slot_scalars+=1
            if 'occluder' in ev:
                ck(prefix+'/exact_specific_occluder',ev['occluder']==blockers[view]['object']);slot_blockers+=1
        if not covered:
            explanation=json.dumps(final).lower()
            ck(slot+'/'+name+'/finite_pool_scope',('finite' in explanation or 'camera pool' in explanation) and 'occlu' in str(row['reason']).lower())
    total_tools=doc(folder/'o/TOOLS.json');requests=[]
    for p in sorted((folder/'o').glob('tool_*/REQUEST.json')):requests.append(doc(p)['params'])
    ck(slot+'/actual_calls_match_logs',len(requests)==total_tools['calls'])
    if slot[0]=='N':
        ck(slot+'/native_only_generic_python',all(x['name']=='execute_python' for x in requests))
        ck(slot+'/native_no_active_index',obs['active'] is None)
        code='\n'.join(x['arguments']['code'] for x in requests)
        ck(slot+'/native_own_exact_math_and_pixels',all(s in code for s in ('Fraction','cross','render_views','buffers')))
        ck(slot+'/native_no_private_file_import',not any(s in code for s in ('coverage.py','common_observation','read_text','read_bytes','open(','importlib','__globals__','__self__')))
    else:
        ck(slot+'/single_actual_active_tool',len(requests)==1 and requests[0]['name']=='active_coverage')
        ck(slot+'/live_current_index_identity',obs['active']['index']['scene_identity']==old_index['scene_identity'] and obs['active']['index']['candidate_identity']==old_index['candidate_identity'])
        ck(slot+'/active_recomputed_same_classifications',obs['active']['index']['classifications']==old_index['classifications'])
        stages=[s for s in obs['stages'] if s['name']=='active_index'];tool=total_tools['tools'][0]
        ck(slot+'/index_computed_inside_actual_tool',len(stages)==1 and tool['started_ns']<=stages[0]['started_ns']<stages[0]['closed_ns']<=tool['closed_ns'])
        ck(slot+'/rasters_inside_actual_tool',all(tool['started_ns']<=f['render_started_ns']<f['render_closed_ns']<=tool['closed_ns'] for f in obs['frames']))
        facts=doc(folder/'o/tool_01/RESPONSE.json')['result']['content'][0]
        facts= json.loads(facts['text']);ck(slot+'/facts_target_set',{x['object'] for x in facts['panels']}==set(targets))
        for p in facts['panels']:
            ck(slot+'/fact/'+p['object'],p['status']==('covered' if p['object'] in visible else 'uncovered'))
            for ev in p['views']:
                ck(slot+'/fact/'+p['object']+'/'+ev['view'],ev['ref']==frames[ev['view']]['ref'] and ev['visible_surface_pixels']==counts[ev['view']][p['object']]['surface'] and ev['contrasting_boundary_pixels']==counts[ev['view']][p['object']]['boundary'])
    slot_checks=checks[start:];quality=all(c['passed'] for c in slot_checks)
    all_quality.append(quality);scalar_count+=slot_scalars;blocker_count+=slot_blockers
    results[slot]=dict(answer_quality_pass=quality,outer_qualified=outer['outer_valid_completion'],frame_count=len(frames),views=list(frames),pixel_counts=counts,
                       final_scalar_claims=slot_scalars,specific_blocker_claims=slot_blockers,actual_tools=[x['name'] for x in requests],failures=[c for c in slot_checks if not c['passed']])
ck('84_explicit_pixel_scalar_claims',scalar_count==84)
ck('18_specific_occluder_claims',blocker_count==18)
ck('24_current_frames',total_frames==24)
out=dict(author_commit='52d9a838fd52074f3df157aba97e29a5c0cde924',scope='Independent raw-source rectangle discovery, all24 stored frame pixel arithmetic, six final answers and exact rational blocker witnesses. Full geometric completeness uses previously accepted001 classification matrix; no author scorer or engine imported.',
         checks=checks,check_count=len(checks),failed=[c for c in checks if not c['passed']],answer_quality_passed=sum(all_quality),explicit_pixel_scalars=scalar_count,specific_occluder_claims=blocker_count,
         exact_blocker_witnesses=blockers,targets=list(targets),runs=results,inputs=inputs,new_model_renderer_Blender_calls=0,
         limitations=['No new formal model calls or render tests','Geometric completeness inherited from accepted001 same bytes; specific blocker rays independently recomputed','Six correct answers do not change two original strict execution failures','No claim of generalized complex-scene or visual-semantic performance'])
HERE.mkdir(parents=True,exist_ok=True)
(HERE/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:out[k] for k in ('check_count','failed','answer_quality_passed','explicit_pixel_scalars','specific_occluder_claims')},ensure_ascii=False))
