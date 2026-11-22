"""Trace whole-object source triangle adoption from actual CLI events and owned captures."""

import argparse
from fractions import Fraction
from functools import lru_cache
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUNTIME = Path('D:/he_m3_whole_object_witness_triangle_consumption_001')
LABELS = ('A1','B1')
TARGET = 'M16'
REFERENCES = ('M19','M14')
TOOL = 'human_eye_scene_observe'
FACT = 'surface_proximity'
SOURCE = {'A1':'338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac',
          'B1':'d39b0da9913dc31f55944a10b0299c15acc265a2d4d33d77a39e4798c65cb8c7'}
BINDINGS = {
    'A1': V/'m1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json',
    'B1': V/'m3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json',
}
ERRORS = (OSError, ValueError, AssertionError, KeyError, TypeError, AttributeError, IndexError, ArithmeticError, StopIteration)
ORDINARY = {'setup_only','other_relevant_work','new_required_evidence','repeat_same_evidence',
            'independent_membership_verification_same_fact','standalone_new_source_membership',
            'recomputation_with_new_evidence','unrelated_work'}


def read(path, default=None):
    return json.loads(path.read_bytes()) if path.is_file() else default


def lines(path):
    return [json.loads(raw) for raw in path.read_bytes().splitlines() if raw] if path.is_file() else []


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def previous():
    old = run_path(str(V/'m1_source_region_no_image_measurement_consumption_001/checks/consumption_trace.py'))
    m1 = run_path(str(V/'m1_source_region_no_image_native_transfer_001/checks/consumption_trace.py'))
    product = run_path(str(V/'m3_whole_object_witness_triangle_001/checks/delivery.py'))
    costs = run_path(str(V/'perf050_readonly_product_pilot_001/consumer/costs.py'))
    return old,m1,product,costs


def reconcile_slot_sources(slot, result, required_names):
    old,_,_,_ = previous()
    first, last = [json.loads(old['checked'](old['inside'](slot, result[key]['path']),result[key]['sha256']))
                   for key in ('initial_source','terminal_source')]
    require(result['asset_sha256'] == last['source']['asset_sha256'] == old['ASSET']
            and first['source'] == last['source'] and first['objects'] == last['objects']
            and len(last['objects']) == 21 and len({row['name'] for row in last['objects']}) == 21,
            'closed_current_asset_or_geometry_changed')
    objects = {row['name']:row for row in last['objects']}
    require(set(required_names) <= objects.keys(), 'ordered_current_objects_missing_from_terminal_readback')
    return last,objects


def requested_pair(arguments, objects, target=TARGET, references=REFERENCES):
    if not isinstance(arguments, dict):
        return None
    old,_,_,_ = previous()
    named = old['selected_name']
    outer = arguments.get('query')
    if not isinstance(outer,dict):
        return None
    mode = outer.get('mode')
    query = outer.get('task_query') if mode == 'active_observation' else outer
    if not isinstance(query, dict) or FACT not in (query.get('requested_facts') or ()):
        return None
    full_rows = False
    if mode == 'source_region':
        region, ref = query.get('region'),query.get('region_ref')
        if isinstance(region,dict):
            name = named(region.get('object'),objects)
            indices = region.get('source_triangle_indices')
        elif isinstance(ref,dict):
            name = next((name for name,row in objects.items() if (row['object_id'],row['instance_id'])
                         == (ref.get('host_id'),ref.get('instance_id'))),None)
            indices = ref.get('source_triangle_indices')
        else:
            return None
        order = [name,named(query.get('reference'),objects)]
        full_rows = (name in objects and type(indices) is list and all(type(i) is int for i in indices)
                     and sorted(indices) == list(range(len(objects[name]['evaluated']['triangles']))))
    elif mode in ('task','active_observation') and isinstance(query.get('objects'),list):
        order = [named(item,objects) for item in query['objects']]
    else:
        return None
    if len(order)!=2 or target not in order:
        return None
    reference = order[1] if order[0]==target else order[0]
    if reference not in references:
        return None
    return {'reference':reference,'order':order,'mode':mode,'same_whole_scope':mode!='source_region' or full_rows,
            'ordinary_whole_entry':mode=='task','explicit_no_image':arguments.get('include_image') is False,
            'requested_detail':arguments.get('response_detail','omitted'),'sole_surface_fact':query['requested_facts']==[FACT]}


