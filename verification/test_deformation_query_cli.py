"""Finite CLI selection intake: frozen bytes, exact binding and original time."""
import contextlib,copy,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import skin_source_process as process
from verification.test_surface_deformation import one_triangle
from verification.test_skin_source import rehash


def selection(packet):
    return dict(schema='surface-deformation-selection-v1',source_ref=dict(scene_sha256=packet['scene_sha256'],
        rig_object_id=packet['rig']['identity']['object_id'],mesh_object_id=packet['mesh']['identity']['object_id'],
        frame=copy.deepcopy(packet['rig']['payload']['frame'])),triangle_indices=[0])


class DeformationQueryCLITests(unittest.TestCase):
    def run_cli(self,*,blob=None,second=None,mutate_after_read=False,expire_selection=False,relative_path=False):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);root=Path(temporary.name).resolve()
        packet=one_triangle();query=selection(packet);path=root/'selection.json';path.write_bytes(json.dumps(query).encode() if blob is None else blob)
        clock=[100];actors=[];saved=[];real_fsync=os.fsync;real_open=Path.open;names={}
        class Actor:
            def __init__(self,_profile):
                self.received_ns=100;self.deadline_ns=1000;self.profile=dict(fake=True);self.capabilities=dict(read_only=True)
                self.count=0;self.closed=False;actors.append(self)
            def inspect(self):
                self.count+=1
                if mutate_after_read:path.write_text('null')
                return copy.deepcopy(packet if self.count==1 or second is None else second)
            def close(self):self.closed=True
        def opened(p,*args,**kwargs):
            stream=real_open(p,*args,**kwargs);names[stream.fileno()]=p.name;return stream
        def fsync(fd):
            real_fsync(fd);name=names[fd];saved.append(name)
            if expire_selection and name=='SELECTION.json':clock[0]=1000
        output=root/'output';stdout=io.StringIO();query_path='selection.json' if relative_path else str(path)
        with patch.object(process,'SkinSourceProcess',Actor),patch.object(process.time,'perf_counter_ns',side_effect=lambda:clock[0]),\
                patch.object(Path,'open',opened),patch.object(process.os,'fsync',fsync),contextlib.redirect_stdout(stdout):
            code=process.main(['--operator-profile',str(root/'unused.json'),'--output',str(output),'--triangle-query',query_path])
        self.assertEqual(len(actors),1);self.assertTrue(actors[0].closed)
        lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1)
        return code,json.loads(lines[0]),output,actors[0],query,saved

    def test_explicit_query_returns_requested_face_with_actual_capture_binding(self):
        code,out,folder,actor,query,_=self.run_cli()
        self.assertEqual(code,0);self.assertEqual(actor.count,2);self.assertEqual(out['task_query']['triangle_indices'],[0])
        self.assertEqual(out['task_query']['source_sha256'],out['source_sha256'])
        self.assertEqual(out['task_query']['triangles'][0]['principal_stretches'],[1.,1.])
        self.assertEqual(json.loads((folder/'SELECTION.json').read_text()),query)
        self.assertEqual(out['geometry_setters'],0);self.assertFalse(out['execution_authority'])

    def test_selection_is_frozen_before_inspect_even_if_input_file_changes(self):
        code,out,folder,_,query,_=self.run_cli(mutate_after_read=True)
        self.assertEqual(code,0);self.assertEqual(out['task_query']['triangle_indices'],[0])
        self.assertEqual(json.loads((folder/'SELECTION.json').read_text()),query)

    def test_null_cannot_silently_turn_an_explicit_selection_into_overview(self):
        code,out,folder,actor,_,_=self.run_cli(blob=b'null')
        self.assertEqual(code,1);self.assertIn('selection_fields',out['reason']);self.assertEqual(actor.count,1)
        self.assertFalse((folder/'REPORT.json').exists())

    def test_other_invalid_selection_shapes_never_publish_success(self):
        for value in (True,[],{},'query'):
            with self.subTest(value=value):
                code,out,folder,_,_,_=self.run_cli(blob=json.dumps(value).encode())
                self.assertEqual(code,1);self.assertIn('selection_fields',out['reason']);self.assertFalse((folder/'REPORT.json').exists())

    def test_duplicate_keys_are_rejected_before_inspect(self):
        code,out,folder,actor,_,_=self.run_cli(blob=b'{"schema":0,"schema":1}')
        self.assertEqual(code,1);self.assertIn('duplicate_JSON_key',out['reason']);self.assertEqual(actor.count,0)
        self.assertFalse((folder/'REPORT.json').exists())

    def test_selection_byte_budget_is_checked_before_decode_or_inspect(self):
        code,out,_,actor,_,_=self.run_cli(blob=b' '*4097)
        self.assertEqual(code,1);self.assertIn('selection_byte_budget',out['reason']);self.assertEqual(actor.count,0)

    def test_nonfinite_json_is_rejected(self):
        code,out,_,actor,_,_=self.run_cli(blob=b'{"schema":NaN}')
        self.assertEqual(code,1);self.assertIn('nonfinite',out['reason']);self.assertEqual(actor.count,0)

    def test_selection_fsync_cannot_renew_original_deadline(self):
        code,out,folder,actor,_,saved=self.run_cli(expire_selection=True)
        self.assertEqual(code,1);self.assertEqual(out['reason'],'rig_pose_original_deadline');self.assertEqual(actor.count,0)
        self.assertEqual(saved,['INPUTS.json','SELECTION.json','FAILURE.json']);self.assertFalse((folder/'REPORT.json').exists())

    def test_second_capture_change_does_not_rebind_the_selected_triangle(self):
        changed=one_triangle();changed['rig']['payload']['unit_scale_m']=.001;rehash(changed)
        code,out,folder,actor,_,_=self.run_cli(second=changed)
        self.assertEqual(code,1);self.assertIn('query_stale_source',out['reason']);self.assertEqual(actor.count,2)
        self.assertFalse((folder/'REPORT.json').exists())

    def test_query_file_path_must_be_absolute(self):
        code,out,_,actor,_,_=self.run_cli(relative_path=True)
        self.assertEqual(code,1);self.assertIn('selection_path',out['reason']);self.assertEqual(actor.count,0)


if __name__=='__main__':unittest.main()
