"""Typed read-only native observation validation; no action authority.

Pure standard-library validation of trusted native transport responses. Pixel
projection and frame predicates retain the previously tested common gateway
contract. Nothing here imports a test harness or dispatches a host operation.
"""
from __future__ import annotations
import base64,copy,hashlib,json,math,struct,zlib

RENDER_AUDIT_PROTOCOL='owned-native-render-audit-v1-20261031'
MULTISCALE_PROTOCOL='owned-native-multiscale-v1-20261031'
READONLY_OBSERVATION_PROTOCOL='typed-native-readonly-observation-v1-20261031'
READONLY_BUDGET_SCOPE='per_call_readonly_observation_lease_deadline'
_MAX_MULTISCALE_PNG_BYTES=16*1024*1024
_OBJECT_KEYS=('object_id','name','local_vertices','world_vertices','faces','matrix','color')
_RENDER_STATE_SCOPE='render-helper-assigned-and-implicitly-dependent-scalars-camera-assets-selection'


def _require(value,reason):
    if not value:raise ValueError(reason)


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8')


def _digest(value):return hashlib.sha256(_json(value)).hexdigest()


def _finite(value):
    try:return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:return False


def _vector(value,size):return type(value) is list and len(value)==size and all(_finite(x) for x in value)


def _public_native_png(raw):
    """Project a complete PNG to pixels and supported numeric color chunks.

    Native renderer text/EXIF/time chunks may contain the private .blend path.
    The retained chunks are copied byte for byte, including IDAT and alpha.
    Corrupt or unsupported critical/profile data is refused, never repaired.
    """
    signature=b'\x89PNG\r\n\x1a\n'
    _require(type(raw) is bytes and len(raw)<=8*1024*1024 and raw.startswith(signature),
        'common_native_png_invalid')
    kept=[signature];position=8;seen=set();idat=False;idat_ended=False;ended=False;color=None;palette_entries=None
    numeric_lengths={b'sRGB':1,b'gAMA':4,b'cHRM':32,b'sBIT':None,b'bKGD':None}
    while position<len(raw):
        _require(len(raw)-position>=12,'common_native_png_truncated')
        size=struct.unpack('>I',raw[position:position+4])[0]
        kind=raw[position+4:position+8];stop=position+12+size
        _require(stop<=len(raw) and all(65<=x<=90 or 97<=x<=122 for x in kind),
            'common_native_png_chunk_invalid')
        payload=raw[position+8:position+8+size]
        expected=struct.unpack('>I',raw[position+8+size:stop])[0]
        _require((zlib.crc32(kind+payload)&0xffffffff)==expected,'common_native_png_crc_invalid')
        _require((position==8)==(kind==b'IHDR') and not ended,'common_native_png_order_invalid')
        retain=False
        if kind==b'IHDR':
            _require(size==13,'common_native_png_header_invalid')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',payload)
            depths={0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}
            _require(width>0 and height>0 and color in depths and depth in depths[color]
                and compression==filtering==0 and interlace in (0,1),'common_native_png_header_invalid')
            retain=True
        elif kind==b'PLTE':
            _require(not idat and kind not in seen and 0<size<=768 and size%3==0
                and color not in (0,4),'common_native_png_palette_invalid')
            palette_entries=size//3;retain=True
        elif kind==b'IDAT':
            _require(not idat_ended and (color!=3 or b'PLTE' in seen),'common_native_png_idat_order_invalid')
            idat=True;retain=True
        elif kind==b'IEND':
            _require(size==0 and idat and stop==len(raw),'common_native_png_end_invalid')
            ended=True;retain=True
        elif kind==b'tRNS':
            _require(not idat and kind not in seen and (
                color==0 and size==2 or color==2 and size==6
                or color==3 and palette_entries is not None and 0<size<=palette_entries),
                'common_native_png_alpha_invalid')
            retain=True
        elif kind==b'iCCP':
            # An arbitrary ICC blob can carry free text. Dropping it could
            # alter color interpretation; reject this unsupported case.
            raise ValueError('common_native_png_icc_profile_requires_separate_public_contract')
        elif kind in numeric_lengths:
            _require(not idat and kind not in seen,'common_native_png_color_order_invalid')
            expected_size=numeric_lengths[kind]
            if kind==b'sBIT':expected_size={0:1,2:3,3:3,4:2,6:4}[color]
            if kind==b'bKGD':expected_size={0:2,2:6,3:1,4:2,6:6}[color]
            _require(size==expected_size,'common_native_png_color_invalid')
            if kind==b'sRGB':_require(payload[0]<=3,'common_native_png_srgb_invalid')
            if kind==b'gAMA':_require(struct.unpack('>I',payload)[0]>0,'common_native_png_gamma_invalid')
            if kind==b'bKGD' and color==3:
                _require(palette_entries is not None and payload[0]<palette_entries,'common_native_png_background_invalid')
            retain=True
        else:
            # Uppercase first byte denotes an unknown critical chunk.
            _require(kind[0]&32,'common_native_png_critical_chunk_unsupported')
        if idat and kind!=b'IDAT':idat_ended=True
        if retain:kept.append(raw[position:stop])
        seen.add(kind);position=stop
    _require(ended,'common_native_png_end_missing')
    return b''.join(kept)


def _public_query(raw, *, minimum_objects=2):
    _require(type(raw) is dict and raw.get('unit')=='m' and raw.get('coordinate_frame')=='world',
             'complete_common_native_query_required')
    _require(type(raw.get('revision')) is str and bool(raw['revision']), 'native_revision_required')
    objects=raw.get('objects');_require(type(objects) is list and minimum_objects<=len(objects)<=256,'complete_native_objects_required')
    result=[];ids=set()
    for obj in objects:
        _require(type(obj) is dict and set(_OBJECT_KEYS)<=set(obj),'complete_native_object_fields_required')
        _require(type(obj['object_id']) is str and obj['object_id'] not in ids,'unique_native_object_ids_required')
        _require(type(obj['name']) is str,'native_object_name_required');ids.add(obj['object_id'])
        _require(type(obj['matrix']) is list and len(obj['matrix'])==4
            and all(_vector(row,4) for row in obj['matrix']),'native_matrix_invalid')
        _require(_vector(obj['color'],4),'native_color_invalid')
        vertices=obj['local_vertices'];world=obj['world_vertices'];faces=obj['faces']
        _require(type(vertices) is list and type(world) is list and 3<=len(vertices)==len(world)<=100000
            and all(_vector(point,3) for point in vertices) and all(_vector(point,3) for point in world),
            'native_vertices_invalid')
        _require(type(faces) is list and 1<=len(faces)<=200000
            and all(type(face) is list and 3<=len(face)<=len(vertices)
                and all(type(i) is int and 0<=i<len(vertices) for i in face) for face in faces),'native_faces_invalid')
        result.append({key:copy.deepcopy(obj[key]) for key in _OBJECT_KEYS})
    value={'unit':'m','coordinate_frame':'world','revision':raw['revision'],'objects':result}
    _json(value)
    return value


