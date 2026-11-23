"""Reproduce auxiliary thin-occluder and self-occlusion facts from closed original slots."""

from base64 import b64decode
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
from itertools import accumulate, product
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUN = Path('D:/he_m4_source_region_visual_scope_proof_001')
PRODUCT = Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product')
DEPENDENCIES = Path('D:/he_anchor_001/venv/Lib/site-packages')
DENSE = ('m4_bound_blocker_evidence_001', 'a3277cd7', 'QP',
         '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164')
RAIL = ('m4_rail_blocker_consumption_formal_001', 'a17083c0', 'B1',
        'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce')
YANYITE = 'm4_yanyite_opposite_direction_product_native_001'
DENSE_EXPECTED = {'M4_Far_00': ('M4_Near', 0, '73786983304225/9223372036854775808')}
RAIL_EXPECTED = {'M17': ('M12', 10, '1/4'), 'M18': ('M12', 10, '2/11')}


def digest(value):
    return sha256(value).hexdigest()


def pin(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


class ClosedOriginal:
    def __init__(self, identity):
        name, commit, label, self.asset = identity
        self.root = Path('D:/he_'+name)
        self.slot = self.root/'slots'/label
        self.pins = {}
        raw = subprocess.check_output(('git', 'show',
            f'{commit}:verification/{name}/RUNTIME_INDEX.json'), cwd=REPO)
        self.index = json.loads(raw)
        self.index_identity = {'git': commit, 'bytes': len(raw), 'sha256': digest(raw)}
        archive = Path(self.index['archive']['path'])
        require(archive.resolve() == (self.root/'ORIGINAL_RUNTIME.zip').resolve(), 'archive escaped original root')
        bundle_bytes = archive.read_bytes()
        self.archive = pin(archive, bundle_bytes)
        require(self.archive == self.index['archive'], 'original ZIP identity changed')
        self.bundle = ZipFile(BytesIO(bundle_bytes))
        self.members = {row['path']: row for row in self.index['files']}
        require(len(self.members) == len(self.index['files']), 'duplicate original index row')

    def file(self, path):
        path = Path(path).resolve()
        item = self.members[path.relative_to(self.root.resolve()).as_posix()]
        data = path.read_bytes()
        check = pin(path, data)
        require(check['sha256']==item['sha256'] and check['bytes']==item['bytes']
                and data==self.bundle.read(item['path']), 'local original diverges from sealed ZIP: '+str(path))
        self.pins[str(path)] = check
        return data

    def read(self, leaf):
        return self.file(self.slot/leaf)

    def doc(self, leaf):
        return json.loads(self.read(leaf))

    def proof(self):
        return {'asset_sha256': self.asset, 'archive': self.archive, 'index': self.index_identity,
                'originals': list(self.pins.values())}


def archival_capture(original):
    from human_eye_plugin.scene_residency import SceneDeltaDecoder
    result = original.doc('SLOT_RESULT.json')
    published = original.doc('SLOT_PUBLICATION.json')
    terminal_raw = original.read('TERMINAL_SOURCE.json')
    terminal = json.loads(terminal_raw)
    require(result['status']==published['status']=='completed' and result['closure_verification']['passed']
            and published['result_sha256']==digest(original.read('SLOT_RESULT.json'))
            and result['terminal_source']['sha256']==digest(terminal_raw)
            and terminal['source']['pid']==result['terminal_source']['worker']['pid']
            and terminal['source']['asset_sha256']==result['asset_sha256']==original.asset
            and digest(original.read('native/input.blend'))==original.asset, 'owned closed slot identity mismatch')
    row = json.loads(original.read('PUBLIC_REQUESTS.jsonl').splitlines()[0])
    req = row['request']
    require(req == json.loads(original.file(row['request_path'])) and req['method']=='tools/call'
            and req['params']['name']=='human_eye_scene_observe', 'archived public request mismatch')
    producer_raw = original.file(row['producer_archive']['path'])
    require(digest(producer_raw)==row['producer_archive']['sha256'], 'original producer receipt mismatch')
    producer = json.loads(producer_raw)
    response = original.doc('native/WIRE/002/RESPONSE.bin')
    host_literal = response['result']['result']
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    require(host_literal.startswith(prefix), 'original host response absent')
    decoded = SceneDeltaDecoder().apply(json.loads(host_literal[len(prefix):])['result'])
    binding = producer['binding']
    for key in ('capture_state','scene_revision'):
        actual = decoded.get(key) if key=='capture_state' else decoded['revision']
        require(binding[key]==actual, f'original producer capture binding mismatch: {key}')
    objects, meshes = terminal['objects'], decoded['meshes']
    require(len(objects)==len(meshes)==len(binding['objects']), 'original roster width mismatch')
    for i,(obj,mesh,bound) in enumerate(zip(objects,meshes,binding['objects'],strict=True)):
        require((i,obj['name'],obj['object_id'],obj['instance_id'])==
                (bound['object_index'],bound['object_name'],bound['host_id'],bound['instance_id'])
                and mesh['vertices']==obj['evaluated']['vertices_world_m']
                and mesh['faces']==obj['evaluated']['triangles'],
                'original world coordinates, bit order or exact source rows mismatch')
    require(list(accumulate((len(obj['faces']) for obj in meshes),initial=0))==terminal['source_face_offsets'],
            'actual source triangle offsets changed')
    return decoded, terminal, producer, row


def dot(a,b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def difference(a,b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def cross(a,b):
    return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]


def clip(poly, signed):
    if not poly:
        return ()
    out = []
    old, old_distance = poly[-1], signed(poly[-1])
    for point in poly:
        dist = signed(point)
        if (old_distance >= 0) != (dist >= 0):
            weight = old_distance / (old_distance - dist)
            out.append(tuple(a + weight*(b-a) for a,b in zip(old,point,strict=True)))
        if dist >= 0:
            out.append(point)
        old, old_distance = point, dist
    return tuple(out)


def overlap_witness(row, world_triangle, pose):
    """Independent binary64-rational world-to-target-plane clip for an archived blocker."""
    middle,half_u,half_v = (tuple(map(Fraction,row[key])) for key in
                            ('center_world_m','half_edge_u_world_m','half_edge_v_world_m'))
    origin = tuple(c-u-v for c,u,v in zip(middle,half_u,half_v,strict=True))
    u,v = (tuple(2*x for x in values) for values in (half_u,half_v))
    direction = tuple(map(Fraction,pose['direction_rational']))
    normal = cross(u,v)
    forward = dot(normal,direction)
    require(forward>0 and dot(u,v)==0,'registered blocker view not a front perpendicular target chart')
    view, proj = ([tuple(map(Fraction,line)) for line in pose[key]] for key in ('view_matrix','projection_matrix'))
    matrix = tuple(tuple(dot(line,col) for col in zip(*view,strict=True)) for line in proj)
    inequalities = tuple(tuple(w+sign*x for w,x in zip(matrix[3],line,strict=True))
                         for line in matrix[:3] for sign in (-1,1))
    corners = [tuple(x+a*y+b*z for x,y,z in zip(origin,u,v,strict=True)) for a,b in product((0,1),repeat=2)]
    require(all(dot(plane,(*point,1))>=0 for plane in inequalities for point in corners),
            'registered target outside the certified frustum')
    poly = tuple(tuple(map(Fraction,point)) for point in world_triangle)
    for plane in inequalities:
        poly = clip(poly,lambda p:dot(plane,(*p,1)))
    depth = lambda p:dot(normal,difference(p,origin))
    require(poly and max(map(depth,poly))>0,'registered blocker never in front of its target')
    poly = clip(poly,depth)
    chart = []
    for point in poly:
        dx = difference(point,origin)
        height = dot(normal,dx)/forward
        projected = tuple(x-height*d for x,d in zip(dx,direction,strict=True))
        chart.append((dot(u,projected)/dot(u,u),dot(v,projected)/dot(v,v)))
    for i in range(2):
        chart = clip(chart,lambda p:p[i])
        chart = clip(chart,lambda p:1-p[i])
    area = abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(chart,chart[1:]+chart[:1],strict=True)))/2
    right = cross((0,0,1),direction)
    if not any(right):
        right = cross((0,1,0),direction)
    up = cross(direction,right)
    screen_factor = abs(dot(right,u)*dot(up,v)-dot(up,u)*dot(right,v))
    return area, area*screen_factor


