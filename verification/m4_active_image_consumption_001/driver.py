"""Frozen two-route image interface run; real CLI invocation requires --run-models."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


consumer = load('_active_image_consumer', HERE / 'consumer.py')
launch = consumer.launch
read, save, sha = consumer.read, consumer.save, consumer.sha


def resolve_input(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (HERE / path).resolve()


def input_checks(plan):
    if plan['sequence'] != ['N', 'P'] or plan['route_deadline_seconds'] != 450 or plan['max_tool_calls'] != 4:
        raise ValueError('fixed_two_routes_and_original_budgets')
    prompt = resolve_input(plan['inputs']['prompt'])
    manifest_path = resolve_input(plan['inputs']['images_manifest'])
    manifest = read(manifest_path)
    if [row['ref'] for row in manifest['images']] != ['view-a', 'view-b']:
        raise ValueError('registered_opaque_reference_order')
    sources = {str(prompt): sha(prompt), str(manifest_path): sha(manifest_path)}
    for row in manifest['images']:
        path = (manifest_path.parent / row['file']).resolve()
        if not path.is_relative_to(HERE) or sha(path) != row['sha256'] or path.stat().st_size != row['PNG_bytes']:
            raise ValueError('registered_image_source_binding')
        sources[str(path)] = sha(path)
    return prompt.read_bytes(), manifest_path, sources


def source_files(plan):
    _, _, sources = input_checks(plan)
    files = [HERE / name for name in ('driver.py', 'consumer.py', 'actor.py', 'image_content.py', 'fake_cli.py', 'PLAN.json', 'PUBLIC_INTERFACE.md')]
    files.extend([
        Path(consumer.previous.__file__), Path(consumer.cli.__file__), Path(consumer.packer.__file__),
        Path(consumer.compatibility.__file__), Path(launch.__file__), launch.BOOTSTRAP,
        consumer.previous.ATTACH_PATH, consumer.CONTINUITY / 'cli/CLI_INTERFACE.json',
        launch.BASE,
    ])
    contract = launch.describe()
    files.extend([Path(contract['dependency_manifest_path']),
                  *[Path(row['path']) for row in contract['expected_dependencies'].values()]])
    files.append(Path(read(consumer.CONTINUITY / 'cli/CLI_INTERFACE.json')['executable']))
    for path in files:
        sources[str(path.resolve())] = sha(path)
    return sources


def check_frozen(plan):
    frozen = read(HERE / 'FROZEN.json')
    current = source_files(plan)
    if frozen['runtime_sources'] != current:
        raise ValueError('frozen_source_or_input_changed')
    return frozen


def common_image_faults(record, owner):
    """Use actual failed image construction or completed result mismatch only."""
    faults = []
    metrics_path = owner / 'METRICS.json'
    metrics = read(metrics_path) if metrics_path.exists() else {}
    if metrics.get('failed_image_constructions', 0):
        faults.append({'reason': 'registered_image_construction_failed', 'count': metrics['failed_image_constructions']})
    if record.get('unknown_image_payloads', 0):
        faults.append({'reason': 'CLI_completed_image_content_invalid', 'count': record['unknown_image_payloads']})
    tools_path = owner / 'TOOLS.json'
    tools = read(tools_path).get('tools', []) if tools_path.exists() else []
    for original, observed in zip(tools, record.get('tool_calls', [])):
        item = observed['item']
        response = read(owner / ('tool_' + str(original['attempt']).zfill(2)) / 'RESPONSE.json')
        source_images = original.get('content_metrics', {}).get('image_blocks', 0)
        if source_images and not (consumer.packer.encoded(response.get('result')) == consumer.packer.encoded(item.get('result'))
                                  or consumer.compatibility.successful_result_matches(response, item)):
            faults.append({'reason': 'completed_image_response_binding_failed', 'attempt': original['attempt'],
                           'CLI_item_id': item.get('id')})
    return faults


def publish_route(folder, row, began, deadline):
    row['outer_valid_completion'] = bool(row.get('consumer_valid_completion') and row.get('owner_close_confirmed')
                                          and row.get('owner_process_cleanup', {}).get('confirmed')
                                          and not row['errors'])
    save(folder / 'RESULT.json', row)
    closed = time.perf_counter_ns()
    if closed >= deadline:
        row['outer_valid_completion'] = False
        row['errors'].append({'stage': 'publication', 'type': 'TimeoutError', 'message': 'original_route_deadline_through_result_close'})
        save(folder / 'RESULT.json', row)
        closed = time.perf_counter_ns()
    timing = {'started_ns': began, 'result_closed_ns': closed, 'elapsed_ns': closed - began,
              'original_deadline_ns': deadline, 'accepted_success': row['outer_valid_completion'] and closed < deadline,
              'scope': 'Before input checks and actor startup through CLI/actor cleanup, raw ZIP, input readback and RESULT write/close.'}
    save(folder / 'FINAL_TIMING.json', timing)
    row['final_timing'] = timing
    return row


def run_route(group, plan, runtime_root, local_cli=None):
    began = time.perf_counter_ns()
    deadline = began + 450_000_000_000
    folder = runtime_root / group
    folder.mkdir(parents=True, exist_ok=False)
    owner = folder / 'o'
    endpoint = folder / 'ENDPOINT.json'
    row = {'group': group, 'execution_kind': 'provider' if local_cli is None else 'synthetic_local_process',
           'folder': str(folder), 'owner_output': str(owner), 'consumer_output': str(folder / 'c'),
           'started_ns': began, 'deadline_ns': deadline, 'errors': [], 'consumer_valid_completion': False,
           'common_image_faults': [], 'new_renders': 0, 'Blender_processes': 0, 'paid_API_calls': 0,
           'provider_internal_raw_request': None, 'content_quality': 'unscored'}
    process = None
    record = None
    stdout_file = stderr_file = None
    input_sources = None
    try:
        prompt, manifest, input_sources = input_checks(plan)
        row['input_sources_sha256'] = input_sources
        config = {'group': group, 'output': str(owner), 'endpoint': str(endpoint),
                  'worker_deadline_ns': deadline, 'images_manifest': str(manifest), 'max_tool_calls': 4}
        save(folder / 'ACTOR_CONFIG.json', config)
        command = launch.python_command(HERE / 'actor.py', ['--config', folder / 'ACTOR_CONFIG.json'])
        row['actor_command'] = command
        stdout_file = (folder / 'actor.stdout.bin').open('wb')
        stderr_file = (folder / 'actor.stderr.bin').open('wb')
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file,
                                   env=consumer.safe_environment(os.environ), cwd=folder,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        row['owner_pid'] = process.pid
        ready_deadline = min(deadline, time.perf_counter_ns() + 40_000_000_000)
        while not endpoint.exists():
            if process.poll() is not None:
                if endpoint.exists():
                    break
                raise RuntimeError('actor_exited_before_endpoint')
            if time.perf_counter_ns() >= ready_deadline:
                raise TimeoutError('actor_endpoint_original_deadline')
            time.sleep(.02)
        actual = read(endpoint)
        if actual['actor_pid'] != process.pid or actual['chain_deadline_ns'] != deadline:
            raise ValueError('actor_PID_and_original_deadline_binding')
        record = consumer.consume_turn(episode_id='active-image-' + group, turn_index=1,
            folder=folder / 'c', work=folder / 'w',
            cell={'group': group, 'endpoint': str(endpoint), 'audit_dir': str(owner)},
            install={'python': str(launch.BASE)}, plan=plan, prompt=prompt,
            episode_deadline_ns=deadline, turn_deadline_ns=deadline, local_cli=local_cli)
        row['consumer_valid_completion'] = record['valid_completion']
        row['consumer_safe_to_continue'] = record['safe_to_continue']
        row['consumer_errors'] = record['errors']
        row['consumer_process_cleanup'] = record['process_cleanup']
        row['bridge_cleanup'] = record['bridge_cleanup']
        row['raw_usage_events'] = record['raw_usage_events']
        row['public_image_count'] = record['public_image_count']
        row['public_image_bytes'] = record['public_image_bytes']
        row['actual_tool_calls'] = len(record['tool_calls'])
    except BaseException as error:
        row['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.stdin.write(b'finish\n')
                    process.stdin.close()
                    process.wait(timeout=max(.01, min(5., (deadline - time.perf_counter_ns()) / 1e9)))
            except BaseException as error:
                row['errors'].append({'stage': 'owner_finish', 'type': type(error).__name__, 'message': str(error)})
            row['owner_process_cleanup'] = launch.stop_process(process, timeout=5)
        else:
            row['owner_process_cleanup'] = {'confirmed': False, 'scope': 'actor never launched'}
        for stream in (stdout_file, stderr_file):
            if stream is not None:
                stream.close()
        try:
            close = read(owner / 'CLOSE.json') if (owner / 'CLOSE.json').exists() else None
            row['owner_close'] = close
            row['owner_close_confirmed'] = bool(close and close.get('confirmed') is True and close.get('actor_pid') == row.get('owner_pid'))
            if record is not None:
                row['common_image_faults'] = common_image_faults(record, owner)
            row['input_readback_unchanged'] = input_sources is not None and input_checks(plan)[2] == input_sources
            if not row['input_readback_unchanged']:
                row['errors'].append({'stage': 'input_readback', 'message': 'source_input_changed_or_unavailable'})
            archive = folder.parent / (group + '.raw.zip')
            members = consumer.packer.capture_cell(folder, archive)
            row['originals'] = {'path': str(archive), 'sha256': sha(archive), 'bytes': archive.stat().st_size,
                                'members_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in members.items()}}
        except BaseException as error:
            row['errors'].append({'stage': 'postclose_archive', 'type': type(error).__name__,
                                  'message': str(error), 'traceback': traceback.format_exc()})
        row['stop_remaining_reasons'] = list(row['common_image_faults'])
        if not row.get('owner_close_confirmed') or not row['owner_process_cleanup']['confirmed']:
            row['stop_remaining_reasons'].append({'reason': 'owner_cleanup_unconfirmed'})
        if record is not None and not record['safe_to_continue']:
            row['stop_remaining_reasons'].append({'reason': 'consumer_cleanup_unconfirmed'})
        return publish_route(folder, row, began, deadline)


def run_batch(plan, runtime_root, local_cli=None):
    records = []
    stopped = None
    for group in plan['sequence']:
        if stopped:
            records.append({'group': group, 'execution_state': 'not_run', 'stop_reasons': stopped})
            continue
        record = run_route(group, plan, runtime_root, local_cli=local_cli)
        record['execution_state'] = 'completed' if record['outer_valid_completion'] else 'failed'
        records.append(record)
        if record['stop_remaining_reasons']:
            stopped = record['stop_remaining_reasons']
    result = {'schema': 'active-image-consumption-001-run-v1', 'records': records,
              'planned_routes': 2, 'planned_user_turns': 2, 'maximum_tools_per_route': 4,
              'actual_routes': sum(row['execution_state'] != 'not_run' for row in records),
              'provider_internal_raw_requests': None, 'fees': None, 'model_visual_consumption': 'unscored',
              'new_renders': 0, 'Blender_processes': 0, 'paid_API_calls': 0}
    save(runtime_root / 'RUN_RESULT.json', result)
    return result


def local_readback(local_root, plan):
    """Recheck saved real owner/stdio/synthetic CLI bytes without new processes."""
    result = read(local_root / 'RUN_RESULT.json')
    manifest_path = resolve_input(plan['inputs']['images_manifest'])
    manifest = read(manifest_path)
    expected = [row['sha256'] for row in manifest['images']]
    checks = []
    sources = {}
    route_content = []
    for row in result['records']:
        folder = Path(row['folder'])
        record_path = folder / 'c/CONSUMER.json'
        record = read(record_path)
        sources[str(record_path)] = sha(record_path)
        public = [block for tool in record['tool_calls'] for block in tool['item']['result']['content']
                  if block.get('type') == 'image']
        originals = []
        for path in sorted((folder / 'o').glob('tool_*/RESPONSE.json')):
            sources[str(path)] = sha(path)
            originals.extend(block for block in read(path)['result']['content'] if block.get('type') == 'image')
        wire = []
        for path in sorted((folder / 'c/attachments').glob('bridge_*/[0-9]*/RX.bin')):
            sources[str(path)] = sha(path)
            response = read(path)
            wire.extend(block for block in response.get('result', {}).get('content', []) if block.get('type') == 'image')
        hashes = [hashlib.sha256(consumer.base64.b64decode(block['data'], validate=True)).hexdigest() for block in public]
        checks.extend([
            {'group': row['group'], 'check': 'owner_stdio_CLI_image_blocks_equal', 'passed': originals == wire == public},
            {'group': row['group'], 'check': 'original_PNG_reference_order_and_payload', 'passed': hashes == expected},
            {'group': row['group'], 'check': 'original_handle_cleanup', 'passed': row['owner_process_cleanup']['confirmed']
                and row['consumer_process_cleanup']['confirmed']},
            {'group': row['group'], 'check': 'thin_EXIT_receipt', 'passed': record['bridge_cleanup']['confirmed'] is True},
            {'group': row['group'], 'check': 'full_route_deadline', 'passed': row['final_timing']['accepted_success'] is True},
            {'group': row['group'], 'check': 'generic_Python_retained', 'passed': any(
                call['item']['tool'] == 'execute_python' and
                json.loads(call['item']['result']['content'][0]['text'])['stdout'] == '42\n'
                for call in record['tool_calls'])},
        ])
        route_content.append(public)
    checks.append({'check': 'N_P_public_image_blocks_identical', 'passed': len(route_content) == 2 and route_content[0] == route_content[1]})
    value = {'schema': 'active-image-local-readback-v1', 'passed': all(row['passed'] for row in checks),
             'checks': checks, 'inputs_sha256': sources,
             'actual_synthetic_CLI_processes': 2, 'actual_actor_processes': 2,
             'actual_thin_processes': 2, 'real_Pro_sessions': 0, 'new_renders': 0,
             'scope': 'Original owner results, original stdio RX and completed synthetic CLI events. Real Codex CLI/provider/model receipt requires the later root-owned two-route run.'}
    save(local_root / 'LOCAL_READBACK.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--freeze', action='store_true')
    modes.add_argument('--run-models', action='store_true')
    modes.add_argument('--check-local', action='store_true')
    options = parser.parse_args()
    plan = read(HERE / 'PLAN.json')
    if options.freeze:
        value = {'schema': 'active-image-consumption-001-source-freeze-v1', 'runtime_sources': source_files(plan),
                 'CLI_interface': read(consumer.CONTINUITY / 'cli/CLI_INTERFACE.json'),
                 'settings': consumer.previous.settings(), 'launch_contract': launch.describe()}
        path = HERE / 'FROZEN.json'
        if path.exists():
            raise FileExistsError('source_freeze_already_exists')
        save(path, value)
        print(json.dumps({'frozen': True, 'sources': len(value['runtime_sources'])}))
        return
    if options.check_local:
        local_root = HERE / 'local' / ('a' + str(1 + len(list((HERE / 'local').glob('a*')))).zfill(2))
        local_root.mkdir(parents=True, exist_ok=False)
        fixture = HERE / 'fake_cli.py'
        result = run_batch(plan, local_root, local_cli={'command': [str(launch.BASE), '-I', '-B', str(fixture)], 'script_sha256': sha(fixture)})
        readback = local_readback(local_root, plan)
        save(local_root / 'LOCAL_CHECK.json', {'passed': all(row['outer_valid_completion'] for row in result['records'])
             and readback['passed'],
             'real_provider_sessions': 0, 'scope': 'Synthetic CLI exercises real stdio, owner and image archives. Actual CLI/provider image receipt remains untested.'})
        print(json.dumps({'local_result': str(local_root / 'LOCAL_CHECK.json')}))
        return
    frozen = check_frozen(plan)
    if not options.run_models:
        print(json.dumps({'source_unchanged': True, 'sources': len(frozen['runtime_sources']), 'provider_sessions_started': 0}))
        return
    if plan.get('model_consumer_enabled') is not True:
        raise ValueError('real_model_execution_not_enabled')
    runtime_root = resolve_input(plan['runtime_root'])
    if not runtime_root.is_relative_to(HERE):
        raise ValueError('new_namespace_output_required')
    with (HERE / 'FORMAL_STARTED.json').open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'source_freeze_sha256': sha(HERE / 'FROZEN.json')}, stream)
    runtime_root.mkdir(parents=True, exist_ok=False)
    result = run_batch(plan, runtime_root)
    print(json.dumps({'actual_routes': result['actual_routes'], 'planned_user_turns': 2,
                      'execution_counts': {state: sum(row['execution_state'] == state for row in result['records']) for state in ('completed', 'failed', 'not_run')}}))


if __name__ == '__main__':
    main()
