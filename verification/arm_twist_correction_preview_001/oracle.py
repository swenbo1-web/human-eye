"""Independent fixed-case geometry: no twist model, labels, or product solver.

Ordered section areas use Newell's three-dimensional area vector; an independent
projection/shoelace implementation is also available for the coaxial checks.
Matrix operations use NumPy, rather than the product's rig_pose helpers.
"""
from __future__ import annotations

import math
import numpy as np


def rotation_y(degrees):
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    return np.array([[c,0.,s,0.],[0.,1.,0.,0.],[-s,0.,c,0.],[0.,0.,0.,1.]])


def rotation_x(degrees):
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    return np.array([[1.,0.,0.,0.],[0.,c,-s,0.],[0.,s,c,0.],[0.,0.,0.,1.]])


def chain_poses(rests,u_deg,theta_deg,*,swing_deg=0.):
    """Ordinary parent FK with roll-bearing rest matrices, not the solver."""
    matrices=[np.asarray(matrix,dtype=float) for matrix in rests]
    basis=[np.eye(4),rotation_y(u_deg)@rotation_x(swing_deg),rotation_y(theta_deg-u_deg)]
    poses=[]
    for index,(rest,delta) in enumerate(zip(matrices,basis)):
        relative=rest if index==0 else np.linalg.solve(matrices[index-1],rest)
        poses.append(relative@delta if index==0 else poses[-1]@relative@delta)
    return [pose.tolist() for pose in poses]


def skin_vertices(patch,poses=None):
    """Independent direct LBS of all supplied point rows in their input order."""
    rest=np.asarray(patch['rest_vertices'],dtype=float)
    homogeneous=np.column_stack((rest,np.ones(len(rest))))
    weights=np.asarray(patch['weights'],dtype=float)
    poses=poses if poses is not None else [bone['pose_matrix'] for bone in patch['bone_chain']]
    output=np.zeros_like(rest)
    for index,(bone,pose) in enumerate(zip(patch['bone_chain'],poses)):
        deform=np.asarray(pose,dtype=float)@np.linalg.inv(np.asarray(bone['rest_matrix'],dtype=float))
        transformed=(homogeneous@deform.T)[:,:3]
        output+=weights[:,index,None]*transformed
    return output.tolist()


def local_basis_matrices(patch,poses=None):
    rests=[np.asarray(bone['rest_matrix'],dtype=float) for bone in patch['bone_chain']]
    poses=[np.asarray(pose,dtype=float) for pose in (poses if poses is not None
           else [bone['pose_matrix'] for bone in patch['bone_chain']])]
    output=[]
    for index,(rest,pose) in enumerate(zip(rests,poses)):
        relative=rest if index==0 else np.linalg.solve(rests[index-1],rest)
        parent_relative=pose if index==0 else np.linalg.solve(poses[index-1],pose)
        output.append(np.linalg.solve(relative,parent_relative).tolist())
    return output


def polygon_area(points):
    """Newell area-vector magnitude; translations cancel before summation."""
    values=np.asarray(points,dtype=float)
    values=values-values.mean(axis=0)
    vector=[]
    for first,second in ((1,2),(2,0),(0,1)):
        vector.append(.5*math.fsum((float(values[i,first])-float(values[(i+1)%len(values),first]))*
            (float(values[i,second])+float(values[(i+1)%len(values),second])) for i in range(len(values))))
    return math.hypot(*vector)


def section_area_ratios(rest,current,sections):
    reference=np.asarray(rest,dtype=float);deformed=np.asarray(current,dtype=float)
    return [polygon_area(deformed[section])/polygon_area(reference[section]) for section in sections]


def projected_section_ratios(rest,current,sections):
    """Signed shoelace areas projected into each original section's plane."""
    reference=np.asarray(rest,dtype=float);deformed=np.asarray(current,dtype=float);ratios=[]
    for section in sections:
        before=reference[section];after=deformed[section];origin=before.mean(axis=0)
        axis=before[1]-before[0];axis=axis/np.linalg.norm(axis)
        normal=np.cross(before[1]-before[0],before[2]-before[0]);normal/=np.linalg.norm(normal)
        second=np.cross(normal,axis)
        def area(points):
            coords=np.column_stack(((points-origin)@axis,(points-origin)@second))
            return .5*abs(math.fsum(float(coords[i,0])*float(coords[(i+1)%len(coords),1])-
                float(coords[(i+1)%len(coords),0])*float(coords[i,1]) for i in range(len(coords))))
        ratios.append(area(after)/area(before))
    return ratios


def section_objective(rest,current,sections):
    ratios=section_area_ratios(rest,current,sections)
    return {'section_area_ratios':ratios,'max_section_area_loss':max(0.,max(1.-ratio for ratio in ratios))}


def known_objective(theta_deg,u_deg):
    """Independent analytic minimax truth, used solely on the QA side."""
    return max(math.sin(math.radians(u_deg)/2)**2,math.sin(math.radians(theta_deg-u_deg)/2)**2)