def exact_public(row, item):
    if item is None or item.get('tool')!=row['tool'] or item.get('error') is not None or row['stdio_RX'] is None:
        return None
    reply = json.loads(Path(row['stdio_RX']['path']).read_bytes())
    result = reply.get('result') or {}
    public = result.get('content')
    if (result.get('isError') is not False or not isinstance(public,list) or len(public)!=1
            or public[0]['type']!='text' or (item.get('result') or {}).get('content')!=public
            or item.get('arguments')!=row['arguments']):
        return None
    return json.loads(public[0]['text'])


def oriented(body, scope, *, target=TARGET):
    output = body if scope['mode']=='task' else body['task_result']
    metric = output['facts'][FACT]
    if metric['status']!='measured':
        return None
    value = metric['value']
    point = value['nearest_witness']
    primary = point.get('source_triangles')
    mapping = output.get('source_mapping',{}).get('nearest_witness',{})
    if primary:
        faces = {k:[primary[k]['source_triangle_index']] for k in ('a','b')}
    else:
        faces = {k:mapping.get(k,{}).get('source_triangle_indices',[]) for k in ('a','b')}
    normal = scope['order'][0]==target
    return {'metres':value['distance_m'],'direction':point['direction_a_to_b'] if normal else
            [-x for x in point['direction_a_to_b']],
            'point_a':point['a' if normal else 'b'],'point_b':point['b' if normal else 'a'],
            'membership':faces if normal else {'a':faces['b'],'b':faces['a']},
            'new_whole_source_present':primary is not None}


def account_active_costs(ledger):
    old,_,_,_ = previous()
    result = old['totals'](ledger)
    a,b = result['CLI_input_plus_output_tokens'],result['CLI_cached_input_tokens']
    result['CLI_uncached_input_plus_output_tokens'] = a-b if type(a) is int and type(b) is int \
        and 0<=b<=result['CLI_input_tokens'] else None
    result['CLI_uncached_input_tokens'] = result['CLI_uncached_input_plus_output_tokens']-result['CLI_output_tokens'] \
        if result['CLI_uncached_input_plus_output_tokens'] is not None else None
    return result


def audit_work(slot):
    rows = lines(slot/'product_audit.jsonl')
    calls = {e['trace']['annotations'].get('mcp_request_id'):e['trace']['trace_id']
             for e in rows if e.get('event')=='request_trace'}
    work = {e['trace_id']:e['task_work'] for e in rows
            if e.get('event')=='observe' and 'trace_id' in e and 'task_work' in e}
    return calls,work


