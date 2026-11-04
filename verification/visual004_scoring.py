"""Condition-blind finite spatial answer scoring, not source/host attestation.

Only a trusted controller supplies contracts and deliveries after checking the
actual host event and PNG/text bytes. Model-supplied delivery records are not
evidence. Truth is frozen authored analytic geometry, never HE success flags.
Free-text interpretation and evidence sufficiency still require blind review.
"""
from __future__ import annotations
import hashlib,json,math

CONTRACT_SCHEMA='visual004-score-contract-v1'
ANSWER_SCHEMA='visual004-answer-v1'
BINDINGS=('case_id','task_run_id','asset_sha256','task_sha256')
IMAGE_LIMITS=dict(max_images=8,max_single_pixels=1024**2,max_total_pixels=4*768**2)
ANSWER_FIELDS={'schema',*BINDINGS,'objects','identity_evidence_refs','facts','visual_evidence_used','interpretation'}
FACT_FIELDS={'status','value','evidence_refs','uncertainty'}
UNCERTAINTY_FIELDS={'basis','physical_metrology','note'}
KINDS={'closest_local_region','target_to_reference_world_axis','aabb_center_direction_xyz',
    'minimum_surface_distance_m','vertical_clearance_m','opposite_side_clearance_m',
    'vertical_is_not_minimum_3d_distance','internal_surface_not_visible_from_external_opaque_view',
    'separation_class','pin_location_relative_to_hole'}

class ScoringError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)
def need(value,reason):
    if not value:raise ScoringError(reason)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def same(a,b):return canonical(a)==canonical(b)
def finite(value):
    try:return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:return False
def text(value,max_length=4096):return type(value) is str and 0<len(value)<=max_length and bool(value.strip()) and '\x00' not in value
def hex64(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)

def parse_answer(raw):
    """Parse raw model JSON without dropping duplicate keys or nonfinite values."""
    need(type(raw) in (str,bytes),'answer_json_type')
    def unique(pairs):
        out={}
        for key,value in pairs:
            need(key not in out,'duplicate_answer_key');out[key]=value
        return out
    def bad_constant(value):raise ScoringError('nonfinite_answer_json')
    try:return json.loads(raw,object_pairs_hook=unique,parse_constant=bad_constant)
    except ScoringError:raise
    except (ValueError,TypeError,UnicodeError):raise ScoringError('answer_json_invalid') from None

def public_answer_schema():
    """Public shape only: no truth roles, names, values or selected views."""
    return dict(schema=ANSWER_SCHEMA,bindings=list(BINDINGS),objects='each public required role maps to exact neutral object name, or null when unknown',
        identity_evidence_refs='actual delivered evidence IDs, not paths or model-invented proof',
        facts='all public required_fact_ids, each with status/value/evidence_refs/uncertainty',
        fact_status=['known','unknown'],unknown_value=None,
        uncertainty=dict(basis=['geometry','image','mixed','insufficient'],physical_metrology=False,note='nonempty explanation of uncertainty'),
        visual_evidence_used='self-declaration, distinct from host-confirmed image delivery; never causal proof',
        interpretation='spatial reasoning, visible versus occluded limits, numerical versus image evidence',
        closest_region='free description permitted; non-enumerated descriptions await independent blind review',
        directions='world axes; target_to_reference uses nearest target surface toward reference; aabb_center_direction_xyz uses target minus reference')

def validate_contract(contract):
    need(type(contract) is dict and set(contract)=={'schema',*BINDINGS} and contract['schema']==CONTRACT_SCHEMA,'contract_schema')
    need(text(contract['case_id'],64) and text(contract['task_run_id'],256)
        and hex64(contract['asset_sha256']) and hex64(contract['task_sha256']),'contract_binding')

def validate_reference(public,truth,contract):
    need(type(public) is dict and type(truth) is dict and public.get('case_id')==truth.get('case_id')==contract['case_id'],'reference_case')
    roles=public.get('required_roles');facts=public.get('required_fact_ids')
    need(type(roles) is list and roles and len(set(roles))==len(roles) and all(text(r,64) for r in roles),'reference_roles')
    need(type(facts) is list and facts and len(set(facts))==len(facts) and all(text(f,64) for f in facts),'reference_fact_ids')
    need(type(truth.get('expected_objects')) is dict and set(truth['expected_objects'])==set(roles)
        and all(text(name,256) for name in truth['expected_objects'].values()),'reference_objects')
    need(type(truth.get('facts')) is dict and set(truth['facts'])==set(facts),'reference_facts')
    for fact in truth['facts'].values():
        need(type(fact) is dict and fact.get('kind') in KINDS and 'value' in fact,'reference_fact')
        value=fact['value']
        if 'tolerance' in fact:
            need(finite(value) and finite(fact['tolerance']) and fact['tolerance']>0,'reference_tolerance')
        if 'accepted_values' in fact:
            need(type(fact['accepted_values']) is list and fact['accepted_values']
                and any(same(value,v) for v in fact['accepted_values']),'reference_accepted_values')
    canonical(truth)
    return roles,facts

