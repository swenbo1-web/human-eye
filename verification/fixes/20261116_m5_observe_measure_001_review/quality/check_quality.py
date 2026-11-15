"""Independent saved-wire, measurement, image and matrix-state review."""
import base64
import copy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
RUN = Path('D:/he_m5_observe_measure_001')
FROZEN = Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')
checks = 0

def check(condition, name):
    global checks
    if not condition:
        raise AssertionError(name)
    checks += 1

def read(p):
    return json.loads(Path(p).read_bytes())

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def digest(v):
    raw = json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

def geometry_alias(mesh):
    vertices = tuple(tuple(F(x) for x in p) for p in mesh['vertices'])
    triangles = []
    for face in mesh['faces']:
        corners = tuple(vertices[i] for i in face)
        triangles.append(min(corners[i:]+corners[:i] for i in range(3)))
    key = (tuple(sorted(vertices)),tuple(sorted(triangles)))
    raw = json.dumps(key,default=str,sort_keys=True,separators=(',', ':')).encode()
    return 'geometry:'+hashlib.sha256(raw).hexdigest()

check(sha(FROZEN) == 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da', 'root frozen input')
source = read(FROZEN)
original = {m['name']: {'vertices': [[float(F(x)) for x in p] for p in m['world_vertices_m']],
                       'faces': m['triangles']} for m in source['objects']}

def decode(slot):
    saved = read(slot / 'SAVED_WIRE.json')
    resources = {}
    captures = {}
    for step in saved['steps']:
        check(sha(step['request']) == step['request_sha256'], 'original host TX hash')
        check(sha(step['response']) == step['response_sha256'], 'original host RX hash')
        outer = read(step['response'])
        text = outer.get('result', {}).get('result')
        if not isinstance(text, str) or not text.startswith('HUMAN_EYE_BLENDER_MCP:'):
            continue
        packet = json.loads(text.split(':', 1)[1])['result']
        if packet.get('schema') != 'human-eye-scene-delta-v1':
            continue
        for resource in packet['resources']:
            resources[resource['id']] = resource
        capture = copy.deepcopy(packet['capture'])
        for mesh in capture['meshes']:
            ref = mesh.pop('_scene_resource')
            resource = resources[ref['id']]
            check(resource['revision'] == ref['revision'], 'current resource revision')
            matrix, scale = ref['matrix'], ref['scale']
            mesh['vertices'] = [[sum(matrix[k][axis] * vertex[axis] for axis in range(3)) * scale
                                 + matrix[k][3] * scale for k in range(3)]
                                for vertex in resource['vertices_local']]
            mesh['faces'] = resource['faces']
            mesh['edges'] = resource['edges']
        seq = int(Path(step['request']).parent.name)
        captures[seq] = capture
    for row in saved['captures']:
        check(sha(row['path']) == row['sha256'], 'saved capture hash')
        check(captures[row['wire_sequence']] == read(row['path']), 'wire reconstructed equals saved capture')
    return captures

def point_on_surface(point, mesh):
    p = [F(x) for x in point]
    for face in mesh['faces']:
        a, b, c = [[F(x) for x in mesh['vertices'][i]] for i in face]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        w = [p[i] - a[i] for i in range(3)]
        n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        if sum(n[i]*w[i] for i in range(3)) != 0:
            continue
        dot = lambda x,y: sum(x[i]*y[i] for i in range(3))
        uu, uv, vv, wu, wv = dot(u,u), dot(u,v), dot(v,v), dot(w,u), dot(w,v)
        det = uu*vv-uv*uv
        if not det:
            continue
        alpha, beta = (vv*wu-uv*wv)/det, (uu*wv-uv*wu)/det
        if alpha >= 0 and beta >= 0 and alpha+beta <= 1:
            return True
    return False

def measurements(task, meshes, expected):
    check(task['schema_version'] == 'task-query-v3' and task['execution_authority'] is False, 'readonly task schema')
    check(task['unit'] == 'm' and task['coordinate_frame'] == 'world' and task['pair_order'] == 'A_to_B', 'task units and order')
    fact = task['facts']['surface_proximity']
    check(fact['status'] == 'measured' and fact['witness_status'] == 'measured', 'measured proximity and witness')
    val = fact['value']
    check(val['distance_m'] == expected, 'independent distance oracle')
    a, b = val['nearest_witness']['a'], val['nearest_witness']['b']
    pair = task['binding']['objects']
    check([o['name'] for o in pair] == ['M4_Far_00', 'M4_Far_11' if expected == math.sqrt(101) else 'M4_Near'], 'actual pair selectors')
    target = meshes['M4_Far_00']
    if expected == math.sqrt(101):
        far = meshes['M4_Far_11']
        check(all(p[0]==12 and 0<=p[2]<=1 for p in far['vertices']), 'Far11 exact supporting plane and z range')
        check(all((all(target['vertices'][i][0]==1 for i in face)
                   or all(target['vertices'][i][2]==2 and 1<=target['vertices'][i][0]<=2 for i in face))
                  for face in target['faces']), 'each target face lower bound gives 11 or sqrt101')
    else:
        near = meshes['M4_Near']
        plane = near['vertices'][0][0]
        check(all(p[0]==plane for p in near['vertices']) and min(p[0] for p in target['vertices'])-plane==expected,
              'independent parallel support distance lower bound')
    check(point_on_surface(a, meshes[pair[0]['name']]) and point_on_surface(b, meshes[pair[1]['name']]), 'witness exact source triangle membership')
    distance = math.sqrt(sum((b[k]-a[k])**2 for k in range(3)))
    check(distance == expected, 'witness separation')
    direction = val['nearest_witness']['direction_a_to_b']
    check(all(abs(direction[k] - (b[k]-a[k])/expected) <= 2e-15 for k in range(3)), 'witness A to B direction')
    check(abs(sum(x*x for x in direction)-1) <= 3e-15, 'unit direction')
    return val

def normalize_frame(frame, capture, response_images, index, producer):
    check(frame['host_binding_sha256']==producer['binding']['binding_sha256']
          and frame['source_revision']==producer['binding']['scene_revision'],'frame current parent binding and source')
    check(sha(frame['arrays_path']) == frame['arrays_sha256'] and sha(frame['image_path']) == frame['image_sha256'], 'producer NPZ PNG hash')
    check(base64.b64decode(response_images[index]['data'], validate=True) == Path(frame['image_path']).read_bytes(), 'same actual delivered PNG')
    with np.load(frame['arrays_path'], allow_pickle=False) as arrays:
        data = {k:arrays[k] for k in arrays.files}
    check(np.array_equal(np.asarray(Image.open(frame['image_path'])),data['color']), 'PNG equals RGB buffer')
    meshes = capture['meshes']
    offsets = np.cumsum([0] + [len(m['faces']) for m in meshes])
    check(np.array_equal(offsets,data['face_patch_offsets']), 'frame original object face offsets')
    valid = data['owners'] >= 0
    check(np.array_equal(valid,data['triangle_ids'] >= 0), 'pixel owner/source support')
    tri = data['triangle_ids'][valid]
    owner = np.searchsorted(offsets[1:],tri,side='right')
    check(np.array_equal(data['owners'][valid],owner), 'pixel source owner from offsets')
    rois = {r['roi_id']:r for r in producer['facts']['regions']}
    roi_ids = data['patch_roi_ids'].tolist()
    target_index = next(i for i,m in enumerate(meshes) if m['name']=='M4_Far_00')
    expected_patch = np.full(offsets[-1],-1,dtype=np.int32)
    for i,roi in enumerate(roi_ids):
        local_faces = [512,513] if rois[roi]['center_world_m'][2] == 2 else list(range(512))
        expected_patch[offsets[target_index]+np.asarray(local_faces)] = i
    check(np.array_equal(expected_patch,data['face_patch_ids']), 'actual source faces to ROI')
    expected_pixel_patch = np.full(data['owners'].shape,-1,dtype=np.int32)
    expected_pixel_patch[valid] = expected_patch[tri]
    check(np.array_equal(expected_pixel_patch,data['patch_owners']), 'source-derived patch owner')
    obs = next(o for o in producer['facts']['observations'] if o['view_name']==frame['view_name'])
    for row in obs['pixel_rows']:
        mask = expected_pixel_patch == roi_ids.index(row['roi_id'])
        count = int(np.count_nonzero(mask))
        contrast = np.zeros(mask.shape,dtype=bool)
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            ys,ye=max(0,-dy),min(512,512-dy)
            xs,xe=max(0,-dx),min(512,512-dx)
            own=(slice(ys,ye),slice(xs,xe))
            adjacent=(slice(ys+dy,ye+dy),slice(xs+dx,xe+dx))
            delta=data['color'][own].astype(np.int32)-data['color'][adjacent].astype(np.int32)
            contrast[own] |= mask[own] & ~mask[adjacent] & (np.sum(delta*delta,axis=2)>=24**2)
        check(count==row['visible_surface_pixels'] and int(np.count_nonzero(contrast))==row['contrasting_boundary_pixels'],'independent surface and RGB contrast pixels')
        check(row['readable']==(row['front_facing'] and count>=16 and np.count_nonzero(contrast)>=4),'actual readability')
    asset = np.full(data['owners'].shape,-1,dtype=np.int32)
    local = np.full(data['owners'].shape,-1,dtype=np.int32)
    names = sorted(original)
    asset[valid] = np.asarray([names.index(m['name']) for m in meshes])[owner]
    local[valid] = tri-offsets[owner]
    return {'view':frame['view_name'],'color':data['color'],'depth':data['depth'],'owner':asset,
            'local':local,'patch':data['patch_owners']}

def review(slot, state=False):
    run = read(slot/'RESULT.json')
    captures = decode(slot)
    observations = []
    for request in run['requests']:
        producer = read(request['producer']['path'])
        check(sha(request['producer']['path']) == request['producer']['sha256'], 'same producer hash')
        public = read(request['public_path'])
        text = next(x['text'] for x in request['response']['result']['content'] if x['type']=='text')
        check(json.loads(text) == public, 'actual public JSON equals saved projection')
        obs = producer.get('result_kind') == 'active_observation'
        if obs:
            binding = producer['binding']
            parent = next(c for c in captures.values() if c.get('revision') == binding['scene_revision']
                          and all(c['capture_state'][k] == binding['capture_state'][k]
                                  for k in ('instance_id', 'epoch', 'revision')))
            check(parent['capture_scope'] == 'target_observation_meshes', 'parent capture retains scope')
            check(parent['capture_state']['revision'] == binding['capture_state']['revision'], 'current observation generation')
            mesh_map = {m['name']:m for m in parent['meshes']}
            target = mesh_map['M4_Far_00']
            moved = 'matrix_changed' in request['id']
            shift = .25 if moved else 0
            for mesh in parent['meshes']:
                expected_vertices = original[mesh['name']]['vertices']
                if mesh['name']=='M4_Far_00' and moved:
                    expected_vertices = [[p[0]+.25,p[1],p[2]] for p in expected_vertices]
                check(mesh['vertices'] == expected_vertices and mesh['faces'] == original[mesh['name']]['faces'], 'current world geometry source')
            check(len(target['vertices']) == 293 and len(target['faces']) == 514, 'entire target geometry')
            if 'task_result' in producer:
                task = producer['task_result']
                check(public['task_result'] == task, 'brief or full delivers exact quantitative facts')
                source = task['binding']['observation_source']
                check(source['parent_binding_sha256'] == binding['binding_sha256'] and source['parent_source_binding_sha256'] == binding['source_binding_sha256'], 'parent task binding')
                check(source['parent_capture_scope'] == parent['capture_scope'] and source['measurement_scope']=='whole_objects', 'measurement scope')
                check(all(source['capture_state'][k] == parent['capture_state'][k] for k in ('instance_id','epoch','revision')), 'derived same scene generation')
                if 'missing' in request['id']:
                    extra = next(c for c in captures.values() if c.get('capture_scope')=='selected_objects' and len(c['meshes'])==1)
                    check(extra['meshes'][0]['name']=='M4_Far_11' and len(extra['meshes'][0]['faces'])==512, 'only missing object supplemented')
                    check(extra['meshes'][0]['vertices']==original['M4_Far_11']['vertices'], 'supplement exact frozen world vertices')
                    check(all(extra['capture_state'][k] == parent['capture_state'][k] for k in ('instance_id','epoch','revision')), 'supplement same generation')
                    mesh_map.update({m['name']:m for m in extra['meshes']})
                    expected = math.sqrt(101)
                else:
                    expected = float(F(5,4) - F(original['M4_Near']['vertices'][0][0])) if moved else float(F(1)-F(original['M4_Near']['vertices'][0][0]))
                for row in source['objects']:
                    mesh = next(m for m in mesh_map.values() if m['object_id']==row['object_id'])
                    check(mesh['faces'] == original[mesh['name']]['faces'], 'quantitative original source face sequence')
                    check(row['source_triangle_count']==len(mesh['faces']) and row['source_triangle_index_ranges']==[[0,len(mesh['faces'])-1]], 'whole source face set')
                    check(row['ordered_geometry_sha256']==digest({'vertices':mesh['vertices'],'faces':mesh['faces']}), 'ordered quantitative geometry digest')
                    all_instances = parent['observation_target']['full_scene_identity']['object_instances']
                    check(row['instance_id']==all_instances[row['object_id']], 'true host object instance')
                    i = row['observation_object_index']
                    if i is None:
                        check(mesh['name']=='M4_Far_11' and row['geometry_id'] is None, 'supplement no invented image geometry alias')
                    else:
                        check(parent['meshes'][i]['object_id']==row['object_id'], 'image index to actual object')
                        check(binding['objects'][i]['host_id']==row['object_id'] and binding['objects'][i]['instance_id']==row['instance_id'], 'image index to host identity map')
                        check(row['geometry_id']==geometry_alias(mesh),'independently rebuilt observation geometry alias')
                val = measurements(task,mesh_map,expected)
                work = producer['work']['task_query']
                check(work['surface_pair_count']==(0 if work['result_cache_hit'] else 1) and work['additional_raster_attempts']==0, 'one pair solve or existing result and no extra raster')
                check(work['supplemental_capture_calls']==(1 if 'missing' in request['id'] else 0), 'actual supplemental capture count')
            else:
                val = None
            covered = len(producer['facts']['coverage']['covered_roi_ids'])
            unknown = len(producer['facts']['coverage']['unresolved_roi_ids'])
            check((covered,unknown)==((2,0) if moved else (1,1)), 'current complete and unknown regions')
            frames = request['producer_frames']
            images = [x for x in request['response']['result']['content'] if x['type']=='image']
            check(len(frames)==len(images)==(2 if moved else 1), 'actual image count')
            normalized = [normalize_frame(frame,parent,images,i,producer) for i,frame in enumerate(frames)]
            observations.append({'id':request['id'],'binding':binding,'capture':parent,'frames':normalized,
                                 'classes':producer['target_view_classifications'],'facts':producer['facts'],
                                 'measurement':val,'covered':covered,'unknown':unknown})
        else:
            check(request['image_blocks']==0 and not request['producer_frames'], 'ordinary task no images')
            task = producer
            check(public['facts']==task['facts'] and public['binding']==task['binding'], 'ordinary public quantitative facts and binding')
            mesh_map = {m['name']:m for c in captures.values() for m in c['meshes']}
            measurements(task,mesh_map,float(F(1)-F(original['M4_Near']['vertices'][0][0])))
    return observations

def compare(a,b):
    check(a['classes']==b['classes'], 'same six-direction classification')
    check(a['binding']['camera_specification']==b['binding']['camera_specification'], 'same actual cameras')
    check(len(a['frames'])==len(b['frames']), 'same generated frame count')
    for fa,fb in zip(a['frames'],b['frames']):
        check(fa['view']==fb['view'],'same actual view')
        for key in ('color','depth','owner','local','patch'):
            check(np.array_equal(fa[key],fb[key]),'all pixel '+key+' equal')

summary = {'formal':[]}
for i in (1,2,3):
    a,b = review(RUN/'formal'/f'A{i}'),review(RUN/'formal'/f'B{i}')
    compare(a[0],b[0])
    summary['formal'].append({'pair':i,'distance_m':b[0]['measurement']['distance_m'],'same_frames':len(b[0]['frames'])})
for label in ('A_task_only','B_task_only'):
    check(review(RUN/'formal'/label)==[], 'task-only has no observation')
states=review(RUN/'control/B_state',True)
check(len(states)==5,'five actual state requests')
compare(states[0],states[1])
compare(states[0],states[4])
check([s['binding']['capture_state']['revision'] for s in states]==[1,1,1,2,3], 'actual scene revisions')
check(len(set(states[i]['binding']['binding_sha256'] for i in (0,3,4)))==3, 'old bindings not reused after change/restore')
control=read(RUN/'control/B_state/STATE_CONTROL.json')
check(control['actual_fixture_matrix_setters']==2 and control['product_setters']==0 and control['source_asset_saved'] is False, 'fixture-only two actual setters')
receipts=[r['response']['result'] for r in control['fixture_receipts']]
identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
move=copy.deepcopy(identity);move[0][3]=.25
check(receipts[0]['matrix_before']==identity and receipts[0]['matrix_after']==move,'actual moved matrix')
check(receipts[1]['matrix_before']==move and receipts[1]['matrix_after']==identity,'actual matrix restored')
check(receipts[0]['before_fingerprint']==receipts[1]['after_fingerprint'],'whole scene fingerprint restored')
for r in receipts:
    for phase in ('before','after'):
        matrix=r['matrix_'+phase]
        vertices=[[p[0]+matrix[0][3],p[1],p[2]] for p in original['M4_Far_00']['vertices']]
        check(r['world_'+phase]==vertices,'293 exact world points match fixture matrix')
summary.update(status='passed',checks=checks,formal_slots=8,state_requests=5,formal_frames=6,state_frames=sum(len(s['frames']) for s in states),
               state_unique_frame_files=len({f['arrays_path'] for q in read(RUN/'control/B_state/RESULT.json')['requests'] for f in q['producer_frames']}),
               state_distances=[s['measurement']['distance_m'] for s in states],
               actual_fixture_matrix_setters=2,new_Blender=0,new_raster=0,new_model=0,
               scope='Independent fixed-source geometry, original wire resources, public response and saved producer buffers. No new host execution.')
(OUT/'RESULT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in summary.items() if k!='formal'},ensure_ascii=False))
