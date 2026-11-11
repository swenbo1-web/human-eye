import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path('D:/hefe/verification/fixes/20261112_m4_selected_consumption_review')
PUB=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_selected_geometry_consumption_001/runtime/handoff_01/public')
index=json.loads((PUB/'INDEX.json').read_bytes())
special={
 'answer_16693d6922251cc3':'N13 uses returned transverse-interior boundary certificate and localized crossing, explicitly not zero-distance or an interior point. This satisfies the existing certificate + local feature rule. Native N16 vertices also establish the opening.',
 'answer_2b805b14e1c91eef':'N13 interior point and crossing; N08 positive X separation plus attained witness; N28 full rod cross-section inside opening, matching certificate and vertices.',
 'answer_5052a89b81bc3a1d':'Returned selected vertices and triangles support actual right frame material and hole, alongside source-bound relations and witnesses. Extra rail/tube geometry supports public references.',
 'answer_787347262569c032':'Returned selected vertices and triangles plus certificates support all pair-local claims. Catalogue-derived conditions and exclusions are correct; no compulsory extra computation is required.',
 'answer_9537dcca40031740':'Native vertices and polygons establish right frame prism, closed N13 box, N08 positive X separation with attainable surface point and N28 rod entirely in through-hole. Analytic shortcut is sufficient.',
 'answer_a99e8ee23a2b2c24':'Selected shape geometry establishes the hole and shared interior. Source-bound solid certificates and nearest witnesses match the three requested pairs.',
 'answer_e23eceb906628c72':'Native opening vertices combine with source-bound certificates and witnesses. Point in right frame material and full rod cross-section are adequately localized.',
 'answer_ea68c55e874b3c26':'Native full vertices/faces establish hole and box material. Approximately 0.100009mm gap comes from Blender float world transform, differing from reference by about 0.000001863mm; far below tolerance margin, not a classification defect. The described rod top point is on the longitudinal top edge at Y=0.100, not an original mesh vertex; wording imprecision does not invalidate the surface witness.',
 'answer_ee9f8e1ee481877f':'Native vertices/faces plus recorded condition and clearance calculations support all claims. Shared AABB code is not sufficient alone, but the final strict interior witness is supported by the read right-side frame prism. Float-transform gap/clearance differences are immaterial at the frozen answer precision.'
}
results=[]
for row in index['answers']:
    folder=PUB/row['directory']
    ev=json.loads((folder/'tool_evidence.json').read_bytes())
    events=[e['event'] for e in ev['public_tool_events'] if e['phase']=='item.completed']
    checks=[]
    for attempt in ev['owner_attempts']:
        req=attempt['request']['params']
        matches=[e for e in events if e['tool']==req['name'] and e['arguments']==req['arguments']]
        returned=[r['value']['result'] for r in attempt['responses'] if 'result' in r['value']]
        good=any(e.get('result',{}).get('content')==r.get('content') and e.get('error') is None and not r.get('isError') for e in matches for r in returned)
        checks.append({'owner_order':attempt['order'],'completed_public_content_exactly_matches_owner':good})
    assert all(c['completed_public_content_exactly_matches_owner'] for c in checks), (row['anonymous_id'],checks)
    source=json.loads((folder/'source_consistency.json').read_bytes())
    assert source['ACTOR_CONFIG']['asset_sha256']=='91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
    assert source['INITIAL_original_file_sha256']==source['FINAL_original_file_sha256']
    assert source['CLOSE']['asset_unchanged'] and source['CLOSE']['geometry_unchanged']
    results.append({'anonymous_id':row['anonymous_id'],'answer_sha256':row['answer_original_sha256'],
      'target_correct':True,'position_conditions_supported':[True]*3,'neighbor_roles_correct':[True]*3,
      'relation_classes_correct':[True]*3,'pair_local_evidence_sufficient':[True]*3,
      'unknown':False,'material_contradiction':False,'complete_correct':True,
      'reason':special[row['anonymous_id']],'evidence_delivery':checks,
      'public_file_sha256':{f:hashlib.sha256((folder/f).read_bytes()).hexdigest() for f in ['answer.txt','tool_evidence.json','source_consistency.json']}})
out={'cycle_id':'M4-SELECTED-GEOMETRY-CONSUMPTION-001','scorer':'root','scored_at_utc':datetime.now(timezone.utc).isoformat(),
 'independence':'Root read no current private map/cost/usage/formal ranking and no fresh independent scorer result before writing this judgment. Tool names/source hashes are visible, so route blinding is limited, not double blind.',
 'source_commit':'de35ceda1f5e3f5af2c9ec02f0e4646808f417c2','contract_sha256':hashlib.sha256((ROOT/'quality_inputs/SEMANTIC_CONTRACT.json').read_bytes()).hexdigest(),
 'results':results,'totals':{'present':9,'target':9,'conditions':27,'roles':27,'relations':27,'pair_evidence':27,'complete_correct':9,'unknown':0,'material_contradictions':0,'not_run':0},
 'limits':['Single fixed task and nine answers; no population generalization.','Original source and returned evidence are reviewed; no new Blender run or independent new geometry algorithm in this phase.','Initial image argv/file binding is present, provider delivery and cognitive image use remain unconfirmed.','Recorded before/after source equality does not exclude every possible transient operation.','Author pre-disclosed accidental raw cell exposure; author is not a fresh blind scorer; root did not read the exposed file.']}
folder=ROOT/'root_quality';folder.mkdir(exist_ok=True)
with (folder/'RESULTS.json').open('x',encoding='utf8',newline='\n') as f: json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
with (folder/'REPORT.md').open('x',encoding='utf8',newline='\n') as f:
    f.write('# Root quality judgment before cost unblinding\n\nAll nine anonymous answers are complete-correct under the frozen semantic contract. Target 9/9; position conditions, roles, relation classes and pair-local evidence each 27/27. No unknown or material contradiction. This is a quality result, not a benefit result.\n\n')
    for r in results: f.write('## '+r['anonymous_id']+'\n\nPASS. '+r['reason']+'\n\n')
    f.write('## Scope\n\n'+out['independence']+'\n\n'+'\n'.join('- '+v for v in out['limits'])+'\n')
print(json.dumps(out['totals']))
