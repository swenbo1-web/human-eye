"""Synthetic/static preparation checks; no consumers, network or geometry."""
import ast
import json
import io
from pathlib import Path
import sys
import tempfile
import time
import types
import tomllib
import unittest
from unittest.mock import patch,Mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import runner


class RunnerPreparationTests(unittest.TestCase):
    def test_frozen_order_and_executable_limits(self):
        plan=json.loads((HERE/'PLAN.json').read_bytes())
        runner.validate_plan(plan)
        self.assertEqual(plan['limits']['total_physical_rpc'],8*(128+1))
        self.assertEqual(plan['limits']['action_observation_threshold'],8)
        self.assertIsNone(plan['limits']['output_tokens_hard_limit'])
        self.assertFalse(plan['execution_ready'])

    def test_unready_guard_precedes_every_external_action(self):
        plan=json.loads((HERE/'PLAN.json').read_bytes())
        with patch.object(runner.subprocess,'Popen',side_effect=AssertionError('no child')):
            with self.assertRaisesRegex(AssertionError,'PREPARATION_ONLY'):
                runner.require_ready(plan,{})

    def test_public_record_discards_reasoning_and_system(self):
        for item_type in ('reasoning','encrypted_reasoning','system_message','developer_message'):
            raw={'type':'item.completed','item':{'type':item_type,'text':'MUST_NOT_EXPORT'}}
            self.assertIsNone(runner.public_event(raw))
        self.assertIsNone(runner.public_event({'type':'response.reasoning.delta','delta':'MUST_NOT_EXPORT'}))

    def test_public_tools_keep_arguments_without_private_extras(self):
        item=dict(type='mcp_tool_call',id='1',server='native',tool='execute_blender_code',
            arguments={'code':'print(1)'},result={'content':[]},reasoning='DROP',system='DROP')
        record=runner.public_event(dict(type='item.completed',item=item))
        self.assertEqual(record['item']['arguments'],{'code':'print(1)'})
        self.assertNotIn('reasoning',record['item']);self.assertNotIn('system',record['item'])

    def test_usage_only_numeric_terminal_values_no_snapshot_addition(self):
        event=runner.public_event({'type':'turn.completed','usage':dict(input_tokens=10,cached_input_tokens=3,
            output_tokens=2,total_tokens=True,model='UNEXPOSED',reasoning='DROP')})
        self.assertEqual(event['usage'],dict(input_tokens=10,cached_input_tokens=3,output_tokens=2))
        self.assertIsNone(runner.public_event({'type':'token_count','usage':{'total_tokens':100}}))

    def test_all_candidate_overrides_toml_round_trip(self):
        settings=json.loads((HERE/'PLAN.json').read_bytes())['codex']['settings']
        for key,value in settings.items():
            with self.subTest(key=key):
                parsed=tomllib.loads(key+'='+runner.toml_value(value))
                self.assertTrue(parsed)
        self.assertEqual(settings['model_provider'],'openai_http')
        self.assertEqual(settings['model_reasoning_effort'],'ultra')

    def test_component_source_syntax_only(self):
        for name in ('runner.py','bridge.py','he_bootstrap.py','freeze_plan.py'):
            ast.parse((HERE/name).read_bytes(),filename=name)
        text=(HERE/'he_bootstrap.py').read_text('utf8')
        self.assertNotIn('sys.setprofile',text)
        self.assertNotIn('capture_nearest_candidates(',text)

    def test_secret_and_parent_binding_values_are_never_read(self):
        class Environment:
            def __iter__(self):return iter(('CODEX_API_KEY','GOOGLE_API_KEY','CODEX_THREAD_ID','CODEX_APP_TOOLS_PIPE_PATH','CODEX_HOME','PATH'))
            def __getitem__(self,key):
                if key not in ('CODEX_HOME','PATH'):raise AssertionError('forbidden value read')
                return 'synthetic-safe-path'
        self.assertEqual(runner.safe_environment(Environment()),{'CODEX_HOME':'synthetic-safe-path','PATH':'synthetic-safe-path'})

    def test_early_broken_pipe_still_reaps_and_records_failure(self):
        from bridge import Budget
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-lifecycle-') as folder:
            root=Path(folder);cell=dict(ledger_path=str(root/'ledger.json'),audit_root=folder,
                deadline_perf_ns=time.perf_counter_ns()+10_000_000_000)
            Budget.create(cell)
            child=types.SimpleNamespace(stdin=Mock(),stdout=io.BytesIO(),stderr=io.BytesIO(),returncode=None)
            child.stdin.write.side_effect=BrokenPipeError('synthetic')
            child.poll=lambda:child.returncode
            def reap(process):process.returncode=0
            with patch.object(runner,'argv_for',return_value=['synthetic-not-launched']), \
                 patch.object(runner.subprocess,'Popen',return_value=child),patch.object(runner,'kill_tree',side_effect=reap) as closed:
                record=runner.consume({},cell,root,b'synthetic only')
            self.assertFalse(record['valid_completion']);self.assertEqual(record['error_type'],'BrokenPipeError')
            self.assertTrue(record['process_reaped']);closed.assert_called_once_with(child)
            self.assertTrue((root/'CONSUMER.json').exists())

    def test_kill_tree_helper_has_a_bounded_timeout(self):
        child=Mock();child.poll.return_value=None
        with patch.object(runner.subprocess,'run',side_effect=runner.subprocess.TimeoutExpired('synthetic',3)) as command:
            runner.kill_tree(child)
        self.assertEqual(command.call_args.kwargs['timeout'],3)
        child.kill.assert_called_once();child.wait.assert_called_once_with(timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
