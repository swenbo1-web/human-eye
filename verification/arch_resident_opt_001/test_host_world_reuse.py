"""Targeted bpy-double tests for metadata/physical-pose world reuse only."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from verification.arch_resident_001.test_residency_contract import (
    make_host, selected, by_name, notify_geometry)


class HostWorldReuseTests(unittest.TestCase):
    def setUp(self):
        self.host,self.focal,self.reference,self.graph=make_host()
        self.addCleanup(self.host.close_residency)

    def work(self):return self.host.residency_work()

    def assert_work(self,before,*,world=0,resource=0):
        after=self.work()
        self.assertEqual(after['world_transforms']-before['world_transforms'],world)
        self.assertEqual(after['resource_builds']-before['resource_builds'],resource)
        self.assertEqual(after['to_mesh']-before['to_mesh'],resource)
        self.assertEqual(after['triangulations']-before['triangulations'],resource)

    def test_color_only_updates_metadata_without_world_or_resource_work(self):
        first=selected(self.host);before=self.work()
        self.focal.color=(1.,0.,0.,1.)
        after=selected(self.host)
        self.assert_work(before)
        self.assertEqual(by_name(after,'Focal')['color_rgb'],[255,0,0])
        self.assertEqual(by_name(after,'Focal')['vertices'],by_name(first,'Focal')['vertices'])
        self.assertNotEqual(first['capture_state'],after['capture_state'])
        self.assertEqual(by_name(first,'Focal')['color_rgb'],[128,64,255])

    def test_name_only_updates_identity_and_old_binding_without_world_work(self):
        first=selected(self.host);before=self.work()
        self.focal.name=self.focal.name_full='Renamed'
        after=selected(self.host,('Renamed','Reference'))
        self.assert_work(before)
        self.assertNotEqual(by_name(first,'Focal')['object_id'],by_name(after,'Renamed')['object_id'])
        self.assertEqual(by_name(first,'Focal')['vertices'],by_name(after,'Renamed')['vertices'])
        self.assertEqual(after['task_selection']['bindings'][0]['name'],'Renamed')
        self.assertEqual(selected(self.host)['task_selection']['bindings'][0]['reason'],'object_not_found')

    def test_parent_and_child_renames_are_metadata_without_resource_work(self):
        self.reference.parent=self.focal;self.focal.children=[self.reference]
        selected(self.host);before=self.work()
        self.focal.name=self.focal.name_full='ParentRenamed'
        self.reference.name=self.reference.name_full='ChildRenamed'
        result=selected(self.host,('ParentRenamed','ChildRenamed'))
        self.assert_work(before)
        self.assertEqual({m['name'] for m in result['meshes']},{'ParentRenamed','ChildRenamed'})

    def test_active_only_refreshes_focal_flags_without_world_work(self):
        first=selected(self.host);before=self.work()
        self.host.view_layer.objects.active=self.reference
        after=selected(self.host)
        self.assert_work(before)
        self.assertTrue(by_name(first,'Focal')['is_focal_target'])
        self.assertFalse(by_name(after,'Focal')['is_focal_target'])
        self.assertTrue(by_name(after,'Reference')['is_focal_target'])

    def test_cross_selection_ordinals_are_independent_and_do_not_transform(self):
        full=selected(self.host);before=self.work()
        singleton=selected(self.host,('Reference',))
        self.assert_work(before)
        self.assertEqual(by_name(singleton,'Reference')['mark_label'],'#B0001')
        self.assertEqual(selected(self.host),full)
        self.assert_work(before)
        self.assertEqual(len({m['mark_label'] for m in full['meshes']}),2)

    def test_single_pose_updates_only_affected_world_and_matches_fresh_math(self):
        first=selected(self.host);before=self.work()
        self.focal._matrix_world[0][3]+=0.375
        after=selected(self.host)
        self.assert_work(before,world=1)
        self.assertEqual(by_name(after,'Reference'),by_name(first,'Reference'))
        fresh=self.host._capture(_task_selectors=[{'name':'Focal'},{'name':'Reference'}])
        without_state={k:v for k,v in after.items() if k!='capture_state'}
        self.assertEqual(without_state,fresh)

    def test_single_mesh_event_updates_only_affected_resource_and_world(self):
        first=selected(self.host);before=self.work()
        self.focal.data.vertices[0].co=(0.25,0.,0.)
        notify_geometry(self.host,self.graph,self.focal,via_data=True)
        after=selected(self.host)
        self.assert_work(before,world=1,resource=1)
        self.assertEqual(by_name(after,'Focal')['vertices'][0],[2.25,3.,4.])
        self.assertEqual(by_name(after,'Reference'),by_name(first,'Reference'))
        self.assertEqual(by_name(after,'Focal')['faces'],by_name(first,'Focal')['faces'])

    def test_same_object_mesh_and_pose_change_compute_world_once(self):
        selected(self.host);before=self.work()
        self.focal.data.vertices[0].co=(0.25,0.,0.)
        self.focal._matrix_world[1][3]+=0.5
        notify_geometry(self.host,self.graph,self.focal,via_data=True)
        result=selected(self.host)
        self.assert_work(before,world=1,resource=1)
        self.assertEqual(by_name(result,'Focal')['vertices'][0],[2.25,3.5,4.])

    def test_unit_scale_updates_worlds_but_reuses_local_resources(self):
        first=selected(self.host);before=self.work()
        self.host.scene.unit_settings.scale_length=0.5
        after=selected(self.host)
        self.assert_work(before,world=2)
        self.assertEqual(by_name(after,'Focal')['vertices'],
                         [[v*0.5 for v in p] for p in by_name(first,'Focal')['vertices']])

    def test_metadata_capture_and_old_tokens_remain_detached(self):
        first=selected(self.host);saved=copy.deepcopy(first)
        self.focal.color=(1.,1.,0.,1.)
        after=selected(self.host);before=self.work()
        self.assertEqual(first,saved)
        self.assertNotIn('schema',self.host.capture_delta(first,None))
        after['meshes'][0]['vertices'][0][0]=999.
        after['meshes'][0]['faces'][0][0]=999
        again=selected(self.host)
        self.assert_work(before)
        self.assertNotEqual(again['meshes'][0]['vertices'][0][0],999.)
        self.assertNotEqual(again['meshes'][0]['faces'][0][0],999)

    def test_native_and_write_keep_fresh_capture_math(self):
        before=self.host.capture_scene();work=self.work()
        native=self.host.capture_evidence()
        self.assertNotIn('capture_state',native['capture'])
        self.assertEqual(native['capture'],{k:v for k,v in before.items() if k!='capture_state'})
        self.assert_work(work)
        result=self.host.apply_transform({'focal_id':self.host.object_id(self.focal),
            'translation':[0.25,0.,0.]},before['revision'])
        self.assertNotIn('capture_state',result['scene'])
        after=self.host.capture_scene()
        self.assert_work(work,world=1)
        self.assertEqual({k:v for k,v in after.items() if k!='capture_state'},result['scene'])


if __name__=='__main__':unittest.main(verbosity=2)
