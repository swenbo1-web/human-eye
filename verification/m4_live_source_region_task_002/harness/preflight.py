"""Exercise one formal slot's startup and MCP wiring with a synthetic region."""

import argparse
import base64
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class FixtureRuntime:
    def __init__(self, product_tool):
        self.cameras = {'views': [{'name': 'SCENE', 'size_px': [1, 1]}]}
        self.buffers = {}
        self.product_tools = [product_tool]
        self.public_requests = []

    def public_request(self, arguments):
        request = {'jsonrpc': '2.0', 'id': 'fixture-observe', 'method': 'tools/call',
                   'params': {'name': self.product_tools[0]['name'], 'arguments': copy.deepcopy(arguments)}}
        query = arguments['query']
        brief = {'schema': 'source-region-brief-v2', 'result_kind': 'source_region', 'status': 'complete',
                 'region': {'source_triangle_count': len(query['region']['source_triangle_indices'])}}
        result = {'isError': False, 'content': [{'type': 'text', 'text': json_text(brief)}, self.image]}
        response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        self.public_requests.append({'request': request, 'response': response, 'fixture': True})
        return response


def record_library_paths(owner, dependency_root, shared_dependency_root):
    evidence = {}
    for module, variable, root in (('numpy', 'np', dependency_root), ('PIL', 'PIL', dependency_root),
                                   ('shapely', 'shapely', shared_dependency_root)):
        loaded = sys.modules[module]
        path = Path(loaded.__file__).resolve()
        require(path.is_file() and path.is_relative_to(root), f'{module} resolved outside {root}: {path}')
        require(owner.session.namespace[variable] is loaded, f'{module} is absent from the ordinary session')
        evidence[module] = {'file': str(path), 'version': loaded.__version__}
    return evidence


