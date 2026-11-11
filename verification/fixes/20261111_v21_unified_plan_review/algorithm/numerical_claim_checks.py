"""Offline checks of proposed equivalence arguments; imports no project code.

These are mathematical/IEEE arithmetic examples, NOT product-entry regressions.
They do not claim that the product admits any of the illustrated geometry.
"""
import json
import math
import sys
from fractions import Fraction
from pathlib import Path


def point_segment_scalar(p, start, end):
    delta = end - start
    offset = p - start
    t = max(0.0, min(1.0, offset * delta / (delta * delta)))
    return (offset - t * delta) ** 2


# Already in a common local frame: query at 0; segment is entirely x <= -1.
p, start, end = 0.0, -1e16, -1.0
legacy_sq = point_segment_scalar(p, start, end)
exact_sq = (Fraction.from_float(p) - Fraction.from_float(end)) ** 2
bound_sq = (p - end) ** 2
incumbent_sq = 0.25
prunes = bound_sq * (1.0 - 1e-14) > incumbent_sq
assert exact_sq == 1 and legacy_sq == 0 and prunes

left_sum = ((1e16 + 1.0) + -1e16)
python_sum = sum([1e16, 1.0, -1e16])
left_zero = ((-0.0 + -0.0) + -0.0) + -0.0
python_zero = sum([-0.0, -0.0, -0.0]) + -0.0
assert math.copysign(1.0, left_zero) != math.copysign(1.0, python_zero)

# Strict '<' updates preserve the first encountered equal candidate.
def first_witness(order):
    best, witness = math.inf, None
    for point in order:
        distance = sum(value * value for value in point)
        if distance < best:
            best, witness = distance, point
    return best, witness

forward = first_witness([(1, 0, 0), (-1, 0, 0)])
reverse = first_witness([(-1, 0, 0), (1, 0, 0)])
assert forward[0] == reverse[0] and forward[1] != reverse[1]

result = {
    'scope': 'offline arithmetic claims only; no project imports, product calls, Blender or model consumers',
    'python': sys.version,
    'float_aabb_relaxation': {
        'point': p, 'segment': [start, end],
        'exact_distance_squared': str(exact_sq), 'legacy_residual_squared': legacy_sq,
        'aabb_lower_bound_squared': bound_sq, 'incumbent_squared': incumbent_sq,
        'proposed_rule_prunes': prunes,
        'conclusion': '1e-14 does not prove equality to a cancellation-prone float kernel; use geometric truth/output contract, not preservation of old numerical error',
    },
    'scalar_world_transform': {
        'python_sum': python_sum, 'three_term_left_association': left_sum,
        'python_sum_json_zero': json.dumps(python_zero), 'left_association_json_zero': json.dumps(left_zero),
        'conclusion': 'foreach_get can preserve source values; replacing the following arithmetic needs a separate equivalence argument for the actual host Python version',
    },
    'equal_distance_witness': {'forward': forward, 'reverse': reverse,
        'conclusion': 'a reordered traversal must define deterministic feature ties if witness identity is part of output equivalence'},
}
Path(__file__).with_name('numerical_claim_results.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'offline_checks': 'passed', 'product_tests': 'not_run', 'result': str(Path(__file__).with_name('numerical_claim_results.json'))}))
