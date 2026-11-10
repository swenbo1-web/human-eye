"""Seal this specific metadata/failed-handoff fix, without rerunning product checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

FIX = Path(__file__).resolve().parent
BATCH = FIX.parents[1]
ROOT = BATCH.parents[1]
OLD = FIX/'original_169b0be0'
SELF_RECORDS = {'ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json','FIX_READY.json'}
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                    encoding='utf8', newline='\n')


def main():
    plan, previous = read(BATCH/'PLAN.json'), read(OLD/'PLAN.json')
    assert not any((BATCH/name).exists() for name in ('GO.json','STARTED.json','RUN_RESULT.json','cells'))
    allowed = {'phase','dispatch_input_sha256','quality_handoff_script_sha256',
               'synthetic_validation_result','preparation_fix'}
    assert set(plan) == set(previous) | {'preparation_fix'}
    assert all(plan[key] == previous[key] for key in previous if key not in allowed)
    changed_controls = {'seal_preparation.py','quality_handoff/pack_quality.py',
                        'quality_handoff/SOURCE_REUSE.json'}
    for name, digest in previous['dispatch_input_sha256'].items():
        if name not in changed_controls:
            assert sha(BATCH/name) == digest, name
    for row in read(FIX/'ORIGINALS.json')['originals']:
        assert sha(OLD/row['path']) == row['sha256'], row['path']
    for name in ('ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json'):
        assert (BATCH/name).read_bytes() == (OLD/name).read_bytes(), 'prior seal already replaced: '+name
    assert plan['quality_handoff_script_sha256'] == sha(BATCH/'quality_handoff/pack_quality.py')
    assert all(sha(BATCH/name) == digest for name, digest in plan['dispatch_input_sha256'].items())
    result = read(BATCH/plan['synthetic_validation_result'])
    assert result['passed'] and result['model_consumers'] == result['product_calls'] == result['Blender_sessions'] == 0
    assert not any(result['external_attempts'].values())
    scope = read(FIX/'INDEX_SCOPE_REVIEW.json')
    assert scope['status'] == 'PASS' and scope['committed_batch_file_count'] == 692
    assert scope['original_indexed_files'] == 680 and scope['missed_nested_file_count'] == 9
    # Only root-level self references are omitted. Nested archived seals are evidence.
    paths = sorted(p for p in BATCH.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                   and not (p.parent == BATCH and p.name in SELF_RECORDS))
    rows = []
    for path in paths:
        assert not path.is_symlink()
        if path.suffix == '.py': compile(path.read_bytes(), str(path), 'exec', dont_inherit=True)
        rows.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    indexed = {row['path']: row for row in rows}
    for original in scope['missed_nested_files']:
        assert indexed[original['path']]['sha256'] == original['sha256']
        assert indexed[original['path']]['bytes'] == original['bytes']
    index = dict(cycle_id=plan['cycle_id'], fix_id='LRC-PREP-001', files=rows,
        file_count=len(rows), bytes=sum(row['bytes'] for row in rows),
        exclusions='Only four root-level self-referential records plus local disposable __pycache__; all nested metadata included',
        root_self_reference_records=sorted(SELF_RECORDS),
        original_scope_correction='169b0be0 had 692 committed files = 680 indexed +3 root self records +9 nested FREEZE; no files missing',
        original_scope_details='revisions/LRC_PREP_001/INDEX_SCOPE_REVIEW.json')
    write(BATCH/'ARTIFACT_INDEX.json', index)
    freeze = read(OLD/'FREEZE.json')
    freeze.update(status='FIX_READY', fix_id='LRC-PREP-001', plan_sha256=sha(BATCH/'PLAN.json'),
        artifact_index_sha256=sha(BATCH/'ARTIFACT_INDEX.json'), indexed_files=len(rows),
        root_self_reference_records=sorted(SELF_RECORDS), expected_committed_batch_files=len(rows)+4,
        previous_preparation_commit='169b0be061e91b126f46313478690564ccb2bd60')
    write(BATCH/'FREEZE.json', freeze)
    prep = read(OLD/'PREP_READY.json')
    prep.update(status='FIX_READY', fix_id='LRC-PREP-001', plan_sha256=freeze['plan_sha256'],
        freeze_sha256=sha(BATCH/'FREEZE.json'), artifact_index_sha256=freeze['artifact_index_sha256'],
        indexed_files=len(rows), indexed_bytes=index['bytes'], expected_committed_batch_files=len(rows)+4,
        previous_preparation_commit=freeze['previous_preparation_commit'])
    write(BATCH/'PREP_READY.json', prep)
    ready = dict(cycle_id=plan['cycle_id'], fix_id='LRC-PREP-001', status='FIX_READY',
        sealed_utc=datetime.now(timezone.utc).isoformat(), formal_GO=False,
        model_consumers=0, product_calls=0, Blender_sessions=0, CLI_processes=0,
        previous_preparation_commit=freeze['previous_preparation_commit'],
        plan_sha256=freeze['plan_sha256'], packager_sha256=plan['quality_handoff_script_sha256'],
        artifact_index_sha256=freeze['artifact_index_sha256'], freeze_sha256=sha(BATCH/'FREEZE.json'),
        indexed_files=len(rows), root_self_reference_records=sorted(SELF_RECORDS),
        expected_committed_batch_files=len(rows)+4, original_commit_files=692,
        original_unindexed_nested_FREEZE=9, no_original_files_lost=True,
        validation_result=plan['synthetic_validation_result'], source_and_semantic_contracts_unchanged=True,
        cleanup_retried=False, report='revisions/LRC_PREP_001/REPORT.md',
        next_action='Independent root review; stop until a separate current-cycle formal GO')
    write(BATCH/'FIX_READY.json', ready)
    print(json.dumps(ready))


if __name__ == '__main__':
    main()
