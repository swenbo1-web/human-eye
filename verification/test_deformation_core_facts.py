"""Analytic complete-core projection checks, not source-admission evidence.

Authored internal proofs exercise the new projection, independent scalar
diagonal maps give the expected metrics. Formal source/worker QA is separate.
"""
import copy,hashlib,json,math,time,unittest
from dataclasses import replace
from unittest.mock import patch
from human_eye_plugin import deformation_core_facts as f,deformation_context as c,deformation_anchors as a,deformation_region as g,surface_deformation as s
from verification.test_deformation_anchors import proof as anchor_proof
from verification.test_deformation_context import fixture,setup,run


def validation():
    return dict(schema='small-skin-source-snapshot-v1',method='external_binding_full_dependency_FK_and_LBS',
        max_replay_error=0.,replay_atol=2e-5,animation_curves_checked=0,not_coordinate_measurement_error=True)


def call(data,**kwargs):
    values={key:data[key] for key in ('policy','policy_sha256','pins','rows','deadline_ns')};values.update(source_validation=validation());values.update(kwargs)
    return f.plan(data['proof'],data['query'],**values)


def ref(data,membership):
    policy=data['policy']
    return dict(catalog_sha256=policy['catalog_sha256'],policy_sha256=data['policy_sha256'],anchor_id=policy['anchor_id'],
        half_extents_m=policy['required_core_half_extents_m'][:],region=copy.deepcopy(membership['region']))


def projection(data,membership,**kwargs):
    values=dict(rows=data['rows'],core_ref=ref(data,membership),pins=data['pins'],source_validation=validation(),deadline_ns=data['deadline_ns']);values.update(kwargs)
    return f.project(data['proof'],membership,**values)


def diagonal_fixture():
    p=anchor_proof();original=[];current=[];triangles=[]
    scales=[(1.,1.)]*21;scales[16]=(8.,1.);scales[17]=(4.,.03125);scales[18]=(.0625,.0625);scales[19]=(4.,4.);scales[20]=(64.,1.)
    for index,(sx,sy) in enumerate(scales):
        x=2. if index==20 else 0.;first=len(current)
        original.extend([[x,0.,0.],[x+.01,0.,0.],[x,.01,0.]])
        current.extend([[x,0.,0.],[x+.01*sx,0.,0.],[x,.01*sy,0.]])
        triangles.append([first,first+1,first+2])
    p.update(original=original,current=current,triangles=triangles,unweighted=[9,10,11],bones_total=2)
    return p


