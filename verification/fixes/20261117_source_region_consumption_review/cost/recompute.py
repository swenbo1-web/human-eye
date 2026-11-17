"""Independently audit fixed saved consumption evidence without decoding private bodies."""

from pathlib import Path
import ast
import base64
from datetime import datetime
import hashlib
import io
import json
import struct
import subprocess
import sys
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
AREA = REPO / 'verification/m4_source_region_consumption_001'
RUNTIME = Path('D:/he_m4_source_region_consume_001')
FINAL = '28cc6fc728c9fb62d46120f3be14b46d673f675a'
PRODUCT = '29f35a771c1d137455602adf28418f45e2788e6a'
SOURCE = 'af7c2cf6715e11f237e878fd6f66047d632b48e528f6b5abe28f6da66b5e232c'
CHECKS = []
PINS = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    pin = {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}
    if str(path) in PINS and PINS[str(path)] != pin:
        raise ValueError('input_changed/' + str(path))
    PINS[str(path)] = pin
    return data


def read(path):
    return json.loads(raw(path))


def check(name, value):
    CHECKS.append({'name': name, 'passed': bool(value)})


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def blobs(specs):
    specs = list(dict.fromkeys(specs))
    output = subprocess.run(['git', '-C', str(REPO), 'cat-file', '--batch'],
        input=('\n'.join(specs) + '\n').encode(), stdout=subprocess.PIPE, check=True).stdout
    position, result = 0, {}
    for spec in specs:
        end = output.index(b'\n', position)
        header = output[position:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('missing_blob/' + spec)
        size = int(header[2])
        position = end + 1
        result[spec] = output[position:position + size]
        position += size + 1
    check('git/complete_batch', position == len(output))
    return result


def pin_matches(pin, data):
    return sha(data) == pin['sha256'] and ('bytes' not in pin or len(data) == pin['bytes'])


def white(data, position):
    while position < len(data) and data[position] in b' \t\r\n':
        position += 1
    return position


def string_end(data, position):
    if data[position] != 34:
        raise ValueError('JSON_string_expected')
    position += 1
    while position < len(data):
        char = data[position]
        position += 1
        if char == 92:
            position += 1
        elif char == 34:
            return position
    raise ValueError('JSON_string_unterminated')


def value_end(data, position):
    position = white(data, position)
    if data[position] == 34:
        return string_end(data, position)
    if data[position] in (91, 123):
        close = 93 if data[position] == 91 else 125
        position += 1
        while True:
            position = white(data, position)
            if data[position] == close:
                return position + 1
            if data[position] in (44, 58):
                position += 1
            else:
                position = value_end(data, position)
    end = position
    while end < len(data) and data[end] not in b',]} \t\r\n':
        end += 1
    if end == position:
        raise ValueError('JSON_value_expected')
    return end


def members(data, position=0):
    """Locate object members as byte spans, skipping every value body lexically."""
    position = white(data, position)
    if data[position] != 123:
        return {}
    position += 1
    result = {}
    while True:
        position = white(data, position)
        if data[position] == 125:
            return result
        end = string_end(data, position)
        key = json.loads(data[position:end])
        position = white(data, end)
        if data[position] != 58:
            raise ValueError('JSON_colon_expected')
        start = white(data, position + 1)
        end = value_end(data, start)
        result[key] = (start, end)
        position = white(data, end)
        if data[position] == 44:
            position += 1
        elif data[position] != 125:
            raise ValueError('JSON_object_separator_expected')


def scalar(data, fields, key):
    if key not in fields:
        return None
    start, end = fields[key]
    return json.loads(data[start:end])


def event_metadata(line):
    fields = members(line)
    item_fields = members(line, fields['item'][0]) if 'item' in fields else {}
    return {'event_type': scalar(line, fields, 'type'),
            'item_type': scalar(line, item_fields, 'type'),
            'item_id': scalar(line, item_fields, 'id')}


def project_events(stream):
    """Hash private event lines without decoding their body fields."""
    output, changes, public = [], [], []
    for line in stream:
        metadata = event_metadata(line)
        if metadata['item_type'] in ('reasoning', 'analysis'):
            change = {'original_line_sha256': sha(line), 'original_line_bytes': len(line),
                      'item_id': metadata['item_id'], 'item_type': metadata['item_type']}
            replacement = {'type': metadata['event_type'],
                'item': {'id': metadata['item_id'], 'type': metadata['item_type'], 'redacted': True},
                'original_line_sha256': change['original_line_sha256'],
                'original_line_bytes': len(line)}
            output.append((json.dumps(replacement, sort_keys=True, separators=(',', ':')) + '\n').encode())
            changes.append(change)
        else:
            output.append(line)
            public.append(json.loads(line))
    return b''.join(output), changes, public


def zip_projection(original, shared, label):
    changes = []
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(io.BytesIO(shared)) as target:
        check(label + '/same_members', source.namelist() == target.namelist())
        for info in source.infolist():
            target_info = target.getinfo(info.filename)
            properties = ('filename', 'date_time', 'compress_type', 'external_attr', 'create_system', 'extra', 'comment', 'flag_bits')
            check(label + '/metadata/' + info.filename,
                  all(getattr(info, key) == getattr(target_info, key) for key in properties))
            if info.filename.endswith('stdout.raw.bin'):
                with source.open(info) as stream:
                    expected, rows, _ = project_events(stream)
                changes.extend(dict(member=info.filename, **row) for row in rows)
            else:
                expected = source.read(info)
            check(label + '/public_member/' + info.filename, expected == target.read(info.filename))
    return changes


def main():
    manifest = read(AREA / 'CONTENT_MANIFEST.json')
    archive = read(AREA / 'RUNTIME_ARCHIVE.json')
    baseline = read(AREA / 'BASELINE.json')
    binding = read(AREA / 'inputs/PRODUCT_BINDING.json')
    namespace = AREA.relative_to(REPO).as_posix()
    paths = {namespace + '/' + row['path'] for row in manifest['files']} | {namespace + '/CONTENT_MANIFEST.json'}
    changes = git('diff', '--name-status', baseline['baseline_git'], FINAL).decode().splitlines()
    changed = {line.split('\t', 1)[1] for line in changes}
    check('git/314_new_namespace_only', len(paths) == len(changed) == 314 and paths == changed
          and all(line.startswith('A\t' + namespace + '/') for line in changes))
    specs = [FINAL + ':' + path for path in sorted(paths)]
    specs += [commit + ':' + row['path'] for commit in (FINAL, PRODUCT) for row in binding['source_manifest']]
    fixed = blobs(specs)
    for row in manifest['files']:
        data = raw(AREA / row['path'])
        check('git/member/' + row['path'], pin_matches(row, data) and data == fixed[FINAL + ':' + namespace + '/' + row['path']])
    check('git/manifest_self', raw(AREA / 'CONTENT_MANIFEST.json') == fixed[FINAL + ':' + namespace + '/CONTENT_MANIFEST.json'])
    aggregate = sha(json.dumps({key: binding[key] for key in ('base_version', 'implementation_revision')}
        | {'files': binding['source_manifest']}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check('source/143identity', len(binding['source_manifest']) == 143 and aggregate == SOURCE
          and binding['source_sha256'] == baseline['source_sha256'] == SOURCE and baseline['product_git'] == PRODUCT)
    for row in binding['source_manifest']:
        data = raw(Path(binding['install_root']) / row['path'])
        check('source/Git_fixed_install/' + row['path'], pin_matches(row, data)
              and data == fixed[FINAL + ':' + row['path']] == fixed[PRODUCT + ':' + row['path']])
    for row in baseline['direct_pins']:
        check('source/prior_pin/' + row['path'], pin_matches(row, raw(row['path'])))
    check('source/original_asset', sha(raw(baseline['asset']['path'])) == baseline['asset']['sha256'])

    actual_files = {path.relative_to(RUNTIME).as_posix() for path in RUNTIME.rglob('*') if path.is_file()}
    check('runtime/all_253_originals', len(actual_files) == 253 and actual_files == {row['relative'] for row in archive['files']})
    totals = {'original_bytes': 0, 'shared_bytes': 0, 'byte_exact_files': 0, 'projected_files': 0}
    projections = []
    for row in archive['files']:
        original = raw(RUNTIME / row['relative'])
        shared = raw(AREA / row['copy'])
        label = 'runtime/' + row['relative']
        check(label + '/original_hash', len(original) == row['original_bytes'] and sha(original) == row['original_sha256'])
        check(label + '/shared_hash', len(shared) == row['shared_bytes'] and sha(shared) == row['sha256'])
        totals['original_bytes'] += len(original)
        totals['shared_bytes'] += len(shared)
        if row['byte_exact']:
            check(label + '/byte_exact', original == shared and row['reasoning_event_projection'] == [])
            totals['byte_exact_files'] += 1
        else:
            totals['projected_files'] += 1
            if row['relative'].endswith('/stdout.raw.bin'):
                expected, derivation, _ = project_events(io.BytesIO(original))
                check(label + '/stream_projection', shared == expected)
            elif row['relative'].endswith('.raw.zip'):
                derivation = zip_projection(original, shared, label)
            else:
                raise ValueError('projection_outside_registered_event_stream/' + row['relative'])
            check(label + '/projection_receipt', derivation == row['reasoning_event_projection'])
            projections.append({'path': row['relative'], 'changes': derivation})
    check('runtime/byte_totals', totals == {'original_bytes': 8304962, 'shared_bytes': 8305365, 'byte_exact_files': 247, 'projected_files': 6}
          and archive['original_bytes'] == totals['original_bytes'] and archive['shared_bytes'] == totals['shared_bytes'])
    check('runtime/retention', archive['original_files_deleted'] == 0 and archive['originals_retained_locally'] is True)

    old = read(AREA / 'FROZEN.json')
    revised = read(AREA / 'FROZEN_PROTOCOL_R1.json')
    revision = read(AREA / 'protocol_revisions/REVISION_01.json')
    active = read(AREA / 'ACTIVE_FREEZE.json')
    old_pins = {row['path']: row for row in old['direct_inputs']}
    new_pins = {row['path']: row for row in revised['direct_inputs']}
    changed_pins = {path for path in old_pins if old_pins[path] != new_pins[path]}
    expected_changes = {str((AREA / 'harness' / name).resolve()) for name in ('read_observation.py', 'run_slot.py')}
    check('freeze/178_with_two_registered_changes', len(old_pins) == len(new_pins) == 178
          and set(old_pins) == set(new_pins) and changed_pins == expected_changes == set(revision['changed_frozen_source_paths']))
    for path, pin in new_pins.items():
        check('freeze/current/' + path, pin_matches(pin, raw(path)))
    for name in ('read_observation.py', 'run_slot.py'):
        path = str((AREA / 'harness' / name).resolve())
        check('freeze/R0_preserved/' + name, pin_matches(old_pins[path], raw(AREA / 'protocol_revisions' / ('R0_' + name + '.txt'))))
    check('freeze/revision_bindings', revised['original_freeze_sha256'] == sha(raw(AREA / 'FROZEN.json'))
          and revised['protocol_revision_sha256'] == sha(raw(AREA / 'protocol_revisions/REVISION_01.json'))
          and active == {'name': 'FROZEN_PROTOCOL_R1.json', 'sha256': sha(raw(AREA / 'FROZEN_PROTOCOL_R1.json'))})
    profile = {'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium', 'service_tier': 'default'}
    check('freeze/profile_budget', all(freeze['model_profile'] == profile and freeze['new_consumer_cap'] == 3
          and freeze['replacement_consumers'] == 0 and freeze['business_limit'] == 4
          and freeze['task_seconds'] == 450 and freeze['process_seconds'] == 600 for freeze in (old, revised)))
    preflight = read(AREA / 'PREFLIGHT.json')
    infrastructure = read(AREA / 'checks/INFRA_PREFLIGHT_REVIEW.json')
    nested = []
    for pin in infrastructure['source_files']:
        path = REPO / pin['path']
        check('nested/current_pin/' + pin['path'], pin_matches(pin, raw(path)))
        nested.append({'path': str(path.resolve()), 'sha256': pin['sha256'], 'direct_rehash_member': str(path.resolve()) in old_pins})
    check('nested/18_committed_paths', len(nested) == 18)
    adapter_pairs = [('accepted_consumer_path', 'accepted_consumer_sha256'), ('event_loop_path', 'event_loop_sha256'),
                     ('result_matcher_path', 'result_matcher_sha256'), ('settings_path', 'settings_sha256')]
    for path_key, sha_key in adapter_pairs:
        check('nested/preflight/' + path_key, sha(raw(preflight['adapter_proof'][path_key])) == preflight['adapter_proof'][sha_key])
    runner_source = raw(AREA / 'harness/run_slot.py')
    adapter_source = raw(AREA / 'harness/consumer_adapter.py')
    ast.parse(runner_source)
    ast.parse(adapter_source)
    check('nested/direct_only_runner_observed', b"for row in frozen['direct_inputs']" in runner_source
          and b"sha(row['path'])" in runner_source)

    inputs = read(AREA / 'INPUTS.json')
    prompt = raw(AREA / 'inputs/PROMPT.txt')
    tool = read(AREA / 'inputs/TOOL_SCHEMA.json')
    rubric = read(AREA / 'scoring/RUBRIC.json')
    check('input/frozen_prompt_schema', sha(prompt) == inputs['prompt_sha256']
          and sha(raw(AREA / 'inputs/TOOL_SCHEMA.json')) == inputs['tool_schema_sha256']
          and rubric['common_prompt_verbatim'].encode() == prompt)
    cases = {}
    for row in inputs['cases']:
        case_id = row['case_id']
        folder = AREA / 'inputs' / case_id
        observation = read(row['input_file'])
        source_response = raw(row['source_response'])
        check('input/' + case_id + '/prior_response', sha(source_response) == row['source_response_sha256']
              and source_response == raw(folder / 'ORIGINAL_RESPONSE.json') and json.loads(source_response)['result'] == observation)
        check('input/' + case_id + '/result_pin', sha(raw(row['input_file'])) == row['input_sha256'])
        brief = observation['content'][0]['text'].encode()
        image = base64.b64decode(observation['content'][1]['data'], validate=True)
        check('input/' + case_id + '/brief_image', brief == raw(folder / 'ORIGINAL_BRIEF.json')
              and sha(brief) == row['original_brief_sha256'] and len(brief) == row['brief_UTF8_bytes']
              and image == raw(folder / 'ORIGINAL_IMAGE.png') and sha(image) == row['PNG_sha256'] and len(image) == row['PNG_bytes'])
        check('input/' + case_id + '/PNG_header', image[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', image[16:24]) == (512, 512))
        cases[case_id] = {'binding': row, 'observation': observation, 'brief': brief, 'image': image}

    sealed = read(AREA / 'ANSWERS_SEALED.json')
    answer_pins = {row['case_id']: row for row in sealed['answers']}
    score = read(AREA / 'scoring/AUTHOR_SCORES.json')
    check('scoring/frozen_rules', score['frozen_inputs']['rubric_sha256'] == sha(raw(AREA / 'scoring/RUBRIC.json'))
          and score['frozen_inputs']['case_answers_sha256'] == sha(raw(AREA / 'scoring/CASE_ANSWERS.json'))
          and score['frozen_inputs']['rules_changed'] is False)
    check('scoring/release_declared_after_seal', sealed['all_original_answers_preserved_before_scoring'] is True
          and 'after sealing' in score['scoring_release']
          and datetime.fromisoformat(score['scored_at_utc'].replace('Z', '+00:00')) > datetime.fromisoformat(rubric['frozen_at_utc'].replace('Z', '+00:00')))
    check('scoring/denominator_preserved', sealed['original_denominator'] == 3 and sealed['replacement_consumers'] == 0
          and score['summary']['accepted_cases'] == 0 and score['summary']['case_denominator'] == 3)

    sessions, threads, usage_sum = [], [], {}
    total_tools = total_business = total_admitted = total_empty_resources = total_images = 0
    delivered_text_bytes = delivered_PNG_bytes = 0
    for case_id in ('S1', 'S2', 'S3'):
        folder = RUNTIME / 'slots' / case_id
        label = 'slot/' + case_id
        started = read(folder / 'SLOT_STARTED.json')
        slot = read(folder / 'SLOT_RESULT.json')
        pub = read(folder / 'SLOT_PUBLICATION.json')
        consumer = read(folder / 'consumer/CONSUMER.json')
        timing = read(folder / 'consumer/FINAL_TIMING.json')
        proof = read(folder / 'ADAPTER_PROOF.json')
        ledger = read(folder / 'owner/TOOLS.json')
        binding_record = read(folder / 'consumer/RUNTIME_BINDING.json')
        final = raw(folder / 'consumer/PUBLIC_FINAL.txt')
        check(label + '/publication_hashes', sha(raw(folder / 'SLOT_RESULT.json')) == pub['result_sha256']
              and sha(raw(folder / 'consumer/CONSUMER.json')) == slot['consumer_record_sha256'])
        began = started['started_ns']
        deadline = began + 450_000_000_000
        lifecycle = began + 600_000_000_000
        check(label + '/original_450_600', started['task_deadline_ns'] == slot['task_deadline_ns'] == pub['original_task_deadline_ns'] == deadline
              and started['lifecycle_deadline_ns'] == slot['lifecycle_deadline_ns'] == pub['original_lifecycle_deadline_ns'] == lifecycle
              and consumer['deadline_ns'] == consumer['episode_deadline_ns'] == timing['original_turn_deadline_ns'] == deadline
              and began < consumer['started_ns'] < consumer['prompt_submitted_ns'] < consumer['final_received_ns']
              <= consumer['turn_completed_ns'] < consumer['cleanup_end_ns'] < timing['consumer_record_closed_ns']
              < slot['closed_ns'] < pub['published_ns'] < deadline)
        check(label + '/wall_recomputation', slot['wall_ns'] == slot['closed_ns'] - began
              and consumer['wall_ns'] == consumer['cleanup_end_ns'] - consumer['started_ns']
              and consumer['prompt_to_final_ns'] == consumer['final_received_ns'] - consumer['prompt_submitted_ns']
              and timing['full_turn_wall_ns'] == timing['consumer_record_closed_ns'] - consumer['started_ns'])
        if case_id == 'S1':
            check(label + '/original_freeze_before', old['frozen_ns'] < began < pub['published_ns'] < revision['started_ns'])
        else:
            check(label + '/revised_freeze_before', revised['frozen_ns'] < began and slot['freeze_sha256'] == sha(raw(AREA / 'FROZEN_PROTOCOL_R1.json')))
        check(label + '/answers_original', pin_matches(answer_pins[case_id], final)
              and final == raw(answer_pins[case_id]['copy_path']) == raw(folder / 'consumer/final.txt')
              and answer_pins[case_id]['slot_publication_sha256'] == sha(raw(folder / 'SLOT_PUBLICATION.json')))
        check(label + '/seal_after_publication', pub['published_ns'] < sealed['sealed_ns'])
        argv = consumer['argv']
        configs = {}
        for index, arg in enumerate(argv[:-1]):
            if arg == '-c':
                key, value = argv[index + 1].split('=', 1)
                configs[key] = value
        check(label + '/fresh_requested_profile', '--ephemeral' in argv and '--ignore-user-config' in argv
              and '--ignore-rules' in argv and '--strict-config' in argv and argv[-1] == '-'
              and not set(argv) & {'resume', 'fork', '--last', '--all'}
              and argv[argv.index('-m') + 1] == 'gpt-6.1-sol'
              and configs['model_reasoning_effort'] == '"medium"' and configs['service_tier'] == '"default"'
              and consumer['expected_thread_id'] is None and consumer['turn_index'] == 1)
        check(label + '/actual_CLI_Python_identity', sha(raw(argv[0])) == proof['CLI_sha256'] == preflight['CLI_sha256']
              and binding_record['actual_executable_sha256'] == proof['Python_sha256'] == sha(raw(binding_record['actual_executable'])))
        check(label + '/runtime_creation_binding', binding_record['confirmed'] is True
              and binding_record['launcher_pid'] == consumer['consumer_pid']
              and binding_record['runtime_pid'] == consumer['bridge_cleanup']['instances'][0]['started']['pid']
              and binding_record['launcher_created_filetime'] < binding_record['runtime_created_filetime']
              and binding_record['parent_chain'][0]['pid'] == binding_record['runtime_pid'])
        runtime_exit = consumer['runtime_exit']
        process_exit = consumer['process_cleanup']
        check(label + '/actual_held_reader_exit1', runtime_exit['confirmed'] is True and runtime_exit['exited'] is True
              and runtime_exit['exit_code'] == 1 and runtime_exit['handle_closed'] is True
              and runtime_exit['original_deadline_ns'] == deadline and runtime_exit['closed_ns'] < deadline)
        check(label + '/CLI_exit0_readers_pipes', consumer['exit_code'] == 0 and consumer['process_reaped'] is True
              and consumer['readers_stopped'] is True and consumer['deadline_timer_fired'] is False
              and process_exit['confirmed'] is True and process_exit['reaped'] is True and process_exit['exit_code'] == 0
              and process_exit['kill_requested'] is False and all(process_exit['pipes_closed'].values())
              and process_exit['process_handle_closed'] is True and not process_exit['errors'])
        bridge = consumer['bridge_cleanup']
        check(label + '/normal_receipt_unknown_preserved', bridge['receipt_status'] == 'unknown'
              and bridge['confirmed'] is None and bridge['missing_exit_count'] == 1
              and bridge['instances'][0]['exit'] is None and bridge['instances'][0]['confirmed'] is None)
        for path_key, sha_key in adapter_pairs:
            check(label + '/adapter_source/' + path_key, sha(raw(proof[path_key])) == proof[sha_key] == preflight['adapter_proof'][sha_key])
        server_path = str((AREA / 'harness/read_observation.py').resolve())
        expected_server_sha = old_pins[server_path]['sha256'] if case_id == 'S1' else new_pins[server_path]['sha256']
        check(label + '/server_generation', proof['server_sha256'] == expected_server_sha)
        check(label + '/original_failure_retained', slot['status'] == consumer['status'] == 'failed'
              and consumer['valid_completion'] is False and slot['errors'][0]['message'] == 'consumer_execution_or_delivery_not_completed'
              and consumer['errors'][0]['errors'][0] == {'reason': 'owner_and_CLI_attempt_count', 'owner': ledger['attempts'], 'CLI': len(consumer['tool_calls'])})

        stdout = raw(folder / 'consumer/stdout.raw.bin')
        _, private_changes, public_events = project_events(io.BytesIO(stdout))
        check(label + '/stdout_original_pin', sha(stdout) == consumer['stdout_raw_sha256'] and len(stdout) == consumer['stdout_raw_bytes'])
        thread_events = [event for event in public_events if event['type'] == 'thread.started']
        complete_events = [event for event in public_events if event['type'] == 'turn.completed']
        completed_tools = [event for event in public_events if event['type'] == 'item.completed' and event.get('item', {}).get('type') == 'mcp_tool_call']
        check(label + '/one_fresh_thread_turn', len(thread_events) == len(complete_events) == 1
              and thread_events[0]['thread_id'] == consumer['thread_id'])
        check(label + '/numeric_usage_original', [event['usage'] for event in complete_events] == consumer['raw_usage_events']
              and consumer['usage'] == consumer['raw_usage_events'][0])
        check(label + '/public_tools_exact', completed_tools == [{key: value for key, value in event.items() if key != 'perf_ns'} for event in consumer['tool_calls']])
        final_events = [event['item']['text'].encode() for event in public_events if event['type'] == 'item.completed' and event.get('item', {}).get('type') == 'agent_message']
        check(label + '/public_final_event', bool(final_events) and final_events[-1] == final)
        check(label + '/private_bodies_hash_only', len(private_changes) == 1)
        public_log_private_rows = []
        for line in io.BytesIO(raw(folder / 'consumer/events.jsonl')):
            outer = members(line)
            start, end = outer['event']
            event_bytes = line[start:end]
            metadata = event_metadata(event_bytes)
            if metadata['item_type'] in ('reasoning', 'analysis'):
                fields = members(event_bytes)
                item_fields = members(event_bytes, fields['item'][0])
                check(label + '/public_log_redacted_shape', set(item_fields) == {'type', 'redacted'}
                      and scalar(event_bytes, item_fields, 'redacted') is True)
                public_log_private_rows.append({'original_line_sha256': scalar(event_bytes, fields, 'raw_sha256'),
                    'original_line_bytes': scalar(event_bytes, fields, 'raw_bytes'),
                    'item_type': metadata['item_type']})
        check(label + '/public_log_private_hashes', public_log_private_rows == [
            {key: row[key] for key in ('original_line_sha256', 'original_line_bytes', 'item_type')} for row in private_changes])
        threads.append(consumer['thread_id'])
        for key, value in complete_events[0]['usage'].items():
            usage_sum[key] = usage_sum.get(key, 0) + value

        tools = consumer['tool_calls']
        business = [event for event in tools if event['item']['server'] == 'arm_engine' and event['item']['tool'] == 'read_observation']
        resources = [event for event in tools if event['item']['server'] == 'codex']
        check(label + '/four_call_budget', len(tools) <= 4 and ledger['attempts'] <= 4 and ledger['admitted'] <= 4
              and len(business) == ledger['attempts'] == (2 if case_id == 'S1' else 1) and len(resources) == 2)
        for event in resources:
            item = event['item']
            check(label + '/empty_resource/' + item['tool'], item['tool'] in ('list_mcp_resources', 'list_mcp_resource_templates')
                  and item['status'] == 'completed' and list(json.loads(item['result']['content'][0]['text']).values()) == [[]])
        service_windows = []
        for index, event in enumerate(business, 1):
            request = read(folder / 'owner' / ('tool_' + str(index).zfill(2)) / 'REQUEST.json')
            response = read(folder / 'owner' / ('tool_' + str(index).zfill(2)) / 'RESPONSE.json')
            check(label + '/business_ids/' + str(index), request['id'] == response['id']
                  and request['params']['name'] == 'read_observation' and request['params']['arguments'] == event['item']['arguments'] == {}
                  and isinstance(request['params'].get('_meta'), dict))
            turn_metadata = request['params']['_meta']['x-codex-turn-metadata']
            check(label + '/actual_transport_profile/' + str(index), turn_metadata['model'] == 'gpt-6.1-sol'
                  and turn_metadata['reasoning_effort'] == 'medium'
                  and turn_metadata['thread_id'] == turn_metadata['session_id'] == consumer['thread_id'])
            check(label + '/business_original_to_CLI/' + str(index), event['item']['result']['content'] == response['result']['content'])
            if case_id == 'S1':
                check(label + '/original_meta_rejection/' + str(index), response['result']['isError'] is True
                      and response['result']['content'] == [{'type': 'text', 'text': 'empty_parameter_read_observation_required'}])
            else:
                check(label + '/actual_original_delivery/' + str(index), response['result'] == cases[case_id]['observation']
                      and event['item']['status'] == 'completed')
                delivered_text_bytes += len(cases[case_id]['brief'])
                delivered_PNG_bytes += len(cases[case_id]['image'])
            row = ledger['tools'][index - 1]
            if 'closed_ns' in row:
                check(label + '/service_clock/' + str(index), began < row['received_ns'] < row['closed_ns'] < deadline)
                service_windows.append({'attempt': index, 'received_ns': row['received_ns'], 'closed_ns': row['closed_ns'],
                    'saved_service_ns': row['closed_ns'] - row['received_ns'], 'CLI_completion_ns': event['perf_ns'],
                    'receive_to_CLI_completion_ns': event['perf_ns'] - row['received_ns']})
        wire_requests = []
        wire_responses = []
        for instance in bridge['instances']:
            audit = Path(instance['directory'])
            for wire in sorted(audit.glob('[0-9][0-9][0-9]')):
                request = read(wire / 'TX.bin')
                wire_requests.append(request)
                if (wire / 'RX.bin').exists():
                    response = read(wire / 'RX.bin')
                    wire_responses.append(response)
                    check(label + '/wire_id/' + wire.name, request['id'] == response['id'])
                    if request.get('method') == 'tools/list':
                        check(label + '/wire_same_schema', response['result']['tools'] == [tool])
                    if request.get('method') == 'tools/call':
                        check(label + '/wire_business_matches_owner/' + wire.name,
                              response in [read(folder / 'owner' / ('tool_' + str(index).zfill(2)) / 'RESPONSE.json') for index in range(1, len(business) + 1)])
        protocol_errors = [response['error'] for response in wire_responses if 'error' in response]
        check(label + '/resource_protocol_generation', len(protocol_errors) == (2 if case_id == 'S1' else 0)
              and all(error['code'] == -32601 for error in protocol_errors))
        source_archive = read(folder / 'consumer/ARCHIVE.json')
        original_zip = raw(folder / 'consumer.raw.zip')
        check(label + '/own_raw_zip_hash', sha(original_zip) == source_archive['archive_sha256'])
        with zipfile.ZipFile(io.BytesIO(original_zip)) as zipped:
            check(label + '/own_raw_zip_member_set', set(zipped.namelist()) == set(source_archive['source_files_sha256']))
            for name, digest in source_archive['source_files_sha256'].items():
                member = zipped.read(name)
                check(label + '/own_raw_zip_pin/' + name, sha(member) == digest and member == raw(folder / 'consumer' / name))
        expected_images = 0 if case_id == 'S1' else 1
        check(label + '/image_count_bytes', consumer['public_image_count'] == slot['native_image_deliveries'] == expected_images
              and consumer['public_image_bytes'] == (0 if case_id == 'S1' else len(cases[case_id]['image'])))
        total_tools += len(tools)
        total_business += len(business)
        total_admitted += ledger['admitted']
        total_empty_resources += len(resources)
        total_images += expected_images
        sessions.append({'case_id': case_id, 'thread_id': consumer['thread_id'], 'CLI_pid': consumer['consumer_pid'],
            'reader_pid': binding_record['runtime_pid'], 'started_ns': began, 'closed_ns': slot['closed_ns'],
            'published_ns': pub['published_ns'], 'full_slot_ns': slot['wall_ns'], 'consumer_ns': consumer['wall_ns'],
            'consumer_record_ns': timing['full_turn_wall_ns'], 'prompt_to_final_ns': consumer['prompt_to_final_ns'],
            'tool_count': len(tools), 'business_attempts': ledger['attempts'], 'business_admitted': ledger['admitted'],
            'empty_resource_completions': len(resources), 'PNG_deliveries': expected_images,
            'actual_tool_text_bytes': 0 if case_id == 'S1' else len(cases[case_id]['brief']),
            'actual_PNG_bytes': consumer['public_image_bytes'], 'service_windows': service_windows,
            'CLI_exit_code': consumer['exit_code'], 'reader_retained_exit': runtime_exit,
            'normal_bridge_receipt': bridge, 'usage': consumer['raw_usage_events'][0],
            'provider_requests': consumer['provider_requests'], 'fees': consumer['fees'], 'image_tokens': consumer['image_tokens'],
            'harness_status': slot['status'], 'harness_failure': consumer['errors'], 'private_event_metadata': private_changes})

    check('cohort/three_independent_threads', len(set(threads)) == 3)
    check('cohort/serial_order', all(left['published_ns'] < right['started_ns'] for left, right in zip(sessions, sessions[1:])))
    check('cohort/counts', (total_tools, total_business, total_admitted, total_empty_resources, total_images) == (10, 4, 2, 6, 2))
    check('cohort/transport_bytes', delivered_text_bytes == 235243 and delivered_PNG_bytes == 3776
          and sum(len(case['brief']) for case in cases.values()) == 350451)
    check('cohort/usage_totals', usage_sum == {'input_tokens': 95115, 'cached_input_tokens': 62464,
          'cache_write_input_tokens': 0, 'output_tokens': 2913, 'reasoning_output_tokens': 299})
    check('protocol/revision_between_cases', sessions[0]['published_ns'] < revision['started_ns']
          < revision['closed_ns'] < revised['frozen_ns'] < sessions[1]['started_ns'])
    check('protocol/original_answer_preserved', revision['S1_slot_result_sha256'] == sha(raw(RUNTIME / 'slots/S1/SLOT_RESULT.json'))
          and revision['S1_replacement_consumers'] == 0)
    prep = read(AREA / 'PREPARATION_TIMING.json')
    prep_start = prep['automated_input_preparation_started_ns']
    prep_close = prep['automated_input_preparation_closed_ns']
    pure_preflights = []
    for label, folder, closure in [('R0', RUNTIME / 'preflight', preflight['stdio_closure']),
                                   ('R1', RUNTIME / 'preflight_r1', revision['preflight_closure'])]:
        ledger = read(folder / 'owner/TOOLS.json')
        check('preflight/' + label + '/count_closed', ledger['attempts'] == 5 and ledger['admitted'] == 4
              and closure['confirmed'] is True and closure['exit_code'] == 0 and closure['reader_stopped'] is True
              and closure['process_handle_closed'] is True and all(closure['pipes_closed'].values())
              and not closure['forced_kill'] and not closure['errors'])
        pure_preflights.append({'revision': label, 'tool_attempts': 5, 'admitted_original_deliveries_to_Python': 4,
            'closed': closure})
    check('preflight/before_models', prep_start < prep_close < preflight['started_ns'] < preflight['closed_ns']
          < old['preparation_freeze_started_ns'] < old['frozen_ns'] < sessions[0]['started_ns'])
    cleanup = read(AREA / 'CACHE_CLEANUP.json')
    check('cleanup/zero_deleted', cleanup['deleted'] == [] and cleanup['runtime_files_deleted'] == 0)
    full_ns = sum(row['full_slot_ns'] for row in sessions)
    consumer_ns = sum(row['consumer_ns'] for row in sessions)
    publication_end = sessions[-1]['published_ns']
    cost = {'full_slots_ns': full_ns, 'consumer_loops_ns': consumer_ns,
        'slots_through_publication_timestamps_ns': sum(row['published_ns'] - row['started_ns'] for row in sessions),
        'slot_result_and_publication_timestamp_overhead_ns': sum(row['published_ns'] - row['closed_ns'] for row in sessions),
        'prompt_to_final_ns': sum(row['prompt_to_final_ns'] for row in sessions),
        'automated_input_preparation_ns': prep_close - prep_start,
        'R0_protocol_and_CLI_preflight_ns': preflight['closed_ns'] - preflight['started_ns'],
        'R0_freeze_ns': old['frozen_ns'] - old['preparation_freeze_started_ns'],
        'R1_protocol_qualification_ns': revision['closed_ns'] - revision['started_ns'],
        'automated_preparation_to_last_publication_elapsed_ns': publication_end - prep_start,
        'first_slot_to_last_publication_elapsed_ns': publication_end - sessions[0]['started_ns'],
        'manual_planning_and_adapter_authoring_wall_ns': None,
        'fees': None, 'provider_request_count': None, 'CPU_RSS': None,
        'scope': 'Consumer, prompt-to-final and service windows are nested. full_slots_ns ends at SLOT_RESULT.closed_ns before outer result/publication saving. Publication timestamp windows are separately available; final publication write completion is unmeasured. Preparation and protocol windows are separate. Bounding campaign elapsed time includes unclassified gaps.'}
    decision = read(AREA / 'DECISION.json')
    check('decision/full_slot_cost', abs(decision['cost_scope']['full_slot_seconds_sum'] - full_ns / 1e9) < 1e-9)
    check('decision/failures_unknowns_retained', decision['accepted_cases'] == 0 and decision['case_denominator'] == 3
          and decision['delivery']['undelivered_case'] == 'S1' and decision['provider_request_count'] is None
          and decision['fees'] is None and len(decision['audit_caveats']) == 4)
    return {'status': 'passed_checked_scope' if all(row['passed'] for row in CHECKS) else 'failed',
        'checks': len(CHECKS), 'failed_checks': [row for row in CHECKS if not row['passed']],
        'author_commit': FINAL, 'namespace_Git_paths': len(paths), 'source_files': 143, 'source_sha256': SOURCE,
        'archive_totals': totals, 'projections': projections, 'freeze_inputs': len(old_pins),
        'freeze_changed_paths': sorted(changed_pins), 'nested_infrastructure_pins_currently_verified': nested,
        'transitive_preexecution_rehash': 'unproven; original runner checks direct_inputs only',
        'scoring_order': 'Monotonic seal follows all original publications. Stored release declaration follows sealing. Scorer UTC is later than rubric UTC. A shared monotonic scoring-start receipt is absent.',
        'sessions': sessions, 'cost': cost, 'usage': usage_sum,
        'all_CLI_tool_completions': total_tools, 'business_attempts': total_business,
        'business_admitted': total_admitted, 'empty_resource_completions': total_empty_resources,
        'native_PNG_deliveries': total_images, 'delivered_brief_bytes': delivered_text_bytes,
        'delivered_PNG_bytes': delivered_PNG_bytes, 'protocol_preflights': pure_preflights,
        'private_body_handling': 'Only type/id scalar metadata decoded. Private line bytes hashed and skipped lexically; body fields never decoded or output.',
        'new_live_Blender': 0, 'new_MCP': 0, 'new_raster': 0, 'new_image_encoding': 0, 'new_model': 0, 'new_paid': 0,
        'initial_metadata_reader_failure': 'READER_ATTEMPT_001.json', 'input_pins': list(PINS.values())}


if __name__ == '__main__':
    HERE.mkdir(parents=True, exist_ok=True)
    try:
        result = main()
    except Exception:
        (HERE / 'CHECKER_ERROR_001.txt').write_text(traceback.format_exc(), encoding='utf8')
        raise
    (HERE / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: result[key] for key in ('status', 'checks', 'failed_checks', 'archive_totals', 'cost', 'usage')}, ensure_ascii=False))
    sys.exit(0 if result['status'] == 'passed_checked_scope' else 1)
