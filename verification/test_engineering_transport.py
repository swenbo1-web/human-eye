"""Task fairness, reply bindings and real shared lifecycle negative cases."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from verification.engineering_task_contract import choose_region,he_regions
from verification.engineering_native_service import NativeService,ReadOnly
from human_eye_plugin.forward_deadline import counter_descriptor
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.structure_task_control import begin,close


class EngineeringContractTests(unittest.TestCase):
    def test_anchor_and_smaller_bounds_choose_without_ref_or_source_order(self):
        small=dict(ref='z',bounds=[[-.1,-.1,-.1],[.1,.1,.1]])
        large=dict(ref='a',bounds=[[-1,-1,-1],[1,1,1]])
        for regions in ([small,large],[large,small]):
            self.assertEqual(choose_region(regions,[0,0,0],total=2)['region']['ref'],'z')

    def test_omitted_or_unknown_regions_cannot_be_ignored(self):
        known=dict(ref='r',bounds=[[-.1]*3,[.1]*3])
        self.assertEqual(choose_region([known],[0,0,0],total=2,omitted=1)['status'],'unknown')
        self.assertEqual(choose_region([dict(ref='u',bounds=None)],[0,0,0],total=1)['status'],'unknown')
        self.assertEqual(choose_region([],[0,0,0],total=None,complete=False)['status'],'unknown')

    def test_coincident_regions_are_ambiguous(self):
        regions=[dict(ref=name,bounds=[[-1]*3,[1]*3]) for name in ('a','b')]
        self.assertEqual(choose_region(regions,[0,0,0],total=2)['reason'],'ambiguous_nearest_boundary')
        regions[1]['ref']='a'
        with self.assertRaisesRegex(ValueError,'duplicate'):choose_region(regions,[0,0,0],total=2)

    def test_invalid_and_extreme_coordinates_do_not_create_arbitrary_rank(self):
        for value in (True,float('nan')):
            with self.assertRaises(ValueError):choose_region([dict(ref='r',bounds=[[value]*3,[1]*3])],[0]*3,total=1)
        result=choose_region([dict(ref='r',bounds=[[1e308]*3,[1e308]*3])],[0]*3,total=1)
        self.assertEqual(result['status'],'unknown')

    def test_public_HE_omission_adapter_preserves_gap(self):
        value=dict(diagnostic=dict(report=dict(checks=dict(boundary_edges=dict(state='complete',total=3,omitted=1))),
            patches=[dict(category='boundary_edges',cluster_ordinal=0,position=dict(status='known',length_unit='m',world_bounds_m=[[-1]*3,[1]*3]))]),
            patch_refs=[dict(category='boundary_edges',cluster_ordinal=0,patch_ref='r')])
        regions,coverage=he_regions(value)
        self.assertEqual(choose_region(regions,[0]*3,**coverage)['status'],'unknown')

    def test_readonly_facade_rejects_both_action_tools(self):
        facade=ReadOnly(None,{})
        for result in (facade.transform('x',{}),facade.run_clearance_segment('x','r',{},execute=True)):
            self.assertEqual(result['status'],'refused');self.assertFalse(result['executed'])

    def test_HE_role_requires_registered_comparability_before_bootstrap(self):
        from verification.engineering_stdio import main
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);gate=root/'gate.json';spec=root/'spec.json'
            gate.write_text(json.dumps(dict(new_HE_trials_permitted=False)))
            spec.write_text(json.dumps(dict(arm='he',he_gate_file=str(gate))))
            with patch('verification.engineering_task_contract.bootstrap',side_effect=AssertionError('unexpected runtime')):
                with self.assertRaisesRegex(ValueError,'comparability'):main(spec)


class NativeReplyTests(unittest.TestCase):
    def service(self):
        service=NativeService.__new__(NativeService)
        service.benchmark=dict(peer_nonce='peer',host='127.0.0.1',port=1,source_sha256='a'*64)
        return service

    def call(self,mutation=None):
        service=self.service()
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def settimeout(self,*args):pass
            def sendall(self,raw):self.request=json.loads(raw);self.done=False
            def recv(self,size):
                if self.done:return b''
                self.done=True;p=self.request['params']
                value=dict(request_id=p['request_id'],peer_nonce=p['peer_nonce'],deadline_ns=p['deadline_ns'],clock=counter_descriptor(),
                    source_before='a'*64,source_after='a'*64,error=None,native=dict(status='observed',damage='not_inferred',facts={},regions=[],images=[]))
                if mutation:mutation(value)
                return json.dumps(value).encode()
        with patch('verification.engineering_native_service.socket.create_connection',return_value=Connection()):
            return service.probe('diagnose','target',time.perf_counter_ns()+10**9)

    def test_correct_reply_binding_is_accepted(self):
        value,images=self.call();self.assertEqual(value['status'],'observed');self.assertEqual(images,[])

    def test_request_nonce_clock_deadline_and_source_drift_are_rejected(self):
        mutations=[lambda v:v.update(request_id='other'),lambda v:v.update(peer_nonce='other'),
            lambda v:v.update(deadline_ns=1),lambda v:v.update(clock={}),lambda v:v.update(source_after='b'*64),
            lambda v:v.update(error='host failed')]
        for mutation in mutations:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.call(mutation)


class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=self.root/'CONFIG.json';self.config.write_text(json.dumps(dict(schema_version='1.0',enabled=True,
            project_root=str(Path(__file__).resolve().parents[1]),state_file='STATE.json',audit_file='AUDIT.jsonl',
            structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',quad_size=64,max_sessions=4)),encoding='utf8')
        self.service=NativeService(self.config,dict(helpers={}));self.server=LiveSpatialMCPServer(self.service)
        self.calls=[]
        def probe(*args,**kwargs):
            self.calls.append(args[0]);return dict(status='observed',damage='not_inferred',facts={},
                regions=[dict(bounds=[[-.1]*3,[.1]*3],edges=[[0,1]])],image_metadata=[]),[]
        self.service.probe=probe;self.task=begin(self.config,'test','target',categories=['boundary_edges'])

    def request(self,key,ref=None,images=False):
        q=dict(mode='mesh_structure',operation='patch' if ref else 'diagnose',request_id=key,task_ref=self.task['task_ref'])
        if ref:q['patch_ref']=ref
        reply=self.server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=key,method='tools/call',
            params=dict(name='human_eye_scene_observe',arguments=dict(query=q,include_image=images))))['result']
        return json.loads(reply['content'][0]['text']),reply

    def test_duplicate_receipt_no_reobserve_and_unknown_image_keeps_quota(self):
        first,_=self.request('d');ref=first['regions'][0]['ref']
        image,_=self.request('p',ref,True);self.assertEqual(image['task_budget']['spent']['images'],2)
        receipt,_=self.request('p',ref,True);self.assertEqual(receipt['status'],'receipt');self.assertEqual(self.calls,['diagnose','patch'])
        exhausted,_=self.request('e',ref,True);self.assertEqual(exhausted['image_status'],'budget_exhausted')
        self.assertEqual(self.calls,['diagnose','patch','diagnose'])
        result=close(self.config,self.task['task_ref']);self.assertEqual(result['task_budget']['spent']['queries'],3)
        _,reply=self.request('late');self.assertTrue(reply['isError']);self.assertEqual(len(self.calls),3)

    def test_bad_reference_cannot_observe(self):
        _,reply=self.request('bad','0'*32,True);self.assertTrue(reply['isError']);self.assertFalse(self.calls)

    def test_helper_drift_prevents_reservation_and_host_observation(self):
        source=self.root/'helper.py';source.write_text('# changed')
        self.service.benchmark['helpers']={str(source):'0'*64}
        _,reply=self.request('drift');self.assertTrue(reply['isError']);self.assertFalse(self.calls)

    def test_service_restart_cannot_reuse_claimed_generation(self):
        self.request('claimed');other=NativeService(self.config,dict(helpers={}))
        other.probe=lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not call host'))
        self.server=LiveSpatialMCPServer(other)
        _,reply=self.request('newprocess');self.assertTrue(reply['isError']);self.assertEqual(len(self.calls),1)


if __name__=='__main__':unittest.main()
