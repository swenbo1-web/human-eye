"""Independent fixed-truth and cache provenance audit. Offline, no product imports."""
import ast
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch

TREE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
BATCH=TREE/'verification/m4_surface_scan_continuity_001_fix2'
CELL=BATCH/'episodes/C'
WORK=CELL/'owner/native'
QUAL=TREE/'verification/m4_surface_scan_001/qualification'
HOST='9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9'
SOURCE='4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
EXPECTED_SHA={
 'BASE_TRUTH.json':'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
 'EDIT_TRUTH.json':'ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91',
 'BASE_SNAPSHOT.json':'f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b',
 'EDIT_SNAPSHOT.json':'beb4e441b1898c6aedbe633828b1a93948f1d5be172ded9e1a884c8bdebffd80'}
inputs={};checks=[];real_read=Path.read_bytes
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
def raw(path):
    data=real_read(path);inputs[str(path)]={'sha256':digest(data),'bytes':len(data)};return data
def load(path):return json.loads(raw(path))
def check(label,ok,**details):checks.append({'label':label,'passed':bool(ok),**details})
def require(ok,label):
    if not ok:raise AssertionError(label)
def bits(value):return struct.pack('>d',value)
def names(pair,ids):return tuple(sorted(ids[x] for x in pair))
def fraction(value):return Fraction(int(value['numerator']),int(value['denominator']))
def decimal_sqrt(value):
    with localcontext() as ctx:
        ctx.prec=90
        return (Decimal(value.numerator)/Decimal(value.denominator)).sqrt()

for name,sha in EXPECTED_SHA.items():check('fixed_sha:'+name,digest(raw(QUAL/name))==sha)
truth={s:load(QUAL/(s+'_TRUTH.json')) for s in ('BASE','EDIT')}
references={s:load(QUAL/(s+'_SNAPSHOT.json')) for s in ('BASE','EDIT')}
episode=load(CELL/'RESULTS.json')
snapshots={'BASE':load(CELL/'owner/INITIAL.json'),'EDIT':episode['registered_pose']['snapshot']}
audit=[json.loads(line) for line in raw(CELL/'owner/audit.jsonl').splitlines()]
host_events=[json.loads(line) for line in raw(WORK/'WORKER_EVENTS.jsonl').splitlines()]
old_reader_path=TREE/'verification/m4_surface_scan_continuity_001_fix1/qualification/verify_continuity.py'
parsed=ast.parse(raw(old_reader_path).decode('utf8'))
node=next(n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=='read_capture')
namespace={'json':json,'Path':Path,'require':require,'canonical':canonical,'digest':digest,'HOST_SOURCE_SHA':HOST}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(old_reader_path),'exec'),namespace)
reader=namespace['read_capture']
for path in ['scene_cache.py','scene_residency.py','surface_scan.py','task_query.py','read_context.py','live_service.py','geometry_safety.py']:
    raw(TREE/'human_eye_plugin'/path)

