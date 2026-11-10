"""Read-only check of the observed two-call nearest evidence pattern."""
from pathlib import Path
import json,hashlib
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m1_task_entry_001_eval'
PUBLIC=BASE/'quality_handoff/handoff_01/public'
OUT=Path(__file__).parent
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def payload(attempt):
    response=next(r['value'] for r in attempt['responses'] if r['kind']=='RESPONSE.json')
    return json.loads(response['result']['content'][0]['text'])
rows=[]
for slot in read(BASE/'private/ANON_MAP.json')['rows']:
    if slot['group']!='S' or slot['task']=='T1': continue
    path=PUBLIC/slot['anonymous_id']/'tool_evidence.json'
    evidence=read(path)
    attempts=evidence['owner_attempts']
    assert len(attempts)==2
    assert attempts[0]['request']['params']['name']=='human_eye_surface_nearest'
    assert attempts[1]['request']['params']['name']=='human_eye_spatial_relations'
    first,second=map(payload,attempts)
    assert first['status']=='complete' and first['coverage']['unresolved']==0
    assert 'nearest_witness' not in json.dumps(first)
    assert len(second['candidates'])==1
    pair=second['candidates'][0]
    surface=pair['surface_proximity']
    assert surface['status']=='measured'
    assert surface['value']['distance_m']==first['distance_m']
    assert pair['name']==first['nearest_objects'][0]['name']
    rows.append({**slot,'first_result_status':first['status'],'first_nearest':first['nearest_objects'],
        'first_result_has_world_point_witness':False,
        'second_tool':attempts[1]['request']['params']['name'],'second_status':second['status'],
        'surface_proximity_status':surface['status'],'closed_solid_relation':pair['closed_solid_relation'],
        'second_witness':surface['value']['nearest_witness'],'evidence_sha256':sha(path)})
assert len(rows)==6
files=['human_eye_plugin/task_query.py','human_eye_plugin/live_service.py','human_eye_plugin/live_spatial_mcp.py']
result={'passed':True,'observed_cells':6,'rows':rows,'source_hashes':{f:sha(ROOT/f) for f in files},
    'source_finding':'surface_nearest_result retains the per-pair measurement object through ranking, but its result dictionary omits already-computed closest-point witnesses. live_service decorates winner IDs with names, without adding those witnesses. The follow-up relation tool returns surface witnesses and also computes solid relation, which is unknown on these open T3 meshes.',
    'interpretation':'Six observed S nearest tasks perform a second plugin local-evidence query; no native tool or global re-solve in these six. Providing the existing witness in the first response is a concrete output-layer candidate. This does not prove motives, guarantee elimination of future calls, or quantify saved model inference.',
    'scope':'Read existing public transcripts after quality seal, frozen map and product source only. No product/model/Blender execution.'}
(OUT/'NEAREST_EVIDENCE_GAP.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'cells':[(r['cell'],r['task'],r['second_status']) for r in rows]}))
