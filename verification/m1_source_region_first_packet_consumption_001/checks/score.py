"""Validate closed-slot answer evidence against the frozen five-item rubric."""

import argparse
import base64
import json
from pathlib import Path
import re
from runpy import run_path


HERE = Path(__file__).resolve().parent
TRUTH = run_path(str(HERE / 'truth.py'))
require, read, pin, digest = (TRUTH[name] for name in ('require', 'read', 'pin', 'digest'))


def original_final(slot):
    file = slot / 'consumer/PUBLIC_FINAL.txt'
    events = [json.loads(line) for line in (slot / 'consumer/stdout.raw.bin').read_bytes().splitlines() if line.strip()]
    completed = [event['item'] for event in events if event.get('type') == 'item.completed']
    answers = [item['text'] for item in completed if item['type'] == 'agent_message']
    require(answers and answers[-1].encode() == file.read_bytes(), 'original_final_does_not_match_raw_agent_message')
    return answers[-1], [item for item in completed if item['type'] == 'mcp_tool_call'], pin(file)


def packet_images(slot, tools):
    result = {}
    owner = [(path, read(path).get('result', {}), read(path.with_name('REQUEST.json')))
             for path in sorted((slot / 'owner').glob('tool_*/RESPONSE.json'))]
    for event in tools:
        if event.get('error'):
            continue
        blocks = (event.get('result') or {}).get('content', [])
        png = [block for block in blocks if block.get('type') == 'image' and block.get('mimeType') == 'image/png']
        if not png:
            continue
        matching = [path for path, reply, request in owner
                    if reply.get('content') == blocks and request['params']['name'] == event['tool']
                    and request['params']['arguments'] == event['arguments'] and not reply.get('isError')]
        require(matching, 'CLI_image_delivery_does_not_match_issued_owner_reply/' + event['id'])
        for block in png:
            raw = base64.b64decode(block['data'], validate=True)
            result.setdefault(digest(raw), []).append({
                'agent_tool_event': event['id'], 'owner_responses': [pin(item) for item in matching],
                'PNG_bytes': len(raw), 'block': block,
            })
    return result


def device_proof(slot, frame, current, block):
    """Confirm a delivered supported original along either arm's allowed image route."""
    file, arrays = [Path(frame[key]).resolve(strict=True) for key in ('PNG', 'NPZ')]
    require(file.is_relative_to(slot) and arrays.is_relative_to(slot), 'device_frame_outside_closed_slot')
    png, raw = file.read_bytes(), arrays.read_bytes()
    require(base64.b64decode(block['data'], validate=True) == png and digest(png) == frame['PNG_sha256']
            and len(png) == frame['PNG_bytes'] and digest(raw) == frame['NPZ_sha256'],
            'device_frame_original_bytes_or_sha_mismatch')
    provenance = {row['name']: row for row in current['objects']}
    names = frame['object_names']
    require(frame['object_ids'] == [provenance[name]['object_id'] for name in names]
            and frame['object_instance_ids'] == [provenance[name]['instance_id'] for name in names]
            and frame['display_object_mask'] == [True]*len(provenance)
            and frame['view'] == frame['pose']['name'], 'current_device_frame_source_identity_or_display_mismatch')
    geometry = TRUTH['source']()['geometry']
    details = {**TRUTH['verify_projection'](frame['pose'], geometry), **TRUTH['pixel_proof'](png, raw, names)}
    return {**details, 'origin': frame['origin'], 'image_ref': frame['ref'],
            'frame_identity': frame['frame_identity'], 'file': pin(file), 'arrays': pin(arrays)}


def final_links(text):
    for match in re.finditer(r'!?\[[^\]\r\n]*\]\((?:<([^>\r\n]+)>|([^)\r\n]+))\)', text):
        target = (match[1] or match[2]).strip()
        if target.lower().endswith('.png'):
            yield target


def qualify_images(slot, text, tools, current):
    items = packet_images(slot, tools)
    frames = read(slot / 'DEVICE_EVIDENCE.json')['frames']
    readable, errors = {}, []
    for frame in frames:
        path = Path(frame['PNG']).resolve()
        delivered = items.get(frame['PNG_sha256'])
        if not delivered:
            continue
        try:
            proof = device_proof(slot, frame, current, delivered[0]['block'])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            errors.append({'path': path.as_posix(), 'why': str(exc)})
            continue
        proof['deliveries'] = [{key: val for key, val in item.items() if key != 'block'} for item in delivered]
        readable[path] = proof
    links = []
    for target in dict.fromkeys(final_links(text)):
        path = Path(target)
        resolved = path.resolve() if path.is_absolute() else None
        found = readable.get(resolved)
        links.append({'reference_in_original': target, 'same_slot_readable_original': found is not None,
                      'after_close_disk_sha256': pin(resolved)['sha256'] if found is not None else None,
                      'view': found['view'] if found is not None else None})
    return {'current_readable_originals': list(readable.values()), 'rejected_delivered_frames': errors,
            'original_final_links': links, 'actual_attachment_renderer_and_user_click': None}


def score(slot, annotation):
    slot = Path(slot).resolve(strict=True)
    result_file = slot / 'SLOT_RESULT.json'
    result, publication = read(result_file), read(slot / 'SLOT_PUBLICATION.json')
    require(result['status'] == publication['status'] == 'completed'
            and result['model_consumers'] == 1 and result['closure_verification']['passed']
            and result['independent_before_after']['passed']
            and publication['result_sha256'] == pin(result_file)['sha256'],
            'formal_slot_is_not_completed_and_protected')
    before, after = [read(slot / name) for name in ('initial_capture/TERMINAL_SOURCE.json', 'TERMINAL_SOURCE.json')]
    independent = TRUTH['independent_math']()['verify_geometry']
    before_binding, after_binding = independent(before), independent(after)
    require(before_binding == after_binding, 'independent_scene_changed_during_slot')
    text, tools, receipt = original_final(slot)
    for label, quote in annotation['quotes'].items():
        require(quote is None or type(quote) is str and quote and quote in text,
                'annotation_must_quote_original_final/' + label)
    measure = annotation['measurement']
    a, b = measure.get('point_a'), measure.get('point_b')
    supported = TRUTH['score_measurement'](
        measure['distance_m'] if measure['distance_m'] is not None else 0,
        measure['direction'] if measure['direction'] is not None else '',
        a if a is not None else (0, 0, 0), b if b is not None else (0, 0, 0))
    if a is None or b is None:
        supported['actual_surface_points'] = False
    images = qualify_images(slot, text, tools, after)
    grades = {
        'selection_and_reference_scope': annotation['source_scope_correct'] and bool(annotation['quotes']['scope']),
        'distance_and_world_direction': supported['distance'] and supported['direction']
        and bool(annotation['quotes']['measurement']),
        'attaining_actual_surface_point_pair': supported['actual_surface_points'] and bool(annotation['quotes']['points']),
        'current_complete_readable_selection': annotation['claims_complete_readable'] and bool(annotation['quotes']['visibility'])
        and bool(images['current_readable_originals']),
        'final_same_slot_original_can_reopen': any(row['same_slot_readable_original'] for row in images['original_final_links']),
    }
    return {'slot': slot.name, 'passed': sum(grades.values()), 'planned': len(grades), 'grades': grades,
            'raw_final': receipt, 'annotation': annotation, 'measurement_proof': supported,
            'independent_initial_and_terminal': [before_binding, after_binding], 'images': images}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = score(args.slot, read(args.annotation))
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
