"""One fixed B run: original 41 surface methods plus direct pruning checks."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
OUTPUT = Path(__file__).resolve().parents[1]
MODULES = ['verification.test_surface_proximity_001',
           'verification.test_surface_proximity_pruning_001']
started = time.perf_counter_ns()
from human_eye_plugin import runtime_identity


def identifiers(group):
    for item in group:
        if isinstance(item, unittest.TestSuite):
            yield from identifiers(item)
        else:
            yield item.id()


suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
selected = list(identifiers(suite))
assert len(selected) == len(set(selected))
identity = runtime_identity.runtime_identity()
freeze = json.loads((OUTPUT / 'FREEZE.json').read_text('utf8'))
assert identity['source_sha256'] == freeze['source_sha256']
assert len(selected) == freeze['expected_targeted_methods']
result = unittest.TextTestRunner(verbosity=2).run(suite)
record = dict(selection=MODULES, selected=selected, selected_count=len(selected),
    tests_run=result.testsRun, failures=[(test.id(), trace) for test, trace in result.failures],
    errors=[(test.id(), trace) for test, trace in result.errors],
    skipped=[(test.id(), reason) for test, reason in result.skipped], successful=result.wasSuccessful(),
    identity=identity, source_drift=runtime_identity.check_source_drift(),
    elapsed_ns=time.perf_counter_ns() - started)
with (OUTPUT / 'UNIT_RESULT.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
assert result.wasSuccessful() and result.testsRun == len(selected) and not result.skipped
