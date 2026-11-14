"""Exact offline justification for the no-frustum-clipping fixture oracle."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
T=ROOT/'verification/m4_active_observation_patch_ownership_001'
O=Path(__file__).resolve().parent
joined=json.loads((T/'inputs/JOINED.json').read_bytes())
split=json.loads((T/'inputs/SPLIT.json').read_bytes())
prior_path=ROOT/'verification/m4_active_observation_host_bridge_001/inputs/QA_GEOMETRY.json'
prior=json.loads(prior_path.read_bytes())
source_objects={r['name']:r for r in prior['objects']}
new_objects={r['name']:r for r in split['objects']}
lineage={
    'prior_sha256':hashlib.sha256(prior_path.read_bytes()).hexdigest(),
    'prior_hash_matches':hashlib.sha256(prior_path.read_bytes()).hexdigest()=='6d3772a061dbdde5b2a65317252548f9f2129c12afdb52570e41f19a48ff05bd',
    'all_28_original_objects_unchanged':all(obj==new_objects[name] for name,obj in source_objects.items()),
    'only_one_added_component':set(new_objects)-set(source_objects)=={'QA_UnsupportedTriangle'},
    'original_triangle_count':sum(len(o['triangles']) for o in source_objects.values()),
}
idx=json.loads((T/'external_archive/f0108_INDEX_01.json').read_bytes())
verts=[tuple(F(x) for x in v) for v in joined['objects'][0]['vertices']]
unique=sorted(set(verts));checks=[]
for pose in idx['cameras']['views']:
    view=[[F(x) for x in row] for row in pose['view_matrix']]
    proj=[[F(x) for x in row] for row in pose['projection_matrix']]
    depths=[];clipcoords=[]
    for vertex in unique:
        world=vertex+(F(1),)
        camera=tuple(sum(a*b for a,b in zip(row,world)) for row in view)
        clip=tuple(sum(a*b for a,b in zip(row,camera)) for row in proj)
        depths.append(-camera[2]);clipcoords.extend(clip[:3])
    checks.append({'view':pose['name'],'passed':min(depths)>0 and min(clipcoords)>=-1 and max(clipcoords)<=1,
                   'unique_vertices':len(unique),'minimum_depth':str(min(depths)),
                   'maximum_abs_NDC':str(max(abs(x) for x in clipcoords))})
result={'schema':'root-patch-frustum-independent-v1','passed':all(c['passed'] for c in checks) and all(lineage[k] for k in ('prior_hash_matches','all_28_original_objects_unchanged','only_one_added_component')),'checks':checks,'fixture_lineage':lineage,
        'method':'Exact rational evaluation of stored binary64 matrices on original exact fixture vertices; no product calls.',
        'new_product_raster_calls':0,'source_sha256':hashlib.sha256((T/'external_archive/f0108_INDEX_01.json').read_bytes()).hexdigest()}
(O/'FRUSTUM.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'views':len(checks),'unique_vertices':len(unique)}))
