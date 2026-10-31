"""Strict known no-entry refusals at the guarded runtime boundary."""
import copy
import time
import unittest

from human_eye_plugin.forward_deadline import PROTOCOL,make_deadline,build_refusal
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.blender_host import PREWRITE_REFUSAL_PROTOCOL
from verification.test_host_runtime import MutableHost


class DeadlineRefusalHost(MutableHost):
    prewrite_refusal_protocol=PREWRITE_REFUSAL_PROTOCOL
    forward_deadline_protocol=PROTOCOL
    def __init__(self):
        super().__init__();self.requests=[];self.bad_proof=False
    def apply_transform(self,action,expected_revision,expected_fingerprint=None,request_nonce=None,forward_deadline=None):
        self.requests.append(copy.deepcopy(forward_deadline))
        result=build_refusal(forward_deadline,checked_ns=time.perf_counter_ns())
        if self.bad_proof:result['rejection']['mutation_started']=True
        return result


class RuntimeForwardDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.host=DeadlineRefusalHost();self.runtime=GuardedHostRuntime(self.host,quad_size=64)
        self.runtime.before_model(session_id='s',task_instruction='Adjust part clearance.',
            focal_id='part',reference_id='base',messages=[])
        self.action={'focal_id':'part','reference_id':'base','translation':[0,0,.05]}
        self.base=make_deadline(time.perf_counter()+5.,0.,goal_id='goal',process_id=123,
            binding={'host_epoch':'a'*32,'document_epoch':'b'*64,'focal_id':'part','reference_id':'base',
                     'object_instances':{'part':'p1','base':'b1'}})

    def test_exact_expired_proof_is_blocked_without_quarantine_or_setter(self):
        result=self.runtime.execute_action(session_id='s',action=self.action,_host_deadline=self.base)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['executed'])
        self.assertFalse(result['host_mutation_started'])
        self.assertFalse(self.runtime.status['quarantined'])
        self.assertEqual(self.host.calls,0)
        wire=self.host.requests[0]
        self.assertEqual(len(wire['request_nonce']),32)
        self.assertEqual(result['host_prewrite_refusal']['forward_deadline'],wire)
        self.assertEqual(result['forward_deadline'],wire)

    def test_inconsistent_or_forged_zero_write_proof_keeps_uncertainty(self):
        self.host.bad_proof=True
        result=self.runtime.execute_action(session_id='s',action=self.action,_host_deadline=self.base)
        self.assertEqual(result['status'],'host_execution_uncertain')
        self.assertIsNone(result['executed'])
        self.assertTrue(self.runtime.status['quarantined'])
        self.assertEqual(self.host.calls,0)

    def test_unnegotiated_host_does_not_receive_a_deadline_action(self):
        self.host.forward_deadline_protocol=None
        result=self.runtime.execute_action(session_id='s',action=self.action,_host_deadline=self.base)
        self.assertEqual(result['status'],'host_execution_uncertain')
        self.assertEqual(self.host.requests,[])
        self.assertEqual(self.host.calls,0)


if __name__=='__main__':unittest.main()
