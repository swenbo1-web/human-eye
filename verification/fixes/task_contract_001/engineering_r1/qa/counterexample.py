"""Record the actual mixed-component tolerance counterexample without new geometry."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
import numpy as np
from human_eye_plugin import geometry_safety as geometry, runtime_identity, task_query
from verification.test_concave_geometry import box, entity

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
overlap = 2.0 ** -32
a = box((1 - overlap, 0, 0), (1, 1, 1), 'a')
parts = [box((0, y, 0), (1, 1, 1), str(index)) for index, y in enumerate((0, 3))]
b = entity('b', np.vstack([part.vertices for part in parts]),
           np.vstack([parts[0].faces, parts[1].faces + 8]))
original = geometry._certified_solid_collision
calls = []
def measured(*values, **options):
    result = original(*values, **options)
    calls.append(dict(tolerance_m=values[2], penetrating=result[0],
                      depth_m=result[1], method=result[3]))
    return result

with patch.object(geometry, '_certified_solid_collision', side_effect=measured):
    strict = geometry.measure_pair_geometry(a, b, need_clearance=True,
                                           need_witness=True, need_relation_evidence=True)
projected = task_query._pair_relation(strict)
assert strict['signed_clearance_m'] == -overlap
assert calls[0]['method'] == 'convex_components_sat' and not calls[0]['penetrating']
assert calls[1]['method'] == 'convex_components_escape' and calls[1]['penetrating']
record = dict(source_sha256=runtime_identity.runtime_identity()['source_sha256'],
              independent_expected_overlap_m=overlap,
              actual_binary64_axis_overlap_m=float(np.max(parts[0].vertices[:, 0])-np.min(a.vertices[:, 0])),
              intrinsic_classification_calls=calls, strict=strict, pair_relation=projected,
              provenance_correct=projected['value']['evidence']['method'] == strict['clearance_method'])
with args.output.open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(dict(signed_clearance_m=strict['signed_clearance_m'],
                     method=projected['value']['evidence']['method'],
                     clearance_method=strict['clearance_method'],
                     provenance_correct=record['provenance_correct'])))
