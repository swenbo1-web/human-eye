"""Independent rational evidence checks; no engine geometry imports."""
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def rational(value):
    return F.from_float(value) if type(value) is float else F(value)


def vector_sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def area(poly): return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2 if poly else F(0)
def encoded(value):
    if isinstance(value,F): return str(value)
    if isinstance(value,dict): return {str(k):encoded(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [encoded(v) for v in value]
    return value


def decimal_sqrt(value):
    with localcontext() as context:
        context.prec = 90
        return str((Decimal(value.numerator)/Decimal(value.denominator)).sqrt())


def read_meshes(snapshot):
    data = json.loads(Path(snapshot).read_bytes())
    assert rational(data['unit_scale_m']) == 1
    assert hashlib.sha256(Path(data['source_asset']).read_bytes()).hexdigest() == data['source_asset_sha256']
    out = {}
    for row in data['objects']:
        assert row['parent'] is None and row['modifiers'] == []
        assert set(row['source_polygon_sizes']) == {3}
        matrix = [[rational(v) for v in values] for values in row['matrix_world']]
        assert matrix[3] == [0,0,0,1]
        assert [r[:3] for r in matrix[:3]] == [[1,0,0],[0,1,0],[0,0,1]]
        vertices = []
        for local,native in zip(row['vertices_local'],row['vertices_world_native'],strict=True):
            local = [rational(v) for v in local]
            exact = tuple(sum(matrix[k][i]*local[i] for i in range(3))+matrix[k][3] for k in range(3))
            assert exact == tuple(rational(v) for v in native), 'stored/native transform is not exact on frozen dyadic coordinates'
            vertices.append(exact)
        faces = [tuple(face) for face in row['triangles']]
        assert {i for face in faces for i in face} == set(range(len(vertices)))
        assert all(len(set(face)) == 3 and cross(vector_sub(vertices[face[1]],vertices[face[0]]),
            vector_sub(vertices[face[2]],vertices[face[0]])) != (0,0,0) for face in faces)
        out[row['name']] = {'vertices':vertices,'faces':faces,'origin':tuple(matrix[k][3] for k in range(3))}
    return data,out


def contains_triangle(mesh,point):
    for index,face in enumerate(mesh['faces']):
        triangle = [mesh['vertices'][i] for i in face]
        normal = cross(vector_sub(triangle[1],triangle[0]),vector_sub(triangle[2],triangle[0]))
        if dot(normal,vector_sub(point,triangle[0])) != 0: continue
        drop = max(range(3),key=lambda k:abs(normal[k]))
        axes = [k for k in range(3) if k != drop]
        tri = [tuple(v[k] for k in axes) for v in triangle]
        p = tuple(point[k] for k in axes)
        values = [orient(a,b,p) for a,b in zip(tri,tri[1:]+tri[:1])]
        if all(v>=0 for v in values) or all(v<=0 for v in values): return index
    raise AssertionError('analytic witness is absent from actual evaluated triangle surface')


def clip(poly,clipper):
    result = list(poly)
    if orient(clipper[0],clipper[1],clipper[2]) < 0: clipper = list(reversed(clipper))
    for c,d in zip(clipper,clipper[1:]+clipper[:1]):
        old,result = result,[]
        if not old: break
        for p,q in zip(old,old[1:]+old[:1]):
            a,b = orient(c,d,p),orient(c,d,q)
            if a>=0: result.append(p)
            if (a<0<=b) or (b<0<=a):
                t = a/(a-b)
                result.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(2)))
    return result


def closed_boundary(mesh,patches,expected_volume):
    edges = Counter((a,b) for face in mesh['faces'] for a,b in zip(face,face[1:]+face[:1]))
    assert all(count==1 and edges[(b,a)]==1 for (a,b),count in edges.items())
    volume = sum(dot(mesh['vertices'][face[0]],cross(mesh['vertices'][face[1]],mesh['vertices'][face[2]])) for face in mesh['faces'])/6
    assert volume == expected_volume and volume > 0
    groups = {}
    for axis,plane,low,high in patches:
        groups.setdefault((axis,plane),{'rectangles':[],'triangles':[]})['rectangles'].append(
            [(low[0],low[1]),(high[0],low[1]),(high[0],high[1]),(low[0],high[1])])
    for face in mesh['faces']:
        triangle = [mesh['vertices'][i] for i in face]
        planes = [(axis,triangle[0][axis]) for axis in range(3) if len({v[axis] for v in triangle})==1]
        assert len(planes)==1 and planes[0] in groups
        axis,_ = planes[0]
        tri = [tuple(v[k] for k in range(3) if k != axis) for v in triangle]
        group = groups[planes[0]]
        assert sum(area(clip(tri,rect)) for rect in group['rectangles']) == area(tri)
        group['triangles'].append(tri)
    coverage = []
    for key,group in sorted(groups.items()):
        triangles,rectangles = group['triangles'],group['rectangles']
        for index,a in enumerate(triangles):
            assert all(area(clip(a,b))==0 for b in triangles[index+1:]), 'overlapping surface interiors'
        for rect in rectangles:
            assert sum(area(clip(tri,rect)) for tri in triangles) == area(rect), 'surface coverage gap'
        coverage.append({'plane':key,'triangles':len(triangles),'rectangles':len(rectangles),
            'area':sum(area(rect) for rect in rectangles)})
    return {'vertices':len(mesh['vertices']),'triangles':len(mesh['faces']),
        'oriented_closed_manifold':True,'volume':volume,'exact_surface_coverage':coverage}


def box_patches(low,high):
    return [(axis,plane,tuple(low[k] for k in range(3) if k!=axis),
        tuple(high[k] for k in range(3) if k!=axis)) for axis in range(3) for plane in (low[axis],high[axis])]


def box_pair(a,b):
    p,q = [],[]
    for (lo,hi),(low,high) in zip(zip(*a),zip(*b)):
        if hi < low: x,y=hi,low
        elif high < lo: x,y=lo,high
        else: x=y=(max(lo,low)+min(hi,high))/2
        p.append(x);q.append(y)
    return dot(vector_sub(p,q),vector_sub(p,q)),tuple(p),tuple(q)
