"""Arm-local data-only capability router. No engine/bpy imports or file access.

The three live names below are frozen from live_spatial_mcp.py and the actual
2026-10-30 tool catalog: discovery is an observation query, preview is a segment
with execute=false, and controlled single execution is human_eye_transform.
There are no invented preview_action/act/discover tools.
"""
from __future__ import annotations

import copy
import json
import math
import re
import time

from .compute import RestrictedCompute
from .deadline import DeadlineExceeded, EpisodeDeadline


class ToolRejected(ValueError):
    pass


class UnconfirmedToolOutcome(ToolRejected):
    uncertain = True


def _obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required),
            'additionalProperties': False}


_ID = {'type': 'string', 'minLength': 1, 'maxLength': 256}
_BOOL = {'type': 'boolean'}
_NUMBER = {'type': 'number'}
_NONNEGATIVE = {'type': 'number', 'minimum': 0}
_VEC = {'type': 'array', 'items': _NUMBER, 'minItems': 3, 'maxItems': 3}
_NATIVE_ACTION = _obj({'object_id': _ID, 'delta_world_m': _VEC}, ['object_id', 'delta_world_m'])
_NATIVE_SINGLE = _obj({**_NATIVE_ACTION['properties'], 'expected_revision': _ID},
                      ['object_id', 'delta_world_m', 'expected_revision'])
_NATIVE_BATCH = _obj({'expected_revision': _ID, 'actions': {
    'type': 'array', 'items': _NATIVE_ACTION, 'minItems': 1, 'maxItems': 8}},
    ['expected_revision', 'actions'])
_NATIVE = [
    {'name': 'native_scene_query', 'description':
     'Read complete actual local/world vertices, faces, topology, world matrices, object identities and revision. '
     'Lengths are metres. No target solution or selector is supplied.', 'inputSchema': _obj({})},
    {'name': 'native_look', 'description':
     'Capture the common native 384px view of the current scene. Choose XY, XZ or SCENE.',
     'inputSchema': _obj({'view': {'type': 'string', 'enum': ['XY', 'XZ', 'SCENE']}})},
    {'name': 'native_compute', 'description':
     'Write a mathematical Python subset program over scene, a fresh complete sanitized native_scene_query snapshot. '
     'Assign JSON output to result. Supports functions, return, for, if, comprehensions, indexing, lists/dictionaries, '
     'arithmetic/comparisons, sum/min/max/len/range/enumerate/zip/abs/float/int/round/list/sorted/all/any/bool and '
     'whitelisted math sqrt/trigonometry/projections/log functions. No import, arbitrary attributes, files, network, '
     'processes, bpy or mutable host objects. This common AST interpreter differs from arbitrary Python/bpy tools; '
     'model-written geometry algorithms are allowed. Call native_transform for each real write or a bounded action list.',
     'inputSchema': _obj({'code': {'type': 'string', 'minLength': 1, 'maxLength': 64000}}, ['code'])},
    {'name': 'native_transform', 'description':
     'Translate specified owned object(s) along world Z by explicit delta_world_m in metres, preserving everything else. '
     'Supply the actual native_scene_query expected_revision. Either one action or up to eight ordered actions; '
     'every setter counts separately, including rollback. Shared limits: each actual write <=0.001m, eight writes, '
     'total path <=0.008m. Actual native quantization must also meet 0.001m; excessive requests are refused. '
     'Batch stops on a failed step. No solver or hidden quality oracle is supplied.',
     'inputSchema': {'oneOf': [_NATIVE_SINGLE, _NATIVE_BATCH]}},
]
_GOAL = _obj({
    'focal_id': _ID, 'reference_id': _ID, 'target_clearance_m': _NONNEGATIVE,
    'clearance_tolerance_m': _NONNEGATIVE, 'target_focal_pivot_world_m': _VEC,
    'position_tolerance_m': _NONNEGATIVE,
    'max_contact_normal_angle_deg': {'type': 'number', 'minimum': 0, 'maximum': 180},
    'max_tangent_yaw_mismatch_deg': {'type': 'number', 'minimum': 0, 'maximum': 180},
    'yaw_symmetry_order': {'type': 'integer', 'enum': [1, 2, 4]},
})
_QUERY = _obj({
    'mode': {'type': 'string', 'enum': ['overview', 'exact_pairs', 'nearest', 'top1']},
    'object_ids': {'type': 'array', 'items': _ID, 'minItems': 1, 'maxItems': 255, 'uniqueItems': True},
    'label_object_ids': {'type': 'array', 'items': _ID, 'minItems': 1, 'maxItems': 6, 'uniqueItems': True},
    'max_exact_pairs': {'type': 'integer', 'minimum': 1, 'maximum': 255},
    'alignment_evidence': _BOOL,
    'support_plane_discovery': _obj({'direction_world': _VEC,
        'max_candidates': {'type': 'integer', 'minimum': 1, 'maximum': 6}}),
    'visual_diagnostic': {'type': 'string', 'enum': ['contact_section']},
})
_BINDING = _obj({'focal_id': _ID, 'reference_id': _ID, 'scene_revision': _ID,
    'scene_fingerprint': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}},
    ['focal_id', 'reference_id', 'scene_revision', 'scene_fingerprint'])
