"""Condition-blind scoring of actually delivered static post-anchor evidence.

The caller is a trusted trial controller: delivery records must come from real
transport stdout/input transcripts, not the model or a publication flag. This
module checks their binding and content; it is not a transport attestation
service. Rows in a report or hash-bound snapshot lookup are not fresh targeted
worker inspections. No production selector/geometry/grader is imported.
"""
import hashlib
import json
import math


CONTRACT_SCHEMA='v21-post-anchor-score-contract-v1'
PAYLOAD_SCHEMA='v21-delivered-facts-v1'
SOURCE_FIELDS={'source_ref','source_observation_sha256','original_topology_sha256','anchor_id','core_half_extents_m'}
STATES=('measured','collapsed','unknown')
EXTREMA_FIELDS={'max_principal_stretch','min_principal_stretch','min_area_ratio','max_area_ratio'}
IDENTITY_FIELDS=('task_sha256','run_nonce','consumer_id')
ANSWER_FIELDS={'task_sha256','selected_triangle','frames','interpretation'}
ANSWER_ROW_FIELDS={'label','file_sha256','principal_stretches','area_ratio','state','reason','in_core','has_confirmed_mixed_witness'}


class ScoringError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)


def need(value,reason):
    if not value:raise ScoringError(reason)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def same(actual,expected):return canonical(actual)==canonical(expected)


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def near(actual,expected):
    return finite(actual) and finite(expected) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-9)


def hex_text(value,length=64):
    return type(value) is str and len(value)==length and all(c in '0123456789abcdef' for c in value)


def text(value):return type(value) is str and 0<len(value)<=4096 and '\x00' not in value


def _source(source):
    need(type(source) is dict and set(source)==SOURCE_FIELDS,'contract_source_fields')
    ref=source['source_ref']
    need(type(ref) is dict and set(ref)=={'scene_sha256','rig_object_id','mesh_object_id','frame'},'contract_source_ref')
    need(hex_text(ref['scene_sha256']) and text(ref['rig_object_id']) and text(ref['mesh_object_id']),'contract_source_ref')
    frame=ref['frame']
    need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and finite(frame['subframe']) and 0<=frame['subframe']<1,'contract_saved_frame')
    half=source['core_half_extents_m']
    need(type(half) is list and len(half)==3 and all(finite(v) and v>0 for v in half),'contract_core')
    need(text(source['anchor_id']) and hex_text(source['source_observation_sha256'])
        and hex_text(source['original_topology_sha256']),'contract_source_identity')


def validate_contract(contract):
    need(type(contract) is dict and set(contract)=={'schema','task_sha256','run_nonce','consumer_id','thresholds','sources'}
        and contract['schema']==CONTRACT_SCHEMA,'contract_schema')
    need(hex_text(contract['task_sha256']) and hex_text(contract['run_nonce'],32) and text(contract['consumer_id']),'contract_identity')
    thresholds=contract['thresholds']
    need(type(thresholds) is dict and set(thresholds)=={'high','low'} and finite(thresholds['high'])
        and finite(thresholds['low']) and 0<=thresholds['low']<1<thresholds['high'],'contract_thresholds')
    sources=contract['sources']
    need(type(sources) is dict and len(sources)==2 and all(text(label) for label in sources),'contract_sources')
    for source in sources.values():_source(source)
    need(len({s['original_topology_sha256'] for s in sources.values()})==1,'contract_original_topology')
    canonical(contract)


def _counts(value,reason):
    need(type(value) is dict and set(value)==set(STATES)
        and all(type(v) is int and v>=0 for v in value.values()),reason)


