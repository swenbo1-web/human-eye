"""M4-A2 finite feasibility probe. Deliberately NOT a product rig consumer.

All scene objects are captured conservatively. No generic rig dependency-closure
claim is made. The original A1 FK reader and its unsupported domains are intact.
"""
import importlib.util,math
from pathlib import Path
# Blender's embedded Python has no product UI/image dependencies. Load only
# the pinned pure-math source instead of importing package __init__ / Pillow.
_core=Path(__file__).resolve().parents[1]/'human_eye_plugin/rig_pose.py'
_spec=importlib.util.spec_from_file_location('_rig_evaluation_math',_core)
r=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(r)

SCHEMA='rig-evaluation-feasibility-v1'
MAX_OBJECTS=8
MAX_BONES=8
MAX_BYTES=512*1024


def mat(value):return [[float(x) for x in row] for row in value]
def vec(value):return [float(x) for x in value]


def identity(value):
    if value is None:return None
    return dict(name=value.name_full,type=value.bl_rna.identifier,instance=str(value.session_uid),
        library=None if value.library is None else value.library.filepath)


def scalar(value):
    if value is None or type(value) in (bool,int,str):return value
    if isinstance(value,float):
        r.require(math.isfinite(value),'nonfinite_RNA');return value
    return [scalar(x) for x in value]


def constraint(value):
    """All writable scalar/enum/array/ID-pointer settings, not just type/name."""
    settings={}
    for prop in value.bl_rna.properties:
        if prop.identifier=='rna_type' or prop.is_readonly:continue
        item=getattr(value,prop.identifier)
        if prop.type=='POINTER':settings[prop.identifier]=identity(item)
        else:
            r.require(prop.type!='COLLECTION','constraint_collection_not_in_probe')
            settings[prop.identifier]=scalar(item)
    return dict(type=value.type,settings=settings,is_valid=bool(value.is_valid))


def curves(action):
    if hasattr(action,'fcurves'):return list(action.fcurves)
    r.require(len(action.slots)==1,'multiple_action_slots_not_in_probe')
    result=[]
    for layer in action.layers:
        for strip in layer.strips:
            r.require(hasattr(strip,'channelbags'),'action_strip_not_in_probe')
            for bag in strip.channelbags:result.extend(bag.fcurves)
    return result


def animation(value):
    ad=value.animation_data
    if ad is None:return None
    r.require(len(ad.nla_tracks)==0,'NLA_not_in_probe');action=ad.action
    fcurves=[] if action is None else curves(action);drivers=list(ad.drivers)
    r.require(len(fcurves)+len(drivers)<=8,'curve_limit')
    def capture(fc):
        r.require(len(fc.keyframe_points)<=16 and len(fc.sampled_points)==0 and len(fc.modifiers)==0,'curve_shape_not_in_probe')
        item=dict(data_path=fc.data_path,index=fc.array_index,mute=fc.mute,extrapolation=fc.extrapolation,
            points=[dict(co=vec(p.co),left=vec(p.handle_left),right=vec(p.handle_right),left_type=p.handle_left_type,
                right_type=p.handle_right_type,interpolation=p.interpolation,easing=p.easing,amplitude=p.amplitude,
                back=p.back,period=p.period) for p in fc.keyframe_points])
        if fc in drivers:
            driver=fc.driver;r.require(len(driver.variables)<=4,'driver_variable_limit')
            item['driver']=dict(type=driver.type,expression=driver.expression,use_self=driver.use_self,
                variables=[dict(name=v.name,type=v.type,targets=[dict(id=identity(t.id),id_type=t.id_type,
                    data_path=t.data_path,bone_target=t.bone_target,transform_type=t.transform_type,
                    transform_space=t.transform_space,rotation_mode=t.rotation_mode) for t in v.targets]) for v in driver.variables])
        return item
    return dict(action=identity(action),slot_handle=getattr(ad,'action_slot_handle',None),
        curves=[capture(fc) for fc in fcurves],drivers=[capture(fc) for fc in drivers],
        action_blend_type=ad.action_blend_type,action_extrapolation=ad.action_extrapolation,action_influence=ad.action_influence)


