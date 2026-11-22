"""Measure both genuinely new transfer slots from original events and receipts."""

import argparse
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PILOT = NS.parent / 'perf050_readonly_product_transfer_001'
P3 = NS.parent / 'perf050_source_region_final_image_p3'
RUN = Path('D:/he_perf050_dense_micro_surface_holdout_recovery_001')
LABELS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
prior = run_path(str(PILOT / 'consumer/costs.py'))
read, digest, file_receipt, summarize = (
    prior[name] for name in ('read', 'digest', 'file_receipt', 'summarize'))
observed_first_image = run_path(str(P3 / 'consumer/costs.py'))['observed_first_image']


def collect(run, output):
    freeze_file = NS / 'FROZEN.json'
    frozen = read(freeze_file)
    freeze = digest(freeze_file) if frozen else None
    receipt = read(PILOT / 'consumer/COSTS.json')
    p3 = read(P3 / 'consumer/COSTS.json')
    old_threads = {row.get('thread_id') for row in receipt['slots'] + p3['slots']}
    rows = []
    fresh = set()
    for label in LABELS:
        slot = run / 'slots' / label
        row = summarize(slot, freeze)
        row['first_image_delivery'] = observed_first_image(slot, row)
        if row['status'] == 'completed':
            thread_id = row['thread_id']
            if thread_id is None or thread_id in old_threads or thread_id in fresh:
                row['cost_review_errors'].append('not_a_distinct_new_transfer_thread')
            else:
                fresh.add(thread_id)
            if row['initial_prompt_sha256'] != frozen.get('prompt_sha256'):
                row['cost_review_errors'].append('consumer_input_does_not_match_frozen_common_prompt')
            if row['cost_review_errors']:
                row['cost_evidence_verified'] = False
        rows.append(row)
    data = {'schema': 'perf050-dense-micro-surface-holdout-recovery-original-costs-v1', 'freeze_sha256': freeze,
            'slots': rows, 'planned_consumers': len(LABELS),
            'CLI_process_launches_observed': sum(row['model_consumers_launched'] for row in rows),
            'distinct_fresh_threads': len(fresh), 'historical_consumers_in_denominator': 0,
            'provider_timing': None, 'provider_billing': None,
            'scope': 'Three frozen pairs on one fixture. Provider internal timing and billing are unobserved.'}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(f'{output.name} {digest(output)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'COSTS.json')
    args = parser.parse_args()
    collect(args.runtime, args.output)
