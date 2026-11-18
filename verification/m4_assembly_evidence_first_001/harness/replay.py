"""Exercise the installed stdio MCP, host protocol and task formatter offline."""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import CASES, DETAILS, PREFIX, PRIOR_NS, ROOT, compact, fixture, require, save, sha


PREVIOUS_HARNESS = PRIOR_NS / 'harness'
STDIO_CLIENT = ROOT / 'verification/m4_source_region_display_001/harness/reused/stdio_checks.py'
TOOL = 'human_eye_scene_observe'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jsonl(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def result_folder(root, index):
    return root if index == 0 else root / f'attempt_{index + 1:03d}'


def read_host_rpc(connection):
    raw = bytearray()
    while chunk := connection.recv(65536):
        raw.extend(chunk)
        require(len(raw) <= 1024 * 1024, 'mock host request exceeds bound')
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        require(set(request) == {'type', 'params'} and request['type'] == 'execute_code', 'unexpected host transport')
        header = next(line for line in request['params']['code'].splitlines() if line.startswith('_request = '))
        expression = ast.parse(header).body[0].value
        return bytes(raw), json.loads(ast.literal_eval(expression.args[0]))
    raise ValueError('incomplete mock host request')


def receive(listener, output, selectors, packets, receipts, stopped):
    try:
        for index, packet in enumerate(packets):
            while True:
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    if stopped.is_set():
                        return
            folder = result_folder(output, index)
            started = time.perf_counter_ns()
            with connection:
                connection.settimeout(10)
                raw, request = read_host_rpc(connection)
                require(request['command'] == 'capture_task' and request['params'] == {'selectors': selectors},
                        'installed product did not make exact selected task capture')
                envelope = {'protocol_version': '1.0', 'id': request['id'], 'result': packet}
                wire = compact({'status': 'success', 'result': {'executed': True,
                    'result': PREFIX + compact(envelope).decode('utf8') + '\n'}})
                connection.sendall(wire)
                replied = time.perf_counter_ns()
            (folder / 'HOST_REQUEST.bin').write_bytes(raw)
            (folder / 'HOST_RESPONSE.bin').write_bytes(wire)
            receipts.append({'method': request['command'], 'selectors': selectors,
                'TX_bytes': len(raw), 'RX_bytes': len(wire), 'RX_sha256': sha(wire),
                'accept_to_reply_ns': replied - started})
    except Exception as error:
        receipts.append({'host_error': str(error), 'traceback': traceback.format_exc()})


def arguments(selectors, detail):
    params = {'query': {'mode': 'task', 'target': selectors[0], 'candidates': selectors[1:],
              'requested_facts': ['closed_solid_relation', 'surface_proximity']}, 'include_image': False}
    if detail != 'default':
        params['response_detail'] = detail
    return params


def run(binding_path, output, case, detail, repeat):
    output.mkdir(parents=True)
    binding = json.loads(binding_path.read_bytes())
    prepared = []
    for index in range(2 if case == 'stale_capture' else repeat):
        begin = time.perf_counter_ns()
        packet, capture, provenance = fixture(case, index)
        prepared.append((packet, capture, provenance, time.perf_counter_ns() - begin))
        folder = result_folder(output, index)
        if index:
            folder.mkdir()
        save(folder / 'CAPTURE.json', capture)
        save(folder / 'HOST_PACKET.json', packet)
        save(folder / 'PROVENANCE.json', provenance)
    selectors = prepared[0][1]['task_selection']['selectors']
    budget_class = load('_assembly_replay_budget', PREVIOUS_HARNESS / 'budget.py').Budget
    transport = load('_assembly_replay_stdio', STDIO_CLIENT)
    budget = budget_class(output / 'budget')
    record = {'case': case, 'detail': detail, 'passed': False, 'source_sha256': binding['source_sha256'],
        'binding_sha256': sha(binding_path.read_bytes()), 'python': sys.executable,
        'capture_count': 0, 'attempts': [], 'Blender_starts': 0, 'model_starts': 0, 'API_calls': 0}
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = thread = None
    stopped = threading.Event()
    host_receipts = []
    try:
        listener.bind(('127.0.0.1', 0))
        listener.listen(2)
        listener.settimeout(.25)
        thread = threading.Thread(target=receive, daemon=True, args=(listener, output, selectors,
                                  [row[0] for row in prepared], host_receipts, stopped))
        thread.start()
        config = output / 'PRODUCT_CONFIG.json'
        save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                      'project_root': binding['install_root'], 'state_file': str(output / 'product_state.json'),
                      'audit_file': str(output / 'product_audit.jsonl'),
                      'expected_identity': {'source_sha256': binding['source_sha256']}, 'request_budget_s': 20,
                      'blender': {'host': '127.0.0.1', 'port': listener.getsockname()[1], 'timeout_s': 20}})
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(PREVIOUS_HARNESS / 'mcp_entry.py'),
                   '--binding', str(binding_path), '--config', str(config), '--ledger', str(budget.root),
                   '--evidence', str(output / 'mcp_io'), '--phase', 'qualification', '--label', 'P1',
                   '--archive', str(output / 'product_full')]
        client = transport.StdioClient(command, output, output / 'mcp', time.perf_counter_ns() + 60_000_000_000)
        identity = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'assembly-evidence-replay', 'version': '1'}}})['result']['_meta']['human_eye']
        require(identity['source_sha256'] == binding['source_sha256']
                and identity['source_kind'] == 'installed_distribution', 'installed identity mismatch')
        record['identity'] = identity
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'})
        schema = compact(next(row for row in listing['result']['tools'] if row['name'] == TOOL))
        (output / 'TOOL_SCHEMA.json').write_bytes(schema)
        record['tool_schema_UTF8_bytes'] = len(schema)
        record['tool_schema_sha256'] = sha(schema)
        for index, (_, capture, _, preparation_ns) in enumerate(prepared):
            folder = result_folder(output, index)
            ident = f'observe-{index + 1:03d}'
            request = {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                       'params': {'name': TOOL, 'arguments': arguments(selectors, detail)}}
            save(folder / 'REQUEST.json', request)
            reply = client.call(request)
            save(folder / 'RESPONSE.json', reply)
            public = reply.get('result', {})
            content = public.get('content', [])
            require([block['type'] for block in content] == ['text'], 'replay expected one text block and zero images')
            body = content[0]['text'].encode('utf8')
            (folder / 'PUBLIC.json').write_bytes(body)
            require(bool(public['isError']) == (case == 'wrong_scope'), 'unexpected product response error flag')
            record['attempts'].append({'id': ident, 'public_UTF8_bytes': len(body), 'public_sha256': sha(body),
                'MCP_wire_receipt': client.records[-1], 'capture_fixture_preparation_ns': preparation_ns,
                'capture_objects': len(capture['meshes']),
                'capture_vertices': sum(len(row['vertices']) for row in capture['meshes']),
                'capture_triangles': sum(len(row['faces']) for row in capture['meshes']),
                'is_error': public['isError']})
        thread.join(timeout=2)
        require(not thread.is_alive() and len(host_receipts) == len(prepared)
                and all('method' in row for row in host_receipts), 'mock host receipt absent or failed')
        # The original server flushes the successful reply before it closes
        # request tracing. Its graceful exit drains that final audit write.
        require(client.finish()['confirmed'], 'installed MCP did not close cleanly')
        spans = {row['id']: row for row in jsonl(output / 'mcp_io/MCP_IO.jsonl') if row.get('id')}
        audit = jsonl(output / 'product_audit.jsonl')
        observed = {row['request_id']: row for row in audit if row.get('event') == 'observe'}
        traces = {row['trace']['annotations']['mcp_request_id']: row['trace'] for row in audit
                  if row.get('event') == 'request_trace'}
        for index, attempt in enumerate(record['attempts']):
            attempt['host'] = host_receipts[index]
            attempt['request_to_flush_with_archive_ns'] = spans[attempt['id']]['request_to_reply_ns']
            attempt['product_trace'] = traces.get(attempt['id'])
            product_request = attempt['product_trace']['request_id'] if attempt['product_trace'] else None
            attempt['task_work'] = observed.get(product_request, {}).get('task_work')
            attempt['raster_actual'] = spans[attempt['id']]['raster_actual']
        record['capture_count'] = len(host_receipts)
        record['budget_counts'] = budget.snapshot()['counts']
        require(record['budget_counts']['all_raster_upper'] == 0
                and all(row['raster_actual'] == 0 for row in record['attempts']), 'nonzero raster budget')
        require(set(traces) == {row['id'] for row in record['attempts']}
                and (case == 'wrong_scope' or len(observed) == len(prepared)), 'task audit or trace missing')
        record['passed'] = True
    except Exception as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        stopped.set()
        if client is not None:
            record['MCP_close'] = client.finish()
            record['passed'] &= record['MCP_close']['confirmed']
        if thread is not None:
            thread.join(timeout=2)
            record['passed'] &= not thread.is_alive()
        listener.close()
        record['host_receipts'] = host_receipts
        save(output / 'RUN.json', record)
    print(f"{case}/{detail} passed={record['passed']} bytes={[row['public_UTF8_bytes'] for row in record['attempts']]}",
          flush=True)
    return record['passed']


