"""Single installed-source identity check and approved unittest selection."""
import importlib
import json
from pathlib import Path
import sys
import sysconfig
import time
import unittest

RUN = Path(__file__).resolve().parents[1]
FREEZE = json.loads((RUN.parent / "static_freeze.json").read_bytes())
PURELIB = Path(sysconfig.get_path("purelib")).resolve()
started = time.perf_counter_ns()
from human_eye_plugin import runtime_identity as runtime
import numpy
import PIL

identity = runtime.runtime_identity()
assert identity["source_kind"] == "installed_distribution", identity
assert identity["source_sha256"] == FREEZE["source_sha256"], identity
assert len(identity["source_files"]) == 130, identity
assert identity["distribution_version"] == FREEZE["candidate_distribution_version"]
assert runtime.check_source_drift()["compatible"]
for module in (runtime, numpy, PIL):
    assert Path(module.__file__).resolve().is_relative_to(PURELIB), module.__file__
proof = dict(identity=identity, purelib=str(PURELIB), executable=sys.executable,
             python=sys.version, numpy=numpy.__version__, pillow=PIL.__version__,
             prefix=sys.prefix, base_prefix=sys.base_prefix)
(RUN / "INSTALLED_IDENTITY.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf8")

names = ["verification." + name for name in FREEZE["regression_modules"]]
names.extend(FREEZE["regression_additional_methods"])
suite = unittest.defaultTestLoader.loadTestsFromNames(names)

def identifiers(group):
    for item in group:
        if isinstance(item, unittest.TestSuite):
            yield from identifiers(item)
        else:
            yield item.id()

selected = list(identifiers(suite))
result = unittest.TextTestRunner(verbosity=2).run(suite)
loaded = {}
for name, module in tuple(sys.modules.items()):
    if name.startswith(("human_eye_plugin", "human_eye_module1_operators")):
        filename = getattr(module, "__file__", None)
        if filename:
            loaded[name] = filename
            assert Path(filename).resolve().is_relative_to(PURELIB), filename
report = dict(selection=names, selected_ids=selected, selected_count=len(selected),
              tests_run=result.testsRun, failures=result.failures, errors=result.errors,
              skipped=result.skipped, expected_failures=result.expectedFailures,
              unexpected_successes=result.unexpectedSuccesses,
              successful=result.wasSuccessful(), loaded_product_paths=loaded,
              elapsed_ns=time.perf_counter_ns() - started,
              source_drift_after=runtime.check_source_drift())
(RUN / "REGRESSIONS.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
assert result.wasSuccessful() and result.testsRun == len(selected) and not result.skipped, report
