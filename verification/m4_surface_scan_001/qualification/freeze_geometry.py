"""Freeze one functional 24-part assembly before any Blender or product run."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent


def box(size):
    x, y, z = [v / 2 for v in size]
    points = [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),
              (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
    return points, [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
                    (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]


def caps(polygon):
    remaining = list(range(len(polygon)))
    triangles = []
    def area(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    while len(remaining) > 3:
        found = False
        for k,b in enumerate(remaining):
            a,c = remaining[k-1],remaining[(k+1)%len(remaining)]
            if area(polygon[a],polygon[b],polygon[c]) <= 0:
                continue
            if any(min(area(polygon[a],polygon[b],polygon[j]),
                       area(polygon[b],polygon[c],polygon[j]),
                       area(polygon[c],polygon[a],polygon[j])) >= 0
                   for j in remaining if j not in (a,b,c)):
                continue
            triangles.append((a,b,c));remaining.pop(k);found=True;break
        if not found:
            raise ValueError('contour_ear_clipping_failed')
    return triangles + [tuple(remaining)]


def prism(polygon, length, axis='z'):
    n=len(polygon)
    if axis=='z':
        points=[(a,b,h) for h in (-length/2,length/2) for a,b in polygon]
    else:
        points=[(h,a,b) for h in (-length/2,length/2) for a,b in polygon]
    cap=caps(polygon)
    # (x,y)->z and (y,z)->x have positive orientation.
    faces=[tuple(reversed(f)) for f in cap]+[tuple(v+n for v in f) for f in cap]
    for i in range(n):
        j=(i+1)%n;faces.extend([(i,j,j+n),(i,j+n,i+n)])
    return points,faces


def channel(width,height,wall):
    x,y=width/2,height/2
    return [(-x,-y),(x,-y),(x,y),(x-wall,y),(x-wall,-y+wall),
            (-x+wall,-y+wall),(-x+wall,y),(-x,y)]


def angle(width,height,wall):
    x,y=width/2,height/2
    return [(-x,-y),(x,-y),(x,-y+wall),(-x+wall,-y+wall),(-x+wall,y),(-x,y)]


def ring(outer,inner,height,n=16):
    points=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z)
            for z in (-height/2,height/2) for r in (outer,inner) for i in range(n)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        for quad in ((i,j,2*n+j,2*n+i),(n+j,n+i,3*n+i,3*n+j),
                     (j,i,n+i,n+j),(2*n+i,2*n+j,3*n+j,3*n+i)):
            faces.extend([(quad[0],quad[1],quad[2]),(quad[0],quad[2],quad[3])])
    return points,faces


def pin(radius,height,n=16):
    points=[(radius*math.cos(2*math.pi*i/n),radius*math.sin(2*math.pi*i/n),z)
            for z in (-height/2,height/2) for i in range(n)] + [(0,0,-height/2),(0,0,height/2)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([(i,j,n+j),(i,n+j,n+i),(2*n,j,i),(2*n+1,n+i,n+j)])
    return points,faces


def main():
    parts=[]
    def add(role,geometry,center=(0,0,0),rotation=0):
        points,faces=geometry;c=math.cos(math.radians(rotation));s=math.sin(math.radians(rotation))
        points=[[(c*x-s*y+center[0])/1000,(s*x+c*y+center[1])/1000,(z+center[2])/1000]
                for x,y,z in points]
        parts.append({'name':f'Obj_{len(parts)+1:03d}','private_role':role,
                      'vertices_m_before_Blender_binary32':points,'triangles':[list(f) for f in faces]})
    add('base',box((160,110,10)),(0,0,-5))
    rail=prism(channel(16,16,3),148,'x')
    add('slotted rail',rail,(0,-14,8),18)
    add('slotted rail',rail,(0,14,8),-18)
    for i,(w,h,wall,height,bottom,kind) in enumerate(((150,100,4,20,0,'u'),(130,90,4,28,1,'l'),
             (110,80,4,36,.5,'u'),(90,70,4,44,1.5,'l'))):
        polygon=channel(w,h,wall) if kind=='u' else angle(w,h,wall)
        add('upright bracket',prism(polygon,height),(0,0,bottom+height/2))
    add('slider',box((18,20,8)),(-38,-26,22.25),18)
    add('slider',box((18,20,8)),(38,2,20),-18)
    add('cover',box((144,94,1.5)),(0,0,21))
    add('cover',box((106,76,1)),(0,0,37.2))
    add('open cover',([(-43,-33,0),(43,-33,0),(43,33,0),(-43,33,0)],[(0,1,2),(0,2,3)]),(0,0,47))
    for center in ((-38,-26,17),(-25,-22,17),(38,2,17),(50,-2,17)):
        add('annular shim',ring(6,3,1.5),center)
    for center in ((-65,-35,6),(65,7,6),(-65,35,6),(65,-7,6)):
        add('stop',box((9,18,12)),center)
    for center in ((-38,-26,20),(38,2,20),(0,0,10)):
        add('pin',pin(2.4,12),center)
    add('internal spacer',box((6,6,4)),(0,0,-5))
    assert len(parts)==24
    spec={'schema':'surface-scan-fixed-geometry-v1','frozen_utc':datetime.now(timezone.utc).isoformat(),
          'parts':parts,'counts':{'objects':24,'vertices':sum(len(p['vertices_m_before_Blender_binary32']) for p in parts),
                                 'triangles':sum(len(p['triangles']) for p in parts)},
          'threshold_m':.002,'edit':{'object_name':'Obj_008','property':'location.z','delta_m':-.00075},
          'representation':'Baked metre-coordinate static triangle meshes, identity object matrices in base state. Edit changes only one object location.z.',
          'allowed_morphology_revision':{'maximum':1,'condition':'Only if retained AABB pair count is below 69 before product runs.',
              'rule':'Multiply the four bracket contour x/y coordinates by 1.2 about the assembly origin, preserve z and all other parts.',
              'otherwise':'No replacement; report qualification failure.'},
          'controls':{'strict_containment_pair':['Obj_001','Obj_024'],
              'strict_containment_nominal_surface_gap_m':.003,
              'left_zone_members':['Obj_002','Obj_008','Obj_013','Obj_021'],
              'right_zone_members':['Obj_003','Obj_009','Obj_015','Obj_022'],
              'open_mesh':'Obj_012','overlapping_bound_nonmatch_candidates':[['Obj_004','Obj_005'],['Obj_005','Obj_006']]},
          'model_consumers':0,'product_pretests':0,'images':0}
    path=HERE/'GEOMETRY_FREEZE.json'
    with path.open('x',encoding='utf8',newline='\n') as f:json.dump(spec,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'counts':spec['counts'],'freeze_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__=='__main__':
    main()
