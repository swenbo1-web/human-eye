"""Explicit registered read tasks for finite surface facts and references."""
import copy,hashlib,json,math,time,uuid
from . import mesh_structure as raw,surface_geometry as g
from .structure_task import require,digest,TEXT_RESERVATION,hex_id
from .structure_task_control import consumption
from .structure_task_service import _base as _structure_base


def _base(status,session_id):
    value=_structure_base(status,session_id);value['result_kind']='surface_task'
    value['evidence_scope']='finite_raw_surface_facts_not_general_damage_or_write_authority'
    return value
from .forward_deadline import counter_descriptor


def query(value):
    require(type(value) is dict and not set(value)-{'mode','operation','request_id','task_ref','near_m','reference_ref','threshold_m','indices'}
        and value.get('mode')=='mesh_surface' and value.get('operation') in ('diagnose','reference','restore_preview'),'surface_query')
    request=value.get('request_id');require(type(request) is str and 1<=len(request)<=128
        and all(c.isascii() and (c.isalnum() or c in '_.:-') for c in request),'surface_request_id')
    if 'task_ref' in value:require(hex_id(value['task_ref']),'surface_task_ref')
    operation=value['operation']
    if operation=='diagnose':
        require(not set(value)&{'reference_ref','threshold_m','indices'},'surface_diagnose_fields')
        near=value.get('near_m',.00001);require(type(near) in (int,float) and math.isfinite(near) and 0<=near<=.001,'surface_near')
    else:
        require('near_m' not in value and hex_id(value.get('reference_ref')),'surface_reference_ref')
        threshold=value.get('threshold_m',.0001)
        require(type(threshold) in (int,float) and math.isfinite(threshold) and 0<threshold<=.01,'surface_threshold')
        if operation=='reference':require('indices' not in value,'surface_reference_indices')
        else:
            indices=value.get('indices');require(type(indices) is list and 1<=len(indices)<=64 and all(type(i) is int and 0<=i<4096 for i in indices)
                and len(set(indices))==len(indices),'surface_preview_indices')
    return copy.deepcopy(value)


def consume_packet(host,object_id,deadline,near,*,geometry=True):
    from pathlib import Path
    from .blender_host import _RAW_MESH_SHA256
    method='observe_surface_geometry' if geometry else 'capture_surface_source'
    require(all(callable(getattr(host,k,None)) for k in ('surface_geometry_capabilities',method)),'surface_typed_host_unavailable')
    caps=host.surface_geometry_capabilities()
    require(type(caps) is dict and caps==dict(protocol=g.PROTOCOL,helper_sha256=hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest(),
        raw_helper_sha256=_RAW_MESH_SHA256,limits=g.LIMITS,clock=counter_descriptor(),read_only=True,execution_authority=False,images=False),'surface_capability_mismatch')
    request=uuid.uuid4().hex
    packet=host.observe_surface_geometry(request,object_id,deadline,near) if geometry else host.capture_surface_source(request,object_id,deadline)
    fields={'schema','request_id','source','raw','triangles','triangle_polygons'}|({'diagnostic'} if geometry else set())
    require(type(packet) is dict and set(packet)==fields
        and packet['schema']==g.PROTOCOL and packet['request_id']==request,'surface_packet')
    source=packet['source'];require(type(source) is dict and source.get('object_id')==object_id,'surface_target')
    # A separate consumer budget shares the original deadline. This validates
    # transport and repeats predicates; independent mathematical truth is tested
    # separately, not claimed from running the same implementation twice.
    budget=raw.WorkBudget(deadline_ns=deadline)
    prepared=raw.prepare_raw(packet['raw'],{k:source[k] for k in ('object_id','object_instance','document_epoch','capture_id')},budget=budget)
    require(prepared['source']==source,'surface_source_commitment')
    if not geometry:
        g.validate_tessellation(prepared['raw'],packet['triangles'],packet['triangle_polygons'],budget)
        budget.check('surface_source_consumer_complete')
        return prepared,packet,None
    replay=g.analyze(prepared,packet['triangles'],packet['triangle_polygons'],budget=raw.WorkBudget(deadline_ns=deadline),near_m=near)
    reported=copy.deepcopy(packet['diagnostic']);require(type(reported) is dict,'surface_report_type')
    # Capture work differs from consumer validation work; both remain bounded.
    claimed_work=reported.pop('work_used',None);replay.pop('work_used')
    require(type(claimed_work) is int and 0<=claimed_work<=raw.LIMITS['work_units'] and reported==replay,'surface_replay_mismatch')
    budget.check('surface_consumer_complete')
    return prepared,packet,replay


