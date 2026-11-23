"""Replay the frozen capture into the existing production stdio installation."""

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
CURVED_ROOT = Path('D:/he_m4_source_region_curved_view_sample_001').resolve()
ROOT = Path('D:/he_m4_yanyite_low_bilateral_product_native_001/preflight/product').resolve()
CURVED = V/'m4_source_region_curved_view_sample_001'
CURVED_REPLAY = run_path(str(CURVED/'replay.py'))
OLD = CURVED_REPLAY['OLD']
require, read, write, pin, git = (CURVED_REPLAY[k] for k in ('require','read','write','pin','git'))
BINDING = CURVED/'install/PRODUCT_RUN_BINDING.json'
PRODUCT = 'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237'
EVIDENCE = 'a62a86d526b29f9136c22fad9d2d0b4bc59d234b'
SOURCE = '98b95613011bf66d4b80b382fefbee8f3073c1c25d9891d21f21d698c53981e1'
WHEEL = '23cce9d9b042770f3d77147b9b0e1c06a6790c9f6dd196bb7da74b7d8322291c'
CAPTURE = '63ae6ed6bb6c372e31b91a814a6d6bb8f7171afdab8b8f47a91cf53f7d4bb2d5'
TERMINAL = 'ac102487f75c875e5c1fba2ea374b87295022dae4172359f068357a56b4e241b'
PLAN = 'f4a49c75477870b07022cf82c4896cafd279be98:docs/M4_YANYITE_LOW_BILATERAL_PRODUCT_NATIVE_001_PLAN.md'
ORACLE = V/'m4_yanyite_dual_curved_region_native_001/score/oracle.py'
BOXES = {'left': {'min': [-.09,-.14,.30], 'max': [-.04,.02,.50]},
         'right': {'min': [.04,-.14,.30], 'max': [.09,.02,.53]}}
EXPECTED = {
    'left': (199,139,.5097656218945279,'15ae8ef3a74539f6be145c8d17143d9ac35f529114dd35b0ba7a5b10d5d7179f',
             'LEFT',73106,114,(24,377,24047)),
    'right': (392,258,.47021484284290327,'5935331261c31d5d33b90eb94c66cf2418fb5961004e42a0fa9a09ceab91f129',
              'SCENE',55542,217,(24,384,13902)),
}


def inputs():
    fixture = OLD['sealed_inputs']()
    terminal_path = Path(fixture['original_slot'])/'TERMINAL_SOURCE.json'
    require(pin(terminal_path)['sha256'] == TERMINAL, 'frozen_bilateral_terminal_changed')
    for path in (BINDING,CURVED/'RESULT.json'):
        require(path.read_bytes() == git('show',EVIDENCE+':'+path.relative_to(V.parent).as_posix()),
                'frozen_curve_install_or_qualification_changed')
    index_path = CURVED_ROOT/'sealed/RAW_INDEX.json'
    archive = CURVED_ROOT/'sealed/ORIGINAL_RUNTIME.zip'
    index = read(index_path)
    registered = read(CURVED/'RESULT.json')['raw_archive']
    require(registered['archive']==index['archive']==pin(archive)
            and registered['member_count']==index['member_count']==len(index['members'])==1437,
            'frozen_curve_raw_archive_changed')
    cap_path = CURVED_ROOT/'arms/P1/CAPTURE_01.json'
    with ZipFile(archive) as z:
        cap_receipt = CURVED_REPLAY['pinned_member'](CURVED_ROOT,z,index,cap_path)
    require(cap_receipt['sha256'] == CAPTURE, 'frozen_captured_scene_bytes_changed')
    binding = read(BINDING)
    require((binding['preparation_git'],binding['source_sha256'],binding['wheel_sha256'])
                == (PRODUCT,SOURCE,WHEEL) and len(binding['source_manifest'])==143
            and pin(binding['wheel_path'])['sha256']==WHEEL, 'frozen_product_identity_changed')
    fixed_inputs = (Path(__file__),ORACLE,BINDING,CURVED/'RESULT.json',archive,index_path,
                    Path(binding['wheel_path']),*OLD['source_paths']())
    fixture['source_pins'] = list({row['path']:row for row in (
        *fixture['source_pins'],cap_receipt,*(pin(path) for path in fixed_inputs))}.values())
    plan = []
    for side, request, delta in zip(BOXES,fixture['calls'],fixture['deltas'],strict=True):
        query = OLD['renamed'](OLD['box_for'](request,BOXES[side]),'low-'+side,image=True)
        plan.append(OLD['case'](query,delta,fixture['terminal'],None,stage=side,box=True))
    fixture['capture_plan'] = [item['capture'] for item in plan]
    return binding,fixture,plan,read(cap_path)


