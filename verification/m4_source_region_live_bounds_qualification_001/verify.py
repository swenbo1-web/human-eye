"""Verify the cold bound probe independently against the original source and NumPy tight bounds."""

from hashlib import sha256
import json
import math
from pathlib import Path
from runpy import run_path
import struct

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'm4_source_region_visual_scope_proof_001'
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
SCHEMA = 'm4-live-bounds-diagnostic-v1'

# Reuse the already accepted, all-axis finite viewport proof and installed runtime.
VISUAL = run_path(str(PRIOR / 'proof.py'))
np = VISUAL['np']
host = VISUAL['host']


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def read_pinned(record):
    actual = pin(record['path'])
    need(all(actual[key] == record[key] for key in ('bytes', 'sha256')), 'pinned_source_changed/' + record['path'])
    return read(record['path'])


def same_bits(first, second):
    a, b = (np.asarray(value, dtype=np.float64) for value in (first,second))
    return a.shape==b.shape and np.array_equal(a.view(np.uint64),b.view(np.uint64))


def bit_triplets(points):
    return [[struct.pack('>d', float(value)).hex() for value in row] for row in points]


def numpy_tight(world):
    points = np.asarray(world, dtype=np.float64)
    need(points.ndim==2 and points.shape[1]==3 and len(points)>0 and np.isfinite(points).all(),
         'finite_full_evaluated_world_rows_required')
    return [points.min(axis=0).tolist(),points.max(axis=0).tolist()]


def exact_axis_modes(matrix):
    m = np.asarray(matrix, dtype=np.float64)
    if m.shape!=(4,4) or not np.isfinite(m).all() or m[3].tolist() != [0.,0.,0.,1.]:
        return None
    support = [tuple(col for col in range(3) if float(m[axis,col])!=0.) for axis in range(3)]
    return support


def local_box(corners):
    try:
        points = [tuple(point) for point in corners]
        if (len(points)!=8 or any(len(row)!=3 or any(type(v) not in (int,float) or not math.isfinite(v)
                                                   for v in row) for row in points)
                or all(row==(-1.,-1.,-1.) for row in points)):
            return None
        lo,hi=([fn(row[i] for row in points) for i in range(3)] for fn in (min,max))
        expected = {(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])}
        return [lo,hi] if set(points)==expected else None
    except (TypeError,ValueError,OverflowError,IndexError):
        return None


def axis_candidate_value(corners, matrix, scale):
    box=local_box(corners)
    modes=exact_axis_modes(matrix)
    if box is None or modes is None or any(len(row)>1 for row in modes) or not math.isfinite(scale) or scale<=0:
        return None
    low,high=[],[]
    for index,active in enumerate(modes):
        row=matrix[index]
        vals=[]
        for end in (0,1):
            p=list(box[0])
            if active:
                p[active[0]]=box[end][active[0]]
            # This reproduces the original sum/multiply order. The local
            # authority for ambiguous zero signs is always the NumPy scan.
            vals.append((sum(row[k]*p[k] for k in range(3))+row[3])*scale)
        if any(not math.isfinite(v) for v in vals):
            return None
        low.append(min(vals))
        high.append(max(vals))
    return [low,high]


def contains(points, bounds):
    if bounds is None:
        return False
    full=np.asarray(points,dtype=np.float64)
    lo,hi=np.asarray(bounds,dtype=np.float64)
    return bool(np.isfinite(full).all() and np.isfinite(lo).all() and np.isfinite(hi).all()
                and ((lo<=full)&(full<=hi)).all())


def materialized_stage(row):
    return (type(row) is dict and all(type(row.get(key)) is int for key in ('started_ns','closed_ns','elapsed_ns'))
            and 0<=row['started_ns']<=row['closed_ns']
            and row['closed_ns']-row['started_ns']==row['elapsed_ns'])


