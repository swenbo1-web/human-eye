"""Unavailable hook observations are data, never cached geometry or permission.

All hooks here are explicit in-memory simulations. These tests do not prove a
live desktop hook fired or connect to Blender.
"""
from contextlib import contextmanager
import copy
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import human_eye_hook as bootstrap
from human_eye_plugin import live_hooks
from human_eye_plugin.blender_process import HostTransportError
from human_eye_plugin.live_service import RequestBudgetError, StateBindingError
from human_eye_plugin.telemetry import current_trace, span


SPATIAL = '检查 Blender 中蓝色零件与灰色底座的间隙，只观察，不移动。'


def event(kind='UserPromptSubmit', prompt=SPATIAL, **changes):
    result = {'hook_event_name': kind, 'session_id': 'unavailable-contract',
              'turn_id': 'test-turn', 'tool_use_id': 'test-tool', 'prompt': prompt,
              'tool_name': live_hooks.SPATIAL_TRANSFORM,
              'tool_input': {'action': {'focal_id': 'part', 'reference_id': 'base',
                                        'translation': [0, 0, -.003]}}}
    result.update(changes)
    return result


def reply(answer, question='请选择下一步'):
    items = [{'questionItemId': json.dumps(['request_user_input_async', 'call_contract', 0]),
              'question': question, 'answer': answer}]
    return '<send_user_message_question_reply>' + json.dumps(items, ensure_ascii=False) + '</send_user_message_question_reply>'


class HookService:
    def __init__(self, error=None):
        self.config = {'enabled': True, 'observe_on_prompt': True}
        self.error = HostTransportError('untrusted host text') if error is None else error
        self.calls = []
        self.records = []
        self.audit_failure = False
        self.stale_scene = {'scene_revision': 'stale-r1', 'signed_clearance_m': 9.25,
                            'point_a_world': [999, 888, 777]}

    def describe_runtime(self):
        return {'implementation_revision': 'test-local-runtime', 'build_id': 'test-build',
                'source_kind': 'test-double', 'production_mode': False}

    def record_event(self, name, **fields):
        if self.audit_failure:
            raise OSError('audit offline')
        self.records.append((name, copy.deepcopy(fields)))

    def observe(self, *args, **kwargs):
        self.calls.append(('observe', args, kwargs))
        trace = current_trace()
        if trace is None:
            raise self.error
        with span('service.observe', kind='cpu'):
            with span('host.capture', kind='host'):
                raise self.error

    def preview_action(self, *args, **kwargs):
        self.calls.append(('preview', args, kwargs))
        raise self.error


@contextmanager
def no_trace(*args, **kwargs):
    yield None


class PartialTrace:
    def __init__(self):
        self.outcomes = []

    def annotate(self, **fields):
        raise RuntimeError('ancillary annotation failure')

    def set_outcome(self, value):
        self.outcomes.append(value)

    @property
    def trace_id(self):
        raise RuntimeError('ancillary identifier failure')


