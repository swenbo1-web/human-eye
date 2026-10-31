"""Capability descriptions preserve current gates without repeating geometry."""
import copy
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.scene_capabilities import build_scene_capabilities
from verification.test_host_runtime import mesh


FINGERPRINT = 'a' * 64


def captured_scene():
    return {
        'revision': 'current-scene-1', 'unit': 'm', 'coordinate_frame': 'world',
        'source': 'independent-capability-fixture',
        'meshes': [mesh('base', [0, 0, .1], [1, 1, .2]),
                   mesh('part', [0, 0, .254], [.2, .3, .1], True),
                   mesh('far', [10, 0, 0], [1, 1, 1])],
        'host_execution': {
            'schema_version': '1.0', 'operation': 'rigid_transform',
            'supported': True, 'scope': 'independent_static_rigid_meshes', 'reasons': [],
        },
        'host_identity': {
            'schema_version': '1.0', 'document_epoch': 'document-1',
            'capture_scope': 'complete_scene_meshes',
            'object_instances': {'base': 'base-1', 'part': 'part-1', 'far': 'far-1'},
        },
    }


def current_evidence(scene):
    return {
        'scene_revision': scene['revision'], 'scene_fingerprint': FINGERPRINT,
        'solid_support': {
            item['object_id']: {'supported': True, 'support_method': 'existing_solid_classifier',
                                'work_budget': {'within_budget': True}}
            for item in scene['meshes']
        },
        'pair_measurements': [
            {'focal_id': 'part', 'reference_id': 'base', 'signed_clearance_m': .004,
             'measurement_valid': True, 'is_penetrating': False},
        ],
    }


class NoGeometryWalk(list):
    def __iter__(self):
        raise AssertionError('Capability diagnostics must not traverse geometry')

    def __getitem__(self, index):
        raise AssertionError('Capability diagnostics must not inspect geometry elements')


class SceneCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.scene = captured_scene()
        self.evidence = current_evidence(self.scene)

    def describe(self, **changes):
        kwargs = {'scene_fingerprint': FINGERPRINT, 'computed_evidence': self.evidence}
        kwargs.update(changes)
        return build_scene_capabilities(self.scene, **kwargs)

    @staticmethod
    def objects(result):
        return {item['object_id']: item for item in result['objects']}

    def test_default_reports_available_records_but_unknown_algorithm_support(self):
        result = build_scene_capabilities(self.scene)
        objects = self.objects(result)
        self.assertEqual(objects['part']['capture']['status'], 'supported')
        self.assertEqual(objects['part']['obstacle_geometry']['status'], 'unknown')
        self.assertEqual(objects['part']['represented_mesh_measurement']['status'], 'unknown')
        self.assertEqual(objects['part']['movable']['status'], 'unknown')
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['changes_existing_gates'])

    def test_supported_prerequisites_still_do_not_certify_an_action_or_path(self):
        result = self.describe()
        part = self.objects(result)['part']
        self.assertEqual(part['obstacle_geometry']['status'], 'supported')
        self.assertEqual(part['movable']['status'], 'supported')
        self.assertFalse(part['movable']['execution_authority'])
        self.assertFalse(part['movable']['candidate_checked'])
        self.assertTrue(part['movable']['fresh_execution_required'])
        self.assertEqual(result['scene']['candidate_endpoint']['status'], 'not_evaluated')
        self.assertEqual(result['scene']['swept_path']['status'], 'not_evaluated')

    def test_far_modifier_keeps_all_current_movement_blocked(self):
        reason = {'object_id': 'far', 'object_name': 'Far object', 'reason': 'modifiers_present'}
        self.scene['host_execution'].update(supported=False, reasons=[reason])
        result = self.describe()
        objects = self.objects(result)
        self.assertEqual(objects['part']['capture']['status'], 'supported')
        self.assertEqual(objects['part']['represented_mesh_measurement']['status'], 'supported')
        self.assertEqual(objects['far']['obstacle_geometry']['status'], 'supported')
        self.assertEqual(objects['part']['host_object_restrictions'], [])
        for item in objects.values():
            self.assertEqual(item['movable']['status'], 'unsupported')
            self.assertIn('modifiers_present', item['movable']['reason_codes'])
        self.assertEqual(result['host_execution_declaration']['reasons'], [reason])

    def test_details_filter_does_not_hide_scene_wide_blocker(self):
        self.scene['host_execution'].update(supported=False, reasons=[
            {'object_id': 'far', 'object_name': 'far', 'reason': 'transform_locks_present'}])
        result = self.describe(object_ids=['part', 'base'])
        self.assertEqual([item['object_id'] for item in result['objects']], ['part', 'base'])
        self.assertEqual(result['scene']['captured_object_count'], 3)
        self.assertEqual(result['scene']['detailed_object_count'], 2)
        self.assertTrue(result['scene']['details_filtered'])
        self.assertEqual(result['scene']['host_editability_gate']['blocking_objects'], ['far'])
        self.assertEqual(self.objects(result)['part']['movable']['status'], 'unsupported')

    def test_empty_details_filter_preserves_full_summary(self):
        result = self.describe(object_ids=[])
        self.assertEqual(result['objects'], [])
        self.assertEqual(result['scene']['captured_object_count'], 3)
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'supported')

    def test_known_unsupported_solid_differs_from_resource_unknown(self):
        self.evidence['solid_support']['far'] = {
            'supported': False, 'reason': 'unsupported_solid_geometry'}
        result = self.describe(object_ids=['part'])
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'unsupported')
        self.assertEqual(result['scene']['unresolved_solid_object_ids'], ['far'])
        self.assertEqual(self.objects(result)['part']['movable']['status'], 'unsupported')
        self.evidence['solid_support']['far']['reason'] = 'scene_solid_validation_resource_limit'
        result = self.describe()
        self.assertEqual(self.objects(result)['far']['obstacle_geometry']['status'], 'unknown')
        self.assertEqual(self.objects(result)['part']['movable']['status'], 'unknown')

    def test_missing_solid_evidence_is_not_inferred_from_bounds_or_capture(self):
        del self.evidence['solid_support']['far']
        result = self.describe()
        self.assertEqual(self.objects(result)['far']['capture']['status'], 'supported')
        self.assertEqual(self.objects(result)['far']['obstacle_geometry']['status'], 'unknown')
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'unknown')

    def test_stale_revision_or_fingerprint_discards_computed_evidence(self):
        for field, wrong in (('scene_revision', 'old'), ('scene_fingerprint', 'b' * 64)):
            with self.subTest(field=field):
                evidence = copy.deepcopy(self.evidence)
                evidence[field] = wrong
                result = self.describe(computed_evidence=evidence)
                self.assertEqual(result['evidence_binding']['status'], 'unknown')
                part = self.objects(result)['part']
                self.assertEqual(part['obstacle_geometry']['status'], 'unknown')
                self.assertEqual(part['represented_mesh_measurement']['status'], 'unknown')

    def test_missing_current_fingerprint_cannot_bind_support(self):
        result = self.describe(scene_fingerprint=None)
        self.assertEqual(result['evidence_binding']['status'], 'unknown')
        self.assertEqual(self.objects(result)['part']['obstacle_geometry']['status'], 'unknown')

    def test_lower_bound_is_counted_without_becoming_exact(self):
        self.evidence['pair_measurements'] = [{
            'focal_id': 'part', 'reference_id': 'base', 'measurement_valid': False,
            'numeric_bound_valid': True, 'clearance_lower_bound_m': .003,
            'measurement_kind': 'exact',
        }]
        result = self.describe()
        measured = self.objects(result)['part']['represented_mesh_measurement']
        self.assertEqual(measured['precision_counts']['exact'], 0)
        self.assertEqual(measured['precision_counts']['lower_bound'], 1)
        self.assertFalse(measured['all_scene_pairs_evaluated'])
        self.assertEqual(self.objects(result)['far']['represented_mesh_measurement']['status'], 'unknown')

    def test_pair_label_cannot_override_invalid_or_conflicting_numeric_evidence(self):
        record = self.evidence['pair_measurements'][0]
        record.update(measurement_kind='exact', strict_geometry={'measurement_valid': False})
        measured = self.objects(self.describe())['part']['represented_mesh_measurement']
        self.assertEqual(measured['status'], 'unknown')
        self.assertEqual(measured['precision_counts']['exact'], 0)

    def test_duplicate_identical_pair_is_counted_once_and_conflict_is_unknown(self):
        self.evidence['pair_measurements'].append(copy.deepcopy(self.evidence['pair_measurements'][0]))
        measured = self.objects(self.describe())['part']['represented_mesh_measurement']
        self.assertEqual(measured['pair_count'], 1)
        self.assertEqual(measured['precision_counts']['exact'], 1)
        self.evidence['pair_measurements'][1]['signed_clearance_m'] = .008
        measured = self.objects(self.describe())['part']['represented_mesh_measurement']
        self.assertEqual(measured['pair_count'], 1)
        self.assertEqual(measured['status'], 'unknown')

    def test_pair_penetration_is_not_exact_positive_clearance(self):
        self.evidence['pair_measurements'][0].update(signed_clearance_m=-.001, is_penetrating=True)
        measured = self.objects(self.describe())['part']['represented_mesh_measurement']
        self.assertEqual(measured['precision_counts']['certified_penetration'], 1)
        self.assertEqual(measured['precision_counts']['exact'], 0)

    def test_missing_host_declaration_is_unknown_even_for_legacy_optional_policy(self):
        self.scene.pop('host_execution')
        for required in (False, True):
            with self.subTest(required=required):
                result = self.describe(require_host_execution=required)
                self.assertEqual(result['scene']['host_editability_gate']['status'], 'unknown')
                self.assertEqual(result['scene']['host_editability_gate']['required_by_caller'], required)
                self.assertEqual(self.objects(result)['part']['movable']['status'], 'unknown')

    def test_missing_frame_does_not_erase_available_mesh_measurement(self):
        self.scene['meshes'][1].pop('pivot_world')
        result = self.describe()
        part = self.objects(result)['part']
        self.assertEqual(part['represented_mesh_measurement']['status'], 'supported')
        self.assertEqual(part['host_rigid_frame']['status'], 'unsupported')
        self.assertEqual(part['movable']['status'], 'unsupported')

    def test_capture_scope_requires_explicit_complete_host_inventory(self):
        result = self.describe()
        self.assertEqual(result['scene']['capture_completeness']['status'], 'supported')
        self.scene['host_identity']['object_instances'].pop('far')
        result = self.describe()
        self.assertEqual(result['scene']['capture_completeness']['status'], 'unknown')

    def test_invalid_host_reason_namespace_is_unknown_not_permission(self):
        self.scene['host_execution'].update(supported=False, reasons=[
            {'object_id': ['not-an-id'], 'object_name': 'bad', 'reason': 'modifiers_present'}])
        result = self.describe()
        self.assertEqual(result['scene']['host_editability_gate']['status'], 'unknown')
        self.assertEqual(self.objects(result)['part']['movable']['status'], 'unknown')

    def test_invalid_computed_namespace_is_not_assigned_to_another_object(self):
        self.evidence['pair_measurements'][0]['reference_id'] = 'absent-object'
        result = self.describe()
        self.assertEqual(result['evidence_binding']['status'], 'unknown')
        self.assertEqual(self.objects(result)['part']['obstacle_geometry']['status'], 'unknown')

    def test_malformed_or_contradictory_support_evidence_stays_unknown(self):
        for budget in ([], {'within_budget': False}):
            with self.subTest(budget=budget):
                self.evidence['solid_support']['part']['work_budget'] = budget
                result = self.describe()
                self.assertEqual(self.objects(result)['part']['obstacle_geometry']['status'], 'unknown')

    def test_solid_budget_flag_requires_an_actual_boolean(self):
        for value in (None, 0, 1, 0.0, 1.0, 'false', 'true', [], {}):
            with self.subTest(value=value):
                self.evidence['solid_support']['part']['work_budget'] = {'within_budget': value}
                result = self.describe()
                part = self.objects(result)['part']
                self.assertEqual(part['obstacle_geometry']['status'], 'unknown')
                self.assertIn('solid_support_evidence_invalid', part['obstacle_geometry']['reason_codes'])
                self.assertEqual(result['scene']['current_motion_prerequisites']['status'], 'unknown')
                self.assertEqual(part['represented_mesh_measurement']['status'], 'supported')

    def test_missing_solid_budget_cannot_be_inferred_from_capture_or_pair_result(self):
        for record in ({'supported': True}, {'supported': True, 'work_budget': None},
                       {'supported': True, 'work_budget': {}}):
            with self.subTest(record=record):
                self.evidence['solid_support']['part'] = record
                result = self.describe()
                part = self.objects(result)['part']
                self.assertEqual(part['capture']['status'], 'supported')
                self.assertEqual(part['represented_mesh_measurement']['status'], 'supported')
                self.assertEqual(part['obstacle_geometry']['status'], 'unknown')
                self.assertIn('solid_support_budget_not_supplied', part['obstacle_geometry']['reason_codes'])

    def test_explicit_failure_markers_cannot_override_true_support_and_budget(self):
        cases = [
            {'reason': 'unsupported_solid_geometry'},
            {'reason': 'geometry_resource_limit'},
            {'reason': 'scene_solid_validation_resource_limit'},
            {'reason': 'solid_support_evaluation_failed'},
            {'error_type': 'ValueError'},
            {'reason_codes': ['solid_support_evaluation_failed']},
            {'work_budget': {'within_budget': True, 'reason_codes': ['dense_geometry_work_limit']}},
        ]
        for conflicting in cases:
            with self.subTest(conflicting=conflicting):
                self.evidence['solid_support']['part'] = {
                    'supported': True, 'work_budget': {'within_budget': True}, **conflicting}
                part = self.objects(self.describe())['part']
                self.assertEqual(part['obstacle_geometry']['status'], 'unknown')
                self.assertIn('solid_support_evidence_contradictory', part['obstacle_geometry']['reason_codes'])

    def test_malformed_failure_metadata_does_not_promote_support(self):
        for malformed in ({'reason': []}, {'error_type': []}, {'reason_codes': None},
                          {'reason_codes': [None]},
                          {'work_budget': {'within_budget': True, 'reason_codes': 'none'}}):
            with self.subTest(malformed=malformed):
                self.evidence['solid_support']['part'] = {
                    'supported': True, 'work_budget': {'within_budget': True}, **malformed}
                self.assertEqual(self.objects(self.describe())['part']['obstacle_geometry']['status'], 'unknown')

    def test_descriptive_success_reason_preserves_valid_support(self):
        self.evidence['solid_support']['part'].update(reason='closed_convex_components_supported')
        result = self.describe()
        self.assertEqual(self.objects(result)['part']['obstacle_geometry']['status'], 'supported')
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'supported')

    def test_filtered_far_invalid_budget_remains_a_scene_wide_unknown(self):
        self.evidence['solid_support']['far']['work_budget']['within_budget'] = 0
        result = self.describe(object_ids=['part'])
        self.assertEqual(result['scene']['unresolved_solid_object_ids'], ['far'])
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'unknown')
        self.assertEqual(self.objects(result)['part']['obstacle_geometry']['status'], 'supported')
        self.assertEqual(self.objects(result)['part']['movable']['status'], 'unknown')

    def test_diagnostics_do_not_traverse_geometry_or_rerun_kernels(self):
        for item in self.scene['meshes']:
            item['vertices'] = NoGeometryWalk(item['vertices'])
            item['faces'] = NoGeometryWalk(item['faces'])
        with patch('human_eye_plugin.geometry_safety.solid_support_status', side_effect=AssertionError('Repeated solid kernel')), \
                patch('human_eye_plugin.geometry_safety.measure_pair_geometry', side_effect=AssertionError('Repeated pair kernel')):
            result = self.describe()
        self.assertEqual(result['scene']['solid_obstacle_domain']['status'], 'supported')
        self.assertEqual(self.objects(result)['part']['capture']['status'], 'supported')

    def test_input_and_returned_mutable_fields_are_detached(self):
        self.scene['host_execution'].update(supported=False, reasons=[
            {'object_id': 'far', 'object_name': 'far', 'reason': 'modifiers_present'}])
        original_scene, original_evidence = copy.deepcopy(self.scene), copy.deepcopy(self.evidence)
        result = self.describe()
        result['host_execution_declaration']['reasons'][0]['reason'] = 'tampered'
        result['objects'][0]['movable']['reason_codes'].append('tampered')
        self.assertEqual(self.scene, original_scene)
        self.assertEqual(self.evidence, original_evidence)

    def test_result_is_json_compatible_and_filters_cannot_add_objects(self):
        json.dumps(self.describe(), allow_nan=False)
        for selection in (['part', 'part'], ['unknown'], 'part'):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.describe(object_ids=selection)


if __name__ == '__main__':
    unittest.main()