def trace_attempt(slot,row,item,objects,terminal,source_binding,proof_work, *, target=TARGET,references=REFERENCES):
    old,_,engineering,_ = previous()
    ask = requested_pair(row['arguments'],objects,target,references) if row['tool']==TOOL else None
    proof = {'attempt':row['attempt'],'tool':row['tool'],'requested_pair':ask,
             'classification':'other_successful_tool_delivery','accepted_CLI_result':item is not None,
             'outer_TX':row['stdio_TX'],'outer_RX':row['stdio_RX'],'tool_wire_text_bytes':row['wire_content']['text_bytes'],
             'tool_wire_RTT_ms':row['tool_wire_RTT_ms'],'dispatch_to_CLI_ms':row['dispatch_to_CLI_result_ms']}
    if row['stdio_RX'] is None:
        return {**proof,'classification':'no_returned_tool_evidence'}
    if row['wire_content']['error']:
        return {**proof,'classification':'original_tool_or_protocol_rejection'}
    if row['tool'] in ('execute_python','execute_blender_code'):
        return {**proof,'classification':'ordinary_read_or_calculation_content_review_required'}
    if ask is None or row['product'] is None:
        return proof
    tx,rx = (json.loads(old['checked'](old['inside'](slot,row[key]['path']),row[key]['sha256']))
             for key in ('stdio_TX','stdio_RX'))
    inner, producer = old['checked_product'](slot,tx,rx,row['product'])
    proof['inner'] = inner
    proof['inner_product_stages_ms'] = row['product']['request_trace_duration_ms']
    proof['service_stage_ms'] = row['product']['service_stage_ms']
    req = read(Path(row['product']['request_file']['path']))
    ids,works = proof_work
    proof['task_work'] = works.get(ids.get(req['id']))
    body = exact_public(row,item)
    if body is None:
        return {**proof,'classification':'current_pair_known_but_public_CLI_content_not_exact'}
    fact = oriented(body,ask,target=target)
    if fact is None:
        return {**proof,'classification':'current_pair_measurement_unknown'}
    proof['fact'] = fact
    require(producer is not None,'successful_pair_reply_missing_original_producer')
    actual = body if ask['ordinary_whole_entry'] else body['task_result']
    raw = producer if ask['ordinary_whole_entry'] else producer['task_result']
    require(actual['facts'][FACT]==raw['facts'][FACT],'delivered_metric_changed_from_original_producer')
    if ask['ordinary_whole_entry'] or ask['mode']=='source_region':
        dependency = source_binding['dependency_root']
        if dependency not in sys.path:
            sys.path.append(dependency)
        envelope, = [x for x in lines(slot/'PUBLIC_REQUESTS.jsonl') if x['request']['id']==req['id']]
        sequence,capture = engineering['H']['slot_capture'](slot,source_binding,{**envelope,'producer':producer},
                                                            lambda path:old['inside'](slot,path).read_bytes())
        whole = ask['ordinary_whole_entry']
        names = ask['order'] if whole else objects.keys()
        original = engineering['E']['prove_capture'](capture,terminal,names,
            revision=producer['binding']['scene_revision'],scope='selected_objects' if whole else 'complete_scene_meshes',
            generation=capture['capture_state'],
            epoch=capture['host_identity']['document_epoch'])
        proof['source_capture']={'sequence':sequence,'authority':original,
             'TX':previous()[3]['file_receipt'](slot/'native/WIRE'/f'{sequence:03d}'/'REQUEST.bin'),
             'RX':previous()[3]['file_receipt'](slot/'native/WIRE'/f'{sequence:03d}'/'RESPONSE.bin')}
        if whole and fact['new_whole_source_present']:
            proof['current_triangle_source'] = engineering['verify_witness'](capture,body,expected_names=ask['order'])
    if ask['mode']=='source_region':
        expected = objects[ask['order'][0]]
        current = body['region_ref']
        require(current==producer['region_ref'] and current['host_id']==expected['object_id']
                and current['instance_id']==expected['instance_id']
                and body['task_result']['source_mapping']['nearest_witness']==
                    producer['task_result']['source_mapping']['nearest_witness'],'source_region_supplement_wrong_current_scope')
        for side,name in zip(('a','b'),ask['order'],strict=True):
            nearest = actual['facts'][FACT]['value']['nearest_witness'][side]
            membership = actual['source_mapping']['nearest_witness'][side]
            mesh = objects[name]['evaluated']
            ids = membership['source_triangle_indices']
            oracle = engineering['T']
            if ids:
                independent = oracle['member'](oracle['vector'](nearest),(
                    tuple(oracle['vector'](x) for x in mesh['vertices_world_m']),
                    tuple(tuple(x) for x in mesh['triangles']),tuple(ids)))
                require(membership['exact_membership'] is True and independent['exact_source_triangle_indices']==ids,
                        'supplement_claimed_source_not_on_current_triangle/'+side)
    return {**proof,'classification':'bound_whole_measurement' if ask['same_whole_scope']
            else 'bound_narrow_scope_measurement'}


