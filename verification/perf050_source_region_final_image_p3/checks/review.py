"""Audit what the unchanged P3 final message delivers and can actually reference."""

import argparse
import base64
import json
from pathlib import Path
import re
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
P2 = NS.parent / 'perf050_source_region_active_view_p2'
M1 = NS.parent / 'm1_source_region_final_image_001'
RUN = Path('D:/he_perf050_source_region_final_image_p3')
P2_RUN = Path('D:/he_perf050_source_region_active_view_p2')
INSTALL = M1 / 'install/PRODUCT_RUN_BINDING.json'
COMMIT = '470a36f111cd5e96845569c258f464d4bbcf2824'
SOURCE = '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7'
WHEEL = '78f9626dc30ace6523f4715512a934d1a42ddca977066a614067f3ed61586eb8'
OLD = run_path(str(P2 / 'checks/review.py'))
read, pin, digest, require = (OLD[key] for key in ('read', 'pin', 'digest', 'require'))


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


# Angle destinations are part of the local Codex Markdown file-link contract.
LINK = re.compile(r'(?<!\\)(!?)\[([^\]\n]*)\]\(\s*(?:<([^<>\n]+)>|([^\s()<>]+))'
                  r'(?:\s+"[^"\n]*")?\s*\)')
OPAQUE = re.compile(r'(?<![\w-])(?:native-image|source-region-image|active-host-image):[0-9a-f]+')
FENCES = re.compile(r'(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[^\n]*$|\Z)')
CODE = re.compile(r'(`+)[^\n]*?\1')


def final_reference_kinds(answer, known_paths):
    """Return literal authored forms; source claims or guessed images prove nothing."""
    # Remove fenced examples, then inline code for counting actual links. Inline
    # code can still carry a bare path but cannot count as a clickable link.
    prose = FENCES.sub('', answer)
    links_in = CODE.sub('', prose)
    parsed = []
    for match in LINK.finditer(links_in):
        image_mark, _, angle, plain = match.groups()
        destination = angle or plain
        kind = 'markdown_image' if image_mark else 'markdown_link'
        if re.match(r'^[a-zA-Z]:[/\\]|^/(?!/)', destination):
            parsed.append({'kind': kind, 'destination': destination, 'local_markdown': True})
        elif destination.startswith(('file:', 'sandbox:')):
            parsed.append({'kind': kind, 'destination': destination, 'local_markdown': False,
                           'reason': 'has_URI_scheme_instead_of_local_path'})
        elif OPAQUE.fullmatch(destination):
            parsed.append({'kind': 'opaque_' + kind, 'destination': destination, 'local_markdown': False})
    remainder = LINK.sub('', prose)
    for path in sorted(set(known_paths)):
        spellings = {path, path.replace('\\', '/'), path.replace('/', '\\')}
        if any(re.search(r'(?<![\w/\\])' + re.escape(item) + r'(?![\w/\\.-])', remainder,
                         flags=re.IGNORECASE) for item in spellings):
            parsed.append({'kind': 'bare_path', 'destination': path, 'local_markdown': False})
    parsed.extend({'kind': 'bare_opaque_ref', 'destination': item, 'local_markdown': False}
                  for item in dict.fromkeys(OPAQUE.findall(remainder)))
    return parsed


def final_item(slot):
    saved = slot / 'consumer/PUBLIC_FINAL.txt'
    if not saved.is_file():
        return '', None, []
    answer = saved.read_bytes()
    raw, timed = (slot / 'consumer'/name for name in ('stdout.raw.bin', 'events.jsonl'))

    def candidates(events):
        return [event['item'] for event in events if event.get('type') == 'item.completed'
                and event.get('item', {}).get('type') == 'agent_message']

    stdout = candidates(lines(raw))
    log = candidates(row['event'] for row in lines(timed))
    require(stdout and stdout == log and stdout[-1].get('text', '').encode() == answer,
            'raw_final_agent_message_public_answer_or_timed_event_changed')
    item = stdout[-1]
    attachments = []
    for key in ('content', 'images', 'attachments'):
        for block in item.get(key) or []:
            if not isinstance(block, dict) or block.get('type') not in ('image', 'image_url', 'attachment',
                                                                      'file', 'output_image'):
                continue
            raw_digest = None
            payload = block.get('data')
            if isinstance(payload, str):
                try:
                    data = base64.b64decode(payload, validate=True)
                except ValueError:
                    data = b''
                if data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raw_digest = digest(data)
            attachments.append({'kind': 'structured_media', 'field': key,
                                'destination': block.get('path') or block.get('url'),
                                'PNG_sha256': raw_digest, 'local_markdown': False})
    return answer.decode(), {'answer': pin(saved), 'raw_stdout': pin(raw), 'timed_events': pin(timed),
                             'id': item.get('id'), 'fields': list(item)}, attachments


