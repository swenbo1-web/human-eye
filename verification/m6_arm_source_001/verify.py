"""Selected-size, fake-RNA acceptance; never launches Blender or an API.

These tests validate the source adapter's Python boundary and counted reads.
They do not establish the dirty-notification semantics of a real depsgraph.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from human_eye_plugin import arm_twist_expert as expert
from human_eye_plugin.arm_twist_source import ArmTwistSource
from human_eye_plugin.arm_twist_source import ArmTwistSourceError
from verification.m6_arm_expert_001.synthetic import generate_dataset
from verification.m6_arm_source_001.fixtures import Bone, Matrix, build_fixture, unit_matrix

OBSERVATIONS={}


@lru_cache(maxsize=1)
def cases():return generate_dataset()


def cycle(triangle):
    start=min(range(3),key=lambda i:triangle[i])
    return tuple(triangle[start:]+triangle[:start])


def oriented_faces(triangles):return sorted(cycle(list(t)) for t in triangles)


def canonical_static(packet):
    value=copy.deepcopy(packet);value.pop('current_vertices')
    for bone in value['bone_chain']:bone.pop('pose_matrix')
    return value


def counter_delta(after,before):
    return {name:after.get(name,0)-before.get(name,0) for name in set(after)|set(before)}


class SourceAcceptance(unittest.TestCase):
    def bind(self,fixture):
        return ArmTwistSource(fixture.host,topology_reader=fixture.topology_reader).bind(fixture.selection)

    def no_global_expansion(self,fixture):
        for key in ('full_vertex_iteration_attempts','full_vertex_bulk_attempts',
                    'full_topology_iteration_attempts','unselected_vertex_requests'):
            self.assertEqual(fixture.counters[key],0,key)

    def compare_capture(self,capture,packet,*,static=True):
        self.assertEqual(capture['schema'],'arm-twist-source-capture-v1')
        self.assertEqual(capture['source']['coordinate_frame'],'armature_local')
        self.assertEqual(capture['source']['unit'],'m')
        np.testing.assert_allclose(capture['current_vertices'],packet['current_vertices'],rtol=0,atol=3e-12)
        np.testing.assert_allclose(capture['pose_matrices'],[b['pose_matrix'] for b in packet['bone_chain']],rtol=0,atol=3e-12)
        if not static:return
        got=capture['static_patch'];want=canonical_static(packet)
        self.assertEqual(set(got),set(want))
        self.assertEqual(got['vertex_ids'],want['vertex_ids'])
        self.assertEqual(got['sections'],want['sections'])
        self.assertEqual(got['schema'],want['schema']);self.assertEqual(got['unit'],'m')
        self.assertEqual(oriented_faces(got['triangles']),oriented_faces(want['triangles']))
        for field in ('rest_vertices','weights'):
            np.testing.assert_allclose(got[field],want[field],rtol=0,atol=3e-12)
        for actual,expected in zip(got['bone_chain'],want['bone_chain']):
            self.assertEqual(set(actual),set(expected))
            for field in ('name','parent'):self.assertEqual(actual[field],expected[field])
            np.testing.assert_allclose(actual['rest_matrix'],expected['rest_matrix'],rtol=0,atol=3e-12)

    def test_01_cold_402_selected_in_million_vertex_asset(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);capture=bound.capture()
        self.compare_capture(capture,fixture.packet)
        self.assertTrue(capture['static_changed']);self.assertIsNotNone(bound.prepared)
        self.assertEqual(len(capture['static_patch']['rest_vertices']),402)
        self.assertEqual(len(capture['static_patch']['triangles']),800)
        totals=bound.work_totals()
        self.assertEqual(totals['captures'],1);self.assertEqual(totals['preparations'],1)
        self.assertEqual(totals['rest_vertices'],402);self.assertEqual(totals['weight_rows'],402)
        self.assertEqual(totals['current_vertices'],402);self.assertEqual(totals['topology_reads'],1)
        self.assertEqual(fixture.counters['rest_index_reads'],402)
        self.assertEqual(fixture.counters['current_index_reads'],402)
        self.no_global_expansion(fixture)
        OBSERVATIONS['cold']={'virtual_asset_vertices':fixture.total_vertices,
            'selected_vertices':402,'selected_triangles':800,'source_work':totals,
            'native_reads':dict(fixture.counters)}

    def test_02_five_native_lbs_poses_keep_one_prepare_no_static_reread(self):
        asset=cases()[0]['metadata']['asset_id'];poses=[c for c in cases() if c['metadata']['asset_id']==asset
            and c['metadata']['deformation']=='LBS_point_pose_times_inverse_rest']
        fixture=build_fixture(poses[0]);bound=self.bind(fixture);first=bound.capture();prepared=bound.prepared
        self.compare_capture(first,poses[0]['packet'])
        before=dict(fixture.counters);work_before=bound.work_totals()
        for case in poses[1:]:
            fixture.set_pose(case['packet']);capture=bound.capture()
            self.compare_capture(capture,case['packet'],static=False)
            self.assertIs(capture['static_changed'],False);self.assertIsNone(capture['static_patch'])
            self.assertIs(bound.prepared,prepared)
        delta=counter_delta(dict(fixture.counters),before)
        for key in ('rest_index_reads','rest_coordinates','weights_collections','bone_rest_matrices','topology_reads'):
            self.assertEqual(delta.get(key,0),0,key)
        work=bound.work_totals();self.assertEqual(work['preparations'],1)
        self.assertEqual(work['current_vertices']-work_before['current_vertices'],4*402)
        self.assertEqual(work['pose_bones']-work_before['pose_bones'],4*len(fixture.bones))
        self.no_global_expansion(fixture)
        OBSERVATIONS['five_native_lbs_poses']={'poses':len(poses),'source_work':work,'warm_native_delta':delta}

    def test_03_all_saved_asset_families_and_77_current_poses(self):
        grouped={}
        for case in cases():grouped.setdefault(case['metadata']['asset_id'],[]).append(case)
        counts=[]
        accepted=0;refused=0
        for asset,poses in grouped.items():
            fixture=build_fixture(poses[0]);bound=self.bind(fixture)
            for index,case in enumerate(poses):
                if index:fixture.set_pose(case['packet'])
                if case['metadata']['deformation']=='LBS_point_pose_times_inverse_rest':
                    capture=bound.capture();self.compare_capture(capture,case['packet'],static=index==0);accepted+=1
                else:
                    with self.assertRaises(ArmTwistSourceError) as raised:bound.capture()
                    self.assertEqual(raised.exception.reason,'same_index_lbs_readback_mismatch');refused+=1
            self.assertEqual(bound.work_totals()['preparations'],1)
            self.no_global_expansion(fixture)
            counts.append({'asset':asset,'poses':len(poses),'bones':len(fixture.bones),'source_work':bound.work_totals()})
        self.assertEqual(sum(row['poses'] for row in counts),77)
        self.assertEqual(len(counts),11);self.assertEqual({row['bones'] for row in counts},{2,3})
        self.assertEqual((accepted,refused),(55,22))
        OBSERVATIONS['saved_dataset']={'assets':len(counts),'poses_attempted':77,'lbs_accepted':accepted,
            'non_lbs_controls_refused':refused,'refusal_reason':'same_index_lbs_readback_mismatch','rows':counts}

    def test_04_dirty_false_alarm_checks_static_but_does_not_reprepare(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);first=bound.capture()
        prepared=bound.prepared;before=bound.work_totals();fixture.touch_geometry()
        capture=bound.capture();after=bound.work_totals()
        self.assertIs(bound.prepared,prepared);self.assertIs(capture['static_changed'],False)
        self.assertIsNone(capture['static_patch'])
        self.assertEqual(capture['source']['static_revision'],first['source']['static_revision'])
        self.assertEqual(after['static_reads']-before['static_reads'],1)
        self.assertEqual(after['rest_vertices']-before['rest_vertices'],402)
        self.assertEqual(after['topology_reads']-before['topology_reads'],1)
        self.assertEqual(after['preparations'],before['preparations'])
        self.no_global_expansion(fixture)
        OBSERVATIONS['dirty_false_alarm']={'source_delta':counter_delta(after,before)}

    def test_05_changed_rest_reprepares(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);old=bound.capture();prepared=bound.prepared
        fixture.native_vertices[fixture.indices[0]].value[0]+=.001;fixture.touch_geometry();fixture.refresh_lbs()
        current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertNotEqual(current['source']['static_revision'],old['source']['static_revision'])
        self.assertAlmostEqual(current['static_patch']['rest_vertices'][0][0],fixture.packet['rest_vertices'][0][0]+.001)

    def test_06_changed_normalized_weights_reprepare(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);bound.capture();prepared=bound.prepared
        fixture.native_vertices[fixture.indices[0]].memberships=[(0,.75),(1,.25)];fixture.touch_geometry();fixture.refresh_lbs()
        current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertEqual(current['static_patch']['weights'][0],[.75,.25])

    def test_07_changed_topology_reprepares_preserving_direction(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);bound.capture();prepared=bound.prepared
        fixture.global_triangles[0]=list(reversed(fixture.global_triangles[0]));fixture.touch_geometry()
        current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        expected=copy.deepcopy(fixture.packet['triangles']);expected[0].reverse()
        self.assertEqual(oriented_faces(current['static_patch']['triangles']),oriented_faces(expected))

    def test_08_changed_bone_rest_reprepares(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);bound.capture();prepared=bound.prepared
        fixture.bones[1].rest[0][3]+=.002;fixture.touch_geometry('rig');fixture.refresh_lbs()
        current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertAlmostEqual(current['static_patch']['bone_chain'][1]['rest_matrix'][0][3],
                               fixture.packet['bone_chain'][1]['rest_matrix'][0][3]+.002)

    def test_09_same_name_mesh_replacement_is_fresh_source(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);first=bound.capture();prepared=bound.prepared
        fixture.replace_mesh();current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertNotEqual(current['source'],first['source']);self.compare_capture(current,fixture.packet)

    def test_10_same_name_rig_replacement_is_fresh_source(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);first=bound.capture();prepared=bound.prepared
        fixture.replace_rig();current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertNotEqual(current['source'],first['source']);self.compare_capture(current,fixture.packet)

    def test_11_epoch_reset_cannot_reuse_old_preparation(self):
        fixture=build_fixture(cases()[0]);bound=self.bind(fixture);first=bound.capture();prepared=bound.prepared
        fixture.rebuild_epoch();current=bound.capture()
        self.assertIsNot(bound.prepared,prepared);self.assertTrue(current['static_changed'])
        self.assertGreater(current['source']['epoch'],first['source']['epoch'])
        self.compare_capture(current,fixture.packet)

    def test_12_relative_affine_mesh_rigid_rig_and_scene_units(self):
        mesh=Matrix([[1.25,.12,0.,.31],[0.,.8,.08,-.27],[0.,0.,1.1,.14],[0.,0.,0.,1.]])
        rig=Matrix([[0.,-1.,0.,-.42],[1.,0.,0.,.23],[0.,0.,1.,.19],[0.,0.,0.,1.]])
        for scale in (.01,1.,2.5):
            with self.subTest(unit_scale_m=scale):
                fixture=build_fixture(cases()[0],unit_scale=scale,mesh_world=mesh,rig_world=rig)
                bound=self.bind(fixture);current=bound.capture();self.compare_capture(current,fixture.packet)
                self.no_global_expansion(fixture)

    def test_13_analyze_retains_native_global_localization_and_readonly_scope(self):
        case=next(c for c in cases() if c['metadata']['pose_family']=='anomalous_twist')
        fixture=build_fixture(case);bound=self.bind(fixture);report=bound.analyze()
        reference=expert.analyze(fixture.packet)
        self.assertEqual(report['schema'],reference['schema']);self.assertEqual(report['status'],reference['status'])
        self.assertIs(report['execution_authority'],False);self.assertIn('source',report)
        self.assertEqual([r['vertex_ids'] for r in report['regions']],[r['vertex_ids'] for r in reference['regions']])
        np.testing.assert_allclose([r['predicted_severity'] for r in report['regions']],
            [r['predicted_severity'] for r in reference['regions']],rtol=0,atol=3e-12)
        self.no_global_expansion(fixture)

    def test_14_other_valid_deform_bone_weight_cannot_be_silently_dropped(self):
        fixture=build_fixture(cases()[0])
        extra=Bone('other_deform',fixture.bones[0],unit_matrix(),unit_matrix(),fixture.counters)
        fixture.bones.append(extra);fixture.mesh.vertex_groups.append(NS(name=extra.name,index=len(fixture.bones)-1))
        fixture.native_vertices[fixture.indices[0]].memberships=[(0,.75),(len(fixture.bones)-1,.25)]
        bound=self.bind(fixture)
        with self.assertRaises(ValueError):bound.capture()
        self.no_global_expansion(fixture)


def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SourceAcceptance)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    files=['human_eye_plugin/arm_twist_source.py','verification/m6_arm_source_001/fixtures.py',
           'verification/m6_arm_source_001/verify.py','verification/m6_arm_expert_001/synthetic.py']
    summary={'scope':'pure_fake_RNA_no_real_Blender_no_API_no_training',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'observations':OBSERVATIONS,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
        'limitations':['Real Blender depsgraph dirty notifications, evaluated topology/index preservation and RNA lifecycle are not exercised.',
            'Million-vertex asset uses sparse indexed test doubles; it is a bounded-read contract, not a real-asset timing benchmark.',
            'No host/worker/service entry point or real Blender process was modified or launched.']}
    print(json.dumps(summary,sort_keys=True,ensure_ascii=False,allow_nan=False))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