def _validate_private_render_state(value, expected_mesh_names, *, minimum_objects=2):
    """Validate complete typed readback, without projecting it to model data."""
    fields={'schema_version','scope','scene_camera','scene_objects','global_objects','camera_datablocks',
        'active_object','selection','render','shading','image_settings','view_settings',
        'image_color_management','scene_display_settings','execution_authority'}
    _require(type(value) is dict and set(value)==fields
        and value['schema_version']=='native-render-state-v1' and value['scope']==_RENDER_STATE_SCOPE
        and value['execution_authority'] is False, 'native_render_state_fields_incomplete')
    def identity(item, nullable=False):
        if item is None:
            _require(nullable, 'native_render_state_identity_required');return
        keys={'name','session_uid','pointer','identity_kind','test_object_id'}
        _require(type(item) is dict and set(item)==keys and type(item['name']) is str
            and len(item['name'])<=4096 and item['identity_kind'] in ('blender_rna','injectable_test_object'),
            'native_render_state_identity_invalid')
        for key in ('session_uid','pointer','test_object_id'):
            _require(item[key] is None or type(item[key]) is int and item[key]>=0,
                'native_render_state_identity_number_invalid')
    def inventory(items, objects=False):
        _require(type(items) is list and len(items)<=10000, 'native_render_state_inventory_required')
        for row in items:
            _require(type(row) is dict and set(row)==({'identity','type','data'} if objects else {'identity'}),
                'native_render_state_inventory_row_invalid')
            identity(row['identity'])
            if objects:
                _require(type(row['type']) is str,'native_render_state_object_type_invalid')
                identity(row['data'],nullable=True)
    inventory(value['scene_objects'],objects=True);inventory(value['global_objects'],objects=True)
    inventory(value['camera_datablocks'])
    _require(len(value['scene_objects'])>=minimum_objects, 'native_render_scene_inventory_empty')
    names={row['identity']['name'] for row in value['scene_objects']}
    _require(set(expected_mesh_names)<=names, 'native_render_scene_mesh_coverage_incomplete')
    global_ids={_json(row['identity']) for row in value['global_objects']}
    scene_ids={_json(row['identity']) for row in value['scene_objects']}
    _require(scene_ids<=global_ids, 'native_render_global_inventory_incomplete')
    identity(value['active_object'],nullable=True)
    if value['active_object'] is not None:
        _require(_json(value['active_object']) in scene_ids, 'native_render_active_object_not_in_scene')
    selection=value['selection']
    _require(type(selection) is list and len(selection)==len(value['scene_objects']),
        'native_render_selection_coverage_incomplete')
    selected_ids=[]
    for row in selection:
        _require(type(row) is dict and set(row)=={'object','selected'} and type(row['selected']) is bool,
            'native_render_selection_row_invalid')
        identity(row['object']);selected_ids.append(_json(row['object']))
    _require(len(set(selected_ids))==len(selected_ids) and set(selected_ids)==scene_ids,
        'native_render_selection_identities_incomplete')
    camera=value['scene_camera']
    if camera is not None:
        _require(type(camera) is dict and set(camera)=={'identity','data','matrix_world','data_settings'},
            'native_render_camera_fields_incomplete')
        identity(camera['identity']);identity(camera['data'])
        _require(_json(camera['identity']) in scene_ids and _json(camera['data']) in
            {_json(row['identity']) for row in value['camera_datablocks']}, 'native_render_camera_inventory_incomplete')
        _require(type(camera['matrix_world']) is list and len(camera['matrix_world'])==4
            and all(_vector(row,4) for row in camera['matrix_world']), 'native_render_camera_matrix_invalid')
        _require(type(camera['data_settings']) is dict and bool(camera['data_settings']),
            'native_render_camera_settings_incomplete')
    render=value['render'];shade=value['shading']
    _require(type(render) is dict and set(render)=={'engine','resolution_x','resolution_y',
        'resolution_percentage','filepath','film_transparent','pixel_aspect_x','pixel_aspect_y',
        'use_border','use_crop_to_border','border_min_x','border_max_x','border_min_y','border_max_y'},
        'native_render_settings_incomplete')
    _require(type(render['engine']) is str and type(render['filepath']) is str
        and type(render['film_transparent']) is bool and all(type(render[k]) is int and render[k]>0
            for k in ('resolution_x','resolution_y','resolution_percentage'))
        and all(_finite(render[k]) and render[k]>0 for k in ('pixel_aspect_x','pixel_aspect_y'))
        and all(type(render[k]) is bool for k in ('use_border','use_crop_to_border'))
        and all(_finite(render[k]) and 0<=render[k]<=1
            for k in ('border_min_x','border_max_x','border_min_y','border_max_y')),
        'native_render_settings_invalid')
    _require(type(shade) is dict and set(shade)=={'light','color_type','background_type','background_color',
        'show_shadows','show_cavity','show_object_outline'}, 'native_render_shading_incomplete')
    _require(all(type(shade[k]) is str for k in ('light','color_type','background_type'))
        and _vector(shade['background_color'],3) and all(type(shade[k]) is bool
            for k in ('show_shadows','show_cavity','show_object_outline')), 'native_render_shading_invalid')
    color=value['image_color_management']
    _require(type(color) is dict and set(color)<={'linear_colorspace_settings','display_settings','view_settings'},
        'native_render_color_management_fields_invalid')
    mappings=[(value['image_settings'],{'file_format'}),(value['view_settings'],{'view_transform'}),
        (value['scene_display_settings'],set())]
    mappings.extend((mapping,set()) for mapping in color.values())
    if camera is not None:mappings.append((camera['data_settings'],set()))
    for mapping,required in mappings:
        _require(type(mapping) is dict and required<=set(mapping) and len(mapping)<=256
            and all(type(k) is str for k in mapping), 'native_render_scalar_settings_incomplete')
        def scalar(item,depth=0):
            _require(depth<=4, 'native_render_scalar_settings_depth')
            if type(item) is list:
                _require(len(item)<=4096,'native_render_scalar_array_bound')
                for part in item:scalar(part,depth+1)
            else:_require(item is None or type(item) in (str,bool) or _finite(item),
                'native_render_scalar_settings_invalid')
        for item in mapping.values():scalar(item)
    _json(value)
    return value


