"""Execute only the six fixed offline mock groups, once per evidence directory."""
import ast
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import types
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sha = lambda data: hashlib.sha256(data).hexdigest()


class ObservedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.groups = []

    def startTest(self, test):
        self.groups.append(dict(method=test.id(), subscenarios=0, failed_subscenarios=0))
        super().startTest(test)

    def addSubTest(self, test, subtest, error):
        self.groups[-1]['subscenarios'] += 1
        if error is not None:
            self.groups[-1]['failed_subscenarios'] += 1
        super().addSubTest(test, subtest, error)


def main():
    output = HERE / 'OFFLINE_RESULTS.json'
    assert not output.exists(), 'do not silently replace previous test evidence'
    source = (HERE / 'runner.py').read_bytes()
    old = (ROOT / 'verification/consumption_run_002/runner.py').read_bytes()
    assert sha(old) == 'bfb9189e9c115bad4bd43e249ae543b235246c2ab75460af0d6fd32b54eeb4bf'
    assert sha(source) == '1e87f432ea648613c30666dd06d5dde6cfd16697d7fbd5de10e36f25c997aaf9'
    baseline = ast.parse(old)
    candidate = ast.parse(source)
    changed = []
    assert len(baseline.body) == len(candidate.body)
    for before, after in zip(baseline.body, candidate.body):
        if ast.dump(before) != ast.dump(after):
            assert isinstance(before, ast.FunctionDef) and isinstance(after, ast.FunctionDef)
            assert before.name == after.name
            changed.append(before.name)
    assert changed == ['process_exited', 'registered_tree_cleanup']
    old_start = next(n for n in baseline.body if getattr(n, 'name', None) == changed[0]).lineno - 1
    old_end = next(n for n in baseline.body if getattr(n, 'name', None) == changed[-1]).end_lineno
    new_start = next(n for n in candidate.body if getattr(n, 'name', None) == changed[0]).lineno - 1
    new_end = next(n for n in candidate.body if getattr(n, 'name', None) == changed[-1]).end_lineno
    assert old.splitlines(keepends=True)[:old_start] == source.splitlines(keepends=True)[:new_start]
    assert old.splitlines(keepends=True)[old_end:] == source.splitlines(keepends=True)[new_end:]

    protected_paths = [
        'verification/consumption_run_002/EVIDENCE_INDEX.json',
        'verification/consumption_run_002/actual_01/RESULTS.json',
        'verification/consumption_run_final_001/actual_01/RESULTS.json',
    ]
    protected = {rel: sha((ROOT / rel).read_bytes()) for rel in protected_paths}
    tests = (HERE / 'tests_cleanup.py').read_bytes()
    assert sha(tests) == '412a6adbf4ecf83190e76f82b3adfb0ff3b36cfb73fa90e426893e3f7bc85794'
    module = types.ModuleType('_bounded_cleanup_tests')
    module.__file__ = str(HERE / 'tests_cleanup.py')
    sys.modules[module.__name__] = module
    exec(compile(tests, module.__file__, 'exec', dont_inherit=True), module.__dict__)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.CleanupReceiptChecks)
    assert suite.countTestCases() == 6
    capture = io.StringIO()
    stdout = io.StringIO()
    started_utc = datetime.now(timezone.utc).isoformat()
    started_ns = time.perf_counter_ns()
    with redirect_stdout(stdout), redirect_stderr(capture):
        result = unittest.TextTestRunner(stream=capture, verbosity=2, resultclass=ObservedResult).run(suite)
    elapsed_ns = time.perf_counter_ns() - started_ns
    unchanged = all(sha((ROOT / rel).read_bytes()) == digest for rel, digest in protected.items())
    (HERE / 'OFFLINE_STDOUT.txt').write_text(stdout.getvalue(), encoding='utf8', newline='\n')
    (HERE / 'OFFLINE_STDERR.txt').write_text(capture.getvalue(), encoding='utf8', newline='\n')
    report = dict(
        baseline_HEAD='63dd07f762c1e144a3bedfd5ca5d81d6461748fb',
        started_utc=started_utc, elapsed_ns=elapsed_ns,
        changed_functions=changed, bytes_outside_changed_functions_identical=True,
        source_sha256=sha(source), tests_sha256=sha(tests),
        mock_groups_run=result.testsRun, mock_groups_limit=6,
        failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), successful=result.wasSuccessful(),
        groups=result.groups,
        scenario_count=sum(max(1, g['subscenarios']) for g in result.groups),
        protected_before_sha256=protected, protected_unchanged=unchanged,
        actual_Codex_CLI=0, actual_model_consumers=0, actual_MCP_services=0,
        actual_Blender=0, actual_RPC=0, actual_paid_API=0,
        actual_target_process_starts_or_signals=0,
        method='stdlib unittest; process/OS/network interfaces replaced by mocks or failing guards; no product/backend imports',
        limitations='offline behavior only; does not certify real process state, task correctness, tool approval or future runtime activation',
    )
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({k: report[k] for k in ('mock_groups_run', 'scenario_count', 'failures', 'errors', 'successful', 'protected_unchanged')}))
    assert unchanged and result.wasSuccessful()


if __name__ == '__main__':
    main()
