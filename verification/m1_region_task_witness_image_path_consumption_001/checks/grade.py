"""Grade the original answer and current, model-visible Blender evidence."""

import argparse
from fractions import Fraction as F
from math import sqrt
import json
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import unquote
from runpy import run_path


HERE = Path(__file__).resolve().parent
E = run_path(str(HERE/'evidence.py'))
NS, V, DENSE = (E[name] for name in ('NS','V','DENSE'))
module, read, require = (E[name] for name in ('module','read','require'))
TARGETS = E['TARGETS']
# Only the two reported dimensions are decimal approximations of independent geometry.
CENTER_TOLERANCE_M = 5e-6
DECIMAL_TOLERANCE = 5e-7
MARKDOWN = re.compile(r'!?\[[^]\n]+\]\(\s*(?:<([^>\n]+)>|([^\s)\n]+))\s*\)')
ERRORS = (ValueError, TypeError, KeyError, IndexError, ArithmeticError, OSError)


def quote(answer, claim):
    text = claim['quote']
    require(type(text) is str and text.strip() and text in answer,
            'assertion_does_not_quote_original_final_answer')
    return text


def markdown_paths(text):
    paths = []
    for link in MARKDOWN.finditer(text):
        value = unquote(link.group(1) or link.group(2)).replace('\\','/')
        if re.match(r'^/[A-Za-z]:/',value):
            value = value[1:]
        path = Path(value)
        if path.is_absolute() and path.suffix.casefold()=='.png':
            paths.append(path.as_posix())
    return paths


def final_link(slot, text, address, delivered):
    """Require an actual hyperlink and the previously delivered PNG of the same frame."""
    require(address in markdown_paths(text),'original_answer_has_no_clickable_owned_PNG_link')
    original = delivered.get(address)
    require(original is not None,'final_PNG_link_not_delivered_with_current_binding')
    closed = E['pin'](address,slot)
    require(closed['path']==address==original['path'] and closed['sha256']==original['sha256'],
            'after_close_reference_not_same_original_PNG')
    return {**original,'closed_reopen':closed}


