"""Independent NumPy qualification of a frozen small LBS source, not runtime.

This research verifier never edits captured channels or grants product support.
The production source contract, limits, and entry points are unchanged.
"""
import argparse,copy,hashlib,json,math,re,time
from pathlib import Path
import numpy as np

LIMITS=dict(vertices=256,triangles=256,bones=16,objects=16,parent_depth=8,groups=32,influences=8,snapshot_bytes=512*1024,actions=16,curves=64,curve_keys=256)
POSITION_ATOL=2e-5
MATRIX_ATOL=2e-5
GRAM_ATOL=2e-5
MAX_CONDITION=1e4


class Refusal(ValueError):
    def __init__(self,reason,status='rejected'):self.reason=reason;self.status=status;super().__init__(reason)


def need(value,reason,status='rejected'):
    if not value:raise Refusal('b3_'+reason,status)


def check_time(deadline):need(type(deadline) is int and time.perf_counter_ns()<deadline,'original_deadline','unknown')
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def source_digest(packet):return digest({k:v for k,v in packet.items() if k not in ('capture_id','source_sha256')})
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def hex64(v):return type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v)


def matrix(value):
    need(type(value) is list and len(value)==4 and all(type(row) is list and len(row)==4 and all(finite(v) for v in row) for row in value),'matrix_shape')
    a=np.asarray(value,dtype=float);need(np.array_equal(a[3],[0.,0.,0.,1.]),'matrix_affine')
    condition=float(np.linalg.cond(a[:3,:3]));need(math.isfinite(condition) and condition<=MAX_CONDITION,'matrix_condition','unknown')
    need(np.linalg.det(a[:3,:3])>0,'matrix_reflection')
    return a


