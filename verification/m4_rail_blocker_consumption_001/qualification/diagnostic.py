"""Issue the fixed qualification calls through the owned stdio bridge."""

from pathlib import Path
import runpy
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
BRIEF = V / 'm4_dense_region_brief_001/checks/brief_schema.py'
TYPED = V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py'


def diagnostic_plan():
    from common import TRUTH, read

    targets = [[row['object_name'], row['source_triangle_indices']]
               for row in read(TRUTH)['eligible'] if row['unit_normal'] == [-1, 0, 0]]
    code = 'TARGETS = ' + repr(targets) + '\n' + (HERE / 'native_case.py').read_text(encoding='utf8')
    compile(code, '<rail-native-qualification>', 'exec')
    return [
        {'name': 'human_eye_scene_observe', 'arguments': read(NS / 'inputs/REQUEST.json')},
        {'name': 'execute_python', 'arguments': {'code': code}},
    ]


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import transport

    if group != 'P' or result['label'] not in ('QA', 'QB'):
        raise ValueError('registered_rail_qualification_required')
    verify_brief = runpy.run_path(str(BRIEF))['verify_brief']
    inspect = runpy.run_path(str(TYPED))['inspect_images']
    local = folder / 'client'
    client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'thin_stdio.py'),
        '--endpoint', str(endpoint), '--audit', str(local / 'attachments')], folder, local / 'transport', deadline)
    try:
        initial = client.call({'jsonrpc': '2.0', 'id': 'init-diagnostic', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'm4-rail-qualification', 'version': '1.0'}}})
        save(local / 'INITIALIZE.json', initial)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = client.call({'jsonrpc': '2.0', 'id': 'list-diagnostic', 'method': 'tools/list'})
        save(local / 'TOOLS.json', listing)
        if listing['result']['tools'] != owner.tools:
            raise ValueError('diagnostic_tool_schema_differs_from_owner')
        result['diagnostic_ready_ns'] = time.perf_counter_ns()
        for ordinal, call in enumerate(diagnostic_plan(), 1):
            tool = local / f'call_{ordinal:02d}'
            tool.mkdir()
            request = {'jsonrpc': '2.0', 'id': f'diagnostic-{ordinal}', 'method': 'tools/call', 'params': call}
            save(tool / 'REQUEST.json', request)
            row = {'ordinal': ordinal, 'name': call['name'], 'request_sha256': sha(tool / 'REQUEST.json'),
                   'started_ns': time.perf_counter_ns()}
            result['diagnostic_calls'].append(row)
            response = client.call(request)
            row['returned_ns'] = time.perf_counter_ns()
            save(tool / 'RESPONSE.json', response)
            save(tool / 'RECEIPT.json', client.records[-1])
            raw = response.get('result', {})
            content = raw.get('content', [])
            row.update(response_sha256=sha(tool / 'RESPONSE.json'), transport_index=client.records[-1]['index'],
                       text_UTF8_bytes=sum(len(x['text'].encode()) for x in content if x['type'] == 'text'),
                       images=sum(x['type'] == 'image' for x in content),
                       tool_error='error' in response or raw.get('isError') is not False)
            if row['tool_error']:
                raise ValueError(f'diagnostic_tool_error_preserved/{ordinal}')
            if ordinal == 1:
                _, images = verify_brief(raw)
                delivered = tool / 'delivered'
                delivered.mkdir()
                for metadata, png in images:
                    (delivered / f"block_{metadata['content_index']:02d}.png").write_bytes(png)
                save(delivered / 'READBACK.json', {'images': [metadata for metadata, _ in images], 'typed_v2': True})
                row['delivered_PNG_bytes'] = sum(len(png) for _, png in images)
            else:
                archive = inspect(response, tool / 'delivered', contract='ordinary', fact_index=0)
                row['delivered_PNG_bytes'] = archive['PNG_bytes']
            row['readback_sha256'] = sha(tool / 'delivered/READBACK.json')
    finally:
        result['diagnostic_close'] = close = client.finish()
        if not close['confirmed'] or close['exit_code'] != 0:
            raise RuntimeError('diagnostic_stdio_close_unconfirmed')