def source_rows(terminal):
    rows = terminal['objects']
    vals = {r['object_id']:r for r in rows}
    need(len(vals)==len(rows) and rows, 'duplicate_or_missing_real_terminal_rows')
    return vals


def comparable_object(observed, actual, historical=None):
    evaluated=actual['evaluated']
    need(observed['instance_id']==actual['instance_id'] and observed['name']==actual['name']
         and same_bits(observed['matrix_world'],actual['matrix_world']),
         'actual_same_slot_instance_or_pose_mismatch/'+observed['name'])
    if historical is not None:
        old_eval=historical['evaluated']
        need(observed['name']==historical['name'] and same_bits(observed['matrix_world'],historical['matrix_world'])
             and same_bits(evaluated['vertices'],old_eval['vertices'])
             and same_bits(evaluated['vertices_world_m'],old_eval['vertices_world_m'])
             and evaluated['triangles']==old_eval['triangles'],
             'live_immutable_asset_ordered_geometry_differs_from_archived_source/'+observed['name'])


def old_camera_equal(a,b):
    """Check bit-exact viewport and clip fields, rather than Python signed-zero equality."""
    need(tuple(v['name'] for v in a['views'])==tuple(v['name'] for v in b['views'])==VIEWS,
         'six_pose_order_changed')
    fields=('view_matrix','projection_matrix','near','far','near_m','far_m','min_camera_depth_m',
            'max_camera_depth_m','camera_eye_world_m','half_span_m')
    return {
        pose['name']:{field:same_bits(pose[field],prior[field]) for field in fields}
        | {'size_px':pose['size_px']==prior['size_px']} for pose,prior in zip(a['views'],b['views'],strict=True)
    }


def poses_pass(values):
    return all(all(props.values()) for props in values.values())


def retention(cameras, bounds, protected):
    retained, per_view, unknown = [],{v:[] for v in VIEWS},[]
    evidence={}
    for i, box in enumerate(bounds):
        certs={v['name']:VISUAL['viewport_certificate'](box,v) for v in cameras['views']}
        all_outside=all(row['status']=='outside' for row in certs.values())
        if all_outside:
            need(host._observation_outside_xy_viewports(box,cameras)[0],'full_three_axis_proof_inconsistent')
        if any(row['status']=='unknown' for row in certs.values()): unknown.append(i)
        if i in protected or not all_outside: retained.append(i)
        for name,test in certs.items():
            if i in protected or test['status']!='outside': per_view[name].append(i)
        evidence[str(i)]=certs
    return {'kept':retained,'per_view':per_view,'uncertain':unknown,'viewport_evidence':evidence}


def closed_box_indices(world, faces, query):
    points,tri = np.asarray(world,dtype=np.float64), np.asarray(faces,dtype=np.int64)
    box=query['region']['world_box_m']
    need(tri.ndim==2 and tri.shape[1]==3 and len(tri)>0 and ((tri>=0)&(tri<len(points))).all(),
         'independent_selected_triangle_topology_unavailable')
    lo,hi=(np.asarray(box[key],dtype=np.float64) for key in ('min','max'))
    need(lo.shape==hi.shape==(3,) and np.isfinite(lo).all() and np.isfinite(hi).all() and (lo<=hi).all(),
         'registered_closed_box_is_invalid')
    inside=((lo<=points)&(points<=hi)).all(axis=1)
    return np.flatnonzero(inside[tri].all(axis=1)).tolist()


def select_registered(rows, spec):
    need(type(spec) is dict and set(spec) in ({'name'},{'id'}),'registered_exact_object_selector_required')
    key,=spec
    field = 'name' if key=='name' else 'object_id'
    options=[row['ordinal'] for row in rows if row[field]==spec[key]]
    need(len(options)==1,'registered_object_selector_missing_or_ambiguous')
    return options[0]


