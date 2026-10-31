import copy,unittest,time
from types import SimpleNamespace as NS
from human_eye_plugin import mesh_structure as m
from verification.test_host_identity_contract import identity_host
from verification.test_mesh_structure_runtime import raw_case
from verification.mesh_structure_fixtures import fixtures


def fixture():
    host,obj,other,graph=identity_host();value=raw_case(fixtures()[1])
    obj.data.vertices=[NS(co=v[:]) for v in value['vertices']]
    obj.data.edges=[NS(vertices=e[:]) for e in value['edges']]
    obj.data.polygons=[NS(vertices=p[:]) for p in value['polygons']]
    obj.data.loops=[None]*sum(map(len,value['polygons']));obj.data.session_uid=303;obj.data.library=None
    return host,obj,other


class MeshStructureHostTests(unittest.TestCase):
    def test_unrelated_unsupported_geometry_does_not_imply_visibility_coverage(self):
        host,obj,other=fixture();other.type='CURVE'
        value=m.observe_raw(host,host.object_id(obj),request_id='t')
        self.assertEqual(value['report']['source']['capture_scope'],'target_mesh_only')
        self.assertEqual(value['report']['natural_visibility'],'not_checked')
        self.assertEqual(obj.assignments,0);self.assertEqual(obj.clears,0)

    def test_static_source_restrictions(self):
        for field in ('mode','modifier','parent','shape_keys','library','data_library','instance','animation'):
            host,obj,_=fixture()
            if field=='mode':obj.mode='EDIT'
            elif field=='modifier':obj.modifiers=[NS(name='subdivision',type='SUBSURF')]
            elif field=='parent':obj.parent=NS(name='parent')
            elif field=='shape_keys':obj.data.shape_keys=object()
            elif field=='library':obj.library=NS(filepath='linked.blend')
            elif field=='data_library':obj.data.library=NS(filepath='linked.blend')
            elif field=='instance':obj.instance_type='COLLECTION'
            else:obj.animation_data=object()
            with self.subTest(field=field),self.assertRaises(m.StructureRefused):
                m.observe_raw(host,host.object_id(obj),request_id='t')

    def test_same_name_recreation_and_data_replacement_change_source(self):
        host,obj,_=fixture();oid=host.object_id(obj)
        a=m.capture_raw(host,oid)['source'];obj.session_uid+=100
        b=m.capture_raw(host,oid)['source'];obj.data.session_uid+=100
        c=m.capture_raw(host,oid)['source']
        self.assertEqual(a['object_id'],b['object_id'])
        self.assertNotEqual(a['object_instance'],b['object_instance']);self.assertNotEqual(b['object_instance'],c['object_instance'])
        self.assertNotEqual(a['raw_sha256'],b['raw_sha256']);self.assertNotEqual(b['raw_sha256'],c['raw_sha256'])

    def test_transform_locks_do_not_make_read_only_source_unreadable(self):
        host,obj,_=fixture();obj.lock_location=(True,True,True)
        self.assertEqual(m.observe_raw(host,host.object_id(obj),request_id='t')['status'],'observed')

    def test_missing_target_and_missing_datablock_identity_rejected(self):
        host,obj,_=fixture()
        with self.assertRaises(m.StructureRefused):m.capture_raw(host,'missing')
        del obj.data.session_uid
        with self.assertRaises(m.StructureRefused):m.capture_raw(host,host.object_id(obj))

    def test_actual_source_change_during_capture_rejected(self):
        host,obj,_=fixture()
        class ChangeOnRead:
            def __iter__(self):
                obj.data.session_uid+=1
                return iter([0.,0.,0.])
        obj.data.vertices[0].co=ChangeOnRead()
        with self.assertRaisesRegex(m.StructureRefused,'source_changed'):
            m.capture_raw(host,host.object_id(obj))

    def test_geometry_counts_checked_before_reading(self):
        host,obj,_=fixture()
        class TooMany:
            def __len__(self):return m.LIMITS['vertices']+1
            def __getitem__(self,key):raise AssertionError('must not allocate/read')
        obj.data.vertices=TooMany()
        with self.assertRaisesRegex(m.StructureRefused,'geometry_budget'):
            m.capture_raw(host,host.object_id(obj))


if __name__=='__main__':unittest.main()
