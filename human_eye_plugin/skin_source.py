"""Finite static LBS source correspondence. Facts do not authorize mesh edits."""
import math
from . import rig_pose as r

PROTOCOL='owned-skin-source-readonly-v1'
MAX_VERTICES=128
MAX_TRIANGLES=256
MAX_INFLUENCES=8
POSITION_ATOL=2e-5
WEIGHT_ATOL=1e-6
MOD_FIELDS={'name','type','rig_id','rig_instance','show_viewport','show_render','use_vertex_groups','use_bone_envelopes',
    'use_deform_preserve_volume','use_multi_modifier','vertex_group','invert_vertex_group','count'}
MOD_RNA_FIELDS={'name','show_viewport','show_render','show_in_editmode','show_on_cage','show_expanded','is_active','use_pin_to_last',
    'use_apply_on_spline','object','use_bone_envelopes','use_vertex_groups','use_deform_preserve_volume','use_multi_modifier','vertex_group','invert_vertex_group'}


def source_digest(packet):
    return r.digest(dict(schema=packet['schema'],scene_sha256=packet['scene_sha256'],rig_source_sha256=packet['rig']['source_sha256'],
        rig_object_basis=packet['rig_object_basis'],bone_channels=packet['bone_channels'],deform_bones=packet['deform_bones'],mesh=packet['mesh'],audit=packet['audit']))


def rigid_object(matrix):
    r.matrix(matrix);r.require(r.rigid(matrix) and all(abs(matrix[i][3])<=100 for i in range(3)),'unsupported_skin_object_transform')


