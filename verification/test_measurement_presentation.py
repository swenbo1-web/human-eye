"""Strict measurement wording and independent hostile-input boundaries."""
from __future__ import annotations

import copy
import json
import math
import unittest

from human_eye_plugin.hook_context import compact_hook_summary, encode_hook_summary
from human_eye_plugin.measurement_presentation import (
    finite_metric, present_measurement, valid_unrounded_measurement,
)
from human_eye_plugin.query_policy import measurement_contract
from human_eye_plugin.result_contract import scoped_result


def measured(value=25e-6, *, penetrating=False):
    return {
        'measurement_valid': True, 'signed_clearance_m': value,
        'is_penetrating': penetrating,
        'display_signed_clearance_m': 0.,
        'alignment_state': 'ALIGNED_FLUSH',
        'alignment_state_is_display_only': True,
        'axes_valid': False, 'axes_check': 'legacy_alignment_not_available',
        'rigid_frame_valid': True, 'rigid_frame': {'valid': True, 'execution_authority': False},
        'point_a_world': [1., 2., 3.000025], 'point_b_world': [1., 2., 3.],
        'strict_geometry': {
            'measurement_valid': True, 'signed_clearance_m': value,
            'is_penetrating': penetrating, 'collision_tolerance_m': 1e-9,
            'clearance_method': 'independent_test_unrounded_surface',
            'independent_ground_truth': False,
        },
    }


