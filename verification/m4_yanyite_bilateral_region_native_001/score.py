"""Verify bilateral source truth and literal final answers against closed-slot wires."""

import argparse
from base64 import b64decode
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from runpy import run_path
import subprocess
import sys
from types import FunctionType, SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PRIOR = HERE.parent/'m4_yanyite_dual_curved_region_native_001/score'
ORACLE = SimpleNamespace(**run_path(str(PRIOR/'oracle.py')))
paths = sys.path[:]
try:
    QUALIFY = SimpleNamespace(**run_path(str(PRIOR/'qualify.py')))
finally:
    sys.path[:] = paths

load, pin, require, write = ORACLE.load, ORACLE.pin, ORACLE.require, ORACLE.write
SOURCE_RUN = Path('D:/he_m2_resident_capture_direct_delta_001')
SOURCE_GIT = '48899b41f592fc60b266b4b278bd7e4b9d5c8daa'
SOURCE_MEMBER = 'slots/A/TERMINAL_SOURCE.json'
SOURCE_SHA = '63b2ece7ee16f1a14083db12124d7a55354354fbcabcb40a56d13ea7af3cb399'
SOURCE_EVIDENCE = HERE.parent/'m2_resident_capture_direct_delta_001/RESULT.json'
BOXES = {'left': ((-.10,-.09,.65),(-.025,.09,.80)),
         'right': ((.025,-.09,.65),(.10,.09,.80))}
EXPECTED = {'left': (178, 125, .201660157584), 'right': (155, 98, .200195311849)}
THRESHOLD = Fraction(201, 1000)
POSITION_TOL = 1e-6
REGIONAL_ITEMS = ('counts', 'distance', 'direction', 'nearest_pair', 'threshold', 'image', 'pixel', 'scope')
REQUIRED = tuple(f'{region}.{item}' for region in BOXES for item in REGIONAL_ITEMS) + ('nearer',)


def truth_regions(world, triangles, cube, cube_triangles):
    answers = {name: ORACLE.region_truth(world, triangles, cube, cube_triangles, bounds)
               for name, bounds in BOXES.items()}
    for name, row in answers.items():
        count, vertices, expected = EXPECTED[name]
        require((row['triangle_count'], row['vertex_count']) == (count, vertices) and
                abs(row['distance_m']-expected) < 1e-7, 'frozen_bilateral_truth_changed/'+name)
        row.pop('at_least_0_40_m')
        row['at_least_0_201_m'] = Fraction(*row['distance_exact']) >= THRESHOLD
    left, right = answers.values()
    require(not set(left['triangle_ids']) & set(right['triangle_ids']) and
            left['at_least_0_201_m'] and not right['at_least_0_201_m'] and
            left['distance_m'] > right['distance_m'], 'frozen_bilateral_threshold_or_order_changed')
    return answers


def with_replacements(function, **changes):
    return FunctionType(function.__code__, {**function.__globals__, **changes},
                        function.__name__, function.__defaults__)


_verify_terminal = with_replacements(ORACLE.verify_terminal, truths=truth_regions)


def verify_terminal(terminal, historical, expected=None):
    geometry = _verify_terminal(terminal, historical, expected)
    geometry['nearer'] = 'right'
    return geometry


verify_closed_source = with_replacements(ORACLE.verify_closed_source, verify_terminal=verify_terminal)


def historical_truth():
    pin_fields = ('path', 'bytes', 'sha256')
    source, index = SOURCE_RUN/SOURCE_MEMBER, SOURCE_RUN/'sealed/RAW_INDEX.json'
    source_file = pin(source)
    require((source_file['bytes'], source_file['sha256']) == (9_614_509, SOURCE_SHA),
            'fixed_current_Yanyite_source_changed')
    recorded = subprocess.check_output(['git', '-C', str(REPO), 'show',
        f'{SOURCE_GIT}:{SOURCE_EVIDENCE.relative_to(REPO).as_posix()}'])
    require(SOURCE_EVIDENCE.read_bytes() == recorded, 'accepted_M2_source_evidence_changed')
    published, listing = load(SOURCE_EVIDENCE), load(index)
    archive = Path(listing['archive']['path'])
    require(published['passed'] is True and listing['archive'] == pin(archive) == published['raw_evidence_local'] and
            published['live_arms']['A']['terminal_files']['TERMINAL_SOURCE.json'] == source_file and
            published['raw_member_count'] == listing['member_count'] == len(listing['members']),
            'fixed_M2_source_not_bound_to_sealed_archive')
    with ZipFile(archive) as zip_file:
        require(zip_file.read(SOURCE_MEMBER) == source.read_bytes() and
                listing['members'][SOURCE_MEMBER] == {key:source_file[key] for key in pin_fields if key != 'path'},
                'fixed_Yanyite_source_is_not_same_sealed_terminal')
    historical, _ = ORACLE.history()
    terminal = load(source)
    known = verify_terminal(terminal, historical)
    old = ORACLE.verify_terminal(terminal, historical)['regions']
    require(all(not set(old_row['triangle_ids']) & set(new_row['triangle_ids'])
                for old_row in old.values() for new_row in known['regions'].values()),
            'new_bilateral_regions_overlap_old_task')
    require(terminal['display_object_mask'] == [True, False], 'source_hidden_Cube_display_changed')
    proof = {'passed': True, 'source': source_file, 'threshold_m': float(THRESHOLD), 'nearer': 'right',
             'regions': known['regions'], 'matrix64_world': known['matrix64_regions'],
             'no_overlap_with_old_task': True, 'actual_Blender_starts': 0,
             'input_pins': [source_file, pin(index), pin(archive), pin(SOURCE_EVIDENCE),
                            pin(Path(ORACLE.__file__)), pin(Path(QUALIFY.__file__))]}
    return historical, proof