def exercise_bridge(owner, runtime, folder, region, budget):
    import bridge
    from consumer_adapter import THIN

    image = io.BytesIO()
    owner.session.namespace['Image'].new('RGB', (1, 1), (5, 7, 11)).save(image, format='PNG')
    runtime.image = {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(image.getvalue()).decode()}
    meta = {'progressToken': 'startup-fixture'}
    protocol = [
        ('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'startup-fixture', 'version': '1'}, '_meta': meta}),
        ('notifications/initialized', {}),
        ('tools/list', {'_meta': meta}),
        ('resources/list', {'_meta': meta}),
        ('resources/templates/list', {'_meta': meta}),
        ('ping', {'_meta': meta}),
    ]
    args = {'include_image': True, 'query': {'mode': 'source_region', 'reference': region['reference'],
            'requested_facts': ['surface_proximity'],
            'region': {'object': region['object'], 'source_triangle_indices': [0]}}}
    if owner.group == 'P':
        protocol.append(('tools/call', {'name': bridge.PRODUCT_TOOL, 'arguments': args, '_meta': meta}))
    ordinary = (
        'import json\n'
        'from shapely.geometry import Polygon\n'
        'polygon = Polygon([(0, 0), (3, 0), (0, 4)])\n'
        'print(json.dumps({"length": float(np.linalg.norm([3, 4])), "area": polygon.area,\n'
        '    "pixel": list(Image.new("RGB", (1, 1), (5, 7, 11)).getpixel((0, 0))), "region": region}))'
    )
    protocol.extend([
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': ordinary}, '_meta': meta}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': 'print(region)'}, '_meta': []}),
    ])
    requests = [{'jsonrpc': '2.0', 'method': method, 'params': params,
                 **({} if method.startswith('notifications/') else {'id': index})}
                for index, (method, params) in enumerate(protocol, 1)]
    incoming = ('\n'.join(map(json_text, requests)) + '\n').encode('utf8')
    (folder / 'STDIN.jsonl').write_bytes(incoming)
    endpoint = owner.start(folder / 'ENDPOINT.json')
    run = subprocess.run([sys.executable, '-I', '-B', str(THIN), '--endpoint', endpoint,
                          '--audit', str(folder / 'stdio')], input=incoming, capture_output=True, timeout=20)
    (folder / 'STDOUT.jsonl').write_bytes(run.stdout)
    (folder / 'STDERR.bin').write_bytes(run.stderr)
    require(run.returncode == 0 and not run.stderr, 'isolated thin_stdio failed; see STDERR.bin')
    responses = [json.loads(line) for line in run.stdout.splitlines()]
    require([reply['id'] for reply in responses] == [row['id'] for row in requests if 'id' in row]
            and all(reply['jsonrpc'] == '2.0' and 'result' in reply for reply in responses),
            'stdio JSON-RPC response identity or shape changed')
    initialized, listed, resources, templates, ping, *calls = [row['result'] for row in responses]
    require(initialized['protocolVersion'] == '2025-03-26' and 'tools' in initialized['capabilities']
            and initialized['serverInfo']['name'] == 'm4-live-source-region-task-002',
            'tool initialization failed')
    require(resources == {'resources': []} and templates == {'resourceTemplates': []} and ping == {},
            'empty discovery replies changed')
    tool_names = [tool['name'] for tool in listed['tools']]
    require(len(tool_names) == len(set(tool_names)) and set(tool_names) == bridge.TOOL_NAMES[owner.group],
            'unexpected slot tool inventory')
    if owner.group == 'P':
        product_tool = next(tool for tool in listed['tools'] if tool['name'] == bridge.PRODUCT_TOOL)
        require('omit the top-level response_detail field' in initialized['instructions']
                and initialized['instructions'] in product_tool['description'],
                'P did not advertise the default source_region request')
        downstream = copy.deepcopy(args)
        downstream['query']['region']['source_triangle_indices'] = region['source_triangle_ids']
        retained = json.loads((owner.output / 'tool_01/REQUEST.json').read_bytes())
        require(retained['params'] == {'name': bridge.PRODUCT_TOOL, 'arguments': args, '_meta': meta},
                'P model request or standard params._meta changed')
        product = runtime.public_requests
        require(len(product) == 1
                and product[0]['request']['params'] == {'name': bridge.PRODUCT_TOOL, 'arguments': downstream}
                and calls[0] == product[0]['response']['result']
                and calls[0]['isError'] is False
                and json.loads(calls[0]['content'][0]['text'])['schema'] == 'source-region-brief-v2'
                and calls[0]['content'][1] == runtime.image,
                'P omitted-detail request, marker expansion, or fixture v2 delivery changed')
        detail = json.loads((owner.output / 'tool_01/PRODUCT_DETAIL.json').read_bytes())
        require(detail['default_brief_v2_returned'] and detail['bound_marker_expanded']
                and detail['returned_images'] == 1, 'P default detail receipt did not match the fixture wire')
    else:
        require(not runtime.public_requests and 'instructions' not in initialized, 'N acquired a P entry')
    calculation, invalid = calls[-2:]
    execution = json.loads(calculation['content'][0]['text'])
    require(calculation['isError'] is False and execution['error'] is None and execution['stderr'] == ''
            and json.loads(execution['stdout']) == {'length': 5., 'area': 6., 'pixel': [5, 7, 11], 'region': region},
            'ordinary dependency computation or synthetic region binding failed')
    require(invalid['isError'] is True and 'MCP_tool_params_required' in invalid['content'][0]['text'],
            'malformed _meta was not recorded as a rejected attempt')
    tools = json.loads((owner.output / 'TOOLS.json').read_bytes())
    expected_count = len(calls)
    require(tools['attempts'] == expected_count
            and [row['attempt'] for row in tools['tools']] == list(range(1, expected_count + 1))
            and [row['status'] for row in tools['tools']] == ['returned'] * (expected_count - 1) + ['tool_error'],
            'bridge attempt ledger missed a successful or rejected tool call')
    (exit_path,) = (folder / 'stdio').glob('*/EXIT.json')
    stdio = json.loads(exit_path.read_bytes())
    require(stdio['normal_exit'] and stdio['attempts'] == expected_count and stdio['requests'] == len(requests),
            'thin_stdio attempt ledger disagrees with the bridge')
    counts = budget.snapshot()['counts']
    require(counts['business_admissions'] == expected_count and
            counts['Blender_start_attempts'] == counts['consumer_admissions'] == counts['all_raster_upper'] == 0,
            'isolated fixture budget disagrees with the attempt ledger')
    return {'tools': tool_names, 'resource_discoveries': [resources, templates], 'business_attempts': expected_count,
            'budget_counts': counts, 'P_default_fixture': owner.group == 'P',
            'synthetic_region_rows': len(region['source_triangle_ids'])}


