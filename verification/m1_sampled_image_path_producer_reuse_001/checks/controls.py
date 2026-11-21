"""Compare actual installed MCP replies against retained producer evidence."""

import argparse
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace


V = Path(__file__).resolve().parents[2]
PRIOR = V / 'm1_source_region_sampled_image_path_001'
BASE = PRIOR / 'install/PRODUCT_RUN_BINDING.json'
BASE_SOURCE = 'a8ddc3b672c6b32c3a69711ecbc847d9761315ccb6239e447d7006df2c35b982'
OVERLAY = ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'path':str(path.resolve()),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def save(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())


def build_cases(shared):
    prior = run_path(str(PRIOR/'checks/controls.py'))
    inherited, cases, pins = prior['load_plan'](shared)
    require(len(cases)==49,'prior_control_roster_changed')
    sample = cases['actual_sampled_brief']

    for case in cases.values():
        case['expected_A_path'] = int(case['expected_new'])
        case['expected_B_path'] = int(case['expected_new'])
        case['origin'] = 'prior_49'
    complete = cases['historical_complete_witness_path']
    complete['expected_A_path'] = complete['expected_B_path'] = 1
    for name, reason in (
        ('valid_sparse_single_pixel_stays_sampling','prior synthetic reply reported one pixel over an unchanged retained 26,212-sample record'),
        ('wrong_recorded_png_byte_count','prior synthetic reply changed the private declaration to 4016 while the retained record and validated PNG have 4015'),
    ):
        cases[name]['expected_B_path'] = 0
        cases[name]['difference_reason'] = reason

    def add(name, *, source=sample, mutation=None, authored=None, state=None, expect=(0,0), difference=None):
        copy = {**source,'request':deepcopy(source['request']),'producer':deepcopy(source['producer']),
                'state':state,'expected_A_path':expect[0],'expected_B_path':expect[1],
                'actual_original':False,'origin':'new'}
        if mutation is not None:
            mutation(copy['producer'])
        if authored is not None:
            copy['authored'] = authored
        if difference is not None:
            copy['difference_reason'] = difference
        cases[name] = copy

    add('separately_authored_sparse_one_pixel',source=cases['valid_sparse_single_pixel_stays_sampling'],
        authored='reply',expect=(1,1),difference='synthetic coverage fixture with the identical sample authored and retained separately; no new frame')
    add('reply_swaps_frame_array_sha_without_moving_directory',expect=(1,0),
        mutation=lambda p:p['frames'][0].update(arrays_sha256='0'*64),
        difference='reply changed the companion arrays SHA, retained canonical frame unchanged')
    add('reply_swaps_plausible_visibility_count_without_moving_directory',expect=(1,0),
        mutation=lambda p:p['facts']['visibility'].update(selected_surface_pixels=26211),
        difference='plausible but unauthored 26,211-pixel reply differs from the retained 26,212')
    add('reply_changes_parent_camera_policy_with_same_digest',expect=(1,0),
        mutation=lambda p:p['binding']['camera_policy'].update(scope='wrong-camera-scope'),
        difference='unchanged binding digest field does not override retained parent camera policy')
    add('reply_changes_region_object_name_with_same_instance',expect=(1,0),
        mutation=lambda p:p['facts']['region'].update(object_name='OtherObject'),
        difference='name differs from retained region despite the unchanged host and instance fields')
    add('read_origin_overlay_excluded_from_producer_comparison',expect=(1,1),
        mutation=lambda p:p['binding'].update(runtime_source_sha256='b'*64,source_check_scope='test_overlay'),
        difference='runtime binding annotations are attached after the retained producer record')
    add('retained_observation_missing_but_directory_exists',state='missing_observation',expect=(1,0),
        difference='registered renderer directory without an observation cannot author the path')
    add('retained_region_missing_from_current_selection',state='missing_region')
    add('retained_selection_actually_evicted',state='evicted')
    add('current_capture_generation_advanced',state='advanced')
    add('read_lock_held_in_other_thread',state='locked')
    pins.extend((pin(PRIOR/'checks/controls.py'),pin(Path(__file__))))
    return prior, inherited, cases, pins


