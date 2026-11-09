"""The eight cases are fixed before the product solver is evaluated.

Reuse the existing seed/asset families and original IDs, weights and rest roll.
No supervision labels, reference vertices or expected answers enter patch/task.
"""
from __future__ import annotations

from copy import deepcopy
import math

from verification.m6_arm_expert_001.synthetic import _asset
from verification.arm_twist_correction_preview_001.oracle import chain_poses,known_objective,skin_vertices

CASE_DEFINITIONS=(
    ('round_120','round',120.,120.,None,'candidate',0.),
    ('round_minus150','round',-150.,-150.,None,'candidate',0.),
    ('elliptic_120','elliptic',120.,120.,None,'candidate',0.),
    ('elliptic_minus150','elliptic',-150.,-150.,None,'candidate',0.),
    ('balanced_120','round',120.,60.,None,'no_op',0.),
    ('small_twist_30','round',30.,30.,None,'no_op',0.),
    ('unreachable_120','round',120.,120.,(110.,120.),'unreachable',0.),
    ('noncoaxial','round',120.,120.,None,'not_applicable',10.),
)


def make_cases():
    assets={shape:_asset(1729,'train',shape,'three_even','linear',0) for shape in ('round','elliptic')}
    output=[]
    for case_id,shape,theta,u,interval,status,swing in CASE_DEFINITIONS:
        asset=assets[shape];patch=deepcopy(asset['packet'])
        poses=chain_poses(asset['rests'],u,theta,swing_deg=swing)
        patch['bone_chain']=[{'name':'arm_'+str(index),'parent':None if index==0 else 'arm_'+str(index-1),
            'rest_matrix':deepcopy(rest),'pose_matrix':pose} for index,(rest,pose) in enumerate(zip(asset['rests'],poses))]
        patch['current_vertices']=skin_vertices(patch)
        lower,upper=interval if interval is not None else (min(0.,theta),max(0.,theta))
        protected=[vertex_id for vertex_id,weights in zip(patch['vertex_ids'],patch['weights'])
                   if weights==[1.,0.,0.] or weights==[0.,0.,1.]]
        task={'schema':'arm-axial-redistribution-task-v1',
            'fixed_end_pose_matrices':[deepcopy(poses[0]),deepcopy(poses[-1])],
            'u_interval_deg':[lower,upper],'max_section_area_loss':.4,
            'protected_vertex_ids':protected,'angle_tolerance_deg':.001,
            'position_tolerance_m':1e-9,'area_tolerance':1e-8}
        best=min(upper,max(lower,theta/2))
        expected=u if status=='no_op' else best
        output.append({'case_id':case_id,'patch':patch,'task':task,'expected_status':status,
            'theta_deg':theta,'current_u_deg':u,'expected_u_deg':None if swing else expected,
            'expected_before_j':None if swing else known_objective(theta,u),
            'expected_after_j':None if swing else known_objective(theta,expected),
            'asset_id':asset['asset_id'],'shape':shape,
            'fixture':{'world_matrix':deepcopy(asset['world']),'local_vertices':deepcopy(asset['local']),
                       'rest_matrices':deepcopy(asset['rests'])}})
    assert len(output)==8
    return output


def joint_weight_proof(patch):
    """Both exact joint-center rings must contain the original 50/50 rows."""
    expected=((8,[.5,.5,0.]),(16,[0.,.5,.5]))
    records=[]
    for ring,row in expected:
        actual=[patch['weights'][index] for index in patch['sections'][ring]]
        assert len(actual)==16 and all(all(math.isclose(a,b,rel_tol=0.,abs_tol=1e-14)
            for a,b in zip(weights,row)) for weights in actual)
        records.append({'section_index':ring,'weights':row,'vertices':len(actual)})
    return records
