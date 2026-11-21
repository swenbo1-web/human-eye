"""Replay scoped compatibility and fixed client loss for the joint-full tail change."""

import argparse
import base64
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile


DENSE = ('perf050_dense_pair_transfer_001', 'P1', 1)
M09 = ('perf050_target_observation_first_image_p2', 'P2', 1)
SOURCE = ('perf050_source_region_final_image_p3', 'P3', 2)
REGION_FOUR = ('perf050_source_region_active_view_p2', 'P2', 3)
BAD_M09 = ('perf050_target_observation_first_image_p2', 'P2', 2)
BEFORE = '0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147'
AFTER_REVISION = '475ae93a0'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


class Fixture:
    """Use only source and request members verified against each real closed ZIP."""

    def __init__(self, v, spec, invalid=False):
        namespace, label, ordinal = spec
        index = v / namespace / 'RUNTIME_INDEX.json'
        info = read(index)
        archive = Path(info['archive']['path'])
        self.pins = [pin(index), pin(archive)]
        require(self.pins[-1]['sha256'] == info['archive']['sha256'], 'archive_digest_differ')
        slot = f'slots/{label}'
        path = f'{slot}/product_calls/call_{ordinal:03}'
        self.slot = archive.parent / slot
        self.state = self.slot / 'product_state.json'
        entries = {x['path']: x for x in info['files']}
        with ZipFile(archive) as z:
            require(set(z.namelist()) == set(entries) and len(entries) == info['count'], 'archive_roster_differ')

            def take(path):
                item = entries[path]
                raw = z.read(path)
                file = archive.parent / path
                require(digest(raw) == item['sha256'] and len(raw) == item['bytes']
                        and raw == file.read_bytes(), 'frozen_member_differ/' + path)
                self.pins.append({'path': str(file.resolve()), 'bytes': len(raw), 'sha256': item['sha256']})
                return raw

            self.request = json.loads(take(f'{path}/REQUEST.json'))
            self.original = json.loads(take(f'{path}/RESPONSE.json'))
            calls = [json.loads(row) for row in take(f'{slot}/PUBLIC_REQUESTS.jsonl').splitlines()]
            match, = [row for row in calls if row['index'] == ordinal and row['request'] == self.request]
            self.inner = f"{slot}/mcp/rpc_{match['receipt']['index']:02}"
            self.original_inner = take(f'{self.inner}/RX.bin')
            require(json.loads(take(f'{self.inner}/TX.bin')) == self.request
                    and json.loads(self.original_inner) == self.original
                    and digest(self.original_inner) == match['receipt']['RX_sha256'],
                    'actual_historical_inner_request_or_reply_changed')
            result = json.loads(take(f'{slot}/SLOT_RESULT.json'))
            require(result['status'] == 'completed' and result['closure_verification']['passed'],
                    'frozen_original_slot_not_completed_and_closed')
            self.producer = None
            if invalid:
                require(self.original['result']['isError'] and not match.get('producer_archive'),
                        'planned_invalid_fixture_was_not_original_reject')
                return
            require(not self.original['result']['isError'] and match.get('producer_archive'),
                    'original_public_producer_not_available')
            producer_entry = match['producer_archive']
            relative = Path(producer_entry['path']).relative_to(archive.parent).as_posix()
            data = take(relative)
            require(digest(data) == producer_entry['sha256'], 'original_producer_digest_differ')
            self.producer = json.loads(data)
            for frame in self.producer['frames']:
                data = take(Path(frame['image_path']).relative_to(archive.parent).as_posix())
                require(digest(data) == frame['image_sha256'], 'original_producer_PNG_file_changed')
            received = media(self.original['result'])
            require(received == [frame['image_sha256'] for frame in self.producer['frames']], 'original_media_order_changed')


def media(result):
    return [digest(base64.b64decode(row['data'], validate=True))
            for row in result['content'] if row['type'] == 'image']


def body(reply):
    result = reply['result']
    first = result['content'][0]
    require(first['type'] == 'text', 'expected_first_original_text_block')
    return first['text'], json.loads(first['text'])


