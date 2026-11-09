"""Pure three-bone axial redistribution preview, without any rig setter.

The geometric solution preserves both end poses. Its finite domain requires
coaxial rigid bones and uniform adjacent weights on convex ordered sections,
including a 50/50 section at each joint. It does not infer repair intent,
source provenance, constraints, bone tails, animation winding or volume.
"""
import math
import numpy as np

from . import rig_pose as r
from .arm_twist_expert import _parse_patch

TASK_SCHEMA='arm-axial-redistribution-task-v1'
SCHEMA='arm-axial-redistribution-preview-v1'
WEIGHT_ATOL=1e-10


class _DomainError(ValueError):
    pass


def _need(value,reason):
    if not value:raise _DomainError(reason)


def _ry(angle):
    angle=math.radians(angle);c=math.cos(angle);s=math.sin(angle)
    return [[c,0.,s,0.],[0.,1.,0.,0.],[-s,0.,c,0.],[0.,0.,0.,1.]]


def _points(matrix,vertices):
    matrix=np.asarray(matrix,dtype=float)
    return vertices@matrix[:3,:3].T+matrix[:3,3]


def _lbs(rest,weights,rests,poses):
    output=np.zeros_like(rest)
    for index,(original,pose) in enumerate(zip(rests,poses)):
        output+=weights[:,index,None]*_points(r.multiply(pose,r.inverse(original)),rest)
    return output


def _areas(points,sections):
    areas=[]
    for indices in sections:
        ring=points[indices];ring=ring-ring.mean(axis=0)
        areas.append(float(np.linalg.norm(np.cross(ring,np.roll(ring,-1,axis=0)).sum(axis=0))*.5))
    return np.asarray(areas)


def _objective(points,sections,areas0):
    ratios=_areas(points,sections)/areas0
    _need(np.isfinite(ratios).all(),'unreliable_section_area')
    return {'max_section_area_loss':max(0.,1.-float(ratios.min())),
            'section_area_ratios':ratios.tolist()}


def _task(task):
    fields={'schema','fixed_end_pose_matrices','u_interval_deg','max_section_area_loss',
            'protected_vertex_ids','angle_tolerance_deg','position_tolerance_m','area_tolerance'}
    _need(type(task) is dict and set(task)==fields and task['schema']==TASK_SCHEMA,'task_schema_or_fields')
    for field,upper in (('angle_tolerance_deg',.001),('position_tolerance_m',1e-5),('area_tolerance',1e-6)):
        _need(r.finite(task[field]) and 0<task[field]<=upper,'task_tolerance:'+field)
    interval=task['u_interval_deg']
    _need(type(interval) is list and len(interval)==2 and all(r.finite(v) for v in interval)
          and interval[0]<=interval[1],'u_interval')
    target=task['max_section_area_loss']
    _need(r.finite(target) and 0<=target<1,'section_area_target')
    ends=task['fixed_end_pose_matrices']
    _need(type(ends) is list and len(ends)==2,'fixed_end_targets')
    for matrix in ends:
        r.matrix(matrix);_need(r.rigid(matrix),'fixed_end_targets')
    ids=task['protected_vertex_ids']
    _need(type(ids) is list and all(type(v) is int and v>=0 for v in ids)
          and len(ids)==len(set(ids)),'protected_vertex_ids')
    return interval,target,task['angle_tolerance_deg'],task['position_tolerance_m'],task['area_tolerance']


