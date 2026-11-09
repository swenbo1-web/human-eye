"""The owned fifth dependency must leave the four-source read path intact."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import threading
import unittest

from human_eye_plugin.blender_host import BlenderSceneHost

ROOT=Path(__file__).resolve().parents[2]


class ReadCompatibilityTests(unittest.TestCase):
    def test_four_source_snapshot_remains_independent_of_execution_snapshot(self):
        host=BlenderSceneHost.__new__(BlenderSceneHost)
        names=('rig_pose.py','arm_twist_weights.py','arm_twist_expert.py','arm_twist_source.py')
        original={name:(ROOT/'human_eye_plugin'/name).read_bytes() for name in names}
        host._arm_twist_dependency_sources=dict(original)
        read=host._arm_twist_source_module()
        execution=host._arm_twist_source_module(execution=True)
        self.assertIs(host._arm_twist_source_module(),read)
        self.assertIs(host._arm_twist_source_module(execution=True),execution)
        self.assertIsNot(read,execution)
        self.assertEqual(host._arm_twist_dependency_sources,original)
        self.assertEqual(set(host._arm_twist_dependency_sources),set(names))
        self.assertIs(host._arm_correction_preview,host._arm_correction_module.preview_axial_redistribution)

    def test_existing_read_entry_forwards_once_without_correction(self):
        host=BlenderSceneHost.__new__(BlenderSceneHost);host._lock=threading.RLock()
        selection={'mesh_name':'Arm','armature_name':'Rig','bone_names':['a','b','c'],
                   'vertex_indices':[0,1,2,3,4,5],'sections':[[0,1,2],[3,4,5]]}
        calls=[]
        class Bound:
            _selection=deepcopy(selection)
            def analyze(self):calls.append('analyze');return {'status':'estimated','scope':'fake_read_dispatch'}
        class Adapter:
            def bind(self,value):calls.append('bind');return Bound()
        host._arm_twist_adapter=Adapter()
        self.assertEqual(host.observe_arm_twist(selection)['status'],'estimated')
        self.assertEqual(host.observe_arm_twist(selection)['status'],'estimated')
        self.assertEqual(calls,['bind','analyze','analyze'])
        self.assertFalse(hasattr(host,'_last_arm_axial_audit'))


if __name__=='__main__':unittest.main()
