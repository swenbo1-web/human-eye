"""Replay registered source-region frames in separately bound source ordinal domains."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/he_m4_source_region_visual_scope_proof_001')
INSTALL = Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product')
DEPENDENCIES = 'D:/he_anchor_001/venv/Lib/site-packages'
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
PRIVATE_SCOPE = 'offline_source_region_raster_domain_v1'

sys.path[:0] = [str(INSTALL), DEPENDENCIES]
import numpy as np
from human_eye_plugin import blender_host as host
from human_eye_plugin import source_region as region
from human_eye_plugin import attention_raster as raster
from human_eye_plugin.active_observation_host import source_binding
from human_eye_plugin.active_observation_images import SceneObservationImages, fingerprint
from human_eye_plugin.attention_rendering import _contrasting_boundaries
from human_eye_plugin.query_policy import validate_source_region_query


def need(value, reason):
    if not value:
        raise ValueError(reason)


def pin(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def write(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as out:
        json.dump(value, out, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def checkpoint(_stage):
    pass


def viewport_certificate(bounds, pose):
    """Prove arithmetic legality and strict XY exclusion for one registered pose."""
    if bounds is None:
        return {'status': 'unknown', 'reason': 'finite_world_bounds_unavailable'}
    try:
        view, projection = (pose[key] for key in ('view_matrix','projection_matrix'))
        expected = [0., 0., 0., 1.]
        if (pose.get('projection') != 'orthographic'
                or any(type(m) is not list or len(m) != 4
                       or any(type(row) is not list or len(row) != 4 for row in m)
                       for m in (view, projection))
                or any(type(x) not in (int,float) or not math.isfinite(x)
                       for m in (view, projection) for row in m for x in row)
                or view[3] != expected or projection[3] != expected
                or projection[0][0] <= 0 or projection[1][1] <= 0
                or any(projection[i][j] != 0 for i in range(3) for j in range(3) if i != j)
                or any(projection[i][3] != 0 for i in range(2))):
            return {'status':'unknown','reason':'outside_registered_camera_domain'}
        intervals = []
        for i in range(3):
            view_interval = host._observation_affine_interval(bounds, view[i][:3], view[i][3])
            if view_interval is None:
                return {'status':'unknown','reason':'world_to_camera_interval_unavailable'}
            factor, shift = projection[i][i], projection[i][3]
            a,b = (value * factor for value in view_interval)
            if i < 2:
                # Match the installed diagonal XY multiplication and widen once.
                low = math.nextafter(min(a,b), -math.inf)
                high = math.nextafter(max(a,b), math.inf)
            else:
                low = math.nextafter(math.nextafter(min(a,b), -math.inf) + shift, -math.inf)
                high = math.nextafter(math.nextafter(max(a,b), math.inf) + shift, math.inf)
            if not math.isfinite(low) or not math.isfinite(high):
                return {'status':'unknown','reason':'nonfinite_viewport_extent'}
            intervals.append([low,high])
        for axis,(low,high) in zip(('x','y'),intervals):
            if high < -1 or low > 1:
                boundary = -1 if high < -1 else 1
                # Do not encode an infinite gap at the extreme finite endpoints.
                return {'status':'outside','axis':axis,'boundary':boundary,'ndc_intervals':intervals}
        return {'status':'intersecting_or_touching','ndc_intervals':intervals}
    except (TypeError, ValueError, OverflowError, IndexError, KeyError):
        return {'status':'unknown','reason':'unusable_viewport_bound'}


def owner_domain(identities, face_counts, kept_ordinals):
    ids, counts, kept = tuple(map(tuple,identities)), tuple(face_counts), tuple(kept_ordinals)
    need(len(ids) == len(counts) and 0 < len(ids) <= 256
         and all(len(i)==2 and all(type(s) is str and s for s in i) for i in ids)
         and len(set(ids))==len(ids) and len({i[0] for i in ids})==len(ids)
         and all(type(n) is int and n >= 0 for n in counts)
         and sum(counts) <= np.iinfo(np.int32).max, 'ambiguous_or_missing_current_source_rows')
    need(kept and all(type(i) is int and 0<=i<len(ids) for i in kept)
         and tuple(sorted(set(kept)))==kept,'derived_domain_must_preserve_original_object_order')
    return {'identities':ids,'faces':counts,'ordinals':kept,
            'full_offsets': (0,*np.cumsum(counts,dtype=np.int64).tolist()),
            'local_offsets': (0,*np.cumsum([counts[k] for k in kept],dtype=np.int64).tolist())}


def restore_owners(owners, triangles, domain):
    """Map local winners through counted source rows, never through object names."""
    kept = np.asarray(domain['ordinals'], dtype=np.int32)
    local = np.asarray(domain['local_offsets'], dtype=np.int64)
    world = np.asarray(domain['full_offsets'], dtype=np.int64)
    need(owners.dtype==triangles.dtype==np.int32 and owners.ndim==2 and owners.shape==triangles.shape
         and np.all(owners >= -1) and np.all(owners < len(kept)) and np.all(triangles >= -1)
         and np.array_equal(owners >= 0,triangles >= 0),'invalid_local_owner_buffer')
    active = owners >= 0
    indices = owners[active]
    faces = triangles[active].astype(np.int64) - local[indices]
    need(np.all((0<=faces) & (faces < local[indices+1]-local[indices])), 'local_owner_source_triangle_mismatch')
    original = kept[indices]
    global_triangle = world[original] + faces
    full_owner,full_triangle = owners.copy(),triangles.copy()
    full_owner[active],full_triangle[active] = original,global_triangle.astype(np.int32)
    return full_owner,full_triangle


def view_fingerprint(parent_binding, cameras, domain):
    return fingerprint({'scope':PRIVATE_SCOPE, 'parent':parent_binding, 'cameras':cameras,'domain':domain})


def camera_bounded_meshes(prepared, terminal):
    """Verify real world rows and reconstruct an outward local-box hypothesis."""
    actual = {o['object_id']:o for o in terminal['objects']}
    rows = prepared.binding['objects']
    need(len(actual)==len(terminal['objects'])==len(rows)
         and {r['host_id'] for r in rows}==set(actual),'terminal_current_object_directory_mismatch')
    display = prepared.binding['image_scope']['participation_mask']
    scale = terminal['source']['scale_length']
    tight, cheap, sizes = [],[],[]
    for i,(row,mesh) in enumerate(zip(rows,prepared.meshes,strict=True)):
        o = actual[row['host_id']]
        evaluated = o['evaluated']
        local = np.asarray(evaluated['vertices'], dtype=np.float64)
        worlds = np.asarray(evaluated['vertices_world_m'],dtype=np.float64)
        matrix = np.asarray(o['matrix_world'],dtype=np.float64)
        need(o['instance_id']==row['instance_id'] and o['name']==row['object_name']
             and type(o['visible_get']) is bool and o['visible_get'] is display[i]
             and np.array_equal(worlds,mesh.vertices)
             and np.array_equal(evaluated['triangles'],mesh.faces),
             'current_terminal_display_mesh_or_source_index_mismatch/'+str(i))
        need(np.array_equal((local @ matrix[:3,:3].T + matrix[:3,3])*scale,worlds),
             'terminal_local_to_world_reconstruction_mismatch/'+str(i))
        tight.append([np.min(worlds,axis=0).tolist(),np.max(worlds,axis=0).tolist()])
        corners = list(product(*zip(local.min(axis=0).tolist(),local.max(axis=0).tolist())))
        outward = host._acquisition_bounds(corners,o['matrix_world'],scale)
        if outward is not None:
            need(np.all((worlds>=outward[0]) & (worlds<=outward[1])),
                 'reconstructed_outward_world_box_excludes_actual_geometry/'+str(i))
        cheap.append(outward)
        sizes.append({'ordinal':i,'name':o['name'],'host_id':row['host_id'],'instance_id':row['instance_id'],
                      'displayed':display[i],'vertices':len(local),'triangles':len(mesh.faces),
                      'tight_bounds_source':'complete_terminal_evaluated_world_vertices',
                      'cheap_bounds_source':'terminal_local_vertex_extrema_and_outward_affine_hypothesis'})
    return tight,cheap,sizes


def selection_for(prepared, cameras, bounds, protected):
    need(tuple(pose['name'] for pose in cameras['views'])==VIEWS,'six_registered_camera_order_required')
    proof = []
    for index, box in enumerate(bounds):
        certificates = {pose['name']:viewport_certificate(box,pose) for pose in cameras['views']}
        all_out = all(value['status']=='outside' for value in certificates.values())
        installed = host._observation_outside_xy_viewports(box,cameras)[0]
        need(not all_out or installed,'offline_exclusion_disagrees_with_installed_all_six')
        proof.append({'ordinal':index,'protected':index in protected,'all_six_outside':all_out,
                      'installed_all_six_outside':installed,'views':certificates})
    global_kept = tuple(row['ordinal'] for row in proof if row['protected'] or not row['all_six_outside'])
    by_view = {view:tuple(row['ordinal'] for row in proof
                         if row['protected'] or row['views'][view]['status']!='outside') for view in VIEWS}
    return global_kept,by_view,proof


def source_scope(prepared, cameras, kept, output, *, original=False):
    parent_display = prepared.binding['image_scope']
    ids = [(row['host_id'],row['instance_id']) for row in prepared.binding['objects']]
    domain = owner_domain(ids,[len(mesh.faces) for mesh in prepared.meshes],kept)
    mask = tuple(parent_display['participation_mask'][i] for i in kept)
    if original:
        need(kept==tuple(range(len(ids))) and cameras==prepared.cameras,'original_scope_needs_complete_original_binding')
        display,scene,candidate = (parent_display,prepared.binding['geometry_identity'],prepared.binding['camera_identity'])
    else:
        scope = view_fingerprint(prepared.binding['binding_sha256'],cameras,domain)
        display = {'scope':PRIVATE_SCOPE,'status':'captured','participation_mask':list(mask),
                   'parent_display_identity':prepared.binding['display_identity'],
                   'source_domain':scope,'original_ordinals':list(kept)}
        display['identity'] = fingerprint(display)
        scene,candidate = scope,fingerprint({'cameras':cameras,'private_scope':scope})
    objects = tuple(prepared.objects[i] for i in kept)
    meshes = tuple(prepared.meshes[i] for i in kept)
    image_builder = SceneObservationImages(objects,cameras,output,scene_identity=scene,candidate_identity=candidate,
        display_identity=display['identity'],object_mask=mask,image_scope=display,
        _prepared_meshes=meshes,_measure_stages=True)
    source = replace(prepared,objects=objects,meshes=meshes,object_index=kept.index(prepared.object_index),
                     binding={**prepared.binding,'image_scope':display},cameras=cameras,images=None,observation=None)
    return source,mask,domain,image_builder


def world_positions(depth, owners, pose):
    """Unproject real sample centers using the producer's size-1 pixel convention."""
    rows,cols = np.nonzero(owners>=0)
    width = depth.shape[1]
    height = depth.shape[0]
    matrix = np.asarray(pose['projection_matrix'],dtype=np.float64)
    views = np.asarray(pose['view_matrix'],dtype=np.float64)
    x = ((cols+0.5)*2/(width-1)-1-matrix[0,3])/matrix[0,0]
    y = (1-(rows+0.5)*2/(height-1)-matrix[1,3])/matrix[1,1]
    view_points = np.column_stack((x,y,-depth[rows,cols]))
    result = (view_points-views[:3,3]) @ np.linalg.inv(views[:3,:3]).T
    need(np.isfinite(result).all(),'nonfinite_world_pixel_reconstruction')
    return result


