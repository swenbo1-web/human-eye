"""Verify saved qualification facts, exact distance bounds and public witnesses."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def point(values):
    return tuple(F(value) for value in values)


def sub(left, right):
    return tuple(a - b for a, b in zip(left, right))


def dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def triangle_contains(mesh, position):
    for face in mesh['triangles']:
        a, b, c = [point(mesh['vertices_world'][index]) for index in face]
        u, v, offset = sub(b, a), sub(c, a), sub(position, a)
        normal = cross(u, v)
        squared = dot(normal, normal)
        if not squared or dot(normal, offset):
            continue
        first = dot(cross(offset, v), normal) / squared
        second = dot(cross(u, offset), normal) / squared
        if first >= 0 and second >= 0 and first + second <= 1:
            return True
    return False


def main():
    batch = Path(__file__).resolve().parent
    run = batch / 'entry/run_01'
    result = read(run / 'RESULTS.json')
    binding = read(run / 'INPUT_BINDINGS.json')
    snapshot = read(run / 'ACTUAL_SNAPSHOT.json')
    oracle = read(batch / 'oracle/formal_replay_01/ORACLE.json')
    assert result['harness_execution_complete'] and not result['errors']
    assert read(batch / 'oracle/formal_replay_01/RESULTS.json')['passed']
    assert oracle['binding']['passed'] and oracle['binding']['original_12_source_bound']
    for name, expected in binding['source_files'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
    meshes = {row['name']: row for row in snapshot['objects']}
    assert len(meshes) == 14
    assert sum(len(mesh['vertices_world']) for mesh in meshes.values()) == 848
    assert sum(len(mesh['triangles']) for mesh in meshes.values()) == 1640
    original = read(batch.parents[1] / 'verification/scale_diag_001/fixtures/G508.json')
    for old in original['objects']:
        for key in ('vertices_local', 'vertices_world', 'matrix_world', 'triangles', 'logical_id'):
            assert meshes[old['name']][key] == old[key], (old['name'], key)
    rows = {row['request']['id']: row for row in result['business']}
    assert list(rows) == ['directory', 'assembly_task', 'control_task']
    directory = rows['directory']['body']
    assert directory['status'] == 'complete' and len(directory['objects']) == 14
    for row in directory['objects']:
        vertices = meshes[row['name']]['vertices_world']
        lower = [min(p[axis] for p in vertices) for axis in range(3)]
        upper = [max(p[axis] for p in vertices) for axis in range(3)]
        assert row['bbox_min'] == lower and row['bbox_max'] == upper
        assert row['center'] == [float((F(a) + F(b)) / 2) for a, b in zip(lower, upper)]
    assembly = rows['assembly_task']['body']
    assert assembly['status'] == 'partial'
    assert assembly['summary']['nearest_separated_complete'] is False
    assert assembly['summary']['nearest_separated_ids'] is None
    for pair in assembly['pairs']:
        for field, reason in (('surface_proximity', 'surface_geometry_work_limit'),
                              ('closed_solid_relation', 'closed_solid_geometry_work_limit')):
            assert pair['facts'][field]['status'] == 'unknown'
            assert pair['facts'][field]['value'] is None and pair['facts'][field]['reason'] == reason
    certificates = []
    for certificate in oracle['pairs']:
        left, right = meshes['Target'], meshes[certificate['candidate_name']]
        normal = tuple(F(*item) for item in certificate['support_normal'])
        first = max(dot(normal, point(p)) for p in left['vertices_world'])
        second = min(dot(normal, point(p)) for p in right['vertices_world'])
        gap = second - first
        assert gap > 0 and gap == F(*certificate['support_gap'])
        lower_squared = gap * gap / dot(normal, normal)
        witness = certificate['witness']
        positions = []
        for mesh, suffix in ((left, 'a'), (right, 'b')):
            face = mesh['triangles'][witness['triangle_' + suffix]]
            weights = [F(*v) for v in witness['barycentric_' + suffix]]
            assert sum(weights) == 1 and min(weights) >= 0
            positions.append(tuple(sum(weights[j] * F(mesh['vertices_world'][face[j]][axis])
                                       for j in range(3)) for axis in range(3)))
        delta = sub(positions[1], positions[0])
        upper_squared = dot(delta, delta)
        assert upper_squared == F(*witness['squared_distance'])
        assert F(certificate['distance_lower_m']) ** 2 <= lower_squared <= upper_squared
        assert upper_squared <= F(certificate['distance_upper_m']) ** 2
        assert certificate['relation_qualified'] and certificate['solid_relation'] == 'separated'
        threshold = F(1, 250)
        decision = ('satisfied' if F(certificate['distance_lower_m']) >= threshold else
                    'not_satisfied' if F(certificate['distance_upper_m']) < threshold else 'unknown')
        assert decision == certificate['minimum_4mm']
        certificates.append({'name': certificate['candidate_name'], 'minimum_4mm': decision,
                             'lower_m': certificate['distance_lower_m'],
                             'upper_m': certificate['distance_upper_m']})
    winner = min(certificates, key=lambda row: row['upper_m'])
    assert all(row is winner or winner['upper_m'] < row['lower_m'] for row in certificates)
    assert winner['name'] == oracle['three_candidate_nearest']['name'] == 'Peer_000'
    control = rows['control_task']['body']['pairs'][0]['facts']
    assert control['closed_solid_relation']['value'] == 'separated'
    proximity = control['surface_proximity']
    assert proximity['status'] == 'measured' and proximity['value']['distance_m'] == 1.
    public_witness = proximity['value']['nearest_witness']
    a, b = point(public_witness['a']), point(public_witness['b'])
    assert triangle_contains(meshes['Control_A'], a)
    assert triangle_contains(meshes['Control_B'], b)
    assert dot(sub(b, a), sub(b, a)) == 1
    wires = read(run / 'native/WIRE/INDEX.json')
    assert len(wires) == 5
    for wire in wires:
        folder = run / 'native/WIRE' / str(wire['sequence']).zfill(3)
        assert len((folder / 'REQUEST.bin').read_bytes()) == wire['request_bytes']
        assert len((folder / 'RESPONSE.bin').read_bytes()) == wire['response_attempted_bytes']
        assert wire['response_sendall_completed']
    assert result['native_close']['exit_code'] == 0 and result['native_close']['process_reaped']
    assert all(result['product_runtime_exit'][key] is True for key in ('confirmed', 'exited', 'handle_closed'))
    assert result['product_runtime_exit']['exit_code'] == 0
    verification = {'cycle_id': 'SPATIAL-TASK-QUALIFICATION-001', 'passed': True,
                    'scope': 'saved raw bytes, exact support/witness arithmetic, actual public witness and source checks',
                    'assembly_business_complete': False, 'control_business_complete': True,
                    'directory_objects': 14, 'assembly_pairs_unknown': 3, 'control_pairs_measured': 1,
                    'independent_certificates': certificates, 'independent_nearest': winner['name'],
                    'public_control_witness_valid': True, 'actual_host_RPC': len(wires),
                    'formal_business_observe': 3, 'new_business_calls': 0, 'new_Blender_sessions': 0,
                    'model_consumers': 0}
    with (batch / 'SAVED_VERIFICATION.json').open('x', encoding='utf8', newline='\n') as output:
        json.dump(verification, output, indent=2)
        output.write('\n')
    print(json.dumps(verification))


if __name__ == '__main__':
    main()
