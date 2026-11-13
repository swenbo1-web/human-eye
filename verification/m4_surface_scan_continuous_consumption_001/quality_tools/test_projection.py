"""Small offline source-projection counterexamples. No process or provider."""

import argparse
import contextlib
import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load('_continuous_quality_test_pack', HERE / 'pack_quality.py')
checker = load('_continuous_quality_test_checker', HERE / 'check_package.py')
THREAD = '01234567-89ab-4cde-8123-0123456789ab'
OTHER_THREAD = '11234567-89ab-4cde-8123-0123456789ab'
ERROR_TEXT = 'SYNTHETIC original provider error message preserved exactly.'
BUSINESS_TEXT = '{"group":"semantic-group","usage":314,"elapsed_ns":271,"path":"C:/business/path","argv":["semantic"]}'


def save(path, value):
    pack.put(path, pack.encoded(value))


def tiny_zip(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'x') as bundle:
        bundle.writestr('SYNTHETIC.txt', 'Offline synthetic bytes. No real answer.')


def fixture(base):
    batch = base / 'batch'
    qualification = base / 'qualification'
    materials = {}
    for name in pack.MATERIALS:
        raw = pack.encoded({'synthetic': True, 'fixture': name, 'objects': [], 'pairs': []})
        pack.put(qualification / name, raw)
        materials[name] = pack.sha(raw)
    prompt_materials = []
    for index, (name, _) in enumerate(pack.PROMPTS, 1):
        raw = ('SYNTHETIC common prompt ' + str(index) + '\n').encode()
        pack.put(batch / 'inputs' / name, raw)
        prompt_materials.append((name, pack.sha(raw)))
    rows = [{'cell': cell, 'group': cell[0], 'pair': int(cell[1]),
        'anonymous_episode_id': 'episode_' + format(16 - index, '016x'),
        'anonymous_turn_ids': ['answer_' + format(100 + index * 3 + turn, '016x') for turn in range(3)]}
        for index, cell in enumerate(pack.CELLS)]
    mapping = {'schema': 'continuous_anonymous_map_v1', 'rows': rows}
    mapping_path = batch / 'private/ANON_MAP.json'
    save(mapping_path, mapping)
    save(batch / 'PLAN.json', {'cycle': pack.CYCLE, 'sequence': rows,
        'anonymous_map_sha256': pack.sha(mapping_path.read_bytes())})
    records = []
    # One completed episode, a failed resume with a final, a partial launch,
    # and three completed turns whose complete outer time fails.
    for row, turns_count in zip(rows[:4], (3, 2, 1, 3)):
        runtime = base / 'runtime' / row['cell']
        owner = runtime / 'owner'
        consumer = runtime / 'c'
        outer_folder = batch / 'episodes' / row['cell']
        outer_folder.mkdir(parents=True)
        outer = {**row, 'runtime_folder': str(runtime), 'folder': str(outer_folder),
                 'owner_output': str(owner), 'consumer_output': str(consumer), 'errors': []}
        turns = []
        for index in range(1, turns_count + 1):
            label = pack.LABELS[index - 1]
            folder = consumer / 'turns' / label
            failed_resume = row['cell'] == 'C1' and index == 2
            partial = row['cell'] == 'C2'
            observed = OTHER_THREAD if failed_resume else THREAD
            error_event = {'type': 'error', 'thread_id': observed, 'timestamp': 'ADMIN_TIME_SECRET',
                'usage': {'ADMIN_USAGE_SECRET': 9000}, 'message': ERROR_TEXT,
                'error': {'code': 'synthetic', 'data': {'opaque': BUSINESS_TEXT, 'usage': 314}}}
            result = {'isError': False, 'content': [{'type': 'text', 'text': BUSINESS_TEXT}],
                      'business_extension': {'group': 'semantic-group', 'elapsed_ns': 271}}
            arguments = {'code': 'print(' + repr(BUSINESS_TEXT) + ')\n'}
            request = {'jsonrpc': '2.0', 'id': 'ADMIN_RPC_SECRET', '_meta': {'ADMIN_USAGE_SECRET': 10},
                'method': 'tools/call', 'params': {'name': 'execute_blender_code',
                    '_meta': {'ADMIN_TIME_SECRET': 20}, 'arguments': arguments}}
            response = {'jsonrpc': '2.0', 'id': 'ADMIN_RPC_SECRET', '_meta': {'ADMIN_USAGE_SECRET': 10}, 'result': result}
            attempt = owner / ('tool_' + str(index).zfill(2))
            save(attempt / 'REQUEST.json', request)
            save(attempt / 'RESPONSE.json', response)
            save(attempt / 'ATTEMPT.json', {'is_error': False, 'exception': None})
            text = 'SYNTHETIC exact final ' + str(index) + '\n'
            events = [{'type': 'thread.started', 'thread_id': observed},
                {'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'arm_engine',
                    'tool': 'execute_blender_code', 'arguments': arguments, 'result': result, 'status': 'completed'}}]
            if failed_resume or partial:
                events.append(error_event)
            events.append({'type': 'item.completed', 'item': {'type': 'agent_message', 'id': 'ADMIN_MESSAGE_ID', 'text': text}})
            events.append({'type': 'turn.completed', 'usage': {'ADMIN_USAGE_SECRET': 8000}})
            pack.put(folder / 'events.jsonl', b''.join(pack.encoded({'perf_ns': 123456789, 'event': event}).replace(b'\n', b'') + b'\n'
                                                      for event in events))
            pack.put(folder / 'PUBLIC_FINAL.txt', text.encode())
            pack.put(folder / 'final.txt', ('unconfirmed CLI output\n' + text).encode())
            tiny_zip(folder / 'RAW_ARCHIVE.zip')
            expected = None if index == 1 else THREAD
            errors = [{'perf_ns': 123456789, 'event': error_event}] if failed_resume else []
            summary_errors = ([error_event, {'type': 'resume_thread_mismatch', 'expected': THREAD, 'observed': OTHER_THREAD}]
                              if failed_resume else [])
            record = {'episode_id': row['cell'], 'turn_index': index, 'turn_label': label,
                'expected_thread_id': expected, 'thread_id': observed,
                'frozen_cli_argv': ['codex', 'exec'] + ([] if expected is None else ['resume', expected]),
                'argv': ['ADMIN_ARGV_SECRET'], 'usage': {'ADMIN_USAGE_SECRET': 9000},
                'started_ns': 123456789, 'valid_completion': not failed_resume,
                'status': 'failed' if failed_resume else 'completed', 'final': text, 'errors': errors,
                'unexpected_tool_deviations': [], 'process_reaped': True, 'readers_stopped': True,
                'safe_to_continue': True, 'mutation_unknown': False,
                'summary': {'execution_state': 'failed' if failed_resume else 'completed', 'errors': summary_errors}}
            turn = {'turn_index': index, 'turn_label': label, 'folder': str(folder), 'expected_thread_id': expected,
                'status_before': {'business_attempts': index - 1}, 'status_after': {'business_attempts': index}}
            if not partial:
                save(folder / 'CONSUMER.json', record)
                save(folder / 'FINAL_TIMING.json', {'accepted_success': not failed_resume,
                    'original_turn_deadline_ns': 123456999})
                turn['consumer'] = record
            turns.append(turn)
        coordinator = {'turns': turns, 'errors': ([{'type': 'SyntheticLaunchError', 'message': 'SYNTHETIC entered launch failed',
            'traceback': 'ADMIN_PATH_SECRET'}] if row['cell'] == 'C2' else []),
            'qualified_execution': row['cell'] in ('N1', 'N2'), 'within_episode_deadline': True,
            'owner_finish': {'confirmed': True}}
        save(consumer / 'EPISODE_RESULT.json', coordinator)
        tiny_zip(consumer / 'quality/CONSUMER_ORIGINALS.zip')
        tiny_zip(consumer / 'quality/OWNER_ORIGINALS.zip')
        save(consumer / 'quality/PRIVATE_BINDING.json', {'synthetic': True, 'source': 'ADMIN_PATH_SECRET'})
        outer['coordinator'] = coordinator
        timing = {'outer_valid_completion': row['cell'] == 'N1', 'full_episode_wall_ns': 123456789}
        outer['timing'] = timing
        outer['outer_valid_completion'] = timing['outer_valid_completion']
        save(outer_folder / 'OUTER_RESULT.json', {'synthetic': True, 'valid_before_result_publication': True})
        save(outer_folder / 'FINAL_TIMING.json', timing)
        originals = pack.pack.capture_cell(runtime, outer_folder / 'ORIGINALS.zip')
        save(outer_folder / 'RUNTIME_MANIFEST.json', {'runtime_folder': str(runtime),
            'archive': str(outer_folder / 'ORIGINALS.zip'),
            'archive_sha256': pack.sha((outer_folder / 'ORIGINALS.zip').read_bytes()),
            'members': {name: {'bytes': len(raw), 'sha256': pack.sha(raw)} for name, raw in originals.items()}})
        records.append(outer)
    run_result = batch / 'RUN_RESULT.json'
    save(run_result, {'records': records})
    return batch, mapping_path, run_result, materials, tuple(prompt_materials), rows


