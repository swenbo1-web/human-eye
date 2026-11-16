"""Small data-only controls for the new saved checker, without product imports."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('saved_frames', HERE / 'saved_frames.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
np = checker.np


def minimal_source():
    views = [dict(name=name, direction_rational=direction, size_px=[512, 512], projection='orthographic',
                  view_matrix=np.eye(4).tolist(), projection_matrix=np.eye(4).tolist())
             for name, direction in zip(checker.ORDER, checker.DIRECTIONS)]
    capture = dict(capture_scope='complete_scene_meshes', revision='current-revision', unit='m',
                   coordinate_frame='world', source='blender',
                   host_identity=dict(capture_scope='complete_scene_meshes', document_epoch='a' * 64,
                                      object_instances={'actual-id': 'actual-instance'}),
                   capture_state=dict(instance_id='host-instance', epoch=1, revision=2, selection_key='scene'),
                   meshes=[dict(object_id='actual-id', name='Fixture')])
    binding = dict(schema='active-observation-host-source-v1', scene_revision=capture['revision'],
                   document_epoch=capture['host_identity']['document_epoch'], capture_scope=capture['capture_scope'],
                   unit='m', coordinate_frame='world', source='blender', capture_state=capture['capture_state'],
                   objects=[dict(object_index=0, host_id='actual-id', object_name='Fixture', instance_id='actual-instance')],
                   camera_policy={})
    binding['source_binding_sha256'] = checker.fingerprint(binding)
    binding['camera_specification'] = {'views': views}
    binding['geometry_identity'] = 'synthetic-data-only'
    binding['camera_identity'] = checker.fingerprint([{key: row[key] for key in (
        'name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')} for row in views])
    binding['binding_sha256'] = checker.fingerprint(binding)
    return capture, binding


class Checks(unittest.TestCase):
    def test_current_scope_and_source_pass(self):
        capture, binding = minimal_source()
        evidence = checker.Evidence()
        self.assertEqual(len(checker.source_binding_checks(capture, binding, evidence)), 6)

    def test_same_name_instance_replacement_rejected(self):
        capture, binding = minimal_source()
        capture['host_identity']['object_instances']['actual-id'] = 'replacement'
        with self.assertRaisesRegex(ValueError, 'actual_ordered_host_instance_mapping'):
            checker.source_binding_checks(capture, binding, checker.Evidence())

    def test_parent_scope_cannot_be_renamed(self):
        capture, binding = minimal_source()
        capture['capture_scope'] = 'selected_objects'
        with self.assertRaisesRegex(ValueError, 'parent_scope_preserved'):
            checker.source_binding_checks(capture, binding, checker.Evidence())

    def test_stale_revision_rejected(self):
        capture, binding = minimal_source()
        capture['revision'] = 'later-revision'
        with self.assertRaisesRegex(ValueError, 'current_capture_generation'):
            checker.source_binding_checks(capture, binding, checker.Evidence())

    def test_camera_identity_change_rejected(self):
        capture, binding = minimal_source()
        binding['camera_specification']['views'][0]['view_matrix'][0][3] = .25
        binding['binding_sha256'] = checker.fingerprint({key: value for key, value in binding.items() if key != 'binding_sha256'})
        with self.assertRaisesRegex(ValueError, 'published_camera_identity'):
            checker.source_binding_checks(capture, binding, checker.Evidence())

    def test_rgb_boundary_uses_patch_identity_and_inclusive_24(self):
        patches = np.asarray([[0, 1], [0, 1]], dtype=np.int32)
        rgb = np.zeros((2, 2, 3), dtype=np.uint8)
        rgb[:, 1, 0] = 24
        self.assertTrue(np.all(checker.contrasting_boundary(rgb, patches)))
        rgb[:, 1, 0] = 23
        self.assertFalse(np.any(checker.contrasting_boundary(rgb, patches)))
        self.assertFalse(np.any(checker.contrasting_boundary(rgb, np.zeros((2, 2), dtype=np.int32))))

    def test_pixel_locations_and_row_major_tie(self):
        mask = np.asarray([[True, False, True], [False, False, False]], dtype=bool)
        self.assertEqual(checker.pixel_location(mask), ([0, 0, 2, 0], [0, 0]))
        self.assertEqual(checker.pixel_location(np.zeros((2, 2), dtype=bool)), (None, None))

    def test_fraction_pixel_centres_and_outside_clipping(self):
        identity = np.eye(4).tolist()
        pose = dict(name='TOP', view_matrix=identity, projection_matrix=identity)
        vertices = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        result = checker.pixel_bbox_upper(vertices, [[0, 1, 2]], pose)
        self.assertEqual(result['dimensions'], [1, 1])
        self.assertEqual(result['pixel_center_bbox_upper'], 1)
        outside = [[4, 4, 0], [5, 4, 0], [4, 5, 0]]
        self.assertEqual(checker.pixel_bbox_upper(outside, [[0, 1, 2]], pose)['pixel_center_bbox_upper'], 0)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(schema='m4-global-local-saved-checker-pure-controls-v1', passed_checked_scope=result.wasSuccessful(),
                  tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  source_sha256=checker.sha(HERE / 'saved_frames.py'),
                  new_operations=dict(Blender=0, MCP=0, raster=0, model=0),
                  limitation='Data-only source/threshold/index controls. Actual frame evidence is evaluated after owned sessions close.')
    output = HERE / 'PURE_CHECKS.json'
    with output.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
