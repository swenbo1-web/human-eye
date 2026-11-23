"""Replay the signed-off bilateral scene through the installed production stdio endpoints."""

import argparse
import ast
import base64
from copy import deepcopy
from hashlib import file_digest, sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m1_source_region_world_box_001').resolve()
BASE_GIT = '4104add44251b03a1eafc5af69502aa2575b632c'
INPUTS = HERE/'inputs.py'
OLD = V/'m2_source_region_shared_normalization_001/harness/replay.py'
WIRE = V/'m4_region_task_global_first_frame_001/harness/replay.py'
FORMAL = V/'m4_yanyite_bilateral_region_native_001'
PAIRS = [('N1','P1'), ('N2','P2'), ('N3','P3')]
ORDER = ('N1','P1','P2','N2','N3','P3','AN','BP')
CLI_PATH = V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'
PRIOR = V/'m4_dense_sweep_integrated_native_pilot_001'
SEAL = V/'m5_harness_recovery_001'
CATALOGUE = V/'m4_dense_sweep_integrated_native_startup_001/inputs/EVIDENCE_TOOLS_SCHEMA.json'
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
CAPTURE = {'command': 'capture', 'params': {}}
OLD_WIRE = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
require, read, append, pin = (OLD_WIRE[k] for k in ('require','read','append','pin'))
INIT = {'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
    'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'source-region-world-box-replay', 'version': '1'}}}
NOTIFY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}


def write(path, data):
    OLD_WIRE['write'](Path(path), data)


