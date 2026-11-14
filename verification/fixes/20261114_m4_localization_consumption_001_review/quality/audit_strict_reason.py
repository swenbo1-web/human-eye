"""Independent raw-answer, exact source geometry and current-frame audit."""
from pathlib import Path
from fractions import Fraction as F
from collections import defaultdict, Counter
import hashlib,json,io,time
import numpy as np
from PIL import Image
R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_region_localization_consumption_001'; O=Path(__file__).parent
SLOTS=('N1','P1','P2','N2','N3','P3'); inputs={}; checks=[]
def raw(p):
 p=Path(p);b=p.read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def js(p):return json.loads(raw(p))
def ck(n,v,d=None):checks.append(dict(name=n,passed=bool(v),detail=d))
def vec(x):return tuple(F(a) for a in x)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def canon(q):
 i=min(range(4),key=lambda i:q[i]);return q[i:]+q[:i]
scene=js(H/'inputs/SCENE_GEOMETRY_RATIONAL.json'); camera=js(H/'inputs/CAMERAS.json')
source_manifest=js(H/'inputs/SOURCES.json')
for key in ('scene','cameras','capture'):
 p=H/'inputs'/source_manifest[key]['file'];ck('input_source_hash:'+key,hashlib.sha256(raw(p)).hexdigest()==source_manifest[key]['sha256'])
obj=scene['objects'][0]; V=list(map(vec,obj['vertices'])); faces=obj['triangles']; cameras=camera['views']
ck('one_mesh',len(scene['objects'])==1);ck('source_size',len(V)==1913 and len(faces)==3337)
old=js(R/'verification/m4_active_observation_patch_ownership_001/inputs/JOINED.json')['objects'][0]
ck('same_old_source',V==list(map(vec,old['vertices'])) and faces==old['triangles'])
planes=[];normals=[];edges=defaultdict(list)
for i,f in enumerate(faces):
 a,b,c=(V[x] for x in f);n=cross(sub(b,a),sub(c,a));axis=[j for j,x in enumerate(n) if x]
 ck(f'axis:{i}',len(axis)==1);planes.append((axis[0],a[axis[0]]));normals.append(n)
 for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))].append(i)
adj=[set() for _ in faces]
for items in edges.values():
 for a in items:
  for b in items:
   if a!=b and planes[a]==planes[b]:adj[a].add(b)
groups=[];seen=set()
for start in range(len(faces)):
 if start in seen:continue
 todo=[start];seen.add(start);comp=[]
 while todo:
  a=todo.pop();comp.append(a)
  for b in adj[a]-seen:seen.add(b);todo.append(b)
 groups.append(sorted(comp))
regions=[];unsupported=[]
for ids in groups:
 if len(ids)==1:unsupported+=ids;continue
 axis,plane=planes[ids[0]];points={V[x] for i in ids for x in faces[i]};lo=tuple(min(p[j] for p in points) for j in range(3));hi=tuple(max(p[j] for p in points) for j in range(3))
 a,b=((1,2),(2,0),(0,1))[axis];q=[]
 for u,v in [(lo[a],lo[b]),(hi[a],lo[b]),(hi[a],hi[b]),(lo[a],hi[b])]:
  p=list(lo);p[a]=u;p[b]=v;q.append(tuple(p))
 if normals[ids[0]][axis]<0:q.reverse()
 q=canon(q);n=cross(sub(q[1],q[0]),sub(q[3],q[0]))
 ck(f'quad_corners:{ids[0]}',set(q)<=points)
 ck(f'quad_area:{ids[0]}',sum(normals[i][axis] for i in ids)==2*n[axis] and all(normals[i][axis]*n[axis]>0 for i in ids))
 cnt=Counter(tuple(sorted((a,b))) for i in ids for a,b in zip(faces[i],faces[i][1:]+faces[i][:1]))
 ck(f'quad_boundary:{ids[0]}',all((V[x][a]==V[y][a] and V[x][a] in (lo[a],hi[a])) or (V[x][b]==V[y][b] and V[x][b] in (lo[b],hi[b])) for (x,y),c in cnt.items() if c==1))
 regions.append(dict(ids=ids,q=q,normal=n,axis=axis,plane=plane,center=tuple((x+y)/2 for x,y in zip(lo,hi)),lo=lo,hi=hi))
