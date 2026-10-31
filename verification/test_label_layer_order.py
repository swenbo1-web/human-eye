"""Visible glyph integrity with independent Pillow layer-order oracles."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from human_eye_plugin import scene_rendering as rendering


BG = (18, 22, 30)
LINE = (245, 218, 135)


def fixture(count=2, *, edge=False):
    size = 256
    anchors = [(100, 100), (200, 57), (50, 20), (40, 160),
               (100, 180), (160, 160), (220, 180), (190, 220)][:count]
    boxes = [(80, 50, 144, 64), (8, 50, 72, 64), (150, 110, 214, 124),
             (5, 140, 69, 154), (80, 140, 144, 154), (150, 140, 214, 154),
             (80, 190, 144, 204), (150, 190, 214, 204)][:count]
    endpoints = [(80, 57), (72, 57), (150, 117), (5, 147),
                 (80, 147), (150, 147), (144, 197), (150, 197)][:count]
    if edge:
        anchors[:2] = [(1, 1), (254, 26)]
        boxes[:2] = [(80, 19, 144, 33), (2, 50, 66, 64)]
        endpoints[:2] = [(80, 26), (66, 57)]
    owners = np.full((size, size), -1, dtype=np.int32)
    meshes = [SimpleNamespace(object_id=f'layer-{i}', mark_label=f'#{i}') for i in range(count)]
    pixels = np.empty((size, size, 3), dtype=np.uint8)
    pixels[:] = BG
    for index, (x, y) in enumerate(anchors):
        owners[y - 1:y + 2, x - 1:x + 2] = index
        pixels[y - 1:y + 2, x - 1:x + 2] = (35 + index * 9, 80, 170)
    return meshes, owners, pixels, anchors, boxes, endpoints


def oracle(pixels, rows, name, *, interleaved=False):
    """Independent primitive composition; never call production placement/drawing."""
    image = Image.fromarray(pixels.copy())
    draw = ImageDraw.Draw(image)
    def label(row):
        x0, y0, x1, y1 = row['box']
        draw.rectangle((x0, y0, x1, y1), fill=BG, outline=(150, 145, 110))
        draw.text((x0 + 3, y0), row['text'], fill=(255, 245, 180))
    for row in rows:
        draw.line((*row['anchor'], *row['endpoint']), fill=LINE, width=1)
        if interleaved:
            label(row)
    if not interleaved:
        for row in rows:
            label(row)
    size = image.width
    draw.rectangle((0, 0, size - 1, 16), fill=(28, 34, 46))
    draw.text((3, 1), name, fill=(235, 242, 255))
    draw.rectangle((0, size - 15, size - 1, size - 1), fill=BG)
    draw.line((4, size - 4, 4 + size // 4, size - 4), fill=(225, 230, 240), width=2)
    draw.text((4, size - 15), f'{size // 4 * .001:.3g} m', fill=(235, 242, 255))
    draw.rectangle((0, 0, size - 1, size - 1), outline=(70, 82, 105))
    return image


def union(rows, size=256):
    mask = Image.new('1', (size, size))
    draw = ImageDraw.Draw(mask)
    for row in rows:
        draw.line((*row['anchor'], *row['endpoint']), fill=1, width=1)
        draw.rectangle(row['box'], fill=1)
    return np.asarray(mask, dtype=bool)


class LabelLayerOrderTests(unittest.TestCase):
    def render(self, count=2, *, edge=False, contact=False):
        meshes, owners, pixels, anchors, boxes, endpoints = fixture(count, edge=edge)
        before = owners.copy()
        mesh_before = copy.deepcopy([vars(mesh) for mesh in meshes])
        name = 'Q4 CONTACT' if contact else 'Q1 XY TOP'
        metadata = {'name': name, 'projection': 'orthographic', 'm_per_pixel': .001,
                    'target_object_ids': [mesh.object_id for mesh in meshes],
                    'label_priority_object_ids': [mesh.object_id for mesh in meshes]}
        text_to_index = {rendering.stable_object_label(mesh.object_id): index for index, mesh in enumerate(meshes)}
        def place(draw, text, anchor, *args, **kwargs):
            index = text_to_index[text]
            self.assertEqual(tuple(anchor), anchors[index])
            return boxes[index], endpoints[index], True, True
        def contact_place(draw, text, anchor, *args, **kwargs):
            index = text_to_index[text]
            self.assertEqual(tuple(anchor), anchors[index])
            return boxes[index]
        image = Image.fromarray(pixels.copy())
        with patch.object(rendering, '_adaptive_context_label', side_effect=place), \
             patch.object(rendering, '_label_box', side_effect=contact_place):
            rendering._annotate(image, meshes, None, None, metadata, owners)
        np.testing.assert_array_equal(before, owners)
        self.assertEqual(mesh_before, [vars(mesh) for mesh in meshes])
        expected_rows = [{'anchor': anchor, 'box': box,
                          'endpoint': ((box[0], box[1] + 7) if contact else endpoint),
                          'text': rendering.stable_object_label(mesh.object_id)}
                         for mesh, anchor, box, endpoint in zip(meshes, anchors, boxes, endpoints)]
        self.assertEqual(len(metadata['projected_labels']), count)
        for index, row in enumerate(metadata['projected_labels']):
            self.assertEqual(row['projected_center_px'], list(anchors[index]))
            self.assertEqual(row['label_box_px'], list(boxes[index]))
            self.assertEqual(row['surface_visible_pixels'], 9)
            self.assertEqual(row['object_id'], meshes[index].object_id)
            self.assertFalse(metadata['labels_certify_visibility'])
        return image, metadata, pixels, expected_rows, name

    def test_later_leader_cannot_overwrite_previous_glyphs_or_box(self):
        image, metadata, pixels, rows, name = self.render()
        old = oracle(pixels, rows, name, interleaved=True)
        expected = oracle(pixels, rows, name)
        x0, y0, x1, y1 = rows[0]['box']
        target = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        self.assertTrue(np.any(np.asarray(old)[target] != np.asarray(expected)[target]),
                        'Fixture must genuinely expose a later leader crossing an earlier label')
        np.testing.assert_array_equal(np.asarray(image), np.asarray(expected))

    def test_multiple_crossing_leaders_preserve_all_earlier_labels(self):
        image, _, pixels, rows, name = self.render(3)
        expected = oracle(pixels, rows, name)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(expected))

    def test_eight_labels_preserve_priority_boxes_anchors_and_footprint(self):
        image, metadata, pixels, rows, name = self.render(8)
        expected = oracle(pixels, rows, name)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(expected))
        actual_rows = [{'anchor': row['projected_center_px'], 'box': row['label_box_px'],
                        'endpoint': row['leader_endpoint_px']} for row in metadata['projected_labels']]
        np.testing.assert_array_equal(union(rows), union(actual_rows))
        old = oracle(pixels, rows, name, interleaved=True)
        changed = np.any(np.asarray(image) != np.asarray(old), axis=2)
        boxes = Image.new('1', image.size)
        for row in rows:
            ImageDraw.Draw(boxes).rectangle(row['box'], fill=1)
        self.assertFalse(np.any(changed & ~np.asarray(boxes, dtype=bool)),
                         'Layer repair must not create changes outside the existing label boxes')

    def test_edge_anchors_keep_title_footer_and_canvas_bounds(self):
        image, _, pixels, rows, name = self.render(2, edge=True)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(oracle(pixels, rows, name)))
        self.assertEqual(image.size, (256, 256))

    def test_zero_labels_leave_same_bands_and_geometry(self):
        image, _, pixels, rows, name = self.render(0)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(oracle(pixels, rows, name)))

    def test_one_label_is_pixel_identical_to_original_order(self):
        image, _, pixels, rows, name = self.render(1)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(oracle(pixels, rows, name, interleaved=True)))

    def test_contact_retains_existing_interleaved_output(self):
        image, _, pixels, rows, name = self.render(3, contact=True)
        np.testing.assert_array_equal(np.asarray(image), np.asarray(oracle(pixels, rows, name, interleaved=True)))


if __name__ == '__main__':
    unittest.main()
