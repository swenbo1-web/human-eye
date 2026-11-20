"""Revalidate the bounded pixel shortfall against immutable Blender output."""

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
from contextlib import ExitStack


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
PRIMARY = 'D:/he_m4_cross_scale_assembly_transfer_001'
COLD = V / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
REPLAY = V / 'm4_cross_scale_region_geometry_facts_001/checks/projection_replay.py'
SOURCE = 'human_eye_plugin/live_spatial_mcp.py'
FIELD = 'pixel_shortfall'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def inspect_pixels(original, value):
    """Use only the original PNG, owner/triangle IDs, and independent mesh source."""
    import numpy as np
    from PIL import Image

    terminal = original.load(original.slot / 'TERMINAL_SOURCE.json')
    truth = json.loads(original.evidence.raw(ASSEMBLY / 'fixture/CURRENT_TRUTH.json',
        'da4a27ac2cf278709a3f1a7de691af416fc2c1b21d2846a21a1d38732ddbbd71'))
    directions = {row['object_name']: row['eligible_complete_views'] for row in truth['eligible']}
    expected = {obj['name']: obj for obj in terminal['objects']}
    rows = value['facts']['region_task']['rows']
    scopes = {scope['scope_id']: scope for scope in value['scopes']}
    measurements = {}
    for frame in value['constructed_frames']:
        scope = scopes[frame['scope_id']]
        binding = scope['binding']
        objects = binding['objects']
        names = [obj['object_name'] for obj in objects]
        offsets = [0, *np.cumsum([len(expected[name]['evaluated']['triangles']) for name in names]).tolist()]
        png = original.raw(frame['image_path'])
        npz = original.raw(frame['arrays_path'])
        require(hashlib.sha256(png).hexdigest() == frame['image_sha256']
                and hashlib.sha256(npz).hexdigest() == frame['arrays_sha256'],
                'frame_member_does_not_match_producer_digest')
        with Image.open(io.BytesIO(png)) as im, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
            pixels = arrays['color'][:, :, :3].astype(np.int32)
            require(set(expected) == set(names) and len(names) == len(expected)
                    and all(obj['object_index'] == n and obj['host_id'] == expected[name]['object_id']
                            and obj['instance_id'] == expected[name]['instance_id']
                            for n, (name, obj) in enumerate(zip(names, objects, strict=True)))
                    and offsets == arrays['face_patch_offsets'].tolist()
                    and im.size == (512, 512) and im.format == 'PNG'
                    and np.array_equal(np.asarray(im.convert('RGB')), pixels),
                    'independent_image_or_object_basis_changed')
            observation = next(item for item in scope['facts']['observations']
                               if item['frame_identity'] == frame['frame_identity'])
            for row in rows:
                name = row['object_name']
                reports = [item for item in observation['pixel_rows'] if item['roi_id'] == row['roi_id']]
                if not reports:
                    continue
                report, = reports
                obj = names.index(name)
                triangles = [offsets[obj] + i for i in row['source_triangle_indices']]
                owners = (arrays['owners'] == obj) & np.isin(arrays['triangle_ids'], triangles)
                require(np.isfinite(arrays['depth'][owners]).all(), 'source_triangle_depth_not_finite/' + name)
                contrasting = np.zeros(owners.shape, dtype=bool)
                for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                             (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
                    delta = pixels[a] - pixels[b]
                    contrasting[a] |= owners[a] & ~owners[b] & (np.sum(delta * delta, axis=2) >= 24**2)
                surface, edges = int(np.count_nonzero(owners)), int(np.count_nonzero(contrasting))
                require((report['visible_surface_pixels'], report['contrasting_boundary_pixels']) ==
                        (surface, edges), 'independent_surface_or_contrast_differs/' + name)
                measurements.setdefault(name, []).append({'scope_id': frame['scope_id'],
                    'frame_identity': frame['frame_identity'], 'view_name': frame['view_name'],
                    'visible_surface_pixels': surface, 'contrasting_boundary_pixels': edges,
                    'geometrically_complete_direction': frame['view_name'] in directions[name],
                    'PNG_sha256': frame['image_sha256'], 'NPZ_sha256': frame['arrays_sha256']})
    return measurements


def compatibility_source(evidence, path, digest, detail):
    producer = json.loads(evidence.raw(path, digest))
    for frame in producer['frames']:
        evidence.raw(frame['image_path'], frame['image_sha256'])
        evidence.raw(frame['arrays_path'], frame['arrays_sha256'])
    return {'source': path, 'arguments': {'response_detail': detail}, 'work': producer['work']}


def expected_call(case, result):
    body = case['response']
    require(result['work'] == case['work']
            and json.loads(result['result']['content'][0]['text']) == json.loads(body['content'][0]['text'])
            and len(result['result']['content'][0]['text'].encode()) == len(body['content'][0]['text'].encode())
            and result['result']['content'][1:] == body['content'][1:]
            and result['result']['isError'] is False, 'baseline_replay_differs_from_original_wire')


def shortfall_row(body, name):
    return next(row for row in body['region_task']['rows'] if row['object_name'] == name)


def verify_shortfall(reference, actual, measurements):
    original, updated = [json.loads(item['content'][0]['text']) for item in (reference, actual)]
    remainder = copy.deepcopy(updated)
    row = shortfall_row(remainder, 'N10')
    evidence = row.pop(FIELD)
    local, = [m for m in measurements['N10'] if m['scope_id'] != 'global' and m['view_name'] == 'TOP']
    global_top, = [m for m in measurements['N10'] if m['scope_id'] == 'global' and m['view_name'] == 'TOP']
    require((local['visible_surface_pixels'], local['contrasting_boundary_pixels']) == (8835, 0)
            and (global_top['visible_surface_pixels'], global_top['contrasting_boundary_pixels']) == (5026, 0)
            and local['geometrically_complete_direction'] and global_top['geometrically_complete_direction'],
            'expected_distinct_original_TOP_probes_not_measured')
    require(evidence == {'scope_id': local['scope_id'], 'view_name': 'TOP',
                         'visible_surface_pixels': 8835, 'contrasting_boundary_pixels': 0,
                         'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4,
                         'minimum_rgb_boundary_contrast': 24, 'image_delivered': False,
                         'native_content_block_index': None},
            'actual_shortfall_not_bound_to_local_TOP_or_claims_unselected_image')
    require(remainder == original and row['complete_witness'] is None
            and row['reason'] == 'pixel_evidence_insufficient', 'non_shortfall_brief_semantics_changed')
    require(any(m['view_name'] == 'SCENE' and
                (m['visible_surface_pixels'], m['contrasting_boundary_pixels']) == (1489, 546)
                for m in measurements['N22'])
            and any(m['view_name'] == 'TOP' and
                    (m['visible_surface_pixels'], m['contrasting_boundary_pixels']) == (6244, 13)
                    for m in measurements['N11']),
            'successful_and_partially_occluded_controls_not_independently_measured')
    require(FIELD not in shortfall_row(updated, 'N22') and FIELD not in shortfall_row(updated, 'N11'),
            'successful_witness_or_geometrically_occluded_partial_labeled_shortfall')
    return evidence


def control_process(install, dependency, source):
    command = """
import json, runpy, sys
from pathlib import Path
install, dependency, script, source = map(Path, sys.argv[1:])
sys.path[:0] = [str(install), str(dependency)]
from human_eye_plugin import live_spatial_mcp
assert Path(live_spatial_mcp.__file__).resolve() == install / 'human_eye_plugin/live_spatial_mcp.py'
controls = runpy.run_path(str(script))['exercise_controls']
print(json.dumps(controls(live_spatial_mcp._tool_result, json.loads(source.read_bytes())), ensure_ascii=True))
"""
    child = subprocess.run([sys.executable, '-I', '-B', '-c', command, str(install),
                            str(dependency), __file__, source], capture_output=True, check=False, timeout=60)
    if child.returncode:
        raise ValueError(child.stderr.decode())
    return json.loads(child.stdout)


def exercise_controls(formatter, fixture):
    """Check producer/formatter contracts without treating synthetic rows as real pixels."""
    results = {}
    original = copy.deepcopy(fixture)

    def project(value):
        result = formatter(value, is_error=False, response_detail='brief')
        return json.loads(result['content'][0]['text']), result['content'][1:]

    def trial(name, mutate, *, expect=None, may_reject=False, roi='N10'):
        value = copy.deepcopy(fixture)
        mutate(value)
        before = copy.deepcopy(value)
        try:
            body, images = project(value)
        except (ValueError, KeyError, IndexError) as exc:
            require(may_reject, 'unexpected_projection_error/' + name + '/' + str(exc))
            results[name] = {'outcome': 'rejected', 'reason': str(exc)}
        else:
            probe = shortfall_row(body, roi).get(FIELD)
            if expect is None:
                require(probe is None, 'invalid_control_produced_shortfall/' + name)
                results[name] = {'outcome': 'omitted'}
            else:
                require(probe is not None and all(probe[k] == wanted for k, wanted in expect.items()),
                        'valid_control_did_not_report_expected_shortfall/' + name + '/' + str(probe))
                if probe['image_delivered']:
                    index = probe['native_content_block_index']
                    require(type(index) is int and 1 <= index <= len(images)
                            and images[index - 1]['type'] == 'image', 'selected_shortfall_public_block_unresolvable')
                results[name] = {'outcome': 'confirmed', 'pixel_shortfall': probe}
        require(value == before and fixture == original, 'control_formatter_mutated_producer_value/' + name)

    row = shortfall_row(fixture['facts'], 'N10')
    roi = row['roi_id']
    region_scope, = [scope['scope_id'] for scope in fixture['scopes'] if
                     scope['binding'].get('region_source') == row['source']]

    def local(value):
        return next(scope for scope in value['scopes'] if scope['scope_id'] == region_scope)

    def local_frame(value):
        return next(frame for frame in value['constructed_frames'] if frame['scope_id'] == region_scope)

    def probe_rows(value):
        return [probe for scope in value['scopes'] for observation in scope['facts']['observations']
                if observation['view_name'] == 'TOP' for probe in observation['pixel_rows'] if probe['roi_id'] == roi]

    trial('prediction_status_cannot_publish_observation',
          lambda value: value.update(observation_status='prediction_only'))
    trial('geometric_occlusion_with_partial_pixels',
          lambda value: shortfall_row(value['facts'], 'N11').update(reason='pixel_evidence_insufficient'),
          roi='N11')
    trial('stale_capture_frame', lambda value: local_frame(value).update(source_revision='wrong'), may_reject=True)
    trial('stale_scope_capture_state',
          lambda value: local(value)['binding']['capture_state'].update(revision=-1), may_reject=True)
    trial('wrong_local_ordered_source',
          lambda value: local(value)['binding']['region_source'].update(ordered_geometry_sha256='f' * 64))
    trial('forged_selected_frame',
          lambda value: value['frames'].append({**local_frame(value), 'frame_identity': '0' * 64}), may_reject=True)
    trial('wrong_scope_frame_order',
          lambda value: local(value).update(frame_refs=['1' * 64]), may_reject=True)
    trial('wrong_observation_frame_order',
          lambda value: local(value)['facts']['observations'][0].update(frame_identity='2' * 64), may_reject=True)
    for name, fields in (
            ('wrong_ROI', {'roi_id': 'other_ROI'}),
            ('wrong_host', {'host_id': 'foreign_instance'}),
            ('wrong_object_index', {'object_index': -1}),
            ('wrong_pixel_view', {'view': 'SCENE'}),
            ('back_facing_pixel', {'front_facing': False}),
            ('readable_flag_disagrees', {'readable': True}),
            ('bool_count', {'contrasting_boundary_pixels': False}),
            ('negative_count', {'contrasting_boundary_pixels': -1}),
            ('contrast_exceeds_surface', {'visible_surface_pixels': 0, 'contrasting_boundary_pixels': 1}),
            ('wrong_threshold', {'minimum_rgb_boundary_contrast': 1}),
            ('positive_count_without_location', {'visible_pixel_bounds': None, 'visible_pixel_anchor': None}),
            ('both_thresholds_pass', {'contrasting_boundary_pixels': 4})):
        def mutate(value, fields=fields):
            for item in probe_rows(value):
                item.update(fields)
        trial(name, mutate, may_reject=True)

    def duplicate_local_pixel(value):
        observation = local(value)['facts']['observations'][0]
        same, = [item for item in observation['pixel_rows'] if item['roi_id'] == roi]
        observation['pixel_rows'].append(copy.deepcopy(same))

    trial('ambiguous_duplicate_ROI_pixel', duplicate_local_pixel)

    def duplicate_local_reason(value):
        reasons = local(value)['facts']['region_evidence']
        same, = [item for item in reasons if item['roi_id'] == roi]
        reasons.append(copy.deepcopy(same))

    trial('ambiguous_duplicate_ROI_evidence', duplicate_local_reason)

    def remove_top(value):
        value['constructed_frames'][:] = [f for f in value['constructed_frames'] if f['view_name'] != 'TOP']
        for scope in value['scopes']:
            scope['facts']['observations'][:] = [item for item in scope['facts']['observations']
                                                if item['view_name'] != 'TOP']
            scope['frame_refs'][:] = [item['frame_identity'] for item in scope['facts']['observations']]
        value['facts']['region_task']['summary']['constructed_image_count'] = len(value['constructed_frames'])

    trial('claimed_shortfall_without_real_frame', remove_top, may_reject=True)

    def injected_shortfall(value):
        remove_top(value)
        shortfall_row(value['facts'], 'N10')[FIELD] = {'image_delivered': True, 'native_content_block_index': 9}

    trial('injected_shortfall_field_with_no_actual_frame', injected_shortfall)

    def set_zero(value):
        for item in probe_rows(value):
            item.update(visible_surface_pixels=0, contrasting_boundary_pixels=0,
                        visible_pixel_bounds=None, visible_pixel_anchor=None)

    trial('exact_zero_pixels_is_a_shortfall', set_zero,
          expect={'scope_id': region_scope, 'visible_surface_pixels': 0, 'contrasting_boundary_pixels': 0,
                  'image_delivered': False, 'native_content_block_index': None})
    trial('actual_selected_shortfall_index', lambda value: value['frames'].append(local_frame(value)),
          expect={'scope_id': region_scope, 'view_name': 'TOP',
                  'image_delivered': True, 'native_content_block_index': 2})
    trial('two_existing_scopes_prefer_local', lambda value: value['scopes'].reverse(),
          expect={'scope_id': region_scope, 'view_name': 'TOP', 'visible_surface_pixels': 8835})

    def add_synthetic_prior_view(value):
        # Only an actual selected frame can produce a public block index. This
        # synthetic unselected frame checks deterministic ordering with two views.
        scope = local(value)
        other = copy.deepcopy(local_frame(value))
        name = 'BACK'
        other.update(view_name=name, frame_identity='3' * 64, image_ref='active-host-image:' + '4' * 64)
        scope['frame_refs'].insert(0, other['frame_identity'])
        value['constructed_frames'].insert(value['constructed_frames'].index(local_frame(value)), other)
        observation = copy.deepcopy(scope['facts']['observations'][0])
        observation.update(view_name=name, frame_identity=other['frame_identity'], image_ref=other['image_ref'])
        for item in observation['pixel_rows']:
            item['view'] = name
        scope['facts']['observations'].insert(0, observation)
        local_reason = next(item for item in scope['facts']['region_evidence'] if item['roi_id'] == roi)
        for item in (local_reason, shortfall_row(value['facts'], 'N10')):
            item['view_reasons']['positive_area_occlusion'].remove(name)
            item['view_reasons']['pixel_evidence_insufficient'].append(name)

    trial('two_views_use_first_actual_order', add_synthetic_prior_view,
          expect={'scope_id': region_scope, 'view_name': 'BACK', 'image_delivered': False})
    return results


def run_checks(output, baseline_only=False):
    replay = runpy.run_path(str(REPLAY))
    evidence = replay['Evidence']()
    evidence.raw(REPLAY, '10af2c84b49596e7130235310938243cdf0cf1c28288b739ea10005e55e45232')
    evidence.raw(__file__)
    binding_a = json.loads(evidence.raw(COLD, 'f19f417d9d7a468626941a45bef997d5cc5902b9fb0fe743a9b476d6990e5cea'))
    binding_b = binding_a if baseline_only else json.loads(evidence.raw(NS / 'install/PRODUCT_RUN_BINDING.json'))
    dependency = Path(binding_a['dependency_root']).resolve()
    require(dependency == Path(binding_b['dependency_root']).resolve(), 'dependency_root_changed_between_arms')
    sys.path.insert(0, str(dependency))
    installs = []
    for binding in (binding_a, binding_b):
        install = Path(binding['install_root']).resolve()
        source, = [item for item in binding['source_manifest'] if item['path'] == SOURCE]
        evidence.raw(install / SOURCE, source['sha256'])
        installs.append(install)
    with ExitStack() as stack:
        archived = replay['Original'](evidence, ASSEMBLY, PRIMARY,
            'dad6c71dd614ab82f8ddfbd10f9645ff1da09e82c187b8ddac3422c9c7e1a4f0', stack)
        smaller = replay['Original'](evidence, V / 'm4_cross_scale_brief_entry_001',
            'D:/he_m4_cross_scale_brief_entry_001',
            '7625392863637b311c5c6a1921a4eaac386845e5acbcd30c452a2c1d2e385fbb', stack)
        first = archived.call(1, 'brief', 1, 3)
        prediction = archived.call(2, 'full', 0, 0)
        old_brief = smaller.call(1, 'brief', 3, 4)
        producer = archived.load(first['source'])
        measurements = inspect_pixels(archived, producer)
    cases = {'assembly_brief': first,
             'assembly_full_with_image': with_detail(first, 'full'),
             'assembly_no_image_full': prediction,
             'assembly_no_image_brief': with_detail(prediction, 'brief'),
             'fixed21_brief': old_brief,
             'fixed21_full': with_detail(old_brief, 'full')}
    for name, producer_path, digest in (
            ('source_region', 'D:/he_m4_live_source_region_task_003/slots/P1/product_full/call_001/SERVICE_RESULT.json',
             '32d1dded3fe137e611087e1e8487b732d3cede1d47a6cbe259a466eb6be5b9c9'),
            ('ordinary_active', 'D:/he_m4_global_local_001/sessions/global/product_full/call_001/SERVICE_RESULT.json',
             '7e1c4331d7582254e985d256595dad0fdef4d98a21974b969f3cff9e97f6a112')):
        for detail in ('brief', 'full'):
            cases[f'{name}_{detail}'] = compatibility_source(evidence, producer_path, digest, detail)
    baseline, candidate = [replay['run_formatter'](install, dependency, cases.values()) for install in installs]
    require(baseline['tool_catalogues'] == candidate['tool_catalogues'], 'actual_tool_catalogue_changed')
    checker_file = V / 'm1_source_region_facts_first_001/checks/client_budget_replay.py'
    policy_file = checker_file.with_name('CLIENT_BUDGET_REVIEW.json')
    evidence.raw(checker_file, '8a59abf2ccdaba3013c7ef3e8180265a3311ca3d5039f8af86b679252be08f4a')
    policy = json.loads(evidence.raw(policy_file,
        '0e90ad3df1f74a1977d96b212bd7592e11cdbc4e285a80213a25745fedc57ae8'))['policy']
    checker = runpy.run_path(str(checker_file))
    outcomes = {}
    for (name, case), old, new in zip(cases.items(), baseline['results'], candidate['results'], strict=True):
        if name in ('assembly_brief', 'assembly_no_image_full', 'fixed21_brief'):
            expected_call(case, old)
        reference, actual = old['result'], new['result']
        require(old['work'] == new['work'] == case['work']
                and reference['content'][1:] == actual['content'][1:] and actual['isError'] is False,
                'producer_work_or_native_images_changed/' + name)
        shortfall = None
        if name == 'assembly_brief' and not baseline_only:
            shortfall = verify_shortfall(reference, actual, measurements)
        else:
            require(reference == actual, 'out_of_scope_text_or_images_changed/' + name)
        old_text, new_text = (item['content'][0]['text'] for item in (reference, actual))
        row = {'original_text_UTF8_bytes': len(old_text.encode()), 'candidate_text_UTF8_bytes': len(new_text.encode()),
               'candidate_added_UTF8_bytes': len(new_text.encode()) - len(old_text.encode()),
               'native_images': len(actual['content']) - 1, 'producer_rasters': case['work']['raster_attempts']}
        if name in ('assembly_brief', 'fixed21_brief'):
            row['CLI_budget'] = replay['verify_cli'](checker, policy, actual)
            row['native_image_indexes'] = replay['verify_images'](json.loads(new_text), actual)
        if shortfall is not None:
            row['new_shortfall'] = shortfall
        outcomes[name] = row
    negative = {} if baseline_only else control_process(installs[1], dependency, first['source'])
    record = {'schema': 'm4-cross-scale-pixel-evidence-offline-v1', 'passed': True, 'baseline_only': baseline_only,
              'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
              'baseline_formatter_sha256': baseline['sha256'], 'candidate_formatter_sha256': candidate['sha256'],
              'original_png_npz_recomputed': measurements, 'cases': outcomes, 'controls': negative,
              'source_pins': sorted(evidence.pins.values(), key=lambda obj: obj['path'])}
    if output is not None:
        with output.open('x', encoding='utf8', newline='\n') as sink:
            json.dump(record, sink, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
            sink.write('\n')
    print('Pixel evidence replay passed:', [(name, row['candidate_added_UTF8_bytes'])
                                              for name, row in outcomes.items()])


def with_detail(case, detail):
    return {**case, 'arguments': {**case['arguments'], 'response_detail': detail}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'PIXEL_CONTROLS.json')
    parser.add_argument('--precheck-base', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_python_I_B')
    run_checks(None if args.precheck_base else args.output, args.precheck_base)


if __name__ == '__main__':
    main()
