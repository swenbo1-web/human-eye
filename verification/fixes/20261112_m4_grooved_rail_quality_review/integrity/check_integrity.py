"""Offline independent byte/lifecycle/projection audit; writes only beside itself.

No product modules are imported, no implementation scripts are executed, and
private mapping values are never decoded. Mixed administrative JSON is traversed
lexically: only explicitly requested identity/status/contract values are decoded.
Business payloads are compared for equality, never printed or quality-scored.
"""
from pathlib import Path
import hashlib, json, subprocess, zipfile, re, ast

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = ROOT / 'verification/m4_grooved_rail_consumption_001'
Q = ROOT / 'verification/m4_grooved_rail_transfer_001'
PUB = B / 'runtime/handoff_01/public'
PRIV = B / 'runtime/handoff_01/private'
HEAD = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
PARENT = '25e4f21335a53b28c5688dc6611f13204a6fde15'
PREP = '8f83d7eb'
QUAL = '9f38e8522cfeea9a580a19baad0e0d823eb1a16f'
PRODUCT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
PACKET = '1c121d1e513f8b8103dfed42ae20168773f178861dcf3026a23dc3f119044026'
READY = '4d33f0b4c01131974a540852f7d6aea83df1e9487fa02286a57d892dfa582224'
SOURCE = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
checks = {}

def sha(raw): return hashlib.sha256(raw).hexdigest()
def file_sha(path): return sha(path.read_bytes())
def enc(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
def check(name, value): checks[name] = bool(value)
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)
def tree(commit, *paths):
    out = {}
    for row in git('ls-tree','-r','-z',commit,'--',*paths).split(b'\0'):
        if row:
            meta, name = row.split(b'\t',1)
            mode, kind, digest = meta.split()
            assert kind == b'blob' and mode in (b'100644',b'100755')
            out[name.decode()] = digest.decode()
    return out
def blob(path):
    data=path.read_bytes()
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

class J:
    """Lexical JSON view: skip unrequested values without decoding them."""
    def __init__(self, raw): self.s = raw.decode('utf-8-sig') if isinstance(raw,bytes) else raw
    def skip(self, pos):
        s=self.s
        while pos<len(s) and s[pos].isspace(): pos+=1
        start=pos
        if s[pos]=='"':
            pos+=1
            while pos<len(s):
                if s[pos]=='\\': pos+=2
                elif s[pos]=='"': return pos+1
                else: pos+=1
        elif s[pos] in '[{':
            close='}' if s[pos]=='{' else ']'; pos+=1
            while True:
                while s[pos].isspace() or s[pos] in ',:': pos+=1
                if s[pos]==close: return pos+1
                pos=self.skip(pos)
        else:
            while pos<len(s) and s[pos] not in ',]} \r\n\t': pos+=1
            return pos
        raise ValueError('incomplete JSON value at '+str(start))
    def fields(self):
        s=self.s; pos=0
        while s[pos].isspace(): pos+=1
        assert s[pos]=='{'; pos+=1; out={}
        while True:
            while s[pos].isspace() or s[pos]==',': pos+=1
            if s[pos]=='}': return out
            end=self.skip(pos); key=json.loads(s[pos:end]); pos=end
            while s[pos].isspace(): pos+=1
            assert s[pos]==':'; pos+=1
            while s[pos].isspace(): pos+=1
            end=self.skip(pos)
            if key in out: raise ValueError('duplicate key')
            out[key]=J(s[pos:end]); pos=end
    def array(self):
        s=self.s; pos=0
        while s[pos].isspace(): pos+=1
        assert s[pos]=='['; pos+=1; out=[]
        while True:
            while s[pos].isspace() or s[pos]==',': pos+=1
            if s[pos]==']': return out
            end=self.skip(pos); out.append(J(s[pos:end])); pos=end
    def node(self,*keys):
        value=self
        for key in keys:
            if value is None or value.s.strip()=='null': return None
            value=value.fields().get(key)
        return value
    def get(self,*keys,default=None):
        value=self.node(*keys)
        return default if value is None else json.loads(value.s)
    def select(self,*keys): return {key:self.get(key) for key in keys}

