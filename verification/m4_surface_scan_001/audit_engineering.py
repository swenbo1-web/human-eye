"""Independent offline audit of frozen inputs, all planned rows and public metrics."""
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
QUAL = HERE/'qualification'
RUN = HERE/'engineering/run_01'
COMMIT = 'c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
SOURCE = 'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_distance(row):
    exact = row['exact_squared_distance_m2']
    return math.sqrt(float(Fraction(int(exact['numerator']), int(exact['denominator']))))


def public_metrics(body, truth):
    expected = {tuple(sorted((row['object_a'], row['object_b']))): row
                for row in truth['pairs']}
    assert body['status'] == 'complete'
    assert body['binding']['runtime_source_sha256'] == SOURCE
    actual = set()
    for row in body['matches']:
        pair = tuple(sorted(obj['name'] for obj in row['objects']))
        assert pair not in actual and expected[pair]['matches_threshold']
        actual.add(pair)
        assert row['witness_status'] == 'measured'
        assert math.isfinite(row['distance_m']) and row['distance_m'] >= 0
        assert abs(row['distance_m']-reference_distance(expected[pair])) <= 1e-10
        assert abs(math.dist(row['point_a_world'], row['point_b_world'])-row['distance_m']) <= 1e-10
    assert actual == {pair for pair, row in expected.items() if row['matches_threshold']}
    return len(actual)


def planned_rows(sequences):
    rows = []
    for index in range(1, 6):
        sequence = sequences.get(index)
        for state in ('cold', 'repeat', 'edit'):
            matches = [] if sequence is None else [r for r in sequence.get('business', []) if r['state'] == state]
            status = ('not_attempted' if not matches else 'duplicate' if len(matches) != 1 else
                      'failed' if matches[0].get('errors') else 'present')
            rows.append(dict(sequence=index, state=state, status=status))
    return rows


def self_check(first, truth):
    assert len(planned_rows({})) == 15
    assert all(row['status'] == 'not_attempted' for row in planned_rows({}))
    duplicate = {1: dict(business=[dict(state='cold', errors=[])]*2)}
    assert planned_rows(duplicate)[0]['status'] == 'duplicate'
    failed = {1: dict(business=[dict(state='cold', errors=['failure'])])}
    assert planned_rows(failed)[0]['status'] == 'failed'
    for field, value in (('distance_m', .123), ('witness_status', 'unknown')):
        mutant = copy.deepcopy(first)
        mutant['matches'][0][field] = value
        try:
            public_metrics(mutant, truth)
        except AssertionError:
            pass
        else:
            raise AssertionError('public metric counterexample accepted')
    return 5