def geometry_bound(obj):
    from human_eye_plugin.blender_host import _acquisition_bounds
    local = obj['evaluated']['vertices']
    lo,hi = ([fn(v[k] for v in local) for k in range(3)] for fn in (min,max))
    result = _acquisition_bounds(list(product(*zip(lo,hi,strict=True))), obj['matrix_world'], 1.)
    require(result is not None and all(a<=q<=b for point in obj['evaluated']['vertices_world_m']
        for a,q,b in zip(result[0],point,result[1],strict=True)), 'reconstructed outer bound not conservative')
    return result


def packed_raster(meshes, pose):
    import numpy as np
    from human_eye_plugin.attention_raster import rasterize_attention
    face_ids = tuple(np.arange(start,start+len(mesh.faces),dtype=np.int32)
                     for mesh, start in zip(meshes,accumulate((len(m.faces) for m in meshes),initial=0)))
    return rasterize_attention(meshes,pose['view_matrix'],pose['projection_matrix'],pose['size_px'][0],
                               return_owner=True,return_patch_owner=True,face_patch_ids=face_ids)


def identical_derived(full, smaller, retained, offsets, mesh_index):
    import numpy as np
    color,depth,owners,triangles = full
    c,d,o,t = smaller
    ordinals = np.asarray([*retained,-1],dtype=np.int32)
    restored_owner = ordinals[o]
    triangle_map = np.concatenate([*(np.arange(offsets[i],offsets[i+1],dtype=np.int32) for i in retained),
                                   np.asarray([-1],dtype=np.int32)])
    require(np.array_equal(color,c) and np.array_equal(depth.view(np.uint64),d.view(np.uint64))
            and np.array_equal(owners,restored_owner) and np.array_equal(triangles,triangle_map[t]),
            'filtered auxiliary buffers failed identical original-order comparison: '+mesh_index)


