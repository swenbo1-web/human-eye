"""Private vertical integration for M1-02; no public MCP/Hook dispatch yet."""
from __future__ import annotations
import copy
import hashlib
import time
import uuid
from . import mesh_structure as m
from .blender_host import _RAW_MESH_SHA256
from .forward_deadline import counter_descriptor


def validate_result(value, *, object_id, request_id, categories, deadline_ns):
    """Check a pinned typed host's summary, not re-attest its geometry remotely."""
    need=m._require;integer=m._integer
    raw=m._bytes(value);need(len(raw)<=m.LIMITS['report_bytes'],'structure_result_bytes')
    need(type(value) is dict and set(value)=={'protocol','status','report','patches','coverage',
         'omitted_reference','accounting','execution_authority','images'},'structure_result_fields')
    need(value['protocol']==m.PROTOCOL and value['status'] in ('observed','partial')
         and value['execution_authority'] is False and value['images']==[],'structure_result_capability')
    report=value['report'];need(type(report) is dict and set(report)=={'schema','task','source','checks',
         'not_checked','execution_authority','natural_visibility'},'structure_report_fields')
    need(report['schema']=='mesh-structure-evidence-v1' and report['execution_authority'] is False
         and report['natural_visibility']=='not_checked','structure_report_scope')
    wanted=dict(schema='spatial-readonly-task-v1',kind='mesh_structure',task_id=request_id,
                object_ids=[object_id],read_only=True,categories=list(categories))
    need(type(report['task']) is dict and report['task']==wanted
         and report['task'].get('read_only') is True,'structure_task_binding')
    source=report['source']
    need(type(source) is dict and set(source)=={'object_id','object_instance','document_epoch','capture_id',
         'raw_sha256','source_kind','coordinate_frame','length_unit','counts','capture_scope','geometry_complete'},'structure_source_fields')
    need(source['object_id']==object_id and all(m._identifier(source[k]) for k in
         ('object_instance','document_epoch','capture_id')),'structure_source_identity')
    need(type(source['raw_sha256']) is str and len(source['raw_sha256'])==64
         and all(c in '0123456789abcdef' for c in source['raw_sha256']),'structure_source_digest')
    need(source['source_kind']=='raw_mesh' and source['coordinate_frame']=='local'
         and source['length_unit']=='m' and source['capture_scope']=='target_mesh_only'
         and source['geometry_complete'] is True,'structure_source_scope')
    counts=source['counts'];need(type(counts) is dict and set(counts)=={'vertices','edges','polygons','corners'}
         and all(integer(v,0,m.LIMITS[k]) for k,v in counts.items()),'structure_source_counts')
    need(report['not_checked']==[c for c in m.CATEGORIES if c not in categories]+list(m.UNEXAMINED),'structure_unchecked_domains')
    checks=report['checks'];need(type(checks) is dict and set(checks)==set(categories),'structure_category_binding')
    delivered=0;has_partial=False
    for category,record in checks.items():
        need(type(record) is dict and set(record)=={'state','scanned','found','total','regions','omitted','reason','omission_reason'},'structure_check_fields')
        need(record['state'] in ('complete','partial'),'structure_check_state')
        need(type(record['scanned']) is dict and set(record['scanned'])==set(counts)
             and all(integer(v,0,counts[k]) for k,v in record['scanned'].items()),'structure_scan_counts')
        regions=record['regions']
        need(type(regions) is list and len(regions)<=m.LIMITS['regions'],'structure_regions')
        need(integer(record['found']) and integer(record['omitted'])
             and record['found']==len(regions)+record['omitted'],'structure_found_count')
        need(record['omission_reason']==('output_budget' if record['omitted'] else None),'structure_omission')
        seen=set()
        for region in regions:
            need(type(region) is list and 1<=len(region)<=m.LIMITS['members_per_region'],'structure_region_size')
            if category=='isolated_vertices':
                need(all(integer(i,0,counts['vertices']-1) for i in region),'structure_vertex_index')
                canonical=tuple(sorted(region))
            else:
                need(all(type(e) is list and len(e)==2 and e[0]!=e[1]
                         and all(integer(i,0,counts['vertices']-1) for i in e) for e in region),'structure_edge_indices')
                canonical=tuple(sorted(tuple(sorted(e)) for e in region))
            need(len(set(canonical))==len(canonical) and canonical not in seen,'duplicate_structure_region')
            seen.add(canonical)
        delivered+=len(regions)
        if record['state']=='complete':
            need(record['scanned']==counts and integer(record['total']) and record['total']==record['found']
                 and record['reason'] is None,'structure_complete_scan')
        else:
            has_partial=True;need(record['total'] is None and m._identifier(record['reason']),'structure_partial_total')
    need(delivered<=m.LIMITS['regions'] and (value['status']=='partial')==has_partial,'structure_summary_status')
    accounting=value['accounting']
    need(type(accounting) is dict and set(accounting)=={'work_units','max_work_units','source_bytes',
         'deadline_ns','deadline_scope','task_wide_budget_enforced'},'structure_accounting_fields')
    need(integer(accounting['max_work_units'],0,m.LIMITS['work_units'])
         and integer(accounting['work_units'],0,accounting['max_work_units'])
         and integer(accounting['source_bytes'],0,m.LIMITS['source_bytes'])
         and type(accounting['deadline_ns']) is int and accounting['deadline_ns']==deadline_ns
         and accounting['task_wide_budget_enforced'] is False
         and accounting['deadline_scope']=='single_call_cooperative_checkpoints','structure_accounting')
    patches=value['patches'];need(type(patches) is list and len(patches)==delivered,'structure_patch_count')
    patch_keys=set();patch_counts={c:0 for c in categories}
    for patch in patches:
        need(type(patch) is dict and set(patch)=={'category','cluster_ordinal','element_kind','source_indices',
             'membership_sha256','raw_sha256','object_instance','document_epoch'},'structure_patch_fields')
        category=patch['category'];need(type(category) is str and category in categories,'structure_patch_category')
        need(integer(patch['cluster_ordinal'],0,checks[category]['found']-1),'structure_patch_ordinal')
        key=(category,patch['cluster_ordinal']);need(key not in patch_keys,'duplicate_structure_patch');patch_keys.add(key)
        kind='vertex' if category=='isolated_vertices' else 'edge'
        ids=patch['source_indices'];extent=counts['vertices' if kind=='vertex' else 'edges']
        need(patch['element_kind']==kind and type(ids) is list and 1<=len(ids)<=64
             and all(integer(i,0,extent-1) for i in ids) and sorted(set(ids))==ids,'structure_patch_indices')
        need(all(patch[k]==source[k] for k in ('raw_sha256','object_instance','document_epoch'))
             and patch['membership_sha256']==m._digest(ids),'structure_patch_source_binding')
        need(patch_counts[category]<len(checks[category]['regions']),'structure_patch_distribution')
        region=checks[category]['regions'][patch_counts[category]];patch_counts[category]+=1
        need(len(ids)==len(region) and (kind!='vertex' or ids==region),'structure_patch_region')
    need(all(patch_counts[c]==len(checks[c]['regions']) for c in categories),'structure_patch_distribution')
    need(value['omitted_reference']==dict(object_id=object_id,object_instance=source['object_instance'],
        document_epoch=source['document_epoch'],raw_sha256=source['raw_sha256'],
        query='repeat_structure_on_fresh_matching_raw_source',retrieval_endpoint_available=False),'structure_backreference')
    coverage=value['coverage'];need(type(coverage) is dict and set(coverage)=={'vertices_prefix','edges_prefix',
        'polygons_prefix','polygon_corners','component_categories_completed'},'structure_coverage_fields')
    for name,k in [('vertices_prefix','vertices'),('edges_prefix','edges'),('polygons_prefix','polygons'),('polygon_corners','corners')]:
        need(integer(coverage[name],0,counts[k]),'structure_coverage_range')
    need(coverage['component_categories_completed']==[c for c in categories if checks[c]['state']=='complete'],
         'structure_coverage_completed')
    return copy.deepcopy(value)


