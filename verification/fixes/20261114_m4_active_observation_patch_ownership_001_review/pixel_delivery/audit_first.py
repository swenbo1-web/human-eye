"""Independent saved-data audit; imports no product or author oracle."""
from pathlib import Path
from fractions import Fraction
from io import BytesIO
import json, hashlib, base64, traceback
import numpy as np
from PIL import Image

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = ROOT / 'verification/m4_active_observation_patch_ownership_001'
OUT = Path(__file__).resolve().parent
checks, inputs, details = [], {}, {}

def raw(p):
    p = Path(p); b = p.read_bytes(); inputs[str(p)] = hashlib.sha256(b).hexdigest(); return b
def js(p): return json.loads(raw(p))
def digest(b): return hashlib.sha256(b).hexdigest()
def ck(name, value, detail=None): checks.append({'name': name, 'passed': bool(value), 'detail': detail})
def stable(value): return json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode()
def table(v): return [dict(zip(v['columns'], row)) for row in v.get('rows', [])]

archive = js(H / 'EXTERNAL_ARCHIVE.json')
by_path = {r['original_path'].replace('\\', '/'): ROOT / r['archive_path'] for r in archive['files']}
by_rel = {r['original_relative_path']: ROOT / r['archive_path'] for r in archive['files']}
def archived(path): return by_path[str(path).replace('\\', '/')]
def saved(name): return js(by_rel['run/acceptance_01/' + name])