def validate_deliveries(deliveries,contract):
    """Controller-attested actual delivery registry, not a model parameter.

    Failed/undelivered operations stay in the cost log, outside this registry.
    A PNG hash is not validated against pixels here: the controller must check
    the real host image block before admitting its record.
    """
    need(type(deliveries) is list,'delivery_registry');out={};slots=set();pixels=0;images=0
    for record in deliveries:
        need(type(record) is dict and all(same(record.get(k),contract[k]) for k in BINDINGS),'delivery_binding')
        identity=record.get('evidence_id');host=record.get('actual_host_event_id');slot=record.get('host_block_index',0)
        need(text(identity,256) and text(host,512) and type(slot) is int and slot>=0,'delivery_host_identity')
        need(identity not in out and (host,slot) not in slots,'duplicate_delivery_reference')
        need(record.get('delivered') is True,'evidence_not_delivered')
        kind=record.get('kind');payload=record.get('payload')
        need(kind in ('image','geometry','text') and type(payload) is dict,'delivery_payload')
        need(record.get('payload_sha256')==digest(payload),'delivery_payload_digest')
        if kind=='image':
            width=payload.get('width');height=payload.get('height')
            need(type(width) is int and type(height) is int and 0<width<=1024 and 0<height<=1024
                and width*height<=IMAGE_LIMITS['max_single_pixels'] and hex64(payload.get('png_sha256')),'delivery_image_metadata')
            images+=1;pixels+=width*height
            need(images<=IMAGE_LIMITS['max_images'] and pixels<=IMAGE_LIMITS['max_total_pixels'],'delivery_image_budget')
        else:need('text' in payload or 'data' in payload,'delivery_text_or_geometry')
        out[identity]=record;slots.add((host,slot))
    return out,dict(host_confirmed_image_delivery=bool(images),image_blocks=images,delivered_image_pixels=pixels,
        scope='trusted-controller actual-host image receipt, not model self-declaration or causality')

def _refs(refs,registry):
    need(type(refs) is list and len(refs)<=32 and all(text(r,256) for r in refs)
        and len(set(refs))==len(refs),'evidence_refs')
    need(all(ref in registry for ref in refs),'evidence_not_in_actual_delivery_registry')
    return {registry[ref]['kind'] for ref in refs}

def _uncertainty(value):
    need(type(value) is dict and set(value)==UNCERTAINTY_FIELDS,'uncertainty_schema')
    need(value['basis'] in ('geometry','image','mixed','insufficient') and text(value['note']),'uncertainty_basis_or_note')
    need(type(value['physical_metrology']) is bool and value['physical_metrology'] is False,'unsupported_physical_precision_claim')
    return value['basis']

def _fact(row,expected,registry,visual_claim):
    need(type(row) is dict and set(row)==FACT_FIELDS,'fact_schema')
    need(row['status'] in ('known','unknown'),'fact_status')
    basis=_uncertainty(row['uncertainty']);modalities=_refs(row['evidence_refs'],registry)
    result=dict(status=row['status'],kind=expected['kind'],correct=False,safe_unknown=False,
        pending_blind_review=False,evidence_modalities=sorted(modalities),issues=[])
    if row['status']=='unknown':
        need(row['value'] is None and basis=='insufficient','unknown_must_be_explicit_not_false')
        result.update(safe_unknown=True,issues=['honest_unknown_incomplete_where_frozen_geometry_has_answer'])
        return result
    need(row['evidence_refs'] and basis!='insufficient','known_fact_needs_actual_evidence')
    if basis=='image':need('image' in modalities and visual_claim,'visual_claim_without_referenced_image')
    elif basis=='geometry':need('geometry' in modalities,'geometry_claim_without_geometry_evidence')
    elif basis=='mixed':need('image' in modalities and 'geometry' in modalities and visual_claim,'mixed_claim_without_both_modalities')
    actual=row['value'];wanted=expected['value']
    if 'tolerance' in expected:
        need(finite(actual),'numeric_fact_requires_finite_number_not_boolean')
        result['correct']=abs(actual-wanted)<=expected['tolerance'];result['absolute_error_m']=abs(actual-wanted)
        result['tolerance_m']=expected['tolerance']
    elif type(wanted) is bool:
        need(type(actual) is bool,'boolean_fact_requires_boolean')
        result['correct']=actual is wanted
    elif expected['kind']=='closest_local_region':
        need(text(actual),'closest_region_text')
        if any(same(actual,v) for v in expected.get('accepted_values',[wanted])):result['correct']=True
        else:
            result.update(correct=None,pending_blind_review=True,
                issues=['free_region_description_needs_blind_review_not_automatic_full_credit'])
    else:result['correct']=any(same(actual,v) for v in expected.get('accepted_values',[wanted]))
    if result['correct'] is False:result['issues'].append('incorrect_frozen_spatial_fact')
    if basis in ('image','mixed'):
        result['evidence_sufficiency_review']='actual PNG resolution, occlusion and claim precision require blind review; native projected pixel opportunities do not substitute'
    return result

