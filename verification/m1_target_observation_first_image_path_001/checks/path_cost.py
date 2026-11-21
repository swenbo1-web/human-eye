"""Measure the path-only projection on the fixed, already rendered P1 evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter_ns


NS = Path(__file__).resolve().parents[1]
P1 = Path('D:/he_perf050_readonly_product_transfer_001/slots/P1')
TRANSFER = NS.parent / 'perf050_readonly_product_transfer_001'
SAMPLES = 60


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def summarize(samples):
    order = sorted(samples)
    return {'median_ns': statistics.median(order), 'p95_ns': order[(95 * len(order) + 99) // 100 - 1],
            'minimum_ns': order[0], 'maximum_ns': order[-1]}


def measure():
    install_path = NS / 'install/PRODUCT_RUN_BINDING.json'
    install = read(install_path)
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp

    assert Path(mcp.__file__).is_relative_to(install['install_root'])
    saved_path = P1 / 'product_full/call_002/SERVICE_RESULT.json'
    replay = read(saved_path)
    image_root = P1 / 'product_state.json.active_observation'
    history_path = TRANSFER / 'consumer/COSTS.json'
    history, = [row for row in read(history_path)['slots'] if row['label'] == 'P1']
    first, repeat = history['actual_requests'][1:]
    assert [first['attempt'], repeat['attempt']] == [2, 3]
    stage, outer_off, outer_on = [], [], []
    check_paths = mcp._project_target_observation_image_paths
    stage_elapsed = None

    def measure_check(*args):
        nonlocal stage_elapsed
        before = perf_counter_ns()
        check_paths(*args)
        stage_elapsed = perf_counter_ns() - before

    def run(root):
        start = perf_counter_ns()
        result = mcp._tool_result(replay, is_error=False, response_detail='brief',
                                  target_observation_image_root=root)
        elapsed = perf_counter_ns() - start
        return result, elapsed

    mcp._project_target_observation_image_paths = measure_check
    try:
        old, _ = run(None)
        new, _ = run(image_root)
        brief = json.loads(new['content'][0]['text'])
        assert brief['images']['columns'][-1] == 'local_image_path'
        assert brief['images']['rows'][0][-1] is None
        assert Path(brief['images']['rows'][1][-1]).is_relative_to(image_root)
        assert new['content'][1:] == old['content'][1:]
        for i in range(12 + SAMPLES):
            paths = (image_root, None) if i % 2 else (None, image_root)
            for root in paths:
                result, elapsed = run(root)
                assert result == (new if root is not None else old)
                if i >= 12:
                    if root is None:
                        outer_off.append(elapsed)
                    else:
                        outer_on.append(elapsed)
                        stage.append(stage_elapsed)
    finally:
        mcp._project_target_observation_image_paths = check_paths
    return {
        'schema': 'm1-target-observation-first-image-path-offline-cost-v1',
        'build': install['preparation_git'], 'runtime_source_sha256': install['source_sha256'],
        'pins': [pin(path) for path in (install_path, saved_path, history_path)],
        'samples_per_arm': SAMPLES, 'warmup_pairs': 12,
        'path_projection_stage': summarize(stage),
        'candidate_serializer_without_image_root': summarize(outer_off),
        'candidate_serializer_with_image_root': summarize(outer_on),
        'candidate_serializer_paired_delta': summarize([on - off for on, off in zip(outer_on, outer_off, strict=True)]),
        'raw_path_projection_ns': stage, 'raw_candidate_serializer_without_image_root_ns': outer_off,
        'raw_candidate_serializer_with_image_root_ns': outer_on,
        'archived_P1_attempt_2': {
            'MCP_RTT_ms': first['tool_wire_RTT_ms'],
            'dispatch_to_CLI_result_ms': first['dispatch_to_CLI_result_ms'],
            'stdio_RX': first['stdio_RX'],
        },
        'archived_P1_attempt_3': {
            'MCP_RTT_ms': repeat['tool_wire_RTT_ms'],
            'dispatch_to_CLI_result_ms': repeat['dispatch_to_CLI_result_ms'],
            'owner_window_ms': repeat['owner_window_ms'],
            'after_attempt_2_ms': repeat['after_previous_result_ms'],
            'stdio_RX': repeat['stdio_RX'],
            'wire_content': repeat['wire_content'],
        },
        'scope': 'Alternating in-process serialization against existing files with a warm filesystem. '
                 'Historical P1 times are observations from the original slot.',
    }


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=NS / 'checks/PATH_COST.json')
    args = cli.parse_args()
    result = measure()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
