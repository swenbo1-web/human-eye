"""Score actual nearest-component evidence and independently attributed follow-up work."""
import argparse
import ast
from collections import defaultdict, deque
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PREV = HERE.parent/'m4_nearest_surface_task_intent_001/score.py'
spec = importlib.util.spec_from_file_location('prior_intent_score', PREV)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
entry, nearest, intent = prior.entry, prior.nearest, prior.intent
need, read, pin = intent.need, intent.read, intent.pin
BATCH = 'M4-NEAREST-SURFACE-COMPONENT-REF-001'
ORDER = ('A1','B1','B2','A2')
SCOPE = 'one_target_vertex_connected_component_to_reference_whole_object'
PRIOR_PROMPTS = Path('M4-NEAREST-SURFACE-TASK-INTENT-001/preflight/fixture')


def shared_vertex_component(faces, winner):
    """Compute independent full index connectivity, without coordinates."""
    need(type(winner) is int and 0<=winner<len(faces),'invalid_component_seed')
    incident = defaultdict(list)
    for index,face in enumerate(faces):
        for vertex in set(face):
            incident[vertex].append(index)
    visited,vertices,queue={winner},set(),deque([winner])
    while queue:
        row=queue.popleft()
        for vertex in faces[row]:
            if vertex in vertices:
                continue
            vertices.add(vertex)
            for child in incident[vertex]:
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
    return sorted(visited)


def context_by_mesh(capture,truth,topic):
    meshes={mesh['name']:mesh for mesh in capture['meshes']}
    case=truth['cases'][topic]
    return meshes[truth['target_name']],meshes[case['reference_name']]


def canonical_size(value):
    raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return len(raw.encode('utf8'))


def wire_member_size(reply,component):
    decoder=json.JSONDecoder()
    sizes=[]
    for block in reply['result']['content']:
        if block.get('type')!='text':
            continue
        text=block['text']
        for marker in re.finditer(r'"component"\s*:\s*(?=\{)',text):
            value,length=decoder.raw_decode(text[marker.end():])
            if value==component:
                sizes.append(len(text[marker.start():marker.end()+length].encode('utf8')))
    need(len(sizes)==1,'component_member_not_unique_in_delivered_text')
    return sizes[0]


def verify_component_field(body,producer,domain,target,truth_entry):
    focus=body['facts']['focus']
    solved=focus['nearest_surface']
    component=solved.get('component')
    actual=producer['facts']['focus']
    need(solved==actual['nearest_surface'] and focus['region_ref']==actual['region_ref'],
         'public_component_or_single_face_does_not_match_producer')
    if component is None:
        return None
    need(type(component) is dict and component.get('scope')==SCOPE, 'component_scope_mislabelled')
    if component.get('status')=='unknown':
        need(set(component)=={'status','scope','reason'} and type(component['reason']) is str
             and bool(component['reason']), 'unavailable_component_publishes_unverified_reference')
        return {**component,'component_json_bytes':canonical_size(component)}
    need(set(component)=={'status','scope','region_ref','distance_m'} and component['status']=='measured'
         and solved['status']=='measured' and component['distance_m']==solved['distance_m'],
         'component_does_not_reuse_same_witness_distance')
    whole=component['region_ref']
    winner=solved['witness']['a']['source_triangle_index']
    faces=shared_vertex_component(target['faces'],winner)
    singleton=focus['region_ref']
    need(whole['schema']==singleton['schema']=='human-eye-source-region-ref-v1'
         and entry._same_current_region(whole,domain,target)
         and entry._same_current_region(singleton,domain,target)
         and whole['source_triangle_indices']==faces==truth_entry['nearest_source_triangle_indices']
         and singleton['source_triangle_indices']==[winner],
         'wrong_current_component_or_single_face_reference')
    return {'status':'measured','scope':SCOPE,'region_ref':whole,'source_rows':faces,
            'unchanged_single_face_ref':singleton,'distance_m':component['distance_m'],
            'component_json_bytes':canonical_size(component),
            'work':{k:v for k,v in producer.get('work',{}).items() if 'component' in k},
            'stages':{k:v for k,v in producer.get('stages',{}).items() if 'component' in k}}


def raw_calls(folder):
    output=[]
    for trace in intent.json_lines(folder/'wire/INDEX.jsonl'):
        if trace['method']!='tools/call':
            continue
        tx,rx=(read(intent.checked_pin(trace[side])) for side in ('tx','rx'))
        p=tx['params']
        output.append({'ordinal':trace['ordinal'],'tool':p['name'],'args':p['arguments'],'reply':rx,
                       'trace':trace,'raw':folder/'wire'/f"{trace['ordinal']:03d}",
                       'ok':'error' not in rx and rx.get('result',{}).get('isError') is False})
    return output


