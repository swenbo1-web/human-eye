"""Independently check image transport, four saved meshes and contour measurements."""
import base64
import hashlib
import json
from pathlib import Path
import runpy
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6ref2/batch'
PREVIOUS = HERE.parent / '_m6ref1/batch'
KERNEL = runpy.run_path(str(HERE.parent / 'm6_reference_refine_001_review/review.py'))


def read(path):
    return json.loads(path.read_bytes())


def main():
    started = time.perf_counter()
    image_binding = read(BASE / 'IMAGE_BINDING.json')
    views = read(BASE / 'VIEWABLES.json')
    previous_observation = read(PREVIOUS / 'OBSERVATION.json')
    annotation = read(PREVIOUS / 'ANNOTATION_DRAFT.json')
    with np.load(BASE / 'private/cases/forearm/initial.npz') as initial:
        observed_ids = initial['F_source_ids']
        editable_ids = initial['I_ids']
        assert len(np.unique(observed_ids)) == 599
        assert len(np.unique(editable_ids)) == 347
        assert np.isin(editable_ids, observed_ids).all()
    records = []
    prompt_digests = set()
    image_count = 0
    image_bytes = 0
    independent_station_checks = 0
    for session in views['sessions']:
        folder = BASE / 'private/consumers' / session['stage'] / 'forearm' / session['route']
        consumer = read(folder / 'CONSUMER.json')
        answer = read(folder / 'PUBLIC_FINAL.txt')
        events = [json.loads(line)['event'] for line in (folder / 'events.jsonl').read_text(encoding='utf8').splitlines()]
        completed = [event for event in events if event['type'] == 'turn.completed']
        assert len(completed) == 1
        usage = completed[0]['usage']
        assert usage == consumer['usage']
        tool_events = [event['item'] for event in events if event['type'] == 'item.completed' and event['item']['type'] == 'mcp_tool_call']
        assert len(tool_events) == consumer['tool_count'] <= 12
        assert tool_events[0]['tool'] == 'images'
        assert consumer['status'] == 'completed' and consumer['exit_code'] == 0
        assert answer['modification_decision'] == 'no_edit'
        assert answer['version'] == 0
        prompt_digests.add(hashlib.sha256((folder / 'PROMPT.txt').read_bytes()).hexdigest())
        image_reply = read(folder / 'bridge/tool_01/RESPONSE.json')
        blocks = [block for block in image_reply['content'] if block['type'] == 'image']
        assert len(blocks) == len(image_binding['images']) == 9
        for block, expected in zip(blocks, image_binding['images']):
            data = base64.b64decode(block['data'], validate=True)
            assert len(data) == expected['bytes']
            assert hashlib.sha256(data).hexdigest() == expected['sha256']
            image_bytes += len(data)
        image_count += len(blocks)
        session_folder = BASE / 'private/sessions' / session['session']
        state = read(session_folder / 'session.json')
        assert state['version'] == 0 and not state['operations'] and state['pending'] is None
        assert hashlib.sha256((session_folder / 'before.blend').read_bytes()).hexdigest() == '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
        packet = session_folder / 'readbacks/001/readback.npz'
        quality = read(session_folder / 'readbacks/001/QUALITY.json')
        with np.load(packet) as actual, np.load(PREVIOUS / 'private/cases/s01/baseline_readback.npz') as prior:
            assert actual.files == prior.files
            for name in prior.files:
                assert np.array_equal(actual[name], prior[name]), (session['session'], name)
            projection = annotation['source_projection']
            pixels = actual['vertices_world'] @ np.asarray(projection['affine_2_by_3']).T + np.asarray(projection['offset'])
            for family in ('primary', 'alternative'):
                anchors = previous_observation[family + '_anchors']
                measured = quality['contours']['definitions'][family]
                for stage in ('before', 'after'):
                    for index, station in enumerate(annotation['stations']):
                        inner, outer = KERNEL['section'](pixels, actual['faces'], anchors['model']['E'], anchors['model']['W'], station)
                        observed = measured[stage]['stations'][index]['model']
                        np.testing.assert_allclose(
                            [inner, outer, outer - inner, (inner + outer) / 2],
                            [observed['inner'], observed['outer'], observed['width'], observed['centerline']],
                            rtol=0, atol=1e-12,
                        )
                        independent_station_checks += 1
        assert quality['contours']['geometry_improvement_established'] == {'primary': False, 'alternative': False}
        assert quality['displacement']['changed_vertices'] == 0
        records.append(dict(
            stage=session['stage'], route=session['route'], usage=usage,
            tools=len(tool_events), wall_s=consumer['wall_s'], decision='no_edit',
            actual_images=len(blocks), saved_geometry='bitwise_equal_to_prior_baseline',
        ))
    assert len(prompt_digests) == 1
    assert len(records) == 4 and image_count == 36 and image_bytes == 15365788
    selection = read(BASE / 'API_SELECTION.json')
    assert selection['default'] == 'v1'
    assert (BASE / 'session_api.py').read_bytes() == (BASE / selection['executed_v1_source']['path']).read_bytes()
    totals = {name: sum(record['usage'][name] for record in records) for name in records[0]['usage']}
    result = dict(
        status='passed_conditional_visual_consumption_no_refinement',
        sessions=records, independent_station_checks=independent_station_checks,
        full_image_blocks_checked=image_count, raw_PNG_bytes=image_bytes,
        usage_from_raw_turn_completed=totals,
        total_consumer_wall_s=sum(record['wall_s'] for record in records),
        total_tools=sum(record['tools'] for record in records),
        source_region_points=len(observed_ids), editable_points=len(editable_ids),
        default_API='v1_exact_executed_bytes', new_Pro_consumers=0,
        new_Blender_jobs=0, new_training=0, artistic_acceptance=None,
        wall_s=time.perf_counter() - started,
    )
    (HERE / 'RESULTS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
