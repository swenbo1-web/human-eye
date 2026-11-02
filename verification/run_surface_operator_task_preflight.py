"""New copies of authored factory assets; finite operator task/MCP/crash QA.

No shared Blender, original assets, host policy changes or real form claims.
The run folder must be new. Core can be the checkout or an isolated install.
"""
import argparse,copy,hashlib,json,os,queue,shutil,subprocess,sys,threading,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Client:
    def __init__(self,command,folder):
        self.queue=queue.Queue();self.protocol=[];self.err=(folder/'STDERR.txt').open('wb')
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def read():
            try:
                while True:
                    line=self.process.stdout.readline(256*1024+1)
                    if not line:break
                    value=json.loads(line);self.protocol.append(value);self.queue.put(value)
            finally:self.queue.put(None)
        threading.Thread(target=read,daemon=True).start()
    def rpc(self,key,method,params):
        self.process.stdin.write((json.dumps(dict(jsonrpc='2.0',id=key,method=method,params=params))+'\n').encode());self.process.stdin.flush()
        reply=self.queue.get(timeout=65);assert reply is not None,('server closed',self.process.poll())
        assert reply.get('method')!='elicitation/create','unexpected per-goal form'
        return reply
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.err.close()


def metadata(reply):return json.loads(reply['result']['content'][0]['text'])


def crash_child(args):
    sys.path.insert(0,str(args.core_root))
    from human_eye_plugin.surface_owned_task import OperatorReferenceTask
    from human_eye_plugin.surface_owned_process import OwnedSurfaceProcess
    task=OperatorReferenceTask(args.config,[6,12],args.task_root)
    if args.crash_point=='intake':os._exit(37)
    actor=OwnedSurfaceProcess(args.config);save(args.output/'WORKER.json',dict(pid=actor.process.pid))
    task.attach(actor)
    publish=task._publish
    def crash(name,value):
        if name=='SCOPE.json' and args.crash_point in ('parent_eof_before_approval','before_approval'):
            if args.crash_point=='before_approval':actor.process.kill();actor.process.wait(timeout=5)
            os._exit(37)
        if name=='RESULT.json' and args.crash_point=='after_write':os._exit(37)
        publish(name,value)
        if name=='RESULT.json' and args.crash_point=='after_receipt':os._exit(37)
    task._publish=crash
    task.execute(actor,[6,12],event_id='crash:'+task.task_id,client_received_ns=time.perf_counter_ns(),cancelled=lambda:False)
    raise AssertionError('crash point not reached')


