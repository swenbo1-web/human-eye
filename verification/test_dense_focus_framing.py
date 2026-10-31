"""Dense-focus opportunities and independent plan contracts, no native render."""
from __future__ import annotations
import copy,math,unittest
from unittest.mock import patch
from human_eye_plugin import episode_gateway as producer
from human_eye_plugin import native_observation as consumer
from verification.test_native_multiscale import box
from verification.test_task_gap_framing import scene as gap_scene


def dense_box(identity='focal',center=(0.,0.,.014),half=(.02,.02,.01)):
    # Conforming six planar surfaces: 56 grid vertices plus nine face-interior
    # subdivisions, preserving the original solid boundaries without duplicates.
    lookup={};points=[];faces=[];grid=(-3,-1,1,3)
    def vertex(key):
        key=tuple(key)
        if key not in lookup:
            lookup[key]=len(points);points.append([center[k]+half[k]*key[k]/3 for k in range(3)])
        return lookup[key]
    for axis in range(3):
        axes=[(axis+1)%3,(axis+2)%3]
        for sign in (-1,1):
            for i in range(3):
                for j in range(3):
                    quad=[]
                    for a,b in ((i,j),(i+1,j),(i+1,j+1),(i,j+1)):
                        key=[0,0,0];key[axis]=3*sign;key[axes[0]]=grid[a];key[axes[1]]=grid[b];quad.append(vertex(key))
                    if sign<0:quad.reverse()
                    a,b,c,d=quad;faces.extend(([a,b,c],[a,c,d]))
    originals=faces[:9];faces=faces[9:]
    for a,b,c in originals:
        index=len(points);points.append([math.fsum(points[i][k] for i in (a,b,c))/3 for k in range(3)])
        faces.extend(([a,b,index],[b,c,index],[c,a,index]))
    return {'object_id':identity,'world_vertices':points,'faces':faces}


def scene():
    return {'unit':'m','coordinate_frame':'world','revision':'dense-focus-pure','objects':[
        dense_box(),box('base',[0.,0.,-.02],[.1,.1,.04]),box('far',[100.,0.,0.],[1.,1.,1.])]}


def plan(native,view='XY',scale=1.,**options):
    return producer.plan_readonly_dense_focus(native,'focal','base',view,scale,**options)


def validated(native,view='XY'):
    value=plan(native,view)[0];value['budget_scope']=consumer.READONLY_BUDGET_SCOPE
    return consumer._validate_dense_focus_plan(value,native,view,'focal')


