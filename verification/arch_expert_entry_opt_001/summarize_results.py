"""Summarize existing CPU and actual evidence without importing product."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cpu = json.loads((ROOT / 'cpu_run_01/RESULTS.json').read_text(encoding='utf-8'))
actual = json.loads((ROOT / 'actual_run_01/RESULTS.json').read_text(encoding='utf-8'))
assert cpu['passed'] and cpu['tests'] == 27 and not (cpu['failures'] or cpu['errors'] or cpu['skipped'])
assert actual['passed'] and len(actual['records']) == 19
assert actual['source_sha256'] == cpu['source_sha256']
work = {}
calls = {}
modes = {}
for row in actual['records']:
    for key, value in row['blender_event']['work_delta'].items():
        work[key] = work.get(key, 0) + value
    for key, value in row['blender_event']['calls'].items():
        calls[key] = calls.get(key, 0) + value
    bucket = modes.setdefault(row['mode'], dict(tool_calls=0, estimated=0, unknown=0))
    bucket['tool_calls'] += 1
    bucket[row['result']['status']] += 1
    assert row['metric']['profile_none'] and row['client_profile_none'] and row['blender_event']['profile_none']
    assert row['oracle_max_abs_error'] == 0
    assert row['ledger_before_sha256'] == row['ledger_after_sha256']
assert sum(bucket['estimated'] for bucket in modes.values()) == 18
assert sum(bucket['unknown'] for bucket in modes.values()) == 1
assert calls['capture_entries'] == 19 and calls['predict_entries'] == 19
assert work['captures'] == 19 and work['static_reads'] == work['preparations'] == 14

pairs = []
for name in ('first', 'repeat', 'static', 'load'):
    old = next(row for row in actual['records'] if row['mode'] == 'old_owned' and row['label'] == name)
    new = next(row for row in actual['records'] if row['mode'] == 'new_owned' and row['label'] == name)
    assert old['blender_event']['work_delta'] == new['blender_event']['work_delta']
    assert {k: v for k, v in old['result'].items() if k not in ('source', 'request_trace')} == {
        k: v for k, v in new['result'].items() if k not in ('source', 'request_trace')}
    pairs.append(dict(label=name, old_product_ms=old['blender_event']['product_method_ms'],
                      new_product_ms=new['blender_event']['product_method_ms'],
                      old_full_tool_ms=old['full_tool_rtt_ms'], new_full_tool_ms=new['full_tool_rtt_ms'],
                      old_static_copies=old['blender_event']['calls'].get('static_patch_copies', 0),
                      new_static_copies=new['blender_event']['calls'].get('static_patch_copies', 0)))
summary = dict(
    task='ARCH-EXPERT-ENTRY-OPT-001', passed=True,
    disposition='candidate_fixed_and_qa_complete_pending_mainline_deep_review',
    product_commit=actual['product_commit'], source_sha256=actual['source_sha256'], source_members=136,
    base_commit=actual['old_commit'], old_source_sha256=actual['old_source_sha256'],
    product_scope=['human_eye_plugin/blender_host.py', 'human_eye_plugin/arm_twist_source.py'],
    product_lines=dict(insertions=6, deletions=4),
    cpu=dict(attempts=1, tests=27, passed=27, failures=0, errors=0, skipped=0,
             new_methods=7, related_entry_methods=14, related_source_methods=6,
             fake_endpoint_unknown_tools_inside_methods=6, source_unchanged=cpu['source_unchanged']),
    actual=dict(attempts=1, tool_calls=19, estimated=18, unknown=1, unexpected_errors=0,
                by_mode=modes, work=work, method_entries=calls,
                oracle_score_regions=sum(len(row['result']['regions']) for row in actual['records']),
                oracle_severity_max_abs_error=0, post_response_oracle_controls=19,
                owned_and_shared_selection_vertices=[1602, 1536, 1602],
                unknown_reason='bone_twist_branch_unknown', unknown_is_error=False,
                unknown_recovery='load_then_estimated_with_new_preparation',
                profiler_enabled=False, old_new_pairs=pairs, runner_sequence_ms=actual['runner_sequence_ms']),
    fixture_sha256=actual['fixture_sha256'], processes=actual['processes'],
    model_api_calls=0, user_assets=0,
    prior_matrices_referenced_not_replayed=['arch_expert_entry_001 actual25', 'historical165CPU', 'M5zero_one_four'],
    evidence=dict(report='REPORT.md', actual_report='ACTUAL_QA_REPORT.md', costs='ACTUAL_COSTS.json',
                  cleanup='PROCESS_CLEANUP.json', independent_review='REVIEW.md', index='EVIDENCE_INDEX.json'),
    limits=[
        'Single old/new pair per phase, old group first; no statistical speed guarantee. Repeat is slightly slower.',
        'Timers include lightweight counters and wire recording; no sys.setprofile, oracle or large packet/event writes inside timing.',
        'Native same-model oracle checks source and integration consistency, not model accuracy.',
        'BMesh still has whole-mesh C work; selected Python row counts do not prove O(selected) total cost.',
        'Unknown is a normal report and enters predict_prepared but returns before MLP severity scoring.',
        'Real unknown recovery uses load and re-prepares; CPU same-binding recovery separately proves reuse.',
        'Shared controlled terminate/wait returns1; stdio clients return0. Stdio client PIDs were not separately recorded.',
        'No old25 tool,165 CPU or M5 matrix repeated; future repair operators are outside this task.'])
assert summary['actual']['oracle_score_regions'] == 441
assert [row['old_static_copies'] for row in pairs] == [1, 0, 1, 1]
assert [row['new_static_copies'] for row in pairs] == [0, 0, 0, 0]
(ROOT / 'RESULTS.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(passed=True, cpu_methods=27, actual_tools=19, oracle_score_regions=441)))
