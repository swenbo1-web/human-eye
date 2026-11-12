"""Read fixed saved requests/responses, never execute their programs."""
from pathlib import Path
import hashlib,json

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE=Path(__file__).resolve().parent
CELL=ROOT/'verification/m4_selected_geometry_consumption_001/cells/sgc03/owner'
files={}
def load(path):
    blob=path.read_bytes();files[str(path)]=hashlib.sha256(blob).hexdigest()
    return json.loads(blob)
def request(n):return load(CELL/f'tool_{n:02}/REQUEST.json')['params']
def response(n):return json.loads(load(CELL/f'tool_{n:02}/RESPONSE.json')['result']['content'][0]['text'])
r1,r2,r3=[request(n) for n in (1,2,3)]
p1,p2,p3=[response(n) for n in (1,2,3)]
directory=json.loads(p1['result']['result'])
references=('N24','N12','N04','N19')
bound_rows=[r for r in directory if r['name'] in references]
assert len(directory)==28 and len(bound_rows)==4
assert all('bounds' in row and 'center' in row for row in bound_rows)
assert all(name in r3['arguments']['code'] for name in references)
assert 'local vertices' in r3['arguments']['code'] and 'o.data.vertices' in r3['arguments']['code']
assert 'matrix_world' in r3['arguments']['code'] and 'math.hypot' in r3['arguments']['code']
assert r2['arguments']['geometry']['include_triangles'] is True
geometry=[dict(name=row['name'],vertices=len(row['vertices_world']),triangles=len(row['triangles'])) for row in p2['geometry']['objects']]
local=[dict(name=row['name'],local_evidence=row['closed_solid_relation'].get('local_evidence'),
    nearest_witness=row['surface_proximity']['value'].get('nearest_witness')) for row in p2['candidates']]
for rel in ('human_eye_plugin/task_query.py','human_eye_plugin/live_spatial_mcp.py',
            'human_eye_plugin/blender_host.py','human_eye_plugin/scene_residency.py',
            'human_eye_plugin/surface_proximity.py','human_eye_plugin/live_service.py'):
    path=ROOT/rel;files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
result=dict(passed=True,source_scope='saved sgc03 tool records plus c013/fac source inspection; no new model/Blender',
    first_call_object_count=len(directory),first_call_reference_bounds_and_centers=bound_rows,
    first_call_code=r1['arguments']['code'],relation_call_arguments=r2['arguments'],
    third_call_code=r3['arguments']['code'],third_call_new_reference_shape_text=p3['result']['result'],
    third_call_classification=['four reference local vertex arrays and matrices',
        'repeat bounds/centers for N15 N18 N25 N16','XY distance computations'],
    relation_geometry=geometry,existing_relation_local_evidence=local,
    findings=dict(reference_bounds_were_already_delivered=True,
        reference_bounds_only_proves_round_elimination=False,geometry_default_off=True,
        explicit_geometry_triangles_default=False,original_polygons_preserved_in_relation_resource=False,
        local_crossing_and_distance_witnesses_already_present=True,
        current_surface_sum_faces_limit=4096,current_surface_triangle_pairs_limit=16384),
    source_files=files)
(HERE/'EVIDENCE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('passed','first_call_object_count','relation_geometry','findings')},ensure_ascii=False))
