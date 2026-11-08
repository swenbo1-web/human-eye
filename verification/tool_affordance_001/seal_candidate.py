"""Fix one final description candidate and seal the bounded offline evidence."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_bytes())
save=lambda p,v:p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
git=lambda *a,data=None:subprocess.check_output(['git',*a],cwd=ROOT,input=data)
start=load(OUT/'TASK_START.json'); result=load(OUT/'offline_04/RESULTS.json')
assert result['passed'] and load(OUT/'JSONSCHEMA_RESULTS.json')['passed']
assert load(OUT/'SEMANTIC_REVIEW.json')['passed']
assert time.time()<start['implementation_deadline_epoch_seconds']
assert git('rev-parse','HEAD').decode().strip()==start['baseline_HEAD']
rel='human_eye_plugin/live_spatial_mcp.py'
assert set(git('diff','--name-only').decode().splitlines())=={rel}
assert not git('diff','--cached','--name-only')
manifest=load(OUT/'offline_04/candidate_manifest.json')
baseline_manifest=load(OUT/'offline_04/baseline_manifest.json')
assert len(manifest)==131
for row in manifest:assert sha(ROOT/row['path'])==row['sha256']
assert [r['path'] for r in manifest if r['sha256']!={b['path']:b['sha256'] for b in baseline_manifest}[r['path']]]==[rel]
for r in load(OUT/'PROTECTED_BEFORE.json')['files']:assert sha(ROOT/r['path'])==r['sha256']
(OUT/'live_spatial_mcp.final.py').write_bytes((ROOT/rel).read_bytes())
(OUT/'DESCRIPTION_SOURCE_FINAL.diff').write_bytes(git('diff','--no-ext-diff','--',rel))
git('-c','core.autocrlf=false','add','--',rel)
assert git('show',':'+rel)==(ROOT/rel).read_bytes()
git('commit','--quiet','-m','Clarify paired solid relation and surface distance tool requests')
candidate=git('rev-parse','HEAD').decode().strip()
request=b''.join((candidate+':'+r['path']+'\n').encode() for r in manifest)
raw=git('cat-file','--batch',data=request);offset=0
for row in manifest:
    end=raw.index(b'\n',offset);header=raw[offset:end].split();assert header[1]==b'blob'
    size=int(header[2]);begin=end+1
    assert raw[begin:begin+size]==(ROOT/row['path']).read_bytes(),row['path']
    offset=begin+size+1
assert offset==len(raw)
save(OUT/'SOURCE_FREEZE.json',dict(cycle_id='TOOL-AFFORDANCE-001',candidate_commit=candidate,
    baseline_commit=start['baseline_HEAD'],source_sha256=result['candidate_source_sha256'],source_count=131,
    manifest=manifest,all_131_committed_blobs_equal_executed_sources=True,only_changed_product_path=rel,
    product_schema_proof='offline_04/structure_proof.json',JSONSchema_proof='JSONSCHEMA_RESULTS.json',
    one_final_product_commit=True,precommit_draft_byte_correction='Deleted exactly current plus one space (8 UTF8 bytes) after production byte gate exposed +2 bytes; no alternative design search.'))
save(OUT/'PROTECTED_AFTER.json',dict(files=load(OUT/'PROTECTED_BEFORE.json')['files'],all_unchanged=True))
elapsed=round((time.time()-start['receipt_epoch_seconds'])*1000)
text=f'''# TOOL-AFFORDANCE-001

One final description-only candidate is ready for independent root review. All final offline gates pass. No model, Blender, live-service/field RPC, or performance sample was run. This change does not establish adoption, exact model-visible schema exposure, task speed, trust, or token savings.

Product `{candidate}` starts from clean `{start['baseline_HEAD']}`. The complete 131-source manifest is in SOURCE_FREEZE.json; canonical identity is `{result['candidate_source_sha256']}` (baseline `{result['baseline_source_sha256']}`). All 131 committed blobs match the exact sources supplied to the original verified loader. Only live_spatial_mcp.py changes; the other 130 source blobs remain identical. Recursive description-stripped actual schemas and the non-description module AST are equal, preserving fields, enum, required/allOf/defaults, dispatch, algorithms, domains, budgets, unknown behavior, return handling and authorization.

| Actual UTF-8 representation | Before B | Final B | Delta B |
| --- | ---: | ---: | ---: |
| Observe compact JSON | 9473 | 9465 | -8 |
| Complete catalogue compact JSON | 18514 | 18506 | -8 |
| Observe production JSON | 9938 | 9932 | -6 |
| Actual production tools/list response | 19631 | 19625 | -6 |

These compare actual generated schema/tool-list outputs with the same serializers. The response uses the existing wire.encode_response including JSON-RPC envelope and newline; the observe production row uses its default-spaced JSON encoding. Python source size is not the byte gate. Schemas, full directory/wire bytes, source-before/after, four changed description paths and exact hashes are retained in offline_04. No description outside observe changes.

| Previous ambiguity | Final guidance |
| --- | --- |
| First complete example was single-object nearest | First example is a parseable generic A/B task request for closed_solid_relation plus surface_proximity |
| Exactly one selector sounded general | Each selector contains name OR id; pair facts require two ordered A to B; global surface_nearest alone targets one object |
| Closed-solid fact buried after nearest guidance | requested_facts explains connected closed shells, zero tolerance, separated/touching/positive-volume penetration, independent nonnegative surface distance and unknown reasons |
| More candidates and use of measurements unstated | Query relevant pairs; answer from complete current facts and supplement missing/unknown quantities |
| Other supported modes could be lost in shortening | Existing legacy nearest/top1 bounds/ties, mesh registered reads, image options, revision/code binding, expiry and escape-vs-distance distinctions remain accurate |

The example uses only generic A/B names, no fixture identity/shape/value/truth. It passes both archived actual input schemas using the installed PowerShell Test-Json validator. Twelve JSONSchema checks pass (six cases per arm), including selector mutual exclusion, the one-object nearest limit and unsupported facts. Existing _validate_arguments and validate_query run directly under the original source guard: final 16 cases per arm, 32 outcomes, all expected accept/reject results match. All eight query modes are covered. No replacement parser or validator is implemented. The final runner initially marks external JSONSchema proof pending; JSONSCHEMA_RESULTS.json completes that separate gate. Both product guard receipts succeed. The runner and third-party dependencies are outside the product guard, with their interpreter/origin/hash records explicitly saved.

Failures and the precommit correction are preserved. Invocation1 failed before product imports because the verifier called AST Dict.values as a method. Invocation2 completed baseline16 parser cases, then candidate guard rejected NumPy located beneath the workspace; no product guard was weakened. Invocation3 used an existing external compatible interpreter, completed both arms/32 parser cases and guards, then correctly failed production byte gates: compact bytes tied, but production observe/wire each grew2 bytes from added JSON separator spaces. No word alternatives were compared. The same uncommitted candidate received one deterministic constraint correction: remove only the redundant eight-byte `current ` in its opening sentence. Initial source/review, exact failed scripts, owned Popen/wait receipts, raw stderr and failure tracebacks remain. Invocation4 then passed unchanged gates for the final source. Only one final product candidate is committed; the failed precommit source identity is not presented as the final identity. One malformed apply_patch request also failed before mutation and was corrected in the task log.

The honest offline denominator is four harness invocations: three failed, one passed. Across their control flow,80 original parser assertions completed:48 in earlier attempts before later failures and32 final detailed JSON rows. Only the final32 have per-case result rows; earlier completion follows the preserved frozen runner path and failure location, without retrospective row attestation. Five local in-process tools/list generations accessed no service methods and are not field RPCs. Dependency discovery also encountered a missing Python jsonschema package and exploratory missing paths; the installed native Test-Json was used without installation. No model use, native scene call, Blender process, repeated word-design comparison, Google/API/key/503 access, default configuration, original asset, GUI, shared STATE or competitor branch modification occurred.

Independent SEMANTIC_REVIEW passes21 checks, updated only for the eight-byte correction with its initial review retained. PROTECTED_AFTER verifies31 prior markers unchanged. The root COMPLEX001 failure review remains the motivation, not evidence that a model distrusted or did not see HE; previous geometry optimization stays closed. This candidate ends here pending independent root review and any separately authorized bounded consumption validation.

App turn receipt 2026-11-08T17:44:48Z (2026-11-09 01:44:48 Asia/Shanghai); full25-minute deadline18:09:48Z. This report was sealed {datetime.now(timezone.utc).isoformat()}, {elapsed}ms after receipt, including failed checks, correction, final validation and source commit. Handoff records the later full elapsed interval through evidence commit/callback; it does not substitute the roughly one-second verifier lifetime for engineering cost.
'''
(OUT/'REPORT.md').write_bytes(text.encode())
files=[]
for p in sorted(OUT.rglob('*')):
    if p.is_file() and p.name!='EVIDENCE_INDEX.json' and '__pycache__' not in p.parts and p.suffix!='.pyc':
        files.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
save(OUT/'EVIDENCE_INDEX.json',dict(cycle_id='TOOL-AFFORDANCE-001',candidate_commit=candidate,
    file_count=len(files),total_bytes=sum(r['bytes'] for r in files),files=files))
print(json.dumps(dict(candidate_commit=candidate,source_sha256=result['candidate_source_sha256'],
    report_sha256=sha(OUT/'REPORT.md'),index_sha256=sha(OUT/'EVIDENCE_INDEX.json'),files=len(files),elapsed_ms=elapsed)))
