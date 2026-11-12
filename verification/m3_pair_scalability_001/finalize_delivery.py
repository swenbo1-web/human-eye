"""Verify saved M3 evidence and index the finite failed candidate delivery."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import statistics
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = '3beb3f809674658b086e50af194adaa16e226111'
SOURCE = '0770602e875c819dd424639fd7c750aaad4bca3bbe506aaf747ba337e5991139'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def git_sources(manifest):
    requests = ''.join(COMMIT + ':' + row['path'] + '\n' for row in manifest).encode()
    result = subprocess.run(['git', 'cat-file', '--batch'], input=requests, cwd=ROOT,
                            capture_output=True, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    cursor = 0
    for row in manifest:
        end = result.stdout.index(b'\n', cursor)
        _, kind, length = result.stdout[cursor:end].split()
        assert kind == b'blob'
        cursor = end + 1
        value = result.stdout[cursor:cursor + int(length)]
        cursor += int(length) + 1
        assert sha(value) == row['sha256'], row['path']
        assert value == (ROOT / row['path']).read_bytes(), row['path']
    assert cursor == len(result.stdout)


def verify_witness(certificate, public, raw):
    face = raw['triangles'][certificate['triangle']]
    assert face == certificate['actual_triangle_vertex_indices']
    weights = [F(*value) for value in certificate['barycentric']]
    assert len(weights) == 3 and sum(weights) == 1 and min(weights) >= 0
    position = [sum(weights[j] * F(raw['vertices_world'][face[j]][axis]) for j in range(3))
                for axis in range(3)]
    assert position == [F(*value) for value in certificate['exact_surface_point_world_m']]
    squared = sum((F(a) - b) ** 2 for a, b in zip(public, position))
    assert squared == F(*certificate['squared_position_error_m2'])
    assert squared <= F(1e-9) ** 2


def verify():
    frozen = read(HERE / 'CANDIDATE_FREEZE.json')
    assert frozen['source_count'] == 137 and frozen['source_sha256'] == SOURCE
    git_sources(frozen['manifest'])
    ready = read(HERE / 'installation/READY.json')
    assert ready['commit'] == COMMIT and ready['source_sha256'] == SOURCE
    assert ready['source_count'] == 137 and ready['installed_identity_passed']
    assert ready['no_default_activation'] and ready['protected_inputs_unchanged']
    for row in frozen['manifest']:
        assert sha((Path(ready['install_root']) / row['path']).read_bytes()) == row['sha256']
    regressions = {}
    for name, count in (('final_regressions_01', 128), ('final_related_01', 85), ('final_node_02', 3)):
        result = read(HERE / 'testing' / name / 'RESULTS.json')
        assert result['methods'] == count and result['passed']
        assert result['guard_verified'] and result['sources_unchanged'] and result['tests_unchanged']
        assert result['source_sha256'] == SOURCE
        regressions[name] = {'methods': count, 'passed': True}
    mechanisms = read(HERE / 'testing/final_mechanisms_01/RESULTS.json')
    assert mechanisms['source_sha256'] == SOURCE and mechanisms['methods'] == 15
    assert not mechanisms['errors'] and mechanisms['runner_exception'] is None
    failures = mechanisms['failures']
    assert len(failures) == 4
    assert sum('test_g508_frozen_three_pairs' in row['test'] for row in failures) == 3
    assert sum('test_node_certificate_all_descendants' in row['test'] for row in failures) == 1
    timing = read(HERE / 'testing/paired_01/RESULTS.json')
    samples = timing['samples']
    assert len(samples) == timing['actual_samples'] == timing['planned_samples'] == 40
    assert timing['source_files_unchanged'] and timing['retries'] == 0
    assert len({(row['case'], row['iteration'], row['role']) for row in samples}) == 40
    assert all(row['exception'] is None for row in samples)
    assert all(row['independent_verification']['surface_passed'] for row in samples)
    peer = [row for row in samples if row['case'] == 'Peer_000']
    assert [row['surface_work']['intersection_tests'] for row in peer if row['role'] == 'reference'] == [18791] * 5
    assert [row['surface_work']['intersection_tests'] for row in peer if row['role'] == 'candidate'] == [7324] * 5
    control = [row for row in samples if row['case'] == 'cube12/control']
    old = statistics.median(row['complete_ns'] for row in control if row['role'] == 'reference')
    new = statistics.median(row['complete_ns'] for row in control if row['role'] == 'candidate')
    assert all(row['complete_facts'] for row in control)
    assert new - old <= max(1_000_000, old * .05)
    assembly_samples = [row for row in samples if row['case'] != 'cube12/control' and row['role'] == 'candidate']
    assert len(assembly_samples) == 15
    assert all(not row['complete_facts'] and row['closed']['reason'] == 'closed_solid_work_budget'
               for row in assembly_samples)
    run = HERE / 'entry/run_01'
    entry = read(run / 'RESULTS.json')
    assert entry['harness_execution_complete'] and not entry['errors'] and entry['source_files_unchanged']
    binding = read(run / 'INPUT_BINDINGS.json')
    for name, expected in binding['source_files'].items():
        assert sha(Path(name).read_bytes()) == expected, name
    snapshot = read(run / 'ACTUAL_SNAPSHOT.json')
    assert sha((run / 'ACTUAL_SNAPSHOT.json').read_bytes()) == '29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c'
    meshes = {row['name']: row for row in snapshot['objects']}
    public = read(run / 'SAVED_VERIFICATION.json')
    assert not public['full_pass'] and public['execution_cleanup_complete']
    assert [task['label'] for task in public['tasks']] == ['assembly_task', 'control_task']
    assembly, control_task = public['tasks']
    assert len(assembly['pairs']) == 3 and len(control_task['pairs']) == 1
    assert not assembly['full_pass'] and not assembly['nearest_passed'] and control_task['full_pass']
    for task, target in ((assembly, 'Target'), (control_task, 'Control_A')):
        assert task['binding_passed'] and task['aabb_passed']
        for row in task['pairs']:
            assert row['distance_passed'] and row['witness_passed'] and row['selector_passed']
            points = row['surface_fact']['value']['nearest_witness']
            cert = row['witness_certificate']
            verify_witness(cert['point_a'], points['a'], meshes[target])
            verify_witness(cert['point_b'], points['b'], meshes[row['candidate']])
    assert all(row['closed_fact']['reason'] == 'closed_solid_work_budget'
               and row['separation_gap']['status'] == 'unknown' for row in assembly['pairs'])
    runtime = entry['product_runtime_exit']
    assert runtime['confirmed'] and runtime['exited'] and runtime['handle_closed'] and runtime['exit_code'] == 0
    assert entry['native_close']['process_reaped'] and entry['native_close']['exit_code'] == 0
    assert entry['closed']['initial_geometry_fingerprint'] == entry['closed']['final_geometry_fingerprint']
    scopes = entry['scope_counts']
    assert scopes['business_observe_attempts'] == scopes['business_received_responses'] == scopes['business_host_RPC'] == 3
    assert scopes['QA_snapshot_host_RPC'] == scopes['close_host_RPC'] == 1
    assert entry['all_actual_host_RPC_including_QA_and_close'] == 5
    asset = binding['asset_manifest']
    assert sha(Path(asset['asset']).read_bytes()) == asset['asset_sha256'] == '27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46'
    record = {
        'saved_evidence_consistent': True, 'candidate_acceptance_passed': False,
        'product_commit': COMMIT, 'source_sha256': SOURCE, 'source_count': 137,
        'Git_disk_install_bytes_equal': True, 'regressions': regressions,
        'mechanism_G508_real_failures': 3, 'original_node_QA_expectation_failure_preserved': True,
        'corrected_node_replay_passed': True, 'frozen_kernel_samples': 40,
        'G508_candidate_complete_pairs': 0, 'G508_candidate_surface_verified': 15,
        'peer_reference_leaves': 18791, 'peer_candidate_leaves': 7324,
        'peer_50_percent_structure_gate': True,
        'simple_control_median_ns': {'reference': old, 'candidate': new, 'budget_passed': True},
        'actual_MCP_assembly_distances_verified': 3, 'actual_MCP_assembly_witnesses_verified': 3,
        'actual_MCP_assembly_closed_verified': 0, 'actual_MCP_control_passed': True,
        'runtime_and_Blender_exited': True, 'original_asset_hash_verified': True,
        'product_calls_in_this_verifier': 0, 'scope': 'saved-only delivery check; administrator deep review remains separate',
    }
    save(HERE / 'SAVED_VERIFICATION.json', record)
    print(json.dumps(record))


def index():
    excluded = ('INDEX.json', 'COMPLETE.json')
    files = []
    for path in sorted(HERE.rglob('*')):
        relative = path.relative_to(HERE)
        if not path.is_file() or relative.as_posix() in excluded:
            continue
        if path.suffix.lower() in ('.pyc', '.pyo') or any(part in ('__pycache__', 'tmp') for part in relative.parts):
            continue
        raw = path.read_bytes()
        files.append({'path': relative.as_posix(), 'bytes': len(raw), 'sha256': sha(raw)})
    save(HERE / 'INDEX.json', {'files': files, 'count': len(files), 'bytes': sum(row['bytes'] for row in files),
        'self_reference_exclusions': list(excluded), 'transient_exclusions': ['__pycache__', '*.pyc', '*.pyo', 'tmp/']})
    complete = {'cycle_id': 'M3-PAIR-SCALABILITY-001', 'execution_status': 'complete',
        'acceptance_status': 'failed_partial_capability', 'product_commit': COMMIT,
        'source_count': 137, 'source_sha256': SOURCE,
        'index_sha256': sha((HERE / 'INDEX.json').read_bytes()),
        'report_sha256': sha((HERE / 'REPORT.md').read_bytes()),
        'saved_verification_sha256': sha((HERE / 'SAVED_VERIFICATION.json').read_bytes()),
        'indexed_files': len(files), 'substantive_optimizations_used': 1,
        'remaining_bottleneck': 'insufficient multi-pair coverage per shared-simplex certificate in the fixed closed candidate tree',
        'default_activation': False, 'model_calls': 0, 'new_Blender_sessions': 1,
        'formal_MCP_sequences': 1, 'business_observes': 3, 'kernel_samples': 40}
    save(HERE / 'COMPLETE.json', complete)
    print(json.dumps(complete))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='store_true')
    args = parser.parse_args()
    index() if args.index else verify()
