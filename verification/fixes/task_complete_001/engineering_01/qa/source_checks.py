"""The single fixed targeted run, against this checkout's candidate bytes."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
OUTPUT = Path(__file__).resolve().parents[1]
MODULES = ["test_task_complete_001", "test_task_query", "test_selected_task_query",
           "test_concave_geometry", "test_perf030_002_pt_dual", "test_perf030_003_goal"]
started = time.perf_counter_ns()
from human_eye_plugin import runtime_identity

identity = runtime_identity.runtime_identity()
assert Path(runtime_identity.__file__).resolve().is_relative_to(ROOT)
suite = unittest.defaultTestLoader.loadTestsFromNames(["verification." + name for name in MODULES])


def identifiers(group):
    for item in group:
        if isinstance(item, unittest.TestSuite):
            yield from identifiers(item)
        else:
            yield item.id()


selected = list(identifiers(suite))
result = unittest.TextTestRunner(verbosity=2).run(suite)
record = dict(modules=MODULES, selected=selected, selected_count=len(selected),
              tests_run=result.testsRun, failures=result.failures, errors=result.errors,
              skipped=result.skipped, successful=result.wasSuccessful(), identity=identity,
              source_drift=runtime_identity.check_source_drift(),
              elapsed_ns=time.perf_counter_ns() - started)
with (OUTPUT / "UNIT_RESULT.json").open("x", encoding="utf8") as stream:
    json.dump(record, stream, indent=2)
assert result.wasSuccessful() and result.testsRun == len(selected) and not result.skipped
