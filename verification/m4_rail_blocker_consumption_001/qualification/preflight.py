"""Recompute the ordinary qualification proof from the retained source, without a live slot."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
sys.path[:0] = [str(NS / 'harness'), str(HERE)]
from common import GEOMETRY, TRUTH, read, save, sha
from diagnostic import diagnostic_plan


def main():
    geometry, truth = read(GEOMETRY), read(TRUTH)
    objects = [{'name': obj['name'], 'visible_get': obj['visible_get'],
                'vertices': obj['evaluated']['vertices_world_m'], 'triangles': obj['evaluated']['triangles']}
               for obj in geometry['objects']]
    result = io.StringIO()
    with redirect_stdout(result):
        exec(diagnostic_plan()[1]['arguments']['code'], {'scene_data': lambda: {'objects': objects,
             'source_ref': 'sealed-array-offline-replay'}})
    value = json.loads(result.getvalue())
    expect = {(row['object_name'], tuple(row['source_triangle_indices'])): sorted(
        [hit['object_name'], hit['source_triangle_index'], hit['projected_target_plane_area_m2_exact']]
        for hit in row['finite_direction_proofs']['LEFT']['positive_area_occluders'])
        for row in truth['eligible'] if row['unit_normal'] == [-1, 0, 0]}
    actual = {(row['target'][0], tuple(row['target'][1])): row['hits'] for row in value['targets']}
    if len(actual) != 2 or actual != expect or value['counts'] != truth['counts']:
        raise ValueError('ordinary_exact_overlap_chart_disagrees_with_independent_proof')
    save(HERE / 'PREFLIGHT.json', {'passed': True, 'truth_sha256': sha(TRUTH), 'actual_live_slots': 0,
          'actual_models': 0, 'ordinary_replay': value})


if __name__ == '__main__':
    main()
