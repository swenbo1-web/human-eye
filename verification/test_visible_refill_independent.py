"""Independent delivery, safe-pixel, retained-memory and one-shot boundaries.

Frozen clocks exercise policy branches only; these are not cost/adoption trials.
"""
import copy
import gc
import hashlib
import pickle
import unittest
import weakref
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin import auto_router
from human_eye_plugin import visible_refill as refill
from verification.test_visible_refill_policy import bundle, finish, prepared, priority_scene


def pixel_digest(picture):
    return hashlib.sha256(picture.tobytes()).hexdigest()


def enumerated_owner_boundaries(color, owners, safe, owner, final_equal=None):
    """Full-frame integer four-neighbour oracle; no crop or engine helper."""
    height, width = owners.shape
    found = set()
    for y in range(height):
        for x in range(width):
            if int(owners[y, x]) != owner or not bool(safe[y, x]):
                continue
            if final_equal is not None and not bool(final_equal[y, x]):
                continue
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                yy, xx = y + dy, x + dx
                if not (0 <= yy < height and 0 <= xx < width):
                    continue
                if (not bool(safe[yy, xx]) or int(owners[yy, xx]) == owner
                        or final_equal is not None and not bool(final_equal[yy, xx])):
                    continue
                squared = sum((int(color[y, x, channel]) - int(color[yy, xx, channel])) ** 2
                              for channel in range(3))
                if squared >= 24 * 24:
                    found.add((y, x))
                    break
    return found


