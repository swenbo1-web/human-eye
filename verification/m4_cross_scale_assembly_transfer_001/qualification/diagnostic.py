"""Run the predeclared zero-model calls through the real thin stdio and owner."""

import ast
import importlib.util
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
SCOPES = (
    (V / 'm4_global_local_qualification_001/oracle/static_oracle.py',
     ('sub', 'dot', 'cross', 'primitive', 'component_analysis')),
    (V / 'm4_cross_scale_discovery_001/oracle/geometry_witness.py', ('clip', 'area2', 'prove')),
)
REQUEST = {'query': {'mode': 'active_observation', 'region_task': {'area_min_m2': 0.025,
           'area_max_m2': 0.05, 'normal_z_min': 0.75}}, 'include_image': True, 'response_detail': 'brief'}
READBACK = """import json
data = scene_data()
print(json.dumps({'source_ref': data['source_ref'], 'objects': len(data['objects']),
                  'vertices': sum(len(x['vertices']) for x in data['objects']),
                  'triangles': sum(len(x['triangles']) for x in data['objects'])}, separators=(',', ':')))
"""


def legacy(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native_code():
    parts = ['from collections import Counter, defaultdict\nfrom fractions import Fraction as F\n'
             'from math import gcd, lcm, sqrt\nimport json']
    for path, names in SCOPES:
        tree = ast.parse(path.read_bytes(), filename=str(path))
        functions = {item.name: item for item in tree.body if isinstance(item, ast.FunctionDef)}
        for name in names:
            part = ast.unparse(functions[name])
            if name == 'component_analysis':
                old = 'F(1, 128) ** 2 <= area_squared <= F(1, 32) ** 2'
                if part.count(old) != 1:
                    raise ValueError('native_oracle_selection_anchor_changed')
                part = part.replace(old, 'F(1, 40) ** 2 <= area_squared <= F(1, 20) ** 2')
            parts.append(part)
    parts.append((HERE / 'native_case.py').read_text(encoding='utf8'))
    code = '\n\n'.join(parts)
    compile(code, '<assembly-native-qualification>', 'exec')
    return code


def diagnostic_plan(group):
    fixed = json.loads((NS / 'inputs/REQUEST.json').read_bytes())
    if fixed != REQUEST:
        raise ValueError('product_qualification_request_differs_from_registered_task')
    if group == 'P':
        return [{'name': 'human_eye_scene_observe', 'arguments': fixed},
                {'name': 'execute_python', 'arguments': {'code': READBACK}}]
    if group != 'N':
        raise ValueError('unregistered_qualification_group')
    return [{'name': 'execute_python', 'arguments': {'code': native_code()}},
            {'name': 'execute_python', 'arguments': {'code': READBACK}}]


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import transport

    inspect = legacy('_assembly_qualification_content_reader',
                     V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py').inspect_images
    local = folder / 'client'
    calls = diagnostic_plan(group)
    client = transport.StdioClient([sys.executable, '-I', '-B', '-X', 'utf8', str(NS / 'thin_stdio.py'),
        '--endpoint', str(endpoint), '--audit', str(local / 'attachments')], folder, local / 'transport', deadline)
    try:
        initial = client.call({'jsonrpc': '2.0', 'id': 'init-diagnostic', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'cross-scale-assembly-qualification', 'version': '1.0'}}})
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
            contract = 'active_region_task' if call['name'] == 'human_eye_scene_observe' else 'ordinary'
            archive = inspect(response, tool / 'delivered', contract=contract, fact_index=0)
            row.update(delivered_PNG_bytes=archive['PNG_bytes'], readback_sha256=sha(tool / 'delivered/READBACK.json'))
    finally:
        result['diagnostic_close'] = close = client.finish()
        if not close['confirmed'] or close['exit_code'] != 0:
            raise RuntimeError('diagnostic_stdio_close_unconfirmed')
