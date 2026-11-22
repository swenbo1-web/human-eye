"""Drive live qualification through the same stdio and Owner as formal runs."""

from pathlib import Path
import sys
import time

from common import NS, load, read, save, sha
from runtime import previous


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    source = read(folder / 'initial_capture/TERMINAL_SOURCE.json')
    root = folder / 'client'
    client = previous.transport.StdioClient(
        [sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
         '--endpoint', str(endpoint), '--audit', str(root / 'attachments')],
        folder, root / 'transport', deadline)

    def call(name, arguments):
        ordinal = len(result['diagnostic_calls']) + 1
        directory = root / f'call_{ordinal:02d}'
        directory.mkdir()
        request = {'jsonrpc': '2.0', 'id': f'qualification-{ordinal}', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': arguments}}
        save(directory / 'REQUEST.json', request)
        row = {'index': ordinal, 'name': name, 'request_sha256': sha(directory / 'REQUEST.json'),
               'started_ns': time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        response = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory / 'RESPONSE.json', response)
        save(directory / 'RECEIPT.json', client.records[-1])
        row['response_sha256'] = sha(directory / 'RESPONSE.json')
        body = response.get('result')
        if not isinstance(body, dict) or 'error' in response:
            raise ValueError(f'qualification_RPC_error/{ordinal}/{name}/{str(response)[:400]}')
        return body

    try:
        init = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'dense-micro-surface-qualification', 'version': '1'}}})
        save(root / 'INITIALIZE.json', init)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = client.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(root / 'TOOLS.json', tools)
        if tools['result']['tools'] != owner.tools:
            raise ValueError('qualification_stdio_catalogue_changed')
        invalid = call('render_local', {'direction': 'TOP', 'view_span_m': 0})
        if not invalid['isError']:
            raise ValueError('invalid_common_argument_was_accepted')
        name = 'native' if group == 'N' else 'product_qa'
        paths = sys.path[:]
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            module = load(f'_dense_micro_surface_{name}', Path(__file__).with_name(name + '.py'))
            solver = module.solve_native if group == 'N' else module.solve_product
            proof = solver(call, owner, source, folder)
        finally:
            sys.path[:] = paths
        if proof.get('passed') is not True or sum(row.get('complete') is True for row in proof.get('images', {}).values()) < 2:
            raise ValueError('live_qualification_missing_two_complete_witnesses')
        if group == 'N':
            replay = load('_dense_micro_surface_CLI_replay', Path(__file__).with_name('product_qa.py')).check_cli
            output = root / 'fixed_cli_replay'
            output.mkdir()
            proof['CLI'] = {f'{row["index"]}_{row["name"]}':replay(
                read(root / f'call_{row["index"]:02d}' / 'RESPONSE.json')['result'], output, str(row['index']))
                 for row in result['diagnostic_calls'] if row['name'] in ('render_views', 'render_local', 'execute_python') and row['index'] != 1}
            if not all(row['passed'] for row in proof['CLI'].values()):
                raise ValueError('ordinary_qualification_required_CLI_text_or_PNG_clipped')
    finally:
        result['diagnostic_close'] = close = client.finish()
        if not close['confirmed'] or close['exit_code'] != 0:
            raise ValueError('qualification_stdio_close_unconfirmed')
    save(folder / 'QUALIFICATION.json', proof)
    result['qualification'] = proof
