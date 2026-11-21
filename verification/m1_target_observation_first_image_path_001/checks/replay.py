"""Replay sealed original responses through two installed MCP serializers."""

import argparse
import base64
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from unittest.mock import patch
from zipfile import ZipFile


TRANSFER = 'perf050_readonly_product_transfer_001'
SOURCE_REGION = 'perf050_source_region_final_image_p3'
REGION_TASK = 'm5_joint_brief_source_projection_recovery_001'
RUNS = {
    TRANSFER: ('P1', 376, 'a9137fd155103d65d914cce847f7675cc8e0dbe09af2b00f30e7dcafd70b02fe'),
    SOURCE_REGION: ('P3', 268, '2363439f0bb573fdd160a424f5307c8198f3b7912935be2720fcbb5126eb7cab'),
    REGION_TASK: ('B', 133, '8d6c39fb458dbf9d426366261f75bab63f4589ea18e3002d1cd3113cb81f20b1'),
}
SOURCE = '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7'
LEFT = '4a69c9a0c955be1527564d9df02db9fbfcdbad95bfd836deb7fd6afd04c75157'
SCENE = '1ada614acfce81b7c8ca867c16fb0bca85e83292b009c2137324584e52ffddff'
P3 = 'a0b1aa30a722c519252224c8645084c92b08a514762e07e61e24f1b8e8225dbe'
FIELD = 'local_image_path'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(data):
    return sha256(data).hexdigest()


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(data), 'sha256': digest(data)}


class Original:
    def __init__(self, repo, key, stack):
        self.root = Path('D:/he_' + key).resolve()
        self.slot, count, known = RUNS[key]
        index = repo / 'verification' / key / 'RUNTIME_INDEX.json'
        pointer = read(index)
        archive_path = self.root / 'ORIGINAL_RUNTIME.zip'
        receipt = pin(archive_path)
        self.pins = [pin(index), receipt]
        require(receipt['sha256'] == pointer['archive']['sha256'] == known, 'wrong_original_archive/' + key)
        self.archive = stack.enter_context(ZipFile(archive_path))
        self.files = {row['path']: row for row in pointer['files']}
        require(set(self.archive.namelist()) == self.files.keys() and len(self.files) == count == pointer['count'],
                'wrong_original_member_set/' + key)

    def member(self, name):
        member = ('slots/' + self.slot + '/' + name).replace('\\', '/')
        path = self.root / member
        data = path.read_bytes()
        receipt = {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}
        require({**receipt, 'path': member} == self.files[member] and data == self.archive.read(member),
                'original_member_changed/' + member)
        self.pins.append(receipt)
        return data

    def json(self, name):
        return json.loads(self.member(name))

    @property
    def state_path(self):
        return self.root / 'slots' / self.slot / 'product_state.json'


def original_case(original, call):
    name = f'call_{call:03d}'
    return (original.json(f'product_calls/{name}/REQUEST.json'),
            original.json(f'product_full/{name}/SERVICE_RESULT.json'),
            original.json(f'product_calls/{name}/RESPONSE.json')['result'])


def body(reply):
    return json.loads(reply['content'][0]['text'])


def image_bytes(reply):
    return [base64.b64decode(row['data'], validate=True)
            for row in reply['content'] if row['type'] == 'image' and row['mimeType'] == 'image/png']


def image_receipts(reply):
    return [{'bytes': len(window), 'sha256': digest(window)} for window in image_bytes(reply)]


def value(reply, *, strip_target=False):
    metadata = body(reply)
    images = metadata.get('images')
    if type(images) is list:
        scope = metadata.get('image_scope', {})
        objects = scope.get('objects')
        if isinstance(objects, dict):
            scope['objects'] = [dict(zip(objects['columns'], row, strict=True)) for row in objects['rows']]
    if strip_target:
        table = metadata['images']
        col = table['columns'].index(FIELD)
        table['columns'].pop(col)
        for row in table['rows']:
            row.pop(col)
    return metadata, reply['content'][1:], reply['isError']


def image_paths(reply):
    parsed = body(reply)
    images = parsed.get('images')
    if isinstance(images, list):
        return [row[FIELD] for row in images if FIELD in row]
    if isinstance(images, dict) and FIELD in images['columns']:
        col = images['columns'].index(FIELD)
        return [row[col] for row in images['rows']]
    return []


def modified_request(request, **changes):
    altered = deepcopy(request)
    altered['params']['arguments'].update(changes)
    return altered


