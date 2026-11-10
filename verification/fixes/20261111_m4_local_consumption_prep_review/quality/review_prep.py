"""Read fixed preparation and run synthetic postprocessing only."""
from pathlib import Path
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import socket
import subprocess
import sys
from unittest.mock import patch

B=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001')
OLD=B.parent/'m4_observation_baseline_001'
OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def ck(label,ok):checks.append({'label':label,'passed':bool(ok)})
def read(p):return json.loads(p.read_bytes())
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    sys.modules[name]=result
    spec.loader.exec_module(result)
    return result

old=read(OLD/'scoring/SCORING_CONTRACT.json');new=read(B/'scoring/SCORING_CONTRACT.json')
changed=[k for k in old if old[k]!=new.get(k)]
ck('only_three_existing_metadata_fields_changed',set(changed)=={'cycle_id','scope','fixed_sample_policy'})
ck('only_added_sample_metadata',set(new)-set(old)=={'sample_metadata'})
def leaves(v):
    if isinstance(v,dict):return sum(leaves(x) for x in v.values())
    if isinstance(v,list):return sum(leaves(x) for x in v)
    return 1
unchanged=[k for k in old if k not in changed]
ck('17_fields_86_leaves_unchanged',len(unchanged)==17 and sum(leaves(old[k]) for k in unchanged)==86)
ck('old_contract_raw_copy_exact',(B/'scoring/SCORING_CONTRACT_BASELINE.json').read_bytes()==(OLD/'scoring/SCORING_CONTRACT.json').read_bytes())
plan=read(B/'PLAN.json');sequence=plan['sequence'];mapping=read(B/'private/ANON_MAP.json')
ck('nine_balanced_latin_slots',[x['group'] for x in sequence]==['N','P0','P1','P0','P1','N','P1','N','P0'])
ck('map_has_exact_nine_slots_and_opaque_uniques',len(mapping['rows'])==9 and len({x['anonymous_id'] for x in mapping['rows']})==9 and all(all(s[k]==r[k] for k in ('cell','task','round','group')) for s,r in zip(sequence,mapping['rows'])))
ck('map_hash_pinned',sha(B/'private/ANON_MAP.json')==new['sample_metadata']['anonymous_mapping_sha256']==plan['private_anonymous_map_sha256'])
ck('sequence_hash_pinned',sha(B/'SEQUENCE.json')==new['sample_metadata']['sequence_sha256'])

# Compile only pure grouping functions/constants from driver, importing neither
# driver runtime nor consumer/actor/product modules.
tree=ast.parse((B/'runtime/driver.py').read_text(encoding='utf-8'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('arm_runtime','go_contract') or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('CYCLE','SOURCE_BY_PROFILE','COMMIT_BY_PROFILE','GROUP_ORDER') for t in n.targets)]
scope={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'pure-driver-selected-AST','exec'),scope)
for slot in sequence:
    before=copy.deepcopy(slot);internal,ready,profile=scope['arm_runtime'](plan,slot)
    ck('internal_external_binding_'+slot['cell'],slot==before and internal is not slot and internal['external_group']==slot['group'] and internal['group']==('N' if slot['group']=='N' else 'P') and profile==('P1' if slot['group']=='P1' else 'P0'))

syn=module('root_synthetic_fixture',B/'synthetic/verify_packager.py')
syn.OUT=OUT/'synthetic_replay'
stream=io.StringIO()
with contextlib.redirect_stdout(stream):code=syn.main()
(OUT/'SYNTHETIC_STDOUT.txt').write_text(stream.getvalue(),encoding='utf-8')
synthetic=read(syn.OUT/'RESULTS.json')
ck('author_synthetic_replayed_with_root_only_output',code==0 and synthetic['passed'] and synthetic['external_attempts']=={'subprocess':0,'socket':0})

# A real executable path can fail at first input/backend setup, before any
# consumer is launched. Reproduce only packaging of that terminal stop record.
pack=module('root_packager',B/'quality_handoff/pack_quality.py')
folder=OUT/'zero_launch/e';(folder/'q').mkdir(parents=True)
encode=lambda v:(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
sm={'rows':[dict(s,anonymous_id='answer_'+hashlib.sha256(('synthetic-only-'+s['cell']).encode()).hexdigest()[:16]) for s in sequence]}
smraw=encode(sm)
sp={'cycle_id':pack.CYCLE,'batch':pack.CYCLE,'logical_denominator':9,'per_arm':3,'arms':{'N':{},'P0':{},'P1':{}},'image_count':1,'new_images':0,'sequence':sequence,'private_anonymous_map_sha256':hashlib.sha256(smraw).hexdigest()}
spraw=encode(sp)
run={'synthetic':True,'records':[{**sequence[0],'consumer':None,'errors':[{'type':'TimeoutError','message':'synthetic actor startup failure'}]}],'stop':'synthetic first-cell failed before consumer','batch_ended_ns':1}
for name,raw in {'PLAN.json':spraw,'FREEZE.json':encode({'plan_sha256':hashlib.sha256(spraw).hexdigest()}),'private/ANON_MAP.json':smraw,'RUN_RESULT.json':encode(run)}.items():
    p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
pack.EVAL=folder;pack.HERE=folder/'q'
exception=None;original=sys.argv
def forbidden(*a,**k):raise AssertionError('external operation forbidden')
try:
    sys.argv=['synthetic-only','h']
    with patch.object(subprocess,'Popen',forbidden),patch.object(socket,'socket',forbidden):pack.main()
except BaseException as exc:exception={'type':type(exc).__name__,'message':str(exc)}
finally:sys.argv=original
ck('zero_launch_terminal_stop_can_be_packaged',exception is None)
report={'status':'PASS' if all(x['passed'] for x in checks) else 'ISSUE','checks':checks,'scoring_changed_fields':changed,'unchanged_fields':len(unchanged),'unchanged_leaves':sum(leaves(old[k]) for k in unchanged),'synthetic_replay_checks':synthetic['check_count'],'zero_launch_reproduction':exception,'packager_sha256':sha(B/'quality_handoff/pack_quality.py'),'scoring_sha256':sha(B/'scoring/SCORING_CONTRACT.json'),'driver_sha256':sha(B/'runtime/driver.py'),'imported_consumer_product_Blender':False,'new_consumers':0,'Blender_calls':0,'private_actual_map_values_exposed':False}
p=OUT/'RESULTS.json'
with p.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({'status':report['status'],'checks':len(checks),'failed':[x['label'] for x in checks if not x['passed']],'synthetic_replay_checks':synthetic['check_count'],'zero_launch':exception,'sha256':sha(p)}))
