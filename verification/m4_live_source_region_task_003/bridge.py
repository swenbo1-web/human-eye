"""Expose the slot's ordinary read-only tools and the installed P entry."""

import ast
import base64
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
BRIEF_SCHEMA = 'source-region-brief-v2'
OBJECT_NAME = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
DISCOVERY = {'resources/list': {'resources': []},
             'resources/templates/list': {'resourceTemplates': []}}
P_ENTRY = ('For your first business call, use human_eye_scene_observe with '
           '{"include_image":true,"query":{"mode":"source_region",'
           '"region":{"object":{"name":"' + OBJECT_NAME + '"},"source_triangle_indices":[0]},'
           '"reference":{"name":"Cube"},"requested_facts":["surface_proximity"]}} '
           'and omit the top-level response_detail field. In this query, [0] represents the bound ARM_REGION array. '
           'After the first call, request any needed detail or use the ordinary tools.')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COMMON = load('_m4_live_ordinary_session', VERIFICATION / 'm5_harness_recovery_001/native_tools.py')
IMAGES = load('_m4_live_image_content', VERIFICATION / 'm4_active_coverage_consumption_001/image_content.py')
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
         'region holds object, object_id, reference and source_triangle_ids. '
         'scene_data(selectors=None) accepts object names and returns source_ref and current objects. '
         'Each object has name, object_id, visible_get, vertices in world metres and object-local triangles. '
         'cameras gives the fixed SCENE device. render_views(["SCENE"],include_images=False,fresh=False) returns frame metadata. '
         'buffers[frame_ref] holds color, depth, owners and triangle_ids. Top-left origin, zero-based pixels, background -1. '
         'Frame object_names, object_ids and source_face_offsets give the owner and global triangle mapping. '
         'read_images([frame_ref]) attaches a cached PNG. np, shapely, PIL, Image and scratch are available. '
         'blender(code,timeout=30) runs read-only ordinary Python in the current Blender. Use render_views for frames. '
         'Keep large geometry and pixel arrays in the persistent session and compute with familiar math libraries. '
         'Print only concise numbers, source witnesses and frame references needed by the task.', CODE, ['code']),
    tool('execute_blender_code', 'Run persistent read-only ordinary Python in the current Blender with bpy, mathutils and NumPy. '
         'Returns stdout, stderr and errors.', CODE, ['code']),
    tool('render_views', 'Get the current SCENE frame metadata and optionally attach its PNG. Reuses a current matching frame unless fresh is true.',
         {'names': {'type': 'array', 'items': {'const': 'SCENE'}, 'minItems': 1, 'maxItems': 1},
          'fresh': {'type': 'boolean', 'default': False}, 'include_images': {'type': 'boolean', 'default': False}}, ['names']),
    tool('read_images', 'Attach a cached current-slot PNG by frame ref.',
         {'refs': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 6}}, ['refs']),
]
TOOL_NAMES = {group: frozenset(row['name'] for row in TOOLS) | ({PRODUCT_TOOL} if group == 'P' else set())
              for group in ('N', 'P')}


