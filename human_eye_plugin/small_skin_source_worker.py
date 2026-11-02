"""Fixed-file small LBS source producer. No edit, frame, save or generic command.

Captures raw dependency data; the host independent consumer owns admission.
The extractor retains the B3a field coverage but is a separately pinned runtime.
"""
import argparse,hashlib,importlib.util,json,os,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
PREFIX=b'HUMAN_EYE_SMALL_SKIN:'
LIMIT=512*1024
LIMITS=dict(vertices=256,triangles=256,bones=16,objects=16,parent_depth=8,groups=32,influences=8,edges=768)
def require(value,reason):
    if not value:raise ValueError('small_skin_'+reason)
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(deadline):require(type(deadline) is int and time.perf_counter_ns()<deadline,'original_deadline')
def decode(blob):
    require(len(blob)<=LIMIT,'byte_budget')
    def unique(pairs):
        out={}
        for k,v in pairs:require(k not in out,'duplicate_JSON_key');out[k]=v
        return out
    return json.loads(blob,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('small_skin_nonfinite')))
def source_digest(packet):return digest({k:v for k,v in packet.items() if k not in ('capture_id','source_sha256')})



def precheck_dependencies(mesh,rig,deadline):
    """Cheap domain exits BEFORE depsgraph evaluation, without rewriting data."""
    check(deadline)
    require(mesh.data.shape_keys is None,'shape_keys')
    require(len(mesh.modifiers)==1,'modifier_count')
    mod=mesh.modifiers[0]
    require(mod.type=='ARMATURE' and mod.object is rig,'modifier_binding')
    require(mod.use_deform_preserve_volume is False,'DQ')
    require(mod.use_bone_envelopes is False,'envelopes')
    require(mod.use_multi_modifier is False and mod.invert_vertex_group is False
        and mod.vertex_group=='' and mod.use_vertex_groups is True
        and mod.show_render is True and mod.show_viewport is True
        and mod.is_override_data is False,'modifier_semantics')
    check(deadline)


def precheck_evaluated(mesh,rig,em,er,deadline):
    """Only O(1) collection counts before any evaluated array expansion."""
    check(deadline)
    require(1<=len(em.data.vertices)<=LIMITS['vertices']
        and len(em.data.vertices)==len(mesh.data.vertices),'evaluated_vertex_count')
    require(1<=len(em.data.polygons)<=LIMITS['triangles']
        and len(em.data.polygons)==len(mesh.data.polygons),'evaluated_topology')
    require(1<=len(er.pose.bones)<=LIMITS['bones']
        and len(er.pose.bones)==len(rig.data.bones),'evaluated_bone_count')
    check(deadline)

