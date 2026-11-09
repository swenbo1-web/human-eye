"""One bounded old/new actual group; parent fixed-SHA gate is required."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PYTHON=Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe')
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)
OLD='27785b3f40716b71cfbc8326590a751cccdf9138'
OLD_SOURCE='239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9'

def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path):return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line] if Path(path).exists() else []

def identity(root):
    code="import json,sys;sys.path.insert(0,sys.argv[1]);from human_eye_plugin.runtime_identity import runtime_identity;print(json.dumps(runtime_identity(mode='live')))"
    value=json.loads(subprocess.check_output([str(PYTHON),'-X','utf8','-I','-B','-c',code,str(root)],cwd=root))
    for item in value['source_files']:assert sha(root/item['path'])==item['sha256'],item['path']
    return value

def export_old(folder):
    folder.mkdir()
    prior=json.loads((ROOT/'verification/arch_expert_entry_001/actual_run_02/identity_before.json').read_text())
    for item in prior['source_files']:
        path=folder/item['path'];path.parent.mkdir(parents=True,exist_ok=True)
        raw=subprocess.check_output(['git','show',OLD+':'+item['path']],cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest()==item['sha256'];path.write_bytes(raw)
    (folder/'pyproject.toml').write_bytes(subprocess.check_output(['git','show',OLD+':pyproject.toml'],cwd=ROOT))
    current=identity(folder);assert current==prior
    return current

def control(port,folder,params):
    tx=compact(dict(type='test_control',params=params));started=time.perf_counter_ns()
    with socket.create_connection(('127.0.0.1',port),timeout=30) as stream:
        stream.sendall(tx);rx=bytearray()
        while True:
            block=stream.recv(65536)
            if not block:break
            rx.extend(block)
    result=json.loads(rx)
    with (folder/'controls.jsonl').open('a',encoding='utf8') as out:
        out.write(json.dumps(dict(params=params,tx_hex=tx.hex(),rx_hex=rx.hex(),duration_ms=(time.perf_counter_ns()-started)/1e6))+'\n')
    assert 'control' in result,result
    return result['control']

class Client:
    def __init__(self,folder,mode,runtime,config,spec,blender,scene):
        self.folder,self.mode,self.sequence=folder,mode,0;self.queue=queue.Queue();folder.mkdir(exist_ok=True)
        self.state=Path(json.loads(config.read_text())['state_file'])
        command=[str(PYTHON),'-X','utf8','-I','-B',str(HERE/'qa_stdio.py'),'--mode',mode,
            '--config',str(config),'--directory',str(folder),'--spec',str(spec)]
        if mode!='shared':command+=['--blender',str(blender),'--scene',str(scene)]
        save(folder/'command.json',command);env=dict(__import__('os').environ,EXPERT_RUNTIME_ROOT=str(runtime))
        self.stderr=(folder/'stderr.log').open('wb')
        self.process=subprocess.Popen(command,cwd=runtime,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=self.stderr,bufsize=0,creationflags=HIDDEN)
        def read():
            while True:
                line=self.process.stdout.readline()
                if not line:break
                with (folder/'stdio_rx.bin').open('ab') as stream:stream.write(line)
                try:self.queue.put((line,json.loads(line)))
                except ValueError:self.queue.put((line,None))
            self.queue.put((b'',None))
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
        self.request('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo=dict(name='expert-opt-qa',version='1')))
        _,listed,_=self.request('tools/list',{})
        assert 'human_eye_arm_twist_observe' in [t['name'] for t in listed['result']['tools']]
    def request(self,method,params):
        assert sys.getprofile() is None
        self.sequence+=1;request_id=self.sequence
        tx=compact(dict(jsonrpc='2.0',id=request_id,method=method,params=params))+b'\n'
        started=time.perf_counter_ns();self.process.stdin.write(tx);self.process.stdin.flush()
        line,response=self.queue.get(timeout=90);ms=(time.perf_counter_ns()-started)/1e6
        with (self.folder/'stdio_tx.bin').open('ab') as stream:stream.write(tx)
        assert response is not None and response.get('id')==request_id,(line[:1000],self.process.poll())
        assert 'error' not in response,response
        return dict(full_tool_rtt_ms=ms,stdio_tx_bytes=len(tx),stdio_rx_bytes=len(line),client_profile_none=sys.getprofile() is None),response,request_id
    def tool(self,selection,label):
        arguments=dict(session_id='expert-opt',selection=selection);before=sha(self.state)
        cost,response,request_id=self.request('tools/call',dict(name='human_eye_arm_twist_observe',arguments=arguments))
        attempt=dict(request_id=request_id,label=label,arguments=arguments,response=response,**cost)
        with (self.folder/'tool_attempts.jsonl').open('a',encoding='utf8') as out:out.write(json.dumps(attempt,ensure_ascii=False)+'\n')
        assert response['result'].get('isError') is False,response
        report=json.loads(next(item['text'] for item in response['result']['content'] if item['type']=='text'))
        metric=next(r for r in reversed(rows(self.folder/'metrics.jsonl')) if r.get('event')=='tool' and r['request_id']==request_id)
        assert metric['profile_none'] and sha(self.state)==before
        return dict(label=label,request_id=request_id,arguments=arguments,result=report,metric=metric,
                    ledger_before_sha256=before,ledger_after_sha256=sha(self.state),**cost)
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=10)
        self.thread.join(timeout=2);self.stderr.close();save(self.folder/'exit.json',dict(returncode=self.process.returncode))
        assert self.process.returncode==0,self.process.returncode

def compare(actual,expected):
    for key in ('schema','status','assessment','model_id','scope','reason'):assert actual.get(key)==expected.get(key),key
    assert len(actual['regions'])==len(expected['regions'])
    maximum=0.
    for a,b in zip(actual['regions'],expected['regions']):
        for key in ('section_index','vertex_ids','flagged'):assert a[key]==b[key],key
        error=abs(a['predicted_severity']-b['predicted_severity']);assert error<=1e-9;maximum=max(maximum,error)
    if 'max_severity' in expected:assert abs(actual['max_severity']-expected['max_severity'])<=1e-9
    return maximum

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-commit',required=True);parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--blender',type=Path,default=Path('D:/Tools/blender5.2/blender.exe'))
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==args.expected_commit
    before=identity(ROOT);assert before['source_sha256']==args.expected_source_sha256;save(output/'identity_before.json',before)
    for name in ('qa_fixture.py','qa_observer.py','qa_stdio.py','qa_run.py'):
        shutil.copyfile(HERE/name,output/(name+'.txt'))
    result=dict(passed=False,product_commit=args.expected_commit,source_sha256=args.expected_source_sha256,
        old_commit=OLD,old_source_sha256=OLD_SOURCE,records=[],processes=[],model_api_calls=0,user_assets=0,
        timing_scope='no profiler; lightweight wrappers/wire copies included; direct oracle is separate post-response control')
    client=None;shared=None;shared_log=None;started=time.perf_counter_ns()
    def persist():save(output/'RESULTS.json',result)
    try:
        old_root=output/'runtime_old';old_before=export_old(old_root);save(output/'old_identity_before.json',old_before)
        original=ROOT/'verification/arch_expert_entry_001/actual_run_02/original_fixture.blend';fixture_sha=sha(original)
        original_spec=json.loads((original.with_name('original_spec.json')).read_text())
        result['fixture_sha256']=fixture_sha;result['fixture_spec']=original_spec
        for label,mode,runtime,expected in [('old_owned','owned',old_root,OLD_SOURCE),('new_owned','owned',ROOT,args.expected_source_sha256),('new_shared','shared',ROOT,args.expected_source_sha256)]:
            setup=output/(label+'_setup');setup.mkdir();fixture=setup/'fixture.blend';shutil.copyfile(original,fixture)
            spec=dict(original_spec,fixture=str(fixture));spec_path=setup/'spec.json';save(spec_path,spec)
            state=setup/'actions.json';state.write_bytes(b'opaque ledger unchanged in expert opt QA\n')
            config=dict(schema_version='1.0',enabled=True,project_root=str(runtime),state_file=str(state),audit_file=str(setup/'audit.jsonl'),quad_size=64)
            port=None
            if mode=='shared':
                ready=setup/'ready.json';shared_log=(setup/'blender.log').open('wb')
                command=[str(args.blender),'--factory-startup','--disable-autoexec','--background',str(fixture),'--python',str(HERE/'qa_fixture.py'),'--','serve',str(spec_path),str(ready),str(output/label)]
                save(setup/'command.json',command);shared=subprocess.Popen(command,stdout=shared_log,stderr=subprocess.STDOUT,creationflags=HIDDEN)
                limit=time.monotonic()+60
                while not ready.exists():
                    assert shared.poll() is None and time.monotonic()<limit,'shared fixture startup failed';time.sleep(.05)
                port=json.loads(ready.read_text())['port'];config['blender']=dict(host='127.0.0.1',port=port,timeout_s=30.)
            config_path=setup/'connector.json';save(config_path,config)
            client=Client(output/label,mode,runtime,config_path,spec_path,args.blender,fixture)
            def manipulate(op):
                return control(port,setup,dict(op=op)) if port else client.request('qa/control',dict(op=op))[1]['result']
            original_selection=spec['selection'];explicit=copy.deepcopy(original_selection);explicit['sections']=explicit['sections'][:-1]
            implicit={k:copy.deepcopy(v) for k,v in explicit.items() if k!='vertex_indices'}
            sequence=[]
            if mode=='owned':sequence=[('first',None,original_selection),('repeat',None,original_selection),('static','static',original_selection),('load','load',original_selection)]
            if label=='new_owned':sequence += [('explicit_first',None,explicit),('explicit_repeat',None,explicit),('implicit_first',None,implicit),('implicit_repeat',None,implicit),('explicit_return',None,explicit),('explicit_return_repeat',None,explicit),('unknown','unknown',original_selection),('recovered','load',original_selection)]
            if mode=='shared':sequence=[('explicit_first',None,explicit),('implicit_first',None,implicit),('explicit_return',None,explicit)]
            for name,op,selection in sequence:
                if op:manipulate(op)
                row=client.tool(selection,name);row['mode']=label;result['records'].append(row);persist()
                inspected=manipulate('inspect');event=inspected['event'];oracle=json.loads(Path(inspected['oracle_file']).read_text())
                row.update(blender_event=event,oracle_file=inspected['oracle_file'],oracle_max_abs_error=compare(row['result'],oracle['report']))
                assert event['profile_none'] and event['calls']['capture_entries']==1 and event['calls']['predict_entries']==1
                assert event['calls'].get('static_patch_copies',0)==(int(name in ('first','static','load')) if label=='old_owned' else 0)
                assert row['result']['source']['runtime_source_sha256']==expected
                required=len(selection['vertex_indices']) if 'vertex_indices' in selection else len({i for section in selection['sections'] for i in section})
                assert row['result']['source']['selected_vertices']==required
                if name=='unknown':
                    assert row['result']['status']=='unknown' and row['result']['reason']=='bone_twist_branch_unknown'
                    assert row['result']['regions']==[] and 'max_severity' not in row['result']
                else:assert row['result']['status']=='estimated'
                if 'repeat' in name:
                    assert event['bound_same'] and event['prepared_before']==event['prepared_after']
                    assert event['work_delta'].get('preparations',0)==0 and event['work_delta'].get('static_reads',0)==0
                persist()
            client.close();client=None
            armed=next(r for r in rows(output/label/'blender_events.jsonl') if r['event']=='observer_armed')
            result['processes'].append(dict(kind=label,pid=armed['pid'],stdio_returncode=0));assert sha(fixture)==fixture_sha
            if shared is not None:
                shared.terminate();shared.wait(timeout=20);result['processes'].append(dict(kind='shared_fixture_teardown',pid=shared.pid,returncode=shared.returncode,method='controlled terminate then wait'))
                shared=None;shared_log.close();shared_log=None
        after=identity(ROOT);assert after==before;save(output/'identity_after.json',after)
        old_after=identity(old_root);assert old_after==old_before;save(output/'old_identity_after.json',old_after)
        assert len(result['records'])==19
        result['passed']=True
    except BaseException as exc:
        result.update(failure=repr(exc),traceback=traceback.format_exc());print(result['traceback'],flush=True)
    finally:
        if client is not None:
            try:client.close()
            except BaseException as exc:result.setdefault('cleanup_errors',[]).append(repr(exc))
        if shared is not None:
            shared.terminate();shared.wait(timeout=20)
            result['processes'].append(dict(kind='shared_fixture_failure_teardown',pid=shared.pid,returncode=shared.returncode))
        if shared_log:shared_log.close()
        result['runner_sequence_ms']=(time.perf_counter_ns()-started)/1e6;result['record_count']=len(result['records']);persist()
    print(json.dumps(dict(passed=result['passed'],records=len(result['records']),result=str(output/'RESULTS.json'))))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
