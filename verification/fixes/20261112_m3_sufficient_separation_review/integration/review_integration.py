"""Independent, bounded integration probes; no Blender, model, or product edits."""
from pathlib import Path
import ast, copy, hashlib, json, subprocess, sys, types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe').resolve()
OUT = Path(__file__).resolve().parent
EVIDENCE = '189ecdb84185d96c3ed0d75ca268bc16d6d4999b'
PRODUCT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
EXPECTED = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip() == EVIDENCE
freeze = json.loads((ROOT/'verification/m3_sufficient_separation_001/CANDIDATE_FREEZE.json').read_bytes())
manifest = freeze['manifest']
assert len(manifest) == 137
sources = {row['path']: (ROOT/row['path']).read_bytes() for row in manifest}
assert all(sha(sources[row['path']]) == row['sha256'] for row in manifest)
constants={node.targets[0].id:ast.literal_eval(node.value)
    for node in ast.parse(sources['human_eye_plugin/runtime_identity.py']).body
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
    and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
canonical = sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
    implementation_revision=constants['IMPLEMENTATION_REVISION'],files=manifest),
    sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
assert canonical == EXPECTED, canonical
# Pin the manifest to fixed Git source bytes, not only the working tree receipt.
for row in manifest:
    assert subprocess.check_output(['git','show',PRODUCT+':'+row['path']],cwd=ROOT) == sources[row['path']]
helper_name = 'human_eye_plugin/verified_source_loader.py'
helper = types.ModuleType('_independent_integration_guard')
helper.__file__ = str(ROOT/helper_name)
sys.modules[helper.__name__] = helper
exec(compile(sources[helper_name],helper.__file__,'exec',dont_inherit=True),helper.__dict__)
guard = helper.install(ROOT,manifest,sources=sources,bootstrap_module=helper)

import numpy as np
from unittest.mock import patch
from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import task_query as task, surface_proximity as surface, surface_geometry as closed
from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.scene_cache import SpatialSceneCache

results = {'identity': {'evidence_commit':EVIDENCE,'product_commit':PRODUCT,'source_sha256':canonical,
    'source_count':len(manifest),'all_worktree_bytes_match_product_git':True,
    'execution':'verified-source snapshot; trusted existing dependency Python; no Blender/model'},'checks':[]}

def record(name, **detail):
    results['checks'].append({'name':name,'passed':True,**detail})

def triangle(name,x):
    return {'name':name,'vertices':[[x,0,0],[x,1,0],[x,0,1]],'faces':[[0,1,2]]}

