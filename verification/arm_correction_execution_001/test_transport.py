"""Typed mutation transport faults; real shipped worker with a fake host only.

No Blender/model process is started. The small Python child runs the unchanged
worker command loop against a deliberately limited host fixture, so delivery
failure classification is tested independently of native geometry.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_process import BlenderProcessHost,HostTransportError

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKER=ROOT/'human_eye_plugin/blender_worker.py'

HOST_SOURCE='''
class BlenderSceneHost:
    def __init__(self,**kwargs):pass
    def correct_arm_axial(self,task):
        event=task['event_id'];selection=task['selection']
        if event=='raise_after_previous':raise RuntimeError('unacknowledged setter entry')
        source={'unit':'m','coordinate_frame':'armature_local','selected_bones':selection['bone_names'],
                'mesh':{'name':selection['mesh_name']},'armature':{'name':selection['armature_name']}}
        result={'schema':'arm-axial-execution-result-v1','event_id':event,'status':'satisfied',
            'reason':'actual_target_met','executed':True,'setter_attempts':2,'setter_returns':2,
            'task_succeeded':True,'before_source':source,'after_source':source}
        if event=='no_op':result.update(status='no_op',reason='area_target_already_met',
            executed=False,setter_attempts=0,setter_returns=0,after_source=None)
        if event=='partial':result.update(status='execution_uncertain',reason='second_setter_failed',
            setter_returns=1,task_succeeded=False,after_source=None)
        if event=='readback_failed':result.update(status='execution_uncertain',reason='after_readback_failed',
            task_succeeded=False,after_source=None)
        if event=='wrong_event':result['event_id']='unrelated'
        if event=='boolean_count':result['setter_returns']=True
        if event=='contradictory_noop':result.update(status='no_op',executed=False)
        if event=='uncertain_zero':result.update(status='execution_uncertain',executed=None,
            setter_attempts=0,setter_returns=0,task_succeeded=False)
        if event=='uncertain_attempt_zero':result.update(status='execution_uncertain',executed=None,
            setter_attempts=0,setter_returns=None,task_succeeded=False)
        if event=='nonfinite_receipt':result['unserializable']=float('nan')
        return result
'''

LAUNCHER='''
import runpy,sys,types
from pathlib import Path
worker,fixture=map(Path,sys.argv[1:3]);flag=sys.argv[3:]
sys.modules['bpy']=types.SimpleNamespace(app=types.SimpleNamespace(version_string='fake-arm-worker-protocol'))
sys.argv=[str(worker),'--',str(fixture),*flag]
runpy.run_path(str(worker),run_name='__main__')
'''


def task(event='success'):
    return {'schema':'arm-axial-execution-task-v1','event_id':event,
        'selection':{'mesh_name':'ArmMesh','armature_name':'ArmRig','bone_names':['root','middle','end'],
            'vertex_indices':list(range(402)),'sections':[list(range(i*16,(i+1)*16)) for i in range(25)]},
        'u_interval_deg':[0.,120.],'max_section_area_loss':.4,
        'protected_vertex_ids':list(range(194)),'angle_tolerance_deg':.001,
        'position_tolerance_m':5e-6,'area_tolerance':1e-6,'sentinel_name':'Outside'}


class ArmTransportTests(unittest.TestCase):
    def setUp(self):
        (HERE/'temp').mkdir(exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=HERE/'temp')
        self.base=Path(self.temporary.name).resolve()
        assert self.base.is_relative_to(HERE.resolve())
        self.addCleanup(self.temporary.cleanup)
        (self.base/'human_eye_plugin').mkdir()
        (self.base/'human_eye_plugin/blender_host.py').write_text(HOST_SOURCE,encoding='utf8',newline='\n')
        self.launcher=self.base/'worker_launcher.py';self.launcher.write_text(LAUNCHER,encoding='utf8',newline='\n')
        self.blend=self.base/'transport-fixture.blend';self.blend.write_bytes(b'fake host; no Blender reads this')
        self.real_popen=subprocess.Popen

    def host(self,**options):
        def launch(command,**kwargs):
            flag=['material-readview-only-v1'] if command[-1]=='material-readview-only-v1' else []
            # Windows venv python.exe is a redirector with a different child
            # PID. Use its actual interpreter for the ownership handshake.
            return self.real_popen([getattr(sys,'_base_executable',sys.executable),'-I','-B',
                str(self.launcher),str(WORKER),str(self.base),*flag],**kwargs)
        with patch('human_eye_plugin.blender_process.subprocess.Popen',side_effect=launch):
            host=BlenderProcessHost(sys.executable,self.blend,timeout=1.,startup_timeout=3.,**options)
        self.addCleanup(host.close)
        return host

    def test_actual_worker_dispatch_accepts_the_full_selection_and_receipt(self):
        value=task();before=deepcopy(value)
        self.assertGreater(len(json.dumps(value)),4096)
        host=self.host();receipt=host.correct_arm_axial(value)
        self.assertEqual(receipt['status'],'satisfied');self.assertEqual(receipt['setter_returns'],2)
        self.assertEqual(value,before);self.assertTrue(host.is_alive)

    def test_noop_has_no_writes_and_keeps_connection(self):
        host=self.host();receipt=host.correct_arm_axial(task('no_op'))
        self.assertEqual((receipt['executed'],receipt['setter_attempts'],receipt['setter_returns']),(False,0,0))
        self.assertTrue(host.is_alive)

    def test_partial_pair_returns_known_counts_then_quarantines(self):
        host=self.host();receipt=host.correct_arm_axial(task('partial'))
        self.assertEqual(receipt['status'],'execution_uncertain')
        self.assertEqual((receipt['setter_attempts'],receipt['setter_returns']),(2,1))
        self.assertTrue(receipt['executed']);self.assertFalse(host.is_alive)
        sequence=host._sequence
        with self.assertRaises(HostTransportError):host.correct_arm_axial(task('partial'))
        self.assertEqual(host._sequence,sequence)

    def test_postwrite_readback_failure_preserves_two_returned_setters(self):
        host=self.host();receipt=host.correct_arm_axial(task('readback_failed'))
        self.assertEqual((receipt['setter_attempts'],receipt['setter_returns']),(2,2))
        self.assertFalse(receipt['task_succeeded']);self.assertFalse(host.is_alive)

    def test_worker_serialization_failure_carries_known_action_receipt(self):
        host=self.host()
        with self.assertRaises(HostTransportError) as caught:host.correct_arm_axial(task('nonfinite_receipt'))
        receipt=caught.exception.mutation_result
        self.assertEqual(receipt['event_id'],'nonfinite_receipt')
        self.assertEqual((receipt['setter_attempts'],receipt['setter_returns']),(2,2))
        self.assertTrue(receipt['executed']);self.assertFalse(receipt['task_succeeded'])
        self.assertFalse(host.is_alive)

    def test_invalid_event_counts_or_completion_receipts_fail_closed(self):
        for event in ('wrong_event','boolean_count','contradictory_noop','uncertain_zero','uncertain_attempt_zero'):
            with self.subTest(event=event):
                host=self.host()
                with self.assertRaises(HostTransportError):host.correct_arm_axial(task(event))
                self.assertFalse(host.is_alive)

    def test_worker_error_does_not_reuse_the_previous_event_counts(self):
        host=self.host();host.correct_arm_axial(task('success'))
        with self.assertRaises(HostTransportError) as caught:host.correct_arm_axial(task('raise_after_previous'))
        self.assertFalse(hasattr(caught.exception,'mutation_result'));self.assertFalse(host.is_alive)

    def test_custom_or_readonly_workers_cannot_use_new_writes(self):
        for options in ({'worker_path':WORKER},{'material_readview_only':True}):
            with self.subTest(options=options):
                host=self.host(**options);sequence=host._sequence
                with self.assertRaises(ValueError):host.correct_arm_axial(task())
                self.assertEqual(host._sequence,sequence);self.assertTrue(host.is_alive)

    def test_local_nonfinite_or_untyped_input_is_rejected_without_dispatch(self):
        host=self.host()
        for value in (dict(task(),candidate_matrices=[]),dict(task(),max_section_area_loss=float('nan'))):
            sequence=host._sequence
            with self.assertRaises(ValueError):host.correct_arm_axial(value)
            self.assertEqual(host._sequence,sequence);self.assertTrue(host.is_alive)


if __name__=='__main__':unittest.main()
