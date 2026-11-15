"""Independently recompute the two saved failed repairs and their actual inputs."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import time

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6dg4/batch'
HELPERS = runpy.run_path(str(HERE.parent / 'm6_matched_refine_003_review/review.py'))
statistics = HELPERS['statistics']
current_normals = HELPERS['current_normals']


def read(path):
    return json.loads(path.read_bytes())


def main():
    started = time.perf_counter()
    binding = read(BASE / 'CASE_BINDING.json')
    for source in binding['source_files']:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    with np.load(BASE / 'private/scoring/target.npz') as packet:
        target = {key: packet[key] for key in packet.files}
    with np.load(BASE / 'private/cases/repair/initial.npz') as packet:
        initial = {key: packet[key] for key in packet.files}
    with np.load(BASE / binding['normal_readback']['path']) as normal:
        np.testing.assert_array_equal(target['clean_vertices_world'], normal['vertices_world'])
        changed = np.flatnonzero(np.any(initial['vertices_local'] != normal['vertices_local'], axis=1))
        np.testing.assert_array_equal(changed, target['support_ids'])
    with np.load(BASE / binding['actual_initial_readback']['path']) as actual:
        for key in actual.files:
            np.testing.assert_array_equal(actual[key], initial[key])
    assert len(initial) == 16
    np.testing.assert_allclose(current_normals(initial['vertices_world'], initial['faces']), initial['n0'], rtol=0, atol=1e-12)
    region, editable, support = target['F_source_ids'], target['I_ids'], target['support_ids']
    normal_ids, normal_editable = np.setdiff1d(region, support), np.setdiff1d(editable, support)
    outside = np.setdiff1d(initial['source_ids'], editable)
    assert tuple(map(len, (region, editable, support, normal_ids, normal_editable))) == (410, 274, 47, 363, 227)
    noise = np.zeros_like(target['clean_vertices_world'])
    noise[region] = np.random.default_rng(2026111604).uniform(-1/8192, 1/8192, size=(len(region), 3))
    assert hashlib.sha256(noise.tobytes()).hexdigest() == binding['noise_array_sha256']
    groups = dict(support_47=support, observation_410=region, normal_363=normal_ids, normal_editable_227=normal_editable)
    before_error = initial['vertices_world'] - target['clean_vertices_world']
    pngs = {(row['sha256'], row['bytes']) for row in read(BASE / 'MANIFEST.json')['files'] if row['path'].endswith('.png')}
    cases = []
    PNG_blocks = PNG_bytes = 0
    prompt_hashes = set()
    for session in read(BASE / 'FINAL_VERIFICATION.json')['sessions']:
        name, stage, route = session['session'], session['stage'], session['route']
        folder = BASE / 'private/final_verify' / name
        score = read(folder / 'SCORE.json')
        with np.load(folder / 'readback.npz') as packet:
            actual = {key: packet[key] for key in packet.files}
        final_error = actual['vertices_world'] - target['clean_vertices_world']
        delta = actual['vertices_world'] - initial['vertices_world']
        np.testing.assert_array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
        np.testing.assert_array_equal(delta[outside], 0)
        for key in ('matrix_world', 'faces', 'source_ids', 'poly_offsets', 'poly_vertices', 'triangle_polygon_ids'):
            np.testing.assert_array_equal(actual[key], initial[key])
        metrics = {}
        for group, ids in groups.items():
            metrics[group] = dict(before=statistics(before_error, ids), after=statistics(final_error, ids))
            for position in ('before', 'after'):
                for key, value in metrics[group][position].items():
                    assert abs(value - score['metrics'][group][position][key]) < 1e-12, (name, group, position, key)
        reduction = 1 - metrics['support_47']['after']['RMSE_m'] / metrics['support_47']['before']['RMSE_m']
        normal_misedit = statistics(delta, normal_editable)
        passed = (reduction >= .3 and metrics['observation_410']['after']['RMSE_m'] < metrics['observation_410']['before']['RMSE_m']
                  and normal_misedit['RMSE_m'] <= .0001)
        assert passed is False and score['restoration_quality_pass'] is False
        with np.load(folder / 'SCORE_points.npz') as points:
            np.testing.assert_array_equal(points['final_error_world'], final_error)
            np.testing.assert_array_equal(points['displacement_world'], delta)
        active = np.flatnonzero(np.linalg.norm(delta, axis=1) > 1e-12)
        state = read(BASE / 'private/sessions' / name / 'session.json')
        assert state['version'] == 1 and len(state['operations']) == 1 and state['pending'] is None
        public = BASE / 'private/consumers' / stage / 'repair' / route
        consumer = read(public / 'CONSUMER.json')
        events = [json.loads(line)['event'] for line in (public / 'events.jsonl').read_text(encoding='utf8').splitlines()]
        usage = [event['usage'] for event in events if event['type'] == 'turn.completed']
        assert len(usage) == 1 and usage[0] == consumer['usage']
        tools = [event['item'] for event in events if event['type'] == 'item.completed' and event['item']['type'] == 'mcp_tool_call']
        assert len(tools) == consumer['tool_count'] == 10
        prompt_hashes.add(hashlib.sha256((public / 'PROMPT.txt').read_bytes()).hexdigest())
        for response_path in (public / 'bridge').glob('tool_*/RESPONSE.json'):
            for block in read(response_path).get('content', []):
                if block['type'] == 'image':
                    data = base64.b64decode(block['data'], validate=True)
                    assert (hashlib.sha256(data).hexdigest(), len(data)) in pngs
                    PNG_blocks += 1
                    PNG_bytes += len(data)
        cases.append(dict(
            session=name, route=route, metrics=metrics, support_RMSE_reduction_fraction=reduction,
            normal_editable_misedit=normal_misedit, changed_points=len(active),
            TP=len(np.intersect1d(active, support)), FP=len(np.setdiff1d(active, support)), FN=len(np.setdiff1d(support, active)),
            quality_pass=passed, technical_QA=score['technical_quality'],
            tools=len(tools), tool_statuses=dict(Counter(tool['status'] for tool in tools)),
            usage=usage[0], wall_s=consumer['wall_s'],
        ))
    assert len(cases) == 2 and len(prompt_hashes) == 1
    assert PNG_blocks == 24 and PNG_bytes == 9533093
    totals = {key: sum(case['usage'][key] for case in cases) for key in cases[0]['usage']}
    result = dict(
        status='accepted_delivery_two_repair_quality_failures', cases=cases,
        current_normals_recomputed=27304, noise_sha_matches=True,
        actual_image_blocks=PNG_blocks, PNG_bytes=PNG_bytes, actual_usage=totals,
        actual_tools=sum(case['tools'] for case in cases), wall_s_consumers=sum(case['wall_s'] for case in cases),
        new_Pro=0, new_Blender=0, new_training=0, independent_full_contact_rescan=False,
        wall_s=time.perf_counter() - started,
    )
    (HERE / 'RESULTS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in result.items() if key != 'cases'}))


if __name__ == '__main__':
    main()
