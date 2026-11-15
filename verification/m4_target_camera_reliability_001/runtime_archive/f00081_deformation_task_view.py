"""Task-bound deterministic witnesses and global scope over qualified facts.

The v1 projection stays unchanged. This layer selects public fact witnesses,
not a core or a source, and is not a physical uncertainty certification.
"""
import copy,hashlib
from . import deformation_closure as closure,deformation_context as context
from . import deformation_anchors as anchors,surface_deformation as surface
r=anchors.r
SPEC_SCHEMA='surface-deformation-task-request-v1'
SOURCE_FIELDS={'source_ref','catalog_sha256','anchor_id','core_half_extents_m','profile_sha256'}


def need(value,reason):r.require(value,'deformation_task_view_'+reason)


def validate_task_spec(spec):
    need(type(spec) is dict and set(spec)=={'schema','question','thresholds','sources'}
        and spec['schema']==SPEC_SCHEMA and type(spec['question']) is str
        and 1<=len(spec['question'])<=8192 and bool(spec['question'].strip()) and '\x00' not in spec['question'],'spec')
    thresholds=spec['thresholds']
    need(type(thresholds) is dict and set(thresholds)=={'high','low'}
        and anchors.finite(thresholds['high']) and anchors.finite(thresholds['low'])
        and 0<=thresholds['low']<1<thresholds['high'],'thresholds')
    sources=spec['sources']
    need(type(sources) is dict and len(sources)==2 and all(r.text(label) for label in sources),'sources')
    for source in sources.values():
        need(type(source) is dict and set(source)==SOURCE_FIELDS,'source_fields')
        context._source_ref(source['source_ref']);context._anchor_id(source['anchor_id'])
        context._half(source['core_half_extents_m'])
        need(r.hex_text(source['catalog_sha256'],64) and r.hex_text(source['profile_sha256'],64),'source_fields')
    need(len(context.publication_bytes(spec))<=65536,'spec_bytes')
    return copy.deepcopy(spec)


def task_digest(spec):
    return hashlib.sha256(context.publication_bytes(validate_task_spec(spec))).hexdigest()


def _select(task,frames,explicit,max_candidates,deadline_ns):
    need(type(max_candidates) is int and 0<=max_candidates<=4,'candidate_budget')
    spec=task['spec'];labels=sorted(spec['sources']);by_label={}
    need(type(frames) is list and len(frames)==2,'frames')
    for frame in frames:
        need(type(frame) is dict and set(frame)==closure.FRAME_FIELDS,'frames')
        label=frame['label'];need(type(label) is str and label in labels and label not in by_label,'labels')
        by_label[label]=frame
    if explicit is None:explicit={label:[] for label in labels}
    need(type(explicit) is dict and set(explicit)==set(labels),'explicit_labels')
    selected=set();origins={label:set() for label in labels};mixed={};unknown={};extrema={};rows_scanned=0
    for label in labels:
        r.check_time(deadline_ns);frame=by_label[label];source=spec['sources'][label];policy=frame['policy']
        need(source['source_ref']==anchors.source_ref(frame['proof'])
            and source['catalog_sha256']==policy['catalog_sha256'] and source['anchor_id']==policy['anchor_id']
            and source['core_half_extents_m']==policy['required_core_half_extents_m']
            and source['profile_sha256']==frame['pins']['profile_sha256'],'source_binding')
        values=surface._verified_rows(frame['proof'],frame['rows'],deadline_ns=deadline_ns)
        for row in values:r.check_time(deadline_ns);closure._row(row)
        rows_scanned+=len(values)
        membership=frame['membership']
        need(type(membership) is dict and membership.get('membership_complete') is True,'membership')
        members=membership.get('matched_triangle_indices')
        need(type(members) is list and all(type(i) is int and 0<=i<len(values) for i in members)
            and members==sorted(set(members)),'membership')
        ids=explicit[label]
        need(type(ids) is list and len(ids)<=4 and all(type(i) is int and 0<=i<len(values) for i in ids)
            and len(ids)==len(set(ids)),'explicit_indices')
        selected.update(ids);origins[label].update(ids)
        thresholds=spec['thresholds']
        mixed[label]=[i for i in members if values[i]['state']=='measured'
            and values[i]['principal_stretches'][0]>=thresholds['high']
            and values[i]['principal_stretches'][1]<=thresholds['low']]
        unknown[label]=[i for i in members if values[i]['state']=='unknown']
        measured=[i for i in members if values[i]['state']!='unknown']
        keys=(lambda i:values[i]['principal_stretches'][0],lambda i:-values[i]['principal_stretches'][1],
              lambda i:-values[i]['area_ratio'],lambda i:values[i]['area_ratio'])
        extrema[label]=[max(measured,key=lambda i:(key(i),-i)) for key in keys] if measured else []
    # At most two positive scopes. Reuse explicit witnesses, then a shared
    # witness where possible; never sacrifice an existing explicit selection.
    missing=[label for label in labels if mixed[label] and not selected.intersection(mixed[label])]
    if len(missing)==2 and set(mixed[missing[0]]).intersection(mixed[missing[1]]):
        index=min(set(mixed[missing[0]]).intersection(mixed[missing[1]]));selected.add(index)
        for label in missing:origins[label].add(index)
    else:
        for label in missing:index=mixed[label][0];selected.add(index);origins[label].add(index)
    need(len(selected)<=max_candidates,'candidate_budget')
    mandatory={label:next((i for i in sorted(selected) if i in mixed[label]),None) for label in labels}
    optional=[]
    for label in labels:
        for index in unknown[label][:1]+extrema[label]:
            if index in selected:continue
            if len(selected)>=max_candidates:break
            selected.add(index);origins[label].add(index);optional.append(dict(label=label,triangle=index))
    selection=dict(rule='explicit_then_cover_each_confirmed_core_with_same_face_mixed_witness_then_optional_unknown_extrema',
        explicit_by_label=copy.deepcopy(explicit),mandatory_mixed_by_label=mandatory,
        confirmed_core_witness_counts={label:len(mixed[label]) for label in labels},
        optional=optional,candidates_by_label={label:sorted(origins[label]) for label in labels},
        selected_triangle_indices=sorted(selected),candidate_limit=max_candidates,
        selection_verified_rows_passes=2,selection_rows_scanned=rows_scanned,
        selection_authority='public_qualified_engine_facts_not_private_truth',
        fact_scope='complete_source_rows_selection_after_full_source_read_not_targeted_worker_receipt')
    r.check_time(deadline_ns);return selection,by_label


