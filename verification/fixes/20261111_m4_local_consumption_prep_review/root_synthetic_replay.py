"""Replay fixed synthetic QA without executing consumers, products or Blender.

Author bytes are compiled directly; only synthetic output destination changes.
Local modules loaded by importlib also compile the verified source bytes, so
retained local pyc files are neither deleted nor used for these replay modules.
"""
import contextlib
import hashlib
import importlib.machinery
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = WT/'verification/m4_local_relation_consumption_001'
OUT = Path(__file__).resolve().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
plan_raw = (BATCH/'PLAN.json').read_bytes()
assert sha(plan_raw) == '698b74ec8607e499693d1d34394e4ae06f9bca2e52ac1bda456cc96d4e453761'
plan = json.loads(plan_raw)
paths = {
    BATCH/'synthetic/verify_packager.py':'0c10a60acb826699b4a51e2cc31110a214686899aa1af5e372d12169a84dbc29',
    BATCH/'quality_handoff/pack_quality.py':'90f07a6b78457bb7ca9a5b93fbb7d78bf3439b547cfb21ff4fbae0b0c76ab0d4',
    BATCH/'runtime/driver.py':plan['preflight_driver_sha256'],
}
raws = {p.resolve():p.read_bytes() for p in paths}
assert all(sha(raws[p.resolve()]) == digest for p,digest in paths.items())
test_path = BATCH/'runtime/test_group_contract.py'
test_raw = test_path.read_bytes()
attempts = []
def forbid(*args, **kwargs):
    attempts.append('external_process_or_network')
    raise AssertionError(attempts[-1])

original_get_code = importlib.machinery.SourceFileLoader.get_code
def source_code(loader, fullname):
    path = Path(loader.get_filename(fullname)).resolve()
    if path in raws:
        assert path.read_bytes() == raws[path]
        return compile(raws[path], str(path), 'exec', dont_inherit=True)
    return original_get_code(loader, fullname)

def module_from_bytes(name, path, raw):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module

stream = io.StringIO()
with patch.object(importlib.machinery.SourceFileLoader,'get_code',source_code), \
        patch.object(subprocess,'Popen',side_effect=forbid), \
        patch.object(socket,'socket',side_effect=forbid), \
        patch.object(socket,'create_connection',side_effect=forbid):
    synth = module_from_bytes('root_fixed_synthetic', BATCH/'synthetic/verify_packager.py',
                              raws[(BATCH/'synthetic/verify_packager.py').resolve()])
    synth.OUT = OUT/'synthetic_replay'
    with contextlib.redirect_stdout(stream):
        synthetic_exit = synth.main()
    group = module_from_bytes('root_fixed_group_qa', test_path, test_raw)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(group.GroupContractTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    # Check the real frozen plan, not only the author's synthetic plan fixture.
    group.driver.go_contract(dict(task=plan['cycle_id'],authorized=True,
        plan_sha256=sha(plan_raw),max_consumers=9),plan,sha(plan_raw))
    real_mapping = []
    for slot in plan['sequence']:
        internal, ready, profile = group.driver.arm_runtime(plan, slot)
        real_mapping.append(dict(cell=slot['cell'],external=slot['group'],
            internal=internal['group'],recorded_external=internal['external_group'],
            profile=profile,source=ready['source_sha256']))

summary = json.loads((OUT/'synthetic_replay/RESULTS.json').read_bytes())
receipt = dict(synthetic_exit=synthetic_exit,synthetic_checks=summary['check_count'],
    synthetic_passed=summary['passed'],group_tests=result.testsRun,
    group_passed=result.wasSuccessful(),real_frozen_mapping=real_mapping,
    external_attempts=attempts,author_synthetic_external_attempts=summary['external_attempts'],
    sources={str(p):sha(raw) for p,raw in raws.items()},group_test_sha256=sha(test_raw),
    wrapper_sha256=sha(Path(__file__).read_bytes()),model_consumers=0,Blender_sessions=0,
    note='Synthetic fixture PIDs/finals are fictitious; no actual GO or formal cells created.')
with (OUT/'ROOT_REPLAY.json').open('x',encoding='utf8') as f:
    json.dump(receipt,f,indent=2);f.write('\n')
with (OUT/'ROOT_REPLAY_LOG.txt').open('x',encoding='utf8') as f:
    f.write(stream.getvalue())
assert synthetic_exit == 0 and result.wasSuccessful() and not attempts
print(json.dumps({k:v for k,v in receipt.items() if k not in ('real_frozen_mapping','sources')}))
