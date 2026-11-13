"""Fixed six-episode outer owner for the continuous consumption experiment.

Importing this module performs no process, Blender or model operation. The
provider gate is reached only by --run-models after the frozen preparation and
the exclusive formal reservation have been checked.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time
import traceback


BATCH = Path(__file__).resolve().parent.parent
ROOT = BATCH.parents[1]
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
QUAL = ROOT / 'verification/m4_surface_scan_001/qualification'
CYCLE = 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001'
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
TURNS = ('BASE', 'REPEAT', 'EDIT')
EPISODE_NS = 590 * 10**9
TURN_NS = 450 * 10**9
PROMPT_HASHES = (
    '6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc',
    '1556e86013d52b1ca222237f6e5df33d389d33e95c8e3df3bd218edb4e5549d6',
)
SOURCE_SHA = '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
ASSET_SHA = '7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66'
ACTOR = FIX1 / 'runtime/actor.py'
COORDINATOR = FIX1 / 'consumer/episode.py'
TRANSPORT = FIX1 / 'runtime/consumer_transport.py'
OLD_DRIVER = ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/driver.py'
ATTACH = ROOT / 'verification/native_plugin_complex_003/reused/stdio_attach.py'
POSTCLOSE = ROOT / 'verification/m4_surface_scan_continuity_001_fix2/engineering/run_candidate.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                          encoding='utf8', newline='\n')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def check_deadline(deadline):
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError('original_episode_590s_deadline')


def failure(error, stage):
    return {'stage': stage, 'type': type(error).__name__, 'message': str(error),
            'traceback': traceback.format_exc()}


def contract(plan):
    """Validate the fixed plan without launching a consumer or an owner."""
    assert plan['cycle'] == CYCLE, 'current_cycle_required'
    assert tuple(row['cell'] for row in plan['sequence']) == CELLS, 'fixed_six_episode_order'
    assert len({row['anonymous_episode_id'] for row in plan['sequence']}) == 6, 'unique_anonymous_episodes'
    turn_ids = []
    for row in plan['sequence']:
        assert row['episode'] == row['cell'] and row['group'] == row['cell'][0], 'episode_arm_binding'
        assert row['pair'] == row['round'] == int(row['cell'][1]), 'fixed_pair_binding'
        assert len(row['anonymous_turn_ids']) == 3, 'three_anonymous_turns'
        turn_ids.extend(row['anonymous_turn_ids'])
    assert len(set(turn_ids)) == 18, 'unique_anonymous_turns'
    assert plan['model_consumer_enabled'] is True, 'formal_provider_gate_required'
    assert plan['image_count'] == plan['new_images'] == plan['inputs']['image_bytes'] == 0, 'zero_images'
    assert plan['inputs']['image'] is None and plan['inputs']['image_sha256'] is None, 'no_image_input'
    expected = {'episode_seconds': 590, 'turn_seconds': 450, 'actor_startup_seconds': 40,
                'tool_timeout_seconds': 30, 'episode_tool_attempts': 32,
                'episode_host_nonclose_requests': 128, 'episode_tool_response_bytes': 1048576,
                'code_bytes': 262144, 'requested_model': 'gpt-6.1-sol',
                'requested_effort': 'medium', 'service_tier': 'default'}
    for key, value in expected.items():
        assert plan[key] == value, 'fixed_contract_' + key
    assert plan['quality_before_cost'] is True and plan['usage_aggregation'] is None, 'quality_first_raw_usage'
    assert plan['replace_failed_episodes'] is False and plan['stop_unavailable_or_unknown'] is True
    ready = plan['installation_ready']
    assert ready['commit'] == '452b44d2dcf231d6675bef54e568db0431a29261'
    assert ready['source_count'] == 138 and ready['source_sha256'] == SOURCE_SHA, 'fixed_C_source'
    assert ready['version'] == '9.7.2+m4.surface.scan.compact.r1', 'fixed_C_installation'
    assert ready['wheel_sha256'] == 'f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792'
    assert Path(plan['runtime_root']).resolve() == (ROOT / '.m4cc1').resolve(), 'short_runtime_root'
    assert plan['inputs']['scene_sha256'] == ASSET_SHA, 'fixed_scene'
    assert Path(plan['inputs']['scene']).resolve() == (QUAL / 'assembly.blend').resolve(), 'fixed_scene_path'
    assert read(BATCH / 'inputs/C_READY.json') == ready, 'frozen_common_dependency_READY'
    assert read(BATCH / 'inputs/C_PUBLIC_TOOLS.json') == plan['read_schemas'], 'frozen_C_public_schema'
    prompts = [BATCH / plan['inputs'][key] for key in ('prompt_base', 'prompt_recheck')]
    assert tuple(sha(path) for path in prompts) == PROMPT_HASHES, 'fixed_prompt_bytes'
    assert tuple(path.stat().st_size for path in prompts) == (405, 435), 'fixed_prompt_sizes'
    assert prompts[1].read_bytes() == '请重新检查当前场景。'.encode('utf8') + prompts[0].read_bytes(), 'common_recheck_prefix'
    assert sha(Path(plan['inputs']['scene'])) == ASSET_SHA, 'asset_bytes_changed'
    return {'planned_episodes': 6, 'planned_turns': 18, 'model_calls': 0, 'Blender_calls': 0}


def validate_preparation(frozen, require_committed=True):
    """Check the current batch and its committed bytes, using its dynamic path."""
    path = BATCH / 'PREPARATION.json'
    relative = path.relative_to(ROOT).as_posix()
    assert BATCH.name == 'm4_surface_scan_continuous_consumption_001', 'current_batch_required'
    assert read(path) == frozen, 'current_preparation_bytes_required'
    for row in frozen['files']:
        source = BATCH / row['path']
        assert source.resolve().is_relative_to(BATCH.resolve()), 'frozen_path_outside_batch'
        assert sha(source) == row['sha256'], row['path']
        if 'bytes' in row:
            assert source.stat().st_size == row['bytes'], row['path']
    for source, expected in frozen['external_sha256'].items():
        assert sha(source) == expected, source
    if require_committed:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        assert head != frozen['preparation_parent_commit'], 'preparation_must_be_committed'
        committed = subprocess.check_output(['git', 'show', head + ':' + relative], cwd=ROOT)
        assert committed == path.read_bytes(), 'current_preparation_commit_required'
        for row in frozen['files']:
            source = BATCH / row['path']
            committed = subprocess.check_output(['git', 'show', head + ':' + source.relative_to(ROOT).as_posix()], cwd=ROOT)
            assert digest(committed) == row['sha256'], 'frozen_source_not_committed:' + row['path']
    return {'preparation_path': relative, 'files': len(frozen['files']),
            'external_files': len(frozen['external_sha256']), 'committed_verified': require_committed}


def source_guard(plan):
    """Bind reused execution code, fixed launcher and CLI without running them."""
    interface_path = ROOT / 'verification/m4_surface_scan_continuity_001/cli/CLI_INTERFACE.json'
    interface = read(interface_path)
    assert interface['executable_sha256'] == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6', 'fixed_CLI_identity'
    assert sha(interface['executable']) == interface['executable_sha256'], 'frozen_CLI_changed'
    paths = [Path(__file__), ACTOR, COORDINATOR, TRANSPORT, OLD_DRIVER, ATTACH, POSTCLOSE,
             interface_path, Path(plan['installation_ready']['entry']), BATCH / 'PLAN.json']
    return {str(path.resolve()): sha(path) for path in paths}


def execution_rows(coordinator):
    """Preserve attempted failures even when the consumer threw before a record."""
    actual = {row['turn_label']: row for row in coordinator.get('turns', [])}
    result = []
    for index, label in enumerate(TURNS, 1):
        row = actual.get(label)
        consumer = None if row is None else row.get('consumer')
        state = 'not_run' if row is None else 'failed'
        if consumer is not None and consumer.get('valid_completion') is True:
            state = 'completed'
        result.append({'turn_index': index, 'turn_label': label, 'execution_state': state,
                       'attempted': row is not None, 'consumer_record_present': consumer is not None,
                       'consumer_status': None if consumer is None else consumer.get('status'),
                       'folder': None if row is None else row.get('folder'),
                       'thread_id': None if consumer is None else consumer.get('thread_id')})
    return result


def recorded_coordinator(runtime):
    """Read surviving turn records after an exception, without retrying work."""
    result_path = runtime / 'c/EPISODE_RESULT.json'
    if result_path.exists():
        return read(result_path)
    result = {'turns': []}
    for index, label in enumerate(TURNS, 1):
        turn = runtime / 'c/turns' / label
        if turn.exists():
            row = {'turn_index': index, 'turn_label': label, 'folder': str(turn)}
            if (turn / 'CONSUMER.json').exists():
                row['consumer'] = read(turn / 'CONSUMER.json')
            result['turns'].append(row)
    return result


def counts(rows):
    return {'planned': 3, **{state: sum(row['execution_state'] == state for row in rows)
                             for state in ('completed', 'failed', 'not_run')}}


def continuity(coordinator):
    records = [row.get('consumer') for row in coordinator.get('turns', [])]
    present = [row for row in records if row is not None]
    ids = [row.get('thread_id') for row in present]
    resume = [row.get('expected_thread_id') for row in present]
    complete = len(present) == 3 and all(ids) and len(set(ids)) == 1 and resume == [None, ids[0], ids[0]]
    observed_sessions = set()
    for row in coordinator.get('turns', []):
        for name in ('status_before', 'status_after'):
            observed_sessions.update(row.get(name, {}).get('observed_product_session_ids', []))
    return {'three_turn_thread_continuity': complete, 'thread_ids': ids,
            'expected_thread_ids': resume, 'observed_product_session_ids': sorted(observed_sessions),
            'configured_session_id': 'current-scene',
            'scope': 'Actual CLI thread IDs and explicit resume bindings; configured session is not proof of product use'}


def unavailable_evidence(coordinator):
    """Use terminal consumer failures, retaining retry text without treating it as failure."""
    pattern = re.compile(r'\b(?:http(?:/[\d.]+)?(?:\s+status)?|status(?:\s+code)?|error(?:\s+code)?)'
                         r'\s*[:=]?\s*(?:401|403|429|503)\b', re.I)
    phrases = ('authentication failed', 'authorization failed', 'not authenticated', 'not logged in',
               'login required', 'invalid api key', 'usage limit reached', 'usage limit exceeded',
               'quota exceeded', 'insufficient quota', 'rate limit exceeded', 'service unavailable')

    def unavailable(error):
        if isinstance(error, dict):
            for key, value in error.items():
                if key in ('status', 'status_code', 'http_status', 'code') and str(value) in ('401', '403', '429', '503'):
                    return True
                if isinstance(value, (dict, list)) and unavailable(value):
                    return True
        if isinstance(error, list):
            return any(unavailable(value) for value in error)
        text = json.dumps(error, ensure_ascii=False)
        return bool(pattern.search(text) or any(phrase in text.casefold() for phrase in phrases))

    found = []
    for turn in coordinator.get('turns', []):
        consumer = turn.get('consumer')
        if consumer is None or consumer.get('valid_completion') is True:
            continue
        if (consumer.get('turn_completed_ns') is not None and consumer.get('final_received_ns') is not None
                and consumer.get('exit_code') == 0):
            # Strict execution errors remain, while a terminal completion proves
            # a prior retry message did not leave the provider unavailable.
            continue
        # Errors are terminal facts. Recovered retry observations alone never stop the batch.
        for error in consumer.get('errors', []):
            if unavailable(error):
                found.append({'turn': turn['turn_label'], 'source': 'consumer.errors', 'value': error})
        summary = consumer.get('summary', {})
        for error in summary.get('errors', []):
            if unavailable(error):
                found.append({'turn': turn['turn_label'], 'source': 'consumer.summary.errors', 'value': error})
    return found


def stop_reasons(row):
    reasons = []
    if row.get('owner_started') and row.get('owner_finish', {}).get('confirmed') is not True:
        reasons.append({'reason': 'owned_close_unconfirmed', 'receipt': row.get('owner_finish')})
    for turn in row.get('coordinator', {}).get('turns', []):
        record = turn.get('consumer')
        if record is None:
            reasons.append({'reason': 'attempted_consumer_lifecycle_unconfirmed', 'turn': turn['turn_label'],
                            'scope': 'Coordinator registered this turn but no consumer cleanup record returned'})
            continue
        if record.get('mutation_unknown') or record.get('bridge_protocol_errors') or record.get('unexpected_tool_deviations'):
            reasons.append({'reason': 'consumer_action_state_unknown', 'turn': turn['turn_label'],
                            'mutation_unknown': record.get('mutation_unknown'),
                            'bridge_protocol_errors': record.get('bridge_protocol_errors'),
                            'unexpected_tool_deviations': record.get('unexpected_tool_deviations')})
        if (record.get('process_reaped') is False or record.get('readers_stopped') is False
                or record.get('bridge_cleanup', {}).get('confirmed') is False):
            reasons.append({'reason': 'consumer_cleanup_unconfirmed', 'turn': turn['turn_label']})
    unavailable = unavailable_evidence(row.get('coordinator', {}))
    if unavailable:
        reasons.append({'reason': 'provider_unavailable', 'evidence': unavailable})
    return reasons


def prepare_config(slot, plan, runtime, started, deadline):
    """Bind the unchanged actor config before the caller launches it once."""
    check_deadline(deadline)
    startup_deadline = min(deadline, started + 40 * 10**9)
    contract(plan)
    guard = source_guard(plan)
    save(runtime / 'SOURCE_GUARD_BEFORE.json', guard)
    ready = plan['installation_ready']
    internal = 'N' if slot['group'] == 'N' else 'P'
    config = {'group': internal, 'external_group': slot['group'], 'task': 'T1',
              'episode_id': slot['anonymous_episode_id'], 'session_id': 'current-scene',
              'output': str(runtime / 'owner'), 'endpoint': str(runtime / 'ENDPOINT.json'),
              'asset': plan['inputs']['scene'], 'asset_sha256': ASSET_SHA,
              'blender': 'D:/Tools/blender5.2/blender.exe', 'worker_deadline_ns': deadline,
              'dependency_python': ready['dependency_python'],
              'read_schemas': [] if internal == 'N' else plan['read_schemas'],
              'entry': None if internal == 'N' else ready['entry'],
              'install_root': None if internal == 'N' else ready['install_root'],
              'source_sha256': None if internal == 'N' else ready['source_sha256']}
    save(runtime / 'ACTOR_CONFIG.json', config)
    command = [ready['dependency_python'], '-I', '-B', '-X', 'utf8', str(ACTOR),
               '--config', str(runtime / 'ACTOR_CONFIG.json')]
    check_deadline(startup_deadline)
    return config, command, startup_deadline, guard


def wait_ready(runtime, process, started, deadline, command, startup_deadline):
    save(runtime / 'ACTOR_LAUNCH.json', {'pid': process.pid, 'argv': command, 'started_ns': started,
         'worker_deadline_ns': deadline, 'actor_startup_deadline_ns': startup_deadline})
    endpoint = runtime / 'ENDPOINT.json'
    while not endpoint.exists():
        if process.poll() is not None:
            raise RuntimeError('actor_start_failed')
        check_deadline(startup_deadline)
        time.sleep(.02)
    check_deadline(startup_deadline)
    value = read(endpoint)
    assert value['chain_deadline_ns'] == deadline, 'owner_original_absolute_deadline'
    return value


def postclose(row, runtime, plan, guard, deadline, old, post):
    """Validate closed source and registered states, without solving the task."""
    check_deadline(deadline)
    receipt = row['owner_finish']
    assert receipt['confirmed'] is True, 'postreadback_requires_confirmed_finish'
    close = receipt['close']
    assert close['asset_unchanged'] and close['accepted_worker_geometry_matches'], 'closed_source_guard'
    assert close['expected_terminal_geometry_matches'] and close['zero_new_images_budget_met'], 'closed_state_guard'
    assert source_guard(plan) == guard, 'execution_source_changed'
    save(runtime / 'SOURCE_GUARD_AFTER.json', guard)
    old.snapshot_binding(read(runtime / 'owner/INITIAL.json'), read(QUAL / 'BASE_SNAPSHOT.json'))
    edited = close.get('registered_pose_applied') is True
    if edited:
        old.snapshot_binding(read(runtime / 'owner/PRE_EDIT.json'), read(QUAL / 'BASE_SNAPSHOT.json'))
        old.snapshot_binding(read(runtime / 'owner/EDIT.json'), read(QUAL / 'EDIT_SNAPSHOT.json'))
    expected = QUAL / ('EDIT_SNAPSHOT.json' if edited else 'BASE_SNAPSHOT.json')
    old.snapshot_binding(read(runtime / 'owner/FINAL.json'), read(expected))
    row['terminal_wire_verification'] = post.verify_terminal_wire(runtime)
    row['postclose_verification'] = {'passed': True, 'registered_pose_applied': edited,
                                    'source_unchanged': True, 'asset_unchanged': sha(plan['inputs']['scene']) == ASSET_SHA,
                                    'scope': 'Closed source, registered geometry, zero recorded images and terminal WIRE; task quality unscored'}
    assert row['postclose_verification']['asset_unchanged'], 'asset_readback_changed'
    check_deadline(deadline)


def publish(row, folder, deadline):
    """Measure through result write/close; timing receipt publication is separate."""
    row['execution_rows'] = execution_rows(row.get('coordinator', {}))
    row['execution_counts'] = counts(row['execution_rows'])
    row['continuity'] = continuity(row.get('coordinator', {}))
    row['stop_reasons'] = stop_reasons(row)
    row['valid_before_result_publication'] = bool(not row['errors'] and
        row.get('postclose_verification', {}).get('passed') is True and
        row['execution_counts']['completed'] == 3 and row['continuity']['three_turn_thread_continuity'] and
        row.get('coordinator', {}).get('qualified_execution') is True and time.perf_counter_ns() < deadline)
    publication_errors = []
    try:
        save(folder / 'OUTER_RESULT.json', row)
    except BaseException as error:
        publication_errors.append(failure(error, 'OUTER_RESULT_publication'))
    closed = time.perf_counter_ns()
    timing = {'started_ns': row['started_ns'], 'business_receipts_closed_ns': closed,
              'full_episode_wall_ns': closed - row['started_ns'], 'episode_deadline_ns': deadline,
              'within_590s': closed < deadline,
              'outer_valid_completion': row['valid_before_result_publication'] and not publication_errors and closed < deadline,
              'publication_errors': publication_errors,
              'scope': 'Input checks, owner startup, three turns, registered edit, sole finish, postclose readback, outer ZIP and OUTER_RESULT write/close',
              'durability': 'Buffered writes and close; fsync unmeasured'}
    began = time.perf_counter_ns()
    try:
        save(folder / 'FINAL_TIMING.json', timing)
        ended = time.perf_counter_ns()
        save(folder / 'TIMING_PUBLICATION.json', {'started_ns': began, 'closed_ns': ended,
            'scope': 'FINAL_TIMING publication; this receipt publication is separate'})
    except BaseException as error:
        publication_errors.append(failure(error, 'timing_receipt_publication'))
        timing['outer_valid_completion'] = False
    row['timing'] = timing
    row['outer_valid_completion'] = timing['outer_valid_completion']
    return row


def run_one(slot, plan):
    # This clock precedes input checks, runtime directory creation and owner startup.
    started = time.perf_counter_ns()
    deadline = started + EPISODE_NS
    runtime = Path(plan['runtime_root']) / slot['cell']
    folder = BATCH / 'episodes' / slot['cell']
    row = {**slot, 'folder': str(folder), 'runtime_folder': str(runtime),
           'consumer_output': str(runtime / 'c'), 'owner_output': str(runtime / 'owner'),
           'started_ns': started, 'episode_deadline_ns': deadline, 'errors': [],
           'owner_started': False, 'owner_finish_calls': 0, 'usage_aggregation': None,
           'usage_semantics': 'unconfirmed_turn_or_session_scope', 'quality': 'unscored'}
    process = None
    finish_result = None
    old = load('_continuous_original_driver', OLD_DRIVER)
    coordinator = load('_continuous_fixed_coordinator', COORDINATOR)
    attach = load('_continuous_fixed_attach', ATTACH)
    post = load('_continuous_terminal_readback', POSTCLOSE)

    def finish_once():
        nonlocal finish_result
        if finish_result is None:
            row['owner_finish_calls'] += 1
            # Never signal an owner twice, even when finish itself raises.
            finish_result = {'confirmed': False, 'error': 'finish_started_without_receipt'}
            finish_result = old.finish(runtime, process)
        row['owner_finish'] = finish_result
        return finish_result

    admin_count = 0

    def control(operation, **arguments):
        nonlocal admin_count
        check_deadline(deadline)
        admin_count += 1
        request = {'jsonrpc': '2.0', 'id': 'admin-' + str(admin_count),
                   'method': 'continuity/' + operation,
                   'params': {'episode_id': slot['anonymous_episode_id'], **arguments}}
        record = {'started_ns': time.perf_counter_ns(), 'request': request}
        try:
            response = attach.attach(read(runtime / 'ENDPOINT.json'), 'native', request)
            record['response'] = response
            if 'error' in response:
                raise RuntimeError('owner_control_rejected:' + json.dumps(response['error'], ensure_ascii=False))
            return response['result']
        except BaseException as error:
            record['error'] = failure(error, 'owner_control')
            raise
        finally:
            record['ended_ns'] = time.perf_counter_ns()
            save(runtime / ('ADMIN_' + str(admin_count).zfill(2) + '.json'), record)

    try:
        folder.mkdir(parents=True, exist_ok=False)
        runtime.mkdir(parents=True, exist_ok=False)
        assert len(str(runtime / 'c/turns/REPEAT/attachments' / ('bridge_' + 'f' * 32) / '004/RX.bin')) < 260, 'Windows_runtime_path_budget'
        config, command, startup_deadline, guard = prepare_config(slot, plan, runtime, started, deadline)
        with (runtime / 'actor_stdout.bin').open('wb') as out, (runtime / 'actor_stderr.bin').open('wb') as err:
            check_deadline(startup_deadline)
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            row['owner_started'] = True
        wait_ready(runtime, process, started, deadline, command, startup_deadline)
        cell = {'group': config['group'], 'external_group': slot['group'],
                'endpoint': str(runtime / 'ENDPOINT.json'), 'audit_dir': str(runtime / 'owner')}
        save(runtime / 'cell.json', cell)
        prompts = [BATCH / plan['inputs'][key] for key in ('prompt_base', 'prompt_recheck', 'prompt_recheck')]
        row['coordinator'] = coordinator.run_episode(episode_id=slot['anonymous_episode_id'],
            output=runtime / 'c', work=runtime / 'w', cell=cell,
            install={'python': plan['installation_ready']['dependency_python']}, plan=plan,
            prompts=[path.read_bytes() for path in prompts], episode_deadline_ns=deadline,
            turn_budget_ns=TURN_NS, control=control, finish=finish_once,
            anonymous_episode_id=slot['anonymous_episode_id'], local_cli=None)
    except BaseException as error:
        row['errors'].append(failure(error, 'episode_execution'))
        if 'coordinator' not in row:
            try:
                row['coordinator'] = recorded_coordinator(runtime)
            except BaseException as recovery_error:
                row['errors'].append(failure(recovery_error, 'read_only_episode_recovery'))
    finally:
        if process is not None:
            try:
                row['owner_finish'] = finish_once()
            except BaseException as error:
                row['owner_finish'] = finish_result
                row['errors'].append(failure(error, 'sole_owner_finish'))
        if row.get('owner_finish', {}).get('confirmed') is True:
            try:
                postclose(row, runtime, plan, guard, deadline, old, post)
            except BaseException as error:
                row['errors'].append(failure(error, 'postclose_readback'))
        try:
            archive = folder / 'ORIGINALS.zip'
            sources = coordinator.pack.capture_cell(runtime, archive)
            manifest = {'runtime_folder': str(runtime), 'archive': str(archive), 'archive_sha256': sha(archive),
                        'members': {name: {'bytes': len(raw), 'sha256': digest(raw)} for name, raw in sources.items()},
                        'scope': 'All closed short-runtime originals, retained at their original paths'}
            save(folder / 'RUNTIME_MANIFEST.json', manifest)
            row['runtime_archive'] = str(archive)
            row['runtime_manifest'] = str(folder / 'RUNTIME_MANIFEST.json')
            row['runtime_archive_sha256'] = manifest['archive_sha256']
            check_deadline(deadline)
        except BaseException as error:
            row['errors'].append(failure(error, 'outer_originals_archive'))
    return publish(row, folder, deadline)


def run_batch(plan):
    contract(plan)
    result = {'cycle': CYCLE, 'started_ns': time.perf_counter_ns(), 'records': [],
              'planned_episodes': 6, 'planned_turns': 18, 'quality': 'unscored',
              'usage_aggregation': None, 'stop_reasons': [], 'not_run_episodes': [],
              'publication_errors': []}
    for index, slot in enumerate(plan['sequence']):
        try:
            row = run_one(slot, plan)
        except BaseException as error:
            # No retry is authorized. Recover existing records without starting
            # a process or guessing that an unrecorded cleanup completed.
            runtime = Path(plan['runtime_root']) / slot['cell']
            coordinator = {'turns': []}
            recovery_errors = []
            try:
                coordinator = recorded_coordinator(runtime)
            except BaseException as recovery_error:
                recovery_errors.append(failure(recovery_error, 'read_only_episode_recovery'))
            row = {**slot, 'folder': str(BATCH / 'episodes' / slot['cell']),
                   'runtime_folder': str(runtime), 'consumer_output': str(runtime / 'c'),
                   'owner_output': str(runtime / 'owner'), 'coordinator': coordinator,
                   'errors': [failure(error, 'unhandled_episode_boundary'), *recovery_errors],
                   'outer_valid_completion': False, 'usage_aggregation': None,
                   'continuity': continuity(coordinator), 'execution_rows': execution_rows(coordinator),
                   'stop_reasons': [{'reason': 'unhandled_episode_boundary_cleanup_unconfirmed'}]}
            row['execution_counts'] = counts(row['execution_rows'])
        result['records'].append(row)
        try:
            save(BATCH / 'RUN_RESULT.json', result)
        except BaseException as error:
            result['publication_errors'].append(failure(error, 'batch_progress_publication'))
            row['stop_reasons'].append({'reason': 'batch_progress_publication_failed'})
        if row['stop_reasons']:
            result['stop_reasons'] = [{'cell': slot['cell'], **reason} for reason in row['stop_reasons']]
            result['not_run_episodes'] = [{**remaining, 'reason': 'batch_stopped', 'execution_state': 'not_run'}
                                          for remaining in plan['sequence'][index + 1:]]
            break
    base_threads = [row['continuity']['thread_ids'][0] for row in result['records'] if row['continuity']['thread_ids']]
    result['cross_episode_threads_distinct'] = len(base_threads) == len(set(base_threads))
    result['thread_continuity_confirmed'] = (len(result['records']) == 6 and result['cross_episode_threads_distinct']
        and all(row['continuity']['three_turn_thread_continuity'] for row in result['records']))
    result['execution_counts'] = {'planned': 18,
        'completed': sum(row['execution_counts']['completed'] for row in result['records']),
        'failed': sum(row['execution_counts']['failed'] for row in result['records']),
        'not_run': sum(row['execution_counts']['not_run'] for row in result['records']) + 3 * len(result['not_run_episodes'])}
    result['ended_ns'] = time.perf_counter_ns()
    try:
        save(BATCH / 'RUN_RESULT.json', result)
    except BaseException as error:
        result['publication_errors'].append(failure(error, 'final_batch_publication'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true')
    options = parser.parse_args()
    plan = read(BATCH / 'PLAN.json')
    checked = contract(plan)
    if not options.run_models:
        print(json.dumps(checked))
        return 0
    preparation = validate_preparation(read(BATCH / 'PREPARATION.json'))
    for slot in plan['sequence']:
        assert not (Path(plan['runtime_root']) / slot['cell']).exists(), 'formal_runtime_already_exists'
        assert not (BATCH / 'episodes' / slot['cell']).exists(), 'formal_outer_output_already_exists'
    # The six formal slots are reserved before starting Blender or any model.
    with (BATCH / 'FORMAL_STARTED.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'cycle': CYCLE,
                   'sequence': list(CELLS), 'maximum_episodes': 6, 'maximum_turns': 18,
                   'preparation': preparation, 'plan_sha256': sha(BATCH / 'PLAN.json')}, stream, indent=2)
        stream.write('\n')
    result = run_batch(plan)
    # Group timing, tokens, usage and adoption remain private until quality seal.
    print(json.dumps({'planned_episodes': 6, 'started_episodes': len(result['records']),
                      'execution_counts': result['execution_counts'],
                      'thread_continuity_confirmed': result['thread_continuity_confirmed']}))
    return 0 if not result['stop_reasons'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