def clone(fixture):
    return deepcopy(fixture.request), deepcopy(fixture.producer)


def plan(v):
    dense, m09, source, four = (Fixture(v, spec) for spec in (DENSE, M09, SOURCE, REGION_FOUR))
    bad = Fixture(v, BAD_M09, invalid=True)
    cases = {}

    def add(name, fixture, request, producer, move=False, target=None):
        cases[name] = (fixture, request, producer, move, target)

    add('dense_exact_full', dense, *clone(dense), True)
    add('m09_exact_full_two_images', m09, *clone(m09), True)
    four_req, four_producer = clone(four)
    add('region_task_exact_brief_four_images', four, four_req, four_producer)
    four_full = deepcopy(four_req)
    four_full['params']['arguments']['response_detail'] = 'full'
    add('region_task_explicit_full_four_images', four, four_full, four_producer)
    src_req, src_result = clone(source)
    add('source_region_exact_brief', source, src_req, src_result)
    src_full = deepcopy(src_req)
    src_full['params']['arguments']['response_detail'] = 'full'
    add('source_region_explicit_full', source, src_full, src_result)
    add('actual_malformed_refused_before_observe', bad, *clone(bad))
    for detail in (None, 'brief'):
        req, producer = clone(m09)
        args = req['params']['arguments']
        if detail is None:
            args.pop('response_detail')
        else:
            args['response_detail'] = detail
        add('default' if detail is None else detail, m09, req, producer)
    req, producer = clone(m09)
    req['params']['arguments']['query'].pop('task_query')
    producer.pop('task_result')
    add('target_full_without_measurement', m09, req, producer)
    req, producer = clone(m09)
    req['params']['arguments']['query'].pop('objects')
    producer['binding']['capture_scope'] = 'complete_scene_meshes'
    producer['task_result']['binding']['observation_source']['parent_capture_scope'] = 'complete_scene_meshes'
    add('non_target_full_synthetic_scope_control', m09, req, producer)
    req, producer = clone(m09)
    req['params']['arguments']['include_image'] = False
    producer.update(frames=[], status='predicted', observation_status='prediction_only')
    producer['facts']['observations'] = []
    add('no_image_prediction', m09, req, producer)
    for label, field, malformed in (
            ('wrong_scope', 'measurement_scope', 'selected_source_triangles'),
            ('wrong_parent', 'parent_binding_sha256', '0' * 64),
            ('wrong_parent_source', 'parent_source_binding_sha256', '0' * 64),
            ('wrong_source_schema', 'schema', 'misbound-source'),
            ('wrong_source_capture', 'capture_scope', 'selected_objects')):
        req, producer = clone(m09)
        producer['task_result']['binding']['observation_source'][field] = malformed
        add('ineligible_measurement_' + label, m09, req, producer)
    req, producer = clone(m09)
    producer['task_result']['binding'].pop('observation_source')
    add('missing_measurement_source', m09, req, producer)
    req, producer = clone(m09)
    producer['task_result']['pair_order'] = 'unordered'
    add('wrong_measurement_pair_order', m09, req, producer)
    req, producer = clone(m09)
    producer['status'] = 'error'
    add('explicit_full_error_result', m09, req, producer)
    req, producer = clone(m09)
    producer['task_result']['facts']['surface_proximity'] = {
        'status': 'unknown', 'value': None, 'reason': 'synthetic_control_unknown_measurement'}
    add('unknown_measurement_preserved', m09, req, producer, True)

    for goal in (11965, 11967, 18400):
        req, producer = clone(m09)
        # A deliberately synthetic budget stress case. Remove larger diagnostics,
        # keep the selected evidence bytes and task result, then pad one test-only
        # diagnostic member to a measured exact body length via the real serializer.
        for key in ('work', 'generation_work', 'stages', 'generation_stages', 'target_view_classifications'):
            producer.pop(key, None)
        producer['work'] = {'test_only_budget_padding': ''}
        producer['facts'] = {key: item for key, item in producer['facts'].items()
                             if key in ('regions', 'observations', 'region_evidence')}
        for key in ('objects', 'observation_target', 'camera_specification'):
            producer['binding'].pop(key, None)
        for frame in producer['frames']:
            for key in ('stages', 'feedback_stages', 'patch_roi_ids', 'patch_owner_array_bytes',
                        'patch_mapping_array_bytes', 'owner_metadata_array_bytes'):
                frame.pop(key, None)
        add(f'synthetic_two_images_body_{goal}', m09, req, producer, True, goal)
    refs = {p['path']: p for fixture in (dense, m09, source, four, bad) for p in fixture.pins}
    return cases, list(refs.values())


