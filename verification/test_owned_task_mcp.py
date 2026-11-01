"""Protocol approval tests with explicit client/host doubles, not human evidence."""
import copy,io,json,threading,time,unittest
from unittest.mock import patch
from human_eye_plugin.owned_task_mcp import OwnedTaskMCP,GOAL_TOOL,proposal,valid_id
from verification import test_task_entry as setup


class OwnedTaskMCPTests(unittest.TestCase):
    setUp=setup.TaskEntryTests.setUp
    approve=setup.TaskEntryTests.approve
    mock_entry=setup.TaskEntryTests.mock_entry
    state=setup.TaskEntryTests.state
    write=setup.TaskEntryTests.write

    def server(self,protocol='2025-06-18',capabilities=None):
        self.mcp=OwnedTaskMCP(self.config,self.host,io.StringIO(),io.StringIO())
        self.entry=self.mcp.entry;self.mock_entry(self.entry);self.sent=[]
        self.mcp.handle(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion=protocol,
            capabilities={'elicitation':{}} if capabilities is None else capabilities)))
        self.client_result={'action':'accept','content':{'approve':True}}
        def emit(value):
            self.sent.append(copy.deepcopy(value))
            if value.get('method')=='elicitation/create':
                response=dict(jsonrpc='2.0',id=value['id'],result=copy.deepcopy(self.client_result))
                self.mcp.messages.put((response,self.now))
        self.mcp.emit=emit
        return self.mcp

    def call(self,arguments=None,request_id=2,**kwargs):
        arguments={'focal_id':'part','reference_id':'base'} if arguments is None else arguments
        return self.mcp.handle(dict(jsonrpc='2.0',id=request_id,method='tools/call',
            params=dict(name=GOAL_TOOL['name'],arguments=arguments)),**kwargs)

    def metadata(self,value):return json.loads(value['result']['content'][0]['text'])

    def test_typed_proposal_never_accepts_model_authorization(self):
        for field in ('approved','authorization_id','event_id','config','scene','blender','received_monotonic'):
            with self.assertRaises(ValueError):proposal(dict(focal_id='part',reference_id='base',**{field:True}))

    def test_legacy_no_capability_or_url_only_never_elicits_or_dispatches(self):
        for protocol,caps in [('2025-03-26',{'elicitation':{}}),('2025-06-18',{}),('2025-11-25',{'elicitation':{'url':{}}})]:
            server=self.server(protocol,caps)
            with patch.object(self.entry,'register',side_effect=AssertionError('registration forbidden')):response=self.call()
            self.assertFalse(self.sent);self.assertFalse(self.metadata(response)['executed'])

    def test_newer_negotiation_selects_implemented_june_form(self):
        server=self.server('2025-11-25',{'elicitation':{'form':{}}})
        self.assertTrue(server.elicitation)
        self.assertIn('initialize once',server.handle(dict(jsonrpc='2.0',id=9,method='initialize'))['error']['message'])

    def test_owned_entry_has_no_legacy_write_bypass(self):
        server=self.server();response=server.handle(dict(jsonrpc='2.0',id=4,method='tools/list'))
        self.assertEqual({t['name'] for t in response['result']['tools']},{GOAL_TOOL['name'],'human_eye_scene_observe','human_eye_connection_status'})
        for name in ('human_eye_transform','human_eye_clearance_segment'):
            response=server.handle(dict(jsonrpc='2.0',id=5,method='tools/call',params={'name':name,'arguments':{'execute':False}}))
            self.assertEqual(response['error']['code'],-32601)

    def test_accept_binds_actual_scope_and_preserves_original_receive_window(self):
        self.server()
        with patch.object(self.entry,'execute',return_value=dict(status='completed',executed_this_call=False,new_setter_count=0)) as execute:
            response=self.call(received_monotonic=98.)
        self.assertEqual(self.metadata(response)['status'],'completed');execute.assert_called_once()
        record=next(iter(self.state()['goal_authorizations']['records'].values()))
        self.assertEqual(record['grant']['issued_monotonic'],98.);self.assertEqual(record['grant']['deadline_monotonic'],128.)
        self.assertIn('"connector_config_sha256"',self.sent[0]['params']['message'])
        self.assertEqual(record['grant']['authorization_id'],self.sent[0]['id'])

    def test_decline_cancel_false_or_extra_content_cannot_create_grant(self):
        self.server()
        for index,answer in enumerate(({'action':'decline'},{'action':'cancel'},
                {'action':'accept','content':{'approve':False}}, {'action':'accept','content':{'approve':True,'authorization_id':'fake'}})):
            self.client_result=answer
            with patch.object(self.entry,'execute',side_effect=AssertionError('dispatch forbidden')):response=self.call(request_id=20+index)
            self.assertFalse(self.metadata(response)['executed']);self.assertFalse(self.entry._live)
        self.assertFalse(self.entry.service.state_path.exists())

    def test_numeric_one_cannot_impersonate_boolean_approval(self):
        for numeric in (1,1.0):
            self.server();self.client_result={'action':'accept','content':{'approve':numeric}}
            with patch.object(self.entry,'execute',side_effect=AssertionError('numeric approval must not dispatch')):result=self.call()
            self.assertFalse(self.metadata(result)['executed']);self.assertFalse(self.entry._live)

    def test_duplicate_call_id_cannot_repeat_approval_or_execution(self):
        self.server()
        with patch.object(self.entry,'execute',return_value=dict(status='review_required')) as execute:
            self.call();second=self.call()
        self.assertEqual(execute.call_count,1);self.assertEqual(len(self.sent),1);self.assertIn('duplicate',second['error']['message'])

    def test_wrong_approval_id_never_dispatches(self):
        self.server()
        def wrong(value):self.mcp.messages.put((dict(jsonrpc='2.0',id='foreign',result=self.client_result),self.now))
        self.mcp.emit=wrong
        with patch.object(self.entry,'execute',side_effect=AssertionError('dispatch forbidden')):result=self.call()
        self.assertFalse(self.metadata(result)['executed']);self.assertFalse(self.entry._live)

    def test_approval_wait_uses_original_deadline(self):
        self.server()
        real=self.mcp.emit
        def expired(value):real(value);self.now=130.
        self.mcp.emit=expired
        with patch.object(self.entry,'execute',side_effect=AssertionError('dispatch forbidden')):result=self.call()
        self.assertFalse(self.metadata(result)['executed']);self.assertFalse(self.entry._live)

    def test_changed_config_during_approval_cannot_dispatch(self):
        self.server();real=self.mcp.emit
        def changed(value):real(value);self.config.write_bytes(self.config.read_bytes()+b' ')
        self.mcp.emit=changed
        with patch.object(self.entry,'execute',side_effect=AssertionError('dispatch forbidden')):result=self.call()
        self.assertFalse(self.metadata(result)['executed']);self.assertFalse(self.entry._live)

    def test_exception_after_execute_boundary_is_unknown_never_false_zero(self):
        self.server()
        with patch.object(self.entry,'execute',side_effect=OSError('lost executor outcome')):result=self.call()
        value=self.metadata(result);self.assertIsNone(value['executed']);self.assertIsNone(value['new_setter_count'])
        self.assertIn('duplicate',self.call()['error']['message'])

    def test_foreign_cancellation_cannot_stop_active_call(self):
        self.server();cancel=threading.Event()
        self.mcp.active=dict(request_id=7,cancelled=cancel,registration_id=None)
        # EOF independently cancels; inspect only the delivered notification.
        self.mcp.incoming=io.StringIO(json.dumps(dict(jsonrpc='2.0',method='notifications/cancelled',params={'requestId':'7'}))+'\n')
        with patch.object(self.mcp,'stop_active') as stopping:self.mcp._read()
        self.assertEqual(stopping.call_count,1)  # EOF, not the foreign string id

    def test_cancelled_approval_wait_stops_without_waiting_full_deadline(self):
        self.server();event=threading.Event();event.set()
        with self.assertRaisesRegex(ValueError,'request_cancelled'):self.mcp.next_message(1000.,cancelled=event)

    def test_eof_and_bad_input_fail_closed(self):
        for raw in ('','[1,2]\n','{"jsonrpc":"2.0","value":NaN}\n'):
            server=self.server();server.incoming=io.StringIO(raw);server._read();self.assertTrue(server.closed.is_set())
            with self.assertRaises(ValueError):server.next_message()

    def test_rpc_ids_cannot_alias_bools_or_be_unbounded(self):
        for value in (True,None,[],{},-1,2**53,'','a'*129):self.assertFalse(valid_id(value))
        self.assertTrue(valid_id(0));self.assertTrue(valid_id('0'))

    def test_timing_cannot_renew_from_future_or_nonfinite_receive(self):
        for index,received in enumerate((101.,float('nan'),float('inf'),True,-1.)):
            self.server()
            with patch.object(self.entry,'execute',side_effect=AssertionError('dispatch forbidden')):result=self.call(request_id=50+index,received_monotonic=received)
            self.assertFalse(self.metadata(result)['executed']);self.assertFalse(self.entry._live)
        with self.assertRaises(ValueError):proposal(dict(focal_id='part',reference_id='base',limits={'max_duration_s':31.}))


if __name__=='__main__':unittest.main()
