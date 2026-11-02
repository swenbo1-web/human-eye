"""Poisoned collections and actual capture ordering, plus independent quaternion QA."""
import ast,copy,math,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from human_eye_plugin import small_skin_source_worker as worker
from verification.run_source_precheck_preflight import quaternion_rotation,raw_component_values,FIRST,LAST,VERTICES
N=types.SimpleNamespace

class PoisonCollection:
    def __init__(self,count):self.count=count;self.len_reads=0;self.iterations=0
    def __len__(self):self.len_reads+=1;return self.count
    def __iter__(self):self.iterations+=1;raise AssertionError('full array iteration happened before precheck')
    def __getitem__(self,index):raise AssertionError('array materialized before precheck')


def fixture(vertices=4,polygons=2,bones=1,ev_vertices=None,ev_polygons=None,ev_bones=None):
    rig=N(data=N(bones=PoisonCollection(bones)))
    mod=N(type='ARMATURE',object=rig,use_deform_preserve_volume=False,use_bone_envelopes=False,use_multi_modifier=False,invert_vertex_group=False,
        vertex_group='',use_vertex_groups=True,show_render=True,show_viewport=True,is_override_data=False)
    mesh=N(data=N(vertices=PoisonCollection(vertices),polygons=PoisonCollection(polygons),edges=PoisonCollection(5),shape_keys=None,as_pointer=lambda:1),modifiers=[mod])
    em=N(data=N(vertices=PoisonCollection(vertices if ev_vertices is None else ev_vertices),polygons=PoisonCollection(polygons if ev_polygons is None else ev_polygons),as_pointer=lambda:2),original=mesh,is_evaluated=True)
    er=N(pose=N(bones=PoisonCollection(bones if ev_bones is None else ev_bones)),original=rig,is_evaluated=True)
    rig.evaluated_get=lambda graph:er;mesh.evaluated_get=lambda graph:em
    return mesh,rig,em,er


def actual_capture(mesh,rig):
    """Compile the production capture function unchanged; inject only its closure.

    This executes the real call order. Moving a guard behind array expansion or
    depsgraph access makes the poison/call assertions fail, even if helpers pass.
    """
    tree=ast.parse(Path(worker.__file__).read_bytes());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    capture=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='capture');calls=[]
    def mark(kind,value):calls.append(kind);return value
    env=dict(Path=Path,check=worker.check,require=worker.require,precheck_dependencies=worker.precheck_dependencies,precheck_evaluated=worker.precheck_evaluated,LIMITS=worker.LIMITS,
        deadline=time.perf_counter_ns()+2_000_000_000,runtime=N(check_source_drift=lambda:{'compatible':True}),sha=lambda path:'fixed',
        p=dict(scene_file='fake.blend',scene_sha256='fixed',expected_frame=dict(number=13,subframe=0.),unit_scale_m=1.),
        scene=N(frame_current=13,frame_subframe=0.,unit_settings=N(scale_length=1.)),mesh=mesh,rig=rig,
        independent_audit=lambda:mark('audit',{}),state=lambda:mark('state',{}),bpy=N(context=N(evaluated_depsgraph_get=lambda:mark('depsgraph',object()))))
    exec(compile(ast.Module(body=[capture],type_ignores=[]),'<actual-worker-capture>','exec'),env)
    return env['capture'],calls