def retained_source(case):
    original = case['producer'] if case.get('authored')=='reply' else case['fixture'].producer
    snapshot = deepcopy(original)
    for name in OVERLAY:
        snapshot['binding'].pop(name,None)
    for name in ('task_result','session_id','request_trace'):
        snapshot.pop(name,None)
    if case['paths'] is not None:
        # The one authorized cloned-generation control changes the fixture's
        # canonical root at authorship; all other reply modifications stay separate.
        directory = case['paths'][1]
        for frame in snapshot['frames']:
            for field in ('image_path','arrays_path'):
                frame[field] = str(directory/Path(frame[field]).name)
    elif snapshot['frames']:
        directory = Path(snapshot['frames'][0]['image_path']).parent
    else:
        directory = None
    return snapshot, directory


def archive_sparse_samples():
    """Identify genuine sparse history separately from the current synthetic fixture."""
    import numpy as np

    root = Path('D:/he_m4_m5_source_region_001')
    namespace = V/'m4_m5_source_region_001'
    index_path = namespace/'RUNTIME_ARCHIVE.json'
    index = {row['relative']:row for row in read(index_path)['files']}
    sources = []
    for call in (1,2):
        path = root/f'sessions/qualification_R0/product_full/call_{call:03d}/SERVICE_RESULT.json'
        producer = read(path)
        frame, = producer['frames']
        png, npz = (Path(frame[field]) for field in ('image_path','arrays_path'))
        captured = []
        for item in (path,png,npz):
            record = index[item.relative_to(root).as_posix()]
            receipt = pin(item)
            require((receipt['sha256'],receipt['bytes'])==(record['sha256'],record['bytes'])
                    and receipt['sha256']==pin(namespace/record['copy'])['sha256'], 'legacy_sparse_archive_changed')
            captured.append(receipt)
        ref = producer['region_ref']
        owner, = [row['object_index'] for row in producer['binding']['objects'] if row['host_id']==ref['host_id']]
        with np.load(npz,allow_pickle=False) as arrays:
            selected = np.asarray(ref['source_triangle_indices'])+int(arrays['face_patch_offsets'][owner])
            samples = int(np.count_nonzero((arrays['owners']==owner)&np.isin(arrays['triangle_ids'],selected)))
        reported = producer['facts']['visibility']['selected_surface_pixels']
        require(samples==reported==13 and 'image_scope' not in producer['binding']
                and 'selected_object_participates' not in producer['facts']['visibility'], 'legacy_sparse_metadata_unexpected')
        sources.append({'call':call,'authored_and_decoded_pixels':samples,'eligible_current_source_contract':False,
                        'why_ineligible':'archived producer predates captured display scope and selected-object participation',
                        'files':captured})
    return {'index':pin(index_path),'historical_sparse_frames':sources,'new_synthetic_scope':'separate retained and returned one-pixel sample metadata; existing PNG bytes retained; no claim of a newly rasterized one-pixel frame'}


