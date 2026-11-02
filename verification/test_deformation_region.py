"""Analytic membership/affine examples and complete region summary contracts.

Expected sets and summary extrema below are authored independently of the
production selector. Native qualification uses a separate 13-axis SAT oracle.
"""
import copy,itertools,math,time,unittest
from fractions import Fraction
from unittest.mock import patch
from human_eye_plugin import deformation_region as region

SHA='a'*64
IDENTITY=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def proof(triangles,*,world=None,unit=1.):
    vertices=[list(p) for tri in triangles for p in tri]
    return dict(original=copy.deepcopy(vertices),current=vertices,triangles=[[3*i,3*i+1,3*i+2] for i in range(len(triangles))],
        world=copy.deepcopy(IDENTITY if world is None else world),unit=unit,source_sha256=SHA,
        source=dict(scene_sha256='b'*64,object_id='rig',mesh_identity=dict(object_id='mesh'),frame=dict(number=1,subframe=0.)))


def query(bounds=((-1.,-1.,-1.),(1.,1.,1.))):
    return dict(schema='surface-deformation-region-query-v1',expected_source_sha256=SHA,
        region=dict(kind='closed_aabb',coordinate_space='current_world_m',bounds=[list(v) for v in bounds]))


def selection(p,q=None):
    s=p['source'];return dict(schema='surface-deformation-region-selection-v1',source_ref=dict(scene_sha256=s['scene_sha256'],
        rig_object_id=s['object_id'],mesh_object_id=s['mesh_identity']['object_id'],frame=copy.deepcopy(s['frame'])),region=copy.deepcopy((q or query())['region']))


def fact(index,high=1.,low=1.,area=1.,state='measured',reason=None):
    return dict(triangle=index,state=state,reason=reason,principal_stretches=None if state=='unknown' else [high,low],
        area_ratio=None if state=='unknown' else area,reference_geometry='nonzero_area',current_geometry='zero_area' if state=='collapsed' else 'nonzero_area')


