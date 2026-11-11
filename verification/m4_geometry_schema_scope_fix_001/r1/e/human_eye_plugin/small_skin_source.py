"""Finite fixed-file current-frame LBS consumer with external launch binding.

This module validates a new source contract. It never treats a packet's hash,
research qualification or JSON flag as an external expectation or edit grant.
"""
import copy,math,re
from dataclasses import dataclass
from . import rig_pose as r

SCHEMA='small-skin-source-snapshot-v1'
PROTOCOL='owned-small-skin-source-readonly-v1'
LIMITS=dict(vertices=256,triangles=256,bones=16,objects=16,parent_depth=8,groups=32,influences=8,actions=16,curves=64,curve_keys=256,edges=768,bytes=512*1024)
POSITION_ATOL=2e-5
MATRIX_ATOL=2e-5
GRAM_ATOL=2e-5
PIN_FIELDS=('scene_sha256','profile_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256','runtime_source_sha256')
REF_FIELDS={'name','id_type','session_uid','linked'}
ROTATION_FIELDS={'location','scale','rotation_mode','rotation_euler','rotation_quaternion','rotation_axis_angle'}
OBJECT_FIELDS=ROTATION_FIELDS|{'name','type','identity','data_identity','parent','parent_identity','parent_type','parent_bone',
    'matrix_basis','matrix_local','matrix_parent_inverse','matrix_world','delta_location','delta_scale','delta_rotation_euler','delta_rotation_quaternion',
    'constraints','object_linked','data_linked','object_override','data_override','animation'}
BONE_FIELDS=ROTATION_FIELDS|{'name','parent','rest_matrix','rest_head','rest_tail','length','inherit_rotation','inherit_scale','local_location',
    'connected','bbone_segments','basis_matrix','pose_matrix','pose_head','pose_tail','use_deform','use_envelope_multiply','constraints','custom_shape'}
ACTION_FIELDS={'name','identity','linked','override','is_action_legacy','is_action_layered','use_frame_range','use_cyclic','frame_start','frame_end','frame_range','curve_frame_range','slots','layers'}
ANIMATION_FIELDS={'action','action_id','action_slot','action_slot_handle','last_slot_identifier','action_tweak_storage','action_tweak_storage_id',
    'action_slot_handle_tweak_storage','use_pin','use_nla','use_tweak_mode','action_blend_type','action_extrapolation','action_influence','drivers','nla_tracks'}
CURVE_FIELDS={'data_path','array_index','extrapolation','mute','is_valid','auto_smoothing','keys','sampled_points','modifiers','driver'}
KEY_FIELDS={'co','handle_left','handle_right','interpolation','easing','type','amplitude','back','period','handle_left_type','handle_right_type'}
MOD_SETTINGS={'execution_time','invert_vertex_group','is_active','is_override_data','name','persistent_uid','show_expanded','show_in_editmode',
    'show_on_cage','show_render','show_viewport','type','use_apply_on_spline','use_bone_envelopes','use_deform_preserve_volume','use_multi_modifier','use_pin_to_last','use_vertex_groups','vertex_group'}
STRIP_SETTINGS={'action_frame_end','action_frame_start','action_slot_handle','active','blend_in','blend_out','blend_type','extrapolation',
    'frame_end','frame_end_raw','frame_end_ui','frame_start','frame_start_raw','frame_start_ui','influence','last_slot_identifier','mute','name','repeat','scale',
    'select','strip_time','type','use_animated_influence','use_animated_time','use_animated_time_cyclic','use_auto_blend','use_reverse','use_sync_length'}


class SmallSourceError(ValueError):
    def __init__(self,code,status='unsupported'):
        self.code='small_skin_'+code;self.status=status;super().__init__(self.code)


def need(value,code,status='unsupported'):
    if not value:raise SmallSourceError(code,status)
def check(deadline_ns):need(type(deadline_ns) is int and r.time.perf_counter_ns()<deadline_ns,'original_deadline','unavailable')
def fields(value,keys,code):need(type(value) is dict and set(value)==keys,code)
def vector(value,n,code):need(type(value) is list and len(value)==n and all(r.finite(v) for v in value),code);return value
def scalar_values(value,code):
    need(all(type(v) is bool or r.finite(v) or r.text(v) or v=='' for v in value.values()),code)
def reference(value,kind=None):
    fields(value,REF_FIELDS,'identity_fields')
    need(r.text(value['name']) and r.text(value['id_type']) and type(value['session_uid']) is int and value['session_uid']>0
        and type(value['linked']) is bool,'identity_value')
    need(kind is None or value['id_type']==kind,'identity_type')
    need(value['linked'] is False,'linked_source');return value