truth_pairs={state:{tuple(sorted((r['object_a'],r['object_b']))):r for r in content['pairs']} for state,content in truth.items()}
ids={'blender:'+digest(canonical(['',r['name']])):r['name'] for r in snapshots['BASE']['objects']}
all_pairs=set(truth_pairs['BASE'])
check('complete_truth_pair_set',len(ids)==24 and len(all_pairs)==276 and all_pairs==set(truth_pairs['EDIT']))
turns={}; summaries={};distance_errors=[]
for turn,state,expected_matches,expected_kernels in [('BASE','BASE',71,112),('REPEAT','BASE',71,0),('EDIT','EDIT',72,10)]:
    row=load(CELL/('TURN_'+turn+'.json'))
    response=row['response'];body=json.loads(response['result']['content'][0]['text'])
    observes=[a for a in audit if a.get('event')=='observe' and a.get('trace_id')==body['trace_id']]
    check(turn+':one_trace_bound_observe',len(observes)==1)
    work=observes[0]['task_work']
    hosts=[h for h in host_events if row['started_ns']<=h.get('started_ns',-1)<=row['ended_ns']]
    check(turn+':one_completed_capture_in_full_window',len(hosts)==1 and hosts[0]['status']=='completed' and hosts[0]['started_ns']+hosts[0]['elapsed_ns']<=row['ended_ns'])
    event=hosts[0];sequence=event['sequence'];read_paths=[]
    def prior_wire_only(path):
        if 'WIRE' in path.parts and path.name!='INDEX.json':
            require(int(path.parent.name)<=sequence,'forbidden_future_wire')
        read_paths.append(str(path));return raw(path)
    with patch.object(Path,'read_bytes',prior_wire_only):captured=reader(WORK,event)
    check(turn+':only_current_or_prior_wire',all(not ('WIRE' in Path(p).parts and Path(p).name!='INDEX.json') or int(Path(p).parent.name)<=sequence for p in read_paths))
    delta=captured['delta'];packet=delta['capture'];binding=packet['binding'];meshes=packet['capture']['meshes']
    resources={(r['id'],r['revision']):r for r in captured['retained_resources']}
    expected={r['name']:r for r in references[state]['objects']};source={r['name']:r for r in snapshots[state]['objects']}
    captured_geometry={};resource_refs={}
    check(turn+':source_names',set(expected)==set(source)==set(ids.values()))
    for mesh in meshes:
        name=mesh['name'];ref=mesh['_scene_resource'];res=resources[(ref['id'],ref['revision'])]
        geometry={'vertices_local':res['vertices_local'],'faces':res['faces'],'matrix_world':ref['matrix']}
        captured_geometry[name]=geometry;resource_refs[name]=ref
        check(turn+':actual_source_geometry:'+name,all(canonical(geometry[k])==canonical(source[name][k])==canonical(expected[name][k]) for k in geometry))
        check(turn+':actual_identity_and_unit:'+name,ids[mesh['object_id']]==name and ref['scale']==snapshots[state]['unit_scale_m']==references[state]['unit_scale_m']==1.0)
    check(turn+':complete_supported_scope',len(meshes)==24 and packet['scope_issues']==[] and len(packet['coverage'])==24 and all(r['source_status']=='supported' and r['source_mode']=='evaluated_static' for r in packet['coverage']))
    check(turn+':host_and_result_origin',binding['host_source_sha256']==body['binding']['host_source_sha256']==HOST and body['binding']['runtime_source_sha256']==SOURCE and binding['host_identity']['document_epoch']==body['binding']['document_epoch'] and binding['directory_sha256']==body['binding']['directory_sha256'])
    check(turn+':fixed_capture_frame_units',binding['frame']==references[state]['frame_current']==1 and binding['scale_length']==1.0 and binding['unit']=='m' and binding['coordinate_frame']=='world' and binding['same_main_thread_read'] is True)
    check(turn+':query_and_output_contract',row['request']['params']['arguments']['query']=={'mode':'surface_scan','threshold_m':.002} and 'response_detail' not in row['request']['params']['arguments'] and body['result_kind']=='surface_scan' and body['status']=='complete' and body['threshold_m']==.002 and body['unit']=='m' and body['coordinate_frame']=='world' and body['execution_authority'] is False and body['measurement_semantics']['solid_relation']=='not_evaluated')
    dispositions={};counts=Counter();oracle=truth_pairs[state]
    for d in work['dispositions']:
        pair=names(d['object_ids'],ids);check(turn+':unique_pair:'+str(pair),pair not in dispositions)
        dispositions[pair]=d;counts[d['status']]+=1
        q=fraction(oracle[pair]['exact_squared_distance_m2']);match=q<=Fraction('0.002')**2
        check(turn+':truth_membership:'+str(pair),match==oracle[pair]['matches_threshold'] and (d['status']=='measured_match')==match)
        if d['status']=='bound_excluded':
            check(turn+':valid_exclusion:'+str(pair),d['lower_bound_m']>.002 and Fraction(d['lower_bound_m'])**2<=q)
        else:
            actual=d['distance_m'];error=abs(Decimal.from_float(actual)-decimal_sqrt(q));distance_errors.append(error)
            check(turn+':measured_distance:'+str(pair),type(actual)is float and math.isfinite(actual) and actual>=0 and error<=Decimal('1e-10') and d['status'] in ('measured_match','measured_nonmatch'))
    check(turn+':all_276_dispositions',set(dispositions)==all_pairs and len(work['dispositions'])==276)
    public={}
    check(turn+':compact_column_contract',body['match_columns']==['object_a','object_b','object_a_ref','object_b_ref','distance_m','distance_mm'])
    for item in body['matches']:
        a,b,ar,br,d,mm=item;pair=tuple(sorted((a,b)));objects=body['objects']
        check(turn+':public_names_ID_units:'+str(pair),objects[ar]['name']==a and objects[br]['name']==b and ids[objects[ar]['id']]==a and ids[objects[br]['id']]==b and bits(mm)==bits(d*1000.0))
        check(turn+':public_raw_distance_matches_private:'+str(pair),pair not in public and bits(d)==bits(dispositions[pair]['distance_m']))
        public[pair]=d
    expected_public={p for p,v in oracle.items() if v['matches_threshold']}
    check(turn+':complete_public_matches',set(public)==expected_public and len(public)==expected_matches)
    check(turn+':coverage_matches_raw',all(body['coverage'][key]==counts[key] for key in ['bound_excluded','measured_match','measured_nonmatch','unknown','deferred']) and body['coverage']['objects']==24 and body['coverage']['total_pairs']==276 and body['scope_issues']==body['unsupported_objects']==body['unresolved']==[])
    check(turn+':delivery_complete',body['delivery']['complete'] is True and body['delivery']['matches_total']==body['delivery']['delivered_matches']==expected_matches)
    diagnostics={names(json.loads(key),ids):value for key,value in work.get('pairs',{}).items()}
    object_digests={}
    for key,value in work.get('pairs',{}).items():
        pair_ids=json.loads(key);pair=names(pair_ids,ids);deps=value['surface_dependency_objects']
        check(turn+':dependency_used:'+str(pair),value['surface_dependency_used'] is True and len(deps)==2)
        for oid,dep in zip(pair_ids,deps):
            check(turn+':object_dependency_consistent:'+ids[oid]+':'+str(pair),oid not in object_digests or object_digests[oid]==dep)
            object_digests[oid]=dep
        key_payload={'algorithm':'task-surface-proximity-exact-world-rank-v3','parameters':{'source':'blender','unit':'m','coordinate_frame':'world','world_witness_tolerance_m':1e-9,'retain_exact_rank':True},'focal':{'surface_scan_resource_dependency':deps[0]},'reference':{'surface_scan_resource_dependency':deps[1]}}
        check(turn+':pair_dependency_key_recomputed:'+str(pair),digest(canonical(key_payload))==value['surface_dependency_key'])
    counted_kernels=sum(v['surface_pair_count'] for v in diagnostics.values());counted_hits=sum(v['surface_pair_cache_hit'] is True for v in diagnostics.values())
    check(turn+':kernel_count_from_pair_records',counted_kernels==work['kernel_calls']==expected_kernels)
    check(turn+':cache_count_from_pair_records',counted_hits==work['cache_hits'] and len(diagnostics)==work['pair_calls'])
    before=work['measurement_cache_before'];after=work['measurement_cache_after']
    check(turn+':cache_computation_delta',after['measurement_computations']-before['measurement_computations']==counted_kernels and after['measurement_hits']-before['measurement_hits']==counted_hits)
    turns[turn]={'row':row,'body':body,'work':work,'capture':captured,'geometry':captured_geometry,'refs':resource_refs,'dispositions':dispositions,'public':public,'diagnostics':diagnostics,'object_digests':object_digests}
    summaries[turn]={'capture_sequence':sequence,'matches':len(public),'dispositions':dict(counts),'new_kernel_records':counted_kernels,'cache_hit_records':counted_hits,'result_cache_hit':work['result_cache_hit'],'resources_transmitted':len(delta['resources']),'resolved_resources':len(resources),'resource_origin_sequences':sorted({r['sequence'] for r in captured['resource_origins']}),'response_text_bytes':len(response['result']['content'][0]['text'].encode())}

