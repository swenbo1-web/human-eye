"""Verify current foot-region geometry and the original closed delivery."""

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
LOW_PATH = HERE.parent/'m4_yanyite_low_bilateral_product_native_001/score.py'
LOW = SimpleNamespace(**run_path(str(LOW_PATH)))
ORACLE, QUALIFY, OLD = LOW.ORACLE, LOW.QUALIFY, LOW.OLD
load, write, pin, require = LOW.load, LOW.write, LOW.pin, LOW.require
BOXES = {
    'negative_y': ((-.08,-.21,.05),(.08,-.115,.14)),
    'positive_y': ((-.08,.09,.125),(-.02,.21,.24)),
}
EXPECTED = {
    'negative_y': (247,193,.8603515573882434,'1b07b5e3fdad3453be0dbeccb5d9444e8a503a371c7f15f76e758f65f7565267'),
    'positive_y': (151,95,.7602539116605649,'4fcf5c994a2e1198dca61336228e088f7fcca8f3a9ad12fa29fbd4478b18fc15'),
}
THRESHOLD = Fraction(41,50)
REQUIRED = tuple(f'{region}.{item}' for region in BOXES for item in (*OLD.REGIONAL_ITEMS,'margin')) + ('nearer',)
ROOT = Path('D:/he_m1_yanyite_foot_region_image_evidence_consumption_001')
TERMINAL_RUN = Path('D:/he_m4_yanyite_low_bilateral_product_native_001')
TERMINAL_MEMBER = 'slots/P1/TERMINAL_SOURCE.json'
TERMINAL_SHA = 'f022aa6addb84c34bff78bf077765c97951ac2f47a969d1684796d828dae9eea'
PRODUCT_SOURCES = {
    'A1':'98b95613011bf66d4b80b382fefbee8f3073c1c25d9891d21f21d698c53981e1',
    'B1':'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e',
}


def foot_regions(world, triangles, cube, cube_triangles):
    regions = {}
    for name,bounds in BOXES.items():
        row = ORACLE.region_truth(world,triangles,cube,cube_triangles,bounds)
        faces,vertices,distance,checksum = EXPECTED[name]
        digest = sha256(json.dumps(row['triangle_ids'],separators=(',',':')).encode()).hexdigest()
        require((row['triangle_count'],row['vertex_count'],digest) == (faces,vertices,checksum)
                and abs(row['distance_m']-distance) <= ORACLE.WORLD_ALLOWANCE_M,
                'frozen_foot_selection_changed/'+name)
        margin = Fraction(*row['distance_exact']) - THRESHOLD
        del row['at_least_0_40_m']
        row.update(at_least_0_82_m=margin>=0,signed_margin_m=float(margin),
                   signed_margin_exact=[margin.numerator,margin.denominator],
                   ordered_triangle_ids_sha256=digest)
        regions[name] = row
    negative,positive = regions.values()
    require(negative['signed_margin_m']>0>positive['signed_margin_m'] and not
            set(negative['triangle_ids']).intersection(positive['triangle_ids']),
            'frozen_foot_threshold_or_overlap_changed')
    return regions


_verify_terminal = OLD.with_replacements(ORACLE.verify_terminal,truths=foot_regions)


def verify_terminal(terminal, historical, expected=None):
    result = _verify_terminal(terminal,historical,expected)
    require(terminal['display_object_mask'] == [True,False],'Cube_not_hidden_in_current_capture')
    result['nearer'] = 'positive_y'
    return result


verify_closed_source = OLD.with_replacements(ORACLE.verify_closed_source,verify_terminal=verify_terminal)