def run():
    expected = js(H / 'inputs/EXPECTED_PATCHES.json')
    roi_ids = [r['roi_id'] for r in expected['regions']]
    ck('frozen_expected138sorted', len(roi_ids) == 138 and roi_ids == sorted(set(roi_ids)))
    rows_by_roi = {r['roi_id']: r for r in expected['regions']}
    buffers_by_form = {}
    raw_values = [saved('server/RESULT_%02d.json' % i) for i in range(1, 6)]
    captures = [saved('server/CAPTURE_%02d.json' % i) for i in range(1, 6)]
    for form, n in [('split', 0), ('joined', 2)]:
        value, capture = raw_values[n], captures[n]
        meshes = capture['meshes']
        ck(form + ':mesh_count', len(meshes) == (29 if form == 'split' else 1))
        ck(form + ':tri_count', sum(len(m['faces']) for m in meshes) == 3337)
        ck(form + ':v_count', sum(len(m['vertices']) for m in meshes) == 1913)
        face_ids = [np.full(len(m['faces']), -1, dtype=np.int32) for m in meshes]
        region_objects = []
        # Map actual captured triangles by the independently frozen axis plane,
        # rectangle bounds and orientation. No candidate face IDs are used.
        for ridx, region in enumerate(expected['regions']):
            axis, plane, sign = region['axis'], float(Fraction(region['plane'])), region['normal_sign']
            quad = np.array([[float(Fraction(x)) for x in p] for p in region['quad']])
            lo, hi = quad.min(axis=0), quad.max(axis=0)
            for p in region['quad']:
                ck(form + ':exact_quad:' + region['roi_id'], all(Fraction(float(Fraction(x))) == Fraction(x) for x in p))
            owners = []
            actual_indices = []
            for object_index, mesh in enumerate(meshes):
                verts, faces = np.array(mesh['vertices']), np.array(mesh['faces'])
                triangles = verts[faces]
                normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
                valid = (np.all(triangles[:, :, axis] == plane, axis=1)
                         & np.all(triangles >= lo, axis=(1, 2)) & np.all(triangles <= hi, axis=(1, 2))
                         & (normal[:, axis] * sign > 0))
                ids = np.flatnonzero(valid)
                if len(ids):
                    owners.append(object_index)
                    ck(form + ':no_overlap:' + region['roi_id'], np.all(face_ids[object_index][ids] == -1))
                    face_ids[object_index][ids] = ridx
                    actual_indices.extend(ids.tolist())
            ck(form + ':one_owner:' + region['roi_id'], len(owners) == 1)
            region_objects.append(owners[0])
            registered = region['split_triangle_indices'] if form == 'split' else region['joined_triangle_indices']
            ck(form + ':registered_face_set:' + region['roi_id'], actual_indices == registered)
        offsets = np.r_[0, np.cumsum([len(x) for x in face_ids])].astype(np.int64)
        flat_ids = np.concatenate(face_ids)
        ck(form + ':partition_counts', np.count_nonzero(flat_ids >= 0) == 3336 and np.count_nonzero(flat_ids < 0) == 1)
        ordered_geometry = [(tuple(tuple(Fraction(x) for x in p) for p in m['vertices']), tuple(tuple(f) for f in m['faces'])) for m in meshes]
        mapping_identity = digest(stable({'version': 'active-patch-owner-v1', 'roi_ids': tuple(roi_ids),
            'ordered_geometry': ordered_geometry, 'face_patch_ids': [x.tolist() for x in face_ids]}))
        scope = value['facts']['scope']['patch_support']
        for oi, support in enumerate(scope['objects']):
            supported = np.flatnonzero(face_ids[oi] >= 0).tolist()
            unknown = sorted(j for c in support['unsupported_components'] for j in c['triangle_indices'])
            ck(form + ':support_partition:' + str(oi), support['supported_triangle_indices'] == supported
               and unknown == np.flatnonzero(face_ids[oi] < 0).tolist()
               and support['source_triangle_count'] == len(face_ids[oi])
               and support['supported_triangle_count'] == len(supported)
               and support['unsupported_triangle_count'] == len(unknown))
        ck(form + ':partial_status', scope['objects'][0]['support_status'] == 'partially_supported' if form == 'joined'
           else sum(o['support_status'] == 'unsupported' for o in scope['objects']) == 1)
        ck(form + ':roi_ids', [r['roi_id'] for r in value['facts']['regions']] == roi_ids)
        ck(form + ':frame_count', len(value['frames']) == len(value['facts']['observations']) == 3)
        form_buffers, frame_details, seen_readable = {}, [], set()
        for frame, observation in zip(value['frames'], value['facts']['observations']):
            key = form + ':' + frame['view_name']
            npz, png = raw(archived(frame['arrays_path'])), raw(archived(frame['image_path']))
            ck(key + ':file_hashes', digest(npz) == frame['arrays_sha256'] and digest(png) == frame['image_sha256'])
            with np.load(BytesIO(npz), allow_pickle=False) as arrays:
                data = {k: arrays[k] for k in arrays.files}
            ck(key + ':nine_arrays', set(data) == {'color','depth','owners','patch_owners','patch_mapping_version','patch_mapping_identity','patch_roi_ids','face_patch_ids','face_patch_offsets'})
            for field, arr in data.items():
                meta = frame['arrays'][field]
                ck(key + ':array_meta:' + field, meta == {'dtype': str(arr.dtype), 'shape': list(arr.shape), 'nbytes': arr.nbytes, 'sha256': digest(arr.tobytes())})
            ck(key + ':mapping', data['patch_mapping_identity'].item() == frame['patch_mapping_identity'] == mapping_identity
               and data['patch_mapping_version'].item() == frame['patch_mapping_version'] == 'active-patch-owner-v1'
               and data['patch_roi_ids'].tolist() == frame['patch_roi_ids'] == roi_ids
               and np.array_equal(data['face_patch_ids'], flat_ids) and np.array_equal(data['face_patch_offsets'], offsets))
            color, depth, owners, patches = (data[x] for x in ('color','depth','owners','patch_owners'))
            with Image.open(BytesIO(png)) as image:
                image.load()
                ck(key + ':PNG_actual_RGB', image.mode == 'RGB' and image.size == (512,512) and np.array_equal(np.asarray(image), color))
            fg = owners >= 0
            ck(key + ':common_depth', np.all(np.isposinf(depth[~fg])) and np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)))
            ck(key + ':patch_owner_range', patches.min() >= -1 and patches.max() < 138 and np.all(patches[~fg] == -1))
            assigned = patches >= 0
            ck(key + ':object_patch_match', np.array_equal(owners[assigned], np.asarray(region_objects)[patches[assigned]]))
            # Independent full-frame integer RGB pair differences and boolean
            # pixel union. No product sparse-path/helper or author oracle.
            boundary = np.zeros((512,512), dtype=bool)
            for left, right in [((slice(None,-1),slice(None)),(slice(1,None),slice(None))),
                                ((slice(None),slice(None,-1)),(slice(None),slice(1,None)))]:
                delta = color[left].astype(np.int64) - color[right].astype(np.int64)
                eligible = (patches[left] != patches[right]) & (np.sum(delta * delta, axis=2) >= 576)
                boundary[left] |= eligible; boundary[right] |= eligible
            pixel_rows = observation['pixel_rows']
            ck(key + ':all138rows', [r['roi_id'] for r in pixel_rows] == roi_ids)
            readable = []
            view_direction = tuple(Fraction(x) for x in frame['pose']['direction_rational'])
            for ridx, (region, row) in enumerate(zip(expected['regions'], pixel_rows)):
                mask = patches == ridx
                surfaces = int(mask.sum()); edges = int((mask & boundary).sum())
                front = sum(Fraction(v) * d for v,d in zip(region['normal'], view_direction)) > 0
                expected_row = {'front_facing':front,'visible_surface_pixels':surfaces,
                    'contrasting_boundary_pixels':edges,'readable':front and surfaces>=16 and edges>=4,
                    'minimum_surface_pixels':16,'minimum_boundary_pixels':4,'minimum_rgb_boundary_contrast':24}
                ck(key + ':pixel:' + region['roi_id'], all(row[k] == v for k,v in expected_row.items()) and row['object_index'] == region_objects[ridx])
                if expected_row['readable']: readable.append(region['roi_id'])
            ck(key + ':readable_set', sorted(readable) == observation['readable_roi_ids'])
            seen_readable.update(readable)
            if frame['view_name'] == 'SCENE':
                idx = {r['roi_id']:r for r in pixel_rows}
                front = idx[expected['checkpoints']['SCENE_visible_front']['roi_id']]
                rear = idx[expected['checkpoints']['SCENE_hidden_same_object_rear']['roi_id']]
                ck(key + ':discriminating_front', front['visible_surface_pixels'] == 354 and front['contrasting_boundary_pixels'] == 73 and front['readable'])
                ck(key + ':discriminating_rear', rear['front_facing'] and rear['visible_surface_pixels'] == rear['contrasting_boundary_pixels'] == 0 and not rear['readable'])
                if form == 'joined': ck(key + ':same_object_witness', front['object_index'] == rear['object_index'] == 0)
            frame_details.append({'view':frame['view_name'],'pixel_rows':len(pixel_rows),'readable':len(readable),
                'negative':len(pixel_rows)-len(readable),'unsupported_foreground_pixels':int(np.count_nonzero(fg & (patches < 0))),
                'mapping_sha256':mapping_identity,'array_bytes':sum(x.nbytes for x in data.values())})
            form_buffers[frame['view_name']] = {k:data[k] for k in ('color','depth','owners','patch_owners')}
        coverage = value['facts']['coverage']
        ck(form + ':covered_union', sorted(seen_readable) == coverage['covered_roi_ids'] and len(seen_readable) == 115)
        ck(form + ':unknown23', set(coverage['unresolved_roi_ids']) == set(roi_ids)-seen_readable and len(coverage['unresolved_roi_ids']) == 23)
        buffers_by_form[form] = form_buffers
        details[form] = frame_details
    for view in buffers_by_form['split']:
        for key in ('color','depth','patch_owners'):
            ck('split_join_equal:'+view+':'+key,np.array_equal(buffers_by_form['split'][view][key],buffers_by_form['joined'][view][key]))

    public_values, total_images = [], 0
    wire_bytes = []
    for rpc in range(1,8):
        prefix='run/acceptance_01/stdio/rpc_%02d/'%rpc
        tx, rx = raw(by_rel[prefix+'TX.bin']),raw(by_rel[prefix+'RX.bin'])
        request,response=json.loads(tx),json.loads(rx)
        ck('rpc_id:'+str(rpc), request['id']==response['id'] and 'error' not in response)
        wire_bytes.append(rx)
        if rpc<3:continue
        raw_value=raw_values[rpc-3]
        content=response['result']['content']
        value=json.loads(content[0]['text']);public_values.append(value)
        ck('rpc_ok:'+str(rpc),response['result']['isError'] is False and content[0]['type']=='text' and len(content)==4)
        for block,frame in zip(content[1:],raw_value['frames']):
            blob=base64.b64decode(block['data'],validate=True);total_images+=1
            ck('native_image:'+str(rpc)+':'+frame['view_name'], block['type']=='image' and block['mimeType']=='image/png'
               and blob==raw(archived(frame['image_path'])) and digest(blob)==frame['image_sha256'])
            with Image.open(BytesIO(blob)) as im:
                im.load();ck('consumer_decode:'+str(rpc)+':'+frame['view_name'],im.mode=='RGB' and im.size==(512,512))
        for k in ('status','result_kind','observation_status','session_id','read_only','execution_authority'):
            ck('top:'+str(rpc)+':'+k,value[k]==raw_value[k])
        if rpc==7:
            ck('full_facts',value['facts']==raw_value['facts'])
            ck('full_binding',value['binding']==raw_value['binding'])
            for got,frame in zip(value['frames'],raw_value['frames']):
                ck('full_frame_fields:'+frame['view_name'], all(frame[k]==v for k,v in got.items()))
            continue
        ck('brief_v2:'+str(rpc),value['schema']=='active-observation-brief-v2' and value['index_base']==0)
        objects=table(value['objects']);regions=table(value['regions']);images=table(value['images']);observations=table(value['observations']);pixels=table(value['pixels'])
        ck('object_table:'+str(rpc),objects==raw_value['binding']['objects'])
        retained_binding={k:v for k,v in raw_value['binding'].items() if k not in ('objects','schema','camera_policy')}
        retained_binding['capture_state']={k:v for k,v in retained_binding['capture_state'].items() if k!='selection_key'}
        ck('brief_binding:'+str(rpc),value['binding']==retained_binding)
        actual_regions=raw_value['facts']['regions'];support=raw_value['facts']['scope']['patch_support']
        ck('brief_region_count:'+str(rpc),len(regions)==len(actual_regions)==138)
        for ri,(row,orig) in enumerate(zip(regions,actual_regions)):
            expected_row={k:orig[k] for k in ('roi_id','object_index','status','reason')}
            expected_row['triangle_count']=len(support['regions'][ri]['triangle_indices'])
            ck('brief_region:'+str(rpc)+':'+str(ri),row==expected_row)
        for row,orig in zip(images,raw_value['frames']):
            ck('brief_image:'+str(rpc)+':'+row['view_name'],all(row[k]==orig[k] for k in ('view_name','image_ref','image_sha256','patch_mapping_identity'))
               and row['native_content_block_index']==images.index(row)+1)
        source_pixels=[r for obs in raw_value['facts']['observations'] for r in obs['pixel_rows']]
        ck('all_public_pixels:'+str(rpc),len(pixels)==len(source_pixels)==414)
        for row,original in zip(pixels,source_pixels):
            ck('brief_pixel:'+str(rpc)+':'+str(row['image_index'])+':'+str(row['region_index']),
               regions[row['region_index']]['roi_id']==original['roi_id'] and images[row['image_index']]['view_name']==original['view']
               and all(row[k]==original[k] for k in ('front_facing','visible_surface_pixels','contrasting_boundary_pixels','readable')))
        for obs,orig in zip(observations,raw_value['facts']['observations']):
            ck('brief_observation:'+str(rpc)+':'+str(obs['image_index']),[regions[i]['roi_id'] for i in obs['readable_region_indices']]==orig['readable_roi_ids'])
        for compact,old in [('covered_region_indices','covered_roi_ids'),('unresolved_region_indices','unresolved_roi_ids'),('candidate_pool_uncovered_region_indices','candidate_pool_uncovered_roi_ids')]:
            ck('coverage:'+str(rpc)+':'+old,[regions[i]['roi_id'] for i in value['coverage'].get(compact,[])]==raw_value['facts']['coverage'][old])
        ps=value['scope']['patch_support']
        ck('support_denominators:'+str(rpc),table(ps['object_support'])==[{k:o[k] for k in ('object_index','source_triangle_count','supported_triangle_count','unsupported_triangle_count','support_status')} for o in support['objects']])
        unknown=table(ps.get('unsupported_components',{'columns':[],'rows':[]}))
        expected_unknown=[]
        for oi,o in enumerate(support['objects']):
            for ci,c in enumerate(o['unsupported_components']):expected_unknown.append((oi,ci,c))
        ck('unknown_component_count:'+str(rpc),len(unknown)==len(expected_unknown)==1)
        for row,(oi,ci,c) in zip(unknown,expected_unknown):
            restored=[i for a,b in row['triangle_index_ranges'] for i in range(a,b+1)]
            ck('unknown_component:'+str(rpc),row['object_index']==oi and row['component_index']==ci and row['reason']==c['reason']
               and row['status']==c['status']=='unknown' and row['triangle_count']==len(c['triangle_indices']) and restored==c['triangle_indices'])
        ck('delivery_consumer_unconfirmed:'+str(rpc),value['image_delivery']['consumer_read_status']=='unconfirmed')
    ck('15_native_images',total_images==15)
    details['public']={'default_text_bytes':[len(v.encode('utf8')) for v in [json.loads(raw(by_rel['run/acceptance_01/stdio/rpc_%02d/RX.bin'%i]))['result']['content'][0]['text'] for i in range(3,7)]],
        'native_blocks':total_images,'brief_region_columns':public_values[2]['regions']['columns'],
        'full_region_keys':list(public_values[4]['facts']['regions'][0]),
        'full_region_mapping_keys':list(public_values[4]['facts']['scope']['patch_support']['regions'][0]),
        'full_frame_keys':list(public_values[4]['frames'][0])}

try:
    run()
except BaseException as exc:
    ck('audit_runtime_exception',False,{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
result={'schema':'root-patch-pixel-delivery-audit-v1','candidate':'efe7f77aabdab4f8de47fdb4f8714cb25f301503',
    'passed':all(c['passed'] for c in checks),'check_count':len(checks),'checks':checks,
    'failures':[c for c in checks if not c['passed']],'details':details,'inputs':inputs,
    'method':'Independent JSON/NumPy/Pillow reconstruction from original captured geometry and stored images; no product or author oracle imports.',
    'new_product_Blender_raster_model_calls':0}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:result[k] for k in ('passed','check_count','failures','details')},ensure_ascii=False))
