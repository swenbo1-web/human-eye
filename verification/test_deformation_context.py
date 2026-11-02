"""Authored context-retention examples; not native source admission evidence."""
import copy,hashlib,json,time,unittest
from dataclasses import FrozenInstanceError,replace
from unittest.mock import patch
from human_eye_plugin import deformation_context as c,deformation_anchors as a,deformation_region as g,surface_deformation as s
from verification.test_deformation_anchors import proof as anchor_proof,pins


def fixture(*,empty=False,unknown_core=False,unknown_context=False,collapsed=False,long=False,unicode=False):
    p=anchor_proof();p['bone_landmarks'][0].update(head=[0.,0.,0.],tail=[0.,1.,0.])
    triangles=[]
    if long:triangles=[[[0.,0.,0.],[6.,0.,0.],[0.,6.,0.]]]
    else:
        for i in range(9):
            x=.5 if i==0 and empty else 0. if i==0 else 1.+i*.5
            triangles.append([[x+.02,.02,0.],[x+.08,.02,0.],[x+.02,.08,0.]])
    vertices=[v for tri in triangles for v in tri];p.update(original=copy.deepcopy(vertices),current=copy.deepcopy(vertices),
        triangles=[[i*3,i*3+1,i*3+2] for i in range(len(triangles))],unweighted=[],bones_total=2)
    if unknown_core:p['unweighted']=[0,1,2]
    if unknown_context:p['unweighted'].extend(range(3,len(vertices)))
    if collapsed:p['current'][:3]=[[.02,0.,0.],[.08,0.,0.],[.05,0.,0.]]
    if unicode:
        p['source']['mesh_identity']['name']='网格 λ';p['bone_landmarks'][0]['name']='根骨 λ';p['bone_landmarks'][1]['parent']='根骨 λ'
    return p


def setup(p,*,core=.1,primary=8.,candidates=(.2,),maximum=0,saved=256,budget=250):
    deadline=time.perf_counter_ns()+10_000_000_000;directory=a.catalog(p,pins=pins(p),deadline_ns=deadline)
    item=next(v for v in directory['anchors'] if v['endpoint']=='head' and v['bone_name']==p['bone_landmarks'][0]['name'])
    policy=dict(schema='surface-deformation-context-policy-v1',source_ref=copy.deepcopy(directory['source_ref']),catalog_sha256=directory['catalog_sha256'],
        anchor_id=item['anchor_id'],required_core_half_extents_m=[core]*3,primary_half_extents_m=[primary]*3,
        candidate_half_extents_m=[[h]*3 for h in candidates],max_surplus_members=maximum,min_saved_bytes=saved,planning_budget_ms=budget)
    # The file SHA is intentionally not the canonical dictionary digest.
    digest=hashlib.sha256(json.dumps(policy,indent=2,ensure_ascii=False).encode()).hexdigest()
    selection=dict(schema='surface-deformation-context-selection-v1',source_ref=copy.deepcopy(policy['source_ref']),catalog_sha256=policy['catalog_sha256'],
        anchor_id=policy['anchor_id'],policy_sha256=digest)
    query=c.bind_selection(p,selection,policy=policy,policy_sha256=digest,pins=pins(p),deadline_ns=deadline)
    rows=s._geometry_rows(p,deadline_ns=deadline)
    def factory(membership,trace):
        report=s._report_from_rows(p,rows,deadline_ns=deadline,region_membership=membership)
        report['anchor_query']=copy.deepcopy(trace);report['source_validation']=dict(method='authored_numeric_fixture_not_source_admission')
        return report
    return dict(proof=p,query=query,policy=policy,policy_sha256=digest,pins=pins(p),rows=rows,report_factory=factory,deadline_ns=deadline),selection


def run(data):
    return c.plan(data['proof'],data['query'],**{k:v for k,v in data.items() if k not in ('proof','query')})


