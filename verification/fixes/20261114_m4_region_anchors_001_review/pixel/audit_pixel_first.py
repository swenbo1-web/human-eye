"""Root-independent saved-buffer audit. No product import or execution."""
import base64
from collections import Counter
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
ROOT = AUTHOR / 'verification/m4_active_observation_region_anchors_001'
OUT = Path(__file__).resolve().parent
inputs = {}
failures = []
checks = Counter()

def read(path):
    path = Path(path)
    raw = path.read_bytes()
    inputs[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw

def js(path):
    return json.loads(read(path))

def check(value, label, detail=None):
    checks[label.split(':')[0]] += 1
    if not bool(value):
        failures.append({'label': label, 'detail': detail})

archive = js(ROOT / 'EXTERNAL_ARCHIVE.json')
by_original = {row['original_path'].replace('\\', '/'): row for row in archive['files']}
by_relative = {row['original_relative_path']: row for row in archive['files']}

def archived(original=None, relative=None):
    row = by_original[original.replace('\\', '/')] if original else by_relative[relative]
    path = AUTHOR / row['archive_path']
    data = read(path)
    check(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'archive:binding')
    return data

def arjs(relative):
    return json.loads(archived(relative=relative))

index = arjs('run/acceptance_01/server/INDEX_01.json')
capture = arjs('run/acceptance_01/server/CAPTURE_01.json')
regions = index['regions']
roi_ids = [r['roi_id'] for r in regions]
check(len(roi_ids) == 138 and roi_ids == sorted(set(roi_ids)), 'mapping:ordered_138_ROIs')
face_map = [-1] * len(capture['meshes'][0]['faces'])
for k, reg in enumerate(regions):
    check(reg['object_index'] == 0, 'mapping:joined_object')
    for face in reg['triangle_indices']:
        check(face_map[face] == -1, 'mapping:disjoint_source_faces')
        face_map[face] = k
check(len(face_map) == 3337 and [i for i,v in enumerate(face_map) if v == -1] == [48], 'mapping:unsupported_face_48')

server = [arjs(f'run/acceptance_01/server/RESULT_{i:02d}.json') for i in (1,2,3)]
cold = server[0]
check(len(cold['frames']) == 3, 'frames:three_unique_frames')
observed = {}
frame_by_view = {}
frame_counts = []
class_counts = Counter()

def fraction_normal(reg):
    q = [[Fraction(x) for x in p] for p in reg['vertices']]
    a = [q[1][i] - q[0][i] for i in range(3)]
    b = [q[3][i] - q[0][i] for i in range(3)]
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

for frame in cold['frames']:
    view = frame['view_name']
    frame_by_view[view] = frame
    raw = archived(original=frame['arrays_path'])
    png = archived(original=frame['image_path'])
    check(hashlib.sha256(raw).hexdigest() == frame['arrays_sha256'], 'frames:NPZ_hash')
    check(hashlib.sha256(png).hexdigest() == frame['image_sha256'], 'frames:PNG_hash')
    with np.load(BytesIO(raw), allow_pickle=False) as z:
        arrays = {k:z[k].copy() for k in z.files}
    check(set(arrays) == set(frame['arrays']), 'frames:nine_array_keys')
    for key, val in arrays.items():
        meta = frame['arrays'][key]
        check(meta == {'dtype':str(val.dtype),'shape':list(val.shape),'nbytes':val.nbytes,
                      'sha256':hashlib.sha256(val.tobytes(order='C')).hexdigest()}, 'frames:array_metadata')
    color, depth, owners, patches = [arrays[k] for k in ('color','depth','owners','patch_owners')]
    check(patches.shape == (512,512) and patches.dtype == np.int32, 'frames:512_patch_buffer')
    check(np.array_equal(arrays['patch_roi_ids'], roi_ids), 'mapping:buffer_ROI_order')
    check(np.array_equal(arrays['face_patch_ids'],face_map), 'mapping:buffer_source_faces')
    check(np.array_equal(arrays['face_patch_offsets'],[0,3337]), 'mapping:buffer_offsets')
    check(str(arrays['patch_mapping_identity']) == frame['patch_mapping_identity'], 'mapping:frame_identity')
    check(str(arrays['patch_mapping_version']) == frame['patch_mapping_version'], 'mapping:version')
    check(np.all(owners[patches >= 0] == 0) and np.all(patches[owners == -1] == -1), 'mapping:owners_consistency')
    check(np.all(np.isposinf(depth[owners == -1])) and np.all(np.isfinite(depth[owners >= 0])), 'frames:depth_consistency')
    with Image.open(BytesIO(png)) as image:
        check(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512,512), 'frames:PNG_encoding')
        check(np.array_equal(np.asarray(image),color), 'frames:PNG_equals_saved_RGB')
    old_npz = read(ROOT / f'inputs/historical/{view}.npz')
    old_png = read(ROOT / f'inputs/historical/{view}.png')
    check(old_npz == raw and old_png == png, 'history:byte_identical_PNG_NPZ')
    with np.load(BytesIO(old_npz), allow_pickle=False) as old:
        for key in ('color','depth','owners','patch_owners'):
            check(np.array_equal(old[key],arrays[key]), 'history:color_depth_owners_identical')
    pose = next(p for p in index['cameras']['views'] if p['name'] == view)
    check(frame['pose'] == pose, 'frames:bound_camera')
    check(frame['scene_identity'] == index['scene_identity'] and frame['candidate_identity'] == index['candidate_identity'], 'frames:index_identity')
    check(frame['host_binding_sha256'] == cold['binding']['binding_sha256'], 'frames:host_binding')
    check(frame['source_revision'] == capture['revision'], 'frames:source_revision')
    # Independent neighbor-array test, then scalar min over actual ROI pixel set.
    c = color.astype(np.int64)
    boundary = np.zeros(patches.shape, dtype=bool)
    horizontal = (patches[:,1:] != patches[:,:-1]) & (np.sum((c[:,1:]-c[:,:-1])**2,axis=2) >= 576)
    vertical = (patches[1:,:] != patches[:-1,:]) & (np.sum((c[1:,:]-c[:-1,:])**2,axis=2) >= 576)
    boundary[:,1:] |= horizontal
    boundary[:,:-1] |= horizontal
    boundary[1:,:] |= vertical
    boundary[:-1,:] |= vertical
    rows = {}
    for k,reg in enumerate(regions):
        ys,xs = np.nonzero(patches == k)
        n = len(xs)
        edge = int(np.count_nonzero(boundary[ys,xs]))
        front = sum(x*Fraction(y) for x,y in zip(fraction_normal(reg),pose['target_to_eye_unit'])) > 0
        bounds = anchor = None
        if n:
            bounds = [int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())]
            lx,ly,hx,hy = bounds
            scored = [((2*int(x)-lx-hx)**2+(2*int(y)-ly-hy)**2,int(y)*512+int(x),[int(x),int(y)]) for x,y in zip(xs,ys)]
            anchor = min(scored)[2]
            check(patches[anchor[1],anchor[0]] == k, 'anchors:actual_owner')
            class_counts['nonempty'] += 1
            class_counts['backface_nonempty' if not front else 'front_nonempty'] += 1
            class_counts['visible_unreadable' if not (front and n>=16 and edge>=4) else 'visible_readable'] += 1
            class_counts['multiple_nearest_tie'] += sum(s[0] == min(scored)[0] for s in scored) > 1
        else:
            class_counts['empty'] += 1
            class_counts['front_empty' if front else 'back_empty'] += 1
        rows[reg['roi_id']] = {'roi_id':reg['roi_id'],'object_index':0,'view':view,'front_facing':front,
            'visible_surface_pixels':n,'contrasting_boundary_pixels':edge,'readable':front and n>=16 and edge>=4,
            'visible_pixel_bounds':bounds,'visible_pixel_anchor':anchor}
    observed[view] = rows
    frame_counts.append({'view':view,'pixel_rows':len(rows),'nonempty':sum(r['visible_surface_pixels']>0 for r in rows.values()),
                         'readable':sum(r['readable'] for r in rows.values()),'png_sha256':frame['image_sha256'],
                         'npz_sha256':frame['arrays_sha256']})

