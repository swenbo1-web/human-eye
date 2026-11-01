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


    def episode(self,response):
        from human_eye_plugin.task_episode import validate_episode
        ref=self.metadata(response)['task_episode_ref']
        result=self.mcp.handle(dict(jsonrpc='2.0',id=900,method='resources/read',params={'uri':ref['uri']}))
        value=validate_episode(json.loads(result['result']['contents'][0]['text']))
        self.assertEqual(ref['sha256'],value['sha256'])
        self.assertNotIn('task_episode',value['raw_evidence']['result'])
        return value

    def test_episode_freezes_receive_binding_and_observed_client_response(self):
        self.server()
        with patch.object(self.entry,'execute',return_value=dict(status='review_required',new_setter_count=0)):
            result=self.call(received_monotonic=98.)
        value=self.episode(result);raw=value['raw_evidence']
        self.assertEqual(raw['received_monotonic'],98.)
        self.assertEqual(raw['admission']['original_deadline_monotonic'],128.)
        self.assertEqual(raw['binding']['scope'],raw['admission']['scope'])
        self.assertEqual(raw['approval']['decision'],'accept_true')
        self.assertTrue(raw['approval']['response']['result']['content']['approve'])
        self.assertFalse(value['derived']['human_UI_verified'])
        self.assertFalse(value['derived']['training_positive'])
        self.assertNotIn('raw_evidence',self.metadata(result))
        self.assertLess(len(json.dumps(self.metadata(result)['task_episode_ref']).encode()),650)

    def test_episode_resources_are_read_only_connection_scoped_and_cannot_read_paths(self):
        self.server();self.client_result={'action':'decline'};result=self.call()
        value=self.episode(result)
        listed=self.mcp.handle(dict(jsonrpc='2.0',id=901,method='resources/list'))
        self.assertEqual(len(listed['result']['resources']),1)
        for uri in ('file:///D:/hefe/.codex/config.toml','human-eye-episode://foreign/receipt',None,{}):
            response=self.mcp.handle(dict(jsonrpc='2.0',id=902,method='resources/read',params={'uri':uri}))
            self.assertIn('error',response)
        value['raw_evidence']['result']['status']='mutated client copy'
        self.assertNotEqual(self.episode(result)['raw_evidence']['result']['status'],'mutated client copy')
        self.assertFalse(self.entry.service.state_path.exists())

    def test_episode_decline_cancel_and_rpc_error_do_not_claim_user_intent(self):
        for index,(answer,decision) in enumerate([({'action':'decline'},'decline'),
                ({'action':'cancel'},'cancel'),({'action':'accept','content':{'approve':1}},'invalid_or_false')]):
            self.server();self.client_result=answer;value=self.episode(self.call(request_id=100+index))
            self.assertEqual(value['raw_evidence']['approval']['decision'],decision)
            self.assertFalse(value['derived']['human_UI_verified'])
            self.assertEqual(value['derived']['new_setter_count'],0)
        self.server()
        def rpc_error(value):self.mcp.messages.put((dict(jsonrpc='2.0',id=value['id'],error={'code':-1}),self.now))
        self.mcp.emit=rpc_error;value=self.episode(self.call())
        self.assertEqual(value['raw_evidence']['approval']['decision'],'rpc_error')
        self.assertEqual(value['derived']['outcome'],'not_admitted')

    def test_episode_unknown_outcome_never_claims_false_physical_zero(self):
        self.server()
        with patch.object(self.entry,'execute',side_effect=OSError('outcome lost')):result=self.call()
        value=self.episode(result)
        self.assertTrue(value['raw_evidence']['execution_started'])
        self.assertIsNone(value['derived']['new_setter_count'])
        self.assertEqual(value['derived']['outcome'],'unknown')

    def test_recording_failure_preserves_the_actual_execution_receipt(self):
        self.server()
        with patch.object(self.entry,'execute',return_value=dict(status='completed',new_setter_count=4)), \
                patch('human_eye_plugin.owned_task_mcp.TaskEpisode.finish',side_effect=OSError('archive unavailable')):
            result=self.call()
        value=self.metadata(result)
        self.assertEqual(value['status'],'completed');self.assertEqual(value['new_setter_count'],4)
        self.assertEqual(value['task_episode_unavailable'],'OSError')
        self.assertNotIn('task_episode_ref',value);self.assertEqual(len(self.mcp.episodes),0)

    def test_duplicate_and_capacity_do_not_create_or_evict_recorded_events(self):
        self.server();self.client_result={'action':'decline'}
        first=self.call(request_id=100);self.assertIn('error',self.call(request_id=100))
        for index in range(101,116):self.call(request_id=index)
        self.assertEqual(len(self.mcp.episodes),16)
        response=self.call(request_id=116);self.assertIn('error',response)
        self.assertEqual(len(self.mcp.episodes),16);self.episode(first)



if __name__=='__main__':unittest.main()
