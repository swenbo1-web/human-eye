"""Independent saved-only delivery/source/pixel review. No product imports."""
import ast
import base64
import copy
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

ROOT = Path('D:/he_m4_cross_scale_001/sessions')
OUT = Path(__file__).resolve().parent
AUTHOR = '3c26b43d197e6de252f65db69c061733e5a7216e'
CHECKS, PINS, RAY_CACHE, FRAME_RECORDS = [], {}, {}, {}


def require(value, name):
    if not value:
        raise AssertionError(name)
    CHECKS.append(name)


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    PINS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def rows(path):
    return [json.loads(line) for line in raw(path).decode().splitlines() if line]


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def ordered(mesh):
    return sha({'vertices': mesh['vertices'], 'faces': mesh['faces']})


def wire_captures(session):
    resources, captures = {}, []
    for folder in sorted((session / 'native/WIRE').glob('[0-9]*')):
        tx, rx = read(folder / 'REQUEST.bin'), read(folder / 'RESPONSE.bin')
        code = tx.get('params', {}).get('code', '')
        match = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if not match:
            continue
        command = json.loads(ast.literal_eval(match.group(1)))
        packets = [line.split(':', 1)[1] for line in rx.get('result', {}).get('result', '').splitlines()
                   if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        require(rx.get('status') == 'success' and len(packets) == 1, session.name + '/actual wire unique packet')
        packet = json.loads(packets[0])
        require(packet.get('error') is None, session.name + '/actual wire success')
        value = packet.get('result')
        if not isinstance(value, dict):
            continue
        for resource in value.get('resources', []):
            key = resource['id'], resource['revision']
            require(key not in resources or resources[key] == resource, session.name + '/immutable resource')
            resources[key] = resource
        capture = copy.deepcopy(value.get('capture', value))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            ref = mesh.pop('_scene_resource', None)
            if ref:
                resource = resources[ref['id'], ref['revision']]
                matrix, scale = ref['matrix'], ref['scale']
                mesh.update(vertices=[[(((matrix[k][0] * p[0] + matrix[k][1] * p[1])
                    + matrix[k][2] * p[2]) + matrix[k][3]) * scale for k in range(3)]
                    for p in resource['vertices_local']], faces=copy.deepcopy(resource['faces']))
        captures.append((command, capture))
    return captures


def bound_capture(full, captures, label):
    binding = full['binding']
    matched = [c for _, c in captures if c['revision'] == binding['scene_revision']
               and c['capture_state'] == binding['capture_state']]
    require(bool(matched), label + '/same producer current capture exists')
    signatures = {sha(c) for c in matched}
    require(len(signatures) == 1, label + '/same generation capture unambiguous')
    capture = matched[0]
    require(len(capture['meshes']) == 9 and sum(len(m['vertices']) for m in capture['meshes']) == 54
            and sum(len(m['faces']) for m in capture['meshes']) == 56, label + '/9 objects 54 vertices 56 faces')
    require(binding['document_epoch'] == capture['host_identity']['document_epoch'], label + '/document epoch')
    require(binding['objects'] == [dict(object_index=i, host_id=m['object_id'], object_name=m['name'],
            instance_id=capture['host_identity']['object_instances'][m['object_id']])
            for i, m in enumerate(capture['meshes'])], label + '/current object order')
    return capture


def binding_hash(binding, local=False):
    appended = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}
    core = {k: v for k, v in binding.items() if k not in appended}
    require(sha({k: v for k, v in core.items() if k != 'binding_sha256'}) == core['binding_sha256'], 'full binding preimage')
    require(sha({k: v for k, v in core.items() if k not in {'source_binding_sha256', 'binding_sha256',
        'geometry_identity', 'camera_identity', 'camera_specification'}}) == core['source_binding_sha256'], 'source binding preimage')
    cameras = binding['camera_specification']['views']
    require(sha([{k: p[k] for k in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
        for p in cameras]) == binding['camera_identity'], 'camera identity preimage')


def boundary_mask(color, patches):
    result = np.zeros(patches.shape, dtype=bool)
    for axis in (0, 1):
        a, b = [slice(None)] * 2, [slice(None)] * 2
        a[axis], b[axis] = slice(None, -1), slice(1, None)
        a, b = tuple(a), tuple(b)
        difference = color[a].astype(np.int32) - color[b].astype(np.int32)
        edge = (patches[a] != patches[b]) & ((difference * difference).sum(axis=2) >= 24**2)
        result[a] |= edge
        result[b] |= edge
    return result


def rays(frame, meshes, arrays):
    """Independent world ray-plane and Gram solves for existing foreground."""
    pose = frame['pose']
    key = sha(([(m['vertices'], m['faces']) for m in meshes], pose, frame['image_sha256'],
               frame['patch_mapping_identity'], frame['arrays_sha256']))
    if key in RAY_CACHE:
        return RAY_CACHE[key]
    camera = np.asarray(pose['view_matrix'], dtype=float)
    inverse = np.linalg.inv(camera)
    projection = np.asarray(pose['projection_matrix'], dtype=float)
    foreground = arrays['owners'].ravel() >= 0
    ids = np.flatnonzero(foreground)
    # Include fixed background probes independently of foreground ownership.
    probes = np.array([y*512+x for y in range(0,512,32) for x in range(0,512,32)], dtype=int)
    ids = np.unique(np.concatenate((ids, probes)))
    screen_x = (2*(ids % 512 + .5)/511 - 1) / projection[0,0]
    screen_y = (1 - 2*(ids // 512 + .5)/511) / projection[1,1]
    valid_xy = (np.abs(screen_x * projection[0,0]) <= 1) & (np.abs(screen_y * projection[1,1]) <= 1)
    origins = inverse[:3,3] + screen_x[:,None]*inverse[:3,0] + screen_y[:,None]*inverse[:3,1]
    direction = -inverse[:3,2]
    actual_t = arrays['triangle_ids'].ravel()[ids]
    actual_o = arrays['owners'].ravel()[ids]
    actual_d = arrays['depth'].ravel()[ids]
    actual_p = arrays['patch_owners'].ravel()[ids]
    best = np.full(len(ids), np.inf)
    owner = np.full(len(ids), -1)
    triangle = np.full(len(ids), -1)
    near_band = np.zeros(len(ids), dtype=bool)
    claimed_valid = np.zeros(len(ids), dtype=bool)
    claimed_weight = np.full(len(ids), -np.inf)
    claimed_depth_error = np.full(len(ids), np.inf)
    face_id = 0
    for object_id, mesh in enumerate(meshes):
        vertices = np.asarray(mesh['vertices'], dtype=float)
        for face in mesh['faces']:
            a,b,c = vertices[face]
            e,f = b-a,c-a
            normal = np.cross(e,f)
            denominator = normal @ direction
            if denominator == 0:
                face_id += 1
                continue
            depth = ((a-origins) @ normal)/denominator
            delta = origins + depth[:,None]*direction-a
            gram = np.array([[e@e,e@f],[e@f,f@f]])
            uv = (np.linalg.inv(gram) @ np.stack((delta@e,delta@f))).T
            weight = np.minimum(np.minimum(uv[:,0],uv[:,1]),1-uv[:,0]-uv[:,1])
            valid = valid_xy & (weight >= -1e-8) & (depth >= pose['near']) & (depth <= pose['far'])
            near_band |= valid & (weight <= 1e-8)
            finite = np.isfinite(best)
            ties = np.zeros(len(ids), dtype=bool)
            ties[finite] = np.abs(depth[finite]-best[finite]) <= 1e-8
            near_band |= valid & ties
            closer = valid & (depth < best)
            best[closer],owner[closer],triangle[closer] = depth[closer],object_id,face_id
            claimed = actual_t == face_id
            claimed_valid[claimed] = valid[claimed] & (actual_o[claimed] == object_id)
            claimed_weight[claimed] = weight[claimed]
            claimed_depth_error[claimed] = np.abs(depth[claimed]-actual_d[claimed])
            face_id += 1
    fg = actual_o >= 0
    require(np.array_equal(np.isfinite(best),fg), 'independent foreground/background probe rays')
    require(np.all(claimed_valid[fg]), 'every saved foreground has current source intersection')
    error = float(np.max(claimed_depth_error[fg])) if np.any(fg) else 0
    near_error = float(np.max(np.abs(best[fg]-actual_d[fg]))) if np.any(fg) else 0
    require(error <= 1e-10 and near_error <= 1e-10, 'all current source/nearest depths within 1e-10m')
    certain = fg & ~near_band
    require(np.array_equal(owner[certain],actual_o[certain]) and np.array_equal(triangle[certain],actual_t[certain]),
            'unambiguous saved current owner and triangle')
    target = []
    edges = boundary_mask(arrays['color'],arrays['patch_owners']).ravel()[ids]
    for patch, roi in enumerate(arrays['patch_roi_ids'].tolist()):
        mask = fg & (actual_p == patch)
        if frame.get('scope_id','global') == 'global':
            continue
        require(np.all(claimed_weight[mask] >= -1e-12), 'local witness strict source membership')
        usable = mask & ~near_band
        require(int(usable.sum()) >= 16 and int(np.count_nonzero(usable & edges)) >= 4,
                'local witness readable after removing every ambiguous pixel')
        target.append(dict(roi_id=roi,source_pixels=int(mask.sum()),ambiguous=int(np.count_nonzero(mask&near_band)),
            certain_pixels=int(usable.sum()),certain_boundary=int(np.count_nonzero(usable&edges))))
    result = dict(source_pixels=int(fg.sum()),probes=len(ids)-int(fg.sum()),ambiguous=int(np.count_nonzero(fg&near_band)),
        cross_object_ambiguous=int(np.count_nonzero(fg&near_band&(actual_o!=owner))),
        cross_patch_ambiguous=int(np.count_nonzero(fg&near_band&(actual_p!=arrays['face_patch_ids'][triangle]))),
        max_source_depth_error=error,max_nearest_depth_error=near_error,local_targets=target)
    RAY_CACHE[key]=result
    return result


def check_frame(frame, scope, capture, sequence):
    binding,facts = scope['binding'],scope['facts']
    require(frame.get('scope_id',scope['scope_id']) == scope['scope_id'], 'frame scope id')
    require(frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['scene_identity'] == binding['geometry_identity']
            and frame['candidate_identity'] == binding['camera_identity']
            and frame['source_revision'] == binding['scene_revision'], 'frame source geometry camera binding')
    require(frame['pose'] == next(p for p in binding['camera_specification']['views'] if p['name']==frame['view_name']),
            'actual saved pose equals its own scope camera')
    png,npz = raw(frame['image_path']),raw(frame['arrays_path'])
    require(hashlib.sha256(png).hexdigest()==frame['image_sha256']
            and hashlib.sha256(npz).hexdigest()==frame['arrays_sha256'], 'PNG and NPZ file digests')
    with np.load(BytesIO(npz),allow_pickle=False) as z:
        arrays = {k:z[k] for k in z.files}
    require(np.array_equal(np.asarray(Image.open(BytesIO(png))),arrays['color']), 'actual PNG equals saved RGB')
    for name,metadata in frame['arrays'].items():
        a=arrays[name]
        require(metadata==dict(dtype=str(a.dtype),shape=list(a.shape),nbytes=a.nbytes,
                sha256=hashlib.sha256(a.tobytes()).hexdigest()), 'array metadata/'+name)
    meshes=capture['meshes']
    offsets=np.cumsum([0]+[len(m['faces']) for m in meshes])
    patch_rows=facts['scope']['patch_support']['regions']
    patch=np.full(offsets[-1],-1,dtype=np.int32)
    for pi,row in enumerate(patch_rows):
        indices=offsets[row['object_index']]+np.asarray(row['triangle_indices'])
        require(np.all(patch[indices]==-1),'source triangle patch assigned once')
        patch[indices]=pi
    require(np.array_equal(arrays['face_patch_offsets'],offsets)
            and np.array_equal(arrays['face_patch_ids'],patch)
            and arrays['patch_roi_ids'].tolist()==[p['roi_id'] for p in patch_rows], 'complete ordered patch-source mapping')
    geometry=[(tuple(tuple(Fraction(v) for v in p) for p in m['vertices']),tuple(tuple(f) for f in m['faces'])) for m in meshes]
    mapping=sha(dict(version='active-patch-owner-v1',roi_ids=tuple(p['roi_id'] for p in patch_rows),
        ordered_geometry=geometry,face_patch_ids=[patch[offsets[i]:offsets[i+1]].tolist() for i in range(len(meshes))]))
    owner_mapping=sha(('active-dual-owner-v1','zero-based-global-source-triangles-in-mesh-order',mapping,offsets.tolist()))
    require(mapping==frame['patch_mapping_identity']==arrays['patch_mapping_identity'].item()
            and owner_mapping==frame['owner_mapping_identity']==arrays['owner_mapping_identity'].item(),'mapping identity preimages')
    identity=sha(((frame['scene_identity'],frame['candidate_identity']),frame['owner_schema'],owner_mapping,
                  frame['view_name'],sequence,frame['image_sha256']))
    require(identity==frame['frame_identity'],'frame identity preimage')
    reference=sha((binding['binding_sha256'],frame['view_name'],frame['image_sha256'],mapping,
                   frame['owner_schema'],owner_mapping,identity))
    require('active-host-image:'+reference==frame['image_ref'],'current host image ref preimage')
    o,t,p=arrays['owners'],arrays['triangle_ids'],arrays['patch_owners']
    fg=o>=0
    require(np.array_equal(t>=0,fg) and np.all(t[fg]>=offsets[o[fg]]) and np.all(t[fg]<offsets[o[fg]+1])
            and np.array_equal(p[fg],patch[t[fg]]),'all foreground owner/source triangle/patch rows')
    require(np.isposinf(arrays['depth'][~fg]).all() and (arrays['color'][~fg]==[18,22,30]).all(),'actual background arrays')
    observation=next(x for x in facts['observations'] if x['view_name']==frame['view_name'])
    require(all(observation[k]==frame[k] for k in ('image_ref','image_sha256','image_path')),'observation references actual frame')
    if 'scope_id' in frame:
        require(observation['frame_identity']==identity and observation['scope_id']==scope['scope_id'],'scoped observation identity')
    boundary=boundary_mask(arrays['color'],p)
    pixel_rows={x['roi_id']:x for x in observation['pixel_rows']}
    for pi,row in enumerate(patch_rows):
        mask=p==pi
        count,bcount=int(mask.sum()),int(np.count_nonzero(mask&boundary))
        pixel=pixel_rows[row['roi_id']]
        require(count==pixel['visible_surface_pixels'] and bcount==pixel['contrasting_boundary_pixels'], 'actual pixel surface/boundary count')
        require(pixel['minimum_surface_pixels']==16 and pixel['minimum_boundary_pixels']==4
                and pixel['minimum_rgb_boundary_contrast']==24
                and pixel['readable']==(pixel['front_facing'] and count>=16 and bcount>=4),'unchanged readability gates')
    result=rays(frame,meshes,arrays)
    FRAME_RECORDS[frame['image_path']]=dict(frame_identity=identity,scope_id=scope['scope_id'],view=frame['view_name'],
        image_sha256=frame['image_sha256'],array_sha256=frame['arrays_sha256'],ray_review=result)
    return arrays


def compare_public(public,full,blocks):
    task=full['facts'].get('region_task')
    if public.get('schema')=='active-observation-region-task-brief-v1':
        require(task is not None,'brief region task exists')
        require(public['region_task']['conditions']==task['conditions']
                and public['region_task']['summary']==task['summary'],'brief exact conditions and denominators')
        wanted=copy.deepcopy(task['rows'])
        selected={f['frame_identity']:i+1 for i,f in enumerate(full['frames'])}
        for row in wanted:
            if row['complete_witness']:
                row['complete_witness']['native_content_block_index']=selected.get(row['complete_witness']['frame_identity'])
        require(public['region_task']['rows']==wanted,'brief exact source facts and witness projection')
        require(public['binding']=={k:v for k,v in full['binding'].items()
                if k not in ('schema','objects','camera_policy','camera_specification')},'brief exact parent source binding')
        require(public['objects']['rows']==[[o[k] for k in public['objects']['columns']] for o in full['binding']['objects']],
                'brief parent object table')
        expected_images=[[f[k] for k in public['images']['columns'][:-1]]+[i+1] for i,f in enumerate(full['frames'])]
        require(public['images']['rows']==expected_images,'brief exact scoped image table/native block indices')
        expected_scopes=[[s['scope_id'],s['binding']['camera_identity'],s['binding']['binding_sha256'],
            len(s['frame_refs']),len(s['facts']['coverage']['covered_roi_ids'])] for s in full['scopes']]
        require(public['scopes']['rows']==expected_scopes,'brief exact scope camera/source/count table')
        expected_pixels=[]
        by_scope={s['scope_id']:s for s in full['scopes']}
        for row in task['rows']:
            witness=row['complete_witness']
            if witness:
                scope=by_scope[witness['scope_id']]
                observation=next(x for x in scope['facts']['observations'] if x['frame_identity']==witness['frame_identity'])
                pixel=observation['pixel_rows'][witness['pixel_row_index']]
                expected_pixels.append([witness['scope_id'],witness['frame_identity'],row['roi_id'],
                    pixel['visible_surface_pixels'],pixel['contrasting_boundary_pixels'],pixel['visible_pixel_bounds'],pixel['visible_pixel_anchor']])
        require(public['witness_pixels']['rows']==expected_pixels,'brief exact witness pixel table')
        require(public['image_delivery']['local_verified_image_count']==len(full['constructed_frames'])
                and public['image_delivery']['mcp_content_constructed_image_count']==len(full['frames']), 'constructed and delivered counts separate')
    elif 'facts' in public:
        require(public['facts']==full['facts'] and public['scopes']==full['scopes']
                and public['constructed_frames']==full['constructed_frames'],'full exact facts scopes constructed original')
        require(public['binding']=={k:v for k,v in full['binding'].items() if k!='camera_specification'},'full parent binding projection')
    else:
        require(public['schema']=='active-observation-brief-v5','legacy public brief version5')
    images=[b for b in blocks if b['type']=='image']
    require(len(images)==len(full['frames']),'selected actual native image count')
    for image,frame in zip(images,full['frames']):
        require(image['mimeType']=='image/png' and base64.b64decode(image['data'],validate=True)==raw(frame['image_path']),
                'native selected bytes equal original frame PNG')


def review_session(session):
    captures=wire_captures(session)
    calls=rows(session/'PUBLIC_REQUESTS.jsonl')
    index=rows(session/'product_full/INDEX.jsonl')
    require(len(calls)==len(index)==(7 if session.name=='state' else 1),'one producer archive per public call')
    results=[]
    for call,entry in zip(calls,index):
        label=session.name+'/'+str(call['internal_public_call_index'])
        tx,rx=read(call['actual_TX_path']),read(call['actual_RX_path'])
        require(tx==call['request']==read(call['request_path']) and rx==call['response']==read(call['response_path']),label+'/original public wire')
        require(hashlib.sha256(raw(call['actual_TX_path'])).hexdigest()==call['actual_TX_sha256']
                and hashlib.sha256(raw(call['actual_RX_path'])).hexdigest()==call['actual_RX_sha256'],label+'/wire hashes')
        require(rx['id']==tx['id'] and rx['result']['isError'] is False,label+'/original success flags')
        require(entry==call['producer_archive'] and entry['index']==call['producer_archive_index'],label+'/independent archive correlation')
        require(entry['sha256']==hashlib.sha256(raw(entry['path'])).hexdigest(),label+'/same producer archive digest')
        full=read(entry['path'])
        capture=bound_capture(full,captures,label)
        binding_hash(full['binding'])
        blocks=rx['result']['content']
        texts=[json.loads(b['text']) for b in blocks if b['type']=='text']
        require(len(texts)==1,label+'/one JSON text')
        public=texts[0]
        compare_public(public,full,blocks)
        task=full['facts'].get('region_task')
        scopes=full.get('scopes',[dict(scope_id='global',binding=full['binding'],facts=full['facts'])])
        constructed=full.get('constructed_frames',full['frames'])
        all_frames={f['frame_identity']:f for f in constructed}
        require(len(all_frames)==len(constructed),label+'/unique constructed identities')
        for f in full['frames']:
            require(f==all_frames[f['frame_identity']],label+'/selected original constructed frame')
        for scope in scopes:
            source=scope['binding']
            binding_hash(source,scope['scope_id']!='global')
            require(all(source[k]==full['binding'][k] for k in ('capture_state','document_epoch','scene_revision','objects','geometry_identity')),
                    label+'/all scopes same captured source')
            fs=[f for f in constructed if f.get('scope_id','global')==scope['scope_id']]
            if 'frame_refs' in scope:
                require(scope['frame_refs']==[f['frame_identity'] for f in fs],label+'/scope exact frame order')
            if scope['scope_id']!='global':
                require(source['parent_binding_sha256']==full['binding']['binding_sha256']
                        and source['parent_source_binding_sha256']==full['binding']['source_binding_sha256'],label+'/local parent binding')
            for number,f in enumerate(fs,1):
                if f['image_path'] not in FRAME_RECORDS:
                    check_frame(f,scope,capture,number)
        if task:
            names={row['object_name'] for row in task['rows']}
            require(names==({'Obj_02','Obj_06'} if task['conditions']['normal_z_min']==1 else {'Obj_02','Obj_06','Obj_09'}),label+'/task eligible set')
            summary=task['summary']
            require(summary['eligible_region_count']==len(names) and summary['unknown_region_count']==1
                    and summary['observed_region_count']==len(names)-1 and summary['unsupported_triangle_count']==12
                    and summary['source_triangle_count']==56 and summary['supported_region_count']==22,label+'/task denominator status')
            for row in task['rows']:
                source=row['source'];mesh=capture['meshes'][row['object_index']]
                require(source['source_triangle_indices']==row['source_triangle_indices']==[0,1]
                        and source['ordered_geometry_sha256']==ordered(mesh),label+'/task actual source rows and geometry hash')
                require(all(source[k]==full['binding'][k] for k in ('document_epoch','scene_revision','capture_state'))
                        and source['parent_binding_sha256']==full['binding']['binding_sha256'],label+'/task current source parent')
                witness=row['complete_witness']
                if row['object_name']=='Obj_06':
                    require(row['status']=='unknown' and witness is None and row['reason']=='positive_area_occlusion_all_front_views',label+'/covered true unknown')
                    continue
                require(row['status']=='covered' and witness['selected_for_delivery'] is True,label+'/open actual witness')
                frame=all_frames[witness['frame_identity']]
                scope=next(s for s in scopes if s['scope_id']==witness['scope_id'])
                require(scope['binding']['region_source']==source and frame['image_ref']==witness['image_ref'],label+'/current child source witness')
                observation=next(x for x in scope['facts']['observations'] if x['frame_identity']==frame['frame_identity'])
                pixel=observation['pixel_rows'][witness['pixel_row_index']]
                require(pixel['roi_id']==row['roi_id'] and pixel['readable'] is True,label+'/same actual readable pixel witness')
            require(full['work']['capture_calls']==1,label+'/one actual capture')
            if not full['work']['result_cache_hit']:
                require(full['work']['mapping_calls']==full['work']['geometry_parse_calls']==full['work']['mesh_conversions']==full['work']['partition_calls']==1,
                        label+'/one mapping parse conversion partition')
        results.append(dict(index=call['internal_public_call_index'],task=task,full=full,capture=capture,public_schema=public.get('schema'),
                            native_count=sum(b['type']=='image' for b in blocks),new_rasters=full['work']['raster_attempts']))
    return dict(session=session.name,calls=results)


def main():
    sessions=[review_session(p) for p in sorted(ROOT.iterdir()) if p.is_dir()]
    lookup={s['session']:s for s in sessions}
    paired=[]
    for i in (1,2,3):
        a,b=[lookup[f'pair{i}_{version}']['calls'][0] for version in ('R0','R1')]
        require([(m['vertices'],m['faces']) for m in a['capture']['meshes']]
                ==[(m['vertices'],m['faces']) for m in b['capture']['meshes']],f'pair{i}/exact ordered capture')
        clean=lambda r:[{k:v for k,v in row.items() if k not in ('source','complete_witness','instance_id')} for row in r['task']['rows']]
        require(clean(a)==clean(b),f'pair{i}/exact task geometric facts and outcomes')
        for fa,fb in zip(a['full']['frames'],b['full']['frames']):
            require(fa['pose']==fb['pose'] and raw(fa['image_path'])==raw(fb['image_path']),f'pair{i}/selected exact camera PNG')
            with np.load(fa['arrays_path'],allow_pickle=False) as za,np.load(fb['arrays_path'],allow_pickle=False) as zb:
                require(za.files==zb.files and all(np.array_equal(za[k],zb[k]) for k in za.files),f'pair{i}/selected every RGB depth owner patch array exact')
        require(a['new_rasters']==8 and b['new_rasters']==3 and a['native_count']==b['native_count']==3,f'pair{i}/8 to3 construction same3delivery')
        paired.append(dict(pair=i,passed=True))
    state=lookup['state']['calls']
    require([c['new_rasters'] for c in state]==[6,3,0,0,2,3,3],'state exact generation raster sequence')
    require([c['full']['binding']['capture_state']['revision'] for c in state]==[1,1,1,1,1,2,3],'state exact revisions')
    for i in (2,3):
        require(state[i]['full']['frames']==state[1]['full']['frames'] and state[i]['full']['work']['result_cache_hit'] is True,
                'state cache reuses exact source frames')
    base={m['name']:m for m in state[1]['capture']['meshes']}
    moved={m['name']:m for m in state[5]['capture']['meshes']}
    restored={m['name']:m for m in state[6]['capture']['meshes']}
    for name in base:
        expected=[[p[0]+.25,p[1],p[2]] if name=='Obj_02' else p for p in base[name]['vertices']]
        require(moved[name]['vertices']==expected and moved[name]['faces']==base[name]['faces'],'state exact +.25 only '+name)
        require(restored[name]['vertices']==base[name]['vertices'] and restored[name]['faces']==base[name]['faces'],'state exact restore '+name)
    require(state[6]['full']['binding']['binding_sha256']!=state[1]['full']['binding']['binding_sha256'],'restored geometry current new binding')
    total_requests=sum(len(s['calls']) for s in sessions)
    total_native=sum(c['native_count'] for s in sessions for c in s['calls'])
    rasters=sum(c['new_rasters'] for s in sessions for c in s['calls'])
    require((total_requests,total_native,rasters,len(FRAME_RECORDS))==(14,44,58,58),'total14requests44native58constructed58files')
    result=dict(status='passed',checks=len(CHECKS),fixed_commit=AUTHOR,new_live=0,new_raster=0,new_models=0,
        totals=dict(public_requests=total_requests,native_image_blocks=total_native,new_producer_rasters=rasters,unique_saved_frames=len(FRAME_RECORDS)),
        paired=paired,state_rasters=[c['new_rasters'] for c in state],
        sessions=[dict(session=s['session'],calls=[dict(index=c['index'],schema=c['public_schema'],new_rasters=c['new_rasters'],native_count=c['native_count']) for c in s['calls']]) for s in sessions],
        frame_records=FRAME_RECORDS,unique_ray_checks=len(RAY_CACHE),input_pins=PINS,assertions=CHECKS)
    (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],totals=result['totals'],unique_ray_checks=len(RAY_CACHE))))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error),last_checks=CHECKS[-8:],passed_checks=len(CHECKS)),indent=2),encoding='utf8')
        raise