def raster_row(scope, name, *, unproject=True):
    source,mask,domain,renderer=scope
    started=perf_counter_ns()
    frame=renderer.render_view(name)
    made=perf_counter_ns()
    arrays=renderer.validate_frame(frame)
    reopened=perf_counter_ns()
    owners, triangles = restore_owners(arrays['owners'],arrays['triangle_ids'],domain)
    sizes = {key:pin(frame[field]) for key,field in (('png','image_path'),('npz','arrays_path'))}
    original_target = domain['ordinals'][source.object_index]
    selected=(owners==original_target)&np.isin(triangles,
        np.asarray(source.source_triangle_indices,dtype=np.int32)+domain['full_offsets'][original_target])
    visible=sorted(map(int,np.unique(triangles[selected])-domain['full_offsets'][original_target]))
    pixels = int(np.sum(selected))
    contrast = int(np.sum(selected & _contrasting_boundaries(arrays['color'],selected)))
    proof = {'selected_pixels':pixels,'contrasting_pixels':contrast,'visible_source_triangles':len(visible),
             'visible_source_triangles_sha256':fingerprint(visible),'frame_identity':frame['frame_identity'],
             'owner_identity':frame['owner_mapping_identity'],'image_scope_identity':frame['image_scope_identity'],
             'stage_ns':{k:v['elapsed_ns'] for k,v in frame['stages'].items()},
             'construction_ns':made-started,'independent_file_validation_ns':reopened-made,**sizes}
    result = {'color':arrays['color'],'depth':arrays['depth'],'owner':owners,'triangle':triangles,
              'patch':arrays['patch_owners'],'proof':proof}
    if unproject:
        result['world'] = world_positions(arrays['depth'],owners,frame['pose'])
    return result


