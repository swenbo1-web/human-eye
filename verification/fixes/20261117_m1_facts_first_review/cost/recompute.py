"""Independent saved-byte identity, formatter-window and complete consumption cost audit."""

from pathlib import Path
import ast
import base64
from collections import Counter
import csv
import hashlib
import io
import json
import statistics
import struct
import subprocess
import sys
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
AREA = REPO / 'verification/m1_source_region_facts_first_001'
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')
FINAL = '544cf4f123c35fbca24b8f425acc30fd3308b178'
OLD = '29f35a771c1d137455602adf28418f45e2788e6a'
A_GIT = 'be28a9cbc1311580e75c3c8d7f0f084967f0207c'
B_GIT = '08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1'
B_SOURCE = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
PRODUCT_PATH = 'human_eye_plugin/live_spatial_mcp.py'
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


def public_events(data):
    """Decode public events after lexically skipping any private event bodies."""
    output, private = [], []
    for line in io.BytesIO(data):
        fields = members(line)
        item_fields = members(line, fields['item'][0]) if 'item' in fields else {}
        event_type = scalar(line, fields, 'type')
        item_type = scalar(line, item_fields, 'type')
        if event_type in ('reasoning', 'analysis') or item_type in ('reasoning', 'analysis'):
            private.append({'line_sha256': sha(line), 'bytes': len(line), 'type': item_type or event_type})
        else:
            output.append(json.loads(line))
    return output, private


def closed_process(label, receipt, expected_exit=0):
    check(label, receipt['confirmed'] is True and receipt['exit_code'] == expected_exit
          and receipt['process_handle_closed'] is True and receipt['reader_stopped'] is True
          and all(receipt['pipes_closed'].values()) and not receipt['forced_kill'] and not receipt['errors'])


