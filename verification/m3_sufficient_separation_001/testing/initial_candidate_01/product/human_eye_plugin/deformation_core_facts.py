"""Complete core facts without optional peripheral-context compaction.

``project`` consumes internal, complete same-source membership and bound B2
rows; it grants no source or policy admission. The formal actor must validate
the entire source before ``plan`` validates its policy and selects one core.
Neither interface infers damage, anatomy, volume, visibility or write authority.
"""
import copy,hashlib
from . import deformation_context as context,deformation_anchors as anchors,deformation_region as region,surface_deformation as surface
r=anchors.r
METRICS=('max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio')
CORE_REF_FIELDS={'catalog_sha256','policy_sha256','anchor_id','half_extents_m','region'}
VALIDATION_FIELDS={'schema','method','max_replay_error','replay_atol','animation_curves_checked','not_coordinate_measurement_error'}


def need(value,reason):r.require(value,'deformation_core_facts_'+reason)


def _validation(value):
    # This validates metadata, not the packet or external expectations. Source
    # admission remains the existing independent complete source consumer.
    need(type(value) is dict and set(value)==VALIDATION_FIELDS
        and value['schema']=='small-skin-source-snapshot-v1'
        and value['method']=='external_binding_full_dependency_FK_and_LBS'
        and region.finite(value['max_replay_error'],1e308) and 0<=value['max_replay_error']
        and region.finite(value['replay_atol'],1e308) and 0<value['replay_atol']
        and value['max_replay_error']<=value['replay_atol']
        and type(value['animation_curves_checked']) is int and value['animation_curves_checked']>=0
        and value['not_coordinate_measurement_error'] is True,'source_validation')


def _membership(proof,membership,core_ref):
    need(type(core_ref) is dict and set(core_ref)==CORE_REF_FIELDS
        and r.hex_text(core_ref['catalog_sha256'],64) and r.hex_text(core_ref['policy_sha256'],64),'core_ref')
    context._anchor_id(core_ref['anchor_id']);context._half(core_ref['half_extents_m']);region.region_value(core_ref['region'])
    need(type(proof.get('triangles')) is list and 1<=len(proof['triangles'])<=region.MAX_TRIANGLES
        and type(proof.get('current')) is list and 1<=len(proof['current'])<=region.MAX_VERTICES,'proof_shape')
    need(type(membership) is dict and set(membership)==region.MEMBERSHIP_FIELDS
        and membership['schema']=='surface-deformation-region-membership-v1'
        and membership['source_sha256']==proof.get('source_sha256')
        and membership['membership_complete'] is True
        and membership['coordinate_model']==region.COORDINATE_MODEL
        and membership['selection_rule']==region.SELECTION_RULE
        and membership['region']==core_ref['region'],'membership')
    scanned=membership['triangles_scanned'];vertices=membership['vertices_transformed'];members=membership['matched_triangle_indices']
    need(type(scanned) is int and scanned==len(proof['triangles']) and type(vertices) is int and vertices==len(proof['current'])
        and type(members) is list and all(type(i) is int and 0<=i<scanned for i in members)
        and members==sorted(set(members)),'membership')
    return members


