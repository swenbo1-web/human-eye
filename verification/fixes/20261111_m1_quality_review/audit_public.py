"""Independent public-only source binding checks; no private or cost reads."""
from pathlib import Path
import collections, hashlib, json

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval')
PUBLIC = ROOT/'quality_handoff/handoff_01/public'
OUT = Path(__file__).parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p, x): p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

errors = []
def check(ok, label):
    if not ok: errors.append(label)

index = read(PUBLIC/'INDEX.json')
check(sha(PUBLIC/'INDEX.json') == 'a8f7832732c489db4d870ea8305cd191890c77a5cb8a4030b44aaf4cb04c7884', 'public_index_hash')
rubric = read(ROOT/'SCORING_CONTRACT.json')
rows = index['answers']
check(len(rows) == index['fixed_slots'] == 27, '27_slots')
check(len({r['anonymous_id'] for r in rows}) == 27, 'unique_anonymous_ids')
check(collections.Counter(r['task_id'] for r in rows) == {'T1':9, 'T2':9, 'T3':9}, 'task_denominators')
checks = []
for r in rows:
    p = PUBLIC/r['directory']
    check(p.resolve().is_relative_to(PUBLIC.resolve()), r['anonymous_id']+':path')
    answer = p/r['answer_file']
    digest = sha(answer)
    check(digest == r['answer_original_sha256'] == r['source_provenance']['public_final_sha256'], r['anonymous_id']+':answer_hash')
    check(r['answer_state'] == 'present' and bool(answer.read_bytes()), r['anonymous_id']+':final_present')
    source = read(p/r['source_consistency_file'])
    asset = rubric['independent_answers'][r['task_id']]['asset_sha256']
    check(source['ACTOR_CONFIG']['asset_sha256'] == source['owner_IDENTITY']['asset_sha256'] == asset, r['anonymous_id']+':asset')
    check(source['INITIAL_original_file_sha256'] == source['FINAL_original_file_sha256'], r['anonymous_id']+':initial_final')
    close = source['CLOSE']
    check(close['asset_unchanged'] is True and close['geometry_unchanged'] is True and close['errors'] == [], r['anonymous_id']+':owner_close')
    check(close['native_close']['protected_files_unchanged'] is True and close['native_close']['source_file_unchanged'] is True, r['anonymous_id']+':native_close')
    fp = close['worker_fingerprint_fields']
    check(bool(fp['initial_geometry_fingerprint']) and fp['initial_geometry_fingerprint'] == fp['final_geometry_fingerprint'], r['anonymous_id']+':fingerprint')
    check(source['missing_or_null_notes'] == [], r['anonymous_id']+':source_missing')
    read(p/r['evidence_file'])
    checks.append({'anonymous_id':r['anonymous_id'], 'task_id':r['task_id'], 'answer_sha256':digest, 'source_sha256':sha(p/r['source_consistency_file']), 'evidence_sha256':sha(p/r['evidence_file']), 'answer_present':True})
for t in index['tasks']:
    check(sha(PUBLIC/t['prompt']) == t['input_sha256'], t['task_id']+':model_input')
members = [{'path':str(p.relative_to(PUBLIC)).replace('\\','/'), 'bytes':p.stat().st_size, 'sha256':sha(p)} for p in sorted(PUBLIC.rglob('*')) if p.is_file()]
save(OUT/'PUBLIC_SNAPSHOT.json', {'source':str(PUBLIC), 'members':members})
save(OUT/'PUBLIC_BINDING_REVIEW.json', {'passed':not errors, 'errors':errors, 'fixed_slots':27, 'task_denominators':dict(collections.Counter(r['task_id'] for r in rows)), 'answers':checks, 'snapshot_sha256':sha(OUT/'PUBLIC_SNAPSHOT.json'), 'scope':'Public-only independent hashes, source-field comparisons and JSON readability. Original private records/projection fidelity deferred until quality seal; final equality does not prove absence of all transient edits. No quality score or runtime/cost result inferred.', 'private_read':False, 'models_or_blender_run':0})
print(json.dumps({'passed':not errors,'errors':errors,'answers':len(checks),'public_files':len(members)}, ensure_ascii=False))
