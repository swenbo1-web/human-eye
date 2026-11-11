"""Public-only mechanism inventory. Never reads private mapping or run costs."""
import hashlib, json, re
from pathlib import Path

WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
PUBLIC=WT/'verification/m4_local_relation_consumption_001/quality_handoff/handoff_01/public'
OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def decode(x):
    if isinstance(x,str):
        try:return decode(json.loads(x))
        except (ValueError,TypeError):return x
    if isinstance(x,dict):
        if 'content' in x:return [decode(v.get('text',v)) for v in x['content']]
        if 'result' in x:return decode(x['result'])
    return x
rows=[]
for p in sorted(PUBLIC.glob('answer_*/tool_evidence.json')):
    evidence=json.loads(p.read_bytes()); answer=(p.parent/'answer.txt').read_text(encoding='utf8')
    attempts=evidence['owner_attempts']
    requests=[a['request']['params'] for a in attempts]
    relations=[a for a in attempts if a['request']['params']['name']=='human_eye_spatial_relations']
    relation=decode(relations[0]['responses'][0]['value'])[0] if relations else None
    last=requests[-1]['arguments'].get('code','')
    local=relation['candidates'][0]['closed_solid_relation'].get('local_evidence') if relation else None
    rows.append({
      'anonymous_id':p.parent.name,'answer_sha256':sha(p.parent/'answer.txt'),'evidence_sha256':sha(p),
      'route':[r['name'] for r in requests],
      'relation_target':relation['target']['name'] if relation else None,
      'relation_candidates':[x['name'] for x in relation['candidates']] if relation else [],
      'crossing_evidence_present':local is not None,
      'crossing_point':local.get('point_world_m') if local else None,
      'crossing_point_cited_in_final':bool(local and '0.250' in answer and '0.115' in answer and '0.390' in answer),
      'last_native_code':last,
      'last_native_named_objects':sorted(set(re.findall(r"['\"](N\d+)['\"]",last))),
      'manual_classification':('selected vertex/coordinate-level observation plus target-predicate calculations; no independent three-pair closed-solid/surface solver' if relations else 'native geometric discovery and analytic pair/material reasoning'),
      'source_scope':'public original answers, owner attempts and consumer event projections; no private arm identity or cost opened'})
sources=['live_spatial_mcp.py','task_query.py','live_service.py','read_context.py','scene_cache.py','scene_delta.py','blender_mcp_host.py','blender_host.py','query_policy.py','surface_task_service.py']
result={'cycle_id':'M4-LOCAL-RELATION-CONSUMPTION-001','review_kind':'public-only adoption and architecture mechanism, not cost grading',
 'public_index_sha256':sha(PUBLIC/'INDEX.json'),'rows':rows,
 'counts':{'anonymous_answers':len(rows),'relations_routes':sum(bool(r['relation_target']) for r in rows),'local_crossing_present':sum(r['crossing_evidence_present'] for r in rows),'local_crossing_cited':sum(r['crossing_point_cited_in_final'] for r in rows),'relations_followed_by_native':sum(bool(r['relation_target']) and r['route'][-1]=='execute_blender_code' for r in rows),'nearest_calls':sum(r['route'].count('human_eye_surface_nearest') for r in rows)},
 'source_file_sha256':{n:sha(WT/'human_eye_plugin'/n) for n in sources},
 'not_run':['new consumers','Blender','product calls','private cost or mapping reads','performance estimation']}
(OUT/'MECHANISM.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result['counts']))
