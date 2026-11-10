"""Read fixed JSON only; own rational checks, no product/oracle execution."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter, defaultdict
import hashlib, json

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001')
O=Path(__file__).resolve().parent
load=lambda p:json.loads((R/p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
g=load('scoring/source/qual001/admin/world_geometry.json')
truth=load('scoring/TRUTH.json')
rows={r['object_id']:r for r in g['objects']}
v={k:[tuple(F(c) for c in p) for p in r['world_vertices']] for k,r in rows.items()}
b={k:[(min(p[i] for p in pts),max(p[i] for p in pts)) for i in range(3)] for k,pts in v.items()}
c={k:tuple((a+z)/2 for a,z in bounds) for k,bounds in b.items()}
levels={k:[sorted({p[i] for p in pts}) for i in range(3)] for k,pts in v.items()}
groups=defaultdict(list)
for k,r in rows.items(): groups[r['data']].append(k)
frames=next(ids for ids in groups.values() if len(ids)==4 and all(list(map(len,levels[k]))==[4,2,4] for k in ids))
rails=next(ids for ids in groups.values() if len(ids)==2 and all(list(map(len,levels[k]))==[2,4,4] for k in ids))
assert len({json.dumps([rows[k]['local_vertices'],rows[k]['triangles']]) for k in frames})==1
beams=[k for k in rows if len(v[k])==8 and list(map(len,levels[k]))==[2,2,2] and b[k][0][1]-b[k][0][0]>=10*max(b[k][i][1]-b[k][i][0] for i in (1,2))]
front=min(beams,key=lambda k:c[k][1])
pipes=[k for k in rows if len(v[k])==24 and len(levels[k][2])==2 and b[k][2][1]-b[k][2][0]>4*max(b[k][i][1]-b[k][i][0] for i in (0,1))]
assert len(beams)==len(pipes)==2
midz=sum(c[k][2] for k in rails)/2
rear=b[front][1][1]
pipexy=tuple(sum(c[k][i] for k in pipes)/2 for i in (0,1))
evaluations={k:[c[k][2]<midz,c[k][1]>rear,sum((c[k][i]-pipexy[i])**2 for i in (0,1))<=F(7,10)**2] for k in frames}
assert evaluations=={r['object_id']:r['three_conditions'] for r in truth['candidate_evaluations']}
assert [k for k,a in evaluations.items() if all(a)]==[truth['target_id']]
assert all(sum(all(a[j] for j in range(3) if j!=i) for a in evaluations.values())==2 for i in range(3))

def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def ontri(p,tri):
 a,z,w=tri;u=sub(z,a);q=sub(w,a);r=sub(p,a);n=cross(u,q)
 if dot(n,r): return False
 uu,vv,uv,ru,rv=dot(u,u),dot(q,q),dot(u,q),dot(r,u),dot(r,q)
 den=uu*vv-uv*uv
 assert den>0
 s,t=vv*ru-uv*rv,uu*rv-uv*ru
 return s>=0 and t>=0 and s+t<=den
def triangles(k): return [[v[k][i] for i in f] for f in rows[k]['triangles']]
def inside(k,p):
 ts=triangles(k)
 assert not any(ontri(p,t) for t in ts)
 for d in [(13,17,23),(29,31,37),(41,43,47)]:
  hits=[];ambiguous=False
  for tri in ts:
   a,z,w=tri;n=cross(sub(z,a),sub(w,a));den=dot(n,d)
   if not den:
    if not dot(n,sub(a,p)): ambiguous=True;break
    continue
   t=dot(n,sub(a,p))/den
   if t<=0: continue
   hit=tuple(p[i]+t*d[i] for i in range(3))
   if ontri(hit,tri):
    if any(dot(cross(sub(e,a0),sub(hit,a0)),cross(sub(e,a0),sub(hit,a0)))==0 for a0,e in zip(tri,tri[1:]+tri[:1])):
     ambiguous=True;break
    hits.append(t)
  if not ambiguous:return bool(len(hits)%2)
 raise AssertionError('all independent rays ambiguous')
for k in ['N16','N13','N08','N28']:
 edge=Counter();direct=Counter()
 for f in rows[k]['triangles']:
  assert len(set(f))==3
  for a,z in zip(f,f[1:]+f[:1]):edge[tuple(sorted((a,z)))]+=1;direct[a,z]+=1
 assert all(n==2 and direct[a,z]==direct[z,a]==1 for (a,z),n in edge.items())
rel={r['neighbor_id']:r for r in truth['relations']}
p=tuple(F(int(q['numerator']),int(q['denominator'])) for q in rel['N13']['strict_interior_witness']['exact'])
assert inside('N16',p) and inside('N13',p)
x,y,z=levels['N16']
# Every original frame triangle is outside at least one side of the infinite
# opening prism; the entire opening is connected to exterior along Y.
assert all(any(all(p[axis]<=bound for p in t) if sign<0 else all(p[axis]>=bound for p in t)
 for axis,bound,sign in [(0,x[1],-1),(0,x[2],1),(2,z[1],-1),(2,z[2],1)]) for t in triangles('N16'))
assert all(x[1]<p[0]<x[2] and z[1]<p[2]<z[2] for p in v['N28'])
gaps={'N08':b['N16'][0][0]-b['N08'][0][1],
 'N28':min(b['N28'][0][0]-x[1],x[2]-b['N28'][0][1],b['N28'][2][0]-z[1],z[2]-b['N28'][2][1])}
for k,gap in gaps.items():
 assert gap>0
 points=[tuple(F(q) for q in p) for p in rel[k]['attaining_original_surface_witness_points_world_m']]
 assert all(any(ontri(p,t) for t in triangles(mesh)) for mesh,p in zip(['N16',k],points))
 assert dot(sub(*points),sub(*points))==gap*gap
 q=rel[k]['minimum_distance_squared_m2']
 assert gap*gap==F(int(q['numerator']),int(q['denominator']))
assert gaps['N08']<F(1,4000)<gaps['N28']
width=b['N16'][0][1]-b['N16'][0][0];height=b['N16'][2][1]-b['N16'][2][0]
short=[k for k in rows if len(v[k])==8 and list(map(len,levels[k]))==[2,2,2]
 and b[k][0][1]-b[k][0][0]<width/2
 and F(3,2)*(b[k][0][1]-b[k][0][0])<b[k][2][1]-b[k][2][0]<height
 and max(b[k][1][0],y[0])<min(b[k][1][1],y[1])
 and z[0]<c[k][2]<z[-1] and abs(c[k][0]-c['N16'][0])<width]
roles={'right':[k for k in short if c[k][0]>c['N16'][0]],
 'left':[k for k in short if c[k][0]<x[0]],
 'through':[k for k in rows if len(v[k])==24 and b[k][1][0]<y[0] and b[k][1][1]>y[1]
 and all(x[1]<p[0]<x[2] and z[1]<p[2]<z[2] for p in v[k])]}
assert roles=={'right':['N13'],'left':['N08'],'through':['N28']}
binding=load('scoring/SOURCE_BINDING.json')
for row in binding['files']:assert sha(R/row['path'])==row['sha256']
inputs=load('scoring/INPUT_BINDING.json')
for f,row in inputs['originals'].items():assert sha(R/'input/original'/f)==row['sha256']
for label in ['prompt','scene','image']:assert sha(R/inputs['inputs'][label])==inputs['inputs'][label+'_sha256']
out={'scope':'own rational arithmetic over frozen world geometry; no original oracle or product functions executed; not a new full general-purpose mesh oracle',
 'target_conditions':evaluations,'each_condition_needed':True,'derived_references':{'rails':rails,'front':front,'pipes':pipes},
 'role_geometric_filter_unique':roles,'role_scope':'Recorded geometry qualifiers matching public short/narrow/adjacent/opening roles; these numeric recognition filters are oracle diagnostics, not new scoring requirements.',
 'strict_common_interior_verified_by_own_ray_parity':True,'N08_positive_AABB_bound_attained_on_original_triangles':float(gaps['N08']),
 'N28_opening_prism_clearance_lower_bound_attained_on_original_triangles':float(gaps['N28']),
 'original_pair_meshes_closed_oriented':True,'private_truth_matches':True,'nine_reference_hashes':True,'seven_original_input_hashes':True,
 'prompt_scene_image_hashes':True,'geometry_sha256':sha(R/'scoring/source/qual001/admin/world_geometry.json'),
 'truth_sha256':sha(R/'scoring/TRUTH.json')}
(O/'INDEPENDENT_MATH_CHECKS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(out,ensure_ascii=False))
