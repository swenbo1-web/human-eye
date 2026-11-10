"""Bounded static audit; output deliberately excludes assignment and cost data."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import traceback
import zipfile

W=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=W/'verification/m4_observation_baseline_001'
O=Path(__file__).resolve().parent
HEAD='a5f9da9cdb66f95d8a4393f29362c18d5be366b4'
CANON='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
P=B/'quality_handoff/handoff_01/public'
V=B/'quality_handoff/handoff_01/private'
checks=[];errors=[];counts={}
def h(raw):return hashlib.sha256(raw).hexdigest()
def sha(p):return h(Path(p).read_bytes())
def j(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def enc(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def chk(name,yes):
    checks.append({'check':name,'status':'pass' if yes else 'fail'})
    if not yes:errors.append(name)
def git(*args):return subprocess.run(['git','-C',str(W),*args],check=True,capture_output=True).stdout
def stripped(v):return {k:copy.deepcopy(x) for k,x in v.items() if k not in ('id','jsonrpc','_meta')}
def stage(name,fn):
    try:fn()
    except Exception as e:
        # Do not emit private identifiers or values from an exception.
        errors.append(name+':checker_exception:'+type(e).__name__)
        checks.append({'check':name,'status':'unknown','exception_type':type(e).__name__,'script_line':traceback.extract_tb(e.__traceback__)[-1].lineno})

plan=j(B/'PLAN.json');prov=j(V/'PROVENANCE.json');public=j(P/'INDEX.json')
seal=j(B/'formal_run/EXECUTION_SEAL.json');ready=j(B/'quality_handoff/FORMAL_QUALITY_READY.json')

def indices():
    chk('fixed_HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
    entries={}
    for raw in git('ls-tree','-r','-z',HEAD).split(b'\0'):
        if raw:
            meta,path=raw.split(b'\t',1);entries[path.decode()]=meta.split()[2].decode()
    idx=j(B/'formal_run/EXECUTION_ARTIFACT_INDEX.json')
    bad=0
    for row in idx['files']:
        raw=(W/row['path']).read_bytes()
        bad+=not (len(raw)==row['bytes'] and h(raw)==row['sha256'])
    chk('execution_index_528_hash_size',len(idx['files'])==idx['file_count']==528 and bad==0)
    fixed=[r['path'] for r in idx['files']]+[(B/x).relative_to(W).as_posix() for x in ('formal_run/EXECUTION_ARTIFACT_INDEX.json','formal_run/EXECUTION_SEAL.json')]
    bad=0
    for rel in fixed:
        raw=(W/rel).read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest();bad+=blob!=entries.get(rel)
    chk('execution_530_git_blobs',len(fixed)==530 and bad==0)
    idxold=j(B/'ARTIFACT_INDEX.json');bad=0
    for r in idxold['files']:
        raw=(W/r['path']).read_bytes();bad+=h(raw)!=r['sha256'] or len(raw)!=r['bytes']
    chk('preparation_380_unchanged',len(idxold['files'])==380 and bad==0)
    pins=plan['dispatch_input_sha256'];bad=0
    for path,digest in pins.items():
        p=Path(path) if Path(path).is_absolute() else B/path
        bad+=sha(p)!=digest
    chk('dispatch_37_pins_unchanged',len(pins)==37 and bad==0)
    chk('seal_bound',seal['source_sha256']==CANON and seal['source_count']==137 and seal['execution_artifact_index_sha256']==sha(B/'formal_run/EXECUTION_ARTIFACT_INDEX.json') and seal['public_INDEX_sha256']==sha(P/'INDEX.json') and seal['private_PROVENANCE_sha256']==sha(V/'PROVENANCE.json') and seal['quality_ready_sha256']==sha(B/'quality_handoff/FORMAL_QUALITY_READY.json'))
    files={p.relative_to(P).as_posix():sha(p) for p in P.rglob('*') if p.is_file()}
    chk('public_28_exact_files',len(files)==28 and files==prov['public_files_sha256'])
    counts.update(execution_index_members=528,execution_git_members=530,unchanged_preparation_members=380,dispatch_pins=37,public_files=28)

def handoff():
    pb={r['anonymous_id']:r for r in public['answers']};zcount=0;sourcecount=0;attemptcount=0;eventcount=0;removalcount=0
    validfinal=0;zipbad=0;projectionbad=0;recordbad=0;issues=0
    TOOL_TYPES={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view','file_change','todo_list','collab_tool_call'}
    for row in prov['answers']:
        amap=row['mapping'];aid=amap['anonymous_id'];cell=B/'cells'/amap['cell'];publicrow=pb[aid];answerdir=P/aid
        zipfile_path=V/'raw'/(aid+'.zip')
        with zipfile.ZipFile(zipfile_path) as z:
            names=z.namelist();sources={n:z.read(n) for n in names}
        zcount+=1;sourcecount+=len(sources)
        expected={p.relative_to(cell).as_posix():sha(p) for p in cell.rglob('*') if p.is_file()}
        zipbad+=len(names)!=len(set(names)) or {n:h(v) for n,v in sources.items()}!=expected or expected!=row['source_files_sha256']
        def sj(path):return json.loads(sources[path])
        consumer=sj('CONSUMER.json')
        final=sources['PUBLIC_FINAL.txt']
        validfinal+=final==consumer['final'].encode() and final==(answerdir/'answer.txt').read_bytes() and publicrow['answer_original_sha256']==h(final) and publicrow['answer_state']=='present'
        recordbad+=sources['final.txt']!=(answerdir/'cli_output_unconfirmed.txt').read_bytes()
        recordbad+=any(sha(answerdir/name)!=digest for name,digest in row['files_sha256'].items())
        # Exact payload comparison, only explicitly known outer RPC metadata removed.
        evidence=j(answerdir/'tool_evidence.json');dirs=sorted({Path(n).parts[1] for n in sources if len(Path(n).parts)>=3 and Path(n).parts[0]=='owner' and Path(n).parts[1].startswith('tool_')},key=lambda v:int(v.split('_')[1]))
        recordbad+=len(dirs)!=len(evidence['owner_attempts']);attemptcount+=len(dirs)
        for td,a in zip(dirs,evidence['owner_attempts'],strict=True):
            req=sj('owner/'+td+'/REQUEST.json');expectedreq=stripped(req)
            if isinstance(expectedreq.get('params'),dict):expectedreq['params'].pop('_meta',None)
            projectionbad+=a['request']!=expectedreq
            actualresponses=[]
            for name in ('RESPONSE.json','ERROR_RESPONSE.json'):
                rel='owner/'+td+'/'+name
                if rel in sources:actualresponses.append({'kind':name,'value':stripped(sj(rel))})
            projectionbad+=a['responses']!=actualresponses
            att=sj('owner/'+td+'/ATTEMPT.json');exception=copy.deepcopy(att.get('exception'))
            if isinstance(exception,dict):exception.pop('traceback',None)
            projectionbad+=a['is_error']!=att.get('is_error') or a['owner_exception']!=exception
            projectionbad+=any(x['original_sha256']!=h(sources['owner/'+td+'/'+x['kind']]) for x in a['source_files'])
        expectevents=[]
        for line in sources['events.jsonl'].splitlines():
            if not line:continue
            event=json.loads(line).get('event',{});item=event.get('item',{})
            if item.get('type') in TOOL_TYPES and event.get('type') in ('item.started','item.completed'):
                ev={k:copy.deepcopy(item[k]) for k in ('type','tool','server','arguments','result','error','status','command') if k in item}
                expectevents.append(dict(order=len(expectevents)+1,phase=event['type'],event=ev,source_sha256=h(sources['events.jsonl']),source_line_sha256=h(line)))
        projectionbad+=evidence['public_tool_events']!=expectevents;eventcount+=len(expectevents)
        blobs={h(raw):raw for raw in sources.values()}
        for removal in row['administrative_projections']:
            raw=blobs[removal['source_sha256']];value=json.loads(raw);pointer=removal['pointer']
            allowed=pointer in ('$/id','$/jsonrpc','$/_meta','$/params/_meta','$/exception/traceback','$/worker_closed/pid','$/worker_closed/closed_ns','$/worker_closed/original_deadline_ns')
            for token in pointer[2:].split('/'):value=value[token.replace('~1','/').replace('~0','~')]
            projectionbad+=not allowed or removal['original_value_sha256']!=h(enc(value));removalcount+=1
        # Check source summary producer fields directly, including unknown image delivery.
        consistency=j(answerdir/'source_consistency.json');cfg=sj('ACTOR_CONFIG.json');iid=sj('owner/IDENTITY.json');close=sj('owner/CLOSE.json')
        recordbad+=consistency['ACTOR_CONFIG']['asset_sha256']!=cfg['asset_sha256'] or consistency['owner_IDENTITY']['asset_sha256']!=iid['asset_sha256']
        recordbad+=any(consistency['source_records_sha256'][name]!=h(sources[name]) for name in consistency['source_records_sha256'])
        recordbad+=consistency['INITIAL_original_file_sha256']!=h(sources['owner/INITIAL.json']) or consistency['FINAL_original_file_sha256']!=h(sources['owner/FINAL.json'])
        recordbad+=any(consistency['CLOSE'][k]!=close[k] for k in ('geometry_unchanged','asset_unchanged','errors'))
        recordbad+=any(consistency['CLOSE']['native_close'][k]!=close['native_close'][k] for k in ('source_file_unchanged','protected_files_unchanged'))
        worker={k:v for k,v in close['worker_closed'].items() if k not in ('pid','closed_ns','original_deadline_ns')}
        recordbad+=consistency['CLOSE']['worker_closed']!=worker
        img=consistency['CONSUMER_IMAGE'];recordbad+=img['initial_image_sha256']!=consumer['initial_image']['sha256'] or img['initial_image_unchanged']!=consumer['initial_image_unchanged']
        recordbad+=any(img['image_delivery'][k]!=consumer['image_delivery'][k] for k in img['image_delivery'])
        issues+=len(row['issues'])
    chk('six_private_zip_all_475_members_match_cell_and_provenance',zcount==6 and sourcecount==475 and zipbad==0)
    chk('six_finals_original_public_consumer_exact',validfinal==6)
    chk('tool_payloads_events_and_administrative_removals_exact',projectionbad==0)
    chk('public_source_records_and_unconfirmed_cli_preserved',recordbad==0)
    chk('packager_issues_empty',issues==0)
    counts.update(private_archives=zcount,private_archive_members=sourcecount,final_bindings=validfinal,owner_attempts=attemptcount,public_tool_events=eventcount,administrative_projection_entries=removalcount)

def runtime():
    records=j(B/'RUN_RESULT.json');seq=plan['sequence'];mapping=prov['fixed_anonymous_map'];threads=set();consumerpids=set();thinmissing=0;geometry=0;identity=0;image=0;deadline=0;backends=0;consumers=0;knownpids=set()
    chk('six_fixed_slots_no_substitution',len(seq)==len(mapping['rows'])==len(records['records'])==6 and all(all(a[k]==b[k]==c[k] for k in ('cell','task','round','group')) for a,b,c in zip(seq,mapping['rows'],records['records'],strict=True)) and records['no_replacements'] and records['all_planned_dispatched'] and records['stop'] is None)
    assetsha=sha(B/plan['inputs']['scene']);imagesha=sha(B/plan['inputs']['image']);dep=j(B/'installation/READY.json')['dependency_python'];entry=j(B/'installation/READY.json')['entry']
    for slot,record in zip(seq,records['records'],strict=True):
        cell=B/'cells'/slot['cell'];c=j(cell/'CONSUMER.json');cfg=j(cell/'ACTOR_CONFIG.json');a=j(cell/'ACTOR_LAUNCH.json');iid=j(cell/'owner/IDENTITY.json');cl=j(cell/'owner/CLOSE.json');f=j(cell/'OWNER_FINISH.json');ns=j(cell/'owner/native/SESSION.json');wc=j(cell/'owner/native/WORKER_CLOSED.json')
        threads.add(c['thread_id']);consumerpids.add(c['consumer_pid'])
        chk('consumer_record_bound_'+str(len(threads)),c==record['consumer'] and all(c[k]==slot[k] for k in ('cell','task','round','group')) and c['owner_finish']==f==record['finish'])
        consumers+=c['valid_completion'] and c['process_reaped'] and c['exit_code']==0
        geometry+=sha(cell/'owner/INITIAL.json')==sha(cell/'owner/FINAL.json')==sha(B/'preflight/SOURCE_SNAPSHOT.json') and sha(cell/'owner/native/input.blend')==assetsha==iid['asset_sha256']==cfg['asset_sha256'] and cl['geometry_unchanged'] and cl['asset_unchanged']
        runtimeid=iid['runtime_identity'];basegood=iid['python']==dep and not iid['private_geometry_warmup']
        if runtimeid is None:
            identity+=basegood and iid['product_serve_entry'] is None and cl['plugin_close'] is None and iid['exposed_tool_names']==['execute_blender_code']
        else:
            init=j(cell/'owner/PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye'];start=j(cell/'owner/plugin/START.json')
            identity+=basegood and runtimeid==init and init['source_sha256']==CANON and init['source_file_count']==137 and init['source_kind']=='installed_distribution' and init['identity_check']['compatible'] and start['command'][0]==dep and start['command'][3]==entry==iid['product_serve_entry']
            knownpids.add(start['launcher_pid'])
        argv=c['argv'];pos=[i for i,x in enumerate(argv) if x=='--image'];img=c['initial_image'];delivery=c['image_delivery']
        image+=len(pos)==1 and Path(argv[pos[0]+1])==B/plan['inputs']['image'] and img['sha256']==imagesha==plan['inputs']['image_sha256'] and sha(img['path'])==imagesha and c['initial_image_unchanged'] and delivery['initial_attachment_in_argv'] and delivery['provider_delivery_confirmed'] is None and delivery['model_view_confirmed'] is None
        original=a['worker_deadline_ns'];nc=cl['native_close']
        deadline+=original==record['worker_deadline_ns']==cfg['worker_deadline_ns']==ns['deadline_ns']==nc['original_deadline_ns']==wc['original_deadline_ns'] and original==a['cell_started_ns']+plan['total_cell_seconds']*10**9 and c['deadline_ns']==c['started_ns']+plan['max_session_seconds']*10**9 and cl['ended_ns']<=original and record['cell_ended_ns']<=original
        nativeclosefiles=list((cell/'owner/native').glob('CLOSE_*.json'));nativeclose=[j(p) for p in nativeclosefiles]
        # Scope is original launcher/backend receipts, never inferred from PID absence.
        backends+=f['close']==cl and f['confirmed'] and f['exit_code']==0 and f['actor_pid']==a['pid']==iid['actor_parent_pid'] and cl['actor_pid']==iid['actor_pid'] and nc['response']['status']=='closed' and nc['pid']==wc['pid'] and nc['process_reaped'] and nc['exit_code']==0 and cl['worker_closed']==wc and any(x==nc for x in nativeclose) and (cl['plugin_close'] is None or cl['plugin_close']['confirmed'] and cl['plugin_close']['exit_code']==0)
        bc=c['bridge_cleanup'];instances=bc['instances'];missing=0
        for instance in instances:
            d=Path(instance['directory']);start=j(d/'STARTED.json')
            missing+=not (d/'EXIT.json').exists() and instance['exit'] is None and instance['confirmed'] is False and instance['started']==start
            knownpids.add(start['pid'])
        thinmissing+=missing
        chk('thin_unknown_not_graceful_'+str(len(threads)),missing==bc['missing_exit_count']==1 and bc['confirmed'] is None and bc['receipt_status']=='unknown')
        knownpids.update((c['consumer_pid'],a['pid'],iid['actor_pid'],ns['pid']))
    chk('six_unique_consumers_and_threads',len(threads)==len(consumerpids)==6 and consumers==6)
    chk('six_initial_final_and_original_asset_bindings',geometry==6)
    chk('six_actual_runtime_identity_bindings',identity==6)
    chk('six_same_image_arg_hash_and_unknown_delivery',image==6)
    chk('six_original_deadlines_retained_through_actual_close',deadline==6)
    chk('six_actor_and_backend_close_records_bound',backends==6)
    chk('six_missing_thin_EXIT_retained_unknown',thinmissing==seal['thin_missing_EXIT_receipts']==ready['thin_missing_EXIT_receipts']==6 and seal['thin_exit_status']=='unknown')
    estate=j(B/'formal_run/private/EXECUTION_STATE.json')
    chk('known_33_PID_inventory_only_corroborative',len(estate['PID_index'])==33 and {r['pid'] for r in estate['PID_index']}==knownpids and len(knownpids)==33)
    go=j(B/'GO.json');started=j(B/'STARTED.json')
    chk('GO_STARTED_fixed_plan_binding',go['authorized'] and go['max_consumers']==started['max_consumers']==6 and go['plan_sha256']==started['plan_sha256']==sha(B/'PLAN.json') and seal['GO_sha256']==sha(B/'GO.json'))
    counts.update(logical_slots=6,consumer_threads=len(threads),source_and_geometry_bindings=geometry,runtime_identity_bindings=identity,image_argument_and_hash_bindings=image,deadline_to_close_bindings=deadline,backend_close_bindings=backends,thin_missing_EXIT_unknown=thinmissing,recorded_PID_inventory=len(knownpids))

stage('indices',indices);stage('handoff',handoff);stage('runtime',runtime)
out=dict(schema='m4-formal-blind-integrity-review-v1',status='pass' if not errors else 'requires_review',fixed_head=HEAD,product_source_sha256=CANON,source_count=137,checks=checks,aggregate_counts=counts,errors=errors,method='Independent byte/hash/Git and captured original record checks only; no backend, model, product or author packager execution',unknown=['Six thin EXIT receipts absent: graceful client exit remains unknown.','Provider image delivery and model viewing remain unknown.','Exact provider request count and fees not established; no cost comparison performed.'],limits=['No quality scoring performed. Output excludes anonymous-to-cell/arm mapping and timing/usage values.','The already reviewed 137-source installation matrix was not repeated.','Historical PID absence is corroborative only and is not promoted to graceful exit.','Initial/final equality cannot exclude every transient scene action; original image monitoring scope remains limited.'],artifacts={'execution_index_sha256':sha(B/'formal_run/EXECUTION_ARTIFACT_INDEX.json'),'execution_seal_sha256':sha(B/'formal_run/EXECUTION_SEAL.json'),'public_index_sha256':sha(P/'INDEX.json'),'private_provenance_sha256':sha(V/'PROVENANCE.json'),'packager_sha256':sha(B/'quality_handoff/pack_quality.py')})
O.mkdir(parents=True,exist_ok=True);dest=O/'INTEGRITY_REVIEW.json'
with dest.open('x',encoding='utf-8')as f:f.write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':out['status'],'checks':len(checks),'errors':errors,'aggregate_counts':counts,'report_sha256':sha(dest)},ensure_ascii=False))
