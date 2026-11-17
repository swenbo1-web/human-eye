"""Independent saved source-subset mathematics and installed exact-holder tests."""
import ast
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import traceback

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
RUN = Path('D:/he_m4_m5_source_region_001/sessions')
INSTALL = Path('D:/he_m4_m5_source_region_001/R1/product')
sys.path[:0] = [str(INSTALL), 'D:/he_anchor_001/venv/Lib/site-packages']
from human_eye_plugin import source_region as product
from human_eye_plugin.surface_proximity import measure_surface_proximity

checks = []
pins = {}


def check(value, name):
    if not value:
        raise AssertionError(name)
    checks.append(name)


def raw(path):
    path = Path(path)
    value = path.read_bytes()
    pins[str(path)] = dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest())
    return value


def read(path):
    return json.loads(raw(path))


def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def member(point, vertices):
    # Independent Gram-coordinate solution in the full plane.
    origin,a,b = vertices
    u,v,q = sub(a,origin),sub(b,origin),sub(point,origin)
    normal = cross(u,v)
    if normal == (0,0,0):
        first,last = min(vertices),max(vertices)
        direction = sub(last,first)
        if first == last:
            return point == first
        rel = sub(point,first)
        return cross(direction,rel)==(0,0,0) and 0<=dot(rel,direction)<=dot(direction,direction)
    if dot(q,normal):
        return False
    uu,uv,vv = dot(u,u),dot(u,v),dot(v,v)
    det = uu*vv-uv*uv
    s,t = dot(q,u)*vv-dot(q,v)*uv,dot(q,v)*uu-dot(q,u)*uv
    return s>=0 and t>=0 and s+t<=det


def surface_min_squared(left_vertices,right_vertices):
    # For these prescribed left-union/right-rectangle inputs, independent
    # disjoint-axis bounds are achieved by explicit source vertex projections.
    right_low = tuple(min(p[k] for p in right_vertices) for k in range(3))
    right_high = tuple(max(p[k] for p in right_vertices) for k in range(3))
    low = tuple(min(p[k] for p in left_vertices) for k in range(3))
    high = tuple(max(p[k] for p in left_vertices) for k in range(3))
    lower = sum(max(F(0),right_low[k]-high[k],low[k]-right_high[k])**2 for k in range(3))
    attained=[]
    for p in left_vertices:
        q=tuple(max(right_low[k],min(right_high[k],p[k])) for k in range(3))
        if dot(sub(p,q),sub(p,q))==lower:
            attained.append((p,q))
    check(bool(attained),'independent_coordinate_lower_bound_attained')
    return lower,attained


def full_capture_decoder():
    prior = Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/geometry/review.py')
    tree=ast.parse(raw(prior).decode('utf8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='captures')
    env=dict(read=read,check=check,json=json)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(prior),'exec'),env)
    return env['captures']


def validate_camera(binding,selected_points,capture,is_original):
    cameras=binding['camera_specification']
    center=tuple((min(p[k] for p in selected_points)+max(p[k] for p in selected_points))/2 for k in range(3))
    fit_checks=[]
    for pose in cameras['views']:
        axes=[tuple(map(F,row[:3])) for row in pose['view_matrix'][:2]]
        half=max(abs(dot(sub(p,center),axis)) for p in selected_points for axis in axes)
        observed=F(pose['half_span_m']) if 'half_span_m' in pose else F(pose['span'])/2
        error=abs(observed-half*F(1.1))
        fit_checks.append(error<F(1,10**12))
        for p in selected_points:
            h=tuple(p)+(F(1),)
            cam=tuple(dot(tuple(map(F,row)),h) for row in pose['view_matrix'])
            ndc=tuple(dot(tuple(map(F,row)),cam) for row in pose['projection_matrix'])
            check(all(-1<x<1 for x in ndc[:2]),'selected_vertex_inside_actual_camera_XY')
        if is_original:
            continue
        for mesh in capture['meshes']:
            axes_bounds=[(min(F(p[k]) for p in mesh['vertices']),max(F(p[k]) for p in mesh['vertices'])) for k in range(3)]
            for p in itertools.product(*axes_bounds):
                depth=-dot(tuple(map(F,pose['view_matrix'][2])),tuple(p)+(F(1),))
                check(F(pose['near'])<depth<F(pose['far']),'all_scene_AABB_corners_inside_depth')
    if is_original:
        check(not any(fit_checks),'original_R0_global_camera_rejected_by_local_fit_contract')
    else:
        check(all(fit_checks),'corrected_local_fit_contract')
        check(tuple(map(F,cameras['common_center_world_m']))==center,'camera_center_is_selected_bounds_center')
    return dict(fitted=all(fit_checks),SCENE_span=cameras['views'][0]['span'])


