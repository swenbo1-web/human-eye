"""Opt-in segment display options traverse actual hook validators without host work."""
import copy
import json
import unittest

from human_eye_plugin.live_hooks import route_live_hook
from verification.test_clearance_segment_hooks import NoSceneHookService,goal_event


class SegmentBriefHookTests(unittest.TestCase):
    def test_display_option_remains_shape_only_for_supported_agents(self):
        for agent in ('codex','claude'):
            for detail in ('full','brief'):
                with self.subTest(agent=agent,detail=detail):
                    event=goal_event()
                    event['tool_input']['response_detail']=detail
                    before=copy.deepcopy(event)
                    service=NoSceneHookService()
                    output=route_live_hook(event,service,agent=agent)['hookSpecificOutput']
                    facts=json.loads(output['additionalContext'])
                    self.assertNotIn('permissionDecision',output)
                    self.assertEqual(facts['human_eye_live'],'goal_request_structure_valid')
                    self.assertTrue(facts['execute_requested'])
                    self.assertTrue(facts['inner_execution_gate_required'])
                    self.assertFalse(facts['scene_read'])
                    self.assertFalse(facts['engine_invoked'])
                    self.assertFalse(facts['execution_authority'])
                    self.assertFalse(facts['retry_authorized'])
                    self.assertEqual(event,before)

    def test_invalid_display_option_is_denied_before_host_work(self):
        for agent in ('codex','claude'):
            for detail in (None,False,0,[],{},'short','BRIEF'):
                with self.subTest(agent=agent,detail=repr(detail)):
                    event=goal_event()
                    event['tool_input']['response_detail']=detail
                    result=route_live_hook(event,NoSceneHookService(),agent=agent)
                    self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')


if __name__=='__main__':
    unittest.main()