def validate_reconstructed_cameras(packet, request, fallback_bounds, truth_bounds, outer_bounds, terminals):
    result={}
    rows,truth=packet['objects'],packet['truth']
    actual_queries=packet['queries']
    need(len(actual_queries)==len(request['closed_cases'])==2,'registered_two_queries_required')
    for measured,old in zip(actual_queries,request['closed_cases'],strict=True):
        query=old['query']
        need(measured['query']==query,'working_query_not_registered')
        target=select_registered(rows,query['region']['object'])
        reference=select_registered(rows,query['reference'])
        need(target!=reference and measured['target_ordinal']==target
             and measured['reference_ordinal']==reference,'target_reference_source_binding_changed')
        measured_target=truth[target]
        faces=measured_target['target_triangles']
        actual_target=terminals[rows[target]['object_id']]['evaluated']
        need(faces==actual_target['triangles'],'target_triangles_not_actual_current_source_order')
        selected=closed_box_indices(measured_target['world_vertices'],faces,query)
        need(selected and selected==measured['source_triangle_indices']==old['source_triangle_indices'],
             'queried_source_triangle_rows_changed')
        vertices=sorted({v for i in selected for v in faces[i]})
        world=[measured_target['world_vertices'][i] for i in vertices]
        original=host._observation_target_cameras(world,truth_bounds)
        fallback=host._observation_target_cameras(world,fallback_bounds)
        prior_pose=old_camera_equal(original,old['old_camera_specification'])
        replay_pose=old_camera_equal(original,fallback)
        need(poses_pass(prior_pose) and poses_pass(replay_pose),'original_camera_not_bit_preserved/'+old['label'])
        protected={target,reference}
        original_roster=retention(original,truth_bounds,protected)
        fallback_roster=retention(fallback,fallback_bounds,protected)
        outer_roster=retention(original,outer_bounds,protected)
        need(original_roster['kept']==old['original_kept_ordinals']==fallback_roster['kept']
             and original_roster['per_view']==fallback_roster['per_view'],
             'current_registered_viewport_candidate_roster_changed/'+old['label'])
        need(set(original_roster['kept'])<=set(outer_roster['kept']),
             'outward_only_certificate_pruned_original_candidate/'+old['label'])
        result[old['label']]={
            'selected_triangle_count':len(selected),'selected_vertex_count':len(vertices),
            'target_ordinal':target,'reference_ordinal':reference,
            'reference_image_participates':terminals[rows[reference]['object_id']]['visible_get'],
            'historical_camera_and_current_truth_bit_equality':prior_pose,
            'hybrid_tight_after_required_scan_bit_equality':replay_pose,
            'actual_original_and_hybrid_kept':original_roster['kept'],
            'conservative_exclusion_using_unchanged_original_matrices':outer_roster['kept'],
            'per_view_hybrid_kept':fallback_roster['per_view'],
            'per_view_outer_kept':outer_roster['per_view'],
        }
    return result


def verify_tally(counter, indices, truth, *, faces):
    expect_vertices=sum(len(truth[i]['world_vertices']) for i in indices)
    triangulations=sum(truth[i]['target_triangles'] is not None for i in indices) if faces else 0
    triangle_rows=sum(len(truth[i]['target_triangles'] or ()) for i in indices) if faces else 0
    expected={
        'to_mesh_attempts':len(indices), 'to_mesh_allocations':len(indices),
        'clear_attempts':len(indices), 'to_mesh_clear':len(indices),
        'vertices_read':expect_vertices, 'world_transforms':expect_vertices,
        'triangulations':triangulations, 'triangle_rows_read':triangle_rows,
    }
    need(counter==expected,'to_mesh_allocation_cleanup_and_geometry_work_tally_mismatch')
    return expected