def fits_scored_points(score, reference, metric, *, require_source):
    _,m1,_,_ = previous()
    rows=score['checks']
    actual=rows[f'{reference}_actual_point_pair_and_triangle_membership']['verified']
    grade=rows[f'{reference}_distance_and_world_direction']['verified']
    close=m1['close_vector']
    if not (isclose(float(Fraction(str(grade['metres']))),metric['metres'],rel_tol=0,abs_tol=5e-5)
            and close(grade['direction_a_to_b'],metric['direction'])
            and close(actual['point_a'],metric['point_a']) and close(actual['point_b'],metric['point_b'])):
        return False
    if not require_source:
        return True
    return all(set(actual['stated_source_triangle_indices'][side]) & set(metric['membership'][side])
               for side in ('a','b'))


def same_metric(a,b):
    keys=('metres','direction','point_a','point_b')
    return all(a[key]==b[key] for key in keys)


def pair_report(trace, reference, score, quality_passed, ordinary, answer, *, qualifying_candidate):
    recognized = [row for row in trace if (row.get('requested_pair') or {}).get('reference')==reference
                  and row['classification'] in ('bound_whole_measurement','bound_narrow_scope_measurement')]
    first = next((row for row in recognized if row['classification']=='bound_whole_measurement'),None)
    ordinary_whole = next((row for row in recognized if row['classification']=='bound_whole_measurement'
                           and row['requested_pair']['ordinary_whole_entry']),None)
    seen = []
    supplemental, repeated, new = [],[],[]
    for row in recognized:
        metric = row['fact']
        peers=[peer for peer in seen if same_metric(peer['fact'],metric)]
        known = {side:{f for peer in peers for f in peer['fact']['membership'][side]} for side in ('a','b')}
        # An extra true incident face is additional provenance even if one row
        # was already enough for the task. Keep it separate from required work.
        novelty = {side:sorted(set(metric['membership'][side])-known[side]) for side in ('a','b')}
        required = any(metric['membership'][side] and not known[side] for side in ('a','b'))
        if peers and any(novelty.values()):
            supplemental.append({'attempt':row['attempt'],'follows':peers[0]['attempt'],'new_faces':novelty,
                                 'needed_for_original_requested_source_membership':required})
        elif peers:
            repeated.append(row['attempt'])
        else:
            new.append(row['attempt'])
        seen.append(row)
    adopted = bool(qualifying_candidate and quality_passed and first is not None and first is ordinary_whole
                   and first.get('current_triangle_source') and first['requested_pair']['explicit_no_image']
                   and fits_scored_points(score,reference,first['fact'],require_source=True))
    quote = None
    if adopted:
        quote=score['checks'][f'{reference}_actual_point_pair_and_triangle_membership']['verified']['point_pair_quote']
        require(isinstance(quote,str) and bool(quote.strip()) and quote in answer,
                'first_packet_adoption_claim_not_bound_to_original_answer_quote')
    ordinary_membership = [row for row in ordinary if reference in row.get('pairs',[]) and row['classification'] in
                           ('standalone_new_source_membership','independent_membership_verification_same_fact')]
    return {'first_whole_attempt':None if first is None else first['attempt'],
            'whole_observe_attempt':None if ordinary_whole is None else ordinary_whole['attempt'],
            'first_whole_has_verified_source':bool(first and first.get('current_triangle_source')),
            'candidate_first_whole_adopted':adopted,'verified_answer_point_source_quote':quote,
            'whole_first_packet_text_bytes':None if first is None else first['tool_wire_text_bytes'],
            'product_attempts_known':[row['attempt'] for row in recognized],
            'same_measurement_nonincremental_repeats':repeated,'new_metric_or_point_attempts':new,
            'same_metric_with_new_source':supplemental,'ordinary_membership':ordinary_membership,
            'required_source_followups':sorted({row['attempt'] for row in supplemental
                if row['needed_for_original_requested_source_membership']} |
                {row['attempt'] for row in ordinary_membership if row['classification']=='standalone_new_source_membership'})}