def inputs(bpy):
    scene=bpy.context.scene;objects=sorted(scene.objects,key=lambda v:v.name)
    r.require(len(objects)<=MAX_OBJECTS and bpy.context.mode=='OBJECT','probe_scene_domain')
    rows=[];total_bones=0;total_constraints=0
    for obj in objects:
        r.require(obj.type in ('ARMATURE','EMPTY'),'probe_object_type')
        r.require(obj.library is None and (obj.data is None or obj.data.library is None),'probe_linked_source')
        row=dict(id=identity(obj),type=obj.type,data=identity(obj.data),parent=identity(obj.parent),
            matrix_world=mat(obj.matrix_world),matrix_basis=mat(obj.matrix_basis),matrix_parent_inverse=mat(obj.matrix_parent_inverse),
            location=vec(obj.location),scale=vec(obj.scale),rotation_mode=obj.rotation_mode,
            delta_location=vec(obj.delta_location),delta_scale=vec(obj.delta_scale),delta_euler=vec(obj.delta_rotation_euler),
            delta_quaternion=vec(obj.delta_rotation_quaternion),parent_type=obj.parent_type,parent_bone=obj.parent_bone,
            euler=vec(obj.rotation_euler),quaternion=vec(obj.rotation_quaternion),axis_angle=vec(obj.rotation_axis_angle),
            properties={k:scalar(v) for k,v in obj.items()},animation=animation(obj),
            constraints=[constraint(c) for c in obj.constraints],selected=obj.select_get())
        total_constraints+=len(obj.constraints)
        if obj.type=='ARMATURE':
            total_bones+=len(obj.data.bones);r.require(total_bones<=MAX_BONES,'probe_bone_limit')
            row['data_animation']=animation(obj.data);row['pose_position']=obj.data.pose_position
            row['ik_solver']=obj.pose.ik_solver
            row['ik_parameters']=None if obj.pose.ik_param is None else {p.identifier:scalar(getattr(obj.pose.ik_param,p.identifier)) for p in obj.pose.ik_param.bl_rna.properties
                if p.identifier!='rna_type' and not p.is_readonly and p.type in ('BOOLEAN','INT','FLOAT','STRING','ENUM')}
            row['bones']=[dict(name=b.name,parent=None if b.parent is None else b.parent.name,matrix=mat(b.matrix_local),
                head=vec(b.head_local),tail=vec(b.tail_local),length=float(b.length),inherit_rotation=b.use_inherit_rotation,
                inherit_scale=b.inherit_scale,local_location=b.use_local_location,connected=b.use_connect,bbone_segments=b.bbone_segments)
                for b in sorted(obj.data.bones,key=lambda v:v.name)]
            row['channels']=[dict(name=b.name,basis=mat(b.matrix_basis),location=vec(b.location),scale=vec(b.scale),
                rotation_mode=b.rotation_mode,euler=vec(b.rotation_euler),quaternion=vec(b.rotation_quaternion),
                axis_angle=vec(b.rotation_axis_angle),constraints=[constraint(c) for c in b.constraints],
                ik_settings={p.identifier:scalar(getattr(b,p.identifier)) for p in b.bl_rna.properties
                    if p.identifier.startswith(('ik_','use_ik_','lock_ik_')) and p.type in ('BOOLEAN','INT','FLOAT','STRING','ENUM')})
                for b in sorted(obj.pose.bones,key=lambda v:v.name)]
            total_constraints+=sum(len(b.constraints) for b in obj.pose.bones)
        rows.append(row)
    r.require(total_constraints<=8,'probe_constraint_limit')
    return dict(scene=identity(scene),frame=dict(number=scene.frame_current,subframe=scene.frame_subframe),
        unit_scale_m=float(scene.unit_settings.scale_length),mode=bpy.context.mode,view_layer=bpy.context.view_layer.name,
        active=None if bpy.context.view_layer.objects.active is None else bpy.context.view_layer.objects.active.name_full,objects=rows)