def valid_piece_result(call,domain,target,reference):
    if call['tool']!='human_eye_scene_observe' or call['args'].get('query',{}).get('mode')!='source_region' or not call['ok']:
        return None
    for body in nearest._body(call['reply']):
        task=body.get('task_result',{})
        region=body.get('region_ref') or task.get('region_ref')
        m=task.get('facts',{}).get('surface_proximity',{})
        r=task.get('reference',{})
        if not (region and m.get('status')=='measured' and r.get('object_id')==reference['object_id']):
            continue
        need(entry._same_current_region(region,domain,target)
             and r['instance_id']==domain['instances'][reference['object_id']],
             'followup_distance_misses_same_current_object_pair')
        return {'ordinal':call['ordinal'],'source_rows':region['source_triangle_indices'],
                'distance_m':m['value']['distance_m'],'request_ref':call['args']['query'].get('region_ref')}
    return None


def observation_for_whole_pair(call,target,reference):
    if call['tool']!='human_eye_scene_observe' or not call['ok']:
        return False
    query=call['args'].get('query',{})
    if query.get('mode')=='active_observation':
        query=query.get('task_query',{})
    objects=query.get('objects')
    return bool(query.get('mode')=='task' and 'surface_proximity' in query.get('requested_facts',[])
                and isinstance(objects,list) and len(objects)==2
                and any(all(nearest._selector_matches(selector,mesh)
                            for selector,mesh in zip(objects,ordered,strict=True))
                        for ordered in ((target,reference),(reference,target))))


def python_target_read(code,target):
    """Identify disclosed scene_data reading with literal selectors; keep dynamic uses unknown."""
    if type(code) is not str:
        return 'none'
    try:
        tree=ast.parse(code)
    except SyntaxError:
        return 'none'
    nodes=list(ast.walk(tree))
    calls=[n for n in nodes if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='scene_data']
    handled={id(n.func) for n in calls}
    possible_alias=any(isinstance(n,ast.Name) and n.id=='scene_data' and id(n) not in handled for n in nodes)
    dynamic=False
    for node in calls:
        expr=node.args[0] if node.args else next((k.value for k in node.keywords if k.arg=='objects'),None)
        if expr is None:
            return 'target'
        try:
            selectors=ast.literal_eval(expr)
        except (ValueError,SyntaxError,TypeError):
            dynamic=True
            continue
        if selectors is None or isinstance(selectors,(list,tuple)) and target in selectors:
            return 'target'
        if not isinstance(selectors,(list,tuple)):
            dynamic=True
    return 'unknown' if possible_alias or dynamic else 'none'


def target_inventory(call,target):
    if not call['ok']:
        return 'none'
    if call['tool']=='read_scene':
        for body in nearest._body(call['reply']):
            if any(all(row.get(k)==target[k] for k in ('object_id','vertices','faces')) for row in body.get('objects',[])):
                return 'target'
    elif call['tool']=='execute_python':
        return python_target_read(call['args'].get('code'),target['name'])
    return 'none'


def scope_quote_matches(quote,ref):
    """Accept an actual opaque ref, literal lists or inclusive source-row ranges."""
    if type(quote) is not str or not quote:
        return False
    ident=re.escape(ref['region_id'])
    if re.search(r'(?<![\w:])'+ident+r'(?![\w:])',quote):
        return True
    if not re.search(r'三角|源面|连通片|片范围|面片索引|面编号|source[_ -]?(?:triangle|row|face)|triangles?|face rows|component',quote,re.I):
        return False
    scope=ref['source_triangle_indices']
    found=[]
    tokens=re.findall(r'(?<![\d.])\d+(?:\s*(?:-|–|—|~|～|至|到|…|\.\.)\s*\d+)?(?![\d.])',quote)
    for token in tokens:
        nums=list(map(int,re.findall(r'\d+',token)))
        if len(nums)==2:
            if nums[1]<nums[0] or nums[1]-nums[0]>=4096:
                return False
            found.extend(range(nums[0],nums[1]+1))
        else:
            found.extend(nums)
    return bool(found) and sorted(set(found))==scope