def collect_images(attempts):
    delivery = {}
    for row in attempts:
        original = row['wire_content']['PNG']
        if row.get('CLI_binding') == 'content_and_envelope_match' and row.get('CLI_delivered_images') == len(original):
            for image in original:
                delivery.setdefault(image['sha256'], []).append(row['attempt'])
    return delivery


def fixed_install():
    install = read(INSTALL)
    require((install['preparation_git'], install['source_sha256'], install['wheel_sha256'],
             len(install['source_manifest'])) == (COMMIT, SOURCE, WHEEL, 143),
            'fixed_candidate_identity_changed')
    return install


def candidate_field(product, slot, config, frame):
    """A path may be counted only if the actual same-run PNG leave is verified."""
    offered = [item for item in product.get('images', []) if 'local_image_path' in item]
    if not offered:
        return None
    entry = {'attempt': product['attempt'], 'verified': False, 'fields': offered}
    if len(offered) != 1 or product.get('schema') != 'source-region-brief-v3':
        return {**entry, 'reason': 'not_one_successful_source_region_brief_field'}
    image = offered[0]
    entry.update(path=image['local_image_path'], PNG_sha256=image['image_sha256'], ref=image['image_ref'])
    state = Path(config['state_file'])
    source_root = state.with_name(state.name + '.source_region')
    path = Path(image['local_image_path'])
    witness = product.get('complete_witness')
    qualifies = (product['witness_targets_frozen_region'] and witness and frame is not None and frame['qualifies']
                 and frame['surface_pixels'] == witness['selected_surface_pixels']
                 and frame['contrasting_boundary_pixels'] == witness['contrasting_boundary_pixels'])
    if (not qualifies or not product['delivered_to_CLI'] or product['attempt'] not in frame['delivered_in_attempts']
            or not state.is_absolute() or state.resolve() == slot.resolve()
            or not state.resolve().is_relative_to(slot.resolve()) or config['expected_identity']['source_sha256'] != SOURCE
            or not path.is_absolute() or not path.is_relative_to(source_root)
            or len(path.relative_to(source_root).parts) != 2 or path.resolve(strict=True) != path
            or not path.is_file() or Path(frame['native_PNG']).resolve() != path
            or frame['PNG_sha256'] != image['image_sha256'] or frame['ref'] != image['image_ref']):
        return {**entry, 'reason': 'unverified_current_slot_scope_frame_or_CLI_delivery'}
    producer = read(slot / 'owner' / f"tool_{product['attempt']:02d}" / 'PRODUCT_RESPONSE.json')
    block = producer['result']['content'][image['image_block_index']]
    raw = base64.b64decode(block['data'], validate=True)
    require(path.read_bytes() == raw, 'candidate_path_and_actual_delivered_block_differ')
    return {**entry, 'verified': True, 'matching_bytes': len(raw),
            'frame_identity': image['frame_identity'], 'image_block_index': image['image_block_index']}


def full_path(product, slot, frame, delivery):
    """Record the original full-form route to the path independently of the new field."""
    if (not product.get('delivered_to_CLI') or product.get('schema') in
            ('source-region-brief-v2', 'source-region-brief-v3') or
            not product.get('witness_targets_frozen_region') or frame is None or
            frame['qualifies'] is not True):
        return None
    p = slot / 'owner' / f"tool_{product['attempt']:02d}" / 'PRODUCT_RESPONSE.json'
    body = OLD['response_body'](read(p)['result'])
    originals = [f for f in body.get('frames', []) if f['image_ref'] == frame['ref'] and
                 f['image_sha256'] == frame['PNG_sha256']]
    if len(originals) != 1 or product['attempt'] not in delivery.get(frame['PNG_sha256'], []):
        return None
    path = Path(originals[0]['image_path'])
    if not path.is_absolute() or not path.is_relative_to(slot) or path != Path(frame['native_PNG']):
        return None
    return {'attempt': product['attempt'], 'path': path.as_posix(), 'ref': frame['ref'],
            'PNG_sha256': frame['PNG_sha256']}


