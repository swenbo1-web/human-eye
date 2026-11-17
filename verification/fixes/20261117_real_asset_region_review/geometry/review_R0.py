"""Independent real-source correspondence and exact closed-box qualification."""
import ast
from collections import Counter
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import traceback

sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np

OUT=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_real_asset_region_qualification_001')
RUN=Path('D:/he_m4_real_asset_region_001/sessions')
counts=Counter()
pins={}


def check(value,label):
    if not value:
        raise AssertionError(label)
    counts[label]+=1


def raw(path):
    path=Path(path)
    value=path.read_bytes()
    pins[str(path)]=dict(bytes=len(value),sha256=hashlib.sha256(value).hexdigest())
    return value


def read(path):
    return json.loads(raw(path))


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def member(point,points):
    p,a,b=points
    u,v,q=sub(a,p),sub(b,p),sub(point,p)
    n=cross(u,v)
    if dot(n,q):return False
    aa,bb,cc=dot(u,u),dot(u,v),dot(v,v)
    det=aa*cc-bb*bb
    if not det:return False
    s,t=dot(q,u)*cc-dot(q,v)*bb,dot(q,v)*aa-dot(q,u)*bb
    return s>=0 and t>=0 and s+t<=det


def binary64_world(points,matrix,scale):
    # This operation ordering is the actual host resource realization.
    return [[(((row[0]*p[0]+row[1]*p[1])+row[2]*p[2])+row[3])*scale for row in matrix[:3]] for p in points]


def closed_box(vertices,triangles):
    check(len(vertices)==8 and len(triangles)==12,'Cube_8_vertices_12_triangles')
    low=tuple(min(p[k] for p in vertices) for k in range(3))
    high=tuple(max(p[k] for p in vertices) for k in range(3))
    check(set(vertices)==set(itertools.product(*zip(low,high))),'Cube_exact_eight_AABB_corners')
    assigned=[]
    faces=[]
    for axis in range(3):
        free=[k for k in range(3) if k!=axis]
        for side,value in (('min',low[axis]),('max',high[axis])):
            rows=[i for i,t in enumerate(triangles) if all(vertices[j][axis]==value for j in t)]
            check(len(rows)==2,'Cube_two_triangles_per_exact_face')
            left,right=[set(triangles[i]) for i in rows]
            common=left&right
            check(len(common)==2 and len(left|right)==4,'Cube_face_four_corners_shared_edge')
            a,b=[vertices[j] for j in common]
            check(all(a[k]!=b[k] for k in free),'Cube_shared_edge_is_face_diagonal')
            for row in rows:
                tri=[vertices[j] for j in triangles[row]]
                normal=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]))
                check(normal[axis]!=0 and all(normal[k]==0 for k in free),'Cube_nondegenerate_axis_face')
            faces.append(dict(axis=axis,side=side,level=str(value),source_triangle_rows=rows))
            assigned.extend(rows)
    check(sorted(assigned)==list(range(12)),'Cube_surface_all_faces_exactly_covered')
    return low,high,faces


def box_distance(points,low,high,source_ids):
    check(all(all(low[k]<p[k]<high[k] for k in range(3)) for p in points),'all_selected_vertices_strictly_inside_Cube')
    bounds=[]
    for axis in range(3):
        for side,level in (('min',low[axis]),('max',high[axis])):
            gaps=[p[axis]-level if side=='min' else level-p[axis] for p in points]
            minimum=min(gaps)
            attaining=[source_ids[i] for i,g in enumerate(gaps) if g==minimum]
            bounds.append(dict(axis=axis,side=side,minimum=minimum,attaining=attaining))
    winner=min(bounds,key=lambda row:row['minimum'])
    check(winner['axis']==2 and winner['side']=='max','nearest_closed_box_surface_is_positive_Z')
    return winner,bounds


