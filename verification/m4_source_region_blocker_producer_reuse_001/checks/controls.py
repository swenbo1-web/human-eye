"""Verify current producer reuse and object-local addresses through both MCP installations."""

import argparse
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from threading import Event, Thread
from time import perf_counter_ns


NS = Path(__file__).resolve().parents[1]
V = NS.parent
PRIOR = V / 'm4_source_region_blocker_brief_001'
BASE = PRIOR / 'install/PRODUCT_RUN_BINDING.json'
BASE_COMMIT = '66f1a39601fdec1e7bbf5f23157086fe18d9a753'
CURRENT_NAMES = {'active', 'matching', 'missing_observation', 'missing_region', 'absent', 'stale',
                 'evicted', 'lock', 'derived_self', 'derived_last', 'copied_generation'}


def authored_variant(old, kind, capture, request, source_region, active_host, replay):
    """Prepare independent derived topology and exact attempts without manufacturing a fresh image."""
    original_generation = deepcopy(capture['capture_state'])
    capture['capture_state']['revision'] += 1
    capture['revision'] += '/derived/' + kind
    owner_index = 2 if kind == 'derived_self' else 8
    mesh = capture['meshes'][owner_index]
    if kind == 'derived_self':
        index = len(mesh['vertices'])
        small = 2**-20
        mesh['vertices'].extend([[2, 2, 1.125], [2 + small, 2, 1.125], [2, 2 + small, 1.125]])
        mesh['faces'].append([index, index + 1, index + 2])
        expected_face, area = 2, '1/2199023255552'
    else:
        # Retain the eight original nonblocking TOP faces and put original face 0 last.
        # Three more nonblocking rows keep the original object-local count at twelve.
        faces = mesh['faces']
        mesh['faces'] = faces[4:] + [faces[11], faces[10], faces[9], faces[0]]
        expected_face, area = 11, '1/128'
    prepared, selected = replay['prepare'](source_region, active_host, capture, request)
    region = source_region._selected_rectangle(prepared)
    check = lambda _phase: None
    triangles = source_region._displayed_front_triangles(prepared, region, check)
    attempts = [
        {'view_name': pose['name'], **source_region._classify_view(region, triangles, pose, check),
         'constructed': pose['name'] == 'SCENE'} for pose in prepared.cameras['views']
    ]
    top, = [row for row in attempts if row['view_name'] == 'TOP']
    wanted = {'object_index': owner_index, 'source_triangle_index': expected_face,
              'overlap_area_screen_exact': area}
    replay['require'](top['status'] == 'positive_area_occlusion' and top['first_blocker'] == wanted
                      and len(prepared.meshes[owner_index].faces) == expected_face + 1,
                      'independent_authored_topology_control_disagrees/' + kind)
    # Original bytes are a transport fixture, never pixel evidence for this derived geometry.
    frame, = old['frames']
    frame.update(scene_identity=prepared.binding['geometry_identity'], candidate_identity=prepared.binding['camera_identity'],
                 host_binding_sha256=prepared.binding['binding_sha256'], source_revision=prepared.binding['scene_revision'],
                 all_triangle_count=sum(len(item.faces) for item in prepared.meshes))
    frame['frame_identity'] = source_region.fingerprint((kind, prepared.binding['binding_sha256'], frame['image_sha256']))
    frame['image_ref'] = 'source-region-image:' + source_region.fingerprint((
        prepared.region_ref['region_id'], frame['frame_identity'], frame['image_sha256']))
    attempts[0].update(sample_only=True, frame_identity=frame['frame_identity'], selected_surface_pixels=0)
    visibility = old['facts']['visibility']
    visibility.update(geometry_status=attempts[0]['status'], frame_identity=frame['frame_identity'], image_ref=frame['image_ref'])
    old['binding'] = {**prepared.binding, **{key: old['binding'][key] for key in replay['OVERLAYS'] if key in old['binding']}}
    old['task_result'].update(region_ref=deepcopy(prepared.region_ref), binding=deepcopy(old['binding']))
    old.update(region_ref=deepcopy(prepared.region_ref), constructed_frames=[deepcopy(frame)], view_attempts=attempts)
    rows = [[item['view_name'], item['first_blocker']['object_index'], item['first_blocker']['source_triangle_index']]
            for item in attempts if item['status'] == 'positive_area_occlusion']
    proof = {'source': 'separately prepared derived capture; archived PNG is transport fixture only',
             'original_generation': original_generation, 'derived_generation': capture['capture_state'],
             'producer_and_return_match': True, 'mesh_faces': len(prepared.meshes[owner_index].faces),
             'occluder_TOP': wanted, 'region_ref': prepared.region_ref, 'binding_sha256': prepared.binding['binding_sha256']}
    return prepared, selected, rows, proof