class SourcePrecheckTests(unittest.TestCase):
    def test_supported_counts_only_read_lengths(self):
        mesh,rig,em,er=fixture();deadline=time.perf_counter_ns()+1_000_000_000
        worker.precheck_dependencies(mesh,rig,deadline);worker.precheck_evaluated(mesh,rig,em,er,deadline)
        for collection in (mesh.data.vertices,mesh.data.polygons,rig.data.bones,em.data.vertices,em.data.polygons,er.pose.bones):
            self.assertGreater(collection.len_reads,0);self.assertEqual(collection.iterations,0)

    def test_evaluated_vertex_count_refuses_without_array_expansion(self):
        for count in (0,3,5,257,10000000):
            mesh,rig,em,er=fixture(ev_vertices=count)
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'^small_skin_evaluated_vertex_count$'):
                worker.precheck_evaluated(mesh,rig,em,er,time.perf_counter_ns()+1_000_000_000)
            self.assertEqual(em.data.vertices.iterations,0)

    def test_evaluated_topology_count_refuses_without_array_expansion(self):
        for count in (0,1,3,257,10000000):
            mesh,rig,em,er=fixture(ev_polygons=count)
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'^small_skin_evaluated_topology$'):
                worker.precheck_evaluated(mesh,rig,em,er,time.perf_counter_ns()+1_000_000_000)
            self.assertEqual(em.data.polygons.iterations,0)

    def test_evaluated_bone_count_refuses_without_array_expansion(self):
        for count in (0,2,17,10000000):
            mesh,rig,em,er=fixture(ev_bones=count)
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'^small_skin_evaluated_bone_count$'):
                worker.precheck_evaluated(mesh,rig,em,er,time.perf_counter_ns()+1_000_000_000)
            self.assertEqual(er.pose.bones.iterations,0)

    def test_maximum_matching_counts_are_supported_without_iteration(self):
        mesh,rig,em,er=fixture(vertices=256,polygons=256,bones=16)
        worker.precheck_evaluated(mesh,rig,em,er,time.perf_counter_ns()+1_000_000_000)
        self.assertEqual(em.data.vertices.iterations+em.data.polygons.iterations+er.pose.bones.iterations,0)

    def test_dependencies_precise_domain_exits_before_depsgraph(self):
        cases=[('shape_keys',lambda m,r:setattr(m.data,'shape_keys',object())),('modifier_count',lambda m,r:m.modifiers.append(m.modifiers[0])),
            ('modifier_binding',lambda m,r:setattr(m.modifiers[0],'type','SUBSURF')),('modifier_binding',lambda m,r:setattr(m.modifiers[0],'object',object())),
            ('DQ',lambda m,r:setattr(m.modifiers[0],'use_deform_preserve_volume',True)),('envelopes',lambda m,r:setattr(m.modifiers[0],'use_bone_envelopes',True))]
        for field in ('use_multi_modifier','invert_vertex_group','vertex_group','use_vertex_groups','show_render','show_viewport','is_override_data'):
            value='mask' if field=='vertex_group' else field in ('use_multi_modifier','invert_vertex_group','is_override_data')
            cases.append(('modifier_semantics',lambda m,r,key=field,value=value:setattr(m.modifiers[0],key,value)))
        for reason,change in cases:
            mesh,rig,em,er=fixture();change(mesh,rig);capture,calls=actual_capture(mesh,rig)
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'^small_skin_'+reason+'$'):capture()
            self.assertEqual(calls,[],'unsupported dependencies cannot cause state expansion or depsgraph evaluation')
            self.assertEqual(mesh.data.vertices.iterations+mesh.data.polygons.iterations+em.data.vertices.iterations,0)

    def test_actual_capture_evaluated_precheck_precedes_expansion(self):
        for changes,reason in [({'ev_vertices':257},'evaluated_vertex_count'),({'ev_polygons':257},'evaluated_topology'),({'ev_bones':17},'evaluated_bone_count')]:
            mesh,rig,em,er=fixture(**changes);capture,calls=actual_capture(mesh,rig)
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'^small_skin_'+reason+'$'):capture()
            self.assertEqual(calls,['audit','state','depsgraph'])
            self.assertEqual(em.data.vertices.iterations+em.data.polygons.iterations+er.pose.bones.iterations,0)

    def test_both_helpers_check_original_deadline_before_any_count(self):
        mesh,rig,em,er=fixture()
        for helper,args in ((worker.precheck_dependencies,(mesh,rig)),(worker.precheck_evaluated,(mesh,rig,em,er))):
            with self.subTest(helper=helper.__name__),self.assertRaisesRegex(ValueError,'^small_skin_original_deadline$'):helper(*args,0)
        self.assertEqual(em.data.vertices.len_reads+mesh.data.vertices.len_reads,0)

    def test_both_helpers_check_deadline_after_counts(self):
        mesh,rig,em,er=fixture()
        for helper,args in ((worker.precheck_dependencies,(mesh,rig)),(worker.precheck_evaluated,(mesh,rig,em,er))):
            with self.subTest(helper=helper.__name__),patch.object(worker.time,'perf_counter_ns',side_effect=[1,101]),self.assertRaisesRegex(ValueError,'^small_skin_original_deadline$'):
                helper(*args,100)


class QuaternionOracleTests(unittest.TestCase):
    @staticmethod
    def curves(kind):return [dict(data_path='pose.bones["Bone"].rotation_quaternion',array_index=i,keys=[dict(co=[1,FIRST[i]],interpolation=kind),dict(co=[25,LAST[i]],interpolation=kind)]) for i in range(4)]

    def test_linear_quarter_is_component_interpolation_not_slerp(self):
        value=raw_component_values(self.curves('LINEAR'),7,'LINEAR');rotation=quaternion_rotation(value)
        angle=math.degrees(math.atan2(rotation[1,0],rotation[0,0]))
        self.assertGreater(abs(angle-30.),1.)
        np.testing.assert_allclose(value,[.875,0.,0.,math.sqrt(3)/8],atol=1e-15,rtol=0.)
        np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-15,rtol=0.)

    def test_midpoint_and_constant_have_independent_known_answers(self):
        value=raw_component_values(self.curves('LINEAR'),13,'LINEAR');rotation=quaternion_rotation(value)
        self.assertAlmostEqual(math.degrees(math.atan2(rotation[1,0],rotation[0,0])),60.,places=12)
        np.testing.assert_allclose(quaternion_rotation(raw_component_values(self.curves('CONSTANT'),13,'CONSTANT')),np.eye(3),atol=0.,rtol=0.)
        points=(rotation@np.asarray(VERTICES).T).T
        np.testing.assert_allclose(np.linalg.norm(points,axis=1),np.linalg.norm(VERTICES,axis=1),atol=1e-15,rtol=0.)

    def test_wrong_raw_key_binding_cannot_be_used_as_expected_answer(self):
        curves=self.curves('LINEAR');curves[3]['keys'][1]['co'][1]=.7
        with self.assertRaises(AssertionError):raw_component_values(curves,7,'LINEAR')

if __name__=='__main__':unittest.main()
