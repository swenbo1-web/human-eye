"""Exercise the formal slot wiring with synthetic replies and archived public events."""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class FixtureRuntime:
    def __init__(self):
        self.cameras = {'views': []}
        self.buffers = {}
        self.product_tools = []
        self.public_requests = []
        self.scene_reads = []
        self.normalized_query = None

    def attach_product(self, server):
        self.server = server
        request = {'jsonrpc': '2.0', 'id': 'fixture-list', 'method': 'tools/list'}
        self.product_tools = server.handle_jsonrpc_message(request)['result']['tools']

    def scene_data(self, selectors=None):
        self.scene_reads.append(copy.deepcopy(selectors))
        return {'schema': 'fixture-scene', 'source_ref': 'fixture:source', 'source': {},
                'objects': [{'name': name, 'vertices': [[0., 0., 0.], [3., 4., 0.], [0., 4., 0.]],
                             'triangles': [[0, 1, 2]]} for name in selectors]}

    def observe(self, session_id, *, task_instruction, focal_id, reference_id, include_image, query):
        from human_eye_plugin.task_query import validate_task_query

        self.normalized_query = normalized = validate_task_query(query)
        require(include_image is False and not task_instruction and focal_id is reference_id is None,
                'registered tool passed unexpected observation arguments')
        return {'schema_version': 'task-query-set-v1', 'result_kind': 'task_query', 'status': 'partial',
                'fixture': True, 'selectors': normalized['objects'], 'requested_facts': normalized['requested_facts']}

    def _check_request_budget(self, stage):
        require(stage == 'before_task_publication', 'unexpected fixture budget stage')

    def public_request(self, arguments):
        request = {'jsonrpc': '2.0', 'id': 'fixture-observe', 'method': 'tools/call',
                   'params': {'name': 'human_eye_scene_observe', 'arguments': copy.deepcopy(arguments)}}
        response = self.server.handle_jsonrpc_message(request)
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


