"""Independent fixed-case geometry and saved-buffer arithmetic; stdlib only."""

import array
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar(value):
    return value.numerator if value.denominator==1 else str(value)


def vector(values):
    return [scalar(value) for value in values]


def fraction(value):
    return Fraction.from_float(value) if type(value) is float else Fraction(value)


def matrix_vector(matrix, point):
    return tuple(sum(fraction(a)*b for a,b in zip(row,point)) for row in matrix)


def geometry_truth(scene,cameras):
    names=[obj['name'] for obj in scene['objects']]
    if names!=['Panel_A','Panel_B']:
        raise ValueError('registered_two_rectangle_source_required')
    expected=[((-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)),((3,-5,3),(5,-5,3),(5,-3,3),(3,-3,3))]
    regions=[]
    offset=0
    for index,obj in enumerate(scene['objects']):
        points=[tuple(fraction(v) for v in p) for p in obj['vertices']]
        if points!=[tuple(map(Fraction,p)) for p in expected[index]] or obj['triangles']!=[[0,1,2],[0,2,3]]:
            raise ValueError('fixed_case_geometry_changed')
        x0,y0,z=points[0];x1,y1,_=points[2]
        area=(x1-x0)*(y1-y0)
        roi='roi_'+hashlib.sha256(json.dumps(points,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
        regions.append(dict(roi_id=roi,object_index=index,object_name=obj['name'],source_triangle_indices=[0,1],
            global_source_triangle_indices=[offset,offset+1],quad_world_m=[vector(p) for p in points],
            center_world_m=vector([(points[0][k]+points[2][k])/2 for k in range(3)]),
            half_edge_u_world_m=vector([(points[1][k]-points[0][k])/2 for k in range(3)]),
            half_edge_v_world_m=vector([(points[3][k]-points[0][k])/2 for k in range(3)]),
            front_direction_world=[0,0,1],area=scalar(area),views={}))
        offset+=2
    required=['SCENE','TOP','LEFT','RIGHT','FRONT','BACK']
    directions=[(4,-4,3),(0,0,1),(-1,0,1),(1,0,1),(0,-1,1),(0,1,1)]
    if [view['name'] for view in cameras['views']]!=required:
        raise ValueError('registered_camera_order_required')
    for view,direction in zip(cameras['views'],directions):
        if view['direction_rational']!=list(direction) or view['size_px']!=[512,512]:
            raise ValueError('registered_camera_direction_size_required')
        for index,region in enumerate(regions):
            points=[tuple(fraction(v) for v in p) for p in region['quad_world_m']]
            clips=[matrix_vector(view['projection_matrix'],matrix_vector(view['view_matrix'],p+(Fraction(1),))) for p in points]
            inside=all(p[3]>0 and all(-p[3]<=p[k]<=p[3] for k in range(3)) for p in clips)
            shadow=Fraction(0)
            shadows=[]
            target_z=points[0][2]
            for other_index,other in enumerate(regions):
                if other_index==index:
                    continue
                q=[tuple(fraction(v) for v in p) for p in other['quad_world_m']]
                delta=q[0][2]-target_z
                if delta<=0:
                    continue
                shifted=[(p[0]-delta*direction[0]/direction[2],p[1]-delta*direction[1]/direction[2]) for p in q]
                left=max(points[0][0],min(p[0] for p in shifted));right=min(points[2][0],max(p[0] for p in shifted))
                bottom=max(points[0][1],min(p[1] for p in shifted));top=min(points[2][1],max(p[1] for p in shifted))
                overlap=max(Fraction(0),right-left)*max(Fraction(0),top-bottom)
                shadow+=overlap
                shadows.append(dict(occluder_object_index=other_index,projected_quad_xy=[vector(p) for p in shifted],overlap_area=scalar(overlap)))
            front=direction[2]>0
            region['views'][view['name']]=dict(front_facing=front,fully_in_view=inside,
                positive_shadow_area=scalar(shadow),complete=front and inside and shadow==0,shadows=shadows)
    if regions[0]['views']['SCENE']['positive_shadow_area']!=4 or not all(regions[0]['views'][v]['complete'] for v in required[1:]):
        raise ValueError('independent_fixed_case_shadow_derivation_failed')
    return dict(regions=regions,view_names=required,target_object_name='Panel_A',target_roi_id=regions[0]['roi_id'],
                supported_region_count=2,source_triangle_count=4,unsupported_source_triangles=[],
                thresholds=dict(surface_pixels=16,boundary_pixels=4,rgb_euclidean_contrast=24),
                scope='Registered six-camera pool and fixed two horizontal rectangles only. Readability is not predicted.')


def npy(raw):
    if raw[:6]!=b'\x93NUMPY':
        raise ValueError('NPY_magic')
    length_bytes=2 if raw[6]==1 else 4
    length=int.from_bytes(raw[8:8+length_bytes],'little')
    start=8+length_bytes
    header=ast.literal_eval(raw[start:start+length].decode('latin1'))
    if header['fortran_order']:
        raise ValueError('C_order_arrays_required')
    return header,raw[start+length:]


def int32(data):
    values=array.array('i');values.frombytes(data)
    if sys.byteorder!='little':
        values.byteswap()
    return values


def png_rgb(path):
    raw=Path(path).read_bytes()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ValueError('actual_PNG_signature')
    position=8;compressed=bytearray();dimensions=None
    while position<len(raw):
        length=int.from_bytes(raw[position:position+4],'big');kind=raw[position+4:position+8]
        data=raw[position+8:position+8+length];crc=int.from_bytes(raw[position+8+length:position+12+length],'big')
        if zlib.crc32(kind+data)&0xffffffff!=crc:
            raise ValueError('actual_PNG_CRC')
        if kind==b'IHDR':
            width,height,depth,color,compression,filter_method,interlace=struct.unpack('>IIBBBBB',data)
            if (width,height,depth,color,compression,filter_method,interlace)!=(512,512,8,2,0,0,0):
                raise ValueError('actual_PNG_RGB_schema')
            dimensions=(width,height)
        elif kind==b'IDAT':
            compressed.extend(data)
        position+=length+12
        if kind==b'IEND':
            break
    if dimensions is None:
        raise ValueError('actual_PNG_dimensions_missing')
    data=zlib.decompress(compressed);stride=512*3
    if len(data)!=512*(stride+1):
        raise ValueError('actual_PNG_scanline_size')
    result=bytearray();previous=bytearray(stride)
    for y in range(512):
        offset=y*(stride+1);filter_type=data[offset];row=bytearray(data[offset+1:offset+1+stride])
        for x in range(stride):
            left=row[x-3] if x>=3 else 0;up=previous[x];upper_left=previous[x-3] if x>=3 else 0
            if filter_type==0:
                predictor=0
            elif filter_type==1:
                predictor=left
            elif filter_type==2:
                predictor=up
            elif filter_type==3:
                predictor=(left+up)//2
            elif filter_type==4:
                p=left+up-upper_left;a=abs(p-left);b=abs(p-up);c=abs(p-upper_left)
                predictor=left if a<=b and a<=c else up if b<=c else upper_left
            else:
                raise ValueError('actual_PNG_filter')
            row[x]=(row[x]+predictor)&255
        result.extend(row);previous=row
    return bytes(result)


def frame_pixels(frame,truth):
    path=Path(frame['arrays_path'])
    if sha(path)!=frame['arrays_sha256'] or sha(frame['image_path'])!=frame['image_sha256']:
        raise ValueError('actual_frame_file_hash_mismatch')
    payload={}
    with zipfile.ZipFile(path) as archive:
        for name,meta in frame['arrays'].items():
            head,data=npy(archive.read(name+'.npy'))
            if hashlib.sha256(data).hexdigest()!=meta['sha256'] or len(data)!=meta['nbytes'] or list(head['shape'])!=meta['shape']:
                raise ValueError('actual_array_metadata_mismatch:'+name)
            payload[name]=(head,data)
    for name in ('triangle_ids','owners','patch_owners'):
        if payload[name][0]['descr'] not in ('<i4','=i4') or payload[name][0]['shape']!=(512,512):
            raise ValueError('source_owner_array_schema:'+name)
    rgb=payload['color'][1]
    if payload['color'][0]['shape']!=(512,512,3) or payload['color'][0]['descr']!='|u1':
        raise ValueError('actual_RGB_schema')
    if png_rgb(frame['image_path'])!=rgb:
        raise ValueError('published_PNG_differs_from_actual_RGB_buffer')
    raw=int32(payload['triangle_ids'][1]);owners=int32(payload['owners'][1]);patch=int32(payload['patch_owners'][1])
    count=len(raw);surface=[0,0];boundary=[0,0];bounds=[None,None];edge=bytearray(count)
    by_raw={face:r['object_index'] for r in truth['regions'] for face in r['global_source_triangle_indices']}
    region=[-1]*count
    roi_order=payload['patch_roi_ids'][1].decode('utf-32-le');width=int(payload['patch_roi_ids'][0]['descr'][2:]);roi_order=[roi_order[i*width:(i+1)*width].rstrip('\x00') for i in range(2)]
    if set(roi_order)!={r['roi_id'] for r in truth['regions']}:
        raise ValueError('actual_patch_order_identity')
    patch_for_object={r['object_index']:roi_order.index(r['roi_id']) for r in truth['regions']}
    for pos,source in enumerate(raw):
        if source>=0:
            obj=by_raw[source];region[pos]=obj
            if owners[pos]!=obj or patch[pos]!=patch_for_object[obj]:
                raise ValueError('independent_raw_object_patch_relation')
            x=pos%512;y=pos//512;surface[obj]+=1;b=bounds[obj]
            bounds[obj]=[x,y,x,y] if b is None else [min(b[0],x),min(b[1],y),max(b[2],x),max(b[3],y)]
        elif source!=-1 or owners[pos]!=-1 or patch[pos]!=-1:
            raise ValueError('background_source_owner_relation')
    for pos in range(count):
        for other in ([pos+1] if pos%512<511 else [])+([pos+512] if pos<count-512 else []):
            if region[pos]!=region[other] and sum((rgb[3*pos+k]-rgb[3*other+k])**2 for k in range(3))>=576:
                edge[pos]=edge[other]=1
    best=[None,None];anchor=[None,None]
    for pos,obj in enumerate(region):
        if obj<0:
            continue
        if edge[pos]:
            boundary[obj]+=1
        x=pos%512;y=pos//512;b=bounds[obj];distance=(2*x-b[0]-b[2])**2+(2*y-b[1]-b[3])**2
        if best[obj] is None or distance<best[obj]:
            best[obj]=distance;anchor[obj]=[x,y]
    rows=[]
    for region_truth in truth['regions']:
        obj=region_truth['object_index'];geometry=region_truth['views'][frame['view_name']]
        readable=geometry['front_facing'] and surface[obj]>=16 and boundary[obj]>=4
        rows.append(dict(roi_id=region_truth['roi_id'],object_index=obj,view=frame['view_name'],
            surface_pixels=surface[obj],boundary_pixels=boundary[obj],front_facing=geometry['front_facing'],
            readable=readable,complete=geometry['complete'],complete_readable=geometry['complete'] and readable,
            bounds=bounds[obj],anchor=anchor[obj]))
    return dict(view_name=frame['view_name'],image_ref=frame['image_ref'],rows=rows,raw_region_by_pixel=region)
