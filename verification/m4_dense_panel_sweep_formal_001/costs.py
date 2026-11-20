"""Measure original per-slot envelopes, wire, work and raw CLI usage."""

import argparse
from pathlib import Path
from statistics import median
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import publication, verify_freeze
from common import EXTERNAL, SLOTS, load, read, save, sha


RETAINED = NS.parent / 'm4_cross_scale_live_task_formal_001/costs.py'
FORMAL_ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
USAGE_FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                'output_tokens', 'reasoning_output_tokens')


def raw_usage(path, events, completed):
    if not path.is_file():
        if completed:
            raise ValueError('completed_formal_slot_missing_CLI_record')
        return None
    consumer = read(path)
    if events != consumer['raw_usage_events']:
        raise ValueError('raw_turn_completed_usage_does_not_match_the_actual_record')
    if not events:
        return None
    if (len(events) != 1 or any(type(events[0].get(key)) is not int or events[0][key] < 0 for key in USAGE_FIELDS)):
        raise ValueError('expected_single_raw_CLI_usage_receipt')
    use = {key: events[0][key] for key in USAGE_FIELDS}
    use['input_plus_output_tokens'] = use['input_tokens'] + use['output_tokens']
    return use


def summarize(label, freeze, retained):
    slot = EXTERNAL / 'slots' / label
    if not slot.exists():
        return {'label': label, 'phase': SLOTS[label][1], 'arm': SLOTS[label][0], 'status': 'unrun',
                'model_consumers': 0}
    result, published = publication(label, freeze)
    row = retained.slot_summary(label)
    if row['publication_sha256'] != sha(slot / 'SLOT_PUBLICATION.json'):
        raise ValueError('original_cost_row_lost_its_slot_binding')
    row.update(status=published['status'], phase=result['phase'], arm=result['group'],
               result_sha256=published['result_sha256'], asset_sha256=result['asset_sha256'])
    consumer_path = slot / 'consumer/CONSUMER.json'
    row['usage'] = raw_usage(consumer_path, row['original_CLI_usage'],
                             result['phase'] == 'formal' and row['status'] == 'completed')
    row['thread_id'] = read(consumer_path).get('thread_id') if consumer_path.is_file() else None
    last = row['attempts'][-1]['CLI_received_ns'] if row['attempts'] else None
    first = next((attempt['CLI_received_ns'] for attempt in row['attempts']
                  if attempt['CLI_received_ns'] is not None and not attempt['error']), None)
    row['first_to_last_tool_result_ms'] = retained.elapsed(first, last)
    row['total_between_tool_ms'] = sum(attempt['previous_CLI_result_to_tool_request_ms']
        for attempt in row['attempts'] if attempt['previous_CLI_result_to_tool_request_ms'] is not None)
    row['tool_owner_total_ms'] = sum(attempt['owner_window_ms'] for attempt in row['attempts']
                                     if attempt['owner_window_ms'] is not None)
    row['total_tool_dispatch_to_CLI_ms'] = sum(attempt['tool_request_to_CLI_result_ms']
        for attempt in row['attempts'] if attempt['tool_request_to_CLI_result_ms'] is not None)
    row['no_image_full_attempts'] = []
    for attempt in row['attempts']:
        folder = slot / 'owner' / f"tool_{attempt['attempt']:02d}"
        request = read(folder / 'REQUEST.json')
        receipt = read(folder / 'RECEIPT.json')
        attempt['config'] = {'argument_keys': sorted(request['params']['arguments']),
                             'request_label': receipt.get('tool')}
        arguments = attempt.get('product_request_arguments') or {}
        if arguments.get('include_image') is False and arguments.get('response_detail') == 'full':
            row['no_image_full_attempts'].append({'attempt': attempt['attempt'], 'text_bytes': attempt['text_bytes'],
                'CLI_text_bytes': attempt['CLI_text_bytes'], 'product_rpc_ms': attempt.get('product_rpc_ms')})
    cfg_path = slot / 'consumer/ACTUAL_CONFIGURATION.json'
    if cfg_path.is_file():
        cfg = read(cfg_path)
        row['requested_CLI'] = {'model': cfg['requested_model'], 'effort': cfg['requested_effort'],
                                'service_tier': cfg['requested_service_tier'],
                                'config_sha256': sha(cfg_path), 'fallback_state': cfg['fallback_state']}
    return row


