"""Root review: replay fixed candidate tests in a separate exact-byte copy."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = 'b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3'
EVIDENCE = 'verification/m1_task_entry_001'
sha = lambda b: hashlib.sha256(b).hexdigest()
assert subprocess.check_output(['git', '-C', str(AUTHOR), 'rev-parse', 'HEAD']).decode().strip() == COMMIT
identity_bytes = (AUTHOR/EVIDENCE/'offline_03/EXECUTION_IDENTITY.json').read_bytes()
identity = json.loads(identity_bytes)
files = {r['path']: r['sha256'] for r in identity['manifest']}
files.update(identity['fixture_sha256'])
files.update(identity['sealed_original_files_sha256'])
files[identity['test']['path']] = identity['test']['sha256']
files[EVIDENCE+'/run_offline.py'] = identity['runner_sha256']
tree = subprocess.check_output(['git','-C',str(AUTHOR),'ls-tree','-r','-z',COMMIT])
git_blobs = {}
for entry in tree.split(b'\0'):
    if entry:
        meta, name = entry.split(b'\t',1)
        git_blobs[name.decode()] = meta.decode().split()[2]
snapshot = HERE/'fixed_candidate'
snapshot.mkdir(exist_ok=False)
for name, expected in sorted(files.items()):
    raw = (AUTHOR/name).read_bytes()
    assert sha(raw) == expected, name
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == git_blobs[name], name
    dest = snapshot/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(raw)
binding = {'candidate_commit':COMMIT,'author_execution_identity_sha256':sha(identity_bytes),
    'copied_files_sha256':files, 'all_files_match_git_blobs':True,
    'product_sources':len(identity['manifest']), 'no_product_or_test_edits':True,
    'scope':'Root offline replay only; no Blender, network, model or formal installation'}
(HERE/'ROOT_REPLAY_INPUTS.json').write_text(json.dumps(binding,indent=2)+'\n',encoding='utf8')
result = subprocess.run([sys.executable,'-I','-B','-X','utf8',str(snapshot/EVIDENCE/'run_offline.py'),'root_offline_01'],
    cwd=snapshot,capture_output=True)
(HERE/'ROOT_REPLAY_STDOUT.txt').write_bytes(result.stdout)
(HERE/'ROOT_REPLAY_STDERR.txt').write_bytes(result.stderr)
summary_path = snapshot/EVIDENCE/'root_offline_01/RESULTS.json'
summary = json.loads(summary_path.read_bytes()) if summary_path.exists() else None
out = {'exit_code':result.returncode,'summary':summary,
    'inputs_sha256':sha((HERE/'ROOT_REPLAY_INPUTS.json').read_bytes()),
    'all_inputs_unchanged':all(sha((snapshot/p).read_bytes())==h for p,h in files.items())}
(HERE/'ROOT_REPLAY_RESULT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(json.dumps(out))
raise SystemExit(result.returncode)
