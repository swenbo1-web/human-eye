"""A registered single-object task through the existing observation tool."""
from __future__ import annotations
import base64,copy,json,time,uuid
from . import mesh_structure as m, mesh_structure_service as raw_consumer
from . import patch_observation as image_consumer
from .structure_task import TaskStore,TaskRefused,require,query,digest,TEXT_RESERVATION
from .forward_deadline import counter_descriptor
from .blender_host import _RAW_MESH_SHA256


def _raw(host,object_id,categories,deadline):
    require(all(callable(getattr(host,k,None)) for k in ('mesh_structure_capabilities','observe_mesh_structure')),
            'typed_raw_host_unavailable')
    caps=host.mesh_structure_capabilities()
    require(type(caps) is dict and caps.get('protocol')==m.PROTOCOL and caps.get('read_only') is True
        and caps.get('execution_authority') is False and caps.get('images') is False
        and caps.get('helper_sha256')==_RAW_MESH_SHA256 and caps.get('supported_categories')==list(m.SUPPORTED)
        and caps.get('clock')==counter_descriptor(),'raw_capability_mismatch')
    require(time.perf_counter_ns()<deadline,'deadline_expired')
    request=uuid.uuid4().hex
    value=host.observe_mesh_structure(request,object_id,categories,deadline)
    require(time.perf_counter_ns()<deadline,'deadline_expired')
    return raw_consumer.validate_result(value,object_id=object_id,request_id=request,categories=categories,deadline_ns=deadline)


def _references(state,diagnostic):
    """Only complete delivered patches receive a reference; positions may be unknown."""
    old={digest(p):ref for ref,p in state['refs'].items()}
    chosen=diagnostic['patches'][:state['limits']['refs']];refs={};public=[]
    for patch in chosen:
        key=old.get(digest(patch),uuid.uuid4().hex);refs[key]=copy.deepcopy(patch)
        public.append(dict(patch_ref=key,category=patch['category'],cluster_ordinal=patch['cluster_ordinal'],
            element_kind=patch['element_kind'],member_count=len(patch['source_indices']),
            position_status=patch['position']['status'],raw_sha256=patch['raw_sha256']))
    state['refs']=refs
    return public,len(diagnostic['patches'])-len(public)


def _base(status,session_id):
    return dict(status=status,session_id=session_id,result_kind='structure_task',execution_authority=False,
        executed=False,allow_action=False,task_succeeded=None,
        evidence_scope='single_target_structural_facts_not_damage_or_pair_measurement',
        routing={'route':'engine','observation_status':'unavailable','reason_codes':[]})


