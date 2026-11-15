"""Freeze the declared cache-control transform and its exact shadow answers."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MATRIX = [[0, 0, 1, F(9, 8)], [0, 1, 0, F(-1, 8)], [-1, 0, 0, F(451, 32)], [0, 0, 0, 1]]
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
              'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}


def main():
    path = HERE / 'reference/FROZEN_GEOMETRY.json'
    frozen = json.loads(path.read_bytes())
    far = next(row for row in frozen['objects'] if row['name'] == 'M4_Far_11')
    vertices = [tuple(F(value) for value in point) for point in far['world_vertices_m']]
    transformed = [tuple(sum(row[k]*point[k] for k in range(3))+row[3] for row in MATRIX[:3]) for point in vertices]
    bounds = [[min(point[k] for point in transformed) for k in range(3)],
              [max(point[k] for point in transformed) for k in range(3)]]
    assert bounds == [[F(9, 8), F(-1, 8), F(67, 32)], [F(17, 8), F(7, 8), F(67, 32)]]
    rows = []
    for name, direction in DIRECTIONS.items():
        t = (F(67, 32)-2)/direction[2]
        shadow = [[bounds[0][k]-t*direction[k] for k in range(2)],
                  [bounds[1][k]-t*direction[k] for k in range(2)]]
        low = [max(F(1), shadow[0][0]), max(F(0), shadow[0][1])]
        high = [min(F(2), shadow[1][0]), min(F(1), shadow[1][1])]
        area = (high[0]-low[0])*(high[1]-low[1])
        assert area > 0
        if name == 'SCENE':
            assert shadow == [[F(1), F(0)], [F(2), F(1)]] and area == 1
        rows.append({'view': name, 'ray_parameter_exact': str(t),
                     'shadow_xy': [[str(value) for value in row] for row in shadow],
                     'horizontal_intersection_area_exact': str(area)})
    output = {'schema': 'target-002-cache-fixed-expectations-v1',
              'geometry_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'Far11_setup_matrix': [[str(value) for value in row] for row in MATRIX],
              'Far11_local_vertices_and_source_faces_unchanged': True,
              'moved_world_bounds': [[str(value) for value in row] for row in bounds],
              'shadow_union_answers': rows,
              'baseline_and_restored': {'horizontal_complete': True, 'vertical_Near_unknown': True,
                                        'Far11_excluded': True, 'complete_readable_witnesses': 1},
              'moved': {'horizontal_all_six_positive_area_occlusion': True,
                         'vertical_still_Near_unknown': True, 'Far11_retained': True,
                         'covered': 0, 'complete_witnesses': 0},
              'checker_requirements': [
                  'Use the same owned host and validate each current phase source/capture token and full directory.',
                  'Preserve the explicit setup setter receipt and readback, with the exact moved matrix and exact identity restore.',
                  'Bind expected moved world geometry to this transform of frozen local data, without rewriting the frozen input.',
                  'Recompute the actual first-blocker triangle shadow. The producer first-blocker area is not the whole-board union area above.',
                  'Do not carry a baseline complete witness or frame binding into the moved phase.',
                  'Restore the original full geometry/fingerprint and require the horizontal witness again.'
              ],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0}
    with (HERE / 'CACHE_EXPECTATIONS.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'fixed_transform_shadows': 6,
                      'physical_xy_areas': [row['horizontal_intersection_area_exact'] for row in rows]}))


if __name__ == '__main__':
    main()