def capture(bpy,epoch,deadline_ns):
    r.check_time(deadline_ns);before=inputs(bpy);graph=bpy.context.evaluated_depsgraph_get();rows=[]
    for obj in sorted(bpy.context.scene.objects,key=lambda v:v.name):
        r.check_time(deadline_ns);evaluated=obj.evaluated_get(graph)
        row=dict(id=identity(obj),matrix_world=mat(evaluated.matrix_world))
        if obj.type=='ARMATURE':
            r.require({b.name for b in obj.data.bones}=={b.name for b in evaluated.pose.bones},'evaluated_bone_correspondence')
            row['bones']=[dict(name=b.name,parent=None if b.parent is None else b.parent.name,matrix=mat(b.matrix),
                head=vec(b.head),tail=vec(b.tail)) for b in sorted(evaluated.pose.bones,key=lambda v:v.name)]
        rows.append(row)
    after=inputs(bpy);r.require(before==after,'probe_inputs_changed')
    packet=dict(schema=SCHEMA,document_epoch=epoch,inputs=before,evaluated=rows,
        audit=dict(before_sha256=r.digest(before),after_sha256=r.digest(after)),
        geometry_setters=0,original_file_saved=False,product_support=False)
    packet['source_sha256']=r.digest(packet);r.require(len(r.encoded(packet))<=MAX_BYTES,'probe_packet_budget')
    r.check_time(deadline_ns);return packet


def validate(packet,expected=None):
    r.require(type(packet) is dict and set(packet)=={'schema','document_epoch','inputs','evaluated','audit','geometry_setters',
        'original_file_saved','product_support','source_sha256'} and packet['schema']==SCHEMA,'probe_schema')
    r.require(len(r.encoded(packet))<=MAX_BYTES and r.hex_text(packet['document_epoch'],32),'probe_size_epoch')
    r.require(type(packet['geometry_setters']) is int and packet['geometry_setters']==0 and packet['original_file_saved'] is False
        and packet['product_support'] is False,'probe_no_authority')
    body={k:v for k,v in packet.items() if k!='source_sha256'}
    r.require(r.digest(body)==packet['source_sha256'],'probe_source_digest')
    audit=packet['audit'];r.require(type(audit) is dict and set(audit)=={'before_sha256','after_sha256'}
        and audit['before_sha256']==audit['after_sha256']==r.digest(packet['inputs']),'probe_input_audit')
    rows=packet['inputs']['objects'];out=packet['evaluated'];r.require(1<=len(rows)<=MAX_OBJECTS and len(rows)==len(out),'probe_object_count')
    frame=packet['inputs']['frame'];r.require(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and r.finite(frame['subframe']) and 0<=frame['subframe']<1,'probe_frame')
    keys=[(v['id']['name'],v['id']['instance']) for v in rows]
    r.require(len(set(keys))==len(keys) and keys==[(v['id']['name'],v['id']['instance']) for v in out],'probe_evaluated_identity')
    names=[v['id']['name'] for v in rows];r.require(names==sorted(set(names)),'probe_names')
    refs={r.digest(v['id']) for v in rows}
    total_bones=0;total_constraints=0
    for row,evaluated in zip(rows,out):
        for key in ('matrix_world','matrix_basis','matrix_parent_inverse'):r.matrix(row[key])
        r.matrix(evaluated['matrix_world'])
        if row['type']=='ARMATURE':
            rest=row['bones'];channels=row['channels'];poses=evaluated['bones'];total_bones+=len(rest)
            names=[v['name'] for v in rest];r.require(names==sorted(set(names)) and 1<=len(names)<=MAX_BONES
                and names==[v['name'] for v in channels]==[v['name'] for v in poses],'probe_bone_correspondence')
            lookup={v['name']:v for v in rest}
            for b,ch,pose in zip(rest,channels,poses):
                r.require(b['parent']==pose['parent'] and (b['parent'] is None or b['parent'] in lookup),'probe_evaluated_parent')
                visited=set();current=b['name']
                while current is not None:
                    r.require(current not in visited,'probe_parent_cycle');visited.add(current);current=lookup[current]['parent']
                r.require(r.finite(b['length']) and b['length']>0,'probe_bone_length');r.matrix(ch['basis'])
                for value in (b,pose):
                    r.matrix(value['matrix'])
                    for key,y in (('head',0),('tail',b['length'])):
                        r.require(type(value[key]) is list and len(value[key])==3 and all(r.finite(x) for x in value[key]),'probe_endpoint')
                        actual=r.point(value['matrix'],[0,y,0])
                        r.require(max(abs(a-v) for a,v in zip(actual,value[key]))<=2e-5*max(1,b['length']), 'probe_endpoint_matrix')
        if row['parent'] is not None:r.require(r.digest(row['parent']) in refs,'probe_missing_parent')
        all_constraints=row['constraints']+[c for b in row.get('channels',[]) for c in b['constraints']]
        total_constraints+=len(all_constraints)
        for c in all_constraints:
            for key in ('target','pole_target','space_object'):
                ref=c['settings'].get(key)
                if ref is not None:r.require(r.digest(ref) in refs,'probe_missing_dependency')
        for ad in (row['animation'],row.get('data_animation')):
            if ad:
                for fc in ad['drivers']:
                    for var in fc['driver']['variables']:
                        for target in var['targets']:
                            if target['id'] is not None:r.require(r.digest(target['id']) in refs,'probe_missing_driver_dependency')
    r.require(total_bones<=MAX_BONES and total_constraints<=8,'probe_total_limits')
    if expected is not None:
        r.require(packet['document_epoch']==expected['document_epoch'] and packet['source_sha256']==expected['source_sha256'],
            'probe_stale_evidence')
    return packet['inputs']


