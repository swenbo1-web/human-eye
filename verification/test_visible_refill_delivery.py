"""Router integration of default add-only identity recovery and optional costs."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from human_eye_plugin import auto_router
from human_eye_plugin import visible_refill
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.task_brief import project_task_brief
from verification.test_visible_refill_policy import priority_scene
from verification.test_label_coverage_delivery import ReadOnlyHost


def raw():
    return {'revision':'refill-delivery-r1','unit':'m','coordinate_frame':'world',
            'source':'owned_contract_fixture','meshes':[m.to_dict() for m in priority_scene()]}


def route(**changes):
    event={'event':'before_model','session_id':'refill-delivery','task_kind':'spatial_3d',
           'scene':raw(),'focal_id':'focus','reference_id':'reference'}
    event.update(changes)
    return auto_router.HumanEyeAutoRouter(quad_size=256).handle_event(event)


def facts(value):return json.loads(value['context_text'])
def png(value):return base64.b64decode(value['image']['data'])
def refill_rows(value):
    return [r for v in facts(value)['canvas']['views'] for r in v.get('projected_labels',[])
            if r.get('display_source')=='visible_candidate_refill']


class VisibleRefillDeliveryTests(unittest.TestCase):
    def test_real_router_gain_keeps_priority_risk_plan_and_critical_measurements(self):
        with patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(auto_router,'visible_refill_clock',return_value=0.):
            value=route()
        f=facts(value);receipt=f['label_refill']
        self.assertTrue(receipt['applied'],receipt)
        self.assertEqual(receipt['new_readable_object_ids'],['risk-02-visible'])
        self.assertEqual(receipt['candidate_raster_count'],0)
        self.assertEqual(f['canvas']['task_labels']['related_object_ids'],['risk-00-hidden','risk-01-hidden'])
        self.assertEqual(f['label_presentation']['selected_related_count'],2)
        self.assertEqual(f['label_presentation']['actual_default_related_drawn_count'],1)
        self.assertEqual(f['label_presentation']['refilled_related_object_ids'],['risk-02-visible'])
        self.assertEqual(len(refill_rows(value)),1)
        contacts={r['object_id']:r for r in f['scene_contacts']}
        for identity in ['risk-00-hidden','risk-01-hidden','risk-02-visible']:
            self.assertLess(contacts[identity]['signed_clearance_m'],0)
        self.assertTrue(f['measurement']['measurement_valid'])
        self.assertAlmostEqual(f['measurement']['signed_clearance_m'],.004)
        self.assertEqual(Image.open(io.BytesIO(png(value))).size,(512,512))
        self.assertFalse(receipt['execution_authority'])

    def test_explicit_ids_core_focus_section_and_text_only_skip_new_pool(self):
        for changes in [{'query':{'object_ids':['risk-02-visible']}},
                        {'query':{'label_object_ids':['focus']}},
                        {'query':{'label_object_ids':['risk-02-visible']}},
                        {'query':{'visual_diagnostic':'contact_section'}},
                        {'include_image':False}]:
            with self.subTest(changes=changes), \
                 patch.object(auto_router,'_build_task_label_bundle',side_effect=AssertionError('explicit path used default pool')):
                value=route(**changes)
            self.assertNotIn('label_refill',facts(value))

    def test_optional_pool_and_constructor_failure_retain_existing_risk_image(self):
        for target in ['_build_task_label_bundle','VisibleRefillCollector']:
            with self.subTest(target=target),patch.object(auto_router,target,side_effect=RuntimeError('optional setup')):
                value=route()
            f=facts(value)
            self.assertIn('image',value)
            self.assertFalse(f['label_refill']['applied'])
            self.assertEqual(refill_rows(value),[])
            self.assertEqual(f['canvas']['task_labels']['related_object_ids'],['risk-00-hidden','risk-01-hidden'])
            self.assertIn('risk-00-hidden',{r['object_id'] for r in f['scene_contacts']})

    def test_collection_failure_preserves_its_known_incremental_cost(self):
        clock={'value':0.}
        def fail(*args,**kwargs):clock['value']=.001;raise ValueError('collection')
        with patch.object(auto_router,'visible_refill_clock',side_effect=lambda:clock['value']), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector,'observe_view',new=fail):
            value=route()
        r=facts(value)['label_refill']
        self.assertFalse(r['applied']);self.assertEqual(r['collection_error_type'],'ValueError')
        self.assertAlmostEqual(r['collection_cost_ms'],1.)
        self.assertGreaterEqual(r['additional_cost_ms'],1.)
        self.assertEqual(refill_rows(value),[])

    def test_finish_exception_does_not_replace_measurement_or_hide_spent_time(self):
        clock={'value':0.}
        def fail(*args,**kwargs):clock['value']=.003;raise RuntimeError('optional finalization')
        with patch.object(auto_router,'visible_refill_clock',side_effect=lambda:clock['value']), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector,'finish',new=fail):
            value=route()
        f=facts(value);r=f['label_refill']
        self.assertFalse(r['applied']);self.assertAlmostEqual(r['additional_cost_ms'],3.)
        self.assertEqual(r['new_readable_object_ids'],[])
        self.assertTrue(f['measurement']['measurement_valid'])
        self.assertEqual(refill_rows(value),[])

    def test_completed_helper_can_be_rejected_by_full_integration_budget(self):
        clock={'value':0.};original=visible_refill.VisibleRefillCollector.finish
        def finish(*args,**kwargs):
            result=original(*args,**kwargs);clock['value']=.006;return result
        with patch.object(auto_router,'visible_refill_clock',side_effect=lambda:clock['value']), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector,'finish',new=finish):
            value=route()
        r=facts(value)['label_refill']
        self.assertFalse(r['applied']);self.assertEqual(r['reason'],'visible_refill_integration_budget_exceeded')
        self.assertEqual(r['candidate_readable_object_ids'],['risk-02-visible'])
        self.assertEqual(r['new_readable_object_ids'],[])
        self.assertEqual(r['actual_delivered_default_related_count'],0)
        self.assertAlmostEqual(r['additional_cost_ms'],6.)
        self.assertEqual(refill_rows(value),[])

    def test_applied_receipt_without_matching_delivered_identity_row_is_rejected(self):
        original=visible_refill.VisibleRefillCollector.finish
        def bad(self,canvas,metadata,meshes,**kwargs):
            _,_,receipt=original(self,canvas,metadata,meshes,**kwargs)
            broken=copy.deepcopy(metadata)
            broken['views'][0]['label_layout']['fake_refill_layout_only']=True
            return canvas.copy(),broken,receipt
        with patch.object(auto_router,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector,'finish',new=bad):
            value=route()
        r=facts(value)['label_refill']
        self.assertFalse(r['applied']);self.assertEqual(r['reason'],'visible_refill_unavailable')
        self.assertEqual(r['candidate_readable_object_ids'],['risk-02-visible'])
        self.assertEqual(r['new_readable_object_ids'],[])
        self.assertEqual(refill_rows(value),[])

    def test_changed_or_nonproposal_output_never_replaces_original_canvas(self):
        original=visible_refill.VisibleRefillCollector.finish
        for channel in (0,1,2,None):
            observed={}
            def spill(self,canvas,metadata,meshes,**kwargs):
                result,changed,receipt=original(self,canvas,metadata,meshes,**kwargs)
                observed['helper_ready']=receipt.get('status')=='proposal_ready' and receipt.get('applied') is False
                observed['original_pixels']=canvas.tobytes()
                if channel is None:
                    return canvas.copy(),changed,receipt
                # A normal PIL write makes a readonly issued tile use a new
                # core. Even a one-channel mutation must invalidate its claim.
                pixel=list(result.tile.getpixel((0,0)))
                pixel[channel]^=1;result.tile.putpixel((0,0),tuple(pixel))
                return result,changed,receipt
            with self.subTest(channel=channel), \
                 patch.object(auto_router,'visible_refill_clock',return_value=0.), \
                 patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
                 patch.object(visible_refill.VisibleRefillCollector,'finish',new=spill):
                value=route()
            self.assertTrue(observed['helper_ready'])
            self.assertFalse(facts(value)['label_refill']['applied'])
            self.assertEqual(facts(value)['label_refill']['reason'],'visible_refill_unavailable')
            self.assertEqual(refill_rows(value),[])
            self.assertEqual(Image.open(io.BytesIO(png(value))).tobytes(),observed['original_pixels'])

    def test_router_composition_exception_after_valid_proposal_is_atomic(self):
        original=visible_refill.VisibleRefillCollector.finish
        paste=Image.Image.paste;observed={}
        def finish(self,canvas,*args,**kwargs):
            result=original(self,canvas,*args,**kwargs)
            observed['helper_ready']=result[2].get('status')=='proposal_ready' and result[2].get('applied') is False
            observed['original_pixels']=canvas.tobytes();observed['ready']=True
            return result
        def fail(self,*args,**kwargs):
            if observed.get('ready') and self.size==(512,512):
                observed['composition_attempted']=True
                raise OSError('injected root composition failure')
            return paste(self,*args,**kwargs)
        with patch.object(auto_router,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(visible_refill.VisibleRefillCollector,'finish',new=finish), \
             patch.object(Image.Image,'paste',new=fail):
            value=route()
        self.assertTrue(observed['helper_ready']);self.assertTrue(observed['composition_attempted'])
        self.assertFalse(facts(value)['label_refill']['applied'])
        self.assertEqual(facts(value)['label_refill']['error_type'],'OSError')
        self.assertEqual(refill_rows(value),[])
        self.assertEqual(Image.open(io.BytesIO(png(value))).tobytes(),observed['original_pixels'])

    def test_shared_budget_after_caption_is_checked_without_another_raster(self):
        clock={'value':0.};original=visible_refill.VisibleRefillCollector.finish
        caption=auto_router._annotate_orthogonal_target_measurement
        def late_caption(*args,**kwargs):
            result=caption(*args,**kwargs);clock['value']=.039;return result
        def late_finish(*args,**kwargs):
            result=original(*args,**kwargs);clock['value']=.041;return result
        with patch.object(auto_router,'visible_refill_clock',side_effect=lambda:clock['value']), \
             patch.object(visible_refill,'visible_refill_clock',return_value=0.), \
             patch.object(auto_router,'_annotate_orthogonal_target_measurement',new=late_caption), \
             patch.object(visible_refill.VisibleRefillCollector,'finish',new=late_finish):
            value=route()
        r=facts(value)['label_refill']
        self.assertFalse(r['applied']);self.assertEqual(r['candidate_raster_count'],0)
        self.assertAlmostEqual(r['shared_budget_elapsed_before_ms'],39.)
        self.assertAlmostEqual(r['shared_budget_elapsed_after_ms'],41.)
        self.assertEqual(refill_rows(value),[])

    def test_full_brief_cache_preserves_new_identity_and_separates_current_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            path.write_text(json.dumps({'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                'quad_size':256,'max_sessions':2,'state_file':'state.json','audit_file':'audit.jsonl'}),encoding='utf-8')
            host=ReadOnlyHost();host.raw=raw();service=LiveSpatialService(path,host=host)
            with patch.object(auto_router,'visible_refill_clock',return_value=0.), \
                 patch.object(visible_refill,'visible_refill_clock',return_value=0.):
                full=service.observe('refill-cache',focal_id='focus',reference_id='reference')
            f=json.loads(full['routing']['context_text']);self.assertTrue(f['label_refill']['applied'])
            brief=project_task_brief(full);self.assertIsNotNone(brief)
            self.assertEqual(brief['observation']['label_refill'],f['label_refill'])
            self.assertEqual(brief['observation']['canvas']['object_labels'],f['canvas']['object_labels'])
            self.assertEqual(brief['routing']['image'],full['routing']['image'])
            with patch.object(visible_refill.VisibleRefillCollector,'finish',side_effect=AssertionError('cache rerender')):
                reused=service.observe('refill-cache',focal_id='focus',reference_id='reference')
            cache=json.loads(reused['routing']['context_text'])
            self.assertTrue(reused['routing']['cache_hit'])
            self.assertTrue(cache['label_refill']['evidence_reused'])
            self.assertEqual(cache['label_refill']['current_event_refill_cost_ms'],0.)
            self.assertEqual(cache['label_refill']['current_event_candidate_raster_count'],0)
            self.assertEqual(cache['label_refill']['new_readable_object_ids'],['risk-02-visible'])
            self.assertEqual(reused['routing']['image'],full['routing']['image']);self.assertEqual(host.applies,0)


if __name__=='__main__':unittest.main()