def same_arrays(a,b):
    return {name:np.array_equal(a[name].view(np.uint64) if a[name].dtype==np.float64 else a[name],
                                 b[name].view(np.uint64) if b[name].dtype==np.float64 else b[name])
            for name in ('color','depth','owner','triangle','patch','world')}


def array_hashes(row):
    return {name:sha256(row[name].tobytes()).hexdigest()
            for name in ('color','depth','owner','triangle','patch','world')}


def sample_votes(scope):
    source,mask,_,_=scope
    started=perf_counter_ns()
    if not mask[source.object_index]:
        return {'votes':{},'actual_search_votes':{},'choice':'SCENE','elapsed_ns':0}
    selected = np.zeros(len(source.meshes[source.object_index].faces),dtype=np.bool_)
    selected[list(source.source_triangle_indices)]=True
    votes = {}
    with np.errstate(over='raise',divide='raise',invalid='raise'):
        for pose in source.cameras['views']:
            votes[pose['name']]=raster._sparse_attention_owner_count(
                source.meshes,pose,mask,source.object_index,selected,checkpoint)
    all_vote_ns=perf_counter_ns()-started
    started=perf_counter_ns()
    choice,actual = raster.select_sparse_attention_view(source.meshes,source.cameras['views'],
         object_mask=mask,object_index=source.object_index,source_triangle_indices=source.source_triangle_indices,
         check_budget=checkpoint)
    need(all(votes[name]==count for name,count in actual.items()),'production_sparse_vote_shape_changed')
    return {'votes':votes,'actual_search_votes':actual,'choice':choice,'elapsed_ns':perf_counter_ns()-started,
            'all_six_vote_diagnostic_ns':all_vote_ns}


