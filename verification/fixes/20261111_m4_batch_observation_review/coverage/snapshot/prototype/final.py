"""Two explicit projections of one frozen saved observation bundle.

The input contains already captured world geometry and existing relation facts.
Faces retain their recorded topology kind.
This offline prototype makes no host requests and retains no additional cache.
"""

import argparse
import copy
import json
from pathlib import Path


OBJECT_FIELDS = ('vertices_world', 'faces')


def directory(bundle):
    """Return the ordinary spatial directory without vertex or face payloads."""
    objects, gaps = [], []
    for item in bundle['objects']:
        row = {'object_id': item['object_id'], 'name': item['name']}
        vertices = item.get('vertices_world')
        if vertices:
            lower = [min(point[axis] for point in vertices) for axis in range(3)]
            upper = [max(point[axis] for point in vertices) for axis in range(3)]
            row['aabb'] = {'min': lower, 'max': upper}
        else:
            row['aabb'] = None
            gaps.append({'object_id': item['object_id'],
                         'reason': 'world_geometry_not_available'})
        objects.append(row)
    return {'status': 'partial' if gaps else 'observed',
            'source': copy.deepcopy(bundle['source']),
            'unit': bundle['unit'], 'coordinate_frame': bundle['coordinate_frame'],
            'objects': objects, 'gaps': gaps}


def selected_observation(bundle, request):
    """Combine caller-selected geometry and recorded ordered-pair fact fields."""
    result = {'status': 'observed', 'source': copy.deepcopy(bundle['source']),
              'unit': bundle['unit'], 'coordinate_frame': bundle['coordinate_frame'],
              'objects': [], 'relations': [], 'gaps': []}
    if request['source'] != bundle['source']:
        result['status'] = 'unknown'
        result['gaps'].append({'reason': 'source_mismatch'})
        return result
    by_id = {item['object_id']: item for item in bundle['objects']}
    for selection in request.get('objects', []):
        object_id = selection['object_id']
        item = by_id.get(object_id)
        if item is None:
            result['gaps'].append({'object_id': object_id,
                                   'reason': 'object_not_in_capture'})
            continue
        row = {'object_id': object_id, 'name': item['name']}
        for field in selection['fields']:
            if field not in OBJECT_FIELDS or field not in item:
                result['gaps'].append({'object_id': object_id, 'field': field,
                                       'reason': 'object_field_not_available'})
                continue
            row[field] = copy.deepcopy(item[field])
            if field == 'faces':
                row['face_kind'] = item['face_kind']
        result['objects'].append(row)
    by_pair = {(item['target_id'], item['candidate_id']): item
               for item in bundle['relations']}
    for selection in request.get('relation_pairs', []):
        pair = (selection['target_id'], selection['candidate_id'])
        item = by_pair.get(pair)
        if item is None:
            result['gaps'].append({'target_id': pair[0], 'candidate_id': pair[1],
                                   'reason': 'ordered_relation_not_in_capture'})
            continue
        row = {'target_id': pair[0], 'candidate_id': pair[1], 'facts': {}}
        for field in selection['fields']:
            if field not in item['facts']:
                result['gaps'].append({'target_id': pair[0], 'candidate_id': pair[1],
                                       'field': field, 'reason': 'relation_field_not_available'})
                continue
            row['facts'][field] = copy.deepcopy(item['facts'][field])
        result['relations'].append(row)
    if result['gaps']:
        result['status'] = 'partial'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('directory', 'selected'))
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_bytes())
    if args.phase == 'directory':
        result = directory(bundle)
    else:
        if args.request is None:
            parser.error('selected requires --request')
        request = json.loads(args.request.read_bytes())
        result = selected_observation(bundle, request)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False))


if __name__ == '__main__':
    main()
