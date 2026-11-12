"""Attach the checked scene boundary to an already running BlenderMCP addon.

Only fixed capture/apply code is sent to the loopback addon. Model text and
arbitrary Python are never accepted by this API. Each request uses a fresh TCP
connection and a matching random nonce, because BlenderMCP's JSON transport has
no request identifiers or framing. No addon is installed, started, or changed.

``transaction`` serializes callers of this object only. Other Blender tools can
still edit the scene; the Blender-side revision/fingerprint comparison is the
actual mutation boundary. This connector does not intercept those other tools.
An ambiguous transport failure invalidates this instance and is never retried.
Scoped observations may reconnect on a later call only when establishing the
socket failed before any request could be sent; the failing call is not retried.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import errno
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import select
import socket
import threading
import time
from typing import Any, Iterator
import uuid
import zlib

from .blender_process import (HostRemoteError, HostTransportError, NATIVE_OBSERVATION_PROTOCOL,
    _validate_native_observation_capabilities, _validate_native_observation_request, _validate_arm_twist_report)
from .blender_host import PREWRITE_REFUSAL_PROTOCOL, validate_prewrite_refusal
from .scene_residency import SceneDeltaDecoder


RPC_PREFIX = "HUMAN_EYE_BLENDER_MCP:"
PROTOCOL_VERSION = "1.0"
_MAX_REQUEST_BYTES = 32 * 1024
_MAX_RESIDENT_INIT_BYTES = 1024 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_OBSERVATION_UNPROBED = object()
_OBSERVATION_COMMANDS=frozenset({'capture_directory','capture_task','capture_nearest_candidates','capture_surface_scan','native_observation_capabilities','observe_readonly_native','last_readonly_native_audit'})
_STRUCTURE_COMMANDS=frozenset({'observe_arm_twist','mesh_structure_capabilities','observe_mesh_structure','mesh_region_summary_capabilities',
    'observe_mesh_structure_summary','patch_observation_capabilities','observe_patch',
    'nonplanar_observation_capabilities','observe_nonplanar_patch','surface_geometry_capabilities','observe_surface_geometry','capture_surface_source','reference_view_capabilities','observe_reference_patch'})
_READONLY_COMMANDS = _OBSERVATION_COMMANDS | _STRUCTURE_COMMANDS | {'capture', 'capture_evidence'}
_JSON_STRING_EVENT = re.compile(rb'["\\]')
_JSON_CONTAINER_EVENT = re.compile(rb'[{}\[\]"]')


class _JSONObjectBoundary:
    """Recognize a possible outer endpoint while the strict loader owns syntax."""

    def __init__(self):
        self.started = self.in_string = self.escape_pending = False
        self.depth = 0

    def feed(self, chunk):
        pos = 0
        if not self.started:
            while pos < len(chunk) and chunk[pos] in b' \t\r\n':
                pos += 1
            if pos == len(chunk):
                return False
            if chunk[pos] != 123:
                raise ValueError('BlenderMCP response must be a JSON object')
            self.started = True
        if self.escape_pending:
            pos += 1
            self.escape_pending = False
        while pos < len(chunk):
            event = (_JSON_STRING_EVENT if self.in_string else _JSON_CONTAINER_EVENT).search(chunk, pos)
            if event is None:
                return False
            token = chunk[event.start()]
            pos = event.end()
            if self.in_string:
                if token == 92:
                    if pos == len(chunk):
                        self.escape_pending = True
                    else:
                        pos += 1
                else:
                    self.in_string = False
            elif token == 34:
                self.in_string = True
            elif token in (123, 91):
                self.depth += 1
            else:
                self.depth -= 1
                if self.depth == 0:
                    return True
        return False


class _ReadonlyPreconnectUnavailable(HostTransportError):
    """The connector failed before obtaining a socket or sending any request."""


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON constant: " + value)


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite JSON number")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _loads(data):
    return json.loads(data, parse_constant=_reject_constant,
                      parse_float=_finite_float, object_pairs_hook=_unique_object)


class BlenderMCPHost:
    """Use the existing loopback BlenderMCP service, without owning Blender.

    ``project_root`` must identify trusted engine source on the same machine as
    Blender. Closing this connection never closes Blender or saves its file.
    All mutation requests need a revision and are rechecked inside Blender.
    """

    prewrite_refusal_protocol = PREWRITE_REFUSAL_PROTOCOL

    def __init__(self, project_root, host="127.0.0.1", port=9876,
                 timeout_s=15):
        if host == "localhost":
            host = "127.0.0.1"
        try:
            address = ipaddress.ip_address(host)
        except (TypeError, ValueError) as exc:
            raise ValueError("BlenderMCP host must be a numeric loopback address") from exc
        if not address.is_loopback:
            raise ValueError("BlenderMCP host must be a loopback address")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be an integer in 1..65535")
        if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
                or not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("timeout_s must be finite and greater than zero")
        root = Path(project_root).expanduser().resolve()
        source = (root / "human_eye_plugin" / "blender_host.py").resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("project_root must contain trusted human_eye_plugin/blender_host.py")
        self.project_root, self.source = root, source
        with source.open('rb') as stream:source_bytes=stream.read(512*1024+1)
        if len(source_bytes)>512*1024:
            raise ValueError('Readonly host source exceeds its fixed connector bound')
        self._readonly_host_source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        helper_source = source.with_name('scene_residency.py')
        helper_bytes = helper_source.read_bytes()
        if len(helper_bytes) > 128 * 1024:
            raise ValueError('Scene residency helper exceeds its connector bound')
        self._readonly_scene_residency_sha256 = hashlib.sha256(helper_bytes).hexdigest()
        self._resident_sources = ((str(helper_source), base64.b64encode(zlib.compress(helper_bytes)).decode('ascii')),
                                  (str(source), base64.b64encode(zlib.compress(source_bytes)).decode('ascii')))
        self._resident_expert_sources = {}
        self._readonly_arm_twist_sources_sha256 = {}
        expert_bytes = []
        for name in ('rig_pose.py', 'arm_twist_weights.py', 'arm_twist_expert.py', 'arm_twist_source.py'):
            path = source.with_name(name)
            if not path.is_file():
                continue  # Minimal SDK roots can still use ordinary capture.
            if not path.resolve().is_relative_to(root):
                raise ValueError('Arm twist dependency is outside the trusted root')
            blob = path.read_bytes()
            if len(blob) > 512 * 1024:
                raise ValueError('Arm twist dependency exceeds its source bound')
            expert_bytes.append(blob)
            self._readonly_arm_twist_sources_sha256['human_eye_plugin/' + name] = hashlib.sha256(blob).hexdigest()
            self._resident_expert_sources[name] = base64.b64encode(zlib.compress(blob)).decode('ascii')
        self._resident_tag = hashlib.sha256(source_bytes + helper_bytes + b''.join(expert_bytes)).hexdigest()
        self._resident_slot = '_human_eye_mcp_resident_' + hashlib.sha256(str(root).encode('utf8')).hexdigest()[:20]
        self._resident_ready = False
        self._scene_decoder = SceneDeltaDecoder()
        self.host, self.port, self.timeout_s = str(address), port, float(timeout_s)
        self._lock = threading.RLock()
        self._closed = False
        self._poisoned = False
        self._native_observation_caps = _OBSERVATION_UNPROBED
        self._observation_depth = 0
        self._observation_document_epoch = _OBSERVATION_UNPROBED

    @property
    def is_alive(self) -> bool:
        """Local connection validity; this property does not probe Blender."""
        return not self._closed and not self._poisoned

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _ensure_live(self):
        if not self.is_alive:
            raise HostTransportError("BlenderMCP connection is closed or invalidated; observe with a new host")

    @contextmanager
    def transaction(self) -> Iterator["BlenderMCPHost"]:
        with self._lock:
            self._ensure_live()
            yield self

    @contextmanager
    def observation_transaction(self) -> Iterator["BlenderMCPHost"]:
        """Serialize a read-only call without reviving invalidated connections.

        Only a failure to establish the socket is recoverable on a later call.
        The caller still receives that failure, and no request is retried.
        """
        with self._lock:
            self._observation_depth += 1
            try:
                yield self
            finally:
                self._observation_depth -= 1

    def _record_observation_document(self, result):
        identity = result.get('host_identity') if isinstance(result, dict) else None
        epoch = identity.get('document_epoch') if isinstance(identity, dict) else None
        if (not isinstance(epoch, str) or len(epoch) != 64
                or any(char not in '0123456789abcdef' for char in epoch)):
            # Older capture contracts permit identities that cannot identify a
            # native runtime. Leave capture validation to its original owner,
            # and never reuse positive or negative capabilities across them.
            self._native_observation_caps = _OBSERVATION_UNPROBED
            self._observation_document_epoch = _OBSERVATION_UNPROBED
            return
        if epoch != self._observation_document_epoch:
            self._native_observation_caps = _OBSERVATION_UNPROBED
            self._observation_document_epoch = epoch

    def capture_scene(self) -> dict[str, Any]:
        return self._request("capture", {})

    def capture_task_scene(self, selectors) -> dict[str, Any]:
        return self._request('capture_task', {'selectors': selectors})

    def capture_directory(self, deadline_ns, max_response_bytes):
        now = time.perf_counter_ns()
        if type(deadline_ns) is not int or now >= deadline_ns:
            raise ValueError('directory_deadline_exceeded')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_RESPONSE_BYTES:
            raise ValueError('directory_document_budget')
        deadline_ns = min(deadline_ns, now + int(self.timeout_s * 1e9))
        result = self._request('capture_directory', dict(deadline_ns=deadline_ns,
            max_response_bytes=max_response_bytes))
        if time.perf_counter_ns() >= deadline_ns:
            raise ValueError('directory_deadline_exceeded')
        return result

    def capture_nearest_candidates(self, focal_id, deadline_ns, max_response_bytes, *, selector=None):
        if selector is None:
            if type(focal_id) is not str or not focal_id or len(focal_id.encode('utf8')) > 256:
                raise ValueError('acquisition_focal_id')
        else:
            if focal_id is not None:
                raise ValueError('acquisition_focal_selector_conflict')
            if (type(selector) is not dict or set(selector) not in ({'id'}, {'name'})
                    or any(type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256
                           for value in selector.values())):
                raise ValueError('acquisition_selector')
            selector = dict(selector)
        now_ns = time.perf_counter_ns()
        if type(deadline_ns) is not int or now_ns >= deadline_ns:
            raise ValueError('acquisition_deadline_exceeded')
        # The host cannot outlive this connector's shorter transport allowance.
        # Min preserves an earlier parent deadline and starts before encoding.
        deadline_ns = min(deadline_ns, now_ns + int(self.timeout_s * 1_000_000_000))
        if deadline_ns <= now_ns:
            raise ValueError('acquisition_deadline_exceeded')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_RESPONSE_BYTES:
            raise ValueError('acquisition_document_budget')
        params = {'focal_id': focal_id, 'deadline_ns': deadline_ns, 'max_response_bytes': max_response_bytes}
        if selector is not None:
            params['selector'] = selector
        result = self._request('capture_nearest_candidates', params)
        if time.perf_counter_ns() >= deadline_ns:
            raise ValueError('acquisition_deadline_exceeded')
        binding = result.get('binding')
        if (type(binding) is not dict or result.get('protocol') != 'single-read-surface-candidates-v1'
                or result.get('execution_authority') is not False
                or binding.get('host_source_sha256') != self._readonly_host_source_sha256):
            raise ValueError('acquisition_response_binding')
        if selector is None:
            if result.get('focal_id') != focal_id:
                raise ValueError('acquisition_response_binding')
        else:
            capture = result.get('capture')
            meshes = capture.get('meshes') if type(capture) is dict else None
            if type(meshes) is not list or any(type(mesh) is not dict for mesh in meshes):
                raise ValueError('acquisition_response_binding')
            key, value = next(iter(selector.items()))
            field = 'object_id' if key == 'id' else 'name'
            matches = [mesh.get('object_id') for mesh in meshes if mesh.get(field) == value]
            if (len(matches) != 1 or type(matches[0]) is not str or not matches[0]
                    or len(matches[0].encode('utf8')) > 256
                    or result.get('focal_id') != matches[0]):
                raise ValueError('acquisition_response_binding')
        self._record_observation_document(binding)
        return result

    def capture_surface_scan(self, threshold_m, deadline_ns, max_response_bytes):
        if type(threshold_m) not in (int, float):
            raise ValueError('surface_scan_threshold')
        try:
            threshold_m = float(threshold_m)
        except OverflowError as exc:
            raise ValueError('surface_scan_threshold') from exc
        if not math.isfinite(threshold_m) or threshold_m < 0:
            raise ValueError('surface_scan_threshold')
        now_ns = time.perf_counter_ns()
        if type(deadline_ns) is not int or now_ns >= deadline_ns:
            raise ValueError('acquisition_deadline_exceeded')
        deadline_ns = min(deadline_ns, now_ns + int(self.timeout_s * 1_000_000_000))
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_RESPONSE_BYTES:
            raise ValueError('acquisition_document_budget')
        result = self._request('capture_surface_scan', dict(threshold_m=float(threshold_m),
            deadline_ns=deadline_ns, max_response_bytes=max_response_bytes))
        if time.perf_counter_ns() >= deadline_ns:
            raise ValueError('acquisition_deadline_exceeded')
        binding = result.get('binding')
        if (type(binding) is not dict or result.get('protocol') != 'single-read-surface-scan-v1'
                or result.get('threshold_m') != threshold_m or result.get('execution_authority') is not False
                or binding.get('host_source_sha256') != self._readonly_host_source_sha256):
            raise ValueError('acquisition_response_binding')
        self._record_observation_document(binding)
        return result

    def capture_evidence(self) -> dict[str, Any]:
        return self._request('capture_evidence', {})

    def observe_arm_twist(self, selection):
        if type(selection) is not dict:
            raise ValueError('Arm twist selection requires an object')
        return _validate_arm_twist_report(self._request('observe_arm_twist', {'selection': selection}), selection)

    def native_observation_capabilities(self):
        with self._lock:
            self._ensure_live()
            if self._native_observation_caps is _OBSERVATION_UNPROBED:
                value=self._request('native_observation_capabilities',{})
                self._native_observation_caps=(None if value=={'supported':False} else
                    _validate_native_observation_capabilities(value,source=self.source))
            value=self._native_observation_caps
            return None if value is None else _validate_native_observation_capabilities(value,source=self.source)

    def observe_readonly_native(self, request_id, focal_id, reference_id,
                                expected_capture_revision, deadline_ns, view='SCENE'):
        if self.native_observation_capabilities() is None:
            raise ValueError('Typed readonly native observation is unavailable')
        _validate_native_observation_request(request_id,focal_id,reference_id,
            expected_capture_revision,deadline_ns,view)
        return self._request('observe_readonly_native',{'request_id':request_id,'focal_id':focal_id,
            'reference_id':reference_id,'expected_capture_revision':expected_capture_revision,
            'deadline_ns':deadline_ns,'view':view})

    def last_readonly_native_audit(self, request_id):
        if self.native_observation_capabilities() is None:
            raise ValueError('Typed readonly native observation is unavailable')
        _validate_native_observation_request(request_id,diagnostic=True)
        return self._request('last_readonly_native_audit',{'request_id':request_id})

    def reference_view_capabilities(self):
        value=self._request('reference_view_capabilities',{})
        _validate_native_observation_capabilities(value['native'],source=self.source)
        return value

    def observe_reference_patch(self,request_id,object_id,patch,deadline_ns):
        return self._request('observe_reference_patch',dict(request_id=request_id,object_id=object_id,patch=patch,deadline_ns=deadline_ns))

    def surface_geometry_capabilities(self):
        return self._request('surface_geometry_capabilities',{})

    def capture_surface_source(self,request_id,object_id,deadline_ns):
        return self._request('capture_surface_source',dict(request_id=request_id,object_id=object_id,deadline_ns=deadline_ns))

    def observe_surface_geometry(self,request_id,object_id,deadline_ns,near_m):
        return self._request('observe_surface_geometry',dict(request_id=request_id,object_id=object_id,deadline_ns=deadline_ns,near_m=near_m))

    def mesh_structure_capabilities(self):
        return self._request('mesh_structure_capabilities',{})

    def mesh_region_summary_capabilities(self):
        return self._request('mesh_region_summary_capabilities',{})

    def observe_mesh_structure_summary(self,request_id,object_id,categories,deadline_ns):
        return self._request('observe_mesh_structure_summary',dict(request_id=request_id,object_id=object_id,
            categories=categories,deadline_ns=deadline_ns))

    def observe_mesh_structure(self,request_id,object_id,categories,deadline_ns):
        return self._request('observe_mesh_structure',dict(request_id=request_id,object_id=object_id,
            categories=categories,deadline_ns=deadline_ns))

    def patch_observation_capabilities(self):
        value=self._request('patch_observation_capabilities',{})
        _validate_native_observation_capabilities(value['native'],source=self.source)
        return value

    def observe_patch(self,request_id,object_id,patch,deadline_ns):
        return self._request('observe_patch',dict(request_id=request_id,object_id=object_id,
            patch=patch,deadline_ns=deadline_ns))

    def nonplanar_observation_capabilities(self):
        value=self._request('nonplanar_observation_capabilities',{})
        _validate_native_observation_capabilities(value['native'],source=self.source)
        return value

    def observe_nonplanar_patch(self,request_id,object_id,patch,deadline_ns,mode):
        return self._request('observe_nonplanar_patch',dict(request_id=request_id,object_id=object_id,
            patch=patch,deadline_ns=deadline_ns,mode=mode))

    def begin_motion_goal(self, goal_id, focal_id, reference_id, limits=None):
        return self._request('motion_begin', {'goal_id':goal_id, 'focal_id':focal_id,
                                             'reference_id':reference_id, 'limits':limits})

    def motion_goal_status(self, goal_id, after_event_count=0):
        return self._request('motion_status', {'goal_id':goal_id, 'after_event_count':after_event_count})

    def end_motion_goal(self, goal_id):
        return self._request('motion_end', {'goal_id':goal_id})

    def apply_transform(self, action, expected_revision, expected_fingerprint=None, request_nonce=None):
        allowed = {"focal_id", "reference_id", "translation", "rotation_euler_deg"}
        if (not isinstance(action, dict) or set(action) - allowed
                or not {"translation", "rotation_euler_deg"}.intersection(action)
                or not isinstance(action.get("focal_id"), str) or not action["focal_id"]
                or ("reference_id" in action and (
                    not isinstance(action["reference_id"], str) or not action["reference_id"]))):
            raise ValueError("action must identify an object and an explicit delta SE(3)")
        for field in ("translation", "rotation_euler_deg"):
            if field in action:
                value = action[field]
                if (not isinstance(value, (list, tuple)) or len(value) != 3
                        or any(isinstance(x, bool) or not isinstance(x, (int, float))
                               or not math.isfinite(x) for x in value)):
                    raise ValueError(field + " must contain three finite numbers")
        if not isinstance(expected_revision, str) or not expected_revision:
            raise ValueError("expected_revision must be a nonempty string")
        if expected_fingerprint is not None and (
                not isinstance(expected_fingerprint, str) or not expected_fingerprint):
            raise ValueError("expected_fingerprint must be a nonempty string or None")
        params = {"action": action, "expected_revision": expected_revision,
                  "expected_fingerprint": expected_fingerprint}
        if request_nonce is not None:
            params["request_nonce"] = request_nonce
        return self._request("apply", params)

    def _code(self, command, params, request_id):
        if command in _STRUCTURE_COMMANDS:
            return self._structure_code(command, params, request_id)
        if command in _OBSERVATION_COMMANDS:
            return self._observation_code(command, params, request_id)
        if command in {'capture_evidence', 'motion_begin', 'motion_status', 'motion_end'}:
            return self._supervision_code(command, params, request_id)
        if command not in {'capture', 'apply'}:
            raise ValueError('Unsupported fixed host command')
        return self._resident_code(command, params, request_id, 4096)

    def _resident_setup(self):
        # Source is frozen in this connector once. Only the first dispatch
        # carries those bytes; warm RPCs only look up the live host.
        lines = ["    import sys as _sys", "    _module = _sys.modules.get(" + repr(self._resident_slot) + ")"]
        if not self._resident_ready:
            helper, source = self._resident_sources
            lines += [
                "    if _module is None or getattr(_module, '_resident_tag', None) != " + repr(self._resident_tag) + ":",
                "        import importlib.util as _iu, base64 as _b64, zlib as _zl",
                "        if _module is not None:",
                "            _old = getattr(_module, '_mcp_resident_host', None)",
                "            if _old is not None: _old.close_residency()",
                "        _helper_spec = _iu.spec_from_file_location('_human_eye_scene_residency', " + repr(helper[0]) + ")",
                "        _helper = _iu.module_from_spec(_helper_spec)",
                "        _sys.modules['_human_eye_scene_residency'] = _helper",
                "        exec(compile(_zl.decompress(_b64.b64decode(" + repr(helper[1]) + ")), " + repr(helper[0]) + ", 'exec', dont_inherit=True), _helper.__dict__)",
                "        _spec = _iu.spec_from_file_location(" + repr(self._resident_slot) + ", " + repr(source[0]) + ")",
                "        _module = _iu.module_from_spec(_spec)",
                "        _sys.modules[" + repr(self._resident_slot) + "] = _module",
                "        exec(compile(_zl.decompress(_b64.b64decode(" + repr(source[1]) + ")), " + repr(source[0]) + ", 'exec', dont_inherit=True), _module.__dict__)",
                "        _module._READONLY_LOADED_HOST_SHA256 = " + repr(self._readonly_host_source_sha256),
                "        _module._mcp_resident_host = _module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)",
                "        _module._mcp_resident_host._residency_module = _helper",
                "        _module._mcp_resident_host._residency = _helper.SceneResidency(bpy)",
                "        _module._mcp_resident_host._arm_twist_dependency_sources = {n: _zl.decompress(_b64.b64decode(v)) for n, v in " + repr(self._resident_expert_sources) + ".items()}",
                "        _module._resident_tag = " + repr(self._resident_tag),
            ]
        lines += [
            "    if _module is None or getattr(_module, '_resident_tag', None) != " + repr(self._resident_tag) + ": raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')",
            "    _host = _module._mcp_resident_host",
        ]
        return lines

    def _resident_code(self, command, params, request_id, limit):
        request = json.dumps({'id': request_id, 'command': command, 'params': params},
                             ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        if len(request.encode('utf8')) > limit:
            raise ValueError('Fixed host request exceeds ' + str(limit) + ' bytes')
        methods = {'capture': 'capture_scene', 'capture_task': 'capture_task_scene',
                   'motion_begin': 'begin_motion_goal', 'motion_status': 'motion_goal_status',
                   'motion_end': 'end_motion_goal', 'apply': 'apply_transform'}
        method = methods.get(command, command)
        lines = ['import json as _json, contextlib as _cl, io as _io',
                 '_request = _json.loads(' + repr(request) + ')', 'try:']
        lines += self._resident_setup()
        if command == 'native_observation_capabilities':
            lines.append("    _result = _host.native_observation_capabilities() if getattr(_host, 'native_observation_protocol', None) == " + repr(NATIVE_OBSERVATION_PROTOCOL) + " else {'supported': False}")
        else:
            lines += ['    with _cl.redirect_stdout(_io.StringIO()):',
                      '        _result = getattr(_host, ' + repr(method) + ")(**_request['params'])"]
        if command in {'capture', 'capture_task', 'capture_nearest_candidates', 'capture_surface_scan'}:
            baseline = json.dumps(self._scene_decoder.baseline(), allow_nan=False, separators=(',', ':'))
            lines.append('    _result = _host.capture_delta(_result, _json.loads(' + repr(baseline) + '))')
        lines += [
            "    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}",
            'except Exception as _exc:',
            "    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}",
            'print(' + repr(RPC_PREFIX) + " + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))",
        ]
        return '\n'.join(lines)

    def _supervision_code(self, command, params, request_id):
        required = {'capture_evidence': set(), 'motion_begin': {'goal_id', 'focal_id', 'reference_id', 'limits'},
                    'motion_status': {'goal_id', 'after_event_count'}, 'motion_end': {'goal_id'}}
        if command not in required or type(params) is not dict or set(params) != required[command]:
            raise ValueError('Invalid fixed supervision command')
        return self._resident_code(command, params, request_id, 4096)

    def _observation_code(self, command, params, request_id):
        required = {'capture': set(), 'capture_evidence': set(), 'capture_task': {'selectors'},
            'capture_directory': {'deadline_ns', 'max_response_bytes'},
            'capture_nearest_candidates': {'focal_id', 'deadline_ns', 'max_response_bytes'},
            'capture_surface_scan': {'threshold_m', 'deadline_ns', 'max_response_bytes'},
            'native_observation_capabilities': set(),
            'observe_readonly_native': {'request_id', 'focal_id', 'reference_id', 'expected_capture_revision', 'deadline_ns', 'view'},
            'last_readonly_native_audit': {'request_id'}}
        if command == 'capture_nearest_candidates' and type(params) is dict and 'selector' in params:
            required[command] = required[command] | {'selector'}
        if command not in required or type(params) is not dict or set(params) != required[command]:
            raise ValueError('Invalid fixed native observation command')
        return self._resident_code(command, params, request_id, 8192 if command == 'capture_task' else 4096)

    def _structure_code(self, command, params, request_id):
        required = {'reference_view_capabilities': set(), 'observe_reference_patch': {'request_id', 'object_id', 'patch', 'deadline_ns'},
            'capture_surface_source': {'request_id', 'object_id', 'deadline_ns'}, 'surface_geometry_capabilities': set(),
            'observe_surface_geometry': {'request_id', 'object_id', 'deadline_ns', 'near_m'},
            'mesh_structure_capabilities': set(), 'mesh_region_summary_capabilities': set(),
            'observe_mesh_structure_summary': {'request_id', 'object_id', 'categories', 'deadline_ns'},
            'patch_observation_capabilities': set(), 'observe_patch': {'request_id', 'object_id', 'patch', 'deadline_ns'},
            'nonplanar_observation_capabilities': set(),
            'observe_nonplanar_patch': {'request_id', 'object_id', 'patch', 'deadline_ns', 'mode'},
            'observe_mesh_structure': {'request_id', 'object_id', 'categories', 'deadline_ns'},
            'observe_arm_twist': {'selection'}}
        if command not in required or type(params) is not dict or set(params) != required[command]:
            raise ValueError('Invalid fixed structure observation command')
        return self._resident_code(command, params, request_id,
            _MAX_RESIDENT_INIT_BYTES if command == 'observe_arm_twist' else 16384)

    def _fail(self, message):
        self._poisoned = True
        raise HostTransportError(message)

    def _request(self, command, params):
        with self._lock:
            if self._observation_depth and command not in _READONLY_COMMANDS:
                raise ValueError('Only fixed read-only commands are allowed during observation')
            self._ensure_live()
            request_id = uuid.uuid4().hex
            code = (self._observation_code(command, params, request_id)
                    if self._observation_depth and command in {'capture','capture_evidence'}
                    else self._code(command, params, request_id))
            payload = json.dumps({"type": "execute_code", "params": {"code": code}},
                                 allow_nan=False, separators=(",", ":")).encode("utf-8")
            request_limit = (_MAX_RESIDENT_INIT_BYTES if not self._resident_ready or command == 'observe_arm_twist' else
                             64 * 1024 if command in {'capture', 'capture_task', 'capture_nearest_candidates', 'capture_surface_scan'} else _MAX_REQUEST_BYTES)
            if len(payload) > request_limit:
                raise ValueError("BlenderMCP request exceeds the transport size limit")
            try:
                outer = self._exchange(payload)
                if (not isinstance(outer, dict) or outer.get("status") != "success"
                        or set(outer) != {"status", "result"}):
                    raise ValueError("BlenderMCP returned an unsuccessful or unexpected response")
                executed = outer["result"]
                if (not isinstance(executed, dict) or set(executed) != {"executed", "result"}
                        or executed["executed"] is not True or not isinstance(executed["result"], str)):
                    raise ValueError("BlenderMCP execute_code response is invalid")
                output = executed["result"]
                if (not output.startswith(RPC_PREFIX) or not output.endswith("\n")
                        or "\n" in output[:-1] or "\r" in output):
                    raise ValueError("BlenderMCP output must contain exactly one fixed host envelope")
                response = _loads(output[len(RPC_PREFIX):-1])
                if (not isinstance(response, dict) or response.get("id") != request_id
                        or response.get("protocol_version") != PROTOCOL_VERSION
                        or set(response) not in ({"protocol_version", "id", "result"},
                                                 {"protocol_version", "id", "error"})):
                    raise ValueError("BlenderMCP host response identity or protocol does not match")
                if "error" in response:
                    error = response["error"]
                    if (not isinstance(error, dict) or set(error) != {"type", "message", "mutation_uncertain"}
                            or not isinstance(error["type"], str) or not isinstance(error["message"], str)
                            or type(error["mutation_uncertain"]) is not bool):
                        raise ValueError("BlenderMCP host error envelope is invalid")
                    if command == "apply" or error["mutation_uncertain"]:
                        self._fail("Blender mutation could not be verified: " + error["message"])
                    raise HostRemoteError(error)
                result = response["result"]
                if not isinstance(result, dict):
                    raise ValueError("BlenderMCP host result must be an object")
                self._resident_ready = True
                if command in {'capture', 'capture_task', 'capture_nearest_candidates', 'capture_surface_scan'}:
                    result = self._scene_decoder.apply(result)
                if command == 'capture_directory':
                    self._record_observation_document(result.get('binding', {}))
                if self._observation_depth and command in {'capture', 'capture_evidence', 'capture_task'}:
                    capture = result.get('capture') if command == 'capture_evidence' else result
                    self._record_observation_document(capture)
                if command == "apply" and (result.get("status") == "rejected_before_mutation" or "rejection" in result):
                    validate_prewrite_refusal(result, action=params["action"],
                        expected_revision=params["expected_revision"],
                        expected_fingerprint=params["expected_fingerprint"],
                        request_nonce=params.get("request_nonce"))
                return result
            except HostRemoteError:
                raise
            except _ReadonlyPreconnectUnavailable:
                if self._observation_depth and command in _READONLY_COMMANDS:
                    self._native_observation_caps = _OBSERVATION_UNPROBED
                else:
                    self._poisoned = True
                raise
            except HostTransportError:
                self._poisoned = True
                raise
            except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError, RecursionError) as exc:
                self._fail("BlenderMCP response unavailable or invalid; execution outcome unknown: " + str(exc))

    def _connect(self, deadline):
        """Open one numeric loopback socket within the request's deadline.

        Explicit nonblocking completion avoids the timed connect path's extra
        wait on this Windows runtime. Writable readiness alone is insufficient:
        the socket's completion error must also be checked. No retry is made.
        """
        if deadline - time.monotonic() <= 0:
            raise TimeoutError("BlenderMCP connection timed out")
        address = ipaddress.ip_address(self.host)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        target = (self.host, self.port)
        if address.version == 6:
            numeric, separator, scope = self.host.partition('%')
            scope_id = (int(scope) if scope.isdecimal() else socket.if_nametoindex(scope)) if separator else 0
            if not 0 <= scope_id <= 0xffffffff:
                raise ValueError("BlenderMCP IPv6 scope is outside the socket range")
            target = (numeric, self.port, 0, scope_id)
        connection = socket.socket(family, socket.SOCK_STREAM)
        try:
            connection.setblocking(False)
            result = connection.connect_ex(target)
            if result != 0:
                pending = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                           10035, 10036, 10037}
                if result not in pending:
                    raise OSError(result, "BlenderMCP connection failed")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("BlenderMCP connection timed out")
                _, writable, exceptional = select.select([], [connection], [connection], remaining)
                if not writable and not exceptional:
                    raise TimeoutError("BlenderMCP connection timed out")
                error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    raise OSError(error, "BlenderMCP connection completion failed")
                if exceptional:
                    raise OSError("BlenderMCP connection reported exceptional readiness")
                if connection not in writable:
                    raise OSError("BlenderMCP connection did not become writable")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("BlenderMCP connection timed out")
            connection.settimeout(remaining)
            return connection
        except BaseException:
            connection.close()
            raise

    def _exchange(self, payload):
        # The addon keeps sockets open. Scan new bytes to find the outer endpoint.
        deadline = time.monotonic() + self.timeout_s
        try:
            connection = self._connect(deadline)
        except (OSError, TimeoutError) as exc:
            if self._observation_depth:
                raise _ReadonlyPreconnectUnavailable(
                    'BlenderMCP unavailable before read-only request was sent; no retry was made') from exc
            raise
        with connection:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("BlenderMCP connection timed out")
            connection.settimeout(remaining)
            connection.sendall(payload)
            buffer = bytearray()
            boundary = _JSONObjectBoundary()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("BlenderMCP request timed out")
                connection.settimeout(remaining)
                chunk = connection.recv(min(65536, _MAX_RESPONSE_BYTES + 1 - len(buffer)))
                if not chunk:
                    raise ValueError("BlenderMCP disconnected before a complete response")
                buffer.extend(chunk)
                if len(buffer) > _MAX_RESPONSE_BYTES:
                    raise ValueError("BlenderMCP response exceeds the size limit")
                if boundary.feed(chunk):
                    return _loads(buffer.decode("utf-8"))


__all__ = ["BlenderMCPHost", "HostTransportError", "HostRemoteError"]
