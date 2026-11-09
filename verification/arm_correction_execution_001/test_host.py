"""Fault/unit checks of the actual host arm method using indexed RNA doubles.

The existing source adapter and preview run unchanged. Independent NumPy FK/LBS
updates the fake evaluated mesh after property assignments; QA never supplies
the resulting pose or points to the product as a substitute readback.
"""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if 'human_eye_plugin' not in sys.modules:
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package

from verification.arm_twist_correction_preview_001.cases import make_cases
from verification.arm_twist_correction_preview_001 import oracle
from verification.m6_arm_source_001 import test_arm_source as old


class Matrix:
    """Only the mathutils Matrix surface consumed by the host boundary."""
    def __init__(self,value):self.rows=np.asarray(value,dtype=float).tolist()
    def __iter__(self):return iter(self.rows)
    def __getitem__(self,index):return self.rows[index]
    def copy(self):return Matrix(self.rows)
    def __matmul__(self,other):
        a=np.asarray(self.rows);b=np.asarray(list(other),dtype=float)
        if b.shape==(3,):return (a@np.r_[b,1.])[:3].tolist()
        return Matrix(a@b)


def native_matrix(value,scale):
    output=deepcopy(value)
    for row in output[:3]:row[3]/=scale
    return output


class PoseBone:
    def __init__(self,fixture,index,bone,basis,parent):
        self.fixture=fixture;self.index=index;self.name=bone.name;self.bone=bone
        self.parent=parent;self.constraints=[];self.rotation_mode='QUATERNION'
        self._basis=deepcopy(basis)
    @property
    def matrix_basis(self):return Matrix(self._basis)
    @matrix_basis.setter
    def matrix_basis(self,value):
        f=self.fixture;f.attempted.append(self.name)
        if f.fail_bone==self.index:raise RuntimeError('fake_second_basis_assignment_failure')
        self._basis=np.asarray(list(value),dtype=float).tolist()
        f.returned.append(self.name);f.assigned.append((self.name,deepcopy(self._basis)))
        f.dirty=True
    @property
    def matrix(self):
        self.fixture.flush()
        return Matrix(self.fixture.poses[self.index])
    @property
    def head(self):return np.asarray(list(self.matrix))[:3,3].tolist()
    @property
    def tail(self):
        m=np.asarray(list(self.matrix));return (m[:3,3]+m[:3,1]*self.bone.length).tolist()


class BoundView:
    def __init__(self,fixture,bound):self.fixture=fixture;self.bound=bound
    def __getattr__(self,name):return getattr(self.bound,name)
    def capture(self,*args,**kwargs):
        f=self.fixture;f.capture_attempts+=1
        if f.fail_capture==f.capture_attempts:raise RuntimeError('fake_after_capture_failure')
        return self.bound.capture(*args,**kwargs)