def unknown_witness(producer, *, include_image):
    sample = deepcopy(producer)
    sample['status'] = 'partial' if include_image else 'predicted'
    sample['frames'] = sample['frames'][:int(include_image)]
    facts = sample['facts']
    facts['observations'] = facts['observations'][:int(include_image)]
    roi = facts['regions'][0]['roi_id']
    facts['regions'][0].update(status='unknown', reason='unobserved_geometric_candidates')
    evidence, = facts['region_evidence']
    evidence.update(complete_witness=None, unobserved_reason='unobserved_geometric_candidates',
                    view_reasons={'positive_area_occlusion': ['SCENE', 'TOP', 'RIGHT', 'FRONT'],
                                  'unobserved_geometric_candidate': ['LEFT', 'BACK']})
    facts['coverage'].update(covered_roi_ids=[], unresolved_roi_ids=[roi],
                             observed_views=['SCENE'] if include_image else [], state_updates=int(include_image))
    facts['inspection']['counts'].update(covered=0, unobserved=1, pending_geometric_candidate=1)
    facts['inspection'].update(state='observation_required' if include_image else 'prediction_only',
                               stop_reason='unobserved_geometric_candidates_remain' if include_image
                               else 'actual_observation_required')
    return sample


def whole_scene(producer):
    # Target-bound image files remain byte-identical. Convert display fields only
    # to cover the ordinary full-scene projection route without rendering.
    sample = deepcopy(producer)
    sample.pop('task_result')
    sample['binding'].pop('observation_target')
    sample['binding']['capture_scope'] = 'complete_scene_meshes'
    facts = sample['facts']
    facts['scope'].pop('observation_scope')
    support = facts['scope']['patch_support']
    support['schema'] = 'active-patch-support-v1'
    for row in support['objects'][1:]:
        row.pop('coverage_role')
        row['support_status'] = 'unsupported'
        row['unsupported_triangle_count'] = row['source_triangle_count']
        row['unsupported_components'] = [{'reason': 'synthetic_projection_control', 'status': 'unknown',
                                          'triangle_indices': list(range(row['source_triangle_count']))}]
    facts['scope']['objects_without_supported_roi'] = [
        {**row, 'status': 'unsupported'} for row in sample['binding']['objects'][1:]
    ]
    return sample


