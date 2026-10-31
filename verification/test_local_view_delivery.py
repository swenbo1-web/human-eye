"""Actual router/service integration of optional local identity recovery."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import numpy as np

from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.scene_rendering import _task_label_coverage_summary, _display_snapshot_signature
from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.task_brief import project_task_brief
from verification.test_local_view_policy import nav_scene, rendered
from verification.test_label_coverage_delivery import ReadOnlyHost


def raw():
    meshes,ids=nav_scene()
    return {'revision':'local-delivery-r1','unit':'m','coordinate_frame':'world',
            'source':'local_contract_fixture','meshes':[m.to_dict() for m in meshes]},ids

def route(**changes):
    scene,ids=raw()
    event={'event':'before_model','session_id':'local-delivery','scene':scene,
           'task_kind':'spatial_3d','focal_id':'part','reference_id':'base',
           'query':{'label_object_ids':ids}}
    event.update(changes)
    return HumanEyeAutoRouter(quad_size=256).handle_event(event)

def pixels(value):
    return Image.open(io.BytesIO(base64.b64decode(value['image']['data'])))


class LocalViewDeliveryTests(unittest.TestCase):
    def test_snapshot_signature_handles_empty_array_without_minting_geometry_support(self):
        mesh=MeshEntity3D('empty','empty','empty',np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]),
                          np.empty((0,3),dtype=int),None,(80,80,80))
        first=_display_snapshot_signature([mesh])
        self.assertEqual(first,_display_snapshot_signature([mesh]))
        self.assertTrue(first.startswith('sha256:'))
        mesh.vertices[1,0]=2.
        self.assertNotEqual(first,_display_snapshot_signature([mesh]))

    def test_qualified_local_delivery_updates_union_and_keeps_natural_evidence(self):
        with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.), \
             patch('human_eye_plugin.auto_router.local_view_clock',return_value=0.):
            value=route()
        facts=json.loads(value['context_text']);canvas=facts['canvas'];receipt=facts['local_view']
        self.assertTrue(receipt['applied'],receipt)
        self.assertEqual(len(canvas['views']),4)
        self.assertEqual(len(canvas['supplemental_views']),1)
        self.assertEqual(facts['label_presentation']['natural_visual_focus_drawn_count'],4)
        self.assertEqual(facts['label_presentation']['visual_focus_drawn_count'],6)
        self.assertEqual(facts['label_presentation']['visual_focus_not_drawn_ids'],[])
        self.assertEqual(receipt['new_readable_object_ids'],['peripheral-0','peripheral-2'])
        self.assertEqual(pixels(value).size,(640,512))
        self.assertFalse(receipt['execution_authority'])
        self.assertFalse(receipt['evidence_reused'])

    def test_raw_drawn_but_unqualified_local_label_does_not_inflate_union(self):
        meshes,ids=nav_scene();_,meta=rendered(meshes,ids)
        before=copy.deepcopy(meta)
        meta['supplemental_views']=[{'projected_labels':[{'object_id':'peripheral-0'},
            {'object_id':'peripheral-2'}], 'readable_focus_object_ids':['peripheral-0','unknown-id']}]
        summary=_task_label_coverage_summary(meta)
        self.assertEqual(summary['natural_visual_focus_drawn_count'],4)
        self.assertEqual(summary['visual_focus_drawn_count'],5)
        self.assertEqual(summary['visual_focus_not_drawn_ids'],['peripheral-2'])
        self.assertEqual(summary['new_local_readable_object_ids'],['peripheral-0'])
        self.assertEqual(meta['views'],before['views'])

    def test_optional_failure_retains_original_four_view_image_and_measurement(self):
        with patch('human_eye_plugin.auto_router.append_gain_local_view',side_effect=ValueError('probe failure')):
            value=route()
        facts=json.loads(value['context_text'])
        self.assertEqual(facts['local_view']['reason'],'local_view_unavailable')
        self.assertEqual(pixels(value).size,(512,512))
        self.assertEqual(len(facts['canvas']['views']),4)
        self.assertNotIn('supplemental_views',facts['canvas'])
        self.assertIn('measurement',facts)
        self.assertEqual(facts['label_presentation']['visual_focus_drawn_count'],4)

    def test_shared_budget_exhaustion_prevents_extra_raster(self):
        with patch('human_eye_plugin.auto_router.local_view_clock',side_effect=[0.,.041,.041]):
            value=route()
        facts=json.loads(value['context_text']);receipt=facts['local_view']
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['candidate_raster_count'],0)
        self.assertEqual(receipt['reason'],'shared_local_budget_unavailable')
        self.assertEqual(pixels(value).size,(512,512))

    def test_final_integration_checkpoint_can_reject_completed_candidate(self):
        with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.), \
             patch('human_eye_plugin.auto_router.local_view_clock',side_effect=[0.,.010,.041]):
            value=route()
        facts=json.loads(value['context_text']);receipt=facts['local_view']
        self.assertFalse(receipt['applied'])
        self.assertEqual(receipt['reason'],'local_view_integration_budget_exceeded')
        self.assertEqual(receipt['candidate_raster_count'],1)
        self.assertEqual(receipt['new_readable_object_ids'],[])
        self.assertEqual(receipt['candidate_readable_object_ids'],['peripheral-0','peripheral-2'])
        self.assertEqual(receipt['still_missing_ids'],['peripheral-0','peripheral-2'])
        self.assertNotIn('supplemental_views',facts['canvas'])
        self.assertEqual(pixels(value).size,(512,512))

    def test_explicit_section_request_takes_priority_over_automatic_local_view(self):
        _,ids=raw()
        value=route(query={'label_object_ids':ids,'visual_diagnostic':'contact_section'})
        facts=json.loads(value['context_text'])
        self.assertFalse(facts['local_view']['applied'])
        self.assertEqual(facts['local_view']['reason'],'existing_visual_diagnostic_requested')
        self.assertEqual(facts['local_view']['candidate_raster_count'],0)
        self.assertNotIn('supplemental_views',facts['canvas'])
        self.assertIn('visual_diagnostics',facts)

    def test_full_brief_and_cached_reuse_keep_image_and_separate_historical_cost(self):
        scene,ids=raw()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                'state_file':'state.json','audit_file':'audit.jsonl','quad_size':256,'max_sessions':2}),encoding='utf-8')
            host=ReadOnlyHost();host.raw=scene
            service=LiveSpatialService(path,host=host)
            with patch('human_eye_plugin.local_view.local_view_clock',return_value=0.), \
                 patch('human_eye_plugin.auto_router.local_view_clock',return_value=0.):
                value=service.observe('local',focal_id='part',reference_id='base',query={'label_object_ids':ids})
            facts=json.loads(value['routing']['context_text']);brief=project_task_brief(value)
            self.assertTrue(facts['local_view']['applied'],facts['local_view'])
            self.assertIsNotNone(brief)
            self.assertEqual(brief['routing']['image'],value['routing']['image'])
            self.assertEqual(brief['observation']['local_view'],facts['local_view'])
            self.assertEqual(brief['observation']['label_presentation'],facts['label_presentation'])
            full_local=facts['canvas']['supplemental_views'][0]
            brief_local=brief['observation']['canvas']['supplemental_views'][0]
            for field in ['projected_labels','readable_focus_object_ids','panel_offset_px','source_window_px']:
                self.assertEqual(brief_local[field],full_local[field])
            self.assertNotIn('view_matrix',brief_local)
            with patch('human_eye_plugin.auto_router.append_gain_local_view',side_effect=AssertionError('cache rerender')):
                reused=service.observe('local',focal_id='part',reference_id='base',query={'label_object_ids':ids[::-1]})
            reuse_facts=json.loads(reused['routing']['context_text'])
            self.assertTrue(reused['routing']['cache_hit'])
            self.assertTrue(reuse_facts['local_view']['evidence_reused'])
            self.assertEqual(reuse_facts['local_view']['current_event_candidate_raster_count'],0)
            self.assertEqual(reuse_facts['local_view']['current_event_local_view_cost_ms'],0.)
            self.assertEqual(value['routing']['image'],reused['routing']['image'])
            self.assertEqual(host.applies,0)

if __name__=='__main__':unittest.main()
