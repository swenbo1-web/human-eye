"""Own an isolated, persistent Blender process for a specific .blend file.

This transport does not attach to an already open Blender window. Changes live
in the child process until it exits; the original .blend file is never saved by
this module or its worker. A host transport failure invalidates this connection
because a timed-out mutation may already have reached Blender.
"""
from __future__ import annotations

from .verified_source_loader import worker_arguments

from collections import deque
from contextlib import contextmanager
from fractions import Fraction
import json
import hashlib
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Iterator

from .blender_host import PREWRITE_REFUSAL_PROTOCOL, validate_prewrite_refusal
from .forward_deadline import (PROTOCOL as FORWARD_DEADLINE_PROTOCOL, counter_descriptor,
    validate_base, validate_deadline, validate_refusal as validate_deadline_refusal)


RPC_PREFIX = "HUMAN_EYE_RPC:"
PROTOCOL_VERSION = "1.0"
COMMON_NATIVE_PROTOCOL = 'owned-common-native-v1-20261031'
READONLY_EVIDENCE_PROTOCOL = 'owned-readonly-native-evidence-v1-20261031'
RENDER_AUDIT_PROTOCOL = 'owned-native-render-audit-v1-20261031'
MULTISCALE_PROTOCOL = 'owned-native-multiscale-v1-20261031'
NATIVE_OBSERVATION_PROTOCOL = 'typed-native-readonly-observation-v1-20261031'
SCENE_DELTA_PROTOCOL = 'human-eye-scene-delta-v1'
ARM_AXIAL_EXECUTION_PROTOCOL = 'owned-arm-axial-execution-v1'
_MAX_LINE_CHARS = 64 * 1024 * 1024
_MAX_REQUEST_CHARS = 4096
_MAX_CAPTURE_REQUEST_CHARS = 64 * 1024
_DEADLINE_REPLY_GRACE_NS = 2_000_000_000


def _validate_native_observation_capabilities(value, *, source, process_id=None):
    keys={'schema_version','protocol','process_id','clock','max_duration_ns',
          'host_source_sha256','read_only','execution_authority'}
    if (type(value) is not dict or set(value)!=keys
            or value['schema_version']!='native-readonly-capabilities-v1'
            or value['protocol']!=NATIVE_OBSERVATION_PROTOCOL
            or type(value['process_id']) is not int or value['process_id']<=0
            or process_id is not None and value['process_id']!=process_id
            or value['clock']!=counter_descriptor()
            or type(value['max_duration_ns']) is not int or value['max_duration_ns']!=30_000_000_000
            or value['host_source_sha256']!=hashlib.sha256(Path(source).read_bytes()).hexdigest()
            or value['read_only'] is not True or value['execution_authority'] is not False):
        raise ValueError('Unnegotiated or changed typed native observation capability')
    return json.loads(json.dumps(value,allow_nan=False))


def _validate_native_observation_request(request_id, focal_id=None, reference_id=None,
        expected_capture_revision=None, deadline_ns=None, view='SCENE', *, diagnostic=False):
    def identity(value):
        return (type(value) is str and 0<len(value)<=256 and bool(value.strip())
                and not any(ord(char)<32 for char in value))
    if not identity(request_id):raise ValueError('Invalid readonly native request identity')
    if diagnostic:return
    if (not all(identity(value) for value in (focal_id,reference_id,expected_capture_revision))
            or focal_id==reference_id or type(deadline_ns) is not int
            or not 0<deadline_ns<(1<<63) or view not in ('XY','XZ','SCENE')):
        raise ValueError('Invalid readonly native observation request')


class HostTransportError(RuntimeError):
    """The child host could not provide a trustworthy, matching response."""

    def __init__(self, message: str, diagnostics: tuple[str, ...] = ()) -> None:
        self.diagnostics = diagnostics
        super().__init__(message)


class HostRemoteError(RuntimeError):
    """Blender rejected a request and returned a definite error response."""

    def __init__(self, error: dict[str, Any]):
        self.error = error
        super().__init__(f"{error.get('type', 'HostError')}: {error.get('message', 'request rejected')}")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Blender response key: " + key)
        result[key] = value
    return result