def produce(task,frames,*,explicit_candidates_by_label=None,max_candidates=4,deadline_ns):
    r.check_time(deadline_ns);started=r.time.perf_counter_ns()
    need(type(task) is dict and set(task)=={'spec','task_sha256','condition_id','run_nonce'},'task')
    spec=validate_task_spec(task['spec'])
    need(task['task_sha256']==task_digest(spec),'task_binding')
    need(r.text(task['condition_id']) and r.hex_text(task['run_nonce'],32),'run_binding')
    selection,by_label=_select(task,frames,explicit_candidates_by_label,max_candidates,deadline_ns)
    bound=dict(task_sha256=task['task_sha256'],condition_id=task['condition_id'],sources={})
    for label,source in spec['sources'].items():
        bound['sources'][label]={key:copy.deepcopy(source[key]) for key in ('source_ref','catalog_sha256','anchor_id')}
        bound['sources'][label]['policy_sha256']=by_label[label]['policy_sha256']
    base,audit=closure.project(bound,frames,candidates_by_label=selection['candidates_by_label'],
        threshold_high=spec['thresholds']['high'],threshold_low=spec['thresholds']['low'],deadline_ns=deadline_ns)
    globals=[]
    for label in sorted(by_label):
        r.check_time(deadline_ns);source=audit['evidence_sidecar']['frames'][label];rows=source['rows']
        counts,reasons=context._stats(rows);unknown=[row['triangle'] for row in rows if row['state']=='unknown']
        globals.append(dict(label=label,source_ref=copy.deepcopy(spec['sources'][label]['source_ref']),
            triangles_total=len(rows),states=counts,unknown_triangle_indices=unknown,unknown_reasons=reasons,
            status='partial' if unknown else 'observed',
            source_validation_scope=dict(validation=copy.deepcopy(source['source_validation']),
                applies_to='complete_dependency_source_replay_consistency',
                physical_measurement_error_certified=False,geometric_unknowns_remain=bool(unknown),
                does_not_resolve_geometric_unknowns=True)))
    evidence=copy.deepcopy(audit['evidence_sidecar'])
    evidence.update(schema='surface-deformation-task-witness-evidence-v2',request_task=copy.deepcopy(task),
        task_selection=copy.deepcopy(selection),global_summary_by_frame=copy.deepcopy(globals))
    blob=context.publication_bytes(evidence);need(len(blob)<=2*r.MAX_BYTES,'evidence_bytes')
    view=copy.deepcopy(base)
    view.update(schema='surface-deformation-task-witness-view-v2',task_binding=dict(task_sha256=task['task_sha256'],
        condition_id=task['condition_id'],run_nonce=task['run_nonce'],question=spec['question'],thresholds=copy.deepcopy(spec['thresholds'])),
        global_summary_by_frame=globals,task_witness_selection=copy.deepcopy(selection),
        evidence_ref=dict(schema=evidence['schema'],sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob),
            storage='task_bound_persistent_artifact_must_be_verified_before_publication'))
    view['scope'].update(task_binding='canonical_question_threshold_source_spec_digest',
        candidate_selection=selection['rule'],global_scope='all_complete_source_rows_not_only_core',
        source_validation='replay_consistency_not_physical_measurement_error_certification')
    payload=context.publication_bytes(view);need(len(payload)<=r.MAX_BYTES,'view_bytes')
    result=dict(schema='surface-deformation-task-witness-audit-v2',base_projection_audit=audit,
        base_projection_view=base,evidence_sidecar=evidence,evidence_sidecar_sha256=hashlib.sha256(blob).hexdigest(),
        evidence_sidecar_bytes=len(blob),published_publication_bytes=len(payload),
        published_publication_sha256=hashlib.sha256(payload).hexdigest(),selection=selection,
        global_summary_rows_scanned=sum(len(audit['evidence_sidecar']['frames'][label]['rows']) for label in by_label),
        verified_rows_passes_total=6,original_deadline_ns=deadline_ns,
        delivered=False,model_received=False,physical_reader_calls=0,
        physical_reader_calls_scope='view_producer_only_reader_counts_must_be_added_by_adapter')
    result['producer_elapsed_ns']=r.time.perf_counter_ns()-started
    r.check_time(deadline_ns);return view,result
