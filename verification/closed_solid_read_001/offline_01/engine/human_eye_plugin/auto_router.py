"""Host-driven 3D perception routing, independent of a model's tool selection.

Scenes are explicit, world-space metre snapshots. This module never loads the
demo scene, executes host actions, or certifies a swept motion path. A host must
check its revision atomically when executing an action accepted by this gate.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
import copy
import hashlib
import io
import json
import math
import threading
import time
import uuid
from typing import Any

import numpy as np

from human_eye_module1_operators import (
    MeshEntity3D, QuadCognitiveCanvasCompositor, SE3AlignmentMath,
    SpatialAnomalySniffer,
)
from human_eye_module1_operators.submodule_1_5_alignment_verifier import _probe_is_trustworthy
from .geometry_safety import COLLISION_TOLERANCE_M, measure_pair_geometry, work_budget_status
from .scene_rendering import (_render_scene_canvas_prepared, _finalize_prepared_scene_q4,
                              _task_label_coverage_summary)
from .task_labels import build_task_label_plan, _build_task_label_bundle
from .scene_cache import SpatialSceneCache
from .attention_rendering import apply_attention_to_canvas, _annotate_orthogonal_target_measurement
from .local_view import append_gain_local_view, local_view_clock
from .visible_refill import VisibleRefillCollector, VisibleRefillProposal, visible_refill_clock
from .refill_budget import refill_budget_for_quad_size
from .refill_recovery import (BUDGET_REASONS as _REFILL_BUDGET_REASONS,
    retry_state as _refill_retry_state, retry_blocked as _refill_retry_blocked,
    record_budget_failure as _refill_budget_failure, retry_evidence as _refill_retry_evidence)
from .spatial_index import SpatialSceneIndex
from .task_intent import classify_task_intent
from .query_policy import validate_query, measurement_contract, summarize_query
from .top1_query import select_top1_pairs
from .contact_section import append_contact_section
from .rigid_frame import (RIGID_FRAME_CONTRACT_REVISION, pair_rigid_frame_status,
                          preserve_raw_frame_rejection, rigid_frame_status)
from .telemetry import annotate as _annotate, span as _span, record_image_event as _image_event
from .scene_capabilities import build_scene_capabilities
from contextlib import contextmanager
from functools import wraps
import sys


# Bump when the query or visual delivery contract changes. Persisted complete
# observations include images and must never reuse an earlier visual layout.
OBSERVATION_CONTRACT_REVISION = 'v19-compact-support-plane-discovery-20261028'
_ATTENTION_COST_CONTRACT = 'cpu_numpy_full_scene_depth_owner_readability_40ms_net2px_v1'
_ATTENTION_RETRY_SCHEMA = 'bounded_cost_retry_v2'
_ATTENTION_RETRY_MAX_IDLE_S = 30.0
_ATTENTION_RETRY_DELAYS_S = (1.0, 4.0, 8.0)
_ATTENTION_BUDGET_REASONS = frozenset({
    'attention_budget_exhausted_before_raster',
    'attention_additional_compute_budget_exceeded',
})


def _refill_tile_has_new_pixels(tile, original, *, view_index, quad_size, label_box=None):
    """Prove nonempty RGB change in an already bound single-view proposal."""
    x, y = (view_index % 2)*quad_size, (view_index // 2)*quad_size
    if (type(label_box) is list and len(label_box) == 4
            and all(type(value) is int for value in label_box)
            and 0 <= label_box[0] < label_box[2] < quad_size
            and 0 <= label_box[1] < label_box[3] < quad_size):
        if tile.getpixel((label_box[0], label_box[1])) != original.getpixel((x+label_box[0], y+label_box[1])):
            return True
    window = (x, y, x+quad_size, y+quad_size)
    return tile.tobytes() != original.crop(window).tobytes()


def _attention_retry_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _attention_retry_state(value, now, *, key=None):
    """Untrusted observational persistence can only impose a short bounded wait.

    Expiry is measured from the last actual attempt. A skipped request never
    refreshes this record. Clock reversal, excess deadlines and corrupt data
    discard the optional feedback rather than indefinitely suppressing views.
    """
    if (type(value) is not dict or not _attention_retry_number(now)
            or value.get('schema_version') != _ATTENTION_RETRY_SCHEMA):
        return None
    expected = {'schema_version', 'key', 'last_attempt_s', 'retry_at_s',
                'budget_failures'}
    if set(value) != expected:
        return None
    identity = value.get('key')
    def digest(text):
        return (type(text) is str and len(text) == 64
                and all(character in '0123456789abcdef' for character in text))
    if (not digest(identity) or key is not None and identity != key
            or type(value.get('budget_failures')) is not int
            or not 1 <= value['budget_failures'] <= len(_ATTENTION_RETRY_DELAYS_S)):
        return None
    attempted, retry = value.get('last_attempt_s'), value.get('retry_at_s')
    if (not all(_attention_retry_number(number) for number in (attempted, retry))
            or not 0 <= now - attempted <= _ATTENTION_RETRY_MAX_IDLE_S
            or not 0 < retry - attempted <= 8.0
            or retry != attempted + _ATTENTION_RETRY_DELAYS_S[value['budget_failures'] - 1]):
        return None
    return copy.deepcopy(value)


def _attention_retry_record(key, now, *, failures=1):
    failures = min(len(_ATTENTION_RETRY_DELAYS_S), failures)
    return {'schema_version': _ATTENTION_RETRY_SCHEMA, 'key': key,
            'last_attempt_s': now,
            'retry_at_s': now + _ATTENTION_RETRY_DELAYS_S[failures - 1],
            'budget_failures': failures}


def _attention_retry_evidence(*, attempted, cooldown=False,
                              record=None, discarded_pose=False):
    return {'schema_version': _ATTENTION_RETRY_SCHEMA,
            'scope': 'optional_visual_attention_only_no_execution_authority',
            'candidate_attempted': attempted,
            'unattempted_due_to_cooldown': cooldown,
            'confirmed_opportunity_withheld': False,
            'unattempted_counterfactual_eligibility_known': False,
            'requires_same_plan_two_consecutive_confirmations': False,
            'recovery_admission_rule': 'display_immediately_after_current_full_hard_gates',
            'consecutive_budget_failures': record['budget_failures'] if record else 0,
            'retry_at_s': record['retry_at_s'] if record else None,
            'expiry_from_last_actual_attempt_s': _ATTENTION_RETRY_MAX_IDLE_S,
            'discarded_invalid_pose_time': discarded_pose,
            'execution_authority': False}
LEGACY_AXES_VALIDATION_SCOPE = 'face_alignment_controller_only_not_world_rigid_execution'
_ORTHOGONAL_MEASUREMENT_METHODS = frozenset({
    'exact_orthogonal_cell_union_sat', 'exact_orthogonal_cell_union_escape',
})


@contextmanager
def _trace_span(name, *, kind="cpu", source_name="engine_numpy"):
    """Instrumentation may fail; the wrapped operation keeps its own outcome."""
    try:
        manager = _span(name, kind=kind, source_name=source_name)
        manager.__enter__()
    except Exception:
        yield
        return
    try:
        yield
    except BaseException:
        failure = sys.exc_info()
        try:
            manager.__exit__(*failure)
        except Exception:
            pass
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:
            pass


def _trace_annotate(**fields):
    try:
        _annotate(**fields)
    except Exception:
        pass


def _trace_stage(name, *, kind="cpu", source_name="engine_numpy", image_event=False):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with _trace_span(name, kind=kind, source_name=source_name):
                if not image_event:
                    return function(*args, **kwargs)
                event_name, requested = 'invalid_event', None
                try:
                    event = args[1] if len(args) > 1 else kwargs.get('event')
                    name_value = event.get('event') if isinstance(event, dict) else None
                    if isinstance(name_value, str) and name_value in {
                            'before_model', 'scene_changed', 'before_action', 'after_action'}:
                        event_name = name_value
                    value = event.get('include_image', True) if isinstance(event, dict) else None
                    if type(value) is bool:
                        requested = value
                except Exception:
                    # Ancillary envelope inspection cannot prevent the actual
                    # function from running, even for unusual Python mappings.
                    pass
                try:
                    result = function(*args, **kwargs)
                except BaseException:
                    try:
                        _image_event(event_name, requested, None)
                    except Exception:
                        pass
                    raise
                try:
                    picture = result.get('image') if isinstance(result, dict) else None
                    present = (isinstance(picture, dict) if picture is not None else False) if isinstance(result, dict) else None
                    if picture is not None and not isinstance(picture, dict):
                        present = None
                    _image_event(event_name, requested, present)
                except Exception:
                    pass
                return result
        return wrapped
    return decorate


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _vector(value: Any, length: int = 3) -> np.ndarray:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError("Expected a numeric vector")
    if any(isinstance(x, (bool, np.bool_, str)) for x in value):
        raise ValueError("Vector values must be numbers")
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError("Vector must be finite")
    return result


def _validate_raw_indices(raw, width, vertex_count, field):
    """Reject raw scalar coercions before the core constructs index arrays.

    Native integer arrays retain the vectorized path. JSON-like sequences are
    checked without an extra object/dense array: mixed bool/int values would
    otherwise become indistinguishable integers after np.asarray.
    """
    message = f"{field} must contain valid integer indices"
    if isinstance(raw, np.ndarray):
        if (raw.ndim != 2 or raw.shape[1:] != (width,) or len(raw) == 0
                or raw.dtype.kind not in "iu" or np.min(raw) < 0
                or np.max(raw) >= vertex_count):
            raise ValueError(message)
        return
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(message)
    for row in raw:
        if not isinstance(row, (list, tuple, np.ndarray)) or len(row) != width:
            raise ValueError(message)
        for value in row:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
                raise ValueError(message)
            if not 0 <= int(value) < vertex_count:
                raise ValueError(message)


@_trace_stage("scene.validate")
def _validated_scene(scene: dict, *, _return_payload=False, _annotate_scene=True,
                     _task_capture=False, _surface_nearest_capture=False) -> tuple:
    if not isinstance(scene, dict):
        raise ValueError("scene must be an object")
    if scene.get("unit") != "m" or scene.get("coordinate_frame") != "world":
        raise ValueError("scene requires unit=m and coordinate_frame=world")
    revision = scene.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("scene requires a nonempty revision string")
    if _task_capture and _surface_nearest_capture:
        raise ValueError('Observation entries must have one capture scope')
    scope = ('surface_nearest_candidates' if _surface_nearest_capture else
             'selected_objects' if _task_capture else 'complete_scene_meshes')
    if scene.get('capture_scope', 'complete_scene_meshes') != scope:
        raise ValueError('Scene capture_scope does not match this observation entry')
    items = scene.get("meshes")
    minimum, maximum = (0, 4) if _task_capture else (1, 256)
    if not isinstance(items, list) or not minimum <= len(items) <= maximum:
        raise ValueError('scene requires ' + str(minimum) + '..' + str(maximum) + ' meshes')
    meshes, ids, marks = [], set(), set()
    vertex_count = face_count = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("mesh must be an object")
        oid, mark = item.get("object_id"), item.get("mark_label")
        if not isinstance(oid, str) or not oid or oid in ids:
            raise ValueError("object_id must be unique and nonempty")
        if not isinstance(mark, str) or not mark or mark in marks:
            raise ValueError("mark_label must be unique and nonempty")
        ids.add(oid); marks.add(mark)
        raw_vertices, raw_faces = item.get("vertices"), item.get("faces")
        if (not isinstance(raw_vertices, (list, tuple, np.ndarray))
                or not isinstance(raw_faces, (list, tuple, np.ndarray))
                or vertex_count + len(raw_vertices) > 500_000
                or face_count + len(raw_faces) > 1_000_000):
            raise ValueError("scene geometry budget exceeded before allocation")
        raw_edges = item.get("edges")
        if raw_edges is not None and (not isinstance(raw_edges, (list, tuple, np.ndarray))
                or len(raw_edges) > 3 * len(raw_faces)):
            raise ValueError("surface edge hints exceed the triangle edge budget")
        vertices = np.asarray(raw_vertices, dtype=np.float64)
        if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or len(vertices) < 3
                or not np.isfinite(vertices).all()):
            raise ValueError("vertices must be finite Nx3")
        vertex_count += len(vertices)
        for field, width in (("faces", 3), ("edges", 2)):
            raw = item.get(field)
            if field == "edges" and (raw is None or len(raw) == 0):
                continue
            _validate_raw_indices(raw, width, len(vertices), field)
            if field == "faces":
                face_count += len(raw)
        if vertex_count > 500_000 or face_count > 1_000_000:
            raise ValueError("scene geometry budget exceeded")
        if item.get("pivot_world") is not None:
            _vector(item["pivot_world"])
        if item.get("local_axes") is not None:
            axes = np.asarray(item["local_axes"], dtype=np.float64)
            if axes.shape != (3, 3) or not np.isfinite(axes).all():
                raise ValueError("local_axes must be finite 3x3")
        rgb = item.get("color_rgb", [128, 128, 128])
        if (not isinstance(rgb, (list, tuple)) or len(rgb) != 3
                or any(type(c) is not int or not 0 <= c <= 255 for c in rgb)):
            raise ValueError("color_rgb requires three bytes")
        # from_dict copies all arrays and converts metadata to value types.
        # The event already owns a detached input; another recursive copy here
        # repeats the complete geometry walk without adding isolation.
        raw_frame = rigid_frame_status(item)
        mesh = MeshEntity3D.from_dict(item)
        preserve_raw_frame_rejection(raw_frame, mesh)
        meshes.append(mesh)
    normalized = {"revision": revision, "unit": "m", "coordinate_frame": "world",
                  "source": copy.deepcopy(scene.get("source", "host_snapshot")),
                  "meshes": [m.to_dict() for m in meshes]}
    if "host_execution" in scene:
        capability = scene["host_execution"]
        fields = {"schema_version", "operation", "supported", "scope", "reasons"}
        if (not isinstance(capability, dict) or set(capability) != fields
                or capability.get("schema_version") != "1.0"
                or capability.get("operation") != "rigid_transform"
                or type(capability.get("supported")) is not bool
                or capability.get("scope") != "independent_static_rigid_meshes"
                or not isinstance(capability.get("reasons"), list)
                or any(not isinstance(reason, dict)
                       or set(reason) != {"object_id", "object_name", "reason"}
                       or any(not isinstance(reason[k], str) or not reason[k] for k in reason)
                       for reason in capability["reasons"])
                or capability["supported"] != (not capability["reasons"])):
            raise ValueError("Invalid host_execution capability declaration")
        normalized["host_execution"] = copy.deepcopy(capability)
    if "host_identity" in scene:
        identity = scene['host_identity']
        if (not isinstance(identity, dict) or set(identity) != {
                'schema_version', 'document_epoch', 'object_instances', 'capture_scope'}
                or identity.get('schema_version') != '1.0'
                or identity.get('capture_scope') != scope
                or not isinstance(identity.get('document_epoch'), str)
                or not 1 <= len(identity['document_epoch']) <= 256
                or not identity['document_epoch'].strip()
                or not isinstance(identity.get('object_instances'), dict)
                or set(identity['object_instances']) != ids
                or any(not isinstance(token, str) or not 1 <= len(token) <= 256
                       or not token.strip()
                       for token in identity['object_instances'].values())
                or len(set(identity['object_instances'].values())) != len(ids)):
            raise ValueError('Invalid host_identity declaration')
        normalized['host_identity'] = copy.deepcopy(identity)
    if _task_capture:
        if 'host_identity' not in normalized:
            raise ValueError('Selected capture requires host_identity')
        selection = scene.get('task_selection')
        if type(selection) is not dict or set(selection) != {
                'selectors', 'bindings', 'pair_reason', 'candidate_count'}:
            raise ValueError('Invalid task_selection declaration')
        from .task_query import validate_task_query
        selectors = validate_task_query({'mode': 'task', 'objects': selection['selectors'],
                                         'requested_facts': ['aabb']})['objects']
        bindings = selection['bindings']
        if (type(selection['candidate_count']) is not int or selection['candidate_count'] < len(ids)
                or type(bindings) is not list or len(bindings) != len(selectors)):
            raise ValueError('Invalid selected candidate count or bindings')
        by_id = {item['object_id']: item for item in normalized['meshes']}
        resolved = set()
        for selector, row in zip(selectors, bindings):
            if type(row) is not dict:
                raise ValueError('Invalid task binding')
            if set(row) == {'object_id', 'name'}:
                item = by_id.get(row['object_id']) if type(row['object_id']) is str else None
                field = 'object_id' if 'id' in selector else 'name'
                if (item is None or row['name'] != item['name']
                        or item[field] != next(iter(selector.values()))):
                    raise ValueError('Task binding does not match selected geometry')
                resolved.add(row['object_id'])
            elif (set(row) != {'status', 'selector', 'reason'} or row['status'] != 'unknown'
                    or row['selector'] != selector
                    or row['reason'] not in {'object_not_found', 'object_name_ambiguous'}):
                raise ValueError('Invalid unresolved task binding')
        pair_reason = ('pair_selectors_resolve_to_same_object' if len(bindings) == 2
            and all('object_id' in row for row in bindings)
            and bindings[0]['object_id'] == bindings[1]['object_id'] else None)
        if resolved != ids or selection['pair_reason'] != pair_reason:
            raise ValueError('Selected geometry coverage or pair reason does not match bindings')
        normalized['capture_scope'] = scope
        normalized['task_selection'] = copy.deepcopy(selection)
    if _surface_nearest_capture:
        if 'host_identity' not in normalized:
            raise ValueError('Nearest candidate capture requires host_identity')
        normalized['capture_scope'] = scope
    # Includes identity, topology, pivots, frames and their provenance; stable
    # across processes, unlike the core's in-process cache tokens.
    with _trace_span("scene.hash"):
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
        fingerprint = hashlib.sha256(payload).hexdigest()
    # Detached history/delta validation retains all checks, hashes and spans,
    # but does not own the current request capture metadata.
    if _annotate_scene:
        _trace_annotate(scene_revision=revision, scene_fingerprint=fingerprint,
                        object_count=len(meshes), vertex_count=vertex_count, face_count=face_count)
    return ((normalized, meshes, fingerprint, payload) if _return_payload else
            (normalized, meshes, fingerprint))


class _ValidatedObservation:
    """One detached capture, for one synchronous internal observation only.

    This Python object never enters an agent event or persisted state. It does
    not authorize an action or replace any execution/readback validation.
    """
    __slots__ = ('_parts', '_owner_thread', '_used')

    def __init__(self, captured):
        self._parts = _validated_scene(captured, _return_payload=True)
        self._owner_thread = threading.get_ident()
        self._used = False

    @property
    def scene(self):
        return self._parts[0]

    @property
    def meshes(self):
        return self._parts[1]

    @property
    def fingerprint(self):
        return self._parts[2]

    def _consume(self):
        if self._owner_thread != threading.get_ident() or self._used:
            raise ValueError('Validated observation must be used once on its capturing thread')
        self._used = True
        return self._parts


def _pair(meshes: list[MeshEntity3D], event: dict) -> tuple[MeshEntity3D, MeshEntity3D]:
    action = event.get("action") or {}
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    for field in ("focal_id", "reference_id"):
        if field in event and field in action and event[field] != action[field]:
            raise ValueError("Conflicting " + field)
    focal_id = event.get("focal_id", action.get("focal_id"))
    reference_id = event.get("reference_id", action.get("reference_id"))
    by_id = {m.object_id: m for m in meshes}
    if focal_id is None:
        candidates = [m for m in meshes if m.is_focal_target]
        if len(candidates) != 1:
            raise ValueError("focal_id required")
        focal_id = candidates[0].object_id
    if focal_id not in by_id:
        raise ValueError("Unknown focal_id")
    if reference_id is None:
        candidates = [m for m in meshes if m.object_id != focal_id]
        if len(candidates) != 1:
            raise ValueError("reference_id required for multi-object scenes")
        reference_id = candidates[0].object_id
    if reference_id not in by_id or reference_id == focal_id:
        raise ValueError("Unknown or identical reference_id")
    return by_id[focal_id], by_id[reference_id]


def _probe_summary(probe: Any) -> dict:
    def number(value):
        return float(value) if np.isfinite(value) else None
    return {"measurement_valid": bool(probe.measurement_valid),
            "measurement_method": probe.measurement_method,
            "axes_valid": bool(probe.axes_valid), "axes_check": probe.axes_check,
            "legacy_axes_validation_scope": LEGACY_AXES_VALIDATION_SCOPE,
            "alignment_state": probe.alignment_state,
            "signed_clearance_m": number(probe.signed_clearance_m),
            "contact_normal_angle_deg": number(probe.contact_normal_angle_deg),
            "tangent_yaw_mismatch_deg": number(probe.tangent_yaw_mismatch_deg),
            "is_penetrating": bool(probe.is_penetrating)}


def _validated_orthogonal_measurement(value):
    """Recognize the new bounded geometry result, never a display probe.

    This is an internal contract check. Geometry certification and its work
    bounds belong to geometry_safety; no caller-supplied observation can grant
    this status or replace the mandatory fresh endpoint check.
    """
    clearance = value.get('signed_clearance_m')
    return (value.get('measurement_method') in _ORTHOGONAL_MEASUREMENT_METHODS
            and value.get('measurement_valid') is True
            and type(value.get('is_penetrating')) is bool
            and type(clearance) in (int, float) and np.isfinite(clearance))


class HumanEyeAutoRouter:
    """One router per agent service; bounded state is isolated by session_id.

    Events: before_model, scene_changed, before_action, after_action. The host
    provides explicit task_kind or a recognizable spatial task to select 3D.
    A background scene alone does not turn ordinary text into a spatial task.
    Empty structured scene observations remain compatible with existing hosts.
    """

    def __init__(self, mode: str = "auto", quad_size: int = 128,
                 observation_ttl_s: float = 120, max_sessions: int = 32,
                 clock=None, readback_atol_m: float = 1e-9):
        if mode not in {"auto", "off", "force_3d"}:
            raise ValueError("Unknown routing mode")
        if (not 64 <= quad_size <= 512 or not 0 < observation_ttl_s <= 3600
                or not 1 <= max_sessions <= 256):
            raise ValueError("Invalid router resource limits")
        if (isinstance(readback_atol_m, bool) or not np.isfinite(readback_atol_m)
                or not 0 <= readback_atol_m <= 1e-5):
            raise ValueError("Readback comparison tolerance must be between 0 and 10 micrometres")
        self.readback_atol_m = float(readback_atol_m)
        self.mode, self.quad_size = mode, int(quad_size)
        self.observation_ttl_s, self.max_sessions = float(observation_ttl_s), int(max_sessions)
        self._clock = clock or time.time
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        self._lock = threading.RLock()

    def _base(self, event: dict, state: dict | None = None) -> dict:
        return {"schema_version": "1.0", "event": event.get("event"),
                "session_id": event.get("session_id"), "route": "native",
                "reason_codes": [], "scene_revision": (state or {}).get("scene", {}).get("revision"),
                "scene_fingerprint": (state or {}).get("fingerprint"),
                "observation_id": None, "cache_hit": False, "engine_invoked": False,
                "allow_action": None, "measurement_valid": None, "axes_valid": None,
                "rigid_frame_valid": None, "rigid_frame": None,
                "legacy_axes_validation_scope": LEGACY_AXES_VALIDATION_SCOPE,
                "context_text": "", "image": None, "requires_reobserve": False,
                "execution_scope": "observation_only",
                "collision_tolerance_m": COLLISION_TOLERANCE_M}

    @staticmethod
    def _block(result: dict, reason: str, detail: str = "") -> dict:
        _trace_annotate(route="blocked")
        result.update(route="blocked", allow_action=False,
                      reason_codes=[reason], requires_reobserve=True,
                      context_text=json.dumps({"human_eye_status": "blocked", "reason": reason,
                                               "detail": detail}, ensure_ascii=False))
        return result

    @_trace_stage("router.event", image_event=True)
    def handle_event(self, event: dict) -> dict:
        return self._handle_event(event)

    @_trace_stage('router.event', image_event=True)
    def _handle_validated_observation(self, event, capture):
        """Private fresh-observation handoff; public/raw events always validate."""
        if (type(capture) is not _ValidatedObservation or not isinstance(event, dict)
                or event.get('event') != 'before_model' or 'scene' in event):
            raise ValueError('Internal validated capture requires an observation-only metadata event')
        return self._handle_event(event, _observation_parts=capture._consume())

    def _handle_event(self, event, *, _observation_parts=None):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        event = copy.deepcopy(event)
        if _observation_parts is not None:
            event['scene'] = _observation_parts[0]
        if type(event.get("include_image", True)) is not bool:
            raise ValueError("include_image must be boolean")
        if event.get("event") not in {"before_model", "scene_changed", "before_action", "after_action"}:
            raise ValueError("Unknown lifecycle event")
        sid = event.get("session_id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("session_id required")
        # Event defaults describe this stage, not the outer request's mode.
        _trace_annotate(session_id=sid)
        with self._lock:
            state = self._sessions.get(sid)
            result = self._base(event, state)
            action_event = event["event"] in {"before_action", "after_action"}
            if self.mode == "off":
                if action_event:
                    return self._block(result, "router_disabled")
                result["reason_codes"] = ["router_disabled"]
                return result
            intent = classify_task_intent(event.get('task_instruction', ''),
                                          task_kind=event.get('task_kind'))
            result['task_intent'] = intent
            explicit_native = (isinstance(event.get('task_kind'), str)
                               and event['task_kind'] in {'image_2d', 'ocr', 'general'})
            structured_observation = ('scene' in event and event.get('task_kind') is None
                and isinstance(event.get('task_instruction', ''), str)
                and not event.get('task_instruction', '').strip())
            in_domain = (action_event or event['event'] == 'scene_changed'
                or intent['kind'] == 'spatial_3d' or structured_observation
                or self.mode == 'force_3d' and not explicit_native)
            if not in_domain:
                # Even an unmeasured native scene update must retire any prior
                # observation token. Pending host uncertainty stays intact.
                if state and 'scene' in event:
                    state['observation'] = None
                result = self._base(event)
                result['task_intent'] = intent
                result['reason_codes'] = ['native_task' if intent['kind'] in {'general', 'image_2d'}
                                          else 'no_3d_context']
                native_scene = event.get('scene')
                if (isinstance(native_scene, dict) and isinstance(native_scene.get('revision'), str)
                        and native_scene['revision'].strip()):
                    result['scene_revision'] = native_scene['revision']
                    result['scene_revision_source'] = 'caller_declared_unvalidated_no_geometry_read'
                return result
            previous = copy.deepcopy(state.get("pending")) if state else None
            scene_payload = None
            if "scene" in event:
                try:
                    if _observation_parts is None:
                        scene, meshes, fingerprint, scene_payload = _validated_scene(
                            event["scene"], _return_payload=True)
                    else:
                        scene, meshes, fingerprint, scene_payload = _observation_parts
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    # A bad update must invalidate previous authority as well.
                    if state and state.get("pending"):
                        state["observation"] = None
                    else:
                        self._sessions.pop(sid, None)
                    return self._block(result, "invalid_scene", str(exc))
                if state is None or state["fingerprint"] != fingerprint:
                    if state is None and len(self._sessions) >= self.max_sessions:
                        evictable = next((key for key, item in self._sessions.items()
                                          if not item.get("pending")), None)
                        if evictable is None:
                            return self._block(result, "sessions_awaiting_host_readback")
                        del self._sessions[evictable]
                    retained_pending = (previous if previous and scene["revision"] ==
                                        previous["revision"] else None)
                    state = {"scene": scene, "fingerprint": fingerprint,
                             "observation": None, "pending": retained_pending,
                             "attention_state": copy.deepcopy((state or {}).get("attention_state"))}
                    self._sessions[sid] = state
                # Equal content still uses the freshly validated meshes above.
                # Reconstructing the prior snapshot here would repeat all
                # array copies, topology derivation and frame initialization.
            elif state:
                meshes = [MeshEntity3D.from_dict(m) for m in state["scene"]["meshes"]]
            else:
                return self._block(result, "scene_required", "No demo scene is substituted.")
            self._sessions.move_to_end(sid)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
            result = self._base(event, state)
            result['task_intent'] = intent
            with _trace_span("geometry.work_budget"):
                budget = work_budget_status(meshes, query_pairs=[], purpose='mesh_validation')
            result["geometry_work_budget"] = budget
            if not budget["within_budget"]:
                state["observation"] = None
                return self._block(result, "geometry_resource_limit")
            if action_event and state["scene"].get("host_execution", {}).get("supported") is False:
                state["observation"] = None
                return self._block(result, "host_execution_unsupported")
            try:
                order = event.get("yaw_symmetry_order", 2)
                if type(order) is not int or order not in (1, 2, 4):
                    raise ValueError("yaw_symmetry_order must be 1, 2 or 4")
                focal, reference = _pair(meshes, event)
            except (ValueError, TypeError, AttributeError) as exc:
                return self._block(result, "pair_or_frame_required", str(exc))
            # The reference pair always supplies the control frame/display
            # probe, including when its AABBs are far apart.
            with _trace_span('geometry.reference_budget'):
                pair_budget = work_budget_status(meshes,
                    query_pairs=[[focal.object_id, reference.object_id]])
            if not pair_budget['within_budget']:
                state['observation'] = None
                result['geometry_work_budget'] = pair_budget
                return self._block(result, 'geometry_resource_limit')
            try:
                if event["event"] == "before_action":
                    return self._before_action(event, state, meshes, focal, reference, order, result)
                if event["event"] == "after_action":
                    if (not previous or "scene" not in event
                            or state["scene"]["revision"] == previous["revision"]):
                        state["observation"] = None
                        # A new observation of the old snapshot cannot prove
                        # what happened in the host. Preserve this quarantine.
                        if previous:
                            state["pending"] = previous
                        return self._block(result, "host_readback_required")
                    state["pending"] = None
                    if (focal.object_id != previous["focal_id"]
                            or reference.object_id != previous["reference_id"]):
                        state["observation"] = None
                        return self._block(result, "host_action_pair_mismatch")
                    actual = focal.to_dict()
                    expected = previous["candidate"]
                    for field in ("object_id", "mark_label", "faces", "edges", "is_focal_target",
                                  "axes_source", "axes_confidence", "axes_reason"):
                        if actual[field] != expected[field]:
                            state["observation"] = None
                            return self._block(result, "host_action_mismatch", field)
                    for field in ("vertices", "local_axes", "pivot_world"):
                        if (actual[field] is None) != (expected[field] is None):
                            return self._block(result, "host_action_mismatch")
                        if actual[field] is not None and not np.allclose(
                                actual[field], expected[field], rtol=0, atol=self.readback_atol_m):
                            state["observation"] = None
                            return self._block(result, "host_action_mismatch")
                    plan, checks, failure = self._terminal_geometry(
                        meshes, focal, reference, state['fingerprint'], stage_name='geometry.post_action_check')
                    result['engine_invoked'] = True
                    result['spatial_index'] = self._query_summary(plan)
                    if failure is not None:
                        state['observation'] = None
                        return self._block(result, 'host_collision_detected' if failure[0] == 'collision'
                            else 'host_geometry_unknown', failure[1])
                return self._observe(event, state, meshes, focal, reference, order, result,
                                     canonical_scene_payload=scene_payload)
            except Exception as exc:
                state["observation"] = None
                if previous and state["scene"]["revision"] == previous["revision"]:
                    state["pending"] = previous
                return self._block(result, "engine_error", type(exc).__name__ + ": " + str(exc))

    @_trace_stage("observation.prepare")
    def _observe(self, event, state, meshes, focal, reference, order, result, *,
                 canonical_scene_payload=None):
        try:
            # Actions always retain the default observation and their own full
            # terminal gate; an external query cannot narrow either write gate.
            query = validate_query(event.get('query') if event['event'] in
                {'before_model', 'scene_changed'} else None,
                object_ids={mesh.object_id for mesh in meshes}, focal_id=focal.object_id)
            if query.get('alignment_evidence') is False and event.get('include_image', True) is not False:
                raise ValueError('alignment_evidence=false requires include_image=false')
        except ValueError as exc:
            state['observation'] = None
            return self._block(result, 'invalid_query', str(exc))
        with _trace_span("cache.scene_history"):
            # Only this operation's normalized/hashed bytes use the private
            # path. A scene omitted by the caller still takes public validation.
            memory = (self.scene_cache._record_validated_scene(state['scene'],
                          canonical_scene_payload=canonical_scene_payload)
                      if canonical_scene_payload is not None else
                      self.scene_cache.record_scene(state['scene']))
        with _trace_span("cache.observation_key"):
            refill_budget = refill_budget_for_quad_size(self.quad_size)
            key = _digest({"observation_contract": OBSERVATION_CONTRACT_REVISION, "scene": state["fingerprint"], "focal": focal.object_id,
                       "quad_size": self.quad_size, "attention_cost_contract": _ATTENTION_COST_CONTRACT,
                        "refill_budget_policy": refill_budget.descriptor(),
                       "include_image": event.get("include_image", True),
                       "reference": reference.object_id, "yaw": order,
                            "task": event.get("task_instruction", ""), 'query': query})
        now, cached = self._clock(), state.get("observation")
        retry_eligible = (event['event'] in {'before_model', 'scene_changed'}
                          and event.get('include_image', True))
        refill_feedback = (_refill_retry_state(state.get('refill_retry'), now, key=key)
                           if retry_eligible else None)
        if retry_eligible and refill_feedback is None and state.pop('refill_retry', None) is not None:
            # Invalid, expired or differently bound feedback must not keep an
            # old budget hold hidden behind the complete-observation TTL.
            cached = None
        refill_regeneration_started = (visible_refill_clock() if refill_feedback is not None
            and not _refill_retry_blocked(refill_feedback, now) else None)
        retry_feedback = None
        discarded_pose = False
        if retry_eligible:
            raw_retry = state.get('attention_retry')
            retry_feedback = _attention_retry_state(raw_retry, now, key=key)
            if retry_feedback is None:
                state.pop('attention_retry', None)
                if raw_retry is not None:
                    cached = None
            pose = state.get('attention_state')
            if isinstance(pose, dict):
                shifted = pose.get('last_shift_s')
                if (not _attention_retry_number(shifted) or not _attention_retry_number(now)
                        or shifted > now):
                    # A wall-clock rollback must not turn a historical pose
                    # into a permanent attention_clock_reversed hold.
                    state.pop('attention_state', None)
                    discarded_pose = True
                    cached = None
        if (cached and cached.get('contract_revision') == OBSERVATION_CONTRACT_REVISION
                and not state.get("pending") and cached["key"] == key
                and 0 <= now - cached["created"] <= self.observation_ttl_s
                and ('attention_recheck_after' not in cached
                     or _attention_retry_number(cached['attention_recheck_after'])
                     and now < cached['attention_recheck_after'])
                # The validated cost record is authoritative for scheduling;
                # a missing or overlong derived observation deadline cannot
                # conceal the next legitimate retry behind the ordinary TTL.
                and (retry_feedback is None or now < retry_feedback['retry_at_s'])
                and (refill_feedback is None or _refill_retry_blocked(refill_feedback, now))):
            try:
                reused = copy.deepcopy(cached["result"])
                facts = json.loads(reused['context_text'])
                if not isinstance(facts, dict) or not isinstance(facts.get('attention'), dict):
                    raise ValueError('Malformed cached attention context')
                attention = facts['attention']
                reasons = attention.get('reason_codes')
                if (not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons)
                        or 'retry' in attention and not isinstance(attention['retry'], dict)):
                    raise ValueError('Malformed cached attention evidence')
                if (retry_eligible and 'attention_unavailable' in reasons
                        and not now < cached['created'] + 1.0):
                    # Error feedback is intentionally not a budget record. Its
                    # one-second reconsideration is still recoverable from
                    # the cached fact and creation time after persistence.
                    raise ValueError('Cached optional attention error needs retry')
                reused.update(event=event["event"], cache_hit=True, engine_invoked=False)
                reused['task_intent'] = result.get('task_intent')
                facts['scene_memory'] = memory
                facts['observation_reused'] = True
                attention['evidence_reused'] = True
                attention['current_event_shifted'] = False
                attention['current_event_attention_cost_ms'] = 0
                local_view = facts.get('local_view')
                if isinstance(local_view, dict):
                    local_view['evidence_reused'] = True
                    local_view['current_event_candidate_raster_count'] = 0
                    local_view['current_event_local_view_cost_ms'] = 0.
                label_refill = facts.get('label_refill')
                if isinstance(label_refill, dict):
                    label_refill['evidence_reused'] = True
                    label_refill['current_event_candidate_raster_count'] = 0
                    label_refill['current_event_refill_cost_ms'] = 0.
                    # Preserve a successful/failed real attempt's history;
                    # cache reuse itself cannot spend another recovery attempt.
                    old_retry = label_refill.get('retry', {})
                    label_refill['retry'] = {**old_retry, 'attempted': False, 'evidence_reused': True}
                if 'retry' in attention:
                    attention['retry'].update(candidate_attempted=False,
                        unattempted_due_to_cooldown=False, confirmed_opportunity_withheld=False,
                        evidence_reused=True)
                facts['measurement_cache'] = {'hits': 0, 'misses': 0,
                    'scope': 'whole_observation_reused_no_measurement_lookup',
                    'execution_gate_uses_cache': False, 'stats': self.scene_cache.stats()}
                with _trace_span("observation.context_encode", kind="encoding", source_name="protocol_serialize"):
                    reused['context_text'] = json.dumps(facts, ensure_ascii=False, allow_nan=False)
                _trace_annotate(cache_hit=True, engine_invoked=False,
                                observation_id=reused['observation_id'], route=reused['route'],
                                measurement_valid=reused['measurement_valid'], axes_valid=reused['axes_valid'])
                return reused
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
                # Optional persisted evidence cannot prevent a fresh current
                # observation or acquire authority by surviving malformed data.
                pass
        with _trace_span('geometry.spatial_index'):
            index = SpatialSceneIndex(meshes, scene_fingerprint=state['fingerprint'],
                                      observation_cache=self.scene_cache)
            proximity = float(np.linalg.norm(focal.bbox_max - focal.bbox_min)) * .25
            plan = index.query(focal, max_distance_m=proximity, force_ids=(reference.object_id,))
            support = index.support_status
            requested_ids = (list(plan['candidate_ids']) if query['mode'] == 'overview' else
                query.get('object_ids', [mesh.object_id for mesh in meshes if mesh.object_id != focal.object_id]))
            # The display/control reference is measured once, always first and
            # charged against the same finite budget. Unsupported targets do
            # not waste a slot that a supported requested target can use.
            desired_ids = [reference.object_id] + [identity for identity in requested_ids
                                                   if identity != reference.object_id]
            supported_ids = [identity for identity in desired_ids if support[identity]['supported'] is True]
            selected_ids = ([reference.object_id] if query['mode'] == 'top1'
                            else supported_ids[:query['max_exact_pairs']])
            budget_deferred = ([] if query['mode'] == 'top1'
                               else supported_ids[query['max_exact_pairs']:])
            resource_deferred = []
            # An optional precision query may leave expensive extra pairs
            # unresolved, while the already admitted reference remains useful.
            # Default overview retains the existing collective admission rule.
            query_pairs = ([[focal.object_id, identity] for identity in selected_ids]
                if query['mode'] != 'overview' or budget_deferred else plan['query_pairs'])
            budget = work_budget_status(meshes, query_pairs=query_pairs)
            if not budget['within_budget'] and query['mode'] != 'overview':
                selected_ids = [reference.object_id]
                for identity in supported_ids[1:query['max_exact_pairs']]:
                    attempted = [[focal.object_id, value] for value in selected_ids + [identity]]
                    candidate_budget = work_budget_status(meshes, query_pairs=attempted)
                    if candidate_budget['within_budget']:
                        selected_ids.append(identity)
                    else:
                        resource_deferred.append(identity)
                query_pairs = [[focal.object_id, identity] for identity in selected_ids]
                budget = work_budget_status(meshes, query_pairs=query_pairs)
            selected = set(selected_ids)
            if query['mode'] not in {'overview', 'top1'}:
                plan = index.query(focal, max_distance_m=proximity, force_ids=tuple(selected_ids))
        result['spatial_index'] = self._query_summary(plan)
        result['geometry_work_budget'] = budget
        if not budget['within_budget']:
            return self._block(result, 'geometry_resource_limit')
        # A readable pair and an editable complete scene are separate contracts.
        # Unknown non-target solids remain in the captured/rendered scene and
        # in the output inventory; only the execution path requires every solid
        # to be supported. Neither index.supported nor terminal queries change.
        if (plan['focal_support_status']['supported'] is not True
                or any(support[identity]['supported'] is not True
                       for identity in (focal.object_id, reference.object_id))):
            state['observation'] = None
            return self._block(result, 'reference_pair_geometry_unknown')
        pair_hits, pair_misses = 0, 0
        def calculate_summary(other):
            if query.get('alignment_evidence') is False:
                with _trace_span('measurement.exact_clearance'):
                    exact = measure_pair_geometry(focal, other, need_clearance=True)
                # Full-mesh clearance and host rigid-frame validity are
                # independent of the optional legacy face-alignment probe.
                frame = pair_rigid_frame_status(focal, other)
                summary = {'measurement_valid': exact['measurement_valid'],
                    'measurement_method': exact['measurement_method'],
                    'signed_clearance_m': exact['signed_clearance_m'],
                    'is_penetrating': exact['is_penetrating'], 'strict_geometry': exact,
                    'axes_valid': None, 'axes_check': None,
                    'legacy_axes_validation_scope': LEGACY_AXES_VALIDATION_SCOPE,
                    'contact_normal_angle_deg': None, 'tangent_yaw_mismatch_deg': None,
                    'control_frame_trustworthy': None,
                    'alignment_evidence': {'status': 'not_requested',
                        'reason': 'explicit_distance_only_observation', 'execution_authority': False},
                    'rigid_frame': frame, 'rigid_frame_valid': frame['valid'],
                    'point_a_world': None, 'point_b_world': None,
                    'witness_source': 'not_available_from_exact_clearance_kernel'}
                if _validated_orthogonal_measurement(exact):
                    for field in ('point_a_world', 'point_b_world'):
                        point = np.asarray(exact.get(field), dtype=float)
                        if point.shape == (3,) and np.isfinite(point).all():
                            summary[field] = point.tolist()
                    summary['witness_source'] = ('current_original_full_mesh_surface_features'
                        if summary['point_a_world'] is not None and summary['point_b_world'] is not None
                        else 'not_available_from_exact_clearance_kernel')
                return measurement_contract(summary)
            with _trace_span("measurement.display_probe"):
                display_probe = SpatialAnomalySniffer.probe_closest_clearance(focal, other, yaw_symmetry_order=order)
            summary = _probe_summary(display_probe)
            with _trace_span("measurement.exact_clearance"):
                exact = measure_pair_geometry(focal, other, need_clearance=True)
            summary["display_signed_clearance_m"] = summary["signed_clearance_m"]
            summary["signed_clearance_m"] = exact["signed_clearance_m"]
            summary["is_penetrating"] = exact["is_penetrating"]
            orthogonal = _validated_orthogonal_measurement(exact)
            summary["measurement_valid"] = bool(exact["measurement_valid"]
                and (summary["measurement_valid"] or orthogonal))
            if orthogonal:
                summary['measurement_method'] = exact['measurement_method']
                summary['legacy_probe_measurement_valid'] = bool(display_probe.measurement_valid)
                summary['witness_source'] = 'current_original_full_mesh_surface_features'
            summary["strict_geometry"] = exact
            summary["alignment_state_is_display_only"] = True
            summary['control_frame_trustworthy'] = bool(_probe_is_trustworthy(display_probe))
            summary['rigid_frame'] = pair_rigid_frame_status(focal, other)
            summary['rigid_frame_valid'] = summary['rigid_frame']['valid']
            for field in ('point_a_world', 'point_b_world'):
                point = np.asarray(exact.get(field) if orthogonal
                    else getattr(display_probe, field), dtype=float)
                summary[field] = point.tolist() if point.shape == (3,) and np.isfinite(point).all() else None
            return measurement_contract(summary)

        def measured_summary(other):
            nonlocal pair_hits, pair_misses
            if state.get('pending') or event['event'] == 'after_action':
                pair_misses += 1
                return calculate_summary(other)
            with _trace_span("cache.pair_measurement"):
                parameters = {'yaw': order, 'need_clearance': True,
                    'rigid_frame_contract': RIGID_FRAME_CONTRACT_REVISION,
                    'collision_tolerance_m': COLLISION_TOLERANCE_M,
                    'source': state['scene']['source'], 'unit': 'm', 'coordinate_frame': 'world'}
                algorithm = 'strict-orthogonal-witness-presentation-observation-v3-20261024'
                if query.get('alignment_evidence') is False:
                    parameters['alignment_evidence'] = False
                    algorithm = 'strict-distance-without-alignment-observation-v1-20261028'
                summary, hit = self.scene_cache.pair_measurement(focal, other,
                    lambda: calculate_summary(other),
                    parameters=parameters, algorithm_version=algorithm)
            pair_hits += int(hit)
            pair_misses += int(not hit)
            return measurement_contract(summary)

        target_measurement = measured_summary(reference)
        if target_measurement['measurement_valid'] is not True:
            state['observation'] = None
            return self._block(result, 'reference_pair_measurement_unknown')
        top1_measurements = {}
        comparison_guard_m = 0.
        if query['mode'] == 'top1':
            by_id = {mesh.object_id: mesh for mesh in meshes}
            # Use the same scene-scale outward padding as the spatial index,
            # plus one upward ULP. This envelope only reduces pruning.
            scale = max(1., *(float(np.max(np.abs(mesh.bbox_min))) for mesh in meshes),
                        *(float(np.max(np.abs(mesh.bbox_max))) for mesh in meshes))
            comparison_guard_m = max(COLLISION_TOLERANCE_M, scale * (64 * np.finfo(np.float64).eps))
            selection = select_top1_pairs(requested_ids=requested_ids,
                reference_id=reference.object_id, reference_measurement=target_measurement,
                bounds_by_id={row['object_id']: row for row in plan['pairs']},
                supported_ids=supported_ids, max_exact_pairs=query['max_exact_pairs'],
                comparison_guard_m=comparison_guard_m,
                measure=lambda identity: measured_summary(by_id[identity]),
                admit=lambda identities: work_budget_status(meshes,
                    query_pairs=[[focal.object_id, identity] for identity in identities])['within_budget'])
            selected_ids = selection['selected_ids']
            selected = set(selected_ids)
            top1_measurements = selection['measurements']
            budget_deferred = selection['budget_deferred']
            resource_deferred = selection['resource_deferred']
            result['geometry_work_budget'] = work_budget_status(meshes,
                query_pairs=[[focal.object_id, identity] for identity in selected_ids])
        facts = {"source": "human_eye_geometry_observation", "scene_revision": state["scene"]["revision"],
                 "scene_source": state["scene"]["source"], "unit": "m", "coordinate_frame": "world",
                 "focal_id": focal.object_id, "reference_id": reference.object_id,
                 "yaw_symmetry_order": order, "measurement": target_measurement,
                 "rigid_frame_valid": target_measurement['rigid_frame_valid'],
                 "rigid_frame": copy.deepcopy(target_measurement['rigid_frame']),
                 "legacy_axes_validation_scope": LEGACY_AXES_VALIDATION_SCOPE,
                 "scene_memory": memory,
                 "objects": [{"object_id": m.object_id, "mark_label": m.mark_label,
                              "bbox_min": m.bbox_min.tolist(), "bbox_max": m.bbox_max.tolist()}
                             for m in meshes],
                 "scope": "Known mesh geometry; no reconstruction of unseen objects or motion-path guarantee.",
                 "host_execution": copy.deepcopy(state["scene"].get("host_execution")),
                 'spatial_index': self._query_summary(plan),
                 "collision_policy": {"tolerance_m": COLLISION_TOLERANCE_M,
                     "scope": "terminal_geometry_only",
                     "evaluator_source": "engine_geometry",
                     "independent_ground_truth": False,
                     "display_flush_tolerance_used_for_execution": False}}
        by_id = {mesh.object_id: mesh for mesh in meshes}
        contacts, unknown_objects = [], []
        for pair in plan['pairs']:
            identity = pair['object_id']
            solid = support[identity]
            reasons = []
            if solid['supported'] is not True:
                reasons.append(solid.get('reason', 'solid_support_unknown'))
                contact = copy.deepcopy(pair)
            elif identity in selected:
                measured = (target_measurement if identity == reference.object_id
                            else top1_measurements[identity] if identity in top1_measurements
                            else measured_summary(by_id[identity]))
                contact = {'object_id': identity, **measured}
                if measured['measurement_valid'] is not True:
                    reason = measured.get('strict_geometry', {}).get('reason', 'pair_measurement_unknown')
                    # A resource rejection remains a hard boundary even when
                    # the main reference pair happened to be measurable.
                    if reason == 'geometry_resource_limit':
                        state['observation'] = None
                        return self._block(result, 'geometry_resource_limit')
                    reasons.append(reason)
            else:
                contact = copy.deepcopy(pair)
            if reasons:
                contact.update(measurement_valid=False, collision_assessment_valid=False,
                    signed_clearance_m=None, clearance_exact=False, is_penetrating=None,
                    point_a_world=None, point_b_world=None, reason_codes=reasons,
                    geometry_support='unknown' if solid['supported'] is not True else 'supported')
                unknown_objects.append({'object_id': identity,
                    'geometry_support': contact['geometry_support'], 'reason_codes': list(reasons)})
            contacts.append(measurement_contract(contact))
        query_result = summarize_query(query, requested_ids=requested_ids,
            reference_id=reference.object_id, contacts=contacts,
            budget_deferred=budget_deferred, resource_deferred=resource_deferred,
            top1_supported_ids=supported_ids, comparison_guard_m=comparison_guard_m)
        # A planned candidate may be deferred or unsupported. Observation
        # precision counts describe returned results, not the plan's workload.
        for summary in (result['spatial_index'], facts['spatial_index']):
            summary.update(exact_pair_count=query_result['exact_pair_count'],
                measured_pair_count=query_result['measured_pair_count'],
                count_scope='observation_measurement_results')
        partial = bool(unknown_objects) or query_result['status'] != 'complete'
        scene_assessment = {'status': 'unknown' if unknown_objects else 'not_evaluated',
            'scope': 'all_scene_objects',
            'geometry_support': 'supported' if index.supported else 'unknown',
            'unknown_object_ids': [item['object_id'] for item in unknown_objects],
            'reason_codes': (list(dict.fromkeys(
                'scene_solid_support_unknown' if item['geometry_support'] == 'unknown'
                else 'scene_pair_measurement_unknown' for item in unknown_objects))
                if unknown_objects else ['scene_execution_not_evaluated_by_observation'])}
        facts.update(scene_contacts=contacts, unknown_objects=unknown_objects,
            observation_status='partial' if partial else 'complete',
            scene_assessment=scene_assessment, query=query, query_result=query_result)
        if 'support_plane_discovery' in query:
            # Explicit observation-only work on this current snapshot. Never
            # broaden the subsequent action gate or discard other unknowns.
            from .support_plane_discovery import discover_support_planes
            try:
                with _trace_span('observation.support_plane_discovery'):
                    discovery = discover_support_planes(state['scene'], focal.object_id,
                        reference.object_id, query['support_plane_discovery'])
            except Exception as exc:
                # Optional discovery failure does not erase a valid strict
                # observation, or turn an unavailable selector into a choice.
                discovery = {'status': 'unknown', 'candidates': [],
                    'total_candidate_count': None, 'omitted_candidate_count': None,
                    'ambiguous': None, 'reason_codes': ['support_plane_discovery_unavailable'],
                    'error_type': type(exc).__name__,
                    'scene_revision': state['scene']['revision'],
                    'scene_fingerprint': state['fingerprint'],
                    'focal_id': focal.object_id, 'reference_id': reference.object_id,
                    'scope': 'current_pair_support_plane_discovery_not_execution_authorization',
                    'execution_authority': False}
            facts['support_plane_discovery'] = discovery
            result['support_plane_discovery'] = copy.deepcopy(discovery)
        capabilities = build_scene_capabilities(state['scene'], scene_fingerprint=state['fingerprint'],
            computed_evidence={'scene_revision': state['scene']['revision'],
                'scene_fingerprint': state['fingerprint'], 'solid_support': support,
                'pair_measurements': [{**contact, 'focal_id': focal.object_id,
                    'reference_id': contact['object_id']} for contact in contacts]},
            object_ids=[focal.object_id, reference.object_id])
        facts['scene_capabilities'] = capabilities
        result['scene_capabilities'] = copy.deepcopy(capabilities)
        facts['measurement_cache'] = {'hits': pair_hits, 'misses': pair_misses,
            'scope': 'observation_only_exact_content_in_process',
            'execution_gate_uses_cache': False, 'stats': self.scene_cache.stats()}
        facts['attention'] = {'decision': 'hold', 'reason_codes': ['image_not_requested']}
        attention_error_retry_at = None
        refill_attempted = False
        try:
            if not event.get("include_image", True):
                raise ValueError("image_not_requested_by_text_only_host")
            label_plan = None
            refill_collector = None
            refill_observer = None
            refill_costs = {'setup_ms': 0., 'capture_ms': 0., 'error_type': None}
            try:
                label_arguments = dict(focal_id=focal.object_id,
                    reference_id=reference.object_id, contacts=facts['scene_contacts'],
                    requested_ids=query.get('object_ids', ()), visual_focus_ids=query.get('label_object_ids', ()),
                    scene_revision=state['scene']['revision'], scene_fingerprint=state['fingerprint'])
                refill_eligible = (self.quad_size >= 128 and not query.get('object_ids')
                    and not query.get('label_object_ids') and not query.get('visual_diagnostic'))
                if refill_eligible and _refill_retry_blocked(refill_feedback, now):
                    # Even an attention retry or TTL cache miss must not spend
                    # setup/capture work during this optional feature's cooldown.
                    label_plan = build_task_label_plan(meshes, **label_arguments)
                    facts['label_refill'] = {'applied': False, 'status': 'hold',
                        'reason': ('visible_refill_retry_exhausted' if refill_feedback['retry_at_s'] is None
                                   else 'visible_refill_retry_cooldown'),
                        'additional_cost_ms': 0., 'current_event_refill_cost_ms': 0.,
                        'candidate_raster_count': 0, 'current_event_candidate_raster_count': 0,
                        'new_readable_object_ids': [], 'evidence_reused': False,
                        'retry': _refill_retry_evidence(refill_feedback), 'execution_authority': False}
                elif refill_eligible:
                    setup_started = visible_refill_clock()
                    try:
                        label_plan, candidate_pool = _build_task_label_bundle(meshes, **label_arguments)
                    except Exception as exc:
                        # Optional pool preparation cannot remove the original
                        # priority plan or its measured-risk image.
                        label_plan = build_task_label_plan(meshes, **label_arguments)
                        candidate_pool = ()
                        facts['label_refill'] = {'applied': False, 'status': 'unavailable',
                            'reason': 'candidate_pool_unavailable', 'error_type': type(exc).__name__,
                            'additional_cost_ms': max(0., (visible_refill_clock()-setup_started)*1000.),
                            'candidate_raster_count': 0, 'new_readable_object_ids': [],
                            'execution_authority': False}
                    if len(candidate_pool) > label_plan['max_related_labels']:
                        bundle_cost = max(0., (visible_refill_clock() - setup_started) * 1000.)
                        try:
                            refill_collector = VisibleRefillCollector(label_plan, candidate_pool,
                                scene_fingerprint=state['fingerprint'], setup_cost_ms=bundle_cost,
                                quad_size=self.quad_size)
                        except Exception as exc:
                            facts['label_refill'] = {'applied': False, 'status': 'unavailable',
                                'reason': 'candidate_collector_unavailable', 'error_type': type(exc).__name__,
                                'additional_cost_ms': max(0., (visible_refill_clock()-setup_started)*1000.),
                                'candidate_raster_count': 0, 'new_readable_object_ids': [],
                                'execution_authority': False}
                        refill_costs['setup_ms'] = max(0., (visible_refill_clock() - setup_started) * 1000.)

                        if refill_collector is not None:
                            def refill_observer(index, *parts):
                                if refill_costs['error_type'] is not None:
                                    return
                                started = visible_refill_clock()
                                try:
                                    refill_collector.observe_view(index, *parts)
                                except Exception as exc:
                                    refill_costs['error_type'] = type(exc).__name__
                                finally:
                                    refill_costs['capture_ms'] += max(0., (visible_refill_clock() - started) * 1000.)
                else:
                    label_plan = build_task_label_plan(meshes, **label_arguments)
            except (TypeError, ValueError, OverflowError) as exc:
                refill_collector = refill_observer = None
                # A bounded alias collision or invalid display plan cannot
                # remove the legacy image or change measured geometry.
                facts['label_presentation'] = {'status': 'legacy_fallback',
                    'reason': 'task_label_plan_unavailable', 'error_type': type(exc).__name__,
                    'execution_authority': False}
            render_extras = {'raw_observer': refill_observer} if refill_observer is not None else {}
            with _trace_span("render.scene_canvas"):
                canvas, visual_metadata, prepared_render = _render_scene_canvas_prepared(meshes, self.quad_size,
                    focal_id=focal.object_id, reference_id=reference.object_id,
                    scene_fingerprint=state['fingerprint'], label_plan=label_plan, **render_extras)
            default_canvas, default_visual_metadata = canvas, visual_metadata
            # A conservative shared allowance includes existing attention and
            # mandatory Q4/caption work after base Q1-Q3. No explicit visual
            # request takes this timing or the optional local-view path.
            local_started = local_view_clock() if query.get('label_object_ids') else None
            refill_shared_started = visible_refill_clock() if refill_collector is not None else None
            try:
                cooling = bool(retry_feedback and now < retry_feedback['retry_at_s'])
                if cooling:
                    attention_state = None
                    visual_metadata = copy.deepcopy(visual_metadata)
                    visual_metadata['attention'] = {'decision': 'hold', 'applied': False,
                        'shifted': False, 'state_to_commit': None,
                        'reason_codes': ['attention_cost_cooldown'],
                        'additional_cost_ms': 0.0,
                        'cost_scope': 'candidate_not_attempted_due_to_bounded_cost_feedback',
                        'visibility_verified': False, 'readability_verified': False,
                        'execution_authority': False}
                else:
                    with _trace_span("render.attention"):
                        canvas, visual_metadata, attention_state = apply_attention_to_canvas(
                            canvas, visual_metadata, meshes, focal_id=focal.object_id,
                            reference_id=reference.object_id, contacts=facts['scene_contacts'],
                            scene_fingerprint=state['fingerprint'], previous=state.get('attention_state'), now_s=now,
                            prepared_render=prepared_render)
                if retry_eligible and not cooling:
                    attention = visual_metadata['attention']
                    if _ATTENTION_BUDGET_REASONS.intersection(attention.get('reason_codes', ())):
                        failures = retry_feedback['budget_failures'] + 1 if retry_feedback else 1
                        retry_feedback = _attention_retry_record(key, now, failures=failures)
                    else:
                        # A complete current confirmation already proves the
                        # candidate's cost, visibility and readable sampling
                        # gain. Budget history cannot withhold that view. A
                        # non-budget hold also ends the consecutive cost chain.
                        retry_feedback = None
                    if retry_feedback:
                        state['attention_retry'] = retry_feedback
                    else:
                        state.pop('attention_retry', None)
                if retry_eligible:
                    visual_metadata['attention']['retry'] = _attention_retry_evidence(
                        attempted=not cooling, cooldown=cooling,
                        record=retry_feedback, discarded_pose=discarded_pose)
                facts['attention'] = visual_metadata['attention']
                if attention_state is not None:
                    state['attention_state'] = attention_state
            except Exception as exc:
                # An optional gaze choice cannot invalidate measured geometry.
                canvas, visual_metadata = default_canvas, default_visual_metadata
                facts['attention'] = {'decision': 'hold', 'reason_codes': ['attention_unavailable'],
                                      'error_type': type(exc).__name__}
                if retry_eligible:
                    # An optional rendering error is not evidence of another
                    # budget failure. Preserve geometry and end the cost chain.
                    retry_feedback = None
                    state.pop('attention_retry', None)
                    attention_error_retry_at = now + 1.0
                    facts['attention']['retry'] = _attention_retry_evidence(attempted=True,
                        record=retry_feedback, discarded_pose=discarded_pose)
                visual_metadata['attention'] = copy.deepcopy(facts['attention'])
            if not visual_metadata['raster_schedule']['canvas_complete']:
                with _trace_span("render.q4_fallback"):
                    canvas, visual_metadata = _finalize_prepared_scene_q4(canvas, visual_metadata, prepared_render,
                        scene_fingerprint=state['fingerprint'])
            if not visual_metadata['raster_schedule']['canvas_complete']:
                raise ValueError('Incomplete observation canvas cannot be delivered')
            with _trace_span('render.orthogonal_measurement_caption'):
                canvas, visual_metadata = _annotate_orthogonal_target_measurement(
                    canvas, visual_metadata, meshes, focal_id=focal.object_id,
                    reference_id=reference.object_id,
                    contact={'object_id': reference.object_id, **target_measurement},
                    prepared_render=prepared_render)
            if query.get('visual_diagnostic') == 'contact_section':
                try:
                    with _trace_span('render.contact_section'):
                        section_canvas, section_evidence = append_contact_section(
                            canvas, meshes, target_measurement, focal_id=focal.object_id,
                            reference_id=reference.object_id, quad_size=self.quad_size)
                    if (not isinstance(section_evidence, dict) or section_evidence.get('status') != 'available'
                            or section_canvas.mode != 'RGB' or section_canvas.height != canvas.height
                            or section_evidence.get('panel_offset_px') != [canvas.width, 0]
                            or section_evidence.get('panel_size_px') != [section_canvas.width-canvas.width, canvas.height]
                            or section_canvas.width <= canvas.width):
                        raise ValueError('Incomplete analytical section result')
                    json.dumps(section_evidence, allow_nan=False)
                    section_metadata = copy.deepcopy(visual_metadata)
                    section_metadata['diagnostic_panel'] = {key: copy.deepcopy(section_evidence[key])
                        for key in ('kind', 'status', 'scope', 'panel_offset_px', 'panel_size_px',
                                    'natural_visibility_certified', 'execution_authority')}
                    section_metadata['diagnostic_panel']['evidence_path'] = 'visual_diagnostics'
                    section_metadata['natural_canvas_size'] = section_metadata['canvas_size']
                    section_metadata['canvas_size'] = list(section_canvas.size)
                    section_metadata['view_layout'] += '_with_analytical_contact_section'
                    # Publish only a fully prepared diagnostic. Optional errors
                    # must keep natural pixels and their dimensions together.
                    canvas, visual_metadata = section_canvas, section_metadata
                    facts['visual_diagnostics'] = section_evidence
                except Exception as exc:
                    facts['visual_diagnostics'] = {'kind': 'contact_section', 'status': 'unavailable',
                        'reason': str(exc), 'error_type': type(exc).__name__, 'execution_authority': False,
                        'natural_visibility_certified': False}
            if refill_collector is not None:
                original_canvas, original_visual = canvas, visual_metadata
                before_refill = max(0., (visible_refill_clock() - refill_shared_started) * 1000.)
                finish_started = visible_refill_clock()
                known_refill = None
                try:
                    refill_attempted = True
                    if refill_costs['error_type'] is not None:
                        raise ValueError('Same-raster candidate collection unavailable')
                    delivery, visual_metadata, known_refill = refill_collector.finish(
                        canvas, visual_metadata, meshes, scene_fingerprint=state['fingerprint'],
                        remaining_budget_ms=max(0., refill_budget.shared_ms-before_refill), proposal_only=True)
                    if not isinstance(known_refill, dict):
                        raise ValueError('Missing visible refill receipt')
                    if type(delivery) is VisibleRefillProposal:
                        if (known_refill.get('applied') is not False
                                or known_refill.get('status') != 'proposal_ready'
                                or known_refill.get('new_readable_object_ids') != []):
                            raise ValueError('Refill proposal claimed delivery before composition')
                        new_ids = known_refill.get('candidate_readable_object_ids')
                        if (type(new_ids) is not list or len(new_ids) != 1
                                or type(delivery) is not VisibleRefillProposal
                                or visual_metadata.get('canvas_size') != original_visual.get('canvas_size')
                                or visual_metadata.get('task_labels') != original_visual.get('task_labels')
                                or visual_metadata.get('object_labels') != original_visual.get('object_labels')
                                or len(visual_metadata.get('views', [])) != 4):
                            raise ValueError('Incomplete visible candidate delivery')
                        changed = [index for index in range(4)
                                   if visual_metadata['views'][index] != original_visual['views'][index]]
                        if len(changed) != 1 or changed[0] >= 3:
                            raise ValueError('Refill changed more than one natural context view')
                        marked = [(index, row) for index, view in enumerate(visual_metadata['views'])
                                  for row in view.get('projected_labels', [])
                                  if row.get('display_source') == 'visible_candidate_refill']
                        if (len(marked) != 1 or marked[0][0] != changed[0]
                                or marked[0][1].get('object_id') != new_ids[0]
                                or marked[0][1].get('display_label') != next(
                                    row['display_label'] for row in original_visual['object_labels']
                                    if row['object_id'] == new_ids[0])):
                            raise ValueError('Refill receipt differs from the delivered identity row')
                        size = original_visual['quad_size']
                        if (type(delivery.view_index) is not int or delivery.view_index != changed[0]
                                or known_refill.get('source_view_index') != changed[0]
                                or delivery.object_id != new_ids[0]
                                or not refill_collector.claim_proposal(delivery,
                                    canvas=original_canvas, metadata=original_visual)):
                            raise ValueError('Visible refill proposal is stale, changed or unissued')
                        if not _refill_tile_has_new_pixels(delivery.tile, original_canvas,
                                view_index=changed[0], quad_size=size,
                                label_box=marked[0][1].get('label_box_px')):
                            raise ValueError('Refill proposal added no pixels')
                        original_drawn = {row['object_id'] for view in original_visual['views']
                            for row in view.get('projected_labels', [])}
                        selected = set(label_plan['related_object_ids'])
                        if (set(new_ids) & original_drawn or known_refill.get('donor_object_id') not in selected
                                or known_refill['donor_object_id'] in original_drawn
                                or len((selected & original_drawn) | set(new_ids)) > label_plan['max_related_labels']):
                            raise ValueError('Refill lost its empty global slot or added no identity')
                        # Only this layer composes the canvas. A sized RGB tile
                        # pasted without a mask into its exact bounds cannot
                        # alter another view, including CONTACT.
                        canvas = original_canvas.copy()
                        canvas.paste(delivery.tile, ((changed[0] % 2)*size, (changed[0] // 2)*size))
                        known_refill = {**known_refill, 'applied': True, 'status': 'applied',
                            'reason': 'one_same_priority_identity_added',
                            'new_readable_object_ids': list(new_ids),
                            'actual_delivered_default_related_count': len(selected & original_drawn)+1}
                    elif known_refill.get('applied') or known_refill.get('status') == 'proposal_ready':
                        raise ValueError('Refill delivery requires an issued single-view proposal')
                    elif delivery is not original_canvas or visual_metadata is not original_visual:
                        raise ValueError('Unadopted refill must preserve original objects')
                    json.dumps(known_refill, allow_nan=False)
                    finish_cost = max(0., (visible_refill_clock()-finish_started)*1000.)
                    total_cost = refill_costs['setup_ms'] + refill_costs['capture_ms'] + finish_cost
                    after_refill = max(0., (visible_refill_clock()-refill_shared_started)*1000.)
                    exceeded = (['local'] if total_cost > refill_budget.incremental_ms else []) + (
                        ['shared'] if after_refill > refill_budget.shared_ms else [])
                    if known_refill.get('applied') and exceeded:
                        canvas, visual_metadata = original_canvas, original_visual
                        known_refill = {**known_refill, 'applied': False, 'status': 'hold',
                            'reason': 'visible_refill_integration_budget_exceeded',
                            'candidate_readable_object_ids': known_refill['new_readable_object_ids'],
                            'new_readable_object_ids': [],
                             'budget_checkpoint': 'router_commit',
                             'budget_failure_scope': 'both' if len(exceeded) == 2 else exceeded[0],
                            'actual_delivered_default_related_count': len(selected & original_drawn)}
                    facts['label_refill'] = {**known_refill,
                        'candidate_additional_cost_ms': known_refill.get('additional_cost_ms'),
                        'additional_cost_ms': total_cost, 'setup_cost_ms': refill_costs['setup_ms'],
                        'collection_cost_ms': refill_costs['capture_ms'], 'finalization_cost_ms': finish_cost,
                        'shared_budget_elapsed_before_ms': before_refill, 'shared_budget_elapsed_after_ms': after_refill,
                        'shared_budget_limit_ms': refill_budget.shared_ms,
                        'budget_ms': refill_budget.incremental_ms,
                        'budget_policy': refill_budget.descriptor(), 'evidence_reused': False,
                        'budget_exceeded': exceeded,
                        'budget_accounting': 'independent_incremental_and_post_Q1_Q3_wall_windows',
                        'current_event_candidate_raster_count': 0, 'current_event_refill_cost_ms': total_cost,
                        'cost_scope': 'pool_and_collector_setup_raw_collection_final_helper_and_checks_excludes_PNG',
                        'execution_authority': False}
                except Exception as exc:
                    canvas, visual_metadata = original_canvas, original_visual
                    finish_cost = max(0., (visible_refill_clock()-finish_started)*1000.)
                    total_cost = refill_costs['setup_ms'] + refill_costs['capture_ms'] + finish_cost
                    known = known_refill if isinstance(known_refill, dict) else {}
                    facts['label_refill'] = {**known, 'applied': False, 'status': 'unavailable',
                        'reason': 'visible_refill_unavailable', 'error_type': type(exc).__name__,
                        'collection_error_type': refill_costs['error_type'],
                        'candidate_readable_object_ids': known.get('candidate_readable_object_ids',
                            known.get('new_readable_object_ids', [])),
                        'new_readable_object_ids': [],
                        'actual_delivered_default_related_count': (
                            len(known['actual_base_drawn_selected_object_ids'])
                            if type(known.get('actual_base_drawn_selected_object_ids')) is list else None),
                        'candidate_raster_count': 0,
                        'candidate_additional_cost_ms': known.get('additional_cost_ms'),
                        'additional_cost_ms': total_cost, 'setup_cost_ms': refill_costs['setup_ms'],
                        'collection_cost_ms': refill_costs['capture_ms'], 'finalization_cost_ms': finish_cost,
                        'current_event_refill_cost_ms': total_cost, 'current_event_candidate_raster_count': 0,
                        'shared_budget_elapsed_before_ms': before_refill,
                        'shared_budget_elapsed_after_ms': max(0., (visible_refill_clock()-refill_shared_started)*1000.),
                        'shared_budget_limit_ms': refill_budget.shared_ms,
                        'budget_ms': refill_budget.incremental_ms,
                        'budget_policy': refill_budget.descriptor(),
                        'evidence_reused': False, 'execution_authority': False}
            if local_started is not None:
                original_canvas, original_visual = canvas, visual_metadata
                elapsed_before_local = max(0., (local_view_clock() - local_started) * 1000)
                local_receipt = None
                try:
                    canvas, visual_metadata, local_receipt = append_gain_local_view(
                        canvas, visual_metadata, meshes, scene_fingerprint=state['fingerprint'],
                        remaining_budget_ms=max(0., 40. - elapsed_before_local),
                        diagnostic_requested=query.get('visual_diagnostic') == 'contact_section')
                    if local_receipt.get('applied'):
                        panels = visual_metadata.get('supplemental_views')
                        if (not isinstance(panels, list) or len(panels) != 1
                                or canvas.mode != 'RGB' or canvas.height != original_canvas.height
                                or panels[0]['panel_offset_px'] != [original_canvas.width, 0]
                                or panels[0]['panel_size_px'] != [canvas.width-original_canvas.width, canvas.height]
                                or canvas.width <= original_canvas.width
                                or visual_metadata['views'] != original_visual['views']
                                or visual_metadata['canvas_size'] != list(canvas.size)):
                            raise ValueError('Incomplete or changed local-view delivery')
                    elif canvas is not original_canvas or visual_metadata is not original_visual:
                        raise ValueError('Unadopted local view must retain original canvas and metadata')
                    elapsed_after_local = max(0., (local_view_clock() - local_started) * 1000)
                    complete_local_cost = max(0., elapsed_after_local - elapsed_before_local)
                    if local_receipt.get('applied') and (elapsed_after_local > 40.
                            or complete_local_cost > local_receipt['budget_ms']):
                        # Include final integration checks in the cooperative
                        # allowance. A completed but late candidate is not a
                        # delivered improvement, and it must not trigger retry.
                        canvas, visual_metadata = original_canvas, original_visual
                        local_receipt = {**local_receipt, 'applied': False, 'status': 'hold',
                            'reason': 'local_view_integration_budget_exceeded',
                            'candidate_readable_object_ids': local_receipt['new_readable_object_ids'],
                            'new_readable_object_ids': [],
                            'still_missing_ids': sorted(set(query['label_object_ids'])
                                - set(local_receipt['base_drawn_object_ids']))}
                    facts['local_view'] = {**local_receipt,
                        'evidence_reused': False,
                        'current_event_candidate_raster_count': local_receipt.get('candidate_raster_count'),
                        'current_event_local_view_cost_ms': complete_local_cost,
                        'candidate_additional_cost_ms': local_receipt.get('additional_cost_ms'),
                        'additional_cost_ms': complete_local_cost,
                        'shared_budget_elapsed_before_ms': elapsed_before_local,
                        'shared_budget_elapsed_after_ms': elapsed_after_local,
                        'shared_budget_limit_ms': 40.,
                        'shared_budget_scope': 'after_base_Q1_Q3_attention_Q4_caption_and_local_candidate_excludes_PNG'}
                except Exception as exc:
                    canvas, visual_metadata = original_canvas, original_visual
                    failed_elapsed = max(0., (local_view_clock() - local_started) * 1000)
                    failed_cost = max(0., failed_elapsed - elapsed_before_local)
                    known = local_receipt if isinstance(local_receipt, dict) else {}
                    base_drawn = {row['object_id'] for view in original_visual['views']
                                  for row in view.get('projected_labels', ())}
                    facts['local_view'] = {'applied': False, 'status': 'unavailable',
                        'reason': 'local_view_unavailable', 'error_type': type(exc).__name__,
                        'attempted': known.get('attempted'),
                        'candidate_raster_count': known.get('candidate_raster_count'),
                        'candidate_additional_cost_ms': known.get('additional_cost_ms'),
                        'additional_cost_ms': failed_cost,
                        'current_event_local_view_cost_ms': failed_cost,
                        'current_event_candidate_raster_count': known.get('candidate_raster_count'),
                        'new_readable_object_ids': [],
                        'candidate_readable_object_ids': known.get('new_readable_object_ids'),
                        'base_drawn_object_ids': sorted(set(query['label_object_ids']) & base_drawn),
                        'still_missing_ids': sorted(set(query['label_object_ids']) - base_drawn),
                        'shared_budget_elapsed_before_ms': elapsed_before_local,
                        'shared_budget_elapsed_after_ms': failed_elapsed,
                        'shared_budget_limit_ms': 40., 'evidence_reused': False,
                        'cost_scope': 'known_router_wall_time_including_optional_failure_excludes_PNG',
                        'unknown_attempt_or_raster_count_is_not_zero': True,
                        'execution_authority': False}
            coverage = _task_label_coverage_summary(visual_metadata)
            if coverage is not None:
                facts['label_presentation'] = coverage
            with _trace_span("encoding.png", kind="encoding", source_name="protocol_serialize"):
                buf = io.BytesIO(); canvas.save(buf, format="PNG")
            with _trace_span("encoding.base64", kind="encoding", source_name="protocol_serialize"):
                result["image"] = {"type": "image", "mimeType": "image/png",
                                   "data": base64.b64encode(buf.getvalue()).decode("ascii")}
            facts["canvas"] = visual_metadata
        except ValueError as exc:
            facts["canvas"] = {"omitted": "text_only_host_delivery" if not event.get("include_image", True)
                               else "rendering_resource_or_numeric_limit", "detail": str(exc)}
            if query.get('label_object_ids'):
                facts['label_presentation'] = {
                    'status': 'unavailable',
                    'reason': 'scene_canvas_unavailable' if event.get('include_image', True) else 'image_not_requested',
                    'visual_focus_requested_ids': list(query['label_object_ids']),
                    'scope': 'display_request_only_not_geometry_or_execution',
                    'execution_authority': False}
            if query.get('visual_diagnostic') == 'contact_section':
                facts['visual_diagnostics'] = {'kind': 'contact_section', 'status': 'unavailable',
                    'reason': 'natural_four_view_canvas_unavailable', 'execution_authority': False,
                    'natural_visibility_certified': False}
        refill_receipt = facts.get('label_refill')
        if refill_attempted and isinstance(refill_receipt, dict):
            # This is request-driven recovery, not a background renderer. The
            # actual expense of an overrun is never clipped to the allowance.
            attempt_record = _refill_budget_failure(refill_feedback, key=key, now=now,
                cost_ms=refill_receipt['additional_cost_ms'])
            transient_budget_hold = (refill_receipt.get('reason') in _REFILL_BUDGET_REASONS
                and refill_receipt.get('budget_failure_scope') in {'local', 'shared', 'both'})
            refill_receipt['retry'] = _refill_retry_evidence(attempt_record, attempted=True)
            if retry_eligible and transient_budget_hold:
                refill_feedback = attempt_record
                state['refill_retry'] = attempt_record
            else:
                state.pop('refill_retry', None)
                refill_feedback = None
                refill_receipt['retry'].update(retry_at_s=None, exhausted=False,
                    recovered=bool(refill_receipt.get('applied')))
        elif retry_eligible and not (isinstance(refill_receipt, dict) and refill_receipt.get('reason') in
                  {'visible_refill_retry_cooldown', 'visible_refill_retry_exhausted'}):
            # A current no-op/unreadable/error result is not evidence that a
            # transient-budget retry can add a useful identity.
            state.pop('refill_retry', None)
            refill_feedback = None
        if refill_regeneration_started is not None and isinstance(refill_receipt, dict):
            refill_receipt['retry_regeneration_after_key_through_PNG_ms'] = max(0.,
                (visible_refill_clock() - refill_regeneration_started) * 1000.)
        with _trace_span("observation.context_encode", kind="encoding", source_name="protocol_serialize"):
            context_text = json.dumps(facts, ensure_ascii=False, allow_nan=False)
        reasons = (["spatial_3d_observed", "scene_observation_partial"]
                   if partial else ["spatial_3d_observed"])
        if target_measurement['rigid_frame_valid'] is not True:
            reasons.append('rigid_frame_unverified')
        result.update(route="engine", reason_codes=reasons,
                       observation_status='partial' if partial else 'complete',
                       scene_assessment=copy.deepcopy(scene_assessment),
                       query_result=copy.deepcopy(query_result),
                       engine_invoked=True, observation_id=None if partial else uuid.uuid4().hex,
                       allow_action=False if partial else None,
                      measurement_valid=target_measurement["measurement_valid"], axes_valid=target_measurement['axes_valid'],
                       rigid_frame_valid=target_measurement['rigid_frame_valid'],
                       rigid_frame=copy.deepcopy(target_measurement['rigid_frame']),
                      context_text=context_text,
                       requires_reobserve=partial or not (target_measurement['rigid_frame_valid'] and target_measurement["measurement_valid"]))
        state["observation"] = {"key": key, "created": now, "fingerprint": state["fingerprint"],
                                "contract_revision": OBSERVATION_CONTRACT_REVISION,
                                "focal_id": focal.object_id, "reference_id": reference.object_id,
                                "yaw": order, "result": copy.deepcopy(result)}
        attention = facts.get('attention', {})
        policy = attention.get('policy', attention.get('proposal', {}).get('policy', {}))
        if event.get('include_image', True) and state.get('attention_state') and 'min_dwell_s' in policy:
            # A dwell can retain an older useful view as well as hold default
            # Q4. Both must reconsider better candidates when the dwell ends.
            retry_at = state['attention_state']['last_shift_s'] + policy['min_dwell_s']
            if now < retry_at:
                state['observation']['attention_recheck_after'] = retry_at
        if retry_feedback and now < retry_feedback['retry_at_s']:
            # The earliest future reconsideration wins. Default TTL and dwell
            # must not conceal a legitimate retry when their own expiry is later.
            state['observation']['attention_recheck_after'] = min(
                state['observation'].get('attention_recheck_after', float('inf')),
                retry_feedback['retry_at_s'])
        if attention_error_retry_at is not None and now < attention_error_retry_at:
            # A transient optional rendering error is not sustained overload,
            # but its default image must not hide recovery for the whole TTL.
            state['observation']['attention_recheck_after'] = min(
                state['observation'].get('attention_recheck_after', float('inf')),
                attention_error_retry_at)
        if refill_feedback is not None and refill_feedback['retry_at_s'] is not None:
            state['observation']['refill_recheck_after'] = refill_feedback['retry_at_s']
        _trace_annotate(cache_hit=False, engine_invoked=True, observation_id=result['observation_id'],
                        measurement_cache_hit=pair_hits > 0, route=result['route'],
                        measurement_valid=result['measurement_valid'], axes_valid=result['axes_valid'])
        return result

    @staticmethod
    def _query_summary(plan):
        return {key: copy.deepcopy(plan[key]) for key in ('algorithm_version', 'supported',
            'max_distance_m', 'coverage_object_count', 'scope', 'collision_tolerance_m', 'reason_codes')} | {
                'exact_pair_count': len(plan['candidate_ids']),
                'candidate_pair_count': len(plan['candidate_ids']),
                'count_scope': 'planned_pair_queries_not_exact_distance_results',
                'separated_pair_count': len(plan['separated_records']),
                'lower_bounds_are_exact_clearance': False}

    @_trace_stage('geometry.terminal_query')
    def _terminal_geometry(self, meshes, focal, reference, fingerprint, *,
                           stage_name='geometry.candidate_collision'):
        # Both proposed and actual terminal geometry are queried independently.
        # The current focal replaces its old geometry for support/budget checks.
        current = [focal if mesh.object_id == focal.object_id else mesh for mesh in meshes]
        index = SpatialSceneIndex(current, scene_fingerprint=fingerprint)
        plan = index.query(focal, force_ids=(reference.object_id,))
        budget = work_budget_status(current, query_pairs=plan['query_pairs'])
        if not budget['within_budget']:
            return plan, [], ('unknown', 'geometry_resource_limit')
        if not plan['supported']:
            return plan, [], ('unknown', ','.join(plan['reason_codes']))
        by_id = {mesh.object_id: mesh for mesh in current}
        checks = []
        for pair in plan['pairs']:
            if pair['is_candidate']:
                with _trace_span(stage_name):
                    with _trace_span('geometry.narrow_phase'):
                        measured = measure_pair_geometry(focal, by_id[pair['object_id']])
                checks.append({'object_id': pair['object_id'], **measured})
                if not measured['measurement_valid']:
                    return plan, checks, ('unknown', pair['object_id'])
                if measured['is_penetrating']:
                    return plan, checks, ('collision', pair['object_id'])
            else:
                checks.append(copy.deepcopy(pair))
        return plan, checks, None

    @_trace_stage("geometry.before_action_gate")
    def _before_action(self, event, state, meshes, focal, reference, order, result):
        result["execution_scope"] = "terminal_geometry_only"
        obs = state.get("observation")
        if obs and (obs['result'].get('observation_status') == 'partial'
                    or obs['result'].get('scene_assessment', {}).get('status') == 'unknown'):
            return self._block(result, 'partial_observation_not_actionable')
        if (not obs or not isinstance(obs['result'].get('observation_id'), str)
                or not obs['result']['observation_id']
                or event.get("observation_id") != obs["result"]["observation_id"]
                or obs["fingerprint"] != state["fingerprint"]):
            return self._block(result, "stale_or_missing_observation")
        if obs.get('contract_revision') != OBSERVATION_CONTRACT_REVISION:
            return self._block(result, 'stale_or_missing_observation')
        age = self._clock() - obs["created"]
        if not 0 <= age <= self.observation_ttl_s:
            return self._block(result, "observation_expired")
        if (obs["focal_id"] != focal.object_id or obs["reference_id"] != reference.object_id
                or obs["yaw"] != order):
            return self._block(result, "observation_pair_mismatch")
        if state.get("pending"):
            return self._block(result, "action_pending_readback")
        action = event.get("action")
        allowed = {"focal_id", "reference_id", "translation", "rotation_euler_deg"}
        if (not isinstance(action, dict) or set(action) - allowed
                or not ({"translation", "rotation_euler_deg"} & set(action))):
            return self._block(result, "unsupported_action", "Only explicit world-space delta SE(3) is supported.")
        try:
            translation = _vector(action.get("translation", [0, 0, 0]))
            euler = _vector(action.get("rotation_euler_deg", [0, 0, 0]))
        except (TypeError, ValueError) as exc:
            return self._block(result, "invalid_action", str(exc))
        with _trace_span("geometry.gate_frame_probe"):
            pre = SpatialAnomalySniffer.probe_closest_clearance(focal, reference, yaw_symmetry_order=order)
            rigid_frame = pair_rigid_frame_status(focal, reference)
        result["engine_invoked"] = True
        result['rigid_frame_valid'] = rigid_frame['valid']
        result['rigid_frame'] = rigid_frame
        result['axes_valid'] = bool(pre.axes_valid)
        geometry_valid = bool(pre.measurement_valid and np.isfinite(pre.signed_clearance_m))
        if rigid_frame['valid'] is True and not geometry_valid:
            # The frozen display/controller probe does not classify concave
            # solids. A newly certified bounded solid can supply this current
            # pair measurement while the explicit host rigid frame remains a
            # separate requirement. Endpoint and actual readback checks below
            # always run independently and never consult observation caches.
            with _trace_span('geometry.gate_exact_orthogonal_pair'):
                geometry_valid = _validated_orthogonal_measurement(
                    measure_pair_geometry(focal, reference, need_clearance=True))
        if rigid_frame['valid'] is not True or not geometry_valid:
            return self._block(result, "unverified_geometry_or_frame")
        rotation = SE3AlignmentMath.euler_xyz_to_matrix(*euler)
        # Exact proposed action, without the controller's nominal correction or
        # deadband. Detached reconstruction avoids retaining transform parents.
        candidate = focal.rotated_around_pivot(rotation).translated(translation)
        candidate = MeshEntity3D.from_dict(candidate.to_dict())
        plan, checks, failure = self._terminal_geometry(meshes, candidate, reference, state['fingerprint'])
        result['spatial_index'] = self._query_summary(plan)
        if failure is not None:
            return self._block(result, 'candidate_collision' if failure[0] == 'collision'
                else 'candidate_geometry_unknown', failure[1])
        state["pending"] = {"revision": state["scene"]["revision"],
                            "fingerprint": state["fingerprint"], "observation_id": event["observation_id"],
                            "focal_id": focal.object_id, "reference_id": reference.object_id,
                            "candidate": candidate.to_dict(), "action": copy.deepcopy(action)}
        result.update(route="engine", reason_codes=["candidate_endpoint_clear"],
                      allow_action=True, observation_id=event["observation_id"],
                      measurement_valid=True, axes_valid=bool(pre.axes_valid),
                      rigid_frame_valid=True, rigid_frame=rigid_frame,
                      context_text=json.dumps({"human_eye_status": "endpoint_clear", "checks": checks,
                          "scope": "terminal_geometry_only", "host_execution_verified": False,
                          "collision_tolerance_m": COLLISION_TOLERANCE_M,
                          "expected_scene_revision": state["scene"]["revision"],
                          "rigid_frame_valid": True, "rigid_frame": rigid_frame,
                          "legacy_alignment_axes_valid": bool(pre.axes_valid),
                          "legacy_axes_validation_scope": LEGACY_AXES_VALIDATION_SCOPE,
                          "expected_scene_fingerprint": state["fingerprint"]}, ensure_ascii=False))
        return result

    def export_state(self) -> dict:
        """Trusted local persistence only; not a model-writable authorization token."""
        with self._lock:
            return copy.deepcopy({"schema_version": "1.0", "sessions": list(self._sessions.items()),
                                  "scene_memory": self.scene_cache.export_state()})

    def import_state(self, value: dict) -> None:
        """Restore scene snapshots; reject corrupt fingerprints and stale records."""
        if not isinstance(value, dict) or value.get("schema_version") != "1.0":
            raise ValueError("Unsupported router state")
        sessions = value.get("sessions")
        if not isinstance(sessions, list) or len(sessions) > self.max_sessions:
            raise ValueError("Invalid persisted sessions")
        restored = OrderedDict()
        for sid, state in sessions:
            if not isinstance(sid, str) or not sid or sid in restored:
                raise ValueError("Invalid persisted session")
            scene, _, fingerprint = _validated_scene(state["scene"], _annotate_scene=False)
            if fingerprint != state.get("fingerprint"):
                raise ValueError("Persisted scene fingerprint mismatch")
            item = copy.deepcopy(state); item["scene"] = scene
            retry = _attention_retry_state(item.get('attention_retry'), self._clock())
            if retry is None:
                if 'attention_retry' in item:
                    item['observation'] = None
                item.pop('attention_retry', None)
            else:
                item['attention_retry'] = retry
            obs = item.get("observation")
            if obs and (obs.get('contract_revision') != OBSERVATION_CONTRACT_REVISION
                        or obs.get("fingerprint") != fingerprint or not
                        0 <= self._clock() - obs["created"] <= self.observation_ttl_s):
                item["observation"] = None
            raw_refill = item.get('refill_retry')
            # The most recent observation may be text-only, which must not
            # reset a visual recovery episode. Bind the record to the actual
            # image request key when that request arrives, before any reuse.
            refill = _refill_retry_state(raw_refill, self._clock(),
                key=raw_refill.get('key') if type(raw_refill) is dict else None)
            if refill is None:
                if 'refill_retry' in item:
                    item['observation'] = None
                item.pop('refill_retry', None)
            else:
                item['refill_retry'] = refill
            restored[sid] = item
        with self._lock:
            self._sessions = restored
            # Historical snapshots are optional observation aids. Corrupt cache
            # data is discarded without altering pending execution authority.
            try:
                if 'scene_memory' in value and self.scene_cache.export_state() != value['scene_memory']:
                    self.scene_cache.import_state(value['scene_memory'], preserve_measurements=True)
            except (ValueError, TypeError, KeyError, OverflowError):
                self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
