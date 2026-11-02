"""Cancellation/commit boundary doubles; no Blender I/O or human approval proof."""
import copy,io,json,queue,threading,time,unittest
from unittest.mock import patch

from human_eye_plugin.owned_task_mcp import GOAL_TOOL
from human_eye_plugin.surface_owned_process import OwnedSurfaceProcess
from human_eye_plugin.surface_owned_mcp import SurfaceOwnedMCP,_RequestCancellation
from human_eye_plugin import surface_owned as s
from human_eye_plugin.task_episode import TaskEpisode
from verification import test_owned_task_mcp as Fixture
from verification import test_surface_owned as SurfaceFixture


class _OpenInput:
    """Keep a real reader open after its finite input has been consumed."""
    def __init__(self,lines):
        self.lines=iter(lines);self.waiting=threading.Event();self.release=threading.Event()
    def readline(self,_limit):
        try:return next(self.lines)
        except StopIteration:
            self.waiting.set();self.release.wait(5);return ''


class OwnedCancellationRegressionTests(unittest.TestCase):
    setUp=Fixture.OwnedTaskMCPTests.setUp
    approve=Fixture.OwnedTaskMCPTests.approve
    mock_entry=Fixture.OwnedTaskMCPTests.mock_entry
    state=Fixture.OwnedTaskMCPTests.state
    write=Fixture.OwnedTaskMCPTests.write
    server=Fixture.OwnedTaskMCPTests.server
    call=Fixture.OwnedTaskMCPTests.call
    metadata=Fixture.OwnedTaskMCPTests.metadata

    def queued(self,request_id,cancel_id):
        request=dict(jsonrpc='2.0',id=request_id,method='tools/call',params=dict(name=GOAL_TOOL['name'],
            arguments=dict(focal_id='part',reference_id='base')))
        cancellation=dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId=cancel_id))
        source=_OpenInput([json.dumps(request)+'\n',json.dumps(cancellation)+'\n']);self.mcp.incoming=source
        reader=threading.Thread(target=self.mcp._read,daemon=True);reader.start()
        def finish():source.release.set();reader.join(2);self.assertFalse(reader.is_alive())
        self.addCleanup(finish);self.assertTrue(source.waiting.wait(2));return self.mcp.next_message()

    def test_wire_cancel_while_queued_never_registers_or_requests_approval(self):
        self.server();request,received=self.queued(2,2)
        with patch.object(self.entry,'register',side_effect=AssertionError('cancelled queued registration')) as register:
            result=self.mcp.handle(request,received_monotonic=received)
        register.assert_not_called();self.assertFalse(self.sent)
        value=self.metadata(result);self.assertFalse(value['executed']);self.assertEqual(value['new_setter_count'],0)

    def test_typed_foreign_queue_cancel_does_not_cancel_numeric_request(self):
        self.server();request,received=self.queued(7,'7')
        with patch.object(self.entry,'execute',return_value=dict(status='completed',new_setter_count=0)) as execute:
            result=self.mcp.handle(request,received_monotonic=received)
        execute.assert_called_once();self.assertEqual(self.metadata(result)['status'],'completed');self.assertEqual(len(self.sent),1)

    def test_cancel_between_scope_binding_and_form_publication_emits_no_form(self):
        self.server();original=TaskEpisode.bind
        def bind(episode,*args):
            original(episode,*args);self.mcp.stop_active()
        with patch.object(TaskEpisode,'bind',bind),patch.object(self.entry,'execute') as execute:
            result=self.call()
        execute.assert_not_called();self.assertFalse(self.sent);self.assertFalse(self.metadata(result)['executed'])

    def test_cancel_during_registration_handoff_revokes_without_execute(self):
        self.server();original=self.entry.register
        def register(*args,**kwargs):
            admission=original(*args,**kwargs);self.mcp.stop_active();return admission
        with patch.object(self.entry,'register',register),patch.object(self.entry,'execute') as execute:
            result=self.call()
        execute.assert_not_called();value=self.metadata(result)
        self.assertFalse(value['executed']);self.assertEqual(value['new_setter_count'],0)
        live=next(iter(self.entry._live.values()));self.assertTrue(live['revoked'].is_set())

    def test_cancel_after_execute_handoff_preserves_known_actual_count(self):
        self.server()
        def execute(_key):
            self.mcp.stop_active()
            return dict(status='review_required',executed_this_call=True,new_setter_count=1)
        with patch.object(self.entry,'execute',execute):result=self.call()
        value=self.metadata(result);self.assertTrue(value['executed_this_call']);self.assertEqual(value['new_setter_count'],1)

    def test_cancelled_registration_is_revoked_before_fallible_episode_recording(self):
        self.server();original=self.entry.register
        def register(*args,**kwargs):
            admission=original(*args,**kwargs);self.mcp.stop_active();return admission
        with patch.object(self.entry,'register',register),patch.object(TaskEpisode,'admitted',side_effect=OSError('record unavailable')):
            with patch.object(self.entry,'execute') as execute:result=self.call()
        execute.assert_not_called();self.assertFalse(self.metadata(result)['executed'])
        self.assertTrue(next(iter(self.entry._live.values()))['revoked'].is_set())


