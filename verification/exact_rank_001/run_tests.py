"""Capture a fixed correctness run, preserving stdout/stderr and test failures."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
sys.path.insert(0, str(REPO))
mode = sys.argv[1]
prefix = sys.argv[2]
destination = OUT / prefix
destination.mkdir(exist_ok=False)
started = datetime.now(timezone.utc).isoformat()
source_paths = ['human_eye_plugin/surface_proximity.py', 'human_eye_plugin/task_query.py',
                'human_eye_plugin/runtime_identity.py']
hashes = {p: hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in source_paths}
if mode == 'new':
    spec = importlib.util.spec_from_file_location('exact_rank_tests', OUT/'test_exact_rank.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
else:
    names = ['verification.test_surface_proximity_001', 'verification.test_surface_proximity_pruning_001',
             'verification.test_scene_cache', 'verification.test_cache_accounting', 'verification.test_task_query']
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
with (destination/'unittest.stderr.txt').open('w', encoding='utf8') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
from human_eye_plugin import runtime_identity, surface_proximity
identity = runtime_identity.runtime_identity()
assert all(hashlib.sha256((REPO/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
record = dict(mode=mode, started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(),
    tests_run=result.testsRun, failures=[dict(test=str(t), traceback=s) for t,s in result.failures],
    errors=[dict(test=str(t), traceback=s) for t,s in result.errors], skipped=result.skipped,
    passed=result.wasSuccessful(), source_hashes=hashes, runtime_source_sha256=identity['source_sha256'],
    runtime_source_count=len(identity['source_files']), module_file=surface_proximity.__file__,
    Blender_runs=0, performance_samples=0, consumers=0, API_calls=0)
if mode == 'new':
    record['groups'] = module.EVIDENCE
    record['kernel_calls'] = sum(v['kernel_calls'] for v in module.EVIDENCE.values())
    record['nearest_calls'] = sum(v['nearest_calls'] for v in module.EVIDENCE.values())
(destination/'RESULT.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k not in ('groups','source_hashes','failures','errors')}))
raise SystemExit(0 if result.wasSuccessful() else 1)