class MeasurementPresentationTests(unittest.TestCase):
    def test_25um_is_positive_without_same_level_flush_aliases(self):
        record = measured()
        result = measurement_contract(record)
        self.assertEqual(result['signed_clearance_m'], 25e-6)
        self.assertEqual(result['clearance_state'], 'positive_clearance')
        for name in ('alignment_state', 'display_signed_clearance_m',
                     'alignment_state_is_display_only'):
            self.assertNotIn(name, result)
        self.assertEqual(result['legacy_display']['alignment_state'], 'ALIGNED_FLUSH')
        self.assertEqual(result['legacy_display']['display_signed_clearance_m'], 0)
        self.assertFalse(result['legacy_display']['execution_authority'])

    def test_positive_sub_tolerance_clearance_is_never_rounded_to_zero(self):
        result = measurement_contract(measured(1e-12))
        self.assertEqual(result['clearance_state'], 'positive_clearance')
        self.assertEqual(result['signed_clearance_m'], 1e-12)
        self.assertEqual(result['strict_geometry']['collision_tolerance_m'], 1e-9)
        self.assertEqual(result['measurement_kind'], 'exact')

    def test_negative_clearance_preserves_the_unrounded_signed_metric(self):
        result = measurement_contract(measured(-50e-6, penetrating=True))
        self.assertEqual(result['clearance_state'], 'negative_clearance')
        self.assertEqual(result['signed_clearance_m'], -50e-6)
        self.assertEqual(result['measurement_kind'], 'certified_penetration')
        self.assertFalse(result['clearance_exact'])
        self.assertIn('not_global_minimum', result['clearance_scope'])

    def test_negative_sub_collision_tolerance_does_not_rewrite_collision_flag(self):
        result = measurement_contract(measured(-1e-12, penetrating=False))
        self.assertEqual(result['clearance_state'], 'negative_clearance')
        self.assertEqual(result['signed_clearance_m'], -1e-12)
        self.assertIs(result['is_penetrating'], False)
        self.assertIs(result['strict_geometry']['is_penetrating'], False)

    def test_both_signed_zeros_are_zero_metrics_not_alignment_certificates(self):
        for value in (0., -0.):
            with self.subTest(value=repr(value)):
                result = measurement_contract(measured(value))
                self.assertEqual(result['clearance_state'], 'zero_clearance')
                self.assertEqual(math.copysign(1., result['signed_clearance_m']),
                                 math.copysign(1., value))
                self.assertNotIn('alignment_state', result)
                self.assertFalse(result['legacy_display']['execution_authority'])

    def test_invalid_measurement_cannot_become_positive_from_a_display_value(self):
        record = measured()
        record['measurement_valid'] = False
        result = measurement_contract(record)
        self.assertEqual(result['clearance_state'], 'unknown')
        self.assertEqual(result['measurement_kind'], 'unknown')
        self.assertFalse(result['measurement_valid'])

    def test_missing_measurement_stays_unknown(self):
        result = measurement_contract({'measurement_valid': False, 'signed_clearance_m': None})
        self.assertEqual(result['clearance_state'], 'unknown')
        self.assertEqual(result['measurement_kind'], 'unknown')
        self.assertNotIn('legacy_display', result)

    def test_bool_string_nonfinite_and_huge_numbers_are_not_metrics(self):
        for value in (True, False, None, '0.000025', [], {}, math.nan, math.inf,
                      -math.inf, 10 ** 400):
            with self.subTest(value=repr(value)):
                result = measurement_contract(measured(value))
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')
                self.assertFalse(result['clearance_exact'])

    def test_nonliteral_validity_flags_do_not_certify_measurement(self):
        for value in (1, 0, 'true', None, [], {}):
            record = measured()
            record['measurement_valid'] = value
            with self.subTest(value=value):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_strict_explicit_invalidity_does_not_launder_display_metric(self):
        record = measured()
        record['strict_geometry']['measurement_valid'] = False
        result = measurement_contract(record)
        self.assertEqual(result['clearance_state'], 'unknown')
        self.assertEqual(result['measurement_kind'], 'unknown')
        self.assertEqual(result['signed_clearance_m'], 25e-6)

    def test_conflicting_strict_distance_is_not_blessed_as_exact(self):
        record = measured()
        record['strict_geometry']['signed_clearance_m'] = 0
        result = measurement_contract(record)
        self.assertEqual(result['clearance_state'], 'unknown')
        self.assertEqual(result['measurement_kind'], 'unknown')
        self.assertEqual(result['strict_geometry']['signed_clearance_m'], 0)
        self.assertEqual(result['signed_clearance_m'], 25e-6)

    def test_conflicting_strict_penetration_is_unknown(self):
        record = measured(-25e-6)
        record['strict_geometry']['is_penetrating'] = True
        result = measurement_contract(record)
        self.assertEqual(result['clearance_state'], 'unknown')
        self.assertEqual(result['measurement_kind'], 'unknown')

    def test_malformed_strict_envelopes_remain_unknown(self):
        for strict in (None, False, [], 'trusted'):
            record = measured()
            record['strict_geometry'] = strict
            with self.subTest(strict=strict):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_malformed_strict_numeric_field_is_unknown(self):
        for value in (True, False, None, '0.000025', math.nan, math.inf, 10 ** 400):
            record = measured()
            record['strict_geometry']['signed_clearance_m'] = value
            with self.subTest(value=repr(value)):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_strict_boolean_fields_require_literal_booleans(self):
        for name in ('is_penetrating', 'measurement_valid'):
            record = measured()
            record['strict_geometry'][name] = 1
            with self.subTest(name=name):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_top_penetration_field_requires_a_literal_boolean(self):
        for value in (1, 0, 'false', [], {}):
            record = measured()
            record['is_penetrating'] = value
            with self.subTest(value=value):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_positive_or_zero_penetration_certificate_is_inconsistent(self):
        for value in (0., -0., 25e-6):
            with self.subTest(value=value):
                result = measurement_contract(measured(value, penetrating=True))
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_existing_method_only_strict_envelope_is_compatible(self):
        record = {'measurement_valid': True, 'signed_clearance_m': .7,
                  'is_penetrating': False, 'strict_geometry': {'clearance_method': 'unrounded'}}
        result = measurement_contract(record)
        self.assertEqual((result['measurement_kind'], result['clearance_exact'], result['method']),
                         ('exact', True, 'unrounded'))
        self.assertEqual(result['clearance_state'], 'positive_clearance')

    def test_existing_minimal_measurement_without_strict_envelope_is_compatible(self):
        result = measurement_contract({'measurement_valid': True, 'signed_clearance_m': .7})
        self.assertEqual(result['clearance_state'], 'positive_clearance')
        self.assertEqual(result['measurement_kind'], 'exact')

    def test_lower_bound_is_never_presented_as_an_exact_distance(self):
        for bound in (0., .6):
            record = {'measurement_valid': False, 'signed_clearance_m': None,
                      'numeric_bound_valid': True, 'clearance_lower_bound_m': bound}
            with self.subTest(bound=bound):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'lower_bound')
                self.assertEqual(result['measurement_kind'], 'lower_bound')
                self.assertFalse(result['clearance_exact'])
                self.assertIsNone(result['signed_clearance_m'])

    def test_invalid_lower_bounds_remain_unknown(self):
        for value in (True, None, '0.1', math.inf, math.nan, 10 ** 400):
            record = {'measurement_valid': False, 'signed_clearance_m': None,
                      'numeric_bound_valid': True, 'clearance_lower_bound_m': value}
            with self.subTest(value=repr(value)):
                result = measurement_contract(record)
                self.assertEqual(result['clearance_state'], 'unknown')
                self.assertEqual(result['measurement_kind'], 'unknown')

    def test_projection_is_idempotent(self):
        for source in (measured(), measured(-1e-12), measured(0.), {'measurement_valid': False}):
            with self.subTest(source=source):
                once = measurement_contract(source)
                twice = measurement_contract(once)
                self.assertEqual(once, twice)
                self.assertEqual(json.dumps(once, sort_keys=True, allow_nan=False),
                                 json.dumps(twice, sort_keys=True, allow_nan=False))

    def test_input_is_not_mutated_and_legacy_values_are_detached(self):
        source = measured()
        source['alignment_state'] = ['legacy', {'other': 1}]
        before = copy.deepcopy(source)
        result = measurement_contract(source)
        self.assertEqual(source, before)
        result['legacy_display']['alignment_state'][1]['other'] = 2
        self.assertEqual(source, before)

    def test_original_strict_geometry_frames_and_witnesses_are_preserved(self):
        source = measured()
        result = measurement_contract(source)
        for field in ('strict_geometry', 'axes_valid', 'axes_check', 'rigid_frame',
                      'rigid_frame_valid', 'point_a_world', 'point_b_world'):
            with self.subTest(field=field):
                self.assertEqual(result[field], source[field])

    def test_presentation_does_not_add_execution_or_goal_authority(self):
        source = measured()
        result = measurement_contract(source)
        for key in ('allow_action', 'task_succeeded', 'execution_verified',
                    'execution_authority', 'is_aligned_flush'):
            self.assertNotIn(key, result)
        self.assertFalse(result['legacy_display']['execution_authority'])

    def test_existing_legacy_namespace_is_preserved_and_cannot_gain_authority(self):
        source = measured()
        source['legacy_display'] = {'other': ['retained'], 'execution_authority': True}
        before = copy.deepcopy(source)
        result = measurement_contract(source)
        self.assertEqual(result['legacy_display']['other'], ['retained'])
        self.assertFalse(result['legacy_display']['execution_authority'])
        self.assertEqual(source, before)
        self.assertEqual(result, measurement_contract(result))

    def test_non_dictionary_legacy_namespace_is_retained_as_diagnostic_only(self):
        source = measured()
        source['legacy_display'] = ['previous diagnostic']
        result = measurement_contract(source)
        self.assertEqual(result['legacy_display']['previous_value'], ['previous diagnostic'])
        self.assertEqual(result, measurement_contract(result))

    def test_stale_presentation_state_cannot_override_the_metric(self):
        source = measured()
        source['clearance_state'] = 'zero_clearance'
        self.assertEqual(measurement_contract(source)['clearance_state'], 'positive_clearance')

    def test_hook_projection_keeps_canonical_surface_wording(self):
        measurement = measurement_contract(measured())
        context = {'measurement': measurement, 'observation_status': 'complete'}
        summary = {'human_eye_live': 'observed', 'observation': json.dumps(context)}
        projected = compact_hook_summary(summary, {}, {}, correlation={'turn_id': 'test'},
            identity={'source_kind': 'independent_fixture'})
        encoded = json.loads(encode_hook_summary(projected))
        canonical = encoded['observation']['measurement']
        self.assertEqual(canonical['clearance_state'], 'positive_clearance')
        self.assertEqual(canonical['signed_clearance_m'], 25e-6)
        self.assertNotIn('alignment_state', canonical)
        self.assertEqual(canonical['legacy_display']['alignment_state'], 'ALIGNED_FLUSH')

    def test_scoped_result_does_not_promote_presentation_to_a_goal_or_permission(self):
        measurement = measurement_contract(measured())
        result = scoped_result({'status': 'observed', 'measurement': measurement},
                               operation='observe')
        self.assertEqual(result['measurement'], measurement)
        self.assertFalse(result['action_eligibility']['execution_authority'])
        self.assertEqual(result['action_eligibility']['status'], 'not_evaluated')
        self.assertEqual(result['pair_goal']['status'], 'not_requested')

    def test_pure_presentation_handles_plain_finite_records_without_type_conversion(self):
        for value in (1, 0, -1, 1e-12):
            with self.subTest(value=value):
                source = {'measurement_valid': True, 'signed_clearance_m': value}
                result = present_measurement(source)
                self.assertIs(type(result['signed_clearance_m']), type(value))
                self.assertTrue(valid_unrounded_measurement(result))
                self.assertTrue(finite_metric(value))


if __name__ == '__main__':
    unittest.main()

