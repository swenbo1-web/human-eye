"""Finite task-native mathematics over a COMMON externally qualified capture.

This arm is not a source-admission service or a complete no-Human-Eye baseline.
Only independent exact SAT / NumPy QR-SVD geometry is used here. Complete rows
remain available to the trial's bound lookup; the initial report is task-sized.
No production B2, task-witness selector, prior answer or private truth is read.
"""
from __future__ import annotations
import copy,hashlib,json,math,time

from verification.deformation_anchor_oracle import (
    STABLE_KEYS,PIN_KEYS,digest,expected_geometry,expected_box,stable_object,affine_decimal,numeric_projection)
from verification.deformation_region_oracle import (
    transformed_vertices,triangle_box_sat,independent_metric)
from verification.model_trial.b3e_native import (
    validate_shared_capture,validate_policy,hex64,vec)


DEFAULT_THRESHOLDS=dict(high=1.1,low=.9)
STATES=('measured','collapsed','unknown')


class NativeTrialError(ValueError):
    def __init__(self,reason):
        self.reason=reason
        super().__init__('v21_trial_native_'+reason)


def need(value,reason):
    if not value:raise NativeTrialError(reason)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')


def _thresholds(value):
    value=DEFAULT_THRESHOLDS if value is None else value
    need(type(value) is dict and set(value)=={'high','low'} and all(type(v) in (int,float)
        and math.isfinite(v) for v in value.values()) and 0<value['low']<1<value['high'],'thresholds')
    return copy.deepcopy(value)


def _check(deadline_ns,clock_ns):
    need(type(deadline_ns) is int and clock_ns()<deadline_ns,'deadline')


def _catalog(packet,catalog):
    """Explicit coherence checks, independent of Python assertion optimization.

    A stable catalog may come from the just-completed common directory read.
    Its geometric fields and pins are recomputed for this qualified snapshot;
    this supplies no external acquisition authority or fresh worker window.
    """
    need(type(catalog) is dict and STABLE_KEYS<=set(catalog) and hex64(catalog.get('catalog_sha256')),'catalog_shape')
    need(catalog.get('execution_authority') is False and type(catalog.get('geometry_setters')) is int
        and catalog['geometry_setters']==0 and catalog.get('original_file_saved') is False,'readonly_catalog')
    need(catalog['schema']=='surface-deformation-anchor-catalog-v1'
        and catalog['catalog_sha256']==digest({key:catalog[key] for key in STABLE_KEYS}),'catalog_digest')
    raw=packet['inputs'];identity=packet['identity'];expected=expected_geometry(packet)
    source=dict(scene_sha256=identity['scene_sha256'],rig_object_id=stable_object(raw['rig']['name']),
        mesh_object_id=stable_object(raw['mesh']['name']),frame=copy.deepcopy(raw['frame']))
    need(catalog['source_ref']==source and catalog['operator_pins']=={key:identity[key] for key in PIN_KEYS},'catalog_source_binding')
    need(catalog['graph']==expected['graph'] and type(catalog['anchors']) is list
        and len(catalog['anchors'])==len(expected['anchors']),'catalog_geometry')
    for got,wanted in zip(catalog['anchors'],expected['anchors']):
        need(type(got) is dict and all(got.get(key)==value for key,value in wanted.items())
            and got.get('state')==('available' if wanted['reason'] is None else 'unavailable'),'catalog_geometry')
    used=sorted({index for triangle in raw['mesh']['triangles'] for index in triangle})
    points=[affine_decimal(packet['evaluated']['mesh_matrix_world'],packet['evaluated']['vertices'][index],
        raw['unit_scale_m']) for index in used]
    low=[min(point[axis] for point in points) for axis in range(3)]
    high=[max(point[axis] for point in points) for axis in range(3)]
    _,_,bounds_reason=numeric_projection(low+high)
    expected_bounds=dict(kind='referenced_current_triangle_hull_aabb',state='available' if bounds_reason is None else 'unavailable',
        reason=bounds_reason,bounds_world_m=expected['bounds_world_m'],
        **{key:expected[key] for key in ('vertices_total','surface_vertices_total','loose_vertices_excluded','triangles_total')})
    need(catalog['bounds']==expected_bounds,'catalog_bounds')
    counts=catalog['completeness'];available=sum(row['reason'] is None for row in expected['anchors'])
    need(counts==dict(bones_total=len(raw['rig']['bones']),anchors_total=len(expected['anchors']),
        anchors_available=available,anchors_unavailable=len(expected['anchors'])-available,
        anchors_omitted=0,graph_complete=True,anchors_complete=True),'catalog_completeness')
    need(catalog['coordinate_model']==dict(coordinate_space='current_world_m',
        position_model='nearest_binary64_from_exact_binary_affine',
        interval_model='outward_binary64_interval_for_published_numeric_inputs_not_physical_error'),'catalog_coordinates')
    need(catalog['scope']==dict(anchor_semantics='native_evaluated_bone_endpoints_only',
        bounds_semantics='referenced_current_triangle_hulls_not_volume',
        not_inferred=['anatomical_semantics','surface_location','damage','visibility','repair','editing_authority']),'catalog_scope')
    live=catalog.get('live_capture')
    need(hex64(catalog.get('source_sha256')) and type(live) is dict
        and set(live)=={'source_sha256','document_epoch','process_id'}
        and live['source_sha256']==catalog['source_sha256']
        and type(live['document_epoch']) is str and len(live['document_epoch'])>0
        and type(live['process_id']) is int and live['process_id']>0,'catalog_capture')
    return source