def role_identity(value,object_name,data_kind):
    if type(value) is bytes:value=r.decode(value)
    fields(value,{'identity','data_identity'},'external_role_identity')
    reference(value['identity'],'OBJECT');reference(value['data_identity'],data_kind)
    need(value['identity']['name']==object_name,'external_role_name');return r.encoded(value)


@dataclass(frozen=True)
class ExternalBinding:
    scene_sha256:str
    profile_sha256:str
    worker_sha256:str
    module_sha256:str
    math_sha256:str
    binary_sha256:str
    runtime_source_sha256:str
    process_id:int
    mesh_name:str
    rig_name:str
    expected_frame:tuple
    unit_scale_m:float
    document_epoch:str
    mesh_identity:object
    rig_identity:object

    def __post_init__(self):
        need(all(r.hex_text(getattr(self,key),64) for key in PIN_FIELDS),'external_digest')
        need(type(self.process_id) is int and self.process_id>0,'external_process')
        need(r.text(self.mesh_name) and r.text(self.rig_name) and self.mesh_name!=self.rig_name,'external_roles')
        need(type(self.expected_frame) is tuple and len(self.expected_frame)==2 and type(self.expected_frame[0]) is int
            and r.finite(self.expected_frame[1]) and 0<=self.expected_frame[1]<1,'external_frame')
        need(r.finite(self.unit_scale_m) and 0<self.unit_scale_m<=1e6 and r.hex_text(self.document_epoch,32),'external_unit_epoch')
        object.__setattr__(self,'mesh_identity',role_identity(self.mesh_identity,self.mesh_name,'MESH'))
        object.__setattr__(self,'rig_identity',role_identity(self.rig_identity,self.rig_name,'ARMATURE'))


def source_digest(packet):return r.digest({k:v for k,v in packet.items() if k not in ('capture_id','source_sha256')})
def residual(a,b):
    if type(a[0]) is list:return max(abs(x-y) for aa,bb in zip(a,b) for x,y in zip(aa,bb))
    return max(abs(x-y) for x,y in zip(a,b))
def matrix(value):
    need(type(value) is list and len(value)==4 and all(type(row) is list and len(row)==4 and all(r.finite(v) and abs(v)<=1e12 for v in row) for row in value),'matrix_shape')
    need(value[3]==[0,0,0,1],'matrix_affine')
    determinant=r.determinant(value);need(math.isfinite(determinant) and abs(determinant)>1e-12,'matrix_condition','unknown')
    need(determinant>0,'matrix_reflection')
    inverse=r.inverse(value)
    condition=max(sum(abs(value[i][j]) for j in range(3)) for i in range(3))*max(sum(abs(inverse[i][j]) for j in range(3)) for i in range(3))
    need(math.isfinite(condition) and condition<=1e4,'matrix_condition','unknown')
    gram=max(abs(math.fsum(value[k][i]*value[k][j] for k in range(3))-(1 if i==j else 0)) for i in range(3) for j in range(3))
    need(gram<=GRAM_ATOL,'nonrigid_matrix');return value


