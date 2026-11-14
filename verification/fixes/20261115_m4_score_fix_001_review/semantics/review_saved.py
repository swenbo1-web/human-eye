"""Independent AST/record review; no scorer/product execution or live calls."""
from pathlib import Path
import ast
import copy
import hashlib
import json

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
NEW = ROOT / 'verification/m4_complete_witness_score_fix_001'
OLD = ROOT / 'verification/m4_complete_witness_consumption_001'
OUT = Path(__file__).resolve().parent
inputs = {}
checks = []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def read(path):
    return json.loads(raw(path))

def check(name, passed):
    checks.append({'check': name, 'passed': bool(passed)})

def assigned(node, name):
    return isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name

def named_call(node, name):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == name

def result_metadata(node):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    target = node.targets[0]
    return isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'result' and isinstance(target.slice, ast.Constant) and target.slice.value in ('scorer_identity', 'terminal_binding')

def terminal_check(node):
    return named_call(node, 'check') and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == 'valid_final_and_terminal_process'

old_src = raw(OLD / 'score_saved.py')
new_src = raw(NEW / 'score_saved.py')
reader_src = raw(NEW / 'terminal_reader.py')
old = ast.parse(old_src)
new = ast.parse(new_src)
old_fn = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
new_fn = {n.name: n for n in new.body if isinstance(n, ast.FunctionDef)}
old_outer = next(n for n in old_fn['score'].body if assigned(n, 'outer'))
old_terminal = next(n for n in old_fn['score'].body if terminal_check(n))
fixed = copy.deepcopy(new_fn['score'])
body = []
removed = []
for n in fixed.body:
    if named_call(n, 'require_new_output') or assigned(n, 'terminal') or assigned(n, 'terminal_result') or result_metadata(n):
        removed.append(ast.unparse(n))
    elif assigned(n, 'run_result'):
        body.append(copy.deepcopy(old_outer))
        removed.append(ast.unparse(n))
    elif assigned(n, 'outer'):
        removed.append(ast.unparse(n))
    elif isinstance(n, ast.If) and ast.unparse(n.test) == "not terminal_result['passed']":
        removed.append(ast.unparse(n))
    elif terminal_check(n):
        body.append(copy.deepcopy(old_terminal))
        removed.append(ast.unparse(n))
    else:
        body.append(n)
fixed.body = body
dump = lambda n: ast.dump(n, include_attributes=False)
check('score_remaining_AST_equal_after_explicit_read_output_metadata_reversal', dump(fixed) == dump(old_fn['score']))
check('unchanged_loader_AST', dump(old_fn['load']) == dump(new_fn['load']))
fixed_main = copy.deepcopy(new_fn['main'])
fixed_main.body = [n for n in fixed_main.body if not named_call(n, 'require_new_output')]
for n in ast.walk(fixed_main):
    if isinstance(n, ast.ExceptHandler):
        n.body = [x for x in n.body if not result_metadata(x)]
check('main_remaining_AST_equal_after_explicit_output_metadata_reversal', dump(fixed_main) == dump(old_fn['main']))
check('original_scorer_expected_SHA', hashlib.sha256(old_src).hexdigest() == 'fd6a1c455d40407e8e3b1ad8f2711689f4419c6ce187a9e3083467edcd0d4074')

registry = read(NEW / 'REGISTRY.json')
summary = read(NEW / 'regression_01/RESULT.json')
check('registry_denominator_21', len(registry['cases']) == 21)
check('saved_matrix_denominator_21', summary['logical_cases_run'] == summary['passed_cases'] == 21 and summary['unrun_cases'] == [])
check('saved_zero_extra_live_calls', summary['new_model_product_Blender_raster_network_calls'] == 0 and summary['blocked_side_effects'] == [])
check('actual_23_score_invocations', summary['fullscore_calls'] + summary['root_independent_positive_calls'] + summary['output_protection_auxiliary']['score_invocations'] == 23)
for case in registry['cases']:
    folder = NEW / 'regression_01' / case['id']
    recorded_case = read(folder / 'CONTROL.json')
    result = read(folder / 'RESULT.json')
    score = read(folder / 'FULL_SCORE.json')
    terminal = read(folder / 'TERMINAL.json')
    overlay = read(folder / 'READ_OVERLAY.json')
    check(case['id'] + ':actual_control_matches_registered', recorded_case == case)
    check(case['id'] + ':actual_terminal_fields', terminal['failed_fields'] == case['expected_terminal_failed_fields'] and score['terminal_binding'] == terminal)
    expected = case['expected_terminal_failed_fields'] if case['kind'] == 'terminal' else case['expected_content_errors']
    check(case['id'] + ':exact_error_set', set(score['errors']) == set(expected))
    check(case['id'] + ':quality_and_exit', score['final_quality_passed'] is (case['kind'] == 'positive') and result['scorer_exit_code'] == (0 if case['kind'] == 'positive' else 1))
    check(case['id'] + ':three_json_read_overlays_only', len(overlay['read_intercepts']) == 3 and {x['target'] for x in overlay['read_intercepts']} == {'run', 'consumer', 'normalized'})
    if case['kind'] == 'content':
        check(case['id'] + ':current_product_kept_correct', score['product_current_facts_correct'] is True)
        if case['id'] == 'W01_actual_partial_readable':
            row = score['independent_actual_evidence']['target_first_readable']
            w = case['mutations'][0]['value']
            check('partial_control_is_real_readable_not_complete', row['readable'] is True and row['complete'] is False and row['surface_pixels'] == 37917 and row['boundary_pixels'] == 924 and row['view_name'] == w['view'] and row['image_ref'] == w['ref'])

