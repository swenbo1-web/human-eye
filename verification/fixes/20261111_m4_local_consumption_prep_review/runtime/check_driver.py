"""No-process wiring audit. run_models is never invoked; all Popen calls are mocked."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import types
from unittest.mock import patch

W=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=W/'verification/m4_local_relation_consumption_001'
OLD=W/'verification/m4_observation_baseline_001'
O=Path(__file__).resolve().parent
HEAD='169b0be061e91b126f46313478690564ccb2bd60'
checks=[];rows=[];hashes={};mock_popen=[];unexpected=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def check(name,ok):checks.append({'check':name,'passed':bool(ok)});assert ok,name
def load(name,p):
    raw=p.read_bytes();rel=p.relative_to(W).as_posix()
    expected=subprocess.run(['git','-C',str(W),'show',HEAD+':'+rel],check=True,capture_output=True).stdout
    check(name+'_fixed_Git_bytes',raw==expected);hashes[rel]=sha(p)
    # These two modules only define functions/constants at import.
    m=types.ModuleType(name);m.__file__=str(p);exec(compile(raw,str(p),'exec'),m.__dict__);return m

plan=read(B/'PLAN.json')
driver=load('driver',B/'runtime/driver.py')
transport=load('transport',B/'runtime/consumer_transport.py')
check('actual_new_transport_batch_directory',transport.HERE==B and driver.HERE==B)
check('actor_and_transport_identical_to_accepted_baseline',all((B/rel).read_bytes()==(OLD/rel).read_bytes() for rel in ('runtime/actor.py','runtime/consumer_transport.py')))
check('original_time_contracts',(plan['max_session_seconds'],plan['total_cell_seconds'],plan['actor_startup_seconds'])==(450,570,40))
check('formal_GO_STARTED_not_created',not(B/'GO.json').exists() and not(B/'STARTED.json').exists())
fresh=[]
for slot in plan['sequence']:
    folder=transport.ROOT/'.m4_observation_baseline_001_runtime/work'/slot['cell']
    fresh.append(not folder.exists() or not any(folder.iterdir()))
check('all_nine_original_transport_workspaces_fresh',len(fresh)==9 and all(fresh))

# Execute the real prepare function with filesystem confined to an independent
# copy and its only process-launch boundary replaced by an in-memory fake.
virtual=O/'synthetic_batch';virtual.mkdir(parents=True,exist_ok=False)
required=['PLAN.json','installations/P0_READY.json','installations/P1_READY.json','schemas/P0_PUBLIC_TOOLS.json','schemas/P1_PUBLIC_TOOLS.json',plan['inputs']['scene'],plan['inputs']['image']]
for rel in required:
    dest=virtual/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((B/rel).read_bytes())
driver.HERE=virtual;transport.HERE=virtual;transport.ROOT=O/'synthetic_project'

class FakeActor:
    def __init__(self,command,**kwargs):
        self.pid=900000+len(mock_popen);self.stdin=io.BytesIO();self.returncode=None
        cfg=read(command[-1]);out=Path(cfg['output']);out.mkdir(parents=True)
        save(out/'CLOSE.json',{'confirmed':True,'synthetic':True})
        save(Path(cfg['endpoint']),{'host':'127.0.0.1','port':1,'chain_deadline_ns':cfg['worker_deadline_ns'],'actor_pid':self.pid})
        mock_popen.append({'kind':'synthetic_actor','command':command,'config':cfg})
    def poll(self):return self.returncode
    def wait(self,timeout=None):self.returncode=0;return 0
    def kill(self):raise AssertionError('no kill should be needed')

class FakeTimer:
    def __init__(self,*args,**kwargs):self.daemon=False
    def start(self):pass
    def cancel(self):pass
    def join(self,timeout=None):pass

class StopBeforeCLI(Exception):pass
def block_cli(argv,**kwargs):
    mock_popen.append({'kind':'synthetic_CLI_boundary','argv':argv})
    raise StopBeforeCLI('audit_only_no_process_created')
def forbidden(*args,**kwargs):
    unexpected.append('unexpected_subprocess_run');raise AssertionError('external operation forbidden')

for slot in plan['sequence']:
    original=copy.deepcopy(slot);internal,ready,profile=driver.arm_runtime(plan,slot)
    start=10**9
    with patch.object(driver.subprocess,'Popen',side_effect=FakeActor),patch.object(driver.subprocess,'run',side_effect=forbidden),patch.object(driver.time,'perf_counter_ns',return_value=start):
        folder,proc,began=driver.prepare(slot,output=virtual/'cells'/slot['cell'],cell_started_ns=start)
    config=read(folder/'ACTOR_CONFIG.json');cell=read(folder/'cell.json');launch=read(folder/'ACTOR_LAUNCH.json')
    check(slot['cell']+'_real_prepare_mapping',slot==original and config['group']==internal['group']==cell['group'] and config['external_group']==slot['group']==cell['external_group'])
    expected_schema=[] if slot['group']=='N' else read(B/'schemas'/(profile+'_PUBLIC_TOOLS.json'))
    check(slot['cell']+'_selected_install_and_schema',config['read_schemas']==expected_schema and config['entry']==(None if slot['group']=='N'else ready['entry']) and config['source_sha256']==(None if slot['group']=='N'else ready['source_sha256']) and config['install_root']==(None if slot['group']=='N'else ready['install_root']))
    check(slot['cell']+'_original_actor_deadlines',launch['cell_started_ns']==start and launch['worker_deadline_ns']==start+570*10**9 and launch['actor_startup_deadline_ns']==start+40*10**9)
    # The actual consume reads this generated cell.json, computes argv, creates
    # and persists its real record, then hits the substituted Popen boundary.
    # It takes its normal exception/finally path without a CLI, reader or timer.
    with patch.object(transport.subprocess,'Popen',side_effect=block_cli),patch.object(transport.subprocess,'run',side_effect=forbidden),patch.object(transport.threading,'Timer',FakeTimer):
        consumer=transport.consume(internal,{'python':ready['dependency_python']},plan,b'synthetic audit prompt; never delivered')
    check(slot['cell']+'_actual_consumer_external_identity',consumer['cell']==slot['cell'] and consumer['group']==internal['group'] and consumer['external_group']==slot['group'] and consumer['consumer_pid'] is None and any(e.get('type')=='StopBeforeCLI' for e in consumer['errors']))
    check(slot['cell']+'_consumer_record_location',read(folder/'CONSUMER.json')==consumer)
    config_args=[consumer['argv'][i+1]for i,x in enumerate(consumer['argv'])if x=='-c']
    mcp_arg=next(x for x in config_args if x.startswith('mcp_servers.arm_engine='))
    check(slot['cell']+'_same_cell_endpoint_attachment_and_tools',json.dumps(str(folder/'ENDPOINT.json')) in mcp_arg and json.dumps(str(folder/'attachments')) in mcp_arg and all(json.dumps(n)in mcp_arg for n in consumer['expected_tool_names']))
    check(slot['cell']+'_450_consumer_deadline',consumer['deadline_ns']-consumer['started_ns']==450*10**9)
    with patch.object(driver.subprocess,'run',side_effect=forbidden):finished=driver.finish(folder,proc)
    check(slot['cell']+'_finish_reaps_own_actor',finished['confirmed'] and finished['actor_pid']==proc.pid and finished['exit_code']==0)
    rows.append({'cell':slot['cell'],'external_group':slot['group'],'internal_group':internal['group'],'installation_profile':profile,'source_sha256':config['source_sha256'],'schema_sha256':None if slot['group']=='N'else sha(B/'schemas'/(profile+'_PUBLIC_TOOLS.json')),'consumer_record_group':consumer['group'],'consumer_external_group':consumer['external_group'],'endpoint_relative':Path(cell['endpoint']).relative_to(virtual).as_posix(),'process_created':False})

digest=sha(B/'PLAN.json');validgo={'task':driver.CYCLE,'authorized':True,'plan_sha256':digest,'max_consumers':9}
driver.go_contract(validgo,plan,digest)
check('GO_nine_new_cycle_accepted_by_contract',True)
rejections=[]
for name,go,p in (
    ('actual_old_six_GO',read(OLD/'GO.json'),plan),
    ('new_cycle_six_max',{**validgo,'max_consumers':6},plan),
    ('wrong_plan_hash',{**validgo,'plan_sha256':'0'*64},plan),
    ('old_cell_names',validgo,{**plan,'sequence':[{**r,'cell':str(i+1).zfill(2)}for i,r in enumerate(plan['sequence'])]}),
    ('reordered_groups',validgo,{**plan,'sequence':[plan['sequence'][1],plan['sequence'][0],*plan['sequence'][2:]]})):
    try:driver.go_contract(go,p,digest)
    except AssertionError:rejections.append(name)
check('five_invalid_GO_sequence_cases_rejected',len(rejections)==5)
check('no_external_subprocess_operation',not unexpected and len(mock_popen)==18)
check('formal_files_still_absent',not(B/'GO.json').exists() and not(B/'STARTED.json').exists() and not(B/'cells').exists())
result={'status':'pass','fixed_head':HEAD,'checks':checks,'wiring':rows,'rejections':rejections,'source_hashes':hashes,'real_processes_started':0,'model_consumers':0,'Blender_sessions':0,'run_models_invocations':0,'scope':'Actual fixed driver prepare with mocked Popen and relocated output only; actual transport consume through generated cell/argv/record to an injected pre-process exception, then normal cleanup. Not a real preparation or consumer run. Real actor source/schema checks reviewed statically.','limits':['No live tools/list or initialized source rerun.','No timed live process or timeout experiment.','Stop-loop code inspected against accepted old source; run_models not invoked.']}
dest=O/'DRIVER_WIRING_REVIEW.json'
with dest.open('x',encoding='utf-8')as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'pass','checks':len(checks),'wiring_slots':len(rows),'real_processes':0,'report_sha256':sha(dest)}))
