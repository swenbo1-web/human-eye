"""Qualify both installed evidence endpoints on the new foot boxes offline."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m1_yanyite_foot_region_image_evidence_consumption_001/preflight').resolve()
PLAN = '8cf6015bc5dd7594298a30cb1687bea849760de6:docs/M1_YANYITE_FOOT_REGION_IMAGE_EVIDENCE_CONSUMPTION_001_PLAN.md'
PRIOR = V/'m1_source_region_image_evidence_001'
IMAGE_EVIDENCE = run_path(str(PRIOR/'replay.py'))
LOW = IMAGE_EVIDENCE['PREVIOUS']
CURVED = IMAGE_EVIDENCE['CURVED']
OLD = IMAGE_EVIDENCE['OLD']
require, read, write, pin, git = (IMAGE_EVIDENCE[k] for k in ('require','read','write','pin','git'))
CAPTURE = Path('D:/he_m4_source_region_curved_view_sample_001/arms/P1/CAPTURE_01.json')
CAPTURE_SHA = '63ae6ed6bb6c372e31b91a814a6d6bb8f7171afdab8b8f47a91cf53f7d4bb2d5'
TERMINAL_SHA = 'f022aa6addb84c34bff78bf077765c97951ac2f47a969d1684796d828dae9eea'
BINDINGS = {
    'A': (IMAGE_EVIDENCE['BASE_BINDING'], 'a62a86d526b29f9136c22fad9d2d0b4bc59d234b', LOW['PRODUCT'], LOW['SOURCE'], LOW['WHEEL']),
    'B': (PRIOR/'install/PRODUCT_RUN_BINDING.json', '6fee57dff92aed9270259368c3139118f016ae6f',
          'e800667077a6c390dbc1f49aa46ba9a01b153de5', 'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e',
          'a866444b62bd03d4588800d930436bd0aa88509aabadf54bc9a16f9777a987c8'),
}
BOXES = {
    'negative_y': {'min':[-.08,-.21,.05], 'max':[.08,-.115,.14]},
    'positive_y': {'min':[-.08,.09,.125], 'max':[-.02,.21,.24]},
}
EXPECTED = {
    'negative_y': (247,193,.8603515573882434,'1b07b5e3fdad3453be0dbeccb5d9444e8a503a371c7f15f76e758f65f7565267',
                   'SCENE',13014,179,(24,184,22735)),
    'positive_y': (151,95,.7602539116605649,'4fcf5c994a2e1198dca61336228e088f7fcca8f3a9ad12fa29fbd4478b18fc15',
                   'BACK',80425,140,(24,381,43755)),
}


def inputs(arm):
    binding_path, register, product, source, wheel = BINDINGS[arm]
    bind = read(binding_path)
    require(binding_path.read_bytes()==git('show',register+':'+binding_path.relative_to(V.parent).as_posix())
            and (bind['preparation_git'],bind['source_sha256'],bind['wheel_sha256'])==(product,source,wheel)
            and len(bind['source_manifest'])==143 and pin(bind['wheel_path'])['sha256']==wheel,'fixed_install_changed')
    fixture = IMAGE_EVIDENCE['inputs']()
    cap_path = LOW['CURVED_ROOT']/'sealed/RAW_INDEX.json'
    index = read(cap_path)
    bundle_path = LOW['CURVED_ROOT']/'sealed/ORIGINAL_RUNTIME.zip'
    bundle = pin(bundle_path)
    require(bundle==index['archive']==read(LOW['CURVED']/'RESULT.json')['raw_archive']['archive'],
            'registered_reference_capture_archive_changed')
    from zipfile import ZipFile
    with ZipFile(bundle_path) as archive:
        cap_pin = CURVED['pinned_member'](LOW['CURVED_ROOT'],archive,index,CAPTURE)
    terminal = pin(IMAGE_EVIDENCE['SLOT']/'TERMINAL_SOURCE.json')
    require(terminal['sha256']==TERMINAL_SHA and terminal['bytes']==9614519 and cap_pin['sha256']==CAPTURE_SHA,
            'registered_foot_capture_or_terminal_changed')
    proof = [*fixture['source_pins'],cap_pin,bundle,pin(cap_path),pin(binding_path),pin(bind['wheel_path']),
             pin(LOW['CURVED']/'RESULT.json'),pin(Path(__file__))]
    fixture['source_pins'] = list({item['path']:item for item in proof}.values())
    cold,warm = (rec['delta'] for rec in fixture['records'][:2])
    plan = []
    for detail in ('full','brief'):
        for side,box in BOXES.items():
            q = OLD['renamed'](fixture['records'][0]['request'],f'offline-{side}-{detail}',image=True,detail=detail)
            OLD['args_of'](q)['query']['region']['world_box_m'] = deepcopy(box)
            plan.append(OLD['case'](q,cold if not plan else warm,fixture['terminal'],None,
                        stage=side,box=True))
    fixture['capture_plan'] = [item['capture'] for item in plan]
    return bind,fixture,plan


def truth_for(fixture, captured):
    reference = read(CAPTURE)
    terminal = fixture['terminal']
    oracle = run_path(str(LOW['ORACLE']))
    meshes = captured['meshes']
    for entry,native,prior in zip(meshes,terminal['objects'],reference['meshes'],strict=True):
        require(entry['object_id']==native['object_id'] and entry['faces']==native['evaluated']['triangles']==prior['faces']
                and entry['vertices']==native['evaluated']['vertices_world_m']==prior['vertices'],
                'current_foot_native_and_previous_capture_differ')
    target,cube = meshes
    result = {}
    for side,box in BOXES.items():
        row = oracle['region_truth'](target['vertices'],target['faces'],cube['vertices'],cube['faces'],
                                   (box['min'],box['max']))
        digest = sha256(json.dumps(row['triangle_ids'],separators=(',',':')).encode()).hexdigest()
        require((row['triangle_count'],row['vertex_count'],row['distance_m'],digest)==EXPECTED[side][:4]
                and row['direction_world']==[0,0,1], 'independent_foot_truth_changed/'+side)
        result[side] = row
    require(result['negative_y']['distance_m']>.82>result['positive_y']['distance_m'],
            'independent_foot_threshold_or_rank_changed')
    return result


def check_catalogue(arm, tools):
    original = read(IMAGE_EVIDENCE['LOW']/'inputs/EVIDENCE_TOOLS_SCHEMA.json')
    prior = next(row for row in original if row['name']=='human_eye_scene_observe')
    expected = prior['description'].replace(
        'with include_image=false also returns the same evidence packet for all response_detail values.',
        'returns a brief when include_image=false or when a single sampled image has a verified '
        'source pixel and local path, including for explicit full.')
    require(expected!=prior['description'],'existing_catalogue_description_anchor_changed')
    if arm=='B':
        prior['description'] = expected
    require(tools==original,'unexpected_actual_foot_catalogue_difference/'+arm)


def check_request(arm,root,number,item,reply,receipt,meter,host,np,truth,cold_frames,fixed_cli):
    capture_path = Path(host['capture_file'])
    capture = read(capture_path)
    side = item['stage']
    producer_path = root/'product_full'/f'call_{number:03d}'/'SERVICE_RESULT.json'
    value = read(producer_path)
    blocks = reply['result']['content']
    body = json.loads(blocks[0]['text'])
    compact = arm=='B' or number>2
    require(compact==('images' in body) and len(blocks)==2 and blocks[1]['type']=='image'
            and ('source_mapping' in body) is not compact, 'unexpected_installed_projection_shape/'+side)
    if compact:
        public = body
    else:
        region = body['facts']['region']
        public = {**body, 'region':{'source_triangle_count':len(region['source_triangle_indices']),
                                   'source_vertex_count':len(region['source_vertex_indices'])}}
    fact = LOW['check_measurement'](capture,public,value,{'wire':truth[side]},side)
    frames,paths = OLD['selected_image_paths'](root,body,value,blocks)
    frame, = frames
    visibility = value['facts']['visibility']
    image = body['images'][0] if compact else {
        **value['frames'][0], 'image_block_index':1, 'sampled_pixel':visibility['sampled_pixel'],
        'local_image_path':Path(frame['png']['path']).as_posix()}
    if compact:
        require(paths==[Path(frame['png']['path']).as_posix()],'compact_path_missing/'+side)
    else:
        require('sampled_pixel' not in body['facts']['visibility']
                and body['frames'][0]['image_sha256']==frame['png']['sha256'],'baseline_full_shape_changed/'+side)
    px,count = CURVED['verify_arrays'](np,frame,visibility,value,image,value['frames'][0],witness_required=True)
    point = visibility['sampled_pixel']
    require((frame['view'],px,count,tuple(point[k] for k in ('row','column','source_triangle_index')))==EXPECTED[side][4:],
            'independent_foot_image_anchor_changed/'+side)
    work = value['work']
    require(work['capture_calls']==1 and work['frame_array_decodes']==0
            and host['resource_count']==(2 if number==1 else 0)
            and meter['raster_actual']==work['raster_attempts']==int(number<=2),
            'offline_preparation_work_changed/'+side)
    if number<=2:
        cold_frames[side] = frame
        require(work['sparse_view_probe_views']==(1 if side=='negative_y' else 6),'current_probe_work_changed/'+side)
    else:
        require(frame==cold_frames[side] and work['frame_reuses']==1 and work['sparse_view_probe_views']==0
                and work['task_query']['result_cache_hit'], 'warm_foot_frame_or_measurement_changed/'+side)
    cli = fixed_cli(reply,require_all=compact)
    require(cli['passed'] and len(cli['stages'])==6 and all(row['original_images_exact'] and row['exact']==compact
            for row in cli['stages']) and (not compact or cli['original_text_bytes']<=10800),
            'foot_fixed_consumer_projection_failed/'+side)
    return {'stage':side,'detail':OLD['args_of'](item['request'])['response_detail'],'projection':'brief' if compact else 'full',
            'wire':OLD['retained_workers']()[1]['bound_wire'](root,item['request'],receipt,meter),
            'producer':pin(producer_path),'capture':pin(capture_path),'measurement':fact,'frame':frame,
            'sampled_pixel':point,'public_sampled_pixel':image['sampled_pixel'] if compact else None,
            'local_image_path':paths[0] if compact else None,'selected_pixels':px,'sampled_source_rows':count,
            'actual_rasters':meter['raster_actual'],'work':work,'cli':cli}


def preflight(arm, root):
    binding,fixture,plan = inputs(arm)
    binding_path = BINDINGS[arm][0]
    root.mkdir(parents=True,exist_ok=False)
    path = sys.path[:]
    sys.path[:0] = [binding['dependency_root'],read(OLD['SEAL']/'SHARED_DEPENDENCY.json')['dependency_root'],
                   str(OLD['PRIOR']/'harness')]
    try:
        from runtime import ProductionStdioClient
    finally:
        sys.path[:] = path
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    cmd = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--arm',arm,'--worker','--output',str(root)]
    started = time.perf_counter_ns()
    held = ProductionStdioClient(cmd,root,root/'mcp',started+120_000_000_000,worker_evidence=root/'mcp_io')
    replies = []
    try:
        info = held.call(OLD['INIT'])['result']['_meta']['human_eye']
        held.call(OLD['NOTIFY'])
        tools = held.call(OLD['LIST'])['result']['tools']
        require(info['source_sha256']==binding['source_sha256'] and info['source_kind']=='installed_distribution',
                'actual_offline_product_identity_mismatch')
        check_catalogue(arm,tools)
        for item in plan:
            reply = held.call(item['request'])
            require('error' not in reply and reply['result']['isError'] is False, 'new_foot_product_request_failed/'+item['stage'])
            replies.append(reply)
        through = time.perf_counter_ns()
    finally:
        close = held.finish()
    closed = time.perf_counter_ns()
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code']==0,'actual_offline_product_close_missing')
    worker = read(root/'REPLAY_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0,
            'new_foot_preflight_acted_outside_sealed_source')
    wire = [r for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
            if (r:=json.loads(line))['method']=='tools/call']
    truth = truth_for(fixture,read(root/'CAPTURE_01.json'))
    np = CURVED['np_module'](binding)
    fixed_cli = run_path(str(OLD['CLI_PATH']))['fixed_cli']
    cold_frames = {}
    requests = [check_request(arm,root,n,*args,np,truth,cold_frames,fixed_cli)
                for n,args in enumerate(zip(plan,replies,held.records[3:],wire,worker['calls'],strict=True),1)]
    result = {'passed':True,'role':'offline_product_foot_qualification','arm':arm,'plan':PLAN,
              'product_git':binding['preparation_git'],'source_sha256':binding['source_sha256'],
              'wheel_sha256':binding['wheel_sha256'],'actual_tools':tools,'requests':requests,
              'actual_MCP_business':len(requests),'actual_rasters':sum(row['actual_rasters'] for row in requests),
              'actual_Blender_starts':0,'actual_models':0,'held_close':pin(root/'mcp/HELD_CLOSE.json'),
              'window_ns':closed-started,'through_last_response_ns':through-started,
              'source_pins':fixture['source_pins']}
    write(root/'SUMMARY.json',result)
    print(root/'SUMMARY.json',flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',required=True,choices=tuple(BINDINGS))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--worker',action='store_true')
    args = parser.parse_args()
    root = (args.output or (RUN/f'product_{args.arm}')).resolve()
    require(root.parent==RUN and root.name.startswith(f'product_{args.arm}'),'new_foot_preflight_root_required')
    if args.worker:
        require(root.is_dir() and not (root/'REPLAY_CLOSE.json').exists(),'current_foot_worker_root_required')
        _,fixture,_ = inputs(args.arm)
        raise SystemExit(OLD['retained_workers']()[0]['worker'](
            root,BINDINGS[args.arm][0],'foot_qualification',False,source=fixture))
    preflight(args.arm,root)
