"""Confirmed construction is charged independently of deliverable evidence.

Consumer doubles represent already validated native image bundles. Existing
consumer suites independently validate producer geometry and native PNGs.
"""
import base64,copy,io,json,time,unittest
from contextlib import ExitStack
from unittest.mock import patch
from PIL import Image
from human_eye_plugin import structure_task as task
from human_eye_plugin.live_service import RequestBudgetError
from verification import test_structure_task as structure_setup,test_surface_tasks as surface_setup


def bundle():
    stream=io.BytesIO();Image.new('RGB',(384,384),(10,20,30)).save(stream,format='PNG')
    raw=stream.getvalue();return [dict(type='image',mimeType='image/png',data=base64.b64encode(raw).decode('ascii')) for _ in range(2)],2*len(raw)


class Harness:
    def __init__(self,kind):
        self.kind=kind;self.stack=ExitStack();self.case=(surface_setup.SurfaceTaskTests if kind=='surface' else structure_setup.StructureTaskTests)('runTest')
        self.case.setUp();self.stack.callback(self.case.doCleanups);self.case.register();self.image_calls=0
        self.images,self.png_bytes=bundle()
        if kind=='surface':
            ref=self.case.view_fixture();first,_=self.case.call('reference',operation='reference',reference_ref=ref,threshold_m=.0002)
            self.ref=first['feature_refs'][0]['patch_ref'];consumer='human_eye_plugin.reference_view_consumer'
            self.case.host.reference_view_capabilities=lambda:{};self.case.host.observe_reference_patch=self.image_call
            self.stage='after_surface_task'
        else:
            first,_=self.case.call('reference');self.ref=first['patch_refs'][0]['patch_ref'];self.stage='after_structure_task_host'
            if kind=='planar':
                consumer='human_eye_plugin.patch_observation';self.case.host.patch_observation_capabilities=lambda:{};self.case.host.observe_patch=self.image_call
            else:
                self.case.service.config['structure_patch_mode']=kind;consumer='human_eye_plugin.nonplanar_observation'
                self.case.host.nonplanar_observation_capabilities=lambda:{};self.case.host.observe_nonplanar_patch=self.image_call
        self.consumer=consumer
        self.stack.enter_context(patch(consumer+'.validate_capabilities',return_value={}))
        self.validation=self.stack.enter_context(patch(consumer+'.validate_result',side_effect=lambda *a,**k:dict(status='observed',images=copy.deepcopy(self.images))))

    def image_call(self,*args):self.image_calls+=1;return {}
    def call(self,name):
        if self.kind=='surface':return self.case.call(name,images=True,operation='reference_patch',patch_ref=self.ref)
        return self.case.call(name,images=True,operation='patch',ref=self.ref)
    def close(self):self.stack.close()
    def state(self):return self.case.state()
    def late_failure(self):
        original=self.case.service._check_request_budget
        def check(stage):
            if stage==self.stage:raise RequestBudgetError('expired',stage)
            return original(stage)
        self.stack.enter_context(patch.object(self.case.service,'_check_request_budget',side_effect=check))


def baseline_observations():
    rows=[]
    for kind in ('planar','surface'):
        h=Harness(kind)
        try:
            h.late_failure();first,_=h.call('patch1');one=h.state();calls1=h.image_calls
            second,_=h.call('patch2');two=h.state()
            rows.append(dict(kind=kind,after_first=dict(spent=one['spent'],confirmed=one['confirmed'],image_calls=calls1,status=first['status']),
                after_second=dict(spent=two['spent'],confirmed=two['confirmed'],image_calls=h.image_calls,status=second['status']),known_png_bytes=h.png_bytes))
        finally:h.close()
    return rows


