"""Build and install exactly one candidate from the fixed Git source domain."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from subprocess import check_output, run
import sys
import time
import tomllib
from zipfile import ZipFile

NS=Path(__file__).resolve().parent
V=NS.parent
REPO=V.parent
RUN=Path('D:/he_m1_region_task_witness_image_path_001')
BASE_BINDING=V/'m1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
BUILDER=V/'build_candidate_release.py'
PYTHON=Path('D:/he_anchor_001/venv/Scripts/python.exe')
FILES=('human_eye_plugin/live_service.py','human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/read_context.py')
DATA=('human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json')


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path,value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def digest(data):
    return sha256(data).hexdigest()


def pin(path):
    path=path.resolve(strict=True)
    return {'path':str(path),'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size}


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def git(*args):
    return check_output(['git','-C',str(REPO),*args])


def build(candidate):
    mark=time.perf_counter_ns()
    base=read(BASE_BINDING)
    parent=base['preparation_git']
    require(git('rev-list','--parents','-n','1',candidate).decode().split()==[candidate,parent]
            and git('diff','--name-only',parent,candidate).decode().splitlines()==list(FILES),'single_fixed_product_delta_required')
    require(BUILDER.read_bytes()==git('show',candidate+':verification/build_candidate_release.py'),'retained_builder_changed')
    helper=run_path(str(BUILDER))
    source=run_path(str(V/'m4_cross_scale_local_first_view_001/install/build_install.py'))['git_blobs']
    names=[row['path'] for row in base['source_manifest']]
    paths=[*names,*DATA,'pyproject.toml']
    bl, changed=source(parent,paths),source(candidate,paths)
    baseline_wheel=Path(base['wheel_path'])
    require(len(names)==143 and pin(baseline_wheel)['sha256']==base['wheel_sha256'],'baseline_install_wheel_changed')
    helper['verify_wheel'](baseline_wheel.read_bytes())
    with ZipFile(baseline_wheel) as package:
        for row in base['source_manifest']:
            name=row['path']
            require(digest(bl[name])==row['sha256'] and bl[name]==package.read(name)==
                    (Path(base['install_root'])/name).read_bytes(),'baseline_Git_wheel_install_changed/'+name)
        for name in DATA:
            require(bl[name]==package.read(name)==(Path(base['install_root'])/name).read_bytes(),'baseline_package_data_changed/'+name)
    require([name for name in paths if bl[name]!=changed[name]]==list(FILES),'candidate_runtime_diff_changed')
    external=RUN/'candidate_install'
    external.mkdir(parents=True,exist_ok=False)
    staging=external/'git_source'
    for name,raw in changed.items():
        path=staging/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
    manifest=[{'path':name,'sha256':digest(changed[name])} for name in names]
    version='9.7.2+m1.region.task.witness.path.001'
    project=tomllib.loads(changed['pyproject.toml'].decode())['project']
    name,raw=helper['wheel_bytes'](staging,manifest,project,version)
    wheel=external/name
    wheel.write_bytes(raw)
    wheel_check=helper['verify_wheel'](raw)
    installed=external/'product'
    command=[str(PYTHON),'-IB','-m','pip','--isolated','--disable-pip-version-check','install','--no-index',
             '--no-deps','--no-compile','--target',str(installed),str(wheel)]
    process=run(command,capture_output=True,timeout=90)
    (external/'PIP_STDOUT.bin').write_bytes(process.stdout)
    (external/'PIP_STDERR.bin').write_bytes(process.stderr)
    process.check_returncode()
    with ZipFile(wheel) as package:
        require(sorted(name for name in package.namelist() if name.endswith('.py'))==names,'wheel_source_set_changed')
        for name in package.namelist():
            if not name.endswith('/RECORD'):
                require(package.read(name)==(installed/name).read_bytes(),'actual_installed_bytes_changed/'+name)
    require(sorted(path.relative_to(installed).as_posix() for path in installed.rglob('*.py'))==names,'installed_source_set_changed')
    identity={key:base[key] for key in ('base_version','implementation_revision')}
    canonical=json.dumps({**identity,'files':manifest},sort_keys=True,separators=(',',':')).encode()
    source_hash=digest(canonical)
    binding={**identity,'build_id':'sha256:'+source_hash,'source_sha256':source_hash,'source_manifest':manifest,
             'distribution_version':version,'install_root':str(installed.resolve()),'dependency_root':base['dependency_root'],
             'preparation_git':candidate,'protocol_version':base['protocol_version'],'wheel_path':str(wheel.resolve()),
             'wheel_sha256':digest(raw),'historical_preparation_git':parent,'historical_source_sha256':base['source_sha256'],
             'changed_product_sources':list(FILES),'unchanged_product_sources':len(names)-len(FILES)}
    write(NS/'install/PRODUCT_RUN_BINDING.json',binding)
    write(NS/'install/BUILD_INSTALL.json',{'passed':True,'binding':binding,'baseline_sources_verified':len(names),
          'wheel_RECORD':wheel_check,'wheel':pin(wheel),'installed_files':[pin(path) for path in sorted(installed.rglob('*')) if path.is_file()],
          'command':command,'actual_candidate_wheels':1,'actual_candidate_installs':1,'elapsed_ns':time.perf_counter_ns()-mark})
    print(json.dumps({k:binding[k] for k in ('preparation_git','source_sha256','wheel_sha256','install_root')}),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and Path(sys.executable).resolve()==PYTHON.resolve(),
            'use_pinned_install_interpreter')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    build(parser.parse_args().candidate)
