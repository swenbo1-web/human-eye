"""Independent post-seal binding review. Reads frozen originals only."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import subprocess
import zipfile

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = REPO/'verification/m4_surface_scan_consumption_001'
OUT = Path(__file__).resolve().parent
ROOT = Path('D:/hefe')
DELIVERY = 'ab69a99e0ac4c0e925688b10859cdf26da88b83e'
OLD = 'e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3'
PREP = 'bedcc827ec548e3afab816c0986db0c99eb42bb8'
PRODUCT = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'
SOURCE = 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'
checks=[]
inputs={}
old_manifest={}


def sha(raw): return hashlib.sha256(raw).hexdigest()
def gitblob(raw): return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def ck(name, condition):
    checks.append({'name':name,'passed':bool(condition)})
    if not condition:
        path=OUT/('FAILED_'+str(len(list(OUT.glob('FAILED_*.json')))+1)+'.json')
        path.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
        raise AssertionError(name)


def raw(path):
    data=path.read_bytes()
    k=str(path)
    if k not in inputs:
        inputs[k]={'bytes':len(data),'sha256':sha(data)}
        try: rel=path.relative_to(REPO).as_posix()
        except ValueError: rel=''
        if rel in old_manifest:
            row=old_manifest[rel]
            ck('old-bound '+rel,len(data)==row['bytes'] and sha(data)==row['sha256'])
    return data


def j(path): return json.loads(raw(path))
def git_tree(commit):
    data=subprocess.check_output(['git','ls-tree','-rz',commit],cwd=REPO)
    return {entry.split(b'\t',1)[1].decode():entry.split(b'\t',1)[0].split()[2].decode()
            for entry in data.split(b'\0') if entry}


def strip_rpc(value, request=False):
    result={k:v for k,v in value.items() if k not in ('id','jsonrpc','_meta')}
    if request and isinstance(result.get('params'),dict):
        result['params']={k:v for k,v in result['params'].items() if k!='_meta'}
    return result


def main():
    oldraw=raw(B/'DELIVERY_MANIFEST.json')
    ck('old manifest exact anchor',sha(oldraw)=='1ead579f888711876cb6295d86c3134285bcf578e278247c8ea5a8affc66ce2d')
    ck('old manifest Git',oldraw==subprocess.check_output(['git','show',OLD+':verification/m4_surface_scan_consumption_001/DELIVERY_MANIFEST.json'],cwd=REPO))
    old_manifest.update({v['path']:v for v in json.loads(oldraw)['files']})
    prior=ROOT/'verification/fixes/20261112_m4_surface_scan_consumer_quality_review/integrity/RESULTS.json'
    ck('reuse root prior integrity',raw(prior)==subprocess.check_output(['git','show','91cce49cd83c5dd00bac270b2ae128a2ede5b3ba:'+prior.relative_to(ROOT).as_posix()],cwd=ROOT))
    ck('prior integrity pass',j(prior)['passed'] is True)
    changed=set(subprocess.check_output(['git','diff','--name-only',OLD,DELIVERY],cwd=REPO,text=True).splitlines())
    ck('old committed content unchanged',not changed.intersection(old_manifest))
    trees={c:git_tree(c) for c in (DELIVERY,PREP,PRODUCT)}
    cm=j(B/'cost/DELIVERY_MANIFEST.json')
    ck('new manifest sha',sha(raw(B/'cost/DELIVERY_MANIFEST.json'))=='af1e66c8fc5925072375cf1f2742d9a61923c4b5d751191a8d58bea965ee2263')
    ck('new manifest Git',gitblob(raw(B/'cost/DELIVERY_MANIFEST.json'))==trees[DELIVERY][(B/'cost/DELIVERY_MANIFEST.json').relative_to(REPO).as_posix()])
    ck('new 24 files',len(cm['files'])==24)
    for row in cm['files']:
        p=B/'cost'/row['path'];data=raw(p)
        ck('new bytes '+row['path'],len(data)==row['bytes'] and sha(data)==row['sha256'])
        ck('new Git '+row['path'],gitblob(data)==trees[DELIVERY][p.relative_to(REPO).as_posix()])
    sealpath=ROOT/'verification/fixes/20261112_m4_surface_scan_consumer_quality_review/QUALITY_SEAL.json'
    seal=j(sealpath)
    ck('seal anchor',sha(raw(sealpath))=='1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f')
    ck('cost carries seal',raw(B/'cost/inputs/QUALITY_SEAL.json')==raw(sealpath))
    smap={v['anonymous_id']:v for v in seal['answers']}
    public=B/'runtime/handoff_01/public';private=B/'runtime/handoff_01/private'
    plan=j(B/'PLAN.json'); mapping=j(B/'private/ANON_MAP.json');run=j(B/'RUN_RESULT.json');prov=j(private/'PROVENANCE.json')
    ck('plan GO freeze',sha(raw(B/'PLAN.json'))==j(B/'GO.json')['plan_sha256']==j(B/'FREEZE.json')['plan_sha256'])
    ck('map frozen',sha(raw(B/'private/ANON_MAP.json'))==plan['private_anonymous_map_sha256'])
    ck('map copied',mapping==prov['fixed_anonymous_map']==j(private/'control/private/ANON_MAP.json'))
    ck('IDs bijection',{x['anonymous_id'] for x in mapping['rows']}==set(smap))
    expected_order=['N1','P1','P2','N2','N3','P3']
    ck('actual sequence',[v['cell'] for v in run['records']]==[v['cell'] for v in plan['sequence']]==expected_order)
    ck('six no replacements',run['started_cells']==6 and run['no_replacements'] is True and run['stop'] is None)
    for rel in ['PLAN.json','GO.json','FREEZE.json','private/ANON_MAP.json','runtime/driver.py','runtime/actor.py','runtime/consumer_transport.py']:
        ck('prepared '+rel,gitblob(raw(B/rel))==trees[PREP][(B/rel).relative_to(REPO).as_posix()])
    source=j(B/'preflight/SOURCE_BINDING.json');ready=j(B/'installations/P_READY.json')
    rows=source['source_manifest'];ck('138 fixed sources',len(rows)==138)
    for row in rows:
        p=REPO/row['path'];data=raw(p)
        ck('source '+row['path'],sha(data)==row['sha256'] and gitblob(data)==trees[PRODUCT][row['path']] and raw(Path(ready['install_root'])/row['path'])==data)
    aggregate={'base_version':'9.7.2','implementation_revision':'v26-surface-scan-pair-cache-20261112','files':rows}
    ck('aggregate',sha(json.dumps(aggregate,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())==SOURCE)
    ck('launcher',sha(raw(Path(ready['entry'])))==ready['launcher_sha256'])
    snap=j(B/'scoring/ACTUAL_SNAPSHOT.json')
    baseline={'unit_scale_m':snap['unit_scale_m'],'objects':[{k:o[k] for k in ['name','vertices_local','matrix_world','faces']} for o in snap['objects']]}
    common_native=j(B/'schemas/COMMON_NATIVE.json')
    extra_tools=j(B/'schemas/P_PUBLIC_TOOLS.json')
    frozen_settings=j(B/'preflight/CONSUMER_CONFIGURATION.json')['settings']
    cells=[];archive_members=0;business=0
    for maprow in mapping['rows']:
        cell=maprow['cell']; aid=maprow['anonymous_id'];f=B/'cells'/cell
        consumer=j(f/'CONSUMER.json');rec=next(r for r in run['records'] if r['cell']==cell)
        ck(cell+' slot',all(maprow[k]==rec[k]==consumer[k] for k in ['cell','group','round','slot','task']))
        ck(cell+' consumer stored',consumer==rec['consumer'])
        answer=raw(public/aid/'answer.txt')
        ck(cell+' all final bytes',answer==raw(f/'PUBLIC_FINAL.txt')==raw(f/'final.txt')==consumer['final'].encode('utf8'))
        ck(cell+' quality seal final',sha(answer)==smap[aid]['answer_sha256'] and smap[aid]['status']=='complete_correct')
        # The sealed manifest and ZIP, rather than another full Git walk, bind raw archive members.
        archive=private/'raw'/(aid+'.zip')
        raw(archive)
        with zipfile.ZipFile(archive) as z:
            expected={p.relative_to(f).as_posix() for p in f.rglob('*') if p.is_file()}
            ck(cell+' ZIP set',len(z.namelist())==len(expected) and set(z.namelist())==expected)
            for name in z.namelist():
                rr=(f/name).relative_to(REPO).as_posix();data=z.read(name);row=old_manifest[rr]
                ck(cell+' ZIP member '+name,sha(data)==row['sha256'] and len(data)==row['bytes']);archive_members+=1
        eventraw=raw(f/'events.jsonl');lines=eventraw.splitlines();events=[json.loads(x) for x in lines]
        start=[e['event']['thread_id'] for e in events if e['event']['type']=='thread.started']
        ck(cell+' one fresh thread',start==[consumer['thread_id']])
        msgs=[{'perf_ns':e['perf_ns'],'id':e['event']['item']['id'],'text':e['event']['item']['text']} for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
        ck(cell+' all public text',msgs==consumer['all_public_messages'] and msgs[-1]['text'].encode()==answer)
        te=[e for e in events if e['event'].get('item',{}).get('type')=='mcp_tool_call']
        done=[e for e in te if e['event']['type']=='item.completed']
        ck(cell+' completed consumed records',[{'perf_ns':e['perf_ns'],**e['event']} for e in done]==consumer['tool_calls'])
        evidence=j(public/aid/'tool_evidence.json')
        projection=[]
        for line,e in zip(lines,events):
            item=e['event'].get('item',{})
            if item.get('type')=='mcp_tool_call' and e['event']['type'] in ('item.started','item.completed'):
                projection.append({'order':len(projection)+1,'phase':e['event']['type'],'event':{k:item[k] for k in ['type','tool','server','arguments','result','error','status','command'] if k in item},'source_sha256':sha(eventraw),'source_line_sha256':sha(line)})
        ck(cell+' public exact event projection',projection==evidence['public_tool_events'])
        attempts=sorted((f/'owner').glob('tool_*'),key=lambda p:int(p.name.split('_')[1]))
        ck(cell+' attempts denominator',len(attempts)==len(done)==len(evidence['owner_attempts']))
        bridge,=list((f/'attachments').glob('bridge_*'))
        packets=[(j(p),j(p.with_name('RX.bin'))) for p in sorted(bridge.glob('*/TX.bin')) if j(p).get('method')=='tools/call']
        list_packets=[j(p.with_name('RX.bin')) for p in sorted(bridge.glob('*/TX.bin')) if j(p).get('method')=='tools/list']
        ck(cell+' actual tool declarations',len(list_packets)==1 and list_packets[0]['result']['tools']==[common_native]+(extra_tools if maprow['group']=='P' else []))
        ck(cell+' actual transport denominator',len(packets)==len(attempts))
        for attempt,event,pub,packet in zip(attempts,done,evidence['owner_attempts'],packets):
            request=j(attempt/'REQUEST.json');response=j(next(p for p in (attempt/'RESPONSE.json',attempt/'ERROR_RESPONSE.json') if p.exists()));item=event['event']['item']
            ck(cell+' raw transport '+attempt.name,packet==(request,response))
            ck(cell+' request projection '+attempt.name,strip_rpc(request,True)==pub['request'] and item['arguments']==request['params']['arguments'] and item['tool']==request['params']['name'])
            ck(cell+' response projection '+attempt.name,len(pub['responses'])==1 and strip_rpc(response)==pub['responses'][0]['value'])
            result=response['result']
            ck(cell+' CLI payload '+attempt.name,item['result']=={'content':result['content'],'structured_content':result.get('structuredContent')} and (item['status']=='failed')==bool(result.get('isError')))
            business+=1
        cfg=j(f/'ACTOR_CONFIG.json');owner=j(f/'owner/IDENTITY.json');native=j(f/'owner/native/SESSION.json');close=j(f/'owner/CLOSE.json');finish=j(f/'OWNER_FINISH.json');launch=j(f/'ACTOR_LAUNCH.json')
        sc=j(public/aid/'source_consistency.json')
        for rel,hashvalue in sc['source_records_sha256'].items():
            ck(cell+' source projection hash '+rel,sha(raw(f/rel))==hashvalue)
        ck(cell+' original initial/final hashes',sc['INITIAL_original_file_sha256']==sha(raw(f/'owner/INITIAL.json')) and sc['FINAL_original_file_sha256']==sha(raw(f/'owner/FINAL.json')))
        ck(cell+' asset files',sha(raw(Path(native['asset_copy'])))==sha(raw(B/'input/scene.blend'))==cfg['asset_sha256']==owner['asset_sha256']==plan['inputs']['scene_sha256'])
        ck(cell+' owned',owner['actor_parent_pid']==launch['pid']==finish['actor_pid'] and close['worker_closed']['pid']==native['pid'])
        for label in ['INITIAL','FINAL']:
            ss=j(f/'owner'/(label+'.json'));receipt=j(f/'owner'/(label+'.json.receipt.json'))
            ck(cell+' snapshot '+label,ss==baseline==json.loads(receipt['response']['result']['result']))
        ck(cell+' consumer closure',consumer['process_reaped'] and consumer['exit_code']==0 and finish['confirmed'] and finish['exit_code']==0)
        ck(cell+' native closure',close['native_close']['process_reaped'] and close['native_close']['exit_code']==0 and close['geometry_unchanged'] and close['asset_unchanged'])
        ck(cell+' thin EXIT unknown',not (bridge/'EXIT.json').exists() and consumer['bridge_cleanup']['confirmed'] is None and consumer['bridge_cleanup']['receipt_status']=='unknown' and consumer['bridge_cleanup']['missing_exit_count']==1)
        ck(cell+' common prompt',consumer['input_sha256']==sha(raw(B/'input/PROMPT.txt'))==plan['inputs']['prompt_sha256'])
        argv=consumer['argv'];settings=[argv[i+1] for i,v in enumerate(argv[:-1]) if v=='-c']
        for key,value in frozen_settings.items():
            if isinstance(value,(str,int,bool)):
                ck(cell+' requested setting '+key,key+'='+json.dumps(value,ensure_ascii=False,separators=(',',':')) in settings)
        ck(cell+' CLI isolation',all(flag in argv for flag in ['--ignore-user-config','--ignore-rules','--ephemeral','--strict-config']))
        ck(cell+' request/resolve distinction',consumer['model']=='gpt-6.1-sol' and consumer['requested_effort']=='medium' and consumer.get('resolved_model') is None and consumer['resolved_effort'] is None)
        ck(cell+' metadata only declaration',owner['private_geometry_warmup'] is False)
        cold=None;product_pid=None;product_created_utc=None
        if maprow['group']=='P':
            proof=j(f/'owner/PRODUCT_RUNTIME_PROOF.json');rpc=j(f/'owner/plugin/RPC.json');identity=owner['runtime_identity']
            startup=j(f/'owner/plugin/START.json')
            ck(cell+' actual entry',owner['product_serve_entry']==ready['entry'] and ready['entry'] in startup['command'])
            ck(cell+' startup pid',startup['launcher_pid']==proof['launcher_pid'])
            ck(cell+' product identity',identity['source_sha256']==SOURCE and identity['source_file_count']==138 and identity['distribution_version']==ready['version'] and identity['source_kind']=='installed_distribution')
            ck(cell+' owned product proof',proof['confirmed'] and proof['proved_ns']<consumer['started_ns'] and proof['runtime_pid']!=proof['launcher_pid'])
            ck(cell+' before-consumer RPC',[r['method'] for r in rpc['requests'] if r['started_ns']<consumer['started_ns']]==['initialize','notifications/initialized','tools/list','ping'])
            audit=[json.loads(v) for v in raw(f/'owner/audit.jsonl').splitlines()]
            work=next(x for x in audit if x['event']=='observe')['task_work'];cold=work['measurement_cache_before']
            ck(cell+' actual cold',cold['measurement_entries']==0 and work['cache_hits']==0 and work['kernel_calls']==work['pair_calls']==112)
            ck(cell+' product closure',close['plugin_close']['confirmed'] and close['product_runtime_exit']['confirmed'] and close['product_runtime_exit']['handle_closed'])
            product_pid=proof['runtime_pid']
            product_created_utc=(datetime(1601,1,1,tzinfo=timezone.utc)+timedelta(microseconds=proof['runtime_created_filetime']//10)).isoformat()
        else:
            ck(cell+' native only',owner['runtime_identity'] is None and cfg['entry'] is None and close['plugin_close'] is None and close['product_runtime_exit'] is None and not (f/'owner/plugin').exists())
        timing=j(f/'CELL_FINAL_TIMING.json')
        ck(cell+' closure before sampled end',consumer['cleanup_end_ns']<=close['ended_ns']<=timing['business_receipts_closed_ns'])
        cells.append({'cell':cell,'anonymous_id':aid,'thread_id':consumer['thread_id'],'owner_pid':owner['actor_pid'],'backend_pid':native['pid'],'product_pid':product_pid,'product_created_utc':product_created_utc,'measurement_cache_before':cold,'final_sha256':sha(answer),'attempts':len(attempts),'thin_EXIT':'unknown','provider_cached_input':consumer['usage'].get('cached_input_tokens'),'start_perf_ns':timing['cell_started_ns']})
    ck('unique threads/owners/backend',all(len({c[k] for c in cells})==6 for k in ['thread_id','owner_pid','backend_pid']))
    ck('3 product processes',len({c['product_pid'] for c in cells if c['product_pid'] is not None})==3)
    ck('26 attempts',business==26)
    prep_epoch=int(subprocess.check_output(['git','show','-s','--format=%ct',PREP],cwd=REPO,text=True).strip())
    prep_utc=datetime.fromtimestamp(prep_epoch,timezone.utc)
    formal=j(B/'FORMAL_PROCESS.json');formal_end=datetime.fromisoformat(formal['ended_utc'])
    inferred_start=formal_end-timedelta(microseconds=(formal['ended_ns']-formal['started_ns'])/1000)
    ck('inferred formal after prep',inferred_start>prep_utc)
    ck('P process creation after prep',all(datetime.fromisoformat(c['product_created_utc'])>prep_utc for c in cells if c['product_created_utc']))
    result={'passed':True,'checks':len(checks),'delivery':DELIVERY,'original_delivery':OLD,'quality_seal':sha(raw(sealpath)),'new_cost_files':25,'old_full_git_walk_reused_from_root':'91cce49cd83c5dd00bac270b2ae128a2ede5b3ba','old_content_unchanged_in_commits':True,'actual_read_inputs_bound':len(inputs),'raw_zip_members_verified':archive_members,'cells':cells,'business_attempts':business,'complete_initial_final_snapshots':12,'prepare_utc':prep_utc.isoformat(),'formal_start_utc_inferred':inferred_start.isoformat(),'formal_start_after_prepare_seconds_inferred':(inferred_start-prep_utc).total_seconds(),'chronology_scope':'P Windows process creation FILETIME anchors plus monotonic launch order; overall formal start inferred from single UTC end anchor assuming wall clock did not jump. No direct UTC start probe for all six.','new_Blender_model_API':0,'historical_process_memory_replayed':False}
    for name,value in [('RESULTS.json',result),('CHECKS.json',checks),('INPUTS.json',inputs)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='cells'},ensure_ascii=False))


if __name__=='__main__': main()
