"""Score the selected/whole comparison against raw answers and same-slot evidence."""

import argparse
import base64
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
TRUTH = run_path(str(HERE / 'truth.py'))
PREVIOUS = run_path(str(HERE.parents[1] / 'm1_source_region_first_packet_consumption_001/checks/score.py'))
require, read, pin, digest = (TRUTH[k] for k in ('require', 'read', 'pin', 'digest'))


def audit_image(slot, device, block, scene):
    """Check either arm's bound original independently of the delivery formatter."""
    png, npz = [Path(device[key]).resolve(strict=True) for key in ('PNG', 'NPZ')]
    require(png.is_relative_to(slot) and npz.is_relative_to(slot), 'current_oracle_frame_outside_closed_slot')
    rgb, arrays = png.read_bytes(), npz.read_bytes()
    require(digest(rgb) == device['PNG_sha256'] and len(rgb) == device['PNG_bytes']
            and base64.b64decode(block['data'], validate=True) == rgb
            and digest(arrays) == device['NPZ_sha256'], 'current_delivered_png_or_npz_does_not_match_original')
    objects = {obj['name']: obj for obj in scene['objects']}
    names = device['object_names']
    require(device['object_ids'] == [objects[name]['object_id'] for name in names]
            and device['object_instance_ids'] == [objects[name]['instance_id'] for name in names]
            and device['display_object_mask'] == [True]*len(objects)
            and device['source_face_offsets'] == TRUTH['offsets'](names)
            and device['view'] == device['pose']['name'], 'device_object_source_and_view_not_currently_bound')
    proof = {**TRUTH['verify_projection'](device['pose']), **TRUTH['pixel_proof'](rgb, arrays, names)}
    return {**proof, 'origin': device['origin'], 'image': pin(png), 'arrays': pin(npz),
            'image_ref': device['ref'], 'frame_identity': device['frame_identity']}


def actual_images(slot, text, tools, scene):
    packet_images = PREVIOUS['packet_images'](slot, tools)
    frames = read(slot / 'DEVICE_EVIDENCE.json')['frames']
    supported, rejected = {}, []
    for device in frames:
        path = Path(device['PNG']).resolve()
        delivered = packet_images.get(device['PNG_sha256'])
        if not delivered:
            continue
        try:
            proof = audit_image(slot, device, delivered[0]['block'], scene)
        except (ValueError, OSError, TypeError, KeyError) as error:
            rejected.append({'path': path.as_posix(), 'reason': str(error)})
            continue
        proof['original_deliveries'] = [{k:v for k,v in item.items() if k != 'block'} for item in delivered]
        supported[path] = proof
    links = []
    for stated in dict.fromkeys(PREVIOUS['final_links'](text)):
        p = Path(stated)
        path = p.resolve() if p.is_absolute() else None
        proof = supported.get(path)
        links.append({
            'exact_answer_reference': stated,
            'same_slot_verified_readable_original': proof is not None,
            'post_close_file': pin(path) if proof is not None else None,
            'bound_image_ref': proof['image_ref'] if proof is not None else None,
        })
    return {'readable_originals': list(supported.values()), 'rejected_frames': rejected,
            'original_final_image_links': links, 'user_click_and_host_render_observed': None}


def score(slot, annotation):
    slot = Path(slot).resolve(strict=True)
    result_path = slot / 'SLOT_RESULT.json'
    result, posted = read(result_path), read(slot / 'SLOT_PUBLICATION.json')
    require(result['status'] == posted['status'] == 'completed' and result['model_consumers'] == 1
            and result['closure_verification']['passed'] and result['independent_before_after']['passed']
            and posted['result_sha256'] == pin(result_path)['sha256'], 'formal_slot_not_safely_completed')
    first, last = [read(slot / name) for name in ('initial_capture/TERMINAL_SOURCE.json', 'TERMINAL_SOURCE.json')]
    before_after = [TRUTH['verify_source'](item) for item in (first, last)]
    require(before_after[0] == before_after[1], 'formal_closed_slot_geometry_or_id_changed')
    text, tools, final = PREVIOUS['original_final'](slot)
    for label, excerpt in annotation['quotes'].items():
        require(excerpt is None or type(excerpt) is str and excerpt and excerpt in text,
                'evidence_must_be_quoted_verbatim_from_actual_final/' + label)
    measurements = {}
    for scope in ('selected', 'whole'):
        item = annotation['measurements'][scope]
        measurements[scope] = TRUTH['score_measurement'](
            scope, item['distance_m'], item['direction'], item['point_a'], item['point_b'])
    pictures = actual_images(slot, text, tools, last)
    # Distances and point witnesses are independent rubric items.
    grades = {'scope': bool(annotation['scope_correct'] and annotation['quotes']['scope'])}
    for scope, proof in measurements.items():
        grades[scope+'_distance_direction'] = bool(proof['distance_correct'] and proof['world_direction_correct']
                                                   and annotation['quotes'][scope+'_distance'])
        grades[scope+'_actual_point_pair'] = bool(proof['actual_attaining_pair'] and annotation['quotes'][scope+'_points'])
    grades['complete_readability'] = bool(annotation['claims_complete_readability']
                                          and annotation['quotes']['visibility'] and pictures['readable_originals'])
    grades['verified_original_png_in_final'] = any(
        row['same_slot_verified_readable_original'] for row in pictures['original_final_image_links'])
    return {'arm': slot.name, 'passed': sum(grades.values()), 'planned': len(grades), 'grades': grades,
            'independent_initial_terminal': before_after, 'measurements': measurements,
            'annotation': annotation, 'final_original': final, 'images': pictures}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--annotation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = score(args.slot, read(args.annotation))
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        file.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
