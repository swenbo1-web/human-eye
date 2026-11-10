"""Identical finite stdio MCP forwarding adapter for installed plugin versions.

This experiment helper has no geometry solver, candidate setter or canned
answer. It exposes one already registered owned task, and forwards a model's
explicit call through the actual installed product scheduler and worker.
"""
import argparse
from collections import Counter
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

MAX_LINE=4*1024*1024
TASK_FIELDS=('event_id','selection','u_interval_deg','max_section_area_loss',
    'protected_vertex_ids','sentinel_name','angle_tolerance_deg','position_tolerance_m','area_tolerance')
TOOLS=[
    {'name':'describe_task','description':
        'Read the registered task and exact permitted constraints for this owned Blender session. This is task metadata, not a measured result.',
     'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
    {'name':'run_arm_goal','description':
        'Run the registered finite arm goal through the installed engine on this owned Blender scene. The engine reads actual geometry, fixes starting end poses, applies only permitted changes if justified, and returns actual execution feedback. Reusing the same event returns a historical receipt; it does not authorize another action.',
     'inputSchema':{'type':'object','properties':{'event_id':{'type':'string'}},
                    'required':['event_id'],'additionalProperties':False}},
]


def encoded(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')+b'\n'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')


class Bridge:
    def __init__(self,cell_path):
        self.born_ns=time.perf_counter_ns();self.cell_path=Path(cell_path).resolve()
        self.cell=json.loads(self.cell_path.read_text(encoding='utf8'))
        self.out=Path(self.cell['audit_dir']).resolve();self.out.mkdir(parents=True,exist_ok=False)
        self.fixture_path=Path(self.cell['fixture_input']).resolve()
        self.fixture=json.loads(self.fixture_path.read_text(encoding='utf8'))
        if len(self.fixture['cases'])!=1:raise ValueError('exactly_one_fixture_required')
        self.row=self.fixture['cases'][0]
        self.task={key:copy.deepcopy(self.row[key]) for key in TASK_FIELDS}
        self.host=None;self.process=None;self.scheduler=None;self.closed=False
        self.rpc=[];self.costs=[];self.calls=[];self.protocol=[]
        self.public_text_bytes=0;self.public_image_bytes=0
        self.summary={'schema':'plugin-version-ab-bridge-v1','started':False,'closed':False,
            'fixture_input_sha256':sha(self.fixture_path),'cell_sha256':sha(self.cell_path),
            'bridge_sha256':sha(Path(__file__)),'initializer_sha256':sha(Path(__file__).with_name('initializer.py')),
            'bridge_pid':os.getpid(),'candidate_assignments_by_bridge':0,'model_calls_by_bridge':0}
        save(self.out/'BRIDGE_PID.json',{'pid':os.getpid(),'cell':str(self.cell_path)})
        self.snapshot()

    def snapshot(self):
        self.summary.update(rpc=copy.deepcopy(self.rpc),costs=copy.deepcopy(self.costs),calls=copy.deepcopy(self.calls),
            public_text_bytes=self.public_text_bytes,public_image_bytes=self.public_image_bytes,
            cost_counts=dict(Counter(c['phase'] for c in self.costs)))
        save(self.out/'BRIDGE_RESULT.json',self.summary)

    def measured(self,name,original):
        def call(*args,**kwargs):
            mark=time.perf_counter_ns();error=None
            try:return original(*args,**kwargs)
            except BaseException as exc:error=type(exc).__name__;raise
            finally:self.costs.append({'phase':name,'elapsed_ns':time.perf_counter_ns()-mark,'error':error})
        return call

    def start(self):
        if self.host is not None:return
        if self.summary.get('startup_attempted'):raise RuntimeError('startup_failed_no_implicit_retry')
        self.summary['startup_attempted']=True;mark=time.perf_counter_ns()
        # Normal installed imports: no sys.path/PYTHONPATH override or source
        # namespace injection. The venv interpreter is selected by the caller.
        import human_eye_plugin
        from human_eye_plugin import runtime_identity as identity_module
        from human_eye_plugin import goal_execution
        from human_eye_plugin.blender_process import BlenderProcessHost
        from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
        from human_eye_plugin.task_authority import TrustedTaskAuthority
        self.goal_execution=goal_execution;self.identity_module=identity_module
        root=Path(identity_module.__file__).resolve().parents[1]
        if root!=Path(self.cell['expected_install_root']).resolve():raise RuntimeError('installed_import_root_mismatch')
        self.summary['installed_import_root']=str(root)
        self.summary['package_file']=human_eye_plugin.__file__
        self.summary['interpreter']=sys.executable
        self.summary['python_version']=sys.version
        self.summary['distribution_version']=importlib.metadata.version('human-eye-spatial-plugin')
        import numpy
        self.summary['controller_numpy_version']=numpy.__version__
        self.identity=identity_module.runtime_identity(mode='live')
        if self.identity['source_kind']!='installed_distribution':raise RuntimeError('wheel_install_identity_required')
        expected=self.cell.get('expected_source_sha256')
        if expected and self.identity['source_sha256']!=expected:raise RuntimeError('installed_source_identity_mismatch')
        self.summary['source_before']=self.identity
        self.summary['installed_import_ns']=time.perf_counter_ns()-mark
        blend=Path(self.cell['blend_file']).resolve();self.blend=blend;self.blend_before=sha(blend)
        initializer=Path(__file__).with_name('initializer.py').resolve();initializer_digest=sha(initializer)
        save(self.out/'SOURCE_FREEZE.json',{'runtime_identity':self.identity,
            'bridge_path':str(Path(__file__).resolve()),'bridge_sha256':sha(Path(__file__)),
            'initializer_path':str(initializer),'initializer_sha256':initializer_digest,
            'fixture_input_sha256':sha(self.fixture_path),'blend_path':str(blend),'blend_sha256':self.blend_before})
        original_popen=subprocess.Popen
        log_lock=threading.Lock();owner=self
        class StreamLog:
            def __init__(self,raw,path):self.raw=raw;self.path=path
            def write(self,value):
                with log_lock:
                    with self.path.open('a',encoding='utf8',newline='') as stream:stream.write(value)
                return self.raw.write(value)
            def readline(self,*args,**kwargs):
                value=self.raw.readline(*args,**kwargs)
                if value:
                    with log_lock:
                        with self.path.open('a',encoding='utf8',newline='') as stream:stream.write(value)
                return value
            def __getattr__(self,name):return getattr(self.raw,name)
        def launch(command,**kwargs):
            if owner.process is not None:raise AssertionError('one_owned_process_only')
            if '--python-expr' not in command or '--python' in command:raise AssertionError('default_verified_worker_required')
            position=command.index('--python-expr');original_expression=command[position+1]
            expression=("from pathlib import Path as _QP;import hashlib as _QH;import sys as _QS;"
                "_QS.path.append("+repr(str(root))+");"
                "_QB=_QP("+repr(str(initializer))+").read_bytes();assert _QH.sha256(_QB).hexdigest()=="+
                repr(initializer_digest)+";exec(compile(_QB,'<arm-ab-qa>','exec'));del _QB")
            actual=command[:position]+['--python-expr',expression]+command[position:]
            kwargs['env']=dict(os.environ,ARM_EXEC_QA_OUTPUT=str(owner.out),ARM_EXEC_QA_INPUTS=str(owner.fixture_path),
                ARM_AB_INSTALLED_ROOT=str(root))
            save(owner.out/'COMMAND.json',{'original':command,'actual':actual,'verified_expression_unchanged':
                actual[actual.index(original_expression)]==original_expression,'initializer_sha256':initializer_digest,
                'installed_site_root_appended_to_child_path':str(root),
                'path_append_purpose':'read actual wheel metadata; Blender native site entries keep priority',
                'stream_representation':'ProcessHost text API, not kernel raw bytes'})
            owner.process=original_popen(actual,**kwargs)
            owner.process.stdin=StreamLog(owner.process.stdin,owner.out/'RPC_TX.txt')
            owner.process.stdout=StreamLog(owner.process.stdout,owner.out/'RPC_RX.txt')
            save(owner.out/'PROCESS.json',{'pid':owner.process.pid,'argv':actual})
            return owner.process
        startup=time.perf_counter_ns();subprocess.Popen=launch
        try:self.host=BlenderProcessHost(Path(self.cell.get('blender','D:/Tools/blender5.2/blender.exe')),blend,timeout=30.,startup_timeout=60.)
        finally:subprocess.Popen=original_popen
        self.summary['blender_startup_ns']=time.perf_counter_ns()-startup
        ready=json.loads((self.out/'OBSERVER_READY.json').read_text(encoding='utf8'))
        if not ready.get('profile_none') or 'error' in ready:raise RuntimeError('readonly_observer_unavailable')
        self.summary['observer_ready']=ready;self.summary['capabilities']=self.host.capabilities()
        original_request=self.host._request
        def request(command,params,**kwargs):
            started=time.perf_counter_ns();result=None;error=None
            try:result=original_request(command,params,**kwargs);return result
            except BaseException as exc:error=repr(exc);raise
            finally:self.rpc.append({'command':command,'params':copy.deepcopy(params),
                'elapsed_ns':time.perf_counter_ns()-started,'result':copy.deepcopy(result),'error':error})
        self.host._request=request
        config=self.out/'product_config.json'
        save(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(root),
            'state_file':str(self.out/'state.json'),'audit_file':str(self.out/'audit.jsonl'),
            'quad_size':128,'max_sessions':16,'readback_atol_m':1e-6,
            'expected_identity':{'source_sha256':self.identity['source_sha256'],'build_id':self.identity['build_id']}})
        def no_grant(*args,**kwargs):raise AssertionError('arm_task_does_not_use_clearance_grant')
        self.scheduler=OwnedGoalScheduler(config,self.host,TrustedTaskAuthority('owned-arm-model-consumer',no_grant))
        goal_execution.validate_arm_axial_ledger=self.measured('arm_ledger_validation',goal_execution.validate_arm_axial_ledger)
        original_runtime=self.scheduler.service._runtime
        def runtime():
            value=self.measured('legacy_runtime_construct',original_runtime)()
            value.import_state=self.measured('legacy_runtime_import',value.import_state)
            value.export_state=self.measured('legacy_runtime_export',value.export_state)
            return value
        self.scheduler.service._runtime=runtime
        self.scheduler.service._save=self.measured('service_save',self.scheduler.service._save)
        self.summary['started']=True;self.summary['initialize_total_ns']=time.perf_counter_ns()-mark
        self.snapshot()

    def tool(self,name,arguments):
        if name=='describe_task':
            if arguments:raise ValueError('describe_task_accepts_no_arguments')
            return {'registered_task':copy.deepcopy(self.task),'scope':'owned_generated_fixed_frame_three_bone_LBS',
                'saved_frame':1,'file_saving_allowed':False}
        if name!='run_arm_goal':raise ValueError('unknown_tool')
        if set(arguments)!={'event_id'} or arguments['event_id']!=self.task['event_id']:
            raise ValueError('registered_event_identity_required')
        if self.host is None or self.scheduler is None:raise RuntimeError('initialize_required')
        record={'tool':name,'arguments':copy.deepcopy(arguments),'started_ns':time.perf_counter_ns(),
            'rpc_before':len(self.rpc),'costs_before':len(self.costs)}
        self.calls.append(record)
        try:
            spec=self.goal_execution.ArmAxialTaskSpec(**copy.deepcopy(self.task))
            entry_started=time.perf_counter_ns()
            try:result=self.scheduler.run(spec)
            finally:record['scheduler_entry_ns']=time.perf_counter_ns()-entry_started
            record['result']=copy.deepcopy(result)
            # Codex can terminate its MCP child tree immediately after final
            # output, without delivering stdin EOF. Finish owned native QA and
            # cleanup before publishing this tool result. The scheduler keeps
            # its actual receipt for same-event replay; no new host is started.
            close_started=time.perf_counter_ns()
            try:self.close()
            except Exception as exc:
                self.summary['post_run_close_error']={'type':type(exc).__name__,'message':str(exc)}
            finally:record['post_run_close_ns']=time.perf_counter_ns()-close_started
            record['owned_close_before_response_ns']=self.summary.get('owned_close_completed_ns')
            return result
        except BaseException as exc:record['error']={'type':type(exc).__name__,'message':str(exc)};raise
        finally:
            record.update(elapsed_ns=time.perf_counter_ns()-record['started_ns'],
                          rpc_after=len(self.rpc),costs_after=len(self.costs))
            self.snapshot()

    def respond(self,request):
        method=request.get('method');params=request.get('params') or {}
        if method=='initialize':
            self.start()
            return {'protocolVersion':params.get('protocolVersion','2024-11-05'),
                'capabilities':{'tools':{}},'serverInfo':{'name':'owned-arm-task-adapter','version':'1.0'}}
        if method=='ping' or method=='shutdown':return {}
        if method=='tools/list':return {'tools':TOOLS}
        if method=='tools/call':
            mark=time.perf_counter_ns()
            try:value=self.tool(params.get('name'),params.get('arguments') or {})
            except Exception as exc:
                value={'error':{'type':type(exc).__name__,'message':str(exc)},'outcome':'not_completed_by_this_tool_response'}
                result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}],'isError':True}
            else:result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}]}
            self.costs.append({'phase':'mcp_tool_call','elapsed_ns':time.perf_counter_ns()-mark})
            return result
        raise ValueError('unsupported_mcp_method')

    def close(self):
        if self.closed:return
        self.closed=True;mark=time.perf_counter_ns()
        try:
            if self.host is not None:self.host.close()
        finally:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
                self.summary['process_exit']={'pid':self.process.pid,'returncode':self.process.returncode,
                    'closed':self.process.poll() is not None}
            self.summary['close_ns']=time.perf_counter_ns()-mark
            self.summary['closed']=True
            self.summary['owned_close_completed_ns']=time.perf_counter_ns()
            self.summary['total_bridge_ns']=time.perf_counter_ns()-self.born_ns
            self.summary['total_bridge_ns_scope']='construction_through_owned_close_MCP_can_still_serve_replay'
            if hasattr(self,'identity_module'):
                self.summary['source_after']=self.identity_module.runtime_identity(mode='live')
                self.summary['source_unchanged']=self.summary['source_after']==self.summary.get('source_before')
            if hasattr(self,'blend_before'):
                self.summary['blend_sha256_before']=self.blend_before;self.summary['blend_sha256_after']=sha(self.blend)
            self.snapshot()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cell',type=Path,required=True)
    args=parser.parse_args();bridge=Bridge(args.cell)
    try:
        for raw in sys.stdin.buffer:
            if len(raw)>MAX_LINE:raise ValueError('mcp_request_size_limit')
            request=json.loads(raw);method=request.get('method')
            if 'id' not in request:
                if method=='exit':break
                continue
            started=time.perf_counter_ns()
            try:response={'jsonrpc':'2.0','id':request['id'],'result':bridge.respond(request)}
            except Exception as exc:
                response={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32603,'message':type(exc).__name__+': '+str(exc)}}
                bridge.summary.setdefault('protocol_errors',[]).append({'method':method,'error':repr(exc),
                    'traceback':traceback.format_exc()})
            payload=encoded(response)
            if method=='tools/list':bridge.public_text_bytes+=len(encoded(response.get('result',{}).get('tools',[])))-1
            elif method=='tools/call':
                bridge.public_text_bytes+=sum(len(c.get('text','').encode('utf8')) for c in response.get('result',{}).get('content',[]) if c.get('type')=='text')
            bridge.protocol.append({'method':method,'request':request,'response':response,
                'elapsed_ns':time.perf_counter_ns()-started,'response_ready_ns':time.perf_counter_ns()})
            save(bridge.out/'MCP_PROTOCOL.json',bridge.protocol)
            bridge.snapshot()
            sys.stdout.buffer.write(payload);sys.stdout.buffer.flush()
            if method=='shutdown':break
    finally:bridge.close()


if __name__=='__main__':main()
