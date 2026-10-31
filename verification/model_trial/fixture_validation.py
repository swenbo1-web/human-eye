"""Private fixture preflight from raw geometry and supplied native mask PNGs.

Standard library only; no engine, Blender, renderer or model imports. Geometry
feasibility is distinct from engine support and from actual host execution.
Mask provenance is the trusted owner's responsibility; image contents/counts
and ray geometry are independently checked here.
"""
from __future__ import annotations

import base64
import copy
from fractions import Fraction
import hashlib
from itertools import combinations
import math
import struct
import zlib

from . import oracle

VIEWS = {'XY':(0.,0.,1.), 'XZ':(0.,-1.,0.), 'SCENE':(1.,-1.,.75)}
RAY_MIN_M = 1e-7
BARYCENTRIC_EPS = 1e-10
MASK_MIN_ISOLATED_PIXELS = 16
SCENE_MAX_VISIBLE_FRACTION = .35
RECOVERY_MIN_VISIBLE_FRACTION = .70
CAMERA_FLOAT32_DIRECTION_EPS = 2e-6


def _number(x):
    return type(x) in (int,float) and math.isfinite(x)


def _vec(x):
    return type(x) in (list,tuple) and len(x)==3 and all(_number(v) for v in x)


def _sub(a,b): return [x-y for x,y in zip(a,b)]
def _dot(a,b): return math.fsum(x*y for x,y in zip(a,b))
def _cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _unit(v):
    length=math.hypot(*v)
    if not math.isfinite(length) or length<=1e-15: raise ValueError('invalid direction')
    return [x/length for x in v]


def _triangles(obj):
    vertices=obj['world_vertices']
    for face in obj['faces']:
        for i in range(1,len(face)-1):
            yield vertices[face[0]],vertices[face[i]],vertices[face[i+1]]


def ray_triangle_distance(point,direction,a,b,c):
    """Two-sided positive ray hit; explicit numerical boundary tolerance."""
    edge1,edge2=_sub(b,a),_sub(c,a)
    pvec=_cross(direction,edge2);det=_dot(edge1,pvec)
    scale=math.hypot(*edge1)*math.hypot(*edge2)
    if abs(det)<=max(1e-30,scale*1e-12): return None
    tvec=_sub(point,a);u=_dot(tvec,pvec)/det
    if u < -BARYCENTRIC_EPS or u > 1+BARYCENTRIC_EPS: return None
    qvec=_cross(tvec,edge1);v=_dot(direction,qvec)/det
    if v < -BARYCENTRIC_EPS or u+v > 1+BARYCENTRIC_EPS: return None
    distance=_dot(edge2,qvec)/det
    return distance if distance>RAY_MIN_M else None


def _camera(camera,view):
    if type(camera) is not dict: raise ValueError('missing owner camera')
    direction=camera.get('eye_direction',camera.get('direction_world'))
    center=camera.get('center',camera.get('center_world'))
    right,up=camera.get('camera_right'),camera.get('camera_up')
    if not all(_vec(v) for v in (direction,center,right,up)): raise ValueError('invalid camera vectors')
    direction,right,up=map(_unit,(direction,right,up))
    # Camera matrix/Euler readback is binary32 in Blender. This is an angular
    # metadata agreement bound, not the ray, geometry or pixel tolerance.
    if math.dist(direction,_unit(VIEWS[view]))>CAMERA_FLOAT32_DIRECTION_EPS: raise ValueError('camera is not the requested common view')
    if max(abs(_dot(a,b)) for a,b in combinations((direction,right,up),2))>CAMERA_FLOAT32_DIRECTION_EPS:
        raise ValueError('camera basis is not orthogonal')
    if _dot(_cross(right,up),direction)<1-CAMERA_FLOAT32_DIRECTION_EPS: raise ValueError('camera basis orientation invalid')
    span=camera.get('ortho_scale');width,height=camera.get('width'),camera.get('height')
    if not _number(span) or span<=0 or type(width) is not int or type(height) is not int or not 1<=width<=1024 or not 1<=height<=1024:
        raise ValueError('camera frame invalid')
    return {'eye_direction':direction,'center':list(center),'camera_right':right,
            'camera_up':up,'ortho_scale':span,'width':width,'height':height,
            'camera_direction_agreement_bound':CAMERA_FLOAT32_DIRECTION_EPS}