def box(name,low,high,subdivide=False):
    verts=[[x,y,z] for x in (low,high) for y in (low,high) for z in (low,high)]
    faces=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
           [2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
    if subdivide:
        rows=[]
        for a,b,c in faces:
            idx=len(verts);verts.append([sum(verts[i][axis] for i in (a,b,c))/3 for axis in range(3)])
            rows.extend([[a,b,idx],[b,c,idx],[c,a,idx]])
        faces=rows
    return {'name':name,'vertices':verts,'faces':faces}

def validated(items,source='independent-integration-source'):
    meshes=[MeshEntity3D(row['name'],'#'+row['name'],row['name'],np.array(row['vertices'],dtype=float),
        np.array(row['faces'],dtype=int),None,(70,140,210),False,local_axes=np.eye(3),pivot_world=np.zeros(3)).to_dict()
        for row in items]
    return _validated_scene({'revision':'independent-integration-revision','unit':'m',
        'coordinate_frame':'world','source':source,'meshes':meshes})

NEW=['spatial_relation','surface_proximity']
OLD=['closed_solid_relation','surface_proximity']
MIXED=['spatial_relation','surface_proximity','closed_solid_relation']
def evaluate(items,facts=NEW,cache=None,source='independent-integration-source',extra_candidates=(),checkpoint=lambda _:None):
    scene,meshes,fingerprint=validated(items,source)
    query=validate_query({'mode':'task','target':{'name':items[0]['name']},
        'candidates':[{'name':row['name']} for row in items[1:]]+list(extra_candidates),'requested_facts':facts})
    diagnostics={}
    value=task.task_result(scene,meshes,fingerprint,query,cache if cache is not None else SpatialSceneCache(),
        checkpoint,diagnostics=diagnostics)
    return value,diagnostics

a,b=triangle('A',0),triangle('B',1)
new,nw=evaluate([a,b])
mixed,mw=evaluate([a,b],MIXED)
assert new['status']=='observed' and new['schema_version']=='task-query-set-v2'
assert new['pairs'][0]['facts']['spatial_relation']['value']=='separated'
assert new['pairs'][0]['facts']['spatial_relation']['geometry_scope']=='referenced_triangle_unions_and_their_vertex_convex_hulls'
assert new['summary']['distance_m']==1 and new['execution_authority'] is False
assert 'closed_solid_relation' not in new['pairs'][0]['facts']
assert mixed['status']=='partial' and mixed['summary']['nearest_separated_complete'] is True
assert mixed['pairs'][0]['facts']['closed_solid_relation']['status']=='unknown'
assert mixed['pairs'][0]['facts']['closed_solid_relation']['reason']=='closed_solid_too_few_faces'
record('open-triangle support never promotes embedded closed health',new=new,mixed=mixed)

unknown,uw=evaluate([a,b],extra_candidates=[{'name':'Missing'}])
assert unknown['status']=='partial' and unknown['summary']['nearest_separated_complete'] is False
assert unknown['summary']['nearest_separated_ids'] is None and unknown['summary']['distance_m'] is None
assert unknown['summary']['best_known_separated_ids']==['B'] and unknown['summary']['best_known_distance_m']==1
record('unknown candidate prevents complete nearest set',value=unknown)

cache=SpatialSceneCache()
cold,cw=evaluate([a,b],MIXED,cache)
warm,ww=evaluate([a,b],MIXED,cache)
assert cold==warm and cw['spatial_pair_count']==1 and ww['spatial_pair_count']==0
assert ww['closed_solid_pair_count']==1 # Unknown closed result must be retried, not promoted/cached.
legacy,lw=evaluate([a,b],OLD,cache)
assert legacy['schema_version']=='task-query-set-v1' and legacy['status']=='partial'
assert lw['closed_solid_pair_count']==1 and lw['surface_pair_count']==1
changed_source,sw=evaluate([a,b],NEW,cache,source='independent-source-edited')
assert sw['spatial_pair_count']==1
changed_geometry,gw=evaluate([a,triangle('B',2)],NEW,cache)
assert gw['spatial_pair_count']==1 and changed_geometry['summary']['distance_m']==2
record('warm mixed unknown retry, old version isolation, source and geometry invalidation',
    cold_work=cw,warm_work=ww,legacy_work=lw,changed_source_work=sw,changed_geometry_work=gw)

class Cancelled(Exception): pass
def cancel_at(stage):
    def checkpoint(current):
        if current==stage: raise Cancelled(stage)
    return checkpoint
cancel_cache=SpatialSceneCache()
try: evaluate([a,b],NEW,cancel_cache,checkpoint=cancel_at('spatial_relation_complete'))
except Cancelled: pass
else: raise AssertionError('cancellation swallowed')
retry,rw=evaluate([a,b],NEW,cancel_cache)
assert rw['spatial_pair_count']==1 # Aborted result was not memoized.
try: evaluate([a,b],NEW,cancel_cache,checkpoint=cancel_at('after_spatial_pair_measurement'))
except Cancelled: pass
else: raise AssertionError('warm-hit cancellation swallowed')
record('cold and warm cancellation propagate; aborted computation not cached',retry_work=rw)

left,right=box('outer',0,4,True),box('inner',1,2,True)
_,meshes,_=validated([left,right])
holder={};sd={}
surface_result=surface.measure_surface_proximity(*meshes,lambda _:None,diagnostics=sd,_prepared_holder=holder)
assert surface_result['measurement_valid'] and 'trees' in holder
pair,trees=holder['pair'],holder['trees']
cd={}
reuse=closed.classify_closed_solids(*meshes,lambda _:None,diagnostics=cd,prepared_pair=pair,prepared_trees=trees)
fresh_work={};fresh=closed.classify_closed_solids(*meshes,lambda _:None,diagnostics=fresh_work)
assert reuse['measurement_valid'] and reuse['relation']=='penetrating'
assert {k:v for k,v in reuse.items() if k!='work'} == {k:v for k,v in fresh.items() if k!='work'}
assert cd['prepared_pair_reused'] is True and cd['prepared_trees_reused'] is True
# A same-valued but freshly normalized pair cannot inherit another pair's prepared trees.
_,other_meshes,_=validated([left,right])
other_work={}
other=closed.classify_closed_solids(*other_meshes,lambda _:None,diagnostics=other_work,
    prepared_pair=pair,prepared_trees=trees)
assert other['relation']==reuse['relation'] and not other_work['prepared_pair_reused']
assert not other_work['prepared_trees_reused']
record('query-local trees reuse only exact prepared-pair identities; containment answer unchanged',
    reuse_work=cd,fresh_work=fresh_work,new_identity_work=other_work,relation=reuse['relation'])

with patch.object(closed,'classify_closed_solids',wraps=closed.classify_closed_solids) as calls:
    fallback,fw=evaluate([left,right],MIXED)
assert calls.call_count==1 and fw['closed_solid_pair_count']==1
assert fallback['status']=='observed' and fallback['summary']['penetrating_ids']==['inner']
assert fallback['pairs'][0]['facts']['spatial_relation']['geometry_scope']==closed.CLOSED_SOLID_SCOPE
assert fallback['pairs'][0]['separation_gap']['status']=='not_applicable'
record('mixed fallback executes original closed exactly once and publishes its actual scope',value=fallback,work=fw)

valid=[];rejected=[]
for requested in (OLD,NEW,MIXED,NEW+['aabb']):
    query={'mode':'task','target':{'name':'A'},'candidates':[{'name':'B'}],'requested_facts':requested}
    mcp._validate_arguments('human_eye_scene_observe',{'query':query,'include_image':False})
    valid.append(validate_query(query))
for requested in (['spatial_relation'],['surface_proximity'],['spatial_relation','surface_proximity','spatial_relation']):
    query={'mode':'task','target':{'name':'A'},'candidates':[{'name':'B'}],'requested_facts':requested}
    try: validate_query(query)
    except ValueError: rejected.append(requested)
    else: raise AssertionError('invalid set accepted')
assert len(rejected)==3
compact=mcp._spatial_task_query({'target':{'name':'A'},'candidates':[{'name':'B'}]})
assert compact['requested_facts']==OLD
record('runtime explicit fact acceptance and compact unchanged old-contract mapping',accepted=valid,rejected=rejected,compact=compact,
    full_json_schema_engine='not run; runtime acceptance and declared schema reviewed separately')

guard.verify_loaded()
results['identity']['executed_engine_modules']=len(guard._executed)
results['checks_passed']=len(results['checks'])
results['status']='passed'
(OUT/'RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'status':results['status'],'checks_passed':len(results['checks']),
    'source_count':len(manifest),'source_sha256':canonical,'executed_engine_modules':len(guard._executed)},sort_keys=True))
