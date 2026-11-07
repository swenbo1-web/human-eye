"""The one necessary QA recovery: only the fixture-construction error method."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
METHOD = ('verification.test_surface_proximity_pruning_001.SurfaceAABBPruningTests.'
          'test_checkpoint_exceptions_propagate_before_a_prunable_pair')
initial = json.loads((HERE / 'UNIT_RESULT.json').read_text('utf8'))
freeze = json.loads((HERE / 'FREEZE.json').read_text('utf8'))
assert initial['tests_run'] == initial['selected_count'] == 52
assert not initial['failures'] and not initial['skipped'] and len(initial['errors']) == 1
assert initial['errors'][0][0] == METHOD and "missing 1 required positional argument: 'stage'" in initial['errors'][0][1]
before = (HERE / 'qa/test_surface_proximity_pruning_001.before_recovery.txt').read_bytes()
after = (ROOT / 'verification/test_surface_proximity_pruning_001.py').read_bytes()
assert hashlib.sha256(before).hexdigest() == freeze['tests']['test_surface_proximity_pruning_001.py']
assert after == before.replace(b"RequestBudgetError('request_deadline_exceeded')",
                             b"RequestBudgetError('expired', 'surface_proximity_pair')")
from human_eye_plugin import runtime_identity
identity = runtime_identity.runtime_identity()
assert identity['source_sha256'] == freeze['source_sha256'] == initial['identity']['source_sha256']
start = time.perf_counter_ns()
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames([METHOD]))
record = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), selected=[METHOD], tests_run=result.testsRun,
    successful=result.wasSuccessful(), failures=[(test.id(), trace) for test, trace in result.failures],
    errors=[(test.id(), trace) for test, trace in result.errors], skipped=result.skipped,
    elapsed_ns=time.perf_counter_ns()-start, identity=identity, source_drift=runtime_identity.check_source_drift(),
    scope='only necessary fixture recovery; initial 52-method run and traceback remain unchanged',
    before_test_sha256=hashlib.sha256(before).hexdigest(), after_test_sha256=hashlib.sha256(after).hexdigest(),
    remaining_qa_recovery_allowance=0)
with (HERE / 'UNIT_RECOVERY.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
assert result.wasSuccessful() and result.testsRun == 1 and not result.skipped
acceptance = dict(successful=True, identity=identity, selected=initial['selected'], selected_count=52,
    tests_run=52, unique_methods=52, method_executions_including_recovery=53,
    initial_passed=51, initial_errors=1, recovered_methods=1, remaining_failures=0, remaining_qa_recovery_allowance=0,
    original_run='UNIT_RESULT.json', recovery_run='UNIT_RECOVERY.json', product_source_unchanged=True)
with (HERE / 'UNIT_ACCEPTANCE.json').open('x', encoding='utf8') as stream:
    json.dump(acceptance, stream, indent=2)
