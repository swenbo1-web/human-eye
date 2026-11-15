"""Independent saved-evidence review. No author checker or product import."""
import base64
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = Path('D:/he_m4_target_002')
FROZEN = Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json')
checks = 0


def check(value, label):
    global checks
    checks += 1
    if not value:
        raise AssertionError(label)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


ORIGINALS = {obj['name']: obj for obj in read(FROZEN)['objects']}


def decode_wire(pin, resources):
    for key in ('wire_request', 'wire_response', 'capture'):
        check(sha(pin[key]) == pin[key + '_sha256'], key + ' bytes')
    reply = read(pin['wire_response'])['result']['result']
    rows = [row.split(':', 1)[1] for row in reply.splitlines() if row.startswith('HUMAN_EYE_BLENDER_MCP:')]
    check(len(rows) == 1, 'one host packet')
    packet = json.loads(rows[0])['result']
    for resource in packet.get('resources', []):
        resources[resource['id'], resource['revision']] = resource
    capture = packet.get('capture', packet)
    for mesh in capture['meshes']:
        ref = mesh.pop('_scene_resource', None)
        if ref:
            resource = resources[ref['id'], ref['revision']]
            mat, scale = ref['matrix'], ref['scale']
            mesh['vertices'] = [[(sum(mat[a][b] * v[b] for b in range(3)) + mat[a][3]) * scale for a in range(3)] for v in resource['vertices_local']]
            mesh['faces'], mesh['edges'] = resource['faces'], resource['edges']
    check(capture == read(pin['capture']), 'actual wire matches saved expanded capture')
    return capture