def geometry_route(scope, rows, votes):
    source,mask,domain,_=scope
    local = region._selected_rectangle(source) if mask[source.object_index] else None
    if local is None:
        return {'method':'sparse_samples' if mask[source.object_index] else 'hidden_sample',
                'statuses':{},'view':votes['choice']}
    front=region._displayed_front_triangles(source,local,checkpoint)
    statuses = {}
    for pose in source.cameras['views']:
        outcome=region._classify_view(local,front,pose,checkpoint)
        for key in ('first_blocker','first_tie'):
            if key in outcome:
                outcome[key]['object_index']=domain['ordinals'][outcome[key]['object_index']]
        statuses[pose['name']]=outcome
    complete = [name for name,outcome in statuses.items() if outcome['status']=='complete']
    witness = next((name for name in complete if rows[name]['proof']['selected_pixels']>=region._MIN_SURFACE_PIXELS
                    and rows[name]['proof']['contrasting_pixels']>=region._MIN_BOUNDARY_PIXELS),None)
    view=witness or (max(complete,key=lambda name:rows[name]['proof']['selected_pixels']) if complete else 'SCENE')
    return {'method':'exact_rectangle_then_pixels','statuses':statuses,'view':view,'complete_witness':witness}


def prepare_case(case):
    capture = case['capture']
    archived = case['producer']
    parent=source_binding(capture)
    start=perf_counter_ns()
    order=region.ordered_geometry_identity(capture,parent)
    query=validate_source_region_query(case['query'])
    if 'region' in query:
        reference,_,validation=region.resolve_region_selection(capture,query['region'],parent,order,checkpoint)
        query={key:value for key,value in query.items() if key!='region'} | {'region_ref':reference}
    else:
        region.validate_region_ref(capture,query['region_ref'],_binding=parent,_ordered_geometry_sha256=order)
        validation=None
    prepared=region.prepare_region(capture,query,_binding=parent,_validated_region_ref=True,
                                  _ordered_geometry_sha256=order,_scene_validation_stage=validation)
    prep_wall=perf_counter_ns()-start
    original=archived['binding']
    keys=('ordered_geometry_sha256','geometry_identity','camera_identity','camera_specification',
          'display_identity','image_scope','binding_sha256','scene_revision','document_epoch')
    need(prepared.region_ref==archived['region_ref'] and
         all(prepared.binding[k]==original[k] for k in keys),'original_producer_reference_or_view_binding_mismatch')
    need(prepared.source_mapping==archived['source_mapping'],'original_prepared_source_mapping_mismatch')
    return prepared,query,prep_wall


