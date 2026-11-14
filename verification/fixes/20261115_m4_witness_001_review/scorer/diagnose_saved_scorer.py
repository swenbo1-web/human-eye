"""Read-only derived diagnostic, not an official regrade or independent oracle."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
BASE = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_complete_witness_consumption_001')
RUNTIME = Path('D:/he_complete_witness_001')
OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
read_paths = set()


def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)))
        if writing and not path.is_relative_to(OUT):
            raise PermissionError('review_writes_only_in_assigned_evidence_directory')
        if not writing and (path.is_relative_to(BASE) or path.is_relative_to(RUNTIME)):
            read_paths.add(path)
    if event in ('subprocess.Popen', 'socket.connect', 'socket.bind', 'os.system'):
        raise PermissionError('no_process_network_or_product_launch_in_offline_review')
    if event == 'import' and str(args[0]).startswith(('human_eye_', 'bpy')):
        raise PermissionError('no_product_import_in_scorer_diagnostic')


sys.addaudithook(audit)
source_path = BASE / 'score_saved.py'
raw = source_path.read_bytes()
source_sha = hashlib.sha256(raw).hexdigest()
assert source_sha == 'fd6a1c455d40407e8e3b1ad8f2711689f4419c6ce187a9e3083467edcd0d4074'
original = raw.decode('utf-8-sig')
line = "outer = oracle.read(arguments.runtime_root / 'formal/RUN_RESULT.json')['records'][0]"
assert original.count(line) == 1
assert original.count("outer['execution_state']") == 1
derived = original.replace(line,
    "run_result = oracle.read(arguments.runtime_root / 'formal/RUN_RESULT.json')\n    outer = run_result['records'][0]")
derived = derived.replace("outer['execution_state']", "run_result['execution_state']")
namespace = {'__name__': '_root_saved_scorer_diagnostic', '__file__': str(source_path)}
exec(compile(derived, '<in-memory-read-layer-diagnostic>', 'exec'), namespace)
output = OUT / 'DIAGNOSTIC_LAYER_FIX_ONLY.json'
exit_value = namespace['score'](SimpleNamespace(
    normalized=BASE / 'admin/NORMALIZED.json', runtime_root=RUNTIME, output=output))
diagnostic = json.loads(output.read_bytes())

# A narrow producer-specific terminal reader. This is a test proposal and
# evaluator of existing data, not a mutation of the frozen scorer.
def terminal_valid(top, consumer):
    try:
        if (top['schema'] != 'complete-witness-single-formal-v1'
                or type(top['records']) is not list or len(top['records']) != 1
                or any(type(top[key]) is not int or top[key] != 1
                       for key in ('planned_routes', 'actual_routes', 'actual_CLI_processes'))
                or type(top['outer_retries']) is not int or top['outer_retries'] != 0
                or top['execution_state'] != 'completed'
                or top['launcher_succeeded'] is not True or top['terminal_errors'] != []):
            return False
        row = top['records'][0]
        return (row['slot'] == 'P1' and row['group'] == 'P' and row['outer_valid_completion'] is True
                and consumer['valid_completion'] is True
                and consumer['runtime_binding']['confirmed'] is True
                and consumer['runtime_exit']['confirmed'] is True)
    except (KeyError, TypeError, IndexError):
        return False


top = json.loads((RUNTIME / 'formal/RUN_RESULT.json').read_bytes())
consumer = json.loads((RUNTIME / 'formal/P1/c/CONSUMER.json').read_bytes())
controls = []


def control(name, update_top=None, update_consumer=None, expected=False):
    candidate = copy.deepcopy(top)
    c = copy.deepcopy(consumer)
    if update_top:
        update_top(candidate)
    if update_consumer:
        update_consumer(c)
    observed = terminal_valid(candidate, c)
    controls.append({'name': name, 'expected': expected, 'observed': observed, 'pass': observed == expected})


control('actual_saved_run', expected=True)
control('missing_top_execution_state', lambda t: t.pop('execution_state'))
control('nested_only_state_does_not_substitute_top', lambda t: (t['records'][0].update(execution_state=t.pop('execution_state'))))
control('top_state_failed', lambda t: t.update(execution_state='failed'))
control('postchecks_failed_with_completed_route', lambda t: t.update(launcher_succeeded=False, terminal_errors=[{'stage': 'post_route_checks'}]))
control('contradictory_launcher_false_without_errors', lambda t: t.update(launcher_succeeded=False))
control('errors_present_despite_launcher_true', lambda t: t.update(terminal_errors=[{'stage': 'post_route_checks'}]))
control('wrong_schema', lambda t: t.update(schema='routed-task-v1'))
control('empty_records', lambda t: t.update(records=[]))
control('duplicate_records', lambda t: t['records'].append(copy.deepcopy(t['records'][0])))
control('outer_valid_false', lambda t: t['records'][0].update(outer_valid_completion=False))
control('wrong_slot', lambda t: t['records'][0].update(slot='P2'))
control('wrong_group', lambda t: t['records'][0].update(group='N'))
control('unexpected_extra_CLI', lambda t: t.update(actual_CLI_processes=2))
control('outer_retry_present', lambda t: t.update(outer_retries=1))
control('consumer_invalid', update_consumer=lambda c: c.update(valid_completion=False))
control('runtime_binding_unconfirmed', update_consumer=lambda c: c['runtime_binding'].update(confirmed=False))
control('runtime_exit_unconfirmed', update_consumer=lambda c: c['runtime_exit'].update(confirmed=False))

summary = {
    'method': 'In-memory two-site read-layer correction of frozen author scorer on unchanged saved bytes; not official regrade and not an independent pixel oracle',
    'source_sha256': source_sha,
    'frozen_source_unchanged': hashlib.sha256(source_path.read_bytes()).hexdigest() == source_sha,
    'original_quality_sha256': hashlib.sha256((BASE / 'admin/QUALITY.json').read_bytes()).hexdigest(),
    'new_product_model_Blender_raster_calls': 0,
    'derived_read_layer_exit': exit_value,
    'derived_quality': diagnostic['final_quality_passed'],
    'derived_direct_adoption': diagnostic['direct_product_adoption'],
    'derived_correct_with_supplement': diagnostic['correct_with_supplement_or_recomputation'],
    'derived_checks': len(diagnostic['checks']),
    'derived_errors': diagnostic['errors'],
    'derived_adoption_errors': diagnostic['adoption_evidence_errors'],
    'additional_key_or_schema_failure_after_state_read_fix': False,
    'proposed_terminal_controls': controls,
    'terminal_controls_passed': sum(c['pass'] for c in controls),
    'terminal_controls_failed': sum(not c['pass'] for c in controls),
    'remaining_limits': [
        'Source-quoted normalization still depends on human semantic review of entailment and contradictions.',
        'Adoption category provenance checks do not algorithmically prove the code category; this current raw/native classification is manually supported.',
        'Native-frame fallback branch not exercised by this actual run because extra TOP access reused product frame.',
        'An official derived regrade must be versioned and must retain the original failed QUALITY and seal unchanged.'
    ],
}
(OUT / 'RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
inputs = [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
          for p in sorted(read_paths) if p.is_file()]
(OUT / 'INPUTS.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: summary[key] for key in ('derived_checks', 'derived_quality', 'derived_direct_adoption',
                                               'terminal_controls_passed', 'terminal_controls_failed')}))
if summary['terminal_controls_failed'] or exit_value:
    raise SystemExit(1)