_DISPLAY = {'type': 'string', 'enum': ['full', 'brief']}


def _plugin_schemas(max_steps):
    budgets = {
        'max_steps': {'type': 'integer', 'minimum': 1, 'maximum': max_steps},
        'max_step_translation_m': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': .001},
        'max_total_translation_m': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': .008},
        'max_duration_s': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 30},
    }
    common = {'focal_id': _ID, 'reference_id': _ID, 'target_clearance_m': _NONNEGATIVE,
              'clearance_tolerance_m': _NONNEGATIVE, **budgets}
    required = ['focal_id', 'reference_id', 'target_clearance_m', 'clearance_tolerance_m']
    box = _obj({**common, 'axis': {'type': 'string', 'enum': ['+x', '-x', '+y', '-y', '+z', '-z']}}, required + ['axis'])
    support = _obj({**common, 'solver': {'type': 'string', 'enum': ['support_plane']},
        'direction_world': _VEC, 'reference_triangle_index': {'type': 'integer', 'minimum': 0},
        'selection_binding': _BINDING}, required + ['solver', 'direction_world', 'reference_triangle_index'])
    return [
        {'name': 'human_eye_scene_observe', 'description':
         'Read a current measured spatial observation. Object IDs select focal/reference objects. '
         'query.support_plane_discovery discovers original support triangles without inventing an action direction. '
         'Measurements can be unknown or stale. The common display default is brief and include_image=true; '
         'full and native images remain available. Caller goals are criteria, not independently verified intent.',
         'inputSchema': _obj({'task_instruction': {'type': 'string', 'maxLength': 16000},
             'focal_id': _ID, 'reference_id': _ID, 'goal': _GOAL, 'query': _QUERY,
             'include_image': _BOOL, 'response_detail': _DISPLAY})},
        {'name': 'human_eye_clearance_segment', 'description':
         'Preview or execute a finite target-clearance segment. execute defaults false; reuse request_id only '
         'to retrieve a historical receipt. Use explicit signed world axis or solver=support_plane with an original '
         'reference triangle and explicit world direction. Every actual step requires fresh geometry checks/readback. '
         'Endpoint only; no swept path certificate. Shared actual write/path limits still apply. '
         'The common display default is brief and include_image=false. '
         f'Target segment max_steps must not exceed {max_steps}.',
         'inputSchema': _obj({'request_id': _ID, 'request': {'oneOf': [box, support]},
             'execute': _BOOL, 'include_image': _BOOL, 'response_detail': _DISPLAY}, ['request_id', 'request'])},
        {'name': 'human_eye_transform', 'description':
         'Apply an explicit guarded world Z translation in metres to the focal object after fresh observation and '
         'mandatory endpoint checks/readback. Shared actual write limits apply. Caller goals are criteria, '
         'not independently verified intent. No swept path is certified.',
         'inputSchema': _obj({'action': _obj({'focal_id': _ID, 'reference_id': _ID,
             'translation': _VEC}, ['focal_id', 'reference_id', 'translation']), 'goal': _GOAL}, ['action'])},
    ]


