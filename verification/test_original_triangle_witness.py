"""Original finite support intent survives only an independently proved foot.

Discovery selects a representative per exact plane, whereas task intent may
select another original triangle. These tests use elementary flat geometry,
not candidate count/rounded normals, to distinguish legal and illegal cases.
"""
from __future__ import annotations

import copy,math,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin import goal_scheduler as scheduler
from human_eye_plugin.support_plane_discovery import discover_support_planes
from human_eye_plugin.task_authority import ClearanceTaskSpec
from verification.test_support_plane_candidate import flat_scene,tetra_scene


class OriginalTriangleWitnessTests(unittest.TestCase):
    def discover(self,scene,original=3,observation=None):
        spec=ClearanceTaskSpec('part','base',reference_triangle_index=original)
        raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        if observation is None:observation={'support_plane_discovery':raw}
        owner=scheduler.OwnedGoalScheduler.__new__(scheduler.OwnedGoalScheduler)
        owner.service=SimpleNamespace(observe=Mock(return_value=observation))
        envelope={'capture':copy.deepcopy(scene)}
        result=owner._discover(spec,envelope,'witness-read')
        return result,raw,spec,owner

    def test_explicit_original_three_retained_when_representative_two_has_own_foot(self):
        scene=flat_scene();before=copy.deepcopy(scene)
        result,raw,spec,owner=self.discover(scene)
        self.assertEqual(raw['candidates'][0]['selector']['reference_triangle_index'],2)
        self.assertEqual(result['reference_triangle_index'],3)
        self.assertEqual(spec.reference_triangle_index,3)
        self.assertEqual(result['selection_binding'],raw['candidates'][0]['selector']['selection_binding'])
        self.assertEqual(scene,before)
        self.assertIsNot(result,raw['candidates'][0]['selector'])
        self.assertIsNot(result['selection_binding'],raw['candidates'][0]['selector']['selection_binding'])
        owner.service.observe.assert_called_once()

    def test_none_and_matching_original_keep_existing_fast_path(self):
        for original in (None,2):
            with self.subTest(original=original),patch.object(scheduler,'_retain_original_triangle') as proof:
                result,raw,_,_=self.discover(flat_scene(),original)
                self.assertEqual(result,raw['candidates'][0]['selector']);proof.assert_not_called()

    def test_other_half_triangle_does_not_become_original_witness_from_coplanarity(self):
        scene=tetra_scene((-.05,.05,.104))
        raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        self.assertEqual(raw['candidates'][0]['selector']['reference_triangle_index'],3)
        self.assertEqual(raw['candidates'][0]['coplanar_triangle_count'],2)
        with self.assertRaisesRegex(ValueError,'original_triangle_no_exact_support_witness:minimum_support_projects_outside_original_triangle'):
            self.discover(scene,2)

    def test_exact_edge_belongs_to_both_triangles_without_tolerance(self):
        result,raw,_,_=self.discover(tetra_scene((.05,.05,.104)),3)
        self.assertEqual(raw['candidates'][0]['selector']['reference_triangle_index'],2)
        self.assertEqual(result['reference_triangle_index'],3)

    def test_one_ulp_outside_original_finite_triangle_remains_refused(self):
        scene=tetra_scene((math.nextafter(.05,0.),.05,.104))
        with self.assertRaisesRegex(ValueError,'original_triangle_no_exact_support_witness'):
            self.discover(scene,2)

    def test_forged_count_and_normal_never_replace_original_geometry(self):
        scene=tetra_scene((-.05,.05,.104))
        raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        raw['candidates'][0].update(coplanar_triangle_count=1000000,
            plane_normal_world=[0.,0.,1.],clearance_m=.004)
        with self.assertRaisesRegex(ValueError,'original_triangle_no_exact_support_witness'):
            self.discover(scene,2,{'support_plane_discovery':raw})

    def test_forged_non_support_representative_is_reproved_and_refused(self):
        scene=flat_scene();raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        raw['candidates'][0]['selector']['reference_triangle_index']=0
        with self.assertRaisesRegex(ValueError,'discovered_triangle_no_exact_support_witness'):
            self.discover(scene,3,{'support_plane_discovery':raw})

    def test_original_and_representative_indices_are_not_coerced_or_wrapped(self):
        scene=flat_scene();raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        for index in (True,False,-1,1.5,'2',None,1000000):
            bad=copy.deepcopy(raw);bad['candidates'][0]['selector']['reference_triangle_index']=index
            with self.subTest(index=index),self.assertRaises(ValueError):
                self.discover(scene,3,{'support_plane_discovery':bad})
        with self.assertRaisesRegex(ValueError,'original_triangle_outside_original_mesh'):
            self.discover(scene,999999)

    def test_stale_fingerprint_revision_or_pair_refused_before_mismatch_proof(self):
        scene=flat_scene();raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        for key,value in [('scene_revision','older'),('scene_fingerprint','0'*64),
                          ('focal_id','other'),('reference_id','other')]:
            bad=copy.deepcopy(raw);bad['candidates'][0]['selector']['selection_binding'][key]=value
            with self.subTest(key=key),patch.object(scheduler,'_retain_original_triangle') as proof:
                with self.assertRaisesRegex(ValueError,'discovery_not_original_fresh_capture'):
                    self.discover(scene,3,{'support_plane_discovery':bad})
                proof.assert_not_called()

    def test_changed_same_revision_geometry_refuses_stale_selector_binding(self):
        scene=flat_scene();raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        scene['meshes'][0]['faces'][2],scene['meshes'][0]['faces'][3]=scene['meshes'][0]['faces'][3],scene['meshes'][0]['faces'][2]
        with self.assertRaisesRegex(ValueError,'discovery_not_original_fresh_capture'):
            self.discover(scene,3,{'support_plane_discovery':raw})

    def test_ambiguous_incomplete_or_omitted_discovery_is_still_refused(self):
        scene=flat_scene();raw=discover_support_planes(scene,'part','base',{'direction_world':[0,0,1]})
        for changes in ({'status':'unknown'},{'ambiguous':True},{'omitted_candidate_count':1},
                        {'candidates':[]},{'candidates':raw['candidates']*2}):
            bad=copy.deepcopy(raw);bad.update(changes)
            with self.subTest(changes=changes),patch.object(scheduler,'_retain_original_triangle') as proof:
                with self.assertRaisesRegex(ValueError,'unique_complete_support_required'):
                    self.discover(scene,3,{'support_plane_discovery':bad})
                proof.assert_not_called()

    def test_resource_limit_precedes_expensive_rational_geometry(self):
        capture=flat_scene();capture['meshes'][1]['vertices']*=10
        selector={'reference_triangle_index':2,'selection_binding':{}}
        spec=ClearanceTaskSpec('part','base',reference_triangle_index=3)
        with patch('human_eye_plugin.support_plane_candidate._rational_mesh') as conversion:
            with self.assertRaisesRegex(ValueError,'original_triangle_resource_limit'):
                scheduler._retain_original_triangle(capture,[],spec,selector)
            conversion.assert_not_called()


if __name__=='__main__':unittest.main()
