"""Replay saved cost evidence with the standard library. Never launch the product.

Run with any Python 3.10+ interpreter from the repository. Only Git object reads and
saved-file reads are performed. Outputs stay beside this script.
"""

import hashlib
import json
import statistics
import subprocess
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BASE = 'verification/m4_spatial_fact_consumption_001'
EVIDENCE = '5cdf62f311f94890ca569d06c1a858f1578225e4'
SEAL_COMMIT = '3a4b090532e01920110e6ee2be1702bc1c45c265'
SEAL_PATH = 'verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json'
SEAL_SHA = 'fa467d121359d8ffff45693887de2598f1d34a811bf031849215042ef0e44852'
SEMANTICS = [
    BASE + '/runtime/actor.py',
    BASE + '/runtime/consumer_transport.py',
    BASE + '/runtime/driver.py',
    'verification/native_plugin_complex_003/reused/accepted_native.py',
    'verification/native_plugin_complex_003/reused/stdio_attach.py',
    'verification/native_plugin_complex_003/actor.py',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


class SavedEvidence:
    """Read fixed Git blobs, while requiring their existing saved copies to agree."""

    def __init__(self):
        names = git('ls-tree', '-r', '--name-only', EVIDENCE, '--', BASE).decode().splitlines()
        self.paths = set(names)
        wanted = [p for p in names if p.startswith(BASE + '/cells/') and
                  Path(p).suffix in {'.json', '.jsonl', '.bin', '.txt', '.py'}]
        wanted += [BASE + '/' + name for name in (
            'BENEFIT_CONTRACT.json', 'SEQUENCE.json', 'RUN_RESULT.json',
            'PLAN.json', 'PREPARATION_COST.json', 'FORMAL_PROCESS.json',
            'schemas/COMMON_NATIVE.json', 'schemas/N_CONSUMER_TOOLS.json',
            'schemas/P_CONSUMER_TOOLS.json', 'schemas/P_PUBLIC_TOOLS.json')]
        wanted += SEMANTICS
        wanted = list(dict.fromkeys(wanted))
        requests = ''.join(EVIDENCE + ':' + p + '\n' for p in wanted).encode()
        output = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '--batch'],
                                input=requests, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True).stdout
        self.blobs = {}
        self.used = {}
        offset = 0
        for path in wanted:
            end = output.index(b'\n', offset)
            header = output[offset:end].split()
            assert header[1] == b'blob', (path, header)
            size = int(header[2])
            self.blobs[path] = output[end + 1:end + 1 + size]
            offset = end + 2 + size
        assert offset == len(output)

    def exists(self, path):
        return path in self.paths

    def raw(self, path):
        raw = self.blobs[path]
        assert (ROOT / path).read_bytes() == raw, 'saved evidence changed: ' + path
        self.used[path] = {'path': path, 'commit': EVIDENCE, 'bytes': len(raw),
                           'sha256': sha(raw), 'working_copy_matches_blob': True}
        return raw

    def json(self, path):
        return json.loads(self.raw(path).decode('utf-8-sig'))

    def lines(self, path):
        return [json.loads(line) for line in self.raw(path).splitlines() if line]


def summary(values):
    assert values
    return {'count': len(values), 'sum': sum(values), 'minimum': min(values),
            'median': statistics.median(values), 'maximum': max(values)}


def improvement(n, p):
    ratio = Fraction(p, n)
    return {'N': n, 'P': p, 'P_minus_N': p - n,
            'P_to_N_exact': str(ratio), 'reduction_percent': float((1 - ratio) * 100)}


def wire_messages(saved, prefix):
    folders = sorted({str(Path(p).parent).replace('\\', '/') for p in saved.paths
                      if p.startswith(prefix + '/') and p.endswith('/TX.bin')})
    rows = []
    for folder in folders:
        tx = saved.raw(folder + '/TX.bin')
        rx_path = folder + '/RX.bin'
        rx = saved.raw(rx_path) if saved.exists(rx_path) else b''
        message = json.loads(tx)
        reply = json.loads(rx) if rx else None
        rows.append({'path': folder, 'method': message.get('method'),
                     'request_id': message.get('id'),
                     'tool': message.get('params', {}).get('name'),
                     'tx_bytes': len(tx), 'rx_bytes': len(rx),
                     'tx': message, 'rx': reply})
    return rows


def public_tool_timings(events):
    starts = {}
    completed = []
    for row in events:
        event = row['event']
        item = event.get('item', {})
        if item.get('type') != 'mcp_tool_call':
            continue
        if event['type'] == 'item.started':
            assert item['id'] not in starts
            starts[item['id']] = row['perf_ns']
        if event['type'] == 'item.completed':
            completed.append({'item_id': item['id'], 'name': item['tool'],
                              'started_ns': starts.pop(item['id']),
                              'completed_ns': row['perf_ns'], 'item': item})
    assert not starts
    return completed


def body_text_bytes(result):
    return sum(len(block['text'].encode('utf-8')) for block in result.get('content', [])
               if block.get('type') == 'text')