def match_final_reference(row, slot, frames, known_fields, full_paths=()):
    verified = [frame for frame in frames if frame.get('qualifies') and frame.get('delivered_in_attempts')]
    aliases = [frame for frame in verified if frame.get('ref') == row.get('destination')]
    if aliases:
        return {**row, 'archival_ref_matches': [f['ref'] for f in aliases], 'eligible_for_local_reopen': False}
    if row['kind'] == 'structured_media' and row.get('PNG_sha256'):
        matches = [frame for frame in verified if frame['PNG_sha256'] == row['PNG_sha256']]
        return {**row, 'verified_same_slot_media': bool(matches),
                'matching_refs': [frame['ref'] for frame in matches], 'eligible_for_local_reopen': False}
    destination = row.get('destination')
    if not isinstance(destination, str) or not Path(destination).is_absolute() or destination.startswith(('//', '\\\\')):
        return {**row, 'eligible_for_local_reopen': False}
    path = Path(destination)
    if not path.is_relative_to(slot.resolve()) or '..' in path.parts:
        return {**row, 'eligible_for_local_reopen': False, 'reason': 'foreign_or_traversing_final_path'}
    matches = [frame for frame in verified if frame.get('native_PNG') and path == Path(frame['native_PNG'])]
    if len(matches) != 1:
        return {**row, 'eligible_for_local_reopen': False, 'reason': 'no_unique_complete_delivered_frame'}
    frame, = matches
    field_attempts = [item['attempt'] for item in known_fields if item['verified'] and Path(item['path']) == path and
                      item['ref'] == frame['ref']]
    full_attempts = [item['attempt'] for item in full_paths if Path(item['path']) == path and item['ref'] == frame['ref']]
    return {**row, 'same_slot_delivered_qualified_frame': True,
            'frame_ref': frame['ref'], 'expected_original_PNG_sha256': frame['PNG_sha256'],
            'delivery_attempts': frame['delivered_in_attempts'],
            'matches_candidate_field_attempts': field_attempts, 'matches_existing_full_path_attempts': full_attempts,
            'candidate_field_first_observed_path_exposure': bool(
                field_attempts and not any(when <= min(field_attempts) for when in full_attempts)),
            'eligible_for_local_reopen': row['local_markdown'] or row['kind'] == 'structured_media'}


