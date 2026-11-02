"""Authored affine/identity/budget counterexamples for native anchor products.

These internal proof doubles are not native source-admission evidence. Numeric
expectations use exact scalar algebra; source/installed native QA is separate.
"""
import copy,math,time,unittest
from fractions import Fraction as Q
from unittest.mock import patch
from human_eye_plugin import deformation_anchors as a

I=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def proof():
    return dict(current=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[9.,9.,9.]],triangles=[[0,1,2]],world=copy.deepcopy(I),rig_world=copy.deepcopy(I),unit=1.,
        source_sha256='a'*64,source=dict(scene_sha256='b'*64,object_id='rig',mesh_identity=dict(object_id='mesh'),frame=dict(number=1,subframe=0.),
            document_epoch='c'*32,process_id=123),bone_landmarks=[
                dict(name='Root',parent=None,connected=False,use_deform=True,head=[0.,0.,0.],tail=[0.,1.,0.]),
                dict(name='Child',parent='Root',connected=True,use_deform=True,head=[0.,1.,0.],tail=[0.,2.,0.])])


def pins(p):
    v={key:format(i+1,'x')*64 for i,key in enumerate(a.PIN_FIELDS)};v['scene_sha256']=p['source']['scene_sha256'];return v


class DeformationAnchorTests(unittest.TestCase):
    def window(self):return time.perf_counter_ns()+5_000_000_000
    def catalog(self,p,**kw):return a.catalog(p,pins=kw.pop('pins',pins(p)),deadline_ns=kw.pop('deadline_ns',self.window()),**kw)
    def choose(self,p,bone='Child',endpoint='head',half=(.5,.5,.5),directory=None):
        directory=self.catalog(p) if directory is None else directory
        anchor=next(v for v in directory['anchors'] if v['bone_name']==bone and v['endpoint']==endpoint)
        return dict(schema='surface-deformation-anchor-selection-v1',source_ref=copy.deepcopy(directory['source_ref']),catalog_sha256=directory['catalog_sha256'],
            anchor_id=anchor['anchor_id'],half_extents_m=list(half))
    def bind(self,p,s,**kw):return a.bind_selection(p,s,pins=kw.pop('pins',pins(p)),deadline_ns=kw.pop('deadline_ns',self.window()),**kw)
    def resolve(self,p,q,**kw):return a.resolve(p,q,pins=kw.pop('pins',pins(p)),deadline_ns=kw.pop('deadline_ns',self.window()),**kw)
    def error(self,reason,call):
        with self.assertRaisesRegex(ValueError,'^rig_pose_deformation_anchor_'+reason+'$'):call()

    def test_complete_native_graph_and_explicit_stable_payload(self):
        p=proof();before=copy.deepcopy(p);c=self.catalog(p)
        self.assertEqual(c['schema'],'surface-deformation-anchor-catalog-v1');self.assertEqual(c['status'],'observed')
        self.assertEqual(c['completeness'],dict(bones_total=2,anchors_total=4,anchors_available=4,anchors_unavailable=0,anchors_omitted=0,graph_complete=True,anchors_complete=True))
        self.assertEqual([b['name'] for b in c['graph']],['Child','Root']);self.assertEqual(len(c['anchors']),4)
        self.assertEqual(c['catalog_sha256'],a.r.digest({key:c[key] for key in a.STABLE_FIELDS}))
        self.assertEqual(c['live_capture'],dict(source_sha256=p['source_sha256'],document_epoch='c'*32,process_id=123))
        self.assertFalse(c['execution_authority']);self.assertEqual(c['geometry_setters'],0);self.assertFalse(c['original_file_saved']);self.assertEqual(p,before)
        self.assertEqual(c['scope']['anchor_semantics'],'native_evaluated_bone_endpoints_only')

    def test_coincident_endpoints_keep_different_native_identities(self):
        p=proof();c=self.catalog(p);s1=self.choose(p,'Root','tail',directory=c);s2=self.choose(p,'Child','head',directory=c)
        self.assertNotEqual(s1['anchor_id'],s2['anchor_id']);q1,t1=self.resolve(p,self.bind(p,s1));q2,t2=self.resolve(p,self.bind(p,s2))
        self.assertEqual(q1,q2);self.assertNotEqual(t1['anchor_id'],t2['anchor_id']);self.assertEqual(t1['bone_name'],'Root');self.assertEqual(t2['bone_name'],'Child')

    def test_rig_world_and_mesh_world_are_separate_and_units_apply(self):
        p=proof();p['unit']=.001;p['rig_world']=[[0.,-1.,0.,2.],[1.,0.,0.,3.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        p['world'][0][3]=4.;p['world'][1][3]=-2.;p['world'][2][3]=1.;c=self.catalog(p)
        endpoint=next(x for x in c['anchors'] if x['bone_name']=='Root' and x['endpoint']=='tail')
        self.assertEqual(endpoint['position_world_m'],[.001,.003,0.])
        bounds=c['bounds']['bounds_world_m'];truth=[[Q(4)*Q(.001),-Q(2)*Q(.001),Q(.001)],[Q(5)*Q(.001),-Q(.001),Q(.001)]]
        for side,expected in zip(bounds,truth):
            for value,t in zip(side,expected):self.assertLessEqual(abs(Q(value)-t),Q(math.ulp(value)))

    def test_nearest_position_and_outward_interval_contain_exact_affine_sum(self):
        p=proof();p['rig_world'][0][3]=.1;p['bone_landmarks'][0]['head'][0]=.2;c=self.catalog(p)
        x=next(v for v in c['anchors'] if v['bone_name']=='Root' and v['endpoint']=='head');truth=Q(.1)+Q(.2)
        self.assertEqual(x['position_world_m'][0],float(truth));lo,hi=x['position_interval_world_m']
        self.assertLessEqual(Q(lo[0]),truth);self.assertGreaterEqual(Q(hi[0]),truth);self.assertNotEqual(lo[0],hi[0])
        self.assertGreater(Q(math.nextafter(lo[0],math.inf)),truth);self.assertLess(Q(math.nextafter(hi[0],-math.inf)),truth)

    def test_small_affine_increment_is_not_erased_before_interval_projection(self):
        p=proof();p['rig_world'][0][3]=1.;p['bone_landmarks'][0]['head'][0]=2**-54;c=self.catalog(p)
        x=next(v for v in c['anchors'] if v['bone_name']=='Root' and v['endpoint']=='head')
        self.assertEqual(x['position_world_m'][0],1.);self.assertEqual(x['position_interval_world_m'][0][0],1.)
        self.assertEqual(x['position_interval_world_m'][1][0],math.nextafter(1.,math.inf))

    def test_nonzero_underflow_is_unavailable_without_clamping(self):
        p=proof();p['unit']=math.ulp(0.);p['bone_landmarks'][0]['head'][0]=.25;c=self.catalog(p)
        x=next(v for v in c['anchors'] if v['bone_name']=='Root' and v['endpoint']=='head')
        self.assertEqual(x['reason'],'coordinate_underflow');self.assertEqual(x['state'],'unavailable')
        self.assertIsNone(x['position_world_m']);self.assertIsNone(x['position_interval_world_m']);self.assertEqual(c['status'],'partial')
        s=self.choose(p,'Root','head',directory=c);self.error('anchor_unavailable',lambda:self.bind(p,s))

    def test_anchor_outside_query_domain_remains_present_and_unavailable(self):
        p=proof();p['bone_landmarks'][0]['head'][0]=2e9;c=self.catalog(p)
        x=next(v for v in c['anchors'] if v['bone_name']=='Root' and v['endpoint']=='head')
        self.assertEqual(x['reason'],'outside_region_coordinate_domain');self.assertIsNone(x['position_world_m'])
        self.assertEqual(c['completeness']['anchors_total'],4);self.assertEqual(c['completeness']['anchors_unavailable'],1)
        self.error('anchor_unavailable',lambda:self.bind(p,self.choose(p,'Root','head',directory=c)))

    def test_surface_context_bounds_exclude_but_count_loose_vertices(self):
        p=proof();c=self.catalog(p);b=c['bounds'];self.assertEqual(b['bounds_world_m'],[[0.,0.,0.],[1.,1.,0.]])
        self.assertEqual((b['vertices_total'],b['surface_vertices_total'],b['loose_vertices_excluded'],b['triangles_total']),(4,3,1,1))
        self.assertEqual(b['kind'],'referenced_current_triangle_hull_aabb');self.assertTrue(all(v['endpoint'] in ('head','tail') for v in c['anchors']))

    def test_degenerate_hulls_remain_context_and_no_mesh_center_anchor_exists(self):
        p=proof();p['current'][:3]=[[.25,.25,.25]]*3;c=self.catalog(p)
        self.assertEqual(c['bounds']['bounds_world_m'],[[.25,.25,.25],[.25,.25,.25]])
        self.assertEqual(len(c['anchors']),4);self.assertFalse(any('mesh' in v['anchor_id'] for v in c['anchors']))

    def test_stable_catalog_is_separate_from_live_capture_and_old_recipe(self):
        p=proof();c=self.catalog(p);s=self.choose(p,directory=c);recipe=self.bind(p,s)
        fresh=copy.deepcopy(p);fresh['source_sha256']='d'*64;fresh['source']['document_epoch']='e'*32;fresh['source']['process_id']=456
        new=self.catalog(fresh);self.assertEqual(c['catalog_sha256'],new['catalog_sha256']);self.assertNotEqual(c['live_capture'],new['live_capture'])
        self.assertEqual(self.bind(fresh,s)['expected_source_sha256'],fresh['source_sha256'])
        self.error('stale_source',lambda:self.resolve(fresh,recipe))

    def test_public_geometry_graph_and_operator_pin_changes_invalidate_catalog(self):
        original=proof();s=self.choose(original)
        for change in (lambda p:p['rig_world'][0].__setitem__(3,.125),lambda p:p.__setitem__('unit',.5),
                lambda p:p['bone_landmarks'][1].__setitem__('connected',False),lambda p:p['bone_landmarks'][0].__setitem__('use_deform',False)):
            p=copy.deepcopy(original);change(p);self.error('stale_catalog',lambda:self.bind(p,s))
        for key in ('profile_sha256','runtime_source_sha256','binary_sha256'):
            changed=pins(original);changed[key]='f'*64;self.error('stale_catalog',lambda:self.bind(original,s,pins=changed))

    def test_pins_require_exact_fields_values_and_scene_binding(self):
        p=proof();good=pins(p)
        for changed in (dict(good,extra='f'*64),{k:v for k,v in good.items() if k!='math_sha256'},dict(good,profile_sha256=True),dict(good,scene_sha256='f'*64)):
            self.error('pins_binding',lambda:self.catalog(p,pins=changed))

    def test_graph_rejects_duplicates_cycles_missing_parents_and_bad_flags(self):
        for change in (lambda p:p['bone_landmarks'].append(copy.deepcopy(p['bone_landmarks'][0])),lambda p:p['bone_landmarks'][0].__setitem__('parent','Child'),
                lambda p:p['bone_landmarks'][1].__setitem__('parent','Absent'),lambda p:p['bone_landmarks'][0].__setitem__('connected',1),
                lambda p:p['bone_landmarks'][0].__setitem__('head',[float('nan'),0.,0.])):
            p=proof();change(p);self.error('bone_graph',lambda:self.catalog(p))

    def test_all_sixteen_bones_are_complete_without_positional_deduplication(self):
        p=proof();p['bone_landmarks']=[dict(name='B%02d'%i,parent=None if i==0 else 'B%02d'%(i-1),connected=False,use_deform=True,
            head=[0.,0.,0.],tail=[0.,1.,0.]) for i in range(16)];c=self.catalog(p)
        self.assertEqual((len(c['graph']),len(c['anchors'])),(16,32));self.assertEqual(len({v['anchor_id'] for v in c['anchors']}),32)
        p['bone_landmarks'].append(dict(p['bone_landmarks'][-1],name='Overflow'));self.error('bone_graph',lambda:self.catalog(p))

    def test_full_geometry_shape_and_loose_tail_validate_before_context(self):
        p=proof();p['current'][-1]=[float('inf'),0.,0.];self.error('proof_shape',lambda:self.catalog(p))
        for key,value in [('current',[]),('current',[[0.,0.,0.]]*257),('triangles',[[0,1,True]]),('triangles',[[0,1,999]]),('rig_world',[[1.]])]:
            p=proof();p[key]=value;self.error('proof_shape',lambda:self.catalog(p))

    def test_selection_schema_frame_source_and_digest_are_strict(self):
        p=proof();s=self.choose(p)
        for value in (None,dict(s,extra=True),dict(s,catalog_sha256=True),dict(s,schema='other')):self.error('selection_fields',lambda:self.bind(p,value))
        bad=copy.deepcopy(s);bad['source_ref']['frame']['number']=True;self.error('frame',lambda:self.bind(p,bad))
        bad=copy.deepcopy(s);bad['source_ref']['frame']['number']=2;self.error('stale_selection',lambda:self.bind(p,bad))
        bad=copy.deepcopy(s);bad['source_ref']['mesh_object_id']='wrong';self.error('stale_selection',lambda:self.bind(p,bad))
        self.error('stale_catalog',lambda:self.bind(p,dict(s,catalog_sha256='f'*64)))

    def test_unknown_and_malformed_anchor_id_fail_without_fallback(self):
        p=proof();s=self.choose(p)
        self.error('unknown_anchor',lambda:self.bind(p,dict(s,anchor_id='bone-anchor:'+'f'*64)))
        for value in (None,True,'mesh-center','bone-anchor:'+'f'*63):self.error('anchor_id',lambda:self.bind(p,dict(s,anchor_id=value)))

    def test_half_sizes_have_strict_finite_nonbool_lower_and_upper_limits(self):
        p=proof();s=self.choose(p)
        for value in (None,[True,1.,1.],[0.,1.,1.],[1e-7,1.,1.],[1e6+1,1.,1.],[float('nan'),1.,1.],[float('inf'),1.,1.],(1.,1.,1.),[1.,1.]):
            self.error('half_extents',lambda:self.bind(p,dict(s,half_extents_m=value)))
        self.bind(p,dict(s,half_extents_m=[1e-6]*3));self.bind(p,dict(s,half_extents_m=[1e6]*3))

    def test_box_uses_published_center_and_minimal_outward_binary_bounds(self):
        p=proof();p['bone_landmarks'][1]['head'][0]=.1;s=self.choose(p,half=(.2,.2,.2));rq,t=self.resolve(p,self.bind(p,s))
        for axis,(center,half) in enumerate(zip(t['center_world_m'],t['half_extents_m'])):
            lo,hi=Q(center)-Q(half),Q(center)+Q(half);a0,a1=rq['region']['bounds'][0][axis],rq['region']['bounds'][1][axis]
            self.assertLessEqual(Q(a0),lo);self.assertGreaterEqual(Q(a1),hi)
            self.assertGreater(Q(math.nextafter(a0,math.inf)),lo);self.assertLess(Q(math.nextafter(a1,-math.inf)),hi)
        self.assertEqual(t['center_world_m'][0],.1);self.assertEqual(t['region'],rq['region'])

    def test_near_domain_edge_does_not_clamp_or_shift_box(self):
        p=proof();p['bone_landmarks'][1]['head'][0]=1e9;c=self.catalog(p)
        self.assertEqual(next(v for v in c['anchors'] if v['bone_name']=='Child' and v['endpoint']=='head')['state'],'available')
        self.error('box_domain',lambda:self.bind(p,self.choose(p,directory=c)))

    def test_recipe_schema_catalog_and_source_are_checked_again(self):
        p=proof();q=self.bind(p,self.choose(p))
        for value in (None,dict(q,extra=True),dict(q,schema='other'),dict(q,expected_source_sha256=True)):self.error('query_fields',lambda:self.resolve(p,value))
        self.error('stale_source',lambda:self.resolve(p,dict(q,expected_source_sha256='f'*64)))
        self.error('stale_catalog',lambda:self.resolve(p,dict(q,catalog_sha256='f'*64)))

    def test_selection_query_trace_and_region_do_not_share_mutable_state(self):
        p=proof();s=self.choose(p);before=copy.deepcopy(s);q=self.bind(p,s);s['half_extents_m'][0]=99.
        self.assertEqual(q['half_extents_m'],before['half_extents_m']);rq,t=self.resolve(p,q);self.assertEqual(q,self.bind(p,before))
        rq['region']['bounds'][0][0]=-999.;self.assertNotEqual(rq['region'],t['region'])
        self.assertEqual(t['anchor_id'],q['anchor_id']);self.assertEqual(t['metric_scope'],'whole_original_triangles_not_clipped_integrals')

    def test_original_deadline_arithmetic_and_report_budgets_fail_closed(self):
        p=proof()
        with self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):self.catalog(p,deadline_ns=0)
        with patch.object(a,'MAX_BITS',8):
            p['bone_landmarks'][0]['head'][0]=.1;self.error('arithmetic_budget',lambda:self.catalog(p))
        with patch.object(a.r,'MAX_BYTES',128):self.error('report_byte_budget',lambda:self.catalog(proof()))

    def test_deadline_is_checked_during_endpoint_transform(self):
        p=proof();calls=[];check=a.r.check_time
        def during(deadline):
            calls.append(deadline)
            if len(calls)==12:check(0)
            check(deadline)
        with patch.object(a.r,'check_time',side_effect=during):
            with self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):self.catalog(p)
        self.assertEqual(len(calls),12)


if __name__=='__main__':unittest.main()
