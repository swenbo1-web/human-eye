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
    "description": "Observation precision request; never an execution permission. nearest requires complete exact nonpenetrating order; top1 may exclude supported distant objects by strict outward bounds and reports equal-distance ties. Unknown or budget-limited proofs return no nearest result.",
    "properties": {
        "mode": {"type": "string", "enum": ["task", "overview", "exact_pairs", "nearest", "top1", "mesh_structure", "mesh_surface"]},
        "objects": {"type": "array", "items": SELECTOR_SCHEMA, "minItems": 1, "maxItems": 4,
            "description": "task only: exact name or id selectors bound to one fresh capture. Pair facts use exactly two objects ordered A to B."},
        "requested_facts": {"type": "array", "items": {"type": "string", "enum": list(TASK_FACTS)},
            "minItems": 1, "uniqueItems": True},
        "operation": {"type":"string","enum":["diagnose","patch","reference","restore_preview","reference_patch"],
            "description":"Registered single-target reads. mesh_structure: diagnose text or patch images. mesh_surface: local opt-in; diagnose/reference/restore_preview require include_image=false. reference_patch uses a returned opaque feature patch_ref and may request useful native images under the original task budget. Reference input is locally trusted; previews never execute. Caller labels never reset budgets."},
        "request_id": {"type":"string","minLength":1,"maxLength":128},
        "near_m": {"type":"number","minimum":0,"maximum":0.001},
        "threshold_m": {"type":"number","exclusiveMinimum":0,"maximum":0.01},
        "reference_ref": {"type":"string","pattern":"^[a-f0-9]{32}$"},
        "indices": {"type":"array","items":{"type":"integer","minimum":0,"maximum":4095},"minItems":1,"maxItems":64,"uniqueItems":True},
        "patch_ref": {"type":"string","pattern":"^[a-f0-9]{32}$"},
        "task_ref": {"type":"string","pattern":"^[a-f0-9]{32}$",
            "description":"Required in locally controlled lifecycle mode; use the trusted begin handoff. Selects the active registered generation and never creates or renews a task."},
        "object_ids": {"type": "array", "items": copy.deepcopy(_ID_SCHEMA), "minItems": 1, "maxItems": 255, "uniqueItems": True},
        "label_object_ids": {"type": "array", "items": copy.deepcopy(_ID_SCHEMA), "minItems": 1, "maxItems": MAX_VISUAL_LABEL_IDS, "uniqueItems": True,
            "description": "Optional current full object IDs to prioritize in paired image observations. Separate from measurement object_ids; expands only the related annotation budget, up to six related labels plus A/B. Missing pair, unrequested image, occlusion or undersampling is reported explicitly; never an action permission."},
        "max_exact_pairs": {"type": "integer", "minimum": 1, "maximum": 255},
        "alignment_evidence": {"type": "boolean", "default": True,
            "description": "False explicitly requests strict distance evidence without optional face-alignment angles; requires include_image=false. Host rigid-frame and all action checks remain independent."},
        "support_plane_discovery": copy.deepcopy(SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA),
        "native_visual": copy.deepcopy(NATIVE_VISUAL_SCHEMA),
        "visual_diagnostic": {"type": "string", "enum": ["contact_section"],
            "description": "Append an analytical full-mesh contact section beside the natural views; not natural visibility or an action permission."},
    },
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
            "Read current Blender facts directly: query={mode:'task',objects:[{name:'Part'},{name:'Base'}],"
            "requested_facts:['surface_clearance','center_delta']} with include_image=false. "
            "aabb accepts 1..4 objects; pair facts require two ordered A to B. Unknown is field-specific. "
            "Read the current Blender scene and obtain a measured spatial observation. "
            "Use returned object IDs to select focal and reference objects. "
            "Observations describe the live scene and may expire when it changes. "
            "An optional caller-supplied goal checks current task criteria separately. "
            "mesh_structure consumes an explicitly registered single-object read task; diagnose returns facts and patch references, then patch can request fresh local images."
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
        "human_eye_scene_observe": {"task_instruction", "focal_id", "reference_id", "session_id", "goal", "query", 'task_context', 'scene_delta', 'response_detail', 'include_image'},
        "human_eye_transform": {"action", "session_id", "goal", 'task_context'},
        "human_eye_connection_status": set(),
        'human_eye_clearance_segment': {'session_id', 'request_id', 'request', 'execute', 'include_image', 'task_context', 'response_detail'},
    }
    if name not in allowed:
        raise ValueError(f"Unknown tool: {name}")
    if set(arguments) - allowed[name]:
        raise ValueError("Unexpected tool arguments")
    for field in ("session_id", "focal_id", "reference_id"):
        if field in arguments and (not isinstance(arguments[field], str) or not arguments[field].strip()):
            raise ValueError(f"{field} must be a nonempty string")
    if "task_instruction" in arguments and not isinstance(arguments["task_instruction"], str):
        raise ValueError("task_instruction must be a string")
    if 'response_detail' in arguments and (not isinstance(arguments['response_detail'], str)
            or arguments['response_detail'] not in ('full', 'brief')):
        raise ValueError('response_detail must be full or brief')
    if "query" in arguments:
        validate_query(arguments["query"])
    if name == 'human_eye_scene_observe':
        if 'include_image' in arguments and type(arguments['include_image']) is not bool:
            raise ValueError('include_image must be boolean')
        if (validate_query(arguments.get('query')).get('alignment_evidence') is False
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


def _tool_result(value: Any, *, is_error: bool, response_detail: str = 'full',
                 compact_support_planes: bool = False, segment_brief: bool = False) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Live service returned an invalid result")
    if value.get('result_kind') == 'task_query':
        # Already selected structured facts. No full diagnostic, alias pass,
        # copy, model message, nested context JSON or second encoding.
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        limit = 2048 if set(value['facts']) == {'aabb'} else 4096
        if len(text.encode('utf8')) > limit:
            raise ValueError('task_result_body_budget_exceeded; request fewer objects or facts')
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

    def __init__(self, service: Any, default_session_id: str | None = None):
        self.service = service
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
                      'human_eye_transform': 'mcp.transform',
                      'human_eye_clearance_segment': 'mcp.clearance_segment',
                      'human_eye_connection_status': 'mcp.status'}
        args = arguments if isinstance(arguments, dict) else {}
        operation = operations.get(name, 'mcp.invalid') if isinstance(name, str) else 'mcp.invalid'
        with factory(operation,
                     session_id=args.get('session_id', self.default_session_id)) as trace:
            set_image_request(args.get('include_image', False) if name == 'human_eye_clearance_segment' else
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
        task_read = (name == 'human_eye_scene_observe' and type(arguments) is dict
            and type(arguments.get('query')) is dict and arguments['query'].get('mode') == 'task')
        # Keep the original service deadline alive through selected-body
        # encoding. Nested service.observe reuses this scope, never renews it.
        budget = self.service._request_budget if task_read else nullcontext
        with self.request_trace(name, arguments, mcp_request_id=mcp_request_id), budget():
            annotate(request_origin='mcp')
            value = self._dispatch_tool(name, arguments)
            # Constructing native content proves transport preparation only.
            annotate(delivery='mcp_content_constructed')
            return value

    def _dispatch_tool(self, name: str, arguments: dict) -> dict:
        _validate_arguments(name, arguments)
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
            if value.get('result_kind') in ('structure_task','surface_task') and value.get('status')=='receipt':is_error=False
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
            result = _tool_result(value, is_error=is_error,
                response_detail=args.get('response_detail', 'full'),
                segment_brief=(name == 'human_eye_clearance_segment'),
                compact_support_planes=(name == 'human_eye_scene_observe'
                    and 'support_plane_discovery' in args.get('query', {})))
        if value.get('result_kind') == 'task_query':
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
            result = {"tools": copy.deepcopy(LIVE_MCP_TOOLS_SCHEMA)}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str):
                return _rpc_error(request_id, -32602, "Tool name must be a string")
            try:
                result = self._call_tool(params["name"], params.get("arguments", {}),
                                         mcp_request_id=request_id)
            except Exception as exc:
                metadata = {"status": "error", "error": str(exc),
                            "tool_outcome": "unknown", "automatic_retry": False}
                from .live_service import StateBindingError, RequestBudgetError
                if isinstance(exc, (StateBindingError, RequestBudgetError)):
                    metadata.update(exc.to_error_fields())
                    metadata.update(executed=False, execution_verified=False, allow_action=False)
                result = _tool_result(metadata, is_error=True)
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
                         output_stream: TextIO | None = None) -> None:
    """Serve newline-delimited MCP JSON-RPC without writing logs to stdout."""
    incoming = sys.stdin if input_stream is None else input_stream
    outgoing = sys.stdout if output_stream is None else output_stream
    server = LiveSpatialMCPServer(service)
    try:
        for req,error in wire.requests(incoming):
            if error is not None:
                if not wire.write_encoded(outgoing,wire.encode_response(error)):break
                continue
            params=req.get('params')
            traced=(req.get('method')=='tools/call' and 'id' in req and isinstance(params,dict))
            scope=server.request_trace(params.get('name'),params.get('arguments',{}),mcp_request_id=req['id']) if traced else nullcontext()
            published=False;pipe_closed=False
            try:
                with scope:
                    response=server.handle_jsonrpc_message(req)
                    if response is not None:
                        with span('mcp.wire_encode',kind='encoding'):
                            encoded=wire.encode_response(response,req)
                        with span('mcp.stdio_write',kind='io'):
                            pipe_closed=not wire.write_encoded(outgoing,encoded)
                        if pipe_closed:break
                        published=True
                        annotate(output_bytes=len(encoded.encode('utf8')),delivery='stdio_write_completed')
            except Exception:
                # Handler/encoder/trace failures belong to this request. A
                # completed write must never get a second response or dispatch.
                if pipe_closed:break
                if not published and 'id' in req:
                    if not wire.write_encoded(outgoing,wire.encode_response(wire.internal_error(req),req)):break
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


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Serve the live Human Eye Blender connection over MCP stdio")
    parser.add_argument("--config", required=True, help="Trusted local live-service configuration JSON")
    args = parser.parse_args(argv)
    from .live_service import LiveSpatialService
    try:
        service = LiveSpatialService(args.config, production_mode=True)
    except Exception as exc:
        print(f"Unable to configure live spatial service: {exc}", file=sys.stderr)
        return 2
    run_stdio_mcp_server(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
