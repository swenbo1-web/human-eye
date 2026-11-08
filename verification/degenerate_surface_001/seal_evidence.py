"""Seal this finished candidate and original evidence; no product execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = '35f6d31ae779af823168c9242c2a0c1205592f78'
CANDIDATE = '0ad59befeee43c2fad752e3bad2ee69f87af3136'
EXTERNAL = ['human_eye_plugin/surface_proximity.py', 'human_eye_plugin/task_query.py',
    'verification/test_surface_proximity_001.py', 'verification/test_surface_proximity_pruning_001.py',
    'verification/surface_nearest_entry_001/tests/test_surface_nearest_entry.py']
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(path.read_bytes())


def put(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf8', newline='\n')


def main():
    index_path = OUT / 'EVIDENCE_INDEX.json'
    assert not index_path.exists()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == CANDIDATE
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT)
    freeze = load(OUT / 'CANDIDATE_FREEZE.json')
    assert freeze['candidate_commit'] == CANDIDATE
    assert freeze['source_sha256'] == '82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6'
    for row in freeze['product_manifest']:
        data = (ROOT / row['path']).read_bytes()
        assert sha(data) == row['sha256']
        assert data == (Path(freeze['source_root']) / row['path']).read_bytes()
        assert data == subprocess.check_output(['git', 'cat-file', 'blob', CANDIDATE + ':' + row['path']], cwd=ROOT)
    for key in ('offline_proof', 'identity_proof', 'independent_oracle'):
        assert sha(Path(freeze[key]['path']).read_bytes()) == freeze[key]['sha256']
    assert load(OUT / 'offline_01/RESULTS.json')['passed'] is True
    assert load(OUT / 'qa_01/RESULTS.json')['passed'] is True
    outer = load(OUT / 'qa_invocation_01/RESULT.json')
    assert outer['exit_code'] == 0 and outer['process_reaped'] is True
    qa_freeze = load(OUT / 'qa_01/FREEZE.json')
    assert sha((OUT / 'qa_01/PLAN.json').read_bytes()) == qa_freeze['plan_sha256']
    for row in qa_freeze['controllers']:
        assert sha(Path(row['path']).read_bytes()) == row['sha256']
    for name in ('REPORT.md', 'GEOMETRY_AUDIT.json', 'QA_AUDIT.json', 'SOURCE_REVIEW.json'):
        assert (OUT / name).exists(), name
    protected = load(OUT / 'PROTECTED_BEFORE.json')['files']
    for row in protected:
        data = (ROOT / row['path']).read_bytes()
        assert sha(data) == row['sha256']
        assert data == subprocess.check_output(['git', 'cat-file', 'blob', BASE + ':' + row['path']], cwd=ROOT)
    raw_paths = sorted(p for folder in ('offline_01', 'qa_01', 'qa_invocation_01')
                       for p in (OUT / folder).rglob('*') if p.is_file())
    rows = []
    archive_path = OUT / 'RAW_ORIGINALS.zip'
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in raw_paths:
            assert path.resolve().is_relative_to(OUT.resolve())
            raw = path.read_bytes(); rel = path.relative_to(OUT).as_posix()
            archive.writestr(rel, raw)
            assert path.read_bytes() == raw
            rows.append(dict(path=rel, bytes=len(raw), sha256=sha(raw)))
    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == sorted(row['path'] for row in rows)
        for row in rows:
            raw = archive.read(row['path'])
            assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
            assert (OUT / row['path']).read_bytes() == raw
    put(OUT / 'RAW_ORIGINALS_INDEX.json', dict(archive=archive_path.name,
        archive_sha256=sha(archive_path.read_bytes()), files=rows, file_count=len(rows),
        source_deleted_or_moved=False, scope='all files including bytecode in the three original evidence directories'))
    turn = load(OUT / 'MANAGEMENT_START.json')
    started = datetime.fromtimestamp(turn['started_at_epoch_seconds'], timezone.utc)
    cutoff = datetime.now(timezone.utc)
    put(OUT / 'MANAGEMENT_CLOCK.json', dict(thread_id=turn['thread_id'], turn_id=turn['turn_id'],
        started_utc=started.isoformat(), cutoff_utc=cutoff.isoformat(), completed_utc=None,
        elapsed_through_cutoff_s=(cutoff-started).total_seconds(),
        start_through_QA_dispatch_s=(datetime.fromisoformat(outer['started_utc'])-started).total_seconds(),
        QA_end_through_cutoff_s=(cutoff-datetime.fromisoformat(outer['ended_utc'])).total_seconds(),
        scope='management elapsed lower bound including nested tests/preparation/QA and parallel audits; do not add intervals; commit/callback tail and earlier turns excluded'))
    put(OUT / 'PRESERVATION.json', dict(baseline_HEAD=BASE, candidate_commit=CANDIDATE,
        source_sha256=freeze['source_sha256'], old_markers_unchanged=protected,
        frozen_originals=rows, original_outputs_rewritten=False, source_deleted_or_moved=False,
        scope='only two product files, three necessary old test files, and new batch evidence; STATE/defaults/assets/other branches not written'))
    for row in rows:
        assert sha((OUT / row['path']).read_bytes()) == row['sha256']
    files = [(ROOT / rel) for rel in EXTERNAL]
    files += [p for p in OUT.rglob('*') if p.is_file() and p != index_path
              and '__pycache__' not in p.parts and p.suffix != '.pyc']
    entries = []
    for path in sorted(files):
        raw = path.read_bytes()
        entries.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=sha(raw)))
    assert len({row['path'] for row in entries}) == len(entries)
    put(index_path, dict(schema='degenerate-surface-001-evidence-index-v1', baseline_HEAD=BASE,
        candidate_commit=CANDIDATE, runtime_source_sha256=freeze['source_sha256'],
        path_base='repository', file_count=len(entries), files=entries,
        excludes=['EVIDENCE_INDEX.json (self)', 'direct __pycache__/** and *.pyc; original bytecode remains in RAW_ORIGINALS.zip']))
    print(json.dumps(dict(indexed_files=len(entries), raw_original_files=len(rows),
        report_sha256=sha((OUT / 'REPORT.md').read_bytes()), index_sha256=sha(index_path.read_bytes()))))


if __name__ == '__main__':
    main()
