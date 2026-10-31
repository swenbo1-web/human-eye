import copy
import hashlib
import time
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch
from human_eye_plugin import mesh_structure as m, patch_focus as f, patch_observation as c, episode_gateway as render
from human_eye_plugin.blender_host import _PATCH_FOCUS_SHA256
from verification.patch_observation_fixtures import fixtures,ring


def source(case, single=False):
    raw=ring(case);raw['edges']=sorted({tuple(sorted((p[i-1],p[i]))) for p in raw['polygons'] for i in range(len(p))})
    raw['edges']=[list(e) for e in raw['edges']]
    raw.update(matrix_world=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]],unit_scale=1.)
    prepared=m.prepare_raw(raw,dict(object_id='target',object_instance='target:mesh',document_epoch='doc',capture_id='capture'))
    report=m.analyze_prepared(prepared,task_id='test',categories=['boundary_edges'])
    ids=[i for i,e in enumerate(raw['edges']) if set(e)<={4,5,6,7}]
    patch=next(p for p in report['patches'] if p['source_indices']==ids)
    objects=[dict(object_id='target',world_vertices=copy.deepcopy(raw['vertices']),
        faces=[tri for p in raw['polygons'] for tri in ([p[0],p[1],p[2]],[p[0],p[2],p[3]])])]
    def box(name,b):
        vertices=[[x,y,z] for z in b[4:6] for y in b[2:4] for x in b[:2]]
        faces=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
               [2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
        objects.append(dict(object_id=name,world_vertices=vertices,faces=faces))
    if not single:box('reference',[99.,101.,-1.,1.,-1.,1.] if case['far'] else [-.1,.1,-.1,.1,-1.1,-.9])
    if case['blocker'] is not None:box('blocker',case['blocker'])
    native=dict(objects=objects,unit='m',coordinate_frame='world',revision='test')
    return prepared,patch,native


class PatchObservationTests(unittest.TestCase):
    def test_frozen_six_cases_independent_replay(self):
        for case in fixtures():
            with self.subTest(case=case['id']):
                prepared,patch,native=source(case);deadline=time.perf_counter_ns()+30_000_000_000
                plan,*_=f.plan(prepared,patch,native,render,deadline)
                self.assertEqual(plan['detail_included'],case['want_detail'])
                if plan['visibility']['visible']:
                    self.assertEqual(sum(plan['visibility']['visible']),case['visible_samples'])
                with (mock_patch.object(f,'plan',side_effect=AssertionError('producer must not replay itself')),
                      mock_patch.object(f,'nearest_xy',side_effect=AssertionError('independent rays required'))):
                    work=c.validate_plan(plan,prepared,patch,native,deadline)
                self.assertLessEqual(work*2,8192)

    def test_true_single_target_has_no_fake_reference(self):
        prepared,patch,native=source(fixtures()[0],single=True)
        plan,*_=f.plan(prepared,patch,native,render,time.perf_counter_ns()+30_000_000_000)
        self.assertEqual(len(native['objects']),1);self.assertTrue(plan['detail_included'])

    def test_visibility_and_frame_tamper_rejected(self):
        prepared,patch,native=source(fixtures()[0]);deadline=time.perf_counter_ns()+30_000_000_000
        plan,*_=f.plan(prepared,patch,native,render,deadline)
        edits=[lambda p:p['visibility']['visible'].__setitem__(0,False),
               lambda p:p['visibility'].update(producer_triangle_tests=0),
               lambda p:p['detail']['center_world_m'].__setitem__(0,0.),
               lambda p:p.update(detail_included=False),
               lambda p:p['visibility']['samples'][0][0].__setitem__(0,99.),
               lambda p:p.update(execution_authority=True),
               lambda p:p['projection'].update(not_aperture_measurement=False)]
        for edit in edits:
            damaged=copy.deepcopy(plan);edit(damaged)
            with self.subTest(edit=edit),self.assertRaises(ValueError):c.validate_plan(damaged,prepared,patch,native,deadline)

    def test_combined_budget_is_reserved_before_rays(self):
        prepared,patch,native=source(fixtures()[0]);native['objects'][1]['faces']*=20
        with mock_patch.object(f,'nearest_xy',side_effect=AssertionError('must refuse before scanning')):
            with self.assertRaisesRegex(ValueError,'combined_ray_budget'):
                f.plan(prepared,patch,native,render,time.perf_counter_ns()+30_000_000_000)

    def test_nonplanar_and_open_components_refused(self):
        for mode in ('nonplanar','open'):
            prepared,patch,native=source(fixtures()[0])
            if mode=='nonplanar':prepared['raw']['vertices'][0][2]=.1;native['objects'][0]['world_vertices'][0][2]=.1
            else:patch['source_indices'].pop()
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                f.plan(prepared,patch,native,render,time.perf_counter_ns()+30_000_000_000)

    def test_deadline_and_pin(self):
        prepared,patch,native=source(fixtures()[0])
        with self.assertRaisesRegex(ValueError,'deadline'):
            f.plan(prepared,patch,native,render,time.perf_counter_ns()-1)
        self.assertEqual(hashlib.sha256(Path(f.__file__).read_bytes()).hexdigest(),_PATCH_FOCUS_SHA256)

    def test_nearest_feasible_combined_budget_boundary(self):
        prepared,patch,native=source(fixtures()[0]);tri=native['objects'][1]['faces']
        native['objects'][1]['faces']=(tri*14)[:162]
        deadline=time.perf_counter_ns()+30_000_000_000
        plan,*_=f.plan(prepared,patch,native,render,deadline)
        self.assertEqual(c.validate_plan(plan,prepared,patch,native,deadline)*2,8160)
        native['objects'][1]['faces'].append(tri[0])
        with self.assertRaisesRegex(ValueError,'combined_ray_budget'):
            f.plan(prepared,patch,native,render,deadline)

    def test_finite_geometry_cap_and_thin_region_decline(self):
        prepared,patch,native=source(fixtures()[0]);native['objects'][1]['faces']*=171
        with self.assertRaisesRegex(ValueError,'native_budget'):
            f.plan(prepared,patch,native,render,time.perf_counter_ns()+30_000_000_000)
        case=fixtures()[0];case['half']=[.0001,.1]
        prepared,patch,native=source(case);deadline=time.perf_counter_ns()+30_000_000_000
        plan,*_=f.plan(prepared,patch,native,render,deadline)
        self.assertFalse(plan['detail_included']);self.assertEqual(plan['reason'],'insufficient_projection_gain')
        self.assertEqual(c.validate_plan(plan,prepared,patch,native,deadline),0)

    def test_consumer_caps_geometry_before_common_copy_and_hash(self):
        prepared,patch,native=source(fixtures()[0]);now=time.perf_counter_ns();deadline=now+30_000_000_000
        identity={k:prepared['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')}
        obj=dict(object_id='target',name='target',local_vertices=[[0.,0.,0.]]*4097,
            world_vertices=[[0.,0.,0.]]*4097,faces=[[0,1,2]],matrix=[],color=[])
        value=dict(protocol=f.PROTOCOL,request_id='test',object_id='target',patch=patch,raw=prepared['raw'],
            identity=identity,evidence={'native_scene':{'objects':[obj]}},display={},source_binding='',plan={},frames=[],
            started_ns=now,planning_finished_ns=now,finished_ns=now,deadline_ns=deadline,
            restored=True,read_only=True,execution_authority=False)
        with (mock_patch.object(c,'validate_capabilities'),
              mock_patch.object(c.n,'_readonly_evidence',side_effect=AssertionError('oversized copy attempted'))):
            with self.assertRaisesRegex(ValueError,'consumer_geometry_budget'):
                c.validate_result(value,object_id='target',patch=patch,request_id='test',deadline_ns=deadline,capabilities={})


if __name__=='__main__':unittest.main()
