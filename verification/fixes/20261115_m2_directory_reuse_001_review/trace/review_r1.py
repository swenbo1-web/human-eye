"""Independent bounded historical trace audit; stdlib, no product imports/calls."""
from pathlib import Path
import json, hashlib, collections

N=Path('C:/Users/Administrator/.codex/worktrees/m2-dir-001/hefe/verification/m2_directory_resource_reuse_001')
OUT=Path(__file__).parent
checks=[]; inputs={}; expected={}
def check(name,value):
    checks.append({'check':name,'passed':bool(value)})
def read(path):
    path=Path(path); raw=path.read_bytes(); key=str(path.resolve()); h=hashlib.sha256(raw).hexdigest()
    if key not in inputs and key in expected: check('pinned source '+key,h==expected[key])
    inputs[key]={'sha256':h,'bytes':len(raw),'matched_author_source_pin':key in expected}
    return raw
def load(path): return json.loads(read(path))
def body(path): return json.loads(load(path)['result']['content'][0]['text'])
def keys(x):
    if isinstance(x,dict):
        yield from x
        for value in x.values():yield from keys(value)
    elif isinstance(x,list):
        for value in x:yield from keys(value)

m2=load(N/'M2_TRACE_REVIEW.json'); m4=load(N/'M4_TRACE_REVIEW.json'); fr=load(N/'FRAMED_TX_REVIEW.json')
root=Path(m2['source_inventory']['root'])
for row in m2['source_inventory']['pins']:expected[str((root/row['path']).resolve())]=row['sha256']
for row in m4['input_files']:expected[str(Path(row['path']).resolve())]=row['sha256']

# All M2 business rows from actual result files, not review classifications.
raw_business=[]; measurement_rows=0; measurement_hosts=0
for path in sorted((root/'measurement').rglob('RESULTS.json')):
    result=load(path); rows=result.get('rows',[])
    measurement_hosts+=1; measurement_rows+=len(rows);raw_business.extend(row['body'] for row in rows)
check('measurement host and row denominators',measurement_hosts==39 and measurement_rows==321)
cached_sequences=[]; mutations=[]
for entry in ['entry_01','entry_02']:
    base=root/'correctness'/entry; result=load(base/'RESULTS.json'); records=result['records']
    check(entry+' first five sequence',[r['label'] for r in records[:5]]==['directory_cold','directory_warm','selected_after_directory','delta_after_directory','directory_after_full'])
    packets=[]
    for record in records:
        label=record['label']; req=load(base/(label+'.REQUEST.json')); packet=body(base/(label+'.RESPONSE.json'))
        check(entry+' raw response equals results '+label,packet==record['body'])
        packets.append(packet);raw_business.append(packet)
        if label.startswith('changed_'):
            oracle=load(base/(label+'.ORACLE.json'))
            missing={'resource_stamp','_resource_stamp','resource_pose'}.isdisjoint(set(keys(packet))|set(keys(oracle)))
            check(entry+' changed directory missing prior private snapshot '+label,missing)
            check(entry+' changed request '+label,req['params']['arguments']['query']['mode']=='directory' and packet['schema']=='human-eye-directory-v1')
            mutations.append({'case':entry,'label':label,'cache_hit':packet['cache_hit'],'compatibility':'unknown_prior_stamp_pose_not_recorded'})
    check(entry+' before-resource cold cache miss',packets[0]['cache_hit'] is False)
    check(entry+' cached after resource',packets[1]['cache_hit'] is True and packets[4]['cache_hit'] is True and packets[0]['capture_state']==packets[1]['capture_state']==packets[4]['capture_state'])
    cached_sequences.append({'case':entry,'sequence':[r['label'] for r in records[:5]],'last_cache_hit':packets[4]['cache_hit']})

typed=root/'correctness/typed_01'; requests=load(typed/'REQUESTS.json')
check('typed original request order',[r['command'] for r in requests]==['capture_directory','capture_directory','capture_task','capture_directory','capture','shutdown'])
check('typed actual cached bytes',read(typed/'directory_hot.json')==read(typed/'directory_after_selected.json'))
check('typed task-after cache hit',requests[3]['response']['cache_hit'] is True)
raw_business.extend(r['response'] for r in requests if r['command']!='shutdown')
cached_sequences.append({'case':'typed_01','sequence':[r['command'] for r in requests],'last_cache_hit':requests[3]['response']['cache_hit']})
dirs=[p for p in raw_business if p.get('schema')=='human-eye-directory-v1']
counts={'measurement_hosts':measurement_hosts,'measurement_rows':measurement_rows,'M2_hosts':measurement_hosts+3,'business_reads':len(raw_business),'typed_shutdown':1,'product_directories':len(dirs),'directory_hit':sum(p['cache_hit'] is True for p in dirs),'directory_miss':sum(p['cache_hit'] is False for p in dirs),'mutated_directories':len(mutations)}
check('raw M2 total units',counts=={'measurement_hosts':39,'measurement_rows':321,'M2_hosts':42,'business_reads':368,'typed_shutdown':1,'product_directories':139,'directory_hit':98,'directory_miss':41,'mutated_directories':26})
source=read(root/'correctness/run_entry.py').decode('utf8')
check('mutations explicitly scripted','control(port, **parameters)' in source and "directory('changed_' + label)" in source)