def project(proof,membership,*,rows,core_ref,pins,source_validation,deadline_ns):
    """Project existing complete core membership; no B2/catalog/geometry work.

    ``membership`` and ``core_ref`` are internal products of a qualified plan,
    not public evidence authorizing an arbitrary caller-selected core. This
    narrow helper also permits offline reuse of the frozen B3e core audit.
    """
    r.check_time(deadline_ns);started=r.time.perf_counter_ns()
    source_ref=anchors.source_ref(proof);_validation(source_validation)
    need(type(pins) is dict and set(pins)==set(anchors.PIN_FIELDS)
        and all(r.hex_text(pins[key],64) for key in anchors.PIN_FIELDS)
        and pins['scene_sha256']==source_ref['scene_sha256'],'pins_binding')
    members=_membership(proof,membership,core_ref)
    values=surface._verified_rows(proof,rows,deadline_ns=deadline_ns)
    counts=dict(measured=0,collapsed=0,unknown=0);reasons={};extrema=dict.fromkeys(METRICS);witnesses=dict.fromkeys(METRICS);selected=[]
    for index in members:
        r.check_time(deadline_ns);row=values[index];selected.append(row);state=row['state'];counts[state]+=1
        if state=='unknown':
            need(r.text(row.get('reason')) and row.get('principal_stretches') is None and row.get('area_ratio') is None,'rows')
            reasons[row['reason']]=reasons.get(row['reason'],0)+1;continue
        stretches=row.get('principal_stretches');area=row.get('area_ratio')
        need(type(stretches) is list and len(stretches)==2 and all(region.finite(x,1e308) for x in stretches)
            and stretches[0]>=stretches[1]>=0 and region.finite(area,1e308) and area>=0,'rows')
        for name,value,maximum in zip(METRICS,(stretches[0],stretches[1],area,area),(True,False,False,True)):
            previous=extrema[name]
            if previous is None or (value>previous if maximum else value<previous) or value==previous and index<witnesses[name]:
                extrema[name]=value;witnesses[name]=index
    # Witnesses are selected while traversing all complete core members. Keep
    # this explicit check before publication; omitted per-face details cannot
    # turn a peripheral extremum into evidence about the required core.
    core_ids=set(members)
    need(all(witnesses[name] is None and extrema[name] is None or type(witnesses[name]) is int
        and witnesses[name] in core_ids and values[witnesses[name]]['state']!='unknown' for name in METRICS),'witness_binding')
    facts=dict(core_status='empty' if not members else 'partial' if counts['unknown'] else 'observed',core_triangle_count=len(members),
        core_states=counts,core_unknown_reasons=dict(sorted(reasons.items())),core_extrema=extrema)
    report=dict(schema='surface-deformation-core-facts-v1',source_sha256=proof['source_sha256'],source_ref=copy.deepcopy(source_ref),
        live_capture=dict(document_epoch=proof['source']['document_epoch'],process_id=proof['source']['process_id']),
        operator_pins=copy.deepcopy(pins),source_validation=copy.deepcopy(source_validation),core_ref=copy.deepcopy(core_ref),facts=facts,
        core_witnesses=witnesses,completeness=dict(membership_complete=True,core_facts_complete=True,unknown_reasons_omitted=0,
            metric_witnesses_complete=True,member_ids_omitted=len(members),per_face_rows_omitted=len(members),
            all_members_unknown=bool(members) and counts['unknown']==len(members),all_members_measurable=bool(members) and not counts['unknown']),
        scope=dict(metric_scope='whole_original_triangles_not_clipped_integrals',extrema_scope='measured_and_collapsed_core_members_only',
            coordinate_model=region.COORDINATE_MODEL,selection_rule=region.SELECTION_RULE,
            coordinate_precision='binary32 coordinate quantization plus conservative binary64 arithmetic margins; not a certified physical bound',
            peripheral_context='not_reported',peripheral_shrinking=False,contact_extent='not_checked',damage='not_inferred',
            anatomy='not_inferred',volume='not_checked',visibility='not_checked',timeline='not_checked'),
        execution_authority=False,geometry_setters=0,original_file_saved=False)
    # Final source-validation metadata is already present in the bytes gate.
    blob=context.publication_bytes(report);need(len(blob)<=r.MAX_BYTES,'report_byte_budget');r.check_time(deadline_ns)
    audit=dict(schema='surface-deformation-core-facts-audit-v1',source_sha256=proof['source_sha256'],core_ref=copy.deepcopy(core_ref),
        core_membership=copy.deepcopy(membership),core_triangle_indices=members[:],core_rows=selected,core_rows_sha256=r.digest(selected),
        published_publication_bytes=len(blob),published_publication_sha256=hashlib.sha256(blob).hexdigest(),
        original_deadline_ns=deadline_ns,pure_projection_B2_rows_passes=0,pure_projection_geometry_cache_preparations=0,
        pure_projection_region_scans=0,candidates_evaluated=0,peripheral_shrinking=False)
    audit['projection_elapsed_ns']=r.time.perf_counter_ns()-started
    r.check_time(deadline_ns);return report,audit


def plan(proof,query,*,policy,policy_sha256,pins,rows,source_validation,deadline_ns):
    """Qualified actor wrapper: strict policy, exactly one required-core scan."""
    r.check_time(deadline_ns);started=r.time.perf_counter_ns()
    policy=context.validate_policy(policy);context._query(proof,query,policy,policy_sha256)
    _,item=context._directory(proof,policy,pins,deadline_ns)
    core_region=anchors.box(item,policy['required_core_half_extents_m'])
    core_ref=dict(catalog_sha256=policy['catalog_sha256'],policy_sha256=policy_sha256,anchor_id=policy['anchor_id'],
        half_extents_m=policy['required_core_half_extents_m'][:],region=copy.deepcopy(core_region))
    cache=region.prepare_geometry(proof,deadline_ns=deadline_ns)
    membership=region.select_prepared(cache,dict(schema='surface-deformation-region-query-v1',
        expected_source_sha256=proof['source_sha256'],region=core_region),deadline_ns=deadline_ns)
    report,audit=project(proof,membership,rows=rows,core_ref=core_ref,pins=pins,source_validation=source_validation,deadline_ns=deadline_ns)
    audit.update(geometry_cache_preparations=1,region_scans=1,B2_rows_passes=0,wrapper_elapsed_ns=r.time.perf_counter_ns()-started)
    r.check_time(deadline_ns);return report,audit
