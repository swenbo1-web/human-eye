"""Install only fixed M4 candidate bytes into this evidence directory.

Reuse the accepted deterministic builder and unchanged isolated installer.
No dependency install, model command, Blender, activation or config write.
"""
import ast
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
COMMIT='107641ec19919d56aa843c1949261590fc338148'
CANONICAL='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
VERSION='9.7.2+m4.r2'
PYTHON=Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe')
INSTALLER=Path('D:/hefe/verification/fixes/20261110_local_upgrade/INSTALL_CANDIDATE.py')
SHARED=Path('D:/hefe/verification/fixes/20261103_spatial_perception_qual002/shared')
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')


def command(folder,label,argv):
    row=dict(argv=[str(v) for v in argv],started_ns=time.perf_counter_ns(),
        started_utc=datetime.now(timezone.utc).isoformat(),timeout_s=120,pid=None,returncode=None,timed_out=False)
    output=error=b''
    try:
        process=subprocess.Popen(row['argv'],cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        row['pid']=process.pid
        try:output,error=process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            row['timed_out']=True
            stop=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            row['owned_tree_stop_returncode']=stop.returncode
            output,error=process.communicate(timeout=15)
        row['returncode']=process.returncode
    finally:
        row.update(ended_ns=time.perf_counter_ns(),stdout_sha256=sha(output),stderr_sha256=sha(error))
        (folder/(label+'.stdout.bin')).write_bytes(output)
        (folder/(label+'.stderr.txt')).write_bytes(error)
        save(folder/(label+'.PROCESS.json'),row)
    assert row['returncode']==0 and not row['timed_out'],label+' failed; original logs retained'
    return output


def main():
    started=time.perf_counter_ns()
    run=HERE/'run_02';run.mkdir(exist_ok=False)
    protected={str(path):sha(path.read_bytes()) for path in SHARED.iterdir() if path.is_file()}
    for path in (Path('C:/Users/Administrator/.codex/config.toml'),Path('D:/hefe/.codex/config.toml'),ROOT/'pyproject.toml'):
        protected[str(path)]=sha(path.read_bytes()) if path.is_file() else None
    save(run/'PROTECTED_BEFORE.json',protected)
    listed=command(run,'01_GIT_TREE',['git','-C',ROOT,'ls-tree','-r','--name-only',COMMIT]).decode().splitlines()
    source_identity=command(run,'02_IDENTITY_SOURCE',['git','-C',ROOT,'show',COMMIT+':human_eye_plugin/runtime_identity.py'])
    tree=ast.parse(source_identity)
    constants={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES')}
    runtime=sorted(set(constants['_ROOT_MODULES'])|{name for name in listed if name.endswith('.py')
        and len(Path(name).parts)==2 and Path(name).parts[0] in ('human_eye_plugin','human_eye_module1_operators')})
    assert len(runtime)==137
    extras=['README.md','pyproject.toml','human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json',
        'verification/build_candidate_release.py','examples/agents/target_runtime_entry.py','examples/agents/installed_release.py']
    names=sorted(set(runtime+extras))
    raw=command(run,'03_GIT_ARCHIVE',['git','-C',ROOT,'archive','--format=tar',COMMIT,'--',*names])
    source=run/'source_107641ec';source.mkdir()
    manifest=[]
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive.getmembers():
            if not member.isfile():continue
            assert member.name in names
            value=archive.extractfile(member).read()
            target=source/member.name
            assert target.resolve().is_relative_to(source.resolve())
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
            assert value==(ROOT/member.name).read_bytes(), 'fixed checkout source drift'
            if member.name in runtime:manifest.append(dict(path=member.name,sha256=sha(value)))
    manifest.sort(key=lambda row:row['path'])
    canonical=sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
        implementation_revision=constants['IMPLEMENTATION_REVISION'],files=manifest),
        sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    assert len(manifest)==137 and canonical==CANONICAL
    save(run/'FIXED_BUILD_INPUTS.json',dict(commit=COMMIT,source_sha256=canonical,source_count=137,
        manifest=manifest,archive_sha256=sha(raw),source_pyproject_sha256=sha((source/'pyproject.toml').read_bytes()),
        distribution_version_external=VERSION,source_version_constants_changed=False))
    copied=run/'INSTALL_CANDIDATE.py';copied.write_bytes(INSTALLER.read_bytes())
    save(run/'INSTALLER_PROVENANCE.json',dict(original=str(INSTALLER),sha256=sha(copied.read_bytes()),
        unchanged_copy=True,default_activation_requested=False))
    build=json.loads(command(run,'04_BUILD',[PYTHON,'-I','-B','-X','utf8',source/'verification/build_candidate_release.py',
        '--output',run/'bundle','--version',VERSION]))
    release=HERE/'.human-eye/releases'/VERSION
    installed=json.loads(command(run,'05_INSTALL',[PYTHON,'-I','-B','-X','utf8',copied,
        '--source-root',source,'--git-repository',ROOT,'--commit',COMMIT,'--bundle',run/'bundle',
        '--version',VERSION,'--release-dir',release,'--dependency-python',PYTHON,'--evidence-dir',run/'receipt']))
    assert installed['source_sha256']==CANONICAL and installed['source_count']==137
    assert installed['isolated_identity_passed'] and installed['source_commit_wheel_install_equal']
    assert installed['default_activation_changed'] is False
    unchanged={name:(sha(Path(name).read_bytes()) if Path(name).is_file() else None)==before for name,before in protected.items()}
    assert all(unchanged.values())
    assert all(sha((ROOT/row['path']).read_bytes())==row['sha256'] for row in manifest)
    save(run/'PROTECTED_AFTER.json',dict(unchanged=unchanged,all_unchanged=True,product_sources_unchanged=True))
    ready=dict(status='isolated installed candidate; no activation or model consumers',commit=COMMIT,
        source_sha256=CANONICAL,source_count=137,version=VERSION,entry=installed['entry'],
        install_root=str(release/'site-packages'),release=str(release),dependency_python=str(PYTHON),
        wheel_sha256=installed['wheel_sha256'],launcher_sha256=installed['launcher_sha256'],binding_sha256=installed['binding_sha256'],
        installed_identity_passed=True,receipt=str(run/'receipt/ISOLATED_INSTALL.json'),
        no_default_activation=True,protected_inputs_unchanged=True,model_calls=0,Blender_calls=0,
        elapsed_ns=time.perf_counter_ns()-started)
    save(HERE/'READY.json',ready)
    print(json.dumps(ready))


if __name__=='__main__':main()