def specifications(prior, source_region):
    cases, pins, geometry = prior['build_cases'](source_region)
    rows = prior['ORIGINAL_ROWS']
    top_removed = [row for row in rows if row[0] != 'TOP']
    source = cases['actual_P1_4_blockers']
    for name, case in cases.items():
        case['A'] = case['expected']
        case['B'] = rows if name in ('actual_P1_4_blockers', 'omitted_brief_default', 'unknown_measurement_preserved') else None
        case['state'] = 'active'
    prior_wire_count = len(cases)

    def variant(name, state='active', *, mutate=None, a=rows, b=None):
        case = deepcopy(source)
        case.update(state=state, A=a, B=b, is_unmodified_archived_call=False)
        if mutate is not None:
            mutate(case['producer'])
        cases[name] = case

    for face in (-1, 12, 55, 56):
        a = [rows[0], ['TOP', 8, face], *rows[2:]] if 0 <= face < 56 else top_removed
        for state in ('active', 'matching'):
            variant(f'Obj03_TOP_face_{face}_{state}', state,
                    mutate=lambda result, face=face: result['view_attempts'][1]['first_blocker'].update(
                        source_triangle_index=face), a=a, b=top_removed if state == 'matching' else None)
    variant('Obj06_TOP_face2_in_matching_two_face_producer', 'matching',
            mutate=lambda result: result['view_attempts'][1]['first_blocker'].update(object_index=2, source_triangle_index=2),
            a=[rows[0], ['TOP', 2, 2], *rows[2:]], b=top_removed)
    for name in ('wrong_object_index', 'bool_is_not_source_index',
                 'same_object_selected_face_does_not_certify', 'duplicate_angle', 'wrong_angle_order',
                 'contradictory_depth_tie_untrusted', 'invalid_exact_area'):
        inherited = deepcopy(cases[name])
        inherited.update(state='matching', B=inherited['A'])
        cases['matching_retained_' + name] = inherited
    for state in ('missing_observation', 'missing_region', 'absent', 'stale', 'evicted', 'lock',
                  'derived_self', 'derived_last', 'copied_generation'):
        variant(state, state)
    # Old metadata checks did not compare an unconstructed TOP attempt's identity.
    variant('nonprimary_TOP_attempt_wrong_frame',
            mutate=lambda value: value['view_attempts'][1].update(frame_identity='0' * 64))
    variant('returned_TOP_area_edited_but_still_positive',
            mutate=lambda value: value['view_attempts'][1]['first_blocker'].update(overlap_area_screen_exact='1/256'))
    variant('returned_constructed_frames_edited',
            mutate=lambda value: value['constructed_frames'].append(deepcopy(value['constructed_frames'][0])), a=None)
    return cases, pins, geometry, prior_wire_count