def _validated_render_audit(audit,view,mesh_names,previous_sequence, *, minimum_objects=2):
    _require(type(audit) is dict and audit.get('schema_version')=='native-render-audit-v1'
        and audit.get('protocol')==RENDER_AUDIT_PROTOCOL and audit.get('status')=='completed'
        and audit.get('view')==view and audit.get('restored') is True
        and audit.get('geometry_restored') is True and audit.get('error') is None
        and audit.get('state_capture_errors')==[] and audit.get('execution_authority') is False,
        'native_render_restoration_unverified')
    sequence=audit.get('sequence')
    _require(type(sequence) is int and sequence>previous_sequence,'native_render_audit_not_new')
    before,after=audit.get('before'),audit.get('after')
    _validate_private_render_state(before,mesh_names,minimum_objects=minimum_objects)
    _validate_private_render_state(after,mesh_names,minimum_objects=minimum_objects)
    _require(_json(before)==_json(after),'native_render_private_state_not_restored')
    return copy.deepcopy(audit)


def _near(actual,expected,*,relative=1e-12):
    return (_finite(actual) and _finite(expected) and
        abs(actual-expected)<=max(64*max(math.ulp(float(actual)),math.ulp(float(expected))),
                                  relative*max(abs(actual),abs(expected))))


def _points(native):return [point for obj in native['objects'] for point in obj['world_vertices']]


def _center(points):
    return [min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]


def _dot(a,b):return math.fsum(x*y for x,y in zip(a,b))


def _feature_width(focal,right,up):
    vertices=focal['world_vertices'];origin=_center(vertices)
    projected=[[_dot([p[k]-origin[k] for k in range(3)],axis) for axis in (right,up)] for p in vertices]
    widths=[]
    for face in focal['faces']:
        for index,first in enumerate(face):
            a,b=projected[first],projected[face[(index+1)%len(face)]]
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if not length:continue
            offsets=[(-dy*p[0]+dx*p[1])/length for p in projected]
            widths.append(max(offsets)-min(offsets))
    return min(widths) if widths else None


def _validate_multiscale_plan(plan,native,view,focal_id,*,budget_scope='per_call_original_episode_deadline'):
    keys={'schema_version','view','scene_revision','focal_id','unit','coordinate_frame','image_size',
        'max_images','max_total_pixels','image_count','detail_included','reason_code','overview','detail',
        'feature','visibility','execution_authority','budget_scope'}
    _require(type(plan) is dict and set(plan)==keys and len(_json(plan))<=65536,
        'multiscale_public_plan_fields')
    _require(plan['schema_version']=='native-multiscale-plan-v1' and plan['view']==view
        and plan['scene_revision']==native['revision'] and plan['focal_id']==focal_id
        and plan['unit']=='m' and plan['coordinate_frame']=='world' and plan['image_size']==[384,384]
        and type(plan['max_images']) is int and plan['max_images']==2
        and type(plan['max_total_pixels']) is int and plan['max_total_pixels']==294912
        and plan['execution_authority'] is False
        and plan['budget_scope']==budget_scope,'multiscale_public_plan_binding')
    _require(type(plan['detail_included']) is bool and type(plan['image_count']) is int
        and plan['image_count']==(2 if plan['detail_included'] else 1)
        and (plan['detail'] is not None)==plan['detail_included'],'multiscale_image_count_invalid')
    reasons={'overview_sufficient','focus_budget_exceeded','degenerate_projected_focus','gain_below_threshold',
        'detail_insufficient_at_zoom_cap','central_ray_occluded_or_unknown','occlusion_budget_exceeded',
        'focal_not_renderable','projected_detail_gain'}
    _require(type(plan['reason_code']) is str and plan['reason_code'] in reasons
        and (plan['reason_code']=='projected_detail_gain')==plan['detail_included'],
        'multiscale_reason_invalid')
    raw={'XY':[0.,0.,1.],'XZ':[0.,-1.,0.],'SCENE':[1.,-1.,.75]}[view]
    eye=[x/math.hypot(*raw) for x in raw]
    # Blender's existing XY to_track_quat has a deterministic 180deg roll.
    # Match that native camera convention rather than changing its pixels.
    right=[-eye[1],eye[0],0.] if view!='XY' else [-1.,0.,0.]
    right=[x/math.hypot(*right) for x in right]
    up=[eye[1]*right[2]-eye[2]*right[1],eye[2]*right[0]-eye[0]*right[2],eye[0]*right[1]-eye[1]*right[0]]
    frame_keys={'center_world_m','right_world','up_world','eye_direction_world','span_m','screen_coverage','depth_coverage'}
    all_points=_points(native);focal=next(obj for obj in native['objects'] if obj['object_id']==focal_id)
    for kind,center in [('overview',_center(all_points)),('detail',_center(focal['world_vertices']))]:
        frame=plan[kind]
        if frame is None:continue
        _require(type(frame) is dict and set(frame)==frame_keys and _finite(frame['span_m'])
            and frame['span_m']>0 and frame['depth_coverage']=='all_native_vertices'
            and frame['screen_coverage']==('all_native_vertices' if kind=='overview' else 'intentional_local_window'),
            'multiscale_frame_fields')
        for key,expected in [('center_world_m',center),('right_world',right),('up_world',up),('eye_direction_world',eye)]:
            _require(_vector(frame[key],3) and all(_near(a,b) for a,b in zip(frame[key],expected)),
                'multiscale_frame_geometry_disagrees')
    overview=plan['overview'];_require(overview is not None,'multiscale_overview_required')
    relative=[[p[k]-overview['center_world_m'][k] for k in range(3)] for p in all_points]
    span=2.5*max(abs(_dot(p,axis)) for p in relative for axis in (right,up))
    _require(_near(overview['span_m'],span),'multiscale_overview_span_disagrees')
    feature=plan['feature']
    _require(type(feature) is dict and set(feature)=={'method','width_m','overview_px','detail_px','zoom'}
        and feature['method']=='projected_min_edge_normal_width','multiscale_feature_fields')
    values=[feature[k] for k in ('width_m','overview_px','detail_px','zoom')]
    _require(all(value is None or _finite(value) and value>0 for value in values),'multiscale_feature_values')
    bounded=(len(focal['world_vertices'])<=64 and len(focal['faces'])<=128
        and all(len(face)==3 for face in focal['faces']))
    width=_feature_width(focal,right,up) if bounded else None
    if width is None or width<=0:
        _require(all(value is None for value in values) and not plan['detail_included'],'multiscale_unavailable_feature')
    else:
        detail_span=max(4*width,span/4096)
        expected=[width,384*width/span,384*width/detail_span,span/detail_span]
        _require(all(value is not None and _near(value,target,relative=1e-10)
            for value,target in zip(values,expected)),'multiscale_feature_geometry_disagrees')
        if plan['detail_included']:
            _require(feature['overview_px']<12 and 2<=feature['zoom']<=4096 and feature['detail_px']>=32
                and _near(plan['detail']['span_m'],detail_span,relative=1e-10),'multiscale_detail_gain_unverified')
    visibility=plan['visibility']
    _require(type(visibility) is dict and set(visibility)=={'method','status','scope'}
        and visibility['method']=='single_orthographic_central_ray'
        and visibility['scope']=='one_sample_not_complete_visibility'
        and visibility['status'] in ('not_checked','focal_first','other_or_uncertain','budget_exceeded','focal_hidden_render')
        and (not plan['detail_included'] or visibility['status']=='focal_first'),'multiscale_visibility_fields')
    return copy.deepcopy(plan)


