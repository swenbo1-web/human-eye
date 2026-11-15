"""Six-slot, source-quoted task quality and actual product-fact adoption."""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
PRODUCT = {'A': '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be',
           'B': '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'}
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path))


def load(path, name):
    raw(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_load(path, name):
    module = load(path, name)
    if hasattr(module, 'read'):
        module.read = read
    if hasattr(module, 'sha'):
        module.sha = lambda filename: hashlib.sha256(raw(filename)).hexdigest()
    if hasattr(module, 'load'):
        module.load = tracked_load
    return module


def terminal(slot, outer, result, publication, envelope, consumer):
    checks = []

    def need(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})

    need('slot_schema_and_label', result.get('schema') == 'target-task-consumption-slot-v1'
         and result.get('slot_id') == slot and result.get('group') == slot[:1] and result.get('phase') == 'formal')
    need('slot_actual_completed', outer.get('status') == result.get('status') == envelope.get('status') == 'completed')
    need('slot_errors', result.get('errors') == [])
    need('envelope_identity', envelope.get('slot_id') == slot and envelope.get('group') == slot[:1])
    need('current_product_source', result.get('source', {}).get('product_source141_sha256') == PRODUCT[slot[:1]]
         and envelope.get('source', {}).get('product_source141_sha256') == PRODUCT[slot[:1]])
    need('current_fixed_asset', result.get('source', {}).get('asset_sha256') ==
         '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164')
    clocks = result.get('clocks', {})
    start = clocks.get('slot_started_ns')
    valid_deadlines = (type(start) is int and clocks.get('consumer_deadline_ns') == start+450_000_000_000
                       and clocks.get('owned_deadline_ns') == start+600_000_000_000)
    need('original_absolute_deadlines', valid_deadlines
         and consumer.get('deadline_ns') == clocks.get('consumer_deadline_ns')
         and result.get('owned', {}).get('worker_deadline_ns') == clocks.get('consumer_deadline_ns')
         and result.get('owned', {}).get('owned_deadline_ns') == clocks.get('owned_deadline_ns'))
    need('publication_within_original_lifecycle', valid_deadlines
         and publication.get('slot_started_ns') == start
         and type(publication.get('slot_result_published_ns')) is int
         and start <= publication['slot_result_published_ns'] <= clocks['owned_deadline_ns'])
    for field, path in (('common_task_sha256', HERE / 'inputs/COMMON_TASK.txt'), ('answer_schema_sha256', HERE / 'inputs/ANSWER_SCHEMA.json')):
        digest = hashlib.sha256(raw(path)).hexdigest()
        need(field, result.get('source', {}).get(field) == envelope.get('source', {}).get(field) == digest)
    launcher = load(HERE / 'launcher.py', '_consume_expected_common_prompt')
    expected_prompt = hashlib.sha256(launcher.common_prompt(slot[:1])).hexdigest()
    need('actual_prompt_hash', consumer.get('input_sha256') == envelope.get('source', {}).get('prompt_sha256') == expected_prompt)
    need('consumer_valid_completion', consumer.get('valid_completion') is True and consumer.get('status') == 'completed')
    need('fixed_model_effort', consumer.get('model') == 'gpt-6.1-sol' and consumer.get('requested_effort') == 'medium')
    need('consumer_single_turn', consumer.get('turn_index') == 1 and consumer.get('expected_thread_id') is None)
    for key in ('runtime_binding', 'runtime_exit'):
        need('consumer_' + key, type(consumer.get(key)) is dict and consumer[key].get('confirmed') is True)
    need('consumer_exit', consumer.get('process_reaped') is True and consumer.get('exit_code') == 0
         and consumer.get('readers_stopped') is True)
    need('consumer_protocol', consumer.get('errors') == [] and consumer.get('unexpected_tool_deviations') == []
         and consumer.get('bridge_protocol_errors') == [] and consumer.get('mutation_unknown') is False)
    cleanup = result.get('cleanup', {})
    need('actor_exit', cleanup.get('actor_exit_code') == 0)
    for kind in ('native', 'mcp'):
        need('held_' + kind + '_exit', cleanup.get(kind, {}).get('confirmed') is True
             and cleanup.get(kind, {}).get('exit_code') == 0 and cleanup.get(kind, {}).get('forced_by_root') is False)
    actor = cleanup.get('actor_close') or {}
    need('actor_errors', actor.get('errors') == [])
    need('bridge_close', actor.get('bridge', {}).get('confirmed') is True and actor.get('bridge', {}).get('errors') == [])
    runtime = actor.get('runtime') or {}
    need('runtime_errors', runtime.get('errors') == [] and runtime.get('runtime', {}).get('errors') == [])
    native = runtime.get('Blender_close') or {}
    need('owned_Blender_reaped_unchanged', native.get('process_reaped') is True and native.get('exit_code') == 0
         and native.get('source_file_unchanged') is True and native.get('protected_files_unchanged') is True)
    native_status = runtime.get('Blender_status') or {}
    closed = native_status.get('closed') or {}
    need('full_scene_unchanged', closed.get('initial_geometry_fingerprint') == closed.get('final_geometry_fingerprint')
         and type(closed.get('initial_geometry_fingerprint')) is str and closed.get('poisoned') is False)
    need('actual_publication_binding', publication.get('schema') == 'target-task-slot-publication-v1'
         and publication.get('slot_id') == slot and publication.get('group') == slot[:1]
         and publication.get('result_sha256') == hashlib.sha256(raw(outer['result_path'])).hexdigest())
    return {'passed': all(row['passed'] for row in checks), 'checks': checks,
            'failed_fields': [row['check'] for row in checks if not row['passed']]}


