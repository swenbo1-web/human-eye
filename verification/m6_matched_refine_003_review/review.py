"""Recompute saved-mesh errors and audit actual inputs, image blocks and usage."""
import base64
import hashlib
import json
from pathlib import Path
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6ref3/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')


def read(path):
    return json.loads(path.read_bytes())


def statistics(vectors, ids):
    lengths = np.linalg.norm(vectors[ids], axis=1)
    return dict(points=len(ids), RMSE_m=float(np.sqrt(np.mean(lengths ** 2))),
                p95_m=float(np.quantile(lengths, .95)), maximum_m=float(lengths.max()))


def current_normals(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    sums = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(sums, faces[:, corner], cross)
    lengths = np.linalg.norm(sums, axis=1)
    unit = np.divide(sums, lengths[:, None], out=np.zeros_like(sums), where=lengths[:, None] > 0)
    edges = np.unique(np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    neighbor_sum = np.zeros_like(vertices)
    degree = np.zeros(len(vertices))
    for first, last in ((0, 1), (1, 0)):
        np.add.at(neighbor_sum, edges[:, first], unit[edges[:, last]])
        np.add.at(degree, edges[:, first], 1)
    neighbor = np.divide(neighbor_sum, degree[:, None], out=np.zeros_like(neighbor_sum), where=degree[:, None] > 0)
    average = .5 * (unit + neighbor)
    lengths = np.linalg.norm(average, axis=1)
    return np.divide(average, lengths[:, None], out=np.zeros_like(average), where=lengths[:, None] > 0)


def main():
    started = time.perf_counter()
    binding = read(BASE / 'CASE_BINDING.json')
    for source in binding['source_files']:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    with np.load(BASE / 'private/scoring/target.npz') as packet:
        target = {name: packet[name] for name in packet.files}
    with np.load(BASE / 'private/cases/matched/initial.npz') as packet:
        initial = {name: packet[name] for name in packet.files}
    assert len(initial) == 16
    with np.load(BASE / 'private/cases/matched/actual_initial_readback.npz') as actual:
        for name in actual.files:
            assert np.array_equal(actual[name], initial[name]), name
    clean = np.load(Path(binding['source_files'][0]['path']))
    assert np.array_equal(clean, target['clean_vertices_world'])
    assert np.array_equal(initial['vertices_world'], target['initial_vertices_world'])
    np.testing.assert_allclose(current_normals(initial['vertices_world'], initial['faces']), initial['n0'], rtol=0, atol=1e-12)
    region, editable, support = target['F_source_ids'], target['I_ids'], target['support_ids']
    normal = np.setdiff1d(region, support)
    normal_editable = np.setdiff1d(editable, support)
    outside = np.setdiff1d(initial['source_ids'], editable)
    assert tuple(map(len, (region, editable, support, normal, normal_editable))) == (410, 274, 47, 363, 227)
    groups = dict(support_47=support, observation_410=region, normal_363=normal, normal_editable_227=normal_editable)
    initial_error = initial['vertices_world'] - clean
    known_png = {(row['sha256'], row['bytes']) for row in read(BASE / 'MANIFEST.json')['files'] if row['path'].endswith('.png')}
    cases = []
    image_blocks = image_bytes = 0
    for session in read(BASE / 'FINAL_VERIFICATION.json')['sessions']:
        name, stage, route = session['session'], session['stage'], session['route']
        folder = BASE / 'private/final_verify' / name
        score = read(folder / 'SCORE.json')
        with np.load(folder / 'readback.npz') as packet:
            actual = {key: packet[key] for key in packet.files}
        current = actual['vertices_world']
        final_error = current - clean
        displacement = current - initial['vertices_world']
        np.testing.assert_array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
        for field in ('matrix_world', 'faces', 'source_ids', 'poly_offsets', 'poly_vertices', 'triangle_polygon_ids'):
            assert np.array_equal(actual[field], initial[field]), (name, field)
        metrics = {}
        for group, ids in groups.items():
            metrics[group] = dict(before=statistics(initial_error, ids), after=statistics(final_error, ids))
            for position in ('before', 'after'):
                for field, value in metrics[group][position].items():
                    assert abs(value - score['metrics'][group][position][field]) < 1e-12, (name, group, position, field)
        np.testing.assert_array_equal(displacement[normal], 0)
        np.testing.assert_array_equal(displacement[outside], 0)
        with np.load(folder / 'SCORE_points.npz') as points:
            np.testing.assert_array_equal(points['final_error_world'], final_error)
            np.testing.assert_array_equal(points['displacement_world'], displacement)
        reduction = 1 - metrics['support_47']['after']['RMSE_m'] / metrics['support_47']['before']['RMSE_m']
        assert reduction >= .3 and metrics['observation_410']['after']['RMSE_m'] < metrics['observation_410']['before']['RMSE_m']
        assert statistics(displacement, normal_editable)['RMSE_m'] <= .0001
        state = read(BASE / 'private/sessions' / name / 'session.json')
        assert state['version'] == 1 and len(state['operations']) == 1 and state['pending'] is None
        public = BASE / 'private/consumers' / stage / 'matched' / route
        consumer = read(public / 'CONSUMER.json')
        events = [json.loads(line)['event'] for line in (public / 'events.jsonl').read_text(encoding='utf8').splitlines()]
        finished = [event for event in events if event['type'] == 'turn.completed']
        assert len(finished) == 1 and finished[0]['usage'] == consumer['usage']
        tools = [event['item'] for event in events if event['type'] == 'item.completed' and event['item']['type'] == 'mcp_tool_call']
        assert len(tools) == consumer['tool_count'] <= 12
        for response_path in (public / 'bridge').glob('tool_*/RESPONSE.json'):
            for block in read(response_path).get('content', []):
                if block['type'] == 'image':
                    data = base64.b64decode(block['data'], validate=True)
                    assert (hashlib.sha256(data).hexdigest(), len(data)) in known_png
                    image_blocks += 1
                    image_bytes += len(data)
        cases.append(dict(
            session=name, stage=stage, route=route, metrics=metrics,
            support_RMSE_reduction_fraction=reduction,
            changed_points=int(np.count_nonzero(np.linalg.norm(displacement, axis=1) > 1e-12)),
            normal_editable_misedit_RMSE_m=statistics(displacement, normal_editable)['RMSE_m'],
            actual_tools=len(tools), consumer_wall_s=consumer['wall_s'], usage=finished[0]['usage'],
        ))
    assert len(cases) == 4 and image_blocks == 48 and image_bytes == 19063285
    lattice_error = np.linalg.norm(initial['vertices_world'] - np.round(initial['vertices_world'] * 4096) / 4096, axis=1)
    detected = editable[lattice_error[editable] > 1e-6]
    usage = {key: sum(case['usage'][key] for case in cases) for key in cases[0]['usage']}
    result = dict(
        status='passed_fixed_case_saved_restoration', cases=cases,
        recomputed_damaged_normals=27304, image_blocks=image_blocks, PNG_bytes=image_bytes,
        actual_usage_from_raw_events=usage, actual_tools=sum(case['actual_tools'] for case in cases),
        consumer_wall_s=sum(case['consumer_wall_s'] for case in cases),
        frozen_native_grid_detector=dict(threshold_m=1e-6, detected=len(detected),
            true_positive=len(np.intersect1d(detected, support)), false_positive=len(np.setdiff1d(detected, support)), support_points=len(support)),
        artistic_acceptance=None, causal_image_benefit=None, new_Pro=0, new_Blender=0, new_training=0,
        wall_s=time.perf_counter() - started,
    )
    (HERE / 'RESULTS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}))


if __name__ == '__main__':
    main()
