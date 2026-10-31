"""Finite cross-view gap opportunities; pixels and Blender require owned tests."""
from __future__ import annotations
import copy,math,unittest
from unittest.mock import patch
from human_eye_plugin import episode_gateway as planner
from human_eye_plugin import native_observation as consumer
from verification.test_native_multiscale import box


def scene(axis=2,gap=25e-6,reverse=False):
    # Both cubes are .1m wide, .02m along the separation axis.
    size=[.1,.1,.1];size[axis]=.02
    origin=[0.,0.,0.];part=list(origin);part[axis]=.02+gap
    objects=[box('ref',origin,size),box('focal',part,size)]
    if reverse:objects[0]['object_id'],objects[1]['object_id']='focal','ref'
    return {'unit':'m','coordinate_frame':'world','revision':'task-gap-pure','objects':objects}


def plan(value,view='SCENE',**options):
    return planner.plan_readonly_task_gap(value,'focal','ref',view,1.,**options)


def validate(value,view='SCENE'):
    result=plan(value,view)[0];result['budget_scope']=consumer.READONLY_BUDGET_SCOPE
    return consumer._validate_task_gap_plan(result,value,view,'focal','ref')


class TaskGapFramingTests(unittest.TestCase):
    def test_all_axes_and_orderings_have_analytic_gap_and_cross_view(self):
        for axis in range(3):
            for reverse in (False,True):
                with self.subTest(axis=axis,reverse=reverse):
                    value=scene(axis,reverse=reverse);before=copy.deepcopy(value)
                    result,overview,detail=plan(value)
                    self.assertEqual(result['schema_version'],'native-task-gap-plan-v2')
                    task=result['task_feature'];self.assertEqual(task['gap_axis'],axis)
                    self.assertAlmostEqual(task['gap_m'],25e-6,places=15)
                    self.assertEqual(task['detail_view'],'XZ' if axis==2 else 'XY')
                    self.assertAlmostEqual(task['detail_gap_px'],96.)
                    self.assertEqual(result['max_total_pixels'],294912)
                    self.assertEqual(result['image_count'],2);self.assertIsNotNone(detail)
                    self.assertEqual(validate(value)['task_feature'],task);self.assertEqual(value,before)

    def test_requested_depth_projection_is_zero_but_detail_is_side_view(self):
        value=scene();result,_,detail=plan(value,'XY');task=result['task_feature']
        self.assertEqual(task['requested_gap_projection_px'],0.)
        self.assertEqual(task['detail_view'],'XZ');self.assertGreater(task['detail_gap_px'],32.)
        self.assertEqual(detail['direction'],[0.,-1.,0.]);validate(value,'XY')

    def test_ordinary_four_mm_has_byte_equal_legacy_plan_and_no_extra_rays(self):
        value=scene(gap=.004)
        expected=planner.plan_native_multiscale(value,'focal','SCENE',1.)
        with patch.object(planner,'_task_gap_sample_hits',side_effect=AssertionError('unnecessary ray')):
            actual=plan(value)
        self.assertEqual(actual,expected);self.assertEqual(actual[0]['image_count'],1)

    def test_existing_legacy_detail_is_not_replaced(self):
        value=scene();value['objects'].append(box('remote',[100.,0.,0.],[1.,1.,1.]))
        expected=planner.plan_native_multiscale(value,'focal','SCENE',1.)
        self.assertTrue(expected[0]['detail_included'])
        with patch.object(planner,'_task_gap_witness',side_effect=AssertionError('legacy detail preserved')):
            self.assertEqual(plan(value),expected)

    def test_gap_behind_front_enclosure_is_refused_and_legacy_preserved(self):
        value=scene();value['objects'].append(box('shell',[0.,0.,0.],[.5,.5,.5]))
        expected=planner.plan_native_multiscale(value,'focal','SCENE',1.)
        self.assertEqual(plan(value),expected)

    def test_thin_front_occluder_blocks_gap_sample_but_background_is_allowed(self):
        value=scene();task=plan(value)[0]['task_feature'];z=task['center_world_m'][2]
        value['objects'].append(box('front',[0.,-.2,z],[.08,.01,5e-6]))
        self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')
        value['objects'][-1]=box('back',[0.,.2,z],[.08,.01,5e-6])
        self.assertEqual(plan(value)[0]['schema_version'],'native-task-gap-plan-v2');validate(value)

    def test_near_sample_surface_is_conservatively_refused(self):
        value=scene();z=plan(value)[0]['task_feature']['center_world_m'][2]
        value['objects'].append(box('near',[0.,1e-10,z],[.08,1e-10,5e-6]))
        self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_both_render_hidden_flags_refuse_new_window(self):
        for key in ('focal_hidden_render','reference_hidden_render'):
            self.assertEqual(plan(scene(),**{key:True})[0]['schema_version'],'native-multiscale-plan-v1')

    def test_zero_penetrating_and_two_axis_gaps_are_not_task_gap_claims(self):
        for value in (scene(gap=0.),scene(gap=-.0001),scene()):
            if value['objects'][1]['world_vertices'][0][2]>.010001:
                for p in value['objects'][1]['world_vertices']:p[0]+=.2
            self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_transverse_edge_contact_is_not_an_overlap_window(self):
        value=scene()
        for p in value['objects'][1]['world_vertices']:p[0]+=.1
        self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_wrong_topology_or_missing_side_never_becomes_box_from_corners(self):
        for mode in ('missing','duplicate','flip','diagonal','all_reversed'):
            value=scene();faces=value['objects'][1]['faces']
            if mode=='missing':faces.pop()
            elif mode=='duplicate':faces[-1]=list(faces[0])
            elif mode=='flip':faces[-1]=list(reversed(faces[-1]))
            elif mode=='all_reversed':faces[:]=[list(reversed(f)) for f in faces]
            else:faces[-1]=[0,2,6]
            self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_triangle_budget_does_not_expand_for_three_samples(self):
        value=scene();extra=box('extra',[.3,.3,.3],[.1,.1,.1]);extra['faces']=extra['faces']*112
        value['objects'].append(extra)
        with patch.object(planner,'_task_gap_sample_hits',side_effect=AssertionError('over budget')):
            self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_scene_vertex_budget_rejects_unreferenced_vertex_work(self):
        value=scene();extra=box('extra',[.3,.3,.3],[.1,.1,.1]);extra['world_vertices'] += [[.3,.3,.3]]*4090
        value['objects'].append(extra)
        with patch.object(planner,'_task_gap_sample_hits',side_effect=AssertionError('over budget')):
            self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_scale_conversion_preserves_si_task_plan(self):
        value=scene();a=plan(value)[0]
        b=planner.plan_readonly_task_gap(value,'focal','ref','SCENE',1000.)[0]
        # BU conversion introduces a few ulps in public SI span. The task
        # witness itself is computed from unchanged SI geometry.
        self.assertEqual(a['task_feature']['gap_m'],b['task_feature']['gap_m'])
        self.assertEqual(a['task_feature']['sample_points_world_m'],b['task_feature']['sample_points_world_m'])
        self.assertAlmostEqual(a['overview']['span_m'],b['overview']['span_m'],places=14)
        self.assertAlmostEqual(a['task_feature']['zoom'],b['task_feature']['zoom'],places=10)

    def test_validator_rejects_forged_gap_geometry_view_and_budget(self):
        value=scene();original=validate(value)
        changes=[('gap_m',.0001),('reference_id','focal'),('gap_axis',True),('detail_view','SCENE'),
            ('requested_gap_projection_px',0.),('detail_gap_px',150.),('canonical_gap_px',5.),('zoom',8192.)]
        for key,bad in changes:
            with self.subTest(key=key):
                corrupt=copy.deepcopy(original);corrupt['task_feature'][key]=bad
                with self.assertRaises(ValueError):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')
        for key,bad in [('triangle_tests',24),('max_triangle_tests',8192),('scene_vertex_count',True),
                ('consumer_triangle_tests',0),('total_triangle_tests',1440),('max_total_triangle_tests',8192)]:
            corrupt=copy.deepcopy(original);corrupt['visibility'][key]=bad
            with self.assertRaises(ValueError):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')

    def test_validator_independently_rejects_new_front_occluder(self):
        value=scene();original=validate(value);z=original['task_feature']['center_world_m'][2]
        value['objects'].append(box('front',[0.,-.2,z],[.08,.01,5e-6]))
        # Rebuild overview and declared work to isolate visibility, not stale span.
        legacy=planner.plan_native_multiscale(value,'focal','SCENE',1.)[0]
        corrupt=copy.deepcopy(original);corrupt['overview']=legacy['overview'];corrupt['feature']=legacy['feature']
        span=legacy['overview']['span_m'];gap=corrupt['task_feature']['gap_m'];detail_span=max(4*gap,span/4096.)
        t=corrupt['task_feature'];t.update(canonical_gap_px=384*gap/span,detail_gap_px=384*gap/detail_span,
            zoom=span/detail_span,requested_gap_projection_px=384*gap*math.hypot(*[corrupt['overview'][k][2] for k in ('right_world','up_world')])/span)
        corrupt['detail']['span_m']=detail_span;corrupt['visibility'].update(triangle_tests=108,
            consumer_triangle_tests=108,total_triangle_tests=216,scene_vertex_count=24)
        with self.assertRaisesRegex(ValueError,'occluded'):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')

    def test_validator_rejects_task_plan_in_legacy_v1_consumer(self):
        with self.assertRaises(ValueError):consumer._validate_multiscale_plan(validate(scene()),scene(),'SCENE','focal')

    def test_validator_rejects_missing_and_unknown_fields(self):
        original=validate(scene())
        for value in ({k:v for k,v in original.items() if k!='reason_code'},dict(original,unknown=True)):
            with self.assertRaises(ValueError):consumer._validate_task_gap_plan(value,scene(),'SCENE','focal','ref')

    def test_validator_cannot_replace_an_existing_legacy_detail(self):
        value=scene(gap=.0002);original=validate(value)
        value['objects'].append(box('remote',[3.,0.,0.],[.1,.1,.1]))
        legacy=planner.plan_native_multiscale(value,'focal','SCENE',1.)[0]
        self.assertTrue(legacy['detail_included']);self.assertLess(legacy['feature']['overview_px'],12)
        corrupt=copy.deepcopy(original);corrupt['overview']=legacy['overview'];corrupt['feature']=legacy['feature']
        with self.assertRaisesRegex(ValueError,'legacy_overview_branch'):
            consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')

    def test_large_world_offset_does_not_enlarge_task_coordinate_budget(self):
        value=scene()
        for obj in value['objects']:
            for p in obj['world_vertices']:p[0]+=1e9
        expected=planner.plan_native_multiscale(value,'focal','SCENE',1.)
        self.assertEqual(plan(value),expected)
        self.assertFalse(consumer._task_gap_local_point([1e9+.0002,0.,0.],[1e9,0.,0.],25e-6))

    def test_each_task_coordinate_and_detail_center_is_locally_bound(self):
        value=scene();original=validate(value)
        for key in ('center_world_m','witness_focal_world_m','witness_reference_world_m'):
            corrupt=copy.deepcopy(original);corrupt['task_feature'][key][0]+=.0002
            with self.assertRaises(ValueError):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')
        for index in range(3):
            corrupt=copy.deepcopy(original);corrupt['task_feature']['sample_points_world_m'][index][0]+=.0002
            with self.assertRaises(ValueError):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')
        corrupt=copy.deepcopy(original);corrupt['detail']['center_world_m'][0]+=.0002
        with self.assertRaises(ValueError):consumer._validate_task_gap_plan(corrupt,value,'SCENE','focal','ref')

    def test_parallel_coplanar_ray_is_unknown_in_both_independent_paths(self):
        value=scene();z=plan(value)[0]['task_feature']['center_world_m'][2]
        value['objects'].append({'object_id':'coplanar','world_vertices':[[-.001,-.15,z],[.001,-.15,z],[0.,-.2,z]],
            'faces':[[0,1,2]]})
        self.assertEqual(plan(value)[0]['schema_version'],'native-multiscale-plan-v1')
        with self.assertRaisesRegex(ValueError,'ray_uncertain'):
            consumer._task_gap_ray_readback(value,[0.,0.,z],[0.,-1.,0.])

    def test_shared_producer_consumer_budget_at_682_and_683_triangles(self):
        def bounded(total):
            value=scene();extra=box('extra',[.3,.3,.3],[.1,.1,.1])
            extra['faces']=[copy.deepcopy(extra['faces'][i%12]) for i in range(total-24)]
            value['objects'].append(extra);return value
        at=bounded(682);result=validate(at)
        self.assertEqual(result['visibility']['total_triangle_tests'],4092)
        self.assertEqual(result['visibility']['triangle_tests'],2046)
        self.assertEqual(result['visibility']['consumer_triangle_tests'],2046)
        beyond=bounded(683)
        with patch.object(planner,'_task_gap_sample_hits',side_effect=AssertionError('shared budget exceeded')):
            self.assertEqual(plan(beyond)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_float32_side_camera_offset_cannot_break_a_usable_overview(self):
        value=scene()
        for obj in value['objects']:
            for p in obj['world_vertices']:p[0]+=100.000003
        self.assertIsNotNone(planner._task_gap_witness(value,'focal','ref'))
        self.assertEqual(plan(value),planner.plan_native_multiscale(value,'focal','SCENE',1.))
        self.assertEqual(plan(scene())[0]['schema_version'],'native-task-gap-plan-v2')


if __name__=='__main__':unittest.main()
