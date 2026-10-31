"""Optional display projections; full precision and gates stay intact.

Observation brief omits explicitly named camera, raster and attention details.
Segment brief preserves every decoded endpoint fact using local references.
Unknown fields survive. Malformed or unrecognized contracts retain full MCP
responses instead of acquiring a new summary meaning.
"""
from __future__ import annotations

import copy
import json
import math

from .hook_context import _observation, _deduplicate, _contains_reference_key


BRIEF_REVISION = 'observation-task-brief-v1-20261026'
SEGMENT_BRIEF_REVISION = 'segment-endpoint-references-v1-20261030'
_SOURCES = {'human_eye_geometry_observation', 'human_eye_live_blender_scene_overview'}
_REQUIRED = ('observation_status', 'scene_assessment', 'action_eligibility',
             'execution_status', 'pair_goal', 'scene_capabilities')
_VIEW_DIAGNOSTICS = (
    'view_matrix', 'projection_matrix', 'camera_eye_world_m', 'target_world_m',
    'near_m', 'far_m', 'view_span_m', 'm_per_pixel', 'fov_y_deg',
    'target_plane_distance_m', 'target_plane_m_per_pixel',
    'geometry_depth_pixels', 'geometry_depth_fraction', 'depth_range_m',
    'geometry_pixels_unchanged_by_annotations', 'object_visible_pixels', 'scale_bar',
)


def project_task_brief(metadata):
    """Return a detached brief, or None to retain the unchanged full response.

    Measurement, capability, query, unknown, goal and execution evidence is
    copied whole, including missing/null/false/zero distinctions. Scene delta
    payloads also remain whole. No permission, visibility or success is inferred.
    """
    if (not isinstance(metadata, dict)
            or not isinstance(metadata.get('status'), str)
            or metadata.get('status') not in {'observed', 'overview', 'partial'}
            or metadata.get('result_contract_version') != '1.1'
            or any(field not in metadata for field in _REQUIRED)
            or any(not isinstance(metadata[field], dict) for field in
                   ('scene_assessment', 'action_eligibility', 'pair_goal', 'scene_capabilities'))
            or metadata['observation_status'] not in ('complete', 'partial', 'unavailable', 'not_requested')
            or metadata['execution_status'] != 'not_requested'
            or any(field in metadata for field in ('observation', 'response_detail', 'task_brief'))):
        return None
    route = metadata.get('routing')
    if not isinstance(route, dict):
        return None
    observation, status = _observation(route.get('context_text'))
    if (status != 'structured' or not isinstance(observation.get('source'), str)
            or observation.get('source') not in _SOURCES
            or observation.get('unit') != 'm' or observation.get('coordinate_frame') != 'world'):
        return None
    # Preserve contradictory evidence in full rather than selecting one version.
    for field in ('scene_revision', 'observation_status', 'scene_assessment', 'query_result', 'support_plane_discovery'):
        if (field in route and field in observation
                and json.dumps(route[field], sort_keys=True, allow_nan=False) !=
                    json.dumps(observation[field], sort_keys=True, allow_nan=False)):
            return None
    for field in ('observation_status', 'scene_assessment', 'query_result', 'support_plane_discovery'):
        if (field in route and field in metadata
                and json.dumps(route[field], sort_keys=True, allow_nan=False) !=
                    json.dumps(metadata[field], sort_keys=True, allow_nan=False)):
            return None
    canvas = observation.get('canvas')
    if canvas is not None and not isinstance(canvas, dict):
        return None
    if isinstance(canvas, dict) and 'views' in canvas:
        if (not isinstance(canvas['views'], list)
                or any(not isinstance(view, dict) for view in canvas['views'])):
            return None
    if isinstance(canvas, dict) and 'supplemental_views' in canvas:
        if (not isinstance(canvas['supplemental_views'], list) or len(canvas['supplemental_views']) > 1
                or any(not isinstance(view, dict) for view in canvas['supplemental_views'])):
            return None
    for attention in (observation.get('attention'),
                      canvas.get('attention') if isinstance(canvas, dict) else None):
        if attention is not None and not isinstance(attention, dict):
            return None

    brief = copy.deepcopy(metadata)
    brief['routing'].pop('context_text')
    brief['observation'] = observation
    omitted = []

    def omit(value, fields, prefix):
        for field in fields:
            if field in value:
                value.pop(field)
                path = prefix + '.' + field
                if path not in omitted:
                    omitted.append(path)

    for field in ('scene_memory', 'measurement_cache'):
        diagnostic = observation.get(field)
        if isinstance(diagnostic, dict):
            omit(diagnostic, ('stats',), 'observation.' + field)
    attention = observation.get('attention')
    if isinstance(attention, dict):
        omit(attention, ('proposal', 'state_to_commit'), 'observation.attention')
    if isinstance(canvas, dict):
        for view in canvas.get('views', []):
            omit(view, _VIEW_DIAGNOSTICS, 'observation.canvas.views[]')
        for view in canvas.get('supplemental_views', []):
            omit(view, _VIEW_DIAGNOSTICS, 'observation.canvas.supplemental_views[]')
        attention = canvas.get('attention')
        if isinstance(attention, dict):
            omit(attention, ('proposal', 'state_to_commit'), 'observation.canvas.attention')

    brief['response_detail'] = 'brief'
    brief['task_brief'] = {
        'schema_revision': BRIEF_REVISION,
        'scope': 'observation_display_projection_not_execution_authorization',
        'execution_authority': False,
        'omitted_diagnostics': omitted,
        'full_diagnostics_request': {'response_detail': 'full'},
        'full_diagnostics_returns': 'new_current_observation_not_historical_receipt',
        'native_image_bytes_changed': False,
    }
    return brief