def j(path): return J(path.read_bytes())
def normal(value):
    return {'unit_scale_m':value.get('unit_scale_m',value.get('scale_length')),
            'objects':sorted([{'name':o['name'],'vertices_local':o['vertices_local'],
              'matrix_world':o['matrix_world'],'faces':o.get('faces',o.get('triangles'))}
              for o in value['objects']],key=lambda o:o['name'])}

def project_rpc(raw, request=False):
    node=J(raw)
    value={}
    for k,v in node.fields().items():
        if k in ('id','jsonrpc','_meta'): continue
        if request and k=='params' and v.s.lstrip().startswith('{'):
            value[k]={pk:json.loads(pv.s) for pk,pv in v.fields().items() if pk!='_meta'}
        else: value[k]=json.loads(v.s)
    return value

def project_tool_evidence(sources):
    attempts=[]; events=[]
    names=sorted({p.split('/')[1] for p in sources if re.match(r'^owner/tool_\d+/',p)},key=lambda x:int(x.split('_')[1]))
    for directory in names:
        a={'order':len(attempts)+1,'request':None,'responses':[],'is_error':None,'owner_exception':None,'source_files':[]}
        for kind in ('REQUEST.json','RESPONSE.json','ERROR_RESPONSE.json','ATTEMPT.json'):
            raw=sources.get('owner/'+directory+'/'+kind)
            if raw is None: continue
            a['source_files'].append({'kind':kind,'original_sha256':sha(raw)})
            if kind=='REQUEST.json': a['request']=project_rpc(raw,True)
            elif kind=='ATTEMPT.json':
                n=J(raw); a['is_error']=n.get('is_error')
                exc=n.node('exception')
                a['owner_exception']=None if exc is None or exc.s.strip()=='null' else {k:json.loads(v.s) for k,v in exc.fields().items() if k!='traceback'}
            else: a['responses'].append({'kind':kind,'value':project_rpc(raw)})
        a['request_missing']=a['request'] is None; a['response_missing']=not a['responses']; attempts.append(a)
    tool_types={'command_execution','mcp_tool_call','custom_tool_call','function_call','web_search','image_view','file_change','todo_list','collab_tool_call'}
    raw=sources.get('events.jsonl',b'')
    for line in raw.splitlines():
        if not line.strip(): continue
        n=J(line); phase=n.get('event','type'); item=n.node('event','item')
        if item is not None and item.get('type') in tool_types and phase in ('item.started','item.completed'):
            fields=item.fields()
            selected={k:json.loads(fields[k].s) for k in ('type','tool','server','arguments','result','error','status','command') if k in fields}
            events.append({'order':len(events)+1,'phase':phase,'event':selected,'source_sha256':sha(raw),'source_line_sha256':sha(line)})
    return {'owner_attempts':attempts,'public_tool_events':events,
        'binding_scope':'Owner-produced responses and consumer-public events are separate original records; unmatched/missing evidence does not prove delivery.'}

