"""Explicit post-anchor, two-source fact projection; never source admission.

Callers must first qualify each complete source through the existing external
binding consumer and retain its bound B2 rows and complete core membership.
This function rechecks those internal bindings, not provenance of arbitrary JSON.
It performs no reads, geometry computation, face selection, learning or writes.
"""
import copy,hashlib
from . import deformation_anchors as anchors,deformation_context as context
from . import deformation_core_facts as core,surface_deformation as surface

r=anchors.r
FRAME_FIELDS={'label','proof','rows','membership','policy','policy_sha256','query','pins','source_validation'}
SOURCE_FIELDS={'source_ref','catalog_sha256','anchor_id','policy_sha256'}
MAX_CANDIDATES=4


def need(value,reason):r.require(value,'deformation_closure_'+reason)


def _row(row):
    need({'state','reason','principal_stretches','area_ratio'}<=set(row),'rows')
    state=row['state'];stretches=row.get('principal_stretches');area=row.get('area_ratio')
    if state=='unknown':
        need(r.text(row.get('reason')) and stretches is None and area is None,'rows')
    else:
        need(type(stretches) is list and len(stretches)==2
            and all(anchors.finite(x) for x in stretches) and stretches[0]>=stretches[1]>=0
            and anchors.finite(area) and area>=0,'rows')
        need((state=='measured' and row.get('reason') is None)
            or (state=='collapsed' and row.get('reason')=='current_zero_area' and stretches[1]==0 and area==0),'rows')


def _pointer(label):return label.replace('~','~0').replace('/','~1')