def _validate_arm_twist_report(value, selection):
    source = value.get('source') if isinstance(value, dict) else None
    mesh = source.get('mesh') if isinstance(source, dict) else None
    armature = source.get('armature') if isinstance(source, dict) else None
    if (not isinstance(source, dict) or value.get('schema') != 'arm-twist-expert-report-v1'
            or value.get('status') not in ('estimated', 'unknown')
            or value.get('source_binding') != 'local_armature_source_adapter'
            or source.get('unit') != 'm' or source.get('coordinate_frame') != 'armature_local'
            or not isinstance(mesh, dict) or mesh.get('name') != selection.get('mesh_name')
            or source.get('selected_bones') != selection.get('bone_names')
            or 'armature_name' in selection and (not isinstance(armature, dict)
                or armature.get('name') != selection['armature_name'])):
        raise ValueError('Arm twist report schema or current selection binding mismatch')
    return value


def _validate_arm_axial_result(value, task):
    """Bind the mutation receipt to this event, including true partial counts."""
    if (type(value) is not dict or value.get('schema')!='arm-axial-execution-result-v1'
            or value.get('event_id')!=task.get('event_id')
            or value.get('status') not in ('satisfied','feedback_failed','no_op',
                'unreachable','not_applicable','execution_uncertain')
            or type(value.get('reason')) is not str
            or type(value.get('task_succeeded')) is not bool
            or value.get('executed') is not None and type(value.get('executed')) is not bool):
        raise ValueError('Arm correction receipt schema or event mismatch')
    if not {'executed','setter_attempts','setter_returns'}.issubset(value):
        raise ValueError('Arm correction receipt omitted action state')
    attempts,returns=value['setter_attempts'],value['setter_returns']
    if (any(v is not None and (type(v) is not int or not 0<=v<=2) for v in (attempts,returns))
            or returns is not None and attempts is not None and returns>attempts):
        raise ValueError('Arm correction receipt has invalid setter counts')
    status=value['status'];executed=value['executed'];succeeded=value['task_succeeded']
    if status=='execution_uncertain':
        if (succeeded or executed is False and (attempts,returns)!=(0,0)
                or (attempts,returns)==(0,0) and executed is not False
                or attempts==0 and (returns!=0 or executed is not False)
                or returns is not None and returns>0 and executed is not True
                or executed is True and (returns is None or returns==0)):
            raise ValueError('Arm correction uncertainty contradicts known setters')
    elif status in ('satisfied','feedback_failed'):
        if (attempts,returns)!=(2,2) or executed is not True or succeeded!=(status=='satisfied'):
            raise ValueError('Arm correction completion contradicts setter counts')
    elif (attempts,returns)!=(0,0) or executed is not False or succeeded!=(status=='no_op'):
        raise ValueError('Arm correction no-write receipt contradicts action state')
    selection=task['selection']
    for name in ('before_source','after_source'):
        source=value.get(name)
        if source is None:
            if status in ('satisfied','feedback_failed') or (name=='before_source' and status in ('no_op','unreachable')):
                raise ValueError('Arm correction completion omitted current source')
            continue
        if (type(source) is not dict or source.get('unit')!='m'
                or source.get('coordinate_frame')!='armature_local'
                or source.get('selected_bones')!=selection.get('bone_names')
                or type(source.get('mesh')) is not dict
                or source['mesh'].get('name')!=selection.get('mesh_name')
                or type(source.get('armature')) is not dict
                or source['armature'].get('name')!=selection.get('armature_name')):
            raise ValueError('Arm correction source selection binding mismatch')
    json.dumps(value,allow_nan=False)
    return value


