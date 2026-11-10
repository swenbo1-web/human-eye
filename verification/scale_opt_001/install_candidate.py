"""Build one SCALE-OPT-001 wheel and isolated installation after root readiness.

The default mode is a read-only plan.  --build requires the root's fixed source
SHA.  The existing O environment and dependency wheelhouse are read, never
copied or installed into.  No Blender, model or performance task is launched.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
RUNTIME=ROOT/'.scale_opt_001_runtime'
OLD=ROOT/'.plugin_ab_runtime/B/venv'
BUILDER=ROOT/'.plugin_ab_runtime/builder/Scripts/python.exe'
WHEELHOUSE=ROOT/'.plugin_ab_runtime/dependency_wheels'
BASELINE_COMMIT='b39a5d9f58aed2782225287738413982beac4920'
OLD_CANONICAL='a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b'
SURFACE='human_eye_plugin/surface_proximity.py'
PINS={'numpy':'2.3.5','Pillow':'12.3.0'}
ROOT_MODULES=('human_eye_hook.py','human_eye_foveated_renderer.py','native_3d_spatial_scratchpad.py',
    'module_2_low_token_mcp_scene_bridge.py','module_3_1_mcp_protocol_ipc_engine.py',
    'module_3_2_vlm_grounding_closed_loop_agent.py','module_3_3_closed_loop_control_engine.py')
EXTRAS=('pyproject.toml','README.md','human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json')
PROBE=r'''
import hashlib,importlib.metadata,json,pathlib,sys,sysconfig
import numpy,PIL,human_eye_plugin
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin import surface_proximity
identity=runtime_identity(mode='live')
print(json.dumps({'isolated':bool(sys.flags.isolated),'python':sys.executable,
 'prefix':sys.prefix,'base_prefix':sys.base_prefix,'python_version':sys.version,
 'site_root':sysconfig.get_paths()['purelib'],'plugin_file':human_eye_plugin.__file__,
 'surface_file':surface_proximity.__file__,'numpy_version':numpy.__version__,
 'numpy_file':numpy.__file__,'pillow_version':PIL.__version__,'pillow_file':PIL.__file__,
 'distribution_version':importlib.metadata.version('human-eye-spatial-plugin'),
 'source_kind':identity['source_kind'],'runtime_identity':identity,'sys_path':sys.path}))
'''


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')


def source_manifest(root):
    names=set(ROOT_MODULES)
    for package in ('human_eye_plugin','human_eye_module1_operators'):
        names.update(package+'/'+p.name for p in (root/package).glob('*.py'))
    if len(names)!=137:raise ValueError('runtime_source_count_must_be_137:'+str(len(names)))
    return [{'path':name,'sha256':sha(root/name)} for name in sorted(names)]


def canonical(root,manifest):
    constants={node.targets[0].id:ast.literal_eval(node.value)
        for node in ast.parse((root/'human_eye_plugin/runtime_identity.py').read_text(encoding='utf8')).body
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
    value={'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':manifest}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf8')).hexdigest(),constants


class Installer:
    def __init__(self,expected):
        self.expected=expected
        self.report={'schema':'scale-opt-001-isolated-installs-v1','task':'SCALE-OPT-001','passed':False,
            'baseline_commit':BASELINE_COMMIT,'runtime_root':str(RUNTIME),'dependency_pins':PINS,
            'expected_candidate_surface_sha256':expected,'versions':{},'commands':[],
            'models_started':0,'Blender_started':0,'performance_tasks_started':0,
            'formal_installation_modified':False,'old_environment_reused_without_copy':True}
        self.env=dict(os.environ)
        for key in ('PYTHONPATH','PYTHONHOME'):self.env.pop(key,None)
        self.env.update(PYTHONDONTWRITEBYTECODE='1',PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_CONFIG_FILE=os.devnull)

    def run(self,label,args,*,cwd=RUNTIME,timeout=180):
        started=time.perf_counter_ns();log=RUNTIME/'logs'/f'{len(self.report["commands"])+1:02}_{label}.log'
        log.parent.mkdir(exist_ok=True)
        proc=subprocess.run([str(arg) for arg in args],cwd=cwd,env=self.env,capture_output=True,timeout=timeout)
        log.write_bytes(proc.stdout+b'\n---STDERR---\n'+proc.stderr)
        self.report['commands'].append({'label':label,'argv':[str(arg) for arg in args],'cwd':str(cwd),
            'elapsed_ns':time.perf_counter_ns()-started,'returncode':proc.returncode,'log':str(log),'log_sha256':sha(log)})
        save(HERE/'INSTALLS_PARTIAL.json',self.report)
        if proc.returncode:raise RuntimeError(f'{label} failed ({proc.returncode}); see {log}')
        return proc.stdout

    def probe(self,label,python,venv):
        proof=json.loads(self.run('probe_'+label,[python,'-I','-B','-X','utf8','-c',PROBE]))
        site=Path(proof['site_root']).resolve();identity=proof['runtime_identity']
        if not proof['isolated'] or proof['source_kind']!='installed_distribution':raise ValueError('isolated_wheel_import_required:'+label)
        if site!=venv.resolve()/'Lib/site-packages':raise ValueError('actual_site_root_mismatch:'+label)
        for key in ('plugin_file','surface_file','numpy_file','pillow_file'):
            if not Path(proof[key]).resolve().is_relative_to(site):raise ValueError('foreign_import:'+label+':'+key)
        if proof['numpy_version']!=PINS['numpy'] or proof['pillow_version']!=PINS['Pillow']:raise ValueError('dependency_version_mismatch:'+label)
        if proof['distribution_version']!='9.7.2':raise ValueError('distribution_version_changed:'+label)
        manifest=source_manifest(site);independent,constants=canonical(site,manifest)
        if identity['source_files']!=manifest or identity['source_sha256']!=independent or identity['build_id']!='sha256:'+independent:
            raise ValueError('actual_137_source_manifest_identity_mismatch:'+label)
        return {'python':str(python.resolve()),'venv':str(venv.resolve()),'installed_root':str(site),
            'source_sha256':independent,'identity':identity,'runtime_source_members':manifest,
            'source_constants':constants,'proof':proof}

    def main(self):
        if RUNTIME.exists():raise ValueError('new_candidate_runtime_must_not_exist; preserve and diagnose previous attempt')
        if not all(p.is_file() for p in (OLD/'Scripts/python.exe',BUILDER)):raise ValueError('existing_isolated_tools_required')
        if sha(ROOT/SURFACE)!=self.expected:raise ValueError('candidate_source_does_not_match_root_fixed_SHA')
        current=source_manifest(ROOT);current_canonical,current_constants=canonical(ROOT,current)
        RUNTIME.mkdir();(RUNTIME/'logs').mkdir()
        started=time.perf_counter_ns()
        try:
            old=self.probe('O',OLD/'Scripts/python.exe',OLD)
            if old['source_sha256']!=OLD_CANONICAL:raise ValueError('old_O_must_remain_frozen_product')
            old['reused']=True;old['copied']=False;self.report['versions']['O']=old
            old_members={r['path']:r['sha256'] for r in old['runtime_source_members']}
            changed=[r['path'] for r in current if old_members.get(r['path'])!=r['sha256']]
            if changed!=[SURFACE] or set(old_members)!={r['path'] for r in current}:
                raise ValueError('single_runtime_file_change_contract:'+str(changed))
            if current_constants!=old['source_constants'] or current_canonical==OLD_CANONICAL:
                raise ValueError('identity_version_must_stay_same_and_source_digest_change')
            self.report.update(changed_runtime_files=changed,candidate_source_canonical=current_canonical)
            source=RUNTIME/'candidate/source';source.mkdir(parents=True)
            members={}
            for name in [r['path'] for r in current]+list(EXTRAS):
                blob=(ROOT/name).read_bytes();dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
                members[name]={'sha256':sha(dest),'bytes':len(blob),'runtime':name not in EXTRAS}
            if source_manifest(source)!=current:raise ValueError('new_source_snapshot_mismatch')
            patch=subprocess.check_output(['git','diff','--binary',BASELINE_COMMIT,'--',SURFACE],cwd=ROOT)
            (RUNTIME/'candidate/SOURCE_CHANGE.patch').write_bytes(patch)
            self.report['candidate_patch_sha256']=hashlib.sha256(patch).hexdigest()
            self.report['source_git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            expected_wheels=('numpy-2.3.5-cp312-cp312-win_amd64.whl','pillow-12.3.0-cp312-cp312-win_amd64.whl',
                'setuptools-80.9.0-py3-none-any.whl','wheel-0.45.1-py3-none-any.whl')
            self.report['dependency_wheels']={name:{'path':str(WHEELHOUSE/name),'sha256':sha(WHEELHOUSE/name),'bytes':(WHEELHOUSE/name).stat().st_size} for name in expected_wheels}
            builder_proof=json.loads(self.run('builder_versions',[BUILDER,'-I','-B','-X','utf8','-c',
                "import importlib.metadata,json,sys;print(json.dumps({'setuptools':importlib.metadata.version('setuptools'),'wheel':importlib.metadata.version('wheel'),'python':sys.version}))"]))
            if builder_proof['setuptools']!='80.9.0' or builder_proof['wheel']!='0.45.1':raise ValueError('builder_tools_not_frozen_versions')
            self.report['builder']=builder_proof
            wheels=RUNTIME/'candidate/wheels';wheels.mkdir()
            self.run('build_candidate_wheel',[BUILDER,'-I','-B','-X','utf8','-m','pip','wheel','--no-index','--no-deps',
                '--no-build-isolation','--wheel-dir',wheels,source])
            files=list(wheels.glob('*.whl'))
            if len(files)!=1:raise ValueError('exactly_one_candidate_wheel_required')
            wheel=files[0]
            with zipfile.ZipFile(wheel) as archive:
                wheel_py={name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.endswith('.py')}
                if wheel_py!={r['path']:r['sha256'] for r in current}:raise ValueError('actual_wheel_137_source_mismatch')
                for name in ('human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json'):
                    if hashlib.sha256(archive.read(name)).hexdigest()!=members[name]['sha256']:raise ValueError('wheel_package_data_mismatch:'+name)
            venv=RUNTIME/'candidate/venv';python=venv/'Scripts/python.exe'
            self.run('create_candidate_venv',[OLD/'Scripts/python.exe','-I','-B','-X','utf8','-m','venv',venv])
            self.run('install_candidate',[python,'-I','-B','-X','utf8','-m','pip','install','--no-index','--find-links',WHEELHOUSE,
                wheel,'numpy=='+PINS['numpy'],'Pillow=='+PINS['Pillow']])
            candidate=self.probe('C',python,venv)
            if candidate['runtime_source_members']!=current or candidate['source_sha256']!=current_canonical:raise ValueError('installed_candidate_does_not_match_fixed_source')
            candidate.update(reused=False,copied=False,source_root=str(source),source_members=members,
                wheel=str(wheel),wheel_sha256=sha(wheel),wheel_bytes=wheel.stat().st_size)
            self.report['versions']['C']=candidate
            for label,install in self.report['versions'].items():
                frozen=self.run('pip_freeze_'+label,[install['python'],'-I','-B','-X','utf8','-m','pip','freeze','--all']).decode('utf8')
                (RUNTIME/f'FREEZE_{label}.txt').write_text(frozen,encoding='utf8',newline='\n')
                install['pip_freeze_file']=str(RUNTIME/f'FREEZE_{label}.txt');install['pip_freeze_sha256']=sha(RUNTIME/f'FREEZE_{label}.txt')
            # Repeat disk checks after building/installing to attest that O was
            # only read and that the root's fixed candidate did not drift.
            if source_manifest(Path(old['installed_root']))!=old['runtime_source_members']:raise ValueError('old_O_source_changed')
            if source_manifest(ROOT)!=current or sha(ROOT/SURFACE)!=self.expected:raise ValueError('working_candidate_changed_during_install')
            self.report.update(passed=True,old_environment_source_unchanged=True,
                candidate_wheel_and_source_bound=True)
        except BaseException as exc:
            self.report['failure']={'type':type(exc).__name__,'message':str(exc)}
            raise
        finally:
            self.report['elapsed_ns']=time.perf_counter_ns()-started;self.report['script_sha256']=sha(Path(__file__))
            save(HERE/'INSTALLS.json',self.report)
            print(json.dumps({'passed':self.report['passed'],'versions':list(self.report['versions']),'result':str(HERE/'INSTALLS.json')}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build',action='store_true')
    parser.add_argument('--expected-surface-sha256');args=parser.parse_args()
    if not args.build:
        print(json.dumps({'mode':'read_only_plan','old_python':str(OLD/'Scripts/python.exe'),
            'candidate_runtime':str(RUNTIME),'builder':str(BUILDER),'wheelhouse':str(WHEELHOUSE),
            'build_requires':'root fixed source and regression completed; --build --expected-surface-sha256 SHA',
            'driver_interface':'INSTALLS.json versions.O/C python,installed_root,source_sha256,identity; all absolute paths'}));return
    if args.expected_surface_sha256 is None or len(args.expected_surface_sha256)!=64:
        parser.error('--build requires --expected-surface-sha256 from the root fixed candidate')
    Installer(args.expected_surface_sha256).main()


if __name__=='__main__':main()
