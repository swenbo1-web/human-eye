"""Offline synthetic archive checks for the nine-slot text-only quality packer."""

from contextlib import ExitStack, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import traceback
import types
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
PACK_PATH = BATCH / 'runtime/pack_quality.py'
CYCLE = 'M4-SURFACE-SCAN-COMPACT-CONSUMPTION-001'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def put(folder, name, raw):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def sequence():
    groups = ('N','O','C','O','C','N','C','N','O')
    return [{'cell': group + str(i // 3 + 1), 'task': 'T1', 'round': i // 3 + 1, 'group': group}
            for i, group in enumerate(groups)]


def fixture(folder, *, consumer_failure=False, all_nine=False, zero_entered=False):
    slots = sequence()
    mapping = {'synthetic': True, 'rows': [dict(slot, anonymous_id='answer_' + sha(('synthetic|' + slot['cell']).encode())[:16])
                                          for slot in slots]}
    map_raw = encoded(mapping)
    prompt = b'SYNTHETIC common task text only. No consumer or real answer.\n'
    scoring = {
        'SCORING_CONTRACT.json': encoded({'synthetic': True, 'same_standard': True}),
        'ACTUAL_SNAPSHOT.json': encoded({'synthetic': True, 'objects': []}),
        'TRUTH.json': encoded({'synthetic': True, 'no_real_answers': True}),
    }
    materials = [{'path': 'scoring/' + name, 'public_name': name, 'sha256': sha(raw)}
                 for name, raw in scoring.items()]
    plan = {'cycle_id': CYCLE, 'batch': CYCLE, 'logical_denominator': 9, 'per_arm': 3,
            'arms': {'N': {}, 'O': {}, 'C': {}}, 'image_count': 0, 'new_images': 0,
            'sequence': slots, 'private_anonymous_map_sha256': sha(map_raw),
            'tasks': {'T1': {}}, 'inputs': {'prompt': 'input/PROMPT.txt', 'prompt_sha256': sha(prompt)},
            'quality_materials': materials}
    plan_raw = encoded(plan)
    final = 'SYNTHETIC final 原始字节。\nUnknown remains explicit.\n'
    business_text = '{ "group": "semantic-group", "status":"unknown", "timing_ms":17, "support_evidence":{"primitive_direction":[1,0,0]}, "reason":"surface_work_budget", "path":"C:/semantic/file" }'
    tool_result = {'isError': False, 'content': [{'type': 'text', 'text': business_text}],
                   'future_business_extension': {'group': 'semantic-group', 'elapsed_ns': 123,
                                                 'unknown': {'reason': 'synthetic-budget', 'proof': [2, 3, 5]}}}
    request = {'jsonrpc': '2.0', 'id': 'administrative-id', '_meta': {'clock': 123}, 'method': 'tools/call',
               'params': {'name': 'human_eye_scene_observe', '_meta': {'elapsed': 77},
                          'arguments': {'query': {'mode': 'task', 'requested_facts': ['spatial_relation', 'surface_proximity']},
                                        'include_image': False, 'native_semantic_text': business_text}}}
    response = {'jsonrpc': '2.0', 'id': 'administrative-id', '_meta': {'usage': 999}, 'result': tool_result}
    error_value = {'code': -32602, 'message': 'SYNTHETIC invalid fact request',
                   'data': {'status': 'unknown', 'reason': 'not_executed',
                            'group': 'semantic-group', 'support_evidence': {'integers': [7, 11]}}}
    error_response = {'jsonrpc': '2.0', 'id': 'administrative-id', 'error': error_value}
    native_code = 'print("SYNTHETIC", {"group": "business", "elapsed_ns": 17})\n'
    native_request = {'jsonrpc': '2.0', 'id': 'native-id', 'method': 'tools/call',
                      'params': {'name': 'execute_blender_code', 'arguments': {'code': native_code}}}
    native_result = {'isError': False, 'content': [{'type': 'text', 'text': business_text + '\nSYNTHETIC native stdout\n'}]}
    native_response = {'jsonrpc': '2.0', 'id': 'native-id', 'result': native_result}
    records = []
    selected = [] if zero_entered else slots if all_nine else slots[:1]
    for i, slot in enumerate(selected):
        consumer = None
        if consumer_failure or all_nine:
            consumer = {**slot, 'group': 'N' if slot['group']=='N' else 'P', 'external_group': slot['group'], 'consumer_pid': 1000 + i if all_nine else None,
                        'status': 'completed' if all_nine else 'failed', 'valid_completion': all_nine,
                        'thread_id': 'synthetic-thread' if all_nine else None, 'final': final if all_nine else None,
                        'errors': [] if all_nine else [{'type': 'SyntheticPopenError', 'message': 'synthetic launch failure'}],
                        'usage': {'admin_usage_stays_private': 123}, 'started_ns': 31,
                        'initial_image': {'path': None, 'sha256': None, 'bytes': 0, 'count': 0},
                        'input_image_count': 0, 'input_image_bytes': 0, 'initial_image_unchanged': True,
                        'image_delivery': {'prepared_file_verified': None, 'initial_attachment_in_argv': False,
                                           'CLI_process_launched': all_nine, 'CLI_thread_started': all_nine,
                                           'status': 'text_only_no_attachment',
                                           'provider_delivery_confirmed': None, 'model_view_confirmed': None}}
            put(folder, 'cells/' + slot['cell'] + '/CONSUMER.json', encoded(consumer))
            if all_nine:
                put(folder, 'cells/' + slot['cell'] + '/PUBLIC_FINAL.txt', final.encode())
                events = {'at_ns': 765, 'event': {'type': 'item.completed', 'item': {
                    'type': 'mcp_tool_call', 'server': 'human_eye', 'tool': 'human_eye_scene_observe',
                    'arguments': request['params']['arguments'], 'result': tool_result, 'status': 'completed'}}}
                for number in (1, 2):
                    base = 'cells/' + slot['cell'] + '/owner/tool_' + str(number).zfill(2) + '/'
                    put(folder, base + 'REQUEST.json', encoded(request))
                    put(folder, base + 'RESPONSE.json', encoded(response))
                    put(folder, base + 'ATTEMPT.json', encoded({'is_error': False, 'elapsed_ns': 123456}))
                base = 'cells/' + slot['cell'] + '/owner/tool_03/'
                put(folder, base + 'REQUEST.json', encoded(request))
                put(folder, base + 'ERROR_RESPONSE.json', encoded(error_response))
                put(folder, base + 'ATTEMPT.json', encoded({'is_error': True, 'elapsed_ns': 345678,
                    'exception': {'type': 'ValueError', 'message': 'SYNTHETIC not_executed',
                                  'traceback': 'synthetic administrative traceback'}}))
                base = 'cells/' + slot['cell'] + '/owner/tool_04/'
                put(folder, base + 'REQUEST.json', encoded(native_request))
                put(folder, base + 'RESPONSE.json', encoded(native_response))
                put(folder, base + 'ATTEMPT.json', encoded({'is_error': False, 'elapsed_ns': 456789}))
                event_values = [events]
                for tool, arguments, result, error in (
                        ('human_eye_scene_observe', request['params']['arguments'], None, error_value),
                        ('execute_blender_code', native_request['params']['arguments'], native_result, None)):
                    event_values.append({'at_ns': 987, 'event': {'type': 'item.completed', 'item': {
                        'type': 'mcp_tool_call', 'server': 'human_eye', 'tool': tool,
                        'arguments': arguments, 'result': result, 'error': error, 'status': 'completed'}}})
                put(folder, 'cells/' + slot['cell'] + '/events.jsonl',
                    b''.join(encoded(value).replace(b'\n', b'') + b'\n' for value in event_values))
        records.append({**slot, 'consumer': consumer, 'finish': None,
                        'errors': [] if consumer is not None else [{'type': 'SyntheticActorError', 'message': 'synthetic startup failure'}],
                        'cell_started_ns': 30 + i, 'cell_ended_ns': 40 + i,
                        'full_cell_wall_ns': 10, 'within_570s': True})
    run = {'synthetic': True, 'records': records, 'started_cells': len(records), 'maximum_consumers': 9,
           'all_planned_dispatched': all_nine, 'no_replacements': True,
           'stop': None if all_nine else 'synthetic terminal stop',
           'batch_started_ns': 10, 'batch_ended_ns': 70, 'batch_wall_ns': 60}
    controls = {'PLAN.json': plan_raw, 'FREEZE.json': encoded({'plan_sha256': sha(plan_raw)}),
                'private/ANON_MAP.json': map_raw, 'RUN_RESULT.json': encoded(run),
                'GO.json': encoded({'task': CYCLE, 'authorized': True, 'max_consumers': 9, 'plan_sha256': sha(plan_raw)}),
                'STARTED.json': encoded({'started_ns': 20, 'max_consumers': 9, 'plan_sha256': sha(plan_raw)}),
                'input/PROMPT.txt': prompt}
    for name, raw in controls.items():
        put(folder, name, raw)
    for name, raw in scoring.items():
        put(folder, 'scoring/' + name, raw)
    return {'slots': slots, 'mapping': mapping, 'run': run, 'controls': controls, 'prompt': prompt,
            'scoring': scoring, 'final': final, 'business_text': business_text,
            'request': request, 'tool_result': tool_result, 'error_value': error_value,
            'native_request': native_request, 'native_result': native_result}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'synthetic_01'
    assert Path(name).name == name and name not in ('.','..')
    output = HERE / name
    output.mkdir(exist_ok=False)
    pack_bytes = PACK_PATH.read_bytes()
    pack = types.ModuleType('_m4_grooved_packager_synthetic')
    pack.__file__ = str(PACK_PATH)
    exec(compile(pack_bytes, str(PACK_PATH), 'exec', dont_inherit=True), pack.__dict__)
    checks, attempts, cases = [], [], []
    error = None

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})

    def forbidden(*args, **kwargs):
        attempts.append('external operation')
        raise AssertionError('external operation forbidden in synthetic packager checks')

    try:
        with ExitStack() as stack:
            for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
                stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
            stack.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
            for name, consumer_failure, all_nine, zero_entered in (
                    ('actor_failed', False, False, False),
                    ('consumer_launch_failed', True, False, False),
                    ('preloop_terminal_no_entered_cells', False, False, True),
                    ('nine_completed', False, True, False)):
                root = output / name
                data = fixture(root, consumer_failure=consumer_failure, all_nine=all_nine, zero_entered=zero_entered)
                pack.EVAL = root
                pack.HERE = root / 'runtime'
                pack.HERE.mkdir()
                previous = sys.argv
                capture = io.StringIO()
                try:
                    sys.argv = ['synthetic-pack-quality', 'handoff_01']
                    with redirect_stdout(capture):
                        pack.main()
                finally:
                    sys.argv = previous
                put(root, 'synthetic_stdout.txt', capture.getvalue().encode())
                public = pack.HERE / 'handoff_01/public'
                private = pack.HERE / 'handoff_01/private'
                index = json.loads((public / 'INDEX.json').read_bytes())
                by_id = {answer['anonymous_id']: answer for answer in index['answers']}
                ordered = [by_id[row['anonymous_id']] for row in data['mapping']['rows']]
                check(name + ':nine_slots', index['fixed_slots'] == len(index['answers']) == 9)
                check(name + ':no_score', index['scoring_performed'] is False)
                check(name + ':common_prompt', (public / 'tasks/T1.txt').read_bytes() == data['prompt'])
                check(name + ':no_images', not list(public.rglob('*.png')) and index['tasks'][0]['initial_image_count'] == 0)
                check(name + ':complete_scoring_materials', len(index['scoring_materials']) == 3 and
                      all((public / 'scoring' / key).read_bytes() == value for key, value in data['scoring'].items()))
                check(name + ':map_private', not (public / 'ANON_MAP.json').exists()
                      and (private / 'control/private/ANON_MAP.json').read_bytes() == data['controls']['private/ANON_MAP.json'])
                if not all_nine:
                    if zero_entered:
                        check(name + ':nine_not_run', all(row['execution_record_state'] == row['answer_state'] == 'not_run'
                                                        for row in ordered))
                    else:
                        expected = 'failed' if consumer_failure else 'failed_before_consumer'
                        check(name + ':entered_failure', ordered[0]['execution_record_state'] == expected
                              and ordered[0]['answer_state'] == 'missing')
                        check(name + ':eight_not_run', all(row['execution_record_state'] == row['answer_state'] == 'not_run'
                                                          for row in ordered[1:]))
                    wrong = dict(data['controls'])
                    wrong['GO.json'] = encoded({'task': 'M4-SPATIAL-FACT-CONSUMPTION-001',
                                                'authorized': True, 'max_consumers': 9,
                                                'plan_sha256': sha(data['controls']['PLAN.json'])})
                    try:
                        pack.validate_zero_launch_failure(data['run'], wrong)
                    except AssertionError:
                        check(name + ':historical_GO_rejected', True)
                    else:
                        check(name + ':historical_GO_rejected', False)
                else:
                    for row in ordered:
                        folder = public / row['directory']
                        check(name + ':' + row['anonymous_id'] + ':final_bytes',
                              row['answer_state'] == 'present' and (folder / 'answer.txt').read_bytes() == data['final'].encode())
                        tools = json.loads((folder / 'tool_evidence.json').read_bytes())
                        check(name + ':' + row['anonymous_id'] + ':duplicates_retained', len(tools['owner_attempts']) == 4
                              and tools['owner_attempts'][0]['request'] == tools['owner_attempts'][1]['request'])
                        check(name + ':' + row['anonymous_id'] + ':full_business_response',
                              all(item['responses'][0]['value'] == {'result': data['tool_result']} for item in tools['owner_attempts'][:2]))
                        expected_request = copy.deepcopy(data['request'])
                        for key in ('jsonrpc', 'id', '_meta'):
                            expected_request.pop(key)
                        expected_request['params'].pop('_meta')
                        check(name + ':' + row['anonymous_id'] + ':arguments_preserved',
                              all(item['request'] == expected_request for item in tools['owner_attempts'][:2]))
                        failed, native = tools['owner_attempts'][2:]
                        check(name + ':' + row['anonymous_id'] + ':failed_response_preserved',
                              failed['is_error'] is True and failed['responses'][0]['value'] == {'error': data['error_value']})
                        expected_native = copy.deepcopy(data['native_request'])
                        expected_native.pop('jsonrpc')
                        expected_native.pop('id')
                        check(name + ':' + row['anonymous_id'] + ':native_followup_preserved',
                              native['request'] == expected_native
                              and native['responses'][0]['value'] == {'result': data['native_result']})
                        check(name + ':' + row['anonymous_id'] + ':known_exception_envelope_only',
                              failed['owner_exception'] == {'type': 'ValueError', 'message': 'SYNTHETIC not_executed'})
                        public_events = tools['public_tool_events']
                        check(name + ':' + row['anonymous_id'] + ':public_events_preserved',
                              len(public_events) == 3
                              and public_events[0]['event']['result'] == data['tool_result']
                              and public_events[1]['event']['error'] == data['error_value']
                              and public_events[2]['event']['arguments'] == data['native_request']['params']['arguments']
                              and public_events[2]['event']['result'] == data['native_result'])
                        consistency = json.loads((folder / 'source_consistency.json').read_bytes())
                        check(name + ':' + row['anonymous_id'] + ':recorded_text_only_input',
                              consistency['CONSUMER_INPUT']['input_image_count'] == 0
                              and consistency['CONSUMER_INPUT']['input_image_bytes'] == 0)
                        archive = private / 'raw' / (row['anonymous_id'] + '.zip')
                        with zipfile.ZipFile(archive) as bundle:
                            consumer = json.loads(bundle.read('CONSUMER.json'))
                            check(name + ':' + row['anonymous_id'] + ':private_original_kept',
                                  consumer['usage'] == {'admin_usage_stays_private': 123})
                cases.append({'case': name, 'public_path': str(public), 'synthetic': True,
                              'logical_slots': 9, 'scoring_performed': False})
    except BaseException:
        error = traceback.format_exc()
    unchanged = PACK_PATH.read_bytes() == pack_bytes
    record = {'passed': error is None and not attempts and unchanged and all(row['passed'] for row in checks),
              'checks': checks, 'failed_checks': [row for row in checks if not row['passed']],
              'unexpected_error': error, 'external_operation_attempts': attempts,
              'packager_source_unchanged': unchanged, 'packager_sha256': sha(pack_bytes),
              'test_source_sha256': sha(Path(__file__).read_bytes()), 'synthetic_cases': cases,
              'model_consumers': 0, 'product_calls': 0, 'Blender_sessions': 0,
              'scope': 'synthetic archival and projection behavior only, no answers or consumers'}
    put(output, 'RESULTS.json', encoded(record))
    print(json.dumps({'passed': record['passed'], 'checks': len(checks), 'unexpected_error': error}))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
