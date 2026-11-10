"""COMPLEX-004 preparation and single serial trial; model execution needs root GO."""
import argparse,hashlib,importlib.util,json,os,socket,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OLD=HERE.parent/'native_plugin_complex_003';DIAG=HERE.parent/'scale_diag_001'
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def tasks():return {
 'assembly':{'asset':str(OLD/'scene.blend'),'prompt':str(OLD/'PROMPT.txt'),'initial':str(OLD/'private/author_mesh_snapshots.json')},
 'discovery':{'asset':str(DIAG/'fixtures/D48.blend'),'prompt':str(HERE/'PROMPT_DISCOVERY.txt'),'initial':str(DIAG/'fixtures/D48.json')}}
def sequence():
    result=[];latin=[['N','O','C'],['O','C','N'],['C','N','O']]
    for round_ in range(3):
        order=('assembly','discovery') if round_%2==0 else ('discovery','assembly')
        for task in order:
            for group in latin[(round_+(task=='discovery'))%3]:result.append({'cell':str(len(result)+1).zfill(2),'round':round_+1,'task':task,'group':group})
    return result
def prepare_plan():
    source=read(HERE/'SOURCE_PREFLIGHT.json');cli=read(HERE/'CLI_PREFLIGHT.json');assert source['passed'] and cli['passed']
    plan={'cycle_id':'NATIVE-PLUGIN-COMPLEX-004','phase':'PREP/PREFLIGHT; no model execution before root GO','sequence':sequence(),'denominator':18,
       'model':'gpt-6.1-sol','requested_effort':'medium','max_session_seconds':450,'total_cell_seconds':570,'tool_attempts':32,
       'tool_response_bytes':1048576,'tool_timeout_s':30,'code_bytes':262144,'physical_RPC_limit':128,'images':0,'model_retries':0,
       'CLI_sha256':cli['cli']['sha256'],'tasks':tasks(),'source_manifest_sha256':sha(HERE/'SOURCE_PREFLIGHT.json'),
       'session_rules':str(HERE/'SESSION_RULES.txt'),'session_rules_sha256':sha(HERE/'SESSION_RULES.txt'),
       'ordinary_scene_observe_schema_unchanged':True,'public_native_same_as_003':True,
       'image_budget_enforcement':'ordinary schema unchanged; missing/true include_image refused, never rewritten; error consumes attempt/bytes',
       'private_input_boundary':'truth/scoring/plan not sent or copied into consumer workspaces; native Python is an audited read-only protocol, not a hostile-code filesystem security sandbox',
       'unknown_and_failed_in_denominator':True,'independent_quality':'unmodified anonymous final text, task-labelled only; route wording may reveal method; root judges before costs',
       'learning_context':'own connection unbound/rebind_required host_epoch5; parent task514 not borrowed','fees':'unmeasured','coordinator_model_cost':'unmeasured'}
    for task,value in plan['tasks'].items():
        value['asset_sha256']=sha(value['asset']);value['prompt_sha256']=sha(value['prompt']);value['prompt_bytes']=Path(value['prompt']).stat().st_size
        raw=(HERE/'SESSION_RULES.txt').read_bytes()+b'\n'+Path(value['prompt']).read_bytes()
        value['model_input_sha256']=hashlib.sha256(raw).hexdigest();value['model_input_bytes']=len(raw)
    save(HERE/'PLAN.json',plan);return plan
