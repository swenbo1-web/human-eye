"""Independent exact screen-envelope oracle and installed coverage controls."""

import argparse
from dataclasses import asdict
from fractions import Fraction as F
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
import json
from pathlib import Path
import sys
from unittest.mock import patch


sys.path.insert(0,str(Path(__file__).resolve().parent))
from fixture import CASES, digest, pin, read, require, source


MOD = 'human_eye_plugin/active_observation.py'
TASK = 'human_eye_plugin/active_observation_region_task.py'
BASE = 'cee6fe78a65c1534361228641743aa83d6d72b61'
EXPECTED_MAIN = {'Component_582':[2,2,514,514,2,2],'Component_736':[4,4,2,4,4,4]}


def canonical(value):
    return json.dumps(value,default=str,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def load(path,tag,files,source_pins):
    bound = read(path)
    manifest = {row['path']:row['sha256'] for row in bound['source_manifest']}
    require(len(manifest)==143,'isolated_runtime_manifest_wrong_size')
    root = Path(bound['install_root']).resolve(strict=True)
    sys.path[:0] = [str(root),bound['dependency_root']]
    loaded = []
    for name in files:
        file = root/name
        verified = pin(file)
        require(verified['sha256']==manifest[name],'wrong_isolated_module/'+tag+'/'+name)
        label = 'human_eye_plugin._m4_bounds_'+tag+'_'+file.stem
        spec = spec_from_file_location(label,file)
        module = module_from_spec(spec)
        sys.modules[label] = module
        spec.loader.exec_module(module)
        source_pins.append(verified)
        loaded.append(module)
    source_pins.append(pin(path))
    return bound,*loaded


def basis(direction):
    """Independent expansion of the canonical scene-up rational screen axes."""
    x,y,z = map(F,direction)
    return ((-y,x,F(0)),(-x*z,-y*z,x*x+y*y)) if x or y else ((z,F(0),F(0)),(F(0),z*z,F(0)))


def projection(points, axes):
    return tuple(tuple(sum(point[i]*axis[i] for i in range(3)) for axis in axes) for point in points)


def envelope(points):
    return tuple((min(values),max(values)) for values in zip(*points,strict=True))


def positive_overlap(a,b):
    return all(min(hi,other_hi) - max(lo,other_lo) > 0
               for (lo,hi),(other_lo,other_hi) in zip(a,b,strict=True))


def object_bounds(objects):
    return tuple(envelope(row[0]) if row[0] else None for row in objects)


def oracle_views(objects,triangles,region,cameras,bounds_,candidate=None):
    """Use the eight explicit corners as a checker, and all old faces for exact overlaps."""
    result = {}
    for view in cameras['views']:
        axes = basis(view['direction_rational'])
        region_box = envelope(projection(region.vertices,axes))
        survivors = set()
        for i,world_box in enumerate(bounds_):
            if world_box is None:
                survivors.add(i)
                continue
            screen_box = envelope(projection(product(*world_box),axes))
            if candidate is not None:
                require(candidate._project_world_bounds(world_box,axes)==screen_box,
                        'signed_endpoint_projection_is_not_exact_corner_hull')
            if positive_overlap(region_box,screen_box):
                survivors.add(i)
        legacy, filtered, old_projection, filtered_projection = [],[],[],[]
        old_points, filtered_points = set(),set()
        for triangle in triangles:
            tri = projection(triangle.vertices,axes)
            passes = positive_overlap(envelope(tri),region_box)
            source_row = triangle.object_index,triangle.triangle_index
            old_projection.append(tri)
            old_points.update(triangle.vertices)
            if passes:
                legacy.append(source_row)
            if triangle.object_index in survivors:
                filtered_projection.append(tri)
                filtered_points.update(triangle.vertices)
                if passes:
                    filtered.append(source_row)
        require(legacy==filtered,'independent_ordered_fine_overlap_changed/'+view['name'])
        result[view['name']] = {'old':old_projection,'selected':filtered_projection,
                                'old_vertices':len(old_points),'selected_vertices':len(filtered_points),
                                'fine':legacy,'object_indices':sorted(survivors)}
    return result


def observed(api,objects,triangles,scene,region,cameras,*,bounds_=None):
    observations, current = {}, None
    real_planes, real_bounds, real_shadow = api.camera_planes,api.bounds,api.triangle_shadow

    def planes(pose):
        nonlocal current
        current = observations[pose['name']] = {'bounds':[],'shadows':[]}
        return real_planes(pose)

    def bounds(points):
        if len(points)==3:
            current['bounds'].append(points)
        return real_bounds(points)

    def shadow(triangle,roi,axes,planes_,cached_screen=None):
        current['shadows'].append((triangle.object_index,triangle.triangle_index))
        return real_shadow(triangle,roi,axes,planes_,cached_screen)

    work = {}
    options = {} if bounds_ is None else {'local_object_bounds':bounds_,'local_projection_work':work}
    with patch.multiple(api,camera_planes=planes,bounds=bounds,triangle_shadow=shadow):
        index = api.build_index_from_parsed(objects,triangles,scene,(region,),cameras,
                                            bind_blocker_sources=True,**options)
    return asdict(index),observations,work


def compare(label,parsed,region,cameras,a,b=None,task=None,*,unknown=(),reverse=False):
    objects, triangles, scene = parsed
    if reverse:
        triangles = tuple(reversed(triangles))
    bounds_ = object_bounds(objects)
    if task:
        require(task._object_world_bounds(objects)==bounds_,'installed_world_box_is_not_normalized_bounds/'+label)
    checked = tuple(None if i in unknown else row for i,row in enumerate(bounds_))
    oracle = oracle_views(objects,triangles,region,cameras,checked,b)
    old, old_calls, _ = observed(a,objects,triangles,scene,region,cameras)
    if b:
        new, new_calls, work = observed(b,objects,triangles,scene,region,cameras,bounds_=checked)
        require(canonical(old)==canonical(new),'complete_local_CoverageIndex_changed/'+label)
    proof = {}
    for view,row in oracle.items():
        original = old_calls[view]
        require(original['bounds']==row['old'],'legacy_projection_diverges_from_independent_oracle/'+label+'/'+view)
        self_rows = {(region.object_index,i) for i in region.triangle_indices}
        fine = [x for x in row['fine'] if x not in self_rows]
        require(original['shadows']==fine[:len(original['shadows'])],
                'legacy_exact_shadow_order_or_fine_candidates_changed/'+label+'/'+view)
        if b:
            current = new_calls[view]
            require(current['bounds']==row['selected'] and current['shadows']==original['shadows'],
                    'coarse_screen_or_exact_shadow_sequence_changed/'+label+'/'+view)
            values = work[view]
            require(values['input_triangles']==len(row['old'])
                    and values['projected_triangles']==len(row['selected'])
                    and values['projected_vertices']==row['selected_vertices'],
                    'actual_projection_diagnostics_disagree_with_oracle/'+label+'/'+view)
        proof[view] = {'legacy_projected_triangles':len(row['old']),'filtered_projected_triangles':len(row['selected']),
                       'legacy_projected_vertices':row['old_vertices'],'filtered_projected_vertices':row['selected_vertices'],
                       'ordered_fine_source_rows':row['fine'],'actual_exact_depth_branches':original['shadows'],
                       'coverage':old['classifications'][view][region.roi_id],
                       'surviving_object_indices':row['object_indices']}
    return {'label':label,'coverage_index_identity':digest(canonical(old)),'directions':proof}


def real_case(name,a,b,task):
    scene,producer,pins = source(name)
    parsed = a.geometry(scene)
    objects,triangles,identity = parsed
    require(identity==producer['binding']['geometry_identity'],'real_normalized_geometry_identity_changed/'+name)
    regions,_ = a.partition_regions(objects)
    lookup = {row.roi_id:row for row in regions}
    results = []
    for scope in producer['scopes'][1:]:
        detail = scope['facts']['scope']
        roi = lookup[detail['roi_id']]
        bound = detail['source']
        require((roi.object_index,list(roi.triangle_indices))==(bound['object_index'],bound['source_triangle_indices']),
                'sealed_rectangle_source_changed/'+name)
        result = compare(roi.object_name,parsed,roi,scope['binding']['camera_specification'],a,b,task)
        if name=='main':
            per_direction = [row['filtered_projected_triangles'] for row in result['directions'].values()]
            require(per_direction==EXPECTED_MAIN[roi.object_name],'preregistered_projection_counts_changed/'+roi.object_name)
        result['scope_id'] = scope['scope_id']
        result['roi_id'] = roi.roi_id
        results.append(result)
    return results,pins


def synthetic(a,b,task):
    eps = F(1,2**100)
    identity = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1))

    def mesh(name,vertices,faces=((0,1,2),)):
        return {'name':name,'vertices':vertices,'triangles':faces}

    def task_case(label,occluders,expected,*,center=F(0),unknown=(),reverse=False):
        c = center
        square = ((c,c,0),(c+1,c,0),(c+1,c+1,0),(c,c+1,0))
        scene = {'objects':[mesh('task_roi',square,((0,1,2),(0,2,3))),*occluders]}
        parsed = a.geometry(scene)
        roi, = [r for r in a.partition_regions(parsed[0])[0] if r.object_index==0]
        base_camera = ((1,0,0,-c),(0,1,0,-c),(0,0,1,0),(0,0,0,1))
        cameras = {'views':[
            {'name':view,'direction_rational':direction,'view_matrix':matrix,
             'projection_matrix':identity,'size_px':[48,48]}
            for view,direction,matrix in (
                ('SCENE',(0,0,1),base_camera),('diagonal',(-2,3,4),base_camera),
                ('back',(0,0,-1),base_camera),('edge',(1,0,0),base_camera),
                ('offscreen',(0,0,1),((1,0,0,2-c),*base_camera[1:])),
            )]}
        row = compare(label,parsed,roi,cameras,a,b,task,unknown=unknown,reverse=reverse)
        statuses = {k:v['coverage']['status'] for k,v in row['directions'].items()}
        require(statuses['SCENE']==expected and statuses['back']=='back_facing'
                and statuses['edge']=='edge_on' and statuses['offscreen']=='outside_frustum',
                'synthetic_exact_state_not_exercised/'+label+'/'+str(statuses))
        return row

    contact = mesh('edge_contact',((1,0,F(1,4)),(2,0,F(1,4)),(1,1,F(1,4))))
    sliver = mesh('not_a_task_rectangle',((1-eps,0,F(1,4)),(2,0,F(1,4)),(1-eps,1,F(1,4))))
    depth = mesh('across_target_depth',((0,0,-eps),(1,0,eps),(0,1,eps)))
    tied = mesh('equal_depth',((0,0,0),(1,0,0),(0,1,0)))
    clip = mesh('cross_camera_plane',((0,0,F(2)),(1,0,F(1,4)),(0,1,F(1,4))))
    far = mesh('entirely_outside_depth_frustum',((0,0,2),(1,0,2),(0,1,2)))
    empty = mesh('unknown_empty_box',(),())
    front = mesh('no_rectangle_occluder_a',((0,0,F(1,4)),(1,0,F(1,4)),(0,1,F(1,4))))
    duplicate = mesh('no_rectangle_occluder_b',front['vertices'])
    c = F(10**20,3)
    wide = mesh('large_position_exact_sliver',
                ((c+1-eps,c,eps),(c+2,c,eps),(c+1-eps,c+1,eps)))
    rows = [
        task_case('zero_width_contact',(contact,empty),'complete'),
        task_case('tiny_positive_width_and_non_task_occluder',(sliver,),'positive_area_occlusion'),
        task_case('large_offset_exact_overlap',(wide,),'positive_area_occlusion',center=c),
        task_case('near_equal_and_crossing_depth',(tied,depth),'positive_area_occlusion'),
        task_case('equal_depth_has_no_positive_front',(tied,),'complete'),
        task_case('camera_clip_retain_crossing_triangle',(clip,),'positive_area_occlusion'),
        task_case('camera_clip_reject_outside_triangle',(far,),'complete'),
        task_case('unknown_object_box_retained',(front,),'positive_area_occlusion',unknown={1}),
        task_case('equal_geometry_uses_first_original_triangle',(front,duplicate),'positive_area_occlusion'),
        task_case('reversed_order_keeps_first_current_triangle',(front,duplicate),'positive_area_occlusion',reverse=True),
    ]
    for row,expected in zip(rows[-2:],(1,2),strict=True):
        hit = row['directions']['SCENE']['coverage']['first_blocker']
        require(hit['source_object_index']==expected,'synthetic_equal_geometry_order_control_missing')
    return rows


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--baseline',type=Path,required=True)
    cli.add_argument('--candidate',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_isolated_python_required')
    pins = [pin(Path(__file__))]
    a_binding,a = load(args.baseline,'A',(MOD,),pins)
    require(a_binding['preparation_git']==BASE,'wrong_baseline_product')
    b_binding = b = task = None
    if args.candidate:
        b_binding,b,task = load(args.candidate,'B',(MOD,TASK),pins)
        require(b_binding['dependency_root']==a_binding['dependency_root']
                and b_binding['source_sha256']!=a_binding['source_sha256'],'different_isolated_candidate_required')
    rows = {}
    for name in CASES:
        rows[name],source_pins = real_case(name,a,b,task)
        pins.extend(source_pins)
    controls = synthetic(a,b,task)
    checked = {'passed':True,'candidate_checked':bool(b),'baseline_git':BASE,
               'candidate_git':b_binding['preparation_git'] if b_binding else None,
               'installed_coverage_equal':bool(b),'real_cases':rows,'synthetic_controls':controls,
               'source_pins':pins,'new_Blender':0,'new_model':0,'new_raster':0}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(checked,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
    print('Exact coverage checks',len(rows),len(controls),'candidate',bool(b),pin(args.output)['sha256'])


if __name__=='__main__':
    main()
