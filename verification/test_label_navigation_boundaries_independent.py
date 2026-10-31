"""Independent NAV presentation-band and complete visual-request boundaries."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin.task_labels import build_task_label_plan, validate_task_label_plan
from verification.test_auto_router import box


def controlled_layer(owners, *, region, contact=False, focus=('focus',)):
    """Use supplied current-owner pixels, never manufacture a geometry ROI."""
    meshes=[SimpleNamespace(object_id=identity,mark_label='#'+identity)
            for identity in ['focus','reference']]
    plan=build_task_label_plan(meshes,focal_id='focus',reference_id='reference',visual_focus_ids=list(focus))
    metadata={'name':'Q4 CONTACT' if contact else 'Q1 NAV XY','projection':'orthographic',
              'm_per_pixel':.001,'target_object_ids':['focus','reference']}
    before=owners.copy();picture=Image.new('RGB',(len(owners),len(owners)),(18,22,30))
    rendering._annotate(picture,meshes,None,None,metadata,owners,label_plan=plan,
                        navigation_reserved_region=region)
    np.testing.assert_array_equal(owners,before)
    return picture,metadata,plan

def reference_patch(owners):
    owners[30:34,12:16]=1


class IndependentNavigationBoundaryTests(unittest.TestCase):
    def test_real_96px_north_nav_object_has_no_false_title_covered_anchor(self):
        raw=[box('focus',[0,0,.024],[.08,.06,.04],True),
             box('reference',[0,0,-.02],[.14,.12,.04]),
             box('far',[0,10,.5],[1,1,1])]
        meshes=[MeshEntity3D.from_dict(row) for row in raw]
        before=copy.deepcopy([mesh.to_dict() for mesh in meshes])
        plan=build_task_label_plan(meshes,focal_id='focus',reference_id='reference',visual_focus_ids=['far'])
        _,metadata=rendering.render_scene_canvas(meshes,96,focal_id='focus',reference_id='reference',label_plan=plan)
        self.assertEqual(metadata['view_layout'],'navigation_workspace_target')
        q1=metadata['views'][0]
        self.assertEqual(q1['object_visible_pixels']['far'],49)
        self.assertEqual(q1['label_layout']['navigation_reserved_region_px'],[0,81,96,96])
        coverage=q1['label_layout']['visual_focus_coverage']
        self.assertEqual(coverage['drawn_object_ids'],[])
        self.assertEqual(coverage['undrawn_objects'],[{'object_id':'far',
            'reason':'no_surface_anchor_outside_navigation_overlay'}])
        self.assertTrue(all(row['object_id']!='far' for row in q1['projected_labels']))
        self.assertEqual(before,[mesh.to_dict() for mesh in meshes])
        self.assertFalse(q1['labels_certify_visibility'])

    def test_row17_is_safe_and_reselected_from_real_current_owner_pixels(self):
        owners=np.full((128,128),-1,dtype=np.int32)
        owners[4:8,50:60]=0
        owners[17,50:58]=0
        reference_patch(owners)
        _,metadata,_=controlled_layer(owners,region=(0,85,128,113))
        row=next(row for row in metadata['projected_labels'] if row['object_id']=='focus')
        x,y=row['projected_center_px']
        self.assertEqual(y,17)
        self.assertEqual(owners[y,x],0)
        self.assertGreaterEqual(row['label_box_px'][1],19)
        self.assertEqual(metadata['label_layout']['visual_focus_coverage']['drawn_object_ids'],['focus'])

    def test_title_row16_is_opaque_and_no_safe_pixels_means_explicit_omission(self):
        owners=np.full((128,128),-1,dtype=np.int32)
        owners[16,50:60]=0
        reference_patch(owners)
        picture,metadata,_=controlled_layer(owners,region=(0,85,128,113))
        self.assertEqual(metadata['object_visible_pixels']['focus'],10)
        self.assertEqual(metadata['label_layout']['visual_focus_coverage']['undrawn_objects'],[
            {'object_id':'focus','reason':'no_surface_anchor_outside_navigation_overlay'}])
        self.assertTrue(all(row['object_id']!='focus' for row in metadata['projected_labels']))
        self.assertEqual(picture.getpixel((54,16)),(28,34,46))

    def test_seven_safe_pixels_do_not_invent_an_eighth_surface_anchor(self):
        owners=np.full((128,128),-1,dtype=np.int32)
        owners[4:8,50:60]=0
        owners[17,50:57]=0
        reference_patch(owners)
        _,metadata,_=controlled_layer(owners,region=(0,85,128,113))
        self.assertEqual(metadata['object_visible_pixels']['focus'],47)
        coverage=metadata['label_layout']['visual_focus_coverage']
        self.assertEqual(coverage['drawn_object_ids'],[])
        self.assertEqual(coverage['undrawn_objects'][0]['reason'],'no_surface_anchor_outside_navigation_overlay')

    def test_existing_safe_row17_anchor_does_not_move_to_row19(self):
        owners=np.full((128,128),-1,dtype=np.int32)
        owners[16:19,50:59]=0
        reference_patch(owners)
        _,baseline,_=controlled_layer(owners,region=None)
        _,navigation,_=controlled_layer(owners,region=(0,85,128,113))
        a=next(row for row in baseline['projected_labels'] if row['object_id']=='focus')
        b=next(row for row in navigation['projected_labels'] if row['object_id']=='focus')
        self.assertEqual(a['projected_center_px'][1],17)
        self.assertEqual(a['projected_center_px'],b['projected_center_px'])

    def test_footer_top_is_excluded_but_preceding_row_can_supply_anchor(self):
        for size in [128,256]:
            top=size-43
            for row_y,drawn in [(top-1,True),(top,False)]:
                with self.subTest(size=size,row_y=row_y):
                    owners=np.full((size,size),-1,dtype=np.int32)
                    owners[row_y,50:60]=0;reference_patch(owners)
                    _,metadata,_=controlled_layer(owners,region=(0,top,size,size-15))
                    coverage=metadata['label_layout']['visual_focus_coverage']
                    self.assertEqual(coverage['drawn_object_ids'],['focus'] if drawn else [])
                    if drawn:
                        actual=next(row for row in metadata['projected_labels'] if row['object_id']=='focus')
                        self.assertEqual(actual['projected_center_px'][1],top-1)
                        self.assertLess(actual['label_box_px'][3],top)
                    else:self.assertEqual(coverage['undrawn_objects'][0]['reason'],
                                          'no_surface_anchor_outside_navigation_overlay')

    def test_64px_navigation_refuses_labels_instead_of_using_a_fake_small_roi(self):
        owners=np.full((64,64),-1,dtype=np.int32)
        owners[25:28,30:33]=0;owners[30:33,10:13]=1
        _,metadata,plan=controlled_layer(owners,region=(0,49,64,64),focus=('focus','reference'))
        self.assertEqual(metadata['projected_labels'],[])
        coverage=metadata['label_layout']['visual_focus_coverage']
        self.assertEqual(coverage['drawn_object_ids'],[])
        self.assertEqual({row['reason'] for row in coverage['undrawn_objects']},{'view_too_small'})
        summary=rendering._task_label_coverage_summary({'task_labels':plan,'views':[metadata]})
        self.assertEqual(summary['visual_focus_count'],2)
        self.assertEqual(summary['visual_focus_not_drawn_ids'],['focus','reference'])
        self.assertFalse(summary['execution_authority'])

    def test_contact_does_not_invoke_navigation_filter_or_change_core_only_layout(self):
        owners=np.full((128,128),-1,dtype=np.int32)
        owners[45:50,50:55]=0;owners[80:85,90:95]=1
        with patch.object(rendering,'_navigation',side_effect=AssertionError('CONTACT must not draw navigation')):
            plain,plain_meta,_=controlled_layer(owners,region=None,contact=True,focus=())
            requested,requested_meta,_=controlled_layer(owners,region=None,contact=True,
                                                      focus=('focus','reference'))
        np.testing.assert_array_equal(np.asarray(plain),np.asarray(requested))
        self.assertNotIn('navigation_reserved_region_px',requested_meta['label_layout'])
        self.assertEqual(plain_meta['projected_labels'],requested_meta['projected_labels'])
        self.assertEqual(requested_meta['label_layout']['visual_focus_coverage']['drawn_object_ids'],
                         ['focus','reference'])

    def test_v2_plan_is_rejected_instead_of_being_reinterpreted_as_full_request(self):
        objects=[{'object_id':'focus'},{'object_id':'reference'}]
        plan=build_task_label_plan(objects,focal_id='focus',reference_id='reference',
                                   visual_focus_ids=['focus'])
        self.assertEqual(plan['visual_focus_object_ids'],['focus'])
        plan['schema_revision']='observation-task-labels-v2-visual-focus-20261027'
        with self.assertRaises(ValueError):
            validate_task_label_plan(plan,objects,focal_id='focus',reference_id='reference')


if __name__=='__main__':unittest.main()
