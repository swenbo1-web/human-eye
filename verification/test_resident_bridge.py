"""Independent affine oracle and ownership checks for the RB-A array bridge."""

import unittest
import weakref

import numpy as np

from human_eye_fast.resident_bridge import ResidentBridge


_ARRAY_FIELDS = ("local_m", "world_m", "triangles", "world_from_local")


def _array_views(mesh):
    return tuple(getattr(mesh, field) for field in _ARRAY_FIELDS)


def _world_oracle(local_m, world_from_local):
    homogeneous = np.column_stack((local_m, np.ones(len(local_m))))
    return np.einsum("ij,nj->ni", world_from_local, homogeneous)[:, :3]


def _mesh_fixture():
    vertices = np.array([[0., 0., 0.], [2., 0., 1.], [0., 3., -1.], [1., 2., 4.]])
    triangles = np.array([[0, 1, 2], [2, 1, 3]], dtype=np.int32)
    transform = np.array([
        [0., -2., 0.25, 11.],
        [0.5, 0., 0., -2.],
        [0., 0.125, 1.5, 3.],
        [0., 0., 0., 1.],
    ])
    return vertices, triangles, transform


def _grid(side):
    row, column = np.indices((side, side))
    vertices = np.column_stack((column.ravel(), row.ravel(), (row * column).ravel()))
    vertices = np.ascontiguousarray(vertices, dtype=np.float64) / side**2
    corners = (row[:-1, :-1] * side + column[:-1, :-1]).ravel()
    triangles = np.empty((2 * len(corners), 3), dtype=np.int64)
    triangles[::2] = np.column_stack((corners, corners + 1, corners + side))
    triangles[1::2] = np.column_stack((corners + 1, corners + side + 1, corners + side))
    return vertices, triangles


