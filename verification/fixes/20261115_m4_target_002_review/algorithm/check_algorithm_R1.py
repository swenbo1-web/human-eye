"""Independent fixed-source numerical review; no Blender, raster or product mutation."""
import ast, copy, hashlib, itertools, json, math, random, subprocess, time
from fractions import Fraction as F
from pathlib import Path

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
OUT=Path(__file__).resolve().parent
SRC=ROOT/'human_eye_plugin/blender_host.py'
FINAL='71a505135ecf202c0e8572fb01bbe21c410342e2'
BASE='4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
raw=SRC.read_bytes()
fixed=subprocess.check_output(['git','show',FINAL+':human_eye_plugin/blender_host.py'],cwd=ROOT)
assert raw==fixed
tree=ast.parse(raw)
names={'_acquisition_bounds','_observation_affine_interval','_observation_outside_xy_viewports'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(nodes)==3
env={'math':math}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SRC),'exec'),env)
outside=env['_observation_outside_xy_viewports']; interval=env['_observation_affine_interval']
bound=env['_acquisition_bounds']
checks=[]
def check(name, value, detail=None):
    checks.append({'name':name,'pass':bool(value),'detail':detail})
    if not value: raise AssertionError(name)
def ast_functions(blob):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(blob).body if isinstance(n,ast.FunctionDef)}
old=ast_functions(subprocess.check_output(['git','show',BASE+':human_eye_plugin/blender_host.py'],cwd=ROOT))
now=ast_functions(raw)
check('camera_ast_unchanged',old['_observation_target_cameras']==now['_observation_target_cameras'])
check('reused_bound_and_interval_unchanged',all(old[n]==now[n] for n in ('_acquisition_bounds','_observation_affine_interval')))

def corners(box): return list(itertools.product(*zip(box[0],box[1])))
def exact_axis(points, pose, axis):
    v=pose['view_matrix'][axis]; p=F(pose['projection_matrix'][axis][axis])
    return [(sum(F(v[k])*F(x[k]) for k in range(3))+F(v[3]))*p for x in points]
def exact_out(box,cameras):
    pts=corners(box)
    return all(any(max(z:=exact_axis(pts,p,a)) < -1 or min(z)>1 for a in (0,1)) for p in cameras['views'])
def sum_variants(terms):
    out=[]
    for a,b,c,d in itertools.permutations(terms):
        out.extend([((a+b)+c)+d,(a+(b+c))+d,(a+b)+(c+d),a+((b+c)+d),a+(b+(c+d))])
    return out

caps={}
for which in ('main','target_only'):
    for version in ('A','B'):
        for i in (1,2,3):
            key=f'{version}{i}_{which}'
            p=Path('D:/he_m4_target_002/formal')/key/'MAIN_CAPTURE_01.json'
            caps[key]=json.loads(p.read_bytes())
