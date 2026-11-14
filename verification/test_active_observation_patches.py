"""Exact planar-patch discovery and same-object occlusion, without rasterization."""

import copy
from fractions import Fraction
import hashlib
import json
import unittest

from human_eye_plugin.active_observation import geometry, partition_regions, prepare_scene


def rectangle_mesh(name='Panel', *, z=0, x=0, segments=1, removed_cell=None):
    vertices = [[Fraction(i, segments) + x, Fraction(j, segments), z]
                for j in range(segments + 1) for i in range(segments + 1)]
    faces = []
    for j in range(segments):
        for i in range(segments):
            if (i, j) == removed_cell:
                continue
            a = j * (segments + 1) + i
            b, c = a + 1, a + segments + 1
            d = c + 1
            faces.extend([[a, b, d], [a, d, c]])
    return {'name': name, 'vertices': vertices, 'triangles': faces}


def joined_mesh(*meshes):
    vertices, faces = [], []
    for mesh in meshes:
        offset = len(vertices)
        vertices.extend(copy.deepcopy(mesh['vertices']))
        faces.extend([[index + offset for index in face] for face in mesh['triangles']])
    return {'name': 'Joined patches', 'vertices': vertices, 'triangles': faces}


def partition(*meshes):
    objects, _, _ = geometry({'objects': list(meshes)})
    return partition_regions(objects)


def box_mesh():
    return {'name': 'Box', 'vertices': [
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
    ], 'triangles': [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2],
        [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5],
    ]}


def camera_pool():
    return {'views': [{
        'name': 'SCENE', 'direction_rational': [0, 0, 1],
        'target_to_eye_unit': [0, 0, 1], 'size_px': [512, 512],
        'view_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -3], [0, 0, 0, 1]],
        'projection_matrix': [[Fraction(1, 2), 0, 0, 0], [0, Fraction(1, 2), 0, 0],
                              [0, 0, Fraction(1, 5), 0], [0, 0, 0, 1]],
    }]}


