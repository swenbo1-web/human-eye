"""Build/install fixed A/B Git bytes into independent test venvs.

No formal installation, model process, Blender process or project source edit.
Dependency wheels are shared, pinned inputs; application installations are not.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUNTIME=ROOT/'.plugin_ab_runtime'
PYTHON=Path('C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe')
COMMITS={'A':'a3a72b929f55c40f195ff5e1a9f64ceb303b6360',
         'B':'d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d'}
PINS=['numpy==2.3.5','Pillow==12.3.0','setuptools==80.9.0','wheel==0.45.1']
ROOT_MODULES=('human_eye_hook.py','human_eye_foveated_renderer.py','native_3d_spatial_scratchpad.py',
              'module_2_low_token_mcp_scene_bridge.py','module_3_1_mcp_protocol_ipc_engine.py',
              'module_3_2_vlm_grounding_closed_loop_agent.py','module_3_3_closed_loop_control_engine.py')
REPORT={'schema':'plugin-version-llm-ab-installed-v1','passed':False,'commands':[],
        'versions':{},'dependency_pins':PINS,'models_started':0,'Blender_started':0}
ENV=dict(os.environ)
for key in ('PYTHONPATH','PYTHONHOME'):ENV.pop(key,None)
ENV['PYTHONDONTWRITEBYTECODE']='1'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8',newline='\n')


def run(label,args,*,cwd=HERE):
    started=time.perf_counter_ns();log=HERE/'install_logs'/f'{len(REPORT["commands"])+1:02}_{label}.log'
    log.parent.mkdir(exist_ok=True)
    proc=subprocess.run([str(a) for a in args],cwd=cwd,env=ENV,capture_output=True)
    log.write_bytes(proc.stdout+b'\n---STDERR---\n'+proc.stderr)
    row={'label':label,'argv':[str(a) for a in args],'cwd':str(cwd),
         'elapsed_ns':time.perf_counter_ns()-started,'returncode':proc.returncode,
         'log':str(log.relative_to(ROOT)),'log_sha256':sha(log)}
    REPORT['commands'].append(row);save(HERE/'INSTALL_PARTIAL.json',REPORT)
    if proc.returncode:raise RuntimeError(f'{label} returned {proc.returncode}; see {log}')
    return proc.stdout


def extract(label,commit):
    source=RUNTIME/label/'source';source.mkdir(parents=True,exist_ok=False)
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',commit],cwd=ROOT,text=True).splitlines()
    runtime=[n for n in names if n in ROOT_MODULES or (
        n.startswith(('human_eye_plugin/','human_eye_module1_operators/')) and n.count('/')==1 and n.endswith('.py'))]
    assert len(runtime)==137,len(runtime)
    wanted=runtime+['pyproject.toml','README.md','human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json']
    members={}
    for name in wanted:
        blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
        members[name]={'sha256':sha(dest),'bytes':len(blob),'runtime':name in runtime}
    return source,members


def main():
    if RUNTIME.exists():raise RuntimeError('owned_runtime_must_be_new')
    RUNTIME.mkdir()
    REPORT['runtime_root']=str(RUNTIME)
    report_started=time.perf_counter_ns()
    try:
        run('create_builder',[PYTHON,'-I','-B','-X','utf8','-m','venv',RUNTIME/'builder'])
        builder=RUNTIME/'builder/Scripts/python.exe'
        wheelhouse=RUNTIME/'dependency_wheels';wheelhouse.mkdir()
        run('download_pinned_dependencies',[builder,'-I','-B','-X','utf8','-m','pip','download',
            '--only-binary=:all:','--dest',wheelhouse,*PINS])
        REPORT['dependency_wheels']={f.name:{'sha256':sha(f),'bytes':f.stat().st_size}
            for f in wheelhouse.glob('*.whl')}
        run('install_builder_tools',[builder,'-I','-B','-X','utf8','-m','pip','install','--no-index',
            '--find-links',wheelhouse,'setuptools==80.9.0','wheel==0.45.1'])
        for label,commit in COMMITS.items():
            started=time.perf_counter_ns();source,members=extract(label,commit)
            wheels=HERE/'wheels'/label;wheels.mkdir(parents=True,exist_ok=False)
            run('build_'+label,[builder,'-I','-B','-X','utf8','-m','pip','wheel','--no-deps',
                '--no-build-isolation','--wheel-dir',wheels,source])
            files=list(wheels.glob('*.whl'));assert len(files)==1
            wheel=files[0]
            venv=RUNTIME/label/'venv'
            run('create_venv_'+label,[PYTHON,'-I','-B','-X','utf8','-m','venv',venv])
            python=venv/'Scripts/python.exe'
            run('install_'+label,[python,'-I','-B','-X','utf8','-m','pip','install','--no-index',
                '--find-links',wheelhouse,wheel,'numpy==2.3.5','Pillow==12.3.0'])
            raw=run('probe_'+label,[python,'-I','-B','-X','utf8',HERE/'probe_install.py'])
            proof=json.loads(raw)
            assert proof['isolated'] and proof['source_kind']=='installed_distribution',proof
            assert proof['distribution_version']=='9.7.2' and len(proof['runtime_identity']['source_files'])==137
            assert Path(proof['plugin_file']).is_relative_to(venv)
            for member in proof['runtime_identity']['source_files']:
                assert member['sha256']==members[member['path']]['sha256'],member
            freeze=run('freeze_'+label,[python,'-I','-B','-X','utf8','-m','pip','freeze','--all']).decode('utf8')
            (HERE/f'FREEZE_{label}.txt').write_text(freeze,encoding='utf8',newline='\n')
            REPORT['versions'][label]={'commit':commit,'source_root':str(source),'source_members':members,
                'python':str(python),'venv':str(venv),'installed_root':proof['site_root'],
                'wheel':str(wheel.relative_to(ROOT)),'wheel_sha256':sha(wheel),'wheel_bytes':wheel.stat().st_size,
                'elapsed_ns':time.perf_counter_ns()-started,'proof':proof}
            save(HERE/'INSTALL_PARTIAL.json',REPORT)
        assert REPORT['versions']['A']['proof']['numpy_version']==REPORT['versions']['B']['proof']['numpy_version']=='2.3.5'
        assert REPORT['versions']['A']['proof']['pillow_version']==REPORT['versions']['B']['proof']['pillow_version']=='12.3.0'
        REPORT['passed']=True
    except BaseException as exc:
        REPORT['failure']={'type':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        REPORT['total_elapsed_ns']=time.perf_counter_ns()-report_started
        REPORT['script_sha256']=sha(Path(__file__))
        save(HERE/'INSTALL_RESULT.json',REPORT)
        print(json.dumps({'passed':REPORT['passed'],'versions':list(REPORT['versions']),
            'result':str(HERE/'INSTALL_RESULT.json')}))


if __name__=='__main__':main()
