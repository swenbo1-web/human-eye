"""Write the bounded decision and index the preserved original evidence."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_bytes())
save=lambda p,v:p.write_bytes((json.dumps(v,indent=2,allow_nan=False)+'\n').encode())
start=load(OUT/'TASK_START.json')
baseline=load(OUT/'qa_baseline/RESULTS.json');candidate=load(OUT/'qa_candidate/RESULTS.json')
offline=load(OUT/'offline_01/RESULTS.json')
for row in load(OUT/'RAW_FREEZE.json')['files']:
    p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],row['path']
for row in load(OUT/'PROTECTED_BEFORE.json')['files']:assert sha(ROOT/row['path'])==row['sha256']
assert (OUT/'ENTRY_AUDIT.json').exists() and (OUT/'ACCEPTANCE_REVIEW.json').exists() and (OUT/'COSTS.json').exists()
assert load(OUT/'ENTRY_AUDIT.json')['passed'] and load(OUT/'ACCEPTANCE_REVIEW.json')['passed']
base_cold=baseline['cold_changed_observe_total_ns'];cand_cold=candidate['cold_changed_observe_total_ns']
base_hot=baseline['unchanged_observe_total_ns'];cand_hot=candidate['unchanged_observe_total_ns']
allowance=max(10_000_000,Decimal(base_hot)/10)
zero=candidate['known_contact_paths']
gates=dict(correct_contracts=offline['passed'] and baseline['passed'] and candidate['passed'],
    three_real_witness_nearest_skips=len(zero)==3 and all(r['nearest_traversal_count']==0 and r['distance_m']==0
        and r['witness_status']=='measured' and len(r['surface_work'])==1 and r['surface_work'][0].get('zero_witness_reused') is True
        and r['surface_work'][0]['triangle_pairs']==0 for r in zero),
    cold_changed_at_least_10_percent=cand_cold*10<=base_cold*9,
    unchanged_within_allowance=Decimal(cand_hot-base_hot)<=allowance)
improvement=(Decimal(base_cold-cand_cold)/Decimal(base_cold))*100
decision=dict(gates=gates,all_gates_passed=all(gates.values()),decision='accept' if all(gates.values()) else 'reject',
    baseline_cold_changed_full_observe_ns=base_cold,candidate_cold_changed_full_observe_ns=cand_cold,
    improvement_percent=str(improvement),baseline_unchanged_ns=base_hot,candidate_unchanged_ns=cand_hot,
    unchanged_delta_ns=cand_hot-base_hot,unchanged_allowed_regression_ns=str(allowance),
    comparison='one fresh baseline arm then one candidate arm; full observe intervals; no repeat',
    observed_sessions=2,physical_RPC=baseline['total_RPC_attempts']+candidate['total_RPC_attempts'],
    public_observations=len(baseline['public_calls'])+len(candidate['public_calls']),model_consumers=0)
save(OUT/'GATES.json',decision)
assert decision['all_gates_passed'], 'reject optimization, preserve accepted capability before delivery'
now=datetime.now(timezone.utc); elapsed_ms=round((time.time()-start['receipt_epoch_seconds'])*1000)
assert time.time()<start['implementation_deadline_epoch_seconds']
base_freeze=load(OUT/'SOURCE_FREEZE_BASELINE.json');cand_freeze=load(OUT/'SOURCE_FREEZE_CANDIDATE.json')
refs={}
for frozen in (base_freeze,cand_freeze):
    for row in frozen['originals']:
        for key in ('source_path','copy_path'):refs[str(Path(row[key]).resolve())]=row['sha256']
for row in base_freeze['product_manifest']:refs[str((Path(base_freeze['source_root'])/row['path']).resolve())]=row['sha256']
for key in ('offline_proof','identity_proof'):
    refs[base_freeze[key]['path']]=base_freeze[key]['sha256']
for p in ('verification/closed_solid_read_001/SOURCE_FREEZE.json','verification/visual004_native.py',
          'verification/surface_nearest_entry_001/qa_prepare/controller.py','verification/surface_nearest_entry_001/qa_prepare/stdio_bootstrap.py',
          'verification/test_task_complete_001.py','verification/test_concave_geometry.py','verification/test_blender_host_contracts.py'):
    refs[str((ROOT/p).resolve())]=sha(ROOT/p)
for row in load(OUT/'PROTECTED_BEFORE.json')['files']:refs[str((ROOT/row['path']).resolve())]=row['sha256']
for p,digest in refs.items():assert sha(Path(p))==digest,p
save(OUT/'EXTERNAL_REFERENCES.json',dict(baseline_reused_in_place=True,files=[dict(path=p,sha256=d) for p,d in sorted(refs.items())],
    proof_scope='Product loaded through original verified source loader. Fixture and ordinary test dependency references record disk bytes; they are outside the product execution guard.'))
summary=f'''# ZERO-WITNESS-REUSE-001 — accepted

All four preregistered engineering gates pass. One candidate, two fresh arms in baseline→candidate order, 18/18 observations correct, 28 physical RPC, zero model consumers, no retry or additional sample. This is a local engineering result, with no model-benefit claim.

| Full observe wall | Fresh baseline | Candidate |
| --- | ---: | ---: |
| Initial three | {baseline['observe_phase_totals_ns']['initial']/1e9:.7f} s | {candidate['observe_phase_totals_ns']['initial']/1e9:.7f} s |
| Unchanged three | {base_hot/1e9:.7f} s | {cand_hot/1e9:.7f} s |
| Changed three | {baseline['observe_phase_totals_ns']['changed_current']/1e9:.7f} s | {candidate['observe_phase_totals_ns']['changed_current']/1e9:.7f} s |
| Six initial+changed | {base_cold/1e9:.7f} s | {cand_cold/1e9:.7f} s |

The six-observe improvement is **{improvement:.5f}%**, exceeding 10%. Unchanged delta is {(cand_hot-base_hot)/1e6:.4f} ms; permitted regression was {allowance/Decimal(1_000_000):.5f} ms (max of 10 ms and 10% of fresh baseline). Both complete outer lifecycles, including startup and closure, are retained: baseline {load(OUT/'qa_invocation_baseline/RESULT.json')['wall_ns']/1e9:.7f} s, candidate {load(OUT/'qa_invocation_candidate/RESULT.json')['wall_ns']/1e9:.7f} s. See COSTS for inclusive profile, capture, cache, preparation, publication, and byte boundaries; nested times are not summed as exclusive costs.

Initial Object_03, changed Object_02, and changed Object_03 each use an actual same-query exact boundary point: candidate nearest traversals 0/0/0, triangle-pair visits 0/0/0, genuine witness reuse flags true, measured zero-distance world witnesses retained. Fresh baseline visits were 507/1083/507. Closed classification is unchanged. Initial/unchanged penetrating set is Object_03 with nearest separated Object_02; changed penetrating set is Object_02+Object_03 with nearest separated Object_04. Positive distances remain 0.010000049869218474 m and 0.039999960660935814 m inside independent original error intervals. All matrices, topology and world AABBs remain fixed while only the original four local coordinates are patched.

The optimization retains the first actual cross-surface intersection with its exact frame and triangle references in a local holder. It validates current ordered mesh identity and exact triangle membership, then uses the existing zero-contact descriptor and publication checks. Penetrating containment with positive surface gap never implies zero. Standalone and mixed cache paths preserve their prior behavior; private objects are absent from result/cache serialization. CORE_DESIGN and CODE_REVIEW give the source rationale.

Baseline product `{base_freeze['candidate_commit']}`, 131-source canonical `{base_freeze['source_sha256']}`, is reused from the preceding sealed directory without another baseline source copy. Candidate product `{cand_freeze['candidate_commit']}`, canonical `{cand_freeze['source_sha256']}`, was frozen after tests and before either live arm. Both use surface method exact_binary64_triangle_surface_hulls_v3 and closed method bounded_exact_closed_shell_v1; the source identity records this private optimization. Verified loader witnesses bind the actual loaded generations in both services; identical instrumentation was prepared for both arms before opening either session.

Offline denominator: **15 methods, 15 pass, 0 failure, 0 error, 0 skipped** in one invocation. Nine new directed methods and six existing imported-class methods were discovered. The runner compiles exact frozen bytes for the new test module and prior fixture module; six existing test methods and ordinary fixture/dependency imports remain outside that test compilation mechanism. All product execution uses the original verified source loader, frozen 131-source manifest, and successful final guard verification. The ZIP and identity file preserve that proof; dependency disk hashes are references, not retrospective execution attestation. Tests cover crossing/tangency, complete containment, separated gap, unresolved solid with real surface evidence, stale/wrong pair/frame/point, very large translation/publication limits, cancellation, standalone rank, changed geometry and both one-side-cache-hit combinations. No old full matrix was rerun.

Each arm used one original <=600-second worker lifetime, nine public observations, three independent state readbacks, one original patch and one close: **14 RPC each**, 28 total against caps 16/arm and 32/batch. Product observations are actual stdio/service/socket executions. No models, GUI/default deployment, original assets, Google, other branch or shared STATE were modified. No failures, unknown substitutions, retries or source candidate changes occurred in these test/live invocations. Per-plan new_product_candidates=1 denotes the same global candidate allowance in both plans, not two candidates.

ENTRY_AUDIT passes 427 checks and ACCEPTANCE_REVIEW passes 651 independent read-only checks. All 36 public witness points are independently within 1e-9 m of the original triangle surfaces. Original raw files were sealed before review; PROTECTED_AFTER verifies 27 prior evidence markers unchanged. Owner Popen handles and stdio/Blender exits establish owned closure; direct wait evidence for the Windows controller self PID remains unavailable, and worker close-event unknown is preserved beside the explicit successful close response. No new PID query or scene call was made to fill that gap. Previous baseline evidence limitations remain unchanged and are not used as this fresh A/B denominator.

Postprocessing failures are separate from the zero-failure test/live denominator: the first entry-audit attempt passed 383/385 checks but wrongly expected completed for the typed qa_patch_applied event; its script and outputs remain saved. A subsequent audit exception assumed notifications had response frames; its traceback/hash record is preserved. The final audit follows the actual typed event and notification protocol. One cost-table Markdown Decimal/float formatting error was corrected and disclosed in COSTS. These corrections changed only analysis, with no source candidate, original raw output, test/live rerun or extra RPC.

Receipt app turn started 2026-11-08T15:22:49Z; implementation deadline 2026-11-08T16:07:49Z. This report was sealed {now.isoformat()}, **{elapsed_ms} ms** after receipt; commit/callback completion time is reported at handoff. All raw experiment timings, including outer invocation and process ownership records, remain indexed. The batch ends after one completion callback.
'''
(OUT/'REPORT.md').write_bytes(summary.encode())
files=[]
for p in sorted(OUT.rglob('*')):
    if p.is_file() and p.name!='EVIDENCE_INDEX.json' and '__pycache__' not in p.parts and p.suffix!='.pyc':
        files.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
save(OUT/'EVIDENCE_INDEX.json',dict(candidate_commit=cand_freeze['candidate_commit'],baseline_product=base_freeze['candidate_commit'],
    file_count=len(files),total_bytes=sum(r['bytes'] for r in files),external_references_path='verification/zero_witness_reuse_001/EXTERNAL_REFERENCES.json',
    raw_original_count=load(OUT/'RAW_FREEZE.json')['file_count'],files=files))
print(json.dumps(dict(decision=decision,report_sha256=sha(OUT/'REPORT.md'),index_sha256=sha(OUT/'EVIDENCE_INDEX.json'),file_count=len(files),elapsed_ms=elapsed_ms)))
