"""Bounded exact node-certificate soundness check on 32 transformed small cases.
Independent existing Fraction edge-plane oracle is loaded without its package.
No G508 strategy change, candidate tuning or performance measurement.
"""
import ast
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
hashes={'surface_proximity':'ef909bed94344408c6ac53a3e40b8fac3886c6ea69d96dbcb2c2a51ce6cdbf98',
        'surface_geometry':'5142952ffb61976e40966bf5a69ef1e2aa25c7dde11de9d4755f7a2c4d71a9d3'}
pkg=types.ModuleType('closed_soundness_fixed');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
for name,digest in hashes.items():
    raw=(OUT/(name+'.py.snapshot')).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
    module=types.ModuleType(pkg.__name__+'.'+name);module.__package__=pkg.__name__
    sys.modules[module.__name__]=module;setattr(pkg,name,module)
    exec(compile(raw,str(OUT/(name+'.py.snapshot')),'exec'),module.__dict__)
e,c=pkg.surface_proximity,pkg.surface_geometry
oracle_path=ROOT/'verification/test_surface_geometry.py'
oracle_bytes=oracle_path.read_bytes();tree=ast.parse(oracle_bytes)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='oracle')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(oracle_path),'exec'))
cases=json.loads((ROOT/'verification/m3_pair_scalability_001/testing/NODE_CASES.json').read_bytes())['cases']
maps=[((1,0,0),(0,1,0),(0,0,1)),((-1,0,0),(0,1,0),(0,0,1)),
      ((1,1,0),(0,1,0),(1,0,1)),((1,0,1),(0,1,0),(0,0,1))]
records=[];positives=0;covered=0
def descend(node):
    return list(node[3]) if node[3] is not None else descend(node[4])+descend(node[5])
def minus(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]
def legal(points,fa,fb,vertices):
    if not points:return True
    shared=set(fa)&set(fb)
    if len(shared)==1:return all(p==vertices[next(iter(shared))] for p in points)
    if len(shared)!=2:return False
    a,b=(vertices[i] for i in sorted(shared));d=minus(b,a);n=sum(v*v for v in d)
    return bool(n) and all(not any(cross(minus(p,a),d)) and 0<=sum(x*y for x,y in zip(minus(p,a),d))<=n for p in points)
for case in cases:
    for index,matrix in enumerate(maps):
        vertices={i:tuple(sum(int(Q(point[j])*4)*row[j] for j in range(3)) for row in matrix)
                  for i,point in enumerate(case['vertices'])}
        faces=case['left']+case['right'];cut=len(case['left'])
        bounds=[(tuple(min(vertices[i][k] for i in f) for k in range(3)),
                 tuple(max(vertices[i][k] for i in f) for k in range(3))) for f in faces]
        budget=c._ClosedWork(lambda _:None,{},e)
        a=c._bvh(bounds,budget,list(range(cut)),leaf_size=1)
        b=c._bvh(bounds,budget,list(range(cut,len(faces))),leaf_size=1)
        root=(tuple(min(a[0][k],b[0][k]) for k in range(3)),tuple(max(a[1][k],b[1][k]) for k in range(3)),len(faces),None,a,b)
        shell={'candidate_vertices':vertices,'candidate_root':root,'faces':faces}
        metadata=c._closed_cone_metadata(shell,budget)
        # Independently check all actual descendant rays are inside and that
        # source-ID boundary sets are complete, including opposite directions.
        nodes=[root]
        while nodes:
            node=nodes.pop()
            if node[3] is None:nodes.extend((node[4],node[5]))
            for anchor,cone in metadata.get(id(node),{}).items():
                ids=descend(node);assert all(anchor in faces[i] for i in ids)
                rays={v:minus(vertices[v][:2],vertices[anchor][:2]) for i in ids for v in faces[i] if v!=anchor}
                cr=lambda x,y:x[0]*y[1]-x[1]*y[0]
                assert cr(cone['lo'],cone['hi'])>0
                assert all(cr(cone['lo'],r)>=0 and cr(r,cone['hi'])>=0 for r in rays.values())
                for raykey,idkey in (('lo','lo_ids'),('hi','hi_ids')):
                    ray=cone[raykey]
                    actual={v for v,r in rays.items() if cr(ray,r)==0 and sum(x*y for x,y in zip(ray,r))>0}
                    assert actual==set(cone[idkey])
        passed=c._closed_node_simplex(a,b,metadata,vertices,budget)
        illegal=[]
        for i in descend(a):
            for j in descend(b):
                pts=oracle(tuple(vertices[v] for v in faces[i]),tuple(vertices[v] for v in faces[j]))
                if not legal(pts,faces[i],faces[j],vertices):illegal.append([i,j])
        if passed:
            positives+=1;covered+=a[2]*b[2];assert not illegal,(case['id'],index,illegal)
        records.append({'case':case['id'],'invertible_transform':index,'certificate':passed,'illegal_pairs':illegal})
out={'scope':'independently rerun transformed small cases, not new implementation or full-domain proof',
     'source_hashes':hashes,'independent_oracle_sha256':hashlib.sha256(oracle_bytes).hexdigest(),
     'cases':len(records),'positive_certificates':positives,'positive_covered_pairs':covered,
     'false_positive_certificates':0,'metadata_containment_and_complete_source_ids':'passed',
     'records':records,'Blender_calls':0,'model_calls':0}
(OUT/'NODE_SOUNDNESS.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in out.items() if k!='records'}),flush=True)
