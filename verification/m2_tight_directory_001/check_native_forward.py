"""Check the fixed native arithmetic against stored evaluated-vertex originals."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def main():
    batch = Path(__file__).resolve().parent
    source = batch / 'measurement/assets_01/INPUTS.json'
    output = Path(sys.argv[1])
    raw = source.read_bytes()
    rows = []
    for asset in json.loads(raw)['inputs']:
        changed_points = changed_boxes = 0
        maximum_difference = 0.
        for obj in asset['oracle']:
            local = np.array(obj['vertices_local'], dtype=np.float64)
            matrix = obj['matrix_world']
            world = np.empty_like(local)
            for axis in range(3):
                part = np.zeros(len(local), dtype=np.float64) + matrix[axis][0] * local[:, 0]
                part = part + matrix[axis][1] * local[:, 1]
                part = part + matrix[axis][2] * local[:, 2]
                world[:, axis] = (part + matrix[axis][3]) * asset['scale_length']
            expected = np.asarray(obj['vertices_world'])
            changed_points += int(np.count_nonzero(np.any(world != expected, axis=1)))
            maximum_difference = max(maximum_difference, float(np.max(np.abs(world - expected))))
            changed_boxes += int(world.min(axis=0).tolist() != obj['bbox_min']
                                 or world.max(axis=0).tolist() != obj['bbox_max'])
        rows.append({'asset': asset['name'], 'vertices': asset['vertex_count'],
                     'different_points': changed_points, 'different_bounds': changed_boxes,
                     'maximum_absolute_difference_m': maximum_difference})
    # This counterexample records why a fixed-input check cannot establish a
    # general claim about Python's float sum and a NumPy left fold.
    terms = [1e16, 1., -1e16]
    scalar = sum(terms)
    left_fold = float((np.float64(terms[0]) + terms[1]) + terms[2])
    result = {'scope': 'fixed-input pure arithmetic only', 'Python': sys.version,
              'Python_executable': sys.executable, 'NumPy': np.__version__,
              'input_sha256': hashlib.sha256(raw).hexdigest(), 'rows': rows,
              'sum_counterexample': {'terms': terms, 'builtin_sum': scalar, 'NumPy_left_fold': left_fold},
              'all_fixed_input_points_exact': all(row['different_points'] == 0 for row in rows),
              'generic_bitwise_equivalence_proven': False,
              'Blender_sessions': 0, 'model_consumers': 0, 'performance_samples': 0}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result))
    return 0 if result['all_fixed_input_points_exact'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
