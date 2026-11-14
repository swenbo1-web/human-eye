"""Use the frozen six-slot grader with private new-batch input bindings."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ORIGINAL = ROOT/'verification/m4_region_localization_consumption_001/admin'
RUNTIME = Path('D:/he_routed_001/formal')
ORIGINAL_SHA = '274a20096cebbf2a7e4f93e5975321b44925465cdb41c66efdad007fc22f8c10'


def read(path):
    return json.loads(Path(path).read_bytes())


def connect():
    contract = read(HERE/'SCORING_CONTRACT.json')
    for name, expected in contract['files_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_scoring_dependency_changed:'+name)
    source = ORIGINAL/'score_quality.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('original_six_slot_grader_changed')
    specification = importlib.util.spec_from_file_location('_routed_original_quality', source)
    original = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(original)
    method = original.Grader.frames
    frames = types.FunctionType(method.__code__, dict(method.__globals__, BATCH=BATCH),
                                method.__name__, method.__defaults__, method.__closure__)
    frames.__kwdefaults__ = method.__kwdefaults__

    class Grader(original.Grader):
        pass

    Grader.frames = frames
    virtual_inputs = {(HERE/'TRUTH.json').resolve(): ORIGINAL/'TRUTH.json',
                      (HERE/'FROZEN_SCORING.json').resolve(): ORIGINAL/'FROZEN_SCORING.json'}

    def scoped_read(path):
        return original.read(virtual_inputs.get(Path(path).resolve(), path))

    grade = types.FunctionType(original.quality.__code__, dict(original.quality.__globals__,
        HERE=HERE, BATCH=BATCH, Grader=Grader, read=scoped_read), original.quality.__name__,
        original.quality.__defaults__, original.quality.__closure__)
    grade.__kwdefaults__ = original.quality.__kwdefaults__
    methods = ('__init__', 'identity', 'artifact', 'bind_sources', 'support', 'tool_binding',
               'frames', 'reason_valid', 'panels', 'unsupported', 'questions')
    checks = {name: getattr(Grader, name).__code__ is getattr(original.Grader, name).__code__ for name in methods}
    checks.update(six_slot_quality_main=grade.__code__ is original.quality.__code__,
                  private_manifest=frames.__globals__['BATCH'] == BATCH,
                  private_quality_grader=grade.__globals__['Grader'] is Grader,
                  original_quality_globals_untouched=original.quality.__globals__['Grader'] is original.Grader)
    if not all(checks.values()):
        raise ValueError('original_scoring_code_object_binding')
    return grade, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, default=RUNTIME)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_root.resolve() != RUNTIME.resolve():
        raise ValueError('registered_six_slot_runtime_required')
    if args.output.exists():
        raise FileExistsError('quality_output_already_published')
    grade, checks = connect()
    grade(args)
    binding = args.output.with_name(args.output.stem+'.binding.json')
    with binding.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(dict(schema='routed-six-slot-scoring-binding-v1', original_scorer_sha256=ORIGINAL_SHA,
            exact_code_object_checks=checks, predicate_AST='Original full quality code object reused without expression edits.',
            private_inputs={'manifest_root': str(BATCH), 'truth_and_rules': str(ORIGINAL)},
            cost_analysis_performed=False), stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
