"""Cross-process live Blender service shared by command hooks and MCP tools."""
from __future__ import annotations

import base64
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import copy
from functools import wraps, partial
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import time
import uuid

import numpy as np

from .agent_hooks import _atomic_write, _path, _read_object, _state_lock, StateLockTimeoutError
from .auto_router import _validated_scene, _ValidatedObservation, _trace_span, _trace_annotate as annotate
from .host_runtime import GuardedHostRuntime, _bound_goal, _goal_fields, _capability_rejection
from .scene_rendering import render_scene_canvas
from .runtime_identity import IMPLEMENTATION_REVISION, runtime_identity, validate_expected_identity, check_source_drift, check_task_source
from .telemetry import best_effort_trace, current_trace, set_image_request, record_image_artifact
from .result_contract import scoped_result
from .query_policy import validate_query
from .native_observation import (validate_native_capabilities, validate_readonly_observation)
from .prompt_pairing import resolve_prompt_pair
from .scene_capabilities import build_scene_capabilities
from .request_context import (validate_task_context, bind_task_context, trace_task_context,
                              validate_scene_delta_request)
from human_eye_hook import write_audit_event

span = partial(_trace_span, source_name='live_service')
_IMAGE_UNSPECIFIED = object()
_REQUEST_BUDGET = ContextVar('human_eye_live_request_budget', default=None)
_STATE_WRITE_BUFFER_LIMIT = 512 * 1024
_STATE_COMPARE_STREAM_CHUNKS = 2048
_REQUEST_BUDGET_SCOPE = 'cooperative_service_entry_through_mcp_prewrite_checkpoints'

_DIAGNOSTIC_MANIFEST_LIMIT = 64
_DIAGNOSTIC_MANIFEST_BYTES = 256 * 1024


def _state_json_matches(encoded, previous, *, checkpoint=None):
    """Exact ASCII JSON equality without joining a second large document.

    Token-heavy states retain the C encoder after a bounded streaming probe.
    Even after a mismatch, finish validating the old JSON (or fall back) so a
    trailing nonfinite/unsupported/cyclic value cannot turn into a quiet write.
    Individual encoder string tokens can still be large; this is not an
    all-input constant-memory guarantee.
    """
    if len(encoded) <= _STATE_WRITE_BUFFER_LIMIT:
        return encoded == json.dumps(previous, ensure_ascii=True, allow_nan=False)
    with span('state.persist.compare_stream', kind='encoding'):
        encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False)
        offset, matches = 0, True
        for index, chunk in enumerate(encoder.iterencode(previous)):
            if checkpoint is not None and index % 16 == 0:
                checkpoint()
            if index >= _STATE_COMPARE_STREAM_CHUNKS:
                with span('state.persist.compare_fallback', kind='encoding'):
                    return encoded == json.dumps(previous, ensure_ascii=True, allow_nan=False)
            if matches:
                matches = encoded.startswith(chunk, offset)
                offset += len(chunk)
            # Do not retain the caller's reference while requesting the next
            # chunk; no prefix slice or list of old chunks is constructed.
            del chunk
        return matches and offset == len(encoded)


def _request_error_fields(error=None):
    saved = getattr(error, '_human_eye_request_fields', None)
    if saved is not None:
        return copy.deepcopy(saved)
    request = _REQUEST_BUDGET.get()
    if request is None:
        return {}
    writes = request['state_writes']
    submitted = request['submitted']
    execution = request['execution'] or {
        'executed': None if submitted else False, 'verified': False,
        'execution_verified': False,
        'execution_status': 'execution_uncertain' if submitted else 'not_executed',
        'host_mutation_started': None if submitted else False}
    return {**execution, 'allow_action': False, 'execution_authority': False,
        'retry_authorized': False,
        'connector_state_write_attempted': writes['attempts'] > 0,
        'connector_state_write_committed': (True if writes['commits'] else
            None if writes['unknowns'] else False),
        'connector_state_write_status': writes['last_status'],
        'connector_state_write_attempts': writes['attempts'],
        'connector_state_write_commits': writes['commits'],
        'connector_state_write_unknown': writes['unknowns'] > 0,
        'state_write_scope': 'connector_state_json_not_audit_or_lock_sidecars'}


class RequestBudgetError(ValueError):
    """A cooperative deadline refusal retaining completed or uncertain effects."""

    def __init__(self, kind, stage):
        if kind not in {'busy', 'expired'}:
            raise ValueError('Invalid request budget error kind')
        self.code = 'live_request_' + kind
        self.diagnostic = {
            'status': kind, 'code': self.code, 'reason_codes': [self.code],
            'budget_stage': stage,
            'budget_scope': _REQUEST_BUDGET_SCOPE,
            **_request_error_fields(),
        }
        super().__init__('[' + self.code + '] Local request budget exhausted at ' + stage)

    def to_error_fields(self):
        return {**copy.deepcopy(self.diagnostic), **_request_error_fields(self)}


class StateBindingError(ValueError):
    """A preserved binding refusal, with non-authorizing recovery guidance."""

    code = 'state_configuration_binding_mismatch'

    def __init__(self, classification, *, disk_configuration='unavailable', manifest=None):
        self.reason_codes = [self.code, classification]
        action, message = {
            'stale_configuration_snapshot': (
                'restart_and_revalidate_current_configuration',
                'This process holds an older connector configuration; the current on-disk '
                'configuration matches the persisted state. Restart with the reviewed current '
                'configuration, then revalidate state and pending-operation health.'),
            'known_uncommitted_activation_fence': (
                'operator_recovery_from_activation_records',
                'Persisted connector state matches an unfinished activation fence. Preserve '
                'the activation backups and operation journal for operator recovery; '
                'restarting does not remove this fence.'),
            'state_binding_cause_unconfirmed': (
                'review_configuration_state_and_activation_records',
                'Persisted connector state does not match this process configuration. '
                'Preserve the state, operation journal and activation backups; review the '
                'configuration binding before proceeding. A restart alone is not a general repair.'),
        }[classification]
        self.recovery = {
            'classification': classification, 'action': action,
            'preserve_state_and_journal': True, 'preserve_activation_backups': True,
            'restart_alone_is_sufficient': False, 'execution_authority': False,
            'disk_configuration': disk_configuration,
        }
        if manifest is not None:
            self.recovery['matching_activation_record'] = copy.deepcopy(manifest)
        self.diagnostic = {'code': self.code, 'reason_codes': list(self.reason_codes),
                           'recovery': copy.deepcopy(self.recovery)}
        super().__init__('[' + self.code + '] ' + message)

    def to_error_fields(self):
        return copy.deepcopy(self.diagnostic)


def _diagnostic_object(raw):
    """Reject ambiguous records rather than guessing an activation history."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate diagnostic JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite diagnostic JSON value')
    result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=invalid)
    json.dumps(result, allow_nan=False)  # Includes exponent-overflow rejection.
    if not isinstance(result, dict):
        raise ValueError('Diagnostic JSON must be an object')
    return result


def _plain_diagnostic_path(path):
    """Diagnostic discovery never follows symlink/junction backup entries."""
    attributes = path.lstat()
    return not (stat.S_ISLNK(attributes.st_mode)
                or getattr(attributes, 'st_file_attributes', 0) & 0x400)


def _diagnostic_sha256(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in '0123456789abcdef' for char in value))


def _request(operation):
    """Reuse a transport trace; direct Python callers get one request trace."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            session_id = args[0] if args else kwargs.get('session_id')
            if operation == 'goal_supervision':
                session_id = args[2] if len(args) > 2 else kwargs.get('session_id')
            elif operation == 'supervised_clearance_segment':
                session_id = args[1] if len(args) > 1 else kwargs.get('session_id')
            task_context = validate_task_context(kwargs.get('task_context'))
            with self._request_budget(), self.request_trace(operation, session_id=session_id,
                    task_context=task_context,
                    include_image=None if operation == 'status' else
                        kwargs.get('include_image', operation not in {
                            'clearance_segment', 'goal_supervision', 'supervised_clearance_segment', 'mesh_structure'})) as trace:
                if self.request_budget_s is not None:
                    annotate(request_budget_s=self.request_budget_s,
                        request_budget_scope=_REQUEST_BUDGET_SCOPE)
                with span('service.' + operation, kind='cpu'):
                    result = method(self, *args, **kwargs)
                if isinstance(result, dict):
                    self._remember_execution_result(result)
                    if operation in {"observe", "preview", "transform"} and result.get('result_kind') not in ('structure_task','surface_task','task_query','surface_nearest'):
                        pair = (args[1] if len(args) > 1 else kwargs.get('action')) if operation != 'observe' else kwargs
                        result = scoped_result(result, operation=operation, goal=kwargs.get('goal'), pair=pair)
                    route = result.get('routing') or {}
                    record_image_artifact('service_result', image_present=(route.get('image') is not None
                        or bool(route.get('images'))))
                    for key in ('observation_id', 'scene_revision', 'cache_hit',
                                'measurement_cache_hit', 'engine_invoked', 'requires_reobserve'):
                        if key in route:
                            annotate(**{key: route[key]})
                    for key in ('status', 'verified', 'execution_verified', 'goal_evaluation'):
                        if key in result:
                            annotate(**{key: result[key]})
                    if 'segment_id' in result:
                        annotate(segment_id=result['segment_id'])
                    for field, annotation in (('replayed', 'receipt_replayed'), ('historical_receipt', 'historical_receipt')):
                        if type(result.get(field)) is bool:
                            annotate(**{annotation: result[field]})
                    if trace is not None:
                        try:
                            trace.set_outcome(result.get('status', 'completed'))
                            if result.get('result_kind') in ('task_query', 'surface_nearest'):
                                result['trace_id'] = trace.trace_id
                            else:
                                result['request_trace'] = {'trace_id': trace.trace_id,
                                    'request_id': trace.request_id, 'model_usage': 'unknown',
                                    'delivery': 'service_result_constructed'}
                                associated = trace_task_context(trace)
                                if associated is not None:
                                    result['request_trace']['task_context'] = associated
                                    result['request_trace']['task_context_scope'] = 'caller_correlation_only_not_authority'
                        except Exception:
                            pass
                return result
        return wrapped
    return decorate


