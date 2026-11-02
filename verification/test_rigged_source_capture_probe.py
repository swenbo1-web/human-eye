"""Probe transport/publication counterexamples, not native source certification."""
import contextlib,copy,io,json,os,queue,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from verification import rigged_source_capture_probe as probe


class _Output:
    def __init__(self):self.queue=queue.Queue()
    def readline(self,_limit):return self.queue.get(timeout=3)


class _Input:
    def __init__(self,process):self.process=process
    def write(self,blob):
        value=json.loads(blob);self.process.commands.append(value)
        if value['command']=='shutdown':self.process.emit(dict(kind='closed',id=value['id']))
        else:self.process.emit(dict(kind='snapshot',id=value['id'],packet=copy.deepcopy(self.process.packet)))
    def flush(self):pass
    def close(self):pass


class FakeProcess:
    def __init__(self,command,**kwargs):
        self.pid=73;self.returncode=None;self.commands=[];self.stdout=_Output();self.stdin=_Input(self)
        profile=Path(command[command.index('--profile')+1]);value=json.loads(profile.read_bytes())
        self.deadline=int(command[command.index('--deadline-ns')+1])
        self.packet=dict(schema='fake-clock-only',identity=dict(epoch='unit',scene_sha256=value['scene_sha256'],profile_sha256=probe.sha(profile),
            probe_sha256=value['probe_sha256'],binary_sha256=value['blender_sha256']),inputs=dict(frame=value['expected_frame'],
            rig=dict(name=value['rig_name']),mesh=dict(name=value['mesh_name'])),evaluated=dict(),audit=dict(),capture_id='unit')
        self.packet['source_sha256']=probe.source_digest(self.packet)
        self.emit(dict(kind='ready',pid=self.pid,profile_sha256=probe.sha(profile),probe_sha256=value['probe_sha256'],deadline_ns=self.deadline))
    def emit(self,value):self.stdout.queue.put(probe.PREFIX+probe.encoded(value)+b'\n')
    def poll(self):return self.returncode
    def wait(self,timeout=None):
        self.returncode=0 if self.returncode is None else self.returncode;self.stdout.queue.put(b'');return self.returncode
    def terminate(self):self.returncode=-15;self.stdout.queue.put(b'')
    def kill(self):self.terminate()


class SourceCaptureProbeTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_and_size_are_rejected(self):
        for blob,reason in ((b'{"a":1,"a":2}','duplicate_key'),(b'{"a":NaN}','nonfinite'),(b' '* (probe.LIMIT+1),'response_budget')):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError,reason):probe.decode(blob)

    def test_capture_id_is_not_source_but_every_input_and_eval_is(self):
        packet=dict(inputs=dict(parent_inverse=[1,2],future_key=[3,4]),evaluated=dict(vertices=[[1,2,3]]),capture_id='a')
        before=probe.source_digest(packet);packet['capture_id']='b';packet['source_sha256']='not-part-of-self-digest'
        self.assertEqual(before,probe.source_digest(packet))
        for key in ('parent_inverse','future_key'):
            changed=copy.deepcopy(packet);changed['inputs'][key][-1]+=.001
            self.assertNotEqual(before,probe.source_digest(changed))
        packet['evaluated']['vertices'][0][0]+=1;self.assertNotEqual(before,probe.source_digest(packet))

    def run_clock(self,expire_at=None,qualify=False,qualification_status='qualified',wrong_identity=False,wrong_role=False):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);root=Path(folder.name).resolve();scene=root/'source.blend';scene.write_bytes(b'owned fake only')
        binary=root/'blender.exe';binary.write_bytes(b'fake executable not launched');output=root/'run';clock=[100];actors=[];names={};qualified=[]
        real_open=Path.open;real_fsync=os.fsync;real_replace=os.replace;real_encoded=probe.encoded
        def opened(path,*args,**kwargs):
            stream=real_open(path,*args,**kwargs);names[stream.fileno()]=path.name;return stream
        def fsync(fd):
            real_fsync(fd)
            if expire_at==names[fd]:clock[0]=100+30_000_000_000
        def replace(source,destination):
            real_replace(source,destination)
            if expire_at=='publish' and destination.name=='REPORT.json':clock[0]=100+30_000_000_000
        def encoded(value):
            result=real_encoded(value)
            if expire_at=='success_encode' and type(value) is dict and value.get('passed') is True:clock[0]=100+30_000_000_000
            return result
        def popen(*args,**kwargs):
            actor=FakeProcess(*args,**kwargs);actors.append(actor)
            if wrong_identity:actor.packet['identity']['scene_sha256']='0'*64
            if wrong_role:actor.packet['inputs']['mesh']['name']='Other'
            actor.packet['source_sha256']=probe.source_digest(actor.packet)
            if expire_at=='close':
                old=actor.wait
                def wait(*a,**kw):
                    result=old(*a,**kw);clock[0]=100+30_000_000_000;return result
                actor.wait=wait
            return actor
        def qualification(packet,*,deadline_ns,expected_source_sha256):
            qualified.append(dict(deadline=deadline_ns,source=expected_source_sha256))
            return dict(status=qualification_status,product_support_certified=False)
        args=SimpleNamespace(output=output,scene=scene,blender=binary,mesh_name='Mesh',rig_name='Rig',frame_number=1,subframe=0.,qualify=qualify)
        stdout=io.StringIO()
        with patch.object(probe.subprocess,'Popen',popen),patch.object(probe.time,'perf_counter_ns',side_effect=lambda:clock[0]),\
                patch.object(Path,'open',opened),patch.object(probe.os,'fsync',fsync),patch.object(probe.os,'replace',replace),patch.object(probe,'encoded',encoded),\
                patch.dict('sys.modules',{'verification.rigged_source_qualification':SimpleNamespace(qualify=qualification)}),contextlib.redirect_stdout(stdout):
            code=probe.controller(args)
        lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1)
        self.assertTrue(all(a.poll() is not None for a in actors));return code,json.loads(lines[0]),output,actors,qualified

    def test_normal_protocol_reuses_one_original_deadline_and_reaps(self):
        code,result,folder,actors,_=self.run_clock();self.assertEqual(code,0);self.assertTrue(result['passed'])
        actor=actors[0];self.assertEqual([x['command'] for x in actor.commands],['inspect','inspect','shutdown'])
        self.assertEqual({x['deadline_ns'] for x in actor.commands},{actor.deadline});self.assertTrue((folder/'REPORT.json').exists())

    def test_qualification_runs_before_close_in_the_original_window(self):
        code,result,folder,actors,qualified=self.run_clock(qualify=True)
        self.assertEqual(code,0);self.assertEqual(result['stage'],'capture_and_qualification');self.assertEqual(len(qualified),1)
        self.assertEqual(qualified[0]['deadline'],actors[0].deadline);self.assertEqual(qualified[0]['source'],actors[0].packet['source_sha256'])
        report=json.loads((folder/'REPORT.json').read_bytes());self.assertEqual(report['qualification']['status'],'qualified')

    def test_rejected_qualification_is_not_a_successful_admission_or_pipeline_error(self):
        code,result,folder,_,_=self.run_clock(qualify=True,qualification_status='rejected')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertFalse(result['qualification_passed'])
        report=json.loads((folder/'REPORT.json').read_bytes());self.assertEqual(report['qualification']['status'],'rejected')
        self.assertFalse(report['qualification_passed']);self.assertFalse((folder/'FAILURE.json').exists())

    def test_self_hashed_wrong_identity_packet_is_not_trusted(self):
        code,result,folder,_,_=self.run_clock(wrong_identity=True)
        self.assertEqual(code,1);self.assertEqual(result['reason'],'b3_probe_packet_identity_binding')
        self.assertFalse((folder/'REPORT.json').exists())

    def test_packet_roles_are_bound_in_addition_to_ready_and_source_digest(self):
        code,result,folder,_,_=self.run_clock(wrong_role=True)
        self.assertEqual(code,1);self.assertEqual(result['reason'],'b3_probe_packet_roles_or_frame_binding')
        self.assertFalse((folder/'REPORT.json').exists())

    def test_profile_persistence_expiry_cannot_launch_a_worker(self):
        code,result,folder,actors,_=self.run_clock('PROFILE.json')
        self.assertEqual(code,1);self.assertEqual(result['reason'],'b3_probe_original_deadline');self.assertFalse(actors);self.assertFalse((folder/'REPORT.json').exists())

    def test_read_persistence_expiry_cannot_start_second_read(self):
        code,result,folder,actors,_=self.run_clock('READ_01.json')
        self.assertEqual(code,1);self.assertEqual(result['reason'],'b3_probe_original_deadline');self.assertEqual(len(actors[0].commands),1)
        self.assertFalse((folder/'REPORT.json').exists())

    def test_pending_publish_encode_and_close_expiry_never_leave_valid_report(self):
        for point in ('REPORT_PENDING.json','publish','success_encode','close'):
            with self.subTest(point=point):
                code,result,folder,_,_=self.run_clock(point);self.assertEqual(code,1)
                self.assertFalse(result['passed']);self.assertEqual(result['reason'],'b3_probe_original_deadline');self.assertFalse((folder/'REPORT.json').exists())
                self.assertEqual((folder/'REVOKED_REPORT.json').exists(),point in ('publish','success_encode'))


if __name__=='__main__':unittest.main()