def invoke(service, mcp, request):
    incoming = StringIO(json.dumps(request, ensure_ascii=False) + '\n')
    outgoing = StringIO(newline='\r\n')
    mcp.run_stdio_mcp_server(service, input_stream=incoming, output_stream=outgoing)
    raw = outgoing.getvalue().encode('utf8')
    reply = json.loads(raw)
    require(reply['id'] == request['id'] and reply['jsonrpc'] == '2.0', 'mcp_public_correlation_changed')
    return raw


def save_raw(path, payload):
    with path.open('xb') as out:
        out.write(payload)
    return pin(path)


def worker(repo, install, out):
    binding = read(install)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution'
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'wrong_isolated_runtime')
    cases, pins = plan(repo / 'verification')
    outputs = {}
    out.mkdir(exist_ok=False)

    class Budgeted:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self, fixture, request, producer):
            self.fixture, self.request, self.producer = fixture, request, producer
            self.state_path = fixture.state
            self.observations = 0
            self.closed = False

        def observe(self, session, **arguments):
            self.observations += 1
            require(self.observations == 1 and self.producer is not None
                    and arguments.get('query') == self.request['params']['arguments']['query']
                    and arguments.get('include_image') is self.request['params']['arguments']['include_image'],
                    'archived_producer_dispatched_wrong_request')
            return deepcopy(self.producer)

        def _check_request_budget(self, phase, *, publication=False):
            require((phase, publication) in (('before_task_publication', False), ('before_stdio_write', True)),
                    'unexpected_publication_budget_phase')

        def close(self):
            self.closed = True

    for name, (fixture, request, producer, move, goal) in cases.items():
        if goal:
            tester = Budgeted(fixture, request, producer)
            _, base = body(json.loads(invoke(tester, mcp, request)))
            actual_base = len(json.dumps(base, ensure_ascii=False, separators=(',', ':')).encode())
            require(0 < goal - actual_base < 20000, f'synthetic_stress_fixture_size_out_of_domain/{name}/{actual_base}')
            producer['work']['test_only_budget_padding'] = 'x' * (goal - actual_base)
        service = Budgeted(fixture, request, producer)
        wire = invoke(service, mcp, request)
        reply = json.loads(wire)
        text, preserved = body(reply)
        expected_images = [] if producer is None else [frame['image_sha256'] for frame in producer['frames']]
        require(service.closed and service.observations == int(producer is not None)
                and media(reply['result']) == expected_images, 'archived_images_or_actual_stdio_close_changed/' + name)
        if producer is None:
            require(wire == fixture.original_inner, 'old_validation_rejection_byte_behavior_changed')
        elif name == 'unknown_measurement_preserved':
            require(preserved['task_result']['facts']['surface_proximity'] ==
                    producer['task_result']['facts']['surface_proximity'], 'unknown_fact_not_preserved_exactly')
        if goal:
            require(len(text.encode()) == goal, 'synthetic_body_not_at_exact_test_boundary')
        outputs[name] = {'RX': save_raw(out / (name + '_RX.bin'), wire), 'expects_tail_move': move,
                         'actual_original_same_body_and_media': reply['result'] == fixture.original['result'],
                         'images': media(reply['result']), 'body_bytes': len(text.encode()),
                         'actual_observations': service.observations, 'actual_stdio_close_verified': service.closed}
    sys.stdout.buffer.write(json.dumps({'source_sha256': identity['source_sha256'], 'outputs': outputs,
                                        'source_pins': pins}, ensure_ascii=False).encode())


