"""Private exact oracle from final exported world triangles, without HumanEye.

Synthetic qualification only: certify Cartesian extrusions from their complete
boundary triangles, then intersect exact footprint polygons. Intent labels and
builder answer fields are never consulted. This is not a general asset solver.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rational(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite exported coordinate required')
    return F(value)


def cross2(a, b):
    return a[0]*b[1]-a[1]*b[0]


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross3(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def area(poly):
    return abs(sum(cross2(a, b) for a, b in zip(poly, poly[1:]+poly[:1])))/2 if len(poly)>=3 else F(0)


def ccw(poly):
    return poly if sum(cross2(a, b) for a, b in zip(poly, poly[1:]+poly[:1]))>=0 else list(reversed(poly))


def clip(subject, boundary):
    output=list(subject)
    for a, b in zip(boundary, boundary[1:]+boundary[:1]):
        previous=output
        output=[]
        if not previous:
            break
        edge=sub(b,a)
        for p, q in zip(previous, previous[1:]+previous[:1]):
            fp=cross2(edge,sub(p,a));fq=cross2(edge,sub(q,a))
            if fp>=0:
                output.append(p)
            if (fp<0<=fq) or (fq<0<=fp):
                t=fp/(fp-fq)
                output.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(2)))
    return output


def rectangle(x0, x1, z0, z1):
    return [(x0,z0),(x1,z0),(x1,z1),(x0,z1)]


def hull(points):
    points=sorted(set(points))
    require(len(points)>=3, 'footprint needs three distinct points')
    lower=[];upper=[]
    for p in points:
        while len(lower)>=2 and cross2(sub(lower[-1],lower[-2]),sub(p,lower[-1]))<=0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross2(sub(upper[-1],upper[-2]),sub(p,upper[-1]))<=0:
            upper.pop()
        upper.append(p)
    result=lower[:-1]+upper[:-1]
    require(area(result)>0, 'degenerate convex hull')
    return result


def frac(value):
    return {'numerator':str(value.numerator),'denominator':str(value.denominator),'float':float(value)}


def point_record(point):
    return {'world_m':[float(v) for v in point], 'exact':[frac(v) for v in point]}


def object_mesh(row):
    vertices=row.get('world_vertices',row.get('vertices_world'))
    triangles=row.get('triangles',row.get('triangle_indices',row.get('faces')))
    require(type(vertices) is list and type(triangles) is list,'complete world geometry required')
    vertices=[tuple(rational(v) for v in point) for point in vertices]
    require(all(len(point)==3 for point in vertices),'3D world vertices required')
    triangles=[tuple(face.get('vertices') if type(face) is dict else face) for face in triangles]
    require(all(len(face)==3 and all(type(i) is int and 0<=i<len(vertices) for i in face)
                for face in triangles),'complete triangle indices required')
    require(vertices and triangles,'empty geometry')
    identifier=row.get('object_id',row.get('name',row.get('name_full')))
    require(type(identifier) is str and identifier,'object identity required')
    return {'id':identifier,'name':row.get('name',identifier),'vertices':vertices,'triangles':triangles,
            'bounds':[(min(p[k] for p in vertices),max(p[k] for p in vertices)) for k in range(3)]}


def manifold(mesh):
    undirected=Counter();directed=Counter()
    for face in mesh['triangles']:
        p,q,r=[mesh['vertices'][i] for i in face]
        require(cross3(sub(q,p),sub(r,p))!=(0,0,0),'zero-area original triangle')
        for a,b in zip(face,face[1:]+face[:1]):
            undirected[tuple(sorted((a,b)))]+=1
            directed[a,b]+=1
    require(all(n==2 for n in undirected.values()),'mesh not closed two-manifold')
    require(all(directed[a,b]==directed[b,a]==1 for a,b in undirected),'inconsistent triangle winding')
    return {'vertices':len(mesh['vertices']),'triangles':len(mesh['triangles']),
            'undirected_edges':len(undirected),'closed_consistently_oriented':True}


def no_overlap(polys):
    for i,a in enumerate(polys):
        for b in polys[i+1:]:
            require(area(clip(a,b))==0,'overlapping boundary triangles')


def certify_ring(mesh):
    levels=[sorted(set(p[k] for p in mesh['vertices'])) for k in range(3)]
    require([len(v) for v in levels]==[4,2,4],'not four-X/two-Y/four-Z ring candidate')
    stats=manifold(mesh)
    x,y,z=levels
    cells={(i,j):rectangle(x[i],x[i+1],z[j],z[j+1]) for i in range(3) for j in range(3)}
    caps={level:[] for level in y}
    for face in mesh['triangles']:
        points=[mesh['vertices'][i] for i in face]
        if len({p[1] for p in points})==1:
            caps[points[0][1]].append(ccw([(p[0],p[2]) for p in points]))
    occupied=[]
    for key,cell in cells.items():
        amounts=[sum(area(clip(tri,cell)) for tri in caps[level]) for level in y]
        require(amounts[0]==amounts[1] and amounts[0] in (0,area(cell)),
                'caps are not complete identical grid cells')
        if amounts[0]:
            occupied.append(key)
    require(set(occupied)==set(cells)-{(1,1)},'not rectangular through-hole material footprint')
    expected=defaultdict(list)
    for i,j in occupied:
        for yy in y:
            expected[1,yy].append(cells[i,j])
        for ni,constant in ((i-1,x[i]),(i+1,x[i+1])):
            if (ni,j) not in occupied:
                expected[0,constant].append(rectangle(y[0],y[1],z[j],z[j+1]))
        for nj,constant in ((j-1,z[j]),(j+1,z[j+1])):
            if (i,nj) not in occupied:
                expected[2,constant].append(rectangle(x[i],x[i+1],y[0],y[1]))
    actual=defaultdict(list)
    for face in mesh['triangles']:
        points=[mesh['vertices'][i] for i in face]
        constant=[k for k in range(3) if len({p[k] for p in points})==1]
        require(len(constant)==1,'nonrectangular ring boundary triangle')
        axis=constant[0];key=axis,points[0][axis]
        require(key in expected,'unexpected ring boundary plane')
        axes=[k for k in range(3) if k!=axis]
        tri=ccw([tuple(p[k] for k in axes) for p in points])
        require(sum(area(clip(tri,rect)) for rect in expected[key])==area(tri),
                'ring triangle outside reconstructed occupied-cell boundary')
        actual[key].append(tri)
    for key,rects in expected.items():
        no_overlap(actual[key])
        for rect in rects:
            require(sum(area(clip(tri,rect)) for tri in actual[key])==area(rect),
                    'missing ring boundary area')
    return {'mesh':mesh,'levels':levels,'cells':[cells[key] for key in sorted(occupied)],
            'center':tuple((lo+hi)/2 for lo,hi in mesh['bounds']),
            'certificate':{**stats,'kind':'rectangular_through_hole_Y_extrusion',
                'levels':[[frac(v) for v in axis] for axis in levels],
                'occupied_XZ_grid_cells':[list(key) for key in sorted(occupied)],
                'complete_original_boundary_matches_cells':True}}


def certify_convex_extrusion(mesh, axis=1):
    ys=sorted(set(p[axis] for p in mesh['vertices']))
    require(len(ys)==2,'convex neighbor must have exactly two extrusion levels')
    stats=manifold(mesh)
    axes=[k for k in range(3) if k!=axis]
    polygon=hull([tuple(p[k] for k in axes) for p in mesh['vertices']])
    caps={v:[] for v in ys};sides=defaultdict(list)
    for face in mesh['triangles']:
        pts=[mesh['vertices'][i] for i in face]
        footprint=[tuple(p[k] for k in axes) for p in pts]
        if len({p[axis] for p in pts})==1:
            caps[pts[0][axis]].append(ccw(footprint))
            continue
        require(area(footprint)==0,'side triangle is not extrusion-aligned')
        matches=[]
        for idx,(a,b) in enumerate(zip(polygon,polygon[1:]+polygon[:1])):
            edge=sub(b,a);coordinate=0 if edge[0] else 1
            if all(cross2(edge,sub(p,a))==0 for p in footprint):
                ts=[(p[coordinate]-a[coordinate])/edge[coordinate] for p in footprint]
                if all(0<=t<=1 for t in ts):
                    matches.append((idx,ccw([(t,p[axis]) for t,p in zip(ts,pts)])))
        require(len(matches)==1,'side does not match unique convex boundary edge')
        sides[matches[0][0]].append(matches[0][1])
    for cap in caps.values():
        no_overlap(cap)
        require(sum(area(tri) for tri in cap)==area(polygon),'convex cap incomplete')
    for index in range(len(polygon)):
        no_overlap(sides[index])
        require(sum(area(tri) for tri in sides[index])==ys[1]-ys[0],
                'convex extrusion side incomplete')
    return {'mesh':mesh,'polygon':polygon,'interval':ys,'axis':axis,
        'certificate':{**stats,'kind':'convex_polygon_extrusion','axis':axis,
            'footprint_vertices':[[frac(v) for v in p] for p in polygon],
            'extrusion_interval':[frac(v) for v in ys],
            'complete_original_boundary_matches_convex_prism':True}}


def point_on_triangle(p,tri):
    a,b,c=tri;n=cross3(sub(b,a),sub(c,a))
    if dot(n,sub(p,a)):
        return False
    drop=next(i for i,x in enumerate(n) if x)
    axes=[i for i in range(3) if i!=drop]
    project=lambda q:tuple(q[i] for i in axes)
    q=project(p);poly=ccw([project(v) for v in tri])
    return all(cross2(sub(b,a),sub(q,a))>=0 for a,b in zip(poly,poly[1:]+poly[:1]))


def strictly_inside_original(mesh,p):
    triangles=[[mesh['vertices'][i] for i in face] for face in mesh['triangles']]
    if any(point_on_triangle(p,tri) for tri in triangles):
        return False
    for direction in ((1,2,3),(2,3,5),(3,5,7),(5,7,11),(7,11,13)):
        count=0;ambiguous=False
        for tri in triangles:
            a,b,c=tri;n=cross3(sub(b,a),sub(c,a));denominator=dot(n,direction)
            if not denominator:
                if not dot(n,sub(a,p)):
                    ambiguous=True;break
                continue
            t=dot(n,sub(a,p))/denominator
            if t<=0:
                continue
            hit=tuple(p[k]+t*direction[k] for k in range(3))
            if point_on_triangle(hit,tri):
                drop=next(i for i,x in enumerate(n) if x)
                axes=[i for i in range(3) if i!=drop]
                poly=ccw([tuple(v[i] for i in axes) for v in tri]);q=tuple(hit[i] for i in axes)
                if any(cross2(sub(b,a),sub(q,a))==0 for a,b in zip(poly,poly[1:]+poly[:1])):
                    ambiguous=True;break
                count+=1
        if not ambiguous:
            return count%2==1
    raise ValueError('all independent strict-interior rays ambiguous')


def point_segment_distance2(p,a,b):
    edge=sub(b,a);t=max(F(0),min(F(1),dot(sub(p,a),edge)/dot(edge,edge)))
    closest=tuple(a[k]+t*edge[k] for k in range(2))
    return dot(sub(p,closest),sub(p,closest)),p,closest


def segment_distance2(a,b,c,d):
    ab=sub(b,a);cd=sub(d,c);den=cross2(ab,cd)
    if den:
        t=cross2(sub(c,a),cd)/den;u=cross2(sub(c,a),ab)/den
        if 0<=t<=1 and 0<=u<=1:
            p=tuple(a[k]+t*ab[k] for k in range(2))
            return F(0),p,p
    candidates=[point_segment_distance2(p,c,d) for p in (a,b)]
    for p in (c,d):
        dist,q,r=point_segment_distance2(p,a,b)
        candidates.append((dist,r,q))
    return min(candidates,key=lambda item:item[0])


def relation(ring,neighbor):
    polygon=neighbor['polygon'];y0,y1=ring['levels'][1];n0,n1=neighbor['interval']
    depth=max(F(0),min(y1,n1)-max(y0,n0))
    intersections=[clip(polygon,cell) for cell in ring['cells']]
    intersection_area=sum(area(poly) for poly in intersections)
    volume=intersection_area*depth
    witness=None
    if volume:
        poly=next(poly for poly in intersections if area(poly)>0)
        xz=tuple(sum(p[k] for p in poly)/len(poly) for k in range(2))
        p=(xz[0],(max(y0,n0)+min(y1,n1))/2,xz[1])
        require(strictly_inside_original(ring['mesh'],p),'material witness not inside original ring triangles')
        require(strictly_inside_original(neighbor['mesh'],p),'material witness not inside original neighbor triangles')
        witness={**point_record(p),'strict_inside_both_original_triangle_meshes':True,
                 'method':'independent_exact_generic_ray_parity_with_boundary_exclusion'}
    distances=[]
    for cell,overlap in zip(ring['cells'],intersections):
        if area(overlap)>0:
            p=overlap[0];distances.append((F(0),p,p))
        else:
            distances.extend(segment_distance2(a,b,c,d)
                for a,b in zip(cell,cell[1:]+cell[:1])
                for c,d in zip(polygon,polygon[1:]+polygon[:1]))
    distance2,ring_xz,neighbor_xz=min(distances,key=lambda item:item[0])
    ygap=max(F(0),n0-y1,y0-n1)
    distance2+=ygap*ygap
    threshold=F(1,4000)
    status='solid_overlap' if volume else 'within_contact_tolerance' if distance2<=threshold*threshold else 'separated'
    return {'ring_id':ring['mesh']['id'],'neighbor_id':neighbor['mesh']['id'],
        'classification':status,'contact_tolerance_m':frac(threshold),
        'intersection_XZ_area_m2':frac(intersection_area),'intersection_Y_depth_m':frac(depth),
        'intersection_volume_m3':frac(volume),'minimum_distance_squared_m2':frac(distance2),
        'minimum_distance_mm':math.sqrt(float(distance2))*1000,
        'distance_scope':'solid-set distance; surface separation when interiors do not overlap',
        'strict_interior_witness':witness,
        'distance_method':'exact_footprint_edge_segment_distance_plus_Cartesian_interval_gap',
        'intersection_method':'exact_convex_polygon_clipping_against_certified_material_grid_prisms',
        'aabb_is_not_penetration_evidence':True}


def permuted_mesh(mesh,axes):
    return {**mesh,'vertices':[tuple(p[k] for k in axes) for p in mesh['vertices']],
            'bounds':[mesh['bounds'][k] for k in axes]}


def midpoint(bounds):
    return tuple((a+b)/2 for a,b in bounds)


def box_distance2(a,b):
    return sum(max(F(0),b0-a1,a0-b1)**2 for (a0,a1),(b0,b1) in zip(a,b))


def mesh_digest(mesh):
    payload={'world_vertices':[[[str(v.numerator),str(v.denominator)] for v in p]
                               for p in mesh['vertices']], 'triangles':mesh['triangles']}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()


def main():
    root=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=root/'admin'/'world_geometry.json')
    parser.add_argument('--output-dir',type=Path,default=root/'oracle')
    args=parser.parse_args()
    blob=args.input.read_bytes();export=json.loads(blob)
    require(export.get('schema')=='world-geometry-v1' and export.get('unit')=='m'
            and export.get('coordinate_frame')=='world','world-metre source contract required')
    shared=root/'shared'
    scene_sha=hashlib.sha256((shared/'scene.blend').read_bytes()).hexdigest()
    require(export.get('source_sha256')==scene_sha,'export does not bind current frozen scene bytes')
    objects=[object_mesh(row) for row in export['objects']]
    require(len({mesh['id'] for mesh in objects})==len(objects),'duplicate object identity')
    rings=[];rails=[];convex_y=[];pipes=[]
    for mesh in objects:
        levels=[len(set(p[k] for p in mesh['vertices'])) for k in range(3)]
        if levels==[4,2,4]:
            rings.append(certify_ring(mesh))
        elif levels==[2,4,4]:
            rail=certify_ring(permuted_mesh(mesh,(1,0,2)))
            rail['original_mesh']=mesh
            rails.append(rail)
        elif levels[1]==2:
            try:
                convex_y.append(certify_convex_extrusion(mesh))
            except ValueError:
                pass  # Background shapes are outside this oracle's pair domain.
        widths=[b-a for a,b in mesh['bounds']]
        if levels[2]==2 and widths[2]>4*max(widths[:2]):
            try:
                pipe=certify_convex_extrusion(mesh,axis=2)
                if len(pipe['polygon'])>=8:
                    pipes.append(pipe)
            except ValueError:
                pass
    require(len(rings)==4 and len(rails)==2 and len(pipes)==2,
            'four same-domain hole frames, two hollow rails and dual vertical pipes required')
    lower_rail=min(rails,key=lambda item:item['original_mesh']['bounds'][2][0])['original_mesh']
    support_rank=sorted((box_distance2(ring['mesh']['bounds'],lower_rail['bounds']),ring['mesh']['id'],ring)
                        for ring in rings)
    distance2,_,target=support_rank[0]
    require(support_rank[1][0]>distance2,'lower-rail clue has no unique closest frame')
    # Attain the AABB lower bound on both ORIGINAL surfaces. This establishes
    # actual closest support distance; other candidates' lower bounds exceed it.
    tb=target['mesh']['bounds'];rb=lower_rail['bounds']
    xy=[(max(tb[k][0],rb[k][0])+min(tb[k][1],rb[k][1]))/2 for k in (0,1)]
    require(all(max(tb[k][0],rb[k][0])<min(tb[k][1],rb[k][1]) for k in (0,1)),
            'support witness needs overlapping X/Y')
    target_support=(xy[0],xy[1],tb[2][0]);rail_support=(xy[0],xy[1],rb[2][1])
    for mesh,p in ((target['mesh'],target_support),(lower_rail,rail_support)):
        require(any(point_on_triangle(p,[mesh['vertices'][i] for i in face])
                    for face in mesh['triangles']),'support lower bound not attained on original surface')
    require(dot(sub(target_support,rail_support),sub(target_support,rail_support))==distance2,
            'support lower bound mismatch')
    width=tb[0][1]-tb[0][0];height=tb[2][1]-tb[2][0];center=target['center']
    beams=[item for item in convex_y
        if item['mesh']['bounds'][0][1]-item['mesh']['bounds'][0][0]>4*width
        and item['mesh']['bounds'][2][1]-item['mesh']['bounds'][2][0]<height
        and tb[2][0]<midpoint(item['mesh']['bounds'])[2]<tb[2][1]
        and item['mesh']['bounds'][1][1]<tb[1][0]]
    require(len(beams)==1,'front-crossbeam clue not unique')
    front_beam=beams[0]['mesh']
    zmid=(min(r['center'][2] for r in rings)+max(r['center'][2] for r in rings))/2
    lower_rings=[ring for ring in rings if ring['center'][2]<zmid]
    def pipe_proximity(ring):
        return sum(sum((ring['center'][k]-midpoint(pipe['mesh']['bounds'])[k])**2
                       for k in (0,1)) for pipe in pipes)
    pipe_rank=sorted((pipe_proximity(ring),ring['mesh']['id']) for ring in lower_rings)
    require(pipe_rank[0][1]==target['mesh']['id'] and pipe_rank[0][0]<pipe_rank[1][0],
            'dual-upright proximity does not independently select same lower frame')
    short_rects=[]
    for item in convex_y:
        b=item['mesh']['bounds'];c=midpoint(b);wx=b[0][1]-b[0][0];hz=b[2][1]-b[2][0]
        if (len(item['polygon'])==4 and wx<width/2 and wx*F(3,2)<hz<height
                and max(b[1][0],tb[1][0])<min(b[1][1],tb[1][1])
                and tb[2][0]<c[2]<tb[2][1] and abs(c[0]-center[0])<width):
            short_rects.append(item)
    right=[item for item in short_rects if midpoint(item['mesh']['bounds'])[0]>center[0]]
    left=[item for item in short_rects if midpoint(item['mesh']['bounds'])[0]<tb[0][0]]
    require(len(right)==len(left)==1,'short right separator/left locator roles not unique')
    xl,yl,zl=target['levels']
    probes=[item for item in convex_y if len(item['polygon'])==12
        and item['interval'][0]<yl[0] and item['interval'][1]>yl[1]
        and all(xl[1]<p[0]<xl[2] and zl[1]<p[1]<zl[2] for p in item['polygon'])]
    require(len(probes)==1,'straight 12-gon through-opening probe not unique')
    roles=[('near_right_upright_separator',right[0]),
           ('left_short_locator_block',left[0]),('through_opening_probe_rod',probes[0])]
    relations=[];neighbor_certificates=[]
    for role,neighbor in roles:
        result=relation(target,neighbor)
        result['neighbor_role']=role
        relations.append(result)
        neighbor_certificates.append({'object_id':neighbor['mesh']['id'],
            'world_mesh_sha256':mesh_digest(neighbor['mesh']),**neighbor['certificate']})
    # Probe center is independently outside original ring triangles, inside the
    # actual rod, and strictly between its original caps, not an AABB argument.
    probe=probes[0];probe_center=midpoint(probe['mesh']['bounds'])
    require(not strictly_inside_original(target['mesh'],probe_center),'probe center unexpectedly in frame material')
    require(strictly_inside_original(probe['mesh'],probe_center),'probe center not inside original rod')
    source_binding={'scene_sha256':scene_sha,
        'catalog_sha256':hashlib.sha256((shared/'CATALOG.json').read_bytes()).hexdigest(),
        'initial_view_sha256':hashlib.sha256((shared/'INITIAL.png').read_bytes()).hexdigest()}
    oracle={'schema':'private-spatial-perception-oracle-v1','task_id':'SPATIAL-PERCEPTION-QUAL-001',
        'provenance':'controlled_synthetic_final_world_triangle_export',
        'source_binding':source_binding,'world_geometry_sha256':hashlib.sha256(blob).hexdigest(),
        'target_id':target['mesh']['id'],'judgment_count':4,
        'relations':[{'neighbor_role':r['neighbor_role'],'neighbor_id':r['neighbor_id'],
                      'relation':r['classification']} for r in relations],
        'oracle_scope':'four frozen judgments only; not renderer or HumanEye output'}
    certificate={'schema':'private-spatial-perception-certificate-v1',
        'source_binding':source_binding,'world_geometry_sha256':hashlib.sha256(blob).hexdigest(),
        'oracle_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'exact_coordinate_model':'Fraction of every exported binary64 world coordinate; no rounding or epsilon snapping',
        'mesh_count':len(objects),'target_id':target['mesh']['id'],
        'target_uniqueness':{'rule':'unique actual closest frame to the lower hollow rail, behind unique front crossbeam, independently closest to dual uprights among lower frames',
            'lower_rail_id':lower_rail['id'],'front_crossbeam_id':front_beam['id'],
            'vertical_pipe_ids':[pipe['mesh']['id'] for pipe in pipes],
            'support_ranking_lower_bounds_m2':[{'object_id':i,'squared_distance':frac(d)} for d,i,_ in support_rank],
            'attaining_target_surface_witness':point_record(target_support),
            'attaining_rail_surface_witness':point_record(rail_support),
            'support_distance_mm':math.sqrt(float(distance2))*1000,
            'behind_front_beam_clearance_m':frac(tb[1][0]-front_beam['bounds'][1][1]),
            'lower_frame_dual_pipe_horizontal_squared_proximity':[{'object_id':i,'metric':frac(d)} for d,i in pipe_rank]},
        'frame_certificates':[{'object_id':ring['mesh']['id'],'world_mesh_sha256':mesh_digest(ring['mesh']),
                               **ring['certificate']} for ring in rings],
        'hollow_rail_certificates':[{'object_id':rail['original_mesh']['id'],
            'source_axes_to_certifier_axes':[1,0,2],**rail['certificate']} for rail in rails],
        'neighbor_certificates':neighbor_certificates,'relations':relations,
        'probe_crosscheck':{'probe_center':point_record(probe_center),
            'inside_original_probe':True,'inside_original_frame_material':False},
        'method_independence':'stdlib-only exact polygon/prism reconstruction and independent original-triangle ray parity; no HumanEye imports, intention labels, AABB-only penetration, or production algorithm outputs',
        'limitations':['frozen synthetic Y-extrusion domain only','contact label is a 0.25mm classification tolerance, not exact physical touching',
            'no global penetration-depth, visual visibility, camera fidelity, task-speed or real-asset value claim']}
    require(args.output_dir.resolve()==Path(__file__).resolve().parent,'oracle output must remain in private oracle directory')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,payload in (('ORACLE_PRIVATE.json',oracle),('CERTIFICATES_PRIVATE.json',certificate)):
        (args.output_dir/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':'certified','target_id':oracle['target_id'],'mesh_count':len(objects),
        'relations':[{'neighbor_id':r['neighbor_id'],'relation':r['classification'],
                      'minimum_distance_mm':r['minimum_distance_mm'],
                      'intersection_volume_m3':r['intersection_volume_m3']['float']} for r in relations],
        'files':['ORACLE_PRIVATE.json','CERTIFICATES_PRIVATE.json']},ensure_ascii=False))


if __name__=='__main__':
    main()
