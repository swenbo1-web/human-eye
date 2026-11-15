"""Independent saved-data review; never imports author/product oracle or rerenders."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import json, hashlib, itertools, math, sys
sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

N=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_occluded_scene_transfer_001')
OUT=Path(__file__).parent
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
def check(label, ok):
    checks.append({'check':label,'passed':bool(ok)})
    if not ok: print('FAIL',label)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def clip(poly,dist):
    if not poly:return []
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db=dist(a),dist(b)
        if da>=0:result.append(a)
        if (da<0<db) or (db<0<da):result.append(add(a,mul(sub(b,a),da/(da-db))))
    return result
def area2(poly):return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))) if poly else F(0)
scene=read(N/'inputs/SCENE_GEOMETRY_RATIONAL.json');cameras=read(N/'inputs/CAMERAS.json')
truth=read(N/'admin/TRUTH.json');pixels=read(N/'admin/PIXEL_TRUTH.json');norm=read(N/'admin/NORMALIZED.json')
triangles=[];regions=[];unsupported=[];offset=0
for oi,obj in enumerate(scene['objects']):
    vs=[tuple(F(x) for x in v) for v in obj['vertices']]; ts=obj['triangles']
    ns=[cross(sub(vs[t[1]],vs[t[0]]),sub(vs[t[2]],vs[t[0]])) for t in ts]
    groups=[];remaining=set(range(len(ts)))
    while remaining:
        group={min(remaining)};grow=True
        while grow:
            grow=False
            for b in remaining-group:
                if any(len(set(ts[a])&set(ts[b]))==2 and cross(ns[a],ns[b])==(0,0,0) and dot(ns[a],ns[b])>0 and dot(ns[a],sub(vs[ts[b][0]],vs[ts[a][0]]))==0 for a in group):
                    group.add(b);grow=True
        remaining-=group;groups.append(sorted(group))
    for group in groups:
        ec=Counter(tuple(sorted(e)) for ti in group for e in zip(ts[ti],ts[ti][1:]+ts[ti][:1]))
        boundary=[e for e,c in ec.items() if c==1];adj={}
        for a,b in boundary:adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
        order=[min(adj)]
        while len(order)<len(adj):
            choices=[x for x in adj[order[-1]] if x not in order]
            if not choices:break
            order.append(min(choices))
        q=[vs[i] for i in order];isrect=len(q)==4 and all(dot(sub(q[(i+1)%4],q[i]),sub(q[(i-1)%4],q[i]))==0 for i in range(4))
        if not isrect:
            unsupported.extend(offset+i for i in group);continue
        n=ns[group[0]];center=mul(tuple(sum(v[k] for v in q) for k in range(3)),F(1,4))
        rid=f'object_{oi:02d}_triangles_'+'_'.join(map(str,group))
        regions.append(dict(id=rid,oi=oi,name=obj['name'],local=group,global_ids=[offset+i for i in group],q=q,n=n,c=center))
    for li,t in enumerate(ts):triangles.append(dict(oi=oi,li=li,q=[vs[i] for i in t]))
    offset+=len(ts)
check('source counts',len(regions)==61 and len(triangles)==126 and len(scene['objects'])==12)
check('unsupported full L',unsupported==[122,123,124,125])
byid={r['id']:r for r in regions};bykey={(r['name'],tuple(r['local'])):r for r in regions}
oracle={r['roi_id']:r for r in truth['regions']}
geometric={};shadows={};front={};fullsets={}
camrows=cameras['views'];cammap={c['name']:c for c in camrows}
for r in regions:
    tr=oracle[r['id']]
    check('source corners '+r['id'],{tuple(F(x) for x in v) for v in tr['quad_world_m']}==set(r['q']))
    check('source center '+r['id'],tuple(F(x) for x in tr['center_world_m'])==r['c'])
    check('source facing '+r['id'],cross(tuple(F(x) for x in tr['front_direction_world']),r['n'])==(0,0,0) and dot(tr['front_direction_world'],r['n'])>0)
for cam in camrows:
    name=cam['name'];d=tuple(F(x) for x in cam['direction_rational']);fullsets[name]=set()
    for r in regions:
        n=r['n'];q=r['q'];a=q[0];u=sub(q[1],a);v=sub(q[3],a);nd=dot(n,d)
        front[name,r['id']]=nd>0; oc=[]
        if nd>0:
            for ti,t in enumerate(triangles):
                if ti in r['global_ids']:continue
                h=lambda p:dot(n,sub(p,a))
                if max(map(h,t['q']))<=0:continue
                poly=clip(t['q'],h)
                proj=[sub(p,mul(d,h(p)/nd)) for p in poly]
                uv=[(dot(sub(p,a),u)/dot(u,u),dot(sub(p,a),v)/dot(v,v)) for p in proj]
                for dim in range(2):
                    uv=clip(uv,lambda p,dim=dim:p[dim]);uv=clip(uv,lambda p,dim=dim:1-p[dim])
                if area2(uv)>0:oc.append(ti)
        shadows[name,r['id']]=oc
        # Validate real camera frustum without trusting stored inside flags.
        matrix=np.asarray(cam['projection_matrix'])@np.asarray(cam['view_matrix']);cq=np.asarray([[float(x) for x in p]+[1.] for p in q])@matrix.T
        inside=bool((np.abs(cq[:,:3]/cq[:,3,None])<1).all())
        complete=nd>0 and not oc and inside
        geometric[name,r['id']]=complete
        if complete:fullsets[name].add(r['id'])
        old=oracle[r['id']]['views'][name]
        check('front/complete '+name+' '+r['id'],old['front_facing']==(nd>0) and old['complete']==complete and old['fully_in_view']==inside)
        check('shadows '+name+' '+r['id'],set(oc)=={x['source_triangle_index'] for x in old['shadows']})

mapping=np.full(len(triangles),-2,dtype=np.int32)
for i,r in enumerate(regions):mapping[r['global_ids']]=i
pixelrows={};actualframes={};readsets={}
for frame in pixels['native_frame_descriptors']:
    view=frame['view_name'];npz=np.load(frame['NPZ']);raw=npz['triangle_ids'];col=npz['color'];owners=npz['owners'];labels=np.full(raw.shape,-1,dtype=np.int32);mask=raw>=0;labels[mask]=mapping[raw[mask]]
    check('frame files '+view,sha(frame['NPZ'])==frame['NPZ_sha256'] and sha(frame['PNG'])==frame['PNG_sha256'])
    check('PNG/color '+view,np.array_equal(np.asarray(Image.open(frame['PNG']).convert('RGB')),col))
    check('raw/object owners '+view,np.array_equal(owners[mask],np.asarray([t['oi'] for t in triangles],dtype=np.int32)[raw[mask]]))
    marked=np.zeros(raw.shape,dtype=bool);rgb=col.astype(np.int32)
    edges=(labels[:,1:]!=labels[:,:-1])&(((rgb[:,1:]-rgb[:,:-1])**2).sum(axis=2)>=576);marked[:,1:]|=edges;marked[:,:-1]|=edges
    edges=(labels[1:,:]!=labels[:-1,:])&(((rgb[1:,:]-rgb[:-1,:])**2).sum(axis=2)>=576);marked[1:,:]|=edges;marked[:-1,:]|=edges
    oldrows={x['roi_id']:x for f in pixels['frames'] if f['view_name']==view for x in f['rows']};readsets[view]=set()
    for i,r in enumerate(regions):
        owned=labels==i;ns=int(owned.sum());nb=int((owned&marked).sum());readable=front[view,r['id']] and ns>=16 and nb>=4
        row=dict(surface_pixels=ns,boundary_pixels=nb,readable=readable,complete=geometric[view,r['id']],complete_readable=readable and geometric[view,r['id']])
        check('actual pixels '+view+' '+r['id'],all(oldrows[r['id']][k]==v for k,v in row.items()))
        pixelrows[view,r['id']]=row
        if row['complete_readable']:readsets[view].add(r['id'])
    actualframes[view]={'raw':raw,'arrays':{k:hashlib.sha256(npz[k].tobytes()).hexdigest() for k in npz.files}}
universe=set.union(*readsets.values());remaining=set(byid)-universe
covers=[combo for size in range(1,7) for combo in itertools.combinations(readsets,size) if set.union(*(readsets[k] for k in combo))==universe]
minsize=min(map(len,covers));mincovers=[x for x in covers if len(x)==minsize]
reasons={rid:('no_front_facing_candidate' if not any(front[v,rid] for v in readsets) else 'positive_area_occlusion_all_front_views') for rid in remaining}
check('coverage/unknown/minimum',len(universe)==18 and len(remaining)==43 and minsize==3 and Counter(reasons.values())=={'no_front_facing_candidate':10,'positive_area_occlusion_all_front_views':33})
check('actual coverage vs author',universe==set(pixels['complete_readable_roi_ids']) and remaining==set(pixels['remaining_roi_ids']))
scene_partial=[r for r in universe if pixelrows['SCENE',r]['readable'] and not geometric['SCENE',r]]
check('partial readable distinct from complete',bool(scene_partial))
points=read(N/'inputs/TASK_INPUTS.json')['pixel_samples'];pointids={}
for p in points:
    ti=int(actualframes[p['view_name']]['raw'][p['y'],p['x']]);ri=int(mapping[ti]);pointids[p['id']]=regions[ri]['id']
check('fixed raw pixel ownership',pointids=={'sample_A':'object_01_triangles_2_3','sample_B':'object_00_triangles_10_11'})

def identity(i):
    name=i.get('object_name',i.get('object'))
    if name is None:name=scene['objects'][i['object_index']]['name']
    return bykey[name,tuple(i['source_triangle_indices'])]
def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)
slotresults=[]
for s in norm['slots']:
    sid=s['slot_id'];final=Path(s['raw_answer_path']).read_bytes().decode('utf8');sources={'final':final}
    check(sid+' final hash',sha(s['raw_answer_path'])==s['raw_answer_sha256'])
    for source in s['sources']:
        check(sid+' source hash '+source['id'],sha(source['path'])==source['sha256'])
        sources[source['id']]=Path(source['path']).read_bytes().decode('utf8')
        if source['kind']=='cited_artifact':check(sid+' actual final citation '+source['id'],source['path'].replace('\\','/') in final.replace('\\','/'))
    for item in walk(s):
        if 'source_id' in item and 'excerpt' in item:
            check(sid+' source excerpt',item['excerpt'].replace('\r\n','\n') in sources[item['source_id']].replace('\r\n','\n'))
    check(sid+' finite scope',s['finite_pool_only'] and not s['global_invisibility_overclaim'])
    keys=[identity(p['identity'])['id'] for p in s['panels']]
    check(sid+' exact full inventory',len(keys)==61 and set(keys)==set(byid))
    for p in s['panels']:
        rid=identity(p['identity'])['id'];expected='covered' if rid in universe else 'unknown'
        check(sid+' state '+rid,p['status']==expected)
        if expected=='unknown':check(sid+' reason '+rid,p['reason_code']==reasons[rid])
        else:
            check(sid+' witness exists '+rid,bool(p['views']))
            for witness in p['views']:
                view=witness['view'];row=pixelrows[view,rid]
                check(sid+' complete witness '+rid,row['complete_readable'])
                for field in ['surface_pixels','boundary_pixels']:
                    if field in witness:check(sid+' witness count '+rid+' '+field,row[field]==witness[field])
    check(sid+' exact remaining set',{identity(x)['id'] for x in s['remaining']}==remaining)
    for target in s['pixel_targets']:
        r=identity(target['identity']);check(sid+' pixel identity '+target['id'],r['id']==pointids[target['id']])
        check(sid+' pixel center '+target['id'],tuple(F(x) for x in target['center_world_m'])==r['c'])
        check(sid+' pixel corners '+target['id'],set(tuple(F(x) for x in q) for q in target['quad_world_m'])==set(r['q']))
        n=tuple(F(x) for x in target['front_direction_world']);check(sid+' pixel facing '+target['id'],cross(n,r['n'])==(0,0,0) and dot(n,r['n'])>0)
    for target in s['source_targets']:
        r=identity(target['identity']);check(sid+' source target '+target['id'],target['status']=='unknown' and target['reason_code']==reasons[r['id']])
    slotresults.append({'slot':sid,'core_facts_correct':True,'contradictions':s['contradictions']})
n2=next(x for x in norm['slots'] if x['slot_id']=='N2');f=Path(n2['raw_answer_path']).read_text(encoding='utf8');turned=bykey['TurnedUnit',(6,7)]
dn=dot(turned['n'],tuple(F(x) for x in cammap['SCENE']['direction_rational']))
check('N2 erroneous sentence unretracted', '[6,7]: SCENE/RIGHT/BACK' in f and dn<0)
check('N2 correct candidate set',[v for v in ['SCENE','TOP','LEFT','RIGHT','FRONT','BACK'] if front[v,turned['id']]]==['RIGHT','BACK'])
result={'scope':'Independent rational geometry, actual saved pixels, normalized claim/source and core fact verification. No product/author oracle imported, no raster/model/Blender calls.','checks':checks,'passed':all(c['passed'] for c in checks),'count':len(checks),'geometry':{'supported':len(regions),'triangles':len(triangles),'unsupported':unsupported,'complete_readable':sorted(universe),'remaining_reasons':reasons,'minimum_cover_size':minsize,'minimum_covers':mincovers,'scene_partial_readable':scene_partial,'pixel_targets':pointids,'L_occlusion_source_triangles':sorted({ti for oc in shadows.values() for ti in oc if ti in unsupported})},'slots':slotresults,'N2_scene_dot_unnormalized':str(dn),'inputs':{str(p):sha(p) for p in [N/'admin/TRUTH.json',N/'admin/PIXEL_TRUTH.json',N/'admin/NORMALIZED.json',N/'inputs/SCENE_GEOMETRY_RATIONAL.json']}}
with (OUT/'RESULT.json').open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':result['passed'],'checks':len(checks),'failed':sum(not x['passed'] for x in checks),'minimum_covers':mincovers,'N2_dot':str(dn)}))