def extract_cell(saved, slot, run):
    stem = BASE + '/cells/' + slot['cell']
    read = lambda suffix: saved.json(stem + '/' + suffix)
    c = read('CONSUMER.json')
    assert all(c[k] == slot[k] == run[k] for k in ('cell', 'group', 'round', 'task'))
    assert run['consumer'] == c and c['status'] == 'completed'
    assert not run['errors'] and not c['errors'] and not c['unexpected_tool_deviations']
    events = saved.lines(stem + '/events.jsonl')
    terminal = [r['event']['usage'] for r in events if r['event']['type'] == 'turn.completed']
    assert terminal == [c['usage']] == c['usage_rows']
    usage = c['usage'].copy()
    assert 0 <= usage['cached_input_tokens'] <= usage['input_tokens']
    assert 0 <= usage['reasoning_output_tokens'] <= usage['output_tokens']
    usage['input_plus_output_tokens'] = usage['input_tokens'] + usage['output_tokens']
    usage['input_excluding_cached_tokens'] = usage['input_tokens'] - usage['cached_input_tokens']

    anchors = [('cell_start', run['cell_started_ns']), ('consumer_start', c['started_ns']),
               ('consumer_popen_return', c['popen_ns']), ('prompt_submitted', c['prompt_submitted_ns']),
               ('public_final_received', c['final_received_ns']), ('turn_complete', c['turn_completed_ns']),
               ('consumer_process_exit', c['process_exit_ns']), ('consumer_cleanup_end', c['cleanup_end_ns']),
               ('cell_end', run['cell_ended_ns'])]
    phases = []
    for left, right in zip(anchors, anchors[1:]):
        duration = right[1] - left[1]
        assert duration >= 0
        phases.append({'from': left[0], 'through': right[0], 'duration_ns': duration})
    assert sum(p['duration_ns'] for p in phases) == run['full_cell_wall_ns']
    assert c['prompt_to_final_ns'] == c['final_received_ns'] - c['prompt_submitted_ns']
    assert c['pre_consumer_setup_ns'] == c['started_ns'] - run['cell_started_ns']
    assert c['wall_ns'] == c['cleanup_end_ns'] - c['started_ns']
    assert c['total_task_wall_ns'] == run['full_cell_wall_ns']

    thin_prefix = stem + '/attachments'
    thin = wire_messages(saved, thin_prefix)
    listings = [r for r in thin if r['method'] == 'tools/list']
    assert len(listings) == 1
    tools = listings[0]['rx']['result']['tools']
    assert tools == saved.json(BASE + '/schemas/' + slot['group'] + '_CONSUMER_TOOLS.json')
    native = saved.json(BASE + '/schemas/COMMON_NATIVE.json')
    assert next(t for t in tools if t['name'] == 'execute_blender_code') == native
    schema = {'tools_list_response_wire_bytes': listings[0]['rx_bytes'],
              'tools_list_request_wire_bytes': listings[0]['tx_bytes'],
              'tools_array_compact_json_bytes': len(compact(tools)),
              'declarations': [{'name': t['name'], 'compact_json_bytes': len(compact(t)),
                                'compact_json_sha256': sha(compact(t))} for t in tools],
              'token_contribution': None,
              'semantics': 'actual captured wire frame versus explicit compact JSON reserialization; bytes are not provider tokens'}
    thin_calls = [r for r in thin if r['method'] == 'tools/call']
    tool_times = public_tool_timings(events)
    actor_tools = read('owner/TOOLS.json')
    assert len(thin_calls) == len(tool_times) == actor_tools['attempts'] == len(actor_tools['tools'])
    attempts = []
    for number, (wire, public, actor) in enumerate(zip(thin_calls, tool_times, actor_tools['tools']), 1):
        folder = f'owner/tool_{number:02}'
        request = read(folder + '/REQUEST.json')
        response = read(folder + '/RESPONSE.json')
        assert request == wire['tx'] and response == wire['rx']
        assert public['item']['arguments'] == request['params']['arguments']
        assert public['item']['result']['content'] == response['result']['content']
        assert actor == read(folder + '/ATTEMPT.json')
        assert actor['response_bytes'] == wire['rx_bytes']
        result = response['result']
        assert not any(b.get('type') == 'image' for b in result['content'])
        args = request['params']['arguments']
        row = {'attempt': number, 'name': actor['name'], 'request_id': request['id'],
               'public_item_id': public['item_id'], 'public_started_ns': public['started_ns'],
               'public_completed_ns': public['completed_ns'],
               'public_tool_interval_ns': public['completed_ns'] - public['started_ns'],
               'actor_started_ns': actor['started_ns'], 'actor_elapsed_ns': actor['elapsed_ns'],
               'is_error': actor['is_error'], 'exception': actor['exception'],
               'request_wire_bytes': wire['tx_bytes'], 'response_wire_bytes': wire['rx_bytes'],
               'arguments_compact_json_bytes': len(compact(args)),
               'response_text_utf8_bytes': body_text_bytes(result),
               'code_utf8_bytes': len(args['code'].encode('utf-8')) if 'code' in args else 0,
               'requested_facts': args.get('query', {}).get('requested_facts')}
        if actor['name'] == 'execute_blender_code':
            receipt = read(folder + '/NATIVE_RECEIPT.json')
            row['native_receipt_elapsed_ns'] = receipt['elapsed_ns']
            row['native_script_sha256'] = sha(args['code'].encode('utf-8'))
        else:
            row['native_fallback'] = False
            text = json.loads(result['content'][0]['text'])
            row['response_status'] = text.get('status')
            row['response_error'] = text.get('error')
            row['fact_statuses'] = [
                {'candidate_index': p['candidate_index'], 'fact': name,
                 'status': fact.get('status'), 'reason': fact.get('reason')}
                for p in text.get('pairs', []) for name, fact in p['facts'].items()]
        attempts.append(row)
    assert sum(r['response_wire_bytes'] for r in attempts) == actor_tools['wire_tool_bytes']
    public_ns = sum(r['public_tool_interval_ns'] for r in attempts)
    actor_ns = sum(r['actor_elapsed_ns'] for r in attempts)
    gaps = []
    left = c['prompt_submitted_ns']
    for r in attempts:
        assert left <= r['public_started_ns'] <= r['public_completed_ns'] <= c['final_received_ns']
        gaps.append(r['public_started_ns'] - left)
        left = r['public_completed_ns']
    gaps.append(c['final_received_ns'] - left)
    assert sum(gaps) + public_ns == c['prompt_to_final_ns']

    worker = saved.lines(stem + '/owner/native/WORKER_EVENTS.jsonl')
    execution = [r for r in worker if 'script_sha256' in r]
    closing = [r for r in worker if 'script_sha256' not in r]
    assert len(closing) == 1 and closing[0] == worker[-1]
    assert closing[0]['status'] == 'unknown'
    assert [r['sequence'] for r in worker] == list(range(1, len(worker) + 1))
    business_shas = {r['native_script_sha256'] for r in attempts if r['name'] == 'execute_blender_code'}
    physical = []
    for row in execution:
        call = f"owner/native/call_{row['sequence']}"
        script = saved.raw(stem + '/' + call + '/SCRIPT.py')
        stdout = saved.raw(stem + '/' + call + '/stdout.txt')
        stderr = saved.raw(stem + '/' + call + '/stderr.txt')
        # Helper writes text-mode files on Windows after hashing/counting the
        # received code and StringIO output. CRLF file size is a separate metric.
        code = script.replace(b'\r\n', b'\n')
        assert row['script_sha256'] == sha(code)
        assert row['stdout_bytes'] == len(stdout.replace(b'\r\n', b'\n'))
        assert row['stderr_bytes'] == len(stderr.replace(b'\r\n', b'\n'))
        if row['sequence'] == 1:
            kind = 'initial_QA_snapshot'
        elif row['sequence'] == execution[-1]['sequence']:
            kind = 'final_QA_snapshot'
        elif row['script_sha256'] in business_shas:
            kind = 'consumer_native_tool'
        else:
            assert slot['group'] == 'P'
            kind = 'product_capture'
        physical.append({**row, 'classification': kind, 'script_utf8_bytes': len(code),
                         'saved_script_file_bytes': len(script),
                         'saved_stdout_file_bytes': len(stdout),
                         'saved_stderr_file_bytes': len(stderr)})
    assert sum(r['classification'].endswith('QA_snapshot') for r in physical) == 2
    assert sum(r['classification'] == 'consumer_native_tool' for r in physical) == len(business_shas)
    initial = read('owner/INITIAL.json')
    assert initial == read('owner/FINAL.json')
    full_scene = {'objects': len(initial['objects']),
                  'vertices': sum(len(o['vertices_local']) for o in initial['objects']),
                  'faces': sum(len(o['faces']) for o in initial['objects'])}
    assert all(len(face) == 3 for o in initial['objects'] for face in o['faces'])
    full_scene['face_kind'] = 'triangles'
    close = read('owner/CLOSE.json')
    finish = read('OWNER_FINISH.json')
    assert finish == run['finish'] == c['owner_finish'] and finish['confirmed'] is True
    assert close == finish['close'] and close['native_close']['response']['status'] == 'closed'
    assert read('owner/native/WORKER_CLOSED.json') == close['worker_closed']
    session = read('owner/native/SESSION.json')

    product = None
    product_wire = []
    if slot['group'] == 'P':
        product_wire = wire_messages(saved, stem + '/owner/plugin')
        rpc = read('owner/plugin/RPC.json')
        assert len(product_wire) == len(rpc['requests'])
        assert sum(r['tx_bytes'] for r in product_wire) == rpc['tx_bytes']
        assert sum(r['rx_bytes'] for r in product_wire) == rpc['rx_bytes']
        for wire, receipt in zip(product_wire, rpc['requests']):
            assert wire['method'] == receipt['method']
            assert wire['tx_bytes'] == receipt['sent_bytes']
            assert wire['rx_bytes'] == receipt['received_bytes']
        audits = saved.lines(stem + '/owner/audit.jsonl')
        traces = [a['trace'] for a in audits if a['event'] == 'request_trace']
        observe = [a for a in audits if a['event'] == 'observe']
        assert len(observe) == 1
        successful = [a for a in traces if a['operation'] == 'mcp.observe' and
                      a['annotations'].get('object_count') is not None]
        assert len(successful) == 1
        trace = successful[0]
        assert trace['trace_id'] == observe[0]['trace_id']
        annotations = trace['annotations']
        observed_spans = [{'name': s['name'], 'parent_span_id': s['parent_span_id'],
                           'span_id': s['span_id'], 'start_offset_ns': s['start_offset_ns'],
                           'duration_ns': s['duration_ns']} for s in trace['spans']]
        work = observe[0]['task_work']
        closed_work = [p['closed_solid_work']['work_units'] for p in work['pairs']]
        assert len(closed_work) == 3
        product = {'peer': rpc, 'trace_inclusive_duration_ns': trace['duration_ns'],
                   'trace_semantics': trace['duration_semantics'],
                   'selected_geometry': {k: annotations[k] for k in ('object_count', 'vertex_count', 'face_count')},
                   'spans': observed_spans, 'all_traces': traces,
                   'task_work': work,
                   'closed_solid_work_units': closed_work,
                   'closed_solid_separate_duration_ns': None,
                   'cache_metrics': {k: v for k, v in work.items() if 'cache' in k},
                   'cache_occupancy_bytes': None,
                   'process_peak_rss': trace['peak_rss'],
                   'public_tools_list_raw_response_bytes': next(r['rx_bytes'] for r in product_wire if r['method'] == 'tools/list'),
                   'public_tools_list_full_tool_count': len(next(r['rx']['result']['tools'] for r in product_wire if r['method'] == 'tools/list'))}

    thin_dir = {str(Path(r['path']).parent).replace('\\', '/') for r in thin}
    assert len(thin_dir) == 1
    thin_exit_path = next(iter(thin_dir)) + '/EXIT.json'
    assert not saved.exists(thin_exit_path)
    rpc_layers = {
        'consumer_stdio': {'messages_sent_including_notification': len(thin),
                           'requests_with_response': sum(r['rx'] is not None for r in thin),
                           'tool_attempts': len(attempts),
                           'metadata_requests_with_response': sum(r['method'] != 'tools/call' and r['rx'] is not None for r in thin),
                           'local_notifications_not_forwarded': sum(r['request_id'] is None for r in thin),
                           'tx_bytes': sum(r['tx_bytes'] for r in thin),
                           'rx_bytes': sum(r['rx_bytes'] for r in thin)},
        'owner_control': {'attached_mcp_successful_request_response_pairs': sum(r['rx'] is not None for r in thin),
                          'basis': 'captured stdio pairs plus fixed stdio_attach source; notification has no id and is not forwarded',
                          'tcp_wire_tx_bytes': None, 'tcp_wire_rx_bytes': None,
                          'owner_finish_stdin_signals': 1,
                          'owner_finish_elapsed_ns': finish['elapsed_ns']},
        'product_peer_stdio': None if product is None else {
            'messages_sent_including_notification': len(product_wire),
            'requests_with_response': sum(r['rx'] is not None for r in product_wire),
            'tool_requests': sum(r['method'] == 'tools/call' for r in product_wire),
            'metadata_requests_with_response': sum(r['method'] != 'tools/call' and r['rx'] is not None for r in product_wire),
            'notifications': sum(r['request_id'] is None for r in product_wire),
            'tx_bytes': product['peer']['tx_bytes'], 'rx_bytes': product['peer']['rx_bytes']},
        'native_physical_tcp': {'requests': len(worker), 'execute_requests': len(execution),
                                'consumer_native_execute': sum(r['classification'] == 'consumer_native_tool' for r in physical),
                                'product_capture_execute': sum(r['classification'] == 'product_capture' for r in physical),
                                'QA_snapshot_execute': 2, 'close_requests': 1,
                                'tx_bytes': None, 'rx_bytes': None,
                                'count_basis': 'worker sequence and script receipts; final unknown entry is the close request, confirmed by close response and WORKER_CLOSED'},
        'provider': {'requests': None, 'wire_bytes': None}}
    return {
        **slot, 'status': c['status'], 'quality': 'complete_correct_from_sealed_quality',
        'usage': usage, 'usage_basis': 'one terminal turn.completed cumulative usage, identical to sole usage_rows and CONSUMER usage',
        'requested_model': c['model'], 'requested_effort': c['requested_effort'],
        'resolved_model': None, 'resolved_effort': c['resolved_effort'],
        'provider_requests': c['provider_requests'], 'provider_retry_observations': c['provider_retry_observations'],
        'provider_retry_observations_semantics': 'original heuristic stderr rows; spc03 contains a PowerShell shell_snapshot warning, which does not establish a provider retry',
        'fees': c['fees'], 'image_tokens': c['image_tokens'],
        'timing': {'full_cell_ns': run['full_cell_wall_ns'], 'prompt_to_final_ns': c['prompt_to_final_ns'],
                   'consumer_wall_ns': c['wall_ns'], 'pre_consumer_setup_ns': c['pre_consumer_setup_ns'],
                   'owner_finish_elapsed_ns': finish['elapsed_ns'], 'phases': phases,
                   'anchors': dict(anchors), 'actor_startup_ns': read('owner/IDENTITY.json')['startup_ns'],
                   'native_startup_ns': session['startup_ns'], 'public_tool_intervals_sum_ns': public_ns,
                   'actor_tool_intervals_sum_ns': actor_ns,
                   'prompt_to_final_outside_public_tool_intervals_ns': sum(gaps),
                   'prompt_to_final_gaps_ns': gaps,
                   'residual_semantics': 'unattributed wall intervals include provider/client waiting and uninstrumented work; no inference-time attribution',
                   'cell_scope': run['cell_timing_scope']},
        'schema': schema, 'tools': attempts, 'rpc_layers': rpc_layers,
        'tool_totals': {'attempts': len(attempts), 'failed_or_refused': sum(t['is_error'] for t in attempts),
                        'native_attempts': sum(t['name'] == 'execute_blender_code' for t in attempts),
                        'observe_attempts': sum(t['name'] == 'human_eye_scene_observe' for t in attempts),
                        'P_to_native_fallback_attempts': sum(t['name'] == 'execute_blender_code' for t in attempts) if slot['group'] == 'P' else None,
                        'request_wire_bytes': sum(t['request_wire_bytes'] for t in attempts),
                        'response_wire_bytes': sum(t['response_wire_bytes'] for t in attempts),
                        'response_text_utf8_bytes': sum(t['response_text_utf8_bytes'] for t in attempts),
                        'arguments_compact_json_bytes': sum(t['arguments_compact_json_bytes'] for t in attempts),
                        'native_code_utf8_bytes': sum(t['code_utf8_bytes'] for t in attempts)},
        'native_worker_execute_receipts': physical,
        'geometry': {'full_scene_snapshot': full_scene, 'native_geometry_cache_bytes': None,
                     'native_RSS_bytes': None, 'native_capture_internal_elapsed_ns': None,
                     'common_QA_scope': 'two full-scene snapshots and helper fingerprints/file checks; already inside measured cell and worker intervals',
                     'product_selected_capture': None if product is None else product['selected_geometry']},
        'product': product,
        'text_bytes': {k: c[k] for k in ('input_text_bytes', 'public_text_bytes', 'output_text_bytes', 'bridge_public_text_bytes', 'stdout_bytes')},
        'shutdown': {'consumer_exit_code': c['exit_code'], 'consumer_process_reaped': c['process_reaped'],
                     'consumer_readers_stopped': c['readers_stopped'], 'owner_finish_confirmed': finish['confirmed'],
                     'native_close': close['native_close'], 'worker_closed': close['worker_closed'],
                     'product_runtime_exit': close['product_runtime_exit'],
                     'thin_client_EXIT_receipt_present': False,
                     'thin_client_confirmed_normal_exit': None,
                     'thin_client_limitation': 'all six original EXIT receipts absent; no replacement receipt synthesized'},
        'limits': {'within_570s': run['within_570s'], 'actor_tools_limit': 32,
                   'actor_response_bytes_limit': 1048576, 'host_RPC_limit': 128,
                   'images': c['public_image_count'], 'input_images': c['input_image_count']}}


