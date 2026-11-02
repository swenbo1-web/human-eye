"""Read-only fixed-file B3 qualification probe, never a production source reader.

The worker imports only the standard library and bpy. It has no edit, save,
frame, generic-code or budget-renewal command. Limits are experimental only.
"""
import argparse,hashlib,json,math,os,queue,subprocess,sys,threading,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PREFIX=b'B3_SOURCE_PROBE:'
LIMIT=512*1024
LIMITS=dict(vertices=256,triangles=256,bones=16,objects=16,parent_depth=8,groups=32,influences=8)


def require(ok,reason):
    if not ok:raise ValueError('b3_probe_'+reason)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(v):return hashlib.sha256(encoded(v)).hexdigest()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(deadline):require(type(deadline) is int and time.perf_counter_ns()<deadline,'original_deadline')
def decode(blob):
    require(len(blob)<=LIMIT,'response_budget')
    def unique(pairs):
        out={}
        for k,v in pairs:require(k not in out,'duplicate_key');out[k]=v
        return out
    return json.loads(blob,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('b3_probe_nonfinite')))
def source_digest(packet):return digest({k:v for k,v in packet.items() if k not in ('capture_id','source_sha256')})


def worker(args):
    import bpy
    deadline=args.deadline_ns;check(deadline)
    with args.profile.open('rb') as f:profile_bytes=f.read(65537)
    require(len(profile_bytes)<=65536 and hashlib.sha256(profile_bytes).hexdigest()==args.profile_sha256,'profile_pin');p=decode(profile_bytes)
    require(bpy.app.background and Path(bpy.data.filepath).resolve()==Path(p['scene_file'])
        and Path(bpy.app.binary_path).resolve()==Path(p['blender_executable']),'owned_fixed_file')
    require(sha(Path(p['scene_file']))==p['scene_sha256'] and sha(Path(__file__))==p['probe_sha256'],'input_or_probe_pin')
    scene=bpy.context.scene;rig=scene.objects.get(p['rig_name']);mesh=scene.objects.get(p['mesh_name']);epoch=uuid.uuid4().hex
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
        check(deadline);require(scene.frame_current==p['expected_frame']['number'] and scene.frame_subframe==p['expected_frame']['subframe'],'fixed_frame')
        audit_before=independent_audit();before=state();graph=bpy.context.evaluated_depsgraph_get();er=rig.evaluated_get(graph);em=mesh.evaluated_get(graph)
        require(er.is_evaluated and em.is_evaluated and er.original==rig and em.original==mesh and em.data.as_pointer()!=mesh.data.as_pointer(),'evaluated_links')
        ev=dict(rig_matrix_world=mat(er.matrix_world),mesh_matrix_world=mat(em.matrix_world),bones=[dict(name=b.name,parent=None if b.parent is None else b.parent.name,
            pose_matrix=mat(b.matrix),pose_head=vec(b.head),pose_tail=vec(b.tail)) for b in sorted(er.pose.bones,key=lambda b:b.name)],
            vertices=[vec(v.co) for v in em.data.vertices],triangles=[list(poly.vertices) for poly in em.data.polygons],original_links_verified=True)
        after=state();audit_after=independent_audit();require(before==after,'RNA_changed');require(audit_before==audit_after,'independent_RNA_changed')
        require(sha(Path(p['scene_file']))==p['scene_sha256'],'scene_changed');check(deadline)
        packet=dict(schema='b3-source-probe-v1',identity=dict(document_epoch=epoch,scene_sha256=p['scene_sha256'],profile_sha256=args.profile_sha256,
            probe_sha256=p['probe_sha256'],binary_sha256=p['blender_sha256']),inputs=before,evaluated=ev,
            audit=dict(before_sha256=digest(before),after_sha256=digest(after),independent_before_sha256=digest(audit_before),independent_after_sha256=digest(audit_after)),capture_id=uuid.uuid4().hex)
        packet['source_sha256']=source_digest(packet);require(len(encoded(packet))<=LIMIT-1024,'snapshot_byte_budget');return packet
    def emit(v):
        blob=encoded(v);require(len(blob)<=LIMIT,'wire_budget');sys.stdout.buffer.write(PREFIX+blob+b'\n');sys.stdout.buffer.flush()
    emit(dict(kind='ready',pid=os.getpid(),profile_sha256=args.profile_sha256,probe_sha256=p['probe_sha256'],deadline_ns=deadline,
        blender_version=bpy.app.version_string,blender_build_hash=bpy.app.build_hash.decode(),read_only=True,geometry_setters=0,saves_file=False,sets_frame=False))
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


