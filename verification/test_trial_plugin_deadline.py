"""Real owned-pipe faults and one immutable shared task deadline.

These stdlib subprocesses are synthetic peers, never model providers. Tests do
not replace the production entry identity checks or connect to Blender9876.
"""
from pathlib import Path
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from verification.model_trial.deadline import EpisodeDeadline, DeadlineExceeded
from verification.model_trial.plugin_client import PrivatePluginClient, UnconfirmedRequestError


MEASUREMENTS=[]
OWNED_PROCESSES=[]


class Fixture:
    port=1
    bound_deadline=None
    def __init__(self):
        self.expired=False
        self.starts=0
    def start(self):
        self.starts+=1
        return self
    def bind_deadline(self,budget):
        if self.bound_deadline is not None and self.bound_deadline is not budget:
            raise RuntimeError('Cannot replace shared fixture deadline')
        if self.bound_deadline is None:
            self.bound_deadline=budget
            budget.add_expiry_callback(lambda:setattr(self,'expired',True))


class Clock:
    def __init__(self): self.value=10.
    def __call__(self): return self.value


class PluginDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)/'plugin'
        self.fixture=Fixture()
        self.client=PrivatePluginClient(self.folder,self.fixture)
        self.budgets=[]
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.client.close()
        if self.client.process is not None:
            self.assertIsNotNone(self.client.process.returncode)
            self.assertEqual(self.client.cleanup_failures,[])
            self.assertFalse(any(t is not None and t.is_alive() for t in (
                self.client._send_thread,self.client._reader_thread)))
            OWNED_PROCESSES.append({'test':self.id(),'pid':self.client.process.pid,
                'exit_code':self.client.process.returncode,'io_workers_stopped':True})
        for budget in self.budgets: budget.close()

    def budget(self,seconds=2.,**kwargs):
        value=EpisodeDeadline(seconds,**kwargs)
        self.budgets.append(value)
        return value

    def peer(self,body):
        """Attach a synthetic process only after a bounded READY handshake."""
        self.folder.mkdir()
        code='import json,sys,time\nprint("READY",flush=True)\n'+body
        process=subprocess.Popen([sys.executable,'-I','-B','-c',code],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.client.process=process
        ready=queue.Queue()
        thread=threading.Thread(target=lambda:ready.put(process.stdout.readline()),daemon=True)
        thread.start()
        try:
            self.assertEqual(ready.get(timeout=3),'READY\n')
        except BaseException:
            process.kill();process.wait(timeout=2)
            raise
        thread.join(timeout=1)
        self.client._start_reader()
        return process

    def assert_stopped(self,process):
        process.wait(timeout=1)
        self.assertIsNotNone(process.returncode)
        for worker in (self.client._send_thread,self.client._reader_thread):
            self.assertFalse(worker is not None and worker.is_alive())
        self.assertEqual(self.client.cleanup_failures,[])
        self.assertTrue(self.client.failed)
        self.assertTrue(self.fixture.expired)
        with self.assertRaises((RuntimeError,DeadlineExceeded)):
            self.client._rpc('cannot_retry',{})
        self.assertEqual(self.client.rows,[])

    def test_binding_is_lazy_shared_and_nonrenewable(self):
        budget=self.budget()
        with patch('subprocess.Popen',side_effect=AssertionError('must not start')):
            self.assertIs(self.client.bind_deadline(budget),self.client)
        self.assertIsNone(self.client.process)
        self.assertFalse(self.folder.exists())
        self.assertIs(self.client.bound_deadline,self.fixture.bound_deadline)
        self.assertTrue(self.client.deadline_enforced)
        self.client.bind_deadline(budget)
        with self.assertRaises(RuntimeError): self.client.bind_deadline(self.budget())

    def test_expired_bind_starts_nothing(self):
        budget=self.budget();budget.expire('test')
        with self.assertRaises(DeadlineExceeded): self.client.bind_deadline(budget)
        self.assertIsNone(self.client.process)
        self.assertFalse(self.folder.exists())
        self.assertFalse(self.client.deadline_enforced)

    def test_budget_close_revokes_admission_and_capability(self):
        budget=self.budget()
        self.client.bind_deadline(budget)
        self.assertTrue(self.client.deadline_enforced)
        budget.close()
        self.assertFalse(self.client.deadline_enforced)
        with self.assertRaises(DeadlineExceeded): self.client.call('human_eye_scene_observe',{})
        self.assertIsNone(self.client.process)
        self.assertEqual(self.fixture.starts,0)

    def test_unbound_and_conflicting_fixture_do_not_claim_deadline(self):
        self.assertFalse(self.client.deadline_enforced)
        first=self.budget()
        self.fixture.bind_deadline(first)
        with self.assertRaises(RuntimeError): self.client.bind_deadline(self.budget())
        self.assertIsNone(self.client.bound_deadline)
        self.assertFalse(self.client.deadline_enforced)
        self.assertIsNone(self.client.process)

    def test_start_checks_expiry_after_process_publication(self):
        # Inject the narrow Popen return race: the timer fired when no process
        # reference was available yet. The newly published child is still killed.
        budget=self.budget(3.)
        self.client.bind_deadline(budget)
        original=subprocess.Popen
        children=[]
        def spawned_then_expired(*args,**kwargs):
            child=original([sys.executable,'-I','-B','-c','import time; time.sleep(30)'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            children.append(child)
            budget.expire('startup_publication_race')
            return child
        with patch('verification.model_trial.plugin_client.subprocess.Popen',side_effect=spawned_then_expired):
            with self.assertRaises((RuntimeError,DeadlineExceeded)): self.client.start()
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].returncode)
        self.assertTrue(self.client.failed)
        self.assertTrue(self.client.closed)
        self.assertEqual(self.client.rows,[])

    def test_lazy_start_synchronizes_native_before_plugin_spawn(self):
        budget=self.budget(3.);self.client.bind_deadline(budget)
        original=subprocess.Popen
        def spawn_after_native(*args,**kwargs):
            self.assertGreater(self.fixture.starts,0)
            return original([sys.executable,'-I','-B','-c','import time; time.sleep(30)'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        from verification.model_trial.plugin_client import BUILD
        with patch('verification.model_trial.plugin_client.subprocess.Popen',side_effect=spawn_after_native), \
             patch.object(self.client,'_rpc',side_effect=[{'_meta':{'human_eye':{
                 'build_id':BUILD,'source_file_count':68,'source_kind':'installed_distribution'}}}, {'tools':[]}]):
            self.assertIs(self.client.start(),self.client)
        self.assertEqual(self.fixture.starts,1)

    def test_close_does_not_block_on_full_stdin_peer(self):
        process=self.peer('time.sleep(30)\n')
        self.client.bind_deadline(self.budget(5.))
        errors=[]
        def request():
            try: self.client._rpc('blocked_during_close',{'padding':'x'*(512*1024)},timeout=4.)
            except BaseException as exc: errors.append(exc)
        caller=threading.Thread(target=request,daemon=True)
        caller.start()
        until=time.monotonic()+1.
        while self.client._send_thread is None and time.monotonic()<until: time.sleep(.005)
        self.assertIsNotNone(self.client._send_thread)
        started=time.monotonic()
        self.client.close()
        caller.join(timeout=1.)
        self.assertLess(time.monotonic()-started,3.5)
        self.assertFalse(caller.is_alive())
        self.assertIsNotNone(process.returncode)
        self.assertTrue(errors)
        closed=json.loads((self.folder/'CLOSED.json').read_text(encoding='utf-8'))
        self.assertTrue(closed['io_workers_stopped'])

    def test_real_pipe_blocked_send_is_killed_and_joined(self):
        process=self.peer('time.sleep(30)\n')
        self.client.bind_deadline(self.budget(2.))
        started=time.monotonic()
        with self.assertRaises(UnconfirmedRequestError):
            self.client._rpc('blocked_pipe',{'padding':'x'*(512*1024)},timeout=.15)
        elapsed=time.monotonic()-started
        self.assertLess(elapsed,1.5)
        self.assert_stopped(process)
        MEASUREMENTS.append({'case':'blocked_pipe','deadline_s':.15,'wall_s':elapsed,
            'exit_code':process.returncode,'io_joined':True,'cross_channel_revoked':True})

    def test_real_no_reply_uses_shared_remaining(self):
        process=self.peer('sys.stdin.readline()\ntime.sleep(30)\n')
        self.client.bind_deadline(self.budget(.18))
        started=time.monotonic()
        with self.assertRaises(UnconfirmedRequestError): self.client._rpc('no_reply',{},timeout=30)
        elapsed=time.monotonic()-started
        self.assertLess(elapsed,1.5)
        self.assert_stopped(process)
        MEASUREMENTS.append({'case':'no_reply','deadline_s':.18,'wall_s':elapsed,
            'exit_code':process.returncode,'io_joined':True,'cross_channel_revoked':True})

    def test_real_late_reply_never_accepted(self):
        process=self.peer('r=json.loads(sys.stdin.readline())\ntime.sleep(.5)\n'
            'print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":{"late":True}}),flush=True)\n')
        self.client.bind_deadline(self.budget(.15))
        with self.assertRaises(UnconfirmedRequestError): self.client._rpc('late',{},timeout=5)
        self.assert_stopped(process)

    def test_real_normal_reply_and_graceful_close(self):
        process=self.peer('for line in sys.stdin:\n r=json.loads(line)\n '
            'print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":{"ok":True}}),flush=True)\n')
        self.client.bind_deadline(self.budget(3.))
        self.assertEqual(self.client._rpc('normal',{},timeout=1),{'ok':True})
        self.assertEqual(len(self.client.rows),1)
        self.client.close()
        self.assertEqual(process.returncode,0)
        closed=json.loads((self.folder/'CLOSED.json').read_text(encoding='utf-8'))
        self.assertTrue(closed['io_workers_stopped'])
        self.assertEqual(closed['cleanup_failures'],[])
        self.assertLess(closed['cleanup_wall_s'],3.5)

    def test_shared_expiry_while_idle_prevents_next_call(self):
        process=self.peer('time.sleep(30)\n')
        budget=self.budget(2.);self.client.bind_deadline(budget)
        budget.expire('owner_revoked')
        process.wait(timeout=1)
        with self.assertRaises((RuntimeError,DeadlineExceeded)): self.client.call('human_eye_scene_observe',{})
        self.assertEqual(self.client.rows,[])
        self.assertTrue(self.fixture.expired)

    def test_late_after_json_parse_does_not_return_success(self):
        process=self.peer('r=json.loads(sys.stdin.readline())\n'
            'print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":42}),flush=True)\n'
            'time.sleep(30)\n')
        clock=Clock();self.client.bind_deadline(self.budget(1.,clock=clock,watchdog=False))
        original=json.loads
        def late_parse(raw,*args,**kwargs):
            value=original(raw,*args,**kwargs)
            clock.value=12.
            return value
        with patch('verification.model_trial.plugin_client.json.loads',side_effect=late_parse):
            with self.assertRaises(UnconfirmedRequestError): self.client._rpc('parse_late',{})
        self.assert_stopped(process)

    def test_segment_request_is_capped_by_shared_remaining(self):
        process=self.peer('time.sleep(30)\n')
        clock=Clock();budget=self.budget(5.,clock=clock,watchdog=False)
        self.client.bind_deadline(budget);clock.value=14.
        seen=[]
        def rpc(method,params,timeout):
            seen.append((params,timeout));return {'ok':True}
        with patch.object(self.client,'_rpc',side_effect=rpc):
            value=self.client.call('human_eye_clearance_segment',{'request':{'max_duration_s':30}})
        self.assertEqual(value,{'ok':True})
        self.assertEqual(seen[0][0]['arguments']['request']['max_duration_s'],1.)
        self.assertEqual(seen[0][1],1.)
        self.assertFalse(self.client.deadline_enforced)  # fake clock has no watchdog

    def test_local_rpc_timeout_revokes_other_registered_owned_resource(self):
        process=self.peer('sys.stdin.readline()\ntime.sleep(30)\n')
        budget=self.budget(5.);self.client.bind_deadline(budget)
        other_stopped=threading.Event();budget.add_expiry_callback(other_stopped.set)
        with self.assertRaises(UnconfirmedRequestError): self.client._rpc('lost_ack',{},timeout=.1)
        self.assertTrue(other_stopped.is_set())
        self.assert_stopped(process)


if __name__=='__main__': unittest.main()
