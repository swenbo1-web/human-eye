"""Measure P2 from original CLI/tool events and attach the sealed historical costs."""

import argparse
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
OLD = NS.parent / 'perf050_readonly_product_pilot_001/consumer'
RUN = Path('D:/he_perf050_source_region_active_view_p2')
_prior = run_path(str(OLD / 'costs.py'))
read, digest, file_receipt, summarize = (
    _prior[name] for name in ('read', 'digest', 'file_receipt', 'summarize'))


def collect(run, output):
    old_cost = OLD / 'COSTS.json'
    original = read(old_cost)
    historical = original['slots']
    if [row['label'] for row in historical] != ['N1', 'P1']:
        raise ValueError('sealed_historical_pair_changed')
    freeze_path = NS / 'FROZEN.json'
    freeze = digest(freeze_path) if freeze_path.is_file() else None
    row = summarize(run / 'slots/P2', freeze)
    thread = row.get('thread_id')
    fresh = thread is not None and thread not in {x.get('thread_id') for x in historical}
    if row['status'] == 'completed' and not fresh:
        row['cost_evidence_verified'] = False
        row['cost_review_errors'].append('P2_did_not_bind_a_fresh_thread')
    data = {'schema': 'perf050-source-region-active-view-p2-original-costs-v1', 'freeze_sha256': freeze,
            'slots': [row], 'planned_consumers': 1, 'CLI_process_launches_observed': row['model_consumers_launched'],
            'distinct_fresh_threads': int(fresh), 'historical_reference': file_receipt(old_cost),
            'historical_slots': [{key: item.get(key) for key in (
                'label', 'status', 'raw_CLI_usage', 'input_plus_output_tokens', 'tool_wire_text_total_bytes',
                'tool_wire_PNG_bytes', 'CLI_public_PNG_count', 'CLI_public_PNG_bytes', 'clock_ms', 'budget')}
                                 for item in historical],
            'provider_timing': None, 'provider_billing': None,
            'scope': 'P2 is a single diagnostic slot. Tool waiting combines runtime and model call generation.'}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(f'{output.name} {digest(output)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'COSTS.json')
    args = parser.parse_args()
    collect(args.runtime, args.output)
