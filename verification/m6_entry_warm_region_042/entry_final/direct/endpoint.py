"""Owned ordinary G60 endpoint and direct production stdio controls; no host dispatch."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
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
import uuid

HERE=Path(__file__).resolve().parent
VER=HERE.parents[2]
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/direct')
BASE=Path('D:/HumanEye/runs/M6-041-KERNEL-HOOK')
PYTHON=Path('D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe')
SITE=BASE/'install/r3/.human-eye/releases/9.7.2+k041hookr3/site-packages'
ENTRY=SITE.parent/'admin/target_runtime_entry.py'
SOURCE='ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e'
ASSET=Path('D:/he_b32g_release_acceptance/matrix/B_G60_D12/native/input.blend')
ASSET_SHA='9bba515e72bcbd307d3b41b42d426e253d9da56b1723c0da21663b3653bb7cd8'
CONFIG=RAW/'CONFIG.json'
PORT=48142
CYCLE='M6-042-E-FINAL-DIRECT'


def need(ok,reason):
    if not ok:raise ValueError(reason)


def read(p):return json.loads(Path(p).read_bytes())


def pin(p):
    p=Path(p).resolve(strict=True);b=p.read_bytes()
    return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(v,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def prepare():
    """No GUI/socket/model/config registration: source copies and one immutable config."""
    RAW.mkdir(parents=True,exist_ok=True)
    support=read(BASE/'s1/PLAN_recovery_01.json')['support']
    for label in ('addon_original','addon','identity_tools','blender','worker','launcher'):
        need(pin(support[label]['path'])==support[label],'041_support_drift:'+label)
    out={}
    for label in ('addon','identity_tools','worker'):
        p=Path(support[label]['path']);dest=RAW/'support'/p.name;dest.parent.mkdir(exist_ok=True)
        if not dest.exists():shutil.copyfile(p,dest)
        need(dest.read_bytes()==p.read_bytes(),'support_copy')
        out[label]=pin(dest)
    out.update(addon_original=support['addon_original'],blender=support['blender'],launcher=pin(HERE/'gui_owner.py'))
    need(pin(ASSET)['sha256']==ASSET_SHA,'G60_asset')
    config={'schema_version':'1.0','enabled':True,'observe_on_prompt':True,'project_root':str(SITE),
            'state_file':str(RAW/'STATE.json'),'audit_file':str(RAW/'AUDIT.jsonl'),'quad_size':128,'max_sessions':4,
            'request_budget_s':30.0,'expected_identity':{'source_sha256':SOURCE},
            'blender':{'host':'127.0.0.1','port':PORT,'timeout_s':30.0}}
    if CONFIG.exists():need(read(CONFIG)==config,'immutable_endpoint_config_changed')
    else:dump(CONFIG,config)
    plan={'schema':'m6-042-direct-endpoint-v1','config':pin(CONFIG),'port':PORT,'host':'127.0.0.1',
          'asset':pin(ASSET),'support':out,'python':pin(PYTHON),'entry':pin(ENTRY),
          'production_command':[str(PYTHON),'-I','-B',str(ENTRY),'serve','--config',str(CONFIG)],
          'runtime_source_sha256':SOURCE,'model_tool':{'name':'human_eye_connection_status','arguments':{}},
          'post_matcher':'^mcp__human_eye_live__human_eye_connection_status$',
          'automatic_dispatch_or_trust_actions':0,'sources':{p.name:pin(p) for p in HERE.glob('*.py')}}
    if not (RAW/'PLAN.json').exists():dump(RAW/'PLAN.json',plan)
    else:need(read(RAW/'PLAN.json')==plan,'direct_plan_drift')
    return plan


class EndpointOwner:
    """Only the fresh Owned instance can close its own Popen; port remains fixed."""
    def __init__(self,folder,window):
        plan=read(RAW/'PLAN.json');need(pin(CONFIG)==plan['config'],'fixed_config')
        self.g=module('m6_042_fixedport_gui',HERE/'gui_owner.py')
        self.owner=self.g.Owned(Path(folder),plan['asset'],plan['support'],window)
        need(self.owner.port==PORT,'fixed_port')
        for key in ('pid','port','host','workspace','process','ready'):
            setattr(self,key,getattr(self.owner,key))
    def run(self,*args,**kwargs):return self.owner.run(*args,**kwargs)
    def close(self):return self.owner.close()


def client_class():
    transport=module('m6_042_direct_stdio_transport',VER/'m6_bounded_surface_scan_027/driver.py')
    class Client(transport.Client):
        def __init__(self,folder):
            self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=False)
            self.config=CONFIG;self.audit=RAW/'AUDIT.jsonl';self.seq=0;self.wire=[];self.responses=queue.Queue()
            self.stderr=(self.folder/'STDIO.stderr').open('xb');self.started=time.perf_counter_ns()
            command=read(RAW/'PLAN.json')['production_command']
            env={k:v for k,v in os.environ.items() if not k.upper().startswith(('HUMAN_EYE_','PYTHON'))}
            env.update({k:'1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
            self.worker=subprocess.Popen(command,cwd=self.folder,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self.stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            dump(self.folder/'LAUNCH.json',{'command':command,'pid':self.worker.pid,'config':pin(CONFIG),'native_mode':'ordinary_installed_production_stdio'})
            self.reader=threading.Thread(target=self.receive,daemon=True);self.reader.start()
        def initialize(self):
            hello,t=self.call('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':CYCLE,'version':'1'}})
            identity=hello['result']['_meta']['human_eye']
            need(identity['source_sha256']==SOURCE and identity['source_file_count']==143 and identity['production_mode'] is True,'actual_production_identity')
            self.call('notifications/initialized',notify=True)
            tools,tt=self.call('tools/list')
            catalog={v['name']:v for v in tools['result']['tools']}
            need('human_eye_scene_observe' in catalog and 'human_eye_connection_status' in catalog,'readonly_tools')
            need(catalog['human_eye_connection_status']['inputSchema']['additionalProperties'] is False,'status_tool_schema')
            dump(self.folder/'STARTUP.json',{'hello':hello,'initialize_timing':t,'tools':tools,'tools_timing':tt})
    return Client


def snapshot(owner,directory,label):
    reply=owner.run((VER/'m6_post032_profile_036/snapshot.py').read_text(encoding='utf8'))
    need(reply['response']['status']=='success','snapshot_success')
    text=reply['response']['result']['result'];line,=[r for r in text.splitlines() if r.startswith('M6_036_SNAPSHOT:')]
    data=json.loads(line.split(':',1)[1]);need(data['pid']==owner.pid and not data['background'] and data['main_thread'],'snapshot_owned_GUI')
    need(pin(data['asset'])['sha256']==ASSET_SHA,'snapshot_source_copy')
    fixture=read(VER/'scale_diag_001/fixtures/G60_D12.json')
    import numpy as np
    expected={v['name']:v for v in fixture['objects']}
    got={k:v for k,v in data['geometry'].items() if v['type']=='MESH'}
    need(set(got)==set(expected),'G60_mesh_names')
    for name,o in expected.items():
        need(got[name]['matrix']==o['matrix_world'],'G60_matrix')
        need(got[name]['local_sha256']==hashlib.sha256(np.asarray(o['vertices_local'],dtype='<f8').tobytes()).hexdigest(),'G60_vertices')
        need(got[name]['triangles_sha256']==hashlib.sha256(np.asarray(o['triangles'],dtype='<i4').tobytes()).hexdigest(),'G60_native_triangles')
    dump(Path(directory)/(label+'.json'),data)
    return data


def geometric(value):
    return {k:v for k,v in value.items() if k not in ('binding','trace_id','correlation','request_trace')}


def manual_probe(directory):
    protocol_path=RAW.parent/'FORMAL_PROTOCOL_02.json';protocol=read(protocol_path)
    event={'hook_event_name':'UserPromptSubmit','session_id':'042-direct-manual-positive','turn_id':'manual-positive-01','prompt':protocol['related_prompt']}
    command=[str(PYTHON),'-I','-B',str(ENTRY),'hook','--agent','codex','--event','UserPromptSubmit','--config',str(CONFIG),'--probe']
    dump(directory/'INPUT.json',event)
    before=(RAW/'AUDIT.jsonl').read_bytes() if (RAW/'AUDIT.jsonl').exists() else b''
    process=subprocess.run(command,input=json.dumps(event).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,check=False)
    (directory/'STDOUT.bin').write_bytes(process.stdout);(directory/'STDERR.bin').write_bytes(process.stderr)
    logs=(RAW/'AUDIT.jsonl').read_bytes();(directory/'AUDIT_APPEND.jsonl').write_bytes(logs[len(before):] if logs.startswith(before) else logs)
    value=json.loads(process.stdout);context=value.get('hookSpecificOutput',{}).get('additionalContext')
    # --probe can additionally enclose diagnostics; retain literal output and
    # report field presence without promoting this manual delivery to desktop.
    parsed=None
    if isinstance(context,str):
        try:parsed=json.loads(context)
        except ValueError:pass
    result={'status':'pass' if process.returncode==0 else 'fail','returncode':process.returncode,'command':command,
            'protocol':pin(protocol_path),'output':value,'additionalContext_type':type(context).__name__,
            'context_json':parsed,'manual_probe_only':True,'automatic_delivery_proved':False}
    dump(directory/'RESULT.json',result);return result


def preflight(output,window):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result={'status':'failed','model_calls':0,'automatic_dispatches':0,'trust_changes':0,'sessions':[],'plan':pin(RAW/'PLAN.json')}
    try:
        Client=client_class()
        for number in (1,2):
            d=output/f'session_{number}';d.mkdir();owner=None;client=None;row={'number':number,'port':PORT}
            try:
                owner=EndpointOwner(d/'native',window);row['pid']=owner.pid
                before=snapshot(owner,d,'BEFORE')
                client=Client(d/'stdio');client.initialize()
                status=client.observe({'name':'human_eye_connection_status','arguments':{}})
                dump(d/'STATUS.json',status);need(not status['tool_error'] and not status['rpc_error'],'actual_status_tool')
                row['status_result']=status['result']
                if number==1:
                    request=read(RAW.parent/'FORMAL_PROTOCOL_02.json')['short_direct_oracle']
                    arguments=dict(request['args'],session_id='m3-bvh-040',response_detail='full')
                    dump(d/'NEAREST_REQUEST.json',{'name':request['tool'],'arguments':arguments})
                    nearest=client.observe({'name':request['tool'],'arguments':arguments})
                    dump(d/'NEAREST.json',nearest);need(not nearest['tool_error'] and not nearest['rpc_error'],'actual_geometry_tool')
                    expected=read(BASE/'s1/warm_diagnostic/cells/G60_1_r3/first_nearest.json')['value']
                    need(geometric(nearest['result'])==geometric(expected),'exact041_G60_nearest_answer')
                    row['nearest_exact']=True
                    probe=d/'manual_positive';probe.mkdir();row['manual_positive']=manual_probe(probe)
                    need(row['manual_positive']['status']=='pass','manual_positive_probe')
                after=snapshot(owner,d,'AFTER')
                need(before['geometry']==after['geometry'],'readonly_geometry_preserved')
                row['source_preserved']=True;row['status']='pass'
            except BaseException:row.update(status='failed',error=traceback.format_exc())
            finally:
                if client is not None:
                    try:row['stdio_exit']=client.close();need(row['stdio_exit']==0,'stdio_EOF_cleanup')
                    except BaseException:row['stdio_cleanup_error']=traceback.format_exc()
                if owner is not None:
                    try:row['close']=owner.close()
                    except BaseException:row['GUI_cleanup_error']=traceback.format_exc()
                result['sessions'].append(row);dump(d/'RESULT.json',row)
            need(row.get('status')=='pass' and row.get('stdio_exit')==0 and row.get('close',{}).get('status')=='pass','direct_session_failure')
        need(result['sessions'][0]['pid']!=result['sessions'][1]['pid'],'independent_reopen_PID')
        result.update(status='pass',same_fixed_port_reopened=True,all_owned_processes_reaped=True)
    except BaseException:result['error']=traceback.format_exc()
    dump(output/'RESULT.json',result);print(json.dumps({'status':result['status'],'result':pin(output/'RESULT.json')}),flush=True)
    return 0 if result['status']=='pass' else 1


def serve(output,window):
    directory=Path(output);directory.mkdir(parents=True,exist_ok=False);owner=None
    try:
        owner=EndpointOwner(directory/'native',window)
        dump(directory/'CONTROLLER_READY.json',{'controller_pid':os.getpid(),'GUI_pid':owner.pid,'host':owner.host,'port':owner.port,'config':pin(CONFIG),'deadline_ns':owner.owner.deadline_ns,'stop_request':str(directory/'STOP_REQUEST.json')})
        while not (directory/'STOP_REQUEST.json').exists() and time.perf_counter_ns()<owner.owner.deadline_ns-15_000_000_000:
            need(owner.process.poll() is None,'owned_GUI_exited');time.sleep(.2)
    finally:
        if owner is not None:dump(directory/'CLOSE.json',owner.close())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','preflight','serve','stop'))
    parser.add_argument('--output');parser.add_argument('--window');args=parser.parse_args()
    if args.action=='prepare':print(json.dumps(prepare(),indent=2))
    elif args.action=='stop':dump(Path(args.output)/'STOP_REQUEST.json',{'requested_ns':time.perf_counter_ns(),'source':'explicit owned endpoint stop'})
    else:
        need(args.output is not None and args.window is not None,'output_and_frozen_window_required')
        window=read(args.window)
        if args.action=='preflight':raise SystemExit(preflight(args.output,window))
        serve(args.output,window)