def historical_truth():
    snapshot,history = ORACLE.history()
    terminal,native_pins = LOW.archived(TERMINAL_RUN,TERMINAL_MEMBER,TERMINAL_SHA)
    captured,product_pins = LOW.archived(LOW.CURVED_RUN,LOW.CURVED_MEMBER,LOW.CURVED_SHA)
    require(native_pins[0]['bytes'] == 9_614_519 and
            (captured['source'],captured['coordinate_frame'],captured['unit']) == ('blender','world','m'),
            'frozen_foot_source_or_world_unit_changed')
    for old,mesh,shown in zip(terminal['objects'],captured['meshes'],captured['display_snapshot']['objects'],strict=True):
        require((old['name'],old['object_id'],old['evaluated']['triangles'],old['evaluated']['vertices_world_m'])
                == (mesh['name'],mesh['object_id'],mesh['faces'],mesh['vertices'])
                and shown['host_id']==old['object_id'] and shown['visible_get'] is old['visible_get']
                and all(shown[key]==old['display'][key] for key in ORACLE.DISPLAY),
                'archived_native_and_product_geometry_disagree')
    current = verify_terminal(terminal,snapshot)
    prior = (history['matrix64_world'], OLD.verify_terminal(terminal,snapshot)['matrix64_regions'],
             LOW.verify_terminal(terminal,snapshot)['matrix64_regions'])
    require(all(not set(region['triangle_ids']).intersection(before['triangle_ids'])
                for region in current['regions'].values() for domain in prior for before in domain.values()),
            'foot_selection_overlaps_earlier_tasks')
    source_pins = [*native_pins,*product_pins,*history['histories'],
                   *(pin(Path(p)) for p in (LOW_PATH,OLD.__file__,ORACLE.__file__,QUALIFY.__file__))]
    for row in source_pins:
        require(pin(row['path']) == {key:row[key] for key in ('path','bytes','sha256')},
                'frozen_foot_input_pin_changed')
    proof = {'passed':True,'source':native_pins[0],'second_capture':product_pins[0],
             'asset_sha256':ORACLE.ASSET,'nearer':'positive_y','threshold_m':float(THRESHOLD),
             'regions':current['regions'],'matrix64_world':current['matrix64_regions'],
             'no_overlap_with_old_tasks':True,'actual_Blender_starts':0,'actual_models':0,
             'input_pins':source_pins}
    return snapshot,proof


def preflight(output):
    _,proof = historical_truth()
    write(output,proof)
    return proof


def check_claim(item,row,answer,geometry,frames,claims):
    region,_,criterion = item.partition('.')
    if criterion not in ('threshold','margin'):
        return OLD.check_claim(item,row,answer,geometry,frames,claims)
    quote = row['quote']
    require(isinstance(quote,str) and quote.strip() and quote in answer,
            'claim_quote_absent_from_actual_final')
    truth = geometry['regions'][region]
    if criterion == 'threshold':
        require(row['at_least_0_82_m'] is truth['at_least_0_82_m'],'wrong_threshold_classification')
        return None
    literal = row['margin_literal'].replace('−','-')
    match = re.fullmatch(r'[+-]?[0-9]+(?:\.([0-9]+))?',literal)
    unit = row['unit']
    expected_relation = 'above' if truth['at_least_0_82_m'] else 'below'
    require(match and unit in ('m','mm') and row['relation']==expected_relation
            and re.search(r'(?<![\d.])'+re.escape(literal)+r'(?![\d.])',quote.replace('−','-')),
            'threshold_margin_not_literal_or_wrong_relation')
    factor = 1000 if unit=='mm' else 1
    amount = Fraction(literal)/factor
    require(amount>=0 or expected_relation=='below','threshold_margin_sign_reversed')
    tolerance = min(.000500001, .500001*10**(-len(match[1] or ''))/factor)
    require(abs(float(abs(amount))-abs(truth['signed_margin_m'])) <= max(tolerance,ORACLE.WORLD_ALLOWANCE_M),
            'threshold_margin_incorrect')
    return None


_inner = SimpleNamespace(**vars(OLD))
_inner.qualify_frames = OLD.with_replacements(OLD.qualify_frames,BOXES=BOXES)
qualify_frames = OLD.with_replacements(LOW.qualify_frames,OLD=_inner)


def verify_product_measurements(slot,calls,geometry,terminal):
    product = OLD.with_replacements(LOW.product_inputs,BOXES=BOXES,EXPECTED=EXPECTED,
                                    PRODUCT_SOURCE=PRODUCT_SOURCES[slot.name])
    return {row['attempt']:row for row in product(slot,calls,geometry,terminal)}


def requested_region(query,geometry):
    """Bind recognizable request intent even if the tool rejected the request."""
    selection = query.get('region')
    target, = (obj for obj in geometry['meshes'] if obj['name']==ORACLE.TARGET)
    if isinstance(selection,dict):
        selected = selection.get('object',{})
        if not isinstance(selected,dict) or not (selected.get('name')==target['name']
                                                 or selected.get('id')==target['object_id']):
            return None
        for region,(minimum,maximum) in BOXES.items():
            if (selection.get('world_box_m') == {'min':list(minimum),'max':list(maximum)}
                    or selection.get('source_triangle_indices')==geometry['regions'][region]['triangle_ids']):
                return region
    ref = query.get('region_ref')
    if isinstance(ref,dict) and (ref.get('host_id'),ref.get('instance_id'))==(target['object_id'],target['instance_id']):
        for region,truth in geometry['regions'].items():
            if ref.get('source_triangle_indices')==truth['triangle_ids']:
                return region
    return None


