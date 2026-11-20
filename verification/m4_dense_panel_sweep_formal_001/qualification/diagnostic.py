"""Freeze and execute ordinary native qualification calls on the actual stdio bridge."""

import ast
import importlib.util
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ORACLE = V / 'm4_dense_panel_sweep_001/truth/panel_truth.py'
TYPED = V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py'
SOURCE_PATHS = (Path(__file__), HERE / 'native_case.py', ORACLE, TYPED)
READBACK = """capture_again = scene_data()
print(json.dumps({'source_ref': capture_again['source_ref'], 'objects': len(capture_again['objects']),
                  'vertices': sum(len(x['vertices']) for x in capture_again['objects']),
                  'triangles': sum(len(x['triangles']) for x in capture_again['objects']),
                  'persistent_source_ref': diagnostic_source_ref}, separators=(',', ':')))
"""


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native_code():
    tree = ast.parse(ORACLE.read_bytes(), filename=str(ORACLE))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    constants = {node.targets[0].id: node for node in tree.body if isinstance(node, ast.Assign)
                 and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    nodes = [constants[name] for name in ('COUNTS', 'DIRECTIONS')]
    nodes.extend(functions[name] for name in ('require', 'sub', 'dot', 'cross', 'pairs', 'numeric_vector',
                 'source_ranges', 'partition', 'boundary_rectangle', 'clip', 'visibility', 'determine'))
    preface = ('from collections import defaultdict\nfrom fractions import Fraction\nfrom itertools import pairwise\n'
               'from math import gcd, lcm, sqrt\nfrom shapely.geometry import Polygon\nimport json')
    code = '\n\n'.join([preface, *map(ast.unparse, nodes), (HERE / 'native_case.py').read_text(encoding='utf8')])
    compile(code, '<m4-dense-panel-native-qualification>', 'exec')
    return code


def diagnostic_plan(group):
    if group != 'N':
        raise ValueError('only_QN_native_qualification_is_registered_here')
    return [{'name': 'execute_python', 'arguments': {'code': code}} for code in (native_code(), READBACK)]


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import transport

    inspect = load('_dense_formal_native_typed', TYPED).inspect_images
    local = folder / 'client'
    calls = diagnostic_plan(group)
    client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'thin_stdio.py'),
        '--endpoint', str(endpoint), '--audit', str(local / 'attachments')], folder, local / 'transport', deadline)
    try:
        initial = client.call({'jsonrpc': '2.0', 'id': 'init-diagnostic', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'm4-dense-panel-native-qualification', 'version': '1.0'}}})
        save(local / 'INITIALIZE.json', initial)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = client.call({'jsonrpc': '2.0', 'id': 'list-diagnostic', 'method': 'tools/list'})
        save(local / 'TOOLS.json', listing)
        if listing['result']['tools'] != owner.tools:
            raise ValueError('diagnostic_tool_schema_differs_from_owner')
        result['diagnostic_ready_ns'] = time.perf_counter_ns()
        for ordinal, call in enumerate(calls, 1):
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
            content = response.get('result', {}).get('content', [])
            row.update(response_sha256=sha(tool / 'RESPONSE.json'), transport_index=client.records[-1]['index'],
                       text_UTF8_bytes=sum(len(x['text'].encode()) for x in content if x['type'] == 'text'),
                       images=sum(x['type'] == 'image' for x in content),
                       tool_error='error' in response or response.get('result', {}).get('isError') is not False)
            if row['tool_error']:
                raise ValueError(f'diagnostic_tool_error_preserved/{ordinal}')
            archive = inspect(response, tool / 'delivered', contract='ordinary', fact_index=0)
            row.update(delivered_PNG_bytes=archive['PNG_bytes'], readback_sha256=sha(tool / 'delivered/READBACK.json'))
    finally:
        result['diagnostic_close'] = close = client.finish()
        if not close['confirmed'] or close['exit_code'] != 0:
            raise RuntimeError('diagnostic_stdio_close_unconfirmed')