def main():
    qualification = read(QUAL/'QUALIFICATION_READY.json')
    promised = {'asset_sha256': QUAL/'assembly.blend',
        'base_snapshot_sha256': QUAL/'BASE_SNAPSHOT.json', 'edit_snapshot_sha256': QUAL/'EDIT_SNAPSHOT.json',
        'base_truth_sha256': QUAL/'BASE_TRUTH.json', 'edit_truth_sha256': QUAL/'EDIT_TRUTH.json',
        'control_certificates_sha256': QUAL/'CONTROL_CERTIFICATES.json',
        'geometry_freeze_sha256': QUAL/'GEOMETRY_FREEZE.json',
        'pose_helper_sha256': HERE/'worker/pose_native.py', 'pose_patch_sha256': HERE/'worker/POSE_PATCH.json'}
    for field, path in promised.items():
        assert sha(path) == qualification[field], field
    frozen_manifest = read(QUAL/'SOURCE_OUTPUT_MANIFEST.json')
    for row in frozen_manifest['files']:
        path = HERE/row['path']
        assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
    protected = read(HERE/'PROTECTED_BEFORE.json')
    assert all(sha(Path(path)) == expected for path, expected in protected.items())
    candidate = read(HERE/'CANDIDATE_SOURCE.json')
    assert candidate['identity']['source_sha256'] == SOURCE
    ready = read(HERE/'installation/run_01/READY.json')
    assert ready['commit'] == COMMIT and ready['source_sha256'] == SOURCE
    for row in candidate['identity']['source_files']:
        expected = row['sha256']
        assert sha(ROOT/row['path']) == sha(Path(ready['install_root'])/row['path']) == expected
        archived = subprocess.check_output(['git', 'show', COMMIT+':'+row['path']], cwd=ROOT)
        assert hashlib.sha256(archived).hexdigest() == expected
    binding = read(RUN/'INPUT_BINDINGS.json')
    assert binding['source_commit'] == COMMIT and binding['source_sha256'] == SOURCE
    assert binding['sequences'] == 5 and binding['images'] == binding['model_consumers'] == 0
    for name, expected in binding['files'].items():
        assert sha(Path(name)) == expected, name
    sequences = {i: read(RUN/('sequence_'+str(i).zfill(2))/'RESULTS.json') for i in range(1, 6)}
    plan = planned_rows(sequences)
    assert all(row['status'] == 'present' for row in plan), plan
    truth = {state: read(QUAL/(state.upper()+'_TRUTH.json')) for state in ('base', 'edit')}
    checked_pairs = checked_public = 0
    costs = {state: [] for state in ('cold', 'repeat', 'edit')}
    unrelated_edit_pairs = []
    for sequence in sequences.values():
        assert sequence['passed'] and sequence['source_files_unchanged']
        assert sequence['automatic_retries'] == 0 and not sequence['errors']
        assert sequence['native_close']['process_reaped'] and sequence['native_close']['exit_code'] == 0
        assert sequence['runtime_exit']['confirmed'] and sequence['runtime_exit']['exit_code'] == 0
        for row in sequence['business']:
            state = 'edit' if row['state'] == 'edit' else 'base'
            checked_public += public_metrics(row['body'], truth[state])
            target = {tuple(sorted((p['object_a'], p['object_b']))): p for p in truth[state]['pairs']}
            names = {obj['id']: obj['name'] for match in row['body']['matches'] for obj in match['objects']}
            snapshot = read(QUAL/(state.upper()+'_SNAPSHOT.json'))
            for obj in snapshot['objects']:
                oid = 'blender:'+hashlib.sha256(json.dumps(['',obj['name']], ensure_ascii=False,
                    sort_keys=True, separators=(',',':')).encode()).hexdigest()
                names[oid] = obj['name']
            dispositions = row['diagnostics']['dispositions']
            seen = set()
            unrelated = 0
            for part in dispositions:
                pair = tuple(sorted(names[oid] for oid in part['object_ids']))
                assert pair not in seen and pair in target
                seen.add(pair)
                expected = target[pair]
                assert (part['status'] == 'measured_match') == expected['matches_threshold']
                assert part['status'] in ('bound_excluded','measured_match','measured_nonmatch')
                if part['status'] == 'bound_excluded':
                    value = expected['exact_squared_distance_m2']
                    assert Fraction(part['lower_bound_m'])**2 <= Fraction(int(value['numerator']),int(value['denominator']))
                    assert part['lower_bound_m'] > .002
                else:
                    assert abs(part['distance_m']-reference_distance(expected)) <= 1e-10
                    unrelated += int('Obj_008' not in pair)
            assert len(seen) == 276 and seen == set(target)
            checked_pairs += len(seen)
            assert row['actual_host_RPC'] == 1
            spans = {part['name'] for part in row['span_timings_ns']}
            assert {'mcp.wire_encode','mcp.stdio_write','service.observe'} <= spans
            assert not row['errors'] and row['trace']['annotations']['mcp_native_image_block_count'] == 0
            costs[row['state']].append(row['complete_client_request_ns']/1e6)
            if row['state'] == 'edit':
                unrelated_edit_pairs.append(unrelated)
    directed = read(HERE/'engineering/process_01/RESULTS.json')
    assert directed['passed'] and directed['original_asset_unchanged'] and directed['owned_copy_not_saved']
    assert directed['actual_commands'] == ['capabilities','capture_surface_scan','shutdown']
    directed_public = public_metrics(directed['body'], truth['base'])
    first = sequences[1]['business'][0]['body']
    tests = self_check(first, truth['base'])
    result = dict(passed=True, candidate_commit=COMMIT, source_sha256=SOURCE,
        qualified_input_hashes_verified=len(promised), qualification_files_verified=len(frozen_manifest['files']),
        runtime_sources_verified=len(candidate['identity']['source_files']), planned_main_rows=plan,
        planned_main_business_attempts=15, actual_main_business_attempts=15, missing=0, duplicate_rows=0,
        main_pair_dispositions_rechecked=checked_pairs, main_public_oracle_distances_rechecked=checked_public,
        directed_public_oracle_distances_rechecked=directed_public,
        public_witness_status='all measured', postrun_guard_counterexamples_passed=tests,
        client_wall_ms={state:dict(values=values,median=statistics.median(values)) for state,values in costs.items()},
        edit_recomputed_pairs_not_involving_changed_object=unrelated_edit_pairs,
        timing_scope='Server trace includes MCP wire encoding and stdio completion. Client wall also includes Peer evidence I/O.',
        model_consumers=0, images=0, business_APIs=0,
        protected_files_unchanged=True, installed_source_and_commit_bytes_equal=True)
    with (HERE/'ROOT_ENGINEERING_AUDIT.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