def image_evidence(call,packet,region,frames):
    evidence = []
    for frame in frames.get(region,()):
        attempt = call['attempt']
        cli = {row['owner_attempt'] for row in frame['CLI_delivery']}
        for delivery in frame['public_delivery']:
            if delivery['attempt'] != attempt or attempt not in cli:
                continue
            row = LOW.matching_public_image(packet,frame,delivery['public_block_index'])
            if row is None:
                continue
            path = row.get('local_image_path')
            sample = row.get('sampled_pixel')
            supported = False
            if isinstance(sample,dict):
                r,c,face = (sample.get(k) for k in ('row','column','source_triangle_index'))
                if all(type(value) is int and value>=0 for value in (r,c,face)) and face in frame['selected_triangle_counts']:
                    with QUALIFY.np.load(frame['NPZ']['path'],allow_pickle=False) as arrays:
                        rows,columns = arrays['owners'].shape
                        supported = bool(r<rows and c<columns and
                                         arrays['owners'][r,c]==frame['target_object_row'] and
                                         arrays['triangle_ids'][r,c]==frame['within_object_offset']+face)
            evidence.append({'ref':frame['ref'],'source_frame':frame['frame_identity'],
                             'image_sha256':frame['PNG']['sha256'],'native_block':delivery['public_block_index'],
                             'local_image_path':path if path==Path(frame['PNG']['path']).as_posix() else None,
                             'sampled_pixel':sample if supported else None})
    return evidence


