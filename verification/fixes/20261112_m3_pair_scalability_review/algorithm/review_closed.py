"""Fixed-source closed review: one bounded original prefix, static fan audit.
No gate changes, candidate modifications, Blender, model or installed process.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time
import types

ROOT=Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
FIX=ROOT/'verification/m3_pair_scalability_001'
freeze=json.loads((FIX/'CANDIDATE_FREEZE.json').read_bytes())
ready=json.loads((FIX/'installation/READY.json').read_bytes())
assert freeze['source_sha256']=='0770602e875c819dd424639fd7c750aaad4bca3bbe506aaf747ba337e5991139'
assert ready['commit']=='3beb3f809674658b086e50af194adaa16e226111'
manifest=freeze['manifest'];assert len(manifest)==137
for item in manifest:
    raw=(ROOT/item['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==item['sha256'],item['path']
    assert raw==(Path(ready['install_root'])/item['path']).read_bytes(),item['path']
pkg=types.ModuleType('fixed_closed_review');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
for name in ('surface_proximity','surface_geometry'):
    raw=(ROOT/f'human_eye_plugin/{name}.py').read_bytes()
    (OUT/(name+'.py.snapshot')).write_bytes(raw)
    module=types.ModuleType(pkg.__name__+'.'+name);module.__package__=pkg.__name__
    sys.modules[module.__name__]=module;setattr(pkg,name,module)
    exec(compile(raw,str(OUT/(name+'.py.snapshot')),'exec'),module.__dict__)
e,c=pkg.surface_proximity,pkg.surface_geometry
snapshot_path=ROOT/'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json'
snapshot_bytes=snapshot_path.read_bytes()
assert hashlib.sha256(snapshot_bytes).hexdigest()=='29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c'
raws={x['name']:x for x in json.loads(snapshot_bytes)['objects']}
meshes={name:types.SimpleNamespace(vertices=r['vertices_world'],faces=r['triangles']) for name,r in raws.items()}
phase=['preparation'];charges=Counter();phase_charges=Counter();captures={};rejected=[]
original_consume=c._ClosedWork.consume
def consume(self,amount,stage):
    try:original_consume(self,amount,stage)
    except Exception as error:
        rejected.append({'phase':phase[-1],'stage':stage,'amount':amount,'error':str(error)})
        raise
    charges[stage]+=amount;phase_charges[phase[-1]]+=amount
c._ClosedWork.consume=consume
original_validate=c._closed_validate_embedded
def validate(shell,budget):
    label='self_'+str(len(captures))
    captures[label]={'shell':shell};phase.append(label)
    try:return original_validate(shell,budget)
    finally:phase.pop()
c._closed_validate_embedded=validate
original_metadata=c._closed_cone_metadata
def metadata(shell,budget):
    phase.append('metadata_'+str(len(captures)-1))
    try:result=original_metadata(shell,budget)
    finally:phase.pop()
    captures['self_'+str(len(captures)-1)]['metadata']=result
    return result
c._closed_cone_metadata=metadata
began=time.perf_counter();checkpoints=Counter()
def checkpoint(stage):
    checkpoints[stage]+=1
    if time.perf_counter()-began>30:raise TimeoutError('review-only 30 second ceiling')
diag={};holder={}
result=c.classify_closed_solids(meshes['Target'],meshes['Peer_000'],checkpoint,
                                diagnostics=diag,prepared_holder=holder)
assert sum(charges.values())==diag['work_units']==262144
assert result['reason']=='closed_solid_work_budget'
out={'source_sha256':freeze['source_sha256'],'verified_source_and_installed_files':137,
     'scope':'one fixed original bounded prefix; no product changes or cap override',
     'result':result,'charges_by_stage':dict(charges.most_common()),
     'charges_by_phase':dict(phase_charges),'rejected_charge':rejected,
     'instrumented_elapsed_ms_not_benchmark':(time.perf_counter()-began)*1000,
     'holder_has_pair':'pair' in holder,'holder_has_trees':'trees' in holder,
     'Blender_calls':0,'model_calls':0,'product_writes':0}
(OUT/'PREFIX_ACCOUNTING.json').write_text(json.dumps(out,indent=2),encoding='utf8')

shell=captures['self_0']['shell'];meta=captures['self_0']['metadata']
faces=shell['faces'];nodes=[]
def visit(node,parent=None):
    ids=list(node[3]) if node[3] is not None else visit(node[4],node)+visit(node[5],node)
    common=set(faces[ids[0]])
    for i in ids[1:]:common.intersection_update(faces[i])
    nodes.append({'node':node,'parent':parent,'ids':ids,'common':common})
    return ids
visit(shell['candidate_root'])
by_identity={id(n['node']):n for n in nodes}
valences=Counter(v for face in faces for v in face)
fan_rows=[]
for anchor,valence in valences.most_common(12):
    eligible=[n for n in nodes if anchor in n['common']]
    maximal=[n for n in eligible if n['parent'] is None or anchor not in by_identity[id(n['parent'])]['common']]
    certified=[n for n in eligible if anchor in meta.get(id(n['node']),{})]
    fan_rows.append({'source_vertex':anchor,'incident_faces':valence,
         'maximal_same_anchor_subtrees':len(maximal),
         'partition_sizes':sorted([len(n['ids']) for n in maximal],reverse=True),
         'largest_same_anchor_subtree':max(len(n['ids']) for n in eligible),
         'largest_cone_certified_subtree':max((len(n['ids']) for n in certified),default=0)})
categories=Counter();sizes=Counter();degenerate_faces=[]
for i,face in enumerate(faces):
    a,b,d=[shell['candidate_vertices'][v] for v in face]
    area=(b[0]-a[0])*(d[1]-a[1])-(b[1]-a[1])*(d[0]-a[0])
    if area==0:degenerate_faces.append(i)
for row in nodes:
    node=row['node'];n=len(row['ids'])
    if n==1:continue
    if not row['common']:categories['internal_no_common_anchor']+=1
    elif id(node) in meta:categories['internal_has_cone_metadata']+=1
    else:
        categories['internal_common_anchor_but_no_cone']+=1
        if any(i in degenerate_faces for i in row['ids']):categories['internal_no_cone_with_degenerate_descendant']+=1
    if id(node) in meta:sizes[n]+=1
local=raws['Target']['vertices_local'];levels=sorted({p[2] for p in local})
fixture_groups=[]
for z in levels:
    ids=[i for i,face in enumerate(faces) if all(local[v][2]==z for v in face)]
    edge_counts=Counter(tuple(sorted((f[k],f[(k+1)%3]))) for i in ids for f in (faces[i],) for k in range(3))
    vertices={v for i in ids for v in faces[i]}
    fixture_groups.append({'scope':'source-fixture grouping by native local extrusion level, not inferred product certificate',
      'native_z':z,'faces':len(ids),'vertices':len(vertices),'edges':len(edge_counts),
      'euler_characteristic':len(vertices)-len(edge_counts)+len(ids),
      'boundary_edges':sum(v==1 for v in edge_counts.values()),
      'projected_degenerate_faces':sum(i in degenerate_faces for i in ids)})
static={'source_sha256':freeze['source_sha256'],'Target_triangles':len(faces),
        'Target_vertices':len(shell['vertices']),'valence_histogram':dict(Counter(valences.values())),
        'largest_fans':fan_rows,'internal_node_categories':dict(categories),
        'internal_cone_metadata_subtree_size_histogram':dict(sizes),
        'projected_degenerate_face_count':len(degenerate_faces),
        'fixture_native_cap_groups':fixture_groups,
        'scope':'single existing candidate tree static attribution, not alternative axis/tree or new candidate'}
(OUT/'STATIC_FAN_STRUCTURE.json').write_text(json.dumps(static,indent=2),encoding='utf8')
print(json.dumps({'charges_by_phase':dict(phase_charges),'largest_stages':charges.most_common(12),
                  'static':static}),flush=True)
