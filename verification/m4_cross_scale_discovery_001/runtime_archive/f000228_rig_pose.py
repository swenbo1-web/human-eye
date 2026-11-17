"""Finite read-only FK pose facts; orientation limits never imply damage.

Rest matrices and evaluated pose matrices are armature-space transforms.
Angles below remove the current parent pose and the parent/rest relationship.
They describe visual orientation modulo full turns, not channel winding, skin
deformation, joint injury, anatomical plausibility or execution permission.
"""
import hashlib,json,math,time

PROTOCOL='owned-rig-pose-readonly-v1'
MAX_BONES=64
MAX_BYTES=512*1024
ANGLE_GUARD_DEG=.001
ROTATION_ATOL=2e-5
REST_FIELDS=('name','parent','rest_matrix','rest_head','rest_tail','length','inherit_rotation','inherit_scale','local_location','connected','bbone_segments')


def require(value,reason):
    if not value:raise ValueError('rig_pose_'+reason)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def finite(v):return type(v) in (int,float) and math.isfinite(v)
def text(v):return type(v) is str and 0<len(v)<=256 and not any(ord(c)<32 for c in v)
def hex_text(v,n):return type(v) is str and len(v)==n and all(c in '0123456789abcdef' for c in v)
def check_time(deadline):require(type(deadline) is int and time.perf_counter_ns()<deadline,'original_deadline')


def decode(blob):
    require(len(blob)<=MAX_BYTES,'byte_limit')
    def unique(pairs):
        result={}
        for key,value in pairs:require(key not in result,'duplicate_JSON_key');result[key]=value
        return result
    return json.loads(blob,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('rig_pose_nonfinite')))


def matrix(value):
    require(type(value) is list and len(value)==4 and all(type(row) is list and len(row)==4
        and all(finite(v) and abs(v)<=1e12 for v in row) for row in value),'matrix_shape_or_finite')
    require(value[3]==[0,0,0,1],'affine_matrix_required');return value


def multiply(a,b):return [[math.fsum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def point(a,p):return [math.fsum(a[i][j]*p[j] for j in range(3))+a[i][3] for i in range(3)]
def determinant(a):return a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])-a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])+a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0])


def inverse(a):
    det=determinant(a);require(abs(det)>1e-12,'singular_matrix')
    r=[[(a[(j+1)%3][(i+1)%3]*a[(j+2)%3][(i+2)%3]-a[(j+1)%3][(i+2)%3]*a[(j+2)%3][(i+1)%3])/det for j in range(3)] for i in range(3)]
    return [row+[-math.fsum(row[j]*a[j][3] for j in range(3))] for row in r]+[[0,0,0,1]]


def rigid(a):
    return abs(determinant(a)-1)<=ROTATION_ATOL and all(abs(math.fsum(a[k][i]*a[k][j] for k in range(3))-(1 if i==j else 0))<=ROTATION_ATOL for i in range(3) for j in range(3))


def quaternion(a):
    # Largest-diagonal construction avoids acos/trace loss near 0 and 180deg.
    candidates=[1+a[0][0]+a[1][1]+a[2][2],1+a[0][0]-a[1][1]-a[2][2],1-a[0][0]+a[1][1]-a[2][2],1-a[0][0]-a[1][1]+a[2][2]]
    index=max(range(4),key=candidates.__getitem__);value=math.sqrt(max(0,candidates[index]))/2
    require(value>1e-12,'rotation_quaternion_unavailable');den=4*value
    if index==0:q=[value,(a[2][1]-a[1][2])/den,(a[0][2]-a[2][0])/den,(a[1][0]-a[0][1])/den]
    elif index==1:q=[(a[2][1]-a[1][2])/den,value,(a[0][1]+a[1][0])/den,(a[0][2]+a[2][0])/den]
    elif index==2:q=[(a[0][2]-a[2][0])/den,(a[0][1]+a[1][0])/den,value,(a[1][2]+a[2][1])/den]
    else:q=[(a[1][0]-a[0][1])/den,(a[0][2]+a[2][0])/den,(a[1][2]+a[2][1])/den,value]
    norm=math.sqrt(math.fsum(v*v for v in q));q=[v/norm for v in q]
    return [-v for v in q] if q[0]<0 else q