def worker(binding_path, output, shared):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind']=='installed_distribution' and identity['source_sha256']==binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),'wrong_isolated_runtime')
    output.mkdir(parents=True)
    prior, inherited, cases, pins = build_cases(shared)

    class ReplayService:
        _source_region_sample_directory = getattr(LiveSpatialService,'_source_region_sample_directory',None)
        _source_region_sample_path = getattr(LiveSpatialService,'_source_region_sample_path',None)
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self, case):
            self.case = case
            self.state_path = case['fixture'].state if case['paths'] is None else case['paths'][0]
            self._read_context = ReadContext()
            self.closed, self.observations, self.deliveries, self.budgets = False, 0, [], []
            self.retained, directory = retained_source(case)
            ref = self.retained.get('region_ref')
            current = self.retained['binding']
            if not ref or not case['trusted_owner']:
                return
            reading = self._read_context
            original_selection = {'scope':'captured-replay'}
            reading.activate(current,'source_region',original_selection)
            prepared = SimpleNamespace(binding=deepcopy(current),region_ref=deepcopy(ref),
                images=SimpleNamespace(output_directory=directory) if directory is not None else None,
                region_facts=deepcopy(self.retained['facts']['region']),
                observation=None if case.get('state')=='missing_observation' else self.retained)
            regions = {} if case.get('state')=='missing_region' else {ref['region_id']:prepared}
            reading.prepared('source_regions',lambda:{'regions':regions,'aliases':{}})
            if case.get('state')=='evicted':
                for index in range(8):
                    reading.activate(current,'source_region',{'different_selection':index})
                reading.activate(current,'source_region',original_selection)
                require(reading.current_prepared('source_regions') is None,'original_cached_selection_not_evicted')
            elif case.get('state')=='advanced':
                reading.activate({'capture_state':{**current['capture_state'],
                    'revision':current['capture_state']['revision']+1}},'source_region',original_selection)
                require(reading.current_prepared('source_regions') is None,'original_capture_generation_not_invalidated')

        def observe(self, _session, **kwargs):
            args = self.case['request']['params']['arguments']
            require(kwargs.get('query')==args['query'] and kwargs.get('include_image',True)==args.get('include_image',True),
                    'actual_replayed_incoming_request_changed')
            self.observations += 1
            return deepcopy(self.case['producer'])

        def record_event(self, event, **data):
            if event in ('source_region_mcp_content','active_observation_mcp_content'):
                self.deliveries.append(data['image_delivery'])

        def _check_request_budget(self, phase, *, publication=False):
            require((phase,publication) in (('before_task_publication',False),('before_stdio_write',True)),
                    'unexpected_MCP_publication_stage')
            self.budgets.append([phase,publication])

        def close(self):
            self.closed = True

    result = {}
    for name, case in cases.items():
        fixture, request = case['fixture'], case['request']
        service = ReplayService(case)
        raw = (json.dumps(request,ensure_ascii=False)+'\n').encode()
        outgoing = StringIO(newline='\r\n')
        acquired, release = Event(), Event()

        def hold_other_thread_lock():
            with service._read_context.lock:
                acquired.set()
                release.wait(5)

        holder = Thread(target=hold_other_thread_lock) if case.get('state')=='locked' else None
        if holder:
            holder.start()
        try:
            if holder:
                require(acquired.wait(5),'external_lock_contention_not_established')
            mcp.run_stdio_mcp_server(service,input_stream=StringIO(raw.decode()),output_stream=outgoing)
        finally:
            if holder:
                release.set()
                holder.join(5)
                require(not holder.is_alive(),'external_lock_not_released')
        wire = outgoing.getvalue().encode()
        reply = json.loads(wire)
        require(service.closed and reply['id']==request['id'] and reply['jsonrpc']=='2.0', 'wire_id_or_EOF_changed/'+name)
        is_error = 'error' in reply or reply['result']['isError']
        if case['expected_error'] is not None:
            require(is_error is case['expected_error'],'control_did_not_reach_expected_error/'+name)
        require(service.observations==(0 if name=='request_validation_rejects_empty_region' else 1), 'unexpected_observation_count/'+name)
        tx, rx = output/(name+'_TX.bin'), output/(name+'_RX.bin')
        tx.write_bytes(raw)
        rx.write_bytes(wire)
        historical = None
        if case['actual_original']:
            archived = fixture.original['result']
            actual = reply['result']
            stored = json.loads(actual['content'][0]['text'])
            for image in stored.get('images',[]):
                image.pop('local_image_path',None)
            historical = (reply['id']==fixture.original['id'] and actual['isError']==archived['isError']
                and stored==json.loads(archived['content'][0]['text']) and actual['content'][1:]==archived['content'][1:])
            require(historical,'actual_historical_fields_or_original_PNG_changed/'+name)
        path_fields = prior['image_paths'](reply['result']) if 'result' in reply else []
        visibility = service.retained.get('facts',{}).get('visibility',{})
        frames = service.retained['frames']
        result[name] = {'origin':case['origin'],'expected_A_path':case['expected_A_path'],'expected_B_path':case['expected_B_path'],
            'difference_reason':case.get('difference_reason'),'actual_EOF':service.closed,'observations':service.observations,
            'original_body_and_PNG_equal_except_path':historical,'error':is_error,'budget_phases':service.budgets,
            'retained_path':frames[0].get('image_path') if frames else None,
            'retained_sampling_pixels':visibility.get('selected_surface_pixels'),
            'retained_declared_PNG_bytes':frames[0].get('PNG_bytes') if frames else None,
            'images':inherited['media'](reply['result']) if 'result' in reply else [],
            'MCP_TX':pin(tx),'MCP_RX':pin(rx),'path_fields':path_fields,
            'serializer_receipt':service.deliveries[0] if service.deliveries else None}
    save(output.parent/(output.name.upper()+'.json'),{'binding':pin(binding_path),'source_sha256':identity['source_sha256'],
        'original_pins':pins,'cases':result,'sparse_archive_check':archive_sparse_samples()})


