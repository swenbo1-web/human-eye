"""Native initial/continuation checks needed before scheduler dispatch."""
import copy
import unittest

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.goal_continuation import inspect_current_clearance,review_continuation
from verification.test_goal_continuation import fixture,digest


class SchedulerNativeReviewTests(unittest.TestCase):
    def test_already_satisfied_is_readonly_and_does_not_require_a_fake_move(self):
        before,current,receipt,policy=fixture(True)
        original=copy.deepcopy(current)
        result=inspect_current_clearance(current,policy)
        self.assertEqual(result['decision'],'already_satisfied')
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['permission_checked'])
        self.assertEqual(current,original)

    def test_unsatisfied_native_goal_is_only_observation(self):
        before,current,receipt,policy=fixture()
        result=inspect_current_clearance(before,policy)
        self.assertEqual(result['decision'],'not_satisfied')
        self.assertFalse(result['execution_authority'])

    def test_unicode_capture_uses_the_actual_router_fingerprint(self):
        before,current,receipt,policy=fixture()
        for envelope in (before,current):
            for mesh in envelope['capture']['meshes']:
                mesh['name']='蓝色零件' if mesh['object_id']=='part' else '灰色底座'
            for obj in envelope['native_scene']['objects']:
                obj['name']='蓝色零件' if obj['object_id']=='part' else '灰色底座'
            envelope['capture_confirmation']=copy.deepcopy(envelope['capture'])
            envelope['native_scene']['revision']='native:'+digest(envelope['native_scene']['objects'])
        receipt['request']['selection_binding']['scene_fingerprint']=_validated_scene(before['capture'])[2]
        receipt['residual']['scene_fingerprint']=_validated_scene(current['capture'])[2]
        result=review_continuation(before,current,receipt,policy)
        self.assertEqual(result['decision'],'eligible_for_fresh_preview',result)
        observed=inspect_current_clearance(before,policy)
        self.assertEqual(observed['capture_fingerprint'],receipt['request']['selection_binding']['scene_fingerprint'])

    def test_mismatched_bracket_cannot_qualify_initial_dispatch(self):
        before,current,receipt,policy=fixture()
        before['capture_confirmation']['revision']='changed'
        result=inspect_current_clearance(before,policy)
        self.assertEqual(result['decision'],'stop')


if __name__=='__main__':unittest.main()
