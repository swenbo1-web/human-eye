"""Independent original-byte and sampled-ray review. No product code executes."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = Path('D:/he_m4_source_region_display_001/sessions')
OLD = Path('D:/hefe/verification/fixes/20261117_real_asset_region_review/delivery/review_real_asset.py')
OLD_SHA = '8ccd3f699edcf80916ba80b5f86fd9e437995e9f3123efcbe3368769c3cd7b74'
assert hashlib.sha256(OLD.read_bytes()).hexdigest() == OLD_SHA
spec = importlib.util.spec_from_file_location('_our_saved_review_math', OLD)
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
CHECKS, PINS, GROUPS, FRAMES = [], {str(OLD): OLD_SHA}, {}, []
R.S.H.CHECKS, R.S.H.PINS = CHECKS, PINS
require, read, raw, rows, sha = R.require, R.read, R.raw, R.rows, R.sha
STATES = dict(main=('initial', 'repeat'), state=('initial', 'cube_visible', 'cube_restored', 'target_hidden', 'target_restored', 'repeat'))


def nearest(origins, direction, triangles, eligible, pose):
    indices = np.flatnonzero(eligible)
    if not len(indices):
        return np.full(len(origins), np.inf), np.full(len(origins), -1, dtype=int), np.zeros(len(origins), dtype=bool)
    with np.errstate(invalid='ignore'):
        depth, face, ambiguity = R.nearest_samples(origins, direction, triangles[indices], pose['near'], pose['far'])
    face[face >= 0] = indices[face[face >= 0]]
    ambiguity &= face >= 0
    return depth, face, ambiguity


def numeric_review(full, capture, arrays, label):
    frame = full['frames'][0]
    pose = frame['pose']
    triangles, objects, offsets = R.prepare_triangles(capture)
    mask = np.asarray(frame['image_scope']['participation_mask'])
    key = sha(([(m['vertices'], m['faces']) for m in capture['meshes']], pose, mask.tolist()))
    if key in GROUPS:
        old = GROUPS[key]
        require(all(old['array_hashes'][k] == hashlib.sha256(arrays[k].tobytes()).hexdigest() for k in old['array_hashes']), label+'/same numerical group exact RGB/depth/owner/triangle buffers')
        return old
    foreground = arrays['owners'] >= 0
    ys, xs = np.nonzero(foreground)
    origin, direction, inside = R.pixel_rays(xs, ys, pose)
    claimed = arrays['triangle_ids'][foreground]
    residual = 0.
    min_barycentric = None
    if len(claimed):
        t = triangles[claimed]
        a, e, f = t[:, 0], t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]
        normal = np.cross(e, f)
        denom = normal @ direction
        distance = np.einsum('ij,ij->i', a-origin, normal)/denom
        delta = origin+distance[:, None]*direction-a
        squared = np.einsum('ij,ij->i', normal, normal)
        u = np.einsum('ij,ij->i', np.cross(f, normal), delta)/squared
        v = np.einsum('ij,ij->i', np.cross(normal, e), delta)/squared
        minimum = np.minimum(np.minimum(u, v), 1-u-v)
        min_barycentric = float(minimum.min())
        require(np.all(inside) and np.all(denom != 0) and min_barycentric >= 0, label+'/every foreground source point strict independent plane barycentric membership')
        residual = float(np.max(np.abs(distance-arrays['depth'][foreground])))
        require(residual <= 1e-8 and np.all(distance >= pose['near']) and np.all(distance <= pose['far']), label+'/every source point depth independently reconstructed')
        light = np.array([.4, -.5, 1.])
        light /= np.linalg.norm(light)
        shading = .45+.55*np.abs(normal @ light)/np.linalg.norm(normal, axis=1)
        rgb = np.clip(shading[:, None]*[180, 190, 205], 0, 255).astype(np.uint8)
        require(np.array_equal(rgb, arrays['color'][foreground]), label+'/every foreground source normal gives exact saved RGB')
    require(np.all(np.isinf(arrays['depth'][~foreground])) and np.all(arrays['color'][~foreground] == [18, 22, 30]), label+'/all background pixels depth and published raster background RGB')
    eligible = mask[objects]
    grid = np.floor((np.arange(16)+.5)*512/16).astype(int)
    gx, gy = np.tile(grid, 16), np.repeat(grid, 16)
    origins, direction, inside = R.pixel_rays(gx, gy, pose)
    d, winner, ambiguity = nearest(origins, direction, triangles, eligible, pose)
    hit = winner >= 0
    require(inside.all() and np.array_equal(hit, foreground[gy, gx]), label+'/fixed256 grid nearest displayed foreground')
    require(np.all(np.abs(d[hit]-arrays['depth'][gy[hit], gx[hit]]) <= 1e-8), label+'/all fixed grid hit depths including ambiguous boundaries')
    certain = hit & ~ambiguity
    require(np.array_equal(winner[certain], arrays['triangle_ids'][gy[certain], gx[certain]]) and np.array_equal(objects[winner[hit]], arrays['owners'][gy[hit], gx[hit]]), label+'/grid exact nearest source identities away from numeric edge ties')
    source = next(i for i, m in enumerate(capture['meshes']) if m['object_id'] == full['region_ref']['host_id'])
    selected = np.asarray(full['region_ref']['source_triangle_indices'])
    centers = triangles[offsets[source]+selected].mean(axis=1)
    view = np.asarray(pose['view_matrix'])
    inv = np.linalg.inv(view)
    target_depth = -(centers @ view[2, :3]+view[2, 3])
    origins = centers+target_depth[:, None]*inv[:3, 2]
    cd, cf, ca = nearest(origins, -inv[:3, 2], triangles, eligible, pose)
    blocked = np.isfinite(cd) & (cd < target_depth-1e-8)
    visible = np.isfinite(cd) & (np.abs(cd-target_depth) <= 1e-8)
    if not mask[source]:
        require(np.all(cf == -1), label+'/all748 hidden target centroid rays contain no displayed geometry')
    elif mask[1]:
        require(blocked.all() and np.all(objects[cf] == 1), label+'/all748 source centroids occluded by displayed Cube')
    else:
        require(visible.any() and blocked.any(), label+'/selected source centroids include actual visible and self-occluded surfaces')
    result = dict(participation_mask=mask.tolist(), declared_source_members=len(xs), min_barycentric=min_barycentric,
        max_depth_residual_m=residual, fixed_grid_rays=256, grid_hits=int(hit.sum()), grid_ambiguous=int(ambiguity.sum()),
        selected_centroid_rays=748, centroid_visible=int(visible.sum()), centroid_blocked=int(blocked.sum()),
        centroid_ambiguous=int(ca.sum()), participating_source_triangles=int(eligible.sum()),
        actual_ray_triangle_pairs=1004*int(eligible.sum()), full_foreground_nearest_surface_claim=False,
        array_hashes={k: hashlib.sha256(arrays[k].tobytes()).hexdigest() for k in ('color', 'depth', 'owners', 'triangle_ids')})
    GROUPS[key] = result
    return result


def frame_review(full, capture, label):
    frame, binding = full['frames'][0], full['binding']
    png, npz = raw(frame['image_path']), raw(frame['arrays_path'])
    require(hashlib.sha256(png).hexdigest() == frame['image_sha256'] and hashlib.sha256(npz).hexdigest() == frame['arrays_sha256'], label+'/saved original PNG NPZ SHA')
    with np.load(BytesIO(npz), allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    require(np.array_equal(np.asarray(Image.open(BytesIO(png))), arrays['color']), label+'/PNG matches NPZ RGB')
    for key, meta in frame['arrays'].items():
        a = arrays[key]
        require(meta == dict(dtype=str(a.dtype), shape=list(a.shape), nbytes=a.nbytes, sha256=hashlib.sha256(a.tobytes()).hexdigest()), label+'/original array metadata '+key)
    triangles, owners, offsets = R.prepare_triangles(capture)
    require(offsets.tolist() == [0, 53264, 53276] and frame['all_triangle_count'] == 53276 and frame['all_object_count'] == 2, label+'/all full-source53276 global source IDs retained')
    require(np.array_equal(offsets, arrays['face_patch_offsets']) and np.all(arrays['face_patch_ids'] == -1) and arrays['patch_roi_ids'].size == 0 and np.all(arrays['patch_owners'] == -1), label+'/unchanged full patch mapping offsets')
    fg = arrays['owners'] >= 0
    face, obj = arrays['triangle_ids'][fg], arrays['owners'][fg]
    require(np.array_equal(arrays['triangle_ids'] >= 0, fg) and np.all(face >= offsets[obj]) and np.all(face < offsets[obj+1]), label+'/every foreground globalface owns current fullmesh')
    scope = binding['image_scope']
    require(frame['display_identity'] == binding['display_identity'] == scope['identity'] == arrays['display_identity'].item() and frame['image_scope'] == scope and frame['image_scope_identity'] == sha(scope) == arrays['image_scope_identity'].item(), label+'/frame display and exact NPZ metadata identities')
    require(arrays['display_object_mask'].tolist() == scope['participation_mask'] and np.all(np.asarray(scope['participation_mask'])[obj]), label+'/foreground owners participate in actual mask')
    geometry = [(tuple(tuple(F(v) for v in p) for p in m['vertices']), tuple(tuple(f) for f in m['faces'])) for m in capture['meshes']]
    mapping = sha(dict(version='active-patch-owner-v1', roi_ids=(), ordered_geometry=geometry, face_patch_ids=[[-1]*len(m['faces']) for m in capture['meshes']]))
    owner = sha(('active-dual-owner-v1', 'zero-based-global-source-triangles-in-mesh-order', mapping, offsets.tolist()))
    require(frame['patch_mapping_identity'] == mapping == arrays['patch_mapping_identity'].item() and frame['owner_mapping_identity'] == owner == arrays['owner_mapping_identity'].item(), label+'/independent full source mapping digest preimages')
    fb = (binding['geometry_identity'], binding['camera_identity'], scope['identity'], sha(scope), tuple(scope['participation_mask']))
    fid = sha((fb, frame['owner_schema'], owner, 'SCENE', 1, frame['image_sha256']))
    require(frame['frame_identity'] == fid and frame['image_ref'] == 'source-region-image:'+sha((full['region_ref']['region_id'], fid, frame['image_sha256'])), label+'/display-aware frame and current reference preimages')
    require(frame['host_binding_sha256'] == binding['binding_sha256'] and frame['source_revision'] == binding['scene_revision'] and frame['scene_identity'] == binding['geometry_identity'] and frame['candidate_identity'] == binding['camera_identity'], label+'/frame bound actual current full source and camera')
    require(frame['pose'] == next(v for v in binding['camera_specification']['views'] if v['name'] == 'SCENE'), label+'/actual SCENE published camera')
    selected = np.asarray(full['region_ref']['source_triangle_indices'])
    selected_mask = np.isin(arrays['triangle_ids'], selected)
    yy, xx = np.nonzero(selected_mask)
    vis = full['facts']['visibility']
    seen = sorted(map(int, np.unique(arrays['triangle_ids'][selected_mask])))
    require(vis['selected_surface_pixels'] == len(xx) and vis['visible_source_triangle_indices'] == seen and vis['unseen_source_triangle_indices'] == sorted(set(selected)-set(seen)) and vis['visible_pixel_bounds'] == ([int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())] if len(xx) else None), label+'/every visibility summary derived exactly from saved actual current source pixels')
    require(vis['complete_witness'] is None and vis['unknown'] == ['complete_surface_visibility'] and vis['image_scope'] == scope, label+'/complete curved surface visibility retains unknown')
    numeric = numeric_review(full, capture, arrays, label)
    FRAMES.append(dict(label=label, image_path=frame['image_path'], frame_identity=fid, image_sha256=frame['image_sha256'], arrays_sha256=frame['arrays_sha256'], selected_pixels=len(xx), foreground_pixels=int(fg.sum()), numeric=numeric))
    return FRAMES[-1]


def public_review(full, public, blocks, label):
    if public.get('schema') == 'source-region-brief-v1':
        require(public['region_ref'] == full['region_ref'] and public['task_result'] == full['task_result'] and public['region'] == full['facts']['region'] and public['visibility'] == full['facts']['visibility'], label+'/brief exact same-producer source region measurement and status')
        require(public['binding'] == {k: v for k, v in full['binding'].items() if k != 'camera_specification'}, label+'/brief full current source display binding')
        expected = [dict(**{k: f[k] for k in ('image_ref', 'view_name', 'frame_identity', 'image_sha256', 'camera_identity', 'host_binding_sha256', 'display_identity', 'image_scope_identity') if k in f}, image_block_index=i+1) for i, f in enumerate(full['frames'])]
        require(public['images'] == expected and public['status'] == full['status'] and public['observation_status'] == full['observation_status'], label+'/brief current image metadata and zero-pixel status')
    else:
        a, b = copy.deepcopy(public), copy.deepcopy(full)
        a.pop('image_delivery', None)
        b.pop('image_delivery', None)
        require(a == b, label+'/normal full exact original same producer apart image_delivery')
    require(len(blocks) == 2 and blocks[1]['type'] == 'image' and blocks[1]['mimeType'] == 'image/png' and base64.b64decode(blocks[1]['data'], validate=True) == raw(full['frames'][0]['image_path']), label+'/original MCP native PNG exact published bytes')


def fresh_check(full, capture, fresh, label):
    by_name = {o['name']: o for o in fresh['objects']}
    require(fresh['source_sha256'] == '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d' and fresh['source_writes'] == 0, label+'/fresh export original blend and zero writes')
    for mesh in capture['meshes']:
        obj = by_name[mesh['name']]
        m, scale = obj['matrix_world'], fresh['unit_scale']
        world = [[(((m[k][0]*p[0]+m[k][1]*p[1])+m[k][2]*p[2])+m[k][3])*scale for k in range(3)] for p in obj['evaluated']['vertices']]
        require(world == mesh['vertices'] and obj['evaluated']['triangles'] == mesh['faces'], label+'/fresh exact full source local geometry plus transform '+mesh['name'])
    snapshot = capture['display_snapshot']
    require(sha({k: v for k, v in snapshot.items() if k != 'sha256'}) == snapshot['sha256'] and sha(fresh['display_snapshot']) == fresh['display_snapshot_sha256'], label+'/actual compact capture and richer fresh display snapshot each exact SHA')
    require(snapshot['view_layer'] == {k: fresh['display_snapshot']['view_layer'][k] for k in ('instance_id', 'name')}, label+'/compact and fresh richer active viewlayer instance same')
    scope = full['binding']['image_scope']
    require(scope['identity'] == snapshot['sha256'] and scope['snapshot_sha256'] == snapshot['sha256'] and scope['view_layer'] == snapshot['view_layer'] and scope['status'] == 'captured', label+'/image actual effective active viewlayer scope')
    rows_by_id = {o['host_id']: o for o in snapshot['objects']}
    for row in scope['objects']:
        original = rows_by_id[row['host_id']]
        exported = by_name[row['object_name']]
        require(row['instance_id'] == original['instance_id'] == exported['instance_id'] and all(row[k] == original[k] == exported['display'][k] for k in ('hide_get', 'hide_viewport', 'hide_render', 'visible_get')) and row['participates'] == original['visible_get'], label+'/current object flags effective participation '+row['object_name'])
    return scope


def session_review(name):
    session = ROOT/name
    captures = R.S.H.wire_captures(session)
    calls = rows(session/'PUBLIC_REQUESTS.jsonl')
    archives = rows(session/'product_full/INDEX.jsonl')
    require(len(calls) == len(STATES[name]) == len(archives), name+'/exact public requests and producer archives')
    output = []
    for c, state, archived in zip(calls, STATES[name], archives):
        label = name+'/'+state
        tx, rx = read(c['actual_TX_path']), read(c['actual_RX_path'])
        require(tx == c['request'] == read(c['request_path']) and rx == c['response'] == read(c['response_path']) and rx['id'] == tx['id'] and rx['result']['isError'] is False, label+'/original TX RX and public copies ID exact')
        require(hashlib.sha256(raw(c['actual_TX_path'])).hexdigest() == c['actual_TX_sha256'] and hashlib.sha256(raw(c['actual_RX_path'])).hexdigest() == c['actual_RX_sha256'], label+'/original TX RX SHA')
        a = c['producer_archive']
        require(a == archived and hashlib.sha256(raw(a['path'])).hexdigest() == a['sha256'], label+'/exact producer archive index and bytes')
        full = read(a['path'])
        capture = R.S.current_capture(full, captures, label)
        R.S.binding_ref(full, capture, label)
        fresh_state = 'target_restored' if state == 'repeat' and name == 'state' else 'initial' if state == 'repeat' else state
        scope = fresh_check(full, capture, read(session/('SOURCE_'+fresh_state+'.json')), label)
        public = json.loads(rx['result']['content'][0]['text'])
        public_review(full, public, rx['result']['content'], label)
        f = frame_review(full, capture, label)
        expected_mask = [state != 'target_hidden', state == 'cube_visible']
        require(scope['participation_mask'] == expected_mask, label+'/predeclared exact display state')
        partial = state in ('cube_visible', 'target_hidden')
        require(f['selected_pixels'] == (0 if partial else 35452) and f['foreground_pixels'] == (261121 if state == 'cube_visible' else 0 if state == 'target_hidden' else 166193), label+'/predeclared foreground and selected exact actual pixels')
        require(full['status'] == ('partial' if partial else 'complete') and full['observation_status'] == ('evidence_insufficient' if partial else 'locally_observed'), label+'/zero selected sample truthful top status')
        if partial:
            expected_reason = 'selected_region_not_displayed' if state == 'target_hidden' else 'selected_region_displayed_without_pixels'
            require(full['facts']['visibility']['status'] == 'unknown' and full['facts']['visibility']['reason'] == expected_reason, label+'/zero sample exact reason')
        surface = full['task_result']['facts']['surface_proximity']
        require(surface['status'] == 'measured' and surface['value']['distance_m'] == .37011719389236364 and len(full['source_mapping']['submesh_to_source_triangle_indices']) == 748 and len(full['source_mapping']['submesh_to_source_vertex_indices']) == 410, label+'/M3 complete selected geometry preserved independent of visibility')
        output.append(dict(state=state, full=full, capture=capture, wire_format=public['schema']))
    require(output[-1]['full']['work']['raster_attempts'] == 0 and output[-1]['full']['work']['frame_reuses'] == 1 and output[-1]['full']['work']['task_query']['result_cache_hit'] is True, name+'/same state repeat has zero raster and actual image plus M3 cache hit')
    prior = output[-2] if name == 'state' else output[0]
    require(output[-1]['full']['frames'] == prior['full']['frames'] and output[-1]['full']['region_ref'] == prior['full']['region_ref'], name+'/same-state repeated actual frame ref identical')
    require(read(calls[-1]['actual_TX_path'])['params']['arguments']['query']['region_ref'] == prior['full']['region_ref'], name+'/actual repeat passed delivered public ref')
    return output


def main():
    raw(Path(__file__))
    raw(R.PREVIOUS)
    raw(R.S.HELPER)
    product = Path('D:/he_m4_source_region_display_001/R0/product')
    for filename in ('source_region.py', 'active_observation_images.py', 'attention_raster.py', 'blender_host.py', 'task_brief.py'):
        raw(product/'human_eye_plugin'/filename)
    raw(next(product.glob('*.dist-info/runtime_sources.json')))
    main_calls, state_calls = session_review('main'), session_review('state')
    require([c['full']['region_ref']['capture_generation']['revision'] for c in state_calls] == [1, 2, 3, 4, 5, 5], 'state actual generations1to5 plus same-generation repeat')
    initial = state_calls[0]
    for c in state_calls[1:]:
        require(c['capture']['meshes'] == initial['capture']['meshes'] and c['full']['region_ref']['ordered_geometry_sha256'] == initial['full']['region_ref']['ordered_geometry_sha256'], 'state/'+c['state']+'/geometry unchanged despite display generation')
    for c in (state_calls[2], state_calls[4]):
        require(c['full']['region_ref']['region_id'] != initial['full']['region_ref']['region_id'] and c['full']['frames'][0]['frame_identity'] == initial['full']['frames'][0]['frame_identity'] and c['full']['work']['raster_attempts'] == 1, 'restore/'+c['state']+'/fresh generation ref restored content identity reconstructed once')
    setters = []
    for state in ('CUBE_VISIBLE', 'CUBE_RESTORED', 'TARGET_HIDDEN', 'TARGET_RESTORED'):
        receipt = read(ROOT/'state'/(state+'_RECEIPT.json'))['response']['result']
        require(receipt['fixture_hide_set_setters'] == 1 and receipt['product_setters'] == 0 and receipt['source_asset_saved'] is False, 'fixture/'+state+'/one isolated setter zero product setter zero save')
        setters.append(receipt)
    require(setters[0]['before_fingerprint'] == setters[-1]['after_fingerprint'], 'four actual fixture setter complete restore fingerprint')
    all_calls = main_calls+state_calls
    totals = dict(public_requests=len(all_calls), PNG_deliveries=len(FRAMES), constructions=sum(c['full']['work']['raster_attempts'] for c in all_calls),
        declared_source_members=sum(f['foreground_pixels'] for f in FRAMES), grid_rays=len(FRAMES)*256, selected_centroid_rays=len(FRAMES)*748)
    require(totals == dict(public_requests=8, PNG_deliveries=8, constructions=6, declared_source_members=1258279, grid_rays=2048, selected_centroid_rays=5984), 'all eight original delivery coverage denominators')
    require(len(GROUPS) == 3, 'only three numerically distinct full-geometry camera display-mask groups')
    require(all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in PINS.items()), 'all original read inputs retain identical SHA at review completion')
    result = dict(status='passed', author_commit='aa45f033ce662b7453dda77084b36da34640f558', product_commit='29f35a77', checks=len(CHECKS),
        new_live=0, new_MCP=0, new_raster=0, new_encoding=0, new_model=0, new_paid=0,
        actual_partial_full_wire='not_run', full_foreground_nearest_surface_claim=False,
        actual_wire_formats=dict(brief=sum(c['wire_format'] == 'source-region-brief-v1' for c in all_calls), normal_full=sum(c['wire_format'] == 'human-eye-source-region-observation-v1' for c in all_calls)),
        historical_AL_assignment='own handle b205d29d5b6d4ca8b7ad3c2ea6a31e74 historical child task740 expired; current explicit root747 delegation followed; no root-handle task mutation',
        totals=totals, executed_unique_numeric=dict(groups=len(GROUPS), declared_source_members=sum(g['declared_source_members'] for g in GROUPS.values()), fixed_grid_rays=sum(g['fixed_grid_rays'] for g in GROUPS.values()), selected_centroid_rays=sum(g['selected_centroid_rays'] for g in GROUPS.values()), ray_triangle_pairs=sum(g['actual_ray_triangle_pairs'] for g in GROUPS.values())),
        groups=GROUPS, frames=FRAMES, input_pins=PINS, assertions=CHECKS)
    (OUT/'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(CHECKS), totals=totals, unique=result['executed_unique_numeric'])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error), passed_checks=len(CHECKS), last_checks=CHECKS[-6:]), indent=2), encoding='utf8')
        raise