def main():
    manifest = read(AREA / 'CONTENT_MANIFEST.json')
    baseline = read(AREA / 'BASELINE.json')
    archive = read(AREA / 'RUNTIME_ARCHIVE.json')
    bindings = {'OLD': read(AREA / 'historical/PRODUCT_BINDING.json'),
                'A': read(AREA / 'A_RUN_BINDING.json'), 'B': read(AREA / 'B_RUN_BINDING.json')}
    commits = {'OLD': OLD, 'A': A_GIT, 'B': B_GIT}
    namespace = AREA.relative_to(REPO).as_posix()
    paths = {namespace + '/' + row['path'] for row in manifest['files']} | {namespace + '/CONTENT_MANIFEST.json'}
    changed = set(git('diff', '--name-only', baseline['baseline_git'], FINAL).decode().splitlines())
    check('git/1010_namespace_plus_product', len(paths) == 1010 and changed == paths | {PRODUCT_PATH})
    check('git/old_to_A_single_product_path', git('diff', '--name-only', OLD, A_GIT, '--', 'human_eye_plugin').decode().splitlines() == [PRODUCT_PATH])
    check('git/A_to_B_single_product_path', git('diff', '--name-only', A_GIT, B_GIT, '--', 'human_eye_plugin').decode().splitlines() == [PRODUCT_PATH])
    check('git/B_to_final_product_equal', not git('diff', '--name-only', B_GIT, FINAL, '--', 'human_eye_plugin'))
    specs = [FINAL + ':' + path for path in sorted(changed)]
    specs += [commits[label] + ':' + row['path'] for label, binding in bindings.items() for row in binding['source_manifest']]
    fixed = blobs(specs)
    for row in manifest['files']:
        data = raw(AREA / row['path'])
        check('git/member/' + row['path'], pin_matches(row, data) and data == fixed[FINAL + ':' + namespace + '/' + row['path']])
    check('git/self_manifest', raw(AREA / 'CONTENT_MANIFEST.json') == fixed[FINAL + ':' + namespace + '/CONTENT_MANIFEST.json'])
    check('git/current_product', raw(REPO / PRODUCT_PATH) == fixed[FINAL + ':' + PRODUCT_PATH] == fixed[B_GIT + ':' + PRODUCT_PATH])
    for pin in baseline['direct_pins']:
        check('prior_pin/' + pin['path'], pin_matches(pin, raw(pin['path'])))

    for label, binding in bindings.items():
        aggregate = sha(json.dumps({key: binding[key] for key in ('base_version', 'implementation_revision')}
            | {'files': binding['source_manifest']}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
        check('source/' + label + '/aggregate143', len(binding['source_manifest']) == 143 and aggregate == binding['source_sha256'])
        for row in binding['source_manifest']:
            data = raw(Path(binding['install_root']) / row['path'])
            check('source/' + label + '/Git_install/' + row['path'], pin_matches(row, data) and data == fixed[commits[label] + ':' + row['path']])
        if label == 'OLD':
            continue
        build = read(AREA / ('build_' + label) / 'BUILD_INSTALL.json')
        wheel = raw(build['wheel'])
        check('wheel/' + label + '/build_binding', build['binding'] == binding and build['pip_exit'] == 0
              and sha(wheel) == build['wheel_sha256'] == binding['wheel_sha256'])
        with zipfile.ZipFile(io.BytesIO(wheel)) as zipped:
            record = next(name for name in zipped.namelist() if name.endswith('.dist-info/RECORD'))
            for name, digest, length in csv.reader(io.StringIO(zipped.read(record).decode())):
                if name == record:
                    continue
                data = zipped.read(name)
                check('wheel/' + label + '/RECORD/' + name, len(data) == int(length)
                      and digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())
            for row in binding['source_manifest']:
                check('wheel/' + label + '/installed/' + row['path'], zipped.read(row['path']) == raw(Path(binding['install_root']) / row['path']))
    check('source/fixed_B', bindings['B']['source_sha256'] == B_SOURCE and bindings['B']['preparation_git'] == B_GIT)
    identity_diffs = {}
    for first, second in [('OLD', 'A'), ('A', 'B')]:
        left = {row['path']: row['sha256'] for row in bindings[first]['source_manifest']}
        right = {row['path']: row['sha256'] for row in bindings[second]['source_manifest']}
        difference = sorted(path for path in left if left[path] != right[path])
        check('source/diff/' + first + '_' + second, set(left) == set(right) and difference == [PRODUCT_PATH])
        identity_diffs[first + '_' + second] = difference

    actual = {path.relative_to(RUNTIME).as_posix() for path in RUNTIME.rglob('*') if path.is_file()}
    check('runtime/913_all_originals', len(actual) == 913 and actual == {row['relative'] for row in archive['files']})
    original_total = 0
    for row in archive['files']:
        original = raw(RUNTIME / row['relative'])
        shared = raw(AREA / row['copy'])
        label = 'runtime/' + row['relative']
        check(label + '/original', len(original) == row['original_bytes'] and sha(original) == row['original_sha256'])
        check(label + '/same_shared', original == shared and row['byte_exact'] is True
              and len(shared) == row['shared_bytes'] and sha(shared) == row['sha256'] and row['reasoning_event_projection'] == [])
        original_total += len(original)
        if row['relative'].endswith('.raw.zip'):
            with zipfile.ZipFile(io.BytesIO(original)) as zipped:
                metadata = row['zip_members']
                check(label + '/zip_members_count', len(metadata) == len(zipped.infolist()))
                for index, info in enumerate(zipped.infolist()):
                    data = zipped.read(info)
                    pin = metadata[index]
                    check(label + '/zip_member/' + info.filename, pin['index'] == index and pin['name'] == info.filename
                          and pin['byte_exact'] is True and len(data) == pin['original_bytes'] == pin['shared_bytes']
                          and sha(data) == pin['original_sha256'] == pin['sha256'])
    check('runtime/bytes_retained', original_total == archive['original_bytes'] == archive['shared_bytes'] == 26826163
          and archive['original_files_deleted'] == 0 and archive['originals_retained_locally'] is True and archive['projected_members'] == [])

    contract = read(AREA / 'BENCHMARK_CONTRACT.json')
    benchmark = read(AREA / 'BENCHMARK_RESULT.json')
    publication = read(AREA / 'BENCHMARK_PUBLICATION.json')
    check('benchmark/frozen_contract', sha(raw(AREA / 'BENCHMARK_CONTRACT.json')) == benchmark['contract_sha256']
          and contract['registered_ns'] < benchmark['started_ns'] and contract['pair_order'] == ['AB', 'BA', 'AB', 'BA', 'AB']
          and contract['pairs_per_case'] == 5 and contract['calls_per_window'] == 20 and contract['warmup_calls_per_case_per_candidate'] == 2)
    check('benchmark/publication', publication['result_sha256'] == sha(raw(AREA / 'BENCHMARK_RESULT.json'))
          and publication['started_ns'] == benchmark['started_ns'] < benchmark['closed_before_worker_cleanup_ns'] < publication['closed_ns'])
    worker_source = raw(AREA / 'projection_worker.py')
    ast.parse(worker_source)
    check('benchmark/instrumentation_scope_source', b"if operation == 'profile':" in worker_source
          and b'mcp.copy = types.SimpleNamespace(deepcopy=counted_copy)' in worker_source
          and b"counters['formatter_deepcopy_calls'] += 1" in worker_source
          and b'call_elapsed += time.perf_counter_ns() - call_started' in worker_source
          and b'Image.Image.save = forbidden_encoding' in worker_source and b'np.savez_compressed = forbidden_encoding' in worker_source)
    raw_calls = {}
    calls_in_clock_order = []
    total_iterations = 0
    operations = Counter()
    interval_ns = timed_ns = timed_iterations = 0
    closures = read(RUNTIME / 'projection_benchmark/CLOSURES.json')
    for label, binding in bindings.items():
        folder = RUNTIME / 'projection_benchmark' / label / 'stdio'
        start = read(folder / 'START.json')
        closed = read(folder / 'CLOSE.json')
        closed_process('benchmark/' + label + '/closed', closed)
        check('benchmark/' + label + '/same_closure_deadline', closed == closures[label]
              and closed['pid'] == start['pid'] and closed['closed_ns'] < start['deadline_ns']
              and start['deadline_ns'] == benchmark['started_ns'] + 300_000_000_000)
        for rpc in sorted(folder.glob('rpc_*')):
            request = read(rpc / 'TX.bin')
            receipt = read(rpc / 'RECEIPT.json')
            response = read(rpc / 'RESPONSE.json')
            wire = raw(rpc / 'RX.bin')
            check('benchmark/' + label + '/' + rpc.name + '/wire', json.loads(wire) == response and 'error' not in response
                  and receipt['RX_sha256'] == sha(wire) and receipt['RX_bytes'] == len(wire)
                  and receipt['TX_bytes'] == len(raw(rpc / 'TX.bin'))
                  and request['id'] == response['id'] == receipt['id'] and receipt['error'] is None)
            value = response['result']
            check('benchmark/' + label + '/' + rpc.name + '/installed_formatter', value['source_sha256'] == binding['source_sha256']
                  and Path(value['import_path']).resolve() == (Path(binding['install_root']) / PRODUCT_PATH).resolve()
                  and value['operation'] == request['method'] and value['iterations'] == request['params']['iterations']
                  and value['text_sha256'] == sha(value['text'].encode()) and value['text_UTF8_bytes'] == len(value['text'].encode())
                  and value['input_unchanged'] is True and value['PNG_NPZ_encodes'] == value['raster'] == 0)
            check('benchmark/' + label + '/' + rpc.name + '/window', 0 < value['elapsed_ns'] <= value['window_elapsed_ns']
                  < receipt['elapsed_ns'] and receipt['elapsed_ns'] == receipt['closed_ns'] - receipt['started_ns'])
            if value['operation'] != 'profile':
                check('benchmark/' + label + '/' + rpc.name + '/uninstrumented', all(count == 0 for count in value['counters'].values()))
            if value['operation'] != 'memory':
                check('benchmark/' + label + '/' + rpc.name + '/no_tracemalloc', value['Python_tracemalloc_current_peak_bytes'] is None)
            raw_calls[(label, receipt['index'])] = {'request': request, 'receipt': receipt, 'value': value}
            calls_in_clock_order.append((receipt['started_ns'], label, receipt['index']))
            total_iterations += value['iterations']
            operations[value['operation']] += value['iterations']
            interval_ns += value['elapsed_ns']
            if value['operation'] == 'timed':
                timed_iterations += value['iterations']
                timed_ns += value['elapsed_ns']
    check('benchmark/63RPC_639formatter_600timed', len(raw_calls) == 63 and total_iterations == 639 and timed_iterations == 600
          and dict(operations) == {'warmup': 12, 'timed': 600, 'export': 15, 'profile': 6, 'memory': 6})
    check('benchmark/raw_summary_order', [(label, index) for _, label, index in sorted(calls_in_clock_order)]
          == [(row['candidate'], row['rpc_index']) for row in benchmark['calls']])
    for row in benchmark['calls']:
        original = raw_calls[(row['candidate'], row['rpc_index'])]['value']
        check('benchmark/summary_call/' + row['candidate'] + '/' + str(row['rpc_index']),
              row['case'] == original['case'] and row['operation'] == original['operation'] and row['iterations'] == original['iterations']
              and row['elapsed_ns'] == original['elapsed_ns'] and row['text_sha256'] == original['text_sha256']
              and row['counters'] == original['counters'] and row['memory'] == original['Python_tracemalloc_current_peak_bytes'])
    medians = []
    profiles = []
    for case_id in ('S1', 'S2', 'S3'):
        selected = [row for row in benchmark['pairs'] if row['case'] == case_id]
        check('benchmark/' + case_id + '/five_pairs', len(selected) == 5)
        timed = {label: [row for row in benchmark['calls'] if row['case'] == case_id and row['candidate'] == label and row['operation'] == 'timed'] for label in ('A', 'B')}
        for pair_index, pair in enumerate(selected):
            first = raw_calls[('A', timed['A'][pair_index]['rpc_index'])]
            second = raw_calls[('B', timed['B'][pair_index]['rpc_index'])]
            left, right = first['value'], second['value']
            actual_order = 'AB' if first['receipt']['started_ns'] < second['receipt']['started_ns'] else 'BA'
            check('benchmark/' + case_id + '/pair/' + str(pair_index + 1), pair['pair'] == pair_index + 1
                  and pair['order'] == actual_order == contract['pair_order'][pair_index]
                  and pair['iterations'] == left['iterations'] == right['iterations'] == 20
                  and pair['A_elapsed_ns'] == left['elapsed_ns'] and pair['B_elapsed_ns'] == right['elapsed_ns']
                  and pair['A_window_elapsed_ns'] == left['window_elapsed_ns'] and pair['B_window_elapsed_ns'] == right['window_elapsed_ns']
                  and left['text'] == right['text'] and left['native_images'] == right['native_images'])
        a = statistics.median(row['A_elapsed_ns'] for row in selected)
        b = statistics.median(row['B_elapsed_ns'] for row in selected)
        summary = next(row for row in benchmark['summary'] if row['case'] == case_id)
        check('benchmark/' + case_id + '/median', summary['A_median_ns'] == a and summary['B_median_ns'] == b
              and abs(summary['B_time_improvement_fraction'] - (1 - b / a)) < 1e-15)
        medians.append({'case': case_id, 'iterations_per_window': 20, 'paired_windows': 5,
            'A_window_median_ns': a, 'B_window_median_ns': b, 'improvement_fraction': 1 - b / a,
            'all_five_B_windows_faster': all(row['B_elapsed_ns'] < row['A_elapsed_ns'] for row in selected)})
        saved_profile = read(RUNTIME / 'projection_benchmark' / (case_id + '_PROFILES.json'))
        for label in ('A', 'B'):
            record = next(row for row in benchmark['calls'] if row['case'] == case_id and row['candidate'] == label and row['operation'] == 'profile')
            measured = raw_calls[(label, record['rpc_index'])]['value']
            check('profile/' + case_id + '/' + label, saved_profile['profiles'][label] == measured
                  and measured['iterations'] == 1 and measured['counters']['formatter_deepcopy_calls'] == (37 if label == 'A' else 1)
                  and measured['counters']['formatter_json_dumps_calls'] == 1)
            memory_record = next(row for row in benchmark['calls'] if row['case'] == case_id and row['candidate'] == label and row['operation'] == 'memory')
            memory_value = raw_calls[(label, memory_record['rpc_index'])]['value']
            current_bytes, peak_bytes = memory_value['Python_tracemalloc_current_peak_bytes']
            check('profile/' + case_id + '/' + label + '/separate_memory_raw', saved_profile['memory'][label] == memory_value
                  and memory_value['iterations'] == 1 and 0 <= current_bytes <= peak_bytes)
        check('profile/' + case_id + '/work_reduced', saved_profile['profiles']['B']['counters']['deepcopy_argument_JSON_UTF8_bytes']
              < saved_profile['profiles']['A']['counters']['deepcopy_argument_JSON_UTF8_bytes'])
        profiles.append({'case': case_id, 'A': saved_profile['profiles']['A']['counters'], 'B': saved_profile['profiles']['B']['counters'],
            'A_memory_current_peak_bytes': saved_profile['memory']['A']['Python_tracemalloc_current_peak_bytes'],
            'B_memory_current_peak_bytes': saved_profile['memory']['B']['Python_tracemalloc_current_peak_bytes']})
        for detail in (None, 'full'):
            labels = ('A', 'B') if detail is None else ('OLD', 'A', 'B')
            values = []
            for label in labels:
                record = next(row for row in benchmark['calls'] if row['case'] == case_id and row['candidate'] == label and row['operation'] == 'export' and row['detail'] == detail)
                values.append(raw_calls[(label, record['rpc_index'])]['value']['tool_result'])
            check('export/' + case_id + '/' + str(detail), all(value == values[0] for value in values))
    check('benchmark/fixed_B_selected', benchmark['selected_candidate'] == 'B' and all(row['all_five_B_windows_faster'] for row in medians))

    freeze = read(AREA / 'FROZEN.json')
    direct = {row['path']: row for row in freeze['direct_inputs']}
    check('freeze/363_direct_14_execution', len(direct) == 363 and freeze['execution_source_count'] == len(freeze['execution_sources']) == 14)
    for path, pin in direct.items():
        check('freeze/direct/' + path, pin_matches(pin, raw(path)))
    for pin in freeze['execution_sources']:
        check('freeze/explicit_execution_member/' + pin['path'], direct[pin['path']] == pin and pin_matches(pin, raw(pin['path'])))
    check('freeze/B_budget', freeze['selected_candidate'] == 'B' and freeze['selected_source_sha256'] == B_SOURCE
          and freeze['consumer_cap'] == 3 and freeze['replacement_consumers'] == 0 and freeze['completed_CLI_tool_cap'] == 4
          and freeze['task_seconds'] == 450 and freeze['process_seconds'] == 600)
    runner_source = raw(AREA / 'harness/run_slot.py')
    ast.parse(runner_source)
    check('freeze/actual_preexecution_direct_loop', b"for row in frozen['direct_inputs']" in runner_source and b"sha(row['path'])" in runner_source)
    inputs = read(AREA / 'INPUTS.json')
    old_namespace = AREA.with_name('m4_source_region_consumption_001')
    for name in ('PROMPT.txt', 'TOOL_SCHEMA.json'):
        check('input/unchanged/' + name, raw(AREA / 'inputs' / name) == raw(old_namespace / 'inputs' / name))
    for name in ('RUBRIC.json', 'CASE_ANSWERS.json', 'SCORE_METHOD.md'):
        check('scoring/unchanged/' + name, raw(AREA / 'scoring' / name) == raw(old_namespace / 'scoring' / name))
    prepared = {}
    for row in inputs['cases']:
        case_id = row['case_id']
        result = read(row['input_file'])
        brief = result['content'][0]['text'].encode()
        image = base64.b64decode(result['content'][1]['data'], validate=True)
        old_input = read(AREA / 'historical' / case_id / 'TOOL_RESULT.json')
        check('input/' + case_id + '/fixed_projection', sha(raw(row['input_file'])) == row['input_sha256']
              and brief == raw(AREA / 'inputs' / case_id / 'ORIGINAL_BRIEF.json')
              and len(brief) == row['brief_UTF8_bytes'] <= 10000 and row['projection_source_sha256'] == B_SOURCE
              and image == raw(AREA / 'inputs' / case_id / 'ORIGINAL_IMAGE.png') == raw(AREA / 'historical' / case_id / 'ORIGINAL_IMAGE.png')
              and result['content'][1:] == old_input['content'][1:] and sha(image) == row['PNG_sha256'])
        check('input/' + case_id + '/dimensions', image[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', image[16:24]) == (512, 512))
        prepared[case_id] = {'result': result, 'brief_bytes': len(brief), 'PNG_bytes': len(image)}

    sealed = read(AREA / 'ANSWERS_SEALED.json')
    answer_pins = {row['case_id']: row for row in sealed['answers']}
    sessions, thread_ids, usage = [], [], Counter()
    for case_id in ('S1', 'S2', 'S3'):
        folder = RUNTIME / 'slots' / case_id
        label = 'consumer/' + case_id
        start = read(folder / 'SLOT_STARTED.json')
        slot = read(folder / 'SLOT_RESULT.json')
        pub = read(folder / 'SLOT_PUBLICATION.json')
        consumer = read(folder / 'consumer/CONSUMER.json')
        timing = read(folder / 'consumer/FINAL_TIMING.json')
        proof = read(folder / 'ADAPTER_PROOF.json')
        ledger = read(folder / 'owner/TOOLS.json')
        final = raw(folder / 'consumer/PUBLIC_FINAL.txt')
        began = start['started_ns']
        deadline = began + 450_000_000_000
        lifecycle = began + 600_000_000_000
        check(label + '/original_deadlines', start['task_deadline_ns'] == slot['task_deadline_ns'] == pub['original_task_deadline_ns'] == deadline
              and start['lifecycle_deadline_ns'] == slot['lifecycle_deadline_ns'] == pub['original_lifecycle_deadline_ns'] == lifecycle
              and consumer['deadline_ns'] == consumer['episode_deadline_ns'] == timing['original_turn_deadline_ns'] == deadline
              and freeze['frozen_ns'] < began < consumer['started_ns'] < consumer['prompt_submitted_ns'] < consumer['final_received_ns']
              < consumer['turn_completed_ns'] < consumer['cleanup_end_ns'] < timing['consumer_record_closed_ns']
              < slot['closed_ns'] < pub['published_ns'] < deadline)
        check(label + '/original_source_proof', proof['execution_sources'] == freeze['execution_sources']
              and slot['freeze_sha256'] == sha(raw(AREA / 'FROZEN.json'))
              and sha(raw(proof['CLI_path'])) == proof['CLI_sha256']
              and sha(raw(proof['Python_path'])) == proof['Python_sha256'])
        check(label + '/result_hashes', pub['result_sha256'] == sha(raw(folder / 'SLOT_RESULT.json'))
              and slot['consumer_record_sha256'] == sha(raw(folder / 'consumer/CONSUMER.json'))
              and answer_pins[case_id]['publication_sha256'] == sha(raw(folder / 'SLOT_PUBLICATION.json')))
        check(label + '/same_original_answer', pin_matches(answer_pins[case_id], final) and final == raw(answer_pins[case_id]['copy_path']) == raw(folder / 'consumer/final.txt')
              and pub['published_ns'] < sealed['sealed_ns'])
        argv = consumer['argv']
        configs = dict(argv[index + 1].split('=', 1) for index, item in enumerate(argv[:-1]) if item == '-c')
        check(label + '/fresh_profile', '--ephemeral' in argv and '--ignore-user-config' in argv and '--ignore-rules' in argv
              and '--strict-config' in argv and not set(argv) & {'resume', 'fork', '--last', '--all'}
              and consumer['expected_thread_id'] is None and consumer['turn_index'] == 1
              and argv[argv.index('-m') + 1] == 'gpt-6.1-sol' and configs['model_reasoning_effort'] == '"medium"'
              and configs['service_tier'] == '"default"')
        events, private = public_events(raw(folder / 'consumer/stdout.raw.bin'))
        check(label + '/private_events0', len(private) == 0)
        turns = [event for event in events if event['type'] == 'turn.completed']
        threads = [event for event in events if event['type'] == 'thread.started']
        tools = [event for event in events if event['type'] == 'item.completed' and event.get('item', {}).get('type') == 'mcp_tool_call']
        messages = [event['item']['text'].encode() for event in events if event['type'] == 'item.completed' and event.get('item', {}).get('type') == 'agent_message']
        check(label + '/one_thread_one_turn', len(turns) == len(threads) == 1 and threads[0]['thread_id'] == consumer['thread_id'])
        check(label + '/actual_tools_usage_final', tools == [{key: value for key, value in event.items() if key != 'perf_ns'} for event in consumer['tool_calls']]
              and [event['usage'] for event in turns] == consumer['raw_usage_events'] and messages[-1] == final)
        original_archive = consumer['archive']
        zip_bytes = raw(folder / 'consumer.raw.zip')
        check(label + '/consumer_zip_pin', sha(zip_bytes) == original_archive['archive_sha256'])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zipped:
            check(label + '/consumer_zip_members', set(zipped.namelist()) == set(original_archive['source_files_sha256']))
            for name, digest in original_archive['source_files_sha256'].items():
                data = zipped.read(name)
                check(label + '/consumer_zip_same_original/' + name, sha(data) == digest and data == raw(folder / 'consumer' / name))
        check(label + '/completed_one_tool_one_PNG', slot['status'] == consumer['status'] == 'completed' and consumer['valid_completion'] is True
              and not slot['errors'] and not consumer['errors'] and not consumer['unexpected_tool_deviations']
              and len(tools) == ledger['attempts'] == ledger['admitted'] == 1
              and consumer['public_image_count'] == 1 and consumer['public_image_bytes'] == prepared[case_id]['PNG_bytes']
              and consumer['tool_accounting']['completed_empty_discoveries'] == consumer['tool_accounting']['completed_unexpected_tools'] == 0)
        request = read(folder / 'owner/tool_01/REQUEST.json')
        response = read(folder / 'owner/tool_01/RESPONSE.json')
        check(label + '/original_public_content', request['id'] == response['id'] and request['params']['name'] == 'read_observation'
              and request['params']['arguments'] == {} and response['result'] == prepared[case_id]['result']
              and tools[0]['item']['result']['content'] == prepared[case_id]['result']['content'])
        transport_profile = request['params']['_meta']['x-codex-turn-metadata']
        check(label + '/actual_transport_metadata', transport_profile['model'] == 'gpt-6.1-sol'
              and transport_profile['reasoning_effort'] == 'medium' and transport_profile['thread_id'] == consumer['thread_id'])
        bridge = consumer['bridge_cleanup']
        runtime_binding = read(folder / 'consumer/RUNTIME_BINDING.json')
        check(label + '/reader_creation_binding', runtime_binding['confirmed'] is True and runtime_binding['launcher_pid'] == consumer['consumer_pid']
              and runtime_binding['runtime_pid'] == bridge['instances'][0]['started']['pid']
              and runtime_binding['actual_executable_sha256'] == proof['Python_sha256'])
        exited = consumer['runtime_exit']
        cleanup = consumer['process_cleanup']
        check(label + '/reader_held_exit1', exited['confirmed'] is True and exited['exited'] is True and exited['exit_code'] == 1
              and exited['handle_closed'] is True and exited['original_deadline_ns'] == deadline and exited['closed_ns'] < deadline)
        check(label + '/CLI_closed0', consumer['exit_code'] == 0 and consumer['process_reaped'] is True and consumer['readers_stopped'] is True
              and cleanup['confirmed'] is True and cleanup['exit_code'] == 0 and cleanup['reaped'] is True
              and cleanup['process_handle_closed'] is True and all(cleanup['pipes_closed'].values()) and not cleanup['kill_requested'] and not cleanup['errors'])
        check(label + '/normal_EXIT_unknown', bridge['receipt_status'] == 'unknown' and bridge['confirmed'] is None
              and bridge['missing_exit_count'] == 1 and bridge['instances'][0]['exit'] is None)
        check(label + '/wall', slot['wall_ns'] == slot['closed_ns'] - began
              and consumer['wall_ns'] == consumer['cleanup_end_ns'] - consumer['started_ns']
              and consumer['prompt_to_final_ns'] == consumer['final_received_ns'] - consumer['prompt_submitted_ns'])
        usage.update(turns[0]['usage'])
        thread_ids.append(consumer['thread_id'])
        sessions.append({'case': case_id, 'started_ns': began, 'closed_ns': slot['closed_ns'], 'published_ns': pub['published_ns'],
            'full_slot_ns': slot['wall_ns'], 'through_publication_ns': pub['published_ns'] - began,
            'consumer_ns': consumer['wall_ns'], 'consumer_through_record_close_ns': timing['full_turn_wall_ns'],
            'prompt_to_final_ns': consumer['prompt_to_final_ns'],
            'CLI_pid': consumer['consumer_pid'], 'reader_pid': runtime_binding['runtime_pid'], 'CLI_exit': 0, 'reader_exit': 1,
            'normal_EXIT': bridge, 'tool_count': len(tools), 'PNG_bytes': prepared[case_id]['PNG_bytes'],
            'brief_bytes': prepared[case_id]['brief_bytes'], 'usage': turns[0]['usage'], 'model_thread': consumer['thread_id']})
    check('consumers/three_serial_distinct', len(set(thread_ids)) == 3 and all(left['published_ns'] < right['started_ns'] for left, right in zip(sessions, sessions[1:])))
    check('consumers/usage_totals', dict(usage) == {'input_tokens': 42661, 'cached_input_tokens': 9728, 'cache_write_input_tokens': 0,
          'output_tokens': 4213, 'reasoning_output_tokens': 0})
    check('consumers/bytes', sum(row['brief_bytes'] for row in sessions) == 29942 and sum(row['PNG_bytes'] for row in sessions) == 28510)

    decision = read(AREA / 'DECISION.json')
    prep_start = read(AREA / 'PREPARATION_STARTED.json')
    prep_end = read(AREA / 'PREPARATION_CLOSED.json')
    audit = read(AREA / 'FINAL_AUDIT.json')
    closeout = read(AREA / 'CLOSEOUT_STARTED.json')
    check('timing/preparation840', prep_end['started_ns'] == prep_start['started_ns']
          and prep_end['freeze_sha256'] == sha(raw(AREA / 'FROZEN.json'))
          and abs((prep_end['closed_ns'] - prep_start['started_ns']) / 1e9 - 840.674589) < 1e-9
          and prep_end['closed_ns'] < sessions[0]['started_ns'])
    full_slot_ns = sum(row['full_slot_ns'] for row in sessions)
    through_publication_ns = sum(row['through_publication_ns'] for row in sessions)
    check('timing/consumer127', abs(decision['cost']['full_slot_seconds_sum'] - full_slot_ns / 1e9) < 1e-9
          and abs(decision['cost']['full_slot_through_publication_seconds_sum'] - through_publication_ns / 1e9) < 1e-9)
    phases = []
    for phase in decision['cost']['preparation_and_nested_phases']:
        source = read(phase['source']['path'])
        check('timing/phase/' + phase['phase'], pin_matches(phase['source'], raw(phase['source']['path']))
              and phase['wall_seconds'] == (phase['closed_ns'] - phase['started_ns']) / 1e9
              and prep_start['started_ns'] <= phase['started_ns'] <= phase['closed_ns'] <= prep_end['closed_ns'])
        phases.append({key: phase[key] for key in ('phase', 'started_ns', 'closed_ns', 'wall_seconds')})
    check('timing/audit1698_closeout354', abs(audit['timing']['preparation_through_final_audit_seconds']
          - (audit['timing']['audit_completed_ns'] - prep_start['started_ns']) / 1e9) < 1e-9
          and abs(audit['timing']['closeout_envelope_seconds'] - (audit['timing']['audit_completed_ns'] - closeout['started_ns']) / 1e9) < 1e-9)
    author_scores = read(AREA / 'scoring/AUTHOR_SCORES.json')
    independent_scores = read(AREA / 'scoring/INDEPENDENT_SCORES.json')
    check('scoring/original_rules_retained', author_scores['rules_changed'] is False and author_scores['answers_sealed_sha256'] == sha(raw(AREA / 'ANSWERS_SEALED.json'))
          and author_scores['started_ns'] > sealed['sealed_ns'] > sessions[-1]['published_ns']
          and decision['accepted_cases'] == 0 and decision['case_denominator'] == 3)
    protocol = read(AREA / 'checks/BRIDGE_PREFLIGHT.json')
    protocol_processes = []
    for process in protocol['protocol_processes']:
        closure = read(Path(process['path']) / 'stdio/CLOSE.json')
        check('protocol/' + process['window'] + '/original_closure', closure == process['closure'])
        expected_expiry = process['window'] == 'original_expired_deadline_rejected'
        if expected_expiry:
            check('protocol/expired_deadline_expected_exit1', closure['exit_code'] == 1 and closure['confirmed'] is False
                  and closure['reader_stopped'] is True and closure['process_handle_closed'] is True
                  and all(closure['pipes_closed'].values()) and not closure['forced_kill'] and not closure['errors']
                  and process['response_count'] == 0 and process['error']['message'] == 'stdio_eof:None')
        else:
            closed_process('protocol/' + process['window'] + '/closed0', closure)
        for receipt in process['exit_receipts']:
            check('protocol/' + process['window'] + '/EXIT_identity', receipt['identity_matched'] is True
                  and receipt['receipt_status'] == 'observed' and receipt['STARTED']['pid'] == receipt['EXIT']['pid'] == closure['pid']
                  and receipt['EXIT']['normal_exit'] is (not expected_expiry))
        protocol_processes.append({'window': process['window'], 'closure': closure, 'expected_expiry_control': expected_expiry})
    check('protocol/five_pure_processes', len(protocol_processes) == 5 and all(value == 0 for value in protocol['zero_work'].values()))
    regressions = []
    for label in ('source', 'installed'):
        record = read(AREA / 'tests' / ('REGRESSIONS_' + label + '.json'))
        log_path = AREA / 'tests' / ('REGRESSIONS_' + label + '.log')
        check('regression/' + label + '/saved_report', record['tests'] == 9 and record['status'] == 'passed'
              and not record['errors'] and not record['failures'] and all(value == 0 for value in record['guarded_operations'].values())
              and sha(raw(log_path)) == record['log_sha256'])
        regressions.append(record)
    cleanup = read(AREA / 'CACHE_CLEANUP.json')
    check('cleanup/deleted0', cleanup['deleted'] == [] and cleanup['runtime_files_deleted'] == 0)
    costs = {'full_slots_ns': full_slot_ns, 'full_slots_through_publication_timestamps_ns': through_publication_ns,
        'consumer_loops_ns': sum(row['consumer_ns'] for row in sessions),
        'consumer_through_record_close_ns': sum(row['consumer_through_record_close_ns'] for row in sessions),
        'prompt_to_final_ns': sum(row['prompt_to_final_ns'] for row in sessions),
        'preparation_ns': prep_end['closed_ns'] - prep_start['started_ns'],
        'preparation_through_final_audit_ns': audit['timing']['audit_completed_ns'] - prep_start['started_ns'],
        'closeout_envelope_ns': audit['timing']['audit_completed_ns'] - closeout['started_ns'],
        'seal_audit_ns': audit['timing']['audit_completed_ns'] - audit['timing']['seal_started_ns'],
        'benchmark_formatter_intervals_ns': interval_ns, 'benchmark_timed_formatter_intervals_ns': timed_ns,
        'benchmark_through_closure_publication_ns': publication['closed_ns'] - publication['started_ns'],
        'author_scoring_report_generation_ns': author_scores['closed_ns'] - author_scores['started_ns'],
        'independent_content_review_wall_ns': None,
        'nested_preparation_phases': phases, 'fees': None, 'provider_requests': None, 'image_tokens': None,
        'manual_authoring_separate_work': None, 'scope': 'Nested windows retained separately. Final publication write completion, manifest/Git publication and administrator review are outside their recorded endpoints.'}
    return {'status': 'passed_checked_scope' if all(row['passed'] for row in CHECKS) else 'failed',
        'checks': len(CHECKS), 'failed_checks': [row for row in CHECKS if not row['passed']],
        'fixed_author': FINAL, 'namespace_Git_paths': len(paths), 'full_changed_paths': len(changed),
        'runtime_files': len(actual), 'runtime_bytes': original_total, 'all_runtime_byte_exact': True,
        'source_files_per_product': 143, 'B_source_sha256': B_SOURCE, 'source_diffs': identity_diffs,
        'freeze_direct_inputs': len(direct), 'declared_execution_sources': freeze['execution_sources'],
        'formatter_RPCs': len(raw_calls), 'formatter_iterations': total_iterations, 'formatter_timed_iterations': timed_iterations,
        'formatter_iteration_classes': dict(operations), 'window_medians': medians, 'profiles': profiles,
        'sessions': sessions, 'usage': dict(usage), 'costs': costs, 'saved_regressions': regressions,
        'protocol_processes': protocol_processes,
        'grading_scope': 'Original author/independent grading files remain sealed. This audit verifies identity/timing, leaving task-versus-G1 interpretation to root quality review.',
        'private_event_handling': 'Event type/item.type scanned lexically before public decoding. Private bodies skipped and represented only by hashes. Observed private event count is zero.',
        'new_live_Blender': 0, 'new_MCP': 0, 'new_raster': 0, 'new_PNG_NPZ_encoding': 0, 'new_model': 0, 'new_paid': 0,
        'initial_reader_failure': 'READER_ATTEMPT_001.json', 'input_pins': list(PINS.values())}


if __name__ == '__main__':
    HERE.mkdir(parents=True, exist_ok=True)
    try:
        result = main()
    except Exception:
        (HERE / 'CHECKER_ERROR_001.txt').write_text(traceback.format_exc(), encoding='utf8')
        raise
    (HERE / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: result[key] for key in ('status', 'checks', 'failed_checks', 'namespace_Git_paths', 'full_changed_paths', 'formatter_iteration_classes', 'window_medians', 'usage')}, ensure_ascii=False))
    sys.exit(0 if result['status'] == 'passed_checked_scope' else 1)