def project_segment_brief(metadata):
    """Losslessly reference a recognized fresh segment's endpoint display.

    Receipt fields stay direct and unchanged. Only the strictly decoded
    context string and routing dictionaries share a local reference catalog;
    no receipt, execution decision, image or diagnostic is summarized.
    Unsupported or ambiguous contracts retain their complete full response.
    """
    try:
        return _segment_brief(metadata)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None


def _segment_brief(metadata):
    reserved = {'observation', 'task_brief', 'response_detail', 'endpoint_observation',
                'segment_brief', 'segment_projection', 'capability_reference_encoding',
                'support_plane_reference_encoding', 'support_plane_value_encoding',
                'context_observation_ref'}
    if (not isinstance(metadata, dict) or reserved.intersection(metadata)
            or metadata.get('schema_version') != '1.0'
            or metadata.get('status') not in ('satisfied', 'review_required')
            or metadata.get('replayed') is not False
            or metadata.get('historical_receipt') is not False
            or metadata.get('execution_scope') != 'terminal_geometry_only'
            or any(metadata.get(field) is not False for field in
                   ('swept_path_certified', 'execution_authority', 'retry_authorized'))
            or metadata.get('task_succeeded') is not (metadata['status'] == 'satisfied')
            or metadata.get('review_required') is not (metadata['status'] == 'review_required')
            or type(metadata.get('executed')) is not bool
            or metadata.get('execution_status') != (
                'executed_verified' if metadata['executed'] else 'not_executed')
            or metadata.get('presentation_scope') != 'segment_end_snapshot_not_current_after_return'
            or metadata.get('current_scene_revalidated') is False
            or _contains_reference_key(metadata)):
        return None
    # This is contract recognition, not a second execution gate. In particular,
    # initial selection bindings and previous-step revisions may legitimately
    # differ from the endpoint and are never relabeled as current evidence.
    for field in ('request_id', 'segment_id', 'base_revision', 'end_revision'):
        if not isinstance(metadata.get(field), str) or not metadata[field]:
            return None
    for field in ('actual_total_translation_m', 'elapsed_s'):
        number = metadata.get(field)
        if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
            return None
    request = metadata.get('request')
    steps = metadata.get('steps')
    residual = metadata.get('residual')
    route = metadata.get('routing')
    if (not isinstance(request, dict) or not isinstance(steps, list)
            or not isinstance(residual, dict) or not isinstance(route, dict)
            or reserved.intersection(route)
            or any(field in route for field in ('scene_capabilities_ref', 'support_plane_discovery_ref'))
            or route.get('route') != 'engine'):
        return None
    for field in ('focal_id', 'reference_id'):
        if not isinstance(request.get(field), str) or not request[field]:
            return None
    if request['focal_id'] == request['reference_id']:
        return None
    binding = request.get('selection_binding')
    if binding is not None:
        if (not isinstance(binding, dict)
                or any(binding.get(field) != request[field] for field in ('focal_id', 'reference_id'))):
            return None
    for step in steps:
        if (not isinstance(step, dict) or step.get('state') != 'complete'
                or not isinstance(step.get('result'), dict)
                or type(step['result'].get('executed')) is not bool
                or step['result'].get('status') not in
                    ('verified', 'no_op', 'blocked', 'invalid_action', 'invalid_goal',
                     'observation_required', 'implementation_mismatch', 'host_quarantined', 'disabled')):
            return None
        result = step['result']
        verified = result['status'] == 'verified'
        if any(result.get(field) is not verified for field in ('executed', 'verified', 'execution_verified')):
            return None
        action = step.get('action')
        if (not isinstance(action, dict)
                or any(action.get(field) != request[field] for field in ('focal_id', 'reference_id'))):
            return None
    observation, status = _observation(route.get('context_text'))
    if (status != 'structured' or reserved.intersection(observation)
            or _contains_reference_key(observation)
            or observation.get('source') != 'human_eye_geometry_observation'
            or observation.get('unit') != 'm'
            or observation.get('coordinate_frame') != 'world'
            or observation.get('observation_status') not in
                ('complete', 'partial', 'unavailable', 'not_requested')
            or any(observation.get(field) != request[field] for field in ('focal_id', 'reference_id'))
            or route.get('scene_revision') != metadata['end_revision']
            or observation.get('scene_revision') != metadata['end_revision']):
        return None

    def exact(left, right):
        # JSON equality distinguishes false/zero and null/missing; ordinary
        # Python dictionary equality would collapse some of those facts.
        return (json.dumps(left, sort_keys=True, ensure_ascii=True, allow_nan=False)
                == json.dumps(right, sort_keys=True, ensure_ascii=True, allow_nan=False))

    shared = ('scene_revision', 'scene_fingerprint', 'scene_source', 'unit',
              'coordinate_frame', 'focal_id', 'reference_id', 'observation_status',
              'scene_assessment', 'query_result', 'support_plane_discovery',
              'scene_capabilities', 'spatial_index', 'rigid_frame', 'rigid_frame_valid',
              'legacy_axes_validation_scope', 'measurement', 'host_execution', 'scene_contacts', 'query')
    for field in shared:
        copies = [value[field] for value in (metadata, route, observation) if field in value]
        if copies and any(not exact(copies[0], value) for value in copies[1:]):
            return None
    for value in (metadata, route, residual):
        for field in ('focal_id', 'reference_id'):
            if field in value and not exact(value[field], request[field]):
                return None
        if 'scene_revision' in value and not exact(value['scene_revision'], metadata['end_revision']):
            return None
        if 'unit' in value and value['unit'] != 'm':
            return None
        if 'coordinate_frame' in value and value['coordinate_frame'] != 'world':
            return None
    residual_request = residual.get('request')
    if residual_request is not None:
        if (not isinstance(residual_request, dict)
                or any(residual_request.get(field) != request[field] for field in ('focal_id', 'reference_id'))):
            return None
    fingerprints = [value['scene_fingerprint'] for value in (metadata, route, observation, residual)
                    if 'scene_fingerprint' in value]
    if any(not isinstance(value, str) or len(value) != 64
           or any(character not in '0123456789abcdef' for character in value)
           for value in fingerprints):
        return None
    if fingerprints and any(value != fingerprints[0] for value in fingerprints[1:]):
        return None
    canvas = observation.get('canvas')
    if 'canvas' in observation:
        if (not isinstance(canvas, dict)
                or canvas.get('unit') != 'm' or canvas.get('coordinate_frame') != 'world'):
            return None
        for field in ('views', 'supplemental_views'):
            if field in canvas:
                if (not isinstance(canvas[field], list)
                        or any(not isinstance(view, dict) for view in canvas[field])):
                    return None
                for view in canvas[field]:
                    if (('unit' in view and view['unit'] != 'm')
                            or ('coordinate_frame' in view and view['coordinate_frame'] != 'world')):
                        return None
    for attention in (observation.get('attention'),
                      canvas.get('attention') if isinstance(canvas, dict) else None):
        if attention is not None and not isinstance(attention, dict):
            return None
    # Check all original receipt values are finite before building any aliases.
    json.dumps(metadata, ensure_ascii=True, allow_nan=False)
    brief = {key: copy.deepcopy(value) for key, value in metadata.items() if key != 'routing'}
    seen = {}
    brief['endpoint_observation'] = _deduplicate(observation, '#/endpoint_observation', seen)
    route_fields = {key: value for key, value in route.items() if key != 'context_text'}
    # The routing container also owns the explicit context pointer, so it must
    # stay physical even if an unknown endpoint field duplicates its contents.
    brief['routing'] = {
        key: _deduplicate(value, '#/routing/' + key.replace('~', '~0').replace('/', '~1'), seen)
        for key, value in route_fields.items()}
    brief['routing']['context_observation_ref'] = '#/endpoint_observation'
    brief['response_detail'] = 'brief'
    brief['segment_brief'] = {
        'revision': SEGMENT_BRIEF_REVISION,
        'reference_encoding': 'local_pointer_with_object_id',
        'reference_base': 'this_same_tool_result_metadata',
        'scope': 'exact_value_transport_only_no_geometry_or_authority_change',
        'execution_authority': False,
        'omitted_diagnostics': [],
        'context_text_original_path': '#/routing/context_text',
        'context_text_representation': '#/endpoint_observation',
        'context_text_equivalence': 'strict_decoded_json_value_not_raw_string_bytes',
        'receipt_fields_unchanged': True,
        'native_image_bytes_changed': False,
    }
    return brief
