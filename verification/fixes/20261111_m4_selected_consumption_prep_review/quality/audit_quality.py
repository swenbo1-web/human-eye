"""Independent saved-evidence and no-process synthetic quality audit."""
import ast, copy, hashlib, io, json, os, re, socket, subprocess, sys, types
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = WT / 'verification/m4_selected_geometry_consumption_001'
OLD = WT / 'verification/m4_local_relation_consumption_001'
BASE = WT / 'verification/m4_observation_baseline_001'
checks = []
def sha(raw): return hashlib.sha256(raw).hexdigest()
def raw(p): return p.read_bytes()
def read(p): return json.loads(raw(p))
def enc(v): return (json.dumps(v, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
def check(name, ok):
    checks.append({'check': name, 'passed': bool(ok)})
    assert ok, name
def put(p, v):
    assert p.resolve().is_relative_to(OUT.resolve())
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f: f.write(v if isinstance(v, bytes) else enc(v))

new = read(B/'scoring/SCORING_CONTRACT.json')
old = read(OLD/'scoring/SCORING_CONTRACT.json')
outer = {'cycle_id','fixed_sample_policy','sample_metadata','scope'}
fields = sorted(set(old)-outer)
check('same_contract_field_set', set(new)==set(old))
check('seventeen_semantic_fields', len(fields)==17)
for key in fields: check('semantic:'+key, new[key]==old[key])
check('baseline_contract_copy', raw(B/'scoring/SCORING_CONTRACT_BASELINE.json')==raw(OLD/'scoring/SCORING_CONTRACT.json'))
for item in read(B/'scoring/SCORING_CONTRACT_EQUIVALENCE.json')['reference_copies']:
    current=B/'scoring'/item['path']
    historical=OLD/'scoring'/item['path']
    check('reference_copy:'+item['path'], raw(current)==raw(historical) and sha(raw(current))==item['sha256'])
source=read(B/'scoring/SOURCE_BINDING.json')
for item in source['files']:
    p=BASE/item['path']
    check('resolved_truth_source:'+item['path'], p.is_file() and len(raw(p))==item['bytes'] and sha(raw(p))==item['sha256'])
binding=read(B/'scoring/INPUT_BINDING.json')
for key in ('prompt','image','scene'):
    p=B/binding['inputs'][key]
    check('current_input_binding:'+key, sha(raw(p))==binding['inputs'][key+'_sha256'])
for item in read(B/'scoring/SOURCE_REUSE.json')['copies']:
    check('original_reference_copy:'+item['destination'], raw(B/item['destination'])==raw(WT/item['source']) and sha(raw(WT/item['source']))==item['sha256'])

plan=read(B/'PLAN.json'); mapping=read(B/'private/ANON_MAP.json'); rows=mapping['rows']
check('map_pinned', sha(raw(B/'private/ANON_MAP.json'))==plan['private_anonymous_map_sha256']==new['sample_metadata']['anonymous_mapping_sha256'])
check('map_nine_unique_opaque_ids', len(rows)==9 and len({r['anonymous_id'] for r in rows})==9 and all(re.fullmatch('answer_[0-9a-f]{16}',r['anonymous_id']) for r in rows))
check('map_slots_bound_without_reordering', all({k:r[k] for k in ('cell','task','round','group')}==s for r,s in zip(rows,plan['sequence'],strict=True)))
check('sequence_pinned', sha(raw(B/'SEQUENCE.json'))==new['sample_metadata']['sequence_sha256'])
correction=read(B/'preparation_history/ANONYMOUS_MAPPING_CORRECTION.json')
for item in correction['archive']:
    check('correction_original_retained:'+item['source'],sha(raw(B/item['archived']))==item['sha256'])

benefit=read(B/'BENEFIT_CONTRACT.json')
check('benefit_both_baselines', benefit['advance_requires_both_comparisons'] is True and {x['reference'] for x in benefit['comparisons']}=={'N','P'})
for row in benefit['comparisons']:
    check('benefit_rule:'+row['reference'], row['candidate']=='G' and row['required_improvement_fraction']==0.1 and row['full_cell_median_rule']==row['actual_total_input_plus_output_rule']=='G <= reference' and row['useful_improvement_rule']=='G time median <= 0.90 * reference OR G total actual input+output <= 0.90 * reference')
check('nine_slots_no_replacement', benefit['logical_denominator']==9 and benefit['replacements']==0 and benefit['historical_pooling'] is False)

pack_path=B/'runtime/pack_quality.py'; old_pack=OLD/'quality_handoff/pack_quality.py'
old_text=raw(old_pack).decode()
expected=old_text.replace("CYCLE = 'M4-LOCAL-RELATION-CONSUMPTION-001'", "CYCLE = 'M4-SELECTED-GEOMETRY-CONSUMPTION-001'")
expected=expected.replace("{'N':'N','P0':'P','P1':'P'}", "{'N':'N','P':'P','G':'P'}")
expected=expected.replace("{'N','P0','P1'}", "{'N','P','G'}")
check('entire_packer_AST_only_expected_three_changes', ast.dump(ast.parse(expected),include_attributes=False)==ast.dump(ast.parse(raw(pack_path)),include_attributes=False))
source_pins={str(p):sha(raw(p)) for p in (pack_path,old_pack,B/'PLAN.json',B/'private/ANON_MAP.json',B/'scoring/SCORING_CONTRACT.json',B/'BENEFIT_CONTRACT.json',B/'MECHANISM_CLASSIFICATION.json')}
external_attempts=[]
def forbidden(*a,**kw):
    external_attempts.append('process/socket/signal')
    raise AssertionError('external operation forbidden')

with ExitStack() as guard:
    for key in ('Popen','run','call','check_call','check_output'):
        guard.enter_context(patch.object(subprocess,key,side_effect=forbidden))
    for key in ('socket','create_connection'):
        guard.enter_context(patch.object(socket,key,side_effect=forbidden))
    for key in ('system','kill'):
        guard.enter_context(patch.object(os,key,side_effect=forbidden))
    pack=types.ModuleType('_independent_packer'); pack.__file__=str(pack_path)
    exec(compile(raw(pack_path),str(pack_path),'exec'),pack.__dict__)
    for kind in ('consumer_none','consumer_null_pid'):
        folder=OUT/'synthetic'/kind
        synthetic_map={'synthetic':True,'rows':[dict(s,anonymous_id='answer_'+sha(('quality-audit|'+s['cell']).encode())[:16]) for s in plan['sequence']]}
        synthetic_plan=copy.deepcopy(plan)
        synthetic_plan['synthetic']=True
        synthetic_plan['private_anonymous_map_sha256']=sha(enc(synthetic_map))
        first=plan['sequence'][0]
        consumer=None if kind=='consumer_none' else dict(first,external_group=first['group'],consumer_pid=None,status='failed',valid_completion=False,thread_id=None,final=None,errors=[{'type':'SyntheticFailure','message':'no process was attempted'}])
        record=dict(first,consumer=consumer,finish=None,errors=[{'type':'SyntheticFailure','message':'no process was attempted'}],cell_started_ns=30,cell_ended_ns=40,full_cell_wall_ns=10,within_570s=True)
        run={'synthetic':True,'records':[record],'started_cells':1,'maximum_consumers':9,'all_planned_dispatched':False,'no_replacements':True,'stop':'synthetic terminal first-cell failure','batch_started_ns':10,'batch_ended_ns':50,'batch_wall_ns':40}
        controls={'PLAN.json':synthetic_plan,'private/ANON_MAP.json':synthetic_map,'FREEZE.json':{'plan_sha256':sha(enc(synthetic_plan))},'RUN_RESULT.json':run,'GO.json':{'synthetic':True,'real_GO':False,'task':pack.CYCLE,'authorized':True,'max_consumers':9,'plan_sha256':sha(enc(synthetic_plan))},'STARTED.json':{'synthetic':True,'started_ns':20,'max_consumers':9,'plan_sha256':sha(enc(synthetic_plan))}}
        for name,value in controls.items(): put(folder/name,value)
        for key in ('image','prompt'): put(folder/plan['inputs'][key],raw(B/plan['inputs'][key]))
        if consumer is not None: put(folder/'cells'/first['cell']/'CONSUMER.json',consumer)
        pack.HERE=folder/'quality'; pack.EVAL=folder
        pack.HERE.mkdir()
        original_argv=sys.argv; sys.argv=['synthetic-quality-only','handoff']
        capture=io.StringIO()
        try:
            with redirect_stdout(capture): pack.main()
        finally: sys.argv=original_argv
        index=read(pack.HERE/'handoff/public/INDEX.json')
        states=[a['execution_record_state'] for a in index['answers']]
        check(kind+':nine_slots_no_scores',index['fixed_slots']==len(index['answers'])==9 and index['scoring_performed'] is False)
        check(kind+':failed_plus_eight_not_run',states.count('not_run')==8 and states.count('failed_before_consumer' if consumer is None else 'failed')==1)
        check(kind+':no_invented_answers',all(a['answer_file'] is None and a['answer_state'] in ('missing','not_run') for a in index['answers']))

    geom={'objects':[{'id':'semantic_object','source':{'generation':'same_capture','group':'real fact','profile':'geometry','usage':{'cost':7}},'vertices_world_m':[[0.,1.,2.],[-3.2,4.,5.]],'triangles':[[0,1,0]],'unknown':{'reason':'semantic unknown','future_field':[None,True]}}],'units':'m','path':'C:\\semantic asset\\a.blend'}
    text=' \r\n'+json.dumps({'geometry':geom},ensure_ascii=False,indent=3)+'\n  '
    result={'content':[{'type':'text','text':text}],'isError':False,'geometry':geom,'measurement_contracts':{'geometry':geom},'future_unknown_field':geom}
    request={'jsonrpc':'2.0','id':'synthetic-envelope','method':'tools/call','params':{'name':'human_eye_spatial_relations','arguments':{'target':{'id':'semantic_object'},'candidates':[{'id':'other'}],'geometry':{'objects':[{'id':'semantic_object'}],'include_triangles':True}}}}
    for group in ('N','P','G'):
        slot=next(s for s in plan['sequence'] if s['group']==group)
        consumer=dict(slot,group='N' if group=='N' else 'P',external_group=group,status='completed',final=text)
        sources={'CONSUMER.json':enc(consumer),'PUBLIC_FINAL.txt':text.encode(),'owner/tool_01/REQUEST.json':enc(request),'owner/tool_01/RESPONSE.json':enc({'jsonrpc':'2.0','id':'synthetic-envelope','result':result})}
        dest=OUT/'synthetic'/'nested_payload'/group
        answer,private=pack.handoff_one(slot,{'anonymous_id':'answer_'+sha(('synthetic|'+group).encode())[:16]},slot,sources,dest)
        evidence=read(dest/'tool_evidence.json')['owner_attempts'][0]
        check(group+':nested_geometry_and_string_exact',evidence['responses'][0]['value']=={'result':result} and evidence['request']['params']==request['params'])
        check(group+':final_exact_and_present',raw(dest/'answer.txt')==text.encode() and answer['answer_state']=='present')
        check(group+':only_RPC_envelope_removed',all(x['rule']=='RPC_transport_envelope' for x in private['administrative_projections']))

check('no_external_operation_attempts',not external_attempts)
check('read_sources_unchanged',all(sha(raw(Path(p)))==value for p,value in source_pins.items()))
report={'passed':all(c['passed'] for c in checks),'check_count':len(checks),'checks':checks,'semantic_fields':fields,'source_pins':source_pins,'map_validated_without_publishing_formal_mapping':True,'external_operation_attempts':external_attempts,'new_models':0,'new_Blender':0,'new_product_processes':0,'synthetic_cases':{'zero_start_variants':2,'nested_geometry_group_variants':3},'scope':'Saved contract/source checks and direct current packer synthetic execution only. No original files modified; synthetic GO records under this report are not real authorization.'}
put(OUT/'RESULTS.json',report)
print(json.dumps({'passed':report['passed'],'checks':len(checks),'formal_mapping_not_exported':True}))
