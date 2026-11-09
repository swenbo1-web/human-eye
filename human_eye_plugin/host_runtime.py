"""Enforce automatic perception and checked execution against a real host.

The host is the only scene authority. This boundary must run in the host's
execution path; it does not intercept unrelated Python/shell tools.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import nullcontext
import copy
import json
import math
import threading
import uuid
from typing import Any, Protocol

import numpy as np

from .agent_adapters import AgentRuntimeAdapter
from .auto_router import (HumanEyeAutoRouter, _validated_scene, _vector,
                          _trace_span, _trace_stage, _trace_annotate)
from .task_verification import evaluate_spatial_goal, _goal as _normalize_goal
from .task_intent import classify_task_intent
from .result_contract import scoped_result
from .query_policy import validate_query
from .auto_router import _ValidatedObservation
from .blender_host import PREWRITE_REFUSAL_PROTOCOL, validate_prewrite_refusal
from .forward_deadline import (PROTOCOL as FORWARD_DEADLINE_PROTOCOL,
                               bind_deadline, validate_refusal as validate_deadline_refusal)


def _bound_goal(goal, focal_id, reference_id):
    """Validate caller-supplied targets before any mutation, binding exact IDs."""
    if goal is None:
        return None
    if not isinstance(goal, dict):
        raise ValueError("goal must be a spatial goal object")
    value = copy.deepcopy(goal)
    for key, identity in (("focal_id", focal_id), ("reference_id", reference_id)):
        if key in value and value[key] != identity:
            raise ValueError("Goal identity differs from the selected " + key)
        value[key] = identity
    return _normalize_goal(value)


def _goal_fields(scene, goal, *, _observation=None):
    if goal is None:
        return {}
    try:
        with _trace_span("goal.evaluate"):
            verified = (evaluate_spatial_goal(scene, goal) if _observation is None else
                evaluate_spatial_goal(scene, goal, _observation=_observation))
    except Exception as exc:
        # Actual action/readback verification has already succeeded. A failed
        # optional evaluator must not turn it into an uncertain/retryable write.
        verified = {"status": "evaluation_failed", "task_succeeded": False,
                    "measurement_valid": False, "reason_codes": ["goal_evaluator_failed"],
                    "error_type": type(exc).__name__, "goal": copy.deepcopy(goal)}
    verified["goal_source"] = "caller_supplied_not_verified_user_intent"
    return {"goal_evaluation": verified["status"], "task_succeeded": verified["task_succeeded"],
            "goal_verification": verified}


def _capability_rejection(scene):
    """Retain the host's object-specific reasons at an execution refusal."""
    capability = copy.deepcopy(scene.get("host_execution"))
    reasons = ["host_execution_capability_required"]
    if isinstance(capability, dict) and capability.get("supported") is False:
        reasons.append("host_execution_unsupported")
        for item in capability.get("reasons", []):
            reason = item.get("reason") if isinstance(item, dict) else None
            if isinstance(reason, str) and reason and reason not in reasons:
                reasons.append(reason)
    return {"reason_codes": reasons, "host_execution": capability}


class SceneHost(Protocol):
    def capture_scene(self) -> dict: ...
    def apply_transform(self, action: dict, expected_revision: str,
                        expected_fingerprint: str | None = None) -> dict: ...