def bind_tools(evidence, consumer):
    path = HERE.parent / 'm4_consumer_error_contract_001/result_contract.py'
    if hashlib.sha256(raw(path)).hexdigest() != '5da53bbbfee51f1c07fde32ecf0e1ab1e79a73ef68feff388f709931840cd638':
        raise ValueError('accepted_result_contract_changed')
    contract = load(path, '_consume_actual_tool_result_contract')
    calls = consumer['tool_calls']
    requests, responses = evidence['actual_tool_requests'], evidence['actual_tool_results']
    if len(calls) != len(requests) or len(calls) != len(responses) or len(calls) > 12:
        raise ValueError('actual_tool_count_or_budget')
    for request_path, response_path, call in zip(requests, responses, calls):
        request, response = read(request_path), read(response_path)
        item = call['item']
        if request['params']['name'] != item['tool'] or request['params']['arguments'] != item['arguments']:
            raise ValueError('actual_CLI_tool_request_mismatch')
        if type(request['id']) is not type(response['id']) or request['id'] != response['id']:
            raise ValueError('actual_tool_response_id')
        if not contract.bind_tool_result(response, item)['matched']:
            raise ValueError('actual_CLI_tool_response_mismatch')


def grade_slot(slot, row, outer, runtime_root, truth, claims, saved, quoted):
    folder = runtime_root / slot
    result_path = Path(outer['result_path']).resolve()
    if result_path != (folder / 'SLOT_RESULT.json').resolve():
        raise ValueError('actual_slot_result_path')
    result = read(result_path)
    publication_path = Path(outer['publication_path']).resolve()
    if publication_path != (folder / 'SLOT_PUBLICATION.json').resolve():
        raise ValueError('actual_slot_publication_path')
    publication = read(publication_path)
    envelope_path = Path(result['consumer_envelope_path']).resolve()
    if envelope_path != (folder / 'CONSUMER_ENVELOPE.json').resolve():
        raise ValueError('actual_consumer_envelope_path')
    envelope = read(envelope_path)
    consumer_path = Path(result['consumer_record']).resolve()
    if consumer_path != (folder / 'consumer/CONSUMER.json').resolve() or Path(envelope['consumer_record']).resolve() != consumer_path:
        raise ValueError('actual_consumer_record_path')
    consumer = read(consumer_path)
    term = terminal(slot, outer, result, publication, envelope, consumer)
    final_path = (folder / 'consumer/PUBLIC_FINAL.txt').resolve()
    final_blob = raw(final_path)
    final = final_blob.decode('utf-8')
    if final != consumer['final'] or row['raw_answer_sha256'] != hashlib.sha256(final_blob).hexdigest() or Path(row['raw_answer_path']).resolve() != final_path:
        raise ValueError('actual_final_bytes_binding')
    excerpt = row.get('answer_excerpt')
    if type(excerpt) is not str or not excerpt or excerpt not in final:
        raise ValueError('actual_answer_excerpt')
    evidence = saved.evaluate_slot(folder, truth)
    local_aliases = {}
    import copy
    for region in row['answer'].get('regions', []):
        label = region.get('identity', {}).get('roi_id')
        if label is None:
            continue
        if type(label) is not str or not label:
            raise ValueError('consumer_local_label_type')
        descriptor = copy.deepcopy(region)
        descriptor['identity'].pop('roi_id')
        resolved = claims.identify(descriptor, truth, evidence['aliases'])
        known = {**evidence['aliases'], **local_aliases}
        if resolved is None or label in known and known[label] != resolved:
            raise ValueError('consumer_local_label_source_conflict')
        local_aliases[label] = resolved
    evidence['aliases'].update(local_aliases)
    bind_tools(evidence, consumer)
    for index, request_path in enumerate(evidence['actual_tool_requests'], 1):
        name = read(request_path)['params']['name']
        evidence['current_source_references'].append('current-tool:' + str(index) + ':' + name)
    if not evidence['initial_product_entry']:
        raise ValueError('configured_product_first_entry')
    for item in row.get('sources', []):
        raw(item['path'])
    source = quoted.Sources(folder, final, row.get('sources', []), evidence['actual_tool_results'], evidence['actual_tool_requests'])
    if not row.get('claim_support') or not all(source.support(support) for support in row['claim_support']):
        raise ValueError('actual_claim_quotations_required')
    quoted.validate_reference_resolutions(row, final, source, evidence)
    try:
        quality = claims.grade_answer(row['answer'], row, truth, evidence)
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as error:
        quality = {'passed': False, 'checks': [{'check': 'well_formed_final_claims', 'passed': False}],
                   'errors': ['malformed_final_claim:' + type(error).__name__ + ':' + str(error)]}
    adopted = quoted.adoption(row, final, source, evidence,
        lambda identity: claims.identify(identity, truth, evidence['aliases']), term['passed'] and quality['passed'])
    return {'slot_id': slot, 'group': slot[:1], 'execution_state': result['status'],
            'final_quality_passed': term['passed'] and quality['passed'], 'terminal_binding': term,
            'claim_quality': quality, 'adoption': adopted, 'saved_evidence': evidence['summary'],
            'native_local_aliases_validated': local_aliases,
            'raw_field_observations': row.get('raw_field_observations'),
            'errors': term['failed_fields'] + quality['errors']}