class IndependentVisibleRefillTests(unittest.TestCase):
    def assert_original(self, result, canvas, metadata):
        output, visual, receipt = result
        self.assertFalse(receipt['applied'], receipt)
        self.assertIs(output, canvas)
        self.assertIs(visual, metadata)
        self.assertEqual(receipt['new_readable_object_ids'], [])
        return receipt

    def test_nav_reserved_band_and_row17_are_not_confused_with_geometry(self):
        raw = np.full((128, 128, 3), (80, 90, 100), np.uint8)
        picture = Image.fromarray(raw.copy())
        metadata = {'label_layout': {'navigation_reserved_region_px': [0, 85, 128, 113]}}
        safe = refill._usable_pixels(raw, picture, metadata)
        self.assertFalse(safe[16, 30])
        self.assertTrue(safe[17, 30])
        self.assertTrue(safe[84, 30])
        self.assertFalse(safe[85:128, 30].any())
        self.assertFalse(safe[:, 0].any())
        self.assertFalse(safe[:, 127].any())
        # Real UI strokes cannot become contrast evidence just because they
        # fall above the reserved footer.
        picture.putpixel((30, 40), (255, 207, 88))
        self.assertFalse(refill._usable_pixels(raw, picture, metadata)[40, 30])

    def test_decreasing_uint8_values_do_not_wrap_into_a_readable_boundary(self):
        raw = np.full((8, 8, 3), (250, 250, 250), np.uint8)
        raw[2:6, 2:6] = (245, 250, 250)
        owners = np.zeros((8, 8), np.int32)
        owners[2:6, 2:6] = 1
        boundary = refill._boundary_pixels(raw, owners, np.ones((8, 8), bool))
        self.assertEqual(int(np.count_nonzero(boundary & (owners == 1))), 0)

    def test_four_edges_of_one_owner_pixel_are_only_one_boundary_pixel(self):
        raw = np.zeros((5, 5, 3), np.uint8)
        raw[2, 2] = (255, 255, 255)
        owners = np.zeros((5, 5), np.int32)
        owners[2, 2] = 1
        boundary = refill._boundary_pixels(raw, owners, np.ones((5, 5), bool))
        self.assertEqual(int(np.count_nonzero(boundary & (owners == 1))), 1)

    def test_successful_collector_cannot_replay_against_original_or_delivered_canvas(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, records = prepared()
            output, visual, receipt = finish(collector, canvas, metadata, meshes)
            self.assertTrue(receipt['applied'], receipt)
            index = receipt['source_view_index']
            _, raw_color, raw_owners = records[index]
            tile = np.asarray(output.crop(((index % 2) * 256, (index // 2) * 256,
                                          (index % 2 + 1) * 256, (index // 2 + 1) * 256)))
            # The optimized changed-point delta must equal a fresh full-frame
            # recount, including any old UI/label pixels that remain present.
            full_count = int(np.count_nonzero((raw_owners >= 0) & np.all(tile == raw_color, axis=2)))
            self.assertEqual(visual['views'][index]['geometry_pixels_unchanged_by_annotations'], full_count)
            delivered_hash = pixel_digest(output)
            for current, current_meta in ((canvas, metadata), (output, visual)):
                replay = self.assert_original(finish(collector, current, current_meta, meshes), current, current_meta)
                self.assertEqual(replay['reason'], 'refill_context_already_consumed')
            self.assertEqual(pixel_digest(output), delivered_hash)
            self.assertEqual(collector._views, {})

    def test_budget_rejection_consumes_context_and_cannot_retry_into_a_gain(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared()
            first = self.assert_original(finish(collector, canvas, metadata, meshes, remaining_budget_ms=0.), canvas, metadata)
            self.assertEqual(first['reason'], 'shared_refill_budget_unavailable')
            second = self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)
            self.assertEqual(second['reason'], 'refill_context_already_consumed')
            self.assertEqual(collector._views, {})

    def test_nonfinite_or_boolean_remaining_budget_never_certifies_delivery(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for value in (float('nan'), float('inf'), -1., True):
                with self.subTest(value=value):
                    collector, canvas, metadata, meshes, _ = prepared()
                    receipt = self.assert_original(finish(collector, canvas, metadata, meshes,
                        remaining_budget_ms=value), canvas, metadata)
                    self.assertEqual(receipt['reason'], 'shared_refill_budget_unavailable')

    def test_old_camera_metadata_and_new_category_do_not_reuse_a_borrowed_view(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for change in ('camera', 'category'):
                with self.subTest(change=change):
                    collector, canvas, metadata, meshes, _ = prepared()
                    if change == 'camera':
                        metadata['views'][1]['projection_matrix'][0][0] += .01
                    else:
                        metadata['task_labels']['related_reasons']['risk-00-hidden'] = 'near_exact_clearance'
                    before = copy.deepcopy(metadata)
                    self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)
                    self.assertEqual(metadata, before)

    def test_source_picture_copy_on_write_invalidates_even_a_matching_canvas_tile(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, records = prepared()
            for index, (picture, _, _) in records.items():
                if index not in (0, 1, 2):
                    continue
                picture.putpixel((1, 30), (1, 2, 3))
                canvas.paste(picture, ((index % 2) * 256, (index // 2) * 256))
            self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)

    def test_actual_missing_text_pixels_roll_back_without_mocking_the_glyph_verdict(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, records = prepared()
            old_pixels = pixel_digest(canvas)
            old_meta = copy.deepcopy(metadata)
            old_raw = {index: (color.tobytes(), owners.tobytes()) for index, (_, color, owners) in records.items()}
            # Suppress actual new text drawing, rather than patching the
            # production glyph validator to return our expected answer.
            with patch.object(ImageDraw.ImageDraw, 'text', return_value=None):
                receipt = self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)
            self.assertFalse(receipt['readability']['complete_final_glyph'])
            self.assertEqual(receipt['reason'], 'refill_readability_not_delivered')
            self.assertEqual(pixel_digest(canvas), old_pixels)
            self.assertEqual(metadata, old_meta)
            self.assertEqual({i: (c.tobytes(), o.tobytes()) for i, (_, c, o) in records.items()}, old_raw)
            self.assertEqual(collector._views, {})

    def test_collector_does_not_keep_depth_arrays_between_render_and_finish(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            meshes = priority_scene()
            plan, pool = bundle(meshes)
            collector = refill.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot')
            depth_refs = []

            def observer(index, picture, meta, current_meshes, color, depth, owners):
                if index in (0, 1, 2):
                    depth_refs.append(weakref.ref(depth))
                collector.observe_view(index, picture, meta, current_meshes, color, depth, owners)

            canvas, metadata = rendering._render_scene_canvas_impl(meshes, 256,
                focal_id='focus', reference_id='reference', label_plan=plan, raw_observer=observer)
            gc.collect()
            self.assertEqual(len(depth_refs), 3)
            self.assertTrue(all(ref() is None for ref in depth_refs))
            self.assertGreater(collector._retained, 0)
            self.assertEqual(collector._retained, 3 * 256 * 256 * (3 + 4))
            finish(collector, canvas, metadata, meshes)
            self.assertEqual(collector._retained, 0)

    def test_truncated_diagnostics_do_not_leave_a_delivered_id_still_omitted(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            meshes = priority_scene()
            plan, pool = bundle(meshes)
            collector = refill.VisibleRefillCollector(plan, pool, scene_fingerprint='snapshot')

            def observer(index, picture, meta, current_meshes, color, depth, owners):
                # Preserve exact counts/reasons but shorten the diagnostic ID
                # listing before it is bound. The missing entry must not be
                # needed to update truthful final delivery counts.
                layout = meta['label_layout']
                layout['omitted_objects'] = []
                layout['omitted_objects_truncated'] = layout['omitted_object_count']
                collector.observe_view(index, picture, meta, current_meshes, color, depth, owners)

            canvas, metadata = rendering._render_scene_canvas_impl(meshes, 256,
                focal_id='focus', reference_id='reference', label_plan=plan, raw_observer=observer)
            output, visual, receipt = finish(collector, canvas, metadata, meshes)
            self.assertTrue(receipt['applied'], receipt)
            index = receipt['source_view_index']
            before = metadata['views'][index]['label_layout']
            after = visual['views'][index]['label_layout']
            self.assertEqual(after['omitted_object_count'], before['omitted_object_count'] - 1)
            self.assertEqual(after['omitted_objects_truncated'], after['omitted_object_count'])
            self.assertEqual(after['omitted_reason_counts'].get('outside_task_label_focus', 0),
                             before['omitted_reason_counts'].get('outside_task_label_focus', 0) - 1)
            self.assertEqual(receipt['prior_candidate_omission']['object_id'], 'risk-02-visible')
            self.assertEqual(receipt['prior_candidate_omission']['scope'], 'original_pre_refill_history')
            self.assertEqual(visual['task_labels'], metadata['task_labels'])

    def test_96pixel_original_image_does_not_opt_into_128pixel_refill_rules(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared(96)
            old_hash = pixel_digest(canvas)
            receipt = self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)
            self.assertEqual(canvas.size, (192, 192))
            self.assertEqual(pixel_digest(canvas), old_hash)
            self.assertEqual(receipt['candidate_raster_count'], 0)

    def test_owner_crop_matches_full_frame_neighbor_oracle_at_halos_and_safe_boundaries(self):
        rng = np.random.default_rng(73129)
        fixtures = []
        # Clipped corners, a one-column fragment, separated fragments, and a
        # fully excluded fragment exercise bbox/halo bounds independently.
        for points in ([(0, 0), (0, 1), (1, 0)], [(23, 30)],
                       [(8, 12), (9, 12), (10, 12)],
                       [(0, 0), (23, 30), (10, 15), (10, 17)]):
            color = rng.integers(0, 256, (24, 31, 3), dtype=np.uint8)
            owners = np.full((24, 31), -1, np.int32)
            for y, x in points:
                owners[y, x] = 2
            fixtures.append((color, owners, np.ones((24, 31), bool)))
        for _ in range(12):
            fixtures.append((rng.integers(0, 256, (24, 31, 3), dtype=np.uint8),
                             rng.integers(-1, 4, (24, 31), dtype=np.int32),
                             rng.random((24, 31)) > .3))
        for fi, (color, owners, safe) in enumerate(fixtures):
            final_equal = rng.random(owners.shape) > .2
            for stable in (None, final_equal, np.zeros(owners.shape, bool)):
                with self.subTest(fixture=fi, final_mask=stable is not None):
                    usable = safe if stable is None else safe & stable
                    boundary, target, ys, xs = refill._owner_boundary_pixels(color, owners, usable, 2)
                    actual = set(zip(*np.nonzero(boundary & (owners == 2))))
                    expected = enumerated_owner_boundaries(color, owners, safe, 2, stable)
                    self.assertEqual(actual, expected)
                    self.assertTrue(np.array_equal(target, usable & (owners == 2)))
                    self.assertEqual(set(zip(ys.tolist(), xs.tolist())), set(zip(*np.nonzero(target))))

    def test_late_output_paste_failure_cannot_leak_COW_rows_or_omission_updates(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared()
            old_meta = copy.deepcopy(metadata)
            old_pixels = pixel_digest(canvas)
            original_paste = Image.Image.paste

            def reject_output(picture, *args, **kwargs):
                if picture.size == canvas.size:
                    raise RuntimeError('late canvas composition after metadata preparation')
                return original_paste(picture, *args, **kwargs)

            with patch.object(Image.Image, 'paste', new=reject_output):
                receipt = self.assert_original(finish(collector, canvas, metadata, meshes), canvas, metadata)
            self.assertEqual(receipt['reason'], 'visible_candidate_refill_unavailable')
            self.assertEqual(metadata, old_meta)
            self.assertEqual(pixel_digest(canvas), old_pixels)
            self.assertEqual(collector._views, {})

    def test_boxed_glyph_matches_full_image_verifier_with_AA_damage_and_original_bounds(self):
        for alias in ('RABF1', 'R12345678', 'A'):
            text_box = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((3, 0), alias)
            width = text_box[2] + 3
            for left, top in ((1, 19), (126 - width, 98)):
                with self.subTest(alias=alias, left=left):
                    box = [left, top, left + width - 1, top + 14]
                    picture = Image.new('RGB', (128, 128), (80, 90, 100))
                    draw = ImageDraw.Draw(picture)
                    draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
                    draw.text((left + 3, top), alias, fill=(255, 245, 180))
                    row = {'label_box_px': box, 'display_label': alias}
                    self.assertTrue(refill._glyph_survives(picture, row, alias))
                    self.assertEqual(refill._boxed_glyph_survives(picture, row, alias),
                                     refill._glyph_survives(picture, row, alias))
                    mask = Image.new('L', (width, 15))
                    ImageDraw.Draw(mask).text((3, 0), alias, fill=255)
                    y, x = np.argwhere(np.asarray(mask) > 0)[0]
                    damaged = picture.copy()
                    point = (left + int(x), top + int(y))
                    red, green, blue = damaged.getpixel(point)
                    damaged.putpixel(point, (red ^ 1, green, blue))
                    self.assertFalse(refill._glyph_survives(damaged, row, alias))
                    self.assertFalse(refill._boxed_glyph_survives(damaged, row, alias))
                    invalid = ([True, top, box[2], box[3]], tuple(box),
                               [-1, top, box[2], box[3]], [left, top, 128, box[3]],
                               [left, top, left, box[3]])
                    for invalid_box in invalid:
                        changed = dict(row, label_box_px=invalid_box)
                        self.assertFalse(refill._glyph_survives(picture, changed, alias))
                        self.assertFalse(refill._boxed_glyph_survives(picture, changed, alias))

    def test_private_tile_proposal_is_pending_then_matches_default_caller_composition(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared()
            before = copy.deepcopy(metadata)
            original_pixels = pixel_digest(canvas)
            proposal, visual, receipt = finish(collector, canvas, metadata, meshes, proposal_only=True)
            self.assertIs(type(proposal), refill.VisibleRefillProposal)
            self.assertFalse(receipt['applied'])
            self.assertEqual(receipt['status'], 'proposal_ready')
            self.assertEqual(receipt['new_readable_object_ids'], [])
            self.assertEqual(receipt['candidate_readable_object_ids'], ['risk-02-visible'])
            self.assertEqual(receipt['actual_delivered_default_related_count'], 0)
            self.assertIs(proposal.source_canvas, canvas)
            self.assertIs(proposal.source_metadata, metadata)
            self.assertEqual(proposal.tile.size, (256, 256))
            self.assertEqual(proposal.tile.mode, 'RGB')
            self.assertTrue(proposal.tile.readonly)
            self.assertEqual(pixel_digest(canvas), original_pixels)
            self.assertEqual(metadata, before)
            self.assertTrue(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))
            output = canvas.copy()
            output.paste(proposal.tile, ((proposal.view_index % 2) * 256, (proposal.view_index // 2) * 256))
            self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))
            other, old_canvas, old_meta, old_meshes, _ = prepared()
            expected, expected_meta, adopted = finish(other, old_canvas, old_meta, old_meshes)
            self.assertTrue(adopted['applied'])
            self.assertEqual(output.tobytes(), expected.tobytes())
            self.assertEqual(visual, expected_meta)

    def test_fake_or_foreign_proposals_consume_no_unrelated_capability(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for kind in ('fake_same_fields', 'oversized_fake', 'foreign', 'plain_object'):
                with self.subTest(kind=kind):
                    collector, canvas, metadata, meshes, _ = prepared()
                    proposal, _, _ = finish(collector, canvas, metadata, meshes, proposal_only=True)
                    foreign = None
                    if kind == 'foreign':
                        foreign, fc, fm, fmesh, _ = prepared()
                        supplied, _, _ = finish(foreign, fc, fm, fmesh, proposal_only=True)
                    elif kind == 'plain_object':
                        supplied = object()
                    else:
                        tile = proposal.tile if kind == 'fake_same_fields' else Image.new('RGB', (257, 257))
                        supplied = refill.VisibleRefillProposal(tile, tile.im, proposal.view_index,
                            proposal.object_id, canvas, metadata)
                    self.assertFalse(collector.claim_proposal(supplied, canvas=canvas, metadata=metadata))
                    self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))
                    if foreign is not None:
                        self.assertTrue(foreign.claim_proposal(supplied, canvas=fc, metadata=fm))

    def test_claim_source_identity_is_stricter_than_equal_copied_pixels_or_metadata(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for kind in ('canvas', 'metadata'):
                with self.subTest(kind=kind):
                    collector, canvas, metadata, meshes, _ = prepared()
                    proposal, _, _ = finish(collector, canvas, metadata, meshes, proposal_only=True)
                    supplied_canvas = canvas.copy() if kind == 'canvas' else canvas
                    supplied_meta = copy.deepcopy(metadata) if kind == 'metadata' else metadata
                    self.assertEqual(supplied_canvas.tobytes(), canvas.tobytes())
                    self.assertEqual(supplied_meta, metadata)
                    self.assertFalse(collector.claim_proposal(proposal, canvas=supplied_canvas, metadata=supplied_meta))
                    self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))

    def test_tile_COW_shape_and_mode_mutations_reject_claim_without_altering_source(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            for operation in ('pixel', 'paste', 'thumbnail', 'alpha'):
                with self.subTest(operation=operation):
                    collector, canvas, metadata, meshes, _ = prepared()
                    before = copy.deepcopy(metadata)
                    old_pixels = pixel_digest(canvas)
                    proposal, _, _ = finish(collector, canvas, metadata, meshes, proposal_only=True)
                    if operation == 'pixel':
                        proposal.tile.putpixel((0, 0), (1, 2, 3))
                    elif operation == 'paste':
                        proposal.tile.paste((1, 2, 3), (0, 0, 1, 1))
                    elif operation == 'thumbnail':
                        proposal.tile.thumbnail((128, 128))
                    else:
                        proposal.tile.putalpha(255)
                    self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))
                    self.assertFalse(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))
                    self.assertEqual(pixel_digest(canvas), old_pixels)
                    self.assertEqual(metadata, before)

    def test_proposal_cannot_be_serialized_or_retargeted_through_public_fields(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared()
            proposal, _, _ = finish(collector, canvas, metadata, meshes, proposal_only=True)
            for field, value in (('view_index', 3), ('object_id', 'other'), ('tile', canvas),
                                 ('source_canvas', canvas.copy()), ('source_metadata', {})):
                with self.assertRaises(AttributeError):
                    setattr(proposal, field, value)
            with self.assertRaises(TypeError):
                pickle.dumps(proposal)
            with self.assertRaises(TypeError):
                copy.deepcopy(proposal)
            self.assertTrue(collector.claim_proposal(proposal, canvas=canvas, metadata=metadata))

    def test_held_or_replayed_finish_never_issues_a_delivered_proposal(self):
        with patch.object(refill, 'visible_refill_clock', return_value=0.):
            collector, canvas, metadata, meshes, _ = prepared()
            self.assert_original(finish(collector, canvas, metadata, meshes,
                proposal_only=True, remaining_budget_ms=0.), canvas, metadata)
            self.assertFalse(collector.claim_proposal(object(), canvas=canvas, metadata=metadata))
            self.assert_original(finish(collector, canvas, metadata, meshes, proposal_only=True), canvas, metadata)
            self.assertIsNone(collector._issued_proposal)

    def test_tile_change_witness_and_fallback_match_complete_RGB_pixel_enumeration(self):
        size = 4
        original = Image.new('RGB', (2 * size, 2 * size), (29, 80, 121))
        hints = ([0, 0, 1, 1], None, (0, 0, 1, 1), [True, 0, 1, 1],
                 [0., 0, 1, 1], [-1, 0, 1, 1], [0, 0, size, size], 'box')
        for view_index in range(4):
            x0, y0 = (view_index % 2) * size, (view_index // 2) * size
            baseline = original.crop((x0, y0, x0 + size, y0 + size))
            for hint in hints:
                self.assertFalse(auto_router._refill_tile_has_new_pixels(baseline.copy(), original,
                    view_index=view_index, quad_size=size, label_box=hint))
            for y in range(size):
                for x in range(size):
                    for channel in range(3):
                        tile = baseline.copy()
                        pixel = list(tile.getpixel((x, y)))
                        pixel[channel] ^= 1
                        tile.putpixel((x, y), tuple(pixel))
                        expected = any(tile.getpixel((xx, yy)) != original.getpixel((x0 + xx, y0 + yy))
                                       for yy in range(size) for xx in range(size))
                        for hint in hints:
                            self.assertEqual(auto_router._refill_tile_has_new_pixels(tile, original,
                                view_index=view_index, quad_size=size, label_box=hint), expected,
                                (view_index, x, y, channel, hint))


if __name__ == '__main__':
    unittest.main()
