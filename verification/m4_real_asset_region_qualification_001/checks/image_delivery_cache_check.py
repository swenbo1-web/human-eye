"""Cross-check original image delivery and saved-frame reuse across both sessions."""

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import image_check


def review(run_root):
    audit = image_check.Audit()
    audit.file(__file__)
    root = Path(run_root).resolve()

    def full(session, call_index):
        calls = [json.loads(line) for line in audit.file(root / session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
        record = calls[call_index - 1]['producer_archive']
        return audit.read(record['path'], record['sha256'], root / session)

    first, repeat = full('main', 1), full('main', 2)
    for field in ('binding', 'region_ref', 'frames', 'facts', 'source_mapping', 'generation_work'):
        audit.check(first[field] == repeat[field], 'same_region_repeat_exact_' + field)
    audit.check(first['work']['raster_attempts'] == first['work']['raster_completed'] == 1,
                'main_first_exactly_one_raster')
    work = repeat['work']
    audit.check(work['prepare_cache_hit'] is True and work['frame_reuses'] == 1
                and work['task_query']['result_cache_hit'] is True, 'main_repeat_prepare_frame_measurement_cache_reuse')
    for field in ('prepare_calls', 'geometry_normalization_calls', 'region_array_preparation_calls',
                  'camera_preparation_calls', 'raster_attempts', 'raster_completed', 'PNG_bytes', 'NPZ_bytes',
                  'array_payload_bytes', 'temporary_encoded_archive_bytes', 'frame_array_decodes'):
        audit.check(work[field] == 0, 'main_repeat_zero_' + field)

    states = [full('state', index) for index in (1, 3, 5)]
    references = [state['region_ref'] for state in states]
    audit.check(len({row['region_id'] for row in references}) == 3,
                'initial_moved_restored_distinct_current_region_identities')
    audit.check(len({state['binding']['binding_sha256'] for state in states}) == 3,
                'initial_moved_restored_distinct_current_host_bindings')
    audit.check(len({state['frames'][0]['image_ref'] for state in states}) == 3,
                'initial_moved_restored_distinct_current_public_image_references')
    audit.check(references[0]['ordered_geometry_sha256'] == references[2]['ordered_geometry_sha256']
                and references[0]['ordered_geometry_sha256'] != references[1]['ordered_geometry_sha256'],
                'restored_geometry_equal_original_and_distinct_from_moved')
    initial_frame, moved_frame, restored_frame = [state['frames'][0] for state in states]
    audit.check(initial_frame['image_sha256'] == moved_frame['image_sha256'] == restored_frame['image_sha256'],
                'fully_occluded_selected_region_same_delivered_RGB_bytes_after_move_and_restore')
    audit.check(initial_frame['arrays_sha256'] == restored_frame['arrays_sha256']
                and moved_frame['arrays_sha256'] != initial_frame['arrays_sha256'],
                'saved_depth_owner_bundle_changes_with_moved_camera_and_restores_exactly')
    audit.check(initial_frame['frame_identity'] == restored_frame['frame_identity']
                and initial_frame['frame_identity'] != moved_frame['frame_identity'],
                'geometry_camera_frame_identity_restores_and_current_region_reference_stays_fresh')
    for state in states:
        audit.check(state['work']['raster_attempts'] == state['work']['raster_completed'] == 1
                    and state['work']['prepare_cache_hit'] is False, 'state_fresh_selection_one_current_raster')
    raster_total = first['work']['raster_attempts'] + repeat['work']['raster_attempts'] + sum(state['work']['raster_attempts'] for state in states)
    audit.check(raster_total == 4, 'both_sessions_total_four_rasters')

    names = ['MAIN_INITIAL_IMAGE_REVIEW.json', 'MAIN_REPEAT_IMAGE_REVIEW.json',
             'STATE_INITIAL_IMAGE_REVIEW.json', 'STATE_MOVED_IMAGE_REVIEW.json', 'STATE_RESTORED_IMAGE_REVIEW.json']
    reviews = [audit.read(image_check.HERE / name) for name in names]
    for report in reviews:
        audit.check(report['passed_checked_scope'] and report['original_public_delivery_checked'],
                    'separate_all_pixel_and_nearest_ray_review_passed_original_public_delivery')
        audit.check(report['selected_region_image_evidence'] == 'unknown'
                    and report['frames'][0]['selected_surface_pixels'] == 0,
                    'selected_region_zero_pixels_image_evidence_unknown')
        frame = report['frames'][0]
        audit.check(frame['visible_object_pixel_counts']['Cube'] == 511 * 511
                    and sum(frame['visible_object_pixel_counts'].values()) == 511 * 511,
                    'all_actual_foreground_pixels_are_Cube')
        cube_proofs = frame['occluder_diagnosis']['closed_AABB_containment_proofs']
        audit.check(any(proof['object_name'] == 'Cube' and proof['original_hide_render'] is True
                        and proof['all_selected_continuous_triangle_surfaces_occluded_by_this_object']
                        for proof in cube_proofs), 'hidden_render_Cube_full_selected_surface_occlusion_proved')
    source_pixels = sum(report['frames'][0]['full_image_source_pixel_review']['checked_source_memberships'] for report in reviews)
    nearest_rays = sum(report['frames'][0]['sampled_nearest_scene_review']['deduplicated_samples'] for report in reviews)
    centroid_rays = sum(report['frames'][0]['occluder_diagnosis']['centroid_sample_count'] for report in reviews)
    return dict(schema='m4-real-asset-image-delivery-cache-review-v1', passed_checked_scope=True,
        original_public_deliveries_checked=5, independent_all_foreground_source_memberships=source_pixels,
        independent_sampled_nearest_scene_rays=nearest_rays, additional_selected_centroid_rays=centroid_rays,
        actual_product_raster_attempts=raster_total, actual_repeat_raster_attempts=0,
        actual_repeat_frame_reuses=1, selected_region_image_evidence='unknown',
        reason='All five original deliveries contain zero selected source-triangle pixels. Cube hide_render=true is included in the surface capture and its closed box strictly contains every selected triangle.',
        main_repeat=dict(region_ref_unchanged=True, current_binding_unchanged=True, image_and_arrays_unchanged=True,
                         producer_prepare_calls=0, producer_raster_calls=0, producer_encoded_bytes=0),
        states=[dict(capture_generation=state['region_ref']['capture_generation'], region_id=state['region_ref']['region_id'],
                     image_ref=state['frames'][0]['image_ref'], frame_identity=state['frames'][0]['frame_identity'],
                     image_sha256=state['frames'][0]['image_sha256'], arrays_sha256=state['frames'][0]['arrays_sha256']) for state in states],
        checks=audit.checks, input_pins=list(audit.pins.values()), new_operations=dict(Blender=0, raster=0, model=0, paid=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = review(args.sessions_root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps(dict(passed_checked_scope=True, checks=len(result['checks']), output=str(args.output.resolve()))))


if __name__ == '__main__':
    main()