def run(slot, folder, shared_root):
    from run_slot import load_slot_dependencies
    from budget import Budget
    from common import NS, read, save, sha

    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    result = {'slot': slot, 'group': slot[0], 'pid': os.getpid(), 'python': sys.executable,
              'iso_flags': {'isolated': sys.flags.isolated, 'dont_write_bytecode': sys.dont_write_bytecode},
              'started_ns': time.perf_counter_ns(), 'passed': False}
    owner = None
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode, 'invoke the fixed base Python with -I -B')
        binding = read(NS / 'PRODUCT_RUN_BINDING.json')
        dependency_root = Path(binding['dependency_root']).resolve(strict=True)
        shared_root = shared_root.resolve(strict=True)
        Owner, consume_slot = load_slot_dependencies(dependency_root, shared_root)
        import bridge
        from consumer_adapter import BASE, BASE_SHA
        require(Path(sys.executable).resolve() == BASE.resolve() and sha(BASE) == BASE_SHA,
                'preflight base interpreter identity changed')
        require(callable(consume_slot) and Path(bridge.__file__).resolve() == NS / 'bridge.py',
                'formal slot dependency entry resolved to another bridge')
        library_names = ('numpy', 'PIL', 'shapely')
        before = [name for name in library_names if name in sys.modules]
        result.update(dependency_root=str(dependency_root), shared_dependency_root=str(shared_root),
                      libraries_before_Owner=before)
        require(not before, 'a geometry dependency was imported before Owner construction')
        region = {'object': {'name': bridge.OBJECT_NAME}, 'object_id': 'fixture:region',
                  'reference': {'name': 'Cube'}, 'source_triangle_ids': list(range(1000, 1748))}
        region_path = folder / 'FIXTURE_REGION.json'
        save(region_path, region)
        runtime = FixtureRuntime(read(NS / 'inputs/PRODUCT_SCHEMA.json'))
        budget = Budget(folder / 'fixture_budget')
        owner = Owner(runtime, {'label': slot, 'group': slot[0], 'phase': 'formal',
            'worker_deadline_ns': time.perf_counter_ns() + 30_000_000_000, 'output': str(folder / 'owner'),
            'region_path': str(region_path), 'region_sha256': sha(region_path)}, budget=budget)
        result['libraries'] = record_library_paths(owner, dependency_root, shared_root)
        result.update(exercise_bridge(owner, runtime, folder, region, budget))
        result['passed'] = True
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        if owner is not None:
            try:
                closed = owner.close()
                result['owner_close'] = closed
                if not closed['confirmed'] or closed['errors'] or closed['transport_errors']:
                    result['passed'] = False
            except Exception as error:
                result['close_error'] = {'type': type(error).__name__, 'message': str(error)}
                result['passed'] = False
        result['closed_ns'] = time.perf_counter_ns()
        save(folder / 'PREFLIGHT.json', result)
    print(slot, 'passed' if result['passed'] else 'failed', folder / 'PREFLIGHT.json')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=('N1', 'P1'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--shared-dependency-root', required=True, type=Path)
    options = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(run(options.slot, options.output, options.shared_dependency_root))
