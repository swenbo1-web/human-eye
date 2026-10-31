"""Analytical sections preserve natural pixels and cannot grant authority."""
import base64
import copy
import io
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.contact_section import append_contact_section
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA
from verification.test_auto_router import box, observation, action
from verification.test_attention_rendering import near_scene


def section_fixture(gap=.002, extra=(), offset=(0., 0., 0.), scale=1.):
    shift = np.array(offset)
    items = [box('base', shift + np.array([0, 0, -.05]) * scale, np.array([1., .4, .1])*scale),
             box('part', shift + np.array([0, 0, .05+gap])*scale, np.array([.3, .2, .1])*scale, True)]
    items += list(extra)
    meshes = [MeshEntity3D.from_dict(value) for value in items]
    measured = dict(measurement_kind='exact', clearance_exact=True, measurement_valid=True,
        signed_clearance_m=gap*scale, point_a_world=(shift + [0, 0, gap*scale]).tolist(),
        point_b_world=shift.tolist())
    return meshes, measured


def picture(result):
    return Image.open(io.BytesIO(base64.b64decode(result['image']['data']))).convert('RGB')


class ContactSectionTests(unittest.TestCase):
    def draw(self, meshes, measured, canvas=None):
        canvas = canvas or Image.new('RGB', (256, 256), (17, 31, 47))
        return append_contact_section(canvas, meshes, measured, focal_id='part', reference_id='base', quad_size=128)

    def test_two_mm_section_has_analytical_boundaries_and_original_pixels(self):
        meshes, measured = section_fixture()
        original = Image.new('RGB', (256, 256), (17, 31, 47))
        before = [copy.deepcopy(mesh.to_dict()) for mesh in meshes]
        output, evidence = self.draw(meshes, measured, original)
        np.testing.assert_array_equal(np.asarray(output)[:, :256], np.asarray(original))
        self.assertEqual(output.size, (448, 256))
        self.assertEqual(evidence['participating_object_ids'], ['base', 'part'])
        rows = {item['object_id']: item for item in evidence['objects']}
        base_y = [p[1] for segment in rows['base']['viewport_segments_plane_m'] for p in segment]
        part_y = [p[1] for segment in rows['part']['viewport_segments_plane_m'] for p in segment]
        self.assertAlmostEqual(max(base_y), -.001)
        self.assertAlmostEqual(min(part_y), .001)
        self.assertAlmostEqual((min(part_y)-max(base_y))/evidence['m_per_pixel'], 12.)
        self.assertEqual(before, [mesh.to_dict() for mesh in meshes])
        for key in ('natural_visibility_certified', 'free_path_certified', 'execution_authority',
                    'independent_ground_truth', 'annotations_count_as_evidence'):
            self.assertIs(evidence[key], False)
        json.dumps(evidence, allow_nan=False)

    def test_fifty_micrometre_section_retains_world_units(self):
        meshes, measured = section_fixture(gap=50e-6)
        _, evidence = self.draw(meshes, measured)
        self.assertAlmostEqual(evidence['measured_clearance_m'], 50e-6)
        self.assertAlmostEqual(evidence['m_per_pixel'] * 12, 50e-6)
        self.assertEqual(evidence['scope'], 'local_analytical_wire_section_not_natural_visibility_or_solid_classification')

    def test_translation_and_scale_preserve_independent_plane_geometry(self):
        for offset, scale in (((12., -7., 3.), 1.), ((10000., 300., -20.), 10.)):
            with self.subTest(offset=offset, scale=scale):
                meshes, measured = section_fixture(offset=offset, scale=scale)
                _, evidence = self.draw(meshes, measured)
                origin = np.array(evidence['plane_origin_world_m'])
                self.assertTrue(np.allclose(origin, np.array(offset) + [0, 0, .001*scale], rtol=0, atol=1e-10))
                horizontal, vertical, normal = [np.array(evidence[key]) for key in (
                    'horizontal_basis_world', 'vertical_basis_world', 'plane_normal_world')]
                self.assertAlmostEqual(abs(np.linalg.det(np.stack((horizontal, vertical, normal)))), 1.)
                for row in evidence['objects']:
                    for segment in row['viewport_segments_plane_m']:
                        for point in segment:
                            world = origin + point[0]*horizontal + point[1]*vertical
                            self.assertAlmostEqual(float((world-origin) @ normal), 0., places=9)
                self.assertAlmostEqual(evidence['m_per_pixel'], .002*scale/12.)

    def test_third_obstacle_is_intersected_even_inside_measured_pair_gap(self):
        blocker = box('blocker', [0, 0, .001], [.2, .2, .0005])
        meshes, measured = section_fixture(extra=[blocker])
        _, evidence = self.draw(meshes, measured)
        row = next(item for item in evidence['objects'] if item['object_id'] == 'blocker')
        self.assertGreater(row['visible_segment_count'], 0)
        self.assertFalse(evidence['free_path_certified'])

    def test_nonintersecting_object_is_reported_instead_of_omitted(self):
        meshes, measured = section_fixture(extra=[box('off-plane', [0, 10, 0], [.1, .1, .1])])
        _, evidence = self.draw(meshes, measured)
        self.assertIn('off-plane', evidence['participating_object_ids'])
        row = next(item for item in evidence['objects'] if item['object_id'] == 'off-plane')
        self.assertEqual(row['intersection_segment_count'], 0)

    def test_coplanar_triangles_and_degenerate_faces_are_disclosed(self):
        meshes, measured = section_fixture()
        triangle = MeshEntity3D.from_dict(box('coplanar', [0, 0, .005], [.1, .1, .001]))
        triangle.vertices[:, 1] = 0
        meshes.append(triangle)
        _, evidence = self.draw(meshes, measured)
        row = evidence['objects'][-1]
        self.assertGreater(row['coplanar_triangle_count'], 0)
        self.assertGreater(row['degenerate_triangle_count'], 0)
        self.assertIn('not_solid_boundary', evidence['coplanar_policy'])

    def test_contact_penetration_unknown_and_forged_distance_are_not_positive_sections(self):
        meshes, original = section_fixture()
        for fields in ({'signed_clearance_m': 0.}, {'signed_clearance_m': -.002},
                       {'measurement_kind': 'lower_bound'}, {'measurement_valid': False},
                       {'signed_clearance_m': .02}, {'point_a_world': [float('nan'), 0, 0]}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.draw(meshes, {**original, **fields})

    def test_resource_failure_returns_no_partial_panel_and_never_mutates_canvas(self):
        meshes, measured = section_fixture()
        original = Image.new('RGB', (256, 256), (17, 31, 47))
        before = original.tobytes()
        with patch('human_eye_plugin.contact_section.MAX_SECTION_TRIANGLES', 1), self.assertRaises(ValueError):
            self.draw(meshes, measured, original)
        self.assertEqual(original.tobytes(), before)

    def test_query_is_explicit_bounded_idempotent_and_advertised(self):
        query = validate_query({'visual_diagnostic': 'contact_section'})
        self.assertEqual(validate_query(query), query)
        self.assertNotIn('visual_diagnostic', validate_query(None))
        for value in ('xray', '', None, True, {}, ['contact_section']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_query({'visual_diagnostic': value})
        observe = next(item for item in LIVE_MCP_TOOLS_SCHEMA if item['name'] == 'human_eye_scene_observe')
        self.assertEqual(observe['inputSchema']['properties']['query']['properties']['visual_diagnostic']['enum'], ['contact_section'])

    def test_router_opt_in_preserves_natural_four_views_and_isolated_cache_key(self):
        router = HumanEyeAutoRouter(quad_size=128)
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            natural = router.handle_event(observation(scene=near_scene()))
            diagnostic = router.handle_event(observation(scene=near_scene(), query={'visual_diagnostic':'contact_section'}))
            repeated = router.handle_event(observation(scene=near_scene(), query={'visual_diagnostic':'contact_section'}))
        self.assertFalse(diagnostic['cache_hit'])
        self.assertTrue(repeated['cache_hit'])
        np.testing.assert_array_equal(np.asarray(picture(diagnostic))[:, :256], np.asarray(picture(natural)))
        facts = json.loads(diagnostic['context_text'])
        self.assertEqual(facts['visual_diagnostics']['status'], 'available')
        self.assertEqual(len(facts['canvas']['views']), 4)
        self.assertFalse(facts['visual_diagnostics']['execution_authority'])
        self.assertIsNotNone(diagnostic['observation_id'])  # Normal observation, not authority from a section.

    def test_optional_section_exception_preserves_full_natural_image_and_measurement(self):
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            natural = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene()))
            with patch('human_eye_plugin.auto_router.append_contact_section', side_effect=RuntimeError('optional')):
                failed = HumanEyeAutoRouter(quad_size=128).handle_event(observation(
                    scene=near_scene(), query={'visual_diagnostic':'contact_section'}))
        self.assertEqual(picture(natural).tobytes(), picture(failed).tobytes())
        facts = json.loads(failed['context_text'])
        self.assertEqual(facts['visual_diagnostics']['status'], 'unavailable')
        self.assertEqual(facts['visual_diagnostics']['error_type'], 'RuntimeError')
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .002)

    def test_text_only_avoids_section_work_and_reports_unavailability(self):
        with patch('human_eye_plugin.auto_router.append_contact_section') as render:
            result = HumanEyeAutoRouter(quad_size=128).handle_event(observation(
                scene=near_scene(), include_image=False, query={'visual_diagnostic':'contact_section'}))
        render.assert_not_called()
        self.assertIsNone(result['image'])
        self.assertEqual(json.loads(result['context_text'])['visual_diagnostics']['status'], 'unavailable')

    def test_incomplete_optional_result_cannot_publish_widened_image_or_metadata(self):
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            natural = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene()))
            with patch('human_eye_plugin.auto_router.append_contact_section',
                       return_value=(Image.new('RGB', (448, 256)), {'status':'available'})):
                broken = HumanEyeAutoRouter(quad_size=128).handle_event(observation(
                    scene=near_scene(), query={'visual_diagnostic':'contact_section'}))
        self.assertEqual(picture(broken).size, (256,256))
        self.assertEqual(picture(broken).tobytes(), picture(natural).tobytes())
        facts = json.loads(broken['context_text'])
        self.assertEqual(facts['canvas']['canvas_size'], [256,256])
        self.assertNotIn('diagnostic_panel', facts['canvas'])
        self.assertEqual(facts['visual_diagnostics']['status'], 'unavailable')

    def test_section_does_not_bypass_inner_collision_gate(self):
        router = HumanEyeAutoRouter(quad_size=128)
        result = router.handle_event(observation(scene=near_scene(), include_image=False,
            query={'visual_diagnostic':'contact_section'}))
        rejected = router.handle_event(action(result, action={'translation':[0,0,-.003]}))
        self.assertFalse(rejected['allow_action'])
        self.assertEqual(rejected['reason_codes'], ['candidate_collision'])

    def test_stepwise_gap_changes_are_tracked_from_current_meshes(self):
        router = HumanEyeAutoRouter(quad_size=128)
        observed = []
        for gap in (.004, .002, .001):
            value = near_scene()
            item = value['meshes'][1]
            delta = gap - .002
            item['vertices'] = (np.asarray(item['vertices']) + [0, 0, delta]).tolist()
            item['pivot_world'][2] += delta
            # Deliberately retain the same external revision: content decides.
            result = router.handle_event(observation(scene=value, query={'visual_diagnostic':'contact_section'}))
            facts = json.loads(result['context_text'])
            evidence = facts['visual_diagnostics']
            self.assertEqual(evidence['status'], 'available')
            self.assertAlmostEqual(evidence['measured_clearance_m'], gap)
            self.assertAlmostEqual(evidence['m_per_pixel'] * 12, gap)
            if observed:
                self.assertIn('part', facts['scene_memory']['changes']['transform'])
            observed.append(result['scene_fingerprint'])
        self.assertEqual(len(set(observed)), 3)

    def test_hidden_object_change_is_detected_when_natural_image_is_identical(self):
        value = near_scene()
        value['meshes'] += [box('shell', [0, 0, 0], [10, 10, 10]),
                            box('hidden', [.2, .2, .4], [.1, .1, .1])]
        router = HumanEyeAutoRouter(quad_size=128)
        # Include the opaque shell in the target fit, retaining four natural
        # surface views rather than a navigation map that deliberately exposes
        # coordinates of hidden objects.
        before = router.handle_event(observation(scene=value, reference_id='shell'))
        changed = copy.deepcopy(value)
        moved = changed['meshes'][-1]
        moved['vertices'] = (np.asarray(moved['vertices']) + [.01, 0, 0]).tolist()
        moved['pivot_world'][0] += .01
        after = router.handle_event(observation(scene=changed, reference_id='shell'))
        self.assertEqual(picture(before).tobytes(), picture(after).tobytes())
        self.assertNotEqual(before['scene_fingerprint'], after['scene_fingerprint'])
        memory = json.loads(after['context_text'])['scene_memory']
        self.assertEqual(memory['changes']['transform'], ['hidden'])
        self.assertEqual(set(memory['changes']['unchanged']), {'base', 'part', 'shell'})


if __name__ == '__main__':
    unittest.main()