def saved_math():
    decode=full_capture_decoder()
    records,whole_controls=[],[]
    for session in sorted(RUN.iterdir()):
        captures=decode(session)
        for path in sorted((session/'product_full').glob('call_*/SERVICE_RESULT.json')):
            full=read(path)
            if full.get('result_kind')=='task_query':
                names=[r['name'] for r in full['binding']['objects']]
                matches=[c for c in captures if c.get('revision')==full['binding']['scene_revision']
                         and [m['name'] for m in c['meshes']]==names]
                check(bool(matches),'whole_object_control_actual_selected_capture')
                left,right=matches[-1]['meshes']
                minimum,pairs=surface_min_squared([tuple(map(F,p)) for p in left['vertices']],
                                                 [tuple(map(F,p)) for p in right['vertices']])
                expected=F(1,1024) if names[1]=='Ref_B' else F(2305,1024)
                check(minimum==expected,'whole_object_distance_differs_from_subset')
                with localcontext() as ctx:
                    ctx.prec=100
                    rounded=float((Decimal(minimum.numerator)/Decimal(minimum.denominator)).sqrt())
                check(full['facts']['surface_proximity']['value']['distance_m']==rounded,
                      'actual_whole_object_control_correctly_rounded')
                whole_controls.append(dict(reference=names[1],exact_distance_squared=str(minimum),distance=rounded))
                continue
            if full.get('result_kind')!='source_region':
                continue
            binding=full['binding']
            matches=[c for c in captures if c.get('revision')==binding['scene_revision'] and c.get('capture_state')==binding['capture_state']]
            check(bool(matches) and all(c==matches[0] for c in matches),'actual_current_capture_recovered')
            capture=matches[0]
            region=full['facts']['region']
            object_index=next(i for i,o in enumerate(capture['meshes']) if o['name']==region['object_name'])
            mesh=capture['meshes'][object_index]
            faces=region['source_triangle_indices']
            source_vertices=sorted({i for fi in faces for i in mesh['faces'][fi]})
            mapping=full['source_mapping']
            check(mapping['submesh_to_source_triangle_indices']==faces,'submesh_original_face_order')
            check(mapping['submesh_to_source_vertex_indices']==source_vertices,'submesh_original_vertex_order')
            check(mapping['triangles_source_vertices']==[mesh['faces'][i] for i in faces],'source_faces_match_capture')
            for local,source in zip(mapping['triangles_submesh_vertices'],mapping['triangles_source_vertices']):
                check([source_vertices[i] for i in local]==source,'compact_face_indices_reverse_exactly')
            selected=[tuple(map(F,mesh['vertices'][i])) for i in source_vertices]
            check([list(map(float,p)) for p in selected]==region['vertices_world_m'],'selected_world_coordinates_exactly_captured')
            measurement=full['task_result']
            reference_name=measurement['reference']['name']
            right=next(m for m in capture['meshes'] if m['name']==reference_name)
            right_vertices=[tuple(map(F,p)) for p in right['vertices']]
            minimum,pairs=surface_min_squared(selected,right_vertices)
            fact=measurement['facts']['surface_proximity']
            check(fact['status']=='measured','actual_surface_distance_measured')
            value=fact['value']
            with localcontext() as ctx:
                ctx.prec=100
                exact_distance=(Decimal(minimum.numerator)/Decimal(minimum.denominator)).sqrt()
                rounded=float(exact_distance)
            check(value['distance_m']==rounded,'distance_correctly_rounded_from_independent_exact_lower_bound')
            near=value['nearest_witness']
            witness_a,witness_b=tuple(map(F,near['a'])),tuple(map(F,near['b']))
            check(dot(sub(witness_a,witness_b),sub(witness_a,witness_b))==minimum,'published_exact_world_witness_attains_minimum')
            for side,point,source_mesh,source_rows,vertices in (
                    ('a',witness_a,mesh,faces,source_vertices),
                    ('b',witness_b,right,list(range(len(right['faces']))),list(range(len(right['vertices']))))):
                expected_faces=[i for i in source_rows if member(point,[tuple(map(F,source_mesh['vertices'][j])) for j in source_mesh['faces'][i]])]
                expected_vertices=[i for i in vertices if tuple(map(F,source_mesh['vertices'][i]))==point]
                result=measurement['source_mapping']['nearest_witness'][side]
                check(result['exact_membership'] is True and result['source_triangle_indices']==expected_faces
                      and result['source_vertex_indices']==expected_vertices,'world_witness_original_source_memberships/'+side)
            camera=validate_camera(binding,selected,capture,session.name=='qualification_R0')
            records.append(dict(session=session.name,call=path.parent.name,source_faces=faces,reference=reference_name,
                                exact_distance_squared=str(minimum),actual_distance=value['distance_m'],
                                selected_pixels=full['facts']['visibility']['selected_surface_pixels'],camera=camera))
    check(len(records)==20,'all_twenty_successful_source_region_results_checked')
    check(all(r['selected_pixels']==13 for r in records if r['session']=='qualification_R0'),'original_R0_thirteen_pixels_preserved')
    check(all(r['selected_pixels']==26212 for r in records if r['session']!='qualification_R0' and r['source_faces']==[0,1,2,3]),
          'corrected_full_region_actual_pixel_count')
    check(len(whole_controls)==2,'two_saved_whole_object_controls')
    return records,whole_controls


