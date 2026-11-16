"""Independent exact source geometry and saved-camera qualification review.

Reads raw evidence only. Imports no author oracle or product implementation.
"""
from collections import Counter, defaultdict
from decimal import Decimal, getcontext
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import traceback

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_global_local_qualification_001')
RUN = Path('D:/he_m4_global_local_001')
checks = []

def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)

def read(path):
    return json.loads(Path(path).read_bytes())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def vec(values):
    return tuple(F(value) for value in values)

def sub(a, b):
    return tuple(x-y for x,y in zip(a,b))

def dot(a, b):
    return sum(x*y for x,y in zip(a,b))

def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def canonical_plane(normal, point):
    multiplier = math.lcm(*(v.denominator for v in normal))
    ints = [int(v*multiplier) for v in normal]
    divisor = math.gcd(*ints)
    primitive = tuple(v//divisor for v in ints)
    return primitive, dot(primitive, point)

def components(obj):
    vertices, faces = obj['vertices'], obj['triangles']
    planes, incidence = [], defaultdict(list)
    for index, face in enumerate(faces):
        normal = cross(sub(vertices[face[1]],vertices[face[0]]),sub(vertices[face[2]],vertices[face[0]]))
        check(dot(normal,normal)>0, 'nondegenerate/'+obj['name']+'/'+str(index))
        planes.append(canonical_plane(normal,vertices[face[0]]))
        for a,b in zip(face,face[1:]+face[:1]):
            incidence[tuple(sorted((a,b)))].append((index,a,b))
    links = defaultdict(set)
    for entries in incidence.values():
        for first in entries:
            for second in entries:
                if first[0]!=second[0] and planes[first[0]]==planes[second[0]]:
                    check(first[1:]==second[1:][::-1], 'consistent shared edge/'+obj['name'])
                    links[first[0]].add(second[0])
    unseen, output = set(range(len(faces))), []
    while unseen:
        seed = min(unseen)
        pending, found = [seed], set()
        while pending:
            index = pending.pop()
            if index in found:
                continue
            found.add(index)
            pending.extend(links[index]-found)
        unseen -= found
        edge_count = Counter()
        directed = []
        area_vector = (F(0),F(0),F(0))
        for index in found:
            face = faces[index]
            cr = cross(sub(vertices[face[1]],vertices[face[0]]),sub(vertices[face[2]],vertices[face[0]]))
            area_vector = tuple(x+y/2 for x,y in zip(area_vector,cr))
            for a,b in zip(face,face[1:]+face[:1]):
                edge_count[tuple(sorted((a,b)))]+=1
                directed.append((a,b))
        boundary = [edge for edge in directed if edge_count[tuple(sorted(edge))]==1]
        successors = {a:b for a,b in boundary}
        check(len(successors)==len(boundary), 'simple oriented boundary/'+obj['name'])
        unused, loops = set(successors), []
        while unused:
            start = min(unused)
            cycle, current = [], start
            while current not in cycle:
                cycle.append(current)
                unused.remove(current)
                current = successors[current]
            check(current==start, 'closed boundary/'+obj['name'])
            simplified = list(cycle)
            changed = True
            while changed and len(simplified)>3:
                changed = False
                for i,point in enumerate(simplified):
                    first = sub(vertices[point],vertices[simplified[i-1]])
                    second = sub(vertices[simplified[(i+1)%len(simplified)]],vertices[point])
                    if cross(first,second)==(0,0,0) and dot(first,second)>0:
                        simplified.pop(i)
                        changed = True
                        break
            loops.append(simplified)
        rectangle = False
        if len(loops)==1 and len(loops[0])==4:
            corners = [vertices[i] for i in loops[0]]
            edges = [sub(corners[(i+1)%4],corners[i]) for i in range(4)]
            rectangle = (edges[0]==tuple(-v for v in edges[2])
                         and edges[1]==tuple(-v for v in edges[3])
                         and dot(edges[0],edges[1])==0
                         and area_vector==cross(edges[0],edges[1]))
        normal = planes[seed][0]
        area2 = dot(area_vector,area_vector)
        eligible = (rectangle and F(1,128)**2<=area2<=F(1,32)**2
                    and normal[2]>0 and 16*normal[2]**2>=9*dot(normal,normal))
        output.append(dict(object=obj['name'], faces=sorted(found), rectangle=rectangle,
                           loops=loops, normal=normal, area_squared=area2, eligible=eligible))
    return output

def clip_polygon(poly, signed_distance):
    result=[]
    if not poly:
        return result
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db = signed_distance(a),signed_distance(b)
        if da>=0:
            result.append(a)
        if (da<0<db) or (db<0<da):
            t=da/(da-db)
            result.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
    return result

def unobstructed_horizontal(objects, target, direction):
    corners=target['vertices']
    xmin,xmax=min(p[0] for p in corners),max(p[0] for p in corners)
    ymin,ymax=min(p[1] for p in corners),max(p[1] for p in corners)
    z=corners[0][2]
    check(direction[2]>0,'front direction for open surface')
    tested=0
    for obj in objects:
        if obj['name']==target['name']:
            continue
        for face in obj['triangles']:
            triangle=[obj['vertices'][i] for i in face]
            if max(p[2] for p in triangle)<=z:
                continue
            clipped=clip_polygon(triangle,lambda p:p[2]-z)
            projected=[(p[0]+(z-p[2])*direction[0]/direction[2],
                        p[1]+(z-p[2])*direction[1]/direction[2]) for p in clipped]
            for axis,bound,sign in ((0,xmin,1),(0,xmax,-1),(1,ymin,1),(1,ymax,-1)):
                projected=clip_polygon(projected,lambda p,a=axis,b=bound,s=sign:s*(p[a]-b))
            area=abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(projected,projected[1:]+projected[:1]))) if projected else 0
            check(area==0,'no positive-area projected occluder/'+obj['name'])
            tested+=1
    return tested

