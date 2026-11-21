"""Replay real and derived controls through two isolated installed MCP servers."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import statistics
import subprocess
import sys
from time import perf_counter_ns


V = Path(__file__).resolve().parents[2]
RETAINED = V/'m1_joint_full_task_tail_001/checks/controls.py'
BASE = V/'m1_joint_full_task_tail_scope_001/install/PRODUCT_RUN_BINDING.json'
DISPLAY = V/'m4_source_region_display_001'
DISPLAY_RUN = Path('D:/he_m4_source_region_display_001')
RANK = 'perf050_source_scope_rank_transfer_recovery_001'
SAMPLE = (RANK, 'P1', 2)
SOURCE = 'a436539e9f5389b9ebaa5ccacc0a4845d53d2429923b4443b15e3f49e2a6e846'
SAMPLE_PNG = '815eed92ff73118535035ce7f9faf4bfbc798cae0f527ad0c3c7ecd624c4546f'


def require(value, label):
    if not value:
        raise ValueError(label)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':str(path), 'bytes':len(raw), 'sha256':digest(raw)}


def save(path, value):
    with path.open('xb') as out:
        out.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())


def image_paths(result):
    body = json.loads(result['content'][0]['text'])
    return [row['local_image_path'] for row in body.get('images', [])
            if isinstance(row, dict) and 'local_image_path' in row]


class CopiedArchiveFixture:
    """Load genuine producer and images from a retained file-by-file archive."""

    def __init__(self, ordinal, *, archive_directory=DISPLAY, run_directory=DISPLAY_RUN):
        archive_path = archive_directory/'RUNTIME_ARCHIVE.json'
        archive = {row['relative']:row for row in read(archive_path)['files']}
        self.pins = [pin(archive_path)]
        self.slot = run_directory/'sessions/state'
        self.state = self.slot/'product_state.json'
        relative = f'sessions/state/product_calls/call_{ordinal:03d}'

        def take(rel):
            record = archive[rel]
            live, archive_file = run_directory/rel, archive_directory/record['copy']
            raw = live.read_bytes()
            require(len(raw) == record['bytes'] and digest(raw) == record['sha256']
                    and raw == archive_file.read_bytes(), 'indexed_original_display_archive_changed/'+rel)
            self.pins.extend((pin(live), pin(archive_file)))
            return raw

        self.request = json.loads(take(relative+'/REQUEST.json'))
        self.original = json.loads(take(relative+'/RESPONSE.json'))
        producer = f'sessions/state/product_full/call_{ordinal:03d}/SERVICE_RESULT.json'
        self.producer = json.loads(take(producer))
        for frame in self.producer['frames']:
            rel = Path(frame['image_path']).relative_to(run_directory).as_posix()
            require(digest(take(rel)) == frame['image_sha256'], 'original_display_frame_sha_changed')


def load_plan(output):
    prior = run_path(str(RETAINED))
    Fixture = prior['Fixture']
    sample, pre_full, pre_nopic, rect_fallback, legacy_complete, target, region_task = (
        Fixture(V, spec) for spec in (SAMPLE, (RANK,'P1',1), (RANK,'P1',3),
            ('m4_source_region_active_view_001','A',1), prior['SOURCE'],
            prior['M09'], prior['REGION_FOUR']))
    hidden, zero = CopiedArchiveFixture(4), CopiedArchiveFixture(2)
    ordinary = CopiedArchiveFixture(1,archive_directory=V/'m4_m5_source_region_001',
                                    run_directory=Path('D:/he_m4_m5_source_region_001'))
    fixtures = (sample, pre_full, pre_nopic, rect_fallback, legacy_complete, ordinary,
                target, region_task, hidden, zero)
    require(ordinary.producer['result_kind'] == 'active_observation'
            and set(ordinary.request['params']['arguments']['query']) == {'mode'}
            and len(ordinary.producer['frames'])==6,'ordinary_fixture_wrong_kind')
    cases = {}

    def add(name, fixture=sample, *, change=None, disclosure=False, actual=False, missing_owner=False,
            paths=None, proof=None, error=None):
        request, value = deepcopy(fixture.request), deepcopy(fixture.producer)
        if change is not None:
            change(request, value)
        cases[name] = {'request':request, 'producer':value, 'fixture':fixture, 'expected_new':disclosure,
            'actual_original':actual,'trusted_owner':not missing_owner, 'paths':paths, 'proof':proof, 'expected_error':error}

    add('actual_sampled_brief', disclosure=True, actual=True)
    add('sampled_without_registered_producer_directory', missing_owner=True)
    add('historical_first_no_image_full', pre_full, actual=True)
    add('historical_no_image_brief', pre_nopic, actual=True)
    add('historical_zero_pixel_display', zero)
    add('historical_hidden_display', hidden)
    add('historical_rectangle_fallback_without_pixels', rect_fallback)
    add('historical_complete_witness_path', legacy_complete)
    add('historical_target_active', target)
    add('historical_region_task', region_task)
    add('historical_non_source_image', ordinary)
    add('sampled_explicit_full', change=lambda q,v:q['params']['arguments'].update(response_detail='full'))
    add('partially_observed_sample', change=lambda q,v:v.update(status='partial', observation_status='evidence_insufficient'))
    add('error_outcome_keeps_original_path_rule', change=lambda q,v:v.update(status='error'),error=True)

    def visibility(name, value, *, disclose=False):
        add(name,change=lambda q,v:v['facts']['visibility'].update(value),disclosure=disclose)

    visibility('misbound_visibility_ref', {'image_ref':'source-region-image:'+'0'*64})
    visibility('misbound_visibility_identity', {'frame_identity':'0'*64})
    visibility('misbound_visibility_view', {'view_name':'LEFT'})
    visibility('misbound_visibility_scope', {'visibility_scope':'foreign_surface'})
    visibility('selected_object_not_participating', {'selected_object_participates':False})
    visibility('zero_pixels_in_sampled_record', {'selected_surface_pixels':0})
    visibility('invalid_boolean_sample_count', {'selected_surface_pixels':True})
    visibility('invalid_sample_count_above_frame', {'selected_surface_pixels':512*512+1})
    visibility('invalid_sample_bounds', {'visible_pixel_bounds':[24, 159, 513, 388]})
    visibility('impossible_count_for_pixel_bounds', {'visible_pixel_bounds':[24,159,25,160]})
    visibility('empty_visible_partition', {'visible_source_triangle_indices':[], 'unseen_source_triangle_indices':[0,1,2,3]})
    visibility('overlap_or_duplicate_source_partition', {'visible_source_triangle_indices':[0,0,1,2,3]})
    visibility('foreign_source_partition', {'visible_source_triangle_indices':[0,1,2,999]})
    visibility('invalid_unseen_partition', {'unseen_source_triangle_indices':[3]})
    visibility('valid_sparse_single_pixel_stays_sampling', {'selected_surface_pixels':1,'visible_pixel_bounds':[24,159,24,159],
               'visible_source_triangle_indices':[0],'unseen_source_triangle_indices':[1,2,3]},disclose=True)

    def frame_case(name, **changes):
        add(name,change=lambda q,v:v['frames'][0].update(changes))

    frame_case('wrong_frame_source_revision', source_revision='blender:'+'0'*64)
    frame_case('wrong_frame_display_identity', display_identity='0'*64)
    frame_case('wrong_frame_candidate_identity', candidate_identity='0'*64)
    frame_case('wrong_frame_scope_identity', image_scope_identity='0'*64)
    # This advisory count is not the verified raw image receipt. Keep the
    # discrepancy as an expanded probe and record the actual delivered count.
    add('wrong_recorded_png_byte_count',change=lambda q,v:v['frames'][0].update(PNG_bytes=4016),
        disclosure=True,proof='expanded probe: private declared count differs; actual 4015 byte PNG and its SHA remain fixed')
    add('wrong_frame_binding',change=lambda q,v:v['frames'][0].update(host_binding_sha256='0'*64),error=True)
    add('wrong_stored_png_digest',change=lambda q,v:v['frames'][0].update(image_sha256='0'*64),error=True)
    add('duplicate_frame_candidate',change=lambda q,v:v['frames'].append(deepcopy(v['frames'][0])),error=True)
    add('wrong_selection_scope',change=lambda q,v:v['facts']['region'].update(source_triangle_indices=[0,1,2]),error=True)
    add('request_validation_rejects_empty_region',change=lambda q,v:q['params']['arguments']['query']['region'].update(
        source_triangle_indices=[]),error=True)

    def same_shape_set(q,v):
        v['view_attempts'] = [{'view_name':'TOP', 'status':'complete', 'constructed':True},
                              {'view_name':'SCENE', 'sample_only':True, 'constructed':True}]
        v['constructed_frames'] = [deepcopy(v['frames'][0])]
        v['facts']['visibility'].update(geometry_status='complete',contrasting_boundary_pixels=0,
                      reason='selected_region_boundary_or_surface_pixels_insufficient')

    add('derived_rectangle_low_contrast_or_occlusion_fallback',change=same_shape_set)
    add('derived_duplicate_constructed_candidate',change=lambda q,v:v.update(constructed_frames=
        [deepcopy(v['frames'][0]),deepcopy(v['frames'][0])]))

    # All adversarial paths are in a fresh control tree. The authoritative
    # producer directory is fixed separately and never follows a frame path.
    # The genuine formal output root remains read-only, including on Windows.
    src = sample.producer['frames'][0]
    source_png, source_arrays = (Path(src[key]) for key in ('image_path','arrays_path'))
    require(digest(source_png.read_bytes()) == SAMPLE_PNG and digest(source_arrays.read_bytes()) == src['arrays_sha256'],
            'canonical_closed_frame_bytes_changed')
    state = output/'PathProof'/'slot_a'/'product_state.json'
    authority = state.with_name(state.name+'.source_region')/source_png.parent.name
    other_generation = authority.with_name('a'*32)
    other_slot = output/'PathProof'/'slot_b'/authority.parent.name/authority.name
    originals = (source_png.name,source_arrays.name)

    def materialize(directory, other=False):
        directory.mkdir(parents=True, exist_ok=True)
        result = (directory/originals[0],directory/originals[1])
        png = Path(legacy_complete.producer['frames'][0]['image_path']) if other else source_png
        result[0].write_bytes(png.read_bytes())
        result[1].write_bytes(source_arrays.read_bytes())
        return result

    normal = materialize(authority)
    sibling = materialize(other_generation)
    foreign = materialize(other_slot)
    wrong_image = materialize(authority.with_name('b'*32),other=True)
    aliases = [path.with_name('002-'+path.name.split('-',1)[1]) for path in normal]
    for alias, real in zip(aliases,normal,strict=True):
        alias.write_bytes(real.read_bytes())
    case_only = tuple(Path(str(path).replace('PathProof','PATHPROOF')) for path in normal)
    require(all(path.is_file() and str(path.resolve(strict=True)) != str(path) and path.resolve(strict=True) == path
                for path in case_only), 'windows_case_alias_control_not_reproducible')

    def path_change(paths):
        return lambda q,v:v['frames'][0].update(image_path=str(paths[0]),arrays_path=str(paths[1]))

    add('cloned_canonical_generation_control',change=path_change(normal),disclosure=True,paths=(state,authority),
        proof='canonical duplicate in isolated control namespace, authorized independently')
    add('same_byte_duplicate_in_other_generation',change=path_change(sibling),paths=(state,authority))
    add('same_byte_duplicate_in_other_slot',change=path_change(foreign),paths=(state,authority))
    add('same_byte_non_generated_filename',change=path_change(aliases),paths=(state,authority))
    add('same_byte_case_alias',change=path_change(case_only),paths=(state,authority))
    add('same_png_with_foreign_generation_npz_path',change=path_change((normal[0],sibling[1])),paths=(state,authority))
    add('different_png_with_same_generated_name',change=path_change(wrong_image),paths=(state,authority),error=True)
    absent = source_png.with_name('unused.png')
    require(not absent.exists(), 'declared_missing_test_file_unexpectedly_exists')
    add('missing_png_preserves_existing_error',change=path_change((absent,source_arrays)),error=True)
    pins = {row['path']:row for fixture in fixtures for row in fixture.pins}
    for path in (source_png,source_arrays):
        row = pin(path)
        pins[row['path']] = row
    return prior, cases, list(pins.values())


def worker(binding_path, output, timing_samples):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind']=='installed_distribution' and identity['source_sha256']==binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),'wrong_isolated_runtime')
    output.mkdir(parents=True)
    prior,cases,pins = load_plan(output)

    class ReplayService:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self, case):
            self.case = case
            fixture = case['fixture']
            self.owner_ref = deepcopy(fixture.producer.get('region_ref'))
            self.owner_binding = fixture.producer['binding'].get('binding_sha256')
            frames = fixture.producer['frames']
            self.state_path = fixture.state if case['paths'] is None else case['paths'][0]
            self.directory = (Path(frames[0]['image_path']).parent if frames else None) if case['paths'] is None else case['paths'][1]
            self.closed, self.observations, self.lookups, self.deliveries, self.budgets = False, 0, [], [], []

        def observe(self, session, **kwargs):
            args = self.case['request']['params']['arguments']
            require(kwargs.get('query') == args['query'] and kwargs.get('include_image',True) == args.get('include_image',True),
                    'actual_replayed_incoming_request_changed')
            self.observations += 1
            return deepcopy(self.case['producer'])

        def _source_region_sample_directory(self, ref, binding_sha256):
            self.lookups.append((ref,binding_sha256))
            if self.case['trusted_owner'] and ref == self.owner_ref and binding_sha256 == self.owner_binding:
                return self.directory
            return None

        def record_event(self, event, **data):
            if event in ('source_region_mcp_content','active_observation_mcp_content'):
                self.deliveries.append(data['image_delivery'])

        def _check_request_budget(self, phase, *, publication=False):
            require((phase,publication) in (('before_task_publication',False),('before_stdio_write',True)),
                    'unexpected_MCP_publication_stage')
            self.budgets.append(phase)

        def close(self):
            self.closed = True

    def invoke(service, request):
        raw = (json.dumps(request,ensure_ascii=False)+'\n').encode()
        output_stream = StringIO(newline='\r\n')
        started = perf_counter_ns()
        mcp.run_stdio_mcp_server(service,input_stream=StringIO(raw.decode()),output_stream=output_stream)
        elapsed = perf_counter_ns()-started
        wire = output_stream.getvalue().encode()
        body = json.loads(wire)
        require(service.closed and body['id']==request['id'] and body['jsonrpc']=='2.0', 'bad_response_or_EOF')
        return raw, wire, elapsed

    result = {}
    for name, case in cases.items():
        fixture, request = case['fixture'], case['request']
        service = ReplayService(case)
        request_raw, wire, elapsed = invoke(service,request)
        reply = json.loads(wire)
        require('result' in reply or case['expected_error'], 'unexpected_rpc_failure/'+name)
        is_error = 'error' in reply or reply['result']['isError']
        if case['expected_error'] is not None:
            require(is_error is case['expected_error'],'control_did_not_reach_expected_error/'+name)
        require(service.observations == (0 if name=='request_validation_rejects_empty_region' else 1),
                'actual_observation_count_mismatch/'+name)
        tx, rx = output/(name+'_TX.bin'), output/(name+'_RX.bin')
        tx.write_bytes(request_raw)
        rx.write_bytes(wire)
        historical_content_value_equal = False
        if case['actual_original']:
            original = fixture.original['result']
            current = reply['result']
            historical_content_value_equal = (reply['id']==fixture.original['id'] and current['isError']==original['isError']
                and json.loads(current['content'][0]['text'])==json.loads(original['content'][0]['text'])
                and current['content'][1:]==original['content'][1:])
        item = {'expected_new':case['expected_new'],'actual_original':case['actual_original'],
            'original_raw_wire_identical': hasattr(fixture,'original_inner') and wire==fixture.original_inner,
            'original_body_and_blocks_value_equal':historical_content_value_equal,
            'derived_qualification_proof':case['proof'],'error':is_error,'MCP_TX':pin(tx),'MCP_RX':pin(rx),
            'actual_EOF':service.closed,'observations':service.observations,'budget_phases':service.budgets,
            'service_directory_lookup_count':len(service.lookups),'stdio_elapsed_ns':elapsed,
            'actual_cold_serializer_audit':service.deliveries[0] if service.deliveries else None}
        if 'result' in reply:
            item.update(images=prior['media'](reply['result']),path_fields=image_paths(reply['result']))
        result[name] = item

    timings = []
    for iteration in range(6+timing_samples):
        case = cases['actual_sampled_brief']
        service = ReplayService(case)
        _, wire, elapsed = invoke(service,case['request'])
        require(digest(wire)==result['actual_sampled_brief']['MCP_RX']['sha256'] and len(service.deliveries)==1,
                'warm_actual_reply_or_accounting_changed')
        if iteration>=6:
            audit=service.deliveries[0]
            frame, = audit['frames']
            timings.append({'stdio_dispatch_ns':elapsed,'serializer_ns':audit['elapsed_ns'],
                'PNG_read_ns':frame['read_ns'],'PNG_validate_ns':frame['validate_ns'],'PNG_base64_ns':frame['base64_ns']})
    sys.stdout.buffer.write(json.dumps({'binding':pin(binding_path),'source_sha256':identity['source_sha256'],
        'cases':result,'original_pins':pins,'warm_timings_ns':timings},ensure_ascii=False).encode())


def compare(before, after):
    require(before['source_sha256']==SOURCE and after['source_sha256']!=SOURCE,'actual_install_A_B_identity_wrong')
    require(before['original_pins']==after['original_pins'] and before['cases'].keys()==after['cases'].keys(),
            'original_sources_or_frozen_case_roster_changed')
    failures, checked = [], {}
    for name,left in before['cases'].items():
        right=after['cases'][name]
        old_wire,new_wire=(Path(item['MCP_RX']['path']).read_bytes() for item in (left,right))
        passed = old_wire==new_wire
        if left['expected_new']:
            a,b=(json.loads(wire) for wire in (old_wire,new_wire))
            if right.get('path_fields') and not left.get('path_fields') and a['id']==b['id']:
                text_a,text_b=(json.loads(item['result']['content'][0]['text']) for item in (a,b))
                frame, = text_b['images']
                path = Path(frame.pop('local_image_path'))
                passed = text_a==text_b and a['result']['content'][1:]==b['result']['content'][1:] \
                    and path.is_absolute() and digest(path.read_bytes())==SAMPLE_PNG
                if name=='actual_sampled_brief':
                    original = Path(read(V/RANK/'checks/QUALITY.json')['verified']['P1']['final_image']['PNG'])
                    passed = passed and str(original)==str(path)
        if left['actual_original']:
            passed = passed and left['original_body_and_blocks_value_equal']
        if not passed:
            failures.append(name)
        checked[name] = {'passed':passed,'byte_identical':old_wire==new_wire,
                         'candidate_path_count':len(right.get('path_fields',[]))}
        if name=='wrong_recorded_png_byte_count':
            audit = right['actual_cold_serializer_audit']['frames'][0]
            checked[name]['expanded_private_frame_count_disagreement'] = {
                'producer_declared_PNG_bytes':4016,'stdio_verified_PNG_bytes':audit['PNG_bytes_read'],
                'native_PNG_sha256':right['images'][0], 'provenance_canonical_directory_lookup_count':right['service_directory_lookup_count'],
                'original_native_contents_equal':old_wire!=new_wire and left['images']==right['images']}
    def summary(rows):
        return {key:{'median':statistics.median(row[key] for row in rows),
                     'p95':sorted(row[key] for row in rows)[(len(rows)*95+99)//100-1]} for key in rows[0]}
    return {'passed':not failures,'failures':failures,'cases':checked,
            'denominator':len(checked),'exact_compatibility':sum(row['byte_identical'] for row in checked.values()),
            'path_positive_total':sum(row['expected_new'] for row in before['cases'].values()),
            'warm_timing_median_p95_ns':{'baseline':summary(before['warm_timings_ns']),'candidate':summary(after['warm_timings_ns'])},
            'warm_timing_samples_per_arm':len(before['warm_timings_ns']),'scope':'in-process public stdio replay over frozen producer; no renderer, host, or model starts'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--timing-samples',type=int,default=48)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--baseline-only',action='store_true')
    args=parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode and args.timing_samples>0,'run_with_Isolated_Python_I_B')
    if args.worker:
        worker(args.candidate.resolve(strict=True),args.out.resolve(),args.timing_samples)
        return
    args.out.mkdir(parents=True)
    arms={}
    for label,binding in (('baseline',BASE),('candidate',args.candidate)):
        raw=subprocess.check_output([sys.executable,'-IB',str(Path(__file__).resolve()),'--worker',
            '--candidate',str(binding.resolve()),'--out',str((args.out/label).resolve()),
            '--timing-samples',str(args.timing_samples)],timeout=100)
        arms[label]=json.loads(raw)
        save(args.out/(label.upper()+'.json'),arms[label])
        if args.baseline_only:
            print(json.dumps({'baseline_cases':len(arms[label]['cases']),'replayed':True}))
            return
    report=compare(arms['baseline'],arms['candidate'])
    save(args.out/'CONTROL_REVIEW.json',report)
    print(json.dumps(report,ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