def observe(service, session_id, object_id, categories):
    """Private service entry. No persistence or new public tool advertisement."""
    m._require(m._identifier(session_id) and m._identifier(object_id),'structure_request_identity')
    m._require(type(categories) in (list,tuple) and 1<=len(categories)<=len(m.SUPPORTED)
        and all(type(c) is str and c in m.SUPPORTED for c in categories)
        and len(set(categories))==len(categories),'structure_request_categories')
    if not service.config.get('enabled',True):return {'status':'disabled','execution_authority':False}
    rejected=service._identity_rejection()
    if rejected is not None:return rejected
    with service._locked() as (state,runtime),service._observation_scope():
        if state.get('inflight') or runtime.status['quarantined']:
            return {'status':'host_quarantined','execution_authority':False}
        host=service.host
        if not callable(getattr(host,'mesh_structure_capabilities',None)) or not callable(getattr(host,'observe_mesh_structure',None)):
            return {'status':'unsupported','reason':'raw_mesh_typed_host_unavailable','execution_authority':False}
        service._check_request_budget('before_structure_capabilities')
        caps=host.mesh_structure_capabilities()
        m._require(type(caps) is dict and caps.get('protocol')==m.PROTOCOL and caps.get('read_only') is True
            and caps.get('execution_authority') is False and caps.get('images') is False
            and caps.get('helper_sha256')==_RAW_MESH_SHA256
            and caps.get('supported_categories')==list(m.SUPPORTED)
            and caps.get('clock')==counter_descriptor(),'structure_host_capability_mismatch')
        service._check_request_budget('after_structure_capabilities')
        remaining=service._remaining_request_budget()
        duration=30. if remaining is None else min(30.,remaining)
        deadline=time.perf_counter_ns()+int(duration*1e9);request_id=uuid.uuid4().hex
        result=host.observe_mesh_structure(request_id,object_id,list(categories),deadline)
        service._check_request_budget('after_structure_observation')
        m._require(time.perf_counter_ns()<deadline,'structure_delivery_deadline_expired')
        validated=validate_result(result,object_id=object_id,request_id=request_id,categories=categories,deadline_ns=deadline)
        return dict(status=validated['status'],session_id=session_id,diagnostic=validated,
                    execution_authority=False,executed=False,allow_action=False)
