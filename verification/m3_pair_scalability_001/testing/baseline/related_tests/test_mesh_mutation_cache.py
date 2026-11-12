"""Mutation/cache regressions against independently constructed fresh meshes.

These tests create only in-memory meshes. Public array mutation remains a
supported compatibility input; cached geometry must not hide that input.
"""
import copy
import unittest

import numpy as np

import human_eye_foveated_renderer as renderer
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import SpatialAnomalySniffer


# The phase runner can substitute the frozen baseline class without patching
# the imported product module or a live host. The normal suite uses live code.
MESH_CLASS = renderer.MeshEntity3D
ADJACENCY_CLASS = renderer.SphericalIoRMultiLocusSniffer


def make_mesh(count=196, *, dtype=np.float64):
    vertices = np.array([[i % 14, i // 14, 0.] for i in range(count)], dtype=dtype)
    faces = []
    for a in range(count):
        if a % 14 == 13:
            continue
        if a + 14 < count:
            faces.append([a, a + 14, a + 1])
        if a + 15 < count:
            faces.append([a + 1, a + 14, a + 15])
    return MESH_CLASS('cache-test', '#T', 'in-memory cache test', vertices,
        np.array(faces, dtype=np.int32), np.empty((0, 2), dtype=np.int32),
        (70, 100, 130), local_axes=np.eye(3), pivot_world=np.array([.3, .4, .5]))


def fresh_copy(mesh):
    return MESH_CLASS(mesh.object_id, mesh.mark_label, mesh.name,
        mesh.vertices.copy(), mesh.faces.copy(), mesh.edges.copy(), tuple(mesh.color_rgb),
        mesh.is_focal_target, mesh.local_axes.copy(), mesh.pivot_world.copy(),
        mesh.axes_source, mesh.axes_confidence, mesh.axes_reason)


def tree(mesh, primitive='faces'):
    return SpatialAnomalySniffer.build_lbvh_morton_tree(mesh, primitive_type=primitive)


class MeshMutationCacheTests(unittest.TestCase):
    def assert_geometry_matches_fresh(self, mesh):
        fresh = fresh_copy(mesh)
        for field in ('bbox_min', 'bbox_max', 'aabb_center', 'face_normals', 'face_centroids'):
            np.testing.assert_allclose(getattr(mesh, field), getattr(fresh, field),
                rtol=0, atol=1e-12, err_msg=field)
        for field in ('tri_vertices', 'edge_vertices', 'triangle_aabb_bounds', 'edge_aabb_bounds'):
            for actual, expected in zip(getattr(mesh, field), getattr(fresh, field)):
                np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12, err_msg=field)
        for primitive in ('faces', 'edges'):
            actual, expected = tree(mesh, primitive), tree(fresh, primitive)
            for field in ('order', 'prim_min', 'prim_max', 'micro_min', 'micro_max',
                          'macro_min', 'macro_max', 'root_min', 'root_max'):
                np.testing.assert_allclose(getattr(actual, field), getattr(expected, field),
                    rtol=0, atol=1e-12, err_msg=primitive + ':' + field)
            for lower, upper in (([2., 0., -.1], [4., 2., 11.]),
                                  ([-1., -1., -1.], [20., 20., 20.]),
                                  ([100., 100., 100.], [101., 101., 101.])):
                args = np.array(lower), np.array(upper), 0.
                query = SpatialAnomalySniffer.query_lbvh_active_primitives
                np.testing.assert_array_equal(query(mesh, *args, primitive_type=primitive),
                    query(fresh, *args, primitive_type=primitive))

    @staticmethod
    def warm(mesh):
        for field in ('bbox_min', 'bbox_max', 'aabb_center', 'tri_vertices', 'edge_vertices',
                      'face_normals', 'face_centroids', 'triangle_aabb_bounds', 'edge_aabb_bounds'):
            getattr(mesh, field)
        return tree(mesh), tree(mesh, 'edges')

    def test_nonanchor_vertex_edit_rebuilds_complete_lbvh(self):
        mesh = make_mesh()
        before, _ = self.warm(mesh)
        mesh.vertices[17, 2] = 10.
        after = tree(mesh)
        self.assertEqual(after.root_max[2], 10.)
        self.assertIsNot(after, before)
        self.assertEqual(before.root_max[2], 0.)
        self.assert_geometry_matches_fresh(mesh)

    def test_128_and_129_vertex_boundary_has_same_mutation_semantics(self):
        for size in (128, 129):
            with self.subTest(vertices=size):
                mesh = make_mesh(size)
                self.warm(mesh)
                mesh.vertices[17, 2] = 10.
                self.assert_geometry_matches_fresh(mesh)

    def test_each_nonanchor_coordinate_change_is_visible(self):
        for coordinate in range(3):
            with self.subTest(coordinate=coordinate):
                mesh = make_mesh()
                self.warm(mesh)
                mesh.vertices[17, coordinate] += 30.
                self.assert_geometry_matches_fresh(mesh)

    def test_explicit_invalidation_drops_both_tree_caches_without_geometry_change(self):
        mesh = make_mesh()
        before_face, before_edge = self.warm(mesh)
        mesh.invalidate_caches()
        self.assertIsNot(tree(mesh), before_face)
        self.assertIsNot(tree(mesh, 'edges'), before_edge)
        self.assert_geometry_matches_fresh(mesh)

    def test_explicit_invalidation_after_nonanchor_edit_does_not_reuse_old_tree(self):
        mesh = make_mesh()
        before = tree(mesh)
        mesh.vertices[17, 2] = 10.
        mesh.invalidate_caches()
        after = tree(mesh)
        self.assertEqual(after.root_max[2], 10.)
        self.assertIsNot(after, before)
        self.assert_geometry_matches_fresh(mesh)

    def test_faces_content_edit_with_same_shape_recomputes_geometry(self):
        mesh = make_mesh()
        self.warm(mesh)
        mesh.faces[0] = [5, 18, 19]
        self.assert_geometry_matches_fresh(mesh)

    def test_edges_content_edit_with_same_shape_recomputes_edge_tree(self):
        mesh = make_mesh()
        self.warm(mesh)
        mesh.edges[0] = [17, 190]
        self.assert_geometry_matches_fresh(mesh)

    def test_same_shape_topology_edit_refreshes_real_adjacency_consumer(self):
        mesh = make_mesh()
        before = ADJACENCY_CLASS._get_vertex_adj_faces_list(mesh)
        self.assertIn(0, before[0])
        mesh.faces[0] = [5, 18, 19]
        actual = ADJACENCY_CLASS._get_vertex_adj_faces_list(mesh)
        expected = ADJACENCY_CLASS._get_vertex_adj_faces_list(fresh_copy(mesh))
        self.assertNotIn(0, actual[0])
        for a, b in zip(actual, expected):
            np.testing.assert_array_equal(a, b)

    def test_axis_edit_outside_old_sample_is_part_of_coherency(self):
        mesh = make_mesh()
        before = mesh._check_coherency()
        mesh.local_axes[0, 1] = .125
        after = mesh._check_coherency()
        self.assertNotEqual(before, after)
        np.testing.assert_array_equal(mesh.translated((0., 0., 1.)).local_axes, mesh.local_axes)

    def test_explicit_invalidation_clears_external_geometry_cache_families(self):
        mesh = make_mesh()
        names = ('_cached_tri_metric', '_cached_edge_metric', '_cached_lbvh_faces',
                 '_cached_lbvh_edges', '_cached_curvatures', '_cached_vert_adj_faces',
                 '_cached_extra_sat_axes', '_cached_unique_halfspaces')
        for name in names:
            setattr(mesh, name, ('previous-generation derived geometry',))
        mesh.invalidate_caches()
        for name in names:
            with self.subTest(cache=name):
                self.assertIsNone(getattr(mesh, name, None))

    def test_vertex_replacement_with_same_shape_refreshes_all_geometry(self):
        mesh = make_mesh()
        self.warm(mesh)
        replacement = mesh.vertices.copy()
        replacement[17, 2] = 10.
        mesh.vertices = replacement
        self.assert_geometry_matches_fresh(mesh)

    def test_noncontiguous_vertex_replacement_preserves_correct_geometry(self):
        mesh = make_mesh()
        self.warm(mesh)
        backing = np.zeros((len(mesh.vertices), 6), dtype=np.float64)
        backing[:, ::2] = mesh.vertices
        mesh.vertices = backing[:, ::2]
        self.assertFalse(mesh.vertices.flags.c_contiguous)
        mesh.vertices[17, 2] = 10.
        self.assert_geometry_matches_fresh(mesh)

    def test_float32_replacement_normalizes_without_stale_tree(self):
        mesh = make_mesh()
        self.warm(mesh)
        mesh.vertices = mesh.vertices.astype(np.float32)
        mesh.vertices[17, 2] = 10.
        self.assert_geometry_matches_fresh(mesh)
        self.assertEqual(mesh.vertices.dtype, np.float64)

    def test_translated_child_lazy_geometry_is_bound_to_its_own_vertices(self):
        parent = make_mesh()
        child = parent.translated((.3, .2, 1.))
        own_vertices = child.vertices.copy()
        parent.vertices[17, 2] = 10.
        self.assert_geometry_matches_fresh(child)
        np.testing.assert_array_equal(child.vertices, own_vertices)

    def test_translated_child_warm_geometry_stays_valid_after_parent_edit(self):
        parent = make_mesh()
        child = parent.translated((.3, .2, 1.))
        self.warm(child)
        parent.vertices[17, 2] = 10.
        self.assert_geometry_matches_fresh(child)

    def test_rotation_child_does_not_borrow_changed_parent_geometry(self):
        parent = make_mesh()
        self.warm(parent)
        angle = .2
        matrix = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0],
                           [-np.sin(angle), 0, np.cos(angle)]])
        child = parent.rotated_around_pivot(matrix)
        parent.vertices[17, 2] = 10.
        self.assert_geometry_matches_fresh(child)

    def test_unchanged_mesh_still_reuses_face_and_edge_tree(self):
        mesh = make_mesh()
        a, b = self.warm(mesh)
        self.assertIs(tree(mesh), a)
        self.assertIs(tree(mesh, 'edges'), b)
        self.assert_geometry_matches_fresh(mesh)

    def test_compatibility_and_full_token_gate_agree_for_large_mesh(self):
        mesh = make_mesh()
        self.assertEqual(mesh._check_coherency(), mesh._compute_full_crc_token())
        mesh.vertices[17, 2] = 10.
        self.assertEqual(mesh._check_coherency(), mesh._compute_full_crc_token())

    def test_changed_vertex_updates_cached_curvature_against_fresh_mesh(self):
        mesh = make_mesh()
        function = SpatialAnomalySniffer.estimate_local_principal_curvatures_and_gauss_bonnet
        function(mesh)
        mesh.vertices[17, 2] = .25
        actual, expected = function(mesh), function(fresh_copy(mesh))
        for a, b in zip(actual, expected):
            np.testing.assert_allclose(a, b, rtol=0, atol=1e-12)