def component_uptake(final,claim,measured,reads,possible_reads,scopes,base):
    checked=[]
    proof=claim.get('component_use') if isinstance(claim,dict) else None
    for component in measured:
        ref=component['region_ref']
        ordinal=component['ordinal']
        opaque=re.search(r'(?<![\w:])'+re.escape(ref['region_id'])+r'(?![\w:])',final)
        quote=proof.get('quote') if isinstance(proof,dict) and proof.get('ordinal')==ordinal else None
        final_mentions=bool(opaque or isinstance(quote,str) and quote in final and scope_quote_matches(quote,ref))
        prior_read=sorted([r['ordinal'] for r in reads+possible_reads])
        duplicate_scope=sorted(p['ordinal'] for p in scopes if p['source_rows']==component['source_rows']
                               and not (p['ordinal']>ordinal and p['request_ref']==ref))
        used_in_request=sorted(p['ordinal'] for p in scopes if p['ordinal']>ordinal and p['request_ref']==ref)
        unique=bool(final_mentions and base.get('answer',{}).get('selected_correct_piece')
                    and not prior_read and not duplicate_scope)
        checked.append({'delivery_ordinal':ordinal,'final_exact_opaque_ref':bool(opaque),
                        'final_scope_quote_verified':bool(final_mentions),'used_exact_ref_as_query':used_in_request,
                        'possible_alternative_full_mesh_read':prior_read,
                        'same_scope_available_from_other_query':duplicate_scope,'unique_final_scope_adoption':unique})
    return checked


def group_work(folder,capture,truth,topic,domain,base,calls,distances,readings,claim,arm):
    target,reference=context_by_mesh(capture,truth,topic)
    case=truth['cases'][topic]
    near=set(case['nearest_source_triangle_indices'])
    near_i=truth['target_components'].index(case['nearest_source_triangle_indices'])
    distance=math.sqrt(float(Fraction(case['distances_squared_m2'][near_i])))
    verified_routes={r['ordinal']:r for r in base['nearest_surface_routes'] if r['verified_nearest']}
    components,scopes,reads,ambiguous,followups,far,first_global=[],[],[],[],[],[],None
    near_before_product,possible_pair_repeat=[],[]
    directory,readbacks,other=[],[],[]
    for call in calls:
        at=call['ordinal']
        cost=prior._cost(folder,call['trace'])
        inventory=target_inventory(call,target)
        query=call['args'].get('query',{})
        observation=(call['tool']=='human_eye_scene_observe' and query.get('mode')=='directory')
        if observation:
            directory.append(cost)
        elif call['tool']=='read_images':
            readbacks.append(cost)
        elif inventory=='target':
            reads.append({**cost,'after_known_component':any(c['status']=='measured' for c in components),
                          'after_global_nearest':first_global is not None})
        elif inventory=='unknown':
            ambiguous.append(cost)
        if at in verified_routes:
            body=next(b for b in nearest._body(call['reply']) if b.get('facts',{}).get('focus',{}).get('nearest_surface'))
            received=verify_component_field(body,read(call['raw']/'PRODUCER.json'),domain,target,case)
            if received is not None:
                need(arm=='B','unexpected_candidate_component_on_fixed_A')
                rendered=wire_member_size(call['reply'],body['facts']['focus']['nearest_surface']['component'])
                components.append({**received,'ordinal':at,'rx':call['trace']['rx'],
                                   'wire_component_member_utf8_bytes':rendered,'total_body_bytes':cost['text_bytes']})
            if first_global is None:
                first_global=at
            elif entry._matches_value(verified_routes[at]['witness']['distance_m'],distance):
                followups.append({**cost,'kind':'global_pair_repeat','source_rows':None,
                                 'distance_m':verified_routes[at]['witness']['distance_m']})
            continue
        piece=valid_piece_result(call,domain,target,reference)
        if piece is None:
            if first_global is not None and observation_for_whole_pair(call,target,reference):
                possible_pair_repeat.append({**cost,'kind':'additional_whole_target_reference_measurement_request'})
            # Ordinary computation is not a new geometry scope unless its
            # actual answer and value are bound. Preserve unattributed reads.
            if not observation and call['tool']!='read_images' and inventory=='none':
                other.append({**cost,'tool':call['tool'],'mode':query.get('mode'),'isError':not call['ok']})
            continue
        scopes.append(piece)
        rows=set(piece['source_rows'])
        if rows and rows<=near and entry._matches_value(piece['distance_m'],distance):
            if first_global is None:
                near_before_product.append({**cost,**piece,'kind':'near_measurement_before_global_route'})
            else:
                known=any(component['status']=='measured' and component['ordinal']<at
                           and rows==set(component['source_rows']) for component in components)
                kind='near_same_component_scope' if known else 'near_new_scope_same_distance'
                followups.append({**cost,**piece,'kind':kind})
        elif rows==set(truth['target_components'][1-near_i]) and entry._matches_value(
                piece['distance_m'],math.sqrt(float(Fraction(case['distances_squared_m2'][1-near_i])))):
            far.append({**cost,**piece,'kind':'far_component_measurement'})
        else:
            other.append({**cost,**piece,'tool':call['tool'],'mode':query.get('mode')})
    # Existing answer scoring independently validates annotated ordinary
    # computation. Separate evidence and follow-up attribution from estimates.
    costs={call['ordinal']:prior._cost(folder,call['trace']) for call in calls}
    if not far:
        for row in distances:
            if (row['component']!=near_i and row['status']=='passed'
                    and row.get('kind') in ('ordinary_calculation','ordinary_source_geometry')):
                far.append({**costs[row['source_ordinal']],'kind':row['kind'],
                            'scope':'far_component_original_answer_confirmation'})
    for row in distances:
        if (first_global is not None and row['component']==near_i and row['status']=='passed'
                and row.get('kind')=='ordinary_calculation' and row['source_ordinal']>first_global):
            followups.append({**costs[row['source_ordinal']],'kind':'ordinary_near_distance_recomputed'})
    final=(folder/'consumer/final.txt').read_text(encoding='utf8')
    measured=[c for c in components if c['status']=='measured']
    uptake=component_uptake(final,claim,measured,reads,ambiguous,scopes,base)
    return {'first_tool':{'ordinal':calls[0]['ordinal'],'tool':calls[0]['tool']} if calls else None,
            'first_geometry_localization':base['first_geometry_localization'],
            'first_global_nearest':first_global,'component_deliveries':components,'component_uptake':uptake,
            'full_target_mesh_reads':reads,'unresolved_possible_target_mesh_reads':ambiguous,
            'near_distance_followups':sorted(followups,key=lambda x:x['ordinal']),
            'near_measurements_before_product':near_before_product,'possible_whole_pair_repeats':possible_pair_repeat,
            'far_first_measurement':far[0] if far else None,'all_far_measurements':far,
            'directories':directory,'read_images':readbacks,'other_calls':other,
            'repeat_image_delivery_count':sum(max(0,len(r['delivery_ordinals'])-1) for r in base['images']),
            'additional_rasters_after_first':max(0,base['actual_rasters']-1),
            'all_business_costs':list(costs.values()),
            'distance_packets':readings}