def run_tests():
    assertions = []

    def verify(condition, name):
        if not condition:
            raise AssertionError(name)
        assertions.append(name)

    with tempfile.TemporaryDirectory(prefix='_offline_projection_', dir=HERE) as temporary:
        base = Path(temporary).resolve()
        assert base.is_relative_to(HERE.resolve())
        batch, mapping, run_result, materials, prompts, rows = fixture(base)
        with contextlib.ExitStack() as stack:
            for module in (pack, checker.pack):
                stack.enter_context(patch.object(module, 'QUALIFICATION', base / 'qualification'))
                stack.enter_context(patch.object(module, 'MATERIALS', materials))
                stack.enter_context(patch.object(module, 'PROMPTS', prompts))
            output = base / 'quality'
            pack.pack_batch(batch=batch, run_result=run_result, mapping_path=mapping, output=output)
            result = checker.check_package(output)
            verify(result['passed'], 'all_original_and_public_bindings_pass')
            verify(result['counts'] == {'completed': 7, 'failed': 2, 'not_run': 9}, 'eighteen_slots_include_failures_and_not_run')
            verify(result['episode_counts'] == {'completed': 1, 'execution_failure': 3, 'not_run': 2}, 'six_episode_execution_counts')
            public = output / 'public'
            index = pack.read_json(public / 'INDEX.json')
            verify(index['anonymous_episode_order'] == sorted(row['anonymous_episode_id'] for row in rows), 'anonymous_order_sorted')
            verify(index['anonymous_episode_order'] != [row['anonymous_episode_id'] for row in rows], 'dispatch_order_hidden')
            failed_dir = public / rows[1]['anonymous_episode_id'] / 'turn_2'
            failed = pack.read_json(failed_dir / 'TURN.json')
            verify(failed['execution_state'] == 'failed' and failed['final_present'], 'correct_looking_final_does_not_erase_error')
            verify(failed['errors'][0]['event']['message'] == ERROR_TEXT, 'original_error_message_exact')
            verify(failed['summary_errors'][1]['expected'] == 'context_1'
                   and failed['summary_errors'][1]['observed'] == 'context_2', 'resume_mismatch_stably_anonymized')
            partial_dir = public / rows[2]['anonymous_episode_id'] / 'turn_1'
            partial = pack.read_json(partial_dir / 'TURN.json')
            verify(partial['execution_state'] == 'failed' and partial['final_present'], 'entered_without_consumer_retains_partial_final')
            verify(partial['public_error_events'][0]['message'] == ERROR_TEXT, 'partial_turn_error_event_retained')
            outer_failed = pack.read_json(public / rows[3]['anonymous_episode_id'] / 'EPISODE.json')
            verify(outer_failed['execution_state'] == 'execution_failure'
                   and all(turn['execution_state'] == 'completed' for turn in outer_failed['turns']), 'outer_failure_separate_from_three_valid_turns')
            first_dir = public / rows[0]['anonymous_episode_id'] / 'turn_1'
            evidence = pack.read_json(first_dir / 'tool_evidence.json')
            verify(evidence['owner_attempts'][0]['responses'][0]['value']['result']['content'][0]['text'] == BUSINESS_TEXT,
                   'opaque_business_json_string_exact')
            verify(evidence['public_tool_events'][0]['event']['result']['business_extension'] == {'group': 'semantic-group', 'elapsed_ns': 271},
                   'business_admin_named_fields_preserved')
            combined = b'\n'.join(path.read_bytes() for path in public.rglob('*') if path.is_file())
            for secret in (THREAD, OTHER_THREAD, 'ADMIN_USAGE_SECRET', 'ADMIN_TIME_SECRET', 'ADMIN_RPC_SECRET',
                           'ADMIN_ARGV_SECRET', 'ADMIN_PATH_SECRET', 'ADMIN_MESSAGE_ID'):
                verify(secret.encode() not in combined, 'known_admin_hidden:' + secret)
            verify(evidence['owner_attempts'][0]['request']['params']['arguments']['code'] == 'print(' + repr(BUSINESS_TEXT) + ')\n',
                   'semantic_admin_lookalikes_remain_public')
            original_answer = (first_dir / 'answer.txt').read_bytes()
            (first_dir / 'answer.txt').write_bytes(original_answer + b'tampered')
            tampered = checker.check_package(output)
            verify(not tampered['passed'] and any('answer' in name or 'inventory' in name for name in tampered['failures']),
                   'answer_tampering_rejected')
            (first_dir / 'answer.txt').write_bytes(original_answer)
            # A pre-loop terminal result still preserves all frozen slots.
            empty_run = batch / 'EMPTY_RUN_RESULT.json'
            save(empty_run, {'records': [], 'errors': [{'type': 'SyntheticPreloopError', 'message': 'offline synthetic terminal'}]})
            empty_output = base / 'empty_quality'
            pack.pack_batch(batch=batch, run_result=empty_run, mapping_path=mapping, output=empty_output)
            empty_check = checker.check_package(empty_output)
            verify(empty_check['passed'] and empty_check['counts'] == {'completed': 0, 'failed': 0, 'not_run': 18},
                   'preloop_terminal_preserves_all_eighteen_not_run_slots')
            verify(pack.read_json(empty_output / 'public/INDEX.json')['batch_errors'][0]['message'] == 'offline synthetic terminal',
                   'preloop_terminal_error_retained')
            # Read-only driver recovery can have live source files but no outer
            # archive, final timer or recorded owner-attempt boundary.
            recovery = pack.read_json(run_result)
            recovery_row = recovery['records'][2]
            recovery_turn = recovery_row['coordinator']['turns'][0]
            recovery_turn.pop('status_before')
            recovery_turn.pop('status_after')
            for name in ('ORIGINALS.zip', 'RUNTIME_MANIFEST.json', 'FINAL_TIMING.json'):
                path = Path(recovery_row['folder']) / name
                assert path.resolve().is_relative_to(base)
                path.rename(path.with_name(name + '.retained'))
            (Path(recovery_row['consumer_output']) / 'EPISODE_RESULT.json').write_bytes(pack.encoded(recovery_row['coordinator']))
            recovery_run = batch / 'RECOVERY_RUN_RESULT.json'
            save(recovery_run, recovery)
            recovery_output = base / 'recovery_quality'
            pack.pack_batch(batch=batch, run_result=recovery_run, mapping_path=mapping, output=recovery_output)
            recovery_check = checker.check_package(recovery_output)
            verify(not recovery_check['passed'] and any('available' in label for label in recovery_check['failures']),
                   'missing_archive_and_timer_report_failure_without_crash')
            recovery_episode = pack.read_json(recovery_output / 'public' / rows[2]['anonymous_episode_id'] / 'EPISODE.json')
            verify(recovery_episode['execution_state'] == 'execution_failure'
                   and recovery_episode['turns'][0]['execution_state'] == 'failed'
                   and recovery_episode['turns'][0]['public_error_events'][0]['message'] == ERROR_TEXT,
                   'unsealed_recovery_retains_partial_final_errors_and_failure')
            recovery_evidence = pack.read_json(recovery_output / 'public' / rows[2]['anonymous_episode_id'] / 'turn_1/tool_evidence.json')
            verify(len(recovery_evidence['owner_attempts']) == 1
                   and recovery_evidence['owner_attempt_attribution'].startswith('unknown_start_boundary'),
                   'missing_owner_boundary_preserves_attempts_with_unknown_attribution')
    return {'schema': 'continuous_quality_offline_projection_tests_v1', 'passed': True,
            'assertions': assertions, 'assertion_count': len(assertions), 'model_calls': 0, 'Blender_calls': 0,
            'fixture_scope': 'Small synthetic bytes only. Complete product geometry and previous real consumer fixtures were not copied.',
            'quality': 'unscored', 'cost_unsealed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = run_tests()
    if args.receipt:
        pack.put(args.receipt, pack.encoded(result))
    print(pack.encoded(result).decode(), end='')
