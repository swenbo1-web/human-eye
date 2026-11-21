"""MCP transport for the live, guarded Blender service.

This entry point deliberately exposes a separate set of tools from the legacy
demo server. It requires a trusted local configuration and never loads a demo
scene or executes arbitrary host code supplied by a model.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
from fractions import Fraction
from contextlib import contextmanager, nullcontext
from functools import partial
import json
import math
from pathlib import Path
import sys
import time
import uuid
from typing import Any, TextIO

from .runtime_identity import BASE_VERSION, MCP_PROTOCOL_VERSION, runtime_identity
from .auto_router import _trace_span, _trace_annotate as annotate
from .query_policy import MAX_VISUAL_LABEL_IDS, NATIVE_VISUAL_SCHEMA, REGION_TASK_SCHEMA, validate_query
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
_SOURCE_TRIANGLE_ROWS_SCHEMA = {"type": "array", "minItems": 1, "maxItems": 4096,
    "uniqueItems": True, "items": {"type": "integer", "minimum": 0}}
_SOURCE_REGION_REF_SCHEMA = {
    "type": "object", "required": ["schema", "region_id", "document_epoch", "host_id", "instance_id",
        "capture_generation", "ordered_geometry_sha256", "source_triangle_indices"],
    "properties": {
        "schema": {"const": "human-eye-source-region-ref-v1"},
        "region_id": {"type": "string", "pattern": "^source-region:[a-f0-9]{64}$"},
        "document_epoch": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "host_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "instance_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "capture_generation": {"oneOf": [{"type": "null"}, {"type": "object",
            "required": ["instance_id", "epoch", "revision"],
            "properties": {"instance_id": {"type": "string", "minLength": 1},
                "epoch": {"type": "integer", "minimum": 0}, "revision": {"type": "integer", "minimum": 0}},
            "additionalProperties": False}]},
        "ordered_geometry_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "source_triangle_indices": copy.deepcopy(_SOURCE_TRIANGLE_ROWS_SCHEMA),
    }, "additionalProperties": False,
    "description": "Self-contained current region binding. Geometry and capture generation are validated on each reuse.",
}
_VECTOR_SCHEMA = {
    "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
}
_TASK_GEOMETRY_SCHEMA = {
    'type': 'object',
    'description': 'Opt-in geometry from the original relation bindings. Vertices use world metres; captured triangles are optional.',
    'properties': {
        'objects': {'type': 'array', 'items': copy.deepcopy(SELECTOR_SCHEMA), 'minItems': 1, 'maxItems': 4},
        'include_triangles': {'type': 'boolean', 'default': False},
    },
    'required': ['objects'], 'additionalProperties': False,
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
        "mode": {"type": "string", "enum": ["directory", "task", "surface_nearest", "surface_scan", "overview", "exact_pairs", "nearest", "top1", "mesh_structure", "mesh_surface", "active_observation", "source_region"]},
        "region": {"type": "object", "required": ["object", "source_triangle_indices"],
            "properties": {"object": copy.deepcopy(SELECTOR_SCHEMA),
                "source_triangle_indices": copy.deepcopy(_SOURCE_TRIANGLE_ROWS_SCHEMA)},
            "additionalProperties": False,
            "description": "Current evaluated object-local triangle rows. The full selected set participates in measurement."},
        "region_ref": copy.deepcopy(_SOURCE_REGION_REF_SCHEMA),
        "reference": copy.deepcopy(SELECTOR_SCHEMA),
        "objects": {"type": "array", "items": SELECTOR_SCHEMA, "minItems": 1, "maxItems": 4,
            "description": "active_observation: one visual target. Legacy task: aabb 1..4 selectors; pair facts two ordered A to B."},
        "task_query": {"type": "object", "required": ["mode", "objects", "requested_facts"],
            "description": "Optional active-observation quantitative query over entire selected objects, using the same source geometry. Pair selectors are ordered A to B.",
            "properties": {"mode": {"const": "task"},
                "objects": {"type": "array", "items": copy.deepcopy(SELECTOR_SCHEMA), "minItems": 1, "maxItems": 4},
                "requested_facts": {"type": "array", "minItems": 1, "uniqueItems": True,
                    "items": {"type": "string", "enum": list(TASK_FACTS)}}},
            "additionalProperties": False},
        'region_task': copy.deepcopy(REGION_TASK_SCHEMA),
        "target": copy.deepcopy(SELECTOR_SCHEMA),
        "candidates": {"type": "array", "items": copy.deepcopy(SELECTOR_SCHEMA), "minItems": 1, "maxItems": 3,
            "description": "1..3 explicit candidates in request order; one capture with target. Requires surface_proximity with spatial_relation or closed_solid_relation. Optional aabb supplies bounds."},
        "requested_facts": {"type": "array", "items": {"type": "string", "enum": list(TASK_FACTS)},
            "minItems": 1, "uniqueItems": True,
            "description": "task: spatial_relation proves strict full-referenced-vertex support separation or uses closed-shell classification, with geometry_scope identifying the performed proof. closed_solid_relation is zero-tolerance separated/touching/penetrating (positive-volume overlap, including containment) for represented connected closed triangle shells; invalid/ambiguous is unknown. surface_proximity independently gives nonnegative triangle-surface distance, original world witness points and positive-distance A-to-B direction; zero-distance direction is inapplicable. Boundary/nonmanifold counts do not certify solids. Penetrating/contained distances are not separated gaps. pair_relation's escape of A is not surface distance, nearest direction or minimum depth."},
        'geometry': copy.deepcopy(_TASK_GEOMETRY_SCHEMA),
        "operation": {"type":"string","enum":["diagnose","patch","reference","restore_preview","reference_patch"],
            "description":"Registered target reads. mesh_structure: diagnose text or patch images. mesh_surface (local opt-in): diagnose/reference/restore_preview require include_image=false; reference_patch uses a returned opaque patch_ref and optional native images. References are locally trusted; previews do not execute; the original task budget applies."},
        "request_id": {"type":"string","minLength":1,"maxLength":128},
        "near_m": {"type":"number","minimum":0,"maximum":0.001},
        "threshold_m": {"type":"number","minimum":0},
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
    "allOf": [{"if": {"properties": {"mode": {"const": "source_region"}}, "required": ["mode"]},
               "then": {"required": ["reference", "requested_facts"],
                        "properties": {"mode": {}, "region": {}, "region_ref": {}, "reference": {},
                            "requested_facts": {"const": ["surface_proximity"]}},
                        "oneOf": [{"required": ["region"], "not": {"required": ["region_ref"]}},
                                  {"required": ["region_ref"], "not": {"required": ["region"]}}],
                        "additionalProperties": False}},
              {"if": {"properties": {"mode": {"const": "active_observation"}}, "required": ["mode"]},
               "then": {"properties": {"mode": {}, "objects": {"maxItems": 1}, "task_query": {}, 'region_task': {}},
                        'not': {'required': ['objects', 'region_task']}, "additionalProperties": False}},
              {"if": {"properties": {"mode": {"const": "directory"}}, "required": ["mode"]},
               "then": {"properties": {"mode": {}}, "additionalProperties": False}},
              {"if": {"properties": {"mode": {"const": "surface_nearest"}}, "required": ["mode"]},
               "then": {"properties": {"mode": {}, "objects": {"maxItems": 1}}, "additionalProperties": False}},
              {"if": {"properties": {"mode": {"const": "surface_scan"}}, "required": ["mode"]},
               "then": {"required": ["threshold_m"], "properties": {"mode": {}, "threshold_m": {}},
                        "additionalProperties": False},
               "else": {"properties": {"threshold_m": {"exclusiveMinimum": 0, "maximum": 0.01}}}},
              {"if": {"anyOf": [{"properties": {"mode": {"const": "task"}}, "required": ["mode"]},
                                  {"required": ["target"]}, {"required": ["candidates"]}]},
               "then": {"required": ["mode", "requested_facts"], "properties": {"mode": {"const": "task"}}, "oneOf": [
                   {"required": ["objects"], "properties": {"target": False, "candidates": False}},
                   {"required": ["target", "candidates"],
                    "additionalProperties": False,
                    "properties": {"mode": {}, "target": {}, "candidates": {}, "geometry": {}, "requested_facts": {"items": {"enum": ["closed_solid_relation", "spatial_relation", "surface_proximity", "aabb"]},
                        "allOf": [{"contains": {"const": "surface_proximity"}},
                            {"anyOf": [{"contains": {"const": "closed_solid_relation"}},
                                       {"contains": {"const": "spatial_relation"}}]}]}}}
               ]}},
              {"if": {"required": ["geometry"]},
               "then": {"required": ["mode", "target", "candidates"],
                        "properties": {"mode": {"const": "task"}}}}],
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
            "Current Blender facts. Directory query={mode:directory} with include_image=false returns tight evaluated world bounds, AABB centers and an independent directory binding. Task set example: "
            "{\"include_image\":false,\"query\":{\"mode\":\"task\",\"target\":{\"name\":\"A\"},\"candidates\":[{\"name\":\"B\"}],\"requested_facts\":[\"closed_solid_relation\",\"surface_proximity\"]}}. "
            "Opt in to spatial_relation and surface_proximity for support-certified separation with closed-classification fallback. "
            "Unknown/duplicate rows remain. Complete penetration/nearest-separated sets require all relevant evidence; otherwise only known subsets are reported. "
            "Legacy objects pair/aabb supported. Global surface_nearest instead uses one query.objects selector without focal_id, "
            "or focal_id with query={\"mode\":\"surface_nearest\"}; session_id and include_image=false required. "
            "Complete means global nearest; partial means best-known. scene_revision/fingerprint bind this capture/source/revision; "
            "runtime_source_sha256 identifies code. Scene edits expire observations. Goals are caller criteria."
            " For all current scene mesh pairs use query={\"mode\":\"surface_scan\",\"threshold_m\":0.002}. "
            "This text-only scan includes hidden meshes, needs no selectors, includes threshold equality and reports coverage. "
            "Its unsigned triangle-surface distance describes surface proximity. Solid relations require separate facts. "
            "For surface_scan, omitted response_detail or brief returns a versioned compact table with readable names, "
            "object-table references, original distance_m and derived distance_mm. Explicit full returns detailed current "
            "evidence with witnesses. Combine observations using their scene/source binding."
            " For finite active observation use {\"query\":{\"mode\":\"active_observation\"},\"include_image\":true}; add query.objects=[{\"name\":\"Target\"}] for one visual target with scene occluders. Returns brief source-bound region locations, owned-pixel anchors and remaining unknowns with up to six 512px native PNGs. Optional query.task_query supplies one legacy task query over whole objects. Its task_result, requested values, witnesses and source bindings appear in both brief and full. Explicit response_detail=full includes diagnostics."
            " Optional query.region_task={area_min_m2,area_max_m2,normal_z_min} discovers whole-scene rectangular regions with inclusive area and directed unit-normal z limits, then obtains needed local evidence. It combines with task_query. Its region rows and image references identify each scope and actual frame, including repeated view names."
            " For an explicit evaluated triangle subset use query={mode:source_region,region:{object:{name:Target},source_triangle_indices:[0,1]},reference:{name:Reference},requested_facts:[surface_proximity]}. A returned top-level region_ref replaces region on later requests. Image depth uses the captured active view layer's effective visible meshes, retaining complete source indices. Measurements cover every selected triangle, including unseen portions and an explicitly selected hidden reference. Missing current display evidence or zero selected image pixels returns partial/evidence_insufficient with the measured task_result preserved. Brief and full return the source scope, display participation, distance, witness and native image references."
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
                    "description": "False returns text evidence without rendering. surface_scan defaults to false and accepts only false. mesh_structure diagnose requires false and reads only the registered target raw mesh; patch may explicitly request images. Other observation modes retain default true."},
            },
            "allOf": [{"if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"enum": ["active_observation", "source_region"]}}}}},
                "then": {"properties": {"task_instruction": {"const": ""}},
                         "not": {"anyOf": [{"required": [field]} for field in
                             ("focal_id", "reference_id", "goal", "scene_delta")]}}},
              {"if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"const": "directory"}}}}},
                "then": {"required": ["include_image"],
                         "properties": {"include_image": {"const": False}, "task_instruction": {"const": ""}},
                         "not": {"anyOf": [{"required": [field]} for field in
                             ("focal_id", "reference_id", "goal", "scene_delta")]}}}, {
                "if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"const": "surface_nearest"}}}}},
                "then": {"required": ["session_id", "include_image"],
                         "properties": {"include_image": {"const": False}},
                         "oneOf": [
                             {"required": ["focal_id"], "properties": {"query": {"not": {"required": ["objects"]}}}},
                             {"not": {"required": ["focal_id"]}, "properties": {"query": {"required": ["objects"]}}},
                         ]},
            }, {"if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"const": "surface_scan"}}}}},
                "then": {"properties": {"include_image": {"const": False},
                                         "response_detail": {"default": "brief"}},
                         "not": {"anyOf": [{"required": [field]} for field in
                             ("focal_id", "reference_id", "goal", "scene_delta")]}}},
            {"if": {"required": ["query"], "properties": {"query": {
                    "required": ["mode"], "properties": {"mode": {"enum": ["surface_scan", "active_observation", "source_region"]}}}}},
                "then": {"properties": {"response_detail": {"default": "brief"}}},
                "else": {"properties": {"response_detail": {"default": "full"}}}},
            {"if": {"required": ["query"], "properties": {"query": {
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
            'type': 'string', 'enum': ['full', 'brief'],
            'description': ('Optional display projection. surface_scan defaults to brief: a versioned table preserves '
                'all delivered matches, raw metre distances, derived millimetres, identities, scopes and unknowns. '
                'distance_mm uses a number, or an exact decimal string when binary64 millimetres overflow. '
                'Its object table covers matched endpoints. Full requests a new current observation with detailed '
                'witnesses; combine observations by scene/source binding. active_observation also defaults to brief, '
                'with all objects, region unknowns, actual pixel facts and native image references; full retains diagnostics. '
                'source_region defaults to brief with its complete selected-triangle measurement scope, witnesses and visibility. '
                'Other modes default to full; their brief '
                'omits named camera/raster diagnostics while preserving measurements and native images. '
                'Errors and unsupported projections retain the detailed response.'),
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
        'A supported transverse crossing includes its captured triangles and an approximate boundary location when publishable. '
        'Read-only: no images or actions.'),
    'inputSchema': {'type': 'object', 'properties': {
        'target': copy.deepcopy(SELECTOR_SCHEMA),
        'candidates': {'type': 'array', 'items': copy.deepcopy(SELECTOR_SCHEMA), 'minItems': 1, 'maxItems': 3},
        'geometry': copy.deepcopy(_TASK_GEOMETRY_SCHEMA),
        'include_aabb': {'type': 'boolean', 'default': False}},
        'required': ['target', 'candidates'], 'additionalProperties': False}}, {
    'name': 'human_eye_surface_nearest',
    'description': ('Find the nearest triangle surfaces, in metres, from one current Blender mesh '
        'to all other meshes in the scene. Complete results give global nearest ties; partial '
        'results give best-known candidates and unresolved coverage. Surface distance is unsigned, '
        'not penetration depth. Includes available closest points in world metres and independent '
        'witness/direction status for each best-known candidate. Read-only: no images or actions. '
        'Example: {"target":{"name":"Bracket"}}.'),
    'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                    'idempotentHint': True, 'openWorldHint': False},
    'inputSchema': {'type': 'object', 'properties': {
        'target': copy.deepcopy(SELECTOR_SCHEMA)},
        'required': ['target'], 'additionalProperties': False}}]


def _spatial_task_query(arguments):
    query = {'mode': 'task', 'target': arguments.get('target'), 'candidates': arguments.get('candidates'),
        'requested_facts': ['closed_solid_relation', 'surface_proximity']
            + (['aabb'] if arguments.get('include_aabb', False) else [])}
    if 'geometry' in arguments:
        query['geometry'] = arguments['geometry']
    return query


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
        'human_eye_spatial_relations': {'target', 'candidates', 'include_aabb', 'geometry'},
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
        if selected_query['mode'] == 'directory':
            if (arguments.get('include_image', True) or arguments.get('task_instruction', '')
                    or any(field in arguments for field in ('focal_id', 'reference_id', 'goal', 'scene_delta'))):
                raise ValueError('directory requires include_image=false and no instruction, pair, goal or scene_delta')
        if selected_query['mode'] == 'active_observation':
            if (arguments.get('task_instruction', '')
                    or any(field in arguments for field in ('focal_id', 'reference_id', 'goal', 'scene_delta'))):
                raise ValueError('active_observation accepts visual observation without instruction, pair, goal or scene_delta')
        if selected_query['mode'] == 'source_region':
            if (arguments.get('task_instruction', '')
                    or any(field in arguments for field in ('focal_id', 'reference_id', 'goal', 'scene_delta'))):
                raise ValueError('source_region accepts region and reference selectors only in query')
        if selected_query['mode'] == 'surface_nearest':
            if 'objects' in selected_query and 'focal_id' in arguments:
                raise ValueError('surface_nearest accepts query.objects or focal_id, not both')
            if (not arguments.get('session_id') or ('objects' not in selected_query and not arguments.get('focal_id'))
                    or arguments.get('include_image', True)
                    or any(arguments.get(key) is not None for key in ('goal', 'reference_id', 'scene_delta'))):
                raise ValueError('surface_nearest requires session_id, one target, include_image=false and no reference, goal or scene_delta')
        if selected_query['mode'] == 'surface_scan':
            if (arguments.get('include_image', False)
                    or any(field in arguments for field in ('focal_id', 'reference_id', 'goal', 'scene_delta'))):
                raise ValueError('surface_scan accepts only text observation without pair selectors, goal or scene_delta')
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
        context['certificate_scope'] = ('Certificate category with local evidence when available. '
            'Transverse evidence identifies current captured triangles and approximates their boundary crossing; '
            'the exact midpoint is on both boundaries, not in their shared volume interior. '
            'Neither a boundary location nor surface distance is penetration depth.')
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
    if 'geometry' in value:
        result['geometry'] = value['geometry']
    return result


def project_surface_scan_brief(value):
    """Project delivered scan facts into a detached, source-bound display table."""
    display_fields = ('display_encoding', 'objects', 'object_table_scope', 'object_reference',
                      'match_columns', 'match_metadata', 'match_exceptions',
                      'match_metadata_semantics', 'distance_mm_semantics', 'detail')
    if (type(value) is not dict or value.get('result_kind') != 'surface_scan'
            or value.get('status') not in ('complete', 'partial', 'unknown')
            or value.get('unit') != 'm' or value.get('coordinate_frame') != 'world'
            or type(value.get('matches')) is not list
            or any(field in value for field in display_fields)):
        return None
    objects = []
    object_refs = {}
    matches = []
    annotations = []
    for match in value['matches']:
        if (type(match) is not dict or type(match.get('objects')) is not list
                or len(match['objects']) != 2
                or type(match.get('distance_m')) not in (int, float)):
            return None
        distance = match['distance_m']
        if distance < 0 or type(distance) is float and not math.isfinite(distance):
            return None
        refs = []
        for obj in match['objects']:
            if (type(obj) is not dict or type(obj.get('id')) is not str or not obj['id']
                    or type(obj.get('name')) is not str):
                return None
            object_id = obj['id']
            if object_id not in object_refs:
                object_refs[object_id] = len(objects)
                objects.append(copy.deepcopy(obj))
            reference = object_refs[object_id]
            if json.dumps(objects[reference], ensure_ascii=False, allow_nan=False) != json.dumps(
                    obj, ensure_ascii=False, allow_nan=False):
                return None
            refs.append(reference)
        for key in ('point_a_world', 'point_b_world'):
            if key in match:
                point = match[key]
                if (type(point) is not list or len(point) != 3
                        or any(type(number) not in (int, float)
                               or type(number) is float and not math.isfinite(number)
                               for number in point)):
                    return None
        distance_mm = distance * 1000
        if type(distance_mm) is float and not math.isfinite(distance_mm):
            # A finite binary64 this large already has integral metre value.
            distance_mm = str(int(distance) * 1000)
        matches.append([match['objects'][0]['name'], match['objects'][1]['name'],
                        refs[0], refs[1], distance, distance_mm])
        annotations.append({key: copy.deepcopy(item) for key, item in match.items()
                            if key not in ('objects', 'distance_m', 'point_a_world', 'point_b_world')})
    encoded_annotations = [
        {key: json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
         for key, item in annotation.items()} for annotation in annotations]
    common = {}
    if annotations:
        common = {key: item for key, item in annotations[0].items()
                  if all(annotation.get(key) == encoded_annotations[0][key]
                         for annotation in encoded_annotations)}
    exceptions = []
    for index, annotation in enumerate(annotations):
        varying = {key: item for key, item in annotation.items() if key not in common}
        if varying:
            exceptions.append({'match_index': index, 'metadata': varying})
    result = {key: copy.deepcopy(item) for key, item in value.items() if key != 'matches'}
    result.update(display_encoding='surface-scan-task-table-v1', objects=objects,
        object_table_scope='matched_endpoints_only',
        object_reference='zero_based_index_in_objects; scoped_to_this_result_binding',
        match_columns=['object_a', 'object_b', 'object_a_ref', 'object_b_ref', 'distance_m', 'distance_mm'],
        matches=matches, match_metadata=common, match_exceptions=exceptions,
        match_metadata_semantics='common_fields_apply_to_every_match; merge_exceptions_by_zero_based_match_index',
        distance_mm_semantics='derived_display_only; number_or_exact_decimal_string_on_binary64_overflow; '
                              'threshold_membership_uses_original_distance_m',
        detail='response_detail=full requests a new current observation with witnesses; compare binding before combining')
    return result


def _contiguous_index_ranges(ordered_indices):
    ranges = []
    for index in ordered_indices:
        if ranges and index == ranges[-1][1] + 1:
            ranges[-1][1] = index
        else:
            ranges.append([index, index])
    return ranges


def _project_active_patch_support(patch_support, objects, regions):
    """Keep complete source-face denominators while displaying component ranges."""
    if set(patch_support) != {'schema', 'triangle_index_scope', 'all_triangles_participate_in_occlusion',
                              'objects', 'regions'} or patch_support['schema'] not in (
                                  'active-patch-support-v1', 'active-patch-support-v2'):
        raise ValueError('unsupported_active_patch_support')
    mapping = patch_support['regions']
    if len(mapping) != len(regions):
        raise ValueError('active_patch_region_mapping_mismatch')
    region_counts, region_ranges, region_faces = [], [], [set() for _ in objects]
    for source, region in zip(mapping, regions):
        if (set(source) != {'roi_id', 'object_index', 'triangle_indices'}
                or source['roi_id'] != region['roi_id'] or type(source['object_index']) is not int
                or source['object_index'] != region['object_index']):
            raise ValueError('active_patch_region_mapping_mismatch')
        faces = source['triangle_indices']
        indices = set(faces)
        owned = region_faces[region['object_index']]
        if (not indices or len(indices) != len(faces) or owned & indices
                or any(type(index) is not int for index in faces)):
            raise ValueError('active_patch_region_triangle_overlap')
        owned.update(indices)
        region_counts.append(len(indices))
        region_ranges.append(_contiguous_index_ranges(sorted(indices)))
    support_rows, component_rows = [], []
    sources = patch_support['objects']
    object_fields = {'object_index', 'host_id', 'instance_id', 'object_name'}
    partition_fields = {'source_triangle_count', 'supported_triangle_count', 'supported_triangle_indices',
                        'unsupported_triangle_count', 'unsupported_components', 'support_status'}
    if len(sources) != len(objects):
        raise ValueError('active_patch_object_mapping_mismatch')
    for index, source in enumerate(sources):
        occluder = source.get('coverage_role') == 'occluder_only'
        if (set(source) != object_fields | partition_fields | ({'coverage_role'} if occluder else set())
                or occluder and patch_support['schema'] != 'active-patch-support-v2'
                or type(source['object_index']) is not int
                or any(source[key] != objects[index][key] for key in object_fields)
                or any(type(source[key]) is not int or source[key] < 0 for key in
                       ('source_triangle_count', 'supported_triangle_count', 'unsupported_triangle_count'))):
            raise ValueError('active_patch_object_mapping_mismatch')
        total = source['source_triangle_count']
        supported = set(source['supported_triangle_indices'])
        rejected = set()
        for component_index, component in enumerate(source['unsupported_components']):
            if (set(component) != {'triangle_indices', 'reason', 'status'}
                    or component['status'] != 'unknown' or type(component['reason']) is not str
                    or not component['reason']):
                raise ValueError('active_patch_component_mismatch')
            faces = component['triangle_indices']
            indices = set(faces)
            if (not indices or len(indices) != len(faces) or rejected & indices
                    or any(type(face) is not int for face in faces)):
                raise ValueError('active_patch_component_mismatch')
            rejected.update(indices)
            component_rows.append([index, component_index, len(indices), component['reason'],
                                   component['status'], _contiguous_index_ranges(sorted(indices))])
        expected_status = ('occluder_only' if occluder else 'unsupported' if not supported else
                           'partially_supported' if rejected else 'fully_supported')
        expected_faces = set() if occluder else set(range(total))
        if (len(supported) != len(source['supported_triangle_indices'])
                or any(type(face) is not int for face in source['supported_triangle_indices'])
                or supported != region_faces[index] or supported & rejected
                or supported | rejected != expected_faces
                or source['supported_triangle_count'] != len(supported)
                or source['unsupported_triangle_count'] != len(rejected)
                or source['support_status'] != expected_status):
            raise ValueError('active_patch_triangle_denominator_mismatch')
        support_rows.append([index, total, len(supported), len(rejected), expected_status])
    result = {key: patch_support[key] for key in
              ('schema', 'triangle_index_scope', 'all_triangles_participate_in_occlusion')}
    result['object_support'] = {
        'columns': ['object_index', 'source_triangle_count', 'supported_triangle_count',
                    'unsupported_triangle_count', 'support_status'],
        'rows': support_rows,
    }
    if component_rows:
        result['unsupported_components'] = {
            'columns': ['object_index', 'component_index', 'triangle_count', 'reason', 'status',
                        'triangle_index_ranges'],
            'rows': component_rows,
        }
    return result, region_counts, region_ranges


def _valid_region_location_vector(values):
    if type(values) is not list or len(values) != 3:
        return False
    for value in values:
        if type(value) not in (int, float, str) or type(value) is float and not math.isfinite(value):
            return False
        if type(value) is str:
            try:
                Fraction(value)
            except (ValueError, ZeroDivisionError):
                return False
    return True


def _valid_visible_pixel_location(pixel, size):
    bounds, anchor = pixel['visible_pixel_bounds'], pixel['visible_pixel_anchor']
    if pixel['visible_surface_pixels'] == 0:
        return bounds is None and anchor is None
    if (type(bounds) is not list or len(bounds) != 4 or type(anchor) is not list or len(anchor) != 2
            or any(type(value) is not int for value in bounds + anchor)):
        return False
    xmin, ymin, xmax, ymax = bounds
    return (0 <= xmin <= anchor[0] <= xmax < size[0]
            and 0 <= ymin <= anchor[1] <= ymax < size[1])


def _project_active_inspection(facts, regions, pixel_references):
    inspection = facts['inspection']
    if (set(inspection) != {'schema', 'scope', 'state', 'stop_reason', 'view_names', 'counts'}
            or inspection['schema'] != 'active-inspection-v1'
            or inspection['scope'] != facts['coverage']['scope']):
        raise ValueError('active_inspection_contract')
    views = inspection['view_names']
    if (type(views) is not list or not views or len(set(views)) != len(views)
            or any(type(view) is not str for view in views)):
        raise ValueError('active_inspection_view_pool')
    view_indices = {name: index for index, name in enumerate(views)}
    if not set(facts['coverage']['observed_views']) <= set(views):
        raise ValueError('active_inspection_observed_pool')
    rows = facts['region_evidence']
    if type(rows) is not list or len(rows) != len(regions):
        raise ValueError('active_region_evidence_count')
    counts = {'supported': len(regions), 'covered': 0, 'unobserved': 0,
              'pending_geometric_candidate': 0, 'no_geometric_complete_candidate': 0,
              'pixel_insufficient': 0, 'covered_without_witness': 0}
    no_candidate_reasons = {'no_front_facing_candidate', 'positive_area_occlusion_all_front_views',
                            'no_complete_geometric_candidate'}
    covered_ids = set(facts['coverage']['covered_roi_ids'])
    unavailable_ids = set(facts['coverage']['candidate_pool_uncovered_roi_ids'])
    view_reason_names = {'back_facing', 'edge_on', 'outside_frustum', 'positive_area_occlusion',
                         'unobserved_geometric_candidate', 'pixel_evidence_insufficient'}
    compact, groups, group_indices = [], [], {}
    for index, (row, region) in enumerate(zip(rows, regions)):
        if (set(row) != {'roi_id', 'complete_witness', 'unobserved_reason', 'view_reasons'}
                or row['roi_id'] != region['roi_id'] or type(row['view_reasons']) is not dict):
            raise ValueError('active_region_evidence_identity')
        witness = row['complete_witness']
        if (region['status'] == 'covered') != (region['roi_id'] in covered_ids):
            raise ValueError('active_region_evidence_coverage')
        if region['status'] == 'covered':
            counts['covered'] += 1
            if (type(witness) is not dict or set(witness) != {'view_name', 'pixel_row_index'}
                    or type(witness['pixel_row_index']) is not int or row['unobserved_reason'] is not None
                    or row['view_reasons']):
                raise ValueError('active_complete_witness_required')
            pixel_index, owner_index, pixel = pixel_references[(witness['view_name'], witness['pixel_row_index'])]
            if (owner_index != index or pixel['readable'] is not True or pixel['front_facing'] is not True
                    or pixel['visible_surface_pixels'] < pixel['minimum_surface_pixels']
                    or pixel['contrasting_boundary_pixels'] < pixel['minimum_boundary_pixels']):
                raise ValueError('active_complete_witness_pixel_binding')
            compact.append([pixel_index, None, []])
            continue
        if region['status'] != 'unknown' or witness is not None:
            raise ValueError('active_unobserved_evidence_status')
        counts['unobserved'] += 1
        reason = row['unobserved_reason']
        classifications = set(row['view_reasons'])
        if ((reason in no_candidate_reasons) != (region['roi_id'] in unavailable_ids)
                or (reason == 'unobserved_geometric_candidates') != ('unobserved_geometric_candidate' in classifications)
                or (reason == 'pixel_evidence_insufficient' and 'pixel_evidence_insufficient' not in classifications)
                or (reason in no_candidate_reasons and classifications & {
                    'unobserved_geometric_candidate', 'pixel_evidence_insufficient'})
                or (reason == 'no_front_facing_candidate' and not classifications <= {'back_facing', 'edge_on'})
                or (reason == 'positive_area_occlusion_all_front_views'
                    and ('positive_area_occlusion' not in classifications
                         or not classifications <= {'back_facing', 'edge_on', 'positive_area_occlusion'}))):
            raise ValueError('active_unobserved_reason_classification')
        if reason in no_candidate_reasons:
            counts['no_geometric_complete_candidate'] += 1
        elif reason == 'unobserved_geometric_candidates':
            counts['pending_geometric_candidate'] += 1
        elif reason == 'pixel_evidence_insufficient':
            counts['pixel_insufficient'] += 1
        else:
            raise ValueError('active_unobserved_reason')
        references, seen = [], []
        for classification, names in row['view_reasons'].items():
            if (classification not in view_reason_names or type(names) is not list or not names
                    or len(set(names)) != len(names)):
                raise ValueError('active_unobserved_view_reason')
            indices = tuple(view_indices[name] for name in names)
            seen.extend(names)
            key = classification, indices
            if key not in group_indices:
                group_indices[key] = len(groups)
                groups.append([classification, list(indices)])
            references.append(group_indices[key])
        if len(seen) != len(views) or set(seen) != set(views):
            raise ValueError('active_unobserved_view_partition')
        compact.append([None, reason, references])
    if (inspection['counts'] != counts
            or any(type(value) is not int for value in inspection['counts'].values())
            or counts['covered'] != len(facts['coverage']['covered_roi_ids'])
            or counts['unobserved'] != len(facts['coverage']['unresolved_roi_ids'])):
        raise ValueError('active_inspection_counts')
    if not regions:
        expected = 'no_supported_regions', 'no_supported_regions'
    elif not facts['coverage']['observed_views']:
        expected = 'prediction_only', 'actual_observation_required'
    elif counts['pending_geometric_candidate']:
        expected = 'observation_required', 'unobserved_geometric_candidates_remain'
    elif not counts['unobserved']:
        expected = 'all_supported_regions_observed', 'all_supported_regions_observed'
    else:
        expected = 'finite_pool_exhausted', 'no_unobserved_geometric_candidates'
    if (inspection['state'], inspection['stop_reason']) != expected:
        raise ValueError('active_inspection_stop_reason')
    return compact, {'columns': ['reason', 'view_indices'], 'rows': groups}


def _unique_rows_by_roi(rows):
    by_roi = {}
    if not isinstance(rows, (list, tuple)):
        return by_roi
    for row in rows:
        roi = row.get('roi_id') if isinstance(row, dict) else None
        if isinstance(roi, str):
            by_roi[roi] = None if roi in by_roi else row
    return by_roi


def _shortfall_pixel_matches(pixel, task_row, observation):
    if pixel is None or pixel.get('readable') is not False or pixel.get('front_facing') is not True:
        return False
    readable = observation.get('readable_roi_ids')
    if (pixel.get('view') != observation['view_name']
            or not isinstance(readable, list) or pixel['roi_id'] in readable
            or type(pixel.get('object_index')) is not int
            or any(pixel.get(key) != task_row[key] for key in ('object_index', 'object_name', 'host_id'))):
        return False
    surface = pixel.get('visible_surface_pixels')
    boundary = pixel.get('contrasting_boundary_pixels')
    valid = (type(surface) is int and type(boundary) is int and 0 <= boundary <= surface <= 512 * 512
            and (surface < 16 or boundary < 4)
            and all(type(pixel.get(key)) is int and pixel[key] == limit for key, limit in
                    (('minimum_surface_pixels', 16), ('minimum_boundary_pixels', 4),
                     ('minimum_rgb_boundary_contrast', 24)))
            and {'visible_pixel_bounds', 'visible_pixel_anchor'} <= pixel.keys()
            and _valid_visible_pixel_location(pixel, [512, 512]))
    if not valid or surface == 0:
        return valid
    xmin, ymin, xmax, ymax = pixel['visible_pixel_bounds']
    return surface <= (xmax - xmin + 1) * (ymax - ymin + 1)


def _region_task_shortfalls(scope, regions, observations, frame_indices):
    by_roi = _unique_rows_by_roi(scope['facts'].get('region_evidence', ()))
    pending = {}
    for roi, (index, row) in regions.items():
        evidence = by_roi.get(roi)
        reasons = row.get('view_reasons')
        if (evidence is not None and evidence.get('unobserved_reason') == 'pixel_evidence_insufficient'
                and evidence.get('complete_witness') is None and isinstance(reasons, dict)
                and evidence.get('view_reasons') == reasons):
            views = reasons.get('pixel_evidence_insufficient')
            if type(views) is list:
                pending[roi] = (index, row, views)
    shortfalls = []
    for identity in scope['frame_refs']:
        if not pending:
            break
        observation = observations[identity]
        view = observation['view_name']
        pixels = _unique_rows_by_roi(observation.get('pixel_rows', ()))
        for roi, pixel in pixels.items():
            if roi not in pending:
                continue
            index, row, views = pending[roi]
            if view not in views or not _shortfall_pixel_matches(pixel, row, observation):
                continue
            shortfalls.append([index, frame_indices[identity], pixel['visible_surface_pixels'],
                               pixel['contrasting_boundary_pixels']])
            pending.pop(roi)
    return shortfalls


def _project_region_task_blockers(packet, binding, support, global_facts, region_rows):
    """Bind sparse geometric witnesses to the current whole-scene task."""
    if (type(packet) is not dict or set(packet) != {
            'scope_id', 'binding_sha256', 'source_binding_sha256', 'camera_identity', 'rows'}
            or packet['scope_id'] != 'global'
            or any(packet[key] != binding[key] for key in
                   ('binding_sha256', 'source_binding_sha256', 'camera_identity'))
            or type(packet['rows']) is not list or not packet['rows']):
        raise ValueError('active_region_task_blocker_binding')
    evidence_by_roi = _unique_rows_by_roi(global_facts['region_evidence'])
    camera_order = binding['camera_policy']['order']
    expected = []
    for region_index, region in enumerate(region_rows):
        if region['reason'] != 'positive_area_occlusion_all_front_views':
            continue
        roi = region['roi_id']
        global_evidence = evidence_by_roi.get(roi)
        if (global_evidence is None
                or global_evidence['unobserved_reason'] != 'positive_area_occlusion_all_front_views'):
            continue
        reasons = region['view_reasons']
        if (region['status'] != 'unknown' or region['complete_witness'] is not None
                or global_evidence['complete_witness'] is not None or reasons != global_evidence['view_reasons']
                or not set(reasons) <= {'back_facing', 'edge_on', 'positive_area_occlusion'}
                or any(type(views) is not list for views in reasons.values())):
            raise ValueError('active_region_task_blocker_classification')
        views = [view for group in reasons.values() for view in group]
        occluded = reasons.get('positive_area_occlusion')
        if (not occluded or len(views) != len(camera_order) or set(views) != set(camera_order)
                or occluded != [view for view in camera_order if view in occluded]):
            raise ValueError('active_region_task_blocker_directions')
        expected.extend((region_index, region, view) for view in occluded)
    if len(packet['rows']) != len(expected):
        raise ValueError('active_region_task_blocker_denominator')
    compact = []
    objects = binding['objects']
    for witness, (region_index, region, view) in zip(packet['rows'], expected):
        if (type(witness) is not dict or set(witness) != {
                'roi_id', 'view_name', 'blocker_object_index', 'source_triangle_index', 'blocker_host_id',
                'blocker_instance_id', 'triangle_geometry_id', 'overlap_area_screen_exact'}
                or (witness['roi_id'], witness['view_name']) != (region['roi_id'], view)):
            raise ValueError('active_region_task_blocker_region_view')
        index, face = witness['blocker_object_index'], witness['source_triangle_index']
        if type(index) is not int or not 0 <= index < len(objects) or index >= len(support['objects']):
            raise ValueError('active_region_task_blocker_object')
        host, source = objects[index], support['objects'][index]
        if (source['object_index'] != index or source['host_id'] != host['host_id']
                or source['instance_id'] != host['instance_id']
                or witness['blocker_host_id'] != host['host_id']
                or witness['blocker_instance_id'] != host['instance_id']
                or type(face) is not int or not 0 <= face < source['source_triangle_count']
                or index == region['object_index'] and face in region['source_triangle_indices']):
            raise ValueError('active_region_task_blocker_source')
        digest, area = witness['triangle_geometry_id'], witness['overlap_area_screen_exact']
        try:
            positive = type(area) is str and Fraction(area) > 0
        except (ValueError, ZeroDivisionError):
            positive = False
        if not positive or type(digest) is not str or len(digest) != 64 or any(
                char not in '0123456789abcdef' for char in digest):
            raise ValueError('active_region_task_blocker_positive_area')
        compact.append([region_index, view, index, face])
    return compact


def _project_region_task_measurement(task, parent, support, regions, query):
    """Share a whole-object measurement's proven parent; otherwise keep its legacy result."""
    from .active_observation import fingerprint
    from .task_query import validate_task_query

    def digest(value):
        return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

    try:
        if (query is None or task['schema_version'] != 'task-query-v3' or task['result_kind'] != 'task_query'
                or task['status'] != 'observed' or task['pair_order'] != 'A_to_B'
                or task['unit'] != parent['unit'] or task['coordinate_frame'] != parent['coordinate_frame']
                or task['execution_authority'] is not False or set(task['facts']) != {'surface_proximity'}
                or task['facts']['surface_proximity']['status'] != 'measured'):
            return None
        query = validate_task_query(query)
        if query['mode'] != 'task' or query['requested_facts'] != ['surface_proximity']:
            return None

        binding = task['binding']
        shared = {key: parent[key] for key in ('source', 'runtime_source_sha256', 'source_check_scope',
                                               'disk_status', 'source_status') if key in parent}
        if (set(binding) != set(shared) | {'candidate_count', 'selected_count', 'capture_scope',
                'scene_revision', 'scene_fingerprint', 'objects', 'observation_source'}
                or any(binding[key] != item for key, item in shared.items())
                or not digest(binding['scene_fingerprint'])):
            return None
        source = binding['observation_source']
        capture = source['capture_state']
        parent_capture = parent['capture_state']
        generation_keys = {'instance_id', 'epoch', 'revision'}
        if (set(source) != {'schema', 'measurement_scope', 'capture_scope', 'capture_state', 'objects',
                'parent_binding_sha256', 'parent_source_binding_sha256', 'parent_capture_scope'}
                or source['schema'] != 'active-observation-task-source-v1'
                or source['measurement_scope'] != 'whole_objects'
                or source['capture_scope'] != binding['capture_scope']
                or binding['capture_scope'] != 'observation_task_objects'
                or source['parent_binding_sha256'] != parent['binding_sha256']
                or source['parent_source_binding_sha256'] != parent['source_binding_sha256']
                or source['parent_capture_scope'] != parent['capture_scope']
                or set(capture) != generation_keys | {'selection_key'} or set(capture) != set(parent_capture)
                or type(capture['instance_id']) is not str or not capture['instance_id']
                or any(type(capture[key]) is not int or capture[key] < 0 for key in ('epoch', 'revision'))
                or any(type(capture[key]) is not type(parent_capture[key]) or capture[key] != parent_capture[key]
                       for key in generation_keys)):
            return None
        selection_key = capture['selection_key']
        if not digest(selection_key) or binding['scene_revision'] != 'observation-task:' + selection_key:
            return None

        directory = parent['objects']
        by_id = {row['host_id']: row for row in directory}
        selected, sources = binding['objects'], source['objects']
        if (len(by_id) != len(directory) or type(binding['candidate_count']) is not int
                or binding['candidate_count'] != len(directory) or type(binding['selected_count']) is not int
                or binding['selected_count'] != 2 or len(selected) != 2 or len(sources) != 2
                or len(query['objects']) != 2):
            return None
        ordered = []
        for bound, selector in zip(selected, query['objects'], strict=True):
            obj = by_id[bound['object_id']]
            if bound != {'object_id': obj['host_id'], 'name': obj['object_name']}:
                return None
            if 'id' in selector:
                if selector['id'] != obj['host_id']:
                    return None
            elif (selector['name'] != obj['object_name']
                    or sum(item['object_name'] == selector['name'] for item in directory) != 1):
                return None
            ordered.append(obj['object_index'])

        columns = ('object_index', 'geometry_id', 'source_triangle_count',
                   'source_triangle_index_ranges', 'ordered_geometry_sha256')
        rows = []
        for item in sources:
            idx, alias, count = item['observation_object_index'], item['geometry_id'], item['source_triangle_count']
            if (set(item) != (set(columns) - {'object_index'}) | {'observation_object_index', 'object_id', 'instance_id'}
                    or type(idx) is not int or not 0 <= idx < len(directory)
                    or type(count) is not int or count <= 0 or type(alias) is not str
                    or not alias.startswith('geometry:') or not digest(alias[len('geometry:'):])
                    or not digest(item['ordered_geometry_sha256'])
                    or item['source_triangle_index_ranges'] != [[0, count - 1]]):
                return None
            obj, complete = directory[idx], support['objects'][idx]
            if (item['object_id'] != obj['host_id'] or item['instance_id'] != obj['instance_id']
                    or complete['source_triangle_count'] != count
                    or any(complete[key] != obj[key] for key in ('object_index', 'host_id', 'instance_id'))
                    or any(row['source']['ordered_geometry_sha256'] != item['ordered_geometry_sha256']
                           for row in regions if row['object_index'] == idx)):
                return None
            rows.append([idx, *(item[key] for key in columns[1:])])
        # The producer's selection key binds the actual ordered selectors and source rows,
        # including geometry aliases and ordered mesh digests for objects without a region.
        if (len(set(ordered)) != 2 or set(ordered) != {row[0] for row in rows}
                or fingerprint(['observation_task', parent['source_binding_sha256'], query, sources]) != selection_key):
            return None

        compact = dict(capture_scope=binding['capture_scope'], measurement_scope=source['measurement_scope'],
                       selection_key=selection_key, scene_fingerprint=binding['scene_fingerprint'],
                       object_indices=ordered, sources={'columns': list(columns), 'rows': rows})
        return copy.deepcopy({**task, 'schema_version': 'active-observation-region-task-result-v1',
                              'binding': compact})
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def _project_region_task_brief(value, *, validate_only=False, observation_task_query=None):
    """Validate current evidence and project the versioned region task tables."""
    from .query_policy import validate_region_task

    def require(condition, reason):
        if not condition:
            raise ValueError('active_region_task_' + reason)

    binding, facts = value['binding'], value['facts']
    task = facts['region_task']
    include_pixel_shortfalls = not validate_only and value['observation_status'] == 'region_task_observed'
    require(task['schema'] == 'active-region-task-v1', 'schema')
    require(validate_region_task(task['conditions']) == task['conditions'], 'conditions')
    require(binding['capture_scope'] == 'complete_scene_meshes', 'whole_scene_source')
    scopes, constructed, selected = value['scopes'], value['constructed_frames'], value['frames']
    require(type(scopes) is list and type(constructed) is list and type(selected) is list, 'collections')
    by_scope = {scope['scope_id']: scope for scope in scopes}
    require(len(by_scope) == len(scopes) and 'global' in by_scope, 'unique_scopes')
    global_binding = {key: item for key, item in by_scope['global']['binding'].items() if key != 'camera_specification'}
    require(global_binding == {key: item for key, item in binding.items() if key != 'camera_specification'}, 'global_binding')
    by_frame = {frame['frame_identity']: frame for frame in constructed}
    by_image = {frame['image_ref']: frame for frame in constructed}
    require(len(by_frame) == len(constructed) == len(by_image), 'unique_constructed_frames')
    frame_indices = {identity: index for index, identity in enumerate(by_frame)}
    selected_indices = {frame['frame_identity']: index for index, frame in enumerate(selected)}
    require(len(selected_indices) == len(selected) <= 6, 'selected_frame_count')
    for frame in selected:
        require(by_frame.get(frame['frame_identity']) == frame, 'selected_frame_original')
    objects = binding['objects']
    object_columns = ['object_index', 'host_id', 'instance_id', 'object_name']
    require(type(objects) is list and all(obj['object_index'] == index for index, obj in enumerate(objects)),
            'parent_object_order')
    observations = {}
    local_scope_by_roi = {}
    scope_rows = []
    for scope in scopes:
        scope_id, source = scope['scope_id'], scope['binding']
        require(source['document_epoch'] == binding['document_epoch']
                and source['scene_revision'] == binding['scene_revision']
                and source['capture_state'] == binding['capture_state']
                and source['objects'] == objects
                and source['geometry_identity'] == binding['geometry_identity'], 'scope_current_source')
        for key in ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'):
            require(source.get(key) == binding.get(key), 'scope_runtime_source')
        if scope_id != 'global':
            require(source['schema'] == 'active-observation-region-source-v1'
                    and source['parent_binding_sha256'] == binding['binding_sha256']
                    and source['parent_source_binding_sha256'] == binding['source_binding_sha256'],
                    'scope_parent_binding')
        scope_frames = [frame for frame in constructed if frame['scope_id'] == scope_id]
        require(scope['frame_refs'] == [frame['frame_identity'] for frame in scope_frames], 'scope_frame_order')
        require(len({frame['view_name'] for frame in scope_frames}) == len(scope_frames), 'scope_view_unique')
        scope_facts = scope['facts']
        if include_pixel_shortfalls and scope_id != 'global':
            location = scope_facts.get('scope')
            roi = location.get('roi_id') if isinstance(location, dict) else None
            if isinstance(roi, str):
                local_scope_by_roi[roi] = None if roi in local_scope_by_roi else scope_id
        require(scope_facts['scene_identity'] == source['geometry_identity']
                and scope_facts['candidate_identity'] == source['camera_identity'], 'scope_fact_identity')
        require(len(scope_facts['observations']) == len(scope_frames), 'scope_actual_observations')
        for frame, observation in zip(scope_frames, scope_facts['observations']):
            require(frame['scene_identity'] == source['geometry_identity']
                    and frame['candidate_identity'] == source['camera_identity']
                    and frame['camera_identity'] == source['camera_identity']
                    and frame['host_binding_sha256'] == source['binding_sha256']
                    and frame['source_revision'] == source['scene_revision'], 'frame_scope_binding')
            require(observation['scope_id'] == scope_id
                    and observation['frame_identity'] == frame['frame_identity']
                    and all(observation[key] == frame[key] for key in
                            ('view_name', 'image_ref', 'image_path', 'image_sha256')), 'frame_observation_binding')
            observations[frame['frame_identity']] = observation
        scope_rows.append([scope_id, source['camera_identity'], source['binding_sha256'],
                           len(scope_frames), len(scope_facts['coverage']['covered_roi_ids'])])
    require(set(frame['scope_id'] for frame in constructed) <= set(by_scope), 'frame_scope_exists')
    require(facts['scope'] == by_scope['global']['facts']['scope'], 'global_scope_denominator')
    support = facts['scope']['patch_support']
    source_triangles = {(row['object_index'], row['roi_id']): row['triangle_indices'] for row in support['regions']}
    region_rows = task['rows']
    require(len({row['roi_id'] for row in region_rows}) == len(region_rows), 'unique_task_regions')
    world_fields = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
    compact_rows, witness_rows = [], []
    shortfall_rows = {}
    for region_index, row in enumerate(region_rows):
        index = row['object_index']
        require(type(index) is int and 0 <= index < len(objects), 'task_object_index')
        host = objects[index]
        require(all(row[key] == host[key] for key in ('host_id', 'instance_id', 'object_name')), 'task_host_identity')
        require(all(_valid_region_location_vector(row[key]) for key in world_fields), 'task_world_location')
        faces = row['source_triangle_indices']
        require(faces == source_triangles[(index, row['roi_id'])], 'task_source_triangles')
        source = row['source']
        require(source['document_epoch'] == binding['document_epoch']
                and source['scene_revision'] == binding['scene_revision']
                and source['capture_state'] == binding['capture_state']
                and source['parent_binding_sha256'] == binding['binding_sha256']
                and source['parent_source_binding_sha256'] == binding['source_binding_sha256']
                and all(source[key] == row[key] for key in
                        ('object_index', 'host_id', 'instance_id', 'source_triangle_indices')),
                'task_source_binding')
        digest = source['ordered_geometry_sha256']
        require(type(digest) is str and len(digest) == 64 and all(char in '0123456789abcdef' for char in digest),
                'ordered_geometry_digest')
        witness = row['complete_witness']
        if witness is not None:
            frame = by_frame[witness['frame_identity']]
            scope = by_scope[witness['scope_id']]
            require(frame['scope_id'] == witness['scope_id']
                    and frame['image_ref'] == witness['image_ref']
                    and frame['view_name'] == witness['view_name'], 'witness_frame')
            require(witness['selected_for_delivery'] is (frame['frame_identity'] in selected_indices), 'witness_delivery')
            if scope['scope_id'] != 'global':
                require(scope['binding']['region_source'] == source, 'witness_source')
            observation = observations[frame['frame_identity']]
            pixel_index = witness['pixel_row_index']
            if not validate_only:
                require(type(pixel_index) is int and 0 <= pixel_index < len(observation['pixel_rows']),
                        'witness_pixel_row_index')
            pixel = observation['pixel_rows'][pixel_index]
            evidence = next(item for item in scope['facts']['region_evidence'] if item['roi_id'] == row['roi_id'])
            require(row['status'] == 'covered' and pixel['roi_id'] == row['roi_id']
                    and pixel['readable'] is True and row['roi_id'] in observation['readable_roi_ids']
                    and evidence['complete_witness'] == {'view_name': witness['view_name'],
                        'pixel_row_index': witness['pixel_row_index']}, 'complete_readable_witness')
            require(pixel['visible_surface_pixels'] >= pixel['minimum_surface_pixels'] == 16
                    and pixel['contrasting_boundary_pixels'] >= pixel['minimum_boundary_pixels'] == 4
                    and pixel['minimum_rgb_boundary_contrast'] == 24
                    and pixel['front_facing'] is True
                    and _valid_visible_pixel_location(pixel, [512, 512]), 'witness_pixel_gates')
            if not validate_only:
                witness_rows.append([region_index, frame_indices[frame['frame_identity']], pixel_index,
                    pixel['visible_surface_pixels'], pixel['contrasting_boundary_pixels'],
                    copy.deepcopy(pixel['visible_pixel_bounds']), copy.deepcopy(pixel['visible_pixel_anchor'])])
        else:
            require(row['status'] != 'covered', 'covered_requires_witness')
            if (include_pixel_shortfalls and row['status'] == 'unknown'
                    and row['reason'] == 'pixel_evidence_insufficient'):
                roi = row['roi_id']
                scope_id = local_scope_by_roi.get(roi, 'global')
                if scope_id == 'global' or (scope_id is not None
                        and by_scope[scope_id]['binding'].get('region_source') == source
                        and by_scope[scope_id]['facts']['scope'].get('source') == source):
                    shortfall_rows.setdefault(scope_id, {})[roi] = (region_index, row)
        if not validate_only:
            require(bool(faces) and all(type(face) is int and face >= 0 for face in faces)
                    and all(left < right for left, right in zip(faces, faces[1:])), 'task_source_triangle_order')
            compact_rows.append([index, row['roi_id'], *(copy.deepcopy(row[key]) for key in world_fields),
                                 _contiguous_index_ranges(faces), digest, row['status'], row['reason'],
                                 copy.deepcopy(row['view_reasons'])])
    if 'task_result' in value:
        task_result = value['task_result']
        task_source = task_result['binding']['observation_source']
        require(task_source['measurement_scope'] == 'whole_objects'
                and task_source['parent_binding_sha256'] == binding['binding_sha256']
                and task_source['parent_source_binding_sha256'] == binding['source_binding_sha256']
                and task_source['parent_capture_scope'] == binding['capture_scope'], 'whole_object_task_binding')
    blocker_rows = None
    if 'blocker_evidence' in task:
        blocker_rows = _project_region_task_blockers(task['blocker_evidence'], binding, support,
                                                    by_scope['global']['facts'], region_rows)
    if validate_only:
        return None
    shortfalls = []
    for scope_id, rows in shortfall_rows.items():
        shortfalls.extend(_region_task_shortfalls(by_scope[scope_id], rows, observations, frame_indices))
    shortfalls.sort(key=lambda item: item[0])
    scope_indices = {scope_id: index for index, scope_id in enumerate(by_scope)}
    frame_rows = []
    for frame in constructed:
        block = selected_indices.get(frame['frame_identity'])
        frame_rows.append([scope_indices[frame['scope_id']], frame['view_name'], frame['frame_identity'],
                           frame['image_ref'], frame['image_sha256'], None if block is None else block + 1])
    result = {key: copy.deepcopy(value[key]) for key in
              ('status', 'result_kind', 'observation_status', 'session_id', 'read_only', 'execution_authority')}
    compact_binding = {key: copy.deepcopy(item) for key, item in binding.items()
                       if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')}
    result.update(schema='active-observation-region-task-brief-v2', index_base=0,
        binding=compact_binding,
        objects={'columns': object_columns, 'rows': [[obj[key] for key in object_columns] for obj in objects]},
        region_task=dict(schema=task['schema'], conditions=copy.deepcopy(task['conditions']),
            summary=copy.deepcopy(task['summary']),
            columns=['object_index', 'roi_id', *world_fields, 'source_triangle_index_ranges',
                     'ordered_geometry_sha256', 'status', 'reason', 'view_reasons'], rows=compact_rows),
        scopes={'columns': ['scope_id', 'camera_identity', 'binding_sha256', 'constructed_frame_count',
                            'locally_covered_region_count'], 'rows': scope_rows},
        frames={'columns': ['scope_index', 'view_name', 'frame_identity', 'image_ref', 'image_sha256',
                            'native_content_block_index'], 'rows': frame_rows},
        witnesses={'columns': ['region_index', 'frame_index', 'pixel_row_index', 'visible_surface_pixels',
                               'contrasting_boundary_pixels', 'visible_pixel_bounds', 'visible_pixel_anchor'],
                   'rows': witness_rows},
        pixel_shortfalls={'columns': ['region_index', 'frame_index', 'visible_surface_pixels',
                                      'contrasting_boundary_pixels'], 'rows': shortfalls},
        pixel_requirements={'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4,
                            'minimum_rgb_boundary_contrast': 24},
        image_delivery=copy.deepcopy(value['image_delivery']),
        source_triangle_index_ranges_semantics='Zero-based inclusive ranges in current object-local triangle order.',
        frame_index_semantics='Zero-based indices in the frame table. A null MCP content index means no image was delivered.')
    if blocker_rows is not None:
        result['blocker_evidence'] = {
            'scope_index': scope_indices['global'],
            'columns': ['region_index', 'view_name', 'blocker_object_index', 'source_triangle_index'],
            'rows': blocker_rows,
            'meaning': ('One current object-local evaluated triangle with positive-area occlusion per listed view. '
                        'Nearest depth, other blockers, and total occlusion are unspecified.'),
        }
    if 'task_result' in value:
        original = value['task_result']
        compact_task = _project_region_task_measurement(
            original, binding, support, region_rows, observation_task_query)
        result['task_result'] = compact_task if compact_task is not None else copy.deepcopy(original)
    return result


def project_active_observation_brief(value):
    """Deduplicate one complete active result using versioned, local table indices.

    Empty tables and coverage collections are omitted. Indices are zero-based;
    native_content_block_index addresses the actual MCP content list, whose
    first image follows its text at index one. Unsupported or conflicting
    references retain the full response through the caller's existing path.
    """
    if 'region_task' in value.get('facts', {}):
        return _project_region_task_brief(value)
    object_columns = ['object_index', 'host_id', 'instance_id', 'object_name']
    region_columns = ['roi_id', 'object_index', 'status', 'reason']
    pixel_columns = ['image_index', 'region_index', 'front_facing',
                     'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable']
    rule_fields = ('minimum_surface_pixels', 'minimum_boundary_pixels', 'minimum_rgb_boundary_contrast')
    identity_fields = ('host_id', 'instance_id', 'object_name')
    world_fields = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
    location_fields = ('visible_pixel_bounds', 'visible_pixel_anchor')
    try:
        if (value['result_kind'] != 'active_observation'
                or value['status'] not in ('complete', 'partial', 'unknown', 'predicted')):
            return None
        binding, facts = value['binding'], value['facts']
        required_binding = {
            'scene_revision', 'document_epoch', 'capture_scope', 'unit', 'coordinate_frame',
            'source', 'capture_state', 'source_binding_sha256', 'geometry_identity',
            'camera_identity', 'binding_sha256', 'runtime_source_sha256',
            'source_status', 'disk_status', 'source_check_scope', 'objects',
        }
        if (type(binding) is not dict or not required_binding <= set(binding)
                or set(binding) - required_binding - {'schema', 'camera_policy', 'observation_target'}):
            return None
        capture_state = binding['capture_state']
        if capture_state is not None and (
                type(capture_state) is not dict
                or not {'instance_id', 'epoch', 'revision'} <= set(capture_state)
                or set(capture_state) - {'instance_id', 'epoch', 'revision', 'selection_key'}):
            return None
        located = 'location_conventions' in facts
        consumable = 'inspection' in facts or 'region_evidence' in facts
        fact_fields = {'scene_identity', 'candidate_identity', 'regions', 'observations',
                       'coverage', 'scope', 'image_delivery_scope'}
        if (set(facts) != fact_fields | ({'location_conventions'} if located else set())
                | ({'inspection', 'region_evidence'} if consumable else set())
                or facts['scene_identity'] != binding['geometry_identity']
                or facts['candidate_identity'] != binding['camera_identity']):
            return None
        objects = binding['objects']
        if (not objects or any(set(obj) != set(object_columns) or type(obj['object_index']) is not int
                              or obj['object_index'] != index
                              for index, obj in enumerate(objects))
                or len({obj['host_id'] for obj in objects}) != len(objects)
                or len({obj['instance_id'] for obj in objects}) != len(objects)):
            return None
        regions = facts['regions']
        if located:
            conventions = facts['location_conventions']
            if (set(conventions) != {'coordinate_frame', 'unit', 'corner_order', 'front_direction_normalization',
                    'pixel_origin', 'pixel_index_base', 'pixel_axis_order', 'image_size_px',
                    'visible_pixel_bounds', 'visible_pixel_anchor'}
                    or conventions['coordinate_frame'] != binding['coordinate_frame']
                    or conventions['unit'] != binding['unit']
                    or conventions['corner_order'] != ['center-u-v', 'center+u-v', 'center+u+v', 'center-u+v']
                    or conventions['front_direction_normalization'] != 'maximum absolute component is 1'
                    or conventions['pixel_origin'] != 'top-left' or type(conventions['pixel_index_base']) is not int
                    or conventions['pixel_index_base'] != 0 or conventions['pixel_axis_order'] != ['x', 'y']
                    or conventions['visible_pixel_bounds'] != 'inclusive bounds of actual ROI-owned pixels'
                    or conventions['visible_pixel_anchor'] != 'ROI-owned pixel nearest bounds center; row-major ties'):
                return None
            image_size = conventions['image_size_px']
            if (type(image_size) is not list or len(image_size) != 2
                    or any(type(size) is not int or not 64 <= size <= 512 for size in image_size)):
                return None
        region_indices = {region['roi_id']: index for index, region in enumerate(regions)}
        if len(region_indices) != len(regions):
            return None
        for region in regions:
            if (set(region) != set(region_columns) | set(identity_fields) | (set(world_fields) if located else set())
                    or type(region['object_index']) is not int
                    or not 0 <= region['object_index'] < len(objects)
                    or any(region[key] != objects[region['object_index']][key] for key in identity_fields)):
                return None
            if located and not all(_valid_region_location_vector(region[key]) for key in world_fields):
                return None

        def region_references(ids):
            if type(ids) is not list or len(set(ids)) != len(ids):
                raise ValueError('nonunique_region_reference')
            return [region_indices[roi_id] for roi_id in ids]

        coverage = facts['coverage']
        coverage_lists = {
            'covered_roi_ids': 'covered_region_indices',
            'unresolved_roi_ids': 'unresolved_region_indices',
            'candidate_pool_uncovered_roi_ids': 'candidate_pool_uncovered_region_indices',
        }
        if set(coverage) != set(coverage_lists) | {'scope', 'state_updates', 'observed_views'}:
            return None
        compact_coverage = {key: coverage[key] for key in ('scope', 'state_updates')}
        for key, projected_key in coverage_lists.items():
            references = region_references(coverage[key])
            if references:
                compact_coverage[projected_key] = references
        if coverage['observed_views']:
            compact_coverage['observed_views'] = coverage['observed_views']
        if set(coverage['covered_roi_ids']) & set(coverage['unresolved_roi_ids']):
            return None

        scope = facts['scope']
        patch_support = scope.get('patch_support')
        target = binding.get('observation_target')
        observation_scope = scope.get('observation_scope')
        scope_fields = {'capture_object_count', 'supported_roi_object_count', 'domain',
                        'all_objects_participate_in_occlusion', 'objects_without_supported_roi'}
        if (set(scope) != scope_fields | ({'patch_support'} if patch_support is not None else set())
                | ({'observation_scope'} if observation_scope is not None else set())
                or scope['capture_object_count'] != len(objects)):
            return None
        coverage_indices = set(range(len(objects)))
        if target is not None:
            index = target['target_object_index']
            if (type(index) is not int or not 0 <= index < len(objects)
                    or target['target_object_id'] != objects[index]['host_id']
                    or target['target_instance_id'] != objects[index]['instance_id']
                    or binding['capture_scope'] != 'target_observation_meshes'
                    or patch_support is None or patch_support['schema'] != 'active-patch-support-v2'
                    or observation_scope != {
                        'kind': 'target', 'target_object_index': index, 'target_object_count': 1,
                        'occluder_only_object_count': len(objects) - 1,
                        'full_scene_object_count': len(target['full_scene_identity']['object_instances']),
                        'excluded_object_count': len(target['excluded_object_ids'])}):
                return None
            coverage_indices = {index}
        elif (observation_scope is not None or binding['capture_scope'] != 'complete_scene_meshes'
              or patch_support is not None and patch_support['schema'] != 'active-patch-support-v1'):
            return None
        unsupported = scope['objects_without_supported_roi']
        unsupported_indices = []
        for obj in unsupported:
            index = obj['object_index']
            if (set(obj) != set(object_columns) | {'status'} or type(index) is not int
                    or not 0 <= index < len(objects)
                    or any(obj[key] != objects[index][key] for key in identity_fields)):
                return None
            unsupported_indices.append(index)
        supported_indices = {region['object_index'] for region in regions}
        if (len(set(unsupported_indices)) != len(unsupported_indices)
                or not supported_indices <= coverage_indices
                or set(unsupported_indices) != coverage_indices - supported_indices
                or scope['supported_roi_object_count'] != len(supported_indices)):
            return None
        compact_scope = {key: item for key, item in scope.items() if key != 'objects_without_supported_roi'}
        if unsupported:
            compact_scope['objects_without_supported_roi'] = {
                'columns': ['object_index', 'status'],
                'rows': [[obj['object_index'], obj['status']] for obj in unsupported],
            }
        region_counts, region_source_ranges = None, None
        if patch_support is not None:
            compact_scope['patch_support'], region_counts, region_source_ranges = _project_active_patch_support(
                patch_support, objects, regions)
            occluder_indices = {row['object_index'] for row in patch_support['objects']
                                if row.get('coverage_role') == 'occluder_only'}
            if occluder_indices != set(range(len(objects))) - coverage_indices:
                return None

        frames = value['frames']
        image_indices = {frame['image_ref']: index for index, frame in enumerate(frames)}
        if (len(image_indices) != len(frames)
                or len({frame['view_name'] for frame in frames}) != len(frames)):
            return None
        for frame in frames:
            if (frame['scene_identity'] != binding['geometry_identity']
                    or frame['candidate_identity'] != binding['camera_identity']
                    or frame['host_binding_sha256'] != binding['binding_sha256']
                    or frame['source_revision'] != binding['scene_revision']):
                return None
        if patch_support is not None:
            for frame in frames:
                if (frame['patch_mapping_version'] != 'active-patch-owner-v1'
                        or frame['patch_roi_ids'] != [region['roi_id'] for region in regions]
                        or type(frame['patch_mapping_identity']) is not str or not frame['patch_mapping_identity']
                        or frame['patch_mapping_identity'] != frames[0]['patch_mapping_identity']):
                    return None
        observation_rows, pixels, pixel_rules, observed_indices = [], [], None, []
        pixel_references = {}
        for observation in facts['observations']:
            if set(observation) != {'view_name', 'image_path', 'image_ref', 'image_sha256',
                                    'readable_roi_ids', 'pixel_rows'}:
                return None
            image_index = image_indices[observation['image_ref']]
            frame = frames[image_index]
            if any(observation[key] != frame[key] for key in ('view_name', 'image_path', 'image_sha256')):
                return None
            observed_indices.append(image_index)
            observation_rows.append([image_index, region_references(observation['readable_roi_ids'])])
            seen_regions, readable_ids = set(), set()
            for pixel_index, pixel in enumerate(observation['pixel_rows']):
                expected_pixel_fields = set(rule_fields) | {
                        'roi_id', 'object_index', 'host_id', 'object_name', 'view',
                        'front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable'}
                if set(pixel) != expected_pixel_fields | (set(location_fields) if located else set()):
                    return None
                if located and not _valid_visible_pixel_location(pixel, image_size):
                    return None
                region_index = region_indices[pixel['roi_id']]
                region = regions[region_index]
                if (region_index in seen_regions or pixel['view'] != observation['view_name']
                        or any(pixel[key] != region[key] for key in ('object_index', 'host_id', 'object_name'))):
                    return None
                seen_regions.add(region_index)
                rules = {key: pixel[key] for key in rule_fields}
                if pixel_rules is None:
                    pixel_rules = rules
                elif rules != pixel_rules:
                    return None
                if pixel['readable']:
                    readable_ids.add(pixel['roi_id'])
                if consumable:
                    pixel_references[(observation['view_name'], pixel_index)] = (len(pixels), region_index, pixel)
                pixels.append([image_index, region_index, *[pixel[key] for key in pixel_columns[2:]],
                               *[pixel[key] for key in location_fields if located]])
            if (seen_regions != set(range(len(regions)))
                    or readable_ids != set(observation['readable_roi_ids'])):
                return None
        if (len(set(observed_indices)) != len(frames) or sorted(observed_indices) != list(range(len(frames)))
                or coverage['observed_views'] != [row['view_name'] for row in facts['observations']]):
            return None
        compact_binding = {key: item for key, item in binding.items()
                           if key not in ('schema', 'objects', 'camera_policy')}
        if target is not None:
            compact_target = {key: target[key] for key in (
                'schema', 'selector', 'target_object_id', 'target_instance_id', 'target_object_index',
                'camera_plan_sha256', 'directory_sha256', 'source_frame')}
            compact_target['full_scene_identity_sha256'] = hashlib.sha256(json.dumps(
                target['full_scene_identity'], sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()
            compact_binding['observation_target'] = compact_target
        if type(compact_binding.get('capture_state')) is dict:
            compact_binding['capture_state'] = {key: item for key, item in binding['capture_state'].items()
                                                if key != 'selection_key'}
        result = {key: value[key] for key in ('status', 'result_kind', 'observation_status',
                                             'session_id', 'read_only', 'execution_authority')}
        result.update(schema='active-observation-brief-v2' if patch_support is not None else 'active-observation-brief-v1', index_base=0,
            binding=compact_binding,
            objects={'columns': object_columns, 'rows': [[obj[key] for key in object_columns] for obj in objects]},
            coverage=compact_coverage, scope=compact_scope,
            image_delivery_scope=facts['image_delivery_scope'], image_delivery=value['image_delivery'])
        if regions:
            result['regions'] = {'columns': region_columns,
                                 'rows': [[region[key] for key in region_columns] for region in regions]}
            if region_counts is not None:
                result['regions']['columns'].extend(['triangle_count', 'source_triangle_index_ranges'])
                for row, count, ranges in zip(result['regions']['rows'], region_counts, region_source_ranges):
                    row.append(count)
                    row.append(ranges)
            if located:
                result['regions']['columns'].extend(world_fields)
                for row, region in zip(result['regions']['rows'], regions):
                    row.extend(region[key] for key in world_fields)
        if frames:
            result['images'] = {
                'columns': ['view_name', 'image_ref', 'image_sha256', 'native_content_block_index'],
                'rows': [[frame['view_name'], frame['image_ref'], frame['image_sha256'], index + 1]
                         for index, frame in enumerate(frames)],
            }
            result['observations'] = {'columns': ['image_index', 'readable_region_indices'], 'rows': observation_rows}
            if patch_support is not None:
                result['patch_mapping_version'] = frames[0]['patch_mapping_version']
                result['images']['columns'].append('patch_mapping_identity')
                for row, frame in zip(result['images']['rows'], frames):
                    row.append(frame['patch_mapping_identity'])
        if pixels:
            result['pixels'] = {'columns': pixel_columns + (list(location_fields) if located else []), 'rows': pixels}
            result['pixel_rules'] = pixel_rules
        if located:
            result['schema'] = 'active-observation-brief-v3'
            result['location_conventions'] = conventions
        if consumable:
            evidence, view_groups = _project_active_inspection(facts, regions, pixel_references)
            result['schema'] = 'active-observation-brief-v4'
            result['inspection'] = facts['inspection']
            if regions:
                result['regions']['columns'].extend(['complete_witness_pixel_index', 'unobserved_reason',
                                                     'unobserved_view_group_indices'])
                for row, extra in zip(result['regions']['rows'], evidence):
                    row.extend(extra)
            if view_groups['rows']:
                result['unobserved_view_groups'] = view_groups
        if region_source_ranges is not None:
            result['schema'] = 'active-observation-brief-v5'
            result['source_triangle_index_ranges_semantics'] = (
                'zero_based_object_local_inclusive; object_index_in_objects; scoped_to_this_binding')
        if 'task_result' in value:
            task = value['task_result']
            source = task.get('binding', {}).get('observation_source') if type(task) is dict else None
            if (type(source) is not dict or task.get('result_kind') != 'task_query'
                    or task.get('schema_version') != 'task-query-v3'
                    or source.get('schema') != 'active-observation-task-source-v1'
                    or source.get('measurement_scope') != 'whole_objects'
                    or source.get('capture_scope') != 'observation_task_objects'
                    or source.get('parent_binding_sha256') != binding['binding_sha256']
                    or source.get('parent_source_binding_sha256') != binding['source_binding_sha256']
                    or source.get('parent_capture_scope') != binding['capture_scope']):
                return None
            derived_state = source.get('capture_state')
            if ((derived_state is None) != (capture_state is None)
                    or derived_state is not None and (type(derived_state) is not dict
                        or any(derived_state.get(key) != capture_state.get(key)
                               for key in ('instance_id', 'epoch', 'revision')))):
                return None
            result['task_result'] = copy.deepcopy(task)
        return copy.deepcopy(result)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        return None


def _validate_source_region_projection(value):
    """Share the existing source-selection and frame checks across both details."""
    from .query_policy import validate_source_region_query

    task = value['task_result']
    reference = value['region_ref']
    validate_source_region_query({'mode': 'source_region', 'region_ref': reference,
        'reference': {'id': task['reference']['object_id']}, 'requested_facts': ['surface_proximity']})
    if (value['result_kind'] != 'source_region' or task['region_ref'] != reference
            or value['facts']['region']['source_triangle_indices'] != reference['source_triangle_indices']):
        raise ValueError('source_region_result_scope_mismatch')
    for frame in value['frames']:
        if frame['host_binding_sha256'] != value['binding']['binding_sha256']:
            raise ValueError('source_region_frame_binding_mismatch')
    visibility = value['facts']['visibility']
    witness = visibility.get('complete_witness')
    if witness is not None:
        fields = ('view_name', 'image_ref', 'frame_identity')
        frames = value['frames']
        if (not isinstance(witness, dict) or len(frames) != 1
                or any(witness.get(field) != frames[0][field] or visibility.get(field) != frames[0][field]
                       for field in fields)
                or witness.get('geometry_status') != 'complete' or visibility.get('geometry_status') != 'complete'
                or any(type(witness.get(field)) is not int or witness[field] < minimum
                       or visibility.get(field) != witness[field] for field, minimum in (
                           ('selected_surface_pixels', 16), ('contrasting_boundary_pixels', 4)))
                or any(witness.get(field) != minimum for field, minimum in (
                    ('minimum_surface_pixels', 16), ('minimum_boundary_pixels', 4),
                    ('minimum_rgb_boundary_contrast', 24)))):
            raise ValueError('source_region_complete_witness_frame_mismatch')


def _project_source_region_brief(value):
    task = value['task_result']
    reference = value['region_ref']
    images = []
    for index, frame in enumerate(value['frames'], 1):
        images.append({key: frame[key] for key in (
            'image_ref', 'view_name', 'frame_identity', 'image_sha256', 'camera_identity',
            'host_binding_sha256', 'display_identity', 'image_scope_identity') if key in frame})
        images[-1]['image_block_index'] = index
    binding = value['binding']
    region = value['facts']['region']
    visibility = value['facts']['visibility']
    brief = {
        'schema': 'source-region-brief-v2',
        'status': value['status'],
        'observation_status': value['observation_status'],
        'task_result': {
            'status': task['status'],
            'reference': task['reference'],
            'measurement_scope': task['measurement_scope'],
            'unit': binding['unit'],
            'coordinate_frame': binding['coordinate_frame'],
            'facts': task['facts'],
            'source_mapping': {'nearest_witness': task['source_mapping']['nearest_witness']},
        },
        'visibility': {key: item for key, item in visibility.items()
            if key not in ('visible_source_triangle_indices', 'unseen_source_triangle_indices', 'image_scope')},
        'images': images,
        'region': {key: region[key] for key in (
            'host_id', 'instance_id', 'object_name', 'index_domain', 'bbox_min_world_m', 'bbox_max_world_m')},
        'image_scope': binding['image_scope'],
        'binding': {key: binding[key] for key in (
            'source_binding_sha256', 'binding_sha256', 'runtime_source_sha256', 'source_status', 'disk_status')
            if key in binding},
    }
    # Keep the pre-existing unknown and no-image transports unchanged. On
    # success the witnessed PNG and its full reference must fit one CLI reply.
    if visibility.get('complete_witness') is not None:
        scope = brief['image_scope']
        objects = scope['objects']
        columns = list(objects[0])
        if any(row.keys() != objects[0].keys() for row in objects):
            raise ValueError('source_region_uniform_display_directory_required')
        brief['image_scope'] = {**scope, 'objects': {
            'columns': columns, 'rows': [[row[key] for key in columns] for row in objects]}}
        brief['schema'] = 'source-region-brief-v3'
    brief['visibility'].update(
        visible_source_triangle_count=len(visibility['visible_source_triangle_indices']),
        unseen_source_triangle_count=len(visibility['unseen_source_triangle_indices']))
    brief['region'].update(source_triangle_count=len(region['source_triangle_indices']),
                           source_vertex_count=len(region['source_vertex_indices']))
    brief.update({key: value[key] for key in (
        'result_kind', 'session_id', 'read_only', 'execution_authority', 'image_delivery') if key in value})
    # Document, generation and ordered geometry identities remain in the original
    # self-contained v1 ref. Detailed member mappings use the existing full path.
    brief['details'] = 'response_detail=full'
    brief['region_ref'] = reference
    return copy.deepcopy(brief)


def project_source_region_brief(value):
    """Place measured facts and image evidence before one complete selection ref."""
    _validate_source_region_projection(value)
    return _project_source_region_brief(value)


def _observation_image_path(path, image_root, binding_digest=None):
    if not path.is_absolute() or path.as_posix().startswith('//') or path.suffix != '.png':
        return None
    try:
        relative = path.relative_to(image_root)
        if len(relative.parts) != (2 if binding_digest is None else 3):
            return None
        generation = relative.parts[0]
        if len(generation) != 32 or any(char not in '0123456789abcdef' for char in generation):
            return None
        if binding_digest is not None and relative.parts[1] != binding_digest:
            return None
        if path.resolve(strict=True) != path or not path.is_file():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return path.as_posix()


def _source_region_local_image_path(value, frame, image_root):
    """Expose only the witness file belonging to this service's image output."""
    if image_root is None:
        return None
    from .active_observation import fingerprint

    # The selected frame must be the exact constructed frame, including its
    # path, rather than a different file that happens to have identical pixels.
    constructed = value.get('constructed_frames')
    if type(constructed) is not list or any(not isinstance(item, dict) for item in constructed):
        return None
    candidates = [item for item in constructed
                  if item.get('frame_identity') == frame['frame_identity'] or item.get('image_ref') == frame['image_ref']]
    expected_ref = 'source-region-image:' + fingerprint((
        value['region_ref']['region_id'], frame['frame_identity'], frame['image_sha256']))
    if candidates != [frame] or frame['image_ref'] != expected_ref:
        return None
    return _observation_image_path(Path(frame['image_path']), image_root)


def _target_observation_local_image_path(frame, sequence, binding_digest, image_root):
    from .active_observation import fingerprint

    view, image_sha = frame['view_name'], frame['image_sha256']
    owner_schema, owner_identity = frame.get('owner_schema'), frame.get('owner_mapping_identity')
    frame_identity = frame.get('frame_identity')
    if not all(isinstance(item, str) and item for item in (owner_schema, owner_identity, frame_identity)):
        return None
    scene_camera = (frame['scene_identity'], frame['candidate_identity'])
    if frame_identity != fingerprint((scene_camera, owner_schema, owner_identity, view, sequence, image_sha)):
        return None
    reference = (binding_digest, view, image_sha, frame['patch_mapping_identity'],
                 owner_schema, owner_identity, frame_identity)
    if frame['image_ref'] != 'active-host-image:' + fingerprint(reference):
        return None
    path = Path(frame['image_path'])
    stem = f'{sequence:03d}-' + fingerprint((scene_camera, owner_identity, view))[:24]
    if (frame['image_path'] != str(path) or path.name != stem + '.png'
            or frame.get('arrays_path') != str(path.with_suffix('.npz'))):
        return None
    return _observation_image_path(path, image_root, binding_digest)


def _project_target_observation_image_paths(brief, value, blocks, image_root):
    """Add paths only for complete witnesses in the already encoded native blocks."""
    if (image_root is None or brief['status'] != 'complete'
            or brief['observation_status'] != 'locally_observed'
            or brief['binding']['capture_scope'] != 'target_observation_meshes'
            or brief['schema'] != 'active-observation-brief-v5'):
        return
    regions, pixels, images = (brief.get(table) for table in ('regions', 'pixels', 'images'))
    if not all((regions, pixels, images)) or not blocks:
        return
    witness_column = regions['columns'].index('complete_witness_pixel_index')
    roi_column = regions['columns'].index('roi_id')
    image_column = pixels['columns'].index('image_index')
    region_column = pixels['columns'].index('region_index')
    frames = value['frames']
    classifications = value.get('target_view_classifications')
    if type(classifications) is not dict:
        return
    witnessed = set()
    for region_index, region in enumerate(regions['rows']):
        witness = region[witness_column]
        if type(witness) is not int or not 0 <= witness < len(pixels['rows']):
            continue
        pixel = pixels['rows'][witness]
        image_index = pixel[image_column]
        if (pixel[region_column] != region_index or type(image_index) is not int
                or not 0 <= image_index < len(frames)):
            continue
        view = classifications.get(frames[image_index]['view_name'])
        if type(view) is dict and view.get(region[roi_column]) == {
                'status': 'complete', 'complete': True, 'first_blocker': None}:
            witnessed.add(image_index)
    if not witnessed or len(images['rows']) != len(frames) or len(blocks) != len(frames):
        return
    from .active_observation import fingerprint

    binding = value['binding']
    digest = binding['binding_sha256']
    if digest != fingerprint({key: field for key, field in binding.items() if key not in {
            'binding_sha256', 'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}}):
        return
    # The service constructs every ordinary frame under the same generation.
    if len({Path(frame['image_path']).parent for frame in frames}) != 1:
        return
    paths = [None] * len(frames)
    for index in witnessed:
        frame, row = frames[index], images['rows'][index]
        if row == [frame[key] for key in ('view_name', 'image_ref', 'image_sha256')] + [
                index + 1, frame['patch_mapping_identity']]:
            paths[index] = _target_observation_local_image_path(frame, index + 1, digest, image_root)
    if any(paths):
        images['columns'].append('local_image_path')
        for row, path in zip(images['rows'], paths):
            row.append(path)


def _active_observation_content(value, *, is_error, audit, response_detail=None, observation_task_query=None,
                                source_region_image_root=None, target_observation_image_root=None):
    started = time.perf_counter_ns()
    audit.update(status='encoding', started_ns=started, frames=[],
        native_blocks_constructed=0, mcp_content_ready=False,
        consumer_read_status='unconfirmed')
    source_region = value.get('result_kind') == 'source_region'
    source_region_brief = source_region and response_detail != 'full' and not is_error
    if source_region:
        metadata = {} if source_region_brief else copy.deepcopy(value)
    else:
        metadata = {key: copy.deepcopy(value[key]) for key in (
            'status', 'result_kind', 'observation_status', 'session_id', 'facts',
            'work', 'generation_work', 'stages', 'generation_stages',
            'read_only', 'execution_authority', 'target_view_classifications', 'task_result',
        ) if key in value}
    if 'binding' in value and not source_region:
        metadata['binding'] = {key: copy.deepcopy(item) for key, item in value['binding'].items()
            if key != 'camera_specification'}
    frames = value.get('frames')
    content = []
    try:
        if type(frames) is not list or len(frames) > (1 if source_region else 6):
            raise ValueError('Active observation requires at most six frame references')
        if source_region:
            _validate_source_region_projection(value)
        else:
            metadata['frames'] = [{key: copy.deepcopy(frame[key]) for key in (
                'scene_identity', 'candidate_identity', 'view_name', 'image_ref',
                'image_path', 'image_sha256', 'PNG_bytes', 'arrays_path', 'arrays_sha256',
                'compressed_array_file_bytes', 'array_payload_bytes',
                'host_binding_sha256', 'source_revision', 'stages', 'feedback_stages',
                'patch_mapping_version', 'patch_roi_ids', 'patch_mapping_identity',
                'patch_owner_array_bytes', 'patch_mapping_array_bytes',
                'mesh_order_identity', 'owner_schema', 'owner_mapping_identity', 'triangle_id_scope',
                'owner_capabilities', 'frame_identity', 'triangle_owner_array_bytes', 'owner_metadata_array_bytes',
                'scope_id', 'camera_identity',
            ) if key in frame} for frame in frames]
        region_task = 'region_task' in value.get('facts', {})
        if region_task:
            metadata['scopes'] = copy.deepcopy(value['scopes'])
            metadata['constructed_frames'] = copy.deepcopy(value['constructed_frames'])
            # Scope validation uses the exact selected references from the same
            # construction archive. Each selected image gets its public block
            # index after selection, independent of repeated view names.
            metadata['frames'] = copy.deepcopy(frames)
        for frame in frames:
            row = {'image_ref': frame.get('image_ref'), 'view_name': frame.get('view_name'),
                   'PNG_bytes_read': 0, 'base64_chars': 0, 'status': 'reading'}
            audit['frames'].append(row)
            mark = time.perf_counter_ns()
            raw = Path(frame['image_path']).read_bytes()
            row.update(read_ns=time.perf_counter_ns()-mark, PNG_bytes_read=len(raw))
            mark = time.perf_counter_ns()
            if hashlib.sha256(raw).hexdigest() != frame['image_sha256']:
                raise ValueError('Active observation PNG source binding changed')
            public = _public_native_png(raw)
            if public != raw or public[16:24] != b'\x00\x00\x02\x00\x00\x00\x02\x00':
                raise ValueError('Active observation requires the registered 512px PNG bytes')
            row.update(validate_ns=time.perf_counter_ns()-mark, status='encoding')
            mark = time.perf_counter_ns()
            data = base64.b64encode(public).decode('ascii')
            row.update(base64_ns=time.perf_counter_ns()-mark, base64_chars=len(data), status='constructed')
            content.append({'type': 'image', 'mimeType': 'image/png', 'data': data})
            audit['native_blocks_constructed'] = len(content)
        image_delivery = {
            'local_verified_image_count': len(value.get('constructed_frames', frames)),
            'mcp_content_constructed_image_count': len(content),
            'consumer_read_status': 'unconfirmed',
            'frame_reuses': value.get('work', {}).get('frame_reuses', 0),
            'new_raster_attempts': value.get('work', {}).get('raster_attempts', 0),
        }
        if source_region_brief:
            metadata = _project_source_region_brief({**value, 'image_delivery': image_delivery})
            if (len(content) == 1 and value['status'] == 'complete'
                    and value['facts']['visibility'].get('complete_witness') is not None):
                local_path = _source_region_local_image_path(value, frames[0], source_region_image_root)
                if local_path is not None:
                    metadata['images'][0]['local_image_path'] = local_path
            projected = metadata
        else:
            metadata['image_delivery'] = image_delivery
        if region_task:
            metadata['image_delivery']['selected_image_count'] = len(frames)
            projected = _project_region_task_brief(metadata,
                validate_only=response_detail == 'full' or is_error,
                observation_task_query=observation_task_query)
        audit['projection_status'] = 'full_requested' if response_detail == 'full' else 'unsupported_full'
        if response_detail != 'full' and not is_error:
            brief = projected if source_region or region_task else project_active_observation_brief(metadata)
            if brief is not None:
                if not source_region and not region_task:
                    _project_target_observation_image_paths(brief, value, content, target_observation_image_root)
                metadata = brief
                audit['projection_status'] = 'brief'
        text = json.dumps(metadata, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        audit.update(status='constructed', mcp_content_ready=True,
            public_text_bytes=len(text.encode('utf8')),
            PNG_bytes=sum(row['PNG_bytes_read'] for row in audit['frames']),
            base64_chars=sum(row['base64_chars'] for row in audit['frames']))
        record_image_artifact('mcp_content', native_block_count=len(content))
        return {'content': [{'type': 'text', 'text': text}, *content], 'isError': bool(is_error)}
    except Exception as error:
        audit.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:1000]})
        record_image_artifact('mcp_content', native_block_count=0)
        raise
    finally:
        audit['closed_ns'] = time.perf_counter_ns()
        audit['elapsed_ns'] = audit['closed_ns'] - started


def _tool_result(value: Any, *, is_error: bool, response_detail: str | None = None,
                 compact_support_planes: bool = False, segment_brief: bool = False,
                 active_delivery_audit=None, observation_task_query=None, source_region_image_root=None,
                 target_observation_image_root=None) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Live service returned an invalid result")
    if value.get('result_kind') in ('active_observation', 'source_region'):
        return _active_observation_content(value, is_error=is_error,
            audit={} if active_delivery_audit is None else active_delivery_audit,
            response_detail=response_detail, observation_task_query=observation_task_query,
            source_region_image_root=source_region_image_root,
            target_observation_image_root=target_observation_image_root)
    if response_detail is None:
        response_detail = 'brief' if value.get('result_kind') == 'surface_scan' else 'full'
    if (value.get('result_kind') in ('task_query', 'surface_nearest', 'surface_scan', 'scene_directory')
            or value.get('schema') == 'arm-twist-expert-report-v1'):
        # Validate the complete response before optional display-only omission.
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        if value.get('result_kind') == 'surface_scan' and response_detail == 'brief' and not is_error:
            try:
                with span('mcp.surface_scan_compact_projection'):
                    compact = project_surface_scan_brief(value)
                if compact is not None:
                    text = json.dumps(compact, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                    annotate(surface_scan_display='compact')
                else:
                    annotate(surface_scan_display='full_unsupported_projection')
            except Exception as error:
                annotate(surface_scan_display='full_projection_fallback',
                         surface_scan_display_error=type(error).__name__)
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
        query = args.get('query')
        scan = isinstance(query, dict) and query.get('mode') == 'surface_scan'
        operation = operations.get(name, 'mcp.invalid') if isinstance(name, str) else 'mcp.invalid'
        with factory(operation,
                     session_id=args.get('session_id', self.default_session_id)) as trace:
            set_image_request(False if name in {'human_eye_spatial_relations', 'human_eye_surface_nearest', 'human_eye_arm_twist_observe'} else
                              args.get('include_image', False) if name == 'human_eye_clearance_segment' else
                              args.get('include_image', not scan) if name == 'human_eye_scene_observe' else
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
        from .blender_host import BlenderHostError
        from .blender_process import HostRemoteError
        numeric_reason = 'active_observation_target_camera_numeric_insufficient'
        numeric_insufficient = type(exc) is BlenderHostError and str(exc) == numeric_reason
        if isinstance(exc, HostRemoteError):
            remote = exc.error
            numeric_insufficient = (type(remote) is dict
                and set(remote) == {'type', 'message', 'mutation_uncertain'}
                and remote['type'] == 'BlenderHostError' and remote['message'] == numeric_reason
                and remote['mutation_uncertain'] is False)
        if numeric_insufficient:
            metadata.update(status='unknown', reason=numeric_reason,
                observation_status='numeric_insufficient', observation_mode='active_observation')
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
            if isinstance(args.get('query'), dict) and args['query'].get('mode') == 'surface_scan':
                args.setdefault('include_image', False)
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
            if value.get('result_kind') in ('surface_nearest', 'scene_directory'):
                is_error = value.get('status') not in {'complete', 'partial'}
            if value.get('result_kind') == 'surface_scan':
                is_error = value.get('status') not in {'complete', 'partial', 'unknown'}
            if value.get('result_kind') in ('active_observation', 'source_region'):
                is_error = value.get('status') not in {'complete', 'partial', 'unknown', 'predicted'}
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
            kind = value.get('result_kind')
            delivery_audit = {} if kind in ('active_observation', 'source_region') else None
            image_root, target_image_root = None, None
            if delivery_audit is not None:
                state_path = getattr(self.service, 'state_path', None)
                if isinstance(state_path, Path) and state_path.is_absolute():
                    if kind == 'source_region':
                        image_root = state_path.with_name(state_path.name + '.source_region')
                    elif isinstance(value.get('binding'), dict) and value['binding'].get(
                            'capture_scope') == 'target_observation_meshes':
                        target_image_root = state_path.with_name(state_path.name + '.active_observation')
            try:
                result = _tool_result(value, is_error=is_error,
                    response_detail=args.get('response_detail'),
                    segment_brief=(name == 'human_eye_clearance_segment'),
                    compact_support_planes=(name == 'human_eye_scene_observe'
                        and 'support_plane_discovery' in args.get('query', {})),
                    active_delivery_audit=delivery_audit,
                    observation_task_query=(args['query'].get('task_query')
                        if isinstance(args.get('query'), dict) else None),
                    source_region_image_root=image_root,
                    target_observation_image_root=target_image_root)
            finally:
                recorder = getattr(self.service, 'record_event', None)
                if delivery_audit is not None and callable(recorder):
                    recorder('source_region_mcp_content' if value.get('result_kind') == 'source_region'
                        else 'active_observation_mcp_content', session_id=session_id,
                        image_delivery=delivery_audit)
        if value.get('result_kind') in ('task_query', 'surface_nearest', 'surface_scan', 'scene_directory', 'active_observation', 'source_region'):
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
