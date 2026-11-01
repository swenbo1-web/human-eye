"""Analytic surface truth and real service/MCP reads; no Blender writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from human_eye_plugin.geometry_safety import (
    measure_pair_geometry, _surface_distance_with_witness,
)
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.task_verification import evaluate_spatial_goal
from verification.test_concave_geometry import box, entity, ring
from verification.test_live_service import SelfLockingHost


def extra(mesh, point, *, first=False):
    vertices = np.vstack(([point], mesh.vertices)) if first else np.vstack((mesh.vertices, point))
    return entity(mesh.object_id, vertices, mesh.faces + int(first))


class SurfaceScopeRegressionTests(unittest.TestCase):
    def pair(self):
        return box((.5,.5,.5),(1,1,1),'part'), box((2.5,.5,.5),(1,1,1),'base')

    def test_isolated_points_cannot_change_certified_surface_gap(self):
        a,b = self.pair()
        for point in ((2,.5,.5),(2.5,.5,.5),(1e20,1e20,1e20)):
            for first in (False,True):
                for reverse in (False,True):
                    with self.subTest(point=point,first=first,reverse=reverse):
                        modified=extra(a,point,first=first)
                        left,right=(b,modified) if reverse else (modified,b)
                        before=modified.to_dict()
                        result=measure_pair_geometry(left,right,need_clearance=True)
                        self.assertTrue(result['measurement_valid'],result)
                        self.assertAlmostEqual(result['signed_clearance_m'],1.,places=12)
                        self.assertFalse(result['is_penetrating'])
                        self.assertIn('triangle_surface_only',result['geometry_scope'])
                        self.assertEqual(modified.to_dict(),before)

    def test_witness_origin_and_features_are_on_referenced_surface(self):
        a,b=self.pair()
        for first in (False,True):
            distance,p,q=_surface_distance_with_witness(extra(a,(1e20,1e20,1e20),first=first),b)
            self.assertAlmostEqual(distance,1.,places=12)
            self.assertAlmostEqual(p[0],1.,places=12)
            self.assertAlmostEqual(q[0],2.,places=12)
            self.assertAlmostEqual(float(np.linalg.norm(np.array(p)-q)),1.,places=12)

    def test_reordering_and_component_union_preserve_gap(self):
        a,b=self.pair()
        vertices=np.vstack((a.vertices,a.vertices+[0,4,0],[[2,.5,.5]]))
        faces=np.vstack((a.faces,a.faces+8))
        rng=np.random.default_rng(1101)
        for iteration in range(4):
            order=rng.permutation(len(vertices)); inverse=np.argsort(order)
            modified=entity('part',vertices[order],inverse[faces[rng.permutation(len(faces))]])
            result=measure_pair_geometry(modified,b,need_clearance=True)
            self.assertTrue(result['measurement_valid'],result)
            self.assertAlmostEqual(result['signed_clearance_m'],1.,places=12)

    def test_contact_and_penetration_do_not_use_far_isolated_vertex(self):
        a,_=self.pair()
        for center,penetrating in ((1.5,False),(1.,True)):
            with self.subTest(center=center):
                b=box((center,.5,.5),(1,1,1),'base')
                result=measure_pair_geometry(extra(a,(20,20,20)),b,need_clearance=True)
                self.assertTrue(result['measurement_valid'],result)
                self.assertEqual(result['is_penetrating'],penetrating)
                self.assertLessEqual(result['signed_clearance_m'],0.)

    def test_concave_orphan_domain_stays_explicitly_unknown(self):
        result=measure_pair_geometry(box(),extra(ring(),(.006,0,0)),need_clearance=True)
        self.assertFalse(result['measurement_valid'])
        self.assertIsNone(result['signed_clearance_m'])

    def test_service_mcp_and_zero_goal_cannot_report_false_contact(self):
        a,b=self.pair()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64}),encoding='utf8')
            # Host inputs are canonical metres; millimetre source assets must
            # be converted at capture, never relabelled as metre coordinates.
            for unit,scale in (('m',1.),('mm',.001)):
                with self.subTest(unit=unit):
                    host=SelfLockingHost()
                    modified=extra(a,(2,.5,.5))
                    # A loose edge is not an additional solid surface.
                    modified.edges=np.vstack((modified.edges,[[0,8]]))
                    meshes=[modified.to_dict(),b.to_dict()]
                    for mesh in meshes:
                        mesh['vertices']=(np.array(mesh['vertices'])*scale).tolist()
                        mesh['pivot_world']=(np.array(mesh['pivot_world'])*scale).tolist()
                    host.scene.update(revision='surface-'+unit,unit='m',meshes=meshes)
                    goal={'focal_id':'part','reference_id':'base','target_clearance_m':0.,'clearance_tolerance_m':1e-6}
                    before=copy.deepcopy(host.scene)
                    direct=evaluate_spatial_goal(host.scene,goal)
                    self.assertFalse(direct['task_succeeded'],direct)
                    self.assertAlmostEqual(direct['measurements']['signed_clearance_m'],scale,places=12)
                    service=LiveSpatialService(path,host=host)
                    observed=service.observe('surface',focal_id='part',reference_id='base',goal=goal,
                        include_image=False,query={'alignment_evidence':False})
                    self.assertFalse(observed['task_succeeded'],observed)
                    self.assertAlmostEqual(observed['goal_verification']['measurements']['signed_clearance_m'],scale,places=12)
                    # Exercise the production MCP projection over the real service.
                    server=LiveSpatialMCPServer(service,default_session_id='surface')
                    result=server.handle_jsonrpc_message({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
                        'name':'human_eye_scene_observe','arguments':{'focal_id':'part','reference_id':'base',
                            'goal':goal,'include_image':False,'query':{'alignment_evidence':False}}}})['result']
                    self.assertFalse(result.get('isError',False),result)
                    text='\n'.join(item['text'] for item in result['content'] if item['type']=='text')
                    self.assertIn('"task_succeeded": false',text)
                    self.assertEqual(host.calls,0)
                    self.assertEqual(host.scene,before)


if __name__=='__main__':unittest.main()