class ResidentBridgeTests(unittest.TestCase):
    def assertMesh(self, mesh, local, triangles, transform):
        np.testing.assert_array_equal(mesh.local_m, local)
        np.testing.assert_array_equal(mesh.triangles, triangles)
        np.testing.assert_array_equal(mesh.world_from_local, transform)
        np.testing.assert_allclose(
            mesh.world_m, _world_oracle(local, transform), rtol=1e-12, atol=1e-12,
        )
        self.assertEqual(mesh.local_m.dtype, np.float64)
        self.assertEqual(mesh.world_m.dtype, np.float64)
        self.assertTrue(np.issubdtype(mesh.triangles.dtype, np.integer))
        for field in _ARRAY_FIELDS:
            self.assertFalse(getattr(mesh, field).flags.writeable, field)

    def test_two_grids_full_dirty_and_unchanged_reads(self):
        bridge = ResidentBridge()
        rng = np.random.default_rng(619)
        _, _, transform = _mesh_fixture()
        rigid = np.array([
            [0., 1., 0., -5.], [-1., 0., 0., 2.], [0., 0., 1., 8.], [0., 0., 0., 1.],
        ])
        fixtures = {"scan": (*_grid(100), rigid), 17: (*_grid(300), transform)}
        meshes = {object_id: bridge.add(object_id, *fixture) for object_id, fixture in fixtures.items()}
        views = {object_id: _array_views(mesh) for object_id, mesh in meshes.items()}
        expected = {object_id: fixture[0].copy() for object_id, fixture in fixtures.items()}
        self.assertEqual(len(bridge), 2)
        self.assertScene(bridge, fixtures, meshes, views, expected)

        for object_id, (local, _, _) in fixtures.items():
            with self.subTest(object_id=object_id):
                full = local + [0.125, -0.25, 0.5]
                self.assertIs(bridge.update_full(object_id, full), meshes[object_id])
                expected[object_id] = full.copy()
                full[:] = -500.
                self.assertScene(bridge, fixtures, meshes, views, expected)

                count = len(local) // 100
                indices = rng.choice(len(local), size=count, replace=False)
                self.assertTrue(np.any(np.diff(np.sort(indices)) > 1))
                before = expected[object_id][indices].copy()
                after = before + rng.uniform(0.01, 0.25, size=(count, 3))
                for state in (after, before, after):
                    incoming = state.copy()
                    self.assertIs(bridge.update_dirty(object_id, indices, incoming), meshes[object_id])
                    expected[object_id][indices] = state
                    incoming[:] = 500.
                    self.assertScene(bridge, fixtures, meshes, views, expected)

    def assertScene(self, bridge, fixtures, meshes, views, expected):
        for object_id, (_, triangles, transform) in fixtures.items():
            mesh = bridge.get(object_id)
            self.assertIs(mesh, meshes[object_id])
            self.assertSameViews(mesh, views[object_id])
            self.assertMesh(mesh, expected[object_id], triangles, transform)

    def assertSameViews(self, mesh, expected_views):
        for field, current, expected in zip(_ARRAY_FIELDS, _array_views(mesh), expected_views):
            self.assertIs(current, expected, field)

    def test_caller_converts_scene_units_and_transform_handles_large_translation(self):
        bridge = ResidentBridge()
        vertices_scene, triangles, transform_scene = _mesh_fixture()
        scale_length = 0.025
        local_m = vertices_scene * scale_length
        matrix_m = transform_scene.copy()
        matrix_m[:3, 3] *= scale_length
        mesh = bridge.add("assembly", local_m, triangles, matrix_m)
        views = _array_views(mesh)
        self.assertMesh(mesh, local_m, triangles, matrix_m)
        np.testing.assert_allclose(
            mesh.world_m, _world_oracle(vertices_scene, transform_scene) * scale_length,
            rtol=1e-12, atol=1e-12,
        )

        changed = matrix_m.copy()
        changed[:3, :3] = [[2., 0.25, -0.5], [0.125, -1.5, 0.], [0., 0.5, 3.]]
        changed[:3, 3] = [2e9, -3e9, 1e9]
        incoming = changed.copy()
        self.assertIs(bridge.update_transform("assembly", incoming), mesh)
        incoming[:3, :] = 0.
        self.assertIs(bridge.get("assembly"), mesh)
        self.assertSameViews(mesh, views)
        self.assertMesh(mesh, local_m, triangles, changed)
        without_translation = changed.copy()
        without_translation[:3, 3] = 0.
        displacement = _world_oracle(local_m, without_translation)
        np.testing.assert_allclose(
            mesh.world_m - changed[:3, 3], displacement, rtol=0., atol=5e-7,
        )

        local_m[2] += [0.5, -0.75, 1.25]
        self.assertIs(bridge.update_dirty("assembly", np.array([2]), local_m[[2]]), mesh)
        self.assertSameViews(mesh, views)
        self.assertMesh(mesh, local_m, triangles, changed)

    def test_add_owns_arrays_and_appearance_update_keeps_arrays(self):
        bridge = ResidentBridge()
        local, triangles, transform = _mesh_fixture()
        source = [array.copy() for array in (local, triangles, transform)]
        appearance = {"material": {"color": [0.2, 0.4, 0.6]}}
        original = bridge.add("paint", *source, appearance=appearance)
        views = _array_views(original)
        for field, incoming in zip(("local_m", "triangles", "world_from_local"), source):
            self.assertFalse(np.shares_memory(getattr(original, field), incoming), field)
            incoming[:] = 0
        appearance["material"]["color"][0] = 1.
        self.assertMesh(original, local, triangles, transform)
        self.assertEqual(original.appearance, {"material": {"color": [0.2, 0.4, 0.6]}})

        updated = {"material": {"color": [0.3, 0.6, 0.9]}}
        current = bridge.update_appearance("paint", updated)
        updated["material"]["color"][-1] = 1.
        self.assertIs(bridge.get("paint"), current)
        self.assertSameViews(current, views)
        self.assertMesh(current, local, triangles, transform)
        self.assertEqual(current.appearance, {"material": {"color": [0.3, 0.6, 0.9]}})

    def test_topology_replace_preserves_transform_appearance_and_other_object(self):
        bridge = ResidentBridge()
        local, triangles, transform = _mesh_fixture()
        before = bridge.add("target", local, triangles, transform, appearance="primer")
        other = bridge.add("other", local, triangles, transform)
        other_views = _array_views(other)
        new_local = np.vstack((local, [[5., -2., 1.]]))
        new_triangles = np.array([[4, 0, 2], [0, 1, 3], [2, 0, 3]], dtype=np.int32)
        source_local, source_triangles = new_local.copy(), new_triangles.copy()

        after = bridge.replace_topology("target", source_local, source_triangles)
        source_local[:] = 0.
        source_triangles[:] = 0
        self.assertIsNot(before, after)
        for field in ("local_m", "world_m", "triangles"):
            self.assertFalse(np.shares_memory(getattr(before, field), getattr(after, field)), field)
        self.assertEqual(after.appearance, "primer")
        self.assertMesh(after, new_local, new_triangles, transform)
        self.assertMesh(before, local, triangles, transform)
        self.assertIs(bridge.get("target"), after)
        self.assertIs(bridge.get("other"), other)
        self.assertSameViews(other, other_views)
        self.assertMesh(other, local, triangles, transform)

        # The added vertex uses the new buffer dimensions in subsequent dirty updates.
        new_local[-1] += [1., 2., 3.]
        bridge.update_dirty("target", np.array([4]), new_local[[-1]])
        self.assertMesh(after, new_local, new_triangles, transform)

    def test_remove_and_clear_drop_the_bridges_array_references(self):
        bridge = ResidentBridge()
        fixture = _mesh_fixture()
        first = bridge.add("first", *fixture)
        second = bridge.add("second", *fixture)
        first_array_refs = [weakref.ref(getattr(first, field)) for field in _ARRAY_FIELDS]
        second_array_refs = [weakref.ref(getattr(second, field)) for field in _ARRAY_FIELDS]
        del first, second

        bridge.remove("first")
        self.assertEqual(len(bridge), 1)
        with self.assertRaises(KeyError):
            bridge.get("first")
        self.assertTrue(all(ref() is None for ref in first_array_refs))
        self.assertTrue(all(ref() is not None for ref in second_array_refs))
        bridge.clear()
        self.assertEqual(len(bridge), 0)
        with self.assertRaises(KeyError):
            bridge.get("second")
        self.assertTrue(all(ref() is None for ref in second_array_refs))
        self.assertMesh(bridge.add("first", *fixture), *fixture)


if __name__ == "__main__":
    unittest.main()
