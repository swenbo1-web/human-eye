"""Qualify sparse source-region selection and sampled evidence over installed stdio."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m4_source_region_curved_view_sample_001').resolve()
M1 = V/'m1_source_region_world_box_001'
M1_RUN = Path('D:/he_m1_source_region_world_box_001')
M1_HEAD = 'eaa26074264451d55201118b6aeb44f4550bedbd'
BASE_GIT = 'e956eedc81058c93b0e60a7e901e28395939d7f1'
BASE_BINDING = M1/'install/PRODUCT_RUN_BINDING.json'
HIST = Path('D:/he_m4_yanyite_bilateral_region_native_001')
HIST_REPORT = V/'m4_yanyite_bilateral_region_native_001/RESULT.json'
HIST_HEAD = '25e82445e1b4385033b2e60fd92f0f54c6178318'
SCENE_PROOF = HIST/'preflight/data/DATA_PREFLIGHT.json'
OLD = run_path(str(M1/'replay.py'))
SHARED_INPUTS = V/'m2_source_region_shared_normalization_001/harness/inputs.py'
VERIFY_GEOMETRY = V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py'
PAIRS = [('N1', 'P1'), ('N2', 'P2'), ('N3', 'P3')]
ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3', 'AN', 'BP')
SELECTION_STAGE = 'source_region_sparse_view_selection'
EXPECTED_LEFT_VOTES = {'SCENE': 0, 'TOP': 2, 'LEFT': 22, 'RIGHT': 0, 'FRONT': 2, 'BACK': 0}
require, read, write, append, pin = (OLD[key] for key in ('require', 'read', 'write', 'append', 'pin'))
case, rename, args_of = (OLD[key] for key in ('case', 'renamed', 'args_of'))
git = OLD['OLD_WIRE']['git']


def source_paths():
    paths = (*OLD['source_paths'](), Path(__file__), M1/'replay.py', M1/'RESULT.json', BASE_BINDING,
             HIST_REPORT, VERIFY_GEOMETRY, SHARED_INPUTS)
    return tuple(dict.fromkeys(Path(path).resolve(strict=True) for path in paths))


def archived_inputs(runtime, report, commit):
    require(report.read_bytes() == git('show', commit + ':' + report.relative_to(V.parent).as_posix()),
            'preceding_qualification_not_its_registered_Git_result')
    record = read(report)
    idx = runtime/'sealed/RAW_INDEX.json'
    index = read(idx)
    archive = runtime/'sealed/ORIGINAL_RUNTIME.zip'
    registered = record.get('raw_evidence_local', record.get('raw_archive'))
    require(index['archive'] == registered == pin(archive)
            and index['member_count'] == record['raw_member_count'] == len(index['members']),
            'preceding_raw_archive_changed')
    pins = [pin(report), pin(idx), pin(archive)]
    return index, archive, pins


def pinned_member(runtime, archive, index, path):
    path = Path(path).resolve(strict=True)
    key = path.relative_to(runtime.resolve()).as_posix()
    raw = path.read_bytes()
    expected = index['members'][key]
    require(archive.read(key) == raw and len(raw) == expected['bytes']
            and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'preceding_member_changed/' + key)
    return {'path': str(path), **expected}


def sealed_inputs(controls=False):
    fixture = OLD['sealed_inputs']()
    idx, bundle, pins = archived_inputs(HIST, HIST_REPORT, HIST_HEAD)
    with ZipFile(bundle) as archive:
        member = pinned_member(HIST, archive, idx, SCENE_PROOF)
        proof = read(member['path'])
        require(proof['passed'] is True and proof['actual_new_models'] == proof['actual_new_Blender'] == 0,
                'independent_Yanyite_views_unavailable')
        pins.append(member)
        expected = {side: proof['product_views'][side]['views'] for side in ('left', 'right')}
        for side, views in expected.items():
            for view in ('SCENE', 'LEFT') if side == 'left' else ('SCENE',):
                for artifact in ('PNG', 'NPZ'):
                    item = views[view][artifact]
                    saved = pinned_member(HIST, archive, idx, item['path'])
                    require(saved == item, 'independent_reference_frame_unbound')
                    pins.append(saved)
    idx, bundle, m1pins = archived_inputs(M1_RUN, M1/'RESULT.json', M1_HEAD)
    with ZipFile(bundle) as archive:
        guide = M1_RUN/'controls/BP/SUMMARY.json'
        m1pins.append(pinned_member(M1_RUN, archive, idx, guide))
        prior = read(guide)
        require(prior['binding']['preparation_git'] == BASE_GIT and prior['passed'], 'preceding_world_box_image_gate_failed')
        for index, side in ((0, 'left'), (2, 'right')):
            frame, = prior['product_requests'][index]['frames']
            require(frame['view'] == 'SCENE', 'preceding_world_box_frame_drift')
            same_capture = {key: frame[field] for key, field in (('PNG', 'png'), ('NPZ', 'array'))}
            expected[side]['SCENE_same_capture'] = same_capture
            for part in same_capture.values():
                saved = pinned_member(M1_RUN, archive, idx, part['path'])
                require(saved == part, 'preceding_source_frame_unbound')
                m1pins.append(saved)
    fixture.update(view_expectations=expected, source_pins=[*fixture['source_pins'], *pins, *m1pins])
    if controls:
        origins = run_path(str(SHARED_INPUTS))
        fixture['holdouts'] = {name: origins['sealed_inputs'](name)
                              for name in ('paired_image', 'holdout', 'rectangle', 'defaults')}
        for item in fixture['holdouts'].values():
            fixture['source_pins'].extend(item['source_pins'])
    fixture['source_pins'] = list({item['path']: item for item in fixture['source_pins']}.values())
    return fixture


def requests(fixture, controls):
    if not controls:
        l, r = fixture['calls']
        cold, warm = fixture['deltas']
        a, b = fixture['producers']
        terminal = fixture['terminal']
        l_box, r_box = (OLD['box_for'](request, box) for request, box in zip((l, r), fixture['boxes'], strict=True))
        r_ref = rename(r, 'warm-right-ref', image=True)
        query = args_of(r_ref)['query']
        query.pop('region')
        query['region_ref'] = b['region_ref']
        return [case(rename(l_box, 'cold-left-box', image=True), cold, terminal, a, stage='left'),
                case(rename(r_box, 'cold-right-box', image=True), warm, terminal, b, stage='right'),
                case(rename(l, 'warm-left-indices', image=True), warm, terminal, a, stage='left_warm'),
                case(r_ref, warm, terminal, b, stage='right_warm')]

    result = []
    upper_lower = fixture['holdouts']['paired_image']
    for index, side in enumerate(('upper', 'lower')):
        original = upper_lower['frames'] if index == 0 else upper_lower['lower_image_frames']
        planned = case(rename(upper_lower['calls'][index], side, image=True), upper_lower['deltas'][index],
                       upper_lower['terminal'], upper_lower['producers'][index], stage=side)
        result.append({**planned, 'original_frames': original})
    for name in ('holdout', 'rectangle'):
        original = fixture['holdouts'][name]
        planned = case(rename(original['calls'][0], name, image=True), original['deltas'][0], original['terminal'],
                       original['producer'], stage=name)
        result.append({**planned, 'original_frames': original['frames']})
    cold, warm = fixture['deltas']
    l, _ = fixture['calls']
    left, _ = fixture['producers']
    result.append(case(rename(l, 'known-no-image', image=False), cold, fixture['terminal'], left, stage='no_image'))
    changed = deepcopy(warm)
    changed['capture']['capture_state']['revision'] += 1
    changed['capture']['revision'] += ':curved-sampling-hidden-control'
    display = changed['capture']['display_snapshot']
    obj = next(row for row in display['objects'] if row['host_id'] == left['region_ref']['host_id'])
    obj.update(visible_get=False, hide_get=True)
    display.pop('sha256')
    display['sha256'] = hashlib.sha256(json.dumps(display, sort_keys=True, separators=(',', ':'),
                                                ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    stale = rename(l, 'stale-hidden-ref', image=True)
    query = args_of(stale)['query']
    query.pop('region')
    query['region_ref'] = left['region_ref']
    result.append(case(stale, changed, fixture['terminal'], left, stage='stale',
                       error='source_region_ref_capture_generation_changed'))
    result.append(case(rename(l, 'hidden-recovery', image=True), changed, fixture['terminal'], left, stage='new_generation'))
    default = fixture['holdouts']['defaults']
    full, delta = (default['capture_plan'][i][0] for i in (0, 1))
    require(all(full['capture']['capture_state'][k] == delta['capture']['capture_state'][k]
                for k in ('instance_id', 'epoch')), 'ordinary_control_resources_unbound')
    result.append(case(rename(default['calls'][1], 'ordinary-observation', image=False), {**delta, 'resources': full['resources']},
                       default['capture_plan'][1][2], None, stage='ordinary'))
    return result


def run_worker(root, binding, controls):
    fixture = sealed_inputs(controls=controls)
    planned = requests(fixture, controls)
    source = {**fixture, 'capture_plan': [item['capture'] for item in planned]}
    return OLD['retained_workers']()[0]['worker'](root, binding, 'curved_view', False, source=source)


def np_module(binding):
    sys.path.insert(0, binding['dependency_root'])
    try:
        import numpy as np
    finally:
        sys.path.pop(0)
    return np


def key_for_object(value):
    match, = [row for row in value['binding']['objects']
              if row['host_id'] == value['region_ref']['host_id'] and row['instance_id'] == value['region_ref']['instance_id']]
    return match['object_index']


def verify_arrays(np, raw_frame, visibility, value, public, frame, *, witness_required):
    image_index = public['image_block_index']
    require(image_index == 1 and all(public[field] == frame[field] for field in (
        'image_ref', 'frame_identity', 'image_sha256', 'host_binding_sha256', 'display_identity', 'image_scope_identity')),
            'published_image_not_linked_to_the_validated_frame')
    require(visibility['frame_identity'] == frame['frame_identity'] and visibility['image_ref'] == frame['image_ref']
            and visibility['image_scope'] == frame['image_scope'] == value['binding']['image_scope'],
            'visibility_not_bound_to_current_frame_or_scope')
    owner_idx = key_for_object(value)
    with np.load(raw_frame['array']['path'], allow_pickle=False) as arrays:
        for field in ('owner_schema', 'owner_mapping_identity', 'triangle_id_scope', 'display_identity', 'image_scope_identity'):
            require(arrays[field].item() == frame[field], 'npz_frame_metadata_changed/' + field)
        require(arrays['display_object_mask'].tolist() == value['binding']['image_scope']['participation_mask'],
                'npz_display_mask_not_bound')
        offsets = arrays['face_patch_offsets']
        offset = int(offsets[owner_idx])
        selected_rows = np.asarray(value['region_ref']['source_triangle_indices'], dtype=np.int32)
        owner = arrays['owners']
        triangle = arrays['triangle_ids']
        mask = (owner == owner_idx) & np.isin(triangle, selected_rows + offset)
        actual_rows = (np.unique(triangle[mask])-offset).tolist()
        pixels = int(np.count_nonzero(mask))
        require(pixels == visibility['selected_surface_pixels'] and actual_rows == visibility['visible_source_triangle_indices'],
                'actual_npz_source_membership_changed')
        if witness_required:
            require(visibility['complete_witness'] is None and 'complete_surface_visibility' in visibility['unknown']
                    and visibility['status'] == 'observed_samples' and actual_rows,
                    'sampled_pixel_falsely_claimed_complete_visibility')
            require(public.get('local_image_path') is not None and public.get('sampled_pixel') == visibility.get('sampled_pixel'),
                    'actual_public_pixel_not_authored_with_local_path')
            point = public['sampled_pixel']
            require(type(point) is dict and set(point) == {'row', 'column', 'source_triangle_index'}
                    and all(type(v) is int for v in point.values()), 'invalid_actual_sample_pixel_shape')
            r, c, src = (point[key] for key in ('row', 'column', 'source_triangle_index'))
            require(0 <= r < owner.shape[0] and 0 <= c < owner.shape[1] and mask[r, c]
                    and triangle[r,c]-offset == src, 'public_pixel_not_owned_by_selected_source')
            require(r * owner.shape[1] + c == int(np.argmax(mask)), 'sample_pixel_not_first_owned_cell')
        else:
            require('sampled_pixel' not in public, 'unverified_frame_published_a_pixel')
    return pixels, len(actual_rows)


def compare_independent_frame(np, actual, reference):
    require(actual['png']['sha256'] == reference['PNG']['sha256'], 'independent_unmodified_PNG_changed')
    # The separately acquired LEFT oracle came from another host instance.
    # Verify live bindings above, then compare all other array contents here.
    separate = {'display_identity', 'image_scope_identity'}
    with np.load(actual['array']['path'], allow_pickle=False) as candidate, \
         np.load(reference['NPZ']['path'], allow_pickle=False) as original:
        require(set(candidate.files) == set(original.files), 'independent_NPZ_roster_changed')
        for key in set(candidate.files)-separate:
            a, b = candidate[key], original[key]
            require(a.dtype == b.dtype and np.array_equal(a,b,equal_nan=a.dtype.kind=='f'),
                    'independent_original_raster_array_changed/' + key)


def check_slot(root, binding, base, controls, fixture, planned, replies, receipts, ledger):
    np = np_module(binding)
    fixed_cli = run_path(str(OLD['CLI_PATH']))['fixed_cli']
    bound_wire = OLD['retained_workers']()[1]['bound_wire']
    verify_geometry = OLD['retain'](VERIFY_GEOMETRY, ('verify_geometry',))['verify_geometry']
    out = []
    for index, (item, reply, receipt, meter, actual) in enumerate(zip(planned,replies,receipts,ledger['wire'],ledger['captures'],strict=True), 1):
        stage, request = item['stage'], item['request']
        delta, _, terminal = item['capture']
        cap = read(root/f'CAPTURE_{index:02d}.json')
        verify_geometry(cap, terminal)
        require(actual['resource_count'] == len(delta['resources']) and actual['capture_state'] == cap['capture_state']
                == delta['capture']['capture_state'] and cap['display_snapshot'] == delta['capture']['display_snapshot'],
                'formal_capture_state_or_source_changed')
        body = json.loads(reply['result']['content'][0]['text'])
        producer_path = root/'product_full'/f'call_{index:03d}'/'SERVICE_RESULT.json'
        row = {'stage': stage, 'wire': bound_wire(root,request,receipt,meter), 'capture_resources': actual['resource_count']}
        if item['error']:
            OLD['reject_body'](body,item['error'])
            require(not producer_path.exists() and meter['raster_actual'] == 0, 'stale_ref_constructed_a_frame')
            out.append({**row, 'error': item['error'], 'raster': 0})
            continue
        value = read(producer_path)
        work = value['work']
        probe_views = work.get('sparse_view_probe_views', 0)
        probe = value['stages'].get(SELECTION_STAGE)
        frames, paths = OLD['selected_image_paths'](root, body, value, reply['result']['content'])
        raster = meter['raster_actual']
        row.update(visible_pixels=0, sampled_source_rows=0, frames=frames, local_image_paths=paths,
                   probe_views=probe_views, probe=probe, raster=raster, frame_reuses=work.get('frame_reuses', 0),
                   evidence=pin(producer_path), cli=fixed_cli(reply,require_all=(stage!='ordinary')))
        if item['expected'] is None:
            require(stage == 'ordinary' and not probe and not probe_views and not raster and not frames,
                    'ordinary_call_entered_curved_view_branch')
            out.append(row)
            continue
        OLD['assert_region'](value,item['expected'],body,stage)
        require(work['capture_calls'] == 1 and value['read_only'] is True and value['execution_authority'] is False,
                'observation_not_exactly_one_current_read')
        visibility = value['facts']['visibility']
        row.update(ref=value['region_ref'], measurement=value['task_result']['facts']['surface_proximity'],
            capture_state=value['binding']['capture_state'], service_ns=OLD['work_interval'](value,'service_total'),
            capture_ns=OLD['work_interval'](value,'host_capture'), generation_work=value['generation_work'],
            stage_ns={k:v['elapsed_ns'] for k,v in value['stages'].items() if isinstance(v,dict) and 'elapsed_ns' in v})
        needs = stage not in ('no_image','new_generation','rectangle')
        warm = stage.endswith('_warm')
        if base or not needs or warm:
            require(not probe and not probe_views, 'unexpected_sparse_diagnostics_on_compatibility_or_warm_path')
        else:
            require(probe and probe_views == len(probe['votes']) and 0 < probe['elapsed_ns']
                    == probe['closed_ns']-probe['started_ns'], 'actual_sparse_selection_stage_unbound')
            if stage == 'left':
                require(probe['votes'] == EXPECTED_LEFT_VOTES and probe['chosen_view'] == 'LEFT', 'actual_left_sparse_votes_disagree')
            else:
                require(probe_views == 1 and probe['votes']['SCENE'] > 0 and probe['chosen_view'] == 'SCENE',
                        'existing_SCENE_positive_view_was_replaced_or_reprobed')
        if stage == 'no_image':
            require(not raster and not frames, 'no_image_observation_changed')
        else:
            require(len(frames) == 1 and raster == (0 if warm else len(item.get('original_frames', [None]))),
                    'cold_or_warm_actual_raster_denominator_changed')
            public, = body['images']
            row['sampled_pixel'] = public.get('sampled_pixel')
            pixels, source_rows = verify_arrays(np,frames[0],visibility,value,public,value['frames'][0],
                                                witness_required=not base and needs)
            row.update(visible_pixels=pixels,sampled_source_rows=source_rows)
            if stage == 'new_generation':
                require(pixels == 0 and paths == [None] and visibility['reason'] == 'selected_region_not_displayed',
                        'hidden_object_yielded_a_pixel_or_local_path')
            elif controls:
                originals = item['original_frames']
                actual_frames = value.get('constructed_frames', value['frames']) if not warm else value['frames']
                for old_frame, actual_frame in zip(originals,actual_frames,strict=True):
                    require(old_frame['view_name'] == actual_frame['view_name']
                            and old_frame['png']['sha256'] == actual_frame['image_sha256']
                            and old_frame['arrays']['sha256'] == actual_frame['arrays_sha256'],
                            'historical_compatibility_frame_changed/' + stage)
                if stage == 'rectangle':
                    require(visibility['complete_witness'] and paths[0], 'original_rectangle_witness_or_image_changed')
            else:
                side = stage.split('_')[0]
                chosen = 'LEFT' if not base and side == 'left' else 'SCENE'
                expected = fixture['view_expectations'][side][chosen]
                require(frames[0]['view'] == chosen and pixels == expected['selected_pixels']
                        and source_rows == expected['sampled_source_rows'], 'bilateral_pixels_or_view_disagree')
                if chosen == 'LEFT':
                    compare_independent_frame(np,frames[0],expected)
                else:
                    same = fixture['view_expectations'][side]['SCENE_same_capture']
                    require(all(frames[0][a]['sha256'] == same[b]['sha256'] for a,b in (('png','PNG'),('array','NPZ'))),
                            'bilateral_SCENE_bytes_changed')
                require(bool(paths[0]) is bool(pixels), 'actual_bilateral_local_path_availability_changed')
        out.append(row)
    if not controls:
        require([r['capture_resources'] for r in out] == [2,0,0,0], 'warm_replay_sent_new_host_resources')
        for cold, warm in ((out[0], out[2]), (out[1], out[3])):
            require(cold['frames'] == warm['frames'] and cold['ref'] == warm['ref']
                    and cold['measurement'] == warm['measurement'] and cold['sampled_pixel'] == warm['sampled_pixel']
                    and warm['frame_reuses'] == 1, 'source_selection_alias_did_not_reuse_the_same_pixel_and_PNG')
    return out


def run_slot(root, binding_path, controls):
    binding = read(binding_path)
    base = binding['preparation_git'] == BASE_GIT
    require(len(binding['source_manifest']) == 143 and root.is_relative_to(RUN), 'fixed_isolated_install_required')
    root.mkdir(parents=True,exist_ok=False)
    fixture = sealed_inputs(controls=controls)
    planned = requests(fixture,controls)
    deps = [binding['dependency_root'],read(OLD['SEAL']/'SHARED_DEPENDENCY.json')['dependency_root'],str(OLD['PRIOR']/'harness')]
    sys.path[:0] = deps
    try:
        from runtime import ProductionStdioClient
    finally:
        del sys.path[:len(deps)]
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    command = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker',str(root),'--binding',str(binding_path)]
    if controls:
        command.append('--controls')
    started = time.perf_counter_ns()
    client = ProductionStdioClient(command,root,root/'mcp',started+120_000_000_000,worker_evidence=root/'mcp_io')
    replies = []
    try:
        identity = client.call(OLD['INIT'])['result']['_meta']['human_eye']
        client.call(OLD['NOTIFY'])
        catalogue = client.call(OLD['LIST'])['result']['tools']
        require(identity['source_sha256'] == binding['source_sha256'] and identity['source_kind'] == 'installed_distribution',
                'wrong_actual_installed_production_identity')
        OLD['catalogue_has_only_world_box_change'](catalogue)
        for item in planned:
            response = client.call(item['request'])
            require('error' not in response and response['result']['isError'] is bool(item['error']),
                    'unexpected_actual_product_response/' + item['stage'] + '/' + str(response['result']['content'][0]['text'])[:250])
            replies.append(response)
        last = time.perf_counter_ns()
    finally:
        close = client.finish()
        clks = time.perf_counter_ns()
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code'] == 0, 'actual_installed_mcp_not_closed_cleanly')
    details = read(root/'REPLAY_CLOSE.json')
    require(details['old_sources_unchanged'] and details['actual_Blender_starts'] == details['actual_models'] == 0,
            'replay_changed_originals_or_entered_live_host')
    wire = [row for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
            if (row := json.loads(line))['method'] == 'tools/call']
    checked = check_slot(root,binding,base,controls,fixture,planned,replies,client.records[3:],
                         {'wire':wire, 'captures':details['calls']})
    result = {'passed':True,'label':root.name,'binding':binding['source_sha256'],'source_pins':fixture['source_pins'],
              'actual_Blender':0,'actual_models':0,'held_close':pin(root/'mcp/HELD_CLOSE.json'),
              'window_ns':clks-started,'through_last_response_ns':last-started,'requests':checked}
    write(root/'SUMMARY.json',result)
    print('Passed',root.name,len(checked),'actual MCP calls',flush=True)
    return result


def group(baseline, candidate, preflight, name):
    require(read(baseline)['preparation_git'] == BASE_GIT, 'baseline_not_the_frozen_world_box_install')
    if candidate is not None:
        require(read(candidate)['preparation_git'] != BASE_GIT, 'candidate_identity_required')
    if preflight:
        roots = [('base',baseline), ('product',candidate)] if candidate else [('base',baseline)]
        for label,binding in roots:
            run_slot(RUN/'preflight'/name/(label+'_main'),binding,False)
            run_slot(RUN/'preflight'/name/(label+'_compatibility'),binding,True)
        return
    require(candidate is not None, 'missing_fixed_candidate_install')
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    journal.open('x').close()
    arms = {}
    for label in ORDER:
        controls = label in ('AN','BP')
        path = RUN/('controls' if controls else 'arms')/label
        append(journal,{'event':'start','label':label,'perf_ns':time.perf_counter_ns()})
        try:
            arms[label] = run_slot(path,baseline if label.startswith(('N','A')) else candidate,controls)
        except BaseException as error:
            append(journal,{'event':'failed','label':label,'type':type(error).__name__,'message':str(error),'perf_ns':time.perf_counter_ns()})
            raise
        append(journal,{'event':'closed','label':label,'summary':pin(path/'SUMMARY.json'),'perf_ns':time.perf_counter_ns()})
    pairs = {}
    for a,b in PAIRS:
        old,new = arms[a], arms[b]
        rows = []
        for prev,now in zip(old['requests'],new['requests'],strict=True):
            require(prev['ref'] == now['ref'] and prev['measurement'] == now['measurement']
                    and prev['capture_state'] == now['capture_state'], 'A_B_selected_measurement_binding_changed')
            rows.append({'stage':prev['stage'],'probe_ns':now['stage_ns'].get(SELECTION_STAGE,0),
                         'service_ns':[prev['service_ns'],now['service_ns']],
                         'capture_ns':[prev['capture_ns'],now['capture_ns']]})
        pairs[f'{a}/{b}'] = {'rows':rows,'window_ns':[old['window_ns'],new['window_ns']]}
    positive = [r['probe']['elapsed_ns'] for r in arms['BP']['requests'] if r['probe'] is not None]
    medians = {side:median(q['rows'][n]['probe_ns'] for q in pairs.values()) for n,side in enumerate(('left','right'))}
    passes = medians['left'] <= 80_000_000 and medians['right'] <= 25_000_000 and all(t<=25_000_000 for t in positive)
    report = {'passed':passes,'arms':arms,'pairs':pairs,'measured_order':ORDER[:6],
              'selection_median_ns':medians,'SCENE_positive_control_ns':positive,
              'actual_Blender':0,'actual_models':0,'actual_mcp_slots':len(arms),
              'actual_mcp_requests':sum(len(a['requests']) for a in arms.values()),
              'actual_rasters':sum(r['raster'] for a in arms.values() for r in a['requests']),
              'historical_originals_unchanged':True,'real_model_use_untested':True}
    write(RUN/'REPLAY_SCORE.json',report)
    require(passes,'actual_sparse_view_selection_budget_exceeded')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_flags_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--preflight-name',default='installed')
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--binding',type=Path)
    parser.add_argument('--controls',action='store_true')
    args = parser.parse_args()
    if args.worker:
        require(args.binding is not None and args.worker.is_relative_to(RUN), 'registered_worker_required')
        raise SystemExit(run_worker(args.worker.resolve(strict=True),args.binding.resolve(strict=True),args.controls))
    require(args.baseline is not None and (args.preflight or args.candidate is not None)
            and Path(args.preflight_name).name == args.preflight_name, 'fixed_replay_binding_and_root_required')
    group(args.baseline.resolve(strict=True),args.candidate.resolve(strict=True) if args.candidate else None,
          args.preflight,args.preflight_name)