def bound_receipt(row, raw, expected_eval, scale):
    local,world=raw['local_vertices'],raw['world_vertices']
    need(same_bits(local,expected_eval['vertices']) and same_bits(world,expected_eval['vertices_world_m']),
         'same_window_full_truth_not_current_evaluated_source/'+row['name'])
    truth=numpy_tight(world)
    product_tight=raw['tight_world_bounds']
    py_bounds=[[reduce(p[k] for p in world) for k in range(3)] for reduce in (min,max)]
    need(same_bits(product_tight,py_bounds) and raw['tight_world_bounds_bits']==bit_triplets(product_tight),
         'signed_world_truth_serialization_mismatch/'+row['name'])
    corners,matrix=row['corners_local'],row['matrix_world']
    got_outward=row['outward_world_bounds']
    recomputed=host._acquisition_bounds(corners,matrix,scale)
    need((recomputed is None and got_outward is None)
         or (recomputed is not None and got_outward is not None and same_bits(got_outward,recomputed)),
         'installed_outward_interval_not_bound_to_actual_RNA_corners/'+row['name'])
    proven_outer=got_outward is not None and contains(world,got_outward)
    if got_outward is not None:
        need(proven_outer,'actual_bound_box_interval_fails_to_contain_world_geometry/'+row['name'])
    if corners is not None:
        need(row['corners_local_binary64']==[[float(value).hex() for value in p] for p in corners],
             'actual_RNA_corners_not_exactly_logged/'+row['name'])
    box=local_box(corners)
    local_exact=box is not None and np.asarray(box).tolist()==numpy_tight(local)
    axes=exact_axis_modes(matrix)
    need(axes==[tuple(a) for a in row['axis_support']] and row['axis_separable'] is all(len(a)<=1 for a in axes),
         'world_axis_separability_must_use_exact_nonzero_terms/'+row['name'])
    guess=row['tight_candidate_world']
    bit_match=guess is not None and same_bits(guess,truth)
    if guess is not None:
        endpoints=axis_candidate_value(corners,matrix,scale)
        need(endpoints is not None and proven_outer and same_bits(endpoints,guess)
             and row['tight_candidate_bits']==bit_triplets(guess) and row['axis_separable']
             and row['tight_fallback_reason'] is None and row['needs_vertices'] is False,
             'tight_candidate_did_not_come_from_allowed_exact_binary64_affine_branch/'+row['name'])
    else:
        need(row['needs_vertices'] is True and row['tight_fallback_reason'],
             'missing_exact_tight_candidate_untracked/'+row['name'])
    static=row['static_directory']
    original=expected_eval['polygons']
    all_triangles=all(len(poly)==3 for poly in original)
    counters=row['rna_counts']
    if counters['vertices'] is not None:
        need(counters=={'vertices':len(local),'loops':sum(len(poly) for poly in original),
                         'polygons':len(original),'triangle_upper':max(0,sum(len(poly)-2 for poly in original))},
             'cheap_directory_counts_not_actual_evaluated_source/'+row['name'])
        need(0<=counters['triangle_upper'] and len(expected_eval['triangles'])<=counters['triangle_upper'],
             'cheap_directory_triangle_upper_understates_actual_shape/'+row['name'])
    if static['eligible']:
        need(all_triangles and static['source_mode']=='evaluated_static' and static['error'] is None,
             'static_guard_admitted_incompatible_evaluated_source/'+row['name'])
    # Only the actual match, rather than the interval enclosure, establishes
    # this diagnostic result. This is not a general product admission proof.
    exact=local_exact and bit_match and proven_outer and row['axis_separable']
    return {
        'ordinal':row['ordinal'], 'name':row['name'],'object_id':row['object_id'],
        'instance_id':row['instance_id'],'visible':row['display']['visible_get'],
        'static_guard':static, 'current_polygons_all_triangles':all_triangles,
        'axis_separable':row['axis_separable'],'local_RNA_limits_equal_evaluated_extrema':local_exact,
        'installed_outward_bounds_contain_world':proven_outer, 'cheap_counts':counters,
        'candidate_ends_match_Numpy_binary64':bit_match,
        'candidate_qualified_numerically_this_window':exact,
        'candidate_qualified_under_static_guard_this_window':exact and static['eligible'],
        'candidate_matches_numeric_but_outside_static_guard':exact and not static['eligible'],
        'actual_point_only_fallback_reason':row['tight_fallback_reason'],
        'python_first_tie_and_numpy_tight_signed_bits_equal':same_bits(product_tight,truth),
        'numpy_tight_binary64':bit_triplets(truth),
    },truth