class CoreFactsTests(unittest.TestCase):
    def test_whole_core_with_late_distinct_witnesses_and_stronger_peripheral_extrema(self):
        d,_=setup(diagonal_fixture(),core=.5,candidates=(1.,));report,audit=call(d);facts=report['facts']
        self.assertEqual(facts['core_status'],'partial');self.assertEqual(facts['core_triangle_count'],20)
        self.assertEqual(facts['core_states'],dict(measured=19,collapsed=0,unknown=1))
        self.assertEqual(facts['core_unknown_reasons'],{'unweighted_vertex_source':1})
        expected=dict(max_principal_stretch=8.,min_principal_stretch=.03125,min_area_ratio=.00390625,max_area_ratio=16.)
        for key,value in expected.items():self.assertAlmostEqual(facts['core_extrema'][key],value,delta=1e-10)
        self.assertEqual(report['core_witnesses'],dict(max_principal_stretch=16,min_principal_stretch=17,min_area_ratio=18,max_area_ratio=19))
        self.assertEqual(audit['core_triangle_indices'],list(range(20)));self.assertEqual(len(audit['core_rows']),20)
        self.assertEqual(audit['core_rows_sha256'],f.r.digest(audit['core_rows']))
        self.assertEqual(report['completeness']['per_face_rows_omitted'],20);self.assertNotIn('triangles',report)
        self.assertEqual(set(facts),{'core_status','core_triangle_count','core_states','core_unknown_reasons','core_extrema'})

    def test_empty_all_unknown_mixed_and_collapsed_have_complete_explicit_facts(self):
        for options,status,counts in [({'empty':True},'empty',(0,0,0)),({'unknown_core':True},'partial',(0,0,1)),
                ({'collapsed':True},'observed',(0,1,0)),({},'observed',(1,0,0))]:
            with self.subTest(options=options):
                d,_=setup(fixture(**options));report,audit=call(d);facts=report['facts']
                self.assertEqual(facts['core_status'],status);self.assertEqual(tuple(facts['core_states'].values()),counts)
                self.assertTrue(report['completeness']['core_facts_complete']);self.assertTrue(report['completeness']['membership_complete'])
                self.assertEqual(report['completeness']['all_members_unknown'],bool(counts[2]))
                if status=='empty' or counts[2]:
                    self.assertEqual(facts['core_extrema'],dict.fromkeys(f.METRICS));self.assertEqual(report['core_witnesses'],dict.fromkeys(f.METRICS))
                elif counts[1]:
                    self.assertEqual(facts['core_extrema']['min_area_ratio'],0.);self.assertEqual(facts['core_extrema']['max_area_ratio'],0.)
                    self.assertFalse(report['scope']['peripheral_shrinking'])

    def test_closed_edge_and_point_membership_do_not_imply_positive_area(self):
        p=anchor_proof();triangles=[[[.125,0.,0.],[.25,0.,0.],[.125,.125,0.]],
            [[.125,.125,.125],[.25,.125,.125],[.125,.25,.125]],[[.25,.25,0.],[.5,.25,0.],[.25,.5,0.]]]
        vertices=[v for tri in triangles for v in tri];p.update(original=copy.deepcopy(vertices),current=copy.deepcopy(vertices),
            triangles=[[i*3,i*3+1,i*3+2] for i in range(3)],unweighted=[],bones_total=2)
        d,_=setup(p,core=.125);report,audit=call(d)
        self.assertEqual(audit['core_triangle_indices'],[0,1]);self.assertEqual(report['facts']['core_triangle_count'],2)
        self.assertEqual(report['scope']['contact_extent'],'not_checked');self.assertEqual(set(report['core_witnesses'].values()),{0})

    def test_pure_projection_reuses_b3e_core_without_any_new_geometry_or_B2(self):
        d,_=setup(fixture());_,old_audit=run(d)
        with patch.object(g,'prepare_geometry',side_effect=AssertionError('new geometry')),patch.object(g,'select_prepared',side_effect=AssertionError('new scan')),\
                patch.object(s,'_geometry_rows',side_effect=AssertionError('new B2')),patch.object(a,'catalog',side_effect=AssertionError('new catalog')):
            report,audit=projection(d,old_audit['core_membership'])
        self.assertEqual(audit['core_rows'],old_audit['core_rows']);self.assertEqual(audit['core_rows_sha256'],old_audit['core_rows_sha256'])
        self.assertEqual(report['facts']['core_triangle_count'],len(old_audit['core_triangle_indices']))
        for key in ('pure_projection_B2_rows_passes','pure_projection_geometry_cache_preparations','pure_projection_region_scans','candidates_evaluated'):
            self.assertEqual(audit[key],0)

    def test_wrapper_prepares_and_scans_core_once_without_B2_primary_or_candidates(self):
        d,_=setup(fixture());original_box=a.box
        with patch.object(g,'prepare_geometry',wraps=g.prepare_geometry) as prepare,patch.object(g,'select_prepared',wraps=g.select_prepared) as select,\
                patch.object(s,'_geometry_rows',side_effect=AssertionError('new B2')),patch.object(a,'resolve',side_effect=AssertionError('primary anchor')),\
                patch.object(a,'box',wraps=original_box) as box:
            report,audit=call(d)
        self.assertEqual(prepare.call_count,1);self.assertEqual(select.call_count,1);self.assertEqual(box.call_count,1)
        self.assertEqual(box.call_args.args[1],d['policy']['required_core_half_extents_m'])
        self.assertEqual(audit['geometry_cache_preparations'],1);self.assertEqual(audit['region_scans'],1);self.assertEqual(audit['B2_rows_passes'],0)

    def test_complete_membership_same_source_region_counts_and_sorted_ids_required(self):
        d,_=setup(fixture());_,audit=call(d);good=audit['core_membership']
        bads=[dict(good,membership_complete=False),dict(good,source_sha256='0'*64),dict(good,triangles_scanned=8),
            dict(good,vertices_transformed=True),dict(good,matched_triangle_indices=[True]),dict(good,matched_triangle_indices=[0,0]),
            dict(good,coordinate_model='approximate'),dict(good,extra=True)]
        changed=copy.deepcopy(good);changed['region']['bounds'][0][0]-=.01;bads.append(changed)
        for bad in bads:
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'deformation_core_facts_membership'):
                projection(d,bad,core_ref=ref(d,good))

    def test_private_rows_bind_full_geometry_and_source_metadata(self):
        d,_=setup(fixture());_,audit=call(d)
        for change in ('source','geometry'):
            changed=copy.deepcopy(d['proof'])
            if change=='source':changed['source']['frame']['number']+=1
            else:changed['current'][0][0]+=.0001
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'deformation_rows_binding'):
                f.project(changed,audit['core_membership'],rows=d['rows'],core_ref=ref(d,audit['core_membership']),
                    pins=d['pins'],source_validation=validation(),deadline_ns=d['deadline_ns'])
        with self.assertRaisesRegex(ValueError,'deformation_rows_binding'):projection(d,audit['core_membership'],rows=json.loads(d['rows'].payload))

    def test_bad_metric_rows_cannot_publish_a_complete_fact_report(self):
        d,_=setup(fixture());_,audit=call(d);good=json.loads(d['rows'].payload)
        for edits in (dict(principal_stretches=[True,0.]),dict(principal_stretches=[0.,1.]),dict(area_ratio=-1.),
                dict(state='unknown',reason='',principal_stretches=None,area_ratio=None),dict(state='unknown',reason='missing',principal_stretches=[1.,1.])):
            bad=copy.deepcopy(good);bad[0].update(edits);rows=replace(d['rows'],payload=f.r.encoded(bad))
            with self.subTest(edits=edits),self.assertRaisesRegex(ValueError,'deformation_core_facts_rows'):
                projection(d,audit['core_membership'],rows=rows)

    def test_bad_policy_source_catalog_anchor_or_pins_reject_without_fallback(self):
        d,_=setup(fixture())
        for query,policy,pins,reason in [(dict(d['query'],expected_source_sha256='0'*64),d['policy'],d['pins'],'context_stale_source'),
                (dict(d['query'],policy_sha256='0'*64),d['policy'],d['pins'],'context_policy_binding'),
                (dict(d['query'],catalog_sha256='0'*64),dict(d['policy'],catalog_sha256='0'*64),d['pins'],'context_stale_catalog'),
                (d['query'],dict(d['policy'],min_saved_bytes=1),d['pins'],'context_min_saved_bytes'),
                (d['query'],d['policy'],dict(d['pins'],scene_sha256='0'*64),'anchor_pins_binding')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                f.plan(d['proof'],query,policy=policy,policy_sha256=d['policy_sha256'],pins=pins,rows=d['rows'],source_validation=validation(),deadline_ns=d['deadline_ns'])

    def test_metadata_unknown_reason_publication_ascii_LF_and_budget_include_final_validation(self):
        p=fixture(unknown_core=True,unicode=True);p['source']['object_id']='rig 根骨 λ';p['source']['mesh_identity']['object_id']='mesh 网格 λ'
        d,_=setup(p);report,audit=call(d)
        blob=c.publication_bytes(report);self.assertTrue(blob.endswith(b'\n'));self.assertFalse(blob.endswith(b'\n\n'));blob.decode('ascii')
        self.assertEqual(audit['published_publication_bytes'],len(blob));self.assertEqual(audit['published_publication_sha256'],hashlib.sha256(blob).hexdigest())
        self.assertIn('source_validation',json.loads(blob));self.assertIn('not_coordinate_measurement_error',json.loads(blob)['source_validation'])
        self.assertIn(b'\\u',blob)
        short,_=setup(fixture(long=True,unknown_core=True));short_report,short_audit=call(short)
        with patch.object(f.r,'MAX_BYTES',len(c.publication_bytes(short_report))-1),self.assertRaisesRegex(ValueError,'deformation_core_facts_report_byte_budget'):
            projection(short,short_audit['core_membership'])
        for bad in (None,dict(validation(),extra=True),dict(validation(),replay_atol=False),dict(validation(),max_replay_error=1.),dict(validation(),animation_curves_checked=True)):
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'deformation_core_facts_source_validation'):call(d,source_validation=bad)

    def test_original_deadline_expiry_before_and_after_report_or_audit_never_returns_success(self):
        d,_=setup(fixture());deadline=d['deadline_ns']
        with self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):call(d,deadline_ns=0)
        publication=c.publication_bytes
        def late_publication(report):
            blob=publication(report)
            f.r.time.perf_counter_ns=lambda:deadline
            return blob
        with patch.object(f.r.time,'perf_counter_ns',side_effect=time.perf_counter_ns):
            with patch.object(c,'publication_bytes',side_effect=late_publication),self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):call(d)
        original_digest=f.r.digest
        def late_digest(value):
            result=original_digest(value)
            if type(value) is list:f.r.time.perf_counter_ns=lambda:deadline
            return result
        with patch.object(f.r.time,'perf_counter_ns',side_effect=time.perf_counter_ns):
            with patch.object(f.r,'digest',side_effect=late_digest),self.assertRaisesRegex(ValueError,'rig_pose_original_deadline'):call(d)

    def test_inputs_public_output_and_local_audit_are_not_mutable_aliases(self):
        d,_=setup(fixture());before=copy.deepcopy(d['proof']);valid=validation();report,audit=call(d,source_validation=valid)
        self.assertEqual(d['proof'],before);original_payload=d['rows'].payload;valid['max_replay_error']=1.
        audit['core_membership']['region']['bounds'][0][0]=-999.;audit['core_rows'][0]['principal_stretches'][0]=999.
        self.assertEqual(report['source_validation']['max_replay_error'],0.)
        self.assertNotEqual(report['core_ref']['region']['bounds'][0][0],-999.);self.assertAlmostEqual(report['facts']['core_extrema']['max_principal_stretch'],1.)
        again,again_audit=call(d);self.assertEqual(d['rows'].payload,original_payload)
        self.assertAlmostEqual(again_audit['core_rows'][0]['principal_stretches'][0],1.);self.assertEqual(again['facts'],report['facts'])
        d['pins']['scene_sha256']='0'*64;self.assertNotEqual(report['operator_pins']['scene_sha256'],'0'*64)
        self.assertFalse(report['execution_authority']);self.assertEqual(report['geometry_setters'],0);self.assertFalse(report['original_file_saved'])


if __name__=='__main__':unittest.main()
