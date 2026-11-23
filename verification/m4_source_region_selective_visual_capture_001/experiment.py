"""Single fixed two-arm cold qualification with identical replay and formal dispatch."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Empty, Queue
from shutil import copyfile
import subprocess
import sys
from threading import Thread
from time import perf_counter_ns, sleep
import traceback
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from cold_native import NativeSession, RETAINED, METER
from score import ORDER, ASSET, need, pin, reference_inputs, verify_pair

ROOT=Path('D:/he_m4_source_region_selective_visual_capture_001').resolve()
PYTHON=Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe').resolve()
BLENDER=Path('D:/Tools/blender5.2/blender.exe').resolve()
BLENDER_SHA='284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
PYTHON_SHA='50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
BASE_BINDING=HERE.parent/'m1_m2_source_region_scoped_measurement_001/install/PRODUCT_RUN_BINDING.json'
B_BINDING=ROOT/'candidate_install/PRODUCT_RUN_BINDING.json'
DEVICE=HERE.parent/'m4_live_source_region_task_003/harness/device_capture.py'
HISTORY=Path('D:/he_m4_rail_source_region_product_native_001/slots/P1')
FIXTURE=HISTORY/'native/input.blend'
TERMINAL=HISTORY/'TERMINAL_SOURCE.json'
CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
MAX_LINE=8*1024*1024
WINDOW_NS=120*10**9


def digest(data):
    return sha256(data).hexdigest()


def stable(data):
    return (json.dumps(data,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))+'\n').encode()


def load(path):
    return json.loads(path.read_bytes())


def save(path,value):
    with path.open('xb') as fp:
        fp.write(stable(value))


def left(deadline):
    seconds=(deadline-perf_counter_ns())/1e9
    if seconds<=0:
        raise TimeoutError('absolute_slot_deadline')
    return seconds


def assert_install(arm):
    binding_path = BASE_BINDING if arm=='A' else B_BINDING
    b = load(binding_path)
    target=Path(b['install_root'])
    need(digest(Path(b['wheel_path']).read_bytes())==b['wheel_sha256'],'isolated_wheel_changed')
    with ZipFile(b['wheel_path']) as pack:
        for row in b['source_manifest']:
            name = row['path']
            expected=subprocess.check_output(['git','-C',str(HERE.parents[1]),'show',b['preparation_git']+':'+name])
            actual=(target/name).read_bytes()
            need(actual==pack.read(name)==expected and digest(actual)==row['sha256'],
                 'isolated_Git_wheel_runtime_byte_mismatch/'+name)
    return binding_path,b


def start_worker(argv, directory, prefix, *, stdin):
    with (directory/(prefix+'_STDERR.bin')).open('xb') as err:
        return subprocess.Popen(argv,cwd=str(directory),stdin=stdin,stdout=subprocess.PIPE,
                                stderr=err,creationflags=CREATE_NO_WINDOW)


class Stdio:
    def __init__(self,arm,slot,binding,config,deadline):
        self.slot,self.deadline=slot,deadline
        stdout=slot/'mcp'
        stdout.mkdir()
        self.process=start_worker([str(PYTHON),'-IB','-X','utf8',str(HERE/'stdio_entry.py'),
            arm,str(binding),str(config),str(slot)],stdout,'STDIO',stdin=subprocess.PIPE)
        self.messages=Queue()
        self.reader=Thread(target=self.read_stdout,name='m4-stdio-reader',daemon=True)
        try:
            self.reader.start()
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=3)
            raise

    def read_stdout(self):
        try:
            while True:
                raw=self.process.stdout.readline(MAX_LINE+1)
                if not raw:
                    self.messages.put(None)
                    break
                need(len(raw)<=MAX_LINE and raw.endswith(b'\n'),'stdio_line_limit')
                self.messages.put(raw)
        except BaseException as error:
            self.messages.put(error)

    def request(self,seq,method,params):
        folder=self.slot/'mcp'/f'{seq:03d}'
        folder.mkdir()
        tx,rx=folder/'REQUEST.bin',folder/'RESPONSE.bin'
        outbound=stable({'jsonrpc':'2.0','id':seq,'method':method,'params':params})
        tx.write_bytes(outbound)
        started=perf_counter_ns()
        self.process.stdin.write(outbound)
        self.process.stdin.flush()
        try:
            inbound=self.messages.get(timeout=left(self.deadline))
        except Empty as error:
            raise TimeoutError('production_stdio_response_missing') from error
        if isinstance(inbound,BaseException):
            raise inbound
        need(inbound is not None,'production_stdio_premature_EOF')
        rx.write_bytes(inbound)
        elapsed=perf_counter_ns()-started
        parsed=json.loads(inbound)
        need(parsed.get('id')==seq and parsed.get('jsonrpc')=='2.0' and 'result' in parsed,
             'production_stdio_response_wrong_request')
        return parsed['result'],tx,rx,elapsed

    def close(self):
        started=perf_counter_ns()
        forced=False
        suffix=None
        try:
            self.process.stdin.close()
            suffix=self.messages.get(timeout=left(self.deadline))
            self.reader.join(timeout=left(self.deadline))
            code=self.process.wait(timeout=left(self.deadline))
        except (Empty,TimeoutError,OSError,subprocess.TimeoutExpired):
            forced=True
            if self.process.poll() is None:
                self.process.kill()
            code=self.process.wait(timeout=3)
        exit_path=self.slot/'STDIO_PROCESS_EXIT.json'
        normal=(not forced and suffix is None and not self.reader.is_alive() and code==0
                and (self.slot/'STDIO_WORKER_EOF.json').exists())
        save(exit_path,{'pid':self.process.pid,'exit_code':code,'forced_kill':forced,
             'stdout_eof_seen':suffix is None and not forced,'started_ns':started,'closed_ns':perf_counter_ns()})
        return {'confirmed':normal,'production_eof_and_exit_verified':normal,'exit_code':code,
                'stdout_eof_seen':suffix is None and not forced,'forced_kill':forced,
                'worker_eof':pin(self.slot/'STDIO_WORKER_EOF.json') if normal else None,
                'worker_exit':pin(exit_path)}


def start_native(arm,slot,deadline,binding,offline,*,reservation_only=False):
    need(digest(FIXTURE.read_bytes())==ASSET and digest(BLENDER.read_bytes())==BLENDER_SHA,
         'asset_or_blender_exact_source_changed')
    if reservation_only:
        raise ReachedReservation(arm)
    if not offline:
        save(slot/'BLENDER_RESERVATION.json',{'label':arm,'at_ns':perf_counter_ns(),'deadline_ns':deadline})
        return NativeSession.start(blender=BLENDER,asset=FIXTURE,workspace=slot/'native',
            deadline_ns=deadline,condition='P',expected_asset_sha256=ASSET,max_calls=3)
    workspace=slot/'native'
    workspace.mkdir()
    process=start_worker([str(PYTHON),'-IB','-X','utf8',str(HERE/'replay.py'),'--terminal',str(TERMINAL),
        '--workspace',str(workspace),'--asset',str(FIXTURE),'--asset-sha256',ASSET,'--deadline-ns',str(deadline),
        '--label',arm,'--binding',str(binding)],workspace,'REPLAY',stdin=subprocess.DEVNULL)
    ready_file=workspace/'READY.json'
    try:
        while not ready_file.is_file():
            need(process.poll() is None,'real_replay_worker_exited_before_ready')
            left(deadline)
            sleep(.01)
        ready=load(ready_file)
        need(ready['pid']==process.pid and ready['deadline_ns']==deadline and ready['host']=='127.0.0.1',
             'replay_ready_identity')
        session=NativeSession()
        session.process,session.workspace,session.ready=process,workspace,ready
        session.config={'pid':process.pid,'host':ready['host'],'port':ready['port'],'deadline_ns':deadline,
            'asset':str(FIXTURE),'asset_copy':str(workspace/'input.blend'),'asset_sha256':ASSET,
            'protected_public_images':[]}
        return session
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        raise


class ReachedReservation(Exception):
    pass


def post_source(session,slot,offline):
    target=slot/'TERMINAL_SOURCE.json'
    if offline:
        copyfile(TERMINAL,target)
        return {'scope':'archive-backed transcript after replay', 'source':pin(target)}
    script=DEVICE.read_text(encoding='utf8')+'\ncapture_device(bpy,'+repr(str(target))+','+repr(ASSET)+',terminal=True)\n'
    raw=session.run(script)
    save(slot/'POST_SOURCE_CLIENT.json',raw)
    response=raw['response']
    need(response.get('status')=='success' and response['result']['executed'] is True,'post_source_capture_failed')
    line=response['result']['result']
    prefix='M4_LIVE_SOURCE_CAPTURE:'
    need(line.startswith(prefix),'post_source_receipt_missing')
    evidence=json.loads(line.removeprefix(prefix))
    expected=pin(target)
    need(evidence['pid']==session.process.pid and expected['sha256']==evidence['sha256']
         and expected['bytes']==evidence['bytes'],'post_source_actual_receipt_scope')
    return {'scope':'actual same Blender after both measured requests', 'source':expected,
            'receipt':evidence,'client_elapsed_ns':raw['elapsed_ns']}


def frame_paths(producer):
    f,=producer['frames']
    return f['image_path'],f['arrays_path']


def raw_host_paths(slot,sequence):
    base=slot/'native/WIRE'/f'{sequence:03d}'
    return base/'REQUEST.bin',base/'RESPONSE.bin'


def run_slot(root,arm,reference,*,offline=False,reservation_only=False):
    begin=perf_counter_ns()
    deadline=begin+WINDOW_NS
    binding_path,binding=assert_install(arm)
    slot=root/'slots'/arm
    if reservation_only:
        try:
            start_native(arm,slot,deadline,binding_path,offline,reservation_only=True)
        except ReachedReservation as stop:
            need(str(stop)==arm and not slot.exists(),'preflight_crossed_actual_Blender_reservation')
        return {'label':arm,'pid':os.getpid(),'started_ns':begin,'elapsed_ns':perf_counter_ns()-begin,
                'at_appointment_boundary':True,'actual_Blender':0,'binding':pin(binding_path)}
    slot.mkdir(parents=True,exist_ok=False)
    config_path=slot/'PRODUCT_CONFIG.json'
    closed,stdio_closed=None,None
    session,mcp=None,None
    shots=[]
    terminal=None
    error=None
    try:
        session=start_native(arm,slot,deadline,binding_path,offline)
        save(config_path,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
            'expected_identity':{'source_sha256':binding['source_sha256']},
            'project_root':binding['install_root'],'state_file':str(slot/'product_state.json'),
            'audit_file':str(slot/'product_audit.jsonl'),'request_budget_s':30,
            'blender':{'host':session.host,'port':session.port,'timeout_s':30}})
        mcp=Stdio(arm,slot,binding_path,config_path,deadline)
        init,*_=mcp.request(1,'initialize',{})
        need(init['_meta']['human_eye']['source_sha256']==binding['source_sha256'],'wrong_real_stdio_runtime')
        listing,*_=mcp.request(2,'tools/list',{})
        tool,=[x for x in listing['tools'] if x['name']=='human_eye_scene_observe']
        modes=tool['inputSchema']['properties']['query']['properties']['mode']['enum']
        need(('source_region_visual' in modes)==(arm=='B') and 'source_region' in modes,'wrong_actual_tools_list')
        for seq,label in enumerate(ORDER,1):
            queries=reference[label]['query']
            query=dict(queries,mode=('source_region_visual' if arm=='B' else 'source_region'))
            args={'query':query,'include_image':True,'response_detail':'full','session_id':'m4-cold-visual'}
            response,tx,rx,elapsed=mcp.request(seq+2,'tools/call',{'name':'human_eye_scene_observe','arguments':args})
            need(response.get('isError') is False,'real_stdio_business_failed/'+json.dumps(response)[:1800])
            producer=slot/f'PRODUCER_{seq}.json'
            png,npz=frame_paths(load(producer))
            ht,hr=raw_host_paths(slot,seq)
            shots.append({'label':label,'args':args,'png_path':png,'npz_path':npz,'producer_path':str(producer),
                'mcp_tx_path':str(tx),'mcp_rx_path':str(rx),'host_tx_path':str(ht),'host_rx_path':str(hr),
                'public_mcp_elapsed_ns':elapsed})
        terminal=post_source(session,slot,offline)
    except BaseException as exc:
        error={'type':type(exc).__name__,'reason':str(exc),'traceback':traceback.format_exc()}
    finally:
        if mcp is not None:
            try:
                stdio_closed=mcp.close()
            except BaseException as exc:
                if error is None:
                    error={'type':type(exc).__name__,'reason':str(exc),'traceback':traceback.format_exc()}
        if session is not None:
            try:
                closed=session.close()
            except BaseException as exc:
                if error is None:
                    error={'type':type(exc).__name__,'reason':str(exc),'traceback':traceback.format_exc()}
    native_status=slot/'native/WORKER_CLOSED.json'
    native=load(native_status) if native_status.exists() else None
    mcp_pass=stdio_closed is not None and stdio_closed['confirmed']
    native_pass=(closed is not None and closed['process_reaped'] and closed['exit_code']==0 and closed['error'] is None
                 and native is not None and not native['poisoned']
                 and native['initial_geometry_fingerprint']==native['final_geometry_fingerprint']
                 and closed['pid']==native['pid'] and closed['source_file_unchanged'] and closed['protected_files_unchanged'])
    if error is None and not (mcp_pass and native_pass):
        error={'type':'ClosureError','reason':'unconfirmed_stdio_or_native_close'}
    save(slot/'RUNTIME_CLOSE.json',{'public_MCP_close':stdio_closed,'Blender_close':closed,
         'Blender_status':{'closed':native},'offline':offline})
    safe_no_start=not (slot/'native/SPAWN.json').exists() and session is None
    publication=slot/'SLOT_PUBLICATION.json'
    close_path=slot/'RUNTIME_CLOSE.json'
    save(publication,{'status':'collected' if error is None else 'failed','started_ns':begin,
        'closed_ns':perf_counter_ns(),'elapsed_ns':perf_counter_ns()-begin,'deadline_ns':deadline,
        'terminal':terminal,'error':error,'safe_to_close':native_pass or safe_no_start,
        'actual_blender_starts':int(not offline and (slot/'native/SPAWN.json').exists()),
        'close':pin(close_path),'binding':pin(binding_path),
        'raw_worker_events':pin(slot/'native/WORKER_EVENTS.jsonl') if (slot/'native/WORKER_EVENTS.jsonl').exists() else None})
    if error is not None:
        print(error['reason'],flush=True)
        return {'passed':False,'safe':native_pass or safe_no_start,'error':error}
    save(slot/'SHOOT.json',{'label':arm,'offline':offline,'asset_sha256':ASSET,'queries':shots,
        'terminal_path':str(slot/'TERMINAL_SOURCE.json'),'publication_path':str(publication),'close_path':str(close_path)})
    print(arm+' '+('replay' if offline else 'formal')+' collected',flush=True)
    return {'passed':True,'safe':True}


def run_pair(root,offline,reference):
    outputs={}
    for arm in ('A','B'):
        outputs[arm]=run_slot(root,arm,reference,offline=offline)
        if not outputs[arm]['safe']:
            break
    score=None
    error=None
    if len(outputs)==2 and all(x['passed'] for x in outputs.values()):
        try:
            score=verify_pair(root/'slots/A',root/'slots/B',reference)
        except Exception as exc:
            error={'type':type(exc).__name__,'reason':str(exc),'traceback':traceback.format_exc()}
            print(error['reason'],flush=True)
    result={'passed':score is not None and score['passed'],'offline':offline,
            'slots':outputs,'score':score,'error':error,'closed_ns':perf_counter_ns(),
            'failed':sum(not v['passed'] for v in outputs.values()),'unrun':2-len(outputs)}
    save(root/'RESULT.json',result)
    return result['passed']


def frozen_inputs(preflight):
    files=[p for p in HERE.glob('*.py') if p.is_file()]+[HERE/'PLAN.md',FIXTURE,TERMINAL,RETAINED,METER,
          DEVICE,BASE_BINDING,B_BINDING,BLENDER,PYTHON,preflight/'RESULT.json',
          ROOT/'SCORE_CONTROLS.json',ROOT/'preflight_compatibility/RESULT.json',
          ROOT/'preflight_host_probe/HOST_CONTROL_OUTPUT.txt']
    need(load(ROOT/'SCORE_CONTROLS.json')['passed'] and load(ROOT/'preflight_compatibility/RESULT.json')['passed'],
         'replay_boundary_or_default_compatibility_control_failed')
    return [pin(p) for p in sorted(files)]


def assert_freeze():
    q=load(ROOT/'FREEZE.json')
    preflight=Path(q['preflight'])
    need(q['files']==frozen_inputs(preflight),'frozen_actual_inputs_changed')
    result=load(preflight/'RESULT.json')
    need(result['passed'] and result['offline'],'same_path_two_arm_replay_did_not_pass')
    checked=verify_pair(preflight/'slots/A',preflight/'slots/B')
    need(checked==result['score'],'same_closed_verification_cannot_be_replayed')
    return q


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('offline','freeze','cold','formal'))
    parser.add_argument('arg',nargs='?')
    args=parser.parse_args()
    need(Path(sys.executable).resolve()==PYTHON and digest(PYTHON.read_bytes())==PYTHON_SHA
         and sys.flags.isolated and sys.dont_write_bytecode,'fixed_interpreter')
    reference=reference_inputs()
    if args.action in ('offline','freeze'):
        name=args.arg or 'paired'
        need(name.isascii() and name.replace('-','').isalnum(),'private_preflight_namespace')
        sandbox=ROOT/'preflight'/name
        if args.action=='offline':
            sandbox.mkdir(parents=True,exist_ok=False)
            return int(not run_pair(sandbox,True,reference))
        result=load(sandbox/'RESULT.json')
        need(result['passed'] and result['offline'] and
             verify_pair(sandbox/'slots/A',sandbox/'slots/B',reference)==result['score'],'closed_qualification_gate')
        save(ROOT/'FREEZE.json',{'preflight':str(sandbox),'files':frozen_inputs(sandbox),'at_ns':perf_counter_ns()})
    elif args.action=='cold':
        assert_freeze()
        need(args.arg in ('A','B'),'cold_arm_required')
        mark=run_slot(ROOT,args.arg,reference,reservation_only=True)
        mark['freeze']=pin(ROOT/'FREEZE.json')
        save(ROOT/f'COLD_{args.arg}.json',mark)
    else:
        assert_freeze()
        frozen=pin(ROOT/'FREEZE.json')
        for arm in ('A','B'):
            gate=load(ROOT/f'COLD_{arm}.json')
            need(gate['label']==arm and gate['at_appointment_boundary'] and not gate['actual_Blender']
                 and gate['freeze']==frozen,'real_cold_start_boundary_proof_required')
        save(ROOT/'FORMAL_START.json',{'freeze':frozen,'pid':os.getpid(),'started_ns':perf_counter_ns(),'order':['A','B']})
        return int(not run_pair(ROOT,False,reference))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
