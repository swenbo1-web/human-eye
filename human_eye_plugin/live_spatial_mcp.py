"""MCP transport for the live, guarded Blender service.

This entry point deliberately exposes a separate set of tools from the legacy
demo server. It requires a trusted local configuration and never loads a demo
scene or executes arbitrary host code supplied by a model.
"""
from __future__ import annotations

import argparse
import base64
import copy
from contextlib import contextmanager, nullcontext
from functools import partial
import json
import math
import sys
import time
import uuid
from typing import Any, TextIO

from .runtime_identity import BASE_VERSION, MCP_PROTOCOL_VERSION, runtime_identity
from .auto_router import _trace_span, _trace_annotate as annotate
from .query_policy import MAX_VISUAL_LABEL_IDS, NATIVE_VISUAL_SCHEMA, validate_query
from .task_query import FACTS as TASK_FACTS, SELECTOR_SCHEMA
from .native_observation import _public_native_png
from .support_plane_discovery import SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA
from .telemetry import set_image_request, record_image_artifact
from .goal_segment import CLEARANCE_SEGMENT_REQUEST_SCHEMA, validate_clearance_segment_request
from .request_context import (TASK_CONTEXT_SCHEMA, SCENE_DELTA_REQUEST_SCHEMA,
                              validate_task_context, validate_scene_delta_request, bind_task_context)
from .telemetry import current_trace
from . import mcp_transport as wire
from .hook_context import (_observation as _parse_observation,
                           _deduplicate, _contains_reference_key)
from .task_brief import project_task_brief, project_segment_brief, project_structure_brief

span = partial(_trace_span, source_name='mcp_transport')
_NO_RPC_ID = object()


_ID_SCHEMA = {"type": "string", "minLength": 1}
_VECTOR_SCHEMA = {
    "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
}
_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "focal_id": copy.deepcopy(_ID_SCHEMA),
        "reference_id": copy.deepcopy(_ID_SCHEMA),
        "translation": copy.deepcopy(_VECTOR_SCHEMA),
        "rotation_euler_deg": copy.deepcopy(_VECTOR_SCHEMA),
    },
    "required": ["focal_id", "reference_id"],
    "anyOf": [{"required": ["translation"]}, {"required": ["rotation_euler_deg"]}],
    "additionalProperties": False,
}
_QUERY_SCHEMA = {
    "type": "object",
    "description": "Selectors use name OR id. Legacy exact_pairs/nearest/top1 use object_ids/max_exact_pairs. nearest needs complete exact nonpenetrating order; top1 may prune by strict outward bounds and reports ties. Unknown/budget-limited proofs do not certify nearest.",
    "properties": {
        "mode": {"type": "string", "enum": ["task", "surface_nearest", "overview", "exact_pairs", "nearest", "top1", "mesh_structure", "mesh_surface"]},
        "objects": {"type": "array", "items": SELECTOR_SCHEMA, "minItems": 1, "maxItems": 4,
            "description": "Legacy task: aabb 1..4 selectors; pair facts two ordered A to B."},
        "target": copy.deepcopy(SELECTOR_SCHEMA),
        "candidates": {"type": "array", "items": copy.deepcopy(SELECTOR_SCHEMA), "minItems": 1, "maxItems": 3,
            "description": "1..3 explicit candidates in request order; one capture with target. Requires closed_solid_relation and surface_proximity; aabb optional."},
        "requested_facts": {"type": "array", "items": {"type": "string", "enum": list(TASK_FACTS)},
            "minItems": 1, "uniqueItems": True,
            "description": "task: closed_solid_relation is zero-tolerance separated/touching/penetrating (positive-volume overlap, including containment) for represented connected closed triangle shells; invalid/ambiguous is unknown. surface_proximity independently gives nonnegative triangle-surface distance, original world witness points and positive-distance A-to-B direction; zero-distance direction is inapplicable. Boundary/nonmanifold counts do not certify solids. Penetrating/contained distances are not separated gaps. pair_relation's escape of A is not surface distance, nearest direction or minimum depth."},
        "operation": {"type":"string","enum":["diagnose","patch","reference","restore_preview","reference_patch"],
            "description":"Registered target reads. mesh_structure: diagnose text or patch images. mesh_surface (local opt-in): diagnose/reference/restore_preview require include_image=false; reference_patch uses a returned opaque patch_ref and optional native images. References are locally trusted; previews do not execute; the original task budget applies."},
        "request_id": {"type":"string","minLength":1,"maxLength":128},
        "near_m": {"type":"number","minimum":0,"maximum":0.001},
        "threshold_m": {"type":"number","exclusiveMinimum":0,"maximum":0.01},
        "reference_ref": {"type":"string","pattern":"^[a-f0-9]{32}$"},
        "indices": {"type":"array","items":{"type":"integer","minimum":0,"maximum":4095},"minItems":1,"maxItems":64,"uniqueItems":True},
        "patch_ref": {"type":"string","pattern":"^[a-f0-9]{32}$"},
        "task_ref": {"type":"string","pattern":"^[a-f0-9]{32}$",
            "description":"Trusted begin handoff, required in local lifecycle mode; selects the active generation without creating or renewing a task."},
        "object_ids": {"type": "array", "items": copy.deepcopy(_ID_SCHEMA), "minItems": 1, "maxItems": 255, "uniqueItems": True},
        "label_object_ids": {"type": "array", "items": copy.deepcopy(_ID_SCHEMA), "minItems": 1, "maxItems": MAX_VISUAL_LABEL_IDS, "uniqueItems": True,
            "description": "Current full IDs for image annotation, separate from measurement object_ids: up to six related labels plus A/B. Missing pair/image, occlusion or undersampling is explicit; display only."},
        "max_exact_pairs": {"type": "integer", "minimum": 1, "maximum": 255},
        "alignment_evidence": {"type": "boolean", "default": True,
            "description": "False omits optional face angles and requires include_image=false; strict distance, host rigid-frame and action checks remain."},
        "support_plane_discovery": copy.deepcopy(SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA),
        "native_visual": copy.deepcopy(NATIVE_VISUAL_SCHEMA),
        "visual_diagnostic": {"type": "string", "enum": ["contact_section"],
            "description": "Analytical full-mesh contact section beside natural views; not visibility evidence or action permission."},
    },
    "allOf": [{"if": {"properties": {"mode": {"const": "surface_nearest"}}, "required": ["mode"]},
               "then": {"properties": {"mode": {}, "objects": {"maxItems": 1}}, "additionalProperties": False}},
              {"if": {"anyOf": [{"properties": {"mode": {"const": "task"}}, "required": ["mode"]},
                                  {"required": ["target"]}, {"required": ["candidates"]}]},
               "then": {"required": ["mode", "requested_facts"], "properties": {"mode": {"const": "task"}}, "oneOf": [
                   {"required": ["objects"], "properties": {"target": False, "candidates": False}},
                   {"required": ["target", "candidates"],
                    "additionalProperties": False,
                    "properties": {"mode": {}, "target": {}, "candidates": {}, "requested_facts": {"items": {"enum": ["closed_solid_relation", "surface_proximity", "aabb"]},
                        "allOf": [{"contains": {"const": "closed_solid_relation"}}, {"contains": {"const": "surface_proximity"}}]}}}
               ]}}],
    "additionalProperties": False,
}
_GOAL_SCHEMA = {
    "type": "object",
    "description": (
        "Optional caller-supplied task criteria, evaluated separately from execution. "
        "Omitted object IDs bind to the selected observation/action pair. "
        "These criteria are not independently verified as the human user's intent."
    ),
    "properties": {
        "focal_id": copy.deepcopy(_ID_SCHEMA),
        "reference_id": copy.deepcopy(_ID_SCHEMA),
        "target_clearance_m": {"type": "number", "minimum": 0},
        "clearance_tolerance_m": {"type": "number", "minimum": 0},
        "target_focal_pivot_world_m": copy.deepcopy(_VECTOR_SCHEMA),
        "position_tolerance_m": {"type": "number", "minimum": 0},
        "max_contact_normal_angle_deg": {"type": "number", "minimum": 0, "maximum": 180},
        "max_tangent_yaw_mismatch_deg": {"type": "number", "minimum": 0, "maximum": 180},
        "yaw_symmetry_order": {"type": "integer", "enum": [1, 2, 4]},
    },
    "anyOf": [
        {"required": [field]} for field in (
            "target_clearance_m", "target_focal_pivot_world_m",
            "max_contact_normal_angle_deg", "max_tangent_yaw_mismatch_deg")
    ],
    "dependentRequired": {
        "target_clearance_m": ["clearance_tolerance_m"],
        "clearance_tolerance_m": ["target_clearance_m"],
        "target_focal_pivot_world_m": ["position_tolerance_m"],
        "position_tolerance_m": ["target_focal_pivot_world_m"],
    },
    "additionalProperties": False,
}

