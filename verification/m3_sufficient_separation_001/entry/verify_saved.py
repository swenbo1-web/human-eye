"""Recompute public support certificates and surface witnesses from saved inputs."""

import argparse
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUAL = ROOT / 'verification/spatial_task_qualification_001'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_bytes())


def primitive_difference(points):
    difference = [F(b) - F(a) for a, b in zip(points['a'], points['b'])]
    denominator = math.lcm(*(value.denominator for value in difference))
    integers = [value.numerator * (denominator // value.denominator) for value in difference]
    divisor = math.gcd(*integers)
    assert divisor > 0
    return [value // divisor for value in integers]


def verify_support(fact, points, left, right):
    assert fact['status'] == 'measured' and fact['value'] == 'separated'
    assert fact['certificate'] == 'strict_all_referenced_vertex_support'
    assert fact['geometry_scope'] == 'referenced_triangle_unions_and_their_vertex_convex_hulls'
    evidence = fact['support_evidence']
    assert evidence['proposal'] == 'first_public_nearest_points_difference'
    direction = evidence['primitive_direction']
    assert direction == primitive_difference(points)
    origin = [F(*value) for value in evidence['origin']]
    factor = evidence['factor']
    assert type(factor) is int and factor > 0 and factor & (factor - 1) == 0
    supports = []
    for mesh in (left, right):
        indices = sorted({index for face in mesh['triangles'] for index in face})
        values = []
        for index in indices:
            position = [(F(value) - start) * factor
                        for value, start in zip(mesh['vertices_world'][index], origin)]
            assert all(value.denominator == 1 for value in position)
            projection = sum(axis * value for axis, value in zip(direction, position))
            values.append((projection, index))
        supports.append(values)
    assert evidence['referenced_counts'] == [len(values) for values in supports]
    left_max = max(value for value, _ in supports[0])
    right_min = min(value for value, _ in supports[1])
    assert left_max == evidence['left_max'] and right_min == evidence['right_min']
    assert right_min > left_max
    assert evidence['left_vertex_index'] == min(index for value, index in supports[0] if value == left_max)
    assert evidence['right_vertex_index'] == min(index for value, index in supports[1] if value == right_min)
    return {'passed': True, 'full_referenced_vertex_counts': evidence['referenced_counts'],
            'strict_support': True, 'proposal_matches_current_public_witness': True}


def verify_pair(row, left, right, reference, witness, *, spatial):
    surface = row['facts']['surface_proximity']
    assert surface['status'] == surface['witness_status'] == 'measured'
    value = surface['value']
    distance = value['distance_m']
    assert reference['distance_lower_m'] - 1e-6 <= distance <= reference['distance_upper_m'] + 1e-6
    points = value['nearest_witness']
    proof = witness.certify_pair(points['a'], points['b'], distance, left, right,
                                 position_tolerance_m=1e-9, distance_tolerance_m=1e-6)
    assert proof['passed']
    result = {'distance_m': distance, 'surface_passed': True, 'witness': proof}
    if spatial:
        result['support'] = verify_support(row['facts']['spatial_relation'], points, left, right)
        gap = row['separation_gap']
        assert gap['status'] == 'measured' and gap['value'] == distance
        decision = ('not_satisfied' if distance + 1e-6 < .004 else
                    'satisfied' if distance - 1e-6 >= .004 else 'unknown')
        if 'minimum_4mm' in reference:
            assert decision == reference['minimum_4mm']
        result.update(separation_gap_passed=True, minimum_4mm=decision)
    else:
        relation = row['facts']['closed_solid_relation']
        assert relation['status'] == 'unknown' and relation['reason'] == 'closed_solid_work_budget'
        assert row['separation_gap']['status'] == 'unknown'
        result['legacy_closed_failure_preserved'] = True
    return result


def verify(folder):
    started = time.perf_counter_ns()
    binding = read(folder / 'INPUT_BINDINGS.json')
    for path, expected in binding['source_files'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    snapshot = read(folder / 'ACTUAL_SNAPSHOT.json')
    binder = load('_sufficient_actual_binding', QUAL / 'oracle/verify_actual.py')
    actual_binding = binder.bind_actual(snapshot)
    assert actual_binding['passed']
    entry = load('_sufficient_entry', HERE / 'run_entry.py')
    witness = load('_sufficient_witness', HERE / 'witness_oracle.py')
    execution = read(folder / 'RESULTS.json')
    assert execution['harness_execution_complete'] and not execution['errors']
    assert execution['source_files_unchanged']
    rows = {row['request']['id']: row['body'] for row in execution['business']}
    assert list(rows) == ['directory', 'spatial_assembly_task', 'legacy_assembly_task', 'spatial_control_task']
    names = entry.verify_directory(rows['directory'], snapshot)
    meshes = {row['name']: row for row in snapshot['objects']}
    oracle_path = QUAL / 'oracle/formal_replay_01/ORACLE.json'
    oracle = read(oracle_path)
    tasks = []
    for label, target, candidates, references, spatial in (
            ('spatial_assembly_task', 'Target', ('Peer_000', 'Competing_001', 'Near_003'), oracle['pairs'], True),
            ('legacy_assembly_task', 'Target', ('Peer_000', 'Competing_001', 'Near_003'), oracle['pairs'], False),
            ('spatial_control_task', 'Control_A', ('Control_B',), (oracle['control'],), True)):
        body = rows[label]
        assert body['schema_version'] == ('task-query-set-v2' if spatial else 'task-query-set-v1')
        assert body['binding']['runtime_source_sha256'] == binding['ready']['source_sha256']
        assert [item['object_id'] for item in body['binding']['objects']] == [names[name] for name in (target, *candidates)]
        assert len(body['pairs']) == len(candidates)
        pairs = []
        for index, (candidate, reference) in enumerate(zip(candidates, references)):
            row = body['pairs'][index]
            assert row['candidate_index'] == index and row['object_id'] == names[candidate]
            result = verify_pair(row, meshes[target], meshes[candidate], reference, witness, spatial=spatial)
            result['candidate'] = candidate
            pairs.append(result)
        summary = body['summary']
        if spatial:
            winner = 'Peer_000' if label == 'spatial_assembly_task' else 'Control_B'
            assert body['status'] == 'observed'
            assert summary['nearest_separated_complete'] is True
            assert summary['nearest_separated_ids'] == [names[winner]]
            assert summary['penetration_set_complete'] is True and summary['penetrating_ids'] == []
        else:
            assert body['status'] == 'partial'
            assert summary['nearest_separated_complete'] is False and summary['nearest_separated_ids'] is None
        tasks.append({'label': label, 'passed': True, 'pairs': pairs, 'summary': summary})
    scopes = execution['scope_counts']
    assert scopes['business_observe_attempts'] == scopes['business_received_responses'] == scopes['business_host_RPC'] == 4
    assert scopes['QA_snapshot_host_RPC'] == scopes['close_host_RPC'] == 1
    assert execution['all_actual_host_RPC_including_QA_and_close'] == 6
    assert execution['native_close']['exit_code'] == 0 and execution['native_close']['process_reaped']
    runtime = execution['product_runtime_exit']
    assert runtime['confirmed'] and runtime['exited'] and runtime['handle_closed'] and runtime['exit_code'] == 0
    assert execution['closed']['initial_geometry_fingerprint'] == execution['closed']['final_geometry_fingerprint']
    return {'passed': True, 'tasks': tasks, 'actual_source_binding': actual_binding,
            'new_contract_assembly_passed': True, 'legacy_failure_preserved': True,
            'control_passed': True, 'cleanup_passed': True,
            'source_sha256': binding['ready']['source_sha256'], 'source_count': 137,
            'oracle_sha256': hashlib.sha256(oracle_path.read_bytes()).hexdigest(),
            'elapsed_ns': time.perf_counter_ns() - started, 'product_calls': 0, 'model_calls': 0,
            'scope': 'saved input and certificate replay, with independent rational support and surface checks'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run.resolve())
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'legacy_failure_preserved': True}))