def _task_gap_checked_geometry(native,focal_id,reference_id):
    """Independent finite topology/witness reconstruction for readonly V2."""
    boxes=[]
    for identity in (focal_id,reference_id):
        obj=next(o for o in native['objects'] if o['object_id']==identity)
        vertices,faces=obj['world_vertices'],obj['faces']
        _require(len(vertices)==8 and len(faces)==12,'task_gap_axis_box_required')
        bounds=[(min(p[k] for p in vertices),max(p[k] for p in vertices)) for k in range(3)]
        _require(all(a<b for a,b in bounds) and len({tuple(p) for p in vertices})==8
            and all(all(p[k] in bounds[k] for k in range(3)) for p in vertices),'task_gap_box_corners')
        edges={};plane_counts={};seen=set()
        for tri in faces:
            _require(len(tri)==3 and len(set(tri))==3 and tuple(sorted(tri)) not in seen,'task_gap_box_triangles')
            seen.add(tuple(sorted(tri)))
            planes=[(k,vertices[tri[0]][k]) for k in range(3)
                if len({vertices[i][k] for i in tri})==1]
            _require(len(planes)==1,'task_gap_box_face_plane')
            k,level=planes[0];a,b,c=[vertices[i] for i in tri]
            u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
            facing=u[(k+1)%3]*v[(k+2)%3]-u[(k+2)%3]*v[(k+1)%3]
            _require(_finite(facing) and (facing<0 if level==bounds[k][0] else facing>0),
                'task_gap_box_outward_faces_required')
            plane_counts[planes[0]]=plane_counts.get(planes[0],0)+1
            for j in range(3):
                edge=(tri[j],tri[(j+1)%3]);edges[edge]=edges.get(edge,0)+1
        _require(len(edges)==36 and all(v==1 and edges.get((b,a))==1 for (a,b),v in edges.items())
            and plane_counts=={(k,v):2 for k in range(3) for v in bounds[k]},'task_gap_box_closed_manifold')
        boxes.append(bounds)
    f,r=boxes;separations=[];center=[None]*3
    for k in range(3):
        if f[k][1]<r[k][0]:separations.append((k,f[k][1],r[k][0],-1))
        elif r[k][1]<f[k][0]:separations.append((k,f[k][0],r[k][1],1))
        else:
            low,high=max(f[k][0],r[k][0]),min(f[k][1],r[k][1])
            _require(low<high,'task_gap_transverse_overlap_required')
            center[k]=low/2+high/2
    _require(len(separations)==1,'task_gap_single_positive_axis_required')
    axis,fvalue,rvalue,sign=separations[0];gap=abs(fvalue-rvalue)
    _require(_finite(gap) and gap>0 and all(k==axis or min(f[k][1],r[k][1])-max(f[k][0],r[k][0])>=4*gap
        for k in range(3)),'task_gap_overlap_window_required')
    center[axis]=fvalue/2+rvalue/2
    fp=list(center);rp=list(center);fp[axis]=fvalue;rp[axis]=rvalue
    fs=list(fp);rs=list(rp)
    fs[axis]+=sign*min(gap,(f[axis][1]-f[axis][0])/4)
    rs[axis]-=sign*min(gap,(r[axis][1]-r[axis][0])/4)
    return axis,gap,center,fp,rp,[fs,rs,list(center)]


def _task_gap_local_point(actual,expected,gap):
    """V2 coordinate budget follows the task gap, never absolute world size."""
    precision=gap*1e-8
    return (_vector(actual,3) and precision>0
        and all(math.ulp(float(x))<=precision/8 for x in [*actual,*expected])
        and all(abs(a-b)<=precision for a,b in zip(actual,expected)))


def _task_gap_ray_readback(native,point,eye):
    """3D line/triangle replay, independent of the planner's 2D barycentrics."""
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    def sub(a,b):return [a[k]-b[k] for k in range(3)]
    hits=[]
    for obj in native['objects']:
        vertices=obj['world_vertices']
        for tri in obj['faces']:
            a,b,c=[vertices[i] for i in tri];normal=cross(sub(b,a),sub(c,a));n2=_dot(normal,normal)
            transverse=[k for k in range(3) if eye[k]==0]
            contains=all(min(p[k]-point[k] for p in (a,b,c))<=0<=max(p[k]-point[k] for p in (a,b,c))
                for k in transverse)
            if n2==0:
                _require(not contains,'task_gap_ray_uncertain');continue
            den=_dot(normal,eye)
            if abs(den)<=1e-12*math.sqrt(n2):
                _require(not contains,'task_gap_ray_uncertain');continue
            t=_dot(normal,sub(a,point))/den
            q=[math.fsum((point[k],t*eye[k])) for k in range(3)]
            sides=[_dot(normal,cross(sub(v,u),sub(q,u))) for u,v in ((a,b),(b,c),(c,a))]
            if min(sides)<-1e-12*n2:continue
            _require(_finite(t),'task_gap_ray_nonfinite');hits.append((t,obj['object_id']))
    tolerance=1e-9*max([1.]+[abs(t) for t,_ in hits])
    nearest=max((t for t,_ in hits),default=None)
    identities={identity for t,identity in hits if nearest-t<=tolerance} if hits else set()
    return nearest,identities,tolerance