def without_path(packet):
    result = packet['result']
    body = json.loads(result['content'][0]['text'])
    for row in body.get('images',[]):
        row.pop('local_image_path',None)
    result['content'][0]['text'] = json.dumps(body,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    return packet


def compare(a, b):
    require(a['source_sha256']==BASE_SOURCE and b['source_sha256']!=BASE_SOURCE,
            'fixed_actual_baseline_and_candidate_identities_required')
    require(a['original_pins']==b['original_pins'] and a['cases'].keys()==b['cases'].keys()
            and a['sparse_archive_check']==b['sparse_archive_check'],'frozen_inputs_changed')
    results, failures = {}, []
    for name, old in a['cases'].items():
        new = b['cases'][name]
        before, after = (Path(row['MCP_RX']['path']).read_bytes() for row in (old,new))
        byte_equal = before==after
        want_a, want_b = old['expected_A_path'], old['expected_B_path']
        exact = byte_equal if want_a==want_b else without_path(json.loads(before))==without_path(json.loads(after))
        path_alignment = all(str(Path(path))==record['retained_path'] for record in (old,new) for path in record['path_fields'])
        passed = (exact and path_alignment and len(old['path_fields'])==want_a and len(new['path_fields'])==want_b
                  and old['images']==new['images'] and old['error']==new['error']
                  and old['budget_phases']==new['budget_phases'] and old['MCP_TX']['sha256']==new['MCP_TX']['sha256'])
        if not passed:
            failures.append(name)
        results[name] = {'passed':passed,'origin':old['origin'],'byte_identical':byte_equal,'same_PNG_digests':old['images']==new['images'],
            'A_paths':old['path_fields'],'B_paths':new['path_fields'],'difference_reason':old['difference_reason'],
            'expected_path_counts':[want_a,want_b],'actual_path_counts':[len(old['path_fields']),len(new['path_fields'])],
            'A_MCP_RX':old['MCP_RX'],'B_MCP_RX':new['MCP_RX']}
    previous = [row for row in results.values() if row['origin']=='prior_49']
    return {'passed':not failures,'total':len(results),'prior_49_passed':sum(row['passed'] for row in previous),
        'prior_49_byte_equal':sum(row['byte_identical'] for row in previous),'new_controls':len(results)-len(previous),
        'byte_equal_total':sum(row['byte_identical'] for row in results.values()),'failures':failures,'cases':results,
        'sparse_archive_check':a['sparse_archive_check'],'new_blender':0,'new_models':0,'new_rasters':0,
        'scope':'separate replay of each installed product public MCP over immutable live/derived service replies and actual current ReadContext provenance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--shared',type=Path)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--baseline-only',action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'use_pinned_python_I_B')
    if args.worker:
        worker(args.candidate.resolve(strict=True),args.output.resolve(),args.shared.resolve())
        return
    output = args.output.resolve()
    output.mkdir(parents=True)
    for arm, install in (('baseline',BASE),('candidate',args.candidate)):
        subprocess.run([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker','--candidate',str(install.resolve()),
                        '--output',str(output/arm),'--shared',str(output/'shared')],check=True,timeout=100)
        if args.baseline_only:
            return
    result = compare(read(output/'BASELINE.json'),read(output/'CANDIDATE.json'))
    save(output/'CONTROL_REVIEW.json',result)
    print(json.dumps({key:result[key] for key in ('passed','total','prior_49_passed','prior_49_byte_equal','new_controls','byte_equal_total','failures')},ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
