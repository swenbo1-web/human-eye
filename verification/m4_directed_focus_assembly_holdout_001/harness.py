"""One frozen, no-retry holdout on an existing installed directed-focus runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback

BATCH='M4-DIRECTED-FOCUS-ASSEMBLY-HOLDOUT-001'
ADMIN='30c6e127ff5c484e7b6bfc28aecd3b8ef106affdccde7553e5c6a9de49cee7ea'
LABELS='03f11dae6aff1428cff5e751c959900a6be1ddaed5d6d29c05290519e991b39e'
PRODUCT='e98ad951d554179c9b9fd3024013d1a875acbe84'
SOURCE='00ba6e251415847878e7ed028a5ba704f6e8ee6ba4bd567dd3fea0e8076bb72e'
WHEEL='4d60f9eac3f3791f883eed8bf6c31e1b37a8a0618458d386cb66804a29719358'
PYTHON='b95409b2edc04f3db3f2a5021fa52d2e0791ae978c13cdeb857cab0f35476919'
BLENDER='284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
ORDER=('RAIL_AUTO','RAIL_EXPLICIT','ASSEMBLY_AUTO','ASSEMBLY_EXPLICIT')
TOPICS={'RAIL':('M19','M21'),'ASSEMBLY':('N19','N25')}
LIMIT_NS=190_000_000_000
MAX_LINE=64*1024*1024


def need(value,reason):
    if not value:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')


def pin(path):
    resolved=Path(path).resolve(strict=True)
    return {'path':str(resolved),'sha256':digest(resolved),'bytes':resolved.stat().st_size}


def confirm(expected):
    need(pin(expected['path'])=={key:expected[key] for key in ('path','sha256','bytes')},
         'frozen_file_mismatch')
    return Path(expected['path'])


def prepare(root):
    admin=root/'preflight/ADMIN_PLAN.md'
    labels=root/'preflight/FROZEN_TASK_LABELS.json'
    custody=root/'preflight/INSTALL_CUSTODY.json'
    need(root.name==BATCH and digest(admin)==ADMIN and sys.flags.isolated and sys.dont_write_bytecode,
         'wrong_plan_or_interpreter')
    need(digest(labels)==LABELS,'frozen_task_label_digest_changed')
    tag=read(labels)
    installed=read(custody)
    need(installed['passed'] and installed['candidate_commit']==PRODUCT and installed['source_sha256']==SOURCE
         and installed['runtime_sources']==146,'wrong_frozen_product')
    for key,wanted in (('wheel',WHEEL),('blender',BLENDER),('python',PYTHON),('build',None)):
        p=installed[key]
        confirm(p)
        if wanted is not None:
            need(p['sha256']==wanted,'wrong_wheel_blender_or_interpreter_digest')
    need(Path(sys.executable).resolve()==Path(installed['python']['path']),'wrong_prior_runtime')
    site=Path(installed['installation']['path']).resolve(strict=True)
    need(site.is_dir(),'candidate_installation_missing')
    need(tuple(tag['task_order'])==('M19','M21','N19','N25'),'wrong_frozen_topic_order')
    jobs={}
    for slot in ORDER:
        asset,arm=slot.split('_')
        a=tag['assets'][asset.lower()]
        source=pin(a['asset']['path'])
        need(all(source[k]==a['asset'][k] for k in ('bytes','sha256')),'asset_changed')
        expected='f5469ae8' if asset=='RAIL' else '91129d2e'
        need(source['sha256'].startswith(expected),'unexpected_holdout_asset')
        jobs[slot]={'asset':asset,'arm':arm.lower(),'fixture':source,'requests':[]}
        for index,label in enumerate(TOPICS[asset],3):
            row=tag['tasks'][label]
            explicit=row['explicit_source_triangle_index']
            need(row['target']==label and row['asset']==asset.lower()
                 and type(explicit) is int and explicit in row['source_triangle_indices'],'bad_frozen_source_row')
            focus='auto' if arm=='AUTO' else {'source_triangle_index':explicit}
            arguments={'query':{'mode':'active_observation','objects':[{'name':label}],'focus':focus},
                       'include_image':True,'response_detail':'full'}
            jobs[slot]['requests'].append({'id':index,'label':label,'arguments':arguments})
    return {'batch':BATCH,'order':list(ORDER),'jobs':jobs,
            'inputs':[pin(x) for x in (admin,labels,custody,Path(__file__))],
            'candidate_site':str(site),'blender':installed['blender'],'python':installed['python'],
            'candidate_source_sha256':SOURCE,'two_new_rasters_limit_per_request':2}


def frozen(root):
    value=read(root/'preflight/FROZEN_EXECUTION.json')
    need(value==prepare(root),'execution_freeze_changed')
    return value


class AtReservation(Exception):
    pass


class Launch:
    """Reserve one actual installed-host process launch, or stop at that call."""
    def __init__(self,folder,mode,settings,fixture):
        self.folder,self.mode,self.settings,self.fixture=folder,mode,settings,fixture
        self.process=None
        self.called=False

    def __getattr__(self,name):
        return getattr(subprocess,name)

    def Popen(self,command,*args,**options):
        need(not self.called and not args and options.get('shell') is False,
             'second_or_unrecognized_blender_launch')
        self.called=True
        need(command[:5]==[self.settings['blender']['path'],'--factory-startup','--disable-autoexec',
                          '--background',str(self.fixture)]
            and command[5]=='--python-expr' and command[-2:]==['--',self.settings['candidate_site']]
            and options.get('creationflags',0) & getattr(subprocess,'CREATE_NO_WINDOW',0),
             'owned_black_box_launch_contract')
        recipe={'command_sha256':sha(json.dumps(command,ensure_ascii=True,separators=(',',':')).encode()),
                'bootstrap_sha256':sha(command[6].encode()),'fixture':pin(self.fixture),
                'at_ns':time.perf_counter_ns(),'attempt':self.mode=='formal','python_pid':os.getpid(),
                'headless_autoexec_disabled':True,'geometry_preflight_reads':0}
        if self.mode=='cold':
            save(self.folder/'AT_APPOINTMENT.json',recipe)
            raise AtReservation()
        save(self.folder/'Blender_RESERVATION.json',recipe)
        self.process=subprocess.Popen(command,**options)
        save(self.folder/'Blender_SPAWN.json',{'pid':self.process.pid,'started_ns':time.perf_counter_ns()})
        return self.process


def copied_input(folder,job):
    fixture=folder/'input.blend'
    original=confirm(job['fixture'])
    if not fixture.is_file():
        shutil.copyfile(original,fixture)
        fixture.chmod(0o444)
    need(digest(fixture)==job['fixture']['sha256'],'not_the_pinned_asset_copy')
    return fixture


def emit_focus_source(service, folder, expected):
    from human_eye_plugin import active_observation_images

    handle=service._observe_active_observation
    raster=active_observation_images.rasterize_attention
    active=None
    admitted=set()

    def guarded(*args,**kwargs):
        nonlocal active
        need(active is not None,'unregistered_actual_raster')
        if len(active['raster_calls'])>=2:
            active['limit_exceeded']=True
            raise ValueError('holdout_two_actual_rasters_limit')
        stamp={'started_ns':time.perf_counter_ns(),'completed':False}
        active['raster_calls'].append(stamp)
        try:
            result=raster(*args,**kwargs)
            stamp['completed']=True
            return result
        finally:
            stamp['closed_ns']=time.perf_counter_ns()

    def observed(session_id,*,include_image,selector=None,task_query=None,region_task=None,focus=None):
        nonlocal active
        key,=[x for x in expected if x['arguments']['query']['objects']==[selector]]
        need(active is None and key['id'] not in admitted and include_image is True
             and task_query is None and region_task is None
             and focus==key['arguments']['query']['focus'],'unregistered_or_repeated_focus_tool_call')
        admitted.add(key['id'])
        event={'id':key['id'],'label':key['label'],'service_started_ns':time.perf_counter_ns(),
               'raster_calls':[],'limit_exceeded':False}
        active=event
        try:
            value=handle(session_id,include_image=include_image,selector=selector,focus=focus)
            event['service_returned_ns']=time.perf_counter_ns()
            save(folder/f"producer_{key['id']:02d}.json",value)
            event['result_recorded']=True
            return value
        finally:
            event.setdefault('service_returned_ns',time.perf_counter_ns())
            active=None
            save(folder/f"construction_{key['id']:02d}.json",event)

    service._observe_active_observation=observed
    active_observation_images.rasterize_attention=guarded
    return raster,active_observation_images


def product_runtime(settings):
    site=Path(settings['candidate_site'])
    sys.path.insert(0,str(site))
    from human_eye_plugin import blender_process
    from human_eye_plugin.runtime_identity import runtime_identity
    ident=runtime_identity()
    need(Path(blender_process.__file__).resolve().parent.parent==site
         and ident['source_sha256']==SOURCE and len(ident['source_files'])==146
         and ident['source_kind']=='installed_distribution','actual_installed_handler_not_frozen')
    return blender_process,ident


def serve(root,slot,mode):
    settings=frozen(root)
    job=settings['jobs'][slot]
    folder=(root/'slots'/slot) if mode=='formal' else (root/'preflight/cold'/slot)
    if mode=='formal':
        launch=read(root/'FORMAL_START.json')
        registered=read(folder/'REGISTERED.json')
        need(launch['freeze']==pin(root/'preflight/FROZEN_EXECUTION.json')
             and registered['slot']==slot and registered['planned']==job['requests'],
             'formal_child_without_registered_parent')
    fixture=copied_input(folder,job)
    module,ident=product_runtime(settings)
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server

    config=folder/'config.json'
    save(config,{'schema_version':'1.0','enabled':True,'project_root':str(folder),
                 'state_file':'state.json','audit_file':'audit.jsonl','request_budget_s':30,
                 'expected_identity':{'source_sha256':SOURCE}})
    launched=Launch(folder,mode,settings,fixture)
    real=module.subprocess
    module.subprocess=launched
    host=None
    caught=None
    post=None
    t0=time.perf_counter_ns()
    try:
        try:
            host=module.BlenderProcessHost(settings['blender']['path'],fixture,timeout=25,startup_timeout=45)
        except AtReservation:
            need(mode=='cold' and launched.process is None,'unreal_cold_boundary')
            return 0
        need(mode=='formal' and launched.process is host._process,'wrong_owned_blender_handle')
        service=LiveSpatialService(config,host=host,production_mode=True)
        save(folder/'ready.json',{'pid':host._process.pid,'startup_ns':time.perf_counter_ns()-t0,
             'source_sha256':SOURCE,'source_files':len(ident['source_files']),'source_kind':ident['source_kind'],
             'fixture_before':digest(fixture),'asset':job['asset'],'arm':job['arm']})

        def finish():
            nonlocal post
            before=time.perf_counter_ns()
            value=host.capture_scene()
            end=time.perf_counter_ns()
            save(folder/'post_capture.json',value)
            post={'started_ns':before,'closed_ns':end,'path':pin(folder/'post_capture.json')}
            # The finally block below owns closure regardless of EOF/capture status.

        service.close=finish
        original,images=emit_focus_source(service,folder,job['requests'])
        try:
            run_stdio_mcp_server(service)
        finally:
            images.rasterize_attention=original
    except BaseException as failure:
        caught=type(failure).__name__+': '+str(failure)
        raise
    finally:
        module.subprocess=real
        if mode=='formal':
            close_started=time.perf_counter_ns()
            try:
                if host is not None:
                    host.close()
                elif launched.process is not None and launched.process.poll() is None:
                    launched.process.terminate()
                    try:
                        launched.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        launched.process.kill()
                        launched.process.wait(timeout=3)
            finally:
                p=launched.process
                save(folder/'closed.json',{'pid':p.pid if p else None,
                     'blender_exit':p.poll() if p else None,'native_spawned':p is not None,
                     'fixture_after':digest(fixture),'closed_ns':time.perf_counter_ns(),
                     'native_close_started_ns':close_started,'post_capture':post,'failure':caught})
    return 0


def process_env():
    return dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')


def child_args(root,slot,mode):
    return [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),str(root),'worker',slot,mode]


def cold_slots(root):
    settings=frozen(root)
    gates=[]
    for slot in settings['order']:
        folder=root/'preflight/cold'/slot
        folder.mkdir(parents=True,exist_ok=False)
        result=subprocess.run(child_args(root,slot,'cold'),cwd=folder,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=process_env(),
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=40)
        (folder/'stdout.bin').write_bytes(result.stdout)
        (folder/'stderr.bin').write_bytes(result.stderr)
        result.check_returncode()
        mark=read(folder/'AT_APPOINTMENT.json')
        need(not mark['attempt'] and mark['geometry_preflight_reads']==0 and not result.stdout
             and not (folder/'Blender_SPAWN.json').exists(),'cold_already_launched')
        gates.append({'slot':slot,'receipt':pin(folder/'AT_APPOINTMENT.json'),'exit':result.returncode})
    save(root/'preflight/COLD_GATES.json',{'passed':True,'freeze':pin(root/'preflight/FROZEN_EXECUTION.json'),
        'actual_blender':0,'gates':gates})


def audit_size(folder):
    path=folder/'audit.jsonl'
    if not path.is_file():
        return 0
    return sum(json.loads(line).get('event')=='active_observation_render_attempt'
               for line in path.read_bytes().splitlines())


def sequence(job):
    yield ('init','initialize',{'protocolVersion':'2024-11-05','capabilities':{},
          'clientInfo':{'name':'directed-focus-assembly-holdout','version':'1'}})
    yield ('tools','tools/list',{})
    for row in job['requests']:
        yield (row['label'],'tools/call',{'name':'human_eye_scene_observe','arguments':row['arguments']})


def run_slot(root,slot,settings):
    job=settings['jobs'][slot]
    folder=root/'slots'/slot
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/'REGISTERED.json',{'slot':slot,'planned':job['requests'],'allocated':time.perf_counter_ns()})
    copied_input(folder,job)
    records=[]
    issues=[]
    began=time.perf_counter_ns()
    code=None
    with (folder/'stderr.log').open('xb') as stderr:
        child=subprocess.Popen(child_args(root,slot,'formal'),cwd=folder,stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,stderr=stderr,env=process_env(),
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        lines=queue.Queue()
        eof=threading.Event()

        def receive():
            try:
                while True:
                    line=child.stdout.readline(MAX_LINE+1)
                    if not line:
                        eof.set()
                        lines.put(None)
                        return
                    if len(line)>MAX_LINE:
                        lines.put(ValueError('stdout_line_budget'))
                        return
                    lines.put(line)
            except BaseException as failure:
                lines.put(failure)

        reader=threading.Thread(target=receive,daemon=True)
        try:
            reader.start()
            for index,(label,method,params) in enumerate(sequence(job),1):
                tx=(json.dumps({'jsonrpc':'2.0','id':index,'method':method,'params':params},
                               separators=(',',':'),allow_nan=False)+'\n').encode('utf8')
                prefix=folder/f'{index:02d}-{label}'
                prefix.with_suffix('.tx').write_bytes(tx)
                before=audit_size(folder)
                started=time.perf_counter_ns()
                row={'id':index,'label':label,'tx':len(tx),'tx_sha':sha(tx),'started_ns':started,
                     'render_attempts_before':before,'status':'dispatch_started'}
                records.append(row)
                child.stdin.write(tx)
                child.stdin.flush()
                ttl=(began+LIMIT_NS-time.perf_counter_ns())/1e9
                need(ttl>0,'whole_slot_window_expired')
                rx=lines.get(timeout=min(80,ttl))
                returned=time.perf_counter_ns()
                if isinstance(rx,BaseException):
                    raise rx
                need(rx is not None,'early_stdio_EOF')
                prefix.with_suffix('.rx').write_bytes(rx)
                row.update(rx=len(rx),rx_sha=sha(rx),returned_ns=returned,rtt_ms=(returned-started)/1e6,
                           render_attempts_after=audit_size(folder))
                reply=json.loads(rx)
                need(reply.get('id')==index and reply.get('jsonrpc')=='2.0','wrong_stdio_response')
                result=reply.get('result')
                if method=='tools/call' and (not isinstance(result,dict) or result.get('isError') is True):
                    row['status']='failed'
                    issues.append({'label':label,'reason':'product_error_response'})
                    continue
                need(isinstance(result,dict),'bad_actual_stdout_result')
                if method=='initialize':
                    need(result['_meta']['human_eye']['source_sha256']==SOURCE,'wrong_MCP_source_identity')
                if method=='tools/list':
                    tool,=[x for x in result['tools'] if x['name']=='human_eye_scene_observe']
                    need('focus' in tool['inputSchema']['properties']['query']['properties'],'missing_production_focus_schema')
                if method=='tools/call':
                    construction=read(folder/f'construction_{index:02d}.json')
                    need(construction['id']==index and len(construction['raster_calls'])<=2
                         and not construction['limit_exceeded'],'wrong_native_construction_limit')
                    row['new_rasters']=len(construction['raster_calls'])
                    row['service_ms']=(construction['service_returned_ns']-construction['service_started_ns'])/1e6
                row['status']='returned'
        except BaseException as failure:
            issues.append({'reason':type(failure).__name__+': '+str(failure),'traceback':traceback.format_exc()})
        finally:
            child.stdin.close()
            try:
                code=child.wait(timeout=48)
            except subprocess.TimeoutExpired:
                issues.append({'reason':'stdio_graceful_exit_timeout'})
                child.kill()
                code=child.wait(timeout=8)
            reader.join(timeout=3)
            child.stdout.close()
    closed=read(folder/'closed.json') if (folder/'closed.json').is_file() else None
    safe=closed is not None and (
        closed['blender_exit'] is not None or not closed['native_spawned'])
    admitted={x['label'] for x in records}
    unrun=[x['label'] for x in job['requests'] if x['label'] not in admitted]
    good=(not issues and not unrun and code==0 and eof.is_set() and safe
          and closed['blender_exit']==0 and closed['post_capture'] is not None)
    ledger={'slot':slot,'arm':job['arm'],'asset':job['asset'],'requests':records,'server_exit':code,
            'stdout_eof':eof.is_set(),'fixture_sha':job['fixture']['sha256'],'started_ns':began,
            'closed_ns':time.perf_counter_ns(),'status':'closed' if good else 'failed',
            'issues':issues,'unrun':unrun,'safe_to_continue':safe}
    save(folder/'ledger.json',ledger)
    return ledger


def formal(root):
    settings=frozen(root)
    gate=read(root/'preflight/COLD_GATES.json')
    need(gate['passed'] and gate['actual_blender']==0 and gate['freeze']==pin(root/'preflight/FROZEN_EXECUTION.json')
         and [x['slot'] for x in gate['gates']]==settings['order'],'cold_qualification_not_bound')
    for row in gate['gates']:
        confirm(row['receipt'])
    save(root/'FORMAL_START.json',{'order':settings['order'],'freeze':gate['freeze'],
                                 'started_ns':time.perf_counter_ns(),'max_Blender':4,'max_business':8})
    (root/'slots').mkdir(exist_ok=False)
    ledger=[]
    try:
        for slot in settings['order']:
            try:
                result=run_slot(root,slot,settings)
            except BaseException as failure:
                ledger.append({'slot':slot,'status':'error','error':str(failure),'traceback':traceback.format_exc()})
                break
            ledger.append(result)
            if not result['safe_to_continue']:
                break
    finally:
        closed={row['slot']:row for row in ledger}
        save(root/'FORMAL_EXECUTION.json',{'slots':ledger,
             'unrun_slots':[x for x in ORDER if x not in closed],'closed_ns':time.perf_counter_ns(),
             'substitutes':0,'models':0})
    return int(len(ledger)!=4 or any(x['status']!='closed' for x in ledger))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda x:Path(x).resolve(strict=True))
    parser.add_argument('action',choices=('freeze','cold','formal','worker'))
    parser.add_argument('slot',nargs='?',choices=ORDER)
    parser.add_argument('mode',nargs='?',choices=('formal','cold'))
    args=parser.parse_args()
    if args.action=='freeze':
        save(args.root/'preflight/FROZEN_EXECUTION.json',prepare(args.root))
    elif args.action=='cold':
        cold_slots(args.root)
    elif args.action=='formal':
        raise SystemExit(formal(args.root))
    else:
        need(args.slot and args.mode,'worker_requires_fixed_slot_and_mode')
        raise SystemExit(serve(args.root,args.slot,args.mode))