def _validate_task_gap_plan(plan,native,view,focal_id,reference_id):
    keys={'schema_version','view','scene_revision','focal_id','unit','coordinate_frame','image_size',
        'max_images','max_total_pixels','image_count','detail_included','reason_code','overview','detail',
        'feature','visibility','execution_authority','budget_scope','task_feature'}
    _require(type(plan) is dict and set(plan)==keys and plan.get('schema_version')=='native-task-gap-plan-v2'
        and len(_json(plan))<=65536,'task_gap_plan_schema')
    legacy=copy.deepcopy(plan);task=legacy.pop('task_feature',None)
    _require(type(task) is dict and set(task)=={'method','reference_id','gap_axis','gap_m','center_world_m',
        'witness_focal_world_m','witness_reference_world_m','sample_points_world_m','detail_view',
        'requested_gap_projection_px','canonical_gap_px','detail_gap_px','zoom','quality_scope','execution_authority'},
        'task_gap_feature_fields')
    _require(plan['reason_code']=='task_gap_detail_gain' and plan['detail_included'] is True
        and type(plan['image_count']) is int and plan['image_count']==2,'task_gap_two_frames_required')
    legacy.update(schema_version='native-multiscale-plan-v1',reason_code='overview_sufficient',
        detail_included=False,image_count=1,detail=None,visibility={'method':'single_orthographic_central_ray',
        'status':'not_checked','scope':'one_sample_not_complete_visibility'})
    _validate_multiscale_plan(legacy,native,view,focal_id,budget_scope=READONLY_BUDGET_SCOPE)
    _require(_finite(plan['feature']['overview_px']) and plan['feature']['overview_px']>=12,
        'task_gap_legacy_overview_branch_required')
    axis,gap,center,fp,rp,samples=_task_gap_checked_geometry(native,focal_id,reference_id)
    _require(all(_task_gap_local_point(p,p,gap) for p in (center,fp,rp,*samples)),
        'task_gap_local_coordinate_precision_unavailable')
    detail_view='XZ' if axis==2 else 'XY'
    right,up,eye=([1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]) if detail_view=='XZ' else ([-1.,0.,0.],[0.,-1.,0.],[0.,0.,1.])
    overview=plan['overview'];span=overview['span_m'];detail_span=max(4*gap,span/4096)
    canonical_px=384*gap/span;detail_px=384*gap/detail_span;zoom=span/detail_span
    _require(0<canonical_px<1 and detail_px>=32 and 2<=zoom<=4096,'task_gap_gain_unverified')
    delta=[fp[k]-rp[k] for k in range(3)]
    requested_px=384*math.hypot(_dot(delta,overview['right_world']),_dot(delta,overview['up_world']))/span
    _require(task['method']=='strict_axis_box_single_axis_gap' and task['reference_id']==reference_id
        and type(task['gap_axis']) is int and task['gap_axis']==axis and task['detail_view']==detail_view
        and task['quality_scope']=='geometric_opportunity_three_samples_not_complete_visibility'
        and task['execution_authority'] is False,'task_gap_feature_binding')
    for key,value in [('gap_m',gap),('canonical_gap_px',canonical_px),('detail_gap_px',detail_px),
            ('zoom',zoom),('requested_gap_projection_px',requested_px)]:
        _require(_near(task[key],value,relative=1e-10),'task_gap_feature_geometry_disagrees')
    for key,value in [('center_world_m',center),('witness_focal_world_m',fp),('witness_reference_world_m',rp)]:
        _require(_task_gap_local_point(task[key],value,gap),
            'task_gap_witness_disagrees')
    _require(type(task['sample_points_world_m']) is list and len(task['sample_points_world_m'])==3
        and all(_task_gap_local_point(p,q,gap) for p,q in zip(task['sample_points_world_m'],samples)),
        'task_gap_sample_points_disagree')
    frame=plan['detail'];keys={'center_world_m','right_world','up_world','eye_direction_world','span_m','screen_coverage','depth_coverage'}
    _require(type(frame) is dict and set(frame)==keys and _near(frame['span_m'],detail_span,relative=1e-10)
        and frame['screen_coverage']=='intentional_local_window' and frame['depth_coverage']=='all_native_vertices',
        'task_gap_detail_frame_fields')
    for key,value in [('center_world_m',center),('right_world',right),('up_world',up),('eye_direction_world',eye)]:
        _require(_task_gap_local_point(frame[key],value,gap) if key=='center_world_m'
            else _vector(frame[key],3) and all(_near(a,b) for a,b in zip(frame[key],value)),
            'task_gap_detail_frame_disagrees')
    triangles=sum(len(obj['faces']) for obj in native['objects']);vertices=len(_points(native))
    visibility=plan['visibility']
    _require(type(visibility) is dict and set(visibility)=={'method','status','scope','triangle_tests','max_triangle_tests','scene_vertex_count',
        'consumer_triangle_tests','total_triangle_tests','max_total_triangle_tests','work_scope'}
        and visibility['method']=='three_orthographic_samples'
        and visibility['status']=='pair_surfaces_first_and_gap_clear_to_sample'
        and visibility['scope']=='three_samples_not_complete_visibility'
        and type(visibility['triangle_tests']) is int and visibility['triangle_tests']==3*triangles<=4096
        and type(visibility['max_triangle_tests']) is int and visibility['max_triangle_tests']==4096
        and type(visibility['consumer_triangle_tests']) is int and visibility['consumer_triangle_tests']==3*triangles
        and type(visibility['total_triangle_tests']) is int and visibility['total_triangle_tests']==6*triangles<=4096
        and type(visibility['max_total_triangle_tests']) is int and visibility['max_total_triangle_tests']==4096
        and visibility['work_scope']=='producer_plus_independent_consumer'
        and type(visibility['scene_vertex_count']) is int and visibility['scene_vertex_count']==vertices<=4096
        and all(len(face)==3 for obj in native['objects'] for face in obj['faces']),
        'task_gap_visibility_budget')
    ray=[_task_gap_ray_readback(native,p,eye) for p in samples]
    for (nearest,identities,tolerance),identity in zip(ray[:2],(focal_id,reference_id)):
        _require(nearest is not None and nearest>=-tolerance and identities=={identity},'task_gap_surface_visibility_disagrees')
    nearest,_,tolerance=ray[2]
    _require(nearest is None or nearest<-tolerance,'task_gap_gap_occluded_before_sample')
    return copy.deepcopy(plan)


def _dense_focus_ray_readback(native,point,right,up,eye):
    """Independent 3D line/triangle replay using the actual view basis."""
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    def sub(a,b):return [a[k]-b[k] for k in range(3)]
    hits=[]
    for obj in native['objects']:
        for tri in obj['faces']:
            a,b,c=[obj['world_vertices'][i] for i in tri]
            normal=cross(sub(b,a),sub(c,a));n2=_dot(normal,normal)
            projected=[[_dot(sub(p,point),axis) for axis in (right,up)] for p in (a,b,c)]
            contains=all(min(p[k] for p in projected)<=0<=max(p[k] for p in projected) for k in (0,1))
            if not contains:continue
            den=_dot(normal,eye)
            _require(n2>0 and abs(den)>1e-12*math.sqrt(n2),'dense_focus_ray_uncertain')
            distance=_dot(normal,sub(a,point))/den
            q=[math.fsum((point[k],distance*eye[k])) for k in range(3)]
            sides=[_dot(normal,cross(sub(v,u),sub(q,u))) for u,v in ((a,b),(b,c),(c,a))]
            if min(sides)<-1e-12*n2:continue
            _require(_finite(distance),'dense_focus_ray_nonfinite');hits.append((distance,obj['object_id']))
    tolerance=1e-9*max([1.]+[abs(t) for t,_ in hits])
    nearest=max((t for t,_ in hits),default=None)
    identities={identity for t,identity in hits if nearest-t<=tolerance} if hits else set()
    return nearest,identities,tolerance


