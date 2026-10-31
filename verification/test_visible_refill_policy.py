"""Add-only same-rank labels preserve current geometry and original delivery."""
import copy
import itertools
import pickle
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin import visible_refill as refill
from human_eye_plugin.task_labels import _build_task_label_bundle, build_task_label_plan
from verification.test_auto_router import box
from verification.test_task_label_policy import penetration


def priority_scene():
    specifications = [
        ('reference', [0, 0, -.02], [.14, .12, .04], [120, 120, 120]),
        ('focus', [0, 0, .024], [.06, .05, .04], [30, 50, 210]),
        ('risk-00-hidden', [-.012, 0, .024], [.008] * 3, [220, 110, 30]),
        ('risk-01-hidden', [.012, 0, .024], [.008] * 3, [220, 110, 30]),
        ('risk-02-visible', [.029, -.024, .034], [.018] * 3, [30, 180, 80]),
    ]
    meshes = []
    for identity, center, extent, color in specifications:
        row = box(identity, center, extent, identity == 'focus')
        row['color_rgb'] = color
        meshes.append(MeshEntity3D.from_dict(row))
    return meshes


def bundle(meshes, **changes):
    kwargs = dict(focal_id='focus', reference_id='reference',
                  contacts=[penetration(mesh.object_id) for mesh in meshes[2:]],
                  scene_revision='refill-policy-r1', scene_fingerprint='snapshot')
    kwargs.update(changes)
    return _build_task_label_bundle(meshes, **kwargs)


def prepared(size=256, **changes):
    meshes = priority_scene()
    plan, pool = bundle(meshes)
    collector = refill.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot', **changes)
    records = {}

    def observer(index, picture, metadata, current_meshes, color, depth, owners):
        records[index] = (picture, color, owners)
        collector.observe_view(index, picture, metadata, current_meshes, color, depth, owners)

    canvas, metadata = rendering._render_scene_canvas_impl(meshes, size,
        focal_id='focus', reference_id='reference', label_plan=plan, raw_observer=observer)
    return collector, canvas, metadata, meshes, records


def finish(collector, canvas, metadata, meshes, **changes):
    kwargs = dict(scene_fingerprint='snapshot', remaining_budget_ms=40.)
    kwargs.update(changes)
    return collector.finish(canvas, metadata, meshes, **kwargs)