def source_truth(terminal, capture):
    oracle = run_path(str(ORACLE))
    by_side = {}
    target,cube = capture['meshes']
    native_target,native_cube = (row['evaluated'] for row in terminal['objects'])
    for side, box in BOXES.items():
        args = (box['min'],box['max'])
        actual = oracle['region_truth'](target['vertices'],target['faces'],cube['vertices'],cube['faces'],args)
        native = oracle['region_truth'](native_target['vertices_world_m'],native_target['triangles'],
                                        native_cube['vertices_world_m'],native_cube['triangles'],args)
        nfaces,nverts,distance,rows_sha,*_ = EXPECTED[side]
        source_sha = sha256(json.dumps(actual['triangle_ids'],separators=(',',':')).encode()).hexdigest()
        require((actual['triangle_count'],actual['vertex_count'],actual['distance_m'],source_sha)
                    == (nfaces,nverts,distance,rows_sha)
                and native['triangle_ids']==actual['triangle_ids'] and native['vertex_ids']==actual['vertex_ids']
                and abs(native['distance_m']-actual['distance_m'])<=1e-7
                and native['direction_world']==actual['direction_world']==[0,0,1], 'independent_scene_truth_changed/'+side)
        by_side[side] = {'wire':actual,'native':native,'source_rows_sha256':source_sha}
    require(by_side['left']['wire']['distance_m']>=.49>by_side['right']['wire']['distance_m'],
            'threshold_or_order_changed')
    return by_side