def compare_frame(row, terminal):
    expected=terminal['source']
    for field in ('scene','view_layer','view_layer_id','frame','unit_settings'):
        need(row[field]==expected[field],'same_slot_source_frame_mismatch/'+field)
    need(same_bits([row['subframe'],row['scale_length']],[expected['subframe'],expected['scale_length']]),
         'same_slot_subframe_or_unit_bits_mismatch')
    need(row['scene_id'] and row['depsgraph_id'], 'missing_current_scene_or_depsgraph_identity')


def verify_packet(packet, request, *, initial, terminal, offline=False):
    """Common verifier for archival RNA replay and the real host publication."""
    need(packet['schema']==SCHEMA and packet['status']=='complete' and packet['prepost_equal'] is True
         and [row['query'] for row in packet['queries']]==request['queries'],
         'registered_read_only_probe_or_closed_queries_mismatch')
    historical=read_pinned(request['terminal'])
    first,last,old=map(source_rows,(initial,terminal,historical))
    rows,truth=packet['objects'],packet['truth']
    ids=[r['object_id'] for r in rows]
    need(len(ids)==len(set(ids))==len(rows)==len(truth)==len(first)==len(last)==len(old)
         and set(ids)==set(first)==set(last)==set(old),
         'complete_current_instance_rows_not_original_geometry_roster')
    need([r['ordinal'] for r in rows]==[r['ordinal'] for r in truth]==list(range(len(rows)))
         and [r['object_id'] for r in truth]==ids,'same_window_object_ordinals_not_closed_source_order')
    identity,display=packet['identity'],packet['display']
    need(identity.get('capture_scope')=='complete_scene_meshes'
         and identity['object_instances']=={r['object_id']:r['instance_id'] for r in rows}
         and display['status']=='captured' and [r['host_id'] for r in display['objects']]==ids,
         'actual_current_instance_or_display_roster_mismatch')
    frame=packet['frame']
    for source in (initial,terminal):
        compare_frame(frame,source)
        need(source['source']['asset_sha256']==request['asset']['sha256'],
             'expected_read_only_asset_digest_not_current_slot')
    need(display['view_layer']=={'name':frame['view_layer'],'instance_id':frame['view_layer_id']},
         'display_not_current_locked_scene_layer')
    evidence,full_tight,outer=[],[],[]
    for index,(row,raw,vis) in enumerate(zip(rows,truth,display['objects'],strict=True)):
        oid=row['object_id']
        need(vis==row['display'] and vis['instance_id']==row['instance_id']
             and all(vis[key] is last[oid]['display'][key]==first[oid]['display'][key] for key in
                     ('hide_get','hide_viewport','hide_render'))
             and vis['visible_get'] is last[oid]['visible_get'] is first[oid]['visible_get'],
             'effective_visibility_not_from_same_window_or_current_slot/'+row['name'])
        comparable_object(row,first[oid],old[oid])
        comparable_object(row,last[oid],old[oid])
        need(row['evaluated_id'] and row['evaluated_data_id']
             and all(materialized_stage(rt) for rt in raw['stages'].values()),
             'missing_exact_evaluated_geometry_lifetime_or_stage_intervals')
        receipt,tight=bound_receipt(row,raw,last[oid]['evaluated'],frame['scale_length'])
        evidence.append(receipt)
        full_tight.append(tight)
        outer.append(row['outward_world_bounds'])
    targets={m['target_ordinal'] for m in packet['queries']}
    need({i for i,m in enumerate(truth) if m['target_triangles'] is not None}==targets,
         'unrelated_source_geometry_was_triangulated_or_missing_target_rows')
    fallback_indices=[i for i,r in enumerate(rows) if r['needs_vertices']]
    fallback=packet['fallbacks']
    need([r['ordinal'] for r in fallback]==fallback_indices,'actual_point_only_fallback_denominator_mismatch')
    for row in fallback:
        i=row['ordinal']
        need(row['vertices_scanned']==len(truth[i]['world_vertices'])
             and row['reason']==rows[i]['tight_fallback_reason']
             and same_bits(row['tight_world_bounds'],full_tight[i])
             and row['tight_world_bounds_bits']==bit_triplets(row['tight_world_bounds'])
             and all(materialized_stage(t) for t in row['stages'].values())
             and 'target_triangulation' not in row['stages'],
             'point_only_fallback_not_old_NumPy_exact_tight_bounds/'+rows[i]['name'])
    known_fallback={row['ordinal']:row['tight_world_bounds'] for row in fallback}
    valid_candidate=[r['candidate_qualified_numerically_this_window'] for r in evidence]
    hybrid=[row['tight_candidate_world'] if valid else known_fallback.get(i, full_tight[i])
            for i,(row,valid) in enumerate(zip(rows,valid_candidate,strict=True))]
    work=packet['work']
    stages=packet['stages']
    expected_light=verify_tally(work['point_only_fallback'],fallback_indices,truth,faces=False)
    expected_truth=verify_tally(work['full_vertex_truth_and_target_faces'],list(range(len(rows))),truth,faces=True)
    need(work['depsgraph_fetches']==1 and work['directory_objects']==work['whole_truth_objects']==len(rows)
         and work['point_only_fallback_objects']==len(fallback_indices) and work['target_objects']==len(targets),
         'one_graph_and_directory_fallback_measurements_unbound')
    need(all(materialized_stage(v) for v in stages.values()),'host_probe_interval_clock_mismatch')
    window=stages['one_locked_host_window']
    need(all(window['started_ns']<=v['started_ns']<=v['closed_ns']<=window['closed_ns'] for v in stages.values()),
         'reported_stage_escaped_same_locked_host_window')
    camera=validate_reconstructed_cameras(packet,request,hybrid,full_tight,outer,last)
    return {
        'passed':True, 'scope':'archived_RNA_fixture_uses_real_same_packet_verifier' if offline else 'real_current_locked_host_window',
        'label':request['label'],'frame':frame,'rows':evidence,'camera':camera,
        'host_work':work,'host_stages':stages,'point_only_fallback_verified':expected_light,
        'full_truth_with_target_triangulations_verified':expected_truth,
        'cheap_directory_static_triangles':sum(r['static_guard']['eligible'] for r in evidence),
        'all_triangle_polygons_observed':sum(r['current_polygons_all_triangles'] for r in evidence),
        'numerically_retained_tight':sum(valid_candidate),
        'tight_inside_original_static_guard':sum(r['candidate_qualified_under_static_guard_this_window'] for r in evidence),
        'numerically_tight_but_guard_not_qualified':sum(r['candidate_matches_numeric_but_outside_static_guard'] for r in evidence),
        'candidate_invalid_needs_additional_fallback':sum(not valid and i not in known_fallback for i,valid in enumerate(valid_candidate)),
        'outer_known_proven':sum(r['installed_outward_bounds_contain_world'] for r in evidence),
        'triangle_count_semantics':'cheap upper counts never define exact source offsets',
    }