def consistency_matches_original(public, sources):
    """Every copied field checked by producer JSON path, including null reasons."""
    config=J(sources['ACTOR_CONFIG.json']); identity=J(sources['owner/IDENTITY.json'])
    consumer=J(sources['CONSUMER.json']); close=J(sources['owner/CLOSE.json'])
    notes=[]
    def field(label,node,*path):
        value=node.node(*path)
        if value is None:
            notes.append({'record':label,'pointer':'$/'+('/'.join(path)),'reason':'field_missing_or_parent_unavailable'})
            return None
        decoded=json.loads(value.s)
        if decoded is None: notes.append({'record':label,'pointer':'$/'+('/'.join(path)),'reason':'present_recorded_null'})
        return decoded
    # Administrative worker timestamp/PID values are lexically skipped.
    worker=close.node('worker_closed')
    worker_value=None if worker is None or worker.s.strip()=='null' else {k:json.loads(v.s) for k,v in worker.fields().items() if k not in ('pid','closed_ns','original_deadline_ns')}
    if worker_value is None:
        notes.append({'record':'owner/CLOSE.json','pointer':'$/worker_closed','reason':'record_missing' if worker is None else 'present_recorded_null'})
    expected={'ACTOR_CONFIG':{'asset_sha256':field('ACTOR_CONFIG.json',config,'asset_sha256')},
        'owner_IDENTITY':{'asset_sha256':field('owner/IDENTITY.json',identity,'asset_sha256')},
        'CONSUMER_INPUT':{
            'input_image_count':field('CONSUMER.json',consumer,'input_image_count'),
            'input_image_bytes':field('CONSUMER.json',consumer,'input_image_bytes'),
            'initial_image_sha256':field('CONSUMER.json',consumer,'initial_image','sha256'),
            'initial_image_unchanged':field('CONSUMER.json',consumer,'initial_image_unchanged'),
            'image_delivery':{k:field('CONSUMER.json',consumer,'image_delivery',k) for k in ('prepared_file_verified','initial_attachment_in_argv','CLI_process_launched','CLI_thread_started','status','provider_delivery_confirmed','model_view_confirmed')}},
        'INITIAL_original_file_sha256':sha(sources['owner/INITIAL.json']),
        'FINAL_original_file_sha256':sha(sources['owner/FINAL.json']),
        'CLOSE':{
            'geometry_unchanged':field('owner/CLOSE.json',close,'geometry_unchanged'),
            'asset_unchanged':field('owner/CLOSE.json',close,'asset_unchanged'),
            'native_close':{k:field('owner/CLOSE.json',close,'native_close',k) for k in ('source_file_unchanged','protected_files_unchanged')},
            'worker_closed':worker_value,
            'worker_fingerprint_fields':{k:field('owner/CLOSE.json',close,'worker_closed',k) for k in ('initial_geometry_fingerprint','final_geometry_fingerprint')},
            'errors':field('owner/CLOSE.json',close,'errors')},
        'source_records_sha256':{k:sha(sources[k]) for k in ('ACTOR_CONFIG.json','owner/IDENTITY.json','owner/CLOSE.json','CONSUMER.json','owner/INITIAL.json','owner/FINAL.json')},
        'scope':'Existing producer fields and original file hashes only. No pass/fail, equality or independent readonly attestation is inferred. Final equality cannot exclude every transient operation.',
        'missing_or_null_notes':notes}
    return enc(expected)==public