def slot_score(folder,frozen,geometry,truth,slot,claim):
    topic='K' if slot[-1]=='1' else 'T'
    base=nearest.score_case(folder,prior.scoped_prompts(frozen,slot,topic),geometry,truth,topic,claim)
    if base['status']!='observed':
        return base
    capture=read(folder/'post_capture.json')
    domain=intent.bind_geometry(capture,geometry)
    readings,ordinary=entry.distance_packets(folder,base,geometry,truth,topic)
    distances=entry.score_distances(folder,claim or {},truth,topic,readings,ordinary)
    physical=base['first_actual_raster']
    common=bool(base['quality_passed'] and physical and physical['true_piece_visible'] and base['same_first_frame_in_final'])
    quality=prior.passes_requirements('A' if topic=='K' else 'B',common,distances)
    work=group_work(folder,capture,truth,topic,domain,base,raw_calls(folder),distances,readings,claim,slot[0])
    from_nearest=bool(physical and physical['origin']=='product'
                      and any(r['verified_nearest'] and physical['ordinal']==r['ordinal']
                              for r in base['nearest_surface_routes']))
    used=[r for r in base['nearest_surface_routes'] if r['verified_nearest']]
    early=any(r['before_geometry_localization'] for r in used)
    return {**base,'topic':topic,'distances_required':topic=='T','quality_passed':quality,
            'single_image_common_quality':common,'piece_gap_reports':distances,
            'voluntary_K_gap_count':sum(row['status']=='passed' for row in distances) if topic=='K' else None,
            'late_nearest_adoption':bool(used and not early),'product_nearest_first_raster':from_nearest,
            'component_measured_delivered':any(x['status']=='measured' for x in work['component_deliveries']),
            'unique_final_component_scope_adoption':any(x['unique_final_scope_adoption'] for x in work['component_uptake']),
            'mechanism_passed':bool(base['mechanism_passed'] and quality),
            'attribution':work,'payload':entry.actual_payload(folder)}


