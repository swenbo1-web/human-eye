"""Measure the sole P3 slot from original CLI, wire and host receipts."""

import argparse
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
P2 = NS.parent / 'perf050_source_region_active_view_p2'
RUN = Path('D:/he_perf050_source_region_final_image_p3')
_prior = run_path(str(PILOT / 'consumer/costs.py'))
read, digest, file_receipt, summarize, elapsed = (
    _prior[name] for name in ('read', 'digest', 'file_receipt', 'summarize', 'elapsed'))


def observed_first_image(slot, row):
    source = read(slot / 'consumer/CONSUMER.json') or read(slot / 'consumer/CONSUMER_STARTED.json')
    first = next((attempt for attempt in row.get('actual_requests', [])
                  if attempt['CLI_binding'] == 'content_and_envelope_match'
                  and attempt['CLI_delivered_images'] and attempt['wire_content']['PNG']
                  and not attempt['wire_content']['error']), None)
    if first is None:
        return None
    arrived = first['CLI_received_ns']
    return {'attempt': first['attempt'], 'CLI_received_ns': arrived,
            'prompt_to_first_image_ms': elapsed(source.get('prompt_submitted_ns'), arrived),
            'dispatch_to_first_image_result_ms': first['dispatch_to_CLI_result_ms'],
            'CLI_delivered_images': first['CLI_delivered_images'],
            'original_wire_PNG': first['wire_content']['PNG']}


def collect(run, output):
    old_costs = (PILOT / 'consumer/COSTS.json', P2 / 'consumer/COSTS.json')
    historical = [row for path in old_costs for row in read(path)['slots']]
    if [row['label'] for row in historical] != ['N1', 'P1', 'P2']:
        raise ValueError('sealed_historical_pair_or_P2_changed')
    freeze_path = NS / 'FROZEN.json'
    freeze = digest(freeze_path) if freeze_path.is_file() else None
    slot = run / 'slots/P3'
    row = summarize(slot, freeze)
    thread = row.get('thread_id')
    fresh = thread is not None and thread not in {previous.get('thread_id') for previous in historical}
    if row['status'] == 'completed' and not fresh:
        row['cost_evidence_verified'] = False
        row['cost_review_errors'].append('P3_did_not_bind_a_fresh_thread')
    row['first_image_delivery'] = observed_first_image(slot, row)
    fields = ('label', 'status', 'raw_CLI_usage', 'input_plus_output_tokens', 'tool_wire_text_total_bytes',
              'tool_wire_PNG_bytes', 'CLI_public_PNG_count', 'CLI_public_PNG_bytes', 'clock_ms', 'budget')
    data = {'schema': 'perf050-source-region-final-image-p3-original-costs-v1', 'freeze_sha256': freeze,
            'slots': [row], 'planned_consumers': 1, 'CLI_process_launches_observed': row['model_consumers_launched'],
            'distinct_fresh_threads': int(fresh), 'historical_reference': [file_receipt(path) for path in old_costs],
            'historical_slots': [{key: previous.get(key) for key in fields} for previous in historical],
            'provider_timing': None, 'provider_billing': None,
            'scope': 'P3 is a single diagnostic slot. Tool waiting includes time for model call generation and runtime.'}
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