def _domain(patch,task,work):
    interval,target,angle_tol,position_tol,area_tol=_task(task)
    rest,ids,rests,weights,sections,current,poses=_parse_patch(patch,dynamic=True)
    _need(len(rests)==3,'three_bones_required')
    for target_pose,pose in zip(task['fixed_end_pose_matrices'],(poses[0],poses[2])):
        delta=r.multiply(r.inverse(pose),target_pose)
        _need(r.angles(delta)['rotation_deg']<=angle_tol and
              np.linalg.norm(np.asarray(target_pose)[:3,3]-np.asarray(pose)[:3,3])<=position_tol,
              'fixed_end_target_mismatch')
    first_rest_inv=r.inverse(rests[0]);first_pose_inv=r.inverse(poses[0])
    heads=[];angles=[]
    rotation_tol=math.radians(angle_tol)
    for rest_matrix,pose in zip(rests,poses):
        local_rest=r.multiply(first_rest_inv,rest_matrix)
        _need(np.linalg.norm(np.asarray(local_rest)[[0,2],3])<=position_tol and
              np.linalg.norm(np.asarray(local_rest)[:3,1]-[0.,1.,0.])<=rotation_tol,
              'rest_bones_not_coaxial')
        heads.append(local_rest[1][3])
        # Remove first-bone motion and each bone's rest roll before taking u.
        axial=r.multiply(r.multiply(first_pose_inv,pose),r.inverse(local_rest))
        fact=r.angles(axial);angle=fact['twist_deg']
        _need(angle is not None and fact['swing_deg']<=angle_tol,'non_axial_or_ambiguous_pose')
        expected=np.asarray(_ry(angle));actual=np.asarray(axial)
        _need(np.linalg.norm(actual[:3,3])<=position_tol and
              np.max(np.abs(actual[:3,:3]-expected[:3,:3]))<=rotation_tol,
              'pose_axis_line_changed')
        angles.append(angle)
    _need(heads[1]-heads[0]>position_tol and heads[2]-heads[1]>position_tol,'ordered_distinct_bone_heads')
    u,theta=angles[1:];lower,upper=min(0.,theta),max(0.,theta)
    _need(abs(theta)<180-angle_tol and lower-angle_tol<=u<=upper+angle_tol,'axial_angle_domain')
    _need(lower-angle_tol<=interval[0]<=interval[1]<=upper+angle_tol,'interval_outside_axial_domain')
    _need(np.max(np.abs(weights.sum(axis=1)-1.))<=WEIGHT_ATOL,'weights_not_unit_precision')
    _need(not np.any((weights[:,0]>WEIGHT_ATOL)&(weights[:,2]>WEIGHT_ATOL)),
          'non_adjacent_weights')
    local=_points(first_rest_inv,rest);heights=[];halves=[False,False]
    for section in sections:
        ring=local[section];center=ring.mean(axis=0);heights.append(float(center[1]))
        _need(np.linalg.norm(center[[0,2]])<=position_tol and
              np.max(np.abs(ring[:,1]-center[1]))<=position_tol,'section_not_transverse_centered')
        row=weights[section[0]]
        _need(np.max(np.abs(weights[section]-row))<=WEIGHT_ATOL,'nonuniform_section_weights')
        polygon=ring[:,[0,2]];edge=np.roll(polygon,-1,axis=0)-polygon
        _need(np.min(np.linalg.norm(edge,axis=1))>position_tol,'degenerate_section_edge')
        # Every point on the same side of every edge excludes star windings.
        difference=polygon[None,:,:]-polygon[:,None,:]
        side=edge[:,None,0]*difference[:,:,1]-edge[:,None,1]*difference[:,:,0]
        guard=position_tol*float(np.max(np.linalg.norm(edge,axis=1)))
        _need(np.all(side>=-guard) or np.all(side<=guard),'section_not_convex_ordered')
        for joint,pattern in enumerate(([.5,.5,0.],[0.,.5,.5])):
            if np.max(np.abs(row-pattern))<=WEIGHT_ATOL and abs(center[1]-heads[joint+1])<=position_tol:
                halves[joint]=True
    _need(all(halves),'both_joint_half_weight_sections_required')
    _need(all(b-a>position_tol for a,b in zip(heights,heights[1:])) and
          abs(heights[0])<=position_tol and heights[-1]>heads[-1]+position_tol,'ordered_axial_sections')
    work['rest_area_batches']+=1
    areas0=_areas(rest,sections)
    scale=max(float(np.ptp(local,axis=0).max()),position_tol)
    _need(np.isfinite(areas0).all() and np.min(areas0)>max(position_tol**2,scale**2*1e-12),
          'unreliable_rest_section_area')
    pure=(weights[:,0]>=1-WEIGHT_ATOL)|(weights[:,2]>=1-WEIGHT_ATOL)
    protected={ids[index] for index in np.flatnonzero(pure)}
    _need(protected and set(task['protected_vertex_ids'])==protected,'protect_all_and_only_pure_end_vertices')
    work['lbs_evaluations']+=1
    predicted=_lbs(rest,weights,rests,poses)
    residual=float(np.linalg.norm(predicted-current,axis=1).max())
    _need(residual<=position_tol,'current_not_declared_lbs')
    centers=np.array([current[s].mean(axis=0) for s in sections])
    reference=_points(poses[0],np.column_stack((np.zeros(len(heights)),heights,np.zeros(len(heights)))))
    _need(np.max(np.linalg.norm(centers-reference,axis=1))<=position_tol,'current_centerline_changed')
    return dict(rest=rest,ids=ids,rests=rests,poses=poses,weights=weights,sections=sections,current=current,
                areas0=areas0,pure=pure,u=u,theta=theta,interval=interval,target=target,
                area_tol=area_tol,position_tol=position_tol,lbs_residual=residual)


