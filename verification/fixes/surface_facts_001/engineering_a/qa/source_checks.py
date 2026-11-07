"""The single fixed targeted run, against this checkout's candidate bytes."""
import argparse
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
OUTPUT = Path(__file__).resolve().parents[1]
MODULES = ["test_surface_proximity_001", "test_task_query", "test_selected_task_query",
           "test_task_contract_001", "test_task_complete_001"]
started = time.perf_counter_ns()
parser = argparse.ArgumentParser()
parser.add_argument('--method', action='append')
parser.add_argument('--result', type=Path, default=OUTPUT / 'UNIT_RESULT.json')
args = parser.parse_args()
from human_eye_plugin import runtime_identity

identity = runtime_identity.runtime_identity()
assert Path(runtime_identity.__file__).resolve().is_relative_to(ROOT)
names = args.method or ["verification." + name for name in MODULES]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)


def identifiers(group):
    for item in group:
        if isinstance(item, unittest.TestSuite):
            yield from identifiers(item)
        else:
            yield item.id()


selected = list(identifiers(suite))
result = unittest.TextTestRunner(verbosity=2).run(suite)
record = dict(selection=names, selected=selected, selected_count=len(selected),
              tests_run=result.testsRun, failures=[(test.id(), trace) for test, trace in result.failures],
              errors=[(test.id(), trace) for test, trace in result.errors],
              skipped=[(test.id(), reason) for test, reason in result.skipped], successful=result.wasSuccessful(), identity=identity,
              source_drift=runtime_identity.check_source_drift(),
              elapsed_ns=time.perf_counter_ns() - started)
with args.result.open("x", encoding="utf8") as stream:
    json.dump(record, stream, indent=2)
assert result.wasSuccessful() and result.testsRun == len(selected) and not result.skipped
