"""Public coverage, protocol admission and hard budget boundaries."""
import copy,math,time,unittest
from unittest.mock import patch
from human_eye_plugin import mesh_structure as m
from human_eye_plugin.mesh_structure_service import validate_result
from human_eye_plugin.structure_task_service import _raw
from verification.test_mesh_structure_runtime import identity,raw_case
from verification.engineering_baseline_cases import cases
from verification.engineering_task_contract import he_regions,choose_region

CATS=['boundary_edges','loose_edges','isolated_vertices']


def dense():
    obj=next(c for c in cases() if c['id']=='dense1808')['objects'][0]
    return raw_case(dict(vertices=obj['world_vertices'],edges=obj.get('edges',[]),polygons=obj['faces']))


def chains(n=1,length=65):
    vertices=[];edges=[]
    for group in range(n):
        start=len(vertices)
        vertices.extend([[float(i),float(group),0.] for i in range(length+1)])
        edges.extend([[start+i,start+i+1] for i in range(length)])
    return dict(vertices=vertices,edges=edges,polygons=[],unit_scale=1.,matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])


def observe(raw=None,**kwargs):
    return m.analyze_raw(dense() if raw is None else raw,identity(),task_id='task',categories=CATS,
        region_summaries=True,**kwargs)


def validate(value,summary=True):
    return validate_result(value,object_id='target',request_id='task',categories=CATS,
        deadline_ns=value['accounting']['deadline_ns'],region_summaries=summary)


def public(value):
    return dict(diagnostic=value,patch_refs=[dict(category=p['category'],cluster_ordinal=p['cluster_ordinal'],
        patch_ref=str(i).zfill(32)) for i,p in enumerate(value['patches'])])