def validate_schema(value, schema, path='arguments'):
    """Small strict validator for this frozen schema vocabulary; bool is not numeric."""
    if 'oneOf' in schema:
        successes = 0
        for candidate in schema['oneOf']:
            try:
                validate_schema(value, candidate, path)
                successes += 1
            except ToolRejected:
                pass
        if successes != 1:
            raise ToolRejected(path + ' must match exactly one supported request shape')
    typ = schema.get('type')
    checks = {'object': lambda: type(value) is dict, 'array': lambda: type(value) is list,
              'string': lambda: type(value) is str, 'boolean': lambda: type(value) is bool,
              'number': lambda: type(value) in (int, float), 'integer': lambda: type(value) is int}
    if typ and (typ not in checks or not checks[typ]()):
        raise ToolRejected(path + ' has an unsupported type')
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ToolRejected(path + ' requires a finite number')
        for key, valid in [('minimum', lambda n: value >= n), ('maximum', lambda n: value <= n),
                           ('exclusiveMinimum', lambda n: value > n)]:
            if key in schema and not valid(schema[key]):
                raise ToolRejected(path + ' is outside the allowed range')
    if 'enum' in schema and value not in schema['enum']:
        raise ToolRejected(path + ' has an unsupported value')
    if type(value) is str:
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 2**31):
            raise ToolRejected(path + ' string length outside limit')
        if schema.get('minLength', 0) and not value.strip():
            raise ToolRejected(path + ' must not be blank')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            raise ToolRejected(path + ' has an unsupported format')
    if type(value) is dict and typ == 'object':
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            raise ToolRejected(path + ' missing required field')
        if schema.get('additionalProperties') is False and value.keys() - props.keys():
            raise ToolRejected(path + ' contains unknown or control fields')
        for key, item in value.items():
            if type(key) is not str:
                raise ToolRejected(path + ' keys must be strings')
            if key in props:
                validate_schema(item, props[key], path + '.' + key)
    if type(value) is list and typ == 'array':
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 2**31):
            raise ToolRejected(path + ' array length outside limit')
        if schema.get('uniqueItems') and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            raise ToolRejected(path + ' duplicate array entries')
        for item in value:
            validate_schema(item, schema['items'], path + '[]')


# Strip only runtime transport identity/secrets/paths, never generic state,
# source/provenance, certificates, selectors, unknowns, or geometry diagnostics.
_PRIVATE_KEYS = frozenset((
    'session_id', 'sessionid', 'private_nonce', 'nonce', 'instance_nonce',
    'engine_instance_nonce', 'ownership_nonce', 'auth_token', 'access_token',
    'authorization', 'cookie', 'api_key', 'token', 'owner_token', 'secret',
    'password', 'credential', 'credentials', 'source_path', 'sourcepath',
    'engine_source_path', 'state_file', 'statefile', 'state_path', 'audit_path',
    'runtime_path', 'host_path', 'hostpath', 'installation_path', 'module_path',
    'workdir', 'cwd', 'python_executable', 'config_path',
))
_PATH = re.compile(r'(?i)(?:file://[^\s\"<>]+|[a-z]:[\\/][^\s\"<>]*|\\\\[^\s\"<>]+|(?<![\w:])/(?:home|users|tmp|var|opt|usr|mnt|private|workspace|app|root)(?:/[^\s\"<>]*)?)')


