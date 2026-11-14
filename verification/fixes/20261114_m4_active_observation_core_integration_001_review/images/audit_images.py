"""Independent data-only audit; never imports product modules or renders."""
from pathlib import Path
from fractions import Fraction
import ast
import hashlib
import json
import numpy as np
from PIL import Image

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
DELIVERY = ROOT / 'verification/m4_active_observation_core_integration_001'
OUT = Path(__file__).resolve().parent
checks, pixel_rows, file_reads = [], [], {}

def check(name, value, detail=None):
    checks.append({'name': name, 'passed': bool(value), 'detail': detail})

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    file_reads[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def read(path):
    return json.loads(raw(path))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def vector(values):
    return tuple(Fraction(x) for x in values)

def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

inputs = read(DELIVERY / 'INPUTS.json')
qual = read(DELIVERY / 'external/run/qualify_r2/QUALIFICATION.json')
source_qual = read(DELIVERY / 'runs/source_qualification/QUALIFICATION.json')
observations = read(DELIVERY / 'external/run/observe_r2/OBSERVATIONS.json')
archives = read(DELIVERY / 'EXTERNAL_ARCHIVE.json')
archive_by_source = {str(Path(x['source'])): x for x in archives['files']}
scenes = {name: read(DELIVERY / row['file']) for name, row in inputs['scenes'].items()}
cameras = {name: read(DELIVERY / row['file']) for name, row in inputs['cameras'].items()}
indexes = {row['scene']: row['index'] for row in qual['representations'] if not row['diagnostics_enabled']}
source = raw(ROOT / 'human_eye_plugin/active_observation_images.py').decode('utf8')
tree = ast.parse(source)
funcs = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
body = lambda name: ast.get_source_segment(source, funcs[name])

# Static source facts for the unchanged adapter dependency contract.
check('all_normalized_objects_are_meshed', 'enumerate(objects)' in body('_meshes_from_objects'))
check('mesh_uses_all_actual_faces', 'np.asarray(faces, dtype=np.int32)' in body('_meshes_from_objects'))
check('single_raster_receives_complete_mesh_tuple', 'self.meshes,' in body('render_view') and 'return_owner=True' in body('render_view'))
check('canonical_region_corners_drive_projection', 'region.vertices' in body('_pixel_rows'))
check('region_normal_drives_front', 'region.normal' in body('_pixel_rows'))
check('no_face_count_four_vertex_shortcut', 'len(mesh.vertices) == 4' not in source and 'len(mesh.faces) == 2' not in source)
check('source_and_camera_binding_before_feedback', body('observe_frame').index('current_scene_camera_frame_required') < body('observe_frame').index('_pixel_rows'))
check('owner_order_and_pose_bound', 'current_frame_geometry_camera_binding_required' in body('observe_frame'))
check('stored_vs_memory_arrays_checked', 'np.array_equal(supplied, values)' in body('observe_frame'))
check('PNG_matches_actual_RGB', 'np.array_equal(np.asarray(image), buffers[\'color\'])' in body('observe_frame'))
check('feedback_after_pixel_recompute', body('observe_frame').index('_pixel_rows') < body('observe_frame').index('self.session.observe'))
check('same_frame_cache_return', "return self._frames[view_name]" in body('render_view'))
check('changed_bindings_clear_frame_cache', 'self._frames.clear()' in body('_synchronize'))
check('same_source_rebind_checks_owner_order_and_cameras', 'mesh_order_identity ==' in body('_synchronize') and 'self.session.cameras == self._cameras' in body('_synchronize'))
check('surface_boundary_rgb_thresholds_retained', all(s in source for s in ("'minimum_surface_pixels': 16", "'minimum_boundary_pixels': 4", "'minimum_rgb_boundary_contrast': 24")))
check('short_facts_not_model_delivery_claim', 'local_core_validation' in raw(ROOT / 'human_eye_plugin/active_observation.py').decode('utf8'))

def files_for_new(frame, tag):
    files = {}
    for kind, field, hashfield in [('image','image_path','image_sha256'), ('arrays','arrays_path','arrays_sha256')]:
        original = Path(frame[field])
        row = archive_by_source[str(original)]
        archived = ROOT / row['archive']
        data = raw(archived)
        check(tag + ':' + kind + ':archive', sha(data) == row['sha256'] == frame[hashfield] and len(data) == row['bytes'])
        check(tag + ':' + kind + ':original_equals_archive', raw(original) == data)
        files[kind] = archived
    return files

def inspect_pixels(tag, scene_name, pose, regions, rows, files, frame=None):
    scene = scenes[scene_name]
    with np.load(files['arrays'], allow_pickle=False) as z:
        arrays = {k: z[k] for k in ('color', 'depth', 'owners')}
    rgb, depth, owner = (arrays[k] for k in ('color', 'depth', 'owners'))
    with Image.open(files['image']) as im:
        check(tag + ':png_rgb', im.format == 'PNG' and im.mode == 'RGB' and np.array_equal(np.asarray(im), rgb))
    size = pose['size_px'][0]
    check(tag + ':shapes_dtypes', rgb.shape == (size,size,3) and depth.shape == owner.shape == (size,size) and rgb.dtype == np.uint8 and depth.dtype == np.float64 and owner.dtype == np.int32)
    check(tag + ':owner_range', np.all((owner >= -1) & (owner < len(scene['objects']))))
    check(tag + ':background_depth', np.all(np.isposinf(depth[owner == -1])))
    check(tag + ':foreground_depth', np.all(np.isfinite(depth[owner >= 0]) & (depth[owner >= 0] > 0)))
    if frame:
        for key, a in arrays.items():
            expected = frame['arrays'][key]
            check(tag + ':' + key + ':metadata', expected == {'dtype': str(a.dtype), 'shape': list(a.shape), 'nbytes': a.nbytes, 'sha256': sha(a.tobytes())})
        check(tag + ':all_mesh_counts', frame['all_object_count'] == len(scene['objects']) and frame['all_triangle_count'] == sum(len(x['triangles']) for x in scene['objects']))
        check(tag + ':bytes', frame['PNG_bytes'] == files['image'].stat().st_size and frame['compressed_array_file_bytes'] == files['arrays'].stat().st_size and frame['array_payload_bytes'] == sum(a.nbytes for a in arrays.values()))
    # Independently accumulate 4-neighbour boundaries in integer squared RGB.
    boundary = np.zeros(owner.shape, dtype=bool)
    for dy, dx in ((1, 0), (0, 1)):
        a = (slice(0, size-dy), slice(0, size-dx))
        b = (slice(dy, size), slice(dx, size))
        diff = rgb[a].astype(np.int32) - rgb[b].astype(np.int32)
        marked = (owner[a] != owner[b]) & ((diff*diff).sum(axis=2) >= 24**2)
        boundary[a] |= marked
        boundary[b] |= marked
    by_id = {r['roi_id']: r for r in regions}
    readable = set()
    for row in rows:
        region = by_id[row['roi_id']]
        obj = scene['objects'][region['object_index']]
        verts = [vector(v) for v in obj['vertices']]
        face = obj['triangles'][0]
        a,b,c = (verts[i] for i in face)
        normal = cross(tuple(y-x for x,y in zip(a,b)), tuple(y-x for x,y in zip(a,c)))
        expected_front = sum(n*d for n,d in zip(normal, vector(pose['target_to_eye_unit']))) > 0
        stored_normal = vector(region['normal'])
        check(tag + ':' + row['roi_id'] + ':front_normal_orientation', sum(a*b for a,b in zip(normal, stored_normal)) > 0)
        corners = [vector(v) for v in region['vertices']]
        check(tag + ':' + row['roi_id'] + ':canonical_corners_from_source', len(corners) == 4 and all(v in verts for v in corners))
        surface = int((owner == region['object_index']).sum())
        contrast = int((boundary & (owner == region['object_index'])).sum())
        actual = {'roi_id': region['roi_id'], 'object_index': region['object_index'], 'view': pose['name'], 'front_facing': expected_front, 'visible_surface_pixels': surface, 'contrasting_boundary_pixels': contrast, 'readable': expected_front and surface >= 16 and contrast >= 4, 'minimum_surface_pixels':16, 'minimum_boundary_pixels':4, 'minimum_rgb_boundary_contrast':24}
        check(tag + ':' + row['roi_id'] + ':pixel_fact', all(row[k] == v for k,v in actual.items()), actual)
        check(tag + ':' + row['roi_id'] + ':full_triangle_identity', row['triangle_indices'] == region['triangle_indices'] and row['source_triangles'] == len(obj['triangles']) and row['source_vertices'] == len(obj['vertices']))
        pixel_rows.append({'source': tag, **actual})
        if actual['readable']: readable.add(actual['roi_id'])
    return readable

new_sequences = {}
for chain in observations['chains']:
    name = chain['camera']
    poses = {p['name']:p for p in cameras[name]['views']}
    idx = indexes['grid16_permuted_alternating']
    regions = idx['regions']
    ids = [r['roi_id'] for r in regions]
    covered, gains, views = set(), [], []
    check(name + ':frame_step_counts', len(chain['frames']) == len(chain['steps']))
    for number, (record,step) in enumerate(zip(chain['frames'],chain['steps']),1):
        frame = record['frame']
        view = frame['view_name']
        tag = 'new:' + name + ':' + str(number)
        check(tag + ':pose', frame['pose'] == poses[view])
        check(tag + ':source_binding', frame['scene_identity'] == idx['scene_identity'] == chain['facts']['scene_identity'] and frame['candidate_identity'] == chain['facts']['candidate_identity'])
        check(tag + ':intent', record['status'] == 'completed' and record['attempt']['view'] == view and record['attempt']['chain'] == name)
        files = files_for_new(frame, tag)
        readable = inspect_pixels(tag, 'grid16_permuted_alternating', poses[view], regions, step['pixel_rows'], files, frame)
        check(tag + ':receipt', step['receipt']['pixel_rows'] == step['pixel_rows'] and set(step['receipt']['readable_roi_ids']) == readable and step['receipt']['image_sha256'] == frame['image_sha256'] and step['receipt']['image_ref'] == frame['image_ref'])
        # BACK64 changes projection span, not direction; it returns no readable ROI.
        # For the other views the normal-pool exact mask is identical.
        mask = idx['view_masks'][view] if view != 'BACK64' else 0
        check(tag + ':BACK64_zero_feedback', view != 'BACK64' or len(readable) == 0)
        predicted = {identity for i,identity in enumerate(ids) if mask & (1<<i)}
        added = (readable & predicted) - covered
        covered |= (readable & predicted)
        gains.append(len(added)); views.append(view)
        check(tag + ':state_update', set(step['update']['new_roi_ids']) == added and set(step['update']['covered_roi_ids']) == covered)
        check(tag + ':summary', set(step['summary']['covered_roi_ids']) == covered and step['summary']['observed_views'] == views and step['summary']['state_updates'] == number)
        check(tag + ':short_facts', all('triangle_indices' not in r for r in chain['facts']['observations'][number-1]['pixel_rows']))
    expected_views = ['SCENE','BACK'] if name == 'normal' else ['SCENE','BACK64','LEFT','TOP']
    expected_gains = [2,3] if name == 'normal' else [2,0,2,1]
    check(name + ':expected_chain', views == expected_views and gains == expected_gains)
    unknown = [r for r in chain['facts']['regions'] if r['status'] == 'unknown']
    check(name + ':finite_pool_unknown', len(covered) == 5 and len(unknown) == 1 and unknown[0]['object_name'] == 'Obj_006' and unknown[0]['reason'] == 'finite_camera_pool_uncovered')
    check(name + ':local_validation_only', chain['facts']['image_delivery_scope'] == 'local_core_validation')
    new_sequences[name] = {'views':views,'gains':gains,'covered':sorted(covered),'unknown':unknown}

historical_files = set()
for side, q in [('source',source_qual),('installed',qual)]:
    check(side + ':no_replay_new_renders', q['new_renders'] == 0 and q['historical_frame_count'] == 8)
    for replay in q['offline_replays']:
        spec = next(x for x in inputs['offline_replays'] if x['id'] == replay['id'])
        scene_name = spec['scene']
        regions = indexes[scene_name]['regions']
        poses = {p['name']:p for p in cameras['normal']['views']}
        check(side + ':' + replay['id'] + ':replay_count', replay['new_renders'] == 0 and replay['historical_frames_read'] == len(spec['frames']) == 2)
        for n,(record,step) in enumerate(zip(spec['frames'],replay['steps'])):
            tag = 'historical:' + side + ':' + replay['id'] + ':' + str(n+1)
            files = {'image':DELIVERY/record['image_file'], 'arrays':DELIVERY/record['arrays_file']}
            historical_files.add(record['arrays_file'])
            check(tag + ':file_binding', sha(raw(files['image'])) == record['image_sha256'] and sha(raw(files['arrays'])) == record['arrays_sha256'])
            readable = inspect_pixels(tag,scene_name,poses[record['view_name']],regions,step['pixel_rows'],files)
            check(tag + ':readable', readable == set(step['receipt']['readable_roi_ids']))
    case=q['repeat_and_invalidation_case']
    check(side + ':invalidation_record', all(case[k] is True for k in ['repeat_state_and_facts_equal','duplicate_update_reused','scene_change_invalidated','camera_change_invalidated']) and case['new_renders'] == 0 and not case['final_summary']['covered_roi_ids'] and not case['final_summary']['observed_views'])

trace = [json.loads(x) for x in raw(DELIVERY/'external/run/observe_r2/TRACE.jsonl').splitlines()]
check('trace_exact_12_lines', len(trace) == 12)
check('six_intents_six_completed', [x['event'] for x in trace] == ['render_attempt','frame_complete']*6)
for index, intent in enumerate(trace[::2],1):
    reserve=read(DELIVERY/f'external/run/render_budget/{index:02d}.json')
    check('reserve:'+str(index), all(intent[k] == v for k,v in reserve.items()))
check('new_render_count', observations['new_render_attempts'] == 6)
check('historical_distinct_frame_files', len(historical_files) == 8)
check('all_independent_pixel_rows', len(pixel_rows) == 132 and sum(r['source'].startswith('new:') for r in pixel_rows) == 36)
result = {'schema':'root-independent-image-review-v1','commit':'cd863183b18e35d2ca38f75c0756e1c46e1a1ccb', 'passed':all(x['passed'] for x in checks),'check_count':len(checks),'failed_count':sum(not x['passed'] for x in checks),'checks':checks,'pixel_rows':pixel_rows,'new_sequences':new_sequences,'new_frames_read':6,'new_pixel_rows':36,'historical_frame_files':8,'historical_logical_replays':16,'historical_pixel_rows':96,'file_reads':file_reads,'new_renders':0,'product_calls':0,'model_calls':0,'Blender_calls':0,'notes':['Independent arithmetic recomputes recorded pixel facts from existing PNG/NPZ, does not independently rerasterize geometry.','Repeat/invalidation behavior reviewed statically and through retained source/installed receipts; not reexecuted.','BACK64 has zero readable ROI; its full-pool prediction mask is not inferred by this audit.']}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ['passed','check_count','failed_count','new_frames_read','new_pixel_rows','historical_logical_replays','historical_pixel_rows']}))
for c in checks:
    if not c['passed']: print(json.dumps(c,ensure_ascii=False))
