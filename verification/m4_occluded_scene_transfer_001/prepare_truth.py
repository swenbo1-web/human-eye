"""Publish independent fixed-source truth once, before actual image qualification."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent


def main():
    started=time.perf_counter_ns()
    target=HERE/'admin'
    target.mkdir(exist_ok=True)
    if (target/'TRUTH.json').exists() or (target/'PIXEL_ALGORITHM.json').exists():
        raise FileExistsError('independent_truth_already_created')
    def guard(event,args):
        if event in ('subprocess.Popen','os.system','socket.connect','socket.bind'):
            raise RuntimeError('pure_truth_forbids_process_or_network')
        if event=='import' and str(args[0]).split('.')[0] in ('human_eye_plugin','human_eye_module1_operators','numpy','PIL','bpy'):
            raise RuntimeError('pure_truth_forbids_product_or_image_import')
    sys.addaudithook(guard)
    spec=importlib.util.spec_from_file_location('_transfer_independent_oracle',HERE/'oracle.py')
    oracle=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    scene_path=HERE/'inputs/SCENE_GEOMETRY_RATIONAL.json'
    cameras_path=HERE/'inputs/CAMERAS.json'
    capture_path=HERE/'inputs/CAPTURE_REPLAY.json'
    tasks_path=HERE/'inputs/TASK_INPUTS.json'
    scene,cameras,capture,tasks=map(oracle.read,(scene_path,cameras_path,capture_path,tasks_path))
    if capture['unit']!='m' or capture['coordinate_frame']!='world' or len(capture['meshes'])!=len(scene['objects']):
        raise ValueError('world_capture_contract')
    for obj,mesh in zip(scene['objects'],capture['meshes']):
        if obj['name']!=mesh['name'] or obj['triangles']!=mesh['faces'] or obj['vertices']!=mesh['vertices']:
            raise ValueError('independent_source_capture_geometry_binding')
    truth=oracle.geometry_truth(scene,cameras)
    for region in truth['regions']:
        region['host_id']=capture['meshes'][region['object_index']]['object_id']
    for expected,given in zip(truth['pixel_targets'],tasks['pixel_samples']):
        if expected['id']!=given['id']:
            raise ValueError('registered_pixel_target_order')
        expected.update(given)
    for expected,given in zip(truth['source_targets'],tasks['source_targets']):
        if any(expected[key]!=given[key] for key in ('id','object_name','object_index','source_triangle_indices')):
            raise ValueError('registered_source_target_binding')
    sets={v:{r['region_id'] for r in truth['regions'] if r['views'][v]['complete']} for v in truth['view_names']}
    union=set().union(*sets.values())
    covers=[]
    for count in range(1,7):
        covers=[list(combo) for combo in itertools.combinations(sets,count) if set().union(*(sets[v] for v in combo))==union]
        if covers:
            break
    truth.update(schema='occluded-transfer-independent-truth-v1',
        input_sha256=dict(scene=oracle.sha(scene_path),cameras=oracle.sha(cameras_path),capture=oracle.sha(capture_path),tasks=oracle.sha(tasks_path)),
        oracle_source_sha256=oracle.sha(HERE/'oracle.py'),prepare_source_sha256=oracle.sha(__file__),
        actual_product_raster_model_calls=0,actual_pixel_truth_status='unmeasured_until_single_qualification',
        geometric_only=dict(complete_sets={v:sorted(rows) for v,rows in sets.items()},
            complete_union=sorted(union),minimum_cover_size=count,minimal_covers=covers,
            SCENE_partial_with_complete_elsewhere=[r['region_id'] for r in truth['regions']
                if r['views']['SCENE']['front_facing'] and not r['views']['SCENE']['complete'] and r['region_id'] in union],
            no_positive_candidate=[r['region_id'] for r in truth['regions'] if not any(v['front_facing'] for v in r['views'].values())],
            positive_candidate_but_occluded=[r['region_id'] for r in truth['regions'] if any(v['front_facing'] for v in r['views'].values()) and r['region_id'] not in union]),
        derivation_cost_ns=time.perf_counter_ns()-started)
    algorithm=dict(schema='occluded-transfer-preregistered-pixel-algorithm-v1',
        source_path=str(HERE/'oracle.py'),source_sha256=oracle.sha(HERE/'oracle.py'),
        decoder_dependency_path=str(oracle.SHARED),decoder_dependency_sha256=oracle.sha(oracle.SHARED),
        entry='frame_pixels(frame,truth)',input='One actual saved PNG and NPZ plus actual current frame metadata, independent source truth.',
        binding='Verify whole PNG/NPZ hashes, all array shape/byte payload hashes, source raw triangle to source object owner, and published RGB equality.',
        region_mapping='Global source-triangle membership to ordered supported region_index. Unsupported source IDs remain -2 and background -1. Object IDs are not region IDs.',
        surface_pixels='Count each supported region mask over all 512x512 actual raw triangle pixels.',
        boundary_pixels='Four-neighbor unordered horizontal/vertical pairs. Region IDs differ and integer RGB squared distance >=576. Mark both endpoints and count owned marked pixels.',
        readable='Exact front-facing and actual surface count >=16 and contrasting boundary count >=4.',
        complete_readable='Independent exact geometric complete AND independently measured readable in the same actual frame.',
        pixel_target='At exact registered (view_name,x,y), zero-based upper-left, require actual raw source membership equals its private preregistered region_index.',
        bounds='Inclusive extrema of all owned pixels or null for empty.',
        anchor='Owned pixel nearest to bounds midpoint by integer squared distance; first row-major tie.',
        coverage='Exact per-view complete-readable sets, union, all combinations for minimum set-cover; never sum partial frames into a complete face.',
        qualification='At least3view cover, readable-incomplete SCENE surface with complete-readable elsewhere, positive-candidate blocked and no-positive reasons, both fixed pixel samples correctly owned.',
        actual_pixel_measurements=0,qualification_frames='Only the once-generated N six frames. Later derived PIXEL_TRUTH is a separate new file; TRUTH is never rewritten.')
    def save(name,value):
        path=target/name
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(value,stream,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)
            stream.write('\n')
        return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    files=[save('TRUTH.json',truth),save('PIXEL_ALGORITHM.json',algorithm)]
    print(json.dumps(dict(files=files,supported=len(truth['regions']),unsupported=len(truth['unsupported_source_triangles']),geometric_mincover=count,actual_product_raster_model_calls=0)))

if __name__=='__main__':
    main()