def sanitize_result(value):
    """Project JSON/wire content only. Unprovable values become a partial result.

    MCP text blocks must be JSON, so embedded serialized paths/private keys get
    exactly the same recursive projection. Native PNG base64 bytes are retained.
    Unknown JSON diagnostic/geometry/certificate fields are retained verbatim.
    """
    redactions = 0
    partial = False
    visited = 0

    def clean(item, depth=0):
        nonlocal redactions, partial, visited
        visited += 1
        if depth > 100 or visited > 4000000:
            raise ToolRejected('return structure exceeds safe projection limit')
        typ = type(item)
        if typ in (bool, type(None)):
            return item
        if typ in (int, float):
            try:
                valid = math.isfinite(item)
            except OverflowError:
                valid = False
            if not valid:
                partial = True
                return {'unknown': 'nonfinite_or_unbounded_numeric_return'}
            return item
        if typ is str:
            # JSON encoded inside structured fields gets recursively projected,
            # not regex-only filtering of an opaque nested diagnostic payload.
            stripped = item.lstrip()
            if stripped.startswith(('{', '[')):
                try:
                    decoded = json.loads(item, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
                except (ValueError, RecursionError):
                    decoded = None
                if type(decoded) in (dict, list):
                    return json.dumps(clean(decoded, depth + 1), ensure_ascii=False, allow_nan=False)
            result, count = _PATH.subn('[runtime path removed]', item)
            redactions += count
            return result
        if typ is list:
            return [clean(v, depth + 1) for v in item]
        if typ is not dict or any(type(k) is not str for k in item):
            raise ToolRejected('return must be exact JSON values')
        if item.get('type') == 'image':
            if (set(item) - {'type', 'data', 'mimeType', 'annotations', '_meta'}
                    or type(item.get('data')) is not str
                    or item.get('mimeType') not in ('image/png', 'image/jpeg', 'image/webp')
                    or not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', item['data'])):
                raise ToolRejected('unverifiable native image return')
            output = {'type': 'image', 'mimeType': item['mimeType'], 'data': item['data']}
            for key in ('annotations', '_meta'):
                if key in item:
                    output[key] = clean(item[key], depth + 1)
            return output
        if item.get('type') == 'text' and 'text' in item:
            if type(item['text']) is not str:
                raise ToolRejected('invalid text return')
            try:
                decoded = json.loads(item['text'], parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
            except (ValueError, RecursionError):
                # A plain diagnostic can contain unstructured private authority.
                # Do not guess a safe subset or expose a raw exception string.
                partial = True
                decoded = {'partial': True, 'unknown': 'non_json_wire_text_withheld'}
            output = {'type': 'text', 'text': json.dumps(clean(decoded, depth + 1), ensure_ascii=False, allow_nan=False)}
            for key, val in item.items():
                if key not in ('type', 'text') and key.lower() not in _PRIVATE_KEYS:
                    output[key] = clean(val, depth + 1)
            return output
        output = {}
        for key, val in item.items():
            if key.lower() in _PRIVATE_KEYS or key.lower().endswith(('_nonce', '_statefile', '_source_path')):
                redactions += 1
                continue
            safe_key, count = _PATH.subn('[runtime path removed]', key)
            redactions += count
            if safe_key in output:
                raise ToolRejected('projection key collision')
            output[safe_key] = clean(val, depth + 1)
        return output

    try:
        result = clean(value)
        if type(result) is dict and (partial or redactions):
            result['_trial_sanitization'] = {'partial': partial, 'runtime_fields_removed': redactions}
        return result
    except (ToolRejected, RecursionError, ValueError, TypeError):
        return {'partial': True, 'status': 'partial', 'unknown': 'unsafe_tool_return_withheld',
                '_trial_sanitization': {'partial': True, 'runtime_fields_removed': redactions}}


class TrialRouter:
    def __init__(self, arm, native, plugin=None, clock=time.monotonic):
        if arm not in ('A', 'B', 'C'):
            raise ValueError('arm must be A, B or C')
        if arm in ('B', 'C') and plugin is None:
            raise ValueError('B/C require an explicit plugin adapter')
        self.arm = arm
        self.native = native
        self.plugin = None if arm == 'A' else plugin
        self.clock = clock
        self.max_steps = 1 if arm == 'B' else 8
        self.compute = RestrictedCompute(clock=clock)
        self.events = []
        self._schemas = copy.deepcopy(_NATIVE + ([] if arm == 'A' else _plugin_schemas(self.max_steps)))
        self._by_name = {tool['name']: tool for tool in self._schemas}
        self.deadline = None
        self.bound_deadline = None
        self.closed = False
        self.partial = False
        self.poisoned = False
        self.uncertainty_reason = None

    def bind_deadline(self, budget, *, require_adapters=True):
        if type(budget) is not EpisodeDeadline:
            raise ValueError('one trusted EpisodeDeadline is required')
        if self.closed:
            raise ToolRejected('episode router is closed')
        if self.bound_deadline is not None:
            if self.bound_deadline is not budget:
                raise ToolRejected('episode deadline cannot be rebound or renewed')
            budget.check()
            return self
        budget.check()
        self.bound_deadline = budget
        self.deadline = budget.expires_at
        self.clock = budget.clock
        self.compute.clock = budget.clock
        budget.add_expiry_callback(self._expire_episode)
        for adapter in (self.native, self.plugin):
            if adapter is None:
                continue
            bind = getattr(adapter, 'bind_deadline', None)
            if not callable(bind):
                if require_adapters:
                    self.closed = True
                    raise ToolRejected('tool adapter cannot bind the shared deadline')
                continue  # Data-only synthetic fakes do not gain formal status.
            bind(budget)
            if getattr(adapter, 'bound_deadline', None) is not budget:
                self.closed = True
                raise ToolRejected('tool adapter did not retain the shared deadline')
        budget.check()
        return self

    def _expire_episode(self):
        # Timer callback never performs blocking I/O or acquires adapter locks.
        self.closed = True

    def end_episode(self):
        # The harness still owns scoring/cleanup. Do not cancel the deadline's
        # owned-process watchdog while those processes remain alive.
        self.closed = True

    def _check_deadline(self):
        if self.closed:
            raise ToolRejected('episode router is closed')
        if self.bound_deadline is not None:
            try:
                self.bound_deadline.check()
            except DeadlineExceeded:
                self.closed = True
                raise
        elif self.deadline is not None and self.clock() >= self.deadline:
            self.closed = True
            raise ToolRejected('episode wall time exhausted')

    def tool_schemas(self):
        return copy.deepcopy(self._schemas)

    @property
    def schemas(self):
        return self.tool_schemas()

    def call(self, name, arguments):
        self._check_deadline()
        if self.poisoned or self._adapter_uncertain():
            self.poisoned = True
            raise UnconfirmedToolOutcome('unconfirmed prior tool outcome; all further actions stopped')
        try:
            return self._call(name, arguments)
        except Exception as exc:
            if (getattr(exc, 'uncertain', False) or getattr(exc, 'quarantined', False)
                    or self._adapter_uncertain()):
                self.poisoned = True
                self.uncertainty_reason = 'unconfirmed_tool_outcome'
                raise UnconfirmedToolOutcome('unconfirmed tool outcome; no retry or later action allowed') from None
            raise

    def _adapter_uncertain(self):
        return any(getattr(adapter, '_poisoned', False) or getattr(adapter, 'uncertain_outcome', False)
                   or getattr(adapter, 'quarantined', False)
                   for adapter in (self.native, self.plugin) if adapter is not None)

    @staticmethod
    def _unconfirmed(value, depth=0):
        if depth > 100:
            return True
        if type(value) is str:
            if value.lstrip().startswith(('{', '[')):
                try:
                    return TrialRouter._unconfirmed(json.loads(value), depth + 1)
                except (ValueError, RecursionError):
                    return False
            return False
        if type(value) is list:
            return any(TrialRouter._unconfirmed(v, depth + 1) for v in value)
        if type(value) is not dict:
            return False
        if 'executed' in value and value['executed'] is None:
            return True
        if any(value.get(key) for key in ('inflight', 'quarantined', 'uncertain_outcome')):
            return True
        statuses = {'execution_uncertain', 'host_quarantined', 'unconfirmed', 'unconfirmed_outcome',
                    'inflight', 'in_flight', 'quarantined', 'write_outcome_unknown'}
        if any(type(value.get(key)) is str and value[key] in statuses
               for key in ('status', 'execution_status', 'write_status', 'outcome')):
            return True
        return any(TrialRouter._unconfirmed(v, depth + 1) for v in value.values())

    def _call(self, name, arguments):
        start = self.clock()
        self._check_deadline()
        if name not in self._by_name:
            raise ToolRejected('tool is outside this arm capability whitelist')
        schema = self._by_name[name]['inputSchema']
        validate_schema(arguments, schema)
        args = copy.deepcopy(arguments)
        self._check_deadline()
        if name == 'native_compute':
            # Deliberately no supplied scene/environment/file parameter exists.
            raw_scene = self.native.call('native_scene_query', {})
            if self._adapter_uncertain() or self._unconfirmed(raw_scene):
                self.poisoned = True
                raise UnconfirmedToolOutcome('unconfirmed native snapshot channel')
            scene = sanitize_result(raw_scene)
            self._check_deadline()
            if type(scene) is not dict:
                raise ToolRejected('native geometry snapshot is not a JSON object')
            if scene.get('partial') or scene.get('_trial_sanitization', {}).get('partial'):
                raise ToolRejected('full sanitized native geometry unavailable')
            if self.bound_deadline is not None and self.bound_deadline.clock is time.monotonic:
                from .isolated_compute import run_isolated_compute
                result = run_isolated_compute(args['code'], scene, self.bound_deadline,
                                              limits=self.compute.limits)
            else:
                result = self.compute.run(args['code'], scene, deadline=self.deadline)
        elif name.startswith('native_'):
            if name == 'native_transform':
                actions = args.get('actions', [args])
                for action in actions:
                    vector = action['delta_world_m']
                    if vector[0] != 0 or vector[1] != 0 or abs(vector[2]) > .001:
                        raise ToolRejected('native action requires world Z translation <=0.001m')
            result = self.native.call(name, args)
        else:
            if name == 'human_eye_scene_observe':
                args.setdefault('response_detail', 'brief')
                args.setdefault('include_image', True)
                if (args.get('query', {}).get('alignment_evidence') is False
                        and args['include_image']):
                    raise ToolRejected('alignment_evidence=false requires include_image=false')
            elif name == 'human_eye_clearance_segment':
                # Actual nested request, never a dummy top-level max_steps knob.
                request = args['request']
                request.setdefault('max_steps', self.max_steps)
                request.setdefault('max_step_translation_m', .001)
                request.setdefault('max_total_translation_m', .008)
                request.setdefault('max_duration_s', 30)
                args.setdefault('execute', False)
                args.setdefault('include_image', False)
                args.setdefault('response_detail', 'brief')
                validate_schema(args, schema)
                if request.get('solver') == 'support_plane':
                    direction = request['direction_world']
                    if direction[0] != 0 or direction[1] != 0 or direction[2] == 0:
                        raise ToolRejected('segment direction must be world Z')
                elif request['axis'] not in ('+z', '-z'):
                    raise ToolRejected('segment axis must be world Z')
            elif name == 'human_eye_transform':
                vector = args['action']['translation']
                if vector[0] != 0 or vector[1] != 0 or abs(vector[2]) > .001:
                    raise ToolRejected('plugin action requires world Z translation <=0.001m')
            result = self.plugin.call(name, args)
        if self._adapter_uncertain() or self._unconfirmed(result):
            self.poisoned = True
            self.uncertainty_reason = 'unconfirmed_tool_outcome'
            raise UnconfirmedToolOutcome('unconfirmed tool outcome; no retry or later action allowed')
        self._check_deadline()
        projected = sanitize_result(result)
        self._check_deadline()
        self.partial |= bool(type(projected) is dict and (
            projected.get('partial') or projected.get('_trial_sanitization', {}).get('partial')))
        self.events.append({'name': name, 'arguments': args, 'started': start,
                            'elapsed_s': self.clock() - start, 'result': projected})
        self._check_deadline()
        return projected