class RegionSummaryTests(unittest.TestCase):
    def test_large_component_has_position_but_no_members_or_reference(self):
        value=validate(observe());cat=value['region_summary'];row=cat['entries'][0]
        self.assertEqual((row['category'],row['member_count']),('boundary_edges',120))
        self.assertEqual(row['membership_delivery'],'omitted');self.assertNotIn('source_indices',row)
        self.assertNotIn('patch_ref',row)
        coverage=cat['coverage']['boundary_edges']
        self.assertTrue(coverage['positions_complete']);self.assertFalse(coverage['member_lists_complete'])
        self.assertEqual(value['report']['checks']['boundary_edges']['omitted'],1)

    def test_independent_all_source_bounds_and_digest(self):
        raw=chains();raw['unit_scale']=.001;raw['matrix_world']=[[0,-1,0,2],[1,0,0,3],[0,0,2,4],[0,0,0,1]]
        row=validate(observe(raw))['region_summary']['entries'][0]
        self.assertEqual(row['membership_sha256'],m._digest(list(range(65))))
        self.assertEqual(row['position']['local_bounds_m'],[[0.,0.,0.],[.065,0.,0.]])
        self.assertEqual(row['position']['world_bounds_m'],[[.002,.003,.004],[.002,.068,.004]])

    def test_public_anchor_selects_full_patch_without_oracle(self):
        regions,coverage=he_regions(public(observe()))
        result=choose_region(regions,[0.,0.,0.],**coverage)
        self.assertEqual(result['status'],'selected');self.assertFalse(result['region']['selection_only'])
        self.assertIsNotNone(result['region']['patch_ref'])

    def test_anchor_on_omitted_region_selects_summary_without_image_permission(self):
        regions,coverage=he_regions(public(observe()))
        row=next(r for r in regions if r['selection_only'])
        anchor=[sum(v)/2 for v in zip(*row['bounds'])]
        result=choose_region(regions,anchor,**coverage)
        self.assertEqual(result['region'],row);self.assertIsNone(row['patch_ref'])

    def test_v2_requires_no_new_field_and_v3_requires_explicit_consumer(self):
        old=m.analyze_raw(dense(),identity(),task_id='task',categories=CATS)
        validate(old,False);self.assertNotIn('region_summary',old);self.assertEqual(old['protocol'],m.PROTOCOL)
        for value,mode in ((observe(),False),(old,True)):
            with self.assertRaises(m.StructureRefused):validate(value,mode)

    def test_legacy_patch_values_are_unchanged(self):
        raw=dense();old=m.analyze_raw(raw,identity(),task_id='task',categories=CATS);new=observe(raw)
        self.assertEqual(old['patches'],new['patches']);self.assertEqual(old['report'],new['report'])

    def test_source_binding_includes_capture_but_summary_identity_is_stable(self):
        a=observe();ids=identity();ids['capture_id']='read2'
        b=m.analyze_raw(dense(),ids,task_id='task',categories=CATS,region_summaries=True)
        self.assertNotEqual(a['region_summary']['source_binding_sha256'],b['region_summary']['source_binding_sha256'])
        self.assertEqual(a['region_summary']['entries'],b['region_summary']['entries'])

    def test_more_than_128_components_remains_partial(self):
        raw=chains(129,1);value=validate(observe(raw));cat=value['region_summary']
        self.assertLessEqual(len(value['patches'])+len(cat['entries']),128)
        self.assertFalse(cat['coverage']['loose_edges']['positions_complete'])
        self.assertGreater(cat['coverage']['loose_edges']['summaries_omitted'],0)
        self.assertEqual(value['status'],'partial')

    def test_report_cap_and_missing_summaries_cannot_be_complete(self):
        value=validate(observe(chains(120)));cat=value['region_summary'];coverage=cat['coverage']['loose_edges']
        self.assertLessEqual(len(m._bytes(value)),65536);self.assertGreater(len(m._bytes(value)),60000)
        self.assertGreater(coverage['summaries_omitted'],0);self.assertFalse(coverage['positions_complete'])
        self.assertLess(len(cat['entries']),128);self.assertEqual(value['status'],'partial')

    def test_extra_work_is_charged_and_cannot_be_refunded(self):
        raw=chains();old=m.analyze_raw(raw,identity(),task_id='task',categories=CATS)
        new=validate(observe(raw));self.assertEqual(new['accounting']['work_units']-old['accounting']['work_units'],262)
        for extra in (0,66,67,261):
            with self.subTest(extra=extra):
                budget=m.WorkBudget(max_work=old['accounting']['work_units']+extra)
                limited=validate(observe(raw,budget=budget))
                self.assertLessEqual(budget.used,budget.maximum);self.assertGreaterEqual(budget.used,old['accounting']['work_units'])
                self.assertFalse(limited['region_summary']['coverage']['loose_edges']['positions_complete'])

    def test_incomplete_scan_never_reports_complete_empty_catalog(self):
        # Source capture/validation must finish before an analysis-only stop.
        budget=m.WorkBudget();prepared=m.prepare_raw(chains(),identity(),budget=budget);budget.maximum=budget.used
        value=m.analyze_prepared(prepared,task_id='task',categories=CATS,budget=budget,region_summaries=True)
        validate(value)
        self.assertFalse(value['region_summary']['coverage']['loose_edges']['scan_complete'])
        self.assertFalse(value['region_summary']['coverage']['loose_edges']['positions_complete'])

    def test_deadline_during_summary_remains_partial(self):
        budget=m.WorkBudget(deadline_ns=1000,clock=lambda:0)
        prepared=m.prepare_raw(chains(),identity(),budget=budget)
        budget.clock=lambda:1001 if budget.stage=='summary_membership_digest' else 0
        value=m.analyze_prepared(prepared,task_id='task',categories=CATS,budget=budget,region_summaries=True)
        validate(value)
        self.assertEqual(value['status'],'partial');self.assertEqual(value['accounting']['deadline_ns'],1000)
        self.assertFalse(value['region_summary']['coverage']['loose_edges']['positions_complete'])

    def test_unknown_nonfinite_position_remains_partial(self):
        raw=chains();raw['matrix_world'][0][0]=1e308
        value=validate(observe(raw));row=value['region_summary']['entries'][0]
        self.assertEqual(row['position'],dict(status='unknown',reason='position_nonfinite'))
        self.assertFalse(value['region_summary']['coverage']['loose_edges']['positions_complete'])

    def test_consumer_rejects_tampered_source_and_identity(self):
        original=observe()
        mutations=[lambda v:v['region_summary'].__setitem__('source_binding_sha256','0'*64),
            lambda v:v['report']['source'].__setitem__('document_epoch','other'),
            lambda v:v['region_summary']['entries'][0].__setitem__('summary_id','0'*64),
            lambda v:v['region_summary']['entries'][0].__setitem__('membership_sha256','f'*64),
            lambda v:v['region_summary']['entries'][0].__setitem__('membership_delivery','complete'),
            lambda v:v['region_summary']['coverage']['boundary_edges'].__setitem__('member_lists_complete',True),
            lambda v:v['region_summary']['coverage']['boundary_edges'].__setitem__('positions_known',True),
            lambda v:v['region_summary']['entries'][0].__setitem__('patch_ref','a'*32)]
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                value=copy.deepcopy(original);mutate(value)
                with self.assertRaises(m.StructureRefused):validate(value)

    def test_duplicate_ordinal_invalid_position_and_false_coverage_refused(self):
        original=observe()
        mutations=[lambda v:v['region_summary']['entries'].append(copy.deepcopy(v['region_summary']['entries'][0])),
            lambda v:v['region_summary']['entries'][0]['position']['world_bounds_m'][0].__setitem__(0,math.inf),
            lambda v:v['region_summary']['coverage']['boundary_edges'].__setitem__('summaries_omitted',1)]
        for mutate in mutations:
            value=copy.deepcopy(original);mutate(value)
            with self.assertRaises(m.StructureRefused):validate(value)

    def test_old_host_or_wrong_capability_cannot_silently_fallback(self):
        from verification.test_mesh_structure_service import TypedRawHost
        host=TypedRawHost()
        with self.assertRaisesRegex(ValueError,'typed_raw_host_unavailable'):_raw(host,'target',CATS,time.perf_counter_ns()+1_000_000_000,'summary_v1')
        with self.assertRaisesRegex(ValueError,'unsupported_structure_region_mode'):_raw(host,'target',CATS,time.perf_counter_ns()+1_000_000_000,'auto')
        self.assertEqual(host.raw_calls,0)

    def test_new_capability_is_explicit_and_old_protocol_is_refused(self):
        from verification.test_mesh_structure_service import TypedRawHost
        host=TypedRawHost();host.mesh_region_summary_capabilities=host.mesh_structure_capabilities
        def read(request,object_id,categories,deadline):
            return m.analyze_raw(dense(),identity(),task_id=request,categories=categories,
                budget=m.WorkBudget(deadline_ns=deadline),region_summaries=True)
        host.observe_mesh_structure_summary=read
        deadline=time.perf_counter_ns()+1_000_000_000
        with patch('human_eye_plugin.structure_task_service.counter_descriptor',return_value={'test_clock':True}):
            with self.assertRaisesRegex(ValueError,'raw_capability_mismatch'):_raw(host,'target',CATS,deadline,'summary_v1')
            def capabilities():
                caps=host.mesh_structure_capabilities();caps['protocol']=m.REGION_SUMMARY_PROTOCOL;return caps
            host.mesh_region_summary_capabilities=capabilities
            result=_raw(host,'target',CATS,deadline,'summary_v1')
        self.assertEqual(result['protocol'],m.REGION_SUMMARY_PROTOCOL);self.assertEqual(host.raw_calls,0)

    def test_same_position_ambiguous_is_still_unknown(self):
        regions,coverage=he_regions(public(observe()));regions[1]['bounds']=copy.deepcopy(regions[0]['bounds'])
        self.assertEqual(choose_region(regions,[0.,0.,0.],**coverage)['status'],'unknown')


if __name__=='__main__':unittest.main()