def frame_replay(original, pose_record, raw_event, meshes, retained):
    import numpy as np
    from PIL import Image
    png, npz = (original.file(pose_record[key]) for key in ('image_path','arrays_path'))
    require(digest(png)==pose_record['image_sha256'] and digest(npz)==pose_record['arrays_sha256'],
            'original dense frame SHA mismatch')
    published_images = [b64decode(block['data'],validate=True) for block in raw_event['response']['result']['content']
                        if block['type']=='image']
    require(png in published_images,'frame not actually published in original production response')
    started = perf_counter_ns()
    full = packed_raster(meshes,pose_record['pose'])
    full_ms = (perf_counter_ns()-started)/1e6
    with np.load(BytesIO(npz),allow_pickle=False) as arrays:
        for value, key in zip(full,('color','depth','owners','triangle_ids'),strict=True):
            expected = arrays[key]
            require(value.dtype==expected.dtype and value.shape==expected.shape
                    and value.tobytes()==expected.tobytes(), 'dense original NPZ pixel buffer changed: '+key)
        require(arrays['owner_mapping_identity'].item()==pose_record['owner_mapping_identity'],
                'original NPZ owner mapping identity mismatch')
        mapping = np.append(arrays['face_patch_ids'],np.int32(-1))
        require(np.array_equal(mapping[full[3]],arrays['patch_owners']),
                'original patch owners not bound to raw source winning row')
        require(list(arrays['face_patch_offsets'])==list(accumulate((len(mesh.faces) for mesh in meshes),initial=0)),
                'original dense source offsets misbound')
    final = BytesIO()
    Image.fromarray(full[0], mode='RGB').save(final, format='PNG')
    require(final.getvalue()==png,'dense rendered PNG bytes changed')
    filtered_started = perf_counter_ns()
    filtered = packed_raster(tuple(meshes[i] for i in retained),pose_record['pose'])
    offsets = list(accumulate((len(m.faces) for m in meshes),initial=0))
    identical_derived(full,filtered,retained,offsets,pose_record['view_name'])
    return {'view':pose_record['view_name'],'png_sha256':digest(png),'npz_sha256':digest(npz),
            'png_bytes':len(png),'npz_bytes':len(npz),'full_raster_ms':full_ms,
            'same_matrix_filtered_raster_and_remap_ms':(perf_counter_ns()-filtered_started)/1e6,
            'exact_original_RGB_depth_bits_object_and_triangle_owner': True,
            'original_patch_owners_reconstructed': True,'PNG_bytes_equal': True}


