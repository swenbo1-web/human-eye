"""Preserve every runtime byte and verify a bounded, direct-source final seal."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RUNTIME=Path('D:/he_m4_m5_source_region_001')
BASELINE='3c26b43d197e6de252f65db69c061733e5a7216e'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def files(directory):
    result=[]
    for current,directories,names in os.walk(directory,followlinks=False):
        for name in directories+names:
            path=Path(current)/name
            if path.is_symlink() or path.is_junction():
                raise ValueError('reparse_entry')
            path.resolve().relative_to(directory.resolve())
        result.extend(Path(current)/name for name in names)
    return sorted(result)


def snapshot():
    return [(path.relative_to(RUNTIME).as_posix(),path.stat().st_size,sha(path)) for path in files(RUNTIME)]


def archive():
    before=snapshot()
    target=HERE/'runtime_archive'
    target.mkdir(exist_ok=False)
    entries=[]
    for index,(relative,size,digest) in enumerate(before,1):
        original=RUNTIME/relative
        copy=target/('f'+str(index).zfill(6)+'_'+original.name[:100])
        with original.open('rb') as incoming,copy.open('xb') as outgoing:
            shutil.copyfileobj(incoming,outgoing)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if sha(copy)!=digest or copy.read_bytes()!=original.read_bytes():
            raise ValueError('archive_bytes')
        entries.append(dict(relative=relative,copy=copy.relative_to(HERE).as_posix(),bytes=size,sha256=digest))
    if snapshot()!=before:
        raise ValueError('runtime_changed')
    save(HERE/'RUNTIME_ARCHIVE.json',dict(schema='cross-scale-runtime-archive-v1',files=entries,file_count=len(entries),
        bytes=sum(row['bytes'] for row in entries),runtime_exclusions=[],originals_retained=True,byte_exact=True))
    print(json.dumps(dict(files=len(entries),bytes=sum(row['bytes'] for row in entries))))


def scan(raw,name,findings):
    patterns=(rb'\b(?:sk-proj-|sk-)[A-Za-z0-9_-]{24,}',rb'\bgh[pousr]_[A-Za-z0-9]{25,}',
        rb'\bgithub_pat_[A-Za-z0-9_]{30,}',rb'\bya29\.[A-Za-z0-9_-]{25,}',
        rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    if any(re.search(pattern,raw) for pattern in patterns):
        findings.append(name)
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            for member in zipped.infolist():
                if not member.is_dir():
                    scan(zipped.read(member),name+'!'+member.filename,findings)


def seal():
    baseline=read(HERE/'BASELINE.json')
    for row in baseline['old_direct_seals']+[baseline['accepted_install']]:
        if sha(row['path'])!=row['sha256']:
            raise ValueError('accepted_direct_input_changed')
    for version in ('R0','R0F','R1'):
        frozen=read(HERE/('SOURCE_FREEZE_'+version+'.json'))
        binding=read(HERE/(version+'_RUN_BINDING.json'))
        for row in frozen['runtime_manifest']:
            if sha(Path(binding['install_root'])/row['path'])!=row['sha256']:
                raise ValueError('frozen_installed_generation_changed')
        for row in frozen['harness_pins']:
            relative=Path(row['path']).relative_to(ROOT).as_posix()
            blob=subprocess.check_output(['git','show',frozen['preparation_git']+':'+relative],cwd=ROOT)
            if hashlib.sha256(blob).hexdigest()!=row['sha256']:
                raise ValueError('historical_frozen_harness_changed/'+relative)
        for row in [frozen['task'],frozen['oracle'],frozen['asset']]:
            if sha(row['path'])!=row['sha256']:
                raise ValueError('frozen_direct_input_changed/'+row['path'])
    archive_record=read(HERE/'RUNTIME_ARCHIVE.json')
    if snapshot()!=[(row['relative'],row['bytes'],row['sha256']) for row in archive_record['files']]:
        raise ValueError('original_runtime_set_changed')
    for row in archive_record['files']:
        if sha(HERE/row['copy'])!=row['sha256']:
            raise ValueError('archived_runtime_changed')
    decision=read(HERE/'DECISION.json')
    for name,digest in decision['report_pins'].items():
        if sha(HERE/name)!=digest:
            raise ValueError('decision_input_changed/'+name)
    allowed={'human_eye_plugin/source_region.py','human_eye_plugin/active_observation_images.py',
             'human_eye_plugin/surface_proximity.py','human_eye_plugin/live_service.py',
             'human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/query_policy.py','human_eye_plugin/read_context.py'}
    prefix=HERE.relative_to(ROOT).as_posix()+'/'
    changed=subprocess.check_output(['git','diff','--name-only',BASELINE],cwd=ROOT,text=True).splitlines()
    if any(not name.startswith(prefix) and name not in allowed for name in changed):
        raise ValueError('unexpected_product_or_repository_change')
    findings=[]
    for path in files(HERE):
        scan(path.read_bytes(),str(path),findings)
    if findings:
        raise ValueError('credential_pattern/'+repr(findings))
    save(HERE/'FINAL_AUDIT.json',dict(schema='cross-scale-final-audit-v1',passed=True,
        prior_direct_seals=len(baseline['old_direct_seals']),prior_manifest_members_expanded=0,
        runtime_files=archive_record['file_count'],runtime_bytes=archive_record['bytes'],runtime_exclusions=[],
        allowed_product_paths=sorted(allowed),credential_findings=[],administrator_review='pending'))
    entries=[dict(relative=path.relative_to(HERE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)) for path in files(HERE)]
    save(HERE/'CONTENT_MANIFEST.json',dict(schema='cross-scale-content-manifest-v1',files=entries,member_count=len(entries),excludes_self_only=True))
    print(json.dumps(dict(sealed=True,members=len(entries))))


def verify_git():
    manifest=read(HERE/'CONTENT_MANIFEST.json')
    prefix=HERE.relative_to(ROOT).as_posix()+'/'
    expected={row['relative'] for row in manifest['files']}|{'CONTENT_MANIFEST.json'}
    actual=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD','--',prefix],cwd=ROOT,text=True).splitlines()
    if {name[len(prefix):] for name in actual}!=expected:
        raise ValueError('Git_namespace_file_set')
    for name in sorted(expected):
        blob=subprocess.check_output(['git','show','HEAD:'+prefix+name],cwd=ROOT)
        if blob!=(HERE/name).read_bytes():
            raise ValueError('Git_blob_bytes/'+name)
    print(json.dumps(dict(git_exact_members=len(expected),passed=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=('archive','seal','verify-git'))
    option=parser.parse_args().operation
    {'archive':archive,'seal':seal,'verify-git':verify_git}[option]()
