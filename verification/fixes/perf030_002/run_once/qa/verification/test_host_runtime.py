"""Execution boundary contracts using an independent mutable host double."""
import copy
from contextlib import contextmanager
import unittest

import numpy as np

from human_eye_module1_operators import MeshEntity3D, SE3AlignmentMath
from human_eye_plugin.auto_router import HumanEyeAutoRouter, _validated_scene
from human_eye_plugin.host_runtime import GuardedHostRuntime


SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
FACES = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
         [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]


def mesh(oid, center, size, focal=False):
    return MeshEntity3D(oid, '#'+oid, oid,SIGNS*np.array(size)/2+np.array(center),
                       np.array(FACES),None,(70,140,210),focal,
                       local_axes=np.eye(3),pivot_world=np.array(center,dtype=float)).to_dict()


class MutableHost:
    def __init__(self):
        self.scene={'revision':'r1','unit':'m','coordinate_frame':'world','source':'test_host',
                    'meshes':[mesh('base',[0,0,.1],[1,1,.2]),
                              mesh('part',[0,0,.35],[.2,.3,.1],True)]}
        self.calls=0;self.captures=0;self.in_transaction=False;self.mode='normal'

    @contextmanager
    def transaction(self):
        self.in_transaction=True
        try:yield
        finally:self.in_transaction=False

    def capture_scene(self):
        if not self.in_transaction:raise AssertionError('Capture outside host transaction')
        self.captures+=1
        if self.mode=='capture_failure' or self.mode=='readback_failure' and self.calls:
            raise RuntimeError('Cannot read actual host')
        return copy.deepcopy(self.scene)

    def apply_transform(self,action,expected_revision,expected_fingerprint=None):
        if not self.in_transaction:raise AssertionError('Mutation outside host transaction')
        self.calls+=1
        if self.mode=='cas_failure':raise RuntimeError('Another editor changed revision')
        if expected_revision!=self.scene['revision']:raise RuntimeError('Stale revision')
        _,_,fingerprint=_validated_scene(self.scene)
        if expected_fingerprint!=fingerprint:raise RuntimeError('Wrong fingerprint')
        focal=MeshEntity3D.from_dict(self.scene['meshes'][1])
        rotation=SE3AlignmentMath.euler_xyz_to_matrix(*action.get('rotation_euler_deg',[0,0,0]))
        focal=focal.rotated_around_pivot(rotation).translated(action.get('translation',[0,0,0]))
        item=focal.to_dict()
        if self.mode=='float32':
            for field in ('vertices','local_axes','pivot_world'):
                item[field]=np.array(item[field],dtype=np.float32).astype(float).tolist()
        if self.mode=='incorrect':item['vertices'][0][0]+=.0001
        if self.mode=='nonfocal_mutation':self.scene['meshes'][0]['name']='unexpected_change'
        if self.mode=='topology_mutation':item['faces'][0]=[0,1,2]
        if self.mode=='collision':item=MeshEntity3D.from_dict(item).translated([0,0,-.25]).to_dict()
        self.scene['meshes'][1]=item
        if self.mode=='color_mutation':item['color_rgb']=[255,0,0]
        if self.mode!='same_revision':self.scene['revision']='r'+str(int(self.scene['revision'][1:])+1)
        if self.mode=='partial_failure':raise RuntimeError('Exception after host changed')
        return {'scene':copy.deepcopy(self.scene),'receipt':{'host':'independent_test_double'}}


class HostRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.host=MutableHost();self.runtime=GuardedHostRuntime(self.host,quad_size=64)

    def prepare(self,sid='s',**changes):
        kwargs={'session_id':sid,'task_instruction':'Measure current part clearance.',
                'focal_id':'part','reference_id':'base',
                'messages':[{'role':'user','content':'Measure current part clearance.'}]}
        kwargs.update(changes)
        return self.runtime.before_model(**kwargs)

    def execute(self,sid='s',**changes):
        kwargs={'session_id':sid,'action':{'translation':[0,0,.1]}}
        kwargs.update(changes)
        return self.runtime.execute_action(**kwargs)

    def test_real_boundary_calls_host_before_model_and_independent_readback(self):
        prepared=self.prepare();self.assertEqual(prepared['routing']['route'],'engine')
        result=self.execute()
        self.assertEqual(result['status'],'verified',result)
        self.assertTrue(result['executed']);self.assertTrue(result['verified'])
        self.assertEqual(self.host.calls,1);self.assertGreaterEqual(self.host.captures,3)
        self.assertEqual(result['actual_scene_revision'],'r2')

    def test_no_scene_or_revision_override_accepted(self):
        self.prepare()
        for field in ('scene','source','expected_revision','expected_fingerprint'):
            with self.assertRaises(TypeError):self.runtime.execute_action(session_id='s',action={'translation':[0,0,.1]},**{field:{}})
        self.assertEqual(self.host.calls,0)

    def test_native_does_not_read_host_or_retain_prior_authority(self):
        self.prepare();captures=self.host.captures
        prepared=self.prepare(task_kind='image_2d')
        self.assertEqual(prepared['routing']['route'],'native');self.assertEqual(self.host.captures,captures)
        self.assertEqual(self.execute()['status'],'observation_required')

    def test_execute_requires_observation(self):
        self.assertEqual(self.execute()['status'],'observation_required');self.assertEqual(self.host.calls,0)

    def test_cross_session_tokens_cannot_mutate(self):
        prepared=self.prepare('a');self.prepare('b')
        result=self.execute('b',observation_id=prepared['routing']['observation_id'])
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.host.calls,0)

    def test_host_change_between_observation_and_action_blocks(self):
        self.prepare();self.host.scene['revision']='r2'
        result=self.execute();self.assertEqual(result['status'],'blocked');self.assertEqual(self.host.calls,0)

    def test_action_collision_never_calls_host(self):
        self.prepare();result=self.execute(action={'translation':[0,0,-.15]})
        self.assertEqual(result['status'],'blocked');self.assertEqual(self.host.calls,0)

    def test_action_id_conflict_or_unknown_operation_blocks(self):
        self.prepare()
        for command in ({'translation':[0,0,.1],'focal_id':'base'},
                        {'translation':[0,0,.1],'scale':[1,1,1]},
                        {'translation':[float('nan'),0,0]}):
            self.assertEqual(self.execute(action=command)['status'],'invalid_action')
        self.assertEqual(self.host.calls,0)

    def test_any_uncertain_mutation_quarantines_all_sessions(self):
        for mode in ('cas_failure','partial_failure','readback_failure','incorrect',
                     'nonfocal_mutation','same_revision','topology_mutation','collision','color_mutation'):
            with self.subTest(mode=mode):
                self.setUp();self.prepare('a');self.prepare('b');self.host.mode=mode
                result=self.execute('a')
                self.assertFalse(result['verified']);self.assertTrue(self.runtime.status['quarantined'])
                before=self.host.calls
                self.assertEqual(self.execute('b')['status'],'host_quarantined')
                self.assertEqual(self.host.calls,before)
                with self.assertRaises(RuntimeError):self.prepare('new_session')

    def test_host_snapshot_failure_quarantines_connection(self):
        self.prepare();self.host.mode='capture_failure'
        self.assertEqual(self.execute()['status'],'host_snapshot_unavailable')
        self.assertTrue(self.runtime.status['quarantined']);self.assertEqual(self.host.calls,0)

    def test_float32_readback_within_explicit_bound(self):
        self.host.mode='float32';self.prepare()
        result=self.execute();self.assertTrue(result['verified'],result)
        self.assertEqual(self.runtime.status['readback_comparison_tolerance_m'],1e-6)

    def test_default_strict_router_and_invalid_tolerances(self):
        self.assertEqual(HumanEyeAutoRouter().readback_atol_m,1e-9)
        for value in (-1,1e-3,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):HumanEyeAutoRouter(readback_atol_m=value)

    def test_tolerance_does_not_allow_100_micrometre_error(self):
        self.host.mode='incorrect';self.prepare()
        self.assertFalse(self.execute()['verified']);self.assertTrue(self.runtime.status['quarantined'])

    def test_no_op_does_not_fabricate_host_revision(self):
        self.prepare();result=self.execute(action={'translation':[0,0,0]})
        self.assertEqual(result['status'],'no_op');self.assertFalse(result['executed'])
        self.assertEqual(self.host.calls,0);self.assertEqual(self.host.scene['revision'],'r1')
        self.assertEqual(self.execute()['status'],'observation_required')

    def test_administrative_reconcile_does_not_certify_failed_action(self):
        self.prepare();self.host.mode='partial_failure';self.execute()
        self.host.mode='normal'
        reconciled=self.runtime.reconcile_after_host_review()
        self.assertTrue(reconciled['reconciled']);self.assertFalse(reconciled['previous_action_verified'])
        self.assertEqual(self.execute()['status'],'observation_required')
        self.prepare();self.assertTrue(self.execute()['verified'])

    def test_reconcile_same_old_revision_cannot_clear_quarantine(self):
        self.prepare();self.host.mode='cas_failure';self.execute();self.host.mode='normal'
        with self.assertRaises(ValueError):self.runtime.reconcile_after_host_review()
        self.assertTrue(self.runtime.status['quarantined'])

    def test_preview_does_not_consume_observation_or_mutate_host(self):
        self.prepare();before=self.runtime.export_state()
        preview=self.runtime.preview_action(session_id='s',action={'translation':[0,0,.1]})
        self.assertTrue(preview['allow_action']);self.assertEqual(self.host.calls,0)
        self.assertEqual(self.runtime.export_state(),before)
        self.assertTrue(self.execute()['verified'])

    def test_runtime_persistence_keeps_observation_and_quarantine(self):
        self.prepare();state=self.runtime.export_state()
        other=GuardedHostRuntime(self.host,quad_size=64);other.import_state(state)
        result=other.execute_action(session_id='s',action={'translation':[0,0,.1]})
        self.assertTrue(result['verified'])
        self.setUp();self.prepare();self.host.mode='partial_failure';self.execute()
        quarantined=self.runtime.export_state()
        other=GuardedHostRuntime(self.host,quad_size=64);other.import_state(quarantined)
        self.assertEqual(other.execute_action(session_id='other',action={})['status'],'host_quarantined')
        clean=GuardedHostRuntime(self.host,quad_size=64).export_state();other.import_state(clean)
        self.assertTrue(other.status['quarantined'])

    def test_corrupt_runtime_quarantine_is_not_silently_reset(self):
        state=self.runtime.export_state()
        for bad in ({}, {'schema_version':'1.0','router':state['router'],'sessions':[]},
                    {**state,'quarantine':{}}, {**state,'quarantine':{'reason':'x'}}):
            with self.assertRaises(ValueError):self.runtime.import_state(bad)


if __name__=='__main__':unittest.main()