def angles(a):
    w,x,y,z=quaternion(a);length=math.hypot(w,y)
    geodesic=math.degrees(2*math.atan2(math.sqrt(x*x+y*y+z*z),abs(w)))
    swing=math.degrees(2*math.atan2(math.hypot(x,z),length))
    if length<=math.sin(math.radians(ANGLE_GUARD_DEG)/2):return dict(rotation_deg=geodesic,swing_deg=swing,twist_deg=None,twist_status='singular_or_guarded_180_degree_swing')
    twist=math.degrees(2*math.atan2(y/length,w/length));twist=(twist+180)%360-180
    branch=abs(abs(twist)-180)<=ANGLE_GUARD_DEG
    return dict(rotation_deg=geodesic,swing_deg=swing,twist_deg=None if branch else twist,
        twist_status='branch_boundary_sign_unknown' if branch else 'observed_modulo_full_turns')


def rig_digest(payload):return digest([dict((k,b[k]) for k in REST_FIELDS) for b in payload['bones']])


def validate(snapshot,*,deadline_ns,expected_source=None):
    check_time(deadline_ns);require(type(snapshot) is dict and set(snapshot)=={'schema','identity','payload','source_sha256','rig_sha256','capture_id','audit'},'snapshot_fields')
    require(len(encoded(snapshot))<=MAX_BYTES and snapshot['schema']=='rig-pose-snapshot-v1','snapshot_size_or_schema')
    identity=snapshot['identity'];require(type(identity) is dict and set(identity)=={'document_epoch','object_id','object_instance','data_instance'}
        and all(text(v) for v in identity.values()) and hex_text(identity['document_epoch'],32),'source_identity')
    if expected_source is not None:require(identity==expected_source,'stale_or_foreign_source')
    p=snapshot['payload'];require(type(p) is dict and set(p)=={'object_name','data_name','frame','unit_scale_m','object_matrix_world','context','source_kind','flags','bones'},'payload_fields')
    require(text(p['object_name']) and text(p['data_name']) and p['source_kind']=='original_rest_and_evaluated_current_pose','source_kind')
    require(identity['object_id']=='blender:'+digest(['',p['object_name']]),'object_name_identity')
    require(type(p['frame']) is dict and set(p['frame'])=={'number','subframe'} and type(p['frame']['number']) is int
        and finite(p['frame']['subframe']) and 0<=p['frame']['subframe']<1,'frame')
    require(finite(p['unit_scale_m']) and 0<p['unit_scale_m']<=1e6,'declared_unit_scale');matrix(p['object_matrix_world']);inverse(p['object_matrix_world'])
    context=p['context'];require(type(context) is dict and set(context)=={'mode','active_object','selected_objects'}
        and context['mode'] in ('OBJECT','POSE') and (context['active_object'] is None or text(context['active_object']))
        and type(context['selected_objects']) is list and len(context['selected_objects'])<=32
        and all(text(v) for v in context['selected_objects']) and context['selected_objects']==sorted(set(context['selected_objects'])),'context_binding')
    flags=p['flags'];require(type(flags) is dict and set(flags)=={'constraints','animation','drivers','object_parent','pose_position'}
        and type(flags['constraints']) is int and flags['constraints']>=0 and all(type(flags[k]) is bool for k in ('animation','drivers','object_parent'))
        and flags['pose_position'] in ('POSE','REST'),'domain_flags')
    require(type(p['bones']) is list and 1<=len(p['bones'])<=MAX_BONES,'bone_limit')
    names=[b.get('name') for b in p['bones'] if type(b) is dict]
    require(len(names)==len(p['bones']) and all(text(v) for v in names) and names==sorted(set(names)),'bone_names_unique_sorted')
    bone_fields=set(REST_FIELDS)|{'pose_matrix','pose_head','pose_tail','basis_matrix','rotation_mode','rotation_euler','rotation_quaternion'}
    for b in p['bones']:
        check_time(deadline_ns);require(set(b)==bone_fields,'bone_fields')
        require(b['parent'] is None or b['parent'] in names and b['parent']!=b['name'],'bone_parent')
        for k in ('rest_matrix','pose_matrix','basis_matrix'):matrix(b[k])
        for k in ('rest_head','rest_tail','pose_head','pose_tail','rotation_euler','rotation_quaternion'):
            require(type(b[k]) is list and len(b[k])==(4 if k=='rotation_quaternion' else 3) and all(finite(v) for v in b[k]),'bone_vector')
        require(finite(b['length']) and 1e-8<b['length']<=1e6,'bone_length')
        require(all(type(b[k]) is bool for k in ('inherit_rotation','local_location','connected'))
            and text(b['inherit_scale']) and type(b['bbone_segments']) is int and b['bbone_segments']>=1 and text(b['rotation_mode']),'bone_flags')
        for mat,head,tail in (('rest_matrix','rest_head','rest_tail'),('pose_matrix','pose_head','pose_tail')):
            for calculated,actual in zip(point(b[mat],[0,0,0])+point(b[mat],[0,b['length'],0]),b[head]+b[tail]):
                require(abs(calculated-actual)<=2e-6*max(1,abs(calculated),abs(actual)),'endpoint_matrix_disagreement')
    lookup={b['name']:b for b in p['bones']}
    for name in names:
        visited=set();current=name
        while current is not None:
            require(current not in visited,'parent_cycle');visited.add(current);current=lookup[current]['parent']
    require(snapshot['source_sha256']==digest(dict(identity=identity,payload=p)) and snapshot['rig_sha256']==rig_digest(p),'source_or_rest_digest')
    audit=snapshot['audit'];require(type(audit) is dict and set(audit)=={'before_sha256','after_sha256'}
        and hex_text(audit['before_sha256'],64) and audit['before_sha256']==audit['after_sha256'],'RNA_inputs_changed_during_capture')
    require(hex_text(snapshot['capture_id'],32),'capture_identity');return p


