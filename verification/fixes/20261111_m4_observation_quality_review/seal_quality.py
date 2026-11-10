from pathlib import Path
import datetime, hashlib, json

B=Path('D:/hefe/verification/fixes/20261111_m4_observation_quality_review')
P=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001/quality_handoff/handoff_01/public')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
files=['ROOT_GRADES.json','grader_a/GRADES.json','grader_b/GRADES.json','integrity/INTEGRITY_REVIEW_FINAL.json']
values={name:json.loads((B/name).read_bytes()) for name in files}
root=values['ROOT_GRADES.json']['grades']
a=values['grader_a/GRADES.json']['answers'];b=values['grader_b/GRADES.json']['answers']
def ident(row):return row.get('anonymous_id',row.get('answer_id'))
expected={x['anonymous_id'] for x in json.loads((P/'INDEX.json').read_bytes())['answers']}
for rows in [root,a,b]:
 assert len(rows)==6 and {ident(r) for r in rows}==expected
 assert all(r['complete_correct'] is True for r in rows)
assert values['integrity/INTEGRITY_REVIEW_FINAL.json']['status']=='pass'
assert not values['integrity/INTEGRITY_REVIEW_FINAL.json']['errors']
seal={'schema':'M4-quality-seal-before-cost-v1','cycle_id':'M4-OBSERVATION-BASELINE-001',
 'sealed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'execution_commit':'a5f9da9cdb66f95d8a4393f29362c18d5be366b4',
 'public_index_sha256':sha((P/'INDEX.json').read_bytes()),
 'review_files_sha256':{name:sha((B/name).read_bytes()) for name in files},
 'public_files_sha256':{x.relative_to(P).as_posix():sha(x.read_bytes()) for x in sorted(P.rglob('*')) if x.is_file()},
 'denominator':6,'complete_correct':6,'independent_grader_agreement':True,
 'target_correct':6,'target_conditions_correct':18,'roles_correct':18,'relations_correct':18,'sufficient_local_evidence':18,
 'material_errors':0,'unknown_answers':0,'missing_requested_items':0,
 'minor_nonmaterial_note':'One answer calls a valid rod surface/edge point a vertex; no changed relation or unsupported local proof.',
 'root_and_graders_private_mapping_or_cost_read_before_seal':False,
 'integrity_reviewer_role':'Separate non-grading reviewer checked original private records and returned only integrity/unknown summaries; no arm/cost table exposed to graders.',
 'blindness_limit':'Tool and method semantics may reveal route; no claim of perfect double blindness.',
 'remaining_unknown':['All six thin EXIT receipts absent; not inferred from PID absence.','Image provider receipt/cognitive use unknown.','Cost/value analysis not yet performed.'],
 'next':'Only now permit arm/cost unblinding; preserve these quality grades unchanged.'}
with (B/'QUALITY_SEAL.json').open('x',encoding='utf8') as f:json.dump(seal,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'quality_seal_sha256':sha((B/'QUALITY_SEAL.json').read_bytes()),'complete_correct':6,'denominator':6,'cost_unblinded':False}))