def _metric(value,reason):
    need(type(value) is dict and value.get('state') in STATES,reason)
    if value['state']=='unknown':
        need(text(value.get('reason')) and value.get('principal_stretches') is None and value.get('area_ratio') is None,reason)
    else:
        stretches=value.get('principal_stretches');area=value.get('area_ratio')
        need(type(stretches) is list and len(stretches)==2 and all(finite(v) and v>=0 for v in stretches)
            and stretches[0]>=stretches[1] and finite(area) and area>=0,reason)
        need(value.get('reason') is None if value['state']=='measured' else value.get('reason')=='current_zero_area',reason)
        if value['state']=='collapsed':need(stretches[1]==0 and area==0,reason)


def _same_metric(actual,expected):
    if actual.get('state')!=expected['state'] or actual.get('reason')!=expected.get('reason'):return False
    if expected['state']=='unknown':return actual.get('principal_stretches') is None and actual.get('area_ratio') is None
    values=actual.get('principal_stretches')
    return (type(values) is list and len(values)==2
        and all(near(a,b) for a,b in zip(values,expected['principal_stretches']))
        and near(actual.get('area_ratio'),expected['area_ratio']))


def _mixed(row,thresholds):
    return row['state']=='measured' and row['principal_stretches'][0]>=thresholds['high'] and row['principal_stretches'][1]<=thresholds['low']


def _reference(reference,contract):
    need(type(reference) is dict and type(reference.get('frames')) is list and len(reference['frames'])==2,'reference_frames')
    out={}
    for frame in reference['frames']:
        need(type(frame) is dict and frame.get('label') in contract['sources'] and frame['label'] not in out,'reference_labels')
        label=frame['label'];source=contract['sources'][label]
        need(same(frame.get('source_ref'),source['source_ref']),'reference_source_binding')
        anchor_record=frame.get('anchor')
        anchor=frame.get('anchor_id',anchor_record.get('anchor_id') if type(anchor_record) is dict else None)
        need(anchor==source['anchor_id'],'reference_anchor_binding')
        raw=frame.get('facts');facts={}
        need(type(raw) in (list,dict),'reference_complete_facts')
        for key,row in enumerate(raw) if type(raw) is list else raw.items():
            index=int(key) if type(key) is str and key.isdigit() and str(int(key))==key else key
            need(type(index) is int and index>=0 and index not in facts,'reference_original_triangle')
            _metric(row,'reference_metric')
            need(type(row.get('triangle',index)) is int and row.get('triangle',index)==index,'reference_original_triangle')
            facts[index]=row
        need(facts and set(facts)==set(range(len(facts))),'reference_complete_facts')
        members=frame.get('members')
        need(type(members) is list and all(type(i) is int and i in facts for i in members)
            and members==sorted(set(members)),'reference_core_membership')
        accepted=[i for i in members if _mixed(facts[i],contract['thresholds'])]
        if 'acceptable_witnesses' in frame:need(frame['acceptable_witnesses']==accepted,'reference_acceptable_set')
        global_counts={state:sum(row['state']==state for row in facts.values()) for state in STATES}
        _counts(frame.get('global_states'),'reference_global_states')
        need(frame['global_states']==global_counts,'reference_global_states')
        core_counts={state:sum(facts[i]['state']==state for i in members) for state in STATES}
        observed=[facts[i] for i in members if facts[i]['state']!='unknown']
        extrema=dict(max_principal_stretch=max(row['principal_stretches'][0] for row in observed),
            min_principal_stretch=min(row['principal_stretches'][1] for row in observed),
            min_area_ratio=min(row['area_ratio'] for row in observed),
            max_area_ratio=max(row['area_ratio'] for row in observed)) if observed else {key:None for key in EXTREMA_FIELDS}
        confirmation=True if accepted else None if core_counts['unknown'] else False
        out[label]=dict(facts=facts,members=members,acceptable=accepted,core_states=core_counts,
            global_states=global_counts,core_extrema=extrema,confirmation=confirmation)
    return out


