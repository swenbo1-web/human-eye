"""Shared read-only tools and same-slot MCP wire for the natural consumers."""
import ast
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
from pathlib import Path
import socket
import threading
import time


PRODUCT = 'human_eye_scene_observe'
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
MAX_CALLS = 8
MAX_RASTERS = 4
DEADLINE_MS = 450_000
MAX_LINE = 32 * 1024 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def require(ok, code):
    if not ok:
        raise ValueError(code)


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        return {'path': str(path), 'bytes': path.stat().st_size,
                'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def write(path, value):
    with Path(path).open('xb') as out:
        out.write(encode(value) + b'\n')


def append(path, value):
    with Path(path).open('ab') as out:
        out.write(encode(value) + b'\n')


def tool(name, description, properties, required=()):
    return {'name': name, 'description': description, 'inputSchema': {
        'type': 'object', 'properties': properties, 'required': list(required),
        'additionalProperties': False}}


TOOLS = [
    tool('read_scene', 'Read the current Blender evaluated world-metre vertices and zero-based object-local '
         'triangle rows, with object and capture identities. Omit objects to read the current scene.',
         {'objects': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'uniqueItems': True}}),
    tool('execute_python', 'Run persistent local numeric Python, returning stdout. Use scene_data() for current '
         'Blender geometry and pixels(ref) for an existing frame. Modules math, numpy, itertools and fractions '
         'are available for geometry computation. Frame pixels are zero-based row, column from the top left; '
         'owners and triangle_ids are the object index and scene source triangle index. '
         'Use frame source_face_offsets to recover each object-local triangle row.',
         {'code': {'type': 'string', 'maxLength': 12000}}, ('code',)),
    tool('render_view', 'Render a current Blender view with full current occluders. Provide a current object '
         'name and optionally its zero-based source_triangle_indices to control framing. Returns the original '
         'PNG, path, capture binding and verified target samples with zero-based top-left row, column.',
         {'object': {'type': 'string'}, 'view': {'type': 'string', 'enum': list(VIEWS)},
          'source_triangle_indices': {'type': 'array', 'items': {'type': 'integer', 'minimum': 0},
                                      'minItems': 1, 'uniqueItems': True}}, ('object', 'view')),
    tool('read_images', 'Return an original PNG and its current local path for a previously delivered exact frame ref.',
         {'refs': {'type': 'array', 'minItems': 1, 'maxItems': 4, 'uniqueItems': True,
                   'items': {'type': 'string'}}}, ('refs',)),
]

NUMPY_ATTRS = frozenset('array arange asarray all any amin amax argmin argmax clip concatenate cross dot einsum '
                       'flatnonzero isfinite isin maximum minimum nonzero stack sum sqrt unique where linalg '
                       'norm float64 int64 mean eye zeros ones sort prod abs round transpose'.split())
MATH_ATTRS = frozenset('acos asin atan2 ceil cos dist floor hypot inf isfinite pi sin sqrt tan'.split())
DATA_ATTRS = frozenset('shape T size dtype tolist item min max sum mean nonzero ravel copy astype '
                      'reshape transpose all any keys values items get add append extend'.split())
COMPUTE_ATTRS = NUMPY_ATTRS | MATH_ATTRS | DATA_ATTRS | {'Fraction', 'combinations', 'product'}
COMPUTE_NODES = frozenset(('Module Expr Constant Name Load Store Del List Tuple Dict Set Subscript Slice '
                           'Assign AugAssign For If IfExp Return Break Continue Pass Compare Eq NotEq Lt LtE '
                           'Gt GtE In NotIn Is IsNot BinOp Add Sub Mult Div FloorDiv Mod Pow MatMult BitAnd '
                           'BitOr BitXor UnaryOp USub UAdd Not Invert BoolOp And Or Call keyword Attribute '
                           'FunctionDef arguments arg Lambda ListComp SetComp DictComp GeneratorExp comprehension '
                           'Import ImportFrom alias').split())