# Actual M4 resource and first directory, plus the original purpose of the call.
t=m4['technical_hit']; run=Path(t['run']); trajectory=[]
for p in sorted((run/'stdio').glob('rpc_*/TX.bin')):
    q=json.loads(read(p));trajectory.append((q['id'],q['method']))
check('M4 actual tail sequence',[x[0] for x in trajectory[-4:]]==['nonplanar_source','bad_active_query','ping_after_bad_request','old_readonly_regression'])
check('M4 actual compatibility call is last',len(trajectory)==8)
protocol=load(t['origin_evidence']['protocol']);controller=read(t['origin_evidence']['controller']).decode('utf8')
check('compatibility predeclared','old_readonly_regression' in json.dumps(protocol))
check('compatibility only shape success assertion',"assert old['result'].get('isError') is False and all(block['type'] == 'text' for block in old['result']['content'])" in controller)
last_use=[(i+1,l) for i,l in enumerate(controller.splitlines()) if "old[" in l or 'old =' in l]
check('no later directory result use in runner',len(last_use)==2)
observed=body(run/'stdio/rpc_05/RESPONSE.json');directory=body(run/'stdio/rpc_08/RESPONSE.json')
check('original nonplanar unknown retained',observed['status']=='unknown' and observed['observation_status']=='no_supported_regions')
check('directory raw schema and miss',directory['schema']=='human-eye-directory-v1' and directory['result_kind']=='scene_directory' and directory['cache_hit'] is False)
check('same observed generation',all(observed['binding']['capture_state'][k]==directory['capture_state'][k] for k in ('instance_id','epoch','revision')))
check('same document identity',observed['binding']['document_epoch']==directory['binding']['host_identity']['document_epoch'])
def qa(index):
    raw=load(run/f'qa/rpc_{index:03}/RX.bin')['result']['result']
    return json.loads(raw.split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
capture=qa(5); qadir=qa(6); resource=capture['resources'][0]
check('one captured resource size/version',len(capture['resources'])==1 and resource['revision']==29 and len(resource['vertices_local'])==4 and len(resource['faces'])==2)
check('directory public and host agree',all(directory[k]==qadir[k] for k in ('capture_state','objects','cache_hit','directory_sha256')))
scripts=[read(run/f'qa/rpc_{i:03}/SCRIPT.py').decode('utf8') for i in [5,6]]
check('same original resident module/tag/reference',all(all(value in s for value in [t['direct']['resident_module'],t['direct']['resident_tag'],t['direct']['host_reference']]) for s in scripts))

# Recover exactly the 14 originally failed one-document parses as JSONL.
failures={x['path'] for row in m4['raw_request_inventory'] for x in row['decode_failures']}
check('exact supplemental files',{r['path'] for r in fr['records']}==failures and len(failures)==14)
messages=0;calls=0;directory_calls=[];capture_mentions=[];framed=[]
for record in fr['records']:
    raw=read(record['path']);check('framed original hash '+record['path'],hashlib.sha256(raw).hexdigest()==record['sha256'])
    rows=[]
    for number,line in enumerate(raw.splitlines(),1):
        if not line.strip():continue
        value=json.loads(line);messages+=1;calls+=value.get('method')=='tools/call';rows.append(value)
        params=value.get('params') or {};args=params.get('arguments') or {};query=args.get('query') or {}
        if query.get('mode')=='directory':directory_calls.append([record['path'],number])
        if b'capture_directory' in line:capture_mentions.append([record['path'],number])
    check('framed message ids retained '+record['path'],[x.get('id') for x in rows]==[x['id'] for x in record['messages']])
    framed.append({'path':record['path'],'messages':len(rows),'tools_call':sum(x.get('method')=='tools/call' for x in rows)})
check('framed exact message units',messages==79 and calls==37 and not directory_calls and not capture_mentions)

out={'passed':all(x['passed'] for x in checks),'checks':checks,'assertions':len(checks),'inputs':inputs,'raw_M2_denominators':counts,'cached_sequences':cached_sequences,'mutations':mutations,'M4_trajectory':trajectory,'M4_result_use_lines':last_use,'framed_files':framed,'framed_message_count':messages,'framed_tools_call_count':calls,'conclusion':'not_actionable_on_this_bounded_natural_task_evidence','technical_example_count':1,'natural_demand_frequency':'unknown','AL':{'context_handle':'5b6db88db9e241e18c182d58b5074d3d','old_assignment':'abcff986-3a32-4470-835c-7e2ae81f715c','assignment_current':False,'old_task':'95de6bf0-582e-412b-888b-c8e5ac70796b','current_explicit_parent_delegation':'f2ac3511-ed05-469e-9a8b-710340bd4bed','binding_refreshed':False},'new_product_model_Blender_raster_calls':0,'limitations':['Only bounded saved histories, no proof that all natural directory demand is absent.','Private resource stamp and at-directory mesh identity not directly logged.','No new timing, memory or end-to-end benefit measurement.','47 M4 namespaces and overlapping file inventories are not independent tasks/assets.']}
with (OUT/'RESULT_R1.json').open('x',encoding='utf8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':out['passed'],'assertions':len(checks),'failed':[x for x in checks if not x['passed']],'M2':counts,'framed_files':len(framed),'framed_messages':messages,'tools_call':calls},ensure_ascii=False))

