"""Audit directed focus using the original installed-product packets and NPZ buffers."""
import argparse
import base64
from fractions import Fraction
from hashlib import sha256
from itertools import accumulate
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

BATCH = 'M4-NEAREST-FOCUS-OCCLUSION-MOVE-001'
PLAN_SHA = '2bc87832d55e7508d36ed1a53fff485168f30677cf2542c7d56ea6297515072d'
A_COMMIT = 'ad35b150b1cdc3d90a9de894d49ebaf2148efc88'
A_RUNTIME = 'ba95b60a131613f723bdb4a0ff8cbade5ab39af0903c2269a5548fefc0de7c04'
PRIMARY = ('OPEN_POS_X', 'OPEN_NEG_X', 'VISIBLE', 'SEALED')
SIDE = {'OPEN_POS_X': 1, 'OPEN_NEG_X': -1}
THRESHOLD = 16


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def hash_bytes(data):
    return sha256(data).hexdigest()


def pin(path):
    p = Path(path).resolve(strict=True)
    data = p.read_bytes()
    return {'path': str(p), 'bytes': len(data), 'sha256': hash_bytes(data)}


def canonical(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True,
                      allow_nan=False).encode('utf8')


def fingerprint(value):
    return hash_bytes(canonical(value))


def interval(row, name):
    start, end, elapsed = (row[key] for key in ('started_ns','closed_ns','elapsed_ns'))
    require(type(start) is type(end) is type(elapsed) is int and 0 <= start <= end
            and elapsed == end - start, 'invalid_stage_interval/' + name)
    return start, end, elapsed


