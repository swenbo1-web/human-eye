"""OPT lock adapters honor the existing validated-before-yield contract.

The sealed first-round Service double deliberately remains unchanged. Its
replacement here adds a real threading lock and the same ledger validation
boundary as LiveSpatialService._locked. Two other methods exercise the actual
filesystem-backed live-service lock/runtime load; identity rejection is held
constant because source activation is not the subject of these state tests.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from human_eye_plugin import goal_execution as goal
from human_eye_plugin.live_service import LiveSpatialService
from verification.arm_correction_execution_001 import test_goal as sealed


SealedService=sealed.Service
COUNTS={}


class ValidatedService(SealedService):
    """New test-only adapter, with production's mandatory pre-yield check."""
    def __init__(self,**options):
        super().__init__(**options);self.load_lock=threading.RLock();self.validated_loads=0
    @contextmanager
    def _locked(self):
        with self.load_lock:
            value=deepcopy(self.disk)
            goal.validate_segment_ledger(value)
            self.validated_loads+=1
            yield value,self.runtime


class ArmGoalTests(sealed.ArmGoalTests):
    def setUp(self):
        self.adapter=patch.object(sealed,'Service',ValidatedService);self.adapter.start()
        self.addCleanup(self.adapter.stop)


class ExistingClearanceRegression(sealed.ExistingClearanceRegression):
    pass


class LoadBoundaryTests(unittest.TestCase):
    def test_pending_commit_ack_lost_preserves_barrier_without_rpc(self):
        # Original administrator probe scenario, now with the validated lock.
        service=ValidatedService();service.fail_save=1;service.commit_then_fail=True
        first=goal.run_arm_axial_step(service,sealed.task())
        restarted=ValidatedService(disk=service.disk,host=service.host)
        same=goal.run_arm_axial_step(restarted,sealed.task())
        other=goal.run_arm_axial_step(restarted,sealed.task('arm2'))
        self.assertIs(first['executed'],False)
        self.assertEqual((first['setter_attempts'],first['setter_returns']),(0,0))
        self.assertIsNotNone(service.disk['inflight'])
        self.assertEqual(service.disk['arm_axial_events']['records']['arm1']['state'],'pending')
        self.assertTrue(same['replayed']);self.assertEqual(same['status'],'execution_uncertain')
        self.assertEqual(other['status'],'execution_uncertain')
        self.assertEqual((service.host.calls,service.submitted,restarted.submitted),(0,0,0))
        COUNTS['pending_ack_loss']={'first_loads':service.validated_loads,
            'restart_loads':restarted.validated_loads,'mutation_rpcs':service.host.calls}

    def test_adapter_arm_validation_once_per_loaded_value(self):
        service=ValidatedService();original=goal.validate_arm_axial_ledger
        with patch.object(goal,'validate_arm_axial_ledger',wraps=original) as check:
            result=goal.run_arm_axial_step(service,sealed.task())
            self.assertEqual(result['status'],'satisfied');self.assertEqual(check.call_count,1)
        restarted=ValidatedService(disk=service.disk,host=service.host)
        with patch.object(goal,'validate_arm_axial_ledger',wraps=original) as check:
            result=goal.run_arm_axial_step(restarted,sealed.task())
            self.assertTrue(result['replayed']);self.assertEqual(check.call_count,1)
        self.assertEqual(service.host.calls,1)
        COUNTS['adapter_validation']={'fresh_load':1,'restart_history_load':1,'mutation_rpcs':1}

    @staticmethod
    def real_service(folder,host):
        config=folder/'connector.json'
        if not config.exists():
            root=Path(__file__).resolve().parents[2]
            config.write_text(json.dumps({'schema_version':'1.0','project_root':str(root),
                'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64}),encoding='utf8',newline='\n')
        service=LiveSpatialService(config,host=host)
        service._identity_rejection=lambda:None
        return service

    @staticmethod
    def real_host():
        host=sealed.Host()
        def forbidden(*args,**kwargs):raise AssertionError('No scene capture or rigid setter in arm event test')
        host.capture_scene=forbidden;host.apply_transform=forbidden
        return host

    def test_actual_live_locked_load_validates_arm_ledger_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);host=self.real_host();service=self.real_service(folder,host)
            original=goal.validate_arm_axial_ledger
            with patch.object(goal,'validate_arm_axial_ledger',wraps=original) as check:
                result=goal.run_arm_axial_step(service,sealed.task())
                self.assertEqual(result['status'],'satisfied');self.assertEqual(check.call_count,1)
            restarted=self.real_service(folder,host)
            with patch.object(goal,'validate_arm_axial_ledger',wraps=original) as check:
                replay=goal.run_arm_axial_step(restarted,sealed.task())
                self.assertTrue(replay['replayed']);self.assertEqual(check.call_count,1)
            self.assertEqual(host.calls,1)
            COUNTS['real_live_validation']={'actual_lock_fresh_load':1,'actual_lock_restart_load':1,
                'runtime_construction_import_export':'actual LiveSpatialService and GuardedHostRuntime',
                'mutation_rpcs':host.calls}

    def test_actual_corrupt_persistent_record_rejects_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);host=self.real_host();service=self.real_service(folder,host)
            goal.run_arm_axial_step(service,sealed.task())
            value=json.loads(service.state_path.read_text())
            value['arm_axial_events']['records']['arm1']['request_fingerprint']='0'*64
            service.state_path.write_text(json.dumps(value),encoding='utf8',newline='\n')
            restarted=self.real_service(folder,host)
            original=goal.validate_arm_axial_ledger
            with patch.object(goal,'validate_arm_axial_ledger',wraps=original) as check:
                with self.assertRaisesRegex(ValueError,'arm_event_binding_mismatch'):
                    goal.run_arm_axial_step(restarted,sealed.task('arm2'))
                self.assertEqual(check.call_count,1)
            self.assertEqual(host.calls,1)
            COUNTS['real_corrupt_load']={'validation_calls':1,'additional_mutation_rpcs':0}


if __name__=='__main__':unittest.main()
