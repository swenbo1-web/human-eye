"""Compare the live _bounded with its frozen pre-optimization implementation.

Run with an ordinary Python interpreter; no Blender, scene, or timing work is
performed. The expected function, its error class, and MAX_BITS are compiled
from the fixed Git object, never copied from the candidate implementation.
The supported premise is the product's unchanged, positive MAX_BITS=4096.
"""
import ast
from collections import Counter
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
BASELINE = 'd01d49bc0ec82583b24a8faf22e622e6f6ea8c5d'
MODULE_PATH = 'human_eye_plugin/surface_proximity.py'
REGRESSIONS = [
    'verification/test_surface_proximity_001.py',
    'verification/test_surface_proximity_pruning_001.py',
    'verification/closed_solid_read_001/tests/test_closed_solid.py',
    'verification/degenerate_surface_001/tests/test_degenerate_surface.py',
    'verification/exact_rank_001/test_exact_rank.py',
    'verification/zero_witness_reuse_001/tests/test_zero_witness.py',
    'verification/surface_nearest_entry_001/tests/test_surface_nearest_entry.py',
    'verification/nearest_integration_001/tests/test_integration.py',
]


class IntSubclass(int):
    pass


class BitLengthTrapInt(int):
    def bit_length(self):
        raise RuntimeError('subclass_bit_length_must_not_replace_abs')


class AbsTrapInt(int):
    def __abs__(self):
        raise RuntimeError('subclass_abs_preserved')


class AbsReturnsSmallInt(int):
    def __abs__(self):
        return 1


class AbsReturnsFloatInt(int):
    def __abs__(self):
        return 1.0


class AbsReturnsSelfTrapInt(int):
    def __abs__(self):
        return self

    def bit_length(self):
        raise ArithmeticError('subclass_abs_bit_length_preserved')


class FractionSubclass(Fraction):
    pass


class NumeratorTrapFraction(Fraction):
    @property
    def numerator(self):
        raise RuntimeError('fraction_numerator_preserved')


class DenominatorTrapFraction(Fraction):
    @property
    def denominator(self):
        raise RuntimeError('fraction_denominator_preserved')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _function_source(source):
    matches = [node for node in ast.parse(source).body
               if isinstance(node, ast.FunctionDef) and node.name == '_bounded']
    if len(matches) != 1:
        raise AssertionError('expected_exactly_one_bounded_function')
    return ast.get_source_segment(source, matches[0])


def frozen_function():
    process = subprocess.run(
        ['git', 'show', BASELINE + ':' + MODULE_PATH], cwd=ROOT,
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    raw = process.stdout
    source = raw.decode('utf-8')
    selected = []
    for node in ast.parse(source).body:
        if (isinstance(node, ast.ImportFrom) and node.module == 'fractions'
                and [item.name for item in node.names] == ['Fraction']):
            selected.append(node)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id == 'MAX_BITS'):
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == '_DomainError':
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == '_bounded':
            selected.append(node)
    if len(selected) != 4:
        raise AssertionError('frozen_ast_dependency_set_changed')
    namespace = {'__name__': 'scale_opt_001_frozen_surface_proximity'}
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, BASELINE + ':' + MODULE_PATH, 'exec'), namespace)
    if type(namespace['MAX_BITS']) is not int or namespace['MAX_BITS'] != 4096:
        raise AssertionError('frozen_positive_4096_bit_premise_changed')
    return namespace, {
        'commit': BASELINE,
        'module_sha256': _sha(raw),
        'function_sha256': _sha(_function_source(source).encode('utf-8')),
    }


