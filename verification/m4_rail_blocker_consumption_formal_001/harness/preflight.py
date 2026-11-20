"""Replay both arms' four actual tool deliveries through all six formal routes."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import common
import consumer
import runtime
from budget import LIMITS


NS, OLD = common.NS, common.OLD
ARCHIVE = Path('D:/he_m4_rail_blocker_consumption_001')
retained = common.load('_rail_original_dispatch_preflight', OLD / 'harness/preflight.py')
require, rejection, call, normalize, replay_mcp_start = (getattr(retained, name) for name in
    ('require', 'rejection', 'call', 'normalize', 'replay_mcp_start'))


def actual_calls(arm, pins):
    slot = ARCHIVE / 'slots' / ('Q' + arm)
    device = slot / 'DEVICE_EVIDENCE.json'
    source, = [item for item in common.read(device)['sources'] if not item['terminal']]
    raw_path = Path(source['path'])
    require(raw_path.resolve().is_relative_to(slot.resolve()) and common.sha(raw_path) == source['sha256'],
            'prior_ordinary_source_mismatch/' + arm)
    scene = {**common.read(raw_path), 'source_ref': source['source_ref']}
    pins.update((device, raw_path))
    calls = []
    for index in (1, 2):
        folder = slot / 'client' / f'call_{index:02d}'
        tx, rx = folder / 'REQUEST.json', folder / 'RESPONSE.json'
        pins.update((tx, rx))
        request, reply = common.read(tx), common.read(rx)
        require(request['id'] == reply['id'] and reply['result']['isError'] is False,
                'prior_real_delivery_unavailable/' + arm)
        calls.append((request['params'], reply))
    return scene, calls


def replay_slot(temp, label, bridge, frame_device, proof, turn, actual, prior_argv, digest):
    group, phase = common.SLOTS[label]
    arm = common.ARMS[label]
    admission.check_schedule(label, digest)
    folder = temp / 'slots' / label
    folder.mkdir(parents=True)
    task = time.perf_counter_ns() + 450_000_000_000
    deadline = task + 150_000_000_000
    instance = runtime.Runtime(folder, label, task, deadline)
    path, binding = common.product_for(label)
    require((instance.label, instance.group, instance.phase, instance.arm) == (label, group, phase, arm)
            and instance.folder == folder and instance.binding_path == path and instance.binding == binding,
            'actual_formal_slot_install_route_changed/' + label)
    instance.prepare_device(common.ASSET_SHA256)
    require(type(instance.device) is frame_device.FrameDevice and instance.device.label == label,
            'formal_frame_device_slot_route_changed')
    require(runtime.Runtime._start_public_mcp.__globals__['HERE'] == NS / 'harness',
            'installed_mcp_entry_not_bound_to_formal_harness')
    replay_mcp_start(instance, common.read(path.parent / 'TOOLS_SCHEMA.json'))
    output = folder / 'owner'
    config = {'label': label, 'group': group, 'phase': phase, 'worker_deadline_ns': task, 'output': str(output)}
    owner = bridge.Owner(instance, config, budget=instance.budget)
    schema = owner.handle({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})['result']['tools']
    require(schema == common.read(output / 'TOOLS_SCHEMA.json')
            and sorted(tool['name'] for tool in schema) == proof['actual_tools_by_group'][group],
            'formal_actual_catalogue_or_archive_changed')
    names = owner.session.namespace
    require(not ({'region', 'observe', 'task', 'last_observation_json', 'last_task_json'} & names.keys()),
            'qualification_or_installed_product_data_in_ordinary_session')
    require({item['name'] for item in names['cameras']['views']} == set(bridge.VIEWS),
            'registered_common_directions_changed')
    scene, [(product_request, product_reply), (ordinary_request, ordinary_reply)] = actual[arm]
    require(product_request == {'name': bridge.PRODUCT_TOOL, 'arguments': common.read(common.INPUTS / 'REQUEST.json')}
            and ordinary_request['name'] == 'execute_python', 'actual_qualification_requests_changed')

    def installed(arguments):
        require(arguments == product_request['arguments'], 'original_product_argument_delivery_changed')
        return product_reply

    with patch.object(instance, 'public_request', installed):
        product = call(owner, product_request['name'], product_request['arguments'], 1)
    require(product == product_reply['result'], 'actual_product_text_or_PNG_changed')
    with patch.object(instance.device, '_scene', deepcopy(scene)):
        ordinary = call(owner, ordinary_request['name'], ordinary_request['arguments'], 2)
    require(ordinary == ordinary_reply['result'], 'actual_ordinary_source_reply_changed')
    # The source and qualification proof fixtures are only supplied to this
    # isolated dry owner, never passed into a fresh formal consumer.
    isolation = call(owner, 'execute_python', {'code': 'open(' + repr(str(common.TRUTH)) + ', "rb").read()'}, 3)
    require(isolation['isError'] is True and 'consumer_private_file' in isolation['content'][0]['text'],
            'ordinary_tool_accessed_private_truth')
    closed = owner.close()
    require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
            'dry_owner_close_failed')

    consumer_dir, workspace = folder / 'consumer', folder / 'workspace'
    consumer_dir.mkdir()
    workspace.mkdir()
    endpoint = folder / 'ENDPOINT.json'
    common.save(endpoint, {'chain_deadline_ns': task})
    cell = consumer_dir / 'cell.json'
    common.save(cell, {'endpoint': str(endpoint)})
    argv = turn.__globals__['initial_argv'](proof['Python_path'], cell, workspace, consumer_dir / 'final.txt', group)
    observed = normalize(argv, folder, OLD / 'thin_stdio.py')
    require(observed == prior_argv, 'fixed_native_CLI_dispatch_changed/' + label)
    captured = {}

    def inert(**kwargs):
        captured.update(kwargs)
        return {'status': 'offline_stub'}

    with patch.object(consumer._retained, 'consumer_adapter', return_value=(inert, proof, lambda *a: {'stub': True})):
        envelope = consumer.consume_slot(label, folder, endpoint, output, task, deadline)
    require(captured['work'] == workspace and not any(workspace.iterdir()) and captured['expected_thread_id'] is None
            and captured['prompt'] == (common.INPUTS / 'PROMPT_COMMON.txt').read_bytes()
            and captured['cell'] == {'endpoint': str(endpoint), 'group': 'P', 'audit_dir': str(output)}
            and envelope['arm'] == arm and envelope['consumer_record'] == str(consumer_dir / 'CONSUMER.json'),
            'fresh_cli_prompt_or_evidence_targets_changed')
    row = {**retained.fixture_result(label, digest), 'qualification_sha256': common.sha(admission.DERIVED)}
    result = folder / 'SLOT_RESULT.json'
    common.save(result, row)
    common.save(folder / 'SLOT_PUBLICATION.json', {'label': label, 'status': 'completed',
                  'owned_budget_passed': True, 'result_sha256': common.sha(result)})
    require(admission.publication(label, digest)[0] == row, 'formal_publication_binding_failed')
    rejection(lambda: admission.check_schedule(label, digest), 'rail_formal_schedule_or_replacement_changed')
    return {'slot': label, 'arm': arm, 'phase': phase, 'original_v2_passthrough': True,
            'original_ordinary_source_reply_preserved': True, 'schema_verified': True,
            'formal_thin_argv_matches_prior': True, 'formal_thin_argv_sha256': sha256(json.dumps(observed).encode()).hexdigest(),
            'prompt_sha256': envelope['prompt_sha256'], 'isolated_fresh_workspace': True,
            'product_binding_sha256': common.sha(path), 'product_source_sha256': instance.source_sha,
            'actual_install_path': str(binding['install_root']), 'no_slot_replacement': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=NS / 'harness/DISPATCH_PREFLIGHT.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    shared_file = common.V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
    _, binding = common.product_for('A1')
    sys.path[:0] = [str(OLD), binding['dependency_root'], common.read(shared_file)['dependency_root']]
    import bridge
    import frame_device

    turn, proof, _ = consumer.consumer_adapter()
    gate = common.load('_rail_formal_dry_qualification', admission.DERIVED.with_name('derive.py')).verify_sealed()
    require(gate['passed'] is True, 'formal_originals_ineligible')
    original = retained.HISTORICAL_RUN / 'slots/P1/consumer/ACTUAL_CONFIGURATION.json'
    expected = normalize(common.read(original)['requested_cli_overrides_and_argv'], original.parents[1],
                         common.V / 'm4_dense_panel_sweep_formal_001/thin_stdio.py')
    pins = {original, shared_file, *(NS / 'harness').glob('*.py'), NS / 'run_sequence.py',
            OLD / 'bridge.py', OLD / 'thin_stdio.py', OLD / 'frame_device.py',
            *(OLD / 'harness').glob('*.py'),
            *(common.INPUTS / name for name in ('REQUEST.json', 'PROMPT_COMMON.txt', 'PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'))}
    actual = {arm: actual_calls(arm, pins) for arm in ('A', 'B')}
    with tempfile.TemporaryDirectory(prefix='rail_formal_dispatch_') as temp:
        temp = Path(temp).resolve()
        derived = temp / 'DERIVED_FIXTURE.json'
        common.save(derived, {'offline_test_double_only': True})
        fake_freeze = '0' * 64
        with patch.object(admission, 'EXTERNAL', temp), patch.object(admission, 'DERIVED', derived), \
                patch.object(runtime._previous, 'EXTERNAL', temp):
            rejection(lambda: admission.check_schedule('QA', fake_freeze), 'registered_formal_slot_required')
            rejection(lambda: admission.check_schedule('B1', fake_freeze), 'rail_formal_schedule_or_replacement_changed')
            records = [replay_slot(temp, label, bridge, frame_device, proof, turn, actual, expected, fake_freeze)
                       for label in common.ORDER]
            with patch.object(admission, 'DERIVED', OLD / 'QUALIFICATION.json'):
                rejection(lambda: admission.publication('A1', fake_freeze),
                          'rail_formal_result_publication_or_qualification_changed')
    failed = retained.fixture_result('A1', '0' * 64)
    failed.update(status='failed', errors=[{'stage': 'consumer', 'type': 'TimeoutError'}])
    failed['consumer']['valid_completion'] = False
    closured = {'status': 'failed', 'owned_budget_passed': True}
    require(admission.can_continue(failed, closured), 'verified_model_only_failure_did_not_preserve_schedule')
    for section, name, value in (
        ('consumer', 'safe_to_continue', False), ('owner_close', 'confirmed', False),
        ('independent_before_after', 'passed', False), ('closure_verification', 'mcp_closure_required', False),
        ('consumer', 'errors', [{'stage': 'business_original_binding'}]),
    ):
        row = deepcopy(failed)
        row[section][name] = value
        require(not admission.can_continue(row, closured), 'unknown_host_or_source_binding_accepted/' + name)
    pins.update(Path(row['path']) for row in proof['execution_sources'])
    common.save(args.output, {'schema': 'm4-rail-blocker-formal-dispatch-preflight-v1', 'passed': True,
        'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
        'slots': records, 'ledger_limits': LIMITS, 'products': common.PRODUCTS, 'cli_proof': proof,
        'stored_original_tool_deliveries_exercised': 4, 'clean_model_only_failure_can_continue': True,
        'unknown_host_or_consumer_rejected': True,
        'source_pins': [{'path': str(p), 'sha256': common.sha(p), 'bytes': p.stat().st_size}
                        for p in sorted({item.resolve() for item in pins})]})
    print('Formal dispatch preflight passed', len(records), common.sha(args.output))


if __name__ == '__main__':
    main()
