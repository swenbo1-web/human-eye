"""Run the frozen real-byte regression and artificial offline control matrix."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('m4_complete_witness_consumption_001')
RUNTIME = Path('D:/he_complete_witness_001')
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def snapshot(roots):
    return {str(path.resolve()): sha(path) for root in roots
            for path in sorted(root.rglob('*')) if path.is_file()}


def install_offline_guard(output):
    blocked = []
    product = Path('D:/he_view_reuse_001/product').resolve()

    def audit(event, arguments):
        reason = None
        if event in ('subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind', 'socket.getaddrinfo'):
            reason = 'offline_control_disallows_process_or_network'
        elif event == 'exec':
            filename = Path(arguments[0].co_filename)
            if filename.is_absolute() and filename.resolve().is_relative_to(product):
                reason = 'offline_control_disallows_product_execution'
        elif event == 'open' and isinstance(arguments[0], (str, bytes, os.PathLike)):
            mode, flags = arguments[1], arguments[2]
            writing = isinstance(mode, str) and any(value in mode for value in 'wax+')
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not Path(os.fsdecode(arguments[0])).resolve().is_relative_to(output):
                reason = 'offline_control_writes_only_new_result_directory'
        if reason:
            blocked.append({'event': event, 'reason': reason})
            raise PermissionError(reason)

    sys.addaudithook(audit)
    return blocked


def apply_mutation(values, mutation):
    target = values[mutation['target']]
    path = mutation['path']
    for key in path[:-1]:
        target = target[key]
    key = path[-1]
    if mutation['operation'] == 'delete':
        del target[key]
    elif mutation['operation'] == 'set':
        target[key] = copy.deepcopy(mutation['value'])
    elif mutation['operation'] == 'duplicate_first':
        target[key].append(copy.deepcopy(target[key][0]))
    else:
        raise ValueError('unregistered_control_mutation')


def full_score(scorer, case, values, folder, normalized_path):
    original_load = scorer.load
    paths = {str((RUNTIME / 'formal/RUN_RESULT.json').resolve()): 'run',
             str((RUNTIME / 'formal/P1/c/CONSUMER.json').resolve()): 'consumer',
             str(normalized_path.resolve()): 'normalized'}
    intercepted = []

    def load_with_read_overlay(name, path):
        module = original_load(name, path)
        if Path(path).resolve() == (OLD / 'saved_evidence.py').resolve():
            original_read = module.oracle.read

            def controlled_read(input_path):
                target = paths.get(str(Path(input_path).resolve()))
                if target is not None:
                    intercepted.append({'path': str(Path(input_path).resolve()), 'target': target})
                    return copy.deepcopy(values[target])
                return original_read(input_path)

            module.oracle.read = controlled_read
        return module

    stdout, stderr = io.StringIO(), io.StringIO()
    scorer.load = load_with_read_overlay
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = scorer.score(SimpleNamespace(normalized=normalized_path,
                runtime_root=RUNTIME, output=folder / 'FULL_SCORE.json'))
    finally:
        scorer.load = original_load
        (folder / 'SCORER_STDOUT.txt').write_text(stdout.getvalue(), encoding='utf-8')
        (folder / 'SCORER_STDERR.txt').write_text(stderr.getvalue(), encoding='utf-8')
        save(folder / 'READ_OVERLAY.json', {'artificial_control': case['kind'] != 'positive',
            'read_intercepts': intercepted,
            'scope': 'Only RUN_RESULT, CONSUMER and NORMALIZED JSON reads are replaced in memory. '
                     'Source files, hashes, helpers, images, arrays and all other reads remain original.'})
    return exit_code, read(folder / 'FULL_SCORE.json')


def verify_case(case, terminal, result, exit_code):
    expected_fields = case['expected_terminal_failed_fields']
    assert terminal['failed_fields'] == expected_fields, 'precise_terminal_rejection_fields'
    assert terminal['passed'] is (not expected_fields), 'terminal_pass_boolean'
    assert result['terminal_binding'] == terminal, 'actual_fullscore_uses_same_reader_result'
    if case['kind'] == 'positive':
        assert exit_code == 0 and result['final_quality_passed'] is True, 'real_full_content_positive'
        assert result['errors'] == [], 'positive_has_no_content_errors'
        assert result['product_current_facts_correct'] is True, 'positive_product_facts'
        assert result['direct_product_adoption'] is False, 'native_verification_stays_non_direct'
        assert result['correct_with_supplement_or_recomputation'] is True, 'actual_native_supplement_retained'
    elif case['kind'] == 'terminal':
        assert exit_code == 1 and result['final_quality_passed'] is False, 'terminal_rejected_in_fullscore'
        assert result['status'] == 'terminal_binding_rejected', 'terminal_rejection_stage'
        assert result['errors'] == expected_fields, 'no_unrelated_terminal_error_substitute'
    else:
        assert exit_code == 1 and result['final_quality_passed'] is False, 'content_negative_rejected'
        assert set(result['errors']) == set(case['expected_content_errors']), 'precise_content_error_set'
        assert result['product_current_facts_correct'] is True, 'negative_keeps_actual_product_evidence'
        measured = result['independent_actual_evidence']
        if case['id'] == 'W01_actual_partial_readable':
            actual = measured['target_first_readable']
            witness = case['mutations'][0]['value']
            assert actual['complete'] is False and actual['readable'] is True, 'partial_readable_independent_precondition'
            assert actual['view_name'] == witness['view'] and actual['image_ref'] == witness['ref'], 'actual_partial_frame'
            assert actual['surface_pixels'] == witness['surface_pixels'], 'partial_actual_surface_count'
            assert actual['boundary_pixels'] == witness['boundary_pixels'], 'partial_actual_boundary_count'
            assert actual['surface_pixels'] >= 16 and actual['boundary_pixels'] >= 4, 'partial_exceeds_readability_threshold'
        else:
            unknown_ref = case['mutations'][0]['value']
            assert unknown_ref not in {row['image_ref'] for row in measured['target_ordered_rows']}, 'nonexistent_reference_precondition'


def exclusive_output_check(scorer, originals, normalized_path, folder):
    folder.mkdir()
    existing = folder / 'FULL_SCORE.json'
    save(existing, {'sentinel': 'existing-new-namespace-output-control'})
    before = sha(existing)
    result = {'schema': 'score-fix-exclusive-output-control-v1', 'passed': False,
              'existing_output_path': str(existing), 'before_sha256': before,
              'score_invocations': 1, 'separate_from_21_case_denominator': True}
    try:
        full_score(scorer, {'kind': 'positive'}, copy.deepcopy(originals), folder, normalized_path)
        result['error'] = {'type': 'AssertionError', 'message': 'existing_output_was_not_rejected'}
    except FileExistsError as error:
        result['observed_error'] = {'type': type(error).__name__, 'message': str(error), 'filename': error.filename}
        result['passed'] = Path(error.filename).resolve() == existing.resolve() and sha(existing) == before
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    result['after_sha256'] = sha(existing)
    save(folder / 'RESULT.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--positive-score', type=Path, default=HERE / 'SUPPLEMENTARY_QUALITY.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output == HERE:
        raise ValueError('new_control_output_directory_required')
    registry_path = HERE / 'REGISTRY.json'
    registry = read(registry_path)
    for specification in registry['source_pins']:
        assert sha(specification['path']) == specification['sha256'], 'frozen_control_source_changed'
    prior_positive = read(args.positive_score)
    assert prior_positive['final_quality_passed'] is True, 'root_first_fullscore_must_finish_successfully'
    assert prior_positive['terminal_binding']['passed'] is True, 'root_first_terminal_read_must_pass'
    assert prior_positive['scorer_identity']['source_sha256'] == sha(HERE / 'score_saved.py'), 'root_positive_same_derived_source'
    output.mkdir(parents=True, exist_ok=False)
    protected_roots = [OLD, RUNTIME]
    protected_before = snapshot(protected_roots)
    save(output / 'ORIGINALS_BEFORE.json', protected_before)
    save(output / 'START.json', {'registry_sha256': sha(registry_path),
        'root_positive_path': str(args.positive_score.resolve()), 'root_positive_sha256': sha(args.positive_score),
        'logical_case_denominator': len(registry['cases']),
        'source_kind': 'One original model run, plus artificial offline control mutations.'})
    blocked = install_offline_guard(output)
    scorer = load_module('_score_fix_regression_scorer', HERE / 'score_saved.py')
    reader = load_module('_score_fix_regression_terminal', HERE / 'terminal_reader.py')
    normalized_path = OLD / 'admin/NORMALIZED.json'
    originals = {'run': read(HERE / 'fixtures/RUN_RESULT.json'),
                 'consumer': read(HERE / 'fixtures/CONSUMER.json'),
                 'normalized': read(normalized_path)}
    provenance = read(HERE / 'fixtures/PROVENANCE.json')
    for row in provenance['files']:
        assert sha(row['fixture_path']) == sha(row['source_path']) == row['sha256'], 'fixture_must_be_original_producer_bytes'
    outcomes = []
    terminal_reader_calls = 0
    fullscore_calls = 0
    for case in registry['cases']:
        folder = output / case['id']
        folder.mkdir()
        save(folder / 'CONTROL.json', case)
        values = copy.deepcopy(originals)
        for mutation in case['mutations']:
            apply_mutation(values, mutation)
        outcome = {'id': case['id'], 'kind': case['kind'], 'passed': False}
        try:
            terminal_reader_calls += 1
            terminal = reader.terminal_binding(values['run'], values['consumer'])
            save(folder / 'TERMINAL.json', terminal)
            fullscore_calls += 1
            exit_code, scored = full_score(scorer, case, values, folder, normalized_path)
            verify_case(case, terminal, scored, exit_code)
            outcome.update(passed=True, scorer_exit_code=exit_code,
                observed_terminal_failed_fields=terminal['failed_fields'],
                observed_content_errors=scored['errors'])
        except BaseException as error:
            outcome['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
        save(folder / 'RESULT.json', outcome)
        outcomes.append(outcome)
        if not outcome['passed']:
            break
    output_protection = {'executed': False, 'passed': None, 'score_invocations': 0}
    if len(outcomes) == len(registry['cases']) and all(row['passed'] for row in outcomes):
        output_protection = exclusive_output_check(scorer, originals, normalized_path,
                                                   output / 'AUX_exclusive_output')
        output_protection['executed'] = True
    protected_after = snapshot(protected_roots)
    originals_unchanged = protected_before == protected_after
    save(output / 'ORIGINALS_AFTER.json', protected_after)
    result = {'schema': 'complete-witness-offline-regression-v1',
        'passed': len(outcomes) == len(registry['cases']) and all(row['passed'] for row in outcomes)
                  and output_protection['passed'] is True and originals_unchanged and not blocked,
        'logical_case_denominator': len(registry['cases']), 'logical_cases_run': len(outcomes),
        'passed_cases': sum(row['passed'] for row in outcomes), 'terminal_reader_calls': terminal_reader_calls,
        'fullscore_calls': fullscore_calls, 'root_independent_positive_calls': 1,
        'output_protection_auxiliary': output_protection,
        'total_harness_score_invocations': fullscore_calls + output_protection['score_invocations'],
        'unrun_cases': [row['id'] for row in registry['cases'][len(outcomes):]], 'outcomes': outcomes,
        'original_files_checked_before_after': len(protected_before), 'originals_unchanged': originals_unchanged,
        'blocked_side_effects': blocked, 'new_model_product_Blender_raster_network_calls': 0,
        'sample_scope': 'Offline regression and artificial controls over the same one preserved model sample. '
                        'Historical first automatic quality remains failed0/1 and retains its original seal.'}
    save(output / 'RESULT.json', result)
    print(json.dumps({'passed': result['passed'], 'passed_cases': result['passed_cases'],
                      'denominator': result['logical_case_denominator'], 'result': str(output / 'RESULT.json')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