def snapshots():
    arm=read(AUTHOR/'inputs/ARM_REGION.json')
    historical_raw=read(AUTHOR/'inputs/raw_selected.json')
    historical_eval=read(AUTHOR/'inputs/evaluated_selected.json')
    check(len(arm['source_vertex_ids'])==410 and len(arm['source_triangle_ids'])==748,'historical_region_410_points_748_faces')
    check(historical_raw['vertices_object']==historical_eval['vertices_object']
          and historical_raw['triangles']==historical_eval['triangles']
          and historical_raw['polygon_ids_by_triangle']==historical_eval['polygon_ids_by_triangle'],
          'historical_raw_evaluated_rows_equal')
    output=[]
    for session,name in (('main','initial'),('state','initial'),('state','moved'),('state','restored')):
        path=RUN/session/('SOURCE_'+name+'.json')
        source=read(path)
        target=next(o for o in source['objects'] if o['name']==arm['object_name'])
        cube=next(o for o in source['objects'] if o['name']=='Cube')
        native,evaluated=target['native'],target['evaluated']
        check(len(native['vertices'])==27304 and len(native['polygons'])==29073
              and len(native['triangles'])==53264,'fresh_native_counts')
        for field in ('vertices','polygons','triangles','triangle_polygons','vertices_world_m'):
            check(native[field]==evaluated[field],'fresh_native_evaluated_same_rows/'+field)
        check(native['vertices']==historical_raw['vertices_object'] and native['triangles']==historical_raw['triangles']
              and native['triangle_polygons']==historical_raw['polygon_ids_by_triangle'],'fresh_same_historical_source_topology')
        for face,poly in zip(native['triangles'],native['triangle_polygons']):
            check(set(face)<=set(native['polygons'][poly]),'native_triangle_belongs_to_declared_polygon')
        for domain in (native,evaluated):
            keys=[(p,*sorted(t)) for p,t in zip(domain['triangle_polygons'],domain['triangles'])]
            check(len(set(keys))==53264,'polygon_vertex_triangle_keys_unique')
        source_ids=arm['source_vertex_ids']
        face_ids=arm['source_triangle_ids']
        source_set={i for fi in face_ids for i in native['triangles'][fi]}
        check(source_set==set(source_ids),'region_vertices_are_complete_union_of_selected_faces')
        check([native['triangle_polygons'][i] for i in face_ids]==arm['source_polygon_ids'],
              'all_748_region_source_polygons_mapped')
        check([[source_ids[i] for i in face] for face in arm['triangles_local']]
              ==[native['triangles'][i] for i in face_ids],'region_compact_to_full_triangle_vertices')
        check([native['vertices'][i] for i in source_ids]==arm['vertices_object'],'region_original_vertices_same')
        world64=binary64_world(native['vertices'],target['matrix_world'],source['unit_scale'])
        body64=[tuple(map(F,p)) for p in world64]
        bpyworld=[tuple(map(F,p)) for p in native['vertices_world_m']]
        cast32=np.asarray(world64,dtype=np.float32).astype(np.float64)
        bpy=np.asarray(native['vertices_world_m'],dtype=np.float64)
        check(np.array_equal(cast32,bpy),'Bpy_world_readback_equals_binary64_cast_to_float32')
        cube64=binary64_world(cube['native']['vertices'],cube['matrix_world'],source['unit_scale'])
        low,high,box_faces=closed_box([tuple(map(F,p)) for p in cube64],cube['native']['triangles'])
        selected=[body64[i] for i in source_ids]
        winner,bounds=box_distance(selected,low,high,source_ids)
        bpywinner,bpybounds=box_distance([bpyworld[i] for i in source_ids],low,high,source_ids)
        check(winner['attaining']==[24331],'binary64_unique_attaining_source_point_24331')
        point=body64[24331]
        onbox=(point[0],point[1],high[2])
        member_faces=[i for i in face_ids if member(point,[body64[j] for j in native['triangles'][i]])]
        cube_points=[tuple(map(F,p)) for p in cube64]
        ref_faces=[i for i,t in enumerate(cube['native']['triangles']) if member(onbox,[cube_points[j] for j in t])]
        check(member_faces==[48160,48161],'exact_attaining_source_triangle_rows')
        check([native['triangle_polygons'][i] for i in member_faces]==[26521,26521],
              'attaining_source_polygon_26521')
        check(ref_faces==[0] and cube['native']['triangle_polygons'][0]==0,'attaining_Cube_row_and_polygon_zero')
        check(float(winner['minimum'])==0.37011719389236364 and float(bpywinner['minimum'])==0.3701171875,
              'both_coordinate_domain_answers')
        check(cube['display']['hide_get'] is True and cube['display']['hide_render'] is True
              and cube['display']['visible_get'] is False,'Cube_hidden_display_flags')
        check(target['parent'] is None and target['modifiers']==[] and target['animation'] is None,
              'actual_static_mesh_no_armature_modifiers_or_animation')
        output.append(dict(session=session,state=name,source=source,target=target,cube=cube,world64=world64,
            selected_source_ids=source_ids,source_face_ids=face_ids,
            summary=dict(session=session,state=name,source_file_sha256=pins[str(path)]['sha256'],
                native_vertices=27304,native_polygons=29073,evaluated_triangles=53264,region_vertices=410,region_triangles=748,
                distance_binary64=float(winner['minimum']),distance_binary64_exact=str(winner['minimum']),
                distance_Bpy_float32=float(bpywinner['minimum']),distance_Bpy_float32_exact=str(bpywinner['minimum']),
                inter_domain_gap_m=float(winner['minimum']-bpywinner['minimum']),
                attaining_source_point=24331,attaining_source_faces=member_faces,attaining_source_polygon=26521,
                attaining_Cube_face=0,attaining_Cube_polygon=0,
                six_exact_face_lower_bounds=[dict(axis=b['axis'],side=b['side'],minimum=str(b['minimum']),source_vertex_ids=b['attaining']) for b in bounds],
                box_faces=box_faces)))
    return output