def worker(repo, binding_path):
    install = read(binding_path)
    require(len(install['source_manifest']) == 143, 'incorrect_installed_manifest_count')
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    runtime = runtime_identity()
    require(runtime['source_sha256'] == install['source_sha256']
            and runtime['source_kind'] == 'installed_distribution'
            and Path(mcp.__file__).resolve().is_relative_to(Path(install['install_root']).resolve()),
            'worker_must_use_the_actual_isolated_install')
    serializer = run_path(str(repo / 'verification/m1_source_region_final_image_001/checks/serializer.py'))
    saved = serializer['SavedProducer']

    def dispatch(request, producer, state):
        started = perf_counter_ns()
        service = saved(producer, request['params']['arguments'], state)
        server = mcp.LiveSpatialMCPServer(service, default_session_id=producer['session_id'])
        packet = server.handle_jsonrpc_message(deepcopy(request))
        require(packet['id'] == request['id'] and packet['jsonrpc'] == '2.0' and service.observations == 1,
                'archived_producer_not_reached_via_actual_MCP_dispatch')
        return packet, perf_counter_ns() - started

    def result(request, producer, state):
        return dispatch(request, producer, state)[0]['result']

    timings, path_timings = [], []
    with ExitStack() as stack:
        transfer = Original(repo, TRANSFER, stack)
        source = Original(repo, SOURCE_REGION, stack)
        region = Original(repo, REGION_TASK, stack)
        request, producer, archived = original_case(transfer, 2)
        require(transfer.json('mcp/rpc_05/TX.bin') == request
                and transfer.json('mcp/rpc_05/RX.bin')['result'] == archived,
                'live_stdio_and_primary_replay_inputs_must_match')
        require(transfer.json('SLOT_RESULT.json')['closure_verification']['passed'] is True,
                'archived_transfer_slot_is_not_closed')
        original_images = image_receipts(archived)
        require(original_images == [{'bytes': 2580, 'sha256': SCENE}, {'bytes': 2526, 'sha256': LEFT}],
                'primary_archived_native_blocks_changed')
        for frame, expected in zip(producer['frames'], image_bytes(archived), strict=True):
            path = Path(frame['image_path'])
            require(expected == transfer.member(path.relative_to(transfer.state_path.parent).as_posix()),
                    'actual_archived_frame_versus_wire_bytes_changed')
        old_read = transfer.json('owner/tool_03/RESPONSE.json')['result']
        local = json.loads(old_read['content'][0]['text'].splitlines()[1])
        require(local == {FIELD: Path(producer['frames'][1]['image_path']).as_posix(), 'image_sha256': LEFT}
                and image_bytes(old_read) == [image_bytes(archived)[1]], 'old_second_call_not_same_left_png')
        replied = {}
        target_packet = None
        path_validator = getattr(mcp, '_target_observation_local_image_path', None)

        def timed_validate(*args, **kwargs):
            start = perf_counter_ns()
            try:
                return path_validator(*args, **kwargs)
            finally:
                path_timings.append(perf_counter_ns() - start)

        if path_validator is not None:
            stack.enter_context(patch.object(mcp, '_target_observation_local_image_path', timed_validate))
        for _ in range(21):
            delivered, elapsed = dispatch(request, producer, transfer.state_path)
            require(target_packet is None or delivered == target_packet, 'primary_MCP_replay_is_not_stable')
            target_packet = delivered
            timings.append(elapsed)
        replied['target'] = target_packet['result']
        replied['full'] = result(modified_request(request, response_detail='full'), producer, transfer.state_path)
        replied['no_image'] = result(modified_request(request, include_image=False),
                                    unknown_witness(producer, include_image=False), transfer.state_path)
        replied['no_witness'] = result(request, unknown_witness(producer, include_image=True), transfer.state_path)
        replied['whole_scene'] = result(modified_request(request, query={'mode': 'active_observation'}),
                                       whole_scene(producer), transfer.state_path)
        for label, original, ordinal in [('source_region', source, 2), ('region_task', region, 1)]:
            req, service, raw = original_case(original, ordinal)
            for row in service['frames']:
                original.member(Path(row['image_path']).relative_to(original.state_path.parent).as_posix())
            replied[label] = result(req, service, original.state_path)
            require(value(replied[label]) == value(raw), 'compat_replay_does_not_match_original/' + label)
        require(image_receipts(replied['source_region']) == [{'bytes': 2870, 'sha256': P3}]
                and len(image_paths(replied['source_region'])) == 1, 'P3_path_or_original_changed')
        controls = {}
        controls['missing_trusted_state'] = result(request, producer, None)
        for label in ('wrong_digest', 'wrong_binding', 'wrong_frame_identity', 'wrong_patch',
                      'same_name_different_png', 'path_dot_alias', 'path_case_alias', 'foreign_same_png',
                      'wrong_visibility_binding', 'wrong_roi_binding'):
            sample = deepcopy(producer)
            target = sample['frames'][1]
            observed = sample['facts']['observations'][1]
            if label == 'wrong_digest':
                target['image_sha256'] = '0' * 64
            elif label == 'wrong_binding':
                target['host_binding_sha256'] = '0' * 64
            elif label == 'wrong_frame_identity':
                target['frame_identity'] = '0' * 64
            elif label == 'wrong_patch':
                for row in sample['frames']:
                    row['patch_mapping_identity'] = '0' * 64
            elif label == 'same_name_different_png':
                sample['frames'][0]['view_name'] = sample['facts']['observations'][0]['view_name'] = 'LEFT'
            elif label in ('path_dot_alias', 'path_case_alias', 'foreign_same_png'):
                original_path = Path(target['image_path'])
                if label == 'path_dot_alias':
                    replacement = str(original_path.parent) + '\\.\\' + original_path.name
                    require(Path(replacement).read_bytes() == original_path.read_bytes()
                            and replacement != str(original_path), 'alias_control_must_still_open_actual_png')
                elif label == 'path_case_alias':
                    replacement = str(original_path).replace('\\slots\\', '\\SLOTS\\', 1)
                    alias = Path(replacement)
                    require(alias.read_bytes() == original_path.read_bytes()
                            and str(alias.resolve(strict=True)) == str(original_path)
                            and replacement != str(original_path), 'case_alias_must_open_the_same_noncanonical_file')
                else:
                    path = Path(stack.enter_context(TemporaryDirectory(prefix='he_foreign_png_')))
                    replacement = path / original_path.parent.parent.parent.name / original_path.parent.parent.name \
                        / original_path.parent.name / original_path.name
                    replacement.parent.mkdir(parents=True)
                    replacement.write_bytes(original_path.read_bytes())
                    require(replacement.read_bytes() == original_path.read_bytes(), 'foreign_same_png_control_is_not_equal')
                observed['image_path'] = target['image_path'] = str(replacement)
                target['arrays_path'] = str(replacement).removesuffix('.png') + '.npz'
            elif label == 'wrong_visibility_binding':
                sample['target_view_classifications']['LEFT'][sample['facts']['regions'][0]['roi_id']]['complete'] = False
            else:
                target['patch_roi_ids'] = ['roi_foreign']
            controls[label] = result(request, sample, transfer.state_path)

        projector = mcp.project_active_observation_brief

        def incorrect_block(value):
            brief = projector(value)
            col = brief['images']['columns'].index('native_content_block_index')
            brief['images']['rows'][1][col] = 1
            return brief

        with patch.object(mcp, 'project_active_observation_brief', incorrect_block):
            controls['mismatched_native_block_index'] = result(request, producer, transfer.state_path)
        expected_count = {'full': 2, 'no_image': 0, 'no_witness': 1, 'whole_scene': 2}
        for label, count in expected_count.items():
            reply = replied[label]
            require(not reply['isError'] and len(image_bytes(reply)) == count and not image_paths(reply),
                    'compatibility_control_did_not_reach_expected_display/' + label)
            doc = body(reply)
            if label == 'full':
                require('schema' not in doc and doc['result_kind'] == 'active_observation', 'full_case_projected')
            elif label in ('no_image', 'no_witness'):
                col = doc['regions']['columns'].index('complete_witness_pixel_index')
                require(doc['regions']['rows'][0][col] is None, 'no_witness_control_ineligible')
            else:
                require(doc['binding']['capture_scope'] == 'complete_scene_meshes'
                        and doc['schema'] == 'active-observation-brief-v5', 'whole_scene_control_ineligible')

        historical_costs = read(repo / 'verification' / TRANSFER / 'consumer/COSTS.json')
        attempts = next(row for row in historical_costs['slots'] if row['label'] == 'P1')['actual_requests']
        old_second, old_third = [next(row for row in attempts if row['attempt'] == index) for index in (2, 3)]
        for old_call in (old_second, old_third):
            outer = Path(old_call['stdio_RX']['path'])
            member = outer.relative_to(transfer.state_path.parent).as_posix()
            require(digest(transfer.member(member)) == old_call['stdio_RX']['sha256']
                    and old_call['CLI_binding'] == 'content_and_envelope_match', 'archived_CLI_wire_binding_changed')
        original_inner = transfer.member('mcp/rpc_05/RX.bin')
        pins = transfer.pins + source.pins + region.pins
    report = {'replies': replied, 'controls': controls,
              'source_sha256': runtime['source_sha256'], 'recorded': archived,
              'recorded_path': local[FIELD], 'pins': pins, 'primary_packet': target_packet,
              'original_inner_wire': {'bytes': len(original_inner), 'sha256': digest(original_inner)},
              'timings': {'target_dispatch_ns': timings, 'path_validation_ns': path_timings[:21]},
              'historical_read_images': {k: old_third[k] for k in (
                  'tool_wire_RTT_ms', 'dispatch_to_CLI_result_ms', 'owner_window_ms',
                  'after_previous_result_ms', 'wire_content')}}
    sys.stdout.buffer.write(json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf8'))


def run_worker(repo, binding):
    cmd = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--repo', str(repo), '--worker', str(binding)]
    return json.loads(subprocess.check_output(cmd, timeout=90))


def replay_wire(packet):
    # The saved Windows transport emits CRLF. The in-process handler returns
    # this envelope untouched, with no packet plumbing or new observations.
    return (json.dumps(packet, ensure_ascii=False, allow_nan=False) + '\r\n').encode()


def save_wire(path, payload):
    with path.open('xb') as sink:
        sink.write(payload)
    return pin(path)


def run(repo, baseline, candidate, output, raw_dir):
    prior = run_worker(repo, baseline)
    old = prior['replies']['target']
    require(prior['source_sha256'] == SOURCE and value(old) == value(prior['recorded'])
            and len(old['content'][0]['text'].encode()) == 8478 and not image_paths(old),
            'baseline_does_not_reproduce_actual_first_public_packet')
    report = {
        'schema': 'm1-target-observation-first-image-path-replay-v1',
        'baseline': pin(baseline), 'observed_formal_models': 0, 'observed_Blender_starts': 0,
        'observed_new_rasters': 0, 'archived_primary_body_bytes': 8478, 'baseline_original_body_equal': True,
        'originals': prior['pins'],
        'historic_inner_receive_wire': prior['original_inner_wire'],
        'baseline_replay_body_exact_archived_bytes': old['content'][0]['text'] == prior['recorded']['content'][0]['text'],
        'baseline_replay_wire_exact_archived_bytes': digest(replay_wire(prior['primary_packet'])) ==
            prior['original_inner_wire']['sha256'],
        'historical_read_images': prior['historical_read_images'],
        'baseline_dispatch_ns': {'trials': 21, 'median': median(prior['timings']['target_dispatch_ns'])},
    }
    if candidate is not None:
        diff = run_worker(repo, candidate)
        final = diff['replies']['target']
        opened = Path(prior['recorded_path']).read_bytes()
        require(diff['source_sha256'] != SOURCE and diff['pins'] == prior['pins']
                and value(final, strip_target=True) == value(old)
                and image_paths(final) == [None, prior['recorded_path']]
                and digest(opened) == LEFT and opened == image_bytes(final)[1],
                'candidate_did_not_attach_only_the_actual_LEFT_path')
        cli_replay = run_path(str(repo / 'verification/m4_source_region_active_view_001/checks/evidence.py'))['replay_cli']
        cli = cli_replay(final)
        require(cli['passed'] and len(cli['stages']) == 6, 'fixed_three_head_CLI_history_does_not_preserve_payload')
        values, failures = {}, []
        for name, result in diff['controls'].items():
            actual_paths = image_paths(result)
            old_result = prior['controls'][name]
            unchanged = (value(result, strip_target=bool(actual_paths)) == value(old_result))
            passed = not actual_paths and unchanged
            if not passed:
                failures.append(name)
            values[name] = {'passed': passed, 'is_error': result['isError'],
                            'published_paths': actual_paths, 'unchanged_without_path': unchanged,
                            'native_images': len(image_bytes(result))}
        compatibility = {}
        for name, result in diff['replies'].items():
            if name == 'target':
                continue
            require(value(result) == value(prior['replies'][name]), 'compatibility_changed/' + name)
            compatibility[name] = {'schema': body(result).get('schema'), 'native_images': len(image_bytes(result)),
                                   'existing_image_paths': image_paths(result), 'is_error': result['isError']}
        old_bytes, new_bytes = (replay_wire(row['primary_packet']) for row in (prior, diff))
        without_path = deepcopy(diff['primary_packet'])
        without_path['result']['content'][0]['text'] = json.dumps(value(final, strip_target=True)[0],
            ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        require(replay_wire(without_path) == old_bytes, 'A_B_replay_bytes_change_after_removing_only_path_column')
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            report['actual_replay_packets'] = {
                'baseline': save_wire(raw_dir / 'BASELINE_DISPATCH_RX.bin', old_bytes),
                'candidate': save_wire(raw_dir / 'CANDIDATE_DISPATCH_RX.bin', new_bytes),
            }
        report.update(candidate=pin(candidate), candidate_source_sha256=diff['source_sha256'],
                      body_bytes=cli['body_bytes'], added_body_bytes=cli['body_bytes'] - 8478,
                      baseline_replay_wire_bytes=len(old_bytes), candidate_replay_wire_bytes=len(new_bytes),
                      replay_wire_bytes_equal_after_stripping_only_path=True,
                      native_images=image_receipts(final), left_path=prior['recorded_path'],
                      left_original_open_bytes=len(opened), fixed_cli=cli, negative_controls=values,
                      negative_failures=failures, compatibility=compatibility,
                      candidate_dispatch_ns={'trials': 21, 'median': median(diff['timings']['target_dispatch_ns'])},
                      path_validation_ns={'trials': len(diff['timings']['path_validation_ns']),
                          'median': median(diff['timings']['path_validation_ns']) if diff['timings']['path_validation_ns']
                          else None},
                      final_message_natural_adoption='unmeasured',
                      actual_model_tool_call_reduction='unmeasured',
                      passed=not failures)
        if raw_dir is not None:
            for name in failures:
                report['negative_controls'][name]['actual_reply'] = save_wire(raw_dir / (name + '_RESULT_RX.bin'),
                    replay_wire({**diff['primary_packet'], 'result': diff['controls'][name]}))
    with output.open('x', encoding='utf-8', newline='\n') as out:
        out.write(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    return report.get('passed', True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'run_with_I_B')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--repo', required=True, type=Path)
    cli.add_argument('--worker', type=Path)
    cli.add_argument('--baseline', type=Path)
    cli.add_argument('--candidate', type=Path)
    cli.add_argument('--output', type=Path)
    cli.add_argument('--raw-dir', type=Path)
    args = cli.parse_args()
    if args.worker:
        worker(args.repo, args.worker)
    else:
        baseline = args.baseline or args.repo / 'verification/m1_source_region_final_image_001/install/PRODUCT_RUN_BINDING.json'
        if args.output is None:
            cli.error('--output is required')
        raise SystemExit(0 if run(args.repo, baseline, args.candidate, args.output, args.raw_dir) else 1)
