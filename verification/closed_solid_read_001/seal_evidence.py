"""Seal the one finished source candidate and preserved verification attempts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[1]
BASE='4ca1fdb2882ae31da2fd3ec49ac77e1710c69a3e'
CANDIDATE='b60dd327e3926a06b73d77b37be7b63c50a3939a'
EXTERNAL=['human_eye_plugin/surface_geometry.py','human_eye_plugin/surface_proximity.py',
          'human_eye_plugin/task_query.py','human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/live_service.py']
sha=lambda data:hashlib.sha256(data).hexdigest()
load=lambda name:json.loads((OUT/name).read_bytes())


def put(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')


def main():
    index_path=OUT/'EVIDENCE_INDEX.json'; assert not index_path.exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==CANDIDATE
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT)
    frozen=load('SOURCE_FREEZE.json'); result=load('qa_01/RESULTS.json'); outer=load('qa_invocation_01/RESULT.json')
    assert frozen['candidate_commit']==CANDIDATE and frozen['source_sha256']=='1545da06b415864cf3f666f3a56432e91689d1a0565ea8589a19e3ecfff2b459'
    assert result['passed'] and result['original_contract_complete'] and result['original_contract_checks_passed']
    assert result['owned_sessions_attempted']==1 and result['product_attempts']==9 and result['total_RPC_attempts']==14
    assert outer['exit_code']==0 and outer['process_reaped']
    assert result['worker_closed']['qa_patch_applied'] and result['worker_closed']['poisoned'] is False
    assert load('REGRESSION_CLOSURE.json')['conservative_all_TCP_requests']==16
    assert load('offline_02/RESULTS.json')['passed'] and load('offline_03/RESULTS.json')['passed']
    assert not (OUT/'offline_01/RESULTS.json').exists() and not (OUT/'offline_01/EXECUTION_IDENTITY.json').exists()
    runtime_freeze=load('qa_01/FREEZE.json')
    assert sha((OUT/'qa_01/PLAN.json').read_bytes())==runtime_freeze['plan_sha256']
    for row in runtime_freeze['controllers']: assert sha(Path(row['path']).read_bytes())==row['sha256']
    for row in frozen['product_manifest']:
        raw=(ROOT/row['path']).read_bytes(); assert sha(raw)==row['sha256']
        assert raw==(Path(frozen['source_root'])/row['path']).read_bytes()
        assert raw==subprocess.check_output(['git','cat-file','blob',CANDIDATE+':'+row['path']],cwd=ROOT)
    for row in frozen['originals']:
        assert sha(Path(row['source_path']).read_bytes())==sha(Path(row['copy_path']).read_bytes())==row['sha256']
    protected=load('PROTECTED_BEFORE.json')['files']
    for row in protected:
        raw=(ROOT/row['path']).read_bytes(); assert sha(raw)==row['sha256']
        assert raw==subprocess.check_output(['git','cat-file','blob',BASE+':'+row['path']],cwd=ROOT)
    assert (OUT/'REPORT.md').exists() and (OUT/'ENTRY_AUDIT.json').exists() and (OUT/'CODE_REVIEW.json').exists()
    original_rows=[dict(path=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
        for directory in ('offline_01','offline_02','offline_03','qa_01','qa_invocation_01')
        for p in sorted((OUT/directory).rglob('*')) if p.is_file()]
    turn=load('MANAGEMENT_START.json'); start=datetime.fromtimestamp(turn['started_at_epoch_seconds'],timezone.utc)
    cutoff=datetime.now(timezone.utc); assert cutoff.timestamp()<turn['implementation_deadline_epoch_seconds']
    put('MANAGEMENT_CLOCK.json',dict(thread_id=turn['thread_id'],turn_id=turn['turn_id'],
        started_utc=start.isoformat(),cutoff_utc=cutoff.isoformat(),completed_utc=None,
        elapsed_through_cutoff_s=(cutoff-start).total_seconds(),
        start_through_QA_dispatch_s=(datetime.fromisoformat(outer['started_utc'])-start).total_seconds(),
        QA_end_through_cutoff_s=(cutoff-datetime.fromisoformat(outer['ended_utc'])).total_seconds(),
        implementation_deadline_epoch_seconds=turn['implementation_deadline_epoch_seconds'],
        scope='whole management lower bound includes nested development/tests/failed-attempt correction/QA/parallel review; final review, commit and callback tail excluded; do not sum'))
    put('PRESERVATION.json',dict(baseline_HEAD=BASE,candidate_commit=CANDIDATE,
        source_sha256=frozen['source_sha256'],old_markers_unchanged=protected,original_assets=frozen['originals'],
        frozen_originals=original_rows,original_outputs_rewritten=False,original_assets_written=False,
        actual_Blender_session=1,actual_scene_RPC=14,additional_local_mock_RPC=2,
        actual_public_observations=9,scope='five product source files and new own evidence only; old solver/asset/source failures/STATE/defaults/otherbranches preserved'))
    for row in original_rows:assert sha((OUT/row['path']).read_bytes())==row['sha256']
    paths=[ROOT/name for name in EXTERNAL]+[p for p in OUT.rglob('*') if p.is_file() and p!=index_path and '__pycache__' not in p.parts and p.suffix!='.pyc']
    entries=[]
    for path in sorted(paths):
        raw=path.read_bytes();entries.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=sha(raw)))
    assert len({row['path'] for row in entries})==len(entries)
    put('EVIDENCE_INDEX.json',dict(schema='closed-solid-read-001-evidence-index-v1',baseline_HEAD=BASE,
        candidate_commit=CANDIDATE,source_sha256=frozen['source_sha256'],path_base='repository',file_count=len(entries),
        files=entries,excludes=['EVIDENCE_INDEX.json(self)','direct __pycache__/**','*.pyc']))
    print(json.dumps(dict(indexed_files=len(entries),frozen_originals=len(original_rows),
        report_sha256=sha((OUT/'REPORT.md').read_bytes()),index_sha256=sha(index_path.read_bytes()))))


if __name__=='__main__':main()
