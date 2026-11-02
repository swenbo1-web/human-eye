"""Independent task-core/context checks over full native snapshots.

SAT and NumPy/SVD provide the numerical answers. Canonical row hashes below
only bind already-checked complete rows; hashes are not numerical ground truth.
"""
import copy,hashlib,json
from verification.deformation_anchor_oracle import expected_box
from verification.deformation_region_oracle import matching_indices,all_facts


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def payload(value):return canonical(value)+b'\n'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


def policy(catalog,anchor_id,case):
    return dict(schema='surface-deformation-context-policy-v1',source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
        anchor_id=anchor_id,required_core_half_extents_m=case['core'][:],primary_half_extents_m=case['primary'][:],
        candidate_half_extents_m=copy.deepcopy(case['candidates']),max_surplus_members=case['max_surplus_members'],min_saved_bytes=256,planning_budget_ms=250)


def selection(catalog,anchor_id,policy_sha256):
    return dict(schema='surface-deformation-context-selection-v1',source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
        anchor_id=anchor_id,policy_sha256=policy_sha256)


def expected_memberships(packet,catalog,operator_policy):
    anchor=next(a for a in catalog['anchors'] if a['anchor_id']==operator_policy['anchor_id'])
    dimensions=[operator_policy['required_core_half_extents_m'],operator_policy['primary_half_extents_m'],*operator_policy['candidate_half_extents_m']]
    boxes=[expected_box(anchor,half) for half in dimensions]
    members=[matching_indices(packet,b['bounds']) for b in boxes]
    core=members[0];core_facts=all_facts(packet,core)
    for ids in members[1:]:assert set(core)<=set(ids),'required core lost'
    return dict(anchor=anchor,core_region=boxes[0],primary_region=boxes[1],candidate_regions=boxes[2:],core_members=core,
        primary_members=members[1],candidate_members=members[2:],core_facts=core_facts,
        primary_surplus=len(set(members[1])-set(core)),candidate_surplus=[len(set(ids)-set(core)) for ids in members[2:]])


def primary_gate(expected,operator_policy):
    if not expected['core_members']:return 'focus_empty'
    if all(row['state']=='unknown' for row in expected['core_facts'].values()):return 'focus_all_unknown'
    if expected['primary_surplus']<=operator_policy['max_surplus_members']:return 'within_surplus_budget'
    return 'needs_candidates'


def check_row(row,truth):
    for key in ('triangle','vertices','state','reason','unweighted_vertices','reference_geometry','current_geometry'):assert row[key]==truth[key],(key,row,truth)
    if truth['state']=='unknown':assert row['principal_stretches'] is None and row['area_ratio'] is None
    else:
        assert max(abs(a-b) for a,b in zip(row['principal_stretches'],truth['principal_stretches']))<1e-9
        assert abs(row['area_ratio']-truth['area_ratio'])<1e-9


def verify_region(report,packet,region):
    q=report['region_query'];ids=matching_indices(packet,region['bounds']);facts=all_facts(packet,ids)
    assert q['region']==region and q['matched_triangle_indices']==ids and q['triangles_total']==len(ids)
    assert q['membership_complete'] is True and q['triangles_scanned']==len(packet['inputs']['mesh']['triangles'])
    counts={state:sum(f['state']==state for f in facts.values()) for state in ('measured','collapsed','unknown')}
    for key,count in counts.items():assert q['triangles_'+key]==count
    unknown={f['reason'] for f in facts.values() if f['state']=='unknown'}
    assert q['unknown_reasons']=={reason:sum(f['reason']==reason for f in facts.values() if f['state']=='unknown') for reason in sorted(unknown)}
    assert q['status']==('empty' if not ids else 'partial' if counts['unknown'] else 'observed')
    assert q['details_omitted']==len(ids)-len(q['triangles']) and len(q['triangles'])<=4
    for row in q['triangles']:check_row(row,facts[row['triangle']])
    measurable={i:f for i,f in facts.items() if f['state']!='unknown'}
    for name,field,op in [('max_principal_stretch',lambda f:f['principal_stretches'][0],max),('min_principal_stretch',lambda f:f['principal_stretches'][1],min),
            ('min_area_ratio',lambda f:f['area_ratio'],min),('max_area_ratio',lambda f:f['area_ratio'],max)]:
        witness=q['metric_extrema'][name]
        if not measurable:assert witness is None
        else:
            assert witness['triangle'] in measurable and abs(witness['value']-field(measurable[witness['triangle']]))<1e-9
            assert abs(witness['value']-op(field(f) for f in measurable.values()))<1e-9
    assert q['metric_scope']=='whole_original_triangles_not_clipped_integrals'
    assert q['extrema_scope']=='measured_and_collapsed_members_only'
    assert report['execution_authority'] is False and report['geometry_setters']==0 and report['original_file_saved'] is False
    return dict(matched_triangle_indices=ids,facts=facts,counts=counts)


def verify_core_rows(rows,expected):
    assert type(rows) is list and [r['triangle'] for r in rows]==expected['core_members']
    for row in rows:check_row(row,expected['core_facts'][row['triangle']])
    return digest(rows)