def verify_slot(slot, request, *, offline=False):
    """Check the exact current slot proof, leaving original binary data local."""
    slot=Path(slot).resolve(strict=True)
    if offline:
        initial=terminal=read_pinned(request['terminal'])
        source_pins={'archived_replay_fixture':request['terminal']}
    else:
        initial,terminal=[read(slot/name) for name in ('INITIAL_SOURCE.json','TERMINAL_SOURCE.json')]
        source_pins={name:pin(slot/name) for name in ('INITIAL_SOURCE.json','TERMINAL_SOURCE.json')}
    registered=read(slot/'BUSINESS_REQUEST.json')
    packet=read(slot/'DIAGNOSTIC.json')
    rpc=read(slot/'DIAGNOSTIC_RECEIPT.json')
    publication=read(slot/'SLOT_PUBLICATION.json')
    need(registered['label']==request['label'] and registered['queries']==request['queries'],
         'same_slot_registered_initial_request_changed')
    worker=publication['safe_worker_closed']
    window=packet['stages']['one_locked_host_window']
    need(publication['label']==registered['label'] and publication['offline'] is offline
         and publication['state']=='collected' and publication['deadline_ns']==registered['deadline_ns']
         and publication['request']==pin(slot/'BUSINESS_REQUEST.json')
         and rpc['request']==registered and rpc['outer_original_deadline_ns']==registered['deadline_ns']
         and rpc['diagnostic']==pin(slot/'DIAGNOSTIC.json') and worker['pid']==rpc['pid']
         and publication['launcher_close_receipt']['pid']==rpc['pid']
         and worker['original_deadline_ns']==registered['deadline_ns']
         and publication['started_ns']<=window['started_ns']<=window['closed_ns']<=worker['closed_ns']
         <=publication['closed_ns']<=registered['deadline_ns'],
         'same_locked_host_window_not_bound_to_current_process_close_and_absolute_deadline')
    if not offline:
        verify_live_guards(initial,terminal,source_pins,publication,rpc['pid'],window)
    result=verify_packet(packet,request,initial=initial,terminal=terminal,offline=offline)
    result['pins']={**source_pins, **{name:pin(slot/name) for name in
                                    ('BUSINESS_REQUEST.json','DIAGNOSTIC.json','DIAGNOSTIC_RECEIPT.json',
                                     'SLOT_PUBLICATION.json')}}
    result['freshness']=('archived_RNA_only_actual_native_bridge_and_worker_close' if offline
                         else 'same_process_live_initial_locked_probe_terminal_and_close')
    return result