def normalize(binding_path, output):
    """Materialize canonical inputs after timing; the live producer hash must agree."""
    binding = json.loads(binding_path.read_bytes())
    sys.path.insert(0, binding['dependency_root'])
    helper = load('_assembly_replay_verified', PREVIOUS_HARNESS / 'reused/verified_bootstrap.py')
    guard = helper.bootstrap(binding)
    from human_eye_plugin.auto_router import _validated_scene
    for evidence in sorted(output.rglob('RUN.json')):
        record = json.loads(evidence.read_bytes())
        if not record['passed'] or record['case'] == 'wrong_scope':
            continue
        for index in range(len(record['attempts'])):
            folder = result_folder(evidence.parent, index)
            capture = json.loads((folder / 'CAPTURE.json').read_bytes())
            _, _, fingerprint, canonical = _validated_scene(capture, _task_capture=True, _return_payload=True)
            context = evidence.parent / 'product_full' / f'call_{index + 1:03d}' / 'READ_CONTEXT.json'
            live = json.loads(context.read_bytes())['after']['selections']
            require(any(row['fingerprint'] == fingerprint for row in live), 'installed capture normalization differs')
            with (folder / 'NORMALIZED_CAPTURE.json').open('xb') as stream:
                stream.write(canonical)
    guard.verify_loaded()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--detail', choices=DETAILS, action='append')
    parser.add_argument('--repeat', type=int, choices=range(1, 13), default=1)
    parser.add_argument('--normalize-only', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'replay requires -I -B')
    binding_path, output = args.binding.resolve(), args.output.resolve()
    if args.normalize_only:
        normalize(binding_path, output)
        return 0
    output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for case in args.case or CASES:
        details = args.detail or (DETAILS if case in ('second_assembly', 'assembly001') else ('brief',))
        for detail in details:
            outcomes.append(run(binding_path, output / case / detail, case, detail, args.repeat))
    if all(outcomes):
        normalize(binding_path, output)
    return 0 if all(outcomes) else 1


if __name__ == '__main__':
    raise SystemExit(main())