def current_captures(session):
    prior=Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/geometry/review.py')
    tree=ast.parse(raw(prior).decode('utf8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='captures')
    env=dict(read=read,check=check,json=json)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(prior),'exec'),env)
    return env['captures'](session)


def frame_geometry(exports):
    all_calls=[]
    for session in ('main','state'):
        cap=current_captures(RUN/session)
        for path in sorted((RUN/session/'product_full').glob('call_*/SERVICE_RESULT.json')):
            full=read(path)
            if full.get('result_kind')!='source_region':continue
            binding=full['binding']
            match=[c for c in cap if c.get('revision')==binding['scene_revision'] and c.get('capture_state')==binding['capture_state']]
            check(bool(match),'actual_complete_capture_for_result')
            capture=match[0]
            target_index=next(i for i,m in enumerate(capture['meshes']) if m['name']==exports[0]['target']['name'])
            cube_index=next(i for i,m in enumerate(capture['meshes']) if m['name']=='Cube')
            target=capture['meshes'][target_index]
            same=[e for e in exports if e['session']==session and e['world64']==target['vertices']]
            check(bool(same),'actual_capture_equals_fresh_binary64_domain')
            fresh=same[0]
            native=fresh['target']['native']
            check(target['faces']==native['triangles'],'actual_capture_triangles_same_as_native_rows')
            check(full['source_mapping']['submesh_to_source_triangle_indices']==fresh['source_face_ids']
                  and full['source_mapping']['submesh_to_source_vertex_indices']==fresh['selected_source_ids'],
                  'actual_subset_mapping_exactly_748_by_410')
            fact=full['task_result']['facts']['surface_proximity']
            check(fact['value']['distance_m']==fresh['summary']['distance_binary64'],'actual_product_distance_matches_exact_binary64_answer')
            witness=full['task_result']['source_mapping']['nearest_witness']
            check(witness['a']['source_triangle_indices']==[48160,48161]
                  and witness['a']['source_vertex_indices']==[24331]
                  and witness['b']['source_triangle_indices']==[0],'public_exact_witness_source_rows')
            frame=full['frames'][0]
            pose=frame['pose']
            low=tuple(min(F(p[k]) for p in capture['meshes'][cube_index]['vertices']) for k in range(3))
            high=tuple(max(F(p[k]) for p in capture['meshes'][cube_index]['vertices']) for k in range(3))
            direction=tuple(map(F,pose['view_matrix'][2][:3]))
            check(direction[2]>0,'actual_SCENE_direction_toward_positive_Z')
            margins=[]
            for point_id in fresh['selected_source_ids']:
                p=tuple(map(F,target['vertices'][point_id]))
                t=(high[2]-p[2])/direction[2]
                hit=tuple(x+t*d for x,d in zip(p,direction))
                check(t>0 and all(low[k]<hit[k]<high[k] for k in (0,1)),
                      'every_selected_vertex_ray_strictly_hits_Cube_top')
                margins.extend([hit[k]-low[k] for k in (0,1)])
                margins.extend([high[k]-hit[k] for k in (0,1)])
            # All hit inequalities are affine on each selected triangle.
            # Vertex strictness proves continuous interior occlusion as well.
            for p in itertools.product(*zip(low,high)):
                depth=-dot(tuple(map(F,pose['view_matrix'][2])),tuple(p)+(F(1),))
                check(F(pose['near'])<depth<F(pose['far']),'Cube_inside_actual_near_far_depth')
            check(full['facts']['visibility']['selected_surface_pixels']==0,'actual_selected_samples_zero')
            check(full['facts']['visibility']['unseen_source_triangle_indices']==fresh['source_face_ids'],
                  'all_748_faces_marked_unseen')
            all_calls.append(dict(session=session,call=path.parent.name,camera_span_m=pose['span'],
                Cube_source_object_index=cube_index,selected_triangle_count=748,selected_pixel_count=0,
                continuous_Cube_top_occlusion=True,minimum_strict_XY_hit_margin_m=float(min(margins)),
                observation_status=full['observation_status'],status=full['status']))
    check(len(all_calls)==5,'all_five_successful_deliveries_geometry_checked')
    return all_calls


def main():
    exports=snapshots()
    actual=frame_geometry(exports)
    result=dict(status='passed_checked_scope',checks=sum(counts.values()),checks_by_kind=dict(counts),
        snapshots=[e['summary'] for e in exports],actual_calls=actual,input_pins=pins,
        proof_scope='ordered static source mapping, separate binary64/Bpyfloat32 domains, exact closed-box distances and continuous current SCENE occlusion',
        actual_asset_has_armature=False,new_live_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0))
    (OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],exports=len(exports),actual_calls=len(actual),
        binary64=exports[0]['summary']['distance_binary64'],Bpy32=exports[0]['summary']['distance_Bpy_float32'],
        gap=exports[0]['summary']['inter_domain_gap_m'])))


if __name__=='__main__':
    try:main()
    except BaseException:
        (OUT/'FAILURE.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