class ActiveObservationPatchTests(unittest.TestCase):
    def assert_complete_partition(self, scope):
        for row in scope:
            supported = list(row['supported_triangle_indices'])
            unsupported = [index for component in row['unsupported_components']
                           for index in component['triangle_indices']]
            self.assertEqual(len(supported), row['supported_triangle_count'])
            self.assertEqual(len(unsupported), row['unsupported_triangle_count'])
            self.assertEqual(sorted(supported + unsupported), list(range(row['source_triangle_count'])))

    def test_single_rectangle_identity_survives_subdivision(self):
        plain, _ = partition(rectangle_mesh())
        divided, scope = partition(rectangle_mesh(segments=4))
        quad = (('0', '0', '0'), ('1', '0', '0'), ('1', '1', '0'), ('0', '1', '0'))
        expected = 'roi_' + hashlib.sha256(json.dumps(
            quad, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
        self.assertEqual([row.roi_id for row in plain], [expected])
        self.assertEqual([row.roi_id for row in divided], [expected])
        self.assertEqual(divided[0].normal, (0, 0, 1))
        self.assertEqual(divided[0].triangle_indices, tuple(range(32)))
        self.assert_complete_partition(scope)

    def test_box_exposes_six_maximal_rectangles(self):
        regions, scope = partition(box_mesh())
        self.assertEqual(len(regions), 6)
        self.assertEqual({region.normal for region in regions}, {
            (4, 0, 0), (-4, 0, 0), (0, 4, 0), (0, -4, 0), (0, 0, 4), (0, 0, -4),
        })
        self.assertTrue(all(len(region.triangle_indices) == 2 for region in regions))
        self.assertEqual(scope[0]['supported_triangle_count'], 12)
        self.assertEqual(scope[0]['unsupported_triangle_count'], 0)
        self.assert_complete_partition(scope)

    def test_disconnected_planes_and_partial_unknown_share_one_object(self):
        triangle = {'vertices': [[3, 0, 0], [4, 0, 0], [3, 1, 0]], 'triangles': [[0, 1, 2]]}
        degenerate = {'vertices': [[6, 0, 0], [7, 0, 0], [8, 0, 0]], 'triangles': [[0, 1, 2]]}
        mesh = joined_mesh(rectangle_mesh(), rectangle_mesh(z=1), triangle, degenerate)
        regions, scope = partition(mesh)
        self.assertEqual(len(regions), 2)
        self.assertEqual(scope[0]['supported_triangle_count'], 4)
        self.assertEqual(scope[0]['unsupported_triangle_count'], 2)
        self.assertEqual({row['reason'] for row in scope[0]['unsupported_components']},
                         {'insufficient_faces', 'degenerate_triangle'})
        self.assert_complete_partition(scope)

    def test_hole_and_nonrectangular_component_are_not_completed(self):
        cases = [(3, (1, 1), 'multiple_boundary_cycles'),
                 (2, (1, 1), 'four_corners_required')]
        for segments, removed, reason in cases:
            with self.subTest(segments=segments):
                regions, scope = partition(rectangle_mesh(segments=segments, removed_cell=removed))
                self.assertEqual(regions, ())
                self.assertEqual(scope[0]['unsupported_components'][0]['reason'], reason)
                self.assert_complete_partition(scope)

    def test_bad_winding_rejects_maximal_plane_without_salvaging_pieces(self):
        broken = rectangle_mesh(segments=2)
        broken['triangles'][0].reverse()
        regions, scope = partition(joined_mesh(broken, rectangle_mesh(x=3)))
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].triangle_indices, (8, 9))
        rejected = scope[0]['unsupported_components']
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]['triangle_indices'], tuple(range(8)))
        self.assertEqual(rejected[0]['reason'], 'inconsistent_shared_edge_winding')
        self.assert_complete_partition(scope)

    def test_nonmanifold_edge_preserves_only_independent_legal_patch(self):
        broken = rectangle_mesh()
        broken['vertices'].append([2, 0, 1])
        broken['triangles'].append([0, 3, 4])
        regions, scope = partition(joined_mesh(broken, rectangle_mesh(x=3)))
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].triangle_indices, (3, 4))
        self.assertEqual({row['reason'] for row in scope[0]['unsupported_components']}, {'nonmanifold_edge'})
        self.assert_complete_partition(scope)

    def test_exact_nonplanar_quad_is_not_snapped_to_a_rectangle(self):
        mesh = rectangle_mesh()
        mesh['vertices'][3][2] = Fraction(1, 2 ** 40)
        regions, scope = partition(mesh)
        self.assertEqual(regions, ())
        self.assertEqual(scope[0]['unsupported_triangle_count'], 2)
        self.assert_complete_partition(scope)

    def test_object_vertex_and_triangle_reordering_preserve_geometric_ids(self):
        first, second = rectangle_mesh(segments=2), rectangle_mesh(z=1)
        original, _ = partition(first, second)
        changed = copy.deepcopy(first)
        changed['name'] = 'A different name'
        count = len(changed['vertices'])
        changed['vertices'].reverse()
        changed['triangles'] = [[count - 1 - index for index in face[1:] + face[:1]]
                                for face in reversed(changed['triangles'])]
        reordered, scope = partition(second, changed)
        self.assertEqual([region.roi_id for region in reordered], [region.roi_id for region in original])
        combined, joined_scope = partition(joined_mesh(changed, second))
        self.assertEqual([region.roi_id for region in combined], [region.roi_id for region in original])
        self.assert_complete_partition(scope)
        self.assert_complete_partition(joined_scope)

    def test_same_object_foreground_occludes_back_rectangle(self):
        back, front = rectangle_mesh(z=0), rectangle_mesh(z=1)
        joined = prepare_scene({'objects': [joined_mesh(back, front)]}, camera_pool())
        separate = prepare_scene({'objects': [back, front]}, camera_pool())
        self.assertEqual(joined.index.region_ids, separate.index.region_ids)
        self.assertNotEqual(joined.scene_identity, separate.scene_identity)
        self.assertEqual(joined.index.classifications, separate.index.classifications)
        regions = {region.vertices[0][2]: region for region in joined.regions}
        rows = joined.index.classifications['SCENE']
        self.assertEqual(rows[regions[0].roi_id]['status'], 'positive_area_occlusion')
        self.assertIs(rows[regions[0].roi_id]['complete'], False)
        self.assertEqual(rows[regions[1].roi_id]['status'], 'complete')
        self.assertIs(rows[regions[1].roi_id]['complete'], True)
        self.assertEqual(len(joined.index.ids(joined.index.view_masks['SCENE'])), 1)
        self.assert_complete_partition(joined.index.patch_scope)


if __name__ == '__main__':
    unittest.main()