def _validate_dense_focus_plan(plan,native,view,focal_id):
    """Reconstruct the V3 upper bound, framing and one-sample work independently."""
    keys={'schema_version','view','scene_revision','focal_id','unit','coordinate_frame','image_size',
        'max_images','max_total_pixels','image_count','detail_included','reason_code','overview','detail',
        'feature','visibility','execution_authority','budget_scope','bounds_feature'}
    _require(type(plan) is dict and set(plan)==keys and len(_json(plan))<=65536
        and plan['schema_version']=='native-dense-focus-plan-v3','dense_focus_plan_schema')
    _require(view in ('XY','XZ'),'dense_focus_canonical_view_required')
    _require(plan['reason_code']=='dense_focus_detail_gain' and plan['detail_included'] is True
        and type(plan['image_count']) is int and plan['image_count']==2,'dense_focus_two_frames_required')
    legacy=copy.deepcopy(plan);bounds=legacy.pop('bounds_feature')
    legacy.update(schema_version='native-multiscale-plan-v1',reason_code='focus_budget_exceeded',
        detail_included=False,image_count=1,detail=None,visibility={'method':'single_orthographic_central_ray',
        'status':'not_checked','scope':'one_sample_not_complete_visibility'})
    _validate_multiscale_plan(legacy,native,view,focal_id,budget_scope=READONLY_BUDGET_SCOPE)
    focal=next(obj for obj in native['objects'] if obj['object_id']==focal_id)
    points=focal['world_vertices'];faces=focal['faces']
    vertices=len(_points(native));triangles=sum(len(obj['faces']) for obj in native['objects'])
    _require((len(points)>64 or len(faces)>128) and vertices<=4096 and 2*triangles<=4096
        and all(len(face)==3 for obj in native['objects'] for face in obj['faces']),
        'dense_focus_legacy_branch_and_work_budget')
    overview=plan['overview'];right=overview['right_world'];up=overview['up_world'];eye=overview['eye_direction_world']
    origin=_center(points)
    projected=[[_dot([p[k]-origin[k] for k in range(3)],axis) for axis in (right,up)] for p in points]
    extents=[max(p[k] for p in projected)-min(p[k] for p in projected) for k in (0,1)]
    mid=[min(p[k] for p in projected)/2+max(p[k] for p in projected)/2 for k in (0,1)]
    width=min(extents);span=overview['span_m'];detail_span=max(4*width,span/4096)
    _require(width>0 and 0<384*width/span<12 and 2<=span/detail_span<=4096
        and 384*width/detail_span>=32,'dense_focus_gain_unverified')
    center=[math.fsum((origin[k],mid[0]*right[k],mid[1]*up[k])) for k in range(3)]
    _require(type(bounds) is dict and set(bounds)=={'method','focal_vertex_count','focal_triangle_count',
        'projected_extents_m','width_upper_bound_m','overview_px_upper_bound','detail_px_upper_bound','zoom',
        'center_world_m','quality_scope','execution_authority'}
        and bounds['method']=='projected_aabb_min_extent_upper_bound'
        and type(bounds['focal_vertex_count']) is int and bounds['focal_vertex_count']==len(points)
        and type(bounds['focal_triangle_count']) is int and bounds['focal_triangle_count']==len(faces)
        and bounds['quality_scope']=='bounding_box_opportunity_not_thin_section_or_complete_visibility'
        and bounds['execution_authority'] is False,'dense_focus_bound_fields')
    _require(_vector(bounds['projected_extents_m'],2) and all(_near(a,b,relative=1e-10)
        for a,b in zip(bounds['projected_extents_m'],extents)),'dense_focus_projected_bounds_disagree')
    for key,value in [('width_upper_bound_m',width),('overview_px_upper_bound',384*width/span),
            ('detail_px_upper_bound',384*width/detail_span),('zoom',span/detail_span)]:
        _require(_near(bounds[key],value,relative=1e-10),'dense_focus_feature_geometry_disagrees')
    _require(_task_gap_local_point(bounds['center_world_m'],center,width),'dense_focus_center_disagrees')
    _require(_task_gap_local_point(overview['center_world_m'],_center(_points(native)),width),
        'dense_focus_overview_center_disagrees')
    frame=plan['detail'];frame_keys={'center_world_m','right_world','up_world','eye_direction_world','span_m','screen_coverage','depth_coverage'}
    _require(type(frame) is dict and set(frame)==frame_keys and _near(frame['span_m'],detail_span,relative=1e-10)
        and frame['screen_coverage']=='intentional_local_window' and frame['depth_coverage']=='all_native_vertices',
        'dense_focus_detail_frame_fields')
    _require(_task_gap_local_point(frame['center_world_m'],center,width),'dense_focus_detail_center_disagrees')
    for key,value in [('right_world',right),('up_world',up),('eye_direction_world',eye)]:
        _require(_vector(frame[key],3) and all(_near(a,b) for a,b in zip(frame[key],value)),
            'dense_focus_detail_axes_disagree')
    visibility=plan['visibility']
    _require(type(visibility) is dict and set(visibility)=={'method','status','scope','triangle_tests',
        'consumer_triangle_tests','total_triangle_tests','max_total_triangle_tests','work_scope','scene_vertex_count'}
        and visibility['method']=='single_orthographic_central_ray' and visibility['status']=='focal_first'
        and visibility['scope']=='one_sample_not_complete_visibility'
        and type(visibility['triangle_tests']) is int and visibility['triangle_tests']==triangles
        and type(visibility['consumer_triangle_tests']) is int and visibility['consumer_triangle_tests']==triangles
        and type(visibility['total_triangle_tests']) is int and visibility['total_triangle_tests']==2*triangles<=4096
        and type(visibility['max_total_triangle_tests']) is int and visibility['max_total_triangle_tests']==4096
        and visibility['work_scope']=='producer_plus_independent_consumer'
        and type(visibility['scene_vertex_count']) is int and visibility['scene_vertex_count']==vertices,
        'dense_focus_visibility_budget')
    nearest,identities,_=_dense_focus_ray_readback(native,center,right,up,eye)
    _require(nearest is not None and identities=={focal_id},'dense_focus_first_hit_disagrees')
    return copy.deepcopy(plan)