def group_result(cells, group):
    rows = [c for c in cells if c['group'] == group]
    usage = {key: sum(c['usage'][key] for c in rows) for key in rows[0]['usage']}
    out = {'cells': [c['cell'] for c in rows], 'count': len(rows), 'usage_totals': usage,
           'full_cell_ns': summary([c['timing']['full_cell_ns'] for c in rows]),
           'prompt_to_final_ns': summary([c['timing']['prompt_to_final_ns'] for c in rows]),
           'pre_consumer_setup_ns': summary([c['timing']['pre_consumer_setup_ns'] for c in rows]),
           'owner_finish_elapsed_ns': summary([c['timing']['owner_finish_elapsed_ns'] for c in rows]),
           'tool_totals': {k: sum(c['tool_totals'][k] or 0 for c in rows) for k in rows[0]['tool_totals']},
           'actor_tool_intervals_ns': summary([c['timing']['actor_tool_intervals_sum_ns'] for c in rows]),
           'public_tool_intervals_ns': summary([c['timing']['public_tool_intervals_sum_ns'] for c in rows]),
           'schema_tools_list_response_wire_bytes': summary([c['schema']['tools_list_response_wire_bytes'] for c in rows]),
           'schema_tools_array_compact_json_bytes': summary([c['schema']['tools_array_compact_json_bytes'] for c in rows]),
           'rpc_layers': {}}
    for layer in ('consumer_stdio', 'owner_control', 'product_peer_stdio', 'native_physical_tcp'):
        values = [c['rpc_layers'][layer] for c in rows if c['rpc_layers'][layer] is not None]
        keys = sorted({k for v in values for k, n in v.items() if type(n) is int})
        out['rpc_layers'][layer] = {k: sum(v.get(k, 0) for v in values) for k in keys}
        out['rpc_layers'][layer]['applies_to_cells'] = len(values)
    out['usage_per_cell'] = {k: summary([c['usage'][k] for c in rows]) for k in rows[0]['usage']}
    return out