def preflight(output):
    _, proof = historical_truth()
    write(output, proof)
    return proof


def verify_public_final(slot, result):
    answer = slot/'consumer/PUBLIC_FINAL.txt'
    archived = pin(answer)
    require(result['answer'] == archived, 'published_final_file_changed')
    raw = slot/'consumer/stdout.raw.bin'
    events = [json.loads(line) for line in raw.read_bytes().splitlines() if line]
    completed = [row['item'] for row in events if row['type'] == 'item.completed']
    final = [i for i in completed if i['type'] == 'agent_message'][-1]
    require(any(row['type'] == 'turn.completed' for row in events) and
            not any(row['type'] == 'turn.failed' for row in events) and
            answer.read_text(encoding='utf8').rstrip('\n') == final['text'].rstrip('\n'),
            'public_final_not_the_completed_original_CLI_answer')
    calls = [i for i in completed if i['type'] == 'mcp_tool_call' and i.get('result') and not i.get('error')]
    return archived, final, calls, pin(raw)


def check_product_frame(slot, frame, calls):
    if frame['origin'] != 'product':
        return []
    target = frame['full_result']
    evidence = []
    for call in calls:
        folder = call['folder']
        if call['name'] != 'human_eye_scene_observe' or call['is_error'] or not (folder/'PRODUCT_RECEIPT.json').is_file():
            continue
        proof = load(folder/'PRODUCT_RECEIPT.json')
        if proof.get('producer_archive') != target:
            continue
        actual_args = call['request']['params']['arguments']
        transport = slot/'mcp'/f"rpc_{proof['receipt']['index']:02d}"
        tx, rx = transport/'TX.bin', transport/'RX.bin'
        require(load(tx)['params']['arguments'] == actual_args == load(folder/'PRODUCT_ARGUMENTS.json') and
                load(tx) == load(folder/'PRODUCT_REQUEST.json') and
                load(rx) == load(folder/'PRODUCT_RESPONSE.json') and
                load(rx)['result'] == call['reply']['result'] and pin(rx)['sha256'] == proof['receipt']['RX_sha256'],
                'product_frame_command_or_reply_was_rewritten')
        evidence.append({'attempt': call['attempt'], 'TX': pin(tx), 'RX': pin(rx)})
    require(evidence, 'producer_archive_not_its_actual_product_tool_call')
    return evidence


def consumer_delivery(frame, verified, owner_calls, consumer_calls):
    image = Path(verified['PNG']['path']).read_bytes()
    raw_attempts = {row['attempt'] for row in verified['public_delivery']}
    published = [row for row in owner_calls if row['attempt'] in raw_attempts]
    out = []
    for item in consumer_calls:
        args = item.get('arguments')
        for row in published:
            if item.get('tool') != row['name'] or args != row['request']['params']['arguments']:
                continue
            blocks = item['result']['content']
            refs = any(frame['ref'] in value.get('text','') or verified['PNG']['path'].replace('\\','/') in value.get('text','')
                       for value in blocks if value['type'] == 'text')
            if row['name'] == 'read_images':
                refs |= frame['ref'] in args.get('refs', [])
            hits = [i for i,b in enumerate(blocks) if b['type'] == 'image' and b.get('mimeType') == 'image/png'
                    and b64decode(b['data'], validate=True) == image]
            if refs and hits:
                require(len(hits) == 1, 'consumer_frame_duplicate_original_PNG')
                out.append({'item_id': item['id'], 'owner_attempt': row['attempt'], 'block': hits[0]})
    require(out, 'original_PNG_not_observed_in_actual_CLI_tool_traffic')
    return out


