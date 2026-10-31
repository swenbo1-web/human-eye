"""No-entry proof persistence; parent accounting deliberately stays conservative."""
import copy
import json
import time
import unittest

from human_eye_plugin.blender_host import PREWRITE_REFUSAL_PROTOCOL
from human_eye_plugin.forward_deadline import PROTOCOL,make_deadline,build_refusal
from human_eye_plugin.goal_journal import GoalJournalError
from human_eye_plugin.goal_supervision import GoalSupervisorContext
from verification import test_goal_supervision_service as service_tests


class RefusingSegmentHost(service_tests.MeteredHost):
    prewrite_refusal_protocol=PREWRITE_REFUSAL_PROTOCOL
    forward_deadline_protocol=PROTOCOL
    def __init__(self):
        super().__init__();self.requests=[]
        self.scene['host_identity']['document_epoch']='b'*64
    def apply_transform(self,action,expected_revision,expected_fingerprint=None,request_nonce=None,forward_deadline=None):
        self.requests.append(copy.deepcopy(forward_deadline))
        return build_refusal(forward_deadline,checked_ns=time.perf_counter_ns(),
                             cancelled_event_id=request_nonce+':forward')


class DeadlineReceiptLedgerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=service_tests.GoalSupervisionServiceTests('test_reserved_child_cannot_enter_standalone_route')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.host=RefusingSegmentHost()
        binding={'host_epoch':'a'*32,'document_epoch':'b'*64,'focal_id':'part','reference_id':'base',
                 'object_instances':{'part':'i-part','base':'i-base'}}
        self.fixture.context=GoalSupervisorContext(lambda:'unit-qpc-proof',lambda *args:True,
            self.fixture.meter,clock=time.perf_counter,
            forward_deadline=lambda parent,step:make_deadline(parent,0.,goal_id='goal-1',
                binding=binding,process_id=123))
        self.fixture.service=self.fixture.new_service()
        self.request=self.fixture.prepare()

    def test_known_no_entry_proof_survives_reload_and_readonly_replay(self):
        result=self.fixture.execute(self.request)
        self.assertEqual(result['status'],'blocked')
        state=self.fixture.read()
        self.assertIsNone(state['inflight'])
        raw=state['goal_segments']['records']['child-1']['steps'][0]['result']
        self.assertFalse(raw['host_mutation_started'])
        self.assertEqual(raw['host_prewrite_refusal']['protocol'],PROTOCOL)
        self.assertEqual(raw['forward_deadline'],self.fixture.host.requests[0])
        self.assertFalse(self.fixture.new_service().status()['quarantined'])
        replay=self.fixture.execute(self.request,service=self.fixture.new_service())
        self.assertTrue(replay['historical_receipt'])
        self.assertEqual(len(self.fixture.host.requests),1)
        self.assertEqual(self.fixture.host.calls,0)

    def test_verified_only_parent_freezes_zero_write_step_instead_of_fabricating_a_move(self):
        self.fixture.execute(self.request)
        with self.assertRaises(GoalJournalError):self.fixture.reconcile(service=self.fixture.new_service())
        parent=self.fixture.read()['goal_supervision']['records']['goal-1']
        self.assertEqual(parent['status'],'frozen')
        self.fixture.assert_no_bypass()
        self.assertEqual(self.fixture.host.calls,0)
        self.assertEqual(len(self.fixture.host.requests),1)

    def test_tampered_persisted_proof_is_refused_as_corrupt_not_reloaded_as_known(self):
        self.fixture.execute(self.request)
        state=self.fixture.read()
        entry=state['goal_segments']['records']['child-1']
        # Keep duplicate step/result storage internally equal; semantic proof
        # validation must still reject the altered current request binding.
        entry['steps'][0]['result']['host_prewrite_refusal']['forward_deadline']['request_nonce']='c'*32
        entry['result']['steps']=copy.deepcopy(entry['steps'])
        self.fixture.state.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaises(ValueError):self.fixture.new_service().status()
        self.assertEqual(self.fixture.host.calls,0)


if __name__=='__main__':unittest.main()