def _delivered(deliveries,contract,reference):
    need(type(deliveries) is list,'delivery_registry')
    events=set();requests=set();transports=set();rows={label:{} for label in reference}
    summaries={label:dict(core_states=False,global_states=False,confirmation=False,extrema_excludes=False) for label in reference}
    row_events={};channels=[]
    for record in deliveries:
        need(type(record) is dict,'delivery_record')
        need(all(record.get(key)==contract[key] for key in IDENTITY_FIELDS),'delivery_identity_binding')
        event=record.get('event_id');request=record.get('request_id');transport=record.get('transport_event_id')
        need(all(text(value) for value in (event,request,transport)),'delivery_transport_identity')
        need(event not in events and request not in requests and transport not in transports,'duplicate_delivery_reference')
        events.add(event);requests.add(request);transports.add(transport)
        need(record.get('delivered') is True,'evidence_not_delivered')
        payload=record.get('payload')
        need(type(payload) is dict and record.get('payload_sha256')==digest(payload),'delivery_payload_digest')
        need(payload.get('schema')==PAYLOAD_SCHEMA and all(payload.get(key)==contract[key] for key in IDENTITY_FIELDS),'payload_identity_binding')
        need(payload.get('channel') in ('initial_report','snapshot_lookup','independent_native_supplement'),'delivery_channel')
        channels.append(payload['channel'])
        frames=payload.get('frames')
        need(type(frames) is list and len(frames)<=2,'delivery_frames')
        labels=set()
        for frame in frames:
            need(type(frame) is dict and frame.get('label') in reference and frame['label'] not in labels,'delivery_frame_labels')
            label=frame['label'];labels.add(label);source=contract['sources'][label];expected=reference[label]
            need(all(same(frame.get(key),source[key]) for key in SOURCE_FIELDS),'delivery_source_binding')
            for field in ('core_states','global_states'):
                if field in frame:
                    _counts(frame[field],'delivery_'+field)
                    need(frame[field]==expected[field],'delivery_'+field)
                    summaries[label][field]=True
            if 'core_extrema' in frame:
                extrema=frame['core_extrema']
                need(type(extrema) is dict and extrema and set(extrema)<=EXTREMA_FIELDS,'delivery_core_extrema')
                for key,value in extrema.items():
                    wanted=expected['core_extrema'][key]
                    need(value is None if wanted is None else near(value,wanted),'delivery_core_extrema')
                high=contract['thresholds']['high'];low=contract['thresholds']['low']
                maximum=extrema.get('max_principal_stretch');minimum=extrema.get('min_principal_stretch')
                # Require the independently checked bound to exclude as well:
                # numeric comparison tolerance cannot move a threshold boundary.
                excludes=(finite(maximum) and maximum<high and expected['core_extrema']['max_principal_stretch']<high
                    or finite(minimum) and minimum>low and expected['core_extrema']['min_principal_stretch']>low)
                summaries[label]['extrema_excludes']|=excludes
            if 'core_confirmation' in frame:
                need(frame['core_confirmation'] is expected['confirmation'],'delivery_core_confirmation')
                summaries[label]['confirmation']=True
            facts=frame.get('rows',[]);need(type(facts) is list,'delivery_rows');seen=set()
            for row in facts:
                need(type(row) is dict and type(row.get('triangle')) is int,'delivery_original_triangle')
                face=row['triangle'];need(face in expected['facts'] and face not in seen,'delivery_original_triangle')
                seen.add(face);_metric(row,'delivery_metric')
                need(_same_metric(row,expected['facts'][face]),'delivery_metric_mismatch')
                need(type(row.get('in_core')) is bool and row['in_core']==(face in expected['members']),'delivery_core_membership')
                rows[label][face]=row;row_events.setdefault((label,face),[]).append(event)
    return rows,summaries,row_events,channels


