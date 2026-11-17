"""Finite static Copy Rotation evidence, independent of the unchanged FK API."""
from . import rig_pose as r

PROTOCOL='owned-rig-constraint-readonly-v1'
CONSISTENCY_ATOL=6e-5
CONSTRAINT_FIELDS={'bone','index','name','type','target_id','target_instance','owner_space','target_space','space_object','space_subtarget',
    'subtarget','mute','enabled','show_expanded','active','influence','is_valid','use_x','use_y','use_z','invert_x','invert_y','invert_z',
    'euler_order','mix_mode','use_offset'}
CHANNEL_FIELDS={'location':3,'scale':3,'rotation_euler':3,'rotation_quaternion':4,'rotation_axis_angle':4,
    'delta_location':3,'delta_scale':3,'delta_rotation_euler':3,'delta_rotation_quaternion':4}


def source_digest(packet):
    # A capture UUID is a read identity, not a change in scene state.
    return r.digest(dict(schema=packet['schema'],scene_sha256=packet['scene_sha256'],rig_source_sha256=packet['rig']['source_sha256'],
        rig_object_basis=packet['rig_object_basis'],bone_channels=packet['bone_channels'],target=packet['target'],constraint=packet['constraint'],audit=packet['audit']))


def same_matrix(a,b,rotation=True):
    return all(abs(a[i][j]-b[i][j])<=(CONSISTENCY_ATOL if j<3 else 2e-6*max(1,abs(a[i][j]),abs(b[i][j])))
        for i in range(3) for j in range(4) if rotation or j==3)


def delta(b,bones):
    if b['parent'] is None:return r.multiply(r.inverse(b['rest_matrix']),b['pose_matrix'])
    parent=bones[b['parent']];relative=r.multiply(r.inverse(parent['rest_matrix']),b['rest_matrix'])
    return r.multiply(r.inverse(relative),r.multiply(r.inverse(parent['pose_matrix']),b['pose_matrix']))


def validate(packet,*,deadline_ns,expected=None):
    r.check_time(deadline_ns)
    r.require(type(packet) is dict and set(packet)=={'schema','scene_sha256','rig','rig_object_basis','bone_channels','target','constraint','audit','source_sha256'}
        and packet['schema']=='rig-constraint-snapshot-v1' and len(r.encoded(packet))<=r.MAX_BYTES,'constraint_packet_fields_or_size')
    r.require(r.hex_text(packet['scene_sha256'],64),'constraint_file_pin')
    p=r.validate(packet['rig'],deadline_ns=deadline_ns);f=p['flags'];bones={b['name']:b for b in p['bones']}
    r.require(f==dict(constraints=1,animation=False,drivers=False,object_parent=False,pose_position='POSE'),'unsupported_rig_dependencies')
    r.matrix(packet['rig_object_basis']);r.require(r.rigid(p['object_matrix_world']) and r.rigid(packet['rig_object_basis'])
        and same_matrix(p['object_matrix_world'],packet['rig_object_basis']),'unsupported_rig_world_transform')
    t=packet['target'];r.require(type(t) is dict and set(t)=={'name','object_id','object_instance','object_type','matrix_world','basis_matrix','channels',
        'animation','drivers','object_parent','constraints','linked'},'constraint_target_fields')
    r.require(r.text(t['name']) and r.text(t['object_instance']) and t['object_id']=='blender:'+r.digest(['',t['name']])
        and t['object_id']!=packet['rig']['identity']['object_id'] and t['object_type']=='EMPTY','constraint_target_identity')
    r.require(all(type(t[k]) is bool and t[k] is False for k in ('animation','drivers','object_parent','linked'))
        and type(t['constraints']) is int and t['constraints']==0,'unsupported_target_dependencies')
    for key in ('matrix_world','basis_matrix'):r.matrix(t[key]);r.require(r.rigid(t[key]),'unsupported_target_transform')
    r.require(same_matrix(t['matrix_world'],t['basis_matrix']),'target_evaluated_basis_disagreement')
    ch=t['channels'];r.require(type(ch) is dict and set(ch)==set(CHANNEL_FIELDS)|{'rotation_mode'} and ch['rotation_mode'] in
        ('QUATERNION','AXIS_ANGLE','XYZ','XZY','YXZ','YZX','ZXY','ZYX'),'target_channel_fields')
    for key,n in CHANNEL_FIELDS.items():r.require(type(ch[key]) is list and len(ch[key])==n and all(r.finite(v) for v in ch[key]),'target_channel_vector')
    c=packet['constraint'];r.require(type(c) is dict and set(c)==CONSTRAINT_FIELDS,'constraint_settings_fields')
    r.require(c['bone'] in bones and type(c['index']) is int and c['index']==0 and r.text(c['name'])
        and c['target_id']==t['object_id'] and c['target_instance']==t['object_instance'],'constraint_target_binding')
    r.require(c['type']=='COPY_ROTATION' and c['owner_space']==c['target_space']=='WORLD' and c['mix_mode']=='REPLACE'
        and c['euler_order']=='AUTO' and c['space_object'] is None and c['space_subtarget']==c['subtarget']=='','unsupported_constraint_semantics')
    r.require(r.finite(c['influence']) and c['influence']==1 and all(c[k] is True for k in ('enabled','is_valid','use_x','use_y','use_z'))
        and all(c[k] is False for k in ('mute','invert_x','invert_y','invert_z','use_offset'))
        and type(c['active']) is bool and type(c['show_expanded']) is bool,'unsupported_constraint_options')
    raw=packet['bone_channels'];r.require(type(raw) is list and len(raw)==len(bones) and
        [v.get('name') for v in raw if type(v) is dict]==list(bones),'constraint_raw_channel_names')
    for b,ch in zip(bones.values(),raw):
        r.check_time(deadline_ns)
        r.require(set(ch)=={'name','basis','location','scale','mode','euler','quaternion','axis_angle'} and ch['basis']==b['basis_matrix']
            and ch['mode']==b['rotation_mode'] and ch['euler']==b['rotation_euler'] and ch['quaternion']==b['rotation_quaternion'],'constraint_raw_channel_binding')
        for key,n in (('location',3),('scale',3),('axis_angle',4)):
            r.require(type(ch[key]) is list and len(ch[key])==n and all(r.finite(v) for v in ch[key]),'constraint_raw_channel_vectors')
        r.require(ch['location']==[0,0,0] and ch['scale']==[1,1,1],'unsupported_raw_bone_translation_or_scale')
        r.require(b['inherit_rotation'] and b['inherit_scale']=='FULL' and b['local_location'] and b['bbone_segments']==1,'unsupported_bone_inheritance')
        r.require(all(r.rigid(b[k]) for k in ('rest_matrix','pose_matrix','basis_matrix')) and
            all(b['basis_matrix'][i][3]==0 for i in range(3)),'unsupported_bone_scale_or_translation')
        if b['parent'] is None:fk=r.multiply(b['rest_matrix'],b['basis_matrix'])
        else:
            parent=bones[b['parent']];fk=r.multiply(r.multiply(parent['pose_matrix'],r.inverse(parent['rest_matrix'])),r.multiply(b['rest_matrix'],b['basis_matrix']))
        r.require(same_matrix(fk,b['pose_matrix'],rotation=b['name']!=c['bone']),'constraint_FK_or_position_disagreement')
        r.require(r.rigid(delta(b,bones)),'constraint_effective_rotation_not_rigid')
    world=r.multiply(p['object_matrix_world'],bones[c['bone']]['pose_matrix'])
    r.require(all(abs(world[i][j]-t['matrix_world'][i][j])<=CONSISTENCY_ATOL for i in range(3) for j in range(3)),
        'constraint_world_rotation_disagrees_with_target')
    r.require(packet['audit']==packet['rig']['audit'] and packet['source_sha256']==source_digest(packet),'constraint_source_or_audit')
    if expected is not None:r.require(packet['source_sha256']==expected['source_sha256']
        and packet['rig']['identity']==expected['rig']['identity'],'constraint_stale_source')
    r.check_time(deadline_ns);return p


