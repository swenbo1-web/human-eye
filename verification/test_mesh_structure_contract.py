"""Adversarial acceptance checks; no Blender, provider or production state."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from verification.mesh_structure_contract import (CATEGORIES, LIMITS, NOT_CHECKED,
    SCHEMA, score, validate_report, validate_task)
from verification.mesh_structure_fixtures import fixtures


def report():
    counts = dict(vertices=8, edges=8, polygons=2, corners=8)
    expected = next(c for c in fixtures() if c['id']=='two_open_components')['expected']
    return dict(schema=SCHEMA,
        task=dict(schema='spatial-readonly-task-v1', kind='mesh_structure',
                  task_id='owner-task-1', object_ids=['part'], read_only=True,
                  categories=['boundary_edges']),
        source=dict(object_id='part',object_instance='instance-1',document_epoch='doc-1',
                    capture_id='capture-1',raw_sha256='a'*64,source_kind='raw_mesh',
                    coordinate_frame='local',length_unit='m',counts=counts,
                    capture_scope='target_mesh_only',geometry_complete=True),
        checks={'boundary_edges':dict(state='complete',scanned=counts.copy(),found=2,total=2,
                    regions=expected['boundary_edges'],omitted=0,reason=None,omission_reason=None)},
        not_checked=[c for c in CATEGORIES if c!='boundary_edges']+list(NOT_CHECKED),
        execution_authority=False,natural_visibility='not_checked')


class MeshStructureContractTests(unittest.TestCase):
    def test_single_object_task_has_no_fake_reference(self):
        value=report()['task']; self.assertEqual(validate_task(value), value)
        for ids in ([], ['part','base'], ['part','part']):
            bad=copy.deepcopy(value);bad['object_ids']=ids
            with self.subTest(ids=ids), self.assertRaises(ValueError):validate_task(bad)

    def test_clearance_remains_pair_and_readonly(self):
        value=report()['task'];value.update(kind='clearance',object_ids=['part','base'],categories=['clearance'])
        self.assertEqual(validate_task(value),value)
        value['object_ids']=['part','part']
        with self.assertRaises(ValueError):validate_task(value)

    def test_task_is_not_edit_authorization(self):
        for key, val in [('read_only',False),('grant','invented'),('budget',999),('kind','repair')]:
            value=report()['task'];value[key]=val
            with self.subTest(key=key), self.assertRaises(ValueError):validate_task(value)

    def test_source_exact_binding_includes_incarnation_and_scope(self):
        value=report(); source=copy.deepcopy(value['source'])
        validate_report(value,expected_source=source)
        for key,new in [('object_instance','rebuilt'),('document_epoch','other'),
                        ('capture_id','old'),('raw_sha256','b'*64)]:
            bad=copy.deepcopy(value);bad['source'][key]=new
            with self.subTest(key=key),self.assertRaises(ValueError):validate_report(bad,expected_source=source)

    def test_target_capture_cannot_claim_natural_scene_visibility(self):
        value=report();value['natural_visibility']='visible'
        with self.assertRaises(ValueError):validate_report(value)

    def test_complete_does_not_mean_no_defects(self):
        value=report();valid=validate_report(value)
        self.assertEqual(valid['checks']['boundary_edges']['found'],2)
        self.assertIn('surface_damage',valid['not_checked'])

    def test_complete_scan_cannot_hide_unscanned_geometry(self):
        value=report();value['checks']['boundary_edges']['scanned']['polygons']=1
        with self.assertRaises(ValueError):validate_report(value)

    def test_output_truncation_is_valid_but_missed_localization_stays_in_denominator(self):
        value=report();check=value['checks']['boundary_edges'];expected=copy.deepcopy(check['regions'])
        check['regions'].pop();check.update(omitted=1,omission_reason='output_budget')
        validate_report(value)
        result=score({'boundary_edges':expected},value['checks'])
        self.assertEqual((result['tp'],result['fn'],result['recall']),(1,1,.5))

    def test_scan_interruption_cannot_report_total(self):
        value=report();check=value['checks']['boundary_edges'];check.update(state='partial',reason='work_budget')
        with self.assertRaises(ValueError):validate_report(value)
        check.update(total=None);validate_report(value)

    def test_unknown_all_is_zero_answer_coverage_and_zero_recall(self):
        value=report();check=value['checks']['boundary_edges'];truth=copy.deepcopy(check['regions'])
        check.update(state='unknown',scanned={k:0 for k in check['scanned']},found=0,total=None,
                     regions=[],omitted=0,reason='source_unavailable')
        validate_report(value);result=score({'boundary_edges':truth},value['checks'])
        self.assertEqual((result['tp'],result['fn'],result['recall'],result['answer_coverage']),(0,2,0.,0.))

    def test_unsupported_in_domain_also_counts_as_missed(self):
        expected={'nonmanifold_vertices':[[0]]}
        for state in ('unknown','unsupported','not_checked'):
            result=score(expected,{'nonmanifold_vertices':{'state':state,'regions':[]}})
            self.assertEqual(result['fn'],1);self.assertEqual(result['abstained_categories'],1)

    def test_wrong_cluster_merge_does_not_get_credit(self):
        expected={'isolated_vertices':[[1],[2]]}
        value={'isolated_vertices':{'state':'complete','regions':[[1,2]]}}
        result=score(expected,value)
        self.assertEqual((result['tp'],result['fp'],result['fn']),(0,1,2))

    def test_wrong_cluster_split_does_not_get_credit(self):
        result=score({'nonmanifold_vertices':[[0,1]]},
                     {'nonmanifold_vertices':{'state':'complete','regions':[[0],[1]]}})
        self.assertEqual((result['tp'],result['fp'],result['fn']),(0,2,1))

    def test_edge_orientation_order_do_not_change_exact_matching(self):
        result=score({'boundary_edges':[[[0,1],[1,2]]]},
                     {'boundary_edges':{'state':'complete','regions':[[[2,1],[1,0]]]}})
        self.assertEqual((result['tp'],result['fp'],result['fn']),(1,0,0))

    def test_duplicate_report_cannot_inflate_score(self):
        result=score({'isolated_vertices':[[1]]},
                    {'isolated_vertices':{'state':'complete','regions':[[1],[1]]}})
        self.assertEqual((result['tp'],result['fp'],result['fn']),(1,1,0))

    def test_bad_types_and_nonfinite_rejected(self):
        for bad in (True, -1, 1.0, float('inf'),float('nan'),10**200, '8'):
            value=report();value['source']['counts']['vertices']=bad
            with self.subTest(bad=repr(bad)),self.assertRaises(ValueError):validate_report(value)

    def test_source_and_report_bounds_are_separate(self):
        value=report();value['source']['counts']['vertices']=LIMITS['vertices']+1
        with self.assertRaises(ValueError):validate_report(value)
        value=report();value['checks']['boundary_edges']['regions'][0]=[[0,1]]*65
        with self.assertRaises(ValueError):validate_report(value)

    def test_regions_duplicate_invalid_indices_and_omission_lies_rejected(self):
        for change in ('duplicate','index','found','omitted','reason','total'):
            value=report();check=value['checks']['boundary_edges']
            if change=='duplicate':check['regions'][1]=copy.deepcopy(check['regions'][0])
            elif change=='index':check['regions'][0][0]=[0,8]
            elif change=='reason':check['reason']='normal'
            else:check[change]=999
            with self.subTest(change=change),self.assertRaises(ValueError):validate_report(value)

    def test_future_domains_cannot_silently_disappear(self):
        value=report();value['not_checked'].remove('self_intersection')
        with self.assertRaises(ValueError):validate_report(value)

    def test_unrequested_structure_categories_are_also_explicitly_unchecked(self):
        value=report();value['not_checked'].remove('nonmanifold_vertices')
        with self.assertRaises(ValueError):validate_report(value)

    def test_unrequested_categories_are_rejected(self):
        value=report();value['checks']['surface_damage']=copy.deepcopy(value['checks']['boundary_edges'])
        with self.assertRaises(ValueError):validate_report(value)

    def test_copy_does_not_mutate_input_or_return_shared_lists(self):
        value=report();old=copy.deepcopy(value);valid=validate_report(value)
        valid['checks']['boundary_edges']['regions'].clear()
        self.assertEqual(value,old)

    def test_fixtures_independent_and_cover_negative_and_complex_cases(self):
        cases=fixtures();ids={c['id'] for c in cases}
        self.assertEqual(len(cases),len(ids));self.assertEqual(len(cases),14)
        self.assertTrue({'legal_open_quad','bow_tie_vertex','loose_edge','concave_ngon',
                         'unwelded_duplicate_position','empty_mesh'} <= ids)
        cases[0]['vertices'].clear();self.assertEqual(len(fixtures()[0]['vertices']),4)

    def test_numeric_registration_matches_oracle_and_limits(self):
        root=Path(__file__).resolve().parents[1]
        registered=json.loads((root/'verification/fixtures/mesh_structure_acceptance_v1.json').read_text(encoding='utf8'))
        self.assertEqual(registered['limits'],LIMITS)
        self.assertEqual(registered['oracle_sha256'],hashlib.sha256(
            (root/'verification/mesh_structure_fixtures.py').read_bytes()).hexdigest())
        self.assertEqual(len(registered['numerical_gates']),17)
        for gate in registered['numerical_gates']:
            baseline=gate['source_baseline_p95_ms']
            self.assertAlmostEqual(gate['candidate_pipeline_p95_limit_ms'],baseline+max(20.,.5*baseline),places=5)
        self.assertFalse(registered['diagnostic_runtime_implemented'])

    def test_old_query_does_not_advertise_unimplemented_diagnostic(self):
        from human_eye_plugin.query_policy import validate_query
        with self.assertRaises(ValueError):validate_query({'mode':'mesh_structure'})
        from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA
        self.assertEqual({t['name'] for t in LIVE_MCP_TOOLS_SCHEMA},
                         {'human_eye_scene_observe','human_eye_transform',
                          'human_eye_connection_status','human_eye_clearance_segment'})

    def test_utf8_report_bytes_are_checked_separately_from_region_counts(self):
        value=report();source=value['source']['counts']
        source.update(vertices=16384,edges=32768,polygons=16384,corners=65536)
        check=value['checks']['boundary_edges'];check['scanned']=source.copy()
        check.update(found=128,total=128,regions=[[[i*64+j,i*64+j+1] for j in range(64)] for i in range(128)])
        with self.assertRaisesRegex(ValueError,'report_byte_budget'):validate_report(value)

    def test_supported_negative_oracle_does_not_hide_abstention(self):
        result=score({'nonmanifold_edges':[]},{'nonmanifold_edges':{'state':'unsupported','regions':[]}})
        self.assertEqual(result['fn'],0);self.assertIsNone(result['recall'])
        self.assertEqual(result['answer_coverage'],0.)

    def test_omitted_category_cannot_be_marked_complete(self):
        value=report();value['checks'].clear()
        with self.assertRaisesRegex(ValueError,'category_coverage'):validate_report(value)


if __name__=='__main__':unittest.main()
