"""Independent saved-evidence review. No product import, scorer, host or raster call."""
import base64
import collections
import copy
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SLOT = Path('D:/he_m4_target_001/qualification/A_peripheral_02')
TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe')
checks, inputs = [], []

def read(path):
    path = Path(path)
    b = path.read_bytes()
    inputs.append({'path': str(path), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()})
    return b

def jread(path):
    return json.loads(read(path))

def check(name, ok, evidence=None):
    checks.append({'name': name, 'pass': bool(ok), 'evidence': evidence})

def sha(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def subtract(a, b):
    return tuple(x-y for x,y in zip(a,b))

def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

capture = jread(SLOT/'CAPTURE_01.json')
public = jread(SLOT/'PUBLIC_01.json')
response = jread(SLOT/'RESPONSE_01.json')
request = jread(SLOT/'REQUEST_01.json')
owner = jread(SLOT/'OWNER_BINDING.json')
result = jread(SLOT/'RESULT.json')
wire = jread(SLOT/'native/WIRE/001/RESPONSE.bin')
wire_request = jread(SLOT/'native/WIRE/001/REQUEST.bin')
body = json.loads(wire['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
audit_bytes = read(SLOT/'audit.jsonl')
audit = [json.loads(line) for line in audit_bytes.splitlines()]
observe_audit = next(a for a in audit if a['event']=='observe')
resources = {r['id']:r for r in body['resources']}
expanded = copy.deepcopy(body['capture'])
for mesh in expanded['meshes']:
    ref = mesh.pop('_scene_resource')
    resource = resources[ref['id']]
    matrix = ref['matrix']
    mesh['vertices'] = [[sum(matrix[i][j]*v[j] for j in range(3)) + matrix[i][3] for i in range(3)] for v in resource['vertices_local']]
    mesh['vertices'] = [[x*ref['scale'] for x in v] for v in mesh['vertices']]
    mesh['faces'] = resource['faces']
    mesh['edges'] = resource['edges']
check('actual_wire_resources_expand_exactly_to_saved_capture', expanded == capture)
check('actual_response_text_equals_saved_public', json.loads(response['result']['content'][0]['text']) == public)
check('actual_request_target', request['params']['arguments']['query'] == {'mode':'active_observation','objects':[{'name':'M4_Far_00'}]})
stdio_responses = list((SLOT/'stdio').rglob('RESPONSE.json'))
matching_responses = []
for p in stdio_responses:
    value = jread(p)
    if value == response:
        matching_responses.append(str(p))
check('saved_response_equals_actual_stdio_response', bool(matching_responses), matching_responses)
meshes = capture['meshes']
by_name = {m['name']:m for m in meshes}
check('unique_mesh_names', len(by_name)==len(meshes))
manifest_matches = all(by_name[o['object_name']]['vertices']==o['vertices_world'] and by_name[o['object_name']]['faces']==o['triangles'] and by_name[o['object_name']]['object_id']==o['object_id'] for o in owner['asset_manifest']['objects'])
check('actual_geometry_equals_owner_manifest',manifest_matches)
counts = {'objects':len(meshes),'vertices':sum(len(m['vertices']) for m in meshes),'triangles':sum(len(m['faces']) for m in meshes)}
check('actual_scene_counts',counts=={'objects':14,'vertices':3474,'triangles':6146},counts)
target=by_name['M4_Far_00']; ti=meshes.index(target)
vs=[tuple(F(x) for x in v) for v in target['vertices']]
faces=target['faces']
normals=[cross(subtract(vs[b],vs[a]),subtract(vs[c],vs[a])) for a,b,c in faces]
edges=collections.Counter(tuple(sorted((face[k],face[(k+1)%3]))) for face in faces for k in range(3))
grid={(F(1),F(y,16),F(z,16)) for y in range(17) for z in range(17)}
check('target_289_grid_vertices_512_negative_x_triangles',set(vs)==grid and len(vs)==289 and len(faces)==512 and set(normals)=={(-F(1,256),F(0),F(0))})
check('target_unit_square_area_and_boundary',sum(-n[0]/2 for n in normals)==1 and all(n in (1,2) for n in edges.values()) and sum(n==1 for n in edges.values())==64)
actual_triangles={frozenset(vs[index] for index in face) for face in faces}
expected_triangles=set()
for y in range(16):
    for z in range(16):
        q00=(F(1),F(y,16),F(z,16));q01=(F(1),F(y,16),F(z+1,16))
        q10=(F(1),F(y+1,16),F(z,16));q11=(F(1),F(y+1,16),F(z+1,16))
        expected_triangles.update([frozenset((q00,q01,q11)),frozenset((q00,q11,q10))])
check('target_exact_grid_triangulation_without_gaps_or_overlaps',actual_triangles==expected_triangles and len(actual_triangles)==512)
near=by_name['M4_Near']; d=F(near['vertices'][0][0]); near_vertices=[tuple(F(x) for x in v) for v in near['vertices']]
check('actual_near_triangle',near_vertices==[(d,F(0),F(0)),(d,F(1),F(0)),(d,F(0),F(1))] and near['faces']==[[0,1,2]] and 0<d<1)
shadow_area=d*d/2
near_canonical=min(tuple(near_vertices[i:]+near_vertices[:i]) for i in range(3))
near_sha=sha(near_canonical)
view_plan=capture['observation_target']['camera_plan']
classification={}
for view in view_plan['views']:
    direction=tuple(F(x) for x in view['direction_rational'])
    dot=-direction[0]
    classification[view['name']]='edge_on' if dot==0 else 'back_facing' if dot<0 else 'positive_area_occlusion'
    matrix=np.asarray(view['view_matrix'],dtype=float)
    rational=np.asarray([float(v) for v in direction]); unit=rational/np.linalg.norm(rational)
    eye=np.asarray(view['camera_eye_world_m']); center=np.asarray(view['target_world_m'])
    eye_direction=(eye-center)/np.linalg.norm(eye-center)
    matrix_ok=np.allclose(matrix[2,:3],unit,rtol=0,atol=2e-14) and np.allclose(eye_direction,unit,rtol=0,atol=2e-14) and np.allclose(matrix[:3,:3]@matrix[:3,:3].T,np.eye(3),rtol=0,atol=2e-14)
    check('actual_'+view['name']+'_camera_matrix_agrees_with_rational_direction',matrix_ok)
check('actual_camera_pool_classification',classification=={'SCENE':'back_facing','TOP':'edge_on','LEFT':'positive_area_occlusion','RIGHT':'back_facing','FRONT':'edge_on','BACK':'edge_on'},classification)
roi=public['regions']['rows'][0][0]
actual_classes=observe_audit['target_view_classifications']
check('audit_classifications_match_independent_truth',all(actual_classes[k][roi]['status']==v and actual_classes[k][roi]['complete'] is False for k,v in classification.items()))
blocker=actual_classes['LEFT'][roi]['first_blocker']
check('left_positive_shadow_area_and_near_identity',blocker['overlap_area_screen_exact']==str(shadow_area) and blocker['triangle_geometry_id']==near_sha,{'d':str(d),'area':str(shadow_area),'area_float':float(shadow_area),'blocker':near_sha})
# LEFT ray direction from a point (1,y,z) to eye is (-1,0,1).
# At Near x=d, y+z+1-d <= 1, hence y+z <= d on the target square.
# Its right triangular preimage has exact area d*d/2; focal at x=0 has zero area.
left=next(v for v in view_plan['views'] if v['name']=='LEFT')
frustum=[]
for point in [(1,0,0),(1,float(d),0),(1,0,float(d))]:
    q=np.asarray(left['projection_matrix']) @ np.asarray(left['view_matrix']) @ np.asarray([*point,1.0])
    frustum.append((q[:3]/q[3]).tolist())
check('left_shadow_region_inside_saved_camera_frustum',all(all(-1<x<1 for x in p) for p in frustum),frustum)
region=dict(zip(public['regions']['columns'],public['regions']['rows'][0]))
check('one_target_rectangle_source_range',len(public['regions']['rows'])==1 and region['object_index']==ti and region['triangle_count']==512 and region['source_triangle_index_ranges']==[[0,511]])
check('unknown_zero_covered_null_witness_are_consistent',region['status']=='unknown' and region['reason']=='finite_camera_pool_uncovered' and region['complete_witness_pixel_index'] is None and public['inspection']['counts']['covered']==0 and public['inspection']['counts']['no_geometric_complete_candidate']==1)
check('api_complete_does_not_claim_observation_coverage',public['status']=='complete' and public['inspection']['state']=='finite_pool_exhausted' and public['inspection']['stop_reason']=='no_unobserved_geometric_candidates' and public['coverage']['observed_views']==['SCENE'])
frame_dir=SLOT/'state.json.active_observation'
pngs=list(frame_dir.rglob('*.png')); npzs=list(frame_dir.rglob('*.npz'))
check('only_one_scene_raster_attempt_and_artifact',len(pngs)==len(npzs)==1 and [(a['view_name'],a['attempt']) for a in audit if a['event']=='active_observation_render_attempt']==[('SCENE',1)])
png_bytes=read(pngs[0]);npz_bytes=read(npzs[0])
data=np.load(io.BytesIO(npz_bytes),allow_pickle=False)
color=data['color'];depth=data['depth'];owners=data['owners'];tri=data['triangle_ids'];patch=data['patch_owners']
check('png_matches_delivered_base64_and_public_hash',base64.b64decode(response['result']['content'][1]['data'])==png_bytes and public['images']['rows'][0][2]==hashlib.sha256(png_bytes).hexdigest())
check('npz_color_equals_saved_png',np.array_equal(np.asarray(Image.open(io.BytesIO(png_bytes)).convert('RGB')),color))
offsets=np.array([0]+list(np.cumsum([len(m['faces']) for m in meshes])),dtype=np.int64)
check('npz_source_triangle_offsets',np.array_equal(data['face_patch_offsets'],offsets))
expected_patches=np.full(int(offsets[-1]),-1,dtype=np.int32);expected_patches[offsets[ti]:offsets[ti+1]]=0
check('npz_face_patch_mapping_targets_only_far00',np.array_equal(data['face_patch_ids'],expected_patches) and data['patch_roi_ids'].tolist()==[roi])
foreground=owners>=0
check('npz_background_and_foreground_valid',np.all((owners==-1)|((owners>=0)&(owners<len(meshes)))) and np.all(tri[~foreground]==-1) and np.all(patch[~foreground]==-1) and np.all(np.isposinf(depth[~foreground])) and np.all(np.isfinite(depth[foreground])) and np.all(depth[foreground]>0))
check('npz_winner_source_triangle_and_roi_consistency',np.all(tri[foreground]>=offsets[owners[foreground]]) and np.all(tri[foreground]<offsets[owners[foreground]+1]) and np.array_equal(patch[foreground],expected_patches[tri[foreground]]))
check('npz_patch_identity_equals_response',str(data['patch_mapping_identity'])==public['images']['rows'][0][4])
mask=patch==0
yy,xx=np.nonzero(mask)
bounds=[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())]
distance=(2*xx-bounds[0]-bounds[2])**2+(2*yy-bounds[1]-bounds[3])**2
at=int(np.argmin(distance));anchor=[int(xx[at]),int(yy[at])]
# Direct neighbor pair enumeration, independent of product's optimized boundary helper.
boundary=np.zeros(mask.shape,dtype=bool)
for dy,dx in [(0,1),(1,0)]:
    for y in range(mask.shape[0]-dy):
        for x in range(mask.shape[1]-dx):
            y2,x2=y+dy,x+dx
            if patch[y,x]!=patch[y2,x2] and sum((int(a)-int(b))**2 for a,b in zip(color[y,x],color[y2,x2]))>=24*24:
                boundary[y,x]=boundary[y2,x2]=True
pixel=dict(zip(public['pixels']['columns'],public['pixels']['rows'][0]))
pixel_truth={'surface':int(mask.sum()),'boundary':int(np.count_nonzero(boundary&mask)),'bounds':bounds,'anchor':anchor,'front_facing':False,'readable':False}
check('actual_pixel_counts_bounds_anchor',pixel['visible_surface_pixels']==pixel_truth['surface'] and pixel['contrasting_boundary_pixels']==pixel_truth['boundary'] and pixel['visible_pixel_bounds']==bounds and pixel['visible_pixel_anchor']==anchor,pixel_truth)
check('scene_backface_visible_but_unreadable',pixel['front_facing'] is False and pixel['readable'] is False and pixel['visible_surface_pixels']>0)
check('original_audit_has_no_producer_npz_hash',hashlib.sha256(npz_bytes).hexdigest().encode() not in audit_bytes)
producer_receipts=[SLOT/'io_audit/MCP_IO.jsonl',SLOT/'io_audit/RUNTIME.json',SLOT/'stdio/stdout.raw.bin']+list((SLOT/'stdio').rglob('RECEIPT.json'))
npz_digest=hashlib.sha256(npz_bytes).hexdigest().encode()
receipt_hits=[str(p) for p in producer_receipts if npz_digest in read(p)]
check('captured_producer_io_receipts_do_not_pin_npz_digest',not receipt_hits,{'searched_files':len(producer_receipts),'hits':receipt_hits})
report={'schema':'independent-m4-target001-quality-review-v1','reviewer_assignment':'d7536399-214d-4d7b-afef-adfb3154f95f','author_final_commit':'03eb4e2971891dfe0160972cbcf974e3dcf1a21c','runtime_source_sha256':public['binding']['runtime_source_sha256'],'new_product_calls':0,'new_model_calls':0,'new_blender_calls':0,'new_rasters':0,'checks':checks,'pass_count':sum(c['pass'] for c in checks),'fail_count':sum(not c['pass'] for c in checks),'inputs':inputs,'scope_limits':['Current saved NPZ hash independently recorded after run; no producer-time NPZ digest in original audit. RGB binds to delivered PNG; ownership/depth maps independently checked for current internal consistency, not authenticated as original-time bytes.','No independent reraster or current live host execution.','One A peripheral qualification only; no B nor formal 12-slot controls or net-benefit claim.','API status complete is request completion, not complete geometric/pixel witness.']}
HERE.mkdir(parents=True,exist_ok=True)
(HERE/'RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(checks),'pass':report['pass_count'],'fail':report['fail_count'],'fail_names':[c['name'] for c in checks if not c['pass']],'pixel':pixel_truth,'shadow_area':str(shadow_area)},ensure_ascii=False))