run = read(NEW / 'fixtures/RUN_RESULT.json')
consumer = read(NEW / 'fixtures/CONSUMER.json')
check('fixtures_match_real_RUN_RESULT', raw(NEW / 'fixtures/RUN_RESULT.json') == raw(Path('D:/he_complete_witness_001/formal/RUN_RESULT.json')))
check('fixtures_match_real_CONSUMER', raw(NEW / 'fixtures/CONSUMER.json') == raw(Path('D:/he_complete_witness_001/formal/P1/c/CONSUMER.json')))
namespace = {}
exec(compile(reader_src, str(NEW / 'terminal_reader.py'), 'exec'), namespace)
reader = namespace['terminal_binding']
targeted = []
def probe(name, r, c, expected):
    actual = reader(r, c)
    targeted.append({'name': name, 'observed': actual, 'expected_failed_fields': expected})
    check('executed_reader:' + name, actual['failed_fields'] == expected and actual['passed'] is (not expected))

probe('saved_positive', run, consumer, [])
r = copy.deepcopy(run); r.pop('execution_state'); r['records'][0]['execution_state'] = 'completed'
probe('nested_state_not_substitute', r, consumer, ['RUN_RESULT.execution_state'])
r = copy.deepcopy(run); r['terminal_errors'] = [{'phase': 'post_route_checks'}]
probe('completed_with_postcheck_error', r, consumer, ['RUN_RESULT.terminal_errors'])
r = copy.deepcopy(run); r['actual_CLI_processes'] = True
probe('bool_not_integer_count', r, consumer, ['RUN_RESULT.actual_CLI_processes'])
r = copy.deepcopy(run); r['records'].append(copy.deepcopy(r['records'][0]))
probe('multiple_records', r, consumer, ['RUN_RESULT.records'])
c = copy.deepcopy(consumer); c['runtime_exit']['confirmed'] = False
probe('exit_unconfirmed', run, c, ['CONSUMER.runtime_exit.confirmed'])
c = copy.deepcopy(consumer); c['runtime_binding'] = None
probe('missing_binding_proof', run, c, ['CONSUMER.runtime_binding.confirmed'])

positive = read(NEW / 'SUPPLEMENTARY_QUALITY.json')
receipt = read(NEW / 'POSITIVE_RUN.json')
check('real_positive_no_read_overlay', receipt['read_overlay'] is False and receipt['scorer_entry'] == 'main' and receipt['exit_code'] == 0)
check('real_positive_output_bound', hashlib.sha256(raw(NEW / 'SUPPLEMENTARY_QUALITY.json')).hexdigest() == receipt['output_sha256'])
check('positive_33_checks_all_pass', len(positive['checks']) == 33 and all(x['passed'] for x in positive['checks']))
check('positive_native_remains_nondirect', positive['final_quality_passed'] and positive['product_current_facts_correct'] and positive['direct_product_adoption'] is False and positive['correct_with_supplement_or_recomputation'] is True)
check('positive_extra_categories_unchanged', positive['additional_native_or_unknown_use'] == ['raw_source_read', 'native_computation'])
check('positive_no_additional_frame', positive['actual_additional_native_frames'] == 0)
check('original_quality_remains_failed', read(OLD / 'admin/QUALITY.json')['final_quality_passed'] is False and inputs[str(OLD / 'admin/QUALITY.json')]['sha256'] == '272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87')
for name in ('regression.py', 'REPORT.md', 'terminal_reader.py', 'DERIVED_SCORER.diff'):
    raw(NEW / name)
for name in ('saved_evidence.py', 'native_evidence.py', 'oracle.py', 'admin/NORMALIZED.json', 'admin/TRUTH.json'):
    raw(OLD / name)
raw(Path('D:/hefe/docs/M4_COMPLETE_WITNESS_SCORE_FIX_001_PLAN.md'))
result = {'method': 'Independent AST comparison and actual saved per-case outputs; seven targeted pure terminal-reader executions. No full scorer replay or product/model/Blender/raster/network calls.', 'checks': len(checks), 'passed': sum(c['passed'] for c in checks), 'failures': [c for c in checks if not c['passed']], 'new_product_model_Blender_raster_network_calls': 0, 'new_full_scorer_runs': 0, 'targeted_reader_runs': targeted, 'score_AST_explicitly_reversed_nodes': removed, 'checks_detail': checks, 'interpretation': 'Native supplement occurred; its necessity or causal time saving was not established. Original automated failure and supplementary quality are the same model sample.'}
for name, value in [('RESULT.json', result), ('INPUTS.json', inputs)]:
    with (OUT / name).open('x', encoding='utf8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
print(json.dumps({'checks': result['checks'], 'passed': result['passed'], 'failures': result['failures'], 'inputs': len(inputs), 'targeted_reader_runs': len(targeted)}))
