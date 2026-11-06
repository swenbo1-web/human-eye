"""Pure eligibility review for a *new* preview after a confirmed feature stop.

This module neither authorizes nor executes anything. The caller owns task
authorization, the shared whole-goal budget, fresh discovery/preview, and host
CAS. Double captures bracket a native read; this is not an atomic host sample
and does not rule out an external ABA edit between the samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
import hashlib
import json
import math

CONTRACT_REVISION = 'confirmed-feature-continuation-v1-20261030'
MAX_SCENE_OBJECTS = 64
REPRESENTATION_ATOL_M = 4e-7
SEPARATION_M = 1e-6
_NATIVE_FIELDS = {'object_id','name','local_vertices','world_vertices','faces','matrix','color'}


def _number(v):
    return type(v) in (int,float) and math.isfinite(v)


@dataclass(frozen=True)
class ContinuationPolicy:
    focal_id: str
    reference_id: str
    target_clearance_m: float = .001
    clearance_tolerance_m: float = 1e-6
    direction_world: tuple = (0.,0.,1.)
    reference_triangle_index: int = 2
    max_step_translation_m: float = .001
    max_steps: int = 8
    max_total_translation_m: float = .008
    max_recoveries: int = 1
    measurement_agreement_m: float = 1e-6
    expected_engine_build_id: str | None = None
    max_segment_duration_s: float = 30.

    def __post_init__(self):
        if (type(self.focal_id) is not str or not self.focal_id.strip()
                or type(self.reference_id) is not str or not self.reference_id.strip()
                or self.focal_id == self.reference_id):
            raise ValueError('explicit distinct pair is required')
        for name,maximum,positive in (
                ('target_clearance_m',1.,True),('clearance_tolerance_m',1e-5,False),
                ('max_step_translation_m',.001,True),('max_total_translation_m',.008,True),
                ('measurement_agreement_m',1e-6,True),('max_segment_duration_s',30.,True)):
            value=getattr(self,name)
            if not _number(value) or value < 0 or positive and value == 0 or value > maximum:
                raise ValueError('invalid bounded policy: '+name)
        if (type(self.max_steps) is not int or not 1<=self.max_steps<=8
                or type(self.max_recoveries) is not int or not 0<=self.max_recoveries<=2
                or type(self.reference_triangle_index) is not int or self.reference_triangle_index<0):
            raise ValueError('invalid policy count/index')
        if self.expected_engine_build_id is not None:
            value=self.expected_engine_build_id
            if (type(value) is not str or len(value)!=71 or not value.startswith('sha256:')
                    or any(c not in '0123456789abcdef' for c in value[7:])):
                raise ValueError('invalid explicit engine build binding')
        # A tuple prevents callers mutating a supposedly frozen direction.
        if (type(self.direction_world) is not tuple or len(self.direction_world)!=3
                or not all(_number(v) for v in self.direction_world)
                or self.direction_world[:2] != (0.,0.) or abs(self.direction_world[2]) != 1.):
            raise ValueError('explicit signed unit world-Z direction required')


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _capture_fingerprint(value):
    # Router selection and residual fingerprints use UTF-8 JSON. Native
    # evidence revisions and detached audit hashes retain their ASCII schema.
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _result(decision,reasons=(),**facts):
    return {'schema_version':'1.0','contract_revision':CONTRACT_REVISION,
            'decision':decision,'reason_codes':list(reasons),'execution_authority':False,
            'retry_authorized':False,'requires_fresh_discovery':decision=='eligible_for_fresh_preview',
            'requires_fresh_preview':decision=='eligible_for_fresh_preview',
            'scope':'confirmed box-pair observation eligibility; not authorization or swept-path certification',**facts}


def _require(ok,code):
    if not ok: raise ValueError(code)


def _finite_tree(value,depth=0,count=None):
    count=[0] if count is None else count
    count[0]+=1
    _require(depth<=32 and count[0]<=200000,'evidence_resource_limit')
    if type(value) is str:
        _require(len(value)<=8192,'evidence_string_limit');return
    if value is None or type(value) is bool:return
    if type(value) in (int,float):
        _require(_number(value),'nonfinite_evidence');return
    if type(value) is list:
        for item in value:_finite_tree(item,depth+1,count)
        return
    if type(value) is dict:
        for key,item in value.items():
            _require(type(key) is str,'nonstring_evidence_key');_finite_tree(item,depth+1,count)
        return
    raise ValueError('nonplain_evidence')


def _vec(v,n=3):
    return type(v) is list and len(v)==n and all(_number(x) for x in v)


def _sub(a,b):return [x-y for x,y in zip(a,b)]
def _dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def _unit(v):
    length=math.hypot(*v)
    _require(math.isfinite(length) and length>0,'invalid_native_axes')
    return [x/length for x in v]


def _box(obj):
    """Exact local box topology, with explicitly represented rigid world axes."""
    _require(type(obj) is dict and set(obj)==_NATIVE_FIELDS,'incomplete_native_object')
    _require(type(obj['object_id']) is str and obj['object_id'] and type(obj['name']) is str,'invalid_native_identity')
    local,world,faces,matrix=(obj[k] for k in ('local_vertices','world_vertices','faces','matrix'))
    _require(type(local) is list and len(local)==8 and all(_vec(v) for v in local)
             and type(world) is list and len(world)==8 and all(_vec(v) for v in world),'closed_local_box_required')
    _require(type(matrix) is list and len(matrix)==4 and all(_vec(row,4) for row in matrix)
             and matrix[3]==[0,0,0,1] and _vec(obj['color'],4),'invalid_native_pose')
    low=[min(v[k] for v in local) for k in range(3)]
    high=[max(v[k] for v in local) for k in range(3)]
    _require(all(high[k]>low[k] for k in range(3)) and len(set(map(tuple,local)))==8
             and all(all(v[k] in (low[k],high[k]) for k in range(3)) for v in local),'closed_local_box_required')
    _require(type(faces) is list and len(faces)==12,'closed_local_box_required')
    rational=[tuple(Fraction(float(x)) for x in v) for v in local]
    center=[(Fraction(float(a))+Fraction(float(b)))/2 for a,b in zip(low,high)]
    edges={};seen=set();side_counts={};side_areas={}
    for face in faces:
        _require(type(face) is list and len(face)==3 and all(type(i) is int and 0<=i<8 for i in face)
                 and len(set(face))==3 and tuple(sorted(face)) not in seen,'closed_local_box_required')
        seen.add(tuple(sorted(face)));a,b,c=(rational[i] for i in face)
        normal=_cross(_sub(b,a),_sub(c,a))
        axes=[k for k,x in enumerate(normal) if x]
        _require(len(axes)==1,'closed_local_box_required');axis=axes[0]
        _require(all(p[axis]==a[axis] for p in (b,c)) and sum(x*y for x,y in zip(normal,_sub(a,center)))>0,
                 'closed_outward_local_box_required')
        side=(axis,a[axis]);side_counts[side]=side_counts.get(side,0)+1
        side_areas[side]=side_areas.get(side,Fraction(0))+abs(normal[axis])
        for x,y in zip(face,face[1:]+face[:1]):
            edges.setdefault(tuple(sorted((x,y))),[]).append(x<y)
    _require(len(side_counts)==6 and all(n==2 for n in side_counts.values())
             and all(len(v)==2 and v[0]!=v[1] for v in edges.values()),'closed_outward_local_box_required')
    for (axis,_),area in side_areas.items():
        other=[k for k in range(3) if k!=axis]
        expected=2*(Fraction(float(high[other[0]]))-Fraction(float(low[other[0]])))*(
                    Fraction(float(high[other[1]]))-Fraction(float(low[other[1]])))
        _require(area==expected,'box_face_coverage_required')
    columns=[[matrix[r][c] for r in range(3)] for c in range(3)]
    lengths=[math.hypot(*v) for v in columns];axes=[_unit(v) for v in columns]
    _require(min(lengths)>0 and max(lengths)-min(lengths)<=1e-6*max(lengths)
             and max(abs(_dot(a,b)) for a,b in combinations(axes,2))<=1e-6
             and _dot(_cross(axes[0],axes[1]),axes[2])>0,'native_rigid_box_required')
    for localv,worldv in zip(local,world):
        predicted=[_dot(matrix[k][:3],localv)+matrix[k][3] for k in range(3)]
        _require(all(abs(a-b)<=REPRESENTATION_ATOL_M*max(1.,abs(a),abs(b))
                     for a,b in zip(predicted,worldv)),'native_world_pose_inconsistent')
    return {'object':obj,'axes':axes,'low':[min(v[k] for v in world) for k in range(3)],
            'high':[max(v[k] for v in world) for k in range(3)]}


def _envelope(value):
    _require(type(value) is dict and set(value)=={'capture','native_scene','capture_confirmation'},'coherent_envelope_required')
    _finite_tree(value)
    capture,confirmation,native=(value[k] for k in ('capture','capture_confirmation','native_scene'))
    _require(type(capture) is dict and type(confirmation) is dict
             and _digest(capture)==_digest(confirmation),'capture_window_changed')
    _require(capture.get('unit')=='m' and capture.get('coordinate_frame')=='world'
             and type(capture.get('revision')) is str and capture['revision'],'capture_provenance_required')
    meshes=capture.get('meshes')
    _require(type(meshes) is list and 2<=len(meshes)<=MAX_SCENE_OBJECTS,'complete_bounded_capture_required')
    byid={}
    for mesh in meshes:
        _require(type(mesh) is dict and type(mesh.get('object_id')) is str and mesh['object_id']
                 and mesh['object_id'] not in byid,'duplicate_or_invalid_capture_identity')
        byid[mesh['object_id']]=mesh
    identity=capture.get('host_identity')
    _require(type(identity) is dict and identity.get('schema_version')=='1.0'
             and type(identity.get('document_epoch')) is str and identity['document_epoch']
             and identity.get('capture_scope')=='complete_scene_meshes'
             and type(identity.get('object_instances')) is dict
             and set(identity['object_instances'])==set(byid)
             and all(type(x) is str and x for x in identity['object_instances'].values())
             and len(set(identity['object_instances'].values()))==len(byid),'complete_host_identity_required')
    _require(type(capture.get('host_execution')) is dict
             and capture['host_execution'].get('supported') is True,'host_execution_not_supported')
    _require(type(native) is dict and set(native)=={'unit','coordinate_frame','revision','objects'}
             and native['unit']=='m' and native['coordinate_frame']=='world'
             and type(native['revision']) is str and native['revision']
             and type(native['objects']) is list and len(native['objects'])==len(meshes),'complete_native_scene_required')
    _require(native['revision']=='native:'+_digest(native['objects']),'native_snapshot_revision_mismatch')
    boxes={}
    for obj in native['objects']:
        box=_box(obj);oid=obj['object_id']
        _require(oid not in boxes and oid in byid,'native_capture_identity_mismatch')
        boxes[oid]=box;mesh=byid[oid]
        _require(mesh.get('name')==obj['name'] and mesh.get('faces')==obj['faces'],
                 'native_capture_topology_mismatch')
        _require(type(mesh.get('vertices')) is list and len(mesh['vertices'])==8
                 and all(_vec(v) for v in mesh['vertices']),'invalid_capture_vertices')
        for hostv,rawv in zip(mesh['vertices'],obj['world_vertices']):
            _require(all(abs(a-b)<=REPRESENTATION_ATOL_M*max(1.,abs(a),abs(b))
                         for a,b in zip(hostv,rawv)),'native_capture_geometry_disagrees')
        # The native world coordinates are binary32, but the engine capture
        # evaluates the same local mesh/matrix in binary64. Check that forward
        # map at its arithmetic scale so the wider cross-representation bound
        # cannot hide a small deformation of the captured engine geometry.
        for hostv,localv in zip(mesh['vertices'],obj['local_vertices']):
            for k in range(3):
                terms=[obj['matrix'][k][j]*localv[j] for j in range(3)]+[obj['matrix'][k][3]]
                predicted=math.fsum(terms)
                roundoff=64*max(math.ulp(float(x)) for x in terms+[predicted,hostv[k]])
                _require(abs(predicted-hostv[k])<=roundoff,'capture_not_native_local_pose_forward_map')
        pivot=mesh.get('pivot_world');axes=mesh.get('local_axes')
        _require(_vec(pivot) and pivot==[obj['matrix'][k][3] for k in range(3)]
                 and type(axes) is list and len(axes)==3 and all(_vec(v) for v in axes)
                 and mesh.get('axes_source')=='host' and mesh.get('axes_confidence')=='explicit',
                 'native_capture_frame_disagrees')
        _require(all(abs(a-b)<=1e-6 for u,v in zip(axes,box['axes']) for a,b in zip(u,v)),
                 'native_capture_frame_disagrees')
    return capture,byid,native,boxes


def _project(vertices,axis):
    values=[math.fsum(a*b for a,b in zip(v,axis)) for v in vertices]
    return min(values),max(values)


def _separated(a,b):
    if any(a['low'][k]-b['high'][k]>SEPARATION_M or b['low'][k]-a['high'][k]>SEPARATION_M for k in range(3)):
        return True
    axes=a['axes']+b['axes']+[_cross(x,y) for x in a['axes'] for y in b['axes']]
    for axis in axes:
        if math.hypot(*axis)<=1e-12:continue
        axis=_unit(axis)
        alo,ahi=_project(a['object']['world_vertices'],axis);blo,bhi=_project(b['object']['world_vertices'],axis)
        if blo-ahi>SEPARATION_M or alo-bhi>SEPARATION_M:return True
    return False


def _measurement(boxes,policy):
    focal,reference=(boxes[k] for k in (policy.focal_id,policy.reference_id))
    normal=reference['axes'][2]
    _require(_dot(normal,focal['axes'][2])>=1-2e-6 and abs(normal[2])>.1,'parallel_support_pair_required')
    gap=(_project(focal['object']['world_vertices'],normal)[0]
         -_project(reference['object']['world_vertices'],normal)[1])
    _require(gap>0,'positive_native_gap_required')
    for axis in reference['axes'][:2]:
        flo,fhi=_project(focal['object']['world_vertices'],axis)
        rlo,rhi=_project(reference['object']['world_vertices'],axis)
        _require(flo-rlo>=SEPARATION_M and rhi-fhi>=SEPARATION_M,'finite_native_support_required')
    _require(all(_separated(a,b) for a,b in combinations(boxes.values(),2)),'native_endpoint_separation_not_proven')
    return gap


def _reject_ambiguity(value):
    if type(value) is dict:
        for key,item in value.items():
            if key in {'rollback_count','rollback_assignments','matrix_assignments'}:
                _require(_number(item) and item==0,'rollback_or_unexpected_assignment')
            if key in {'rolled_back','rollback_performed','execution_uncertain','host_quarantined','quarantined','inflight_operation'}:
                _require(item is False,'rollback_or_unknown_execution')
            if key=='executed':
                _require(type(item) is bool,'unknown_execution_value')
            _reject_ambiguity(item)
    elif type(value) is list:
        for item in value:_reject_ambiguity(item)


def _receipt(receipt,policy,before_revision,current_revision):
    _require(type(receipt) is dict,'complete_receipt_required');_finite_tree(receipt);_reject_ambiguity(receipt)
    _require(policy.expected_engine_build_id is not None,'explicit_engine_build_binding_required')
    runtime=receipt.get('runtime_identity')
    _require(type(runtime) is dict and runtime.get('build_id')==policy.expected_engine_build_id
             and runtime.get('mode')=='live','engine_build_or_mode_changed')
    _require(receipt.get('status') in {'review_required','satisfied'} and receipt.get('executed') is True
             and receipt.get('execution_status')=='executed_verified'
             and receipt.get('replayed') is False and receipt.get('historical_receipt') is False,
             'unconfirmed_or_historical_segment')
    _require(receipt.get('base_revision')==before_revision and receipt.get('end_revision')==current_revision,
             'receipt_revision_mismatch')
    request=receipt.get('request')
    request_fields={'focal_id','reference_id','solver','reference_triangle_index','direction_world',
        'target_clearance_m','clearance_tolerance_m','max_steps','max_step_translation_m',
        'max_total_translation_m','max_duration_s','selection_binding'}
    _require(type(request) is dict and request.get('solver')=='support_plane'
             and set(request)==request_fields
             and request.get('focal_id')==policy.focal_id and request.get('reference_id')==policy.reference_id
             and type(request.get('reference_triangle_index')) is int
             and request['reference_triangle_index']==policy.reference_triangle_index
             and _vec(request.get('direction_world'))
             and request.get('direction_world')==list(policy.direction_world)
             and _number(request.get('target_clearance_m')) and _number(request.get('clearance_tolerance_m'))
             and request.get('target_clearance_m')==policy.target_clearance_m
             and request.get('clearance_tolerance_m')==policy.clearance_tolerance_m,'goal_or_role_changed')
    for field,maximum in (('max_steps',policy.max_steps),('max_step_translation_m',policy.max_step_translation_m),
                          ('max_total_translation_m',policy.max_total_translation_m),
                          ('max_duration_s',policy.max_segment_duration_s)):
        _require(_number(request.get(field)) and 0<request[field]<=maximum,'segment_budget_exceeds_policy')
    _require(type(request['max_steps']) is int,'invalid_segment_step_limit')
    binding=request.get('selection_binding')
    _require(type(binding) is dict and binding.get('scene_revision')==before_revision
             and binding.get('focal_id')==policy.focal_id and binding.get('reference_id')==policy.reference_id,
             'original_selection_binding_required')
    steps=receipt.get('steps')
    _require(type(steps) is list and 1<=len(steps)<=min(policy.max_steps,request['max_steps']),
             'confirmed_steps_required')
    previous=before_revision;step_ids=set();operation_ids=set();motions=[];signed=[]
    for index,step in enumerate(steps):
        _require(type(step) is dict and step.get('state')=='complete'
                 and type(step.get('step_index')) is int and step['step_index']==index,
                 'incomplete_or_unknown_step')
        sid,oid=step.get('step_id'),step.get('operation_id')
        _require(type(sid) is str and sid and sid not in step_ids and type(oid) is str and oid
                 and oid not in operation_ids,'duplicate_or_missing_step_identity')
        step_ids.add(sid);operation_ids.add(oid)
        action,result=step.get('action'),step.get('result')
        _require(type(action) is dict and action.get('focal_id')==policy.focal_id
                 and action.get('reference_id')==policy.reference_id and _vec(action.get('translation'))
                 and action['translation'][:2]==[0,0] and action['translation'][2]!=0
                 and abs(action['translation'][2])<=min(policy.max_step_translation_m,request['max_step_translation_m'])
                 and _vec(action.get('rotation_euler_deg')) and action['rotation_euler_deg']==[0,0,0],
                 'step_motion_outside_policy')
        _require(type(result) is dict and result.get('status')=='verified' and result.get('executed') is True
                 and result.get('verified') is True and result.get('execution_verified') is True,
                 'incomplete_or_unknown_step')
        _require(result.get('goal_evaluation') in {'goal_satisfied','goal_not_satisfied'}
                 and result.get('task_succeeded') is (result['goal_evaluation']=='goal_satisfied'),
                 'step_goal_readback_inconsistent')
        native=result.get('receipt')
        _require(type(native) is dict and native.get('source')=='blender' and native.get('host_execution_verified') is True
                 and native.get('focal_id')==policy.focal_id and native.get('before_revision')==previous
                 and type(native.get('after_revision')) is str and native['after_revision']
                 and result.get('actual_scene_revision')==native['after_revision']
                 and _number(native.get('coordinate_tolerance_m'))
                 and 0<=native['coordinate_tolerance_m']<=policy.measurement_agreement_m,
                 'unbound_host_step_receipt')
        previous=native['after_revision'];motion=step.get('actual_translation_m')
        _require(_number(motion) and 0<motion<=min(policy.max_step_translation_m,request['max_step_translation_m'])
                 and abs(motion-abs(action['translation'][2]))<=policy.measurement_agreement_m,
                 'actual_step_motion_not_verified')
        motions.append(motion);signed.append(math.copysign(motion,action['translation'][2]))
    _require(previous==current_revision,'step_chain_end_revision_mismatch')
    total=math.fsum(motions)
    _require(_number(receipt.get('actual_total_translation_m'))
             and abs(receipt['actual_total_translation_m']-total)<=1e-12
             and total<=min(policy.max_total_translation_m,request['max_total_translation_m']),
             'actual_segment_motion_exceeds_policy')
    _require(all(math.copysign(1.,v)==math.copysign(1.,signed[0]) for v in signed),'mixed_direction_segment')
    if receipt['status']=='review_required':
        _require(receipt.get('reason_codes')==['contact_feature_changed_after_rounded_translation']
                 and receipt.get('task_succeeded') is False and receipt.get('review_required') is True,
                 'review_reason_not_automatically_recoverable')
        _require(policy.max_recoveries>0,'recovery_disabled_by_policy')
    else:
        _require(receipt.get('task_succeeded') is True and receipt.get('reason_codes')==[],
                 'satisfied_receipt_inconsistent')
    return total,math.fsum(signed),len(steps)


def review_continuation(before_scene,current_scene,receipt,policy):
    """Review bracketed public geometry and typed confirmed receipt evidence.

    Whole-goal metering and authorization are intentionally external. Eligibility
    may only request a *new* discovery/preview, never replay a submitted action.
    """
    if type(policy) is not ContinuationPolicy:return _result('stop',['explicit_frozen_policy_required'])
    try:
        before,bm,bnative,bb=_envelope(before_scene)
        current,cm,cnative,cb=_envelope(current_scene)
        _require(set(bm)==set(cm) and policy.focal_id in bm and policy.reference_id in bm,'object_set_or_pair_changed')
        _require(before['host_identity']==current['host_identity'],'host_document_or_object_identity_changed')
        _require({k:v for k,v in before.items() if k not in {'revision','meshes'}}==
                 {k:v for k,v in current.items() if k not in {'revision','meshes'}},'capture_provenance_or_capability_changed')
        total,net,count=_receipt(receipt,policy,before['revision'],current['revision'])
        _require(receipt['request']['selection_binding'].get('scene_fingerprint')==_capture_fingerprint(before),
                 'original_selection_fingerprint_mismatch')
        for oid,old in bm.items():
            new=cm[oid];bo=bb[oid]['object'];co=cb[oid]['object']
            if oid!=policy.focal_id:
                _require(old==new and bo==co,'nonfocal_object_changed')
                continue
            _require({k:v for k,v in old.items() if k not in {'vertices','pivot_world'}}==
                     {k:v for k,v in new.items() if k not in {'vertices','pivot_world'}},'focal_capture_metadata_changed')
            _require({k:v for k,v in bo.items() if k not in {'world_vertices','matrix'}}==
                     {k:v for k,v in co.items() if k not in {'world_vertices','matrix'}},'focal_local_mesh_or_metadata_changed')
            _require(all(bo['matrix'][r][c]==co['matrix'][r][c] for r in range(4) for c in range(4)
                         if c!=3 or r==3),'focal_nontranslation_pose_changed')
            _require(all(bo['matrix'][k][3]==co['matrix'][k][3] for k in (0,1))
                     and old['pivot_world'][:2]==new['pivot_world'][:2]
                     and all(a[:2]==b[:2] for a,b in zip(old['vertices'],new['vertices'])),'focal_world_xy_changed')
            _require(abs((co['matrix'][2][3]-bo['matrix'][2][3])-net)<=1e-12,'native_motion_does_not_match_confirmed_steps')
        oldgap=_measurement(bb,policy);gap=_measurement(cb,policy)
        residual=receipt.get('residual')
        _require(type(residual) is dict and residual.get('measurement_valid') is True
                 and residual.get('scene_revision')==current['revision']
                 and residual.get('scene_fingerprint')==_capture_fingerprint(current)
                 and residual.get('unit')=='m' and residual.get('coordinate_frame')=='world'
                 and residual.get('focal_id')==policy.focal_id and residual.get('reference_id')==policy.reference_id
                 and _number(residual.get('current_clearance_m'))
                 and abs(residual['current_clearance_m']-gap)<=policy.measurement_agreement_m,
                 'fresh_native_measurement_disagrees')
        _require(_number(residual.get('signed_error_m')) and _number(residual.get('absolute_error_m'))
                 and abs(residual['signed_error_m']-(residual['current_clearance_m']-policy.target_clearance_m))<=1e-12
                 and abs(residual['absolute_error_m']-abs(residual['signed_error_m']))<=1e-12,
                 'residual_error_fields_inconsistent')
        if receipt['status']=='review_required':
            _require(residual.get('status')=='feature_changed' and residual.get('goal_satisfied') is False
                     and residual.get('reason_codes')==receipt['reason_codes'] and residual.get('candidate') is None,
                     'feature_stop_residual_inconsistent')
        else:
            _require(residual.get('status')=='goal_satisfied' and residual.get('goal_satisfied') is True
                     and residual.get('reason_codes')==[],'goal_residual_inconsistent')
        _require(abs(gap-policy.target_clearance_m)<abs(oldgap-policy.target_clearance_m),
                 'native_residual_not_strictly_improved')
        facts={'before_capture_sha256':_digest(before),'current_capture_sha256':_digest(current),
               'before_native_sha256':_digest(bnative),'current_native_sha256':_digest(cnative),
               'before_clearance_m':oldgap,'current_clearance_m':gap,'confirmed_segment_steps':count,
               'confirmed_segment_translation_m':total,'original_reference_triangle_index':policy.reference_triangle_index,
               'representation_atol_m':REPRESENTATION_ATOL_M,'whole_goal_budget_checked':False,
               'engine_build_binding_checked':True,
               'permission_checked':False,'bracketed_capture_is_atomic':False,'swept_path_certified':False}
        if receipt['status']=='satisfied':
            _require(abs(gap-policy.target_clearance_m)<=policy.clearance_tolerance_m,'native_goal_not_satisfied')
            return _result('completed',**facts)
        return _result('eligible_for_fresh_preview',**facts)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError,ZeroDivisionError) as exc:
        code=str(exc) if type(exc) is ValueError else 'malformed_continuation_evidence'
        return _result('stop',[code[:160]])


def inspect_current_clearance(envelope, policy):
    """Read-only native check, including an already-satisfied zero-write goal.

    Unlike continuation this does not require a preceding executed segment or
    improvement. It never issues permission or changes any evidence/budget.
    """
    if type(policy) is not ContinuationPolicy:
        return _result('stop',['explicit_frozen_policy_required'])
    try:
        capture,meshes,native,boxes=_envelope(envelope)
        _require(policy.focal_id in meshes and policy.reference_id in meshes,'object_set_or_pair_changed')
        gap=_measurement(boxes,policy)
        return _result('already_satisfied' if abs(gap-policy.target_clearance_m)<=policy.clearance_tolerance_m
                       else 'not_satisfied',current_clearance_m=gap,
            capture_revision=capture['revision'],capture_fingerprint=_capture_fingerprint(capture),
            capture_sha256=_digest(capture),native_sha256=_digest(native),
            permission_checked=False,whole_goal_budget_checked=False,swept_path_certified=False)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError,ZeroDivisionError) as exc:
        code=str(exc) if type(exc) is ValueError else 'malformed_current_evidence'
        return _result('stop',[code[:160]])


__all__=['ContinuationPolicy','review_continuation','inspect_current_clearance','CONTRACT_REVISION']