class VisibleRefillPolicyTests(unittest.TestCase):
    def test_private_bundle_preserves_public_plan_and_complete_same_evidence_pool(self):
        meshes = priority_scene()
        plan, pool = bundle(meshes)
        public = build_task_label_plan(meshes, focal_id='focus', reference_id='reference',
            contacts=[penetration(mesh.object_id) for mesh in meshes[2:]],
            scene_revision='refill-policy-r1', scene_fingerprint='snapshot')
        self.assertEqual(plan, public)
        self.assertEqual(plan['related_object_ids'], ['risk-00-hidden', 'risk-01-hidden'])
        self.assertEqual(pool, tuple((mesh.object_id, 'known_penetration') for mesh in meshes[2:]))
        self.assertNotIn('candidate_pool', plan)

    def test_same_rank_gain_preserves_original_boxes_core_owners_and_other_views(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for size in (256, 384):
                with self.subTest(size=size):
                    collector, canvas, meta, meshes, records = prepared(size)
                    before = copy.deepcopy(meta)
                    mesh_before = [mesh.to_dict() for mesh in meshes]
                    for index, record in collector._views.items():
                        self.assertIs(record[3], records[index][1])
                        self.assertIs(record[4], records[index][2])
                    output, visual, receipt = finish(collector, canvas, meta, meshes)
                    self.assertTrue(receipt['applied'], receipt)
                    self.assertEqual(receipt['candidate_raster_count'], 0)
                    self.assertEqual(receipt['new_readable_object_ids'], ['risk-02-visible'])
                    self.assertEqual(receipt['donor_reason'], 'known_penetration')
                    self.assertEqual(receipt['core_new_changed_pixels'], 0)
                    self.assertLessEqual(receipt['actual_delivered_default_related_count'], 2)
                    self.assertEqual(visual['task_labels'], before['task_labels'])
                    self.assertEqual(meta, before)
                    self.assertEqual([mesh.to_dict() for mesh in meshes], mesh_before)
                    self.assertEqual(output.size, canvas.size)
                    source = receipt['source_view_index']
                    self.assertIn(source, (0, 1, 2))
                    for index in range(4):
                        bounds = ((index % 2) * size, (index // 2) * size,
                                  (index % 2 + 1) * size, (index // 2 + 1) * size)
                        if index != source:
                            self.assertEqual(output.crop(bounds).tobytes(), canvas.crop(bounds).tobytes())
                            self.assertEqual(visual['views'][index], before['views'][index])
                            continue
                        picture, color, owners = records[index]
                        changed = np.any(np.asarray(output.crop(bounds)) != np.asarray(picture), axis=2)
                        self.assertFalse(np.any(changed & ((owners == 0) | (owners == 1))))
                        for row in before['views'][index]['projected_labels']:
                            left, top, right, bottom = row['label_box_px']
                            self.assertFalse(np.any(changed[top:bottom + 1, left:right + 1]))
                        new = visual['views'][index]['projected_labels'][-1]
                        layout = visual['views'][index]['label_layout']
                        self.assertEqual(layout['omitted_object_count'],
                                         before['views'][index]['label_layout']['omitted_object_count'] - 1)
                        self.assertEqual(sum(layout['omitted_reason_counts'].values()),
                                         layout['omitted_object_count'])
                        self.assertEqual(layout['omitted_objects_truncated'],
                                         layout['omitted_object_count'] - len(layout['omitted_objects']))
                        self.assertNotIn('risk-02-visible',
                                         [value['object_id'] for value in layout['omitted_objects']])
                        self.assertEqual(new['display_source'], 'visible_candidate_refill')
                        self.assertEqual(visual['views'][index]['geometry_pixels_unchanged_by_annotations'],
                            int(np.count_nonzero((owners >= 0)
                                & np.all(np.asarray(output.crop(bounds)) == color, axis=2))))
                        self.assertTrue(receipt['readability']['complete_final_glyph'])
                        self.assertGreaterEqual(receipt['readability']['final_unmodified_surface_pixels'], 16)
                        self.assertGreaterEqual(receipt['readability']['final_unmodified_boundary_pixels'], 4)
                        self.assertFalse(color.flags.writeable)
                        self.assertFalse(owners.flags.writeable)
                    self.assertEqual(collector._views, {})

    def test_any_original_row_even_weak_or_CONTACT_vetoes_donor_or_new_id(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for kind in ('donors', 'candidate'):
                collector, canvas, meta, meshes, _ = prepared()
                contact = meta['views'][3]
                contact['name'] = 'Q4 CONTACT'
                identities = meta['task_labels']['related_object_ids'] if kind == 'donors' else ['risk-02-visible']
                contact['projected_labels'].extend({'object_id': identity, 'surface_visible_pixels': 8}
                                                   for identity in identities)
                output, visual, receipt = finish(collector, canvas, meta, meshes)
                self.assertFalse(receipt['applied'], receipt)
                self.assertIs(output, canvas)
                self.assertIs(visual, meta)

    def test_pool_reordering_counts_prefix_and_unknown_identity_are_rejected(self):
        meshes = priority_scene()
        plan, pool = bundle(meshes)
        variants = [tuple(reversed(pool)), pool + (pool[0],),
                    pool[:2] + (('unknown', 'known_penetration'),),
                    pool[:2] + ((pool[2][0], 'near_exact_clearance'),)]
        for invalid in variants:
            collector = refill.VisibleRefillCollector(plan, invalid, scene_fingerprint='snapshot')
            if collector._disabled is None:
                color = np.zeros((128, 128, 3), np.uint8)
                owners = np.full((128, 128), -1, np.int32)
                from PIL import Image
                collector.observe_view(0, Image.fromarray(color), {}, meshes,
                                       color, np.full((128, 128), np.inf), owners)
            self.assertIsNotNone(collector._disabled)

    def test_visual_focus_including_core_only_is_not_default_refill(self):
        meshes = priority_scene()
        for focus in (['focus'], ['risk-02-visible']):
            plan, pool = bundle(meshes, visual_focus_ids=focus)
            collector = refill.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot')
            self.assertEqual(collector._disabled, 'default_automatic_plan_required')

    def test_same_bbox_geometry_color_role_changes_and_changed_source_pixels_hold(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for kind in ('vertices', 'color', 'role', 'pixels', 'view'):
                collector, canvas, meta, meshes, _ = prepared()
                if kind == 'vertices':
                    meshes[2].vertices[0, 0] += .0001
                elif kind == 'color':
                    meshes[2].color_rgb = (1, 2, 3)
                elif kind == 'role':
                    meshes[2].is_focal_target = not meshes[2].is_focal_target
                elif kind == 'pixels':
                    for index in range(3):
                        canvas.putpixel(((index % 2) * 256 + 1, (index // 2) * 256 + 30), (1, 2, 3))
                else:
                    meta['views'][0]['name'] += ' changed'
                output, visual, receipt = finish(collector, canvas, meta, meshes)
                self.assertFalse(receipt['applied'], (kind, receipt))
                self.assertIs(output, canvas)
                self.assertIs(visual, meta)

    def test_no_fallback_in_another_reason_rank_and_max_eight_candidates(self):
        meshes = priority_scene()
        plan, pool = bundle(meshes)
        changed = copy.deepcopy(plan)
        changed['candidate_reason_counts'] = {'known_penetration': 2, 'near_exact_clearance': 1}
        pool = pool[:2] + ((pool[2][0], 'near_exact_clearance'),)
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector = refill.VisibleRefillCollector(changed, pool, scene_fingerprint='snapshot')
            canvas, meta = rendering._render_scene_canvas_impl(meshes, 256,
                focal_id='focus', reference_id='reference', label_plan=changed,
                raw_observer=collector.observe_view)
            output, visual, receipt = finish(collector, canvas, meta, meshes)
        self.assertEqual(receipt['reason'], 'no_same_priority_readable_candidate')
        self.assertLessEqual(receipt['candidate_count'], 8)
        self.assertIs(output, canvas)
        self.assertIs(visual, meta)

    def test_raw_cap_is_enforced_without_copying_or_retaining_partial_views(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.), \
                patch.object(refill, 'MAX_RAW_BYTES', 1):
            collector, canvas, meta, meshes, _ = prepared()
            output, visual, receipt = finish(collector, canvas, meta, meshes)
        self.assertEqual(receipt['reason'], 'refill_raw_retention_limit')
        self.assertEqual(collector._views, {})
        self.assertIs(output, canvas)
        self.assertIs(visual, meta)

    def test_budget_spent_setup_and_late_candidate_are_reported_and_not_adopted(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, meta, meshes, _ = prepared(setup_cost_ms=5.1)
            output, visual, receipt = finish(collector, canvas, meta, meshes)
            self.assertEqual(receipt['reason'], 'refill_setup_budget_exceeded')
            self.assertGreaterEqual(receipt['additional_cost_ms'], 5.1)
            self.assertIs(output, canvas)
            self.assertIs(visual, meta)
            collector, canvas, meta, meshes, _ = prepared()
        tick = iter([0., .020, .020])
        with patch.object(refill, 'visible_refill_clock', side_effect=lambda: next(tick, .020)):
            output, visual, receipt = finish(collector, canvas, meta, meshes)
        self.assertFalse(receipt['applied'])
        self.assertGreaterEqual(receipt['additional_cost_ms'], 20.)
        self.assertIs(output, canvas)
        self.assertIs(visual, meta)

    def test_failed_glyph_or_layout_and_optional_exception_keep_original_objects(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for helper, options in (('_glyph_survives', {'return_value': False}),
                                    ('_label_box', {'return_value': None}),
                                    ('_label_box', {'side_effect': RuntimeError('candidate')})):
                collector, canvas, meta, meshes, _ = prepared()
                with patch.object(refill, helper, **options):
                    output, visual, receipt = finish(collector, canvas, meta, meshes)
                self.assertFalse(receipt['applied'], receipt)
                self.assertIs(output, canvas)
                self.assertIs(visual, meta)
                self.assertEqual(collector._views, {})

    def test_boundary_requires_real_two_sided_contrast_and_safe_samples(self):
        color = np.zeros((4, 4, 3), np.uint8)
        owners = np.zeros((4, 4), np.int32)
        owners[:, 2:] = 1
        usable = np.ones((4, 4), bool)
        color[:, 2:, 0] = 23
        self.assertFalse(refill._boundary_pixels(color, owners, usable).any())
        color[:, 2:, 0] = 24
        self.assertEqual(int(refill._boundary_pixels(color, owners, usable).sum()), 8)
        usable[:, 1] = False
        self.assertFalse(refill._boundary_pixels(color, owners, usable).any())

    def test_owner_bbox_halo_matches_full_image_owner_edges_including_safe_holes(self):
        rng = np.random.default_rng(294)
        for shape in ((8, 9), (19, 23)):
            color = rng.integers(0, 256, size=shape + (3,), dtype=np.uint8)
            owners = rng.integers(-1, 4, size=shape, dtype=np.int32)
            usable = rng.random(shape) > .2
            full = refill._boundary_pixels(color, owners, usable)
            for owner in range(4):
                cropped, target, _, _ = refill._owner_boundary_pixels(color, owners, usable, owner)
                np.testing.assert_array_equal(cropped & (owners == owner), full & (owners == owner))
                np.testing.assert_array_equal(target, usable & (owners == owner))
        # A tiny disjoint two-piece owner with one piece at the image edge
        # exercises both bbox clipping and two-sided halo evidence.
        color = np.zeros((32, 32, 3), np.uint8)
        owners = np.zeros((32, 32), np.int32)
        owners[:2, :2] = 1
        owners[20:22, 18:20] = 1
        color[owners == 1] = (24, 0, 0)
        usable = np.ones((32, 32), bool)
        cropped, _, _, _ = refill._owner_boundary_pixels(color, owners, usable, 1)
        full = refill._boundary_pixels(color, owners, usable)
        np.testing.assert_array_equal(cropped & (owners == 1), full & (owners == 1))

    def test_exact_rgb_comparison_preserves_all_channels_and_sparse_delta_shapes(self):
        rng = np.random.default_rng(721)
        first = rng.integers(0, 256, size=(13, 17, 3), dtype=np.uint8)
        second = first.copy()
        second[0, 1, 0] ^= 1
        second[2, 3, 1] ^= 1
        second[4, 5, 2] ^= 1
        np.testing.assert_array_equal(refill._rgb_equal(first, second), np.all(first == second, axis=-1))
        selected = np.any(first != second, axis=-1)
        np.testing.assert_array_equal(refill._rgb_equal(first[selected], second[selected]),
                                      np.all(first[selected] == second[selected], axis=-1))
        difference = ImageChops.difference(Image.fromarray(first), Image.fromarray(second))
        bounds = difference.getbbox()
        self.assertEqual(bounds, (1, 0, 6, 5))
        changed = np.zeros(selected.shape, bool)
        changed[bounds[1]:bounds[3], bounds[0]:bounds[2]] = np.any(
            np.asarray(difference.crop(bounds)) != 0, axis=2)
        np.testing.assert_array_equal(changed, selected)

    def test_candidate_cropped_evidence_matches_full_frame_UI_and_boundary_oracle(self):
        rng = np.random.default_rng(617)
        color = rng.integers(0, 256, (128, 128, 3), dtype=np.uint8)
        owners = np.zeros((128, 128), np.int32)
        owners[12:25, 20:28] = 1  # Header crossing, retained global row 17.
        owners[78:100, 80:94] = 1  # NAV footer crossing in the second case.
        owners[114:128, 124:128] = 1  # Scale/border and clipped halo.
        picture = Image.fromarray(color)
        ImageDraw.Draw(picture).rectangle((83, 80, 85, 82), fill=(1, 2, 3))
        for region in (None, [0, 85, 128, 113]):
            metadata = {'label_layout': {}}
            if region:
                metadata['label_layout']['navigation_reserved_region_px'] = region
            area, safe, target, count = refill._candidate_source_pixels(picture, metadata, color, owners, 1)
            full_safe = refill._usable_pixels(color, picture, metadata)
            expected_target = full_safe & (owners == 1)
            rebuilt = np.zeros(owners.shape, bool)
            rebuilt[area] = target
            np.testing.assert_array_equal(rebuilt, expected_target)
            self.assertEqual(count, int(expected_target.sum()))
            actual_edges = np.zeros(owners.shape, bool)
            actual_edges[area] = refill._boundary_pixels(color[area], owners[area], safe)
            full_edges = refill._boundary_pixels(color, owners, full_safe)
            np.testing.assert_array_equal(actual_edges & (owners == 1), full_edges & (owners == 1))

    def test_boxed_glyph_matches_whole_image_expected_including_AA_pixel_damage(self):
        for alias in ('A', 'RABCD', 'RABCDEF12'):
            picture = Image.new('RGB', (128, 128), (90, 60, 30))
            draw = ImageDraw.Draw(picture)
            width = int(draw.textbbox((0, 0), alias)[2]) + 6
            box = [7, 31, 7 + width, 45]
            draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
            draw.text((10, 31), alias, fill=(255, 245, 180))
            row = {'display_label': alias, 'label_box_px': box}
            self.assertTrue(refill._glyph_survives(picture, row, alias))
            self.assertTrue(refill._boxed_glyph_survives(picture, row, alias))
            mask = Image.new('L', picture.size)
            ImageDraw.Draw(mask).text((10, 31), alias, fill=255)
            coverage = np.asarray(mask)
            ys, xs = np.nonzero((coverage > 0) & (coverage < 255))
            self.assertTrue(len(xs), 'This fixture requires actual anti-aliased glyph pixels')
            x, y = int(xs[0]), int(ys[0])
            pixel = picture.getpixel((x, y))
            picture.putpixel((x, y), (pixel[0] ^ 1, pixel[1], pixel[2]))
            self.assertFalse(refill._glyph_survives(picture, row, alias))
            self.assertFalse(refill._boxed_glyph_survives(picture, row, alias))

    def test_raw_upper_selection_matches_exhaustive_safe_count_and_boundary_order(self):
        def compare(raw, safe, boundary_ok):
            cases = list(zip(raw, range(3), range(3)))
            def qualify(index):
                return (safe[index], index) if safe[index] >= 16 and boundary_ok[index] else None
            actual = refill._best_source_by_upper_bound(cases, qualify)
            expected = sorted(((-safe[index], index) for index in range(3)
                if type(raw[index]) is int and raw[index] >= 16
                and safe[index] >= 16 and boundary_ok[index]))
            self.assertEqual(actual, expected[0][1] if expected else None)
        for raw in ((20, 25, 30), (24, 24, 24), (16, 128, 64), (1406, 1389, 965)):
            for safe in itertools.product(*[(0, 16, value) for value in raw]):
                for boundary in itertools.product((False, True), repeat=3):
                    compare(raw, safe, boundary)
        # Highest raw fails boundary; a UI reduction drops an early candidate
        # below a later safe-count winner. Neither case permits early pruning.
        compare((24, 25, 30), (24, 22, 30), (True, True, False))
        compare((24, 30, 100), (24, 30, 16), (True, True, True))
        calls = []
        result = refill._best_source_by_upper_bound([(20, 0, 0), (30, 2, 2)],
            lambda index: (calls.append(index) or (20, index)))
        self.assertEqual(result, 0)  # Equal safe count must retain lower index.
        self.assertEqual(calls, [2, 0])
        calls = []
        result = refill._best_source_by_upper_bound([(965, 0, 0), (1406, 1, 1), (1389, 2, 2)],
            lambda index: (calls.append(index) or ((1406 if index == 1 else 16), index)))
        self.assertEqual(result, 1)
        self.assertEqual(calls, [1])

    def test_raw_upper_invalid_counts_None_results_and_inconsistent_upper_fail_closed(self):
        invalid = (True, False, 16.0, float('nan'), float('inf'), None, '100', -1, 0, 15)
        for raw in invalid:
            self.assertIsNone(refill._best_source_by_upper_bound([(raw, 0, 'invalid')],
                lambda value: self.fail('Invalid metadata count must not qualify a source')))
        self.assertIsNone(refill._best_source_by_upper_bound([], lambda _: self.fail('empty')))
        self.assertIsNone(refill._best_source_by_upper_bound([(20, 0, 0)], lambda _: None))
        with self.assertRaises(ValueError):
            refill._best_source_by_upper_bound([(20, 0, 0)], lambda _: (21, 0))
        # bool/float coordinates numerically equal to a real left=1 cannot
        # become valid ints merely by translating the box into crop space.
        picture = Image.new('RGB', (128, 128))
        draw = ImageDraw.Draw(picture)
        alias = 'RABCD'
        width = int(draw.textbbox((0, 0), alias)[2]) + 6
        valid = [1, 31, 1 + width, 45]
        draw.rectangle(valid, fill=(18, 22, 30), outline=(150, 145, 110))
        draw.text((4, 31), alias, fill=(255, 245, 180))
        for box in (tuple(valid), [True, *valid[1:]], [1.0, *valid[1:]],
                    [np.int64(1), *valid[1:]], valid[:3], None):
            row = {'display_label': alias, 'label_box_px': box}
            self.assertFalse(refill._glyph_survives(picture, row, alias))
            self.assertFalse(refill._boxed_glyph_survives(picture, row, alias))

    def test_bound_clock_does_not_follow_attention_stdlib_mock(self):
        with patch('time.perf_counter', return_value=-123.):
            self.assertGreaterEqual(refill.visible_refill_clock(), 0.)

    def test_private_proposal_defers_whole_canvas_copy_and_composes_identical_pixels(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for size in (256, 384):
                collector, canvas, meta, meshes, _ = prepared(size)
                before = copy.deepcopy(meta)
                with patch.object(canvas, 'copy', side_effect=AssertionError('router must compose')):
                    proposal, visual, receipt = finish(collector, canvas, meta, meshes, proposal_only=True)
                self.assertFalse(receipt['applied'], receipt)
                self.assertEqual(receipt['status'], 'proposal_ready')
                self.assertEqual(receipt['reason'], 'qualified_single_view_proposal')
                self.assertEqual(receipt['new_readable_object_ids'], [])
                self.assertEqual(receipt['actual_delivered_default_related_count'],
                                 len(receipt['actual_base_drawn_selected_object_ids']))
                self.assertIs(type(proposal), refill.VisibleRefillProposal)
                self.assertIs(proposal.source_canvas, canvas)
                self.assertIs(proposal.source_metadata, meta)
                self.assertEqual(proposal.tile.size, (size, size))
                self.assertEqual(proposal.tile.mode, 'RGB')
                self.assertTrue(proposal.tile.readonly)
                self.assertIs(proposal.tile.im, proposal.tile_core)
                self.assertEqual(proposal.object_id, receipt['candidate_readable_object_ids'][0])
                self.assertEqual(collector._views, {})
                self.assertEqual(meta, before)
                self.assertTrue(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))
                self.assertFalse(receipt['applied'])  # Only the router can publish a committed image.
                composed = canvas.copy()
                composed.paste(proposal.tile, ((proposal.view_index % 2) * size,
                                               (proposal.view_index // 2) * size))
                direct, direct_canvas, direct_meta, direct_meshes, _ = prepared(size)
                expected, expected_meta, expected_receipt = finish(direct, direct_canvas, direct_meta, direct_meshes)
                self.assertTrue(expected_receipt['applied'])
                self.assertEqual(composed.tobytes(), expected.tobytes())
                self.assertEqual(visual, expected_meta)

    def test_private_proposal_identity_sources_and_replay_are_one_shot(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for invalid in ('forged', 'canvas', 'metadata', 'unknown'):
                collector, canvas, meta, meshes, _ = prepared()
                proposal, _, receipt = finish(collector, canvas, meta, meshes, proposal_only=True)
                self.assertFalse(receipt['applied'])
                self.assertEqual(receipt['status'], 'proposal_ready')
                attempted = proposal
                source_canvas, source_meta = canvas, meta
                if invalid == 'forged':
                    attempted = refill.VisibleRefillProposal(proposal.tile, proposal.tile_core,
                        proposal.view_index, proposal.object_id, canvas, meta)
                elif invalid == 'canvas':
                    source_canvas = canvas.copy()
                elif invalid == 'metadata':
                    source_meta = copy.deepcopy(meta)
                else:
                    attempted = object()
                self.assertFalse(collector.claim_proposal(attempted,
                    canvas=source_canvas, metadata=source_meta))
                self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))
            collector, canvas, meta, meshes, _ = prepared()
            proposal, _, _ = finish(collector, canvas, meta, meshes, proposal_only=True)
            plan, pool = bundle(meshes)
            foreign = refill.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot')
            self.assertFalse(foreign.claim_proposal(proposal, canvas=canvas, metadata=meta))
            self.assertTrue(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))
            self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))

    def test_private_proposal_rejects_COW_mutation_and_cannot_be_persisted(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, meta, meshes, _ = prepared()
            proposal, _, receipt = finish(collector, canvas, meta, meshes, proposal_only=True)
            self.assertFalse(receipt['applied'])
            self.assertEqual(receipt['status'], 'proposal_ready')
            with self.assertRaises(AttributeError):
                proposal.view_index = 3
            with self.assertRaises(TypeError):
                pickle.dumps(proposal)
            proposal.tile.putpixel((0, 0), (1, 2, 3))
            self.assertIsNot(proposal.tile.im, proposal.tile_core)
            self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))

    def test_default_failure_invalid_mode_and_second_finish_do_not_leave_issued_proposals(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, meta, meshes, _ = prepared()
            output, _, receipt = finish(collector, canvas, meta, meshes)
            self.assertTrue(receipt['applied'])
            self.assertIsInstance(output, Image.Image)
            self.assertIsNone(collector._issued_proposal)
            for mode in (True, 0, None, 'yes'):
                collector, canvas, meta, meshes, _ = prepared()
                with patch.object(refill, '_glyph_survives', return_value=False):
                    output, visual, receipt = finish(collector, canvas, meta, meshes, proposal_only=mode)
                self.assertFalse(receipt['applied'])
                self.assertIs(output, canvas)
                self.assertIs(visual, meta)
                self.assertIsNone(collector._issued_proposal)
            collector, canvas, meta, meshes, _ = prepared()
            proposal, _, receipt = finish(collector, canvas, meta, meshes, proposal_only=True)
            self.assertFalse(receipt['applied'])
            self.assertEqual(receipt['status'], 'proposal_ready')
            output, visual, receipt = finish(collector, canvas, meta, meshes, proposal_only=True)
            self.assertEqual(receipt['reason'], 'refill_context_already_consumed')
            self.assertIs(output, canvas)
            self.assertIs(visual, meta)
            self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=meta))


if __name__ == '__main__':
    unittest.main()
