"""One-slot adapter over the unchanged region-localization quality methods.

The only method adaptation is a private BATCH global for the new manifest.
The original six-slot main is never invoked. This adapter performs no model,
renderer, product, or process action.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ORIGINAL = ROOT/'verification/m4_region_localization_consumption_001/admin'
SCORER_SHA = '274a20096cebbf2a7e4f93e5975321b44925465cdb41c66efdad007fc22f8c10'
RUNTIME = Path('D:/he_explicit_001/formal')
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def assert_predicates_match(original_source):
    def expressions(source, function):
        tree = ast.parse(source)
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == function)
        result = {}
        for assignment in ast.walk(node):
            if not isinstance(assignment, ast.Assign):
                continue
            for target in assignment.targets:
                if isinstance(target, ast.Name) and target.id == 'lifecycle':
                    result['lifecycle'] = ast.dump(assignment.value, include_attributes=False)
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == 'score' and isinstance(target.slice, ast.Constant)
                        and target.slice.value == 'fully_qualified'):
                    result['fully_qualified'] = ast.dump(assignment.value, include_attributes=False)
        return result
    expected = expressions(original_source, 'quality')
    actual = expressions(raw(__file__).decode('utf8'), 'evaluate')
    if expected != actual or set(actual) != {'lifecycle', 'fully_qualified'}:
        raise ValueError('original_quality_predicate_changed')


def original_grader():
    contract = read(HERE/'SCORING_CONTRACT.json')
    for path, wanted in contract['files_sha256'].items():
        if hashlib.sha256(raw(path)).hexdigest() != wanted:
            raise ValueError('scoring_contract_source_changed:'+path)
    old_rules = read(ORIGINAL/'FROZEN_SCORING.json')
    for path, wanted in old_rules['files_sha256'].items():
        if hashlib.sha256(raw(path)).hexdigest() != wanted:
            raise ValueError('original_frozen_dependency_changed:'+path)
    path = ORIGINAL/'score_quality.py'
    source = raw(path)
    if hashlib.sha256(source).hexdigest() != SCORER_SHA:
        raise ValueError('original_scoring_source_changed')
    assert_predicates_match(source.decode('utf8'))
    specification = importlib.util.spec_from_file_location('_explicit_frozen_quality', path)
    original = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(original)
    method = original.Grader.frames
    scoped = types.FunctionType(method.__code__, dict(method.__globals__, BATCH=BATCH),
                                method.__name__, method.__defaults__, method.__closure__)
    scoped.__kwdefaults__ = method.__kwdefaults__

    class Grader(original.Grader):
        frames = scoped

    names = ('__init__', 'identity', 'artifact', 'bind_sources', 'support', 'tool_binding',
             'frames', 'reason_valid', 'panels', 'unsupported', 'questions')
    same_code = {name: getattr(Grader, name).__code__ is getattr(original.Grader, name).__code__ for name in names}
    if not all(same_code.values()) or scoped.__globals__['BATCH'] != BATCH:
        raise ValueError('original_grader_code_object_binding')
    truth = original.read(ORIGINAL/'TRUTH.json')
    return original, Grader(truth), same_code


def evaluate(grader, row, outer, runtime_root):
    score = {'slot_id': 'P1', 'execution_state': outer['execution_state'],
             'fully_qualified': False, 'evidence_errors': []}
    if outer['execution_state'] == 'not_run':
        score['reason'] = 'not_run'
        return score
    try:
        owner, consumer = runtime_root/'P1/o', runtime_root/'P1/c'
        answer = raw(consumer/'PUBLIC_FINAL.txt')
        if hashlib.sha256(answer).hexdigest() != row['raw_answer_sha256']:
            raise ValueError('normalized_final_SHA')
        if Path(row['raw_answer_path']).resolve() != (consumer/'PUBLIC_FINAL.txt').resolve():
            raise ValueError('normalized_final_original_path')
        text = answer.decode('utf8')
        record, tools, delivered, tool_count = grader.tool_binding(owner, consumer)
        grader.bind_sources(row, owner, consumer, text, tools)
        evidence, render_count = grader.frames(owner, outer, delivered)
        lifecycle = bool(outer['execution_state'] == 'completed' and outer['outer_valid_completion']
            and outer['consumer_safe_to_continue'] and not outer['common_image_faults']
            and outer['runtime_binding']['confirmed'] and outer['runtime_exit']['confirmed']
            and outer['owner_process_cleanup']['confirmed'] and outer['consumer_process_cleanup']['confirmed']
            and record['safe_to_continue'] and tool_count <= 12 and render_count <= 6)
        panels = grader.panels(row.get('panels', []), evidence)
        questions = grader.questions(row.get('questions', {}), evidence)
        remainder = grader.unsupported(row.get('unsupported', []))
        scope = row.get('finite_pool_scope_correct') is True and row.get('global_invisibility_overclaim') is False
        score.update(execution_evidence_valid=lifecycle, coverage=panels, questions=questions,
                     unsupported_remainder_passed=remainder, finite_pool_scope_passed=scope,
                     raw_answer_sha256=row['raw_answer_sha256'], frame_count=len(evidence),
                     render_attempts=render_count, tool_attempts=tool_count,
                     image_refs_delivered=sum(frame['image_delivered'] for frame in evidence.values()))
        score['fully_qualified'] = bool(lifecycle and panels['passed'] and remainder and scope
                                        and all(value['passed'] for value in questions.values()))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        score['evidence_errors'].append({'type': type(error).__name__, 'message': str(error)})
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, default=RUNTIME)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_root.resolve() != RUNTIME.resolve():
        raise ValueError('single_registered_runtime_required')
    original, grader, same_code = original_grader()
    normalized = read(args.normalized)
    rows = normalized['slots']
    if (normalized['schema'] != 'region-localization-normalized-v1' or len(rows) != 1
            or rows[0]['slot_id'] != 'P1'):
        raise ValueError('exact_one_P1_normalized_slot')
    records = read(args.runtime_root/'RUN_RESULT.json')['records']
    if len(records) != 1 or records[0]['slot'] != 'P1' or records[0]['group'] != 'P':
        raise ValueError('exact_one_P1_runtime_slot')
    score = evaluate(grader, rows[0], records[0], args.runtime_root)
    INPUTS.update(original.INPUTS)
    result = {'schema': 'explicit-observation-single-slot-quality-v1', 'slots': [score],
        'denominator': 1, 'task_quality_complete': score['fully_qualified'],
        'cost_analysis_performed': False, 'minimum_view_count_graded': False,
        'normalization_entailment_review_required': True, 'original_grader_code_objects': same_code,
        'original_predicates_AST_equal': True, 'private_globals_adaptation': {'frames.BATCH': str(BATCH)},
        'three_layer_diagnostic_qualification': 'Separately source-audited in the consumption provenance record.',
        'inputs_sha256': dict(sorted(INPUTS.items()))}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps({'denominator': 1, 'task_quality_complete': result['task_quality_complete'],
                      'cost_analysis_performed': False}))


if __name__ == '__main__':
    main()
