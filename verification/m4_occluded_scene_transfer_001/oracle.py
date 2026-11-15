"""Independent exact source geometry and saved raw-buffer arithmetic.

The oracle imports no product, discovery, image renderer or model code.
"""
from __future__ import annotations
import array
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

HERE=Path(__file__).resolve().parent
SHARED=HERE.with_name('m4_complete_witness_consumption_001')/'oracle.py'
spec=importlib.util.spec_from_file_location('_transfer_saved_buffer_decoders',SHARED)
shared=importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
read=shared.read
sha=shared.sha
npy=shared.npy
int32=shared.int32
png_rgb=shared.png_rgb
fraction=shared.fraction
matrix_vector=shared.matrix_vector


def scalar(value):
    if value.denominator==1:
        return value.numerator
    number=float(value)
    return number if Fraction.from_float(number)==value else str(value)


def vector(values):
    return [scalar(value) for value in values]


def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def add(a,b):
    return tuple(x+y for x,y in zip(a,b))


def mul(a,t):
    return tuple(x*t for x in a)


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def clip_polygon(points, signed):
    if not points:
        return []
    result=[]
    previous=points[-1]
    prev=signed(previous)
    for point in points:
        current=signed(point)
        if (current>=0)!=(prev>=0):
            ratio=prev/(prev-current)
            result.append(add(previous,mul(sub(point,previous),ratio)))
        if current>=0:
            result.append(point)
        previous,prev=point,current
    return result


def area2(points):
    if len(points)<3:
        return Fraction(0)
    return abs(sum(p[0]*q[1]-p[1]*q[0] for p,q in zip(points,points[1:]+points[:1])))/2


def shadow_on_rectangle(triangle,center,u,v,normal,direction):
    denominator=dot(normal,direction)
    distances=[dot(normal,sub(point,center))/denominator for point in triangle]
    if max(distances)<=0:
        return Fraction(0)
    nearer=clip_polygon(triangle,lambda p:dot(normal,sub(p,center))/denominator)
    if len(nearer)<3:
        return Fraction(0)
    projected=[]
    uu,vv=dot(u,u),dot(v,v)
    for point in nearer:
        t=dot(normal,sub(point,center))/denominator
        offset=sub(sub(point,mul(direction,t)),center)
        projected.append((dot(offset,u)/uu,dot(offset,v)/vv))
    for axis,sign in ((0,1),(0,-1),(1,1),(1,-1)):
        projected=clip_polygon(projected,lambda p,axis=axis,sign=sign:1+sign*p[axis])
    return area2(projected)


def source_regions(scene):
    regions=[]
    unsupported=[]
    source=[]
    offset=0
    box_quad_indices=((0,3,2,1),(4,5,6,7),(0,1,5,4),
                      (1,2,6,5),(2,3,7,6),(3,0,4,7))
    face_names=('bottom','top','front','right','back','left')
    if len(scene['objects'])!=12:
        raise ValueError('fixed_twelve_object_source_required')
    for obj_index,obj in enumerate(scene['objects']):
        points=[tuple(fraction(x) for x in p) for p in obj['vertices']]
        triangles=obj['triangles']
        for local,indices in enumerate(triangles):
            source.append(dict(object_index=obj_index,source_triangle_index=local,
                global_source_triangle_index=offset+local,
                vertices=tuple(points[i] for i in indices)))
        if obj_index<10:
            if len(points)!=8 or len(triangles)!=12:
                raise ValueError('registered_box_source_topology')
            quads=list(zip(face_names,box_quad_indices,[list(range(i,i+2)) for i in range(0,12,2)]))
        elif obj_index==10:
            if len(points)!=4 or triangles!=[[0,1,2],[0,2,3]]:
                raise ValueError('registered_slanted_rectangle_topology')
            quads=[('plate',(0,1,2,3),[0,1])]
        else:
            if obj['name']!='ConnectedLBracket' or triangles!=[[0,1,3],[1,2,3],[0,3,5],[3,4,5]]:
                raise ValueError('registered_connected_L_source_topology')
            unsupported.extend(dict(object_index=obj_index,object_name=obj['name'],
                source_triangle_index=i,global_source_triangle_index=offset+i,
                reason='connected_coplanar_component_is_not_a_rectangle') for i in range(len(triangles)))
            offset+=len(triangles)
            continue
        for label,quad_indices,faces in quads:
            quad=[points[i] for i in quad_indices]
            center=mul(add(quad[0],quad[2]),Fraction(1,2))
            u=mul(sub(quad[1],quad[0]),Fraction(1,2))
            v=mul(sub(quad[3],quad[0]),Fraction(1,2))
            normal=cross(u,v)
            if dot(u,v)!=0 or dot(u,u)==0 or dot(v,v)==0 or add(quad[0],quad[2])!=add(quad[1],quad[3]):
                raise ValueError('source_quad_must_be_exact_nondegenerate_rectangle')
            if set(triangles[faces[0]])|set(triangles[faces[1]])!=set(quad_indices):
                raise ValueError('source_triangle_quad_binding')
            triangle_normals=[cross(sub(points[triangles[i][1]],points[triangles[i][0]]),
                                    sub(points[triangles[i][2]],points[triangles[i][0]])) for i in faces]
            if any(dot(n,normal)<=0 or cross(n,normal)!=(0,0,0) for n in triangle_normals):
                raise ValueError('source_rectangle_front_winding')
            front=mul(normal,1/max(abs(x) for x in normal))
            identity=f'object_{obj_index:02d}_triangles_'+'_'.join(map(str,faces))
            regions.append(dict(region_id=identity,roi_id=identity,region_index=len(regions),
                object_index=obj_index,object_name=obj['name'],face_name=label,
                source_triangle_indices=faces,global_source_triangle_indices=[offset+i for i in faces],
                quad_world_m=[vector(p) for p in quad],center_world_m=vector(center),
                half_edge_u_world_m=vector(u),half_edge_v_world_m=vector(v),
                front_direction_world=vector(front),area_squared=scalar(16*dot(normal,normal)),views={}))
        offset+=len(triangles)
    return regions,unsupported,source


