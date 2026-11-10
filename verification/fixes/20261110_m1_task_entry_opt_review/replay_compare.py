"""Independently replay the fixed optimized candidate's before/after checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = '7411ac7aa9338f17355ffe5cdf4df113ce862aed'
EVIDENCE = 'verification/m1_task_entry_001_optimize'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert subprocess.check_output(['git','-C',str(AUTHOR),'rev-parse','HEAD']).decode().strip() == COMMIT
identity_bytes = (AUTHOR/EVIDENCE/'offline_01/EXECUTION_IDENTITY.json').read_bytes()
identity = json.loads(identity_bytes)
files = {r['path']:r['sha256'] for r in identity['manifest']}
files.update(identity['fixture_sha256'])
runner_path = EVIDENCE+'/compare_validation.py'
files[runner_path] = '4eae40867c41ab9ee87b7029c1a7d65f1f5e6ddab02ec0d69273ba0c670523d0'
tree = subprocess.check_output(['git','-C',str(AUTHOR),'ls-tree','-r','-z',COMMIT])
git_blobs = {}
for entry in tree.split(b'\0'):
    if entry:
        meta,name = entry.split(b'\t',1)
        git_blobs[name.decode()] = meta.decode().split()[2]
snapshot = HERE/'fixed_candidate_02'
snapshot.mkdir(exist_ok=False)
for name,expected in sorted(files.items()):
    raw = (AUTHOR/name).read_bytes()
    assert sha(raw) == expected, name
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == git_blobs[name], name
    target = snapshot/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw)
binding = {'commit':COMMIT,'files_sha256':files,'all_Git_blobs_match':True,
    'author_identity_sha256':sha(identity_bytes),'scope':'offline comparative QA only; no Blender/model/installation'}
(HERE/'ROOT_COMPARE_02_INPUTS.json').write_text(json.dumps(binding,indent=2)+'\n',encoding='utf8')
# The shared repository supplies the frozen baseline Git blobs; all candidate
# files and fixture imports come from this separate exact-byte copy.
environment = dict(os.environ)
environment['GIT_DIR'] = subprocess.check_output(['git','-C','D:/hefe','rev-parse','--absolute-git-dir']).decode().strip()
environment['GIT_WORK_TREE'] = str(snapshot)
binding['read_only_git_environment'] = {key:environment[key] for key in ('GIT_DIR','GIT_WORK_TREE')}
(HERE/'ROOT_COMPARE_02_INPUTS.json').write_text(json.dumps(binding,indent=2)+'\n',encoding='utf8')
process = subprocess.run([sys.executable,'-I','-B','-X','utf8',str(snapshot/runner_path),'root_compare_02'],
    cwd=snapshot,capture_output=True,env=environment)
(HERE/'ROOT_COMPARE_02_STDOUT.txt').write_bytes(process.stdout)
(HERE/'ROOT_COMPARE_02_STDERR.txt').write_bytes(process.stderr)
result_path = snapshot/EVIDENCE/'root_compare_02/RESULTS.json'
summary = json.loads(result_path.read_bytes()) if result_path.is_file() else None
out = {'exit_code':process.returncode,'summary':summary,
    'all_inputs_unchanged':all(sha((snapshot/name).read_bytes())==expected for name,expected in files.items())}
(HERE/'ROOT_COMPARE_02_RESULT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(json.dumps(out))
raise SystemExit(process.returncode)
