"""Offline producer, adoption-evidence and byte-counter checks without runs."""

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_occluded_scene_transfer_001')
OLD_RUNTIME = Path('D:/he_occluded_transfer_001/formal')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def load_scorer():
    spec = importlib.util.spec_from_file_location('_m1_offline_scorer', HERE / 'score_saved.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def methods(path):
    cls = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(node, ast.ClassDef) and node.name == 'Grader')
    return {node.name: ast.dump(node, include_attributes=False)
            for node in cls.body if isinstance(node, ast.FunctionDef)}


def checks():
    scorer = load_scorer()
    paths = [OLD_RUNTIME / 'RUN_RESULT.json', OLD_RUNTIME / 'LAUNCH_RESULT.json']
    old_order = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
    paths.extend(OLD_RUNTIME / slot / 'c/CONSUMER.json' for slot in old_order)
    paths.extend(sorted((OLD_RUNTIME / 'P1/o').glob('tool_*/RESPONSE.json')))
    paths.append(OLD_RUNTIME / 'P1/o/METRICS.json')
    before = {str(path): sha(path) for path in paths}
    run = copy.deepcopy(read(paths[0]))
    launch = copy.deepcopy(read(paths[1]))
    consumers = {new: read(OLD_RUNTIME / old / 'c/CONSUMER.json')
                 for new, old in zip(scorer.ORDER, old_order)}
    # Only metadata is adapted. The original files remain untouched. This
    # fixture checks the new reader contract without claiming new A/B runs.
    run.update(schema='source-face-binding-six-route-v1', internal_execution_group='P',
               comparison_sequence=[dict(slot=s, group='P', comparison_arm=s[0]) for s in scorer.ORDER])
    for row, slot in zip(run['records'], scorer.ORDER):
        row.update(slot=slot, group='P', comparison_arm=slot[0])
    launch.update(schema='source-face-binding-launch-v1', internal_execution_group='P',
                  comparison_arms={slot: slot[0] for slot in scorer.ORDER},
                  execution_states={slot: row['execution_state'] for slot, row in zip(scorer.ORDER, run['records'])})
    output = []

    def check(name, passed, detail=None):
        output.append(dict(name=name, passed=bool(passed), detail=detail))

    for slot in scorer.ORDER:
        result = scorer.terminal_binding(run, launch, slot, consumers[slot])
        check('adapted_actual_saved_producer_' + slot, result['passed'], result)
    controls = [
        ('old_schema', 'run.schema', 'run', 'schema', 'routed-task-benefit-six-route-v1'),
        ('extra_retry', 'run.outer_retries', 'run', 'outer_retries', 1),
        ('bool_retry', 'run.outer_retries', 'run', 'outer_retries', False),
        ('wrong_internal_group', 'run.internal_execution_group', 'run', 'internal_execution_group', 'A'),
        ('wrong_row_group', 'run.records', 'row', 'group', 'A'),
        ('wrong_row_arm', 'run.records', 'row', 'comparison_arm', 'B'),
        ('wrong_row_slot', 'run.records', 'row', 'slot', 'B1'),
        ('failed_slot', 'slot.execution_state', 'row', 'execution_state', 'failed'),
        ('wrapper_error', 'slot.slot_wrapper_errors', 'row', 'slot_wrapper_errors', [{'type': 'control'}]),
        ('invalid_consumer', 'consumer.valid_completion', 'consumer', 'valid_completion', False),
        ('missing_exit', 'consumer.runtime_exit', 'consumer', 'runtime_exit', None),
        ('launch_error', 'launch.terminal_errors', 'launch', 'terminal_errors', [{'type': 'control'}]),
        ('wrong_launch_arms', 'launch.comparison_arms', 'launch', 'comparison_arms', {}),
    ]
    for name, field, kind, key, value in controls:
        r, l, c = copy.deepcopy(run), copy.deepcopy(launch), copy.deepcopy(consumers['A1'])
        target = {'run': r, 'launch': l, 'consumer': c, 'row': r['records'][0]}[kind]
        target[key] = value
        result = scorer.terminal_binding(r, l, 'A1', c)
        check(name, not result['passed'] and field in result['failed_fields'], result)
    old_methods, new_methods = methods(OLD / 'score_saved.py'), methods(HERE / 'score_saved.py')
    for name in ('identity', 'tools', 'support', 'witness', 'extent', 'unsupported_identity', 'adoption'):
        check('inherited_rule_AST_' + name, old_methods[name] == new_methods[name])

    grader = scorer.Grader(read(HERE / 'admin/TRUTH.json'), read(HERE / 'admin/PIXEL_TRUTH.json'),
                           Path('D:/he_source_face_001/formal'))
    owner = HERE / 'offline_adoption_owner'
    identity = next(iter(grader.targets))
    grader.aliases = {'public-roi': identity}
    grader.sources = {'product': 'current public source range row', 'request': 'actual face-range lookup code',
                     'final': 'task result from source-face lookup'}
    grader.source_paths = {'product': owner / 'tool_01/RESPONSE.json', 'request': owner / 'tool_02/REQUEST.json'}
    grader.source_kinds = {'product': 'tool_result', 'request': 'tool_request', 'final': 'final'}
    support = lambda source: [{'source_id': source, 'excerpt': grader.sources[source]}]
    claim = dict(identity={'roi_id': 'public-roi'}, operation='source_face_to_region_lookup',
                 binding_scoped=True, dataflow_confirmed_by_review=True,
                 product_support=support('product'), operation_support=support('request'),
                 task_use_support=support('final'))
    evidence = dict(comparison_arm='B', source_face_binding_delivered=True)
    result = grader.source_binding_use({'source_binding_use': {'claims': [claim]}}, owner, {}, evidence)
    check('binding_use_supported_dataflow', result['actual_binding_adopted'], result)
    result = grader.source_binding_use({}, owner, {}, evidence)
    check('mere_field_delivery_is_not_adoption', not result['actual_binding_adopted'], result)
    for name, key, value in [('no_operation_evidence', 'operation_support', []),
                             ('no_final_task_use', 'task_use_support', []),
                             ('unreviewed_dataflow', 'dataflow_confirmed_by_review', False),
                             ('unscoped_binding', 'binding_scoped', False)]:
        control = copy.deepcopy(claim)
        control[key] = value
        result = grader.source_binding_use({'source_binding_use': {'claims': [control]}}, owner, {}, evidence)
        check(name, not result['actual_binding_adopted'], result)
    result = grader.source_binding_use({'source_binding_use': {'claims': [claim]}}, owner, {},
                                      dict(comparison_arm='A', source_face_binding_delivered=False))
    check('old_A_cannot_adopt_undelivered_default_binding', not result['actual_binding_adopted'], result)
    declaration = dict(observed=False, review_complete=True, reviewed_tool_attempts=[1, 2],
                       support=support('request'), reason='Controlled complete request review')
    result = grader.process_diagnostics({'process_diagnostics': {'geometry_reverse_lookup': declaration}}, owner,
                                       {'tool_calls': [{}, {}]}, evidence)
    check('complete_review_can_record_absence', result['geometry_reverse_lookup']['observed'] is False, result)
    declaration['reviewed_tool_attempts'] = [2]
    result = grader.process_diagnostics({'process_diagnostics': {'geometry_reverse_lookup': declaration}}, owner,
                                       {'tool_calls': [{}, {}]}, evidence)
    check('partial_review_keeps_absence_unknown', result['geometry_reverse_lookup']['observed'] is None, result)

    consumer = consumers['B1']
    actual_tool_text = 0
    for path in sorted((OLD_RUNTIME / 'P1/o').glob('tool_*/RESPONSE.json')):
        actual_tool_text += sum(len(block['text'].encode('utf-8'))
                                for block in read(path)['result']['content'] if block.get('type') == 'text')
    metric_tool_text = sum(tool['content_metrics']['text_UTF8_bytes']
                           for tool in read(OLD_RUNTIME / 'P1/o/METRICS.json')['tools'])
    assistant_text = sum(len(message['text'].encode('utf-8')) for message in consumer['all_public_messages'])
    check('actual_saved_tool_text_matches_content_metrics', actual_tool_text == metric_tool_text,
          dict(actual_tool_text_UTF8=actual_tool_text, metric_tool_text_UTF8=metric_tool_text))
    check('assistant_text_is_separate_counter', assistant_text == consumer['public_text_bytes']
          and actual_tool_text != assistant_text, dict(assistant_text_UTF8=assistant_text, tool_text_UTF8=actual_tool_text))
    after = {str(path): sha(path) for path in paths}
    check('saved_inputs_unchanged', before == after)
    return dict(schema='source-face-offline-scoring-interface-v1', passed=all(row['passed'] for row in output),
                checks=output, denominator=len(output), saved_actual_inputs_sha256=before,
                fixture_scope='Metadata adaptation over prior real six-route records; controlled new dataflow cases. No new A/B execution is asserted.',
                scorer_sha256=sha(HERE / 'score_saved.py'), cost_source_sha256=sha(HERE / 'cost_audit.py'),
                full_content_scoring_calls=0, new_model_observe_raster_calls=0)