def sampled_visibility(native,camera,view):
    """Surface samples, excluding self-hidden rays; not a raster pixel claim."""
    cam=_camera(camera,view);direction=cam['eye_direction']
    objects=native['objects'];focal=objects['BluePart']
    vertices=focal['world_vertices']
    center=[math.fsum(v[k] for v in vertices)/len(vertices) for k in range(3)]
    triangles={name:list(_triangles(obj)) for name,obj in objects.items()}
    points=[]
    for a,b,c in triangles['BluePart']:
        centroid=[(a[k]+b[k]+c[k])/3 for k in range(3)]
        normal=_cross(_sub(b,a),_sub(c,a))
        if _dot(normal,_sub(centroid,center))<0:normal=[-x for x in normal]
        if _dot(normal,direction)<=max(1e-20,math.hypot(*normal)*1e-10):continue
        for weights in ((1/3,1/3,1/3),(.6,.2,.2),(.2,.6,.2),(.2,.2,.6)):
            points.append([math.fsum(weights[j]*p[k] for j,p in enumerate((a,b,c))) for k in range(3)])
    rows=[]
    for point in points:
        hits=[]
        for name,tris in triangles.items():
            distances=[hit for tri in tris if (hit:=ray_triangle_distance(point,direction,*tri)) is not None]
            if distances:hits.append((min(distances),name))
        own=next((distance for distance,name in hits if name=='BluePart'),None)
        if own is not None:continue
        external=min(hits,default=None)
        relative=_sub(point,cam['center'])
        px=(.5+_dot(relative,cam['camera_right'])/cam['ortho_scale'])*cam['width']
        py=(.5-_dot(relative,cam['camera_up'])/cam['ortho_scale'])*cam['height']
        rows.append({'point_world':point,'visible':external is None,
            'nearest_blocker':external[1] if external else None,
            'blocker_distance_m':external[0] if external else None,
            'within_frame':0<=px<cam['width'] and 0<=py<cam['height']})
    eligible=len(rows);visible=sum(row['visible'] for row in rows)
    return {'available':eligible>0,'sample_count':eligible,'visible_count':visible,
        'visible_fraction':visible/eligible if eligible else None,
        'external_blockers':sorted({r['nearest_blocker'] for r in rows if r['nearest_blocker']}),
        'all_samples_within_frame':bool(rows) and all(r['within_frame'] for r in rows),
        'ray_min_distance_m':RAY_MIN_M,'barycentric_epsilon':BARYCENTRIC_EPS,
        'scope':'finite sampled raw surface visibility, not pixels or all-surface proof','samples':rows}


def _paeth(a,b,c):
    p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c)
    return a if pa<=pb and pa<=pc else b if pb<=pc else c