def geometry_truth(scene,cameras):
    regions,unsupported,triangles=source_regions(scene)
    directions={'SCENE':(4,-4,3),'TOP':(0,0,1),'LEFT':(-1,0,1),
                'RIGHT':(1,0,1),'FRONT':(0,-1,1),'BACK':(0,1,1)}
    if [p['name'] for p in cameras['views']]!=list(directions):
        raise ValueError('registered_six_camera_order')
    for pose in cameras['views']:
        if pose['direction_rational']!=list(directions[pose['name']]) or pose['size_px']!=[512,512]:
            raise ValueError('registered_direction_and_resolution')
        direction=tuple(map(Fraction,directions[pose['name']]))
        for region in regions:
            center=tuple(map(fraction,region['center_world_m']))
            u=tuple(map(fraction,region['half_edge_u_world_m']))
            v=tuple(map(fraction,region['half_edge_v_world_m']))
            normal=cross(u,v)
            front=dot(normal,direction)>0
            quad=[tuple(map(fraction,p)) for p in region['quad_world_m']]
            clips=[matrix_vector(pose['projection_matrix'],matrix_vector(pose['view_matrix'],p+(Fraction(1),))) for p in quad]
            inside=all(p[3]>0 and all(-p[3]<=p[k]<=p[3] for k in range(3)) for p in clips)
            shadows=[]
            if front:
                own=set(region['global_source_triangle_indices'])
                for tri in triangles:
                    if tri['global_source_triangle_index'] in own:
                        continue
                    area=shadow_on_rectangle(tri['vertices'],center,u,v,normal,direction)
                    if area>0:
                        shadows.append(dict(object_index=tri['object_index'],
                            source_triangle_index=tri['source_triangle_index'],
                            global_source_triangle_index=tri['global_source_triangle_index'],
                            positive_overlap_parameter_area=scalar(area)))
            total=sum((fraction(row['positive_overlap_parameter_area']) for row in shadows),Fraction(0))
            region['views'][pose['name']]=dict(front_facing=front,fully_in_view=inside,
                positive_shadow_area=scalar(total),
                shadow_area_unit='half-edge parameter-coordinate square units; overlapping triangles may be counted more than once',
                complete=front and inside and total==0,shadows=shadows)
    by_key={(r['object_index'],tuple(r['source_triangle_indices'])):r for r in regions}
    pixel_expected=[('sample_A',1,(2,3)),('sample_B',0,(10,11))]
    source_expected=[('target_C',0,(2,3)),('target_D',0,(0,1))]
    targets=lambda rows:[dict(id=name,object_index=obj,object_name=scene['objects'][obj]['name'],
        source_triangle_indices=list(faces),region_id=by_key[obj,faces]['region_id'],
        region_index=by_key[obj,faces]['region_index']) for name,obj,faces in rows]
    return dict(regions=regions,view_names=list(directions),supported_region_count=len(regions),
        source_triangle_count=len(triangles),source_triangle_object_indices=[row['object_index'] for row in triangles],
        unsupported_source_triangles=unsupported,pixel_targets=targets(pixel_expected),source_targets=targets(source_expected),
        thresholds=dict(surface_pixels=16,boundary_pixels=4,rgb_euclidean_contrast=24),
        scope='One fixed CAPTURE_REPLAY and six upper-hemisphere cameras. Geometry completeness is exact; actual readability remains unmeasured.',
        derivation='Each nearer source triangle is exactly clipped against the target plane, projected parallel to the rational view direction and clipped to the target rectangle. Any positive parameter-area shadow prevents completeness.')


