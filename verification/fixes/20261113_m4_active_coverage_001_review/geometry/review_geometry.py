"""Root independent exact SAT/segment-intersection audit; no formal timing."""
from fractions import Fraction as F
from itertools import combinations, product
from pathlib import Path
import copy
import hashlib
import json
import sys
import types

SRC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_001')
OUT = Path(__file__).resolve().parent
CHECKS, INPUTS = [], {}

def read(rel):
    raw = (SRC / rel).read_bytes()
    INPUTS[rel] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)

def check(name, ok, detail=None):
    CHECKS.append(dict(name=name, passed=bool(ok), detail=detail))

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def det(a,b): return a[0]*b[1]-a[1]*b[0]
def xyz(values): return tuple(map(F,values))
def hull(points):
    points=sorted(set(points))
    if len(points)<3:return points
    def half(ps):
        result=[]
        for p in ps:
            while len(result)>1 and det(sub(result[-1],result[-2]),sub(p,result[-1]))<=0:result.pop()
            result.append(p)
        return result
    return half(points)[:-1]+half(list(reversed(points)))[:-1]

def edges(poly): return list(zip(poly,poly[1:]+poly[:1]))
def area(poly): return abs(sum(det(a,b) for a,b in edges(poly)))/2 if len(poly)>=3 else F(0)
def inside(p,poly): return all(det(sub(b,a),sub(p,a))>=0 for a,b in edges(poly))

def positive_overlap(a,b):
    if area(a)==0 or area(b)==0:return False
    for x,y in edges(a)+edges(b):
        edge=sub(y,x); axis=(-edge[1],edge[0])
        aa=[dot(p,axis) for p in a]; bb=[dot(p,axis) for p in b]
        if max(aa)<=min(bb) or max(bb)<=min(aa):return False
    return True

def intersection_area(a,b):
    points=[p for p in a if inside(p,b)]+[p for p in b if inside(p,a)]
    for p,q in edges(a):
        u=sub(q,p)
        for r,s in edges(b):
            v=sub(s,r); denom=det(u,v)
            if denom==0:continue
            t=det(sub(r,p),v)/denom; w=det(sub(r,p),u)/denom
            if 0<=t<=1 and 0<=w<=1:points.append(tuple(x+t*y for x,y in zip(p,u)))
    return area(hull(points))

def independent_rectangle(obj):
    vs=[xyz(v) for v in obj['vertices']]; fs=obj['triangles']
    if len(vs)!=4 or len(set(vs))!=4 or len(fs)!=2:return None
    if any(len(f)!=3 or len(set(f))!=3 or any(type(i)is not int or not 0<=i<4 for i in f)for f in fs):return None
    normals=[cross(sub(vs[b],vs[a]),sub(vs[c],vs[a])) for a,b,c in fs]
    if not dot(normals[0],normals[0]) or cross(*normals)!=(0,0,0) or dot(*normals)<=0:return None
    first=min(range(4),key=vs.__getitem__)
    opposite=max(range(4),key=lambda i:dot(sub(vs[i],vs[first]),sub(vs[i],vs[first])))
    sides=[i for i in range(4)if i not in(first,opposite)]
    u,v=[sub(vs[i],vs[first])for i in sides]
    if dot(u,v)!=0 or tuple(x+y+z for x,y,z in zip(vs[first],u,v))!=vs[opposite]:return None
    actual={frozenset(f) for f in fs}
    diag1={frozenset((first,sides[0],opposite)),frozenset((first,sides[1],opposite))}
    diag2={frozenset((first,*sides)),frozenset((opposite,*sides))}
    if actual not in(diag1,diag2):return None
    return {'name':obj['name'],'vertices':vs,'normal':normals[0]}

