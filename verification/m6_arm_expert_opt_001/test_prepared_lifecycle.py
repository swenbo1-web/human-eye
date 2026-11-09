"""Prepared arm patch lifecycle and legacy behavior, without training/Blender."""
from copy import deepcopy
import math
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import arm_twist_expert as expert
from human_eye_plugin.arm_twist_weights import PARAMETERS

ROOT=Path(__file__).resolve().parents[2]
BASELINE='ef84ecc59f107321225d0d832fde119ed0b91e3f'


def matrix(y=0.,angle=0.):
    c=math.cos(angle);s=math.sin(angle)
    return [[c,0.,s,0.],[0.,1.,0.,y],[-s,0.,c,0.],[0.,0.,0.,1.]]


def sample():
    rest=[];current=[];sections=[];triangles=[];weights=[]
    # Repeated 4-point length is deliberately separated by two other groups.
    for ring,(count,factor) in enumerate(zip((4,7,5,4),(.4,.9,.7,1.2))):
        section=[]
        for i in range(count):
            angle=2*math.pi*i/count;x=(1+ring*.1)*math.cos(angle);z=math.sin(angle)
            section.append(len(rest));rest.append([x,float(ring),z])
            current.append([factor*x,float(ring),factor*z])
            weights.append([.2+.1*ring,.8-.1*ring])
        sections.append(section)
        triangles.extend([[section[0],section[i],section[i+1]] for i in range(1,count-1)])
    return dict(schema='arm-twist-patch-v1',unit='m',rest_vertices=rest,current_vertices=current,
        triangles=triangles,sections=sections,weights=weights,vertex_ids=[1000+7*i for i in range(len(rest))],
        bone_chain=[dict(name='upper',parent=None,rest_matrix=matrix(),pose_matrix=matrix()),
                    dict(name='lower',parent='upper',rest_matrix=matrix(1.),pose_matrix=matrix(1.))])


def dynamic(packet):
    return packet['current_vertices'],[bone['pose_matrix'] for bone in packet['bone_chain']]


def no_numpy_arrays(test,value):
    test.assertNotIsInstance(value,np.ndarray)
    if isinstance(value,dict):
        for item in value.values():no_numpy_arrays(test,item)
    elif isinstance(value,(tuple,list)):
        for item in value:no_numpy_arrays(test,item)


class PreparedArmLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the accepted old source in memory. No source snapshot is written,
        # and this never starts the CLI consumer, a model trainer or Blender.
        result=subprocess.run(['git','show',BASELINE+':human_eye_plugin/arm_twist_expert.py'],
                              cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
        cls.old=types.ModuleType('human_eye_plugin._accepted_arm_expert')
        cls.old.__package__='human_eye_plugin'
        exec(compile(result.stdout,'<accepted-arm-expert-'+BASELINE+'>','exec'),cls.old.__dict__)

    def assert_features(self,actual,expected):
        np.testing.assert_allclose(actual[0],expected[0],atol=2e-12,rtol=2e-12)
        self.assertEqual(actual[1],expected[1])

    def test_static_arrays_lists_and_original_packet_are_detached(self):
        packet=sample();expected=self.old.extract_features(packet)
        packet['rest_vertices']=np.asarray(packet['rest_vertices'])
        packet['weights']=np.asarray(packet['weights'])
        for bone in packet['bone_chain']:bone['rest_matrix']=np.asarray(bone['rest_matrix'])
        current,poses=deepcopy(dynamic(packet))
        packet.pop('current_vertices')
        for bone in packet['bone_chain']:bone.pop('pose_matrix')
        prepared=expert.prepare_patch(packet)
        packet['rest_vertices'][:]=0.;packet['weights'][:]=0.
        packet['bone_chain'][0]['rest_matrix'][:]=0.
        packet['bone_chain'][0]['name']='changed';packet['bone_chain'].clear()
        packet['triangles'].clear();packet['sections'][0].clear();packet['sections'].clear()
        packet['vertex_ids'][0]=-1
        self.assert_features(prepared.extract_features(current,poses),expected)

    def test_returned_context_and_features_cannot_modify_prepared_state(self):
        packet=sample();expected=self.old.extract_features(packet)
        prepared=expert.prepare_patch(packet);current,poses=dynamic(packet)
        features,context=prepared.extract_features(current,poses)
        no_numpy_arrays(self,context)
        features[:]=999.;context['sections'][0].clear();context['vertex_ids'][0]=-1
        context['joint_angles'][0]['twist_deg']=999.
        self.assert_features(prepared.extract_features(current,poses),expected)

    def test_hot_path_does_not_revalidate_static_fields_and_batches_lengths(self):
        packet=sample();expected=self.old.extract_features(packet)
        prepared=expert.prepare_patch(packet);current,poses=dynamic(packet)
        real_array=expert._array;real_eig=np.linalg.eigvalsh;calls=[]
        def dynamic_array(value,name,shape=None):
            self.assertNotIn(name,('rest_vertices','weights','rest_matrix'))
            return real_array(value,name,shape)
        def current_eig(values,*args,**kwargs):
            calls.append(np.shape(values))
            return real_eig(values,*args,**kwargs)
        with patch.object(expert,'_array',side_effect=dynamic_array), \
                patch.object(expert,'prepare_patch',side_effect=AssertionError('hot path prepares again')), \
                patch.object(expert.rig_pose,'text',side_effect=AssertionError('hot path checks bone names')), \
                patch.object(np.linalg,'eigvalsh',side_effect=current_eig):
            self.assert_features(prepared.extract_features(current,poses),expected)
        self.assertEqual(sorted(calls),[(1,3,3),(1,3,3),(2,3,3)])
        np.testing.assert_allclose(expected[0][:,0],np.square([.4,.9,.7,1.2]),atol=2e-12,rtol=0)

    def test_dynamic_shape_and_pose_changes_take_effect_with_original_ids(self):
        packet=sample();prepared=expert.prepare_patch(packet)
        baseline=prepared.extract_features(*dynamic(packet))
        packet['current_vertices']=[[x*.5,y,z*.5] for x,y,z in packet['current_vertices']]
        changed=prepared.extract_features(*dynamic(packet))
        self.assert_features(changed,self.old.extract_features(packet))
        np.testing.assert_allclose(changed[0][:,0],baseline[0][:,0]*.25,atol=2e-12,rtol=0)
        packet['bone_chain'][1]['pose_matrix']=matrix(1.,math.pi/4)
        posed=prepared.extract_features(*dynamic(packet))
        self.assert_features(posed,self.old.extract_features(packet))
        np.testing.assert_allclose(posed[0][:,:8],changed[0][:,:8],atol=2e-12,rtol=0)
        self.assertTrue(np.all(posed[0][:,8]>changed[0][:,8]))
        self.assertEqual(posed[1]['vertex_ids'],packet['vertex_ids'])
        model=expert.ArmTwistExpert(PARAMETERS)
        actual=model.predict_prepared(prepared,*dynamic(packet))
        self.assertEqual(actual,prepared.analyze(*dynamic(packet),model=model))
        old=self.old.ArmTwistExpert(PARAMETERS).predict(packet)
        self.assertEqual(actual['status'],old['status'])
        self.assertEqual([row['vertex_ids'] for row in actual['regions']],
                         [row['vertex_ids'] for row in old['regions']])
        np.testing.assert_allclose([row['predicted_severity'] for row in actual['regions']],
                                   [row['predicted_severity'] for row in old['regions']],atol=2e-12,rtol=2e-12)

    def test_raw_multi_error_validation_priority_matches_accepted_source(self):
        cases=[]
        packet=sample();packet['current_vertices'].pop();packet['vertex_ids'][1]=packet['vertex_ids'][0];cases.append(packet)
        packet=sample();packet['bone_chain'][0]['pose_matrix']=[[0.]];packet['bone_chain'][1]['rest_matrix']=[[0.]];cases.append(packet)
        packet=sample();packet['bone_chain'][0]['pose_matrix'][0][0]=2.;packet['weights'][0]=[-1.,2.];cases.append(packet)
        packet=sample();packet['weights'][0]=[-1.,2.];packet['triangles'][0]=[0,0,0];cases.append(packet)
        packet=sample();packet['triangles'][0]=[0,0,0];packet['sections'][0]=[0,0,0];cases.append(packet)
        for index,packet in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ValueError) as expected:self.old.extract_features(packet)
                with self.assertRaises(ValueError) as actual:expert.extract_features(packet)
                self.assertEqual(str(actual.exception),str(expected.exception))

    def test_unknown_priority_and_current_collapse_match_accepted_source(self):
        cases=[]
        packet=sample()
        packet['bone_chain'][1]['pose_matrix']=matrix(1.,math.pi)
        # A branch-unknown pose precedes even bad reference centerlines.
        packet['rest_vertices']=[[x,0.,z] for x,y,z in packet['rest_vertices']];cases.append(packet)
        packet=sample()
        packet['rest_vertices']=[[x,0.,z] for x,y,z in packet['rest_vertices']]
        packet['current_vertices'][0][1]+=.4;cases.append(packet)
        packet=sample();packet['current_vertices'][0][1]+=.4;cases.append(packet)
        packet=sample()
        for vertex in packet['sections'][1]:packet['current_vertices'][vertex]=[0.,1.,0.]
        cases.append(packet)
        # Finite coordinates remain inside the accepted raw input contract.
        # Static eager eigen-analysis must not override an earlier guarded
        # pose/centerline decision merely because squared coordinates overflow.
        for branch in (True,False):
            packet=sample()
            packet['rest_vertices']=(np.asarray(packet['rest_vertices'])*1e155).tolist()
            if branch:packet['bone_chain'][1]['pose_matrix']=matrix(1.,math.pi)
            cases.append(packet)
        for index,packet in enumerate(cases):
            with self.subTest(index=index),np.errstate(over='ignore',invalid='ignore'):
                expected=self.old.extract_features(packet)
                self.assert_features(expert.extract_features(packet),expected)
                prepared=expert.prepare_patch(packet)
                self.assert_features(prepared.extract_features(*dynamic(packet)),expected)


if __name__=='__main__':unittest.main()