def analyze(packet,*,deadline_ns):
    p=validate(packet,deadline_ns=deadline_ns);bones={b['name']:b for b in p['bones']};facts=[];c=packet['constraint']
    for b in bones.values():
        r.check_time(deadline_ns);facts.append(dict(bone=b['name'],parent=b['parent'],constrained=b['name']==c['bone'],rule_registered=False,
            input_channel=r.angles(b['basis_matrix']),evaluated_local=r.angles(delta(b,bones)),
            world_head_m=[v*p['unit_scale_m'] for v in r.point(p['object_matrix_world'],b['pose_head'])],
            world_tail_m=[v*p['unit_scale_m'] for v in r.point(p['object_matrix_world'],b['pose_tail'])]))
    facts.sort(key=lambda b:(not b['constrained'],-b['evaluated_local']['rotation_deg'],b['bone']))
    partial=any(b['evaluated_local']['twist_deg'] is None for b in facts)
    return dict(schema='rig-constraint-diagnostic-v1',status='partial' if partial else 'observed',assessment='unassessed_no_rules',
        source=dict(packet['rig']['identity'],source_sha256=packet['source_sha256'],scene_sha256=packet['scene_sha256'],
            rig_sha256=packet['rig']['rig_sha256'],frame=p['frame'],constraint_sha256=r.digest(c)),
        target=dict(name=packet['target']['name'],object_id=packet['target']['object_id'],object_instance=packet['target']['object_instance']),
        domain='static_single_world_replace_copy_rotation',metric='evaluated_parent_rest_relative_visual_rotation_Y_swing_twist',
        bones_total=len(facts),bones=facts[:16],bones_omitted=max(0,len(facts)-16),rule_bones_total=0,unruled_bones_total=len(facts),
        damage_classification='not_inferred',execution_authority=False,geometry_setters=0,original_file_saved=False,
        not_checked=['role_orientation_limits','skin_deformation','rotation_winding','IK','animation','drivers','anatomical_plausibility','visibility'])
