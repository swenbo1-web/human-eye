"""Correct only old-scope instance equality; preserve first complete review."""
import copy
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
base = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_observation_region_anchors_001')
for src,dst in [('audit_pixel.py','audit_pixel_first.py'),('RESULTS.json','RESULTS_FIRST.json'),('INPUTS.json','INPUTS_FIRST.json')]:
    assert not (out/dst).exists(), 'first audit must not be replaced'
    (out/dst).write_bytes((out/src).read_bytes())
first = json.loads((out/'RESULTS_FIRST.json').read_text('utf-8'))
assert first['failures'] == [{'label':'history:preserved_scope','detail':None}]
paths = [base/'external_archive/f0079_RESULT_01.json',base/'inputs/historical/JOINED_SERVICE_RESULT.json',
         base/'external_archive/f0100_RESPONSE.json',base/'external_archive/f0104_RESPONSE.json']
data = [json.loads(p.read_bytes()) for p in paths]
checks=[]
new,old=data[:2]
left,right=copy.deepcopy(new['facts']['scope']),copy.deepcopy(old['facts']['scope'])
for name,scope,result in [('current',left,new),('historical',right,old)]:
    actual=scope['patch_support']['objects'][0]
    binding=result['binding']['objects'][0]
    checks.append({'label':name+'_scope_matches_own_runtime_object_binding',
                   'passed':all(actual[k] == binding[k] for k in ('host_id','instance_id','object_index','object_name'))})
    actual.pop('instance_id')
checks.append({'label':'scope_identical_except_independently_recreated_object_instance_id','passed':left==right})
columns=['image_index','region_index','front_facing','visible_surface_pixels','contrasting_boundary_pixels','readable','visible_pixel_bounds','visible_pixel_anchor']
for n,result in zip(['cold','hot'],data[2:]):
    value=json.loads(result['result']['content'][0]['text'])
    checks.append({'label':n+'_all_required_public_pixel_columns_present','passed':value['pixels']['columns']==columns})
correction={'passed':all(c['passed'] for c in checks),'checks':checks,
    'reason':'The old and new artifacts are independent Blender runs. Runtime object instance 282 versus 136 must bind to its own run, not equal across runs.',
    'new_instance':new['binding']['objects'][0]['instance_id'],'old_instance':old['binding']['objects'][0]['instance_id'],
    'inputs':[{ 'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
    'first_result_sha256':hashlib.sha256((out/'RESULTS_FIRST.json').read_bytes()).hexdigest(),
    'new_product_calls':0,'new_pixel_recomputations':0}
(out/'SCOPE_CORRECTION.json').write_text(json.dumps(correction,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
final=copy.deepcopy(first)
final.update(passed=correction['passed'],checks=first['checks']-1+len(checks),failures=[],
    history={'first_checks':first['checks'],'first_failures':first['failures'],'replacement_checks':len(checks),
             'replaced_assertion':'history:preserved_scope','correction_file':'SCOPE_CORRECTION.json'},
    check_groups={**first['check_groups'],'history':first['check_groups']['history']-1,'scope_and_columns_correction':len(checks)})
(out/'RESULTS.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':final['passed'],'accepted_checks':final['checks'],'correction':correction},indent=2))
