"""Small independent math/publication probe; no Blender/service/test-suite import."""
import ast
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import subprocess
import types

W=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
O=Path(__file__).resolve().parent
C='e077fce38b5951efff8166b3b688d05ffa2ebf04'
hashes={}
def fixed(rel):
    raw=(W/rel).read_bytes()
    expected=subprocess.run(['git','-C',str(W),'show',C+':'+rel],check=True,capture_output=True).stdout
    assert raw==expected,rel
    hashes[rel]=hashlib.sha256(raw).hexdigest()
    return raw
exact=types.ModuleType('independent_review_exact')
raw=fixed('human_eye_plugin/surface_proximity.py')
exec(compile(raw,'fixed_surface_proximity.py','exec'),exact.__dict__)
raw=fixed('human_eye_plugin/surface_geometry.py')
tree=ast.parse(raw)
names={'_closed_in_triangle','_closed_transverse','_closed_transverse_evidence'}
selected=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[])
namespace={}
exec(compile(selected,'fixed_closed_functions.py','exec'),namespace)
for rel in ('human_eye_plugin/task_query.py','human_eye_plugin/live_spatial_mcp.py'):fixed(rel)
budget=types.SimpleNamespace(exact=exact)
A=((0,0,0),(4,0,0),(0,4,0))
B=((1,-1,-1),(1,4,2),(1,4,-1))
segment=((Q(1),Q(2,3),Q(0)),(Q(1),Q(3),Q(0)))
M=(Q(1),Q(11,6),Q(0))
def triangle(points):
    points=tuple(tuple(Q(x) for x in p) for p in points)
    normal=exact._normal(points)
    return points,normal,exact._dot(normal,normal),(),()
ta,tb=triangle(A),triangle(B)
cases=[]
for name,origin,factor,reverse in (
    ('fractional_midpoint',(Q(0),)*3,1,False),
    ('swapped_triangle_order',(Q(0),)*3,1,True),
    ('scaled_local_frame',(Q(512),Q(-256),Q(128)),256,False),
    ('large_translation_point_unknown',(Q(2**40),)*3,1,False)):
    holder={'middle':'old'}
    t1,t2=(tb,ta) if reverse else (ta,tb)
    assert namespace['_closed_transverse'](segment,t1,t2,budget,middle_holder=holder)
    assert holder['middle']==M
    records=[];expected_triangles=[]
    for rawtri in ((B,A) if reverse else (A,B)):
        world=[[float(origin[k]+Q(point[k],factor)) for k in range(3)] for point in rawtri]
        # Decoy triangle zero proves the selected nonzero indices control output.
        vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]+world
        records.append((types.SimpleNamespace(vertices=vertices),[(0,1,2),(3,4,5)],list(range(6))))
        expected_triangles.append(world)
    evidence=namespace['_closed_transverse_evidence'](records,1,1,holder['middle'],origin,factor,exact)
    assert evidence['triangle_indices']==[1,1]
    assert evidence['triangle_vertices_world_m']==expected_triangles
    assert all(math.isfinite(x) for tri in expected_triangles for p in tri for x in p)
    exact_world=tuple(origin[k]+M[k]/factor for k in range(3))
    rounded=tuple(float(x) for x in exact_world)
    error_squared=sum((Q.from_float(x)-q)**2 for x,q in zip(rounded,exact_world))
    allowed=Q.from_float(1e-9)**2
    if name=='large_translation_point_unknown':
        assert error_squared>allowed
        assert evidence['point_world_m'] is None and evidence['point_status']=='unknown'
        assert evidence['point_reason']=='world_point_precision_exceeded'
    else:
        assert error_squared<=allowed
        assert evidence['point_world_m']==list(rounded) and evidence['point_status']=='approximate'
    assert evidence['point_scope']=='boundary_crossing_localization_not_volume_interior_or_penetration_depth'
    json.dumps(evidence,allow_nan=False)
    cases.append({'name':name,'passed':True,'point_status':evidence['point_status'],'exact_world_midpoint':[str(x) for x in exact_world],'squared_rounding_error':str(error_squared)})
for name,points,x,y in (
    ('point_contact_clears_holder',(segment[0],),ta,tb),
    ('parallel_contact_clears_holder',segment,ta,ta)):
    holder={'middle':M}
    assert namespace['_closed_transverse'](points,x,y,budget,middle_holder=holder) is False
    assert holder=={}
    cases.append({'name':name,'passed':True})
result={'status':'pass','product_commit':C,'source_sha256':hashes,'cases':cases,
    'scope':'Executed only fixed-byte exact math module plus three AST-extracted closed helpers. Independent rational analytic midpoint 11/6, no author fixture or oracle imported. No classification-service/Blender/model run.',
    'limitations':'Helper checks complement static control-flow review; they do not independently rerun full closed-shell classification, cache, installed entry or model consumption.'}
O.mkdir(parents=True,exist_ok=True)
dest=O/'PUBLICATION_PROBE.json'
with dest.open('x',encoding='utf-8') as f:f.write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':'pass','cases':len(cases),'report_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}))
