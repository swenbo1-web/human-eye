"""Task-label integration contracts, using current meshes and real raster/attention.

These checks distinguish display aliases from object identities and natural
visibility. No Blender, production configuration or historical file is loaded.
"""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin.attention_rendering import _contact_overlay, apply_attention_to_canvas
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.task_brief import project_task_brief
from human_eye_plugin.task_labels import build_task_label_plan, task_display_label
from verification.test_attention_rendering import fixture, near_scene
from verification.test_auto_router import action, box, observation, scene


def values(extra=False):
    raw = scene()
    if extra:
        raw['meshes'].extend([
            box('related-one', [-.42, -.26, .3], [.12, .12, .12]),
            box('related-two', [.42, .26, .3], [.12, .12, .12]),
            box('peripheral-one', [-.42, .26, .3], [.12, .12, .12]),
            box('peripheral-two', [.42, -.26, .3], [.12, .12, .12]),
        ])
    return [MeshEntity3D.from_dict(item) for item in raw['meshes']]


def plan_for(meshes, *, focal='part', reference='base', requested=(), contacts=(), fingerprint='snapshot'):
    return build_task_label_plan(meshes, focal_id=focal, reference_id=reference,
        requested_ids=requested, contacts=contacts, scene_revision='r1',
        scene_fingerprint=fingerprint)


def draw(meshes, plan, size=256, *, focal='part', reference='base'):
    return rendering.render_scene_canvas(meshes, size, focal_id=focal,
        reference_id=reference, label_plan=plan)


def aliases(metadata):
    return {row['object_id']: row['display_label'] for row in metadata['object_labels']}


def geometry_metadata(metadata):
    keys = ('view_matrix', 'projection_matrix', 'target_object_ids',
            'object_visible_pixels', 'geometry_depth_pixels', 'depth_range_m',
            'occlusion_object_ids', 'all_supplied_geometry_participates_in_depth')
    return [{key: view[key] for key in keys if key in view} for view in metadata['views']]


def contact_marker_fixture(alias_width):
    # These real SHA-256 prefixes agree for seven characters, then differ.
    # The full eight-character alias is produced by the real policy, without
    # inventing an invalid plan or mocking the display-identity mapping.
    identities = ['part', 'base', 'contact-edge-4375']
    if alias_width == 8:
        identities.append('contact-edge-20515')
    label_plan = build_task_label_plan([{'object_id': identity} for identity in identities],
        focal_id='part', reference_id='base', scene_revision='r1', scene_fingerprint='edge-fixture')
    if label_plan['related_alias_hex_chars'] != alias_width:
        raise AssertionError('Expected real alias collision fixture changed')
    return label_plan, ['part', 'contact-edge-4375']


def capture_contact_markers(size, screen, label_plan, target_ids, occupied=()):
    """Exercise actual Pillow text drawing with independently measured boxes."""
    picture = Image.new('RGB', (size, size), (18, 22, 30))
    metadata = {'projected_labels': [{'label_box_px': list(box),
        'object_id': f'layout-obstacle-{index}', 'stable_label': f'OCCUPIED{index}',
        'display_label': f'OCCUPIED{index}'} for index, box in enumerate(occupied)]}
    screen = np.asarray(screen, dtype=float)
    pixels = np.c_[screen[:, 0], size - 1 - screen[:, 1]]
    marker_names = {task_display_label(identity, label_plan) for identity in target_ids}
    text_calls = []
    original_text = ImageDraw.ImageDraw.text

    def capture(draw_object, position, text, *args, **kwargs):
        if text in marker_names:
            bbox_args = {name: kwargs[name] for name in (
                'font', 'anchor', 'spacing', 'align', 'direction', 'features',
                'language', 'stroke_width', 'embedded_color', 'font_size') if name in kwargs}
            bbox = draw_object.textbbox(position, text, **bbox_args)
            text_calls.append({'marker': text, 'bbox': list(bbox),
                               'stroke_width': kwargs.get('stroke_width', 0)})
        return original_text(draw_object, position, text, *args, **kwargs)

    with patch.object(ImageDraw.ImageDraw, 'text', new=capture):
        _contact_overlay(picture, {'target_object_ids': target_ids},
            {'strict_clearance_m': .000123456789}, pixels, metadata, label_plan=label_plan)
    return metadata['measurement_overlay'], text_calls


def interior_bounds(size):
    bottom = size - (47 if size >= 256 else 55) if size >= 128 else size - 16
    return 2, 19, size - 2, bottom


