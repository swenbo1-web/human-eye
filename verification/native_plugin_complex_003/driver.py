"""One fixed nine-consumer Latin trial, holding backends outside CLI lifetime."""
import argparse,hashlib,importlib.util,json,os,socket,subprocess,sys,time,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def prepare(cell,group):
    folder=HERE/'cells'/cell;folder.mkdir(parents=True,exist_ok=False)
    version='A' if group=='N' else group
    install=read(ROOT/'verification/plugin_version_llm_ab_001/INSTALL_RESULT.json')['versions'][version]
    start=time.perf_counter_ns()
    config={'group':group,'output':str(folder/'owner'),'endpoint':str(folder/'ENDPOINT.json'),
        'asset':str(HERE/'scene.blend'),'asset_sha256':sha(HERE/'scene.blend'),
        'blender':'D:/Tools/blender5.2/blender.exe','worker_deadline_ns':start+570*10**9,
        'install_root':install['installed_root'],'source_sha256':install['proof']['runtime_identity']['source_sha256']}
    save(folder/'ACTOR_CONFIG.json',config)
    actor=subprocess.Popen([install['python'],'-I','-B',str(HERE/'actor.py'),'--config',str(folder/'ACTOR_CONFIG.json')],
        stdin=subprocess.PIPE,stdout=(folder/'actor_stdout.bin').open('wb'),stderr=(folder/'actor_stderr.bin').open('wb'),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.perf_counter()+40
    while not (folder/'ENDPOINT.json').exists():
        if actor.poll() is not None:raise RuntimeError('actor_start_failed:'+str(folder))
        if time.perf_counter()>deadline:actor.kill();actor.wait();raise TimeoutError('actor_startup_40s')
        time.sleep(.05)
    save(folder/'cell.json',{'endpoint':str(folder/'ENDPOINT.json'),'audit_dir':str(folder/'owner')})
    return folder,install,actor,start

def finish(folder,actor):
    start=time.perf_counter_ns()
    if actor.poll() is None:actor.stdin.write(b'finish\n');actor.stdin.close()
    try:actor.wait(timeout=45)
    except subprocess.TimeoutExpired:actor.kill();actor.wait(timeout=5)
    close=read(folder/'owner/CLOSE.json') if (folder/'owner/CLOSE.json').exists() else {'confirmed':False}
    result={'actor_pid':actor.pid,'actor_exit':actor.returncode,'close':close,'finish_elapsed_ns':time.perf_counter_ns()-start,
        'confirmed':actor.returncode==0 and close.get('confirmed',False)}
    save(folder/'OWNER_FINISH.json',result);return result

def preflight():
    folder,install,actor,start=prepare('preflight','A');reply=[]
    client=load('_thin_attach',HERE/'reused/stdio_attach.py')
    endpoint=read(folder/'ENDPOINT.json')
    try:
        for n,name,args in [(1,'execute_blender_code',{'code':"print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'])"}),
            (2,'human_eye_spatial_relations',{'target':{'name':'Object_01'},'candidates':[{'name':n} for n in ('Object_02','Object_03','Object_04')],'include_aabb':True})]:
            reply.append(client.attach(endpoint,'native',{'jsonrpc':'2.0','id':n,'method':'tools/call','params':{'name':name,'arguments':args}}))
        save(folder/'PREFLIGHT_REPLIES.json',reply)
    finally:closed=finish(folder,actor)
    assert closed['confirmed'],closed
    initial=read(folder/'owner/INITIAL.json');expected=read(HERE/'private/author_mesh_snapshots.json')['initial']
    fields=('name','vertices_local','matrix_world','faces')
    assert [{k:o[k] for k in fields} for o in initial['objects']]==[{k:o[k] for k in fields} for o in expected['objects']]
    assert all(not r.get('result',{}).get('isError') for r in reply),reply
    save(HERE/'PREFLIGHT.json',{'passed':True,'model_calls':0,'groups':'A, common native protocol plus installed spatial entry',
        'scene_matches_frozen_oracle':True,'finish':closed,'wall_ns':time.perf_counter_ns()-start})
    print(json.dumps({'preflight':True,'model_calls':0,'closed':closed['confirmed']}),flush=True)

def run():
    plan=read(HERE/'PLAN.json')
    for name,digest in read(HERE/'FREEZE.json').items():assert sha(HERE/name)==digest,name
    claim=HERE/'STARTED.json'
    with claim.open('x') as f:json.dump({'started_ns':time.perf_counter_ns(),'max_consumers':9},f)
    transport=load('_transport',HERE/'consumer_transport.py')
    assert sha(transport.EXE)==plan['CLI_sha256']
    records=[];stop=None;prompt=(HERE/'PROMPT.txt').read_bytes()
    for slot in plan['sequence']:
        if stop:records.append(dict(slot,status='not_run',reason=stop))
        else:
            actor=None;began=time.perf_counter_ns();folder=None
            try:
                folder,install,actor,actor_start=prepare(slot['cell'],slot['group'])
                consumer=transport.consume(dict(slot,version=slot['group'],task='assembly_initial'),install,plan,prompt)
                closed=finish(folder,actor);actor=None
                consumer.update(owner_finish=closed,total_task_wall_ns=time.perf_counter_ns()-began,
                    pre_consumer_setup_ns=consumer['started_ns']-began)
                save(folder/'CONSUMER.json',consumer)
                records.append(dict(slot,status=consumer['status'],model_completed=consumer['valid_completion'],
                    owner_confirmed=closed['confirmed'],prompt_to_final_ns=consumer['prompt_to_final_ns'],
                    total_task_wall_ns=consumer['total_task_wall_ns'],usage=consumer['usage']))
                if not closed['confirmed']:stop='unconfirmed_readonly_backend_or_geometry'
                elif consumer['exit_code']!=0 or consumer['errors']:
                    diagnostics=(folder/'stderr.raw.bin').read_text(encoding='utf8',errors='replace')
                    diagnostics+=json.dumps(consumer['errors'])
                    if any(s in diagnostics.lower() for s in ('insufficient_quota','usage limit','quota exceeded',
                            'authentication','unauthorized','login required','permission denied','rate limit reached')):
                        stop='shared_auth_quota_or_permission_block'
                    # A failed independent cell is retained, not retried.
                    # Confirmed readonly cleanup permits the next frozen cell.
            except BaseException as e:
                records.append(dict(slot,status='failed',error=repr(e)));stop='runtime_error'
                if actor is not None and folder is not None:finish(folder,actor)
        save(HERE/'RUN_RESULT.json',{'cycle_id':plan['cycle_id'],'denominator':9,'cells':records,'stop_reason':stop})
        print(json.dumps(records[-1],ensure_ascii=False),flush=True)
    save(HERE/'RUN_RESULT.json',{'cycle_id':plan['cycle_id'],'denominator':9,'cells':records,'stop_reason':stop,'ended_ns':time.perf_counter_ns()})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    preflight() if args.preflight else run()
