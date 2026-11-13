"""Independent stored-frame and local state characterization. No render or timing run."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image

SOURCE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_001')
HERE = Path(__file__).resolve().parent
checks = []
inputs = {}


def load_bytes(relative):
    raw = (SOURCE / relative).read_bytes()
    inputs[relative] = hashlib.sha256(raw).hexdigest()
    return raw


def document(relative):
    return json.loads(load_bytes(relative))


def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})


result = document('results/optimized.json')
readability = document('render/READABILITY.json')
cameras = document('inputs/CAMERAS.json')
scene = document('inputs/SCENE_GEOMETRY_RATIONAL.json')
order = [p['name'] for p in cameras['views']]
geometric = {row['view_name']: set(row['geometric_complete_roi_ids']) for row in result['per_view']}
actual = {}
views = []
check('stored_rois_6', len(result['regions']) == 6)
check('shared_source_identity', readability['scene_identity'] == result['scene_identity'])
check('shared_camera_identity', readability['candidate_identity'] == result['candidate_identity'])
for pose in cameras['views']:
    name = pose['name']
    meta = document('render/' + name + '.json')
    png = load_bytes('render/' + name + '.png')
    arrays = load_bytes('render/' + name + '.npz')
    check(name + '_png_sha', hashlib.sha256(png).hexdigest() == meta['PNG_sha256'])
    check(name + '_arrays_sha', hashlib.sha256(arrays).hexdigest() == meta['arrays_sha256'])
    check(name + '_camera_pose', meta['pose'] == pose)
    with np.load(SOURCE / 'render' / (name + '.npz'), allow_pickle=False) as f:
        color, owners, depth = (f[k] for k in ('color', 'owners', 'depth'))
    with Image.open(SOURCE / 'render' / (name + '.png')) as image:
        rgb = np.asarray(image.convert('RGB'))
    check(name + '_actual_png_equals_buffer_rgb', np.array_equal(rgb, color))
    check(name + '_full_512_shapes', color.shape == (512, 512, 3) and owners.shape == depth.shape == (512, 512))
    check(name + '_owners_in_scene', bool(np.all((owners >= -1) & (owners < len(scene['objects'])))))
    check(name + '_foreground_depth_and_owner', np.array_equal(owners >= 0, np.isfinite(depth) & (depth > 0)))
    boundary = np.zeros(owners.shape, dtype=bool)
    for axis in (0, 1):
        changed = np.diff(owners, axis=axis) != 0
        delta = np.diff(color.astype(np.int32), axis=axis)
        qualified = changed & (np.sum(delta * delta, axis=2) >= 576)
        if axis == 0:
            boundary[:-1, :] |= qualified
            boundary[1:, :] |= qualified
        else:
            boundary[:, :-1] |= qualified
            boundary[:, 1:] |= qualified
    rows = []
    readable = set()
    for roi in result['regions']:
        mask = owners == roi['object_index']
        count = int(np.count_nonzero(mask))
        edges = int(np.count_nonzero(boundary & mask))
        stored = next(row for row in readability['pixel_rows'] if row['view'] == name and row['roi_id'] == roi['roi_id'])
        # All registered panels face +Z and all six eye directions have positive Z.
        vertices = np.asarray([[float(__import__('fractions').Fraction(x)) for x in v] for v in roi['vertices']])
        front = float(np.cross(vertices[1]-vertices[0], vertices[3]-vertices[0]) @ np.asarray(pose['target_to_eye_unit'])) > 0
        qualified = front and count >= 16 and edges >= 4
        check(name + ':' + roi['roi_id'] + '_pixel_counts', (count, edges, qualified) == (stored['visible_surface_pixels'], stored['contrasting_boundary_pixels'], stored['readable']))
        if qualified:
            readable.add(roi['roi_id'])
        rows.append({'roi_id': roi['roi_id'], 'surface_pixels': count, 'boundary_pixels': edges, 'readable': qualified})
    actual[name] = geometric[name] & readable
    frame = next(x for x in readability['frames'] if x['view_name'] == name)
    check(name + '_stored_readable_set', set(frame['readable_roi_ids']) == readable)
    check(name + '_stored_deliverable_set', actual[name] == set(next(x for x in result['per_view'] if x['view_name'] == name)['deliverable_complete_readable_roi_ids']))
    views.append({'name': name, 'geometric_complete': sorted(geometric[name]), 'pixel_readable': sorted(readable), 'deliverable': sorted(actual[name]), 'rows': rows,
                  'unique_rgb_colors': np.unique(color.reshape(-1, 3), axis=0).tolist(), 'png_bytes': len(png), 'visible_owner_count': len(set(np.unique(owners)) - {-1})})

covered, remaining, sequence = set(), list(order), []
while remaining:
    name = 'SCENE' if not sequence else max(remaining, key=lambda n: len(geometric[n] - covered))
    if sequence and not geometric[name] - covered:
        break
    sequence.append({'view': name, 'new': sorted(actual[name] - covered)})
    covered |= actual[name]
    remaining.remove(name)
check('sequence_SCENE_BACK', [s['view'] for s in sequence] == ['SCENE', 'BACK'])
check('new_coverage_2_3', [len(s['new']) for s in sequence] == [2, 3])
check('covered_5', len(covered) == 5)
check('all_six_same_covered', covered == set().union(*actual.values()))
check('actual_geometric_masks_same_on_this_fixture', all(actual[n] == geometric[n] for n in order))
all_covered = set().union(*actual.values())
subsets = []
for size in range(7):
    subsets = [list(s) for s in itertools.combinations(order, size) if set().union(*(actual[n] for n in s)) == all_covered]
    if subsets:
        break
check('independent_minimum_2', size == 2)

# Characterize state, without any coverage build, render or formal benchmark.
load_bytes('coverage.py')
spec = importlib.util.spec_from_file_location('_root_transition_state_audit', SOURCE / 'coverage.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
index = SimpleNamespace(view_masks={'SCENE': 0, 'TOP': 3, 'BACK': 1}, view_order=('SCENE', 'TOP', 'BACK'))
state = module.CoverageState(index, observed_views={'SCENE': {}}, covered_mask=0)
choice = state.next_view()
check('characterization_geometric_ranking_ignores_known_pixel_quality', choice == 'TOP')
characterization = {'geometric_gains': {'TOP': 2, 'BACK': 1}, 'hypothetical_actual_readable_gains': {'TOP': 0, 'BACK': 1},
                    'chosen': choice, 'meaning': 'Current next_view has no pixel-quality input; this is a state API characterization, not a newly rendered scene nor a failure in the frozen 36-cell fixture.'}

output = {'scope': 'Independent local stored-image decode/count and bitset reconstruction; one state API characterization. No new render, benchmark, model, API or Blender.',
          'source_commit': 'bfcc35e32aab0b724261a5140fc5d05df9ddad48', 'checks': checks, 'checks_count': len(checks),
          'failed': [c for c in checks if not c['passed']], 'views': views, 'sequence': sequence,
          'minimum_subsets': subsets, 'uncovered': sorted(set(result['roi_ids']) - covered),
          'characterization': characterization, 'inputs_sha256': inputs,
          'not_proven': ['external/model image delivery', 'model semantic recognition', 'cold on-demand render savings', 'pixel/geometric mismatch recovery on an actual newly rendered fixture']}
HERE.mkdir(parents=True, exist_ok=True)
(HERE / 'RESULT.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({'checks': len(checks), 'failed': output['failed'], 'selected': [s['view'] for s in sequence], 'new_coverage': [len(s['new']) for s in sequence], 'minimum_subsets': subsets, 'scope': output['scope']}, ensure_ascii=False))