def grade(answer,contract,public_task,private_truth,deliveries):
    """Score the fixed roles/facts; no P/N mapping or producer success input.

    Mechanical correctness does not adjudicate free prose or claim sufficiency.
    Final task quality must combine this result with the retained blind review.
    """
    result=dict(schema='visual004-spatial-score-v1',source='scoring independent',binding_valid=False,
        objects={},facts={},issues=[],mechanical_complete=False,final_complete=None,
        host_confirmed_image_delivery=False,self_declared_visual_evidence_used=None,
        visual_evidence_causal_gain_proven=False,needs_blind_review=['interpretation_and_evidence_sufficiency'],
        denominators=dict(objects=None,facts=None),correct_counts=dict(objects=0,facts=0),
        safe_unknown_count=0,pending_region_count=0,
        precision_scope='frozen authored coordinate tolerance; not physical metrology',
        direction_scope={'target_to_reference_world_axis':'nearest target surface toward reference',
            'aabb_center_direction_xyz':'target AABB center minus reference AABB center'})
    try:
        validate_contract(contract);roles,fact_ids=validate_reference(public_task,private_truth,contract)
        result['denominators']=dict(objects=len(roles),facts=len(fact_ids))
        registry,image_info=validate_deliveries(deliveries,contract);result.update(image_info)
        need(type(answer) is dict and set(answer)==ANSWER_FIELDS and answer['schema']==ANSWER_SCHEMA,'answer_schema')
        need(all(same(answer.get(k),contract[k]) for k in BINDINGS),'answer_binding')
        need(type(answer['objects']) is dict and not set(answer['objects'])-set(roles),'answer_object_roles')
        need(type(answer['facts']) is dict and not set(answer['facts'])-set(fact_ids),'answer_fact_ids')
        need(type(answer['visual_evidence_used']) is bool and text(answer['interpretation'],16384),'answer_visual_or_interpretation')
        result['self_declared_visual_evidence_used']=answer['visual_evidence_used']
        identity_modes=_refs(answer['identity_evidence_refs'],registry);all_refs=set(answer['identity_evidence_refs'])
        if any(name is not None for name in answer['objects'].values()):need(identity_modes,'known_identity_needs_evidence')
        result['binding_valid']=True
        for role in roles:
            name=answer['objects'].get(role)
            if role not in answer['objects']:
                result['objects'][role]=dict(correct=False,status='omitted');result['issues'].append('missing_object:'+role)
            elif name is None:result['objects'][role]=dict(correct=False,status='unknown')
            else:
                need(text(name,256),'object_name')
                correct=name==private_truth['expected_objects'][role]
                result['objects'][role]=dict(correct=correct,status='known',reported_name=name)
                if correct:result['correct_counts']['objects']+=1
                else:result['issues'].append('wrong_object:'+role)
        for fact_id in fact_ids:
            if fact_id not in answer['facts']:
                result['facts'][fact_id]=dict(correct=False,status='omitted',issues=['missing_fact'])
                result['issues'].append('missing_fact:'+fact_id);continue
            row=answer['facts'][fact_id]
            try:
                scored=_fact(row,private_truth['facts'][fact_id],registry,answer['visual_evidence_used'])
                result['facts'][fact_id]=scored;all_refs.update(row['evidence_refs'])
                if scored['correct'] is True:result['correct_counts']['facts']+=1
                elif scored['safe_unknown']:result['safe_unknown_count']+=1
                elif scored['pending_blind_review']:
                    result['pending_region_count']+=1;result['needs_blind_review'].append('closest_region:'+fact_id)
                else:result['issues'].append('wrong_fact:'+fact_id)
            except ScoringError as exc:
                result['facts'][fact_id]=dict(correct=False,status='invalid',issues=[exc.reason]);result['issues'].append(fact_id+':'+exc.reason)
        referenced_images=[ref for ref in all_refs if ref in registry and registry[ref]['kind']=='image']
        result['referenced_image_evidence_ids']=sorted(referenced_images)
        if answer['visual_evidence_used']:need(referenced_images,'visual_claim_without_referenced_image')
        elif referenced_images:need(False,'visual_usage_declaration_conflicts_with_image_refs')
        result['mechanical_complete']=(not result['issues'] and result['correct_counts']['objects']==len(roles)
            and result['correct_counts']['facts']==len(fact_ids))
    except ScoringError as exc:result['issues'].append(exc.reason)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError):result['issues'].append('malformed_input')
    return result

__all__=['CONTRACT_SCHEMA','ANSWER_SCHEMA','IMAGE_LIMITS','canonical','digest','parse_answer',
    'public_answer_schema','validate_contract','validate_reference','validate_deliveries','grade']
