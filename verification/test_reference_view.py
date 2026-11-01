"""Reference-change opportunities, never ordinary object-center visibility."""
import copy,time,unittest
from human_eye_plugin import mesh_structure as m,reference_view as v
from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent,diagnose,make_view_patch
from verification.m3_asset_cases import sheet
from human_eye_plugin.reference_view_consumer import ExactVisibility


def fixture(dent=.002,scale=1):
    points,polygons=sheet(9,dent=0);triangles=[];mapping=[]
    for i,p in enumerate(polygons):triangles.extend(([p[0],p[1],p[2]],[p[0],p[2],p[3]]));mapping.extend((i,i))
    edges=sorted({tuple(sorted(e)) for p in polygons for e in zip(p,p[1:]+p[:1])})
    raw=dict(vertices=points,edges=[list(e) for e in edges],polygons=polygons,matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],unit_scale=scale)
    meta=dict(object_id='target',object_instance='instance',document_epoch='doc',capture_id='capture')
    reference=m.prepare_raw(raw,meta);raw=copy.deepcopy(raw);raw['vertices']=sheet(9,dent=dent)[0];current=m.prepare_raw(raw,meta)
    registry=ReferenceRegistry();ref=registry.bind(reference,current,triangles,mapping,intent=ReferenceIntent('owned','intended undented sheet','same_index_from_owned_copy'))
    binding=registry.resolve(ref,current);report=diagnose(binding,current,budget=m.WorkBudget(),threshold_m=.0002*scale)
    patch=make_view_patch(binding,current,report,0,ref,budget=m.WorkBudget()) if report['changed_count'] else None
    packet=dict(source=current['source'],raw=current['raw'],triangles=triangles,triangle_polygons=mapping)
    obj=dict(object_id='target',name='OwnedSource',local_vertices=[[x*scale for x in p] for p in raw['vertices']],
        world_vertices=[[x*scale for x in p] for p in raw['vertices']],faces=copy.deepcopy(triangles),matrix=raw['matrix_world'],color=[.4,.4,.7,1.])
    return packet,patch,dict(unit='m',coordinate_frame='world',revision='native-fixture',objects=[obj])


class ReferenceViewTests(unittest.TestCase):
    def test_actual_changed_centroids_qualified_without_boundary_tags(self):
        packet,patch,native=fixture();plan,_,_=v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000)
        self.assertIsNotNone(plan['selected_ordinal']);self.assertEqual(plan['reason'],'visible_projected_reference_change_gain')
        self.assertNotIn('category',patch);self.assertLessEqual(plan['reserved_combined_triangle_tests'],16384)
        self.assertEqual(plan['source_member_count'],len(patch['members']))

    def test_independent_3d_rays_reproduce_projection_decision(self):
        packet,patch,native=fixture();deadline=time.perf_counter_ns()+5_000_000_000
        producer,_,_=v.plan(packet,patch,native,deadline)
        exact=ExactVisibility(native,deadline);consumer,_,_=v.plan(packet,patch,native,deadline,visibility=exact)
        self.assertEqual(producer,consumer);self.assertEqual(exact.tests,consumer['consumer_planned_triangle_tests'])

    def test_complete_extra_occluder_blocks_actual_task_witnesses(self):
        packet,patch,native=fixture();other=copy.deepcopy(native['objects'][0]);other['object_id']='occluder'
        # One larger plane above the whole source, both finite diagonal views.
        other['world_vertices']=[[-1,-1,.01],[1,-1,.01],[1,1,.01],[-1,1,.01]]
        other['local_vertices']=copy.deepcopy(other['world_vertices']);other['faces']=[[0,1,2],[0,2,3]]
        native['objects'].append(other);deadline=time.perf_counter_ns()+5_000_000_000
        producer,_,_=v.plan(packet,patch,native,deadline)
        consumer,_,_=v.plan(packet,patch,native,deadline,visibility=ExactVisibility(native,deadline))
        self.assertIsNone(producer['selected_ordinal']);self.assertEqual(producer,consumer)

    def test_center_blocked_other_meaningful_witnesses_can_be_used(self):
        packet,patch,native=fixture();blocked=patch['witnesses'][0]['triangle']
        def visibility(scene,sample,candidate,deadline):return sample['triangle']!=blocked
        plan,_,_=v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000,visibility=visibility)
        self.assertIsNotNone(plan['selected_ordinal'])
        self.assertEqual(plan['candidates'][0]['qualified_visible'],2)

    def test_visible_object_center_cannot_replace_hidden_changed_witnesses(self):
        packet,patch,native=fixture()
        plan,_,_=v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000,visibility=lambda *a:False)
        self.assertIsNone(plan['selected_ordinal']);self.assertEqual(plan['reason'],'no_verified_task_feature_gain')

    def test_visible_but_subpixel_reference_change_does_not_adopt(self):
        packet,patch,native=fixture()
        for w in patch['witnesses']:w['reference_offset_m']=[x*.02 for x in w['reference_offset_m']]
        patch['threshold_m']*=.01
        plan,_,_=v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000)
        self.assertIsNone(plan['selected_ordinal'])

    def test_no_reference_change_has_no_feature_reference(self):
        self.assertIsNone(fixture(dent=0)[1])

    def test_wrong_source_tessellation_or_members_refused(self):
        packet,patch,native=fixture()
        for kind in ('source','triangles','members'):
            value=copy.deepcopy(patch)
            if kind=='source':value['raw_sha256']='wrong'
            if kind=='triangles':value['tessellation_sha256']='wrong'
            if kind=='members':value['members']*=2
            with self.assertRaises(ValueError):v.plan(packet,value,native,time.perf_counter_ns()+2_000_000_000)

    def test_units_map_camera_parameters_back_to_host_units(self):
        packet,patch,native=fixture(scale=.001);plan,candidates,_=v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000)
        self.assertIsNotNone(plan['selected_ordinal'])
        for candidate in candidates:self.assertAlmostEqual(candidate['detail']['ortho_scale_bu']*.001,candidate['span_m'])

    def test_skew_region_is_enclosed_about_the_actual_frame_center(self):
        _,_,native=fixture()
        points=[[0.,1.,0.],[1.,0.,.1],[1.,1.,-.2]]
        for candidate in v.frames(native,points,[.3,.4,1.],1.):
            center=candidate['detail']['center_bu'];half=candidate['detail']['ortho_scale_bu']/2
            self.assertTrue(all(abs(v.dot(v.sub(p,center),axis))<half for p in points for axis in (candidate['right'],candidate['up'])))

    def test_native_pole_candidate_is_classified_without_discarding_other_view(self):
        _,_,native=fixture();normal=[3**.5/2,0.,-.5]
        candidates=v.frames(native,[[-1,-1,0],[1,-1,0],[0,1,.01]],normal,1.)
        self.assertEqual(sum(c['camera_basis_supported'] for c in candidates),1)
        self.assertTrue(all(c['camera_basis_supported'] or abs(c['eye'][2])>.99 for c in candidates))

    def test_oversized_occlusion_inventory_cannot_be_ignored(self):
        packet,patch,native=fixture();native['objects'][0]['faces']*=9
        with self.assertRaisesRegex(ValueError,'geometry_budget'):v.plan(packet,patch,native,time.perf_counter_ns()+2_000_000_000)


if __name__=='__main__':unittest.main()