class Fixture:
    def __init__(self,*,case_index=0,scale=1.,offset_rest_head=False,fail_bone=None,fail_capture=None):
        from human_eye_plugin import arm_twist_source,arm_twist_correction
        self.case=deepcopy(make_cases()[case_index]);packet=self.case['patch']
        packet['vertex_ids']=list(range(len(packet['rest_vertices'])))
        if offset_rest_head:
            root_matrix=np.asarray(packet['bone_chain'][0]['rest_matrix'])
            bone=packet['bone_chain'][1]
            moved=np.asarray(bone['rest_matrix']);moved[:3,3]+=root_matrix[:3,0]*1e-6
            bone['rest_matrix']=moved.tolist()
            poses=oracle.chain_poses([b['rest_matrix'] for b in packet['bone_chain']],120.,120.)
            for bone,pose in zip(packet['bone_chain'],poses):bone['pose_matrix']=pose
            packet['current_vertices']=oracle.skin_vertices(packet)
        self.packet=packet;self.scale=scale
        converted=deepcopy(packet)
        for field in ('rest_vertices','current_vertices'):
            converted[field]=(np.asarray(converted[field])/scale).tolist()
        for bone in converted['bone_chain']:
            for field in ('rest_matrix','pose_matrix'):bone[field]=native_matrix(bone[field],scale)
        with patch.object(old,'fixture_packet',return_value=converted):
            self.f=old.make_host(total=len(packet['rest_vertices']),native_indices=list(range(len(packet['rest_vertices']))),scale=scale)
        f=self.f;self.host=f.host
        f.bpy.app.background=True;f.bpy.data.filepath=''
        self.host.execution_metadata=True;self.host.identity_metadata=True
        self.host._owned_arm_correction_worker=True;self.host._material_readview_only=False
        f.mesh.data.users=f.rig.data.users=1
        self.attempted=[];self.returned=[];self.assigned=[]
        self.fail_bone=fail_bone;self.fail_capture=fail_capture;self.capture_attempts=0
        self.unlink_sentinel_after_writes=False
        self.change_rotation_mode_after_writes=False
        self.dirty=True;self.poses=[]
        bases=oracle.local_basis_matrices(converted)
        bones=old.Named()
        matrices=[np.asarray(b.matrix_local) for b in f.rig.data.bones]
        lengths=[np.linalg.norm(matrices[i+1][:3,3]-matrices[i][:3,3]) for i in range(2)]
        lengths.append(lengths[-1])
        for index,(bone,basis,length) in enumerate(zip(f.rig.data.bones,bases,lengths)):
            bone.length=float(length);bone.use_connect=False
            bones.append(PoseBone(self,index,bone,basis,bones[-1] if index else None))
        f.rig.pose.bones=bones;f.rig.data.is_editmode=False
        sentinel_data=NS(name='SentinelData',vertices=[NS(co=[3.,4.,5.]),NS(co=[4.,4.,5.]),NS(co=[3.,5.,5.])],
            polygons=[NS(vertices=(0,1,2))],session_uid=9001,shape_keys=None,animation_data=None)
        sentinel=old.Object('Sentinel','MESH',sentinel_data,9002)
        f.host.scene.objects.append(sentinel);self.sentinel=sentinel
        f.host.view_layer.update=self.flush
        self.flush()
        def topology(mesh,indices):
            allowed=set(indices)
            return [row[:] for row in f.global_triangles if all(index in allowed for index in row)]
        fixture=self
        class Source:
            def __init__(self,host):self.inner=arm_twist_source.ArmTwistSource(host,topology_reader=topology)
            def bind(self,selection):
                fixture.last_bound=BoundView(fixture,self.inner.bind(selection))
                return fixture.last_bound
        self.last_bound=None
        self.source_module=NS(ArmTwistSource=Source,r=arm_twist_source.r)
        self.correction_module=arm_twist_correction
        self.host._arm_correction_module=arm_twist_correction
        self.preview_calls=0
        self.real_preview=arm_twist_correction.preview_axial_redistribution
        self.host._arm_correction_preview=self.real_preview
        self.selection=deepcopy(f.selection);self.selection['armature_name']=f.rig.name
        protected=[i for i,row in enumerate(packet['weights']) if row in ([1.,0.,0.],[0.,0.,1.])]
        self.task={'schema':'arm-axial-execution-task-v1','event_id':'host-test-'+str(case_index),
            'selection':self.selection,'u_interval_deg':self.case['task']['u_interval_deg'][:],
            'max_section_area_loss':.4,'protected_vertex_ids':protected,'sentinel_name':'Sentinel',
            'angle_tolerance_deg':.001,'position_tolerance_m':5e-6,'area_tolerance':1e-6}

    def flush(self):
        if not self.dirty:return
        f=self.f;poses=[]
        for index,(bone,pose) in enumerate(zip(f.rig.data.bones,f.rig.pose.bones)):
            rest=np.asarray(bone.matrix_local);basis=np.asarray(pose._basis)
            relative=rest if index==0 else np.linalg.solve(np.asarray(f.rig.data.bones[index-1].matrix_local),rest)
            poses.append(relative@basis if index==0 else poses[-1]@relative@basis)
        self.poses=[value.tolist() for value in poses]
        native_packet=deepcopy(self.packet)
        native_packet['rest_vertices']=(np.asarray(native_packet['rest_vertices'])/self.scale).tolist()
        for bone,rest in zip(native_packet['bone_chain'],f.rig.data.bones):bone['rest_matrix']=deepcopy(rest.matrix_local)
        points=oracle.skin_vertices(native_packet,self.poses)
        for index,point in enumerate(points):f.mesh.evaluated.data.vertices.rows[index].co=point
        self.dirty=False
        old.notify(f,f.rig,geometry=False)
        if self.unlink_sentinel_after_writes and self.returned:
            f.host.scene.objects.remove(self.sentinel)
            self.unlink_sentinel_after_writes=False
        if self.change_rotation_mode_after_writes and self.returned:
            f.rig.pose.bones[1].rotation_mode='XYZ'
            self.change_rotation_mode_after_writes=False

    def close(self):self.host.close_residency()

    def invoke(self):
        # The existing loader is the production seam; no test flag enters the
        # task or mutation request. Source capture remains the real adapter.
        if sys.getprofile() is not None:raise AssertionError('Host count trace must not replace another profiler')
        code=self.real_preview.__code__
        def count(frame,event,arg):
            if event=='call' and frame.f_code is code:self.preview_calls+=1
        try:
            sys.setprofile(count)
            with patch.object(self.host,'_arm_twist_source_module',return_value=self.source_module),\
                 patch.dict(sys.modules,{'mathutils':NS(Matrix=Matrix)}),\
                 patch.object(self.host,'capture_scene',side_effect=AssertionError('unexpected rigid capture')),\
                 patch.object(self.host,'capture_evidence',side_effect=AssertionError('unexpected full evidence capture')),\
                 patch.object(self.host,'observe_arm_twist',side_effect=AssertionError('unexpected second expert observation')):
                return self.host.correct_arm_axial(deepcopy(self.task))
        finally:sys.setprofile(None)