def ordinary_review(trace,by_attempt,annotations,references):
    _,m1,_,_ = previous()
    expected={row['attempt'] for row in trace if row['classification']=='ordinary_read_or_calculation_content_review_required'}
    seen=set()
    verified=[]
    for note in annotations.get('ordinary',[]):
        step=note['attempt']
        excerpt=note['result_excerpt']
        item=(by_attempt.get(step) or {}).get('result')
        require(step in expected-seen and note['classification'] in ORDINARY
            and set(note.get('pairs',[])) <= set(references) and isinstance(excerpt,str) and excerpt.strip()
            and any(excerpt in s for s in m1['strings'](item)) and bool(note['reason']),
            'ordinary_membership_or_repeat_review_not_bound_to_actual_attempt/'+str(step))
        seen.add(step)
        verified.append(note)
    return {'verified':verified,'unreviewed':sorted(expected-seen)}


def summarize_slot(slot,token,prompt,score,annotations, *, target=TARGET,references=REFERENCES,source_binding=None):
    _,m1,_,cost = previous()
    try:
        ledger=cost['summarize'](slot,token)
    except ERRORS as exc:
        start=read(slot/'SLOT_RESULT.json',read(slot/'SLOT_STARTED.json',{}))
        return {'label':slot.name,'status':'unverifiable','model_consumers_launched':start.get('model_consumers',0),
                'formal_slot_created':slot.is_dir(),'verification_errors':[str(exc)]}
    ledger['formal_slot_created']=slot.is_dir()
    if not ledger['formal_slot_created']:
        return ledger
    ledger['totals']=account_active_costs(ledger)
    ledger['quality']=m1['quality_identity'](ledger,score)
    errors=ledger['verification_errors']=[]
    ledger['trace']=[]
    ledger['pairs']={}
    source=read(slot/'SLOT_RESULT.json',{})
    if source.get('status')!='completed':
        return ledger
    try:
        require(ledger['initial_prompt_sha256']==prompt and source.get('closure_verification',{}).get('passed')
                and source.get('independent_before_after',{}).get('passed')
                and ledger['thread_id'] and ledger['model_consumers_launched']==1,
                'completed_formal_slot_failed_prompt_read_only_close_or_fresh_model_binding')
        cfg=ledger['requested_consumer_configuration']
        require((cfg['requested_model'],cfg['requested_effort'],cfg['requested_service_tier'])
                ==('gpt-6.1-sol','medium','default') and any(part.startswith('0.152.1-') for part in
                Path(cfg['requested_cli_overrides_and_argv'][0]).parts),'formal_requested_model_or_CLI_changed')
        binding=read(BINDINGS[slot.name]) if source_binding is None else source_binding
        require(source['product_source_sha256']==binding['source_sha256'],'formal_product_source_changed')
        pub=read(slot/'SLOT_PUBLICATION.json')
        require(pub['owned_budget_passed'] is True and pub['complete_slot_ns']/1e6==ledger['totals']['complete_slot_ms'],
                'formal_owned_wall_clock_or_budget_changed')
        terminal,objects=reconcile_slot_sources(slot,source,[target,*references])
        events=m1['event_bindings'](slot)
        proof_work=audit_work(slot)
        for row in ledger['actual_requests']:
            try:
                ledger['trace'].append(trace_attempt(slot,row,events.get(row['attempt']),objects,terminal,binding,proof_work,
                                                     target=target,references=references))
            except ERRORS as exc:
                errors.append(f'actual_tool_{row["attempt"]}: {exc}')
        review=ordinary_review(ledger['trace'],events,annotations,references)
        ledger['ordinary_review']=review
        answer=Path(ledger['answer_file']['path']).read_bytes().decode('utf-8')
        for ref in references:
            ledger['pairs'][ref]=pair_report(ledger['trace'],ref,score,ledger['quality']['passed'],review['verified'],answer,
                                             qualifying_candidate=slot.name=='B1')
    except ERRORS as exc:
        errors.append(str(exc))
    return ledger


