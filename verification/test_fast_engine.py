"""Trusted-session cache and task semantics, with analytic independent facts."""
import json
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_fast.engine import FastSession


def disconnected_triangles(count=4):
    vertices = []
    triangles = []
    for index in range(count):
        origin = len(vertices)
        vertices.extend([[index * 3., 0., 0.], [index * 3. + 1., 0., 0.], [index * 3., 1., 0.]])
        triangles.append([origin, origin + 1, origin + 2])
    return np.array(vertices), np.array(triangles)


def deformed(vertices, transforms):
    value = vertices.copy()
    for face, (x, y) in transforms.items():
        base = face * 3
        value[base + 1] = value[base] + [x, 0., 0.]
        value[base + 2] = value[base] + [0., y, 0.]
    return value


class FastSessionTests(unittest.TestCase):
    def test_full_metrics_have_analytic_values_and_join_original_faces(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', deformed(vertices, {1: (1.5, .5)}))
        session.set_frame('b', deformed(vertices, {1: (2., .25)}))
        result = session.query(['a', 'b'])
        self.assertTrue(result['frames']['a']['mixed'])
        self.assertTrue(result['frames']['b']['mixed'])
        self.assertEqual(result['uncovered_labels'], [])
        witness = next(row for row in result['witnesses'] if row['triangle'] == 1)
        np.testing.assert_allclose(witness['frames']['a']['stretches'], [1.5, .5])
        np.testing.assert_allclose(witness['frames']['b']['stretches'], [2., .25])
        self.assertAlmostEqual(witness['frames']['a']['area_ratio'], .75)

    def test_extrema_on_different_faces_do_not_fabricate_mixed_witness(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', deformed(vertices, {0: (1.5, 1.), 1: (1., .5)}))
        frame = session.query(['a'])['frames']['a']
        self.assertFalse(frame['mixed'])
        self.assertEqual(frame['extrema']['max_stretch'], 1.5)
        self.assertEqual(frame['extrema']['min_stretch'], .5)

    def test_disjoint_positive_faces_report_uncovered_if_preference_too_small(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', deformed(vertices, {0: (1.5, .5)}))
        session.set_frame('b', deformed(vertices, {1: (1.5, .5)}))
        result = session.query(['a', 'b'], max_witnesses=1)
        self.assertEqual(result['selected_triangles'], [0])
        self.assertEqual(result['uncovered_labels'], ['b'])
        self.assertTrue(result['frames']['b']['mixed'])
        result = session.query(['a', 'b'], max_witnesses=0)
        self.assertEqual(result['selected_triangles'], [])
        self.assertEqual(result['uncovered_labels'], ['a', 'b'])

    def test_shared_face_covers_more_frames_and_explicit_details_are_retained(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', deformed(vertices, {0: (1.5, .5), 1: (1.5, .5)}))
        session.set_frame('b', deformed(vertices, {1: (1.5, .5)}))
        result = session.query(['a', 'b'], max_witnesses=1)
        self.assertEqual(result['selected_triangles'], [1])
        self.assertEqual(result['uncovered_labels'], [])
        result = session.query(['a', 'b'], max_witnesses=0, details=[3, 1, 3])
        self.assertEqual(result['selected_triangles'], [1, 3])
        self.assertEqual(result['uncovered_labels'], [])

    def test_empty_core_has_complete_zero_counts_and_no_witness(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', vertices)
        result = session.query(['a'], bounds=[[100., 100., 100.], [101., 101., 101.]])
        self.assertEqual(result['frames']['a']['core_count'], 0)
        self.assertEqual(result['frames']['a']['states'], {'measured': 0, 'collapsed': 0, 'undefined': 0})
        self.assertFalse(result['frames']['a']['mixed'])
        self.assertTrue(all(value is None for value in result['frames']['a']['extrema'].values()))
        self.assertEqual(result['witnesses'], [])

    def test_region_membership_uses_triangle_intersection_not_centroid_or_aabb(self):
        vertices = np.array([[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]])
        session = FastSession(vertices, [[0, 1, 2]])
        session.set_frame('a', vertices)
        empty = session.query(['a'], bounds=[[1.6, 1.6, -.1], [1.9, 1.9, .1]])
        self.assertEqual(empty['frames']['a']['core_count'], 0)
        edge = session.query(['a'], bounds=[[1.9, -.01, -.1], [2.1, .01, .1]])
        self.assertEqual(edge['frames']['a']['core_count'], 1)

    def test_collapse_and_undefined_are_mathematical_states_not_precision_guards(self):
        vertices, triangles = disconnected_triangles(3)
        vertices[8] = vertices[6] + [2., 0., 0.]
        session = FastSession(vertices, triangles)
        current = vertices.copy()
        current[5] = current[3] + [2., 0., 0.]
        session.set_frame('a', current)
        result = session.query(['a'], details=[0, 1, 2])
        self.assertEqual(result['frames']['a']['states'], {'measured': 1, 'collapsed': 1, 'undefined': 1})
        self.assertIsNone(result['frames']['a']['mixed'])
        rows = session.rows('a', [0, 1, 2])
        self.assertEqual(rows[1]['area_ratio'], 0.)
        self.assertIsNone(rows[2]['stretches'])
        json.dumps(result, allow_nan=False)

    def test_sparse_update_equals_full_and_only_recomputes_incident_faces(self):
        vertices, triangles = disconnected_triangles(50)
        incremental = FastSession(vertices, triangles)
        complete = FastSession(vertices, triangles)
        incremental.set_frame('a', vertices)
        complete.set_frame('a', vertices)
        for face in (3, 17, 49, 3):
            updated = vertices.copy()
            updated[face * 3 + 1, 0] += .5
            stats = incremental.set_frame('a', updated, changed_vertices=[face * 3 + 1])
            vertices = updated
            complete.set_frame('a', vertices)
            self.assertEqual(stats['faces_recomputed'], 1)
            self.assertEqual(stats['vertices_updated'], 1)
            self.assertEqual(incremental.rows('a', range(50)), complete.rows('a', range(50)))
            self.assertEqual(incremental.query(['a']), complete.query(['a']))

    def test_sparse_aabb_updates_move_faces_between_regions(self):
        vertices, triangles = disconnected_triangles(3)
        session = FastSession(vertices, triangles)
        session.set_frame('a', vertices)
        box = [[-.1, -.1, -.1], [1.1, 1.1, .1]]
        self.assertEqual(session.query(['a'], bounds=box)['frames']['a']['core_count'], 1)
        updated = vertices.copy()
        updated[:3, 0] += 20
        session.set_frame('a', updated, changed_vertices=[0, 1, 2])
        self.assertEqual(session.query(['a'], bounds=box)['frames']['a']['core_count'], 0)

    def test_ownership_and_explicit_change_declaration(self):
        vertices, triangles = disconnected_triangles(3)
        session = FastSession(vertices, triangles)
        session.set_frame('a', vertices)
        baseline = session.rows('a', [0, 1, 2])
        vertices[1, 0] += 10
        triangles[0] = [6, 7, 8]
        self.assertEqual(session.rows('a', [0, 1, 2]), baseline)
        stats = session.set_frame('a', vertices, changed_vertices=[])
        self.assertEqual(stats['faces_recomputed'], 0)
        self.assertEqual(session.rows('a', [0, 1, 2]), baseline)
        session.set_frame('a', vertices, changed_vertices=[1])
        self.assertEqual(session.rows('a', [0])[0]['stretches'], [11., 1.])

    def test_duplicate_vertex_adjacency_updates_each_face_once(self):
        vertices, _ = disconnected_triangles(1)
        session = FastSession(vertices, [[0, 1, 2], [0, 0, 1]])
        session.set_frame('a', vertices)
        vertices[0, 0] = -.25
        stats = session.set_frame('a', vertices, changed_vertices=[0, 0])
        self.assertEqual(stats['faces_recomputed'], 2)
        self.assertEqual(stats['vertices_updated'], 1)

    def test_query_does_not_recalculate_metrics(self):
        vertices, triangles = disconnected_triangles()
        session = FastSession(vertices, triangles)
        session.set_frame('a', vertices)
        with patch('human_eye_fast.engine.deformation_metrics', side_effect=AssertionError('unexpected recalculation')):
            first = session.query(['a'])
            second = session.query(['a'])
        self.assertEqual(first, second)

    def test_shared_vertex_updates_all_incident_faces_and_no_other_frame(self):
        vertices = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.],
                             [4., 0., 0.], [5., 0., 0.], [4., 1., 0.]])
        triangles = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
        session = FastSession(vertices, triangles)
        session.set_frame('changed', vertices)
        session.set_frame('rest', vertices)
        rest = session.rows('rest', [0, 1, 2])
        vertices[2] = [1.5, 1.5, .25]
        stats = session.set_frame('changed', vertices, changed_vertices=[2])
        self.assertEqual(stats['faces_recomputed'], 2)
        full = FastSession(session.reference_vertices, triangles)
        full.set_frame('changed', vertices)
        self.assertEqual(session.rows('changed', [0, 1, 2]), full.rows('changed', [0, 1, 2]))
        self.assertEqual(session.rows('rest', [0, 1, 2]), rest)

    def test_confirmed_mixed_remains_true_with_an_undefined_face(self):
        vertices, triangles = disconnected_triangles(2)
        vertices[5] = vertices[3] + [2., 0., 0.]
        session = FastSession(vertices, triangles)
        session.set_frame('a', deformed(vertices, {0: (1.5, .5)}))
        result = session.query(['a'])
        self.assertTrue(result['frames']['a']['mixed'])
        self.assertEqual(result['frames']['a']['states']['undefined'], 1)
        self.assertEqual(result['uncovered_labels'], [])

    def test_explicit_cross_frame_rows_keep_per_frame_membership(self):
        vertices, triangles = disconnected_triangles(2)
        session = FastSession(vertices, triangles)
        session.set_frame('rest', vertices)
        moved = vertices.copy()
        moved[:3, 0] += 20
        session.set_frame('moved', moved)
        result = session.query(['rest', 'moved'], bounds=[[-.1, -.1, -.1], [1.1, 1.1, .1]],
                               details=[0], max_witnesses=0)
        witness = result['witnesses'][0]
        self.assertTrue(witness['frames']['rest']['in_core'])
        self.assertFalse(witness['frames']['moved']['in_core'])
        np.testing.assert_allclose(witness['frames']['moved']['stretches'], [1., 1.])


if __name__ == '__main__':
    unittest.main()
