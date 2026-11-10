"""Root replay of the fixed author's QA, with outputs confined to root review.

This verifies execution independently; mathematical oracle review is separate.
The author's runner/test bytes stay unchanged. ROOT selects the fixed checkout,
HERE redirects only replay outputs. No Blender or model is launched.
"""
import hashlib
import json
from pathlib import Path
import sys
import types

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
DEST = Path(__file__).resolve().parent
AUTHOR = WT/'verification/m4_local_relation_evidence_001/run_offline.py'
raw = AUTHOR.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '554d8e2fae20617b1a2767c892f805c96875b85617c58c8e15efc8c794489faf'
module = types.ModuleType('root_fixed_author_runner')
module.__file__ = str(AUTHOR)
exec(compile(raw, str(AUTHOR), 'exec', dont_inherit=True), module.__dict__)
module.ROOT = WT
module.HERE = DEST
role = sys.argv[1]
assert role in ('baseline', 'candidate')
expected = {'baseline':'7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1',
            'candidate':'53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'}[role]
sys.argv = [str(AUTHOR), '--role', role, '--expected-source-sha256', expected,
            '--output', 'root_'+role]
result = module.main()
receipt = {'role':role, 'runner_sha256':hashlib.sha256(raw).hexdigest(),
           'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'changes':'ROOT=verified implementation checkout; HERE=root output; author code unchanged',
           'exit_code':result}
(DEST/('ROOT_REPLAY_'+role+'.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
raise SystemExit(result)
