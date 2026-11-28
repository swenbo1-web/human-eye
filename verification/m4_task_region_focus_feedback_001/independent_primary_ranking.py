"""Recheck closed-box membership and the chosen primary from closed evidence."""
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path


def read_json(path):
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def require(condition, description):
    if not condition:
        raise ValueError(description)


def exact_rows(mesh, reference, world_box):
    points = [tuple(map(Fraction, point)) for point in mesh['vertices']]
    reference_coords = zip(*[tuple(map(Fraction, point)) for point in reference['vertices']])
    reference_bounds = [(min(axis), max(axis)) for axis in reference_coords]
    bounds = list(zip(map(Fraction, world_box['min']), map(Fraction, world_box['max'])))
    group, ranked = [], []
    for index, face in enumerate(mesh['faces']):
        triangle = [points[point] for point in face]
        if not all(lo <= v <= hi for point in triangle for (lo, hi), v in zip(bounds, point)):
            continue
        group.append(index)
        u, v = [[point[i] - triangle[0][i] for i in range(3)] for point in triangle[1:]]
        n = tuple(u[(i + 1) % 3] * v[(i + 2) % 3] - u[(i + 2) % 3] * v[(i + 1) % 3] for i in range(3))
        if not any(n):
            continue
        centroid = tuple(sum(axis) / 3 for axis in zip(*triangle))
        squared_distance = sum(max(lo - v, v - hi, 0) ** 2 for (lo, hi), v in zip(reference_bounds, centroid))
        ranked.append((squared_distance, index, centroid, n))
    distance, index, centroid, n = min(ranked)
    scale = max(map(abs, n))
    direction = [float(component / scale) for component in n]
    length = math.hypot(*direction)
    normal = [component / length for component in direction]
    ties = [rank[1] for rank in ranked if rank[0] == distance]
    return group, index, centroid, normal, distance, ties


def inspect_case(path, current, inputs, labels, number, name):
    source, source_sha = current
    meshes = {mesh['name']: mesh for mesh in source['meshes']}
    task = inputs[name]
    world_box = task['world_box_m']
    target, reference = task['target'], task['reference']
    group, index, centroid, normal, distance, ties = exact_rows(meshes[target], meshes[reference], world_box)
    request, request_sha = read_json(path / f'{number:02d}-{name}.tx')
    reply, reply_sha = read_json(path / f'{number:02d}-{name}.rx')
    record, record_sha = read_json(path / f'producer_{number:02d}.json')
    expected_focus = {'task_region': {'reference': {'name': reference}, 'world_box_m': world_box}}
    require(request['id'] == reply['id'] == number and request['params'] == {
        'name': 'human_eye_scene_observe', 'arguments': {'include_image': True, 'response_detail': 'full',
            'query': {'mode': 'active_observation', 'objects': [{'name': target}], 'focus': expected_focus}}},
        f'{name}: original MCP request differs from frozen task')
    require(reply['result']['isError'] is False, f'{name}: original MCP response is an error')
    reply_text, = [block['text'] for block in reply['result']['content'] if block['type'] == 'text']
    public = json.loads(reply_text)
    focus = record['facts']['focus']
    require(focus == public['facts']['focus'] and public['binding'] == record['binding'],
            f'{name}: producer and MCP differ')
    require(focus['selection'] == expected_focus and focus['reference']['object_name'] == reference,
            f'{name}: focus input or reference differs')
    require(public['binding']['capture_state'] == source['capture_state']
            and public['binding']['scene_revision'] == source['revision'],
            f'{name}: source differs from published capture')
    require(group == labels[name]['source_triangle_indices'] == focus['task_source_triangle_indices']
            == focus['region_ref']['source_triangle_indices'], f'{name}: closed-box group differs')
    require(index == focus['primary_source_triangle_index'], f'{name}: exact primary differs')
    require(list(map(float, centroid)) == focus['source_triangle_centroid_world_m'],
            f'{name}: primary centroid differs')
    normal_diff = math.dist(normal, focus['front_normal_world'])
    require(normal_diff <= 3e-16, f'{name}: primary normal differs')
    corrections = [frame for frame in record['constructed_frames'] if frame['view_name'] == 'FOCUS']
    require(len(corrections) <= 1, f'{name}: extra correction frame')
    correction_diff = None
    if corrections:
        correction_diff = math.dist(normal, corrections[0]['pose']['target_to_eye_unit'])
        require(correction_diff <= 3e-16, f'{name}: correction camera direction differs')
    return {
        'task': name, 'reference': reference, 'slot': path.name, 'group_size': len(group),
        'primary': index, 'equal_nearest_source_rows': ties, 'squared_distance_m2': str(distance),
        'normal_difference': normal_diff, 'correction_camera_direction_difference': correction_diff,
        'views_as_reported': focus['views'], 'post_capture_sha256': source_sha,
        'mcp_tx_sha256': request_sha, 'mcp_rx_sha256': reply_sha, 'producer_sha256': record_sha,
    }


def main():
    root = Path(__file__).resolve().parent.parent
    inputs, inputs_sha = read_json(root / 'preflight' / 'TASK_INPUTS.json')
    labels, labels_sha = read_json(Path(inputs['prior_labels']['path']))
    require(labels_sha == inputs['prior_labels']['sha256'], 'Frozen labels fail their input pin')
    cases = []
    for slot, tasks in [('RAIL_TASK', ('M19', 'M21')), ('ASSEMBLY_TASK', ('N19', 'N25'))]:
        path = root / 'slots' / slot
        current = read_json(path / 'post_capture.json')
        for number, name in enumerate(tasks, 3):
            cases.append(inspect_case(path, current, inputs['tasks'], labels['tasks'], number, name))
    receipt = {'batch': root.name, 'task_inputs_sha256': inputs_sha, 'labels_sha256': labels_sha,
               'scope': 'independent exact geometry replay of four already closed task slots',
               'checked': len(cases), 'passed': len(cases) == 4, 'cases': cases}
    with (Path(__file__).resolve().parent / 'INDEPENDENT_PRIMARY_RANKING.json').open('x', encoding='utf-8') as out:
        json.dump(receipt, out, indent=2)
        out.write('\n')
    print(json.dumps({'checked': len(cases), 'passed': receipt['passed']}))


if __name__ == '__main__':
    main()
