"""Project saved records from one actor into a pinned offline input bundle."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CELL = ROOT/'verification/m4_local_relation_consumption_001/cells/lrc03/owner'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    initial = read(CELL/'INITIAL.json')
    final = read(CELL/'FINAL.json')
    assert initial == final
    response = read(CELL/'tool_02/RESPONSE.json')
    body = json.loads(response['result']['content'][0]['text'])
    frame_path = CELL/'native/call_3/stdout.txt'
    frame = frame_path.read_text('utf8')
    assert frame.startswith('HUMAN_EYE_BLENDER_MCP:')
    packet = json.loads(frame[len('HUMAN_EYE_BLENDER_MCP:'):])['result']
    capture = packet['capture']
    assert capture['unit'] == body['context']['unit'] == 'm'
    assert capture['coordinate_frame'] == body['context']['coordinate_frame'] == 'world'
    assert capture['revision'] == body['context']['scene_revision']
    originals = {row['name']: row for row in initial['objects']}
    objects = []
    for index, item in enumerate(initial['objects']):
        matrix = item['matrix_world']
        vertices = [[(sum(matrix[r][c]*point[c] for c in range(3))+matrix[r][3])
                     * initial['unit_scale_m'] for r in range(3)]
                    for point in item['vertices_local']]
        objects.append(dict(object_id='snapshot:'+str(index), name=item['name'],
            vertices_world=vertices, faces=item['faces'], face_kind='source_polygons'))
    by_name = {item['name']: item for item in objects}
    resources = {row['id']: row for row in packet['resources']}
    evidence = []
    for item in capture['meshes']:
        reference = item['_scene_resource']
        resource = resources[reference['id']]
        original = originals[item['name']]
        assert resource['vertices_local'] == original['vertices_local']
        assert reference['matrix'] == original['matrix_world']
        assert reference['scale'] == initial['unit_scale_m']
        by_name[item['name']]['faces'] = copy.deepcopy(resource['faces'])
        by_name[item['name']]['face_kind'] = 'captured_triangles'
        evidence.append(dict(name=item['name'], host_object_id=item['object_id'],
            offline_object_id=by_name[item['name']]['object_id'],
            captured_triangle_indices=resource['faces'],
            local_vertices_and_pose_match_saved_snapshot=True))
    host_by_name = {row['name']: row['host_object_id'] for row in evidence}
    target = body['target']
    assert target['object_id'] == host_by_name[target['name']]
    relations = []
    for candidate in body['candidates']:
        assert candidate['object_id'] == host_by_name[candidate['name']]
        facts = {field: {**body['measurement_contracts'].get(field, {}), **copy.deepcopy(candidate[field])}
                 for field in ('closed_solid_relation','surface_proximity','separation_gap')}
        relations.append(dict(target_id=by_name[target['name']]['object_id'],
                              candidate_id=by_name[candidate['name']]['object_id'], facts=facts))
    source = dict(kind='offline_frozen_inputs', geometry_snapshot_sha256=sha(CELL/'INITIAL.json'),
                  relation_response_sha256=sha(CELL/'tool_02/RESPONSE.json'),
                  relation_capture_sha256=sha(frame_path))
    bundle = dict(source=source, unit='m', coordinate_frame='world', objects=objects, relations=relations)
    request = dict(source=source,
        objects=[dict(object_id=by_name[row['name']]['object_id'], fields=['vertices_world','faces'])
                 for row in (target, body['candidates'][-1])],
        relation_pairs=[dict(target_id=row['target_id'], candidate_id=row['candidate_id'],
                             fields=list(row['facts'])) for row in relations])
    save(HERE/'input_02/BUNDLE.json', bundle)
    save(HERE/'input_02/REQUEST_PRIMARY.json', request)
    optional_names = [target['name'], *[row['name'] for row in body['candidates']],
                      'N24','N12','N04','N19']
    optional = copy.deepcopy(request)
    optional['objects'] = [dict(object_id=by_name[name]['object_id'], fields=['vertices_world','faces'])
                           for name in dict.fromkeys(optional_names)]
    save(HERE/'input_02/REQUEST_OPTIONAL_UNION.json', optional)
    paths = [CELL/name for name in ('INITIAL.json','FINAL.json','IDENTITY.json','CLOSE.json',
                                   'tool_02/RESPONSE.json','native/call_3/stdout.txt')]
    binding = dict(cycle_id='M4-BATCH-OBSERVATION-COVERAGE-001',
        source_paths_sha256={path.relative_to(ROOT).as_posix(): sha(path) for path in paths},
        bundle_sha256=sha(HERE/'input_02/BUNDLE.json'), actual_relation_context=body['context'],
        actual_capture_state=capture['capture_state'], selected_geometry_binding=evidence,
        ID_scope='Offline snapshot selection IDs. Actual host IDs are preserved in the binding table.',
        source_scope='Two saved observations from the same actor. Selected local vertices/pose match exactly. This is a frozen derived view, with no live currentness or atomic-host-capture assertion.',
        topology_scope='Selected capture objects retain actual evaluated triangles and their original ordinal order. Other objects retain snapshot source polygons. Every object states face_kind.',
        precision='Finite binary64 world values, round-trip JSON. Historical consumer decimal rounding is not replayed.',
        relations='Original facts with corresponding shared measurement metadata merged once into each fact. No solver executed.',
        primary_request_scope='An explicit historical caller-selection fixture, not automatic discovery or a product constant.',
        initial_read_error='An exploratory read treated the marker-prefixed host frame as bare JSON. The fixed parser handles its exact recorded protocol prefix. Original records were not modified.',
        product_processes=0, Blender_sessions=0, model_consumers=0, new_images=0)
    save(HERE/'input_02/SOURCE_BINDING.json', binding)
    print(json.dumps(dict(objects=len(objects), relation_records=len(relations),
                          bundle_sha256=binding['bundle_sha256'], product_processes=0)))


if __name__ == '__main__':
    main()
