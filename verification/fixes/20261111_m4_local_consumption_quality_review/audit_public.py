import hashlib, json, subprocess
from pathlib import Path

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = WT/'verification/m4_local_relation_consumption_001'
P = B/'quality_handoff/handoff_01/public'
OUT = Path(__file__).parent
COMMIT = '06d1b4b4cadd880884a0a3c0927a3095ea761f30'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((B/'quality_handoff/PUBLIC_FILES_SHA256.json').read_bytes())
assert sha(B/'quality_handoff/PUBLIC_FILES_SHA256.json') == '4c0296e378139b7a01a2f8c16e171c36be7b8e658ad61cf6c17208850040ba88'
assert set(manifest) == {p.relative_to(P).as_posix() for p in P.rglob('*') if p.is_file()}
for name, digest in manifest.items():
    p = P/name
    assert sha(p) == digest
    blob = subprocess.check_output(['git','-C',str(WT),'show',COMMIT+':'+p.relative_to(WT).as_posix()])
    assert blob == p.read_bytes()
index = json.loads((P/'INDEX.json').read_bytes())
rows = []
for row in index['answers']:
    folder = P/row['directory']
    assert row['answer_state'] == 'present' and row['execution_record_state'] == 'completed'
    assert sha(folder/'answer.txt') == row['answer_original_sha256']
    evidence = json.loads((folder/'tool_evidence.json').read_bytes())
    attempts = evidence['owner_attempts']
    complete = [e for e in evidence['public_tool_events'] if e['phase'] == 'item.completed']
    assert len(complete) == len(attempts)
    for a,e in zip(attempts, complete):
        assert not a['is_error'] and not a['request_missing'] and not a['response_missing']
        assert e['event']['arguments'] == a['request']['params']['arguments']
        assert e['event']['tool'] == a['request']['params']['name']
        assert e['event']['error'] is None and e['event']['result'] is not None
    source = json.loads((folder/'source_consistency.json').read_bytes())
    assert source['INITIAL_original_file_sha256'] == source['FINAL_original_file_sha256'] == 'ba46e235d6493c193bec7d79b741f2781badda7921aea2537491b609ec6eea4d'
    assert source['CLOSE']['asset_unchanged'] and source['CLOSE']['geometry_unchanged']
    assert source['CONSUMER_IMAGE']['initial_image_sha256'] == '42466e241a4239552fa418b7f79bf1fd73c10092f174c3e87444ed5e93cbed0a'
    rows.append({'anonymous_id':row['anonymous_id'],'answer_sha256':row['answer_original_sha256'], 'evidence_sha256':sha(folder/'tool_evidence.json'),'completed_evidence_events':len(complete),'source_records_consistent':True})
assert len(rows) == 9
result={'scope':'Root actual public-only integrity checks, not automatic semantic grading. No private map/cost/cells read. Producer source assertions checked for consistency, not a new Blender capture.', 'commit':COMMIT,'public_files':len(manifest),'index_sha256':sha(P/'INDEX.json'),'rows':rows,'new_model_consumers':0,'new_Blender_sessions':0}
(OUT/'PUBLIC_INTEGRITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