COMPUTE_BUILTINS = ('abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter', 'float', 'int', 'len', 'list',
                    'map', 'max', 'min', 'print', 'range', 'reversed', 'round', 'set', 'sorted', 'str', 'sum',
                    'tuple', 'zip')


class RasterLimit(ValueError):
    """The current consumer spent its four actual raster reservations."""


class Bridge:
    def __init__(self, folder, host, service, product_server, deadline_ns):
        self.folder = folder
        self.host = host
        self.service = service
        self.product_server = product_server
        self.deadline_ns = deadline_ns
        self.biz = 0
        self.rasters = []
        self.frames = {}
        self.advertised = {}
        self.ordinal = 0
        self.ordinal_source = 'ordinary'
        self.recorded = []
        self.prepare_namespace()
        self.wire = folder / 'wire'
        self.wire.mkdir()
        self.listener = None
        self.thread = None
        self.error = None
        self.eof = False

    def check(self):
        require(time.perf_counter_ns() < self.deadline_ns, 'absolute_task_deadline')

    def prepare_namespace(self):
        import builtins
        import fractions
        import itertools
        import numpy as np
        self.numeric_modules = {'math': math, 'numpy': np, 'itertools': itertools, 'fractions': fractions}
        values = {name: getattr(builtins, name) for name in COMPUTE_BUILTINS}
        self.namespace = {'__builtins__': {**values, '__import__': builtins.__import__},
                          'math': math, 'np': np, 'scene_data': self.scene_data, 'pixels': self.pixels}

    def scene_data(self, objects=None):
        self.check()
        current = self.host.capture_scene()
        names = [mesh['name'] for mesh in current['meshes']]
        if objects is not None:
            require(type(objects) in (list, tuple) and bool(objects) and len(set(objects)) == len(objects)
                    and all(type(name) is str and names.count(name) == 1 for name in objects),
                    'unique_current_object_names_required')
        selected = [dict(mesh, object_index=i, instance_id=current['host_identity']['object_instances'][mesh['object_id']])
                    for i, mesh in enumerate(current['meshes']) if objects is None or mesh['name'] in objects]
        return {'objects': selected, 'unit': 'm', 'coordinate_frame': 'world',
                'capture_state': current['capture_state'], 'revision': current['revision']}

    def pixels(self, ref):
        import numpy as np
        frame = self.advertised[ref]
        with np.load(frame['arrays_path'], allow_pickle=False) as data:
            values = {key: data[key].copy() for key in ('depth', 'owners', 'triangle_ids', 'face_patch_offsets')}
        values['source_face_offsets'] = values['face_patch_offsets']
        return values

    def compute(self, code):
        require(type(code) is str and 0 < len(code) <= 12000, 'bounded_numeric_code_required')
        node = ast.parse(code, mode='exec')
        for part in ast.walk(node):
            require(type(part).__name__ in COMPUTE_NODES, 'unsupported_numeric_syntax')
            if isinstance(part, ast.Attribute):
                require(part.attr in COMPUTE_ATTRS and isinstance(part.ctx, ast.Load),
                        'unsupported_numeric_attribute')
            if isinstance(part, ast.Import):
                require(all(alias.name in self.numeric_modules and not (alias.asname or '').startswith('_')
                            for alias in part.names), 'only_registered_numeric_imports')
            if isinstance(part, ast.ImportFrom):
                require(part.level == 0 and part.module in self.numeric_modules
                        and all(alias.name in COMPUTE_ATTRS and not (alias.asname or '').startswith('_')
                                for alias in part.names), 'only_registered_numeric_imports')
            if isinstance(part, ast.Name):
                require(not part.id.startswith('_'), 'unsupported_numeric_name')
            if isinstance(part, (ast.arg, ast.FunctionDef)):
                name = part.arg if isinstance(part, ast.arg) else part.name
                require(not name.startswith('_'), 'unsupported_numeric_name')
        buffer = io.StringIO()
        ticks = 0

        def trace(*_):
            nonlocal ticks
            ticks += 1
            if ticks % 2048 == 0:
                self.check()
            if ticks > 1_000_000:
                raise ValueError('local_numeric_instruction_budget')
            return trace

        import sys
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with redirect_stdout(buffer):
                exec(compile(node, '<local-numeric-calculation>', 'exec'), self.namespace)
        finally:
            sys.settrace(previous)
        self.check()
        return {'stdout': buffer.getvalue()[:10000]}

    def bind_frame(self, frame, source, delivered=False):
        ref = frame['image_ref']
        image, arrays = [Path(frame[key]).resolve(strict=True) for key in ('image_path', 'arrays_path')]
        require(image.is_relative_to(self.folder) and arrays.is_relative_to(self.folder)
                and image.with_suffix('.npz') == arrays, 'frame_outside_owned_slot')
        require(pin(image)['sha256'] == frame['image_sha256']
                and pin(arrays)['sha256'] == frame['arrays_sha256'], 'current_frame_digest_mismatch')
        old = self.frames.setdefault(ref, frame)
        require(old['frame_identity'] == frame['frame_identity']
                and old['image_sha256'] == frame['image_sha256'], 'ambiguous_frame_ref')
        if delivered:
            self.advertised[ref] = frame
        append(self.folder / 'frames.jsonl', {'request_ordinal': self.ordinal, 'source': source,
                                               'delivered': delivered, **frame})

    def attached(self, frame, source):
        self.bind_frame(frame, source, delivered=True)
        return {'type': 'image', 'mimeType': 'image/png',
                'data': base64.b64encode(Path(frame['image_path']).read_bytes()).decode('ascii')}

    def render(self, name, view, indices=None):
        import numpy as np
        from human_eye_plugin.active_observation_host import source_binding
        from human_eye_plugin.source_region import _capture_region_frame, _region_image_store, display_state, prepare_region

        require(type(name) is str and view in VIEWS, 'registered_view_and_object_required')
        require(len(self.rasters) < MAX_RASTERS, 'actual_raster_budget_already_spent')
        current = self.host.capture_scene()
        index, = [i for i, mesh in enumerate(current['meshes']) if mesh['name'] == name]
        if indices is None:
            indices = list(range(len(current['meshes'][index]['faces'])))
        require(type(indices) is list and 1 <= len(indices) <= 4096 and len(set(indices)) == len(indices)
                and all(type(row) is int and 0 <= row < len(current['meshes'][index]['faces']) for row in indices),
                'current_unique_object_local_rows_required')
        prepared = prepare_region(current, {'region': {'object': {'name': name}, 'source_triangle_indices': sorted(indices)}},
                                  lambda _: self.check())
        display = display_state(current, source_binding(current))
        require(display['status'] == 'captured' and display['participation_mask'][index], 'target_not_currently_displayed')
        prepared.images = _region_image_store(prepared, self.folder / 'ordinary' / f'{self.ordinal:03d}', display)
        work = dict.fromkeys(('raster_attempts','raster_completed','PNG_bytes','NPZ_bytes','array_payload_bytes',
                              'local_verified_images','temporary_encoded_archive_bytes'), 0)
        frame, _ = _capture_region_frame(prepared, view, None, display, work, {}, None,
                                         lambda _: self.check(), sampled_pixel=True)
        with np.load(frame['arrays_path'], allow_pickle=False) as data:
            own = (data['owners'] == index) & np.isfinite(data['depth'])
            offset = int(data['face_patch_offsets'][index])
            frame['source_face_offsets'] = data['face_patch_offsets'].tolist()
            rows = []
            for face in sorted(indices):
                hits = np.flatnonzero(own & (data['triangle_ids'] == offset + face))
                if len(hits):
                    r, c = divmod(int(hits[0]), data['owners'].shape[1])
                    rows.append({'row': r, 'column': c, 'source_triangle_index': face, 'pixels': len(hits)})
        info = {k: frame[k] for k in ('image_ref', 'image_path', 'image_sha256', 'frame_identity',
                                     'view_name', 'source_face_offsets')}
        info.update(object_name=name, object_index=index, source_revision=current['revision'], sampled_pixels=rows)
        return info, self.attached(frame, 'ordinary')

    def capture_product(self, *args, **kwargs):
        value = self.original_observe(*args, **kwargs)
        if value.get('result_kind') in ('active_observation', 'source_region'):
            self.recorded.append(value)
        return value

    def product_call(self, message):
        self.ordinal_source = 'product'
        self.recorded = []
        try:
            result = self.product_server.handle_jsonrpc_message(message)
        finally:
            self.ordinal_source = 'ordinary'
        require(len(self.recorded) <= 1, 'multiple_producer_returns_in_one_public_request')
        if not self.recorded:
            return result
        value, = self.recorded
        write(self.folder / 'wire' / f'{self.ordinal:03d}' / 'PRODUCER.json', value)
        public_content = result.get('result', {}).get('content', [])
        public_hashes = [hashlib.sha256(base64.b64decode(x['data'], validate=True)).hexdigest()
                         for x in public_content if x['type'] == 'image' and x.get('mimeType') == 'image/png']
        delivered = {frame['image_ref']: frame for frame in value.get('frames', []) if frame['image_sha256'] in public_hashes}
        require(len(delivered) == len(public_hashes), 'product_MCP_native_block_without_bound_producer_frame')
        private = {frame['image_ref']: frame for frame in [*value.get('constructed_frames', []), *value.get('frames', [])]}
        for ref, frame in private.items():
            self.bind_frame(frame, 'product', ref in delivered)
        return result

    def answer(self, message):
        method = message['method']
        if 'id' not in message:
            return None
        mid = message['id']
        params = message.get('params', {})
        if method == 'initialize':
            return self.product_server.handle_jsonrpc_message(message)
        if method == 'tools/list':
            product = self.product_server.handle_jsonrpc_message(message)['result']['tools']
            catalogue = [*TOOLS, next(row for row in product if row['name'] == PRODUCT)]
            return {'jsonrpc': '2.0', 'id': mid, 'result': {'tools': catalogue}}
        if method in ('resources/list', 'resources/templates/list', 'prompts/list', 'ping'):
            keys = {'resources/list': 'resources', 'resources/templates/list': 'resourceTemplates', 'prompts/list': 'prompts'}
            return {'jsonrpc': '2.0', 'id': mid, 'result': {keys[method]: []} if method != 'ping' else {}}
        if method != 'tools/call':
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'unknown_method'}}
        require(self.biz < MAX_CALLS, 'business_request_budget_already_spent')
        self.biz += 1
        arguments = params['arguments']
        name = params['name']
        require(type(arguments) is dict, 'object_tool_arguments_required')
        self.check()
        if name == PRODUCT:
            return self.product_call(message)
        tool_schema = next(row['inputSchema'] for row in TOOLS if row['name'] == name)
        require(set(arguments) <= set(tool_schema['properties']) and set(tool_schema['required']) <= set(arguments),
                'unsupported_or_missing_ordinary_tool_argument')
        images = []
        if name == 'read_scene':
            body = self.scene_data(**arguments)
        elif name == 'execute_python':
            body = self.compute(**arguments)
        elif name == 'render_view':
            body, image = self.render(arguments['object'], arguments['view'], arguments.get('source_triangle_indices'))
            images = [image]
        else:
            refs = arguments['refs']
            require(type(refs) is list and 1 <= len(refs) <= 4 and len(set(refs)) == len(refs)
                    and all(type(ref) is str and ref in self.advertised for ref in refs),
                    'previously_delivered_same_slot_frame_refs_required')
            frames = [self.advertised[ref] for ref in refs]
            body = {'images': [{k: f[k] for k in ('image_ref', 'image_path', 'image_sha256', 'frame_identity')}
                               for f in frames]}
            images = [self.attached(frame, 'read_images') for frame in frames]
        return {'jsonrpc': '2.0', 'id': mid, 'result': {'isError': False,
            'content': [{'type': 'text', 'text': encode(body).decode('utf-8')}, *images]}}

    def dispatch(self, raw):
        raw_folder = self.wire / f'{self.ordinal:03d}'
        raw_folder.mkdir()
        (raw_folder / 'TX.bin').write_bytes(raw)
        message = json.loads(raw)
        start = time.perf_counter_ns()
        ran_before = len(self.rasters)
        biz_before = self.biz
        try:
            response = self.answer(message)
        except Exception as error:
            response = {'jsonrpc': '2.0', 'id': message.get('id'), 'result': {
                'isError': True, 'content': [{'type': 'text', 'text': encode({
                    'error': str(error), 'type': type(error).__name__}).decode('utf-8')}]}}
        closed = time.perf_counter_ns()
        outgoing = b'' if response is None else encode(response) + b'\n'
        (raw_folder / 'RX.bin').write_bytes(outgoing)
        append(self.wire / 'INDEX.jsonl', {'ordinal': self.ordinal, 'id': message.get('id'),
               'method': message['method'], 'tool': message.get('params', {}).get('name'),
               'started_ns': start, 'returned_ns': closed, 'business': self.biz - biz_before,
               'rasters': len(self.rasters) - ran_before, 'tx': pin(raw_folder / 'TX.bin'),
               'rx': pin(raw_folder / 'RX.bin')})
        return outgoing

    def install_raster_guard(self):
        from human_eye_plugin import active_observation_images as images
        self.images_module = images
        self.original_raster = images.rasterize_attention
        self.original_observe = self.service.observe

        def meter(*args, **kwargs):
            self.check()
            if len(self.rasters) >= MAX_RASTERS:
                raise RasterLimit('four_actual_rasters_already_spent')
            start = time.perf_counter_ns()
            try:
                result = self.original_raster(*args, **kwargs)
            except BaseException:
                self.rasters.append({'ordinal': self.ordinal, 'origin': self.ordinal_source,
                                     'started_ns': start, 'closed_ns': time.perf_counter_ns(), 'complete': False})
                raise
            self.rasters.append({'ordinal': self.ordinal, 'origin': self.ordinal_source,
                                 'started_ns': start, 'closed_ns': time.perf_counter_ns(), 'complete': True})
            return result

        self.service.observe = self.capture_product
        images.rasterize_attention = meter

    def serve(self, token):
        try:
            connection, _ = self.listener.accept()
            with connection:
                connection.settimeout(max(1, (self.deadline_ns - time.perf_counter_ns()) / 1e9 + 3))
                with connection.makefile('rwb', buffering=0) as transport:
                    require(transport.readline(300) == token.encode('ascii') + b'\n', 'invalid_local_client')
                    while raw := transport.readline(MAX_LINE + 1):
                        require(len(raw) <= MAX_LINE and raw.endswith(b'\n'), 'complete_bounded_MCP_line_required')
                        self.ordinal += 1
                        outgoing = self.dispatch(raw)
                        if outgoing:
                            connection.sendall(outgoing)
                    self.eof = True
        except BaseException as error:
            self.error = {'type': type(error).__name__, 'message': str(error)}

    def start(self, token):
        self.install_raster_guard()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(max(1, (self.deadline_ns - time.perf_counter_ns()) / 1e9 + 3))
        self.thread = threading.Thread(target=self.serve, args=(token,), name='owned-natural-mcp', daemon=True)
        self.thread.start()
        return self.listener.getsockname()[1]

    def finish(self):
        self.thread.join(6)
        self.listener.close()
        self.thread.join(1)
        if not self.thread.is_alive():
            self.images_module.rasterize_attention = self.original_raster
            self.service.observe = self.original_observe
        return {'transport_eof': self.eof, 'closed': not self.thread.is_alive(),
                'business': self.biz, 'rasters': self.rasters, 'error': self.error,
                'requests': self.ordinal, 'known_frames': len(self.frames), 'delivered_frames': len(self.advertised)}
