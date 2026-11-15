"""Independent displacement publication guard for nonunique nearest pairs."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOLERANCE = F.from_float(1e-9)


def vector(value):
    if type(value) not in (list, tuple) or len(value) != 3 or any(type(item) is bool for item in value):
        raise ValueError('published_three_coordinate_witness_required')
    return tuple(F(item) for item in value)


def validate(fact, state='initial', missing=False):
    truth = json.loads((HERE / 'scoring/STATE_TRUTH.json').read_bytes())['states'][state]
    pair = truth['missing_Far11_one_witness'] if missing else truth['one_main_witness']
    expected = tuple(b-a for a, b in zip(vector(pair['a']), vector(pair['b'])))
    witness = fact['value']['nearest_witness']
    delta = tuple(b-a for a, b in zip(vector(witness['a']), vector(witness['b'])))
    residual = tuple(actual-exact for actual, exact in zip(delta, expected))
    squared_error = sum(value*value for value in residual)
    if squared_error > TOLERANCE*TOLERANCE:
        raise ValueError('nearest_witness_relative_displacement_publication_error')
    return {'passed_checked_scope': True, 'expected_nearest_displacement_exact_m': [str(value) for value in expected],
            'published_displacement_exact_m': [str(value) for value in delta],
            'component_residuals_exact_m': [str(value) for value in residual],
            'squared_displacement_error_exact_m2': str(squared_error),
            'publication_tolerance_exact_m': str(TOLERANCE),
            'particular_point_pair_required': False,
            'scope': 'Whole-object global nearest displacement. Equal closest pairs may translate together within their shared YZ locus.'}


def review_existing_qualifications():
    roots = {'A': Path('D:/he_m5_observe_measure_001/qualification/A_qual'),
             'B_initial': Path('D:/he_m5_observe_measure_001/qualification/B_initial_qual')}
    reports = {}
    for arm, root in roots.items():
        path = root / ('business/main/PUBLIC_02.json' if arm == 'A' else 'business/main/PUBLIC_01.json')
        public = json.loads(path.read_bytes())
        task = public if arm == 'A' else public['task_result']
        reports[arm] = {'public_path': str(path), 'public_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'review': validate(task['facts']['surface_proximity'])}
    a = float(F('8589935/2147483648'))
    inconsistent = {'value': {'nearest_witness': {'a': [1, 0, 0], 'b': [a, .000001, 0]}}}
    try:
        validate(inconsistent)
    except ValueError as error:
        negative = {'rejected': str(error) == 'nearest_witness_relative_displacement_publication_error', 'reason': str(error)}
    else:
        negative = {'rejected': False}
    assert negative['rejected']
    return {'schema': 'm5-nearest-witness-publication-review-v1', 'passed_checked_scope': True,
            'qualifications': reports, 'negative_inconsistent_YZ_displacement': negative,
            'existing_kernel_relative_publication_tolerance_m': str(TOLERANCE),
            'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}


if __name__ == '__main__':
    report = review_existing_qualifications()
    path = HERE / 'scoring/WITNESS_PUBLICATION_REVIEW.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