def check_measurement(capture, body, value, truth, side):
    oracle = run_path(str(ORACLE))
    expected = truth['wire']
    reference,public = value['task_result'],body['task_result']
    target,cube = capture['meshes']
    fact = reference['facts']['surface_proximity']
    point = fact['value']['nearest_witness']
    a,b = point['a'],point['b']
    index = value['region_ref']
    faces = expected['triangle_ids']
    vertices = expected['vertex_ids']
    region = value['facts']['region']
    mapping = value['source_mapping']
    product_source_faces = [target['faces'][f] for f in faces]
    require(value['read_only'] is body['read_only'] is True
            and value['execution_authority'] is body['execution_authority'] is False
            and value['binding']['capture_state']==capture['capture_state']==reference['binding']['capture_state']
            and index['capture_generation']=={k:capture['capture_state'][k] for k in ('instance_id','epoch','revision')}
            and body['region_ref']==reference['region_ref']==index
            and body['region']['source_triangle_count']==len(faces) and body['region']['source_vertex_count']==len(vertices)
            and index['source_triangle_indices']==region['source_triangle_indices']==mapping['submesh_to_source_triangle_indices']==faces
            and region['source_vertex_indices']==mapping['submesh_to_source_vertex_indices']==vertices
            and mapping['triangles_source_vertices']==product_source_faces
            and [[vertices[j] for j in row] for row in mapping['triangles_submesh_vertices']]==product_source_faces
            and reference['measurement_scope']==public['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface'
            and reference['reference']==public['reference'] and reference['reference']['object_id']==cube['object_id']
            and reference['binding']['image_scope']['participation_mask']==[True,False]
            and fact==public['facts']['surface_proximity'] and fact['status']=='measured'
            and fact['value']['distance_m']==expected['distance_m']
            and point['direction_a_to_b']==expected['direction_world']
            and a[:2]==b[:2] and b[2]==1.0 and Fraction(b[2])-Fraction(a[2])==Fraction(*expected['distance_exact']),
            'actual_product_selection_measurement_or_binding_changed/'+side)
    require(any(oracle['triangle_contains'](a,[target['vertices'][v] for v in target['faces'][i]]) for i in faces)
            and any(oracle['triangle_contains'](b,[cube['vertices'][v] for v in face]) for face in cube['faces']),
            'actual_product_witness_not_on_source_or_reference/'+side)
    return fact


def check_one(np, side, position, request, reply, receipt, meter, cap_receipt, truth, archived):
    cap_path = ROOT/f'CAPTURE_{position:02d}.json'
    capture = read(cap_path)
    require(capture == archived and cap_receipt['capture_state']==capture['capture_state']
            and cap_receipt['resource_count']==(2 if position==1 else 0), 'actual_replay_capture_changed/'+side)
    body = json.loads(reply['result']['content'][0]['text'])
    producer_path = ROOT/'product_full'/f'call_{position:03d}'/'SERVICE_RESULT.json'
    value = read(producer_path)
    fact = check_measurement(capture,body,value,truth,side)
    frames,paths = OLD['selected_image_paths'](ROOT,body,value,reply['result']['content'])
    frame, = frames
    image, = body['images']
    path, = paths
    family = EXPECTED[side]
    visibility = value['facts']['visibility']
    pixels,sampled = CURVED_REPLAY['verify_arrays'](np,frame,visibility,value,image,value['frames'][0],witness_required=True)
    point = image['sampled_pixel']
    probe = value['stages'][CURVED_REPLAY['SELECTION_STAGE']]
    counts = value['work']
    require((frame['view'],pixels,sampled,tuple(point[k] for k in ('row','column','source_triangle_index')))==family[4:]
            and path==Path(frame['png']['path']).as_posix() and meter['raster_actual']==1
            and counts['capture_calls']==counts['world_box_selection_calls']==1
            and counts['sparse_view_probe_views']==(6 if side=='left' else 1)==len(probe['votes'])
            and probe['chosen_view']==frame['view'] and ((probe['votes']['SCENE']==0) if side=='left' else (probe['votes']['SCENE']>0)),
            'actual_image_pixels_path_or_raster_changed/'+side)
    cli = run_path(str(OLD['CLI_PATH']))['fixed_cli'](reply,require_all=True)
    require(cli['passed'] and len(cli['stages'])==6 and all(r['exact'] and r['original_images_exact'] for r in cli['stages']),
            'fixed_CLI_did_not_keep_low_box_facts_or_image/'+side)
    return {'stage':side,'producer':pin(producer_path),'capture':pin(cap_path),'wire':
            OLD['retained_workers']()[1]['bound_wire'](ROOT,request,receipt,meter),'source':truth,
            'measurement':fact,'frame':frame,'local_image_path':path,'sampled_pixel':point,
            'selected_pixels':pixels,'sampled_source_rows':sampled,'actual_rasters':1,'probe':probe,
            'service_ns':OLD['work_interval'](value,'service_total'),'cli':cli}


def preflight():
    binding,fixture,plan,capture = inputs()
    truth = source_truth(fixture['terminal'],capture)
    ROOT.mkdir(parents=True,exist_ok=False)
    before = sys.path[:]
    sys.path[:0] = [binding['dependency_root'],read(OLD['SEAL']/'SHARED_DEPENDENCY.json')['dependency_root'],
                   str(OLD['PRIOR']/'harness')]
    try:
        from runtime import ProductionStdioClient
    finally:
        sys.path[:] = before
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    cmd = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker']
    started = time.perf_counter_ns()
    held = ProductionStdioClient(cmd,ROOT,ROOT/'mcp',started+120_000_000_000,worker_evidence=ROOT/'mcp_io')
    replies = []
    try:
        identity = held.call(OLD['INIT'])['result']['_meta']['human_eye']
        held.call(OLD['NOTIFY'])
        tools = held.call(OLD['LIST'])['result']['tools']
        require(identity['source_sha256']==SOURCE and identity['source_kind']=='installed_distribution',
                'actual_preflight_production_identity_changed')
        OLD['catalogue_has_only_world_box_change'](tools)
        for item in plan:
            reply = held.call(item['request'])
            require('error' not in reply and reply['result']['isError'] is False,
                    'actual_low_box_failed/'+item['stage']+'/'+str(reply['result']['content'][0]['text'])[:500])
            replies.append(reply)
        ready = time.perf_counter_ns()
    finally:
        close = held.finish()
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code']==0,'actual_preflight_production_close_missing')
    ended = time.perf_counter_ns()
    worker = read(ROOT/'REPLAY_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0,
            'offline_preflight_acted_outside_original_read_only_inputs')
    wire = [row for line in (ROOT/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
            if (row:=json.loads(line))['method']=='tools/call']
    np = CURVED_REPLAY['np_module'](binding)
    checks = []
    for index,(item,reply,receipt,meter,cap_receipt) in enumerate(
            zip(plan,replies,held.records[3:],wire,worker['calls'],strict=True),1):
        side = item['stage']
        checks.append(check_one(np,side,index,item['request'],reply,receipt,meter,cap_receipt,truth[side],capture))
    result = {'passed':True,'role':'product_offline_qualification','plan':PLAN,'plan_sha256':sha256(git('show',PLAN)).hexdigest(),
              'product_git':PRODUCT,'source_sha256':SOURCE,'wheel_sha256':WHEEL,'requests':checks,
              'actual_MCP_business':len(checks),'actual_rasters':sum(row['actual_rasters'] for row in checks),
              'actual_Blender_starts':0,'actual_models':0,'source_pins':fixture['source_pins'],
              'held_close':pin(ROOT/'mcp/HELD_CLOSE.json'),'actual_tools':tools,
              'through_last_response_ns':ready-started,'window_ns':ended-started}
    write(ROOT/'SUMMARY.json',result)
    print(ROOT/'SUMMARY.json',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    args = parser.parse_args()
    if args.worker:
        require(ROOT.is_dir() and not (ROOT/'REPLAY_CLOSE.json').exists(),'actual_product_preflight_root_required')
        binding,fixture,_,_ = inputs()
        raise SystemExit(OLD['retained_workers']()[0]['worker'](ROOT,BINDING,'low_bilateral',False,source=fixture))
    preflight()