def inspect(slot, expected_covered, expected_views, scene_kind='main', moved=False, resources=None, legacy=False):
    pub = read(slot / 'PUBLIC_01.json')
    owner = read(slot / 'OWNER_BINDING.json')
    resources = {} if resources is None else resources
    main, back = [decode_wire(pin, resources) for pin in owner['captures']]
    meshes = main['meshes']
    index_names = [m['name'] for m in meshes]
    check(len(index_names) == len(set(index_names)), 'unique capture objects')
    for idx, mesh in enumerate(meshes):
        original = ORIGINALS[mesh['name']]
        vertices = [[float(Fraction(v)) for v in point] for point in original['world_vertices_m']]
        faces = original['triangles']
        if legacy and mesh['name'] == 'M4_Far_00':
            vertices, faces = vertices[:289], faces[:512]
        if moved and mesh['name'] == 'M4_Far_11':
            vertices = [[z + 9/8, y - 1/8, 67/32] for x, y, z in vertices]
        check(mesh['vertices'] == vertices, 'frozen world vertices ' + mesh['name'])
        check(mesh['faces'] == faces, 'frozen local faces ' + mesh['name'])
        row = pub['binding']['objects'][idx]
        check(row['object_name'] == mesh['name'] and row['host_id'] == mesh['object_id'] and row['object_index'] == idx, 'public object mapping')
    target = next(m for m in meshes if m['name'] == 'M4_Far_00')
    check(back['meshes'][0]['name'] == target['name'], 'readback target')
    check({k:v for k,v in back['meshes'][0].items() if k != 'mark_label'} == {k:v for k,v in target.items() if k != 'mark_label'}, 'readback source and geometry')
    for key in ('instance_id', 'epoch', 'revision'):
        check(main['capture_state'][key] == pub['binding']['capture_state'][key] == back['capture_state'][key], 'same scene generation ' + key)
    regions = pub['facts']['regions']
    supported = 1 if legacy else 2
    check(len(regions) == supported, 'supported regions')
    counts = pub['facts']['inspection']['counts']
    check(counts['supported'] == supported and counts['covered'] == expected_covered and counts['unobserved'] == supported-expected_covered, 'actual coverage counts')
    check([f['view_name'] for f in pub['frames']] == expected_views, 'actual producer view sequence')
    check(pub['facts']['coverage']['observed_views'] == expected_views, 'observed views use producer frames')
    check(len(pub['facts']['observations']) == len(pub['frames']), 'one observation per producer frame')
    normal_regions = []
    for r in regions:
        check(r['object_name'] == target['name'] and r['host_id'] == target['object_id'], 'region target binding')
        normal_regions.append({k:v for k,v in r.items() if k not in ('host_id','instance_id','object_index')})
    data = []
    images = [block for block in read(slot/'RESPONSE_01.json')['result']['content'] if block['type']=='image']
    offsets = np.cumsum([0] + [len(m['faces']) for m in meshes])
    target_idx = index_names.index('M4_Far_00')
    roi_ids = sorted(r['roi_id'] for r in regions)
    expected_patch = np.full(int(offsets[-1]), -1, dtype=np.int32)
    for patch_index, roi in enumerate(roi_ids):
        region = next(r for r in regions if r['roi_id']==roi)
        local = list(range(512,514)) if region['center_world_m'][2] == 2 else list(range(512))
        expected_patch[offsets[target_idx]+np.array(local)] = patch_index
    for frame, obs, image in zip(pub['frames'], pub['facts']['observations'], images):
        check(sha(frame['arrays_path']) == frame['arrays_sha256'], 'producer NPZ hash')
        check(sha(frame['image_path']) == frame['image_sha256'], 'producer PNG hash')
        check(base64.b64decode(image['data'], validate=True) == Path(frame['image_path']).read_bytes(), 'actual response image bytes')
        check(frame['host_binding_sha256'] == pub['binding']['binding_sha256'], 'frame current host binding')
        check(frame['source_revision'] == pub['binding']['scene_revision'], 'frame source revision')
        with np.load(frame['arrays_path'], allow_pickle=False) as z:
            a = {key:z[key] for key in z.files}
        check(np.array_equal(np.asarray(Image.open(frame['image_path'])), a['color']), 'PNG equals raw RGB')
        check(a['color'].shape==(512,512,3) and a['owners'].shape==(512,512), 'actual dimensions')
        check(a['face_patch_offsets'].tolist()==offsets.tolist(), 'source triangle offsets')
        check(a['patch_roi_ids'].tolist()==roi_ids and np.array_equal(a['face_patch_ids'],expected_patch), 'source face to region map')
        valid = a['owners'] >= 0
        check(np.array_equal(valid,a['triangle_ids']>=0), 'owner/source foreground agreement')
        ids = a['triangle_ids'][valid]
        check(bool(np.all((ids>=0)&(ids<offsets[-1]))), 'all source IDs in range')
        source_owners = np.searchsorted(offsets[1:],ids,side='right')
        check(np.array_equal(a['owners'][valid],source_owners), 'all source IDs map to pixel owner')
        patch = np.full(a['owners'].shape,-1,dtype=np.int32)
        patch[valid] = expected_patch[ids]
        check(np.array_equal(patch,a['patch_owners']), 'all patch owners independently derived from source faces')
        asset_owner = np.full(a['owners'].shape,-1,dtype=np.int32)
        source_local = np.full(a['owners'].shape,-1,dtype=np.int32)
        asset_names = sorted(ORIGINALS)
        asset_owner[valid] = np.array([asset_names.index(name) for name in index_names])[source_owners]
        source_local[valid] = ids - offsets[source_owners]
        for row in obs['pixel_rows']:
            mask = patch == roi_ids.index(row['roi_id'])
            yy,xx = np.where(mask)
            check(len(xx)==row['visible_surface_pixels'], 'ROI visible pixel count')
            if len(xx):
                check([int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())]==row['visible_pixel_bounds'], 'actual ROI bounds')
                centerx = int(xx.min())+int(xx.max())
                centery = int(yy.min())+int(yy.max())
                distances = (2*xx-centerx)**2 + (2*yy-centery)**2
                anchor = int(np.argmin(distances))
                check([int(xx[anchor]),int(yy[anchor])]==row['visible_pixel_anchor'], 'ROI nearest-center anchor with row-major tie')
            contrast = np.zeros(mask.shape,dtype=bool)
            for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
                ys,ye=max(0,-dy),min(512,512-dy)
                xs,xe=max(0,-dx),min(512,512-dx)
                source=(slice(ys,ye),slice(xs,xe))
                neighbor=(slice(ys+dy,ye+dy),slice(xs+dx,xe+dx))
                delta=a['color'][source].astype(np.int32)-a['color'][neighbor].astype(np.int32)
                contrast[source] |= mask[source] & ~mask[neighbor] & (np.sum(delta*delta,axis=2)>=24**2)
            check(int(np.count_nonzero(contrast))==row['contrasting_boundary_pixels'], 'independent four-neighbor RGB squared boundary contrast')
            check(row['readable'] == (row['front_facing'] and len(xx)>=16 and row['contrasting_boundary_pixels']>=4), 'readability threshold')
        data.append({'view':frame['view_name'],'color':a['color'],'depth':a['depth'],'owner':asset_owner,'source_local':source_local,'patch':patch})
    check(len(images)==len(data), 'delivered image count')
    for evidence in pub['facts']['region_evidence']:
        witness = evidence['complete_witness']
        if witness:
            obs = next(o for o in pub['facts']['observations'] if o['view_name']==witness['view_name'])
            check(obs['pixel_rows'][witness['pixel_row_index']]['roi_id']==evidence['roi_id'] and obs['pixel_rows'][witness['pixel_row_index']]['readable'], 'complete witness references delivered readable pixels')
            check(pub['target_view_classifications'][witness['view_name']][evidence['roi_id']]['complete'], 'witness also geometrically complete')
    return {'slot':str(slot),'counts':counts,'views':expected_views,'capture_objects':len(meshes),'revision':main['capture_state']['revision'],'retained_names':index_names,'data':data,'regions':normal_regions,'classes':pub['target_view_classifications'],'evidence':pub['facts']['region_evidence'],'camera':main['observation_target']['camera_plan'],'binding':pub['binding']['binding_sha256'],'geometry':pub['binding']['geometry_identity']}