def copy_candidate(packet):
    """Conservative prototype admission only. No evaluation by FK basis equality."""
    p=validate(packet);reasons=[];objects=p['objects'];rigs=[v for v in objects if v['type']=='ARMATURE']
    if len(rigs)!=1:return dict(eligible=False,reasons=['one_armature_required'],product_support=False)
    rig=rigs[0];rest={b['name']:b for b in rig['bones']};channels={b['name']:b for b in rig['channels']}
    poses={b['name']:b for row in packet['evaluated'] if row['id']==rig['id'] for b in row['bones']}
    r.require(set(rest)==set(channels)==set(poses),'probe_bone_correspondence')
    constraints=[(None,c) for row in objects for c in row['constraints']]+[(b['name'],c) for b in rig['channels'] for c in b['constraints']]
    for row in objects:
        if row['parent'] is not None:reasons.append('object_parent')
        if row['animation'] is not None or row.get('data_animation') is not None:reasons.append('animation_or_driver')
        if not r.rigid(row['matrix_world']):reasons.append('nonrigid_object')
    if rig['pose_position']!='POSE':reasons.append('rest_display')
    for name,b in rest.items():
        if not b['inherit_rotation'] or b['inherit_scale']!='FULL' or not b['local_location'] or b['bbone_segments']!=1:reasons.append('bone_inheritance_or_segments')
        if not all(r.rigid(m) for m in (b['matrix'],channels[name]['basis'],poses[name]['matrix'])):reasons.append('nonrigid_bone')
        r.require(b['parent']==poses[name]['parent'],'probe_evaluated_parent')
    bone=None;target=None
    if len(constraints)!=1 or constraints[0][0] is None:reasons.append('one_pose_constraint_required')
    else:
        bone,c=constraints[0];s=c['settings'];target=next((v for v in objects if v['id']==s.get('target')),None)
        if c['type']!='COPY_ROTATION':reasons.append('constraint_type')
        if c['is_valid'] is not True or s.get('mute') is not False or not r.finite(s.get('influence')) or s['influence']!=1.:reasons.append('inactive_or_partial')
        if s.get('owner_space')!='WORLD' or s.get('target_space')!='WORLD' or s.get('mix_mode')!='REPLACE':reasons.append('space_or_mix')
        if any(s.get('use_'+axis) is not True or s.get('invert_'+axis) is not False for axis in ('x','y','z')):reasons.append('axis_options')
        if s.get('subtarget') or target is None or target['type']!='EMPTY':reasons.append('external_empty_target_required')
    result=dict(eligible=not reasons,reasons=sorted(set(reasons)),product_support=False,domain='prototype_static_world_replace_copy_rotation',
        metric='evaluated_parent_rest_relative_visual_rotation; input channels separate',source_sha256=packet['source_sha256'])
    if not reasons:
        b=rest[bone];pose=poses[bone]
        if b['parent'] is None:delta=r.multiply(r.inverse(b['matrix']),pose['matrix'])
        else:
            parent=b['parent'];relative=r.multiply(r.inverse(rest[parent]['matrix']),b['matrix'])
            delta=r.multiply(r.inverse(relative),r.multiply(r.inverse(poses[parent]['matrix']),pose['matrix']))
        r.require(r.rigid(delta),'probe_nonrigid_effective_output')
        result.update(bone=bone,input_channel=r.angles(channels[bone]['basis']),evaluated_local=r.angles(delta),evaluated_delta=delta,
            target=target['id'],damage_classification='not_inferred',joint_rule_assessment='not_assessed')
    return result