def run_worker(binding_path, output, arm):
    prior = run_path(str(PRIOR / 'checks/controls.py'))
    replay = run_path(str(Path(__file__).with_name('prepared_replay.py')))
    read, require, pin = prior['read'], prior['require'], prior['pin']
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import active_observation_host, live_spatial_mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == binding['source_sha256']
            and Path(live_spatial_mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'wrong_isolated_runtime')
    require((arm == 'A') == (binding['preparation_git'] == BASE_COMMIT), 'source_binding_arm_mismatch')
    output.mkdir(parents=True)
    cases, sources, geometry, prior_wire_count = specifications(prior, source_region)
    actual = cases['actual_P1_4_blockers']['fixture']
    capture, capture_pins = replay['frozen_capture']()

    class ReplayService:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)
        _matching_source_region_producer = getattr(LiveSpatialService, '_matching_source_region_producer', None)
        _source_region_blocker_rows = getattr(LiveSpatialService, '_source_region_blocker_rows', None)
        _source_region_sample_path = getattr(LiveSpatialService, '_source_region_sample_path', None)

        def __init__(self, case):
            self.case = case
            self.state_path = case['fixture'].state
            self._read_context = ReadContext()
            self.observations = 0
            self.closed = False
            self.budgets, self.deliveries = [], []
            self.proof = None
            if case['fixture'].state != actual.state:
                return
            state, value = case['state'], case['producer']
            require(state in CURRENT_NAMES, 'unexpected_replay_state')
            if state == 'absent':
                return
            if state in ('derived_self', 'derived_last'):
                derived_capture = deepcopy(capture)
                prepared, selection, rows, self.proof = authored_variant(
                    value, state, derived_capture, case['request'], source_region, active_observation_host, replay)
                replay['register'](self._read_context, derived_capture, selection, prepared,
                                   replay['original_observation'](value))
                case['A'] = case['B'] = rows
                return
            retained = value if state == 'matching' else None
            prepared = replay['restore'](source_region, active_observation_host, self._read_context,
                                         actual.request, actual.producer, retained=retained)
            context = self._read_context
            if state == 'missing_observation':
                prepared.observation = None
            elif state == 'missing_region':
                context.current_prepared('source_regions')['regions'].clear()
            elif state == 'stale':
                changed = {'capture_state': {**capture['capture_state'], 'revision': capture['capture_state']['revision'] + 1}}
                context.activate(changed, 'source_region')
                require(context.current_prepared('source_regions') is None, 'old_capture_remained_current')
            elif state == 'evicted':
                for i in range(8):
                    context.activate(capture, 'source_region', {'another_selection': i})
                _, original_selection = replay['prepare'](source_region, active_observation_host, capture, actual.request)
                context.activate(capture, 'source_region', original_selection)
                require(context.current_prepared('source_regions') is None, 'old_selection_not_evicted')
            elif state == 'copied_generation':
                frame = value['frames'][0]
                source = Path(frame['image_path'])
                root = output.parent / 'copied_generation' / ('f' * 32)
                root.mkdir(parents=True, exist_ok=True)
                clone = root / source.name
                if not clone.exists():
                    clone.write_bytes(source.read_bytes())
                require(clone.read_bytes() == source.read_bytes(), 'copy_fixture_image_sha_changed')
                frame['image_path'] = str(clone)
                value['constructed_frames'][0]['image_path'] = str(clone)

        def observe(self, _session, **kwargs):
            args = self.case['request']['params']['arguments']
            require(kwargs['query'] == args['query'] and kwargs.get('include_image', True) == args.get('include_image', True),
                    'actual_observe_arguments_changed')
            self.observations += 1
            require(self.case['producer'] is not None, 'error_fixture_reached_observe')
            return deepcopy(self.case['producer'])

        def _check_request_budget(self, phase, *, publication=False):
            self.budgets.append((phase, publication))

        def record_event(self, event, **data):
            if event in ('source_region_mcp_content', 'active_observation_mcp_content'):
                self.deliveries.append(data['image_delivery'])

        def close(self):
            self.closed = True

    results = {}
    for name, case in cases.items():
        service = ReplayService(case)
        locked, release = Event(), Event()

        def hold_lock():
            with service._read_context.lock:
                locked.set()
                release.wait(5)

        locker = Thread(target=hold_lock) if case['state'] == 'lock' else None
        if locker is not None:
            locker.start()
            require(locked.wait(5), 'real_concurrent_read_lock_not_held')
        incoming = json.dumps(case['request'], ensure_ascii=False) + '\n'
        outgoing = StringIO(newline='\r\n')
        try:
            started = perf_counter_ns()
            live_spatial_mcp.run_stdio_mcp_server(service, input_stream=StringIO(incoming), output_stream=outgoing)
            elapsed = perf_counter_ns() - started
            require(locker is None or elapsed < 1_000_000_000, 'contention_blocked_publication')
        finally:
            release.set()
            if locker is not None:
                locker.join()
        tx, rx = output / (name + '_TX.bin'), output / (name + '_RX.bin')
        tx.write_bytes(incoming.encode())
        wire = outgoing.getvalue().encode()
        rx.write_bytes(wire)
        reply = json.loads(wire)
        require(service.closed and reply['id'] == case['request']['id']
                and service.observations == case['observations'], 'MCP_alignment_or_EOF_changed/' + name)
        failed = 'error' in reply or reply['result']['isError']
        require(failed == case['error'], 'wrong_expected_error/' + name)
        text = reply['result']['content'][0]['text']
        body = json.loads(text)
        if failed:
            require(body['error'] == prior['EXPECTED_ERRORS'][name], 'wrong_expected_error_reason/' + name)
        table = body.pop('blocker_evidence', None) if case['fixture'].state == actual.state else None
        expected = case[arm]
        require(table is None or isinstance(table, dict) and table['columns'] == prior['TABLE_COLUMNS'],
                'blocker_columns_changed/' + arm + '/' + name)
        actual_rows = table['rows'] if table is not None else None
        normal = deepcopy(reply)
        normal['result']['content'][0]['text'] = json.dumps(body, ensure_ascii=False)
        normalized = output / (name + '_normalized.json')
        prior['write'](normalized, normal)
        producer = output / (name + '_INPUT_PRODUCER.json')
        if case['fixture'].state == actual.state and not case['is_unmodified_archived_call']:
            prior['write'](producer, case['producer'])
        results[name] = {'rows': actual_rows, 'expected_rows': expected, 'matches_expected': actual_rows == expected,
                         'TX': pin(tx), 'RX': pin(rx), 'without_table': pin(normalized),
                         'input_producer': pin(producer) if producer.exists() else None, 'body_bytes': len(text.encode()),
                         'state': case['state'], 'derived_proof': service.proof, 'EOF': service.closed,
                         'observation_calls': service.observations, 'budget': service.budgets,
                         'stdio_elapsed_ns': elapsed, 'error_reason': body['error'] if failed else None}
    prior['write'](output / 'REPLAY.json', {
        'binding': pin(binding_path), 'runtime': identity, 'rows': results, 'inherited_case_count': prior_wire_count,
        'original_capture_inputs': capture_pins, 'original_sources': sources, 'inherited_geometry_controls': geometry})