def frame_against_archived(case,prepared,scope,rows):
    producer=case['producer']
    frames=producer['frames']
    need(len(frames)==1,'one_original_source_region_frame_required')
    original=frames[0]
    view=original['view_name']
    renderer=source_scope(prepared,prepared.cameras,scope[2]['ordinals'],
                         Path(original['arrays_path']).parent,original=True)[3]
    need(original['pose']==next(p for p in prepared.cameras['views'] if p['name']==view),
         'archived_pose_not_current_original')
    png,npz=case['png'],case['npz']
    need(Path(original['image_path'])==Path(png) and Path(original['arrays_path'])==Path(npz),
         'archived_frame_paths_mismatch')
    old_png,old_npz=pin(png),pin(npz)
    need(old_png['sha256']==original['image_sha256'] and old_npz['sha256']==original['arrays_sha256'],
         'archived_PNG_or_NPZ_hash_changed')
    saved=renderer.validate_frame(original)
    row=rows[view]
    old={'color':saved['color'],'depth':saved['depth'],'owner':saved['owners'],
         'triangle':saved['triangle_ids'],'patch':saved['patch_owners'],
         'world':world_positions(saved['depth'],saved['owners'],original['pose'])}
    eq=same_arrays(row,old)
    need(all(eq.values()) and Path(row['proof']['png']['path']).read_bytes()==Path(png).read_bytes(),
         'original_raw_frame_or_actual_raster_mismatch/'+view)
    visible=producer['facts']['visibility']
    need(visible['selected_surface_pixels']==row['proof']['selected_pixels']
         and fingerprint(visible['visible_source_triangle_indices'])==row['proof']['visible_source_triangles_sha256'],
         'original_frame_selected_source_pixels_mismatch')
    stages={}
    for key,stage in producer['generation_stages'].items():
        if type(stage) is dict and 'elapsed_ns' in stage:
            need(stage['closed_ns']-stage['started_ns']==stage['elapsed_ns'],'old_invalid_stage_interval')
            stages[key]=stage['elapsed_ns']
    return {'view':view,'png':old_png,'npz':old_npz,'original_scalar_stage_ns':stages,
            'original_frame_stage_ns':{k:v['elapsed_ns'] for k,v in original['stages'].items()},
            'comparison_with_full_replay':eq,'selected_pixels':visible['selected_surface_pixels'],
            'original_global_owner_identity':original['owner_mapping_identity']}


