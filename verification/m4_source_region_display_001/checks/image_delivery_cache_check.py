"""Compare current display binding, original public delivery and cache counters."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
STATES = ['initial', 'cube_visible', 'cube_restored', 'target_hidden', 'target_restored']


def review(sessions_root):
    root = Path(sessions_root).resolve()
    pins, checks, observations = {}, [], {}

    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)

    def file(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        check(expected is None or digest == expected, 'pinned_bytes/' + path.name)
        pins[str(path)] = dict(path=str(path), bytes=len(raw), sha256=digest)
        return raw

    def read(path, expected=None):
        return json.loads(file(path, expected))

    for label in ('main', 'state'):
        folder = root / label
        result = read(folder / 'SLOT_RESULT.json')
        calls = [json.loads(line) for line in file(folder / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
        check(result['status'] == 'completed' and len(calls) == len(result['requests']), label + '/all_requests_completed')
        expected_labels = (STATES if label == 'state' else ['initial']) + ['repeat']
        check([row['label'] for row in result['requests']] == expected_labels, label + '/public_sequence')
        rows = []
        for record, request in zip(calls, result['requests']):
            name = request['label']
            prefix = label + '/' + name
            archive = record['producer_archive']
            raw = read(archive['path'], archive['sha256'])
            response = read(record['response_path'], record['response_sha256'])
            delivery_folder = folder / 'product_calls' / ('call_' + str(request['public_index']).zfill(3))
            delivery = read(delivery_folder / 'DELIVERY.json')
            check(delivery == request and not delivery['is_error'] and 'error' not in response
                  and response['result'].get('isError') is not True, prefix + '/same_successful_public_delivery')
            texts = [block['text'] for block in response['result']['content'] if block['type'] == 'text']
            native_images = [block for block in response['result']['content'] if block['type'] == 'image']
            check(len(texts) == 1 and len(native_images) == len(raw['frames']) == len(delivery['images']) == 1,
                  prefix + '/one_original_native_image_and_result')
            public = json.loads(texts[0])
            check(public == delivery['public_result'], prefix + '/saved_public_JSON_is_original_text')
            for key in ('status', 'observation_status', 'region_ref', 'task_result'):
                check(public[key] == raw[key], prefix + '/public_preserves_' + key)
            visibility = raw['facts']['visibility']
            public_visibility = public['visibility'] if 'visibility' in public else public['facts']['visibility']
            check(public_visibility == visibility, prefix + '/brief_or_full_preserves_visibility')
            frames = public['frames'] if 'frames' in public else public['images']
            frame = raw['frames'][0]
            check(frames[0]['image_ref'] == frame['image_ref']
                  and frames[0]['display_identity'] == frame['display_identity']
                  and frames[0]['image_scope_identity'] == frame['image_scope_identity'], prefix + '/public_current_display_image_identity')
            image = base64.b64decode(native_images[0]['data'], validate=True)
            check(image == file(delivery['images'][0]['path'], delivery['images'][0]['sha256'])
                  == file(frame['image_path'], frame['image_sha256']), prefix + '/original_native_PNG_equals_producer_bytes')
            file(frame['arrays_path'], frame['arrays_sha256'])

            state = 'target_restored' if label == 'state' and name == 'repeat' else 'initial' if name == 'repeat' else name
            snapshot = read(folder / ('SOURCE_' + state + '.json'))
            independent = snapshot['display_snapshot']
            scope = raw['binding']['image_scope']
            check(scope['status'] == 'captured' and scope['scope'] == independent['scope']
                  and scope['view_layer'] == {key: independent['view_layer'][key] for key in ('name', 'instance_id')},
                  prefix + '/independent_current_view_layer_identity')
            current = {row['name']: row for row in independent['objects']}
            ordered = sorted(raw['binding']['objects'], key=lambda row: row['object_index'])
            check(len(scope['objects']) == len(ordered) == len(scope['participation_mask']),
                  prefix + '/complete_source_object_space_retained')
            for source, displayed, participates in zip(ordered, scope['objects'], scope['participation_mask']):
                host = current[source['object_name']]
                check(displayed['host_id'] == source['host_id'] == host['host_id']
                      and displayed['instance_id'] == source['instance_id'] == host['instance_id']
                      and participates is displayed['participates'] is host['visible_get'],
                      prefix + '/independent_host_instance_and_participation/' + source['object_name'])
                check(all(displayed[key] is host[key] for key in ('visible_get', 'hide_get', 'hide_render', 'hide_viewport')),
                      prefix + '/independent_raw_flags/' + source['object_name'])
            check(frame['display_identity'] == raw['binding']['display_identity'] == scope['identity']
                  and frame['image_scope'] == scope, prefix + '/frame_binds_current_display_scope')
            check(frame['all_triangle_count'] == sum(len(row['evaluated']['triangles']) for row in snapshot['objects'])
                  and frame['all_object_count'] == len(snapshot['objects']), prefix + '/complete_global_triangle_space_retained')
            check(raw['region_ref']['host_id'] == current[TARGET]['host_id']
                  and raw['region_ref']['instance_id'] == current[TARGET]['instance_id']
                  and raw['region_ref']['source_triangle_indices'] == raw['facts']['region']['source_triangle_indices']
                  == raw['source_mapping']['submesh_to_source_triangle_indices']
                  and len(raw['region_ref']['source_triangle_indices']) == 748,
                  prefix + '/full_selected_source_mapping')
            pixels = visibility['selected_surface_pixels']
            if pixels == 0:
                check(visibility['status'] == 'unknown' and raw['status'] == 'partial'
                      and raw['observation_status'] == 'evidence_insufficient', prefix + '/zero_samples_have_direct_insufficient_feedback')
            else:
                check(visibility['status'] == 'observed_samples' and raw['status'] == 'complete'
                      and raw['observation_status'] == 'locally_observed', prefix + '/actual_samples_feedback')
            if state == 'cube_visible':
                check(pixels == 0 and visibility['selected_object_participates'] is True
                      and visibility['reason'] == 'selected_region_displayed_without_pixels', prefix + '/displayed_target_zero_pixels_reason')
            elif state == 'target_hidden':
                check(pixels == 0 and visibility['selected_object_participates'] is False
                      and visibility['reason'] == 'selected_region_not_displayed', prefix + '/hidden_target_zero_pixels_reason')
            else:
                check(pixels > 0 and visibility['selected_object_participates'] is True,
                      prefix + '/original_visible_character_has_source_pixels')
            check(visibility['complete_witness'] is None and 'complete_surface_visibility' in visibility['unknown'],
                  prefix + '/complete_surface_visibility_remains_unknown')
            fact = raw['task_result']['facts']['surface_proximity']
            oracle = read(folder / ('ORACLE_' + state + '.json'))
            check(fact['status'] == 'measured' and raw['task_result']['status'] == 'complete'
                  and abs(fact['value']['distance_m'] - 0.37011719389236364) < 1e-12
                  and abs(fact['value']['distance_m'] - oracle['distance_oracle']['distance_m']) <= 1e-7,
                  prefix + '/hidden_reference_complete_measurement_preserved')
            rows.append(raw)
        first, repeat = rows[0], rows[-1]
        preceding = rows[-2]
        for key in ('binding', 'region_ref', 'frames', 'facts', 'source_mapping', 'generation_work'):
            check(preceding[key] == repeat[key], label + '/same_state_repeat_preserves_' + key)
        work = repeat['work']
        for field in ('prepare_calls', 'geometry_normalization_calls', 'region_array_preparation_calls',
                      'camera_preparation_calls', 'raster_attempts', 'raster_completed', 'PNG_bytes', 'NPZ_bytes',
                      'array_payload_bytes', 'temporary_encoded_archive_bytes', 'frame_array_decodes'):
            check(work[field] == 0, label + '/same_state_repeat_zero_' + field)
        check(work['prepare_cache_hit'] is True and work['frame_reuses'] == 1
              and work['task_query']['result_cache_hit'] is True, label + '/same_state_repeat_caches')
        if label == 'state':
            for index in (1, 3):
                check(rows[index]['binding']['display_identity'] != first['binding']['display_identity']
                      and rows[index]['frames'][0]['image_ref'] != first['frames'][0]['image_ref']
                      and rows[index]['frames'][0]['frame_identity'] != first['frames'][0]['frame_identity'],
                      label + '/changed_display_has_distinct_image_identity_' + str(index))
            for index in (2, 4):
                check(rows[index]['binding']['display_identity'] == first['binding']['display_identity']
                      and rows[index]['frames'][0]['image_sha256'] == first['frames'][0]['image_sha256'],
                      label + '/restored_display_and_PNG_' + str(index))
        observations[label] = rows

    raster_total = sum(row['work']['raster_attempts'] for rows in observations.values() for row in rows)
    check(1 <= raster_total <= 8, 'actual_reported_rasters_within_total_budget')
    return dict(schema='m4-source-region-display-delivery-cache-review-v1', status='passed',
        original_public_deliveries_checked=sum(len(rows) for rows in observations.values()),
        actual_product_raster_attempts=raster_total, repeat_raster_attempts=0,
        states=[dict(label=name, region_ref=row['region_ref'], display_identity=row['binding']['display_identity'],
            image_ref=row['frames'][0]['image_ref'], frame_identity=row['frames'][0]['frame_identity'],
            image_sha256=row['frames'][0]['image_sha256'], selected_surface_pixels=row['facts']['visibility']['selected_surface_pixels'],
            observation_status=row['observation_status'], raster_attempts=row['work']['raster_attempts'])
            for name, row in zip(STATES + ['repeat'], observations['state'])],
        reference_semantics='Returned references and generations are recorded from each actual public result. Restoration cache counters are accepted as observed.',
        checks=checks, input_pins=list(pins.values()),
        operations=dict(Blender_starts=0, actual_rasters=0, model_calls=0, paid_calls=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = review(args.sessions_root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(result['checks']), actual_rasters=result['actual_product_raster_attempts'])))


if __name__ == '__main__':
    main()
