"""Six directed stdlib mocks only; no CLI/backend/product/model execution."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import tomllib
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import runner


class StartupChecks(unittest.TestCase):
    def test_environment_omits_parent_permission_and_secrets_without_reading_values(self):
        allowed={'CODEX_HOME':'synthetic-original-login-path','PATH':'synthetic-path',
            'CODEX_INTERNAL_ORIGINATOR_OVERRIDE':'synthetic-existing-route','UNRELATED_SETTING':'synthetic-preserved'}
        excluded=('CODEX_PERMISSION_PROFILE','CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID',
            'CODEX_APP_TOOLS_PIPE_PATH','CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY','OPENAI_API_KEY','CODEX_API_KEY')
        class Environment:
            def __iter__(self):return iter((*excluded,*allowed))
            def __getitem__(self,key):
                if key not in allowed:raise AssertionError('excluded value was read:'+key)
                return allowed[key]
        self.assertEqual(runner.safe_environment(Environment()),allowed)

    def test_consumer_pid_error_and_cleanup_are_recorded_without_retry(self):
        from bridge import Budget
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-startup-') as name:
            folder=Path(name)
            cell=dict(audit_root=name,ledger_path=str(folder/'BUDGET.json'),
                deadline_perf_ns=time.perf_counter_ns()+10_000_000_000)
            Budget.create(cell)
            stderr=b'Error: failed to load bootstrap configuration\nCaused by:\n    invalid transport\n'
            child=types.SimpleNamespace(pid=424242,stdin=io.BytesIO(),stdout=io.BytesIO(),
                stderr=io.BytesIO(stderr),returncode=None)
            child.poll=lambda:child.returncode
            def wait(timeout=None):child.returncode=1;return 1
            child.wait=wait
            def reap(process):
                process.returncode=1
                return dict(parent_reaped=True,tree_reaped=True,errors=[])
            with patch.object(runner,'argv_for',return_value=['synthetic-not-launched']), \
                    patch.object(runner.subprocess,'Popen',return_value=child) as launch, \
                    patch.object(runner,'kill_tree',side_effect=reap) as close:
                record=runner.consume({},cell,folder,b'synthetic non-question')
            launch.assert_called_once();close.assert_called_once_with(child)
            self.assertEqual(record['consumer_pid'],424242)
            self.assertEqual(record['exit_code'],1);self.assertTrue(record['process_reaped'])
            self.assertFalse(record['valid_completion'])
            self.assertEqual(record['public_events'],[])
            self.assertEqual(record['stderr_bytes'],len(stderr))
            self.assertIn('invalid transport','\n'.join(record['stderr_diagnostics']['lines']))
            self.assertEqual(json.loads((folder/'CONSUMER.json').read_bytes())['consumer_pid'],424242)

    def test_known_startup_diagnostics_keep_only_ordinary_configuration_lines(self):
        record={}
        raws=[b'Error: failed to load bootstrap configuration\n',b'Caused by:\n',
            b'    invalid transport\n',b'    in `mcp_servers.native`\n',b'Usage: codex exec [OPTIONS]\n']
        for raw in raws:runner.retain_startup_diagnostic(record,raw)
        diagnostics=record['stderr_diagnostics'];text='\n'.join(diagnostics['lines'])
        for expected in ('failed to load bootstrap configuration','Caused by:','invalid transport',
                'mcp_servers.native','Usage: codex exec [OPTIONS]'):
            self.assertIn(expected,text)
        self.assertEqual(record['stderr_bytes'],sum(map(len,raws)))
        self.assertEqual(diagnostics['raw_bytes'],sum(map(len,raws)))
        self.assertFalse(diagnostics['unavailable'])
        self.assertLessEqual(diagnostics['retained_utf8_bytes'],4096)

    def test_sensitive_and_unrecognized_content_never_enters_diagnostics(self):
        record={}
        raws=[b'Error: api_key=sk-SYNTHETIC_SECRET_ONLY\n',
            b'Error: system prompt SYSTEM_PRIVATE_SENTINEL\n',
            b'Caused by: encrypted ENCRYPTED_PRIVATE_SENTINEL\n',
            b'Error: developer DEVELOPER_PRIVATE_SENTINEL\n',
            b'Error: reasoning REASONING_PRIVATE_SENTINEL\n',
            b'unrecognized arbitrary PRIVATE_PAYLOAD_SENTINEL\n']
        for raw in raws:runner.retain_startup_diagnostic(record,raw)
        diagnostics=record['stderr_diagnostics'];serialized=json.dumps(record)
        for private in ('SYNTHETIC_SECRET_ONLY','SYSTEM_PRIVATE_SENTINEL','ENCRYPTED_PRIVATE_SENTINEL',
                'DEVELOPER_PRIVATE_SENTINEL','REASONING_PRIVATE_SENTINEL','PRIVATE_PAYLOAD_SENTINEL'):
            self.assertNotIn(private,serialized)
        self.assertEqual(diagnostics['lines'],[])
        self.assertEqual(diagnostics['retained_utf8_bytes'],0)
        self.assertEqual(diagnostics['raw_bytes'],sum(map(len,raws)))
        self.assertEqual(diagnostics['redacted_bytes'],sum(map(len,raws)))
        self.assertGreaterEqual(diagnostics['redacted_lines'],len(raws))
        self.assertTrue(diagnostics['unavailable'])

    def test_diagnostic_limit_is_fixed_and_raw_redaction_costs_survive(self):
        record={}
        raws=[('    in `mcp_servers.native_'+str(index)+'`\n').encode() for index in range(300)]
        for raw in raws:runner.retain_startup_diagnostic(record,raw)
        runner.retain_startup_diagnostic(record,b'Error: '+b'x'*600+b'\n')
        diagnostics=record['stderr_diagnostics'];total=sum(map(len,raws))+608
        self.assertEqual(diagnostics['limit_bytes'],4096)
        self.assertLessEqual(diagnostics['retained_utf8_bytes'],4096)
        self.assertLessEqual(len('\n'.join(diagnostics['lines']).encode()),4096)
        self.assertEqual(diagnostics['raw_bytes'],total)
        self.assertEqual(record['stderr_bytes'],total)
        self.assertGreater(diagnostics['redacted_bytes'],0)
        self.assertGreater(diagnostics['redacted_lines'],0)
        self.assertTrue(diagnostics['truncated'])

    def test_candidate_argv_retains_complete_transports_and_strict_exec(self):
        plan=json.loads((HERE/'PLAN.json').read_bytes())
        disabled=('mcp_servers.blender.enabled','mcp_servers.cua_repl.enabled',
            'mcp_servers.node_repl.enabled','mcp_servers.agent_learning.enabled')
        for field in disabled:self.assertNotIn(field,plan['codex']['settings'])
        self.assertFalse(plan['execution_ready'])
        self.assertEqual(plan['codex']['settings']['model_provider'],'openai_http')
        self.assertEqual(plan['codex']['settings']['model_reasoning_effort'],'ultra')
        self.assertEqual(plan['codex']['settings']['service_tier'],'default')
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-argv-') as name:
            root=Path(name);binary=root/'not-a-real-cli.exe';binary.write_bytes(b'synthetic file only')
            candidate=copy.deepcopy(plan);candidate['codex']['executable']=str(binary)
            candidate['codex']['sha256']=runner.sha(binary.read_bytes())
            for arm in ('N','P'):
                cell=root/(arm+'.json');cell.write_text(json.dumps({'arm':arm}),encoding='utf8')
                argv=runner.argv_for(candidate,cell,root,root/(arm+'.final'))
                self.assertIn('--strict-config',argv);self.assertIn('--ignore-user-config',argv)
                self.assertEqual(argv[1],'exec')
                servers={}
                for index,arg in enumerate(argv):
                    if arg=='-c':servers.update(tomllib.loads(argv[index+1]).get('mcp_servers',{}))
                self.assertEqual(set(servers),{'native'} if arm=='N' else {'native','human_eye'})
                for transport in servers.values():
                    self.assertTrue(transport.get('command'));self.assertIsInstance(transport.get('args'),list)
                    self.assertTrue(transport['args']);self.assertNotEqual(set(transport),{'enabled'})
                if arm=='P':self.assertEqual(servers['human_eye']['enabled_tools'],['human_eye_scene_observe'])


if __name__=='__main__':unittest.main(verbosity=2)
