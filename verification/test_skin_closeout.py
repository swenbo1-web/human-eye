"""Deterministic original-deadline checks around source report publication."""
import contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import skin_source_process as process


class Clock:
    def __init__(self):self.now=100;self.deadline=1000
    def __call__(self):return self.now
    def expire(self):self.now=self.deadline


class SkinCloseoutTests(unittest.TestCase):
    def run_case(self,expire_at=None):
        clock=Clock();actors=[];fsync_names=[];analyzed=[]
        report=dict(schema='fake-closeout-only',status='known',geometry_setters=0,execution_authority=False)
        class FakeActor:
            def __init__(self,profile):
                self.received_ns=clock();self.deadline_ns=clock.deadline;self.profile=dict(fake_profile=True)
                self.capabilities=dict(read_only=True);self.inspections=0;self.closed=False;actors.append(self)
            def inspect(self):self.inspections+=1;return dict(snapshot=self.inspections)
            def close(self):self.closed=True
        real_fsync=os.fsync;real_replace=os.replace;real_dumps=json.dumps;real_open=Path.open;descriptor_names={}
        def tracked_open(path,*args,**kwargs):
            stream=real_open(path,*args,**kwargs);descriptor_names[stream.fileno()]=path.name;return stream
        def fsync(fd):
            real_fsync(fd)
            name=descriptor_names[fd]
            fsync_names.append(name)
            if expire_at==name:clock.expire()
        def replace(source,destination):
            real_replace(source,destination)
            if expire_at=='replace_REPORT' and Path(destination).name=='REPORT.json':clock.expire()
        def dumps(value,*args,**kwargs):
            encoded=real_dumps(value,*args,**kwargs)
            if expire_at=='encode_success' and type(value) is dict and 'evidence' in value and 'elapsed_ns' in value:clock.expire()
            return encoded
        def analyze(value,*,deadline_ns):
            self.assertEqual(value,dict(snapshot=2));self.assertEqual(deadline_ns,clock.deadline)
            analyzed.append(value);return dict(report)
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        output=Path(folder.name).resolve()/'evidence';stdout=io.StringIO()
        with patch.object(process,'SkinSourceProcess',FakeActor),patch.object(process.time,'perf_counter_ns',clock),\
                patch.object(process.os,'fsync',fsync),patch.object(process.os,'replace',replace),\
                patch.object(process.json,'dumps',dumps),patch.object(process.surface_deformation,'analyze',analyze),\
                patch.object(Path,'open',tracked_open),contextlib.redirect_stdout(stdout):
            code=process.main(['--operator-profile',str(output.parent/'unused-profile.json'),'--output',str(output)])
        self.assertEqual(len(actors),1);self.assertTrue(actors[0].closed)
        lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1)
        return code,json.loads(lines[0]),output,actors[0],fsync_names,analyzed,report

    def assert_expired(self,stage):
        code,value,output,actor,fsync_names,analyzed,report=self.run_case(stage)
        self.assertEqual(code,1);self.assertEqual(value['status'],'unavailable')
        self.assertEqual(value['reason'],'rig_pose_original_deadline')
        self.assertFalse(value['execution_authority']);self.assertEqual(value['geometry_setters'],0)
        self.assertFalse((output/'REPORT.json').exists())
        self.assertEqual(json.loads((output/'FAILURE.json').read_text()),value)
        if stage in ('replace_REPORT','encode_success'):
            self.assertEqual(json.loads((output/'REVOKED_REPORT.json').read_text()),report)
        else:self.assertFalse((output/'REVOKED_REPORT.json').exists())
        return output,actor,fsync_names,analyzed

    def test_inputs_fsync_expiry_prevents_inspection(self):
        output,actor,names,analyzed=self.assert_expired('INPUTS.json')
        self.assertEqual(actor.inspections,0);self.assertFalse(analyzed)
        self.assertEqual(names,['INPUTS.json','FAILURE.json'])
        self.assertFalse((output/'SNAPSHOTS.json').exists())

    def test_snapshots_fsync_expiry_prevents_analysis(self):
        _,actor,names,analyzed=self.assert_expired('SNAPSHOTS.json')
        self.assertEqual(actor.inspections,2);self.assertFalse(analyzed)
        self.assertEqual(names,['INPUTS.json','SNAPSHOTS.json','FAILURE.json'])

    def test_pending_fsync_expiry_never_publishes_report(self):
        output,_,names,analyzed=self.assert_expired('REPORT_PENDING.json')
        self.assertTrue((output/'REPORT_PENDING.json').exists());self.assertEqual(len(analyzed),1)
        self.assertEqual(names,['INPUTS.json','SNAPSHOTS.json','REPORT_PENDING.json','FAILURE.json'])

    def test_report_replace_expiry_revokes_published_report(self):self.assert_expired('replace_REPORT')

    def test_success_json_encode_expiry_revokes_published_report(self):self.assert_expired('encode_success')

    def test_normal_publication_has_one_success_and_exact_evidence(self):
        code,value,output,actor,names,analyzed,report=self.run_case()
        self.assertEqual(code,0);self.assertEqual(value['status'],'known')
        self.assertEqual(actor.inspections,2);self.assertEqual(len(analyzed),1)
        self.assertEqual(names,['INPUTS.json','SNAPSHOTS.json','REPORT_PENDING.json'])
        self.assertEqual(json.loads((output/'REPORT.json').read_text()),report)
        self.assertEqual(value['evidence'],dict(report_file=str(output/'REPORT.json'),snapshot_file=str(output/'SNAPSHOTS.json')))
        self.assertFalse((output/'REPORT_PENDING.json').exists());self.assertFalse((output/'FAILURE.json').exists())
        self.assertFalse((output/'REVOKED_REPORT.json').exists())


if __name__=='__main__':unittest.main()
