"""Independent canonical source checks for the fixed M5 derived-view contract."""

import hashlib
import json
from fractions import Fraction


def ordered_geometry_sha256(mesh):
    value = {'vertices': mesh['vertices'], 'faces': mesh['faces']}
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def geometry_alias(mesh):
    """Derive the public image alias from the actual ordered source geometry."""
    vertices = tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices'])
    triangles = []
    for face in mesh['faces']:
        points = tuple(vertices[index] for index in face)
        triangles.append(min(points[index:] + points[:index] for index in range(3)))
    key = (tuple(sorted(vertices)), tuple(sorted(triangles)))
    raw = json.dumps(key, default=str, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'geometry:' + hashlib.sha256(raw).hexdigest()


def generation(state):
    if (type(state) is not dict or type(state.get('instance_id')) is not str or not state['instance_id']
            or type(state.get('epoch')) is not int or type(state.get('revision')) is not int):
        raise ValueError('source_generation_unavailable')
    return state['instance_id'], state['epoch'], state['revision']


def expand_ranges(ranges):
    result = []
    if type(ranges) is not list:
        raise ValueError('source_face_ranges_type')
    for interval in ranges:
        if (type(interval) is not list or len(interval) != 2
                or any(type(value) is not int for value in interval)
                or not 0 <= interval[0] <= interval[1] <= 4095):
            raise ValueError('source_face_ranges_bounds')
        result.extend(range(interval[0], interval[1]+1))
    if len(result) != len(set(result)):
        raise ValueError('source_face_ranges_overlap')
    return result


def validate_source(source, parent_binding, parent_capture, task_bindings, supplemental=None):
    """Check public mapping against actual source captures supplied by caller."""
    if (source.get('schema') != 'active-observation-task-source-v1'
            or source.get('scope') != 'whole_objects' or source.get('capture_scope') != 'observation_task_objects'):
        raise ValueError('derived_source_schema_or_scope')
    if parent_capture['capture_scope'] != 'target_observation_meshes':
        raise ValueError('parent_scope_changed')
    if (source['parent_binding_sha256'] != parent_binding['binding_sha256']
            or source['parent_source_binding_sha256'] != parent_binding['source_binding_sha256']
            or source['parent_capture_scope'] != parent_capture['capture_scope']):
        raise ValueError('parent_source_binding_mismatch')
    document = parent_capture['host_identity']['document_epoch']
    if parent_binding.get('document_epoch') != document:
        raise ValueError('parent_document_epoch_mismatch')
    if generation(source['capture_state']) != generation(parent_capture['capture_state']):
        raise ValueError('derived_parent_generation_mismatch')
    parents = {mesh['object_id']: (index, mesh) for index, mesh in enumerate(parent_capture['meshes'])}
    if len(parents) != len(parent_capture['meshes']):
        raise ValueError('parent_object_ids_duplicate')
    available = dict(parents)
    supplemental = [] if supplemental is None else supplemental
    for capture in supplemental:
        if generation(capture['capture_state']) != generation(parent_capture['capture_state']):
            raise ValueError('supplemental_generation_mismatch')
        if capture['host_identity']['document_epoch'] != document:
            raise ValueError('supplemental_document_epoch_mismatch')
        for mesh in capture['meshes']:
            if mesh['object_id'] in parents:
                raise ValueError('supplement_contains_existing_object')
            if mesh['object_id'] in available:
                raise ValueError('supplemental_object_duplicate')
            available[mesh['object_id']] = (None, mesh)
    rows = source['objects']
    expected_ids = [row['object_id'] for row in task_bindings]
    if [row['object_id'] for row in rows] != expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ValueError('derived_task_object_order_or_duplicates')
    parent_instances = parent_capture['host_identity']['object_instances']
    supplemental_instances = {oid: instance for capture in supplemental
                              for oid, instance in capture['host_identity']['object_instances'].items()}
    checks = []
    for row, binding in zip(rows, task_bindings):
        identity = row['object_id']
        if identity not in available:
            raise ValueError('derived_source_object_unavailable')
        index, mesh = available[identity]
        instance = parent_instances[identity] if index is not None else supplemental_instances[identity]
        if row['instance_id'] != instance or binding.get('instance_id', instance) != instance:
            raise ValueError('derived_source_object_instance_mismatch')
        if row['observation_object_index'] != index:
            raise ValueError('observation_object_index_mismatch')
        if index is None and row['geometry_id'] is not None:
            raise ValueError('supplement_falsely_claims_observed_geometry')
        if index is not None and row['geometry_id'] != geometry_alias(mesh):
            raise ValueError('observed_geometry_alias_mismatch')
        if row['source_triangle_count'] != len(mesh['faces']) or expand_ranges(row['source_triangle_index_ranges']) != list(range(len(mesh['faces']))):
            raise ValueError('whole_object_source_faces_incomplete')
        if row['ordered_geometry_sha256'] != ordered_geometry_sha256(mesh):
            raise ValueError('ordered_current_source_geometry_mismatch')
        checks.append({'object_id': identity, 'instance_id': instance, 'observation_object_index': index,
                       'source_triangle_count': len(mesh['faces']), 'ordered_geometry_sha256': row['ordered_geometry_sha256']})
    missing_ids = set(expected_ids)-set(parents)
    if set(available)-set(parents) != missing_ids:
        raise ValueError('supplement_not_exact_missing_object_set')
    return {'passed_checked_scope': True, 'objects': checks,
            'same_generation': list(generation(source['capture_state'])),
            'selection_key_equality_required': False, 'same_derived_fingerprint_required': False}