for request_i, result in enumerate(server,1):
    check([f['view_name'] for f in result['frames']] == list(observed), 'server:three_frame_order')
    for f in result['frames']:
        ref=frame_by_view[f['view_name']]
        check(all(f[k] == ref[k] for k in ('image_path','image_sha256','arrays_path','arrays_sha256','image_ref')), 'server:frame_reuse')
    for obs in result['facts']['observations']:
        view=obs['view_name']; wanted=observed[view]; frame=frame_by_view[view]
        check(len(obs['pixel_rows'])==138, 'server:complete_138_rows')
        check(all(obs[k]==frame[k] for k in ('image_path','image_ref','image_sha256')), 'server:observation_image_binding')
        for row in obs['pixel_rows']:
            for k,v in wanted[row['roi_id']].items():
                check(row.get(k) == v and type(row.get(k)) is type(v), 'server:pixel_'+k, [request_i,view,row['roi_id']])

responses=[]
for request_i in (3,4,5):
    response=arjs(f'run/acceptance_01/stdio/rpc_{request_i:02d}/RESPONSE.json')
    wire=archived(relative=f'run/acceptance_01/stdio/rpc_{request_i:02d}/RX.bin')
    check(json.loads(wire)==response,'public:wire_response_equal')
    check(not response['result']['isError'],'public:successful_request')
    blocks=response['result']['content']
    check(len(blocks)==4 and blocks[0]['type']=='text','public:one_text_three_images')
    value=json.loads(blocks[0]['text'])
    responses.append(value)
    if request_i<5:
        check(value['schema']=='active-observation-brief-v3','public:v3')
        check(len(blocks[0]['text'].encode('utf-8'))<=48162,'public:brief_bytes_gate')
        pixel_rows=[dict(zip(value['pixels']['columns'],row)) for row in value['pixels']['rows']]
        public_regions=[dict(zip(value['regions']['columns'],row)) for row in value['regions']['rows']]
        public_images=[dict(zip(value['images']['columns'],row)) for row in value['images']['rows']]
        check([r['roi_id'] for r in public_regions]==roi_ids,'public:ordered_ROIs')
        check(len(pixel_rows)==414,'public:all_pixel_rows')
        check(len({(r['image_index'],r['region_index']) for r in pixel_rows})==414,'public:no_duplicate_pixels')
        for row in pixel_rows:
            view=public_images[row['image_index']]['view_name']
            roi=public_regions[row['region_index']]['roi_id']
            for k,v in observed[view][roi].items():
                if k in row:
                    check(row[k]==v and type(row[k]) is type(v),'public:pixel_'+k,[request_i,view,roi])
        for i,img in enumerate(public_images):
            f=frame_by_view[img['view_name']]
            check(img['native_content_block_index']==i+1,'public:image_content_index')
            check(all(img[k]==f[k] for k in ('image_ref','image_sha256','patch_mapping_identity')),'public:image_binding')
        loc=value['location_conventions']
    else:
        check(value['facts']['observations']==server[2]['facts']['observations'],'public:full_observations')
        public_images=value['frames']
        loc=value['facts']['location_conventions']
    check(loc['pixel_origin']=='top-left' and loc['pixel_index_base']==0 and loc['pixel_axis_order']==['x','y'] and loc['image_size_px']==[512,512],'public:pixel_conventions')
    for i,f in enumerate(public_images):
        block=blocks[i+1]
        check(block['type']=='image' and block['mimeType']=='image/png','public:native_image_block')
        decoded=base64.b64decode(block['data'],validate=True)
        check(hashlib.sha256(decoded).hexdigest()==f['image_sha256'],'public:native_png_hash')
        check(decoded==archived(original=frame_by_view[f['view_name']]['image_path']),'public:native_png_same_frame')

