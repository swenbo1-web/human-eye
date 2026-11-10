"""Seal raw fixed-run and anonymous artifacts; never score or compare arms."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
read=lambda path:json.loads(path.read_bytes())


def save(path,value):
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=True)
        stream.write('\n')


def main():
    plan=read(BATCH/'PLAN.json');go=read(BATCH/'GO.json');run=read(BATCH/'RUN_RESULT.json')
    ready=read(BATCH/'quality_handoff/FORMAL_QUALITY_READY.json')
    assert go['authorized'] is True and go['max_consumers']==6
    assert go['plan_sha256']==sha(BATCH/'PLAN.json')=='376339732b468fd1eb2c6008f2b97141ffdd6c7902fc047adb3facce15cf4619'
    assert len(run['records'])==6 and run['stop'] is None and run['all_planned_dispatched'] is True
    assert all(all(row[key]==slot[key] for key in ('cell','task','group','round'))
        for slot,row in zip(plan['sequence'],run['records'],strict=True))
    assert ready['status']=='FORMAL_QUALITY_READY' and ready['quality_scored'] is False
    assert ready['started_consumers']==ready['unique_recorded_threads']==6
    assert ready['recorded_consumer_exit_zero']==ready['recorded_consumer_process_reaped']==6
    assert ready['recorded_consumer_valid_completion']==6
    assert ready['owner_backend_close_confirmed']==6 and ready['unstarted_tail']==0
    assert sha(BATCH/'quality_handoff/pack_quality.py')==ready['packager_sha256']=='afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc'
    for name,digest in plan['dispatch_input_sha256'].items():assert sha(BATCH/name)==digest,name
    preparation=read(BATCH/'ARTIFACT_INDEX.json')
    for row in preparation['files']:
        path=ROOT/row['path']
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],row['path']
    package=BATCH/'quality_handoff/handoff_01'
    provenance=read(package/'private/PROVENANCE.json')
    assert provenance['script_sha256']==ready['packager_sha256']
    public={p.relative_to(package/'public').as_posix():sha(p) for p in (package/'public').rglob('*') if p.is_file()}
    assert public==provenance['public_files_sha256'] and len(public)==28
    assert sha(package/'public/INDEX.json')==ready['public_INDEX_sha256']
    assert sha(package/'private/PROVENANCE.json')==ready['private_PROVENANCE_sha256']
    for check in ready['integrity_reviews']:
        assert sha(BATCH/check['file'])==check['sha256'] and check['failures']==0
    assert read(HERE/'private/QUALITY_INTEGRITY_TESTS.json')['passed'] is True
    assert not read(HERE/'private/QUALITY_INTEGRITY_ARCHITECTURE.json')['issues']
    assert read(HERE/'private/PID_QUERY.json')['all_recorded_pids_absent'] is True
    paths=[BATCH/name for name in ('GO.json','GO_PROVENANCE.json','STARTED.json','RUN_RESULT.json',
        'quality_handoff/FORMAL_QUALITY_READY.json')]
    duplicates=[]
    for slot in plan['sequence']:
        cell=BATCH/'cells'/slot['cell']
        for path in cell.rglob('*'):
            if not path.is_file():continue
            if path.name=='input.blend' and path.parent.name=='native':
                assert sha(path)==plan['inputs']['scene_sha256']
                duplicates.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,
                    'sha256':sha(path),'preserved_in':'same original raw-cell member in the frozen anonymous private ZIP plus local copy'})
            else:paths.append(path)
    excluded={'EXECUTION_ARTIFACT_INDEX.json','EXECUTION_SEAL.json'}
    for folder in (HERE,package):
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.name not in excluded:paths.append(path)
    paths=sorted(set(paths))
    assert len(duplicates)==6
    files=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]
    index={'cycle_id':plan['cycle_id'],'phase':'FORMAL_QUALITY_READY','file_count':len(files),
        'bytes':sum(row['bytes'] for row in files),'files':files,
        'duplicate_native_inputs_retained_locally_and_private_zip':duplicates,
        'policy':'all raw execution and first anonymous package retained; no failure replacement, scoring or arm/cost ranking; repeated native input assets stay local and in original raw ZIP, not duplicated as loose Git paths'}
    save(HERE/'EXECUTION_ARTIFACT_INDEX.json',index)
    seal={'cycle_id':plan['cycle_id'],'status':'FORMAL_QUALITY_READY','preparation_commit':go['preparation_commit'],
        'source_sha256':plan['candidate_source_sha256'],'source_count':137,
        'PLAN_sha256':sha(BATCH/'PLAN.json'),'GO_sha256':sha(BATCH/'GO.json'),
        'preparation_FREEZE_sha256':sha(BATCH/'FREEZE.json'),
        'public_INDEX_sha256':sha(package/'public/INDEX.json'),
        'private_PROVENANCE_sha256':sha(package/'private/PROVENANCE.json'),
        'quality_ready_sha256':sha(BATCH/'quality_handoff/FORMAL_QUALITY_READY.json'),
        'execution_artifact_index_sha256':sha(HERE/'EXECUTION_ARTIFACT_INDEX.json'),
        'indexed_files':len(files),'indexed_bytes':index['bytes'],
        'logical_denominator':6,'started_consumers':6,'replacements':0,'unstarted_tail':0,
        'quality_scored':False,'group_correctness_or_cost_comparison_published':False,
        'thin_missing_EXIT_receipts':6,'thin_exit_status':'unknown; not promoted by PID absence',
        'provider_image_receipt':None,'model_view_confirmed':None,
        'old_preparation_index_entries_unchanged':len(preparation['files']),
        'report':'verification/m4_observation_baseline_001/formal_run/QUALITY_READY_REPORT.md'}
    save(HERE/'EXECUTION_SEAL.json',seal)
    print(json.dumps({key:seal[key] for key in ('cycle_id','status','logical_denominator','started_consumers',
        'quality_scored','indexed_files','indexed_bytes','execution_artifact_index_sha256')},ensure_ascii=True))


if __name__=='__main__':main()
