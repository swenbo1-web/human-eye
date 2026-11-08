"""Reuse the preceding bounded harness and record this task's fixed inputs."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
OLD = ROOT / 'verification/closed_solid_read_001'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
save = lambda p, v: p.write_text(json.dumps(v, indent=2)+'\n', encoding='utf8')
assert not (OUT/'TASK_START.json').exists()
save(OUT/'TASK_START.json', dict(task='ZERO-WITNESS-REUSE-001',
    turn_id='01a1bbc1-4c40-7772-a108-c02e0af45a24',
    receipt_epoch_seconds=1794151369, implementation_deadline_epoch_seconds=1794154069,
    starting_HEAD='51be5e37b57449dd65335e8181337fc08d06051d',
    baseline_product_commit='b60dd327e3926a06b73d77b37be7b63c50a3939a',
    baseline_source_sha256='1545da06b415864cf3f666f3a56432e91689d1a0565ea8589a19e3ecfff2b459'))
for source, name, expected in (
    ('D:/hefe/verification/fixes/20261108_complex_reentry/ZERO_WITNESS_OPT_ASSIGNMENT.md','ASSIGNMENT.md','3453f36ffb708821509eefd511f101848e3d957a5e23a80d514d170bb89b4012'),
    ('D:/hefe/verification/fixes/20261108_complex_reentry/ZERO_WITNESS_WINDOW.json','WINDOW.json','e5ec95a4fef36486ec385e6b781dea7caf110df18a380ae86baa09a5b2f9d5f5'),
    ('D:/hefe/verification/fixes/20261108_complex_reentry/CLOSED_SOLID_REVIEW.md','BASELINE_REVIEW.md',None),
    ('D:/hefe/verification/fixes/20261107_nearest_contract/STANDING_USER_AUTHORIZATION_20261108.json','STANDING_AUTHORIZATION.json','485605143ab94ce19d457724f180649fd4fb5c1d86da23ed2e673c73b7ef33e1')):
    source=Path(source)
    if expected: assert sha(source)==expected
    (OUT/name).write_bytes(source.read_bytes())
protected=json.loads((OLD/'PROTECTED_BEFORE.json').read_text())['files']
paths=[r['path'] for r in protected]+['verification/closed_solid_read_001/'+p for p in ('REPORT.md','EVIDENCE_INDEX.json','qa_01/RESULTS.json')]
save(OUT/'PROTECTED_BEFORE.json', dict(baseline_HEAD='51be5e37b57449dd65335e8181337fc08d06051d',
    files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths]))
runner=(OLD/'run_offline.py').read_text()
runner=runner.replace("directed = execute_test('_closed_solid_directed', 'verification/closed_solid_read_001/tests/test_closed_solid.py')\n    run_group('CLOSED_SOLID_DIRECTED', [directed])", "prior = execute_test('verification.closed_solid_read_001.tests.test_closed_solid', 'verification/closed_solid_read_001/tests/test_closed_solid.py')\n    directed = execute_test('_zero_witness_directed', 'verification/zero_witness_reuse_001/tests/test_zero_witness.py')\n    run_group('ZERO_WITNESS_DIRECTED', [directed])")
(OUT/'run_offline.py').write_text(runner, encoding='utf8')
print(json.dumps(dict(protected_files=len(paths),deadline_epoch_seconds=1794154069)))
