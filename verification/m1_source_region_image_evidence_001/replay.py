"""Qualify full image evidence with the original closed production MCP calls."""

import argparse
import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from types import SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m1_source_region_image_evidence_001').resolve()
HISTORY = Path('D:/he_m4_yanyite_low_bilateral_product_native_001').resolve()
SLOT = HISTORY/'slots/P1'
LOW = V/'m4_yanyite_low_bilateral_product_native_001'
LOW_GIT = '273208f56e7ecbd09e89e8a11da791fd317d389f'
PLAN = '76f952c98ca26a4919e304378d236686bf5042ad:docs/M1_SOURCE_REGION_IMAGE_EVIDENCE_001_PLAN.md'
PREVIOUS = run_path(str(LOW/'product_preflight.py'))
CURVED = PREVIOUS['CURVED_REPLAY']
OLD = PREVIOUS['OLD']
WORLD_INPUTS = run_path(str(OLD['INPUTS']))
BASE_BINDING = PREVIOUS['BINDING']
BASE_GIT = PREVIOUS['PRODUCT']
CANDIDATE_BINDING = HERE/'install/PRODUCT_RUN_BINDING.json'
require, read, write, pin, git = (PREVIOUS[k] for k in ('require','read','write','pin','git'))
args_of, case, renamed = (OLD[k] for k in ('args_of','case','renamed'))
SIDES = ('left','right','left','right','left')


def source_paths():
    return (Path(__file__), LOW/'product_preflight.py', LOW/'inputs/EVIDENCE_TOOLS_SCHEMA.json',
            PREVIOUS['ORACLE'], *CURVED['source_paths']())


def inputs():
    record_path = LOW/'RESULT.json'
    require(record_path.read_bytes()==git('show',LOW_GIT+':'+record_path.relative_to(V.parent).as_posix()),
            'prior_formal_result_not_the_fixed_commit')
    listed = read(record_path)['raw_archive']
    index_path, bundle = HISTORY/'sealed/RAW_INDEX.json', HISTORY/'sealed/ORIGINAL_RUNTIME.zip'
    index = read(index_path)
    require(listed['archive']==index['archive']==pin(bundle)
            and listed['member_count']==index['member_count']==len(index['members'])==999,
            'prior_formal_raw_archive_changed')
    pins = [pin(record_path),pin(index_path),pin(bundle)]
    records, transfers = [], []
    with ZipFile(bundle) as archive:
        def take(path):
            item = CURVED['pinned_member'](HISTORY, archive, index, path)
            pins.append(item)
            return Path(item['path']).read_bytes()

        raw_terminal = take(SLOT/'TERMINAL_SOURCE.json')
        terminal = json.loads(raw_terminal)
        close = json.loads(take(SLOT/'SLOT_RESULT.json'))
        require(close['status'] == 'completed' and close['closure_verification']['passed']
                and close['independent_before_after']['passed']
                and close['terminal_source']['sha256']==sha256(raw_terminal).hexdigest()
                and terminal['source']['asset_sha256']==read(record_path)['asset_sha256'],
                'original_low_slot_not_closed_on_fixed_asset')
        take(SLOT/'mcp/HELD_CLOSE.json')
        native = json.loads(take(SLOT/'native/WIRE/INDEX.json'))
        for position, side in enumerate(SIDES, 2):
            owner = SLOT/'product_calls'/f'call_{position:03d}'
            receipt = json.loads(take(owner/'RECEIPT.json'))
            wire = SLOT/'mcp'/f'rpc_{receipt["index"]:02d}'
            tx, rx = [take(wire/name) for name in ('TX.bin','RX.bin')]
            request, reply = map(json.loads, (tx,rx))
            require(request == json.loads(take(owner/'REQUEST.json')) and
                    reply == json.loads(take(owner/'RESPONSE.json')) and
                    request['id'] == reply['id'] == f'observe-{position}' and
                    receipt['RX_sha256'] == sha256(rx).hexdigest() and not reply['result']['isError'],
                    'original_production_RX_TX_unbound/'+str(position))
            arguments = args_of(request)
            require(arguments['query']['region']['world_box_m'] == PREVIOUS['BOXES'][side] and
                    arguments['response_detail'] == ('full' if position in (2,3) else 'brief') and
                    arguments['include_image'] is (position != 4), 'original_request_shape_changed')
            producer_path = SLOT/'product_full'/f'call_{position:03d}'/'SERVICE_RESULT.json'
            value = json.loads(take(producer_path))
            packet = json.loads(reply['result']['content'][0]['text'])
            require(packet['region_ref'] == value['region_ref'] and
                    packet['task_result']['facts'] == value['task_result']['facts'],
                    'original_packet_not_its_producer')
            frame = None
            if position != 4:
                delivered, = value['frames']
                png, arrays = (Path(delivered[k]) for k in ('image_path','arrays_path'))
                for key,path in (('image_sha256',png),('arrays_sha256',arrays)):
                    require(sha256(take(path)).hexdigest() == delivered[key], 'original_frame_digest_changed')
                frame = {'PNG':pin(png),'NPZ':pin(arrays)}
                OLD['selected_image_paths'](SLOT, packet, value, reply['result']['content'])
            delta, native_receipt = WORLD_INPUTS['recorded_delta'](
                SLOT, f'{position+1:03d}', 2 if position == 2 else 0, native, take)
            require(delta['capture']['capture_state'] == value['binding']['capture_state'],
                    'original_native_capture_unbound_to_same_MCP_producer')
            records.append({'request':request,'reference':value,'wire':pin(wire/'TX.bin'),
                            'reply':reply,'original_frame':frame,'side':side,'delta':delta})
            transfers.append(native_receipt)
    return {'records':records,'terminal':terminal,'native_receipts':transfers,
            'source_pins':list({row['path']:row for row in (*pins,*(pin(p) for p in source_paths()))}.values())}


