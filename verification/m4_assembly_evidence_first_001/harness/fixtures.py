"""Build deterministic offline host packets from pinned historical arrays."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNTIME = Path('D:/he_m4_assembly_evidence_first_001')
PREVIOUS = Path('D:/he_m4_live_assembly_relation_task_001')
PRIOR_NS = ROOT / 'verification/m4_live_assembly_relation_task_001'
SECOND_FILES = {
    'asset': ('verification/m4_local_relation_consumption_001/input/scene.blend',
              '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'),
    'geometry': ('verification/m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json',
                 'daa66107b5b6787dd0083ba5794cb9507218ab8717ee57eb593b749616fd65ab'),
    'snapshot': ('verification/m4_observation_baseline_001/preflight/SOURCE_SNAPSHOT.json',
                 'ba46e235d6493c193bec7d79b741f2781badda7921aea2537491b609ec6eea4d'),
    'truth': ('verification/m4_local_relation_consumption_001/scoring/TRUTH.json',
              '2bb917d6d96bfec4b8dffbdbc437f70185f532877e9bcb45855ea2d988e6a1b2'),
}
ASSEMBLY001_WIRE = PREVIOUS / 'slots/P1/native/WIRE/001/RESPONSE.bin'
ASSEMBLY001_WIRE_SHA = '6c213ec1e9ccf20042129c40221edd10455a7aa0c039f59ff57fbde23f19ca2a'
NAMES = ('N16', 'N13', 'N08', 'N28')
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
CASES = ('second_assembly', 'assembly001', 'touching', 'coplanar_overlap',
         'publication_limit', 'wrong_scope', 'stale_capture')
DETAILS = ('brief', 'default', 'full')
CORNERS = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
           (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
TRIANGLES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def save(path, value):
    with path.open('xb') as stream:
        stream.write(compact(value) + b'\n')


def pinned(path, expected):
    raw = path.read_bytes()
    require(sha(raw) == expected, f'frozen input changed: {path}')
    return raw


def scene(label, meshes, *, producer_source, revision=1, state=None):
    selected = 'selected_objects'
    epoch = sha(('offline-fixture:' + label).encode())
    return {'unit': 'm', 'coordinate_frame': 'world', 'source': producer_source,
        'revision': f'offline:{label}:{revision}', 'capture_scope': selected,
        'capture_state': {'instance_id': f'offline:{label}', 'epoch': 1, 'revision': revision,
                          'selection_key': 'explicit-task-four-objects'} if state is None else state,
        'task_selection': {'selectors': [{'name': mesh['name']} for mesh in meshes],
            'bindings': [{key: mesh[key] for key in ('name', 'object_id')} for mesh in meshes],
            'pair_reason': None, 'candidate_count': len(meshes)},
        'host_identity': {'schema_version': '1.0', 'document_epoch': epoch,
            'object_instances': {mesh['object_id']: f'offline-instance:{index}'
                                 for index, mesh in enumerate(meshes)}, 'capture_scope': selected},
        'meshes': meshes}


def second_assembly():
    inputs = {role: pinned(ROOT / path, digest) for role, (path, digest) in SECOND_FILES.items()}
    source = json.loads(inputs['geometry'])
    snapshot = json.loads(inputs['snapshot'])
    truth = json.loads(inputs['truth'])
    require(source['source_sha256'] == truth['source_scene_sha256'] == SECOND_FILES['asset'][1]
            and truth['source_world_geometry_sha256'] == SECOND_FILES['geometry'][1]
            and source['unit'] == 'm' and source['coordinate_frame'] == 'world'
            and snapshot['unit_scale_m'] == 1.0 and len(source['objects']) == len(snapshot['objects']) == 28,
            'second assembly original provenance changed')
    by_name = {mesh['name']: mesh for mesh in source['objects']}
    by_snapshot = {mesh['name']: mesh for mesh in snapshot['objects']}
    require(len(by_name) == len(by_snapshot) == 28 and set(by_name) == set(by_snapshot),
            'source and snapshot object coverage differ')
    meshes = []
    for name in NAMES:
        mesh, raw = by_name[name], by_snapshot[name]
        require(mesh['object_id'] == name and mesh['local_vertices'] == raw['vertices_local']
                and mesh['matrix_world'] == raw['matrix_world'] and mesh['polygons'] == raw['faces']
                and mesh['world_vertices'] == mesh['vertices'] and mesh['triangles'] == mesh['faces'],
                f'snapshot does not match saved producer mesh: {name}')
        recomputed = [[sum(raw['matrix_world'][row][column] * v[column] for column in range(3))
                       + raw['matrix_world'][row][3] for row in range(3)] for v in raw['vertices_local']]
        require(recomputed == mesh['world_vertices'], f'world coordinate mapping differs: {name}')
        meshes.append({'object_id': name, 'name': name, 'mark_label': '#' + name,
                       'vertices': mesh['world_vertices'], 'faces': mesh['triangles']})
    capture = scene('second-assembly', meshes, producer_source='offline_saved_world_geometry')
    capture['task_selection']['candidate_count'] = len(source['objects'])
    return capture, capture, {'kind': 'saved real arrays with simulated current capture identity',
        'pins': SECOND_FILES, 'saved_object_count': 28,
        'mesh_domain': 'saved oriented triangle rows; native source polygons independently checked and kept separate',
        'frame_or_file_attestation_admitted_to_product': False}


def assembly001():
    wire = json.loads(pinned(ASSEMBLY001_WIRE, ASSEMBLY001_WIRE_SHA))
    output = wire['result']['result']
    require(wire['status'] == 'success' and wire['result']['executed'] is True
            and output.startswith(PREFIX) and output.endswith('\n'), 'assembly001 archived wire invalid')
    payload = json.loads(output[len(PREFIX):-1])['result']
    require(payload['schema'] == 'human-eye-scene-delta-v1', 'assembly001 delta schema changed')
    capture = deepcopy(payload['capture'])
    resources = {record['id']: record for record in payload['resources']}
    for mesh in capture['meshes']:
        reference = mesh.pop('_scene_resource')
        resource = resources[reference['id']]
        require(resource['revision'] == reference['revision'], 'archive resource revision mismatch')
        matrix, scale = reference['matrix'], reference['scale']
        mesh['vertices'] = [[(sum(matrix[row][column] * point[column] for column in range(3))
                             + matrix[row][3]) * scale for row in range(3)]
                            for point in resource['vertices_local']]
        mesh['faces'], mesh['edges'] = resource['faces'], resource['edges']
    require(len(capture['meshes']) == 4 and sum(len(x['vertices']) for x in capture['meshes']) == 72
            and sum(len(x['faces']) for x in capture['meshes']) == 132, 'assembly001 array counts changed')
    return payload, capture, {'kind': 'exact original production host payload of assembly001',
        'wire': str(ASSEMBLY001_WIRE), 'wire_sha256': ASSEMBLY001_WIRE_SHA,
        'transport_note': 'New MCP/RPC correlation ID only, existing resource payload repeated.'}


def boxes(label, positions, common_origin=0.0):
    meshes = []
    for index, offset in enumerate(positions):
        name = f'T{index}'
        vertices = [[common_origin + origin + 2.0 * value for value, origin in zip(corner, offset)]
                    for corner in CORNERS]
        meshes.append({'object_id': name, 'name': name, 'mark_label': '#' + name,
                       'vertices': vertices, 'faces': [list(face) for face in TRIANGLES]})
    return scene(label, meshes, producer_source='offline_synthetic_control')


def fixture(case, index):
    if case == 'second_assembly':
        return second_assembly()
    if case == 'assembly001':
        return assembly001()
    if case == 'stale_capture':
        _, capture, metadata = second_assembly()
        if index:
            # A distinct current generation with the same selection; the old
            # transverse proof must disappear when the former candidate moves.
            capture['capture_state']['revision'] = 2
            capture['revision'] = 'offline:second-assembly:2'
            mesh = next(mesh for mesh in capture['meshes'] if mesh['name'] == 'N13')
            mesh['vertices'] = [[x + 2., y, z] for x, y, z in mesh['vertices']]
        return capture, capture, {'kind': 'new generation after one source edit', 'base': metadata,
                                   'capture_index': index, 'N13_translation_x_m': 2.0 if index else 0.0}
    if case == 'wrong_scope':
        _, capture, metadata = second_assembly()
        capture['capture_scope'] = 'complete_scene_meshes'
        return capture, capture, {'kind': 'wrong capture domain', 'base': metadata}
    if case == 'publication_limit':
        _, capture, metadata = second_assembly()
        translation = 2. ** 24
        for mesh in capture['meshes']:
            mesh['vertices'] = [[value + translation for value in vertex] for vertex in mesh['vertices']]
        capture = scene('publication-limit', capture['meshes'], producer_source='offline_synthetic_control')
        return capture, capture, {'kind': 'positive crossing with world-coordinate publication limit',
                                  'base': metadata, 'offset_on_each_axis_m': translation}
    offsets = {'touching': (2., 2., 0.), 'coplanar_overlap': (2., .8, .6)}
    capture = boxes(case, [(0., 0., 0.), offsets[case], (4., 0., 0.), (7., 0., 0.)])
    return capture, capture, {'kind': 'synthetic exact input control', 'offsets': offsets[case]}
