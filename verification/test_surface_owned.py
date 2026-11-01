"""Finite owned surface protocol doubles; never actual human approval proof."""
import copy,io,json,time,unittest
from human_eye_plugin.surface_owned_mcp import SurfaceOwnedMCP,GOAL,INSPECT
from human_eye_plugin import surface_owned as s


class Actor:
    def __init__(self):self.calls=[];self.poisoned=False;self.closed=False
    def close(self):self.closed=True
    def inspect(self):return dict(physical_RNA_attempts=0,execution_authority=False)
    def goal(self,indices,*,event_id,received_ns,approve,cancelled):
        scope=dict(indices=indices,received_ns=received_ns,deadline_ns=received_ns+s.LIMITS['duration_ns'],
            event_id=event_id,vertex_changes=[dict(vertex=i,before_local=[0,0,-.0005],target_local=[0,0,0]) for i in indices])
        answer=approve(scope);self.calls.append(dict(answer=answer,scope=scope))
        return dict(physical_RNA_attempts=len(indices) if answer else 0,execution_authority=False,reusable_grant=False)


class SurfaceOwnedTests(unittest.TestCase):
    def server(self,caps=None,protocol='2025-06-18'):
        actor=Actor();server=SurfaceOwnedMCP(actor,io.StringIO(),io.StringIO());sent=[]
        server.handle(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion=protocol,
            capabilities={'elicitation':{}} if caps is None else caps)),time.perf_counter_ns())
        answer=dict(action='accept',content=dict(approve=True))
        def emit(value):
            sent.append(copy.deepcopy(value))
            server.messages.put((dict(jsonrpc='2.0',id=value['id'],result=copy.deepcopy(answer)),time.perf_counter_ns()))
        server.emit=emit;return actor,server,sent,answer

    def call(self,server,args=None,key=2,name=GOAL):
        value=server.handle(dict(jsonrpc='2.0',id=key,method='tools/call',params=dict(name=name,
            arguments=dict(indices=[4]) if args is None else args)),time.perf_counter_ns())
        return json.loads(value['result']['content'][0]['text'])

    def test_strict_indices_and_no_json_duplicates_or_nonfinite(self):
        for bad in ([True],[1,1],[],list(range(9)),[128],[-1],['1']):
            with self.assertRaises(ValueError):s.indices(bad)
        for blob in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'):
            with self.assertRaises(ValueError):s.decode(blob)

    def test_model_cannot_supply_approval_path_reference_or_time(self):
        for field in ('approved','scope_sha256','received_ns','duration_ns','reference','scene_file','config','journal_root'):
            actor,server,_,_=self.server();result=self.call(server,dict(indices=[4],**{field:True}))
            self.assertEqual(result['physical_count'],0);self.assertFalse(actor.calls)

    def test_capability_must_be_modern_form(self):
        for protocol,caps in [('2025-03-26',{'elicitation':{}}),('2025-06-18',{}),('2025-11-25',{'elicitation':{'url':{}}})]:
            actor,server,sent,_=self.server(caps,protocol);self.call(server)
            self.assertFalse(sent);self.assertFalse(actor.calls)

    def test_strict_approval_and_concrete_scope(self):
        for answer in (True,False,1,'true',None):
            actor,server,sent,client=self.server();client['content']['approve']=answer
            result=self.call(server);self.assertEqual(result['physical_RNA_attempts'],1 if answer is True else 0)
            message=sent[0]['params']['message'];self.assertIn('before_local',message);self.assertIn('target_local',message)
            self.assertIn('input_file_will_not_be_saved',message)

    def test_decline_cancel_error_and_wrong_id(self):
        for action in ('decline','cancel'):
            actor,server,_,client=self.server();client['action']=action
            self.assertEqual(self.call(server)['physical_RNA_attempts'],0)
        actor,server,_,_=self.server()
        server.emit=lambda v:server.messages.put((dict(jsonrpc='2.0',id='wrong',result={'action':'accept','content':{'approve':True}}),time.perf_counter_ns()))
        self.assertEqual(self.call(server)['physical_RNA_attempts'],0)

    def test_duplicate_goal_only_receipt_and_changed_id_arguments_refused(self):
        actor,server,_,_=self.server();self.call(server);reply=self.call(server)
        self.assertEqual(reply['status'],'receipt');self.assertEqual(len(actor.calls),1);self.assertFalse(reply['retried'])
        result=server.handle(dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name=GOAL,arguments=dict(indices=[3]))),time.perf_counter_ns())
        self.assertIn('error',result);self.assertEqual(len(actor.calls),1)

    def test_inspect_arguments_and_lifetime_budget(self):
        actor,server,sent,_=self.server();self.call(server,{},name=INSPECT)
        self.assertFalse(actor.calls);self.assertFalse(sent)
        self.call(server,{'approved':True},key=3,name=INSPECT)
        for key in range(4,18):self.call(server,{},key=key,name=INSPECT)
        result=server.handle(dict(jsonrpc='2.0',id=100,method='tools/call',params=dict(name=INSPECT,arguments={})),time.perf_counter_ns())
        self.assertIn('budget exhausted',result['error']['message'])

    def test_actor_unknown_result_is_never_auto_retried(self):
        actor,server,_,_=self.server()
        def fail(*a,**kw):actor.poisoned=True;raise OSError('lost child response')
        actor.goal=fail;result=self.call(server);self.assertIsNone(result['physical_count']);self.assertEqual(result['status'],'unknown')
        self.assertEqual(self.call(server)['status'],'receipt')

    def test_receive_time_passed_unchanged(self):
        actor,server,_,_=self.server();received=time.perf_counter_ns()-1000000
        server.handle(dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name=GOAL,arguments=dict(indices=[4]))),received)
        self.assertEqual(actor.calls[0]['scope']['received_ns'],received)

    def test_cancellation_received_while_request_waits_prevents_admission(self):
        actor,server,sent,_=self.server();server.cancelled_ids.add(s.digest(dict(id=2)))
        result=self.call(server);self.assertEqual(result['physical_count'],0)
        self.assertFalse(actor.calls);self.assertFalse(sent)

    def test_invalid_postwrite_counter_is_unknown_never_zero_refusal(self):
        from human_eye_plugin.surface_owned_process import OwnedSurfaceProcess
        actor=OwnedSurfaceProcess.__new__(OwnedSurfaceProcess);actor.physical=0;actor.poisoned=False;actor.closed=False
        actor._call=lambda *a,**kw:dict(physical_RNA_attempts=999)
        actor.close=lambda:setattr(actor,'closed',True)
        with self.assertRaises(ValueError):actor.goal([4],event_id='test',received_ns=time.perf_counter_ns(),approve=lambda _:True)
        self.assertTrue(actor.poisoned);self.assertTrue(actor.closed)


if __name__=='__main__':unittest.main()
