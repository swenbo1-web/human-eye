"""Pure formatting of frozen producer JSON and existing PNG bytes only."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin.query_policy import validate_source_region_query


ROOT = Path(__file__).resolve().parents[3]
ORIGINAL_INPUTS = ROOT / 'verification/m4_source_region_consumption_001/inputs'
PRODUCERS = Path('D:/he_m4_source_region_display_001/sessions')
CASES = [('S1', 'main', 1), ('S2', 'state', 2), ('S3', 'state', 4)]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def producer(slot, index):
    return json.loads((PRODUCERS / slot / 'product_full' / f'call_{index:03d}' / 'SERVICE_RESULT.json').read_bytes())


class FactsProjectionTests(unittest.TestCase):
    def test_three_frozen_default_deliveries(self):
        for case, slot, index in CASES:
            with self.subTest(case=case):
                value = producer(slot, index)
                before = encoded(value)
                audit = {}
                result = mcp._tool_result(value, is_error=False, active_delivery_audit=audit)
                text = result['content'][0]['text'].encode('utf8')
                brief = json.loads(text)
                self.assertEqual(brief['schema'], 'source-region-brief-v2')
                self.assertLessEqual(len(text), 10000)
                self.assertEqual(brief['task_result']['facts'], value['task_result']['facts'])
                self.assertEqual(brief['task_result']['source_mapping'], {
                    'nearest_witness': value['task_result']['source_mapping']['nearest_witness']})
                self.assertEqual(brief['task_result']['unit'], 'm')
                self.assertEqual(brief['task_result']['coordinate_frame'], 'world')
                self.assertEqual(brief['task_result']['reference'], value['task_result']['reference'])
                self.assertEqual(brief['task_result']['measurement_scope'], value['task_result']['measurement_scope'])
                self.assertEqual(brief['region_ref'], value['region_ref'])
                self.assertEqual(text.count(b'"schema":"human-eye-source-region-ref-v1"'), 1)
                for key in ('facts', 'unit', 'coordinate_frame', 'reference', 'measurement_scope',
                            'distance_m', 'nearest_witness', 'source_mapping', 'selected_surface_pixels', 'images'):
                    self.assertLess(text.index(('"' + key + '"').encode()), 4096)
                self.assertLess(text.index(b'"images"') + len(encoded(brief['images'])), 4096)
                self.assertEqual(brief['image_scope'], value['binding']['image_scope'])
                original = json.loads((ORIGINAL_INPUTS / case / 'ORIGINAL_BRIEF.json').read_bytes())
                self.assertEqual(brief['images'], original['images'])
                for key, item in brief['binding'].items():
                    self.assertEqual(item, value['binding'][key])
                visible = value['facts']['visibility']
                self.assertEqual(brief['visibility']['selected_surface_pixels'], visible['selected_surface_pixels'])
                self.assertEqual(brief['visibility']['selected_object_participates'], visible['selected_object_participates'])
                self.assertEqual(brief['visibility']['unknown'], visible['unknown'])
                self.assertEqual(brief['visibility']['visible_source_triangle_count'], len(visible['visible_source_triangle_indices']))
                self.assertEqual(brief['visibility']['unseen_source_triangle_count'], len(visible['unseen_source_triangle_indices']))
                self.assertEqual(brief['region']['source_triangle_count'], len(value['region_ref']['source_triangle_indices']))
                self.assertNotIn('vertices_world_m', brief['region'])
                self.assertNotIn('triangles_source_vertices', brief['region'])
                self.assertNotIn('source_triangle_indices', brief['region'])
                self.assertNotIn('visible_source_triangle_indices', brief['visibility'])
                self.assertEqual(brief['details'], 'response_detail=full')
                png = base64.b64decode(result['content'][1]['data'], validate=True)
                self.assertEqual(png, (ORIGINAL_INPUTS / case / 'ORIGINAL_IMAGE.png').read_bytes())
                self.assertEqual(hashlib.sha256(png).hexdigest(), value['frames'][0]['image_sha256'])
                self.assertEqual(encoded(value), before)
                self.assertEqual(audit['projection_status'], 'brief')
                self.assertEqual(audit['native_blocks_constructed'], 1)

    def test_full_retains_complete_producer_semantics(self):
        for case, slot, index in CASES:
            with self.subTest(case=case):
                value = producer(slot, index)
                result = mcp._tool_result(value, is_error=False, response_detail='full')
                full = json.loads(result['content'][0]['text'])
                expected = copy.deepcopy(value)
                expected['image_delivery'] = {
                    'local_verified_image_count': len(value['frames']),
                    'mcp_content_constructed_image_count': len(value['frames']),
                    'consumer_read_status': 'unconfirmed',
                    'frame_reuses': value['work']['frame_reuses'],
                    'new_raster_attempts': value['work']['raster_attempts'],
                }
                self.assertEqual(full, expected)
                self.assertEqual(full['facts']['region']['vertices_world_m'], value['facts']['region']['vertices_world_m'])
                self.assertEqual(full['source_mapping'], value['source_mapping'])

    def test_projection_mutation_cannot_change_input_or_cached_result(self):
        value = producer('main', 1)
        before = encoded(value)
        result = mcp.project_source_region_brief(value)
        result['region_ref']['source_triangle_indices'].append(123456)
        result['task_result']['facts']['surface_proximity']['value']['nearest_witness']['a'][0] = 42
        result['task_result']['source_mapping']['nearest_witness']['a']['source_triangle_indices'].clear()
        result['image_scope']['objects'][0]['object_name'] = 'changed'
        result['images'][0]['image_ref'] = 'changed'
        result['visibility']['unknown'].clear()
        self.assertEqual(encoded(value), before)
        self.assertEqual(mcp.project_source_region_brief(value)['task_result']['facts'], value['task_result']['facts'])

    def test_unknown_measurement_and_display_evidence_remain_explicit(self):
        value = producer('state', 2)
        value['frames'] = []
        value['status'] = 'partial'
        value['observation_status'] = 'evidence_insufficient'
        value['task_result']['facts']['surface_proximity'] = {'status': 'unknown', 'reason': 'degenerate_surface'}
        value['facts']['visibility'].update(status='unknown', reason='current_display_snapshot_missing',
            unknown=['current_viewport_image', 'complete_surface_visibility'], selected_surface_pixels=0,
            selected_object_participates=None)
        result = mcp._tool_result(value, is_error=False)
        brief = json.loads(result['content'][0]['text'])
        self.assertEqual(brief['status'], 'partial')
        self.assertEqual(brief['observation_status'], 'evidence_insufficient')
        self.assertEqual(brief['task_result']['facts'], value['task_result']['facts'])
        self.assertEqual(brief['visibility']['reason'], 'current_display_snapshot_missing')
        self.assertEqual(brief['visibility']['unknown'], value['facts']['visibility']['unknown'])
        self.assertEqual(brief['images'], [])
        self.assertEqual(len(result['content']), 1)

    def test_image_omitted_and_maximum_ref_roundtrip(self):
        for count in (1, 4096):
            with self.subTest(count=count):
                # This is a formatting boundary control. No geometry or images
                # are constructed from the synthetic selected row domain.
                value = producer('main', 1)
                indices = list(range(count))
                value['region_ref']['source_triangle_indices'] = indices
                value['task_result']['region_ref'] = copy.deepcopy(value['region_ref'])
                value['facts']['region']['source_triangle_indices'] = indices
                value['facts']['visibility'].update(status='unknown', reason='image_not_requested',
                    visible_source_triangle_indices=[], unseen_source_triangle_indices=indices,
                    selected_source_triangle_count=count, selected_surface_pixels=0)
                value['frames'] = []
                brief = json.loads(mcp._tool_result(value, is_error=False)['content'][0]['text'])
                query = {'mode': 'source_region', 'region_ref': brief['region_ref'],
                    'reference': {'id': value['task_result']['reference']['object_id']},
                    'requested_facts': ['surface_proximity']}
                self.assertEqual(validate_source_region_query(query)['region_ref'], value['region_ref'])
                self.assertEqual(brief['region']['source_triangle_count'], count)
                self.assertEqual(brief['visibility']['unseen_source_triangle_count'], count)
                self.assertEqual(brief['visibility']['reason'], 'image_not_requested')

    def test_scope_and_frame_binding_mismatch_are_rejected(self):
        value = producer('main', 1)
        value['task_result']['region_ref']['source_triangle_indices'] = [0]
        with self.assertRaisesRegex(ValueError, 'source_region_result_scope_mismatch'):
            mcp.project_source_region_brief(value)
        value = producer('main', 1)
        value['frames'][0]['host_binding_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source_region_frame_binding_mismatch'):
            mcp.project_source_region_brief(value)

    def test_png_validation_failure_is_audited(self):
        value = producer('main', 1)
        value['frames'][0]['image_sha256'] = '0' * 64
        audit = {}
        with self.assertRaisesRegex(ValueError, 'PNG source binding changed'):
            mcp._tool_result(value, is_error=False, active_delivery_audit=audit)
        self.assertEqual(audit['status'], 'failed')
        self.assertFalse(audit['mcp_content_ready'])
        self.assertEqual(audit['native_blocks_constructed'], 0)

    def test_brief_copies_delivered_fields_and_validates_once(self):
        value = producer('main', 1)
        copied = []
        real_deepcopy = copy.deepcopy

        def record_copy(item, memo=None):
            copied.append(id(item))
            return real_deepcopy(item, memo)

        with patch.object(mcp.copy, 'deepcopy', side_effect=record_copy), patch.object(
                mcp, '_validate_source_region_projection', wraps=mcp._validate_source_region_projection) as validate:
            mcp._tool_result(value, is_error=False)
        self.assertEqual(validate.call_count, 1)
        self.assertNotIn(id(value), copied)
        self.assertNotIn(id(value['facts']['region']['vertices_world_m']), copied)
        self.assertNotIn(id(value['facts']['region']['triangles_source_vertices']), copied)
        self.assertNotIn(id(value['task_result']['source_mapping']['region']), copied)

    def test_full_validates_once_without_constructing_undelivered_brief(self):
        value = producer('main', 1)
        with patch.object(mcp, '_validate_source_region_projection',
                wraps=mcp._validate_source_region_projection) as validate, patch.object(
                mcp, '_project_source_region_brief', wraps=mcp._project_source_region_brief) as project:
            mcp._tool_result(value, is_error=False, response_detail='full')
        self.assertEqual(validate.call_count, 1)
        project.assert_not_called()


if __name__ == '__main__':
    unittest.main()
