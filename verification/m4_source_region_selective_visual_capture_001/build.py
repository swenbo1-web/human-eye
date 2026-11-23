"""Build exactly one isolated product wheel from direct candidate Git objects."""
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns
import tomllib
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/he_m4_source_region_selective_visual_capture_001')
BASE = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
BASE_BINDING = HERE.parent/'m1_m2_source_region_scoped_measurement_001/install/PRODUCT_RUN_BINDING.json'
BUILDER = HERE.parent/'build_candidate_release.py'
VERSION = '9.7.2+m4.source.region.selective.visual.001'
ALLOWED = {'active_observation_images.py','blender_host.py','blender_mcp_host.py','live_service.py',
           'live_spatial_mcp.py','production_server.py','source_region.py','source_region_visual.py'}


def git(*args):
    return subprocess.check_output(['git','-C',str(HERE.parents[1]),*args])


def digest(value):
    return sha256(value).hexdigest()


def demand(ok, reason):
    if not ok:
        raise ValueError(reason)


def build(commit):
    start = perf_counter_ns()
    base = json.loads(BASE_BINDING.read_bytes())
    demand(base['preparation_git']==BASE and git('rev-parse',commit+'^').decode().strip()==BASE,
           'candidate_not_direct_child')
    changed=set(git('diff','--name-only',BASE,commit).decode().splitlines())
    demand(changed and changed <= {'human_eye_plugin/'+name for name in ALLOWED},'candidate_scope_changed')
    prior = {row['path']:row['sha256'] for row in base['source_manifest']}
    data = ['human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json']
    paths=sorted(set(prior) | changed)
    with ZipFile(base['wheel_path']) as pack:
        demand(digest(Path(base['wheel_path']).read_bytes())==base['wheel_sha256'],'baseline_wheel_changed')
        for name in (*prior,*data):
            raw=pack.read(name)
            demand(raw==(Path(base['install_root'])/name).read_bytes()==git('show',BASE+':'+name),
                   'baseline_installed_bytes_changed/'+name)
    root=ROOT/'candidate_install'
    root.mkdir(parents=True,exist_ok=False)
    source=root/'git_source'
    manifest=[]
    for name in [*paths,*data]:
        raw=git('show',commit+':'+name)
        out=source/name
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_bytes(raw)
        if name not in data:
            manifest.append({'path':name,'sha256':digest(raw)})
    metadata=tomllib.loads(git('show',commit+':pyproject.toml').decode())['project']
    tools=run_path(str(BUILDER))
    filename,wheel_bytes=tools['wheel_bytes'](source,manifest,metadata,VERSION)
    tools['verify_wheel'](wheel_bytes)
    wheel=root/filename
    wheel.write_bytes(wheel_bytes)
    target=root/'product'
    pip=subprocess.run([sys.executable,'-IB','-m','pip','--isolated','--disable-pip-version-check',
        'install','--no-index','--no-deps','--no-compile','--target',str(target),str(wheel)],
        capture_output=True,timeout=90)
    (root/'PIP_STDOUT.bin').write_bytes(pip.stdout)
    (root/'PIP_STDERR.bin').write_bytes(pip.stderr)
    pip.check_returncode()
    with ZipFile(wheel) as pack:
        for name in pack.namelist():
            if not name.endswith('/RECORD'):
                demand((target/name).read_bytes()==pack.read(name),'installed_bytes_changed/'+name)
    identity={k:base[k] for k in ('base_version','implementation_revision')}
    source_sha=digest(json.dumps({**identity,'files':manifest},sort_keys=True,separators=(',',':')).encode())
    binding={**identity,'build_id':'sha256:'+source_sha,'source_sha256':source_sha,
             'source_manifest':manifest,'distribution_version':VERSION,'install_root':str(target),
             'preparation_git':commit,'dependency_root':base['dependency_root'],'protocol_version':base['protocol_version'],
             'wheel_path':str(wheel),'wheel_sha256':digest(wheel_bytes),'historical_preparation_git':BASE,
             'changed_product_sources':sorted(changed),'builds':1,'installs':1,'elapsed_ns':perf_counter_ns()-start}
    (root/'PRODUCT_RUN_BINDING.json').write_text(json.dumps(binding,indent=2)+'\n',encoding='utf8')
    print({k:binding[k] for k in ('preparation_git','source_sha256','wheel_sha256')})


if __name__=='__main__':
    demand(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv)==2,'fixed_build_interpreter')
    build(sys.argv[1])