class ContextQualityTests(unittest.TestCase):
    def test_policy_is_exact_frozen_and_rejects_untrusted_overrides(self):
        data,_=setup(fixture());policy=data['policy'];copy_value=c.validate_policy(policy);copy_value['candidate_half_extents_m'][0][0]=99
        self.assertEqual(policy['candidate_half_extents_m'],[[.2]*3])
        for bad in (None,False,dict(policy,extra=True),dict(policy,schema='other')):
            with self.subTest(value=bad),self.assertRaisesRegex(ValueError,'context_policy_fields'):c.validate_policy(bad)

    def test_candidate_authorization_core_primary_and_duplicates(self):
        data,_=setup(fixture());p=data['policy']
        cases=[('candidate_core',[[.01]*3]),('candidate_primary',[[9.]*3]),('candidate_duplicate',[[8.]*3]),
            ('candidate_duplicate',[[.2]*3,[.2]*3]),('candidate_limit',[[.2]*3,[.3]*3,[.4]*3])]
        for reason,halves in cases:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'context_'+reason):c.validate_policy(dict(p,candidate_half_extents_m=halves))

    def test_policy_numeric_bounds_do_not_accept_bools_nans_or_weak_gates(self):
        data,_=setup(fixture());p=data['policy']
        for field,values in [('min_saved_bytes',[True,0,255,65537,256.]),('max_surplus_members',[False,-1,257,.5]),
                ('planning_budget_ms',[True,0,251,1.])]:
            for value in values:
                with self.subTest(field=field,value=value),self.assertRaisesRegex(ValueError,'context_'+field):c.validate_policy(dict(p,**{field:value}))
        for half in ([True,.1,.1],[0.,.1,.1],[float('nan'),.1,.1],[1e7]*3):
            with self.assertRaisesRegex(ValueError,'context_half_extents'):c.validate_policy(dict(p,required_core_half_extents_m=half))

    def test_selection_cannot_replace_policy_or_smuggle_a_center(self):
        d,selection=setup(fixture());p=d['proof']
        for value,reason in [(dict(selection,policy_sha256='0'*64),'policy_binding'),(dict(selection,center=[0,0,0]),'selection_fields'),
                (dict(selection,anchor_id='bone-anchor:'+'0'*64),'policy_binding')]:
            with self.assertRaisesRegex(ValueError,'context_'+reason):c.bind_selection(p,value,policy=d['policy'],policy_sha256=d['policy_sha256'],pins=d['pins'],deadline_ns=d['deadline_ns'])

    def test_source_frame_catalog_and_raw_query_are_bound(self):
        d,_=setup(fixture())
        for change,reason in [(dict(expected_source_sha256='0'*64),'stale_source'),(dict(catalog_sha256='0'*64),'stale_catalog'),
                (dict(policy_sha256='0'*64),'policy_binding'),(dict(extra=True),'query_fields')]:
            value=dict(d,query=dict(d['query'],**change))
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,'context_'+reason):run(value)

    def test_optional_api_shares_one_exact_cache_and_one_B2_rows_pass(self):
        p=fixture()
        with patch.object(s,'triangle_facts',wraps=s.triangle_facts) as metric:
            d,_=setup(p);out,audit=run(d)
            self.assertEqual(metric.call_count,9)
        self.assertEqual(audit['geometry_cache_preparations'],1);self.assertEqual(audit['B2_rows_passes'],1)
        self.assertEqual(out['context_quality']['decision'],'selected_context')

    def test_context_selection_preserves_all_core_facts_and_exact_published_gain(self):
        d,_=setup(fixture());out,audit=run(d);q=out['context_quality']
        self.assertEqual((q['decision'],q['reason']),('selected_context','verified_byte_gain'))
        self.assertEqual(q['core_triangle_indices'],[0]);self.assertEqual(out['region_query']['matched_triangle_indices'],[0])
        self.assertEqual(q['core_rows_sha256'],c.r.digest(audit['core_rows']));self.assertEqual(audit['core_rows'],s._verified_rows(d['proof'],d['rows'],deadline_ns=d['deadline_ns'])[:1])
        self.assertGreaterEqual(audit['primary_publication_bytes']-len(c.publication_bytes(out)),256)
        self.assertEqual(audit['published_publication_sha256'],hashlib.sha256(c.publication_bytes(out)).hexdigest())
        self.assertEqual(q['contact_extent'],'not_checked')

    def test_normal_context_evaluates_no_alternatives(self):
        d,_=setup(fixture(),maximum=8);out,audit=run(d)
        self.assertEqual(out['context_quality']['reason'],'within_surplus_budget');self.assertEqual(audit['candidate_records'],[])
        self.assertEqual(out['context_quality']['candidates_evaluated'],0)

    def test_empty_core_is_not_repaired_by_background_surface(self):
        d,_=setup(fixture(empty=True));out,audit=run(d)
        self.assertEqual(out['context_quality']['reason'],'focus_empty');self.assertEqual(out['context_quality']['core_triangle_indices'],[])
        self.assertEqual(out['region_query']['triangles_total'],9);self.assertEqual(audit['candidate_records'],[])

    def test_all_unknown_core_cannot_be_diluted_by_known_context(self):
        d,_=setup(fixture(unknown_core=True));out,audit=run(d);q=out['context_quality']
        self.assertEqual(q['reason'],'focus_all_unknown');self.assertEqual(q['core_states']['unknown'],1)
        self.assertEqual(q['core_unknown_reasons'],{'unweighted_vertex_source':1});self.assertEqual(audit['candidate_records'],[])

    def test_unknown_context_removal_does_not_change_core_or_global_precision(self):
        d,_=setup(fixture(unknown_context=True));out,audit=run(d)
        self.assertEqual(out['context_quality']['decision'],'selected_context');self.assertEqual(out['context_quality']['core_states']['unknown'],0)
        self.assertEqual(out['triangles_unknown'],audit['primary_report']['triangles_unknown']);self.assertEqual(out['triangles_unknown'],8)

    def test_long_triangle_same_members_has_no_verified_gain(self):
        d,_=setup(fixture(long=True));out,audit=run(d)
        self.assertEqual(out['context_quality']['reason'],'within_surplus_budget')
        self.assertEqual(out['context_quality']['core_triangle_indices'],[0]);self.assertEqual(audit['candidate_records'],[])

    def test_boundary_contact_and_collapsed_core_facts_are_retained(self):
        for collapsed in (False,True):
            p=fixture(collapsed=collapsed)
            if not collapsed:
                p['original'][:3]=[[.1,.1,.1],[.2,.1,.1],[.1,.2,.1]];p['current'][:3]=copy.deepcopy(p['original'][:3])
            d,_=setup(p);out,audit=run(d)
            self.assertEqual(out['context_quality']['core_triangle_indices'],[0]);self.assertEqual(out['context_quality']['contact_extent'],'not_checked')
            self.assertEqual(audit['core_rows'][0]['state'],'collapsed' if collapsed else 'measured')

    def test_final_metadata_or_strict_requested_bytes_can_prevent_selection(self):
        d,_=setup(fixture(),saved=65536);out,audit=run(d)
        self.assertEqual(out['context_quality']['reason'],'no_verified_gain');self.assertEqual(out['context_quality']['decision'],'retained_primary')
        record=audit['candidate_records'][0];self.assertEqual(record['reason'],'no_publication_byte_gain')
        self.assertEqual(record['publication_bytes'],len(c.publication_bytes(record['report'])))

    def test_operator_first_satisfying_rule_is_complete_not_global_optimum(self):
        d,_=setup(fixture(),candidates=(.2,.1));out,audit=run(d)
        self.assertEqual(audit['selected_candidate_index'],0);self.assertEqual(out['context_quality']['candidates_evaluated'],1)
        self.assertTrue(out['context_quality']['search_complete']);self.assertEqual(len(audit['candidate_records']),1)

    def test_optional_expiry_before_core_does_not_fabricate_empty_core(self):
        d,_=setup(fixture(),budget=1);clock=[100];real=g.select_prepared
        def delayed(cache,query,*,deadline_ns):
            if query['region']['bounds'][1]==[.1]*3:clock[0]=2_000_100;raise ValueError('rig_pose_original_deadline')
            return real(cache,query,deadline_ns=deadline_ns)
        with patch.object(c.r.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(g,'select_prepared',side_effect=delayed):out,audit=run(d)
        q=out['context_quality'];self.assertEqual(q['reason'],'planning_budget');self.assertFalse(q['core_complete'])
        self.assertIsNone(q['core_triangle_indices']);self.assertFalse(q['search_complete'])

    def test_original_expiry_never_returns_a_primary_success(self):
        d,_=setup(fixture(),budget=1);clock=[100];real=g.select_prepared
        def delayed(cache,query,*,deadline_ns):
            if query['region']['bounds'][1]==[.1]*3:clock[0]=d['deadline_ns']+1;raise ValueError('rig_pose_original_deadline')
            return real(cache,query,deadline_ns=deadline_ns)
        with patch.object(c.r.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(g,'select_prepared',side_effect=delayed):
            with self.assertRaisesRegex(ValueError,'original_deadline'):run(d)

    def test_late_selected_publication_expiry_restores_primary_surplus(self):
        d,_=setup(fixture(),budget=1);clock=[100];selected=[0];real=c._payload
        def late(report,deadline_ns):
            blob=real(report,deadline_ns)
            if report.get('context_quality',{}).get('decision')=='selected_context':
                selected[0]+=1
                if selected[0]==2:clock[0]=2_000_100
            return blob
        with patch.object(c.r.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(c,'_payload',side_effect=late):out,audit=run(d)
        q=out['context_quality'];self.assertEqual(q['reason'],'planning_budget');self.assertEqual(q['decision'],'retained_primary')
        self.assertEqual(q['selected_surplus_members'],q['primary_surplus_members']);self.assertEqual(q['selected_surplus_members'],8)
        self.assertEqual(out['region_query']['triangles_total'],9);self.assertIsNone(audit['selected_candidate_index'])

    def test_only_named_optional_arithmetic_error_can_retain_primary(self):
        for error,retained in [('rig_pose_deformation_region_arithmetic_budget',True),('rig_pose_deformation_region_proof_shape',False)]:
            d,_=setup(fixture());real=g.select_prepared
            def failure(cache,query,*,deadline_ns):
                if query['region']['bounds'][1]==[.1]*3:raise ValueError(error)
                return real(cache,query,deadline_ns=deadline_ns)
            with patch.object(g,'select_prepared',side_effect=failure):
                if retained:
                    out,_=run(d);self.assertEqual(out['context_quality']['reason'],'arithmetic_budget');self.assertFalse(out['context_quality']['core_complete'])
                else:
                    with self.assertRaisesRegex(ValueError,'proof_shape'):run(d)

    def test_complete_core_digest_is_not_the_four_row_detail_projection(self):
        d,_=setup(fixture(),core=8.,primary=8.,candidates=());out,audit=run(d)
        self.assertEqual(len(audit['core_rows']),9);self.assertEqual(len(out['region_query']['triangles']),4)
        self.assertEqual(out['context_quality']['core_rows_sha256'],c.r.digest(audit['core_rows']))

    def test_unicode_publication_is_ascii_and_matches_the_byte_gate(self):
        d,_=setup(fixture(unicode=True));out,audit=run(d);blob=c.publication_bytes(out)
        self.assertTrue(blob.endswith(b'\n'));self.assertEqual(blob.count(b'\n'),1);self.assertIn(b'\\u7f51',blob)
        self.assertTrue(all(v<128 for v in blob));self.assertNotEqual(len(blob),len(c.r.encoded(out))+1)
        self.assertEqual(len(blob),audit['published_publication_bytes'])

    def test_rows_and_exact_geometry_caches_are_immutable_and_bound(self):
        d,_=setup(fixture());rows=d['rows'];cache=g.prepare_geometry(d['proof'],deadline_ns=d['deadline_ns'])
        with self.assertRaises(FrozenInstanceError):rows.payload=b'[]'
        with self.assertRaises(FrozenInstanceError):cache.points=()
        with self.assertRaisesRegex(ValueError,'deformation_rows_binding'):s._verified_rows(d['proof'],json.loads(rows.payload),deadline_ns=d['deadline_ns'])
        altered=copy.deepcopy(d['proof']);altered['current'][0][0]+=.001
        with self.assertRaisesRegex(ValueError,'deformation_rows_binding'):s._report_from_rows(altered,rows,deadline_ns=d['deadline_ns'])
        values=json.loads(rows.payload);values[-1]['triangle']=0
        with self.assertRaisesRegex(ValueError,'deformation_rows_binding'):s._verified_rows(d['proof'],replace(rows,payload=c.r.encoded(values)),deadline_ns=d['deadline_ns'])


if __name__=='__main__':unittest.main()
