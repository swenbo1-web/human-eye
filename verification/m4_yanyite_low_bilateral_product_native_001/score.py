"""Adjudicate low Yanyite regions from exact source and closed-slot evidence."""

import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
OLD = SimpleNamespace(**run_path(str(HERE.parent/'m4_yanyite_bilateral_region_native_001/score.py')))
ORACLE, QUALIFY = OLD.ORACLE, OLD.QUALIFY
load, pin, require, write = OLD.load, OLD.pin, OLD.require, OLD.write
BOXES = {'left': ((-.09,-.14,.30),(-.04,.02,.50)),
         'right': ((.04,-.14,.30),(.09,.02,.53))}
EXPECTED = {
    'left': (199,139,.5097656218945279,'15ae8ef3a74539f6be145c8d17143d9ac35f529114dd35b0ba7a5b10d5d7179f'),
    'right': (392,258,.47021484284290327,'5935331261c31d5d33b90eb94c66cf2418fb5961004e42a0fa9a09ceab91f129'),
}
THRESHOLD = Fraction(49,100)
REQUIRED = OLD.REQUIRED
TERMINAL_RUN = Path('D:/he_m4_yanyite_bilateral_region_native_001')
CURVED_RUN = Path('D:/he_m4_source_region_curved_view_sample_001')
TERMINAL_MEMBER = 'slots/P1/TERMINAL_SOURCE.json'
CURVED_MEMBER = 'arms/P1/CAPTURE_01.json'
TERMINAL_SHA = 'ac102487f75c875e5c1fba2ea374b87295022dae4172359f068357a56b4e241b'
CURVED_SHA = '63ae6ed6bb6c372e31b91a814a6d6bb8f7171afdab8b8f47a91cf53f7d4bb2d5'
PRODUCT_SOURCE = '98b95613011bf66d4b80b382fefbee8f3073c1c25d9891d21f21d698c53981e1'


def low_regions(world, triangles, cube, cube_triangles):
    rows = {}
    for name, bounds in BOXES.items():
        row = ORACLE.region_truth(world, triangles, cube, cube_triangles, bounds)
        faces, vertices, distance, checksum = EXPECTED[name]
        actual_checksum = sha256(json.dumps(row['triangle_ids'],separators=(',',':')).encode()).hexdigest()
        require((row['triangle_count'],row['vertex_count'],actual_checksum) == (faces,vertices,checksum)
                and abs(row['distance_m']-distance) <= ORACLE.WORLD_ALLOWANCE_M,
                'frozen_low_bilateral_geometry_changed/'+name)
        del row['at_least_0_40_m']
        row['at_least_0_49_m'] = Fraction(*row['distance_exact']) >= THRESHOLD
        row['ordered_triangle_ids_sha256'] = actual_checksum
        rows[name] = row
    require(rows['left']['at_least_0_49_m'] and not rows['right']['at_least_0_49_m']
            and not set(rows['left']['triangle_ids']) & set(rows['right']['triangle_ids']),
            'low_selection_overlap_or_threshold_mismatch')
    return rows


_verify_terminal = OLD.with_replacements(ORACLE.verify_terminal, truths=low_regions)


def verify_terminal(terminal, historical, expected=None):
    geometry = _verify_terminal(terminal, historical, expected)
    require(terminal['display_object_mask'] == [True,False], 'Cube_not_hidden_in_current_capture')
    geometry['nearer'] = 'right'
    return geometry


verify_closed_source = OLD.with_replacements(ORACLE.verify_closed_source, verify_terminal=verify_terminal)


def archived(root, member, checksum):
    path = root/member
    source = pin(path)
    index = root/'sealed/RAW_INDEX.json'
    listing = load(index)
    bundle = Path(listing['archive']['path']).resolve(strict=True)
    require(source['sha256'] == checksum and bundle == (root/'sealed/ORIGINAL_RUNTIME.zip').resolve()
            and listing['members'][member] == {'bytes':source['bytes'],'sha256':checksum},
            'frozen_source_archive_identity_changed/'+member)
    with ZipFile(bundle) as zipped:
        require(zipped.read(member) == path.read_bytes(), 'frozen_source_archive_bytes_changed/'+member)
    return load(path), [source, pin(index), listing['archive']]


