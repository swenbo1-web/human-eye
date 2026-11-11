"""Reasonable native batch projection of the same retained saved information.

This module reads ordinary dictionaries. The caller supplies the same captured
geometry, existing relation facts and selection used by the prototype. It does
not acquire geometry, evaluate relations or keep another scene cache.
"""
import copy


def directory(bundle):
    rows = []
    gaps = []
    for mesh in bundle['objects']:
        row = {'object_id': mesh['object_id'], 'name': mesh['name']}
        vertices = mesh.get('vertices_world')
        if vertices:
            axes = tuple(zip(*vertices))
            lower = [min(values) for values in axes]
            upper = [max(values) for values in axes]
            row['aabb'] = {'min': lower, 'max': upper}
        else:
            row['aabb'] = None
            gaps.append({'object_id': mesh['object_id'],
                         'reason': 'world_geometry_not_available'})
        rows.append(row)
    return {'status': 'partial' if gaps else 'observed',
            'source': copy.deepcopy(bundle['source']),
            'unit': bundle['unit'], 'coordinate_frame': bundle['coordinate_frame'],
            'objects': rows, 'gaps': gaps}


def selected_observation(bundle, request):
    response = {'status': 'observed', 'source': copy.deepcopy(bundle['source']),
                'unit': bundle['unit'], 'coordinate_frame': bundle['coordinate_frame'],
                'objects': [], 'relations': [], 'gaps': []}
    if request['source'] != bundle['source']:
        response['status'] = 'unknown'
        response['gaps'].append({'reason': 'source_mismatch'})
        return response
    objects = {mesh['object_id']: mesh for mesh in bundle['objects']}
    relations = {(pair['target_id'], pair['candidate_id']): pair['facts']
                 for pair in bundle['relations']}
    for selection in request.get('objects', []):
        object_id = selection['object_id']
        mesh = objects.get(object_id)
        if mesh is None:
            response['gaps'].append({'object_id': object_id,
                                     'reason': 'object_not_in_capture'})
            continue
        row = {'object_id': object_id, 'name': mesh['name']}
        for field in selection['fields']:
            if field in ('vertices_world', 'faces') and field in mesh:
                row[field] = copy.deepcopy(mesh[field])
                if field == 'faces':
                    row['face_kind'] = mesh['face_kind']
            else:
                response['gaps'].append({'object_id': object_id, 'field': field,
                                         'reason': 'object_field_not_available'})
        response['objects'].append(row)
    for selection in request.get('relation_pairs', []):
        target = selection['target_id']
        candidate = selection['candidate_id']
        facts = relations.get((target, candidate))
        if facts is None:
            response['gaps'].append({'target_id': target, 'candidate_id': candidate,
                                     'reason': 'ordered_relation_not_in_capture'})
            continue
        row = {'target_id': target, 'candidate_id': candidate, 'facts': {}}
        for field in selection['fields']:
            if field in facts:
                row['facts'][field] = copy.deepcopy(facts[field])
            else:
                response['gaps'].append({'target_id': target, 'candidate_id': candidate,
                                         'field': field, 'reason': 'relation_field_not_available'})
        response['relations'].append(row)
    if response['gaps']:
        response['status'] = 'partial'
    return response