def run(args):
    import bpy
    deadline=args.deadline_ns;check(deadline)
    with args.profile.open('rb') as f:profile_bytes=f.read(65537)
    require(len(profile_bytes)<=65536 and hashlib.sha256(profile_bytes).hexdigest()==args.profile_sha256,'profile_pin');p=decode(profile_bytes)
    require(bpy.app.background and Path(bpy.data.filepath).resolve()==Path(p['scene_file'])
        and Path(bpy.app.binary_path).resolve()==Path(p['blender_executable']),'owned_fixed_file')
    require(sha(Path(p['scene_file']))==p['scene_sha256'] and sha(Path(__file__))==args.worker_sha256,'input_or_probe_pin')
    require(set(p)=={'schema','blender_executable','blender_sha256','scene_file','scene_sha256','mesh_name','rig_name','expected_frame','unit_scale_m','runtime_source_sha256'}
        and p['schema']=='small-skin-source-operator-profile-v1','profile_fields')
    root=args.root.resolve()
    require(sha(root/'human_eye_plugin/small_skin_source.py')==args.module_sha256 and sha(root/'human_eye_plugin/rig_pose.py')==args.math_sha256,'consumer_math_pin')
    require(sha(Path(bpy.app.binary_path))==p['blender_sha256'],'binary_pin')
    spec=importlib.util.spec_from_file_location('_small_skin_runtime_identity',root/'human_eye_plugin/runtime_identity.py')
    runtime=importlib.util.module_from_spec(spec);path=root/'human_eye_plugin/runtime_identity.py'
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==root),None)
    if guard is not None:guard.exec_path(runtime,path)
    else:
        blob=path.read_bytes();exec(compile(blob,str(path),'exec',dont_inherit=True),runtime.__dict__)
    require(runtime.runtime_identity()['source_sha256']==p['runtime_source_sha256'] and runtime.check_source_drift()['compatible'],'runtime_pin')
    scene=bpy.context.scene;rig=scene.objects.get(p['rig_name']);mesh=scene.objects.get(p['mesh_name']);epoch=uuid.uuid4().hex
    require(dict(number=scene.frame_current,subframe=float(scene.frame_subframe))==p['expected_frame'],'fixed_frame')
    require(float(scene.unit_settings.scale_length)==p['unit_scale_m'],'fixed_unit')
    require(rig is not None and rig.type=='ARMATURE' and mesh is not None and mesh.type=='MESH','roles')
    mat=lambda m:[[float(x) for x in row] for row in m]
    vec=lambda v:[float(x) for x in v]
    def ref(v):
        return None if v is None else dict(name=v.name_full,id_type=v.id_type,session_uid=int(v.session_uid),linked=v.library is not None)
    def scalars(value,exclude=()):
        out={}
        for prop in value.bl_rna.properties:
            name=prop.identifier
            if name=='rna_type' or name in exclude:continue
            if prop.type in ('BOOLEAN','INT','FLOAT','STRING','ENUM'):
                current=getattr(value,name)
                out[name]=sorted(current) if isinstance(current,set) else list(current) if getattr(prop,'is_array',False) else current
        return out
    def modifiers(values):return [dict(type=v.type,settings=scalars(v)) for v in values]
    def driver(value):
        if value is None:return None
        return dict(type=value.type,expression=value.expression,use_self=value.use_self,
            variables=[dict(name=v.name,type=v.type,targets=[dict(settings=scalars(t),id=ref(t.id)) for t in v.targets]) for v in value.variables])
    def curve(value):
        check(deadline)
        require(len(value.keyframe_points)<=256 and len(value.sampled_points)<=256,'curve_point_limit')
        keys=[dict(co=vec(k.co),handle_left=vec(k.handle_left),handle_right=vec(k.handle_right),
            interpolation=k.interpolation,easing=k.easing,type=k.type,amplitude=float(k.amplitude),back=float(k.back),period=float(k.period),
            handle_left_type=k.handle_left_type,handle_right_type=k.handle_right_type) for k in value.keyframe_points]
        return dict(data_path=value.data_path,array_index=value.array_index,extrapolation=value.extrapolation,
            mute=value.mute,is_valid=value.is_valid,auto_smoothing=value.auto_smoothing,keys=keys,
            sampled_points=[vec(s.co) for s in value.sampled_points],modifiers=modifiers(value.modifiers),driver=driver(value.driver))
    def curves(values):
        require(len(values)<=64,'curve_limit');return [curve(v) for v in values]
    def slot(value):return None if value is None else dict(identifier=value.identifier,handle=value.handle,target_id_type=value.target_id_type)
    def nla_strip(value,depth=0):
        check(deadline);require(depth<=2 and len(value.strips)<=16,'nla_depth_or_count');return dict(settings=scalars(value),action=None if value.action is None else value.action.name_full,
            action_id=ref(value.action),action_slot=slot(value.action_slot),fcurves=curves(value.fcurves),
            modifiers=modifiers(value.modifiers),strips=[nla_strip(v,depth+1) for v in value.strips])
    def animation(value):
        a=value.animation_data
        if a is None:return None
        require(len(a.nla_tracks)<=16 and all(len(t.strips)<=16 for t in a.nla_tracks),'nla_track_limit')
        return dict(action=None if a.action is None else a.action.name_full,action_id=ref(a.action),
            action_slot=slot(a.action_slot),action_slot_handle=a.action_slot_handle,last_slot_identifier=a.last_slot_identifier,
            action_tweak_storage=None if a.action_tweak_storage is None else a.action_tweak_storage.name_full,
            action_tweak_storage_id=ref(a.action_tweak_storage),action_slot_handle_tweak_storage=a.action_slot_handle_tweak_storage,
            use_pin=a.use_pin,use_nla=a.use_nla,use_tweak_mode=a.use_tweak_mode,
            action_blend_type=a.action_blend_type,action_extrapolation=a.action_extrapolation,action_influence=float(a.action_influence),
            drivers=curves(a.drivers),nla_tracks=[dict(name=t.name,mute=t.mute,is_solo=t.is_solo,
                strips=[nla_strip(s) for s in t.strips]) for t in a.nla_tracks])
    def actions():
        require(len(bpy.data.actions)<=16,'action_limit');out=[]
        for a in sorted(bpy.data.actions,key=lambda v:v.name):
            check(deadline);require(len(a.layers)<=4 and len(a.slots)<=16,'action_layer_slot_limit')
            layers=[]
            for layer in a.layers:
                require({v.identifier for v in layer.bl_rna.properties}=={'rna_type','name','strips'},'action_layer_RNA_domain')
                require(len(layer.strips)<=4,'action_strip_limit')
                strips=[]
                for strip in layer.strips:
                    require({v.identifier for v in strip.bl_rna.properties}=={'rna_type','type','channelbags'},'action_strip_RNA_domain')
                    require(strip.type=='KEYFRAME','action_strip_kind');require(len(strip.channelbags)<=4,'action_channelbag_limit')
                    strips.append(dict(type=strip.type,channelbags=[dict(slot_handle=b.slot_handle,fcurves=curves(b.fcurves)) for b in strip.channelbags]))
                layers.append(dict(name=layer.name,strips=strips))
            out.append(dict(name=a.name_full,identity=ref(a),linked=a.library is not None,override=a.override_library is not None,
                is_action_legacy=a.is_action_legacy,is_action_layered=a.is_action_layered,use_frame_range=a.use_frame_range,
                use_cyclic=a.use_cyclic,frame_start=float(a.frame_start),frame_end=float(a.frame_end),frame_range=vec(a.frame_range),
                curve_frame_range=vec(a.curve_frame_range),slots=[dict(slot(s),name=s.name_display,users=[ref(v) for v in s.users()]) for s in a.slots],layers=layers))
        return out
    def constraints(values):
        return [dict(type=v.type,name=v.name,settings=scalars(v),targets={prop.identifier:ref(getattr(v,prop.identifier))
            for prop in v.bl_rna.properties if prop.type=='POINTER' and isinstance(getattr(v,prop.identifier),bpy.types.ID)}) for v in values]
    def obj(value):
        return dict(name=value.name_full,type=value.type,identity=ref(value),data_identity=ref(value.data),
            parent=None if value.parent is None else value.parent.name_full,parent_identity=ref(value.parent),
            parent_type=value.parent_type,parent_bone=value.parent_bone,
            matrix_basis=mat(value.matrix_basis),matrix_local=mat(value.matrix_local),matrix_parent_inverse=mat(value.matrix_parent_inverse),matrix_world=mat(value.matrix_world),
            location=vec(value.location),scale=vec(value.scale),rotation_mode=value.rotation_mode,rotation_euler=vec(value.rotation_euler),
            rotation_quaternion=vec(value.rotation_quaternion),rotation_axis_angle=vec(value.rotation_axis_angle),
            delta_location=vec(value.delta_location),delta_scale=vec(value.delta_scale),delta_rotation_euler=vec(value.delta_rotation_euler),delta_rotation_quaternion=vec(value.delta_rotation_quaternion),
            constraints=constraints(value.constraints),object_linked=value.library is not None,data_linked=value.data is not None and value.data.library is not None,
            object_override=value.override_library is not None,data_override=value.data is not None and value.data.override_library is not None,
            animation=dict(object=animation(value),data=None if value.data is None else animation(value.data)))
    def rest_bones():
        out=[]
        for b in sorted(rig.data.bones,key=lambda v:v.name):
            raw=rig.pose.bones[b.name]
            out.append(dict(name=b.name,parent=None if b.parent is None else b.parent.name,rest_matrix=mat(b.matrix_local),
                rest_head=vec(b.head_local),rest_tail=vec(b.tail_local),length=float(b.length),inherit_rotation=b.use_inherit_rotation,
                inherit_scale=b.inherit_scale,local_location=b.use_local_location,connected=b.use_connect,bbone_segments=b.bbone_segments,
                basis_matrix=mat(raw.matrix_basis),location=vec(raw.location),scale=vec(raw.scale),rotation_mode=raw.rotation_mode,
                rotation_euler=vec(raw.rotation_euler),rotation_quaternion=vec(raw.rotation_quaternion),rotation_axis_angle=vec(raw.rotation_axis_angle),
                pose_matrix=mat(raw.matrix),pose_head=vec(raw.head),pose_tail=vec(raw.tail),use_deform=b.use_deform,
                use_envelope_multiply=b.use_envelope_multiply,constraints=constraints(raw.constraints),custom_shape=ref(raw.custom_shape)))
        return out
    def geometry(value):
        data=value.data;require(len(data.vertices)<=256 and len(data.polygons)<=256,'audit_geometry_limit')
        return dict(vertices=[vec(v.co) for v in data.vertices],triangles=[list(v.vertices) for v in data.polygons],
            edges=[list(e.vertices) for e in data.edges],weights=[sorted([[g.group,float(g.weight)] for g in v.groups]) for v in data.vertices],
            groups=[g.name for g in value.vertex_groups])
    def state():
        check(deadline);require(len(scene.objects)<=LIMITS['objects'],'object_limit')
        require(len(mesh.data.vertices)<=256 and len(mesh.data.polygons)<=256 and len(rig.data.bones)<=16,'source_size')
        require(len(mesh.vertex_groups)<=32 and all(len(v.groups)<=8 for v in mesh.data.vertices),'weight_limits')
        closure={}
        for role in (rig,mesh):
            current=role;seen=set()
            while current is not None:
                require(current.name_full not in seen,'parent_cycle');seen.add(current.name_full)
                require(len(seen)<=8 and current.name_full in scene.objects,'parent_depth_or_external');closure[current.name_full]=current;current=current.parent
        settings=[]
        for mod in mesh.modifiers:
            settings.append(dict(name=mod.name,type=mod.type,settings=scalars(mod),
                object=None if mod.type!='ARMATURE' or mod.object is None else mod.object.name_full,
                object_identity=None if mod.type!='ARMATURE' else ref(mod.object)))
        return dict(frame=dict(number=scene.frame_current,subframe=float(scene.frame_subframe)),unit_scale_m=float(scene.unit_settings.scale_length),
            context=dict(mode=bpy.context.mode,active_object=None if bpy.context.view_layer.objects.active is None else bpy.context.view_layer.objects.active.name_full,
                selected_objects=sorted(v.name_full for v in bpy.context.selected_objects)),
            scene=dict(name=scene.name_full,fps=int(scene.render.fps),fps_base=float(scene.render.fps_base),
                objects=[dict(name=o.name_full,type=o.type,identity=ref(o),data_identity=ref(o.data)) for o in sorted(scene.objects,key=lambda v:v.name)]),
            closure=[obj(o) for o in sorted(closure.values(),key=lambda v:v.name)],
            rig=dict(name=rig.name_full,data_name=rig.data.name_full,pose_position=rig.data.pose_position,bones=rest_bones()),
            mesh=dict(name=mesh.name_full,data_name=mesh.data.name_full,**geometry(mesh),modifier=settings,
                shape_keys=None if mesh.data.shape_keys is None else dict(identity=ref(mesh.data.shape_keys),keys=[k.name for k in mesh.data.shape_keys.key_blocks])),actions=actions())
    def independent_audit():
        # Separate scene-wide reader, not a hash of capture()'s selected fields.
        check(deadline);require(len(scene.objects)<=16 and all(o.type!='MESH' or len(o.data.vertices)<=256 and len(o.data.polygons)<=256 for o in scene.objects),'audit_scene_limit')
        return dict(frame=[scene.frame_current,scene.frame_subframe],fps=scene.render.fps,fps_base=scene.render.fps_base,unit=scene.unit_settings.scale_length,dirty=bpy.data.is_dirty,
            active=None if bpy.context.view_layer.objects.active is None else bpy.context.view_layer.objects.active.name,
            mode=bpy.context.mode,selected=sorted(o.name for o in bpy.context.selected_objects),
            objects=[dict(name=o.name,type=o.type,parent=None if o.parent is None else o.parent.name,
                basis=[list(row) for row in o.matrix_basis],world=[list(row) for row in o.matrix_world],parent_inverse=[list(row) for row in o.matrix_parent_inverse],
                location=list(o.location),scale=list(o.scale),rotation_mode=o.rotation_mode,
                quaternion=list(o.rotation_quaternion),euler=list(o.rotation_euler),axis_angle=list(o.rotation_axis_angle),
                geometry=None if o.type!='MESH' else dict(v=[list(v.co) for v in o.data.vertices],p=[list(v.vertices) for v in o.data.polygons],
                    w=[[[g.group,g.weight] for g in v.groups] for v in o.data.vertices]),
                bones=None if o.type!='ARMATURE' else [dict(name=b.name,rest=[list(row) for row in b.matrix_local],
                    pose=[list(row) for row in o.pose.bones[b.name].matrix],loc=list(o.pose.bones[b.name].location),scale=list(o.pose.bones[b.name].scale),
                    quaternion=list(o.pose.bones[b.name].rotation_quaternion)) for b in sorted(o.data.bones,key=lambda b:b.name)]) for o in sorted(scene.objects,key=lambda o:o.name)])
    def capture():
        check(deadline)
        require(runtime.check_source_drift()['compatible'],'runtime_changed')
        require(sha(Path(p['scene_file']))==p['scene_sha256'],'scene_changed')
        require(scene.frame_current==p['expected_frame']['number'] and scene.frame_subframe==p['expected_frame']['subframe'],'fixed_frame')
        require(float(scene.unit_settings.scale_length)==p['unit_scale_m'],'fixed_unit')
        require(1<=len(mesh.data.vertices)<=LIMITS['vertices'],'vertex_limit')
        require(1<=len(mesh.data.polygons)<=LIMITS['triangles'],'triangle_limit')
        require(1<=len(rig.data.bones)<=LIMITS['bones'],'bone_limit')
        require(len(mesh.data.edges)<=LIMITS['edges'],'edge_limit')
        precheck_dependencies(mesh,rig,deadline)
        audit_before=independent_audit();before=state();graph=bpy.context.evaluated_depsgraph_get();er=rig.evaluated_get(graph);em=mesh.evaluated_get(graph)
        require(er.is_evaluated and em.is_evaluated and er.original==rig and em.original==mesh and em.data.as_pointer()!=mesh.data.as_pointer(),'evaluated_links')
        precheck_evaluated(mesh,rig,em,er,deadline)
        ev=dict(rig_matrix_world=mat(er.matrix_world),mesh_matrix_world=mat(em.matrix_world),bones=[dict(name=b.name,parent=None if b.parent is None else b.parent.name,
            pose_matrix=mat(b.matrix),pose_head=vec(b.head),pose_tail=vec(b.tail)) for b in sorted(er.pose.bones,key=lambda b:b.name)],
            vertices=[vec(v.co) for v in em.data.vertices],triangles=[list(poly.vertices) for poly in em.data.polygons],original_links_verified=True)
        after=state();audit_after=independent_audit();require(before==after,'RNA_changed');require(audit_before==audit_after,'independent_RNA_changed')
        require(sha(Path(p['scene_file']))==p['scene_sha256'],'scene_changed');check(deadline)
        packet=dict(schema='small-skin-source-snapshot-v1',identity=dict(document_epoch=epoch,scene_sha256=p['scene_sha256'],profile_sha256=args.profile_sha256,
            worker_sha256=args.worker_sha256,module_sha256=args.module_sha256,math_sha256=args.math_sha256,binary_sha256=p['blender_sha256'],runtime_source_sha256=p['runtime_source_sha256'],process_id=os.getpid()),inputs=before,evaluated=ev,
            audit=dict(before_sha256=digest(before),after_sha256=digest(after),independent_before_sha256=digest(audit_before),independent_after_sha256=digest(audit_after)),capture_id=uuid.uuid4().hex)
        packet['source_sha256']=source_digest(packet);require(len(encoded(packet))<=LIMIT-1024,'snapshot_byte_budget');return packet
    def emit(v):
        blob=encoded(v);require(len(blob)<=LIMIT,'wire_budget');sys.stdout.buffer.write(PREFIX+blob+b'\n');sys.stdout.buffer.flush()
    emit(dict(kind='ready',protocol='owned-small-skin-source-readonly-v1',process_id=os.getpid(),profile_sha256=args.profile_sha256,
        worker_sha256=args.worker_sha256,module_sha256=args.module_sha256,math_sha256=args.math_sha256,runtime_source_sha256=p['runtime_source_sha256'],
        scene_sha256=p['scene_sha256'],binary_sha256=p['blender_sha256'],document_epoch=epoch,deadline_ns=deadline,
        mesh_identity=ref(mesh),mesh_data_identity=ref(mesh.data),rig_identity=ref(rig),rig_data_identity=ref(rig.data),
        unit_scale_m=float(scene.unit_settings.scale_length),frame=dict(number=scene.frame_current,subframe=float(scene.frame_subframe)),
        blender_version=bpy.app.version_string,blender_build_hash=bpy.app.build_hash.decode(),read_only=True,
        geometry_setters=0,saves_file=False,sets_frame=False,generic_exec=False,max_requests=16,byte_limit=LIMIT))
    for _ in range(16):
        blob=sys.stdin.buffer.readline(4097)
        if not blob:break
        key=None
        try:
            require(len(blob)<=4096,'command_budget');request=decode(blob)
            require(type(request) is dict and set(request)=={'id','command','deadline_ns'} and type(request['id']) is int,'command_fields');key=request['id']
            require(type(request['deadline_ns']) is int and request['deadline_ns']==deadline,'original_window');check(deadline)
            if request['command']=='shutdown':emit(dict(kind='closed',id=key));break
            require(request['command']=='inspect','readonly_command');emit(dict(kind='snapshot',id=key,packet=capture()))
        except Exception as exc:emit(dict(kind='error',id=key,reason=str(exc)[:400],geometry_setters=0))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('root','profile'):parser.add_argument('--'+key,type=Path,required=True)
    for key in ('profile-sha256','module-sha256','math-sha256','worker-sha256'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--deadline-ns',type=int,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    try:run(args)
    except Exception as exc:
        value=dict(kind='error',id=None,reason=str(exc)[:400],geometry_setters=0)
        sys.stdout.buffer.write(PREFIX+encoded(value)+b'\n');sys.stdout.buffer.flush();raise SystemExit(1)
