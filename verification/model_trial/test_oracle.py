"""Non-model, non-Blender adversarial tests for the private native oracle."""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import unittest


_SPEC = importlib.util.spec_from_file_location('model_trial_oracle', Path(__file__).with_name('oracle.py'))
oracle = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(oracle)

SIGNS = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
         (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
         [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]


def refresh(obj):
    obj['world_vertices'] = [[sum(obj['matrix'][r][c]*v[c] for c in range(3))+obj['matrix'][r][3]
                             for r in range(3)] for v in obj['local_vertices']]


def box(size, center, angle=0, local_origin=(0, 0, 0)):
    s, c = math.sin(angle), math.cos(angle)
    obj = {'matrix': [[c,0,s,center[0]], [0,1,0,center[1]], [-s,0,c,center[2]], [0,0,0,1]],
           'local_vertices': [[sign[k]*size[k]/2+local_origin[k] for k in range(3)] for sign in SIGNS],
           'faces': deepcopy(FACES), 'color': [.12,.4,.85,1.]}
    refresh(obj)
    return obj


def scene(angle=0, origin=(0, 0, 0), gap=.004):
    normal = [math.sin(angle), 0, math.cos(angle)]
    native = {'normal': normal, 'counts': {'host_write_events': 0},
              'native_cumulative_translation_m': 0., 'loaded_file': '', 'user_file_loaded_or_saved': False,
              'objects': {'GreyBase': box([.2,.2,.2], origin, angle),
                          'BluePart': box([.06,.06,.1], [origin[k]+normal[k]*(.15+gap) for k in range(3)], angle),
                          'Distractor': box([.01,.01,.01], [origin[0]+.4, origin[1]+.4, origin[2]+.4])}}
    return native


def move(native, delta):
    after = deepcopy(native)
    for k in range(3):
        after['objects']['BluePart']['matrix'][k][3] += delta[k]
    refresh(after['objects']['BluePart'])
    after['counts']['host_write_events'] += 1
    actual = [after['objects']['BluePart']['matrix'][k][3]-native['objects']['BluePart']['matrix'][k][3] for k in range(3)]
    after['native_cumulative_translation_m'] += math.hypot(*actual)
    return after, {'before': deepcopy(native), 'after': deepcopy(after)}


def goal(initial):
    # Three 0.9mm writes and one smaller write avoid binary64 cap ambiguity.
    current = deepcopy(initial)
    snapshots = []
    dz = (.001-oracle.independent_gap(current))/current['normal'][2]
    while abs(dz) > 1e-14:
        step = math.copysign(min(abs(dz), .0009), dz)
        current, event = move(current, [0,0,step])
        snapshots.append(event)
        dz = (.001-oracle.independent_gap(current))/current['normal'][2]
    return current, snapshots


class NativeOracleTests(unittest.TestCase):
    def test_origin_and_rigid_scene_translation_have_same_verdict(self):
        for angle in (0, math.radians(17)):
            baseline = None
            for origin in ((0,0,0), (.37,-.23,1.2), (-2.4,3.1,-.4)):
                with self.subTest(angle=angle, origin=origin):
                    initial = scene(angle, origin)
                    final, events = goal(initial)
                    scored = oracle.score(initial, final, write_snapshots=events)
                    self.assertTrue(scored['passed'], scored)
                    self.assertTrue(scored['goal_succeeded'])
                    self.assertTrue(scored['endpoint']['footprint']['passed'])
                    self.assertAlmostEqual(scored['gap_m'], .001, places=12)
                    if baseline is None:
                        baseline = scored['checks']
                    self.assertEqual(scored['checks'], baseline)

    def test_reference_mesh_origin_need_not_be_its_center(self):
        initial = scene(math.radians(10), (.41,-.21,.7))
        obj = initial['objects']['GreyBase']
        shift = [.04,-.02,.03]
        for vertex in obj['local_vertices']:
            for k in range(3):
                vertex[k] += shift[k]
        for r in range(3):
            obj['matrix'][r][3] -= sum(obj['matrix'][r][c]*shift[c] for c in range(3))
        refresh(obj)
        final, events = goal(initial)
        self.assertTrue(oracle.score(initial, final, write_snapshots=events)['passed'])

    def test_moving_focal_out_of_finite_support_is_rejected(self):
        initial = scene(gap=.001)
        initial['objects']['BluePart']['matrix'][0][3] = .12
        refresh(initial['objects']['BluePart'])
        scored = oracle.score(initial, deepcopy(initial))
        self.assertFalse(scored['passed'])
        self.assertFalse(scored['checks']['focal_footprint_strictly_inside_actual_support'])

    def test_world_origin_false_positive_is_rejected_at_translated_support(self):
        initial = scene(origin=(.3,.2,0), gap=.001)
        initial['objects']['BluePart']['matrix'][0][3] = 0
        initial['objects']['BluePart']['matrix'][1][3] = 0
        refresh(initial['objects']['BluePart'])
        self.assertFalse(oracle.score(initial, deepcopy(initial))['passed'])

    def test_open_reference_zero_write_correct_refusal(self):
        initial = scene()
        initial['objects']['GreyBase']['faces'].pop()
        scored = oracle.score(initial, deepcopy(initial), kind='unsupported', declared_status='unsupported')
        self.assertTrue(scored['passed'], scored)
        self.assertFalse(scored['goal_succeeded'])
        topology = scored['domain']['initial']['objects']['GreyBase']['topology']
        self.assertFalse(topology['closed_two_incident_faces_per_edge'])
        self.assertFalse(oracle.score(initial, deepcopy(initial), declared_status='success')['passed'])

    def test_open_focal_refusal_requires_no_setters_and_correct_declaration(self):
        initial = scene()
        initial['objects']['BluePart']['faces'] = [[4,5,6], [4,6,7]]
        self.assertFalse(oracle.score(initial, deepcopy(initial), kind='unsupported', declared_status='success')['passed'])
        self.assertFalse(oracle.score(initial, deepcopy(initial), kind='unsupported')['passed'])
        final, event = move(initial, [0,0,0])
        self.assertFalse(oracle.score(initial, final, kind='unsupported', declared_status='refused', write_snapshots=[event])['passed'])

    def test_closed_domain_cannot_claim_unsupported_success(self):
        initial = scene()
        self.assertFalse(oracle.score(initial, deepcopy(initial), kind='unsupported', declared_status='unsupported')['passed'])

    def test_duplicate_and_degenerate_and_fake_closed_faces_reject(self):
        corruptions = [lambda obj: obj['faces'].append(deepcopy(obj['faces'][0])),
                       lambda obj: obj['faces'].__setitem__(0, [0,0,1]),
                       lambda obj: obj.__setitem__('faces', [[0,1,2],[0,2,3]]*6),
                       lambda obj: obj['faces'].__setitem__(0, [0,2,5]),
                       lambda obj: obj['faces'].__setitem__(0, list(reversed(obj['faces'][0])))]
        for corruption in corruptions:
            initial = scene(gap=.001)
            corruption(initial['objects']['GreyBase'])
            with self.subTest(faces=initial['objects']['GreyBase']['faces']):
                scored = oracle.score(initial, deepcopy(initial))
                self.assertFalse(scored['passed'])
                self.assertFalse(scored['domain']['supported'])

    def test_nan_and_malformed_native_fail_closed_and_return_json(self):
        for path in ('normal', 'local', 'matrix', 'world', 'faces', 'color'):
            initial = scene(gap=.001)
            obj = initial['objects']['BluePart']
            if path == 'normal': initial['normal'][0] = float('nan')
            elif path == 'local': obj['local_vertices'] = None
            elif path == 'matrix': obj['matrix'][1][2] = float('nan')
            elif path == 'world': obj['world_vertices'][0][0] = float('inf')
            elif path == 'faces': obj['faces'][0][0] = 99
            elif path == 'color': obj['color'][0] = float('nan')
            with self.subTest(path=path):
                scored = oracle.score(initial, deepcopy(initial))
                self.assertFalse(scored['passed'])
                json.dumps(scored, allow_nan=False)

    def test_intermediate_penetration_remains_failure_after_return(self):
        initial = scene(gap=.001)
        current = initial
        events = []
        for dz in [-.0008, -.0008, .0008, .0008]:
            current, event = move(current, [0,0,dz])
            events.append(event)
        scored = oracle.score(initial, current, write_snapshots=events)
        self.assertTrue(scored['endpoint']['passed'])
        self.assertFalse(scored['passed'])
        self.assertFalse(scored['write_meter']['write_endpoints'][1]['checks']['all_object_pairs_strictly_separated'])

    def test_exact_pose_invariant_rejects_tiny_rotation_change(self):
        initial = scene(gap=.001)
        final, event = move(initial, [0,0,0])
        final['objects']['BluePart']['matrix'][0][1] = 1e-16
        refresh(final['objects']['BluePart'])
        event['after'] = deepcopy(final)
        scored = oracle.score(initial, final, write_snapshots=[event])
        self.assertFalse(scored['passed'])
        self.assertFalse(scored['checks']['focal_13_nontranslation_matrix_values_exactly_unchanged'])

    def test_mesh_color_and_other_objects_must_remain_exact(self):
        for field in ('color', 'local_vertices', 'faces', 'other'):
            initial = scene(gap=.001)
            final, event = move(initial, [0,0,0])
            if field == 'color': final['objects']['BluePart']['color'][0] += 1e-16
            elif field == 'local_vertices':
                final['objects']['BluePart']['local_vertices'][0][0] += 1e-16
                refresh(final['objects']['BluePart'])
            elif field == 'faces': final['objects']['BluePart']['faces'].reverse()
            else: final['objects']['Distractor']['color'][0] += 1e-16
            event['after'] = deepcopy(final)
            with self.subTest(field=field):
                self.assertFalse(oracle.score(initial, final, write_snapshots=[event])['passed'])

    def test_xy_each_tolerance_and_not_euclidean_region(self):
        for dx, dy, expected in ((.9e-6,.9e-6,True), (1.1e-6,0,False), (0,-1.1e-6,False)):
            initial = scene(gap=.001)
            final, event = move(initial, [dx,dy,0])
            scored = oracle.score(initial, final, write_snapshots=[event])
            self.assertEqual(scored['passed'], expected, scored)

    def test_no_engine_or_model_success_claim_can_override_geometry(self):
        initial = scene()
        scored = oracle.score(initial, deepcopy(initial), declared_status='success', reported_gap_m=.001)
        self.assertFalse(scored['passed'])
        self.assertFalse(scored['goal_succeeded'])
        self.assertFalse(scored['model_report']['reported_gap_accurate'])
        self.assertFalse(scored['model_report']['claim_used_for_geometry'])

    def test_readonly_accurate_measurement_zero_write(self):
        initial = scene(math.radians(12), (.31,-.19,.8))
        scored = oracle.score(initial, deepcopy(initial), kind='readonly', reported_gap_m=.004)
        self.assertTrue(scored['passed'], scored)
        self.assertFalse(scored['goal_succeeded'])
        self.assertFalse(oracle.score(initial, deepcopy(initial), kind='readonly', reported_gap_m=.004011)['passed'])
        self.assertFalse(oracle.score(initial, deepcopy(initial), kind='readonly')['passed'])
        final, event = move(initial, [0,0,0])
        self.assertFalse(oracle.score(initial, final, kind='readonly', reported_gap_m=.004, write_snapshots=[event])['passed'])

    def test_every_object_pair_including_distractor_pair_is_scored(self):
        initial = scene(gap=.001)
        initial['objects']['OtherDistractor'] = deepcopy(initial['objects']['Distractor'])
        scored = oracle.score(initial, deepcopy(initial))
        self.assertFalse(scored['passed'])
        self.assertEqual(scored['endpoint']['all_pairs_sat']['pair_count'], 6)
        self.assertFalse(next(row for row in scored['endpoint']['all_pairs_sat']['pairs']
                              if row['objects'] == ['Distractor','OtherDistractor'])['strictly_separated'])

    def test_sat_touch_and_submicrometre_separation_do_not_pass(self):
        for gap in (0, .5e-6, 1e-6):
            initial = scene(gap=gap)
            sat = oracle.independent_all_pairs_sat(initial)
            self.assertFalse(sat['passed'], (gap, sat))
        self.assertTrue(oracle.independent_all_pairs_sat(scene(gap=1.1e-6))['passed'])

    def test_actual_write_cap_count_path_and_missing_evidence(self):
        initial = scene()
        final, events = goal(initial)
        self.assertTrue(oracle.score(initial, final, write_snapshots=events)['passed'])
        self.assertFalse(oracle.score(initial, final)['passed'])
        wrong_count = deepcopy(final)
        wrong_count['counts']['host_write_events'] += 1
        self.assertFalse(oracle.score(initial, wrong_count, write_snapshots=events)['passed'])
        wrong_path = deepcopy(final)
        wrong_path['native_cumulative_translation_m'] = 0
        self.assertFalse(oracle.score(initial, wrong_path, write_snapshots=events)['passed'])
        over, event = move(initial, [0,0,-.003])
        self.assertFalse(oracle.score(initial, over, write_snapshots=[event])['passed'])
        current = scene(gap=.001)
        start = deepcopy(current)
        many = []
        for _ in range(9):
            current, event = move(current, [0,0,0])
            many.append(event)
        self.assertFalse(oracle.score(start, current, write_snapshots=many)['passed'])

    def test_discontinuous_snapshots_and_unmetered_final_changes_reject(self):
        initial = scene()
        final, events = goal(initial)
        events[1]['before']['objects']['BluePart']['color'][0] = .9
        self.assertFalse(oracle.score(initial, final, write_snapshots=events)['passed'])
        final, events = goal(initial)
        final['objects']['BluePart']['matrix'][2][3] += 1e-7
        refresh(final['objects']['BluePart'])
        self.assertFalse(oracle.score(initial, final, write_snapshots=events)['passed'])

    def test_unknown_budget_never_passes_but_full_native_writes_can_account(self):
        initial = scene(gap=.001)
        final = deepcopy(initial)
        del final['counts']
        del final['native_cumulative_translation_m']
        self.assertFalse(oracle.score(initial, final)['passed'])
        final['writes'] = []
        self.assertTrue(oracle.score(initial, final)['passed'])
        initial = scene()
        final, events = goal(initial)
        final.pop('counts')
        final.pop('native_cumulative_translation_m')
        final['writes'] = events
        self.assertTrue(oracle.score(initial, final)['passed'])

    def test_nonfresh_meter_cannot_hide_prior_setters(self):
        initial = scene(gap=.001)
        initial['counts']['host_write_events'] = 7
        initial['native_cumulative_translation_m'] = .007
        self.assertFalse(oracle.score(initial, deepcopy(initial))['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