def analyze(root=RUNTIME, *, freeze_path=None, quality=None, judgments=None):
    root=Path(root)
    freeze=NS/'FROZEN.json' if freeze_path is None else Path(freeze_path)
    token=digest(freeze.read_bytes()) if freeze.is_file() else None
    frozen=read(freeze,{})
    prompt=digest((NS/'inputs/PROMPT.txt').read_bytes())
    observed_prompt=frozen.get('prompt_sha256')
    slots={label:summarize_slot((root/'slots'/label).resolve(),token,prompt,(quality or {}).get(label),
                                (judgments or {}).get(label,{})) for label in LABELS}
    a,b=(slots[label] for label in LABELS)
    completed=bool(token and prompt==observed_prompt and
                   all(r['status']=='completed' and r['cost_evidence_verified'] and not r['verification_errors']
                       for r in slots.values()))
    completed=completed and a['thread_id']!=b['thread_id']
    equal=completed and a['quality']['passed'] and b['quality']['passed'] and a['quality']['score']==b['quality']['score']
    pairs={}
    for ref in REFERENCES:
        left,right=(r.get('pairs',{}).get(ref,{}) for r in (a,b))
        countable=equal and right.get('candidate_first_whole_adopted') and left.get('whole_observe_attempt') is not None
        review_complete=not any(r.get('ordinary_review',{}).get('unreviewed') for r in (a,b))
        pairs[ref]={'baseline':left,'candidate':right,'comparable_quality_and_first_candidate_uptake':bool(countable),
                    'standalone_source_saving_comparable':bool(countable and review_complete and left['required_source_followups']),
                    'required_source_followups_A_minus_B':len(left['required_source_followups'])-
                    len(right['required_source_followups']) if countable and review_complete else None}
    x,y=a.get('totals',{}),b.get('totals',{})
    return {'schema':'m3-whole-object-witness-triangle-actual-consumption-v1','freeze_sha256':token,
            'same_frozen_shape_prompt_and_closed_equal_quality':bool(equal),'slots':slots,'pairs':pairs,
            'denominator':{'planned_formal':2,'created':sum(r['formal_slot_created'] for r in slots.values()),
                           'completed':sum(r['status']=='completed' for r in slots.values()),
                           'failed_or_unconfirmed':sum(r['status'] not in ('completed','unrun') for r in slots.values()),
                           'unrun':sum(r['status']=='unrun' for r in slots.values()),
                           'observed_CLI_launches':sum(r['model_consumers_launched'] for r in slots.values()),
                           'candidate_first_packet_adopted_pairs_of_2':sum(
                               cell['candidate'].get('candidate_first_whole_adopted') is True for cell in pairs.values())},
            'observed_cost_deltas_B_minus_A':{key:y[key]-x[key] for key in x.keys()&y.keys()
                                             if type(x[key]) in (int,float) and type(y[key]) in (int,float)},
            'actual_provider_timing':None,'actual_provider_billing':None}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root',type=Path,default=RUNTIME)
    cli.add_argument('--freeze',type=Path)
    cli.add_argument('--quality',type=Path)
    cli.add_argument('--judgments',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    args=cli.parse_args()
    report=analyze(args.root,freeze_path=args.freeze,quality=read(args.quality) if args.quality else None,
                   judgments=read(args.judgments) if args.judgments else None)
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2,sort_keys=True)
        stream.write('\n')