def comparison(rows):
    indexed = {row['label']: row for row in rows}
    pairs = []
    for i in range(1, 4):
        a, b = [indexed[f'{arm}{i}'] for arm in ('N', 'P')]
        original, plugin = a.get('full_window_ms'), b.get('full_window_ms')
        comparable = all(row['status'] == 'completed' and row.get('usage') for row in (a, b))
        pairs.append({'pair': i, 'native_label': a['label'], 'plugin_label': b['label'],
                      'native_full_window_ms': original, 'plugin_full_window_ms': plugin,
                      'complete_originals': comparable,
                      'plugin_fractional_time_reduction': (original - plugin) / original if comparable else None})
    complete = [row for row in pairs if row['complete_originals']]
    speeds = [row['plugin_fractional_time_reduction'] for row in complete]
    usage_by_arm = {}
    for arm in ('N', 'P'):
        usage = [indexed[f'{arm}{i}'].get('usage') for i in range(1, 4)]
        usage_by_arm[arm] = ({key: sum(item[key] for item in usage) for key in usage[0]}
                             if all(item is not None for item in usage) else None)
    trade = (usage_by_arm['P']['input_plus_output_tokens'] - usage_by_arm['N']['input_plus_output_tokens']
             if all(usage_by_arm.values()) else None)
    thread_ids = [indexed[label].get('thread_id') for label in FORMAL_ORDER if indexed[label].get('thread_id')]
    return {'paired_slots_planned': 3, 'pairs': pairs, 'complete_pair_count': len(complete),
            'median_plugin_fractional_time_reduction': median(speeds) if speeds else None,
            'plugin_faster_pairs': sum(speed > 0 for speed in speeds),
            'raw_CLI_usage_totals_by_arm': usage_by_arm, 'plugin_input_plus_output_tokens_delta': trade,
            'actual_fresh_thread_ids': thread_ids, 'unique_fresh_threads': len(set(thread_ids)) == len(thread_ids),
            'time_gate_passed': len(complete) == 3 and median(speeds) >= .10 and sum(speed > 0 for speed in speeds) >= 2,
            'CLI_usage_gate_passed': len(complete) == 3 and trade is not None and trade <= 0}


def collect():
    frozen_path = NS / 'FROZEN.json'
    freeze = verify_freeze(frozen_path)
    retained = load('_dense_formal_retained_costs', RETAINED)
    retained.NS, retained.EXTERNAL = NS, EXTERNAL
    rows = [summarize(label, freeze, retained) for label in SLOTS]
    gate = NS / 'QUALIFICATION.json'
    prepared = read(frozen_path)
    external_qp = prepared['external_qp']
    score = read(Path(external_qp['review_path']))
    save(NS / 'RUNTIME_REVIEW.json', {'schema': 'm4-dense-panel-sweep-formal-runtime-cost-v1',
        'freeze_sha256': freeze, 'qualification_sha256': sha(gate) if gate.is_file() else None,
        'freeze_registration_ms': (prepared['completed_ns'] - prepared['started_ns']) / 1e6,
        'external_QP_sealed_source': external_qp, 'prior_QP_outside_new_run_cost': score['timing'],
        'slots': rows, 'formal_comparison': comparison(rows), 'new_asset_builds': 0, 'external_paid_API': 0,
        'cash_fees': None, 'provider_identity': None, 'actual_internal_provider_input': None,
        'model_internal_timing': None})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    collect()
