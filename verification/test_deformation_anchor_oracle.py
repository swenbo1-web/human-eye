"""Authored analytic QA for independent public-anchor task answers."""
import copy,hashlib,unittest
from decimal import Decimal
from verification import deformation_anchor_oracle as o

I=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


class AnchorOracleTests(unittest.TestCase):
    def test_unicode_native_rig_and_bone_identity_uses_utf8_protocol(self):
        rig='blender:'+hashlib.sha256('["","骨架"]'.encode('utf8')).hexdigest()
        expected='bone-anchor:'+hashlib.sha256(('["'+rig+'","左臂","head"]').encode('utf8')).hexdigest()
        self.assertEqual(o.stable_object('骨架'),rig)
        self.assertEqual(o.anchor_id('骨架','左臂','head'),expected)
        self.assertEqual(o.encoded(dict(部位='左臂')),'{"部位":"左臂"}'.encode('utf8'))
        self.assertNotEqual(o.digest(['','骨架']),hashlib.sha256(b'["","\\u9aa8\\u67b6"]').hexdigest())

    def test_decimal_affine_and_outward_interval_preserve_binary_input_residual(self):
        m=copy.deepcopy(I);m[0][0]=.1;m[0][3]=-.01
        values=o.affine_decimal(m,[.1,0.,0.],1.)
        p,interval,reason=o.numeric_projection(values)
        self.assertIsNone(reason);self.assertNotEqual(p[0],0.)
        self.assertLessEqual(Decimal.from_float(interval[0][0]),values[0]);self.assertGreaterEqual(Decimal.from_float(interval[1][0]),values[0])

    def test_identity_is_native_name_and_endpoint_not_position(self):
        a=o.anchor_id('Armature','Bone','tail');b=o.anchor_id('Armature','Bone.001','head')
        self.assertNotEqual(a,b);self.assertEqual(a,o.anchor_id('Armature','Bone','tail'))
        self.assertNotEqual(a,o.anchor_id('OtherRig','Bone','tail'))

    def test_exact_domain_violation_cannot_round_back_into_supported_domain(self):
        value=Decimal('1000000000.000000000000000000000000001')
        self.assertEqual(float(value),1e9)
        self.assertEqual(o.numeric_projection([value,Decimal(0),Decimal(0)]),(None,None,'outside_region_coordinate_domain'))

    def test_task_relationships_reject_ambiguity_missing_and_anatomy(self):
        root=dict(name='Bone',parent=None,head_anchor_id='rh',tail_anchor_id='rt');child=dict(name='Bone.001',parent='Bone',head_anchor_id='ch',tail_anchor_id='ct')
        cat=dict(graph=[root,child]);self.assertEqual(o.resolve_task(cat,'unique_nonroot_head'),dict(state='selected',anchor_id='ch'))
        self.assertEqual(o.resolve_task(cat,'named_Bone_tail'),dict(state='selected',anchor_id='rt'))
        self.assertEqual(o.resolve_task(cat,'named_MissingBone_head')['state'],'not_found')
        self.assertEqual(o.resolve_task(cat,'elbow_semantics_without_mapping')['state'],'unsupported_semantics')
        cat['graph'].append(dict(root,name='OtherRoot'))
        self.assertEqual(o.resolve_task(cat,'unique_root_tail')['state'],'ambiguous')

    def test_box_is_outward_rounded_around_public_binary64_point(self):
        point=dict(position_world_m=[.1,0.,-.1]);region=o.expected_box(point,[.2,.5,.2])
        self.assertEqual(region['bounds'][0],[-.1,-.5,-.30000000000000004])
        self.assertEqual(region['bounds'][1],[.30000000000000004,.5,.1])

    def test_bounds_use_complete_referenced_vertices_and_count_loose(self):
        b=dict(name='Bone',parent=None,connected=False,use_deform=True,length=1.,pose_matrix=copy.deepcopy(I),pose_head=[0.,0.,0.],pose_tail=[0.,1.,0.])
        p=dict(inputs=dict(rig=dict(name='Armature',bones=[b]),unit_scale_m=1.,mesh=dict(triangles=[[0,1,2]])),
            evaluated=dict(rig_matrix_world=copy.deepcopy(I),mesh_matrix_world=copy.deepcopy(I),bones=[copy.deepcopy(b)],vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[9.,9.,9.]]))
        r=o.expected_geometry(p);self.assertEqual(r['bounds_world_m'],[[0.,0.,0.],[1.,1.,0.]])
        self.assertEqual((r['surface_vertices_total'],r['loose_vertices_excluded']),(3,1));self.assertEqual(r['maximum_pose_endpoint_crosscheck'],0.)


if __name__=='__main__':unittest.main()
