"""Score the two surface scopes and partial image against closed raw slots."""

import argparse
import base64
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
TRUTH = run_path(str(HERE/'truth.py'))
ORIGINAL = run_path(str(HERE.parents[1]/'m1_source_region_first_packet_consumption_001/checks/score.py'))
require,read,pin,digest = (TRUTH[name] for name in ('require','read','pin','digest'))


def audit_image(slot,frame,block,current):
    png,buffer = [Path(frame[key]).resolve(strict=True) for key in ('PNG','NPZ')]
    require(png.is_relative_to(slot) and buffer.is_relative_to(slot),'verified_current_image_is_outside_closed_slot')
    raw,arrays = png.read_bytes(),buffer.read_bytes()
    require(frame['PNG_sha256'] == digest(raw) and len(raw) == frame['PNG_bytes']
            and base64.b64decode(block['data'],validate=True) == raw
            and frame['NPZ_sha256'] == digest(arrays),'image_content_block_file_or_companion_array_differs')
    names = frame['object_names']
    by_name = {row['name']:row for row in current['objects']}
    require(frame['object_ids'] == [by_name[name]['object_id'] for name in names]
            and frame['object_instance_ids'] == [by_name[name]['instance_id'] for name in names]
            and frame['display_object_mask'] == [True]*len(by_name)
            and frame['source_face_offsets'] == TRUTH['offsets'](names)
            and frame['view'] == frame['pose']['name'],'archive_current_image_owner_or_view_does_not_match')
    pixel = TRUTH['pixel_proof'](raw,arrays,names)
    geometric = TRUTH['projection_proof'](frame['pose'])
    return {**pixel,**geometric,'useful_partial_image':bool(pixel['side_pixels'] and geometric['side_clear_geometry_candidate']),
            'PNG':pin(png),'NPZ':pin(buffer),'origin':frame['origin'],
            'image_ref':frame['ref'],'frame_identity':frame['frame_identity']}


def images(slot,text,tools,current):
    deliveries = ORIGINAL['packet_images'](slot,tools)
    proof_by_path,rejected = {},[]
    for frame in read(slot/'DEVICE_EVIDENCE.json')['frames']:
        hits = deliveries.get(frame['PNG_sha256'])
        if not hits:
            continue
        try:
            proof = audit_image(slot,frame,hits[0]['block'],current)
        except (KeyError,TypeError,OSError,ValueError) as e:
            rejected.append({'declared_path':frame['PNG'],'argument':str(e)})
            continue
        proof['actual_deliveries'] = [{k:v for k,v in row.items() if k!='block'} for row in hits]
        proof_by_path[Path(proof['PNG']['path'])] = proof
    links = []
    for target in dict.fromkeys(ORIGINAL['final_links'](text)):
        path = Path(target)
        resolved = path.resolve() if path.is_absolute() else None
        hit = proof_by_path.get(resolved)
        useful = hit is not None and hit['useful_partial_image']
        links.append({'reference_from_original_final':target,
                      'post_close_read':pin(resolved) if useful else None,
                      'matched_current_useful_partial_image':useful,
                      'frame_identity':hit['frame_identity'] if useful else None})
    return {'current_frames':list(proof_by_path.values()),'failed_frame_controls':rejected,'explicit_final_image_links':links,
            'host_render_or_user_click_observed':None}


def actual_visibility(annotation,frames):
    claim = annotation['visibility_claim']
    # Acknowledging a supported insufficiency is allowed, but an observation that
    # actually contains side pixels should be described as that partial result.
    useful = [frame for frame in frames if frame['useful_partial_image']]
    base = bool(claim['separates_face_groups'] and claim['limits_full_selection'] and not claim['asserts_all_four_fully_visible'])
    matching = []
    if useful:
        for frame in useful:
            counts = frame['pixels_by_evaluated_triangle']
            if (claim['reports_side_samples'] and (claim.get('view') in (None,frame['view']))
                    and all(counts[str(i)] > 0 for i in claim.get('claimed_visible_faces',()))
                    and all(counts[str(i)] == 0 for i in claim.get('claimed_no_sample_faces',()))):
                matching.append(frame['frame_identity'])
        observation = bool(matching)
    else:
        observation = bool(claim['explains_evidence_limit_when_insufficient'] and not claim['reports_side_samples'])
    return {'passed':base and observation,'partial_frame_evidence_count':len(useful),'matching_frame_ids':matching,
            'entire_selected_surface_verified_visible':False}


def score(slot,annotation):
    slot = Path(slot).resolve(strict=True)
    result_path = slot/'SLOT_RESULT.json'
    result,publication = read(result_path),read(slot/'SLOT_PUBLICATION.json')
    require(result['status'] == publication['status'] == 'completed' and result['model_consumers'] == 1
            and result['closure_verification']['passed'] and result['independent_before_after']['passed']
            and publication['result_sha256'] == pin(result_path)['sha256'],'formal_slot_not_safely_completed')
    before,after = [read(slot/name) for name in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json')]
    independent = [TRUTH['verify_source'](packet) for packet in (before,after)]
    require(independent[0] == independent[1],'actual_geometry_or_object_id_changed_during_slot')
    text,tools,final = ORIGINAL['original_final'](slot)
    for name,quote in annotation['quotes'].items():
        require(quote is None or type(quote) is str and quote and quote in text,'annotation_not_verbatim_original/'+name)
    numerical = {scope:TRUTH['score_measurement'](scope,row['distance_m'],row['point_a'],row['point_b'])
                 for scope,row in annotation['measurements'].items()}
    require(set(numerical) == {'selected','whole'},'missing_or_duplicate_scope_in_answer_annotation')
    observed = images(slot,text,tools,after)
    field = actual_visibility(annotation,observed['current_frames'])
    grades = {'scopes':bool(annotation['scopes_correct'] and annotation['quotes']['scope'])}
    for scope,proof in numerical.items():
        grades[scope+'_distance'] = bool(proof['distance_correct'] and annotation['quotes'][scope+'_distance'])
        grades[scope+'_point_pair'] = bool(proof['actual_attaining_pair'] and annotation['quotes'][scope+'_points'])
    grades['partial_visibility_with_full_selection_limit'] = bool(field['passed'] and annotation['quotes']['visibility'])
    grades['original_png_link_reopened'] = any(item['matched_current_useful_partial_image']
                                               for item in observed['explicit_final_image_links'])
    return {'slot':slot.name,'scores':grades,'passed':sum(grades.values()),'planned':len(grades),
            'original_final':final,'measurement_proofs':numerical,'visibility_scope':field,
            'actual_original_evidence':observed,'independent_initial_and_terminal':independent,'annotation':annotation}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot',type=Path,required=True)
    parser.add_argument('--annotation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = score(args.slot,read(args.annotation))
    with args.output.open('x',encoding='utf-8',newline='\n') as destination:
        destination.write(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