def regular_measurement(prepared,query,scope,archived):
    """Measure only target selection and retained whole reference, compare original proof."""
    need('reference' in query and archived,'original_reference_measurement_required')
    reference=region._object_index(prepared.binding,query['reference'])
    source,_,domain,_=scope
    need(reference in domain['ordinals'],'whole_reference_discarded')
    begin=perf_counter_ns()
    work={'surface_pair_count':0}
    got=region._measure_region_surfaces(source.region_mesh,source.meshes[domain['ordinals'].index(reference)],
                                       source.source_triangle_indices,source.source_vertex_indices,checkpoint,work)
    stage=perf_counter_ns()-begin
    fact=region._surface_proximity_fact(got['surface'])
    need(fact==archived['facts']['surface_proximity']
         and got['nearest_witness_source']==archived['source_mapping']['nearest_witness'],
         'independent_retained_reference_measurement_changed')
    return {'matches_original':True,'compute_ns':stage,'reference_ordinal':reference,
            'reference_drawn':bool(scope[1][domain['ordinals'].index(reference)]),
            'scope':'same actual selected triangles to same whole reference',
            'distance_m':fact['value']['distance_m'] if fact.get('status')=='measured' else None}


def stored_rows(scope):
    return {name:raster_row(scope,name) for name in VIEWS}


def original_scope_must_reject(scope,original):
    try:
        scope[3].validate_frame(original)
    except ValueError as error:
        return str(error)
    raise ValueError('derived_image_domain_accepted_original_frame_identity')


def memory_rows_for_pair(baseline,candidate,*,need_equal):
    controls={}
    for name in VIEWS:
        a,b=baseline[name],candidate[name]
        dim=same_arrays(a,b)
        png_same=a['proof']['png']['sha256']==b['proof']['png']['sha256']
        if need_equal:
            need(all(dim.values()) and png_same,'same_pose_replay_difference/'+name+'/'+str(dim))
        controls[name]={'equal':dim,'PNG_byte_identity':png_same,'full':a['proof'],'scoped':b['proof'],
                        'canonical_array_hashes':array_hashes(a),'scoped_canonical_array_hashes':array_hashes(b)}
    return controls