def blocker_group(identity, expected, compare_images):
    from human_eye_plugin.active_observation import geometry, partition_regions, build_index_from_parsed
    from human_eye_plugin.active_observation_host import scene_from_capture
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.blender_host import _observation_outside_xy_viewports, _observation_target_cameras
    original = ClosedOriginal(identity)
    decoded, terminal, producer, old_event = archival_capture(original)
    objs, tris, geom_id = geometry(scene_from_capture(decoded))
    cameras = producer['binding']['camera_specification']
    require(geom_id==producer['binding']['geometry_identity'],'earlier and installed geometry identity mismatch')
    poses = {p['name']:p for p in cameras['views']}
    public = json.loads(old_event['response']['result']['content'][0]['text'])
    public_block = public['blocker_evidence']
    require(public_block['columns']==['region_index','view_name','blocker_object_index','source_triangle_index'],
            'historical compact blocker topology differs')
    public_region = public['region_task']
    public_indices = {values[public_region['columns'].index('roi_id')]:idx
                      for idx,values in enumerate(public_region['rows'])}
    bound_rows = producer['facts']['region_task']['blocker_evidence']['rows']
    by_roi = {row['roi_id']:row for row in producer['facts']['region_task']['rows']}
    region_ids = {hit['roi_id'] for hit in bound_rows if by_roi[hit['roi_id']]['object_name'] in expected}
    regions,_ = partition_regions(objs)
    selected = tuple(region for region in regions if region.roi_id in region_ids)
    require(len(selected)==len(expected),'registered original regions missing')
    started = perf_counter_ns()
    coverage = build_index_from_parsed(objs,tris,geom_id,selected,cameras,bind_blocker_sources=True)
    kernel_ms = (perf_counter_ns()-started)/1e6
    meshes = _meshes_from_objects(objs)
    boxes = [geometry_bound(obj) for obj in terminal['objects']]
    old_keep = [i for i,box in enumerate(boxes) if not _observation_outside_xy_viewports(box,cameras)[0]]
    results = []
    for raw in bound_rows:
        roi = raw['roi_id']
        row = by_roi[roi]
        if row['object_name'] not in expected:
            continue
        blocker_name,source_row,area = expected[row['object_name']]
        ordinal = raw['blocker_object_index']
        box = boxes[ordinal]
        target = terminal['objects'][row['object_index']]
        blocker = terminal['objects'][ordinal]
        require(blocker['name']==blocker_name and raw['source_triangle_index']==source_row
                and blocker['object_id']==raw['blocker_host_id'] and blocker['instance_id']==raw['blocker_instance_id']
                and raw['view_name']=='LEFT', 'original blocker identities are not current')
        triangle = [blocker['evaluated']['vertices_world_m'][idx]
                    for idx in blocker['evaluated']['triangles'][source_row]]
        chart, exact = overlap_witness(row,triangle,poses['LEFT'])
        hit_result = coverage.classifications['LEFT'][roi]
        hit = hit_result['first_blocker']
        require(chart>0 and str(exact)==area
                and hit_result['status']=='positive_area_occlusion'
                and (hit['source_object_index'],hit['source_triangle_index'])==(ordinal,source_row)
                and hit['triangle_geometry_id']==raw['triangle_geometry_id']
                and hit['overlap_area_screen_exact']==raw['overlap_area_screen_exact']==str(exact),
                'closed blocker no longer first positive-area source')
        require([public_indices[roi],'LEFT',ordinal,source_row] in public_block['rows'],
                'archived public packet did not actually deliver current blocker')
        require(ordinal in old_keep,'strict proof removed an actual positive-area blocker')
        target_world = target['evaluated']['vertices_world_m']
        unique = sorted({i for f in row['source_triangle_indices'] for i in target['evaluated']['triangles'][f]})
        tight = [[[fn(v[k] for v in mesh.vertices) for k in range(3)] for fn in (min,max)] for mesh in meshes]
        fitted = _observation_target_cameras([target_world[i] for i in unique], tight)
        fit_keep = [i for i,b in enumerate(boxes) if i==row['object_index']
                    or not _observation_outside_xy_viewports(b,fitted)[0]]
        require(ordinal in fit_keep, 'same source thin blocker lost from target-fitted camera proof')
        chosen_pose = next(p for p in fitted['views'] if p['name']=='LEFT')
        fit_chart, fit_area = overlap_witness(row,triangle,chosen_pose)
        require(fit_chart==chart and fit_area==exact,'thin blocker changed under diagonal local depth camera')
        started = perf_counter_ns()
        if len(fit_keep)<len(meshes):
            full = packed_raster(meshes,chosen_pose)
            filtered = packed_raster(tuple(meshes[i] for i in fit_keep),chosen_pose)
            identical_derived(full,filtered,fit_keep,terminal['source_face_offsets'],row['object_name'])
        results.append({'target':row['object_name'],'target_source_triangles':len(row['source_triangle_indices']),
                        'blocker':blocker_name,'source_row':source_row,'original_ordinal':ordinal,
                        'camera':raw['view_name'],'target_chart_area_exact':str(chart),
                        'exact_area_m2':str(exact),'retained_in_original_all_six':True,
                        'target_fitted_retained':len(fit_keep),'target_fitted_ordinals':fit_keep,
                        'fitted_same_matrix_LEFT_compared': len(fit_keep)<len(meshes),
                        'fitted_same_matrix_LEFT_pair_ms':(perf_counter_ns()-started)/1e6})
    frames = [frame_replay(original,f,old_event,meshes,old_keep) for f in producer['frames']] if compare_images else []
    return {'original_roster':[len(objs),sum(len(o[0]) for o in objs),len(tris)],
            'old_all_six_retained':len(old_keep),'known_reconstructed_outer_bounds':len(boxes),
            'bound_provenance':'outward evaluated local vertices and archived world matrix; no live bound_box claim',
            'installed_positive_area_index_ms':kernel_ms,'blocker_rows':results,'original_frame_replays':frames,
            'proof':original.proof()}


