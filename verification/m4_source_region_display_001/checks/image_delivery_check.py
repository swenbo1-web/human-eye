"""Check all eight original public image deliveries and display feedback.

This saved-evidence entry point runs the independent full-image and bounded-ray
checker on every delivery, persists each attempt, and aggregates current state
expectations. Every attempt creates a fresh report file so earlier failures
remain reviewable. No image generation or live process is invoked.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback


sys.dont_write_bytecode = True
import image_check


SCHEMA = 'm4-source-region-display-image-delivery-review-v1'
STATES = dict(main=('initial', 'repeat'),
              state=('initial', 'cube_visible', 'cube_restored', 'target_hidden', 'target_restored', 'repeat'))


def available_output(directory, stem):
    path = directory / (stem + '.json')
    attempt = 1
    while path.exists():
        attempt += 1
        path = directory / (stem + '_ATTEMPT_' + str(attempt).zfill(2) + '.json')
    return path


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def verify_delivery(session, session_name, state, call_index, call, report, record, audit):
    original = audit.read(call['producer_archive']['path'], call['producer_archive']['sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    receipt = audit.read(session / 'product_calls' / ('call_' + str(call_index).zfill(3)) / 'DELIVERY.json')
    audit.check(receipt['label'] == state and receipt['is_error'] is False, 'original_fixture_state_public_receipt/' + session_name + '/' + state)
    native_images = [block for block in response['result']['content'] if block['type'] == 'image']
    audit.check(len(native_images) == len(receipt['images']) == 1, 'one_native_saved_delivery_receipt/' + session_name + '/' + state)
    for image, saved in zip(native_images, receipt['images'], strict=True):
        png = audit.file(saved['path'], saved['sha256'], session)
        audit.check(png == base64.b64decode(image['data'], validate=True)
                    and len(png) == saved['bytes'], 'receipt_saved_native_PNG_exact_raw_stdio/' + session_name + '/' + state)
    frame = report['frames'][0]
    scope = report['image_scope']
    by_name = {row['object_name']: row for row in scope['objects']}
    cube = by_name['Cube']
    target = by_name[report['source_object_name']]
    cube_visible = state == 'cube_visible'
    target_hidden = state == 'target_hidden'
    audit.check(cube['visible_get'] is cube_visible and cube['participates'] is cube_visible
                and cube['hide_get'] is not cube_visible and cube['hide_render'] is True,
                'fixed_current_Cube_viewport_render_flags/' + session_name + '/' + state)
    audit.check(target['visible_get'] is not target_hidden and target['participates'] is not target_hidden,
                'fixed_current_target_participation/' + session_name + '/' + state)
    count = frame['selected_surface_pixels']
    if cube_visible or target_hidden:
        expected_reason = 'selected_region_not_displayed' if target_hidden else 'selected_region_displayed_without_pixels'
        audit.check(count == 0 and report['status'] == 'partial'
                    and report['observation_status'] == 'evidence_insufficient'
                    and report['selected_region_image_reason'] == expected_reason,
                    'direct_expected_zero_sample_feedback/' + session_name + '/' + state)
    else:
        audit.check(count > 0 and report['selected_region_image_evidence'] == 'pass'
                    and report['status'] == 'complete' and report['observation_status'] == 'locally_observed',
                    'actual_selected_pixels_with_hidden_Cube/' + session_name + '/' + state)
    if target_hidden:
        audit.check(sum(frame['visible_object_pixel_counts'].values()) == 0
                    and frame['selected_centroid_review']['status_counts'] == {'selected_region_not_displayed': 748}
                    and frame['selected_centroid_review']['occluded_centroid_samples'] == 0,
                    'hidden_target_empty_image_and_explicit_nonparticipation')
    if cube_visible:
        audit.check(frame['visible_object_pixel_counts']['Cube'] == 511 * 511
                    and frame['selected_centroid_review']['occluded_centroid_samples'] == 748,
                    'displayed_Cube_actual_pixels_and_all_748_centroid_occlusion_samples')
    if not cube_visible:
        audit.check(frame['visible_object_pixel_counts']['Cube'] == 0,
                    'hidden_Cube_has_no_current_image_pixels/' + session_name + '/' + state)
    centroid = frame['selected_centroid_review']
    sample = frame['sampled_nearest_scene_review']
    audit.check(centroid['centroid_sample_count'] == 748 and sample['fixed_grid_samples'] == 256,
                'fixed_256_grid_and_all_748_centroid_sample_denominators/' + session_name + '/' + state)
    surface = original['task_result']['facts']['surface_proximity']
    audit.check(original['task_result']['status'] == 'complete' and surface['status'] == 'measured'
                and abs(surface['value']['distance_m'] - 0.37011719389236364) <= 1e-12,
                'all_selected_geometry_measurement_retained/' + session_name + '/' + state)
    record.update(selected_surface_pixels=count, status=report['status'],
        observation_status=report['observation_status'], selected_region_image_reason=report['selected_region_image_reason'],
        display_identity=scope['identity'], image_sha256=frame['image_sha256'],
        checked_foreground_pixels=frame['full_image_source_pixel_review']['foreground_pixels'],
        checked_grid_rays=sample['fixed_grid_samples'], checked_centroid_rays=centroid['centroid_sample_count'],
        participating_triangles=sample['participating_source_triangle_denominator'])
    return original


def review(sessions_root, run_binding, reports_dir):
    started = time.perf_counter()
    audit = image_check.Audit()
    audit.file(__file__)
    root = Path(sessions_root).resolve()
    reports_dir = Path(reports_dir).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    reviews, failures, originals = [], [], []
    for session_name, states in STATES.items():
        session = root / session_name
        calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
        audit.check(len(calls) == len(states), 'exact_public_delivery_count/' + session_name)
        for call_index, state in enumerate(states, 1):
            source_state = ('initial' if session_name == 'main' else 'target_restored') if state == 'repeat' else state
            report_path = available_output(reports_dir, session_name.upper() + '_' + state.upper() + '_IMAGE_REVIEW')
            frame_audit = image_check.Audit()
            try:
                report = image_check.check_session(session, run_binding,
                    session / ('SOURCE_' + source_state + '.json'), call_index, frame_audit)
            except Exception as error:
                report = image_check.failure(error, frame_audit)
            report.update(session_label=session_name, state_label=state)
            save(report_path, report)
            record = dict(session=session_name, state=state, call_index=call_index, path=str(report_path),
                sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(), passed_checked_scope=report['passed_checked_scope'],
                error=report.get('error'))
            reviews.append(record)
            if not report['passed_checked_scope']:
                failures.append(record)
                continue
            try:
                original = verify_delivery(session, session_name, state, call_index,
                                           calls[call_index - 1], report, record, audit)
                originals.append(dict(session=session_name, state=state, value=original))
                record['delivery_expectations_passed'] = True
            except Exception as error:
                record.update(delivery_expectations_passed=False, error=str(error),
                              expectation_traceback=traceback.format_exc())
                failures.append(record)
    if not failures:
        for session_name in STATES:
            rows = [row['value'] for row in originals if row['session'] == session_name]
            audit.check(len({row['binding']['ordered_geometry_sha256'] for row in rows}) == 1
                        and len({row['binding']['camera_identity'] for row in rows}) == 1,
                        'same_fixed_geometry_and_camera_across_current_display_states/' + session_name)
        old = audit.read(image_check.REPO / 'verification/m4_real_asset_region_qualification_001/checks/MAIN_INITIAL_IMAGE_REVIEW.json')
        audit.check(old['passed_checked_scope'] and old['frames'][0]['selected_surface_pixels'] == 0,
                    'preserved_prior_actual_zero_selected_pixel_counterexample')
    return dict(schema=SCHEMA, passed_checked_scope=not failures, actual_public_deliveries_checked=len(reviews),
        successful_public_deliveries_checked=len(reviews) - len(failures), failure_count=len(failures), failures=failures,
        original_public_delivery_checked=True, reviews=reviews,
        independent_all_foreground_source_memberships=sum(row.get('checked_foreground_pixels', 0) for row in reviews),
        independent_fixed_grid_nearest_rays=sum(row.get('checked_grid_rays', 0) for row in reviews),
        independent_selected_face_centroid_rays=sum(row.get('checked_centroid_rays', 0) for row in reviews),
        complete_selected_surface_visibility='unknown', full_foreground_nearest_surface_claim=False,
        elapsed_seconds=time.perf_counter() - started, checks=audit.checks, input_pins=list(audit.pins.values()),
        new_operations=dict(Blender=0, raster=0, model=0, paid=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root', type=Path, required=True)
    parser.add_argument('--run-binding', type=Path, default=image_check.NS / 'R0_RUN_BINDING.json')
    parser.add_argument('--reports-dir', type=Path, default=image_check.HERE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = review(args.sessions_root, args.run_binding, args.reports_dir)
    except Exception as error:
        result = dict(schema=SCHEMA, passed_checked_scope=False, error_type=type(error).__name__,
            error=str(error), traceback=traceback.format_exc(), new_operations=dict(Blender=0, raster=0, model=0, paid=0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = available_output(args.output.parent, args.output.stem)
    save(output, result)
    print(json.dumps(dict(passed_checked_scope=result['passed_checked_scope'], output=str(output),
                         error=result.get('error'), failure_count=result.get('failure_count'))))
    raise SystemExit(0 if result['passed_checked_scope'] else 1)


if __name__ == '__main__':
    main()
