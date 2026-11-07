"""Freeze source bytes and the already registered single sample protocol."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
old = json.loads((HERE.parent / 'engineering_a/INSTALLED_IDENTITY.json').read_text('utf8'))['identity']
files = [dict(path=row['path'], sha256=hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest())
         for row in old['source_files']]
payload = dict(base_version=old['base_version'], implementation_revision=old['implementation_revision'], files=files)
pin = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
changed = [row['path'] for row, prior in zip(files, old['source_files']) if row != prior]
assert changed == ['human_eye_plugin/surface_proximity.py', 'human_eye_plugin/task_query.py']
record = dict(frozen_utc=datetime.now(timezone.utc).isoformat(), source_sha256=pin, source_count=len(files),
    source_files=files, changed_runtime_files=changed, expected_targeted_methods=52,
    fixed_inputs={name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                  for name in ('PREREGISTRATION.json', 'MATH_PLAN.md', 'qa/source_checks.py',
                               'qa/surface_comparison.py', 'qa/instrumented_service.py')},
    tests={name: hashlib.sha256((ROOT / 'verification' / name).read_bytes()).hexdigest()
           for name in ('test_surface_proximity_001.py', 'test_surface_proximity_pruning_001.py')})
with (HERE / 'FREEZE.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(dict(source_sha256=pin, source_count=len(files), changed=changed)))