def decode_red_mask(png):
    """Decode bounded noninterlaced RGB/RGBA8 PNG and classify red pixels."""
    if not isinstance(png,(bytes,bytearray)) or len(png)>16*1024*1024 or png[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ValueError('invalid bounded PNG')
    offset=8;header=None;compressed=[];ended=False
    while offset<len(png):
        if offset+12>len(png):raise ValueError('truncated PNG chunk')
        size=struct.unpack('>I',png[offset:offset+4])[0];kind=bytes(png[offset+4:offset+8])
        if size>16*1024*1024 or offset+12+size>len(png):raise ValueError('invalid PNG chunk length')
        data=bytes(png[offset+8:offset+8+size]);crc=struct.unpack('>I',png[offset+8+size:offset+12+size])[0]
        if zlib.crc32(kind+data)&0xffffffff!=crc:raise ValueError('PNG CRC mismatch')
        offset+=12+size
        if kind==b'IHDR':
            if header is not None or size!=13:raise ValueError('invalid PNG header')
            header=struct.unpack('>IIBBBBB',data)
        elif kind==b'IDAT':compressed.append(data)
        elif kind==b'IEND':ended=True;break
    if not ended or offset!=len(png) or header is None:raise ValueError('PNG incomplete or trailing data')
    width,height,bits,color,compression,filter_method,interlace=header
    if not (1<=width<=1024 and 1<=height<=1024 and bits==8 and color in (2,6)
            and compression==filter_method==interlace==0):raise ValueError('unsupported PNG layout')
    channels=3 if color==2 else 4;stride=width*channels;expected=(stride+1)*height
    decoder=zlib.decompressobj();raw=decoder.decompress(b''.join(compressed),expected+1)
    if len(raw)!=expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise ValueError('PNG decompression size mismatch')
    previous=bytearray(stride);mask=bytearray(width*height)
    for y in range(height):
        start=y*(stride+1);kind=raw[start];row=bytearray(raw[start+1:start+stride+1])
        if kind>4:raise ValueError('invalid PNG filter')
        for i in range(stride):
            a=row[i-channels] if i>=channels else 0;b=previous[i];c=previous[i-channels] if i>=channels else 0
            predictor=(0,a,b,(a+b)//2,_paeth(a,b,c))[kind]
            row[i]=(row[i]+predictor)&255
        for x in range(width):
            i=x*channels
            mask[y*width+x]=int(row[i]>127 and row[i+1]<64 and row[i+2]<64 and (channels==3 or row[i+3]>127))
        previous=row
    return {'width':width,'height':height,'red_pixels':sum(mask),'mask':bytes(mask),
            'sha256':hashlib.sha256(png).hexdigest(),
            'pixel_rule':'encoded PNG8 R>127,G<64,B<64,alpha>127'}


def mask_evidence(report,images=None):
    images=images or {}
    def supplied(which,key):
        value=images.get(which)
        if value is not None:return value
        encoded=report.get(key)
        if type(encoded) is not str:raise ValueError('native mask PNG missing')
        return base64.b64decode(encoded,validate=True)
    visible=decode_red_mask(supplied('visible','full_scene_png_base64'))
    isolated=decode_red_mask(supplied('isolated','focal_only_png_base64'))
    if (visible['width'],visible['height'])!=(isolated['width'],isolated['height']):
        raise ValueError('mask camera dimensions differ')
    for label,parsed in (('visible',visible),('isolated',isolated)):
        reported=report.get(label+'_mask_png_sha256')
        if reported is not None and reported!=parsed['sha256']:raise ValueError('native mask SHA mismatch')
    added=sum(a and not b for a,b in zip(visible['mask'],isolated['mask']))
    allowance=max(4,math.ceil(isolated['red_pixels']*.02))
    within=added<=allowance and visible['red_pixels']<=isolated['red_pixels']+allowance
    return {'available':isolated['red_pixels']>=MASK_MIN_ISOLATED_PIXELS,
        'visible_pixels':visible['red_pixels'],'isolated_pixels':isolated['red_pixels'],
        'occluded_pixels':max(0,isolated['red_pixels']-visible['red_pixels']),
        'visible_fraction':visible['red_pixels']/isolated['red_pixels'] if isolated['red_pixels'] else None,
        'unexpected_visible_pixels_outside_isolated':added,'subset_allowance_pixels':allowance,
        'full_mask_within_isolated':within,'width':visible['width'],'height':visible['height'],
        'visible_png_sha256':visible['sha256'],'isolated_png_sha256':isolated['sha256'],
        'pixel_rule':visible['pixel_rule'],'provenance_scope':'supplied native PNG bytes; owner/runner binds renderer and camera'}


def _rigid_prediction(native,target_m):
    gap=oracle.independent_gap(native);normal=_unit(native['normal'])
    if abs(normal[2])<1e-9:raise ValueError('world Z derivative unusable')
    dz=(target_m-gap)/normal[2];predicted=copy.deepcopy(native)
    focal=predicted['objects']['BluePart']
    focal['matrix'][2][3]+=dz
    for vertex in focal['world_vertices']:vertex[2]+=dz
    return predicted,dz


def _swept_box_separation(native,dz):
    """Sufficient fixed-axis interval check for the mathematical rigid sweep."""
    focal=native['objects']['BluePart'];rows=[]
    fa=[_unit([focal['matrix'][r][k] for r in range(3)]) for k in range(3)]
    for name,obj in native['objects'].items():
        if name=='BluePart':continue
        oa=[_unit([obj['matrix'][r][k] for r in range(3)]) for k in range(3)]
        certificate=None
        for axis in fa+oa+[_cross(a,b) for a in fa for b in oa]:
            length=math.hypot(*axis)
            if length<=1e-12:continue
            fp=[sum((Fraction(float(a))*Fraction(float(v)) for a,v in zip(axis,p)),Fraction()) for p in focal['world_vertices']]
            op=[sum((Fraction(float(a))*Fraction(float(v)) for a,v in zip(axis,p)),Fraction()) for p in obj['world_vertices']]
            shift=Fraction(float(axis[2]))*Fraction(float(dz))
            lower=min(fp)+min(Fraction(),shift);upper=max(fp)+max(Fraction(),shift)
            distance=max(min(op)-upper,lower-max(op))
            threshold=Fraction(oracle.SEPARATION_M)*Fraction(math.nextafter(length,math.inf))
            if distance>threshold:
                certificate={'axis_world':[x/length for x in axis],'minimum_interval_gap_m':float(distance)/length}
                break
        rows.append({'object':name,'separated_for_entire_mathematical_translation':certificate is not None,
                     'certificate':certificate})
    return {'passed':all(r['separated_for_entire_mathematical_translation'] for r in rows),
            'pairs':rows,'scope':'conservative raw-box rigid Z mathematical sweep only; not a host swept-path execution certificate'}


def validate_fixture(native,expected,visibility_reports=None,mask_pngs=None):
    """Fail-closed private validity report. Never selects replacement seeds."""
    result={'schema_version':1,'passed':False,'checks':{},'engine_support_assessed':False,
            'scope':'private fixture geometry/visibility preflight, not model benefit or engine support'}
    try:
        if type(expected) is not dict or expected.get('kind') not in ('goal','readonly','unsupported'):
            raise ValueError('expected.kind must be explicit')
        kind=expected['kind'];objects=native['objects'];checks=result['checks']
        if kind=='unsupported':
            refusal=oracle.score(native,copy.deepcopy(native),kind='unsupported',declared_status='unsupported')
            result['initial_oracle']=refusal
            checks['raw_negative_domain_and_zero_write_refusal_contract']=refusal['passed']
            which=expected.get('open_object')
            if which is not None:
                topology=refusal['domain']['initial']['objects'].get(which,{}).get('topology',{})
                checks['specified_target_geometry_actually_open']=topology.get('closed_two_incident_faces_per_edge') is False
            result['passed']=all(checks.values());return result
        gap=oracle.independent_gap(native)
        baseline=oracle.score(native,copy.deepcopy(native),kind='readonly',reported_gap_m=gap)
        result['initial_oracle']=baseline
        checks['initial_native_closed_domain_and_safe_endpoint']=baseline['passed']
        checks['initial_gap_in_3_to5mm_range']=.003-1e-6<=gap<=.005+1e-6
        if 'initial_gap_m' in expected:
            checks['manifest_gap_matches_native_projection']=_number(expected['initial_gap_m']) and abs(gap-expected['initial_gap_m'])<=1e-6
        if expected.get('dense'):
            checks['dense_actual_object_count_26']=len(objects)==26
        target=expected.get('target_m',.001)
        if not _number(target) or target<=0:raise ValueError('invalid target')
        predicted,dz=_rigid_prediction(native,target)
        endgap=oracle.independent_gap(predicted)
        endpoint=oracle.score(predicted,copy.deepcopy(predicted),kind='readonly',reported_gap_m=endgap)
        result.update(initial_gap_m=gap,predicted_world_z_translation_m=dz,
            conservative_steps_at_0_99mm=math.ceil(abs(dz)/.00099),predicted_endpoint_oracle=endpoint)
        checks['mathematical_target_endpoint_safe']=endpoint['passed'] and abs(endgap-target)<=1e-8
        checks['translation_within8mm_and8steps']=abs(dz)<=.008 and math.ceil(abs(dz)/.00099)<=8
        sweep=_swept_box_separation(native,dz);result['mathematical_sweep']=sweep
        checks['mathematical_z_corridor_separated']=sweep['passed']
        if kind=='readonly':checks['owner_permission_declares_readonly']=native.get('readonly') is True and native.get('allow_apply') is False
        if expected.get('occluded'):
            reports=visibility_reports or {};visibility={}
            for view in ('SCENE','XY','XZ'):
                report=reports.get(view)
                if type(report) is not dict:continue
                geometry=sampled_visibility(native,report.get('camera'),view)
                masks=mask_evidence(report,(mask_pngs or {}).get(view))
                cam=_camera(report.get('camera'),view)
                dimensions_match=(masks['width'],masks['height'])==(cam['width'],cam['height'])
                visibility[view]={'geometry':geometry,'native_masks':masks,'camera_dimensions_match':dimensions_match}
            result['visibility']=visibility
            def usable(view):
                entry=visibility.get(view,{})
                g,m=entry.get('geometry',{}),entry.get('native_masks',{})
                return bool(g.get('available') and g.get('all_samples_within_frame') and m.get('available')
                            and m.get('full_mask_within_isolated') and entry.get('camera_dimensions_match'))
            scene=visibility.get('SCENE',{})
            checks['scene_actual_png_and_raw_ray_external_occlusion']=(usable('SCENE')
                and scene['geometry']['visible_fraction']<=SCENE_MAX_VISIBLE_FRACTION
                and bool(scene['geometry']['external_blockers'])
                and scene['native_masks']['visible_fraction']<=SCENE_MAX_VISIBLE_FRACTION)
            checks['alternate_common_view_recovers_visibility']=any(usable(v)
                and visibility[v]['geometry']['visible_fraction']>=RECOVERY_MIN_VISIBLE_FRACTION
                and visibility[v]['native_masks']['visible_fraction']>=RECOVERY_MIN_VISIBLE_FRACTION for v in ('XY','XZ'))
            result['visibility_thresholds']={'scene_visible_fraction_max':SCENE_MAX_VISIBLE_FRACTION,
                'alternate_visible_fraction_min':RECOVERY_MIN_VISIBLE_FRACTION,
                'isolated_pixel_min':MASK_MIN_ISOLATED_PIXELS}
        result['passed']=bool(checks) and all(checks.values())
    except (TypeError,ValueError,KeyError,IndexError,AttributeError,OverflowError,ZeroDivisionError,struct.error,zlib.error) as exc:
        result['checks']['complete_valid_evidence']=False
        result['error']=type(exc).__name__+': '+str(exc)
    return result