def residual(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def gram_error(a):return residual(a[:3,:3].T@a[:3,:3],np.eye(3))


def rotation_channel(bone):
    mode=bone['rotation_mode'];result=np.eye(4)
    if mode=='QUATERNION':
        q=np.asarray(bone['rotation_quaternion'],dtype=float);length=float(np.linalg.norm(q));need(length>1e-12,'quaternion_zero')
        w,x,y,z=q/length
        result[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
            [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
            [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    elif mode=='AXIS_ANGLE':
        angle,*axis=bone['rotation_axis_angle'];axis=np.asarray(axis,dtype=float);length=float(np.linalg.norm(axis))
        need(length>1e-12 or angle==0,'axis_angle_zero');axis=axis/length if length else np.array([0.,0.,1.])
        x,y,z=axis;c=math.cos(angle);s=math.sin(angle);cross=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
        result[:3,:3]=c*np.eye(3)+(1-c)*np.outer(axis,axis)+s*cross
    else:
        need(mode in ('XYZ','XZY','YXZ','YZX','ZXY','ZYX'),'rotation_mode')
        for axis in mode:
            angle=bone['rotation_euler']['XYZ'.index(axis)];c=math.cos(angle);s=math.sin(angle);m=np.eye(4);i,j={'X':(1,2),'Y':(2,0),'Z':(0,1)}[axis]
            m[i,i]=m[j,j]=c;m[i,j]=-s;m[j,i]=s;result=m@result
    result[:3,:3]=result[:3,:3]@np.diag(bone['scale']);result[:3,3]=bone['location']
    return result


def independent_matrices(inputs,evaluated,deadline_ns):
    """Full affine NumPy products/inverses; captured values are never repaired."""
    closure={v['name']:v for v in inputs['closure']};object_errors=[];all_matrices=[]
    for obj in inputs['closure']:
        check_time(deadline_ns);basis=matrix(obj['matrix_basis']);local=matrix(obj['matrix_local']);world=matrix(obj['matrix_world']);inverse=matrix(obj['matrix_parent_inverse'])
        all_matrices.extend((basis,local,world,inverse));parent=obj['parent']
        expected_local=basis if parent is None else inverse@basis
        expected_world=expected_local if parent is None else matrix(closure[parent]['matrix_world'])@expected_local
        object_errors.append(dict(name=obj['name'],basis=residual(basis,rotation_channel(obj)),local=residual(local,expected_local),world=residual(world,expected_world)))
    rig=inputs['rig'];mesh=inputs['mesh'];bones={b['name']:b for b in rig['bones']};ev={b['name']:b for b in evaluated['bones']}
    fk_errors=[];basis_errors=[];raw_scale=[];raw_location=[]
    for b in rig['bones']:
        check_time(deadline_ns);rest=matrix(b['rest_matrix']);basis=matrix(b['basis_matrix']);pose=matrix(ev[b['name']]['pose_matrix'])
        all_matrices.extend((rest,basis,pose));expected=rest@basis
        if b['parent'] is not None:
            parent=bones[b['parent']];expected=matrix(ev[b['parent']]['pose_matrix'])@np.linalg.inv(matrix(parent['rest_matrix']))@rest@basis
        fk_errors.append(dict(name=b['name'],absolute=residual(pose,expected),relative=residual(pose,expected)/max(1.,float(np.max(np.abs(pose))))))
        basis_errors.append(dict(name=b['name'],error=residual(basis,rotation_channel(b))))
        raw_scale.append(dict(name=b['name'],maximum_deviation_from_one=max(abs(v-1) for v in b['scale'])))
        raw_location.append(dict(name=b['name'],maximum_absolute=max(abs(v) for v in b['location'])))
    rig_world=matrix(evaluated['rig_matrix_world']);mesh_world=matrix(evaluated['mesh_matrix_world']);all_matrices.extend((rig_world,mesh_world))
    bind=np.linalg.solve(rig_world,mesh_world);back=np.linalg.inv(bind);deforms={name:matrix(ev[name]['pose_matrix'])@np.linalg.inv(matrix(b['rest_matrix'])) for name,b in bones.items()}
    expected=[];errors=[];weight_sum_errors=[];unweighted=[]
    for index,(point,influences,actual) in enumerate(zip(mesh['vertices'],mesh['weights'],evaluated['vertices'])):
        check_time(deadline_ns);active=[(group,weight) for group,weight in influences if weight>0];total=math.fsum(w for _,w in active)
        if not active:predicted=np.asarray(point);unweighted.append(index)
        else:
            weight_sum_errors.append(abs(total-1.));q=bind@np.array([*point,1.]);p=np.zeros(4)
            for group,weight in active:p+=(weight/total)*(deforms[mesh['groups'][group]]@q)
            predicted=(back@p)[:3]
        expected.append(predicted.tolist());errors.append(float(np.max(np.abs(predicted-np.asarray(actual)))))
    result=dict(object_parent_products=object_errors,FK= fk_errors,raw_channel_basis=basis_errors,raw_scale=raw_scale,raw_location=raw_location,
        maximum_gram_residual=max(gram_error(a) for a in all_matrices),maximum_affine_condition=max(float(np.linalg.cond(a[:3,:3])) for a in all_matrices),
        maximum_object_matrix_error=max([x['local'] for x in object_errors]+[x['world'] for x in object_errors]),
        maximum_object_channel_basis_error=max(x['basis'] for x in object_errors),
        maximum_FK_error=max(x['absolute'] for x in fk_errors),maximum_FK_relative_error=max(x['relative'] for x in fk_errors),
        maximum_channel_basis_error=max(x['error'] for x in basis_errors),maximum_raw_scale_deviation=max(x['maximum_deviation_from_one'] for x in raw_scale),
        maximum_raw_translation=max(x['maximum_absolute'] for x in raw_location),maximum_weight_sum_error=max(weight_sum_errors,default=0.),
        vertices_total=len(expected),unweighted_vertices=unweighted,LBS_maximum_error=max(errors),LBS_p50_error=float(np.percentile(errors,50)),
        LBS_p95_error=float(np.percentile(errors,95)),LBS_errors=errors,independent_evaluated_vertices=expected,
        conformance_atol=POSITION_ATOL,conformance_is_not_coordinate_measurement_error=True,raw_values_normalized_or_zeroed=False)
    check_time(deadline_ns);return result


def validate_structure(packet,deadline_ns,expected_source_sha256):
    check_time(deadline_ns)
    need(type(packet) is dict and set(packet)=={'schema','identity','inputs','evaluated','audit','capture_id','source_sha256'} and packet['schema']=='b3-source-probe-v1','packet_schema')
    need(len(encoded(packet))<=LIMITS['snapshot_bytes'],'snapshot_bytes')
    need(hex64(packet['source_sha256']) and packet['source_sha256']==source_digest(packet),'source_digest')
    if expected_source_sha256 is not None:need(hex64(expected_source_sha256) and packet['source_sha256']==expected_source_sha256,'stale_source')
    ident=packet['identity'];need(type(ident) is dict and set(ident)=={'document_epoch','scene_sha256','profile_sha256','probe_sha256','binary_sha256'} and all(hex64(ident[k]) for k in ident if k!='document_epoch'),'identity')
    need(type(ident['document_epoch']) is str and re.fullmatch('[0-9a-f]{32}',ident['document_epoch']) is not None,'document_epoch')
    audit=packet['audit'];need(type(audit) is dict and set(audit)=={'before_sha256','after_sha256','independent_before_sha256','independent_after_sha256'} and all(hex64(v) for v in audit.values()),'audit_shape')
    need(audit['before_sha256']==audit['after_sha256']==digest(packet['inputs']) and audit['independent_before_sha256']==audit['independent_after_sha256'],'audit_changed')
    i=packet['inputs'];need(set(i)=={'actions','closure','context','frame','mesh','rig','scene','unit_scale_m'},'input_fields')
    frame=i['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int and finite(frame['subframe']) and 0<=frame['subframe']<1,'frame')
    need(finite(i['unit_scale_m']) and 0<i['unit_scale_m']<=1e6,'unit_scale')
    need(i['context']['mode']=='OBJECT','mode')
    need(type(i['scene']['objects']) is list and 1<=len(i['scene']['objects'])<=LIMITS['objects'],'scene_count')
    need(type(i['scene'].get('fps')) is int and i['scene']['fps']>0 and finite(i['scene'].get('fps_base')) and i['scene']['fps_base']>0,'scene_fps')
    need(type(i['actions']) is list and len(i['actions'])<=LIMITS['actions'],'action_limit')
    closure=i['closure'];need(type(closure) is list and 1<=len(closure)<=LIMITS['objects'],'closure_count')
    names=[o['name'] for o in closure];need(all(type(n) is str and n for n in names) and len(set(names))==len(names),'object_names')
    lookup={o['name']:o for o in closure};rig=i['rig'];mesh=i['mesh']
    need(rig['name'] in lookup and mesh['name'] in lookup and lookup[rig['name']]['type']=='ARMATURE' and lookup[mesh['name']]['type']=='MESH','closure_missing')
    scene_rows={o['name']:o for o in i['scene']['objects']};need(len(scene_rows)==len(i['scene']['objects']),'scene_names')
    for obj in closure:
        check_time(deadline_ns);need(obj['parent_type']=='OBJECT' and not obj['parent_bone'],'parent_type')
        need(obj['parent'] is None or obj['parent'] in lookup,'parent_missing')
        need(obj['name'] in scene_rows and scene_rows[obj['name']]['identity']==obj['identity'] and scene_rows[obj['name']]['data_identity']==obj['data_identity'] and scene_rows[obj['name']]['type']==obj['type'],'object_identity_binding')
        need(obj['parent_identity']==(None if obj['parent'] is None else lookup[obj['parent']]['identity']),'parent_identity_binding')
        visited=set();current=obj['name']
        while current is not None:
            need(current not in visited,'parent_cycle');visited.add(current);need(len(visited)<=LIMITS['parent_depth'],'parent_depth');current=lookup[current]['parent']
        for key in ('matrix_basis','matrix_local','matrix_parent_inverse','matrix_world'):matrix(obj[key])
        need(max(abs(obj['matrix_world'][axis][3]) for axis in range(3))<=100,'world_translation_bound')
        need(all(type(obj[k]) is bool for k in ('object_linked','data_linked','object_override','data_override')),'linked_flag_type')
    need(lookup[rig['name']]['data_identity']['name']==rig['data_name'] and lookup[mesh['name']]['data_identity']['name']==mesh['data_name'],'data_identity_binding')
    need(type(rig['bones']) is list and 1<=len(rig['bones'])<=LIMITS['bones'],'bone_limit')
    bones={b['name']:b for b in rig['bones']};need(len(bones)==len(rig['bones']),'bone_names')
    for bone in rig['bones']:
        check_time(deadline_ns);need(bone['parent'] is None or bone['parent'] in bones,'bone_parent_missing')
        visited=set();current=bone['name']
        while current is not None:
            need(current not in visited,'bone_parent_cycle');visited.add(current);current=bones[current]['parent']
        for key,count in (('location',3),('scale',3),('rotation_euler',3),('rotation_quaternion',4),('rotation_axis_angle',4),('rest_head',3),('rest_tail',3),('pose_head',3),('pose_tail',3)):
            need(type(bone[key]) is list and len(bone[key])==count and all(finite(v) for v in bone[key]),'bone_vector')
        for key in ('rest_matrix','basis_matrix','pose_matrix'):matrix(bone[key])
    vertices=mesh['vertices'];triangles=mesh['triangles'];need(type(vertices) is list and 1<=len(vertices)<=LIMITS['vertices'],'vertex_limit')
    need(all(type(v) is list and len(v)==3 and all(finite(x) for x in v) for v in vertices),'vertices')
    need(all(abs(x)<=10 for v in vertices for x in v),'coordinate_bound')
    need(type(triangles) is list and 1<=len(triangles)<=LIMITS['triangles'] and all(type(t) is list and len(t)==3 and len(set(t))==3 and all(type(v) is int and 0<=v<len(vertices) for v in t) for t in triangles),'triangles')
    need(type(mesh['groups']) is list and len(mesh['groups'])<=LIMITS['groups'] and len(set(mesh['groups']))==len(mesh['groups']),'group_limit')
    need(type(mesh['weights']) is list and len(mesh['weights'])==len(vertices),'weights_count')
    for row in mesh['weights']:
        need(type(row) is list and len(row)<=LIMITS['influences'],'influence_limit')
        need(all(type(w) is list and len(w)==2 and type(w[0]) is int and 0<=w[0]<len(mesh['groups']) and finite(w[1]) and 0<=w[1]<=1 for w in row),'weight_shape')
        need([g for g,_ in row]==sorted({g for g,_ in row}),'weight_group_order')
        active=[(g,w) for g,w in row if w>0]
        if active:
            need(abs(math.fsum(w for _,w in active)-1)<=1e-6,'nonunit_weight_sum')
            need(all(mesh['groups'][g] in bones and bones[mesh['groups'][g]]['use_deform'] for g,w in active),'weight_bone')
    e=packet['evaluated'];need(set(e)=={'bones','mesh_matrix_world','original_links_verified','rig_matrix_world','triangles','vertices'} and e['original_links_verified'] is True,'evaluated_binding')
    need(residual(matrix(e['rig_matrix_world']),lookup[rig['name']]['matrix_world'])<=MATRIX_ATOL and residual(matrix(e['mesh_matrix_world']),lookup[mesh['name']]['matrix_world'])<=MATRIX_ATOL,'evaluated_world_binding')
    need(e['triangles']==triangles and all(type(v) is int for t in e['triangles'] for v in t),'evaluated_topology')
    need(type(e['vertices']) is list and len(e['vertices'])==len(vertices) and all(type(v) is list and len(v)==3 and all(finite(x) for x in v) for v in e['vertices']),'evaluated_vertices')
    need(all(abs(x)<=10 for v in e['vertices'] for x in v),'coordinate_bound')
    need(type(e['bones']) is list and len(e['bones'])==len(bones) and {b['name'] for b in e['bones']}==set(bones),'evaluated_bones')
    for b in e['bones']:
        original=bones[b['name']];need(b['parent']==original['parent'],'evaluated_bone_parent');pose=matrix(b['pose_matrix'])
        need(residual(pose,original['pose_matrix'])<=MATRIX_ATOL and residual(b['pose_head'],original['pose_head'])<=MATRIX_ATOL and residual(b['pose_tail'],original['pose_tail'])<=MATRIX_ATOL,'evaluated_pose_binding')
        need(finite(original['length']) and 1e-8<original['length']<=1e6,'bone_length')
        for transform,head,tail in ((matrix(original['rest_matrix']),original['rest_head'],original['rest_tail']),(pose,b['pose_head'],b['pose_tail'])):
            need(residual((transform@np.array([0,0,0,1]))[:3],head)<=MATRIX_ATOL and residual((transform@np.array([0,original['length'],0,1]))[:3],tail)<=MATRIX_ATOL,'endpoint_matrix')
    check_time(deadline_ns);return i,e


def curve_value(curve,frame):
    need(curve['driver'] is None,'driver');need(not curve['modifiers'],'curve_modifier')
    need(curve['mute'] is False and curve['is_valid'] is True and not curve['sampled_points'],'curve_state')
    keys=curve['keys'];need(type(keys) is list and 1<=len(keys)<=LIMITS['curve_keys'],'curve_key_limit')
    points=[key['co'] for key in keys];need(all(type(p) is list and len(p)==2 and all(finite(x) for x in p) for p in points),'curve_key_shape')
    need(all(a[0]<b[0] for a,b in zip(points,points[1:])),'curve_key_order')
    for x,y in points:
        if frame==x:return float(y)
    if frame<points[0][0] or frame>points[-1][0]:
        need(curve['extrapolation']=='CONSTANT','curve_extrapolation','unknown');return float(points[0][1] if frame<points[0][0] else points[-1][1])
    for index,(a,b) in enumerate(zip(points,points[1:])):
        if a[0]<frame<b[0]:
            mode=keys[index]['interpolation'];need(mode in ('CONSTANT','LINEAR'),'curve_interpolation','unknown')
            return float(a[1] if mode=='CONSTANT' else a[1]+(b[1]-a[1])*(frame-a[0])/(b[0]-a[0]))
    raise Refusal('b3_curve_interval','unknown')


def animation_metrics(inputs,deadline_ns):
    actions={a['name']:a for a in inputs['actions']};need(len(actions)==len(inputs['actions']),'action_names')
    bones={b['name']:b for b in inputs['rig']['bones']};checks=[];used=set();current=inputs['frame']['number']+inputs['frame']['subframe']
    pattern=re.compile(r'^pose\.bones\[("(?:[^"\\]|\\.)*")\]\.(location|scale|rotation_euler|rotation_quaternion|rotation_axis_angle)$')
    for obj in inputs['closure']:
        for owner in ('object','data'):
            data=obj['animation'][owner]
            if data is None:continue
            check_time(deadline_ns);need(not data['drivers'],'driver');need(data['use_tweak_mode'] is False,'tweak_mode')
            for track in data['nla_tracks']:
                need(type(track['mute']) is bool and type(track['is_solo']) is bool,'nla_state')
                need(track['mute'] and not track['is_solo'],'active_nla')
                for strip in track['strips']:
                    need(strip['action'] in actions and not strip['modifiers'] and not strip['fcurves'] and not strip['strips'],'nla_strip')
                    need(strip['action_id']==actions[strip['action']]['identity'],'action_identity')
            if data['action'] is None:continue
            need(obj['name']==inputs['rig']['name'] and owner=='object','animation_owner')
            need(data['action_blend_type']=='REPLACE' and type(data['action_influence']) in (int,float) and data['action_influence']==1 and data['action_extrapolation']=='HOLD','action_blend')
            need(data['action'] in actions,'action_missing');action=actions[data['action']];used.add(action['name'])
            need(data['action_id']==action['identity'],'action_identity')
            need(action['linked'] is False and action['override'] is False,'linked_source')
            need(action['is_action_layered'] is True and action['is_action_legacy'] is False and not action['use_cyclic'] and not action['use_frame_range'],'action_shape')
            need(len(action['slots'])==1 and data['action_slot'] is not None and type(data['action_slot_handle']) is int,'action_slot')
            slot=action['slots'][0];need(type(slot['handle']) is int and slot['handle']==data['action_slot_handle']==data['action_slot']['handle'] and slot['target_id_type']=='OBJECT','action_slot')
            need(slot['identifier']==data['action_slot']['identifier'] and data['action_slot']['target_id_type']=='OBJECT','action_slot')
            need(slot['users']==[obj['identity']],'action_slot')
            need(len(action['layers'])==1 and set(action['layers'][0])=={'name','strips'} and len(action['layers'][0]['strips'])==1,'action_shape');strip=action['layers'][0]['strips'][0]
            need(set(strip)=={'type','channelbags'} and strip['type']=='KEYFRAME' and len(strip['channelbags'])==1,'action_shape');bag=strip['channelbags'][0]
            need(set(bag)=={'slot_handle','fcurves'},'action_shape')
            need(type(bag['slot_handle']) is int and bag['slot_handle']==slot['handle'],'action_slot');seen=set()
            need(type(bag['fcurves']) is list and len(bag['fcurves'])<=LIMITS['curves'],'curve_limit')
            for curve in bag['fcurves']:
                check_time(deadline_ns);match=pattern.fullmatch(curve['data_path']);need(match is not None,'animation_path')
                name=json.loads(match.group(1));field=match.group(2);need(name in bones,'animation_path');b=bones[name];index=curve['array_index']
                need(type(index) is int and 0<=index<len(b[field]) and (name,field,index) not in seen,'animation_path');seen.add((name,field,index))
                if field.startswith('rotation_'):need(field==('rotation_quaternion' if b['rotation_mode']=='QUATERNION' else 'rotation_axis_angle' if b['rotation_mode']=='AXIS_ANGLE' else 'rotation_euler'),'animation_path')
                expected=curve_value(curve,current);actual=b[field][index]
                checks.append(dict(bone=name,field=field,index=index,expected=expected,actual=actual,absolute_error=abs(expected-actual)))
    need(set(actions)==used,'action_closure')
    need(all(c['absolute_error']<=MATRIX_ATOL for c in checks),'animation_channel_disagreement')
    return dict(method='independent exact-key/constant/linear scalar evaluation at captured current frame; no timeline stepping',curves=len(checks),checks=checks,
        maximum_channel_error=max([c['absolute_error'] for c in checks],default=0.),all_NLA_tracks_muted=True,source_changes_in_inactive_tracks_invalidate=True)


def dependency_checks(inputs):
    for obj in inputs['closure']:
        need(not any(obj[k] for k in ('object_linked','data_linked','object_override','data_override')),'linked_source')
        need(not obj['constraints'],'constraint')
        need(obj['delta_location']==[0,0,0] and obj['delta_scale']==[1,1,1] and obj['delta_rotation_euler']==[0,0,0] and obj['delta_rotation_quaternion']==[1,0,0,0],'delta_transform')
    rig=inputs['rig'];mesh=inputs['mesh'];need(rig['pose_position']=='POSE','rest_display')
    for b in rig['bones']:
        need(not b['constraints'],'constraint');need(b['inherit_rotation'] is True and b['inherit_scale']=='FULL' and b['local_location'] is True and b['bbone_segments']==1,'bone_inheritance')
        need(b['use_envelope_multiply'] is False,'bone_envelope')
    need(mesh['shape_keys'] is None,'shape_keys');mods=mesh['modifier'];need(type(mods) is list and len(mods)==1,'modifier_count')
    mod=mods[0];need(mod['type']=='ARMATURE' and mod['object']==rig['name'],'modifier_binding');s=mod['settings']
    linked_rig=next(o for o in inputs['closure'] if o['name']==rig['name']);need(mod['object_identity']==linked_rig['identity'],'modifier_binding')
    need(s['use_deform_preserve_volume'] is False,'DQ');need(s['use_bone_envelopes'] is False,'envelopes')
    need(s['use_multi_modifier'] is False and s['invert_vertex_group'] is False and s['vertex_group']=='' and s['use_vertex_groups'] is True and s['show_render'] is True and s['show_viewport'] is True,'modifier_settings')


def qualify(packet,*,deadline_ns,expected_source_sha256=None):
    report=dict(schema='b3-frozen-source-qualification-v1',status='unknown',dependency_admission='unknown',reasons=[],source_sha256=packet.get('source_sha256') if type(packet) is dict else None,
        scope='finite immutable-file current-frame source qualification only; no production admission, health or animation timeline certification',product_support_certified=False,
        geometry_setters=0,original_file_saved=False,raw_values_modified=False,execution_authority=False,numerical_replay=None,animation_evaluation=None)
    try:
        inputs,evaluated=validate_structure(packet,deadline_ns,expected_source_sha256)
        # Replay is useful evidence even if a later unsupported dependency makes
        # the source inadmissible. It cannot substitute for dependency closure.
        metrics=independent_matrices(inputs,evaluated,deadline_ns);report['numerical_replay']=metrics
        need(metrics['maximum_gram_residual']<=GRAM_ATOL,'nonrigid_matrix')
        need(max(metrics['maximum_object_matrix_error'],metrics['maximum_object_channel_basis_error'],metrics['maximum_FK_error'],metrics['maximum_channel_basis_error'])<=MATRIX_ATOL,'matrix_replay_disagreement')
        need(metrics['LBS_maximum_error']<=POSITION_ATOL,'LBS_replay_disagreement')
        dependency_checks(inputs);report['animation_evaluation']=animation_metrics(inputs,deadline_ns)
        check_time(deadline_ns);report.update(status='qualified',dependency_admission='qualified',source_coverage='partial_unweighted' if metrics['unweighted_vertices'] else 'complete_finite')
    except Refusal as exc:report.update(status=exc.status,dependency_admission=exc.status,reasons=[exc.reason])
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,np.linalg.LinAlgError) as exc:
        report.update(status='rejected',dependency_admission='rejected',reasons=['b3_malformed_packet'],error_type=type(exc).__name__)
    if type(deadline_ns) is not int or time.perf_counter_ns()>=deadline_ns:report.update(status='unknown',dependency_admission='unknown',reasons=['b3_original_deadline'])
    return report


def gltf_witness(packet,glb,*,fps,fps_base=1.,deadline_ns):
    """Second route from author GLB data, never a production/native self-answer.

    Supports only the finite anchor's one embedded mesh/skin, TRS or fixed node
    matrices, and STEP/LINEAR animation. Quaternion LINEAR uses shortest-path
    SLERP. The standard Y-up -> Z-up map is fixed, never fitted to the capture.
    """
    from verification.inspect_deformation_asset_intake import parse_glb,accessor_rows
    check_time(deadline_ns);need(finite(fps) and fps>0 and finite(fps_base) and fps_base>0,'gltf_fps')
    scene=packet['inputs']['scene'];need(scene.get('fps')==fps and scene.get('fps_base')==fps_base,'gltf_fps_source')
    doc,binary=parse_glb(glb);need(len(doc['meshes'])==len(doc['skins'])==1 and len(doc['meshes'][0]['primitives'])==1,'gltf_single_skin')
    primitive=doc['meshes'][0]['primitives'][0];attributes=primitive['attributes'];positions=np.asarray(accessor_rows(doc,binary,attributes['POSITION']))
    need(len(positions)<=LIMITS['vertices'],'gltf_vertex_limit');joints=accessor_rows(doc,binary,attributes['JOINTS_0']);weights=accessor_rows(doc,binary,attributes['WEIGHTS_0'])
    triangles=np.asarray(accessor_rows(doc,binary,primitive['indices']),dtype=int).reshape(-1,3).tolist();skin=doc['skins'][0]
    ibms=[np.asarray(v).reshape(4,4,order='F') for v in accessor_rows(doc,binary,skin['inverseBindMatrices'])] if 'inverseBindMatrices' in skin else [np.eye(4)]*len(skin['joints'])
    nodes=copy.deepcopy(doc['nodes']);seconds=(packet['inputs']['frame']['number']+packet['inputs']['frame']['subframe'])*fps_base/fps
    def slerp(a,b,t):
        a=a/np.linalg.norm(a);b=b/np.linalg.norm(b);value=float(a@b)
        if value<0:b=-b;value=-value
        if value>1-1e-12:return (1-t)*a+t*b
        angle=math.acos(min(1.,value));return (math.sin((1-t)*angle)*a+math.sin(t*angle)*b)/math.sin(angle)
    for animation in doc.get('animations',[]):
        for channel in animation['channels']:
            check_time(deadline_ns);sampler=animation['samplers'][channel['sampler']];mode=sampler.get('interpolation','LINEAR');need(mode in ('LINEAR','STEP'),'gltf_interpolation')
            xs=np.asarray(accessor_rows(doc,binary,sampler['input']))[:,0];ys=np.asarray(accessor_rows(doc,binary,sampler['output']));need(len(xs)==len(ys) and np.all(np.diff(xs)>0),'gltf_animation_times')
            index=int(np.searchsorted(xs,seconds,side='right'));target=channel['target'];field=target['path'];need(field in ('translation','rotation','scale'),'gltf_animation_path')
            if index==0:value=ys[0]
            elif index==len(xs):value=ys[-1]
            else:
                a,b=ys[index-1],ys[index];t=(seconds-xs[index-1])/(xs[index]-xs[index-1])
                value=a if mode=='STEP' else slerp(a,b,t) if field=='rotation' else (1-t)*a+t*b
            need('matrix' not in nodes[target['node']],'gltf_animated_matrix');nodes[target['node']][field]=value.tolist()
    parents={child:i for i,node in enumerate(nodes) for child in node.get('children',[])};world={};visiting=set()
    def node_world(index):
        check_time(deadline_ns)
        if index in world:return world[index]
        need(index not in visiting,'gltf_parent_cycle');visiting.add(index);node=nodes[index]
        if 'matrix' in node:local=np.asarray(node['matrix']).reshape(4,4,order='F')
        else:
            x,y,z,w=node.get('rotation',[0,0,0,1]);local=rotation_channel(dict(rotation_mode='QUATERNION',rotation_quaternion=[w,x,y,z],location=node.get('translation',[0,0,0]),scale=node.get('scale',[1,1,1])))
        world[index]=(node_world(parents[index]) if index in parents else np.eye(4))@local;visiting.remove(index);return world[index]
    mesh_nodes=[index for index,node in enumerate(nodes) if node.get('mesh')==0 and node.get('skin')==0];need(len(mesh_nodes)==1,'gltf_mesh_node')
    back=np.linalg.inv(node_world(mesh_nodes[0]));deform=[node_world(joint)@ibm for joint,ibm in zip(skin['joints'],ibms)]
    conversion=np.array([[1.,0,0,0],[0,0,-1.,0],[0,1.,0,0],[0,0,0,1.]])
    original=(conversion@np.column_stack((positions,np.ones(len(positions)))).T).T[:,:3];expected=[]
    for point,indices,values in zip(positions,joints,weights):
        check_time(deadline_ns);total=math.fsum(values);need(total>0,'gltf_unweighted')
        vector=sum((weight/total)*(deform[index]@np.array([*point,1.])) for index,weight in zip(indices,values) if weight>0)
        expected.append((conversion@back@vector)[:3].tolist())
    mesh=packet['inputs']['mesh'];need(triangles==mesh['triangles'],'gltf_triangle_correspondence')
    need(original.shape==np.asarray(mesh['vertices']).shape,'gltf_vertex_correspondence');position_error=residual(original,mesh['vertices']);need(position_error<=POSITION_ATOL,'gltf_vertex_correspondence')
    names=[doc['nodes'][index]['name'] for index in skin['joints']];weight_error=0.
    for indices,values,native in zip(joints,weights,mesh['weights']):
        author={name:0. for name in names};captured={name:0. for name in names}
        for index,value in zip(indices,values):author[names[index]]+=value
        for index,value in native:
            name=mesh['groups'][index];need(name in captured or value==0,'gltf_weight_bone')
            if name in captured:captured[name]+=value
        weight_error=max(weight_error,max(abs(author[name]-captured[name]) for name in names))
    need(weight_error<=1e-6,'gltf_weight_correspondence');evaluated_error=residual(expected,packet['evaluated']['vertices']);need(evaluated_error<=POSITION_ATOL,'gltf_skin_correspondence')
    check_time(deadline_ns)
    return dict(schema='b3-author-gltf-witness-v1',original_glb_sha256=hashlib.sha256(glb).hexdigest(),frame=packet['inputs']['frame'],fps=fps,fps_base=fps_base,
        author_seconds=seconds,fixed_axis_map='(x,y,z)->(x,-z,y)',triangles_same_order=True,vertices_total=len(expected),maximum_original_position_error=position_error,
        maximum_named_weight_error=weight_error,maximum_evaluated_position_error=evaluated_error,conformance_atol=POSITION_ATOL,
        method='author node TRS/column-major matrices, joint hierarchy, inverse bind matrices and LBS; shortest-path SLERP for LINEAR rotation',
        references=['https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html','https://github.khronos.org/glTF-Tutorials/gltfTutorial/gltfTutorial_007_Animations.html'],
        product_support_certified=False,scope='independent finite author-to-format-import witness; not general importer/animation conformance')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=qualify(json.loads(args.input.read_bytes()),deadline_ns=time.perf_counter_ns()+30_000_000_000)
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ('status','dependency_admission','reasons','product_support_certified')}))