def controller(args):
    require(args.output.is_absolute() and args.output.resolve()==args.output,'output_path');args.output.mkdir(exist_ok=False)
    started=time.perf_counter_ns();deadline=started+30_000_000_000;process=None;report_published=False;stderr=None
    def save(name,v):
        with (args.output/name).open('xb') as f:f.write(encoded(v));f.flush();os.fsync(f.fileno())
    try:
        require(args.scene.is_absolute() and args.scene.resolve()==args.scene and args.scene.suffix=='.blend' and args.scene.stat().st_size<=64*1024*1024,'scene_path')
        require(args.blender.is_absolute() and args.blender.resolve()==args.blender,'binary_path')
        p=dict(scene_file=str(args.scene),scene_sha256=sha(args.scene),blender_executable=str(args.blender),blender_sha256=sha(args.blender),
            mesh_name=args.mesh_name,rig_name=args.rig_name,expected_frame=dict(number=args.frame_number,subframe=args.subframe),probe_sha256=sha(Path(__file__)),limits=LIMITS)
        require(type(args.frame_number) is int and type(args.subframe) in (int,float) and math.isfinite(args.subframe) and 0<=args.subframe<1,'profile_frame')
        profile=args.output/'PROFILE.json';save('PROFILE.json',p);profile_sha=sha(profile);check(deadline)
        stderr=(args.output/'STDERR.txt').open('wb');q=queue.Queue(maxsize=18);diagnostics=[]
        command=[str(args.blender),'--factory-startup','--disable-autoexec','--background',str(args.scene),'--python-exit-code','73','--python',str(Path(__file__).resolve()),
            '--','--worker','--profile',str(profile),'--profile-sha256',profile_sha,'--deadline-ns',str(deadline)]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def read():
            try:
                while True:
                    blob=process.stdout.readline(LIMIT+len(PREFIX)+2)
                    if not blob:break
                    require(len(blob)<=LIMIT+len(PREFIX)+1,'wire_budget')
                    if blob.startswith(PREFIX):q.put_nowait(decode(blob[len(PREFIX):]))
                    elif len(diagnostics)<16:diagnostics.append(blob[:512].decode('utf8','replace'))
            except Exception as exc:q.put_nowait(dict(kind='reader_error',reason=str(exc)))
            finally:
                try:q.put_nowait(None)
                except queue.Full:pass
        threading.Thread(target=read,daemon=True).start()
        def next_reply():
            check(deadline);value=q.get(timeout=max(.000001,(deadline-time.perf_counter_ns())/1e9));require(value is not None,'worker_eof');return value
        ready=next_reply();require(ready.get('kind')=='ready' and ready['pid']==process.pid and ready['profile_sha256']==profile_sha
            and ready['probe_sha256']==p['probe_sha256'] and ready['deadline_ns']==deadline,'ready_binding');startup=time.perf_counter_ns()-started
        packets=[];reads=[]
        for key in (1,2):
            begin=time.perf_counter_ns();process.stdin.write(encoded(dict(id=key,command='inspect',deadline_ns=deadline))+b'\n');process.stdin.flush()
            value=next_reply();require(value.get('kind')=='snapshot' and value.get('id')==key,'snapshot_reply:'+str(value.get('reason')))
            packet=value['packet'];require(source_digest(packet)==packet['source_sha256'],'packet_digest')
            expected_identity=dict(scene_sha256=p['scene_sha256'],profile_sha256=profile_sha,probe_sha256=p['probe_sha256'],binary_sha256=p['blender_sha256'])
            require(type(packet.get('identity')) is dict and all(packet['identity'].get(k)==v for k,v in expected_identity.items()),'packet_identity_binding')
            inputs=packet.get('inputs');frame=None if type(inputs) is not dict else inputs.get('frame')
            require(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
                and type(frame['subframe']) in (int,float) and math.isfinite(frame['subframe']) and frame==p['expected_frame']
                and type(inputs.get('rig')) is dict and inputs['rig'].get('name')==p['rig_name']
                and type(inputs.get('mesh')) is dict and inputs['mesh'].get('name')==p['mesh_name'],'packet_roles_or_frame_binding')
            packets.append(packet)
            reads.append(time.perf_counter_ns()-begin);save('READ_%02d.json'%key,packet);check(deadline)
        require(packets[0]['source_sha256']==packets[1]['source_sha256'],'repeated_source_changed')
        qualification=None;qualification_ns=0;qualification_sha=None
        if args.qualify:
            qualification_path=ROOT/'verification/rigged_source_qualification.py';qualification_sha=sha(qualification_path)
            sys.path.insert(0,str(ROOT));from verification.rigged_source_qualification import qualify
            require(sha(qualification_path)==qualification_sha,'qualification_source_changed')
            begin=time.perf_counter_ns();qualification=qualify(packets[1],deadline_ns=deadline,expected_source_sha256=packets[0]['source_sha256']);qualification_ns=time.perf_counter_ns()-begin
            require(sha(qualification_path)==qualification_sha,'qualification_source_changed')
        check(deadline);close_start=time.perf_counter_ns();process.stdin.write(encoded(dict(id=3,command='shutdown',deadline_ns=deadline))+b'\n');process.stdin.flush()
        closed=next_reply();require(closed==dict(kind='closed',id=3),'shutdown_reply');process.stdin.close()
        process.wait(timeout=max(.000001,(deadline-time.perf_counter_ns())/1e9));require(process.returncode==0,'worker_exit');check(deadline)
        close_ns=time.perf_counter_ns()-close_start;require(sha(args.scene)==p['scene_sha256'] and sha(Path(__file__))==p['probe_sha256'],'input_changed')
        qualification_passed=None if qualification is None else qualification.get('status')=='qualified'
        report=dict(schema='b3-source-probe-run-v1',stage='capture_and_qualification' if args.qualify else 'capture_only',qualification=qualification,
            qualification_passed=qualification_passed,
            read_only=True,geometry_setters=0,saves_file=False,sets_frame=False,source_sha256=packets[1]['source_sha256'],snapshot_bytes=len(encoded(packets[1])),
            original_deadline_ns=deadline,process_id=process.pid,exit_code=process.returncode,reaped=process.poll() is not None,
            scene_sha256=p['scene_sha256'],blender=ready,profile_sha256=profile_sha,probe_sha256=p['probe_sha256'],qualification_sha256=qualification_sha,diagnostics=diagnostics,
            timings_ns=dict(startup=startup,reads=reads,qualification=qualification_ns,close=close_ns,complete_through_close=time.perf_counter_ns()-started),
            product_support_certified=False,shared_GUI=False)
        save('REPORT_PENDING.json',report);check(deadline);os.replace(args.output/'REPORT_PENDING.json',args.output/'REPORT.json');report_published=True;check(deadline)
        passed=qualification_passed is not False
        result=encoded(dict(passed=passed,stage=report['stage'],snapshot_bytes=report['snapshot_bytes'],complete_wall_ns=time.perf_counter_ns()-started,
            qualification_passed=qualification_passed,qualification_status=None if qualification is None else qualification.get('status'),evidence=str(args.output/'REPORT.json')))
        check(deadline);print(result.decode());return 0 if passed else 1
    except Exception as exc:
        if report_published:os.replace(args.output/'REPORT.json',args.output/'REVOKED_REPORT.json')
        failure=dict(passed=False,reason=str(exc),geometry_setters=0,saves_file=False,sets_frame=False,original_deadline_ns=deadline)
        save('FAILURE.json',failure);print(encoded(failure).decode());return 1
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        if stderr is not None:stderr.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--profile',type=Path);p.add_argument('--profile-sha256');p.add_argument('--deadline-ns',type=int)
    p.add_argument('--scene',type=Path);p.add_argument('--blender',type=Path,default=Path('D:/Tools/blender5.2/blender.exe'))
    p.add_argument('--mesh-name',default='Cylinder');p.add_argument('--rig-name',default='Armature');p.add_argument('--output',type=Path);p.add_argument('--qualify',action='store_true')
    p.add_argument('--frame-number',type=int,default=1);p.add_argument('--subframe',type=float,default=0.)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if a.worker:worker(a)
    else:raise SystemExit(controller(a))