class DeformationRegionTests(unittest.TestCase):
    def window(self):return time.perf_counter_ns()+5_000_000_000
    def select(self,p,q=None):return region.select(p,query() if q is None else q,deadline_ns=self.window())
    def summarize(self,m,rows):return region.summarize(m,rows,deadline_ns=self.window())
    def assert_error(self,reason,call):
        with self.assertRaisesRegex(ValueError,'^rig_pose_deformation_region_'+reason+'$'):call()

    def test_center_and_vertices_outside_can_still_intersect(self):
        cases=[((-2.,0.,0.),(2.,0.,0.),(0.,5.,0.)),((-4.,-2.,0.),(4.,-2.,0.),(0.,9.,0.))]
        # Both centroids are above y=1. The second triangle contains the entire
        # box's z=0 cross-section even though none of its edges enters the box.
        for tri in cases:
            with self.subTest(triangle=tri):self.assertEqual(self.select(proof([tri]))['matched_triangle_indices'],[0])

    def test_triangle_aabb_overlap_is_only_a_candidate(self):
        tri=((2.,0.,0.),(0.,2.,0.),(2.,2.,0.))
        self.assertEqual(self.select(proof([tri]),query(((0.,0.,-.1),(.5,.5,.1))))['matched_triangle_indices'],[])

    def test_closed_vertex_edge_and_face_contacts(self):
        triangles=[((1.,1.,1.),(2.,1.,1.),(1.,2.,1.)),((1.,-2.,0.),(1.,2.,0.),(2.,0.,0.)),
            ((0.,0.,1.),(1.,0.,1.),(0.,1.,1.))]
        self.assertEqual(self.select(proof(triangles))['matched_triangle_indices'],[0,1,2])

    def test_one_float_step_outside_is_not_absorbed_by_a_tolerance(self):
        x=math.nextafter(1.,math.inf);tri=((x,0.,0.),(x,.5,0.),(x,0.,.5))
        self.assertEqual(self.select(proof([tri]))['matched_triangle_indices'],[])
        tri=tuple((1.,y,z) for _,y,z in tri)
        self.assertEqual(self.select(proof([tri]))['matched_triangle_indices'],[0])

    def test_degenerate_segments_and_points_are_members_not_skipped(self):
        triangles=[((-2.,0.,0.),(0.,0.,0.),(2.,0.,0.)),((.5,.5,.5),)*3,
            ((0.,3.,0.),(1.5,1.5,0.),(3.,0.,0.)),((2.,2.,2.),)*3]
        self.assertEqual(self.select(proof(triangles))['matched_triangle_indices'],[0,1])

    def test_all_vertex_permutations_keep_contacts_and_false_candidates(self):
        examples=[(((-2.,0.,0.),(2.,0.,0.),(0.,5.,0.)),True),(((1.,1.,1.),(2.,1.,1.),(1.,2.,1.)),True),
            (((0.,3.,0.),(1.5,1.5,0.),(3.,0.,0.)),False)]
        for tri,expected in examples:
            for order in itertools.permutations(range(3)):
                with self.subTest(triangle=tri,order=order):
                    self.assertEqual(bool(self.select(proof([[tri[i] for i in order]]))['matched_triangle_indices']),expected)

    def test_affine_rotation_translation_and_unit_conversion_are_applied(self):
        # Independent formula is (x,y,z) -> (.5*(3-y), .5*(-2+x), .5*z).
        world=[[0.,-1.,0.,3.],[1.,0.,0.,-2.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        tri=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.));p=proof([tri],world=world,unit=.5)
        self.assertEqual(self.select(p,query(((1.,-1.,-.1),(1.5,-.5,.1))))['matched_triangle_indices'],[0])
        self.assertEqual(self.select(p,query(((-.1,-.1,-.1),(.1,.1,.1))))['matched_triangle_indices'],[])

    def test_membership_uses_current_instead_of_reference_coordinates(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);p['original']=[[8.,8.,8.],[9.,8.,8.],[8.,9.,8.]]
        self.assertEqual(self.select(p)['matched_triangle_indices'],[0])
        p['current'],p['original']=p['original'],p['current'];self.assertEqual(self.select(p)['matched_triangle_indices'],[])

    def test_exact_affine_avoids_translation_roundoff_false_contact(self):
        world=copy.deepcopy(IDENTITY);world[0][3]=100.
        tri=((1e-20,0.,0.),(1e-20,.5,0.),(1e-20,0.,.5));p=proof([tri],world=world)
        # float(100+1e-20) is 100, but every rational world x is above 100.
        self.assertEqual(100.+1e-20,100.)
        self.assertEqual(self.select(p,query(((99.,-1.,-1.),(100.,1.,1.))))['matched_triangle_indices'],[])

    def test_exact_affine_avoids_subnormal_unit_underflow(self):
        unit=math.ulp(0.);tri=((.5,0.,0.),(.5,1.,0.),(.5,0.,1.));p=proof([tri],unit=unit)
        self.assertEqual(.5*unit,0.)
        self.assertEqual(self.select(p,query(((-unit,-unit,-unit),(0.,unit,unit))))['matched_triangle_indices'],[])
        self.assertEqual(self.select(p,query(((0.,-unit,-unit),(unit,unit,unit))))['matched_triangle_indices'],[0])

    def test_selection_is_bound_to_stable_file_roles_frame_and_copied(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);s=selection(p)
        bound=region.bind_selection(p,s,deadline_ns=self.window());self.assertEqual(bound,query())
        s['region']['bounds'][0][0]=-9.;self.assertEqual(bound['region']['bounds'][0][0],-1.)
        for key,value in (('scene_sha256','c'*64),('rig_object_id','other'),('mesh_object_id','other'),('frame',dict(number=2,subframe=0.))):
            bad=selection(p);bad['source_ref'][key]=value
            with self.subTest(key=key):self.assert_error('stale_selection',lambda:region.bind_selection(p,bad,deadline_ns=self.window()))

    def test_selection_frame_and_envelopes_reject_bool_and_extra_fields(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);s=selection(p)
        for field,value in (('number',True),('subframe',False),('subframe',1.),('subframe',float('nan'))):
            bad=copy.deepcopy(s);bad['source_ref']['frame'][field]=value
            self.assert_error('frame',lambda:region.bind_selection(p,bad,deadline_ns=self.window()))
        for bad in (None,False,dict(s,extra=True),dict(s,schema='surface-deformation-region-selection-v2')):
            self.assert_error('selection_fields',lambda:region.bind_selection(p,bad,deadline_ns=self.window()))

    def test_region_bounds_and_coordinate_space_are_strict(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))])
        for value in (False,None,float('nan'),float('inf'),1e9+1,10**1000):
            bad=query();bad['region']['bounds'][0][0]=value
            with self.subTest(value=str(value)[:40]):self.assert_error('region_bounds',lambda:self.select(p,bad))
        for field,value in (('kind','sphere'),('coordinate_space','reference_local')):
            bad=query();bad['region'][field]=value;self.assert_error('region_kind',lambda:self.select(p,bad))
        for value in (1.,2.):
            bad=query();bad['region']['bounds'][0][0]=value;self.assert_error('region_extent',lambda:self.select(p,bad))
        bad=query();bad['region']['bounds'][0]=tuple(bad['region']['bounds'][0]);self.assert_error('region_bounds',lambda:self.select(p,bad))

    def test_query_source_and_geometry_tail_are_checked_before_success(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);q=query();q['expected_source_sha256']='b'*64
        self.assert_error('stale_source',lambda:self.select(p,q))
        for bad in (None,False,dict(query(),extra=True),dict(query(),expected_source_sha256=True)):
            self.assert_error('query_fields',lambda:region.select(p,bad,deadline_ns=self.window()))
        p['triangles'].append([0,1,True]);self.assert_error('proof_shape',lambda:self.select(p))

    def test_limits_arithmetic_and_original_deadline_fail_closed(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);p['current']*=86
        self.assert_error('mesh_budget',lambda:self.select(p))
        self.assert_error('arithmetic_budget',lambda:region.limited(Fraction(1,1<<16384)))
        self.assert_error('arithmetic_budget',lambda:region.limited(1<<16384))
        for operation in (lambda:region.select(proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]),query(),deadline_ns=0),
                lambda:region.bind_selection(p,{},deadline_ns=0),lambda:region.summarize({},[],deadline_ns=0)):
            with self.assertRaisesRegex(ValueError,'^rig_pose_original_deadline$'):operation()

    def test_deadline_checked_inside_fraction_clipping_and_never_returns_empty(self):
        points=[tuple(Fraction(v) for v in p) for p in ((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))];calls=[0]
        def checkpoint(deadline):
            calls[0]+=1
            if calls[0]==17:raise ValueError('rig_pose_original_deadline')
        with patch.object(region.r,'check_time',side_effect=checkpoint):
            with self.assertRaisesRegex(ValueError,'^rig_pose_original_deadline$'):
                region.clipped(points,[Fraction(-1)]*3,[Fraction(1)]*3,deadline_ns=self.window())
        self.assertEqual(calls[0],17)

    def many(self,n=8):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.)) for _ in range(n)])
        return self.select(p)

    def test_summary_extrema_cover_all_members_and_do_not_depend_on_four_details(self):
        m=self.many();rows=[fact(i) for i in range(8)]
        rows[1]=fact(1,high=3.,low=.7,area=1.2);rows[2]=fact(2,high=1.2,low=.2,area=1.)
        rows[3]=fact(3,high=1.1,low=.7,area=.3);rows[4]=fact(4,high=2.,low=.7,area=4.)
        rows[7]=fact(7,state='unknown',reason='metric_resolution_insufficient');out=self.summarize(m,rows)
        self.assertEqual(out['matched_triangle_indices'],list(range(8)));self.assertEqual(out['triangles_total'],8)
        self.assertEqual(out['metric_extrema'],dict(max_principal_stretch=dict(triangle=1,value=3.),min_principal_stretch=dict(triangle=2,value=.2),
            min_area_ratio=dict(triangle=3,value=.3),max_area_ratio=dict(triangle=4,value=4.)))
        self.assertEqual([row['triangle'] for row in out['triangles']],[1,2,3,4]);self.assertEqual(out['details_omitted'],4)
        self.assertEqual(out['unknown_reasons'],dict(metric_resolution_insufficient=1));self.assertEqual(out['status'],'partial')
        self.assertFalse(out['all_members_measurable']);self.assertEqual(out['metric_scope'],'whole_original_triangles_not_clipped_integrals')

    def test_summary_ties_unknown_and_remaining_ids_follow_frozen_policy(self):
        m=self.many(6);rows=[fact(i) for i in range(6)];rows[1]=fact(1,state='unknown',reason='unweighted_vertex_source')
        rows[5]=fact(5,state='unknown',reason='metric_resolution_insufficient');out=self.summarize(m,rows)
        self.assertTrue(all(v['triangle']==0 for v in out['metric_extrema'].values()))
        self.assertEqual([row['triangle'] for row in out['triangles']],[0,1,2,3]);self.assertEqual(out['details_omitted'],2)
        self.assertEqual(out['triangles_measured'],4);self.assertEqual(out['triangles_unknown'],2)
        rows[0]['principal_stretches'][0]=99.;self.assertEqual(out['triangles'][0]['principal_stretches'][0],1.)

    def test_collapsed_is_a_measurable_fact_but_unknown_is_not_an_extreme(self):
        m=self.many(3);rows=[fact(0,high=.5,low=0.,area=0.,state='collapsed',reason='current_zero_area'),
            fact(1,state='unknown',reason='unweighted_vertex_source'),fact(2,high=2.,low=1.,area=2.)]
        out=self.summarize(m,rows);self.assertEqual(out['triangles_collapsed'],1);self.assertEqual(out['triangles_measured'],1)
        self.assertEqual(out['metric_extrema']['min_area_ratio'],dict(triangle=0,value=0.))
        self.assertEqual(out['metric_extrema']['min_principal_stretch'],dict(triangle=0,value=0.))
        self.assertEqual(out['metric_extrema']['max_principal_stretch'],dict(triangle=2,value=2.))

    def test_empty_and_all_unknown_do_not_report_measurable_success(self):
        p=proof([((2.,2.,2.),(3.,2.,2.),(2.,3.,2.))]);out=self.summarize(self.select(p),[fact(0)])
        self.assertEqual(out['status'],'empty');self.assertFalse(out['all_members_measurable']);self.assertEqual(out['triangles_total'],0)
        self.assertEqual(out['matched_triangle_indices'],[]);self.assertEqual(out['triangles'],[]);self.assertEqual(out['details_omitted'],0)
        self.assertTrue(all(value is None for value in out['metric_extrema'].values()))
        out=self.summarize(self.many(2),[fact(i,state='unknown',reason='original_zero_area') for i in range(2)])
        self.assertEqual(out['status'],'partial');self.assertEqual(out['triangles_unknown'],2)
        self.assertFalse(out['all_members_measurable']);self.assertTrue(all(value is None for value in out['metric_extrema'].values()))

    def test_complete_row_identity_binding_rejects_tails_duplicates_and_wrong_ids(self):
        m=self.many(3);rows=[fact(i) for i in range(3)]
        for bad in (rows[:-1],rows+[fact(3)],[rows[0],rows[1],rows[1]],[rows[0],rows[2],rows[1]]):
            self.assert_error('rows',lambda:self.summarize(m,bad))
        for ids in ([True],[3],[1,1],[2,1]):
            bad=copy.deepcopy(m);bad['matched_triangle_indices']=ids;self.assert_error('membership',lambda:self.summarize(bad,rows))

    def test_full_256_triangle_scan_and_256_vertex_limit_do_not_truncate(self):
        p=proof([((0.,0.,0.),(.5,0.,0.),(0.,.5,0.))]);p['current']+=[[9.,9.,9.] for _ in range(253)]
        p['triangles']=[[0,1,2] for _ in range(256)];m=self.select(p);out=self.summarize(m,[fact(i) for i in range(256)])
        self.assertEqual(m['vertices_transformed'],256);self.assertEqual(out['triangles_scanned'],256)
        self.assertEqual(out['matched_triangle_indices'],list(range(256)));self.assertEqual(out['triangles_total'],256)
        self.assertEqual(out['details_omitted'],252);self.assertTrue(out['all_members_measurable'])
        self.assertEqual([v['triangle'] for v in out['triangles']],[0,1,2,3])


if __name__=='__main__':unittest.main()