class HookUnavailableFeedbackTests(unittest.TestCase):
    def run_hook(self, value=None, service=None, **kwargs):
        service = service or HookService()
        output = live_hooks.route_live_hook(value or event(), service, **kwargs)
        return service, output

    def summary(self, output):
        return json.loads(output['hookSpecificOutput']['additionalContext'])

    def records(self, service, name):
        return [fields for record_name, fields in service.records if record_name == name]

    def test_transport_failure_is_explicit_unavailable_and_does_not_deny_chat(self):
        service, output = self.run_hook()
        self.assertEqual(output['hookSpecificOutput']['hookEventName'], 'UserPromptSubmit')
        self.assertNotIn('permissionDecision', output['hookSpecificOutput'])
        self.assertNotIn('permissionDecisionReason', output['hookSpecificOutput'])
        summary = self.summary(output)
        self.assertEqual(summary['human_eye_live'], 'unavailable')
        self.assertEqual(summary['observation_status'], 'unavailable')
        self.assertEqual(summary['reason_codes'], ['host_observation_unavailable'])
        self.assertTrue(summary['requires_reobserve'])
        self.assertEqual([call[0] for call in service.calls], ['observe'])

    def test_failure_contains_no_cached_measurement_witness_or_scene_revision(self):
        # A real correlation identifier may contain the same digits as a stale
        # witness. Check semantic fields, not substrings of unrelated UUIDs.
        identifier = '916513999905406c9655d5b73fb0965a'
        with patch('human_eye_plugin.telemetry.uuid.uuid4', return_value=SimpleNamespace(hex=identifier)):
            service, output = self.run_hook()
        summary = self.summary(output)
        self.assertEqual(summary['correlation']['request_id'], identifier)
        self.assertEqual(summary['correlation']['trace_id'], identifier)
        semantic = copy.deepcopy(summary)
        semantic.pop('correlation')
        pending = [semantic]
        forbidden_fields = {'signed_clearance_m', 'point_a_world', 'scene_revision',
                            'observation_id', 'measurement', 'clearance_state'}
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                self.assertTrue(forbidden_fields.isdisjoint(node))
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, str):
                self.assertNotIn('stale-r1', node)
            elif type(node) in (int, float):
                self.assertNotIn(node, (9.25, 999, 888, 777))
        self.assertEqual(summary['scene_assessment']['status'], 'unknown')
        self.assertEqual(service.stale_scene['scene_revision'], 'stale-r1')

    def test_forged_event_correlation_cannot_forward_cached_geometry(self):
        service = HookService()
        forged = event(correlation=copy.deepcopy(service.stale_scene),
                       measurement={'signed_clearance_m': 9.25},
                       scene_revision='stale-r1', point_a_world=[999, 888, 777])
        _, output = self.run_hook(forged, service)
        summary = self.summary(output)
        self.assertEqual(set(summary['correlation']),
                         {'turn_id', 'tool_use_id', 'trace_id', 'request_id', 'request_origin'})
        self.assertEqual(summary['correlation']['turn_id'], 'test-turn')
        self.assertEqual(summary['scene_assessment']['status'], 'unknown')
        self.assertNotIn('measurement', summary)
        self.assertNotIn('scene_revision', summary)
        self.assertNotIn('stale-r1', json.dumps(summary, ensure_ascii=False))

    def test_unavailable_never_grants_execution_or_retry(self):
        _, output = self.run_hook()
        summary = self.summary(output)
        self.assertIsNone(summary['allow_action'])
        self.assertFalse(summary['execution_authority'])
        self.assertFalse(summary['retry_authorized'])
        self.assertEqual(summary['execution_status'], 'not_requested')
        self.assertEqual(summary['action_eligibility']['status'], 'blocked')
        self.assertFalse(summary['action_eligibility']['execution_authority'])
        self.assertTrue(summary['inner_execution_gate_required'])

    def test_output_is_static_bounded_and_does_not_forward_transport_body(self):
        values = []
        for body in ('short-secret', 'SECRET_RAW_ERROR_' * 50000):
            service, output = self.run_hook(service=HookService(HostTransportError(body, ('diagnostic-secret',))))
            text = output['hookSpecificOutput']['additionalContext']
            self.assertLess(len(text), 4096)
            self.assertNotIn(body, text)
            self.assertNotIn('diagnostic-secret', text)
            summary = self.summary(output)
            summary.pop('correlation')
            values.append(summary)
            self.assertEqual(len(service.calls), 1)
        self.assertEqual(values[0], values[1])

    def test_exception_string_is_not_evaluated(self):
        class ExplosiveMessage(HostTransportError):
            def __str__(self):
                raise AssertionError('Untrusted exception text must not be read')
        _, output = self.run_hook(service=HookService(ExplosiveMessage('hidden')))
        self.assertEqual(self.summary(output)['human_eye_live'], 'unavailable')

    def test_transport_type_does_not_claim_window_closed_or_account_switched(self):
        _, output = self.run_hook()
        text = output['hookSpecificOutput']['additionalContext'].lower()
        for cause in ('window closed', 'blender is closed', 'account', 'login', 'signed out'):
            self.assertNotIn(cause, text)

    def test_outer_trace_is_non_success_and_nested_capture_error_retained(self):
        service, _ = self.run_hook()
        trace = self.records(service, 'request_trace')[0]['trace']
        self.assertEqual(trace['operation'], 'hook.prompt')
        self.assertEqual(trace['outcome'], 'host_observation_unavailable')
        self.assertEqual(trace['annotations']['status'], 'host_observation_unavailable')
        self.assertEqual(trace['telemetry_issues'], [])
        for name in ('service.observe', 'host.capture'):
            nested = [span for span in trace['spans'] if span['name'] == name]
            self.assertEqual(len(nested), 1)
            self.assertEqual(nested[0]['outcome'], 'error')
            self.assertEqual(nested[0]['error_type'], 'HostTransportError')
            self.assertGreaterEqual(nested[0]['duration_ns'], 0)

    def test_typed_operational_error_and_original_prompt_fingerprint_are_retained(self):
        service, output = self.run_hook()
        error = self.records(service, 'host_hook_error')[0]
        trace = self.records(service, 'request_trace')[0]
        self.assertEqual(error['error_type'], 'HostTransportError')
        self.assertEqual(error['status'], 'host_observation_unavailable')
        self.assertEqual(error['prompt_input'], trace['prompt_input'])
        self.assertEqual(self.summary(output)['correlation']['trace_id'], trace['trace']['trace_id'])
        self.assertEqual(self.summary(output)['correlation']['turn_id'], 'test-turn')
        self.assertEqual(error['invocation_source'], 'hook_command')

    def test_manual_probes_remain_labelled_manual(self):
        service, output = self.run_hook(invocation_source='manual_probe')
        self.assertEqual(self.summary(output)['correlation']['request_origin'], 'manual_probe')
        self.assertTrue(all(fields['invocation_source'] == 'manual_probe' for _, fields in service.records))

    def test_audit_write_failure_cannot_remove_unavailable_context(self):
        service = HookService()
        service.audit_failure = True
        _, output = self.run_hook(service=service)
        self.assertEqual(self.summary(output)['human_eye_live'], 'unavailable')
        self.assertEqual([call[0] for call in service.calls], ['observe'])

    def test_trace_construction_failure_cannot_remove_unavailable_context(self):
        with patch.object(live_hooks, 'best_effort_trace', no_trace):
            _, output = self.run_hook()
        summary = self.summary(output)
        self.assertEqual(summary['human_eye_live'], 'unavailable')
        self.assertIsNone(summary['correlation']['trace_id'])
        self.assertIsNone(summary['correlation']['request_id'])

    def test_partial_trace_cannot_change_disposition(self):
        partial = PartialTrace()
        @contextmanager
        def factory(*args, **kwargs):
            yield partial
        with patch.object(live_hooks, 'best_effort_trace', factory):
            _, output = self.run_hook()
        summary = self.summary(output)
        self.assertEqual(summary['human_eye_live'], 'unavailable')
        self.assertEqual(partial.outcomes, ['host_observation_unavailable'])
        self.assertIsNone(summary['correlation']['trace_id'])
        self.assertIsNone(summary['correlation']['request_id'])

    def test_broken_outcome_method_cannot_change_disposition(self):
        partial = PartialTrace()
        partial.set_outcome = lambda value: (_ for _ in ()).throw(RuntimeError('trace offline'))
        @contextmanager
        def factory(*args, **kwargs):
            yield partial
        with patch.object(live_hooks, 'best_effort_trace', factory):
            _, output = self.run_hook()
        self.assertEqual(self.summary(output)['human_eye_live'], 'unavailable')

    def test_runtime_descriptor_failure_does_not_reuse_event_identity(self):
        service = HookService()
        with patch.object(service, 'describe_runtime', side_effect=ValueError('identity unavailable')):
            _, output = self.run_hook(event(runtime_identity={'build_id': 'attacker-build'}), service)
        summary = self.summary(output)
        self.assertIsNone(summary['runtime_identity'])
        self.assertNotIn('attacker-build', output['hookSpecificOutput']['additionalContext'])

    def test_plain_general_unknown_and_optout_prompts_do_not_read_host(self):
        for prompt in ('继续', '解释缓存算法。', '不要调用引擎，检查 Blender 中零件间隙。'):
            with self.subTest(prompt=prompt):
                service, output = self.run_hook(event(prompt=prompt))
                self.assertEqual(output, {})
                self.assertEqual(service.calls, [])
                self.assertEqual(self.records(service, 'host_hook_error'), [])

    def test_spatial_question_does_not_override_negative_structured_answer(self):
        service, output = self.run_hook(event(prompt=reply('继续', question=SPATIAL)))
        self.assertEqual(output, {})
        self.assertEqual(service.calls, [])

    def test_structured_spatial_answer_reaches_same_unavailable_contract(self):
        service, output = self.run_hook(event(prompt=reply(SPATIAL)))
        self.assertEqual(self.summary(output)['human_eye_live'], 'unavailable')
        self.assertEqual(service.calls[0][2]['task_instruction'], SPATIAL)
        self.assertEqual(self.records(service, 'host_hook_error')[0]['prompt_input']['extraction'], 'answers_only')

    def test_explicit_trusted_spatial_metadata_uses_the_same_unavailable_contract(self):
        service, output = self.run_hook(event(prompt='continue', task_kind='spatial_3d'))
        self.assertEqual(self.summary(output)['task_intent']['source'], 'explicit_host_metadata')
        self.assertEqual([call[0] for call in service.calls], ['observe'])

    def test_claude_plain_spatial_prompt_is_nonblocking_unavailable(self):
        service, output = self.run_hook(agent='claude')
        self.assertEqual(self.summary(output)['human_eye_live'], 'unavailable')
        self.assertEqual(self.summary(output)['session_id'], 'claude:unavailable-contract')
        self.assertEqual([call[0] for call in service.calls], ['observe'])

    def test_pretool_transport_error_still_denies_without_observe_or_mutation(self):
        service, output = self.run_hook(event('PreToolUse'))
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual([call[0] for call in service.calls], ['preview'])
        self.assertEqual(self.records(service, 'request_trace')[0]['trace']['outcome'], 'hook_error')

    def test_posttool_keeps_original_delivery_without_recapture(self):
        service, output = self.run_hook(event('PostToolUse'))
        self.assertEqual(output, {})
        self.assertEqual(service.calls, [])
        self.assertEqual(self.records(service, 'request_trace')[0]['trace']['outcome'], 'duplicate_delivery_omitted')

    def test_state_binding_error_preserves_recovery_contract_for_prompt_and_pretool(self):
        for kind in ('UserPromptSubmit', 'PreToolUse'):
            error = StateBindingError('stale_configuration_snapshot', disk_configuration='matches_persisted_state')
            _, output = self.run_hook(event(kind), HookService(error))
            summary = self.summary(output)
            self.assertEqual(summary['human_eye_live'], 'blocked')
            self.assertEqual(summary['code'], error.code)
            self.assertEqual(summary['recovery'], error.recovery)
            self.assertEqual(summary['reason_codes'], error.reason_codes)
            self.assertEqual('permissionDecision' in output['hookSpecificOutput'], kind == 'PreToolUse')

    def test_budget_error_preserves_refusal_diagnostics_for_prompt_and_pretool(self):
        for kind in ('UserPromptSubmit', 'PreToolUse'):
            for budget_kind in ('busy', 'expired'):
                error = RequestBudgetError(budget_kind, 'lock_wait')
                _, output = self.run_hook(event(kind), HookService(error))
                summary = self.summary(output)
                for key, value in error.to_error_fields().items():
                    self.assertEqual(summary[key], value)
                self.assertEqual('permissionDecision' in output['hookSpecificOutput'], kind == 'PreToolUse')

    def test_handled_state_and_budget_refusals_are_not_labelled_completed(self):
        for error, outcome in ((StateBindingError('state_binding_cause_unconfirmed'), 'hook_state_binding_refused'),
                               (RequestBudgetError('busy', 'lock_wait'), 'hook_request_budget_exhausted')):
            service, _ = self.run_hook(service=HookService(error))
            self.assertEqual(self.records(service, 'request_trace')[0]['trace']['outcome'], outcome)

    def test_untyped_error_retains_conservative_empty_prompt_and_error_outcome(self):
        service, output = self.run_hook(service=HookService(ConnectionError('not a typed host failure')))
        self.assertEqual(output, {})
        self.assertEqual(self.records(service, 'request_trace')[0]['trace']['outcome'], 'hook_error')

    def test_successful_observation_contract_is_unchanged(self):
        service = HookService()
        good = {'status': 'observed', 'routing': {'route': 'engine', 'engine_invoked': True,
                'scene_revision': 'fresh-r2', 'observation_id': 'fresh-o2',
                'context_text': json.dumps({'measurement': {'signed_clearance_m': .004}}),
                'reason_codes': ['spatial_3d_observed']}}
        with patch.object(service, 'observe', return_value=good):
            _, output = self.run_hook(service=service)
        summary = self.summary(output)
        self.assertEqual(summary['human_eye_live'], 'observed')
        self.assertEqual(summary['scene_revision'], 'fresh-r2')
        self.assertEqual(summary['observation']['measurement']['signed_clearance_m'], .004)

    def test_failure_delivery_never_claims_native_image_or_fresh_geometry(self):
        _, output = self.run_hook()
        summary = self.summary(output)
        self.assertEqual(summary['delivery'], 'text_only_hook_no_native_image')
        self.assertNotIn('image', summary)
        self.assertNotIn('observation', summary)
        self.assertNotIn('scene_revision', summary)

    def run_light_main(self, prompt):
        service = HookService()
        original_leaf = bootstrap._leaf
        helpers = original_leaf('agent_hooks')
        fake_helpers = SimpleNamespace(_reject_constant=helpers._reject_constant,
                                       _read_object=lambda path: {'enabled': True, 'observe_on_prompt': True})
        def leaf(name):
            return fake_helpers if name == 'agent_hooks' else original_leaf(name)
        def engine():
            return lambda value, config, agent='codex', probe=False: live_hooks.route_live_hook(
                value, service, agent=agent, invocation_source='manual_probe' if probe else 'hook_command')
        stdin = SimpleNamespace(buffer=io.BytesIO(json.dumps(event(prompt=prompt)).encode()))
        output = io.StringIO()
        with patch.object(bootstrap, '_leaf', side_effect=leaf), \
             patch.object(bootstrap, '_LightService', return_value=service), \
             patch.object(bootstrap, '_engine_entry', side_effect=engine), \
             patch.object(bootstrap.sys, 'stdin', stdin), patch.object(bootstrap.sys, 'stdout', output):
            code = bootstrap.main(['--config', 'in-memory-test-only', '--agent', 'codex',
                                   '--event', 'UserPromptSubmit', '--probe'])
        self.assertEqual(code, 0)
        return service, json.loads(output.getvalue())

    def test_light_main_and_heavy_entry_preserve_same_structured_failure_contract(self):
        prompt = reply(SPATIAL)
        service, light = self.run_light_main(prompt)
        _, heavy = self.run_hook(event(prompt=prompt), invocation_source='manual_probe')
        left, right = self.summary(light), self.summary(heavy)
        left.pop('correlation')
        right.pop('correlation')
        self.assertEqual(left, right)
        self.assertEqual(service.calls[0][2]['task_instruction'], SPATIAL)

    def test_light_main_negative_answer_stays_empty_without_host_read(self):
        service, output = self.run_light_main(reply('continue', question=SPATIAL))
        self.assertEqual(output, {})
        self.assertEqual(service.calls, [])


if __name__ == '__main__':
    unittest.main()