def preview_axial_redistribution(patch,task):
    """Return a geometric preview; invalid/unsupported input has no candidate.

    Angles are extra twist relative to rest, modulo a single turn. The task's
    allowed interval must lie between zero and theta; the analytic minimizer
    is clamped theta/2 after both 50/50 joint sections have been established.
    No model, execution authorization, bone edit or source read occurs here.
    """
    report={'schema':SCHEMA,'status':'not_applicable','reason':None,'candidate':None,
            'candidate_source':'bounded_geometric_solver','objective':None,'preservation':None,
            'work':{'lbs_evaluations':0,'rest_area_batches':0,'current_area_batches':0,
                    'candidate_area_batches':0,'model_calls':0},
            'not_checked':['source_provenance','rig_constraints','actual_bone_tails','animation_winding',
                           'outside_patch_objects','volume','damage_or_artistic_intent']}
    try:
        work=report['work'];d=_domain(patch,task,work)
        work['current_area_batches']+=1
        before=_objective(d['current'],d['sections'],d['areas0'])
        optimal=min(d['interval'][1],max(d['interval'][0],d['theta']/2))
        report.update(u_current_deg=d['u'],theta_deg=d['theta'],optimal_u_deg=optimal,
                      objective={'before':before,'after':None,'target_max_section_area_loss':d['target']},
                      preservation={'max_fixed_end_matrix_delta':0.,'max_centerline_delta_m':0.,
                                    'max_protected_vertex_delta_m':0.,'input_lbs_residual_m':d['lbs_residual']})
        if before['max_section_area_loss']<=d['target']+d['area_tol']:
            report['status']='no_op';report['reason']='area_target_already_met'
            report['objective']['after']=dict(before);return report
        poses=[[row[:] for row in matrix] for matrix in d['poses']]
        poses[1]=r.multiply(r.multiply(d['poses'][0],_ry(optimal)),
                            r.multiply(r.inverse(d['rests'][0]),d['rests'][1]))
        work['lbs_evaluations']+=1
        after_points=_lbs(d['rest'],d['weights'],d['rests'],poses)
        work['candidate_area_batches']+=1
        after=_objective(after_points,d['sections'],d['areas0'])
        before_centers=np.array([d['current'][s].mean(axis=0) for s in d['sections']])
        after_centers=np.array([after_points[s].mean(axis=0) for s in d['sections']])
        head_delta=max(float(np.linalg.norm(np.asarray(a)[:3,3]-np.asarray(b)[:3,3])) for a,b in zip(d['poses'],poses))
        axis_delta=max(float(np.linalg.norm(np.asarray(a)[:3,1]-np.asarray(b)[:3,1])) for a,b in zip(d['poses'],poses))
        center_delta=max(head_delta,float(np.linalg.norm(after_centers-before_centers,axis=1).max()))
        protected_delta=float(np.linalg.norm(after_points[d['pure']]-d['current'][d['pure']],axis=1).max())
        _need(center_delta<=d['position_tol'] and protected_delta<=d['position_tol'] and
              axis_delta<=math.radians(task['angle_tolerance_deg']),'candidate_preservation_failed')
        report['objective']['after']=after
        report['preservation'].update(max_centerline_delta_m=center_delta,
                                      max_protected_vertex_delta_m=protected_delta,
                                      max_bone_axis_vector_delta=axis_delta)
        if after['max_section_area_loss']>d['target']+d['area_tol']:
            report.update(status='unreachable',reason='best_allowed_u_exceeds_area_target',best_feasible_u_deg=optimal)
            return report
        basis=[r.multiply(r.inverse(d['rests'][0]),poses[0])]
        for i in (1,2):
            relative=r.multiply(r.inverse(d['rests'][i-1]),d['rests'][i])
            basis.append(r.multiply(r.inverse(relative),r.multiply(r.inverse(poses[i-1]),poses[i])))
        report.update(status='candidate',reason='area_target_met_with_fixed_end_poses',candidate={
            'u_deg':optimal,'pose_matrices':poses,'local_basis_matrices':basis,
            'bone_changes':[{'name':patch['bone_chain'][i]['name'],'basis_matrix':basis[i]} for i in (1,2)],
            'current_vertices':after_points.tolist()})
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
        report.update(status='not_applicable',reason=str(exc),candidate=None)
    return report
