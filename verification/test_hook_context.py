"""Independent lossless-display checks; no live host, model or installation.

The decoder below is deliberately independent of the production compactor.
Historical Round02 input is optional outside this checkout, never bundled as
runtime data. All geometry composition uses an isolated mutable host double.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.hook_context import compact_hook_summary, encode_hook_summary
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_TRANSFORM


ROOT = Path(__file__).resolve().parents[1]
ROUND02 = ROOT / 'verification/fixes/20261023_agent_live_delivery/ROUND_02_AUTOMATIC_PROMPT_PARSED.json'
ROUND02_SHA256 = '4869504b9893f83c295396ebf2e793f09835074e28da025a81b8cc87af0d59b8'
SCOPED = ('observation_status', 'scene_assessment', 'action_eligibility',
          'pair_goal', 'execution_status', 'task_succeeded_scope', 'host_execution')
ALLOWED_OMISSIONS = {'observation.scene_memory.stats', 'observation.measurement_cache.stats'}
IDENTITY = {'build_id': 'sha256:independent-test-fixture',
            'implementation_revision': 'independent-test-fixture', 'source_kind': 'test_double'}
CORRELATION = {'turn_id': 'host-turn', 'tool_use_id': 'host-call',
               'trace_id': 'trace', 'request_id': 'request', 'request_origin': 'manual_probe'}


def expand_references(document):
    """Expand same-document JSON Pointers, rejecting invalid paths and cycles."""
    encoding = document.get('context_projection', {}).get('reference_encoding')
    if encoding == 'disabled_reserved_key':
        return copy.deepcopy(document)
    def lookup(pointer):
        if not isinstance(pointer, str) or not (pointer == '#' or pointer.startswith('#/')):
            raise AssertionError('Reference is not a local JSON Pointer: ' + repr(pointer))
        target = document
        for token in pointer[2:].split('/') if pointer != '#' else ():
            token = token.replace('~1', '/').replace('~0', '~')
            target = target[int(token)] if isinstance(target, list) else target[token]
        return target

    def visit(value, active=()):
        if isinstance(value, dict):
            if '$ref' in value:
                pointer = value['$ref']
                if pointer in active:
                    raise AssertionError('Cyclic local reference: ' + str(pointer))
                target = visit(lookup(pointer), (*active, pointer))
                siblings = {key: item for key, item in value.items() if key != '$ref'}
                if siblings:
                    if set(siblings) != {'object_id'} or not isinstance(target, dict):
                        raise AssertionError('Unsupported reference siblings')
                    if set(target).intersection(siblings):
                        raise AssertionError('Reference siblings overwrite evidence')
                    target.update({key: visit(item, active) for key, item in siblings.items()})
                return target
            return {key: visit(item, active) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item, active) for item in value]
        return copy.deepcopy(value)
    return visit(document)


def ref_values(value):
    if isinstance(value, dict):
        if '$ref' in value:
            yield value['$ref']
        for item in value.values():
            yield from ref_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from ref_values(item)


def expected_facts(facts):
    result = copy.deepcopy(facts)
    for key in ('scene_memory', 'measurement_cache'):
        if isinstance(result.get(key), dict):
            result[key].pop('stats', None)
    return result


def frame(valid=True):
    return {'valid': valid, 'scope': 'explicit_host_world_rigid_frame_only',
            'execution_authority': False,
            'objects': {name: {'object_id': name, 'valid': valid,
                'axes_source': 'host' if valid else 'ambiguous_geometry',
                'axes_confidence': 'explicit' if valid else 'ambiguous',
                'pivot_world': [12.0, -7.0, 3.0],
                'local_axes': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                'reason_codes': [] if valid else ['axes_source_not_host', 'axes_not_explicit']}
                for name in ('focal', 'reference')}}


def facts_fixture():
    rigid = frame()
    measurement = {'measurement_valid': True, 'measurement_kind': 'exact',
        'clearance_exact': True, 'method': 'unrounded_all_surface_features',
        'signed_clearance_m': 0.0010000000474974513, 'is_penetrating': False,
        'point_a_world': [12.035, -7.012, 3.0000000000474976],
        'point_b_world': [12.035, -7.012, 2.999],
        'rigid_frame_valid': True, 'rigid_frame': rigid,
        'legacy_axes_validation_scope': 'face_alignment_controller_only_not_world_rigid_execution',
        'axes_valid': False, 'axes_check': 'axis0_not_parallel_to_any_face(0.866)',
        'strict_geometry': {'measurement_valid': True, 'signed_clearance_m': 0.0010000000474974513,
            'is_penetrating': False, 'penetration_depth_m': 0.0,
            'collision_tolerance_m': 1e-9, 'independent_ground_truth': False}}
    return {'source': 'independent_numeric_fixture', 'scene_revision': 'snapshot-revision',
        'unit': 'm', 'coordinate_frame': 'world', 'focal_id': 'focal', 'reference_id': 'reference',
        'measurement': measurement, 'rigid_frame': copy.deepcopy(rigid), 'rigid_frame_valid': True,
        'scene_contacts': [{'object_id': 'reference', **copy.deepcopy(measurement)}],
        'objects': [{'object_id': 'focal', 'mark_label': '#B0001',
                     'bbox_min': [11.7, -7.25, 2.95], 'bbox_max': [12.3, -6.75, 3.05]}],
        'scene_memory': {'changes': {'added': ['focal'], 'removed': []}, 'stats': {'hits': 999}},
        'measurement_cache': {'hits': 1, 'misses': 0, 'execution_gate_uses_cache': False,
                              'stats': {'accounted_bytes': 12345}},
        'unknown_objects': [], 'observation_status': 'complete',
        'scene_assessment': {'status': 'not_evaluated', 'scope': 'all_scene_objects',
                             'unknown_object_ids': [], 'reason_codes': ['scene_execution_not_evaluated_by_observation']},
        'collision_policy': {'tolerance_m': 1e-9, 'scope': 'terminal_geometry_only',
                             'independent_ground_truth': False},
        'attention': {'decision': 'hold', 'reason_codes': ['image_not_requested']},
        'canvas': {'omitted': 'text_only_host_delivery'}}


def summary_fixture(facts=None, **changes):
    result = {'human_eye_live': 'observed', 'session_id': 'codex:host-session',
        'observation': json.dumps(facts_fixture() if facts is None else facts, ensure_ascii=True),
        'reason_codes': ['spatial_3d_observed'], 'task_intent': {'kind': 'spatial_3d'},
        'allow_action': None, 'delivery': 'text_only_hook_no_native_image',
        'execution_scope': 'terminal_geometry_only', 'inner_execution_gate_required': True}
    result.update(changes)
    return result


def project(summary, *, result=None, route=None):
    return compact_hook_summary(summary, result or {}, route or {},
                                correlation=CORRELATION, identity=IDENTITY)


class RecordingService:
    def __init__(self, value):
        self.config = {'enabled': True}
        self.value, self.calls, self.records = value, [], []

    def describe_runtime(self):
        return copy.deepcopy(IDENTITY)

    def record_event(self, *args, **kwargs):
        self.records.append((args, kwargs))

    def observe(self, *args, **kwargs):
        self.calls.append(('observe', copy.deepcopy(args), copy.deepcopy(kwargs)))
        return self.value

    def preview_action(self, *args, **kwargs):
        self.calls.append(('preview_action', copy.deepcopy(args), copy.deepcopy(kwargs)))
        return self.value


def event(kind='UserPromptSubmit', **changes):
    value = {'hook_event_name': kind, 'session_id': 'host-session', 'turn_id': 'host-turn',
        'tool_use_id': 'host-call', 'prompt': '检查 Blender 场景中 part 与 base 的间隙，只观察，不移动。',
        'tool_name': SPATIAL_TRANSFORM,
        'tool_input': {'action': {'focal_id': 'part', 'reference_id': 'base',
                                  'translation': [0, 0, .001]}}}
    value.update(changes)
    return value


class HookContextTests(unittest.TestCase):
    def assert_json_identical(self, actual, expected, path='#'):
        self.assertIs(type(actual), type(expected), path)
        if isinstance(expected, dict):
            self.assertEqual(set(actual), set(expected), path)
            for key in expected:
                self.assert_json_identical(actual[key], expected[key], path + '/' + key)
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected), path)
            for index, item in enumerate(expected):
                self.assert_json_identical(actual[index], item, path + '/' + str(index))
        elif isinstance(expected, float):
            self.assertEqual(actual.hex(), expected.hex(), path)
        else:
            self.assertEqual(actual, expected, path)

    def test_complete_facts_round_trip_and_only_named_diagnostics_are_omitted(self):
        facts = facts_fixture()
        compact = project(summary_fixture(facts))
        restored = expand_references(json.loads(encode_hook_summary(compact)))
        self.assert_json_identical(restored['observation'], expected_facts(facts))
        self.assertEqual(set(restored['context_projection']['omitted_diagnostics']), ALLOWED_OMISSIONS)
        self.assertIs(restored['context_projection']['execution_authority'], False)
        self.assertGreater(len(list(ref_values(compact))), 0)

    def test_references_escape_pointer_keys_and_resolve_array_paths(self):
        evidence = frame()
        facts = {'~axis/证据': [evidence], 'other': {'repeated': copy.deepcopy(evidence)}}
        compact = project(summary_fixture(facts))
        self.assertIn('#/observation/~0axis~1证据/0', list(ref_values(compact)))
        self.assert_json_identical(expand_references(compact)['observation'], facts)

    def test_object_id_reference_sibling_adds_identity_without_losing_measurement(self):
        facts = facts_fixture()
        compact = project(summary_fixture(facts))
        contact = compact['observation']['scene_contacts'][0]
        self.assertEqual(set(contact), {'$ref', 'object_id'})
        self.assertEqual(contact['$ref'], '#/observation/measurement')
        self.assertEqual(contact['object_id'], 'reference')
        self.assert_json_identical(expand_references(compact)['observation'], expected_facts(facts))

    def test_null_false_zero_integer_float_and_negative_zero_stay_distinct(self):
        facts = {'values': [None, False, True, 0, 0.0, -0.0, 1, 1.0,
                           0.0010000000474974513, 1e-300, 1e300, 9007199254740993]}
        self.assert_json_identical(expand_references(project(summary_fixture(facts)))['observation'], facts)

    def test_no_list_is_replaced_by_reference_and_order_is_preserved(self):
        items = list(range(100))
        facts = {'first': items, 'second': copy.deepcopy(items)}
        compact = project(summary_fixture(facts))
        self.assertIsInstance(compact['observation']['first'], list)
        self.assertIsInstance(compact['observation']['second'], list)
        self.assert_json_identical(expand_references(compact)['observation'], facts)

    def test_only_two_top_level_stats_paths_can_be_removed(self):
        facts = facts_fixture()
        facts['stats'] = {'clearance_m': .002}
        facts['measurement']['stats'] = {'numeric_evidence': 0.0010000000474974513}
        facts['scene_memory']['details'] = {'stats': {'must_remain': True}}
        restored = expand_references(project(summary_fixture(facts)))['observation']
        self.assert_json_identical(restored, expected_facts(facts))

    def test_inputs_are_unchanged_and_output_has_no_mutable_aliases(self):
        summary = summary_fixture()
        result = {'host_execution': {'supported': False, 'reasons': [{'reason': 'unsupported'}]}}
        route = {'scene_revision': 'snapshot', 'rigid_frame': frame(False)}
        values = [summary, result, route, CORRELATION, IDENTITY]
        before = copy.deepcopy(values)
        compact = project(summary, result=result, route=route)
        self.assertEqual(values, before)
        compact['host_execution']['reasons'][0]['reason'] = 'mutated-output'
        compact['correlation']['turn_id'] = 'mutated-output'
        compact['runtime_identity']['build_id'] = 'mutated-output'
        self.assertEqual(values, before)

    def test_unicode_and_control_characters_remain_data(self):
        facts = {'name': '孔/轴🧿与基座~配合', 'detail': '第一行\n第二行\t"\\',
                 'repeat': [{'name': '空间感知' * 80}, {'name': '空间感知' * 80}]}
        encoded = encode_hook_summary(project(summary_fixture(facts)))
        self.assert_json_identical(expand_references(json.loads(encoded))['observation'], facts)

    def test_partial_keeps_all_unknown_objects_and_scope_separate_from_satisfied_goal(self):
        facts = facts_fixture()
        facts['unknown_objects'] = [{'object_id': 'unknown-' + str(i),
            'geometry_support': 'unknown', 'reason_codes': ['open_surface']} for i in range(100)]
        facts['scene_assessment'].update(status='unknown', unknown_object_ids=[
            item['object_id'] for item in facts['unknown_objects']])
        result = {'observation_status': 'partial', 'scene_assessment': facts['scene_assessment'],
            'action_eligibility': {'status': 'blocked', 'execution_authority': False},
            'pair_goal': {'status': 'satisfied', 'scope': 'known_mesh_pair'},
            'allow_action': False, 'requires_reobserve': True}
        restored = expand_references(project(summary_fixture(facts, allow_action=False), result=result))
        self.assert_json_identical(restored['observation'], expected_facts(facts))
        self.assertEqual(len(restored['scene_assessment']['unknown_object_ids']), 100)
        self.assertEqual(restored['pair_goal']['status'], 'satisfied')
        self.assertEqual(restored['action_eligibility']['status'], 'blocked')
        self.assertIs(restored['allow_action'], False)

    def test_exact_lower_bound_penetration_and_unknown_contracts_are_not_collapsed(self):
        facts = facts_fixture()
        facts['scene_contacts'] += [
            {'object_id': 'far', 'measurement_kind': 'lower_bound', 'clearance_exact': False,
             'signed_clearance_m': None, 'clearance_lower_bound_m': 10.00000000001,
             'method': 'outward_aabb_linf_lower_bound'},
            {'object_id': 'touching', 'measurement_kind': 'certified_penetration',
             'clearance_exact': False, 'signed_clearance_m': -.000000004,
             'clearance_scope': 'certified_separating_translation_not_global_minimum'},
            {'object_id': 'unknown', 'measurement_kind': 'unknown', 'clearance_exact': False,
             'signed_clearance_m': None, 'is_penetrating': None}]
        restored = expand_references(project(summary_fixture(facts)))['observation']
        self.assert_json_identical(restored, expected_facts(facts))

    def test_budget_and_rigid_frame_gate_fields_are_kept_with_top_level_precedence(self):
        budget = {'within_budget': False, 'reason_codes': ['sat_projection_work_limit'],
            'estimates': {'largest_sat_projection_elements': 2081280},
            'limits': {'sat_projection_elements': 2000000}}
        result = {'geometry_work_budget': budget, 'rigid_frame_valid': False,
                  'rigid_frame': frame(False), 'requires_reobserve': True,
                  'source_check': {'supported': False, 'reason_codes': ['missing_source']}}
        route = {'geometry_work_budget': {'must_not_win': True}, 'rigid_frame_valid': True}
        restored = expand_references(project(summary_fixture(allow_action=False), result=result, route=route))
        for key, value in result.items():
            self.assert_json_identical(restored[key], value)

    def test_route_only_gate_fields_are_not_lost(self):
        route = {'geometry_work_budget': {'within_budget': False, 'reason_codes': ['dense_work_limit']},
                 'rigid_frame_valid': False, 'rigid_frame': frame(False), 'requires_reobserve': True}
        restored = expand_references(project(summary_fixture(allow_action=False), route=route))
        for key, value in route.items():
            self.assert_json_identical(restored[key], value)

    def test_missing_context_never_manufactures_measurement_or_action_success(self):
        for raw in (None, False, 0, {}, []):
            with self.subTest(raw=raw):
                compact = project(summary_fixture(observation=raw, human_eye_live='blocked', allow_action=False))
                restored = expand_references(compact)
                self.assertNotEqual(restored['context_projection']['observation_format'], 'structured')
                self.assertEqual(restored['human_eye_live'], 'blocked')
                self.assertIs(restored['allow_action'], False)
                self.assertIs(restored['context_projection']['execution_authority'], False)
                self.assertNotIn('measurement_valid', restored)

    def test_invalid_context_is_explicit_verbatim_not_parsed_success(self):
        for raw in ('broken-json', '', '[1,2,3]', 'null', '{"clearance":NaN}', '{"clearance":Infinity}'):
            with self.subTest(raw=raw):
                restored = expand_references(project(summary_fixture(observation=raw, allow_action=False)))
                self.assertEqual(restored['observation'], raw)
                self.assertEqual(restored['context_projection']['observation_format'], 'verbatim_unparsed')
                self.assertIs(restored['allow_action'], False)

    def test_duplicate_measurement_keys_are_not_silently_promoted_to_structured_facts(self):
        raw = '{"signed_clearance_m":0.002,"signed_clearance_m":0.5}'
        compact = project(summary_fixture(observation=raw, allow_action=False))
        self.assertNotEqual(compact['context_projection']['observation_format'], 'structured')
        self.assertEqual(compact['observation'], raw)

    def test_literal_ref_data_cannot_change_meaning_during_reference_expansion(self):
        facts = {'ordinary': {'$ref': '#/observation/actual'}, 'actual': {'distance_m': .002}}
        compact = project(summary_fixture(facts))
        restored = expand_references(compact)['observation']
        if isinstance(restored, str):
            restored = json.loads(restored)
        self.assert_json_identical(restored, facts)
        self.assertEqual(compact['context_projection']['reference_encoding'], 'disabled_reserved_key')

    def test_reserved_ref_in_non_observation_field_disables_all_generated_references(self):
        facts = facts_fixture()
        result = {'host_execution': {'supported': False, 'operator_data': {'$ref': '#/foreign'}}}
        compact = project(summary_fixture(facts), result=result)
        self.assertEqual(compact['context_projection']['reference_encoding'], 'disabled_reserved_key')
        restored = expand_references(compact)
        self.assert_json_identical(restored['host_execution'], result['host_execution'])
        self.assert_json_identical(restored['observation'], expected_facts(facts))
        self.assertEqual(list(ref_values(compact)), ['#/foreign'])

    def test_real_round02_facts_and_floats_round_trip_with_40_percent_byte_reduction(self):
        if not ROUND02.is_file():
            self.skipTest('Optional historical Round02 evidence is not in this test environment')
        raw = ROUND02.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), ROUND02_SHA256)
        summary = json.loads(raw)
        facts = json.loads(summary['observation'])
        self.assertEqual(facts['measurement']['signed_clearance_m'], 0.0010000000474974513)
        result = {key: copy.deepcopy(summary[key]) for key in SCOPED if key in summary}
        route = {key: facts[key] for key in ('scene_revision', 'rigid_frame_valid', 'rigid_frame') if key in facts}
        compact = project(summary, result=result, route=route)
        encoded = encode_hook_summary(compact)
        restored = expand_references(json.loads(encoded))
        self.assert_json_identical(restored['observation'], expected_facts(facts))
        for key in summary:
            if key != 'observation':
                self.assert_json_identical(restored[key], summary[key])
        old_bytes = len(json.dumps(summary, ensure_ascii=True).encode('utf-8'))
        new_bytes = len(encoded.encode('utf-8'))
        self.assertLessEqual(new_bytes, old_bytes * .60, (old_bytes, new_bytes))
        self.assertEqual(hashlib.sha256(ROUND02.read_bytes()).hexdigest(), ROUND02_SHA256)


class HookWireContextTests(unittest.TestCase):
    @staticmethod
    def service_value(**changes):
        facts = facts_fixture()
        value = {'status': 'observed', 'allow_action': None,
            'routing': {'route': 'engine', 'context_text': json.dumps(facts),
                'scene_revision': 'snapshot-revision', 'observation_id': 'machine-observation',
                'reason_codes': ['spatial_3d_observed']}}
        value.update(changes)
        return value

    def test_wire_unicode_context_is_one_json_string_with_structured_observation(self):
        value = self.service_value()
        facts = facts_fixture()
        facts['name'] = '三维模型🧿'
        value['routing']['context_text'] = json.dumps(facts)
        output = route_live_hook(event(), RecordingService(value), invocation_source='manual_probe')
        wire = json.loads(json.dumps(output, ensure_ascii=True))
        context = expand_references(json.loads(wire['hookSpecificOutput']['additionalContext']))
        self.assertEqual(context['observation']['name'], '三维模型🧿')
        self.assertIsInstance(context['observation'], dict)

    def test_no_input_event_or_service_result_mutation_and_no_extra_service_calls(self):
        request, value = event(), self.service_value()
        before = copy.deepcopy((request, value))
        service = RecordingService(value)
        output = route_live_hook(request, service, invocation_source='manual_probe')
        self.assertEqual((request, value), before)
        self.assertEqual(service.calls, [('observe', ('codex:host-session',),
            {'task_instruction': request['prompt'], 'include_image': False})])
        self.assertNotIn('permissionDecision', output['hookSpecificOutput'])

    def test_pre_denial_does_not_repeat_the_full_observation_in_stdout(self):
        value = self.service_value(status='blocked', allow_action=False,
            reason_codes=['candidate_collision'], action_eligibility={'status': 'blocked',
                'execution_authority': False, 'reason_codes': ['candidate_collision']})
        facts = facts_fixture()
        facts['unique_large_evidence'] = 'UNIQUE_FULL_EVIDENCE_' + '0123456789' * 1000
        value['routing']['context_text'] = json.dumps(facts)
        service = RecordingService(value)
        output = route_live_hook(event('PreToolUse'), service, invocation_source='manual_probe')
        wire = json.dumps(output, ensure_ascii=True)
        hook = output['hookSpecificOutput']
        self.assertEqual(hook['permissionDecision'], 'deny')
        self.assertEqual(wire.count('UNIQUE_FULL_EVIDENCE_'), 1)
        self.assertNotIn('UNIQUE_FULL_EVIDENCE_', hook['permissionDecisionReason'])
        self.assertIn('candidate_collision', hook['permissionDecisionReason'])
        self.assertLess(len(hook['permissionDecisionReason']), len(hook['additionalContext']) / 4)
        self.assertEqual(len(service.calls), 1)

    def test_pre_allows_no_permission_override_and_keeps_preview_non_authorizing(self):
        value = self.service_value(status='preview', allow_action=True,
            action_eligibility={'status': 'eligible_preview', 'execution_authority': False,
                                'reason_codes': ['preview_only_fresh_execution_gate_required']})
        service = RecordingService(value)
        output = route_live_hook(event('PreToolUse'), service, invocation_source='manual_probe')
        hook = output['hookSpecificOutput']
        context = expand_references(json.loads(hook['additionalContext']))
        self.assertNotIn('permissionDecision', hook)
        self.assertIs(context['allow_action'], True)
        self.assertIs(context['action_eligibility']['execution_authority'], False)
        self.assertIs(context['inner_execution_gate_required'], True)
        self.assertEqual(service.calls[0][2], {'include_image': False})

    def test_budget_rejection_survives_through_actual_hook_envelope(self):
        value = self.service_value(status='blocked', allow_action=False,
            reason_codes=['geometry_resource_limit'])
        budget = {'within_budget': False, 'reason_codes': ['sat_projection_work_limit'],
            'estimates': {'largest_sat_projection_elements': 2081280},
            'limits': {'sat_projection_elements': 2000000}}
        value['routing'].update(route='blocked', geometry_work_budget=budget,
            context_text=json.dumps({'human_eye_status': 'blocked', 'reason': 'geometry_resource_limit', 'detail': ''}))
        output = route_live_hook(event('PreToolUse'), RecordingService(value), invocation_source='manual_probe')
        context = expand_references(json.loads(output['hookSpecificOutput']['additionalContext']))
        self.assertEqual(context['geometry_work_budget'], budget)
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_overflow_json_float_cannot_escape_as_nonfinite_structured_success(self):
        value = self.service_value(status='blocked', allow_action=False)
        value['routing']['context_text'] = '{"signed_clearance_m":1e999}'
        output = route_live_hook(event('PreToolUse'), RecordingService(value), invocation_source='manual_probe')
        hook = output['hookSpecificOutput']
        self.assertEqual(hook['permissionDecision'], 'deny')
        self.assertNotIn('Infinity', json.dumps(output))

    def test_missing_and_invalid_service_context_never_overrides_denial(self):
        for raw in (None, '', 'broken', '[1,2]', {'not': 'a JSON text'}):
            with self.subTest(raw=raw):
                value = self.service_value(status='blocked', allow_action=False,
                    reason_codes=['geometry_unknown'])
                value['routing']['context_text'] = raw
                output = route_live_hook(event('PreToolUse'), RecordingService(value), invocation_source='manual_probe')
                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                context = json.loads(output['hookSpecificOutput']['additionalContext'])
                self.assertIs(context['allow_action'], False)

    def test_post_stays_empty_without_service_work_even_for_untrusted_success_claim(self):
        service = RecordingService(self.service_value())
        self.assertEqual(route_live_hook(event('PostToolUse', tool_response={'verified': True}), service), {})
        self.assertEqual(service.calls, [])

    def test_real_mutable_host_observation_and_preview_capture_only_once_each(self):
        from human_eye_plugin.live_service import LiveSpatialService
        from verification.test_host_runtime import MutableHost

        class CapturedHost(MutableHost):
            def capture_scene(self):
                if self.in_transaction:
                    return super().capture_scene()
                with self.transaction():
                    return super().capture_scene()

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / 'live.json'
            config.write_text(json.dumps({'schema_version': '1.0', 'project_root': str(ROOT),
                'enabled': True, 'state_file': 'state.json', 'audit_file': 'audit.jsonl',
                'quad_size': 64, 'max_sessions': 4}), encoding='utf-8')
            host = CapturedHost()
            host.scene['host_execution'] = {'schema_version': '1.0', 'operation': 'rigid_transform',
                'supported': True, 'scope': 'independent_static_rigid_meshes', 'reasons': []}
            service = LiveSpatialService(config, host=host, production_mode=True)
            before = copy.deepcopy(host.scene)
            prompt = route_live_hook(event(), service, invocation_source='manual_probe')
            self.assertEqual(host.captures, 1)
            context = expand_references(json.loads(prompt['hookSpecificOutput']['additionalContext']))
            self.assertEqual(context['observation_status'], 'complete')
            self.assertAlmostEqual(context['observation']['measurement']['signed_clearance_m'], .1)
            preview = route_live_hook(event('PreToolUse'), service, invocation_source='manual_probe')
            self.assertNotIn('permissionDecision', preview['hookSpecificOutput'])
            self.assertEqual(host.captures, 2)
            self.assertEqual(host.calls, 0)
            self.assertEqual(host.scene, before)
            state = json.loads((directory / 'state.json').read_text(encoding='utf-8'))
            self.assertIsNone(state['inflight'])
            self.assertIsNone(state['runtime']['quarantine'])


if __name__ == '__main__':
    unittest.main()