def context(slot,binding,pinned_truth):
    prior = module(DENSE/'checks/evidence.py')
    formal = module(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py')
    raw,pub = prior['publication'](slot)
    original = prior['closed_answer'](slot,raw)
    require(original is not None and raw['closure_verification']['passed']
            and raw['independent_before_after']['passed'], 'owned_formal_result_or_answer_not_closed')
    source = read(slot/'TERMINAL_SOURCE.json')
    first = read(slot/'initial_capture/TERMINAL_SOURCE.json')
    geometry = E['truth'](source,pinned_truth)
    fixture = pinned_truth['sources']['saved_reopened']
    require(E['pin'](fixture['path'])['sha256']==fixture['sha256'],'sealed_cross_scale_source_changed')
    require(formal['verified_arrays'](first,source,read(fixture['path']))==21,'formal_before_after_not_same_meshes')
    require(raw['asset_sha256']==geometry['asset_sha256']==E['pin'](slot/'native/input.blend',slot)['sha256'],
            'formal_asset_copy_not_current')
    wires = prior['formal_wires'](slot,pub)
    device = E['frame_rows'](None,slot)
    deliveries = prior['frame_deliveries'](slot,list(device.values()),wires)
    tasks,owned_frames,route_by_path = [],{},{}
    first_paths = {}
    for event in wires['attempts']:
        if not event['model_visible_as_public_CLI_tool_result'] or event['is_error']:
            continue
        rx = read(event['RX']['path'])
        product = event.get('product') or {}
        evidence = product.get('producer_delivery')
        if evidence is None:
            continue
        producer = read(evidence['path']['path'])
        task = producer.get('facts',{}).get('region_task')
        args = product['arguments']
        current_task = task is not None and task['conditions']==E['CONDITIONS']
        for frame in producer.get('frames',[]):
            ref = frame['image_ref']
            if ref in deliveries and deliveries[ref] and producer.get('constructed_frames'):
                owned_frames.setdefault(ref,producer)
        if not current_task:
            continue
        detail = E['body'](rx)
        typed = None
        if detail.get('schema')==E['BRIEF']:
            typed = E['verify_public_witnesses'](rx,producer,slot=slot,device=device)
        packet = {'attempt':event['attempt'],'arguments':args,'schema':detail.get('schema'),
                  'include_image':args.get('include_image',True),'first_packet_paths':[],
                  'fixed_history_whole':event.get('fixed_history_whole')}
        if typed:
            for path in typed['first_packet_path_originals']:
                ref = path['ref']
                require(any(entry['attempt']==event['attempt'] for entry in deliveries[ref]),
                        'first_packet_path_has_no_actual_CLI_PNG_delivery')
                record = {**path,'attempt':event['attempt'],'route':'witness_image_paths'}
                route_by_path.setdefault(path['path'],[]).append(record)
                packet['first_packet_paths'].append(record)
            if not tasks:
                first_paths = {row['path']:row for row in packet['first_packet_paths']}
        tasks.append(packet)
    for ref,entries in deliveries.items():
        if ref not in device:
            continue
        for entry in entries:
            if not entry['named_local_path']:
                continue
            closed = E['pin'](device[ref]['PNG'],slot)
            route_by_path.setdefault(closed['path'],[]).append({'ref':ref,**closed,**entry})
    return {'slot':slot,'raw':raw,'answer':original,'source':source,'geometry':geometry,'device':device,
            'deliveries':deliveries,'owned_frames':owned_frames,'routes':route_by_path,'tasks':tasks,
            'first_paths':first_paths,'binding':binding}


def image(item, answer, claim, target):
    quote(answer,claim)
    address,ref = claim.get('local_path'),claim.get('image_ref')
    require(address or ref,'wanted_actual_final_image_reference')
    if address:
        require(address in claim['quote'],'claimed_path_not_in_original_answer')
        available = [r for r,row in item['device'].items() if Path(row['PNG']).as_posix()==address]
        require(len(available)==1 and (ref is None or ref==available[0]),'final_image_path_ref_not_owned_same_frame')
        ref = available[0]
    else:
        require(ref in claim['quote'],'claimed_frame_ref_not_in_original_answer')
    require(item['deliveries'].get(ref),'cited_original_was_not_delivered_to_actual_model')
    row = item['device'][ref]
    if row['origin']=='product':
        producer = item['owned_frames'][ref]
        capture = E['capture'](item['slot'],producer,item['source'],item['binding'])
        proof = E['product_frame'](item['slot'],row,producer,capture,item['source'],target,item['geometry'])
    else:
        require(row['origin']=='common_native','cited_frame_has_unknown_owner')
        adapter = SimpleNamespace(runtime=SimpleNamespace(device=SimpleNamespace(by_ref={ref:row})))
        native = module(V/'perf050_dense_micro_surface_holdout_001/qualification/native.py')
        proof = native['prove_image'](item['slot'],adapter,ref,target,source=item['source'],geometry=item['geometry'])
    require(proof['complete'] and (claim.get('view') is None or claim['view']==proof['view']),
            'cited_original_does_not_show_own_complete_current_region/'+target)
    return {'proof':proof,'reference_spelling':address or ref,'actual_delivery':item['deliveries'][ref]}


def quantity(value):
    if value in ('sqrt(10)/256','sqrt(10) / 256'):
        return sqrt(10)/256
    if value in ('3/sqrt(10)','3 / sqrt(10)'):
        return 3/sqrt(10)
    if value in ('1/64-sqrt(10)/256','1/64 - sqrt(10)/256'):
        return 1/64-sqrt(10)/256
    return float(F(str(value)))


def score(item,claims):
    slot = item['slot']
    answer = item['answer']['text']
    expected = item['geometry']['regions']
    rows = claims.get('regions',[])
    named = {row['object_name']:row for row in rows}
    checks,images,links = {},{},{}

    def report(label,checker):
        try:
            proof = checker()
            require(bool(proof),'absent_or_incorrect_final_fact')
        except ERRORS as error:
            checks[label] = {'passed':False,'reason':str(error)}
        else:
            checks[label] = {'passed':True,'verified':proof}

    def candidates():
        require(len(rows)==len(named)==3 and named.keys()==expected.keys(),'missing_or_extra_current_candidate')
        for row in rows:
            require(row['object_name'] in quote(answer,row),'candidate_not_named_in_original_answer')
        return list(named)

    def sources():
        candidates()
        for name in TARGETS:
            row = named[name]
            indices = row['source_triangle_indices']
            require(all(type(i) is int for i in indices) and sorted(indices)==expected[name]['source_triangle_indices'],
                    'wrong_evaluated_source_faces/'+name)
            require(len(row['center_world_m'])==3 and all(abs(quantity(x)-expected_v)<=CENTER_TOLERANCE_M
                    for x,expected_v in zip(row['center_world_m'],expected[name]['center_world_m'],strict=True)),
                    'incorrect_world_center/'+name)
        return {name:{'source_triangle_indices':named[name]['source_triangle_indices'],
                      'center_world_m':named[name]['center_world_m']} for name in TARGETS}

    def original(target):
        candidates = claims.get('images',{}).get(target,[])
        require(len(candidates)==1,'expected_one_explicit_original_image/'+target)
        proof = image(item,answer,candidates[0],target)
        images[target] = proof
        return proof

    def comparison():
        found = claims['comparison']
        quote(answer,found)
        difference = expected['M02']['area_m2']-expected['M09']['area_m2']
        for name in TARGETS:
            row = named[name]
            quote(answer,row)
            for key in ('area_m2','unit_normal_z'):
                require(abs(quantity(row[key])-expected[name][key])<=DECIMAL_TOLERANCE,
                        'incorrect_area_or_oriented_unit_normal_z/'+name+'/'+key)
        require(found['greater_area']=='M02' and found['more_plus_Z']=='M02'
                and abs(quantity(found['area_difference_m2'])-difference)<=DECIMAL_TOLERANCE,
                'wrong_area_difference_or_relative_plus_Z')
        return {'greater_area':'M02','area_difference_m2':difference,'more_plus_Z':'M02'}

    def unknown():
        row = claims['coverage_limit']
        quote(answer,row)
        finite = expected['M06']['directions']
        require(row['object_name']=='M06' and row['fixed_pool_only'] is True
                and row['complete_witness_missing'] is True and row.get('claims_total_invisibility') is not True
                and len(finite)==6 and all(not r['whole_region_clear'] for r in finite.values()),
                'finite_coverage_fact_must_not_assert_entire_invisibility')
        return {'object_name':'M06','known_directions':list(finite),'complete_witness':False}

    def reopen():
        for name in TARGETS:
            data = images[name]
            address = data['proof']['path']
            route = [row for row in item['routes'].get(address,[]) if row['ref']==data['proof']['ref']]
            require(route,'linked_PNG_path_was_not_from_a_model_visible_current_receipt/'+name)
            claim = claims['images'][name][0]
            links[name] = final_link(slot,claim['quote'],address,{address:route[0]})
            links[name]['other_actual_declarations'] = route[1:]
        require(links['M02']['path']!=links['M09']['path'],'same_original_must_not_be_used_for_two_regions')
        return links

    report('all_scene_candidates',candidates)
    report('current_evaluated_source_and_world_centers',sources)
    for target in TARGETS:
        report('complete_original_'+target,lambda target=target: original(target))
    report('numerical_area_and_oriented_normal_comparison',comparison)
    report('finite_six_direction_coverage_limit',unknown)
    report('two_final_markdown_originals_reopened_after_close',reopen)
    extra = claims.get('extra_unsupported_assertions',[])
    for unsupported in extra:
        quote(answer,unsupported)
    adopted_by_target = {}
    for name,link in links.items():
        first = item['first_paths'].get(link['path'])
        if first and first['ref']==link['ref']:
            declarations = [link,*link['other_actual_declarations']]
            adopted_by_target[name] = {'first':first,
                'also_received_later':any(row.get('attempt',0)>first['attempt'] for row in declarations)}
    total = sum(row['passed'] for row in checks.values())
    return {'slot':slot.name,'score':total,'planned':len(checks),'all_quality_passed':total==7 and not extra,
            'checks':checks,'extra_unsupported_assertions':extra,
            'final_original':{k:v for k,v in item['answer'].items() if k!='text'},
            'first_matching_task':item['tasks'][0] if item['tasks'] else None,
            'all_matching_tasks':item['tasks'],'first_packet_path_use':adopted_by_target,
            'both_first_packet_paths_used':checks['two_final_markdown_originals_reopened_after_close']['passed']
            and len(adopted_by_target)==2,'actual_budget':item['raw']['budget'],
            'desktop_render_or_human_click_observed':None}


def score_slot(slot,claims,*,binding,pinned_truth=None):
    truth = read(NS/'fixture/TRUTH.json') if pinned_truth is None else pinned_truth
    return score(context(Path(slot).resolve(strict=True),binding,truth),claims)


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--binding',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    report = score_slot(args.slot,read(args.claims),binding=args.binding)
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