def main():
    check('fixed_HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
    check('implementation_worktree_clean_before',git('status','--porcelain=v1')==b'')
    prefix=B.relative_to(ROOT).as_posix()
    committed=tree(HEAD,prefix)
    actual={p.relative_to(ROOT).as_posix() for p in B.rglob('*') if p.is_file()}
    check('all_914_files_exact_inventory',len(actual)==914 and actual==set(committed))
    check('all_914_files_exact_Git_bytes',all(blob(ROOT/n)==v for n,v in committed.items()))
    check('no_symlinks_in_batch',not any(p.is_symlink() for p in B.rglob('*')))
    prep=tree(PREP,prefix)
    check('preparation_414_files_unchanged',len(prep)==414 and all(blob(ROOT/n)==v for n,v in prep.items()))
    check('ready_exact_requested_sha',file_sha(B/'FORMAL_QUALITY_READY.json')==READY)
    manifest=json.loads((B/'PUBLIC_PACKET_MANIFEST.json').read_bytes())
    files=[{'path':p.relative_to(PUB).as_posix(),'bytes':p.stat().st_size,'sha256':file_sha(p)} for p in sorted(PUB.rglob('*')) if p.is_file()]
    files.sort(key=lambda row:row['path'])
    digest=sha(json.dumps(files,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
    check('public_exact_30_file_manifest',len(files)==30 and files==manifest['files'])
    check('public_packet_sha256',digest==manifest['packet_sha256']==PACKET)
    plan=j(B/'PLAN.json'); freeze=j(B/'FREEZE.json'); go=j(B/'GO.json'); ready=j(B/'FORMAL_QUALITY_READY.json')
    plan_sha=file_sha(B/'PLAN.json')
    check('PLAN_FREEZE_GO_ready_binding',all(n.get('plan_sha256')==plan_sha for n in (freeze,go,ready)))
    for field,base in [('dispatch_input_sha256',B),('external_input_sha256',None)]:
        rows=plan.get(field)
        check(field+'_every_frozen_file_matches',all(file_sha((base/rel) if base else Path(rel))==h for rel,h in rows.items()))
    check('protected_files_unchanged',all(file_sha(Path(n))==h for n,h in json.loads((B/'preflight/PROTECTED_BEFORE.json').read_bytes()).items()))
    seal=json.loads((B/'QUALIFICATION_SEAL.json').read_bytes())
    refs={'ROOT_PLAN.md':'docs/M4_GROOVED_RAIL_TRANSFER_001_CONSUMPTION_PLAN.md','QUALIFICATION_REVIEW.md':'docs/M4_GROOVED_RAIL_TRANSFER_001_QUALIFICATION_REVIEW.md','QUALIFICATION_SEAL.json':'verification/fixes/20261112_m4_grooved_rail_qualification_review/QUALIFICATION_REVIEW.json'}
    root_tree=tree(PARENT,*refs.values(),*[x['path'] for x in seal['files']])
    check('three_root_contract_copies_exact_25e4f213',all(blob(B/k)==root_tree[v] for k,v in refs.items()))
    check('sealed_root_evidence_exact_bytes',all(file_sha(Path('D:/hefe')/r['path'])==r['sha256'] and (Path('D:/hefe')/r['path']).stat().st_size==r['bytes'] and blob(Path('D:/hefe')/r['path'])==root_tree[r['path']] for r in seal['files']))
    check('qualification_seal_fixed_identity',seal['implementation_commit']==QUAL and seal['product_commit']==PRODUCT and seal['status']=='qualified_for_frozen_six_consumer_phase')
    qm=json.loads((Q/'QUALIFICATION_MANIFEST.json').read_bytes()); qt=tree(QUAL,Q.relative_to(ROOT).as_posix())
    check('qualification_57_files_exact_inventory',len(qt)==57 and set(qt)=={p.relative_to(ROOT).as_posix() for p in Q.rglob('*') if p.is_file()})
    check('qualification_57_files_exact_Git_bytes',all(blob(ROOT/n)==h for n,h in qt.items()))
    check('qualification_56_manifest_entries',len(qm['files'])==56 and all(file_sha(Q/r['path'])==r['sha256'] and (Q/r['path']).stat().st_size==r['bytes'] for r in qm['files']))
    check('qualification_manifest_SHA',file_sha(Q/'QUALIFICATION_MANIFEST.json')=='6ff0b854aa52385322e93693c3fa647647eae7705fe91c6a6ca87d209855a9c4')
    for old,new in [('asset/grooved_rail.blend','input/scene.blend'),('asset/ACTUAL_SNAPSHOT.json','scoring/ACTUAL_SNAPSHOT.json'),('oracle/TRUTH.json','scoring/TRUTH.json')]:
        check('qualification_copy_'+new,file_sha(Q/old)==file_sha(B/new))
    sb=j(B/'preflight/SOURCE_BINDING.json'); install=j(B/'installations/P_READY.json'); rows=sb.get('source_manifest')
    pt=tree(PRODUCT,*[r['path'] for r in rows])
    check('137_source_manifest_identity',len(rows)==sb.get('source_count')==install.get('source_count')==137 and sb.get('source_sha256')==install.get('source_sha256')==SOURCE)
    check('137_sources_worktree_install_and_product_Git',all(file_sha(ROOT/r['path'])==file_sha(Path(install.get('install_root'))/r['path'])==r['sha256'] and blob(ROOT/r['path'])==pt[r['path']] for r in rows))
    constants={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes()).body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION')}
    canonical=sha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':sorted(rows,key=lambda x:x['path'])},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('137_source_digest_independently_recomputed',canonical==SOURCE)
    check('installed_launcher_and_binding',file_sha(Path(install.get('entry')))==install.get('launcher_sha256') and file_sha(Path(install.get('release'))/'admin/RUNTIME_BINDING.json')==install.get('binding_sha256'))
    limits={'max_session_seconds':450,'total_cell_seconds':570,'actor_startup_seconds':40,'tool_attempts':32,'physical_RPC_limit':128,'tool_timeout_s':30,'tool_response_bytes':1048576,'code_bytes':262144}
    check('original_frozen_budget_values',all(plan.get(k)==v for k,v in limits.items()))
    check('fixed_model_effort_and_images',plan.get('model')=='gpt-6.1-sol' and plan.get('requested_effort')=='medium' and plan.get('image_count')==plan.get('new_images')==0)
    run=j(B/'RUN_RESULT.json'); records=run.node('records').array(); terminal=j(B/'FORMAL_PROCESS.json')
    check('six_started_no_replacements',run.get('started_cells')==run.get('maximum_consumers')==len(records)==6 and run.get('no_replacements') is True and run.get('all_planned_dispatched') is True)
    check('controller_terminal',terminal.get('status')=='terminal' and terminal.get('started_cells')==6 and terminal.get('controller_error') is None)
    check('six_unique_execution_slots',len({r.get('cell') for r in records})==6)
    expected_geometry=normal(json.loads((B/'scoring/ACTUAL_SNAPSHOT.json').read_bytes()))
    states=[]; thread_ids=[]; cell_sources=[]; event_starts=[]
    schema_native=json.loads((B/'schemas/COMMON_NATIVE.json').read_bytes())
    schema_observe=json.loads((B/'schemas/P_PUBLIC_TOOLS.json').read_bytes())
    schema_options=[json.loads((B/'schemas'/name).read_bytes()) for name in ('N_CONSUMER_TOOLS.json','P_CONSUMER_TOOLS.json')]
    check('common_frozen_schema_composition',schema_options==[[schema_native],[schema_native,*schema_observe]])
    for ordinal,r in enumerate(records,1):
        folder=B/'cells'/r.get('cell'); c=j(folder/'CONSUMER.json'); close=j(folder/'owner/CLOSE.json'); finish=j(folder/'OWNER_FINISH.json')
        cell_sources.append({p.relative_to(folder).as_posix():file_sha(p) for p in folder.rglob('*') if p.is_file()})
        thread_ids.append(c.get('thread_id'))
        cflags=c.select('status','valid_completion','safe_to_continue','exit_code','process_reaped','readers_stopped','deadline_timer_fired','mutation_unknown','cli_output_matches_public_final')
        completed=cflags['status']=='completed' and cflags['valid_completion'] is True and not r.get('errors')
        owner=finish.get('confirmed') is True and finish.get('exit_code')==0 and close.get('confirmed') is True
        native=all(close.get('native_close',k) is True for k in ('process_reaped','source_file_unchanged','protected_files_unchanged')) and close.get('native_close','exit_code')==0
        product=close.node('plugin_close'); runtime=close.node('product_runtime_exit')
        product_required=(folder/'owner/PLUGIN_TOOLS.json').is_file()
        product_ok=not product_required
        if product and product.s.strip()!='null':
            product_ok=all(product.get(k) is True for k in ('confirmed','process_reaped','reader_stopped')) and product.get('exit_code')==0 and runtime is not None and all(runtime.get(k) is True for k in ('confirmed','exited','handle_closed')) and runtime.get('exit_code')==0
        initial=normal(json.loads((folder/'owner/INITIAL.json').read_bytes())); final=normal(json.loads((folder/'owner/FINAL.json').read_bytes()))
        geometry=initial==final==expected_geometry and close.get('geometry_unchanged') is True and close.get('asset_unchanged') is True
        geometry=geometry and close.get('worker_closed','initial_geometry_fingerprint')==close.get('worker_closed','final_geometry_fingerprint') and close.get('worker_closed','poisoned') is False
        argv=c.get('argv'); flags=all(x in argv for x in ['exec','--ignore-user-config','--ignore-rules','--ephemeral','--strict-config','--json']) and 'resume' not in argv
        starts=[]
        for line in (folder/'events.jsonl').read_bytes().splitlines():
            if line.strip():
                e=J(line)
                if e.get('event','type')=='thread.started': starts.append(e.get('event','thread_id'))
        event_starts.append(starts)
        flags=flags and starts==[c.get('thread_id')]
        thin={k:c.get('bridge_cleanup',k) for k in ('confirmed','receipt_status','missing_exit_count')}
        missing=sum(not (p/'EXIT.json').is_file() for p in (folder/'attachments').glob('bridge_*'))
        check('slot_%d_execution_and_owned_closure'%ordinal,completed and owner and native and product_ok and cflags['process_reaped'] is True and cflags['readers_stopped'] is True and cflags['exit_code']==0 and not close.get('errors'))
        check('slot_%d_geometry_and_source'%ordinal,geometry and j(folder/'ACTOR_CONFIG.json').get('asset_sha256')==plan.get('inputs','scene_sha256')==j(folder/'owner/IDENTITY.json').get('asset_sha256'))
        check('slot_%d_fresh_ephemeral_context'%ordinal,flags)
        check('slot_%d_zero_image_and_prompt'%ordinal,all(c.get(k)==0 for k in ('input_image_count','input_image_bytes','public_image_count','public_image_bytes')) and '--image' not in argv and c.get('input_sha256')==file_sha(B/'input/PROMPT.txt') and close.get('zero_new_images_budget_met') is True and close.get('image_construction','observed') is False)
        check('slot_%d_no_protocol_deviation'%ordinal,not c.get('bridge_protocol_errors') and not c.get('unexpected_tool_deviations') and cflags['mutation_unknown'] is False)
        check('slot_%d_original_deadline_recorded_pass'%ordinal,r.get('within_570s') is True and cflags['deadline_timer_fired'] is False)
        check('slot_%d_thin_unknown_preserved'%ordinal,thin['receipt_status']=='unknown' and thin['confirmed'] is None and thin['missing_exit_count']==missing and missing>0)
        observed=[]
        for tx in sorted((folder/'attachments').glob('bridge_*/*/TX.bin')):
            if j(tx).get('method')=='tools/list':
                rx=tx.with_name('RX.bin')
                observed.append(rx.is_file() and j(rx).get('result','tools') in schema_options and {x['name'] for x in j(rx).get('result','tools')}==set(c.get('expected_tool_names')))
        check('slot_%d_actual_full_declaration_matches_frozen'%ordinal,bool(observed) and all(observed))
        identity=j(folder/'owner/IDENTITY.json')
        check('slot_%d_ordinary_serve_no_warmup'%ordinal,identity.get('product_spatial_task_only') is False and identity.get('private_geometry_warmup') is False)
        if product_required:
            selected=[t for t in j(folder/'owner/PLUGIN_TOOLS.json').get('result','tools') if t['name']=='human_eye_scene_observe']
            identity_ok=selected==schema_observe and identity.get('runtime_identity','source_sha256')==SOURCE and identity.get('runtime_identity','source_file_count')==137 and identity.get('runtime_identity','source_kind')=='installed_distribution'
        else: identity_ok=True
        check('slot_%d_applicable_runtime_source_identity'%ordinal,identity_ok)
        check('slot_%d_actual_saved_asset_unchanged'%ordinal,file_sha(Path(j(folder/'ACTOR_CONFIG.json').get('asset')))==plan.get('inputs','scene_sha256'))
        # Actual evidence endpoints, not process presence queried today.
        states.append({'execution_completed':completed,'CLI_and_readers_reaped':cflags['process_reaped'] and cflags['readers_stopped'],'owned_closure_confirmed':owner and native and product_ok,'initial_final_geometry_unchanged':geometry,'within_original_deadline_recorded':r.get('within_570s'),'thin_EXIT':thin})
    check('six_unique_fresh_context_ids',len(thread_ids)==6 and all(isinstance(x,str) and x for x in thread_ids) and len(set(thread_ids))==6)
    check('exactly_six_cell_directories',len([p for p in (B/'cells').iterdir() if p.is_dir()])==6)
    # Private mapping and provenance mapping fields remain lexically skipped.
    provenance=j(PRIV/'PROVENANCE.json')
    check('private_provenance_public_hashes',provenance.get('public_files_sha256')=={r['path']:r['sha256'] for r in files})
    check('packaging_script_bound',provenance.get('script_sha256')==file_sha(B/'runtime/pack_quality.py'))
    check('control_originals_same_bytes',all(file_sha(B/n)==h==file_sha(PRIV/'control'/n) for n,h in provenance.get('control_sha256').items()))
    check('private_map_hash_only_frozen',file_sha(B/'private/ANON_MAP.json')==plan.get('private_anonymous_map_sha256'))
    audits=[n.select('files_sha256','source_files_sha256') for n in provenance.node('answers').array()]
    index=json.loads((PUB/'INDEX.json').read_bytes()); answers=index['answers']
    check('public_exact_six_unscored_slots',index['fixed_slots']==len(answers)==6 and index['scoring_performed'] is False and len({r['anonymous_id'] for r in answers})==6)
    for entry in answers:
        aid=entry['anonymous_id']; destination=PUB/aid
        with zipfile.ZipFile(PRIV/'raw'/(aid+'.zip')) as z:
            names=z.namelist(); sources={n:z.read(n) for n in names}
        hashes={n:sha(raw) for n,raw in sources.items()}
        matching=[x for x in cell_sources if x==hashes]
        audit=[x for x in audits if x['source_files_sha256']==hashes]
        check(aid+'_complete_unique_raw_archive',len(names)==len(set(names)) and len(matching)==len(audit)==1)
        check(aid+'_provenance_published_hashes',len(audit)==1 and audit[0]['files_sha256']=={p.name:file_sha(p) for p in destination.iterdir() if p.is_file()})
        raw_final=sources.get('PUBLIC_FINAL.txt'); raw_cli=sources.get('final.txt')
        check(aid+'_answer_original_binding',raw_final==(destination/'answer.txt').read_bytes() and sha(raw_final)==entry['answer_original_sha256']==entry['source_provenance']['public_final_sha256'] and J(sources['CONSUMER.json']).get('final').encode()==raw_final and entry['answer_state']=='present')
        check(aid+'_CLI_corroboration_exact_bytes',raw_cli==(destination/'cli_output_unconfirmed.txt').read_bytes())
        check(aid+'_consumer_record_original_binding',sha(sources['CONSUMER.json'])==entry['source_provenance']['consumer_record_sha256'])
        check(aid+'_complete_business_projection_exact',enc(project_tool_evidence(sources))==(destination/'tool_evidence.json').read_bytes())
        consistency=json.loads((destination/'source_consistency.json').read_bytes())
        check(aid+'_consistency_all_original_hashes',all(hashes.get(k)==v for k,v in consistency['source_records_sha256'].items()) and consistency['INITIAL_original_file_sha256']==hashes['owner/INITIAL.json'] and consistency['FINAL_original_file_sha256']==hashes['owner/FINAL.json'])
        check(aid+'_consistency_asset_fields',consistency['ACTOR_CONFIG']['asset_sha256']==J(sources['ACTOR_CONFIG.json']).get('asset_sha256') and consistency['owner_IDENTITY']['asset_sha256']==J(sources['owner/IDENTITY.json']).get('asset_sha256'))
        check(aid+'_consistency_complete_projection_exact',consistency_matches_original((destination/'source_consistency.json').read_bytes(),sources))
    check('scoring_materials_exact_frozen_bytes',all(file_sha(PUB/r['file'])==r['sha256']==file_sha(B/r['source_path']) for r in index['scoring_materials']))
    check('common_prompt_exact_bytes',(PUB/'tasks/T1.txt').read_bytes()==(B/'input/PROMPT.txt').read_bytes())
    author=j(B/'review/POSTRUN_CHECK.json')
    author_summary={'reported_check_count':len(author.node('checks').fields()),'reported_passed':author.get('passed'),'scope':'Historical author-side report; not added to this independent check count.'}
    check('implementation_worktree_clean_after',git('status','--porcelain=v1')==b'')
    result={'schema':'anonymous-integrity-review.v1','fixed_HEAD':HEAD,'passed':all(checks.values()),'independent_check_count':len(checks),'checks':checks,'failed_checks':[k for k,v in checks.items() if not v],
        'public_packet_sha256':digest,'ready_sha256':file_sha(B/'FORMAL_QUALITY_READY.json'),'declared_original_limits':limits,
        'execution_summary':{'completed':sum(x['execution_completed'] for x in states),'execution_failed':sum(not x['execution_completed'] for x in states),'not_run':6-len(states),'fresh_unique_contexts':len(set(thread_ids)),'replacement_consumers':0 if run.get('no_replacements') is True else None,'all_recorded_owned_process_closures_confirmed':all(x['owned_closure_confirmed'] for x in states),'thin_EXIT_unknown_cells':sum(x['thin_EXIT']['receipt_status']=='unknown' for x in states),'thin_EXIT_missing_receipts':sum(x['thin_EXIT']['missing_exit_count'] for x in states)},
        'anonymous_lifecycle_multiset':sorted(states,key=lambda x:json.dumps(x,sort_keys=True)),
        'author_report':author_summary,'deferred':['Semantic private map/plan/run group association and actual arm assignment require post-quality unsealing. Mapping files were only hashed.','Raw timestamp arithmetic, deadline origin/reuse and elapsed budget enforcement independent recomputation deferred. Current phase checks frozen limits and existing within_570s/deadline_timer_fired status only.','Usage/cost, arm comparison, mechanism/adoption analysis, and answer correctness are not examined by this integrity audit.'],
        'limits':['Closure is corroborated by retained producer receipts, not a contemporary OS process query or proof excluding transient edits.','Freshness supported by six unique thread.started IDs and ephemeral no-resume argv, plus frozen code empty-workspace guard; not provider internals.','Initial schema reconnaissance decoded mixed JSON containers in memory but output only keys except accidentally displayed preparation FREEZE.frozen_utc and reused P_READY.elapsed_ns. No formal-cell timing/usage values or private mapping values were selected, displayed, compared, or used for conclusions. This script uses lexical field selection for mixed records.'],
        'new_runs':{'Blender':0,'product':0,'consumer':0,'API':0},'implementation_writes':0,'git_writes':0,'review_script_sha256':file_sha(Path(__file__))}
    (OUT/'RESULTS.json').write_bytes(enc(result))
    report='\n'.join(['# 匿名来源与执行完整性独立复核','',
        f"独立检查 {len(checks)} 项；通过 {sum(checks.values())} 项；失败 {len(result['failed_checks'])} 项。作者历史报告 {author_summary['reported_check_count']} 项另记，不计入本轮独立检查。",'',
        '固定实施树 HEAD、914 文件 Git/磁盘字节、414 份准备文件、30 文件 public manifest、原资格 57 文件、137 源码与隔离安装、根计划和封存输入逐项离线核验。',
        '匿名答案只作原始字节/绑定比较。六份完整原件 zip 与磁盘来源、provenance 摘要、工具请求/响应/错误、public tool event 及 source_consistency 全字段投影独立重新构造比对；未调用作者打包器或执行检查脚本。实际 tools/list 完整声明对冻结 schema 核验。','',
        '执行记录：'+json.dumps(result['execution_summary'],ensure_ascii=False)+'。实际 owner/native/适用 runtime 的退出凭各自记录核验；薄客户端 EXIT unknown 和缺失回执单列保留，不相互替代。','',
        '原合同预算值与 frozen preparation 一致。原始时间算术、原期限起点/继承和实际数值限额复算，以及私有映射的语义对应，须质量封存后解封；本轮不把已有 within_570s 状态当作独立时间测量。','',
        '封存边界记录：最初结构探查使用完整 JSON 解码器在内存中解码混合容器，仅输出键名，但误输出了准备冻结时间及复用安装耗时两项元数据。未选取、展示或比较正式六格时间/usage，也未读取私有映射值；该局限已告知父审查者。后续复核脚本对混合记录采用词法字段选择。','',
        '未进行答案质量、组别、成本或机制结论。新增 Blender/产品/消费者/API 运行均为 0，实施树和 Git 均未写入。','',
        'public packet SHA256：`'+digest+'`。','ready SHA256：`'+result['ready_sha256']+'`。','失败项：`'+json.dumps(result['failed_checks'],ensure_ascii=False)+'`。',''])
    (OUT/'REPORT.md').write_text(report,encoding='utf-8',newline='\n')
    print(json.dumps({k:result[k] for k in ['passed','independent_check_count','failed_checks','execution_summary','public_packet_sha256']},ensure_ascii=False))

if __name__=='__main__': main()
