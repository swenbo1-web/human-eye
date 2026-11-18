"""Use the formal read-only bridge and installed MCP with a saved host reply."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace


NS = Path(__file__).resolve().parents[1]
VERIFICATION = NS.parent
LIVE = VERIFICATION / 'm4_live_assembly_relation_task_001'
FIRST = VERIFICATION / 'm4_assembly_evidence_first_001'
HARNESS = NS / 'harness'
sys.path.insert(0, str(HARNESS))

BINDINGS = {
    'A1': (LIVE / 'PRODUCT_RUN_BINDING.json', 'eb0ecece262ce0fbbe2b01f041b9e6eab77f0c4810030094c2f590850f51b2e0',
           '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'),
    'B1': (FIRST / 'install/OPTIMIZED_BINDING.json', '4ec94ff30668330483e24ac8a9169c6cc3cb080fb93ea717adddf482dee33bc9',
           '99d9b5e93ae10294309df2258b0582405861c0189ab15d659ae9b9e26df6ec9a'),
}
REUSED = {
    LIVE / 'harness/preflight.py': 'c356f4b8449374cbf7b75b5fa35321c49614ccc1d8832cbdf065d4ecad01c0d9',
    FIRST / 'harness/replay.py': '33fffbd6fb5b22bb012bbe9528853a7c1b1704c215bf67286ff112241952056a',
    FIRST / 'harness/fixtures.py': '0051204e667012cb33fd7d5f3cce0a0a075ae5b05442620af41c1a619e16576c',
}
TOOL = 'human_eye_scene_observe'
SCHEMA_INSERT = ('Explicit brief for a closed-solid task set adds same-capture object counts and support vertex indices '
                 'for certified transverse crossings. Reuse the bound local world triangle coordinates to verify the crossing. ')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def standalone(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_frozen_schemas():
    paths = [NS / f'inputs/PRODUCT_SCHEMA_{arm}.json' for arm in 'AB']
    raw = [path.read_bytes() for path in paths]
    a, b = map(json.loads, raw)
    response_detail = b['inputSchema']['properties']['response_detail']
    require(response_detail['description'].count(SCHEMA_INSERT) == 1 and a['name'] == b['name'] == TOOL,
            'installed_schema_extension_not_found_exactly_once')
    response_detail['description'] = response_detail['description'].replace(SCHEMA_INSERT, '')
    require(a == b and len(raw[1]) - len(raw[0]) == 211, 'unexpected_installed_schema_difference')
    return {arm: {'sha256': sha_bytes(body), 'bytes': len(body)} for arm, body in zip('AB', raw)}


def exercise_bridge(folder, owner, runtime, bridge, thin, assembly):
    meta = {'progressToken': 'test-fixture'}
    selectors = [selector['name'] for selector in [assembly['target'], *assembly['candidates']]]
    arguments = bridge.task_arguments(assembly)
    require(arguments == {'include_image': False, 'response_detail': 'brief', 'query': {'mode': 'task', **assembly}},
            'entry_request_is_not_the_frozen_standard_brief_request')
    ordinary = (
        'import json\n'
        'from shapely.geometry import Polygon\n'
        f'packet = scene_data({selectors!r})\n'
        'vertices = np.asarray(packet["objects"][0]["vertices"])\n'
        'polygon = Polygon([(0, 0), (3, 4), (0, 4)])\n'
        'print(json.dumps({"shape": list(vertices.shape), "area": polygon.area, '
        '"source_ref": packet["source_ref"], "objects": len(packet["objects"])}))'
    )
    protocol = [
        ('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'startup-fixture', 'version': '1'}, '_meta': meta}),
        ('notifications/initialized', {}),
        ('tools/list', {'_meta': meta}),
        ('resources/list', {'_meta': meta}),
        ('resources/templates/list', {'_meta': meta}),
        ('ping', {'_meta': meta}),
        ('tools/call', {'name': TOOL, 'arguments': arguments, '_meta': meta}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': ordinary}, '_meta': meta}),
        ('tools/call', {'name': 'execute_python', 'arguments': {'code': 'print(vertices.shape)'}, '_meta': []}),
    ]
    requests = [{'jsonrpc': '2.0', 'method': method, 'params': params,
                 **({} if method.startswith('notifications/') else {'id': index})}
                for index, (method, params) in enumerate(protocol, 1)]
    incoming = ('\n'.join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in requests) + '\n').encode()
    (folder / 'STDIN.jsonl').write_bytes(incoming)
    endpoint = owner.start(folder / 'ENDPOINT.json')
    run = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(thin), '--endpoint', endpoint,
                          '--audit', str(folder / 'stdio')], input=incoming, capture_output=True, timeout=25)
    (folder / 'STDOUT.jsonl').write_bytes(run.stdout)
    (folder / 'STDERR.bin').write_bytes(run.stderr)
    require(run.returncode == 0 and not run.stderr, 'isolated thin_stdio failed; see STDERR.bin')
    responses = [json.loads(line) for line in run.stdout.splitlines()]
    require([row['id'] for row in responses] == [row['id'] for row in requests if 'id' in row]
            and all(row['jsonrpc'] == '2.0' and 'result' in row for row in responses), 'stdio_RPC_envelope')
    initialized, listed, resources, templates, ping, first, calculation, invalid = [r['result'] for r in responses]
    expected_entry = (NS / 'inputs/ENTRY.txt').read_text(encoding='utf8').rstrip('\n')
    require(initialized['protocolVersion'] == '2025-03-26' and 'tools' in initialized['capabilities']
            and initialized['serverInfo']['name'] == bridge.SERVER_NAME and initialized['instructions'] == expected_entry,
            'common_entry_instructions_or_handshake_changed')
    require(resources == {'resources': []} and templates == {'resourceTemplates': []} and ping == {}, 'discovery_shape')
    names = [row['name'] for row in listed['tools']]
    require(len(set(names)) == len(names) and set(names) == bridge.TOOL_NAMES[owner.group], 'slot_tool_inventory')
    registered = next(row for row in listed['tools'] if row['name'] == TOOL)
    install_schema = read(NS / f'inputs/PRODUCT_SCHEMA_{owner.group}.json')
    ordinary_tools = [row for row in listed['tools'] if row['name'] != TOOL]
    require(ordinary_tools == bridge.TOOLS and registered == install_schema,
            'product_schema_modified_by_bridge_or_ordinary_inventory_changed')
    require(all(name not in owner.session.namespace for name in
                ('cameras', 'buffers', 'render_views', 'read_images', 'attach_images', 'observe', 'task')),
            'unexpected_image_or_special_product_helpers')
    retained = read(owner.output / 'tool_01/REQUEST.json')
    product, = runtime.public_requests
    require(retained['params'] == {'name': TOOL, 'arguments': arguments, '_meta': meta}
            and product['request']['params'] == {'name': TOOL, 'arguments': arguments}
            and first == product['response']['result'] and first['isError'] is False
            and [row['type'] for row in first['content']] == ['text'], 'first_brief_request_or_response_changed')
    detail = read(owner.output / 'tool_01/PRODUCT_DETAIL.json')
    require(detail['initial_product_call'] and detail['forwarded_arguments_unchanged']
            and detail['requested_response_detail'] == detail['forwarded_response_detail'] == 'brief'
            and detail['requested_include_image'] is False and detail['returned_images'] == 0, 'bridge_first_call_detail')
    raw_public = first['content'][0]['text'].encode()
    facts = json.loads(raw_public)
    require(facts['schema_version'] == 'task-query-set-v1' and facts['status'] == 'observed'
            and facts['binding']['candidate_count'] == 28
            and [row['name'] for row in facts['binding']['objects']] == selectors, 'selected_capture_binding')
    relations = [row['facts']['closed_solid_relation'] for row in facts['pairs']]
    gaps = [row['separation_gap']['value'] for row in facts['pairs']]
    require([row['value'] for row in relations] == ['penetrating', 'separated', 'separated']
            and gaps == [None, 0.00010000728070735931, 0.023000000044703484]
            and relations[0]['certificate'] == 'transverse_boundary_interiors', 'fixture_closed_solid_facts')
    evidence = facts.get('capture_evidence')
    if owner.group == 'B':
        require(evidence['schema_version'] == 'task-closed-crossing-review-v1'
                and evidence['crossings'][0]['status'] == 'verified'
                and evidence['crossings'][0]['triangle_vertex_indices'] == [[1, 10, 2], [1, 7, 3]],
                'B_same_capture_evidence_missing_or_misaligned')
    else:
        require(evidence is None, 'A_received_B_evidence')
    producer = product['producer_archive']
    raw_producer = Path(producer['path']).read_bytes()
    require(producer['new_observations_for_archive'] == 0 and sha_bytes(raw_producer) == producer['sha256']
            and json.loads(raw_producer).get('capture_evidence') == evidence, 'producer_archive_changed')
    execution = json.loads(calculation['content'][0]['text'])
    require(calculation['isError'] is False and execution['error'] is None and execution['stderr'] == ''
            and json.loads(execution['stdout']) == {'shape': [16, 3], 'area': 6., 'source_ref': 'fixture:source', 'objects': 4}
            and runtime.scene_reads == [selectors], 'ordinary_Python_session_or_fixture_geometry_changed')
    require(invalid['isError'] is True and 'MCP_tool_params_required' in invalid['content'][0]['text'], 'typed_meta_control')
    rows = read(owner.output / 'TOOLS.json')
    require(rows['attempts'] == 3 and [row['status'] for row in rows['tools']] == ['returned', 'returned', 'tool_error'],
            'owner_attempt_ledger_mismatch')
    (exit_path,) = (folder / 'stdio').glob('*/EXIT.json')
    stdio = read(exit_path)
    require(stdio['normal_exit'] and stdio['attempts'] == 3 and stdio['requests'] == len(requests), 'thin_attempt_ledger')
    (folder / 'PUBLIC_FIRST.json').write_bytes(raw_public)
    return {'tools': names, 'entry_instruction_sha256': sha_bytes(initialized['instructions'].encode()),
            'ordinary_tools_sha256': sha_bytes(bridge.encoded(ordinary_tools)),
            'first_arguments': arguments, 'first_text_bytes': len(raw_public), 'first_text_sha256': sha_bytes(raw_public),
            'first_product_source_sha256': facts['binding']['runtime_source_sha256'],
            'first_attached_evidence': evidence is not None, 'producer_archive_sha256': producer['sha256'],
            'public_image_blocks': 0, 'business_attempts': rows['attempts']}


def run(slot, folder, shared_root):
    from budget import Budget
    from common import DISPLAY, load
    from owned_runtime import Runtime
    from run_slot import load_slot_dependencies

    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    result = {'slot': slot, 'passed': False, 'Blender_starts': 0, 'model_starts': 0, 'API_calls': 0,
              'python': sys.executable, 'pid': os.getpid(), 'started_ns': time.perf_counter_ns()}
    listener = thread = runtime = owner = None
    stopped = threading.Event()
    receipts = []
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode, 'preflight_requires_immutable_interpreter_mode')
        for path, digest in REUSED.items():
            require(sha_bytes(path.read_bytes()) == digest, f'reused_preflight_source_changed/{path.name}')
        result['reused_source_pins'] = {path.as_posix(): digest for path, digest in REUSED.items()}
        result['frozen_schemas'] = verify_frozen_schemas()
        binding_path, expected_binding, expected_source = BINDINGS[slot]
        require(sha_bytes(binding_path.read_bytes()) == expected_binding, 'installed_binding_hash')
        binding = read(binding_path)
        require(binding['source_sha256'] == expected_source and len(binding['source_manifest']) == 143,
                'installed_source_identity')
        dependency_root = Path(binding['dependency_root']).resolve(strict=True)
        Owner, consume_slot = load_slot_dependencies(dependency_root, shared_root)
        import bridge
        from consumer_adapter import BASE, BASE_SHA, THIN, consumer_adapter
        require(callable(consume_slot) and Path(bridge.__file__).resolve() == NS / 'bridge.py', 'wrong_owner_import')
        require(Path(sys.executable).resolve() == BASE.resolve() and sha_bytes(BASE.read_bytes()) == BASE_SHA,
                'fixed_base_Python_hash')
        require(all(name not in sys.modules for name in ('numpy', 'PIL', 'shapely')), 'library_imported_before_Owner')
        original = standalone('_assembly_prior_preflight', LIVE / 'harness/preflight.py')
        replay = standalone('_assembly_saved_geometry_replay', FIRST / 'harness/replay.py')
        packet, capture, provenance = replay.fixture('second_assembly', 0)
        save(folder / 'CAPTURE.json', capture)
        save(folder / 'PROVENANCE.json', provenance)
        path = NS / 'inputs/ASSEMBLY.json'
        assembly = read(path)
        selectors = [assembly['target'], *assembly['candidates']]
        require(capture['task_selection']['selectors'] == selectors, 'saved_geometry_selector_mismatch')
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(.25)
        thread = threading.Thread(target=replay.receive, daemon=True,
                                  args=(listener, folder, selectors, [packet], receipts, stopped))
        thread.start()

        class FixtureRuntime(Runtime):
            def __init__(self):
                self.folder, self.label, self.group = folder, slot, slot[0]
                self.task_deadline = self.owned_deadline = time.perf_counter_ns() + 45_000_000_000
                self.budget = Budget(folder / 'budget')
                self.client = self.device = self.mcp_handle = self.native_handle = self.claim = None
                self.native = SimpleNamespace(host='127.0.0.1', port=listener.getsockname()[1], workspace=folder)
                self.cameras, self.buffers = {'views': []}, {}
                self.public_requests, self.scene_reads = [], []
                self.binding_path, self.binding, self.source_sha = binding_path, binding, expected_source
                self.product_root = binding['install_root']
                self.proof = load('_assembly_fixture_process_proof', DISPLAY / 'harness/reused/process_proof.py')

            def scene_data(self, selectors=None):
                self.scene_reads.append(selectors)
                return {'schema': 'fixture-scene', 'source_ref': 'fixture:source', 'source': {},
                        'objects': [mesh for mesh in capture['meshes'] if mesh['name'] in selectors]}

        runtime = FixtureRuntime()
        runtime._start_public_mcp(binding_path, binding)
        owner = Owner(runtime, {'label': slot, 'group': slot[0], 'phase': 'formal',
            'worker_deadline_ns': runtime.task_deadline, 'output': str(folder / 'owner'),
            'assembly_path': str(path), 'assembly_sha256': sha_bytes(path.read_bytes())}, budget=runtime.budget)
        result['libraries'] = original.record_library_paths(owner, dependency_root, shared_root.resolve(strict=True))
        result.update(exercise_bridge(folder, owner, runtime, bridge, THIN, assembly))
        require(result['first_product_source_sha256'] == expected_source, 'public_facts_runtime_source_changed')
        thread.join(2)
        require(not thread.is_alive() and len(receipts) == 1 and receipts[0]['method'] == 'capture_task', 'saved_host_receipt')
        result['host_receipt'] = receipts[0]
        counts = runtime.budget.snapshot()['counts']
        require(counts['business_admissions'] == 3 and counts['Blender_start_attempts'] == counts['consumer_admissions']
                == counts['all_raster_upper'] == 0, 'fixture_budget_mismatch')
        result['budget_counts'] = counts
        result['archive_public_event_filter'] = original.exercise_event_filter(folder)
        turn, adapter = consumer_adapter()
        require(callable(turn) and adapter['consumer_launches_during_adapter_construction'] == 0,
                'consumer_adapter_rehearsal_started_model')
        result['consumer_adapter_proof'] = adapter
        result['passed'] = True
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        stopped.set()
        try:
            if owner is not None:
                closed = result['owner_close'] = owner.close()
                result['passed'] &= closed['confirmed'] and not closed['errors'] and not closed['transport_errors']
            if runtime is not None:
                if runtime.client is not None:
                    closed = result['MCP_close'] = runtime.client.finish()
                    result['passed'] &= closed['confirmed']
                if runtime.mcp_handle is not None:
                    exited = result['MCP_exit'] = runtime.proof._runtime_exit(runtime.mcp_handle)
                    result['passed'] &= exited['exited'] and exited['handle_closed']
        except Exception as error:
            result['close_error'] = {'type': type(error).__name__, 'message': str(error)}
            result['passed'] = False
        finally:
            if thread is not None:
                thread.join(2)
                result['passed'] &= not thread.is_alive()
            if listener is not None:
                listener.close()
        result['host_receipts'] = receipts
        result['closed_ns'] = time.perf_counter_ns()
        save(folder / 'PREFLIGHT.json', result)
    print(slot, 'passed' if result['passed'] else 'failed', folder / 'PREFLIGHT.json')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=BINDINGS)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shared-dependency-root', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.slot, args.output, args.shared_dependency_root))
