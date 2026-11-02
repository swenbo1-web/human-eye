"""New factory-only rigid operator tasks and actual process interruption QA."""
import argparse,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def load_core(args):
    sys.path.insert(0,str(args.core_root))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_clearance_operator_installed',args.entry.with_name('target_runtime_entry.py'))
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve()
        return entry.verify_imported_runtime(proof)[0]
    from human_eye_plugin.runtime_identity import runtime_identity
    return runtime_identity()


def child(args):
    load_core(args)
    from human_eye_plugin.owned_clearance_task import OperatorClearanceTask
    from human_eye_plugin import owned_clearance_task as module
    from human_eye_plugin.task_entry import TrustedTaskEntry
    from human_eye_plugin.blender_process import BlenderProcessHost
    task=OperatorClearanceTask(args.profile,args.task_root)
    host=BlenderProcessHost(task.profile['blender_executable'],task.profile['scene_file'])
    save(args.output/'WORKER.json',dict(pid=host._process.pid))
    real_apply=host.apply_transform
    def apply(*a,**kw):
        value=real_apply(*a,**kw)
        if args.crash_point=='after_first':
            save(args.output/'FIRST_ACTUAL_SETTER.json',dict(result=value,actual_setters=1));os._exit(37)
        return value
    def entry(*a,**kw):
        value=TrustedTaskEntry(*a,**kw);execute=value.execute
        def run(key):
            if args.crash_point=='before_execute':os._exit(37)
            return execute(key)
        value.execute=run;return value
    publish=task._publish
    def published(name,value):
        publish(name,value)
        if name=='RESULT.json' and args.crash_point=='after_result':os._exit(37)
    task._publish=published
    with patch.object(module,'TrustedTaskEntry',side_effect=entry),patch.object(host,'apply_transform',side_effect=apply):task.run(host)
    raise AssertionError('did not reach registered crash point')


def wait_owned(pid):
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x00100000,False,pid)
        if handle:
            try:assert kernel.WaitForSingleObject(handle,8000)==0,'owned worker EOF exit failed'
            finally:kernel.CloseHandle(handle)
        else:assert ctypes.get_last_error()==87
    else:
        deadline=time.monotonic()+8
        while True:
            try:os.kill(pid,0)
            except ProcessLookupError:return
            assert time.monotonic()<deadline;time.sleep(.05)


