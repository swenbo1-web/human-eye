"""Fixed original/evaluated mesh reader. No geometry, weight or pose writes."""
import argparse,hashlib,importlib.util,os,sys,types,uuid
from pathlib import Path
sys.dont_write_bytecode=True
PREFIX='HUMAN_EYE_SKIN:'


def _execute(module,path,blob):
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==path.parents[1]),None)
    if guard is not None:return guard.exec_path(module,path,expected_blob=blob)
    exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)


def run(args):
    import bpy
    root=args.root.resolve();package=types.ModuleType('_human_eye_skin_reader');package.__path__=[];sys.modules[package.__name__]=package
    for name,pin in (('rig_pose',args.math_sha256),('skin_source',args.module_sha256)):
        path=root/'human_eye_plugin'/(name+'.py');blob=path.read_bytes()
        if len(blob)>128*1024 or hashlib.sha256(blob).hexdigest()!=pin:raise ValueError('skin_module_pin')
        spec=importlib.util.spec_from_file_location(package.__name__+'.'+name,path);module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module;package.__dict__[name]=module;_execute(module,path,blob)
    core=package.skin_source;r=package.rig_pose;r.check_time(args.deadline_ns)
    with args.profile.open('rb') as f:blob=f.read(65537)
    r.require(len(blob)<=65536 and hashlib.sha256(blob).hexdigest()==args.profile_sha256,'skin_profile_pin');profile=r.decode(blob)
    r.require(bpy.app.background and Path(bpy.data.filepath).resolve()==Path(profile['scene_file'])
        and Path(bpy.app.binary_path).resolve()==Path(profile['blender_executable']),'skin_owned_input')
    r.require(hashlib.sha256(Path(profile['scene_file']).read_bytes()).hexdigest()==profile['scene_sha256'],'skin_scene_pin')
    scene=bpy.context.scene;epoch=uuid.uuid4().hex;mat=lambda v:[[float(x) for x in row] for row in v];vec=lambda v:[float(x) for x in v]
    def flags(obj):
        ids=(obj,obj.data)
        return dict(animation=any(v.animation_data is not None and (v.animation_data.action is not None or len(v.animation_data.nla_tracks)>0) for v in ids),
            drivers=any(v.animation_data is not None and len(v.animation_data.drivers)>0 for v in ids),object_parent=obj.parent is not None)
    def context():return dict(mode=bpy.context.mode,active_object=bpy.context.view_layer.objects.active.name_full if bpy.context.view_layer.objects.active else None,
        selected_objects=sorted(v.name_full for v in bpy.context.selected_objects))
    def capture():
        r.check_time(args.deadline_ns);r.require(len(scene.objects)<=32 and bpy.context.mode=='OBJECT','unsupported_skin_scene_count_or_mode')
        rig=scene.objects.get(profile['rig_name']);obj=scene.objects.get(profile['mesh_name'])
        r.require(rig is not None and rig.type=='ARMATURE' and obj is not None and obj.type=='MESH','unsupported_skin_roles')
        r.require(rig.library is None and rig.data.library is None,'unsupported_skin_linked_rig')
        r.require(1<=len(rig.data.bones)<=r.MAX_BONES,'unsupported_skin_bone_limit')
        r.require(1<=len(obj.data.vertices)<=core.MAX_VERTICES,'unsupported_skin_vertex_limit')
        r.require(1<=len(obj.data.polygons)<=core.MAX_TRIANGLES,'unsupported_skin_triangle_limit')
        r.require(len(obj.vertex_groups)<=64,'unsupported_skin_group_limit')
        r.require(all(len(p.vertices)==3 for p in obj.data.polygons),'unsupported_skin_original_nontriangles')
        r.require(all(len(v.groups)<=core.MAX_INFLUENCES for v in obj.data.vertices),'unsupported_skin_influence_limit')
        r.require(len(obj.modifiers)==1,'unsupported_skin_modifier_count')
        r.require(obj.modifiers[0].type=='ARMATURE','unsupported_skin_modifier_type')
        r.require(obj.modifiers[0].object is rig,'unsupported_skin_modifier_rig')
        mod=obj.modifiers[0];fields={p.identifier for p in mod.bl_rna.properties if p.identifier!='rna_type' and not p.is_readonly}
        r.require(fields==core.MOD_RNA_FIELDS,'unsupported_skin_modifier_RNA_settings')
        for key,value in (('show_viewport',True),('show_render',True),('use_vertex_groups',True),('use_bone_envelopes',False),
            ('use_deform_preserve_volume',False),('use_multi_modifier',False),('invert_vertex_group',False),('vertex_group','')):
            r.require(getattr(mod,key)==value,'unsupported_skin_modifier_'+key)
        r.require(obj.data.shape_keys is None,'unsupported_skin_shape_keys')
        r.require(all(group.index==i for i,group in enumerate(obj.vertex_groups)),'skin_group_index_correspondence')
        def state():
            rest=[dict(name=b.name,parent=b.parent.name if b.parent else None,rest_matrix=mat(b.matrix_local),rest_head=vec(b.head_local),rest_tail=vec(b.tail_local),
                length=float(b.length),inherit_rotation=b.use_inherit_rotation,inherit_scale=b.inherit_scale,local_location=b.use_local_location,
                connected=b.use_connect,bbone_segments=int(b.bbone_segments)) for b in sorted(rig.data.bones,key=lambda v:v.name)]
            channels=[dict(name=b.name,basis=mat(b.matrix_basis),location=vec(b.location),scale=vec(b.scale),mode=b.rotation_mode,
                euler=vec(b.rotation_euler),quaternion=vec(b.rotation_quaternion),axis_angle=vec(b.rotation_axis_angle)) for b in sorted(rig.pose.bones,key=lambda v:v.name)]
            settings=dict(name=mod.name,type=mod.type,count=1,rig_id='blender:'+r.digest(['',rig.name_full]),rig_instance=str(rig.session_uid))
            for key in core.MOD_FIELDS-{'name','type','count','rig_id','rig_instance'}:settings[key]=getattr(mod,key)
            return dict(rest=rest,channels=channels,deform=[dict(use_deform=b.use_deform,use_envelope_multiply=b.use_envelope_multiply) for b in sorted(rig.data.bones,key=lambda v:v.name)],
                rig_flags=dict(**flags(rig),constraints=len(rig.constraints)+sum(len(b.constraints) for b in rig.pose.bones),pose_position=rig.data.pose_position),
                rig_basis=mat(rig.matrix_basis),rig_world=mat(rig.matrix_world),mesh_basis=mat(obj.matrix_basis),mesh_world=mat(obj.matrix_world),
                mesh_flags=dict(**flags(obj),linked=obj.library is not None or obj.data.library is not None,shape_keys=obj.data.shape_keys is not None,constraints=len(obj.constraints)),
                vertices=[vec(v.co) for v in obj.data.vertices],triangles=[list(p.vertices) for p in obj.data.polygons],
                weights=[sorted([[g.group,float(g.weight)] for g in v.groups]) for v in obj.data.vertices],groups=[g.name for g in obj.vertex_groups],modifier=settings,
                modifier_RNA={key:('blender:'+r.digest(['',mod.object.name_full]) if key=='object' else getattr(mod,key)) for key in sorted(fields)},
                frame=dict(number=scene.frame_current,subframe=scene.frame_subframe),unit_scale_m=float(scene.unit_settings.scale_length),context=context())
        before=state();r.require(before['frame']==profile['expected_frame'],'skin_wrong_current_frame')
        graph=bpy.context.evaluated_depsgraph_get();er=rig.evaluated_get(graph);em=obj.evaluated_get(graph)
        r.require(er.is_evaluated and em.is_evaluated and er.original==rig and em.original==obj
            and em.data.as_pointer()!=obj.data.as_pointer(),'skin_evaluated_object_source_required')
        r.require(set(b.name for b in er.pose.bones)==set(b['name'] for b in before['rest']),'skin_evaluated_bones');bones=[]
        for b,ch in zip(before['rest'],before['channels']):
            r.check_time(args.deadline_ns);p=er.pose.bones[b['name']];r.require((p.parent.name if p.parent else None)==b['parent'],'skin_evaluated_parent')
            bones.append(dict(b,pose_matrix=mat(p.matrix),pose_head=vec(p.head),pose_tail=vec(p.tail),basis_matrix=ch['basis'],
                rotation_mode=ch['mode'],rotation_euler=ch['euler'],rotation_quaternion=ch['quaternion']))
        r.require(len(em.data.vertices)==len(before['vertices']) and len(em.data.polygons)==len(before['triangles']),'skin_evaluated_geometry_count')
        mesh=dict(identity=dict(name=obj.name_full,object_id='blender:'+r.digest(['',obj.name_full]),object_instance=str(obj.session_uid),data_name=obj.data.name_full,data_instance=str(obj.data.session_uid)),
            object_matrix_world=mat(em.matrix_world),basis_matrix=before['mesh_basis'],vertices=before['vertices'],triangles=before['triangles'],weights=before['weights'],groups=before['groups'],
            evaluated_vertices=[vec(v.co) for v in em.data.vertices],evaluated_triangles=[list(p.vertices) for p in em.data.polygons],flags=before['mesh_flags'],modifier=before['modifier'])
        after=state();r.require(before==after,'skin_RNA_inputs_changed');audit=dict(before_sha256=r.digest(before),after_sha256=r.digest(after))
        payload=dict(object_name=rig.name_full,data_name=rig.data.name_full,frame=before['frame'],unit_scale_m=before['unit_scale_m'],object_matrix_world=mat(er.matrix_world),context=before['context'],
            source_kind='original_rest_and_evaluated_current_pose',flags=before['rig_flags'],bones=bones)
        identity=dict(document_epoch=epoch,object_id='blender:'+r.digest(['',rig.name_full]),object_instance=str(rig.session_uid),data_instance=str(rig.data.session_uid))
        rig_packet=dict(schema='rig-pose-snapshot-v1',identity=identity,payload=payload,source_sha256=r.digest(dict(identity=identity,payload=payload)),rig_sha256=r.rig_digest(payload),capture_id=uuid.uuid4().hex,audit=audit)
        packet=dict(schema='skin-source-snapshot-v1',scene_sha256=profile['scene_sha256'],rig=rig_packet,rig_object_basis=before['rig_basis'],bone_channels=before['channels'],deform_bones=before['deform'],mesh=mesh,audit=audit)
        packet['source_sha256']=core.source_digest(packet);core.validate(packet,deadline_ns=args.deadline_ns);return packet
    def emit(value):
        blob=r.encoded(value);r.require(len(blob)<=r.MAX_BYTES-64,'skin_response_budget');sys.stdout.write(PREFIX+blob.decode('utf8')+'\n');sys.stdout.flush()
    emit(dict(kind='ready',protocol=core.PROTOCOL,process_id=os.getpid(),scene_sha256=profile['scene_sha256'],profile_sha256=args.profile_sha256,module_sha256=args.module_sha256,
        math_sha256=args.math_sha256,worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),blender_version=bpy.app.version_string,deadline_ns=args.deadline_ns,
        read_only=True,geometry_setters=0,saves_file=False,generic_exec=False))
    for _ in range(16):
        blob=sys.stdin.buffer.readline(r.MAX_BYTES+1)
        if not blob:break
        key=None
        try:
            request=r.decode(blob);r.require(type(request) is dict and set(request)=={'id','command','deadline_ns'} and type(request['id']) is int,'skin_typed_request');key=request['id']
            r.require(type(request['deadline_ns']) is int and request['deadline_ns']==args.deadline_ns,'skin_original_window');r.check_time(args.deadline_ns)
            if request['command']=='shutdown':emit(dict(kind='closed',id=key));break
            r.require(request['command']=='inspect','skin_readonly_command');emit(dict(kind='snapshot',id=key,snapshot=capture()))
        except Exception as exc:emit(dict(kind='error',id=key,reason=str(exc)[:300],geometry_setters=0))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','profile'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('profile-sha256','module-sha256','math-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--deadline-ns',type=int,required=True);run(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
