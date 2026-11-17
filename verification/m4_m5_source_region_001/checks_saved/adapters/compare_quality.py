"""Compare all three saved baseline/optimization pairs after individual review."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def main():
    rows, pins = [], [pin(Path(__file__))]
    original_arrays = None
    for pair in range(1, 4):
        for variant in ('R0', 'R1'):
            path = OUT / ('pair' + str(pair) + '_' + variant + '.json')
            value = json.loads(path.read_bytes())
            assert value['passed'] and value['local_camera_review_required']
            assert value['same_region'] and value['same_frame_identity'] and value['reference_switch_array_content_identical']
            assert len(value['requests']) == 2 and len(value['independent_selected_fit_camera_reviews']) == 2
            current_arrays = [request['frames'][0]['array_sha256'] for request in value['requests']]
            if original_arrays is None:
                original_arrays = current_arrays
            assert current_arrays == original_arrays
            assert [row['numeric']['independent_distance_squared_m2'] for row in value['requests']] == ['25/16', '137/16']
            assert all(row['source_region_triangle_indices'] == [0, 1, 2, 3]
                       and row['source_region_vertex_indices'] == [0, 1, 2, 3, 4, 5] for row in value['requests'])
            rows.append(dict(pair=pair, variant=variant, saved_review=pin(path),
                selected_pixel_counts=value['requests'][0]['frames'][0]['selected_pixel_counts'],
                source_triangle_set=[0, 1, 2, 3], distance_squared_m2=['25/16', '137/16'],
                within_owned_reference_switch_same_frame=True, cross_variant_raw_arrays_equal=True))
            pins.append(pin(path))
    result = dict(schema='m4-m5-source-region-three-pair-quality-review-v1', passed=True,
        pairs=3, fresh_owned_slots=6, individual_saved_reviews=rows, identical_raw_frame_arrays=original_arrays,
        quality_scope='Independent current-source, selected-fit camera, full-scene occlusion, exact native bytes, distance and witness/reverse-map checks passed in every individual saved review.',
        geometric_full_selected_surface_visibility_claim=False,
        input_pins=pins, new_live_Blender=0, new_raster=0, new_model=0)
    path = OUT / 'THREE_PAIR_QUALITY.json'
    path.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, output=str(path))))


if __name__ == '__main__':
    main()
