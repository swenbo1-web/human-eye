"""Fixed-denominator saved quality audit of six main slots and two controls."""

import argparse
import importlib.util
import json
from pathlib import Path
import traceback


HERE = Path(__file__).resolve().parent
MAIN = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
CONTROLS = ['A_task_only', 'B_task_only']
SCHEDULE = MAIN + CONTROLS


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(root, b_binding):
    root = Path(root).resolve()
    ql = load('quality_saved_r2.py', '_m5_formal_quality')
    compare = load('review_qualification_r1.py', '_m5_formal_compare')
    residuals = load('witness_residuals.py', '_m5_formal_publication')
    work = load('review_work.py', '_m5_formal_work')
    task_only = load('review_task_only.py', '_m5_formal_task_only')
    run = ql.read(root / 'RUN_RESULT.json')
    errors = []
    labels = [row['label'] for row in run['records']]
    ql.require(run['schema'] == 'm5-formal-dispatch-result-v1', 'formal_result_schema')
    ql.require(len(labels) == len(set(labels)) and set(labels) <= set(SCHEDULE), 'formal_duplicate_or_unregistered_label')
    ql.require(labels == [label for label in SCHEDULE if label in labels], 'formal_registered_order')
    ql.require(run['retries'] == run['replacement_samples'] == 0, 'formal_no_retries_or_replacements')
    by_label = {row['label']: row for row in run['records']}
    builds = {'A': HERE / 'A_RUN_BINDING.json', 'B': Path(b_binding)}
    expected_sources = {arm: ql.read(path)['source_sha256'] for arm, path in builds.items()}
    registered = ql.read(HERE / 'REQUESTS.json')
    summaries, buffers, comparisons = [], {}, []
    for label in SCHEDULE:
        record = by_label.get(label)
        folder = root / label
        row = {'label': label, 'arm': label[0], 'kind': 'main' if label in MAIN else 'task_only',
               'status': 'not_run', 'passed_checked_scope': False, 'errors': []}
        if record is None:
            if (root / ('DISPATCH_' + label + '.json')).exists():
                row.update(status='dispatched_without_completed_record', reason=run.get('blocker'))
            else:
                row['reason'] = 'registered_slot_not_dispatched'
            summaries.append(row)
            continue
        try:
            ql.require(record['arm'] == label[0] and Path(record['output']).resolve() == folder,
                       'formal_current_label_arm_or_directory')
            expected_key = label[0] + '_main' if label in MAIN else 'task_only'
            ql.require(record['request_key'] == expected_key, 'formal_fixed_request_key')
            actual = ql.read(folder / 'RESULT.json')
            ql.require(actual['label'] == label and actual['phase'] == 'formal', 'actual_formal_slot_identity')
            ql.require(actual['source_sha256'] == expected_sources[label[0]], 'external_frozen_formal_source')
            ql.require([item['request'] for item in actual['requests']] == registered[expected_key], 'actual_formal_frozen_requests')
            ql.require(actual['model_calls'] == actual['paid_API_calls'] == 0, 'engineering_zero_model_paid_API_calls')
            if label in MAIN:
                review, arrays = ql.audit_slot(folder, label[0])
                task_request = actual['requests'][-1]
                public = ql.read(task_request['public_path'])
                task = public if label[0] == 'A' else public['task_result']
                review['nearest_displacement_publication'] = residuals.validate(task['facts']['surface_proximity'])
                if label[0] == 'B':
                    review['actual_work'] = work.audit(folder)
                    expected_task_keys = {'binding', 'coordinate_frame', 'execution_authority', 'facts', 'pair_order',
                                          'result_kind', 'schema_version', 'status', 'unit'}
                    ql.require(type(task) is dict and set(task) == expected_task_keys, 'formal_public_task_object_shape')
                    task_work = review['actual_work']['task_work']
                    ql.require(task_work['geometry_alias_parse_calls'] == 0 and task_work['geometry_alias_reuses'] == 2,
                               'formal_actual_final_alias_reuse')
                buffers[label] = arrays
            else:
                review = task_only.audit(folder, builds[label[0]])
            row.update(status='reviewed', passed_checked_scope=True, review=review)
        except Exception as error:
            row.update(status='failed', errors=[{'type': type(error).__name__, 'reason': str(error),
                                                 'traceback': traceback.format_exc()}])
        summaries.append(row)
    by_summary = {row['label']: row for row in summaries}
    for number in (1, 2, 3):
        a_label, b_label = 'A' + str(number), 'B' + str(number)
        pair = {'A': a_label, 'B': b_label, 'passed_checked_scope': False, 'errors': []}
        if not all(by_summary[label]['passed_checked_scope'] for label in (a_label, b_label)):
            pair['status'] = 'unavailable_due_to_failed_or_unrun_slot'
            comparisons.append(pair)
            continue
        try:
            left = compare.observation_comparison(root / a_label, by_summary[a_label]['review'], ql)
            right = compare.observation_comparison(root / b_label, by_summary[b_label]['review'], ql)
            semantic = {key: left[key] == right[key] for key in left}
            ql.require(all(semantic.values()), 'formal_A_B_entire_observation_quality')
            ql.require(len(buffers[a_label]) == len(buffers[b_label]), 'formal_A_B_selected_frame_count')
            _, q, _, _, _ = ql.dependencies()
            import numpy as np
            arrays = []
            for a, b in zip(buffers[a_label], buffers[b_label]):
                comparison = q.compare_normalized_buffers(a, b)
                comparison['patch_owners_equal'] = bool(np.array_equal(a['patch_owners'], b['patch_owners']))
                ql.require(comparison['equal'] and comparison['patch_owners_equal'], 'formal_A_B_actual_RGB_depth_owner_sourceface_patch')
                arrays.append(comparison)
            a_task, b_task = [by_summary[label]['review']['task']['numeric'] for label in (a_label, b_label)]
            ql.require(a_task['distance_m'] == b_task['distance_m'], 'formal_A_B_global_surface_distance')
            pair.update(status='reviewed', passed_checked_scope=True, entire_observation=semantic, arrays=arrays,
                        equal_distance=True, both_witnesses_independently_legal=True,
                        same_particular_equal_distance_pair_required=False)
        except Exception as error:
            pair.update(status='failed', errors=[{'type': type(error).__name__, 'reason': str(error),
                                                  'traceback': traceback.format_exc()}])
        comparisons.append(pair)
    main_passed = sum(by_summary[label]['passed_checked_scope'] for label in MAIN)
    controls_passed = sum(by_summary[label]['passed_checked_scope'] for label in CONTROLS)
    passed = main_passed == 6 and controls_passed == 2 and all(row['passed_checked_scope'] for row in comparisons)
    if run.get('blocker') is not None or run.get('all_eight_transport_closed') is not True:
        errors.append({'reason': 'formal_dispatch_or_transport_incomplete', 'blocker': run.get('blocker')})
        passed = False
    sources = ['quality_saved_r2.py', 'source_contract_r2.py', 'review_qualification_r1.py',
               'witness_residuals.py', 'review_work.py', 'review_task_only.py', 'formal_quality.py']
    return {'schema': 'm5-formal-independent-quality-v1', 'passed_checked_scope': passed, 'errors': errors,
            'main_denominator': 6, 'main_passed': main_passed, 'task_only_denominator': 2,
            'task_only_passed': controls_passed, 'registered_order': SCHEDULE, 'slots': summaries,
            'paired_quality_comparisons': comparisons, 'failed_and_unrun_slots_retained': True,
            'timing_and_cost_rankings_computed': False,
            'frozen_sources': expected_sources,
            'input_pins': [{'path': str(path), 'sha256': ql.sha(path)} for path in (
                root / 'RUN_RESULT.json', root / 'INTENT.json', HERE / 'PLAN.json', HERE / 'REQUESTS.json',
                HERE / 'STATE_REQUESTS.json', builds['A'], builds['B'])],
            'checker_pins': [{'path': str(HERE / filename), 'sha256': ql.sha(HERE / filename)} for filename in sources],
            'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--B-binding', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.root, args.B_binding)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    ql = load('quality_saved_r2.py', '_m5_formal_report_hash')
    print(json.dumps({'passed_checked_scope': report['passed_checked_scope'], 'main_passed': report['main_passed'],
                      'task_only_passed': report['task_only_passed'], 'output_sha256': ql.sha(args.output)}))