base,repeat,edit=(turns[t] for t in ['BASE','REPEAT','EDIT'])
check('repeat_all_geometry_resource_refs_identical',canonical(base['geometry'])==canonical(repeat['geometry']) and canonical(base['refs'])==canonical(repeat['refs']))
check('repeat_binding_and_all_dispositions_identical',base['body']['binding']==repeat['body']['binding'] and canonical(base['work']['dispositions'])==canonical(repeat['work']['dispositions']))
check('repeat_complete_result_cache_evidence',repeat['work']['result_cache_hit'] is True and repeat['work']['kernel_calls']==repeat['work']['pair_calls']==0 and repeat['diagnostics']=={} and repeat['work']['measurement_cache_before']==repeat['work']['measurement_cache_after'])
check('repeat_complete_response_fact_equality',base['public']==repeat['public'] and base['body']['coverage']==repeat['body']['coverage'])
changed_objects=[name for name in base['geometry'] if canonical(base['geometry'][name])!=canonical(edit['geometry'][name])]
check('edit_only_Obj_008_geometry_changes',changed_objects==['Obj_008'])
check('edit_same_local_geometry_all_objects',all(canonical(base['geometry'][n][k])==canonical(edit['geometry'][n][k]) for n in base['geometry'] for k in ['vertices_local','faces']))
matrix_changes=[(i,j,base['geometry']['Obj_008']['matrix_world'][i][j],edit['geometry']['Obj_008']['matrix_world'][i][j]) for i in range(4) for j in range(4) if bits(base['geometry']['Obj_008']['matrix_world'][i][j])!=bits(edit['geometry']['Obj_008']['matrix_world'][i][j])]
check('edit_only_registered_matrix_z',len(matrix_changes)==1 and matrix_changes[0][:2]==(2,3) and matrix_changes[0][3]==references['EDIT']['objects'][7]['matrix_world'][2][3])
check('edit_bound_generation_stable_state_invalidated',all(base['body']['binding'][k]==edit['body']['binding'][k] for k in ['document_epoch','host_source_sha256','runtime_source_sha256']) and all(base['body']['binding'][k]!=edit['body']['binding'][k] for k in ['scene_revision','scene_fingerprint','directory_sha256']))
changed_deps=[ids[oid] for oid,dep in base['object_digests'].items() if edit['object_digests'].get(oid)!=dep]
check('edit_only_Obj_008_dependency_digest_changes',changed_deps==['Obj_008'])
hits=[];kernels=[]
for pair,diag in edit['diagnostics'].items():
    if diag['surface_pair_cache_hit']:
        hits.append(pair)
        check('edit_cached_pair_real_geometry_and_key:'+str(pair),'Obj_008' not in pair and pair in base['diagnostics'] and diag['surface_dependency_key']==base['diagnostics'][pair]['surface_dependency_key'] and all(canonical(base['geometry'][n])==canonical(edit['geometry'][n]) for n in pair) and canonical(edit['dispositions'][pair])==canonical(base['dispositions'][pair]) and diag['surface_pair_count']==0 and diag['surface_work']=={})
    else:
        kernels.append(pair)
        check('edit_computed_pair_changes_dependency:'+str(pair),'Obj_008' in pair and diag['surface_pair_count']==1 and diag['surface_work']['work_units']>0 and (pair not in base['diagnostics'] or diag['surface_dependency_key']!=base['diagnostics'][pair]['surface_dependency_key']))
