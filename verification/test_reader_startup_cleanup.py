"""Post-Popen reader launch failures must close/reap, before any handshake.

Typed process doubles cover constructor/start and escalation branches. A tiny
real Python stdin worker separately verifies actual OS process/pipe cleanup;
it is not a Blender handshake or geometry test.
"""
import contextlib,hashlib,io,json,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from human_eye_plugin import rig_pose_process,skin_source_process,rig_constraint_process,surface_owned_process

CASES=((rig_pose_process,'RigPoseProcess'),(skin_source_process,'SkinSourceProcess'),
    (rig_constraint_process,'RigConstraintProcess'),(surface_owned_process,'OwnedSurfaceProcess'))
SOURCE='a'*64


class LaunchFailure(RuntimeError):pass


class Process:
    def __init__(self,timeouts=0):
        self.stdin=io.BytesIO();self.stdout=io.BytesIO();self.stderr=io.BytesIO();self.pid=12345
        self.returncode=None;self.waits=0;self.timeouts=timeouts;self.terminates=0;self.kills=0
    def poll(self):return self.returncode
    def wait(self,timeout):
        self.waits+=1
        if self.waits<=self.timeouts:raise subprocess.TimeoutExpired('fake-read-worker',timeout)
        self.returncode=-9 if self.kills else -15 if self.terminates else 0
        return self.returncode
    def terminate(self):self.terminates+=1
    def kill(self):self.kills+=1


def ready(actor,module):
    if module is surface_owned_process:
        from human_eye_plugin.forward_deadline import counter_descriptor
        return dict(kind='ready',protocol=module.s.PROTOCOL,config_sha256=actor.config_sha,worker_source_sha256=actor.manifest['surface_owned_worker'],
            source_manifest=actor.manifest,runtime_source_sha256=SOURCE,process_id=actor.process.pid,clock=counter_descriptor(),limits=module.s.LIMITS,
            generic_exec=False,ui_attached=False,original_file_saved=False,external_process_proof=False)
    result=dict(kind='ready',protocol=module.r.PROTOCOL if module is rig_pose_process else module.core.PROTOCOL,process_id=actor.process.pid,
        scene_sha256=actor.profile['scene_sha256'],profile_sha256=hashlib.sha256(actor.profile_bytes).hexdigest(),module_sha256=actor.module_sha,
        worker_sha256=actor.worker_sha,read_only=True,geometry_setters=0,saves_file=False,generic_exec=False)
    if module is not rig_pose_process:result.update(math_sha256=actor.math_sha,deadline_ns=actor.deadline_ns)
    return result


