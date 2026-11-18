"""Expose the slot's ordinary read-only tools and the installed P entry."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import time


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parent
TOOL_LIMIT = 12
MAX_FRAME = 24 * 1024 * 1024
PRODUCT_TOOL = 'human_eye_scene_observe'
SERVER_NAME = 'm4-live-assembly-relation-task-001'
ASSEMBLY = {'target': {'name': 'Object_01'},
            'candidates': [{'name': name} for name in ('Object_02', 'Object_03', 'Object_04')],
            'requested_facts': ['closed_solid_relation', 'surface_proximity']}
DISCOVERY = {'resources/list': {'resources': []},
             'resources/templates/list': {'resourceTemplates': []}}


def task_arguments(assembly):
    return {'include_image': False, 'query': {'mode': 'task', **copy.deepcopy(assembly)}}


P_ENTRY = ('For your first business call, use human_eye_scene_observe with '
           + json.dumps(task_arguments(ASSEMBLY), separators=(',', ':'))
           + '. After that call, use the ordinary tools or request any needed text-only product evidence.')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COMMON = load('_m4_live_ordinary_session', VERIFICATION / 'm5_harness_recovery_001/native_tools.py')
encoded = COMMON.encoded


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.next')
    temporary.write_bytes(encoded(value) + b'\n')
    temporary.replace(path)


def remaining(deadline_ns):
    seconds = (deadline_ns - time.perf_counter_ns()) / 1e9
    if seconds <= 0:
        raise TimeoutError('original_consumer_deadline')
    return seconds


def tool(name, description, properties, required):
    return {'name': name, 'description': description, 'inputSchema': {'type': 'object',
            'properties': properties, 'required': required, 'additionalProperties': False}}


CODE = {'code': {'type': 'string'}}
TOOLS = [
    tool('execute_python',
         'Run persistent ordinary Python and return stdout, stderr and errors. '
         'scene_data(selectors=None) accepts a list of object names and returns source, source_ref and current evaluated objects. '
         'Each object has name, object_id, instance_id, mesh_sha256, vertices in world metres and zero-based object-local triangles. '
         'np, Fraction, shapely and scratch are available. '
         'blender(code,timeout=30) runs ordinary read-only Python in the current Blender. '
         'Keep mesh arrays in the persistent session, compute locally, and print only the facts and source witnesses needed for the answer.',
         CODE, ['code']),
    tool('execute_blender_code', 'Run persistent ordinary read-only Python in the current Blender with bpy, mathutils and NumPy. '
         'Returns stdout, stderr and errors. Keep arrays in the session and print only the facts and source witnesses needed for the answer.',
         CODE, ['code']),
]
TOOL_NAMES = {group: frozenset(row['name'] for row in TOOLS) | ({PRODUCT_TOOL} if group == 'P' else set())
              for group in ('N', 'P')}


def bound_assembly(path, expected_sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('bound_assembly_changed')
    value = json.loads(raw)
    if value != ASSEMBLY:
        raise ValueError('registered_assembly_selectors_and_facts')
    return value


class Session(COMMON.OrdinarySession):
    def __init__(self, runtime, config):
        super().__init__(runtime, config)
        for key in ('observe', 'task', 'last_observation_json', 'last_task_json', 'last_product_is_error',
                    'cameras', 'buffers', 'render_views', 'read_images', 'attach_images'):
            self.namespace.pop(key)

    def blender(self, code, timeout=30):
        if type(code) is str:
            tree = COMMON.validate_code(code)
            for node in ast.walk(tree):
                blender_operator = (isinstance(node, ast.Attribute) and node.attr == 'ops') or (
                    isinstance(node, ast.ImportFrom) and node.module == 'bpy'
                    and any(alias.name == 'ops' for alias in node.names))
                if blender_operator:
                    self.audit.append({'event': 'native_operator_refused', 'at_ns': time.perf_counter_ns()})
                    raise PermissionError('use_the_read_only_Blender_API')
        return super().blender(code, timeout)


def error_result(error):
    return {'content': [{'type': 'text', 'text': f'{type(error).__name__}: {error}'}], 'isError': True}


def text_result(value, is_error=False):
    return {'content': [{'type': 'text', 'text': encoded(value).decode('utf8')}], 'isError': is_error}


def content_metrics(content):
    if any(block['type'] != 'text' for block in content):
        raise ValueError('expected_text_only_MCP_content')
    return {'text_UTF8_bytes': sum(len(block['text'].encode('utf8')) for block in content),
            'image_blocks': 0, 'images': [], 'PNG_bytes': 0}


class Owner:
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config, self.budget = runtime, config, budget
        self.group, self.label, self.phase = config['group'], config['label'], config['phase']
        if (self.label, self.group) not in (('N1', 'N'), ('P1', 'P')) or self.phase != 'formal':
            raise ValueError('registered_live_slot')
        self.deadline_ns = config['worker_deadline_ns']
        self.output = Path(config['output']).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.assembly = bound_assembly(config['assembly_path'], config['assembly_sha256'])
        self.session = Session(runtime, config)
        self.tools = copy.deepcopy(TOOLS)
        if self.group == 'P':
            registered = next(row for row in runtime.product_tools if row['name'] == PRODUCT_TOOL)
            entry = copy.deepcopy(registered)
            entry['description'] = P_ENTRY + ' ' + registered['description']
            self.tools.append(entry)
        self.rows, self.protocol, self.protocol_errors, self.transport_errors = [], [], [], []
        self.product_called = False
        self.listener = self.thread = None
        self.stop = threading.Event()
        save(self.output / 'TOOLS_SCHEMA.json', self.tools)
        self.publish()

    def publish(self):
        last = self.rows[-1]['attempt'] if self.rows else 0
        save(self.output / 'TOOLS.json', {'calls': last, 'attempts': last, 'tools': self.rows})
        save(self.output / 'BRIDGE_RESULT.json', {'calls': self.rows, 'protocol': self.protocol,
            'protocol_errors': self.protocol_errors, 'transport_errors': self.transport_errors,
            'consumer_audit': self.session.audit,
            'public_text_bytes': sum(row.get('content_metrics', {}).get('text_UTF8_bytes', 0) for row in self.rows)})

    def product(self, arguments, folder):
        query = arguments.get('query', {})
        initial = not self.product_called
        if initial and arguments != task_arguments(self.assembly):
            raise ValueError('first_P_call_requires_the_registered_standard_assembly_task_query')
        if arguments.get('include_image') is not False:
            raise ValueError('explicit_include_image_false_required')
        downstream = copy.deepcopy(arguments)
        save(folder / 'PRODUCT_ARGUMENTS.json', downstream)
        detail_path = folder / 'PRODUCT_DETAIL.json'
        detail = {'initial_product_call': initial, 'query_mode': query.get('mode') if type(query) is dict else None,
                  'request_response_detail_present': 'response_detail' in arguments,
                  'requested_response_detail': arguments.get('response_detail'),
                  'forwarded_response_detail_present': 'response_detail' in downstream,
                  'forwarded_response_detail': downstream.get('response_detail'),
                  'requested_include_image': arguments['include_image'],
                  'forwarded_arguments_unchanged': downstream == arguments,
                  'returned_result_kind': None, 'returned_schema': None, 'returned_status': None,
                  'returned_is_error': None, 'returned_images': None}
        save(detail_path, detail)
        self.product_called = True
        public_requests = getattr(self.runtime, 'public_requests', ())
        before = len(public_requests)
        try:
            response = self.runtime.public_request(downstream)
            save(folder / 'PRODUCT_RESPONSE.json', response)
        finally:
            for record in public_requests[before:]:
                if 'request' in record:
                    save(folder / 'PRODUCT_REQUEST.json', record['request'])
                if 'response' in record:
                    save(folder / 'PRODUCT_RESPONSE.json', record['response'])
                save(folder / 'PRODUCT_RECEIPT.json', {key: value for key, value in record.items()
                                                     if key not in ('request', 'response')})
        if response.get('error') is not None:
            raise RuntimeError(f'Installed product RPC error: {response["error"]}')
        result = response['result'] if 'jsonrpc' in response else response
        blocks = result['content']
        detail['returned_is_error'] = result['isError']
        detail['returned_images'] = sum(block.get('type') == 'image' for block in blocks)
        for block in blocks:
            if block.get('type') != 'text':
                continue
            try:
                value = json.loads(block['text'])
            except (TypeError, ValueError):
                continue
            if type(value) is dict and 'result_kind' in value:
                detail.update(returned_result_kind=value['result_kind'],
                              returned_schema=value.get('schema_version', value.get('schema')),
                              returned_status=value.get('status'))
                break
        save(detail_path, detail)
        return result

    def dispatch(self, name, arguments, folder):
        if name not in TOOL_NAMES[self.group]:
            raise ValueError('tool_unavailable_in_this_slot')
        if self.group == 'P' and not self.product_called and name != PRODUCT_TOOL:
            raise ValueError('first_P_call_requires_human_eye_scene_observe_task')
        if name == PRODUCT_TOOL:
            return self.product(arguments, folder)
        if set(arguments) != {'code'} or type(arguments['code']) is not str:
            raise ValueError('code_string_required')
        execute = self.session.execute if name == 'execute_python' else self.session.blender
        value = execute(arguments['code'])
        return text_result(value, value.get('error') is not None)

    def call(self, request, attempt):
        if type(attempt) is not int or attempt <= (self.rows[-1]['attempt'] if self.rows else 0):
            raise ValueError('monotonic_tool_attempt_required')
        folder = self.output / f'tool_{attempt:02d}'
        folder.mkdir()
        params = request.get('params')
        name = params.get('name') if type(params) is dict else None
        row = {'attempt': attempt, 'name': name, 'started_ns': time.perf_counter_ns(),
               'RPC_id': request.get('id'), 'image_attachments': [], 'status': 'received'}
        save(folder / 'REQUEST.json', request)
        self.rows.append(row)
        self.publish()
        try:
            remaining(self.deadline_ns)
            if attempt > TOOL_LIMIT:
                raise ValueError('business_tool_attempt_budget_exhausted')
            if self.budget is not None:
                self.budget.reserve('business_tool', self.label, self.phase, 1)
            if (type(params) is not dict or set(params) - {'name', 'arguments', '_meta'}
                    or type(name) is not str or type(params.get('arguments', {})) is not dict
                    or ('_meta' in params and type(params['_meta']) is not dict)):
                raise ValueError('MCP_tool_params_required')
            result = self.dispatch(name, params.get('arguments', {}), folder)
            row['content_metrics'] = content_metrics(result['content'])
            if len(encoded(result)) > MAX_FRAME - 1024:
                raise ValueError('MCP_response_frame_limit; print compact results')
            remaining(self.deadline_ns)
        except Exception as error:
            row['error'] = {'type': type(error).__name__, 'message': str(error)}
            if 'content_metrics' in row:
                row['undelivered_content_metrics'] = row.pop('content_metrics')
            result = error_result(error)
            row['content_metrics'] = content_metrics(result['content'])
        response = {'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}
        row.update(is_error=result['isError'], status='tool_error' if result['isError'] else 'returned',
                   response_ready_ns=time.perf_counter_ns(), response_bytes=len(encoded(response)) + 1)
        save(folder / 'RESPONSE.json', response)
        row['closed_ns'] = time.perf_counter_ns()
        save(folder / 'RECEIPT.json', row)
        self.publish()
        return response

    def handle(self, request, attempt=None):
        method = request.get('method')
        if method == 'tools/call':
            return self.call(request, attempt)
        if 'id' not in request:
            return None
        if method == 'initialize':
            version = request.get('params', {}).get('protocolVersion', '2025-03-26')
            result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                      'serverInfo': {'name': SERVER_NAME, 'version': '1'}}
            if self.group == 'P':
                result['instructions'] = P_ENTRY
        elif method == 'tools/list':
            result = {'tools': self.tools}
        elif method == 'ping':
            result = {}
        elif method in DISCOVERY:
            result = DISCOVERY[method]
        else:
            self.protocol_errors.append({'method': method, 'reason': 'unsupported_MCP_method'})
            return {'jsonrpc': '2.0', 'id': request['id'],
                    'error': {'code': -32601, 'message': 'Method not found'}}
        return {'jsonrpc': '2.0', 'id': request['id'], 'result': result}

    def start(self, endpoint_path):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(2)
        self.listener.settimeout(.2)
        self.thread = threading.Thread(target=self.serve, name='m4-live-slot-mcp', daemon=True)
        self.thread.start()
        save(endpoint_path, {'host': '127.0.0.1', 'port': self.listener.getsockname()[1],
                            'chain_deadline_ns': self.deadline_ns})
        return str(Path(endpoint_path).resolve())

    def serve(self):
        while not self.stop.is_set() and time.perf_counter_ns() < self.deadline_ns:
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    raise
                break
            row = {'sequence': len(self.protocol) + 1, 'started_ns': time.perf_counter_ns(),
                   'send_confirmed': False}
            folder = self.output / f'rpc_{row["sequence"]:03d}'
            folder.mkdir()
            raw, payload = bytearray(), None
            with connection:
                try:
                    while True:
                        connection.settimeout(remaining(self.deadline_ns))
                        block = connection.recv(65536)
                        if not block:
                            break
                        raw.extend(block)
                        if len(raw) > MAX_FRAME:
                            raise ValueError('MCP_frame_limit')
                    envelope = json.loads(raw)
                    if envelope['operation'] != 'attached_mcp' or envelope['args']['kind'] != 'native':
                        raise ValueError('attached_MCP_operation')
                    message = envelope['args']['message']
                    row.update(method=message.get('method'), RPC_id=message.get('id'),
                               attempt=envelope['args'].get('attempt'))
                    (folder / 'TCP_TX.bin').write_bytes(raw)
                    result = self.handle(message, row['attempt'])
                    payload = encoded({'request_id': envelope['request_id'], 'ok': True, 'result': result}) + b'\n'
                    if len(payload) > MAX_FRAME:
                        raise ValueError('MCP_frame_limit')
                    (folder / 'TCP_RX.bin').write_bytes(payload)
                    connection.settimeout(remaining(self.deadline_ns))
                    connection.sendall(payload)
                    row['send_confirmed'] = True
                except Exception as error:
                    row['error'] = {'type': type(error).__name__, 'message': str(error)}
                    self.transport_errors.append({'sequence': row['sequence'], **row['error']})
                    if not (folder / 'TCP_TX.bin').exists():
                        (folder / 'TCP_TX.bin').write_bytes(raw)
            row.update(closed_ns=time.perf_counter_ns(), request_bytes=len(raw),
                       response_bytes=len(payload) if payload is not None else None)
            self.protocol.append(row)
            self.publish()

    def close(self):
        self.stop.set()
        if self.listener is not None:
            self.listener.close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        confirmed = self.thread is None or not self.thread.is_alive()
        value = {'confirmed': confirmed, 'closed_ns': time.perf_counter_ns(),
                 'errors': self.protocol_errors, 'transport_errors': self.transport_errors,
                 'scope': 'Owner listener and serving thread'}
        if confirmed:
            self.publish()
            save(self.output / 'CLOSE.json', value)
        return value
