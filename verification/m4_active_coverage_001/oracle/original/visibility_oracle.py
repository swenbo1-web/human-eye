"""Design fixture only: exact rational planar ROI/opaque-box shadow oracle.

Does not import Human Eye, Blender, NumPy, a scorer, or a model provider.
No picture is rendered. This is not a product visibility implementation.
"""
from fractions import Fraction as F
from itertools import combinations, product
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
DIRECTIONS={'SCENE':(4,-4,3),'TOP':(0,0,1),'LEFT':(-1,0,1),
            'RIGHT':(1,0,1),'FRONT':(0,-1,1),'BACK':(0,1,1)}
# One frozen layout, no resampling against its answer or any model.
BLOCKERS=[('SCENE','TOP'),('SCENE','LEFT','FRONT'),('SCENE','RIGHT','TOP'),
          ('BACK','TOP','LEFT'),('LEFT','RIGHT','FRONT','BACK','TOP'),tuple(DIRECTIONS)]

def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
def hull(points):
    points=sorted(set(points))
    lower=[];upper=[]
    for point in points:
        while len(lower)>1 and cross(lower[-2],lower[-1],point)<=0:lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper)>1 and cross(upper[-2],upper[-1],point)<=0:upper.pop()
        upper.append(point)
    return lower[:-1]+upper[:-1]
def clip(poly, axis, bound, keep_less):
    if not poly:return []
    def inside(p):return p[axis]<=bound if keep_less else p[axis]>=bound
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ia,ib=inside(a),inside(b)
        if ia:result.append(a)
        if ia!=ib:
            t=(bound-a[axis])/(b[axis]-a[axis])
            result.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(2)))
    return result
def area(poly):
    if not poly:return F(0)
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))/2
def overlap_area(rect,box,direction):
    dx,dy,dz=map(F,direction)
    shadow=hull([(x-z*dx/dz,y-z*dy/dz) for x,y,z in product(*box)])
    for axis in (0,1):
        shadow=clip(shadow,axis,rect[axis][0],False)
        shadow=clip(shadow,axis,rect[axis][1],True)
    return area(shadow)
def dump_fraction(value):
    if isinstance(value,F):return str(value)
    raise TypeError(type(value).__name__)

panels=[];boxes=[];meshes=[]
for n,blocked in enumerate(BLOCKERS):
    cx=F(n%3)*F(6,25);cy=F(n//3)*F(6,25);half=F(1,50)
    bounds=((cx-half,cx+half),(cy-half,cy+half))
    identity='Obj_'+str(n+1).zfill(3)
    panels.append({'object_id':identity,'rect_xy':bounds,'plane_z':F(0),'front_normal':(0,0,1)})
    meshes.append({'name':identity,'vertices':[(bounds[0][0],bounds[1][0],F(0)),(bounds[0][1],bounds[1][0],F(0)),(bounds[0][1],bounds[1][1],F(0)),(bounds[0][0],bounds[1][1],F(0))],'triangles':[(0,1,2),(0,2,3)]})
    for view in blocked:
        dx,dy,dz=map(F,DIRECTIONS[view]);z=F(2,25)
        bx=cx+z*dx/dz;by=cy+z*dy/dz;bh=F(3,125)
        box=((bx-bh,bx+bh),(by-bh,by+bh),(z-F(1,1000),z+F(1,1000)))
        boxes.append({'object_id':'Obj_'+str(7+len(boxes)).zfill(3),'bounds':box})
for box in boxes:
    vertices=list(product(*box['bounds']))
    faces=[(0,1,3),(0,3,2),(4,6,7),(4,7,5),(0,4,5),(0,5,1),
           (2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3)]
    meshes.append({'name':box['object_id'],'vertices':vertices,'triangles':faces})
visibility={};proofs=[]
for view,direction in DIRECTIONS.items():
    visibility[view]=[]
    for panel in panels:
        intersections=[]
        for box in boxes:
            a=overlap_area(panel['rect_xy'],box['bounds'],direction)
            if a:intersections.append({'occluder':box['object_id'],'overlap_area_m2':a})
        if not intersections:visibility[view].append(panel['object_id'])
        proofs.append({'direction':view,'target':panel['object_id'],'full_interior_visible':not intersections,'positive_area_blockers':intersections})
coverable=set().union(*(set(values) for values in visibility.values()))
unresolved=sorted({panel['object_id'] for panel in panels}-coverable)
optimal=[]
for n in range(1,len(DIRECTIONS)+1):
    optimal=[list(c) for c in combinations(DIRECTIONS,n) if set().union(*(set(visibility[v]) for v in c))==coverable]
    if optimal:break
scene={'schema':'active-inspection-design-fixture-v1','unit':'m','coordinate_frame':'world','objects':meshes,
       'scope':'Prospective small assembly inspection fixture. Not an existing user asset or a rendered/model-tested scene.'}
task={'task':'Discover every independent nondegenerate planar rectangular quad mesh. For its front side, choose local views that reveal its complete open interior, accumulating coverage across the scene. Keep all occluders present and report any target unresolved by the available directions. Do not select by object name.','discovery_rule':'four vertices, two coplanar triangles forming a rectangle; consistent front normal','directions':DIRECTIONS,'forbidden_input':'No panel IDs, panel count, blocker assignment, visibility matrix, answer or optimal-view count supplied to consumers. Geometry and the common task are available to both routes.'}
for name,value in [('SCENE_GEOMETRY_RATIONAL.json',scene),('TASK_SPEC.json',task)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=dump_fraction),encoding='utf8')
answer={'schema':'independent-active-inspection-oracle-v1','scope':'Exact full open-interior visibility for six finite orthographic directions. It proves neither pixel readability nor impossibility from every possible camera.','objects':len(meshes),'triangles':sum(len(m['triangles']) for m in meshes),'discovered_targets':[p['object_id'] for p in panels],'visibility_by_direction':visibility,'coverable_targets':sorted(coverable),'unresolved_in_finite_view_pool':unresolved,'minimum_direction_count_for_coverable':len(optimal[0]) if optimal else 0,'optimal_direction_subsets':optimal,'proofs':proofs,'source_sha256':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('SCENE_GEOMETRY_RATIONAL.json','TASK_SPEC.json')},'product_Blender_model_API_runs':0}
(OUT/'ORACLE.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2,default=dump_fraction),encoding='utf8')
print(json.dumps({k:answer[k] for k in ('objects','triangles','discovered_targets','visibility_by_direction','coverable_targets','unresolved_in_finite_view_pool','minimum_direction_count_for_coverable','optimal_direction_subsets')},ensure_ascii=False))