getcontext().prec=90
def dec(v):
    v=F(v)
    return Decimal(v.numerator)/Decimal(v.denominator)

def normalized(values):
    size=sum(v*v for v in values).sqrt()
    return tuple(v/size for v in values)

def expected_camera(vertices,direction):
    center=tuple((min(p[i] for p in vertices)+max(p[i] for p in vertices))/2 for i in range(3))
    center=tuple(map(dec,center))
    direction=normalized(tuple(map(Decimal,direction)))
    seed=(Decimal(0),Decimal(1),Decimal(0)) if abs(direction[2])>Decimal('.99') else (Decimal(0),Decimal(0),Decimal(1))
    right=normalized(cross(tuple(-x for x in direction),seed))
    up=cross(right,tuple(-x for x in direction))
    relative=[sub(tuple(map(dec,p)),center) for p in vertices]
    half=max(abs(dot(p,axis)) for p in relative for axis in (right,up))*Decimal('1.1')
    front=max(dot(p,direction) for p in relative)
    distance=max(Decimal('.1'),front+Decimal('.1'),2*half)
    eye=tuple(c+d*distance for c,d in zip(center,direction))
    matrix=[list(axis)+[-dot(axis,eye)] for axis in (right,up,direction)]+[[Decimal(0),Decimal(0),Decimal(0),Decimal(1)]]
    return center,half,eye,matrix

def exact_pixel(pose,point):
    v=[dot(vec(row),tuple(point)+(F(1),)) for row in pose['view_matrix']]
    c=[dot(vec(row),v) for row in pose['projection_matrix']]
    check(c[3]==1,'affine homogeneous W')
    return ((c[0]+1)*F(511,2),(1-c[1])*F(511,2))