def run(args):
    output=args.output.resolve();assert output.is_relative_to(ROOT/'verification/fixes')
    output.mkdir(exist_ok=False);sys.path.insert(0,str(args.core_root))
    from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
    from human_eye_plugin.surface_owned_process import OwnedSurfaceProcess
    from human_eye_plugin.surface_owned_task import OperatorReferenceTask
    from human_eye_plugin.surface_restore import RestoreJournal
    from human_eye_plugin.surface_owned_mcp import GOAL,INSPECT
    identity=runtime_identity();assert check_source_drift()['compatible']
    old=ROOT/'verification/fixes/20261102_m3_surface_entry/owned_fixtures'
    binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary)
    if args.entry is not None:
        import importlib.util
        spec=importlib.util.spec_from_file_location('_operator_preflight_fixed_target',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);entry.verify_imported_runtime(proof)
        assert Path(proof['module_root'])==args.core_root.resolve();launcher=args.entry
    else:
        launcher=output/'launch.py';launcher.write_text('import sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,'+repr(str(args.core_root))+')\nfrom human_eye_plugin.surface_owned_mcp import main\nmain()\n',encoding='utf8')
    def make_case(folder,name):
        folder.mkdir(exist_ok=False);source=old/name;case=json.loads((source/'CASE.json').read_bytes())
        for original,new in (('fixture.blend','fixture.blend'),('REFERENCE.json','REFERENCE.json')):shutil.copyfile(source/original,folder/new)
        journal=folder/'journal';journal.mkdir();config=folder/'CONFIG.json'
        save(config,dict(schema='owned-surface-operator-config-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=str(folder/'fixture.blend'),scene_sha256=sha(folder/'fixture.blend'),
            reference_file=str(folder/'REFERENCE.json'),reference_sha256=sha(folder/'REFERENCE.json'),
            object_id=case['object_id'],journal_root=str(journal),runtime_source_sha256=identity['source_sha256'],
            reference_intent=dict(provenance='new_copy_of_owned_factory_same_index_asset',semantic_target='restore selected vertices to the authored intended surface',
                correspondence='same_index_from_owned_copy')))
        return config,case
    rows=[]
    for name in ('flat','curved','rotated','millimetre_units','two_vertices','satisfied','too_far'):
        folder=output/name;config,case=make_case(folder,name);taskroot=folder/'task';selected=case['indices']
        command=[sys.executable,'-I','-B',str(launcher),'--operator-config',str(config),
            '--operator-task-root',str(taskroot),'--authorize-indices',*[str(i) for i in selected]]
        start=time.perf_counter_ns();client=Client(command,folder)
        try:
            init=client.rpc(0,'initialize',dict(protocolVersion='2025-06-18',capabilities={}))
            assert init['result']['_meta']['authorization_mode']=='explicit_operator_task'
            before=metadata(client.rpc(1,'tools/call',dict(name=INSPECT,arguments={})))
            result=metadata(client.rpc(2,'tools/call',dict(name=GOAL,arguments=dict(indices=selected))))
            elapsed=time.perf_counter_ns()-start
            after=metadata(client.rpc(3,'tools/call',dict(name=INSPECT,arguments={})))
            duplicate=metadata(client.rpc(2,'tools/call',dict(name=GOAL,arguments=dict(indices=selected))))
            extra=metadata(client.rpc(4,'tools/call',dict(name=GOAL,arguments=dict(indices=selected))))
            assert duplicate['status']=='receipt' and extra['physical_count']==0
            expected=case['current_raw'] if name=='too_far' else case['reference_raw']
            count=0 if name in ('too_far','satisfied') else len(selected)
            assert before['raw_snapshot']==case['current_raw'] and after['raw_snapshot']==expected
            assert result['physical_RNA_attempts']==after['physical_RNA_attempts']==count,(name,result)
            if count:assert result['task_readback_verified'] and result['kernel_result']['protected_vertices_unchanged']
            for key in ('edges','polygons','matrix_world','unit_scale'):assert after['raw_snapshot'][key]==before['raw_snapshot'][key]
            for i,point in enumerate(before['raw_snapshot']['vertices']):
                if i not in selected:assert after['raw_snapshot']['vertices'][i]==point
            assert sha(folder/'fixture.blend')==case['scene_sha256']
            assert all(v.get('method')!='elicitation/create' for v in client.protocol)
        finally:client.close()
        restart=subprocess.run(command,input=b'',capture_output=True,timeout=15)
        assert restart.returncode!=0 and b'FileExistsError' in restart.stderr
        row=dict(case=name,result=result,after=after,elapsed_startup_to_goal_ns=elapsed,duplicate=duplicate,new_id=extra,
            restart_refused=True,blend_unchanged=True,scripted_client=True,human_form_verified=False,protocol=client.protocol)
        save(folder/'QA.json',row);rows.append(row);print(json.dumps(dict(case=name,passed=True,physical_RNA=count)),flush=True)
    # Actual operator-local entry, not a shell-script form answer.
    folder=output/'local_cli';config,case=make_case(folder,'two_vertices')
    command=[sys.executable,'-I','-B',str(launcher),'--operator-config',str(config),'--operator-task-root',str(folder/'task'),
        '--authorize-indices','6','12','--execute-task']
    reply=subprocess.run(command,capture_output=True,timeout=65);assert reply.returncode==0,reply.stderr
    result=json.loads(reply.stdout);assert result['physical_RNA_attempts']==2 and result['task_readback_verified']
    assert sha(folder/'fixture.blend')==case['scene_sha256'];save(folder/'QA.json',dict(result=result,stderr=reply.stderr.decode()))
    rows.append(dict(case='local_cli',result=result))
    for point in ('intake','parent_eof_before_approval','before_approval','after_write','after_receipt'):
        folder=output/('crash_'+point);config,case=make_case(folder,'two_vertices');taskroot=folder/'task'
        command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--crash-child','--core-root',str(args.core_root),
            '--output',str(folder),'--config',str(config),'--task-root',str(taskroot),'--crash-point',point]
        child=subprocess.run(command,capture_output=True,timeout=65);assert child.returncode==37,(point,child.stderr)
        # Let the known owned child observe stdin EOF; don't touch shared GUIs.
        worker_info=folder/'WORKER.json'
        if worker_info.exists():
            pid=json.loads(worker_info.read_bytes())['pid']
            if os.name=='nt':
                import ctypes
                kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p
                kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
                kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                handle=kernel.OpenProcess(0x00100000,False,pid)
                if handle:
                    try:assert kernel.WaitForSingleObject(handle,8000)==0,'owned worker did not exit after parent EOF'
                    finally:kernel.CloseHandle(handle)
                else:assert ctypes.get_last_error()==87,'could not check known owned worker exit'
            else:
                until=time.monotonic()+8
                while True:
                    try:os.kill(pid,0)
                    except ProcessLookupError:break
                    assert time.monotonic()<until,'owned worker did not exit';time.sleep(.05)
        history=RestoreJournal.inspect(folder/'journal')
        assert len(history['rows'])==(0 if point=='intake' else 1)
        assert history['unknown']==(point=='before_approval')
        if point=='parent_eof_before_approval':assert history['rows'][0]['setter_count']==0
        if point in ('after_write','after_receipt'):assert history['rows'][0]['setter_count']==2
        try:OperatorReferenceTask(config,[6,12],taskroot)
        except FileExistsError:pass
        else:raise AssertionError('restart restored operator authority')
        actor=OwnedSurfaceProcess(config)
        try:
            current=actor.inspect();assert current['physical_RNA_attempts']==0 and current['raw_snapshot']==case['current_raw']
            if history['unknown']:
                denied=actor.goal([6,12],event_id='must_not_dispatch',received_ns=time.perf_counter_ns(),
                    approve=lambda _:(_ for _ in ()).throw(AssertionError('unknown must not approve')))
                assert denied['physical_RNA_attempts']==0 and denied['quarantined']
        finally:actor.close()
        assert sha(folder/'fixture.blend')==case['scene_sha256']
        row=dict(case='crash_'+point,exit_code=child.returncode,journal=history,task_restart_refused=True,
            new_worker_reloaded_unsaved_fixture=True,stderr=child.stderr.decode('utf8','replace'))
        save(folder/'QA.json',row);rows.append(row);print(json.dumps(dict(case='crash_'+point,passed=True)),flush=True)
    save(output/'RESULT.json',dict(runtime_source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        cases=rows,formal_model_calls=0,actual_Codex_operator_mode_UI_proof=False,shared_GUI_accessed=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--core-root',type=Path,required=True)
    p.add_argument('--crash-child',action='store_true');p.add_argument('--config',type=Path);p.add_argument('--task-root',type=Path)
    p.add_argument('--crash-point');p.add_argument('--entry',type=Path)
    args=p.parse_args();crash_child(args) if args.crash_child else run(args)