def _validate_multiscale_frustum(proof,frame,native,view,kind):
    keys={'schema_version','view','unit_scale_m','camera_matrix_host_units','ortho_scale_bu','clip_start_bu',
        'clip_end_bu','resolution_px','pixel_aspect','screen_coverage','depth_coverage','depth_vertex_count',
        'screen_vertex_count','checked_center_world_m','center_ndc','max_abs_screen_bu','min_depth_bu','max_depth_bu'}
    _require(type(proof) is dict and set(proof)==keys and proof['schema_version']=='native-render-frustum-v1'
        and proof['view']==view and proof['resolution_px']==[384,384] and proof['pixel_aspect']==[1.,1.]
        and proof['depth_coverage']=='all_native_vertices' and proof['screen_coverage']==frame['screen_coverage'],
        'multiscale_actual_frustum_fields')
    for key in ('unit_scale_m','ortho_scale_bu','clip_start_bu','clip_end_bu'):
        _require(_finite(proof[key]) and proof[key]>0,'multiscale_actual_frustum_parameter')
    _require(proof['clip_end_bu']>proof['clip_start_bu'],'multiscale_actual_frustum_depth_order')
    scale=proof['unit_scale_m'];half=proof['ortho_scale_bu']/2
    _require(_near(proof['ortho_scale_bu']*scale,frame['span_m'],relative=1e-5),'multiscale_actual_frustum_span')
    matrix=proof['camera_matrix_host_units']
    _require(type(matrix) is list and len(matrix)==4 and all(_vector(row,4) for row in matrix)
        and matrix[3]==[0.,0.,0.,1.],'multiscale_actual_camera_matrix')
    axes=[[matrix[k][column] for k in range(3)] for column in range(3)]
    for actual,key in zip(axes,('right_world','up_world','eye_direction_world')):
        _require(all(_near(a,b,relative=1e-5) or abs(a-b)<=1e-6 for a,b in zip(actual,frame[key])),
            'multiscale_actual_camera_axes')
    def project(point):
        delta=[point[k]/scale-matrix[k][3] for k in range(3)]
        return [_dot(delta,axis) for axis in axes]
    points=_points(native);xyz=[project(point) for point in points]
    _require(all(_vector(p,3) for p in xyz),'multiscale_actual_projection_nonfinite')
    depths=[-p[2] for p in xyz];bounds=[max(abs(p[k]) for p in xyz) for k in (0,1)]
    _require(type(proof['depth_vertex_count']) is int and proof['depth_vertex_count']==len(points)
        and type(proof['screen_vertex_count']) is int
        and proof['screen_vertex_count']==(len(points) if kind=='overview' else 1),
        'multiscale_actual_vertex_coverage')
    _require(_vector(proof['max_abs_screen_bu'],2) and all(_near(a,b) for a,b in zip(proof['max_abs_screen_bu'],bounds))
        and _near(proof['min_depth_bu'],min(depths)) and _near(proof['max_depth_bu'],max(depths)),
        'multiscale_actual_projection_disagrees')
    _require(min(depths)>=proof['clip_start_bu'] and max(depths)<=proof['clip_end_bu']
        and (kind=='detail' or max(bounds)<=half),'multiscale_actual_frustum_incomplete')
    _require(_vector(proof['checked_center_world_m'],3)
        and all(_near(a,b) for a,b in zip(proof['checked_center_world_m'],frame['center_world_m'])),
        'multiscale_actual_center_binding')
    center=project(frame['center_world_m']);ndc=[center[k]/half for k in (0,1)]
    rounding=64*max(math.ulp(float(frame['center_world_m'][k]/scale))+
        math.ulp(float(matrix[k][3])) for k in range(3))/half
    _require(rounding<=.001 and _vector(proof['center_ndc'],2)
        and all(_near(a,b) or abs(a-b)<=rounding for a,b in zip(proof['center_ndc'],ndc))
        and max(abs(x) for x in ndc)<=.02,'multiscale_actual_center_projection')
    return copy.deepcopy(proof)


def _hex(value, length):
    return (type(value) is str and len(value)==length
        and all(char in '0123456789abcdef' for char in value))


def validate_native_capabilities(value):
    """Validate a trusted local transport's capability; no scene is captured."""
    from .forward_deadline import counter_descriptor
    keys={'schema_version','protocol','process_id','clock','max_duration_ns',
          'host_source_sha256','read_only','execution_authority'}
    _require(type(value) is dict and set(value)==keys
        and value['schema_version']=='native-readonly-capabilities-v1'
        and value['protocol']==READONLY_OBSERVATION_PROTOCOL
        and type(value['process_id']) is int and 0<value['process_id']<2**32
        and type(value['max_duration_ns']) is int and value['max_duration_ns']==30_000_000_000
        and _hex(value['host_source_sha256'],64)
        and value['read_only'] is True and value['execution_authority'] is False
        and _json(value['clock'])==_json(counter_descriptor()), 'native_readonly_capabilities_invalid')
    return copy.deepcopy(value)