check('edit_104_real_hits_plus_10_changed_pairs',len(hits)==104 and len(kernels)==10 and edit['work']['pair_calls']==114 and edit['work']['result_cache_hit'] is False)
unchanged=[p for p in all_pairs if 'Obj_008' not in p]
check('all_253_unrelated_pair_dispositions_identical',len(unchanged)==253 and all(canonical(base['dispositions'][p])==canonical(edit['dispositions'][p]) for p in unchanged))
added=sorted(set(edit['public'])-set(base['public']));removed=sorted(set(base['public'])-set(edit['public']))
changed_matches=[{'pair':p,'before_m':base['public'][p],'after_m':edit['public'][p]} for p in sorted(set(base['public'])&set(edit['public'])) if bits(base['public'][p])!=bits(edit['public'][p])]
check('only_added_match_002_008',added==[('Obj_002','Obj_008')] and removed==[])
check('only_two_existing_match_distances_change_to_zero',[r['pair'] for r in changed_matches]==[('Obj_008','Obj_013'),('Obj_008','Obj_014')] and all(r['after_m']==0.0 for r in changed_matches))
new_candidates=sorted(set(edit['diagnostics'])-set(base['diagnostics']))
check('only_two_new_measured_candidates',new_candidates==[('Obj_002','Obj_008'),('Obj_003','Obj_008')])
check('new_negative_003_008_is_measured_nonmatch',edit['dispositions'][('Obj_003','Obj_008')]['status']=='measured_nonmatch')
check('3_execution_successes_no_new_live_by_review',episode['execution_counts']=={'planned':3,'attempted':3,'successful_returns':3,'succeeded':3,'failed':0,'not_run':0})

