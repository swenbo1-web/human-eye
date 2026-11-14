"""Freeze the sole optimization delivery and verify old immutable evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='36694d0e3730a60b0611376b017f978f809a79c0'
PRE='2a8b9811e5080f3d0f26d14c56edd0a657a3935b'
BASE='9c29a9f0990421c607ee821e838394e73dcaa9f3'
REL='verification/m6_shape_opt_001'

def git(*a): return subprocess.check_output(['git',*a],cwd=AUTHOR)
def sha(b): return hashlib.sha256(b).hexdigest()
def put(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists(): assert p.read_bytes()==b,str(p)
    else: p.write_bytes(b)
def checked(item,p=None):
    b=(Path(item['path']) if p is None else p).read_bytes()
    assert len(b)==item['bytes'] and sha(b)==item['sha256'],str(p or item['path'])
    return b

assert git('rev-parse','HEAD').decode().strip()==COMMIT
assert not git('status','--porcelain=v1').strip()
changed=git('diff','--name-only',BASE,COMMIT).decode().splitlines()
assert len(changed)==41 and all(x.startswith(REL+'/') for x in changed)
out={'commit':COMMIT,'pretraining_commit':PRE,'source_files':[],'checked_new_records':[],'pretraining_changes':[]}
for relative in changed:
    b=git('show',COMMIT+':'+relative)
    assert b==(AUTHOR/relative).read_bytes()
    put(HERE/'snapshot'/relative,b)
    out['source_files'].append({'relative':relative,'bytes':len(b),'sha256':sha(b)})
manifest=json.loads((HERE/'snapshot'/REL/'EVIDENCE_MANIFEST.json').read_bytes())
for group in ['public_delivery_files','private_artifacts']:
    for item in manifest[group]:
        b=checked(item)
        out['checked_new_records'].append({'group':group,**item})
        if group=='private_artifacts':put(HERE/'snapshot'/Path(item['path']).relative_to(AUTHOR),b)
freeze=json.loads((HERE/'snapshot'/REL/'TRAIN_FREEZE.json').read_bytes())
for item in freeze['files']:
    relative=REL+'/'+item['path']; frozen=git('show',PRE+':'+relative)
    assert len(frozen)==item['bytes'] and sha(frozen)==item['sha256']
    current=(AUTHOR/relative).read_bytes()
    if current!=frozen:
        assert item['path']=='run_phase.py',relative
        out['pretraining_changes'].append({'relative':relative,'diff':git('diff',PRE,COMMIT,'--',relative).decode()})
for item in freeze['reused_readonly_inputs']:
    b=checked(item)
    put(HERE/'snapshot'/Path(item['path']).relative_to(AUTHOR),b)
prior_path=HERE.parent/'m6_shape_train_001_review/SNAPSHOT.json'
prior=json.loads(prior_path.read_bytes())
for item in prior['checked_records']:checked(item)
out['old_record_count_verified']=len(prior['checked_records'])
out['old_record_index']={'path':str(prior_path),'sha256':sha(prior_path.read_bytes())}
out['new_record_count']=len(out['checked_new_records'])
out['weights']=manifest['weights'];out['threshold']=manifest['threshold']
out['Bunny_scoring']=0
(HERE/'SNAPSHOT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'public_files':len(changed),'new_records':out['new_record_count'],'old_records':out['old_record_count_verified'],'pretraining_changes':out['pretraining_changes'],'weights':out['weights']}))
