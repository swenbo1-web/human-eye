"""Seal the finished bounded capability batch; no new runtime checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = 'a4465a388b73ce144035d9139afb48f61519163a'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda name: json.loads((OUT / name).read_bytes())


def put(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf8', newline='\n')


def main():
    index_path = OUT / 'EVIDENCE_INDEX.json'; assert not index_path.exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip() == BASE
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT)
    freeze = load('SOURCE_FREEZE.json'); result = load('qa_01/RESULTS.json')
    outer = load('qa_invocation_01/RESULT.json'); runtime_freeze = load('qa_01/FREEZE.json')
    assert result['passed'] and result['capability_gap_observed']
    assert result['owned_sessions_attempted'] == 1 and result['product_attempts'] == 1 and result['total_RPC_attempts'] == 2
    assert result['gap_fact'] == dict(status='unknown', value=None, reason='unsupported_solid_geometry')
    assert sum(row['status'] == 'not_run' for row in result['schedule']) == 8
    assert outer['exit_code'] == 0 and outer['process_reaped']
    assert result['worker_closed']['qa_patch_applied'] is False
    assert sha((OUT/'qa_01/PLAN.json').read_bytes()) == runtime_freeze['plan_sha256']
    for row in runtime_freeze['controllers']:
        assert sha(Path(row['path']).read_bytes()) == row['sha256']
    for row in freeze['product_manifest']:
        raw = (ROOT / row['path']).read_bytes()
        assert sha(raw) == row['sha256'] and raw == (Path(freeze['source_root'])/row['path']).read_bytes()
        assert raw == subprocess.check_output(['git','cat-file','blob',BASE+':'+row['path']],cwd=ROOT)
    for row in freeze['originals']:
        assert sha(Path(row['source_path']).read_bytes()) == sha(Path(row['copy_path']).read_bytes()) == row['sha256']
    protected = load('PROTECTED_BEFORE.json')['files']
    for row in protected:
        raw = (ROOT / row['path']).read_bytes()
        assert sha(raw) == row['sha256']
        assert raw == subprocess.check_output(['git','cat-file','blob',BASE+':'+row['path']],cwd=ROOT)
    assert (OUT/'ENTRY_AUDIT.json').exists() and (OUT/'REPORT.md').exists()
    originals = [dict(path=p.relative_to(OUT).as_posix(), bytes=p.stat().st_size, sha256=sha(p.read_bytes()))
                 for dirname in ('qa_01','qa_invocation_01') for p in sorted((OUT/dirname).rglob('*')) if p.is_file()]
    turn = load('MANAGEMENT_START.json'); start = datetime.fromtimestamp(turn['started_at_epoch_seconds'],timezone.utc)
    now = datetime.now(timezone.utc)
    assert now.timestamp() < turn['implementation_deadline_epoch_seconds']
    put('MANAGEMENT_CLOCK.json',dict(thread_id=turn['thread_id'],turn_id=turn['turn_id'],
        started_utc=start.isoformat(),cutoff_utc=now.isoformat(),completed_utc=None,
        elapsed_through_cutoff_s=(now-start).total_seconds(),
        start_through_dispatch_s=(datetime.fromisoformat(outer['started_utc'])-start).total_seconds(),
        QA_end_through_cutoff_s=(now-datetime.fromisoformat(outer['ended_utc'])).total_seconds(),
        implementation_deadline_epoch_seconds=turn['implementation_deadline_epoch_seconds'],
        scope='whole management lower bound including nested preparation/failure/QA/parallel audits; commit/review/callback tail excluded; do not sum'))
    put('PRESERVATION.json',dict(baseline_HEAD=BASE,old_markers_unchanged=protected,
        original_assets=freeze['originals'],frozen_QA_originals=originals,
        product_source_changed=False,original_outputs_rewritten=False,original_assets_written=False,
        actual_public_observations=1,actual_physical_RPC=2,remaining_observations_not_run=8,
        scope='only new complex_reentry_001 evidence; STATE/helper/source/defaults/otherbranches unchanged'))
    for row in originals:
        assert sha((OUT/row['path']).read_bytes()) == row['sha256']
    entries=[]
    for path in sorted(OUT.rglob('*')):
        if not path.is_file() or path == index_path or '__pycache__' in path.parts or path.suffix == '.pyc': continue
        raw=path.read_bytes(); entries.append(dict(path=path.relative_to(OUT).as_posix(),bytes=len(raw),sha256=sha(raw)))
    put('EVIDENCE_INDEX.json',dict(schema='complex-reentry-001-evidence-index-v1',baseline_HEAD=BASE,
        source_sha256=freeze['source_sha256'],path_base='verification/complex_reentry_001',file_count=len(entries),
        excludes=['EVIDENCE_INDEX.json(self)','__pycache__/**','*.pyc'],files=entries))
    print(json.dumps(dict(file_count=len(entries),raw_originals=len(originals),
        report_sha256=sha((OUT/'REPORT.md').read_bytes()),index_sha256=sha(index_path.read_bytes()))))


if __name__ == '__main__': main()
