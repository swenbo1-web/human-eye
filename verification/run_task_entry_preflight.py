"""Fixed installed local entry, real owned worker, all setter commands denied."""
import argparse,copy,hashlib,importlib.util,json,subprocess,sys,tempfile,time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def run(args):
    spec=importlib.util.spec_from_file_location('_entry_admission_installed',args.entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root'])
    identity,_=module.verify_imported_runtime(proof)
    assert identity['source_sha256']==args.expected_build and identity['implementation_revision']=='v21-trusted-task-entry-candidate-20261101'
    from human_eye_plugin.task_entry import TrustedTaskEntry,TaskEntryError
    from human_eye_plugin.task_authority import TrustedTaskAuthority,ClearanceTaskSpec,TaskApproval
    from human_eye_plugin.goal_scheduler import _digest
    from human_eye_plugin.blender_process import BlenderProcessHost
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    creator=ROOT/'verification/fixtures/create_task_entry_scene.py'
    save(output/'REGISTERED_INPUT.json',dict(source_sha256=args.expected_build,rounds=3,
        creator_sha256=hashlib.sha256(creator.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scenarios=['normal_duplicate_restart_revoke','approval_denied','JSON_denied','config_changed','real_expiry','postcommit_ack_loss'],
        forbid_all_motion_commands=True,model_trials=0))
    rows=[];processes=[]
    for repeat in range(3):
        folder=Path(tempfile.mkdtemp(prefix='he-entry-',dir=output));blend=folder/'fixture.blend'
        created=subprocess.run([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',str(creator),'--',str(blend)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (folder/'CREATE.stdout').write_bytes(created.stdout);(folder/'CREATE.stderr').write_bytes(created.stderr)
        assert created.returncode==0 and blend.exists();blend_sha=hashlib.sha256(blend.read_bytes()).hexdigest()
        host=BlenderProcessHost(args.blender,blend);commands=[];original=host._request
        allowed={'capabilities','capture','capture_evidence','native_scene_query','native_observation_capabilities',
            'observe_readonly_native','last_readonly_native_audit','native_render_state','shutdown'}
        def readonly(command,params,**kwargs):
            commands.append(command)
            if command not in allowed:raise AssertionError('motion/other command forbidden in A1: '+command)
            return original(command,params,**kwargs)
        host._request=readonly;initial=host.capture_evidence();pid=host._process.pid
        try:
            by_name={o['name']:o['object_id'] for o in initial['capture']['meshes']}
            proposed=ClearanceTaskSpec(by_name['BluePart'],by_name['GreyBase'])
            for scenario in ('normal_duplicate_restart_revoke','approval_denied','JSON_denied','config_changed','real_expiry','postcommit_ack_loss'):
                local=folder/scenario;local.mkdir();config=local/'CONFIG.json'
                pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
                save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pin,
                    state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
                original_config=hashlib.sha256(config.read_bytes()).hexdigest();approval_calls=[];expected={}
                task=replace(proposed,limits=replace(proposed.limits,max_duration_s=1.5)) if scenario=='real_expiry' else proposed
                def approve(resolved,scope):
                    accepted=(scope['engine_build_id']==identity['build_id'] and scope['process_id']==pid
                        and scope['connector_config_sha256']==original_config and scope['host_identity']==expected['initial']['capture']['host_identity']
                        and scope['initial_capture_sha256']==_digest(expected['initial']['capture'])
                        and scope['initial_native_sha256']==_digest(expected['initial']['native_scene'])
                        and resolved.focal_id==task.focal_id and resolved.reference_id==task.reference_id
                        and resolved.target_clearance_m==task.target_clearance_m and resolved.limits==task.limits
                        and resolved.reference_triangle_index in (2,3))
                    approval_calls.append(dict(accepted=accepted,scope=scope))
                    return TaskApproval('entry-fixture-'+scenario,'explicit-owned-fixture-only') if accepted and scenario!='approval_denied' else None
                authority=TrustedTaskAuthority('owned-fixture-local-entry',approve);entry=TrustedTaskEntry(config,host,authority)
                expected['initial']=entry._scheduler._capture();before=len(commands)
                if scenario=='JSON_denied':
                    try:entry.register(task.to_dict())
                    except TaskEntryError:pass
                    else:raise AssertionError('JSON approved')
                    assert len(commands)==before and not approval_calls;status='rejected_before_host'
                elif scenario=='approval_denied':
                    try:entry.register(task)
                    except TaskEntryError:pass
                    else:raise AssertionError('denied event approved')
                    assert not entry._live;status='approval_denied'
                elif scenario=='postcommit_ack_loss':
                    real_save=entry.service._save;lost=[False]
                    def fault(value,runtime,**kwargs):
                        real_save(value,runtime,**kwargs)
                        if value.get('goal_authorizations',{}).get('records') and not lost[0]:
                            lost[0]=True;raise OSError('injected lost admission commit acknowledgment')
                    with patch.object(entry.service,'_save',side_effect=fault):receipt=entry.register(task)
                    assert lost[0] and receipt['status']=='review_required' and not receipt['live_registration_available']
                    assert receipt['durable_status']=='frozen';status='frozen_after_lost_ack'
                else:
                    receipt=entry.register(task);assert receipt['status']=='registered',receipt
                    key=receipt['registration_id'];deadline=receipt['original_deadline_monotonic']
                    assert entry.snapshot(key)['current_scene_revalidated']
                    if scenario=='normal_duplicate_restart_revoke':
                        duplicate=entry.register(task);assert duplicate['duplicate_event'] and duplicate['original_deadline_monotonic']==deadline
                        reader=TrustedTaskEntry(config,host,TrustedTaskAuthority('owned-fixture-local-entry',approve))
                        historical=reader.snapshot(key);assert not historical['live_registration_available']
                        again=reader.register(task);assert not again['live_registration_available'] and again['original_deadline_monotonic']==deadline
                        revoked=entry.revoke(key);assert revoked['status']=='revoked' and not revoked['live_registration_available']
                        assert entry.revoke(key)['original_deadline_monotonic']==deadline;status='registered_duplicate_restart_revoked'
                    elif scenario=='config_changed':
                        config.write_bytes(config.read_bytes()+b' ');stopped=entry.snapshot(key)
                        assert stopped['durable_status']=='frozen' and not stopped['live_registration_available'];status='frozen_config_change'
                    else:
                        time.sleep(max(0.,deadline-time.perf_counter())+.02);expired=entry.snapshot(key)
                        assert expired['durable_status']=='frozen' and not expired['live_registration_available']
                        assert expired['original_deadline_monotonic']==deadline;status='frozen_original_expiry'
                after=host.capture_evidence();assert _digest(after)==_digest(initial)
                state=json.loads(entry.service.state_path.read_text()) if entry.service.state_path.exists() else {}
                assert all(not p['children'] for p in state.get('goal_supervision',{}).get('records',{}).values())
                row=dict(round=repeat,scenario=scenario,status=status,zero_setter_commands=True,geometry_pose_unchanged=True,
                    motion_goal_never_registered=True,children=0,approval_calls=approval_calls,commands=commands[before:])
                rows.append(row);save(local/'CHECKED.json',row)
                if 'receipt' in locals():save(local/'RECEIPT.json',receipt);del receipt
            assert hashlib.sha256(blend.read_bytes()).hexdigest()==blend_sha
        except Exception as exc:
            save(folder/'FAILURE.json',dict(error=repr(exc),completed=len(rows)));raise
        finally:
            host.close();processes.append(dict(pid=pid,exit_code=host._process.poll(),commands=commands))
            save(folder/'PROCESS.json',processes[-1])
    assert len(rows)==18 and all(p['exit_code']==0 for p in processes)
    result=dict(stage='M3-A1 installed zero-motion admission',rows=rows,processes=processes,passed=True,
        source_sha256=args.expected_build,default_Codex_trusted_event_proven=False,automatic_dispatch=False,formal_model_trials=0)
    save(output/'RESULT.json',result);print(json.dumps(dict(passed=True,scenarios=len(rows),owned_processes=3,zero_setter_commands=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--expected-build',required=True)
    p.add_argument('--blender',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