def exact_holder_controls():
    recipe=read(AUTHOR/'verification/m4_m5_source_region_001/fixture/GEOMETRY.json')
    meshes=[dict(object_id='source-'+o['name'],name=o['name'],vertices=[[float(F(v)) for v in p] for p in o['vertices_world_m']],faces=o['triangles'])
            for o in recipe['objects']]
    capture=dict(unit='m',coordinate_frame='world',source='blender',revision='independent:1',meshes=meshes,
        host_identity=dict(schema_version='1.0',document_epoch='f'*64,capture_scope='complete_scene_meshes',
                           object_instances={m['object_id']:str(i) for i,m in enumerate(meshes)}),
        capture_state=dict(instance_id='independent',epoch=1,revision=1,selection_key='full'))
    query=dict(mode='source_region',region=dict(object=dict(name='Obj_07'),source_triangle_indices=[0,1,2,3]),
               reference=dict(name='Ref_B'),requested_facts=['surface_proximity'])
    prepared=product.prepare_region(capture,query)
    results=[]
    for name in ('Ref_B','Ref_C'):
        index=next(i for i,m in enumerate(prepared.meshes) if m.name==name)
        right=prepared.meshes[index]
        holder=dict(witness_points='stale')
        result=measure_surface_proximity(prepared.region_mesh,right,lambda stage:None,_prepared_holder=holder)
        check(result['measurement_valid'] and isinstance(holder['witness_points'],tuple),'private_holder_replaced_stale_witness')
        origin,factor=holder['pair'][2],holder['pair'][3]
        for side,mesh,rows,vertices in ((0,prepared.region_mesh,prepared.source_triangle_indices,prepared.source_vertex_indices),
                                       (1,right,tuple(range(len(right.faces))),tuple(range(len(right.vertices))))):
            local=holder['witness_points'][side]
            world=tuple(F(o)+F(x,factor) for o,x in zip(origin,local))
            source=meshes[prepared.object_index] if side==0 else meshes[index]
            expected_faces=[rows[i] for i,face in enumerate(mesh.faces) if member(local,[tuple(holder['coordinates'][side][int(j)]) for j in face])]
            expected_vertices=[vertices[int(i)] for i,p in holder['coordinates'][side].items() if p==local]
            actual=product._witness_sources(holder,side,rows,vertices,lambda stage:None)
            check(expected_faces==actual['source_triangle_indices'] and expected_vertices==actual['source_vertex_indices'],
                  'private_exact_holder_membership_recomputed_with_Gram')
            check([float(x) for x in world]==result['point_a_world' if side==0 else 'point_b_world'],
                  'private_exact_holder_origin_scale_publish')
        results.append(dict(reference=name,distance=result['distance_m'],factor=factor,
                            exact_witness_points=[list(map(str,p)) for p in holder['witness_points']]))
    # Degenerate hulls and reversed winding exercise the membership helper only.
    counts=0
    examples=[((F(0),F(0),F(0)),(F(1),F(0),F(0)),(F(0),F(1),F(0))),
              ((F(0),F(0),F(0)),(F(0),F(1),F(0)),(F(1),F(0),F(0))),
              ((F(0),F(0),F(0)),(F(1),F(0),F(0)),(F(2),F(0),F(0))),
              ((F(0),F(0),F(0)),)*3]
    for points in examples:
        normal=cross(sub(points[1],points[0]),sub(points[2],points[0]))
        hull=points if any(normal) else ((min(points),) if min(points)==max(points) else (min(points),max(points)))
        record=(hull,normal,dot(normal,normal),(),())
        for point in itertools.product((F(-1),F(0),F(1,4),F(1),F(2)),repeat=3):
            check(product._contains_exact(point,record)==member(point,points),'exact_membership_plane_segment_or_point')
            counts+=1
    return dict(measurements=results,membership_controls=counts,new_images=0,new_raster=0)


def main():
    saved,whole=saved_math()
    holder=exact_holder_controls()
    result=dict(status='passed',checks=len(checks),saved=saved,whole_object_controls=whole,private_holder=holder,input_pins=pins,
                installed_source_region_path=str(Path(product.__file__).resolve()),
                new_operations=dict(Blender=0,MCP=0,raster=0,image_encoding=0,model=0,paid_API=0))
    (OUT/'SOURCE_MATH_RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=len(checks),saved_results=len(saved),holder=holder)))


if __name__=='__main__':
    try:
        main()
    except BaseException:
        (OUT/'SOURCE_MATH_FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