def main(args):
    identity=load_core(args);output=args.output.resolve();assert output.is_relative_to(ROOT/'verification/fixes')
    output.mkdir(exist_ok=False)
    from human_eye_plugin import owned_clearance_task as module
    from human_eye_plugin.owned_clearance_task import OperatorClearanceTask
    from human_eye_plugin.task_entry import TrustedTaskEntry
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.blender_host import BlenderSceneHost
    binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary);rows=[]
    creator=ROOT/'verification/fixtures/create_registered_task_scene.py'
    def prepare(name,gap=.004,limits=None):
        folder=Path(tempfile.mkdtemp(prefix='he-registered-',dir=output));blend=folder/'fixture.blend'
        created=subprocess.run([str(binary),'--factory-startup','--disable-autoexec','--background','--python',str(creator),
            '--',str(blend),str(gap)],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (folder/'BUILD.stdout').write_bytes(created.stdout);(folder/'BUILD.stderr').write_bytes(created.stderr);assert created.returncode==0
        config=folder/'CONFIG.json';pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
        save(config,dict(schema_version='1.0',enabled=True,project_root=str(args.core_root),expected_identity=pin,
            state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
        ids={name:BlenderSceneHost.object_id(SimpleNamespace(name_full=name,name=name,library=None)) for name in ('BluePart','GreyBase')}
        spec=dict(focal_id=ids['BluePart'],reference_id=ids['GreyBase'],reference_triangle_index=2)
        if limits:spec['limits']=limits
        profile=dict(schema='owned-clearance-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=str(blend),scene_sha256=sha(blend),connector_config=str(config),connector_config_sha256=sha(config),
            runtime_source_sha256=identity['source_sha256'],task=spec)
        save(folder/'PROFILE.json',profile);save(folder/'CASE.json',dict(name=name,gap=gap))
        return folder,profile
    scenarios=['normal','satisfied','deadband_above','deadband_below','revoke_before','revoke_after_first',
        'external_before','lost_apply_reply','completion_ack_loss','result_receipt_loss','expired','config_changed','small_budget']
    for name in scenarios:
        gap={'satisfied':.001,'deadband_above':.00100025,'deadband_below':.00099975}.get(name,.004)
        limits={'max_duration_s':.1} if name=='expired' else {'max_steps':2} if name=='small_budget' else None
        folder,profile=prepare(name,gap,limits);task=OperatorClearanceTask(folder/'PROFILE.json',folder/'task');error=None;result=None
        host=BlenderProcessHost(binary,folder/'fixture.blend');calls=[];external=[]
        try:
            initial=host.capture_evidence();real_apply=host.apply_transform
            def apply(*a,**kw):
                value=real_apply(*a,**kw);calls.append(value)
                if len(calls)==1:
                    if name=='revoke_after_first':task.entry.revoke(task.admitted['registration_id'])
                    if name=='lost_apply_reply':raise OSError('lost real committed apply response')
                return value
            def create_entry(*a,**kw):
                entry=TrustedTaskEntry(*a,**kw);execute=entry.execute;saving=entry.service._save;fault=[]
                def commit(value,runtime,**kw):
                    saving(value,runtime,**kw)
                    if name=='completion_ack_loss' and not fault and any(r['status']=='completed' for r in value.get('goal_authorizations',{}).get('records',{}).values()):
                        fault.append(True);raise OSError('completion already saved; reply lost')
                def run(key):
                    if name=='revoke_before':entry.revoke(key)
                    if name=='external_before':
                        external.append(real_apply(dict(focal_id=task.spec.focal_id,reference_id=task.spec.reference_id,
                            translation=[0.,0.,.0001],rotation_euler_deg=[0.,0.,0.]),initial['capture']['revision']))
                    return execute(key)
                entry.execute=run;entry.service._save=commit;return entry
            publish=task._publish
            def record(file,value):
                if name=='result_receipt_loss' and file=='RESULT.json':raise OSError('result could not be recorded')
                publish(file,value)
            task._publish=record
            if name=='config_changed':(folder/'CONFIG.json').write_bytes((folder/'CONFIG.json').read_bytes()+b' ')
            with patch.object(module,'TrustedTaskEntry',side_effect=create_entry),patch.object(host,'apply_transform',side_effect=apply):
                try:result=task.run(host)
                except Exception as exc:error=str(exc)
            if name in ('expired','config_changed'):assert error and not calls and not task.started_execution
            elif name=='result_receipt_loss':
                assert not error and result['new_setter_count']==4 and result['physical_task_succeeded'] is True
                assert result['status']=='review_required' and result['task_receipt_persistence']=='unknown'
            else:
                assert result is not None,(name,error)
                if name in ('normal','satisfied','deadband_above','deadband_below'):
                    assert result['status']=='completed' and result['independent_readback']['decision']=='already_satisfied'
                    assert result['new_setter_count']==(4 if name=='normal' else 0),(name,result)
                elif name=='lost_apply_reply':assert result['new_setter_count'] is None and result['status']=='review_required'
                elif name=='completion_ack_loss':assert result['physical_task_succeeded'] is True and result['completion_persistence']=='unknown'
                else:assert result.get('status')!='completed'
            after=host.capture_evidence()
            assert task._protected(initial,after)
            expected=4 if name in ('normal','completion_ack_loss','result_receipt_loss') else 1 if name in ('lost_apply_reply','revoke_after_first','small_budget') else 0
            assert len(calls)==expected,(name,len(calls))
            if result and result.get('independent_physical_meter') is not None:
                assert result['independent_physical_meter']['physical_meter']['actual_setter_count']==expected
        finally:host.close()
        assert sha(folder/'fixture.blend')==profile['scene_sha256']
        # Invalid profile mutation remains a refusal; valid completed tasks also
        # refuse any restart using the original task directory.
        try:OperatorClearanceTask(folder/'PROFILE.json',folder/'task')
        except (FileExistsError,ValueError):pass
        else:raise AssertionError('task restarted')
        row=dict(name=name,folder=str(folder),result=result,error=error,actual_apply_calls=len(calls),
            external_fixture_setters=len(external),same_task_restart_refused=True,original_file_saved=False,
            before=initial,after=after,human_form_verified=False)
        save(folder/'QA.json',row);rows.append(row);print(json.dumps(dict(name=name,passed=True,setters=len(calls))),flush=True)
    for point in ('before_execute','after_first','after_result'):
        folder,profile=prepare('crash_'+point)
        command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--crash-child','--core-root',str(args.core_root),
            '--output',str(folder),'--profile',str(folder/'PROFILE.json'),'--task-root',str(folder/'task'),'--crash-point',point]
        child_reply=subprocess.run(command,capture_output=True,timeout=65);assert child_reply.returncode==37,(point,child_reply.stderr)
        wait_owned(json.loads((folder/'WORKER.json').read_bytes())['pid'])
        old=(folder/'STATE.json').read_bytes();state=json.loads(old);records=state['goal_authorizations']['records']
        (folder/'STATE_BEFORE_RESTART.json').write_bytes(old)
        assert len(records)==1
        if point=='after_result':assert next(iter(records.values()))['status']=='completed'
        try:OperatorClearanceTask(folder/'PROFILE.json',folder/'task')
        except FileExistsError:pass
        else:raise AssertionError('crashed task recreated')
        if point!='after_result':
            second=OperatorClearanceTask(folder/'PROFILE.json',folder/'second_task_root')
            with BlenderProcessHost(binary,folder/'fixture.blend') as host:
                with patch.object(host,'apply_transform',side_effect=AssertionError('pending ledger must not dispatch')) as forbidden:
                    try:second.run(host)
                    except ValueError:pass
                    else:raise AssertionError('another task root bypassed unfinished connector ledger')
                    forbidden.assert_not_called()
            recovered=json.loads((folder/'STATE.json').read_bytes())
            assert set(recovered['goal_authorizations']['records'])==set(records)
            for key,record in records.items():
                assert recovered['goal_authorizations']['records'][key]['grant']==record['grant']
                goal=record['grant']['goal_id'];parent=state['goal_supervision']['records'][goal];current=recovered['goal_supervision']['records'][goal]
                for field in ('started_monotonic','deadline_monotonic','limits','children'):assert current[field]==parent[field]
            (folder/'STATE_AFTER_RESTART.json').write_bytes((folder/'STATE.json').read_bytes())
        assert sha(folder/'fixture.blend')==profile['scene_sha256']
        row=dict(name='crash_'+point,folder=str(folder),exit_code=37,old_grants_budgets_and_child_ids_unchanged=True,
            old_task_restart_refused=True,second_root_cannot_bypass_pending=point!='after_result',state=state,
            actual_first_setter_record=(folder/'FIRST_ACTUAL_SETTER.json').exists())
        save(folder/'QA.json',row);rows.append(row);print(json.dumps(dict(name='crash_'+point,passed=True)),flush=True)
    save(output/'RESULT.json',dict(runtime_source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        cases=rows,shared_GUI=False,formal_model_trials=0,human_form_verified=False,source_or_installed='installed' if args.entry else 'checkout'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--core-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--entry',type=Path);p.add_argument('--crash-child',action='store_true');p.add_argument('--profile',type=Path)
    p.add_argument('--task-root',type=Path);p.add_argument('--crash-point');args=p.parse_args();child(args) if args.crash_child else main(args)