ck('138_regions',len(regions)==138);ck('unsupported48',unsupported==[48])
by_ids={tuple(r['ids']):i for i,r in enumerate(regions)};by_quad={frozenset(r['q']):i for i,r in enumerate(regions)}
def clip(poly,dist):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  da,db=dist(a),dist(b)
  if da>=0:out.append(a)
  if (da<0<db) or (db<0<da):
   t=da/(da-db);out.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
 return out
def positive(poly):return len(poly)>=3 and sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))!=0
polys=[r['q'] for r in regions]+[[V[i] for i in faces[48]]];geo={};facing={}
vertices64=np.asarray([[float(x) for x in p] for p in V]);hom=np.c_[vertices64,np.ones(len(V))]
for cam in cameras:
 view=cam['name'];D=vec(cam['direction_rational']);geo[view]={};facing[view]={}
 ndc=hom@np.asarray(cam['view_matrix']).T@np.asarray(cam['projection_matrix']).T
 ck('full_frustum:'+view,np.all(np.abs(ndc[:,:3])<ndc[:,3,None]))
 for ri,r in enumerate(regions):
  front=dot(r['normal'],D)>0;facing[view][ri]=front
  if not front:geo[view][ri]='back_or_edge';continue
  ax=r['axis'];other=[j for j in range(3) if j!=ax];pl=r['plane'];den=D[ax];blocked=False
  for pi,poly in enumerate(polys):
   if pi==ri:continue
   ds=[(p[ax]-pl)/den for p in poly]
   if max(ds)<=0:continue
   ps=clip(poly,lambda p:(p[ax]-pl)/den) if min(ds)<0 else poly
   ps=[tuple(p[j]-D[j]*(p[ax]-pl)/den for j in other) for p in ps]
   if any(max(p[k] for p in ps)<r['lo'][j] or min(p[k] for p in ps)>r['hi'][j] for k,j in enumerate(other)):continue
   for k,j in enumerate(other):
    ps=clip(ps,lambda p,k=k,j=j:p[k]-r['lo'][j]);ps=clip(ps,lambda p,k=k,j=j:r['hi'][j]-p[k])
   if positive(ps):blocked=True;break
  geo[view][ri]='occluded' if blocked else 'complete'
lookup=np.full(len(faces),-2,dtype=np.int32)
for i,r in enumerate(regions):lookup[r['ids']]=i
def parse_table(slot,num):
 p=Path(f'D:/he_loc_001/formal/{slot}/o/tool_{num:02d}/RESPONSE.json');j=js(p);t='\n'.join(x['text'] for x in j['result']['content'] if x['type']=='text');s=json.loads(t)['stdout']
 if slot=='N2':return json.loads(s)['rows']
 return json.JSONDecoder().raw_decode(s[s.index('[['):])[0]