class BlenderProcessHost:
    """Serialize capture and transform requests to an owned headless process.

    Call ``transaction()`` around a capture/check/apply sequence to prevent other
    callers of this instance interleaving requests. Blender also compares the
    expected scene revision at its actual mutation boundary.
    """

    prewrite_refusal_protocol = PREWRITE_REFUSAL_PROTOCOL
    forward_deadline_protocol = FORWARD_DEADLINE_PROTOCOL

    def __init__(self, blender_executable: str | os.PathLike[str],
                 blend_file: str | os.PathLike[str], *, timeout: float = 30.0,
                 startup_timeout: float = 60.0,
                 worker_path: str | os.PathLike[str] | None = None,
                 material_readview_only: bool = False) -> None:
        if type(material_readview_only) is not bool or material_readview_only and worker_path is not None:
            raise ValueError('Material readview requires the fixed readonly worker')
        for name, value in (("timeout", timeout), ("startup_timeout", startup_timeout)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        executable = Path(blender_executable).expanduser().resolve()
        source = Path(blend_file).expanduser().resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"Blender executable does not exist: {executable}")
        if not source.is_file() or source.suffix.lower() != ".blend":
            raise ValueError("blend_file must name an existing .blend file")
        root = Path(__file__).resolve().parents[1]
        worker = Path(worker_path).expanduser().resolve() if worker_path else Path(__file__).resolve().with_name("blender_worker.py")
        if not worker.is_file():
            raise FileNotFoundError(f"Blender worker does not exist: {worker}")
        self._default_worker = worker_path is None
        self._worker_source = worker
        self.timeout = float(timeout)
        self._lock = threading.RLock()
        self._responses: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=16)
        self._diagnostics: deque[str] = deque(maxlen=64)
        self._closed = False
        self._poisoned = False
        self._sequence = 0
        self._deadline_bindings = {}
        self._scene_decoder = None
        command = [str(executable), "--factory-startup", "--disable-autoexec", "--background",
                   str(source), *(worker_arguments(root,worker) if worker_path is None else ["--python",str(worker)]), "--", str(root)]
        if material_readview_only:command.append('material-readview-only-v1')
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                         errors="replace", bufsize=1, creationflags=flags,
                                         shell=False)
        self._stdout_thread = threading.Thread(target=self._read_stdout, name="human-eye-blender-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, name="human-eye-blender-stderr", daemon=True)
        try:
            self._stdout_thread.start()
            self._stderr_thread.start()
            capabilities = self._request("capabilities", {}, timeout=float(startup_timeout))
            if not isinstance(capabilities, dict) or capabilities.get("protocol_version") != PROTOCOL_VERSION:
                self._fail("Blender worker protocol version is incompatible")
            self._capabilities = capabilities
        except BaseException:
            self.close()
            raise

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """Return a bounded tail of Blender banners and stderr diagnostics."""
        return tuple(self._diagnostics)

    def _check_material_readview(self):
        if (not getattr(self, '_default_worker', False)
                or self._capabilities.get('material_readview_protocol')!='static-material-readview-v1'
                or self._capabilities.get('material_readview_only') is not True
                or self._capabilities.get('process_id')!=self._process.pid
                or self._capabilities.get('forward_deadline_clock')!=counter_descriptor()):
            raise ValueError('No fixed owned readonly material-view worker')

    def material_readview_header(self,binding):
        self._check_material_readview()
        return self._request('material_readview_header',{'binding':binding})

    def observe_material_readview(self,request_id,binding,expected_fingerprint,deadline_ns):
        self._check_material_readview()
        seconds=(deadline_ns-time.perf_counter_ns())/1e9
        if seconds<=0:raise ValueError('Material readview deadline expired')
        return self._request('observe_material_readview',{'request_id':request_id,'binding':binding,
            'expected_fingerprint':expected_fingerprint,'deadline_ns':deadline_ns},timeout=min(self.timeout,seconds))

    def last_material_readview_audit(self):
        self._check_material_readview()
        return self._request('last_material_readview_audit',{})

    @property
    def is_alive(self) -> bool:
        return not self._closed and not self._poisoned and self._process.poll() is None

    @contextmanager
    def transaction(self) -> Iterator["BlenderProcessHost"]:
        with self._lock:
            self._ensure_live()
            yield self

    def capabilities(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._capabilities, allow_nan=False))

    def capture_scene(self) -> dict[str, Any]:
        return self._capture_request("capture", {})

    def _capture_request(self, command, params, *, timeout=None):
        """Keep resource baselines private to this connection and this lock.

        The public methods still return ordinary captures. Only the worker wire
        uses resource deltas; evidence and mutation protocols never use them.
        """
        with self._lock:
            if self._capabilities.get('scene_delta_protocol') != SCENE_DELTA_PROTOCOL:
                return self._request(command, params, timeout=timeout)
            if self._scene_decoder is None:
                from .scene_residency import SceneDeltaDecoder
                self._scene_decoder = SceneDeltaDecoder()
            arguments = dict(params, _scene_baseline=self._scene_decoder.baseline())
            result = self._request(command, arguments, timeout=timeout)
            try:
                return self._scene_decoder.apply(result)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                self._fail('Invalid resident capture response: ' + str(exc))

    def capture_task_scene(self, selectors) -> dict[str, Any]:
        return self._capture_request('capture_task', {'selectors': selectors})

    def capture_directory(self, deadline_ns, max_response_bytes):
        now = time.perf_counter_ns()
        if type(deadline_ns) is not int or now >= deadline_ns:
            raise ValueError('directory_deadline_exceeded')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_LINE_CHARS:
            raise ValueError('directory_document_budget')
        deadline_ns = min(deadline_ns, now + int(self.timeout * 1e9))
        result = self._request('capture_directory', dict(deadline_ns=deadline_ns,
            max_response_bytes=max_response_bytes), timeout=(deadline_ns - now) / 1e9)
        if time.perf_counter_ns() >= deadline_ns:
            raise ValueError('directory_deadline_exceeded')
        return result

    def capture_nearest_candidates(self, focal_id, deadline_ns, max_response_bytes, *, selector=None):
        with self._lock:
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
            deadline_ns = min(deadline_ns, now_ns + int(self.timeout * 1_000_000_000))
            if deadline_ns <= now_ns:
                raise ValueError('acquisition_deadline_exceeded')
            if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_LINE_CHARS:
                raise ValueError('acquisition_document_budget')
            params = dict(focal_id=focal_id, deadline_ns=deadline_ns, max_response_bytes=max_response_bytes)
            if selector is not None:
                params['selector'] = selector
            result = self._capture_request('capture_nearest_candidates', params,
                timeout=(deadline_ns-now_ns)/1_000_000_000)
            if time.perf_counter_ns() >= deadline_ns:
                raise ValueError('acquisition_deadline_exceeded')
            return result

    def capture_surface_scan(self, threshold_m, deadline_ns, max_response_bytes):
        with self._lock:
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
            deadline_ns = min(deadline_ns, now_ns + int(self.timeout * 1_000_000_000))
            if deadline_ns <= now_ns:
                raise ValueError('acquisition_deadline_exceeded')
            if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= _MAX_LINE_CHARS:
                raise ValueError('acquisition_document_budget')
            result = self._capture_request('capture_surface_scan', dict(threshold_m=float(threshold_m),
                deadline_ns=deadline_ns, max_response_bytes=max_response_bytes),
                timeout=(deadline_ns-now_ns)/1_000_000_000)
            if time.perf_counter_ns() >= deadline_ns:
                raise ValueError('acquisition_deadline_exceeded')
            return result

    def capture_evidence(self) -> dict[str, Any]:
        return self._request('capture_evidence', {})

    def observe_arm_twist(self, selection):
        if not self._default_worker:
            raise ValueError('Arm twist observation requires the fixed worker')
        if type(selection) is not dict:
            raise ValueError('Arm twist selection requires an object')
        return _validate_arm_twist_report(self._request('observe_arm_twist', {'selection': selection}), selection)

    def correct_arm_axial(self, task):
        """Submit one fixed owned arm step; uncertain outcomes are never retried."""
        fields={'schema','event_id','selection','u_interval_deg','max_section_area_loss',
                'protected_vertex_ids','angle_tolerance_deg','position_tolerance_m','area_tolerance','sentinel_name'}
        if (not self._default_worker or self._capabilities.get('arm_axial_execution_protocol')!=ARM_AXIAL_EXECUTION_PROTOCOL
                or self._capabilities.get('process_id')!=self._process.pid
                or self._capabilities.get('material_readview_only') is True):
            raise ValueError('Arm correction requires the fixed owned writable worker')
        if (type(task) is not dict or set(task)!=fields or task.get('schema')!='arm-axial-execution-task-v1'
                or type(task.get('event_id')) is not str or not 0<len(task['event_id'])<=256
                or any(ord(char)<32 for char in task['event_id']) or type(task.get('selection')) is not dict):
            raise ValueError('Invalid typed arm correction request')
        # Freeze the precise task sent across the process boundary. A caller
        # mutating its original dict cannot change the expected receipt event.
        request=json.loads(json.dumps(task,allow_nan=False))
        with self._lock:
            result=self._request('correct_arm_axial',{'task':request})
            try:
                _validate_arm_axial_result(result,request)
            except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as exc:
                self._fail('Invalid arm correction receipt; execution outcome unknown: '+str(exc))
            if result['status']=='execution_uncertain':
                self._poisoned=True;self._scene_decoder=None
                self._diagnostics.append('Arm correction outcome uncertain; owned connection quarantined')
                self._terminate_child()
            return result

    def mesh_structure_capabilities(self):
        if not self._default_worker:raise ValueError('Raw mesh observation requires the fixed worker')
        return self._request('mesh_structure_capabilities',{})

    def observe_mesh_structure(self, request_id, object_id, categories, deadline_ns):
        if not self._default_worker:raise ValueError('Raw mesh observation requires the fixed worker')
        return self._request('observe_mesh_structure',dict(request_id=request_id,object_id=object_id,
                             categories=categories,deadline_ns=deadline_ns))

    def mesh_region_summary_capabilities(self):
        if not self._default_worker:raise ValueError('Raw mesh summary requires the fixed worker')
        return self._request('mesh_region_summary_capabilities',{})

    def observe_mesh_structure_summary(self,request_id,object_id,categories,deadline_ns):
        if not self._default_worker:raise ValueError('Raw mesh summary requires the fixed worker')
        return self._request('observe_mesh_structure_summary',dict(request_id=request_id,object_id=object_id,categories=categories,deadline_ns=deadline_ns))

    def reference_view_capabilities(self):
        if not self._default_worker:raise ValueError('Reference view requires the fixed worker')
        value=self._request('reference_view_capabilities',{})
        _validate_native_observation_capabilities(value['native'],source=Path(__file__).resolve().with_name('blender_host.py'),process_id=self._process.pid)
        return value

    def observe_reference_patch(self,request_id,object_id,patch,deadline_ns):
        if not self._default_worker:raise ValueError('Reference view requires the fixed worker')
        return self._request('observe_reference_patch',dict(request_id=request_id,object_id=object_id,patch=patch,deadline_ns=deadline_ns))

    def surface_geometry_capabilities(self):
        if not self._default_worker:raise ValueError('Surface geometry requires the fixed worker')
        return self._request('surface_geometry_capabilities',{})

    def capture_surface_source(self,request_id,object_id,deadline_ns):
        if not self._default_worker:raise ValueError('Surface geometry requires the fixed worker')
        return self._request('capture_surface_source',dict(request_id=request_id,object_id=object_id,deadline_ns=deadline_ns))

    def observe_surface_geometry(self,request_id,object_id,deadline_ns,near_m):
        if not self._default_worker:raise ValueError('Surface geometry requires the fixed worker')
        return self._request('observe_surface_geometry',dict(request_id=request_id,object_id=object_id,deadline_ns=deadline_ns,near_m=near_m))

    def patch_observation_capabilities(self):
        if not self._default_worker:raise ValueError('Patch observation requires the fixed worker')
        value=self._request('patch_observation_capabilities',{})
        _validate_native_observation_capabilities(value['native'],
            source=Path(__file__).resolve().with_name('blender_host.py'),process_id=self._process.pid)
        return value

    def observe_patch(self, request_id, object_id, patch, deadline_ns):
        if not self._default_worker:raise ValueError('Patch observation requires the fixed worker')
        return self._request('observe_patch',dict(request_id=request_id,object_id=object_id,
                             patch=patch,deadline_ns=deadline_ns))

    def nonplanar_observation_capabilities(self):
        if not self._default_worker:raise ValueError('Nonplanar observation requires the fixed worker')
        value=self._request('nonplanar_observation_capabilities',{})
        _validate_native_observation_capabilities(value['native'],
            source=Path(__file__).resolve().with_name('blender_host.py'),process_id=self._process.pid)
        return value

    def observe_nonplanar_patch(self,request_id,object_id,patch,deadline_ns,mode):
        if not self._default_worker:raise ValueError('Nonplanar observation requires the fixed worker')
        return self._request('observe_nonplanar_patch',dict(request_id=request_id,object_id=object_id,
            patch=patch,deadline_ns=deadline_ns,mode=mode))

    def native_observation_capabilities(self):
        value=self._capabilities.get('native_observation_capabilities')
        if value is None:return None
        if not self._default_worker:
            raise ValueError('Readonly native observation requires the fixed owned worker')
        return _validate_native_observation_capabilities(value,
            source=Path(__file__).resolve().with_name('blender_host.py'),process_id=self._process.pid)

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

    def _check_native_owner_read_capability(self, field, protocol):
        self._check_common_native_capability()
        if self._capabilities.get(field) != protocol:
            raise ValueError('Fixed worker has not negotiated the owner-only native read protocol')

    def capture_readonly_evidence(self) -> dict[str, Any]:
        """Owner-only original-pose evidence; this read grants no write rights."""
        self._check_native_owner_read_capability('readonly_native_evidence_protocol', READONLY_EVIDENCE_PROTOCOL)
        return self._request('capture_readonly_evidence', {})

    def native_render_state(self) -> dict[str, Any]:
        """Read owner-private camera/render/selection state, never model input."""
        self._check_native_owner_read_capability('native_render_audit_protocol', RENDER_AUDIT_PROTOCOL)
        return self._request('native_render_state', {})

    def last_native_render_audit(self) -> dict[str, Any]:
        """Read owner-private actual before/after render evidence."""
        self._check_native_owner_read_capability('native_render_audit_protocol', RENDER_AUDIT_PROTOCOL)
        return self._request('last_native_render_audit', {})

    def begin_motion_goal(self, goal_id, focal_id, reference_id, limits=None):
        return self._request('motion_begin', {'goal_id':goal_id, 'focal_id':focal_id,
                                             'reference_id':reference_id, 'limits':limits})

    def motion_goal_status(self, goal_id, after_event_count=0):
        return self._request('motion_status', {'goal_id':goal_id, 'after_event_count':after_event_count})

    def end_motion_goal(self, goal_id):
        return self._request('motion_end', {'goal_id':goal_id})

    def _check_common_native_capability(self):
        descriptor = counter_descriptor()
        if (not self._default_worker
                or self._capabilities.get('common_native_protocol') != COMMON_NATIVE_PROTOCOL
                or self._capabilities.get('common_native_clock') != descriptor
                or self._capabilities.get('process_id') != self._process.pid):
            raise ValueError('Fixed worker has not negotiated the common native episode protocol')
        return descriptor

    def begin_owned_episode(self, episode_id, focal_id, reference_id, deadline_ns,
                            read_only=False, limits=None):
        self._check_common_native_capability()
        return self._request('episode_begin', {'episode_id':episode_id, 'focal_id':focal_id,
            'reference_id':reference_id, 'deadline_ns':deadline_ns, 'read_only':read_only, 'limits':limits})

    def owned_episode_status(self, after_event_count=0):
        self._check_common_native_capability()
        return self._request('episode_status', {'after_event_count':after_event_count})

    def native_scene_query(self):
        self._check_common_native_capability()
        return self._request('native_scene_query', {})

    def native_look(self, view='SCENE'):
        self._check_common_native_capability()
        return self._request('native_look', {'view':view})

    def native_look_multiscale(self, view='SCENE'):
        self._check_native_owner_read_capability('native_multiscale_protocol', MULTISCALE_PROTOCOL)
        return self._request('native_look_multiscale', {'view':view})

    def last_native_multiscale_audit(self):
        self._check_native_owner_read_capability('native_multiscale_protocol', MULTISCALE_PROTOCOL)
        return self._request('last_native_multiscale_audit', {})

    def native_transform(self, object_id, delta_world_m, expected_revision):
        self._check_common_native_capability()
        return self._request('native_transform', {'object_id':object_id,
            'delta_world_m':delta_world_m, 'expected_revision':expected_revision})

    def _check_forward_capability(self):
        descriptor = counter_descriptor()
        if (self._capabilities.get('forward_deadline_protocol') != FORWARD_DEADLINE_PROTOCOL
                or self._capabilities.get('forward_deadline_clock') != descriptor
                or self._capabilities.get('process_id') != self._process.pid):
            raise ValueError('Worker has not negotiated this process and common QPC deadline protocol')
        return descriptor

    def require_forward_deadline(self, goal_id):
        with self.transaction():
            self._check_forward_capability()
            binding = self.motion_goal_status(goal_id)['binding']
            result = self._request('deadline_require', {'goal_id':goal_id})
            self._deadline_bindings[goal_id] = binding
            return result

    def bind_forward_deadline(self, lease):
        with self.transaction():
            self._check_forward_capability()
            goal_id = lease.get('goal_id') if type(lease) is dict else None
            if goal_id not in self._deadline_bindings:
                self.require_forward_deadline(goal_id)
            lease = validate_base(lease, binding=self._deadline_bindings[goal_id],
                                  process_id=self._process.pid, goal_id=goal_id)
            return self._request('deadline_bind', {'lease':lease})

    def apply_transform(self, action: dict[str, Any], expected_revision: str,
                        expected_fingerprint: str | None = None,
                        request_nonce: str | None = None, forward_deadline=None) -> dict[str, Any]:
        params = {"action": action, "expected_revision": expected_revision,
                  "expected_fingerprint": expected_fingerprint}
        if request_nonce is not None:
            params["request_nonce"] = request_nonce
        if forward_deadline is not None:
            self._check_forward_capability()
            goal_id = forward_deadline.get('goal_id') if type(forward_deadline) is dict else None
            if goal_id not in self._deadline_bindings:
                raise ValueError('Forward deadline requires a registered and bound goal')
            params['forward_deadline'] = validate_deadline(forward_deadline, action=action,
                expected_revision=expected_revision, expected_fingerprint=expected_fingerprint,
                request_nonce=request_nonce, binding=self._deadline_bindings[goal_id],
                process_id=self._process.pid, goal_id=goal_id)
        return self._request("apply", params)

    def _readback_after_apply(self, result):
        """Consume this owned apply response's actual post-setter scene."""
        if getattr(self, '_default_worker', False) is not True:
            return self.capture_scene()
        if type(result) is not dict or type(result.get('scene')) is not dict:
            raise HostTransportError('Owned apply returned no readback scene')
        return result['scene']

    def _ensure_live(self) -> None:
        if self._closed or self._poisoned:
            raise HostTransportError("Blender connection is closed or invalidated; start a new host and observe again")
        if self._process.poll() is not None:
            self._fail("Blender process exited before the request")

    def _request(self, command: str, params: dict[str, Any], *, timeout: float | None = None) -> Any:
        with self._lock:
            self._ensure_live()
            self._sequence += 1
            request_id = self._sequence
            # Validate before writing: a local serialization failure cannot mutate Blender.
            payload = json.dumps({"id": request_id, "command": command, "params": params},
                                 ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
            capture_request = command in ('capture', 'capture_task', 'capture_nearest_candidates', 'capture_surface_scan')
            limit = (_MAX_LINE_CHARS if command in ('observe_arm_twist','correct_arm_axial') else
                _MAX_CAPTURE_REQUEST_CHARS if capture_request else _MAX_REQUEST_CHARS)
            if len(payload) > limit:
                if command == 'observe_arm_twist':
                    raise ValueError('Arm twist selection exceeds the existing line protocol limit')
                if command == 'correct_arm_axial':
                    raise ValueError('Arm correction task exceeds the existing line protocol limit')
                raise ValueError("Blender request exceeds the 65536-character capture protocol limit"
                    if capture_request else "Blender request exceeds the 4096-character transform protocol limit")
            stop_ns = None
            wire = params.get('forward_deadline') if command == 'apply' else None
            if wire is not None:
                local_seconds = self.timeout if timeout is None else timeout
                local_ns = int(Fraction(local_seconds) * 1_000_000_000)
                stop_ns = min(time.perf_counter_ns() + local_ns,
                              wire['forward_deadline_ns'] + _DEADLINE_REPLY_GRACE_NS)
            def remaining():
                return max(0., (stop_ns-time.perf_counter_ns())/1_000_000_000) if stop_ns is not None else (
                    self.timeout if timeout is None else timeout)
            writer = None
            try:
                assert self._process.stdin is not None
                if stop_ns is None:
                    self._process.stdin.write(payload)
                    self._process.stdin.flush()
                else:
                    done = threading.Event(); failures = []
                    def write_request():
                        try:
                            self._process.stdin.write(payload)
                            self._process.stdin.flush()
                        except (OSError, ValueError) as exc:
                            failures.append(exc)
                        finally:
                            done.set()
                    writer = threading.Thread(target=write_request,
                        name='human-eye-deadline-pipe-writer', daemon=True)
                    writer.start()
                    if not done.wait(timeout=remaining()):
                        self._fail('Deadline-bound request send timed out; outcome unknown')
                    if failures:
                        raise failures[0]
            except (OSError, ValueError) as exc:
                self._fail(f"Could not send a request to Blender: {exc}")
            finally:
                if writer is not None and writer.is_alive():
                    writer.join(timeout=2.)
                    if writer.is_alive():
                        self._diagnostics.append('Deadline pipe writer cleanup incomplete')
            try:
                kind, response = self._responses.get(timeout=remaining())
            except queue.Empty:
                self._fail(f"Blender request {command!r} timed out; its execution outcome is unknown")
            if kind != "response":
                self._fail(str(response))
            if self._poisoned:
                self._fail("Blender response stream was invalidated")
            if (not isinstance(response, dict) or type(response.get("id")) is not int
                    or response.get("id") != request_id
                    or set(response) not in ({"id", "result"}, {"id", "error"})):
                self._fail("Blender response ID does not match the current request")
            has_result, has_error = "result" in response, "error" in response
            if has_result == has_error:
                self._fail("Blender response must contain exactly one of result or error")
            if has_error:
                error = response["error"]
                if not isinstance(error, dict):
                    self._fail("Blender returned an invalid error response")
                # The process must be discarded if execution could be partial.
                known_native_refusal = (command == 'native_transform'
                    and error.get('type') == 'EpisodePrewriteRefused'
                    and error.get('mutation_uncertain') is False
                    and error.get('known_preentry_refusal') is True
                    and error.get('executed') is False)
                if command == 'correct_arm_axial':
                    # A complete host result may have failed worker JSON
                    # delivery after real writes. Preserve only a validated
                    # event-bound action receipt, then discard the process.
                    known=error.get('mutation_receipt')
                    try:
                        if known is not None:
                            _validate_arm_axial_result(known,params['task'])
                            if known['status']!='execution_uncertain':raise ValueError('uncertain receipt required')
                    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
                        known=None
                    try:
                        self._fail('Blender arm mutation could not be verified: '+str(error.get('message','unknown error')))
                    except HostTransportError as exc:
                        if known is not None:exc.mutation_result=known
                        raise
                if command == "apply" or error.get("mutation_uncertain") or (
                        command == 'native_transform' and not known_native_refusal):
                    self._fail(f"Blender mutation could not be verified: {error.get('message', 'unknown error')}")
                raise HostRemoteError(error)
            result = response["result"]
            if command == "apply" and isinstance(result, dict) and (
                    result.get("status") == "rejected_before_mutation" or "rejection" in result):
                try:
                    if wire is not None and result.get('rejection', {}).get('protocol') == FORWARD_DEADLINE_PROTOCOL:
                        validate_deadline_refusal(result, forward_deadline=wire, action=params['action'],
                            expected_revision=params['expected_revision'], expected_fingerprint=params['expected_fingerprint'],
                            request_nonce=params.get('request_nonce'))
                    else:
                        validate_prewrite_refusal(result, action=params["action"],
                            expected_revision=params["expected_revision"],
                            expected_fingerprint=params["expected_fingerprint"],
                            request_nonce=params.get("request_nonce"))
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    self._fail("Invalid prewrite refusal; execution outcome unknown: " + str(exc))
            return result

    def _enqueue(self, item: tuple[str, Any]) -> None:
        try:
            self._responses.put_nowait(item)
        except queue.Full:
            self._poisoned = True
            self._diagnostics.append("Blender emitted too many unsolicited protocol responses")

    def _read_stdout(self) -> None:
        try:
            assert self._process.stdout is not None
            while True:
                line = self._process.stdout.readline(_MAX_LINE_CHARS + 1)
                if not line:
                    break
                if len(line) > _MAX_LINE_CHARS:
                    self._enqueue(("failure", "Blender response exceeded the transport size limit"))
                    return
                if not line.startswith(RPC_PREFIX):
                    self._diagnostics.append("stdout: " + line.rstrip()[:1000])
                    continue
                try:
                    response = json.loads(line[len(RPC_PREFIX):], parse_constant=_reject_constant,
                                          object_pairs_hook=_unique_object)
                    json.dumps(response, allow_nan=False)
                except (ValueError, TypeError) as exc:
                    self._enqueue(("failure", f"Blender emitted invalid protocol JSON: {exc}"))
                    return
                self._enqueue(("response", response))
        except (OSError, ValueError) as exc:
            self._enqueue(("failure", f"Blender stdout failed: {exc}"))
        finally:
            self._enqueue(("failure", "Blender closed its response stream"))

    def _read_stderr(self) -> None:
        try:
            assert self._process.stderr is not None
            while True:
                line = self._process.stderr.readline(4096)
                if not line:
                    break
                self._diagnostics.append("stderr: " + line.rstrip()[:1000])
        except (OSError, ValueError):
            pass

    def _fail(self, reason: str) -> None:
        self._poisoned = True
        self._scene_decoder = None
        self._terminate_child()
        raise HostTransportError(reason, self.diagnostics)

    def _terminate_child(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.0)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if not self._poisoned and self._process.poll() is None:
                try:
                    self._request("shutdown", {}, timeout=min(self.timeout, 2.0))
                    self._process.wait(timeout=2.0)
                except (HostTransportError, HostRemoteError, subprocess.TimeoutExpired):
                    pass
            self._closed = True
            self._scene_decoder = None
            self._terminate_child()
            for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError) as exc:
                        # Terminating an owned process can interrupt a buffered
                        # pipe flush. Keep the failure visible and still close
                        # the other streams and join their reader threads.
                        self._diagnostics.append('Stream close failed: ' + type(exc).__name__)
            for thread in (self._stdout_thread, self._stderr_thread):
                if thread.ident is not None:thread.join(timeout=1.0)

    def __enter__(self) -> "BlenderProcessHost":
        self._ensure_live()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


__all__ = ["BlenderProcessHost", "HostTransportError", "HostRemoteError"]
