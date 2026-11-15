"""Independent fixed-source review; no author oracle or raster execution."""
import ast
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import types

TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-camera-001/hefe')
NS = TREE / 'verification/m4_target_camera_reliability_001'
INSTALL = Path('D:/he_m4_camera_001/candidate/product')
OUT = Path(__file__).parent
FINAL = '4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
PRODUCT = '691f7b78ed89ccf30df47847fc1e99ad51a1dc64'
BASE = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
pins = {}

def git_source(commit, path):
    data = subprocess.check_output(['git', '-C', str(TREE), 'show', commit+':'+path])
    pins[commit+':'+path] = hashlib.sha256(data).hexdigest()
    return data

def load_camera(commit):
    raw = git_source(commit, 'human_eye_plugin/blender_host.py')
    if commit == FINAL:
        assert raw == git_source(PRODUCT, 'human_eye_plugin/blender_host.py')
        assert raw == (TREE/'human_eye_plugin/blender_host.py').read_bytes()
        assert raw == (INSTALL/'human_eye_plugin/blender_host.py').read_bytes()
    names = {'BlenderHostError','_vector','_dot','_cross','_norm',
             '_observation_affine_interval','_observation_target_cameras'}
    nodes = [n for n in ast.parse(raw.decode('utf8')).body if getattr(n,'name',None) in names]
    assert {n.name for n in nodes} == names
    module = {'math':math}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),commit+':camera','exec'),module)
    return module

old, new = load_camera(BASE), load_camera(FINAL)
inputs_raw = (NS/'INPUTS.json').read_bytes()
assert hashlib.sha256(inputs_raw).hexdigest() == 'c10f7231091db360bf1fdb962ad916fba731df7cd94dfa3c5f5ff88e6cff4004'
inputs = json.loads(inputs_raw)
pins['INPUTS.json'] = hashlib.sha256(inputs_raw).hexdigest()

# Interval oracle: every node includes its exact result and correctly-rounded
# binary64 result. Enumerate all subsets/tree partitions for the four affine
# terms. This covers separate multiply/add, all reduction trees, and omission
# of intermediate rounding (fusion); it does not use a gamma constant.
def round_hull(pair):
    lo,hi = pair
    return min(lo,F(float(lo))), max(hi,F(float(hi)))

def multiply(pair, coefficient):
    a,b = (pair[0]*coefficient,pair[1]*coefficient)
    return round_hull((min(a,b),max(a,b)))

def affine_enclosure(point_intervals, row):
    leaves = [multiply(p,F(c)) for p,c in zip(point_intervals,row[:3])]
    leaves.append((F(row[3]),F(row[3])))
    cache = {1<<i:pair for i,pair in enumerate(leaves)}
    def visit(mask):
        if mask in cache:return cache[mask]
        lows,highs = [],[]
        part=(mask-1)&mask
        while part:
            other=mask^part
            if other and part<other:
                a,b=visit(part),visit(other)
                lo,hi=round_hull((a[0]+b[0],a[1]+b[1]))
                lows.append(lo);highs.append(hi)
            part=(part-1)&mask
        cache[mask]=(min(lows),max(highs))
        return cache[mask]
    return visit(15)

def exact_affine(point,row):
    return sum(F(c)*v for c,v in zip(row[:3],point))+F(row[3])

def verify_returned(cameras,points):
    exact_xy=True; exact_xyz=True; interval_xyz=True
    smallest_margin=F(1); vertex_views=0
    for view in cameras['views']:
        for p in points:
            fp=list(map(F,p)); pi=[(x,x) for x in fp]
            cp=[exact_affine(fp,row) for row in view['view_matrix'][:3]]
            ci=[affine_enclosure(pi,row) for row in view['view_matrix'][:3]]
            projected=[exact_affine(cp,row) for row in view['projection_matrix'][:3]]
            intervals=[affine_enclosure(ci,row) for row in view['projection_matrix'][:3]]
            exact_xy &= all(-1<=x<=1 for x in projected[:2])
            exact_xyz &= all(-1<=x<=1 for x in projected)
            interval_xyz &= all(-1<=lo<=hi<=1 for lo,hi in intervals)
            smallest_margin=min(smallest_margin,*(min(lo+1,1-hi) for lo,hi in intervals))
            vertex_views += 1
    return {'exact_xy_inside':exact_xy,'exact_xyz_inside':exact_xyz,
            'rounding_tree_xyz_inside':interval_xyz,'smallest_interval_margin':str(smallest_margin),
            'vertex_view_checks':vertex_views}

