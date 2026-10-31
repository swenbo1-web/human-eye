"""Owner-specific annotation footprints and bounded label placement regressions."""
from types import SimpleNamespace
import copy
import hashlib
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_plugin import scene_rendering as rendering


def visible_meshes(identities):
    return [SimpleNamespace(object_id=identity, mark_label='#' + identity) for identity in identities]


def draw_labels(meshes, owners, priority, protected=None, *, name='Q1 XY TOP'):
    size = owners.shape[0]
    pixels = np.empty((size, size, 3), dtype=np.uint8)
    pixels[:] = (18, 22, 30)
    for index in range(len(meshes)):
        pixels[owners == index] = (65 + index * 7, 105 + index * 3, 165 - index * 5)
    image = Image.fromarray(pixels)
    metadata = {'name': name, 'projection': 'orthographic', 'm_per_pixel': .001,
                'target_object_ids': list(priority) if name == 'Q4 CONTACT' else [mesh.object_id for mesh in meshes],
                'label_priority_object_ids': list(priority)}
    if protected is not None:
        metadata['label_protected_object_ids'] = list(protected)
    rendering._annotate(image, meshes, None, None, metadata, owners)
    return image, metadata, pixels


def independent_label_mask(rows, size, *, historical=False, optimizer=False):
    """Measure Pillow's inclusive rectangles and the actually specified leaders."""
    mask = Image.new('1', (size, size))
    anchors = Image.new('1', (size, size))
    draw, anchor_draw = ImageDraw.Draw(mask), ImageDraw.Draw(anchors)
    for row in rows:
        x, y = row['projected_center_px']
        x0, y0, x1, y1 = row['label_box_px']
        if historical or ('leader_endpoint_px' not in row and not optimizer):
            endpoint = x0, y0 + 7
        elif 'leader_endpoint_px' in row:
            endpoint = tuple(row['leader_endpoint_px'])
        else:
            # Independent projection to the closed rectangle; test fixtures
            # keep anchors outside boxes. Explicit interior cases are tested
            # separately against the production edge helper.
            endpoint = max(x0, min(x, x1)), max(y0, min(y, y1))
        draw.line((x, y, *endpoint), fill=1, width=1)
        draw.rectangle((x0, y0, x1, y1), fill=1)
        anchor_draw.point((x, y), fill=1)
    return np.asarray(mask, dtype=bool), np.asarray(anchors, dtype=bool)


def owner_coverage(image, original, metadata, owners, *, historical=False):
    """Separate all actual RGB changes, label footprints, anchors and bands."""
    size = owners.shape[0]
    changed = np.any(np.asarray(image) != original, axis=2)
    labels, anchors = independent_label_mask(metadata['projected_labels'], size, historical=historical)
    bands = np.zeros(owners.shape, dtype=bool)
    bands[:17] = True
    bands[size - 15:] = True
    rows = {}
    for index in np.unique(owners[owners >= 0]):
        own = owners == index
        count = int(np.count_nonzero(own))
        rows[int(index)] = {'visible_pixels': count,
            'all_annotations_changed_pixels': int(np.count_nonzero(own & changed)),
            'all_annotations_changed_ratio': float(np.count_nonzero(own & changed) / count),
            'label_box_and_leader_pixels': int(np.count_nonzero(own & labels)),
            'label_box_and_leader_ratio': float(np.count_nonzero(own & labels) / count),
            'anchor_pixels': int(np.count_nonzero(own & anchors)),
            'title_footer_changed_pixels': int(np.count_nonzero(own & changed & bands))}
    return rows


def historical_penalty(owners, meshes):
    """The e09 weights, independently constructed for the frozen comparison."""
    counts = np.bincount(owners[owners >= 0], minlength=len(meshes))
    penalty = np.zeros(owners.shape, dtype=np.float32)
    for index, count in enumerate(counts):
        if count:
            penalty[owners == index] = min(16., max(1., owners.shape[0] ** 2 / (4 * count)))
    return penalty


def historical_local_box(draw, text, anchor, size, occupied, foreground):
    """Frozen e09 eight-position selector; excludes the old right/bottom edge."""
    width = int(draw.textbbox((0, 0), text)[2]) + 6
    height = 14
    candidates = []
    for dx, dy in [(8, -20), (8, 8), (-width - 8, -20), (-width - 8, 8),
                   (8, -40), (-width - 8, 28), (18, 28), (-width - 18, -40)]:
        x = max(2, min(int(anchor[0] + dx), size - width - 2))
        y = max(19, min(int(anchor[1] + dy), size - height - 19))
        box = (x, y, x + width, y + height)
        if any(box[0] < old[2] + 2 and box[2] > old[0] - 2
               and box[1] < old[3] + 2 and box[3] > old[1] - 2 for old in occupied):
            continue
        cost = float(np.sum(foreground[y:y + height, x:x + width]))
        candidates.append((cost, abs(x - anchor[0]) + abs(y - anchor[1]), box))
    return min(candidates, key=lambda item: item[:2])[2] if candidates else None