def observe(service,session_id,normalized,*,include_image,focal_id=None):
    value=query(normalized);require(include_image is False,'surface_text_only')
    require(type(session_id) is str and 1<=len(session_id)<=256,'surface_session')
    require(service.config.get('surface_diagnostics_enabled') is True,'surface_requires_local_opt_in')
    if not service.config.get('enabled',True):return _base('disabled',session_id)
    rejected=service._identity_rejection()
    if rejected is not None:return rejected
    with service._locked() as (legacy,runtime),service._observation_scope():
        if legacy.get('inflight') or runtime.status['quarantined']:return _base('host_quarantined',session_id)
        remaining=service._check_request_budget('before_surface_task');timeout=min(20.,remaining) if remaining is not None else 20.
        with consumption(service,value,timeout) as store,store.locked(timeout_s=timeout) as state:
            require(value.get('task_ref',state['task_id'])==state['task_id'] and focal_id in (None,state['object_id']),'surface_bound_target')
            receipt=store.reserve(state,value['request_id'],digest(dict(query=value,object_id=state['object_id'],include_image=False)),want_images=False)
            if receipt is not None:
                result=_base('receipt',session_id);result.update(receipt);result['task_budget']=store.summary(state);return result
            deadline=min(state['deadline_ns'],time.perf_counter_ns()+30_000_000_000)
            if remaining is not None:deadline=min(deadline,time.perf_counter_ns()+int(remaining*1e9))
            result=_base('unavailable',session_id);result['result_kind']='surface_task'
            result['evidence_scope']='finite_raw_surface_facts_not_general_damage_or_write_authority'
            try:
                prepared,packet,report=consume_packet(service.host,state['object_id'],deadline,value.get('near_m',.00001),geometry=value['operation']=='diagnose')
                if value['operation']!='diagnose':
                    registry=service._surface_references;require(registry is not None,'surface_trusted_reference_required')
                    binding=registry.resolve(value['reference_ref'],prepared)
                    require(binding['triangles']==packet['triangles'] and binding['polygon_indices']==packet['triangle_polygons'],'surface_reference_tessellation')
                    from .surface_reference import diagnose,preview_restore
                    budget=raw.WorkBudget(deadline_ns=deadline)
                    report=diagnose(binding,prepared,budget=budget,threshold_m=value.get('threshold_m',.0001)) if value['operation']=='reference' else preview_restore(binding,prepared,value['indices'],budget=budget)
                result.update(status='observed' if report['status']=='preview_only' else report['status'],diagnostic=report,image_status='not_supported',task_succeeded=None)
                result['routing']['observation_status']='complete' if report['status']=='observed' else 'partial'
                require(time.perf_counter_ns()<deadline,'surface_deadline_expired')
                service._check_request_budget('after_surface_task')
            except Exception as exc:
                result['reason']=str(exc)[:500]
                result.pop('diagnostic',None);result['status']='unavailable'
            size=len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf8'))+4096
            if size>TEXT_RESERVATION:
                result=_base('unavailable',session_id);result['reason']='surface_public_text_budget';size=8192
            store.finish(state,value['request_id'],text_bytes=size,images=0,png_bytes=0,outcome=result['status'],image_outcome_known=True,failed=result['status']=='unavailable')
            require(time.perf_counter_ns()<state['deadline_ns'] and time.time_ns()<state['deadline_wall_ns'],'surface_delivery_expired')
            result['task_budget']=store.summary(state);result['accounted_public_text_bytes']=size
            return result
