"""Real preparation limits retain their causes without host writes or journals.

These fixtures construct actual closed mesh surfaces. No budget, clearance,
router or host gate is stubbed. Only persistence is observed while its original
writer still performs every write, to detect even a transient inflight journal.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.geometry_safety import work_budget_status
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_host_runtime import MutableHost, SIGNS, FACES


def closed_prism(object_id, sides, center_z, *, focal=False):
    """Closed convex prism, 2N vertices and 4N-4 outward triangles."""
    radius, half_height = .04, .01
    vertices = np.array([[radius*math.cos(i*math.tau/sides),
                          radius*math.sin(i*math.tau/sides), z+center_z]
                         for z in (-half_height,half_height) for i in range(sides)])
    faces = [(0,i+1,i) for i in range(1,sides-1)]
    faces += [(sides,sides+i,sides+i+1) for i in range(1,sides-1)]
    for i in range(sides):
        following = (i+1)%sides
        faces.extend(((i,following,following+sides),(i,following+sides,i+sides)))
    return MeshEntity3D(object_id,'#'+object_id,object_id,vertices,np.asarray(faces),
                        None,(70,140,210),focal,local_axes=np.eye(3),
                        pivot_world=np.array([0.,0.,center_z])).to_dict()


class PreparationRejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config_path = self.directory/'live.json'
        self.config_path.write_text(json.dumps(dict(schema_version='1.0',
            project_root=str(Path(__file__).resolve().parents[1]), state_file='state.json',
            audit_file='events.jsonl', quad_size=64, max_sessions=4, enabled=True)),encoding='utf-8')
        self.host = MutableHost()
        self.service = LiveSpatialService(self.config_path,host=self.host)
        self.action = dict(focal_id='part',reference_id='base',translation=[0,0,-.001])

    def install_prisms(self,sides):
        self.host.scene['meshes'] = [closed_prism('base',sides,-.01),
                                     closed_prism('part',sides,.012,focal=True)]

    def install_ambiguous_frame(self):
        # Equal in-plane dimensions have no uniquely inferred tangent axes.
        # The geometry/provenance implementation itself derives ambiguity.
        center = np.array([0.,0.,.35])
        self.host.scene['meshes'][1] = MeshEntity3D('part','#part','part',
            SIGNS*np.array([.2,.2,.1])/2+center,np.asarray(FACES),
            None,(70,140,210),True,pivot_world=center).to_dict()
        self.assertEqual(self.host.scene['meshes'][1]['axes_confidence'],'ambiguous')
        self.action['translation'] = [0,0,.001]

    def call_recording_all_state_writes(self,operation):
        from human_eye_plugin.live_service import _atomic_write
        writes = []
        def save(path,value,**kwargs):
            writes.append(copy.deepcopy(value))
            return _atomic_write(path,value,**kwargs)
        with patch('human_eye_plugin.live_service._atomic_write',side_effect=save):
            value = getattr(self.service,operation)('preparation',self.action)
        return value,writes

    def assert_known_rejection_without_journal(self,value,writes,before,operation):
        self.assertEqual(value['status'],'blocked',value)
        self.assertIs(value['allow_action'],False,value)
        self.assertIs(value.get('executed'),False,value)
        self.assertEqual(value['execution_status'],
                         'not_requested' if operation == 'preview_action' else 'not_executed',value)
        self.assertEqual(self.host.calls,0)
        self.assertEqual(self.host.scene,before)
        self.assertEqual(self.host.captures,1)
        self.assertTrue(writes,'Known rejection should persist its non-actionable state')
        for saved in writes:
            self.assertIsNone(saved['inflight'],'A known prep failure must never create even a transient journal')
            self.assertIsNone(saved['runtime']['quarantine'])
            self.assertEqual(saved['runtime']['sessions'],[])
        state = json.loads((self.directory/'state.json').read_text(encoding='utf-8'))
        self.assertIsNone(state['inflight'])
        self.assertIsNone(state['runtime']['quarantine'])
        self.assertEqual(state['runtime']['sessions'],[])
        return value['routing']

    def assert_real_sat_budget_rejection(self,operation):
        self.install_prisms(16)
        before = copy.deepcopy(self.host.scene)
        value,writes = self.call_recording_all_state_writes(operation)
        route = self.assert_known_rejection_without_journal(value,writes,before,operation)
        self.assertEqual(route['route'],'blocked')
        self.assertIn('geometry_resource_limit',route['reason_codes'])
        self.assertIn('geometry_resource_limit',value['reason_codes'])
        budget = route['geometry_work_budget']
        self.assertIs(budget['within_budget'],False)
        self.assertIn('sat_projection_work_limit',budget['reason_codes'])
        self.assertGreater(budget['estimates']['largest_sat_projection_elements'],
                           budget['limits']['sat_projection_elements'])
        self.assertNotIn('observation_required',value['reason_codes'])

    def assert_ambiguous_frame_rejection(self,operation):
        self.install_ambiguous_frame()
        before = copy.deepcopy(self.host.scene)
        value,writes = self.call_recording_all_state_writes(operation)
        route = self.assert_known_rejection_without_journal(value,writes,before,operation)
        self.assertIs(route['rigid_frame_valid'],False)
        self.assertTrue({'rigid_frame_unverified','unverified_geometry_or_frame'}
                        .intersection(value['reason_codes']),value)
        evidence = route.get('rigid_frame')
        self.assertIsInstance(evidence,dict)
        self.assertIn('ambiguous',json.dumps(evidence,sort_keys=True))
        self.assertIn('axes_source_not_host',evidence['objects']['focal']['reason_codes'])
        self.assertIn('axes_not_explicit',evidence['objects']['focal']['reason_codes'])
        self.assertNotIn('observation_required',value['reason_codes'])
        # axes_valid is the legacy contact-display contract, deliberately not
        # the assertion or authorization criterion for this regression.

    def test_real_15_16_side_meshes_straddle_published_pair_budget(self):
        for sides,expected in ((15,True),(16,False)):
            with self.subTest(sides=sides):
                self.install_prisms(sides)
                meshes = [MeshEntity3D.from_dict(item) for item in self.host.scene['meshes']]
                self.assertEqual([len(m.vertices) for m in meshes],[2*sides,2*sides])
                self.assertEqual([len(m.faces) for m in meshes],[4*sides-4,4*sides-4])
                self.assertIs(work_budget_status(meshes,query_pairs=[],purpose='mesh_validation')['within_budget'],True)
                result = work_budget_status(meshes,query_pairs=[['part','base']])
                self.assertIs(result['within_budget'],expected,result)
                self.assertEqual(result['reason_codes'],[] if expected else ['sat_projection_work_limit'])

    def test_transform_keeps_real_sat_preparation_failure_without_journal(self):
        self.assert_real_sat_budget_rejection('transform')

    def test_preview_keeps_real_sat_preparation_failure_without_journal(self):
        self.assert_real_sat_budget_rejection('preview_action')

    def test_transform_keeps_ambiguous_frame_failure_without_journal(self):
        self.assert_ambiguous_frame_rejection('transform')

    def test_preview_keeps_ambiguous_frame_failure_without_journal(self):
        self.assert_ambiguous_frame_rejection('preview_action')

    def test_15_side_control_can_transform_actual_mesh_with_same_policy(self):
        self.install_prisms(15)
        result = self.service.transform('control',self.action)
        self.assertIs(result['executed'],True,result)
        self.assertIs(result['verified'],True,result)
        self.assertEqual(self.host.calls,1)
        part,base = [np.asarray(self.host.scene['meshes'][index]['vertices']) for index in (1,0)]
        self.assertAlmostEqual(float(part[:,2].min()-base[:,2].max()),.001,places=12)
        saved = json.loads((self.directory/'state.json').read_text(encoding='utf-8'))
        self.assertIsNone(saved['inflight'])
        self.assertIsNone(saved['runtime']['quarantine'])

    def test_15_side_control_preview_is_allowed_without_host_assignment(self):
        self.install_prisms(15)
        before = copy.deepcopy(self.host.scene)
        result = self.service.preview_action('control',self.action,include_image=False)
        self.assertIs(result['allow_action'],True,result)
        self.assertEqual(self.host.calls,0)
        self.assertEqual(self.host.scene,before)
        saved = json.loads((self.directory/'state.json').read_text(encoding='utf-8'))
        self.assertIsNone(saved['inflight'])
        self.assertIsNone(saved['runtime']['quarantine'])


if __name__ == '__main__':
    unittest.main()