def render_same_camera(prepared,cameras,tight,protected,output,*,original=False):
    kept,per_view,certs=selection_for(prepared,cameras,tight,protected)
    full=tuple(range(len(prepared.meshes)))
    baseline=source_scope(prepared,cameras,full,output/'complete',original=original)
    subset=source_scope(prepared,cameras,kept,output/'common-subset')
    full_rows,subset_rows=stored_rows(baseline),stored_rows(subset)
    a,b=(sample_votes(v) for v in (baseline,subset))
    keys=('votes','actual_search_votes','choice')
    need(all(a[key]==b[key] for key in keys),'sparse_vote_or_selected_view_changed')
    route_a,route_b=geometry_route(baseline,full_rows,a),geometry_route(subset,subset_rows,b)
    need(route_a==route_b,'original_geometric_or_pixel_view_selection_changed')
    views=memory_rows_for_pair(full_rows,subset_rows,need_equal=True)
    extra={}
    for name in VIEWS:
        if per_view[name]==kept:
            extra[name]={'used_common_subset':True}
            continue
        local=source_scope(prepared,cameras,per_view[name],output/'view-subsets'/name)
        shot=raster_row(local,name)
        dim=same_arrays(full_rows[name],shot)
        png_same=full_rows[name]['proof']['png']['sha256']==shot['proof']['png']['sha256']
        need(all(dim.values()) and png_same,'per_view_owner_or_visibility_changed/'+name)
        extra[name]={'used_common_subset':False,'equal':dim,'PNG_byte_identity':png_same,'scoped':shot['proof'],
                     'canonical_array_hashes':array_hashes(shot)}
    result={'kept_ordinals':list(kept),'per_view_kept_ordinals':per_view,'certificates':certs,
            'actual_search_full':a,'actual_search_common_subset':b,'actual_route':route_a,
            'same_camera_by_view':views,'per_view_replay':extra}
    return result,baseline,subset,full_rows


def with_counts(table, rows):
    def sum_rows(kept):
        retained = [rows[i] for i in kept]
        return {'objects':len(retained),'displayed_objects':sum(row['displayed'] for row in retained),
                'vertices':sum(row['vertices'] for row in retained),'triangles':sum(row['triangles'] for row in retained),
                'estimated_array_JSON_bytes':sum(row['estimated_array_JSON_bytes'] for row in retained)}
    totals=sum_rows(range(len(rows)))
    counts={'complete':totals,'common':sum_rows(table['kept_ordinals']),
            'by_view':{view:sum_rows(values) for view,values in table['per_view_kept_ordinals'].items()}}
    counts['all_six_saved']={k:total-counts['common'][k] for k,total in totals.items()}
    counts['by_view_saved']={v:{k:total-counts['by_view'][v][k] for k,total in totals.items()} for v in VIEWS}
    return counts


def camera_change(original_cameras,new_cameras,old_rows,new_rows):
    result={}
    for old,new in zip(original_cameras['views'],new_cameras['views'],strict=True):
        name=old['name']
        need(name==new['name'],'cheap_camera_view_order_changed')
        a,b=old_rows[name],new_rows[name]
        valid=(a['owner']>=0)&(b['owner']>=0)&(a['triangle']==b['triangle'])
        shared=np.where(valid,a['owner'],-1)
        diff=world_positions(a['depth'],shared,old)-world_positions(b['depth'],shared,new)
        maxima=float(np.max(np.abs(diff))) if diff.size else None
        result[name]={
            'view_matrix_bitwise_equal':same_matrix(old['view_matrix'],new['view_matrix']),
            'projection_bitwise_equal':same_matrix(old['projection_matrix'],new['projection_matrix']),
            'near_m':[old['near_m'],new['near_m']],'far_m':[old['far_m'],new['far_m']],
            'eye_world_m':[old['eye'],new['eye']],'XY_span_m':[old['span'],new['span']],
            'equal':same_arrays(a,b),'shared_owner_triangle_pixel_count':int(valid.sum()),
            'common_owner_world_max_component_delta_m':maxima,
            'RGB_change_pixels':int(np.count_nonzero(np.any(a['color']!=b['color'],axis=2))),
            'depth_bit_change_pixels':int(np.count_nonzero(a['depth'].view(np.uint64)!=b['depth'].view(np.uint64))),
            'owner_change_pixels':int(np.count_nonzero(a['owner']!=b['owner'])),
            'triangle_change_pixels':int(np.count_nonzero(a['triangle']!=b['triangle'])),
            'PNG_byte_identity':a['proof']['png']['sha256']==b['proof']['png']['sha256'],
        }
    return result


def same_matrix(a,b):
    return np.array_equal(np.asarray(a,dtype=np.float64).view(np.uint64),np.asarray(b,dtype=np.float64).view(np.uint64))