def _mixed(row,thresholds):
    return (row['state']=='measured' and row['principal_stretches'][0]>=thresholds['high']
        and row['principal_stretches'][1]<=thresholds['low'])


def _summary(rows,thresholds):
    counts={state:sum(row['state']==state for row in rows) for state in STATES}
    reasons={}
    for row in rows:
        if row['state']=='unknown':reasons[row['reason']]=reasons.get(row['reason'],0)+1
    mixed=[row['triangle'] for row in rows if _mixed(row,thresholds)]
    return dict(triangles_total=len(rows),states=counts,unknown_reasons=dict(sorted(reasons.items())),
        observation_state='empty' if not rows else 'partial' if counts['unknown'] else 'observed',
        has_confirmed_mixed_witness=True if mixed else None if counts['unknown'] else False,
        confirmed_mixed_witness_count=len(mixed),
        confirmation_scope='measured whole original triangles in this explicitly named scope; unknown is not negative')


def prepare_native_frame(packet,catalog,policy,*,deadline_ns,thresholds=None,clock_ns=time.perf_counter_ns):
    """Compute every original face once; no production B2 or live reread.

    The caller must bind raw files/profile/binary/runtime and actual capture
    receipts externally. This function establishes numeric/coherence facts, not
    source approval. ``raw_packet_sha256`` hashes canonical UTF8 JSON, not a file.
    """
    started=clock_ns();_check(deadline_ns,clock_ns);thresholds=_thresholds(thresholds)
    validate_shared_capture(packet);source=_catalog(packet,catalog);validate_policy(policy,catalog)
    anchor=next((row for row in catalog['anchors'] if row['anchor_id']==policy['anchor_id']),None)
    need(anchor is not None and anchor['state']=='available','anchor_unavailable')
    region=expected_box(anchor,policy['required_core_half_extents_m'])
    need(all(vec(row,3,1e9) for row in region['bounds'])
        and all(lo<hi for lo,hi in zip(*region['bounds'])),'core_region')
    _check(deadline_ns,clock_ns);validation_ns=clock_ns()-started;phase=clock_ns()
    mesh=packet['inputs']['mesh'];evaluated=packet['evaluated'];triangles=mesh['triangles']
    world=transformed_vertices(evaluated['vertices'],evaluated['mesh_matrix_world'],packet['inputs']['unit_scale_m'])
    unweighted={i for i,groups in enumerate(mesh['weights']) if not any(weight>0 for _,weight in groups)}
    members=[];facts={};sat_ns=metric_ns=0
    for index,triangle in enumerate(triangles):
        _check(deadline_ns,clock_ns);at=clock_ns()
        in_core=triangle_box_sat([world[i] for i in triangle],region['bounds']);sat_ns+=clock_ns()-at
        if in_core:members.append(index)
        at=clock_ns()
        row=independent_metric([mesh['vertices'][i] for i in triangle],[evaluated['vertices'][i] for i in triangle],
            unweighted=[i for i in triangle if i in unweighted])
        facts[index]=dict(row,triangle=index,vertices=triangle[:],in_core=in_core);metric_ns+=clock_ns()-at
        _check(deadline_ns,clock_ns)
    geometry_ns=clock_ns()-phase;phase=clock_ns()
    core=_summary([facts[index] for index in members],thresholds);global_summary=_summary(list(facts.values()),thresholds)
    topology=dict(vertices_total=len(mesh['vertices']),triangles=copy.deepcopy(triangles))
    report=dict(schema='v21-independent-native-frame-v1',source_ref=copy.deepcopy(source),
        source_observation_sha256=packet['source_sha256'],catalog_sha256=catalog['catalog_sha256'],
        anchor_id=policy['anchor_id'],policy_content_sha256=digest(policy),thresholds=copy.deepcopy(thresholds),
        core_region=region,core_summary=core,global_summary=global_summary,
        scope=dict(acquisition='common_trusted_acquisition_plus_independent_native_mathematics',
            mathematics='independent_exact_SAT_and_NumPy_QR_SVD',metrics='whole_original_faces_not_clipped_integrals',
            unknown='full_core_and_global_reliability_checked; no_unknown_as_false',
            source='two_fixed_static_saved_frames_not_live_GUI_or_animation_timeline',
            damage='not_inferred',volume='not_checked',visibility='not_checked',
            external_acquisition_receipt_required=True),
        execution_authority=False,geometry_setters=0,original_file_saved=False)
    raw_packet_sha256=digest(packet);topology_sha256=digest(topology);report_bytes=encode(report)
    out=dict(schema='v21-independent-native-frame-complete-v1',report=report,facts=facts,members=members,
        source_ref=copy.deepcopy(source),anchor_id=policy['anchor_id'],raw_packet_sha256=raw_packet_sha256,
        raw_packet_digest_model='canonical_utf8_json_not_file_bytes',topology_sha256=topology_sha256,
        thresholds=copy.deepcopy(thresholds),measurements=dict(validation_ns=validation_ns,geometry_ns=geometry_ns,
            exact_SAT_ns=sat_ns,QR_SVD_metrics_ns=metric_ns,aggregation_and_serialization_ns=clock_ns()-phase,
            report_bytes=len(report_bytes),report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            original_faces_computed=len(facts),production_B2_calls=0,common_capture_elapsed_ns=None,
            caller_persistence_elapsed_ns=None,peak_RSS_bytes=None,
            timing_scope='inclusive helper spans; excludes external qualification, acquisition, caller writes and model; do not add nested spans'))
    _check(deadline_ns,clock_ns);out['measurements']['complete_prepare_ns']=clock_ns()-started
    return out


