"""Eight frozen preview cases plus the existing asset/50:50 contract.

Independent checks use ordered-ring area and explicit three-dimensional LBS.
No new source domain, model training, Blender launch, or extra scored case.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path
import unittest

import numpy as np

from verification.arm_twist_correction_preview_001.cases import make_cases,joint_weight_proof
from verification.arm_twist_correction_preview_001.oracle import (
    chain_poses,local_basis_matrices,polygon_area,projected_section_ratios,section_objective,skin_vertices)

ROOT=Path(__file__).resolve().parents[2]
FROZEN_DATASET_RAW_SHA256='6ccec485cc9fedb832324e3802e1ca4bc8529e55b2171afe4278803c62be1f4d'


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def validate_result(case,result):
    """Independent assertions shared with the root's evidence collector."""
    test=unittest.TestCase();patch,task=case['patch'],case['task']
    test.assertEqual(result['schema'],'arm-axial-redistribution-preview-v1')
    test.assertEqual(result['status'],case['expected_status'])
    expected_reason={'not_applicable':'non_axial_or_ambiguous_pose',
                     'unreachable':'best_allowed_u_exceeds_area_target',
                     'no_op':'area_target_already_met'}.get(case['expected_status'])
    if expected_reason is not None:test.assertEqual(result.get('reason'),expected_reason)
    if case['expected_status']=='not_applicable':
        test.assertIsNone(result['candidate'])
        return {'status':result['status'],'no_executable_candidate':True}

    before=section_objective(patch['rest_vertices'],patch['current_vertices'],patch['sections'])
    test.assertAlmostEqual(before['max_section_area_loss'],case['expected_before_j'],delta=1e-8)
    test.assertAlmostEqual(result['objective']['before']['max_section_area_loss'],case['expected_before_j'],delta=1e-8)
    np.testing.assert_allclose(result['objective']['before']['section_area_ratios'],before['section_area_ratios'],rtol=0.,atol=1e-8)
    test.assertAlmostEqual(result['objective']['after']['max_section_area_loss'],case['expected_after_j'],delta=1e-8)
    test.assertAlmostEqual(result['theta_deg'],case['theta_deg'],delta=.001)
    test.assertAlmostEqual(result['u_current_deg'],case['current_u_deg'],delta=.001)
    if result['status']=='candidate':
        candidate=result['candidate'];test.assertIsInstance(candidate,dict)
        test.assertAlmostEqual(candidate['u_deg'],case['expected_u_deg'],delta=.001)
        test.assertGreaterEqual(candidate['u_deg'],task['u_interval_deg'][0])
        test.assertLessEqual(candidate['u_deg'],task['u_interval_deg'][1])
        poses=candidate['pose_matrices'];test.assertEqual(len(poses),3)
        for actual,expected in ((poses[0],task['fixed_end_pose_matrices'][0]),(poses[-1],task['fixed_end_pose_matrices'][-1])):
            np.testing.assert_allclose(actual,expected,rtol=0.,atol=1e-9)
        np.testing.assert_allclose(candidate['local_basis_matrices'],local_basis_matrices(patch,poses),rtol=0.,atol=1e-9)
        changes=candidate['bone_changes'];test.assertEqual(len(changes),2)
        names=[change.get('bone',change.get('name',change.get('bone_name'))) for change in changes]
        test.assertEqual(names,[patch['bone_chain'][1]['name'],patch['bone_chain'][2]['name']])
        current=np.asarray(candidate['current_vertices'],dtype=float)
        np.testing.assert_allclose(current,skin_vertices(patch,poses),rtol=0.,atol=1e-9)
        independent_pose=chain_poses(case['fixture']['rest_matrices'],case['expected_u_deg'],case['theta_deg'])
        np.testing.assert_allclose(poses,independent_pose,rtol=0.,atol=1e-9)
    else:
        test.assertIsNone(result['candidate'])
        if result['status']=='no_op':
            current=np.asarray(patch['current_vertices'],dtype=float)
        else:
            # Infeasible candidates are not exposed for execution; independently
            # reconstruct the known best feasible geometry to check its report.
            poses=chain_poses(case['fixture']['rest_matrices'],case['expected_u_deg'],case['theta_deg'])
            current=np.asarray(skin_vertices(patch,poses),dtype=float)
            test.assertGreater(case['expected_after_j'],task['max_section_area_loss'])

    after=section_objective(patch['rest_vertices'],current,patch['sections'])
    test.assertAlmostEqual(after['max_section_area_loss'],case['expected_after_j'],delta=1e-8)
    np.testing.assert_allclose(result['objective']['after']['section_area_ratios'],after['section_area_ratios'],rtol=0.,atol=1e-8)
    # This second area implementation projects and uses shoelace, rather than
    # the magnitude of Newell's 3D area vector used for the primary oracle.
    np.testing.assert_allclose(projected_section_ratios(patch['rest_vertices'],current,patch['sections']),
                               after['section_area_ratios'],rtol=0.,atol=1e-10)
    original=np.asarray(patch['current_vertices'],dtype=float)
    protected=set(task['protected_vertex_ids'])
    protected_rows=[row for row,vertex_id in enumerate(patch['vertex_ids']) if vertex_id in protected]
    protected_error=float(np.max(np.abs(current[protected_rows]-original[protected_rows])))
    centers_before=np.array([original[section].mean(axis=0) for section in patch['sections']])
    centers_after=np.array([current[section].mean(axis=0) for section in patch['sections']])
    center_error=float(np.max(np.linalg.norm(centers_after-centers_before,axis=1)))
    test.assertLessEqual(protected_error,task['position_tolerance_m'])
    test.assertLessEqual(center_error,task['position_tolerance_m'])
    if result['status'] in ('candidate','no_op'):
        test.assertLessEqual(after['max_section_area_loss'],task['max_section_area_loss']+1e-8)
    if result['status']=='candidate':
        preservation=result['preservation']
        test.assertLessEqual(preservation['max_fixed_end_matrix_delta'],1e-9)
        test.assertLessEqual(preservation['max_centerline_delta_m'],task['position_tolerance_m'])
        test.assertLessEqual(preservation['max_protected_vertex_delta_m'],task['position_tolerance_m'])
    return {'status':result['status'],'before_j':before['max_section_area_loss'],
            'after_j':after['max_section_area_loss'],'known_u_deg':case['expected_u_deg'],
            'max_protected_vertex_delta_m':protected_error,'max_centerline_delta_m':center_error,
            'newell_and_projected_areas_agree':True}


class CorrectionPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from human_eye_plugin.arm_twist_correction import preview_axial_redistribution
        cls.preview=staticmethod(preview_axial_redistribution)
        cls.cases={case['case_id']:case for case in make_cases()}

    def check(self,name):
        case=self.cases[name];patch,task=case['patch'],case['task']
        original=(deepcopy(patch),deepcopy(task));before=(encoded(patch),encoded(task))
        result=self.preview(patch,task)
        self.assertEqual(before,(encoded(patch),encoded(task)))
        self.assertEqual((patch,task),original)
        validate_result(case,result)

    def test_round_120(self):self.check('round_120')
    def test_round_minus150(self):self.check('round_minus150')
    def test_elliptic_120(self):self.check('elliptic_120')
    def test_elliptic_minus150(self):self.check('elliptic_minus150')
    def test_balanced_no_op(self):self.check('balanced_120')
    def test_small_twist_no_op(self):self.check('small_twist_30')
    def test_unreachable_interval(self):self.check('unreachable_120')
    def test_noncoaxial_not_applicable(self):self.check('noncoaxial')

    def test_existing_asset_fields_and_half_weights(self):
        raw=gzip.decompress((ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),FROZEN_DATASET_RAW_SHA256)
        saved=json.loads(raw)
        for shape in ('round','elliptic'):
            case=next(case for case in self.cases.values() if case['shape']==shape)
            original=next(item['packet'] for item in saved if item['metadata']['asset_id']==case['asset_id'])
            for field in ('rest_vertices','triangles','weights','vertex_ids','sections'):
                self.assertEqual(case['patch'][field],original[field])
            self.assertEqual([bone['rest_matrix'] for bone in case['patch']['bone_chain']],
                             [bone['rest_matrix'] for bone in original['bone_chain']])
            self.assertEqual(len(case['patch']['rest_vertices']),402)
            self.assertEqual(len(case['patch']['triangles']),800)
            self.assertEqual(len(case['patch']['sections']),25)
            self.assertEqual([record['section_index'] for record in joint_weight_proof(case['patch'])],[8,16])

    def test_thin_crossing_inside_old_side_tolerance_is_rejected(self):
        # This guard counterexample is separate from the eight effect cases.
        # A step-three traversal of a very flat 16-point ellipse crosses itself;
        # every edge-side determinant fits the old tolerance band, while the
        # algebraic polygon area is still well above the old nonzero-area gate.
        case=self.cases['round_120'];patch=deepcopy(case['patch']);task=deepcopy(case['task'])
        rest=np.asarray(patch['rest_vertices'],dtype=float)
        first=np.asarray(patch['bone_chain'][0]['rest_matrix'],dtype=float)
        local=(np.column_stack((rest,np.ones(len(rest))))@np.linalg.inv(first).T)[:,:3]
        section=patch['sections'][8];height=float(local[section,1].mean())
        phase=3.*2.*math.pi*np.arange(16)/16.
        flat=np.column_stack((.1*np.cos(phase),np.full(16,height),1e-10*np.sin(phase)))
        world=(np.column_stack((flat,np.ones(16)))@first.T)[:,:3]
        for row,value in zip(section,world):patch['rest_vertices'][row]=value.tolist()
        patch['current_vertices']=skin_vertices(patch)
        self.assertEqual(patch['vertex_ids'],case['patch']['vertex_ids'])
        self.assertEqual(patch['triangles'],case['patch']['triangles'])

        local=(np.column_stack((patch['rest_vertices'],np.ones(len(rest))))@np.linalg.inv(first).T)[:,:3]
        ring=local[section];polygon=ring[:,[0,2]]
        self.assertLessEqual(float(np.linalg.norm(ring.mean(axis=0)[[0,2]])),task['position_tolerance_m'])
        self.assertLessEqual(float(np.ptp(ring[:,1])),task['position_tolerance_m'])
        edges=np.roll(polygon,-1,axis=0)-polygon
        lengths=np.linalg.norm(edges,axis=1)
        self.assertGreater(float(lengths.min()),1000.*task['position_tolerance_m'])
        guard=task['position_tolerance_m']*float(lengths.max())
        differences=polygon[None,:,:]-polygon[:,None,:]
        side=edges[:,None,0]*differences[:,:,1]-edges[:,None,1]*differences[:,:,0]
        rows=np.arange(16)[:,None];columns=np.arange(16)[None,:]
        interior=side[(columns!=rows)&(columns!=(rows+1)%16)]
        self.assertTrue(np.all(np.abs(interior)<=guard))
        # Explicitly establish the old loose sign check would accept this ring.
        self.assertFalse(np.any(side>guard) and np.any(side<-guard))
        scale=max(float(np.ptp(local,axis=0).max()),task['position_tolerance_m'])
        area_gate=max(task['position_tolerance_m']**2,scale**2*1e-12)
        actual_area=polygon_area(world)
        self.assertGreater(actual_area,area_gate)
        def orientation(a,b,c):
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        crossings=0
        for i in range(16):
            a,b=polygon[i],polygon[(i+1)%16]
            for j in range(i+1,16):
                if j in (i,(i+1)%16) or (j+1)%16==i:continue
                c,d=polygon[j],polygon[(j+1)%16]
                if orientation(a,b,c)*orientation(a,b,d)<0 and orientation(c,d,a)*orientation(c,d,b)<0:
                    crossings+=1
        self.assertGreater(crossings,0)
        before=(encoded(patch),encoded(task));result=self.preview(patch,task)
        self.assertEqual(before,(encoded(patch),encoded(task)))
        self.assertEqual(result['status'],'not_applicable')
        self.assertEqual(result['reason'],'section_not_reliably_convex_ordered')
        self.assertIsNone(result['candidate'])
        type(self).thin_crossing_guard_evidence={'section_index':8,'side_guard':guard,
            'max_abs_interior_side':float(np.abs(interior).max()),'min_edge_m':float(lengths.min()),
            'newell_area_m2':actual_area,'old_area_gate_m2':area_gate,'proper_segment_crossings':crossings,
            'old_loose_side_check_would_accept':True,'reason':result['reason'],
            'counted_in_eight_effect_cases':False}


if __name__=='__main__':unittest.main()