def historical_contact_annotations(meshes, owners, original, priority, *, name='Q4 CONTACT'):
    """Frozen e09 annotation code path, independent of current placement helpers."""
    size = owners.shape[0]
    image = Image.fromarray(original.copy())
    draw = ImageDraw.Draw(image)
    foreground = owners >= 0
    counts = np.bincount(owners[foreground], minlength=len(meshes))
    penalty = historical_penalty(owners, meshes)
    ranked = sorted(range(len(meshes)), key=lambda index:
        (priority.index(meshes[index].object_id) if meshes[index].object_id in priority else len(priority),
         -counts[index], meshes[index].object_id))
    anchors, occupied = [], []
    for index in ranked:
        mesh = meshes[index]
        if counts[index] < 8 or len(anchors) >= 8 or size < 96:
            continue
        ys, xs = np.nonzero(owners == index)
        center = np.array([np.mean(xs), np.mean(ys)])
        nearest = int(np.argmin((xs - center[0]) ** 2 + (ys - center[1]) ** 2))
        anchor = [int(xs[nearest]), int(ys[nearest])]
        label = 'O' + hashlib.sha256(mesh.object_id.encode('utf-8')).hexdigest()[:8].upper()
        box = historical_local_box(draw, label, anchor, size, occupied, penalty)
        if box is None:
            continue
        occupied.append(box)
        draw.line((anchor[0], anchor[1], box[0], box[1] + 7), fill=(245, 218, 135), width=1)
        draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
        draw.text((box[0] + 3, box[1]), label, fill=(255, 245, 180))
        anchors.append({'object_id': mesh.object_id, 'mark_label': mesh.mark_label,
            'stable_label': label, 'projected_center_px': anchor, 'label_box_px': list(box),
            'surface_visible_pixels': int(counts[index]), 'anchor_source': 'current_full_scene_depth_winner'})
    draw.rectangle((0, 0, size - 1, 16), fill=(28, 34, 46))
    draw.text((3, 1), name, fill=(235, 242, 255))
    bar_px = max(8, size // 4)
    draw.rectangle((0, size - 15, size - 1, size - 1), fill=(18, 22, 30))
    draw.line((4, size - 4, 4 + bar_px, size - 4), fill=(225, 230, 240), width=2)
    draw.text((4, size - 15), f'{bar_px * .001:.3g} m', fill=(235, 242, 255))
    draw.rectangle((0, 0, size - 1, size - 1), outline=(70, 82, 105))
    return image, anchors


def panel_fixture():
    identities = ['focal', 'reference'] + [f'obstacle-{index:02d}' for index in range(8)]
    meshes = visible_meshes(identities)
    owners = np.full((384, 384), -1, dtype=np.int32)
    owners[90:295, 100:285] = 1
    owners[182:202, 177:208] = 0
    for index, x in enumerate((30, 90, 150, 210, 270, 330)):
        owners[42:45, x:x + 3] = index + 2
    owners[338:341, 50:53] = 8
    owners[338:341, 330:333] = 9
    return meshes, owners


def finite_label_candidates(draw, text, anchor, size, bounds, occupied):
    """Independent enumeration of the documented 8 local + 4 outer positions."""
    width, height = int(draw.textbbox((0, 0), text)[2]) + 6, 14
    x, y = anchor
    left, top, right, bottom = bounds
    positions = [(x + 8, y - 20), (x + 8, y + 8),
                 (x - width - 8, y - 20), (x - width - 8, y + 8),
                 (x + 8, y - 40), (x - width - 8, y + 28),
                 (x + 18, y + 28), (x - width - 18, y - 40),
                 (x - width // 2, top - height - 3),
                 (x - width // 2, bottom + 3),
                 (left - width - 3, y - height // 2),
                 (right + 3, y - height // 2)]
    boxes = []
    for px, py in positions:
        px, py = max(2, min(int(px), size - width - 2)), max(19, min(int(py), size - height - 19))
        box = (px, py, px + width, py + height)
        if box in boxes:
            continue
        if any(box[0] < old[2] + 2 and box[2] > old[0] - 2
               and box[1] < old[3] + 2 and box[3] > old[1] - 2 for old in occupied):
            continue
        boxes.append(box)
    return boxes


class LabelOcclusionRepairTests(unittest.TestCase):
    def test_large_surface_bound_skips_all_roi_stats_and_keeps_legacy_context_pixels(self):
        owners = np.zeros((384, 384), dtype=np.int32)
        owners[:, 192:] = 1
        meshes = visible_meshes(['focal', 'reference'])
        with patch.object(rendering, '_label_coverage_stats', side_effect=AssertionError('The area bound proves low risk')), \
             patch.object(rendering.np, 'zeros', wraps=np.zeros) as allocations:
            image, metadata, original = draw_labels(meshes, owners, ['focal', 'reference'])
        reference, rows = historical_contact_annotations(meshes, owners, original,
            ['focal', 'reference'], name='Q1 XY TOP')
        np.testing.assert_array_equal(np.asarray(image), np.asarray(reference))
        self.assertEqual(metadata['projected_labels'], rows)
        self.assertEqual(metadata['label_layout_profile'], 'adaptive_context_benefit_v1')
        self.assertEqual(metadata['label_layout']['optimizer_attempts'], 0)
        self.assertEqual(metadata['label_layout']['optimizer_applied'], 0)
        self.assertTrue(all('leader_endpoint_px' not in row for row in rows))
        self.assertFalse(any(call.args[0] == owners.shape for call in allocations.call_args_list))

    def test_trigger_uses_one_declared_five_percent_budget_on_both_sides(self):
        # The old two-pixel footprint has enough possible gain to reach16;
        # the new anchor lower bound therefore leaves the risk trigger observable.
        for count, attempts in ((41, 0), (40, 0), (39, 1)):
            owners = np.full((384, 384), -1, dtype=np.int32)
            owners[190, 180:200] = 0
            owners[191, 180:180 + count - 20] = 0
            with self.subTest(surface_pixels=count):
                _, metadata, _ = draw_labels(visible_meshes(['focal']), owners, ['focal'])
                self.assertEqual(metadata['label_layout']['optimizer_attempts'], attempts)
                if not attempts:
                    self.assertEqual(metadata['label_layout']['optimizer_applied'], 0)
                    self.assertNotIn('leader_endpoint_px', metadata['projected_labels'][0])

    def test_anchor_gain_upper_bound_skips_new_selector_for_high_risk_tiny_surface(self):
        owners = np.full((384, 384), -1, dtype=np.int32)
        owners[190, 188:196] = 0
        with patch.object(rendering, '_label_box', wraps=rendering._label_box) as choose, \
             patch.object(rendering, '_label_coverage_stats', wraps=rendering._label_coverage_stats) as stats:
            _, metadata, _ = draw_labels(visible_meshes(['focal']), owners, ['focal'])
        self.assertEqual(stats.call_count, 1)
        self.assertEqual(choose.call_count, 1)
        self.assertEqual(choose.call_args.kwargs['profile'], rendering.CONTACT_LABEL_PROFILE)
        self.assertEqual(metadata['label_layout']['optimizer_attempts'], 0)
        self.assertEqual(metadata['label_layout']['optimizer_applied'], 0)
        self.assertNotIn('leader_endpoint_px', metadata['projected_labels'][0])

    def test_risky_label_adopts_only_measured_owner_and_foreground_safe_gain(self):
        owners = np.full((384, 384), -1, dtype=np.int32)
        owners[190:192, 190:194] = 0
        meshes = visible_meshes(['focal'])
        image, metadata, original = draw_labels(meshes, owners, ['focal'])
        reference, old_rows = historical_contact_annotations(meshes, owners, original, ['focal'], name='Q1 XY TOP')
        self.assertEqual(len(metadata['projected_labels']), len(old_rows))
        self.assertEqual(metadata['label_layout']['optimizer_attempts'], 1)
        self.assertEqual(metadata['label_layout']['optimizer_applied'], 1)
        self.assertIn('leader_endpoint_px', metadata['projected_labels'][0])
        old_mask, _ = independent_label_mask(old_rows, 384)
        new_mask, _ = independent_label_mask(metadata['projected_labels'], 384)
        penalty = historical_penalty(owners, meshes)
        self.assertGreater(np.count_nonzero(old_mask & (owners == 0)) / 8, .05)
        self.assertLessEqual(np.count_nonzero(new_mask & (owners == 0)), np.count_nonzero(old_mask & (owners == 0)))
        self.assertLessEqual(np.count_nonzero(new_mask & (owners >= 0)), np.count_nonzero(old_mask & (owners >= 0)))
        self.assertGreaterEqual(float(penalty[old_mask].sum(dtype=np.float64) - penalty[new_mask].sum(dtype=np.float64)), 16.)
        self.assertFalse(np.array_equal(np.asarray(image), np.asarray(reference)))

    def test_risky_label_without_gain_keeps_exact_legacy_row_and_pixels(self):
        owners = np.full((384, 384), -1, dtype=np.int32)
        owners[190, 188:196] = 0
        meshes = visible_meshes(['focal'])
        image, metadata, original = draw_labels(meshes, owners, ['focal'])
        reference, rows = historical_contact_annotations(meshes, owners, original, ['focal'], name='Q1 XY TOP')
        self.assertEqual(metadata['label_layout']['optimizer_attempts'], 0)
        self.assertEqual(metadata['label_layout']['optimizer_applied'], 0)
        self.assertEqual(metadata['projected_labels'], rows)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(reference))

    def test_positive_weighted_gain_is_rejected_if_another_protected_owner_increases(self):
        owners = np.full((384, 384), -1, dtype=np.int32)
        owners[190:192, 190:194] = 0
        owners[20:120, 20:120] = 1
        owners[170, 199] = 1
        owners[192:195, 191:196] = 2
        meshes = visible_meshes(['focal', 'reference', 'obstacle'])
        counts = np.bincount(owners[owners >= 0], minlength=3)
        penalty = historical_penalty(owners, meshes)
        draw = ImageDraw.Draw(Image.new('RGB', (384, 384)))
        text, anchor = 'O12345678', (191, 190)
        old_box = historical_local_box(draw, text, anchor, 384, [], penalty)
        width = int(draw.textbbox((0, 0), text)[2]) + 6
        unsafe_box = (199, 170, 199 + width, 184)
        old_mask, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': old_box}], 384)
        new_mask, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': unsafe_box}], 384, optimizer=True)
        self.assertGreaterEqual(float(penalty[old_mask].sum(dtype=np.float64) - penalty[new_mask].sum(dtype=np.float64)), 16.)
        self.assertLessEqual(np.count_nonzero(new_mask & (owners >= 0)), np.count_nonzero(old_mask & (owners >= 0)))
        self.assertGreater(np.count_nonzero(new_mask & (owners == 1)), np.count_nonzero(old_mask & (owners == 1)))
        original_selector = rendering._label_box

        def selector(*args, **kwargs):
            return original_selector(*args, **kwargs) if kwargs.get('profile') == rendering.CONTACT_LABEL_PROFILE else unsafe_box

        ys, xs = np.nonzero(owners == 0)
        with patch.object(rendering, '_label_box', side_effect=selector):
            box, endpoint, attempted, applied = rendering._adaptive_context_label(draw, text,
                anchor, 384, [], penalty, owners, counts, (0, 1), (xs, ys))
        self.assertTrue(attempted)
        self.assertFalse(applied)
        self.assertEqual(box, old_box)
        self.assertEqual(endpoint, (old_box[0], old_box[1] + 7))

    def test_endpoint_override_matches_exact_legacy_line_and_preserves_tuple_contract(self):
        owners = np.zeros((128, 128), dtype=np.int32)
        owners[:, 64:] = 1
        foreground = np.ones((128, 128), dtype=np.float32)
        anchor, box = (100, 100), (40, 40, 70, 54)
        endpoint = (box[0], box[1] + 7)
        row = {'projected_center_px': anchor, 'label_box_px': box, 'leader_endpoint_px': endpoint}
        footprint, _ = independent_label_mask([row], 128)
        result = rendering._label_coverage_stats(foreground, owners, (0, 1), anchor, box, endpoint=endpoint)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], int(np.count_nonzero(footprint)))
        self.assertEqual(result[1], [int(np.count_nonzero(footprint & (owners == index))) for index in (0, 1)])

    def test_L_slot_caption_keeps_exact_measurement_geometry_camera_and_clear_label_band(self):
        from verification.test_orthogonal_contact_visual import caption_fixture
        from human_eye_plugin.attention_rendering import _annotate_orthogonal_target_measurement

        image, metadata, meshes, options = caption_fixture('L_slot', size=256)
        original_pixels = np.asarray(image).copy()
        original_metadata = copy.deepcopy(metadata)
        original_meshes = [copy.deepcopy(mesh.to_dict()) for mesh in meshes]
        original_contact = copy.deepcopy(options['contact'])
        output, visual = _annotate_orthogonal_target_measurement(image, metadata, meshes, **options)
        view = visual['views'][3]
        overlay = view['measurement_overlay']
        self.assertEqual(overlay['signed_clearance_m'], .04)
        self.assertEqual(overlay['witness_points_world_m'], [original_contact[key]
                         for key in ('point_a_world', 'point_b_world')])
        self.assertFalse(overlay['camera_changed'])
        self.assertFalse(overlay['execution_authority'])
        left, top, right, bottom = overlay['caption_box_px']
        labels, _ = independent_label_mask(view['projected_labels'], 256)
        self.assertFalse(labels[top:bottom, left:right].any())
        for row in view['projected_labels']:
            if 'leader_endpoint_px' in row:
                self.assertLessEqual(row['label_box_px'][3], top - 3)
        eligible = {identity for identity in view['target_object_ids'] if view['object_visible_pixels'][identity] >= 8}
        self.assertTrue(eligible.issubset({row['object_id'] for row in view['projected_labels']}))
        unchanged_view = copy.deepcopy(view)
        unchanged_view.pop('measurement_overlay')
        self.assertEqual(unchanged_view, metadata['views'][3])
        changed = np.any(np.asarray(output) != original_pixels, axis=2)
        allowed = np.zeros(changed.shape, dtype=bool)
        allowed[256 + top:256 + bottom, 256 + left:256 + right] = True
        self.assertTrue(changed.any())
        self.assertFalse(np.any(changed & ~allowed))
        np.testing.assert_array_equal(np.asarray(image), original_pixels)
        self.assertEqual(metadata, original_metadata)
        self.assertEqual([mesh.to_dict() for mesh in meshes], original_meshes)
        self.assertEqual(options['contact'], original_contact)

    def test_caption_reservation_bounds_inclusive_boxes_and_actual_nearest_leaders(self):
        region = (1, 227, 255, 255)
        draw = ImageDraw.Draw(Image.new('RGB', (256, 256)))
        anchor = (100, 215)
        box = rendering._label_box(draw, 'O12345678', anchor, 256, [],
            np.zeros((256, 256), dtype=np.float32), surface_bounds=(60, 180, 140, 218),
            caption_reserved_region=region)
        self.assertIsNotNone(box)
        self.assertLessEqual(box[3], region[1] - 3)
        footprint, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': box}], 256, optimizer=True)
        self.assertFalse(footprint[227:255, 1:255].any())
        with patch.object(rendering.Image, 'new', side_effect=AssertionError('Ordinary above-band anchors need no mask')):
            self.assertTrue(rendering._label_avoids_caption(anchor, box, region))
        self.assertFalse(rendering._label_avoids_caption((100, 240), (10, 180, 75, 194), region))
        self.assertFalse(rendering._label_avoids_caption((0, 255), (2, 180, 65, 194), region))

    def test_geometry_in_caption_band_prevents_reservation_and_final_layout_claim(self):
        size = 256
        owners = np.full((size, size), -1, dtype=np.int32)
        owners[240, 100:108] = 0
        depth = np.full((size, size), np.inf)
        depth[240, 100:108] = 1.
        color = np.full((size, size, 3), (18, 22, 30), dtype=np.uint8)
        metadata = {'name': 'Q4 TARGET', 'projection': 'perspective', 'target_object_ids': ['surface']}
        region = []
        with patch.object(rendering, '_raster_with_owners', return_value=(color, depth, owners)), \
             patch.object(rendering, '_annotate', wraps=rendering._annotate) as annotate:
            rendering._render_view(rendering._SceneRasterizer(size), visible_meshes(['surface']),
                None, None, metadata, caption_region_out=region)
        self.assertIsNone(annotate.call_args.kwargs['caption_reserved_region'])
        self.assertEqual(region, [None])

    def test_contact_profile_matches_frozen_e09_pixels_and_projected_labels(self):
        full = np.zeros((384, 384), dtype=np.int32)
        full[:, 192:] = 1
        fixtures = [(visible_meshes(['focal', 'reference']), full), panel_fixture()]
        for meshes, owners in fixtures:
            with self.subTest(objects=len(meshes)):
                image, metadata, original = draw_labels(meshes, owners, ['focal', 'reference'], name='Q4 CONTACT')
                reference_image, reference_labels = historical_contact_annotations(meshes, owners, original, ['focal', 'reference'])
                np.testing.assert_array_equal(np.asarray(image), np.asarray(reference_image))
                self.assertEqual(metadata['projected_labels'], reference_labels)
                self.assertEqual(metadata['label_layout_profile'], 'local_contact_compat_v1')

    def test_contact_profile_skips_context_coverage_and_nearest_edge_helpers(self):
        owners = np.zeros((384, 384), dtype=np.int32)
        owners[:, 192:] = 1
        meshes = visible_meshes(['focal', 'reference'])
        with patch.object(rendering, '_label_coverage_stats', side_effect=AssertionError('CONTACT keeps the e09 path')), \
             patch.object(rendering, '_label_leader_endpoint', side_effect=AssertionError('CONTACT keeps the e09 leader')):
            _, metadata, _ = draw_labels(meshes, owners, ['focal', 'reference'],
                protected=['focal', 'reference'], name='Q4 CONTACT')
        self.assertEqual(len(metadata['projected_labels']), 2)
        self.assertEqual(metadata['label_layout_profile'], 'local_contact_compat_v1')

    def test_diagonal_local_union_matches_full_pillow_coverage_and_accumulates_once(self):
        size = 128
        owners = np.zeros((size, size), dtype=np.int32)
        owners[:, 64:] = 1
        foreground = ((np.indices((size, size)).sum(axis=0) % 7) + 1).astype(np.float32)
        covered = np.zeros((size, size), dtype=bool)
        expected_union = np.zeros_like(covered)
        total = [0, 0]
        for anchor, box in (((100, 100), (40, 40, 70, 54)), ((100, 100), (20, 80, 50, 94))):
            row = {'projected_center_px': anchor, 'label_box_px': box}
            footprint, _ = independent_label_mask([row], size, optimizer=True)
            before = covered.copy()
            with patch.object(rendering.Image, 'new', wraps=Image.new) as allocation:
                cost, additions = rendering._label_coverage_stats(foreground, owners, (0, 1),
                    anchor, box, covered=covered)
            self.assertEqual(cost, float(np.sum(foreground[footprint], dtype=np.float64)))
            self.assertEqual(additions, [int(np.count_nonzero(footprint & ~before & (owners == index)))
                                         for index in (0, 1)])
            np.testing.assert_array_equal(covered, before)
            for call in allocation.call_args_list:
                width, height = call.args[1]
                self.assertLess(width * height, size * size)
            _, committed = rendering._label_coverage_stats(foreground, owners, (0, 1),
                anchor, box, covered=covered, commit=True)
            self.assertEqual(additions, committed)
            total = [previous + added for previous, added in zip(total, additions)]
            expected_union |= footprint
            np.testing.assert_array_equal(covered, expected_union)
        self.assertEqual(total, [int(np.count_nonzero(expected_union & (owners == index))) for index in (0, 1)])

    def test_horizontal_and_vertical_leaders_need_no_drawing_or_whole_image_allocation(self):
        owners = np.zeros((128, 128), dtype=np.int32)
        owners[:, 64:] = 1
        foreground = np.ones((128, 128), dtype=np.float32)
        for anchor in ((100, 50), (50, 100)):
            row = {'projected_center_px': anchor, 'label_box_px': (40, 40, 70, 54)}
            expected, _ = independent_label_mask([row], 128, optimizer=True)
            with self.subTest(anchor=anchor), \
                 patch.object(rendering.Image, 'new', side_effect=AssertionError('Axis leaders use slices')), \
                 patch.object(rendering.np, 'zeros', side_effect=AssertionError('No whole-image allocation')):
                cost, additions = rendering._label_coverage_stats(foreground, owners, (0, 1), anchor, row['label_box_px'])
            self.assertEqual(cost, int(np.count_nonzero(expected)))
            self.assertEqual(additions, [int(np.count_nonzero(expected & (owners == index))) for index in (0, 1)])

    def test_fairness_includes_the_small_focal_instead_of_only_the_other_surface(self):
        meshes, owners = panel_fixture()
        foreground = historical_penalty(owners, meshes)
        counts = np.bincount(owners[owners >= 0], minlength=len(meshes))
        draw = ImageDraw.Draw(Image.new('RGB', (384, 384)))
        text, anchor = 'O12345678', (192, 191)
        width = int(draw.textbbox((0, 0), text)[2]) + 6
        near = (anchor[0] + 8, anchor[1] - 20, anchor[0] + 8 + width, anchor[1] - 6)
        chosen = rendering._label_box(draw, text, anchor, 384, [], foreground,
            surface_bounds=(177, 182, 207, 201), owners=owners,
            protected_owner_indices=(0, 1), protected_visible_counts=(int(counts[0]), int(counts[1])))
        near_mask, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': near}], 384, optimizer=True)
        chosen_mask, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': chosen}], 384, optimizer=True)
        fractions = lambda mask: [np.count_nonzero(mask & (owners == index)) / counts[index] for index in (0, 1)]
        self.assertLess(max(fractions(chosen_mask)), max(fractions(near_mask)))
        self.assertLess(np.count_nonzero(chosen_mask & (owners == 0)), np.count_nonzero(near_mask & (owners == 0)))

    def test_actual_contact_priority_can_protect_an_additional_requested_reference(self):
        owners = np.zeros((384, 384), dtype=np.int32)
        owners[:, 192:] = 2
        owners[300:340, 120:260] = 1
        meshes = visible_meshes(['focal', 'requested-reference', 'contact-other'])
        with patch.object(rendering, '_adaptive_context_label', wraps=rendering._adaptive_context_label) as choose:
            _, metadata, _ = draw_labels(meshes, owners, ['focal', 'contact-other'],
                protected=['focal', 'requested-reference', 'contact-other'])
        self.assertEqual(metadata['label_priority_object_ids'], ['focal', 'contact-other'])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels'][:2]], ['focal', 'contact-other'])
        self.assertEqual(len(metadata['projected_labels']), 3)
        for call in choose.call_args_list:
            self.assertEqual(set(call.args[8]), {0, 1, 2})

    def test_bounded_optimizer_matches_single_label_soft_budget_oracle(self):
        owners = np.zeros((384, 384), dtype=np.int32)
        owners[:, 192:] = 1
        meshes = visible_meshes(['focal', 'reference'])
        original = np.full((384, 384, 3), (70, 100, 150), dtype=np.uint8)
        image = Image.fromarray(original.copy())
        draw = ImageDraw.Draw(image)
        metadata = {'projected_labels': []}
        visible = [int(np.count_nonzero(owners == index)) for index in (0, 1)]
        self.assertEqual(visible[0], visible[1])
        previous_union = np.zeros(owners.shape, dtype=bool)
        occupied = []
        for own_index, mesh in enumerate(meshes):
            anchor = (95 + own_index * 192, 191)
            text = rendering.stable_object_label(mesh.object_id)
            ys, xs = np.nonzero(owners == own_index)
            bounds = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
            chosen = rendering._label_box(draw, text, anchor, 384, occupied,
                np.ones(owners.shape, dtype=np.float32), surface_bounds=bounds, owners=owners,
                protected_owner_indices=(0, 1), protected_visible_counts=visible)
            candidates = finite_label_candidates(draw, text, anchor, 384, bounds, occupied)
            scored = []
            for box in candidates:
                footprint, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': box}], 384, optimizer=True)
                fractions = [int(np.count_nonzero(footprint & (owners == index))) / visible[index] for index in (0, 1)]
                # Both surfaces have equal area and inverse-area weights clamp
                # to one, so the complete weighted annotation cost is exactly
                # its independent Pillow union pixel count.
                endpoint = max(box[0], min(anchor[0], box[2])), max(box[1], min(anchor[1], box[3]))
                distance = abs(endpoint[0] - anchor[0]) + abs(endpoint[1] - anchor[1])
                score = (max(0., max(fractions) - .05), int(np.count_nonzero(footprint)), sum(fractions), distance)
                scored.append((score, box, footprint))
            self.assertTrue(scored)
            oracle = min(scored, key=lambda value: value[0])
            self.assertEqual(chosen, oracle[1], 'The bounded proposal helper keeps its single-label soft5% objective')
            previous_union |= oracle[2]
            occupied.append(oracle[1])
            endpoint = max(chosen[0], min(anchor[0], chosen[2])), max(chosen[1], min(anchor[1], chosen[3]))
            draw.line((*anchor, *endpoint), fill=(245, 218, 135), width=1)
            draw.rectangle(chosen, fill=(18, 22, 30))
            metadata['projected_labels'].append({'projected_center_px': anchor,
                'label_box_px': chosen, 'leader_endpoint_px': endpoint})
        # This directly tests the optional proposal helper. The adaptive
        # integration below skips this loop entirely for equal large surfaces.
        measured = owner_coverage(image, original, metadata, owners)
        for index in (0, 1):
            count = int(np.count_nonzero(previous_union & (owners == index)))
            self.assertGreater(count, 0)
            self.assertEqual(measured[index]['label_box_and_leader_pixels'], count)
            self.assertEqual(measured[index]['label_box_and_leader_ratio'], count / visible[index])

    def test_reference_leader_avoids_the_focal_when_fair_zero_crossing_position_exists(self):
        owners = np.full((128, 128), -1, dtype=np.int32)
        owners[60:68, 60:68] = 1
        owners[66:71, 66:71] = 0
        meshes = visible_meshes(['focal', 'reference'])
        foreground = historical_penalty(owners, meshes)
        counts = np.bincount(owners[owners >= 0], minlength=2)
        draw = ImageDraw.Draw(Image.new('RGB', (128, 128)))
        anchor = (64, 64)
        chosen = rendering._label_box(draw, 'O12345678', anchor, 128, [], foreground,
            surface_bounds=(60, 60, 67, 67), owners=owners,
            protected_owner_indices=(0, 1), protected_visible_counts=tuple(int(value) for value in counts))
        footprint, _ = independent_label_mask([{'projected_center_px': anchor, 'label_box_px': chosen}], 128, optimizer=True)
        self.assertIsNotNone(chosen)
        self.assertEqual(np.count_nonzero(footprint & (owners == 0)), 0)

    def test_lookup_preserves_small_surface_weights_and_background(self):
        owners = np.full((128, 128), -1, dtype=np.int32)
        owners[:2, :4] = 0
        owners[10:90, 10:90] = 1
        meshes = visible_meshes(['tiny', 'large', 'hidden'])
        counts = np.bincount(owners[owners >= 0], minlength=len(meshes))
        before = owners.copy()
        actual = rendering._label_penalty_map(owners, counts, 128)
        np.testing.assert_array_equal(actual, historical_penalty(owners, meshes))
        self.assertEqual(set(np.unique(actual)), {0., 1., 16.})
        np.testing.assert_array_equal(owners, before)

    def test_rectangle_cost_matches_pillow_including_bottom_and_right_edges(self):
        penalty = np.zeros((32, 32), dtype=np.float32)
        penalty[12, 10], penalty[5, 10], penalty[12, 4], penalty[6, 5] = 17., 3., 5., 2.
        rectangle = (4, 5, 10, 12)
        mask = Image.new('1', (32, 32))
        ImageDraw.Draw(mask).rectangle(rectangle, fill=1)
        expected = float(penalty[np.asarray(mask, dtype=bool)].sum())
        self.assertEqual(expected, 27.)
        self.assertEqual(rendering._label_box_cost(penalty, rectangle), expected)

    def test_leader_joins_the_nearest_edge_or_corner_without_crossing_text(self):
        rectangle = (50, 50, 100, 64)
        cases = [((120, 57), (100, 57)), ((40, 57), (50, 57)),
                 ((75, 30), (75, 50)), ((75, 90), (75, 64)),
                 ((120, 90), (100, 64)), ((75, 57), (75, 50))]
        for anchor, expected in cases:
            with self.subTest(anchor=anchor):
                self.assertEqual(rendering._label_leader_endpoint(anchor, rectangle), expected)
        mask = Image.new('1', (128, 128))
        ImageDraw.Draw(mask).line((120, 57, *rendering._label_leader_endpoint((120, 57), rectangle)), fill=1)
        self.assertFalse(np.asarray(mask)[51:64, 51:100].any())

    def test_outer_positions_escape_a_large_visible_panel_without_dropping_label(self):
        image = Image.new('RGB', (384, 384))
        penalty = np.zeros((384, 384), dtype=np.float32)
        penalty[90:295, 100:285] = 1.
        draw = ImageDraw.Draw(image)
        legacy = historical_local_box(draw, 'O12345678', (192, 192), 384, [], penalty)
        current = rendering._label_box(draw, 'O12345678', (192, 192), 384, [], penalty,
                                       surface_bounds=(100, 90, 284, 294))
        self.assertIsNotNone(legacy)
        self.assertIsNotNone(current)
        self.assertGreater(rendering._label_box_cost(penalty, legacy), 0)
        self.assertEqual(rendering._label_box_cost(penalty, current), 0)

    def test_dense_low_risk_fixture_retains_exact_legacy_pixels_and_pair_coverage(self):
        meshes, owners = panel_fixture()
        before = owners.copy()
        image, metadata, pixels = draw_labels(meshes, owners, ['focal', 'reference'])
        old_image, old_labels = historical_contact_annotations(meshes, owners, pixels,
            ['focal', 'reference'], name='Q1 XY TOP')
        old_rows = owner_coverage(old_image, pixels, {'projected_labels': old_labels}, owners, historical=True)
        rows = owner_coverage(image, pixels, metadata, owners)
        self.assertEqual([row['object_id'] for row in metadata['projected_labels'][:2]], ['focal', 'reference'])
        self.assertEqual(len(metadata['projected_labels']), 8)
        self.assertEqual(metadata['projected_labels'], old_labels)
        self.assertEqual(metadata['label_layout']['optimizer_attempts'], 0)
        self.assertEqual(metadata['label_layout']['optimizer_applied'], 0)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(old_image))
        self.assertEqual(rows, old_rows)
        for index in (0, 1):
            self.assertEqual(rows[index]['anchor_pixels'], 1)
            self.assertEqual(rows[index]['title_footer_changed_pixels'], 0)
        np.testing.assert_array_equal(owners, before)

    def test_measurement_separates_title_footer_changes_from_label_footprint(self):
        owners = np.full((384, 384), -1, dtype=np.int32)
        owners[5:8, 320:323] = 0
        meshes = visible_meshes(['header-surface'])
        image, metadata, pixels = draw_labels(meshes, owners, ['header-surface'])
        row = owner_coverage(image, pixels, metadata, owners)[0]
        self.assertEqual(row['visible_pixels'], 9)
        self.assertEqual(row['all_annotations_changed_pixels'], 9)
        self.assertEqual(row['title_footer_changed_pixels'], 9)
        self.assertLess(row['label_box_and_leader_pixels'], row['all_annotations_changed_pixels'])
        self.assertEqual(row['anchor_pixels'], 1)

    def test_at_most_twelve_deduplicated_candidate_costs_are_examined(self):
        image = Image.new('RGB', (384, 384))
        foreground = np.zeros((384, 384), dtype=np.float32)
        with patch.object(rendering, '_label_box_cost', wraps=rendering._label_box_cost) as cost:
            box = rendering._label_box(ImageDraw.Draw(image), 'O12345678', (192, 192), 384, [], foreground,
                                       surface_bounds=(100, 90, 284, 294))
        self.assertIsNotNone(box)
        self.assertLessEqual(cost.call_count, 12)
        self.assertEqual(len({call.args[1] for call in cost.call_args_list}), cost.call_count)

    def test_edge_clipping_and_overlap_gate_still_apply_to_outer_positions(self):
        image = Image.new('RGB', (128, 128))
        draw = ImageDraw.Draw(image)
        foreground = np.zeros((128, 128), dtype=np.float32)
        for anchor, bounds in (((0, 0), (0, 0, 3, 3)), ((127, 127), (124, 124, 127, 127))):
            with self.subTest(anchor=anchor):
                box = rendering._label_box(draw, 'O12345678', anchor, 128, [], foreground, surface_bounds=bounds)
                self.assertTrue(2 <= box[0] < box[2] <= 126)
                self.assertTrue(19 <= box[1] < box[3] <= 109)
                self.assertIsNone(rendering._label_box(draw, 'O12345678', anchor, 128,
                    [(0, 0, 127, 127)], foreground, surface_bounds=bounds))

    def test_full_foreground_fallback_keeps_both_priority_labels_and_no_certificate(self):
        owners = np.zeros((384, 384), dtype=np.int32)
        owners[:, 192:] = 1
        meshes = visible_meshes(['focal', 'reference'])
        _, metadata, _ = draw_labels(meshes, owners, ['focal', 'reference'])
        self.assertEqual([row['object_id'] for row in metadata['projected_labels']], ['focal', 'reference'])
        self.assertFalse(metadata['labels_certify_visibility'])
        first, second = [row['label_box_px'] for row in metadata['projected_labels']]
        self.assertFalse(first[0] < second[2] and first[2] > second[0]
                         and first[1] < second[3] and first[3] > second[1])

    def test_caption_region_protects_independent_nearest_edge_label_mask(self):
        size = 256
        for anchor, box in (([100, 255], [10, 180, 75, 194]),
                            ([100, 210], [10, 180, 75, 194]),
                            ([250, 230], [180, 205, 245, 219])):
            with self.subTest(anchor=anchor):
                row = {'projected_center_px': anchor, 'label_box_px': box,
                       'leader_endpoint_px': (max(box[0], min(anchor[0], box[2])), max(box[1], min(anchor[1], box[3])))}
                label_mask, _ = independent_label_mask([row], size)
                metadata = {'name': 'Q4 TARGET', 'projection': 'perspective', 'projected_labels': [row]}
                region = rendering._empty_caption_region(np.full((size, size), np.inf),
                    np.full((size, size), -1, dtype=np.int32), metadata, size)
                expected_occupied = label_mask[size - 29:size - 1, 1:size - 1].any()
                self.assertEqual(region is None, bool(expected_occupied))


if __name__ == '__main__':
    unittest.main()
