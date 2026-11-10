from pathlib import Path
import hashlib, json

PUBLIC=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001/quality_handoff/handoff_01/public')
OUT=Path('D:/hefe/verification/fixes/20261111_m4_observation_quality_review')
BASE=PUBLIC.parents[2]
sha=lambda b:hashlib.sha256(b).hexdigest()
index=json.loads((PUBLIC/'INDEX.json').read_bytes())
assert sha((PUBLIC/'INDEX.json').read_bytes())=='e950da63c0b61ddf2b3938b92a7ac443ead08524797330ced86f7e876be861cf'
notes={
 'answer_07229f7fac18446d':'Observed vertex/face geometry and computed selection conditions support the analytic material-region proof, attained X gap and rod-within-hole argument. About0.100009mm reflects the recorded native transform rounding; no new precision gate applies.',
 'answer_16cc0a01c1667547':'Selection checks, observed geometry, source-bound solid relation certificates and pair-local witnesses support all three relations. Strict interior point is explained using the right frame bar, not inferred solely from zero distance.',
 'answer_635fcb52c8009303':'Observed selection geometry and reference bounds support all three conditions; bound solid facts and local vertex/material descriptions support the three pair classifications and witnesses.',
 'answer_69cc9ae597e60afa':'Observed vertices/faces and additional numerical clearances support analytic separation and shared material. Calling the rod point at Y=0.100 a vertex is a minor topology-wording imprecision: it is a surface/edge point between end caps; it still supplies a valid rounded surface witness and does not alter the requested relation.',
 'answer_ae6684a89ddc7a0e':'Observed native vertices/faces, explicit three-condition checks, shared-interior point and attained gap/hole bounds suffice. Native coordinate rounding is immaterial to0.25mm classification and stated approximate values.',
 'answer_e85f06af4348d600':'Actual exact-solid observations plus local coordinate levels/frame faces and candidate selection checks support the final; zero surface distance is not used alone as the overlap proof.'}
rows=[]
for a in index['answers']:
 d=PUBLIC/a['directory'];raw=(d/a['answer_file']).read_bytes()
 assert sha(raw)==a['answer_original_sha256']
 rows.append({'anonymous_id':a['anonymous_id'],'answer_sha256':sha(raw),
  'evidence_sha256':sha((d/a['evidence_file']).read_bytes()),
  'target':{'correct':1,'required':1},'target_conditions':{'correct':3,'required':3},
  'neighbor_roles':{'correct':3,'required':3},'relation_classes':{'correct':3,'required':3},
  'sufficient_pair_evidence':{'correct':3,'required':3},
  'explicit_unknown':0,'missing_requested_items':0,'wrong_relation':0,
  'materially_unsupported_or_contradictory_claims':0,'complete_correct':True,
  'minor_wording_note':a['anonymous_id']=='answer_69cc9ae597e60afa',
  'reason':notes[a['anonymous_id']]})
record={'schema':'M4-root-blind-quality-v1','execution_commit':'a5f9da9cdb66f95d8a4393f29362c18d5be366b4',
 'public_index_sha256':sha((PUBLIC/'INDEX.json').read_bytes()),
 'scoring_contract_sha256':sha((BASE/'scoring/SCORING_CONTRACT.json').read_bytes()),
 'truth_sha256':sha((BASE/'scoring/TRUTH.json').read_bytes()),
 'review_method':'Root read all six original final answers, all sixteen owner request programs/arguments, selected returned target-condition/solid-fact records and the frozen scoring contract; geometric sufficiency judged against independently checked original geometry. Independent full-evidence grades and source-package integrity are separate.',
 'mapping_or_cost_read_before_this_record':False,'not_perfectly_blind':'Tool/method semantics can reveal route; no private anonymous map or cost records read.',
 'correct':6,'denominator':6,'grades':rows,
 'limits':['Current fixed scene only; no generalization to complex assets.','Initial-image cognitive use remains unknown.','Source/receipt integrity is reviewed separately and is not inferred from correct prose.']}
(OUT/'ROOT_GRADES.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'root_complete_correct':6,'denominator':6,'minor_wording_notes':1,'cost_unblinded':False}))