def historical_truth():
    snapshot, history = ORACLE.history()
    terminal, terminal_pins = archived(TERMINAL_RUN, TERMINAL_MEMBER, TERMINAL_SHA)
    captured, captured_pins = archived(CURVED_RUN, CURVED_MEMBER, CURVED_SHA)
    require(terminal_pins[0]['bytes'] == 9_614_514
            and (captured['source'],captured['coordinate_frame'],captured['unit']) == ('blender','world','m'),
            'frozen_Yanyite_ownership_or_unit_changed')
    display = captured['display_snapshot']['objects']
    for old, raw, seen in zip(terminal['objects'],captured['meshes'],display,strict=True):
        require((old['name'],old['object_id'],old['evaluated']['triangles'],old['evaluated']['vertices_world_m'])
                == (raw['name'],raw['object_id'],raw['faces'],raw['vertices'])
                and seen['host_id'] == old['object_id'] and seen['visible_get'] is old['visible_get']
                and all(seen[key] == old['display'][key] for key in ORACLE.DISPLAY),
                'frozen_native_and_product_source_disagree')
    current = verify_terminal(terminal, snapshot)
    old_domains = (history['matrix64_world'], OLD.verify_terminal(terminal,snapshot)['matrix64_regions'])
    require(all(not set(region['triangle_ids']) & set(old['triangle_ids'])
                for region in current['regions'].values()
                for domain in old_domains for old in domain.values()),
            'new_low_selection_overlaps_earlier_tasks')
    proof = {'passed':True, 'source':terminal_pins[0], 'second_capture':captured_pins[0],
             'threshold_m':float(THRESHOLD),'nearer':'right','asset_sha256':ORACLE.ASSET,
             'regions':current['regions'],'matrix64_world':current['matrix64_regions'],
             'no_overlap_with_old_tasks':True,'actual_Blender_starts':0,'actual_models':0,
             'input_pins':[*terminal_pins,*captured_pins,*history['histories'],
                           pin(Path(OLD.__file__)),pin(Path(ORACLE.__file__)),pin(Path(QUALIFY.__file__))]}
    return snapshot, proof


def preflight(output):
    _, proof = historical_truth()
    write(output, proof)
    return proof


def product_wire(slot, call):
    folder = call['folder']
    proof = load(folder/'PRODUCT_RECEIPT.json')
    relay = slot/'mcp'/f"rpc_{proof['receipt']['index']:02d}"
    tx, rx = relay/'TX.bin', relay/'RX.bin'
    args = call['request']['params']['arguments']
    require(load(tx)['params']['arguments'] == args == load(folder/'PRODUCT_ARGUMENTS.json')
            and load(tx) == load(folder/'PRODUCT_REQUEST.json')
            and load(rx) == load(folder/'PRODUCT_RESPONSE.json')
            and load(rx)['result'] == call['reply']['result']
            and pin(rx)['sha256'] == proof['receipt']['RX_sha256'],
            'public_product_wire_is_not_the_same_closed_transaction')
    producer = proof['producer_archive']
    report = QUALIFY.receipt(slot, producer['path'], producer['sha256'])
    return args, load(Path(report['path'])), {'producer':report,'TX':pin(tx),'RX':pin(rx)}


def product_packet(call):
    if call['name'] != 'human_eye_scene_observe' or call['is_error']:
        return None
    for text in call['text']:
        try:
            packet = json.loads(text)
        except ValueError:
            continue
        if isinstance(packet,dict) and packet.get('result_kind') == 'source_region':
            return packet
    return None