geometry=json.loads(Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json').read_bytes())
frozen={m['name']:{'vertices':m['world_vertices_m'],'faces':m['triangles']} for m in geometry['objects']}
ref=caps['B1_main']['observation_target']
cam=ref['camera_plan']; point_checks=0; permutations_checked=0; rounding_enclosures=0
for row in ref['scene_directory']:
    box=row['bounds_world_m']; pts=frozen[row['name']]['vertices']
    check('box_contains_'+row['name'],all(F(box[0][k])<=F(pt[k])<=F(box[1][k]) for pt in pts for k in range(3)))
    point_checks+=len(pts)
    got,tested=outside(box,cam)
    expected=row['object_id'] in ref['excluded_object_ids']
    check('saved_decision_'+row['name'],got==expected,{'excluded':got,'tests':tested})
    check('exact_exclusion_'+row['name'],not got or exact_out(box,cam))
    for pose in cam['views']:
        separated=False
        for axis in (0,1):
            coeff=pose['view_matrix'][axis]; scale=pose['projection_matrix'][axis][axis]
            enclosure=interval(box,coeff[:3],coeff[3])
            lo,hi=math.inf,-math.inf
            for point in corners(box):
                terms=[point[k]*coeff[k] for k in range(3)]+[coeff[3]]
                values=sum_variants(terms)
                permutations_checked+=len(values)
                vmin,vmax=min(values),max(values)
                check('rounding_enclosure',enclosure[0]<=vmin<=vmax<=enclosure[1])
                rounding_enclosures+=1
                lo=min(lo,vmin*scale);hi=max(hi,vmax*scale)
            separated |= hi < -1 or lo > 1
        check('all_orders_separate' if got else 'retained_allowed',not got or separated)

for key,capture in caps.items():
    md=capture['observation_target']; rows=md['scene_directory']; work=md['work']
    mesh_ids=[m['object_id'] for m in capture['meshes']]
    check(key+'_ordered_retained',mesh_ids==md['retained_object_ids']==[r['object_id'] for r in rows if r['object_id'] not in md['excluded_object_ids']])
    check(key+'_target_once',mesh_ids.count(md['target_object_id'])==1)
    check(key+'_source_mapping',all(m['vertices']==frozen[m['name']]['vertices'] and m['faces']==frozen[m['name']]['faces'] for m in capture['meshes']))
    if key.startswith('B'):
        expected=[r['object_id'] for r in rows if r['object_id']!=md['target_object_id'] and outside(r['bounds_world_m'],md['camera_plan'])[0]]
        check(key+'_all_decisions_recomputed',expected==md['excluded_object_ids'])
    check(key+'_work_vertices',work['expanded_vertices']==sum(len(m['vertices']) for m in capture['meshes']))

identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
def cameras(v=None):
    return {'views':[{'name':n,'projection':'orthographic','view_matrix':copy.deepcopy(v or identity),'projection_matrix':copy.deepcopy(identity)} for n in ['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']]}
c=cameras()
cases=[('inside',[[-.5,-.5,0],[.5,.5,1]],False),('touch',[[1,0,0],[2,.5,1]],False),
       ('touch_minus_ulp',[[math.nextafter(1,-math.inf),0,0],[2,.5,1]],False),
       ('touch_plus_ulp',[[math.nextafter(1,math.inf),0,0],[2,.5,1]],False),
       ('strict_outside',[[1.01,0,0],[2,.5,1]],True),('negative_outside',[[-2,0,0],[-1.01,.5,1]],True),
       ('side_crossing',[[-2,-.1,0],[2,.1,0]],False),('unknown',None,False),
       ('nonfinite',[[0,0,0],[math.inf,1,1]],False),('inverted',[[2,0,0],[1,1,1]],False)]
for label,box,expected in cases: check(label,outside(box,c)[0]==expected)
mixed=cameras();mixed['views'][5]['view_matrix'][0][3]=-2
check('only_five_views_exclude',not outside([[1.5,0,0],[2,.1,.1]],mixed)[0])
for label,mutate in [('wrong_count',lambda a:a['views'].pop()),('wrong_order',lambda a:a['views'].reverse()),('sheared_projection',lambda a:a['views'][0]['projection_matrix'][0].__setitem__(1,.1)),('perspective',lambda a:a['views'][0].__setitem__('projection','perspective'))]:
    malformed=copy.deepcopy(c); mutate(malformed)
    check(label,not outside([[2,0,0],[3,.1,.1]],malformed)[0])
large=cameras();large['views'][0]['view_matrix'][0][3]=-2**52
check('large_cancel_on_boundary_retained',not outside([[2**52,0,0],[2**52+1,1,1]],large)[0])

rng=random.Random(727002); random_excluded=0
for i in range(320):
    exp=rng.choice([-80,-10,0,40,100,800]); size=2.**exp
    low=[rng.uniform(-8,8)*size for _ in range(3)]
    high=[x+rng.random()*size for x in low]; box=[low,high]
    v=copy.deepcopy(identity)
    for a in range(3):
        v[a][:3]=[rng.uniform(-2,2) for _ in range(3)]
        v[a][3]=rng.uniform(-4,4)*size
    trial=cameras(v)
    for p in trial['views']: p['projection_matrix'][0][0]=p['projection_matrix'][1][1]=1/size
    result=outside(box,trial)[0]
    random_excluded+=int(result)
    check('seeded_exact_implication',not result or exact_out(box,trial))
    localcorners=corners(box)
    physical=rng.choice([.001,1.,1000.]); computed=bound(localcorners,v,physical)
    if computed is not None:
        for pt in localcorners:
            for a in range(3):
                exact=(sum(F(v[a][k])*F(pt[k]) for k in range(3))+F(v[a][3]))*F(physical)
                actual=(sum(v[a][k]*pt[k] for k in range(3))+v[a][3])*physical
                check('bound_exact_and_capture',F(computed[0][a])<=exact<=F(computed[1][a]) and computed[0][a]<=actual<=computed[1][a])

result={'fixed_git':FINAL,'source_sha256':hashlib.sha256(raw).hexdigest(),'passed':len(checks),'failed':sum(not x['pass'] for x in checks),'frozen_vertices_checked':point_checks,'formal_captures':len(caps),'all_order_float_evaluations':permutations_checked,'enclosure_cases':rounding_enclosures,'random_cases':320,'random_excluded':random_excluded,'new_Blender':0,'new_raster':0,'checks':checks}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