def required_gain(primary,selected,expected,operator_policy):
    ids=selected['region_query']['matched_triangle_indices'];core=set(expected['core_members'])
    assert core<=set(ids)
    surplus=len(set(ids)-core)
    assert surplus<expected['primary_surplus'] and surplus<=operator_policy['max_surplus_members']
    saved=len(payload(primary))-len(payload(selected))
    assert saved>=operator_policy['min_saved_bytes'],('final DTO has no required net gain',saved)
    return dict(primary_payload_bytes=len(payload(primary)),selected_payload_bytes=len(payload(selected)),saved_bytes=saved,selected_surplus=surplus)


def verify_context(report,audit,packet,catalog,operator_policy,primary):
    expected=expected_memberships(packet,catalog,operator_policy);quality=report['context_quality']
    assert quality['schema']=='surface-deformation-context-quality-v1' and quality['policy_sha256']==audit['policy_sha256']
    assert quality['required_core_half_extents_m']==operator_policy['required_core_half_extents_m']
    assert quality['contact_extent']=='not_checked'
    assert audit['primary_report']==primary
    assert audit['primary_publication_bytes']==len(payload(primary)) and audit['primary_publication_sha256']==hashlib.sha256(payload(primary)).hexdigest()
    assert audit['published_publication_bytes']==len(payload(report)) and audit['published_publication_sha256']==hashlib.sha256(payload(report)).hexdigest()
    assert audit['geometry_cache_preparations']==audit['B2_rows_passes']==1
    if quality['core_complete']:
        assert quality['core_triangle_indices']==audit['core_triangle_indices']==expected['core_members']
        row_sha=verify_core_rows(audit['core_rows'],expected)
        assert quality['core_rows_sha256']==audit['core_rows_sha256']==row_sha
        counts={s:sum(f['state']==s for f in expected['core_facts'].values()) for s in ('measured','collapsed','unknown')}
        reasons={f['reason'] for f in expected['core_facts'].values() if f['state']=='unknown'}
        assert quality['core_states']==counts
        assert quality['core_unknown_reasons']=={why:sum(f['reason']==why for f in expected['core_facts'].values() if f['state']=='unknown') for why in sorted(reasons)}
        assert quality['primary_surplus_members']==expected['primary_surplus']
    else:
        assert quality['reason'] in ('planning_budget','arithmetic_budget') and quality['decision']=='retained_primary'
        assert quality['core_triangle_indices'] is None and quality['core_rows_sha256'] is None
    records=audit['candidate_records'];assert quality['candidates_evaluated']==len(records)
    for index,record in enumerate(records):
        assert record['candidate_index']==index and record['half_extents_m']==operator_policy['candidate_half_extents_m'][index]
        assert record['membership']['matched_triangle_indices']==expected['candidate_members'][index]
        assert record['surplus_members']==expected['candidate_surplus'][index]
        if 'report' in record:
            value=record['report'];verify_region(value,packet,expected['candidate_regions'][index])
            assert record['publication_bytes']==len(payload(value)) and record['publication_sha256']==hashlib.sha256(payload(value)).hexdigest()
            assert record['saved_bytes_vs_primary_anchor']==len(payload(primary))-len(payload(value))
        elif record.get('complete'):
            assert record['reason'] in ('no_surplus_reduction','surplus_budget_not_met')
    if quality['decision']=='selected_context':
        index=audit['selected_candidate_index'];assert type(index) is int and index==len(records)-1
        assert quality['reason']=='verified_byte_gain' and quality['search_complete'] is True
        assert records[index]['complete'] is True and records[index]['reason']=='verified_byte_gain'
        assert records[index]['report']==report
        check=verify_region(report,packet,expected['candidate_regions'][index]);gain=required_gain(primary,report,expected,operator_policy)
        assert quality['selected_surplus_members']==gain['selected_surplus']
    else:
        assert quality['decision']=='retained_primary' and audit['selected_candidate_index'] is None
        check=verify_region(report,packet,expected['primary_region']);body=copy.deepcopy(report);body.pop('context_quality');assert body==primary
        if quality['core_complete']:assert quality['selected_surplus_members']==expected['primary_surplus']
        gate=primary_gate(expected,operator_policy)
        if gate!='needs_candidates':assert quality['reason']==gate and not records
        elif quality['reason'] not in ('planning_budget','arithmetic_budget'):
            assert quality['reason']=='no_verified_gain' and len(records)==len(operator_policy['candidate_half_extents_m'])
            assert not any(r.get('complete') and r.get('reason')=='verified_byte_gain' for r in records)
        gain=dict(primary_payload_bytes=len(payload(primary)),selected_payload_bytes=len(payload(report)),saved_bytes=len(payload(primary))-len(payload(report)))
    return dict(core_members=expected['core_members'],core_facts=expected['core_facts'],primary_members=expected['primary_members'],
        selected_members=check['matched_triangle_indices'],selected_states=check['counts'],gate=primary_gate(expected,operator_policy),
        selected=quality['decision']=='selected_context',reason=quality['reason'],bytes=gain)
