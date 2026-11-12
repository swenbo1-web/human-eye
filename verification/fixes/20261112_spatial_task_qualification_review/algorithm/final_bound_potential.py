"""One static traversal/lower-bound study; exact saved input, not a candidate.

The attained best is taken from diagnostic exhaustive distances. It is an
oracle-informed pruning ceiling, not an implementable seed or timing result.
Projected bounds are supplementary slabs on the existing world BVH; existing
world bounds/ray coordinate definitions are untouched. No product writes.
"""
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import types

OUT=Path(__file__).resolve().parent
ROOT=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
binding=json.loads((OUT/'SOURCE_BINDING.json').read_bytes())
expected={r['path']:r['sha256'] for r in binding['manifest']}
pkg=types.ModuleType('review_final_bound');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
for name in ('surface_proximity','surface_geometry'):
    raw=(OUT/(name+'.py.snapshot')).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==expected['human_eye_plugin/'+name+'.py']
    m=types.ModuleType(pkg.__name__+'.'+name);m.__package__=pkg.__name__
    sys.modules[m.__name__]=m;setattr(pkg,name,m)
    exec(compile(raw,str(OUT/(name+'.py.snapshot')),'exec'),m.__dict__)
e,c=pkg.surface_proximity,pkg.surface_geometry
tree=ast.parse((OUT/'cheap_contact_potential.py').read_text('utf8'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='certificate')
exec(compile(ast.Module(body=[node],type_ignores=[]),'review-only shared certificate','exec'))
e.MAX_TRIANGLE_PAIRS=10**9;c.CLOSED_SOLID_MAX_WORK=10**9
raw=(ROOT/'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==binding['snapshot_sha256']
meshes={x['name']:types.SimpleNamespace(vertices=x['vertices_world'],faces=x['triangles'])
        for x in json.loads(raw)['objects']}
solved={r['candidate']:r['result'] for r in json.loads((OUT/'ADMISSION_DIAGNOSTIC.json').read_bytes())['rows']
        if r['label']=='diagnostic_pre_gate_removed_only' and r['kind']=='surface'}


def projected_bounds(prepared,axes):
    return [[tuple((min(e._dot(p,a) for p in t[0]),max(e._dot(p,a) for p in t[0])) for a in axes)
             for t in side] for side in prepared]


def supplement(node,bounds,memo):
    if node[3] is not None:
        value=tuple((min(bounds[i][k][0] for i in node[3]),max(bounds[i][k][1] for i in node[3])) for k in range(3))
    else:
        a=supplement(node[4],bounds,memo);b=supplement(node[5],bounds,memo)
        value=tuple((min(a[k][0],b[k][0]),max(a[k][1],b[k][1])) for k in range(3))
    memo[id(node)]=value
    return value


rows=[]
for name in ('Peer_000','Competing_001','Near_003'):
    prep_count={};budget=c._ClosedWork(lambda _:None,prep_count,e)
    records,_=e._admit((meshes['Target'],meshes[name]),budget)
    origin,factor,prepared=e._integer_frame(records,budget)
    shells=[c._closed_topology(r[0],r[1],ts,budget) for r,ts in zip(records,prepared)]
    first=prepared[0][0];u=e._sub(first[0][1],first[0][0]);n=first[1];v=e._cross(n,u)
    axes=(u,v,n);norms=[e._dot(a,a) for a in axes]
    assert all(norms)
    assert all(e._dot(axes[i],axes[j])==0 for i in range(3) for j in range(i))
    projection=projected_bounds(prepared,axes)
    key=solved[name]['_exact_distance_sq'];best=Fraction(key[0],key[1])
    best=best*(2**key[2] if key[2]>=0 else Fraction(1,2**-key[2]))*factor*factor
    best_tuple=(best.numerator,best.denominator,None)
    surface=dict(all_pairs=0,final_best_world_aabb_retained=0,also_plane_retained=0,also_projected_slabs_retained=0)
    for i,a in enumerate(prepared[0]):
        for j,b in enumerate(prepared[1]):
            surface['all_pairs']+=1
            if e._aabb_exceeds_best(a[4],b[4],best_tuple):continue
            surface['final_best_world_aabb_retained']+=1
            plane_excluded=False
            for t,other in ((a,b),(b,a)):
                ds=[e._dot(t[1],e._sub(p,t[0][0])) for p in other[0]]
                if all(d>0 for d in ds) or all(d<0 for d in ds):
                    gap=min(abs(d) for d in ds)
                    if Fraction(gap*gap,t[2])>best:plane_excluded=True;break
            surface['also_plane_retained']+=not plane_excluded
            excluded=False
            for pa,pb,norm in zip(projection[0][i],projection[1][j],norms):
                gap=max(pa[0]-pb[1],pb[0]-pa[1],0)
                if Fraction(gap*gap,norm)>best:excluded=True;break
            surface['also_projected_slabs_retained']+=not excluded
    memos=[{},{}]
    for s,proj,memo in zip(shells,projection,memos):supplement(s['root'],proj,memo)
    phases=[]
    for label,li,ri in (('self_target',0,0),('self_candidate',1,1),('cross',0,1)):
        left,right=shells[li],shells[ri];self_pass=li==ri
        stat=dict(node_visits=0,leaf_pair_visits=0,extra_slab_axis_tests=0,passed_boxes=0,
                  plane_tests=0,coplanar_edge_tests=0,remaining_full_intersections=0)
        pending=[(left['root'],right['root'])]
        def separate(pa,pb):
            for a,b in zip(pa,pb):
                stat['extra_slab_axis_tests']+=1
                if a[1]<b[0] or b[1]<a[0]:return True
            return False
        while pending:
            a,b=pending.pop();stat['node_visits']+=1
            if any(a[1][k]<b[0][k] or b[1][k]<a[0][k] for k in range(3)):continue
            if separate(memos[li][id(a)],memos[ri][id(b)]):continue
            if a[3] is not None and b[3] is not None:
                for i in a[3]:
                    for j in b[3]:
                        if a is b and i>=j:continue
                        stat['leaf_pair_visits']+=1
                        ba,bb=left['bounds'][i],right['bounds'][j]
                        if any(ba[1][k]<bb[0][k] or bb[1][k]<ba[0][k] for k in range(3)):continue
                        if separate(projection[li][i],projection[ri][j]):continue
                        stat['passed_boxes']+=1
                        fa,fb=left['faces'][i],right['faces'][j]
                        shared=set(fa)&set(fb) if self_pass else set()
                        cert=certificate(left['triangles'][i],right['triangles'][j],fa,fb,shared,stat)
                        if cert:stat[cert]=stat.get(cert,0)+1
                        else:stat['remaining_full_intersections']+=1
            elif a is b:pending.extend(((a[4],a[4]),(a[4],a[5]),(a[5],a[5])))
            elif b[3] is not None or a[3] is None and a[2]>=b[2]:pending.extend(((a[4],b),(a[5],b)))
            else:pending.extend(((a,b[4]),(a,b[5])))
        phases.append({'phase':label,'counts':stat})
    row={'candidate':name,'scope':'static potential, final best is oracle-informed; not candidate acceptance',
         'surface':surface,'closed_existing_world_tree_with_supplementary_exact_slabs':phases,
         'projection_preparation_dot_count':3*sum(len(t[0]) for side in prepared for t in side),
         'supplemental_node_records':sum(len(m) for m in memos),
         'max_projection_bound_bits':max(abs(value).bit_length() for side in projection for t in side for ax in t for value in ax),
         'original_preparation_work_units':prep_count['work_units']}
    rows.append(row)
    (OUT/'FINAL_BOUND_POTENTIAL.json').write_text(json.dumps({'rows':rows},indent=2),encoding='utf8')
    print(json.dumps(row),flush=True)
