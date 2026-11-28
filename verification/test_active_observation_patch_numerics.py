"""Check split/join camera and vertex arithmetic without constructing a raster."""

import hashlib
import json
from pathlib import Path
import unittest

import numpy as np

from human_eye_plugin.active_observation import geometry
from human_eye_plugin.active_observation_host import freeze_cameras
from human_eye_plugin.active_observation_images import _meshes_from_objects


class ActiveObservationPatchNumericsTests(unittest.TestCase):
    def test_split_join_registered_matrices_and_projected_vertices_are_identical(self):
        inputs = Path(__file__).resolve().parent / 'fixtures/observation_patches'
        split = json.loads((inputs / 'SPLIT.json').read_bytes())
        joined_object = {'name': 'QA_Joined', 'vertices': [], 'triangles': []}
        for part in split['objects']:
            offset = len(joined_object['vertices'])
            joined_object['vertices'].extend(part['vertices'])
            joined_object['triangles'].extend([[i + offset for i in face] for face in part['triangles']])
        joined = {**split, 'objects': [joined_object]}
        # Reproduce the original independent fixture without storing its coordinates twice.
        encoded = (json.dumps(joined, sort_keys=True, indent=2) + '\n').encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         'e55cea85cae85dd11a7c533deda20f2162eb60256d82d056973d0cc6305ec3cd')
        meshes, cameras = {}, {}
        for representation, scene in [('split', split), ('joined', joined)]:
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
