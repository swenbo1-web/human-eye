import hashlib, io, json, subprocess, tarfile, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='96d5249f2a08ead5ecde7e644e9a6b4f1f997c0e'
REL=Path('verification/m6_shape_pretrain_001')
SNAP=HERE/'snapshot'; SNAP.mkdir(exist_ok=True)
START=time.perf_counter()
archive=subprocess.check_output(['git','archive',COMMIT,REL.as_posix()],cwd=AUTHOR)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    for member in tar:
        if member.isfile():
            path=SNAP/member.name
            assert path.resolve().is_relative_to(SNAP.resolve())
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(tar.extractfile(member).read())
B=SNAP/REL
manifest=json.loads((B/'EVIDENCE_MANIFEST.json').read_bytes())
records=[]
for record in manifest['public_files']+manifest['private_files']:
    path=AUTHOR/REL/record['path']; data=path.read_bytes()
    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],str(path)
    if not record['path'].startswith('private/'):
        assert data==(B/record['path']).read_bytes()
    if record['path'].startswith('private/pointfilter/'):
        destination=B/record['path'];destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
    records.append({'path':str(path),'bytes':len(data),'sha256':record['sha256']})
freeze=json.loads((B/'PLAN_FREEZE.json').read_bytes())
for record in freeze['files']:
    expected=subprocess.check_output(['git','show','da7e2d7ebb784ef67c1cacd4b2d0e6f633b7d5a1:'+str(REL/record['path']).replace('\\','/')],cwd=AUTHOR)
    assert expected==(B/record['path']).read_bytes() and hashlib.sha256(expected).hexdigest()==record['sha256']
out={'commit':COMMIT,'new_manifest_records':len(records),'private_records':len(manifest['private_files']),'plan_files_unchanged':len(freeze['files']),'records':records,'private_payload_strategy':'read hash-verified bytes in each actual use; official network/weight copied into fixed snapshot','wall_s':time.perf_counter()-START}
(HERE/'SNAPSHOT.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in out.items() if k!='records'}))
