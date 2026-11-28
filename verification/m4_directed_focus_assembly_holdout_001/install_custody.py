"""Bind the fixed product's Git, wheel, installed source and runtime without starting Blender."""
import argparse
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

CANDIDATE = 'e98ad951d554179c9b9fd3024013d1a875acbe84'
WHEEL = '4d60f9eac3f3791f883eed8bf6c31e1b37a8a0618458d386cb66804a29719358'
SOURCE = '00ba6e251415847878e7ed028a5ba704f6e8ee6ba4bd567dd3fea0e8076bb72e'
BUILD = '6933d57b1ac26a4a262c979c18cae58e8bebb8944a8510ce2031a4fbc3ca30c6'
PYTHON = 'b95409b2edc04f3db3f2a5021fa52d2e0791ae978c13cdeb857cab0f35476919'
BLENDER = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'


def ensure(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path):
    path=path.resolve(strict=True)
    data=path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':sha256(data).hexdigest()}


def attest(prior, checkout, blender):
    python=pin(Path(sys.executable))
    build_path=prior/'install/build/BUILD.json'
    build=pin(build_path)
    binary=pin(blender)
    ensure(sys.flags.isolated and sys.dont_write_bytecode and python['sha256']==PYTHON,'retained_interpreter_changed')
    ensure(build['sha256']==BUILD and binary['sha256']==BLENDER,'retained_build_or_Blender_changed')
    manifest=json.loads(build_path.read_bytes())
    rows=manifest['runtime_identity']['source_files']
    ensure(len(rows)==146 and manifest['runtime_identity']['source_sha256']==SOURCE,
           'prior_runtime_manifest_mismatch')
    wheel_path=build_path.parent/manifest['artifacts'][0]['file']
    wheel=pin(wheel_path)
    ensure(wheel['sha256']==WHEEL,'prior_wheel_digest_changed')
    site=(prior/'install/candidate-site').resolve(strict=True)
    ensure(site.is_dir(),'retained_isolated_install_missing')
    manifest_names={row['path'] for row in rows}
    ensure(len(manifest_names)==146,'duplicate_runtime_paths')
    with ZipFile(wheel_path) as bundle:
        ensure(bundle.testzip() is None and len(set(bundle.namelist()))==len(bundle.namelist()),
               'wheel_integrity_or_duplicate_name')
        ensure({p for p in bundle.namelist() if p.endswith('.py')}==manifest_names,'wheel_python_members_changed')
        for row in rows:
            name=row['path']
            raw=bundle.read(name)
            git=subprocess.check_output(['git','-C',str(checkout),'show',CANDIDATE+':'+name])
            ensure((site/name).read_bytes()==raw==git and sha256(raw).hexdigest()==row['sha256'],
                   'Git_wheel_install_source_changed/'+name)
    sys.path.insert(0,str(site))
    from human_eye_plugin import runtime_identity, blender_process, live_spatial_mcp
    import numpy
    import PIL
    ident=runtime_identity.runtime_identity()
    ensure(ident['source_sha256']==SOURCE and len(ident['source_files'])==len(rows)
           and all(Path(module.__file__).resolve().is_relative_to(site)
                   for module in (runtime_identity,blender_process,live_spatial_mcp)),
           'imported_runtime_differs_from_wheel')
    deps={}
    for name,module in (('numpy',numpy),('Pillow',PIL)):
        deps[name]={'version':importlib.metadata.version(name),'module':pin(Path(module.__file__))}
    return {'passed':True,'candidate_commit':CANDIDATE,'source_sha256':SOURCE,'runtime_sources':len(rows),
            'installation':{'path':str(site)},'wheel':wheel,'build':build,'python':python,'blender':binary,
            'source_manifest':rows,'dependencies':deps,'Blender_launches':0,'candidate_installs':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior',required=True,type=Path)
    p.add_argument('--checkout',required=True,type=Path)
    p.add_argument('--blender',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    proof=attest(a.prior,a.checkout,a.blender)
    with a.output.open('x',encoding='utf8',newline='\n') as fo:
        json.dump(proof,fo,sort_keys=True,indent=2)
        fo.write('\n')
    print('retained install verified',proof['runtime_sources'],proof['source_sha256'])
