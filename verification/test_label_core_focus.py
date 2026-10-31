"""Core visual requests retain delivery evidence without consuming related slots."""
import copy
import unittest

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.task_labels import (build_task_label_plan, validate_task_label_plan,
                                          task_display_label)
from human_eye_plugin.scene_rendering import render_scene_canvas, _task_label_coverage_summary
from verification.test_auto_router import box


def ids(*extra):
    return [{'object_id': identity} for identity in ['focus','reference',*extra]]

def make_plan(*extra, visual=(), **changes):
    return build_task_label_plan(ids(*extra), focal_id='focus', reference_id='reference',
        visual_focus_ids=visual, scene_revision='core-focus-r1', **changes)

def checked(plan, *extra):
    return validate_task_label_plan(plan,ids(*extra),focal_id='focus',reference_id='reference')

def hidden_meshes():
    return [MeshEntity3D.from_dict(box('focus',[0,0,0],[.2,.2,.2],True)),
            MeshEntity3D.from_dict(box('reference',[0,0,0],[1,1,1]))]

def visible_meshes():
    return [MeshEntity3D.from_dict(box('focus',[0,0,.024],[.08,.06,.04],True)),
            MeshEntity3D.from_dict(box('reference',[0,0,-.02],[.14,.12,.04]))]

def render(meshes, plan, size=256):
    return render_scene_canvas(meshes,size,focal_id='focus',reference_id='reference',label_plan=plan)


class CoreVisualFocusTests(unittest.TestCase):
    def test_core_only_request_is_retained_but_never_promoted_as_related(self):
        plan=make_plan(visual=['reference','focus'])
        self.assertEqual(plan['visual_focus_object_ids'],['focus','reference'])
        self.assertEqual(plan['max_related_labels'],2)
        self.assertEqual(plan['related_object_ids'],[])
        self.assertEqual(plan['related_candidate_count'],0)
        self.assertEqual(plan['candidate_reason_counts'],{})
        checked(plan)

    def test_mixed_six_requests_use_only_four_related_slots(self):
        plan=make_plan('a','b','c','d',visual=['reference','d','focus','b','a','c'])
        self.assertEqual(plan['visual_focus_object_ids'],['a','b','c','d','focus','reference'])
        self.assertEqual(plan['max_related_labels'],4)
        self.assertEqual(plan['related_object_ids'],list('abcd'))
        self.assertEqual(plan['candidate_reason_counts'],{'explicit_visual_focus':4})
        checked(plan,'a','b','c','d')

    def test_core_requests_do_not_bypass_total_six_request_limit(self):
        with self.assertRaises(ValueError):
            make_plan(*'abcde',visual=['focus','reference',*'abcde'])

    def test_validation_uses_noncore_count_and_detaches_complete_request(self):
        plan=make_plan(*'abcd',visual=['focus','reference',*'abcd'])
        altered=copy.deepcopy(plan);altered['max_related_labels']=6
        with self.assertRaises(ValueError):checked(altered,*'abcd')
        detached=checked(plan,*'abcd');detached['visual_focus_object_ids'].clear()
        self.assertEqual(len(plan['visual_focus_object_ids']),6)

    def test_unknown_deleted_and_duplicate_core_requests_fail(self):
        for visual in [['focus','focus'],['reference','missing'],['removed']]:
            with self.subTest(visual=visual),self.assertRaises(ValueError):
                make_plan(visual=visual)

    def test_role_change_keeps_full_request_identity_and_changes_only_display_role(self):
        objects=ids('a')
        before=build_task_label_plan(objects,focal_id='focus',reference_id='reference',
            visual_focus_ids=['reference'])
        after=build_task_label_plan(objects,focal_id='focus',reference_id='a',
            visual_focus_ids=['reference'])
        self.assertEqual(before['visual_focus_object_ids'],['reference'])
        self.assertEqual(after['visual_focus_object_ids'],['reference'])
        self.assertEqual(task_display_label('reference',before),'B')
        self.assertTrue(task_display_label('reference',after).startswith('R'))
        self.assertEqual(after['related_object_ids'],['reference'])
        validate_task_label_plan(after,objects,focal_id='focus',reference_id='a')

    def test_fully_occluded_requested_core_has_explicit_missing_receipt_in_every_view(self):
        meshes=hidden_meshes();plan=make_plan(visual=['focus'])
        _,metadata=render(meshes,plan)
        report=_task_label_coverage_summary(metadata)
        self.assertEqual(report['selection_mode'],'explicit_visual_focus')
        self.assertEqual(report['visual_focus_count'],1)
        self.assertEqual(report['visual_focus_drawn_count'],0)
        self.assertEqual(report['visual_focus_not_drawn_ids'],['focus'])
        for view in metadata['views']:
            self.assertEqual(view['object_visible_pixels']['focus'],0)
            coverage=view['label_layout']['visual_focus_coverage']
            self.assertEqual(coverage['drawn_object_ids'],[])
            self.assertEqual(coverage['undrawn_objects'],[{'object_id':'focus','reason':'not_surface_visible'}])

    def test_visible_core_only_focus_changes_receipt_without_changing_default_pixels(self):
        meshes=visible_meshes()
        baseline,old=render(meshes,make_plan())
        requested,new=render(meshes,make_plan(visual=['focus','reference']))
        self.assertTrue(np.array_equal(np.asarray(baseline),np.asarray(requested)))
        self.assertEqual(old['task_labels']['related_object_ids'],new['task_labels']['related_object_ids'])
        report=_task_label_coverage_summary(new)
        self.assertEqual(report['visual_focus_count'],2)
        self.assertEqual(report['visual_focus_drawn_count'],2)
        self.assertEqual(report['visual_focus_not_drawn_ids'],[])

    def test_tiny_view_reports_both_requested_core_ids_without_fake_labels(self):
        _,metadata=render(visible_meshes(),make_plan(visual=['focus','reference']),64)
        report=_task_label_coverage_summary(metadata)
        self.assertEqual(report['visual_focus_not_drawn_ids'],['focus','reference'])
        for view in metadata['views']:
            coverage=view['label_layout']['visual_focus_coverage']
            self.assertEqual(coverage['drawn_object_ids'],[])
            self.assertEqual({row['object_id'] for row in coverage['undrawn_objects']},{'focus','reference'})
            self.assertTrue(all(row['reason'] in {'view_too_small','not_surface_visible',
                'insufficient_surface_pixels'} for row in coverage['undrawn_objects']))


if __name__=='__main__':unittest.main()