def critical(path):
    if path[0] == 'task_result':
        return True
    if path[0] == 'facts':
        return len(path) > 1 and path[1] in ('regions', 'observations', 'region_evidence')
    if path[0] == 'frames' and len(path) == 3:
        return path[-1] in ('image_path', 'image_sha256', 'image_ref')
    # The distinct compact region_task vocabulary is covered in its own
    # unchanged transport control, not mistaken for ordinary frame rows.
    return path[0] in ('regions', 'witnesses', 'images', 'observations') or (
        path[0] == 'frames' and len(path) > 1 and path[1] == 'rows')


def counts(paths):
    return dict(sorted(Counter('.'.join(map(str, path[:2])) for path in paths).items()))


def limits(repo):
    helpers, policy = runpy.run_path(
        str(repo / 'verification/m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    wire_dir = repo / 'verification/m5_global_observe_measure_qualification_001/checks'
    sys.path.insert(0, str(wire_dir))
    loss = runpy.run_path(str(wire_dir / 'live_wire.py'))['omitted_paths']
    require(policy['MCP_bytes'] == 12000 and policy['history_approximate_tokens'] == 3000, 'fixed_client_limits_changed')
    return helpers, loss


def budget_rows(repo, reply):
    helpers, loss = limits(repo)
    full, _ = body(reply)
    native = media(reply['result'])
    observed = {}
    for seconds in ('0.0000', '10.0000', '100.0000'):
        original = helpers['model_items'](reply['result'], seconds)
        after = helpers['truncate_items'](original, 12000)
        history = helpers['truncate_items'](after, 3000, token_mode=True)
        stages = {}
        for label, item in [('MCP', after), ('history', history)]:
            words = [x['text'] for x in item if x['type'] == 'input_text']
            retained = words[1] if len(words) > 1 else ''
            lost = sorted({tuple(path) for path in loss(full, retained)}, key=repr)
            important = [path for path in lost if critical(path)]
            pictures = [digest(base64.b64decode(x['image_url'].split(',', 1)[1], validate=True))
                        for x in item if x['type'] == 'input_image']
            stages[label] = ({'original_image_order_preserved': pictures == native,
                              'PNG_sha256': pictures, 'body_bytes': len(retained.encode()),
                              'lost_critical_count': len(important), 'lost_critical_branches': counts(important),
                              'lost_critical_paths_sha256': digest(json.dumps(important, separators=(',', ':')).encode()),
                              'all_lost_leaf_count': len(lost), 'truncated': retained != full},
                             set(important))
        observed[len(original[0]['text'].encode())] = stages
    return observed


def recoverable_frame_reference(path, value, lost, pixels_preserved):
    if (len(path) != 3 or path[0] != 'frames' or type(path[1]) is not int
            or path[-1] not in ('image_path', 'image_ref', 'image_sha256') or not pixels_preserved):
        return None
    frame = value['frames'][path[1]]
    fields = ('image_path', 'image_ref', 'image_sha256')
    atomic = ('view_name', *fields)
    for index, observation in enumerate(value['facts'].get('observations', [])):
        original = ('facts', 'observations', index)
        if (all(frame[key] == observation[key] and original + (key,) not in lost for key in atomic)
                and not any(lost_path[:3] == original for lost_path in lost)):
            return {'lost_duplicate': list(path), 'retained_observation_values': {
                key: list(original + (key,)) for key in atomic}, 'exact_same_frame_reference': True}
    return None


def compare_budget(repo, a, b):
    past, current = budget_rows(repo, a), budget_rows(repo, b)
    _, parsed = body(b)
    rows = {}
    for header, endings in current.items():
        rows[header] = {}
        for stage, (after, b_loss) in endings.items():
            before, a_loss = past[header][stage]
            gained, newly_lost = a_loss - b_loss, b_loss - a_loss
            reused, unbound = [], []
            for path in sorted(newly_lost, key=repr):
                copy = recoverable_frame_reference(path, parsed, b_loss, after['original_image_order_preserved'])
                if copy is not None:
                    reused.append(copy)
                else:
                    unbound.append(list(path))
            rows[header][stage] = {'A': before, 'B': after,
                                   'newly_retained_critical_count': len(gained),
                                   'newly_retained_critical_branches': counts(gained),
                                   'newly_lost_critical_duplicates': reused,
                                   'newly_lost_unrecoverable_critical_paths': unbound}
    return rows


def spawn_worker(repo, binding, out):
    cmd = [sys.executable, '-IB', str(Path(__file__).resolve()), '--repo', str(repo),
           '--worker', str(binding), '--wire-dir', str(out)]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace'))
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--wire-dir', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'requires_pinned_interpreter_-I_-B')
    if args.worker:
        worker(args.repo, args.worker, args.wire_dir)
        return
    require(args.baseline and args.candidate and args.output, 'complete_two_install_explicit_options_required')
    args.wire_dir.mkdir(exist_ok=False)
    before = spawn_worker(args.repo, args.baseline, args.wire_dir / 'A')
    after = spawn_worker(args.repo, args.candidate, args.wire_dir / 'B')
    require(before['source_sha256'] == BEFORE and read(args.candidate)['preparation_git'].startswith(AFTER_REVISION),
            'wrong_bound_A_B_install')
    require(set(before['outputs']) == set(after['outputs']), 'independent_AB_case_sets_differ')
    unchanged, boundary = [], {}
    for case, a in before['outputs'].items():
        b = after['outputs'][case]
        a_raw, b_raw = (Path(record['RX']['path']).read_bytes() for record in (a, b))
        a_packet, b_packet = map(json.loads, (a_raw, b_raw))
        a_text, a_doc = body(a_packet)
        b_text, b_doc = body(b_packet)
        require(a_doc == b_doc and len(a_text.encode()) == len(b_text.encode())
                and a_packet['result']['content'][1:] == b_packet['result']['content'][1:]
                and a['images'] == b['images'], 'control_changed_fields_or_PNG/' + case)
        if a['expects_tail_move']:
            require(list(b_doc) == [key for key in a_doc if key != 'task_result'] + ['task_result'],
                    'eligible_case_moved_other_member_or_did_not_move_tail/' + case)
        else:
            require(a_raw == b_raw, 'ineligible_case_byte_delta/' + case)
            unchanged.append(case)
        if case.startswith('synthetic_two_images_body_') or case.startswith('region_task_'):
            boundary[case] = compare_budget(args.repo, a_packet, b_packet)
            require(all(stage[arm]['original_image_order_preserved'] and not stage['newly_lost_unrecoverable_critical_paths']
                        for groups in boundary[case].values() for stage in groups.values() for arm in ('A', 'B')),
                    'fixed_policy_replay_changed_original_PNG_or_lost_necessary_evidence/' + case)
    report = {'schema': 'm1-joint-full-task-tail-compatibility-controls-v1', 'passed': True,
              'A': before['source_sha256'], 'B': after['source_sha256'], 'case_count': len(unchanged) +
              sum(row['expects_tail_move'] for row in after['outputs'].values()),
              'byte_identical_ineligible': unchanged,
              'tail_cases': [case for case, row in after['outputs'].items() if row['expects_tail_move']],
              'original_and_control_packets': {'A': before['outputs'], 'B': after['outputs']},
              'budget_boundary_and_four_images': boundary, 'source_pins': before['source_pins'],
              'Blender_starts': 0, 'model_starts': 0, 'new_rasters': 0, 'candidate_builds_in_this_check': 0}
    with args.output.open('x', encoding='utf8', newline='\n') as dest:
        json.dump(report, dest, ensure_ascii=False, indent=2, allow_nan=False)
        dest.write('\n')
    print(pin(args.output))


if __name__ == '__main__':
    main()
