import copy,json,tempfile,time,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import structure_task as t
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer,LIVE_MCP_TOOLS_SCHEMA
from verification.test_mesh_structure_service import TypedRawHost


class StructureTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.config=self.root/'config.json'
        self.config.write_text(json.dumps(dict(schema_version='1.0',enabled=True,
            project_root=str(Path(__file__).resolve().parents[1]),state_file='state.json',audit_file='audit.jsonl',
            structure_task_file='read-task.json',quad_size=64,max_sessions=4)),encoding='utf8')
        self.host=TypedRawHost();self.service=LiveSpatialService(self.config,host=self.host)
        self.server=LiveSpatialMCPServer(self.service,'test-default')
        self.clock=patch('human_eye_plugin.structure_task_service.counter_descriptor',return_value={'test_clock':True})
        self.clock.start();self.addCleanup(self.clock.stop)

    def register(self,**kwargs):return t.register(self.config,'target',**kwargs)
    def call(self,request,*,operation='diagnose',ref=None,images=False,**kwargs):
        q=dict(mode='mesh_structure',operation=operation,request_id=request)
        if ref:q['patch_ref']=ref
        response=self.server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=request,method='tools/call',
            params=dict(name='human_eye_scene_observe',arguments=dict(query=q,include_image=images,**kwargs))))['result']
        return json.loads(response['content'][0]['text']),response
    def state(self):return json.loads((self.root/'read-task.json').read_text())

    def test_four_tools_no_registration_no_host(self):
        value,response=self.call('a');self.assertEqual(len(LIVE_MCP_TOOLS_SCHEMA),4)
        self.assertEqual(value['status'],'error');self.assertIn('registration_required',value['error'])
        self.assertEqual(self.host.raw_calls,0);self.assertFalse((self.root/'read-task.json').exists())

    def test_diagnose_and_fresh_text_reference_reach_mcp(self):
        self.register();value,response=self.call('a')
        self.assertFalse(response['isError']);self.assertNotIn('pair_goal',value)
        self.assertEqual(value['diagnostic']['report']['source']['object_id'],'target')
        self.assertFalse(value['allow_action']);self.assertEqual(len(value['patch_refs']),1)
        ref=value['patch_refs'][0]['patch_ref'];again,_=self.call('b',operation='patch',ref=ref)
        self.assertEqual(again['reference_status'],'current');self.assertIn('selected_patch',again)
        self.assertEqual(self.state()['spent']['queries'],2);self.assertEqual(self.host.captures,0)
        self.assertFalse((self.root/'state.json').exists())

    def test_changed_session_labels_do_not_reset_budget(self):
        self.register()
        for i in range(6):
            value,response=self.call(str(i),session_id='different'+str(i),task_context={'task_id':str(i),'task_run_id':'new'})
            self.assertFalse(response['isError'])
        value,response=self.call('seven',session_id='again')
        self.assertTrue(response['isError']);self.assertIn('query_budget_exhausted',value['error'])
        self.assertEqual(self.host.raw_calls,6)

    def test_same_id_receipt_has_no_fresh_facts_and_changed_input_refuses(self):
        self.register();first,_=self.call('a');second,response=self.call('a',session_id='new')
        self.assertEqual(second['status'],'receipt');self.assertFalse(second['current_evidence'])
        self.assertNotIn('diagnostic',second);self.assertEqual(self.host.raw_calls,1)
        third,response=self.call('a',operation='patch',ref=first['patch_refs'][0]['patch_ref'])
        self.assertTrue(response['isError']);self.assertIn('request_id_conflict',third['error'])

    def test_missing_typed_image_preserves_text_and_refunds_unattempted_images(self):
        self.register();first,_=self.call('a')
        value,response=self.call('b',operation='patch',ref=first['patch_refs'][0]['patch_ref'],images=True)
        self.assertEqual(value['status'],'partial');self.assertEqual(value['image_status'],'unavailable')
        self.assertIn('diagnostic',value);self.assertIn('typed_patch_host_unavailable',value['image_reason'])
        self.assertEqual(len(response['content']),1);self.assertEqual(self.state()['spent']['images'],0)

    def test_image_budget_zero_still_returns_fresh_text(self):
        self.register(limits={**t.MAXIMA,'images':0,'png_bytes':0});first,_=self.call('a')
        value,_=self.call('b',operation='patch',ref=first['patch_refs'][0]['patch_ref'],images=True)
        self.assertEqual(value['image_status'],'budget_exhausted');self.assertIn('selected_patch',value)

    def test_wrong_object_and_ambiguous_pair_request_never_reach_host(self):
        self.register()
        for kwargs in ({'focal_id':'other'},{'reference_id':'other'}):
            value,response=self.call('a',**kwargs);self.assertTrue(response['isError'])
        self.assertEqual(self.host.raw_calls,0)

    def test_restart_does_not_claim_used_registration(self):
        self.register();self.call('a');other=LiveSpatialService(self.config,host=self.host)
        with self.assertRaisesRegex(ValueError,'service_restart'):
            other.observe('new',query=dict(mode='mesh_structure',operation='diagnose',request_id='b'),include_image=False)
        self.assertEqual(self.host.raw_calls,1)

    def test_pre_dispatch_commit_failure_never_calls_host_or_restarts(self):
        self.register()
        with patch('human_eye_plugin.structure_task._atomic_write',side_effect=OSError('disk fault')):
            value,response=self.call('a');self.assertTrue(response['isError'])
        self.assertEqual(self.host.raw_calls,0)
        value,_=self.call('b');self.assertIn('writer_failed',value['error'])

    def test_post_dispatch_commit_failure_cannot_reobserve(self):
        self.register();original=t._atomic_write;calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise OSError('lost commit')
            return original(*args,**kwargs)
        with patch('human_eye_plugin.structure_task._atomic_write',side_effect=fail_second):
            value,response=self.call('a');self.assertTrue(response['isError'])
        self.assertEqual(self.host.raw_calls,1);self.assertEqual(self.state()['inflight'],'a')
        value,_=self.call('b');self.assertIn('writer_failed',value['error']);self.assertEqual(self.host.raw_calls,1)

    def test_registered_deadline_not_renewed(self):
        self.register();original=self.state();store=t.TaskStore(self.config,self.service.config_fingerprint)
        with patch('human_eye_plugin.structure_task.time.perf_counter_ns',return_value=original['deadline_ns']):
            with self.assertRaisesRegex(ValueError,'expired'):
                with store.locked():pass
        self.assertEqual(self.state()['deadline_ns'],original['deadline_ns'])

    def test_registration_cannot_overwrite_and_config_switch_refused(self):
        self.register()
        with self.assertRaisesRegex(ValueError,'already_exists'):self.register()
        data=json.loads(self.config.read_text());data['max_sessions']=3;self.config.write_text(json.dumps(data))
        other=LiveSpatialService(self.config,host=self.host)
        with self.assertRaisesRegex(ValueError,'state_binding'):
            other.observe('s',query=dict(mode='mesh_structure',operation='diagnose',request_id='b'),include_image=False)

    def test_state_corruption_and_reserved_crash_not_treated_as_fresh_task(self):
        self.register();store=t.TaskStore(self.config,self.service.config_fingerprint)
        with store.locked() as state:store.reserve(state,'x','f'*64,want_images=True)
        with self.assertRaisesRegex(ValueError,'prior_outcome'):
            with store.locked():pass
        data=self.state();data['spent']['images']=0;(self.root/'read-task.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'charge_sum'):
            with store.locked():pass

    def test_conservative_image_reservation_and_text_limit(self):
        self.register();store=t.TaskStore(self.config,self.service.config_fingerprint)
        with store.locked() as state:
            store.reserve(state,'x','a'*64,want_images=True)
            store.finish(state,'x',text_bytes=20,images=0,png_bytes=0,outcome='partial',image_outcome_known=False)
        self.assertEqual(self.state()['spent']['images'],2);self.assertEqual(self.state()['confirmed']['images'],0)
        with store.locked() as state:
            store.reserve(state,'y','b'*64,want_images=True)
            self.assertEqual(state['requests']['y']['reserved']['images'],0)
            with self.assertRaisesRegex(ValueError,'output_exceeded'):
                store.finish(state,'y',text_bytes=t.TEXT_RESERVATION+1,images=0,png_bytes=0,outcome='x')

    def test_model_cannot_supply_deadline_task_or_raw_patch(self):
        base=dict(mode='mesh_structure',operation='diagnose',request_id='a')
        for field in ('deadline_ns','limits','task_id','patch','object_ids'):
            with self.subTest(field=field),self.assertRaises(ValueError):t.query({**base,field:1})

    def test_stale_reference_returns_new_facts_without_old_selected_patch(self):
        from verification.test_mesh_structure_runtime import raw_case,identity
        from verification.mesh_structure_fixtures import fixtures
        from human_eye_plugin import mesh_structure as m
        self.register();first,_=self.call('a');ref=first['patch_refs'][0]['patch_ref']
        def change(value):
            raw=raw_case(fixtures()[1]);raw['vertices'][0][0]+=.01
            ids=identity();ids['object_id']='target'
            fresh=m.analyze_raw(raw,ids,task_id=value['report']['task']['task_id'],categories=value['report']['task']['categories'],
                budget=m.WorkBudget(deadline_ns=value['accounting']['deadline_ns']))
            value.clear();value.update(fresh)
        self.host.bad=change
        second,_=self.call('b',operation='patch',ref=ref,images=True)
        self.assertEqual(second['reference_status'],'stale');self.assertNotIn('selected_patch',second)
        self.assertIn('diagnostic',second);self.assertEqual(self.state()['spent']['images'],0)
        third,_=self.call('c',operation='patch',ref=ref)
        self.assertIn('patch_ref_not_current',third['reason']);self.assertEqual(self.host.raw_calls,2)

    def test_partial_facts_and_reference_omission_are_explicit(self):
        from verification.test_mesh_structure_runtime import raw_case,identity
        from verification.mesh_structure_fixtures import fixtures
        from human_eye_plugin import mesh_structure as m
        self.register()
        def partial(value):
            ids=identity();ids['object_id']='target';prepared=m.prepare_raw(raw_case(fixtures()[1]),ids)
            fresh=m.analyze_prepared(prepared,task_id=value['report']['task']['task_id'],categories=value['report']['task']['categories'],
                budget=m.WorkBudget(deadline_ns=value['accounting']['deadline_ns'],max_work=0))
            value.clear();value.update(fresh)
        self.host.bad=partial;value,response=self.call('a')
        self.assertEqual(value['status'],'partial');self.assertIsNone(value['diagnostic']['report']['checks']['boundary_edges']['total'])
        self.assertEqual(value['patch_refs'],[])
        from human_eye_plugin.structure_task_service import _references
        state=self.state();original=copy.deepcopy(value['diagnostic']);original['patches']=[{'index':i} for i in range(17)]
        # Use 17 complete synthetic transport records, not truncated geometry.
        original['patches']=[dict(category='boundary_edges',cluster_ordinal=i,source_indices=[i],element_kind='edge',
            position={'status':'known'},raw_sha256='a'*64) for i in range(17)]
        refs,omitted=_references(state,original);self.assertEqual((len(refs),omitted),(16,1))

    def test_mcp_projection_rejects_late_or_undercharged_text(self):
        from human_eye_plugin.live_spatial_mcp import _tool_result
        self.register();value,_=self.call('a')
        late=copy.deepcopy(value);late['task_budget']['deadline_ns']=1
        with self.assertRaisesRegex(ValueError,'delivery deadline'):_tool_result(late,is_error=False)
        value['accounted_public_text_bytes']=1
        with self.assertRaisesRegex(ValueError,'committed charge'):_tool_result(value,is_error=False)

    def test_two_processes_share_one_claim(self):
        self.register();root=str(Path(__file__).resolve().parents[1])
        code="""import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from human_eye_plugin.structure_task import TaskStore
folder=Path(sys.argv[2]);name=sys.argv[3];store=TaskStore(folder/'config.json',sys.argv[4])
(folder/(name+'.ready')).write_text('ready')
until=time.monotonic()+15
while not (folder/'go').exists():
 if time.monotonic()>until:raise RuntimeError('barrier timeout')
 time.sleep(.01)
try:
 with store.locked() as state:
  store.reserve(state,name,'a'*64,want_images=False)
  store.finish(state,name,text_bytes=20,images=0,png_bytes=0,outcome='observed')
 result={'claimed':True}
except ValueError as exc:result={'claimed':False,'reason':str(exc)}
(folder/(name+'.json')).write_text(json.dumps(result))
"""
        children=[subprocess.Popen([sys.executable,'-I','-B','-c',code,root,str(self.root),name,self.service.config_fingerprint],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for name in ('one','two')]
        try:
            deadline=time.monotonic()+15
            while not all((self.root/(name+'.ready')).exists() for name in ('one','two')):
                self.assertLess(time.monotonic(),deadline);time.sleep(.01)
            (self.root/'go').write_text('go')
            for child in children:
                out,err=child.communicate(timeout=15);self.assertEqual(child.returncode,0,err)
            results=[json.loads((self.root/(name+'.json')).read_text()) for name in ('one','two')]
            self.assertEqual(sum(v['claimed'] for v in results),1)
            self.assertIn('service_restart',next(v['reason'] for v in results if not v['claimed']))
            self.assertEqual(self.state()['spent']['queries'],1)
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.communicate(timeout=10)


if __name__=='__main__':unittest.main()
