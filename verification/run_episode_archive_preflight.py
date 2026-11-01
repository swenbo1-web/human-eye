"""Hard-exit owned-controller tests. Explicit scripted clients, no Codex UI.

Only freshly created factory scenes and child PIDs created by this worker are
used. Windows process handles are captured before sending the goal, preventing
PID-reuse confusion during cleanup. Recovery creates no Blender host.
"""
import argparse,ctypes,hashlib,importlib.util,json,os,queue,subprocess,sys,tempfile,time
from ctypes import wintypes
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from verification.run_owned_task_mcp_preflight import Client,save


def installed(args):
    spec=importlib.util.spec_from_file_location('_archive_installed',args.entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root'])
    identity,_=module.verify_imported_runtime(proof);assert identity['source_sha256']==args.expected_build
    return identity


def worker(args):
    installed(args)
    from human_eye_plugin.task_episode_archive import EpisodeArchive
    if args.recover is not None:
        report=EpisodeArchive(args.recover).recover();report['fresh_process_no_host_created']=True
        print(json.dumps(report));return
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.owned_task_mcp import OwnedTaskMCP
    from human_eye_plugin.live_spatial_mcp import _configure_utf8_stdio
    folder=args.config.parent;host=BlenderProcessHost(args.blender,args.scene)
    save(folder/'OWNED_PROCESS.json',dict(pid=host._process.pid,scene=str(args.scene.resolve()),factory_background=True))
    archive_root=folder/'task-evidence';archive_root.mkdir(exist_ok=False);archive=EpisodeArchive(archive_root)
    _configure_utf8_stdio();server=OwnedTaskMCP(args.config,host,sys.stdin,sys.stdout,episode_archive=archive)
    initial=server.entry._scheduler._capture();save(folder/'INITIAL.json',initial)
    commands=[];applied=[];request=host._request
    def requesting(command,params,**kwargs):commands.append(command);return request(command,params,**kwargs)
    host._request=requesting
    def crash(point):
        packet=host.capture_evidence();save(folder/'NATIVE_AT_CRASH.json',packet)
        objects={o['name']:o for o in packet['native_scene']['objects']}
        old={o['name']:o for o in initial['native_scene']['objects']}
        assert objects['GreyBase']==old['GreyBase']
        assert {k:v for k,v in objects['BluePart'].items() if k not in ('world_vertices','matrix')}=={
            k:v for k,v in old['BluePart'].items() if k not in ('world_vertices','matrix')}
        assert all(objects['BluePart']['matrix'][r][c]==old['BluePart']['matrix'][r][c]
            for r in range(4) for c in range(4) if (r,c)!=(2,3))
        gap=min(v[2] for v in objects['BluePart']['world_vertices'])-max(v[2] for v in objects['GreyBase']['world_vertices'])
        meters={live['grant'].goal_id:host.motion_goal_status(live['grant'].goal_id)
            for live in server.entry._live.values()} if applied else {}
        save(folder/'CRASH.json',dict(point=point,applied_calls=len(applied),commands=commands,gap_m=gap,
             physical_meter_registered=bool(meters),meters=meters,reference_and_local_geometry_unchanged=True))
        os._exit(23)  # Deliberately bypass finally, flushing and normal close.
    begin=archive.begin;bind=archive.bind_source;finish=archive.finish;apply=host.apply_transform
    def beginning(value):
        slot=begin(value)
        if args.scenario=='after_intake':crash('after_intake')
        return slot
    def binding(*values):
        result=bind(*values)
        if args.scenario=='after_source':crash('after_source')
        return result
    def applying(*values,**options):
        result=apply(*values,**options);applied.append(True)
        if args.scenario=='after_first_apply':crash('after_first_apply')
        return result
    def finishing(*values):
        result=finish(*values)
        if args.scenario=='after_final_archive':crash('after_final_archive')
        return result
    archive.begin=beginning;archive.bind_source=binding;archive.finish=finishing;host.apply_transform=applying
    try:server.run()
    finally:host.close()  # Not reached at the four registered crash points.


class OwnedChild:
    def __init__(self,pid,expected_executable):
        assert os.name=='nt' and type(pid) is int and pid>0
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];self.api.OpenProcess.restype=wintypes.HANDLE
        self.api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];self.api.WaitForSingleObject.restype=wintypes.DWORD
        self.api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
        self.api.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.api.OpenProcess(0x100000|0x1000|0x1,False,pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        size=wintypes.DWORD(32768);buf=ctypes.create_unicode_buffer(size.value)
        if not self.api.QueryFullProcessImageNameW(self.handle,0,buf,ctypes.byref(size)):
            self.api.CloseHandle(self.handle);raise ctypes.WinError(ctypes.get_last_error())
        if Path(buf.value).resolve()!=expected_executable.resolve():
            self.api.CloseHandle(self.handle);raise ValueError('owned_child_executable_mismatch')
    def close(self):
        try:
            status=self.api.WaitForSingleObject(self.handle,15000);forced=False
            if status==258:
                if not self.api.TerminateProcess(self.handle,24):raise ctypes.WinError(ctypes.get_last_error())
                forced=True;status=self.api.WaitForSingleObject(self.handle,5000)
            assert status==0,'owned Blender child failed to exit'
            return dict(child_exited=True,forced_owned_handle_cleanup=forced,pid_reuse_avoided=True,executable_verified=True)
        finally:self.api.CloseHandle(self.handle)


def parent(args):
    assert os.name=='nt','This hard-exit lifecycle harness targets the Windows Codex environment'
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    scenarios=['after_intake','after_source','after_first_apply','after_final_archive']
    save(output/'REGISTERED_INPUT.json',dict(scenarios=scenarios,rounds=2,source_sha256=args.expected_build,
         formal_model_calls=0,actual_Codex_UI_approval=False,harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    identity=json.loads((args.entry.parent/'RUNTIME_BINDING.json').read_text(encoding='utf8'))['identity']
    pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id')}
    pin.update(source_kind='installed_distribution',protocol_version='2025-03-26',mode='live')
    rows=[]
    for repeat in range(2):
        for scenario in scenarios:
            folder=Path(tempfile.mkdtemp(prefix='he-entry-archive-',dir=output));blend=folder/'fixture.blend'
            with (folder/'CREATE.stdout').open('xb') as out,(folder/'CREATE.stderr').open('xb') as err:
                subprocess.run([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',
                    str(ROOT/'verification/fixtures/create_task_entry_scene.py'),'--',str(blend)],
                    stdout=out,stderr=err,check=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            blend_hash=hashlib.sha256(blend.read_bytes()).hexdigest();config=folder/'CONFIG.json'
            save(config,dict(schema_version='1.0',enabled=True,project_root=str(args.entry.parent.parent/'site-packages'),
                expected_identity=pin,state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
            common=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--entry',str(args.entry),
                '--expected-build',args.expected_build]
            client=Client(common+['--worker','--blender',str(args.blender),'--scene',str(blend),
                '--config',str(config),'--scenario',scenario],folder);owned=None
            try:
                client.rpc(1,'initialize',dict(protocolVersion='2025-11-25',capabilities={'elicitation':{'form':{}}}))
                assert client.receive()['id']==1
                child=json.loads((folder/'OWNED_PROCESS.json').read_text(encoding='utf8'))
                assert child['factory_background'] and Path(child['scene'])==blend
                owned=OwnedChild(child['pid'],args.blender)
                client.rpc(2,'tools/call',dict(name='human_eye_scene_observe',arguments={'include_image':False}))
                result=client.receive();metadata=json.loads(result['result']['content'][0]['text'])
                context=json.loads(metadata['routing']['context_text'])
                client.rpc(100,'tools/call',dict(name='human_eye_owned_clearance_goal',arguments={
                    'focal_id':context['focal_id'],'reference_id':context['reference_id'],'target_clearance_m':.001}))
                result=client.receive()
                if result is not None:
                    assert result.get('method')=='elicitation/create',result
                    assert scenario in ('after_first_apply','after_final_archive')
                    client.send(dict(jsonrpc='2.0',id=result['id'],result={'action':'accept','content':{'approve':True}}))
                    assert client.receive() is None
                else:assert scenario in ('after_intake','after_source')
                assert client.process.wait(15)==23
                life=owned.close();owned=None;save(folder/'CHILD_LIFECYCLE.json',life)
                crash=json.loads((folder/'CRASH.json').read_text(encoding='utf8'))
                expected=4 if scenario=='after_final_archive' else 1 if scenario=='after_first_apply' else 0
                assert crash['applied_calls']==expected
                if expected:
                    assert sum(v['physical_meter']['actual_setter_count'] for v in crash['meters'].values())==expected
                    moved=sum(v['physical_meter']['actual_cumulative_translation_m'] for v in crash['meters'].values())
                    initial=json.loads((folder/'INITIAL.json').read_text(encoding='utf8'))
                    native={o['name']:o for o in initial['native_scene']['objects']}
                    initial_gap=min(v[2] for v in native['BluePart']['world_vertices'])-max(v[2] for v in native['GreyBase']['world_vertices'])
                    assert abs((initial_gap-crash['gap_m'])-moved)<1e-12
                    if expected==4:assert abs(crash['gap_m']-.001)<1e-6
                    else:assert 0<moved<=.001 and .001<crash['gap_m']<initial_gap
                else:assert abs(crash['gap_m']-.004)<1e-6 and not crash['physical_meter_registered']
                recovery=subprocess.run(common+['--recover',str(folder/'task-evidence')],check=True,capture_output=True,
                    text=True,encoding='utf8',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                recovered=json.loads(recovery.stdout);save(folder/'RECOVERY.json',recovered)
                assert recovered['fresh_process_no_host_created'] and not recovered['execution_authority']
                row=recovered['rows'][0]
                if scenario=='after_final_archive':
                    assert recovered['terminal_records']==1 and row['recorded_new_setter_count']==4
                else:assert recovered['unknown_records']==1 and row['recorded_new_setter_count'] is None
                assert recovered['training_positives']==0 and not recovered['retry_authorized']
                assert hashlib.sha256(blend.read_bytes()).hexdigest()==blend_hash
                rows.append(dict(round=repeat,scenario=scenario,actual_apply_calls=expected,recovery=row,
                                 client_received_tool_result=False,child_lifecycle=life))
                print(json.dumps(dict(round=repeat,scenario=scenario,passed=True,recovery=row['status'])),flush=True)
            except Exception as exc:save(folder/'FAILURE.json',dict(error=repr(exc)));raise
            finally:
                if client.process.stdin and not client.process.stdin.closed:
                    try:client.process.stdin.close()
                    except BrokenPipeError:pass
                if client.process.poll() is None:
                    try:client.process.wait(10)
                    except subprocess.TimeoutExpired:client.process.kill();client.process.wait()
                if owned is not None:save(folder/'CHILD_CLEANUP_ON_FAILURE.json',owned.close())
                client.err.close();save(folder/'WIRE.json',client.wire)
    save(output/'RESULT.json',dict(passed=True,rows=rows,owned_workers=8,source_sha256=args.expected_build,
        scripted_client_only=True,actual_Codex_UI_approval=False,model_calls=0,normal_unwind_used=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--expected-build',required=True)
    p.add_argument('--blender',type=Path);p.add_argument('--output',type=Path);p.add_argument('--worker',action='store_true')
    p.add_argument('--recover',type=Path);p.add_argument('--scene',type=Path);p.add_argument('--config',type=Path);p.add_argument('--scenario')
    args=p.parse_args();worker(args) if args.worker or args.recover is not None else parent(args)
