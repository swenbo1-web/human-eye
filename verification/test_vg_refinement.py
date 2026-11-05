"""Native unit/camera and encoder-resource regressions outside timing runs."""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from human_eye_fast.blender_resident_bridge import BlenderResidentBridge
from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
from human_eye_fast.raycast_saccade_gpu import VGRenderer
from verification.test_raycast_saccade_gpu import SceneOracle, score_observation
from verification.vg_fixtures import build_fixture


class NativeRefinement(unittest.TestCase):
    def test_work_buffers_and_explicit_release(self):
        renderer = VGRenderer()
        try:
            allocations = [renderer.scanlines, renderer.rgb, renderer.previous_row]
            self.assertEqual(sum(array.nbytes for array in allocations), 1773056)
            self.assertLess(sum(array.nbytes for array in allocations), 1024 * 512 * 4)
            self.assertTrue(renderer.rgb_deltas.base is renderer.scanlines)
        finally:
            renderer.close()
        self.assertTrue(all(getattr(renderer, name) is None for name in
                            ('scanlines', 'rgb_deltas', 'rgb', 'previous_row')))

    def test_actual_nonunit_natural_and_section_images(self):
        renderer = VGRenderer()
        try:
            for scene_id, units in ((4, .01), (20, 10.)):
                with self.subTest(scene=scene_id, units=units):
                    fixture = build_fixture(scene_id)
                    try:
                        scene = fixture.scene
                        scene.unit_settings.scale_length = units
                        scale = scene.unit_settings.scale_length
                        for obj in fixture.objects.values():
                            obj.scale /= scale
                        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                            graph = bpy.context.evaluated_depsgraph_get()
                            graph.update()
                            bridge = BlenderResidentBridge()
                            meshes = {key: bridge.capture(key, obj, graph, scale)
                                      for key, obj in fixture.objects.items()}
                        indexes = [SurfaceIndex(meshes[key].world_m, meshes[key].triangles)
                                   for key in fixture.target_ids]
                        witness = surface_distance(*indexes)
                        fixture = replace(fixture, scale_length=scale, meshes=meshes, witness=witness)
                        prepared = renderer.prepare(meshes)
                        oracle = SceneOracle(fixture)
                        observation = renderer.observe(
                            prepared, witness, target_ids=fixture.target_ids, frame_id=fixture.frame_id,
                            scale_length=scale, mode=fixture.mode, audit=True)
                        score = score_observation(fixture, observation, oracle=oracle, baseline=False)
                        self.assertTrue(score['passed'], [key for key, passed in score['checks'].items()
                                                          if not passed])
                    finally:
                        fixture.close()
        finally:
            renderer.close()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeRefinement))
    if not result.wasSuccessful():
        raise RuntimeError('VG native refinement checks failed')