def preflight():
    original_pins, pilot = OLD['check_archived_pilot']()
    active_pins, active = OLD['check_archived_active']()
    install = fixed_install()
    verify = read(M1 / 'checks/WIRE_AUDIT.json')
    replay = read(M1 / 'checks/SERIALIZER.json')
    host = read(M1 / 'checks/HOST_OPEN.json')
    require(verify['passed'] is True and verify['P2']['historical_score'] == [4, 5]
            and replay['passed'] is True and replay['candidate_runtime_source_sha256'] == SOURCE
            and host['actual_file_open']['passed'] is True, 'accepted_M1_evidence_changed')
    p2slot = P2_RUN / 'slots/P2'
    prior_index = P2 / 'RUNTIME_INDEX.json'
    history = OLD['Originals'](P2_RUN, prior_index,
                               'befd9d28399e6a2a06b89626d221684433050fda01422d1552a7b05eafde4aa5', 338)
    try:
        for name in ('consumer/stdout.raw.bin', 'consumer/events.jsonl', 'consumer/PUBLIC_FINAL.txt', 'SLOT_RESULT.json',
                     'SLOT_PUBLICATION.json'):
            history.member('slots/P2/' + name)
        answer, message, media = final_item(p2slot)
        require(message and message['answer']['bytes'] == 1031 and
                message['answer']['sha256'] == verify['P2']['historical_final_sha256']
                and not final_reference_kinds(answer, []) and not media, 'historical_P2_final_handoff_changed')
        closed = history.json('slots/P2/SLOT_PUBLICATION.json')
        result = history.json('slots/P2/SLOT_RESULT.json')
        require(closed['result_sha256'] == verify['P2']['published_original_result_sha256']
                and closed['status'] == result['status'] == 'completed', 'historical_P2_closure_changed')
        fixture = host['selected_original']['path']
        original = history.member(Path(fixture).relative_to(P2_RUN).as_posix())
        require(digest(original) == host['selected_original']['sha256'] and len(original) == 2870,
                'historical_original_pixels_changed')
        for row in replay['cold_and_hot'].values():
            require(row['path'] == fixture and row['original_PNG_sha256'] == digest(original)
                    and row['fixed_CLI']['passed'] is True, 'accepted_M1_local_path_or_fixed_CLI_changed')
        control = {'markdown_image': (f'![RIGHT](<{fixture}>)', 'markdown_image', True),
                   'markdown_link': (f'[Original]({fixture})', 'markdown_link', True),
                   'bare_path': ('`' + fixture + '`', 'bare_path', False),
                   'opaque_link': ('[RIGHT](source-region-image:0123)', 'opaque_markdown_link', False),
                   'file_uri': (f'[RIGHT](file:///{fixture})', 'markdown_link', False)}
        for name, (text, kind, eligible) in control.items():
            classified, = final_reference_kinds(text, [fixture])
            require(classified['kind'] == kind and classified['local_markdown'] is eligible,
                    'reference_parser_control_failed/' + name)
        require(not final_reference_kinds('```md\n[RIGHT](<' + fixture + '>)\n```', [fixture])
                and not final_reference_kinds('见所附 RIGHT 原图', [fixture]), 'code_or_unbacked_claim_counted_as_image')
        frame = {'ref': 'source-region-image:0123', 'native_PNG': fixture, 'qualifies': True,
                 'delivered_in_attempts': [6], 'PNG_sha256': digest(original)}
        row, = final_reference_kinds(f'[RIGHT](<{fixture}>)', [fixture])
        checked = match_final_reference(row, p2slot, [frame], [])
        require(checked['eligible_for_local_reopen'] is True and
                match_final_reference(row, p2slot / 'different_slot', [frame], [])['eligible_for_local_reopen'] is False,
                'local_reopen_control_not_bound_to_slot')
        candidate = {'attempt': 6, 'path': fixture, 'ref': frame['ref'], 'verified': True}
        earlier_full = {'attempt': 4, 'path': fixture, 'ref': frame['ref']}
        same = match_final_reference(row, p2slot, [frame], [candidate], [earlier_full])
        require(same['matches_candidate_field_attempts'] == [6] and same['matches_existing_full_path_attempts'] == [4]
                and same['candidate_field_first_observed_path_exposure'] is False,
                'path_match_must_not_be_confused_with_first_exposure')
        staged = [*original_pins, *active_pins, *history.pins]
    finally:
        history.close()
    extra = [Path(__file__), P2 / 'checks/review.py', P2 / 'QUALITY.json', INSTALL,
             Path(install['wheel_path']), M1 / 'FROZEN.json', M1 / 'checks/WIRE_AUDIT.json',
             M1 / 'checks/HOST_OPEN.json', M1 / 'checks/SERIALIZER.json']
    pins = {item['path']: item for item in (*staged, *map(pin, extra))}
    return {'schema': 'perf050-source-region-final-image-p3-review-preflight-v1', 'passed': True,
            'historical_pilot': pilot, 'historical_engineering': active, 'historical_P2_quality': [4, 5],
            'actual_historical_P2_no_final_image': True, 'M1_positive_replays': len(replay['cold_and_hot']),
            'parser_controls': [*control, 'fenced_markdown', 'unsupported_prose_claim', 'same_slot', 'other_slot',
                                'existing_full_path_before_candidate'],
            'source_pins': list(pins.values())}


