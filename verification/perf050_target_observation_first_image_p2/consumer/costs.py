"""Collect the sole P2's real consumer costs with published historical references."""

import argparse
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUN = Path('D:/he_perf050_target_observation_first_image_p2')
TRANSFER = NS.parent / 'perf050_readonly_product_transfer_001'
P3 = NS.parent / 'perf050_source_region_final_image_p3'
_prior = run_path(str(P3 / 'consumer/costs.py'))
read, digest, file_receipt, summarize, first_image = (
    _prior[k] for k in ('read', 'digest', 'file_receipt', 'summarize', 'observed_first_image'))


def collect(run, output):
    freeze_path = NS / 'FROZEN.json'
    freeze = read(freeze_path)
    frozen = digest(freeze_path) if freeze else None
    previous = TRANSFER / 'consumer/COSTS.json'
    old = read(previous)['slots']
    if [row['label'] for row in old] != ['N1', 'P1']:
        raise ValueError('original_transfer_pair_denominator_changed')
    slot = run / 'slots/P2'
    row = summarize(slot, frozen)
    thread = row.get('thread_id')
    fresh = thread is not None and thread not in {item.get('thread_id') for item in old}
    if row['status'] == 'completed':
        if not fresh or row.get('initial_prompt_sha256') != freeze.get('prompt_sha256'):
            row['cost_review_errors'].append('P2_thread_not_fresh_or_frozen_prompt_mismatch')
            row['cost_evidence_verified'] = False
    row['first_image_delivery'] = first_image(slot, row)
    fields = ('label', 'status', 'raw_CLI_usage', 'input_plus_output_tokens', 'tool_wire_text_total_bytes',
              'tool_wire_PNG_bytes', 'CLI_public_PNG_count', 'CLI_public_PNG_bytes', 'clock_ms')
    result = {'schema': 'perf050-target-observation-first-image-p2-costs-v1', 'freeze_sha256': frozen,
              'slots': [row], 'planned_consumers': 1, 'CLI_process_launches_observed': row['model_consumers_launched'],
              'distinct_fresh_threads': int(fresh), 'historical_reference': file_receipt(previous),
              'historical_slots': [{key: item.get(key) for key in fields} for item in old],
              'provider_timing': None, 'provider_billing': None}
    with output.open('x', encoding='utf8', newline='\n') as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'COSTS.json')
    args = parser.parse_args()
    collect(args.runtime, args.output)