def exercise_bridge(owner, runtime, folder, assembly, budget):
    import bridge
    from consumer_adapter import THIN

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
    args = bridge.task_arguments(assembly)
    if owner.group == 'P':
        protocol.append(('tools/call', {'name': bridge.PRODUCT_TOOL, 'arguments': args, '_meta': meta}))
    ordinary = (
        'import json\n'
        'from shapely.geometry import Polygon\n'
        'packet = scene_data(["Object_01", "Object_02", "Object_03", "Object_04"])\n'
        'vertices = np.asarray(packet["objects"][0]["vertices"])\n'
        'polygon = Polygon(vertices[:, :2])\n'
        'print(json.dumps({"length": float(np.linalg.norm(vertices[1] - vertices[0])),\n'
        '    "area": polygon.area, "source_ref": packet["source_ref"], "objects": len(packet["objects"])}))'
    )
    protocol.extend([
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': ordinary}, '_meta': meta}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': 'print(vertices.shape)'}, '_meta': []}),
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
            and initialized['serverInfo']['name'] == bridge.SERVER_NAME,
            'tool initialization failed')
    require(resources == {'resources': []} and templates == {'resourceTemplates': []} and ping == {},
            'empty discovery replies changed')
    tool_names = [tool['name'] for tool in listed['tools']]
    require(len(tool_names) == len(set(tool_names)) and set(tool_names) == bridge.TOOL_NAMES[owner.group],
            'unexpected slot tool inventory')
    shared = [tool for tool in listed['tools'] if tool['name'] != bridge.PRODUCT_TOOL]
    require(shared == bridge.TOOLS and all(name not in owner.session.namespace for name in
            ('cameras', 'buffers', 'render_views', 'read_images', 'attach_images', 'observe', 'task')),
            'different ordinary tool schema or unexpected frame/product helpers')
    if owner.group == 'P':
        product_tool = next(tool for tool in listed['tools'] if tool['name'] == bridge.PRODUCT_TOOL)
        require(initialized['instructions'] == bridge.P_ENTRY and bridge.P_ENTRY in product_tool['description'],
                'P did not advertise the explicit assembly task request')
        retained = json.loads((owner.output / 'tool_01/REQUEST.json').read_bytes())
        require(retained['params'] == {'name': bridge.PRODUCT_TOOL, 'arguments': args, '_meta': meta},
                'P model request or standard params._meta changed')
        product = runtime.public_requests
        payload = json.loads(calls[0]['content'][0]['text'])
        require(len(product) == 1
                and product[0]['request']['params'] == {'name': bridge.PRODUCT_TOOL, 'arguments': args}
                and calls[0] == product[0]['response']['result']
                and calls[0]['isError'] is False
                and len(calls[0]['content']) == 1 and calls[0]['content'][0]['type'] == 'text'
                and payload['result_kind'] == 'task_query' and payload['fixture'] is True
                and payload['selectors'] == [assembly['target'], *assembly['candidates']]
                and payload['requested_facts'] == assembly['requested_facts'],
                'installed task dispatch did not preserve the exact request and text-only fixture result')
        detail = json.loads((owner.output / 'tool_01/PRODUCT_DETAIL.json').read_bytes())
        require(detail['initial_product_call'] and detail['forwarded_arguments_unchanged']
                and detail['requested_include_image'] is False and detail['returned_images'] == 0,
                'P detail receipt did not match the fixture wire')
    else:
        require(not runtime.public_requests and 'instructions' not in initialized, 'N acquired a P entry')
    calculation, invalid = calls[-2:]
    execution = json.loads(calculation['content'][0]['text'])
    require(calculation['isError'] is False and execution['error'] is None and execution['stderr'] == ''
            and json.loads(execution['stdout']) == {'length': 5., 'area': 6., 'source_ref': 'fixture:source', 'objects': 4}
            and runtime.scene_reads == [[selector['name'] for selector in [assembly['target'], *assembly['candidates']]]],
            'ordinary dependency computation or synthetic scene read failed')
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
            'budget_counts': counts, 'P_registered_task_fixture': owner.group == 'P',
            'P_normalized_fixture_request': runtime.normalized_query, 'synthetic_scene_selectors': runtime.scene_reads}


