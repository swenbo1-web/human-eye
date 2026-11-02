"""Fixed read-only static constraint worker; inspect/shutdown, no RNA writes."""
import argparse,hashlib,importlib.util,os,sys,time,types,uuid
from pathlib import Path
sys.dont_write_bytecode=True
PREFIX='HUMAN_EYE_CONSTRAINT:'


def run(args):
    import bpy
    root=args.root.resolve();package=types.ModuleType('_human_eye_constraint_reader');package.__path__=[];sys.modules[package.__name__]=package
    for name,pin in (('rig_pose',args.math_sha256),('rig_constraint',args.module_sha256)):
        path=root/'human_eye_plugin'/(name+'.py');blob=path.read_bytes()
        if len(blob)>128*1024 or hashlib.sha256(blob).hexdigest()!=pin:raise ValueError('constraint_module_pin')
        spec=importlib.util.spec_from_file_location(package.__name__+'.'+name,path);module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module;package.__dict__[name]=module;exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)
    core=package.rig_constraint;r=package.rig_pose;r.check_time(args.deadline_ns)
    with args.profile.open('rb') as f:blob=f.read(65537)
    r.require(len(blob)<=65536 and hashlib.sha256(blob).hexdigest()==args.profile_sha256,'constraint_profile_pin');profile=r.decode(blob)
    r.require(bpy.app.background and Path(bpy.data.filepath).resolve()==Path(profile['scene_file'])
        and Path(bpy.app.binary_path).resolve()==Path(profile['blender_executable']),'constraint_owned_input')
    r.require(hashlib.sha256(Path(profile['scene_file']).read_bytes()).hexdigest()==profile['scene_sha256'],'constraint_scene_pin')
    scene=bpy.context.scene;epoch=uuid.uuid4().hex
    mat=lambda v:[[float(x) for x in row] for row in v];vec=lambda v:[float(x) for x in v]
    def flags(obj):
        ids=(obj,) if obj.data is None else (obj,obj.data)
        return dict(animation=any(v.animation_data is not None and (v.animation_data.action is not None or len(v.animation_data.nla_tracks)>0) for v in ids),
            drivers=any(v.animation_data is not None and len(v.animation_data.drivers)>0 for v in ids),object_parent=obj.parent is not None)
    def context():return dict(mode=bpy.context.mode,active_object=scene.view_layers[bpy.context.view_layer.name].objects.active.name_full
        if bpy.context.view_layer.objects.active else None,selected_objects=sorted(v.name_full for v in bpy.context.selected_objects))
    def channels(obj):return dict(rotation_mode=obj.rotation_mode,**{key:vec(getattr(obj,key)) for key in core.CHANNEL_FIELDS})
    def capture():
        r.check_time(args.deadline_ns);r.require(len(scene.objects)<=32 and bpy.context.mode in ('OBJECT','POSE'),'unsupported_constraint_scene_count_or_mode')
        obj=scene.objects.get(profile['object_name']);target=scene.objects.get(profile['target_name'])
        r.require(obj is not None and obj.type=='ARMATURE' and target is not None and target.type=='EMPTY','unsupported_constraint_objects')
        r.require(obj.library is None and obj.data.library is None and target.library is None,'unsupported_constraint_linked_ID')
        r.require(1<=len(obj.data.bones)<=r.MAX_BONES,'unsupported_constraint_bone_limit')
        constraints=[(b.name,c) for b in obj.pose.bones for c in b.constraints]
        r.require(len(obj.constraints)==0 and len(constraints)==1 and len(target.constraints)==0,'unsupported_constraint_count')
        name,c=constraints[0];r.require(name==profile['constraint_bone'] and c.type=='COPY_ROTATION' and c.target is target,'unsupported_constraint_target_or_type')
        # Fail closed on a future Blender setting instead of silently ignoring it.
        settings={p.identifier for p in c.bl_rna.properties if p.identifier!='rna_type' and not p.is_readonly}
        known=core.CONSTRAINT_FIELDS-{'bone','index','type','target_id','target_instance','is_valid'}|{'target'}
        r.require(settings==known,'unsupported_constraint_RNA_settings')
        r.require(c.space_object is None,'unsupported_constraint_custom_space')
        def state():
            data=[dict(name=b.name,parent=b.parent.name if b.parent else None,rest_matrix=mat(b.matrix_local),rest_head=vec(b.head_local),
                rest_tail=vec(b.tail_local),length=float(b.length),inherit_rotation=b.use_inherit_rotation,inherit_scale=b.inherit_scale,
                local_location=b.use_local_location,connected=b.use_connect,bbone_segments=int(b.bbone_segments)) for b in sorted(obj.data.bones,key=lambda v:v.name)]
            channel=[dict(name=b.name,basis=mat(b.matrix_basis),location=vec(b.location),scale=vec(b.scale),mode=b.rotation_mode,
                euler=vec(b.rotation_euler),quaternion=vec(b.rotation_quaternion),axis_angle=vec(b.rotation_axis_angle)) for b in sorted(obj.pose.bones,key=lambda v:v.name)]
            constraint=dict(bone=name,index=0,type=c.type,target_id='blender:'+r.digest(['',target.name_full]),target_instance=str(target.session_uid),is_valid=bool(c.is_valid))
            for key in sorted(known-{'target'}):constraint[key]=getattr(c,key)
            dependency=dict(name=target.name_full,object_id='blender:'+r.digest(['',target.name_full]),object_instance=str(target.session_uid),
                object_type=target.type,matrix_world=mat(target.matrix_world),basis_matrix=mat(target.matrix_basis),channels=channels(target),
                **flags(target),constraints=len(target.constraints),linked=target.library is not None)
            return dict(rest=data,channels=channel,rig_flags=dict(**flags(obj),constraints=len(constraints),pose_position=obj.data.pose_position),
                rig_object_basis=mat(obj.matrix_basis),rig_object_world=mat(obj.matrix_world),target=dependency,constraint=constraint,
                frame=dict(number=scene.frame_current,subframe=scene.frame_subframe),unit_scale_m=float(scene.unit_settings.scale_length),context=context())
        before=state();r.require(before['frame']==profile['expected_frame'],'constraint_wrong_current_frame')
        graph=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(graph);et=target.evaluated_get(graph)
        r.require(set(v.name for v in ev.pose.bones)==set(v.name for v in obj.data.bones),'constraint_evaluated_correspondence');bones=[]
        for b,ch in zip(before['rest'],before['channels']):
            r.check_time(args.deadline_ns);pose=ev.pose.bones[b['name']]
            r.require((pose.parent.name if pose.parent else None)==b['parent'],'constraint_evaluated_parent')
            bones.append(dict(b,pose_matrix=mat(pose.matrix),pose_head=vec(pose.head),pose_tail=vec(pose.tail),basis_matrix=ch['basis'],
                rotation_mode=ch['mode'],rotation_euler=ch['euler'],rotation_quaternion=ch['quaternion']))
        after=state();r.require(before==after,'constraint_RNA_inputs_changed')
        audit=dict(before_sha256=r.digest(before),after_sha256=r.digest(after))
        payload=dict(object_name=obj.name_full,data_name=obj.data.name_full,frame=before['frame'],unit_scale_m=before['unit_scale_m'],
            object_matrix_world=mat(ev.matrix_world),context=before['context'],source_kind='original_rest_and_evaluated_current_pose',flags=before['rig_flags'],bones=bones)
        identity=dict(document_epoch=epoch,object_id='blender:'+r.digest(['',obj.name_full]),object_instance=str(obj.session_uid),data_instance=str(obj.data.session_uid))
        rig=dict(schema='rig-pose-snapshot-v1',identity=identity,payload=payload,source_sha256=r.digest(dict(identity=identity,payload=payload)),
            rig_sha256=r.rig_digest(payload),capture_id=uuid.uuid4().hex,audit=audit)
        dependency=dict(before['target'],matrix_world=mat(et.matrix_world))
        packet=dict(schema='rig-constraint-snapshot-v1',scene_sha256=profile['scene_sha256'],rig=rig,rig_object_basis=before['rig_object_basis'],bone_channels=before['channels'],
            target=dependency,constraint=before['constraint'],audit=audit)
        packet['source_sha256']=core.source_digest(packet);core.validate(packet,deadline_ns=args.deadline_ns);return packet
    def emit(value):
        blob=r.encoded(value);r.require(len(blob)<=r.MAX_BYTES-64,'constraint_output_budget');sys.stdout.write(PREFIX+blob.decode('utf8')+'\n');sys.stdout.flush()
    emit(dict(kind='ready',protocol=core.PROTOCOL,process_id=os.getpid(),scene_sha256=profile['scene_sha256'],profile_sha256=args.profile_sha256,
        module_sha256=args.module_sha256,math_sha256=args.math_sha256,worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        blender_version=bpy.app.version_string,deadline_ns=args.deadline_ns,read_only=True,geometry_setters=0,saves_file=False,generic_exec=False))
    for _ in range(16):
        blob=sys.stdin.buffer.readline(r.MAX_BYTES+1)
        if not blob:break
        key=None
        try:
            request=r.decode(blob);r.require(type(request) is dict and set(request)=={'id','command','deadline_ns'} and type(request['id']) is int,'constraint_typed_request')
            key=request['id'];r.require(type(request['deadline_ns']) is int and request['deadline_ns']==args.deadline_ns,'constraint_original_window')
            r.check_time(args.deadline_ns)
            if request['command']=='shutdown':emit(dict(kind='closed',id=key));break
            r.require(request['command']=='inspect','constraint_readonly_command');emit(dict(kind='snapshot',id=key,snapshot=capture()))
        except Exception as exc:emit(dict(kind='error',id=key,reason=str(exc)[:300],geometry_setters=0))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','profile'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('profile-sha256','module-sha256','math-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--deadline-ns',type=int,required=True);run(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