def vsub(a, b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def vdot(a, b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def vcross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def rational_point(row):
    return tuple(map(Fraction,row))


def source_triangle(mesh, index):
    require(type(index) is int and 0 <= index < len(mesh['faces']), 'source_face_index_not_current')
    return [rational_point(mesh['vertices'][v]) for v in mesh['faces'][index]]


def on_triangle(point, triangle):
    a,b,c = triangle
    n = vcross(vsub(b,a),vsub(c,a))
    return (any(n) and vdot(n,vsub(point,a)) == 0 and
            all(vdot(n,vcross(vsub(y,x),vsub(point,x))) >= 0 for x,y in ((a,b),(b,c),(c,a))))


def named(capture, name):
    rows = [(i,m) for i,m in enumerate(capture['meshes']) if m['name']==name]
    require(len(rows)==1, 'actual_capture_name_not_unique/' + name)
    return rows[0]


def exact_gap(target, reference, winner=0):
    """Derive the fixture's global minimum from vertical separation and footprint inclusion."""
    triangle = source_triangle(target,winner)
    plane = triangle[0][2]
    require(all(v[2]==plane for v in triangle), 'winner_not_horizontal')
    dz = None
    for index in range(len(reference['faces'])):
        row = source_triangle(reference,index)
        reference_z = row[0][2]
        require(all(p[2]==reference_z for p in row)
                and all(on_triangle((p[0],p[1],plane),triangle) for p in row),
                'reference_footprint_not_in_true_winner')
        require(dz in (None,plane-reference_z), 'reference_is_not_constant_height')
        dz = plane-reference_z
    require(dz is not None and dz > 0, 'no_exact_positive_reference_gap')
    for index in range(len(target['faces'])):
        if index == winner:
            continue
        zs = [p[2] for p in source_triangle(target,index)]
        require(min(zs)>plane or max(zs)<plane-2*dz, 'nonwinner_vertical_lower_bound_failed')
    return dz*dz


def audit_nearest(capture, producer, body, target_name, reference_name, winner):
    focus = body['facts']['focus']
    require(focus==producer['facts']['focus'], 'public_focus_not_same_producer')
    selected_index,target = named(capture,target_name)
    _,reference = named(capture,reference_name)
    expected_sq = exact_gap(target,reference,winner)
    near = focus['nearest_surface']
    w = near['witness']
    instances = capture['host_identity']['object_instances']
    ordered = [{'host_id':mesh['object_id'],'instance_id':instances[mesh['object_id']],
                'vertices':mesh['vertices'],'faces':mesh['faces']} for mesh in capture['meshes']]
    generation = {key:capture['capture_state'][key] for key in ('instance_id','epoch','revision')}
    ref = focus['region_ref']
    require(near['status']=='measured' and w['ordered_geometry_sha256']==fingerprint(ordered)
            and ref['ordered_geometry_sha256']==w['ordered_geometry_sha256']
            and body['binding']['capture_state']==capture['capture_state']
            and body['binding']['scene_revision']==capture['revision']
            and ref['document_epoch']==capture['host_identity']['document_epoch']
            and ref['capture_generation']==generation
            and ref['region_id']=='source-region:'+fingerprint({k:v for k,v in ref.items() if k!='region_id'}),
            'nearest_not_bound_to_original_ordered_capture')
    require(focus['primary_source_triangle_index']==w['a']['source_triangle_index']==winner
            and focus['task_source_triangle_indices']==ref['source_triangle_indices']==[winner]
            and ref['host_id']==target['object_id'] and ref['instance_id']==instances[target['object_id']]
            and focus['reference']['host_id']==reference['object_id']
            and focus['reference']['instance_id']==instances[reference['object_id']],
            'incorrect_bound_primary_or_target_reference')
    points,indices = [],[]
    for label,mesh in (('a',target),('b',reference)):
        endpoint = w[label]
        point = rational_point(endpoint['point_m'])
        row = endpoint['source_triangle_index']
        require(endpoint['host_id']==mesh['object_id']
                and endpoint['instance_id']==instances[mesh['object_id']]
                and on_triangle(point,source_triangle(mesh,row)), 'invalid_endpoint_source_row/'+label)
        points.append(point)
        indices.append(row)
    delta = vsub(*points)
    expected = math.sqrt(float(expected_sq))
    require(vdot(delta,delta)==expected_sq and math.isclose(near['distance_m'],expected,rel_tol=2e-15),
            'independent_exact_distance_mismatch')
    return selected_index, {'distance_m':near['distance_m'],'distance_sq_m2':str(expected_sq),
                             'points_m':[list(map(str,p)) for p in points],'source_rows':indices}


def verify_pose(frame):
    pose = frame['pose']
    view = np.asarray(pose['view_matrix'],dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'],dtype=np.float64)
    direction = np.asarray(pose['target_to_eye_unit'],dtype=np.float64)
    eye = np.asarray(pose['camera_eye_world_m'],dtype=np.float64)
    target = np.asarray(pose['target_world_m'],dtype=np.float64)
    rotation = view[:3,:3]
    require(all(np.isfinite(m).all() for m in (view,projection,direction,eye,target))
            and pose['name']==frame['view_name'] and pose['projection']=='orthographic'
            and pose['size_px']==[512,512]
            and np.allclose(rotation@rotation.T,np.eye(3),rtol=0,atol=2e-12)
            and np.allclose(view[2,:3],direction,rtol=0,atol=2e-12)
            and np.allclose(view[:3,3],-(rotation@eye),rtol=0,atol=2e-12)
            and np.linalg.norm(eye-target)>0
            and np.allclose((eye-target)/np.linalg.norm(eye-target),direction,rtol=0,atol=2e-12)
            and np.array_equal(projection,np.diag(projection.diagonal())+
                               np.outer(projection[:,3]-np.array([0,0,0,projection[3,3]]),[0,0,0,1])),
            'frame_pose_not_actual_consistent_orthographic_view')
    return direction,view,projection


def pixel_points(y,x,depth,view,projection):
    u = 2*(x+.5)/511 - 1
    v = 1 - 2*(y+.5)/511
    camera = np.column_stack(((u-projection[0,3])/projection[0,0],
                              (v-projection[1,3])/projection[1,1],-depth[y,x]))
    return (camera-view[:3,3]) @ view[:3,:3]


def check_point_cloud(points, corners):
    a,b,c = np.asarray(corners,dtype=np.float64)
    normal = np.cross(b-a,c-a)
    norm_sq = normal@normal
    scale = 2e-9*max(1,np.sqrt(norm_sq))
    require(norm_sq>0 and np.all(np.abs((points-a)@normal)<=scale)
            and all(np.all(np.cross(r-q,points-q)@normal >= -scale)
                    for q,r in ((a,b),(b,c),(c,a))),
            'pixels_do_not_reproject_to_current_winning_triangle')


def independently_unblocked(point, direction, capture, display_mask, selected_index, winner):
    # An ordinary world-space ray, independent of the engine's sparse or full raster.
    for oid, mesh in enumerate(capture['meshes']):
        if not display_mask[oid]:
            continue
        vertices = np.asarray(mesh['vertices'],dtype=np.float64)
        for row, indices in enumerate(mesh['faces']):
            if (oid,row)==(selected_index,winner):
                continue
            a,b,c = vertices[indices]
            normal = np.cross(b-a,c-a)
            divisor = normal@direction
            if abs(divisor)<1e-14:
                continue
            t = (normal@(a-point))/divisor
            if t <= 1e-8:
                continue
            q = point + t*direction
            if all(np.cross(y-x,q-x)@normal>=-2e-12 for x,y in ((a,b),(b,c),(c,a))):
                return False
    return True


def audit_frame(scope, frame, capture, producer, selected_index, winner, anchor=None):
    paths = [Path(frame[key]).resolve(strict=True) for key in ('image_path','arrays_path')]
    require(all(path.is_relative_to(scope) for path in paths), 'frame_escaped_current_arm')
    png,npz = (pin(path) for path in paths)
    require(png['sha256']==frame['image_sha256'] and png['bytes']==frame['PNG_bytes']
            and npz['sha256']==frame['arrays_sha256'] and npz['bytes']==frame['compressed_array_file_bytes']
            and png['bytes']>0 and npz['bytes']>0, 'frame_bytes_digest_or_length_mismatch')
    frame_id = frame['frame_identity']
    region_id = producer['facts']['focus']['region_ref']['region_id']
    lineage = producer['binding']
    require(frame['image_ref']=='source-region-image:'+fingerprint((region_id,frame_id,png['sha256']))
            and frame['source_revision']==capture['revision']==lineage['scene_revision']
            and frame['display_identity']==lineage['display_identity'],
            'frame_path_digest_not_same_production_capture')
    image_scope = frame['image_scope']
    display_mask = image_scope['participation_mask']
    instances = capture['host_identity']['object_instances']
    captured_display = {o['host_id']:o for o in capture['display_snapshot']['objects']}
    require(len(image_scope['objects'])==len(capture['meshes'])==len(display_mask),
            'incomplete_frame_object_scope')
    for i, (obj, row) in enumerate(zip(capture['meshes'],image_scope['objects'],strict=True)):
        host_id = obj['object_id']
        raw_display = captured_display[host_id]
        require(row['object_index']==i and row['host_id']==host_id and row['instance_id']==instances[host_id]
                and row['object_name']==obj['name'] and row['participates']==display_mask[i]
                and display_mask[i]==raw_display['visible_get'], 'frame_scope_object_display_mismatch')
    direction,view,projection = verify_pose(frame)
    with np.load(paths[1],allow_pickle=False) as data, Image.open(paths[0]) as decoded:
        color = data['color']
        owners = data['owners']
        source_ids = data['triangle_ids']
        depth = data['depth']
        offsets = data['face_patch_offsets']
        expected = tuple(accumulate((len(m['faces']) for m in capture['meshes']),initial=0))
        require(color.dtype==np.uint8 and color.shape==(512,512,3) and decoded.mode=='RGB'
                and np.array_equal(np.asarray(decoded),color)
                and owners.dtype==source_ids.dtype==np.int32 and depth.dtype==np.float64
                and owners.shape==source_ids.shape==depth.shape==(512,512)
                and tuple(offsets)==expected and list(data['display_object_mask'])==display_mask
                and data['display_identity'].item()==frame['display_identity']
                and data['triangle_id_scope'].item()==frame['triangle_id_scope'],
                'PNG_NPZ_channels_scope_or_source_offset_mismatch')
        for name in ('color','owners','triangle_ids','depth','face_patch_offsets'):
            require(hash_bytes(np.ascontiguousarray(data[name]).tobytes())==frame['arrays'][name]['sha256'],
                    'frame_array_metadata_mismatch/'+name)
        finite = np.isfinite(depth)
        require(np.array_equal(finite,owners>=0) and np.array_equal(finite,source_ids>=0)
                and np.all(depth[finite]>0) and np.all(owners[finite]<len(capture['meshes'])),
                'invalid_depth_owner_coverage')
        owned = owners[finite]
        actual = source_ids[finite]
        require(np.all(np.asarray(display_mask,dtype=bool)[owned])
                and np.all(offsets[owned]<=actual) and np.all(actual<offsets[owned+1]),
                'owner_source_mapping_not_current_capture')
        mask = finite & (owners==selected_index) & (source_ids==offsets[selected_index]+winner)
        y,x = np.nonzero(mask)
        count = int(y.size)
        if count:
            check_point_cloud(pixel_points(y,x,depth,view,projection),source_triangle(capture['meshes'][selected_index],winner))
        if anchor is not None:
            row,col = anchor['row'],anchor['column']
            require(type(row) is type(col) is int and 0<=row<512 and 0<=col<512
                    and anchor['source_triangle_index']==winner and mask[row,col],
                    'public_anchor_not_on_winning_source_in_original_frame')
            world = pixel_points(np.asarray([row]),np.asarray([col]),depth,view,projection)[0]
            require(independently_unblocked(world,direction,capture,display_mask,selected_index,winner),
                    'claimed_anchor_ray_intersects_displayed_blocker')
    return {'frame_identity':frame_id,'image_ref':frame['image_ref'],'view':frame['view_name'],
            'target_to_eye_unit':direction.tolist(),'winning_source_pixels':count,'PNG':png,'NPZ':npz,
            'raster_ns':interval(frame['stages']['actual_raster'],'actual_raster')[2]}


def public_payload(reply):
    require('error' not in reply and not reply['result']['isError'],'tool_rejected')
    blocks = reply['result']['content']
    text = [item for item in blocks if item['type']=='text']
    imgs = [item for item in blocks if item['type']=='image']
    require(len(text)==1 and all(item['mimeType']=='image/png' for item in imgs),
            'unexpected_public_content')
    return json.loads(text[0]['text']),[base64.b64decode(i['data'],validate=True) for i in imgs]


def check_probe(work, stages, second, enabled):
    name = 'focus_view_direction_selection'
    if not enabled:
        require(work.get('focus_view_probe_views',0)==work.get('focus_view_probe_samples',0)==0
                and name not in stages,'probe_outside_only_second_view')
        return {'views':0,'samples':0,'selection_ns':0}
    probe = stages[name]
    count = work['focus_view_probe_views']
    samples = work['focus_view_probe_samples']
    grid = probe['grid_size']
    directions = probe['directions_world']
    votes = probe['votes']
    choice = probe['chosen_candidate']
    require(type(count) is int and 1<=count<=9 and type(grid) is int and 1<=grid<=8
            and type(samples) is int and samples==grid**2*count
            and len(votes)==count and set(votes)<=set(directions)
            and all(type(v) is int and 0<=v<=grid**2 for v in votes.values())
            and type(choice) is str and choice in directions and (not votes or choice in votes)
            and (not votes or votes[choice]==max(votes.values()))
            and np.allclose(directions[choice],second['target_to_eye_unit'],rtol=0,atol=2e-12),
            'chosen_probe_direction_or_budget_not_bound_to_actual_camera')
    return {'views':count,'samples':samples,'selection_ns':interval(probe,name)[2],
            'votes':votes,'chosen_candidate':choice,'directions_world':directions}


def audit_call(arm,label,scope,tx,reply,producer,capture,timing, target,reference,winner):
    args = tx['params']['arguments']
    q = args['query']
    include_image = args.get('include_image',True)
    require(tx['id']==reply['id'] and tx['method']=='tools/call'
            and tx['params']['name']=='human_eye_scene_observe' and q['mode']=='active_observation'
            and q['objects']==[{'name':target}] and q['focus']=={
                'task_region':{'reference':{'name':reference},'relation':'nearest_surface'}},
            'original_request_not_expected_current_task')
    body,images = public_payload(reply)
    oid,near = audit_nearest(capture,producer,body,target,reference,winner)
    work = producer['work']
    stages = producer['stages']
    status = body['status']
    focus = body['facts']['focus']
    sample = focus['sample']
    physical = producer['constructed_frames']
    delivered = producer['frames']
    prefix = label.split('_WARM')[0].split('_NO_IMAGE')[0]
    warm = label.endswith('_WARM')
    no_image = label.endswith('_NO_IMAGE')
    require(include_image!=no_image and status==producer['status']
            and focus['minimum_sample_pixels']==THRESHOLD and len(physical)<=2,
            'incorrect_image_mode_status_or_frame_limit')
    checked=[]
    for frame in physical:
        anchor = sample['sampled_pixel'] if sample and frame['frame_identity']==sample['frame_identity'] else None
        checked.append(audit_frame(scope,frame,capture,producer,oid,winner,anchor))
    views = focus['views']
    require(no_image or [(v['view_name'],v['verified_pixels'],v['primary_verified_pixels']) for v in views]
            ==[(f['view'],f['winning_source_pixels'],f['winning_source_pixels']) for f in checked],
            'public_attempts_pixels_not_equal_independent_arrays')
    first = next((i for i,row in enumerate(checked,1) if row['winning_source_pixels']>=THRESHOLD),None)
    if include_image and delivered:
        require(len(delivered)==len(images)==len(body['frames'])==1 and isinstance(sample,dict),
                'inconsistent_public_image_frame_count')
        frame = delivered[0]
        public = body['frames'][0]
        picked = next(f for f in checked if f['frame_identity']==frame['frame_identity'])
        require(all(frame[key]==public[key]==sample[key] for key in ('view_name','frame_identity','image_ref'))
                and public['image_sha256']==frame['image_sha256']
                and frame['image_sha256']==hash_bytes(images[0])==picked['PNG']['sha256']
                and images[0]==Path(picked['PNG']['path']).read_bytes()
                and Path(public['image_path']).resolve(strict=True)==Path(picked['PNG']['path'])
                and sample['selected_surface_pixels']==sample['primary_surface_pixels']==picked['winning_source_pixels']
                and bool(sample['sampled_pixel'])==bool(picked['winning_source_pixels']),
                'public_content_not_original_bound_png_or_anchor')
        if first is not None:
            require(picked==checked[first-1], 'first_verified_frame_not_delivered')
    else:
        picked = None
        require(not delivered and not images and not body['frames'] and sample is None,
                'unexpected_delivery_without_requested_frame')
    if warm or no_image:
        require(work['raster_attempts']==work['raster_completed']==0 and (not no_image or not checked),
                'warm_or_no_image_constructed_raster')
        if warm:
            require(work['result_cache_hit'] and work['frame_reuses']==1,'warm_frame_no_resident_reuse')
        else:
            require(status=='predicted' and focus['stop_reason']=='image_not_requested','unexpected_no_image_status')
    else:
        require(work['raster_attempts']==work['raster_completed']==len(checked) and checked[0]['view']=='SCENE',
                'constructed_frames_missing_physical_first_raster')
    metrics = check_probe(work,stages,checked[1] if len(checked)==2 else None,
                          arm=='B' and not warm and not no_image and len(checked)==2)
    if not warm and not no_image:
        if prefix=='VISIBLE':
            require(status=='complete' and first==1 and len(checked)==1,'visible_control_did_not_stop_first_view')
        elif prefix=='SEALED':
            require(status=='unknown' and first is None and len(checked)==2
                    and all(f['winning_source_pixels']==0 for f in checked),'closed_control_false_positive')
        elif prefix in SIDE:
            require(len(checked)==2 and checked[0]['winning_source_pixels']==0,
                    'mirrored_opening_missing_first_two_frame_contract')
            if arm=='A':
                normal = np.asarray(focus['front_normal_world'],dtype=np.float64)
                require(np.allclose(normal,checked[1]['target_to_eye_unit'],rtol=0,atol=2e-12),
                        'baseline_second_view_not_original_face_normal')
                require(first is None and status=='unknown',
                        'original_baseline_was_already_readable')
            else:
                require(first==2 and status=='complete'
                        and SIDE[prefix]*checked[1]['target_to_eye_unit'][0]>0.2,
                        'candidate_did_not_find_current_mirrored_opening')
    service_ns = interval(stages['service_total'],'service_total')[2]
    first_frame_ns = None
    if first is not None and not warm:
        started = stages['service_total']['started_ns']
        stage = 'frame_validation_and_selected_pixels_'+checked[first-1]['view']
        closed = interval(stages[stage],stage)[1]
        require(0<=closed-started<=service_ns,'first_readable_time_outside_current_service')
        first_frame_ns = closed-started
    return {'status':status,'stop_reason':focus['stop_reason'],'nearest':near,
            'constructed_frames':checked,'actual_rasters':work['raster_attempts'],'delivered':picked,
            'first_valid_frame':first,'first_valid_service_ns':first_frame_ns,'service_ns':service_ns,
            'observed_rtt_ns':timing,'probe':metrics,'returned_anchor':sample['sampled_pixel'] if sample else None}


def prove_panel_bound(capture,name,panel):
    _,mesh = named(capture,name)
    lo,hi = (rational_point(panel[k]) for k in ('box_min','box_max'))
    axis = panel['axis']
    others = [i for i in range(3) if i!=axis]
    location = Fraction(panel['location'])
    require(lo[axis]==hi[axis]==location,'panel_plane_mismatch/'+name)
    corners = {tuple(Fraction(f[i]) for i in others) for f in mesh['vertices']}
    expected = {(x,y) for x in (lo[others[0]],hi[others[0]]) for y in (lo[others[1]],hi[others[1]])}
    require(all(Fraction(p[axis])==location for p in mesh['vertices']) and corners==expected
            and len(mesh['faces'])==2,'live_panel_not_declared_rectangle/'+name)
    triangles = [{tuple(p[i] for i in others) for p in source_triangle(mesh,j)} for j in range(2)]
    common = triangles[0]&triangles[1]
    require(all(len(tri)==3 for tri in triangles) and len(common)==2
            and all(a!=b for a,b in zip(*common,strict=True)),'live_panel_triangulation_has_gap/'+name)
    return lo,hi,axis


def full_panel_blockers(corners,direction,panels):
    vector = rational_point(direction)
    blocked = []
    for name,(lo,hi,axis) in panels.items():
        if not vector[axis]:
            continue
        hits = []
        for corner in corners:
            offset = (lo[axis]-corner[axis])/vector[axis]
            hit = tuple(a+offset*b for a,b in zip(corner,vector,strict=True))
            hits.append(offset > 0 and all(a<=v<=b for a,v,b in zip(lo,hit,hi,strict=True)))
        if all(hits):
            blocked.append(name)
    return sorted(blocked)


def audit_fixture(capture,native,truth):
    require(capture['unit']=='m' and capture['coordinate_frame']=='world' and capture['source']=='blender'
            and native['scale_length']==1 and capture['host_identity']['capture_scope']=='complete_scene_meshes',
            'native_live_capture_scope_or_units')
    display = {row['host_id']:row for row in capture['display_snapshot']['objects']}
    names = {m['name'] for m in capture['meshes']}
    require(len(names)==len(capture['meshes'])==len(native['objects'])
            and names=={obj['name'] for obj in native['objects']},'fixture_object_scope_changed')
    for reference in native['objects']:
        _,mesh = named(capture,reference['name'])
        evaluated = reference['evaluated']
        require(mesh['vertices']==evaluated['vertices_world'] and mesh['faces']==evaluated['triangles']
                and display[mesh['object_id']]['visible_get']==reference['visible'],
                'live_evaluated_world_vertices_or_source_rows_changed/'+mesh['name'])
    output = {}
    for key in PRIMARY:
        case = truth['cases'][key]
        _,target = named(capture,case['target'])
        _,reference = named(capture,case['reference'])
        winner, = case['expected_source_triangle_indices']
        corners = source_triangle(target,winner)
        gap_sq = exact_gap(target,reference,winner)
        require(gap_sq==Fraction(case['distance_exact_m'])**2,'truth_distance_value_drift/'+key)
        panels = {name:prove_panel_bound(capture,name,panel) for name,panel in case['panels'].items()}
        blockers = {view:full_panel_blockers(corners,direction,panels)
                    for view,direction in truth['default_view_directions'].items()}
        require(blockers=={v:sorted(rows) for v,rows in case['exact_full_face_blockers_by_ray'].items()},
                'live_panel_does_not_match_frozen_exact_geometric_ray_contract/'+key)
        if key in SIDE:
            open_view = 'POS_X' if SIDE[key]>0 else 'NEG_X'
            direction = np.asarray(truth['default_view_directions'][open_view],dtype=np.float64)
            # Three interior probes as a positive check against all evaluated displayed objects; the
            # closed geometrical baseline above covers all source points, including edge rays.
            c = np.asarray(corners,dtype=np.float64)
            center = c.mean(axis=0)
            oid,_ = named(capture,case['target'])
            mask = [display[m['object_id']]['visible_get'] for m in capture['meshes']]
            require(all(independently_unblocked((point+center)/2,direction,capture,mask,oid,winner)
                        for point in c),'frozen_open_side_intersects_other_displayed_geometry/'+key)
        output[key] = {'full_face_blockers':blockers,'independent_distance_sq_m2':str(gap_sq)}
    return output



def arm_audit(root,arm,fixture,truth,corpus,native):
    scope = root/'slots'/arm
    preflight = root/'preflight'
    phase = 'BASELINE' if arm=='A' else 'CANDIDATE'
    freeze_file = preflight/('FROZEN_'+phase+'.json')
    freeze = read(freeze_file)
    reg = read(scope/'REGISTERED.json')
    require(reg['arm']==arm and reg['freeze']==pin(freeze_file),'frozen_arm_registration_mismatch')
    custody_file = freeze['baseline_installation'] if arm=='A' else freeze['candidate_installation']
    require(pin(custody_file['path'])==custody_file,'arm_install_custody_changed')
    custody = read(custody_file['path'])
    ready = read(scope/'ready.json')
    if arm=='A':
        require(custody['candidate_commit']==A_COMMIT and custody['source_sha256']==A_RUNTIME,
                'baseline_installed_version_mismatch')
    result = read(scope/'RESULT.json')
    closed = read(scope/'closed.json')
    initial, post = (read(scope/name) for name in ('initial_capture.json','post_capture.json'))
    require(result['arm']==arm and result['passed'] and result['closed']==closed and result['worker_exit']==0
            and result['model_consumers']==0 and result['confirmed_wire_exchanges']==len(corpus)+2
            and closed['native_spawned'] and closed['blender_exit']==0 and closed['failure'] is None
            and closed['pid']==ready['pid'] and closed['same_before_after_capture'] and initial==post
            and closed['post_capture']==pin(scope/'post_capture.json')
            and ready['initial_capture']==pin(scope/'initial_capture.json')
            and ready['fixture']['sha256']==closed['fixture_sha256_before']==closed['fixture_sha256_after']
            ==fixture['blend']['sha256'] and pin(ready['fixture']['path'])==ready['fixture'],
            'actual_Blender_close_worker_scene_or_corpus_not_valid')
    require(ready['source']['source_sha256']==custody['source_sha256']
            and ready['source']['source_files']==custody['source_manifest'],
            'actual_start_runtime_mismatch')
    proof = audit_fixture(initial,native,truth)
    inventory = scope/'wire/INDEX.jsonl'
    rows = [json.loads(line) for line in inventory.read_bytes().splitlines()]
    order = [r['label'] for r in corpus]
    require([row['label'] for row in rows]==['INITIALIZE','DIRECTORY',*order],
            'closed_original_wire_cases_incomplete_or_reordered')
    trace_list=[]
    previous = 0
    for index,row in enumerate(rows,1):
        base = scope/'wire'/f'{index:03d}'
        current_tx,current_rx = (pin(base/name) for name in ('TX.bin','RX.bin'))
        require(current_tx==row['tx'] and current_rx==row['rx'] and row['success']
                and previous <= row['sent_ns'] <= row['received_ns'] and row['id']==index,
                'wrong_wire_identity_or_interleaving')
        tx = read(current_tx['path'])
        reply = read(current_rx['path'])
        require(tx['id']==reply['id']==index and tx['jsonrpc']==reply['jsonrpc']=='2.0',
                'public_reply_id_mismatch')
        trace_list.append((tx,reply,row['received_ns']-row['sent_ns']))
        previous = row['received_ns']
    ident = trace_list[0][1]['result']['_meta']['human_eye']
    require(ident['source_kind']=='installed_distribution' and ident['source_sha256']==custody['source_sha256'],
            'actual_public_initialized_runtime_mismatch')
    tools = trace_list[1][1]['result']['tools']
    require(trace_list[1][0]['method']=='tools/list'
            and [t['name'] for t in tools].count('human_eye_scene_observe')==1,'missing_public_tool')
    checked={}
    for row,(tx,reply,timing) in zip(corpus,trace_list[2:],strict=True):
        label = row['label']
        key = label.split('_WARM')[0].split('_NO_IMAGE')[0]
        case = truth['cases'][key]
        folder = scope/'cases'/label
        require(tx['params']['arguments']==row['arguments'],'original_args_differ_from_frozen/'+label)
        producer,work,frames = (read(folder/name) for name in ('PRODUCER.json','WORK.json','FRAMES.json'))
        winner, = case['expected_source_triangle_indices']
        item = audit_call(arm,label,scope,tx,reply,producer,initial,timing,case['target'],case['reference'],winner)
        monitor = work['raster_calls']
        require(work['label']==label and work['completion_error'] is None
                and len(monitor)==len(frames)==item['actual_rasters']<=2
                and work['service_started_ns']<=work['service_returned_ns'],
                'independent_physical_raster_inventory_mismatch/'+label)
        for seq,(event,frame) in enumerate(zip(monitor,frames,strict=True)):
            original = producer['constructed_frames'][seq]
            seen = item['constructed_frames'][seq]
            oid,_ = named(initial,case['target'])
            require(event['completed']
                    and work['service_started_ns'] <= frame['started_ns'] <= event['started_ns']
                    <= event['closed_ns'] <= frame['completed_ns'] <= work['service_returned_ns']
                    and frame['frame']==original and frame['object_index']==oid
                    and frame['source_triangle_indices']==[winner]
                    and frame['sample']['primary_surface_pixels']==seen['winning_source_pixels']
                    and frame['sample']['selected_surface_pixels']==seen['winning_source_pixels']
                    and frame['face_patch_offsets']==list(accumulate((len(m['faces']) for m in initial['meshes']),initial=0))
                    and frame['png']==seen['PNG'] and frame['npz']==seen['NPZ'],
                    'physical_record_not_same_real_raster_source/'+label)
        if label.endswith('_WARM'):
            earlier = checked['OPEN_POS_X']
            require(item['delivered']==earlier['delivered']
                    and item['constructed_frames']==earlier['constructed_frames']
                    and item['nearest']==earlier['nearest'],'warm_result_is_not_exact_previous_origin')
        checked[label] = item
    return {'passed':True,'arm':arm,'runtime_source_sha256':custody['source_sha256'],
            'product_commit':custody['candidate_commit'],'truth':proof,'cases':checked,
            'wire':pin(inventory),'ready':pin(scope/'ready.json'),'closed':pin(scope/'closed.json'),
            'output':pin(scope/'RESULT.json'),'tool_directory_sha256':fingerprint(tools),
            'formal_Blender':1,'model_calls':0}


def compare_arm_anchors(a,b):
    require(a['tool_directory_sha256']==b['tool_directory_sha256'],'A_B_public_tool_catalog_changed')
    result={}
    for key in PRIMARY:
        left,right = (rows['cases'][key] for rows in (a,b))
        require(left['nearest']==right['nearest'],'nearest_measurement_or_endpoints_changed/'+key)
        a_first,b_first = (row['constructed_frames'][0] for row in (left,right))
        require(a_first['view']==b_first['view']=='SCENE' 
                and a_first['target_to_eye_unit']==b_first['target_to_eye_unit']
                and a_first['PNG']['sha256']==b_first['PNG']['sha256'],'SCENE_first_camera_or_image_changed/'+key)
        with np.load(a_first['NPZ']['path'],allow_pickle=False) as x,np.load(b_first['NPZ']['path'],allow_pickle=False) as y:
            require(all(np.array_equal(x[k],y[k]) for k in ('color','depth','owners','triangle_ids','face_patch_offsets')),
                    'SCENE_first_raw_raster_arrays_changed/'+key)
        result[key]={'same_first_frame_color_depth_owners_source':True,'same_nearest':True,
                     'A_first_valid_frame':left['first_valid_frame'],'B_first_valid_frame':right['first_valid_frame']}
    return result


def run(root,phase):
    require(root.name==BATCH and pin(root/'preflight/ADMIN_PLAN.md')['sha256']==PLAN_SHA,
            'wrong_fixed_admin_batch')
    folder = root/'preflight/fixture'
    fixture = {key:pin(folder/name) for key,name in (
        ('blend','main.blend'),('truth','TRUTH.json'),('requests','REQUESTS.json'),
        ('source','CURRENT_SOURCE.json'),('asset_binding','ASSET_BINDING.json'))}
    frozen = read(root/'preflight/FROZEN_BASELINE.json')
    require(frozen['batch']==BATCH and frozen['fixture']==fixture
            and frozen['limits']=={'actual_rasters_per_request':2,'minimum_target_pixels':16,
                                  'formal_Blender':2,'model_calls':0}, 'fixture_or_frozen_budget_changed')
    truth,corpus,native = (read(fixture[x]['path']) for x in ('truth','requests','source'))
    require(truth['asset_sha256']==fixture['blend']['sha256'],'frozen_truth_asset_changed')
    if phase=='A':
        result = arm_audit(root,'A',fixture,truth,corpus,native)
        result['baseline_blockers_observed'] = {name:[row['winning_source_pixels'] for row in
                                              result['cases'][name]['constructed_frames']] for name in SIDE}
    else:
        frozen_b = read(root/'preflight/FROZEN_CANDIDATE.json')
        a_inv = frozen_b['baseline_audit']
        require(pin(a_inv['path'])==a_inv and read(a_inv['path'])['passed']
                and pin(frozen_b['deadline_control']['path'])==frozen_b['deadline_control'],
                'previous_A_or_deadline_verification_changed')
        a = arm_audit(root,'A',fixture,truth,corpus,native)
        b = arm_audit(root,'B',fixture,truth,corpus,native)
        pair = compare_arm_anchors(a,b)
        deadline = read(frozen_b['deadline_control']['path'])
        require(deadline['passed'] and deadline['zero_blender'] and deadline['zero_models']
                and deadline['identity']==b['runtime_source_sha256'],
                'deadline_cold_control_not_same_candidate')
        result = {'passed':True,'arms':{'A':a,'B':b},'cross_arm':pair,
                  'candidate_open_sides':sum(b['cases'][name]['first_valid_frame']==2 for name in SIDE),
                  'declared_open_sides':len(SIDE),'formal_Blender':2,'model_calls':0,'deadline':deadline}
    result['fixture'] = fixture
    result['audit_script'] = pin(__file__)
    return result


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda p:Path(p).resolve(strict=True))
    cli.add_argument('phase',choices=('A','AB'))
    cli.add_argument('output',type=Path)
    args = cli.parse_args()
    try:
        evidence = run(args.root,args.phase)
    except (KeyError,IndexError,TypeError,ValueError,OSError,StopIteration) as error:
        evidence = {'passed':False,'phase':args.phase,'error':f'{type(error).__name__}: {error}'}
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(evidence,stream,allow_nan=False,sort_keys=True,indent=2)
        stream.write('\n')
    if not evidence['passed']:
        print(evidence['error'])
        raise SystemExit(1)
    print(json.dumps(pin(args.output)))
