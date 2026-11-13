"""Seal the independent quality dimensions before any group cost unblinding."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).parent
def read(relative):
    return json.loads((ROOT/relative).read_bytes())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

q = read('quality/FINAL_RESULTS.json')
b = read('binding/RESULTS.json')
d = read('binding/BUDGET_RESULTS.json')
u = read('usage_scope/RESULTS.json')
r = read('ROOT_CROSSCHECK.json')
assert q['turns'] == 18 and not q['manual_review_pending'] and not q['failed']
assert all(x['primary_content_classification'] == 'complete_correct' and
           x['current_state_basis']['classification'] == 'sufficient' for x in q['results'])
assert r['answers'] == r['primary_complete_correct'] == 18 and r['matched_facts'] == 1284
assert b['all_passed'] and not b['failed']
assert d['all_passed'] and not d['failed']
f = b['facts']
assert f['actual_independent_UUIDs'] == f['owned_closures'] == f['registered_EDITS'] == 6
assert f['actual_turns'] == f['CLI_reader_closures'] == f['thin_EXIT_unknown'] == 18
assert f['actual_resumes'] == 12
assert u['passed'] and u['scope_conclusion'] == 'per_turn_CLI_invocation_observed'
assert u['cost_unsealed'] is False and u['numeric_aggregates_published'] is False
inputs = ['quality/FINAL_RESULTS.json','quality/CHECKS.json','quality/REPORT.md',
          'binding/RESULTS.json','binding/CHECKS.json','binding/REPORT.md',
          'binding/BUDGET_RESULTS.json','binding/BUDGET_CHECKS.json',
          'usage_scope/RESULTS.json','usage_scope/CHECKS.json','usage_scope/REPORT.md',
          'ROOT_CROSSCHECK.json','root_crosscheck.py']
proofs = {p: sha(ROOT/p) for p in inputs}
seal = {
    'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002',
    'preparation_commit': '11ae08e791c300c58ae935f4f632a22b3d7f3342',
    'delivery_commit': 'a798caf982e2d7eefe0bf52b739b9bef88526be4',
    'contract_commit': '79ed3bff7c87d4ac68e2b2bf382de05d41b731c6',
    'anonymous_package_sha256': '21198b498acbbe0eb3ef68e399b468629094b325eb8cdd75eef532755b068610',
    'delivery_manifest_sha256': 'c70497915899eb8820f6d0698cbd1237095fa8403ee68686ab36b99c60dc191f',
    'truth_sha256': {'BASE': 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
                     'EDIT': 'ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91'},
    'quality': {'planned_episodes':6, 'planned_turns':18, 'actual_finals':18,
                'primary_complete_correct':18, 'primary_incorrect':0, 'primary_incomplete':0,
                'current_state_basis_sufficient':18, 'matched_facts':1284, 'pair_classifications':4968,
                'reference_only':0, 'delta_only':0, 'auxiliary_reconstruction':'not_needed'},
    'execution': {'completed_episodes':6, 'completed_turns':18, 'failed_turns':0, 'not_run_turns':0,
                  'actual_UUIDs':6, 'actual_resumes':12, 'registered_EDITS':6,
                  'owned_closures':6, 'CLI_reader_closures':18, 'thin_EXIT_unknown':18},
    'usage_scope': 'per_turn_CLI_invocation_observed; exactly one terminal per invocation; no aggregate yet',
    'cost_unsealed':False, 'group_mapping_read_by_quality_scorers':False,
    'author_checks_separate':313, 'independent_evidence_sha256':proofs,
    'limits':['Actual business content reveals route: not perfectly blind.',
              '18 missing thin EXIT receipts remain unknown; owner/CLI closure is separate.',
              'Shared GUI before/after unmeasured; inherited QA namespace side effect retained.',
              'No new geometry-oracle reconstruction: fixed exact rational truth reused.',
              '6 episodes of one 24-object/978-triangle task; facts are not independent task samples.',
              'Prior 001 six failed and twelve not_run unchanged; no pooling or replacement.',
              'Fees, provider retry/abandoned-stream coverage and subscription debit unknown.',
              'Whole-scene surface threshold scanning is not autonomous active-view exploration.'],
    'new_live_model_Blender_API_runs':0,
    'next_authorized_step':'Only unblind and recompute existing 002 cost originals under the root cost plan.'
}
target = ROOT/'QUALITY_SEAL.json'
assert not target.exists(), 'Do not overwrite a seal'
seal['sealed_at_utc'] = datetime.now(timezone.utc).isoformat()
target.write_text(json.dumps(seal,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'quality_seal_sha256':sha(target),'primary_complete_correct':18,'current_basis_sufficient':18,'execution_completed':18,'resumes':12,'cost_unsealed':False}))