def observe(service,session_id,normalized,*,include_image,focal_id=None):
    normalized=query(normalized)
    require(type(session_id) is str and 1<=len(session_id)<=256,'bounded_session_label')
    require(not (normalized['operation']=='diagnose' and include_image),'diagnose_requires_include_image_false')
    if not service.config.get('enabled',True):return _base('disabled',session_id)
    rejected=service._identity_rejection()
    if rejected is not None:return rejected
    if not service.config.get('structure_task_file'):
        value=_base('unsupported',session_id);value['reason']='structure_task_registration_required';return value
    with service._locked() as (legacy,runtime),service._observation_scope():
        if legacy.get('inflight') or runtime.status['quarantined']:return _base('host_quarantined',session_id)
        store=getattr(service,'_structure_task_store',None)
        if store is None:
            store=TaskStore(service.config_path,service.config_fingerprint);service._structure_task_store=store
        remaining=service._remaining_request_budget()
        with store.locked(timeout_s=20. if remaining is None else min(20.,remaining)) as state:
            require(focal_id in (None,state['object_id']),'bound_object_cannot_change')
            # Caller labels and natural-language hints do not select a ledger.
            fingerprint=digest(dict(query=normalized,object_id=state['object_id'],include_image=include_image))
            receipt=store.reserve(state,normalized['request_id'],fingerprint,want_images=include_image)
            if receipt is not None:
                result=_base('receipt',session_id);result.update(receipt)
                result['task_budget']=store.summary(state);return result
            record=state['requests'][normalized['request_id']];image_called=False;image_known=True
            result=_base('partial',session_id);images=[];diagnostic=None;deadline=state['deadline_ns']
            try:
                remaining=service._check_request_budget('before_structure_task_host')
                now=time.perf_counter_ns();deadline=min(state['deadline_ns'],now+30_000_000_000)
                if remaining is not None:deadline=min(deadline,now+int(remaining*1e9))
                selected=copy.deepcopy(state['refs'].get(normalized.get('patch_ref')))
                if normalized['operation']=='patch':require(selected is not None,'patch_ref_not_current')
                diagnostic=_raw(service.host,state['object_id'],state['categories'],deadline)
                result['diagnostic']=diagnostic;result['status']=diagnostic['status']
                result['routing']['observation_status']='partial' if diagnostic['status']=='partial' else 'complete'
                result['patch_refs'],result['patch_references_omitted']=_references(state,diagnostic)
                result['image_status']='not_requested';result['reference_status']='not_requested'
                if normalized['operation']=='patch':
                    fresh=next((p for p in diagnostic['patches'] if digest(p)==digest(selected)),None)
                    result['reference_status']='current' if fresh is not None else 'stale'
                    if fresh is None:
                        result['status']='partial';result['image_status']='stale_patch';result['routing']['observation_status']='partial'
                    else:
                        result['selected_patch']=fresh
                        if include_image:
                            result['image_status']='budget_exhausted'
                            if record['reserved']['images']:
                                require(all(callable(getattr(service.host,k,None)) for k in
                                    ('patch_observation_capabilities','observe_patch')),'typed_patch_host_unavailable')
                                caps=image_consumer.validate_capabilities(service.host.patch_observation_capabilities())
                                require(time.perf_counter_ns()<deadline,'deadline_expired')
                                image_called=True;image_known=False;request=uuid.uuid4().hex
                                raw=service.host.observe_patch(request,state['object_id'],fresh,deadline)
                                visual=image_consumer.validate_result(raw,object_id=state['object_id'],patch=fresh,
                                    request_id=request,deadline_ns=deadline,capabilities=caps)
                                images=visual.pop('images');image_known=True
                                result['visual_evidence']=visual;result['image_status']='observed'
                if include_image and result['image_status']!='observed':
                    result['status']='partial';result['routing']['observation_status']='partial'
                require(time.perf_counter_ns()<deadline and time.time_ns()<state['deadline_wall_ns'],'deadline_expired')
                service._check_request_budget('after_structure_task_host')
            except Exception as exc:
                # Facts already validated stay available when image admission or
                # transport fails. An expired task cannot deliver late evidence.
                images=[]
                if diagnostic is not None and time.perf_counter_ns()<deadline and time.time_ns()<state['deadline_wall_ns']:
                    result['status']='partial';result['routing']['observation_status']='partial'
                    result['image_status']='unavailable';result['image_reason']=str(exc)[:500]
                else:
                    result=_base('unavailable',session_id);result['reason']=str(exc)[:500]
            png_bytes=sum(len(base64.b64decode(i['data'],validate=True)) for i in images)
            # Include room for final budget/trace metadata; the MCP projector
            # enforces the resulting text charge before exposing any image.
            text_bytes=len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf8'))+4096
            if text_bytes>TEXT_RESERVATION:
                result=_base('unavailable',session_id);result['reason']='structure_task_public_text_limit'
                images=[];png_bytes=0;image_known=not image_called
                text_bytes=len(json.dumps(result,ensure_ascii=False).encode('utf8'))+4096
            store.finish(state,normalized['request_id'],text_bytes=text_bytes,images=len(images),png_bytes=png_bytes,
                outcome=result['status'],image_outcome_known=image_known,failed=result['status']=='unavailable')
            require(time.perf_counter_ns()<state['deadline_ns'] and time.time_ns()<state['deadline_wall_ns'],'delivery_deadline_expired')
            result['task_budget']=store.summary(state);result['accounted_public_text_bytes']=text_bytes
            if images:result['routing']['images']=images
            return result
