"""Owner broker accounting/identity fixtures; no Blender or task solver."""
import io,json,os,socket,subprocess,sys,tempfile,threading,time,types,unittest
from pathlib import Path
from unittest.mock import patch
from verification import visual004_session as b
from verification.visual004_native import ImageLedger,load
from verification.test_visual004_native import png

class FakeOwner:
    def __init__(self,workspace,condition='N'):
        self.workspace=workspace;self.config=dict(condition=condition,deadline_ns=time.perf_counter_ns()+600*10**9)
        self.calls=[];self.abort_calls=[];self.close_calls=0;self.output='authored generic output';self.failure=None
    def run(self,code,timeout_s):
        self.calls.append((code,timeout_s))
        if self.failure:raise self.failure
        return dict(response=dict(status='success',result=dict(executed=True,result=self.output)),original_deadline_ns=self.config['deadline_ns'])
    def status(self):return dict(pid=12345,owned=True)
    def abort(self,reason):
        self.abort_calls.append(reason);(self.workspace/'POISONED.json').write_text('{}',encoding='utf8')
    def close(self):self.close_calls+=1;return dict(pid=12345,exit_code=0,process_reaped=True)

class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.owner=FakeOwner(self.root);self.broker=b.OwnerBroker(self.owner,started_ns=time.perf_counter_ns(),deadline_ns=self.owner.config['deadline_ns'])
    def request(self,op='native_run',args=None,rid=None):
        return self.broker.handle(dict(request_id=rid or 'request-'+str(len(self.broker.state['events'])+1),operation=op,
            args=dict(code="print('no supplied solver')") if args is None else args))
    def test_same_owner_and_deadline_reused_for_multiple_generic_scripts(self):
        one=self.request();two=self.request()
        self.assertTrue(one['ok'] and two['ok']);self.assertEqual(len(self.owner.calls),2)
        self.assertEqual(one['original_deadline_ns'],two['original_deadline_ns']);self.assertIs(self.broker.session,self.owner)
    def test_N_observe_rejected_without_importing_product_or_running_code(self):
        before=set(sys.modules);response=self.request('observe',dict(arguments={}))
        self.assertFalse(response['ok']);self.assertIn('P_only_product',response['error']['message'])
        self.assertEqual(self.owner.calls,[]);self.assertFalse(any(name.startswith('human_eye') for name in set(sys.modules)-before))
        self.assertEqual(self.broker.state['public_calls'],1)
    def test_invalid_request_is_charged_before_validation(self):
        response=self.broker.handle(dict(bad='request'))
        self.assertFalse(response['ok']);self.assertEqual(self.broker.state['public_calls'],1)
        self.assertEqual(len(self.broker.state['events']),1)
    def test_duplicate_ID_spends_call_but_never_reexecutes(self):
        self.assertTrue(self.request(rid='same')['ok']);again=self.request(rid='same')
        self.assertFalse(again['ok']);self.assertIn('duplicate_request_no_replay',again['error']['message'])
        self.assertEqual(len(self.owner.calls),1);self.assertEqual(self.broker.state['public_calls'],2)
    def test_budget_exhaustion_blocks_new_execution_but_owner_close_still_works(self):
        with patch.object(b,'MAX_PUBLIC_CALLS',2):
            self.request();self.request();failed=self.request()
        self.assertIsNone(failed);self.assertEqual(self.broker.state['events'][-1]['state'],'public_call_budget_failed_no_payload')
        self.assertEqual(len(self.owner.calls),2)
        closed=self.request('close',{});self.assertTrue(closed['ok']);self.assertEqual(self.owner.close_calls,1)
        self.assertTrue(closed['result']['process_reaped']);self.assertEqual(self.broker.state['public_calls'],3)
    def test_full_overbudget_text_retained_privately_and_not_silently_truncated(self):
        self.owner.output='X'*(b.TEXT_LIMIT+500)
        response=self.request();self.assertFalse(response['ok']);self.assertEqual(response['error']['type'],'PublicTextBudgetExceeded')
        full=load(self.root/'broker_calls/1/FULL_RESULT.json')
        self.assertEqual(full['result']['native']['response']['result']['result'],self.owner.output)
        self.assertNotIn(self.owner.output,b.encoded(response).decode('ascii'))
        self.assertEqual(self.broker.state['public_data_bytes'],0);self.assertLess(self.broker.state['public_text_bytes'],b.CONTROL_LIMIT)
        self.owner.output='fixed compact script output';another=self.request();self.assertTrue(another['ok']);self.assertEqual(len(self.owner.calls),2)
    def test_full_data_allowance_is_not_reduced_by_future_error_reservations(self):
        self.owner.output='X'*(200*1024)
        response=self.request();self.assertTrue(response['ok'])
        self.assertGreater(self.broker.state['public_data_bytes'],200*1024)
        self.assertLess(self.broker.state['public_data_bytes'],b.TEXT_LIMIT)
        self.assertEqual(self.broker.state['public_data_bytes']+self.broker.state['public_control_bytes'],self.broker.state['public_text_bytes'])
    def test_control_wire_never_exceeds_fixed_allowance(self):
        self.broker.state['public_control_bytes']=b.CONTROL_LIMIT
        self.broker.state['public_text_bytes']=b.CONTROL_LIMIT
        reply=self.request();self.assertIsNone(reply)
        self.assertEqual(self.broker.state['public_control_bytes'],b.CONTROL_LIMIT)
        self.assertEqual(self.broker.state['public_text_bytes'],b.CONTROL_LIMIT)
        closed=self.request('close',{});self.assertIsNone(closed)
        self.assertEqual(self.owner.close_calls,1);self.assertTrue(self.broker.state['close_receipt']['process_reaped'])
    def test_original_expired_window_does_not_execute_or_extend(self):
        self.broker.deadline_ns=time.perf_counter_ns()-1
        response=self.request();self.assertFalse(response['ok']);self.assertIn('original_deadline',response['error']['message'])
        self.assertEqual(self.owner.calls,[])
    def test_transport_unknown_aborts_owner_and_never_reopens(self):
        self.owner.failure=TimeoutError('authored transport unknown');failed=self.request()
        self.assertFalse(failed['ok']);self.assertEqual(self.owner.abort_calls,['broker_transport_uncertain'])
        self.owner.failure=None;again=self.request()
        self.assertFalse(again['ok']);self.assertIn('session_poisoned',again['error']['message']);self.assertEqual(len(self.owner.calls),1)
    def test_delivery_path_outside_workspace_is_rejected(self):
        response=self.request(args=dict(code='pass',deliver_paths=['../other.png']))
        self.assertFalse(response['ok']);self.assertIn('image_workspace',response['error']['message'])
    def test_rendered_file_registration_and_reservation_do_not_claim_consumption(self):
        (self.root/'own.png').write_bytes(png())
        response=self.request(args=dict(code='pass',deliver_paths=['own.png']))
        self.assertTrue(response['ok']);self.assertEqual(len(response['result']['image_refs']),1)
        self.assertIsNone(response['model_image_consumption_confirmed'])
        ledger=ImageLedger(self.root).status();self.assertEqual(ledger['reserved_images'],1)
        self.assertIsNone(ledger['reservations'][0]['model_received'])
    def test_same_image_reserved_again_spends_again(self):
        ledger=ImageLedger(self.root);image=ledger.register_external_image(png())
        one=self.request('image_reserve',dict(image_ids=[image['image_id']]))
        two=self.request('image_reserve',dict(image_ids=[image['image_id']]))
        self.assertTrue(one['ok'] and two['ok']);self.assertEqual(ledger.status()['reserved_images'],2)
    def test_close_is_idempotent_and_attestation_only_from_same_owner(self):
        first=self.request('close',{});second=self.request('close',{})
        self.assertTrue(first['ok'] and second['ok']);self.assertEqual(first['result'],second['result'])
        self.assertEqual(self.owner.close_calls,1);self.assertEqual(self.broker.state['public_calls'],0)
    def test_P_close_releases_actual_product_cache_and_N_does_not_import_it(self):
        module=types.ModuleType('verification.visual004_product');calls=[]
        module.close_product=lambda owner:calls.append(owner)
        self.owner.config['condition']='P'
        with patch.dict(sys.modules,{'verification.visual004_product':module}):self.request('close',{})
        self.assertEqual(calls,[self.owner]);self.assertEqual(self.owner.close_calls,1)
    def test_product_cleanup_failure_still_closes_and_reaps_native_owner(self):
        module=types.ModuleType('verification.visual004_product')
        def fail(owner):raise OSError('authored close metadata failure')
        module.close_product=fail;self.owner.config['condition']='P'
        with patch.dict(sys.modules,{'verification.visual004_product':module}):response=self.request('close',{})
        self.assertEqual(self.owner.close_calls,1);self.assertTrue(response['result']['process_reaped'])
        self.assertEqual(response['result']['product_context_cleanup_error']['type'],'OSError')
    def _expiry_during_persistence(self,filename):
        original=b.save;early=time.perf_counter_ns();late=self.broker.deadline_ns+1;clock={'late':False}
        def save_then_expire(path,value,**kwargs):
            result=original(path,value,**kwargs)
            if Path(path).name==filename:clock['late']=True
            return result
        with patch.object(b,'save',side_effect=save_then_expire),patch.object(b.time,'perf_counter_ns',side_effect=lambda:late if clock['late'] else early):
            response=self.request()
        self.assertFalse(response['ok']);self.assertEqual(response['error']['type'],'OriginalDeadlineExceeded')
        self.assertFalse(load(self.root/'broker_calls/1/PUBLIC_RESPONSE.json')['ok'])
        self.assertEqual(self.broker.state['public_data_bytes'],0)
        self.assertEqual(self.broker.state['events'][0]['state'],'deadline_exceeded_after_result')
    def test_expiry_during_full_result_persistence_never_returns_success(self):self._expiry_during_persistence('FULL_RESULT.json')
    def test_expiry_during_public_result_persistence_never_returns_success(self):self._expiry_during_persistence('PUBLIC_RESPONSE.json')