class GuardedHostRuntime:
    """One runtime per host connection, shared by all agent sessions.

    ``before_model`` captures the host before routing and building messages.
    ``execute_action`` always gates and independently recaptures the host.
    An uncertain or unexpected mutation quarantines the whole connection.
    ``reconcile_after_host_review`` is an administrative host operation, not
    an agent tool: it accepts a fresh snapshot after an operator reviews it.
    """

    def __init__(self, host: SceneHost, *, quad_size: int = 128,
                 readback_atol_m: float = 1e-6, max_sessions: int = 32,
                 require_execution_capability: bool = False):
        if type(require_execution_capability) is not bool:
            raise ValueError('require_execution_capability must be boolean')
        if not callable(getattr(host, "capture_scene", None)) or not callable(
                getattr(host, "apply_transform", None)):
            raise TypeError("Host must implement capture_scene and apply_transform")
        self.host = host
        self.require_execution_capability = require_execution_capability
        self._router_options = {"quad_size": quad_size, "readback_atol_m": readback_atol_m,
                                "max_sessions": max_sessions}
        self.router = HumanEyeAutoRouter(**self._router_options)
        self._sessions: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.RLock()
        self._quarantine: dict | None = None
        self._last_verified_scene = None
        self._last_verified_observation = None
        self._last_actual_translation_m = None

    def _transaction(self):
        transaction = getattr(self.host, "transaction", None)
        return transaction() if callable(transaction) else nullcontext()

    @property
    def status(self) -> dict:
        with self._lock:
            return {"quarantined": self._quarantine is not None,
                    "reason": copy.deepcopy(self._quarantine),
                    "sessions": len(self._sessions),
                    "execution_scope": "terminal_geometry_only",
                    "readback_comparison_tolerance_m": self.router.readback_atol_m}

    def _quarantine_host(self, reason: str, revision: str | None) -> None:
        self._quarantine = {"reason": reason, "last_checked_revision": revision}
        self._sessions.clear()

    @staticmethod
    def _result(status, *, executed=False, verified=False, routing=None, operation="transform", **fields):
        _trace_annotate(status=status, verified=verified, execution_verified=verified,
                        goal_evaluation=fields.get("goal_evaluation", "not_requested"),
                        task_succeeded=fields.get("task_succeeded"))
        return scoped_result({"status": status, "executed": executed, "verified": verified,
                "execution_verified": verified, "goal_evaluation": "not_requested", "task_succeeded": None,
                "execution_scope": "terminal_geometry_only", "routing": routing, **fields}, operation=operation)

    @_trace_stage("host.before_model", kind="host", source_name="host_blender")
    def before_model(self, *, session_id: str, task_instruction: str,
                     focal_id: str, reference_id: str, messages: list,
                     format: str = "openai_responses", supports_images: bool = True,
                     task_kind: str | None = "spatial_3d", yaw_symmetry_order: int = 2,
                     include_image: bool = True, final_include_image: bool | None = None,
                     query: dict | None = None) -> dict:
        if not isinstance(task_instruction, str):
            raise TypeError("task_instruction must be a string")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id required")
        query = validate_query(query)
        if type(include_image) is not bool or final_include_image is not None and type(final_include_image) is not bool:
            raise ValueError("Image delivery options must be boolean")
        native = classify_task_intent(task_instruction, task_kind=task_kind)['kind'] != 'spatial_3d'
        with self._lock, (nullcontext() if native else self._transaction()):
            if self._quarantine and not native:
                raise RuntimeError("Host is quarantined; an operator must review and reconcile the host state")
            scene = None
            if not native:
                try:
                    with _trace_span("host.capture", kind="host", source_name="host_blender"):
                        scene = self.host.capture_scene()
                except Exception:
                    self._quarantine_host("host_snapshot_unavailable", None)
                    raise
            return self._before_model_on_captured_scene(scene=scene, session_id=session_id,
                task_instruction=task_instruction, focal_id=focal_id, reference_id=reference_id,
                messages=messages, format=format, supports_images=supports_images,
                task_kind=task_kind, yaw_symmetry_order=yaw_symmetry_order, include_image=include_image,
                final_include_image=final_include_image, query=query)

    def _before_model_on_captured_scene(self, *, scene: dict | None, session_id: str,
            task_instruction: str, focal_id: str, reference_id: str, messages: list,
            format: str = "mcp", supports_images: bool = True,
            task_kind: str = "spatial_3d", yaw_symmetry_order: int = 2,
            include_image: bool = True, final_include_image: bool | None = None,
            query: dict | None = None, _validated_observation=None) -> dict:
        """Reuse a trusted service capture for observation, never for execution.

        This private boundary is for the host service that has just captured the
        scene. It is not an agent input. execute_action still independently
        captures, checks and compares the Blender revision at the write boundary.
        """
        if not isinstance(task_instruction, str):
            raise TypeError("task_instruction must be a string")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id required")
        query = validate_query(query)
        if type(include_image) is not bool or final_include_image is not None and type(final_include_image) is not bool:
            raise ValueError("Image delivery options must be boolean")
        event = {"event": "before_model", "session_id": session_id,
                 "task_instruction": task_instruction, "task_kind": task_kind,
                 "focal_id": focal_id, "reference_id": reference_id,
                 "yaw_symmetry_order": yaw_symmetry_order, "include_image": include_image,
                 "query": query}
        if _validated_observation is not None:
            if (type(_validated_observation) is not _ValidatedObservation
                    or scene is not _validated_observation.scene):
                raise ValueError('Validated observation must own this exact fresh scene')
            route_event = lambda event: self.router._handle_validated_observation(
                event, _validated_observation)
        else:
            route_event = self.router
        if scene is not None and _validated_observation is None:
            event["scene"] = scene
        adapter = AgentRuntimeAdapter(route_event, format, supports_images)
        with self._lock:
            self._sessions.pop(session_id, None)
            if (self._quarantine and
                    classify_task_intent(task_instruction, task_kind=task_kind)['kind'] == 'spatial_3d'):
                raise RuntimeError("Host is quarantined; an operator must review and reconcile the host state")
            with _trace_span("host.prepare_agent_delivery", source_name="protocol_serialize"):
                prepared = adapter.before_model(event, messages)
            if scene is not None:
                prepared["host_execution"] = copy.deepcopy(scene.get("host_execution"))
            route = prepared["routing"]
            if (route["route"] == "engine" and not route["requires_reobserve"]
                    and route.get("observation_status") != "partial"
                    and route["measurement_valid"] and route.get("rigid_frame_valid") is True):
                self._sessions[session_id] = {"focal_id": focal_id, "reference_id": reference_id,
                    "task_instruction": task_instruction, "yaw_symmetry_order": yaw_symmetry_order,
                    "include_image": include_image if final_include_image is None else final_include_image,
                    "observation_id": route["observation_id"]}
                while len(self._sessions) > self.router.max_sessions:
                    self._sessions.popitem(last=False)
            return prepared

    @_trace_stage("host.execute_action", kind="host", source_name="host_blender")
    def execute_action(self, *, session_id: str, action: dict,
                       observation_id: str | None = None, goal: dict | None = None,
                       _before_commit=None, _host_deadline=None, _commit_guard=None) -> dict:
        """Accept structured SE(3) only; callers cannot supply a scene or source."""
        action = copy.deepcopy(action)
        with self._lock, self._transaction():
            self._last_verified_scene = None
            self._last_verified_observation = None
            self._last_actual_translation_m = None
            if self._quarantine:
                return self._result("host_quarantined", reason=copy.deepcopy(self._quarantine))
            saved = self._sessions.get(session_id)
            if not saved:
                return self._result("observation_required")
            try:
                goal = _bound_goal(goal, saved["focal_id"], saved["reference_id"])
            except ValueError as exc:
                return self._result("invalid_goal", error=str(exc), goal_evaluation="invalid_goal")
            try:
                with _trace_span("host.capture_before_action", kind="host", source_name="host_blender"):
                    raw_scene = self.host.capture_scene()
                observation = _ValidatedObservation(raw_scene)
                scene = observation.scene
            except Exception as exc:
                self._quarantine_host("host_snapshot_unavailable", None)
                return self._result("host_snapshot_unavailable", error_type=type(exc).__name__)
            revision = scene["revision"]
            supported = scene.get('host_execution', {}).get('supported')
            if supported is False or self.require_execution_capability and supported is not True:
                self._sessions.pop(session_id, None)
                return self._result('blocked', **_capability_rejection(scene),
                                    allow_action=False)
            # A true no-op has no side effects and needs no changed host revision.
            # Validate IDs and permitted fields before reporting it as such.
            allowed = {"focal_id", "reference_id", "translation", "rotation_euler_deg"}
            try:
                if (not isinstance(action, dict) or set(action) - allowed
                        or not {"translation", "rotation_euler_deg"} & set(action)):
                    raise ValueError("Unsupported action")
                for field in ("focal_id", "reference_id"):
                    if field in action and action[field] != saved[field]:
                        raise ValueError("Action object differs from observation")
                translation = _vector(action.get("translation", [0, 0, 0]))
                euler = _vector(action.get("rotation_euler_deg", [0, 0, 0]))
            except (ValueError, TypeError):
                return self._result("invalid_action")
            is_noop = not np.any(translation) and not np.any(euler)
            with _trace_span("host.execution_gate"):
                check = self.router._handle_validated_action({
                    "event": "before_action", "session_id": session_id,
                    "observation_id": observation_id or saved["observation_id"],
                    "focal_id": saved["focal_id"], "reference_id": saved["reference_id"],
                    "yaw_symmetry_order": saved["yaw_symmetry_order"], "action": action}, observation._fork())
            if check["allow_action"] is not True:
                self._sessions.pop(session_id, None)
                return self._result("blocked", routing=check)
            if _before_commit is not None and _before_commit() is not True:
                self._sessions.clear()
                self.router = HumanEyeAutoRouter(**self._router_options)
                return self._result('blocked', routing=check, allow_action=False,
                    reason_codes=['segment_time_budget_exhausted_before_commit'])
            if _commit_guard is not None:
                try:reason=_commit_guard()
                except Exception:reason='registered_commit_guard_unavailable'
                if reason is not None:
                    if type(reason) is not str or not reason or len(reason)>256:reason='registered_commit_guard_unavailable'
                    self.router=HumanEyeAutoRouter(**self._router_options);self._sessions.clear()
                    return self._result('blocked',routing=check,allow_action=False,reason_codes=[reason])
            # Route and host use the same fully validated object IDs.
            action.update(focal_id=saved["focal_id"], reference_id=saved["reference_id"])
            if is_noop:
                self._sessions.pop(session_id, None)
                # Discard the router's pending no-op without claiming a host
                # change or fabricating a revision. Old observations are gone.
                self.router = HumanEyeAutoRouter(**self._router_options)
                self._sessions.clear()
                self._last_verified_scene = scene
                self._last_verified_observation = observation
                self._last_actual_translation_m = 0.
                return self._result("no_op", routing=check,
                    **_goal_fields(scene, goal, _observation=observation))
            self._sessions.clear()  # Another session cannot reuse this pre-state.
            request_nonce = None
            host_arguments = {"expected_revision": revision,
                              "expected_fingerprint": check["scene_fingerprint"]}
            if getattr(self.host, "prewrite_refusal_protocol", None) == PREWRITE_REFUSAL_PROTOCOL:
                request_nonce = uuid.uuid4().hex
                host_arguments["request_nonce"] = request_nonce
            try:
                bound_deadline = None
                if _host_deadline is not None:
                    if (getattr(self.host, 'forward_deadline_protocol', None) != FORWARD_DEADLINE_PROTOCOL
                            or request_nonce is None):
                        raise ValueError('Host has not negotiated forward deadline support')
                    bound_deadline = bind_deadline(_host_deadline, action=action,
                        expected_revision=revision, expected_fingerprint=check['scene_fingerprint'],
                        request_nonce=request_nonce)
                    host_arguments['forward_deadline'] = bound_deadline
                _trace_annotate(mutation_started=True)
                with _trace_span("host.mutation", kind="host", source_name="host_blender"):
                    host_result = self.host.apply_transform(action, **host_arguments)
                if isinstance(host_result, dict) and (
                        host_result.get("status") == "rejected_before_mutation" or "rejection" in host_result):
                    deadline_refusal = (bound_deadline is not None and
                        host_result.get('rejection', {}).get('protocol') == FORWARD_DEADLINE_PROTOCOL)
                    if deadline_refusal:
                        refusal = validate_deadline_refusal(host_result, forward_deadline=bound_deadline,
                            action=action, expected_revision=revision,
                            expected_fingerprint=check['scene_fingerprint'], request_nonce=request_nonce)
                    else:
                        refusal = validate_prewrite_refusal(host_result, action=action,
                            expected_revision=revision, expected_fingerprint=check["scene_fingerprint"],
                            request_nonce=request_nonce)
                        captured_focal = next(mesh for mesh in scene["meshes"]
                                              if mesh["object_id"] == saved["focal_id"])
                        if refusal["precision"]["before_pivot_world_m"] != captured_focal["pivot_world"]:
                            raise ValueError("Prewrite precision proof differs from the captured focal pivot")
                    _trace_annotate(mutation_started=False, mutation_completed=False,
                                    host_prewrite_refused=True)
                    # A refused candidate consumes its observation, including
                    # the router's pending action, without inventing a revision.
                    self.router = HumanEyeAutoRouter(**self._router_options)
                    self._sessions.clear()
                    return self._result("blocked", routing=check, allow_action=False,
                        reason_codes=[refusal["code"]], host_mutation_started=False,
                        host_prewrite_refusal=refusal, requires_reobserve=True,
                        **({'forward_deadline':bound_deadline} if deadline_refusal else {}))
                _trace_annotate(mutation_completed=True)
            except Exception as exc:
                self._quarantine_host("host_execution_uncertain", revision)
                return self._result("host_execution_uncertain", executed=None,
                                    routing=check, error_type=type(exc).__name__)
            try:
                with _trace_span("host.readback_capture", kind="host", source_name="host_blender"):
                    from .blender_process import BlenderProcessHost
                    raw_actual = (self.host._readback_after_apply(host_result)
                        if isinstance(self.host, BlenderProcessHost) else self.host.capture_scene())
                actual_observation = _ValidatedObservation(raw_actual)
                actual = actual_observation.scene
                # A one-object transform cannot quietly move/delete/create
                # another mesh or change its metadata.
                before_other = {m["object_id"]: m for m in scene["meshes"]
                                if m["object_id"] != saved["focal_id"]}
                after_other = {m["object_id"]: m for m in actual["meshes"]
                               if m["object_id"] != saved["focal_id"]}
                if (before_other != after_other or scene["source"] != actual["source"]
                        or scene.get('host_identity') != actual.get('host_identity')):
                    raise ValueError("Unexpected change outside the focal object")
                before_focal = next(m for m in scene["meshes"] if m["object_id"] == saved["focal_id"])
                after_focal = next(m for m in actual["meshes"] if m["object_id"] == saved["focal_id"])
                for key in set(before_focal) - {"vertices", "local_axes", "pivot_world"}:
                    if before_focal[key] != after_focal[key]:
                        raise ValueError("Unexpected focal metadata change: " + key)
                with _trace_span("host.readback_verify"):
                    post = self.router._handle_validated_action({"event": "after_action", "session_id": session_id,
                        "focal_id": saved["focal_id"],
                        "reference_id": saved["reference_id"], "yaw_symmetry_order": saved["yaw_symmetry_order"],
                        "task_instruction": saved["task_instruction"], "include_image": saved.get("include_image", True)},
                        actual_observation._fork())
                if (post["route"] != "engine" or post["requires_reobserve"]
                        or not post["measurement_valid"] or post.get("rigid_frame_valid") is not True):
                    self._quarantine_host("host_readback_rejected", revision)
                    return self._result("host_readback_rejected", executed=None, routing=post,
                                        host_call_completed=True)
            except Exception as exc:
                self._quarantine_host("host_readback_uncertain", revision)
                return self._result("host_readback_uncertain", executed=None,
                                    routing=check, error_type=type(exc).__name__, host_call_completed=True)
            self._last_verified_scene = actual
            self._last_verified_observation = actual_observation
            self._last_actual_translation_m = math.dist(
                next(mesh.pivot_world for mesh in observation.meshes if mesh.object_id == saved['focal_id']),
                next(mesh.pivot_world for mesh in actual_observation.meshes if mesh.object_id == saved['focal_id']))
            receipt = host_result.get("receipt") if isinstance(host_result, dict) else None
            return self._result("verified", executed=True, verified=True, routing=post,
                                receipt=copy.deepcopy(receipt),
                                actual_scene_revision=actual["revision"],
                                **_goal_fields(actual, goal, _observation=actual_observation))

    @_trace_stage("host.preview_action", kind="host", source_name="host_blender")
    def preview_action(self, *, session_id: str, action: dict) -> dict:
        """Inspect a fresh candidate without consuming authority or executing it.

        Execution must still call execute_action, which performs a new check.
        A preview is deliberately not an authorization token.
        """
        with self._lock, self._transaction():
            if self._quarantine:
                return self._result("host_quarantined", allow_action=False, operation="preview")
            saved = self._sessions.get(session_id)
            if not saved:
                return self._result("observation_required", allow_action=False, operation="preview")
            with _trace_span("host.capture_preview", kind="host", source_name="host_blender"):
                raw_scene = self.host.capture_scene()
            scene, _, _ = _validated_scene(raw_scene)
            return self._preview_on_captured_scene(scene, session_id, action)

    def _preview_on_captured_scene(self, scene, session_id, action):
        """Internal read-only preview under the runtime lock and host transaction."""
        saved = self._sessions.get(session_id)
        if not saved:
            return self._result("observation_required", allow_action=False, operation="preview")
        supported = scene.get('host_execution', {}).get('supported')
        if supported is False or self.require_execution_capability and supported is not True:
            return self._result('blocked', allow_action=False,
                                operation="preview", **_capability_rejection(scene))
        probe_router = HumanEyeAutoRouter(**self._router_options)
        probe_router.import_state(self.router.export_state())
        with _trace_span("host.preview_gate"):
            result = probe_router.handle_event({"event": "before_action", "session_id": session_id,
                "scene": scene, "action": copy.deepcopy(action),
                "observation_id": saved["observation_id"], "focal_id": saved["focal_id"],
                "reference_id": saved["reference_id"], "yaw_symmetry_order": saved["yaw_symmetry_order"]})
        return self._result("preview", routing=result, allow_action=result["allow_action"] is True,
                            preview_only=True, operation="preview")

    def _prepare_and_preview(self, *, session_id, action, include_image=False):
        """Share one trusted capture for preparation and non-authorizing preview.

        Execute_action independently captures again and retains its inner gate.
        A caller cannot submit this scene through the MCP action protocol.
        """
        with self._lock, self._transaction():
            if self._quarantine:
                return self._result("host_quarantined", allow_action=False, operation="preview")
            with _trace_span("host.capture_preview", kind="host", source_name="host_blender"):
                scene, _, _ = _validated_scene(self.host.capture_scene())
            prepared = self._before_model_on_captured_scene(scene=scene, session_id=session_id,
                task_instruction="Automatic observation before structured rigid transform.",
                focal_id=action['focal_id'], reference_id=action['reference_id'], messages=[],
                format='mcp', include_image=False, supports_images=False, final_include_image=include_image)
            route = prepared['routing']
            capability = prepared.get('host_execution')
            if isinstance(capability, dict) and capability.get('supported') is False:
                return self._result('blocked', routing=route, allow_action=False, operation='preview',
                                    **_capability_rejection(scene))
            if route.get('observation_status') == 'partial':
                return self._result('blocked', routing=route, allow_action=False, operation='preview',
                                    reason_codes=['partial_observation_not_actionable'])
            if (route.get('route') != 'engine' or route.get('requires_reobserve') is True
                    or route.get('measurement_valid') is not True
                    or route.get('rigid_frame_valid') is not True):
                reasons = list(route.get('reason_codes') or [])
                frame_failure = route.get('route') == 'engine' and route.get('rigid_frame_valid') is False
                code = 'unverified_geometry_or_frame' if frame_failure else 'observation_not_actionable'
                if code not in reasons:
                    reasons.append(code)
                fields = {'reason_codes': reasons}
                if 'geometry_work_budget' in route:
                    fields['geometry_work_budget'] = copy.deepcopy(route['geometry_work_budget'])
                if 'rigid_frame' in route:
                    fields['rigid_frame'] = copy.deepcopy(route['rigid_frame'])
                    fields['rigid_frame_valid'] = route.get('rigid_frame_valid')
                return self._result('blocked', routing=route, allow_action=False,
                                    operation='preview', **fields)
            if session_id not in self._sessions:
                return self._result('observation_required', routing=route, allow_action=False, operation='preview')
            return self._preview_on_captured_scene(scene, session_id, action)

    def _discard_prepared_session(self, session_id: str) -> None:
        """Invalidate a task's action context without restoring trusted geometry."""
        with self._lock:
            self.router._cleanup_observations()
            self._sessions.pop(session_id, None)

    def export_state(self) -> dict:
        """Persist only to host-owned local storage, never model input."""
        with self._lock:
            return {"schema_version": "1.0", "router": self.router.export_state(),
                    "sessions": copy.deepcopy(list(self._sessions.items())),
                    "quarantine": copy.deepcopy(self._quarantine)}

    def import_state(self, value: dict) -> None:
        """Restore trusted state without clearing a prior host quarantine."""
        if (not isinstance(value, dict) or value.get("schema_version") != "1.0"
                or not {"router", "sessions", "quarantine"}.issubset(value)):
            raise ValueError("Unsupported host runtime state")
        sessions = value.get("sessions")
        if not isinstance(sessions, list) or len(sessions) > self.router.max_sessions:
            raise ValueError("Invalid host sessions")
        restored = OrderedDict()
        for sid, saved in sessions:
            if not isinstance(sid, str) or not sid or sid in restored or not isinstance(saved, dict):
                raise ValueError("Invalid host session")
            if any(not isinstance(saved.get(k), str) or not saved[k] for k in
                   ("focal_id", "reference_id", "observation_id")):
                raise ValueError("Incomplete host observation")
            restored[sid] = copy.deepcopy(saved)
        quarantine = value.get("quarantine")
        if quarantine is not None:
            if (not isinstance(quarantine, dict) or not isinstance(quarantine.get("reason"), str)
                    or not quarantine["reason"] or "last_checked_revision" not in quarantine
                    or quarantine["last_checked_revision"] is not None and
                    not isinstance(quarantine["last_checked_revision"], str)):
                raise ValueError("Invalid host quarantine")
        router = HumanEyeAutoRouter(**self._router_options)
        router.scene_cache = self.router.scene_cache
        router.import_state(value["router"])
        with self._lock:
            self.router = router
            self._sessions = restored
            self._quarantine = copy.deepcopy(self._quarantine or quarantine)

    def reconcile_after_host_review(self) -> dict:
        """Administrative acknowledgment; does not certify the preceding action.

        Do not expose this method as a model tool or call it on automatic retry.
        The operator must first inspect the host and resolve uncertain changes.
        """
        with self._lock, self._transaction():
            scene, _, fingerprint = _validated_scene(self.host.capture_scene())
            if self._quarantine and scene["revision"] == self._quarantine["last_checked_revision"]:
                raise ValueError("A fresh host snapshot revision is required")
            self.router = HumanEyeAutoRouter(**self._router_options)
            self._sessions.clear()
            self._quarantine = None
            return {"reconciled": True, "scene_revision": scene["revision"],
                    "scene_fingerprint": fingerprint, "previous_action_verified": False,
                    "requires_new_observation": True}


__all__ = ["SceneHost", "GuardedHostRuntime"]
