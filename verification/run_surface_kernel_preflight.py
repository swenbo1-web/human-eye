"""Actual RNA reference/restore checks in a new owned factory process only.

Run with Blender --factory-startup --disable-autoexec --background --python
this_file -- --output NEW_DIR --core-root FIXED_SITE_PACKAGES.
"""
import argparse,copy,hashlib,importlib.util,json,sys,types,os
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main(args):
    import bpy
    assert bpy.app.background and args.output.resolve().parent.name.startswith('20261102_m3_')
    args.output.mkdir(exist_ok=False)
    # Load precisely the dependency-free runtime leaves, without the unrelated
    # package facade requiring Pillow in Blender. No alternate action protocol.
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(args.core_root/'human_eye_plugin')];sys.modules['human_eye_plugin']=package
    from human_eye_plugin import mesh_structure as m,surface_geometry as g
    from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent,diagnose,preview_restore
    from human_eye_plugin.surface_restore import RestoreController,RestoreJournal
    source=args.core_root/'human_eye_plugin/blender_host.py'
    spec=importlib.util.spec_from_file_location('_he_surface_test_host',source);hostmodule=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=hostmodule;exec(compile(source.read_bytes(),str(source),'exec'),hostmodule.__dict__)
    from verification.m3_asset_cases import build
    rows=[]
    cases=[('flat_success','sheet','ok'),('curved_success','curved','ok'),('commit_exception','sheet','commit_error'),
           ('readback_loss','sheet','read_loss'),('recovery_exception','sheet','rollback_error'),('protected_change','sheet','protected'),
           ('declined','sheet','decline'),('already_satisfied','sheet','satisfied'),('revoked_during_approval','sheet','revoke')]
    if args.crash_phase:cases=cases[:1]
    for name,kind,mode in cases:
        bpy.ops.wm.read_factory_settings(use_empty=True);obj=build(bpy,dict(kind='sheet',n=5))[0]
        if kind=='curved':
            for v in obj.data.vertices:v.co.z=.3*(v.co.x*v.co.x+v.co.y*v.co.y)
        obj.data.update();host=hostmodule.BlenderSceneHost(execution_metadata=True,identity_metadata=True);oid=host.object_id(obj)
        reference=m.capture_raw(host,oid);obj.data.calc_loop_triangles()
        tri=[[int(v) for v in t.vertices] for t in obj.data.loop_triangles];polys=[int(t.polygon_index) for t in obj.data.loop_triangles]
        index=12
        if mode!='satisfied':obj.data.vertices[index].co.z-=.0005
        obj.data.update();original=m.capture_raw(host,oid);registry=ReferenceRegistry()
        ref=registry.bind(reference,original,tri,polys,intent=ReferenceIntent('owned_factory_reference_before_explicit_dent','restore center to registered intended surface','same_index_from_owned_copy'))
        before=[list(v.co) for v in obj.data.vertices];geometry_before=g.digest(original['raw']);calls=[]
        report=diagnose(registry.resolve(ref,original),original,budget=m.WorkBudget())
        if mode=='satisfied':assert report['changed_count']==0
        else:assert report['changed_count']==1 and abs(report['vertices'][0]['signed_normal_m']+.0005)<1e-9
        preview=preview_restore(registry.resolve(ref,original),original,[index],budget=m.WorkBudget())
        assert [list(v.co) for v in obj.data.vertices]==before and not preview['execution_authority']
        def capture():
            if mode=='read_loss' and calls:raise OSError('test missing readback after actual RNA write')
            return m.capture_raw(host,oid)
        def setter(i,p):
            assert bpy.app.background and i==index
            obj.data.vertices[i].co=p;obj.data.update();calls.append(dict(index=i,value=list(obj.data.vertices[i].co)))
            if args.crash_phase=='after_setter':
                with (args.output/'PHYSICAL_WRITE.json').open('x',encoding='utf8') as f:
                    json.dump(dict(actual_RNA_setter_count=len(calls),source_after=m.capture_raw(host,oid)['raw'],
                        protected_vertices_unchanged=all(list(v.co)==before[j] for j,v in enumerate(obj.data.vertices) if j!=index)),f)
                    f.flush();os.fsync(f.fileno())
                os._exit(37)
            if mode=='commit_error' and len(calls)==1:raise OSError('test RNA commit then error')
            if mode=='rollback_error':raise OSError('test error after each real RNA commit')
            if mode=='protected':obj.data.vertices[0].co.x+=.001;obj.data.update()
        def approve(scope):
            if mode=='revoke':registry.revoke(ref)
            return dict(approved=mode!='decline',scope_sha256=g.digest(scope))
        journal_root=args.output/name;journal_root.mkdir(exist_ok=False);journal=RestoreJournal(journal_root)
        if args.crash_phase=='preparing':
            update=journal.update
            def crash_update(*values,**fields):
                update(*values,**fields)
                if values[2]=='preparing':os._exit(37)
            journal.update=crash_update
        controller=RestoreController(registry,journal=journal,capture=capture,set_vertex=setter,approve=approve)
        error=None
        try:result=controller.restore(ref,[index],event_id=name)
        except ValueError as exc:result=None;error=str(exc)
        if args.crash_phase=='after_final':
            with (args.output/'PHYSICAL_FINAL.json').open('x',encoding='utf8') as f:
                json.dump(dict(actual_RNA_setter_count=len(calls),source_after=m.capture_raw(host,oid)['raw'],reference_raw=reference['raw'],
                    controller_result=result,client_received_result=False),f);f.flush();os.fsync(f.fileno())
            os._exit(37)
        actual=m.capture_raw(host,oid);after=[list(v.co) for v in obj.data.vertices]
        expected={'ok':'completed','commit_error':'failed_checkpoint_restored','read_loss':'unknown_quarantined',
            'rollback_error':'unknown_quarantined','protected':'unknown_quarantined','satisfied':'completed','revoke':'unknown_quarantined'}
        if mode=='decline':assert result is None and not calls and after==before
        else:
            assert result['status']==expected[mode],result
            assert result['setter_attempts']==len(calls)
            if mode=='commit_error':assert after==before and result['confirmed_changed_setters']==1 and result['rollback_setters']==1
            if mode=='ok':assert actual['raw']==reference['raw'] and len(calls)==1
            if mode in ('satisfied','revoke'):assert not calls
            if mode in ('read_loss','protected'):assert len(calls)==1
        if mode!='protected':assert all(a==b for i,(a,b) in enumerate(zip(after,before)) if i!=index)
        # Reuse cannot issue another action, even with a new id when quarantined.
        previous=len(calls)
        try:controller.restore(ref,[index],event_id=name)
        except ValueError:pass
        else:raise AssertionError('event unexpectedly reused')
        assert len(calls)==previous
        journal.close();recovered=RestoreJournal.inspect(journal_root)
        assert not recovered['restart_can_dispatch']
        if mode in ('read_loss','protected','rollback_error','revoke'):assert recovered['unknown']
        else:assert not recovered['unknown']
        rows.append(dict(case=name,result=result,error=error,actual_RNA_setter_calls=calls,
            original_raw_sha256=geometry_before,final_raw_sha256=g.digest(actual['raw']),
            reference_diagnostic=report,preview=preview,recovered=recovered,protected_vertices_verified=mode!='protected',user_scene_accessed=False))
        print(json.dumps(dict(case=name,status=result['status'] if result else error,actual_setters=len(calls))),flush=True)
    files=['mesh_structure.py','surface_geometry.py','surface_reference.py','surface_restore.py','blender_host.py']
    output=dict(rows=rows,loaded_sources={n:hashlib.sha256((args.core_root/'human_eye_plugin'/n).read_bytes()).hexdigest() for n in files},
        blender_version=bpy.app.version_string,all_cases_passed=True,approval_client='trusted_scripted_factory_embedding_not_Codex_UI',formal_model_calls=0)
    with (args.output/'RESULT.json').open('x',encoding='utf8') as f:json.dump(output,f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--core-root',type=Path,required=True)
    p.add_argument('--crash-phase',choices=('preparing','after_setter','after_final'))
    main(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