def qualify_frames(slot, terminal, device, geometry, cli_calls):
    owner_calls = QUALIFY.actual_calls(slot)
    candidates, errors = {r: [] for r in BOXES}, []
    for record in device['frames']:
        for region in BOXES:
            try:
                image = QUALIFY.frame_truth(record, slot, terminal, device, geometry['regions'][region], owner_calls)
                image['CLI_delivery'] = consumer_delivery(record, image, owner_calls, cli_calls)
                image['product_producer'] = check_product_frame(slot, record, owner_calls)
                image['selected_triangle_counts'] = image.pop('upper_triangle_pixel_counts')
                image['sampled_triangles'] = image.pop('upper_sampled_triangles')
                image['unsampled_triangles'] = image.pop('upper_unsampled_triangles')
                image['selected_pixels'] = image.pop('upper_selected_pixels')
                image['target_object_row'] = record['object_names'].index(ORACLE.TARGET)
                image['within_object_offset'] = record['source_face_offsets'][image['target_object_row']]
                candidates[region].append(image)
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                errors.append({'region': region, 'ref': record.get('ref'), 'reason': str(error)})
    return candidates, errors


def find_image(row, frames, answer):
    literal = row['local_image_path']
    require(isinstance(literal, str) and literal in row['quote'], 'final_answer_does_not_include_claimed_path')
    path = Path(literal)
    require(path.is_absolute(), 'final_answer_PNG_path_is_not_absolute')
    # Inline Markdown links/images and Markdown reference definitions both use
    # a literal local destination. A code block or bare filename is not a link.
    escaped = re.escape(literal)
    target = rf'(?:{escaped}|<{escaped}>)'
    inline = re.search(r'\[[^\]\n]+\]\(\s*'+target+r'(?:\s+"[^"\n]*")?\s*\)', row['quote'])
    definitions = re.findall(r'^\s{0,3}\[([^\]\n]+)\]:\s*'+target+r'\s*$', answer, re.MULTILINE)
    reference = any(re.search(r'\[[^\]\n]+\]\['+re.escape(name)+r'\]', answer) for name in definitions)
    require(inline or reference, 'final_answer_has_bare_path_without_Markdown_link_or_attachment')
    match = [frame for frame in frames if path.resolve(strict=True) == Path(frame['PNG']['path'])]
    require(len(match) == 1 and match[0]['PNG'] == pin(path), 'final_path_not_one_verified_current_original_PNG')
    return match[0]


def check_pixel(row, frame):
    rc, face = row['pixel_rc'], row['current_object_local_triangle']
    require(isinstance(rc, list) and len(rc) == 2 and all(type(i) is int and i >= 0 for i in rc) and
            type(face) is int and face in frame['selected_triangle_counts'], 'pixel_coordinate_or_current_source_face_missing')
    require(all(re.search(r'(?<!\d)'+str(i)+r'(?!\d)', row['quote']) for i in {*rc, face}),
            'pixel_coordinate_or_source_triangle_not_in_literal_claim')
    with QUALIFY.np.load(frame['NPZ']['path'], allow_pickle=False) as npz:
        y, x = rc
        faces = npz['triangle_ids']
        require(y < faces.shape[0] and x < faces.shape[1] and
                faces[y,x] == frame['within_object_offset'] + face and
                npz['owners'][y,x] == frame['target_object_row'], 'claimed_pixel_not_its_reported_current_source_triangle')


def literal_numbers(quote):
    return {float(token) for token in re.findall(
        r'(?<![\w.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', quote.replace('−', '-'))}


def check_claim(item, row, answer, geometry, frames, claims):
    quote = row['quote']
    require(isinstance(quote, str) and quote.strip() and quote in answer, 'claim_quote_absent_from_actual_final')
    if item == 'nearer':
        require(row['value'] == geometry['nearer'], 'incorrect_nearer_region')
        return None
    region, criterion = item.split('.')
    shape = geometry['regions'][region]
    binary = geometry['matrix64_regions'][region]
    if criterion == 'counts':
        values = row['triangles'], row['vertices']
        require(values == (shape['triangle_count'], shape['vertex_count']) and
                all(re.search(r'(?<!\d)'+str(i)+r'(?!\d)', quote) for i in values), 'source_counts_not_current_or_literal')
    elif criterion == 'distance':
        raw = row['distance_literal']
        match = re.fullmatch(r'\d+\.(\d{6,})', raw)
        require(bool(match) and bool(re.search(r'(?<![\d.])'+re.escape(raw)+r'(?![\d.])', quote)),
                'distance_literal_requires_six_decimals')
        # Allow ordinary nearest rounding in either independently verified
        # Blender coordinate domain. Cap numerical allowance below one micron.
        allowance = max(5e-8, 0.500001*10**(-len(match.group(1))))
        require(any(abs(float(raw)-r['distance_m']) <= allowance for r in (shape,binary)), 'shortest_surface_distance_incorrect')
    elif criterion == 'direction':
        require(QUALIFY.near_point(row['world_unit_direction'], shape['direction_world'], POSITION_TOL), 'world_direction_reversed_or_invalid')
    elif criterion == 'nearest_pair':
        values = {*row['selected_point_world_m'], *row['Cube_point_world_m']}
        require(values <= literal_numbers(quote), 'nearest_point_coordinates_absent_from_original_claim')
        for domain in (shape, binary):
            try:
                QUALIFY.numeric_pair(domain['distance_m'], domain['direction_world'], row['selected_point_world_m'],
                                     row['Cube_point_world_m'], domain, POSITION_TOL)
                break
            except ValueError:
                continue
        else:
            raise ValueError('claimed_points_not_a_current_attaining_pair')
    elif criterion == 'threshold':
        require(row['at_least_0_201_m'] is shape['at_least_0_201_m'], 'incorrect_threshold_classification')
    elif criterion == 'image':
        return find_image(row, frames[region], answer)
    elif criterion == 'pixel':
        image = claims.get(region+'.image')
        require(isinstance(image, dict), 'pixel_claim_without_current_image')
        check_pixel(row, find_image(image, frames[region], answer))
    elif criterion == 'scope':
        require(row['observable_scope'] == 'actual_samples_in_one_frame' and
                row['implies_complete_visibility'] is False and row['implies_all_unsampled_are_occluded'] is False,
                'curve_single_view_visibility_overstatement')
    return None


