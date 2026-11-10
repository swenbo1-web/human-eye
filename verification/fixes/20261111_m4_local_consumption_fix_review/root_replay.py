"""Root replay of the exact fixed synthetic suite; no product/consumer calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import types

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
AUTHOR=WT/'verification/m4_local_relation_consumption_001/revisions/LRC_PREP_001/tests/run_fix_checks.py'
ROOT=Path(__file__).resolve().parent
raw=AUTHOR.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='5f68f70d98b7af7fd60b5c5dd4f7255ccab1717847ad257a017b67cb8148bbcd'
module=types.ModuleType('root_lrc_fix_qa')
module.__file__=str(AUTHOR)
exec(compile(raw,str(AUTHOR),'exec',dont_inherit=True),module.__dict__)
module.TESTS=ROOT/'replay'
module.TESTS.mkdir(exist_ok=False)
temp_root=Path('D:/hefe/.human-eye/qa')
temp_root.mkdir(parents=True,exist_ok=True)
original_mkdtemp=tempfile.mkdtemp
def owned_short_root(*args,**kwargs):
    kwargs['dir']=str(temp_root)
    return original_mkdtemp(*args,**kwargs)
module.tempfile.mkdtemp=owned_short_root
try:
    code=module.main()
finally:
    module.tempfile.mkdtemp=original_mkdtemp
result=json.loads((module.TESTS/'RESULTS_02.json').read_bytes())
receipt=dict(exit_code=code,passed=result['passed'],checks=result['total_assertion_count'],
    old_regression=result['old_231_regression'],new_checks=result['new_check_count'],
    new_case_count=len(result['case_records']),external_attempts=result['external_attempts'],
    archive_member_count=result['archive_member_count'],outputs_archive_sha256=result['outputs_archive_sha256'],
    author_script_sha256=hashlib.sha256(raw).hexdigest(),
    wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    result_sha256=hashlib.sha256((module.TESTS/'RESULTS_02.json').read_bytes()).hexdigest(),
    overrides='TESTS=root review output; tempfile dir=D:/hefe/.human-eye/qa; all test source/assertions unchanged',
    raw_work_root=result['work_root'],raw_outputs_retained=True,cleanup=False,
    model_consumers=0,product_calls=0,Blender_sessions=0)
(ROOT/'ROOT_REPLAY.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
assert code==0 and result['passed'] and result['external_attempts']==dict(subprocess=0,socket=0)
print(json.dumps({k:v for k,v in receipt.items() if k!='old_regression'}))
