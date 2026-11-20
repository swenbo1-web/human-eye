"""Exercise every registered route and its wire without Blender or a model."""

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
from budget import LIMITS


NS = common.NS
TRANSFER_RUN = Path('D:/he_m4_cross_scale_assembly_transfer_001')


def require(test, reason):
    if not test:
        raise ValueError(reason)


def rejection(call, reason):
    try:
        call()
    except (ValueError, RuntimeError) as error:
        require(str(error).startswith(reason), 'wrong_rejection/' + str(error))
    else:
        raise ValueError('failed_to_reject/' + reason)


def normalize(argv, folder, thin):
    for path, label in ((folder, '<slot>'), (thin, '<thin>')):
        value = str(path.resolve())
        separator = chr(92)
        argv = [part.replace(value.replace(separator, separator * 2), label).replace(value, label) for part in argv]
    return argv


def fixture_result(label, freeze):
    group, phase = common.SLOTS[label]
    formal = phase == 'formal'
    return {'label': label, 'group': group, 'phase': phase, 'status': 'completed',
            'asset_sha256': common.ASSET_SHA256, 'freeze_sha256': freeze,
            'product_source_sha256': common.SOURCE_SHA,
            'product_binding_sha256': common.sha(common.PRODUCT_BINDING),
            'errors': [], 'model_consumers': int(formal),
            'owner_close': {'confirmed': True, 'errors': [], 'transport_errors': []},
            'closure_verification': {'status': 'ready_closed', 'passed': True, 'mcp_closure_required': group == 'P'},
            'independent_before_after': {'passed': True, 'same_owned_scene': True},
            'budget': {'counts': {'Blender_spawned_unknown': 0, 'pending_raster_reservations': 0}},
            'consumer': {'valid_completion': True, 'safe_to_continue': True, 'process_reaped': True,
                         'readers_stopped': True, 'errors': [],
                         'runtime_exit': {'confirmed': True, 'exited': True, 'handle_closed': True}} if formal else None}


def publish_fixture(slot, label, freeze):
    path = slot / 'SLOT_RESULT.json'
    common.save(path, fixture_result(label, freeze))
    common.save(slot / 'SLOT_PUBLICATION.json', {'label': label, 'status': 'completed',
                'owned_budget_passed': True, 'result_sha256': common.sha(path)})


def call(owner, name, arguments, attempt):
    request = {'jsonrpc': '2.0', 'id': attempt, 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments}}
    reply = owner.handle(request, attempt)
    require(reply == common.read(owner.output / f'tool_{attempt:02d}/RESPONSE.json'), 'dispatch_archive_route_changed')
    return reply['result']


