"""Seal root-adjudicated public-only quality before arm/cost unblinding."""
from pathlib import Path
import datetime, hashlib, json

HERE=Path(__file__).parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval')
PUBLIC=BASE/'quality_handoff/handoff_01/public'
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
index=read(PUBLIC/'INDEX.json')
assert sha(PUBLIC/'INDEX.json')=='a8f7832732c489db4d870ea8305cd191890c77a5cb8a4030b44aaf4cb04c7884'
assert read(HERE/'PUBLIC_BINDING_REVIEW.json')['passed']
for m in read(HERE/'PUBLIC_SNAPSHOT.json')['members']:
    assert sha(PUBLIC/m['path'])==m['sha256'], m['path']
decisions=[]
reports=[]
for task in ['T1','T2','T3']:
    p=HERE/(task+'_BLIND_REVIEW.json')
    report=read(p)
    rows=report['answers']
    expected={r['anonymous_id'] for r in index['answers'] if r['task_id']==task}
    assert len(rows)==9 and {r['anonymous_id'] for r in rows}==expected
    for row in rows:
        assert row['complete_correct'] is True
        if 'full_pass' in row:
            assert row['full_pass'] is True
        decisions.append({'anonymous_id':row['anonymous_id'],'task_id':task,'complete_correct':True,'root_adjudication':'complete_correct','source_report':p.name})
    reports.append({'path':p.name,'sha256':sha(p)})
result={
    'schema':'m1-root-blind-quality-seal-v1',
    'sealed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'execution_commit':'fa23496e1565e34ddacf4a0ce28b65e0a85c3ca8',
    'public_index_sha256':sha(PUBLIC/'INDEX.json'),
    'public_snapshot_sha256':sha(HERE/'PUBLIC_SNAPSHOT.json'),
    'scoring_contract_sha256':sha(BASE/'SCORING_CONTRACT.json'),
    'review_reports':reports,
    'denominator':27,'complete_correct':27,'incorrect':0,'incomplete':0,'honest_unknown':0,'not_run':0,
    'answers':sorted(decisions,key=lambda x:x['anonymous_id']),
    'root_review':'Root read all 27 original finals and the frozen scoring rules, independently checked public source/input/final hashes, and adjudicated the three independent per-task evidence reviews. Rounded distances meet the disclosed tolerance; legitimate AABB lower-bound plus attained witnesses accepted. Historical tool failures retained as process events, not positive evidence.',
    'blinding':'No private arm map or measured cost opened before this seal. Tool names and original wording can reveal routes; not perfect blinding.',
    'limits':'Small static interface-consumption screen, three distinct tasks repeated three times per arm. No full visual-target-discovery/M4 or broad quality-superiority claim. Private projection/original-record integrity still audited after seal.'
}
with (HERE/'QUALITY_SEAL.json').open('x',encoding='utf-8') as f:
    json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'sealed':True,'complete_correct':27,'denominator':27,'sha256':sha(HERE/'QUALITY_SEAL.json')}))
