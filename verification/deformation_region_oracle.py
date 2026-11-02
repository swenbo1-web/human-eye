"""Independent QA: separating axes over exact frozen numbers, NumPy metrics.

No production selector, clipping helper, validator or triangle metric is imported.
This proves numeric-input conformance, not physical coordinate certainty.
"""
import math
from fractions import Fraction as F


def subtract(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum((x*y for x,y in zip(a,b)),F(0))


def transformed_vertices(vertices,world,unit):
    """Evaluate one affine map as exact algebra over its frozen scalar inputs."""
    matrix=[[F(x) for x in row] for row in world];scale=F(unit)
    return [tuple(scale*(sum((matrix[k][j]*F(p[j]) for j in range(3)),matrix[k][3])) for k in range(3)) for p in vertices]


def triangle_box_sat(points,bounds):
    """Closed triangle-box intersection; 13 separating directions, no clipping.

    The same directions cover collinear triangles and points: zero directions
    are skipped, box face directions remain. Strict separation excludes;
    equality retains exact face, segment and point contact.
    """
    p=[tuple(F(x) for x in row) for row in points];lo,hi=[tuple(F(x) for x in row) for row in bounds]
    axes=[(F(1),F(0),F(0)),(F(0),F(1),F(0)),(F(0),F(0),F(1))]
    edges=[subtract(p[(i+1)%3],p[i]) for i in range(3)]
    directions=axes+[cross(edges[0],edges[1])]+[cross(edge,axis) for edge in edges for axis in axes]
    center=tuple((a+b)/2 for a,b in zip(lo,hi));radius=tuple((b-a)/2 for a,b in zip(lo,hi))
    for axis in directions:
        if not any(axis):continue
        projections=[dot(axis,subtract(point,center)) for point in p]
        extent=sum((abs(a)*b for a,b in zip(axis,radius)),F(0))
        if min(projections)>extent or max(projections)<-extent:return False
    return True


def matching_indices(packet,bounds):
    mesh=packet['inputs']['mesh'];evaluated=packet['evaluated']
    points=transformed_vertices(evaluated['vertices'],evaluated['mesh_matrix_world'],packet['inputs']['unit_scale_m'])
    return [index for index,tri in enumerate(mesh['triangles']) if triangle_box_sat([points[i] for i in tri],bounds)]


def independent_metric(original,current,unweighted=()):
    """QR/SVD and centered NumPy singular scale, independent of chosen chart.

    Reliability follows the public B2 error model. The SVD route differs from
    production's closed-form centered eigenvalue and analytic 2x2 solve.
    """
    import numpy as np
    a=np.asarray(original,dtype=float);b=np.asarray(current,dtype=float)
    area0=float(np.linalg.norm(np.cross(a[1]-a[0],a[2]-a[0])))
    area1=float(np.linalg.norm(np.cross(b[1]-b[0],b[2]-b[0])))
    exact=lambda p:not any(cross(subtract(tuple(F(x) for x in p[1]),tuple(F(x) for x in p[0])),subtract(tuple(F(x) for x in p[2]),tuple(F(x) for x in p[0]))))
    reference_zero=exact(original);current_zero=exact(current)
    result=dict(state='unknown',reason=None,principal_stretches=None,area_ratio=None,reference_geometry='zero_area' if reference_zero else 'nonzero_area',
        current_geometry='zero_area' if current_zero else 'nonzero_area',unweighted_vertices=list(unweighted))
    def unknown(reason):return dict(result,reason=reason)
    if reference_zero:return unknown('original_zero_area')
    if unweighted:return unknown('unweighted_vertex_source')
    longest=max(float(np.linalg.norm(a[(i+1)%3]-a[i])) for i in range(3))
    q0=8*(2**-24*float(np.max(np.abs(a)))+2**-149);q1=8*(2**-24*float(np.max(np.abs(b)))+2**-149)
    if longest<=16*q0:return unknown('reference_below_coordinate_resolution')
    if area0<=2**-20*longest*longest:return unknown('reference_ill_conditioned')
    height=area0/longest
    if height<=16*q0:return unknown('reference_height_below_resolution')
    centered=a-a.mean(axis=0);smin=float(np.linalg.svd(centered.T,compute_uv=False)[1])
    if smin<=3*q0:return unknown('metric_resolution_insufficient')
    _,chart=np.linalg.qr((a[1:]-a[0]).T,mode='reduced')
    gradient=np.linalg.solve(chart.T,(b[1:]-b[0])).T
    factors=np.linalg.svd(gradient,compute_uv=False);high,low=map(float,factors);area=area1/area0
    if current_zero:low=area=0.
    error=max(8*(3*q1+max(1.,high)*3*q0)/(smin-3*q0),32*(q1+max(1.,high)*q0)/height)
    area_error=(high+low)*error+error*error
    if not all(math.isfinite(x) for x in (high,low,area,error,area_error)) or error>.01 or area_error>.02:return unknown('metric_resolution_insufficient')
    current_longest=max(float(np.linalg.norm(b[(i+1)%3]-b[i])) for i in range(3))
    if not current_zero and (low<=4*error or area1<=2**-20*current_longest*current_longest):return unknown('current_near_degenerate')
    return dict(result,state='collapsed' if current_zero else 'measured',reason='current_zero_area' if current_zero else None,
        principal_stretches=[high,low],area_ratio=area)


def all_facts(packet,indices):
    mesh=packet['inputs']['mesh'];evaluated=packet['evaluated'];out={}
    unweighted={i for i,groups in enumerate(mesh['weights']) if not any(weight>0 for _,weight in groups)}
    for index in indices:
        tri=mesh['triangles'][index]
        out[index]=dict(independent_metric([mesh['vertices'][i] for i in tri],[evaluated['vertices'][i] for i in tri],unweighted=[i for i in tri if i in unweighted]),
            triangle=index,vertices=tri[:])
    return out
