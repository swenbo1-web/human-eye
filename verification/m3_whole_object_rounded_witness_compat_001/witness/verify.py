"""Check all 210 witness pairs and four installed stdio cold/warm controls."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PREVIOUS = V / 'm3_whole_object_rounded_witness_001'
ORIGINAL = Path('D:/he_m3_whole_object_rounded_witness_001')
ROOT = Path('D:/he_m3_whole_object_rounded_witness_compat_001/witness')
A1_COMMIT = 'ae14344ea3aa654c710f2329bd4aa4423f7af9c4'
A1_SHA = 'db381ce42b20e864d347c02ec1d41c847b3850d950e03dbbbec56abb9862c7f9'
RAW_INDEX_SHA = '6e970a8fd19c4b35d6ff3e2851a768b97b2020e7dd92d76d60357ac899c4dace'
CASES = (
    ('exact_linear', 'candidate_evidence', 'linear_m01_m03', True),
    ('strict_linear', 'candidate_evidence', 'success_m16_m19', True),
    ('standard_distance', 'candidate_standard', 'linear_m01_m03', False),
    ('exact_tree', 'candidate_evidence', 'tree_n02_n03', True),
)
STAGES = (
    'host.capture', 'observation.task_facts', 'surface_proximity.rounded_source_membership',
    'surface_proximity.exact_source_membership', 'task_query.exact_source_encode',
    'mcp.content_encode', 'mcp.wire_encode', 'mcp.stdio_write',
)
M = run_path(str(PREVIOUS / 'checks/matrix.py'))
E = M['D']
K = run_path(str(PREVIOUS / 'checks/kernel_batch.py'))
require, read, pin, write = (K[name] for name in ('require', 'read', 'pin', 'write'))


def frozen_original():
    index_path = PREVIOUS / 'RAW_INDEX.json'
    index_pin = pin(index_path, RAW_INDEX_SHA)
    index = read(index_path)
    archive_path = PREVIOUS / index['archive']['name']
    archive_pin = pin(archive_path, index['archive']['sha256'])
    require(archive_pin['bytes'] == index['archive']['bytes'], 'sealed_original_archive_size_changed')
    exact_names = ('checks_run/KERNEL_A.json', 'checks_run/KERNEL_B.json', 'checks_run/NUMERIC_B/KERNEL.json')
    prefixes = tuple(f'{arm}/cases/{label}/' for _, arm, label, _ in CASES)
    members = [name for name in index['members'] if name in exact_names or name.startswith(prefixes)]
    require(len(members) > len(exact_names) and all(any(name.startswith(prefix) for name in members)
                                                    for prefix in prefixes), 'prior_exact_raw_cases_missing')
    with ZipFile(archive_path) as archive:
        for name in members:
            replay = (ORIGINAL / name).read_bytes()
            require(index['members'][name] == {'sha256': sha256(replay).hexdigest(), 'bytes': len(replay)}
                    and replay == archive.read(name), 'sealed_original_member_changed/' + name)
    sources = [index_pin, archive_pin, *(pin(ORIGINAL / name) for name in sorted(members))]
    return sources


def kernel_continuity(binding):
    old = ORIGINAL / 'checks_run'
    K['run'](binding, ROOT / 'KERNEL_B.json', old / 'KERNEL_A.json')
    a1, new = (read(path) for path in (old / 'KERNEL_B.json', ROOT / 'KERNEL_B.json'))
    require(a1['identity']['git'] == A1_COMMIT and a1['identity']['source_sha256'] == A1_SHA,
            'wrong_signed_rounded_baseline_kernel')
    require(new['identity']['source_sha256'] != A1_SHA
            and new['old_style_strict'] == a1['old_style_strict'] == 202
            and new['exact_rational'] == a1['exact_rational']
            and len(new['exact_rational']) == 8 and new['source_pins'] == a1['source_pins'],
            'candidate_changed_frozen_proof_population')
    for before, after in zip(a1['cases'], new['cases'], strict=True):
        verify = lambda row: {key: value for key, value in row.items()
                              if key != 'installed_kernel_with_winner_receipt_ns'}
        require(E['G']['encode'](verify(before)) == E['G']['encode'](verify(after)),
                'rounded_scalar_facts_winner_search_or_certificate_changed/' + str(after['names']))
    installed = K['installed'](binding)[0]
    tree = run_path(str(PREVIOUS / 'checks/numeric_controls.py'))['bvh_holdout'](installed, True)
    old_tree = read(old / 'NUMERIC_B/KERNEL.json')['actual_BVH_holdout']
    for key in ('names', 'result', 'winner', 'exact_world_distance_squared_m2', 'source'):
        require(E['G']['canonical'](old_tree[key]) == E['G']['canonical'](tree[key]),
                'frozen_rotated_BVH_kernel_changed/' + key)
    write(ROOT / 'KERNEL_TREE_B.json', tree)
    return {'pair_count': len(new['cases']), 'strict': new['old_style_strict'],
            'exact': len(new['exact_rational']), 'tree_winner': tree['winner'],
            'tree_node_visits': tree['result']['work']['node_pair_visits'],
            'batch': pin(ROOT / 'KERNEL_B.json'), 'tree': pin(ROOT / 'KERNEL_TREE_B.json')}


def clocks(root, label, phase, result):
    case = root / 'cases' / label
    traces = [row['trace'] for row in M['events'](case / 'worker/PRODUCT_EVENTS.jsonl')
              if row['event'] == 'request_trace' and row['trace']['operation'] == 'mcp.observe']
    require(len(traces) == 2, 'cold_and_hot_request_traces_required')
    trace = traces[('cold', 'hot').index(phase)]
    receipt = read(Path(read(case / 'CASE.json')['observations'][phase]['receipt']['path']))
    require(trace['annotations']['mcp_request_id'] == receipt['id'], 'trace_and_wire_observation_disagree')
    spans = {stage: [row['duration_ns'] for row in trace['spans'] if row['name'] == stage] for stage in STAGES}
    require(all(len(durations) <= 1 for durations in spans.values()), 'unexpected_repeated_trace_stage')
    require(phase == 'cold' or all(not spans[stage] for stage in STAGES[2:5]), 'warm_recomputed_witness')
    return {'RTT_ns': result['stdio_ns'], 'request_ns': trace['duration_ns'], 'service_ns': result['service_ns'],
            'host_ns': result['host_ns'], 'inclusive_spans_ns': {name: values[0] for name, values in spans.items() if values}}


def delivery(case, binding):
    name, arm, label, opted_in = case
    old_root, new_root = ORIGINAL / arm, ROOT / name
    runner = run_path(str(PREVIOUS / 'harness/run.py'))['case']
    runner.__globals__['HERE'] = HERE
    result = runner(new_root / 'cases' / label, binding, label, opted_in)
    require(result['passed'], 'actual_installed_witness_replay_failed/' + name)
    (a_identity, a), (b_identity, b) = (M['read_case'](root, label, opted_in=opted_in)
                                        for root in (old_root, new_root))
    require(a_identity['preparation_git'] == A1_COMMIT and a_identity['source_sha256'] == A1_SHA
            and b_identity['source_sha256'] != A1_SHA, 'wrong_actual_comparison_installation')
    rows = {}
    for phase in ('cold', 'hot'):
        left, right = a[phase], b[phase]
        before, after = (M['public'](r['reply']) for r in (left, right))
        require(left['capture'] == right['capture'] and left['work'] == right['work']
                and before[0]['isError'] == after[0]['isError'] is False,
                'replay_capture_input_or_product_work_changed/' + name + '/' + phase)
        stable_left = E['comparable'](before[1], before[2], source_sha=A1_SHA)
        stable_right = E['comparable'](after[1], after[2], source_sha=b_identity['source_sha256'])
        require(stable_left == stable_right, 'stable_public_witness_bytes_changed/' + name + '/' + phase)
        fixture = E['F']['fixture'](label)
        limit = E['LIMITS'][fixture['family']]
        require(len(before[1].encode()) == len(after[1].encode()) <= limit,
                'frozen_public_witness_body_budget_changed/' + name)
        current = E['OLD']['witnesses'](after[2])
        if opted_in:
            exact = name.startswith('exact_')
            proof = E['verify_certificate'](right['capture'], after[2], expect_exact=exact,
                                           expected_order=fixture['names'], prove_global=exact, label=label)
        else:
            require(E['STRICT'] not in current and E['EXACT'] not in current, 'standard_distance_leaked_witness_proof')
            proof = None
        cli = E['OLD']['E']['fixed_cli'](after[0], must_preserve=True)
        require(len(cli['stages']) == 6 and all(row['exact'] for row in cli['stages']),
                'fixed_cli_did_not_preserve_actual_public_witness')
        rows[phase] = {'proof': proof, 'cli': cli, 'public_UTF8_bytes': len(after[1].encode()),
                       'equivalent_normalized_original_bytes': True, 'work': right['work'],
                       'A1_RX': left['RX'], 'B_RX': right['RX'],
                       'A1_clocks': clocks(old_root, label, phase, left),
                       'B_clocks': clocks(new_root, label, phase, right)}
    return {'case': label, 'evidence_option': opted_in, 'phases': rows,
            'A1_lifecycle': pin(old_root / 'cases' / label / 'CASE.json'),
            'B_lifecycle': pin(new_root / 'cases' / label / 'CASE.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--binding', type=Path)
    group.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    sources = frozen_original()
    if args.preflight:
        for _, arm, label, opted_in in CASES:
            M['read_case'](ORIGINAL / arm, label, opted_in=opted_in)
        print(json.dumps({'passed': True, 'sealed_source_members': len(sources)-2, 'selected_case_count': len(CASES)}))
        return
    ROOT.mkdir(parents=True, exist_ok=False)
    write(ROOT / 'SOURCE.json', {'sealed_inputs': sources, 'binding': pin(args.binding),
                                 'test_sources': [pin(p) for p in (HERE / 'verify.py', HERE / 'worker.py')]})
    outputs, kernel, failure = {}, None, None
    try:
        kernel = kernel_continuity(args.binding)
        for case in CASES:
            outputs[case[0]] = delivery(case, args.binding.resolve(strict=True))
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        clocks_summary = {arm: {phase: median(row['phases'][phase][arm]['RTT_ns'] for row in outputs.values())
                                for phase in ('cold', 'hot')} for arm in ('A1_clocks', 'B_clocks')} if outputs else {}
        write(ROOT / 'WITNESS.json', {'passed': failure is None, 'failure': failure, 'kernel': kernel,
              'planned': [item[0] for item in CASES], 'cases': outputs,
              'verified_cases': len(outputs), 'verified_cold_and_hot_calls': len(outputs)*2,
              'verified_B_cli_stages': len(outputs)*12, 'RTT_median_ns': clocks_summary,
              'actual_Blender': 0, 'actual_models': 0, 'actual_rasters': 0})


if __name__ == '__main__':
    main()