def score_slot(slot, claim_path=None):
    slot = Path(slot).resolve(strict=True)
    result = load(slot/'SLOT_RESULT.json')
    publication = load(slot/'SLOT_PUBLICATION.json')
    require(slot.name == result['label'] == publication['label'] and
            publication['result_sha256'] == pin(slot/'SLOT_RESULT.json')['sha256'], 'actual_slot_result_unbound')
    summary = {'slot': slot.name, 'actual_status': publication['status'], 'quality_complete': False,
               'passed_items': 0, 'total_items': len(REQUIRED), 'failure_records': result.get('errors', [])}
    if result['status'] != 'completed' or publication['status'] != 'completed' or not result.get('consumer', {}).get('valid_completion'):
        return {**summary, 'final_available': False, 'unverified_items': list(REQUIRED)}
    historical, prior = historical_truth()
    geometry, terminal, device = verify_closed_source(slot, historical, prior)
    answer, final, cli_calls, stdout = verify_public_final(slot, result)
    frames, unusable = qualify_frames(slot, terminal, device, geometry, cli_calls)
    summary.update(final_available=True, answer=answer, CLI_stdout=stdout, actual_final_item=final['id'],
                   same_slot_geometry=geometry, usable_frames=frames, unusable_frames=unusable)
    if claim_path is None:
        return {**summary, 'unverified_items': list(REQUIRED), 'awaits_literal_claim_transcription': True}
    table = load(claim_path)
    require(table['answer_sha256'] == answer['sha256'] and table['slot'] == slot.name and
            set(table['claims']) <= set(REQUIRED), 'literal_claim_transcription_not_bound_to_original_answer')
    claims = table['claims']
    verdict, chosen = {}, {}
    for item in REQUIRED:
        row = claims.get(item)
        if row is None:
            verdict[item] = {'status': 'missing'}
            continue
        try:
            binding = check_claim(item, row, final['text'], geometry, frames, claims)
            if binding is not None:
                chosen[item] = binding
            verdict[item] = {'status': 'pass', 'quote': row['quote']}
        except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
            verdict[item] = {'status': 'failure', 'quote': row.get('quote'), 'reason': str(error)}
    if len(chosen) == 2 and len({frame['ref'] for frame in chosen.values()}) != 2:
        for item in chosen:
            verdict[item].update(status='failure', reason='two_regions_reused_same_frame_instead_of_two_local_originals')
    passed = sum(row['status'] == 'pass' for row in verdict.values())
    return {**summary, 'passed_items': passed, 'quality_complete': passed == len(REQUIRED),
            'claim_transcription': pin(claim_path), 'criteria': verdict, 'chosen_images': chosen}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    task = cli.add_mutually_exclusive_group(required=True)
    task.add_argument('--slot', type=Path)
    task.add_argument('--preflight', type=Path)
    cli.add_argument('--claims', type=Path)
    cli.add_argument('--output', type=Path)
    opt = cli.parse_args()
    if opt.preflight:
        preflight(opt.preflight)
    else:
        require(opt.output is not None, 'score_output_required')
        try:
            account = score_slot(opt.slot, opt.claims)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            account = {'slot': opt.slot.name, 'quality_complete': False, 'passed_items': 0,
                       'total_items': len(REQUIRED), 'unverified_items': list(REQUIRED), 'error': str(error)}
        write(opt.output, account)
        print({k: account[k] for k in ('slot', 'quality_complete', 'passed_items', 'total_items', 'error') if k in account})
        raise SystemExit(0 if account['quality_complete'] else 1)