def product_inputs(slot, calls, geometry, terminal):
    evidence = []
    objects = terminal['objects']
    ordered = QUALIFY.canonical_sha([{'host_id':o['object_id'],'instance_id':o['instance_id'],
        'vertices':o['evaluated']['vertices_world_m'],'faces':o['evaluated']['triangles']} for o in objects])
    target,cube = ({o['name']:o for o in geometry['meshes']}[name] for name in (ORACLE.TARGET,ORACLE.REFERENCE))
    for call in calls:
        packet = product_packet(call)
        if packet is None:
            continue
        try:
            args, full, wire = product_wire(slot,call)
            ref, task, binding = full['region_ref'],full['task_result'],full['binding']
            query = args['query']
            require(query['mode'] == full['result_kind'] == 'source_region'
                    and full['read_only'] is True and full['execution_authority'] is False
                    and packet['region_ref'] == task['region_ref'] == ref
                    and task['binding'] == binding and binding['capture_scope'] == 'complete_scene_meshes'
                    and binding['coordinate_frame'] == 'world' and binding['unit'] == 'm'
                    and binding['document_epoch'] == ref['document_epoch']
                    and binding['ordered_geometry_sha256'] == ref['ordered_geometry_sha256'] == ordered
                    and binding['runtime_source_sha256'] == PRODUCT_SOURCE
                    and binding['image_scope']['participation_mask'] == terminal['display_object_mask']
                    and all(binding['capture_state'][k] == ref['capture_generation'][k]
                            for k in ('instance_id','revision','epoch'))
                    and (ref['host_id'],ref['instance_id']) == (target['object_id'],target['instance_id'])
                    and all(task['reference'][k] == cube[k] for k in ('name','object_id','instance_id')),
                    'product_measurement_not_bound_to_current_selected_source_and_whole_Cube')
            matches = [n for n,r in geometry['regions'].items() if r['triangle_ids'] == ref['source_triangle_indices']]
            require(len(matches) == 1, 'actual_product_source_region_not_one_of_the_requested_boxes')
            name = matches[0]
            public_task = packet['task_result']
            fact = public_task['facts']['surface_proximity']
            require(public_task['reference'] == task['reference']
                    and public_task['measurement_scope'] == task['measurement_scope']
                    == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
                    and fact == task['facts']['surface_proximity'] and fact['status'] == 'measured',
                    'product_public_measurement_missing_or_differs_from_current_source')
            value = fact['value']
            pair = value['nearest_witness']
            QUALIFY.numeric_pair(value['distance_m'],pair['direction_a_to_b'],pair['a'],pair['b'],
                                 geometry['matrix64_regions'][name],OLD.POSITION_TOL)
            if 'region' in packet:
                require((packet['region']['source_triangle_count'],packet['region']['source_vertex_count'])
                        == (EXPECTED[name][0],EXPECTED[name][1]), 'product_public_current_source_counts_changed')
            world_box = (query.get('region') or {}).get('world_box_m')
            literal_box = {'min':list(BOXES[name][0]),'max':list(BOXES[name][1])}
            evidence.append({'attempt':call['attempt'],'region':name,'world_box_requested':world_box is not None,
                             'exact_requested_world_box':world_box == literal_box,
                             'includes_image':args.get('include_image',True) is True,
                             'response_detail':args.get('response_detail','omitted'),
                             'images_delivered':len(call['images']),'visibility':packet.get('visibility'),
                             'distance_m':value['distance_m'],'nearest_pair':pair,
                             'body':packet.get('images',[]),'status':'verified',**wire})
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            evidence.append({'attempt':call['attempt'],'status':'unverified','reason':str(error)})
    return evidence


def matching_public_image(packet, frame, index):
    """Require the visible image row to name this exact producer and native block."""
    rows = packet.get('images',[]) if 'images' in packet else packet.get('frames',[])
    image_rows = [r for r in rows if r.get('image_ref') == frame['ref']
                  and r.get('frame_identity') == frame['frame_identity']
                  and r.get('image_sha256') == frame['PNG']['sha256']]
    if len(image_rows) != 1:
        return None
    row = image_rows[0]
    if 'images' in packet:
        return row if row.get('image_block_index') == index else None
    # The source_region full response allows one native image and carries its
    # binding in frames, with the JSON body as content index zero.
    return row if len(rows) == 1 and index == 1 else None


def qualify_frames(slot, terminal, device, geometry, cli_calls, calls):
    frames, unusable = OLD.qualify_frames(slot,terminal,device,geometry,cli_calls)
    by_attempt = {row['attempt']:row for row in calls}
    for region,candidates in frames.items():
        for frame in tuple(candidates):
            if frame['origin'] != 'product':
                continue
            preserved = [entry for entry in frame['public_delivery'] if
                         by_attempt[entry['attempt']]['name'] == 'read_images' or
                         matching_public_image(product_packet(by_attempt[entry['attempt']]) or {},
                                               frame,entry['public_block_index']) is not None]
            delivered_attempts = {entry['attempt'] for entry in preserved}
            if not delivered_attempts & {entry['owner_attempt'] for entry in frame['CLI_delivery']}:
                candidates.remove(frame)
                unusable.append({'region':region,'ref':frame['ref'],
                                 'reason':'actual_product_image_row_or_native_content_block_unbound'})
                continue
            frame['public_delivery'] = preserved
            frame['CLI_delivery'] = [entry for entry in frame['CLI_delivery']
                                     if entry['owner_attempt'] in delivered_attempts]
    return frames,unusable


def check_claim(item, row, answer, geometry, frames, claims):
    if not item.endswith('.threshold'):
        return OLD.check_claim(item, row, answer, geometry, frames, claims)
    quote = row['quote']
    region = item.split('.')[0]
    require(isinstance(quote,str) and quote.strip() and quote in answer, 'claim_quote_absent_from_actual_final')
    require(row['at_least_0_49_m'] is geometry['regions'][region]['at_least_0_49_m'],
            'incorrect_threshold_classification')
    return None