def frame_pixels(frame,truth):
    native='NPZ' in frame
    array_path=Path(frame['NPZ'] if native else frame['arrays_path'])
    image_path=Path(frame['PNG'] if native else frame['image_path'])
    array_sha=frame['NPZ_sha256'] if native else frame['arrays_sha256']
    image_sha=frame['PNG_sha256'] if native else frame['image_sha256']
    if sha(array_path)!=array_sha or sha(image_path)!=image_sha:
        raise ValueError('actual_frame_file_hash_mismatch')
    payload={}
    with zipfile.ZipFile(array_path) as archive:
        if set(archive.namelist())!={name+'.npy' for name in frame['arrays']}:
            raise ValueError('actual_array_member_set')
        for name,meta in frame['arrays'].items():
            head,data=npy(archive.read(name+'.npy'))
            if hashlib.sha256(data).hexdigest()!=meta['sha256'] or len(data)!=meta['nbytes'] or list(head['shape'])!=meta['shape']:
                raise ValueError('actual_array_metadata_mismatch:'+name)
            payload[name]=(head,data)
    for name in ('triangle_ids','owners'):
        if payload[name][0]['descr'] not in ('<i4','=i4') or payload[name][0]['shape']!=(512,512):
            raise ValueError('source_owner_array_schema:'+name)
    rgb=payload['color'][1]
    if payload['color'][0]['shape']!=(512,512,3) or payload['color'][0]['descr']!='|u1':
        raise ValueError('actual_RGB_schema')
    if png_rgb(image_path)!=rgb:
        raise ValueError('published_PNG_differs_from_actual_RGB_buffer')
    raw=int32(payload['triangle_ids'][1])
    owners=int32(payload['owners'][1])
    count=len(raw)
    size=len(truth['regions'])
    surface=[0]*size
    boundary=[0]*size
    bounds=[None]*size
    edge=bytearray(count)
    lookup={face:r['region_index'] for r in truth['regions'] for face in r['global_source_triangle_indices']}
    unsupported={r['global_source_triangle_index'] for r in truth['unsupported_source_triangles']}
    all_objects=truth['source_triangle_object_indices']
    region=[-1]*count
    for pos,source in enumerate(raw):
        if source>=0:
            if source>=len(all_objects) or owners[pos]!=all_objects[source]:
                raise ValueError('independent_raw_object_relation')
            idx=lookup.get(source)
            if idx is None:
                if source not in unsupported:
                    raise ValueError('unregistered_source_triangle')
                region[pos]=-2
                continue
            region[pos]=idx
            x,y=pos%512,pos//512
            surface[idx]+=1
            b=bounds[idx]
            bounds[idx]=[x,y,x,y] if b is None else [min(b[0],x),min(b[1],y),max(b[2],x),max(b[3],y)]
        elif source!=-1 or owners[pos]!=-1:
            raise ValueError('background_source_owner_relation')
    for pos in range(count):
        neighbors=([pos+1] if pos%512<511 else [])+([pos+512] if pos<count-512 else [])
        for other in neighbors:
            if region[pos]!=region[other] and sum((rgb[3*pos+k]-rgb[3*other+k])**2 for k in range(3))>=576:
                edge[pos]=edge[other]=1
    best=[None]*size
    anchor=[None]*size
    for pos,idx in enumerate(region):
        if idx<0:
            continue
        if edge[pos]:
            boundary[idx]+=1
        x,y=pos%512,pos//512
        b=bounds[idx]
        distance=(2*x-b[0]-b[2])**2+(2*y-b[1]-b[3])**2
        if best[idx] is None or distance<best[idx]:
            best[idx]=distance
            anchor[idx]=[x,y]
    rows=[]
    for r in truth['regions']:
        idx=r['region_index']
        g=r['views'][frame['view_name']]
        readable=g['front_facing'] and surface[idx]>=16 and boundary[idx]>=4
        rows.append(dict(roi_id=r['roi_id'],region_id=r['region_id'],region_index=idx,
            object_index=r['object_index'],view=frame['view_name'],surface_pixels=surface[idx],
            boundary_pixels=boundary[idx],front_facing=g['front_facing'],readable=readable,
            complete=g['complete'],complete_readable=g['complete'] and readable,
            bounds=bounds[idx],anchor=anchor[idx]))
    return dict(view_name=frame['view_name'],image_ref=frame['ref'] if native else frame['image_ref'],
        rows=rows,raw_region_by_pixel=region,origin='native' if native else 'product')