class SurfaceHandoffRegressionTests(unittest.TestCase):
    def actor(self,*,after_approval=None):
        actor=OwnedSurfaceProcess.__new__(OwnedSurfaceProcess)
        actor.closed=False;actor.poisoned=False;actor.physical=0;actor._gate=threading.Lock();actor._output=queue.Queue(maxsize=16)
        actor.close=lambda:setattr(actor,'closed',True);sent=[]
        def send(value):
            sent.append(copy.deepcopy(value))
            if value['command']=='goal':
                scope=dict(event_id=value['event_id'],received_ns=value['received_ns'],
                    deadline_ns=value['received_ns']+s.LIMITS['duration_ns'],indices=value['indices'],
                    maximum_setter_attempts=2*len(value['indices']),max_displacement_m=s.LIMITS['displacement_m'],
                    vertex_changes=[dict(vertex=index) for index in value['indices']])
                actor._output.put(dict(kind='approval',id=value['id'],scope=scope,scope_sha256=s.digest(scope)))
            elif value['command']=='approval':
                count=1 if value['approved'] else 0
                if after_approval is not None:after_approval(value)
                actor._output.put(dict(kind='result',id=value['id'],result=dict(status='completed' if count else 'refused_before_dispatch',
                    physical_RNA_attempts=count,worker_physical_RNA_attempts=count,
                    execution_authority=False,reusable_grant=False,original_file_saved=False)))
        actor._send=send;return actor,sent

    def goal(self,actor,approve,cancelled):
        return actor.goal([4],event_id='finite-test',received_ns=time.perf_counter_ns(),approve=approve,cancelled=cancelled)

    def test_cancel_before_initial_handoff_sends_no_worker_command(self):
        actor,sent=self.actor()
        with self.assertRaisesRegex(ValueError,'cancelled_before_dispatch'):self.goal(actor,lambda _:self.fail('no approval'),lambda:True)
        self.assertFalse(sent);self.assertFalse(actor.poisoned)

    def test_cancel_during_approval_callback_sends_only_denial_and_reads_zero(self):
        actor,sent=self.actor();cancelled=threading.Event()
        def approve(_scope):cancelled.set();return True
        result=self.goal(actor,approve,cancelled.is_set)
        self.assertEqual([row['approved'] for row in sent if row['command']=='approval'],[False])
        self.assertEqual(result['physical_RNA_attempts'],0);self.assertFalse(actor.poisoned)

    def test_cancel_during_worker_preparation_never_calls_approval_callback(self):
        actor,sent=self.actor();cancelled=threading.Event();original=actor._send
        def send(value):
            original(value)
            if value['command']=='goal':cancelled.set()
        actor._send=send
        result=self.goal(actor,lambda _:self.fail('cancelled preparation must not ask approval'),cancelled.is_set)
        self.assertEqual(sent[-1]['approved'],False);self.assertEqual(result['physical_RNA_attempts'],0)
        self.assertFalse(actor.poisoned)

    def test_cancelled_approval_wait_exception_denies_and_reads_zero(self):
        actor,sent=self.actor();cancelled=threading.Event()
        def approve(_scope):cancelled.set();raise ValueError('mcp_cancelled')
        result=self.goal(actor,approve,cancelled.is_set)
        self.assertEqual(sent[-1]['approved'],False);self.assertEqual(result['physical_RNA_attempts'],0)
        self.assertFalse(actor.poisoned)

    def test_cancel_after_affirmative_submit_still_consumes_known_count(self):
        cancelled=threading.Event();actor,sent=self.actor(after_approval=lambda _message:cancelled.set())
        result=self.goal(actor,lambda _:True,cancelled.is_set)
        self.assertTrue(sent[-1]['approved']);self.assertEqual(result['physical_RNA_attempts'],1)
        self.assertEqual(actor.physical,1);self.assertFalse(actor.poisoned);self.assertFalse(actor.closed)

    def test_normal_approved_and_denied_handoffs_preserve_counter(self):
        for answer,count in ((True,1),(False,0)):
            with self.subTest(answer=answer):
                actor,_=self.actor();result=self.goal(actor,lambda _:answer,lambda:False)
                self.assertEqual(result['physical_RNA_attempts'],count);self.assertEqual(actor.physical,count)

    def test_cancellation_wins_shared_handoff_lock_and_only_denial_is_sent(self):
        actor,sent=self.actor();server=SurfaceOwnedMCP(actor,io.StringIO(),io.StringIO());token=_RequestCancellation(server)
        submit=token.submit_if_live
        def race(action):
            with server.state_lock:server.cancelled.set()
            return submit(action)
        token.submit_if_live=race
        result=self.goal(actor,lambda _:True,token)
        self.assertEqual(sent[-1]['approved'],False);self.assertEqual(result['physical_RNA_attempts'],0)

    def test_affirmative_submission_holds_lock_until_pipe_handoff_finishes(self):
        actor,_=self.actor();server=SurfaceOwnedMCP(actor,io.StringIO(),io.StringIO());token=_RequestCancellation(server)
        entered=threading.Event();release=threading.Event();cancel_done=threading.Event();observed=[]
        def write():entered.set();release.wait(2)
        def cancel():
            with server.state_lock:server.cancelled.set();cancel_done.set()
        sender=threading.Thread(target=lambda:observed.append(token.submit_if_live(write)),daemon=True)
        receiver=threading.Thread(target=cancel,daemon=True)
        try:
            sender.start();self.assertTrue(entered.wait(2));receiver.start()
            self.assertFalse(cancel_done.wait(.02))
        finally:
            release.set();sender.join(2)
            if receiver.ident is not None:receiver.join(2)
        self.assertFalse(sender.is_alive());self.assertFalse(receiver.is_alive())
        self.assertEqual(observed,[True]);self.assertTrue(cancel_done.is_set())

    def test_mcp_cancellation_after_response_dequeue_cannot_return_true(self):
        actor,server,_sent,_client=SurfaceFixture.SurfaceOwnedTests.server(self);original=server.next_message
        def read(*args,**kwargs):
            response=original(*args,**kwargs);server.cancelled.set();return response
        server.next_message=read
        result=SurfaceFixture.SurfaceOwnedTests.call(self,server)
        self.assertEqual(result['physical_RNA_attempts'],0);self.assertFalse(actor.calls[0]['answer'])

    def test_post_submission_receipt_never_receives_a_fresh_deadline(self):
        received=time.perf_counter_ns();deadline=received+s.LIMITS['duration_ns'];clock=[received+1]
        actor,sent=self.actor(after_approval=lambda _:clock.__setitem__(0,deadline))
        with patch('human_eye_plugin.surface_owned_process.time.perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline_unknown'):
                actor.goal([4],event_id='finite-test',received_ns=received,approve=lambda _:True,cancelled=lambda:False)
        self.assertTrue(sent[-1]['approved']);self.assertTrue(actor.poisoned);self.assertTrue(actor.closed)


if __name__=='__main__':unittest.main()
