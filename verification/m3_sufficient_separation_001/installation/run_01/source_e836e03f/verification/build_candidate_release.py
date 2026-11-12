"""Build a deterministic pure-Python wheel from an explicit runtime manifest.

No dependency installation, source rewriting, local-state globbing or activation.
Wheel format: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
"""
from __future__ import annotations
import argparse,base64,csv,hashlib,io,json,re,zipfile
from pathlib import Path,PurePosixPath
import tomllib


def require(value,reason):
    if not value:raise ValueError('candidate_'+reason)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    path=PurePosixPath(name)
    require(type(name) is str and bool(name) and not path.is_absolute()
        and path.as_posix()==name and all(p not in ('','..','.') and ':' not in p for p in path.parts)
        and '\\' not in name,'member_path')
    return name


def archive_bytes(members):
    require(type(members) is dict and bool(members),'members')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,raw in members.items():
            safe_name(name);require(type(raw) is bytes,'member_bytes')
            info=zipfile.ZipInfo(name,(2026,11,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3;info.external_attr=0o100644<<16
            archive.writestr(info,raw,compresslevel=9)
    return stream.getvalue()


def wheel_bytes(root,manifest,project,version):
    root=Path(root).resolve()
    require(re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:\+[a-z0-9]+(?:\.[a-z0-9]+)*)?',version),'version')
    require(project['name']=='human-eye-spatial-plugin','project_name')
    paths=[safe_name(r['path']) for r in manifest]
    require(paths==sorted(set(paths)) and all(p.endswith('.py') for p in paths),'source_manifest_order')
    members={}
    for record in manifest:
        relative=record['path'];path=root/relative
        require(path.resolve()==path and path.is_file() and path.is_relative_to(root),'source_path')
        raw=path.read_bytes();require(digest(raw)==record['sha256'],'source_changed')
        members[relative]=raw
    for relative in ('human_eye_plugin/plugin.json','human_eye_plugin/mcp_config.json'):
        path=root/relative;require(path.resolve()==path and path.is_file(),'package_data_path')
        raw=path.read_bytes();require(len(raw)<=65536 and type(json.loads(raw)) is dict,'package_data')
        members[relative]=raw
    dist='human_eye_spatial_plugin-'+version+'.dist-info'
    metadata=['Metadata-Version: 2.1','Name: '+project['name'],'Version: '+version,
        'Summary: Finite 3D observation candidate; release validation remains separate',
        'Requires-Python: '+project['requires-python']]
    for dependency in project['dependencies']:
        require(type(dependency) is str and '\n' not in dependency and '\r' not in dependency,'dependency')
        metadata.append('Requires-Dist: '+dependency)
    metadata+=['Description-Content-Type: text/markdown','','Candidate only. No installation activation or model-benefit claim.','']
    members[dist+'/METADATA']='\n'.join(metadata).encode()
    members[dist+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: human-eye-exact-manifest-1\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    points=['[console_scripts]']+[name+' = '+value for name,value in sorted(project['scripts'].items())]+['']
    require(all('\n' not in name and '\n' not in value and '\r' not in name+value for name,value in project['scripts'].items()),'entry_points')
    members[dist+'/entry_points.txt']='\n'.join(points).encode()
    members[dist+'/runtime_sources.json']=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    records=io.StringIO(newline='');writer=csv.writer(records,lineterminator='\n')
    for name,raw in members.items():
        writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode(),str(len(raw))])
    writer.writerow([dist+'/RECORD','','']);members[dist+'/RECORD']=records.getvalue().encode()
    return 'human_eye_spatial_plugin-'+version+'-py3-none-any.whl',archive_bytes(members)


def verify_wheel(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=archive.namelist();require(len(names)==len(set(names)),'duplicate_member')
        for name in names:
            safe_name(name);require((archive.getinfo(name).external_attr>>16)&0o170000!=0o120000,'symlink_member')
        records=[name for name in names if name.endswith('.dist-info/RECORD')]
        require(len(records)==1,'record_count')
        rows=list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
        require(len(rows)==len(names) and len({r[0] for r in rows})==len(rows) and {r[0] for r in rows}==set(names),'record_coverage')
        for name,claimed,size in rows:
            if name==records[0]:require(claimed==size=='','record_self');continue
            value=archive.read(name);encoded=base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=').decode()
            require(claimed=='sha256='+encoded and size==str(len(value)),'record_hash')
    return dict(files=len(names),all_hashes_verified=True)


def build(root,output,version):
    import sys
    root=Path(root).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(root))
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    identity=runtime_identity();require(check_source_drift()['compatible'],'runtime_drift')
    original=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf8'))
    name,wheel=wheel_bytes(root,identity['source_files'],original['project'],version)
    verification=verify_wheel(wheel)
    require(wheel_bytes(root,identity['source_files'],original['project'],version)[1]==wheel,'not_deterministic')
    (output/name).write_bytes(wheel)
    notes=('Candidate '+version+'\nRuntime build '+identity['source_sha256']+'\n'
        'Source files '+str(len(identity['source_files']))+'\n'
        'Install only into a new candidate directory. No official activation is included.\n'
        'Local configurations, raw acceptance evidence and third-party test assets are excluded.\n'
        'The SDK base version and this distribution version are recorded separately.\n').encode()
    project=(root/'pyproject.toml').read_bytes().replace(b'version = "9.7.2"',('version = "'+version+'"').encode(),1)
    members={'CANDIDATE_NOTES.txt':notes,'wheel/'+name:wheel,'source/pyproject.toml':project,
        'source/README.md':(root/'README.md').read_bytes()}
    for record in identity['source_files']:
        raw=(root/record['path']).read_bytes();require(digest(raw)==record['sha256'],'source_changed_during_bundle')
        members['source/'+record['path']]=raw
    for name2 in ('plugin.json','mcp_config.json'):
        members['source/human_eye_plugin/'+name2]=(root/'human_eye_plugin'/name2).read_bytes()
    portable=[dict(path=name,bytes=len(raw),sha256=digest(raw)) for name,raw in members.items()]
    members['CONTENTS.json']=json.dumps(portable,indent=2).encode()
    bundle=archive_bytes(members);bundle_name='human_eye_'+version.replace('+','_')+'_candidate.zip'
    (output/bundle_name).write_bytes(bundle)
    require(check_source_drift()['compatible'],'runtime_drift_after_build')
    result=dict(distribution_version=version,runtime_identity=identity,wheel=verification,deterministic_rebuild=True,
        artifacts=[dict(file=name,bytes=len(raw),sha256=digest(raw)) for name,raw in ((name,wheel),(bundle_name,bundle))])
    with (output/'BUILD.json').open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True);args=parser.parse_args()
    value=build(Path(__file__).resolve().parents[1],args.output,args.version)
    print(json.dumps({k:v for k,v in value.items() if k!='runtime_identity'}))