class ActualSocketAndCLITests(unittest.TestCase):
    """Actual local TCP plus isolated Python CLI, with a fake owned bpy peer."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
    def _request_cli(self,request,name):
        path=self.root/name;b.save(path,request)
        return subprocess.run([sys.executable,'-I','-B',str(Path(b.__file__).resolve()),'--workspace',str(self.root),
            '--requestJSON',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
    def test_real_serve_socket_and_isolated_CLI_reuse_one_owner_and_close_it(self):
        owner=FakeOwner(self.root);owner.config.update(pid=os.getpid(),asset_sha256='a'*64,helper_sha256='authored-neutral-fixture')
        errors=[]
        def start_owner(**kwargs):owner.config['deadline_ns']=kwargs['deadline_ns'];return owner
        def run():
            try:b.serve(asset='unused authored fixture',blender='not started',workspace=self.root,condition='N',seconds=12)
            except BaseException as exc:errors.append(exc)
        capture=io.TextIOWrapper(io.BytesIO(),encoding='utf8')
        with patch.object(b.NativeSession,'start',side_effect=start_owner),patch.object(b.sys,'stdout',capture):
            thread=threading.Thread(target=run);thread.start()
            try:
                end=time.monotonic()+3
                while not (self.root/'BROKER_READY.json').exists():
                    if errors:raise errors[0]
                    self.assertLess(time.monotonic(),end);time.sleep(.001)
                for number in (1,2):
                    result=self._request_cli(dict(request_id='cli-'+str(number),operation='native_run',args=dict(code='print(1)')),
                        'REQUEST_'+str(number)+'.json')
                    self.assertEqual(result.returncode,0,result.stderr.decode('utf8',errors='replace'))
                    reply=json.loads(result.stdout);self.assertTrue(reply['ok'])
                    self.assertEqual(reply['result']['stdout'],'authored generic output')
                close=self._request_cli(dict(request_id='close',operation='close',args={}),'CLOSE_REQUEST.json')
                self.assertEqual(close.returncode,0,close.stderr.decode('utf8',errors='replace'))
                self.assertTrue(json.loads(close.stdout)['result']['process_reaped'])
                self.assertEqual(len(owner.calls),2);self.assertEqual(owner.close_calls,1)
            finally:
                if thread.is_alive():
                    try:b.client(self.root,dict(request_id='cleanup',operation='close',args={}))
                    except BaseException:pass
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
    def _empty_peer(self):
        server=socket.socket(socket.AF_INET,socket.SOCK_STREAM);server.bind(('127.0.0.1',0));server.listen(1)
        b.save(self.root/'BROKER_READY.json',dict(host='127.0.0.1',port=server.getsockname()[1],
            helper_sha256=b.sha(b.__file__),original_deadline_ns=time.perf_counter_ns()+10*10**9))
        def reply_empty():
            try:
                with server:
                    connection,_=server.accept()
                    with connection:
                        while connection.recv(65536):pass
            finally:server.close()
        thread=threading.Thread(target=reply_empty);thread.start();return thread
    def test_actual_socket_empty_response_has_explicit_budget_rejection(self):
        thread=self._empty_peer()
        try:
            with self.assertRaisesRegex(ValueError,'broker_public_budget_rejected_no_payload'):
                b.client(self.root,dict(request_id='empty',operation='status',args={}))
        finally:thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
    def test_isolated_CLI_empty_response_cannot_raise_unbound_local(self):
        thread=self._empty_peer()
        try:result=self._request_cli(dict(request_id='empty-cli',operation='status',args={}), 'EMPTY_REQUEST.json')
        finally:thread.join(timeout=2)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'broker_public_budget_rejected_no_payload',result.stderr)
        self.assertNotIn(b'UnboundLocalError',result.stderr)

if __name__=='__main__':unittest.main()