def equal_frames(a,b):
    check(len(a)==len(b),'same frame count')
    for left,right in zip(a,b):
        check(left['view']==right['view'],'same actual view')
        for key in ('color','depth','owner','source_local','patch'):
            check(np.array_equal(left[key],right[key]),'normalized '+key+' pixel equality')


def summarize(record):
    return {k:v for k,v in record.items() if k not in ('data','regions','classes','evidence','camera')}


def main():
    records=[]
    for kind in ('main','target_only'):
        for pair in (1,2,3):
            a,b = [inspect(ROOT/'formal'/f'{arm}{pair}_{kind}',1 if kind=='main' else 2,['SCENE'] if kind=='main' else ['SCENE','LEFT'],kind) for arm in ('A','B')]
            for key in ('regions','classes','evidence','camera'):
                check(a[key]==b[key], 'pair current '+key+' equality')
            equal_frames(a['data'],b['data'])
            check(a['capture_objects']==(14 if kind=='main' else 1) and b['capture_objects']==(6 if kind=='main' else 1),'expected actual acquisition scope')
            records.extend([summarize(a),summarize(b)])
    cache=[]
    resources={}
    for phase,covers in [('baseline',1),('moved',0),('restored',1)]:
        cache.append(inspect(ROOT/'controls/B_cache_move_restore/phases'/phase,covers,['SCENE'],moved=phase=='moved',resources=resources))
    check([r['revision'] for r in cache]==[1,2,3],'cache source revisions')
    check(len({r['binding'] for r in cache})==3,'three distinct live bindings')
    check('M4_Far_11' not in cache[0]['retained_names'] and 'M4_Far_11' in cache[1]['retained_names'] and 'M4_Far_11' not in cache[2]['retained_names'],'excluded moved blocker becomes retained')
    equal_frames(cache[0]['data'],cache[2]['data'])
    check(not np.array_equal(cache[0]['data'][0]['depth'],cache[1]['data'][0]['depth']),'moved depth actually changes')
    check(not np.array_equal(cache[0]['data'][0]['owner'],cache[1]['data'][0]['owner']),'moved asset owner actually changes')
    for op in ('MOVE','RESTORE'):
        receipt=read(ROOT/f'controls/B_cache_move_restore/native/QA_FAR11_{op}_RECEIPT.json')['response']['result']
        identity=[[float(i==j) for j in range(4)] for i in range(4)]
        check(receipt['matrix_before']==identity and receipt['matrix_after']==identity,'actual identity matrix during vertex fixture')
        check(receipt['vertices_written']==289 and receipt['faces_unchanged'],'actual fixed vertex fixture writes')
    old_a = inspect(Path('D:/he_m4_camera_001/controls/NEW_peripheral'),0,['SCENE'],legacy=True)
    old_b = inspect(ROOT/'controls/B_legacy_peripheral',0,['SCENE'],legacy=True)
    for key in ('regions','classes','evidence','camera'):
        check(old_a[key]==old_b[key],'legacy '+key+' equality')
    equal_frames(old_a['data'],old_b['data'])
    roi=old_a['regions'][0]['roi_id']
    check(old_a['evidence'][0]['complete_witness'] is None,'legacy null complete witness')
    # LEFT direction is (-1,0,1). Projecting Near to target x=1 changes
    # z to z+x-1, leaving a right triangle with both legs x inside [0,1]^2.
    near_x=Fraction(ORIGINALS['M4_Near']['world_vertices_m'][0][0])
    check(0<near_x<1, 'Near front-side positive sliver')
    exact_area=near_x*near_x/2
    check(exact_area==Fraction(73786983304225,9223372036854775808),'independent LEFT shadow area')
    check(Fraction(old_a['classes']['LEFT'][roi]['first_blocker']['overlap_area_screen_exact'])==exact_area,'legacy exact Near area')
    result={'status':'pass','checks':checks,'formal_slots':12,'formal_pairs':6,'formal_frames':18,'cache_phases':3,'legacy_slots':2,'formal':records,'cache':[summarize(r) for r in cache],'legacy':[summarize(old_a),summarize(old_b)],'coverage_scope':'Saved producer frames and actual wire captures. No new entrypoint run. Matrix setter invalidation not run.','new_Blender':0,'new_raster':0,'new_model':0}
    (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'pass','checks':checks,'formal_slots':12,'formal_frames':18,'cache_phases':3}))


if __name__=='__main__':
    main()
