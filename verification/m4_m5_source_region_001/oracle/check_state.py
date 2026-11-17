"""Saved state sequence review, including stale errors, legacy images and whole controls."""

import argparse
import base64
from fractions import Fraction as F
from io import BytesIO
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_saved as saved


def public(call, audit, session):
    request = audit.read(call['request_path'], call['request_sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    audit.check(request == audit.read(call['actual_TX_path'], call['actual_TX_sha256'], session)
                and response == audit.read(call['actual_RX_path'], call['actual_RX_sha256'], session), 'state_original_public_stdio')
    blocks = response.get('result', {}).get('content', [])
    rows = [json.loads(row['text']) for row in blocks if row['type'] == 'text']
    return request, response, rows[0] if len(rows) == 1 else None


def whole_control(call, name, audit, session, captures):
    request, response, value = public(call, audit, session)
    args = request['params']['arguments']
    audit.check(response['result']['isError'] is False and args['include_image'] is False
                and args['query'] == dict(mode='task', objects=[dict(name='Obj_07'), dict(name=name)],
                    requested_facts=['surface_proximity']), 'legacy_whole_objects_original_request/' + name)
    audit.check(len(response['result']['content']) == 1, 'legacy_whole_objects_zero_image_blocks/' + name)
    audit.check(value['measurement_scope'] == 'whole_objects', 'legacy_whole_scope/' + name)
    wanted = F(1, 1024) if name == 'Ref_B' else F(2305, 1024)
    fact = value['facts']['surface_proximity']
    metric = fact['value']
    audit.check(fact['status'] == fact['witness_status'] == fact['direction_status'] == 'measured'
                and abs(metric['distance_m'] - math.sqrt(float(wanted))) <= 1e-9, 'legacy_whole_independent_answer/' + name)
    meshes = {mesh['name']: mesh for capture in captures for mesh in capture['meshes']}
    memberships = []
    for side, mesh_name in (('a', 'Obj_07'), ('b', name)):
        mesh = meshes[mesh_name]
        member = saved.MATH.membership(metric['nearest_witness'][side], mesh['vertices'], mesh['faces'])
        audit.check(bool(member['within_publication_tolerance_source_triangle_indices']), 'legacy_whole_witness_source_membership/' + name + '/' + side)
        memberships.append(dict(side=side, source_rows=member['exact_source_triangle_indices']))
    delta = saved.MATH.subtract(saved.MATH.vector(metric['nearest_witness']['b']), saved.MATH.vector(metric['nearest_witness']['a']))
    audit.check(abs(math.sqrt(float(saved.MATH.dot(delta, delta))) - math.sqrt(float(wanted))) <= 1e-9,
                'legacy_whole_attaining_witness_length/' + name)
    return dict(reference=name, scope='whole_objects', distance_m=metric['distance_m'],
                independent_distance_squared_m2=str(wanted), witnesses=memberships, actual_native_images=0)


def legacy_default(call, installed, captures, audit, session):
    request, response, value = public(call, audit, session)
    audit.check(request['params']['arguments']['query'] == dict(mode='active_observation')
                and response['result']['isError'] is False, 'legacy_default_public_entry_success')
    record = call['producer_archive']
    full = audit.read(record['path'], record['sha256'], session)
    capture = saved.current_capture(captures, full['binding'], audit)
    saved.compare_geometry(capture, False, audit)
    frames = full['frames']
    images = [block for block in response['result']['content'] if block['type'] == 'image']
    audit.check(len(frames) == len(images) == 6, 'legacy_default_six_current_native_images')
    reviews = []
    for frame, image in zip(frames, images, strict=True):
        png = audit.file(frame['image_path'], frame['image_sha256'], session)
        blob = audit.file(frame['arrays_path'], frame['arrays_sha256'], session)
        audit.check(base64.b64decode(image['data'], validate=True) == png, 'legacy_default_original_public_PNG')
        with saved.np.load(BytesIO(blob), allow_pickle=False) as arrays:
            buffers = {name: arrays[name] for name in arrays.files}
        with saved.Image.open(BytesIO(png)) as decoded:
            audit.check(decoded.mode == 'RGB' and saved.np.array_equal(saved.np.asarray(decoded), buffers['color']),
                        'legacy_default_original_PNG_RGB_array')
        ray = saved.PIXELS.ray_winner_checks(frame, capture, buffers, audit)
        reviews.append(dict(view_name=frame['view_name'], image_ref=frame['image_ref'], independent_all_scene_ray_review=ray))
    return dict(default_current_11_object_capture=True, original_native_images=len(images), frames=reviews)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--run-binding', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    session = Path(options.session).resolve()
    audit = saved.Audit()
    audit.file(__file__)
    expectations = audit.read(HERE / 'STATE_EXPECTATIONS.json')
    installed = audit.read(options.run_binding)
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    audit.check(len(calls) == len(expectations['rows']) == 11, 'frozen_eleven_state_requests')
    captures, commands = saved.decode_captures(session, installed, audit)
    reviews = {}
    for index in (2, 3, 4, 5, 7, 9):
        reviews[str(index)] = saved.check_session(session, options.run_binding, index, translated=index == 7)
    initial = reviews['2']
    for index in ('3', '4'):
        audit.check(reviews[index]['region_ref'] == initial['region_ref'], 'repeat_or_reference_switch_same_region/' + index)
        audit.check(reviews[index]['frames'][0]['array_sha256'] == initial['frames'][0]['array_sha256']
                    and reviews[index]['frames'][0]['frame_identity'] == initial['frames'][0]['frame_identity'],
                    'repeat_or_reference_switch_same_original_frame/' + index)
    for index in ('5', '7', '9'):
        audit.check(reviews[index]['region_ref'] != initial['region_ref'], 'changed_region_or_generation_new_reference/' + index)
    audit.check(reviews['7']['frames'][0]['array_sha256'] != initial['frames'][0]['array_sha256'],
                'actual_complete_scene_change_uses_new_frame_arrays')
    audit.check(reviews['9']['region_ref']['ordered_geometry_sha256'] == initial['region_ref']['ordered_geometry_sha256']
                and reviews['9']['region_ref']['capture_generation'] != initial['region_ref']['capture_generation'],
                'restored_geometry_current_generation_rebound')
    errors = []
    for index in (6, 8):
        call = calls[index - 1]
        request, response, value = public(call, audit, session)
        audit.check(request['params']['arguments']['query']['region_ref'] == initial['region_ref'], 'stale_original_returned_reference/' + str(index))
        audit.check(response.get('result', {}).get('isError') is True
                    and 'source_region_ref_capture_generation_changed' in json.dumps(response), 'specific_stale_capture_generation_error/' + str(index))
        audit.check(not any(block['type'] == 'image' for block in response['result']['content'])
                    and call.get('producer_archive') is None, 'stale_rejection_zero_images_and_zero_success_archive/' + str(index))
        errors.append(dict(call_index=index, expected_reason='source_region_ref_capture_generation_changed', original_error=response))
    events = [json.loads(line) for line in audit.file(session / 'product_audit.jsonl').splitlines() if line.strip()]
    raster_events = [event for event in events if event.get('event') in ('active_observation_render_attempt', 'source_region_render_attempt')]
    audit.check(len(raster_events) == expectations['expected_state_new_raster'] == 10, 'actual_state_raster_event_count')
    for index in (6, 8):
        error_request = calls[index - 1]['response']['result']['_meta']['human_eye']['request_id']
        audit.check(not any(event.get('request_id') == error_request for event in raster_events),
                    'specific_stale_error_zero_raster_events/' + str(index))
    receipts = []
    for filename, wanted in [('MOVE_RECEIPT.json', F(1, 4)), ('RESTORE_RECEIPT.json', F(0))]:
        receipt = audit.read(session / filename)
        value = receipt['response']['result']
        audit.check(value['target_name'] == 'Obj_07' and F(value['matrix_after'][0][3]) == wanted
                    and value['test_matrix_setters'] == 1 and value['product_setters'] == 0
                    and value['source_asset_saved'] is False, 'fixture_only_owned_matrix_step/' + filename)
        before_x = F(0) if wanted else F(1, 4)
        change = wanted - before_x
        audit.check(value['world_after'] == [[point[0] + float(change), point[1], point[2]] for point in value['world_before']],
                    'fixture_world_point_translation_readback/' + filename)
        receipts.append(value)
    audit.check(receipts[0]['before_fingerprint'] == receipts[1]['after_fingerprint']
                and receipts[0]['after_fingerprint'] == receipts[1]['before_fingerprint'], 'fixture_whole_state_fingerprint_restored')
    default = legacy_default(calls[0], installed, captures, audit, session)
    controls = [whole_control(calls[index - 1], name, audit, session, captures) for index, name in ((10, 'Ref_B'), (11, 'Ref_C'))]
    result = dict(schema='m4-m5-source-region-saved-state-review-v1', passed=True, session=str(session),
        source_region_requests=reviews, stale_original_errors=errors, legacy_default=default, whole_object_controls=controls,
        fixture_owned_matrix_receipts=receipts, actual_raster_events=10, product_setters=0,
        checks=audit.checks, input_pins=list(audit.pins.values()),
        author_association='Fixture and product-independent oracle share an author. Root reviews the frozen sources separately.',
        geometric_full_selected_surface_visible_claim=False, new_live_Blender=0, new_raster=0, new_model=0)
    Path(options.output).write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, output=str(Path(options.output).resolve()))))


if __name__ == '__main__':
    main()
