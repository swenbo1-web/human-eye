"""Pure query contracts can be checked without a host or a model."""
import unittest

from human_eye_plugin.query_policy import validate_query, measurement_contract, summarize_query


class QueryPolicyTests(unittest.TestCase):
    def test_default_overview_is_bounded_and_structurally_idempotent(self):
        self.assertEqual(validate_query(None), {'mode': 'overview', 'max_exact_pairs': 255})
        self.assertEqual(validate_query({}), validate_query(None))
        self.assertEqual(validate_query(validate_query(None)), validate_query(None))

    def test_bad_structure_modes_ids_and_budgets_are_rejected(self):
        cases = [False, 1, [], 'nearest', {'extra': 1}, {'mode': []}, {'mode': 'closest'},
                 {'object_ids': ['a']}, {'mode': 'nearest', 'object_ids': []},
                 {'mode': 'nearest', 'object_ids': None}, {'mode': 'nearest', 'object_ids': 'a'},
                 {'mode': 'nearest', 'object_ids': ['a', 'a']}, {'mode': 'nearest', 'object_ids': [{}]},
                 {'mode': 'nearest', 'object_ids': ['']}, {'mode': 'nearest', 'object_ids': ['  ']}]
        cases += [{'max_exact_pairs': value} for value in (True, False, 0, -1, 256, 1.0, None, '2')]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_query(value)

    def test_scene_membership_and_focal_are_checked_only_when_supplied(self):
        query = {'mode': 'nearest', 'object_ids': ['b', 'a'], 'max_exact_pairs': 2}
        normalized = validate_query(query)
        query['object_ids'].clear()
        self.assertEqual(normalized['object_ids'], ['b', 'a'])
        self.assertEqual(validate_query(normalized, object_ids={'focal', 'a', 'b'}, focal_id='focal'), normalized)
        with self.assertRaises(ValueError):
            validate_query(normalized, object_ids={'focal', 'a'})
        with self.assertRaises(ValueError):
            validate_query(normalized, focal_id='a')

    def test_exact_lower_bound_and_unknown_records_use_explicit_same_level_fields(self):
        exact = measurement_contract({'measurement_valid': True, 'signed_clearance_m': .7,
            'is_penetrating': False, 'strict_geometry': {'clearance_method': 'unrounded_surface'}})
        bound = measurement_contract({'signed_clearance_m': None, 'measurement_valid': False,
            'clearance_lower_bound_m': .6, 'numeric_bound_valid': True})
        unknown = measurement_contract({'measurement_valid': False, 'signed_clearance_m': None})
        self.assertEqual((exact['measurement_kind'], exact['clearance_exact'], exact['method']),
                         ('exact', True, 'unrounded_surface'))
        self.assertEqual((bound['measurement_kind'], bound['clearance_exact'], bound['method']),
                         ('lower_bound', False, 'outward_aabb_linf_lower_bound'))
        self.assertEqual((unknown['measurement_kind'], unknown['clearance_exact'], unknown['method']),
                         ('unknown', False, 'measurement_unavailable'))

    def test_certified_penetration_is_not_an_exact_global_depth_or_display_zero(self):
        record = measurement_contract({'measurement_valid': True, 'signed_clearance_m': -50e-6,
            'is_penetrating': True, 'display_signed_clearance_m': 0., 'alignment_state': 'ALIGNED_FLUSH',
            'alignment_state_is_display_only': True, 'strict_geometry': {'clearance_method': 'certified_escape'}})
        self.assertEqual(record['signed_clearance_m'], -50e-6)
        self.assertNotIn('display_signed_clearance_m', record)
        self.assertNotIn('alignment_state', record)
        self.assertEqual(record['legacy_display']['display_signed_clearance_m'], 0.)
        self.assertEqual(record['clearance_state'], 'negative_clearance')
        self.assertEqual(record['measurement_kind'], 'certified_penetration')
        self.assertFalse(record['clearance_exact'])
        self.assertIn('not_global_minimum', record['clearance_scope'])

    def test_nearest_never_sorts_incomplete_exact_values_using_bounds(self):
        contacts = [measurement_contract({'object_id': 'a', 'measurement_valid': True,
            'signed_clearance_m': .7}), measurement_contract({'object_id': 'b', 'measurement_valid': False,
            'signed_clearance_m': None, 'clearance_lower_bound_m': .6, 'numeric_bound_valid': True})]
        result = summarize_query(validate_query({'mode': 'nearest'}), requested_ids=['a', 'b'],
            reference_id='a', contacts=contacts, budget_deferred=['b'])
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['unresolved_object_ids'], ['b'])
        self.assertIsNone(result['ranked_object_ids'])
        self.assertIn('query_exact_pair_budget_exhausted', result['reason_codes'])


if __name__ == '__main__':
    unittest.main()