def project(task,frames,*,candidates_by_label,threshold_high=1.1,threshold_low=.9,deadline_ns):
    """Return a separately hashed model view and its full evidence sidecar.

    task.sources binds each already chosen public catalog/anchor/policy to its
    own file/mesh/rig/frame. Explicit per-source candidates are unioned, never
    truncated or learned. All retained original triangles have real rows in both
    sources. Task/question hashing and source qualification remain caller duties.
    """
    r.check_time(deadline_ns);started=r.time.perf_counter_ns()
    need(type(task) is dict and set(task)=={'task_sha256','condition_id','sources'}
        and r.hex_text(task['task_sha256'],64) and r.text(task['condition_id']),'task')
    expected=task['sources']
    need(type(expected) is dict and len(expected)==2 and all(r.text(label) for label in expected),'source_labels')
    labels=sorted(expected)
    need(type(frames) is list and len(frames)==2,'frames')
    indexed={}
    for frame in frames:
        need(type(frame) is dict and set(frame)==FRAME_FIELDS,'frame_fields')
        label=frame['label'];need(type(label) is str and label in expected and label not in indexed,'source_labels')
        need(type(frame['proof']) is dict and type(frame['proof'].get('triangles')) is list
            and type(frame['membership']) is dict,'frame_fields')
        indexed[label]=frame
    need(set(indexed)==set(expected),'source_labels')
    need(type(candidates_by_label) is dict and set(candidates_by_label)==set(expected),'candidate_labels')
    need(anchors.finite(threshold_high) and anchors.finite(threshold_low)
        and 0<=threshold_low<1<threshold_high,'thresholds')
    candidates=set();selected={}
    for label in labels:
        value=candidates_by_label[label];total=len(indexed[label]['proof'].get('triangles',[]))
        need(type(value) is list and len(value)<=MAX_CANDIDATES
            and all(type(i) is int and 0<=i<total for i in value) and len(set(value))==len(value),'candidate_indices')
        selected[label]=value[:];candidates.update(value)
    need(len(candidates)<=MAX_CANDIDATES,'candidate_union_limit')
    candidates=sorted(candidates)
    sidecar=dict(schema='surface-deformation-cross-frame-evidence-v1',task=copy.deepcopy(task),
        candidates_by_label=copy.deepcopy(selected),candidate_triangle_indices=candidates[:],
        thresholds=dict(high=threshold_high,low=threshold_low),frames={},
        admission='qualified_internal_inputs_only_not_public_admission')
    summaries=[];source_bindings={};verified={};core_audits={};topology=None;roles=None;validation_ns=0;core_scanned=0;scanned=0
    for label in labels:
        r.check_time(deadline_ns);t=r.time.perf_counter_ns();frame=indexed[label];proof=frame['proof'];binding=expected[label]
        need(type(binding) is dict and set(binding)==SOURCE_FIELDS,'source_binding_fields')
        context._source_ref(binding['source_ref'])
        ref=anchors.source_ref(proof);need(binding['source_ref']==ref,'source_binding')
        policy=context.validate_policy(frame['policy'])
        need(binding['catalog_sha256']==policy['catalog_sha256'] and binding['anchor_id']==policy['anchor_id']
            and binding['policy_sha256']==frame['policy_sha256'],'selection_binding')
        context._query(proof,frame['query'],policy,frame['policy_sha256'])
        directory,item=context._directory(proof,policy,frame['pins'],deadline_ns)
        region=anchors.box(item,policy['required_core_half_extents_m'])
        need(frame['membership'].get('region')==region,'membership_region')
        core_ref=dict(catalog_sha256=directory['catalog_sha256'],policy_sha256=frame['policy_sha256'],
            anchor_id=policy['anchor_id'],half_extents_m=policy['required_core_half_extents_m'][:],region=region)
        facts,core_audit=core.project(proof,frame['membership'],rows=frame['rows'],core_ref=core_ref,
            pins=frame['pins'],source_validation=frame['source_validation'],deadline_ns=deadline_ns)
        values=surface._verified_rows(proof,frame['rows'],deadline_ns=deadline_ns)
        for row in values:r.check_time(deadline_ns);_row(row)
        scanned+=len(values)
        signature=r.digest(dict(original=proof['original'],triangles=proof['triangles']))
        role=(ref['mesh_object_id'],ref['rig_object_id'],proof['unit'],policy['anchor_id'])
        if topology is None:topology=signature;roles=role
        need(signature==topology,'original_topology');need(role==roles,'cross_source_roles')
        need(all(i<len(values) for i in candidates),'candidate_indices')
        members=core_audit['core_triangle_indices'];mixed=[]
        for index in members:
            r.check_time(deadline_ns);row=values[index];core_scanned+=1
            if row['state']=='measured' and row['principal_stretches'][0]>=threshold_high and row['principal_stretches'][1]<=threshold_low:
                mixed.append(index)
        confirmation=True if mixed else None if facts['facts']['core_states']['unknown'] else False
        source_bindings[label]=dict(source_ref=copy.deepcopy(ref),source_sha256=proof['source_sha256'],
            catalog_sha256=directory['catalog_sha256'],anchor_id=policy['anchor_id'],policy_sha256=frame['policy_sha256'],
            operator_pins_sha256=r.digest(frame['pins']))
        summaries.append(dict(label=label,source_ref=copy.deepcopy(ref),core_ref=copy.deepcopy(core_ref),
            facts=copy.deepcopy(facts['facts']),core_witnesses=copy.deepcopy(facts['core_witnesses']),
            has_confirmed_mixed_witness=confirmation,confirmation_scope='entire_complete_core_same_measured_triangle',
            confirmed_witness_count=len(mixed),confirmed_witness_triangle=None if not mixed else mixed[0]))
        sidecar['frames'][label]=dict(proof=copy.deepcopy(proof),rows=copy.deepcopy(values),
            membership=copy.deepcopy(frame['membership']),policy=copy.deepcopy(policy),query=copy.deepcopy(frame['query']),
            operator_pins=copy.deepcopy(frame['pins']),source_validation=copy.deepcopy(frame['source_validation']),
            core_report=facts,core_triangle_indices=members[:],core_rows_sha256=core_audit['core_rows_sha256'],
            confirmed_mixed_triangle_indices=mixed)
        core_audits[label]=core_audit
        verified[label]=(values,set(members),confirmation)
        validation_ns+=r.time.perf_counter_ns()-t
    trajectories=[]
    for index in candidates:
        rows=[];refs={}
        for label in labels:
            r.check_time(deadline_ns);values,members,confirmation=verified[label];row=values[index]
            rows.append(dict(label=label,file_sha256=expected[label]['source_ref']['scene_sha256'],
                principal_stretches=copy.deepcopy(row['principal_stretches']),area_ratio=row['area_ratio'],
                state=row['state'],reason=row['reason'],in_core=index in members,has_confirmed_mixed_witness=confirmation))
            refs[label]='/frames/'+_pointer(label)+'/rows/'+str(index)
        trajectories.append(dict(selected_triangle=index,frames=rows,evidence_rows_by_label=refs))
    evidence_blob=context.publication_bytes(sidecar);need(len(evidence_blob)<=r.MAX_BYTES,'evidence_byte_budget')
    evidence_sha=hashlib.sha256(evidence_blob).hexdigest();r.check_time(deadline_ns)
    view=dict(schema='surface-deformation-cross-frame-view-v1',task_sha256=task['task_sha256'],condition_id=task['condition_id'],
        source_bindings=source_bindings,original_topology_sha256=topology,
        thresholds=dict(high=threshold_high,low=threshold_low),core_summary_by_frame=summaries,
        candidate_witness_trajectories=trajectories,
        completeness=dict(sources_complete=True,same_original_topology_verified=True,candidate_union_complete=True,
            cross_frame_rows_complete=True,core_facts_complete=True,candidate_count=len(candidates),
            source_count=2,unknown_preserved=True),
        evidence_ref=dict(schema=sidecar['schema'],sha256=evidence_sha,bytes=len(evidence_blob),
            storage='caller_must_retain_full_sidecar_before_delivery'),
        scope=dict(source_admission='existing_qualified_source_required',task_binding='caller_supplied_digest_not_question_validation',
            candidate_selection='explicit_post_anchor_union_not_automatic_ranking',
            metric_scope='whole_original_triangles_not_clipped_integrals',confirmation='entire_core_not_candidate_subset',
            timeline='two_static_sources_only',damage='not_inferred',learning=False),
        execution_authority=False,geometry_setters=0,original_file_saved=False)
    blob=context.publication_bytes(view);need(len(blob)<=r.MAX_BYTES,'report_byte_budget');r.check_time(deadline_ns)
    audit=dict(schema='surface-deformation-cross-frame-audit-v1',evidence_sidecar=sidecar,evidence_sidecar_sha256=evidence_sha,
        core_verification_audits_by_label=core_audits,
        evidence_sidecar_bytes=len(evidence_blob),published_publication_bytes=len(blob),
        published_publication_sha256=hashlib.sha256(blob).hexdigest(),original_deadline_ns=deadline_ns,
        scanned_rows=scanned,bound_row_validation_rows=2*scanned,confirmation_core_rows_scanned=core_scanned,
        source_binding_validation_ns=validation_ns,
        B2_rows_passes=0,verified_rows_passes=4,catalog_verification_passes=2,region_membership_scans=0,
        physical_reader_calls=0,physical_reader_calls_scope='projection_only_no_source_acquisition',
        delivered=False,delivery_scope='caller_must_persist_full_evidence_and_publish_with_original_deadline')
    audit['projection_elapsed_ns']=r.time.perf_counter_ns()-started
    r.check_time(deadline_ns);return view,audit