def score_exposure(slot,calls,eligible,geometry,frames,chosen,claims,verdict):
    diary = load(slot/'consumer/BUSINESS_SOURCE_BINDING.json')
    cli = {row['attempt']:row for row in diary['result_contracts'] if row['matched'] is True}
    evidence,regions,seen_images = [],{},set()
    seen_by_region = {region:{'facts':False,'images':set(),'path_pixels':set()} for region in BOXES}
    for call in calls:
        attempt = call['attempt']
        packet = LOW.product_packet(call)
        args = call['request']['params'].get('arguments',{})
        query = args.get('query') if call['name']=='human_eye_scene_observe' else None
        verified = eligible.get(attempt,{})
        region = verified.get('region') or (requested_region(query,geometry) if isinstance(query,dict) else None)
        actual_cli = cli.get(attempt)
        image_ids = [sha256(raw).hexdigest() for _,raw in call['images']]
        delivered_hashes = image_ids if actual_cli else []
        duplicate = [digest for digest in delivered_hashes if digest in seen_images]
        seen_images.update(delivered_hashes)
        row = {'attempt':attempt,'tool':call['name'],'mode':query.get('mode') if isinstance(query,dict) else None,
               'region':region,'error':call['is_error'],'CLI_bound':actual_cli is not None,
               'CLI_text_bytes':actual_cli.get('CLI_text_UTF8_bytes') if actual_cli else None,
               'PNG_SHA256':delivered_hashes,'repeated_PNG_SHA256':duplicate}
        if isinstance(query,dict) and query.get('mode')=='source_region':
            publication = image_evidence(call,packet,region,frames) if packet and region and actual_cli else []
            facts = verified.get('status')=='verified' and actual_cli is not None
            is_brief = bool(packet and 'images' in packet and 'source_mapping' not in packet)
            full_to_evidence = bool(slot.name=='B1' and args.get('response_detail')=='full' and is_brief
                                    and packet.get('details')=='response_detail=full on the standard endpoint'
                                    and any(p['local_image_path'] and p['sampled_pixel'] for p in publication)
                                    and facts)
            row.update(requested_detail=args.get('response_detail','omitted'),
                       requests_image=args.get('include_image',True) is True,
                       projection='brief' if is_brief else ('full' if packet else None),
                       first_packet_projection_triggered=full_to_evidence,
                       image_evidence=publication, measured_source_facts_bound=facts,
                       exact_requested_world_box=verified.get('exact_requested_world_box'),
                       geometry_evidence=verified)
            if region:
                past = seen_by_region[region]
                first_verified_pixel = any(p['local_image_path'] and p['sampled_pixel']
                                           and p['image_sha256'] not in past['path_pixels'] for p in publication)
                row.update(repeated_measured_facts=facts and past['facts'],
                           repeated_region_PNG_SHA256=[h for h in delivered_hashes if h in past['images']],
                           new_image_path_and_pixel=first_verified_pixel)
                past['facts'] |= facts
                past['images'].update(delivered_hashes)
                past['path_pixels'].update(p['image_sha256'] for p in publication if p['local_image_path'] and p['sampled_pixel'])
        evidence.append(row)
    for region in BOXES:
        in_region = [r for r in evidence if r['region']==region and r['mode']=='source_region']
        first_request = next((r for r in in_region if r['requests_image']),None)
        first_delivery = next((r for r in in_region if r['image_evidence']),None)
        frame = chosen.get(region+'.image')
        path = claims.get(region+'.image',{}).get('local_image_path')
        sample = claims.get(region+'.pixel',{})
        adopted = []
        for row in in_region:
            for image in row['image_evidence']:
                p = image['sampled_pixel']
                match = bool(frame and path and verdict[region+'.image']['status']=='pass'
                             and image['ref']==frame['ref'] and image['local_image_path']
                             and Path(path).as_posix()==image['local_image_path'])
                same_pixel = bool(match and p and verdict[region+'.pixel']['status']=='pass'
                                  and [p['row'],p['column']]==sample.get('pixel_rc')
                                  and p['source_triangle_index']==sample.get('current_object_local_triangle'))
                adopted.append({'attempt':row['attempt'],'final_frame_and_path_match':match,
                                'final_path_and_pixel_match':same_pixel})
        first_number = first_request['attempt'] if first_request else None
        first_fact = (first_request['geometry_evidence']
                      if first_request and first_request['measured_source_facts_bound'] else None)
        match_first_measurement = False
        if first_fact and all(verdict.get(region+'.'+item,{}).get('status')=='pass'
                              for item in ('distance','nearest_pair','direction')):
            cited = claims[region+'.nearest_pair']
            observed = first_fact['nearest_pair']
            match_first_measurement = (
                abs(float(claims[region+'.distance']['distance_literal'])-first_fact['distance_m'])<=OLD.POSITION_TOL
                and QUALIFY.near_point(cited['selected_point_world_m'],observed['a'],OLD.POSITION_TOL)
                and QUALIFY.near_point(cited['Cube_point_world_m'],observed['b'],OLD.POSITION_TOL)
                and QUALIFY.near_point(claims[region+'.direction']['world_unit_direction'],
                                       observed['direction_a_to_b'],OLD.POSITION_TOL))
        regions[region] = {
            'first_image_request_attempt':first_number,
            'first_image_requested_detail':first_request['requested_detail'] if first_request else None,
            'first_image_response_projection':first_request['projection'] if first_request else None,
            'first_image_request_failed':first_request['error'] if first_request else None,
            'first_verified_image_delivery_attempt':first_delivery['attempt'] if first_delivery else None,
            'first_image_request_full_projection_triggered':bool(first_request and first_request['first_packet_projection_triggered']),
            'first_image_request_had_verified_path_and_pixel':bool(first_request and
                  any(p['local_image_path'] and p['sampled_pixel'] for p in first_request['image_evidence'])),
            'first_image_request_path_pixel_match_final':any(a['attempt']==first_number and a['final_path_and_pixel_match']
                                                             for a in adopted),
            'first_image_measurement_matches_final':match_first_measurement,
            'final_frame_origin':frame['origin'] if frame else None,'evidence_matching_final':adopted,
            'product_source_region_attempts':[r['attempt'] for r in in_region],
            'repeated_measurement_attempts':[r['attempt'] for r in in_region if r['repeated_measured_facts']],
            'PNG_retransmission_attempts':[r['attempt'] for r in in_region if r['repeated_region_PNG_SHA256']],
        }
    return {'regions':regions,'calls':evidence,'tool_counts':dict(Counter(row['tool'] for row in evidence)),
            'same_PNG_retransmission_count':sum(len(row['repeated_PNG_SHA256']) for row in evidence),
            'first_image_request_full_denominator':sum(r['first_image_requested_detail']=='full' for r in regions.values()),
            'first_image_request_projection_trigger_count':sum(r['first_image_request_full_projection_triggered']
                                                              for r in regions.values()),
            'first_image_path_pixel_adoption_count':sum(r['first_image_request_path_pixel_match_final']
                                                       for r in regions.values())}


