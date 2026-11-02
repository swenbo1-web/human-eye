"""Owned armature reader. Typed inspect/shutdown only; no RNA setters or save."""
import argparse,hashlib,importlib.util,json,os,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
PREFIX='HUMAN_EYE_RIG:'


def _execute(module,path,blob):
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==path.parents[1]),None)
    if guard is not None:return guard.exec_path(module,path,expected_blob=blob)
    exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)


def run(args):
    import bpy
    root=args.root.resolve();path=root/'human_eye_plugin/rig_pose.py';blob=path.read_bytes()
    assert hashlib.sha256(blob).hexdigest()==args.module_sha256 and len(blob)<=128*1024
    spec=importlib.util.spec_from_file_location('_human_eye_rig_reader_core',path);r=importlib.util.module_from_spec(spec)
    _execute(r,path,blob)
    profile_blob=args.profile.read_bytes();r.require(len(profile_blob)<=65536 and hashlib.sha256(profile_blob).hexdigest()==args.profile_sha256,'worker_profile_pin')
    profile=r.decode(profile_blob);scene=bpy.context.scene
    r.require(bpy.app.background and Path(bpy.data.filepath).resolve()==Path(profile['scene_file'])
        and Path(bpy.app.binary_path).resolve()==Path(profile['blender_executable']),'owned_input_file_or_binary')
    r.require(hashlib.sha256(Path(profile['scene_file']).read_bytes()).hexdigest()==profile['scene_sha256'],'scene_pin')
    epoch=uuid.uuid4().hex
    def matrix(v):return [[float(x) for x in row] for row in v]
    def vector(v):return [float(x) for x in v]
    def flags(obj):
        ids=(obj,obj.data);animation=any(v.animation_data is not None and (v.animation_data.action is not None or len(v.animation_data.nla_tracks)>0) for v in ids)
        drivers=any(v.animation_data is not None and len(v.animation_data.drivers)>0 for v in ids)
        return dict(constraints=len(obj.constraints)+sum(len(v.constraints) for v in obj.pose.bones),animation=animation,
            drivers=drivers,object_parent=obj.parent is not None,pose_position=obj.data.pose_position)
    def context():return dict(mode=bpy.context.mode,active_object=bpy.context.view_layer.objects.active.name_full if bpy.context.view_layer.objects.active else None,
        selected_objects=sorted(v.name_full for v in bpy.context.selected_objects))
    def inputs(obj):
        return dict(frame=dict(number=scene.frame_current,subframe=scene.frame_subframe),context=context(),unit_scale_m=scene.unit_settings.scale_length,
            object_matrix=matrix(obj.matrix_world),flags=flags(obj),rest=[dict(name=v.name,parent=v.parent.name if v.parent else None,
                matrix=matrix(v.matrix_local),head=vector(v.head_local),tail=vector(v.tail_local),inherit_scale=v.inherit_scale,
                inherit_rotation=v.use_inherit_rotation,local_location=v.use_local_location,connected=v.use_connect,bbone_segments=v.bbone_segments) for v in obj.data.bones],
            channels=[dict(name=v.name,mode=v.rotation_mode,location=vector(v.location),scale=vector(v.scale),
                euler=vector(v.rotation_euler),quaternion=vector(v.rotation_quaternion),axis_angle=vector(v.rotation_axis_angle)) for v in obj.pose.bones])
    def capture(deadline):
        r.check_time(deadline);r.require(len(scene.objects)<=32 and bpy.context.mode in ('OBJECT','POSE'),'scene_count_or_mode')
        obj=scene.objects.get(profile['object_name']);r.require(obj is not None and obj.type=='ARMATURE','target_armature')
        r.require(obj.library is None and obj.data.library is None,'linked_rig_not_supported')
        r.require(1<=len(obj.data.bones)<=r.MAX_BONES,'bone_limit')
        before=inputs(obj);r.require(before['frame']==profile['expected_frame'],'wrong_current_frame')
        graph=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(graph)
        r.require(set(v.name for v in evaluated.pose.bones)==set(v.name for v in obj.data.bones),'evaluated_bone_correspondence')
        bones=[]
        for bone in sorted(obj.data.bones,key=lambda v:v.name):
            r.check_time(deadline);pose=evaluated.pose.bones[bone.name];channel=obj.pose.bones[bone.name]
            r.require((pose.parent.name if pose.parent else None)==(bone.parent.name if bone.parent else None),'evaluated_parent_correspondence')
            bones.append(dict(name=bone.name,parent=bone.parent.name if bone.parent else None,rest_matrix=matrix(bone.matrix_local),
                rest_head=vector(bone.head_local),rest_tail=vector(bone.tail_local),length=float(bone.length),
                inherit_rotation=bone.use_inherit_rotation,inherit_scale=bone.inherit_scale,local_location=bone.use_local_location,
                connected=bone.use_connect,bbone_segments=int(bone.bbone_segments),pose_matrix=matrix(pose.matrix),
                pose_head=vector(pose.head),pose_tail=vector(pose.tail),basis_matrix=matrix(channel.matrix_basis),
                rotation_mode=channel.rotation_mode,rotation_euler=vector(channel.rotation_euler),rotation_quaternion=vector(channel.rotation_quaternion)))
        payload=dict(object_name=obj.name_full,data_name=obj.data.name_full,frame=before['frame'],unit_scale_m=float(scene.unit_settings.scale_length),
            object_matrix_world=matrix(evaluated.matrix_world),context=context(),source_kind='original_rest_and_evaluated_current_pose',flags=flags(obj),bones=bones)
        after=inputs(obj);r.require(r.digest(before)==r.digest(after),'RNA_inputs_changed_during_capture')
        identity=dict(document_epoch=epoch,object_id='blender:'+r.digest(['',obj.name_full]),
            object_instance=str(obj.session_uid),data_instance=str(obj.data.session_uid))
        snapshot=dict(schema='rig-pose-snapshot-v1',identity=identity,payload=payload,source_sha256=r.digest(dict(identity=identity,payload=payload)),
            rig_sha256=r.rig_digest(payload),capture_id=uuid.uuid4().hex,audit=dict(before_sha256=r.digest(before),after_sha256=r.digest(after)))
        r.validate(snapshot,deadline_ns=deadline);return snapshot
    def emit(value):
        blob=r.encoded(value);r.require(len(blob)<=r.MAX_BYTES,'worker_output_budget')
        sys.stdout.write(PREFIX+blob.decode('utf8')+'\n');sys.stdout.flush()
    emit(dict(kind='ready',protocol=r.PROTOCOL,process_id=os.getpid(),scene_sha256=profile['scene_sha256'],
        profile_sha256=args.profile_sha256,module_sha256=args.module_sha256,worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        blender_version=bpy.app.version_string,read_only=True,geometry_setters=0,saves_file=False,generic_exec=False))
    for _ in range(16):
        line=sys.stdin.buffer.readline(r.MAX_BYTES+1)
        if not line:break
        key=None
        try:
            request=r.decode(line);r.require(type(request) is dict and set(request)=={'id','command','deadline_ns'}
                and type(request['id']) is int,'typed_request');key=request['id'];deadline=request['deadline_ns']
            r.check_time(deadline);r.require(deadline<=time.perf_counter_ns()+30_000_000_000,'request_window')
            if request['command']=='shutdown':emit(dict(kind='closed',id=key));break
            r.require(request['command']=='inspect','read_only_command')
            emit(dict(kind='snapshot',id=key,snapshot=capture(deadline)))
        except Exception as exc:emit(dict(kind='error',id=key,reason=str(exc)[:300],geometry_setters=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--profile-sha256',required=True);p.add_argument('--module-sha256',required=True)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(args)