def boxes_overlap(first, second):
    return (first[0] < second[2] and first[2] > second[0]
            and first[1] < second[3] and first[3] > second[1])


class TaskAttentionLabelIntegrationTests(unittest.TestCase):
    def assert_marker_layout(self, size, overlay, calls, label_plan, target_ids, occupied=()):
        expected = [(identity, task_display_label(identity, label_plan)) for identity in target_ids]
        self.assertEqual([(row['object_id'], row['marker']) for row in overlay['object_markers']], expected)
        self.assertEqual([(row['object_id'], row['marker']) for row in overlay['marker_labels']], expected)
        self.assertEqual(overlay['signed_clearance_m'], .000123456789)
        self.assertFalse(overlay['visible_gap_certified'])
        self.assertEqual(overlay['source'], 'existing_unrounded_contact_measurement')
        self.assertTrue(all(row['stable_label'] == 'O' + hashlib.sha256(row['object_id'].encode()).hexdigest()[:8].upper()
                            for row in overlay['object_markers']))
        left, top, right, bottom = interior_bounds(size)
        drawn_boxes = []
        for row in overlay['marker_labels']:
            actual = [call for call in calls if call['marker'] == row['marker']]
            self.assertIn(row['status'], ('drawn', 'omitted_no_label_space'))
            if row['status'] == 'omitted_no_label_space':
                self.assertIsNone(row['text_box_px'])
                self.assertEqual(actual, [], 'Omitted marker must not still paint cropped text')
                continue
            self.assertEqual(len(actual), 1, 'Every drawn receipt must correspond to one actual text call')
            box = row['text_box_px']
            self.assertEqual(len(box), 4)
            self.assertTrue(all(type(coordinate) is int for coordinate in box))
            self.assertEqual(box, actual[0]['bbox'], 'Receipt must describe Pillow glyph bounds including stroke')
            self.assertEqual(actual[0]['stroke_width'], 1)
            self.assertLess(box[0], box[2])
            self.assertLess(box[1], box[3])
            self.assertGreaterEqual(box[0], left)
            self.assertGreaterEqual(box[1], top)
            self.assertLessEqual(box[2], right)
            self.assertLessEqual(box[3], bottom)
            for other in [*drawn_boxes, *occupied]:
                self.assertFalse(boxes_overlap(box, other), 'Witness text must not overlap existing label text boxes')
            drawn_boxes.append(box)
        self.assertEqual(len(calls), len(drawn_boxes))

    def test_contact_marker_actual_glyph_bounds_at_edges_and_coincident_witnesses(self):
        for size in (64, 96, 128, 256, 512):
            edge_pairs = (
                ((0, 0), (1, 1)), ((size - 2, 0), (size - 1, 1)),
                ((0, size - 2), (1, size - 1)),
                ((size - 2, size - 2), (size - 1, size - 1)),
                ((size / 2, size / 2), (size / 2, size / 2)))
            for width in (4, 8):
                label_plan, target_ids = contact_marker_fixture(width)
                for screen in edge_pairs:
                    with self.subTest(size=size, alias_width=width, screen=screen):
                        overlay, calls = capture_contact_markers(size, screen, label_plan, target_ids)
                        self.assert_marker_layout(size, overlay, calls, label_plan, target_ids)
                        self.assertTrue(calls, 'An unoccupied interior must retain at least the small core marker')

    def test_contact_marker_text_relocates_around_existing_projected_labels(self):
        label_plan, target_ids = contact_marker_fixture(8)
        occupied = ((98, 94, 175, 112), (150, 115, 210, 145))
        overlay, calls = capture_contact_markers(256, ((110, 90), (114, 93)), label_plan, target_ids, occupied)
        self.assert_marker_layout(256, overlay, calls, label_plan, target_ids, occupied)
        self.assertEqual([row['status'] for row in overlay['marker_labels']], ['drawn', 'drawn'])

    def test_contact_marker_without_label_space_keeps_identity_and_explicit_omission(self):
        label_plan, target_ids = contact_marker_fixture(8)
        for size in (64, 96, 128, 256, 512):
            with self.subTest(size=size):
                occupied = (interior_bounds(size),)
                overlay, calls = capture_contact_markers(size,
                    ((size / 2, size / 2), (size / 2 + 1, size / 2 + 2)), label_plan, target_ids, occupied)
                self.assert_marker_layout(size, overlay, calls, label_plan, target_ids, occupied)
                self.assertEqual([row['status'] for row in overlay['marker_labels']],
                                 ['omitted_no_label_space', 'omitted_no_label_space'])
                self.assertEqual(len(overlay['witness_screen_px']), 2)
                self.assertEqual(len(overlay['dimension_line_px']), 2)

    def test_core_aliases_agree_in_every_view_without_changing_geometry(self):
        meshes = values()
        before = copy.deepcopy([mesh.to_dict() for mesh in meshes])
        old_image, old = draw(meshes, None)
        image, visual = draw(meshes, plan_for(meshes))
        binding = aliases(visual)
        self.assertEqual(binding, {'base': 'B', 'part': 'A'})
        self.assertEqual(geometry_metadata(old), geometry_metadata(visual))
        self.assertEqual(image.size, old_image.size)
        for view in visual['views']:
            self.assertEqual({row['object_id'] for row in view['projected_labels']}, {'base', 'part'})
            for row in view['projected_labels']:
                self.assertEqual(row['display_label'], binding[row['object_id']])
                expected = 'O' + hashlib.sha256(row['object_id'].encode()).hexdigest()[:8].upper()
                self.assertEqual(row['stable_label'], expected)
                self.assertGreaterEqual(row['surface_visible_pixels'], 8)
            self.assertFalse(view['labels_certify_visibility'])
        self.assertFalse(visual['visibility_certified'])
        self.assertEqual(before, [mesh.to_dict() for mesh in meshes])

    def test_aliases_stay_stable_under_enumeration_marks_and_scene_translation(self):
        meshes = values(extra=True)
        requested = ('related-one', 'related-two')
        _, before = draw(meshes, plan_for(meshes, requested=requested))
        changed = [MeshEntity3D.from_dict(mesh.to_dict()) for mesh in reversed(meshes)]
        for index, mesh in enumerate(changed):
            mesh.mark_label = '#changed-' + str(index)
            mesh.vertices += np.array([.002, -.003, .001])
        _, after = draw(changed, plan_for(changed, requested=tuple(reversed(requested)), fingerprint='next-snapshot'))
        self.assertEqual(aliases(before), aliases(after))
        self.assertEqual(before['task_labels']['related_object_ids'], after['task_labels']['related_object_ids'])
        self.assertEqual(before['views'][0]['label_priority_object_ids'], after['views'][0]['label_priority_object_ids'])

    def test_related_budget_omits_labels_without_omitting_geometry(self):
        meshes = values(extra=True)
        plan = plan_for(meshes, requested=('related-one', 'related-two'))
        _, visual = draw(meshes, plan)
        all_ids = {mesh.object_id for mesh in meshes}
        selected = {'part', 'base', 'related-one', 'related-two'}
        for view in visual['views']:
            shown = {row['object_id'] for row in view['projected_labels']}
            self.assertLessEqual(len(shown), 4)
            self.assertTrue(shown <= selected)
            self.assertEqual(set(view['occlusion_object_ids']), all_ids)
            self.assertEqual(set(view['object_visible_pixels']), all_ids)
            layout = view['label_layout']
            self.assertEqual(layout['displayed_label_count'] + layout['omitted_object_count'], len(meshes))
        self.assertEqual(len(visual['object_labels']), len(meshes))
        self.assertTrue(any({'part', 'base'} <= {row['object_id'] for row in view['projected_labels']}
                            for view in visual['views']))

    def test_fully_occluded_core_is_not_drawn_as_visible(self):
        meshes = values()
        meshes.append(MeshEntity3D.from_dict(box('enclosure', [0, 0, .2], [10, 10, 10])))
        _, visual = draw(meshes, plan_for(meshes), size=128)
        self.assertEqual(aliases(visual)['part'], 'A')
        for view in visual['views']:
            self.assertEqual(view['object_visible_pixels']['part'], 0)
            self.assertNotIn('part', [row['object_id'] for row in view['projected_labels']])
            self.assertIn('enclosure', view['occlusion_object_ids'])

    def test_small_view_keeps_geometry_but_does_not_force_alias_glyphs(self):
        meshes = values()
        _, visual = draw(meshes, plan_for(meshes), size=64)
        self.assertEqual(aliases(visual)['part'], 'A')
        for view in visual['views']:
            self.assertEqual(view['projected_labels'], [])
            self.assertGreater(view['geometry_depth_pixels'], 0)

    def test_pair_switch_changes_binding_instead_of_silently_reusing_old_B(self):
        meshes = values(extra=True)
        original = plan_for(meshes)
        _, first = draw(meshes, original)
        changed = plan_for(meshes, reference='related-one', fingerprint='next-pair')
        _, second = draw(meshes, changed, reference='related-one')
        self.assertEqual(aliases(first)['base'], 'B')
        self.assertEqual(aliases(second)['related-one'], 'B')
        self.assertNotEqual(aliases(second)['base'], 'B')
        self.assertNotEqual(first['task_labels'], second['task_labels'])
        with self.assertRaises(ValueError):
            draw(meshes, original, reference='related-one')

    def test_explicit_none_keeps_public_legacy_pixels_and_metadata(self):
        meshes = values(extra=True)
        implicit_image, implicit = rendering.render_scene_canvas(meshes, 128, focal_id='part', reference_id='base')
        explicit_image, explicit = draw(meshes, None, size=128)
        np.testing.assert_array_equal(np.asarray(implicit_image), np.asarray(explicit_image))
        self.assertEqual(implicit, explicit)
        self.assertNotIn('task_labels', explicit)
        self.assertTrue(all('display_label' not in row for row in explicit['object_labels']))

    def test_prepared_label_metadata_is_bound_and_tampering_is_rejected(self):
        meshes = values()
        plan = plan_for(meshes)
        image, metadata, token = rendering._render_scene_canvas_prepared(meshes, 128,
            focal_id='part', reference_id='base', scene_fingerprint='snapshot', label_plan=plan)
        metadata['task_labels']['reference_id'] = 'part'
        with self.assertRaises(ValueError):
            rendering._finalize_prepared_scene_q4(image, metadata, token, scene_fingerprint='snapshot')

    def test_public_deferred_finalizer_rejects_non_dictionary_label_plans(self):
        meshes = values()
        image, metadata = rendering.render_scene_canvas(meshes, 128,
            focal_id='part', reference_id='base', defer_q4=True, label_plan=plan_for(meshes))
        image_before = np.asarray(image).copy()
        for malformed in (False, True, 0, 1., 'task-plan', [], ['A', 'B'], ('A', 'B')):
            with self.subTest(type_name=type(malformed).__name__, value=malformed):
                invalid = copy.deepcopy(metadata)
                invalid['task_labels'] = malformed
                before = copy.deepcopy(invalid)
                with self.assertRaises(ValueError):
                    rendering.finalize_scene_q4(image, invalid, meshes)
                self.assertEqual(invalid, before)
                np.testing.assert_array_equal(np.asarray(image), image_before)

    def test_prepared_plan_has_detached_input_and_matching_snapshot_binding(self):
        meshes = values()
        plan = plan_for(meshes)
        image, metadata, token = rendering._render_scene_canvas_prepared(meshes, 128,
            focal_id='part', reference_id='base', scene_fingerprint='snapshot', label_plan=plan)
        plan['reference_id'] = 'part'
        output, visual = rendering._finalize_prepared_scene_q4(image, metadata, token, scene_fingerprint='snapshot')
        self.assertEqual(visual['task_labels']['reference_id'], 'base')
        self.assertEqual(output.size, (256, 256))
        with self.assertRaises(ValueError):
            rendering._render_scene_canvas_prepared(meshes, 128, focal_id='part', reference_id='base',
                scene_fingerprint='different-snapshot', label_plan=plan_for(meshes))

    def test_actual_attention_third_object_keeps_global_B_and_measurement_evidence(self):
        _, _, base_meshes, options = fixture()
        meshes = base_meshes + [MeshEntity3D.from_dict(box('caller-reference', [3, 0, .1], [.3, .3, .2])),
            MeshEntity3D.from_dict(box('related-one', [4, 2, .3], [.1, .1, .1])),
            MeshEntity3D.from_dict(box('related-two', [4, -2, .3], [.1, .1, .1]))]
        original = copy.deepcopy([mesh.to_dict() for mesh in meshes])
        options = dict(options, reference_id='caller-reference')
        label_plan = plan_for(meshes, reference='caller-reference', requested=('related-one', 'related-two'),
            contacts=options['contacts'], fingerprint=options['scene_fingerprint'])
        self.assertNotIn('base', label_plan['related_object_ids'])
        raw, old = draw(meshes, None, 128, reference='caller-reference')
        image, meta = draw(meshes, label_plan, 128, reference='caller-reference')
        with patch('human_eye_plugin.attention_rendering.time.perf_counter', return_value=0.):
            _, old_visual, old_state = apply_attention_to_canvas(raw, old, meshes, **options)
            _, visual, state = apply_attention_to_canvas(image, meta, meshes, **options)
        self.assertIsNotNone(old_state, old_visual['attention'])
        self.assertIsNotNone(state, visual['attention'])
        self.assertEqual(state, old_state)
        contact = visual['views'][3]
        self.assertEqual(contact['target_object_ids'], ['part', 'base'])
        self.assertEqual(contact['readability'], old_visual['views'][3]['readability'])
        self.assertFalse(contact['readability']['annotations_count_as_evidence'])
        self.assertEqual(contact['object_visible_pixels'], old_visual['views'][3]['object_visible_pixels'])
        self.assertEqual({row['object_id'] for row in contact['projected_labels']}, {'part', 'base'})
        mapped = aliases(visual)
        self.assertEqual(mapped['caller-reference'], 'B')
        self.assertTrue(mapped['base'].startswith('R'))
        markers = contact['measurement_overlay']['object_markers']
        self.assertEqual([(row['object_id'], row['marker']) for row in markers], [('part', 'A'), ('base', mapped['base'])])
        self.assertAlmostEqual(contact['measurement_overlay']['signed_clearance_m'], .002)
        self.assertFalse(contact['measurement_overlay']['visible_gap_certified'])
        self.assertEqual(original, [mesh.to_dict() for mesh in meshes])

    def test_router_publishes_bound_plan_without_changing_input_or_measurements(self):
        raw = near_scene()
        before = copy.deepcopy(raw)
        router = HumanEyeAutoRouter(quad_size=128)
        result = router.handle_event(observation(scene=raw))
        facts = json.loads(result['context_text'])
        self.assertEqual(facts['canvas']['task_labels']['scene_revision'], raw['revision'])
        self.assertEqual(facts['canvas']['task_labels']['scene_fingerprint'], result['scene_fingerprint'])
        self.assertEqual(aliases(facts['canvas'])['part'], 'A')
        self.assertAlmostEqual(facts['measurement']['signed_clearance_m'], .002)
        self.assertEqual((facts['focal_id'], facts['reference_id']), ('part', 'base'))
        self.assertEqual(raw, before)

    def test_text_only_observation_does_not_build_display_plan(self):
        with patch('human_eye_plugin.auto_router.build_task_label_plan',
                   side_effect=AssertionError('Text only must not compute image labels')) as build:
            result = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene(), include_image=False))
        build.assert_not_called()
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['image'])

    def test_brief_preserves_actual_label_bindings_and_rendered_aliases(self):
        result = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=near_scene()))
        facts = json.loads(result['context_text'])
        full = {'status': 'observed', 'result_contract_version': '1.1', 'routing': result,
            'observation_status': facts['observation_status'], 'scene_assessment': facts['scene_assessment'],
            'action_eligibility': {}, 'execution_status': 'not_requested', 'pair_goal': {},
            'scene_capabilities': facts['scene_capabilities']}
        original = copy.deepcopy(full)
        brief = project_task_brief(full)
        self.assertIsInstance(brief, dict)
        canvas = brief['observation']['canvas']
        self.assertEqual(canvas['task_labels'], facts['canvas']['task_labels'])
        self.assertEqual(canvas['object_labels'], facts['canvas']['object_labels'])
        for before, after in zip(facts['canvas']['views'], canvas['views']):
            self.assertEqual(before['projected_labels'], after['projected_labels'])
            if 'measurement_overlay' in before:
                self.assertEqual(before['measurement_overlay'], after['measurement_overlay'])
        self.assertEqual(full, original)

    def test_short_alias_is_not_accepted_as_an_action_object_id(self):
        router = HumanEyeAutoRouter(quad_size=128)
        result = router.handle_event(observation(scene=near_scene()))
        blocked = router.handle_event(action(result, focal_id='A', reference_id='B'))
        self.assertFalse(blocked['allow_action'])
        self.assertEqual(blocked['reason_codes'], ['pair_or_frame_required'])

    def test_unknown_geometry_remains_in_scene_evidence_when_labels_are_selective(self):
        raw = near_scene()
        unknown = box('open-obstacle', [2, 0, .3], [.1, .1, .1])
        unknown['faces'] = unknown['faces'][:-2]
        raw['meshes'].append(unknown)
        result = HumanEyeAutoRouter(quad_size=128).handle_event(observation(scene=raw))
        facts = json.loads(result['context_text'])
        self.assertIn('open-obstacle', [item['object_id'] for item in facts['unknown_objects']])
        self.assertEqual(facts['scene_assessment']['status'], 'unknown')
        self.assertIn('open-obstacle', [item['object_id'] for item in facts['objects']])
        for view in facts['canvas']['views']:
            self.assertIn('open-obstacle', view['occlusion_object_ids'])
        self.assertFalse(facts['canvas']['task_labels']['execution_authority'])


if __name__ == '__main__':
    unittest.main()