def review(run, costs_path):
    costs = read(costs_path)
    arm, = (row for row in costs['slots'] if row['label'] == 'P3')
    slot = run.resolve() / 'slots/P3'
    out = {'schema': 'perf050-source-region-final-image-p3-evidence-v1',
           'costs_sha256': pin(costs_path)['sha256'], 'status': arm['status'],
           'historical_denominator_excluded': True, 'frames': [], 'product_attempts': [],
           'candidate_field_arrivals': [], 'existing_full_path_arrivals': [], 'final_reference_forms': [],
           'eligible_final_local_reopens': [],
           'whole_object_proximity_attempts': [], 'verified_final_agent_message': None}
    if not slot.is_dir():
        require(arm['status'] == 'unrun', 'unexpected_record_for_unrun_slot')
        return out
    result, publication = slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'
    if result.is_file() and publication.is_file():
        state, closed = read(result), read(publication)
        require(pin(result)['sha256'] == closed['result_sha256'] and
                (state['group'], state['slot'], closed['slot']) == ('P', 'P3', 'P3') and
                state['asset_sha256'] == OLD['ASSET'], 'live_P3_publication_changed')
        out['published_status'] = closed['status']
        out['published_result_sha256'] = closed['result_sha256']
        out['slot_closed'] = (state.get('closure_verification') or {}).get('passed') is True
    install = fixed_install()
    sys.path.insert(0, install['dependency_root'])
    oracle = run_path(str(OLD['PILOT'] / 'truth/oracle.py'))
    image = run_path(str(OLD['PILOT'] / 'quality_images.py'))
    truth = read(OLD['TRUTH'])
    attempts = arm.get('actual_requests', [])
    delivery = collect_images(attempts)
    evidence = slot / 'DEVICE_EVIDENCE.json'
    by_ref = {}
    for frame in read(evidence)['frames'] if evidence.is_file() else []:
        try:
            checked = image['inspect_frame'](slot, frame, truth, delivery, oracle)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            checked = {'ref': frame.get('ref'), 'view': frame.get('view'), 'origin': frame.get('origin'),
                       'qualifies': False, 'error': str(exc)}
        if checked['ref'] in by_ref:
            by_ref[checked['ref']] = None
        else:
            by_ref[checked['ref']] = checked
        out['frames'].append(checked)
    config = read(slot / 'PRODUCT_CONFIG.json') if (slot / 'PRODUCT_CONFIG.json').is_file() else {}
    for attempt in attempts:
        try:
            product = OLD['product_attempt'](attempt, slot)
            if product is None:
                continue
            witness = product.get('complete_witness') or {}
            field = candidate_field(product, slot, config, by_ref.get(witness.get('image_ref')))
            if field is not None:
                out['candidate_field_arrivals'].append(field)
            path = full_path(product, slot, by_ref.get(witness.get('image_ref')), delivery)
            if path is not None:
                out['existing_full_path_arrivals'].append(path)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            product = {'attempt': attempt['attempt'], 'outcome': 'evidence_binding_error', 'error': str(exc)}
        out['product_attempts'].append(product)
    fields, full = out['candidate_field_arrivals'], out['existing_full_path_arrivals']
    answer, message, attachments = final_item(slot)
    out['verified_final_agent_message'] = message
    out['normal_initial_prompt'] = arm.get('initial_prompt_sha256') == OLD['PROMPT_SHA']
    inputs = [item['path'] for item in fields if item.get('verified')] + [item['path'] for item in full]
    references = final_reference_kinds(answer, inputs) + attachments
    reports = [match_final_reference(row, slot, out['frames'], fields, full) for row in references]
    out['final_reference_forms'] = reports
    out['eligible_final_local_reopens'] = [row for row in reports if row['eligible_for_local_reopen']]
    out['whole_object_proximity_attempts'] = [
        item['attempt'] for item in out['product_attempts'] if item.get('delivered_to_CLI') and
        any(f['scope'] == 'whole_objects' and set(f['objects']) == {'N15', 'N23'}
            and (f.get('proximity') or {}).get('status') == 'measured' for f in item['measurements'])]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--costs', type=Path, default=NS / 'consumer/COSTS.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_interpreter_required')
    data = preflight() if args.preflight else review(args.run, args.costs)
    output = args.output or HERE / ('PREFLIGHT.json' if args.preflight else 'P3_EVIDENCE.json')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(output, pin(output)['sha256'], data.get('passed', data.get('status')))


if __name__ == '__main__':
    main()
