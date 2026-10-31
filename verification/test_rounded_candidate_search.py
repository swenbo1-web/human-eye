"""Finite represented-geometry regression for inward rounded proposals.

The stored native capture is an immutable real fixture. Failure-injection
tests below exercise refusal control flow, not independent physical evidence.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import support_plane_candidate as module
from human_eye_plugin.auto_router import _validated_scene
from verification.test_support_plane_candidate import flat_scene, request as simple_request

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'verification/fixes/20261030_v21_goal_scheduler/owned_work/run_001/lifecycle'
BEFORE=ROOT/'verification/fixes/20261030_v21_goal_boundary/before/human_eye_plugin/support_plane_candidate.py'


def fixture():
    scene=json.loads((OLD/'BEFORE_TASK_TWO.json').read_text(encoding='utf8'))['capture']
    state=json.loads((OLD/'state.json').read_text(encoding='utf8'))
    full=next(child['request'] for parent in state['goal_supervision']['records'].values()
        for child in parent['children'] if child['request']['target_clearance_m']==.0015)
    return scene,{key:value for key,value in full.items() if key in module._ALLOWED}


def baseline():
    name='human_eye_plugin._before_rounded_candidate_search'
    spec=importlib.util.spec_from_file_location(name,BEFORE)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value
    spec.loader.exec_module(value)
    return value


def represented_support(scene, request, translation=None):
    """Independent exact plane heights on the supplied rounded coordinates."""
    byid={mesh['object_id']:mesh for mesh in scene['meshes']}
    a,b,c=(byid[request['reference_id']]['vertices'][i]
        for i in byid[request['reference_id']]['faces'][request['reference_triangle_index']])
    fraction=lambda vector:tuple(Fraction(float(x)) for x in vector)
    a,b,c=map(fraction,(a,b,c))
    sub=lambda first,second:tuple(x-y for x,y in zip(first,second))
    u,v=sub(b,a),sub(c,a)
    normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    vertices=np.asarray(byid[request['focal_id']]['vertices'],dtype=np.float64)
    if translation is not None:vertices=vertices+np.asarray(translation,dtype=np.float64)
    heights=[sum(n*x for n,x in zip(normal,sub(fraction(vertex),a))) for vertex in vertices]
    return [i for i,height in enumerate(heights) if height==min(heights)]


class RoundedCandidateSearchTests(unittest.TestCase):
    def test_real_1mm_to_1_5mm_fixture_recovers_without_changing_exact_feature(self):
        scene,request=fixture();result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'candidate',result)
        search=result['rounded_proposal_search']
        self.assertEqual(search['original_support_vertex_indices'],[0,1,2,3])
        self.assertEqual(search['first_candidate_support_vertex_indices'],[0,3])
        self.assertEqual(search['accepted_attempt'],1)
        self.assertEqual(represented_support(scene,request,result['candidate']['translation']),
                         represented_support(scene,request))
        self.assertLessEqual(abs(result['candidate_clearance_m']-.0015),1e-6)
        self.assertEqual(result['candidate_certificate']['predicate_tolerance_m'],0.)
        self.assertEqual(result['candidate_certificate']['reference_triangle_index'],2)
        self.assertFalse(result['execution_authority'])

    def test_preserved_baseline_rejects_exact_same_native_fixture(self):
        scene,request=fixture();old=baseline().solve_support_plane_candidate(scene,request)
        self.assertEqual(old['status'],'feature_changed')
        self.assertEqual(old['reason_codes'],['contact_feature_changed_after_rounded_translation'])
        self.assertIsNone(old['candidate'])

    def test_inward_request_and_actual_motion_remain_under_original_budget(self):
        scene,request=fixture();before=copy.deepcopy((scene,request))
        result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'candidate',result)
        search=result['rounded_proposal_search'];delta=result['candidate']['translation']
        self.assertLess(math.hypot(*delta),abs(search['original_scalar_m']))
        limit=min(request['max_step_translation_m'],request['max_total_translation_m'])
        self.assertLessEqual(math.hypot(*delta),limit)
        focal=next(mesh for mesh in scene['meshes'] if mesh['object_id']==request['focal_id'])
        actual=max(math.dist(a,b) for a,b in zip(np.asarray(focal['vertices'])+delta,focal['vertices']))
        self.assertLessEqual(actual,limit)
        self.assertEqual(actual,result['actual_max_vertex_translation_m'])
        self.assertLess(result['predicted_absolute_error_m'],result['absolute_error_m'])
        self.assertEqual((scene,request),before)
        result['rounded_proposal_search']['original_support_vertex_indices'].clear()
        self.assertEqual((scene,request),before)

    def test_ordinary_success_output_remains_unchanged_without_search(self):
        scene,request=flat_scene(),simple_request()
        old=baseline().solve_support_plane_candidate(scene,request)
        new=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(old,new)
        self.assertNotIn('rounded_proposal_search',new)

    def test_already_satisfied_does_not_start_proposal_search(self):
        scene,request=fixture();request['target_clearance_m']=.001
        result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'goal_satisfied')
        self.assertNotIn('rounded_proposal_search',result)
        self.assertIsNone(result['candidate'])

    def test_wrong_expected_feature_is_not_rebound(self):
        scene,request=fixture()
        result=module.solve_support_plane_candidate(scene,request,expected_feature_signature='0'*64)
        self.assertEqual(result['status'],'feature_changed')
        self.assertEqual(result['reason_codes'],['contact_feature_changed'])
        self.assertNotIn('rounded_proposal_search',result)
        self.assertIsNone(result['candidate'])

    def test_no_search_for_unsupported_or_degenerate_original_geometry(self):
        for change in ('wrong_face','open','thin_degenerate'):
            scene,request=fixture()
            focal=next(mesh for mesh in scene['meshes'] if mesh['object_id']==request['focal_id'])
            if change=='wrong_face':request['reference_triangle_index']=0
            elif change=='open':focal['faces'].pop()
            else:focal['vertices'][4]=list(focal['vertices'][0])
            with self.subTest(change=change):
                result=module.solve_support_plane_candidate(scene,request)
                self.assertNotEqual(result['status'],'candidate',result)
                self.assertNotIn('rounded_proposal_search',result)
                self.assertIsNone(result['candidate'])

    def test_unrepresentably_small_budget_does_not_search_around_failure(self):
        scene,request=fixture();request.update(max_step_translation_m=1e-22,max_total_translation_m=1e-22)
        result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'precision_floor',result)
        self.assertNotIn('rounded_proposal_search',result)
        self.assertIsNone(result['candidate'])

    def test_nearly_parallel_direction_and_nonfinite_request_do_not_search(self):
        scene=flat_scene();request=simple_request(direction_world=[1.,0.,1e-12])
        result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'unsupported',result)
        self.assertNotIn('rounded_proposal_search',result)
        with self.assertRaises(ValueError):
            module.solve_support_plane_candidate(scene,simple_request(target_clearance_m=math.nan))

    def test_four_refused_feature_trials_keep_original_failure_and_are_inward(self):
        scene,request=fixture();real=module._certificate;calls=[]
        def reject_trials(*args):
            value=real(*args);calls.append(value)
            if len(calls)>=3:value={**value,'support_vertex_indices':[7]}
            return value
        with patch.object(module,'_certificate',side_effect=reject_trials):
            result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'feature_changed')
        self.assertEqual(result['reason_codes'],['contact_feature_changed_after_rounded_translation'])
        self.assertIsNone(result['candidate'])
        search=result['rounded_proposal_search'];self.assertEqual(len(search['attempts']),4)
        self.assertEqual(len(calls),6)
        self.assertIsNone(search['accepted_attempt'])
        magnitudes=[abs(row['scalar_m']) for row in search['attempts']]
        self.assertTrue(all(0<value<abs(search['original_scalar_m']) for value in magnitudes))
        self.assertEqual(magnitudes,sorted(magnitudes,reverse=True))

    def test_fallback_resource_failure_stops_without_trying_around_it(self):
        scene,request=fixture();real=module._certificate;calls=[]
        def failure(*args):
            calls.append(None)
            if len(calls)==3:raise ArithmeticError('support_plane_rational_resource_limit')
            return real(*args)
        with patch.object(module,'_certificate',side_effect=failure):
            result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(len(calls),3)
        self.assertEqual(result['status'],'feature_changed')
        self.assertIsNone(result['candidate'])
        self.assertEqual(len(result['rounded_proposal_search']['attempts']),1)
        self.assertEqual(result['rounded_proposal_search']['attempts'][0]['reason'],'support_plane_rational_resource_limit')

    def test_fallback_strict_metric_disagreement_stops_without_acceptance(self):
        scene,request=fixture();real=module._strict;calls=[]
        def mismatch(*args):
            measured,agreement=real(*args);calls.append(None)
            if len(calls)==2:measured={**measured,'signed_clearance_m':.003}
            return measured,agreement
        with patch.object(module,'_strict',side_effect=mismatch):
            result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(len(calls),2)
        self.assertEqual(result['status'],'feature_changed')
        self.assertIsNone(result['candidate'])
        self.assertEqual(result['rounded_proposal_search']['attempts'][0]['reason'],
                         'rounded_candidate_disagrees_with_linear_prediction')

    def test_fallback_with_no_improvement_is_not_accepted_even_if_metric_guard_is_injected(self):
        scene,request=fixture();real=module._strict;initial=[]
        def no_progress(*args):
            measured,agreement=real(*args)
            if not initial:initial.append(measured['signed_clearance_m'])
            else:return {**measured,'signed_clearance_m':initial[0]},1.
            return measured,agreement
        with patch.object(module,'_strict',side_effect=no_progress):
            result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(result['status'],'feature_changed')
        self.assertIsNone(result['candidate'])
        self.assertEqual(result['rounded_proposal_search']['attempts'][0]['reason'],'no_representable_progress')

    def test_original_unsupported_candidate_does_not_trigger_search(self):
        scene,request=fixture();real=module._certificate;calls=[]
        def fail_original(*args):
            calls.append(None)
            if len(calls)==2:raise ArithmeticError('exact_convex_original_halfspaces_required')
            return real(*args)
        with patch.object(module,'_certificate',side_effect=fail_original):
            result=module.solve_support_plane_candidate(scene,request)
        self.assertEqual(len(calls),2)
        self.assertEqual(result['status'],'unsupported')
        self.assertNotIn('rounded_proposal_search',result)
        self.assertIsNone(result['candidate'])


if __name__=='__main__':unittest.main()
