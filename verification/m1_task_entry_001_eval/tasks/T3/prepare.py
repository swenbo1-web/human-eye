"""Create and certify only this task's new owned background fixture."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
BLENDER=Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA='284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
seal=json.loads((HERE/'FREEZE.json').read_bytes())
assert sha(BLENDER)==BLENDER_SHA
for name,digest in seal['source_sha256'].items(): assert sha(HERE/name)==digest
RUN=HERE/'runs/prepare_01'
RUN.mkdir(parents=True,exist_ok=False)
records=[]


def run(label,command):
    record={'label':label,'command':command,'cwd':str(HERE),'timeout_s':120,
        'started_utc':datetime.now(timezone.utc).isoformat(),'started_ns':time.perf_counter_ns(),
        'spawned':False,'timed_out':False,'returncode':None}
    output=error=b''
    try:
        process=subprocess.Popen(command,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        record['spawned']=True;record['pid']=process.pid
        try: output,error=process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            record['timed_out']=True
            process.kill()
            output,error=process.communicate(timeout=30)
        record['returncode']=process.returncode
    except BaseException as exc:
        record['exception']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        record.update(ended_utc=datetime.now(timezone.utc).isoformat(),ended_ns=time.perf_counter_ns())
        (RUN/(label+'.stdout.txt')).write_bytes(output)
        (RUN/(label+'.stderr.txt')).write_bytes(error)
        (RUN/(label+'.process.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
        records.append(record)
    assert record['returncode']==0 and not record['timed_out'],record


try:
    run('01_build',[str(BLENDER),'--background','--factory-startup','--disable-autoexec','--python',str(HERE/'build_asset.py'),
        '--','--spec',str(HERE/'SPEC.json'),'--output',str(HERE/'assets/scene.blend')])
    run('02_read_saved',[str(BLENDER),'--background',str(HERE/'assets/scene.blend'),'--disable-autoexec',
        '--python',str(HERE/'export_evaluated.py'),'--','--output',str(HERE/'assets/evaluated_mesh.json')])
    bootstrap='import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")'
    run('03_independent_truth',[sys.executable,'-I','-B','-X','utf8','-c',bootstrap,str(HERE),str(HERE/'certify.py'),
        '--spec',str(HERE/'SPEC.json'),'--snapshot',str(HERE/'assets/evaluated_mesh.json'),'--output',str(HERE/'TRUTH.json')])
    run('04_replay',[sys.executable,'-I','-B','-X','utf8',str(HERE/'replay.py'),'--output','REPLAY.json'])
    finished={'successful':True,'frozen_before_any_asset_process':seal,
        'blender_binary_sha256':BLENDER_SHA,'python':sys.executable,'python_binary_sha256':sha(Path(sys.executable)),
        'asset_sha256':sha(HERE/'assets/scene.blend'),'evaluated_snapshot_sha256':sha(HERE/'assets/evaluated_mesh.json'),
        'truth_sha256':sha(HERE/'TRUTH.json'),'replay_truth_equal':(HERE/'TRUTH.json').read_bytes()==(HERE/'REPLAY.json').read_bytes(),
        'source_unchanged':all(sha(HERE/name)==digest for name,digest in seal['source_sha256'].items()),
        'all_processes_exited':all(record['returncode']==0 for record in records),
        'owned_background_blender_processes':2,'GUI_access':False,'model_calls':0,'production_preflight_calls':0,
        'process_records':records}
    with (HERE/'READY.json').open('x',encoding='utf8') as stream: json.dump(finished,stream,indent=2);stream.write('\n')
    print(json.dumps({'ready':True,'task_directory':str(HERE),'asset_sha256':finished['asset_sha256']}))
finally:
    (RUN/'ALL_PROCESS_RECORDS.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