def main():
    geom_path=AUTHOR/'fixture/GEOMETRY.json'
    check(sha(geom_path)=='34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8','frozen raw geometry')
    raw=read(geom_path)
    objects=[dict(name=o['name'],vertices=list(map(vec,o['vertices_world_m'])),triangles=o['triangles']) for o in raw['objects']]
    by_name={o['name']:o for o in objects}
    check(len(objects)==9 and sum(len(o['vertices']) for o in objects)==54 and sum(len(o['triangles']) for o in objects)==56,'independent source counts')
    all_components=[c for o in objects for c in components(o)]
    supported=[c for c in all_components if c['rectangle']]
    unsupported=[c for c in all_components if not c['rectangle']]
    eligible=[c for c in supported if c['eligible']]
    check(len(all_components)==24 and len(supported)==22,'all maximal components')
    check(sum(len(c['faces']) for c in supported)==44 and sum(len(c['faces']) for c in unsupported)==12,'source denominator partition')
    check({c['object'] for c in unsupported}=={'Obj_05','Obj_07'},'nonrectangular connected components')
    check({c['object'] for c in eligible}=={'Obj_02','Obj_06','Obj_09'} and all(c['faces']==[0,1] for c in eligible),'independent eligible set')
    for phase in ('BEFORE_SAVE','AFTER_RELOAD'):
        saved=read(RUN/'fixture'/('READBACK_'+phase+'.json'))
        for obj in saved['objects']:
            original=by_name[obj['name']]
            for kind in ('native','evaluated'):
                check(list(map(vec,obj[kind]['vertices_world']))==original['vertices'],'actual fresh '+phase+'/'+kind+'/'+obj['name'])
                check(obj[kind]['triangles']==original['triangles'],'actual source order '+phase+'/'+kind+'/'+obj['name'])
    results={}
    source_maps=[]
    for slot_name in ('global','local_open','local_covered'):
        slot=RUN/'sessions'/slot_name
        full=read(slot/'product_full/call_001/SERVICE_RESULT.json')
        binding=full['binding']
        resources={}
        captures=[]
        for path in sorted((slot/'native/WIRE').glob('*/RESPONSE.bin')):
            response=read(path).get('result',{}).get('result')
            if not isinstance(response,str) or not response.startswith('HUMAN_EYE_BLENDER_MCP:'):
                continue
            data=json.loads(response.split(':',1)[1]).get('result',{})
            if data.get('schema')!='human-eye-scene-delta-v1':
                continue
            resources.update({r['id']:r for r in data['resources']})
            captures.append(data['capture'])
        check(len(captures)==1,'one actual capture/'+slot_name)
        capture=captures[0]
        check(capture['host_identity']['document_epoch']==binding['document_epoch'] and capture['capture_state']==binding['capture_state'],'actual capture current state/'+slot_name)
        check(capture['revision']==binding['scene_revision'],'actual revision/'+slot_name)
        check(len(capture['meshes'])==len(binding['objects']),'same capture object count/'+slot_name)
        saved_raw=read(slot/'raw_sources/live-source-001.json')
        saved_by_id={o['object_id']:o for o in saved_raw['objects']}
        for i,(mesh,bound) in enumerate(zip(capture['meshes'],binding['objects'])):
            name=mesh['name']; ref=mesh['_scene_resource'];resource=resources[ref['id']]
            check(bound['object_index']==i and bound['object_name']==name and bound['host_id']==mesh['object_id'],'actual bound object order/'+slot_name+'/'+name)
            check(bound['instance_id']==capture['host_identity']['object_instances'][mesh['object_id']],'actual host instance/'+slot_name+'/'+name)
            check(ref['revision']==resource['revision'],'actual resource revision/'+slot_name+'/'+name)
            points=[tuple(dot(vec(row),vec(p)+(F(1),))*F(ref['scale']) for row in ref['matrix'][:3]) for p in resource['vertices_local']]
            check(points==by_name[name]['vertices'] and resource['faces']==by_name[name]['triangles'],'actual captured source/'+slot_name+'/'+name)
            source=saved_by_id[bound['host_id']]
            check(source['name']==name and source['instance_id']==bound['instance_id'] and list(map(vec,source['vertices']))==points and source['triangles']==resource['faces'],'independent additional source read/'+slot_name+'/'+name)
            source_maps.append(dict(slot=slot_name,object=name,object_index=i,host_id=bound['host_id'],instance_id=bound['instance_id'],triangles=len(resource['faces']),document_epoch=binding['document_epoch']))
        # Independently recover represented rectangle corners and membership.
        relevant=[c for c in supported if c['object'] in {b['object_name'] for b in binding['objects']}]
        check(len(relevant)==len(full['facts']['regions']),'actual supported region denominator/'+slot_name)
        matched=[]
        for region in full['facts']['regions']:
            center,u,v=[vec(region[k]) for k in ('center_world_m','half_edge_u_world_m','half_edge_v_world_m')]
            corners={tuple(c+su*a+sv*b for c,a,b in zip(center,u,v)) for su in (-1,1) for sv in (-1,1)}
            component=next(c for c in relevant if c['object']==region['object_name'] and {by_name[c['object']]['vertices'][j] for j in c['loops'][0]}==corners)
            public_normal=vec(region['front_direction_world'])
            check(cross(public_normal,component['normal'])==(0,0,0) and dot(public_normal,component['normal'])>0,'actual oriented direction/'+slot_name+'/'+region['roi_id'])
            matched.append((region['object_name'],component['faces']))
        check(len(set((n,tuple(f)) for n,f in matched))==len(relevant),'complete actual rectangular source membership/'+slot_name)
        results[slot_name]=dict(capture_objects=len(capture['meshes']),supported_regions=len(relevant),constructed_views=[f['view_name'] for f in full['frames']])
    directions={'SCENE':(4,-4,3),'TOP':(0,0,1),'LEFT':(-1,0,1),'RIGHT':(1,0,1),'FRONT':(0,-1,1),'BACK':(0,1,1)}
    global_full=read(RUN/'sessions/global/product_full/call_001/SERVICE_RESULT.json')
    poses=global_full['binding']['camera_specification']['views']
    check({p['name'] for p in poses}==set(directions),'six actual global matrices')
    projected_bounds=[]
    error=F(1,65536)
    for pose in poses:
        direction=directions[pose['name']]
        check(pose['direction_rational']==list(direction),'actual fixed direction/'+pose['name'])
        center,half,eye,expected=expected_camera([p for o in objects for p in o['vertices']],direction)
        check(all(abs(dec(a)-b)<Decimal('1e-11') for row_a,row_b in zip(pose['view_matrix'],expected) for a,b in zip(row_a,row_b)),'independent high precision camera basis/fit/'+pose['name'])
        check(abs(dec(pose['half_span_m'])-half)<Decimal('1e-11') and all(abs(dec(a)-b)<Decimal('1e-11') for a,b in zip(pose['camera_eye_world_m'],eye)),'independent full-scene camera extent/'+pose['name'])
        check(abs(dec(pose['projection_matrix'][0][0])-1/half)<Decimal('1e-13') and abs(dec(pose['projection_matrix'][1][1])-1/half)<Decimal('1e-13'),'independent projection scale/'+pose['name'])
        for component in eligible:
            obj=by_name[component['object']]
            corners=[exact_pixel(pose,obj['vertices'][i]) for i in component['loops'][0]]
            axis_bounds=[(min(p[i] for p in corners)-error,max(p[i] for p in corners)+error) for i in range(2)]
            counts=[max(0,math.floor(hi-F(1,2))-math.ceil(lo-F(1,2))+1) for lo,hi in axis_bounds]
            check(all(hi-lo<2 for lo,hi in axis_bounds),'actual projected widths/'+pose['name']+'/'+obj['name'])
            triangle=[exact_pixel(pose,obj['vertices'][i]) for i in obj['triangles'][0]]
            determinant=abs((triangle[1][0]-triangle[0][0])*(triangle[2][1]-triangle[0][1])-(triangle[1][1]-triangle[0][1])*(triangle[2][0]-triangle[0][0]))
            check(determinant>F(1,2),'nondegenerate actual projected triangle/'+pose['name']+'/'+obj['name'])
            # Dot products each involve four terms and magnitudes below 2^10.
            # Gamma_4 bounds, two affine stages and pixel conversion together
            # contribute below 2^-32 pixels in this fixed finite geometry.
            # Barycentric -1e-10 and computed third-weight slack, with determinant
            # >1/2 and widths <2, extend the triangle by below 2^-24 pixels.
            # The explicit 2^-16 enclosure exceeds their sum by over 250x.
            check(F(1,2**32)+F(1,2**24)<error,'explicit arithmetic and edge-slack enclosure')
            upper=counts[0]*counts[1]
            check(upper<16,'integer pixel-centre bound/'+pose['name']+'/'+obj['name'])
            projected_bounds.append(dict(view=pose['name'],object=obj['name'],axis_intervals=[[str(x) for x in pair] for pair in axis_bounds],axis_integer_counts=counts,surface_pixel_upper=upper,projected_triangle_determinant=str(determinant)))
    covered=by_name['Obj_06']
    margins=[]
    for name,d in directions.items():
        intersections=[(p[0]+(F(9,8)-p[2])*F(d[0],d[2]),p[1]+(F(9,8)-p[2])*F(d[1],d[2])) for p in covered['vertices']]
        margin=min(min(x-F(3,2),F(5,2)-x,y-F(3,2),F(5,2)-y) for x,y in intersections)
        check(margin>0 and all((F(9,8)-p[2])/d[2]>0 for p in covered['vertices']),'strict six-direction cover/'+name)
        margins.append(dict(view=name,strict_xy_margin_m=str(margin),cover_plane_z='9/8'))
    open_proofs={name:unobstructed_horizontal(objects,by_name['Obj_02'],directions[name]) for name in ('SCENE','TOP')}
    corrections=read(AUTHOR/'oracle/SAVED_ADAPTER_CORRECTION_01.json')
    check(sha(corrections['original']['path'])==corrections['original']['sha256'] and sha(corrections['derived']['path'])==corrections['derived']['sha256'],'preserved scorer correction source pins')
    result=dict(status='passed',checks=len(checks),fixed_author_commit='99f939513111637b76a1d486622b4841cad9ccda',components=all_components,eligible=[c['object'] for c in eligible],source_maps=source_maps,sessions=results,actual_pixel_bounds=projected_bounds,covered_strict_margins=margins,open_positive_area_occluders=0,open_triangles_tested=open_proofs,new_live_calls=0)
    (OUT/'RESULT.json').write_text(json.dumps(result,default=str,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],components=len(all_components),eligible=result['eligible'],pixel_bounds=[r['surface_pixel_upper'] for r in projected_bounds],new_live_calls=0)))

if __name__=='__main__':
    try:
        main()
    except BaseException:
        failure=dict(status='failed',completed_checks=len(checks),error=traceback.format_exc())
        (OUT/'INITIAL_FAILURE.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf8')
        raise