def hsh(v):return hashlib.sha256(json.dumps(v,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def tri_key(v):return min(v[i:]+v[:i]for i in range(3))
def projected(vs,d,z=F(0)):return hull([(v[0]-(v[2]-z)*d[0]/d[2],v[1]-(v[2]-z)*d[1]/d[2])for v in vs])

def fixed_audit():
    scene=read('inputs/SCENE_GEOMETRY_RATIONAL.json'); cameras=read('inputs/CAMERAS.json')
    oracle=read('oracle/ADMIN_ORACLE.json')
    outputs=[read('benchmark/OUTPUT_REFERENCE.json')['semantic'],read('benchmark/OUTPUT_OPTIMIZED.json')['semantic']]
    rects=[]; boxes=[]; triangle_by_hash={}
    for obj in scene['objects']:
        vs=[xyz(v)for v in obj['vertices']]; rect=independent_rectangle(obj)
        for f in obj['triangles']:
            tri=tuple(vs[i]for i in f);triangle_by_hash[hsh(tri_key(tri))]=tri
        if rect is not None:
            rects.append(rect);continue
        bs=[sorted({v[i]for v in vs})for i in range(3)]
        valid=all(len(a)==2 for a in bs)and set(product(*bs))==set(vs)and len(obj['triangles'])==12
        planes={}
        for f in obj['triangles']:
            ff=[vs[i]for i in f]
            fixed=[(i,j)for i in range(3)for j in range(2)if all(v[i]==bs[i][j]for v in ff)]
            valid=valid and len(fixed)==1
            if fixed:planes.setdefault(fixed[0],[]).append(f)
        for fs in planes.values():
            inds=sorted(set(i for f in fs for i in f)); remap={old:i for i,old in enumerate(inds)}
            face={'name':'boxface','vertices':[vs[i]for i in inds],'triangles':[[remap[i]for i in f]for f in fs]}
            valid=valid and independent_rectangle(face)is not None
        valid=valid and len(planes)==6
        check('closed_box_'+obj['name'],valid)
        boxes.append({'name':obj['name'],'vertices':vs})
    check('discovered_targets',len(rects)==6, [r['name']for r in rects])
    check('boxes',len(boxes)==22)
    check('horizontal_positive_front',all(all(v[2]==0 for v in r['vertices'])and r['normal'][2]>0 for r in rects))
    check('all_boxes_strictly_front',all(min(v[2]for v in b['vertices'])>0 for b in boxes))
    check('coplanar_targets_disjoint',all(not positive_overlap(hull([v[:2]for v in a['vertices']]),hull([v[:2]for v in b['vertices']]))for a,b in combinations(rects,2)))
    rows=[];witnesses=[]
    expected={(x['direction'],x['target']):x for x in oracle['matrix']}
    for pose in cameras['views']:
        d=xyz(pose['direction_rational']);check('positive_dz_'+pose['name'],d[2]>0)
        for r in rects:
            rp=hull([v[:2]for v in r['vertices']])
            blocked=[b['name']for b in boxes if positive_overlap(rp,projected(b['vertices'],d))]
            full=not blocked
            ex=expected[(pose['name'],r['name'])]
            check('oracle_SAT_'+pose['name']+'_'+r['name'],full==ex['full_interior_visible'] and set(blocked)=={b['occluder']for b in ex['positive_area_blockers']})
            record={'view':pose['name'],'target':r['name'],'complete':full,'positive_area_blockers':blocked}
            rows.append(record)
            for j,out in enumerate(outputs):
                matched=[reg for reg in out['regions']if {xyz(v)for v in reg['vertices']}==set(r['vertices'])]
                check('candidate_region_'+str(j)+'_'+pose['name']+'_'+r['name'],len(matched)==1)
                if len(matched)!=1:continue
                row=out['classifications'][pose['name']][matched[0]['roi_id']]
                check('candidate_SAT_'+str(j)+'_'+pose['name']+'_'+r['name'],row['complete']==full)
                if row['first_blocker']:
                    witness=row['first_blocker']; tri=triangle_by_hash[witness['triangle_geometry_id']]
                    a=intersection_area(rp,projected(tri,d))
                    u=cross((0,0,1),d)
                    if dot(u,u)==0:u=cross((0,1,0),d)
                    v=cross(d,u);scale=abs(u[0]*v[1]-u[1]*v[0])
                    okay=a>0 and a*scale==F(witness['overlap_area_screen_exact'])
                    check('exact_witness_'+str(j)+'_'+pose['name']+'_'+r['name'],okay)
                    if j==0:witnesses.append({'view':pose['name'],'target':r['name'],'area_world_xy':str(a),'screen_scale':str(scale),'area_screen':str(a*scale),'matches':okay})
    return rows,witnesses

def load_candidate():
    raw=(SRC/'coverage.py').read_bytes();INPUTS['coverage.py']=hashlib.sha256(raw).hexdigest()
    m=types.ModuleType('root_review_active_coverage');m.__file__=str(SRC/'coverage.py');sys.modules[m.__name__]=m
    exec(compile(raw,str(SRC/'coverage.py'),'exec'),m.__dict__)
    return m

def probe_audit():
    m=load_candidate()
    target={'name':'target','vertices':[[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],'triangles':[[0,1,2],[0,2,3]]}
    pose={'name':'SCENE','direction_rational':[0,0,1],'size_px':[512,512],
          'view_matrix':[[1,0,0,0],[0,1,0,0],[0,0,1,-4],[0,0,0,1]],
          'projection_matrix':[['1/4',0,0,0],[0,'1/4',0,0],[0,0,'-1/4',0],[0,0,0,1]]}
    fixtures=[
        ('front_interior',[['-1/2','-1/2',1],['1/2','-1/2',1],[0,'1/2',1]],False),
        ('behind',[['-1/2','-1/2',-1],['1/2','-1/2',-1],[0,'1/2',-1]],True),
        ('cross_plane_front_area',[['-1/2','-1/2',-1],['1/2','-1/2',1],[0,'1/2',1]],False),
        ('front_tangent_only',[[1,-1,1],[2,0,1],[1,1,1]],True),
        ('front_tiny_positive', [['999999999999/1000000000000',-1,1],[2,0,1],['999999999999/1000000000000',1,1]],False),
        ('only_behind_portion_projects_inside',[[0,0,-1],[1,0,0],[2,1,1]],True),
        ('frustum_far_reject',[['-1/2','-1/2',10],['1/2','-1/2',10],[0,'1/2',10]],True),
        ('frustum_crossing_front',[['-1/2','-1/2',3],['1/2','-1/2',10],[0,'1/2',3]],False),
        ('edge_on_occluder',[[-1,0,1],[1,0,1],[0,0,2]],True),
        ('winding_does_not_hide_occluder',[[0,'1/2',1],['1/2','-1/2',1],['-1/2','-1/2',1]],False)]
    # Proper rational rotation with translation, plus identity; cameras transform with it.
    rotations=[[[F(i==j)for j in range(3)]for i in range(3)],
               [[F(3,5),0,F(4,5)],[0,1,0],[F(-4,5),0,F(3,5)]]]
    records=[]
    for label,verts,expected in fixtures:
        for rid,R in enumerate(rotations):
            t=(F(1,7),F(-2,5),F(1,3)) if rid else (0,0,0)
            def move(p):return [str(dot(row,xyz(p))+shift)for row,shift in zip(R,t)]
            a=copy.deepcopy(target);a['vertices']=[move(p)for p in a['vertices']]
            b={'name':'occluder','vertices':[move(p)for p in verts],'triangles':[[0,1,2]]}
            pp=copy.deepcopy(pose);pp['direction_rational']=[str(R[i][2])for i in range(3)]
            pp['view_matrix']=[[str(R[j][i])for j in range(3)]+[str(-sum(R[j][i]*t[j]for j in range(3))-(4 if i==2 else 0))]for i in range(3)]+[[0,0,0,1]]
            scene={'objects':[a,b]}
            answers=[]
            for variant in ('reference','optimized'):
                out=m.build_index(scene,{'views':[pp]},variant)
                answer=out.classifications['SCENE'][out.region_ids[0]]
                okay=len(out.regions)==1 and answer['complete']==expected
                check('probe_'+label+'_rotation'+str(rid)+'_'+variant,okay,answer)
                answers.append(answer)
            check('probe_equal_'+label+'_rotation'+str(rid),answers[0]==answers[1])
            records.append({'label':label,'rotation':rid,'expected_complete':expected,'answers':answers})
    # Invalid rectangle topology and front convention.
    bads=[]
    x=copy.deepcopy(target);x['triangles']=[[0,1,2],[0,3,2]];bads.append(('opposed_winding',x))
    x=copy.deepcopy(target);x['vertices'][2]=[2,1,0];bads.append(('non_rectangle',x))
    x=copy.deepcopy(target);x['triangles']=[[0,1,2],[0,1,2]];bads.append(('duplicate_face',x))
    x=copy.deepcopy(target);x['vertices'][2][2]='1/1000000000000';bads.append(('noncoplanar',x))
    for label,obj in bads:check('reject_'+label,not m.discover_regions({'objects':[obj]}))
    rev=copy.deepcopy(target);rev['triangles']=[f[::-1]for f in rev['triangles']]
    o=m.build_index({'objects':[rev]},{'views':[pose]},'optimized')
    check('reversed_front_back_facing',o.classifications['SCENE'][o.region_ids[0]]['status']=='back_facing')
    return records

def main():
    rows,witnesses=fixed_audit();probes=probe_audit()
    result={'checks':len(CHECKS),'passed':sum(x['passed']for x in CHECKS),'failed':[x for x in CHECKS if not x['passed']],
            'fixed_rows':rows,'first_triangle_witness_areas':witnesses,'probes':probes,'inputs':INPUTS,
            'scope':'Independent projected convex hull SAT and segment intersection area; bounded untimed candidate microcases. No author scorer/oracle imports or benchmark/Blender/model/API.'}
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
    (OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
    print(json.dumps({k:result[k]for k in ('checks','passed','failed')},ensure_ascii=False,default=str))

if __name__=='__main__':main()