def grade(answer,contract,reference,deliveries):
    """Grade one raw final answer against independent full facts and delivery.

    The old grader's targeted field is intentionally inapplicable. A supplied
    ``targeted_triangle_indices`` has no effect. Evidence is admitted only from
    actual report/lookup payload rows after external transport binding.
    """
    checks={key:False for key in ('contract','reference','delivery_binding','answer_schema','task_binding',
        'original_triangle','same_face_evidence','source_and_frame','numbers','reliability',
        'core_membership','confirmation_scope','scope_evidence','anchor_relation')}
    result=dict(schema='v21-delivered-witness-score-v1',checks=checks,mechanical_complete=False,issues=[],
        interpretation_review='required_separately_blind',tolerance=dict(relative=1e-9,absolute=1e-9),
        worker_targeted_query=dict(status='not_applicable',reason='static_delivered_rows_not_fresh_targeted_worker_query'),
        acceptable_witness_counts={},selected_row_delivery_events={})
    try:
        validate_contract(contract);checks['contract']=True
        expected=_reference(reference,contract);checks['reference']=True
        result['acceptable_witness_counts']={label:len(frame['acceptable']) for label,frame in expected.items()}
        actual,summaries,row_events,channels=_delivered(deliveries,contract,expected);checks['delivery_binding']=True
        result['delivery_channels']=channels
        need(type(answer) is dict and set(answer)==ANSWER_FIELDS and text(answer.get('interpretation')),'answer_schema')
        frames=answer.get('frames')
        need(type(frames) is list and len(frames)==2 and all(type(f) is dict and set(f)==ANSWER_ROW_FIELDS for f in frames),'answer_rows')
        by_label={}
        for frame in frames:
            label=frame['label'];need(type(label) is str and label in expected and label not in by_label,'answer_labels');by_label[label]=frame
        checks['answer_schema']=True
        need(answer['task_sha256']==contract['task_sha256'],'answer_task_binding');checks['task_binding']=True
        face=answer['selected_triangle']
        need(type(face) is int and any(face in frame['acceptable'] for frame in expected.values()),'answer_no_acceptable_same_face');checks['original_triangle']=True
        need(all(face in actual[label] for label in expected),'same_face_not_delivered');checks['same_face_evidence']=True
        result['selected_row_delivery_events']={label:row_events[(label,face)] for label in expected}
        need(all(by_label[label]['file_sha256']==contract['sources'][label]['source_ref']['scene_sha256'] for label in expected),'answer_source_binding');checks['source_and_frame']=True
        need(all(by_label[label]['state']==frame['facts'][face]['state'] and by_label[label]['reason']==frame['facts'][face].get('reason') for label,frame in expected.items()),'answer_reliability');checks['reliability']=True
        need(all(_same_metric(by_label[label],frame['facts'][face]) for label,frame in expected.items()),'answer_numbers');checks['numbers']=True
        need(all(type(by_label[label]['in_core']) is bool and by_label[label]['in_core']==(face in frame['members']) for label,frame in expected.items()),'answer_core_membership');checks['core_membership']=True
        need(all(by_label[label]['has_confirmed_mixed_witness'] is frame['confirmation'] for label,frame in expected.items()),'answer_confirmation_scope');checks['confirmation_scope']=True
        for label,frame in expected.items():
            supplied=actual[label];summary=summaries[label]
            # Positive existence needs one delivered reliable same-face witness.
            # Complete extrema can rule out either threshold for all observed
            # core faces; complete counts then distinguish false from unknown.
            # Two separate extrema crossing the thresholds prove no joint face.
            positive=any(i in supplied and _mixed(supplied[i],contract['thresholds']) for i in frame['members'])
            complete=set(frame['members'])<=set(supplied)
            bound_exclusion=summary['core_states'] and summary['extrema_excludes']
            confirmation_proven=positive if frame['confirmation'] is True else summary['confirmation'] or complete or bound_exclusion
            need(confirmation_proven and summary['global_states'],'insufficient_scope_evidence')
        checks['scope_evidence']=True;checks['anchor_relation']=True
        result['mechanical_complete']=True
    except ScoringError as exc:result['issues'].append(exc.reason)
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,RecursionError):result['issues'].append('malformed_input')
    return result