def validate(packet,*,deadline_ns,expected=None):
    r.check_time(deadline_ns);r.require(type(packet) is dict and set(packet)=={'schema','scene_sha256','rig','rig_object_basis','bone_channels',
        'deform_bones','mesh','audit','source_sha256'} and packet['schema']=='skin-source-snapshot-v1'
        and len(r.encoded(packet))<=r.MAX_BYTES and r.hex_text(packet['scene_sha256'],64),'skin_packet_fields_or_budget')
    p=r.validate(packet['rig'],deadline_ns=deadline_ns)
    # Preserve the old FK definition, including its refusal of nonrigid bones.
    rig_report=r.analyze(packet['rig'],deadline_ns=deadline_ns)
    r.require(rig_report['status']!='unsupported','unsupported_skin_rig_domain')
    rigid_object(p['object_matrix_world']);rigid_object(packet['rig_object_basis'])
    r.require(all(abs(p['object_matrix_world'][i][j]-packet['rig_object_basis'][i][j])<=POSITION_ATOL for i in range(4) for j in range(4)),
        'skin_rig_world_basis_disagreement')
    bones=p['bones'];raw=packet['bone_channels'];r.require(type(raw) is list and len(raw)==len(bones),'skin_raw_channel_count')
    bone_lookup={b['name']:b for b in bones}
    for b,ch in zip(bones,raw):
        r.check_time(deadline_ns)
        r.require(type(ch) is dict and set(ch)=={'name','basis','location','scale','mode','euler','quaternion','axis_angle'}
            and ch['name']==b['name'] and ch['basis']==b['basis_matrix'] and ch['mode']==b['rotation_mode']
            and ch['euler']==b['rotation_euler'] and ch['quaternion']==b['rotation_quaternion'],'skin_raw_channel_binding')
        for key,n in (('location',3),('scale',3),('axis_angle',4)):
            r.require(type(ch[key]) is list and len(ch[key])==n and all(r.finite(v) for v in ch[key]),'skin_raw_channel_vector')
        r.require(ch['location']==[0,0,0] and ch['scale']==[1,1,1],'unsupported_skin_raw_bone_translation_or_scale')
        if b['parent'] is None:fk=r.multiply(b['rest_matrix'],b['basis_matrix'])
        else:
            parent=bone_lookup[b['parent']];fk=r.multiply(r.multiply(parent['pose_matrix'],r.inverse(parent['rest_matrix'])),r.multiply(b['rest_matrix'],b['basis_matrix']))
        r.require(all(abs(fk[i][j]-b['pose_matrix'][i][j])<=(6e-5 if j<3 else POSITION_ATOL) for i in range(3) for j in range(4)),
            'skin_full_FK_pose_disagreement')
    deform=packet['deform_bones'];r.require(type(deform) is list and len(deform)==len(bones) and all(type(v) is dict and set(v)=={'use_deform','use_envelope_multiply'}
        and type(v['use_deform']) is bool and type(v['use_envelope_multiply']) is bool for v in deform),'skin_deform_flags')
    r.require(all(v['use_envelope_multiply'] is False for v in deform),'unsupported_skin_bone_envelope_multiply')
    m=packet['mesh'];r.require(type(m) is dict and set(m)=={'identity','object_matrix_world','basis_matrix','vertices','triangles','weights','groups',
        'evaluated_vertices','evaluated_triangles','flags','modifier'},'skin_mesh_fields')
    ident=m['identity'];r.require(type(ident) is dict and set(ident)=={'name','object_id','object_instance','data_name','data_instance'}
        and all(r.text(v) for v in ident.values()) and ident['object_id']=='blender:'+r.digest(['',ident['name']])
        and ident['object_id']!=packet['rig']['identity']['object_id'],'skin_mesh_identity')
    rigid_object(m['object_matrix_world']);rigid_object(m['basis_matrix'])
    r.require(all(abs(m['object_matrix_world'][i][j]-m['basis_matrix'][i][j])<=POSITION_ATOL for i in range(4) for j in range(4)),
        'skin_mesh_world_basis_disagreement')
    flags=m['flags'];r.require(type(flags) is dict and set(flags)=={'animation','drivers','object_parent','linked','shape_keys','constraints'}
        and all(type(flags[k]) is bool and flags[k] is False for k in ('animation','drivers','object_parent','linked','shape_keys'))
        and type(flags['constraints']) is int and flags['constraints']==0,'unsupported_skin_mesh_dependencies')
    mod=m['modifier'];r.require(type(mod) is dict and set(mod)==MOD_FIELDS and r.text(mod['name']) and mod['type']=='ARMATURE'
        and type(mod['count']) is int and mod['count']==1 and mod['rig_id']==packet['rig']['identity']['object_id']
        and mod['rig_instance']==packet['rig']['identity']['object_instance'],'unsupported_skin_modifier_binding')
    r.require(all(mod[k] is True for k in ('show_viewport','show_render','use_vertex_groups'))
        and all(mod[k] is False for k in ('use_bone_envelopes','use_deform_preserve_volume','use_multi_modifier','invert_vertex_group'))
        and mod['vertex_group']=='','unsupported_skin_modifier_semantics')
    vertices=m['vertices'];triangles=m['triangles'];evaluated=m['evaluated_vertices']
    r.require(type(vertices) is list and 1<=len(vertices)<=MAX_VERTICES and type(evaluated) is list and len(evaluated)==len(vertices),'unsupported_skin_vertex_limit_or_correspondence')
    for values in (vertices,evaluated):
        r.require(all(type(v) is list and len(v)==3 and all(r.finite(x) and abs(x)<=10 for x in v) for v in values),'unsupported_skin_coordinate_domain')
    r.require(type(triangles) is list and 1<=len(triangles)<=MAX_TRIANGLES and all(type(t) is list and len(t)==3
        and all(type(i) is int and 0<=i<len(vertices) for i in t) and len(set(t))==3 for t in triangles),'unsupported_skin_triangle_limit_or_indices')
    et=m['evaluated_triangles'];r.require(type(et) is list and len(et)==len(triangles) and all(type(t) is list and len(t)==3
        and all(type(i) is int for i in t) for t in et) and et==triangles,'skin_evaluated_topology_or_order_changed')
    groups=m['groups'];r.require(type(groups) is list and len(groups)<=64 and all(r.text(v) for v in groups) and len(set(groups))==len(groups),'unsupported_skin_group_names')
    weights=m['weights'];r.require(type(weights) is list and len(weights)==len(vertices),'skin_weight_vertex_binding')
    lookup={b['name']:i for i,b in enumerate(bones)};deformations=[r.multiply(b['pose_matrix'],r.inverse(b['rest_matrix'])) for b in bones]
    mesh_to_rig=r.multiply(r.inverse(p['object_matrix_world']),m['object_matrix_world']);rig_to_mesh=r.inverse(mesh_to_rig)
    residuals=[];unweighted=[]
    for index,(v,influences,actual) in enumerate(zip(vertices,weights,evaluated)):
        r.check_time(deadline_ns);r.require(type(influences) is list and len(influences)<=MAX_INFLUENCES,'unsupported_skin_influence_limit')
        r.require(all(type(w) is list and len(w)==2 and type(w[0]) is int and 0<=w[0]<len(groups)
            and r.finite(w[1]) and 0<=w[1]<=1 for w in influences),'skin_weight_shape')
        ids=[w[0] for w in influences];r.require(ids==sorted(set(ids)),'skin_weight_group_order')
        active=[w for w in influences if w[1]>0];total=math.fsum(w for _,w in active)
        if not active:predicted=v;unweighted.append(index)
        else:
            r.require(abs(total-1)<=WEIGHT_ATOL,'unsupported_skin_nonunit_weight_sum')
            r.require(all(groups[g] in lookup and deform[lookup[groups[g]]]['use_deform'] for g,_ in active),'unsupported_skin_unknown_or_nondeform_group')
            source=r.point(mesh_to_rig,v);transformed=[(w/total,r.point(deformations[lookup[groups[g]]],source)) for g,w in active]
            predicted=r.point(rig_to_mesh,[math.fsum(w*point[k] for w,point in transformed) for k in range(3)])
        error=max(abs(a-b) for a,b in zip(predicted,actual));r.require(error<=POSITION_ATOL,'skin_same_index_LBS_replay_disagreement');residuals.append(error)
    r.require(packet['audit']==packet['rig']['audit'] and packet['source_sha256']==source_digest(packet),'skin_source_or_audit_binding')
    if expected is not None:r.require(packet['source_sha256']==expected['source_sha256'] and packet['rig']['identity']==expected['rig']['identity']
        and ident==expected['mesh']['identity'],'skin_stale_source')
    r.check_time(deadline_ns);return dict(payload=p,unweighted=unweighted,max_replay_error=max(residuals),mesh_to_rig=mesh_to_rig)


