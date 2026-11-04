"""Authored product-adapter guards; no Blender, scene solver or quality claim."""
from __future__ import annotations
import base64,contextlib,copy,hashlib,io,json,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from verification import visual004_product as p
from verification import visual004_native as n


def png():
    buffer=io.BytesIO();Image.new('RGB',(8,6),(24,88,142)).save(buffer,format='PNG');return buffer.getvalue()


def image_block(raw=None):
    return dict(type='image',mimeType='image/png',data=base64.b64encode(png() if raw is None else raw).decode('ascii'))


def response(*content,is_error=False):
    return dict(jsonrpc='2.0',id='authored-response',result=dict(content=list(content),isError=is_error))


class FakeNativeSession:
    def __init__(self,workspace,*,condition='P'):
        self.workspace=Path(workspace).resolve();self.workspace.mkdir(parents=True,exist_ok=True)
        asset=self.workspace/'fixture.blend';asset.write_bytes(b'authored-no-real-Blender-file')
        self.config=dict(condition=condition,pid=12345,deadline_ns=time.perf_counter_ns()+60_000_000_000,
            asset=str(asset),asset_sha256=n.sha(asset));self.host='127.0.0.1';self.port=21999;self.aborts=[]
    def abort(self,reason):
        self.aborts.append(reason);target=self.workspace/'POISONED.json'
        if not target.exists():n.save(target,dict(reason=reason,original_deadline_ns=self.config['deadline_ns']))


class ProductAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.session=FakeNativeSession(self.root/'session')
        self.hosts=[];self.services=[];self.servers=[];self.handler=lambda request,server:response(dict(type='text',text='{}'))
        self.service_deadline=None;self.service_failure=None;test=self
        class Host:
            def __init__(self,root,**kwargs):self.is_alive=True;self.close_calls=0;self.kwargs=kwargs;test.hosts.append(self)
            def close(self):self.close_calls+=1;self.is_alive=False
        class Service:
            def __init__(self,path,*,host,production_mode):
                self.host=host;self.config=n.load(path);self.active_budget=None;self.budgets=[];test.services.append(self)
                if test.service_failure:raise test.service_failure
            @contextlib.contextmanager
            def _request_budget(self):
                budget=dict(deadline=time.monotonic()+20 if test.service_deadline is None else test.service_deadline)
                self.active_budget=budget;self.budgets.append(budget)
                try:yield budget
                finally:self.active_budget=None
        class Server:
            def __init__(self,service,*,default_session_id):
                self.service=service;self.session_id=default_session_id;self.requests=[];self.forwarded_deadlines=[];test.servers.append(self)
            def handle_jsonrpc_message(self,request):
                self.requests.append(copy.deepcopy(request));self.forwarded_deadlines.append(self.service.active_budget['deadline'])
                return test.handler(request,self)
        def module(name,**values):
            value=types.ModuleType(name);value.__dict__.update(values);return value
        modules={
            'human_eye_plugin.runtime_identity':module('human_eye_plugin.runtime_identity',
                runtime_identity=lambda:dict(source_sha256=p.PIN,source_files=[None]*129,implementation_revision='authored-fixed'),
                check_source_drift=lambda:dict(compatible=True)),
            'human_eye_plugin.blender_mcp_host':module('human_eye_plugin.blender_mcp_host',BlenderMCPHost=Host),
            'human_eye_plugin.live_service':module('human_eye_plugin.live_service',LiveSpatialService=Service),
            'human_eye_plugin.live_spatial_mcp':module('human_eye_plugin.live_spatial_mcp',LiveSpatialMCPServer=Server)}
        self.modules=patch.dict(sys.modules,modules);self.modules.start();self.addCleanup(self.modules.stop)
        p._OWNED_CONTEXTS.clear();self.addCleanup(p._OWNED_CONTEXTS.clear)
    def observe(self,name='test',arguments=None):return p.observe(self.session,{} if arguments is None else arguments,request_id=name)
    def cost(self,name='test'):return n.load(self.session.workspace/'product_calls'/name/'COST.json')
    def native_event(self,index,result=None):
        path=self.session.workspace/('call_'+str(index));path.mkdir()
        text='not a product response' if result is None else 'HUMAN_EYE_BLENDER_MCP:'+json.dumps(dict(result=result))
        (path/'stdout.txt').write_text(text,encoding='utf8');return path

    def test_N_cannot_construct_product_host_or_use_existing_P_context(self):
        self.observe('P-first');self.session.config['condition']='N'
        with self.assertRaisesRegex(ValueError,'P_only_product'):self.observe('N-cannot-reuse')
        self.assertEqual(len(self.hosts),1);self.assertEqual(len(self.servers[0].requests),1)
    def test_readonly_query_and_fixed_visual_mode_whitelists(self):
        for visual in sorted(p.ALLOWED_VISUAL):
            args=dict(query=dict(mode='overview',native_visual=dict(mode=visual[0],view=visual[1])),include_image=True)
            self.assertEqual(p.validate_observe_arguments(args),args)
        rejected=[dict(goal={}),dict(session_id='new'),dict(query=dict(operation='restore_preview')),
            dict(query=dict(mode='mesh_structure')),dict(query=dict(mode='mesh_surface')),
            dict(query=dict(native_visual=dict(mode='multiscale',view='SCENE'))),
            dict(query=dict(native_visual=dict(mode='projection',view='XY'))),
            dict(query=dict(native_visual=dict(mode='auto',view='YZ')))]
        for args in rejected:
            with self.subTest(args=args),self.assertRaises(ValueError):p.validate_observe_arguments(args)
        self.assertFalse(self.hosts)
    def test_task_deadline_shortens_request_scope_without_increasing_config_lease(self):
        self.session.config['deadline_ns']=2_000_001_000
        with patch.object(p.time,'perf_counter_ns',return_value=1000),patch.object(p.time,'monotonic',return_value=10.):
            self.observe()
        self.assertEqual(self.servers[0].forwarded_deadlines,[12.])
        config=n.load(self.session.workspace/'PRODUCT_CONFIG.json')
        self.assertEqual(config['request_budget_s'],20.);self.assertEqual(config['native_visual_timeout_s'],10.)
        self.assertEqual(self.cost()['original_task_deadline_ns'],2_000_001_000)
    def test_already_shorter_service_budget_is_never_extended(self):
        self.session.config['deadline_ns']=2_000_001_000;self.service_deadline=10.25
        with patch.object(p.time,'perf_counter_ns',return_value=1000),patch.object(p.time,'monotonic',return_value=10.):
            self.observe()
        self.assertEqual(self.servers[0].forwarded_deadlines,[10.25])
    def test_persistent_context_reuses_same_host_service_server(self):
        self.observe('one');self.observe('two')
        self.assertEqual((len(self.hosts),len(self.services),len(self.servers)),(1,1,1))
        self.assertEqual(len(self.servers[0].requests),2)
        p.close_product(self.session);self.assertEqual(self.hosts[0].close_calls,1);self.assertFalse(p._OWNED_CONTEXTS)
    def test_changed_pid_or_original_deadline_cannot_replace_context(self):
        self.observe('first');original=copy.deepcopy(self.session.config)
        for key,delta in [('pid',1),('deadline_ns',1_000_000)]:
            self.session.config=copy.deepcopy(original);self.session.config[key]+=delta
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'product_context_not_replaced'):self.observe(key)
        self.assertEqual(len(self.hosts),1);self.assertEqual(len(self.servers[0].requests),1)
    def test_dead_host_poison_is_persistent_and_no_reconnect_occurs(self):
        def fail(request,server):server.service.host.is_alive=False;raise TimeoutError('authored lost wire')
        self.handler=fail
        with self.assertRaisesRegex(TimeoutError,'authored lost wire'):self.observe('lost')
        self.assertTrue((self.session.workspace/'POISONED.json').exists())
        with self.assertRaisesRegex(ValueError,'session_poisoned'):self.observe('cannot-resume')
        self.assertEqual(len(self.hosts),1);self.assertEqual(len(self.servers[0].requests),1)
        cost=self.cost('lost');self.assertIsNone(cost['mcp_content_image_blocks'])
        self.assertEqual(cost['public_images_registered'],0);self.assertIsNone(cost['all_render_attempt_images_constructed'])
    def test_JSON_RPC_error_is_exposed_not_a_false_success(self):
        rpc=dict(code=-32602,message='authored unsupported query')
        self.handler=lambda request,server:dict(jsonrpc='2.0',id=request['id'],error=rpc)
        result=self.observe();self.assertTrue(result['mcp_is_error']);self.assertEqual(result['rpc_error'],rpc)
        self.assertEqual(result['images'],[]);self.assertFalse(result['actual_model_image_delivery_confirmed'])
    def test_MCP_isError_remains_explicit_even_when_text_is_not_JSON(self):
        self.handler=lambda request,server:response(dict(type='text',text='explicit refusal'),is_error=True)
        result=self.observe();self.assertTrue(result['mcp_is_error']);self.assertEqual(result['mcp_text'],['explicit refusal'])
        self.assertIsNone(result['actual_product_metadata']);self.assertIsNone(result['visual_delivery'])
    def test_identical_PNG_blocks_keep_distinct_ordinals_and_content_positions(self):
        block=image_block();self.handler=lambda request,server:response(block,dict(type='text',text='{}'),copy.deepcopy(block))
        result=self.observe();rows=result['images'];self.assertEqual([row['mcp_content_index'] for row in rows],[0,2])
        self.assertEqual([row['construction_ordinal'] for row in rows],[1,2]);self.assertNotEqual(rows[0]['image_id'],rows[1]['image_id'])
        self.assertEqual(rows[0]['sha256'],rows[1]['sha256']);self.assertTrue(rows[1]['same_bytes_previously_registered'])
        state=n.ImageLedger(self.session.workspace).status();self.assertEqual(state['reserved_images'],0)
        self.assertTrue(all(row['delivery_state']=='not_delivered' for row in state['constructions']))
        self.assertEqual(self.cost()['mcp_content_image_blocks'],2);self.assertEqual(self.cost()['public_images_registered'],2)
        self.assertIsNone(self.cost()['all_render_attempt_images_constructed'])
    def test_second_invalid_MIME_keeps_first_construction_and_both_content_blocks(self):
        bad=image_block();bad['mimeType']='image/jpeg'
        self.handler=lambda request,server:response(image_block(),bad)
        with self.assertRaisesRegex(ValueError,'product_png_mime'):self.observe()
        cost=self.cost();self.assertEqual(cost['mcp_content_image_blocks'],2);self.assertEqual(cost['public_images_registered'],1)
        self.assertIsNone(cost['all_render_attempt_images_constructed']);self.assertEqual(n.ImageLedger(self.session.workspace).status()['reserved_images'],0)
    def test_actual_response_blocks_remain_counted_when_final_deadline_expires_before_registration(self):
        original_deadline=self.session.config['deadline_ns'];clock=[original_deadline-1_000_000_000]
        def late(request,server):clock[0]=original_deadline+1;return response(image_block(),image_block())
        self.handler=late
        with patch.object(p.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):self.observe()
        cost=self.cost();self.assertEqual(cost['mcp_content_image_blocks'],2,'actual returned image blocks must not silently become zero')
        self.assertEqual(cost['public_images_registered'],0);self.assertIsNone(cost['all_render_attempt_images_constructed'])
        self.assertEqual(cost['original_task_deadline_ns'],original_deadline)
    def test_private_native_evidence_is_only_new_calls_not_repeated_old_totals(self):
        self.native_event(1,dict(old='not charged again',png_sha256='1'*64))
        def current(request,server):
            self.native_event(2,dict(plan=dict(image_sha256='2'*64),images=[dict(png_sha256='3'*64,image_base64='do-not-copy')]))
            return response(dict(type='text',text='{}'))
        self.handler=current;self.observe('new');self.handler=lambda request,server:response(dict(type='text',text='{}'));self.observe('cached')
        first=self.cost('new')['native_private_evidence'];self.assertEqual([row['call'] for row in first],['call_2'])
        self.assertEqual({row['sha256'] for row in first[0]['raw_png_hashes']},{'2'*64,'3'*64})
        self.assertNotIn('do-not-copy',json.dumps(first));self.assertEqual(self.cost('cached')['native_private_evidence'],[])
    def test_partial_context_initialization_closes_unretained_host(self):
        self.service_failure=ValueError('authored bad service config')
        with self.assertRaisesRegex(ValueError,'authored bad service config'):self.observe()
        self.assertEqual(len(self.hosts),1);self.assertEqual(self.hosts[0].close_calls,1,'a half-constructed context must release its owned host')
        self.assertFalse(p._OWNED_CONTEXTS)


if __name__=='__main__':unittest.main()
