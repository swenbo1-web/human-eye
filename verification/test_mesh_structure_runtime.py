"""Independent fixed oracles, malformed sources and cooperative-stop cases."""
import copy
import unittest
from human_eye_plugin import mesh_structure as m
from verification.mesh_structure_contract import validate_report,score
from verification.mesh_structure_fixtures import fixtures,grid


def raw_case(case):
    edges={tuple(sorted(e)):list(e) for e in case['edges']}
    for polygon in case['polygons']:
        for i,v in enumerate(polygon):
            edge=[polygon[i-1],v];edges.setdefault(tuple(sorted(edge)),edge)
    return dict(vertices=copy.deepcopy(case['vertices']),edges=list(edges.values()),
                polygons=copy.deepcopy(case['polygons']),matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],unit_scale=1.)


def identity():return dict(object_id='target',object_instance='object:mesh',document_epoch='doc',capture_id='read1')


class StructureRuntimeTests(unittest.TestCase):
    def test_frozen_oracles_for_implemented_categories(self):
        scored=0
        for case in fixtures():
            expected={c:v for c,v in case['expected'].items() if c in m.SUPPORTED}
            if not expected:continue
            with self.subTest(case=case['id']):
                result=m.analyze_raw(raw_case(case),identity(),task_id='t',categories=list(expected))
                validate_report(result['report']);metrics=score(expected,result['report']['checks'])
                self.assertEqual((metrics['fp'],metrics['fn'],metrics['answer_coverage']),(0,0,1.))
                self.assertFalse(result['execution_authority']);self.assertEqual(result['images'],[])
                self.assertIn('surface_damage',result['report']['not_checked']);scored+=1
        self.assertEqual(scored,14)

    def test_empty_and_vertices_only_are_readable_not_all_domains_normal(self):
        for case in fixtures()[-2:]:
            result=m.analyze_raw(raw_case(case),identity(),task_id='t')
            validate_report(result['report'])
            self.assertEqual(result['report']['checks']['isolated_vertices']['found'],len(case['vertices']))
            self.assertIn('nonmanifold_vertices',result['report']['not_checked'])

    def test_source_and_output_do_not_share_mutable_input_arrays(self):
        raw=raw_case(fixtures()[1]);before=copy.deepcopy(raw)
        result=m.analyze_raw(raw,identity(),task_id='t');self.assertEqual(raw,before)
        result['report']['checks']['boundary_edges']['regions'][0][0][0]=999
        self.assertEqual(raw,before)

    def test_digest_covers_connectivity_coordinates_units_matrix_and_incarnation(self):
        raw=raw_case(fixtures()[1]);base=m.prepare_raw(raw,identity())['source']['raw_sha256']
        for field in ('coordinate','scale','matrix','edge_order','polygon_order','instance','document'):
            value=copy.deepcopy(raw);ids=identity()
            if field=='coordinate':value['vertices'][0][0]=.001
            elif field=='scale':value['unit_scale']=.001
            elif field=='matrix':value['matrix_world'][0][3]=.001
            elif field=='edge_order':value['edges'].reverse()
            elif field=='polygon_order':value['polygons'][0].reverse()
            elif field=='instance':ids['object_instance']='recreated'
            elif field=='document':ids['document_epoch']='new-doc'
            with self.subTest(field=field):self.assertNotEqual(m.prepare_raw(value,ids)['source']['raw_sha256'],base)
        ids=identity();ids['capture_id']='read2'
        self.assertEqual(m.prepare_raw(raw,ids)['source']['raw_sha256'],base)

    def test_patch_indices_resolve_to_original_edges_not_triangulation(self):
        raw=raw_case(fixtures()[1]);result=m.analyze_raw(raw,identity(),task_id='t')
        patch=result['patches'][0]
        edges=[raw['edges'][i] for i in patch['source_indices']]
        self.assertEqual(edges,result['report']['checks']['boundary_edges']['regions'][0])
        self.assertNotIn([0,2],edges);self.assertEqual(patch['raw_sha256'],result['report']['source']['raw_sha256'])

    def test_duplicate_positions_are_not_welded(self):
        case=next(c for c in fixtures() if c['id']=='unwelded_duplicate_position')
        result=m.analyze_raw(raw_case(case),identity(),task_id='t')
        self.assertEqual(result['report']['checks']['boundary_edges']['found'],2)

    def test_oversized_component_is_omitted_whole_not_relabelled_complete_localization(self):
        result=m.analyze_raw(raw_case(grid(32)),identity(),task_id='t',categories=['boundary_edges'])
        check=result['report']['checks']['boundary_edges'];validate_report(result['report'])
        self.assertEqual((check['state'],check['found'],check['total'],check['omitted']),('complete',1,1,1))
        self.assertEqual(check['regions'],[]);self.assertFalse(result['omitted_reference']['retrieval_endpoint_available'])

    def test_region_limit_preserves_omitted_count(self):
        raw=raw_case(dict(vertices=[[i,0,0] for i in range(200)],edges=[],polygons=[]))
        result=m.analyze_raw(raw,identity(),task_id='t',categories=['isolated_vertices'])
        check=result['report']['checks']['isolated_vertices'];validate_report(result['report'])
        self.assertEqual(check['found'],200);self.assertGreater(check['omitted'],0)
        self.assertEqual(check['found'],len(check['regions'])+check['omitted'])
        self.assertLessEqual(len(m._bytes(result)),m.LIMITS['report_bytes'])

    def test_scan_exhaustion_has_no_total_and_records_real_prefix(self):
        prepared=m.prepare_raw(raw_case(grid(8)),identity())
        result=m.analyze_prepared(prepared,task_id='t',budget=m.WorkBudget(max_work=5))
        self.assertEqual(result['status'],'partial');validate_report(result['report'])
        self.assertEqual(result['coverage']['polygons_prefix'],64)
        self.assertEqual(result['coverage']['polygon_corners'],256)
        self.assertEqual(result['coverage']['component_categories_completed'],[])
        for check in result['report']['checks'].values():self.assertIsNone(check['total'])

    def test_validation_exhaustion_never_returns_prepared_source(self):
        with self.assertRaises(m.StructureStopped):m.prepare_raw(raw_case(fixtures()[1]),identity(),budget=m.WorkBudget(max_work=0))

    def test_deadline_not_renewed_or_accepted_when_already_expired(self):
        with self.assertRaises(m.StructureStopped):m.WorkBudget(deadline_ns=100,clock=lambda:100)
        with self.assertRaises(m.StructureRefused):m.WorkBudget(deadline_ns=30_000_000_101,clock=lambda:100)
        clock=[0];budget=m.WorkBudget(deadline_ns=10,clock=lambda:clock[0])
        clock[0]=10
        with self.assertRaises(m.StructureStopped):budget.consume()

    def test_malformed_indices_edges_and_polygons_rejected(self):
        raw=raw_case(fixtures()[1])
        for variant in ('bool','negative','range','self_edge','duplicate_edge','missing_edge','short_poly','repeat_vertex'):
            value=copy.deepcopy(raw)
            if variant=='bool':value['edges'][0][0]=True
            elif variant=='negative':value['polygons'][0][0]=-1
            elif variant=='range':value['polygons'][0][0]=4
            elif variant=='self_edge':value['edges'][0]=[0,0]
            elif variant=='duplicate_edge':value['edges'].append(value['edges'][0])
            elif variant=='missing_edge':value['edges'].pop()
            elif variant=='short_poly':value['polygons'][0]=[0,1]
            else:value['polygons'][0]=[0,1,0]
            with self.subTest(variant=variant),self.assertRaises(m.StructureRefused):m.prepare_raw(value,identity())

    def test_nonfinite_huge_and_boolean_coordinates_rejected(self):
        for number in (float('nan'),float('inf'),True,10**500):
            value=raw_case(fixtures()[1]);value['vertices'][0][0]=number
            with self.subTest(number=repr(number)),self.assertRaises(m.StructureRefused):m.prepare_raw(value,identity())

    def test_scale_and_affine_are_checked(self):
        for scale in (0,-1,True,float('nan')):
            raw=raw_case(fixtures()[1]);raw['unit_scale']=scale
            with self.assertRaises(m.StructureRefused):m.prepare_raw(raw,identity())
        raw=raw_case(fixtures()[1]);raw['matrix_world'][3][0]=1
        with self.assertRaises(m.StructureRefused):m.prepare_raw(raw,identity())

    def test_count_budget_precedes_large_allocation(self):
        raw=raw_case(fixtures()[1]);raw['vertices']=[[0,0,0]]*(m.LIMITS['vertices']+1)
        with self.assertRaisesRegex(m.StructureRefused,'vertices_budget'):m.prepare_raw(raw,identity())

    def test_unimplemented_detector_is_not_reported_normal(self):
        with self.assertRaisesRegex(m.StructureRefused,'unsupported_diagnostic_categories'):
            m.analyze_raw(raw_case(fixtures()[1]),identity(),task_id='t',categories=['self_intersection'])


if __name__=='__main__':unittest.main()
