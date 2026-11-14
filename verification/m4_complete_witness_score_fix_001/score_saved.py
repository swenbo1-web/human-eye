"""Score one source-quoted final against current independent saved evidence."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


NEW_HERE = Path(__file__).resolve().parent
HERE = NEW_HERE.with_name('m4_complete_witness_consumption_001')
VARIANT = 'm4-complete-witness-score-fix-001-v1'
ORIGINAL_SCORER_SHA256 = 'fd6a1c455d40407e8e3b1ad8f2711689f4419c6ce187a9e3083467edcd0d4074'


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def scorer_identity():
    original = HERE / 'score_saved.py'
    reader = NEW_HERE / 'terminal_reader.py'
    return {
        'variant': VARIANT,
        'source_path': str(Path(__file__).resolve()),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_source_path': str(original),
        'original_source_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'original_expected_sha256': ORIGINAL_SCORER_SHA256,
        'terminal_reader_sha256': hashlib.sha256(reader.read_bytes()).hexdigest(),
        'semantic_dependencies': str(HERE),
    }


def require_new_output(path):
    if not Path(path).resolve().is_relative_to(NEW_HERE):
        raise ValueError('derived_output_must_stay_in_new_namespace')


def reject_terminal(arguments, binding):
    require_new_output(arguments.output)
    result = {
        'schema': 'complete-witness-formal-quality-adoption-v1',
        'denominator': 1,
        'final_quality_passed': False,
        'direct_product_adoption': None,
        'status': 'terminal_binding_rejected',
        'terminal_binding': binding,
        'errors': list(binding['failed_fields']),
        'scorer_identity': scorer_identity(),
        'cost_analysis_performed': False,
        'new_product_raster_model_calls': 0,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'quality': False, 'status': result['status'], 'path': str(arguments.output)}))
    return 1


def score(arguments):
    require_new_output(arguments.output)
    terminal = load('_derived_complete_witness_terminal', NEW_HERE / 'terminal_reader.py')
    saved = load('_formal_witness_saved_evidence', HERE / 'saved_evidence.py')
    oracle = saved.oracle
    truth = oracle.read(HERE / 'admin/TRUTH.json')
    normalized = oracle.read(arguments.normalized)
    owner = arguments.runtime_root / 'formal/P1/o'
    consumer = oracle.read(arguments.runtime_root / 'formal/P1/c/CONSUMER.json')
    run_result = oracle.read(arguments.runtime_root / 'formal/RUN_RESULT.json')
    terminal_result = terminal.terminal_binding(run_result, consumer)
    if not terminal_result['passed']:
        return reject_terminal(arguments, terminal_result)
    outer = run_result['records'][0]
    errors = []
    checks = []
    adoption_errors = []

    def check(name, value):
        checks.append({'check': name, 'passed': bool(value)})
        if not value:
            errors.append(name)

    source_text = {}
    source_hashes = {}
    source_kinds = {}
    final_text = consumer['final']
    for source in normalized['sources']:
        path = Path(source['path']).resolve()
        check('source_is_current:' + source['id'], path.is_relative_to(arguments.runtime_root / 'formal/P1'))
        check('source_hash:' + source['id'], oracle.sha(path) == source['sha256'])
        raw = path.read_bytes().decode('utf-8')
        text = [raw]
        if source['kind'] == 'tool_result':
            text.extend(block.get('text', '') for block in oracle.read(path)['result']['content'])
        elif source['kind'] == 'tool_request':
            request_arguments = oracle.read(path)['params']['arguments']
            if type(request_arguments.get('code')) is str:
                text.append(request_arguments['code'])
        source_text[source['id']] = text
        source_kinds[source['id']] = source['kind']
        source_hashes[str(path)] = source['sha256']
        if source['kind'] != 'final' and source['kind'] != 'tool_request':
            reference = source.get('final_reference_excerpt')
            check('actual_final_source_reference:' + source['id'],
                  type(reference) is str and bool(reference) and reference in final_text)
        if source['kind'] == 'final':
            check('final_source_is_actual_final', raw == final_text)

    def support_valid(items, *, allow_request=False):
        if isinstance(items, dict):
            items = [items]
        return bool(items) and all(
            item['source_id'] in source_text
            and (allow_request or source_kinds[item['source_id']] != 'tool_request')
            and type(item['excerpt']) is str and item['excerpt']
            and any(item['excerpt'] in text for text in source_text[item['source_id']])
            for item in items)

    check('normalization_schema', normalized['schema'] == 'complete-witness-normalized-v1')
    check('one_slot_P1', normalized['slot_id'] == 'P1' and outer['slot'] == 'P1')
    answer_path = Path(normalized['raw_answer_path']).resolve()
    check('current_final_path', answer_path.is_relative_to(arguments.runtime_root / 'formal/P1/c'))
    check('actual_final_bytes', oracle.sha(answer_path) == normalized['raw_answer_sha256']
          and answer_path.read_bytes().decode('utf-8') == consumer['final'])
    check('valid_final_and_terminal_process', terminal_result['passed'])
    measured = saved.evaluate(owner, truth)
    check('product_facts_independently_correct', measured['product_errors'] == [])
    bound_truth = measured['bound_truth']
    truth_by_roi = {region['roi_id']: region for region in bound_truth['regions']}
    by_object = {region['object_name']: region['roi_id'] for region in bound_truth['regions']}
    by_ref = dict(measured['by_ref'])
    observations = oracle.read(owner / 'OBSERVATIONS.json')
    plan = oracle.read(HERE / 'PLAN.json')
    manifest = oracle.read(plan['inputs']['input_manifest'])
    binding = oracle.read(manifest['product_binding']['path'])
    cameras = oracle.read(manifest['cameras']['path'])
    native = load('_formal_witness_native_reader', HERE / 'native_evidence.py')
    native_frame_count = 0
    for frame in observations['frames']:
        if frame['ref'] in by_ref:
            continue
        if frame['origin'] != 'native' or not Path(frame['NPZ']).resolve().is_relative_to(owner):
            raise ValueError('additional_frame_current_source')
        by_ref[frame['ref']] = native.measure(frame, bound_truth, binding['dependency_root'], oracle,
                                             {view['name']: view for view in cameras['views']})
        native_frame_count += 1

    def identity(value):
        matches = []
        if 'roi_id' in value:
            matches.append(value['roi_id'])
        if 'object_name' in value:
            matches.append(by_object[value['object_name']])
        if not matches or any(roi not in truth_by_roi for roi in matches) or len(set(matches)) != 1:
            raise ValueError('claim_identity_is_not_current_source')
        return matches[0]

    def witness_valid(roi, witness):
        frame = by_ref.get(witness['ref'])
        if frame is None or frame['view_name'] != witness['view']:
            return False
        row = next(value for value in frame['rows'] if value['roi_id'] == roi)
        valid = (row['complete_readable']
                 and row['surface_pixels'] == witness['surface_pixels']
                 and row['boundary_pixels'] == witness['boundary_pixels'])
        if 'pixel_xy' in witness:
            x, y = witness['pixel_xy']
            valid = (valid and type(x) is int and type(y) is int and 0 <= x < 512 and 0 <= y < 512
                     and frame['raw_region_by_pixel'][y*512+x] == truth_by_roi[roi]['object_index'])
        return valid

    panels = normalized['surfaces']
    identities = [identity(panel['identity']) for panel in panels]
    check('complete_source_coverage_bijection', len(identities) == len(truth_by_roi)
          and len(set(identities)) == len(identities) and set(identities) == set(truth_by_roi))
    check('explicit_full_coverage_citation', support_valid(normalized['coverage_support']))
    for panel, roi in zip(panels, identities):
        check('quoted_surface:' + roi, support_valid(panel['support']))
        # The one qualification demonstrates actual complete-readable views for
        # both fixed supported surfaces. Formal evidence must be current.
        check('full_current_complete_surface:' + roi,
              panel['status'] == 'covered' and witness_valid(roi, panel['witness']))
    check('unsupported_scope', normalized['unsupported'] == [] and support_valid(normalized['unsupported_support']))
    remaining = normalized['remaining']
    remaining_ids = [identity(row['identity']) for row in remaining]
    check('remaining_declaration', len(set(remaining_ids)) == len(remaining_ids)
          and set(remaining_ids) == set(measured['independent_remaining_roi_ids']))
    check('remaining_declaration_support', support_valid(normalized['remaining_support']))
    check('no_unretracted_final_contradiction', normalized['contradictions'] == [])
    check('finite_pool_scope', normalized['finite_pool_only'] is True
          and support_valid(normalized['finite_pool_support']))
    target = normalized['target']
    target_roi = identity(target['identity'])
    check('target_source', target_roi == bound_truth['target_roi_id'])
    check('target_world_center', target['center_world_m'] == truth_by_roi[target_roi]['center_world_m'])
    check('target_world_center_support', support_valid(target['center_support']))
    check('target_owned_pixel_is_reported', 'pixel_xy' in target['witness'])
    check('target_actual_complete_view', witness_valid(target_roi, target['witness']))
    check('target_quoted_claim', support_valid(target['support']))
    public_witness = measured['public_complete_witnesses'].get(target_roi)
    index = target['complete_witness_pixel_index']
    check('actual_public_complete_witness_index', type(index) is int and public_witness is not None
          and index == public_witness['pixel_index'])
    check('index_source_quote', support_valid(target['index_support']))
    selected_public_witness = bool(public_witness
        and target['witness']['view'] == public_witness['view_name']
        and target['witness']['ref'] == public_witness['image_ref'])
    check('target_index_frame_consistency', selected_public_witness
          or target.get('index_describes_product_witness_separately') is True)
    extra = normalized['extra_tool_classification']
    expected_attempts = list(range(2, len(consumer['tool_calls']) + 1))
    if [item['attempt'] for item in extra] != expected_attempts:
        adoption_errors.append('all_extra_tools_must_be_classified')
    for item in extra:
        if not support_valid(item['support'], allow_request=True):
            adoption_errors.append('extra_tool_source_quote:' + str(item['attempt']))
    categories = [item['category'] for item in extra]
    direct_categories = {'public_json_query', 'cached_image_read', 'existing_buffer_lookup',
                         'format_artifact', 'cached_product_observation'}
    native_categories = {'raw_source_read', 'native_computation', 'new_native_observation'}
    allowed_categories = direct_categories | native_categories | {'unknown'}
    if native_frame_count and not any(category in native_categories for category in categories):
        adoption_errors.append('actual_native_frames_not_accounted_for_in_classification')
    unknown = bool(adoption_errors) or any(category == 'unknown' or category not in allowed_categories for category in categories)
    fully_correct = not errors
    direct = fully_correct and selected_public_witness and not unknown and all(
        category in direct_categories for category in categories)
    result = {
        'schema': 'complete-witness-formal-quality-adoption-v1',
        'denominator': 1,
        'final_quality_passed': fully_correct,
        'product_current_facts_correct': measured['product_errors'] == [],
        'direct_product_adoption': None if unknown else direct,
        'additional_native_or_unknown_use': categories,
        'actual_additional_native_frames': native_frame_count,
        'correct_with_supplement_or_recomputation': fully_correct and any(category in native_categories for category in categories),
        'adoption_evidence_errors': adoption_errors,
        'checks': checks,
        'errors': errors,
        'independent_actual_evidence': saved.summary(measured),
        'target_selected_public_witness': selected_public_witness,
        'normalization_sha256': oracle.sha(arguments.normalized),
        'truth_sha256': oracle.sha(HERE / 'admin/TRUTH.json'),
        'source_hashes': source_hashes,
        'adoption_review_scope': 'Root classifies each actual extra request by its source-quoted code/data use. Python JSON parsing alone is direct use. Scorer checks provenance but does not infer hidden model reasoning.',
        'cost_analysis_performed': False,
        'new_product_raster_model_calls': 0,
        'reviewer_role': 'Independent geometry/pixel oracle and scoring implementation author; root normalization uses actual final/artifacts, without truth fill.'
    }
    result['scorer_identity'] = scorer_identity()
    result['terminal_binding'] = terminal_result
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'quality': fully_correct, 'direct_adoption': result['direct_product_adoption'],
                      'path': str(arguments.output)}))
    return 0 if fully_correct else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    require_new_output(arguments.output)
    try:
        return score(arguments)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        result = {
            'schema': 'complete-witness-formal-quality-adoption-v1',
            'denominator': 1,
            'final_quality_passed': False,
            'direct_product_adoption': None,
            'status': 'claim_or_saved_evidence_missing_or_invalid',
            'errors': [{'type': type(error).__name__, 'message': str(error)}],
            'cost_analysis_performed': False,
            'new_product_raster_model_calls': 0
        }
        result['scorer_identity'] = scorer_identity()
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        with arguments.output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            stream.write('\n')
        print(json.dumps({'quality': False, 'status': result['status'], 'path': str(arguments.output)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
