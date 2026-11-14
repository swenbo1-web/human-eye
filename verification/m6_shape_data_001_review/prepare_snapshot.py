"""Fixed-byte DATA001 snapshot; does not execute or modify author programs."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='efce450c1da372642010871994588a69799e268c'
REL='verification/m6_shape_data_001'


def git(*args): return subprocess.check_output(['git',*args],cwd=AUTHOR)
def sha(b): return hashlib.sha256(b).hexdigest()
def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): assert path.read_bytes()==data, str(path)
    else: path.write_bytes(data)


assert git('rev-parse','HEAD').decode().strip()==COMMIT
assert not git('status','--porcelain=v1').strip()
changed=git('diff','--name-only','9b016c8720b709a6382438ddd505c7b154d4fac2',COMMIT).decode().splitlines()
assert len(changed)==41 and all(x.startswith(REL+'/') for x in changed)
out={'commit':COMMIT,'changed_files':changed,'sources':[],'checked_records':[]}
for rel in changed:
    data=git('show',COMMIT+':'+rel)
    assert data==(AUTHOR/rel).read_bytes()
    put(HERE/'snapshot'/rel,data)
    out['sources'].append({'relative':rel,'bytes':len(data),'sha256':sha(data)})
manifest=json.loads((HERE/'snapshot'/REL/'EVIDENCE_MANIFEST.json').read_bytes())
for group in ['public_delivery_files','private_local_files','source_originals','reused_previous_inputs']:
    for item in manifest[group]:
        source=Path(item['path']); data=source.read_bytes()
        assert len(data)==item['bytes'] and sha(data)==item['sha256'], str(source)
        out['checked_records'].append({'group':group,**item})
        if group in ('private_local_files','reused_previous_inputs'):
            put(HERE/'snapshot'/source.relative_to(AUTHOR),data)
freeze=json.loads((HERE/'snapshot'/REL/'FROZEN_INPUTS.json').read_bytes())
for item in freeze['public_files']:
    relative=Path(item['path']).relative_to(AUTHOR).as_posix()
    assert git('show','bc2dfddb4f0d8d2304a5aa6dcb5c03d076b6f666:'+relative)==(HERE/'snapshot'/relative).read_bytes()
out['generation_preregistered_sources_identical']=True
(HERE/'SNAPSHOT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'sources':len(out['sources']),'manifest_records':len(out['checked_records']),'private':len(manifest['private_local_files'])}))