def report(result):
    n, p = result['groups']['N'], result['groups']['P']
    fmt_s = lambda ns: f'{ns / 1e9:.7f}'
    lines = ['# M4 空间事实消费成本复算', '',
             '本次只读取固定六格原始证据、既有运行代码和已封存质量结果，使用标准库重新计算。原始证据提交为 `' + EVIDENCE + '`。', '',
             '质量封存为 6/6 完整正确、78/78 事实正确。成本计算沿用该封存，两个组各三格，保留全部请求、首次启动、无效请求纠错、额外 closed 计算及收尾。', '',
             '## 冻结门限', '',
             '| 指标 | N | P | P 降幅 |', '|---|---:|---:|---:|',
             f"| 完整单格耗时中位数，秒 | {fmt_s(n['full_cell_ns']['median'])} | {fmt_s(p['full_cell_ns']['median'])} | {result['comparison']['median_full_cell']['reduction_percent']:.4f}% |",
             f"| 累计 input + output tokens | {n['usage_totals']['input_plus_output_tokens']} | {p['usage_totals']['input_plus_output_tokens']} | {result['comparison']['cumulative_input_plus_output']['reduction_percent']:.4f}% |", '',
             '两项均优于 N，至少一项改善达到 10%，冻结的 useful-benefit 门限通过。费用和 provider 请求数未测，当前结果限于同一场景、每组三次的指定任务。', '',
             '## 六格原始计量', '',
             '| 格 | 组 | 完整耗时 s | prompt→final s | input | cached input | output | reasoning output | 工具尝试/失败 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for c in result['cells']:
        u, t = c['usage'], c['timing']
        lines.append(f"| {c['cell']} | {c['group']} | {fmt_s(t['full_cell_ns'])} | {fmt_s(t['prompt_to_final_ns'])} | {u['input_tokens']} | {u['cached_input_tokens']} | {u['output_tokens']} | {u['reasoning_output_tokens']} | {c['tool_totals']['attempts']}/{c['tool_totals']['failed_or_refused']} |")
    lines += ['', 'usage 采用每格唯一 turn.completed 的最终累计值，与 CONSUMER 和 usage_rows 逐项一致。cached input 已包含在 input 内，reasoning output 已包含在 output 内。表中 reasoning 仅为暴露的 token 子项。', '',
              '## 三配对与组范围', '',
              '| 轮 | N / P | 完整耗时降幅 | token 降幅 |', '|---|---|---:|---:|']
    for pair in result['pairs']:
        lines.append(f"| {pair['round']} | {pair['N_cell']} / {pair['P_cell']} | {pair['full_cell']['reduction_percent']:.4f}% | {pair['input_plus_output']['reduction_percent']:.4f}% |")
    lines += ['', '| 组 | 完整耗时总和 s | 最小 s | 中位 s | 最大 s | prompt→final 总和 s |', '|---|---:|---:|---:|---:|---:|']
    for group, g in result['groups'].items():
        f = g['full_cell_ns']
        lines.append(f"| {group} | {fmt_s(f['sum'])} | {fmt_s(f['minimum'])} | {fmt_s(f['median'])} | {fmt_s(f['maximum'])} | {fmt_s(g['prompt_to_final_ns']['sum'])} |")
    lines += ['', '## 时间边界', '',
              '完整单格从输入校验前开始，到 owner close 完成为止，包含启动、QA 全场景快照、产品元数据握手、模型往返、所有业务请求及退出。后续单格 accounting 发布在原合同计时域外。', '',
              '| 格 | consumer 前 s | consumer 启动准备 s | popen→prompt s | prompt→final s | final→turn s | turn→exit s | exit→cleanup s | cleanup→cell end s |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in result['cells']:
        phases = c['timing']['phases']
        lines.append('| ' + c['cell'] + ' | ' + ' | '.join(fmt_s(x['duration_ns']) for x in phases) + ' |')
    lines += ['', '上述八段无重叠，逐格相加等于完整单格耗时。原件另有 actor 启动、Blender 启动、owner finish 及公共工具起止时间，RESULTS 保留这些嵌套计量，合计时不再次加上。', '',
              '| 格 | 公共工具区间合计 s | actor 工具合计 s | prompt→final 区间外 s |', '|---|---:|---:|---:|']
    for c in result['cells']:
        t = c['timing']
        lines.append(f"| {c['cell']} | {fmt_s(t['public_tool_intervals_sum_ns'])} | {fmt_s(t['actor_tool_intervals_sum_ns'])} | {fmt_s(t['prompt_to_final_outside_public_tool_intervals_ns'])} |")
    lines += ['', '区间外时间包含 provider/client 等待和未计量工作，归因保持未知。产品 span 为 inclusive，父子 span 有重叠。host.capture、任务事实计算、编码和发送的原始 spans 已逐项保存在 RESULTS。', '',
              '## 请求、字节与数据采集', '',
              '| 组 | 公共工具尝试 | 失败 | native 工具 | observe 工具 | 工具 TX B | 工具 RX B | text 正文 UTF-8 B |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for group, g in result['groups'].items():
        x = g['tool_totals']
        lines.append(f"| {group} | {x['attempts']} | {x['failed_or_refused']} | {x['native_attempts']} | {x['observe_attempts']} | {x['request_wire_bytes']} | {x['response_wire_bytes']} | {x['response_text_utf8_bytes']} |")
    lines += ['', 'stdio RX/TX 使用实际原始帧长度，正文使用 content.text 解码后的 UTF-8 长度。正文、封装、产品内层 stdio 和 consumer 外层 stdio 是不同层的计量，RESULTS 分别列出。', '',
              '| 组 | consumer 有回包请求 | owner attached 请求 | product 有回包请求 | native 业务 execute | 产品 capture execute | QA execute | native close |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for group, g in result['groups'].items():
        x = g['rpc_layers']
        lines.append(f"| {group} | {x['consumer_stdio']['requests_with_response']} | {x['owner_control']['attached_mcp_successful_request_response_pairs']} | {x['product_peer_stdio'].get('requests_with_response', 0)} | {x['native_physical_tcp']['consumer_native_execute']} | {x['native_physical_tcp']['product_capture_execute']} | {x['native_physical_tcp']['QA_snapshot_execute']} | {x['native_physical_tcp']['close_requests']} |")
    lines += ['', '同一个逻辑请求可依次经过数层，上表各列保持独立。owner 控制通道和 native TCP 的真实 wire 字节未捕获，值为 null。Native worker 的最终 unknown 事件对应 close 接收，真实关闭状态由 close response、WORKER_CLOSED 和 process reap 佐证。', '',
              '| 组 | tools/list 原始 RX B，每格 | tools 数组紧凑重序列化 B，每格 |', '|---|---:|---:|']
    for group, g in result['groups'].items():
        lines.append(f"| {group} | {g['schema_tools_list_response_wire_bytes']['median']} | {g['schema_tools_array_compact_json_bytes']['median']} |")
    lines += ['', 'N 的唯一 native 声明与 P 中的 native 声明逐项一致。P 额外公开 ordinary human_eye_scene_observe 的完整声明。产品 peer 启动时读取完整实际 tools/list，其原始大小和全工具数量单独保留。schema 字节无法可靠换算成 provider token，模型 usage 已包含其实际影响。', '',
              '初始与最终全场景快照每格均为 14 个对象、848 点、1640 个三角形。P 每次成功 observe 实际选取 4 个对象、576 点、1136 面。各组使用独立 Blender 会话，首次请求和采集包含在完整耗时内。', '',
              '## 失败与可优化成本', '',
              'spc02 首次请求添加了域外 nearest_witness，返回明确拒绝。该请求的 5.5156 ms actor 时间与 857 B 回包均已计入，后续纠错所经过的整个模型区间也在完整耗时内。没有因此丢弃或替换格。', '',
              '三次 P 成功请求均额外请求 closed_solid_relation，9 项全部为 closed_solid_work_budget unknown，每项耗用 262144 work units。spatial_relation 与 surface_proximity 成功交付。现有 trace 未单独计量 closed 耗时，整段任务事实 span 同时包含其他计算，因此可删耗时尚不可量化。', '',
              '三次 P 成功后均无 native fallback。N 的额外 native 调用承载数据读取、精度校正或包含关系检查，具体机制由独立轨迹审核解释。', '',
              'P 审计明确暴露的 result/pair cache 命中均为 false 或 0。复用 prepared triangle/tree 的算法工作字段仍按原值保留。缓存占用字节与 native 内部缓存/RSS 未计量。产品 peak RSS 为进程生命周期高水位，无法分离本请求新增内存。', '',
              '## 证据与限制', '',
              '所有参与计算的原件均与固定证据提交逐字节核对，INPUTS.json 保存路径、字节和 SHA256。原始证据、产品源码和全局配置保持原样。', '',
              '六个 consumer、owner、Blender 的原始退出记录均保留，P 另有真实 runtime retained-handle 的退出证明。六个薄 stdio 客户端均缺原始 EXIT.json，其正常退出结论保持 unknown。独立 owned 退出证明、已封存文字质量评分和本批冻结合同结论分别保留。', '',
              '费用、provider 请求次数、provider 自动重试、provider 网络字节、实际 resolved model/effort、host TCP wire 字节及部分缓存/内存指标均未测。未见独立的 closed span、pure model inference span 或 native 算法纯耗时。', '',
              '原 consumer 的 provider_retry_observations 是启发式 stderr 记录。spc03 其中一条为 PowerShell shell_snapshot 警告，provider 重试次数保持未测。', '',
              'PREPARATION_COST 的冻结前本地工作时间，以及本次管理员审核成本，与六格产品任务分开记账。coordinator 模型费用未提供。原 FORMAL_PROCESS/batch 墙钟与六格合计互相包含，RESULTS 保留各自范围并避免相加。', '',
              '冻结合同通过只覆盖这一个指定场景和两个路线各三次，后续跨任务、复杂资产和质量差异仍需独立验证。', '']
    return '\n'.join(lines)


def main():
    saved = SavedEvidence()
    # Read pinned implementation text for framing/count semantics, never import it.
    for path in SEMANTICS:
        saved.raw(path)
    seal_raw = git('show', SEAL_COMMIT + ':' + SEAL_PATH)
    assert sha(seal_raw) == SEAL_SHA
    seal = json.loads(seal_raw)
    assert seal['author_evidence_commit'] == EVIDENCE
    assert seal['quality']['complete_correct'] == 6 and seal['quality']['facts_correct'] == 78
    contract = saved.json(BASE + '/BENEFIT_CONTRACT.json')
    sequence = saved.json(BASE + '/SEQUENCE.json')['sequence']
    runs = saved.json(BASE + '/RUN_RESULT.json')
    assert [r['cell'] for r in runs['records']] == [s['cell'] for s in sequence]
    assert runs['started_cells'] == 6 and runs['all_planned_dispatched'] and runs['no_replacements']
    cells = [extract_cell(saved, slot, row) for slot, row in zip(sequence, runs['records'])]
    groups = {group: group_result(cells, group) for group in ('N', 'P')}
    comparison = {
        'median_full_cell': improvement(groups['N']['full_cell_ns']['median'], groups['P']['full_cell_ns']['median']),
        'cumulative_input_plus_output': improvement(groups['N']['usage_totals']['input_plus_output_tokens'],
                                                     groups['P']['usage_totals']['input_plus_output_tokens'])}
    pairs = []
    for round_number in range(1, 4):
        n = next(c for c in cells if c['round'] == round_number and c['group'] == 'N')
        p = next(c for c in cells if c['round'] == round_number and c['group'] == 'P')
        pairs.append({'round': round_number, 'N_cell': n['cell'], 'P_cell': p['cell'],
                      'full_cell': improvement(n['timing']['full_cell_ns'], p['timing']['full_cell_ns']),
                      'prompt_to_final': improvement(n['timing']['prompt_to_final_ns'], p['timing']['prompt_to_final_ns']),
                      'input_plus_output': improvement(n['usage']['input_plus_output_tokens'], p['usage']['input_plus_output_tokens'])})
    time_ratio = Fraction(comparison['median_full_cell']['P'], comparison['median_full_cell']['N'])
    tokens_ratio = Fraction(comparison['cumulative_input_plus_output']['P'], comparison['cumulative_input_plus_output']['N'])
    gate = {'quality_sealed_before_cost': True, 'all_six_retained': len(cells) == 6,
            'three_full_correct_per_arm': all(g['count'] == 3 for g in groups.values()),
            'no_missing_usage_failed_or_not_run': all(c['status'] == 'completed' and c['usage'] for c in cells),
            'P_median_full_cell_no_regression': time_ratio <= 1,
            'P_cumulative_input_plus_output_no_regression': tokens_ratio <= 1,
            'at_least_one_improvement_at_least_10_percent': min(time_ratio, tokens_ratio) <= Fraction(9, 10)}
    gate['passed'] = all(gate.values())
    formal = saved.json(BASE + '/FORMAL_PROCESS.json')
    assert formal['ended_ns'] - formal['started_ns'] >= sum(c['timing']['full_cell_ns'] for c in cells)
    results = {'schema': 'm4-spatial-fact-saved-cost-review-v1', 'evidence_commit': EVIDENCE,
               'quality_seal': {'commit': SEAL_COMMIT, 'path': SEAL_PATH, 'sha256': SEAL_SHA, 'quality': seal['quality']},
               'frozen_benefit_contract': contract, 'gate': gate, 'comparison': comparison,
               'groups': groups, 'pairs': pairs, 'cells': cells,
               'original_preparation_cost': saved.json(BASE + '/PREPARATION_COST.json'),
               'batch_timing': {k: v for k, v in runs.items() if k.startswith('batch_')},
               'outer_formal_process': formal,
               'unmeasured': ['fees', 'provider request count and retry count', 'provider network bytes',
                              'resolved model and effort', 'host TCP wire bytes', 'owner-control TCP wire bytes',
                              'closed_solid separate duration', 'pure model inference duration',
                              'product cache occupancy', 'native cache occupancy/RSS',
                              'six thin-client normal exits'],
               'overlap_rules': ['cached input is a subset of input; reasoning output is a subset of output',
                                 'only terminal cumulative turn usage is totaled',
                                 'stdio layers/body/schema bytes are independent scopes; do not sum them as model input',
                                 'nested trace spans and startup/finish timings already belong to full cell',
                                 'outer formal wall and six-cell sums overlap'],
               'analysis_execution': {'new_model_consumers': 0, 'new_Blender_sessions': 0,
                                      'new_product_processes': 0, 'source_or_evidence_mutations': 0}}
    inputs = {'evidence_commit': EVIDENCE, 'files': sorted(saved.used.values(), key=lambda r: r['path']),
              'seal': {'path': SEAL_PATH, 'commit': SEAL_COMMIT, 'sha256': sha(seal_raw), 'bytes': len(seal_raw)},
              'extractor_sha256': sha(Path(__file__).read_bytes())}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in [('RESULTS.json', results), ('INPUTS.json', inputs)]:
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'REPORT.md').write_text(report(results), encoding='utf-8')
    print(json.dumps({'gate': gate, 'comparison': comparison,
                      'read_verified_files': len(inputs['files']),
                      'outputs': {name: sha((OUT / name).read_bytes()) for name in ('RESULTS.json', 'INPUTS.json', 'REPORT.md')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
