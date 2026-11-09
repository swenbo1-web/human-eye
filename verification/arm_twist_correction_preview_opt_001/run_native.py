"""Root launches one owned fresh Blender source->preview check and closes it."""
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
# Same enumeration rule as runtime_identity; all runtime source bytes are frozen
# without importing the product or starting Blender in this controller.
names=['human_eye_hook.py','human_eye_foveated_renderer.py','native_3d_spatial_scratchpad.py',
    'module_2_low_token_mcp_scene_bridge.py','module_3_1_mcp_protocol_ipc_engine.py',
    'module_3_2_vlm_grounding_closed_loop_agent.py','module_3_3_closed_loop_control_engine.py']
for package in ('human_eye_plugin','human_eye_module1_operators'):
    names.extend(path.relative_to(ROOT).as_posix() for path in (ROOT/package).glob('*.py'))
runtime_names=sorted(set(names))
names+=['verification/m6_arm_expert_001/synthetic.py']
names+=['verification/arm_twist_correction_preview_001/'+name for name in ('cases.py','oracle.py','native_probe.py')]
names+=['verification/arm_twist_correction_preview_opt_001/'+name for name in ('native_probe.py','run_native.py')]
freeze={'schema':'arm-correction-opt-native-source-freeze-v1','runtime_source_files':runtime_names,
    'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(names))},
    'native_gates':{'angle_deg':.001,'position_m':5e-6,'section_area_loss':2e-5},
    'preview_tolerances':{'angle_tolerance_deg':.001,'position_tolerance_m':5e-6,'area_tolerance':1e-6},
    'cases':'same_fixed_eight_cases_actual_BlenderSceneHost_ArmTwistSource_capture_to_preview',
    'product_setters':0,'qa_normalizers':0}
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
    if code or not result.get('passed'):raise RuntimeError('Native source-to-preview check failed; retain '+str(out))
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
