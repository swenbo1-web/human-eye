"""Verify saved raw coordinates against independent exact fixture construction."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads(path.read_bytes())
def raw_capture(path):
    text=path.read_text(encoding='utf8')
    return json.loads(text.split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
def coefficients(p):
    x,y,z=map(F,p)
    return ((3*x+4*y)/25,(-4*x+3*y)/25,z)
def bounds(vertices):
    return [(min(p[k] for p in vertices),max(p[k] for p in vertices)) for k in range(3)]
def closed(faces):
    edges={}
    for a,b,c in faces:
        for x,y in ((a,b),(b,c),(c,a)):
            key=tuple(sorted((x,y)))
            edges[key]=edges.get(key,0)+1
    return all(count==2 for count in edges.values()),sum(count==1 for count in edges.values())
s=load(ROOT/'author/S/BUILD_READBACK.json')
g=load(ROOT/'author/G/BUILD_READBACK.json')
changed=raw_capture(ROOT/'qualification/S/session/call_4/stdout.txt')
by_name={mesh['name']:mesh for mesh in changed['meshes']}
expected=load(ROOT/'author/S/TRUTH.json')['changed_target_vertices']
assert by_name['Object_01']['vertices']==expected
assert by_name['Object_02']['vertices']==s['Object_02']['vertices']
for name in ('Object_01','Object_02'):
    assert by_name[name]['faces']==s[name]['faces']
    assert closed(s[name]['faces'])==(True,0)
for vertices,t_expected in ((s['Object_01']['vertices'],(F(-1,128),F(1,128))),
                           (s['Object_02']['vertices'],(F(2,128),F(4,128))),
                           (expected,(F(-1,128),F(3,128)))):
    rows=[coefficients(p) for p in vertices]
    assert (min(p[0] for p in rows),max(p[0] for p in rows))==(F(-1,8),F(1,8))
    assert (min(p[1] for p in rows),max(p[1] for p in rows))==t_expected
    assert (min(p[2] for p in rows),max(p[2] for p in rows))==(F(-1,16),F(1,16))
for a in (s['Object_01']['vertices'],expected):
    assert all(max(x[0],y[0])<min(x[1],y[1]) for x,y in zip(bounds(a),bounds(s['Object_02']['vertices'])))
point=[-.078125,.05859375,0]
assert coefficients(point)==(F(0),F(5,256),F(0))
assert F(-1,128)<F(5,256)<F(3,128) and F(2,128)<F(5,256)<F(4,128)
for name,total in (('Object_01',F(0)),('Object_02',F(3,64))):
    assert closed(g[name]['faces'])==(False,4)
    assert all(sum(map(F,p))==total for p in g[name]['vertices'])
paths=['author/S/scene.blend','author/S/qa_patch.json','author/S/TRUTH.json',
       'author/S/BUILD_READBACK.json','author/G/scene.blend','author/G/TRUTH.json',
       'author/G/BUILD_READBACK.json','qualification/S/RAW_READBACK_REPLY.json',
       'qualification/G/RAW_READBACK_REPLY.json','qualification/S/session/call_4/stdout.txt',
       'qualification/S/QA_ADVANCE_RECEIPT.json','qualification/S/RESULT.json','qualification/G/RESULT.json']
rows=[]
for relative in paths:
    path=ROOT/relative
    rows.append(dict(path=relative,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
record=dict(schema='fact-adoption-fixture-provenance-v1',independent_truth_uses_product_solver=False,
    exact_dyadic_coordinates_verified=True,S_changed_raw_capture_matches_exact_patch=True,
    S_both_world_aabbs_overlap=True,S_closed_triangle_edges_verified=True,
    S_shared_interior_point=point,S_plane_distance_initial_m=5/128,
    G_open_boundary_edges_per_mesh=4,G_plane_distance_m=math.sqrt(3)/64,
    raw_readback_cost=2,qualification_observe_cost=3,qualification_qa_update_cost=1,files=rows)
(ROOT/'AUTHOR_PROVENANCE.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(dict(verified=True,files=len(rows))))
