"""Deterministic READY publication/readers; no Blender, sleep races or models.

Events stop a producer immediately before its single publication link. Mock
Popen exercises the real NativeSession.start reader/cleanup, not a substitute
startup algorithm. All files are fresh authored TemporaryDirectory fixtures.
"""
from __future__ import annotations
import copy,json,os,threading,time,types,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from verification import visual004_native as n
from verification import visual004_session as b


class FakeProcess:
    def __init__(self,pid=4242):self.pid=pid;self.returncode=None;self.kills=0;self.waits=[];self.polls=0
    def poll(self):self.polls+=1;return self.returncode
    def kill(self):self.kills+=1;self.returncode=-9
    def wait(self,timeout=None):self.waits.append(timeout);return self.returncode


class WrappedWriter:
    def __init__(self,stream,write):self.stream=stream;self.write_function=write
    def __enter__(self):return self
    def __exit__(self,*exc):self.stream.close()
    def __getattr__(self,name):return getattr(self.stream,name)
    def write(self,raw):return self.write_function(self.stream,raw)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.deadline=time.perf_counter_ns()+30_000_000_000
    def record(self,name):
        if name=='READY.json':return dict(host='127.0.0.1',port=12345,pid=4242,deadline_ns=self.deadline,
            helper_sha256='a'*64,initial_fingerprint='b'*64)
        return dict(schema='visual004-owner-broker-ready-v1',pid=3131,worker_pid=4242,host='127.0.0.1',port=12346,
            condition='N',started_ns=100,original_deadline_ns=self.deadline,asset_sha256='c'*64,
            helper_sha256='d'*64,neutral_helper_sha256='a'*64)
    def target(self,name='READY.json'):
        parent=self.root/name.replace('.json','');parent.mkdir();return parent/name
    def assert_no_own_stage(self,target,*,preserved=()):
        self.assertEqual(set(path.name for path in target.parent.glob('*.ready-stage-*')),set(preserved))
    def test_only_two_ready_target_names_are_allowed(self):
        for name in ('SESSION.json','CONFIG.json','WORKER_CLOSED.json','READY.json.next'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'ready_filename'):
                n.publish_ready(self.root/name,{},deadline_ns=self.deadline)
        self.assertEqual(list(self.root.iterdir()),[])
    def test_each_ready_target_is_absent_until_complete_stage_is_linked(self):
        for name in ('READY.json','BROKER_READY.json'):
            with self.subTest(name=name):
                target=self.target(name);value=self.record(name);entered=threading.Event();release=threading.Event();errors=[]
                real_link=os.link
                def link(source,destination):
                    self.assertEqual(Path(source).read_bytes(),n.encoded(value));self.assertEqual(Path(destination),target)
                    entered.set()
                    if not release.wait(3):raise RuntimeError('test publication release not signaled')
                    return real_link(source,destination)
                def publish():
                    try:n.publish_ready(target,value,deadline_ns=self.deadline)
                    except BaseException as exc:errors.append(exc)
                with patch.object(n.os,'link',side_effect=link):
                    producer=threading.Thread(target=publish);producer.start()
                    try:
                        self.assertTrue(entered.wait(3),'producer did not reach controlled publication')
                        self.assertFalse(target.exists())
                        with self.assertRaises(FileNotFoundError):target.read_bytes()
                    finally:release.set();producer.join(3)
                self.assertFalse(producer.is_alive());self.assertEqual(errors,[])
                self.assertEqual(target.read_bytes(),n.encoded(value));self.assertEqual(n.load(target),value)
                self.assert_no_own_stage(target)
    def test_two_publishers_preserve_first_creation_without_replace_or_retry(self):
        target=self.target();entered=[threading.Event(),threading.Event()];release=[threading.Event(),threading.Event()]
        done=[threading.Event(),threading.Event()];errors=[None,None];records=[dict(self.record('READY.json'),producer=i) for i in (0,1)]
        real_link=os.link
        def link(source,destination):
            index=int(threading.current_thread().name[-1]);entered[index].set()
            if not release[index].wait(3):raise RuntimeError('test release missing')
            return real_link(source,destination)
        def publish(index):
            try:n.publish_ready(target,records[index],deadline_ns=self.deadline)
            except BaseException as exc:errors[index]=exc
            finally:done[index].set()
        with patch.object(n.os,'link',side_effect=link):
            threads=[threading.Thread(name='publisher'+str(i),target=publish,args=(i,)) for i in (0,1)]
            for thread in threads:thread.start()
            try:
                self.assertTrue(all(event.wait(3) for event in entered));self.assertFalse(target.exists())
                release[0].set();self.assertTrue(done[0].wait(3));self.assertEqual(n.load(target),records[0])
                release[1].set();self.assertTrue(done[1].wait(3))
            finally:
                for event in release:event.set()
                for thread in threads:thread.join(3)
        self.assertIsNone(errors[0]);self.assertIsInstance(errors[1],FileExistsError)
        self.assertEqual(n.load(target),records[0]);self.assert_no_own_stage(target)
    def test_partial_write_failure_cleans_only_its_staging_file(self):
        target=self.target();foreign=target.with_name(target.name+'.ready-stage-foreign');foreign.write_bytes(b'other attempt')
        original=Path.open
        def open_path(path,mode='r',*args,**kwargs):
            stream=original(path,mode,*args,**kwargs)
            if mode=='xb' and '.ready-stage-' in path.name:
                def fail(stream,raw):stream.write(raw[:7]);stream.flush();raise OSError('authored stage write failure')
                return WrappedWriter(stream,fail)
            return stream
        with patch.object(Path,'open',new=open_path):
            with self.assertRaisesRegex(OSError,'authored stage write failure'):
                n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertFalse(target.exists());self.assertEqual(foreign.read_bytes(),b'other attempt')
        self.assert_no_own_stage(target,preserved=(foreign.name,))
    def test_short_writes_are_completed_but_zero_write_is_not_success(self):
        original=Path.open;target=self.target();writes=[]
        def open_path(path,mode='r',*args,**kwargs):
            stream=original(path,mode,*args,**kwargs)
            if mode=='xb' and '.ready-stage-' in path.name:
                def short(stream,raw):writes.append(len(raw));return stream.write(raw[:5])
                return WrappedWriter(stream,short)
            return stream
        with patch.object(Path,'open',new=open_path):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertGreater(len(writes),1);self.assertEqual(n.load(target),self.record(target.name))
        other=self.root/'zero';other.mkdir();zero=other/'READY.json'
        def zero_open(path,mode='r',*args,**kwargs):
            stream=original(path,mode,*args,**kwargs)
            return WrappedWriter(stream,lambda stream,raw:0) if mode=='xb' and '.ready-stage-' in path.name else stream
        with patch.object(Path,'open',new=zero_open),self.assertRaisesRegex(ValueError,'ready_staging_write'):
            n.publish_ready(zero,self.record(zero.name),deadline_ns=self.deadline)
        self.assertFalse(zero.exists());self.assert_no_own_stage(zero)
    def test_fsync_failure_never_exposes_target(self):
        target=self.target()
        with patch.object(n.os,'fsync',side_effect=OSError('authored fsync failure')):
            with self.assertRaisesRegex(OSError,'authored fsync failure'):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertFalse(target.exists());self.assert_no_own_stage(target)
    def test_staged_readback_corruption_never_links_target(self):
        target=self.target();original=Path.read_bytes
        def read(path):return b'{"partial":' if '.ready-stage-' in path.name else original(path)
        with patch.object(Path,'read_bytes',new=read),patch.object(n.os,'link') as link:
            with self.assertRaisesRegex(ValueError,'ready_staging_readback'):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
            link.assert_not_called()
        self.assertFalse(target.exists());self.assert_no_own_stage(target)
    def test_link_failure_is_terminal_and_preserves_other_stages(self):
        target=self.target();foreign=target.with_name(target.name+'.ready-stage-foreign');foreign.write_bytes(b'foreign')
        with patch.object(n.os,'link',side_effect=OSError('authored link unavailable')) as link:
            with self.assertRaisesRegex(OSError,'authored link unavailable'):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertEqual(link.call_count,1);self.assertFalse(target.exists());self.assert_no_own_stage(target,preserved=(foreign.name,))
    def test_corrupt_existing_ready_is_not_repaired_or_replaced(self):
        target=self.target();original=b'{"pid":';target.write_bytes(original)
        with self.assertRaises(FileExistsError):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertEqual(target.read_bytes(),original);self.assert_no_own_stage(target)
    def test_staging_collision_does_not_delete_an_unowned_file(self):
        target=self.target();collision=target.with_name(target.name+'.ready-stage-fixed');collision.write_bytes(b'owned elsewhere')
        with patch.object(n.uuid,'uuid4',return_value=types.SimpleNamespace(hex='fixed')):
            with self.assertRaises(FileExistsError):n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertFalse(target.exists());self.assertEqual(collision.read_bytes(),b'owned elsewhere')
    def test_expired_before_staging_publishes_nothing(self):
        target=self.target()
        with self.assertRaisesRegex(ValueError,'original_deadline'):
            n.publish_ready(target,self.record(target.name),deadline_ns=time.perf_counter_ns()-1)
        self.assertEqual(list(target.parent.iterdir()),[])
    def test_expiry_after_link_is_not_success_but_retains_complete_published_record(self):
        target=self.target();clock=[100];deadline=200;value=self.record(target.name);real_link=os.link
        def link(source,destination):real_link(source,destination);clock[0]=deadline
        with patch.object(n.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(n.os,'link',side_effect=link):
            with self.assertRaisesRegex(ValueError,'original_deadline'):n.publish_ready(target,value,deadline_ns=deadline)
        self.assertEqual(target.read_bytes(),n.encoded(value));self.assert_no_own_stage(target)
    def test_final_publication_readback_error_does_not_report_success(self):
        target=self.target();original=Path.read_bytes
        def read(path):return b'{}\n' if path==target else original(path)
        with patch.object(Path,'read_bytes',new=read),self.assertRaisesRegex(ValueError,'ready_persist_readback'):
            n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertEqual(target.read_bytes(),n.encoded(self.record(target.name)));self.assert_no_own_stage(target)
    def test_expiry_during_staging_cleanup_is_not_a_successful_return(self):
        target=self.target();clock=[100];deadline=200;original=Path.unlink
        def unlink(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if '.ready-stage-' in path.name:clock[0]=deadline
            return result
        with patch.object(n.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(Path,'unlink',new=unlink):
            with self.assertRaisesRegex(ValueError,'original_deadline'):
                n.publish_ready(target,self.record(target.name),deadline_ns=deadline)
        self.assertEqual(n.load(target),self.record(target.name));self.assert_no_own_stage(target)
    def test_cleanup_failure_preserves_original_link_failure_and_foreign_stage(self):
        target=self.target();foreign=target.with_name(target.name+'.ready-stage-foreign');foreign.write_bytes(b'foreign')
        original=Path.unlink
        def unlink(path,*args,**kwargs):
            if '.ready-stage-' in path.name:raise PermissionError('authored cleanup failure')
            return original(path,*args,**kwargs)
        with patch.object(n.os,'link',side_effect=OSError('authored original link failure')),patch.object(Path,'unlink',new=unlink):
            with self.assertRaisesRegex(OSError,'authored original link failure') as caught:
                n.publish_ready(target,self.record(target.name),deadline_ns=self.deadline)
        self.assertTrue(any('cleanup' in note for note in getattr(caught.exception,'__notes__',[])))
        self.assertFalse(target.exists());self.assertEqual(foreign.read_bytes(),b'foreign')
        self.assertEqual(len(list(target.parent.glob('*.ready-stage-*'))),2)


class StartupReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.asset=self.root/'source.blend';self.asset.write_bytes(b'authored fixture, no actual Blender')
        self.binary=self.root/'blender-stub';self.binary.write_bytes(b'authored executable placeholder')
        self.deadline=time.perf_counter_ns()+30_000_000_000;self.processes=[]
    def record(self,config,process):return dict(host='127.0.0.1',port=23456,pid=process.pid,deadline_ns=config['deadline_ns'],
        helper_sha256=config['helper_sha256'],initial_fingerprint='a'*64)
    def start(self,workspace):return n.NativeSession.start(blender=self.binary,asset=self.asset,workspace=workspace,deadline_ns=self.deadline)
    def factory(self,workspace,mutate=lambda value,config:None,*,partial=False):
        def launch(*args,**kwargs):
            process=FakeProcess();self.processes.append(process);config=n.load(workspace/'CONFIG.json');value=self.record(config,process)
            mutate(value,config)
            if partial:(workspace/'READY.json').write_bytes(b'{"pid":')
            else:n.publish_ready(workspace/'READY.json',value,deadline_ns=self.deadline)
            return process
        return launch
    def assert_killed_and_waited(self,process):self.assertEqual(process.kills,1);self.assertEqual(process.waits,[5])
    def test_real_start_waits_for_atomic_producer_and_succeeds_once_released(self):
        workspace=self.root/'atomic';entered=threading.Event();release=threading.Event();done=threading.Event();errors=[];threads=[]
        real_link=os.link;poll_count=[0]
        def link(source,destination):
            entered.set()
            if not release.wait(3):raise RuntimeError('controlled producer was never released')
            return real_link(source,destination)
        def launch(*args,**kwargs):
            process=FakeProcess();self.processes.append(process);config=n.load(workspace/'CONFIG.json');value=self.record(config,process)
            def publish():
                try:n.publish_ready(workspace/'READY.json',value,deadline_ns=self.deadline)
                except BaseException as exc:errors.append(exc)
                finally:done.set()
            producer=threading.Thread(target=publish);threads.append(producer);producer.start();return process
        def rendezvous(seconds):
            poll_count[0]+=1;self.assertTrue(entered.wait(3));self.assertFalse((workspace/'READY.json').exists())
            self.assertTrue(any(workspace.glob('READY.json.ready-stage-*')))
            release.set();self.assertTrue(done.wait(3))
        with patch.object(n.subprocess,'Popen',side_effect=launch),patch.object(n.os,'link',side_effect=link),patch.object(n.time,'sleep',side_effect=rendezvous):
            try:session=self.start(workspace)
            finally:
                release.set()
                for producer in threads:producer.join(3)
        self.assertEqual(errors,[]);self.assertEqual(poll_count[0],1)
        self.assertEqual(session.ready['pid'],session.process.pid);self.assertEqual(session.config['deadline_ns'],self.deadline)
        self.assertEqual(session.process.kills,0);self.assertEqual(session.process.waits,[])
        self.assertTrue((workspace/'SESSION.json').exists());self.assertFalse((workspace/'START_FAILURE.json').exists())
        self.assertEqual(list(workspace.glob('*.ready-stage-*')),[])
    def test_wrong_ready_pid_helper_or_deadline_is_rejected_and_owner_reaped(self):
        for index,(field,value,reason) in enumerate([('pid',4243,'ready_binding'),('pid',True,'ready_binding'),
            ('deadline_ns',0,'ready_binding'),('deadline_ns',True,'ready_binding'),('helper_sha256','b'*64,'ready_helper_binding')]):
            with self.subTest(field=field,value=value):
                workspace=self.root/('bad'+str(index))
                with patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace,lambda ready,config:ready.update({field:value}))):
                    with self.assertRaisesRegex(ValueError,reason):self.start(workspace)
                self.assert_killed_and_waited(self.processes[-1]);self.assertFalse((workspace/'SESSION.json').exists())
                self.assertTrue((workspace/'START_FAILURE.json').exists())
    def test_bad_ready_types_host_port_or_fields_do_not_reach_session_success(self):
        changes=[dict(host='8.8.8.8'),dict(port=True),dict(port=0),dict(port=65536),dict(initial_fingerprint='bad'),dict(unexpected=True)]
        for index,change in enumerate(changes):
            workspace=self.root/('shape'+str(index))
            with self.subTest(change=change),patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace,lambda ready,config:ready.update(change))):
                with self.assertRaisesRegex(ValueError,'ready_'):self.start(workspace)
            self.assert_killed_and_waited(self.processes[-1]);self.assertFalse((workspace/'SESSION.json').exists())
    def test_source_or_copy_changed_during_startup_rejects_ready_and_reaps_owner(self):
        for index,target in enumerate(('asset','asset_copy','blender')):
            self.asset.write_bytes(b'authored fixture, no actual Blender');self.binary.write_bytes(b'authored executable placeholder')
            workspace=self.root/('source'+str(index))
            def mutate(ready,config):Path(config[target]).write_bytes(b'changed during worker startup')
            with self.subTest(target=target),patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace,mutate)):
                with self.assertRaisesRegex(ValueError,'ready_source_binding'):self.start(workspace)
            self.assert_killed_and_waited(self.processes[-1]);self.assertFalse((workspace/'SESSION.json').exists())
    def test_existing_partial_ready_is_terminal_not_retried_until_json_becomes_valid(self):
        workspace=self.root/'partial'
        with patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace,partial=True)):
            with self.assertRaises(json.JSONDecodeError):self.start(workspace)
        self.assert_killed_and_waited(self.processes[-1]);self.assertEqual((workspace/'READY.json').read_bytes(),b'{"pid":')
        self.assertFalse((workspace/'SESSION.json').exists())
    def test_expiry_after_ready_read_never_returns_a_session(self):
        workspace=self.root/'late-ready';clock=[self.deadline-1_000_000_000];original=n.load
        def load(path):
            value=original(path)
            if Path(path).name=='READY.json':clock[0]=self.deadline
            return value
        with patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace)),patch.object(n,'load',side_effect=load),patch.object(n.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):self.start(workspace)
        self.assert_killed_and_waited(self.processes[-1]);self.assertFalse((workspace/'SESSION.json').exists())
    def test_expiry_after_SESSION_save_never_returns_a_valid_start(self):
        workspace=self.root/'late-session';clock=[self.deadline-1_000_000_000];original=n.save
        def save(path,value,**kwargs):
            result=original(path,value,**kwargs)
            if Path(path).name=='SESSION.json':clock[0]=self.deadline
            return result
        with patch.object(n.subprocess,'Popen',side_effect=self.factory(workspace)),patch.object(n,'save',side_effect=save),patch.object(n.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):self.start(workspace)
        self.assert_killed_and_waited(self.processes[-1]);self.assertTrue((workspace/'SESSION.json').exists())
        self.assertTrue((workspace/'START_FAILURE.json').exists())


class BrokerReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        asset=self.root/'source.blend';asset.write_bytes(b'authored source')
        copied=self.root/'input.blend';copied.write_bytes(asset.read_bytes());binary=self.root/'binary';binary.write_bytes(b'authored binary')
        now=time.perf_counter_ns();self.deadline=now+30_000_000_000
        self.session=dict(schema='visual004-native-session-v1',pid=4242,condition='N',deadline_ns=self.deadline,asset=str(asset),asset_copy=str(copied),
            asset_sha256=n.sha(asset),helper_sha256=n.sha(n.__file__),blender=str(binary),blender_sha256=n.sha(binary),protected_public_images=[])
        self.ready=dict(schema='visual004-owner-broker-ready-v1',pid=3131,worker_pid=4242,host='127.0.0.1',port=23457,
            condition='N',started_ns=now,original_deadline_ns=self.deadline,asset_sha256=self.session['asset_sha256'],
            helper_sha256=n.sha(b.__file__),neutral_helper_sha256=self.session['helper_sha256'])
        self.state=dict(schema='visual004-owner-broker-v1',owner_pid=3131,condition='N',started_ns=now,original_deadline_ns=self.deadline)
        n.save(self.root/'SESSION.json',self.session);n.save(self.root/'BROKER_STATE.json',self.state);n.save(self.root/'BROKER_READY.json',self.ready)
        # A negative must reach its intended guard, not pass because an unrelated
        # fixture field was missing. The unchanged complete control is valid.
        self.assertEqual(b.load_broker_ready(self.root),self.ready)
    def test_wrong_broker_pid_worker_source_helper_and_deadline_reject_before_socket(self):
        changes=[(dict(pid=3132),'broker_owner_binding'),(dict(worker_pid=4243),'broker_ready_identity'),
            (dict(asset_sha256='c'*64),'broker_ready_source_binding'),(dict(neutral_helper_sha256='d'*64),'broker_ready_source_binding'),
            (dict(helper_sha256='e'*64),'broker_helper_changed'),(dict(original_deadline_ns=self.deadline+1),'broker_ready_deadline'),
            (dict(host='remote.example'),'broker_ready_identity'),(dict(port=True),'broker_ready_identity')]
        for change,reason in changes:
            value=dict(self.ready,**change);n.save(self.root/'BROKER_READY.json',value,replace=True)
            with self.subTest(change=change),patch.object(b.socket,'create_connection') as connection:
                with self.assertRaisesRegex(ValueError,reason):b.client(self.root,dict(request_id='invalid',operation='status',args={}))
                connection.assert_not_called()
    def test_expired_trusted_session_cannot_be_extended_by_ready_contents(self):
        config=dict(self.session,deadline_ns=time.perf_counter_ns()-1);n.save(self.root/'SESSION.json',config,replace=True)
        with patch.object(b.socket,'create_connection') as connection:
            with self.assertRaisesRegex(ValueError,'original_deadline'):b.client(self.root,dict(request_id='expired',operation='status',args={}))
            connection.assert_not_called()
    def test_changed_source_for_normal_observation_is_rejected_before_socket(self):
        Path(self.session['asset']).write_bytes(b'changed source')
        with patch.object(b.socket,'create_connection') as connection:
            with self.assertRaisesRegex(ValueError,'broker_source_changed'):b.client(self.root,dict(request_id='source-changed',operation='status',args={}))
            connection.assert_not_called()
    def test_deadline_crossed_while_reading_complete_broker_ready_is_rejected(self):
        clock=[self.deadline-1_000_000_000];original=b.load
        def load(path):
            value=original(path)
            if Path(path).name=='BROKER_READY.json':clock[0]=self.deadline
            return value
        with patch.object(b,'load',side_effect=load),patch.object(b.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(b.socket,'create_connection') as connection:
            with self.assertRaisesRegex(ValueError,'original_deadline'):b.client(self.root,dict(request_id='late-ready',operation='status',args={}))
            connection.assert_not_called()
    def test_final_response_decode_cannot_return_after_original_deadline(self):
        clock=[self.deadline-1_000_000_000];payload=b'{"ok":true}\n';original=json.loads
        class Connection:
            def __init__(self):self.chunks=[payload,b'']
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def sendall(self,value):pass
            def shutdown(self,how):pass
            def settimeout(self,value):pass
            def recv(self,maximum):return self.chunks.pop(0)
        def decode(raw,*args,**kwargs):
            result=original(raw,*args,**kwargs)
            if isinstance(raw,(bytes,bytearray)) and bytes(raw)==payload:clock[0]=self.deadline
            return result
        with patch.object(b.socket,'create_connection',return_value=Connection()),patch.object(b.json,'loads',side_effect=decode),patch.object(b.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):b.client(self.root,dict(request_id='late-decode',operation='status',args={}))


if __name__=='__main__':unittest.main()
