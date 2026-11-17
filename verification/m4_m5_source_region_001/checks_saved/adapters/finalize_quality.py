"""Seal direct saved quality evidence after all owned processes have closed."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
NS = OUT.parent
RUNTIME = Path('D:/he_m4_m5_source_region_001/sessions')


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def read(path):
    return json.loads(Path(path).read_bytes())


def main():
    pair_quality, state = read(OUT / 'THREE_PAIR_QUALITY.json'), read(OUT / 'state.json')
    old_pass, old_reject = read(OUT / 'qualification_R0.json'), read(OUT / 'qualification_R0_local_camera_reject.json')
    assert pair_quality['passed'] and state['passed'] and old_pass['passed'] and not old_reject['passed']
    optimized = [read(OUT / ('pair' + str(index) + '_R1.json')) for index in range(1, 4)]
    payloads = [row['requests'][0]['actual_optimized_payload_review'] for row in optimized]
    state_calls = [json.loads(line) for line in (RUNTIME / 'state/PUBLIC_REQUESTS.jsonl').read_bytes().splitlines() if line.strip()]
    state_payloads = []
    for call_index in (2, 3, 4, 5, 7, 9):
        raw = read(state_calls[call_index - 1]['producer_archive']['path'])
        work, generation = raw['work'], raw['generation_work']
        expected_fresh = int(call_index in (2, 5, 7, 9))
        assert work['fresh_payload_reuses'] == expected_fresh and work['frame_array_decodes'] == 0
        assert work['frame_reuses'] == 1 - expected_fresh
        assert generation['fresh_payload_reuses'] == 1 and generation['frame_array_decodes'] == 0
        frame = raw['frames'][0]
        assert frame['stages']['private_encoded_archive']['retained_encoded_payload_bytes'] == 0
        state_payloads.append(dict(call_index=call_index, fresh_payload_reuses=work['fresh_payload_reuses'],
            frame_array_decodes=work['frame_array_decodes'], frame_reuses=work['frame_reuses'],
            temporary_encoded_archive_bytes=frame['temporary_encoded_archive_bytes'], retained_encoded_payload_bytes=0))
    first = read(OUT / 'pair1_R0.json')
    first_frame = first['requests'][0]['frames'][0]
    camera = first['independent_selected_fit_camera_reviews'][0]['views'][0]
    direct = [NS / 'fixture/ASSET_BINDING.json', NS / 'fixture/TASK_REQUEST_BINDING.json',
              NS / 'oracle/STATIC_PREFLIGHT.json', NS / 'oracle/ASSET_REVIEW.json', NS / 'oracle/EXPECTATIONS.json',
              OUT / 'LOCAL_CAMERA_CONTRACT_ADJUSTMENT.json', OUT / 'qualification_R0.json',
              OUT / 'qualification_R0_local_camera_reject.json', OUT / 'THREE_PAIR_QUALITY.json', OUT / 'state.json']
    direct += [OUT / ('pair' + str(pair) + '_' + variant + '.json') for pair in range(1, 4) for variant in ('R0', 'R1')]
    direct += [NS / (name + '_RUN_BINDING.json') for name in ('R0', 'R0F', 'R1')]
    direct += sorted(HERE.glob('*.py'))
    for label in ['qualification_R0'] + ['pair' + str(pair) + '_' + variant for pair in range(1, 4) for variant in ('R0', 'R1')] + ['state']:
        slot = read(RUNTIME / label / 'SLOT_RESULT.json')
        assert slot['status'] == 'completed' and not slot['errors']
        direct.append(RUNTIME / label / 'SLOT_RESULT.json')
    result = dict(schema='m4-m5-source-region-quality-review-v1', passed=True,
        asset_sha256='b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9',
        fixture_counts=dict(objects=11, vertices=64, triangles=62),
        asset_readback='Native vertices/polygons and evaluated vertices/triangles match every frozen source row before save and after fresh reopen. Identity matrices, metre units, frame 1.',
        first_qualification=dict(label='qualification_R0', distance_source_pixel_bytes_passed=True,
            local_camera_qualification_passed=False, rejection=old_reject['error'], selected_surface_pixels=13,
            preserved=True),
        corrected_formal_quality=dict(fresh_owned_slots=6, paired_tasks=3, public_requests=12,
            all_passed=True, within_owned_B_C_same_returned_region_ref=True,
            within_owned_B_C_same_frame=True, cross_variant_raw_RGB_depth_object_triangle_patch_arrays_equal=True,
            selected_source_triangle_indices=[0, 1, 2, 3], selected_surface_pixel_counts=first_frame['selected_pixel_counts'],
            selected_surface_pixels=sum(first_frame['selected_pixel_counts'].values()),
            SCENE_span_m=camera['fitted_span_m'], selected_center_world_m=camera['selected_center_world_m'],
            camera_method='Independent exact selected-vertex NDC projection, selected symmetric XY extent with existing padding, and 88 full-scene AABB-corner depth enclosure for all six camera poses.',
            ray_method='Every saved 512x512 pixel independently intersected against all eleven current scene meshes. Source membership, nearest depth, object/triangle owners and unambiguous lit RGB checked.'),
        exact_distance_squared_m2=dict(selected_B='25/16', selected_C='137/16', whole_B='1/1024',
            whole_C='2305/1024', selected_B_after_x_quarter='5/4'),
        state=dict(public_requests=11, passed=True, legacy_default_actual_native_images=6,
            source_region_successes=6, stale_errors=[dict(call=row['call_index'], reason=row['expected_reason'],
                actual_native_images=0, successful_producer_archives=0, raster_events=0) for row in state['stale_original_errors']],
            state_actual_raster_events=state['actual_raster_events'], product_setters=0,
            moved_selected_B_m=state['source_region_requests']['7']['numeric']['distance_m'],
            restored_selected_B_m=state['source_region_requests']['9']['numeric']['distance_m'],
            restored_ordered_geometry_equal_and_current_generation_rebound=True,
            whole_object_controls=state['whole_object_controls']),
        optimization=dict(formal_cold_payload_instrumentation=payloads, state_payload_instrumentation=state_payloads,
            cold_actual_fresh_payload_reuses=1, cold_actual_frame_array_decodes=0,
            warm_actual_fresh_payload_reuses=0, warm_actual_frame_array_decodes=0, warm_actual_frame_reuses=1,
            R0F_one_array_decode='Source-derived from the frozen successful validation path. Original R0F runs did not instrument this count.',
            private_encoded_archive='Temporary immutable compressed payload measured by byte length. Retained encoded payload is zero after publication. BytesIO allocator overhead and process peak RSS are unmeasured.',
            cost_adoption_decision='Root evaluates the three-pair timing gate separately.'),
        evidence_limits=dict(image_visibility='Actual source-triangle pixel samples.',
            measurement='All selected source triangles including portions unseen in the image.',
            geometric_full_selected_surface_visibility_claim=False,
            native_polygon_vertex_to_evaluated_triangle_row_identity='Verified for this frozen fixture.'),
        disclosures=dict(authorship='The fixture and product-independent oracle share an author. Root found and corrected the missing local-camera verification and separately reviews frozen sources.',
            task_detail='Builder-pinned TASK.json contains the author-selected full detail. Actual main REQUESTS use default brief and state repeat uses full, cross-checked against the same producer archives.',
            saved_adapters='Frozen oracle source files remain preserved. Separate saved adapters add local-camera, actual payload counter and real trace-field checks.'),
        new_live_Blender_by_oracle=0, new_raster_by_oracle=0, new_model=0,
        input_pins=[pin(path) for path in direct])
    path = OUT / 'QUALITY_REVIEW.json'
    path.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, output=str(path.resolve()), formal_local_quality_slots=6, state_passed=True,
                          initial_whole_scene_camera_rejection_preserved=True)))


if __name__ == '__main__':
    main()