def channel_matrix(value):
    for key,n in (('location',3),('scale',3),('rotation_euler',3),('rotation_quaternion',4),('rotation_axis_angle',4)):vector(value[key],n,'channel_vector')
    mode=value['rotation_mode'];rotation=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    if mode=='QUATERNION':
        length=math.hypot(*value['rotation_quaternion']);need(length>1e-12,'quaternion_zero','unknown')
        w,x,y,z=[v/length for v in value['rotation_quaternion']]
        rows=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
            [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
            [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
        for i in range(3):rotation[i][:3]=rows[i]
    elif mode=='AXIS_ANGLE':
        angle,*axis=value['rotation_axis_angle'];length=math.hypot(*axis);need(length>1e-12 or angle==0,'axis_angle_zero','unknown')
        x,y,z=[v/length for v in axis] if length else [0.,0.,1.];c=math.cos(angle);s=math.sin(angle);cross=[[0,-z,y],[z,0,-x],[-y,x,0]]
        for i in range(3):
            for j in range(3):rotation[i][j]=(c if i==j else 0)+(1-c)*[x,y,z][i]*[x,y,z][j]+s*cross[i][j]
    else:
        need(mode in ('XYZ','XZY','YXZ','YZX','ZXY','ZYX'),'rotation_mode')
        for axis in mode:
            angle=value['rotation_euler']['XYZ'.index(axis)];c=math.cos(angle);s=math.sin(angle);m=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
            i,j={'X':(1,2),'Y':(2,0),'Z':(0,1)}[axis];m[i][i]=m[j][j]=c;m[i][j]=-s;m[j][i]=s;rotation=r.multiply(m,rotation)
    for i in range(3):
        for j in range(3):rotation[i][j]*=value['scale'][j]
        rotation[i][3]=value['location'][i]
    return rotation


def curve_value(curve,frame,deadline_ns):
    check(deadline_ns);fields(curve,CURVE_FIELDS,'curve_fields')
    need(curve['driver'] is None,'driver');need(curve['modifiers']==[],'curve_modifier')
    need(curve['mute'] is False and curve['is_valid'] is True and curve['sampled_points']==[],'curve_state')
    need(r.text(curve['auto_smoothing']) and curve['extrapolation'] in ('CONSTANT','LINEAR'),'curve_state')
    keys=curve['keys'];need(type(keys) is list and 1<=len(keys)<=LIMITS['curve_keys'],'curve_key_limit')
    points=[]
    for key in keys:
        check(deadline_ns);fields(key,KEY_FIELDS,'curve_key_fields')
        for name in ('co','handle_left','handle_right'):vector(key[name],2,'curve_key_vector')
        need(all(r.finite(key[k]) for k in ('amplitude','back','period')) and all(r.text(key[k]) for k in ('interpolation','easing','type','handle_left_type','handle_right_type')),'curve_key_value')
        points.append(key['co'])
    need(all(a[0]<b[0] for a,b in zip(points,points[1:])),'curve_key_order')
    for x,y in points:
        if frame==x:return y
    if frame<points[0][0] or frame>points[-1][0]:
        need(curve['extrapolation']=='CONSTANT','curve_extrapolation','unknown');return points[0][1] if frame<points[0][0] else points[-1][1]
    for index,(a,b) in enumerate(zip(points,points[1:])):
        if a[0]<frame<b[0]:
            interpolation=keys[index]['interpolation'];need(interpolation in ('CONSTANT','LINEAR'),'curve_interpolation','unknown')
            return a[1] if interpolation=='CONSTANT' else a[1]+(b[1]-a[1])*(frame-a[0])/(b[0]-a[0])
    raise SmallSourceError('curve_interval','unknown')


def animation_check(inputs,objects,bones,deadline_ns):
    actions=inputs['actions'];need(type(actions) is list and len(actions)<=LIMITS['actions'],'action_limit');lookup={}
    for action in actions:
        check(deadline_ns);fields(action,ACTION_FIELDS,'action_fields');reference(action['identity'],'ACTION')
        need(r.text(action['name']) and action['name']==action['identity']['name'] and action['name'] not in lookup,'action_identity')
        need(action['linked'] is False and action['override'] is False,'linked_source')
        need(action['is_action_layered'] is True and action['is_action_legacy'] is False and action['use_frame_range'] is False and action['use_cyclic'] is False,'action_shape')
        for key in ('frame_range','curve_frame_range'):vector(action[key],2,'action_range')
        need(r.finite(action['frame_start']) and r.finite(action['frame_end']),'action_range')
        lookup[action['name']]=action
    current=inputs['frame']['number']+inputs['frame']['subframe'];used=set();checked=0
    pattern=re.compile(r'^pose\.bones\[("(?:[^"\\]|\\.)*")\]\.(location|scale|rotation_euler|rotation_quaternion|rotation_axis_angle)$')
    for obj in objects.values():
        fields(obj['animation'],{'object','data'},'animation_fields')
        for owner,data in obj['animation'].items():
            if data is None:continue
            check(deadline_ns);fields(data,ANIMATION_FIELDS,'animation_fields')
            need(data['drivers']==[],'driver');need(data['use_tweak_mode'] is False and data['action_tweak_storage'] is None and data['action_tweak_storage_id'] is None,'tweak_mode')
            need(type(data['use_nla']) is bool and type(data['use_pin']) is bool and type(data['action_slot_handle_tweak_storage']) is int,'animation_state')
            if data['action_id'] is not None:reference(data['action_id'],'ACTION')
            need(type(data['nla_tracks']) is list and len(data['nla_tracks'])<=16,'nla_track_limit')
            for track in data['nla_tracks']:
                fields(track,{'name','mute','is_solo','strips'},'nla_fields');need(r.text(track['name']) and track['mute'] is True and track['is_solo'] is False,'active_nla')
                need(type(track['strips']) is list and len(track['strips'])<=16,'nla_strip_limit')
                for strip in track['strips']:
                    fields(strip,{'action','action_id','action_slot','fcurves','modifiers','settings','strips'},'nla_strip_fields')
                    need(strip['fcurves']==[] and strip['modifiers']==[] and strip['strips']==[],'nla_strip')
                    fields(strip['settings'],STRIP_SETTINGS,'nla_settings_fields');settings=strip['settings']
                    scalar_values(settings,'nla_settings_value')
                    boolean_keys={'active','mute','select','use_animated_influence','use_animated_time','use_animated_time_cyclic','use_auto_blend','use_reverse','use_sync_length'}
                    text_keys={'blend_type','extrapolation','last_slot_identifier','name','type'}
                    need(all(type(settings[k]) is bool for k in boolean_keys) and all(r.text(settings[k]) for k in text_keys)
                        and all(r.finite(settings[k]) for k in STRIP_SETTINGS-boolean_keys-text_keys),'nla_settings_value')
                    need(settings['type']=='CLIP' and settings['use_animated_time'] is False and settings['use_animated_influence'] is False and settings['use_animated_time_cyclic'] is False,'nla_strip')
                    need(strip['action'] in lookup and strip['action_id']==lookup[strip['action']]['identity'],'nla_action_binding')
                    reference(strip['action_id'],'ACTION')
                    fields(strip['action_slot'],{'identifier','handle','target_id_type'},'nla_slot')
                    need(type(strip['action_slot']['handle']) is int and r.text(strip['action_slot']['identifier']) and strip['action_slot']['target_id_type']=='OBJECT','nla_slot')
                    need(type(settings['action_slot_handle']) is int and settings['action_slot_handle']==strip['action_slot']['handle'],'nla_slot')
                    action=lookup[strip['action']]
                    need(type(action['slots']) is list and len(action['slots'])==1 and strip['action_slot']=={k:action['slots'][0][k] for k in ('identifier','handle','target_id_type')},'nla_slot')
            if data['action'] is None:
                need(data['action_id'] is None and data['action_slot'] is None,'action_identity');continue
            need(owner=='object' and obj['name']==inputs['rig']['name'],'animation_owner')
            need(data['action'] in lookup and data['action_id']==lookup[data['action']]['identity'],'action_identity')
            need(data['action_blend_type']=='REPLACE' and r.finite(data['action_influence']) and data['action_influence']==1 and data['action_extrapolation']=='HOLD','action_blend')
            action=lookup[data['action']];used.add(action['name']);slots=action['slots']
            need(type(slots) is list and len(slots)==1,'action_slot');slot=slots[0]
            fields(slot,{'identifier','handle','target_id_type','name','users'},'action_slot_fields')
            fields(data['action_slot'],{'identifier','handle','target_id_type'},'action_slot_fields')
            need(type(data['action_slot']['handle']) is int and r.text(slot['identifier']) and r.text(slot['name'])
                and type(slot['users']) is list and len(slot['users'])<=16,'action_slot')
            for user in slot['users']:reference(user,'OBJECT')
            need(type(slot['handle']) is int and type(data['action_slot_handle']) is int and slot['handle']==data['action_slot_handle']==data['action_slot']['handle']
                and slot['identifier']==data['action_slot']['identifier'] and slot['target_id_type']==data['action_slot']['target_id_type']=='OBJECT' and slot['users']==[obj['identity']],'action_slot')
            layers=action['layers'];need(type(layers) is list and len(layers)==1,'action_shape');layer=layers[0];fields(layer,{'name','strips'},'action_shape')
            need(r.text(layer['name']) and type(layer['strips']) is list and len(layer['strips'])==1,'action_shape');strip=layer['strips'][0];fields(strip,{'type','channelbags'},'action_shape')
            need(strip['type']=='KEYFRAME' and type(strip['channelbags']) is list and len(strip['channelbags'])==1,'action_shape');bag=strip['channelbags'][0];fields(bag,{'slot_handle','fcurves'},'action_shape')
            need(type(bag['slot_handle']) is int and bag['slot_handle']==slot['handle'],'action_slot')
            need(type(bag['fcurves']) is list and len(bag['fcurves'])<=LIMITS['curves'],'curve_limit');seen=set()
            for curve in bag['fcurves']:
                check(deadline_ns);fields(curve,CURVE_FIELDS,'curve_fields');match=pattern.fullmatch(curve['data_path']) if type(curve['data_path']) is str else None
                need(match is not None,'animation_path');name=r.decode(match.group(1).encode());key=match.group(2);index=curve['array_index']
                need(name in bones and type(index) is int and 0<=index<len(bones[name][key]) and (name,key,index) not in seen,'animation_path');seen.add((name,key,index))
                if key.startswith('rotation_'):need(key==('rotation_quaternion' if bones[name]['rotation_mode']=='QUATERNION' else 'rotation_axis_angle' if bones[name]['rotation_mode']=='AXIS_ANGLE' else 'rotation_euler'),'animation_path')
                need(abs(curve_value(curve,current,deadline_ns)-bones[name][key][index])<=MATRIX_ATOL,'animation_channel_disagreement');checked+=1
    need(set(lookup)==used,'action_closure');return checked


def _validate(packet,*,deadline_ns,expected_bindings,expected_source=None):
    """Return geometry only after external pins AND full independent replay."""
    check(deadline_ns);need(type(expected_bindings) is ExternalBinding,'external_binding_required','unavailable');binding=expected_bindings
    fields(packet,{'schema','identity','inputs','evaluated','audit','capture_id','source_sha256'},'packet_fields')
    need(packet['schema']==SCHEMA and len(r.encoded(packet))<=LIMITS['bytes'],'packet_schema_or_bytes')
    fields(packet['identity'],set(PIN_FIELDS)|{'document_epoch','process_id'},'packet_identity_fields');ident=packet['identity']
    need(all(ident[k]==getattr(binding,k) for k in PIN_FIELDS) and type(ident['process_id']) is int and ident['process_id']==binding.process_id
        and ident['document_epoch']==binding.document_epoch,'external_binding_mismatch','unavailable')
    need(r.hex_text(packet['capture_id'],32) and r.hex_text(packet['source_sha256'],64) and packet['source_sha256']==source_digest(packet),'source_digest','unavailable')
    if expected_source is not None:
        prior=expected_source['source_sha256'] if type(expected_source) is dict else expected_source
        need(r.hex_text(prior,64) and packet['source_sha256']==prior,'stale_source','unavailable')
    inputs=packet['inputs'];evaluated=packet['evaluated'];fields(inputs,{'actions','closure','context','frame','mesh','rig','scene','unit_scale_m'},'input_fields')
    audit=packet['audit'];fields(audit,{'before_sha256','after_sha256','independent_before_sha256','independent_after_sha256'},'audit_fields')
    need(all(r.hex_text(v,64) for v in audit.values()) and audit['before_sha256']==audit['after_sha256']==r.digest(inputs)
        and audit['independent_before_sha256']==audit['independent_after_sha256'],'RNA_changed','unavailable')
    frame=inputs['frame'];fields(frame,{'number','subframe'},'frame_fields')
    need(type(frame['number']) is int and r.finite(frame['subframe']) and (frame['number'],frame['subframe'])==binding.expected_frame,'fixed_frame','unavailable')
    need(r.finite(inputs['unit_scale_m']) and inputs['unit_scale_m']==binding.unit_scale_m,'fixed_unit','unavailable')
    fields(inputs['context'],{'mode','active_object','selected_objects'},'context_fields');need(inputs['context']['mode']=='OBJECT','mode')
    need(inputs['context']['active_object'] is None or r.text(inputs['context']['active_object']),'context_fields')
    selected=inputs['context']['selected_objects'];need(type(selected) is list and len(selected)<=16 and all(r.text(v) for v in selected) and selected==sorted(set(selected)),'context_fields')
    scene=inputs['scene'];fields(scene,{'name','fps','fps_base','objects'},'scene_fields')
    need(r.text(scene['name']) and type(scene['fps']) is int and scene['fps']>0 and r.finite(scene['fps_base']) and scene['fps_base']>0,'scene_fps')
    need(type(scene['objects']) is list and 1<=len(scene['objects'])<=16,'scene_count');scene_objects={}
    for obj in scene['objects']:
        fields(obj,{'name','type','identity','data_identity'},'scene_object_fields');reference(obj['identity'],'OBJECT')
        need(obj['name']==obj['identity']['name'] and obj['name'] not in scene_objects and r.text(obj['type']),'scene_object_identity')
        if obj['data_identity'] is not None:reference(obj['data_identity'])
        scene_objects[obj['name']]=obj
    need(type(inputs['closure']) is list and 1<=len(inputs['closure'])<=16,'closure_count');objects={}
    for obj in inputs['closure']:
        check(deadline_ns);fields(obj,OBJECT_FIELDS,'object_fields');need(r.text(obj['name']) and obj['name'] not in objects,'object_names')
        reference(obj['identity'],'OBJECT');need(obj['identity']['name']==obj['name'] and obj['name'] in scene_objects,'object_identity')
        if obj['data_identity'] is not None:reference(obj['data_identity'])
        need({k:obj[k] for k in ('name','type','identity','data_identity')}==scene_objects[obj['name']],'scene_object_binding','unavailable')
        need(obj['type'] in ('EMPTY','MESH','ARMATURE') and obj['parent_type']=='OBJECT' and obj['parent_bone']=='','parent_type')
        need(all(obj[k] is False for k in ('object_linked','data_linked','object_override','data_override')),'linked_source')
        need(obj['constraints']==[],'constraint')
        need(obj['delta_location']==[0,0,0] and obj['delta_scale']==[1,1,1] and obj['delta_rotation_euler']==[0,0,0] and obj['delta_rotation_quaternion']==[1,0,0,0],'delta_transform')
        for key in ('matrix_basis','matrix_local','matrix_parent_inverse','matrix_world'):matrix(obj[key])
        need(max(abs(obj['matrix_world'][i][3]) for i in range(3))<=100,'world_translation_bound')
        need(residual(obj['matrix_basis'],channel_matrix(obj))<=MATRIX_ATOL,'object_channel_basis')
        objects[obj['name']]=obj
    need(all(name in scene_objects for name in selected) and (inputs['context']['active_object'] is None or inputs['context']['active_object'] in scene_objects),'context_binding')
    mesh=inputs['mesh'];rig=inputs['rig'];fields(rig,{'name','data_name','pose_position','bones'},'rig_fields')
    fields(mesh,{'name','data_name','vertices','triangles','edges','weights','groups','modifier','shape_keys'},'mesh_fields')
    need(mesh['name']==binding.mesh_name and rig['name']==binding.rig_name and mesh['name'] in objects and rig['name'] in objects,'fixed_roles','unavailable')
    mesh_obj=objects[mesh['name']];rig_obj=objects[rig['name']]
    for obj,kind,role,expected in ((mesh_obj,'MESH',mesh,binding.mesh_identity),(rig_obj,'ARMATURE',rig,binding.rig_identity)):
        need(obj['type']==kind and obj['data_identity'] is not None and obj['data_identity']['id_type']==kind and obj['data_identity']['name']==role['data_name'],'role_data_identity','unavailable')
        need(r.encoded({k:obj[k] for k in ('identity','data_identity')})==expected,'role_instance_changed','unavailable')
    required=set()
    for start in (mesh['name'],rig['name']):
        current=start;visited=set()
        while current is not None:
            need(current in objects,'parent_missing');need(current not in visited,'parent_cycle');visited.add(current);required.add(current)
            need(len(visited)<=LIMITS['parent_depth'],'parent_depth');obj=objects[current];parent=obj['parent']
            if obj['parent_identity'] is not None:reference(obj['parent_identity'],'OBJECT')
            need(obj['parent_identity']==(None if parent is None else objects[parent]['identity'] if parent in objects else None),'parent_identity_binding','unavailable')
            local=obj['matrix_basis'] if parent is None else r.multiply(obj['matrix_parent_inverse'],obj['matrix_basis'])
            world=local if parent is None else r.multiply(objects[parent]['matrix_world'],local) if parent in objects else local
            need(residual(local,obj['matrix_local'])<=MATRIX_ATOL and residual(world,obj['matrix_world'])<=MATRIX_ATOL,'parent_matrix_disagreement')
            current=parent
    need(required==set(objects),'closure_extras')
    need(rig['pose_position']=='POSE','rest_display');need(type(rig['bones']) is list and 1<=len(rig['bones'])<=16,'bone_limit');bones={}
    for bone in rig['bones']:
        check(deadline_ns);fields(bone,BONE_FIELDS,'bone_fields');need(r.text(bone['name']) and bone['name'] not in bones,'bone_names')
        for key,n in (('rest_head',3),('rest_tail',3),('pose_head',3),('pose_tail',3)):vector(bone[key],n,'bone_vector')
        for key in ('rest_matrix','pose_matrix','basis_matrix'):matrix(bone[key])
        need(r.finite(bone['length']) and 1e-8<bone['length']<=1e6,'bone_length')
        need(bone['inherit_rotation'] is True and bone['inherit_scale']=='FULL' and bone['local_location'] is True and type(bone['bbone_segments']) is int and bone['bbone_segments']==1,'bone_inheritance')
        need(type(bone['connected']) is bool and type(bone['use_deform']) is bool and bone['use_envelope_multiply'] is False,'bone_deform')
        need(bone['constraints']==[],'constraint')
        if bone['custom_shape'] is not None:reference(bone['custom_shape'],'OBJECT')
        need(residual(bone['basis_matrix'],channel_matrix(bone))<=MATRIX_ATOL,'bone_channel_basis');bones[bone['name']]=bone
    for bone in bones.values():
        current=bone['name'];visited=set()
        while current is not None:
            need(current in bones,'bone_parent_missing');need(current not in visited,'bone_parent_cycle');visited.add(current);current=bones[current]['parent']
        parent=bone['parent'];expected=r.multiply(bone['rest_matrix'],bone['basis_matrix'])
        if parent is not None:expected=r.multiply(r.multiply(bones[parent]['pose_matrix'],r.inverse(bones[parent]['rest_matrix'])),expected)
        need(residual(expected,bone['pose_matrix'])<=MATRIX_ATOL,'FK_pose_disagreement')
        for matrix_key,head,tail in (('rest_matrix','rest_head','rest_tail'),('pose_matrix','pose_head','pose_tail')):
            need(residual(r.point(bone[matrix_key],[0,0,0]),bone[head])<=MATRIX_ATOL and residual(r.point(bone[matrix_key],[0,bone['length'],0]),bone[tail])<=MATRIX_ATOL,'endpoint_matrix')
    need(mesh['shape_keys'] is None,'shape_keys');need(type(mesh['modifier']) is list and len(mesh['modifier'])==1,'modifier_count')
    mod=mesh['modifier'][0];fields(mod,{'name','type','settings','object','object_identity'},'modifier_fields');fields(mod['settings'],MOD_SETTINGS,'modifier_settings_fields');settings=mod['settings']
    scalar_values(settings,'modifier_settings_value')
    boolean_keys=MOD_SETTINGS-{'execution_time','name','persistent_uid','type','vertex_group'}
    need(all(type(settings[k]) is bool for k in boolean_keys) and r.finite(settings['execution_time']) and settings['execution_time']>=0
        and type(settings['persistent_uid']) is int and settings['persistent_uid']>=0 and r.text(settings['name']),'modifier_settings_value')
    reference(mod['object_identity'],'OBJECT')
    need(mod['type']==settings['type']=='ARMATURE' and mod['object']==rig['name'] and mod['object_identity']==rig_obj['identity'],'modifier_binding')
    need(settings['use_deform_preserve_volume'] is False,'DQ');need(settings['use_bone_envelopes'] is False,'envelopes')
    need(settings['use_multi_modifier'] is False and settings['invert_vertex_group'] is False and settings['vertex_group']=='' and settings['use_vertex_groups'] is True
        and settings['show_render'] is True and settings['show_viewport'] is True and settings['is_override_data'] is False,'modifier_semantics')
    original=mesh['vertices'];triangles=mesh['triangles'];weights=mesh['weights'];groups=mesh['groups']
    need(type(original) is list and 1<=len(original)<=256,'vertex_limit')
    for point in original:vector(point,3,'vertex_vector');need(all(abs(v)<=10 for v in point),'coordinate_bound')
    need(type(triangles) is list and 1<=len(triangles)<=256 and all(type(t) is list and len(t)==3 and all(type(v) is int and 0<=v<len(original) for v in t) and len(set(t))==3 for t in triangles),'triangles')
    need(type(mesh['edges']) is list and len(mesh['edges'])<=LIMITS['edges'],'edge_limit')
    need(all(type(e) is list and len(e)==2 and all(type(v) is int and 0<=v<len(original) for v in e) and len(set(e))==2 for e in mesh['edges']),'edges')
    need(type(groups) is list and len(groups)<=32 and all(r.text(v) for v in groups) and len(set(groups))==len(groups),'groups')
    need(type(weights) is list and len(weights)==len(original),'weights_count')
    fields(evaluated,{'bones','mesh_matrix_world','rig_matrix_world','original_links_verified','vertices','triangles'},'evaluated_fields')
    need(evaluated['original_links_verified'] is True and evaluated['triangles']==triangles and all(type(v) is int for t in evaluated['triangles'] for v in t),'evaluated_topology')
    for key,obj in (('mesh_matrix_world',mesh_obj),('rig_matrix_world',rig_obj)):
        matrix(evaluated[key]);need(residual(evaluated[key],obj['matrix_world'])<=MATRIX_ATOL,'evaluated_world_binding','unavailable')
    current=evaluated['vertices'];need(type(current) is list and len(current)==len(original),'evaluated_vertex_count')
    for point in current:vector(point,3,'evaluated_vertex_vector');need(all(abs(v)<=10 for v in point),'coordinate_bound')
    need(type(evaluated['bones']) is list and len(evaluated['bones'])==len(bones),'evaluated_bone_count');seen=set()
    for bone in evaluated['bones']:
        fields(bone,{'name','parent','pose_matrix','pose_head','pose_tail'},'evaluated_bone_fields');need(bone['name'] in bones and bone['name'] not in seen,'evaluated_bone_identity');seen.add(bone['name']);raw=bones[bone['name']]
        matrix(bone['pose_matrix']);vector(bone['pose_head'],3,'evaluated_bone_vector');vector(bone['pose_tail'],3,'evaluated_bone_vector')
        need(bone['parent']==raw['parent'] and max(residual(bone[k],raw[k]) for k in ('pose_matrix','pose_head','pose_tail'))<=MATRIX_ATOL,'evaluated_pose_binding','unavailable')
    animation_count=animation_check(inputs,objects,bones,deadline_ns)
    into=r.multiply(r.inverse(evaluated['rig_matrix_world']),evaluated['mesh_matrix_world']);back=r.inverse(into)
    deforms={name:r.multiply(b['pose_matrix'],r.inverse(b['rest_matrix'])) for name,b in bones.items()};unweighted=[];max_error=0.
    for index,(point,row,actual) in enumerate(zip(original,weights,current)):
        check(deadline_ns);need(type(row) is list and len(row)<=8,'influence_limit')
        need(all(type(w) is list and len(w)==2 and type(w[0]) is int and 0<=w[0]<len(groups) and r.finite(w[1]) and 0<=w[1]<=1 for w in row),'weight_shape')
        need([g for g,_ in row]==sorted({g for g,_ in row}),'weight_group_order');active=[(g,w) for g,w in row if w>0]
        if not active:predicted=point;unweighted.append(index)
        else:
            total=math.fsum(w for _,w in active);need(abs(total-1)<=1e-6,'weight_sum')
            need(all(groups[g] in bones and bones[groups[g]]['use_deform'] for g,w in active),'weight_bone')
            p=r.point(into,point);mapped=[(w/total,r.point(deforms[groups[g]],p)) for g,w in active]
            predicted=r.point(back,[math.fsum(w*q[axis] for w,q in mapped) for axis in range(3)])
        error=residual(predicted,actual);need(error<=POSITION_ATOL,'LBS_replay_disagreement');max_error=max(max_error,error)
    check(deadline_ns)
    mesh_instances=r.decode(binding.mesh_identity);rig_instances=r.decode(binding.rig_identity)
    result=dict(schema='validated-small-skin-geometry-v1',original=copy.deepcopy(original),current=copy.deepcopy(current),triangles=copy.deepcopy(triangles),
        world=copy.deepcopy(evaluated['mesh_matrix_world']),unit=inputs['unit_scale_m'],unweighted=unweighted,source_sha256=packet['source_sha256'],
        rig_world=copy.deepcopy(evaluated['rig_matrix_world']),
        bone_landmarks=[dict(name=b['name'],parent=b['parent'],connected=bones[b['name']]['connected'],use_deform=bones[b['name']]['use_deform'],
            head=copy.deepcopy(b['pose_head']),tail=copy.deepcopy(b['pose_tail'])) for b in evaluated['bones']],
        source=dict(source_kind=SCHEMA,document_epoch=binding.document_epoch,process_id=binding.process_id,scene_sha256=binding.scene_sha256,
            object_id='blender:'+r.digest(['',binding.rig_name]),rig_identity=rig_instances,mesh_instances=mesh_instances,
            mesh_identity=dict(name=binding.mesh_name,object_id='blender:'+r.digest(['',binding.mesh_name]),
                object_instance=str(mesh_instances['identity']['session_uid']),data_name=mesh_instances['data_identity']['name'],
                data_instance=str(mesh_instances['data_identity']['session_uid'])),frame=copy.deepcopy(frame),unit_scale_m=inputs['unit_scale_m']),
        bones_total=len(bones),max_replay_error=max_error,animation_curves_checked=animation_count,execution_authority=False)
    check(deadline_ns);return result


def validate(packet,*,deadline_ns,expected_bindings,expected_source=None):
    try:return _validate(packet,deadline_ns=deadline_ns,expected_bindings=expected_bindings,expected_source=expected_source)
    except SmallSourceError:raise
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,RecursionError) as exc:
        raise SmallSourceError('malformed_packet') from exc