class ArmHostTests(unittest.TestCase):
    def fixture(self,**kwargs):
        fixture=Fixture(**kwargs);self.addCleanup(fixture.close);return fixture

    def test_normal_pair_has_one_preview_and_shared_after_capture(self):
        f=self.fixture();result=f.invoke()
        self.assertEqual(result['status'],'satisfied',result)
        self.assertTrue(result['task_succeeded']);self.assertIs(result['executed'],True)
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,2))
        self.assertEqual(f.attempted,['arm_1','arm_2']);self.assertEqual(f.returned,['arm_1','arm_2'])
        self.assertEqual(f.capture_attempts,2);self.assertEqual(f.preview_calls,1)

    def test_basis_translation_converts_metres_to_nonunit_blender_units(self):
        f=self.fixture(scale=.001,offset_rest_head=True);result=f.invoke()
        self.assertEqual(result['status'],'satisfied',result)
        poses=[np.asarray(matrix) for matrix in f.poses]
        actual_points=np.asarray(f.f.mesh.evaluated.data.vertices.rows[0].co)
        self.assertTrue(np.isfinite(actual_points).all())
        # Independently construct the known u=60 solution with fixed end poses,
        # then recover local bases through NumPy FK; do not call preview twice.
        expected_poses=[deepcopy(bone['pose_matrix']) for bone in f.packet['bone_chain']]
        expected_poses[1]=(np.asarray(expected_poses[0])@oracle.rotation_y(60.)@
            np.linalg.solve(np.asarray(f.packet['bone_chain'][0]['rest_matrix']),
                            np.asarray(f.packet['bone_chain'][1]['rest_matrix']))).tolist()
        expected=oracle.local_basis_matrices(f.packet,expected_poses)
        nonzero=False
        for index,(name,written) in zip((1,2),f.assigned):
            matrix=np.asarray(written);metres=np.asarray(expected[index])
            np.testing.assert_allclose(matrix[:3,:3],metres[:3,:3],rtol=0.,atol=1e-10)
            np.testing.assert_allclose(matrix[:3,3],metres[:3,3]/f.scale,rtol=0.,atol=1e-9)
            nonzero=nonzero or float(np.linalg.norm(metres[:3,3]))>1e-8
        self.assertTrue(nonzero,'Fixture must have a meaningful nonzero basis translation')
        self.assertEqual(len(poses),3);self.assertEqual(f.attempted,['arm_1','arm_2'])

    def test_second_setter_failure_preserves_partial_counts_and_pose(self):
        f=self.fixture(fail_bone=2);initial=deepcopy(f.poses);result=f.invoke()
        self.assertEqual(result['status'],'execution_uncertain',result)
        self.assertIs(result['executed'],True)
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,1))
        self.assertEqual(f.attempted,['arm_1','arm_2']);self.assertEqual(f.returned,['arm_1'])
        f.flush();self.assertFalse(np.allclose(f.poses[1],initial[1],rtol=0.,atol=1e-9))
        self.assertEqual(f.preview_calls,1)

    def test_first_setter_throw_does_not_claim_known_zero_execution(self):
        f=self.fixture(fail_bone=1);result=f.invoke()
        self.assertEqual(result['status'],'execution_uncertain',result)
        self.assertIsNone(result['executed'])
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(1,0))
        self.assertEqual(f.attempted,['arm_1']);self.assertEqual(f.returned,[])
        self.assertEqual(f.preview_calls,1)

    def test_after_capture_failure_preserves_two_returned_writes(self):
        f=self.fixture(fail_capture=2);result=f.invoke()
        self.assertEqual(result['status'],'execution_uncertain',result)
        self.assertIs(result['executed'],True);self.assertFalse(result['task_succeeded'])
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,2))
        self.assertEqual(f.capture_attempts,2);self.assertEqual(f.preview_calls,1)
        self.assertEqual(f.returned,['arm_1','arm_2'])

    def test_no_op_uses_before_state_and_zero_writes(self):
        f=self.fixture(case_index=4);initial=deepcopy(f.poses);result=f.invoke()
        self.assertEqual(result['status'],'no_op',result)
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(0,0))
        self.assertIs(result['executed'],False);self.assertEqual(f.poses,initial)
        self.assertEqual(f.capture_attempts,1);self.assertEqual(f.preview_calls,1)
        self.assertEqual(f.attempted,[])

    def test_animation_is_rejected_before_setter(self):
        f=self.fixture();f.f.rig.animation_data=NS(action=object(),drivers=[])
        result=f.invoke()
        self.assertEqual(result['setter_attempts'],0,result);self.assertEqual(f.attempted,[])
        self.assertFalse(result['task_succeeded'])
        self.assertEqual(result['reason'],'prewrite_scope:arm_execution_static_unconstrained_required')
        self.assertEqual(f.capture_attempts,1);self.assertEqual(f.preview_calls,0)

    def test_dependent_sentinel_geometry_is_rejected_before_setter(self):
        # Reading only the sentinel's original mesh cannot certify a modifier
        # or Key datablock that might depend on the bones being changed.
        for field in ('modifier','shape_keys'):
            with self.subTest(field=field):
                f=self.fixture()
                if field=='modifier':f.sentinel.modifiers=[NS(type='NODES')]
                else:f.sentinel.data.shape_keys=NS(animation_data=NS(drivers=[object()]))
                result=f.invoke()
                self.assertEqual(result['setter_attempts'],0,result)
                self.assertEqual(f.attempted,[]);self.assertFalse(result['task_succeeded'])
                self.assertEqual(result['reason'],'prewrite_scope:arm_execution_fixture_scope')
                self.assertEqual(f.capture_attempts,1);self.assertEqual(f.preview_calls,0)

    def test_unlinked_sentinel_after_pair_cannot_pass_old_held_reference(self):
        f=self.fixture();f.unlink_sentinel_after_writes=True
        result=f.invoke()
        self.assertEqual(result['status'],'execution_uncertain',result)
        self.assertEqual(result['reason'],'actual_feedback:arm_execution_object_incarnation_changed')
        self.assertIs(result['executed'],True);self.assertFalse(result['task_succeeded'])
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,2))
        self.assertEqual(f.capture_attempts,2);self.assertEqual(f.preview_calls,1)
        self.assertEqual(f.attempted,['arm_1','arm_2'])

    def test_valid_source_subset_cannot_authorize_global_bone_writes(self):
        f=self.fixture()
        # The 25 ordered rings and all side triangles remain a valid local
        # source patch; only the two cap-center vertices are not selected.
        selected=list(range(400));f.task['selection']['vertex_indices']=selected
        f.task['protected_vertex_ids']=[index for index in f.task['protected_vertex_ids'] if index in selected]
        result=f.invoke()
        self.assertEqual(result['status'],'not_applicable',result)
        self.assertEqual(result['reason'],'prewrite_scope:arm_execution_full_generated_mesh_required')
        self.assertIs(result['executed'],False)
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(0,0))
        self.assertEqual(f.attempted,[]);self.assertEqual(f.preview_calls,0);self.assertEqual(f.capture_attempts,1)
        self.assertEqual(f.last_bound.work_totals()['captures'],1)
        self.assertEqual(len(f.last_bound._static['rest_vertices']),400)
        self.assertEqual(len(f.f.mesh.data.vertices),402)

    def test_after_pair_rotation_mode_change_is_actual_feedback_failure(self):
        f=self.fixture();f.change_rotation_mode_after_writes=True
        result=f.invoke()
        self.assertEqual(result['status'],'feedback_failed',result)
        self.assertEqual(result['reason'],'actual_feedback_did_not_verify')
        self.assertIs(result['executed'],True);self.assertFalse(result['task_succeeded'])
        self.assertEqual((result['setter_attempts'],result['setter_returns']),(2,2))
        self.assertTrue(result['feedback']['target_met'])
        self.assertFalse(result['feedback']['static_side_unchanged'])
        self.assertEqual(f.f.rig.pose.bones[1].rotation_mode,'XYZ')
        self.assertEqual(f.capture_attempts,2);self.assertEqual(f.preview_calls,1)
        self.assertEqual(f.attempted,['arm_1','arm_2'])


if __name__=='__main__':unittest.main()
