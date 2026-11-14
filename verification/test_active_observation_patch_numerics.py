"""Check split/join camera and vertex arithmetic without constructing a raster."""

import json
from pathlib import Path
import unittest

import numpy as np

from human_eye_plugin.active_observation import geometry
from human_eye_plugin.active_observation_host import freeze_cameras
from human_eye_plugin.active_observation_images import _meshes_from_objects


class ActiveObservationPatchNumericsTests(unittest.TestCase):
    def test_split_join_registered_matrices_and_projected_vertices_are_identical(self):
        inputs = Path(__file__).resolve().parent / 'm4_active_observation_patch_ownership_001/inputs'
        meshes, cameras = {}, {}
        for representation in ('split', 'joined'):
            scene = json.loads((inputs / (representation.upper() + '.json')).read_bytes())
            objects, _, _ = geometry(scene)
            meshes[representation] = _meshes_from_objects(objects)
            cameras[representation] = freeze_cameras(meshes[representation])
        self.assertEqual(cameras['split'], cameras['joined'])
        joined_vertices = meshes['joined'][0].vertices
        for pose in cameras['split']['views']:
            with self.subTest(view=pose['name']):
                view = np.asarray(pose['view_matrix'], dtype=np.float64)
                projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
                split_camera = np.concatenate([
                    mesh.vertices @ view[:3, :3].T + view[:3, 3]
                    for mesh in meshes['split']])
                joined_camera = joined_vertices @ view[:3, :3].T + view[:3, 3]
                np.testing.assert_array_equal(split_camera, joined_camera)
                split_ndc = np.concatenate([
                    (mesh.vertices @ view[:3, :3].T + view[:3, 3])
                    @ projection[:3, :3].T + projection[:3, 3]
                    for mesh in meshes['split']])
                joined_ndc = joined_camera @ projection[:3, :3].T + projection[:3, 3]
                np.testing.assert_array_equal(split_ndc, joined_ndc)


if __name__ == '__main__':
    unittest.main()