def prepare(cell,group,task,*,root_folder=None):
    source=read(HERE/'SOURCE_PREFLIGHT.json');folder=(HERE/'cells' if root_folder is None else Path(root_folder))/cell
    folder.mkdir(parents=True,exist_ok=False);task_info=tasks()[task];start=time.perf_counter_ns()
    version=None if group=='N' else source['versions'][group]
    raw_schema=read(HERE/'O_schemas.stdout.json')
    schemas=raw_schema['tools_list']['result']['tools']
    if not schemas and 'schema_probe' in source['versions']['O']:schemas=source['versions']['O']['schema_probe'].get('tools',[])
    assert isinstance(schemas,list) and schemas,'ordinary_schema_source_required'
    read_schema=next(t for t in schemas if t['name']=='human_eye_scene_observe')
    config={'group':group,'task':task,'output':str(folder/'owner'),'endpoint':str(folder/'ENDPOINT.json'),
        'asset':task_info['asset'],'asset_sha256':sha(task_info['asset']),'blender':'D:/Tools/blender5.2/blender.exe',
        'worker_deadline_ns':start+570*10**9,'dependency_python':source['dependency_python'],'read_schema':read_schema,
        'entry':None if version is None else version['entry'],'install_root':None if version is None else version['installed_root'],
        'source_sha256':None if version is None else version['source_sha256']}
    save(folder/'ACTOR_CONFIG.json',config)
    out=(folder/'actor_stdout.bin').open('wb');err=(folder/'actor_stderr.bin').open('wb');actor=None
    try:
        actor=subprocess.Popen([source['dependency_python'],'-I','-B',str(HERE/'actor.py'),'--config',str(folder/'ACTOR_CONFIG.json')],
            stdin=subprocess.PIPE,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        save(folder/'ACTOR_LAUNCH.json',{'launcher_pid':actor.pid,'started_ns':start})
        deadline=time.perf_counter()+40
        while not (folder/'ENDPOINT.json').exists():
            if actor.poll() is not None:raise RuntimeError('actor_start_failed:'+str(folder))
            if time.perf_counter()>deadline:raise TimeoutError('actor_startup_40s')
            time.sleep(.03)
        save(folder/'cell.json',{'endpoint':str(folder/'ENDPOINT.json'),'audit_dir':str(folder/'owner')})
        return folder,{'python':source['dependency_python']},actor,start
    except BaseException as exc:
        if actor is not None:
            if actor.poll() is None:
                try:actor.stdin.write(b'finish\n');actor.stdin.close();actor.wait(timeout=45)
                except BaseException:
                    subprocess.run(['taskkill','/PID',str(actor.pid),'/T','/F'],capture_output=True,timeout=5)
                    if actor.poll() is None:actor.kill();actor.wait(timeout=5)
        save(folder/'PREPARE_FAILURE.json',{'error':repr(exc),'launcher_reaped':actor is not None and actor.poll() is not None})
        raise
    finally:out.close();err.close()
def finish(folder,actor):
    start=time.perf_counter_ns()
    if actor.poll() is None:actor.stdin.write(b'finish\n');actor.stdin.close()
    try:actor.wait(timeout=45)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/PID',str(actor.pid),'/T','/F'],capture_output=True,timeout=5)
        if actor.poll() is None:actor.kill();actor.wait(timeout=5)
    close=read(folder/'owner/CLOSE.json') if (folder/'owner/CLOSE.json').exists() else {'confirmed':False}
    value={'actor_launcher_pid':actor.pid,'actor_exit':actor.returncode,'close':close,'finish_elapsed_ns':time.perf_counter_ns()-start,'confirmed':actor.returncode==0 and close.get('confirmed',False)}
    save(folder/'OWNER_FINISH.json',value);return value
def snapshot_binding(folder,task):
    actual=read(folder/'owner/INITIAL.json');expected=read(tasks()[task]['initial']);expected=expected['initial'] if task=='assembly' else expected
    fields=('name','vertices_local','matrix_world','faces')
    if task=='discovery':
        expected={'unit_scale_m':expected['unit_scale_m'],'objects':[dict(o,faces=o['triangles']) for o in expected['objects']]}
    assert [{k:o[k] for k in fields} for o in actual['objects']]==[{k:o[k] for k in fields} for o in expected['objects']],'frozen_mesh_binding'
    assert actual['unit_scale_m']==expected.get('unit_scale_m',1.)
    return {'matched':True,'objects':len(actual['objects']),'vertices':sum(len(o['vertices_local']) for o in actual['objects']),
        'triangles':sum(len(o['faces']) for o in actual['objects']),'snapshot_sha256':sha(folder/'owner/INITIAL.json')}
def preflight(output_root=None):
    start=time.perf_counter_ns();plan=prepare_plan();client=load('complex004_attach',OLD/'reused/stdio_attach.py');results=[]
    for task in ('assembly','discovery'):
        for group in ('N','O','C'):
            name=task+'_'+group;folder,install,actor,began=prepare(name,group,task,root_folder=output_root or HERE/'preflight');replies=[];error=None
            try:
                endpoint=read(folder/'ENDPOINT.json');binding=snapshot_binding(folder,task)
                # Exercise one recoverable failure before a valid request. No model.
                bad={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'execute_blender_code','arguments':{'code':"raise ValueError('controlled_no_model_preflight_error')"}}}
                replies.append(client.attach(endpoint,'native',bad));assert replies[-1]['result']['isError']
                good={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'execute_blender_code','arguments':{'code':"print({'mesh_count':sum(o.type=='MESH' for o in bpy.context.scene.objects)})"}}}
                replies.append(client.attach(endpoint,'native',good));assert not replies[-1]['result']['isError']
                listed=client.attach(endpoint,'native',{'jsonrpc':'2.0','id':3,'method':'tools/list'});save(folder/'PUBLIC_TOOLS.json',listed)
                if group!='N':
                    query={'mode':'task','target':{'name':'Object_01'},'candidates':[{'name':n} for n in ('Object_02','Object_03','Object_04')],'requested_facts':['closed_solid_relation','surface_proximity']} if task=='assembly' else {'mode':'surface_nearest','objects':[{'name':'Target'}]}
                    req={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'human_eye_scene_observe','arguments':{'session_id':'current-scene','include_image':False,'query':query}}}
                    replies.append(client.attach(endpoint,'native',req));assert not replies[-1]['result']['isError']
                save(folder/'REPLIES.json',replies)
            except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)};save(folder/'PREFLIGHT_ERROR.json',error)
            finally:closed=finish(folder,actor)
            tools=read(folder/'owner/TOOLS.json');assert tools['attempts']==len(replies) and tools['tools'][0]['is_error'],'failed_attempt_ledger'
            row={'task':task,'group':group,'folder':str(folder),'error':error,'closed':closed['confirmed'],'model_calls':0,'wall_ns':time.perf_counter_ns()-began,
                 'binding':locals().get('binding'),'tool_attempts':tools['attempts'],'all_attempts_logged':len(tools['tools'])==tools['attempts']}
            results.append(row);save(HERE/'PREFLIGHT_PROGRESS.json',results)
            if error or not closed['confirmed']:raise RuntimeError('preflight_failed:'+name)
    save(HERE/'PREFLIGHT.json',{'passed':True,'model_calls':0,'cells':results,'wall_ns':time.perf_counter_ns()-start,'ordinary_real_serve':True})
    print(json.dumps({'preflight':True,'cells':len(results),'model_calls':0}))
