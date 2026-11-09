"""Small deterministic arm-tube dataset with asset-family-held-out splits.

Only ``case['packet']`` is a product/model input. Labels, reference vertices and
metadata are supervision, never feature inputs. A normal label means this
constructed pose is permitted for the twist-collapse task; it is not a claim
about anatomy, injury, all geometric changes or full enclosed-mesh volume.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import math
import random

from human_eye_plugin.rig_pose import inverse, multiply, point


SPLIT_FAMILIES = {
    'train': dict(shape=('round', 'elliptic'), skeleton=('two_even', 'three_even'),
                  weight=('linear', 'smoothstep')),
    'validation': dict(shape=('taper',), skeleton=('two_offset',), weight=('cosine',)),
    'test': dict(shape=('hourglass', 'ripple'), skeleton=('three_offset',),
                 weight=('smootherstep',)),
}
JOINTS = {'two_even': (0.5,), 'three_even': (1/3, 2/3),
          'two_offset': (0.43,), 'three_offset': (0.29, 0.73)}
RINGS = 25
SIDES = 16


def _translation(y=0., x=0., z=0.):
    return [[1., 0., 0., x], [0., 1., 0., y], [0., 0., 1., z], [0., 0., 0., 1.]]


def _rotation(axis, degrees):
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    matrix=_translation()
    a,b=((1,2) if axis=='x' else (2,0) if axis=='y' else (0,1))
    matrix[a][a]=matrix[b][b]=c;matrix[a][b]=-s;matrix[b][a]=s
    return matrix


def _gradient(value, family):
    value=min(1.,max(0.,value))
    if family=='linear':return value
    if family=='smoothstep':return value*value*(3-2*value)
    if family=='cosine':return (1-math.cos(math.pi*value))/2
    if family=='smootherstep':return value**3*(value*(value*6-15)+10)
    raise ValueError('unknown_weight_family')


def _weights(t, joints, width, family):
    for child,joint in enumerate(joints,1):
        if joint-width/2<=t<=joint+width/2:
            alpha=_gradient((t-joint)/width+0.5,family)
            row=[0.]*(len(joints)+1);row[child-1]=1-alpha;row[child]=alpha
            return row
    row=[0.]*(len(joints)+1)
    row[sum(t>joint for joint in joints)]=1.
    return row


def _profile(t, family):
    if family=='round':return 1.,1.
    if family=='elliptic':return 1.25,0.8
    if family=='taper':
        factor=1.12-0.24*t
        return factor*1.08,factor/1.08
    if family=='hourglass':
        factor=1-0.23*math.exp(-((t-0.5)/0.24)**2)
        return factor*1.12,factor/1.12
    if family=='ripple':
        factor=1+0.14*math.sin(2*math.pi*t+0.2)
        return factor/1.09,factor*1.09
    raise ValueError('unknown_shape_family')


def _asset(seed, split, shape, skeleton, weight, variant):
    asset_id='/'.join((split,shape,skeleton,weight,str(variant)))
    digest=hashlib.sha256((str(seed)+'/'+asset_id).encode()).digest()
    rng=random.Random(int.from_bytes(digest[:8],'big'))
    length=0.75+0.3*rng.random();radius=0.065+0.035*rng.random()
    width=0.18+0.04*rng.random();joints=JOINTS[skeleton]
    world=multiply(_translation(x=rng.uniform(-.4,.4),y=rng.uniform(-.3,.3),z=rng.uniform(-.4,.4)),
        multiply(_rotation('z',rng.uniform(-35,35)),
                 multiply(_rotation('x',rng.uniform(-40,40)),_rotation('y',rng.uniform(-45,45)))))
    local=[];sections=[];all_weights=[]
    for ring in range(RINGS):
        t=ring/(RINGS-1);rx,rz=_profile(t,shape);section=[]
        row=_weights(t,joints,width,weight)
        for side in range(SIDES):
            phi=2*math.pi*side/SIDES
            section.append(len(local))
            local.append([radius*rx*math.cos(phi),length*t,radius*rz*math.sin(phi)])
            all_weights.append(row[:])
        sections.append(section)
    local.extend([[0.,0.,0.],[0.,length,0.]])
    all_weights.extend([_weights(0.,joints,width,weight),_weights(1.,joints,width,weight)])
    triangles=[]
    for ring in range(RINGS-1):
        for side in range(SIDES):
            next_side=(side+1)%SIDES
            a=ring*SIDES+side;b=(ring+1)*SIDES+side
            c=(ring+1)*SIDES+next_side;d=ring*SIDES+next_side
            triangles.extend([[a,b,c],[a,c,d]])
    for side in range(SIDES):
        next_side=(side+1)%SIDES
        triangles.append([RINGS*SIDES,side,next_side])
        triangles.append([RINGS*SIDES+1,(RINGS-1)*SIDES+next_side,(RINGS-1)*SIDES+side])
    rests=[]
    for index,t in enumerate((0.,)+joints):
        roll=(-12+24*rng.random())+index*7
        rests.append(multiply(world,multiply(_translation(y=length*t),_rotation('y',roll))))
    offset=1000+(int.from_bytes(digest[8:12],'big')%10000)*10
    packet=dict(schema='arm-twist-patch-v1',unit='m',
        rest_vertices=[point(world,p) for p in local],current_vertices=[],triangles=triangles,
        weights=all_weights,bone_chain=[],sections=sections,
        vertex_ids=[offset+3*i for i in range(len(local))])
    return dict(asset_id=asset_id,packet=packet,local=local,world=world,rests=rests,
                shape=shape,skeleton=skeleton,weight=weight,joints=joints)


def _case(asset, family, angle, joint, *, axis='y', preserve=False):
    packet=copy.deepcopy(asset['packet']);rests=asset['rests'];poses=[]
    for index,rest in enumerate(rests):
        relative=rest if index==0 else multiply(inverse(rests[index-1]),rest)
        basis=_rotation(axis,angle) if index==joint else _translation()
        poses.append(multiply(relative,basis) if index==0 else multiply(poses[index-1],multiply(relative,basis)))
    bones=[dict(name='arm_'+str(index),parent=None if index==0 else 'arm_'+str(index-1),
                rest_matrix=copy.deepcopy(rest),pose_matrix=pose)
           for index,(rest,pose) in enumerate(zip(rests,poses))]
    skin=[multiply(pose,inverse(rest)) for rest,pose in zip(rests,poses)]
    current=[];reference=[]
    for rest,local,weights in zip(packet['rest_vertices'],asset['local'],packet['weights']):
        transformed=[point(matrix,rest) for matrix in skin]
        lbs=[math.fsum(w*p[k] for w,p in zip(weights,transformed)) for k in range(3)]
        if axis=='y':
            # Independent continuous axial SO(2) reference. Each ordered ring
            # is rigidly rotated, hence its polygon area is preserved. This
            # does not certify volume of the discretized between-ring mesh.
            alpha=math.fsum(weights[joint:])
            ideal=point(asset['world'],point(_rotation('y',angle*alpha),local))
        else:ideal=lbs[:]
        reference.append(ideal);current.append(ideal[:] if preserve else lbs)
    abnormal=family=='anomalous_twist'
    labels=[]
    for section in packet['sections']:
        weights=packet['weights'][section[0]];alpha=math.fsum(weights[joint:])
        # Analytic area determinant of (1-alpha)I + alpha R(theta), from the
        # construction/reference. Never calls input-feature or area code.
        severity=4*alpha*(1-alpha)*math.sin(math.radians(angle)/2)**2 if abnormal else 0.
        labels.append(min(1.,max(0.,severity)))
    packet['current_vertices']=current;packet['bone_chain']=bones
    pair_id=asset['asset_id']+'/joint'+str(joint)+'/angle'+str(angle)
    metadata=dict(asset_id=asset['asset_id'],split=asset['asset_id'].split('/',1)[0],
        shape_family=asset['shape'],skeleton_family=asset['skeleton'],weight_family=asset['weight'],
        pose_family=family,angle_deg=angle,joint_index=joint,pair_id=pair_id,
        case_id=pair_id+'/'+family,construction='same-index closed tube with gradual adjacent-bone weights',
        deformation='analytic_section_rotation' if preserve else 'LBS_point_pose_times_inverse_rest',
        label_scope='Constructed abnormal axial-twist cross-section loss only; ordinary bend/small twist permitted. Not injury or general deformation damage.',
        reference_scope=('Ordered transverse section area preserved under axial rotation; no full discretized-mesh volume claim.'
            if axis=='y' else 'Nominal LBS bending reference; zero twist-collapse label does not assert unchanged section area.'),
        fault_section_indices=[i for i,value in enumerate(labels) if value>0],
        supervision_only_fields=['label_severity','reference_vertices','metadata'])
    return dict(packet=packet,label_severity=labels,reference_vertices=reference,metadata=metadata)


def generate_dataset(seed=1729, split=None, asset_variants=1):
    """Return one fixed, small dataset; every pose of an asset stays together.

    Defaults: train 8 assets/56 cases, validation 1/7, test 2/14; 402 vertices,
    25 ordered sections and 800 closed oriented triangles per local patch.
    Shape, skeleton and weight-family marginals are disjoint across splits.
    """
    if type(seed) is not int or type(asset_variants) is not int or asset_variants<1:
        raise ValueError('integer_seed_and_positive_asset_variants_required')
    if split is not None and split not in SPLIT_FAMILIES:raise ValueError('unknown_dataset_split')
    cases=[]
    for split_name,families in SPLIT_FAMILIES.items():
        if split is not None and split!=split_name:continue
        for shape,skeleton,weight in itertools.product(families['shape'],families['skeleton'],families['weight']):
            for variant in range(asset_variants):
                asset=_asset(seed,split_name,shape,skeleton,weight,variant);last=len(asset['joints'])
                cases.extend([_case(asset,'normal_bend',50.,1,axis='z'),
                    _case(asset,'normal_bend',-35.,last,axis='z'),
                    _case(asset,'legal_twist',30.,1)])
                for angle,joint in ((120.,1),(-150.,last)):
                    cases.append(_case(asset,'anomalous_twist',angle,joint))
                    cases.append(_case(asset,'same_angle_preserved',angle,joint,preserve=True))
    return cases
