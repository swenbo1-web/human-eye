"""Expose the common raw tools and transparently proxy the installed P tool."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import threading


HERE = Path(__file__).resolve().parent
SOURCE_REGION = HERE.parent / 'm4_live_source_region_task_003'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_prior = load('_cross_scale_prior_image_bridge', SOURCE_REGION / 'bridge.py')
TOOL_LIMIT, MAX_FRAME, PRODUCT_TOOL = _prior.TOOL_LIMIT, _prior.MAX_FRAME, _prior.PRODUCT_TOOL
DISCOVERY = _prior.DISCOVERY
encoded, save, remaining, error_result = _prior.encoded, _prior.save, _prior.remaining, _prior.error_result
tool, text_result = _prior.tool, _prior.text_result
VIEWS = ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK']
TOOLS = [
    tool('execute_python', 'Run persistent ordinary Python. scene_data(selectors=None) returns source_ref, '
         'source and current objects with identity, visibility, vertices in world metres, and object-local triangles. '
         'np, Fraction, shapely, PIL and Image are available. cameras gives six target-to-eye directions. '
         'render_views(names,include_images=False,fresh=False) returns globally fitted frames. '
         'render_local(direction,target_world_m,view_span_m,include_image=False,fresh=False) returns one '
         '512px orthographic frame using the chosen direction, finite world target and full square width in metres. '
         'View directions are SCENE=(4,-4,3), TOP=(0,0,1), LEFT=(-1,0,1), RIGHT=(1,0,1), '
         'FRONT=(0,-1,1), BACK=(0,1,1). buffers[frame_ref] gives color, depth, owners and triangle_ids. '
         'Frame object_names and source_face_offsets map the zero-based owners and global triangle IDs. '
         'Pixel row/column origin is top-left with centres at integer index +0.5; background owner and triangle are -1. '
         'read_images([frame_ref,...]) attaches original cached PNGs. blender(code,timeout=30) reads current Blender. '
         'Keep arrays local and print compact facts and frame references. Variables persist between calls.',
         _prior.CODE, ['code']),
    copy.deepcopy(_prior.TOOLS[1]),
    tool('render_views', 'Fit any chosen registered directions to the whole current scene. '
         'Returns frame metadata, with original PNGs if include_images is true.',
         {'names': {'type': 'array', 'items': {'enum': VIEWS}, 'minItems': 1, 'maxItems': 6},
          'fresh': {'type': 'boolean', 'default': False}, 'include_images': {'type': 'boolean', 'default': False}}, ['names']),
    tool('render_local', 'Frame a model-chosen world target in a registered direction with a full square width '
         'in metres. All display-participating scene triangles remain in the depth test. Returns one frame '
         'with an optional PNG. A matching frame can be read by ref without a fresh raster.',
         {'direction': {'enum': VIEWS}, 'target_world_m': {'type': 'array', 'minItems': 3, 'maxItems': 3,
            'items': {'type': 'number'}}, 'view_span_m': {'type': 'number', 'exclusiveMinimum': 0},
          'include_image': {'type': 'boolean', 'default': False}, 'fresh': {'type': 'boolean', 'default': False}},
         ['direction', 'target_world_m', 'view_span_m']),
    copy.deepcopy(_prior.TOOLS[-1]),
]
TOOL_NAMES = {group: frozenset(row['name'] for row in TOOLS) | ({PRODUCT_TOOL} if group == 'P' else set())
              for group in ('N', 'P')}


class Session(_prior.Session):
    def __init__(self, runtime, config):
        super().__init__(runtime, config, None)
        self.namespace.pop('region')
        self.namespace['render_local'] = self.render_local

    def render_views(self, names, include_images=False, fresh=False):
        return _prior.COMMON.OrdinarySession.render_views(self, names, include_images, fresh)

    def render_local(self, direction, target_world_m, view_span_m, include_image=False, fresh=False):
        if type(include_image) is not bool:
            raise ValueError('include_image_must_be_boolean')
        with self.trusted():
            frame = self.runtime.render_local(direction, target_world_m, view_span_m, fresh=fresh)
        if include_image:
            self.attach_images([frame['ref']])
        return frame


class Owner(_prior.Owner):
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config, self.budget = runtime, config, budget
        self.group, self.label, self.phase = config['group'], config['label'], config['phase']
        if (self.label, self.group, self.phase) not in (('QN', 'N', 'qualification'),
                ('QP', 'P', 'qualification'), ('N1', 'N', 'formal'), ('P1', 'P', 'formal')):
            raise ValueError('registered_cross_scale_slot_required')
        self.deadline_ns = config['worker_deadline_ns']
        self.output = Path(config['output']).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.session = Session(runtime, config)
        self.tools = copy.deepcopy(TOOLS)
        if self.group == 'P':
            self.tools.append(copy.deepcopy(next(row for row in runtime.product_tools if row['name'] == PRODUCT_TOOL)))
        self.rows, self.protocol, self.protocol_errors, self.transport_errors = [], [], [], []
        self.listener = self.thread = None
        self.stop = threading.Event()
        save(self.output / 'TOOLS_SCHEMA.json', self.tools)
        self.publish()

    def handle(self, request, attempt=None):
        response = super().handle(request, attempt)
        if request.get('method') == 'initialize' and response is not None:
            response['result'].pop('instructions', None)
            response['result']['serverInfo']['name'] = 'm4-cross-scale-live-task-001'
        return response

    def product(self, arguments, folder):
        save(folder / 'PRODUCT_ARGUMENTS.json', arguments)
        before = len(self.runtime.public_requests)
        try:
            response = self.runtime.public_request(copy.deepcopy(arguments))
            save(folder / 'PRODUCT_RESPONSE.json', response)
        finally:
            for record in self.runtime.public_requests[before:]:
                if 'request' in record:
                    save(folder / 'PRODUCT_REQUEST.json', record['request'])
                if 'response' in record:
                    save(folder / 'PRODUCT_RESPONSE.json', record['response'])
                save(folder / 'PRODUCT_RECEIPT.json', {key: value for key, value in record.items()
                     if key not in ('request', 'response')})
        if response.get('error') is not None:
            raise RuntimeError(f'Installed product RPC error: {response["error"]}')
        return response['result']

    def dispatch(self, name, arguments, row, folder):
        if name not in TOOL_NAMES[self.group]:
            raise ValueError('tool_unavailable_in_this_slot')
        if name == PRODUCT_TOOL:
            return self.product(arguments, folder)
        self.session.attached_refs = []
        if name in ('execute_python', 'execute_blender_code'):
            if set(arguments) != {'code'} or type(arguments['code']) is not str:
                raise ValueError('code_string_required')
            run = self.session.execute if name == 'execute_python' else self.session.blender
            value = run(arguments['code'])
            result = text_result(value, value.get('error') is not None)
        elif name == 'render_views':
            if set(arguments) - {'names', 'fresh', 'include_images'} or 'names' not in arguments:
                raise ValueError('render_views_arguments')
            result = text_result({'frames': self.session.render_views(**arguments)})
        elif name == 'render_local':
            required = {'direction', 'target_world_m', 'view_span_m'}
            if not required <= set(arguments) or set(arguments) - required - {'include_image', 'fresh'}:
                raise ValueError('render_local_arguments')
            result = text_result({'frame': self.session.render_local(**arguments)})
        else:
            if set(arguments) != {'refs'}:
                raise ValueError('read_images_arguments')
            self.session.attach_images(arguments['refs'])
            result = {'content': [], 'isError': False}
        result['content'].extend(self.images(self.session.attached_refs, row))
        return result
