"""Reviewer-owned held-out checks for the first competition modules."""
import unittest

import numpy as np

from human_eye_fast.resident_bridge import ResidentBridge
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor


class ReviewerChecks(unittest.TestCase):
    def test_resident_sequence_against_einsum_world_oracle(self):
        rng = np.random.default_rng(97813)
        bridge = ResidentBridge()
        local = rng.normal(size=(193, 3))
        original = local.copy()
        triangles = rng.integers(0, 193, size=(211, 3))
        transform = np.eye(4)
        rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        transform[:3, :3] = rotation @ np.diag([.3, 1.7, -2.])
        transform[:3, 3] = [317., -.004, 61.]
        view = bridge.add('a', local, triangles, transform)
        other = bridge.add('b', local * 2., triangles, np.eye(4))
        other_before = other.world_m.copy()
        local[:] = -900.
        np.testing.assert_array_equal(view.local_m, original)
        indices = rng.choice(len(original), 17, replace=False)
        original[indices] += rng.normal(size=(17, 3)) * .03
        bridge.update_dirty('a', indices, original[indices])
        expected = np.einsum('ij,nj->ni', transform[:3, :3], original) + transform[:3, 3]
        np.testing.assert_allclose(view.world_m, expected, rtol=1e-12, atol=1e-12)
        self.assertIs(bridge.get('a'), view)
        np.testing.assert_array_equal(other.world_m, other_before)
        transform[:3, 3] += [.2, -11., 18.]
        bridge.update_transform('a', transform)
        expected = np.einsum('ij,nj->ni', transform[:3, :3], original) + transform[:3, 3]
        np.testing.assert_allclose(view.world_m, expected, rtol=1e-12, atol=1e-12)
        original *= 1.3
        bridge.update_full('a', original)
        expected = np.einsum('ij,nj->ni', transform[:3, :3], original) + transform[:3, 3]
        np.testing.assert_allclose(view.world_m, expected, rtol=1e-12, atol=1e-12)
        bridge.remove('a')
        self.assertEqual(len(bridge), 1)
        np.testing.assert_array_equal(bridge.get('b').world_m, other_before)
        bridge.clear()
        self.assertEqual(len(bridge), 0)

    def test_deformation_held_out_qr_svd_and_geometric_oracle(self):
        rng = np.random.default_rng(49787)
        reference = rng.normal(size=(39, 3))
        faces = np.arange(39).reshape(-1, 3)
        frames = []
        for _ in range(7):
            rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
            frames.append(reference @ (rotation @ np.diag(rng.uniform(.4, 1.8, 3))).T
                          + rng.normal(size=(39, 3)) * .02)
        frames = np.stack(frames)
        result = compute_cross_frame_deformation_tensor(
            frames, faces, reference_vertices=reference, top_k=7)
        expected = {k: [] for k in ('max_principal_stretch', 'min_principal_stretch',
                                    'max_area_strain', 'max_normal_angle_deg',
                                    'max_centroid_displacement')}
        for face in faces:
            p = reference[face]
            basis = np.column_stack((p[1] - p[0], p[2] - p[0]))
            _, chart = np.linalg.qr(basis, mode='reduced')
            n0 = np.cross(basis[:, 0], basis[:, 1])
            area0 = np.linalg.norm(n0)
            n0 /= area0
            stretches, areas, angles, displacements = [], [], [], []
            for frame in frames:
                q = frame[face]
                edges = np.column_stack((q[1] - q[0], q[2] - q[0]))
                gradient = np.linalg.solve(chart.T, edges.T).T
                stretches.append(np.linalg.svd(gradient, compute_uv=False))
                n1 = np.cross(edges[:, 0], edges[:, 1])
                area1 = np.linalg.norm(n1)
                n1 /= area1
                areas.append(abs(area1 / area0 - 1))
                angles.append(np.degrees(np.arctan2(np.linalg.norm(np.cross(n0, n1)), n0 @ n1)))
                displacements.append(np.linalg.norm(q.mean(axis=0) - p.mean(axis=0)))
            expected['max_principal_stretch'].append(max(x[0] for x in stretches))
            expected['min_principal_stretch'].append(min(x[1] for x in stretches))
            expected['max_area_strain'].append(max(areas))
            expected['max_normal_angle_deg'].append(max(angles))
            expected['max_centroid_displacement'].append(max(displacements))
        for name, values in expected.items():
            np.testing.assert_allclose(result[name], values, rtol=1e-11, atol=1e-11)
        expected_ids = np.lexsort((np.arange(len(faces)), -result['score']))[:7]
        np.testing.assert_array_equal(result['witness_triangle_ids'], expected_ids)

    def test_deformation_scale_invariant_ranking(self):
        rng = np.random.default_rng(61847)
        reference = rng.normal(size=(60, 3))
        faces = np.arange(60).reshape(-1, 3)
        frames = np.stack([reference + rng.normal(size=reference.shape) * .07 for _ in range(4)])
        base = compute_cross_frame_deformation_tensor(frames, faces, reference_vertices=reference)
        for scale in (1e-7, 1e8):
            scaled = compute_cross_frame_deformation_tensor(
                frames * scale, faces, reference_vertices=reference * scale)
            for key in ('max_principal_stretch', 'min_principal_stretch',
                        'max_area_strain', 'max_normal_angle_deg', 'score'):
                np.testing.assert_allclose(scaled[key], base[key], rtol=1e-10, atol=1e-10)
            np.testing.assert_allclose(scaled['max_centroid_displacement'] / scale,
                                       base['max_centroid_displacement'], rtol=1e-10, atol=1e-10)
            np.testing.assert_array_equal(scaled['witness_triangle_ids'], base['witness_triangle_ids'])

    def test_bridge_to_deformation_snapshots_preserve_rigid_motion(self):
        reference = np.array([[0., 0, 0], [1., 0, 0], [0., 1., 0]])
        faces = np.array([[0, 1, 2]])
        bridge = ResidentBridge()
        bridge.add('triangle', reference, faces, np.eye(4))
        before = bridge.get('triangle').world_m.copy()
        rotation = np.diag([1., -1., -1., 1.])
        bridge.update_transform('triangle', rotation)
        after = bridge.get('triangle').world_m.copy()
        result = compute_cross_frame_deformation_tensor(np.stack((before, after)), faces)
        np.testing.assert_allclose(result['max_principal_stretch'], 1.)
        np.testing.assert_allclose(result['min_principal_stretch'], 1.)
        np.testing.assert_allclose(result['max_area_strain'], 0.)
        np.testing.assert_allclose(result['max_normal_angle_deg'], 180.)
        self.assertNotIn('flipped_face_ids', result)


if __name__ == '__main__':
    unittest.main()
