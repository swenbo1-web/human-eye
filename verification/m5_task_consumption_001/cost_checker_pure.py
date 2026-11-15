"""Read-only cost-source review with namespace-only synthetic saved records."""

import ast
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'cost_decision.py'


def pin(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    before = pin(SOURCE)
    spec = importlib.util.spec_from_file_location('_m5_task_cost_synthetic', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = HERE / 'cost_checker_pure_02'
    output.mkdir(exist_ok=False)
    module.RUNTIME = (output / 'runtime').resolve()
    module.HERE = (output / 'reports').resolve()
    module.HERE.mkdir()
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    def fixture(slot, calls, joint=False):
        folder = module.RUNTIME / 'formal' / slot
        usage = {'input_tokens': 100, 'cached_input_tokens': 60, 'output_tokens': 10, 'reasoning_output_tokens': 2}
        events = [{'type': 'thread.started', 'thread_id': 'synthetic-' + slot},
                  {'type': 'turn.completed', 'usage': usage}]
        stdout = b''.join(json.dumps(row).encode() + b'\n' for row in events)
        clocks = {'slot_started_ns': 100, 'consumer_deadline_ns': 450_000_000_100,
                  'owned_deadline_ns': 600_000_000_100}
        result = {'clocks': clocks}
        save(folder / 'SLOT_RESULT.json', result)
        publication = {'result_sha256': pin(folder / 'SLOT_RESULT.json')['sha256'], 'slot_started_ns': 100,
            'slot_result_published_ns': 1000, 'complete_slot_ns': 900, 'status': 'completed'}
        consumer = {'thread_id': 'synthetic-' + slot, 'raw_usage_events': [usage], 'usage_rows': [usage], 'usage': usage,
            'stdout_raw_sha256': hashlib.sha256(stdout).hexdigest(), 'model': 'gpt-6.1-sol',
            'requested_effort': 'medium', 'expected_thread_id': None, 'turn_index': 1,
            'argv': ['fake-codex.exe', '-c', 'model="gpt-6.1-sol"', '-c', 'model_reasoning_effort="medium"',
                '-c', 'service_tier="default"', '-m', 'gpt-6.1-sol'], 'tool_calls': [{}],
            'prompt_to_final_ns': 600, 'resolved_effort': None, 'exit_code': 0,
            'runtime_exit': {'exit_code': 1, 'confirmed': True}, 'bridge_cleanup': {'receipt_status': 'missing'},
            'public_text_bytes': 30, 'output_text_bytes': 20, 'provider_requests': None, 'fees': None,
            'image_tokens': None, 'usage_semantics': 'synthetic raw terminal event'}
        save(folder / 'SLOT_PUBLICATION.json', publication)
        save(folder / 'consumer/CONSUMER.json', consumer)
        save(folder / 'consumer/FINAL_TIMING.json', {'started_ns': 200, 'consumer_record_closed_ns': 900,
            'full_turn_wall_ns': 700})
        save(folder / 'owner/TOOLS.json', {'calls': 1, 'tools': [{'elapsed_ns': 100, 'is_error': False, 'response_bytes': 120}]})
        save(folder / 'owner/METRICS.json', {'tool_attempts': 1, 'public_content': [{'text_UTF8_bytes': 30,
            'image_blocks': 1, 'PNG_bytes': 40, 'base64_chars': 56, 'image_block_JSON_bytes': 100}],
            'transport': [{'started_ns': 300, 'closed_ns': 400}]})
        with (folder / 'consumer/stdout.raw.bin').open('xb') as stream:
            stream.write(stdout)
        requests = []
        for index in range(calls):
            query = {'mode': 'active_observation' if index == 0 else 'task'}
            if joint:
                query['task_query'] = {'mode': 'task'}
            rid = 'synthetic-' + str(index)
            requests.append({'id': rid, 'request': {'id': rid, 'method': 'tools/call',
                'params': {'name': 'human_eye_scene_observe', 'arguments': {'query': query}}}})
        with (folder / 'PUBLIC_REQUESTS.jsonl').open('xb') as stream:
            stream.write(b''.join(json.dumps(row).encode() + b'\n' for row in requests))
        return folder

    original_sha = module.sha

    def synthetic_cli_sha(path):
        if Path(path).name == 'fake-codex.exe':
            return '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
        return original_sha(path)

    quality_row = {'final_quality_passed': True, 'adoption': {'actual_product_facts_adopted': True}}
    with patch.object(module, 'sha', side_effect=synthetic_cli_sha):
        fixture('A1', 2)
        fixture('B1', 1, joint=True)
        a, b = [module.collect(slot, quality_row) for slot in ('A1', 'B1')]
        check('A_batch_one_outer_and_two_public_requests', a['business_tools'] == 1 and a['internal_public_MCP_requests'] == 2)
        check('B_joint_one_outer_and_one_public_request', b['business_tools'] == 1
            and b['internal_public_MCP_requests'] == b['internal_joint_requests'] == 1)
        check('cached_input_is_subset_not_added_to_raw', a['raw_input_plus_output'] == 110)
        check('uncached_input_and_output_computed_separately', a['uncached_input_tokens'] == 40 and a['uncached_input_plus_output'] == 50)
        check('reasoning_subset_is_not_double_counted', a['raw_usage']['reasoning_output_tokens'] == 2
            and a['raw_input_plus_output'] == 110)
        check('nested_cost_clocks_not_added_to_complete_slot', a['complete_slot_ns'] == 900
            and a['consumer_complete_ns'] == 700 and a['business_service_ns'] == a['owner_RPC_all_exchange_ns'] == 100)
        check('missing_EXIT_receipt_and_known_held_exit_preserved', a['thin_adapter_EXIT_receipt_status'] == 'missing'
            and a['thin_adapter_exit_code'] == 1 and a['thin_adapter_exit_confirmed'] is True)
        for name, mutate in (
            ('duplicate_terminal_usage', lambda folder: (folder / 'consumer/stdout.raw.bin').write_bytes(
                (folder / 'consumer/stdout.raw.bin').read_bytes() + json.dumps({'type': 'turn.completed',
                    'usage': {'input_tokens': 100, 'cached_input_tokens': 60, 'output_tokens': 10,
                              'reasoning_output_tokens': 2}}).encode() + b'\n')),
            ('wrong_profile', lambda folder: replace_json(folder / 'consumer/CONSUMER.json',
                lambda value: value['argv'].__setitem__(4, 'model_reasoning_effort="high"'))),
            ('wrong_publication', lambda folder: replace_json(folder / 'SLOT_PUBLICATION.json',
                lambda value: value.update(result_sha256='wrong'))),
            ('zero_complete_window', lambda folder: replace_json(folder / 'SLOT_PUBLICATION.json',
                lambda value: value.update(slot_result_published_ns=100, complete_slot_ns=0))),
        ):
            # Each mutation uses another in-memory-style saved fixture directory.
            slot = {'duplicate_terminal_usage': 'A2', 'wrong_profile': 'B2',
                    'wrong_publication': 'A3', 'zero_complete_window': 'B3'}[name]
            folder = fixture(slot, 1)
            mutate(folder)
            try:
                module.collect(slot, quality_row)
            except (ValueError, KeyError):
                check('reject_' + name, True)
            else:
                check('reject_' + name, False)
    empty_runtime = output / 'empty_runtime'
    empty_runtime.mkdir()
    module.RUNTIME = empty_runtime.resolve()
    run = {'records': [{'slot_id': slot, 'status': 'not_run'} for slot in module.ORDER]}
    audit = {'passed_checked_scope': True, 'budget': {}}
    reasons = module.incomplete_cost_reasons(run, audit)
    check('unrun_slots_classified_without_reading_missing_costs', len(reasons) == 6
        and all(row['reason'] == 'missing_cost_records' for row in reasons))
    failed_audit = module.incomplete_cost_reasons(run, {'passed_checked_scope': False})
    check('failed_runtime_audit_is_preserved_as_noncomparability', any(row['scope'] == 'runtime' for row in failed_audit))
    save(module.HERE / 'QUALITY_SEAL.json', {'quality_sha256': 'synthetic-quality', 'cost_unlocked': True})
    quality = {'A_quality_count': 0, 'B_quality_count': 0, 'B_actual_joint_fact_adoption_count': 0,
        'slots': [{'slot_id': slot, **quality_row, 'final_quality_passed': False} for slot in module.ORDER]}
    module.save_incomplete(run, quality, {'quality_sha256': 'synthetic-quality'}, audit, 1, reasons)
    failed = json.loads((module.HERE / 'DECISION.json').read_bytes())
    check('negative_decision_retains_six_denominator_and_rows', failed['quality_denominator'] == len(failed['rows']) == 6
        and [row['slot_id'] for row in failed['rows']] == module.ORDER)
    check('negative_decision_does_not_impute_missing_usage_or_cost', all(row['complete_slot_ns'] is None
        and row['original_usage_events'] is None for row in failed['rows']) and failed['totals'] is None)
    check('negative_decision_never_passes_candidate_gate', failed['passed_frozen_gates'] is False
        and failed['gates']['same_source_comparable_usage'] is False)
    tree = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    main_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    assignments = {node.targets[0].id: node.value for node in main_node.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    gates = {row.arg: row.value for row in assignments['gates'].keywords}
    plan = {'decision_gate': {'complete_time_paired_median_max': .90, 'B_faster_pairs_min': 2}}

    def evaluate(node, **values):
        return eval(compile(ast.Expression(node), str(SOURCE), 'eval'), {'statistics': statistics, **values})

    for denominator in (10, 1_000_000_000, 590_000_000_000):
        for offset in (-1, 0, 1):
            numerator = denominator * 9 // 10 + offset
            ratio = numerator / denominator
            check('time_0_90_boundary_' + str(denominator) + '_' + str(offset),
                evaluate(gates['complete_time_paired_median'], ratio=ratio, plan=plan)
                == (Fraction(numerator, denominator) <= Fraction(9, 10)))
    for faster in (0, 1, 2, 3):
        pairs = [{'B_faster': index < faster} for index in range(3)]
        check('strict_faster_pair_count_' + str(faster), evaluate(gates['B_faster_pairs'], pairs=pairs, plan=plan) == (faster >= 2))
    b_rows = [{'adopted': True}, {'adopted': True}, {'adopted': False}]
    check('unknown_adoption_keeps_frozen_gate_false', evaluate(gates['B_actual_joint_adoption'],
        quality={'B_actual_joint_fact_adoption_count': 2}, b_rows=[{'adopted': True}, {'adopted': True}, {'adopted': None}]) is False)
    check('two_final_joint_adoptions_do_not_count_as_three', evaluate(gates['B_actual_joint_adoption'],
        quality={'B_actual_joint_fact_adoption_count': 2}, b_rows=b_rows) is False)
    check('raw_token_gate_uses_absolute_totals', evaluate(gates['B_total_raw_input_plus_output'],
        totals={'A': {'raw_input_plus_output': 110}, 'B': {'raw_input_plus_output': 111}}) is False)
    output_node = assignments['output']
    reduction = next(row.value for row in output_node.keywords if row.arg == 'total_raw_input_plus_output_reduction')
    check('zero_A_raw_token_total_has_unknown_display_ratio', evaluate(reduction,
        totals={'A': {'raw_input_plus_output': 0}, 'B': {'raw_input_plus_output': 0}}) is None)
    source = SOURCE.read_text(encoding='utf-8')
    check('quality_seal_and_frozen_runtime_inputs_revalidated', "verify_pins(seal['source_pins'])" in source
        and "verify_pins(frozen['files'])" in source and "verify_pins(audit['input_pins'])" in source)
    check('source_unchanged_during_review', pin(SOURCE) == before)
    report = {'schema': 'm5-task-cost-checker-pure-v1', 'passed_checked_scope': all(row['passed'] for row in checks),
        'reviewed_source': before, 'checks': checks, 'check_count': len(checks),
        'passed_count': sum(row['passed'] for row in checks), 'reviewer_source': pin(__file__),
        'author_association': 'Root authored cost_decision.py. This reviewer authored this independent source/synthetic checker, the public task bridge and later saved sealer. This is not a blind or administrator acceptance.',
        'root_corrections_reviewed': ['Failed/unrun/missing-usage evidence produces an explicit negative decision with six denominator.',
            'Display-only token reduction is unknown for zero A tokens; frozen absolute token gate unchanged.',
            'Positive complete time is required before paired duration ratios.'],
        'scope': 'Only cost source and namespace synthetic records. Actual formal numeric ranking, consumers and runtime records were not read. Actual four-clock/source/budget provenance remains bound through the root runtime audit and its verified input pins.',
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'rasters': 0,
            'model_consumers': 0, 'root_cost_main_executions': 0}}
    save(HERE / 'COST_CHECKER_REVIEW.json', report)
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(checks),
        'failed': [row['name'] for row in checks if not row['passed']], 'source_sha256': before['sha256']}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


def replace_json(path, mutate):
    value = json.loads(path.read_bytes())
    mutate(value)
    path.write_text(json.dumps(value), encoding='utf-8')


if __name__ == '__main__':
    main()
