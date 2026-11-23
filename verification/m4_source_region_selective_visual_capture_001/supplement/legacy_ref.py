"""Check the candidate's standard same-session image and region_ref once, after formal."""
from argparse import ArgumentParser
from base64 import b64decode
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns,sleep
from zipfile import ZIP_DEFLATED, ZipFile

HERE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(HERE))
import experiment as trial

ROOT=Path('D:/he_m4_source_region_selective_visual_capture_001_post_legacy_ref')
PREVIOUS=ROOT/'A'
SLOT=ROOT/'roundtrip'/'A'


def replay_worker(deadline):
    import replay
    original=replay.installed_connector
    production_root=replay.ROOT

    def installed_candidate_under_standard_route(path,label):
        # Keep the original installed B's source attestation, but accept only
        # standard capture requests in this separate control.
        assert path==trial.B_BINDING and label=='A'
        replay.ROOT=production_root
        try:
            return original(path,'B')
        finally:
            replay.ROOT=ROOT
    replay.ROOT=ROOT
    replay.installed_connector=installed_candidate_under_standard_route
    from types import SimpleNamespace
    replay.run(SimpleNamespace(workspace=SLOT/'native',terminal=trial.TERMINAL,asset=trial.FIXTURE,
        asset_sha256=trial.ASSET,deadline_ns=deadline,label='A',binding=trial.B_BINDING))


def main():
    SLOT.mkdir(parents=True,exist_ok=False)
    reference=trial.reference_inputs()
    binding_path,binding=trial.assert_install('B')
    native=SLOT/'native'
    native.mkdir()
    until=perf_counter_ns()+90*10**9
    worker=trial.start_worker([str(trial.PYTHON),'-IB','-X','utf8',str(Path(__file__).resolve()),
         '--worker',str(until)],native,'REPLAY',stdin=subprocess.DEVNULL)
    mcp=session=None
    try:
        while not (native/'READY.json').is_file():
            trial.need(worker.poll() is None,'legacy_replay_exit_before_ready')
            trial.left(until)
            sleep(.01)
        ready=trial.load(native/'READY.json')
        trial.need(ready['pid']==worker.pid and ready['host']=='127.0.0.1' and ready['deadline_ns']==until,
            'legacy_replay_pid_or_scope')
        session=trial.NativeSession()
        session.process,session.workspace,session.ready=worker,native,ready
        session.config={**ready,'asset':str(trial.FIXTURE),'asset_copy':str(native/'input.blend'),
                        'asset_sha256':trial.ASSET,'protected_public_images':[]}
        cfg=SLOT/'PRODUCT_CONFIG.json'
        trial.save(cfg,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
            'expected_identity':{'source_sha256':binding['source_sha256']},'project_root':binding['install_root'],
            'state_file':str(SLOT/'product_state.json'),'audit_file':str(SLOT/'product_audit.jsonl'),
            'request_budget_s':30,'blender':{'host':session.host,'port':session.port,'timeout_s':30}})
        mcp=trial.Stdio('A',SLOT,binding_path,cfg,until)
        hello,*_=mcp.request(1,'initialize',{})
        assert hello['_meta']['human_eye']['source_sha256']==binding['source_sha256']
        old=reference['M21']['query']
        def observe(seq,query):
            result,*_=mcp.request(seq,'tools/call',{'name':'human_eye_scene_observe','arguments':{
                'query':query,'include_image':True,'response_detail':'full'}})
            trial.need(not result['isError'],'candidate_standard_read_error/'+str(result)[:1200])
            images=[block for block in result['content'] if block['type']=='image']
            assert len(images)==1
            return b64decode(images[0]['data'],validate=True)
        first=observe(2,old)
        p=trial.load(SLOT/'PRODUCER_1.json')
        region=p['region_ref']
        assert region['schema']=='human-eye-source-region-ref-v1'
        second=observe(3,{'mode':'source_region','region_ref':region,'reference':old['reference'],
                          'requested_facts':old['requested_facts']})
        q=trial.load(SLOT/'PRODUCER_2.json')
        assert first==second==reference['M21']['png'].read_bytes()
        assert q['region_ref']==region and p['frames']==q['frames'] and q['work']['raster_attempts']==0
        assert p['task_result']['facts']==q['task_result']['facts']
    finally:
        try:
            if mcp is not None:
                mcp_close=mcp.close()
        finally:
            if session is not None:
                closed=session.close()
            else:
                if worker.poll() is None:
                    worker.kill()
                worker.wait(timeout=3)
    assert mcp_close['confirmed'] and closed['process_reaped'] and closed['exit_code']==0
    trial.save(SLOT/'CLOSE.json',{'mcp':mcp_close,'native':closed})
    trial.save(ROOT/'RESULT.json',{'passed':True,'phase':'post_formal_candidate_default_legacy_ref_roundtrip',
        'actual_Blender':0,'model_calls':0,'software_raster_calls':1,'full_image_calls':2,'warm_ref_rasters':0,
        'same_historical_original_png':True,'image_bytes':len(first),'old_ref_schema':region['schema'],
        'runtime_sha256':binding['source_sha256'],'previous_namespace_admission_failure_retained':PREVIOUS.is_dir()})
    members=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()]
    with ZipFile(ROOT/'ORIGINAL_RUNTIME.zip','x',compression=ZIP_DEFLATED) as z:
        for p in members:
            z.write(p,p.relative_to(ROOT).as_posix())
    with ZipFile(ROOT/'ORIGINAL_RUNTIME.zip') as z:
        assert z.testzip() is None
        assert all(z.read(p.relative_to(ROOT).as_posix())==p.read_bytes() for p in members)
    print({'legacy':trial.load(ROOT/'RESULT.json'),'archive_members':len(members),
           'archive_sha256':trial.digest((ROOT/'ORIGINAL_RUNTIME.zip').read_bytes())})


if __name__=='__main__':
    parser=ArgumentParser()
    parser.add_argument('--worker',type=int)
    args=parser.parse_args()
    if args.worker is None:
        main()
    else:
        replay_worker(args.worker)
