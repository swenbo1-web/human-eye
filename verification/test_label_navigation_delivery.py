"""Final-pixel NAV label evidence and opaque chrome delivery boundaries."""
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image,ImageDraw

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import scene_rendering as rendering
from human_eye_plugin.task_labels import build_task_label_plan
from verification.test_auto_router import box


def navigation_fixture():
    rows=[box('reference',[0,0,-.02],[.14,.12,.04]),
          box('focus',[0,0,.024],[.06,.05,.04],True)]
    identities=[]
    for i,(x,y) in enumerate([(-.6,-1.),(0,-1.),(.6,-1.),(-.6,1.),(0,1.),(.6,1.)]):
        identity='peripheral-'+str(i);identities.append(identity)
        rows.append(box(identity,[x,y,.025],[.12,.12,.05]))
    return [MeshEntity3D.from_dict(row) for row in rows],identities


class LabelNavigationDeliveryTests(unittest.TestCase):
    def render_navigation(self,size,*,labels=True):
        meshes,identities=navigation_fixture()
        plan=build_task_label_plan(meshes,focal_id='focus',reference_id='reference',
            visual_focus_ids=identities) if labels else None
        original_nav=rendering._navigation;original_raster=rendering._raster_with_owners
        chrome=[];raw=[]
        def capture_nav(image,*args,**kwargs):
            result=original_nav(image,*args,**kwargs);chrome.append(image.copy());return result
        def capture_raw(*args,**kwargs):
            result=original_raster(*args,**kwargs);raw.append(tuple(v.copy() for v in result));return result
        with patch.object(rendering,'_navigation',side_effect=capture_nav),patch.object(rendering,'_raster_with_owners',side_effect=capture_raw):
            canvas,meta=rendering.render_scene_canvas(meshes,size,focal_id='focus',reference_id='reference',label_plan=plan)
        self.assertEqual(meta['view_layout'],'navigation_workspace_target')
        self.assertEqual(len(chrome),1)
        return np.asarray(canvas)[:size,:size],meta['views'][0],np.asarray(chrome[0]),raw[0][2],meshes,identities

    def assert_actual_glyphs(self,final,view):
        size=final.shape[0]
        self.assertTrue(view['projected_labels'],'A final-pixel test needs actual glyph samples')
        for row in view['projected_labels']:
            box=row['label_box_px'];text=row.get('display_label',row['stable_label'])
            expected=Image.new('RGB',(size,size));draw=ImageDraw.Draw(expected)
            draw.rectangle(box,fill=(18,22,30),outline=(150,145,110))
            draw.text((box[0]+3,box[1]),text,fill=(255,245,180))
            alpha=Image.new('L',(size,size));ImageDraw.Draw(alpha).text((box[0]+3,box[1]),text,fill=255)
            mask=np.asarray(alpha)>0
            self.assertTrue(mask.any(),text)
            self.assertTrue(np.array_equal(final[mask],np.asarray(expected)[mask]),
                'Reported drawn glyph must survive every later NAV marker/footer layer: '+row['object_id'])

    def test_requested_nav_glyphs_survive_final_png_at_three_footer_resolutions(self):
        for size in [128,256,384]:
            with self.subTest(size=size):
                final,view,_,_,_,_=self.render_navigation(size)
                self.assert_actual_glyphs(final,view)

    def test_legacy_nav_glyphs_also_survive_final_png(self):
        for size in [128,256,384]:
            with self.subTest(size=size):
                final,view,_,_,_,_=self.render_navigation(size,labels=False)
                self.assert_actual_glyphs(final,view)

    def test_navigation_footer_text_is_not_overwritten_by_relocated_labels(self):
        for size in [128,256,384]:
            with self.subTest(size=size):
                final,_,chrome,_,_,_=self.render_navigation(size)
                interior=(slice(size-43,size-15),slice(1,size-1))
                self.assertTrue(np.array_equal(final[interior],chrome[interior]))

    def test_all_focus_receipts_match_actual_current_safe_anchors(self):
        for size in [96,128,256,384]:
            with self.subTest(size=size):
                final,view,_,owners,meshes,ids=self.render_navigation(size)
                coverage=view['label_layout']['visual_focus_coverage']
                drawn=set(coverage['drawn_object_ids']);undrawn={r['object_id'] for r in coverage['undrawn_objects']}
                self.assertEqual(drawn|undrawn,set(ids));self.assertFalse(drawn&undrawn)
                top=size-43 if size>=128 else size-15
                for row in view['projected_labels']:
                    x,y=row['projected_center_px'];index=next(i for i,m in enumerate(meshes) if m.object_id==row['object_id'])
                    self.assertEqual(owners[y,x],index)
                    self.assertGreaterEqual(y,17);self.assertLess(y,top)
                    self.assertGreaterEqual(row['label_box_px'][1],19)
                    self.assertLess(row['label_box_px'][3],top)
                self.assert_actual_glyphs(final,view)

    def test_first_safe_surface_row_17_is_preserved_instead_of_discarded(self):
        _,view,_,_,_,_=self.render_navigation(128)
        byid={r['object_id']:r for r in view['projected_labels']}
        for identity in ['peripheral-3','peripheral-4','peripheral-5']:
            self.assertIn(identity,byid,'Surface row17 is below the actual inclusive title end16')
            self.assertEqual(byid[identity]['projected_center_px'][1],17)

    def test_small_navigation_never_reports_an_anchor_covered_by_title(self):
        final,view,_,_,_,_=self.render_navigation(96)
        for row in view['projected_labels']:
            self.assertGreaterEqual(row['projected_center_px'][1],17)
        self.assert_actual_glyphs(final,view)


if __name__=='__main__':unittest.main()
