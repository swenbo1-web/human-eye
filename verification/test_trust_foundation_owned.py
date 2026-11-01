"""Opt-in real factory Blender fault tests over scheduler→service→typed host.

Set HUMAN_EYE_TEST_BLENDER to an executable. Optional HUMAN_EYE_TEST_OUTPUT
retains evidence in new exclusive subdirectories. No socket or user GUI is used.
"""
from dataclasses import asdict
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
from human_eye_plugin.goal_supervision import owned_clock_domain
from human_eye_plugin.forward_deadline import counter_descriptor
from human_eye_plugin.live_service import _atomic_write
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.task_authority import ClearanceTaskSpec, TaskApproval, TrustedTaskAuthority

ROOT=Path(__file__).resolve().parents[1]
BLENDER=os.environ.get('HUMAN_EYE_TEST_BLENDER')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=True,allow_nan=False).encode('utf8')).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)


@unittest.skipUnless(BLENDER and Path(BLENDER).is_file(),'Set HUMAN_EYE_TEST_BLENDER for isolated native acceptance')
class TrustFoundationOwnedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output=os.environ.get('HUMAN_EYE_TEST_OUTPUT')
        if output:
            base=Path(output).resolve();base.mkdir(parents=True,exist_ok=True)
            cls.folder=Path(tempfile.mkdtemp(prefix='he-trust-',dir=base))
        else:
            cls.temp=tempfile.TemporaryDirectory(prefix='he-trust-')
            cls.folder=Path(cls.temp.name)
            cls.addClassCleanup(cls.temp.cleanup)
        cls.blend=cls.folder/'fixture.blend'
        result=subprocess.run([BLENDER,'--factory-startup','--disable-autoexec','--background',
            '--python',str(ROOT/'verification/fixtures/create_trust_scene.py'),'--',str(cls.blend)],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (cls.folder/'create.stdout.log').write_bytes(result.stdout)
        (cls.folder/'create.stderr.log').write_bytes(result.stderr)
        if result.returncode or not cls.blend.is_file():raise RuntimeError('owned fixture creation failed')
        cls.blend_sha=hashlib.sha256(cls.blend.read_bytes()).hexdigest()

    def setUp(self):
        self.case=self.folder/self._testMethodName
        self.case.mkdir()
        self.host=BlenderProcessHost(BLENDER,self.blend,timeout=8.,startup_timeout=20.)
        self.addCleanup(self.close_host)
        config=self.case/'connector.json'
        save(config,{'schema_version':'1.0','project_root':str(ROOT),
            'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64})
        self.config=config
        self.expected=None
        self.event_id='owned-test-event'
        self.approvals=[]
        self.authority=TrustedTaskAuthority('trust-owned',self.approve)
        self.scheduler=OwnedGoalScheduler(config,self.host,self.authority)
        self.packet=self.scheduler._capture()
        self.pair={role:next(m['object_id'] for m in self.packet['capture']['meshes'] if m['name']==name)
            for role,name in [('focal_id','BluePart'),('reference_id','GreyBase')]}
        observed=self.scheduler.service.observe('owned-prepare',**self.pair,include_image=False,
            query={'alignment_evidence':False,'support_plane_discovery':{'direction_world':[0.,0.,1.]}})
        discovery=observed['support_plane_discovery']
        self.assertEqual(discovery['status'],'complete',discovery)
        self.assertEqual(len(discovery['candidates']),1,discovery)
        triangle=discovery['candidates'][0]['selector']['reference_triangle_index']
        self.spec=ClearanceTaskSpec(**self.pair,reference_triangle_index=triangle)
        self.register(self.spec)
        save(self.case/'initial.json',self.packet)

    def register(self,spec):
        capture=_validated_scene(self.packet['capture'])[0]
        self.expected={'engine_build_id':runtime_identity(mode='live')['build_id'],
            'process_id':self.host._process.pid,'host_identity':copy.deepcopy(capture['host_identity']),
            'reference_triangle_index':spec.reference_triangle_index,
            'initial_capture_sha256':digest(capture),'initial_native_sha256':digest(self.packet['native_scene']),
            'clock_domain':owned_clock_domain(capture['host_identity']['document_epoch'],counter_descriptor())}
        self.expected_spec=asdict(spec)

    def approve(self,spec,scope):
        approved=scope==self.expected and asdict(spec)==self.expected_spec
        self.approvals.append({'approved':approved,'scope':scope,'spec':asdict(spec)})
        return TaskApproval(self.event_id,'owned-test-authorization') if approved else None

    def close_host(self):
        pid=self.host._process.pid
        self.host.close()
        save(self.case/'process.json',{'pid':pid,'exit_code':self.host._process.poll(),
            'reaped':self.host._process.poll() is not None,'user_gui_attached':False,
            'input_blend_unchanged':hashlib.sha256(self.blend.read_bytes()).hexdigest()==self.blend_sha})
        save(self.case/'approvals.json',self.approvals)
        self.assertIsNotNone(self.host._process.poll())
        self.assertEqual(hashlib.sha256(self.blend.read_bytes()).hexdigest(),self.blend_sha)

    def state(self):return json.loads((self.case/'state.json').read_text(encoding='utf8'))

    def meter(self):
        records=self.state()['goal_authorizations']['records']
        record=next(iter(records.values()))
        return self.host.motion_goal_status(record['grant']['goal_id'])

    def assert_frozen_retry(self,result):
        self.assertEqual(result['status'],'review_required',result)
        self.assertIs(result['task_succeeded'],False,result)
        self.assertIs(result['retry_authorized'],False)
        self.assertIs(result['execution_authority'],False)
        before=self.meter()['physical_meter']['actual_setter_count']
        state=copy.deepcopy(self.state())
        for index,scheduler in enumerate((self.scheduler,OwnedGoalScheduler(self.config,self.host,self.authority))):
            replay=scheduler.run(self.spec)
            save(self.case/('retry-%d.json'%index),replay)
            self.assertIs(replay['executed_this_call'],False,replay)
            self.assertEqual(replay['new_setter_count'],0)
            self.assertEqual(self.meter()['physical_meter']['actual_setter_count'],before)
        if any(record['status']!='completed' for record in state['goal_authorizations']['records'].values()):
            # Also admit a genuinely fresh trusted event against current
            # evidence. Durable unresolved state must block it independently
            # of the original callback rejecting a changed scene.
            self.packet=self.scheduler._capture()
            self.register(self.spec)
            self.event_id='fresh-trusted-event'
            approvals_before=len(self.approvals)
            # Independently prove the fresh intent has a valid trusted grant;
            # quarantine may correctly stop scheduler discovery even before
            # its own authority callback. Issuing is not durable admission.
            self.authority.issue(self.spec,self.expected)
            fresh=OwnedGoalScheduler(self.config,self.host,self.authority).run(self.spec)
            save(self.case/'fresh-event-retry.json',fresh)
            self.assertTrue(any(item['approved'] for item in self.approvals[approvals_before:]),fresh)
            self.assertFalse(fresh['task_succeeded'],fresh)
            self.assertIs(fresh['executed_this_call'],False)
            self.assertEqual(fresh['new_setter_count'],0)
            self.assertEqual(self.meter()['physical_meter']['actual_setter_count'],before)
        after=self.state()
        self.assertEqual(after['goal_supervision'],state['goal_supervision'])
        save(self.case/'final-state.json',after)

    def record(self,result):
        save(self.case/'result.json',result)
        report=self.meter()
        save(self.case/'meter.json',report)
        final=self.host.capture_evidence()
        save(self.case/'final.json',final)
        # Independent analytic gap for the two rotated parallel boxes.
        objects={obj['name']:obj for obj in final['native_scene']['objects']}
        initial={obj['name']:obj for obj in self.packet['native_scene']['objects']}
        self.assertEqual(set(objects),set(initial))
        self.assertEqual(objects['GreyBase'],initial['GreyBase'])
        for key in ('local_vertices','faces'):
            self.assertEqual(objects['BluePart'][key],initial['BluePart'][key])
        if report['physical_meter']['actual_setter_count']==0:
            self.assertEqual(objects,initial)
        base=np.asarray(objects['GreyBase']['world_vertices'])
        part=np.asarray(objects['BluePart']['world_vertices'])
        triangle=base[np.asarray(objects['GreyBase']['faces'][2])]
        normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);normal/=np.linalg.norm(normal)
        gap=float((part@normal).min()-(base@normal).max())
        save(self.case/'independent.json',{'analytic_parallel_box_gap_m':gap,
            'actual_setter_count':report['physical_meter']['actual_setter_count'],
            'coordinates_changed':final['native_scene']['objects']!=self.packet['native_scene']['objects']})
        return report,gap

    def test_normal_completion(self):
        result=self.scheduler.run(self.spec)
        report,gap=self.record(result)
        self.assertTrue(result['task_succeeded'],result)
        self.assertTrue(result['physical_task_succeeded'])
        self.assertEqual(result['completion_persistence'],'committed')
        self.assertEqual(result['new_setter_count'],report['physical_meter']['actual_setter_count'])
        self.assertLessEqual(abs(gap-.001),self.spec.clearance_tolerance_m)

    def test_already_satisfied_zero_setters(self):
        from dataclasses import replace
        self.spec=replace(self.spec,target_clearance_m=.004)
        self.register(self.spec)
        result=self.scheduler.run(self.spec)
        report,gap=self.record(result)
        self.assertTrue(result['task_succeeded'],result)
        self.assertIs(result['executed_this_call'],False)
        self.assertEqual(report['physical_meter']['actual_setter_count'],0)
        self.assertEqual(result['new_setter_count'],0)

    def test_pre_dispatch_preview_failure_zero_setters(self):
        with patch.object(self.scheduler.service,'run_clearance_segment',side_effect=OSError('preview unavailable')):
            result=self.scheduler.run(self.spec)
        report,gap=self.record(result)
        self.assertIs(result['executed_this_call'],False)
        self.assertEqual(result['new_setter_count'],0)
        self.assertEqual(report['physical_meter']['actual_setter_count'],0)
        self.assert_frozen_retry(result)

    def test_failure_after_reconcile_preserves_known_count(self):
        reconciled=[]
        real_supervise=self.scheduler.service.goal_supervision
        real_capture=self.scheduler._capture
        def supervise(operation,*args,**kwargs):
            result=real_supervise(operation,*args,**kwargs)
            if operation=='reconcile':reconciled.append(result['confirmed_steps'])
            return result
        def capture():
            if reconciled:raise OSError('native review unavailable after committed reconciliation')
            return real_capture()
        with patch.object(self.scheduler.service,'goal_supervision',side_effect=supervise), \
                patch.object(self.scheduler,'_capture',side_effect=capture):
            result=self.scheduler.run(self.spec)
        report,gap=self.record(result)
        self.assertTrue(reconciled,result)
        self.assertEqual(result['engine_confirmed_steps'],reconciled[-1])
        self.assertEqual(result['new_setter_count'],report['physical_meter']['actual_setter_count'])
        self.assertTrue(result['executed_this_call'])
        self.assert_frozen_retry(result)

    def storage_fault(self,stage,after_commit=False):
        fired=[]
        def write(path,value,**kwargs):
            segments=list(value.get('goal_segments',{}).get('records',{}).values())
            auth=list(value.get('goal_authorizations',{}).get('records',{}).values())
            eligible=(any(s['status']=='running' and any(t.get('result',{}).get('executed') is True
                for t in s['steps']) for s in segments) if stage=='step' else
                any(s['status']=='satisfied' for s in segments) if stage=='child' else
                any(a['status']=='completed' for a in auth))
            if eligible and not fired:
                fired.append(stage)
                if after_commit:_atomic_write(path,value,**kwargs)
                raise OSError('injected '+stage+(' committed ACK loss' if after_commit else ' save failure'))
            return _atomic_write(path,value,**kwargs)
        with patch('human_eye_plugin.live_service._atomic_write',side_effect=write):
            result=self.scheduler.run(self.spec)
        self.assertEqual(fired,[stage],result)
        report,gap=self.record(result)
        self.assertGreater(report['physical_meter']['actual_setter_count'],0)
        if stage=='goal':
            self.assertTrue(result['physical_task_succeeded'],result)
            self.assertEqual(result['completion_persistence'],'unknown')
            self.assertLessEqual(abs(gap-.001),self.spec.clearance_tolerance_m)
            self.assertEqual(result['new_setter_count'],report['physical_meter']['actual_setter_count'])
        else:
            self.assertIsNone(result['new_setter_count'],result)
            self.assertIsNot(result['executed_this_call'],False)
        self.assert_frozen_retry(result)

    def test_step_save_failure_after_real_setter(self):self.storage_fault('step')
    def test_child_commit_ack_loss(self):self.storage_fault('child',after_commit=True)
    def test_final_goal_save_failure(self):self.storage_fault('goal')
    def test_final_goal_commit_ack_loss(self):self.storage_fault('goal',after_commit=True)

    def test_real_setter_then_host_ack_loss(self):
        real=self.host.apply_transform
        fired=[]
        def apply(*args,**kwargs):
            value=real(*args,**kwargs)
            fired.append(True)
            raise OSError('injected loss of genuine host ACK')
        with patch.object(self.host,'apply_transform',side_effect=apply):
            result=self.scheduler.run(self.spec)
        self.assertEqual(len(fired),1,result)
        report,gap=self.record(result)
        self.assertGreater(report['physical_meter']['actual_setter_count'],0)
        self.assertIsNone(result['new_setter_count'],result)
        self.assertIsNot(result['executed_this_call'],False)
        self.assert_frozen_retry(result)

    def test_readback_failure_after_real_setter(self):
        applied=[]
        real_apply=self.host.apply_transform
        real_capture=self.host.capture_scene
        def apply(*args,**kwargs):
            result=real_apply(*args,**kwargs);applied.append(True);return result
        def capture(*args,**kwargs):
            if applied:raise OSError('injected unavailable readback after genuine setter')
            return real_capture(*args,**kwargs)
        with patch.object(self.host,'apply_transform',side_effect=apply),patch.object(self.host,'capture_scene',side_effect=capture):
            result=self.scheduler.run(self.spec)
        self.assertGreater(len(applied),0,result)
        report,gap=self.record(result)
        self.assertGreater(report['physical_meter']['actual_setter_count'],0)
        self.assertIsNone(result['new_setter_count'],result)
        self.assert_frozen_retry(result)


if __name__=='__main__':unittest.main()
