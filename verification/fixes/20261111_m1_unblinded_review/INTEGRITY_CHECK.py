"""Independent static M1 evidence audit; never imports or runs project code."""
from pathlib import Path
from collections import Counter
import ast
import copy
import datetime
import hashlib
import json
import re
import subprocess
import zipfile

ROOT = Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = ROOT / 'verification/m1_task_entry_001_eval'
OUT = Path(__file__).resolve().parent
COMMIT = 'fa23496e1565e34ddacf4a0ce28b65e0a85c3ca8'
PREP = '81dcafec303bb867795f4474f5fe9bca2aa85c8e'
PRODUCT = '7411ac7aa9338f17355ffe5cdf4df113ce862aed'
CANONICAL = '0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
PUB = BASE / 'quality_handoff/handoff_01/public'
PRIVATE = BASE / 'quality_handoff/handoff_01/private'
findings = []
checks = Counter()


def rawsha(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return rawsha(path.read_bytes())


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def check(ok, category, detail):
    checks[category] += 1
    if not ok:
        findings.append({'category': category, 'detail': detail})
    return bool(ok)


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout


def tree(commit):
    result = {}
    for entry in git('ls-tree', '-r', '-z', commit).split(b'\0'):
        if entry:
            meta, name = entry.split(b'\t', 1)
            result[name.decode('utf8')] = meta.split()[2].decode('ascii')
    return result


def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def manifest_check(index, frozen_tree, category):
    total = 0
    for r in index['files']:
        path = ROOT / r['path']
        if not check(path.is_file(), category, {'missing':r['path']}):
            continue
        data = path.read_bytes()
        total += len(data)
        check(len(data)==r['bytes'] and rawsha(data)==r['sha256'], category, {'hash_or_size':r['path']})
        check(blob(data)==frozen_tree.get(r['path']), category, {'git_blob':r['path']})
    check(index['file_count']==len(index['files']), category, 'count')
    check(index['bytes']==total, category, 'bytes')
    return {'files':len(index['files']),'bytes':total}


def enc(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')


def projection_diff(a, b, source, notes, where, path='$'):
    """Compare every retained value, allowing only the observed administrative removals."""
    if isinstance(a,str) and isinstance(b,str):
        if a == b:
            return
        try:
            aa,bb=json.loads(a),json.loads(b)
        except (ValueError,TypeError):
            aa=bb=None
        if isinstance(aa,(dict,list)) and isinstance(bb,type(aa)):
            projection_diff(aa,bb,source,notes,where,path+'/decoded_json')
            return
        if path.endswith('/state_file') and b=='<path_'+rawsha(a.encode('utf8'))[:16]+'>':
            notes.append((source,path,'absolute_diagnostic_or_source_path_stable_alias',rawsha(enc(a))))
            return
        check(False,'projection_value_preserved',{'where':where,'pointer':path})
        return
    if isinstance(a,dict) and isinstance(b,dict):
        for k in b.keys()-a.keys():
            check(False,'projection_no_added_field',{'where':where,'pointer':path+'/'+k})
        for k,v in a.items():
            at=path+'/'+k.replace('~','~0').replace('/','~1')
            if k in b:
                projection_diff(v,b[k],source,notes,where,at)
                continue
            if at in ('$/id','$/jsonrpc','$/_meta'):
                rule='RPC_transport_envelope'
            elif at=='$/params/_meta':
                rule='RPC_administrative_meta_envelope'
            elif at in ('$/result/content/0/text/decoded_json/trace_id',
                        '$/result/content/0/text/decoded_json/runtime_identity',
                        '$/result/content/0/text/decoded_json/request_trace',
                        '$/worker_closed/closed_ns','$/worker_closed/original_deadline_ns','$/worker_closed/pid'):
                rule='administrative_envelope_field'
            else:
                check(False,'projection_no_fact_or_error_removed',{'where':where,'pointer':at})
                continue
            notes.append((source,at,rule,rawsha(enc(v))))
        return
    if isinstance(a,list) and isinstance(b,list):
        check(len(a)==len(b),'projection_list_length',{'where':where,'pointer':path})
        for i,(aa,bb) in enumerate(zip(a,b)):
            projection_diff(aa,bb,source,notes,where,path+'/'+str(i))
        return
    check(type(a) is type(b) and a==b,'projection_value_preserved',{'where':where,'pointer':path})


def normalize_geometry(value):
    return {'unit_scale_m':value['unit_scale_m'], 'objects':sorted([
        {'name':o['name'],'vertices_local':o['vertices_local'],
         'matrix_world':o['matrix_world'],'faces':o.get('faces',o.get('triangles'))}
        for o in value['objects']],key=lambda o:o['name'])}


def main():
    execution_tree=tree(COMMIT)
    prep_tree=tree(PREP)
    product_tree=tree(PRODUCT)
    prep_index=read(BASE/'ARTIFACT_INDEX.json')
    run_index=read(BASE/'formal_run/EXECUTION_ARTIFACT_INDEX.json')
    seal=read(BASE/'formal_run/EXECUTION_SEAL.json')
    freeze=read(BASE/'FREEZE.json')
    plan=read(BASE/'PLAN.json')
    ready=read(BASE/'installation/READY.json')
    prov=read(PRIVATE/'PROVENANCE.json')
    mapping=read(BASE/'private/ANON_MAP.json')['rows']
    public_index=read(PUB/'INDEX.json')
    pub_by_id={r['anonymous_id']:r for r in public_index['answers']}
    map_by_cell={r['cell']:r for r in mapping}
    prov_by_id={r['mapping']['anonymous_id']:r for r in prov['answers']}
    rr=read(BASE/'RUN_RESULT.json')
    seal_paths={
        'execution_index_sha256':BASE/'formal_run/EXECUTION_ARTIFACT_INDEX.json',
        'GO_sha256':BASE/'GO.json','PLAN_sha256':BASE/'PLAN.json',
        'public_INDEX_sha256':PUB/'INDEX.json',
        'public_provenance_manifest_sha256':PRIVATE/'PROVENANCE.json',
        'postprocessor_sha256':BASE/'quality_handoff/pack_quality.py'}
    for field,path in seal_paths.items():
        check(sha(path)==seal[field],'execution_seal_binding',field)
    check(sha(BASE/'ARTIFACT_INDEX.json')==freeze['artifact_index_sha256'],'preparation_seal_binding','index')
    manifest_results={
        'execution':manifest_check(run_index,execution_tree,'execution_members'),
        'preparation':manifest_check(prep_index,prep_tree,'preparation_members')}
    for rel in ['ARTIFACT_INDEX.json','FREEZE.json']:
        path=BASE/rel; name=path.relative_to(ROOT).as_posix()
        check(blob(path.read_bytes())==prep_tree[name]==execution_tree[name],'preparation_extra_seals',rel)
    for row in prep_index['files']:
        check(execution_tree.get(row['path'])==prep_tree.get(row['path']),'preparation_unchanged_in_execution_commit',row['path'])
    for rel in ['formal_run/EXECUTION_ARTIFACT_INDEX.json','formal_run/EXECUTION_SEAL.json']:
        path=BASE/rel
        check(blob(path.read_bytes())==execution_tree.get(path.relative_to(ROOT).as_posix()),'execution_outer_seals',rel)

    source=read(BASE/'SOURCE_REVIEW.json')
    check(len(source['files'])==137 and source['canonical']==CANONICAL,'product_source_identity','count/canonical')
    constants={}
    module=ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_text(encoding='utf8'))
    for node in module.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
                    constants[target.id]=ast.literal_eval(node.value)
    expected_names=set(constants['_ROOT_MODULES'])
    for pkg in ['human_eye_plugin','human_eye_module1_operators']:
        expected_names.update(pkg+'/'+p.name for p in (ROOT/pkg).glob('*.py'))
    check(expected_names=={x['path'] for x in source['files']},'product_source_identity','complete source domain')
    canonical=rawsha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':source['files']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check(canonical==CANONICAL,'product_source_identity','recomputed canonical')
    install=Path(ready['install_root'])
    wheel=next((BASE/'installation/bundle').glob('*.whl'))
    check(sha(wheel)==ready['wheel_sha256'],'wheel_binding','wheel bytes')
    with zipfile.ZipFile(wheel) as z:
        for r in source['files']:
            rel=r['path']; raw=(ROOT/rel).read_bytes()
            check(rawsha(raw)==r['sha256'] and blob(raw)==product_tree.get(rel)==execution_tree.get(rel),'product_source_bytes',rel)
            check((BASE/'installation/source_7411'/rel).read_bytes()==raw,'fixed_source_copy_bytes',rel)
            check((install/rel).read_bytes()==raw and z.read(rel)==raw,'wheel_install_source_bytes',rel)
    entry=Path(ready['entry']); binding=entry.parent/'RUNTIME_BINDING.json'
    check(sha(entry)==ready['launcher_sha256'],'installed_entry_binding','entry')
    check(sha(binding)==ready['binding_sha256'],'installed_entry_binding','binding')
    identity_receipt=read(BASE/'installation/receipt/INSTALLED_IDENTITY_STDOUT.json')
    check(identity_receipt['runtime_identity']['source_sha256']==CANONICAL and identity_receipt['runtime_identity']['source_files']==source['files'],'installed_identity_receipt','canonical/source manifest')

    go=read(BASE/'GO.json');gp=read(BASE/'GO_PROVENANCE.json');started=read(BASE/'STARTED.json');launch=read(BASE/'formal_run/LAUNCH.json')
    check((BASE/'GO.json').read_bytes()==Path(gp['original']).read_bytes(),'GO_exact_root_copy','bytes')
    check(sha(BASE/'GO.json')==gp['sha256']==seal['GO_sha256']==launch['root_GO_sha256'],'GO_exact_root_copy','hash')
    check(go['authorized'] is True and go['max_consumers']==27 and go['preparation_commit']==PREP and go['product_commit']==PRODUCT and go['canonical_source_sha256']==CANONICAL,'GO_scope','fixed authorization')
    check(go['plan_sha256']==started['plan_sha256']==launch['PLAN_sha256']==sha(BASE/'PLAN.json') and started['max_consumers']==27,'GO_scope','plan and denominator')
    driver=(BASE/'driver.py').read_text(encoding='utf8')
    check("(HERE/'STARTED.json').open('x')" in driver,'single_start_local_evidence','exclusive-create gate present in frozen driver')
    check(sha(BASE/'driver.py')==launch['driver_sha256']==freeze['driver_sha256'],'single_start_local_evidence','executed driver claimed and frozen byte binding')
    check(launch['started_ns']<=started['started_ns']<=rr['records'][0]['cell_started_ns'],'single_start_local_evidence','local launch-before-start-before-first-cell order')
    sequence=plan['sequence']
    keys=('cell','round','task','group')
    check([{k:r[k] for k in keys} for r in rr['records']]==sequence,'fixed_sequence','RUN_RESULT order')
    check([{k:r[k] for k in keys} for r in mapping]==sequence,'fixed_sequence','anonymous fixed mapping order')
    check(sorted(p.name for p in (BASE/'cells').iterdir() if p.is_dir())==sorted(r['cell'] for r in sequence),'fixed_sequence','exact cell directory set')
    check(len(sequence)==27 and len(map_by_cell)==27 and len(pub_by_id)==27 and len(prov_by_id)==27,'fixed_sequence','denominator and unique anonymous IDs')
    for rel,digest in plan['dispatch_input_sha256'].items():
        check(sha(BASE/rel)==digest,'frozen_dispatch_inputs',rel)
    for name,digest in prov['control_sha256'].items():
        check(sha(PRIVATE/'control'/name)==digest==sha(BASE/name),'private_control_copies',name)
    for name,digest in prov['public_files_sha256'].items():
        check(sha(PUB/name)==digest,'public_provenance_hashes',name)

    cell_results=[]
    threads=[]
    notes_actual=[]
    notes_declared=[]
    attempts_total=0
    error_total=0
    zip_members_total=0
    request_code_count=0
    public_events_count=0
    thin_unknown=0
    native_hashes=set()
    dependency_pythons=set()
    for slot,runrow in zip(sequence,rr['records']):
        cid=slot['cell']; folder=BASE/'cells'/cid; m=map_by_cell[cid];aid=m['anonymous_id'];pr=prov_by_id[aid]
        c=read(folder/'CONSUMER.json');idn=read(folder/'owner/IDENTITY.json');cfg=read(folder/'ACTOR_CONFIG.json')
        close=read(folder/'owner/CLOSE.json');finish=read(folder/'OWNER_FINISH.json');al=read(folder/'ACTOR_LAUNCH.json')
        worker=read(folder/'owner/native/SESSION.json');wc=read(folder/'owner/native/WORKER_CLOSED.json')
        snapshot=read(BASE/plan['tasks'][slot['task']]['snapshot'])
        for label,record in [('consumer',c),('mapping',m),('runrow',runrow)]:
            check(all(record[k]==slot[k] for k in keys),'cell_binding',{'cell':cid,'record':label})
        check(runrow['consumer']==c and runrow['finish']==finish,'cell_binding',{'cell':cid,'record':'RUN_RESULT nested originals'})
        check(pr['mapping']==m and pub_by_id[aid]['task_id']==slot['task'],'cell_binding',{'cell':cid,'record':'provenance/public'})
        prompt=(BASE/'SESSION_RULES.txt').read_bytes()+b'\n'+(BASE/plan['tasks'][slot['task']]['prompt']).read_bytes()
        check(rawsha(prompt)==c['input_sha256']==plan['tasks'][slot['task']]['model_input_sha256'],'consumer_inputs',cid)
        events_raw=(folder/'events.jsonl').read_bytes()
        lines=[line for line in events_raw.splitlines() if line]
        events=[json.loads(line)['event'] for line in lines]
        tids=[e['thread_id'] for e in events if e.get('type')=='thread.started']
        check(tids==[c['thread_id']],'consumer_thread',cid);threads.extend(tids)
        finals=[e['item'].get('text') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
        check(c['final'] in finals,'consumer_final_event',cid)
        raw_final=(folder/'PUBLIC_FINAL.txt').read_bytes()
        check(raw_final==c['final'].encode('utf8')==(PUB/aid/'answer.txt').read_bytes(),'raw_final_binding',cid)
        check(rawsha(raw_final)==pub_by_id[aid]['answer_original_sha256']==pub_by_id[aid]['source_provenance']['public_final_sha256'],'raw_final_binding',cid+' public hash')
        check(sha(folder/'CONSUMER.json')==pub_by_id[aid]['source_provenance']['consumer_record_sha256'],'raw_final_binding',cid+' consumer hash')
        with zipfile.ZipFile(PRIVATE/'raw'/f'{aid}.zip') as z:
            names=z.namelist();local={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
            check(len(names)==len(set(names)) and set(names)==set(pr['source_files_sha256'])==local,'raw_zip_member_set',cid)
            for name in names:
                data=z.read(name)
                check(data==(folder/name).read_bytes() and rawsha(data)==pr['source_files_sha256'][name],'raw_zip_bytes',{'cell':cid,'member':name})
            zip_members_total+=len(names)
        for name,digest in pr['files_sha256'].items():
            check(sha(PUB/aid/name)==digest,'public_provenance_hashes',aid+'/'+name)
        expected_asset=plan['tasks'][slot['task']]['asset_sha256']
        check(cfg['asset_sha256']==idn['asset_sha256']==worker['asset_sha256']==expected_asset==sha(Path(cfg['asset']))==sha(Path(worker['asset_copy'])),'asset_binding',cid)
        initial=read(folder/'owner/INITIAL.json');final=read(folder/'owner/FINAL.json')
        check(initial==final and normalize_geometry(initial)==normalize_geometry(snapshot),'initial_final_geometry',cid)
        check(close['geometry_unchanged'] and close['asset_unchanged'] and wc['initial_geometry_fingerprint']==wc['final_geometry_fingerprint'] and not wc['poisoned'],'initial_final_geometry',cid+' close fingerprint')
        native_hashes.add(idn['common_native_sha256']);dependency_pythons.add(idn['python'])
        check(idn['python']==cfg['dependency_python']==ready['dependency_python'],'entry_dependency',cid)
        check(idn['private_geometry_warmup'] is False,'entry_no_private_warmup',cid)
        if slot['group']=='N':
            check(idn['runtime_identity'] is None and idn['product_serve_entry'] is None and not (folder/'owner/plugin/START.json').exists() and close['plugin_close'] is None,'native_no_product_process',cid)
        else:
            rid=idn['runtime_identity'];ps=read(folder/'owner/plugin/START.json');pc=read(folder/'owner/plugin/CLOSE.json')
            check(rid['source_sha256']==CANONICAL and rid['source_file_count']==137 and rid['source_kind']=='installed_distribution' and rid['identity_check']['compatible'] is True,'runtime_source_record',cid)
            check(idn['product_serve_entry']==ready['entry'] and cfg['entry']==ready['entry'] and cfg['install_root']==ready['install_root'] and cfg['source_sha256']==CANONICAL,'runtime_source_record',cid+' paths')
            cmd=ps['command']
            check(cmd[:5]==[ready['dependency_python'],'-I','-B',ready['entry'],'serve'] and ('--spatial-task-only' in cmd)==(slot['group']=='S'),'actual_serve_entry',cid)
            check(pc==close['plugin_close'] and pc['launcher_pid']==ps['launcher_pid'] and pc['process_reaped'] and pc['exit_code']==0 and pc['confirmed'],'product_close',cid)
        check(close['confirmed'] and not close['errors'] and finish['confirmed'] and finish['exit_code']==0 and finish['actor_pid']==al['pid']==idn['actor_parent_pid'] and close['actor_pid']==idn['actor_pid'],'actor_close',cid)
        nc=close['native_close']
        check(nc['pid']==worker['pid']==wc['pid'] and nc['process_reaped'] and nc['exit_code']==0 and nc['source_file_unchanged'] and nc['protected_files_unchanged'] and nc['original_deadline_ns']==worker['deadline_ns']==wc['original_deadline_ns'],'worker_close',cid)
        check(c['process_reaped'] and c['exit_code']==0 and c['process_cleanup']['parent_reaped'] and c['process_cleanup']['parent_exit']==0 and c['process_cleanup']['pid']==c['consumer_pid'],'consumer_close',cid)
        bridges=c['bridge_cleanup']['instances']
        unknown=0
        for bridge in bridges:
            bd=Path(bridge['directory']);br=read(bd/'STARTED.json')
            check(br==bridge['started'],'thin_started_binding',cid)
            if not (bd/'EXIT.json').exists():
                unknown+=1
                check(bridge['exit'] is None and bridge['confirmed'] is None,'thin_missing_exit_kept_unknown',cid)
        thin_unknown+=unknown
        check(c['bridge_cleanup']['missing_exit_count']==unknown,'thin_missing_exit_kept_unknown',cid+' count')
        te=read(PUB/aid/'tool_evidence.json')
        tool_dirs=sorted((folder/'owner').glob('tool_*'),key=lambda p:int(p.name.split('_')[1]))
        check(len(te['owner_attempts'])==len(tool_dirs)==close['tool_attempts'],'tool_attempt_denominator',cid)
        notes=[]
        for a,td in zip(te['owner_attempts'],tool_dirs):
            attempts_total+=1
            req=read(td/'REQUEST.json');ars=read(td/'ATTEMPT.json')
            projection_diff(req,a['request'],sha(td/'REQUEST.json'),notes,str(td/'REQUEST.json'))
            check(req['params']['arguments']==a['request']['params']['arguments'],'original_arguments_preserved',{'cell':cid,'order':a['order']})
            request_code_count+=int('code' in req['params']['arguments'])
            check(a['is_error']==ars.get('is_error') and a['owner_exception']==ars.get('exception'),'attempt_error_preserved',{'cell':cid,'order':a['order']})
            error_total+=int(a['is_error'] is True)
            expected_responses=[n for n in ['RESPONSE.json','ERROR_RESPONSE.json'] if (td/n).exists()]
            check([r['kind'] for r in a['responses']]==expected_responses,'all_responses_preserved',{'cell':cid,'order':a['order']})
            for response in a['responses']:
                rp=td/response['kind']
                projection_diff(read(rp),response['value'],sha(rp),notes,str(rp))
            for sf in a['source_files']:
                check(sha(td/sf['kind'])==sf['original_sha256'],'tool_source_file_binding',{'cell':cid,'order':a['order'],'kind':sf['kind']})
        tools={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view','file_change','todo_list','collab_tool_call'}
        tool_events=[(line,e) for line,e in zip(lines,events) if e.get('type') in ('item.started','item.completed') and e.get('item',{}).get('type') in tools]
        check(len(tool_events)==len(te['public_tool_events']),'public_event_denominator',cid)
        for (line,e),pe in zip(tool_events,te['public_tool_events']):
            public_events_count+=1
            check(pe['phase']==e['type'] and pe['source_sha256']==rawsha(events_raw) and pe['source_line_sha256']==rawsha(line),'public_event_binding',{'cell':cid,'order':pe['order']})
            item={k:v for k,v in e['item'].items() if k in ('type','tool','server','arguments','result','error','status','command')}
            projection_diff(item,pe['event'],rawsha(events_raw),notes,str(folder/'events.jsonl'))
        sc=read(PUB/aid/'source_consistency.json')
        projection_diff({'worker_closed':close['worker_closed']},{'worker_closed':sc['CLOSE']['worker_closed']},sha(folder/'owner/CLOSE.json'),notes,str(folder/'owner/CLOSE.json'))
        for field in ['geometry_unchanged','asset_unchanged','errors']:
            check(sc['CLOSE'][field]==close[field],'source_consistency_projection',{'cell':cid,'field':field})
        for field in ['source_file_unchanged','protected_files_unchanged']:
            check(sc['CLOSE']['native_close'][field]==nc[field],'source_consistency_projection',{'cell':cid,'field':field})
        for name,digest in sc['source_records_sha256'].items():
            check(sha(folder/name)==digest,'source_consistency_projection',{'cell':cid,'source':name})
        declared=[(x['source_sha256'],x['pointer'],x['rule'],x['original_value_sha256']) for x in pr['administrative_projections']]
        check(Counter(notes)==Counter(declared),'projection_audit_note_exactness',{'cell':cid,'observed_count':len(notes),'declared_count':len(declared),'unmatched_observed':[list(x) for x in (Counter(notes)-Counter(declared)).keys()],'unmatched_declared':[list(x) for x in (Counter(declared)-Counter(notes)).keys()]})
        notes_actual.extend(notes);notes_declared.extend(declared)
        cell_results.append({'cell':cid,'anonymous_id':aid,'task':slot['task'],'group':slot['group'],'thread_id':c['thread_id'],'source_canonical':None if slot['group']=='N' else idn['runtime_identity']['source_sha256'],'source_count':0 if slot['group']=='N' else 137,'final_sha256':rawsha(raw_final),'private_zip_members':len(pr['source_files_sha256']),'attempts':len(tool_dirs),'recorded_tool_errors':sum(a['is_error'] is True for a in te['owner_attempts']),'actor_launcher_exit_recorded':True,'worker_reap_recorded':True,'consumer_reap_recorded':True,'product_reap_recorded':slot['group']!='N','thin_missing_EXIT_unknown':unknown})
    check(len(threads)==len(set(threads))==27,'unique_observed_threads','27 distinct thread.started markers')
    check(len(native_hashes)==1 and len(dependency_pythons)==1,'common_native_dependency','same helper digest and dependency interpreter across all cells')
    pid=read(BASE/'formal_run/private/PID_QUERY.json')
    check(pid['queried_count']==len(pid['rows'])==152 and pid['present_count']==sum(r['present'] for r in pid['rows'])==0,'historical_PID_query','recorded 152 absent; no new OS scan')
    check(seal['thin_EXIT_scope']=='Missing remains unknown; OS absence is not a graceful-exit receipt.','thin_missing_exit_kept_unknown','seal wording')
    report={
        'schema':'m1-independent-unblinded-integrity-review-v1','reviewer':'/root/latest_local_upgrade_audit',
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commit':COMMIT,'preparation_commit':PREP,'product_commit':PRODUCT,
        'status':'passed_with_stated_limits' if not findings else 'requires_review','findings':findings,'check_counts':dict(checks),
        'seal_bindings':{k:sha(v) for k,v in seal_paths.items()},'manifests':manifest_results,
        'summary':{'execution_members':len(run_index['files']),'old_preparation_members_including_index_freeze':len(prep_index['files'])+2,'product_sources':137,'fixed_slots':27,'unique_observed_consumer_threads':len(set(threads)),'raw_final_triple_bindings':27,'private_zip_members':zip_members_total,'owner_tool_attempts':attempts_total,'code_requests':request_code_count,'recorded_tool_errors':error_total,'public_tool_events':public_events_count,'administrative_projection_records':len(notes_actual),'runtime_product_sessions':18,'native_without_product_sessions':9,'missing_thin_EXIT_receipts_kept_unknown':thin_unknown,'historical_indexed_PIDs_absent':pid['queried_count']},
        'cells':cell_results,
        'single_start_evidence':{'root_GO_exact':True,'STARTED_exclusive_create_in_frozen_driver':True,'one_recorded_formal_sequence':True,'observed_distinct_threads':len(set(threads)),'scope':'One recorded fixed run with one thread.started per planned cell. Local records and exclusive creation support this; they do not prove absence of every unobserved provider request or external invocation.','provider_request_count':None},
        'runtime_identity_scope':'Static source/wheel/install bytes and captured runtime/START records agree. No product process was run by this review; manifest membership is not a claim that every module executed.',
        'closure_scope':'Actor launcher, consumer, native worker and product closure/reap are recorded at their owning boundaries. Actual actor OS exit and missing thin EXIT are not upgraded from PID absence. Historical PID query is corroborative only; no new process scan.',
        'asset_scope':'Input copies and original test assets hash to fixed tasks; full initial/final geometry records agree with frozen snapshots. Equality does not independently exclude every transient operation.',
        'projection_scope':'Every public owner request/response and public tool event compared to original records; original arguments/code exact. Only enumerated administrative removals or the stable state-file path alias are allowed, and each removal is bound to the provenance note/value hash. Facts, errors, unknowns, geometry budgets and IDs retained.',
        'not_performed':['No product/Blender/model execution','No cost or adoption recomputation','No provider-side request enumeration','No fresh process scan','No implementation-tree mutation'],
        'agent_learning':'session_context read returned own context 0e292d06286549aa8876d1180f7c4054 with historical current=false assignment and parent_read_only. No parent handle or task write borrowed.',
        'review_script_sha256':sha(Path(__file__))}
    dest=OUT/'INTEGRITY_REVIEW.json'
    if dest.exists():
        dest=OUT/('INTEGRITY_REVIEW_attempt_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'report':str(dest),'status':report['status'],'summary':report['summary'],'findings_count':len(findings),'first_findings':findings[:12]},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        path=OUT/('CHECKER_FAILURE_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
        path.write_text(json.dumps({'error_type':type(error).__name__,'message':str(error),'findings_so_far':findings,'checks_so_far':dict(checks)},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        raise