class ReaderStartupCleanupTests(unittest.TestCase):
    @contextlib.contextmanager
    def environment(self,module,class_name):
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            root=Path(folder).resolve();binary=root/'fake-blender.exe';scene=root/'scene.blend';reference=root/'reference.json'
            binary.write_bytes(b'fake binary');scene.write_bytes(b'fake scene');reference.write_bytes(b'{}')
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            common=dict(blender_executable=str(binary),blender_sha256=sha(binary),scene_file=str(scene),scene_sha256=sha(scene),runtime_source_sha256=SOURCE)
            frame=dict(number=1,subframe=0.)
            if module is rig_pose_process:
                profile=dict(common,schema='rig-pose-operator-profile-v1',object_name='Rig',expected_frame=frame,policy_file=None,policy_sha256=None)
            elif module is skin_source_process:
                profile=dict(common,schema='skin-source-operator-profile-v1',mesh_name='Skin',rig_name='Rig',expected_frame=frame)
            elif module is rig_constraint_process:
                profile=dict(common,schema='rig-constraint-operator-profile-v1',object_name='Rig',target_name='Target',constraint_bone='Bone',expected_frame=frame)
            else:
                profile=dict(common,reference_file=str(reference),reference_sha256=sha(reference))
                stack.enter_context(patch.object(module.s,'load_config',return_value=(profile,'c'*64)))
            path=root/'PROFILE.json';path.write_text(json.dumps(profile))
            stack.enter_context(patch.object(module,'runtime_identity',return_value=dict(source_sha256=SOURCE)))
            stack.enter_context(patch.object(module,'check_source_drift',return_value=dict(compatible=True)))
            yield getattr(module,class_name),path

    def failed(self,module,class_name,*,phase,ordinal,timeouts=0,error=None):
        process=Process(timeouts);error=error or LaunchFailure('reader launch failed');constructed=[];started=[]
        def thread(**kwargs):
            index=len(constructed)+1;constructed.append(index)
            if phase=='construct' and index==ordinal:raise error
            def start():
                started.append(index)
                if phase=='start' and index==ordinal:raise error
            return SimpleNamespace(start=start)
        with self.environment(module,class_name) as (cls,path),patch.object(module.subprocess,'Popen',return_value=process) as popen,\
                patch.object(module.threading,'Thread',side_effect=thread),patch.object(cls,'_next') as handshake:
            with self.assertRaises(BaseException) as caught:cls(path)
            popen.assert_called_once();handshake.assert_not_called()
        if module is surface_owned_process:self.assertIs(caught.exception.__cause__,error)
        else:self.assertIs(caught.exception,error)
        self.assertIsNotNone(process.poll());self.assertGreaterEqual(process.waits,1)
        self.assertTrue(all(s.closed for s in (process.stdin,process.stdout,process.stderr)))
        self.assertEqual(constructed,list(range(1,ordinal+1)))
        self.assertEqual(started,list(range(1,ordinal+(1 if phase=='start' else 0))))
        return process

    def test_first_reader_constructor_failure_reaps_without_handshake(self):
        for module,name in CASES:
            with self.subTest(module=name):self.failed(module,name,phase='construct',ordinal=1)

    def test_second_reader_constructor_failure_cleans_after_first_launch(self):
        for module,name in CASES:
            with self.subTest(module=name):self.failed(module,name,phase='construct',ordinal=2)

    def test_first_reader_start_failure_reaps_without_handshake(self):
        for module,name in CASES:
            with self.subTest(module=name):self.failed(module,name,phase='start',ordinal=1)

    def test_second_reader_start_failure_cleans_already_launched_worker(self):
        for module,name in CASES:
            with self.subTest(module=name):self.failed(module,name,phase='start',ordinal=2)

    def test_failed_start_keeps_timeout_terminate_kill_cleanup_path(self):
        for module,name in CASES:
            with self.subTest(module=name):
                process=self.failed(module,name,phase='start',ordinal=2,timeouts=1 if module is surface_owned_process else 2)
                self.assertEqual(process.terminates,1);self.assertEqual(process.kills,1);self.assertEqual(process.returncode,-9)

    def test_baseexception_on_launch_also_releases_the_process(self):
        for module,name in CASES:
            with self.subTest(module=name):self.failed(module,name,phase='start',ordinal=2,error=KeyboardInterrupt('launch interruption'))

    def test_normal_ready_binding_waits_for_both_reader_launches_and_keeps_original_window(self):
        for module,name in CASES:
            with self.subTest(module=name),self.environment(module,name) as (cls,path):
                process=Process();starts=[]
                with patch.object(module.subprocess,'Popen',return_value=process),\
                        patch.object(module.threading,'Thread',side_effect=lambda **kw:SimpleNamespace(start=lambda:starts.append(kw['target']))),\
                        patch.object(cls,'_next',autospec=True,side_effect=lambda actor,*args:ready(actor,module)) as handshake:
                    actor=cls(path)
                self.assertEqual(len(starts),2);handshake.assert_called_once();self.assertEqual(actor.capabilities,ready(actor,module))
                self.assertIsNone(process.poll());self.assertFalse(actor.closed)
                if module is not surface_owned_process:self.assertEqual(actor.deadline_ns-actor.received_ns,30_000_000_000)
                actor.close();waits=process.waits;actor.close();self.assertEqual(process.waits,waits)
                self.assertTrue(all(s.closed for s in (process.stdin,process.stdout,process.stderr)))

    def test_invalid_ready_reply_still_cleans_after_successful_reader_launch(self):
        for module,name in CASES:
            with self.subTest(module=name),self.environment(module,name) as (cls,path):
                process=Process()
                with patch.object(module.subprocess,'Popen',return_value=process),\
                        patch.object(module.threading,'Thread',return_value=SimpleNamespace(start=lambda:None)),\
                        patch.object(cls,'_next',return_value={'kind':'wrong'}):
                    with self.assertRaises(ValueError):cls(path)
                self.assertIsNotNone(process.poll());self.assertTrue(all(s.closed for s in (process.stdin,process.stdout,process.stderr)))

    def test_first_and_second_start_failures_close_real_python_child_and_all_pipes(self):
        real_popen=subprocess.Popen;real_thread=threading.Thread
        for module,name in CASES:
            for ordinal in (1,2):
                with self.subTest(module=name,ordinal=ordinal),self.environment(module,name) as (cls,path):
                    children=[];threads=[];handshake_error=LaunchFailure('controlled real worker launch failure')
                    def spawn(_command,**kwargs):
                        child=real_popen([sys.executable,'-B','-c','import sys; sys.stdin.buffer.read()'],**kwargs);children.append(child);return child
                    def thread(**kwargs):
                        value=real_thread(**kwargs);threads.append(value)
                        if len(threads)==ordinal:value.start=lambda:(_ for _ in ()).throw(handshake_error)
                        return value
                    try:
                        with patch.object(module.subprocess,'Popen',side_effect=spawn),patch.object(module.threading,'Thread',side_effect=thread),patch.object(cls,'_next') as handshake:
                            with self.assertRaises(BaseException):cls(path)
                            handshake.assert_not_called()
                        self.assertEqual(len(children),1);child=children[0];self.assertIsNotNone(child.poll())
                        self.assertTrue(all(s.closed for s in (child.stdin,child.stdout,child.stderr)))
                    finally:
                        for child in children:
                            if child.poll() is None:child.kill();child.wait(timeout=3)
                        for value in threads:
                            if value.ident is not None:value.join(timeout=3);self.assertFalse(value.is_alive())


if __name__=='__main__':unittest.main()