def _readonly_evidence(raw, captured, *, minimum_objects=2):
    keys={'protocol','capture','native_scene','coherence'}
    _require(type(raw) is dict and set(raw)==keys
        and raw['protocol']=='native-pose-evidence-v1-20261030'
        and _json(raw['capture'])==_json(captured), 'native_readonly_capture_binding')
    coherence=raw['coherence']
    fields={'same_traversal','raw_original_mesh_verified','execution_scope','snapshot_not_history',
        'capture_revision','capture_fingerprint','native_revision','sample_source',
        'world_coordinate_evaluation','independent_physical_measurement','external_edit_history_proven',
        'execution_authority','read_only_evidence','read_only_evidence_protocol'}
    capture_digest=hashlib.sha256(json.dumps(captured,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()
    native=_public_query(raw['native_scene'],minimum_objects=minimum_objects)
    _require(type(coherence) is dict and set(coherence)==fields
        and coherence['same_traversal'] is True and coherence['raw_original_mesh_verified'] is True
        and coherence['snapshot_not_history'] is True
        and coherence['execution_scope']=='independent_static_rigid_meshes'
        and coherence['capture_revision']==captured['revision']
        and coherence['capture_fingerprint']==capture_digest
        and coherence['native_revision']==native['revision']
        and coherence['sample_source']=='single_synchronous_blender_main_thread_capture'
        and coherence['world_coordinate_evaluation']=='binary64_original_local_matrix_forward_map'
        and coherence['independent_physical_measurement'] is False
        and coherence['external_edit_history_proven'] is False
        and coherence['execution_authority'] is False and coherence['read_only_evidence'] is True
        and coherence['read_only_evidence_protocol']=='owned-readonly-native-evidence-v1-20261031',
        'native_readonly_coherence_invalid')
    _require(native['revision']=='native:'+_digest(raw['native_scene']['objects']),
        'native_readonly_revision_digest')
    meshes={obj['object_id']:obj for obj in captured['meshes']}
    _require(set(meshes)=={obj['object_id'] for obj in native['objects']},'native_readonly_mesh_coverage')
    for obj in native['objects']:
        mesh=meshes[obj['object_id']]
        _require(obj['name']==mesh['name'] and _json(obj['world_vertices'])==_json(mesh['vertices'])
            and _json(obj['faces'])==_json(mesh['faces']), 'native_readonly_geometry_disagrees')
    return native


def validate_readonly_observation(raw, *, captured, capabilities, request_id,
                                  focal_id, reference_id, deadline_ns, view):
    """Validate the whole same-call response before publishing any frame.

    Private state, incarnation maps and restoration audits stay inside this
    boundary. The returned plan describes display framing, never permission.
    """
    _require(type(raw) is dict and set(raw)=={'evidence','overview','detail','plan','observation'},
        'native_readonly_response_fields')
    native=_readonly_evidence(raw['evidence'],captured)
    observation=raw['observation']
    keys={'schema_version','protocol','request_id','view','status','expected_capture_revision','binding',
        'started_ns','deadline_ns','finished_ns','capture_revision_before','capture_revision_after',
        'native_revision_before','native_revision_after','geometry_restored','state_restored',
        'quarantined','error','bundle','read_only','execution_authority'}
    _require(type(observation) is dict and set(observation)==keys
        and observation['schema_version']=='native-readonly-observation-v1'
        and observation['protocol']==READONLY_OBSERVATION_PROTOCOL
        and observation['request_id']==request_id and observation['view']==view
        and observation['status']=='completed' and observation['expected_capture_revision']==captured['revision']
        and observation['capture_revision_before']==observation['capture_revision_after']==captured['revision']
        and observation['native_revision_before']==observation['native_revision_after']==native['revision']
        and observation['geometry_restored'] is True and observation['state_restored'] is True
        and observation['quarantined'] is False and observation['error'] is None
        and observation['read_only'] is True and observation['execution_authority'] is False,
        'native_readonly_observation_invalid')
    started,finished=observation['started_ns'],observation['finished_ns']
    _require(type(started) is int and type(finished) is int and type(observation['deadline_ns']) is int
        and observation['deadline_ns']==deadline_ns and 0<=started<=finished<deadline_ns
        and deadline_ns-started<=capabilities['max_duration_ns'], 'native_readonly_deadline_invalid')
    binding=observation['binding'];identity=captured.get('host_identity',{})
    _require(type(binding) is dict and set(binding)=={'host_epoch','document_epoch','focal_id',
        'reference_id','object_instances','process_id'} and _hex(binding['host_epoch'],32)
        and _hex(binding['document_epoch'],64) and binding['document_epoch']==identity.get('document_epoch')
        and type(binding['process_id']) is int and binding['process_id']==capabilities['process_id']
        and binding['focal_id']==focal_id and binding['reference_id']==reference_id and focal_id!=reference_id
        and binding['object_instances']==identity.get('object_instances')
        and type(binding['object_instances']) is dict
        and set(binding['object_instances'])=={obj['object_id'] for obj in native['objects']},
        'native_readonly_incarnation_binding')
    if type(raw['plan']) is dict and raw['plan'].get('schema_version')=='native-dense-focus-plan-v3':
        plan=_validate_dense_focus_plan(raw['plan'],native,view,focal_id)
    else:
        plan=(_validate_task_gap_plan(raw['plan'],native,view,focal_id,reference_id)
            if type(raw['plan']) is dict and raw['plan'].get('schema_version')=='native-task-gap-plan-v2'
            else _validate_multiscale_plan(raw['plan'],native,view,focal_id,budget_scope=READONLY_BUDGET_SCOPE))
    bundle=observation['bundle']
    bundle_keys={'schema_version','protocol','status','view','sequence','native_revision_before',
        'native_revision_after','plan','frames','error','execution_authority'}
    _require(type(bundle) is dict and set(bundle)==bundle_keys
        and bundle['schema_version']=='native-multiscale-audit-v1'
        and bundle['protocol']==MULTISCALE_PROTOCOL and bundle['status']=='completed' and bundle['view']==view
        and type(bundle['sequence']) is int and bundle['sequence']>0
        and bundle['native_revision_before']==bundle['native_revision_after']==native['revision']
        and _json(bundle['plan'])==_json(plan) and bundle['error'] is None
        and bundle['execution_authority'] is False, 'native_readonly_bundle_invalid')
    frames=bundle['frames'];count=plan['image_count']
    _require(type(frames) is list and len(frames)==count
        and (raw['detail'] is not None)==plan['detail_included'],'native_readonly_frame_count')
    names=[obj['name'] for obj in native['objects']]
    previous=0;staged=[];pictures={};total=0
    for index,kind in enumerate(('overview','detail')[:count]):
        record=frames[index];image=raw[kind]
        _require(type(record) is dict and set(record)=={'kind','png_sha256','render_audit','frustum'}
            and record['kind']==kind,'native_readonly_frame_fields')
        frame_view=plan['task_feature']['detail_view'] if kind=='detail' and plan['schema_version']=='native-task-gap-plan-v2' else view
        audit=_validated_render_audit(record['render_audit'],frame_view,names,previous)
        if staged:
            _require(audit['sequence']==previous+1 and _json(audit['before'])==_json(staged[0]['before']),
                'native_readonly_between_frames_state_changed')
        previous=audit['sequence'];staged.append(audit)
        _validate_multiscale_frustum(record['frustum'],plan[kind],native,frame_view,kind)
        _require(type(image) is dict and image.get('mime_type')=='image/png'
            and type(image.get('width')) is int and type(image.get('height')) is int
            and image['width']==image['height']==384 and image.get('view')==frame_view
            and type(image.get('image_base64')) is str
            and len(image['image_base64'])<=4*((8*1024*1024+2)//3),'native_readonly_image_fields')
        png=base64.b64decode(image['image_base64'],validate=True);total+=len(png)
        _require(len(png)<=8*1024*1024 and total<=_MAX_MULTISCALE_PNG_BYTES
            and record['png_sha256']==hashlib.sha256(png).hexdigest(),'native_readonly_image_hash_or_budget')
        public=_public_native_png(png)
        _require(struct.unpack('>II',public[16:24])==(384,384),'native_readonly_png_shape')
        pictures[kind]={'type':'image','mimeType':'image/png','data':base64.b64encode(public).decode('ascii')}
    return {'images':[pictures[kind] for kind in ('overview','detail')[:count]],'plan':plan}


__all__=['READONLY_OBSERVATION_PROTOCOL','READONLY_BUDGET_SCOPE',
         'validate_native_capabilities','validate_readonly_observation']
