"""Independent, offline review of CLI adapters and their actual integration boundary."""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import json

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = ROOT / 'verification/m4_surface_scan_continuity_001'
OUT = Path(__file__).resolve().parent
INPUTS, CHECKS = {}, []

def raw(path):
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value

def read(path):
    return json.loads(raw(path))

def ck(name, passed):
    CHECKS.append({'name': name, 'passed': bool(passed)})

module_path = B / 'cli/continuity_cli.py'
tree = ast.parse(raw(module_path))
ck('module_top_level_only_import_constants_and_functions', all(isinstance(n, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef)) for n in tree.body))
spec = importlib.util.spec_from_file_location('root_readonly_continuity_cli', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
templates = read(B.parent / 'm4_surface_scan_compact_consumption_001/preflight/CLI_ARGV.json')['argv_by_group']
help_rows = read(B / 'cli/ARGV_HELP_VALIDATION.json')['records']
uuid = 'a97c9b33-1210-4d6f-9380-53c01a345bb3'
for group in ('N', 'C'):
    template = templates[group]
    first = module.argv_for_turn(template)
    resumed = module.argv_for_turn(template, uuid)
    ck(group + '_persisted_first', first == [x for x in template if x != '--ephemeral'])
    ck(group + '_explicit_resume', 'resume' in resumed and resumed[-2:] == [uuid, '-'] and '--ephemeral' not in resumed and '--last' not in resumed)
    configs = lambda argv: [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == '-c']
    ck(group + '_same_settings', configs(first) == configs(resumed))
    ck(group + '_same_work', first[first.index('-C') + 1] == resumed[resumed.index('-C') + 1])
    ck(group + '_recorded_help_success', all(r['exit_code'] == 0 for r in help_rows if r['group'] == group))

usage = {'input_tokens': 123, 'output_tokens': 7}
events = [{'type': 'thread.started', 'thread_id': uuid},
          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'synthetic-final'}},
          {'type': 'turn.completed', 'usage': usage}]
rows = []
for index in range(1, 4):
    r = module.summarize_turn(events, episode_id='offline', turn_index=index, expected_thread_id=None if index == 1 else uuid, exit_code=0)
    rows.append(r)
    ck('synthetic_turn_' + str(index), r['valid_completion'] and r['observed_thread_id'] == uuid and r['usage_aggregation'] is None)
failure_events = [events[0], {'type': 'error', 'message': 'retained reconnect failure'}, *events[1:]]
failed = module.summarize_turn(failure_events, episode_id='offline', turn_index=2, expected_thread_id=uuid, exit_code=0)
ck('error_with_final_remains_failed', not failed['valid_completion'] and failed['final_present'] and failed['execution_state'] == 'failed')
other = 'b97c9b33-1210-4d6f-9380-53c01a345bb3'
wrong = module.summarize_turn(events, episode_id='offline', turn_index=2, expected_thread_id=other, exit_code=0)
ck('wrong_thread_rejected', not wrong['valid_completion'])
packet = module.episode_manifest('offline', [rows[0], failed], 'anonymous')
ck('failed_and_not_run_denominator', packet['counts'] == {'completed': 1, 'failed': 1, 'not_run': 1})
ck('failure_final_preserved', packet['turns'][1]['final'] == 'synthetic-final')
ck('draft_no_provider_launch', read(B / 'cli/FUTURE_CONSUMER_DRAFT.json')['model_consumer_launch_enabled'] is False)
transport = raw(B / 'runtime/consumer_transport.py').decode('utf8')
functions = {n.name for n in ast.parse(transport).body if isinstance(n, ast.FunctionDef)}
ck('actual_new_runtime_has_only_thin_turn', functions == {'thin_turn'})
ck('no_cli_adapter_call_in_transport', 'argv_for_turn' not in transport and 'summarize_turn' not in transport)
old = raw(B.parent / 'm4_surface_scan_compact_consumption_001/runtime/consumer_transport.py').decode('utf8')
ck('old_loop_recreates_fresh_workspace', 'fresh_empty_consumer_workspace_required' in old)
ck('old_loop_still_ephemeral', "'--ephemeral'" in old)
ck('old_loop_has_local_deadline', "deadline=began+int(plan['max_session_seconds']*1e9)" in old)
ck('old_loop_no_expected_thread_parameter', 'expected_thread_id' not in old)
result = {'fixed_delivery': 'a206a96e51ca6293ea555f17960b964ba02f0606', 'checks': len(CHECKS), 'failed': [r for r in CHECKS if not r['passed']], 'detail': CHECKS, 'inputs_sha256': INPUTS,
          'finding': 'Pure adapters support explicit resume and preserve failure denominator, but actual consume loop is not connected. A new preparation must parameterize folder/shared workspace/expected thread/deadline and wire raw archives; helper tests do not establish this integration.',
          'new_Blender_model_API_runs': 0, 'actual_model_resume_measured': False}
(OUT / 'CLI_REVIEW.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'checks': result['checks'], 'failed': result['failed']}))
raise SystemExit(bool(result['failed']))