def compare(left, right, require):
    require(left['rows'].keys() == right['rows'].keys()
            and left['original_capture_inputs'] == right['original_capture_inputs'], 'replay_case_or_source_changed')
    outcomes = {}
    for name, a in left['rows'].items():
        b = right['rows'][name]
        require(a['TX']['sha256'] == b['TX']['sha256'] and a['without_table']['sha256'] == b['without_table']['sha256']
                and a['budget'] == b['budget'],
                'dispatch_body_or_images_changed/' + name)
        wire_equal = a['RX']['sha256'] == b['RX']['sha256']
        require(wire_equal == (a['rows'] == b['rows']), 'unrelated_wire_changes/' + name)
        outcomes[name] = {'wire_identical': wire_equal, 'rows_A_B': [a['rows'], b['rows']],
                          'expected_rows_A_B': [a['expected_rows'], b['expected_rows']],
                          'passed': a['matches_expected'] and b['matches_expected'],
                          'body_bytes_A_B': [a['body_bytes'], b['body_bytes']],
                          'wire_sha256_A_B': [a['RX']['sha256'], b['RX']['sha256']],
                          'derived_proof': b['derived_proof'], 'error_reason': b['error_reason']}
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--arm', choices=('A', 'B'))
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    if args.worker:
        run_worker(args.worker, args.output, args.arm)
        return
    prior = run_path(str(PRIOR / 'checks/controls.py'))
    args.output.mkdir(parents=True)
    bindings = {'A': BASE}
    if args.candidate is not None:
        bindings['B'] = args.candidate
    reports = {}
    for arm, source in bindings.items():
        dest = args.output / arm
        worker = subprocess.run([
            sys.executable, '-I', str(Path(__file__).resolve()), '--worker', str(source.resolve()),
            '--arm', arm, '--output', str(dest.resolve())], capture_output=True, check=False)
        (args.output / (arm + '_STDERR.txt')).write_bytes(worker.stderr)
        prior['require'](worker.returncode == 0, '{} worker failed: {}'.format(arm, worker.stderr.decode(errors='replace')))
        reports[arm] = prior['read'](dest / 'REPLAY.json')
    if 'B' not in reports:
        print(json.dumps({'A_cases': len(reports['A']['rows']), 'report': str(args.output / 'A/REPLAY.json')}))
        return
    outcomes = compare(reports['A'], reports['B'], prior['require'])
    passed = sum(row['passed'] for row in outcomes.values())
    summary = {'passed': passed, 'planned': len(outcomes),
               'not_as_expected': [name for name, row in outcomes.items() if not row['passed']],
               'inherited': reports['A']['inherited_case_count'],
               'byte_identical': sum(row['wire_identical'] for row in outcomes.values()),
               'source_A_B': [arm['runtime']['source_sha256'] for arm in reports.values()],
               'raw_replays': [prior['pin'](args.output / (arm + '/REPLAY.json')) for arm in reports],
               'outcomes': outcomes}
    prior['write'](args.output / 'CONTROLS.json', summary)
    if args.summary:
        prior['write'](args.summary, summary)
    print(json.dumps({'passed': passed, 'planned': len(outcomes), 'report': str(args.output / 'CONTROLS.json')}))


if __name__ == '__main__':
    main()
