"""Operator-bounded context compaction without losing required core facts.

This measures retention of whole-triangle records and publication bytes. It is
not a coverage-area, anatomical, damage, optimal-focus or model-benefit score.
"""
import copy,hashlib,json
from . import deformation_anchors as anchors,deformation_region as region,surface_deformation as surface
r=anchors.r
POLICY_FIELDS={'schema','source_ref','catalog_sha256','anchor_id','required_core_half_extents_m','primary_half_extents_m',
    'candidate_half_extents_m','max_surplus_members','min_saved_bytes','planning_budget_ms'}
SELECTION_FIELDS={'schema','source_ref','catalog_sha256','anchor_id','policy_sha256'}
QUERY_FIELDS={'schema','expected_source_sha256','catalog_sha256','anchor_id','policy_sha256'}


def need(value,reason):r.require(value,'deformation_context_'+reason)


def publication_bytes(report):
    """Exact bytes of the new mode, including its single terminal LF."""
    return json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'


def _source_ref(value):
    need(type(value) is dict and set(value)=={'scene_sha256','rig_object_id','mesh_object_id','frame'}
        and r.hex_text(value['scene_sha256'],64) and r.text(value['rig_object_id']) and r.text(value['mesh_object_id']),'source_fields')
    frame=value['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and anchors.finite(frame['subframe'],1) and 0<=frame['subframe']<1,'frame')


def _half(value):
    need(anchors.vector(value,1e6) and all(1e-6<=v<=1e6 for v in value),'half_extents');return value


def _anchor_id(value):
    need(type(value) is str and value.startswith('bone-anchor:') and r.hex_text(value[len('bone-anchor:'):],64),'anchor_id')


def validate_policy(policy):
    need(type(policy) is dict and set(policy)==POLICY_FIELDS and policy['schema']=='surface-deformation-context-policy-v1','policy_fields')
    _source_ref(policy['source_ref']);need(r.hex_text(policy['catalog_sha256'],64),'catalog_digest');_anchor_id(policy['anchor_id'])
    core=_half(policy['required_core_half_extents_m']);primary=_half(policy['primary_half_extents_m'])
    need(all(c<=p for c,p in zip(core,primary)),'candidate_core')
    candidates=policy['candidate_half_extents_m'];need(type(candidates) is list and len(candidates)<=2,'candidate_limit');seen={tuple(primary)}
    for half in candidates:
        _half(half);need(all(c<=h for c,h in zip(core,half)),'candidate_core')
        need(all(h<=p for h,p in zip(half,primary)),'candidate_primary')
        need(tuple(half) not in seen,'candidate_duplicate');seen.add(tuple(half))
    for key,low,high in (('max_surplus_members',0,256),('min_saved_bytes',256,65536),('planning_budget_ms',1,250)):
        need(type(policy[key]) is int and low<=policy[key]<=high,key)
    return copy.deepcopy(policy)


def _directory(proof,policy,pins,deadline_ns):
    need(policy['source_ref']==anchors.source_ref(proof),'stale_selection')
    directory=anchors.catalog(proof,pins=pins,deadline_ns=deadline_ns)
    need(policy['catalog_sha256']==directory['catalog_sha256'],'stale_catalog')
    item=next((v for v in directory['anchors'] if v['anchor_id']==policy['anchor_id']),None)
    need(item is not None,'unknown_anchor');need(item['state']=='available','anchor_unavailable');return directory,item


def bind_selection(proof,selection,*,policy,policy_sha256,pins,deadline_ns):
    r.check_time(deadline_ns);policy=validate_policy(policy);need(r.hex_text(policy_sha256,64),'policy_digest')
    need(type(selection) is dict and set(selection)==SELECTION_FIELDS and selection['schema']=='surface-deformation-context-selection-v1','selection_fields')
    _source_ref(selection['source_ref']);need(r.hex_text(selection['catalog_sha256'],64),'catalog_digest');_anchor_id(selection['anchor_id'])
    need(selection['policy_sha256']==policy_sha256,'policy_binding')
    need(selection['source_ref']==policy['source_ref'],'stale_selection')
    need(selection['catalog_sha256']==policy['catalog_sha256'],'stale_catalog')
    need(selection['anchor_id']==policy['anchor_id'],'policy_binding')
    _,item=_directory(proof,policy,pins,deadline_ns)
    # Resolve every allowed box before any optional fallback work. A bad domain
    # is malformed policy, never a reason to silently retain a valid primary.
    for half in [policy['required_core_half_extents_m'],policy['primary_half_extents_m'],*policy['candidate_half_extents_m']]:
        r.check_time(deadline_ns);anchors.box(item,half)
    result=dict(schema='surface-deformation-context-query-v1',expected_source_sha256=proof['source_sha256'],catalog_sha256=policy['catalog_sha256'],
        anchor_id=policy['anchor_id'],policy_sha256=policy_sha256)
    r.check_time(deadline_ns);return result


def _query(proof,query,policy,policy_sha256):
    need(type(query) is dict and set(query)==QUERY_FIELDS and query['schema']=='surface-deformation-context-query-v1'
        and r.hex_text(query['expected_source_sha256'],64) and r.hex_text(query['catalog_sha256'],64),'query_fields')
    need(r.hex_text(policy_sha256,64),'policy_digest')
    need(query['expected_source_sha256']==proof.get('source_sha256'),'stale_source')
    need(query['policy_sha256']==policy_sha256 and query['anchor_id']==policy['anchor_id'],'policy_binding')
    need(query['catalog_sha256']==policy['catalog_sha256'],'stale_catalog')


def _stats(rows):
    counts={state:sum(v['state']==state for v in rows) for state in ('measured','collapsed','unknown')}
    reasons={reason:sum(v['state']=='unknown' and v['reason']==reason for v in rows)
        for reason in sorted({v['reason'] for v in rows if v['state']=='unknown'})}
    return counts,reasons


def _payload(report,deadline_ns):
    blob=publication_bytes(report);need(len(blob)<=r.MAX_BYTES,'report_byte_budget');r.check_time(deadline_ns);return blob


def plan(proof,query,*,policy,policy_sha256,pins,rows,report_factory,deadline_ns):
    r.check_time(deadline_ns);policy=validate_policy(policy);_query(proof,query,policy,policy_sha256)
    _,item=_directory(proof,policy,pins,deadline_ns)
    boxes=[anchors.box(item,h) for h in [policy['required_core_half_extents_m'],policy['primary_half_extents_m'],*policy['candidate_half_extents_m']]]
    values=surface._verified_rows(proof,rows,deadline_ns=deadline_ns)
    recipe=dict(schema='surface-deformation-anchor-query-v1',expected_source_sha256=proof['source_sha256'],catalog_sha256=policy['catalog_sha256'],
        anchor_id=policy['anchor_id'],half_extents_m=policy['primary_half_extents_m'])
    primary_query,primary_trace=anchors.resolve(proof,recipe,pins=pins,deadline_ns=deadline_ns)
    cache=region.prepare_geometry(proof,deadline_ns=deadline_ns)
    primary=region.select_prepared(cache,primary_query,deadline_ns=deadline_ns)
    baseline=copy.deepcopy(report_factory(primary,primary_trace));need(type(baseline) is dict and baseline.get('source_sha256')==proof['source_sha256'],'report_binding')
    baseline_blob=_payload(baseline,deadline_ns);primary_ids=set(primary['matched_triangle_indices'])
    started=r.time.perf_counter_ns();optional=min(deadline_ns,started+policy['planning_budget_ms']*1_000_000)
    quality=dict(schema='surface-deformation-context-quality-v1',policy_sha256=policy_sha256,decision='retained_primary',reason='planning_budget',
        required_core_half_extents_m=policy['required_core_half_extents_m'][:],core_complete=False,core_triangle_indices=None,core_states=None,
        core_unknown_reasons=None,core_rows_sha256=None,primary_surplus_members=None,selected_surplus_members=None,
        candidates_evaluated=0,search_complete=False,contact_extent='not_checked')
    audit=dict(schema='surface-deformation-context-audit-v1',source_sha256=proof['source_sha256'],policy_sha256=policy_sha256,
        policy=copy.deepcopy(policy),primary_report=copy.deepcopy(baseline),primary_membership=copy.deepcopy(primary),primary_publication_bytes=len(baseline_blob),
        primary_publication_sha256=hashlib.sha256(baseline_blob).hexdigest(),planning_started_ns=started,planning_deadline_ns=optional,
        core_rows=None,core_triangle_indices=None,core_rows_sha256=None,candidate_records=[],selected_candidate_index=None,
        original_deadline_ns=deadline_ns,geometry_cache_preparations=1,B2_rows_passes=1)

    def finish(report,reason,*,selected_index=None,search_complete=True):
        r.check_time(deadline_ns);out=copy.deepcopy(report);q=copy.deepcopy(quality)
        q.update(decision='selected_context' if selected_index is not None else 'retained_primary',reason=reason,search_complete=search_complete)
        if selected_index is None:q['selected_surplus_members']=q['primary_surplus_members']
        out['context_quality']=q;blob=_payload(out,deadline_ns)
        retained=copy.deepcopy(baseline);retained['context_quality']=dict(q,decision='retained_primary',reason='no_verified_gain',selected_surplus_members=q['primary_surplus_members'])
        audit.update(selected_candidate_index=selected_index,published_publication_bytes=len(blob),published_publication_sha256=hashlib.sha256(blob).hexdigest(),
            kept_primary_publication_bytes=len(publication_bytes(retained)),saved_bytes_vs_primary_anchor=len(baseline_blob)-len(blob),
            planning_elapsed_ns=r.time.perf_counter_ns()-started,decision=q['decision'],reason=reason,search_complete=search_complete)
        if selected_index is not None:r.check_time(optional)
        r.check_time(deadline_ns);return out,audit

    try:
        r.check_time(optional)
        core_query=dict(schema='surface-deformation-region-query-v1',expected_source_sha256=proof['source_sha256'],region=boxes[0])
        core=region.select_prepared(cache,core_query,deadline_ns=optional);r.check_time(optional)
        core_ids=core['matched_triangle_indices'];need(set(core_ids)<=primary_ids,'core_retention')
        core_rows=[values[i] for i in core_ids];counts,reasons=_stats(core_rows);row_sha=r.digest(core_rows)
        quality.update(core_complete=True,core_triangle_indices=core_ids[:],core_states=counts,core_unknown_reasons=reasons,
            core_rows_sha256=row_sha,primary_surplus_members=len(primary_ids)-len(core_ids),selected_surplus_members=len(primary_ids)-len(core_ids))
        audit.update(core_rows=copy.deepcopy(core_rows),core_triangle_indices=core_ids[:],core_rows_sha256=row_sha,core_membership=copy.deepcopy(core))
        r.check_time(optional)
        if not core_ids:return finish(baseline,'focus_empty')
        if counts['unknown']==len(core_ids):return finish(baseline,'focus_all_unknown')
        if quality['primary_surplus_members']<=policy['max_surplus_members']:return finish(baseline,'within_surplus_budget')
        for index,half in enumerate(policy['candidate_half_extents_m']):
            r.check_time(optional)
            candidate_query=dict(schema='surface-deformation-region-query-v1',expected_source_sha256=proof['source_sha256'],region=boxes[index+2])
            candidate=region.select_prepared(cache,candidate_query,deadline_ns=optional);r.check_time(optional)
            ids=set(candidate['matched_triangle_indices']);need(set(core_ids)<=ids<=primary_ids,'core_retention')
            surplus=len(ids)-len(core_ids);quality['candidates_evaluated']+=1
            record=dict(candidate_index=index,half_extents_m=half[:],membership=copy.deepcopy(candidate),surplus_members=surplus,complete=False)
            audit['candidate_records'].append(record)
            if surplus>=quality['primary_surplus_members']:record.update(reason='no_surplus_reduction',complete=True);continue
            if surplus>policy['max_surplus_members']:record.update(reason='surplus_budget_not_met',complete=True);continue
            trace=copy.deepcopy(primary_trace);trace.update(half_extents_m=half[:],region=copy.deepcopy(boxes[index+2]))
            candidate_report=copy.deepcopy(report_factory(candidate,trace))
            need(type(candidate_report) is dict and candidate_report.get('source_sha256')==proof['source_sha256'],'report_binding')
            selected_quality=copy.deepcopy(quality);selected_quality.update(decision='selected_context',reason='verified_byte_gain',selected_surplus_members=surplus,search_complete=True)
            candidate_report['context_quality']=selected_quality;candidate_blob=_payload(candidate_report,deadline_ns)
            saved=len(baseline_blob)-len(candidate_blob)
            record.update(reason='verified_byte_gain' if saved>=policy['min_saved_bytes'] else 'no_publication_byte_gain',publication_bytes=len(candidate_blob),
                publication_sha256=hashlib.sha256(candidate_blob).hexdigest(),saved_bytes_vs_primary_anchor=saved,report=copy.deepcopy(candidate_report))
            r.check_time(optional);record['complete']=True
            if saved>=policy['min_saved_bytes']:
                quality['selected_surplus_members']=surplus
                candidate_report.pop('context_quality')
                return finish(candidate_report,'verified_byte_gain',selected_index=index)
        return finish(baseline,'no_verified_gain')
    except ValueError as exc:
        # Only explicit optional resource failures may retain a completed
        # primary. Original expiry, invalid source/schema/policy never do.
        r.check_time(deadline_ns);reason=str(exc)
        if reason=='rig_pose_original_deadline' and r.time.perf_counter_ns()>=optional:
            return finish(baseline,'planning_budget',search_complete=False)
        if reason in ('rig_pose_deformation_region_arithmetic_budget','rig_pose_deformation_anchor_arithmetic_budget'):
            return finish(baseline,'arithmetic_budget',search_complete=False)
        raise
