"""Installed trusted entry → existing kernel → factory-owned Blender only."""
import argparse,copy,hashlib,importlib.util,json,subprocess,sys,tempfile,time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def run(args):
    spec=importlib.util.spec_from_file_location('_registered_installed',args.entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root'])
    identity,_=module.verify_imported_runtime(proof)
    assert identity['source_sha256']==args.expected_build and identity['implementation_revision']=='v21-registered-execution-candidate-20261101'
    from human_eye_plugin.task_entry import TrustedTaskEntry
    from human_eye_plugin.task_authority import TrustedTaskAuthority,ClearanceTaskSpec,TaskApproval
    from human_eye_plugin.goal_scheduler import _digest
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.goal_continuation import inspect_current_clearance
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    creator=ROOT/'verification/fixtures/create_registered_task_scene.py'
    scenarios=['normal_4_to_1','short_segment_stops_at_original_gate','already_satisfied','deadband_above','deadband_below','revoke_before',
        'revoke_after_first_apply','external_before','original_expiry','lost_apply_reply','completion_ack_loss','config_changed']
    save(output/'REGISTERED_INPUT.json',dict(source_sha256=args.expected_build,rounds=args.rounds,scenarios=scenarios,
        creator_sha256=hashlib.sha256(creator.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_GUI=False,formal_activation=False,model_trials=0,logical_commit_not_OS_preemption=True))
    rows=[]
    for repeat in range(args.rounds):
        for scenario in scenarios:
            folder=Path(tempfile.mkdtemp(prefix='he-registered-',dir=output));blend=folder/'fixture.blend'
            gap={'already_satisfied':.001,'deadband_above':.00100025,'deadband_below':.00099975}.get(scenario,.004)
            created=subprocess.run([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',str(creator),'--',str(blend),str(gap)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (folder/'CREATE.stdout').write_bytes(created.stdout);(folder/'CREATE.stderr').write_bytes(created.stderr)
            assert created.returncode==0 and blend.exists();blend_sha=hashlib.sha256(blend.read_bytes()).hexdigest()
            host=BlenderProcessHost(args.blender,blend);commands=[];original_request=host._request
            def request(command,params,**kwargs):
                commands.append(command);return original_request(command,params,**kwargs)
            host._request=request;pid=host._process.pid;started=time.perf_counter()
            try:
                config=folder/'CONFIG.json'
                pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
                save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pin,
                    state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
                initial=host.capture_evidence();by_name={o['name']:o['object_id'] for o in initial['capture']['meshes']}
                task=ClearanceTaskSpec(by_name['BluePart'],by_name['GreyBase'])
                if scenario=='original_expiry':task=replace(task,limits=replace(task.limits,max_duration_s=1.5))
                calls=[];expected={};config_sha=hashlib.sha256(config.read_bytes()).hexdigest()
                def approve(resolved,scope):
                    accepted=(scope['engine_build_id']==identity['build_id'] and scope['process_id']==pid
                        and scope['connector_config_sha256']==config_sha and scope['host_identity']==expected['initial']['capture']['host_identity']
                        and scope['initial_capture_sha256']==_digest(expected['initial']['capture'])
                        and scope['initial_native_sha256']==_digest(expected['initial']['native_scene'])
                        and resolved.focal_id==task.focal_id and resolved.reference_id==task.reference_id
                        and resolved.target_clearance_m==task.target_clearance_m and resolved.limits==task.limits
                        and resolved.reference_triangle_index in (2,3))
                    calls.append(dict(accepted=accepted,scope=scope))
                    return TaskApproval('registered-'+scenario,'explicit-owned-fixture-only') if accepted else None
                authority=TrustedTaskAuthority('owned-registered-entry',approve);entry=TrustedTaskEntry(config,host,authority)
                expected['initial']=entry._scheduler._capture();admitted=entry.register(task)
                save(folder/'INITIAL.json',expected['initial'])
                assert admitted['status']=='registered',admitted
                key=admitted['registration_id'];save(folder/'ADMISSION.json',admitted)
                before=json.loads(entry.service.state_path.read_text());original_grant=copy.deepcopy(before['goal_authorizations']['records'][key]['grant'])
                parent_before=copy.deepcopy(before['goal_supervision']['records'][admitted['goal_id']])
                if scenario=='revoke_before':entry.revoke(key)
                elif scenario=='external_before':
                    # Deliberate separate typed-host edit on this owned fixture,
                    # before any engine motion goal exists; never user assets.
                    host.apply_transform(dict(focal_id=task.focal_id,reference_id=task.reference_id,
                        translation=[0.,0.,.0001],rotation_euler_deg=[0.,0.,0.]),initial['capture']['revision'])
                elif scenario=='original_expiry':time.sleep(max(0.,admitted['original_deadline_monotonic']-time.perf_counter())+.02)
                elif scenario=='config_changed':config.write_bytes(config.read_bytes()+b' ')
                original_apply=host.apply_transform;fired=[];real_save=entry.service._save;goal_supervision=entry.service.goal_supervision
                def apply(*values,**options):
                    result=original_apply(*values,**options);fired.append(True)
                    if scenario=='revoke_after_first_apply' and len(fired)==1:
                        revoked=entry.revoke(key);assert revoked['persistence']=='pending_executor_stop'
                    if scenario=='lost_apply_reply':raise OSError('injected lost real apply reply')
                    return result
                faults=[]
                def saving(value,runtime,**kwargs):
                    real_save(value,runtime,**kwargs)
                    if scenario=='completion_ack_loss' and not faults and any(r['status']=='completed' for r in value.get('goal_authorizations',{}).get('records',{}).values()):
                        faults.append('completed_save_committed_reply_lost');raise OSError('injected completed save ACK loss')
                def supervision(operation,*values,**kwargs):
                    result=goal_supervision(operation,*values,**kwargs)
                    if scenario=='short_segment_stops_at_original_gate' and operation=='caps':result['caps']['max_steps']=1
                    return result
                with (patch.object(authority,'issue',side_effect=AssertionError('reissue')),
                      patch.object(entry._scheduler,'_claim',side_effect=AssertionError('reclaim')),
                      patch.object(host,'apply_transform',side_effect=apply),patch.object(entry.service,'_save',side_effect=saving),
                      patch.object(entry.service,'goal_supervision',side_effect=supervision)):
                    result=entry.execute(key)
                save(folder/'EXECUTION.json',result)
                state=json.loads(entry.service.state_path.read_text());record=state['goal_authorizations']['records'][key]
                parent=state['goal_supervision']['records'][admitted['goal_id']]
                assert record['grant']==original_grant and len(calls)==1
                assert parent['started_monotonic']==parent_before['started_monotonic'] and parent['deadline_monotonic']==parent_before['deadline_monotonic']
                assert parent['limits']==parent_before['limits']
                after=entry._scheduler._capture();resolved=entry._live[key]['resolved']
                save(folder/'FINAL.json',after)
                old={o['name']:o for o in expected['initial']['native_scene']['objects']}
                new={o['name']:o for o in after['native_scene']['objects']}
                assert old['GreyBase']==new['GreyBase']
                assert {k:v for k,v in old['BluePart'].items() if k not in ('matrix','world_vertices')}=={
                    k:v for k,v in new['BluePart'].items() if k not in ('matrix','world_vertices')}
                assert all(old['BluePart']['matrix'][r][c]==new['BluePart']['matrix'][r][c] for r in range(4) for c in range(4) if (r,c)!=(2,3))
                analytic_gap=min(v[2] for v in new['BluePart']['world_vertices'])-max(v[2] for v in new['GreyBase']['world_vertices'])
                native=inspect_current_clearance(after,entry._scheduler._policy(resolved,identity['build_id']))
                assert abs(analytic_gap-native['current_clearance_m'])<=1e-12
                report=host.motion_goal_status(admitted['goal_id']) if 'motion_begin' in commands else None
                count=report['physical_meter']['actual_setter_count'] if report else 0
                if scenario in ('normal_4_to_1','already_satisfied','deadband_above','deadband_below'):
                    assert result['status']=='completed' and result['task_succeeded'] and native['decision']=='already_satisfied',result
                    assert result['new_setter_count']==count and report['closed'] is True
                    assert abs(analytic_gap-task.target_clearance_m)<=task.clearance_tolerance_m
                    if scenario=='normal_4_to_1':assert count>=3 and len(result['segments'])==1
                    else:assert count==0 and not fired
                elif scenario=='short_segment_stops_at_original_gate':
                    assert result['status']=='review_required' and count==1 and result['new_setter_count']==1,result
                    assert len(result['segments'])==1 and 'review_reason_not_automatically_recoverable' in str(result['reason_codes'])
                elif scenario=='revoke_after_first_apply':
                    assert result['status']=='review_required' and count==1 and result['new_setter_count']==1 and result['executed_this_call'] is True,result
                elif scenario=='lost_apply_reply':
                    assert result['status']=='review_required' and count==1 and result['new_setter_count'] is None and result['executed_this_call'] is not False,result
                elif scenario=='completion_ack_loss':
                    assert faults and result['status']=='review_required' and result['physical_task_succeeded'] is True and result['completion_persistence']=='unknown',result
                    assert result['new_setter_count']==count and native['decision']=='already_satisfied'
                else:assert result['status']!='completed' and count==0 and not fired,result
                replay=entry.execute(key);assert replay.get('executed_this_call',False) is False and replay['new_setter_count']==0
                reader=TrustedTaskEntry(config,host,TrustedTaskAuthority('owned-registered-entry',approve));history=reader.execute(key)
                assert history.get('executed_this_call',False) is False and history['new_setter_count']==0
                if report:assert host.motion_goal_status(admitted['goal_id'])['physical_meter']['actual_setter_count']==count
                row=dict(round=repeat,scenario=scenario,status=result['status'],new_setter_count=result['new_setter_count'],
                    actual_setter_count=count,external_fixture_setters=1 if scenario=='external_before' else 0,
                    clearance_m=native['current_clearance_m'],segments=len(result.get('segments',[])),
                    review_event=result.get('review_event'),approval_calls=len(calls),original_grant_and_parent_window_preserved=True,
                    replay_no_new_setters=True,commands=commands,elapsed_s=time.perf_counter()-started)
                rows.append(row);save(folder/'CHECKED.json',row);save(folder/'PHYSICAL.json',report);save(folder/'NATIVE.json',native)
                save(folder/'INDEPENDENT.json',dict(analytic_axis_box_gap_m=analytic_gap,
                    reference_unchanged=True,focal_local_geometry_unchanged=True,only_world_Z_changed=True))
                print(json.dumps({k:row[k] for k in ('round','scenario','status','new_setter_count','actual_setter_count')}),flush=True)
            except Exception as exc:
                save(folder/'FAILURE.json',dict(error=repr(exc),completed=len(rows)));raise
            finally:
                host.close();assert host._process.poll()==0
                assert hashlib.sha256(blend.read_bytes()).hexdigest()==blend_sha
                save(folder/'PROCESS.json',dict(pid=pid,exit_code=host._process.poll(),input_unchanged=True,shared_GUI=False))
    result=dict(passed=True,source_sha256=args.expected_build,rows=rows,scenarios=len(rows),owned_processes=len(rows),
        formal_activation=False,default_Codex_trusted_event_proven=False,model_trials=0)
    save(output/'RESULT.json',result);print(json.dumps(dict(passed=True,scenarios=len(rows),owned_processes=len(rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--expected-build',required=True)
    p.add_argument('--blender',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rounds',type=int,choices=(1,2,3),default=2);run(p.parse_args())
