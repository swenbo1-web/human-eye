"""Synthetic scoring counterexamples. No consumer, product or Blender launch."""
import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_surface_scan_score',HERE/'score_answer.py')
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
truth = json.loads((HERE/'TRUTH.json').read_bytes())
snapshot = json.loads((HERE/'ACTUAL_SNAPSHOT.json').read_bytes())


def reference_rows():
    rows = []
    for row in truth['pairs']:
        if not row['matches_threshold']:
            continue
        value = row['exact_squared_distance_m2']
        with localcontext() as context:
            context.prec = 70
            millimetres = (Decimal(value['numerator'])/Decimal(value['denominator'])).sqrt()*1000
            shown = millimetres.quantize(Decimal('.001'))
        rows.append(dict(objects=[row['object_a'],row['object_b']],distance_mm=str(shown)))
    return rows


def answer(rows=None, status='complete'):
    return json.dumps(dict(status=status,matches=reference_rows() if rows is None else rows))


class QualityTests(unittest.TestCase):
    def test_reference_three_decimal_set_is_complete_correct(self):
        self.assertEqual(score.score_answer(answer(),truth,snapshot)['status'],'complete_correct')

    def test_exact_fraction_tolerance_interval_and_neighbour(self):
        exact = dict(numerator='1',denominator='1000000')
        limit = score.TOLERANCE_MM
        self.assertTrue(score.distance_valid_mm(Fraction(1)+limit,exact))
        self.assertFalse(score.distance_valid_mm(Fraction(1)+limit+Fraction(1,10**12),exact))

    def test_missing_pair_claimed_complete_is_incorrect(self):
        result = score.score_answer(answer(reference_rows()[:-1]),truth,snapshot)
        self.assertEqual(result['status'],'incorrect')
        self.assertEqual(len(result['missing_pairs']),1)

    def test_missing_pair_admitted_unknown_is_incomplete(self):
        result = score.score_answer(answer(reference_rows()[:-1],'unknown'),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')

    def test_all_pairs_without_completeness_is_incomplete(self):
        value = json.loads(answer());value.pop('status')
        self.assertEqual(score.score_answer(json.dumps(value),truth,snapshot)['status'],'incomplete')

    def test_wrong_distance_precedes_admitted_incompleteness(self):
        rows = reference_rows();rows[0]['distance_mm']='0.010'
        self.assertEqual(score.score_answer(answer(rows,'partial'),truth,snapshot)['status'],'incorrect')

    def test_duplicate_pair_is_incorrect_even_in_reverse_order(self):
        rows = reference_rows();rows.append(dict(rows[0],objects=list(reversed(rows[0]['objects']))))
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'incorrect')

    def test_false_positive_pair_is_incorrect(self):
        rows = reference_rows()
        invalid = next(row for row in truth['pairs'] if not row['matches_threshold'])
        rows.append(dict(objects=[invalid['object_a'],invalid['object_b']],distance_mm='3.000'))
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'incorrect')

    def test_scientific_notation_and_scene_bound_ids(self):
        aliases = score.namespace(snapshot)
        ids = {name:label for label,name in aliases.items() if label.startswith('blender:')}
        rows = reference_rows()
        for row in rows:
            row['objects'] = [ids[name] for name in row['objects']]
            row['distance_mm'] = row['distance_mm']+'e0'
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'complete_correct')

    def test_unambiguous_short_name_aliases(self):
        rows = reference_rows()
        for row in rows:
            row['objects'] = ['obj'+str(int(name.split('_')[1])) for name in row['objects']]
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'complete_correct')

    def test_metres_are_numerically_correct_and_presentation_incomplete(self):
        rows = reference_rows()
        for row in rows:
            row['distance_m'] = str(Decimal(row.pop('distance_mm'))/1000)
        result = score.score_answer(answer(rows),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['distance_correct_rows'],71)
        self.assertTrue(result['presentation_issues'])

    def test_centimetres_are_presentation_incomplete_without_numeric_error(self):
        rows = reference_rows()
        for row in rows:
            row['distance'] = str(Decimal(row.pop('distance_mm'))/10)
            row['unit'] = 'cm'
        result = score.score_answer(answer(rows),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['distance_correct_rows'],71)
        self.assertEqual(result['errors'],[])

    def test_nonzero_fewer_places_does_not_pass_presentation(self):
        rows = reference_rows()
        selected = next(row for row in rows if Decimal(row['distance_mm']) != 0)
        selected['distance_mm'] = str(Decimal(selected['distance_mm']).normalize())
        result = score.score_answer(answer(rows),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['errors'],[])
        self.assertTrue(result['presentation_issues'])

    def test_effective_scientific_resolution_and_exact_zero_exception(self):
        exact = dict(numerator='1',denominator='1000000')
        self.assertTrue(score.presentation_met('1.000e0','mm',exact))
        self.assertTrue(score.presentation_met('1000e-3','mm',exact))
        self.assertFalse(score.presentation_met('1.0e0','mm',exact))
        self.assertTrue(score.presentation_met('0','mm',dict(numerator='0',denominator='1')))
        self.assertFalse(score.presentation_met('0','mm',dict(numerator='1',denominator='1000000000000000000')))
        self.assertTrue(score.presentation_met('0.000','mm',dict(numerator='1',denominator='1000000000000000000')))

    def test_json_number_trailing_places_survive_extraction(self):
        rows = reference_rows()
        raw = answer(rows)
        for row in rows:
            raw = raw.replace('"'+row['distance_mm']+'"',row['distance_mm'])
        result = score.score_answer(raw,truth,snapshot)
        self.assertEqual(result['status'],'complete_correct')

    def test_bare_zero_rows_are_allowed_only_for_true_zero(self):
        rows = reference_rows()
        for row in rows:
            if Decimal(row['distance_mm']) == 0:
                row['distance_mm'] = '0'
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'complete_correct')

    def test_complete_visible_mm_list_eligible_and_raw_m_list_incomplete(self):
        visible = answer(reference_rows())
        self.assertEqual(score.score_answer(visible,truth,snapshot)['status'],'complete_correct')
        rows = reference_rows()
        for row in rows:
            row['distance_m'] = str(Decimal(row.pop('distance_mm'))/1000)
        result = score.score_answer(answer(rows),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['errors'],[])

    def test_markdown_rows_and_global_mm_header(self):
        lines = ['检查完整。','| 对象 A | 对象 B | 距离 (mm) |','|---|---|---|']
        lines += ['| '+' | '.join([*row['objects'],row['distance_mm']])+' |' for row in reference_rows()]
        self.assertEqual(score.score_answer('\n'.join(lines),truth,snapshot)['status'],'complete_correct')

    def test_unknown_distance_preserved_as_incomplete(self):
        rows = reference_rows();rows[0]['distance_mm']=None
        result = score.score_answer(answer(rows,'unknown'),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertTrue(result['review_required'])

    def test_missing_unit_does_not_invent_millimetres(self):
        rows = reference_rows();rows[0]['distance']=rows[0].pop('distance_mm')
        self.assertEqual(score.score_answer(answer(rows),truth,snapshot)['status'],'incomplete')

    def test_missing_final_has_execution_failure(self):
        self.assertEqual(score.score_answer(None,truth,snapshot)['status'],'execution_failure')

    def test_reference_to_visible_complete_list_requires_review(self):
        result = score.score_answer('检查完整，所有对象对及距离见刚才返回的完整清单。',truth,snapshot)
        self.assertIsNone(result['status'])
        self.assertTrue(result['review_required'])

    def test_unparsed_free_expression_is_unscored(self):
        result = score.score_answer('检查完整。Obj_001与Obj_002、Obj_003的间隙均为零。',truth,snapshot)
        self.assertIsNone(result['status'])
        self.assertTrue(result['review_required'])

    def test_extra_definite_error_is_preserved(self):
        result = score.score_answer(answer(),truth,snapshot,
            additional_errors=[dict(reason='unfounded_solid_collision_freedom_claim')])
        self.assertEqual(result['status'],'incorrect')

    def test_display_rounding_never_expands_membership(self):
        synthetic = copy.deepcopy(truth)
        outside = next(row for row in synthetic['pairs'] if not row['matches_threshold'])
        value = (Fraction(.002)+Fraction(1,10**10))**2
        outside['exact_squared_distance_m2'] = dict(numerator=str(value.numerator),denominator=str(value.denominator))
        rows = reference_rows()+[dict(objects=[outside['object_a'],outside['object_b']],distance_mm='2.000')]
        self.assertEqual(score.score_answer(answer(rows),synthetic,snapshot)['status'],'incorrect')

    def test_six_planned_slots_keep_missing_and_failed(self):
        sequence = [dict(cell=str(i),task='T1',group='X',round=i) for i in range(6)]
        records = [dict(sequence[0],final=answer()),dict(sequence[1],final=None,execution_status='failed')]
        result = score.score_slots(sequence,records,truth,snapshot)
        self.assertEqual(len(result),6)
        self.assertEqual([row['status'] for row in result],
            ['complete_correct','execution_failure','not_run','not_run','not_run','not_run'])

    def test_extra_duplicate_and_wrong_task_rows_rejected(self):
        sequence = [dict(cell=str(i),task='T1',group='X',round=i) for i in range(6)]
        records = [dict(row,final=answer()) for row in sequence]
        for bad in (records+[records[-1]],records[:-1]+[records[0]],
                    records[:-1]+[dict(records[-1],task='wrong')],
                    records[:-1]+[dict(records[-1],cell='unknown')]):
            with self.assertRaises(ValueError):
                score.score_slots(sequence,bad,truth,snapshot)


if __name__ == '__main__':
    unittest.main(verbosity=2)
