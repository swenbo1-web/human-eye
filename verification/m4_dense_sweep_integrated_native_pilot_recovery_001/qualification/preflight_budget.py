"""Exercise the recovery's production budget verifier without altering originals."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path


module = run_path(str(Path(__file__).with_name('budget.py')))
verify, require, digest = (module[name] for name in ('verify', 'require', 'digest'))


def encode(record):
    return (json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n').encode()


def preflight(old_root):
    root = Path(old_root).resolve(strict=True)
    known = verify(root)
    slots = root / 'slots'
    settlements = root / 'budget/settlements'
    native = slots / 'QN'
    product = slots / 'QP'
    q, = (row for row in known['by_slot']['QP']['evidence'] if row['ordinal'] == 1)
    q2, = (row for row in known['by_slot']['QP']['evidence'] if row['ordinal'] == 2)
    first = settlements / f'{q["claim_token"]}.json'
    second = settlements / f'{q2["claim_token"]}.json'
    claim_path = root / 'budget/claims' / first.name

    def changed(path, update):
        data = json.loads(path.read_bytes())
        update(data)
        return encode(data)

    def result_override(change):
        path = product / 'SLOT_RESULT.json'
        receipt = product / 'SLOT_PUBLICATION.json'
        data = changed(path, change)
        return {path: data, receipt: changed(receipt, lambda row: row.update(result_sha256=digest(data)))}

    def invalid_clock(row):
        result = json.loads((product / 'SLOT_RESULT.json').read_bytes())
        row.update(published_ns=result['owned_deadline_ns'],
                   complete_slot_ns=result['owned_deadline_ns'] - result['started_ns'])

    def duplicate_native(row):
        attempts = [event for event in row['events'] if event['event'] == 'native_raster_attempt']
        attempts[1]['ordinal'] = attempts[0]['ordinal']

    audit = product / 'product_audit.jsonl'
    row = next(line for line in audit.read_bytes().splitlines(keepends=True)
               if json.loads(line)['event'] == 'active_observation_render_attempt')
    first_evidence = json.loads(first.read_bytes())['evidence']
    controls = [
        ('missing_claim', {claim_path: None}, 'FileNotFoundError'),
        ('missing_settlement', {first: None}, 'FileNotFoundError'),
        ('duplicate_claim_token', {claim_path: changed(claim_path, lambda r: r.update(token=q2['claim_token']))},
         'original_claim_token_duplicate_or_detached'),
        ('wrong_settlement_token', {first: changed(first, lambda r: r.update(token=q2['claim_token']))},
         'original_settlement_token_digest_or_clock_invalid'),
        ('wrong_claim_sha256', {first: changed(first, lambda r: r.update(claim_sha256='0'*64))},
         'original_settlement_token_digest_or_clock_invalid'),
        ('wrong_claim_owner_phase', {claim_path: changed(claim_path, lambda r: r.update(label='N1', phase='formal'))},
         'original_claim_cross_slot_phase_or_formal_escape'),
        ('cross_qualifier_charge', {claim_path: changed(claim_path, lambda r: r.update(label='QN'))},
         'original_claim_over_limit_or_outside_slot'),
        ('over_reservation', {claim_path: changed(claim_path, lambda r: r.update(reserved_upper_bound=2))},
         'original_claim_over_limit_or_outside_slot'),
        ('over_settlement', {first: changed(first, lambda r: r.update(actual_attempts=2))},
         'original_raster_reservation_unsettled_over_cap_or_unconfirmed'),
        ('cross_slot_audit_reference',
         {first: changed(first, lambda r: r['evidence'].update(audit_path=str(native/'product_audit.jsonl')))},
         'product_raster_audit_slice_wrong_or_repeated'),
        ('reused_audit_slice', {second: changed(second, lambda r: r.update(evidence=deepcopy(first_evidence)))},
         'product_raster_audit_slice_wrong_or_repeated'),
        ('duplicate_audit_event', {audit: audit.read_bytes()+row}, 'product_raster_producer_attempt_roster_invalid'),
        ('duplicate_native_ordinal', {native/'DEVICE_EVIDENCE.json': changed(native/'DEVICE_EVIDENCE.json',duplicate_native)},
         'native_raster_ordinal_or_owner_roster_invalid'),
        ('wrong_cumulative_count', result_override(lambda r: r['budget']['counts'].update(all_raster_actual=3)),
         'original_cumulative_budget_or_pending_count_disagrees'),
        ('unsettled_pending_raster', result_override(lambda r: r['budget']['counts'].update(pending_raster_reservations=1)),
         'original_cumulative_budget_or_pending_count_disagrees'),
        ('wrong_slot_count', result_override(lambda r: r['budget']['slots']['QP'].update(raster_actual=5)),
         'original_slot_budget_snapshot_and_raw_settlements_disagree'),
        ('late_publication', {product/'SLOT_PUBLICATION.json': changed(product/'SLOT_PUBLICATION.json', invalid_clock)},
         'original_close_or_published_timing_invalid'),
        ('unconfirmed_blender_handle', {native/'RUNTIME_CLOSE.json': changed(native/'RUNTIME_CLOSE.json',
                                         lambda r: r['Blender_exit'].update(handle_closed=False))},
         'original_close_or_published_timing_invalid'),
        ('wrong_product_eof', {product/'mcp_io/EOF.json': changed(product/'mcp_io/EOF.json',
                                                                lambda r: r.update(input_eof_observed=False))},
         'original_production_mcp_close_eof_or_exit_invalid'),
    ]
    verified = []
    for name, replacements, expected in controls:
        def substituted(path):
            if path not in replacements:
                return path.read_bytes()
            if replacements[path] is None:
                raise FileNotFoundError(path.name)
            return replacements[path]

        try:
            verify(root, read_bytes=substituted)
        except (FileNotFoundError, ValueError) as error:
            actual = 'FileNotFoundError' if isinstance(error, FileNotFoundError) else str(error)
            require(actual == expected, f'{name}: {actual} != {expected}')
        else:
            raise ValueError(f'{name}: bad originals were accepted')
        verified.append({'case': name, 'rejected_for': expected})
    require(verify(root) == known, 'original_budget_bytes_changed_during_preflight')
    return {'passed': True, 'real_originals': known['by_slot'], 'historical_total': known['historical_total'],
            'negative_controls': verified, 'source_pins': known['source_pins'],
            'actual_Blender_starts': 0, 'actual_model_starts': 0}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('old_root', type=Path)
    cli.add_argument('output', type=Path)
    args = cli.parse_args()
    proof = preflight(args.old_root)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(f'{len(proof["negative_controls"])} control rejections; QN 2, QP 3; totals 2 and 5')