def score_slot(slot,claim_path=None):
    slot = Path(slot).resolve()
    require(slot.name in PRODUCT_SOURCES,'unexpected_foot_formal_slot')
    result_path,publication_path = slot/'SLOT_RESULT.json',slot/'SLOT_PUBLICATION.json'
    if not publication_path.is_file():
        return {'slot':slot.name,'actual_status':'unconfirmed' if slot.is_dir() else 'unrun',
                'quality_complete':False,'passed_items':0,'total_items':len(REQUIRED),
                'unverified_items':list(REQUIRED),'final_available':False,'adoption':None}
    result,publication = map(load,(result_path,publication_path))
    require(slot.name==result['label']==publication['label']
            and publication['result_sha256']==pin(result_path)['sha256'],'slot_result_unbound')
    summary = {'slot':slot.name,'actual_status':publication['status'],'quality_complete':False,
               'passed_items':0,'total_items':len(REQUIRED),'failure_records':result.get('errors',[])}
    if (result['status']!='completed' or publication['status']!='completed'
            or not (result.get('consumer') or {}).get('valid_completion')):
        return {**summary,'final_available':False,'unverified_items':list(REQUIRED),'adoption':None}
    historical,known = historical_truth()
    geometry,terminal,device = verify_closed_source(slot,historical,known)
    answer,final,cli_calls,stdout = OLD.verify_public_final(slot,result)
    if any((slot/'owner').glob('tool_*')):
        calls = QUALIFY.actual_calls(slot)
        frames,unusable = qualify_frames(slot,terminal,device,geometry,cli_calls,calls)
        product = verify_product_measurements(slot,calls,geometry,terminal)
    else:
        require(not device['frames'] and not cli_calls,'frame_or_CLI_tool_traffic_has_no_owner_call')
        calls,frames,unusable,product = [],dict.fromkeys(BOXES,()),[],{}
    summary.update(final_available=True,answer=answer,CLI_stdout=stdout,actual_final_item=final['id'],
                   same_slot_geometry=geometry,usable_frames=frames,unusable_frames=unusable)
    if claim_path is None:
        return {**summary,'unverified_items':list(REQUIRED),'awaits_literal_claim_transcription':True,
                'adoption':score_exposure(slot,calls,product,geometry,frames,{},{},{})}
    table = load(claim_path)
    require(table['answer_sha256']==answer['sha256'] and table['slot']==slot.name
            and set(table['claims'])<=set(REQUIRED),'literal_claims_unbound_to_original_answer')
    claims,verdict,chosen = table['claims'],{},{}
    for item in REQUIRED:
        if item not in claims:
            verdict[item] = {'status':'missing'}
            continue
        row = claims[item]
        try:
            frame = check_claim(item,row,final['text'],geometry,frames,claims)
            if frame is not None:
                chosen[item] = frame
            verdict[item] = {'status':'pass','quote':row['quote']}
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            verdict[item] = {'status':'failure','quote':row.get('quote'),'reason':str(error)}
    if len(chosen)==2 and len({frame['ref'] for frame in chosen.values()})!=2:
        for item in chosen:
            verdict[item] = {**verdict[item],'status':'failure','reason':'same_frame_reused_for_two_local_originals'}
    passed = sum(row['status']=='pass' for row in verdict.values())
    return {**summary,'passed_items':passed,'quality_complete':passed==len(REQUIRED),
            'claim_transcription':pin(claim_path),'criteria':verdict,'chosen_images':chosen,
            'adoption':score_exposure(slot,calls,product,geometry,frames,chosen,claims,verdict)}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',type=Path)
    mode.add_argument('--slot',type=Path)
    cli.add_argument('--claims',type=Path)
    cli.add_argument('--output',type=Path)
    args = cli.parse_args()
    if args.preflight:
        preflight(args.preflight)
    else:
        require(args.output is not None,'score_output_required')
        try:
            verdict = score_slot(args.slot,args.claims)
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            verdict = {'slot':args.slot.name,'quality_complete':False,'passed_items':0,'total_items':len(REQUIRED),
                       'unverified_items':list(REQUIRED),'error':str(error),'adoption':None}
        write(args.output,verdict)
        print({key:verdict[key] for key in ('slot','quality_complete','passed_items','total_items','error') if key in verdict})
        raise SystemExit(0 if verdict['quality_complete'] or args.claims is None and
                         verdict.get('awaits_literal_claim_transcription') is True else 1)
