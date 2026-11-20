"""Replay the registered CLI presentation limits without starting a consumer."""

from pathlib import Path
import runpy


POLICY = Path(__file__).resolve().parents[2] / 'm4_cross_scale_live_qualification_001/checks/delivery.py'


def replay(value):
    helpers, limits = runpy.run_path(str(POLICY))['budget_helpers']()
    if (limits['MCP_bytes'], limits['history_approximate_tokens']) != (12000, 3000):
        raise ValueError('registered_CLI_limits_changed')
    stages = []
    for seconds, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        initial = helpers['model_items'](value, seconds)
        if len(initial[0]['text'].encode()) != header:
            raise ValueError('registered_CLI_header_length_changed')
        first = helpers['truncate_items'](initial, 12000)
        second = helpers['truncate_items'](first, 3000, token_mode=True)
        images = [row for row in initial if row['type'] == 'input_image']
        stages.append({'header_bytes': header, 'MCP_exact': first == initial, 'history_exact': second == initial,
                       'PNG_exact': all([row for row in stage if row['type'] == 'input_image'] == images
                                        for stage in (first, second))})
    return {'passed': all(stage['MCP_exact'] and stage['history_exact'] and stage['PNG_exact'] for stage in stages),
            'original_image_count': sum(row['type'] == 'image' for row in value['content']),
            'limits': limits, 'stages': stages}
