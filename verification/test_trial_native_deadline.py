"""Real loopback waits/owned child revocation plus finite gateway clock checks."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, threading, time, unittest
from unittest.mock import patch

from verification.model_trial.deadline import EpisodeDeadline, DeadlineExceeded
from verification.model_trial.native_client import OwnedFixture
from verification.model_trial.native_fixture import OwnedGateway, Refusal


class QuietLoopback:
    def __init__(self, mode='silent'):
        self.mode=mode
        self.server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.server.bind(('127.0.0.1',0)); self.server.listen(3)
        self.server.settimeout(.1); self.port=self.server.getsockname()[1]
        self.stop=threading.Event(); self.requests=[]; self.connections=[]
        self.thread=threading.Thread(target=self.run,daemon=True); self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try: connection,_=self.server.accept()
            except socket.timeout: continue
            except OSError: break
            self.connections.append(connection)
            try:
                connection.settimeout(.5); raw=bytearray()
                while True:
                    block=connection.recv(65536)
                    if not block: break
                    raw.extend(block)
                request=json.loads(raw); self.requests.append(request['type'])
                if request['type']=='owner_begin_episode':
                    reply={'status':'success','result':{
                        'episode_started':True,**request['params']}}
                    connection.sendall(json.dumps(reply).encode()); connection.close(); continue
                if self.mode=='trickle':
                    for byte in b'{"status":"success","result":{}}':
                        if self.stop.wait(.03): break
                        connection.sendall(bytes((byte,)))
                elif self.mode=='success':
                    connection.sendall(b'{"status":"success","result":{"ok":true}}')
                else:
                    self.stop.wait(1)
            except (OSError,ValueError): pass
            finally:
                connection.close()

    def close(self):
        self.stop.set(); self.server.close()
        for connection in self.connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            connection.close()
        self.thread.join(timeout=1)


class NativeDeadlineTests(unittest.TestCase):
    def make_started(self, mode='silent', seconds=.22):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        server=QuietLoopback(mode); self.addCleanup(server.close)
        fixture=OwnedFixture(Path(temp.name)/'owned'); fixture.folder.mkdir()
        child=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(30)'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        fixture.process=child; fixture._started=True; fixture.port=server.port
        self.addCleanup(fixture.close)
        budget=EpisodeDeadline(seconds); self.addCleanup(budget.close)
        fixture.bind_deadline(budget)
        return fixture,server,budget

    def test_binding_is_pure_fixed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=OwnedFixture(Path(temp)/'not-created')
            budget=EpisodeDeadline(2); other=EpisodeDeadline(2)
            self.addCleanup(budget.close); self.addCleanup(other.close)
            self.addCleanup(fixture.close)
            self.assertFalse(fixture.deadline_enforced)
            fixture.bind_deadline(budget); fixture.bind_deadline(budget)
            self.assertIs(fixture.bound_deadline,budget)
            self.assertIs(fixture.deadline_budget,budget)
            self.assertTrue(fixture.deadline_enforced)
            self.assertIsNone(fixture.process); self.assertFalse(fixture.folder.exists())
            with self.assertRaises(ValueError): fixture.bind_deadline(other)
            budget.close()
            self.assertFalse(fixture.deadline_enforced)
            with self.assertRaises(DeadlineExceeded): fixture.start()

    def test_real_silent_receive_is_revoked_and_owned_child_exits(self):
        fixture,server,budget=self.make_started()
        began=time.monotonic()
        with self.assertRaises((TimeoutError,OSError,RuntimeError)):
            fixture.call('native_scene_query',{})
        elapsed=time.monotonic()-began
        self.assertLess(elapsed,1.1)
        self.assertTrue(fixture.uncertain_outcome)
        self.assertIsNotNone(fixture.process.poll())
        self.assertLess(fixture.cleanup_info['cleanup_wall_s'],.8)
        self.assertEqual(server.requests,['owner_begin_episode','native_scene_query'])
        count=len(server.requests)
        with self.assertRaises((TimeoutError,RuntimeError)):
            fixture.call('native_transform',{'object_id':'x'})
        self.assertEqual(len(server.requests),count)

    def test_real_trickle_cannot_renew_absolute_receive_deadline(self):
        fixture,server,budget=self.make_started('trickle',.24)
        began=time.monotonic()
        with self.assertRaises((TimeoutError,OSError,RuntimeError)):
            fixture.call('native_scene_query',{})
        self.assertLess(time.monotonic()-began,1.1)
        self.assertTrue(fixture.uncertain_outcome)
        self.assertIsNotNone(fixture.process.poll())

    def test_success_then_expiry_stops_future_channel(self):
        fixture,server,budget=self.make_started('success',.35)
        result=fixture.call('native_scene_query',{})
        self.assertEqual(result,{'ok':True})
        budget.expire('test_revocation')
        fixture.process.wait(timeout=.8)
        count=len(server.requests)
        with self.assertRaises((TimeoutError,RuntimeError)):
            fixture.call('native_transform',{})
        self.assertEqual(len(server.requests),count)
        self.assertFalse(fixture.deadline_enforced)

    def test_owner_handshake_is_once_and_uses_original_window(self):
        fixture,server,budget=self.make_started('success',1)
        fixture.call('native_scene_query',{}); fixture.begin_episode()
        fixture.call('native_scene_query',{})
        self.assertEqual(server.requests.count('owner_begin_episode'),1)
        self.assertEqual(fixture._episode_ack['started_monotonic'],budget.started)
        self.assertEqual(fixture._episode_ack['deadline_monotonic'],budget.expires_at)

    def test_binding_without_independent_watchdog_is_not_formal_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=OwnedFixture(Path(temp)/'no-watchdog'); self.addCleanup(fixture.close)
            budget=EpisodeDeadline(1,watchdog=False); self.addCleanup(budget.close)
            fixture.bind_deadline(budget)
            self.assertFalse(fixture.deadline_enforced)

    def test_late_success_is_rejected_after_parse(self):
        fixture,server,budget=self.make_started('success',1)
        original=__import__('verification.model_trial.native_client',fromlist=['_loads'])._loads
        calls=[]
        def expire_final(raw):
            value=original(raw); calls.append(value)
            if value.get('result',{}).get('ok'): budget.expire('late_reply')
            return value
        with patch('verification.model_trial.native_client._loads',side_effect=expire_final):
            with self.assertRaises((TimeoutError,RuntimeError)):
                fixture.call('native_scene_query',{})
        self.assertTrue(fixture.uncertain_outcome)

    def test_prepare_subprocess_is_killed_at_shared_deadline(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        fixture=OwnedFixture(Path(temp.name)/'prepare'); self.addCleanup(fixture.close)
        budget=EpisodeDeadline(.18); self.addCleanup(budget.close); fixture.bind_deadline(budget)
        original=subprocess.Popen; children=[]
        def slow_prepare(*args,**kwargs):
            argv=[sys.executable,'-I','-B','-c','import time;time.sleep(30)']
            child=original(argv,**kwargs); children.append(child); return child
        started=time.monotonic()
        with patch('verification.model_trial.native_client.subprocess.Popen',side_effect=slow_prepare):
            with self.assertRaises((TimeoutError,OSError,RuntimeError,subprocess.SubprocessError)):
                fixture.start()
        self.assertLess(time.monotonic()-started,1.2)
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].poll())
        self.assertIsNone(fixture.process)
        self.assertTrue(fixture.uncertain_outcome)

    def test_prepare_timeout_revokes_without_watchdog_callback(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=OwnedFixture(Path(temp)/'prepare-local-timeout')
            budget=EpisodeDeadline(10,watchdog=False)
            self.addCleanup(fixture.close); self.addCleanup(budget.close)
            fixture.bind_deadline(budget)
            callbacks=[]
            budget.add_expiry_callback(lambda:callbacks.append('expired'))
            def timeout():
                raise subprocess.TimeoutExpired('controlled prepare',.001)
            fixture._prepare=timeout
            with self.assertRaises(subprocess.TimeoutExpired):fixture.start()
            self.assertEqual(callbacks,[])
            budget.check()
            self.assertTrue(fixture.uncertain_outcome)
            self.assertTrue(fixture._closed)
            self.assertFalse(fixture.deadline_enforced)
            self.assertIsNone(fixture.process)

    def test_startup_wait_is_killed_at_shared_deadline(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        fixture=OwnedFixture(Path(temp.name)/'startup'); self.addCleanup(fixture.close)
        fixture._prepare=lambda:None
        budget=EpisodeDeadline(.18); self.addCleanup(budget.close); fixture.bind_deadline(budget)
        original=subprocess.Popen; children=[]
        def slow_startup(*args,**kwargs):
            child=original([sys.executable,'-I','-B','-c','import time;time.sleep(30)'],**kwargs)
            children.append(child); return child
        started=time.monotonic()
        with patch('verification.model_trial.native_client.subprocess.Popen',side_effect=slow_startup):
            with self.assertRaises((TimeoutError,OSError,RuntimeError)):
                fixture.start()
        self.assertLess(time.monotonic()-started,1.2)
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].poll())

    def test_connect_receives_remaining_not_fresh_ten_seconds(self):
        fixture,server,budget=self.make_started('success',1)
        fixture.start()
        seen=[]
        def blocked_connect(address,timeout):
            seen.append(timeout)
            raise TimeoutError('controlled connect timeout')
        with patch('verification.model_trial.native_client.socket.create_connection',side_effect=blocked_connect):
            with self.assertRaises(TimeoutError): fixture.call('native_scene_query',{})
        self.assertEqual(len(seen),1)
        self.assertGreater(seen[0],0); self.assertLessEqual(seen[0],1)
        self.assertTrue(fixture.uncertain_outcome)

    def test_socket_send_and_recv_timeouts_take_remaining(self):
        fixture,server,budget=self.make_started('success',1)
        fixture.start(); seen=[]
        class TrackingSocket:
            def settimeout(self,value): seen.append(value)
            def sendall(self,_): pass
            def shutdown(self,_): pass
            def recv(self,_): return b''
            def close(self): pass
        connection=TrackingSocket()
        with patch('verification.model_trial.native_client.socket.create_connection',return_value=connection):
            with self.assertRaises(ValueError): fixture.call('native_scene_query',{})
        self.assertGreaterEqual(len(seen),2)
        self.assertTrue(all(0 < value <= 1 for value in seen))
        self.assertTrue(all(b <= a for a,b in zip(seen,seen[1:])))

    def test_close_during_receive_interrupts_and_rejects_reply(self):
        fixture,server,budget=self.make_started('silent',2)
        errors=[]
        worker=threading.Thread(target=lambda:self._call_catching(fixture,errors))
        worker.start()
        until=time.monotonic()+1
        while server.requests != ['owner_begin_episode','native_scene_query'] and time.monotonic()<until:
            time.sleep(.005)
        fixture.close(); worker.join(timeout=.8)
        self.assertFalse(worker.is_alive()); self.assertEqual(len(errors),1)
        self.assertIsNotNone(fixture.process.poll())

    @staticmethod
    def _call_catching(fixture,errors):
        try: fixture.call('native_scene_query',{})
        except BaseException as exc: errors.append(type(exc).__name__)


class GatewayDeadlineTests(unittest.TestCase):
    def make_gateway(self):
        gateway=OwnedGateway.__new__(OwnedGateway)
        gateway.started=10.; gateway.episode_started=None; gateway.episode_deadline=None
        gateway.bound_episode_window=None; gateway.quarantined=False
        gateway.config={'lifetime_s':360,'readonly':False,'case':'floor'}
        return gateway

    def test_fixed_window_not_renewed(self):
        gateway=self.make_gateway(); params={'started_monotonic':10.,'deadline_monotonic':20.}
        with patch('verification.model_trial.native_fixture.time.monotonic',return_value=11.):
            gateway.begin_episode(params); gateway.begin_episode(params)
            self.assertEqual((gateway.episode_started,gateway.episode_deadline),(10.,20.))
            with self.assertRaises(Refusal):
                gateway.begin_episode({'started_monotonic':11.,'deadline_monotonic':21.})
        with patch('verification.model_trial.native_fixture.time.monotonic',return_value=20.):
            with self.assertRaises(Refusal) as context: gateway._write_permission()
            self.assertEqual(context.exception.code,'episode_expired')

    def test_legacy_window_can_only_tighten(self):
        gateway=self.make_gateway()
        with patch('verification.model_trial.native_fixture.time.monotonic',return_value=10.):
            gateway.begin_episode({})
        self.assertEqual(gateway.episode_deadline,190.)
        with patch('verification.model_trial.native_fixture.time.monotonic',return_value=20.):
            gateway.begin_episode({'started_monotonic':20.,'deadline_monotonic':200.})
        self.assertEqual(gateway.episode_deadline,190.)

    def test_invalid_and_expired_windows_never_begin(self):
        for start,end in ((0,181),(12,20),(10,11),(10,float('inf')),(True,12),(10,10)):
            gateway=self.make_gateway()
            with self.subTest(start=start,end=end), \
                patch('verification.model_trial.native_fixture.time.monotonic',return_value=11.), \
                self.assertRaises(Refusal):
                gateway.begin_episode({'started_monotonic':start,'deadline_monotonic':end})
            self.assertIsNone(gateway.episode_deadline)

    def test_dispatch_refuses_read_and_plugin_after_expiry(self):
        gateway=self.make_gateway(); gateway.episode_started=10.; gateway.episode_deadline=11.
        gateway._verify_source=lambda:None
        for request in ({'type':'execute_code'}, {'type':'native_scene_query'}):
            with patch('verification.model_trial.native_fixture.time.monotonic',return_value=11.), \
                 self.assertRaises(Refusal) as context:
                gateway.dispatch(request)
            self.assertEqual(context.exception.code,'episode_expired')


class StartupPublicationTests(unittest.TestCase):
    def gateway(self,folder):
        gateway=OwnedGateway.__new__(OwnedGateway)
        gateway.folder=folder
        return gateway

    def test_final_name_absent_until_complete_pending_is_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); gateway=self.gateway(folder)
            value={'pid':123,'port':12345,'label':'测试'}
            original=os.rename; original_dump=json.dump; observations=[]; writers=[]
            def dump(value,stream,**kwargs):
                writers.append(stream)
                return original_dump(value,stream,**kwargs)
            def inspect(source,destination):
                self.assertFalse(destination.exists())
                self.assertEqual(source.parent,destination.parent)
                self.assertEqual(json.loads(source.read_text(encoding='utf-8')),value)
                self.assertEqual(len(writers),1)
                self.assertTrue(writers[0].closed)
                observations.append(source)
                original(source,destination)
            with patch('verification.model_trial.native_fixture.os.rename',side_effect=inspect), \
                 patch('verification.model_trial.native_fixture.json.dump',side_effect=dump):
                gateway.publish_startup(value)
            self.assertEqual(len(observations),1)
            self.assertEqual(json.loads((folder/'startup.json').read_text(encoding='utf-8')),value)
            self.assertFalse(list(folder.glob('*.pending')))

    def test_existing_publication_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); gateway=self.gateway(folder)
            original=b'{"original":true}\n'
            (folder/'startup.json').write_bytes(original)
            with self.assertRaises(FileExistsError): gateway.publish_startup({'changed':True})
            self.assertEqual((folder/'startup.json').read_bytes(),original)
            self.assertFalse(list(folder.glob('*.pending')))

    @unittest.skipUnless(os.name=='nt','Windows no-replace rename contract')
    def test_destination_created_at_rename_boundary_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); gateway=self.gateway(folder); original=os.rename
            def competitor(source,destination):
                destination.write_bytes(b'competing publication')
                original(source,destination)
            with patch('verification.model_trial.native_fixture.os.rename',side_effect=competitor):
                with self.assertRaises(FileExistsError): gateway.publish_startup({'changed':True})
            self.assertEqual((folder/'startup.json').read_bytes(),b'competing publication')
            self.assertFalse(list(folder.glob('*.pending')))

    def test_serialization_failure_does_not_publish_or_leave_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); gateway=self.gateway(folder)
            with self.assertRaises(ValueError): gateway.publish_startup({'invalid':float('nan')})
            self.assertFalse((folder/'startup.json').exists())
            self.assertFalse(list(folder.glob('*.pending')))

    def test_foreign_pending_collision_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); gateway=self.gateway(folder)
            pending=folder/'.startup.fixed.pending'; pending.write_bytes(b'other owner')
            with patch('verification.model_trial.native_fixture.secrets.token_hex',return_value='fixed'):
                with self.assertRaises(FileExistsError): gateway.publish_startup({'changed':True})
            self.assertEqual(pending.read_bytes(),b'other owner')
            self.assertFalse((folder/'startup.json').exists())


if __name__=='__main__': unittest.main()