def paired(cases):
    details={}
    for i,topic in ((1,'K'),(2,'T')):
        a,b=(cases[f'{arm}{i}'] for arm in 'AB')
        observed=a['status']==b['status']=='observed'
        b_valid=bool(observed and b.get('quality_passed') and b.get('product_nearest_first_raster'))
        quality_comparable=bool(observed and a.get('quality_passed') and b.get('quality_passed'))
        actual={}
        for arm,row in (('A',a),('B',b)):
            if row['status']=='observed':
                at=row['attribution']
                actual[arm]={'target_mesh_reads':len(at['full_target_mesh_reads']),
                             'unknown_target_reads':len(at['unresolved_possible_target_mesh_reads']),
                             'near_repeat_calls':len(at['near_distance_followups']),
                             'near_measurements_before_product':len(at['near_measurements_before_product']),
                             'possible_whole_pair_repeats':len(at['possible_whole_pair_repeats']),
                             'far_proof':bool(at['far_first_measurement'])}
        aa,bb=actual.get('A'),actual.get('B')
        both_baseline=bool(aa and aa['target_mesh_reads'] and aa['near_repeat_calls'])
        b_avoids=bool(bb and not any(bb[key] for key in (
            'target_mesh_reads','unknown_target_reads','near_repeat_calls',
            'near_measurements_before_product','possible_whole_pair_repeats')))
        details[topic]={'observed_pair':observed,'quality_comparable':quality_comparable,
                        'B_used_product_first_image_and_complete_quality':b_valid,
                        'case_counts':actual,'A_baseline_had_both':both_baseline,'B_has_neither':b_avoids,
                        'B_avoids_both_vs_A':bool(b_valid and both_baseline and b_avoids),
                        'B_avoids_both_and_received_component':bool(
                            b_valid and both_baseline and b_avoids and b.get('component_measured_delivered')),
                        'measured_component_delivered':b.get('component_measured_delivered',False),
                        'unique_final_scope_adoption':b.get('unique_final_component_scope_adoption',False),
                        'target_mesh_read_reduction':aa['target_mesh_reads']-bb['target_mesh_reads'] if observed else None,
                        'near_repeat_reduction':aa['near_repeat_calls']-bb['near_repeat_calls'] if observed else None}
    return details


def evaluate(root,annotations):
    frozen=read(root/'preflight/FROZEN_EXECUTION.json')
    need(frozen['batch']==BATCH and frozen['order']==list(ORDER),'wrong_frozen_component_batch')
    fixture=frozen['fixture']
    geometry,truth=[read(intent.checked_pin(fixture[k])) for k in ('source','truth')]
    need(fixture['blend']['sha256']==geometry['asset_sha256']==truth['asset_sha256']
         and fixture['source']['sha256']==truth['evaluated_source_sha256'],'fixture_or_truth_pin_changed')
    for i in (1,2):
        a,b=(intent.checked_pin(fixture['prompts'][f'{arm}{i}']) for arm in 'AB')
        original=root.parent/PRIOR_PROMPTS/('PROMPT_A_K.txt' if i==1 else 'PROMPT_B_T.txt')
        need(a.read_bytes()==b.read_bytes()==original.read_bytes(),'same_topic_A_B_prompt_bytes_changed')
    cases={}
    for slot in ORDER:
        try:
            cases[slot]=slot_score(root/'slots'/slot,frozen,geometry,truth,slot,annotations.get(slot))
        except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
            cases[slot]={'status':'unverified','reason':str(error)}
    pairs=paired(cases)
    counts={}
    for arm in 'AB':
        rows=[cases[arm+str(i)] for i in (1,2)]
        counts[arm]={'registered':2,'observed':sum(r['status']=='observed' for r in rows),
                     'unrun':sum(r['status']=='unrun' for r in rows)}
        labels={'quality':'quality_passed','early':'route_first_nearest','late':'late_nearest_adoption',
                'any':'nearest_surface_adopted','component_delivered':'component_measured_delivered',
                'unique_component_use':'unique_final_component_scope_adoption','mechanism':'mechanism_passed',
                'first_image_in_final':'same_first_frame_in_final'}
        counts[arm].update({key:sum(r.get(field) is True for r in rows) for key,field in labels.items()})
    eligible=sum(r['B_used_product_first_image_and_complete_quality'] for r in pairs.values())
    passed=sum(r['B_avoids_both_vs_A'] for r in pairs.values())
    return {'batch':BATCH,'cases':cases,'paired':pairs,'counts':counts,
            'B_avoids_target_enumeration_and_near_repeat':{'numerator':passed,'eligible_pairs':eligible,'planned_pairs':2},
            'full_benefit_passed':bool(passed==eligible==2 and all(r['quality_comparable'] and
                r['measured_component_delivered'] for r in pairs.values()))}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=lambda x:Path(x).resolve(strict=True))
    parser.add_argument('annotation',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    intent.save(args.output,evaluate(args.root,read(args.annotation)))
