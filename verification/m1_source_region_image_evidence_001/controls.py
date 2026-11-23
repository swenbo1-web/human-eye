"""Exercise the installed MCP image gate and the existing full fallback."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, Thread
import sys
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
BASE = V/'m4_source_region_curved_view_sample_001/install/PRODUCT_RUN_BINDING.json'
BASE_GIT = 'b1a2fa942ba6aea95bf4fef7161aaba89bdc6237'
LOW = Path('D:/he_m4_yanyite_low_bilateral_product_native_001').resolve()
CURVED = Path('D:/he_m4_source_region_curved_view_sample_001').resolve()
RECOVERY = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001').resolve()
RECOVERY_INDEX = V/'m1_region_task_first_packet_consumption_holdout_recovery_001'
GUIDE = 'response_detail=full on the standard endpoint'
BRIEF = 'source-region-brief-v2'
FULL = 'human-eye-source-region-observation-v1'


def signature(raw):
    return {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Fixtures:
    def __init__(self):
        self.pins = {}

    def pin(self, path):
        path = Path(path).resolve(strict=True)
        raw = path.read_bytes()
        row = {'path': str(path), **signature(raw)}
        require(self.pins.setdefault(row['path'], row) == row, 'frozen_control_input_changed')
        return raw

    def archived(self, root, member):
        folder = (RECOVERY_INDEX if root == RECOVERY else root/'sealed').resolve(strict=True)
        index = json.loads(self.pin(folder/'RAW_INDEX.json'))
        bundle = folder/'ORIGINAL_RUNTIME.zip'
        bundle_pin = signature(self.pin(bundle))
        require(all(bundle_pin[k] == index['archive'][k] for k in bundle_pin), 'control_archive_changed')
        key = ('runtime/' if root == RECOVERY else '') + member
        original = self.pin(root/member)
        with ZipFile(bundle) as archive:
            require(archive.read(key) == original and index['members'][key] == signature(original),
                    'unbound_control_member/' + member)
        return json.loads(original)


def call(arguments, name):
    return {'jsonrpc':'2.0', 'method':'tools/call', 'id':name,
            'params':{'name':'human_eye_scene_observe','arguments':arguments}}


def settled_value(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def controls(binding_path, output, candidate):
    fixture = Fixtures()
    binding = json.loads(fixture.pin(binding_path))
    installed = Path(binding['install_root']).resolve(strict=True)
    manifest = {row['path']:row['sha256'] for row in binding['source_manifest']}
    require(len(manifest) == 143 and (binding['preparation_git'] != BASE_GIT) == candidate,
            'wrong_control_arm_installation')
    sys.path[:0] = [str(installed), binding['dependency_root']]
    import numpy as np
    from human_eye_plugin import attention_raster, live_service, live_spatial_mcp, source_region
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.scene_residency import SceneDeltaDecoder

    for module in (attention_raster, live_service, live_spatial_mcp, source_region):
        path = Path(module.__file__).resolve(strict=True)
        require(signature(fixture.pin(path))['sha256'] == manifest[path.relative_to(installed).as_posix()],
                'wrong_loaded_control_module')
    run = output.resolve()
    run.mkdir(parents=True, exist_ok=False)
    source = fixture.archived(LOW, 'slots/P1/native/WIRE/003/RESPONSE.bin')
    original = fixture.archived(LOW, 'slots/P1/product_full/call_002/SERVICE_RESULT.json')
    main_args = fixture.archived(LOW, 'slots/P1/product_calls/call_002/REQUEST.json')['params']['arguments']
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    encoded = source['result']['result']
    require(source['status'] == 'success' and encoded.startswith(prefix), 'missing_real_captured_source')
    scene = SceneDeltaDecoder().apply(json.loads(encoded[len(prefix):])['result'])
    context = ReadContext()
    context.activate(scene, 'source_region')
    indexed = deepcopy(main_args['query'])
    indexed['region'].pop('world_box_m')
    indexed['region']['source_triangle_indices'] = original['region_ref']['source_triangle_indices']
    prepared = source_region.prepare_region(scene, indexed)
    require(prepared.region_ref == original['region_ref'], 'new_prepare_does_not_match_actual_region')
    registry,_ = context.prepared('source_regions', lambda: {'regions': {prepared.region_ref['region_id']:prepared}})
    measured = source_region.measure_region(prepared, indexed['reference'], context.scene_cache)
    require(measured['facts'] == original['task_result']['facts']
            and measured['source_mapping'] == original['task_result']['source_mapping'],
            'live_measurement_or_nearest_source_changed')
    state_path = run/'state.json'
    image_root = run/'state.json.source_region'
    directory = image_root/'9c6bb5c372e31b91a814a6d6bb8f7171'
    cold = source_region.observe_region(prepared, directory, include_image=True)
    warm = source_region.observe_region(prepared, directory, include_image=True)
    no_image = source_region.observe_region(prepared, directory, include_image=False)
    for result in (cold, warm, no_image):
        result.update(session_id='m1-image-evidence-controls', task_result=measured)
    frame, = cold['frames']
    path = Path(frame['image_path'])
    original_png = path.read_bytes()
    pixel = cold['facts']['visibility']['sampled_pixel']
    require(frame['image_sha256'] == original['frames'][0]['image_sha256']
            == signature(original_png)['sha256'] and len(original_png) == 27_001
            and pixel == {'row':24, 'column':377, 'source_triangle_index':24047}, 'real_left_raster_changed')
    with np.load(frame['arrays_path'], allow_pickle=False) as arrays:
        row, column, source_face = (pixel[key] for key in ('row','column','source_triangle_index'))
        offset = int(arrays['face_patch_offsets'][prepared.object_index])
        require(arrays['owners'][row,column] == prepared.object_index
                and arrays['triangle_ids'][row,column] - offset == source_face, 'source_pixel_not_in_real_array')
        inactive = np.argwhere(arrays['owners'] != prepared.object_index)[0].tolist()
    require(cold['work']['raster_attempts'] == 1 and warm['work']['raster_attempts'] == 0
            and warm['work']['frame_reuses'] == 1 and no_image['work']['raster_attempts'] == 0,
            'fixture_construction_not_1_raster')
    kept = prepared.observation
    actual = live_service.LiveSpatialService
    cases = {}

    class Service:
        _matching_source_region_producer = actual._matching_source_region_producer

        def __init__(self, value, path_root, raised):
            self.value, self.state_path, self.raised = value, path_root, raised
            self._read_context = context
            self.calls, self.proof_requests, self.audits = [], [], []

        def observe(self, session_id, **kwargs):
            self.calls.append(kwargs)
            if self.raised is not None:
                raise ValueError(self.raised)
            return self.value

        def _source_region_sample_path(self, value, frame):
            self.proof_requests.append(frame['image_ref'])
            return actual._source_region_sample_path(self, value, frame)

        def record_event(self, name, **kwargs):
            self.audits.append((name,kwargs))

        def _check_request_budget(self, stage):
            require(stage == 'before_task_publication', 'new_request_work_during_projection')

    def capture(name, value, arguments, *, evidence=True, wanted=None, images=1, serves=1, state=state_path,
                raises=None, read_failure=False, proof_count=None):
        spy = Service(value, state, raises)
        server = live_spatial_mcp.LiveSpatialMCPServer(spy, 'm1-source-region-controls',
                                                     region_task_evidence=evidence)
        before_value, before_args = settled_value(value), settled_value(arguments)
        pngs = []
        real_read = Path.read_bytes

        def watched_read(path):
            require(path.suffix.lower() != '.npz', 'mcp_projection_read_NPZ_again')
            if path.suffix.lower() == '.png':
                pngs.append(str(path))
                if read_failure:
                    raise PermissionError('control_image_read_denied')
            return real_read(path)

        def reject_work(*unused, **unused_kw):
            raise ValueError('mcp_projection_added_read_or_geometry_work')

        with patch.object(Path, 'read_bytes', watched_read), patch.object(np, 'load', reject_work), \
             patch.object(source_region, 'observe_region', reject_work), \
             patch.object(source_region, 'prepare_region', reject_work), \
             patch.object(source_region, 'measure_region', reject_work), \
             patch.object(attention_raster, 'select_sparse_attention_view', reject_work):
            result = server.handle_jsonrpc_message(call(arguments, name))['result']
        body = json.loads(result['content'][0]['text'])
        expected_error = wanted == 'error'
        require(result['isError'] is expected_error and (expected_error or body.get('schema') == wanted)
                and len(result['content']) == images+1 and len(spy.calls) == serves, 'wrong_dispatch_shape/' + name)
        require(settled_value(value) == before_value and settled_value(arguments) == before_args,
                'producer_or_request_mutated/' + name)
        if spy.calls:
            source_args = spy.calls[0]
            require(source_args['query'] == arguments['query'] and 'response_detail' not in source_args
                    and ('include_image' in source_args) == ('include_image' in arguments)
                    and source_args.get('include_image') == arguments.get('include_image'),
                    'public_projection_changed_original_dispatch/' + name)
        require(len(spy.proof_requests) <= 1 and (proof_count is None or len(spy.proof_requests) == proof_count),
                'incorrect_path_proof_calls/' + name)
        require(len(pngs) == (1 if read_failure else images), 'png_count_changed/' + name)
        if images:
            from base64 import b64decode
            require(all(block['type'] == 'image' and block['mimeType'] == 'image/png'
                        and signature(b64decode(block['data'], validate=True))['sha256'] == expected['image_sha256']
                        for block, expected in zip(result['content'][1:],value['frames'],strict=True)),
                    'different_PNG_delivered/' + name)
        if value['result_kind'] == 'source_region' and serves and not expected_error:
            delivery = body['image_delivery']
            require(delivery['new_raster_attempts'] == value['work']['raster_attempts']
                    and delivery['frame_reuses'] == value['work']['frame_reuses'],
                    'source_delivery_work_changed/' + name)
        cases[name] = {'schema':body.get('schema'), 'error':result['isError'],
                       'body_bytes':len(result['content'][0]['text'].encode('utf-8')),
                       'content_sha256':signature(settled_value(result))['sha256'],
                       'png_reads':len(pngs), 'current_path_proofs':len(spy.proof_requests), 'images':images,
                       'service_dispatches':len(spy.calls)}
        return body,result

    def with_args(**updates):
        return {**deepcopy(main_args),**updates}

    def inspect_compact(body, guide=False):
        image, = body['images']
        require(image['image_block_index'] == 1 and image['sampled_pixel'] == pixel
                and image['local_image_path'] == path.resolve(strict=True).as_posix()
                and body['task_result']['facts'] == measured['facts']
                and body['task_result']['source_mapping'] == {'nearest_witness':measured['source_mapping']['nearest_witness']}
                and body['region_ref'] == prepared.region_ref and body['visibility']['complete_witness'] is None,
                'compact_frame_or_immutable_facts_changed')
        if guide:
            require(body.get('details') == GUIDE, 'missing_standard_diagnostics_hint')

    def compare_full(name, value=cold, arguments=main_args, **params):
        expected = params.pop('wanted', FULL)
        _, standard = capture(name+'/standard', value, arguments, evidence=False, wanted=expected, **params)
        _, gated = capture(name+'/evidence', value, arguments, wanted=expected, **params)
        require(gated == standard, 'full_diagnostic_fallback_changed/' + name)

    compare_full('ordinary_standard_shape', arguments=main_args, wanted=FULL, state=run/'other-state.json')
    _, legacy_full = capture('successful/standard_full', cold, main_args, evidence=False, wanted=FULL, proof_count=0)
    direct, direct_result = capture('successful/evidence_full', cold, main_args,
                                   wanted=BRIEF if candidate else FULL, proof_count=int(candidate))
    if candidate:
        require(direct_result['content'][1:] == legacy_full['content'][1:]
                and len(direct_result['content'][0]['text'].encode()) <= 10_800, 'evidence_full_budget_or_image_changed')
        inspect_compact(direct, guide=True)
    else:
        require(direct_result == legacy_full, 'baseline_explicit_full_changed')
    for name,value,args in (
        ('brief', cold, with_args(response_detail='brief')),
        ('omitted_detail', cold, {k:v for k,v in main_args.items() if k != 'response_detail'}),
        ('omitted_include_image', cold, {k:v for k,v in main_args.items() if k != 'include_image'}),
        ('explicit_rows', cold, with_args(query=indexed)),
        ('warm_ref', warm, with_args(query={**{k:v for k,v in indexed.items() if k != 'region'},
                                            'region_ref':prepared.region_ref})),
    ):
        brief = name in ('brief','omitted_detail') or candidate
        body,_ = capture('successful/'+name, value, args, wanted=BRIEF if brief else FULL, proof_count=int(brief))
        if brief:
            inspect_compact(body, guide=candidate and name not in ('brief','omitted_detail'))
    no_args = with_args(include_image=False)
    plain,_ = capture('no_image/standard', no_image, no_args, evidence=False, wanted=FULL, images=0, proof_count=0)
    condensed,_ = capture('no_image/evidence', no_image, no_args, wanted=BRIEF, images=0, proof_count=0)
    require(plain['task_result']['facts'] == condensed['task_result']['facts'] == measured['facts']
            and condensed['details'] == GUIDE and condensed['images'] == [], 'old_no_image_contract_changed')
    compare_full('include_image_false_with_frame_producer', arguments=no_args)

    def alter(name, edit, *, both=False, wanted=FULL, weight=1, **params):
        value, backing = deepcopy(cold), deepcopy(kept)
        edit(value)
        if both:
            edit(backing)
            prepared.observation = backing
        try:
            compare_full(name, value, wanted=wanted, images=weight, **params)
        finally:
            prepared.observation = kept

    def visibility(value):
        return value['facts']['visibility']

    def sample(value):
        return visibility(value)['sampled_pixel']

    alter('response_only_wrong_pixel', lambda v: sample(v).update(row=inactive[0],column=inactive[1]))
    alter('correlated_wrong_pixel', lambda v: sample(v).update(row=inactive[0],column=inactive[1]), both=True)
    alter('correlated_bool_pixel', lambda v: sample(v).update(row=True), both=True)
    alter('correlated_out_of_frame_pixel', lambda v: sample(v).update(column=512), both=True)
    alter('correlated_nonmatching_source', lambda v: sample(v).update(source_triangle_index=999999), both=True)
    alter('missing_pixel', lambda v: visibility(v).pop('sampled_pixel'), both=True)
    alter('correlated_wrong_frame_identity', lambda v: [row.update(frame_identity='0'*64)
                for row in (visibility(v), v['frames'][0])], both=True)
    alter('wrong_returned_object_instance', lambda v: v['facts']['region'].update(instance_id='wrong-slot'))
    alter('wrong_parent_display_identity', lambda v: v['binding'].update(display_identity='wrong-display'))
    alter('wrong_task_binding', lambda v: v['task_result']['binding'].update(scene_revision='wrong-revision'))
    alter('non_exact_measurement', lambda v: v['task_result']['source_mapping']['nearest_witness']['a'].
                update(exact_membership=False))
    alter('unknown_measurement', lambda v: v['task_result']['facts']['surface_proximity'].update(status='unknown'))
    alter('negative_distance', lambda v: v['task_result']['facts']['surface_proximity']['value'].update(distance_m=-1))
    alter('incorrect_measurement_scope', lambda v: v['task_result'].update(measurement_scope='whole_objects'))
    alter('extra_fact_in_service_result', lambda v: v['task_result']['facts'].update(aabb={'status':'measured'}))
    alter('multiple_frames', lambda v: v['frames'].append(v['frames'][0]), wanted='error', weight=0)
    alter('zero_selected_pixel_producer', lambda v: visibility(v).update(selected_surface_pixels=0), both=True)
    alter('wrong_frame_parent', lambda v: v['frames'][0].update(host_binding_sha256='0'*64), wanted='error', weight=0)

    alien = image_root/'880f8e956d672b32e2c603703a43a1ef'/path.name
    alien.parent.mkdir()
    alien.write_bytes(original_png)
    alter('other_generation_same_png', lambda v: v['frames'][0].update(image_path=str(alien)), both=True)
    compare_full('read_permission_failure', wanted='error', images=0, read_failure=True)
    compare_full('invalid_fact_arguments', arguments=with_args(query={**indexed,'requested_facts':['aabb']}),
                 wanted='error', serves=0, images=0)
    compare_full('underlying_expired_ref_error', wanted='error', serves=1, images=0,
                 raises='source_region_ref_capture_generation_changed')
    registry['regions'].pop(prepared.region_ref['region_id'])
    try:
        compare_full('producer_evicted')
    finally:
        registry['regions'][prepared.region_ref['region_id']] = prepared

    acquired, release = Event(), Event()

    def hold_current():
        with context.lock:
            acquired.set()
            release.wait(4)

    hold = Thread(target=hold_current)
    hold.start()
    try:
        require(acquired.wait(2), 'control_read_lock_not_acquired')
        compare_full('matching_producer_lock_contention')
    finally:
        release.set()
        hold.join(2)
    require(not hold.is_alive(), 'control_read_lock_still_held')
    advanced = {**scene,'capture_state':{**scene['capture_state'],'revision':scene['capture_state']['revision']+1}}
    context.activate(advanced, 'source_region')
    compare_full('stale_read_context')
    context.activate(scene, 'source_region')
    context.prepared('source_regions', lambda: registry)
    revisit,_ = capture('post_stale_recovery', warm, main_args, wanted=BRIEF if candidate else FULL,
                        proof_count=int(candidate))
    if candidate:
        inspect_compact(revisit, guide=True)

    for label,number,expected_kind in (('rectangle','004','locally_observed'),
                                       ('hidden','007','evidence_insufficient')):
        value = fixture.archived(CURVED, f'controls/BP/product_full/call_{number}/SERVICE_RESULT.json')
        require(value['observation_status'] == expected_kind and len(value['frames']) == 1,
                'historical_compatibility_producer_changed/' + label)
        require((value['facts']['visibility']['complete_witness'] is not None) == (label == 'rectangle'),
                'wrong_historical_visibility_scope/' + label)
        compare_full(label, value)
    ordinary = fixture.archived(CURVED, 'controls/BP/product_full/call_008/SERVICE_RESULT.json')
    ordinary_args = {'query':{'mode':'active_observation'},'include_image':False,'response_detail':'full'}
    compare_full('ordinary_active_observation', ordinary, ordinary_args, images=0, wanted=None)
    region = fixture.archived(RECOVERY, 'slots/B1/product_full/call_001/SERVICE_RESULT.json')
    request = fixture.archived(RECOVERY, 'slots/B1/product_calls/call_001/REQUEST.json')
    region_args = {**request['params']['arguments'],'response_detail':'full'}
    _,old_region = capture('region_task/standard', region, region_args, evidence=False, wanted=None, images=3)
    body,recovered = capture('region_task/evidence', region, region_args, images=3,
                             wanted='active-observation-region-task-brief-v2')
    require(recovered['content'][1:] == old_region['content'][1:] and len(body['region_task']['rows']) == 3,
            'existing_region_task_projection_changed')
    receipt = {'passed':True, 'runtime':'actual_isolated_mcp_dispatch_and_retained_producer',
               'product_commit':binding['preparation_git'],'product_source_sha256':binding['source_sha256'],
               'case_count':len(cases), 'cases':cases, 'source_pins':list(fixture.pins.values()),
               'prepared_rasters':cold['work']['raster_attempts'], 'warm_rasters':warm['work']['raster_attempts'],
               'projection_rasters':0, 'projection_NPZ_reads':0, 'Blender':0, 'models':0}
    with (run/'SUMMARY.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(f"{len(cases)} verified installed dispatcher cases in {run}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, default=BASE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    controls(args.binding, args.output, args.candidate)
