"""Host prompt normalization contracts, not real host activation evidence.

All live-hook integration uses an in-memory service. The one subprocess check
uses a new temporary connector pointing at an unused, refusing test port.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import human_eye_hook as bootstrap
from human_eye_plugin.live_hooks import route_live_hook, SPATIAL_TRANSFORM
from human_eye_plugin.task_intent import classify_task_intent
from verification.test_live_hooks import HookService


OPEN = '<send_user_message_question_reply>'
CLOSE = '</send_user_message_question_reply>'
SPATIAL = '检查 Blender 测试场景中蓝色零件与灰色底座的间隙，只观察，不移动。'


def item(answer, index=0, *, question='Please choose a task.'):
    return {'questionItemId': json.dumps(['request_user_input_async', 'call_contract_01', index]),
            'question': question, 'answer': answer}


def envelope(items):
    return OPEN + '\n' + json.dumps(items, ensure_ascii=False) + '\n' + CLOSE


def event(prompt=SPATIAL, **fields):
    return {'hook_event_name': 'UserPromptSubmit', 'session_id': 'structured-contract',
            'turn_id': 'host-turn', 'tool_use_id': 'host-call', 'prompt': prompt, **fields}


class StructuredPromptBoundaryTests(unittest.TestCase):
    def extract(self, prompt, **fields):
        return bootstrap.host_prompt(event(prompt, **fields))

    def test_actual_reply_shape_extracts_human_answer_without_question(self):
        value = envelope([item(SPATIAL, question='A question with unrelated instructions.')])
        instruction, metadata = self.extract(value)
        self.assertEqual(instruction, SPATIAL)
        self.assertEqual(metadata['extraction'], 'answers_only')
        self.assertEqual(metadata['item_count'], 1)
        self.assertEqual(classify_task_intent(instruction)['kind'], 'spatial_3d')
        self.assertEqual(classify_task_intent(value)['kind'], 'unknown')

    def test_metadata_describes_original_prompt_without_any_body(self):
        value = envelope([item(SPATIAL, question='question-secret-2871')])
        _, metadata = self.extract(value)
        self.assertTrue(metadata['present'])
        self.assertEqual(metadata['type'], 'str')
        self.assertEqual(metadata['chars'], len(value))
        self.assertEqual(metadata['bytes'], len(value.encode('utf-8')))
        self.assertEqual(metadata['sha256'], hashlib.sha256(value.encode('utf-8')).hexdigest())
        serialized = json.dumps(metadata, ensure_ascii=False)
        self.assertNotIn('question-secret-2871', serialized)
        self.assertNotIn(SPATIAL, serialized)
        self.assertNotIn('call_contract_01', serialized)
        self.assertEqual(metadata['scope'], 'current_hook_event_prompt_only_no_history')

    def test_plain_prompts_and_invalid_nontext_preserve_original_value(self):
        for value in ('继续', SPATIAL, 'Read this screenshot.', '', None, 7, True, [], {}):
            with self.subTest(type=type(value).__name__):
                instruction, metadata = self.extract(value)
                self.assertEqual(instruction, value)
                self.assertEqual(metadata['present'], True)
                if not isinstance(value, str):
                    self.assertIsNone(metadata['sha256'])

    def test_missing_prompt_reports_absence_without_history(self):
        value = event()
        del value['prompt']
        value['messages'] = [{'role': 'user', 'text': SPATIAL}]
        instruction, metadata = bootstrap.host_prompt(value)
        self.assertEqual(instruction, '')
        self.assertFalse(metadata['present'])
        self.assertEqual(metadata['chars'], 0)

    def test_claude_and_nonprompt_events_do_not_unwrap(self):
        value = envelope([item(SPATIAL)])
        for agent, kind in [('claude', 'UserPromptSubmit'), ('codex', 'PreToolUse'),
                            ('codex', 'PostToolUse'), ('codex', 'Stop')]:
            with self.subTest(agent=agent, kind=kind):
                instruction, metadata = bootstrap.host_prompt(event(value, hook_event_name=kind), agent=agent)
                self.assertEqual(instruction, value)
                self.assertEqual(metadata['extraction'], 'not_applicable')

    def test_question_and_question_id_text_never_supply_spatial_intent(self):
        for answer in ('继续', 'No, leave it alone.', '', 'Read the photo text.'):
            with self.subTest(answer=answer):
                instruction, _ = self.extract(envelope([item(answer, question=SPATIAL)]))
                self.assertEqual(instruction, answer)
                self.assertNotEqual(classify_task_intent(instruction)['kind'], 'spatial_3d')

    def test_multiple_answers_keep_order_and_do_not_include_questions(self):
        answers = ['Explain a concept.', SPATIAL, 'No movement.']
        instruction, metadata = self.extract(envelope([item(v, i, question='ignored-question')
                                                       for i, v in enumerate(answers)]))
        self.assertEqual(instruction, '\n'.join(answers))
        self.assertEqual(metadata['item_count'], 3)
        self.assertNotIn('ignored-question', instruction)

    def test_engine_opt_out_in_any_answer_remains_effective(self):
        for answers in ([SPATIAL, 'Do not use Human-Eye engine.'],
                        ['不要调用人眼插件。', SPATIAL]):
            instruction, _ = self.extract(envelope([item(v, i) for i, v in enumerate(answers)]))
            self.assertNotEqual(classify_task_intent(instruction)['kind'], 'spatial_3d')

    def test_quoted_and_code_answers_are_not_promoted(self):
        for answer in ('"Measure the cube clearance in Blender."',
                       '```python\ninspect the part gap in Blender\n```',
                       '> Measure the part gap in Blender.'):
            instruction, _ = self.extract(envelope([item(answer)]))
            self.assertEqual(instruction, answer)
            self.assertNotEqual(classify_task_intent(instruction)['kind'], 'spatial_3d')

    def test_answer_is_not_recursively_unwrapped(self):
        nested = envelope([item(SPATIAL)])
        instruction, metadata = self.extract(envelope([item(nested)]))
        self.assertEqual(instruction, nested)
        self.assertEqual(metadata['item_count'], 1)
        self.assertNotEqual(classify_task_intent(instruction)['kind'], 'spatial_3d')

    def test_quoted_fenced_and_prefixed_envelopes_are_rejected(self):
        value = envelope([item(SPATIAL)])
        for invalid in ('```json\n' + value + '\n```', '`' + value + '`',
                        '"' + value + '"', '> ' + value.replace('\n', '\n> '),
                        'Example: ' + value, value + '\nExplanation.', value + value):
            with self.subTest(prefix=invalid[:20]):
                instruction, metadata = self.extract(invalid)
                self.assertEqual(instruction, '')
                self.assertEqual(metadata['extraction'], 'rejected')

    def test_outer_whitespace_is_permitted(self):
        instruction, _ = self.extract(' \r\n' + envelope([item(SPATIAL)]) + '\t\n')
        self.assertEqual(instruction, SPATIAL)

    def test_schema_rejects_nonarray_empty_or_nonobject_items(self):
        for value in ({}, [], [None], ['answer'], [1], [True]):
            with self.subTest(value=value):
                instruction, metadata = self.extract(envelope(value))
                self.assertEqual(instruction, '')
                self.assertEqual(metadata['extraction'], 'rejected')

    def test_every_field_is_required_and_unknown_fields_are_rejected(self):
        original = item(SPATIAL)
        invalids = []
        for key in original:
            altered = copy.deepcopy(original)
            del altered[key]
            invalids.append(altered)
        altered = copy.deepcopy(original)
        altered['task_kind'] = 'spatial_3d'
        invalids.append(altered)
        for value in invalids:
            with self.subTest(keys=list(value)):
                instruction, _ = self.extract(envelope([value]))
                self.assertEqual(instruction, '')

    def test_all_item_fields_must_be_strings_including_nested_answer(self):
        for key in ('questionItemId', 'question', 'answer'):
            for value in (None, True, 5, ['Measure part gap'], {'answer': SPATIAL}):
                with self.subTest(key=key, type=type(value).__name__):
                    altered = item(SPATIAL)
                    altered[key] = value
                    self.assertEqual(self.extract(envelope([altered]))[0], '')

    def test_duplicate_json_keys_are_rejected(self):
        value = json.dumps(item('continue'), ensure_ascii=False)
        for body in ('[' + value[:-1] + ',"answer":' + json.dumps(SPATIAL) + '}]',
                     '[{"questionItemId":"bad","questionItemId":"other","question":"q","answer":"x"}]'):
            instruction, metadata = self.extract(OPEN + body + CLOSE)
            self.assertEqual(instruction, '')
            self.assertEqual(metadata['reason'], 'invalid_reply_json')

    def test_nonfinite_and_malformed_json_are_rejected(self):
        for body in ('[NaN]', '[Infinity]', '[-Infinity]', '[1e10000]', '[', '[{},]',
                     '{"answer":"x"}', '[[[[[[[[[[', '[] trailing'):
            with self.subTest(body=body[:20]):
                self.assertEqual(self.extract(OPEN + body + CLOSE)[0], '')

    def test_deep_json_does_not_escape_as_an_exception(self):
        body = '[' * 2000 + '0' + ']' * 2000
        instruction, metadata = self.extract(OPEN + body + CLOSE)
        self.assertEqual(instruction, '')
        self.assertEqual(metadata['extraction'], 'rejected')

    def test_question_identity_is_strict_async_call_with_nonnegative_integer_index(self):
        bad = (None, {}, [], ['request_user_input', 'call_x', 0],
               ['request_user_input_async', 'not_a_call', 0],
               ['request_user_input_async', 'call_', 0],
               ['request_user_input_async', 'call_x\n', 0],
               ['request_user_input_async', 'call_x', -1],
               ['request_user_input_async', 'call_x', True],
               ['request_user_input_async', 'call_x', 0.0],
               ['request_user_input_async', 'call_x', 0, 'extra'])
        for identity in bad:
            with self.subTest(identity=identity):
                altered = item(SPATIAL)
                altered['questionItemId'] = json.dumps(identity)
                self.assertEqual(self.extract(envelope([altered]))[0], '')

    def test_duplicate_question_ids_are_rejected_even_with_different_json_spacing(self):
        first, second = item(SPATIAL), item('continue')
        second['questionItemId'] = json.dumps(json.loads(first['questionItemId']), separators=(',', ':'))
        instruction, metadata = self.extract(envelope([first, second]))
        self.assertEqual(instruction, '')
        self.assertEqual(metadata['reason'], 'duplicate_question_item_id')

    def test_sixteen_answers_allowed_seventeen_rejected(self):
        instruction, metadata = self.extract(envelope([item('continue', i) for i in range(16)]))
        self.assertEqual(len(instruction.splitlines()), 16)
        self.assertEqual(metadata['extraction'], 'answers_only')
        self.assertEqual(self.extract(envelope([item(SPATIAL, i) for i in range(17)]))[0], '')

    def test_text_character_budget_boundary_and_oversize(self):
        base = envelope([item(SPATIAL, question='')])
        exact = envelope([item(SPATIAL, question='x' * (65536 - len(base)))])
        self.assertEqual(len(exact), 65536)
        self.assertEqual(self.extract(exact)[0], SPATIAL)
        self.assertEqual(self.extract(exact + ' ')[0], '')

    def test_plain_oversize_keeps_existing_classifier_budget_behavior(self):
        value = SPATIAL + 'x' * 65536
        instruction, metadata = self.extract(value)
        self.assertEqual(instruction, value)
        self.assertEqual(metadata['format'], 'plain')
        self.assertEqual(classify_task_intent(instruction)['reason_codes'],
                         ['task_instruction_exceeds_classification_budget'])

    def test_lone_surrogate_diagnostic_hash_is_defined_without_body_leak(self):
        value = 'text-\ud800'
        instruction, metadata = self.extract(value)
        self.assertEqual(instruction, value)
        self.assertEqual(metadata['sha256'], hashlib.sha256(value.encode('utf-8', errors='surrogatepass')).hexdigest())


class StructuredPromptRoutingTests(unittest.TestCase):
    def invoke(self, prompt, *, agent='codex', **changes):
        service = HookService()
        result = route_live_hook(event(prompt, **changes), service, agent=agent, invocation_source='manual_probe')
        return service, result

    def test_heavy_hook_observes_only_answer_once_and_never_executes_motion(self):
        value = envelope([item(SPATIAL, question='question-must-not-forward')])
        service, result = self.invoke(value)
        self.assertEqual([c[0] for c in service.calls], ['observe'])
        self.assertEqual(service.calls[0][2]['task_instruction'], SPATIAL)
        self.assertFalse(service.calls[0][2]['include_image'])
        self.assertNotIn('permissionDecision', result['hookSpecificOutput'])
        records = [fields for args, fields in service.records if args == ('host_hook',)]
        self.assertEqual(records[0]['prompt_input']['sha256'], hashlib.sha256(value.encode()).hexdigest())
        self.assertEqual(records[0]['invocation_source'], 'manual_probe')

    def test_spatial_question_negative_answer_never_reads_host(self):
        for answer in ('继续', 'Do not inspect the part gap.',
                       'Do not use Human-Eye engine.', 'Read the screenshot text.'):
            with self.subTest(answer=answer):
                service, result = self.invoke(envelope([item(answer, question=SPATIAL)]))
                self.assertEqual(service.calls, [])
                self.assertEqual(result, {})

    def test_invalid_wrappers_do_not_fall_back_to_spatial_question_or_body(self):
        for value in (OPEN + SPATIAL + CLOSE,
                      envelope([{'question': SPATIAL, 'answer': SPATIAL}]),
                      envelope([item(SPATIAL, 0), item(SPATIAL, 0)])):
            service, result = self.invoke(value)
            self.assertEqual(service.calls, [])
            self.assertEqual(result, {})

    def test_explicit_kind_is_not_manufactured_and_existing_metadata_still_wins(self):
        for kind in ('general', 'image_2d', 'unknown', {}, 1):
            with self.subTest(kind=kind):
                service, _ = self.invoke(envelope([item(SPATIAL)]), task_kind=kind)
                self.assertEqual(service.calls, [])
        service, _ = self.invoke('continue', task_kind='spatial_3d')
        self.assertEqual([c[0] for c in service.calls], ['observe'])

    def test_claude_preserves_prior_no_unwrap_policy(self):
        service, result = self.invoke(envelope([item(SPATIAL)]), agent='claude')
        self.assertEqual(service.calls, [])
        self.assertEqual(result, {})

    def test_prepost_behavior_unchanged_with_a_structured_prompt(self):
        for kind in ('PreToolUse', 'PostToolUse'):
            service, result = self.invoke(envelope([item(SPATIAL)]), hook_event_name=kind,
                tool_name=SPATIAL_TRANSFORM, tool_input={'action': {'translation': [0, 0, .1]}})
            self.assertEqual([c[0] for c in service.calls], ['preview'] if kind == 'PreToolUse' else [])
            if kind == 'PreToolUse':
                self.assertNotIn('permissionDecision', result['hookSpecificOutput'])

    def test_audit_contains_no_question_answer_or_ids_in_prompt_metadata(self):
        value = envelope([item('continue-secret-971', question='question-secret-352')])
        service, _ = self.invoke(value)
        metadata_records = [f['prompt_input'] for _, f in service.records if 'prompt_input' in f]
        self.assertGreaterEqual(len(metadata_records), 2)
        for metadata in metadata_records:
            serialized = json.dumps(metadata)
            for secret in ('continue-secret-971', 'question-secret-352', 'call_contract_01'):
                self.assertNotIn(secret, serialized)
            self.assertEqual(metadata['sha256'], hashlib.sha256(value.encode()).hexdigest())

    def test_trace_metadata_matches_host_hook_metadata_for_same_current_input(self):
        for answer in ('continue', SPATIAL):
            service, _ = self.invoke(envelope([item(answer)]))
            records = [fields for args, fields in service.records if args[0] in ('host_hook_skip', 'host_hook')]
            traces = [fields for args, fields in service.records if args == ('request_trace',)]
            self.assertEqual(records[0]['prompt_input'], traces[0]['prompt_input'])
            self.assertEqual(traces[0]['trace']['correlation']['turn_id'], 'host-turn')
            self.assertEqual(traces[0]['trace']['annotations']['request_origin'], 'manual_probe')
            self.assertNotIn('invalid_annotation', traces[0]['trace']['telemetry_issues'])

    def run_main(self, prompt, **changes):
        service = HookService()
        original_leaf = bootstrap._leaf
        helpers = original_leaf('agent_hooks')
        fake_helpers = SimpleNamespace(_reject_constant=helpers._reject_constant,
                                       _read_object=lambda path: {'enabled': True, 'observe_on_prompt': True})
        def leaf(name):
            return fake_helpers if name == 'agent_hooks' else original_leaf(name)
        def engine():
            return lambda value, config, agent='codex', probe=False: route_live_hook(
                value, service, agent=agent, invocation_source='manual_probe' if probe else 'hook_command')
        stdin = SimpleNamespace(buffer=io.BytesIO(json.dumps(event(prompt, **changes)).encode('utf-8')))
        output = io.StringIO()
        with patch.object(bootstrap, '_leaf', side_effect=leaf), \
             patch.object(bootstrap, '_LightService', return_value=service), \
             patch.object(bootstrap, '_engine_entry', side_effect=engine), \
             patch.object(bootstrap.sys, 'stdin', stdin), patch.object(bootstrap.sys, 'stdout', output):
            code = bootstrap.main(['--config', 'in-memory-test-only', '--agent', 'codex',
                                   '--event', 'UserPromptSubmit', '--probe'])
        self.assertEqual(code, 0)
        return service, json.loads(output.getvalue())

    def test_main_light_dispatch_and_heavy_observation_share_answer(self):
        value = envelope([item(SPATIAL)])
        service, _ = self.run_main(value)
        self.assertEqual([c[0] for c in service.calls], ['observe'])
        self.assertEqual(service.calls[0][2]['task_instruction'], SPATIAL)

    def test_main_negative_answer_keeps_light_route_without_host_work(self):
        service, result = self.run_main(envelope([item('continue', question=SPATIAL)]))
        self.assertEqual(service.calls, [])
        self.assertEqual(result, {})

    def test_main_plain_prompt_behavior_is_preserved(self):
        for prompt, expected in ((SPATIAL, ['observe']), ('continue', [])):
            service, _ = self.run_main(prompt)
            self.assertEqual([c[0] for c in service.calls], expected)

    def test_skip_subprocess_has_no_engine_import_state_or_blender_connection(self):
        root = Path(bootstrap.__file__).resolve().parent
        inspect = """import json,runpy,sys
