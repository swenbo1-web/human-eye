"""Exercise grade gates without creating a Blender process or model request."""

from copy import deepcopy
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
score = runpy.run_path(str(HERE / 'score.py'))
require = score['require']


def grade_controls(truth, sizes):
    answer_lines, claim_rows, frames, pairs, blockers = [], [], {}, [], []
    for index, target in enumerate(truth['eligible']):
        name = target['object_name']
        source = target['source_triangle_indices']
        center, normal = target['center_world_m'], target['unit_normal']
        label = score['region_label']((name, tuple(source)))
        copy = f'{name} triangles {source}, center {center} m, world unit normal {normal}'
        if target['eligible_complete_views']:
            ref, direction = 'synthetic-ref-' + str(index), target['eligible_complete_views'][0]
            outcome_quote = f'{direction} complete: {ref}'
            outcome = {'kind': 'witness', 'ref': ref, 'direction': direction, 'quote': outcome_quote}
            frames[ref] = {'view': direction, 'witnesses': {label: {'qualifies': True}},
                           'delivery': [{'origin': 'product', 'attempt': 1}]}
            pairs.append({'object_name': name, 'quote': f'{name} opposite world X ends'})
        else:
            direction = 'LEFT'
            hit = target['finite_direction_proofs'][direction]['positive_area_occluders'][0]
            blocker, triangle = hit['object_name'], hit['source_triangle_index']
            outcome_quote = f'{direction}: blocker {blocker} triangle {triangle}'
            outcome = {'kind': 'geometric_occlusion', 'direction': direction, 'quote': outcome_quote,
                       'blocker_object_name': blocker, 'source_triangle_index': triangle}
            blockers.append({'region': label, 'view': direction, 'blocker_object_name': blocker,
                             'source_triangle_index': triangle,
                             'projected_target_plane_area_m2_exact': hit['projected_target_plane_area_m2_exact']})
        answer_lines.append(copy + '\n' + outcome_quote)
        claim_rows.append({'object_name': name, 'source_triangle_indices': source,
                           'center_world_m': center, 'unit_normal': normal, 'quote': copy, 'outcome': outcome})

    answer = '\n'.join(answer_lines + [row['quote'] for row in pairs])
    digest = score['digest'](answer.encode())
    record = {'slot': 'B1', 'arm': 'B', 'status': 'completed', 'answer_sha256': digest,
              'current_read_only': {'synthetic': True}, 'first_actual_tool_is_frozen_brief': True,
              'frames': frames, 'tools': {'attempts': [{'attempt': 1, 'fixed_CLI_whole_content': True,
                  'regions': [], 'validated_blockers': blockers}]}}
    claims = {'answer_sha256': digest, 'rows': claim_rows, 'pairs': pairs, 'extra_assertions': []}

    def grade(res=record, notes=claims, raw=answer):
        return score['grade_slot'](res, notes, raw, truth, sizes)

    resolved = grade()
    require(resolved['passed_quality'] and resolved['blocker_facts_adopted'], 'intact_synthetic_proof_failed')
    independent_only = deepcopy(record)
    independent_only['tools']['attempts'][0]['validated_blockers'].pop()
    actual = grade(independent_only)
    require(actual['passed_quality'] and not actual['blocker_facts_adopted'], 'quality_conflated_with_candidate_use')
    reframed = deepcopy(record)
    reframed['frames'].pop(next(iter(frames)))
    require(not grade(reframed)['passed_quality'], 'absent_same_slot_image_accepted')
    invalid = deepcopy(claims)
    invalid['rows'][0]['unit_normal'] = [-1, 0, 0]
    require(not grade(notes=invalid)['passed_quality'], 'opposite_oriented_normal_accepted')
    invalid = deepcopy(claims)
    invalid['pairs'].pop()
    require(not grade(notes=invalid)['passed_quality'], 'missing_pair_accepted')
    invalid = deepcopy(claims)
    invalid['rows'].append(claim_rows[0])
    require(not grade(notes=invalid)['passed_quality'], 'duplicate_region_accepted')
    invalid = deepcopy(claims)
    negative = next(row for row in invalid['rows'] if row['unit_normal'][0] == -1)
    negative['outcome']['source_triangle_index'] = 100
    require(not grade(notes=invalid)['passed_quality'], 'unproven_source_triangle_accepted')
    negative['outcome']['source_triangle_index'] = True
    require(not grade(notes=invalid)['passed_quality'], 'boolean_source_triangle_accepted')
    negative['outcome']['claims_all_pixels_hidden'] = True
    require(not grade(notes=invalid)['passed_quality'], 'unsupported_total_occlusion_accepted')
    target = next(row for row in truth['eligible'] if row['unit_normal'][0] == -1)
    alternate = target['finite_direction_proofs']['LEFT']['positive_area_occluders'][1]
    require(score['independent_hit'](target, 'LEFT', alternate['object_name'], alternate['source_triangle_index']) > 0,
            'independently_proven_alternative_blocker_rejected')
    unparseable = deepcopy(claims)
    unparseable['rows'][0]['source_triangle_indices'] = [False, 7]
    require(not grade(notes=unparseable)['passed_quality'], 'bad_source_index_type_accepted')
    bad_status = {**record, 'status': 'failed'}
    require(not grade(bad_status)['passed_quality'], 'failed_lifecycle_counted_as_complete')
    print('Bound manual grade and alternatives: passed')


def retained_pixels(truth):
    installed = score['read'](score['BINDINGS']['A'])
    sys.path.insert(0, installed['dependency_root'])
    slot = score['SOURCE'].parent
    packet, _ = score['current_source'](slot, score['read'](slot / 'SLOT_RESULT.json'))
    frames = score['read'](slot / 'DEVICE_EVIDENCE.json')['frames']
    scene, = [frame for frame in frames if frame['view'] == 'SCENE' and frame['scope_id'] == 'global']
    witness = score['inspect_frame'](slot, scene, packet, truth)['witnesses']
    actual = {(row['surface_pixels'], row['contrasting_boundary_pixels'], row['geometrically_clear'], row['qualifies'])
              for row in witness.values() if row['geometrically_clear']}
    require(actual == {(11, 6, True, False), (10, 3, True, False)}, 'retained_scene_pixel_bounds_differ')
    print('Retained same-source global PNG/NPZ and two expected shortfalls: passed')


if __name__ == '__main__':
    truth = score['rail_truth']()
    source = score['read'](score['SOURCE'])
    grade_controls(truth, {row['name']: len(row['evaluated']['triangles']) for row in source['objects']})
    retained_pixels(truth)
