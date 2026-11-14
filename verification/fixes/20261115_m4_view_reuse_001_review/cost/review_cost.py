"""Independent saved-record arithmetic. Does not import any product or author harness."""
import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import zipfile

HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
SRC = AUTHOR / 'verification/m4_view_reuse_001'
RUN = Path('D:/he_view_reuse_001/run/benchmark_01')
inputs = {}
checks = []


def raw(path):
    path = Path(path)
    value = path.read_bytes()
    inputs[str(path)] = {'path': str(path), 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    return value


def read(path):
    return json.loads(raw(path))


def check(name, value):
    checks.append({'name': name, 'pass': bool(value)})


def npz_payload(path):
    result = {}
    raw(path)
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            with archive.open(member) as stream:
                magic = stream.read(8)
                assert magic[:6] == b'\x93NUMPY'
                size = 2 if magic[6] == 1 else 4
                header_length = int.from_bytes(stream.read(size), 'little')
                header = ast.literal_eval(stream.read(header_length).decode('latin1'))
                payload = archive.getinfo(member).file_size - 8 - size - header_length
                result[member[:-4]] = {'shape': header['shape'], 'descr': header['descr'], 'nbytes': payload}
    return result


plan = read(SRC / 'PLAN.json')
measurement = read(RUN / 'MEASUREMENT_STARTED.json')
order = [(f'b{block:02}_{variant}', variant) for block, variants in enumerate(plan['cost']['order'], 1)
         for variant in variants]
check('fixed_five_alternating_pairs', plan['cost']['order'] == [['old', 'new'], ['new', 'old'], ['old', 'new'], ['new', 'old'], ['old', 'new']])
check('measurement_registered_order', measurement['fixed_blocks'] == plan['cost']['order'] and measurement['outer_retries'] == 0)
check('only_ten_arm_folders', {p.name for p in RUN.iterdir() if p.is_dir()} == {name for name, _ in order})
samples = {}
previous_end = measurement['started_ns']
pids = []
paths = []
total_rasters = 0
for name, variant in order:
    folder = RUN / name
    worker = read(folder / 'w/WORKER_RESULT.json')
    process = read(folder / 'PROCESS_RESULT.json')
    config = read(folder / 'CONFIG.json')
    pids.append(worker['process_id'])
    paths.append(str(config.get('output', config.get('output_root', folder))))
    check(name + '_successful_and_no_errors', worker['passed'] and process['passed'] and not worker['errors']
          and not worker['close_errors'] and not process['errors'])
    check(name + '_held_cleanup', process['process_cleanup']['confirmed'] and process['process_cleanup']['reaped']
          and process['process_cleanup']['exit_code'] == 0 and not process['process_cleanup']['kill_requested']
          and process['process_cleanup']['process_handle_closed'])
    check(name + '_clock_containment', previous_end <= process['started_ns'] <= worker['started_ns'] <
          worker['closed_ns'] <= process['process_and_streams_closed_ns'])
    check(name + '_parent_clock_difference', process['elapsed_ns'] == process['process_and_streams_closed_ns'] - process['started_ns'])
    check(name + '_worker_clock_difference', worker['elapsed_ns'] == worker['closed_ns'] - worker['started_ns'])
    previous_end = process['process_and_streams_closed_ns']
    check(name + '_four_requests', len(worker['requests']) == 4)
    check(name + '_no_models', worker['new_model_CLI_Blender_calls'] == 0)
    observation = read(folder / 'o/OBSERVATIONS.json')
    intents = [read(p) for p in sorted((folder / 'ledger').glob('attempt_*/INTENT.json'))]
    expected_count = 6 if variant == 'old' else 3
    check(name + '_actual_intents_and_completed', len(intents) == len(observation['render_attempts']) == expected_count
          and all(r['status'] == 'completed' for r in observation['render_attempts']))
    check(name + '_intent_PID_and_owner', all(r['process_id'] == worker['process_id']
          and Path(r['owner_output']) == folder / 'o' for r in intents))
    check(name + '_scene_count', sum(r['view_name'] == 'SCENE' for r in intents) == (4 if variant == 'old' else 1))
    check(name + '_budgets', config['max_render_attempts'] == config['phase_render_cap'] == 6
          and config['max_tool_calls'] == 12 and worker['closed_ns'] < config['worker_deadline_ns'])
    request_rows = []
    image_hashes = []
    png_delivered = 0
    wire_bytes = 0
    req_started = worker['started_ns']
    for i, request in enumerate(worker['requests'], 1):
        request_folder = folder / f'w/request_{i:02}'
        receipt = read(request_folder / 'CHECKPOINT.json')
        tx = read(request_folder / 'TCP_TX.bin')
        response_raw = raw(request_folder / 'TCP_RX.bin')
        response = json.loads(response_raw)
        result = response['result']['result']
        check(name + f'_request_{i}_record', receipt == request and not request['is_error']
              and request['local_socket_confirmed'] and request['actual_local_socket_bytes'] == len(response_raw)
              and request['response_sha256'] == hashlib.sha256(response_raw).hexdigest())
        check(name + f'_request_{i}_clock', req_started <= request['started_ns'] < request['closed_ns'] <= worker['closed_ns']
              and request['elapsed_ns'] == request['closed_ns'] - request['started_ns'])
        req_started = request['closed_ns']
        expected = plan['cost']['workflow'][i-1]
        params = tx['args']['message']['params']
        check(name + f'_request_{i}_workflow', params['name'] == expected['tool'] and params['arguments'] == expected['arguments'])
        wire_bytes += len(response_raw)
        images = [part for part in result['content'] if part['type'] == 'image']
        check(name + f'_request_{i}_image_count', len(images) == (3 if i == 1 else 1))
        for part in images:
            png = base64.b64decode(part['data'], validate=True)
            png_delivered += len(png)
            image_hashes.append(hashlib.sha256(png).hexdigest())
        mem = request['snapshot']['memory']
        check(name + f'_request_{i}_memory_sum', sum(a['nbytes'] for a in mem['arrays']) == mem['unique_array_payload_bytes']
              and len(mem['arrays']) == mem['unique_array_objects'])
        file_sizes = {}
        payloads = {}
        for row in mem['files']:
            path = Path(row['path'])
            file_sizes.setdefault(path.suffix, 0)
            file_sizes[path.suffix] += len(raw(path))
            check(name + f'_request_{i}_file_' + path.name, len(raw(path)) == row['bytes'])
            if path.suffix == '.npz':
                payloads[str(path)] = npz_payload(path)
        metrics = request['snapshot']['owner_metrics']
        expected_rasters = 3 + (i - 1 if variant == 'old' else 0)
        check(name + f'_request_{i}_rasters', metrics['render_attempts'] == expected_rasters
              and metrics['raster_completed'] == expected_rasters and metrics['frames_completed'] == expected_rasters)
        check(name + f'_request_{i}_file_counts', metrics['NPZ_bytes'] == file_sizes['.npz']
              and metrics['PNG_bytes'] == file_sizes['.png'])
        check(name + f'_request_{i}_generated_payload', metrics['array_payload_bytes'] == sum(
              a['nbytes'] for arrays in payloads.values() for a in arrays.values()))
        request_rows.append({'request': i, 'elapsed_ns': request['elapsed_ns'],
          'cumulative_ns': request['closed_ns'] - worker['started_ns'], 'raster': metrics['render_attempts'],
          'visible_arrays_bytes': mem['unique_array_payload_bytes'], 'raw_array_bytes': mem['raw_buffer_unique_bytes'],
          'file_bytes': file_sizes, 'generated_payload': metrics['array_payload_bytes'],
          'image_blocks': len(images), 'reply_bytes': len(response_raw)})
    for label, index in [('first', 0), ('first_plus_one_repeat', 1), ('first_plus_three_repeats', 3)]:
        cp = worker['checkpoints'][label]
        check(name + '_' + label, cp['started_ns'] == worker['started_ns'] and
              cp['closed_ns'] == worker['requests'][index]['closed_ns'] and cp['elapsed_ns'] == request_rows[index]['cumulative_ns'])
    total_rasters += request_rows[-1]['raster']
    samples[name] = {'variant': variant, 'pid': worker['process_id'], 'requests': request_rows,
        'parent_ns': process['elapsed_ns'], 'images': len(image_hashes), 'image_sha_sequence': image_hashes,
        'PNG_delivered_bytes': png_delivered, 'outer_reply_bytes': wire_bytes,
        'worker_ns': worker['elapsed_ns']}

check('ten_distinct_processes', len(set(pids)) == 10)
check('ten_separate_outputs', len(set(paths)) == 10)
check('forty_five_rasters', total_rasters == 45)
pairs = []
for i in range(1, 6):
    old, new = samples[f'b{i:02}_old'], samples[f'b{i:02}_new']
    check(f'pair_{i}_same_delivered_images', old['image_sha_sequence'] == new['image_sha_sequence'])
    points = []
    for index in range(4):
        a, b = old['requests'][index]['cumulative_ns'], new['requests'][index]['cumulative_ns']
        points.append({'repeats': index, 'old_ns': a, 'new_ns': b, 'new_minus_old_ns': b-a, 'new_over_old': b/a})
    pairs.append({'pair': i, 'points': points, 'first_profitable_repeat': next((p['repeats'] for p in points if p['new_ns'] <= p['old_ns']), None)})

summary = {'first_paired_delta_ms_median': statistics.median(p['points'][0]['new_minus_old_ns'] for p in pairs) / 1e6,
  'first_new_slower_pairs': sum(p['points'][0]['new_minus_old_ns'] > 0 for p in pairs),
  'first_group_median_difference_ms': (statistics.median(s['requests'][0]['cumulative_ns'] for s in samples.values() if s['variant']=='new') -
    statistics.median(s['requests'][0]['cumulative_ns'] for s in samples.values() if s['variant']=='old')) / 1e6,
  'one_repeat_paired_reduction': 1-statistics.median(p['points'][1]['new_over_old'] for p in pairs),
  'three_repeat_paired_reduction': 1-statistics.median(p['points'][3]['new_over_old'] for p in pairs),
  'one_repeat_new_faster_pairs': sum(p['points'][1]['new_ns'] < p['points'][1]['old_ns'] for p in pairs),
  'three_repeat_new_faster_pairs': sum(p['points'][3]['new_ns'] < p['points'][3]['old_ns'] for p in pairs),
  'break_even_observed': [p['first_profitable_repeat'] for p in pairs],
  'groups': {}}
for variant in ['old','new']:
    group = [s for s in samples.values() if s['variant']==variant]
    summary['groups'][variant] = {'first_total_s': sum(s['requests'][0]['cumulative_ns'] for s in group)/1e9,
      'one_repeat_total_s': sum(s['requests'][1]['cumulative_ns'] for s in group)/1e9,
      'three_repeat_total_s': sum(s['requests'][3]['cumulative_ns'] for s in group)/1e9,
      'parent_total_s': sum(s['parent_ns'] for s in group)/1e9,
      'repeat_service_ms_median': statistics.median(r['elapsed_ns'] for s in group for r in s['requests'][1:])/1e6,
      'first_arrays_each': sorted(set(s['requests'][0]['visible_arrays_bytes'] for s in group)),
      'last_arrays_each': sorted(set(s['requests'][-1]['visible_arrays_bytes'] for s in group)),
      'outer_reply_bytes_each': sorted(set(s['outer_reply_bytes'] for s in group)),
      'delivered_PNG_bytes_each': sorted(set(s['PNG_delivered_bytes'] for s in group)),
      'image_blocks_each': sorted(set(s['images'] for s in group))}

for name in ['case_worker.py', 'run_acceptance.py', 'native_tools.py', 'bridge.py', 'TEST_AND_COST_PLAN.md']:
    raw(SRC / name)
for name in ['active_observation_host.py','active_observation_images.py','live_service.py','read_context.py']:
    raw(AUTHOR / 'human_eye_plugin' / name)
result = {'method': 'Independent stdlib-only saved checkpoint/parent/socket/NPZ-header arithmetic; no product imports',
  'new_product_model_Blender_raster_calls': 0, 'fixed_commit': 'a9dd9490d1817630e090975362591ce232d881ae',
  'checks': len(checks), 'failed_checks': [c for c in checks if not c['pass']], 'summary': summary, 'pairs': pairs,
  'samples': samples, 'total_benchmark_rasters': total_rasters, 'all_checks': checks}
HERE.mkdir(parents=True, exist_ok=True)
(HERE / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(HERE / 'INPUT_HASHES.json').write_text(json.dumps(list(inputs.values()), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'checks':len(checks),'failed_checks':result['failed_checks'],'summary':summary},ensure_ascii=False))
if result['failed_checks']:
    raise SystemExit(1)