def digest(raw):
    return {'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}


def retain(path, names, extra=None):
    """Load only inherited wire helpers, without reusing another batch's labels or roots."""
    doc = ast.parse(path.read_bytes(), filename=str(path))
    nodes = [item for item in doc.body if isinstance(item, ast.FunctionDef) and item.name in names]
    require({item.name for item in nodes} == set(names), 'retained_wire_helper_changed')
    ns = {**globals(), **(extra or {})}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return {n: ns[n] for n in names}


def input_module():
    stack = sys.path[:]
    try:
        return run_path(str(INPUTS))
    finally:
        sys.path[:] = stack


def source_paths():
    graph = input_module()
    return (*graph['source_paths'](), Path(__file__), OLD, WIRE, Path(OLD_WIRE['__file__']),
            CLI_PATH, CATALOGUE, SEAL/'SHARED_DEPENDENCY.json',
            PRIOR/'harness/mcp_entry.py', PRIOR/'harness/runtime.py', PRIOR/'harness/common.py',
            PRIOR/'harness/budget.py', PRIOR/'harness/admission.py',
            V/'m1_region_task_first_packet_consumption_holdout_recovery_001/harness/runtime.py',
            V/'m1_region_task_first_packet_consumption_holdout_recovery_001/harness/mcp_entry.py',
            V/'m4_live_source_region_task_003/harness/mcp_entry.py',
            V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
            V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
            V/'m4_cross_scale_live_qualification_001/checks/delivery.py')


def sealed_inputs():
    return input_module()['load_bilateral']()


def box_for(request, box):
    new = deepcopy(request)
    region = new['params']['arguments']['query']['region']
    region['world_box_m'] = deepcopy(box)
    del region['source_triangle_indices']
    return new


def args_of(request):
    return request['params']['arguments']


def case(request, delta, terminal, expected, *, stage, error=None, box=False):
    return {'request': request, 'capture': (delta, CAPTURE, terminal), 'expected': expected,
            'stage': stage, 'error': error, 'box': box}


def renamed(request, label, *, image=None, detail=None):
    new = deepcopy(request)
    new['id'] = label
    arguments = args_of(new)
    if image is not None:
        arguments['include_image'] = image
    if detail is not None:
        arguments['response_detail'] = detail
    return new


def replay_plan(fixture, is_candidate, controls=False):
    base_left, base_right = fixture['calls']
    left, right = fixture['producers']
    cold, warm = fixture['deltas']
    terminal = fixture['terminal']
    box_left, box_right = [box_for(r, b) for r,b in zip(fixture['calls'], fixture['boxes'], strict=True)]
    selected_left, selected_right = (box_left,box_right) if is_candidate else (base_left,base_right)
    if not controls:
        return [case(selected_left, cold, terminal, left, stage='left', box=is_candidate),
                case(selected_right, warm, terminal, right, stage='right', box=is_candidate)]

    changed = deepcopy(warm)
    changed['capture']['capture_state']['revision'] += 1
    changed['capture']['revision'] += ':world-box-new-generation-control'
    stale = renamed(base_right, 'stale-right-ref')
    query = args_of(stale)['query']
    del query['region']
    query['region_ref'] = right['region_ref']
    return [
        case(renamed(base_left, 'left-image-index', image=True), cold, terminal, left, stage='left_image'),
        case(renamed(selected_left, 'left-image-equivalent-alias', image=True), warm, terminal, left,
             stage='left_image_alias', box=is_candidate),
        case(renamed(selected_right, 'right-image-by-region', image=True), warm, terminal, right,
             stage='right_image', box=is_candidate),
        case(renamed(base_right, 'right-image-explicit-full', image=True, detail='full'), warm, terminal, right,
             stage='right_image_alias'),
        case(stale, changed, terminal, right, stage='stale', error='source_region_ref_capture_generation_changed'),
        case(renamed(selected_right, 'right-current-generation'), changed, terminal, right, stage='new_generation', box=is_candidate),
    ]


def add_original_controls(fixture, plan):
    load_previous = input_module()['load_previous']
    past = load_previous('dual')
    default = load_previous('defaults')
    fixture = {**fixture, 'source_pins': [*fixture['source_pins'], *past['source_pins'], *default['source_pins']]}
    for n, (request, delta, producer) in enumerate(zip(past['calls'], past['deltas'], past['producers'], strict=True)):
        plan.append(case(renamed(request, f'original-other-region-{n+1}'), delta, past['terminal'], producer,
                         stage=f'old_region_{n+1}'))
    # The historical ordinary whole-scene request uses the small registered default
    # fixture. Its original delta is warm, so attach the matching original resources.
    full, delta = (default['capture_plan'][i][0] for i in (0,1))
    require(all(full['capture']['capture_state'][k]==delta['capture']['capture_state'][k] for k in ('instance_id','epoch')),
            'ordinary_control_does_not_share_original_full_resources')
    ordinary = renamed(default['calls'][1], 'original-ordinary-no-image', image=False)
    plan.append(case(ordinary, {**delta,'resources':full['resources']}, default['capture_plan'][1][2], None, stage='ordinary'))
    return fixture


def retained_workers():
    import ctypes
    from ctypes import wintypes

    helpers = retain(WIRE, ('bound_wire','peak_memory'), {'ctypes': ctypes, 'wintypes': wintypes})
    return retain(OLD, ('worker','frame_receipts'), {
        'retained': lambda: helpers,
        'capture_plan': lambda source, _: source['capture_plan'],
    }), helpers


def actual_fixture(fixture, candidate, controls):
    planned = replay_plan(fixture, candidate, controls)
    if controls:
        fixture = add_original_controls(fixture, planned)
    return {**fixture, 'capture_plan': [row['capture'] for row in planned]}, planned


def run_worker(root, binding_path, controls):
    binding = read(binding_path)
    fixture, _ = actual_fixture(sealed_inputs(), binding['preparation_git'] != BASE_GIT, controls)
    worker = retained_workers()[0]['worker']
    return worker(root, binding_path, 'bilateral', False, source=fixture)


def catalogue_has_only_world_box_change(actual):
    baseline = read(CATALOGUE)
    require(len(actual) == len(baseline), 'actual_tool_count_changed')
    adjusted = deepcopy(actual)
    observed, = [row for row in adjusted if row['name'] == 'human_eye_scene_observe']
    original, = [row for row in baseline if row['name'] == 'human_eye_scene_observe']
    require('world_box_m' in observed['description'] and observed['description'] != original['description'],
            'world_box_not_described_in_actual_tools_list')
    observed['description'] = original['description']
    new = observed['inputSchema']['properties']['query']['properties']['region']
    before = original['inputSchema']['properties']['query']['properties']['region']
    require(new['required'] == ['object'] and set(new['properties']) == set(before['properties']) | {'world_box_m'},
            'world_box_shape_not_visible_in_actual_schema')
    box = new['properties'].pop('world_box_m')
    expect = {'source_triangle_indices','world_box_m'}
    one = new.pop('oneOf')
    require(len(one) == 2 and {key for branch in one for key in branch['required']} == expect,
            'two_selector_forms_not_exclusive_in_actual_schema')
    require(box['type'] == 'object' and set(box['required']) == {'min','max'}
            and box['additionalProperties'] is False
            and all(box['properties'][k]['type'] == 'array' and box['properties'][k]['minItems'] ==
                    box['properties'][k]['maxItems'] == 3 and box['properties'][k]['items']['type'] == 'number'
                    for k in ('min','max')), 'actual_closed_box_dimensions_not_fixed')
    new['required'] = before['required']
    new['description'] = before['description']
    require(adjusted == baseline, 'actual_tool_directory_differs_outside_the_new_observe_input')


def reject_body(text, expected):
    require(text.get('error') == expected and text.get('execution_status') == 'not_executed'
            and text.get('executed') is False and text.get('host_mutation_started') is False
            and text.get('connector_state_write_attempted') is False, 'unexpected_stale_reason_or_mutation')


def work_interval(record, field):
    interval = record['stages'][field]
    require(interval['closed_ns']-interval['started_ns']==interval['elapsed_ns'] >= 0,
            'actual_stage_clock_did_not_balance/'+field)
    return interval['elapsed_ns']


def assert_region(producer, historical, body, stage):
    ref = producer['region_ref']
    if stage == 'new_generation':
        wanted = historical['region_ref']
        require(ref['region_id'] != wanted['region_id'] and ref['capture_generation']['revision'] ==
                wanted['capture_generation']['revision']+1 and ref['source_triangle_indices'] == wanted['source_triangle_indices'],
                'new_generation_box_or_explicit_selection_reused_stale_region')
    else:
        require(ref == historical['region_ref'], 'historical_order_or_exact_region_ref_changed/'+stage)
    expected = historical['task_result']
    result = producer['task_result']
    require(producer['facts']['region'] == historical['facts']['region']
            and producer['source_mapping'] == historical['source_mapping']
            and result['source_mapping'] == expected['source_mapping']
            and result['reference'] == expected['reference']
            and result['measurement_scope'] == expected['measurement_scope']
            and result['facts'] == expected['facts']
            and body['region_ref'] == ref and body['task_result']['facts'] == expected['facts'],
            'original_source_mapping_measurement_or_public_facts_changed/'+stage)


def selected_image_paths(root, body, producer, content):
    frames = producer['frames']
    originals = [base64.b64decode(row['data'], validate=True) for row in content if row['type']=='image']
    require(originals == [Path(f['image_path']).read_bytes() for f in frames], 'same_request_PNG_delivery_changed')
    rows = []
    for f, png in zip(frames, originals, strict=True):
        paths = [Path(f[k]).resolve(strict=True) for k in ('image_path','arrays_path')]
        proof = [pin(path) for path in paths]
        require(all(path.is_relative_to(root) for path in paths) and
                [p['sha256'] for p in proof] == [f['image_sha256'],f['arrays_sha256']],
                'replay_image_or_arrays_not_bound_to_current_root')
        rows.append({'ref':f['image_ref'],'identity':f['frame_identity'],'view':f['view_name'],
                     'png':proof[0],'array':proof[1]})
    if originals and 'images' in body:
        paths = [x.get('local_image_path') for x in body['images']]
        for local, f, png in zip(paths, frames, originals, strict=True):
            if local is not None:
                local = Path(local).resolve(strict=True)
                require(local == Path(f['image_path']).resolve() and local.read_bytes()==png,
                        'brief_source_image_path_is_not_its_delivered_original')
        return rows, paths
    return rows, []


def stable_frame(image):
    return [(x['ref'], x['identity'], x['view'], x['png']['sha256'], x['array']['sha256']) for x in image]


def run_slot(root, binding_path, controls):
    binding = read(binding_path)
    base = binding['preparation_git']==BASE_GIT
    require(len(binding['source_manifest']) == 143 and root.is_relative_to(RUN), 'fixed_isolated_install_and_output_required')
    root.mkdir(parents=True,exist_ok=False)
    fixture, planned = actual_fixture(sealed_inputs(), not base, controls)
    stack = sys.path[:]
    sys.path[:0] = [binding['dependency_root'],read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root'],str(PRIOR/'harness')]
    try:
        from runtime import ProductionStdioClient
    finally:
        sys.path[:] = stack
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    command = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',str(root),'--binding',str(binding_path)]
    if controls:
        command.append('--controls')
    started = time.perf_counter_ns()
    held = ProductionStdioClient(command,root,root/'mcp',started+120_000_000_000,worker_evidence=root/'mcp_io')
    replies = []
    try:
        identity = held.call(INIT)['result']['_meta']['human_eye']
        held.call(NOTIFY)
        tools = held.call(LIST)['result']['tools']
        require(identity['source_sha256']==binding['source_sha256'] and identity['source_kind']=='installed_distribution',
                'actual_installed_production_worker_identity_changed')
        if base:
            require(tools == read(CATALOGUE),'historical_baseline_tools_directory_changed')
        else:
            catalogue_has_only_world_box_change(tools)
        for item in planned:
            reply = held.call(item['request'])
            require('error' not in reply and reply['result']['isError'] is bool(item['error']),
                    'actual_replay_request_failed/'+item['stage']+'/' + str(reply['result']['content'][0]['text'])[:180])
            replies.append(reply)
        last = time.perf_counter_ns()
    finally:
        close = held.finish()
        ended = time.perf_counter_ns()
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code']==0,'actual_installed_replay_EOF_or_close_missing')
    worker = read(root/'REPLAY_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0
            and len(worker['calls'])==len(planned), 'real_replay_took_extra_capture_or_changed_historical_source')
    wire_log = [v for row in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
                if (v:=json.loads(row))['method']=='tools/call']
    fixed_cli = run_path(str(CLI_PATH))['fixed_cli']
    bound_wire = retained_workers()[1]['bound_wire']
    verifier = retain(V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py', ('verify_geometry',))['verify_geometry']
    checks = []
    for n, (stage, reply, receipt, message, cap) in enumerate(zip(planned,replies,held.records[3:],wire_log,worker['calls'],strict=True),1):
        request, (delta, _, terminal) = stage['request'], stage['capture']
        body = json.loads(reply['result']['content'][0]['text'])
        transport = bound_wire(root,request,receipt,message)
        actual = read(root/f'CAPTURE_{n:02d}.json')
        verifier(actual, terminal)
        require(cap['resource_count']==len(delta['resources']) and cap['capture_state']==actual['capture_state']==delta['capture']['capture_state']
                and actual['display_snapshot']==delta['capture']['display_snapshot'], 'actual_replay_capture_binding_changed')
        producer_path = root/'product_full'/f'call_{n:03d}'/'SERVICE_RESULT.json'
        row = {'stage':stage['stage'],'request':request['id'],'wire':transport,'connection_capture_resources':cap['resource_count'],
               'text_bytes': len(reply['result']['content'][0]['text'].encode('utf8'))}
        if stage['error']:
            reject_body(body, stage['error'])
            require(not producer_path.exists() and message['raster_actual']==0 and len(reply['result']['content'])==1,
                    'stale_reference_published_an_image_or_producer')
            row['error']=stage['error']
            checks.append(row)
            continue
        producer = read(producer_path)
        work = producer['work']
        cli = fixed_cli(reply,require_all=(args_of(request).get('response_detail') != 'full' and stage['stage']!='ordinary'))
        row.update(producer=pin(producer_path),cli=cli,raster_attempts=message['raster_actual'])
        if stage['expected'] is not None:
            assert_region(producer, stage['expected'], body, stage['stage'])
            selection_count = work.get('world_box_selection_calls',0)
            if stage['box'] and stage['stage']!='left_image_alias':
                require(selection_count==1,'fresh_candidate_box_not_timed')
            elif not stage['box']:
                require(selection_count==0 and 'world_box_selection' not in producer['stages'], 'explicit_rows_entered_box_selection')
            row.update(ref=producer['region_ref'], capture_state=producer['binding']['capture_state'],
                capture_ns=work_interval(producer,'host_capture'),service_ns=work_interval(producer,'service_total'),
                selection_count=selection_count, selection_ns=work_interval(producer,'world_box_selection') if selection_count else None,
                normalizations=work['geometry_normalization_calls'], prepared=work['prepare_calls'],
                shared_normalization=work['geometry_normalization_shared_hit'], frame_reuses=work['frame_reuses'],
                pixels=producer['facts']['visibility']['selected_surface_pixels'], source_triangle_count=len(producer['region_ref']['source_triangle_indices']),
                source_vertex_count=len(producer['facts']['region']['source_vertex_indices']),
                measurement=producer['task_result']['facts']['surface_proximity'],
                read_only=producer['read_only'], execution_authority=producer['execution_authority'])
            require(work['capture_calls']==1 and row['read_only'] is True and row['execution_authority'] is False,
                    'one_current_read_capture_required')
        else:
            require(producer['result_kind']=='active_observation' and producer['frames']==[]
                    and not work.get('world_box_selection_calls') and message['raster_actual']==0,
                    'ordinary_no_image_observation_changed')
        frames, local = selected_image_paths(root, body, producer, reply['result']['content'])
        row.update(frames=frames, local_image_paths=local)
        require(not args_of(request)['include_image'] or frames,'expected_product_image_missing')
        checks.append(row)
    if controls:
        for start in (0,2):
            current,warm = checks[start:start+2]
            require(current['ref']==warm['ref'] and current['raster_attempts']==1 and warm['raster_attempts']==0
                    and warm['frame_reuses']==1 and warm['prepared']==0 and current['prepared']==1
                    and stable_frame(current['frames']) == stable_frame(warm['frames']),
                    'index_and_box_alias_did_not_share_current_preparation_and_original_image')
        require(checks[0]['pixels']==checks[1]['pixels']==0 and checks[2]['pixels']==checks[3]['pixels']==110809,
                'source_region_same_default_frame_pixel_evidence_changed')
        require(not any(checks[0]['local_image_paths']) and checks[2]['local_image_paths'][0],
                'old_zero_samples_path_or_positive_local_path_semantics_changed')
    else:
        require([v['source_triangle_count'] for v in checks]==[178,155] and [v['source_vertex_count'] for v in checks]==[125,98]
                and [v['normalizations'] for v in checks]==[1,0] and [v['prepared'] for v in checks]==[1,1]
                and all(v['raster_attempts']==0 and not v['frames'] for v in checks)
                and [v['connection_capture_resources'] for v in checks]==[2,0]
                and checks[0]['capture_state']==checks[1]['capture_state'], 'actual_main_bilateral_scope_or_work_changed')
    result = {'passed':True,'label':root.name,'actual_Blender':0,'actual_models':0,
              'binding': {k:binding[k] for k in ('preparation_git','source_sha256','wheel_sha256')},
              'source_pins':fixture['source_pins'],'held_close':pin(root/'mcp/HELD_CLOSE.json'),
              'window_ns':ended-started,'through_last_response_ns':last-started,'product_requests':checks}
    write(root/'SUMMARY.json',result)
    print('Passed',root.name,len(checks),'actual MCP calls',flush=True)
    return result


def frozen_stats(a,b):
    result = []
    for old,new in zip(a['product_requests'],b['product_requests'],strict=True):
        require(old['ref']==new['ref'] and old['measurement']==new['measurement'] and old['capture_state']==new['capture_state'],
                'baseline_candidate_region_ref_or_measurement_differs')
        row = {'region':old['stage'],'selection_ns':new['selection_ns'],'refs_equal':True,'source_triangle_count':old['source_triangle_count']}
        for key in ('capture_ns','service_ns'):
            row[key] = [old[key],new[key]]
        for key in ('TX_bytes','RX_bytes'):
            row[key] = [old['wire'][key],new['wire'][key]]
        result.append(row)
    return result


def group(baseline, candidate, preflight):
    require(read(baseline)['preparation_git']==BASE_GIT,'baseline_not_fixed_Git_install')
    if preflight:
        run_slot(RUN/'preflight/base_ordinary_v2', baseline, True)
        if candidate is not None:
            require(read(candidate)['preparation_git']!=BASE_GIT,'unique_candidate_for_preflight_required')
            run_slot(RUN/'preflight/world_box_v2', candidate, True)
        return
    require(read(candidate)['preparation_git']!=BASE_GIT,'fixed_unique_candidate_required')
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    journal.open('x').close()
    arms = {}
    for label in ORDER:
        root = RUN/('controls' if label in ('AN','BP') else 'arms')/label
        binding = baseline if label.startswith(('N','A')) else candidate
        started = time.perf_counter_ns()
        append(journal,{'event':'start','label':label,'perf_ns':started})
        try:
            arms[label] = run_slot(root,binding,label in ('AN','BP'))
        except BaseException as err:
            append(journal,{'event':'failed','label':label,'type':type(err).__name__,'message':str(err),'perf_ns':time.perf_counter_ns()})
            raise
        append(journal,{'event':'closed','label':label,'summary':pin(root/'SUMMARY.json'),'perf_ns':time.perf_counter_ns()})
    pairs = {f'{a}/{b}':frozen_stats(arms[a],arms[b]) for a,b in PAIRS}
    for n in (0,1,2,3):
        a,b = (arms[x]['product_requests'][n] for x in ('AN','BP'))
        require(stable_frame(a['frames'])==stable_frame(b['frames']) and a['measurement']==b['measurement']
                and a['ref']==b['ref'],'baseline_candidate_real_cold_or_cached_frame_changed')
    medians = {name:median(pair[n]['selection_ns'] for pair in pairs.values()) for n,name in enumerate(('left','right'))}
    passed = all(ns <= 50_000_000 for ns in medians.values())
    write(RUN/'REPLAY_SCORE.json',{'passed':passed,'arms':arms,'pairs':pairs,'measured_order':ORDER[:6],
          'selection_median_ns':medians,'selection_limit_ns':50_000_000,
          'actual_Blender':0,'actual_models':0, 'actual_mcp_slots':len(arms),
          'actual_mcp_requests':sum(len(a['product_requests']) for a in arms.values()),
          'actual_rasters':sum(r.get('raster_attempts',0) for a in arms.values() for r in a['product_requests']),
          'historic_originals_unchanged':True,'real_model_use_untested':True})
    require(passed,'world_box_current_selection_budget_exceeded')


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==PYTHON_SHA,
            'fixed_isolated_interpreter_flags_required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--binding',type=Path)
    parser.add_argument('--controls',action='store_true')
    option=parser.parse_args()
    if option.worker:
        require(option.binding is not None and option.worker.is_relative_to(RUN),'fixed_worker_roots_required')
        raise SystemExit(run_worker(option.worker.resolve(strict=True),option.binding.resolve(strict=True),option.controls))
    require(option.baseline is not None and (option.preflight or option.candidate is not None),'frozen_candidate_binding_required')
    group(option.baseline.resolve(strict=True),None if option.candidate is None else option.candidate.resolve(strict=True),option.preflight)
