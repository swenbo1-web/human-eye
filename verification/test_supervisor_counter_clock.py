"""Explicit managed clock propagation, without relabelling legacy timestamps."""
import unittest
from unittest.mock import patch

from human_eye_plugin.goal_supervision import GoalSupervisorContext
from human_eye_plugin.live_service import LiveSpatialService
from verification import test_goal_supervision_service as service_tests


class SupervisorCounterClockTests(unittest.TestCase):
    def setUp(self):
        self.fixture=service_tests.GoalSupervisionServiceTests('test_reserved_child_cannot_enter_standalone_route')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.now=[1000.]
        self.context=GoalSupervisorContext(lambda:'explicit-test-counter-v1',lambda *args:True,
            self.fixture.meter,clock=lambda:self.now[0])
        self.fixture.service=self.service()

    def service(self):
        return LiveSpatialService(self.fixture.config,host=self.fixture.host,supervisor_context=self.context)

    def test_journal_segment_and_precommit_share_the_explicit_clock(self):
        with patch('human_eye_plugin.goal_supervision.time.monotonic',return_value=10.):
            request=self.fixture.prepare()
            result=self.fixture.execute(request)
            self.assertEqual(result['status'],'satisfied')
            final=self.fixture.reconcile(service=self.service())
        self.assertEqual(final['started_monotonic'],1000.)
        self.assertEqual(final['deadline_monotonic'],1030.)
        self.assertEqual(final['confirmed_steps'],self.fixture.host.calls)

    def test_explicit_clock_expiry_stops_loop_and_preserves_late_actual_accounting(self):
        with patch('human_eye_plugin.goal_supervision.time.monotonic',return_value=10.):
            request=self.fixture.prepare()
            self.fixture.host.after_mutation=lambda host:self.now.__setitem__(0,1031.)
            result=self.fixture.execute(request)
            self.assertEqual(self.fixture.host.calls,1)
            self.assertEqual(result['status'],'review_required')
            final=self.fixture.reconcile(service=self.service())
        self.assertTrue(final['late_accounted_only'])
        self.assertEqual(final['confirmed_steps'],1)
        self.assertEqual(final['stopped_reason'],'goal_time_budget_exhausted')

    def test_optional_clock_and_deadline_binding_require_trusted_callables(self):
        with self.assertRaises(ValueError):
            GoalSupervisorContext(lambda:'x',lambda *args:True,lambda *args:{},clock=1000.)
        with self.assertRaises(ValueError):
            GoalSupervisorContext(lambda:'x',lambda *args:True,lambda *args:{},forward_deadline=lambda *args:{})


if __name__=='__main__':unittest.main()
