"""Seal an already-finished RUN-004; no consumer, backend, replay or repair."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'verification/consumption_run_004'
OUT = RUN / 'actual_invocation_001'
NEUTRAL = Path('C:/Users/Administrator/AppData/Local/Temp/he-consumption-run-004')
ACTIVATION = Path('D:/hefe/verification/fixes/20261107_nearest_contract/consumption_run_004_prepared')
BASE = 'c9594c5534ddc215bb574d8cb65cbcb47f9a701d'
sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(path.read_bytes())


def put(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf8', newline='\n')


def main():
    index_path = RUN / 'EVIDENCE_INDEX.json'
    assert not index_path.exists(), 'do not overwrite a previous seal'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == BASE
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT)
    for name in ('runner.py', 'bridge.py', 'he_bootstrap.py', 'PRODUCT_BYTES.zip', 'PLAN.json', 'PACKAGE.json'):
        assert (RUN / name).read_bytes() == (ACTIVATION / name).read_bytes()
    package = load(RUN / 'PACKAGE.json')
    for row in package['files']:
        name, expected = row['path'], row['sha256']
        assert sha((RUN / name).read_bytes()) == expected
    assert sha((RUN / 'PLAN.json').read_bytes()) == 'f85ead30c6a51cfe18bfe720f2182a8592069b246e876f0d5b88268781bbae30'
    for name in ('COUNTS_AUDIT.json', 'CLEANUP_AUDIT.json', 'RESULT.json'):
        assert (OUT / name).exists(), name
    assert (RUN / 'REPORT.md').exists()
    invocation = load(OUT / 'RESULT.json')
    assert invocation['process_reaped'] is True
    result = load(RUN / 'actual_01/RESULTS.json')
    assert len(result['cells']) == 8
    assert all(x['status'] not in ('planned', 'running') for x in result['cells'])
    frozen = {p.relative_to(RUN).as_posix(): sha(p.read_bytes())
              for p in (RUN / 'actual_01').rglob('*') if p.is_file()}

    protected = load(OUT / 'PROTECTED_BEFORE.json')
    for row in protected['files']:
        data = (ROOT / row['path']).read_bytes()
        assert sha(data) == row['sha256']
        assert data == subprocess.check_output(['git', 'cat-file', 'blob', BASE + ':' + row['path']], cwd=ROOT)

    archive_path = OUT / 'NEUTRAL_RAW.zip'
    members = []
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(NEUTRAL.rglob('*')):
            if not path.is_file():
                continue
            assert path.resolve().is_relative_to(NEUTRAL.resolve())
            raw = path.read_bytes()
            rel = path.relative_to(NEUTRAL).as_posix()
            item = zipfile.ZipInfo(rel, (2026, 11, 8, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            assert sha(path.read_bytes()) == sha(raw), 'raw file changed while archiving'
            members.append(dict(path=rel, bytes=len(raw), sha256=sha(raw)))
    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == sorted(row['path'] for row in members)
        for row in members:
            assert sha(archive.read(row['path'])) == row['sha256']
    put(OUT / 'NEUTRAL_RAW_INDEX.json', dict(
        source_root=str(NEUTRAL), archive=archive_path.name,
        archive_sha256=sha(archive_path.read_bytes()), file_count=len(members), files=members,
        source_deleted_or_moved=False,
        scope='all raw files from this run private neutral root only; no shared/global log access'))

    turn = load(OUT / 'MANAGEMENT_START.json')
    turn_start = datetime.fromtimestamp(turn['started_at_epoch_seconds'], timezone.utc)
    started = datetime.fromisoformat(invocation['started_utc'])
    ended = datetime.fromisoformat(invocation['ended_utc'])
    cutoff = datetime.now(timezone.utc)
    put(OUT / 'MANAGEMENT_CLOCK.json', dict(
        thread_id=turn['thread_id'], turn_id=turn['turn_id'],
        turn_started_utc=turn_start.isoformat(), turn_completed_utc=None,
        cutoff_utc=cutoff.isoformat(), turn_elapsed_through_cutoff_s=(cutoff-turn_start).total_seconds(),
        preparation_through_controller_dispatch_s=(started-turn_start).total_seconds(),
        controller_end_to_cutoff_s=(cutoff-ended).total_seconds(),
        scope='elapsed lower bound through seal; includes nested invocation and parallel audits; do not sum; final commit/callback tail and earlier turns excluded'))
    put(OUT / 'PRESERVATION.json', dict(
        baseline_HEAD=BASE, old_tracked_originals_unchanged=protected['files'],
        frozen_run_files=frozen, activation_files_exact=True,
        original_result_states=[dict(ordinal=x['ordinal'], task_id=x['task_id'], arm=x['arm'], status=x['status']) for x in result['cells']],
        original_run_result_rewritten=False, source_deleted_or_moved=False,
        scope='new RUN-004 evidence only; old001/002/003/M1, product and STATE unchanged'))
    for rel, expected in frozen.items():
        assert sha((RUN / rel).read_bytes()) == expected
    entries = []
    for path in sorted(RUN.rglob('*')):
        if not path.is_file() or path == index_path or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        raw = path.read_bytes()
        entries.append(dict(path=path.relative_to(RUN).as_posix(), bytes=len(raw), sha256=sha(raw)))
    put(index_path, dict(schema='consumption-run-004-evidence-index-v1', cycle_id='CONSUMPTION-RUN-004',
                         baseline_HEAD=BASE, generated_utc=datetime.now(timezone.utc).isoformat(),
                         path_base='verification/consumption_run_004', file_count=len(entries),
                         excludes=['EVIDENCE_INDEX.json (self)', '__pycache__/**', '*.pyc'], files=entries))
    print(json.dumps(dict(indexed_files=len(entries), neutral_members=len(members),
                          report_sha256=sha((RUN / 'REPORT.md').read_bytes()),
                          index_sha256=sha(index_path.read_bytes()))))


if __name__ == '__main__':
    main()
