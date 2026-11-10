"""Read-only V2 prompt/scoring/source binding checks; no product execution."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
ROOT = EVAL.parents[1]
BASE = '82e976cd425fae9703399148a8938bd6099d486f'
PRECISION = '距离答案误差要求不超过0.001毫米，数值至少保留到0.001毫米；无法支持该精度时说明原因。'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read = lambda path: json.loads(path.read_bytes())


def main():
    assert len(sys.argv) == 2 and Path(sys.argv[1]).name == sys.argv[1]
    output = HERE/sys.argv[1]
    assert not output.exists()
    original = HERE/'original_82e976cd'
    archive = read(HERE/'ORIGINAL_ARCHIVE.json')
    assert archive['base_commit'] == BASE and archive['before_any_V2_modification']
    for row in archive['files']:
        assert sha((ROOT/row['copy_path']).read_bytes()) == row['sha256']
    old, plan = read(original/'PLAN.json'), read(EVAL/'PLAN.json')
    tasks, scoring = read(EVAL/'TASKS.json'), read(EVAL/'SCORING_CONTRACT.json')
    rules = (EVAL/'SESSION_RULES.txt').read_bytes()
    assert rules == (original/'SESSION_RULES.txt').read_bytes()+PRECISION.encode('utf8')+b'\n'
    assert plan['shared_session_rules']['sha256'] == sha(rules)
    assert plan['shared_session_rules']['modified_from_005_and_82e976cd'] is True
    preserved = ['sequence', 'arms', 'treatment_variable', 'logical_denominator', 'per_arm',
        'task_count', 'repetitions_each_task_arm', 'max_session_seconds', 'total_cell_seconds',
        'tool_attempts', 'physical_RPC_limit', 'tool_response_bytes', 'tool_timeout_s', 'code_bytes',
        'images', 'model_retries', 'S_advancement_gates', 'first_request_valid_definition',
        'sampling', 'quality_before_cost', 'fixed_product_commit', 'candidate_source_sha256']
    assert all(plan[k] == old[k] for k in preserved)
    inputs = []
    for task, row in tasks.items():
        data = rules+b'\n'+(EVAL/row['prompt']).read_bytes()
        assert sha(data) == plan['tasks'][task]['model_input_sha256']
        assert len(data) == plan['tasks'][task]['model_input_bytes']
        assert all(plan['tasks'][task][key] == value for key, value in row.items())
        assert len({sha(data) for group in ('N', 'C', 'S')}) == 1
        inputs.append({'task': task, 'all_arms_same': True, 'bytes': len(data), 'sha256': sha(data)})
    world_path = 'tasks/T1/run_01/WORLD_ROUNDOFF.json'
    world = read(EVAL/world_path)
    required = {'Part_26': [0.007812492487105026, 0.007812507512894975],
                'Part_38': [0.015624991804114568, 0.015625008195885432]}
    assert {r['name']: r['captured_world_distance_interval_m'] for r in world[
        'separated_distance_intervals_with_binary64_world_roundoff']} == required
    for name, expected in required.items():
        for collection in (tasks['T1']['facts'], plan['tasks']['T1']['facts'],
                           scoring['independent_answers']['T1']['required_pair_facts']):
            fact = collection[name]
            assert fact['distance_interval_m'] == expected
            source = fact['distance_interval_source']
            assert source['object'] == name and source['path'] == world_path
            assert source['sha256'] == sha((EVAL/world_path).read_bytes())
            assert source['field'].endswith('[].captured_world_distance_interval_m')
    for row in (tasks['T1'], plan['tasks']['T1']):
        assert row['distance_interval_m'] == required['Part_26']
        assert row['distance_interval_source']['sha256'] == sha((EVAL/world_path).read_bytes())
        assert row['tolerance_m'] == 1e-6
    assert scoring['independent_answers']['T1']['certified_interval_m'] == required['Part_26']
    assert scoring['independent_answers']['T1']['certified_interval_source'] == tasks['T1']['distance_interval_source']
    assert all(r['answer_tolerance_m'] == 1e-6 for r in scoring['independent_answers'].values())
    assert plan['scoring_contract_sha256'] == sha((EVAL/'SCORING_CONTRACT.json').read_bytes())
    assert all(sha((EVAL/name).read_bytes()) == digest for name, digest in plan['dispatch_input_sha256'].items())
    before, after = ast.parse((original/'driver.py').read_bytes()), ast.parse((EVAL/'driver.py').read_bytes())
    for tree in (before, after):
        tree.body = [node for node in tree.body if not (isinstance(node, ast.FunctionDef)
            and node.name in ('prepare', 'run_models'))]
    assert ast.dump(before) == ast.dump(after)
    assert plan['preflight_driver_sha256'] == sha((EVAL/'driver.py').read_bytes())
    old_index = read(original/'ARTIFACT_INDEX.json')
    mutable = {r['original_path'] for r in archive['files']}
    immutable = [r for r in old_index['files'] if r['path'] not in mutable]
    assert all(sha((ROOT/r['path']).read_bytes()) == r['sha256'] for r in immutable)
    sources = read(original/'SOURCE_REVIEW.json')['files']
    assert len(sources) == 137 and all(sha((ROOT/r['path']).read_bytes()) == r['sha256'] for r in sources)
    originals = archive['files']
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', '--batch'],
        input=''.join(BASE+':'+r['original_path']+'\n' for r in originals).encode())
    offset = 0
    for row in originals:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        assert header[1] == b'blob'
        size = int(header[2]); offset = end+1
        value = raw[offset:offset+size]; offset += size+1
        assert value == (ROOT/row['copy_path']).read_bytes() and sha(value) == row['sha256']
    assert offset == len(raw)
    assert not (EVAL/'GO.json').exists() and not (EVAL/'STARTED.json').exists() and not (EVAL/'cells').exists()
    result = {'passed': True, 'base_commit': BASE, 'original_Git_blobs_copies_verified': len(originals),
        'unchanged_original_evidence_members': len(immutable), 'product_sources_unchanged': 137,
        'public_precision_exact': PRECISION, 'model_inputs': inputs,
        'T1_official_intervals_bound_to_world_roundoff': required,
        'sequence_abilities_budgets_denominators_blinding_unchanged': True,
        'driver_changes_only_prepare_and_run_models': True, 'models': 0,
        'Blender_calls': 0, 'production_calls': 0,
        'old_preflight_9_and_control_5_are_historical_82e_not_rerun': True}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['model_inputs', 'T1_official_intervals_bound_to_world_roundoff']}))


if __name__ == '__main__':
    main()
