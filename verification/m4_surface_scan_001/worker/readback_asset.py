"""Recover export of the unchanged built asset using the repaired pose fixture."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback

HERE=Path(__file__).resolve().parent
QUAL=HERE.parent/'qualification'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')

def main():
    started=time.perf_counter_ns();qa=None;close=None;errors=[]
    asset_sha=sha(QUAL/'assembly.blend')
    save(HERE/'STARTED.json',{'started_ns':started,'started_utc':datetime.now(timezone.utc).isoformat(),
         'asset_sha256':asset_sha,'helper_sha256':sha(HERE/'pose_native.py'),
         'export_sha256':sha(QUAL/'export_snapshot.py'),'pose_patch_sha256':sha(HERE/'POSE_PATCH.json'),
         'recovery':'Existing factory asset, initial failed QA attempt preserved under attempt_01.'})
    try:
        spec=importlib.util.spec_from_file_location('_surface_scan_pose_fixture',HERE/'pose_native.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        qa=helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe',asset=QUAL/'assembly.blend',
             workspace=HERE/'qa',deadline_ns=time.perf_counter_ns()+180*10**9,condition='N',max_calls=12,
             qa_pose_patch=HERE/'POSE_PATCH.json',expected_asset_sha256=asset_sha)
        code=(QUAL/'export_snapshot.py').read_text(encoding='utf8')
        for state in ('base','edit'):
            if state=='edit':save(HERE/'POSE_ADVANCE.json',qa.qa_advance(timeout_s=30))
            receipt=qa.run(code,timeout_s=30);save(HERE/(state+'_EXPORT_RECEIPT.json'),receipt)
            assert receipt['response']['status']=='success',receipt['response']
            snapshot=json.loads(receipt['response']['result']['result'])
            assert snapshot['counts']=={'objects':24,'vertices':530,'triangles':978}
            save(QUAL/(state.upper()+'_SNAPSHOT.json'),snapshot)
        assert sha(QUAL/'assembly.blend')==asset_sha
    except BaseException as error:
        errors.append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
        save(HERE/'FAILURE.json',{'errors':errors});raise
    finally:
        if qa is not None:close=qa.close();save(HERE/'QA_CLOSE.json',close)
        save(HERE/'PREPARATION.json',{'started_ns':started,'ended_ns':time.perf_counter_ns(),
             'elapsed_ns':time.perf_counter_ns()-started,'qa_close':close,'errors':errors,
             'this_attempt_owned_Blender_processes':int(qa is not None),'previous_attempt':'attempt_01/PREPARATION.json',
             'total_owned_Blender_processes':3,'model_consumers':0,'product_runs':0,'images':0})
    assert close['process_reaped'] and close['exit_code']==0 and close['error'] is None
    print(json.dumps({'states_exported':2,'asset_sha256':asset_sha,'process_reaped':True}))

if __name__=='__main__':main()
