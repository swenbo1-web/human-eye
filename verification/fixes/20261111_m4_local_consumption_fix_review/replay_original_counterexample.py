"""Run the fixed packager on the root's unchanged prior failing fixture."""
import hashlib
import json
from pathlib import Path
import sys
import types

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'20261111_m4_local_consumption_prep_review/zero_launch/e'
DEST=HERE/'original_counterexample/e'
SCRIPT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/quality_handoff/pack_quality.py')
raw=SCRIPT.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365'
DEST.mkdir(parents=True,exist_ok=False)
names=('PLAN.json','FREEZE.json','private/ANON_MAP.json','input/INITIAL.png','input/PROMPT.txt',
       'SYNTHETIC_SCOPE.json','GO.json','STARTED.json','RUN_RESULT.json')
sources={name:(OLD/name).read_bytes() for name in names}
for name,value in sources.items():
    p=DEST/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
module=types.ModuleType('root_fixed_original_counterexample');module.__file__=str(SCRIPT)
exec(compile(raw,str(SCRIPT),'exec',dont_inherit=True),module.__dict__)
module.EVAL=DEST;module.HERE=DEST/'q';module.HERE.mkdir()
sys.argv=['synthetic-original-counterexample','h'];module.main()
index=json.loads((DEST/'q/h/public/INDEX.json').read_bytes())
mapping=json.loads(sources['private/ANON_MAP.json'])
first_id=mapping['rows'][0]['anonymous_id']
first=next(row for row in index['answers'] if row['anonymous_id']==first_id)
assert len(index['answers'])==9
assert (first['execution_record_state'],first['answer_state'])==('failed_before_consumer','missing')
assert all(row['execution_record_state']==row['answer_state']=='not_run'
           for row in index['answers'] if row['anonymous_id']!=first_id)
assert all(row['answer_file'] is None for row in index['answers'])
assert all((DEST/name).read_bytes()==value for name,value in sources.items())
for name in ('GO.json','STARTED.json'):
    assert (DEST/'q/h/private/control'/name).read_bytes()==sources[name]
receipt=dict(original_fixture_bytes_unchanged=True,passed=True,fixed_slots=9,
    first_execution='failed_before_consumer',first_answer='missing',tail_not_run=8,
    new_answers_or_pids=0,real_consumers=0,product_calls=0,Blender_sessions=0,
    source_sha256={name:hashlib.sha256(value).hexdigest() for name,value in sources.items()},
    packager_sha256=hashlib.sha256(raw).hexdigest(),synthetic_only=True)
(HERE/'ORIGINAL_COUNTEREXAMPLE_REPLAY.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_sha256'}))
