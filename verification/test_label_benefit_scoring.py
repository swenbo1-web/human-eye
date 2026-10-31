"""Task benefit scoring contracts, independent from actual reader trial results."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

MODULE = Path(__file__).parent / 'fixes/20261027_refill_budget_recovery/task_benefit/score_responses.py'
spec = importlib.util.spec_from_file_location('label_benefit_scoring', MODULE)
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


class LabelBenefitScoringTests(unittest.TestCase):
    def test_correct_id_requires_localization_in_requested_view(self):
        truth = {'endpoint': 'identity', 'object_id': 'one', 'view_index': 1,
                 'query_point_px': [300, 80], 'minimum_other_point_distance_px': 3,
                 'location_tolerance_px': 3}
        mask = np.zeros((256, 256), bool)
        mask[80:91, 44:55] = True
        answer = {'task_id': 't', 'decision': 'answer', 'object_id': 'one', 'surface_point_px': [306, 86]}
        self.assertTrue(scoring.score_answer(answer, truth, 't', {'1': mask})['task_complete'])
        for point in ([300, 80], [50, 86], [506, 200], [True, 86], [float('nan'), 86]):
            with self.subTest(point=point):
                self.assertFalse(scoring.score_answer({**answer, 'surface_point_px': point}, truth, 't', {'1': mask})['task_complete'])
        self.assertFalse(scoring.score_answer({**answer, 'object_id': 'other'}, truth, 't', {'1': mask})['task_complete'])

    def test_abstention_is_separate_from_solved(self):
        row = scoring.score_answer({'task_id': 't', 'decision': 'abstain'}, {'endpoint': 'gap'}, 't')
        self.assertTrue(row['abstained'])
        self.assertFalse(row['answered'])
        self.assertFalse(row['task_complete'])

    def test_numeric_relation_jointly_required_bool_nonfinite_rejected(self):
        truth = {'endpoint': 'gap', 'gap_mm': 4., 'relation': 'separated', 'numeric_tolerance_mm': .25}
        answer = {'task_id': 't', 'decision': 'answer', 'gap_mm': 4., 'relation': 'separated'}
        self.assertTrue(scoring.score_answer(answer, truth, 't')['task_complete'])
        self.assertFalse(scoring.score_answer({**answer, 'relation': 'touching'}, truth, 't')['task_complete'])
        for value in (True, float('inf'), float('nan'), '4', None):
            self.assertFalse(scoring.score_answer({**answer, 'gap_mm': value}, truth, 't')['valid'])

    def test_complete_contact_set_rejects_duplicates_and_missing_hidden_id(self):
        truth = {'endpoint': 'contacts', 'penetrating_object_ids': ['hidden', 'visible']}
        answer = {'task_id': 't', 'decision': 'answer', 'penetrating_object_ids': ['visible', 'hidden']}
        self.assertTrue(scoring.score_answer(answer, truth, 't')['task_complete'])
        for ids in (['visible'], ['visible', 'hidden', 'visible'], ['visible', 'hidden', 'extra'], None):
            self.assertFalse(scoring.score_answer({**answer, 'penetrating_object_ids': ids}, truth, 't')['task_complete'])

    def test_task_identity_cannot_be_reused(self):
        self.assertFalse(scoring.score_answer({'task_id': 'other', 'decision': 'abstain'}, {'endpoint': 'gap'}, 't')['valid'])


if __name__ == '__main__':
    unittest.main()