def adoption(slot, calls, product, chosen, claims, verdict):
    by_attempt = {row['attempt']:row for row in calls}
    regions = {}
    for region in BOXES:
        frame = chosen.get(region+'.image')
        source = [r for r in product if r.get('region') == region]
        delivered = []
        if frame and verdict[region+'.image']['status'] == 'pass':
            for row in frame['public_delivery']:
                call = by_attempt[row['attempt']]
                packet = product_packet(call) or {}
                image = matching_public_image(packet,frame,row['public_block_index'])
                if image is not None:
                    got = image.get('sampled_pixel') or {}
                    pixel = claims.get(region+'.pixel',{})
                    literal = claims.get(region+'.image',{}).get('local_image_path')
                    image_path = image.get('local_image_path')
                    path_matches = isinstance(image_path,str) and isinstance(literal,str) and Path(image_path) == Path(literal)
                    anchor_matches = (verdict[region+'.pixel']['status'] == 'pass'
                                      and [got.get('row'),got.get('column')] == pixel.get('pixel_rc')
                                      and got.get('source_triangle_index') == pixel.get('current_object_local_triangle'))
                    delivered.append({'attempt':row['attempt'],'path_literal_matches':path_matches,
                                      'pixel_literal_matches':anchor_matches})
        first = source[0]['attempt'] if source else None
        regions[region] = {'first_verified_product_attempt':first,
                           'first_product_exact_world_box':source[0]['exact_requested_world_box'] if source else None,
                           'final_frame_origin':frame['origin'] if frame else None,'product_frame_deliveries':delivered,
                           'first_verified_product_frame_reflects_final_path_and_pixel':any(
                               row['attempt'] == first and row['path_literal_matches'] and row['pixel_literal_matches']
                               for row in delivered)}
    return {'regions':regions,'product_packets':product,
            'actual_tool_counts':dict(Counter(r['name'] for r in calls)),
            'actual_tool_errors':[{k:r[k] for k in ('attempt','name')} for r in calls if r['is_error']]}


def score_slot(slot, claim_path=None):
    slot = Path(slot).resolve(strict=True)
    result, publication = (load(slot/n) for n in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
    require(slot.name == result['label'] == publication['label']
            and publication['result_sha256'] == pin(slot/'SLOT_RESULT.json')['sha256'],
            'actual_slot_result_unbound')
    summary = {'slot':slot.name,'actual_status':publication['status'],'quality_complete':False,
               'passed_items':0,'total_items':len(REQUIRED),'failure_records':result.get('errors',[])}
    if result['status'] != 'completed' or publication['status'] != 'completed' or not result.get('consumer',{}).get('valid_completion'):
        return {**summary,'final_available':False,'unverified_items':list(REQUIRED)}
    historical, known = historical_truth()
    geometry,terminal,device = verify_closed_source(slot,historical,known)
    answer,final,cli_calls,stdout = OLD.verify_public_final(slot,result)
    calls = QUALIFY.actual_calls(slot)
    frames,unusable = qualify_frames(slot,terminal,device,geometry,cli_calls,calls)
    product = product_inputs(slot,calls,geometry,terminal) if slot.name == 'P1' else []
    summary.update(final_available=True,answer=answer,CLI_stdout=stdout,actual_final_item=final['id'],
                   same_slot_geometry=geometry,usable_frames=frames,unusable_frames=unusable)
    if claim_path is None:
        return {**summary,'unverified_items':list(REQUIRED),'awaits_literal_claim_transcription':True,
                'wire_evidence':product}
    table = load(claim_path)
    require(table['answer_sha256'] == answer['sha256'] and table['slot'] == slot.name
            and set(table['claims']) <= set(REQUIRED),'literal_claim_transcription_not_bound_to_original_answer')
    claims = table['claims']
    verdict,chosen = {},{}
    for item in REQUIRED:
        row = claims.get(item)
        if row is None:
            verdict[item] = {'status':'missing'}
            continue
        try:
            frame = check_claim(item,row,final['text'],geometry,frames,claims)
            if frame is not None:
                chosen[item] = frame
            verdict[item] = {'status':'pass','quote':row['quote']}
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            verdict[item] = {'status':'failure','quote':row.get('quote'),'reason':str(error)}
    if len(chosen) == 2 and len({frame['ref'] for frame in chosen.values()}) != 2:
        for item in chosen:
            verdict[item].update(status='failure',reason='same_frame_repeated_as_two_distinct_local_originals')
    passed = sum(row['status'] == 'pass' for row in verdict.values())
    return {**summary,'passed_items':passed,'quality_complete':passed == len(REQUIRED),
            'claim_transcription':pin(claim_path),'criteria':verdict,'chosen_images':chosen,
            'adoption':adoption(slot,calls,product,chosen,claims,verdict)}


if __name__ == '__main__':
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
                       'unverified_items':list(REQUIRED),'error':str(error)}
        write(args.output,verdict)
        print({k:verdict[k] for k in ('slot','quality_complete','passed_items','total_items','error') if k in verdict})
        raise SystemExit(0 if verdict['quality_complete'] else 1)
