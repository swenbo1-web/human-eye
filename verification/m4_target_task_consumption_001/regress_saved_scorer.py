"""Exercise saved-only scorer boundaries without rewriting sealed quality."""

import argparse
import copy
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FORMAL = Path('D:/he_m4_target_consume_001/formal')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    scorer = load(HERE / 'score_saved_R1.py', '_regression_derived_saved_scorer')
    saved = load(HERE / 'saved_evidence.py', '_regression_saved_evidence')
    claims = load(HERE / 'grade_claims.py', '_regression_claims')
    quoted = load(HERE / 'quoted_sources.py', '_regression_quotes')
    truth = read(HERE / 'admin/TRUTH.json')
    normalized = read(HERE / 'admin/NORMALIZED.json')
    run = read(FORMAL.parent / 'RUN_RESULT.json')
    original_read = scorer.read
    actual_evaluate = saved.evaluate_slot
    cache = {}

    def cached_evidence(path, current_truth):
        key = str(path)
        if key not in cache:
            cache[key] = actual_evaluate(path, current_truth)
        base = cache[key]
        return dict(base, aliases=dict(base['aliases']),
                    current_source_references=list(base['current_source_references']))

    saved.evaluate_slot = cached_evidence
    cases = []

    def grade(slot, row):
        outer = next(item for item in run['records'] if item['slot_id'] == slot)
        return scorer.grade_slot(slot, row, outer, FORMAL, truth, claims, saved, quoted)

    for slot in ('N1', 'P1', 'N3', 'P3'):
        row = next(item for item in normalized['slots'] if item['slot_id'] == slot)
        result = grade(slot, copy.deepcopy(row))
        assert result['final_quality_passed'] is True
        cases.append({'case': 'actual_current_positive_' + slot, 'passed': True,
                      'source_quoted_product_adoption': result['adoption']['actual_product_facts_adopted'],
                      'scope': 'Saved-source regression, not another model task or replacement sample.'})

    def reject_claim(name, slot, mutate):
        row = copy.deepcopy(next(item for item in normalized['slots'] if item['slot_id'] == slot))
        mutate(row)
        try:
            result = grade(slot, row)
        except (ValueError, TypeError, KeyError, IndexError) as error:
            cases.append({'case': name, 'passed': True, 'rejection': type(error).__name__ + ':' + str(error)})
        else:
            assert result['final_quality_passed'] is False, name
            cases.append({'case': name, 'passed': True, 'failed_checks': result['errors']})

    reject_claim('native_label_reused_for_different_source_regions', 'N1',
                 lambda row: row['answer']['regions'][1]['identity'].update(roi_id='R0'))
    reject_claim('product_ROI_alias_not_registered_current_source', 'P1',
                 lambda row: row['answer']['regions'][0]['identity'].update(roi_id='unregistered-product-alias'))
    reject_claim('wrong_source_face_set', 'P1',
                 lambda row: row['answer']['regions'][0]['identity'].update(source_triangle_index_ranges=[[511, 513]]))
    reject_claim('foreign_frame_witness', 'P1',
                 lambda row: row['answer']['regions'][0]['complete_witness'].update(frame_ref='other-slot-frame'))
    reject_claim('partial_readable_region_cannot_be_complete_witness', 'P1',
                 lambda row: row['answer']['regions'][1].update(complete_readable=True,
                    complete_witness=copy.deepcopy(row['answer']['regions'][0]['complete_witness'])))
    reject_claim('missing_reason_not_filled_by_truth', 'N1',
                 lambda row: row['answer']['regions'][0].update(unknown_reason=None))
    reject_claim('missing_source_reference_not_filled', 'P1',
                 lambda row: row['answer']['regions'][0].update(source_references=[]))
    reject_claim('wrong_extra_claim_rejected', 'P1',
                 lambda row: row.update(extra_assertion_errors=['synthetic wrong additional assertion']))
    malformed = copy.deepcopy(next(item for item in normalized['slots'] if item['slot_id'] == 'P1'))
    malformed['answer']['regions'][0]['unit_normal_world'] = []
    result = grade('P1', malformed)
    assert result['final_quality_passed'] is False and result['adoption']['actual_product_facts_adopted'] is True
    cases.append({'case': 'task_quality_failure_preserves_observed_product_adoption', 'passed': True})

    run_path = FORMAL.parent / 'RUN_RESULT.json'
    normalized_path = HERE / 'admin/NORMALIZED.json'

    def reject_run(name, mutate, consumer_override=None):
        fixture = copy.deepcopy(run)
        mutate(fixture)
        touched = []

        def overlay(path):
            absolute = Path(path).resolve()
            if absolute == run_path.resolve():
                touched.append(str(absolute))
                return fixture
            value = original_read(path)
            if consumer_override is not None and absolute == (FORMAL / 'N1/consumer/CONSUMER.json').resolve():
                value = copy.deepcopy(value)
                consumer_override(value)
            return value

        scorer.read = overlay
        destination = HERE / 'admin' / ('UNEXPECTED_REGRESSION_' + name + '.json')
        assert not destination.exists()
        try:
            scorer.score(argparse.Namespace(runtime_root=FORMAL, normalized=normalized_path, output=destination))
        except ValueError as error:
            assert touched == [str(run_path.resolve())]
            assert not destination.exists()
            cases.append({'case': name, 'passed': True, 'rejection': str(error),
                          'actual_batch_root_producer_path_checked': True})
        else:
            raise AssertionError('bad producer accepted:' + name)
        finally:
            scorer.read = original_read

    reject_run('extra_seventh_record', lambda value: value['records'].append(copy.deepcopy(value['records'][-1])))
    reject_run('duplicate_slot', lambda value: value['records'][1].update(slot_id='N1', group='N'))
    reject_run('wrong_group', lambda value: value['records'][0].update(group='P'))
    reject_run('outer_retry_not_zero', lambda value: value.update(outer_retries=1))
    reject_run('incorrect_actual_consumer_count', lambda value: value.update(actual_consumers=5))
    reject_run('PID_without_actual_CLI_launch_not_counted', lambda value: None,
               lambda value: value['image_delivery'].update(CLI_process_launched=False))
    reject_run('launch_flag_without_PID_not_counted', lambda value: None,
               lambda value: value.update(consumer_pid=None))
    protected = ('admin/NORMALIZED.json', 'admin/SEMANTIC_REVIEW.json', 'QUALITY.json')
    before = {name: sha(HERE / name) for name in protected}
    assert before['admin/NORMALIZED.json'] == 'c109d1bad22a7472a9a52e031a0223dace8d0bcd9911ede2a6bc9fb3ae96ea92'
    assert before['QUALITY.json'] == '1a4f787bf86c90659be0f77d8becfac80f8598141e9e6852428eaddd3048c104'
    original_contract = read(HERE / 'admin/SCORING_CONTRACT.json')
    assert all(sha(path) == digest for path, digest in original_contract['files_sha256'].items())
    diff = ''.join(difflib.unified_diff((HERE / 'score_saved.py').read_text(encoding='utf-8').splitlines(keepends=True),
                                      (HERE / 'score_saved_R1.py').read_text(encoding='utf-8').splitlines(keepends=True),
                                      fromfile='frozen/score_saved.py', tofile='derived/score_saved_R1.py'))
    diff_path = HERE / 'admin/SCORER_R1.diff'
    with diff_path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(diff)
    report = {'schema': 'target-task-consumption-derived-scorer-regression-v1', 'passed_checked_scope': True,
              'cases': cases, 'case_count': len(cases),
              'original_scorer_sha256': sha(HERE / 'score_saved.py'),
              'derived_scorer_sha256': sha(HERE / 'score_saved_R1.py'), 'derived_diff_sha256': sha(diff_path),
              'sealed_protected_file_sha256': before, 'all_original_33_source_pins_unchanged': True,
              'fixture_scope': 'In-memory mutations of actual saved records. No original final, normalized evidence, review, quality or runtime record is written.',
              'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0,
              'source_sha256': sha(Path(__file__))}
    with (HERE / 'admin/SCORER_R1_REGRESSION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    supplement = {'schema': 'target-task-consumption-scorer-derivation-supplement-v1',
        'original_derivation_record_sha256': sha(HERE / 'admin/SCORER_DERIVATION_R1.json'),
        'original_scorer_sha256': report['original_scorer_sha256'], 'derived_scorer_sha256': report['derived_scorer_sha256'],
        'diff_path': str(diff_path), 'diff_sha256': sha(diff_path),
        'regression_path': str(HERE / 'admin/SCORER_R1_REGRESSION.json'),
        'regression_sha256': sha(HERE / 'admin/SCORER_R1_REGRESSION.json'),
        'task_threshold_and_input_changes': False, 'sealed_quality_changed': False,
        'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}
    with (HERE / 'admin/SCORER_DERIVATION_R1_SUPPLEMENT.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(supplement, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'regression_cases': len(cases), 'sealed_files_unchanged': True}))


if __name__ == '__main__':
    main()
