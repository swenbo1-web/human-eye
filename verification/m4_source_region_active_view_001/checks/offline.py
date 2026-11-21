"""Qualify one source-region candidate with original and local negative fixtures."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import (ASSET, BASE, CANDIDATE, CAPTURE, HERE, LEGACY_WIRE, PILOT, PILOT_P,
                      POLICY, POSITIVE, TOP, TOPOLOGY, Originals, canonical, digest, frame_metrics,
                      load_install, parse_public, pin, pilot_source, read, region_and_geometry,
                      replay_cli, require, save)


def frame_summary(value):
    return {key: val for key, val in value.items() if key not in ('PNG', 'NPZ', 'pose')}


def time_ms(started):
    return round((time.perf_counter_ns() - started) / 1e6, 6)


def capture_on_base(path):
    binding = load_install(BASE)
    with Originals() as originals:
        pilot = pilot_source(binding, originals)
        target, visibility, distance = region_and_geometry(pilot['terminal'])
        baseline = frame_metrics(pilot['producer']['frames'][0], pilot['producer'], originals.member, PILOT_P)
        historic_body, _ = parse_public(pilot['response'], baseline)
        require((baseline['surface'], baseline['contrast']) == (0, 0) and
                historic_body['observation_status'] == 'evidence_insufficient' and
                historic_body['visibility']['complete_witness'] is None,
                'original_source_region_negative_changed')
        pilots_paths = list(originals.pins.values())
    result = {'capture': pilot['capture'], 'request': pilot['request']['params']['arguments'],
              'archived_baseline_measure': pilot['producer']['task_result'], 'target': target,
              'visibility': visibility, 'independent_axis_distance': distance,
              'baseline_scene': frame_summary(baseline), 'baseline_cli': replay_cli(pilot['response']),
              'source_pins': pilots_paths}
    save(path, result)


def image_engine(prep, folder):
    from human_eye_plugin.active_observation_images import SceneObservationImages

    return SceneObservationImages(prep.objects, prep.cameras, folder,
        scene_identity=prep.binding['geometry_identity'], candidate_identity=prep.binding['camera_identity'],
        display_identity=prep.binding['display_identity'], object_mask=tuple(prep.binding['image_scope']['participation_mask']),
        image_scope=prep.binding['image_scope'], _prepared_meshes=prep.meshes, _measure_stages=True,
        _reuse_published_payload=True)


def baseline_replay(value, output):
    from human_eye_plugin.source_region import prepare_region

    started = time.perf_counter_ns()
    prep = prepare_region(value['capture'], value['request']['query'])
    source = {'facts': {'region': prep.region_facts}, 'binding': prep.binding}
    engine = image_engine(prep, output.parent / 'baseline')
    checks = {}
    for view in ('SCENE', 'TOP', 'RIGHT'):
        frame = engine.render_view(view)
        frame.update(host_binding_sha256=prep.binding['binding_sha256'], source_revision=prep.binding['scene_revision'],
                     image_ref='offline-reference:' + view)
        checks[view] = frame_summary(frame_metrics(frame, source))
    require(checks['SCENE']['array_sha256'] == value['baseline_scene']['array_sha256'] and
            checks['SCENE']['PNG_sha256'] == value['baseline_scene']['PNG_sha256'],
            'baseline_raw_replay_does_not_match_archive_bitwise')
    require((checks['TOP']['surface'], checks['TOP']['contrast']) == TOP and
            (checks['RIGHT']['surface'], checks['RIGHT']['contrast']) == POSITIVE and
            checks['RIGHT']['different_owner_contrast'] == 1115 and checks['RIGHT']['same_owner_contrast'] > 0,
            'same_source_TOP_or_RIGHT_threshold_truth_changed')
    return {'independent_frames': checks, 'elapsed_ms': time_ms(started)}


def display(capture, visible):
    adjusted = deepcopy(capture)
    ids = {mesh['object_id'] for mesh in adjusted['meshes'] if mesh['name'] in visible}
    snapshot = adjusted['display_snapshot']
    for row in snapshot['objects']:
        row['visible_get'] = row['host_id'] in ids
        row['hide_get'] = not row['visible_get']
    snapshot.pop('sha256')
    snapshot['sha256'] = digest(canonical(snapshot))
    return adjusted


def screen(capture, tied):
    """Large plate above the subject, or a same-depth duplicate target."""
    change = display(capture, {'N15', 'N23'})
    mesh = next(row for row in change['meshes'] if row['name'] == 'N23')
    target = next(row for row in change['meshes'] if row['name'] == 'N15')
    corners = [target['vertices'][index] for index in (2, 10, 11, 3)]
    if tied:
        mesh.update(vertices=corners, faces=[[0, 1, 2], [0, 2, 3]], edges=[[0, 1], [1, 2], [2, 3], [3, 0], [0, 2]])
    else:
        vertices = [[a, b, .75] for a, b in ((-2, -2), (2, -2), (2, 2), (-2, 2))]
        mesh.update(vertices=vertices, faces=[[0, 1, 2], [0, 2, 3]], edges=[[0, 1], [1, 2], [2, 3], [3, 0], [0, 2]])
    return change


def observed(capture, query, folder, *, include_image=True):
    from human_eye_plugin.source_region import observe_region, prepare_region

    safe = prepare_region(capture, query)
    callbacks = []
    result = observe_region(safe, folder, include_image=include_image, construction_callback=callbacks.append)
    return safe, result, callbacks


def case(result, callbacks):
    return {'construction_callback_views': callbacks, 'raster_attempts': result['work']['raster_attempts'],
            'raster_completed': result['work']['raster_completed'], 'frames': len(result['frames']),
            'frame_reuses': result['work']['frame_reuses'], 'visibility': result['facts']['visibility'],
            'stages': result['stages']}


def measurement_contract(new, old):
    for key in ('schema', 'status', 'region_ref', 'reference', 'measurement_scope', 'facts', 'source_mapping',
                'read_only', 'execution_authority'):
        require(old[key] == new[key], 'source_measurement_changed/' + key)


def candidate_replay(value, output, candidate):
    from human_eye_plugin.live_spatial_mcp import _tool_result
    from human_eye_plugin.source_region import measure_region, observe_region, prepare_region

    prep, cold, callbacks = observed(value['capture'], value['request']['query'], output.parent / 'candidate')
    visibility = cold['facts']['visibility']
    require(callbacks == ['TOP', 'RIGHT'] and cold['work']['raster_attempts'] == cold['work']['raster_completed'] == 2
            and len(cold['frames']) == 1 and visibility['complete_witness'] is not None,
            'new_selected_rectangle_did_not_skip_proven_blockers_and_stop_on_RIGHT')
    chosen = frame_metrics(cold['frames'][0], cold)
    witness = visibility['complete_witness']
    require((chosen['surface'], chosen['contrast']) == POSITIVE and
            chosen['corners_inside_clip'] and chosen['visible_source_ids'] == [20, 21] and
            all(witness[key] == chosen[key] for key in ('view_name', 'image_ref', 'frame_identity')) and
            value['visibility']['RIGHT']['clear'], 'candidate_validity_not_bound_to_independent_RIGHT')
    require(chosen['array_sha256'] == value['baseline_replay']['independent_frames']['RIGHT']['array_sha256'],
            'candidate_alternate_frame_array_bytes_changed')
    warm_calls = []
    warm = observe_region(prep, output.parent / 'candidate', include_image=True, construction_callback=warm_calls.append)
    require(not warm_calls and warm['work']['frame_reuses'] == 1 and warm['work']['raster_attempts'] == 0 and
            warm['facts'] == cold['facts'] and warm['frames'] == cold['frames'],
            'same_prepared_region_reuse_did_not_preserve_single_frame')
    measure = measure_region(prep, value['request']['query']['reference'], None)
    measurement_contract(measure, value['archived_baseline_measure'])
    cold['task_result'] = measure
    legacy_status = {key: value['archived_baseline_measure']['binding'][key]
                     for key in ('source_status', 'disk_status', 'source_check_scope')}
    cold['binding'].update(**legacy_status, runtime_source_sha256=candidate['source_sha256'])
    cold['session_id'] = 'mcp-00000000-0000-0000-0000-000000000000'
    public = _tool_result(cold, is_error=False, response_detail='brief')
    body, raw = parse_public(public, chosen)
    require(raw == Path(chosen['PNG']).read_bytes(), 'candidate_formatter_did_not_preserve_original_PNG')
    cli = replay_cli(public)
    require(cli['passed'], 'candidate_public_positive_exceeds_fixed_CLI_budget')
    full = _tool_result(cold, is_error=False, response_detail='full')
    require(len(full['content']) == 2 and json.loads(full['content'][0]['text'])['region_ref'] == prep.region_ref,
            'existing_full_and_only_one_native_PNG_contract_changed')

    first_cases = {}
    no_prepare, no_image, calls = observed(value['capture'], value['request']['query'],
                                           output.parent / 'no_image', include_image=False)
    require(no_prepare.images is None and not calls and no_image['work']['raster_attempts'] == 0 and
            no_image['facts']['visibility']['reason'] == 'image_not_requested' and not no_image['frames'] and
            not any('view_selection' in stage for stage in no_image['stages']),
            'no_image_request_did_new_view_work')
    first_cases['no_image'] = case(no_image, calls)
    for label, capture in (
            ('first_SCENE_hidden_blocker', display(value['capture'], {'N15'})),
            ('selected_hidden', display(value['capture'], {'N23'})),
            ('all_front_blocked', screen(value['capture'], False)),
            ('equal_depth', screen(value['capture'], True))):
        _, result, calls = observed(capture, value['request']['query'], output.parent / label)
        actual = result['facts']['visibility']
        if label == 'first_SCENE_hidden_blocker':
            require(calls == ['SCENE'] and len(result['frames']) == 1 and actual['complete_witness'] is not None,
                    'first_SCENE_visibility_or_hidden_participation_not_respected')
        else:
            require(actual['complete_witness'] is None, 'unsupported_positive/' + label)
            require(len(result['frames']) <= 1 and (not result['frames'] or actual['image_ref'] ==
                    result['frames'][0]['image_ref']), 'partial_frame_binding/' + label)
        first_cases[label] = case(result, calls)

    for label, selected in [('nonrect', [20]), ('mixed', [20, 21, 22])]:
        query = deepcopy(value['request']['query'])
        query['region']['source_triangle_indices'] = selected
        _, result, calls = observed(value['capture'], query, output.parent / label)
        require(calls == ['SCENE'] and len(result['frames']) == 1 and
                result['facts']['visibility']['complete_witness'] is None and
                result['region_ref']['source_triangle_indices'] == selected, 'nonrectangle_legacy_path_changed/' + label)
        first_cases[label] = case(result, calls)

    class Expired(Exception):
        pass

    for control in ('budget', 'deadline'):
        ready = prepare_region(value['capture'], value['request']['query'])
        used = []
        reasons = []

        def reserve(view):
            used.append(view)
            if control == 'budget' and len(used) == 2:
                raise Expired('registered_frame_budget_denied')

        def deadline(stage):
            reasons.append(stage)
            if control == 'deadline' and used and (stage == 'source_region_after_frame' or len(used) == 2):
                raise Expired('original_simulated_deadline')

        try:
            observe_region(ready, output.parent / control, include_image=True,
                           construction_callback=reserve, check_budget=deadline)
        except Expired as exc:
            require(ready.observation is None, 'aborted_observation_entered_reuse_cache')
            first_cases[control] = {'callback_views': used, 'last_stage': reasons[-1], 'reason': str(exc)}
        else:
            raise ValueError('bounded_failure_not_propagated/' + control)

    source_change = deepcopy(value['capture'])
    source_change['capture_state']['revision'] += 1
    stale_query = {'region_ref': prep.region_ref}
    try:
        prepare_region(source_change, stale_query)
    except ValueError as exc:
        require(str(exc) == 'source_region_ref_capture_generation_changed', 'wrong_stale_ref_rejection')
        first_cases['stale_region_ref'] = {'reason': str(exc)}
    else:
        raise ValueError('old_region_ref_accepted_in_new_generation')

    return {'candidate_first': case(cold, callbacks), 'candidate_warm': case(warm, warm_calls),
            'independent_selected_frame': frame_summary(chosen), 'public_scope_schema': body['schema'],
            'candidate_cli': cli, 'measurement_scope': measure['measurement_scope'],
            'measurement_fact': measure['facts']['surface_proximity'], 'controls': first_cases}


def worker(mode, input_path, output, install_path):
    if mode == 'extract':
        capture_on_base(output)
        return
    install = load_install(install_path)
    value = read(input_path)
    result = baseline_replay(value, output) if mode == 'baseline' else candidate_replay(value, output, install)
    save(output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=CANDIDATE)
    parser.add_argument('--output', type=Path, default=HERE / 'OFFLINE.json')
    parser.add_argument('--worker', choices=('extract', 'baseline', 'candidate'))
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_interpreter_required')
    if args.worker:
        worker(args.worker, args.input, args.output, args.candidate)
        return
    start = time.perf_counter_ns()
    with TemporaryDirectory(prefix='he_m4_source_region_active_view_') as tmp:
        root = Path(tmp)
        paths = [root / name for name in ('source.json', 'baseline.json', 'candidate.json')]
        for mode, path, install in zip(('extract', 'baseline', 'candidate'), paths,
                                       (BASE, BASE, args.candidate), strict=True):
            subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker', mode,
                            '--input', str(paths[0]), '--output', str(path), '--candidate', str(install)],
                           timeout=150, check=True)
            if mode == 'baseline':
                value = read(paths[0])
                value['baseline_replay'] = read(path)
                paths[0].write_bytes(canonical(value))
        source, baseline, candidate = map(read, paths)
    extras = [Path(__file__), HERE / 'evidence.py', BASE, args.candidate, CAPTURE, TOPOLOGY, POLICY, LEGACY_WIRE,
              PILOT / 'truth/oracle.py', PILOT / 'truth/TRUTH.json', PILOT / 'RUNTIME_INDEX.json']
    pins = {row['path']: row for row in [*source['source_pins'], *(pin(path) for path in extras)]}
    result = {'schema': 'm4-source-region-active-view-offline-v1', 'asset_sha256': ASSET, 'passed': True,
              'new_model_runs': 0, 'new_Blender_starts': 0, 'elapsed_ms': time_ms(start),
              'real_original_request': source['request'], 'registered_baseline_camera': source['baseline_scene'],
              'baseline_CLI': source['baseline_cli'], 'independent_exact_visibility': source['visibility'],
              'same_installed_renderer_replayed': baseline, **candidate,
              'source_pins': [pins[path] for path in sorted(pins)]}
    print('Offline source-region proof', save(args.output, result))


if __name__ == '__main__':
    main()
