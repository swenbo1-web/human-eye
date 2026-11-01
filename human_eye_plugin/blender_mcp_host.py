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
import errno
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import select
import socket
import threading
import time
from typing import Any, Iterator
import uuid

from .blender_process import (HostRemoteError, HostTransportError, NATIVE_OBSERVATION_PROTOCOL,
    _validate_native_observation_capabilities, _validate_native_observation_request)
from .blender_host import PREWRITE_REFUSAL_PROTOCOL, validate_prewrite_refusal


RPC_PREFIX = "HUMAN_EYE_BLENDER_MCP:"
PROTOCOL_VERSION = "1.0"
_MAX_REQUEST_BYTES = 32 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
_OBSERVATION_UNPROBED = object()
_OBSERVATION_COMMANDS=frozenset({'native_observation_capabilities','observe_readonly_native','last_readonly_native_audit'})
_STRUCTURE_COMMANDS=frozenset({'mesh_structure_capabilities','observe_mesh_structure','mesh_region_summary_capabilities',
    'observe_mesh_structure_summary','patch_observation_capabilities','observe_patch',
    'nonplanar_observation_capabilities','observe_nonplanar_patch'})
_READONLY_COMMANDS = _OBSERVATION_COMMANDS | _STRUCTURE_COMMANDS | {'capture', 'capture_evidence'}


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

    def capture_evidence(self) -> dict[str, Any]:
        return self._request('capture_evidence', {})

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
            return self._structure_code(command,params,request_id)
        if command in _OBSERVATION_COMMANDS:
            return self._observation_code(command,params,request_id)
        if command in {'capture_evidence', 'motion_begin', 'motion_status', 'motion_end'}:
            return self._supervision_code(command, params, request_id)
        # JSON is a Python string literal, never interpolated as executable code.
        request = json.dumps({"id": request_id, "command": command, "params": params},
                             ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if len(request.encode("utf-8")) > 4096:
            raise ValueError("Blender transform request exceeds 4096 bytes")
        return "\n".join([
            "import importlib.util as _iu, json as _json",
            "_request = _json.loads(" + repr(request) + ")",
            "try:",
            "    _spec = _iu.spec_from_file_location('_human_eye_blender_mcp_host', " + repr(str(self.source)) + ")",
            "    if _spec is None or _spec.loader is None: raise RuntimeError('Cannot load trusted Blender host')",
            "    _module = _iu.module_from_spec(_spec)",
            "    _spec.loader.exec_module(_module)",
            "    _host_options = {'bpy_module': bpy, 'execution_metadata': True}",
            "    if getattr(_module.BlenderSceneHost, 'identity_metadata_protocol', None) == 'host-identity-v1-20261026': _host_options['identity_metadata'] = True",
            "    _host = _module.BlenderSceneHost(**_host_options)",
            "    if _request['command'] == 'capture':",
            "        _result = _host.capture_scene()",
            "    elif _request['command'] == 'apply':",
            "        _result = _host.apply_transform(**_request['params'])",
            "    else: raise ValueError('Unsupported fixed host command')",
            "    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}",
            "except Exception as _exc:",
            "    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}",
            "print(" + repr(RPC_PREFIX) + " + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))",
        ])

    def _supervision_code(self, command, params, request_id):
        """Separate fixed template; legacy capture/apply code bytes stay fixed."""
        request = json.dumps({'id':request_id, 'command':command, 'params':params},
                             ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        if len(request.encode('utf-8')) > 4096:
            raise ValueError('Host supervision request exceeds 4096 bytes')
        return '\n'.join([
            'import importlib.util as _iu, json as _json',
            '_request = _json.loads(' + repr(request) + ')',
            'try:',
            "    _spec = _iu.spec_from_file_location('_human_eye_blender_mcp_host', " + repr(str(self.source)) + ')',
            "    if _spec is None or _spec.loader is None: raise RuntimeError('Cannot load trusted Blender host')",
            '    _module = _iu.module_from_spec(_spec)',
            '    _spec.loader.exec_module(_module)',
            '    _host = _module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)',
            "    if _request['command'] == 'capture_evidence':",
            "        if _request['params']: raise ValueError('capture_evidence accepts no arguments')",
            '        _result = _host.capture_evidence()',
            "    elif _request['command'] == 'motion_begin':",
            "        if set(_request['params']) != {'goal_id','focal_id','reference_id','limits'}: raise ValueError('Invalid motion_begin arguments')",
            "        _result = _host.begin_motion_goal(**_request['params'])",
            "    elif _request['command'] == 'motion_status':",
            "        if set(_request['params']) != {'goal_id','after_event_count'}: raise ValueError('Invalid motion_status arguments')",
            "        _result = _host.motion_goal_status(**_request['params'])",
            "    elif _request['command'] == 'motion_end':",
            "        if set(_request['params']) != {'goal_id'}: raise ValueError('Invalid motion_end arguments')",
            "        _result = _host.end_motion_goal(**_request['params'])",
            "    else: raise ValueError('Unsupported fixed supervision command')",
            "    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}",
            'except Exception as _exc:',
            "    _envelope = {'protocol_version':'1.0', 'id':_request['id'], 'error':{'type':type(_exc).__name__, 'message':str(_exc)[:2000], 'mutation_uncertain':False}}",
            'print(' + repr(RPC_PREFIX) + " + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))",
        ])

    def _observation_code(self, command, params, request_id):
        """Separate constant read-only template; legacy template bytes are kept."""
        required={'capture':set(),'capture_evidence':set(),'native_observation_capabilities':set(),
            'observe_readonly_native':{'request_id','focal_id','reference_id','expected_capture_revision','deadline_ns','view'},
            'last_readonly_native_audit':{'request_id'}}
        if command not in required or type(params) is not dict or set(params)!=required[command]:
            raise ValueError('Invalid fixed native observation command')
        request=json.dumps({'id':request_id,'command':command,'params':params},
            ensure_ascii=True,allow_nan=False,separators=(',',':'))
        if len(request.encode('utf8'))>4096:raise ValueError('Native observation request exceeds4096bytes')
        return '\n'.join([
            'import importlib.util as _iu, json as _json, contextlib as _cl, io as _io, hashlib as _hl',
            '_request = _json.loads('+repr(request)+')',
            'try:',
            '    from pathlib import Path as _Path',
            '    _source = _Path('+repr(str(self.source))+')',
            "    if _source.resolve()!=_source: raise ValueError('Readonly host source escaped its fixed root')",
            "    with _source.open('rb') as _stream: _source_bytes = _stream.read(512*1024+1)",
            '    _source_sha = _hl.sha256(_source_bytes).hexdigest()',
            '    if len(_source_bytes)>512*1024 or _source_sha!='+repr(self._readonly_host_source_sha256)+": raise ValueError('Readonly host source differs from the fixed connector snapshot')",
            "    _spec = _iu.spec_from_file_location('_human_eye_blender_native_read', "+repr(str(self.source))+')',
            "    if _spec is None or _spec.loader is None: raise RuntimeError('Cannot load trusted native read host')",
            '    _module = _iu.module_from_spec(_spec)',
            "    exec(compile(_source_bytes,str(_source),'exec',dont_inherit=True),_module.__dict__)",
            '    _module._READONLY_LOADED_HOST_SHA256 = _source_sha',
            '    _host = _module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)',
            "    _supported = getattr(_host,'native_observation_protocol',None)=="+repr(NATIVE_OBSERVATION_PROTOCOL),
            "    if _request['command'] in ('capture','capture_evidence'):",
            "        if _request['params']: raise ValueError('Capture accepts no arguments')",
            "        _result = _host.capture_scene() if _request['command']=='capture' else _host.capture_evidence()",
            "    elif _request['command']=='native_observation_capabilities':",
            "        if _request['params']: raise ValueError('Capabilities accepts no arguments')",
            "        _result = _host.native_observation_capabilities() if _supported else {'supported':False}",
            '    else:',
            "        if not _supported: raise ValueError('Typed native observation unavailable')",
            '        with _cl.redirect_stdout(_io.StringIO()):',
            "            if _request['command']=='observe_readonly_native':",
            "                if set(_request['params'])!={'request_id','focal_id','reference_id','expected_capture_revision','deadline_ns','view'}: raise ValueError('Invalid readonly native arguments')",
            "                _result = _host.observe_readonly_native(**_request['params'])",
            "            elif _request['command']=='last_readonly_native_audit':",
            "                if set(_request['params'])!={'request_id'}: raise ValueError('Invalid native audit arguments')",
            "                _result = _host.last_readonly_native_audit(**_request['params'])",
            "            else: raise ValueError('Unsupported fixed native observation command')",
            "    _envelope = {'protocol_version':'1.0','id':_request['id'],'result':_result}",
            'except Exception as _exc:',
            "    _envelope = {'protocol_version':'1.0','id':_request['id'],'error':{'type':type(_exc).__name__,'message':str(_exc)[:2000],'mutation_uncertain':False}}",
            'print('+repr(RPC_PREFIX)+" + _json.dumps(_envelope,ensure_ascii=True,allow_nan=False,separators=(',',':')))",
        ])

    def _structure_code(self,command,params,request_id):
        """A separate pinned, typed read template; old template bytes stay fixed."""
        required={'mesh_structure_capabilities':set(),'mesh_region_summary_capabilities':set(),
            'observe_mesh_structure_summary':{'request_id','object_id','categories','deadline_ns'},'patch_observation_capabilities':set(),
            'nonplanar_observation_capabilities':set(),
            'observe_nonplanar_patch':{'request_id','object_id','patch','deadline_ns','mode'},
            'observe_mesh_structure':{'request_id','object_id','categories','deadline_ns'},
            'observe_patch':{'request_id','object_id','patch','deadline_ns'}}
        if command not in required or type(params) is not dict or set(params)!=required[command]:
            raise ValueError('Invalid fixed structure observation command')
        request=json.dumps(dict(id=request_id,command=command,params=params),ensure_ascii=True,
            allow_nan=False,separators=(',',':'))
        if len(request.encode('utf8'))>16384:raise ValueError('Structure observation request exceeds 16384 bytes')
        return '\n'.join([
            'import importlib.util as _iu, json as _json, contextlib as _cl, io as _io, hashlib as _hl',
            '_request = _json.loads('+repr(request)+')',
            'try:',
            '    from pathlib import Path as _Path',
            '    _source = _Path('+repr(str(self.source))+')',
            "    if _source.resolve()!=_source: raise ValueError('Readonly host source escaped its fixed root')",
            "    with _source.open('rb') as _stream: _source_bytes = _stream.read(512*1024+1)",
            '    _source_sha = _hl.sha256(_source_bytes).hexdigest()',
            '    if len(_source_bytes)>512*1024 or _source_sha!='+repr(self._readonly_host_source_sha256)+": raise ValueError('Readonly host source differs from the fixed connector snapshot')",
            "    _spec = _iu.spec_from_file_location('_human_eye_blender_structure_read',str(_source))",
            "    if _spec is None or _spec.loader is None: raise RuntimeError('Trusted structure host unavailable')",
            '    _module = _iu.module_from_spec(_spec)',
            "    exec(compile(_source_bytes,str(_source),'exec',dont_inherit=True),_module.__dict__)",
            '    _module._READONLY_LOADED_HOST_SHA256 = _source_sha',
            '    _host = _module.BlenderSceneHost(bpy_module=bpy,execution_metadata=True,identity_metadata=True)',
            '    _allowed = '+repr({key:sorted(value) for key,value in required.items()}),
            "    if _request['command'] not in _allowed or set(_request['params'])!=set(_allowed[_request['command']]): raise ValueError('Invalid fixed structure arguments')",
            '    with _cl.redirect_stdout(_io.StringIO()):',
            "        _result = getattr(_host,_request['command'])(**_request['params'])",
            "    _envelope = {'protocol_version':'1.0','id':_request['id'],'result':_result}",
            'except Exception as _exc:',
            "    _envelope = {'protocol_version':'1.0','id':_request['id'],'error':{'type':type(_exc).__name__,'message':str(_exc)[:2000],'mutation_uncertain':False}}",
            'print('+repr(RPC_PREFIX)+" + _json.dumps(_envelope,ensure_ascii=True,allow_nan=False,separators=(',',':')))",
        ])

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
            if len(payload) > _MAX_REQUEST_BYTES:
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
                if self._observation_depth and command in {'capture', 'capture_evidence'}:
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
            except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
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
        # The addon keeps sockets open after replies. Decode one complete JSON
        # value, rather than waiting for EOF, and bound the complete read time.
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
                try:
                    decoded = buffer.decode("utf-8")
                except UnicodeDecodeError as exc:
                    if exc.reason == "unexpected end of data":
                        continue
                    raise
                try:
                    return _loads(decoded)
                except json.JSONDecodeError:
                    # Could be a partially received JSON object. Never scan past
                    # banners, concatenated values, or malformed text for data.
                    continue


__all__ = ["BlenderMCPHost", "HostTransportError", "HostRemoteError"]