class DenseFocusFramingTests(unittest.TestCase):
    def test_conforming_65_vertex_mesh_has_unchanged_closed_box_boundaries(self):
        focal=dense_box();self.assertEqual((len(focal['world_vertices']),len(focal['faces'])),(65,126))
        edges={}
        for face in focal['faces']:
            for a,b in zip(face,face[1:]+face[:1]):edges[a,b]=edges.get((a,b),0)+1
        self.assertTrue(all(v==1 and edges.get((b,a))==1 for (a,b),v in edges.items()))
        self.assertEqual([[min(p[k] for p in focal['world_vertices']),max(p[k] for p in focal['world_vertices'])] for k in range(3)],
            [[-.02,.02],[-.02,.02],[.004,.024]])

    def test_dense_far_focus_now_has_truthful_bound_and_96_pixel_opportunity(self):
        native=scene();before=copy.deepcopy(native);value,overview,detail=plan(native)
        self.assertEqual(producer.plan_readonly_task_gap(native,'focal','base','XY',1.)[0]['reason_code'],'focus_budget_exceeded')
        self.assertEqual(value['schema_version'],'native-dense-focus-plan-v3');self.assertEqual(value['image_count'],2)
        bound=value['bounds_feature'];self.assertEqual(bound['method'],'projected_aabb_min_extent_upper_bound')
        self.assertAlmostEqual(bound['width_upper_bound_m'],.04);self.assertAlmostEqual(bound['detail_px_upper_bound'],96.)
        self.assertLess(bound['overview_px_upper_bound'],1);self.assertEqual(value['max_total_pixels'],294912)
        value['budget_scope']=consumer.READONLY_BUDGET_SCOPE
        self.assertEqual(validated(native),value);self.assertEqual(native,before);self.assertIsNotNone(detail)

    def test_canonical_views_have_independent_bound_and_matching_direction(self):
        for view in ('XY','XZ'):
            native=scene();value,_,frame=plan(native,view)
            self.assertEqual(value['schema_version'],'native-dense-focus-plan-v3')
            self.assertEqual(value['view'],view);self.assertEqual(frame['direction'],value['overview']['eye_direction_world'])
            validated(native,view)

    def test_simple_focal_and_existing_detail_remain_exact_legacy_without_dense_work(self):
        native=scene();native['objects'][0]=box('focal',[0.,0.,.014],[.04,.04,.02])
        expected=producer.plan_readonly_task_gap(native,'focal','base','XY',1.)
        with patch.object(producer,'_task_gap_sample_hits',side_effect=AssertionError('dense branch entered')):
            self.assertEqual(plan(native),expected)

    def test_existing_task_gap_v2_and_ordinary_v1_are_unchanged(self):
        for native in (gap_scene(),gap_scene(gap=.004)):
            for obj in native['objects']:
                if obj['object_id']=='ref':obj['object_id']='base'
            expected=producer.plan_readonly_task_gap(native,'focal','base','SCENE',1.)
            self.assertEqual(plan(native,'SCENE'),expected)

    def test_large_dense_footprint_does_not_trace_a_ray_or_add_an_image(self):
        native=scene();native['objects'].pop()
        with patch.object(producer,'_task_gap_sample_hits',side_effect=AssertionError('unnecessary ray')):
            self.assertEqual(plan(native),producer.plan_readonly_task_gap(native,'focal','base','XY',1.))

    def test_fully_occluded_center_preserves_overview(self):
        native=scene();native['objects'].append(box('shell',[0.,0.,0.],[.5,.5,.5]))
        expected=producer.plan_readonly_task_gap(native,'focal','base','XY',1.)
        self.assertEqual(plan(native),expected)

    def test_focal_render_hidden_preserves_overview(self):
        self.assertEqual(plan(scene(),focal_hidden_render=True)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_reference_hidden_does_not_mislabel_focal_visibility(self):
        self.assertEqual(plan(scene(),reference_hidden_render=True)[0]['schema_version'],'native-dense-focus-plan-v3')

    def test_total_producer_consumer_work_boundary_is_2048_not_4096_scene_faces(self):
        for total,wanted in ((2048,'native-dense-focus-plan-v3'),(2049,'native-multiscale-plan-v1')):
            native=scene();work=box('work',[40.,40.,0.],[1.,1.,1.])
            missing=total-sum(len(o['faces']) for o in native['objects'])
            work['faces']=[list(work['faces'][0]) for _ in range(missing)];native['objects'].append(work)
            value=plan(native)[0];self.assertEqual(value['schema_version'],wanted)
            if total==2048:self.assertEqual(validated(native)['visibility']['total_triangle_tests'],4096)

    def test_scene_vertex_budget_prevents_unreferenced_work(self):
        native=scene();native['objects'][-1]['world_vertices'] += [[100.,0.,0.]]*4096
        with patch.object(producer,'_task_gap_sample_hits',side_effect=AssertionError('over budget ray')):
            self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_non_triangular_scene_is_not_miscounted_as_one_triangle(self):
        native=scene();native['objects'][-1]['faces'][0]=[0,1,2,3]
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_degenerate_projection_and_zoom_cap_keep_old_plan(self):
        native=scene()
        for p in native['objects'][0]['world_vertices']:p[1]=0.
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')
        native=scene()
        for p in native['objects'][-1]['world_vertices']:p[0]+=1e7
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_slender_diagonal_bound_is_not_called_true_thin_cross_section(self):
        native=scene()
        for p in native['objects'][0]['world_vertices']:
            x,y=p[:2];p[0]=5*x-y;p[1]=5*x+y
        # XY can conservatively reject a parallel projected side, while XZ
        # still has a valid bounded same-view opportunity.
        value=validated(native,'XZ')
        self.assertIn('not_thin_section',value['bounds_feature']['quality_scope'])
        self.assertEqual(value['bounds_feature']['method'],'projected_aabb_min_extent_upper_bound')

    def test_local_coordinates_do_not_get_world_offset_relative_tolerance(self):
        native=scene()
        for obj in native['objects']:
            for p in obj['world_vertices']:p[0]+=1e9
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_native_camera_float32_precision_cannot_break_an_usable_overview(self):
        native=scene()
        for obj in native['objects']:
            for p in obj['world_vertices']:p[0]+=100000.003
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')

    def test_metre_and_kilometre_BU_keep_the_same_SI_opportunity(self):
        a=plan(scene())[0];b=plan(scene(),scale=1000.)[0]
        # SI geometry is fixed; BU roundtrips can perturb dimensionless ratios
        # by a few ulps, so compare those numerical ratios accordingly.
        for key in ('center_world_m','projected_extents_m','width_upper_bound_m'):
            self.assertEqual(a['bounds_feature'][key],b['bounds_feature'][key])
        for key in ('overview_px_upper_bound','detail_px_upper_bound','zoom'):
            self.assertAlmostEqual(a['bounds_feature'][key],b['bounds_feature'][key],places=11)
        self.assertAlmostEqual(a['detail']['span_m'],b['detail']['span_m'],places=14)

    def test_validator_rejects_forged_bound_and_feature_counts(self):
        native=scene();original=validated(native)
        for key,bad in [('method','projected_min_edge_normal_width'),('focal_vertex_count',True),
                ('focal_triangle_count',12),('width_upper_bound_m',.02),('overview_px_upper_bound',10.),
                ('detail_px_upper_bound',192.),('zoom',8192.),('projected_extents_m',[.04,.03])]:
            wrong=copy.deepcopy(original);wrong['bounds_feature'][key]=bad
            with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(wrong,native,'XY','focal')

    def test_validator_rejects_forged_work_and_visibility_claim(self):
        native=scene();original=validated(native)
        for key,bad in [('triangle_tests',0),('consumer_triangle_tests',0),('total_triangle_tests',0),
                ('max_total_triangle_tests',8192),('scene_vertex_count',True),('scope','complete_visibility')]:
            wrong=copy.deepcopy(original);wrong['visibility'][key]=bad
            with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(wrong,native,'XY','focal')

    def test_validator_rejects_mutated_detail_center_axes_and_span(self):
        native=scene();original=validated(native)
        for key,bad in [('center_world_m',[.001,0.,.014]),('right_world',[1.,0.,0.]),('span_m',.32)]:
            wrong=copy.deepcopy(original);wrong['detail'][key]=bad
            with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(wrong,native,'XY','focal')
        wrong=copy.deepcopy(original);wrong['bounds_feature']['center_world_m'][0]+=.001
        with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(wrong,native,'XY','focal')

    def test_validator_rejects_missing_unknown_and_false_schema(self):
        native=scene();original=validated(native)
        for wrong in ({k:v for k,v in original.items() if k!='reason_code'},dict(original,unknown=True),
                dict(original,schema_version='native-multiscale-plan-v1')):
            with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(wrong,native,'XY','focal')
        with self.assertRaises(ValueError):consumer._validate_multiscale_plan(original,native,'XY','focal')

    def test_consumer_cannot_validate_a_simple_focal_under_the_dense_schema(self):
        native=scene();original=validated(native);native['objects'][0]=box('focal',[0.,0.,.014],[.04,.04,.02])
        with self.assertRaises(ValueError):consumer._validate_dense_focus_plan(original,native,'XY','focal')

    def test_independent_ray_and_producer_both_reject_a_coplanar_blocker(self):
        native=scene();native['objects'].append({'object_id':'coplanar',
            'world_vertices':[[0.,-.001,.1],[0.,.001,.1],[0.,0.,.2]],'faces':[[0,1,2]]})
        self.assertEqual(plan(native)[0]['schema_version'],'native-multiscale-plan-v1')
        with self.assertRaisesRegex(ValueError,'ray_uncertain'):
            consumer._dense_focus_ray_readback(native,[0.,0.,.014],[-1.,0.,0.],[0.,-1.,0.],[0.,0.,1.])

    def test_consumer_independently_rejects_false_focal_first(self):
        native=scene();original=validated(native)
        # Keep identities and work fixed, moving one pre-existing far triangle
        # into the ray requires a recomputed plan; direct ray proof still fails.
        native['objects'][-1]=box('front',[0.,0.,.2],[.1,.1,.1])
        hit,ids,_=consumer._dense_focus_ray_readback(native,[0.,0.,.014],[-1.,0.,0.],[0.,-1.,0.],[0.,0.,1.])
        self.assertEqual(ids,{'front'});self.assertIsNotNone(hit)

    def test_scene_dense_view_keeps_the_original_plan_exact(self):
        native=scene()
        expected=producer.plan_readonly_task_gap(native,'focal','base','SCENE',1.)
        self.assertEqual(plan(native,'SCENE'),expected)

    def test_oblique_far_camera_risk_retains_legacy_without_a_dense_ray(self):
        native=scene()
        # Long depth can amplify Blender's floating SCENE rotation error even
        # when the camera position rounds exactly. This new branch is limited
        # to canonical axes rather than weakening the original frustum guard.
        native['objects'][-1]=box('far',[16384.,-16384.,12288.],[1.,1.,1.])
        expected=producer.plan_readonly_task_gap(native,'focal','base','SCENE',1.)
        with patch.object(producer,'_task_gap_sample_hits',side_effect=AssertionError('oblique dense ray')):
            self.assertEqual(plan(native,'SCENE'),expected)

    def test_consumer_rejects_a_dense_plan_relabelled_as_scene(self):
        original=validated(scene());original['view']='SCENE'
        with self.assertRaisesRegex(ValueError,'canonical_view'):
            consumer._validate_dense_focus_plan(original,scene(),'SCENE','focal')


if __name__=='__main__':unittest.main()
