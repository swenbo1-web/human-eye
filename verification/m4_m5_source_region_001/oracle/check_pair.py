"""Saved-only two-request source-region task review and frame reuse comparison."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--run-binding', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    session = Path(options.session).resolve()
    audit = check_saved.Audit()
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    audit.check(len(calls) == 2, 'fixed_two_public_requests')
    first_query = calls[0]['request']['params']['arguments']['query']
    second_query = calls[1]['request']['params']['arguments']['query']
    expected = dict(mode='source_region', region=dict(object=dict(name='Obj_07'), source_triangle_indices=[0, 1, 2, 3]),
                    reference=dict(name='Ref_B'), requested_facts=['surface_proximity'])
    audit.check(first_query == expected, 'original_fixed_first_region_to_B_request')
    first_public = json.loads(next(block['text'] for block in calls[0]['response']['result']['content'] if block['type'] == 'text'))
    expected_second = dict(mode='source_region', region_ref=first_public['region_ref'],
                           reference=dict(name='Ref_C'), requested_facts=['surface_proximity'])
    audit.check(second_query == expected_second, 'original_public_region_ref_handed_to_second_C_request')
    reviews = [check_saved.check_session(session, options.run_binding, index) for index in (1, 2)]
    first, second = reviews
    audit.check(first['region_ref'] == second['region_ref'], 'region_identity_preserved_across_reference_switch')
    frame_a, frame_b = first['frames'][0], second['frames'][0]
    audit.check(frame_a['array_sha256'] == frame_b['array_sha256'], 'reference_switch_identical_RGB_depth_object_triangle_arrays')
    reuse = frame_a['frame_identity'] == frame_b['frame_identity'] and frame_a['image_ref'] == frame_b['image_ref']
    result = dict(schema='m4-m5-source-region-two-request-saved-review-v1', passed=True, session=str(session),
        requests=reviews, same_region=True, same_frame_identity=reuse,
        reference_switch_array_content_identical=True, checks=audit.checks, input_pins=list(audit.pins.values()),
        author_association='Fixture and product-independent saved oracle share an author. Root reviews the frozen sources separately.',
        new_live_Blender=0, new_raster=0, new_model=0)
    Path(options.output).write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, same_frame_identity=reuse, output=str(Path(options.output).resolve()))))


if __name__ == '__main__':
    main()