def load_aux():
    """Return the two archived Yanyite source_region cases for the common replay."""
    from sources import load_formal
    return load_formal(YANYITE,'75f75b920',('YANYITE_NEG_Y','YANYITE_POS_Y'))


def self_occlusion(case):
    import numpy as np
    from human_eye_plugin.active_observation import geometry
    from human_eye_plugin.active_observation_host import scene_from_capture
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.attention_raster import rasterize_attention
    capture,producer = case['capture'],case['producer']
    frame, = producer['frames']
    obj,_,_ = geometry(scene_from_capture(capture),include_triangles=False)
    full_meshes = _meshes_from_objects(obj)
    require(len(full_meshes)==2 and obj[1][3]=='Cube'
            and producer['binding']['image_scope']['participation_mask']==[True,False],
            'archived Yanyite Cube accidentally entered image display domain')
    side = producer['task_result']
    require(side['reference']['name']=='Cube' and side['status']=='complete',
            'hidden Cube no longer the measured whole reference')
    indices = producer['region_ref']['source_triangle_indices']
    pose = frame['pose']
    full_mask = [np.arange(len(m.faces),dtype=np.int32) for m in full_meshes]
    args = (pose['view_matrix'],pose['projection_matrix'],pose['size_px'][0])
    full = rasterize_attention(full_meshes,*args,return_owner=True,return_patch_owner=True,
                               face_patch_ids=tuple(full_mask),object_mask=(True,False))
    require(np.count_nonzero(full[2]==1)==0,'hidden Cube covered Yanyite in software replay')
    normal_pixels = (full[2]==0)&np.isin(full[3],indices)
    trimmed = _meshes_from_objects(((obj[0][0],tuple(obj[0][1][i] for i in indices),obj[0][2],obj[0][3]),))
    cropped = rasterize_attention(trimmed,*args,return_owner=True,return_patch_owner=True,
                                  face_patch_ids=(np.asarray(indices,dtype=np.int32),))
    cropped_pixels = cropped[2]==0
    lost_mask = cropped_pixels & ~normal_pixels
    lost = int(np.count_nonzero(lost_mask))
    strictly_occluded = lost_mask & (full[2]==0) & (full[1]<cropped[1]) & ~np.isin(full[3],indices)
    occluded_count = int(np.count_nonzero(strictly_occluded))
    require(lost>0 and occluded_count>0,'same-object unselected face did not demonstrably occlude selection')
    r,c = (int(value) for value in np.argwhere(strictly_occluded)[0])
    sample = {'row':r,'column':c,'target_unselected_source_triangle':int(full[3][r,c]),
              'selected_source_triangle_without_self_occluder':int(cropped[3][r,c]),
              'original_depth_m':float(full[1][r,c]),'counterfactual_depth_m':float(cropped[1][r,c])}
    with np.load(case['npz'],allow_pickle=False) as old:
        require(all(full[i].tobytes()==old[key].tobytes()
            for i,key in enumerate(('color','depth','owners','triangle_ids'))),
            'original Yanyite frame failed self-occlusion baseline')
    from PIL import Image
    encoded = BytesIO()
    Image.fromarray(full[0],mode='RGB').save(encoded,format='PNG')
    require(encoded.getvalue()==Path(case['png']).read_bytes(),'Yanyite replay original PNG differs')
    fact = side['facts']['surface_proximity']
    return {'name':case['label'],'view':frame['view_name'],'objects_full_and_retained':[2,2],
            'target_all_triangles':len(full_meshes[0].faces),'target_triangles_selected':len(indices),
            'hidden_cube_raster_pixels':0,'cube_triangles_measurement_retained':len(full_meshes[1].faces),
            'distance_m':fact['value']['distance_m'],'target_selected_pixels':int(np.count_nonzero(normal_pixels)),
            'selected_only_pixels':int(np.count_nonzero(cropped_pixels)),
            'actual_pixel_changes_when_discarding_target_nonselected_faces':lost,
            'proven_strict_self_occlusion_pixels':occluded_count,'self_occlusion_sample':sample,
            'original_RGB_depth_bits_and_owner_arrays_equal':True,'original_PNG_bytes_equal':True}


def main():
    sys.path[:0] = [str(PRODUCT),str(DEPENDENCIES),str(HERE)]
    import human_eye_plugin
    require(Path(human_eye_plugin.__file__).resolve().is_relative_to(PRODUCT.resolve()), 'wrong product installation')
    dense = blocker_group(DENSE,DENSE_EXPECTED,True)
    rail = blocker_group(RAIL,RAIL_EXPECTED,False)
    output = {'dense':dense,'rail_thin':rail,
              'yanyite_self_occlusion':self_occlusion(load_aux()[0]),'actual_Blender':0,'actual_models':0}
    path = RUN/'AUXILIARY.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as fd:
        json.dump(output,fd,ensure_ascii=False,indent=2,sort_keys=True)
        fd.write('\n')
    print(json.dumps({'dense':{'blocker_rows':dense['blocker_rows'],'frames':dense['original_frame_replays']},
          'rail_thin':rail['blocker_rows'], 'self':output['yanyite_self_occlusion']},ensure_ascii=False))


if __name__ == '__main__':
    main()