check(responses[0]['pixels']==responses[1]['pixels'],'public:cold_hot_same_pixels')
check(responses[0]['location_conventions']==responses[1]['location_conventions']==responses[2]['facts']['location_conventions'],'public:same_location_contract')
old=js(ROOT/'inputs/historical/JOINED_SERVICE_RESULT.json')
for key in ('coverage','scope'):
    check(cold['facts'][key]==old['facts'][key],'history:preserved_'+key)
readable_union={roi for rows in observed.values() for roi,row in rows.items() if row['readable']}
check(set(cold['facts']['coverage']['covered_roi_ids'])==readable_union and len(readable_union)==115,'coverage:independent_115_union')
check(len(cold['facts']['coverage']['unresolved_roi_ids'])==23,'coverage:23_unknown')
check(class_counts['nonempty']==161 and class_counts['empty']==253,'denominator:161_nonempty_253_empty')

for path in [AUTHOR/'human_eye_plugin/active_observation_images.py',AUTHOR/'verification/test_active_observation_region_anchors.py',AUTHOR/'verification/test_active_observation_region_delivery.py',ROOT/'units_01/UNIT_TESTS.txt']:
    read(path)
unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256'] for p,v in inputs.items())
check(unchanged,'inputs:unchanged_after_audit')
result={'passed':not failures,'checks':sum(checks.values()),'check_groups':dict(checks),'failures':failures,
    'unique_frames':3,'unique_pixel_rows':414,'server_requests_rechecked':3,'public_requests_rechecked':3,
    'server_pixel_row_instances':1242,'public_pixel_row_instances':1242,'native_image_blocks':9,
    'class_counts':dict(class_counts),'frames':frame_counts,'input_count':len(inputs),
    'new_product_calls':0,'new_raster_calls':0,'new_Blender_calls':0,'new_benchmark_calls':0,'new_model_calls':0,
    'scope':'Independent saved owner/RGB/PNG and complete public pixel data; synthetic product tests read, not rerun.'}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'EXPECTED_PIXELS.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(bool(failures))
