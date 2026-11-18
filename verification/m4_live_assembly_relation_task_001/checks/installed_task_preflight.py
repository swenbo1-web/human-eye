"""Check installed standard MCP with a synthetic four-mesh capture and no Blender."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
from budget import Budget
from common import DISPLAY, HERE, NS, SOURCE_SHA, load, read, save, sha


CORNERS = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
           (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
TRIANGLES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def fixture(selectors):
    offsets = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (1.0, 0.8, 0.6), (6.0, 0.0, 0.0))
    meshes = []
    for index, (selector, offset) in enumerate(zip(selectors, offsets), 1):
        vertices = [[2.0 * value + origin for value, origin in zip(corner, offset)] for corner in CORNERS]
        meshes.append({'object_id': f'fixture:box:{index}', 'mark_label': f'B{index}',
                       'name': selector['name'], 'vertices': vertices, 'faces': TRIANGLES})
    bindings = [{key: mesh[key] for key in ('object_id', 'name')} for mesh in meshes]
    scope = 'selected_objects'
    return {'unit': 'm', 'coordinate_frame': 'world', 'source': 'synthetic_closed_boxes',
            'revision': 'fixture:synthetic-closed-boxes-v1', 'meshes': meshes, 'capture_scope': scope,
            'task_selection': {'selectors': selectors, 'bindings': bindings,
                               'pair_reason': None, 'candidate_count': len(meshes)},
            'host_identity': {'schema_version': '1.0', 'document_epoch': hashlib.sha256(b'fixture').hexdigest(),
                              'object_instances': {mesh['object_id']: str(index) for index, mesh in enumerate(meshes)},
                              'capture_scope': scope}}


def reply_once(listener, selectors, output, result):
    try:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(10)
            raw = bytearray()
            while chunk := connection.recv(65536):
                raw.extend(chunk)
                require(len(raw) <= 1024 * 1024, 'fixture_host_request_bound')
                try:
                    request = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    continue
                break
            (output / 'HOST_REQUEST.bin').write_bytes(raw)
            require(set(request) == {'type', 'params'} and request['type'] == 'execute_code', 'fixture_host_wire_shape')
            header = next(line for line in request['params']['code'].splitlines() if line.startswith('_request = '))
            call = ast.parse(header).body[0].value
            method = json.loads(ast.literal_eval(call.args[0]))
            require(method['command'] == 'capture_task' and method['params'] == {'selectors': selectors},
                    'installed_product_must_request_exact_four_object_task_capture')
            capture = {'protocol_version': '1.0', 'id': method['id'], 'result': fixture(selectors)}
            response = {'status': 'success', 'result': {'executed': True,
                        'result': PREFIX + json.dumps(capture, separators=(',', ':')) + '\n'}}
            wire = json.dumps(response, separators=(',', ':')).encode('utf8')
            (output / 'HOST_RESPONSE.bin').write_bytes(wire)
            connection.sendall(wire)
            result['request'] = method
            result['wire'] = {'request_bytes': len(raw), 'response_bytes': len(wire), 'code_bytes': len(request['params']['code'].encode())}
    except BaseException as error:
        result['fixture_error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}


def run(output):
    output = output.resolve()
    output.mkdir(parents=True)
    binding_path = NS / 'PRODUCT_RUN_BINDING.json'
    binding = read(binding_path)
    task = read(NS / 'inputs/ASSEMBLY.json')
    selectors = [task['target'], *task['candidates']]
    result = {'schema': 'm4-live-assembly-installed-task-preflight-v1', 'passed': False,
              'fixture_source': 'synthetic closed boxes', 'started_ns': time.perf_counter_ns(),
              'Blender_starts': 0, 'model_starts': 0, 'isolation': {'python': sys.executable, 'isolated': sys.flags.isolated}}
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = thread = None
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_base_Python_isolation_required')
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(25)
        thread = threading.Thread(target=reply_once, args=(listener, selectors, output, result), daemon=True)
        thread.start()
        config = output / 'PRODUCT_CONFIG.json'
        save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                      'project_root': binding['install_root'], 'state_file': str(output / 'product_state.json'),
                      'audit_file': str(output / 'product_audit.jsonl'), 'expected_identity': {'source_sha256': SOURCE_SHA},
                      'request_budget_s': 20, 'blender': {'host': '127.0.0.1', 'port': listener.getsockname()[1], 'timeout_s': 20}})
        transport = load('_assembly_fixture_stdio_client', DISPLAY / 'harness/reused/stdio_checks.py')
        budget = Budget(output / 'budget')
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py'),
                   '--binding', str(binding_path), '--config', str(config), '--ledger', str(budget.root),
                   '--evidence', str(output / 'mcp_io'), '--phase', 'qualification', '--label', 'P1',
                   '--archive', str(output / 'product_full')]
        client = transport.StdioClient(command, output, output / 'mcp', time.perf_counter_ns() + 30_000_000_000)
        initial = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'assembly-fixture', 'version': '1'}}})
        identity = initial['result']['_meta']['human_eye']
        require(identity['source_sha256'] == SOURCE_SHA and identity['source_kind'] == 'installed_distribution',
                'installed_product_identity_required')
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'})
        observe = next(row for row in listing['result']['tools'] if row['name'] == 'human_eye_scene_observe')
        require(observe == read(NS / 'inputs/PRODUCT_SCHEMA.json'), 'registered_product_schema_changed')
        arguments = {'query': {'mode': 'task', **task}, 'include_image': False}
        response = client.call({'jsonrpc': '2.0', 'id': 'synthetic-task', 'method': 'tools/call',
                                'params': {'name': observe['name'], 'arguments': arguments}})
        public = response['result']
        require(not public['isError'] and [row['type'] for row in public['content']] == ['text'],
                'synthetic_task_requires_one_text_success')
        facts = json.loads(public['content'][0]['text'])
        require(facts['schema_version'] == 'task-query-set-v1' and facts['status'] == 'observed',
                'installed_task_set_public_result_required')
        require([row['name'] for row in facts['binding']['objects']] == [row['name'] for row in selectors]
                and [row['candidate_index'] for row in facts['pairs']] == [0, 1, 2],
                'public_task_set_selectors_changed')
        relations = [row['facts']['closed_solid_relation'] for row in facts['pairs']]
        states = [row['value'] for row in relations]
        require(states == ['separated', 'penetrating', 'separated'], 'synthetic_solid_relations_changed')
        require(relations[1]['certificate'] == 'transverse_boundary_interiors'
                and relations[1]['local_evidence']['type'] == 'transverse_triangle_crossing',
                'synthetic_transverse_penetration_certificate_missing')
        require([row['separation_gap']['value'] for row in facts['pairs']] == [1.0, None, 4.0]
                and all(row['facts']['surface_proximity']['witness_status'] == 'measured' for row in facts['pairs']),
                'synthetic_surface_gap_or_witness_missing')
        thread.join(timeout=2)
        require(thread is not None and 'wire' in result and 'fixture_error' not in result, 'fixture_capture_not_completed')
        counts = budget.snapshot()['counts']
        require(counts['all_raster_upper'] == counts['Blender_start_attempts'] == counts['consumer_admissions'] == 0,
                'synthetic_preflight_budget_counts_required')
        result.update(identity=identity, schema_sha256=sha(NS / 'inputs/PRODUCT_SCHEMA.json'),
                      public_reply=client.records[-1], public_schema=facts['schema_version'], budget_counts=counts,
                      public_image_blocks=0, passed=True)
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        try:
            if client is not None:
                closed = client.finish()
                result['public_MCP_close'] = closed
                result['passed'] &= closed['confirmed']
        finally:
            listener.close()
            if thread is not None:
                thread.join(timeout=2)
                result['passed'] &= not thread.is_alive()
            result['closed_ns'] = time.perf_counter_ns()
            save(output / 'PREFLIGHT.json', result)
    print(output / 'PREFLIGHT.json')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