def verify_live_guards(initial,terminal,pins,publication,pid,window):
    captures=publication['captures']
    for name,source in (('initial',initial),('terminal',terminal)):
        receipt=captures[name]
        source_pin=pins[name.upper()+'_SOURCE.json']
        need(receipt['pid']==source['source']['pid']==pid
             and receipt['sha256']==source_pin['sha256'] and receipt['bytes']==source_pin['bytes']
             and all(receipt[key]==source[key] for key in ('started_ns','display_read_closed_ns',
                                                           'geometry_read_closed_ns'))
             and receipt['started_ns']<=receipt['display_read_closed_ns']<=receipt['geometry_read_closed_ns']
             <=receipt['json_encoded_ns']<=receipt['file_closed_ns'],
             'independent_capture_not_bound_to_current_process_file_and_read_window/'+name)
    need(publication['started_ns']<=captures['initial']['started_ns']
         <=captures['initial']['file_closed_ns']<=window['started_ns']<=window['closed_ns']
         <=captures['terminal']['started_ns']<=captures['terminal']['file_closed_ns']
         <=publication['safe_worker_closed']['closed_ns'],
         'independent_live_captures_do_not_bracket_actual_locked_read')
    for key in ('source','objects','source_face_offsets','display_object_mask','display_scope',
                'display_read','scene_cameras','layer_collections'):
        # Stable serialization preserves the order of objects and signed zeros.
        need(json.dumps(initial[key],sort_keys=True,allow_nan=False)
             ==json.dumps(terminal[key],sort_keys=True,allow_nan=False),
             'guarded_native_evaluated_display_or_camera_state_changed/'+key)
