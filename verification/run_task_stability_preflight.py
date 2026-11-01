"""Temporal static-domain checks in new owned Blender copies.

Explicit fixture edits are external test actions, counted separately. The
support representative tie alternation is an injected discovery tie-break on
real native geometry, not a claim of changed surfaces being authorized.
"""
import argparse,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def main(args):
    args.output.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_stability_installed',args.entry);entrymodule=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entrymodule;spec.loader.exec_module(entrymodule);proof=entrymodule.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entrymodule.verify_imported_runtime(proof)
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.task_entry import TrustedTaskEntry
    from human_eye_plugin.task_authority import TrustedTaskAuthority,ClearanceTaskSpec,TaskApproval
    from human_eye_plugin.goal_scheduler import _digest
    cases=[('steady_above',.00100025),('steady_below',.00099975),('external_subtolerance',.00100025),
        ('external_outside',.004),('same_plane_representative',.004),('changed_reference',.004)]
    save(args.output/'REGISTRATION.json',dict(cases=cases,observations_or_external_edits_per_sequence=8,
        expectation='unchanged near-band zero writes; external changes stop without rearming; legal representative retains triangle3',
        domain='static exact owned meshes, not noisy sensors',support_tie_break_injected=True,formal_model_calls=0))
    rows=[];creator=ROOT/'verification/fixtures/create_registered_task_scene.py'
    for name,gap in cases:
        folder=Path(tempfile.mkdtemp(prefix='he-registered-',dir=args.output));blend=folder/'fixture.blend'
        build=subprocess.run([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',str(creator),'--',str(blend),str(gap)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert build.returncode==0;original_file=hashlib.sha256(blend.read_bytes()).hexdigest();host=BlenderProcessHost(args.blender,blend)
        try:
            config=folder/'CONFIG.json';pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind')}
            pin.update(protocol_version='2025-03-26',mode='live')
            save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pin,
                state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
            first=host.capture_evidence();ids={m['name']:m['object_id'] for m in first['capture']['meshes']};approvals=[];engine_calls=[];external=[];ties=[]
            task=ClearanceTaskSpec(ids['BluePart'],ids['GreyBase'],reference_triangle_index=3)
            def approve(resolved,scope):
                assert scope['process_id']==host._process.pid and scope['engine_build_id']==identity['build_id']
                assert resolved.reference_triangle_index==3;approvals.append(copy.deepcopy(scope))
                return TaskApproval('owned-stability-'+name,'scripted-owned-fixture-not-human')
            authority=TrustedTaskAuthority('stability',approve);entry=TrustedTaskEntry(config,host,authority)
            observe=entry.service.observe;original_apply=host.apply_transform
            def discovery(*v,**kw):
                result=observe(*v,**kw)
                if name=='same_plane_representative' and kw.get('query',{}).get('support_plane_discovery'):
                    result=copy.deepcopy(result);selector=result['support_plane_discovery']['candidates'][0]['selector']
                    selector['reference_triangle_index']=2 if len(ties)%2==0 else 3;ties.append(selector['reference_triangle_index'])
                return result
            def engine_apply(*v,**kw):
                result=original_apply(*v,**kw);engine_calls.append(result);return result
            with patch.object(entry.service,'observe',side_effect=discovery):
                admission=entry.register(task);key=admission['registration_id'];assert admission['status']=='registered'
                state=json.loads(entry.service.state_path.read_text());original_grant=copy.deepcopy(state['goal_authorizations']['records'][key]['grant'])
                parent_before=copy.deepcopy(state['goal_supervision']['records'][admission['goal_id']]);outcomes=[]
                if name.startswith('steady'):
                    for _ in range(8):
                        snapshot=entry.snapshot(key);assert snapshot['live_registration_available']
                    with patch.object(host,'apply_transform',side_effect=engine_apply):outcomes.append(entry.execute(key))
                    assert outcomes[-1]['status']=='completed' and outcomes[-1]['new_setter_count']==0
                elif name.startswith('external') or name=='changed_reference':
                    for i in range(8):
                        delta=(.00000025 if name=='external_subtolerance' else .0001)*(1 if i==0 else (-2 if i%2 else 2))
                        target=ids['GreyBase'] if name=='changed_reference' else ids['BluePart']
                        capture=host.capture_scene();edit=original_apply(dict(focal_id=target,reference_id=ids['BluePart'] if target==ids['GreyBase'] else ids['GreyBase'],
                            translation=[0.,0.,delta],rotation_euler_deg=[0.,0.,0.]),capture['revision'])
                        assert edit['receipt']['host_execution_verified'] is True;external.append(edit)
                        with patch.object(host,'apply_transform',side_effect=engine_apply):outcomes.append(entry.execute(key))
                        assert outcomes[-1].get('task_succeeded') is not True and not engine_calls
                    assert not entry.snapshot(key)['live_registration_available']
                else:
                    with patch.object(host,'apply_transform',side_effect=engine_apply):outcomes.append(entry.execute(key))
                    assert outcomes[-1]['status']=='completed' and outcomes[-1]['task_succeeded']
                    assert ties==[2,3],ties
                    assert outcomes[-1]['new_setter_count']==len(engine_calls)>=3
                # Repeating the consumed or stopped entry cannot create motion.
                before_count=len(engine_calls)
                with patch.object(host,'apply_transform',side_effect=engine_apply):repeat=entry.execute(key)
                assert len(engine_calls)==before_count and repeat.get('retry_authorized') is False
                state=json.loads(entry.service.state_path.read_text());record=state['goal_authorizations']['records'][key]
                assert record['grant']==original_grant and len(approvals)==1
                parent_after=state['goal_supervision']['records'][admission['goal_id']]
                assert parent_after['deadline_monotonic']==parent_before['deadline_monotonic'] and parent_after['limits']==parent_before['limits']
                final=entry._scheduler._capture()
                if name!='changed_reference':
                    a=next(o for o in first['native_scene']['objects'] if o['object_id']==ids['GreyBase'])
                    b=next(o for o in final['native_scene']['objects'] if o['object_id']==ids['GreyBase']);assert a==b
                assert hashlib.sha256(blend.read_bytes()).hexdigest()==original_file
                row=dict(case=name,engine_setters=len(engine_calls),external_test_setters=len(external),original_grant_unchanged=True,
                    original_budget_unchanged=True,approval_count=len(approvals),ties=ties,outcomes=outcomes,repeat=repeat,
                    initial=first,final=final,input_file_unchanged=True,sensor_hysteresis_certified=False,human_UI_proof=False)
                save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=name,engine_setters=len(engine_calls),external_test_setters=len(external))),flush=True)
        finally:host.close()
    save(args.output/'RESULT.json',dict(runtime_source=identity['source_sha256'],rows=rows,all_passed=True,model_calls=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--blender',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);main(p.parse_args())
