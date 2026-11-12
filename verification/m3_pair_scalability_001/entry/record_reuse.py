"""Record the static harness adaptation and unchanged source dependencies."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'verification/spatial_task_qualification_001/entry'

sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for path in HERE.glob('*.py'):
    ast.parse(path.read_bytes())
before = (OLD/'run_entry.py').read_text(encoding='utf8')
after = (HERE/'run_entry.py').read_text(encoding='utf8')
(HERE/'SOURCE.diff').write_text(''.join(difflib.unified_diff(before.splitlines(keepends=True),
    after.splitlines(keepends=True),fromfile=str(OLD/'run_entry.py'),tofile=str(HERE/'run_entry.py'))),encoding='utf8')
copied = {}
for name in ('qa_snapshot.py','QUERY_RULES.json'):
    assert (OLD/name).read_bytes()==(HERE/name).read_bytes()
    copied[name] = {'source':str(OLD/name),'sha256':sha(HERE/name),'unchanged':True}
value = {'source':str(OLD/'run_entry.py'),'source_sha256':sha(OLD/'run_entry.py'),
    'new_sha256':sha(HERE/'run_entry.py'),'unchanged_copies':copied,
    'changes':['new batch output and READY paths','explicit frozen commit/source CLI; exact137 and external version',
        'old qualification asset/binder/certificate references retained','independent saved public verification and oracle source pins'],
    'independent_saved_checker':{'path':str(HERE/'verify_saved.py'),'sha256':sha(HERE/'verify_saved.py'),
        'witness_helper':str(HERE.parent/'testing/witness_oracle.py'),
        'witness_sha256':sha(HERE.parent/'testing/witness_oracle.py'),
        'position_tolerance_m':1e-9,'distance_tolerance_m':1e-6},
    'AST_valid':True,'install_and_entry_not_executed_by_this_record':True}
(HERE/'SOURCE_REUSE.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
print(json.dumps({'entry_sha256':value['new_sha256'],'checker_sha256':value['independent_saved_checker']['sha256']}))