def replay_plan(fixture, standard):
    records, terminal = fixture['records'],fixture['terminal']
    result = []
    for n,row in enumerate(records[:2] if standard else records, 2):
        confidence = 'full' if standard or n <= 3 else 'brief'
        spec = case(row['request'],row['delta'],terminal,row['reference'],stage=f'original_{n}',
                    box=True)
        result.append({**spec,'side':row['side'],'original_frame':row['original_frame'],'style':confidence,
                       'cold':n <= 3,'fixed_TX':row['wire']})
    if standard:
        return result

    left,right = records[:2]
    warm = fixture['records'][-1]['delta']
    rows,ref = (renamed(row['request'], 'warm-'+name+'-full') for row,name in ((left,'rows'),(right,'ref')))
    regions = (args_of(rows)['query']['region'],args_of(ref)['query'])
    regions[0].pop('world_box_m')
    regions[0]['source_triangle_indices'] = left['reference']['region_ref']['source_triangle_indices']
    regions[1].pop('region')
    regions[1]['region_ref'] = right['reference']['region_ref']
    omitted = renamed(left['request'], 'default-image-full')
    args_of(omitted).pop('include_image')
    default = renamed(right['request'], 'default-image-default-detail')
    args_of(default).pop('response_detail')
    args_of(default).pop('include_image')
    no_image = renamed(left['request'], 'explicit-no-image-full', image=False)
    for q,row,style,has_frame in ((rows,left,'full',True),(ref,right,'full',True),(omitted,left,'full',True),
                                  (default,right,'brief',True),(no_image,left,'brief',False)):
        result.append({**case(q,warm,terminal,row['reference'],stage=q['id']),'side':row['side'],
                       'style':style,'original_frame':row['original_frame'] if has_frame else None,'cold':False})

    changed = deepcopy(warm)
    changed['capture']['capture_state']['revision'] += 1
    changed['capture']['revision'] += ':image-evidence-hidden-gen'
    display = changed['capture']['display_snapshot']
    row = next(row for row in display['objects'] if row['host_id'] == left['reference']['region_ref']['host_id'])
    row.update(visible_get=False, hide_get=True)
    display.pop('sha256')
    display['sha256'] = sha256(json.dumps(display,sort_keys=True,separators=(',',':'),
                                         ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    stale = {**ref,'id':'stale-ref'}
    result.append({**case(stale,changed,terminal,right['reference'],stage='stale',
                          error='source_region_ref_capture_generation_changed'),'side':'right','cold':False})
    hidden = renamed(left['request'], 'current-hidden-full')
    result.append({**case(hidden,changed,terminal,left['reference'],stage='hidden'),
                   'side':'left','style':'full','cold':True,'original_frame':None})
    return result


def installed_worker(root, binding, standard):
    fixture = inputs()
    planned = replay_plan(fixture, standard)
    fixture['capture_plan'] = [item['capture'] for item in planned]
    inherited, _ = OLD['retained_workers']()
    prior = Path(inherited['worker'].__code__.co_filename)
    text = prior.read_text(encoding='utf8')
    patched = ast.parse(text, filename=str(prior))
    worker = next(node for node in patched.body if isinstance(node,ast.FunctionDef) and node.name=='worker')
    selectors = [key for node in ast.walk(worker) if isinstance(node,ast.Call)
                 for key in node.keywords if key.arg=='region_task_evidence']
    require(len(selectors)==1 and isinstance(selectors[0].value,ast.Constant) and selectors[0].value.value is True,
            'inherited_installed_worker_endpoint_anchor_changed')
    selectors[0].value = ast.copy_location(ast.Constant(not standard),selectors[0].value)
    namespace = dict(inherited['worker'].__globals__)
    exec(compile(ast.Module(body=[worker],type_ignores=[]),str(prior),'exec'),namespace)
    return namespace['worker'](root,binding,'image_evidence',False,source=fixture)


def check_measurement(capture, body, value, expected, side, stage):
    fields = ('region_ref','read_only','execution_authority')
    if stage != 'hidden':
        require(all(body[k]==value[k]==expected[k] for k in fields),
                'original_region_or_read_only_contract_changed/'+stage)
    task = value['task_result']
    actual = body['task_result']
    require(value['binding']['capture_state']==task['binding']['capture_state']==capture['capture_state']
            and actual['measurement_scope']==task['measurement_scope']==expected['task_result']['measurement_scope']
            and actual['reference']==task['reference']==expected['task_result']['reference']
            and actual['facts']==task['facts']==expected['task_result']['facts']
            and task['source_mapping']==expected['task_result']['source_mapping']
            and actual['source_mapping']==(
                {'nearest_witness':task['source_mapping']['nearest_witness']}
                if 'images' in body else task['source_mapping']),
            'original_exact_measurement_or_source_mapping_changed/'+stage)
    if stage != 'hidden':
        if 'region' in body:
            PREVIOUS['check_measurement'](capture,body,value,side[1],side[0])
        else:
            require(body['facts']['region']==value['facts']['region']==expected['facts']['region']
                    and body['source_mapping']==value['source_mapping']==expected['source_mapping'],
                    'standard_full_diagnostic_regions_changed/'+stage)
    return actual['facts']['surface_proximity']


def close_score(root,binding,fixture,planned,replies,client,opened,through,closed,standard):
    worker = read(root/'REPLAY_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0,
            'prior_raw_artifacts_changed_or_live_scene_opened')
    wire = [row for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
            if (row:=json.loads(line))['method']=='tools/call']
    np = CURVED['np_module'](binding)
    base = binding['preparation_git']==BASE_GIT
    fixed_cli = run_path(str(OLD['CLI_PATH']))['fixed_cli']
    _,wires = OLD['retained_workers']()
    checks,truth = [],None
    for i,(item,reply,receipt,meter,cap_receipt) in enumerate(
            zip(planned,replies,client.records[3:],wire,worker['calls'],strict=True),1):
        stage,side = item['stage'],item['side']
        proof = wires['bound_wire'](root,item['request'],receipt,meter)
        if 'fixed_TX' in item:
            require(proof['TX_sha256']==item['fixed_TX']['sha256'] and proof['TX_bytes']==item['fixed_TX']['bytes'],
                    'original_exact_MCP_TX_bytes_changed/'+stage)
        body = json.loads(reply['result']['content'][0]['text'])
        cap = read(cap_receipt['capture_file'])
        value_path = root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        if item['error']:
            OLD['reject_body'](body,item['error'])
            require(meter['raster_actual']==0 and not value_path.exists(),'rejected_stale_reference_rasterized')
            checks.append({'stage':stage,'error':item['error'],'wire':proof,'actual_rasters':0})
            continue
        value = read(value_path)
        if truth is None:
            truth = PREVIOUS['source_truth'](fixture['terminal'],cap)
        compact = item['style']=='brief' or (not base and not standard and stage!='hidden')
        require(compact is ('images' in body) and compact is ('source_mapping' not in body),
                'actual_packet_projection_not_expected_for_endpoint/'+stage)
        fact = check_measurement(cap,body,value,item['expected'],(side,truth[side]),stage)
        frames,paths = OLD['selected_image_paths'](root,body,value,reply['result']['content'])
        if item['original_frame']:
            frame, = frames
            CURVED['compare_independent_frame'](np,frame,item['original_frame'])
            require(frame['array']['sha256']==item['original_frame']['NPZ']['sha256']
                    and frame['png']['sha256']==item['original_frame']['PNG']['sha256']
                    and frame['png']['bytes']==(27001 if side=='left' else 56863),
                    'original_same_capture_PNG_or_NPZ_changed/'+stage)
            if compact:
                public = body['images'][0]
                pixels,sampled = CURVED['verify_arrays'](np,frame,value['facts']['visibility'],value,
                                                         public,value['frames'][0],witness_required=True)
                witness = public['sampled_pixel']
                require((pixels,sampled,tuple(witness[k] for k in ('row','column','source_triangle_index')))
                        == PREVIOUS['EXPECTED'][side][5:] and paths==[Path(frame['png']['path']).as_posix()],
                        'exact_published_low_image_pixel_or_path_changed/'+stage)
            else:
                witness = None
                require('sampled_pixel' not in body['facts']['visibility']
                        and body['frames'][0]['image_ref']==frame['ref'],'full_frame_contract_changed')
        else:
            witness = None
            if stage == 'hidden':
                require(value['facts']['visibility']['selected_surface_pixels']==0
                        and not any('sampled_pixel' in r for r in body['frames'])
                        and value['binding']['image_scope']['participation_mask']==[False,False],
                        'hidden_fallback_claimed_pixel_evidence')
            else:
                require(not frames and not value['frames'],'no_image_control_constructed_frame')
        work = value['work']
        require(meter['raster_actual']==work['raster_attempts']==int(item['cold'])
                and work['frame_array_decodes']==0 and work['capture_calls']==1,
                'unexpected_actual_capture_raster_or_array_decode/'+stage)
        if not item['cold'] and item['original_frame']:
            require(work['frame_reuses']==1 and work['task_query']['result_cache_hit']
                    and work['sparse_view_probe_views']==0,'warm_candidate_rendered_or_remeasured/'+stage)
        cli = fixed_cli(reply,require_all=compact)
        if stage in ('original_2','original_3'):
            old_cli = fixed_cli(next(r['reply'] for r in fixture['records'] if r['request']==item['request']),
                                require_all=False)
            require(all(not row['exact'] and row['original_images_exact'] for row in old_cli['stages'])
                    and old_cli['original_text_bytes']==(78920 if side=='left' else 107922)
                    and (cli['original_text_bytes']<=10800 if compact else
                         all(not row['exact'] and row['original_images_exact'] for row in cli['stages'])),
                    'actual_primary_fixed_delivery_threshold_failed')
        else:
            old_cli = None
        checks.append({'stage':stage,'side':side,'style':'brief' if compact else 'full',
                       'wire':proof,'capture':pin(cap_receipt['capture_file']),
                       'service_producer':pin(value_path),'selected_png_npz':frames,'local_paths':paths,
                       'sampled_pixel':witness,'actual_rasters':meter['raster_actual'],
                       'resources':cap_receipt['resource_count'],'actual_work':work,
                       'stages':value['stages'],'fixed_cli':cli,'original_CLI':old_cli,
                       'measurement':fact,'body_bytes':cli['original_text_bytes']})
    return {'passed':True,'actual_models':0,'actual_Blender_starts':0,'requests':checks,
            'endpoint':'standard' if standard else 'evidence','product_git':binding['preparation_git'],
            'actual_mcp_business':len(checks),'actual_rasters':sum(row['actual_rasters'] for row in checks),
            'through_last_response_ns':through-opened,'window_ns':closed-opened,
            'held_close':pin(root/'mcp/HELD_CLOSE.json'),'source_pins':fixture['source_pins']}


def run(root, binding_path, standard):
    fixture = inputs()
    planned = replay_plan(fixture,standard)
    binding = read(binding_path)
    root.mkdir(parents=True,exist_ok=False)
    before = sys.path[:]
    sys.path[:0] = [binding['dependency_root'],read(OLD['SEAL']/'SHARED_DEPENDENCY.json')['dependency_root'],
                   str(OLD['PRIOR']/'harness')]
    try:
        from runtime import ProductionStdioClient
    finally:
        sys.path[:] = before
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    argv = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker','--root',str(root),
            '--binding',str(binding_path)]
    if standard:
        argv.append('--standard')
    opened = time.perf_counter_ns()
    held = ProductionStdioClient(argv,root,root/'mcp',opened+120_000_000_000,worker_evidence=root/'mcp_io')
    replies = []
    try:
        info = held.call(OLD['INIT'])['result']['_meta']['human_eye']
        held.call(OLD['NOTIFY'])
        tools = held.call(OLD['LIST'])['result']['tools']
        require(info['source_kind']=='installed_distribution' and info['source_sha256']==binding['source_sha256'],
                'actual_replay_mcp_installed_identity_changed')
        accepted = read(LOW/'inputs/EVIDENCE_TOOLS_SCHEMA.json')
        old_observe, = (row for row in accepted if row['name']=='human_eye_scene_observe')
        new_observe, = (row for row in tools if row['name']=='human_eye_scene_observe')
        old_description, new_description = old_observe.pop('description'),new_observe.pop('description')
        require(tools==accepted and (not standard or new_description==old_description.split(' In this endpoint,',1)[0]),
                'actual_catalogue_changed_outside_expected_evidence_description')
        for item in planned:
            reply = held.call(item['request'])
            require('error' not in reply and reply['result']['isError'] is bool(item['error']),
                    'unexpected_real_mcp_reply/'+item['stage']+'/'+str(reply['result']['content'][0]['text'])[:250])
            replies.append(reply)
        through = time.perf_counter_ns()
    finally:
        close = held.finish()
        closed = time.perf_counter_ns()
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code']==0,'real_production_stdio_not_reaped')
    summary = close_score(root,binding,fixture,planned,replies,held,opened,through,closed,standard)
    write(root/'SUMMARY.json',summary)
    print(root/'SUMMARY.json',flush=True)
    return summary


def score_closed(root,binding_path,standard):
    """Preflight only: recheck held wire after an earlier scorer raised."""
    require(root.is_relative_to(RUN/'preflight') and not (root/'SUMMARY.json').exists(),
            'preflight_closed_score_path_required')
    binding = read(binding_path)
    start,ended = (read(root/'mcp'/f'{name}.json') for name in ('START','HELD_CLOSE'))
    command = start['command']
    require(Path(command[command.index('--binding')+1]).resolve()==binding_path
            and Path(start['cwd']).resolve()==root and ('--standard' in command) is standard
            and ended['confirmed'] and ended['production_eof_and_exit_verified']
            and ended['process_handle_closed'] and ended['exit_code']==0,
            'original_closed_preflight_incomplete_or_wrong')
    fixture = inputs()
    planned = replay_plan(fixture,standard)
    dirs = sorted((root/'mcp').glob('rpc_*'))
    require(len(dirs)==3+len(planned),'original_preflight_business_denominator_changed')
    actual = [read(folder/'RECEIPT.json') if (folder/'RECEIPT.json').is_file() else None for folder in dirs]
    replies = [read(folder/'RX.bin') for folder in dirs[3:]]
    init = read(dirs[0]/'RX.bin')['result']['_meta']['human_eye']
    require(init['source_kind']=='installed_distribution' and init['source_sha256']==binding['source_sha256'],
            'original_closed_preflight_identity_changed')
    summary = close_score(root,binding,fixture,planned,replies,SimpleNamespace(records=actual),
                          start['started_ns'],actual[-1]['closed_ns'],ended['closed_ns'],standard)
    summary['derived_preflight_score_only'] = True
    write(root/'SUMMARY.json',summary)
    print(root/'SUMMARY.json',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--standard',action='store_true')
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--score-closed',action='store_true')
    args = parser.parse_args()
    output, binding_path = args.root.resolve(),args.binding.resolve(strict=True)
    require(output!=RUN and output.is_relative_to(RUN) and
            binding_path in (BASE_BINDING.resolve(strict=True),CANDIDATE_BINDING.resolve()),
            'registered_isolated_install_and_scope_required')
    if args.worker:
        require(output.is_dir() and not (output/'REPLAY_CLOSE.json').exists(),'worker_root_not_fresh')
        raise SystemExit(installed_worker(output,binding_path,args.standard))
    (score_closed if args.score_closed else run)(output,binding_path,args.standard)