def _reuse_observation_capture(captured):
    """Conservative scheduling hint only; either branch fully validates raw input."""
    if not isinstance(captured, dict) or not isinstance(captured.get('meshes'), list):
        return False
    items = captured['meshes']
    if len(items) >= 8:
        return True
    vertices = 0
    for item in items:
        if not isinstance(item, dict):
            return False
        value = item.get('vertices')
        if not isinstance(value, (list, tuple, np.ndarray)):
            return False
        try:
            vertices += len(value)
        except TypeError:
            return False
        if vertices >= 128:
            return True
    return False


class LiveSpatialService:
    """One trusted config and state file per live Blender connection.

    Every mutation journals uncertainty before contacting the host. Crashes,
    socket timeouts and state-write failures therefore cannot authorize retry.
    Hooks may preview but only transform() can invoke the mandatory inner gate.
    """

    def __init__(self, config_path, host=None, *, production_mode=False,
                 supervisor_context=None, surface_references=None):
        if type(production_mode) is not bool:
            raise ValueError('production_mode must be boolean')
        if surface_references is not None:
            from .surface_reference import ReferenceRegistry
            if type(surface_references) is not ReferenceRegistry:raise ValueError('surface_references requires a trusted local registry')
        self._surface_references=surface_references
        self.production_mode = production_mode
        if supervisor_context is not None:
            from .goal_supervision import GoalSupervisorContext
            if type(supervisor_context) is not GoalSupervisorContext:
                raise ValueError('supervisor_context requires trusted Python callbacks')
        self._supervisor_context = supervisor_context
        self.config_path = Path(config_path).resolve()
        self.config = _read_object(self.config_path)
        self._identity = runtime_identity(mode='live')
        self._identity_check = validate_expected_identity(self.config.get('expected_identity'), self._identity)
        if self.config.get("schema_version") != "1.0":
            raise ValueError("Unsupported live connector configuration")
        for field in ("enabled", "observe_on_prompt"):
            if field in self.config and not isinstance(self.config[field], bool):
                raise ValueError(field + " must be a boolean")
        # Optional trusted local connector policy. None preserves the former
        # 20-second lock wait. This starts at each service method entry, includes
        # lock waiting, and is checked cooperatively only before commit. It does
        # not time startup/imports or interrupt a running kernel/host mutation.
        self.request_budget_s = self.config.get('request_budget_s')
        if self.request_budget_s is not None:
            try:
                valid_budget = (type(self.request_budget_s) in (int, float)
                    and np.isfinite(float(self.request_budget_s)) and self.request_budget_s > 0)
            except (TypeError, ValueError, OverflowError):
                valid_budget = False
            if not valid_budget:
                raise ValueError('request_budget_s must be null or a positive finite number')
            self.request_budget_s = float(self.request_budget_s)
        self.native_visual_timeout_s = self.config.get('native_visual_timeout_s', 10.)
        if (type(self.native_visual_timeout_s) not in (int, float)
                or not np.isfinite(float(self.native_visual_timeout_s))
                or not 0 < self.native_visual_timeout_s <= 30):
            raise ValueError('native_visual_timeout_s must be a positive finite number at most 30')
        self.native_visual_timeout_s = float(self.native_visual_timeout_s)
        self.root = _path(self.config_path.parent, self.config.get("project_root"), "project_root")
        self.state_path = _path(self.config_path.parent, self.config.get("state_file"), "state_file")
        self.audit_path = _path(self.config_path.parent, self.config.get("audit_file"), "audit_file")
        if len({self.config_path, self.state_path, self.audit_path,
                self.state_path.with_name(self.state_path.name + '.lock'),
                self.audit_path.with_name(self.audit_path.name + '.lock')}) != 5:
            raise ValueError("Configuration, state, audit and lock paths must be distinct")
        self.config_fingerprint = hashlib.sha256(json.dumps(self.config, sort_keys=True,
            ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if host is None:
            from .blender_mcp_host import BlenderMCPHost
            connection = self.config.get("blender", {})
            host = BlenderMCPHost(self.root, host=connection.get("host", "127.0.0.1"),
                port=connection.get("port", 9876), timeout_s=connection.get("timeout_s", 10))
        self.host = host
        self._perception_cache = None
        from .read_context import ReadContext
        self._read_context = ReadContext()
        self._read_generation = None
        self._read_source_identity()

    def _read_source_identity(self):
        generation = (self._identity['source_sha256'], id(self.host), self.production_mode)
        if generation != self._read_generation:
            self._identity_check = validate_expected_identity(self.config.get('expected_identity'), self._identity)
            if self._read_generation is not None:
                self._read_context.reset(clear_measurements=True)
            self._read_identity_result = self._check_identity(readonly_task=True)
            self._read_generation = generation
        return self._read_identity_result

    def _bind_read_result(self, result, source_check):
        result['binding']['runtime_source_sha256'] = self._identity['source_sha256']
        if source_check is not None and source_check['status'] == 'loaded_generation':
            result['binding'].update(source_status='loaded_generation', disk_status='disk_not_checked',
                source_check_scope=source_check['source_check_scope'])

    @contextmanager
    def _request_budget(self):
        existing = _REQUEST_BUDGET.get()
        if existing is not None and existing['service'] is self:
            yield existing
            return
        value = {
            'service': self,
            'deadline': None if self.request_budget_s is None else time.monotonic() + self.request_budget_s,
            'guard_active': True, 'submitted': False, 'execution': None,
            'state_writes': {'attempts': 0, 'commits': 0, 'unknowns': 0, 'last_status': 'not_attempted'},
        }
        token = _REQUEST_BUDGET.set(value)
        try:
            yield value
        except Exception as exc:
            exc._human_eye_request_fields = _request_error_fields()
            raise
        finally:
            _REQUEST_BUDGET.reset(token)

    def _remaining_request_budget(self, *, publication=False):
        value = _REQUEST_BUDGET.get()
        if (value is None or value['service'] is not self or value['deadline'] is None
                or not publication and not value['guard_active']):
            return None
        return value['deadline'] - time.monotonic()

    def observe_readview(self,session_id,request_id,*,target_id=None,expected_source_sha256=None):
        """Opt-in SDK candidate. Not exposed through the default MCP/Hook."""
        from PIL import Image
        from .forward_deadline import counter_descriptor
        started=time.perf_counter_ns();deadline=started+30_000_000_000
        receipt={'request_id':request_id,'status':'unavailable','images_constructed':0,
            'construction_status':'not_attempted',
            'publishable_images':0,'consumer_delivery_confirmed':False,'error':None,
            'started_ns':started,'finished_ns':None,'read_only':True,'execution_authority':False}
        self._last_readview_receipt=receipt
        raw=None
        try:
            if type(session_id) is not str or not session_id or type(request_id) is not str or not request_id:
                raise ValueError('material_readview_request_invalid')
            if _read_object(self.config_path)!=self.config:raise ValueError('material_readview_config_changed')
            reject=self._identity_rejection()
            if reject is not None:raise ValueError('material_readview_runtime_identity_changed')
            policy=self.config.get('material_readview')
            if type(policy) is not dict or policy.get('enabled') is not True:
                raise ValueError('material_readview_not_enabled')
            binding=policy.get('binding')
            if type(binding) is not dict:raise ValueError('material_readview_binding_missing')
            if target_id is not None and target_id!=binding['target_id']:
                raise ValueError('material_readview_target_conflict')
            if expected_source_sha256 is not None and expected_source_sha256!=binding['source_sha256']:
                raise ValueError('material_readview_source_conflict')
            with self.host.transaction():
                header=self.host.material_readview_header(binding)
                binding_digest=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',', ':'),
                    ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()
                if (type(header) is not dict or header.get('protocol')!='static-material-readview-v1'
                        or header.get('binding')!=binding or header.get('binding_digest')!=binding_digest
                        or header.get('clock')!=counter_descriptor()
                        or type(header.get('appearance')) is not dict
                        or type(header['appearance'].get('fingerprint')) is not str
                        or len(header['appearance']['fingerprint'])!=64
                        or any(c not in '0123456789abcdef' for c in header['appearance']['fingerprint'])
                        or header.get('read_only') is not True or header.get('execution_authority') is not False):
                    raise ValueError('material_readview_header_invalid')
                receipt['images_constructed']=None
                receipt['construction_status']='unknown_until_host_receipt'
                raw=self.host.observe_material_readview(request_id,binding,header['appearance']['fingerprint'],deadline)
            # A transport reply alone proves neither zero nor one construction.
            # Validate the complete request-bound receipt before adopting costs,
            # including for physical failures after a PNG was constructed.
            receipt['construction_status']='unknown_invalid_host_receipt'
            audit=raw.get('audit') if type(raw) is dict else None
            checked_ns=time.perf_counter_ns()
            def bounded_int(value):
                return type(value) is int and 0<=value<(1<<63)
            def hex64(value):
                return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
            valid=(type(raw) is dict and type(audit) is dict
                and {'protocol','request_id','binding','binding_digest','expected_appearance_fingerprint',
                    'appearance','image','audit','read_only','execution_authority'}<=set(raw)
                and {'protocol','request_id','clock','status','started_ns','finished_ns','deadline_ns',
                    'render_attempted','image_constructed','image_returned_to_transport','restored','error',
                    'attempts_spent','constructed_spent','returned_to_transport','read_only','execution_authority'}<=set(audit)
                and raw.get('protocol')=='static-material-readview-v1' and raw.get('request_id')==request_id
                and raw.get('binding')==binding and raw.get('binding_digest')==binding_digest
                and raw.get('expected_appearance_fingerprint')==header['appearance']['fingerprint']
                and raw.get('read_only') is True and raw.get('execution_authority') is False
                and audit.get('protocol')=='static-material-readview-v1' and audit.get('request_id')==request_id
                and audit.get('clock')==header['clock'] and audit.get('deadline_ns')==deadline
                and all(bounded_int(audit.get(key)) for key in ('started_ns','finished_ns','deadline_ns',
                    'attempts_spent','constructed_spent','returned_to_transport'))
                and started<=audit.get('started_ns',-1)<=audit.get('finished_ns',-1)<=checked_ns
                and audit.get('started_ns',deadline)<deadline
                and all(type(audit.get(key)) is bool for key in
                    ('render_attempted','image_constructed','image_returned_to_transport'))
                and (audit.get('restored') is None or type(audit.get('restored')) is bool)
                and audit.get('read_only') is True and audit.get('execution_authority') is False
                and 0<=audit.get('returned_to_transport',-1)<=audit.get('constructed_spent',-1)
                    <=audit.get('attempts_spent',-1)<=2)
            if valid:
                attempted=audit['render_attempted'];constructed=audit['image_constructed']
                returned=audit['image_returned_to_transport'];appearance=raw.get('appearance')
                valid=(audit['attempts_spent']>=int(attempted)
                    and audit['constructed_spent']>=int(constructed)
                    and audit['returned_to_transport']>=int(returned)
                    and (not constructed or attempted)
                    and (not returned or constructed and audit['restored'] is True)
                    and (appearance is None or type(appearance) is dict and hex64(appearance.get('fingerprint')))
                    and (not constructed or appearance==header['appearance'])
                    and (not constructed or type(audit['restored']) is bool)
                    and (not constructed or {'png_bytes','png_sha256'}<=set(audit))
                    and (not constructed or bounded_int(audit.get('png_bytes')) and audit['png_bytes']>0)
                    and (not constructed or audit.get('png_sha256') is None or hex64(audit['png_sha256']))
                    and (constructed or audit.get('png_bytes',0)==0 and audit.get('png_sha256') is None))
                if audit.get('status')=='ready':
                    valid=valid and (raw.get('status') in (None,'ready') and attempted and constructed and returned
                        and appearance==header['appearance'] and audit['restored'] is True
                        and audit.get('error') is None and hex64(audit.get('png_sha256')))
                elif audit.get('status')=='failed':
                    error=audit.get('error')
                    valid=valid and (raw.get('status')=='unavailable' and raw.get('image') is None and not returned
                        and type(error) is dict and type(error.get('type')) is str and bool(error['type'])
                        and type(error.get('message')) is str and len(error['message'])<=2000)
                else:valid=False
            if not valid:raise ValueError('material_readview_host_receipt_invalid')
            receipt['host_audit']=copy.deepcopy(audit)
            receipt['images_constructed']=int(audit['image_constructed'])
            receipt['construction_status']='validated_host_receipt'
            if audit['status']!='ready':
                raise ValueError('material_readview_not_ready:'+str(audit['error']))
            image=raw['image'];png=base64.b64decode(image['image_base64'],validate=True)
            if len(png)>8*1024*1024 or hashlib.sha256(png).hexdigest()!=raw['audit']['png_sha256']:
                raise ValueError('material_readview_png_binding')
            with Image.open(io.BytesIO(png)) as picture:
                if picture.format!='PNG' or picture.size!=(384,384):raise ValueError('material_readview_png_shape')
                picture.verify()
            if image.get('source')!='blender_cycles_material_readview':raise ValueError('material_readview_wrong_renderer')
            if time.perf_counter_ns()>=deadline:raise ValueError('material_readview_deadline_expired_before_publish')
            receipt.update(status='ready',publishable_images=1)
            return {'status':'observed','source':'candidate_static_material_readview','session_id':session_id,
                'runtime_identity':copy.deepcopy(self._identity),'header':header,'receipt':receipt,
                'image':{'type':'image','mimeType':'image/png','data':image['image_base64']},
                'view':{k:v for k,v in image.items() if k!='image_base64'},
                'scope':'one_static_local_appearance_view_not_global_visibility_or_motion_certification',
                'read_only':True,'execution_authority':False}
        except BaseException as exc:
            receipt['error']={'type':type(exc).__name__,'message':str(exc)[:2000]}
            return {'status':'unavailable','receipt':receipt,'image':None,
                'read_only':True,'execution_authority':False}
        finally:
            receipt['finished_ns']=time.perf_counter_ns()

    def _check_request_budget(self, stage, *, publication=False):
        remaining = self._remaining_request_budget(publication=publication)
        if remaining is not None and remaining <= 0:
            annotate(request_budget_status='expired', request_budget_stage=stage)
            raise RequestBudgetError('expired', stage)
        return remaining

    @staticmethod
    def request_error_fields(error=None):
        return _request_error_fields(error)

    def _remember_execution_result(self, result):
        request = _REQUEST_BUDGET.get()
        if request is None or request['service'] is not self:
            return
        if 'executed' not in result:
            return
        previous = request['execution']
        if previous and (previous.get('executed') is None
                or previous.get('executed') is True and result['executed'] is False):
            return
        request['execution'] = {key: result[key] for key in
            ('executed', 'verified', 'execution_verified', 'execution_status', 'host_mutation_started',
             'historical_receipt', 'replayed', 'current_scene_revalidated')
            if key in result}
        request['execution']['operation_status'] = result.get('status')
        request['execution']['execution_outcome_scope'] = (
            'historical_receipt' if result.get('historical_receipt') or result.get('replayed') else 'current_request')
        request['execution'].setdefault('host_mutation_started',
            False if not request['submitted'] else None if result['executed'] is None else bool(result['executed']))

    @contextmanager
    def _observation_scope(self):
        """Limit reconnect eligibility to this serialized read-only operation."""
        from .blender_mcp_host import BlenderMCPHost
        if isinstance(self.host, BlenderMCPHost):
            with self.host.observation_transaction():
                yield
        else:
            yield

    def _native_visual_policy(self, query, include_image, focal_id, reference_id):
        """Negotiate display only; a model never supplies a lease or deadline."""
        policy=query.get('native_visual', {'mode':'auto','view':'SCENE'})
        mode=policy['mode']
        delivery={'source':'analytical_projection' if include_image else 'none',
            'status':'pending' if include_image else 'not_requested', 'requested_mode':mode,
            'capability_status':'not_probed', 'reason_code':'image_not_requested' if not include_image else None,
            'image_count':0,'plan':None,'read_only':True,'execution_authority':False}
        if not include_image:
            return delivery, None
        if mode=='projection':
            delivery['reason_code']='projection_explicitly_requested'
            return delivery,None
        if query.get('label_object_ids') or query.get('visual_diagnostic'):
            delivery['reason_code']='analytical_annotations_require_projection'
            return delivery,None
        if not focal_id or not reference_id:
            if mode=='multiscale':
                raise ValueError('Native multiscale requires an established distinct observation pair')
            delivery['reason_code']='observation_pair_not_established'
            return delivery,None
        probe=getattr(self.host,'native_observation_capabilities',None)
        if not callable(probe):
            caps=None
        else:
            self._check_request_budget('before_native_capability')
            try:
                caps=probe()
            except Exception:
                raise ValueError('Native observation capability negotiation failed') from None
            self._check_request_budget('after_native_capability')
        if caps is None or type(caps) is dict and caps=={'supported':False}:
            delivery.update(capability_status='unsupported',reason_code='host_native_observation_not_supported')
            if mode=='multiscale':
                raise ValueError('The connected host does not support native read-only multiscale observation')
            return delivery,None
        caps=validate_native_capabilities(caps)
        if not callable(getattr(self.host,'observe_readonly_native',None)):
            raise ValueError('Native observation capability has no matching typed read method')
        delivery.update(source='blender_native_multiscale',capability_status='negotiated',
            reason_code='typed_readonly_native_host_negotiated')
        return delivery,caps

    def _read_native_visual(self, captured, caps, focal_id, reference_id, query):
        remaining=self._check_request_budget('before_native_observation')
        duration=min(self.native_visual_timeout_s, caps['max_duration_ns']/1e9)
        if remaining is not None:
            duration=min(duration,remaining)
        request_id=uuid.uuid4().hex
        deadline_ns=time.perf_counter_ns()+int(duration*1e9)
        view=query.get('native_visual',{}).get('view','SCENE')
        try:
            raw=self.host.observe_readonly_native(request_id,focal_id,reference_id,
                captured['revision'],deadline_ns,view)
            public=validate_readonly_observation(raw,captured=captured,capabilities=caps,
                request_id=request_id,focal_id=focal_id,reference_id=reference_id,
                deadline_ns=deadline_ns,view=view)
            if time.perf_counter_ns()>=deadline_ns:
                raise ValueError('native_readonly_delivery_deadline_expired')
        except Exception:
            # No raw response, process identity, private state or exception text
            # crosses the public boundary. A failed native attempt never swaps
            # in a projection and disguises that failed observation as success.
            raise ValueError('Native read-only observation failed; no projection fallback was performed') from None
        self._check_request_budget('after_native_observation')
        return public

    def _submitted_request(self):
        # Once the durable inflight record exists, do not turn a late result
        # into an unexecuted expiry or abandon the mandatory host readback.
        value = _REQUEST_BUDGET.get()
        if value is not None and value['service'] is self:
            value['guard_active'] = False
            value['submitted'] = True
            annotate(request_budget_enforcement='stopped_after_durable_inflight_commit')

    @contextmanager
    def request_trace(self, operation, *, session_id=None, include_image=_IMAGE_UNSPECIFIED, task_context=None):
        task_context = validate_task_context(task_context)
        trace = current_trace()
        if trace is not None:
            bind_task_context(trace, task_context)
            # A transport/hook owns the request identity. Add this service's
            # actual build even when the outer trace was opened elsewhere.
            annotate(build_id=self._identity['build_id'])
            if session_id is not None:
                annotate(session_id=session_id)
            if include_image is not _IMAGE_UNSPECIFIED:
                set_image_request(include_image, source_name='service')
            yield trace
            return
        def write(record):
            return self.record_event('request_trace', trace=record)
        with best_effort_trace(operation, writer=write,
                implementation_revision=IMPLEMENTATION_REVISION) as trace:
            bind_task_context(trace, task_context)
            # Session IDs are ancillary and may exceed the telemetry limit.
            annotate(build_id=self._identity['build_id'])
            annotate(session_id=session_id)
            if include_image is not _IMAGE_UNSPECIFIED:
                set_image_request(include_image, source_name='service')
            if trace is not None:
                trace.record_usage(source='unavailable')
            yield trace

    def _runtime(self):
        return GuardedHostRuntime(self.host, quad_size=self.config.get("quad_size", 128),
            max_sessions=self.config.get("max_sessions", 16),
            readback_atol_m=self.config.get("readback_atol_m", 1e-6),
            require_execution_capability=self.production_mode)

    def describe_runtime(self):
        """Pure startup descriptor: no host connection, locks or state reads."""
        identity = copy.deepcopy(self._identity)
        identity['source_file_count'] = len(identity.pop('source_files', []))
        identity['production_mode'] = self.production_mode
        identity['identity_check'] = copy.deepcopy(self._identity_check)
        return identity

    def _identity_rejection(self):
        return self._check_identity()[0]

    def _check_identity(self, *, readonly_task=False):
        drift = None
        if not self._identity_check['compatible']:
            return {'status': 'implementation_mismatch', 'executed': False, 'verified': False,
                    'execution_verified': False, 'allow_action': False, 'routing': None,
                    'runtime_identity': self.describe_runtime(),
                    'reason_codes': self._identity_check['reasons']}, drift
        if self.production_mode:
            with span('runtime.source_check', kind='io'):
                drift = check_task_source() if readonly_task else check_source_drift()
            if not drift['compatible']:
                return {'status': 'implementation_mismatch', 'executed': False,
                        'verified': False, 'execution_verified': False, 'allow_action': False,
                        'routing': None, 'runtime_identity': self.describe_runtime(),
                        'source_check': drift, 'reason_codes': drift['reasons']}, drift
            # Blender executes a fixed helper loaded from project_root. That
            # root may differ from this Python package's import location.
            from .blender_mcp_host import BlenderMCPHost
            if isinstance(self.host, BlenderMCPHost):
                expected = next(item['sha256'] for item in self._identity['source_files']
                                if item['path'] == 'human_eye_plugin/blender_host.py')
                try:
                    with span('runtime.host_source_check', kind='io'):
                        actual = hashlib.sha256(self.host.source.read_bytes()).hexdigest()
                except OSError:
                    actual = None
                if actual != expected:
                    return {'status': 'implementation_mismatch', 'executed': False,
                            'verified': False, 'execution_verified': False,
                            'allow_action': False, 'routing': None,
                            'runtime_identity': self.describe_runtime(),
                            'reason_codes': ['host_bridge_source_mismatch']}, drift
        return None, drift

    def _matching_activation_fence(self, state_fingerprint):
        """Read bounded sibling backup metadata solely to explain a refusal.

        An unknown 64-hex fingerprint is not evidence of a transaction fence.
        Matching requires both the current complete state bytes and explicit
        config/state paths in an unfinished local activation manifest.
        """
        if not _diagnostic_sha256(state_fingerprint):
            return None
        backups = self.config_path.parent / 'setup-backups'
        if not _plain_diagnostic_path(backups) or not backups.is_dir():
            return None
        with os.scandir(backups) as entries:
            candidates = []
            for entry in entries:
                candidates.append(Path(entry.path))
                if len(candidates) > _DIAGNOSTIC_MANIFEST_LIMIT:
                    return None
        project = self.config_path.parent.parent
        state_digest = None
        unfinished = {('prepared', 'backups_prepared'), ('in_progress', 'fenced'),
                      ('in_progress', 'configuration_written'), ('rollback_incomplete', 'recovery_required')}
        for candidate in sorted(candidates):
            try:
                manifest_path = candidate / 'manifest.json'
                if (not _plain_diagnostic_path(candidate) or not candidate.is_dir()
                        or not _plain_diagnostic_path(manifest_path)
                        or not manifest_path.is_file()
                        or manifest_path.stat().st_size > _DIAGNOSTIC_MANIFEST_BYTES):
                    continue
                with manifest_path.open('rb') as handle:
                    raw = handle.read(_DIAGNOSTIC_MANIFEST_BYTES + 1)
                if len(raw) > _DIAGNOSTIC_MANIFEST_BYTES:
                    continue
                manifest = _diagnostic_object(raw)
                if (manifest.get('schema_version') != '1.0'
                        or manifest.get('recovery_required') is not True
                        or (manifest.get('status'), manifest.get('phase')) not in unfinished
                        or manifest.get('state_commit_order') != 'fence_first_final_binding_last'
                        or manifest.get('transaction_fence_fingerprint') != state_fingerprint):
                    continue
                paths = {}
                for item in manifest.get('files', []):
                    if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                        raise ValueError('Invalid diagnostic file binding')
                    relative = Path(item['path'])
                    path = (project / relative).resolve()
                    if relative.is_absolute() or not path.is_relative_to(project):
                        raise ValueError('Diagnostic path escapes project')
                    if path in paths:
                        raise ValueError('Duplicate diagnostic path')
                    paths[path] = item
                state_entry = paths.get(self.state_path)
                if (self.config_path not in paths or not isinstance(state_entry, dict)
                        or state_entry.get('existed') is not True
                        or not _diagnostic_sha256(manifest.get('old_state_sha256'))
                        or not _diagnostic_sha256(manifest.get('new_state_sha256'))
                        or state_entry.get('before_sha256') != manifest['old_state_sha256']
                        or state_entry.get('after_sha256') != manifest['new_state_sha256']):
                    continue
                if state_digest is None:
                    with self.state_path.open('rb') as handle:
                        state_raw = handle.read(32 * 1024 * 1024 + 1)
                    if len(state_raw) > 32 * 1024 * 1024:
                        return None
                    state_digest = hashlib.sha256(state_raw).hexdigest()
                if manifest.get('fenced_state_sha256') == state_digest:
                    return {'manifest_path': str(manifest_path), 'status': manifest['status'],
                            'phase': manifest['phase'], 'evidence': 'matching_fingerprint_state_bytes_and_paths',
                            'execution_authority': False}
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                continue
        return None

    def _state_binding_error(self, value):
        """Diagnostic I/O cannot change the binding refusal or contact a host."""
        persisted = value.get('config_fingerprint')
        disk_fingerprint, disk_status = None, 'unavailable'
        try:
            with self.config_path.open('rb') as handle:
                raw = handle.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError('Connector exceeds diagnostic read limit')
            disk = _diagnostic_object(raw)
            if (disk.get('schema_version') != '1.0'
                    or any(field in disk and type(disk[field]) is not bool
                           for field in ('enabled', 'observe_on_prompt'))
                    or _path(self.config_path.parent, disk.get('state_file'), 'state_file') != self.state_path):
                raise ValueError('Current connector cannot establish the same state binding')
            disk_fingerprint = hashlib.sha256(json.dumps(disk, sort_keys=True,
                ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            disk_status = ('matches_persisted_state' if disk_fingerprint == persisted else
                           'matches_loaded_configuration' if disk_fingerprint == self.config_fingerprint
                           else 'different_from_loaded_configuration_and_state')
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            pass
        try:
            manifest = self._matching_activation_fence(persisted)
        except Exception:
            manifest = None
        classification = ('known_uncommitted_activation_fence' if manifest is not None else
                          'stale_configuration_snapshot' if disk_fingerprint is not None
                          and disk_fingerprint == persisted else 'state_binding_cause_unconfirmed')
        return StateBindingError(classification, disk_configuration=disk_status, manifest=manifest)

    @contextmanager
    def _locked(self):
        with ExitStack() as stack:
            remaining = self._check_request_budget('before_state_lock')
            with span('queue.wait', kind='queue'):
                try:
                    stack.enter_context(_state_lock(self.state_path,
                        timeout_s=20 if remaining is None else min(20, remaining)))
                except StateLockTimeoutError as exc:
                    if remaining is None:
                        raise
                    annotate(request_budget_status='busy', request_budget_stage='state_lock_wait')
                    raise RequestBudgetError('busy', 'state_lock_wait') from exc
            self._check_request_budget('after_state_lock')
            existed = self.state_path.exists()
            with span('state.load', kind='io'):
                value = _read_object(self.state_path) if existed else {
                    "schema_version": "1.0", "config_fingerprint": self.config_fingerprint,
                    "runtime": None, "inflight": None}
            if value.get("schema_version") != "1.0":
                raise ValueError("Invalid live service state")
            if value.get("config_fingerprint") != self.config_fingerprint:
                raise self._state_binding_error(value)
            if existed and (not isinstance(value.get("runtime"), dict)
                            or "inflight" not in value
                            or value["inflight"] is not None and (
                                not isinstance(value["inflight"], dict) or
                                not {"operation_id", "session_id", "started"}.issubset(value["inflight"]))):
                raise ValueError("Corrupt persisted live runtime; do not silently reset host authority")
            inflight = value.get("inflight")
            if inflight is not None and (any(not isinstance(inflight[k], str) or not inflight[k]
                                            for k in ("operation_id", "session_id"))
                    or type(inflight["started"]) not in (int, float) or not np.isfinite(inflight["started"])):
                raise ValueError("Invalid pending host operation")
            runtime = self._runtime()
            if self._perception_cache is not None:
                runtime.router.scene_cache = self._perception_cache
            if existed:
                runtime.import_state(value["runtime"])
            # Retain only this process's verified exact-content memo values.
            # Disk contributes validated scene history, never cached measurements.
            self._perception_cache = runtime.router.scene_cache
            from .goal_execution import validate_segment_ledger
            validate_segment_ledger(value)
            if 'goal_supervision' in value:
                from .goal_journal import validate_goal_journal
                validate_goal_journal(value)
            if 'goal_authorizations' in value or any(identity.startswith('auth-goal:') for identity in
                    value.get('goal_supervision', {}).get('records', {})):
                from .task_authority import validate_authorizations
                validate_authorizations(value)
            self._check_request_budget('after_state_restore')
            yield value, runtime

    def _save(self, value, runtime, *, _observation_baseline=None):
        self._check_request_budget('before_state_write')
        with span('state.persist', kind='io'):
            self._perception_cache = runtime.router.scene_cache
            with span('state.persist.export'):
                value["runtime"] = runtime.export_state()
            with span('state.persist.size_encode', kind='encoding'):
                encoded = json.dumps(value, ensure_ascii=True, allow_nan=False)
            if len(encoded) > 32 * 1024 * 1024:
                raise ValueError("Live state exceeds 32 MiB; reduce scene/session limits")
            unchanged = False
            if (type(_observation_baseline) is dict
                    and type(_observation_baseline.get('runtime')) is dict
                    and _observation_baseline.get('inflight') is None
                    and value.get('inflight') is None):
                with span('state.persist.compare', kind='encoding'):
                    # Only a read-only observation supplies its lock-scoped,
                    # already validated loaded state. Compare the full JSON,
                    # including ledger/order and numeric spelling, not dict ==
                    # (which conflates bool/int/float and signed zero). JSON
                    # intentionally gives imported lists and exported tuples
                    # the same representation. No saved clock is refreshed.
                    unchanged = (_state_json_matches(encoded, _observation_baseline,
                        checkpoint=lambda: self._check_request_budget('during_state_comparison'))
                        and self.state_path.is_file())
            # Export, size checking and comparison can exhaust the budget.
            # Recheck immediately before entering the existing atomic writer;
            # its internal serialization/fsync/replace is not preempted.
            self._check_request_budget('before_atomic_state_write')
            if unchanged:
                with span('state.persist.skip_unchanged', kind='io'):
                    pass  # Existing durable bytes already represent this state.
                return
            # The existing ASCII encoding bounds both compact text length and
            # Unicode widening. Larger states retain the streaming writer.
            with span('state.persist.atomic_write', kind='io'):
                request = _REQUEST_BUDGET.get()
                writes = request['state_writes'] if request is not None and request['service'] is self else None
                receipt = {'status': 'unknown'}
                if writes is not None:
                    writes['attempts'] += 1
                try:
                    _atomic_write(self.state_path, value,
                        _buffered=len(encoded) <= _STATE_WRITE_BUFFER_LIMIT, _commit_receipt=receipt)
                    receipt['status'] = 'committed'
                finally:
                    if writes is not None:
                        writes['last_status'] = receipt['status']
                        writes['commits'] += receipt['status'] == 'committed'
                        writes['unknowns'] += receipt['status'] == 'unknown'

    def record_event(self, event, **fields):
        """Minimal operational evidence; no user prompts, source code or mesh data."""
        # Pin the producer, including rejected requests and reused hook traces.
        # Caller-supplied evidence must not impersonate a different runtime.
        fields['runtime_identity'] = {key: self._identity[key] for key in
            ('implementation_revision', 'build_id', 'source_kind')}
        fields['identity_check'] = copy.deepcopy(self._identity_check)
        trace = current_trace()
        if event == 'request_trace' and isinstance(fields.get('trace'), dict):
            # Trace writers run after their ContextVar has been restored. Use
            # their delivered record, without copying all in-progress spans on
            # every operational audit line.
            fields['trace_id'] = fields['trace'].get('trace_id')
            fields['request_id'] = fields['trace'].get('request_id')
        elif trace is not None:
            fields['trace_id'] = trace.trace_id
            fields['request_id'] = trace.request_id
        return write_audit_event(self.audit_path, event, lock_factory=_state_lock, **fields)

    @staticmethod
    def _pair(scene, focal_id=None, reference_id=None, config=None):
        cfg = config or {}
        meshes = scene["meshes"]
        by_id = {m["object_id"]: m for m in meshes}
        def resolve(value, field):
            if value is None:
                name = cfg.get(field + "_name")
                found = [m["object_id"] for m in meshes if m["name"] == name] if name else []
                return found[0] if len(found) == 1 else None
            if value not in by_id:
                raise ValueError("Unknown " + field + "_id")
            return value
        focal_id = resolve(focal_id, "focal")
        reference_id = resolve(reference_id, "reference")
        if focal_id is None:
            active = [m["object_id"] for m in meshes if m["is_focal_target"]]
            if len(active) == 1:
                focal_id = active[0]
        if focal_id and reference_id is None:
            remaining = [m["object_id"] for m in meshes if m["object_id"] != focal_id]
            if len(remaining) == 1:
                reference_id = remaining[0]
        return focal_id, reference_id

    @staticmethod
    def _observation_pair(scene, task_instruction, focal_id, reference_id, config, fingerprint):
        """Bind a natural-language observation only to the current captured scene.

        Explicit complete IDs retain their original contract. An unsupported or
        ambiguous prompt must not silently select a configured/active object or
        the only remaining mesh. Empty-instruction callers keep that legacy
        host-selection behavior. None of these bindings authorizes a transform.
        """
        if not task_instruction.strip() or (focal_id is not None and reference_id is not None):
            focal_id, reference_id = LiveSpatialService._pair(scene, focal_id, reference_id, config)
            return focal_id, reference_id, None
        by_id = {mesh['object_id'] for mesh in scene['meshes']}
        for role, supplied in (('focal', focal_id), ('reference', reference_id)):
            if supplied is not None and supplied not in by_id:
                raise ValueError('Unknown ' + role + '_id')
        resolution = resolve_prompt_pair(scene, task_instruction, scene_fingerprint=fingerprint)
        if resolution['status'] != 'resolved':
            return None, None, resolution
        if ((focal_id is not None and focal_id != resolution['focal_id'])
                or (reference_id is not None and reference_id != resolution['reference_id'])):
            resolution = {**resolution, 'status': 'unresolved', 'focal_id': None, 'reference_id': None,
                          'reason_codes': ['explicit_pair_conflict']}
            return None, None, resolution
        return resolution['focal_id'], resolution['reference_id'], resolution

    def _overview(self, scene, meshes, fingerprint, session_id, include_image=True):
        """A single mesh has useful perception, but no clearance pair to certify."""
        facts = {"source": "human_eye_live_blender_scene_overview", "unit": "m",
                 "coordinate_frame": "world", "scene_revision": scene["revision"],
                 "pair_required_for_clearance": True,
                 "host_execution": copy.deepcopy(scene.get("host_execution")),
                 "objects": [{"object_id": m.object_id, "name": m.name,
                              "mark_label": m.mark_label, "bbox_min": m.bbox_min.tolist(),
                              "bbox_max": m.bbox_max.tolist()} for m in meshes]}
        capabilities = build_scene_capabilities(scene, require_host_execution=self.production_mode,
            scene_fingerprint=fingerprint, object_ids=[mesh.object_id for mesh in meshes[:8]])
        facts['scene_capabilities'] = capabilities
        picture = None
        try:
            if not include_image:
                raise ValueError("image_not_requested_by_text_only_host")
            active = [m.object_id for m in meshes if m.is_focal_target]
            with span('overview.render'):
                image, visual_metadata = render_scene_canvas(meshes, self.config.get("quad_size", 128),
                    focal_id=active[0] if len(active) == 1 else None)
            with span('overview.png', kind='encoding'):
                stream = io.BytesIO(); image.save(stream, format="PNG")
            with span('overview.base64', kind='encoding'):
                picture = {"type": "image", "mimeType": "image/png",
                           "data": base64.b64encode(stream.getvalue()).decode("ascii")}
            facts["canvas"] = visual_metadata
        except ValueError as exc:
            facts["canvas"] = {"omitted": "text_only_host_delivery" if not include_image
                               else "rendering_resource_or_numeric_limit", "detail": str(exc)}
        return {"schema_version": "1.0", "event": "before_model", "session_id": session_id,
                "route": "engine", "reason_codes": ["scene_overview_pair_required"],
                "scene_revision": scene["revision"], "scene_fingerprint": fingerprint,
                "observation_id": None, "cache_hit": False, "engine_invoked": True,
                "allow_action": None, "measurement_valid": None, "axes_valid": None,
                "context_text": json.dumps(facts, ensure_ascii=True), "image": picture,
                'scene_capabilities': capabilities,
                "requires_reobserve": True, "execution_scope": "scene_overview_only"}

    @_request('observe')
    def observe(self, session_id, task_instruction="", focal_id=None, reference_id=None, *, include_image=True,
                goal=None, query=None, task_context=None, scene_delta=None):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id required")
        if not isinstance(task_instruction, str):
            raise ValueError("task_instruction must be text")
        if type(include_image) is not bool:
            raise ValueError("include_image must be boolean")
        query = validate_query(query)
        if query['mode'] == 'surface_nearest':
            selector = query['objects'][0] if 'objects' in query else None
            if selector is not None and focal_id is not None:
                raise ValueError('surface_nearest accepts query.objects or focal_id, not both')
            if (include_image or (selector is None and (type(focal_id) is not str or not focal_id.strip()
                    or len(focal_id.encode('utf8')) > 256)) or reference_id is not None
                    or goal is not None or scene_delta is not None):
                raise ValueError('surface_nearest requires one target, include_image=false and no reference, goal or scene_delta')
            return self._observe_surface_nearest(session_id, focal_id, selector=selector)
        if query['mode'] == 'task':
            if (include_image or focal_id is not None or reference_id is not None
                    or goal is not None or scene_delta is not None):
                raise ValueError('task queries require include_image=false and selectors only in query.objects or query.target/query.candidates')
            return self._observe_task(session_id, query)
        if query['mode']=='mesh_surface':
            if goal is not None or reference_id is not None or scene_delta is not None:raise ValueError('Surface reads do not accept pair goals or scene deltas')
            from .surface_task_service import observe
            return observe(self,session_id,query,include_image=include_image,focal_id=focal_id)
        if query['mode']=='mesh_structure':
            if goal is not None or reference_id is not None or scene_delta is not None:
                raise ValueError('Structure task does not accept pair goals, reference objects or scene deltas')
            from .structure_task_service import observe
            return observe(self,session_id,query,include_image=include_image,focal_id=focal_id)
        if query.get('alignment_evidence') is False and include_image:
            raise ValueError('alignment_evidence=false requires include_image=false')
        scene_delta = validate_scene_delta_request(scene_delta)
        if not self.config.get("enabled", True):
            return {"status": "disabled", "session_id": session_id, "routing": None}
        rejected = self._identity_rejection()
        if rejected is not None:
            return rejected
        with self._locked() as (value, runtime), self._observation_scope():
            if value.get("inflight") or runtime.status["quarantined"]:
                return {"status": "host_quarantined", "session_id": session_id, "routing": None}
            # import_state detaches live sessions/history from this loaded
            # runtime. Retain that large dictionary by reference; copy every
            # other envelope field so a ledger edit cannot mask a change.
            observation_baseline = ({key: old if key == 'runtime' else copy.deepcopy(old)
                for key, old in value.items()} if type(value.get('runtime')) is dict else None)
            self._check_request_budget('before_host_capture')
            with span('host.capture', kind='host'):
                captured = self.host.capture_scene()
            self._check_request_budget('after_host_capture')
            observation_capture = None
            with span('scene.validate'):
                if _reuse_observation_capture(captured):
                    observation_capture = _ValidatedObservation(captured)
                    scene, meshes, fingerprint = (observation_capture.scene,
                        observation_capture.meshes, observation_capture.fingerprint)
                else:
                    scene, meshes, fingerprint = _validated_scene(captured)
            delta_base = None
            if scene_delta:
                delta_base = runtime.router.scene_cache.find_snapshot(
                    scene_delta['base_revision'], scene_delta['base_fingerprint'])
            with span('observation.resolve_prompt_pair'):
                focal_id, reference_id, pair_resolution = self._observation_pair(
                    scene, task_instruction, focal_id, reference_id, self.config, fingerprint)
            query = validate_query(query, object_ids=[m['object_id'] for m in scene['meshes']], focal_id=focal_id)
            goal = _bound_goal(goal, focal_id, reference_id)
            visual_delivery, native_caps = self._native_visual_policy(query,include_image,focal_id,reference_id)
            projection_requested=include_image and native_caps is None
            if focal_id and reference_id:
                prepared = runtime._before_model_on_captured_scene(scene=scene,
                    session_id=session_id, task_instruction=task_instruction,
                    focal_id=focal_id, reference_id=reference_id, messages=[], format="mcp",
                    include_image=projection_requested, supports_images=projection_requested,
                    final_include_image=include_image, query=query,
                    _validated_observation=observation_capture)
                routing = prepared["routing"]
                status = ("partial" if routing.get("observation_status") == "partial" else "observed") if routing["route"] == "engine" else "blocked"
                if 'support_plane_discovery' in query and 'support_plane_discovery' not in routing:
                    discovery = {'status': 'unknown', 'candidates': [],
                        'total_candidate_count': None, 'omitted_candidate_count': None,
                        'ambiguous': None, 'reason_codes': ['observation_pipeline_blocked'],
                        'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
                        'focal_id': focal_id, 'reference_id': reference_id,
                        'scope': 'current_pair_support_plane_discovery_not_execution_authorization',
                        'execution_authority': False}
                    routing['support_plane_discovery'] = discovery
                    facts = json.loads(routing['context_text'])
                    facts['support_plane_discovery'] = copy.deepcopy(discovery)
                    routing['context_text'] = json.dumps(facts, ensure_ascii=True, allow_nan=False)
            else:
                observation_capture = None
                routing = self._overview(scene, meshes, fingerprint, session_id, projection_requested)
                facts = json.loads(routing['context_text'])
                facts['scene_memory'] = runtime.router.scene_cache.record_scene(scene)
                facts['attention'] = {'decision': 'hold', 'reason_codes': ['contact_pair_not_established']}
                overview_query = {'mode': query['mode'],
                    'status': 'complete' if query['mode'] == 'overview' else 'unknown',
                    'requested_object_ids': list(query.get('object_ids', [])),
                    'exact_object_ids': [], 'unresolved_object_ids': list(query.get('object_ids', [])),
                    'ranked_object_ids': None, 'max_exact_pairs': query['max_exact_pairs'],
                    'exact_pair_count': 0,
                    'reason_codes': [] if query['mode'] == 'overview' else ['query_pair_required']}
                if query['mode'] == 'top1':
                    overview_query['top1'] = {'status': 'unknown', 'nearest_object_ids': None,
                        'unique': None, 'signed_clearance_m': None,
                        'excluded_by_lower_bound_ids': [], 'comparison_guard_m': None,
                        'pruning_threshold_m': None,
                        'proof_method': 'exact_candidates_and_strict_outward_aabb_lower_bounds',
                        'tie_scope': 'equal_unrounded_engine_distances_not_physical_equivalence',
                        'execution_authority': False}
                facts['query_result'] = overview_query
                if 'support_plane_discovery' in query:
                    facts['support_plane_discovery'] = {
                        'status': 'unsupported', 'candidates': [],
                        'total_candidate_count': 0, 'omitted_candidate_count': 0,
                        'ambiguous': None, 'reason_codes': ['target_pair_not_established'],
                        'scene_revision': scene['revision'], 'scene_fingerprint': fingerprint,
                        'focal_id': focal_id, 'reference_id': reference_id,
                        'scope': 'current_pair_support_plane_discovery_not_execution_authorization',
                        'execution_authority': False}
                    routing['support_plane_discovery'] = copy.deepcopy(facts['support_plane_discovery'])
                if query.get('visual_diagnostic') == 'contact_section':
                    facts['visual_diagnostics'] = {'kind': 'contact_section', 'status': 'unavailable',
                        'reason': 'exact_target_pair_not_established', 'execution_authority': False,
                        'natural_visibility_certified': False}
                if query.get('label_object_ids'):
                    facts['label_presentation'] = {
                        'status': 'unavailable', 'reason': 'target_pair_not_established',
                        'visual_focus_requested_ids': list(query['label_object_ids']),
                        'scope': 'display_request_only_not_geometry_or_execution',
                        'execution_authority': False}
                routing['query_result'] = copy.deepcopy(overview_query)
                routing['context_text'] = json.dumps(facts, ensure_ascii=True, allow_nan=False)
                status = "overview"
                # Unpaired observation cannot retain a previous clearance token.
                state = runtime.export_state()
                state["sessions"] = [item for item in state["sessions"] if item[0] != session_id]
                runtime.import_state(state)
            if pair_resolution is not None:
                # Observation-local evidence travels through both text hooks
                # and MCP brief projection; it is not cached execution state.
                facts = json.loads(routing['context_text'])
                facts['pair_resolution'] = copy.deepcopy(pair_resolution)
                routing['context_text'] = json.dumps(facts, ensure_ascii=True, allow_nan=False)
            # Validate before state commit, but attach pixels only to a detached
            # delivery after _save. Neither cache nor authority history stores
            # native PNG bytes, a private audit or the native public plan.
            native_visual = None
            if native_caps is not None:
                if routing.get('route')=='engine':
                    native_visual=self._read_native_visual(captured,native_caps,focal_id,reference_id,query)
                else:
                    visual_delivery.update(source='none',status='unavailable',
                        reason_code='observation_pipeline_blocked')
            self._save(value, runtime, _observation_baseline=(observation_baseline
                if routing.get('cache_hit') is True else None))
            routing=copy.deepcopy(routing)
            if native_visual is not None:
                routing.pop('image',None)
                routing['images']=native_visual['images']
                visual_delivery.update(status='delivered',image_count=len(native_visual['images']),
                    plan=native_visual['plan'])
                facts=json.loads(routing['context_text'])
                facts['canvas']={'source':'blender_native_multiscale','image_count':len(native_visual['images']),
                    'framing':'native_overview_with_optional_local_window',
                    'visibility_scope':'one_central_ray_not_complete_visibility', 'execution_authority':False}
                if native_visual['plan']['schema_version']=='native-task-gap-plan-v2':
                    facts['canvas'].update(visibility_scope='three_samples_not_complete_visibility',
                        task_quality_scope='bounded_axis_box_gap_opportunity_not_pixel_metrology')
                elif native_visual['plan']['schema_version']=='native-dense-focus-plan-v3':
                    facts['canvas'].update(task_quality_scope='projected_bounds_opportunity_not_thin_section_or_complete_visibility')
                routing['context_text']=json.dumps(facts,ensure_ascii=True,allow_nan=False)
            elif include_image:
                count=int(routing.get('image') is not None)
                visual_delivery.update(status='delivered' if count else 'unavailable',image_count=count)
            result = {"status": status, "implementation_revision": IMPLEMENTATION_REVISION,
                      'runtime_identity': self.describe_runtime(),
                      "session_id": session_id, "routing": routing,
                       "query_result": copy.deepcopy(routing.get('query_result')),
                       "host_execution": copy.deepcopy(scene.get("host_execution")),
                      "objects": [{k: m[k] for k in ("object_id", "name", "mark_label")} for m in scene["meshes"]],
                      'visual_delivery':visual_delivery, **_goal_fields(scene, goal)}
            if pair_resolution is not None:
                result['pair_resolution'] = copy.deepcopy(pair_resolution)
            if 'support_plane_discovery' in routing:
                result['support_plane_discovery'] = copy.deepcopy(routing['support_plane_discovery'])
            if scene_delta is not None:
                from .scene_delta import make_scene_delta
                with span('observation.delta_transport', kind='encoding'):
                    try:
                        result['scene_transport'] = make_scene_delta(delta_base, scene)
                    except ValueError:
                        if delta_base is None:
                            raise
                        # Old history can predate a newer metadata contract.
                        # Rebuild delivery from the current validated capture;
                        # do not reset history, pending writes or quarantine.
                        result['scene_transport'] = make_scene_delta(None, scene)
                        result['scene_transport_diagnostic'] = {
                            'base_status': 'invalid_or_unusable_full_resync',
                            'execution_authority': False}
        self.record_event("observe", session_id=session_id, status=status,
            scene_revision=routing["scene_revision"], engine_invoked=routing["engine_invoked"])
        return result

    def _observe_surface_nearest(self, session_id, focal_id, *, selector=None):
        """One current candidate capture through the existing read-only boundary."""
        from .task_query import surface_nearest_result
        if not self.config.get('enabled', True):
            return {'status': 'disabled', 'session_id': session_id, 'routing': None}
        context = self._read_context
        with context.lock, self._observation_scope():
            rejected, source_check = self._read_source_identity()
            if rejected is not None:
                return copy.deepcopy(rejected)
            # Sample the destination clock first so conversion cannot extend an
            # earlier parent deadline. The connector also caps its own timeout.
            now = time.perf_counter_ns()
            remaining = self._check_request_budget('before_host_capture')
            timeout = getattr(self.host, 'timeout_s', 10.)
            deadline = now + int((timeout if remaining is None else min(timeout, remaining)) * 1e9)
            with span('host.capture', kind='host'):
                if selector is None:
                    captured = self.host.capture_nearest_candidates(focal_id, deadline, 64 * 1024 * 1024)
                else:
                    captured = self.host.capture_nearest_candidates(None, deadline, 64 * 1024 * 1024, selector=selector)
            self._check_request_budget('after_host_capture')
            if selector is not None:
                field = 'object_id' if 'id' in selector else 'name'
                selected = selector.get('id', selector.get('name'))
                capture = captured.get('capture')
                if type(capture) is not dict or type(capture.get('meshes')) is not list:
                    raise ValueError('surface_nearest capture selector mismatch')
                matches = [item.get('object_id') for item in capture['meshes'] if type(item) is dict and item.get(field) == selected]
                if (len(matches) != 1 or type(matches[0]) is not str or not matches[0]
                        or len(matches[0].encode('utf8')) > 256 or captured.get('focal_id') != matches[0]):
                    raise ValueError('surface_nearest capture selector mismatch')
            elif captured.get('focal_id') != focal_id:
                raise ValueError('surface_nearest capture focal_id mismatch')
            selection = {'focal_id': focal_id, 'selector': selector}
            context.activate(captured.get('capture'), 'surface_nearest', selection)
            def normalize():
                return context.normalized(lambda: _validated_scene(captured.get('capture'),
                    _surface_nearest_capture=True, _annotate_scene=False))
            with span('observation.surface_nearest'):
                work = {'kernel_calls': 0}
                result, hit = context.result('surface_nearest', lambda: surface_nearest_result(
                    captured, context.scene_cache, self._check_request_budget, diagnostics=work,
                    _normalize=normalize, _identity=self._identity))
                work['result_cache_hit'] = hit
            names = {item['object_id']: item['name'] for item in captured['capture']['meshes']}
            def named(oid):
                return {'id': oid, 'name': names[oid]}
            result['focal'] = named(result.pop('focal_id'))
            nearest = result.pop('nearest_ids')
            result['nearest_objects'] = None if nearest is None else [named(oid) for oid in nearest]
            result['best_known_objects'] = [named(oid) for oid in result.pop('best_known_ids')]
            result['unresolved'] = [dict(named(oid), reason=reason)
                for oid, reason in sorted(result['unresolved'].items())]
            result.pop('excluded')
            self._bind_read_result(result, source_check)
        self.record_event('observe', session_id=session_id, status=result['status'],
            scene_revision=result['binding']['scene_revision'],
            engine_invoked=work['kernel_calls'] > 0, task_work=work)
        self._check_request_budget('before_surface_nearest_result')
        return result

    def _observe_task(self, session_id, query):
        """Finite current-capture query, independent of action persistence."""
        from .task_query import task_result
        if not self.config.get('enabled', True):
            return {'status': 'disabled', 'session_id': session_id, 'routing': None}
        context = self._read_context
        with context.lock, self._observation_scope():
            rejected, source_check = self._read_source_identity()
            if rejected is not None:
                return copy.deepcopy(rejected)
            self._check_request_budget('before_host_capture')
            task_capture = getattr(self.host, 'capture_task_scene', None)
            selected_capture = callable(task_capture)
            with span('host.capture', kind='host'):
                captured = task_capture(query['objects']) if selected_capture else self.host.capture_scene()
            self._check_request_budget('after_host_capture')
            context.activate(captured, 'task_selected' if selected_capture else 'task_full',
                query['objects'] if selected_capture else None)
            with span('scene.validate'):
                scene, meshes, fingerprint = context.normalized(
                    lambda: _validated_scene(captured, _task_capture=selected_capture))
            with span('observation.task_facts'):
                from .read_context import query_key
                work = {'exact_pair_count': 0, 'surface_pair_count': 0, 'closed_solid_pair_count': 0}
                result, hit = context.result(query_key(query), lambda: task_result(
                    scene, meshes, fingerprint, query, context.scene_cache,
                    self._check_request_budget, diagnostics=work))
                work['result_cache_hit'] = hit
            self._bind_read_result(result, source_check)
        self.record_event('observe', session_id=session_id, status=result['status'],
            scene_revision=scene['revision'],
            engine_invoked=(work['exact_pair_count'] > 0 or work.get('surface_pair_count', 0) > 0
                            or work.get('closed_solid_pair_count', 0) > 0), task_work=work)
        self._check_request_budget('before_task_result')
        return result

    @staticmethod
    def _identified(action):
        if not isinstance(action, dict) or any(not isinstance(action.get(k), str) or not action[k]
                                             for k in ("focal_id", "reference_id")):
            raise ValueError("Structured action requires focal_id and reference_id")
        return action["focal_id"], action["reference_id"]

    def _prepare(self, runtime, session_id, action, include_image=True):
        self._check_request_budget('before_prepare_host_capture')
        focal, reference = self._identified(action)
        # Every execution boundary can prepare the observation automatically.
        # The caller need not choose a separate inspect tool first.
        return runtime.before_model(session_id=session_id,
            task_instruction="Automatic observation before structured rigid transform.",
            focal_id=focal, reference_id=reference, messages=[], format="mcp",
            include_image=False, supports_images=False, final_include_image=include_image)

    @_request('preview')
    def preview_action(self, session_id, action, *, include_image=True, task_context=None):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id required")
        if type(include_image) is not bool:
            raise ValueError("include_image must be boolean")
        action = copy.deepcopy(action)
        rejected = self._identity_rejection()
        if rejected is not None:
            return rejected
        if not self.config.get("enabled", True):
            return {"status": "disabled", "allow_action": False}
        self._identified(action)
        with self._locked() as (value, runtime):
            if value.get("inflight"):
                return {"status": "host_quarantined", "allow_action": False}
            self._check_request_budget('before_preview_host_capture')
            result = runtime._prepare_and_preview(session_id=session_id, action=action, include_image=include_image)
            self._save(value, runtime)
        self.record_event("preview", session_id=session_id, allow_action=result["allow_action"])
        return result

    @_request('transform')
    def transform(self, session_id, action, *, goal=None, task_context=None):
        rejected = self._identity_rejection()
        if rejected is not None:
            return rejected
        if not self.config.get("enabled", True):
            return {"status": "disabled", "executed": False, "verified": False, "routing": None}
        action = copy.deepcopy(action)
        focal_id, reference_id = self._identified(action)
        goal = _bound_goal(goal, focal_id, reference_id)
        with self._locked() as (value, runtime):
            if 'goal_supervision' in value or 'goal_authorizations' in value:
                from .goal_supervision import write_blocker
                reason = write_blocker(value)
                if reason is not None:
                    return runtime._result('segment_interrupted', allow_action=False,
                        reason_codes=[reason])
            from .goal_execution import unfinished_segment
            if unfinished_segment(value):
                return runtime._result('segment_interrupted', allow_action=False,
                    reason_codes=['unfinished_goal_segment_requires_review'])
            return self._transform_locked(value, runtime, session_id, action, goal)

    def _transform_locked(self, value, runtime, session_id, action, goal=None, *,
                          prepared=None, segment_step=None, segment_id=None, precommit_deadline=None,
                          precommit_clock=None, parent_deadline=None):
        """Shared single-step core; caller already owns the durable state lock."""
        if value.get("inflight") or runtime.status["quarantined"]:
            return {"status": "host_quarantined", "executed": False, "verified": False, "routing": None}
        prepared = self._prepare(runtime, session_id, action) if prepared is None else prepared
        capability = prepared.get('host_execution')
        if isinstance(capability, dict) and capability.get('supported') is False:
            self._save(value, runtime)
            return runtime._result('blocked', routing=prepared['routing'], allow_action=False,
                **_capability_rejection({'host_execution': capability}))
        if prepared['routing'].get('observation_status') == 'partial':
            self._save(value, runtime)
            return runtime._result('blocked', routing=prepared['routing'], allow_action=False,
                reason_codes=['partial_observation_not_actionable'])
        route = prepared['routing']
        if (route.get('route') != 'engine' or route.get('requires_reobserve')
                or route.get('measurement_valid') is not True
                or route.get('rigid_frame_valid', route.get('axes_valid')) is not True):
            # Preparation already knows why this request cannot write. Do
            # not journal an impossible operation or lose its evidence by
            # calling execute_action with no registered host session.
            reasons = list(route.get('reason_codes') or [])
            if route.get('route') == 'engine':
                reasons.append('unverified_geometry_or_frame')
            if not reasons:
                reasons.append('observation_not_actionable')
            self._save(value, runtime)
            return runtime._result('blocked', routing=route, allow_action=False,
                reason_codes=list(dict.fromkeys(reasons)))
        # Recheck after waiting/capture: the host bridge loads helper source
        # on demand, so edits during this request must require a restart.
        rejected = self._identity_rejection()
        if rejected is not None:
            return rejected
        # Journal before any call that could mutate Blender. If this process
        # disappears or the final state cannot be written, keep it blocked.
        value["inflight"] = {"operation_id": uuid.uuid4().hex, "session_id": session_id,
                              "started": time.time()}
        if segment_step is not None:
            segment_step.update(state="submitting", operation_id=value["inflight"]["operation_id"])
            value["inflight"].update(segment_id=segment_id, step_id=segment_step["step_id"])
        self._save(value, runtime)
        self._submitted_request()
        execute_options = {} if precommit_deadline is None else {
            '_before_commit': lambda: (precommit_clock or time.monotonic)() < precommit_deadline}
        context = self._supervisor_context
        if parent_deadline is not None and context is not None and getattr(context,'commit_guard',None) is not None:
            execute_options['_commit_guard']=lambda:context.commit_guard(value)
        if (parent_deadline is not None and context is not None
                and context.forward_deadline is not None):
            execute_options['_host_deadline'] = context.forward_deadline(parent_deadline, precommit_deadline)
        result = runtime.execute_action(session_id=session_id, action=action, goal=goal, **execute_options)
        self._remember_execution_result(result)
        result['runtime_identity'] = self.describe_runtime()
        if goal is not None and result.get("goal_evaluation") == "not_requested":
            result["goal_evaluation"] = "not_evaluated"
        if result.get("status") in {"verified", "no_op", "blocked", "invalid_action", "invalid_goal", "observation_required"}:
            value["inflight"] = None
        if segment_step is not None:
            from .goal_execution import record_step_result
            record_step_result(segment_step, result)
        # Uncertain results keep the durable journal as well as quarantine.
        self._save(value, runtime)
        self.record_event("transform", session_id=session_id, status=result["status"],
                          executed=result.get("executed"), verified=result.get("verified"))
        return result

    @_request('mesh_structure')
    def observe_mesh_structure(self, session_id, object_id, *,
                               categories=('boundary_edges','loose_edges','isolated_vertices'),
                               include_image=False, task_context=None):
        """Private M1 raw observation; public MCP/Hook adoption has its own gate."""
        if include_image is not False:raise ValueError('Raw structure observation has no images')
        from .mesh_structure_service import observe
        return observe(self,session_id,object_id,categories)

    @_request('patch_observation')
    def observe_patch(self, session_id, object_id, patch, *, include_image=True, task_context=None):
        """Private M1-03 patch image candidate; public routing remains gated."""
        if include_image is not True:raise ValueError('Patch observation is an explicit image request')
        from .patch_observation import observe
        return observe(self,session_id,object_id,patch)

    @_request('clearance_segment')
    def run_clearance_segment(self, session_id, request_id, request, *, execute=False,
                              include_image=False, task_context=None):
        """Preview or execute one bounded goal; model-selected IDs are not authority."""
        from .goal_execution import run_clearance_segment
        return run_clearance_segment(self, session_id, request_id, request,
                                     execute=execute, include_image=include_image)

    @_request('goal_supervision')
    def goal_supervision(self, operation, goal_id, session_id=None, *,
                         request_id=None, request=None, limits=None):
        """Private host integration, not exposed as an MCP action endpoint."""
        from .goal_supervision import update
        return update(self, operation, goal_id, session_id, request_id=request_id,
                      request=request, limits=limits)

    @_request('supervised_clearance_segment')
    def run_supervised_clearance_segment(self, goal_id, session_id, request_id,
                                         request, *, include_image=False):
        """Trusted caller still owns task authorization and fresh review."""
        from .goal_supervision import _context
        _context(self)
        from .goal_execution import run_clearance_segment
        return run_clearance_segment(self, session_id, request_id, request,
            execute=True, include_image=include_image, _parent_goal_id=goal_id)

    @_request('status')
    def status(self):
        with self._locked() as (value, runtime):
            supervision = {}
            if 'goal_authorizations' in value:
                from .task_authority import blocking_authorization
                supervision['task_authorization'] = {
                    'records': len(value['goal_authorizations']['records']),
                    'blocking_authorization': blocking_authorization(value),
                    'source': 'trusted_embedding_callback_not_model_JSON',
                }
            if 'goal_supervision' in value:
                from .goal_journal import blocking_goal
                supervision['goal_supervision'] = {
                    'records': len(value['goal_supervision']['records']),
                    'blocking_goal_id': blocking_goal(value),
                    'trusted_context_available': self._supervisor_context is not None,
                    'automatic_mcp_endpoint': False,
                }
            return {"implementation_revision": IMPLEMENTATION_REVISION,
                    'runtime_identity': self.describe_runtime(),
                    "enabled": self.config.get("enabled", True), "connection": "live_blender_mcp",
                    "host_connectivity_checked": False,
                    "inflight_operation": bool(value.get("inflight")), **runtime.status,
                    "goal_segment_receipts": len(value.get('goal_segments', {}).get('records', {})),
                    "unfinished_goal_segment": any(entry['status'] == 'running' for entry in
                        value.get('goal_segments', {}).get('records', {}).values()),
                    **supervision,
                    "state_file": str(self.state_path), "execution_scope": "terminal_geometry_only"}


__all__ = ["LiveSpatialService", "RequestBudgetError", "StateBindingError"]