def exercise_event_filter(folder):
    import consumer_contract as contract
    from common import NS, read, sha

    historical = Path('D:/he_m4_live_source_region_task_002')
    index_file = NS.parent / 'm4_live_source_region_task_002/RUNTIME_INDEX.json'
    index = {row['path']: row for row in read(index_file)['files']}
    originals = {}

    def original(relative):
        path = historical / relative
        row = index[relative]
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'historical original changed')
        originals[relative] = row['sha256']
        return path

    timed = original('slots/N1/consumer/events.jsonl')
    stdout = original('slots/N1/consumer/stdout.raw.bin')
    full = original('slots/N1/owner/tool_01/RESPONSE.json')
    with timed.open('rb') as stream:
        projected = [json.loads(raw) for raw in stream if len(raw) > 2 * contract.CLI_PROJECTION_SIDE_UTF8_BYTES
                     and (header := contract.public_tool_event_header(raw, timed=True))
                     and header.group(1) == b'item.completed']
    require(len(projected) == 1, 'expected one historical projected public tool event')
    record = projected[0]
    event = {'perf_ns': record['perf_ns'], **record['event']}
    projected_binding = contract.bind_tool_result(read(full), event['item'])
    require(projected_binding['reason'] == 'verified_cli_text_projection', 'historical public projection changed')

    real_decode = json.loads
    decoded = []

    def decode_public(raw):
        require(contract.public_tool_event_header(raw) or contract.public_tool_event_header(raw, timed=True),
                'non-public sentinel reached JSON decoding')
        decoded.append(len(raw))
        return real_decode(raw)

    # A nested public-type distractor catches filters that match arbitrary text or fields.
    private = (b'{"type":"item.completed","item":{"id":'
               + contract.compact_json(event['item']['id']).encode('utf8')
               + b',"type":"reasoning","text":"fixture-private-sentinel",'
                 b'"distractor":{"type":"mcp_tool_call"}}}')
    timed_private = b'{"perf_ns":0,"event":' + private + b'}'
    sentinels = folder / 'EVENT_FILTER_SENTINELS.jsonl'
    sentinels.write_bytes(private + b'\n' + timed_private + b'\n')
    fake_json = SimpleNamespace(loads=decode_public, dumps=json.dumps)
    contract.json = fake_json
    try:
        public_stdout = contract.archived_event_line(stdout, event, timed=False)
        public_timed = contract.archived_event_line(timed, event, timed=True)
        require(public_stdout is not None and public_timed is not None and len(decoded) == 2,
                'archive locator did not uniquely bind the historical public originals')
        require(contract.archived_event_line(sentinels, event, timed=False) is None
                and contract.archived_event_line(sentinels, event, timed=True) is None and len(decoded) == 2,
                'private sentinels affected public event lookup')
    finally:
        contract.json = json
    return {'historical_public_projection_verified': True, 'originals_sha256': originals,
            'public_stdout_line': public_stdout, 'public_timed_line': public_timed,
            'public_lines_decoded': len(decoded), 'private_sentinels_decoded': 0}


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
        from consumer_adapter import BASE, BASE_SHA, consumer_adapter
        require(Path(sys.executable).resolve() == BASE.resolve() and sha(BASE) == BASE_SHA,
                'preflight base interpreter identity changed')
        require(callable(consume_slot) and Path(bridge.__file__).resolve() == NS / 'bridge.py',
                'formal slot dependency entry resolved to another bridge')
        library_names = ('numpy', 'PIL', 'shapely')
        before = [name for name in library_names if name in sys.modules]
        result.update(dependency_root=str(dependency_root), shared_dependency_root=str(shared_root),
                      libraries_before_Owner=before)
        require(not before, 'a geometry dependency was imported before Owner construction')
        assembly_path = NS / 'inputs/ASSEMBLY.json'
        assembly = read(assembly_path)
        runtime = FixtureRuntime()
        if slot == 'P1':
            product_root = Path(binding['install_root']).resolve(strict=True)
            sys.path.insert(0, str(product_root))
            from human_eye_plugin import live_spatial_mcp

            source = Path(live_spatial_mcp.__file__).resolve()
            relative = source.relative_to(product_root).as_posix()
            expected_sha = next(row['sha256'] for row in binding['source_manifest'] if row['path'] == relative)
            require(sha(source) == expected_sha, 'fixture product register resolved to unexpected source bytes')
            runtime.attach_product(live_spatial_mcp.LiveSpatialMCPServer(runtime, default_session_id='startup-fixture'))
            require(next(tool for tool in runtime.product_tools if tool['name'] == bridge.PRODUCT_TOOL)
                    == read(NS / 'inputs/PRODUCT_SCHEMA.json'), 'frozen schema differs from installed registered tool')
            result['installed_registered_source'] = {'path': str(source), 'sha256': expected_sha}
        budget = Budget(folder / 'fixture_budget')
        owner = Owner(runtime, {'label': slot, 'group': slot[0], 'phase': 'formal',
            'worker_deadline_ns': time.perf_counter_ns() + 30_000_000_000, 'output': str(folder / 'owner'),
            'assembly_path': str(assembly_path), 'assembly_sha256': sha(assembly_path)}, budget=budget)
        result['libraries'] = record_library_paths(owner, dependency_root, shared_root)
        result.update(exercise_bridge(owner, runtime, folder, assembly, budget))
        result['archive_public_event_filter'] = exercise_event_filter(folder)
        turn, adapter = consumer_adapter()
        require(callable(turn) and adapter['consumer_launches_during_adapter_construction'] == 0,
                'consumer adapter construction changed')
        result['consumer_adapter_proof'] = adapter
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