def prepare_contract():
    paths = [HERE / name for name in ('score_saved.py', 'cost_audit.py', 'saved_evidence.py', 'oracle.py',
        'SCORING_PLAN.md', 'interface_scoring.py', 'PLAN.json', 'inputs/PROMPT.txt',
        'inputs/SOURCES_A.json', 'inputs/SOURCES_B.json', 'admin/TRUTH.json', 'admin/PIXEL_TRUTH.json',
        'admin/REFERENCE_TRUTH_BINDING.json', 'admin/NORMALIZATION_SCHEMA.json')]
    paths.append(ROOT / 'verification/m4_consumer_error_contract_001/result_contract.py')
    plan = read(HERE / 'PLAN.json')
    paths.extend(Path(spec['path']) for spec in plan['products'].values())
    reference = read(HERE / 'admin/REFERENCE_TRUTH_BINDING.json')
    paths.extend(Path(spec['path']) for spec in reference['files'].values())
    value = dict(schema='source-face-binding-scoring-contract-v1', administrator_only=True,
        formal_slots=['A1', 'B1', 'B2', 'A2', 'A3', 'B3'], actual_internal_execution_group='P',
        files_sha256={str(path.resolve()): sha(path) for path in paths},
        thresholds=dict(surface_pixels=16, boundary_pixels=4, RGB_distance=24),
        finite_pool_reason_codes=['no_front_facing_candidate', 'positive_area_occlusion_all_front_views',
            'no_complete_geometric_candidate', 'pixel_evidence_insufficient'],
        adoption_observed_independently_of_task_quality=True, mere_field_presence_is_not_adoption=True,
        normalization_entailment_and_dataflow_review_required=True, direct_only_is_diagnostic=True,
        native_supplement_necessity='unmeasured', quality_before_cost=True,
        positive_signal=dict(A_quality=3, B_quality=3, B_binding_adoption=3,
            median_B_over_A_max=.90, minimum_B_faster_pairs=2, B_input_plus_output_not_increased=True),
        reference_truth='Exact original N6 qualified pixels reused with retained provenance. No N rerun.',
        byte_counter_scope='Actual tool reply text UTF8 and assistant public message UTF8 are independently counted.')
    save(HERE / 'admin/SCORING_CONTRACT.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-contract', action='store_true')
    args = parser.parse_args()
    result = checks()
    save(HERE / 'OFFLINE_SCORING_INTERFACE.json', result)
    if not result['passed']:
        print(json.dumps(dict(passed=False, failed=[r['name'] for r in result['checks'] if not r['passed']])))
        return 1
    if args.prepare_contract:
        prepare_contract()
    print(json.dumps(dict(passed=True, checks=result['denominator'], contract_prepared=args.prepare_contract)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