def analyze(snapshot,policy=None,*,deadline_ns):
    p=validate(snapshot,deadline_ns=deadline_ns);bones={b['name']:b for b in p['bones']};unsupported=[]
    f=p['flags']
    for key in ('constraints','animation','drivers','object_parent'):
        if f[key]:unsupported.append(key)
    if f['pose_position']!='POSE':unsupported.append('rest_display_mode')
    for b in bones.values():
        if not b['inherit_rotation'] or b['inherit_scale']!='FULL' or not b['local_location']:unsupported.append('nondefault_inheritance')
        if b['bbone_segments']!=1:unsupported.append('B_bone_segments')
        if not all(rigid(b[k]) for k in ('rest_matrix','pose_matrix','basis_matrix')):unsupported.append('bone_scale_or_shear')
    facts=[];by_name={}
    for b in bones.values():
        check_time(deadline_ns);fact=dict(bone=b['name'],parent=b['parent'],world_head_m=[v*p['unit_scale_m'] for v in point(p['object_matrix_world'],b['pose_head'])],
            world_tail_m=[v*p['unit_scale_m'] for v in point(p['object_matrix_world'],b['pose_tail'])])
        if unsupported:fact.update(rotation_deg=None,swing_deg=None,twist_deg=None,twist_status='unsupported_rig_domain')
        else:
            if b['parent'] is None:delta=multiply(inverse(b['rest_matrix']),b['pose_matrix'])
            else:
                parent=bones[b['parent']];rest_relative=multiply(inverse(parent['rest_matrix']),b['rest_matrix'])
                delta=multiply(inverse(rest_relative),multiply(inverse(parent['pose_matrix']),b['pose_matrix']))
            require(rigid(delta),'effective_rotation_not_rigid')
            require(all(abs(delta[i][j]-b['basis_matrix'][i][j])<=3*ROTATION_ATOL for i in range(3) for j in range(3)),
                'FK_evaluated_rotation_disagrees_with_channels')
            fact.update(angles(delta))
        facts.append(fact);by_name[b['name']]=fact
    violations=[];uncertain=[];rules_total=0
    if policy is not None:
        require(type(policy) is dict and set(policy)=={'schema','rig_sha256','provenance','rules'}
            and policy['schema']=='rig-pose-orientation-rules-v1' and text(policy['provenance'])
            and policy['rig_sha256']==snapshot['rig_sha256'],'policy_or_rest_binding')
        require(type(policy['rules']) is list and 1<=len(policy['rules'])<=MAX_BONES,'policy_rule_limit');seen=set()
        for rule in policy['rules']:
            check_time(deadline_ns);require(type(rule) is dict and set(rule)=={'bone','min_twist_deg','max_twist_deg','max_swing_deg'}
                and rule['bone'] in bones and rule['bone'] not in seen,'policy_bone')
            seen.add(rule['bone']);require(all(finite(rule[k]) for k in ('min_twist_deg','max_twist_deg','max_swing_deg'))
                and -180<=rule['min_twist_deg']<=rule['max_twist_deg']<=180 and 0<=rule['max_swing_deg']<=180,'policy_angle_bounds')
            for metric,limit,sign in (('twist_deg',rule['min_twist_deg'],-1),('twist_deg',rule['max_twist_deg'],1),('swing_deg',rule['max_swing_deg'],1)):
                rules_total+=1;value=by_name[rule['bone']][metric];item=dict(bone=rule['bone'],metric=metric,limit_deg=limit,value_deg=value,direction='maximum' if sign==1 else 'minimum')
                if value is None:uncertain.append(dict(item,reason='orientation_unavailable'))
                elif sign*(value-limit)>ANGLE_GUARD_DEG:violations.append(item)
                elif abs(value-limit)<=ANGLE_GUARD_DEG:uncertain.append(dict(item,reason='angular_guard_band'))
    ruled={rule['bone'] for rule in policy['rules']} if policy is not None else set()
    for fact in facts:fact['rule_registered']=fact['bone'] in ruled
    ranked=sorted(facts,key=lambda v:(0 if any(r['bone']==v['bone'] for r in violations) else 1,-(v['rotation_deg'] or 0),v['bone']))
    return dict(schema='rig-pose-diagnostic-v1',status='unsupported' if unsupported else 'partial' if uncertain else 'observed',
        assessment='outside_registered_orientation_limits' if violations else 'unknown' if uncertain or unsupported else 'within_registered_orientation_limits' if policy else 'unassessed_no_rules',
        source=dict(snapshot['identity'],source_sha256=snapshot['source_sha256'],rig_sha256=snapshot['rig_sha256'],frame=p['frame'],source_kind=p['source_kind']),
        metric='effective_parent_and_rest_relative_visual_rotation_Y_swing_twist',angular_guard_deg=ANGLE_GUARD_DEG,
        bones_total=len(facts),bones=ranked[:16],bones_omitted=max(0,len(facts)-16),rules_total=rules_total,
        rule_bones_total=len(ruled),unruled_bones_total=len(facts)-len(ruled),
        violations_total=len(violations),violations=violations[:16],violations_omitted=max(0,len(violations)-16),
        unknown_rules_total=len(uncertain),unknown_rules=uncertain[:16],unsupported_reasons=sorted(set(unsupported)),
        policy_source=None if policy is None else dict(schema=policy['schema'],provenance=policy['provenance'],canonical_sha256=digest(policy)),
        damage_classification='not_inferred',not_checked=['skin_deformation','rotation_winding','joint_translation_limits','self_contact','anatomical_plausibility','visibility'],
        execution_authority=False,geometry_setters=0,original_file_saved=False)