def score(args):
    contract = read(HERE / 'admin/SCORING_CONTRACT.json')
    if contract['schema'] != 'm5-task-consumption-scoring-contract-v1':
        raise ValueError('frozen_scoring_contract')
    for path, digest in contract['files_sha256'].items():
        if hashlib.sha256(raw(path)).hexdigest() != digest:
            raise ValueError('frozen_scoring_source_changed:' + path)
    normalized = read(args.normalized)
    if normalized['schema'] != 'm5-task-consumption-normalized-v1':
        raise ValueError('normalized_schema')
    rows = normalized['slots']
    if len(rows) != 6 or Counter(row['slot_id'] for row in rows) != Counter(ORDER):
        raise ValueError('six_unique_normalized_slots')
    review = read(normalized['semantic_review_path'])
    if (review['schema'] != 'm5-task-consumption-semantic-review-v1'
            or review['normalized_sha256'] != hashlib.sha256(raw(args.normalized)).hexdigest()
            or review.get('all_six_reviewed') is not True or review.get('passed') is not True):
        raise ValueError('source_only_independent_semantic_review_required')
    run = read(args.runtime_root.parent / 'RUN_RESULT.json')
    records = run['records']
    if (run['schema'] != 'target-task-consumption-run-v1' or len(records) != 6
            or [row['slot_id'] for row in records] != list(ORDER)
            or any(row['group'] != row['slot_id'][:1] for row in records)
            or run.get('outer_retries') != 0 or run.get('replacement_samples') != 0
            or run.get('planned_slots') != 6):
        raise ValueError('actual_six_slot_producer_contract')
    consumers = []
    for outer in records:
        if outer['status'] == 'not_run':
            continue
        result = read(outer['result_path'])
        path = result.get('consumer_record')
        if path is not None and Path(path).is_file():
            consumer = read(path)
            if consumer.get('image_delivery', {}).get('CLI_process_launched') is True:
                consumers.append(consumer)
    if type(run.get('actual_consumers')) is not int or run['actual_consumers'] != len(consumers):
        raise ValueError('actual_consumer_count_binding')
    truth = read(HERE / 'admin/TRUTH.json')
    for pin in truth['independent_reference_pins']:
        if hashlib.sha256(raw(pin['path'])).hexdigest() != pin['sha256']:
            raise ValueError('private_independent_reference_changed')
    claims = load(HERE / 'grade_claims.py', '_consume_exact_claims')
    saved = tracked_load(HERE / 'saved_evidence.py', '_consume_current_saved_evidence')
    quoted = load(HERE / 'quoted_sources.py', '_consume_source_quotations')
    results = []
    for slot in ORDER:
        row = next(row for row in rows if row['slot_id'] == slot)
        outer = next(row for row in records if row['slot_id'] == slot)
        if outer['status'] == 'not_run':
            results.append({'slot_id': slot, 'group': slot[:1], 'execution_state': 'not_run',
                            'final_quality_passed': False, 'adoption': {'actual_product_facts_adopted': False,
                                'observation_facts_adopted': False, 'measurement_facts_adopted': False,
                                'whole_objects_scope_correct': False, 'actual_A_batch_used': False},
                            'errors': ['not_run', outer.get('reason')]})
            continue
        try:
            results.append(grade_slot(slot, row, outer, args.runtime_root, truth, claims, saved, quoted))
        except (OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError, StopIteration, AssertionError) as error:
            results.append({'slot_id': slot, 'group': slot[:1], 'execution_state': outer.get('status', 'unknown'),
                            'final_quality_passed': False, 'adoption': {'actual_product_facts_adopted': None,
                                'observation_facts_adopted': None, 'measurement_facts_adopted': None,
                                'whole_objects_scope_correct': None, 'actual_A_batch_used': None},
                            'errors': [{'type': type(error).__name__, 'message': str(error)}]})
    output = {'schema': 'm5-task-consumption-quality-v1', 'denominator': 6, 'slots': results,
              'all_six_quality_complete': all(row['final_quality_passed'] for row in results),
              'A_quality_count': sum(row['slot_id'][:1] == 'A' and row['final_quality_passed'] for row in results),
              'B_quality_count': sum(row['slot_id'][:1] == 'B' and row['final_quality_passed'] for row in results),
              'B_actual_joint_fact_adoption_count': sum(row['slot_id'][:1] == 'B'
                  and row['adoption']['actual_product_facts_adopted'] is True for row in results),
              'A_batch_adoption_count': sum(row['slot_id'][:1] == 'A'
                  and row['adoption'].get('actual_A_batch_used') is True for row in results),
              'cost_analysis_performed': False, 'new_model_product_raster_calls': 0,
              'inputs_sha256': dict(sorted(INPUTS.items()))}
    destination = args.output.resolve()
    if not destination.is_relative_to(HERE):
        raise ValueError('new_namespace_output_required')
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_m5_task_consume_001/formal'))
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_root.resolve() != Path('D:/he_m5_task_consume_001/formal').resolve():
        raise ValueError('fixed_formal_root')
    result = score(args)
    print(json.dumps({'denominator': 6, 'quality': result['all_six_quality_complete'],
                      'B_adoption': result['B_actual_joint_fact_adoption_count'], 'cost_analysis_performed': False}))


if __name__ == '__main__':
    main()
