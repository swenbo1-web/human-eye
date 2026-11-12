"""Own a factory builder and one registered-pose QA process through reap."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import traceback

HERE=Path(__file__).resolve().parent
QUAL=HERE.parent/'qualification'
BLENDER=Path('D:/Tools/blender5.2/blender.exe')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')

def main():
    started=time.perf_counter_ns()
    save(HERE/'STARTED.json',{'started_ns':started,'started_utc':datetime.now(timezone.utc).isoformat(),
         'freeze_sha256':sha(QUAL/'GEOMETRY_FREEZE.json'),'builder_sha256':sha(QUAL/'build_asset.py'),
         'helper_sha256':sha(HERE/'pose_native.py'),'export_sha256':sha(QUAL/'export_snapshot.py'),
         'pose_patch_sha256':sha(HERE/'POSE_PATCH.json'),'blender_sha256':sha(BLENDER)})
    builder=None;qa=None;errors=[];build_record=None;close=None
    try:
        argv=[str(BLENDER),'--factory-startup','--disable-autoexec','--background','--python-exit-code','1',
              '--python',str(QUAL/'build_asset.py')]
        mark=time.perf_counter_ns()
        with (HERE/'builder_stdout.bin').open('xb') as out,(HERE/'builder_stderr.bin').open('xb') as err:
            builder=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            save(HERE/'BUILDER_STARTED.json',{'pid':builder.pid,'argv':argv,'started_ns':mark})
            try:builder.wait(timeout=90)
            finally:
                if builder.poll() is None:builder.kill();builder.wait(timeout=5)
            build_record={'pid':builder.pid,'exit_code':builder.returncode,'process_reaped':True,
                          'elapsed_ns':time.perf_counter_ns()-mark}
            save(HERE/'BUILDER_CLOSED.json',build_record)
            assert builder.returncode==0
        spec=importlib.util.spec_from_file_location('_surface_scan_pose_fixture',HERE/'pose_native.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        qa=helper.NativeSession.start(blender=BLENDER,asset=QUAL/'assembly.blend',workspace=HERE/'qa',
             deadline_ns=time.perf_counter_ns()+180*10**9,condition='N',max_calls=12,
             qa_vertex_patch=HERE/'POSE_PATCH.json',expected_asset_sha256=sha(QUAL/'assembly.blend'))
        code=(QUAL/'export_snapshot.py').read_text(encoding='utf8')
        for state in ('base','edit'):
            if state=='edit':
                advance=qa.qa_advance(timeout_s=30)
                save(HERE/'POSE_ADVANCE.json',advance)
            receipt=qa.run(code,timeout_s=30)
            save(HERE/(state+'_EXPORT_RECEIPT.json'),receipt)
            assert receipt['response']['status']=='success'
            snapshot=json.loads(receipt['response']['result']['result'])
            assert snapshot['counts']=={'objects':24,'vertices':530,'triangles':978}
            save(QUAL/(state.upper()+'_SNAPSHOT.json'),snapshot)
    except BaseException as error:
        errors.append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
        save(HERE/'FAILURE.json',{'errors':errors})
        raise
    finally:
        if qa is not None:
            close=qa.close();save(HERE/'QA_CLOSE.json',close)
        if builder is not None and builder.poll() is None:builder.kill();builder.wait(timeout=5)
        save(HERE/'PREPARATION.json',{'started_ns':started,'ended_ns':time.perf_counter_ns(),
             'elapsed_ns':time.perf_counter_ns()-started,'builder':build_record,'qa_close':close,
             'errors':errors,'owned_Blender_processes':int(builder is not None)+int(qa is not None),
             'model_consumers':0,'product_runs':0,'images':0})
    assert close['process_reaped'] and close['exit_code']==0 and close['error'] is None
    print(json.dumps({'prepared_states':2,'objects':24,'triangles':978,'workers_reaped':True}))

if __name__=='__main__':main()
