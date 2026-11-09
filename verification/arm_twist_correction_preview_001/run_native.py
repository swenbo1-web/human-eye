"""Root invokes one fresh Blender QA; this launcher owns and closes its PID."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
out=Path(sys.argv[1]).resolve()
if out.exists() and any(out.iterdir()):raise ValueError('new_output_directory_required_do_not_overwrite_evidence')
out.mkdir(parents=True,exist_ok=True)
names=['human_eye_plugin/'+name for name in ('arm_twist_correction.py','arm_twist_source.py','arm_twist_expert.py',
    'arm_twist_weights.py','rig_pose.py')]
names+=['verification/m6_arm_expert_001/synthetic.py']
names+=['verification/arm_twist_correction_preview_001/'+name for name in ('cases.py','oracle.py','native_probe.py','run_native.py')]
freeze={'schema':'arm-correction-native-source-freeze-v1',
    'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names},
    'native_gates':{'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5},
    'cases':'existing_fixed_four_positives_of_eight_cases_only','product_setters':0}
(out/'SOURCE_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n',encoding='utf8',newline='\n')
command=['D:/Tools/blender5.2/blender.exe','--factory-startup','--disable-autoexec','--background',
    '--python-exit-code','12','--python',str(HERE/'native_probe.py'),'--',str(out),str(ROOT)]
process=None;started=time.perf_counter_ns()
try:
    with (out/'blender.log').open('wb') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (out/'process.json').write_text(json.dumps({'pid':process.pid,'command':command},indent=2)+'\n',encoding='utf8',newline='\n')
        code=process.wait(timeout=60)
    result_path=out/'RESULT.json'
    result=json.loads(result_path.read_text(encoding='utf8')) if result_path.is_file() else {}
    if code or not result.get('passed'):raise RuntimeError('Native feasibility failed; retain '+str(out))
    print(json.dumps({'passed':True,'cases':len(result['cases']),'pid':process.pid,'returncode':code,
        'result':str(result_path)}))
finally:
    if process is not None:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        record={'pid':process.pid,'returncode':process.returncode,'closed':process.poll() is not None,
            'launcher_elapsed_ns':time.perf_counter_ns()-started}
    else:record={'pid':None,'started':False,'closed':True,'launcher_elapsed_ns':time.perf_counter_ns()-started}
    (out/'process_exit.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8',newline='\n')
