"""Make a deterministic wheel and isolate each frozen product generation."""

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path('D:/he_m4_m5_source_region_001')
PRIOR = HERE.with_name('m4_cross_scale_discovery_001')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('R0','R0F','R1'), required=True)
    args = parser.parse_args()
    started = time.perf_counter_ns()
    old = json.loads((PRIOR / 'R1_RUN_BINDING.json').read_bytes())
    names = sorted({row['path'] for row in old['source_manifest']} | {'human_eye_plugin/source_region.py'})
    manifest = [dict(path=name, sha256=sha((ROOT/name).read_bytes())) for name in names]
    if len(manifest) < 143:
        raise ValueError('expected_source_region_runtime_sources')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for row in manifest:
        raw = (ROOT / row['path']).read_bytes()
        committed = subprocess.check_output(['git','show',head+':'+row['path']],cwd=ROOT)
        if raw != committed:
            raise ValueError('product_source_uncommitted/'+row['path'])
    output = HERE / ('build_' + args.version)
    install = EXTERNAL / args.version / 'product'
    if output.exists() or install.exists():
        raise FileExistsError('fixed_candidate_build_exists')
    templates = list((HERE.with_name('m4_cross_scale_discovery_001')/'build_R1').glob('*.whl'))
    if len(templates)!=1 or sha(templates[0].read_bytes()) != old['wheel_sha256']:
        raise ValueError('accepted_template_changed')
    version = '9.7.2+m4.m5.source.region.001.'+args.version.lower()
    members = {}
    with zipfile.ZipFile(templates[0]) as archive:
        for name in archive.namelist():
            if name.endswith('/RECORD') or name in names:
                continue
            raw = archive.read(name)
            if name.endswith('/METADATA'):
                raw=raw.replace(('Version: '+old['distribution_version']).encode(),('Version: '+version).encode())
            if name.endswith('runtime_sources.json'):
                raw=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
            members[name.replace(old['distribution_version'],version)] = raw
    for row in manifest:
        members[row['path']] = (ROOT/row['path']).read_bytes()
    record_name='human_eye_spatial_plugin-'+version+'.dist-info/RECORD'
    buffer=io.StringIO(newline='')
    writer=csv.writer(buffer,lineterminator='\n')
    for name,raw in sorted(members.items()):
        writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode(),len(raw)])
    writer.writerow([record_name,'',''])
    members[record_name]=buffer.getvalue().encode()
    output.mkdir()
    wheel=output/('human_eye_spatial_plugin-'+version+'-py3-none-any.whl')
    with zipfile.ZipFile(wheel,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(members.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,raw)
    with zipfile.ZipFile(wheel) as archive:
        for name,encoded,size in csv.reader(io.StringIO(archive.read(record_name).decode())):
            if name==record_name:
                continue
            raw=archive.read(name)
            if len(raw)!=int(size) or encoded!='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode():
                raise ValueError('wheel_RECORD')
    command=['D:/he_anchor_001/venv/Scripts/python.exe','-I','-B','-m','pip','install','--no-index','--no-deps','--no-compile','--target',str(install),str(wheel)]
    completed=subprocess.run(command,capture_output=True)
    (output/'PIP_STDOUT.bin').write_bytes(completed.stdout)
    (output/'PIP_STDERR.bin').write_bytes(completed.stderr)
    if completed.returncode:
        raise RuntimeError('isolated_install_failed')
    for row in manifest:
        if sha((install/row['path']).read_bytes()) != row['sha256']:
            raise ValueError('installed_runtime_changed')
    identity={key:old[key] for key in ('base_version','implementation_revision')}
    source_sha=sha(json.dumps(dict(identity,files=manifest),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    binding=dict(identity,source_sha256=source_sha,source_manifest=manifest,build_id='sha256:'+source_sha,
        distribution_version=version,install_root=str(install),dependency_root=old['dependency_root'],
        preparation_git=head,protocol_version=old['protocol_version'],wheel_sha256=sha(wheel.read_bytes()))
    save(HERE/(args.version+'_RUN_BINDING.json'),binding)
    save(output/'BUILD_INSTALL.json',dict(started_ns=started,closed_ns=time.perf_counter_ns(),binding=binding,
        wheel=str(wheel),wheel_sha256=binding['wheel_sha256'],wheel_RECORD_verified=True,command=command,pip_exit=0))
    print(json.dumps(dict(version=args.version,source_sha256=source_sha,installed_sources=len(manifest))))


if __name__=='__main__':
    main()