def bound_region(path, expected_sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('bound_ARM_REGION_changed')
    region = json.loads(raw)
    ids = region['source_triangle_ids']
    if (region['object'] != {'name': OBJECT_NAME} or type(ids) is not list or len(ids) != 748
            or any(type(value) is not int or value < 0 for value in ids) or len(set(ids)) != len(ids)):
        raise ValueError('bound_ARM_REGION_source_indices')
    return region


class Session(COMMON.OrdinarySession):
    def __init__(self, runtime, config, region):
        super().__init__(runtime, config)
        for key in ('observe', 'task', 'last_observation_json', 'last_task_json', 'last_product_is_error'):
            self.namespace.pop(key)
        self.namespace['region'] = copy.deepcopy(region)

    def render_views(self, names, include_images=False, fresh=False):
        if names not in (['SCENE'], ('SCENE',)):
            raise ValueError('SCENE_is_the_registered_view')
        return super().render_views(names, include_images, fresh)

    def blender(self, code, timeout=30):
        if type(code) is str:
            tree = COMMON.validate_code(code)
            for node in ast.walk(tree):
                blender_operator = (isinstance(node, ast.Attribute) and node.attr == 'ops') or (
                    isinstance(node, ast.ImportFrom) and node.module == 'bpy'
                    and any(alias.name == 'ops' for alias in node.names))
                if blender_operator:
                    self.audit.append({'event': 'native_operator_refused', 'at_ns': time.perf_counter_ns()})
                    raise PermissionError('use_the_read_only_Blender_API_and_SCENE_frame_device')
        return super().blender(code, timeout)


def error_result(error):
    return {'content': [{'type': 'text', 'text': f'{type(error).__name__}: {error}'}], 'isError': True}


def text_result(value, is_error=False):
    return {'content': [{'type': 'text', 'text': encoded(value).decode('utf8')}], 'isError': is_error}


def content_metrics(content):
    text_bytes = 0
    images = []
    for position, block in enumerate(content):
        if block['type'] == 'text':
            text_bytes += len(block['text'].encode('utf8'))
        elif block['type'] == 'image' and block['mimeType'] == 'image/png':
            raw = base64.b64decode(block['data'], validate=True)
            images.append({'position': position, 'PNG_bytes': len(raw), 'base64_chars': len(block['data']),
                           'PNG_sha256': hashlib.sha256(raw).hexdigest()})
        else:
            raise ValueError('expected_MCP_text_or_PNG_content')
    return {'text_UTF8_bytes': text_bytes, 'image_blocks': len(images), 'images': images,
            'PNG_bytes': sum(row['PNG_bytes'] for row in images)}


class Owner:
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config, self.budget = runtime, config, budget
        self.group, self.label, self.phase = config['group'], config['label'], config['phase']
        if (self.label, self.group) not in (('N1', 'N'), ('P1', 'P')) or self.phase != 'formal':
            raise ValueError('registered_live_slot')
        self.deadline_ns = config['worker_deadline_ns']
        self.output = Path(config['output']).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.region = bound_region(config['region_path'], config['region_sha256'])
        self.session = Session(runtime, config, self.region)
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

    def images(self, refs, row):
        result = []
        for ref in refs:
            spec, directory = self.runtime.image_specification(ref)
            try:
                image, receipt = IMAGES.image_content(spec, directory, self.deadline_ns)
            except IMAGES.ImageContentError as error:
                row['image_attachments'].append(error.receipt)
                raise
            row['image_attachments'].append(receipt)
            result.extend([{'type': 'text', 'text': f'{ref} ({spec["width"]}x{spec["height"]}, image/png)'}, image])
        return result

    def product(self, arguments, folder):
        query = arguments.get('query', {})
        supplied_region = query.get('region', {}) if type(query) is dict else {}
        standard_region = (type(query) is dict and query.get('mode') == 'source_region'
                           and type(supplied_region) is dict
                           and supplied_region.get('object') == self.region['object'])
        bound_selection = self.region['source_triangle_ids']
        supplied_ids = supplied_region.get('source_triangle_indices') if type(supplied_region) is dict else None
        integer_ids = type(supplied_ids) is list and all(type(value) is int for value in supplied_ids)
        bound_marker = integer_ids and supplied_ids == [0]
        if not self.product_called and not (standard_region and integer_ids and (bound_marker or supplied_ids == bound_selection)
                and query.get('reference') == self.region['reference'] and query.get('requested_facts') == ['surface_proximity']
                and arguments.get('include_image', True) is True):
            raise ValueError('first_P_call_requires_the_bound_standard_source_region_query')
        downstream = copy.deepcopy(arguments)
        if standard_region and bound_marker:
            downstream['query']['region']['source_triangle_indices'] = bound_selection.copy()
        save(folder / 'PRODUCT_ARGUMENTS.json', downstream)
        detail_path = folder / 'PRODUCT_DETAIL.json'
        detail = {'request_response_detail_present': 'response_detail' in arguments,
                  'requested_response_detail': arguments.get('response_detail'),
                  'forwarded_response_detail_present': 'response_detail' in downstream,
                  'forwarded_response_detail': downstream.get('response_detail'),
                  'include_image_present': 'include_image' in arguments,
                  'requested_include_image': arguments.get('include_image'),
                  'bound_marker_expanded': standard_region and bound_marker,
                  'returned_schema': None, 'returned_is_error': None, 'returned_images': None,
                  'default_brief_v2_returned': False}
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
            if type(value) is dict and value.get('result_kind') == 'source_region':
                detail['returned_schema'] = value.get('schema')
                break
        detail['default_brief_v2_returned'] = (not detail['request_response_detail_present']
            and not detail['forwarded_response_detail_present'] and detail['returned_is_error'] is False
            and detail['returned_schema'] == BRIEF_SCHEMA)
        save(detail_path, detail)
        return result

    def dispatch(self, name, arguments, row, folder):
        if name not in TOOL_NAMES[self.group]:
            raise ValueError('tool_unavailable_in_this_slot')
        if self.group == 'P' and not self.product_called and name != PRODUCT_TOOL:
            raise ValueError('first_P_call_requires_human_eye_scene_observe_source_region')
        self.session.attached_refs = []
        if name in ('execute_python', 'execute_blender_code'):
            if set(arguments) != {'code'} or type(arguments['code']) is not str:
                raise ValueError('code_string_required')
            value = (self.session.execute(arguments['code']) if name == 'execute_python'
                     else self.session.blender(arguments['code']))
            result = text_result(value, value.get('error') is not None)
        elif name == 'render_views':
            if set(arguments) - {'names', 'fresh', 'include_images'} or 'names' not in arguments:
                raise ValueError('render_views_arguments')
            frames = self.session.render_views(arguments['names'], arguments.get('include_images', False),
                                              arguments.get('fresh', False))
            result = text_result({'frames': frames})
        elif name == 'read_images':
            if set(arguments) != {'refs'}:
                raise ValueError('read_images_arguments')
            self.session.attach_images(arguments['refs'])
            result = {'content': [], 'isError': False}
        else:
            return self.product(arguments, folder)
        result['content'].extend(self.images(self.session.attached_refs, row))
        return result

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
            result = self.dispatch(name, params.get('arguments', {}), row, folder)
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
                      'serverInfo': {'name': 'm4-live-source-region-task-003', 'version': '1'}}
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