def prepare_native_pair(frames,*,thresholds=None,max_candidates=4,deadline_ns,clock_ns=time.perf_counter_ns):
    """Natural finite same-face task aggregation, independent of the B selector.

    Give each frame's confirmed mixed core witness priority. The margin uses
    the weaker of the two required threshold exceedances, never mixed extrema
    from different faces. Remaining slots can show individual core extrema.
    """
    started=clock_ns();_check(deadline_ns,clock_ns);thresholds=_thresholds(thresholds)
    need(type(frames) is dict and len(frames)==2 and all(type(k) is str and 0<len(k)<=128 for k in frames),'pair_labels')
    need(type(max_candidates) is int and 1<=max_candidates<=4,'candidate_budget')
    labels=sorted(frames)
    need(all(type(frame) is dict and frame.get('schema')=='v21-independent-native-frame-complete-v1'
        and frame.get('thresholds')==thresholds for frame in frames.values()),'pair_frames')
    need(len({digest(frame['source_ref']) for frame in frames.values()})==2,'distinct_sources')
    need(len({frame['topology_sha256'] for frame in frames.values()})==1,'original_topology')
    count=len(frames[labels[0]]['facts'])
    need(all(set(frame['facts'])==set(range(count)) and all(type(i) is int for i in frame['facts']) for frame in frames.values()),'complete_original_faces')
    # Cross-check every original triangle, not only the shortlisted witnesses.
    need(all(frames[labels[0]]['facts'][i]['vertices']==frames[labels[1]]['facts'][i]['vertices'] for i in range(count)),
        'original_topology')
    chosen=[];reasons={}
    def add(index,reason):
        if index not in reasons:reasons[index]=[]
        reasons[index].append(reason)
        if index not in chosen:chosen.append(index)
    for label in labels:
        _check(deadline_ns,clock_ns);frame=frames[label]
        mixed=[frame['facts'][index] for index in frame['members'] if _mixed(frame['facts'][index],thresholds)]
        if mixed:
            mixed.sort(key=lambda row:(-min(row['principal_stretches'][0]-thresholds['high'],
                thresholds['low']-row['principal_stretches'][1]),row['triangle']))
            add(mixed[0]['triangle'],'confirmed_same_face_mixed_in_core:'+label)
    need(len(chosen)<=max_candidates,'mandatory_witness_budget')
    for label in labels:
        measured=[frames[label]['facts'][index] for index in frames[label]['members']
            if frames[label]['facts'][index]['state']!='unknown']
        if not measured:continue
        for field,sorter in [('core_maximum_stretch',lambda row:(-row['principal_stretches'][0],row['triangle'])),
            ('core_minimum_stretch',lambda row:(row['principal_stretches'][1],row['triangle']))]:
            index=min(measured,key=sorter)['triangle']
            if index in chosen or len(chosen)<max_candidates:add(index,field+':'+label)
    trajectories=[]
    for index in chosen:
        _check(deadline_ns,clock_ns);rows=[]
        for label in labels:
            frame=frames[label]
            rows.append(dict(label=label,source_ref=copy.deepcopy(frame['source_ref']),
                source_observation_sha256=frame['report']['source_observation_sha256'],anchor_id=frame['anchor_id'],
                has_confirmed_mixed_witness=frame['report']['core_summary']['has_confirmed_mixed_witness'],
                **copy.deepcopy(frame['facts'][index])))
        trajectories.append(dict(selected_triangle=index,selection_reasons=reasons[index],frames=rows))
    report=dict(schema='v21-independent-native-task-view-v1',thresholds=thresholds,
        source_bindings={label:dict(source_ref=copy.deepcopy(frames[label]['source_ref']),anchor_id=frames[label]['anchor_id'],
            catalog_sha256=frames[label]['report']['catalog_sha256'],raw_packet_sha256=frames[label]['raw_packet_sha256'],
            source_observation_sha256=frames[label]['report']['source_observation_sha256'],
            topology_sha256=frames[label]['topology_sha256']) for label in labels},
        core_summary_by_frame=[dict(label=label,**copy.deepcopy(frames[label]['report']['core_summary'])) for label in labels],
        global_summary_by_frame=[dict(label=label,**copy.deepcopy(frames[label]['report']['global_summary'])) for label in labels],
        core_regions_by_frame={label:copy.deepcopy(frames[label]['report']['core_region']) for label in labels},
        candidate_witness_trajectories=trajectories,same_original_topology_verified=True,
        scope=dict(acquisition='common_trusted_acquisition_plus_independent_native_mathematics',
            selection='same-face_dual-source_rows; independent task-native mixed-first aggregation',
            reliability='complete_original_face_qr_svd_facts; exact_sat_core_membership',
            lookup='complete_bound_static_rows_available; not_new_Blender_targeted_inspect',
            semantics='whole_triangle_current_core_hull_intersection; not_damage_volume_visibility_or_timeline'),
        execution_authority=False,geometry_setters=0,original_file_saved=False)
    payload=encode(report)
    out=dict(schema='v21-independent-native-pair-complete-v1',report=report,frames=frames,
        candidate_triangle_indices=chosen,measurements=dict(report_bytes=len(payload),
            report_sha256=hashlib.sha256(payload).hexdigest(),production_B2_calls=0,
            timing_scope='pair aggregation and public serialization only; frame work and common acquisition separate'))
    _check(deadline_ns,clock_ns);out['measurements']['complete_pair_ns']=clock_ns()-started
    return out