def analyze(packet,*,deadline_ns):
    proof=validate(packet,deadline_ns=deadline_ns);m=packet['mesh'];unit=proof['payload']['unit_scale_m'];unweighted=set(proof['unweighted']);facts=[]
    for index,(before,after) in enumerate(zip(m['vertices'],m['evaluated_vertices'])):
        r.check_time(deadline_ns);a=r.point(m['object_matrix_world'],before);b=r.point(m['object_matrix_world'],after)
        facts.append(dict(vertex=index,weighted=index not in unweighted,world_original_m=[x*unit for x in a],world_evaluated_m=[x*unit for x in b],
            displacement_m=math.dist(a,b)*unit))
    facts.sort(key=lambda v:(v['weighted'],-v['displacement_m'],v['vertex']))
    return dict(schema='skin-source-diagnostic-v1',status='partial' if unweighted else 'observed',assessment='source_facts_only',
        correspondence='current_same_index_with_independent_LBS_replay',
        source=dict(packet['rig']['identity'],source_sha256=packet['source_sha256'],scene_sha256=packet['scene_sha256'],rig_sha256=packet['rig']['rig_sha256'],
            mesh_identity=m['identity'],frame=proof['payload']['frame']),
        binding_space='current_mesh_object_to_armature_object; not historical bind intent',mesh_to_armature=proof['mesh_to_rig'],
        vertices_total=len(facts),triangles_total=len(m['triangles']),weighted_vertices_total=len(facts)-len(unweighted),unweighted_vertices_total=len(unweighted),
        vertices=facts[:16],vertices_omitted=max(0,len(facts)-16),max_current_displacement_m=max(v['displacement_m'] for v in facts),
        max_LBS_replay_error_mesh_units=proof['max_replay_error'],LBS_replay_atol_mesh_units=POSITION_ATOL,
        damage_classification='not_inferred',execution_authority=False,geometry_setters=0,original_file_saved=False,
        not_checked=['intended_weight_quality','skin_damage','surface_stretch_or_collapse','volume_Jacobian','self_contact','continuous_motion','visibility'])