scope=runpy.run_path(sys.argv[1],run_name='_structured_prompt_contract')
scope['main'](sys.argv[2:])
print('IMPORT_PROOF:'+json.dumps({n:n in sys.modules for n in ('numpy','PIL','human_eye_plugin')}),file=sys.stderr)
"""
        with tempfile.TemporaryDirectory(prefix='human_eye_structured_prompt_') as temporary:
            directory = Path(temporary)
            cfg = directory/'connector.json'
            cfg.write_text(json.dumps({'schema_version':'1.0','enabled':True,'observe_on_prompt':True,
                'project_root':str(root),'state_file':'state.json','audit_file':'audit.jsonl',
                'blender':{'host':'127.0.0.1','port':1,'timeout_s':.01}}), encoding='utf-8')
            value = envelope([item('continue', question=SPATIAL)])
            completed = subprocess.run([sys.executable, '-I', '-B', '-c', inspect,
                str(root/'human_eye_hook.py'), '--config', str(cfg), '--event', 'UserPromptSubmit', '--probe'],
                input=json.dumps(event(value)), text=True, encoding='utf-8', capture_output=True,
                cwd=directory, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            self.assertEqual(json.loads(completed.stdout), {})
            proof = json.loads(next(l.split(':', 1)[1] for l in completed.stderr.splitlines()
                                    if l.startswith('IMPORT_PROOF:')))
            self.assertFalse(any(proof.values()), proof)
            self.assertFalse((directory/'state.json').exists())
            rows = [json.loads(l) for l in (directory/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
            skip = next(r for r in rows if r['event']=='host_hook_skip')
            self.assertFalse(skip['scene_read'])
            self.assertFalse(skip['engine_invoked'])
            self.assertEqual(skip['prompt_input']['extraction'], 'answers_only')
            self.assertEqual(skip['invocation_source'], 'manual_probe')


if __name__ == '__main__':
    unittest.main()