LIVE_MCP_TOOLS_SCHEMA = [
    {
        "name": "human_eye_scene_observe",
        "description": (
            "Current Blender facts. Task set example: "
            "{\"include_image\":false,\"query\":{\"mode\":\"task\",\"target\":{\"name\":\"A\"},\"candidates\":[{\"name\":\"B\"}],\"requested_facts\":[\"closed_solid_relation\",\"surface_proximity\"]}}. "
            "Unknown/duplicate rows remain. Complete penetration/nearest-separated sets require all relevant evidence; otherwise only known subsets are reported. "
            "Legacy objects pair/aabb supported. Global surface_nearest instead uses one query.objects selector without focal_id, "
            "or focal_id with query={\"mode\":\"surface_nearest\"}; session_id and include_image=false required. "
            "Complete means global nearest; partial means best-known. scene_revision/fingerprint bind this capture/source/revision; "
            "runtime_source_sha256 identifies code. Scene edits expire observations. Goals are caller criteria."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_instruction": {"type": "string"},
                "focal_id": copy.deepcopy(_ID_SCHEMA),
                "reference_id": copy.deepcopy(_ID_SCHEMA),
                "session_id": copy.deepcopy(_ID_SCHEMA),
                "goal": copy.deepcopy(_GOAL_SCHEMA),
                "query": copy.deepcopy(_QUERY_SCHEMA),
                "include_image": {"type": "boolean", "default": True,
                    "description": "False returns text evidence without rendering. mesh_structure diagnose requires false and reads only the registered target raw mesh; patch may explicitly request images. Other observation modes retain default true."},
            },
            "allOf": [{
                "if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"const": "surface_nearest"}}}}},
                "then": {"required": ["session_id", "include_image"],
                         "properties": {"include_image": {"const": False}},
                         "oneOf": [
                             {"required": ["focal_id"], "properties": {"query": {"not": {"required": ["objects"]}}}},
                             {"not": {"required": ["focal_id"]}, "properties": {"query": {"required": ["objects"]}}},
                         ]},
            }, {"if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"const": "task"}}}}},
                "then": {"required": ["include_image"], "properties": {"include_image": {"const": False}},
                         "not": {"anyOf": [{"required": [field]} for field in
                             ("focal_id", "reference_id", "goal", "scene_delta")]}}}],
            "additionalProperties": False,
        },
    },
    {
        "name": "human_eye_transform",
        "description": (
            "Apply a guarded world-space rigid transform to the focal Blender object "
            "automatically preparing a fresh engine observation before its mandatory check. "
            "Translation is in metres; rotation is XYZ Euler degrees about the object pivot. "
            "The service checks the current revision and endpoint geometry, executes only "
            "accepted actions, and reads the actual scene back. An optional caller-supplied "
            "goal checks the actual result separately from execution verification. "
            "This does not certify a swept path or independently verify the caller's intent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": copy.deepcopy(_ACTION_SCHEMA),
                "session_id": copy.deepcopy(_ID_SCHEMA),
                "goal": copy.deepcopy(_GOAL_SCHEMA),
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "human_eye_connection_status",
        "description": "Read the live service configuration and connection status without changing the scene.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

LIVE_MCP_TOOLS_SCHEMA.append({
    'name': 'human_eye_clearance_segment',
    'description': ('Preview or execute a finite target-clearance segment. Legacy requests use exact '
        'world-axis boxes with an explicit signed world axis. Explicit solver=support_plane requests '
        'select an original reference triangle and a world translation direction; exact finite-plane '
        'certificates restrict their supported convex-mesh domain. Supply object IDs, target and '
        'tolerance; the engine computes translations and may correct confirmed residuals within '
        'the declared budget. execute defaults '
        'to false. Reuse the same request_id to retrieve a historical receipt, never to repeat motion. '
        'Every real step retains fresh geometry/precision checks and actual readback. Endpoint only; '
        'no swept path or in-flight cancellation is certified.'),
    'inputSchema': {'type': 'object', 'additionalProperties': False,
        'properties': {'session_id': copy.deepcopy(_ID_SCHEMA), 'request_id': copy.deepcopy(_ID_SCHEMA),
            'request': copy.deepcopy(CLEARANCE_SEGMENT_REQUEST_SCHEMA),
            'execute': {'type': 'boolean', 'default': False},
            'include_image': {'type': 'boolean', 'default': False}},
        'required': ['request_id', 'request']},
})

LIVE_MCP_TOOLS_SCHEMA.append({
    'name': 'human_eye_arm_twist_observe',
    'description': ('Read an explicitly selected Blender arm patch. Returns synthetic-trained '
        'twist-collapse severity by original vertex section and current source. Diagnostic only: '
        'no repair or execution authority. Supply mesh, a 2..4 bone chain and existing ordered sections.'),
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
    'inputSchema': {'type': 'object', 'additionalProperties': False,
        'properties': {'session_id': copy.deepcopy(_ID_SCHEMA),
            'selection': {'type': 'object', 'additionalProperties': False,
                'properties': {
                    'mesh_name': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                    'armature_name': {'type': 'string', 'minLength': 1, 'maxLength': 256},
                    'bone_names': {'type': 'array', 'minItems': 2, 'maxItems': 4, 'uniqueItems': True,
                        'items': {'type': 'string', 'minLength': 1, 'maxLength': 256}},
                    'vertex_indices': {'type': 'array', 'minItems': 6, 'maxItems': 8192, 'uniqueItems': True,
                        'items': {'type': 'integer', 'minimum': 0}},
                    'sections': {'type': 'array', 'minItems': 2, 'maxItems': 128,
                        'items': {'type': 'array', 'minItems': 3, 'maxItems': 256, 'uniqueItems': True,
                            'items': {'type': 'integer', 'minimum': 0}}}},
                'required': ['mesh_name', 'bone_names', 'sections']}},
        'required': ['selection']}})

for _tool in LIVE_MCP_TOOLS_SCHEMA:
    if _tool['name'] != 'human_eye_connection_status':
        _tool['inputSchema']['properties']['task_context'] = copy.deepcopy(TASK_CONTEXT_SCHEMA)
    if _tool['name'] == 'human_eye_scene_observe':
        _tool['inputSchema']['properties']['scene_delta'] = copy.deepcopy(SCENE_DELTA_REQUEST_SCHEMA)
        _tool['inputSchema']['properties']['response_detail'] = {
            'type': 'string', 'enum': ['full', 'brief'], 'default': 'full',
            'description': ('Optional display projection. Brief preserves measurements, scopes, unknowns and '
                'native image bytes while omitting named camera/raster diagnostics. Full is a new current '
                'observation, not retrieval of a previous observation. Errors and insufficient savings keep full.'),
        }
    if _tool['name'] == 'human_eye_clearance_segment':
        _tool['inputSchema']['properties']['response_detail'] = {
            'type': 'string', 'enum': ['full', 'brief'], 'default': 'full',
            'description': ('Optional endpoint display encoding. Brief preserves all receipt facts, '
                'diagnostics and native PNG bytes using exact references within this same result. '
                'The embedded JSON context is represented by its decoded values, not original string '
                'formatting. Historical, unsupported, conflicting or insufficiently smaller results '
                'retain full. This display option grants no execution authority.'),
        }


SPATIAL_TASK_TOOLS_SCHEMA = [{
    'name': 'human_eye_spatial_relations',
    'description': ('Read current solid relations and surface distances from a target to 1..3 explicit '
        'candidates in one capture. Returns each pair, penetrating candidates and nearest separated ties; '
        'unknowns and incomplete sets stay explicit. Surface distance is not penetration depth. '
        'Read-only: no images or actions.'),
    'inputSchema': {'type': 'object', 'properties': {
        'target': copy.deepcopy(SELECTOR_SCHEMA),
        'candidates': {'type': 'array', 'items': copy.deepcopy(SELECTOR_SCHEMA), 'minItems': 1, 'maxItems': 3},
        'include_aabb': {'type': 'boolean', 'default': False}},
        'required': ['target', 'candidates'], 'additionalProperties': False}}, {
    'name': 'human_eye_surface_nearest',
    'description': ('Find the nearest triangle surfaces, in metres, from one current Blender mesh '
        'to all other meshes in the scene. Complete results give global nearest ties; partial '
        'results give best-known candidates and unresolved coverage. Surface distance is unsigned, '
        'not penetration depth. Read-only: no images or actions. '
        'Example: {"target":{"name":"Bracket"}}.'),
    'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                    'idempotentHint': True, 'openWorldHint': False},
    'inputSchema': {'type': 'object', 'properties': {
        'target': copy.deepcopy(SELECTOR_SCHEMA)},
        'required': ['target'], 'additionalProperties': False}}]


def _spatial_task_query(arguments):
    return {'mode': 'task', 'target': arguments.get('target'), 'candidates': arguments.get('candidates'),
        'requested_facts': ['closed_solid_relation', 'surface_proximity']
            + (['aabb'] if arguments.get('include_aabb', False) else [])}


def _surface_nearest_task_query(arguments):
    return {'mode': 'surface_nearest', 'objects': [arguments.get('target')]}


def _rpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _validate_goal_arguments(goal, pair):
    """Validate goal structure now; the service binds it to real host identities.

    Temporary distinct IDs permit optional pair fields at this transport layer.
    They are never passed to the service or used as scene/authority defaults.
    """
    from .task_verification import _goal
    if not isinstance(goal, dict):
        raise ValueError("goal must be an object")
    candidate = copy.deepcopy(goal)
    used = {value for value in (*goal.values(), *pair.values()) if isinstance(value, str)}
    for field in ("focal_id", "reference_id"):
        if field in candidate and field in pair and candidate[field] != pair[field]:
            raise ValueError("goal." + field + " differs from the selected object pair")
        if field not in candidate:
            if field in pair:
                candidate[field] = pair[field]
            else:
                placeholder = "__unbound_goal_" + field + "__"
                while placeholder in used:
                    placeholder += "_"
                candidate[field] = placeholder
                used.add(placeholder)
    if ("target_focal_pivot_world_m" in candidate
            and not isinstance(candidate["target_focal_pivot_world_m"], list)):
        raise ValueError("goal.target_focal_pivot_world_m must be an array")
    _goal(candidate)


def _validate_arguments(name: str, arguments: Any) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    allowed = {
        'human_eye_spatial_relations': {'target', 'candidates', 'include_aabb'},
        'human_eye_surface_nearest': {'target'},
        'human_eye_arm_twist_observe': {'selection', 'session_id', 'task_context'},
        "human_eye_scene_observe": {"task_instruction", "focal_id", "reference_id", "session_id", "goal", "query", 'task_context', 'scene_delta', 'response_detail', 'include_image'},
        "human_eye_transform": {"action", "session_id", "goal", 'task_context'},
        "human_eye_connection_status": set(),
        'human_eye_clearance_segment': {'session_id', 'request_id', 'request', 'execute', 'include_image', 'task_context', 'response_detail'},
    }
    if name not in allowed:
        raise ValueError(f"Unknown tool: {name}")
    if set(arguments) - allowed[name]:
        raise ValueError("Unexpected tool arguments")
    if name == 'human_eye_spatial_relations':
        if type(arguments.get('include_aabb', False)) is not bool:
            raise ValueError('include_aabb must be boolean')
        validate_query(_spatial_task_query(arguments))
        return
    if name == 'human_eye_surface_nearest':
        validate_query(_surface_nearest_task_query(arguments))
        return
    for field in ("session_id", "focal_id", "reference_id"):
        if field in arguments and (not isinstance(arguments[field], str) or not arguments[field].strip()):
            raise ValueError(f"{field} must be a nonempty string")
    if "task_instruction" in arguments and not isinstance(arguments["task_instruction"], str):
        raise ValueError("task_instruction must be a string")
    if name == 'human_eye_arm_twist_observe' and type(arguments.get('selection')) is not dict:
        raise ValueError('selection must be an object')
    if 'response_detail' in arguments and (not isinstance(arguments['response_detail'], str)
            or arguments['response_detail'] not in ('full', 'brief')):
        raise ValueError('response_detail must be full or brief')
    if "query" in arguments:
        selected_query = validate_query(arguments["query"])
    if name == 'human_eye_scene_observe':
        if 'include_image' in arguments and type(arguments['include_image']) is not bool:
            raise ValueError('include_image must be boolean')
        if 'query' not in arguments:
            selected_query = validate_query(None)
        if selected_query['mode'] == 'surface_nearest':
            if 'objects' in selected_query and 'focal_id' in arguments:
                raise ValueError('surface_nearest accepts query.objects or focal_id, not both')
            if (not arguments.get('session_id') or ('objects' not in selected_query and not arguments.get('focal_id'))
                    or arguments.get('include_image', True)
                    or any(arguments.get(key) is not None for key in ('goal', 'reference_id', 'scene_delta'))):
                raise ValueError('surface_nearest requires session_id, one target, include_image=false and no reference, goal or scene_delta')
        if (selected_query.get('alignment_evidence') is False
                and arguments.get('include_image', True)):
            raise ValueError('alignment_evidence=false requires include_image=false')
    if 'task_context' in arguments:
        if not isinstance(arguments['task_context'], dict):
            raise ValueError('task_context must be an object')
        validate_task_context(arguments['task_context'])
    if 'scene_delta' in arguments:
        if not isinstance(arguments['scene_delta'], dict):
            raise ValueError('scene_delta must be an object')
        validate_scene_delta_request(arguments['scene_delta'])
    if name == 'human_eye_clearance_segment':
        identity = arguments.get('request_id')
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError('request_id is required')
        validate_clearance_segment_request(arguments.get('request'))
        for flag in ('execute', 'include_image'):
            if flag in arguments and type(arguments[flag]) is not bool:
                raise ValueError(flag + ' must be boolean')
        return
    if name != "human_eye_transform":
        if "goal" in arguments:
            _validate_goal_arguments(arguments["goal"],
                {field: arguments[field] for field in ("focal_id", "reference_id") if field in arguments})
        if (name == 'human_eye_scene_observe' and selected_query['mode'] == 'task'
                and (arguments.get('include_image', True)
                     or any(field in arguments for field in ('focal_id', 'reference_id', 'goal', 'scene_delta')))):
            raise ValueError('task queries require include_image=false and selectors only in query.objects or query.target/query.candidates')
        return
    action = arguments.get("action")
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    if (set(action) - set(_ACTION_SCHEMA["properties"])
            or not {"translation", "rotation_euler_deg"}.intersection(action)):
        raise ValueError("action requires an exact rigid transform")
    for field in ("focal_id", "reference_id"):
        if not isinstance(action.get(field), str) or not action[field].strip():
            raise ValueError(f"action.{field} must be a nonempty string")
    if action["focal_id"] == action["reference_id"]:
        raise ValueError("focal_id and reference_id must be distinct")
    for field in ("translation", "rotation_euler_deg"):
        if field not in action:
            continue
        vector = action[field]
        if (not isinstance(vector, list) or len(vector) != 3
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)):
            raise ValueError(f"action.{field} requires three finite numbers")
    if "goal" in arguments:
        _validate_goal_arguments(arguments["goal"],
            {field: action[field] for field in ("focal_id", "reference_id")})


def _project_capability_aliases(metadata):
    """Replace exact new-field wire duplicates; keep SDK results untouched."""
    target = '#/scene_capabilities'
    capability = metadata.get('scene_capabilities')
    routing = metadata.get('routing')
    marker = 'same_tool_result_metadata_json_pointer'
    if (not isinstance(capability, dict) or not isinstance(routing, dict)
            or metadata.get('capability_reference_encoding', marker) != marker):
        return
    def equal(value):
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) == json.dumps(
                capability, sort_keys=True, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False
    replaced = False
    if ('scene_capabilities' in routing and routing.get('scene_capabilities_ref', target) == target
            and equal(routing['scene_capabilities'])):
        routing.pop('scene_capabilities')
        routing['scene_capabilities_ref'] = target
        replaced = True
    facts, status = _parse_observation(routing.get('context_text'))
    if (status == 'structured' and 'scene_capabilities' in facts
            and facts.get('scene_capabilities_ref', target) == target
            and equal(facts['scene_capabilities'])):
        facts.pop('scene_capabilities')
        facts['scene_capabilities_ref'] = target
        routing['context_text'] = json.dumps(facts, ensure_ascii=False, allow_nan=False)
        replaced = True
    if replaced:
        metadata['capability_reference_encoding'] = marker


def _project_support_plane_discovery_aliases(metadata):
    """Keep compact selectors once, with exact same-result references.

    SDK evidence stays detached and complete. Only byte-equivalent new-field
    dictionaries are replaced; disagreement remains visible in full.
    """
    field = 'support_plane_discovery'
    target = '#/' + field
    discovery = metadata.get(field)
    routing = metadata.get('routing')
    marker = 'same_tool_result_metadata_json_pointer'
    if (not isinstance(discovery, dict) or not isinstance(routing, dict)
            or metadata.get('support_plane_reference_encoding', marker) != marker):
        return
    def equal(value):
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) == json.dumps(
                discovery, sort_keys=True, ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False
    facts, status = _parse_observation(routing.get('context_text'))
    # Retain all conflicting original copies. Partial aliasing would hide the
    # route copy needed by the brief's contradiction check.
    if ((field in routing and not equal(routing[field]))
            or (status == 'structured' and field in facts and not equal(facts[field]))):
        return
    replaced = False
    if (field in routing and routing.get(field + '_ref', target) == target
            and equal(routing[field])):
        routing.pop(field)
        routing[field + '_ref'] = target
        replaced = True
    if (status == 'structured' and field in facts
            and facts.get(field + '_ref', target) == target and equal(facts[field])):
        facts.pop(field)
        facts[field + '_ref'] = target
        routing['context_text'] = json.dumps(facts, ensure_ascii=False, allow_nan=False)
        replaced = True
    if replaced:
        metadata['support_plane_reference_encoding'] = marker


def _compact_discovery_metadata(metadata):
    """Reversibly reference repeated major facts only for opted-in discovery.

    Reuses the Hook dictionary codec. References inside context_text target
    preceding structured metadata only, never a path through that JSON string.
    The compact selector itself remains a complete directly readable object.
    """
    marker = 'same_tool_result_metadata_json_pointer'
    if (metadata.get('support_plane_reference_encoding') != marker
            or not isinstance(metadata.get('support_plane_discovery'), dict)
            or 'support_plane_value_encoding' in metadata or _contains_reference_key(metadata)):
        return None
    route = metadata.get('routing')
    if not isinstance(route, dict):
        return None
    raw = route.get('context_text')
    facts = None
    if raw is not None:
        facts, status = _parse_observation(raw)
        if (status != 'structured' or _contains_reference_key(facts)
                or json.dumps(facts, ensure_ascii=False, allow_nan=False) != raw):
            return None
    known = {'query_result', 'rigid_frame', 'measurement', 'scene_contacts',
             'scene_assessment', 'scene_capabilities'}
    seen = {}
    def path_for(path, key):
        return path + '/' + key.replace('~', '~0').replace('/', '~1')
    def replace_known(value, path, catalog):
        return {key: (_deduplicate(item, path_for(path, key), catalog)
                      if key in known else copy.deepcopy(item))
                for key, item in value.items()}
    # Canonical top fields precede routing, whose own structured facts precede
    # context_text; a parsed brief observation comes last. No forward scope.
    ordered = {key: value for key, value in metadata.items() if key not in ('routing', 'observation')}
    result = replace_known(ordered, '#', seen)
    route_fields = {key: value for key, value in route.items() if key != 'context_text'}
    result['routing'] = replace_known(route_fields, '#/routing', seen)
    if facts is not None:
        class ExistingMetadataOnly(dict):
            # New dictionaries seen in the decoded string cannot become
            # physical JSON Pointer targets. Existing metadata is read-only.
            def __setitem__(self, key, value):
                pass
        catalog = ExistingMetadataOnly(seen)
        replaced = replace_known(facts, '#/decoded_context_text', catalog)
        result['routing']['context_text'] = json.dumps(replaced, ensure_ascii=False, allow_nan=False)
    if 'observation' in metadata:
        observation = metadata['observation']
        if not isinstance(observation, dict):
            return None
        result['observation'] = replace_known(observation, '#/observation', seen)
    header = {'revision': 'discovery-major-fact-references-v1-20261028',
        'reference_encoding': 'local_pointer_with_object_id',
        'reference_base': 'this_same_tool_result_metadata',
        'context_text_reference_base': 'enclosing_metadata_not_the_decoded_string',
        'context_text_serialization': 'json.dumps_ensure_ascii_false_default_separators' if facts is not None else None,
        'scope': 'exact_value_transport_only_no_geometry_or_authority_change',
        'execution_authority': False}
    return {'support_plane_value_encoding': header, **result}


def _project_spatial_relations(value):
    """Same facts, with request rows and shared metadata written only once."""
    if value.get('schema_version') != 'task-query-set-v1':
        return value
    binding = value['binding']
    rows = [dict(row) for row in binding['objects']]
    context = {key: item for key, item in binding.items() if key not in ('objects', 'host_identity')}
    context.update(scope=value['scope'], unit=value['unit'], coordinate_frame=value['coordinate_frame'],
                   pair_order=value['pair_order'])
    host = binding.get('host_identity')
    if host is not None:
        instances = host.get('object_instances', {})
        for row in rows:
            if row.get('object_id') in instances:
                row['instance_id'] = instances[row['object_id']]
        remaining = {oid: instance for oid, instance in instances.items()
                     if not any(row.get('object_id') == oid for row in rows)}
        context['host_identity'] = {key: item for key, item in host.items()
            if key != 'object_instances' and not (key == 'capture_scope' and item == context.get(key))}
        if remaining:
            context['host_identity']['object_instances'] = remaining
        context['identity_scope'] = 'Object and instance IDs belong to this captured document/snapshot.'
    boxes = value['facts'].get('aabb')
    if boxes is not None:
        for row, box in zip(rows, boxes):
            row['aabb'] = box
    pairs = value['pairs']
    contracts = {}
    for name in ('closed_solid_relation', 'surface_proximity', 'separation_gap'):
        facts = [pair['separation_gap'] if name == 'separation_gap' else pair['facts'][name]
                 for pair in pairs]
        common = {key: facts[0][key] for key in
                  ('method', 'semantics', 'geometry_scope', 'relation_tolerance_m')
                  if key in facts[0] and all(key in fact and fact[key] == facts[0][key] for fact in facts)}
        if common:
            contracts[name] = common
        for pair, fact in zip(pairs, facts):
            row = rows[pair['candidate_index'] + 1]
            row['candidate_index'] = pair['candidate_index']
            row[name] = {key: item for key, item in fact.items() if key not in common}
    if any('certificate' in row['closed_solid_relation'] for row in rows[1:]):
        context['certificate_scope'] = 'Proof category only; surface witnesses are not shared-interior proofs.'
    indices = {row['object_id']: row['candidate_index'] for row in rows[1:] if 'object_id' in row}
    def candidate_indices(ids):
        return None if ids is None else [indices[oid] for oid in ids]
    summary = value['summary']
    penetrating = {'complete': summary['penetration_set_complete'],
                   'candidate_indices': candidate_indices(summary['penetrating_ids'])}
    if summary['known_penetrating_ids'] != summary['penetrating_ids']:
        penetrating['known_candidate_indices'] = candidate_indices(summary['known_penetrating_ids'])
    if summary['unresolved_relations']:
        penetrating['unresolved'] = summary['unresolved_relations']
    nearest = {'complete': summary['nearest_separated_complete'],
               'candidate_indices': candidate_indices(summary['nearest_separated_ids']),
               'distance_m': summary['distance_m']}
    if (summary['best_known_separated_ids'] != summary['nearest_separated_ids']
            or summary['best_known_distance_m'] != summary['distance_m']):
        nearest.update(best_known_candidate_indices=candidate_indices(summary['best_known_separated_ids']),
                       best_known_distance_m=summary['best_known_distance_m'])
    if summary['unresolved_distances']:
        nearest['unresolved_distances'] = [dict(candidate_index=indices[oid], reason=reason)
            for oid, reason in summary['unresolved_distances'].items()]
    result = {'result_kind': value['result_kind'], 'schema_version': 'spatial-relations-v1',
        'status': value['status'], 'target': rows[0], 'candidates': rows[1:],
        'sets': {'penetrating': penetrating, 'nearest_separated': nearest},
        'coverage': value['coverage'], 'context': context, 'measurement_contracts': contracts,
        'execution_authority': value['execution_authority']}
    if 'trace_id' in value:
        result['trace_id'] = value['trace_id']
    return result


def _tool_result(value: Any, *, is_error: bool, response_detail: str = 'full',
                 compact_support_planes: bool = False, segment_brief: bool = False) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Live service returned an invalid result")
    if (value.get('result_kind') in ('task_query', 'surface_nearest')
            or value.get('schema') == 'arm-twist-expert-report-v1'):
        # Already selected structured facts. No full diagnostic, alias pass,
        # copy, model message, nested context JSON or second encoding.
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        record_image_artifact('mcp_content', native_block_count=0)
        return {'content': [{'type': 'text', 'text': text}], 'isError': bool(is_error)}
    metadata = copy.deepcopy(value)
    _project_capability_aliases(metadata)
    _project_support_plane_discovery_aliases(metadata)
    routing = metadata.get("routing")
    picture = routing.pop("image", None) if isinstance(routing, dict) else None
    pictures = routing.pop("images", None) if isinstance(routing, dict) else None
    content = []
    if pictures is not None:
        if picture is not None or type(pictures) is not list or not 1<=len(pictures)<=2:
            raise ValueError('Live service returned an invalid native image bundle')
        staged=[]
        for image in pictures:
            if (type(image) is not dict or set(image)!={'type','mimeType','data'}
                    or image['type']!='image' or image['mimeType']!='image/png'
                    or type(image['data']) is not str or len(image['data'])>4*((8*1024*1024+2)//3)):
                raise ValueError('Live service returned an invalid native PNG content block')
            decoded=_public_native_png(base64.b64decode(image['data'],validate=True))
            if decoded[16:24]!=b'\x00\x00\x01\x80\x00\x00\x01\x80':
                raise ValueError('Live service returned an invalid native PNG shape')
            staged.append({'type':'image','mimeType':'image/png','data':base64.b64encode(decoded).decode('ascii')})
        content.extend(staged)
    if picture is not None:
        if (not isinstance(picture, dict) or picture.get("type") != "image"
                or picture.get("mimeType") != "image/png" or not isinstance(picture.get("data"), str)):
            raise ValueError("Live service returned an invalid PNG content block")
        try:
            decoded = base64.b64decode(picture["data"], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("Live service returned invalid image data") from exc
        if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Live service returned invalid PNG data")
        content.append({"type": "image", "mimeType": "image/png", "data": picture["data"]})
    # Keep image bytes in a native MCP image block only, rather than repeating
    # base64 in the JSON text the model needs to read.
    full_text = json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    if metadata.get('result_kind') in ('structure_task','surface_task') and 'accounted_public_text_bytes' in metadata:
        charge=metadata['accounted_public_text_bytes']
        if type(charge) is not int or not len(full_text.encode('utf8'))<=charge<=96*1024:
            raise ValueError('Structure task text exceeds its committed charge')
    text = full_text
    selected_metadata = metadata
    if response_detail == 'brief' and not is_error:
        try:
            brief = (project_structure_brief(metadata) if metadata.get('result_kind')=='structure_task' else
                None if metadata.get('result_kind')=='surface_task' else project_segment_brief(metadata) if segment_brief else project_task_brief(metadata))
            if brief is not None:
                candidate = json.dumps(brief, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                full_bytes = len(full_text.encode('utf-8'))
                brief_bytes = len(candidate.encode('utf-8'))
                # A request for less detail must actually save transport bytes.
                # This threshold is representation policy, never a geometry gate.
                if full_bytes - brief_bytes >= 256 and brief_bytes <= full_bytes * .9:
                    text = candidate
                    selected_metadata = brief
        except Exception:
            # Only the optional display projection is recoverable. Original
            # full JSON and native PNG validation above must still succeed.
            text = full_text
    if compact_support_planes and not is_error:
        try:
            compact = _compact_discovery_metadata(selected_metadata)
            if compact is not None:
                encoded = json.dumps(compact, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                if len(encoded.encode('utf-8')) < len(text.encode('utf-8')):
                    text = encoded
        except Exception:
            # Encoding can only fall back to the unchanged complete payload.
            pass
    content.insert(0, {"type": "text", "text": text})
    if metadata.get('result_kind') in ('structure_task','surface_task') and 'task_budget' in metadata:
        budget=metadata['task_budget']
        if (type(budget) is not dict or type(budget.get('deadline_ns')) is not int
                or type(budget.get('deadline_wall_ns')) is not int
                or time.perf_counter_ns()>=budget['deadline_ns'] or time.time_ns()>=budget['deadline_wall_ns']):
            raise ValueError('Structure task delivery deadline expired before MCP content publication')
    record_image_artifact('mcp_content', native_block_count=sum(c['type']=='image' for c in content))
    return {"content": content, "isError": bool(is_error)}


class LiveSpatialMCPServer:
    """One persistent MCP process, with a stable default spatial session."""

    def __init__(self, service: Any, default_session_id: str | None = None, *, spatial_task_only=False):
        if type(spatial_task_only) is not bool:
            raise ValueError('spatial_task_only must be boolean')
        self.service = service
        self.spatial_task_only = spatial_task_only
        self.default_session_id = f"mcp-{uuid.uuid4()}" if default_session_id is None else default_session_id
        if not isinstance(self.default_session_id, str) or not self.default_session_id.strip():
            raise ValueError("default_session_id must be a nonempty string")

    @contextmanager
    def request_trace(self, name, arguments, *, mcp_request_id=_NO_RPC_ID):
        factory = getattr(self.service, 'request_trace', None)
        if not callable(factory):
            yield None
            return
        operations = {'human_eye_scene_observe': 'mcp.observe',
                      'human_eye_spatial_relations': 'mcp.observe',
                      'human_eye_surface_nearest': 'mcp.observe',
                      'human_eye_arm_twist_observe': 'mcp.arm_twist_observe',
                      'human_eye_transform': 'mcp.transform',
                      'human_eye_clearance_segment': 'mcp.clearance_segment',
                      'human_eye_connection_status': 'mcp.status'}
        args = arguments if isinstance(arguments, dict) else {}
        operation = operations.get(name, 'mcp.invalid') if isinstance(name, str) else 'mcp.invalid'
        with factory(operation,
                     session_id=args.get('session_id', self.default_session_id)) as trace:
            set_image_request(False if name in {'human_eye_spatial_relations', 'human_eye_surface_nearest', 'human_eye_arm_twist_observe'} else
                              args.get('include_image', False) if name == 'human_eye_clearance_segment' else
                              args.get('include_image', True) if name == 'human_eye_scene_observe' else
                              True if name == 'human_eye_transform' else None,
                              source_name='mcp_transport')
            if mcp_request_id is not _NO_RPC_ID:
                id_type = ('null' if mcp_request_id is None else
                           'string' if type(mcp_request_id) is str else
                           'integer' if type(mcp_request_id) is int else None)
                # Only the actual envelope ID is recorded. params._meta and
                # model-selected tool arguments confer no host identity.
                annotate(mcp_request_id=mcp_request_id, mcp_request_id_type=id_type)
            yield trace

    def _call_tool(self, name: str, arguments: dict, *, mcp_request_id=_NO_RPC_ID) -> dict:
        budget = getattr(self.service, '_request_budget', nullcontext)
        with self.request_trace(name, arguments, mcp_request_id=mcp_request_id), budget():
            annotate(request_origin='mcp')
            value = self._dispatch_tool(name, arguments)
            # Constructing native content proves transport preparation only.
            annotate(delivery='mcp_content_constructed')
            return value

    def request_error_fields(self, error=None):
        describe = getattr(self.service, 'request_error_fields', None)
        return describe(error) if callable(describe) else {}

    def _error_result(self, exc):
        metadata = {'status': 'error', 'error': str(exc),
            'tool_outcome': 'unknown', 'automatic_retry': False,
            **self.request_error_fields(exc)}
        from .live_service import StateBindingError, RequestBudgetError
        if isinstance(exc, (StateBindingError, RequestBudgetError)):
            metadata.update(exc.to_error_fields())
            metadata['allow_action'] = False
        return _tool_result(metadata, is_error=True)

    def _dispatch_tool(self, name: str, arguments: dict) -> dict:
        spatial_task = name in {tool['name'] for tool in SPATIAL_TASK_TOOLS_SCHEMA}
        if spatial_task != self.spatial_task_only:
            raise ValueError('Tool not exposed by this server mode: ' + name)
        _validate_arguments(name, arguments)
        spatial_relations = name == 'human_eye_spatial_relations'
        if spatial_relations:
            arguments = {'query': _spatial_task_query(arguments), 'include_image': False}
            name = 'human_eye_scene_observe'
        elif name == 'human_eye_surface_nearest':
            arguments = {'query': _surface_nearest_task_query(arguments), 'include_image': False}
            name = 'human_eye_scene_observe'
        bind_task_context(current_trace(), arguments.get('task_context'))
        # A service must not retain or mutate the incoming protocol message.
        args = copy.deepcopy(arguments)
        session_id = args.get("session_id", self.default_session_id)
        goal_kwargs = {"goal": args["goal"]} if "goal" in args else {}
        query_kwargs = {"query": args["query"]} if "query" in args else {}
        context_kwargs = {'task_context': args['task_context']} if 'task_context' in args else {}
        delta_kwargs = {'scene_delta': args['scene_delta']} if 'scene_delta' in args else {}
        if name == "human_eye_scene_observe":
            value = self.service.observe(
                session_id,
                task_instruction=args.get("task_instruction", ""),
                focal_id=args.get("focal_id"), reference_id=args.get("reference_id"),
                **({'include_image': args['include_image']} if 'include_image' in args else {}),
                **goal_kwargs,
                **query_kwargs,
                **context_kwargs,
                **delta_kwargs,
            )
            is_error = value.get("status") not in {"observed", "overview", "partial"}
            if value.get('result_kind') == 'surface_nearest':
                is_error = value.get('status') not in {'complete', 'partial'}
            if value.get('result_kind') in ('structure_task','surface_task') and value.get('status')=='receipt':is_error=False
        elif name == 'human_eye_arm_twist_observe':
            value = self.service.observe_arm_twist(session_id, args['selection'], **context_kwargs)
            is_error = value.get('status') not in {'estimated', 'unknown'}
        elif name == "human_eye_transform":
            value = self.service.transform(session_id, args["action"], **goal_kwargs, **context_kwargs)
            is_error = value.get("status") not in {"verified", "no_op"}
        elif name == 'human_eye_clearance_segment':
            value = self.service.run_clearance_segment(session_id, args['request_id'], args['request'],
                execute=args.get('execute', False), include_image=args.get('include_image', False), **context_kwargs)
            is_error = value.get('status') not in {'preview', 'satisfied', 'review_required', 'segment_interrupted'}
        else:
            value = self.service.status()
            is_error = value.get("status") in {"blocked", "error", "unavailable", "disconnected"}
        with span('mcp.content_encode', kind='encoding'):
            if spatial_relations:
                value = _project_spatial_relations(value)
            result = _tool_result(value, is_error=is_error,
                response_detail=args.get('response_detail', 'full'),
                segment_brief=(name == 'human_eye_clearance_segment'),
                compact_support_planes=(name == 'human_eye_scene_observe'
                    and 'support_plane_discovery' in args.get('query', {})))
        if value.get('result_kind') in ('task_query', 'surface_nearest'):
            self.service._check_request_budget('before_task_publication')
        return result

    def handle_jsonrpc_message(self, req: Any) -> dict | None:
        try:wire.validate_request(req,allow_nonfinite=True)
        except wire.RPCInputError as exc:return _rpc_error(None,exc.code,exc.message)
        method, request_id = req["method"], req.get("id")
        # JSON-RPC notifications never receive responses. They also never run
        # mutating tools, even if a malformed client sends tools/call this way.
        if "id" not in req:
            return None
        params = req.get("params", {})
        if not isinstance(params, dict):
            return _rpc_error(request_id, -32602, "params must be an object")
        if method == "initialize":
            describe = getattr(self.service, 'describe_runtime', None)
            identity = describe() if callable(describe) else runtime_identity(mode='live')
            identity = copy.deepcopy(identity)
            identity['source_file_count'] = identity.get('source_file_count', len(identity.pop('source_files', [])))
            result = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "human-eye-live-spatial", "version": BASE_VERSION},
                '_meta': {'human_eye': identity},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": copy.deepcopy(SPATIAL_TASK_TOOLS_SCHEMA if self.spatial_task_only else LIVE_MCP_TOOLS_SCHEMA)}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str):
                return _rpc_error(request_id, -32602, "Tool name must be a string")
            try:
                result = self._call_tool(params["name"], params.get("arguments", {}),
                                         mcp_request_id=request_id)
            except Exception as exc:
                result = self._error_result(exc)
        else:
            return _rpc_error(request_id, -32601, f"Method not found: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle_jsonrpc_message(req: Any, service: Any = None, *, server: LiveSpatialMCPServer | None = None) -> dict | None:
    """Convenience handler; reuse ``server`` for a persistent default session."""
    if server is None:
        if service is None:
            raise ValueError("A live service or server is required")
        server = LiveSpatialMCPServer(service)
    return server.handle_jsonrpc_message(req)


def run_stdio_mcp_server(service: Any, input_stream: TextIO | None = None,
                         output_stream: TextIO | None = None, *, spatial_task_only=False) -> None:
    """Serve newline-delimited MCP JSON-RPC without writing logs to stdout."""
    incoming = sys.stdin if input_stream is None else input_stream
    outgoing = sys.stdout if output_stream is None else output_stream
    server = LiveSpatialMCPServer(service, spatial_task_only=spatial_task_only)
    try:
        for req,error in wire.requests(incoming):
            if error is not None:
                if not wire.write_encoded(outgoing,wire.encode_response(error)):break
                continue
            params=req.get('params')
            traced=(req.get('method')=='tools/call' and 'id' in req and isinstance(params,dict))
            scope=server.request_trace(params.get('name'),params.get('arguments',{}),mcp_request_id=req['id']) if traced else nullcontext()
            budget=getattr(service,'_request_budget',nullcontext) if traced else nullcontext
            published=False;pipe_closed=False;write_started=False
            try:
                with budget(),scope:
                    response=server.handle_jsonrpc_message(req)
                    if response is not None:
                        terminal_error=('error' in response or response.get('result',{}).get('isError') is True)
                        try:
                            with span('mcp.wire_encode',kind='encoding'):
                                encoded=wire.encode_response(response,req,error_fields=server.request_error_fields)
                        except Exception as exc:
                            response={'jsonrpc':'2.0','id':req['id'],'result':server._error_result(exc)}
                            encoded=wire.encode_response(response,req,error_fields=server.request_error_fields)
                            terminal_error=True
                        with span('mcp.stdio_write',kind='io'):
                            check=getattr(service,'_check_request_budget',None)
                            if traced and not terminal_error and callable(check):
                                try:
                                    check('before_stdio_write',publication=True)
                                except Exception as exc:
                                    response={'jsonrpc':'2.0','id':req['id'],'result':server._error_result(exc)}
                                    # Encode the one terminal error without
                                    # renewing or rechecking its expired budget.
                                    encoded=wire.encode_response(response,req,error_fields=server.request_error_fields)
                            write_started=True
                            pipe_closed=not wire.write_encoded(outgoing,encoded)
                        if pipe_closed:break
                        published=True
                        annotate(output_bytes=len(encoded.encode('utf8')),delivery='stdio_write_completed')
            except Exception as exc:
                # Handler/encoder/trace failures belong to this request. A
                # completed write must never get a second response or dispatch.
                if pipe_closed or write_started and not published:break
                if not published and 'id' in req:
                    failure=wire.internal_error(req)
                    failure['error']['data'].update(server.request_error_fields(exc))
                    if not wire.write_encoded(outgoing,wire.encode_response(failure,req)):break
    finally:
        # EOF and actual output/input failure end the connection. No tool call
        # or write is retried; close a live host socket before returning.
        owner=service if callable(getattr(service,'close',None)) else getattr(service,'host',None)
        close=getattr(owner,'close',None)
        if callable(close):close()


def _configure_utf8_stdio() -> None:
    # MCP stdio is UTF-8, including when Windows starts Python with an ANSI
    # default encoding. Injected streams used by callers need no reconfigure.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None, *, spatial_task_only=False) -> int:
    if type(spatial_task_only) is not bool:
        raise ValueError('spatial_task_only must be boolean')
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Serve the live Human Eye Blender connection over MCP stdio")
    parser.add_argument("--config", required=True, help="Trusted local live-service configuration JSON")
    parser.add_argument('--spatial-task-only', action='store_true', default=spatial_task_only,
                        help='Expose only read-only spatial relations and global surface-nearest tasks')
    args = parser.parse_args(argv)
    from .live_service import LiveSpatialService
    try:
        service = LiveSpatialService(args.config, production_mode=True)
    except Exception as exc:
        print(f"Unable to configure live spatial service: {exc}", file=sys.stderr)
        return 2
    run_stdio_mcp_server(service, **({'spatial_task_only': True} if args.spatial_task_only else {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