def run():
    # Root publishes GO only after reviewing this fixed plan and preflight.
    go=read(HERE/'GO.json');assert go['task']=='NATIVE-PLUGIN-COMPLEX-004' and go['authorized'] is True
    assert go['plan_sha256']==sha(HERE/'PLAN.json') and go['freeze_sha256']==sha(HERE/'FREEZE.json')
    plan=read(HERE/'PLAN.json')
    for path,want in read(HERE/'FREEZE.json')['files_sha256'].items():assert sha(path)==want,path
    with (HERE/'STARTED.json').open('x') as stream:json.dump({'started_ns':time.perf_counter_ns(),'max_consumers':18},stream)
    transport=load('complex004_transport',HERE/'consumer_transport.py');assert sha(transport.EXE)==plan['CLI_sha256'];records=[];stop=None
    for slot in plan['sequence']:
        if stop:records.append(dict(slot,status='not_run',reason=stop))
        else:
            actor=None;folder=None;began=time.perf_counter_ns()
            try:
                folder,install,actor,_=prepare(slot['cell'],slot['group'],slot['task'])
                prompt=Path(plan['session_rules']).read_bytes()+b'\n'+Path(plan['tasks'][slot['task']]['prompt']).read_bytes()
                assert __import__('hashlib').sha256(prompt).hexdigest()==plan['tasks'][slot['task']]['model_input_sha256']
                consumer=transport.consume(dict(slot,version=slot['group']),install,plan,prompt)
                closed=finish(folder,actor);actor=None
                consumer.update(owner_finish=closed,total_task_wall_ns=time.perf_counter_ns()-began,pre_consumer_setup_ns=consumer['started_ns']-began)
                save(folder/'CONSUMER.json',consumer)
                records.append(dict(slot,status=consumer['status'],model_completed=consumer['valid_completion'],owner_confirmed=closed['confirmed'],
                    prompt_to_final_ns=consumer['prompt_to_final_ns'],total_task_wall_ns=consumer['total_task_wall_ns'],usage=consumer['usage']))
                if not closed['confirmed']:stop='unconfirmed_readonly_backend_or_geometry'
                elif consumer['exit_code']!=0 or consumer['errors']:
                    diagnostics=(folder/'stderr.raw.bin').read_text(encoding='utf8',errors='replace')+json.dumps(consumer['errors'])
                    if any(s in diagnostics.lower() for s in ('insufficient_quota','usage limit','quota exceeded','authentication','unauthorized','login required','permission denied','rate limit reached')):stop='shared_auth_quota_or_permission_block'
            except BaseException as exc:
                records.append(dict(slot,status='failed',error=repr(exc)));stop='runtime_error'
                if actor is not None and folder is not None:finish(folder,actor)
        save(HERE/'RUN_RESULT.json',{'cycle_id':plan['cycle_id'],'denominator':18,'cells':records,'stop_reason':stop})
    save(HERE/'RUN_RESULT.json',{'cycle_id':plan['cycle_id'],'denominator':18,'cells':records,'stop_reason':stop,'ended_ns':time.perf_counter_ns()})
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--preflight-output',type=Path);parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if args.preflight:preflight(args.preflight_output.resolve() if args.preflight_output else None)
    elif args.run:run()
    else:prepare_plan()