def replay_slot(temp, label, bridge, consumer, runtime, frame_device, proof, turn, archived, historical_cli, digest):
    group, phase = common.SLOTS[label]
    admission.check_schedule(label, digest)
    folder = temp / 'slots' / label
    folder.mkdir(parents=True)
    wrong_group = 'P' if group == 'N' else 'N'
    task = time.perf_counter_ns() + 450_000_000_000
    deadline = task + 150_000_000_000
    instance = runtime.Runtime(folder, label, task, deadline)
    require((instance.label, instance.group, instance.phase) == (label, group, phase)
            and instance.folder == folder, 'actual_runtime_slot_route_changed')
    instance.prepare_device(common.ASSET_SHA256)
    require(type(instance.device) is frame_device.FrameDevice and instance.device.label == label,
            'actual_frame_device_slot_route_changed')
    instance.product_tools = common.read(common.PRODUCT_BINDING.parent / 'TOOLS_SCHEMA.json')
    output = folder / 'owner'
    config = {'label': label, 'group': group, 'phase': phase, 'worker_deadline_ns': task, 'output': str(output)}
    rejection(lambda: bridge.Owner(instance, {**config, 'group': wrong_group}), 'registered_dense_panel_slot_required')
    rejection(lambda: bridge.Owner(instance, {**config, 'phase': 'formal' if phase == 'qualification' else 'qualification'}),
              'registered_dense_panel_slot_required')
    rejection(lambda: bridge.Owner(instance, {**config, 'label': 'QP'}), 'registered_dense_panel_slot_required')
    owner = bridge.Owner(instance, config, budget=instance.budget)
    schema = owner.handle({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})['result']['tools']
    require(schema == common.read(output / 'TOOLS_SCHEMA.json')
            and sorted(tool['name'] for tool in schema) == proof['actual_tools_by_group'][group],
            'actual_slot_catalogue_or_archive_changed')
    names = owner.session.namespace
    require(not ({'region', 'observe', 'task', 'last_observation_json', 'last_task_json'} & names.keys()),
            'qualification_or_installed_product_data_in_ordinary_session')
    registered = {item['name'] for item in names['cameras']['views']}
    require(registered == set(bridge.VIEWS), 'shared_registered_cameras_changed')
    scratch_proof = call(owner, 'execute_python', {'code':
        'value = Fraction(1,3)\nprint(value, np.array([1,2]).sum(), shapely.Point(0,0).is_empty)'}, 1)
    retained_proof = call(owner, 'execute_python', {'code': 'print(value)'}, 2)
    require(scratch_proof['isError'] is False and retained_proof['isError'] is False
            and json.loads(scratch_proof['content'][0]['text'])['stdout'].strip() == '1/3 3 False'
            and json.loads(retained_proof['content'][0]['text'])['stdout'].strip() == '1/3',
            'ordinary_dependencies_or_persistence_changed')
    isolation = call(owner, 'execute_python', {'code': 'open(' + repr(str(common.TRUTH)) + ', "rb").read()'}, 3)
    require(isolation['isError'] is True and 'consumer_private_file' in isolation['content'][0]['text'],
            'ordinary_tool_accessed_private_truth')
    def installed(arguments):
        require(arguments == common.read(NS / 'inputs/REQUEST.json'), 'product_arguments_changed_in_bridge')
        return archived

    with patch.object(instance, 'public_request', installed):
        forwarded = call(owner, bridge.PRODUCT_TOOL, common.read(NS / 'inputs/REQUEST.json'), 4)
    if group == 'P':
        require(forwarded == archived['result'], 'actual_v2_original_text_or_PNG_rewritten')
    else:
        require(forwarded['isError'] is True, 'native_slot_exposed_product')
    clocks = owner.close()
    require(clocks['confirmed'] and not clocks['errors'] and not clocks['transport_errors'], 'owner_offline_close_failed')

    cli = None
    if phase == 'formal':
        consumer_dir, workspace = folder / 'consumer', folder / 'workspace'
        consumer_dir.mkdir()
        workspace.mkdir()
        endpoint = folder / 'ENDPOINT.json'
        common.save(endpoint, {'chain_deadline_ns': task})
        cell = consumer_dir / 'cell.json'
        common.save(cell, {'endpoint': str(endpoint)})
        argv = turn.__globals__['initial_argv'](proof['Python_path'], cell, workspace, consumer_dir / 'final.txt', group)
        old_folder = TRANSFER_RUN / 'slots' / f'{group}1'
        old_thin = common.V / 'm4_cross_scale_assembly_transfer_001/thin_stdio.py'
        actual = normalize(argv, folder, NS / 'thin_stdio.py')
        expected = normalize(historical_cli[group]['requested_cli_overrides_and_argv'], old_folder, old_thin)
        require(actual == expected, 'live_CLI_argv_changed/' + label)
        captured = {}

        def inert(**actual_call):
            captured.update(actual_call)
            return {'status': 'offline_stub'}

        with patch.object(consumer, 'consumer_adapter', return_value=(inert, proof, lambda *args: {'stub': True})):
            envelope = consumer.consume_slot(label, folder, endpoint, output, task, deadline)
        require(captured['folder'] == consumer_dir and captured['work'] == workspace
                and captured['expected_thread_id'] is None and not any(workspace.iterdir())
                and captured['prompt'] == (common.DENSE / f'inputs/PROMPT_{group}.txt').read_bytes()
                and captured['episode_id'].endswith('-' + label)
                and envelope['consumer_record'] == str(consumer_dir / 'CONSUMER.json'),
                'fresh_prompt_or_result_dispatch_changed/' + label)
        cli = {'argv_matches_historical': True, 'argv_sha256': sha256(json.dumps(actual).encode()).hexdigest(),
               'prompt_sha256': envelope['prompt_sha256'], 'workspace_empty': True}
    else:
        rejection(lambda: consumer.consume_slot(label, folder, folder / 'ENDPOINT.json', output, task, deadline),
                  'registered_formal_slot_and_absolute_deadlines_required')
        rejection(lambda: instance.budget.reserve('consumer_task', label, phase), 'qualification_model_consumer_forbidden')
    publish_fixture(folder, label, digest)
    rejection(lambda: admission.check_schedule(label, digest), 'original_schedule_or_replacement_changed')
    return {'slot': label, 'group': group, 'phase': phase, 'result_path_suffix': f'slots/{label}/SLOT_RESULT.json',
            'publication_path_suffix': f'slots/{label}/SLOT_PUBLICATION.json', 'tool_schema_verified': True,
            'ordinary_persistence_and_isolation': True, 'original_v2_passthrough': group == 'P', 'formal_cli': cli,
            'duplicate_slot_rejected': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=NS / 'harness/DISPATCH_PREFLIGHT.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    shared_file = common.V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
    binding = common.read(common.PRODUCT_BINDING)
    sys.path[:0] = [str(NS), binding['dependency_root'], common.read(shared_file)['dependency_root']]
    import bridge
    import consumer
    import frame_device
    import runtime

    turn, proof, _ = consumer.consumer_adapter()
    prev_files = {group: TRANSFER_RUN / 'slots' / f'{group}1/consumer/ACTUAL_CONFIGURATION.json' for group in 'NP'}
    historical_cli = {group: common.read(path) for group, path in prev_files.items()}
    original_wire = common.QP_EXTERNAL / 'slots/QP/mcp/rpc_04/RX.bin'
    archived = common.read(original_wire)
    external = admission.registered_external_qp()
    review = common.read(external['review_path'])
    require(common.sha(original_wire) == review['wire']['RX_sha256']
            and json.loads(archived['result']['content'][0]['text'])['schema'] == 'active-observation-region-task-brief-v2',
            'prior_original_v2_wire_changed')
    checks = []
    with tempfile.TemporaryDirectory(prefix='dense_formal_dispatch_') as path:
        temp = Path(path).resolve()
        with patch.object(admission, 'EXTERNAL', temp), patch.object(runtime._previous, 'EXTERNAL', temp):
            digest = '0' * 64
            rejection(lambda: admission.check_schedule('N1', digest), 'original_schedule_or_replacement_changed')
            for label in common.ORDER:
                checks.append(replay_slot(temp, label, bridge, consumer, runtime, frame_device, proof, turn, archived,
                                          historical_cli, digest))
    failed, publication = fixture_result('P1', '0' * 64), {'status': 'failed', 'owned_budget_passed': True}
    failed.update(status='failed', errors=[{'stage': 'consumer', 'type': 'TimeoutError'}])
    failed['consumer']['valid_completion'] = False
    require(admission.can_continue(failed, publication), 'safe_model_failure_did_not_preserve_schedule')
    for section, key, bad in (('consumer', 'safe_to_continue', False), ('owner_close', 'confirmed', False),
                              ('independent_before_after', 'passed', False),
                              ('closure_verification', 'mcp_closure_required', False)):
        row = deepcopy(failed)
        row[section][key] = bad
        require(not admission.can_continue(row, publication), 'unknown_lifecycle_accepted/' + section)
    pinned = {Path(row['path']).resolve() for row in proof['execution_sources']}
    pinned.update({*prev_files.values(), original_wire, common.PRODUCT_BINDING, shared_file,
                   *(NS / 'harness').glob('*.py'), NS / 'frame_device.py'})
    common.save(args.output, {'schema': 'm4-dense-panel-formal-dispatch-preflight-v1', 'passed': True,
        'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
        'slots': checks, 'ledger_limits': LIMITS, 'external_qp': external, 'cli_proof': proof,
        'clean_model_only_failure_can_continue': True, 'unknown_host_or_consumer_rejected': True,
        'source_pins': [{'path': str(p.resolve()), 'sha256': common.sha(p), 'bytes': p.stat().st_size} for p in sorted(pinned)]})
    print('Offline dispatch passed', len(checks), common.sha(args.output))


if __name__ == '__main__':
    main()