def cases(bits):
    yield 'int_zero', 0
    for width in (1, 2, 7, 8, 63, 64, 255, 1023, bits - 1, bits,
                  bits + 1, bits * 2):
        for endpoint, magnitude in (('first', 1 << (width - 1)),
                                    ('last', (1 << width) - 1)):
            for sign in (1, -1):
                yield 'int_%s_%s_%s' % (width, endpoint, sign), sign * magnitude
    maximum, overflow = (1 << bits) - 1, 1 << bits
    yield 'bool_false', False
    yield 'bool_true', True
    for label, numerator, denominator in (
        ('zero', 0, 1), ('one', 1, 1), ('negative_one', -1, 1),
        ('half', 1, 2), ('negative_half', -1, 2),
        ('max_numerator', maximum, 1), ('negative_max_numerator', -maximum, 1),
        ('overflow_numerator', overflow, 1),
        ('negative_overflow_numerator', -overflow, 1),
        ('max_denominator', 1, maximum), ('overflow_denominator', 1, overflow),
        ('both_max_width', maximum, maximum - 2),
        ('overflow_numerator_and_max_denominator', overflow, maximum),
        ('max_numerator_and_overflow_denominator', maximum, overflow),
        ('reduced_to_boundary', overflow, 2),
        ('reduced_still_overflow', overflow * 2, 2),
    ):
        yield 'fraction_' + label, Fraction(numerator, denominator)
    for cls in (IntSubclass, BitLengthTrapInt, AbsTrapInt, AbsReturnsSmallInt,
                AbsReturnsFloatInt, AbsReturnsSelfTrapInt):
        for label, value in (('zero', 0), ('small_positive', 7),
                             ('small_negative', -7), ('boundary', maximum),
                             ('overflow', overflow), ('negative_overflow', -overflow)):
            yield cls.__name__ + '_' + label, cls(value)
    yield 'fraction_subclass_small', FractionSubclass(1, 2)
    yield 'fraction_subclass_overflow', FractionSubclass(overflow, 1)
    yield 'fraction_numerator_trap', NumeratorTrapFraction(1, 2)
    yield 'fraction_denominator_trap', DenominatorTrapFraction(1, 2)


def observation(function, domain_error, value):
    try:
        returned = function(value)
    except Exception as error:
        kind = ('_DomainError' if type(error) is domain_error else
                type(error).__module__ + '.' + type(error).__qualname__)
        return {'outcome': 'raised', 'error_type': kind,
                'message': str(error), 'args': list(error.args)}
    return {'outcome': 'returned', 'same_object': returned is value,
            'return_type': type(returned).__module__ + '.' + type(returned).__qualname__}


def main():
    baseline, origin = frozen_function()
    sys.path.insert(0, str(ROOT))
    candidate = importlib.import_module('human_eye_plugin.surface_proximity')
    path = Path(candidate.__file__).resolve()
    if path != (ROOT / MODULE_PATH).resolve():
        raise AssertionError('candidate_imported_from_wrong_checkout')
    if type(candidate.MAX_BITS) is not int or candidate.MAX_BITS != baseline['MAX_BITS']:
        raise AssertionError('candidate_positive_4096_bit_premise_changed')
    if candidate._DomainError.__bases__ != baseline['_DomainError'].__bases__:
        raise AssertionError('candidate_domain_error_bases_changed')
    candidate_raw = path.read_bytes()
    counts, failures, labels = Counter(), [], set()
    for label, value in cases(baseline['MAX_BITS']):
        if label in labels:
            raise AssertionError('duplicate_case_label:' + label)
        labels.add(label)
        expected = observation(baseline['_bounded'], baseline['_DomainError'], value)
        actual = observation(candidate._bounded, candidate._DomainError, value)
        counts[expected['outcome']] += 1
        if expected['outcome'] == 'raised':
            counts[expected['error_type']] += 1
        if expected != actual or (actual['outcome'] == 'returned' and not actual['same_object']):
            failures.append({'case': label, 'expected': expected, 'actual': actual})
    if path.read_bytes() != candidate_raw:
        raise AssertionError('candidate_source_changed_during_check')
    missing = [relative for relative in REGRESSIONS if not (ROOT / relative).is_file()]
    if missing:
        raise AssertionError('recommended_regression_missing:' + ','.join(missing))
    report = {
        'schema': 'scale-opt-001-bounded-equivalence-v1',
        'passed': not failures, 'case_count': len(labels), 'failure_count': len(failures),
        'baseline': origin,
        'candidate': {
            'path': str(path), 'module_sha256': _sha(candidate_raw),
            'function_sha256': _sha(_function_source(candidate_raw.decode('utf-8')).encode('utf-8')),
        },
        'premise': {'MAX_BITS': candidate.MAX_BITS, 'fixed_positive_product_constant': True,
                    'arbitrary_MAX_BITS_monkeypatch_equivalence_claimed': False},
        'baseline_outcomes': dict(sorted(counts.items())),
        'regression_recommendations': REGRESSIONS,
        'failures': failures,
    }
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
