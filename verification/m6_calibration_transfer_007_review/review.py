"""Independently recompute the transferred proposal's images and saved geometry."""
import base64
import hashlib
import json
from pathlib import Path
import runpy
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tr7/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007')
PNG = runpy.run_path(str(HERE.parent / 'm6_image_correspondence_005_plan/probe.py'))['read_png']
VECTOR_STATISTICS = runpy.run_path(str(HERE.parent / 'm6_matched_refine_003_review/review.py'))['statistics']


def read(path):
    return json.loads(path.read_bytes())


def local(value):
    path = Path(value)
    return BASE / path.relative_to(AUTHOR) if path.is_absolute() else BASE / path


def statistics(vectors, ids):
    values = VECTOR_STATISTICS(vectors, ids)
    return {key.replace('_m', '_source_unit'): value for key, value in values.items()}


def main():
    started = time.perf_counter()
    binding = read(BASE / 'SOURCE_BINDING.json')
    scoring = read(BASE / 'SCORING_BINDING.json')
    report = read(BASE / 'CALIBRATION_SCORES_v2.json')
    state = read(BASE / 'private/calibrations/v2_raw_proposal/STATE.json')
    result = read(local(state['result']['path']))
    assert result['status'] == 'image_selection_frozen'
    assert result['independent_geometry_scoring'] == 'pending_separate_private_scorer'
    assert result['image_selection_frozen_epoch'] < report['private_scoring_started_epoch']
    with np.load(local(binding['initial']['packet']['path'])) as packet:
        initial = {key: packet[key] for key in packet.files}
    with np.load(local(scoring['target']['path'])) as packet:
        target = {key: packet[key] for key in packet.files}
    with np.load(local(scoring['clean_actual_readback']['path'])) as packet:
        np.testing.assert_array_equal(packet['vertices_world'], target['clean_vertices_world'])
    support, region, editable = target['support_ids'], target['F_source_ids'], target['I_ids']
    normal_editable = np.setdiff1d(editable, support)
    assert tuple(map(len, (support, region, editable, normal_editable))) == (43, 384, 274, 231)
    references = {entry['role'].removeprefix('normal_'): PNG(local(entry['path'])).astype(np.int16)
                  for entry in binding['images']['normal']}
    groups = dict(support_43=support, observation_384=region,
                  normal_341=np.setdiff1d(region, support), normal_editable_231=normal_editable)
    before_error = initial['vertices_world'] - target['clean_vertices_world']
    candidates = []
    for tag, entry in state['candidates'].items():
        item = entry['result']
        alpha = item['alpha']
        claim = next(row for row in report['candidates'] if row['alpha'] == alpha)
        loss = 0
        for image in item['images']:
            pixels = PNG(local(image['path'])).astype(np.int16)
            view = image['role'].removeprefix('current_')
            assert pixels.shape == references[view].shape == (640, 640, 3)
            loss += int(np.abs(pixels - references[view]).sum())
        assert loss == claim['image']['absolute_error_sum'] == item['image']['absolute_error_sum']
        assert claim['image']['sample_count'] == 3686400
        with np.load(local(item['readback']['path'])) as packet:
            actual = {key: packet[key] for key in packet.files}
        with np.load(local(item['payload']['path'])) as payload:
            ids, delta = payload['source_ids'], payload['displacements_world']
        with np.load(local(binding['proposals'][0]['payload']['path'])) as original:
            np.testing.assert_array_equal(ids, original['source_ids'])
            np.testing.assert_array_equal(delta, alpha * original['displacements_world'])
        expected_local = initial['vertices_local'].copy()
        inverse = np.linalg.inv(initial['matrix_world'])
        wanted_world = initial['vertices_world'][ids] + delta
        expected_local[ids] = (wanted_world @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
        np.testing.assert_array_equal(actual['vertices_local'], expected_local)
        for key in ('matrix_world', 'faces', 'source_ids', 'poly_offsets', 'poly_vertices', 'triangle_polygon_ids'):
            np.testing.assert_array_equal(actual[key], initial[key])
        final_error = actual['vertices_world'] - target['clean_vertices_world']
        displacement = actual['vertices_world'] - initial['vertices_world']
        for group, ids_in_group in groups.items():
            for position, vectors in (('before', before_error), ('after', final_error)):
                for key, value in statistics(vectors, ids_in_group).items():
                    assert abs(value - claim['metrics'][group][position][key]) < 1e-12, (alpha, group, key)
                    if key != 'points':
                        ratio_key = key.replace('_source_unit', '_over_ell')
                        assert abs(value / scoring['ell'] - claim['metrics'][group][position][ratio_key]) < 1e-12
        np.testing.assert_array_equal(displacement[normal_editable], 0)
        outside = np.setdiff1d(initial['source_ids'], editable)
        np.testing.assert_array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
        reduction = 1 - statistics(final_error, support)['RMSE_source_unit'] / statistics(before_error, support)['RMSE_source_unit']
        assert reduction < .3 and claim['restoration_quality_pass'] is False
        active = np.flatnonzero(np.linalg.norm(displacement, axis=1) > 1e-12)
        candidates.append(dict(alpha=alpha, integer_RGB_loss=loss, support_RMSE=statistics(final_error, support)['RMSE_source_unit'],
            support_reduction_fraction=reduction, normal_editable_misedit=statistics(displacement, normal_editable),
            TP=len(np.intersect1d(active, support)), FP=len(np.setdiff1d(active, support)), FN=len(np.setdiff1d(support, active))))
    chosen = min(candidates, key=lambda row: (row['integer_RGB_loss'], row['alpha']))
    assert chosen['alpha'] == result['selected_alpha'] == .5
    folder = BASE / 'private/consumers/raw/sample_07/facts'
    consumer = read(folder / 'CONSUMER.json')
    events = [json.loads(line)['event'] for line in (folder / 'events.jsonl').read_text(encoding='utf8').splitlines()]
    usage = [event['usage'] for event in events if event['type'] == 'turn.completed']
    assert len(usage) == 1 and usage[0] == consumer['usage']
    tools = [event['item'] for event in events if event['type'] == 'item.completed' and event['item']['type'] == 'mcp_tool_call']
    assert len(tools) == consumer['tool_count'] == 11
    expected_pngs = {(row['sha256'], row['bytes']) for row in read(BASE / 'MANIFEST.json')['files'] if row['path'].endswith('.png')}
    blocks = PNG_bytes = 0
    for response in (folder / 'bridge').glob('tool_*/RESPONSE.json'):
        for block in read(response).get('content', []):
            if block['type'] == 'image':
                data = base64.b64decode(block['data'], validate=True)
                assert (hashlib.sha256(data).hexdigest(), len(data)) in expected_pngs
                blocks += 1
                PNG_bytes += len(data)
    summary = dict(status='accepted_transfer_execution_three_restoration_failures', candidates=candidates,
        selected_alpha=chosen['alpha'], actual_Pro_sessions=1, actual_tools=len(tools), actual_PNG_blocks=blocks,
        actual_PNG_bytes=PNG_bytes, usage_from_raw_event=usage[0], consumer_wall_s=consumer['wall_s'],
        unit=scoring['unit'], image_selection_restoration_success=False,
        new_Pro=0, new_Blender=0, new_training=0, independent_full_contact_rescan=False,
        wall_s=time.perf_counter() - started)
    (HERE / 'RESULTS.json').write_bytes((json.dumps(summary, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in summary.items() if key != 'candidates'}))


if __name__ == '__main__':
    main()