def run_case(case, output):
    start=perf_counter_ns()
    label=case['label']
    prepared,query,prep_ns=prepare_case(case)
    target=prepared.object_index
    reference=region._object_index(prepared.binding,query['reference'])
    need(target!=reference,'source_region_target_reference_not_distinct')
    protected={target,reference}
    clock=perf_counter_ns()
    tight,cheap,objects=camera_bounded_meshes(prepared,case['terminal'])
    bounds_ns=perf_counter_ns()-clock
    for row,mesh in zip(objects,prepared.meshes,strict=True):
        row['estimated_array_JSON_bytes']=len(json.dumps(
            {'vertices':mesh.vertices.tolist(),'faces':mesh.faces.tolist()},separators=(',',':'),allow_nan=False).encode())
    old,full_scope,old_subset,old_rows=render_same_camera(
        prepared,prepared.cameras,tight,protected,output/'original-tight',original=True)
    archived=frame_against_archived(case,prepared,full_scope,old_rows)
    need(old['actual_route']['view']==archived['view'],'actual_archived_view_selection_not_reproduced')
    producer_frame=case['producer']['frames'][0]
    old['cross_scope_original_frame_rejection']=original_scope_must_reject(old_subset,producer_frame)
    primary=regular_measurement(prepared,query,old_subset,case['producer']['task_result'])
    old['counts']=with_counts(old,objects)

    same_original_cheap={}
    cheap_kept,per_cheap,proof_cheap=selection_for(prepared,prepared.cameras,cheap,protected)
    same_original_cheap={'kept_ordinals':cheap_kept,'per_view_kept_ordinals':per_cheap,'certificates':proof_cheap}
    same_original_cheap['counts']=with_counts(same_original_cheap,objects)
    if cheap_kept!=tuple(old['kept_ordinals']) or per_cheap!=old['per_view_kept_ordinals']:
        again,_,candidate,_=render_same_camera(prepared,prepared.cameras,cheap,protected,output/'original-cheap')
        same_original_cheap['replay']=again
        same_original_cheap['cross_scope_original_frame_rejection']=original_scope_must_reject(candidate,producer_frame)
    else:
        same_original_cheap['same_scope_as_original_tight_replay']=True

    extra={}
    if any(box is None for box in cheap):
        extra={'status':'unknown_cheap_camera_depth_not_available'}
    else:
        clock=perf_counter_ns()
        cams=host._observation_target_cameras(prepared.region_mesh.vertices.tolist(),cheap)
        camera_ns=perf_counter_ns()-clock
        cams.update(schema='offline-source-region-conservative-camera-v1',
                    scope='same_source_region_XY_reconstructed_conservative_scene_depth')
        new,_,candidate,new_rows=render_same_camera(prepared,cams,cheap,protected,output/'conservative-camera')
        new['counts']=with_counts(new,objects)
        new['cross_scope_original_frame_rejection']=original_scope_must_reject(candidate,producer_frame)
        extra={'status':'passed_separate_camera_scope','preparation_ns':camera_ns,'camera_digest':fingerprint(cams),
               'camera_inputs':{'XY_target':'same_compact_selected_ordered_world_vertices',
                                'depth':'all_objects_outward_local_box_affine_world'},
               'against_original_full_raster':camera_change(prepared.cameras,cams,old_rows,new_rows),
               'same_new_camera':new}
    return {'label':label,'passed':True,'source_proof':case['proof'],
            'target_ordinal':target,'reference_ordinal':reference,'objects':objects,
            'prepared_original_ns':prep_ns,'bounds_original_readback_and_affine_ns':bounds_ns,
            'runtime_capture_not_executed':True,'actual_archived_frame':archived,
            'original_camera_tight_world':old,'original_camera_cheap_hypothesis':same_original_cheap,
            'retained_measurement':primary,'separate_conservative_camera':extra,
            'offline_case_window_ns':perf_counter_ns()-start}