layouts={'N1':[8],'P1':[7],'P2':[8],'N2':[8],'N3':[8,9]};slots=[]
for slot in SLOTS:
 base=Path(f'D:/he_loc_001/formal/{slot}');obs=js(base/'o/OBSERVATIONS.json');final=raw(base/'c/PUBLIC_FINAL.txt').decode();frame_data={}
 ck(slot+':six_frames',len(obs['frames'])==6);ck(slot+':no_product',obs['active']==[])
 for frame in obs['frames']:
  view=frame['view_name'];arr=np.load(io.BytesIO(raw(frame['NPZ'])),allow_pickle=False);color=arr['color'];dep=arr['depth'];ids=arr['triangle_ids'];owners=arr['owners']
  ck(slot+':frame_source:'+view,frame['source_scene_sha256']==source_manifest['scene']['sha256'] and frame['source_capture_sha256']==source_manifest['capture']['sha256'] and frame['pose']==next(c for c in cameras if c['name']==view) and Path(frame['owner_output'])==base/'o')
  ck(slot+':PNG:'+view,np.array_equal(np.asarray(Image.open(io.BytesIO(raw(frame['PNG']))).convert('RGB')),color))
  ck(slot+':primitive_ids:'+view,ids.min()>=-1 and ids.max()<len(faces));ck(slot+':depth:'+view,np.array_equal(np.isfinite(dep),ids>=0) and np.all(dep[ids>=0]>0));ck(slot+':object_owner:'+view,np.array_equal(owners,np.where(ids>=0,0,-1)))
  for name,value in [('color',color),('depth',dep),('triangle_ids',ids),('owners',owners)]:ck(slot+':array_hash:'+view+':'+name,hashlib.sha256(value.tobytes()).hexdigest()==frame['arrays'][name]['sha256'])
  mapped=np.full(ids.shape,-1,dtype=np.int32);mapped[ids>=0]=lookup[ids[ids>=0]];boundary=np.zeros(ids.shape,dtype=bool);c=color.astype(np.int32)
  h=(mapped[:,:-1]!=mapped[:,1:])&(np.sum((c[:,:-1]-c[:,1:])**2,axis=2)>=576);boundary[:,:-1]|=h;boundary[:,1:]|=h
  v=(mapped[:-1]!=mapped[1:])&(np.sum((c[:-1]-c[1:])**2,axis=2)>=576);boundary[:-1]|=v;boundary[1:]|=v
  counts=np.bincount(mapped[mapped>=0],minlength=138);bc=np.bincount(mapped[(mapped>=0)&boundary],minlength=138)
  ready={i for i in range(138) if geo[view][i]=='complete' and counts[i]>=16 and bc[i]>=4}
  frame_data[view]=dict(counts=counts,bc=bc,ready=ready,mapped=mapped,ref=frame['ref'],ids=ids)
 expected=set.union(*(f['ready'] for f in frame_data.values()));ck(slot+':reachable115',len(expected)==115)
 table=[]
 if slot=='P3':
  artifact=js(base/'o/scratch/scene_inspection.json');ck(slot+':artifact_cited','scene_inspection.json' in final)
  for row in artifact['surfaces']:
   ri=by_ids[tuple(row['source_triangle_indices'])];items=[]
   ck(slot+':corners:'+str(ri),set(map(vec,row['world_corners_rational']))==set(regions[ri]['q']))
   for view,e in row['evidence_by_view'].items():
    fd=frame_data[view];ck(slot+':allview:'+str(ri)+view,e['surface_pixels']==int(fd['counts'][ri]) and e['boundary_pixels']==int(fd['bc'][ri]) and e['front_facing']==facing[view][ri] and e['complete']==(geo[view][ri]=='complete') and e['readable']==(ri in fd['ready']) and e['image_ref']==fd['ref'])
    if e['sample_pixel_xy'] is not None:
     x,y=e['sample_pixel_xy'];ck(slot+':sample:'+str(ri)+view,fd['mapped'][y,x]==ri)
   for view in row['readable_views']:items.append((view,row['evidence_by_view'][view]['image_ref']))
   table.append((ri,row['status']=='observed',items,row['reason']))
 else:
  for num in layouts[slot]:
   for row in parse_table(slot,num):
    if slot=='N1':ids=tuple(i for a,b in row[1] for i in range(a,b+1));at=2
    elif slot in ('N2','P1'):
     x=row[1][-2:];ids=tuple(range(x[0],x[1]+1));at=2
    elif slot=='P2':ids=tuple(range(row[1],row[2]+1));at=3
    else:
     source=row[1];ids=tuple(source['triangles']) if 'triangles' in source else tuple(regions[by_quad[frozenset(map(vec,source['corners']))]]['ids']);at=2
     if 'triangle_count' in source:ck(slot+':stated_triangle_count:'+str(row[0]),source['triangle_count']==len(ids))
    ri=by_ids[ids];covered=row[at]=='observed';items=[(row[at+1],row[at+2])] if covered else []
    if covered:
     fd=frame_data[row[at+1]];ck(slot+':reported_counts:'+str(ri),row[at+3]==int(fd['counts'][ri]) and row[at+4]==int(fd['bc'][ri]))
     if len(row)>at+5 and isinstance(row[at+5],list):
      x,y=row[at+5];ck(slot+':table_sample:'+str(ri),fd['mapped'][y,x]==ri)
    table.append((ri,covered,items,None if covered else row[at:]))
 got=set()
 for ri,covered,items,reason in table:
  ck(slot+':unique:'+str(ri),ri not in got);got.add(ri);ck(slot+':status:'+str(ri),covered==(ri in expected))
  if not covered:
   rt=str(reason).lower();back=all(not facing[c['name']][ri] for c in cameras)
   ck(slot+':remaining_reason:'+str(ri),('back' in rt or 'remaining-b' in rt) if back else ('occlu' in rt or 'remaining-o' in rt))
   ck(slot+':remaining_geometry:'+str(ri),back or all(geo[c['name']][ri]=='occluded' for c in cameras))
  for view,ref in items:ck(slot+':evidence:'+str(ri)+view,ri in frame_data[view]['ready'] and ref==frame_data[view]['ref'])
 ck(slot+':all_regions',got==set(range(138)))
 ck(slot+':final_counts',all(x in final for x in ('138','115','23','48')) or (slot=='P3' and '22' in final and 'surface 93' in final))
 # Final position claims manually read; check the concrete numbers against source and actual pixels.
 ri=int(frame_data['SCENE']['mapped'][247,109]);front=regions[ri]
 ck(slot+':click_world',front['center']==vec([.15625,-.15625,.11865234375]) and front['normal'][2]>0 and sub(front['hi'],front['lo'])==vec([.0703125,.0703125,0]))
 ck(slot+':click_claim','0.15625,-0.15625,0.11865234375' in final.replace(' ','') and '+Z' in final and 'image-01' in final)
 origin=next(i for i,r in enumerate(regions) if r['center']==(0,0,0) and r['normal'][2]>0)
 xy=[327,415] if slot in ('P1','P2') else [327,427]
 ck(slot+':origin_visible',int(frame_data['SCENE']['counts'][origin])==0 and geo['SCENE'][origin]=='occluded' and facing['SCENE'][origin] and origin in frame_data['LEFT']['ready'] and frame_data['LEFT']['mapped'][xy[1],xy[0]]==origin)
 ck(slot+':origin_claim',str(xy).replace(' ','') in final.replace(' ','') and 'image-03' in final and 'occlu' in final.lower())
 bottom=next(i for i,r in enumerate(regions) if r['center']==vec([.15625,-.15625,.11572265625]) and r['normal'][2]<0)
 ck(slot+':bottom',all(not facing[c['name']][bottom] for c in cameras) and bottom not in expected)
 ck(slot+':bottom_claim','0.11572265625' in final and ('finite' in final.lower() or 'six registered' in final.lower()))
 slots.append(dict(slot=slot,regions=len(got),covered=len(expected),unobserved=len(got-expected),frames=len(frame_data),table_rows=len(table),final_sha256=inputs[str(base/'c/PUBLIC_FINAL.txt')]))
if True:
 correction=raw(Path('D:/he_loc_001/formal/P2/o/tool_09/RESPONSE.json')).decode()
 ck('P2_correction_explicit','1717..2228 inclusive' in correction and '1209..1720 was erroneous' in correction)
 ck('P2_actual_corrected_source',regions[93]['ids']==list(range(1717,2229)))
for p,h in list(inputs.items()):ck('input_stable:'+p,hashlib.sha256(Path(p).read_bytes()).hexdigest()==h)
result=dict(passed=all(c['passed'] for c in checks),checks=len(checks),failures=[c for c in checks if not c['passed']],slots=slots,geometry_method='Exact source-edge connectivity, axis plane/area rectangle proof and Fraction planar shadow clipping; no product or author oracle.',quality_scope='All 828 supported rows, all 36 current frame pixels/counts, 18 explicit position answers; source/derived claims and final prose separately reviewed.',inputs=inputs,new_product_model_Blender_raster_benchmark_calls=0)
(O/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(O/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='inputs'},ensure_ascii=False))
