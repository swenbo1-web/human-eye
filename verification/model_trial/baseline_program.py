"""Public-data mathematical witness for the finite box trial family.

This source is an engineering adequacy check, not a hidden answer supplied to
formal models. It runs through the same restricted mathematical interpreter as
any model-written program. It imports no engine or private fixture/oracle data.
Pair topology is checked; unrelated meshes are conservative bounding obstacles.
The separate fixture oracle establishes the whole scene's supported domain.
"""
from __future__ import annotations

import math


_BODY = r'''
def dot(a,b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def sub(a,b):
    return [a[0]-b[0],a[1]-b[1],a[2]-b[2]]

def cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def unit(a):
    length=math.sqrt(dot(a,a))
    if length <= 0:
        return None
    return [a[0]/length,a[1]/length,a[2]/length]

def bounds(vertices):
    return [[min(v[k] for v in vertices),max(v[k] for v in vertices)] for k in range(3)]

def box_domain(obj):
    vs=obj['local_vertices']
    faces=obj['faces']
    if len(vs)!=8 or len(faces)!=12 or len(obj['world_vertices'])!=8:
        return False
    bb=bounds(vs)
    if any(bb[k][1]<=bb[k][0] for k in range(3)):
        return False
    corners={}
    for v in vs:
        key=0
        for k in range(3):
            if v[k]!=bb[k][0] and v[k]!=bb[k][1]:
                return False
            if v[k]==bb[k][1]:
                key+=2**k
        if key in corners:
            return False
        corners[key]=True
    center=[(bb[k][0]+bb[k][1])/2 for k in range(3)]
    edges={}
    used={}
    triangles={}
    sides=[0,0,0,0,0,0]
    for face in faces:
        if len(face)!=3:
            return False
        f=sorted(face)
        if f[0]<0 or f[2]>=8 or f[0]==f[1] or f[1]==f[2]:
            return False
        key=f[0]*64+f[1]*8+f[2]
        if key in triangles:
            return False
        triangles[key]=True
        a,b,c=[vs[i] for i in face]
        fn=cross(sub(b,a),sub(c,a))
        if dot(fn,sub(a,center))<=0:
            return False
        side=-1
        for k in range(3):
            for end in range(2):
                if a[k]==b[k] and b[k]==c[k] and a[k]==bb[k][end]:
                    if side!=-1:
                        return False
                    side=2*k+end
        if side<0:
            return False
        sides[side]+=1
        for j in range(3):
            left,right=face[j],face[(j+1)%3]
            used[left]=True
            edge=left*8+right
            if edge in edges:
                return False
            edges[edge]=True
    if len(used)!=8 or any(count!=2 for count in sides):
        return False
    for edge in edges:
        left=edge//8
        right=edge%8
        if right*8+left not in edges:
            return False
    matrix=obj['matrix']
    if len(matrix)!=4 or any(len(row)!=4 for row in matrix) or matrix[3]!=[0,0,0,1]:
        return False
    axes=[unit([matrix[r][k] for r in range(3)]) for k in range(3)]
    if any(axis is None for axis in axes):
        return False
    for i in range(3):
        for j in range(i):
            if abs(dot(axes[i],axes[j]))>2e-6:
                return False
    if dot(cross(axes[0],axes[1]),axes[2])<1-4e-6:
        return False
    for local,world in zip(vs,obj['world_vertices']):
        predicted=[dot(matrix[k][:3],local)+matrix[k][3] for k in range(3)]
        if any(abs(predicted[k]-world[k])>4e-7*max(1,abs(predicted[k]),abs(world[k])) for k in range(3)):
            return False
    return True

def projections(vertices,axis):
    values=[dot(v,axis) for v in vertices]
    return [min(values),max(values)]

def aabb_separated(aa,bb):
    for k in range(3):
        if bb[k][0]-aa[k][1]>1e-7 or aa[k][0]-bb[k][1]>1e-7:
            return True
    return False

def endpoint_separated(av,bv,am,bm):
    aa=[unit([am[r][k] for r in range(3)]) for k in range(3)]
    ba=[unit([bm[r][k] for r in range(3)]) for k in range(3)]
    if any(axis is None for axis in aa+ba):
        return False
    axes=aa+ba+[cross(a,b) for a in aa for b in ba]
    for axis in axes:
        length=math.sqrt(dot(axis,axis))
        if length>1e-10:
            axis=[value/length for value in axis]
            ap=projections(av,axis)
            bp=projections(bv,axis)
            if bp[0]-ap[1]>1e-7 or ap[0]-bp[1]>1e-7:
                return True
    return False

def finite_foot(vertices,base,u,v):
    for axis in [u,v]:
        foot=projections(vertices,axis)
        limit=projections(base['world_vertices'],axis)
        if foot[0]<limit[0]+1e-6 or foot[1]>limit[1]-1e-6:
            return False
    return True

def solve(scene,mode,target,cap):
    if scene['unit']!='m' or scene['coordinate_frame']!='world':
        return {'status':'unsupported','reason':'world_metre_snapshot_required'}
    found_a=[o for o in scene['objects'] if o['name']=='BluePart']
    found_b=[o for o in scene['objects'] if o['name']=='GreyBase']
    if len(found_a)!=1 or len(found_b)!=1:
        return {'status':'unsupported','reason':'unique_named_pair_required'}
    focal,base=found_a[0],found_b[0]
    if not box_domain(focal) or not box_domain(base):
        return {'status':'unsupported','reason':'closed_oriented_local_box_pair_required'}
    matrix=base['matrix']
    u=unit([matrix[k][0] for k in range(3)])
    v=unit([matrix[k][1] for k in range(3)])
    n=unit([matrix[k][2] for k in range(3)])
    fn=unit([focal['matrix'][k][2] for k in range(3)])
    if abs(dot(n,fn))<1-2e-6 or abs(n[2])<.1:
        return {'status':'unsupported','reason':'parallel_local_z_and_usable_world_z_required'}
    before=focal['world_vertices']
    gap=projections(before,n)[0]-projections(base['world_vertices'],n)[1]
    if gap<=0:
        return {'status':'unsupported','reason':'positive_pair_gap_required'}
    if not finite_foot(before,base,u,v):
        return {'status':'unsupported','reason':'finite_support_footprint_required'}
    common={'gap_m':gap,'unit':'m','coordinate_frame':'world',
            'object_id':focal['object_id'],'revision':scene['revision'],
            'scope':'finite_parallel_local_box_public_data_witness'}
    if mode=='readonly':
        common['status']='measured'
        return common
    satisfied=abs(gap-target)<=1e-6
    dz=0 if satisfied else max(-cap,min(cap,(target-gap)/n[2]))
    after=[[p[0],p[1],p[2]+dz] for p in before]
    if not finite_foot(after,base,u,v):
        common['status']='blocked'
        common['reason']='candidate_exits_finite_support'
        return common
    after_bounds=bounds(after)
    checked=0
    narrow=0
    for obstacle in scene['objects']:
        if obstacle['object_id']!=focal['object_id']:
            checked+=1
            obstacle_bounds=bounds(obstacle['world_vertices'])
            if not aabb_separated(after_bounds,obstacle_bounds):
                narrow+=1
                if not endpoint_separated(after,obstacle['world_vertices'],focal['matrix'],obstacle['matrix']):
                    common['status']='blocked'
                    common['reason']='candidate_endpoint_separation_not_proven'
                    common['checked_other_objects']=checked
                    return common
    common['status']='satisfied' if satisfied else 'candidate'
    if not satisfied:
        common['delta_world_m']=[0,0,dz]
    common['checked_other_objects']=checked
    common['narrow_phase_objects']=narrow
    common['safety_scope']='candidate_endpoint_only; no_general_swept_path_certificate'
    return common

result=solve(scene,mode,target_m,step_cap_m)
'''


def build_program(mode='goal', target_m=.001, step_cap_m=.00099):
    """Build code using only explicit public task settings, never fixture data."""
    if mode not in ('goal', 'readonly'):
        raise ValueError('mode must be goal or readonly')
    if (type(target_m) not in (int, float) or not math.isfinite(target_m) or target_m <= 0
            or type(step_cap_m) not in (int, float) or not math.isfinite(step_cap_m)
            or not 0 < step_cap_m <= .00099):
        raise ValueError('explicit target/step outside witness contract')
    return ('mode=' + repr(mode) + '\ntarget_m=' + repr(float(target_m)) +
            '\nstep_cap_m=' + repr(float(step_cap_m)) + '\n' + _BODY)


PROGRAM = build_program()
READONLY_PROGRAM = build_program(mode='readonly')