core_raw = git_source(FINAL,'human_eye_plugin/active_observation.py')
assert core_raw == git_source(BASE,'human_eye_plugin/active_observation.py')
core=types.ModuleType('independent_camera_core');sys.modules[core.__name__]=core
exec(compile(core_raw,FINAL+':active_observation','exec'),core.__dict__)
records=[]
for case in inputs['camera_cases']:
    row={'id':case['id']}
    try:
        cameras=new['_observation_target_cameras'](case['world_vertices'],case['world_bounds'])
    except new['BlenderHostError'] as exc:
        assert case['id']=='reachable_binary32' and str(exc)=='active_observation_target_camera_numeric_insufficient'
        row.update(outcome='numeric_insufficient',capability_restored=False)
    else:
        row.update(outcome='accepted',**verify_returned(cameras,case['world_vertices']))
        assert row['rounding_tree_xyz_inside'] and row['exact_xyz_inside']
        if case['check_exact_coverage']:
            objs,tris,ident=core.geometry({'objects':[{'name':case['id'],
                'vertices':case['world_vertices'],'triangles':case['faces']}]})
            scene=core.prepare_scene_from_parsed(objs,tris,ident,cameras,target_object_index=0)
            row['region_count']=len(scene.regions)
            row['complete_views']=[name for name,rs in scene.index.classifications.items()
                if rs and all(r['complete'] for r in rs.values())]
            assert row['region_count']==1 and row['complete_views']
    records.append(row)

# Reproduce only the 384 geometry inputs of the original root probe, using
# the original seed/ranges. No later 64-box loop or new random range/search.
replay_raw=(NS/'PRIOR_384_REPLAY_01.json').read_bytes()
replay=json.loads(replay_raw);pins['PRIOR_384_REPLAY_01.json']=hashlib.sha256(replay_raw).hexdigest()
rng=random.Random(101511); fixed=[]
for magnitude in (0.,1e6,1e8,1e10,1e11,1e12):
    for span in (1.,.01,.001,.0001):
        for rep in range(16):
            off=[magnitude*rng.uniform(-1,1) for _ in range(3)]
            points=[[off[0]+dx*span,off[1]+dy*span,off[2]] for dx,dy in ((-1,-1),(1,-1),(1,1),(-1,1))]
            saved=replay['records'][len(fixed)]
            assert points==saved['points'] and magnitude==saved['magnitude'] and span==saved['span']
            fixed.append((magnitude,points,saved['bounds']))

counts={'accepted':0,'numeric_insufficient':0,'exact_xy_clipped':0,'rounding_tree_xyz_failed':0}
replayed=[]
for i,(magnitude,points,bounds) in enumerate(fixed):
    row={'index':i,'magnitude':magnitude}
    try:cameras=new['_observation_target_cameras'](points,[bounds])
    except new['BlenderHostError'] as exc:
        assert str(exc)=='active_observation_target_camera_numeric_insufficient'
        row['outcome']='numeric_insufficient';counts['numeric_insufficient']+=1
    else:
        row.update(outcome='accepted',**verify_returned(cameras,points));counts['accepted']+=1
        counts['exact_xy_clipped']+=not row['exact_xy_inside']
        counts['rounding_tree_xyz_failed']+=not row['rounding_tree_xyz_inside']
    replayed.append(row)
assert counts=={'accepted':273,'numeric_insufficient':111,'exact_xy_clipped':0,'rounding_tree_xyz_failed':0},counts
result={'scope':'fixed Git AST helper + unchanged exact coverage core; independent exact/rounding-tree oracle',
        'source_pins':pins,'six_cases':records,'prior_384_counts':counts,'prior_384_records':replayed,
        'oracle':'Fraction intervals; all four-term reduction tree partitions; rounding at each node optional; two actual matrix stages',
        'limits':['finite frozen inputs, not general proof or Blender execution','no image or pixel-readability run','does not restore rejected coordinate-domain capability'],
        'new_Blender_rasters_models':0}
(OUT/'NUMERIC_RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({'six_cases':[{k:v for k,v in r.items() if k!='smallest_interval_margin'} for r in records],'prior384':counts}))