class ImageCostCommitTests(unittest.TestCase):
    def harness(self,kind):
        h=Harness(kind);self.addCleanup(h.close);return h
    def assert_charge(self,h,*,unknown=False):
        state=h.state();self.assertEqual(state['spent']['images'],2)
        self.assertEqual(state['confirmed']['images'],0 if unknown else 2)
        self.assertEqual(state['spent']['png_bytes'],16*1024*1024 if unknown else h.png_bytes)
        self.assertEqual(state['confirmed']['png_bytes'],0 if unknown else h.png_bytes)
        return state

    def test_after_host_expiry_charges_validated_cost_without_delivery_or_second_render(self):
        for kind in ('planar','nonplanar_boundary_v1','nonplanar_dense_v1','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);h.late_failure();value,response=h.call('patch1')
                self.assertEqual(value['status'],'partial');self.assertEqual(len(response['content']),1)
                state=self.assert_charge(h);self.assertEqual(state['requests']['patch1']['receipt']['images_constructed'],2)
                self.assertEqual(state['requests']['patch1']['receipt']['png_bytes_constructed'],h.png_bytes)
                self.assertEqual(state['requests']['patch1']['receipt']['delivery'],'not_attested')
                h.call('patch2');self.assertEqual(h.image_calls,1);self.assert_charge(h)

    def test_normal_success_charges_two_and_duplicate_receipt_does_not_redeliver(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);value,response=h.call('patch1')
                self.assertEqual(len(response['content']),3);self.assert_charge(h)
                again,response=h.call('patch1');self.assertEqual(again['status'],'receipt');self.assertEqual(len(response['content']),1)
                self.assertEqual(h.image_calls,1);self.assert_charge(h)

    def test_validated_no_useful_images_refunds_unconstructed_image_reservation(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);h.validation.side_effect=lambda *a,**k:dict(status='no_useful_image',images=[])
                h.call('patch1');state=h.state();self.assertEqual(state['spent']['images'],0);self.assertEqual(state['spent']['png_bytes'],0)
                self.assertEqual(state['confirmed']['images'],0);self.assertEqual(h.image_calls,1)

    def test_unknown_consumer_outcome_holds_reservation_and_does_not_reissue(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);h.validation.side_effect=TimeoutError('consumer outcome unknown')
                value,response=h.call('patch1');self.assertEqual(len(response['content']),1);self.assert_charge(h,unknown=True)
                h.call('patch2');self.assertEqual(h.image_calls,1);self.assert_charge(h,unknown=True)

    def test_surface_post_image_reference_recheck_keeps_exact_known_cost(self):
        h=self.harness('surface');registry=h.case.service._surface_references;resolve=registry.resolve
        def check(*a,**k):
            if h.image_calls:raise ValueError('reference changed after known construction')
            return resolve(*a,**k)
        h.stack.enter_context(patch.object(registry,'resolve',side_effect=check));value,response=h.call('patch1')
        self.assertEqual(value['status'],'partial');self.assertEqual(len(response['content']),1);self.assert_charge(h)

    def test_original_deadline_after_validated_images_commits_cost_and_blocks_delivery(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);deadline=h.state()['deadline_ns'];clock=patch('time.perf_counter_ns',return_value=deadline+1)
                def validated(*a,**k):
                    clock.start();return dict(status='observed',images=copy.deepcopy(h.images))
                h.validation.side_effect=validated
                try:value,response=h.call('patch1')
                finally:clock.stop()
                self.assertTrue(response['isError']);self.assertEqual(len(response['content']),1)
                state=self.assert_charge(h);self.assertEqual(state['requests']['patch1']['phase'],'failed')
                self.assertEqual(state['deadline_ns'],deadline);self.assertEqual(h.image_calls,1)

    def test_text_budget_rejection_clears_delivery_but_keeps_exact_image_cost(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);h.validation.side_effect=lambda *a,**k:dict(status='observed',images=copy.deepcopy(h.images),oversized='x'*(100*1024))
                value,response=h.call('patch1');self.assertEqual(value['status'],'unavailable');self.assertEqual(len(response['content']),1)
                self.assert_charge(h);h.call('patch2');self.assertEqual(h.image_calls,1)

    def test_commit_failure_holds_reserved_cost_and_blocks_all_followups(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);write=task._atomic_write;calls=[]
                def fail(*a,**k):
                    calls.append(1)
                    if len(calls)==2:raise OSError('receipt commit failure')
                    return write(*a,**k)
                with patch('human_eye_plugin.structure_task._atomic_write',side_effect=fail):value,response=h.call('patch1')
                self.assertTrue(response['isError']);state=self.assert_charge(h,unknown=True);self.assertEqual(state['inflight'],'patch1')
                for name in ('patch1','patch2'):
                    value,response=h.call(name);self.assertTrue(response['isError']);self.assertIn('writer_failed',value['error'])
                self.assertEqual(h.image_calls,1)

    def test_commit_success_then_ack_failure_keeps_exact_cost_and_duplicate_receipt(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind);finish=task.TaskStore.finish
                def lost(self,*a,**k):finish(self,*a,**k);raise OSError('lost receipt acknowledgement')
                with patch.object(task.TaskStore,'finish',lost):value,response=h.call('patch1')
                self.assertTrue(response['isError']);self.assert_charge(h)
                value,response=h.call('patch1');self.assertEqual(value['status'],'receipt');self.assertEqual(len(response['content']),1)
                h.call('patch2');self.assertEqual(h.image_calls,1);self.assert_charge(h)

    def test_mcp_publication_failure_does_not_refund_committed_construction(self):
        for kind in ('planar','surface'):
            with self.subTest(kind=kind):
                h=self.harness(kind)
                from human_eye_plugin.live_spatial_mcp import _tool_result
                def publish(value,**kwargs):
                    if value.get('routing',{}).get('images'):raise ValueError('publication failed')
                    return _tool_result(value,**kwargs)
                with patch('human_eye_plugin.live_spatial_mcp._tool_result',side_effect=publish):
                    value,response=h.call('patch1')
                self.assertTrue(response['isError']);self.assertIn('publication failed',value['error'])
                self.assert_charge(h);h.call('patch2');self.assertEqual(h.image_calls,1)


if __name__=='__main__':unittest.main()
