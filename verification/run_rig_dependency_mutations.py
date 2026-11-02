"""Test actor mutates ONLY unsaved factory assets; probe remains read-only.

The static/animation/driver sequences are fixed tests, not product commands.
"""
import argparse,json,math,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verification import rig_evaluation_contract as e
from verification.run_rig_evaluation_preflight import outside_observer,save,sha


def run(args):
    import bpy
    assert bpy.app.background and args.scene.resolve().is_relative_to(ROOT/'verification/fixes')
    assert Path(bpy.data.filepath).resolve()==args.scene.resolve() and sha(args.scene)==args.scene_sha256
    assert args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
    paths=[Path(__file__).resolve(),Path(e.__file__).resolve(),Path(e.r.__file__).resolve(),Path(outside_observer.__code__.co_filename).resolve()]
    pins={str(p):sha(p) for p in paths};source_folder=args.output/'SOURCES';source_folder.mkdir()
    for path in paths:(source_folder/path.name).write_bytes(path.read_bytes())
    epoch=uuid.uuid4().hex;deadline=time.perf_counter_ns()+30_000_000_000;packets=[];rows=[]
    obj=bpy.context.scene.objects['Rig'];target=bpy.context.scene.objects['Target'];c=obj.pose.bones['Tip'].constraints[0]
    def observe(label,expected_deg,*,same_output=False):
        # Only the test actor updates evaluation after its explicit mutations.
        bpy.context.view_layer.update();before=outside_observer(bpy)
        packet=e.capture(bpy,epoch,deadline);after=outside_observer(bpy);assert before==after
        e.validate(packet);report=e.copy_candidate(packet)
        pose=next(v for v in packet['evaluated'] if v['id']['name']=='Rig')['bones']
        tip=next(v for v in pose if v['name']=='Tip');angle=math.degrees(math.atan2(tip['matrix'][1][0],tip['matrix'][0][0]))
        assert abs(angle-expected_deg)<.001,(label,angle,expected_deg)
        changed=False;stale_refused=False
        if packets:
            previous=packets[-1];assert previous['document_epoch']==packet['document_epoch']
            changed=previous['source_sha256']!=packet['source_sha256'];assert changed
            if same_output:assert previous['evaluated']==packet['evaluated'],label
            try:e.validate(packet,expected=previous)
            except ValueError as exc:assert 'probe_stale_evidence' in str(exc);stale_refused=True
            else:raise AssertionError('stale packet accepted')
        save(args.output/(label+'.json'),dict(packet=packet,report=report,outside_before=before,outside_after=after))
        packets.append(packet);rows.append(dict(label=label,evaluated_world_z_deg=angle,source_changed=changed,
            same_output_verified=same_output,stale_refused=stale_refused,probe_RNA_unchanged=True))
    if args.mode=='static':
        observe('baseline',65)
        target.rotation_euler.z=math.radians(-40);observe('target_rotation',-40)
        target['source_only_change']=1.;observe('source_without_output_change',-40,same_output=True)
        c.influence=.5;observe('partial_influence',-10)
        c.mute=True;observe('muted',20)
        c.influence=1.;c.mute=False;observe('restored_constraints',-40)
        bpy.context.scene.frame_set(12,subframe=.25);observe('frame_only_change',-40,same_output=True)
        previous_instance=str(target.session_uid);bpy.data.objects.remove(target,do_unlink=True)
        target=bpy.data.objects.new('Target',None);bpy.context.scene.collection.objects.link(target)
        target.rotation_mode='XYZ';target.rotation_euler.z=math.radians(-40);target['source_only_change']=1.;c.target=target
        assert str(target.session_uid)!=previous_instance;observe('same_name_new_instance',-40)
        # Evaluated identity correctly changes, but the actual rig matrices do not.
        old=next(v for v in packets[-2]['evaluated'] if v['id']['name']=='Rig')
        new=next(v for v in packets[-1]['evaluated'] if v['id']['name']=='Rig');assert old==new
    elif args.mode=='animation':
        for frame,angle in ((1,10.),(6,40.),(11,70.)):
            bpy.context.scene.frame_set(frame);observe('frame_'+str(frame),angle)
        source=[next(v for v in p['inputs']['objects'] if v['id']['name']=='Target')['animation'] for p in packets]
        assert source[0]==source[1]==source[2]
    else:
        observe('driver_input_03',math.degrees(.3))
        target['angle']=.7;target.update_tag();observe('driver_input_07',math.degrees(.7))
        target.animation_data.drivers[0].driver.expression='-angle';target.update_tag();observe('driver_expression',-math.degrees(.7))
    assert sha(args.scene)==args.scene_sha256
    assert all(sha(Path(p))==h for p,h in pins.items())
    save(args.output/'RESULT.json',dict(mode=args.mode,steps=rows,original_file_unchanged=True,probe_geometry_setters=0,
        fixture_actor_performs_mutations=True,product_support=False,shared_GUI=False,pins=pins,
        blender_sha256=sha(Path(bpy.app.binary_path))))
    print(json.dumps(dict(mode=args.mode,steps=len(rows),passed=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('static','animation','driver'),required=True)
    p.add_argument('--scene',type=Path,required=True);p.add_argument('--scene-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
