"""Fixed six-slot coverage consumption; only --run-models invokes real Pro."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
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


SEQUENCE = [('N1', 'N'), ('P1', 'P'), ('P2', 'P'), ('N2', 'N'), ('N3', 'N'), ('P3', 'P')]


def input_checks(plan):
    if [(row['slot'], row['group']) for row in plan['sequence']] != SEQUENCE:
        raise ValueError('fixed_six_fresh_slot_sequence')
    if plan['route_deadline_seconds'] != 450 or plan['max_tool_calls'] != 12 or plan['max_render_attempts'] != 6:
        raise ValueError('original_deadline_tool_and_render_budgets')
    prompt = resolve_input(plan['inputs']['prompt'])
    manifest_path = resolve_input(plan['inputs']['input_manifest'])
    sources = {str(prompt): sha(prompt), str(manifest_path): sha(manifest_path)}
    manifest = read(manifest_path)
    if manifest.get('schema') != 'active-coverage-consumption-001-inputs-v1':
        raise ValueError('registered_common_source_manifest')
    for key in ('scene', 'cameras', 'core', 'adapter'):
        specification = manifest[key]
        path = Path(specification['path']).resolve() if 'path' in specification else (manifest_path.parent / specification['file']).resolve()
        actual = sha(path)
        if actual != specification['sha256']:
            raise ValueError('registered_common_source_hash_' + key)
        sources[str(path)] = actual
    return prompt.read_bytes(), manifest_path, sources


def source_files(plan):
    _, _, sources = input_checks(plan)
    files = [HERE / name for name in ('driver.py', 'consumer.py', 'runtime_handle.py', 'actor.py',
        'common_observation.py', 'image_content.py', 'fake_cli.py', 'PLAN.json', 'PUBLIC_INTERFACE.md',
        'prep_smoke.py', 'seal_delivery.py', 'PUBLIC_TOOLS.json')]
    files.extend([
        Path(consumer.previous.__file__), Path(consumer.cli.__file__), Path(consumer.packer.__file__),
        Path(consumer.compatibility.__file__), Path(launch.__file__), launch.BOOTSTRAP,
        consumer.previous.ATTACH_PATH, consumer.CONTINUITY / 'cli/CLI_INTERFACE.json',
        launch.BASE, consumer.runtime_handle.SOURCE,
    ])
    contract = launch.describe()
    files.extend([Path(contract['dependency_manifest_path']),
                  *[Path(row['path']) for row in contract['expected_dependencies'].values()]])
    files.append(Path(read(consumer.CONTINUITY / 'cli/CLI_INTERFACE.json')['executable']))
    for path in files:
        sources[str(path.resolve())] = sha(path)
    for name in ('TRUTH.json', 'SCORING_SCHEMA.json', 'score_answers.py', 'DISPATCH_PLAN.md', 'PREPARATION_BEGAN.json'):
        path = HERE / 'admin' / name
        sources[str(path.resolve())] = sha(path)
    build_path = ROOT / 'verification/m4_surface_scan_compact_facts_001/installation/run_01/FIXED_BUILD_INPUTS.json'
    fixed = read(build_path)
    dependencies = read(contract['dependency_manifest_path'])
    if (fixed['source_count'] != 138 or
            fixed['source_sha256'] != '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6' or
            sha(build_path) != dependencies['fixed_build_inputs_sha256']):
        raise ValueError('fixed_product_build_identity')
    sources[str(build_path.resolve())] = sha(build_path)
    product_root = ROOT / '.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'
    for specification in fixed['manifest']:
        path = (product_root / specification['path']).resolve()
        actual = sha(path)
        if actual != specification['sha256']:
            raise ValueError('fixed_product_source_changed:' + specification['path'])
        sources[str(path)] = actual
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
    render_attempts = metrics.get('common', {}).get('render_attempts')
    if type(render_attempts) is not int or not 0 <= render_attempts <= 6:
        faults.append({'reason': 'common_render_attempt_ledger_invalid', 'observed': render_attempts})
    if metrics.get('failed_image_constructions', 0):
        faults.append({'reason': 'registered_image_construction_failed', 'count': metrics['failed_image_constructions']})
    if metrics.get('post_construction_failures', 0):
        faults.append({'reason': 'constructed_image_delivery_preparation_failed', 'count': metrics['post_construction_failures']})
    if metrics.get('failed_or_unknown_socket_sends', 0):
        faults.append({'reason': 'actual_owner_socket_send_failed_or_unknown', 'count': metrics['failed_or_unknown_socket_sends']})
    if metrics.get('common', {}).get('runtime_faults'):
        faults.append({'reason': 'common_observation_runtime_failed', 'original_faults': metrics['common']['runtime_faults']})
    if record.get('unknown_image_payloads', 0):
        faults.append({'reason': 'CLI_completed_image_content_invalid', 'count': record['unknown_image_payloads']})
    tools_path = owner / 'TOOLS.json'
    tools = read(tools_path).get('tools', []) if tools_path.exists() else []
    for original in tools:
        if original.get('response_serialization_error'):
            faults.append({'reason': 'actual_tool_response_serialization_failed', 'attempt': original['attempt'],
                           'original_error': original['response_serialization_error']})
    completed = record.get('tool_calls', [])
    if len(tools) != len(completed):
        missing_owner_images = [row['attempt'] for row in tools[len(completed):]
                               if row.get('content_metrics', {}).get('image_blocks', 0)]
        extra_CLI_images = [call['item'].get('id') for call in completed[len(tools):]
                            if any(block.get('type') == 'image' for block in (call['item'].get('result') or {}).get('content', []))]
        if missing_owner_images or extra_CLI_images:
            faults.append({'reason': 'image_tool_completed_receipt_count_binding',
                           'owner_image_attempts_without_CLI_receipt': missing_owner_images,
                           'CLI_image_items_without_owner_receipt': extra_CLI_images,
                           'owner_tool_count': len(tools), 'CLI_completed_count': len(completed)})
    for original, observed in zip(tools, record.get('tool_calls', [])):
        item = observed['item']
        response_path = owner / ('tool_' + str(original['attempt']).zfill(2)) / 'RESPONSE.json'
        if not response_path.exists():
            faults.append({'reason': 'owner_business_response_missing', 'attempt': original['attempt']})
            continue
        response = read(response_path)
        source_images = original.get('content_metrics', {}).get('image_blocks', 0)
        if source_images and not (consumer.packer.encoded(response.get('result')) == consumer.packer.encoded(item.get('result'))
                                  or consumer.compatibility.successful_result_matches(response, item)):
            faults.append({'reason': 'completed_image_response_binding_failed', 'attempt': original['attempt'],
                           'CLI_item_id': item.get('id')})
    return faults


def terminal_service_faults(record):
    """Retain concrete terminal availability evidence; successful retries pass."""
    if record.get('valid_completion'):
        return []
    terminal = [row for row in record.get('errors', []) if row.get('event', {}).get('type') in ('error', 'turn.failed')]
    evidence = json.dumps(terminal, ensure_ascii=False)
    patterns = (
        r'\bHTTP\s*(?:status\s*)?(?:401|403|429|503)\b',
        r'\b(?:status|status_code|code)\s*["\s]*[:=]\s*(?:401|403|429|503)\b',
        r'\b(?:usage limit|quota exceeded|insufficient_quota|not authenticated|authentication failed|login required)\b',
    )
    if terminal and any(re.search(pattern, evidence, re.IGNORECASE) for pattern in patterns):
        return [{'reason': 'terminal_service_or_account_unavailable', 'original_errors': terminal}]
    return []


def outer_accepted(row):
    return bool(row.get('consumer_valid_completion') and row.get('consumer_safe_to_continue')
        and row.get('owner_close_confirmed') and row.get('owner_process_cleanup', {}).get('confirmed')
        and row.get('consumer_process_cleanup', {}).get('confirmed')
        and (row.get('runtime_binding') or {}).get('confirmed') is True
        and (row.get('runtime_exit') or {}).get('confirmed') is True
        and row.get('bridge_cleanup', {}).get('confirmed') is not False
        and row.get('input_readback_unchanged') is True
        and not row['common_image_faults'] and not row['errors'])


def publish_route(folder, row, began, deadline):
    row['outer_valid_completion'] = outer_accepted(row)
    save(folder / 'RESULT.json', row)
    # Read back the closed record inside the original budget.
    if read(folder / 'RESULT.json') != row:
        row['errors'].append({'stage': 'publication', 'message': 'result_readback_mismatch'})
        row['outer_valid_completion'] = False
        save(folder / 'RESULT.json', row)
    closed = time.perf_counter_ns()
    if closed >= deadline:
        row['outer_valid_completion'] = False
        row['errors'].append({'stage': 'publication', 'type': 'TimeoutError', 'message': 'original_route_deadline_through_result_close'})
        save(folder / 'RESULT.json', row)
        closed = time.perf_counter_ns()
    timing = {'started_ns': began, 'result_closed_ns': closed, 'elapsed_ns': closed - began,
              'original_deadline_ns': deadline, 'accepted_success': row['outer_valid_completion'] and closed < deadline,
              'scope': 'Before input checks and actor startup through original CLI/actor handles, retained thin handle, raw ZIP, input readback and RESULT write/close/readback.'}
    save(folder / 'FINAL_TIMING.json', timing)
    row['final_timing'] = timing
    return row


def run_route(slot, group, plan, runtime_root, local_cli=None):
    began = time.perf_counter_ns()
    deadline = began + 450_000_000_000
    folder = runtime_root / slot
    folder.mkdir(parents=True, exist_ok=False)
    owner = folder / 'o'
    endpoint = folder / 'ENDPOINT.json'
    row = {'slot': slot, 'group': group, 'execution_kind': 'provider' if local_cli is None else 'synthetic_local_process',
           'folder': str(folder), 'owner_output': str(owner), 'consumer_output': str(folder / 'c'),
           'started_ns': began, 'deadline_ns': deadline, 'errors': [], 'consumer_valid_completion': False,
           'common_image_faults': [], 'new_renders': None, 'Blender_processes': 0, 'paid_API_calls': 0,
           'provider_internal_raw_request': None, 'content_quality': 'unscored'}
    process = None
    record = None
    stdout_file = stderr_file = None
    input_sources = None
    try:
        prompt, manifest, input_sources = input_checks(plan)
        row['input_sources_sha256'] = input_sources
        config = {'group': group, 'output': str(owner), 'endpoint': str(endpoint),
                  'worker_deadline_ns': deadline, 'input_manifest': str(manifest), 'max_tool_calls': 12,
                  'max_render_attempts': 6}
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
        record = consumer.consume_turn(episode_id='active-coverage-' + slot, turn_index=1,
            folder=folder / 'c', work=folder / 'w',
            cell={'group': group, 'endpoint': str(endpoint), 'audit_dir': str(owner)},
            install={'python': str(launch.BASE)}, plan=plan, prompt=prompt,
            episode_deadline_ns=deadline, turn_deadline_ns=deadline, local_cli=local_cli)
        row['consumer_valid_completion'] = record['valid_completion']
        row['consumer_pid'] = record['consumer_pid']
        row['observed_thread_id'] = record['thread_id']
        row['prompt_submitted_ns'] = record['prompt_submitted_ns']
        row['consumer_safe_to_continue'] = record['safe_to_continue']
        row['consumer_errors'] = record['errors']
        row['consumer_process_cleanup'] = record['process_cleanup']
        row['bridge_cleanup'] = record['bridge_cleanup']
        row['runtime_binding'] = record['runtime_binding']
        row['runtime_exit'] = record['runtime_exit']
        row['answer_present'] = bool(record.get('final'))
        row['turn_terminal_event_seen'] = record.get('turn_completed_ns') is not None
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
            metrics_path = owner / 'METRICS.json'
            row['owner_metrics'] = read(metrics_path) if metrics_path.exists() else None
            row['new_renders'] = row['owner_metrics']['common']['render_attempts'] if row['owner_metrics'] is not None else None
            archive = folder.parent / (slot + '.raw.zip')
            members = consumer.packer.capture_cell(folder, archive)
            row['originals'] = {'path': str(archive), 'sha256': sha(archive), 'bytes': archive.stat().st_size,
                                'members_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in members.items()}}
        except BaseException as error:
            row['errors'].append({'stage': 'postclose_archive', 'type': type(error).__name__,
                                  'message': str(error), 'traceback': traceback.format_exc()})
        row['stop_remaining_reasons'] = list(row['common_image_faults'])
        if record is not None:
            row['stop_remaining_reasons'].extend(terminal_service_faults(record))
        if not row.get('input_readback_unchanged'):
            row['stop_remaining_reasons'].append({'reason': 'shared_input_source_changed_or_unavailable'})
        if record is None:
            row['stop_remaining_reasons'].append({'reason': 'consumer_execution_state_unknown'})
        if not row.get('owner_close_confirmed') or not row['owner_process_cleanup']['confirmed']:
            row['stop_remaining_reasons'].append({'reason': 'owner_cleanup_unconfirmed'})
        if record is not None and not record['safe_to_continue']:
            row['stop_remaining_reasons'].append({'reason': 'consumer_cleanup_unconfirmed'})
        return publish_route(folder, row, began, deadline)


def run_batch(plan, runtime_root, local_cli=None):
    began = time.perf_counter_ns()
    records = []
    stopped = None
    for scheduled in plan['sequence']:
        slot, group = scheduled['slot'], scheduled['group']
        if stopped:
            records.append({'slot': slot, 'group': group, 'execution_state': 'not_run', 'stop_reasons': stopped})
            continue
        try:
            record = run_route(slot, group, plan, runtime_root, local_cli=local_cli)
        except BaseException as error:
            record = {'slot': slot, 'group': group, 'outer_valid_completion': False,
                      'errors': [{'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}],
                      'stop_remaining_reasons': [{'reason': 'outer_execution_state_unknown'}]}
        record['execution_state'] = 'completed' if record['outer_valid_completion'] else 'failed'
        records.append(record)
        if record['stop_remaining_reasons']:
            stopped = record['stop_remaining_reasons']
    result = {'schema': 'active-coverage-consumption-001-run-v1', 'records': records,
              'planned_routes': 6, 'planned_user_turns': 6, 'maximum_tools_per_route': 12,
              'maximum_render_attempts_per_route': 6,
              'actual_routes': sum(row['execution_state'] != 'not_run' for row in records),
              'actual_CLI_processes': sum(row.get('consumer_pid') is not None for row in records),
              'observed_fresh_threads': [row['observed_thread_id'] for row in records if row.get('observed_thread_id')],
              'provider_internal_raw_requests': None, 'fees': None, 'content_quality': 'unscored',
              'Blender_processes': 0, 'paid_API_calls': 0,
              'started_ns': began, 'before_publication_ns': time.perf_counter_ns()}
    save(runtime_root / 'RUN_RESULT.json', result)
    closed = time.perf_counter_ns()
    save(runtime_root / 'BATCH_TIMING.json', {'started_ns': began, 'RUN_RESULT_closed_ns': closed,
         'elapsed_ns': closed - began, 'scope': 'Entire fixed sequential batch through aggregate result write/close.'})
    return result


def local_readback(local_root, rows):
    checks = []
    for row in rows:
        record = read(Path(row['consumer_output']) / 'CONSUMER.json')
        expected_eof = True if row['slot'] == 'normal_EOF' else None
        checks.extend([
            {'slot': row['slot'], 'check': 'runtime_actual_base_binding', 'passed': row['runtime_binding']['confirmed'] is True},
            {'slot': row['slot'], 'check': 'retained_thin_handle_exit_close', 'passed': row['runtime_exit']['confirmed'] is True},
            {'slot': row['slot'], 'check': 'EOF_receipt_separate', 'passed': row['bridge_cleanup']['confirmed'] is expected_eof},
            {'slot': row['slot'], 'check': 'current_outer_gate', 'passed': row['outer_valid_completion'] is True},
            {'slot': row['slot'], 'check': 'raw_stdout_genuine', 'passed': record['stdout_raw_bytes'] > 0
                and sha(Path(row['consumer_output']) / 'stdout.raw.bin') == record['stdout_raw_sha256']},
            {'slot': row['slot'], 'check': 'zero_raster', 'passed': row.get('new_renders') == 0},
        ])
    good = {'consumer_valid_completion': True, 'consumer_safe_to_continue': True,
            'owner_close_confirmed': True, 'owner_process_cleanup': {'confirmed': True},
            'consumer_process_cleanup': {'confirmed': True}, 'runtime_binding': {'confirmed': True},
            'runtime_exit': {'confirmed': True}, 'bridge_cleanup': {'confirmed': None},
            'input_readback_unchanged': True, 'common_image_faults': [], 'errors': []}
    checks.append({'check': 'gate_valid_with_EOF_unknown_and_exit_proven', 'passed': outer_accepted(good)})
    for key in ('consumer_safe_to_continue', 'runtime_binding', 'runtime_exit', 'common_image_faults'):
        bad = dict(good)
        bad[key] = [{'reason': 'control'}] if key == 'common_image_faults' else {'confirmed': False} if key in ('runtime_binding', 'runtime_exit') else False
        checks.append({'check': 'gate_rejects_' + key, 'passed': not outer_accepted(bad)})
    value = {'passed': all(row['passed'] for row in checks), 'checks': checks,
             'actual_synthetic_CLI_processes': 2, 'actual_actor_processes': 2,
             'actual_thin_processes': 2, 'real_Pro_sessions': 0, 'new_renders': 0,
             'scope': 'Two actual Win held-handle thin lifecycle controls and pure outer acceptance controls. No image generation or Pro qualification.'}
    save(local_root / 'LOCAL_CHECK.json', value)
    return value


def shared_fault_controls(output):
    """Pure saved-receipt controls, with no subprocess or image generation."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = (
        ('ordinary_tool_error', {}, {}, [], False),
        ('post_encoding_failure', {'post_construction_failures': 1}, {}, [], True),
        ('actual_send_failure', {'failed_or_unknown_socket_sends': 1}, {}, [], True),
        ('actual_serialization_failure', {}, {}, [{'attempt': 1, 'response_serialization_error': {'type': 'ValueError', 'message': 'fixture'}}], True),
        ('common_runtime_failure', {}, {'runtime_faults': [{'stage': 'render', 'type': 'ValueError'}]}, [], True),
        ('unknown_render_ledger', {}, {'render_attempts': None}, [], True),
        ('missing_image_completion', {}, {}, [{'attempt': 1, 'content_metrics': {'image_blocks': 1}}], True),
    )
    checks = []
    for name, metric_changes, common_changes, tools, expected in cases:
        owner = output / name
        owner.mkdir()
        metrics = {'common': {'render_attempts': 0, 'runtime_faults': [], **common_changes},
                   'failed_image_constructions': 0, 'post_construction_failures': 0,
                   'failed_or_unknown_socket_sends': 0, **metric_changes}
        record = {'tool_calls': [], 'unknown_image_payloads': 0}
        if name == 'ordinary_tool_error':
            tools = [{'attempt': 1, 'content_metrics': {'image_blocks': 0}, 'response_serialization_error': None}]
            folder = owner / 'tool_01'
            folder.mkdir()
            result = {'content': [{'type': 'text', 'text': 'ordinary Python syntax error'}], 'isError': True}
            save(folder / 'RESPONSE.json', {'jsonrpc': '2.0', 'id': 1, 'result': result})
            record['tool_calls'] = [{'item': {'id': 'fixture', 'status': 'failed', 'result': result}}]
        save(owner / 'METRICS.json', metrics)
        save(owner / 'TOOLS.json', {'tools': tools})
        observed = common_image_faults(record, owner)
        checks.append({'case': name, 'expected_shared_fault': expected, 'observed_faults': observed,
                       'passed': bool(observed) is expected})
    terminal = {'valid_completion': False, 'errors': [{'event': {'type': 'turn.failed', 'error': {'status': 503}}}]}
    checks.append({'case': 'explicit_terminal_503', 'passed': bool(terminal_service_faults(terminal))})
    checks.append({'case': 'recovered_terminal_observation', 'passed': not terminal_service_faults(dict(terminal, valid_completion=True))})
    checks.append({'case': 'ordinary_quota_word', 'passed': not terminal_service_faults({'valid_completion': False,
        'errors': [{'type': 'ValueError', 'message': 'quota accounting field'}]})})
    value = {'passed': all(row['passed'] for row in checks), 'checks': checks,
             'driver_sha256': sha(HERE / 'driver.py'), 'new_processes': 0, 'new_renders': 0, 'real_Pro_sessions': 0,
             'scope': 'Actual shared-fault classifier against synthetic receipt files, plus terminal availability controls.'}
    save(output / 'RESULTS.json', value)
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
        value = {'schema': 'active-coverage-consumption-001-source-freeze-v1', 'runtime_sources': source_files(plan),
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
        local_cli = {'command': [str(launch.BASE), '-I', '-B', str(fixture)], 'script_sha256': sha(fixture)}
        rows = [run_route('normal_EOF', 'N', plan, local_root, local_cli),
                run_route('forced_no_EXIT', 'P', plan, local_root, local_cli)]
        save(local_root / 'RUN_RESULT.json', {'records': rows, 'real_Pro_sessions': 0, 'new_renders': 0})
        checked = local_readback(local_root, rows)
        print(json.dumps({'local_result': str(local_root / 'LOCAL_CHECK.json'), 'passed': checked['passed']}))
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
    print(json.dumps({'actual_routes': result['actual_routes'], 'planned_user_turns': 6,
                      'execution_counts': {state: sum(row['execution_state'] == state for row in result['records']) for state in ('completed', 'failed', 'not_run')}}))


if __name__ == '__main__':
    main()