result={'scope':'Three recorded FIX2 C business calls independently checked against frozen exact truth and real capture resource histories; existing read_capture source function reused, no full author checker/product import/live/model/API execution.',
 'delivery':'56caf228f6d0224f36796606c7f27b3c24223768','preparation':'1511af696b564a0b261b70d5f0562325daa1f2a7',
 'parent_task':'f275a20b-0fb0-4d1a-88ac-1cf335b3b929','parent_revision':1,'parent_write':624,
 'own_AL_assignment':'Old child assignment unchanged; parent handle not borrowed.',
 'summary':{'checks':len(checks),'passed':sum(r['passed'] for r in checks),'failed':sum(not r['passed'] for r in checks)},
 'business_denominator':{'recorded_C_episodes':1,'recorded_C_business_calls':3,'new_review_live_calls':0,'reviewed_pair_dispositions':828,'reviewed_public_matches':214},
 'turns':summaries,'max_absolute_distance_error_m':str(max(distance_errors)),
 'EDIT_delta':{'changed_objects':changed_objects,'matrix_changes':matrix_changes,'added_matches':added,'added_match_distance_m':edit['public'][('Obj_002','Obj_008')],'removed_matches':removed,'changed_existing_matches':changed_matches,'unrelated_identical_pairs':len(unchanged),'cache_hit_pairs':hits,'new_kernel_pairs':kernels,'new_candidates':new_candidates,'new_negative_distance_m':edit['dispositions'][('Obj_003','Obj_008')]['distance_m']},
 'limits':['Exact truth was fixed and SHA-checked, not regenerated from triangles in this review.','Kernel/cache counts are corroborated by per-pair diagnostics, source dependencies and actual geometry; no new instrumented live profiler was run.','Dependency object digests contain an unrecorded private decoder-owner token. Pair keys were independently recomputed from recorded object digests; owner-token preimages were not reconstructed.','No actual model thread continuity, model recall, provider usage or end-to-end N/C model benefit was tested.'],
 'checks':checks}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUT_SHA256.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result['summary']))
print(json.dumps({'turns':summaries,'max_error':result['max_absolute_distance_error_m'],'added_matches':added,'changed_matches':changed_matches,'unrelated':len(unchanged)},ensure_ascii=False))
for row in checks:
    if not row['passed']:print(json.dumps(row,ensure_ascii=False))
