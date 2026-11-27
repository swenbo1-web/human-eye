"""Freeze one real packet, independent qualification, install identities and replay orders."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay_common import (ASSET, ASSET_SHA, BASE, RAW, SOURCE, TRUTH, dump,
                           installation, need, pin, read, verify)
from qualification import qualify


def freeze(capture_path, receipt_path, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = read(receipt_path)
    need(receipt['status'] == 'pass' and receipt['native_calls'] == 1 and receipt['solver_calls'] == 0, 'actual_post_business_capture')
    verify(receipt['capture'])
    need(Path(capture_path).resolve() == Path(receipt['capture']['path']).resolve(), 'capture_receipt_path')
    need(pin(ASSET)['sha256'] == ASSET_SHA, 'source_copy_sha')
    qualification = qualify(read(capture_path), SOURCE, TRUTH)
    gui_root = RAW.parent / 'live/main/H3'
    before, after = (read(gui_root / (label + '.json')) for label in ('BEFORE','AFTER'))
    need(before['layer'] == after['layer'] == qualification['view_layer_binding']['archived_name'],
         'current_h3_layer_name')
    need(all(before[k] == after[k] for k in ('frame','subframe','scale','layer')), 'current_h3_frame_preserved')
    qualification['current_h3_source_checks'] = {'before': pin(gui_root/'BEFORE.json'),
        'after': pin(gui_root/'AFTER.json'), 'layer_name': before['layer'],
        'note': 'QA layer name and capture native instance are distinct fields; no RNA ID backfill'}
    old = BASE / 's1/warm_diagnostic/cells/Yanyite_1_032/warm_high.json'
    public = read(old)['value']
    plan = {'schema': 'm6-042-fixed-input-replay-v1', 'contract': 'c7c00d98289',
            'capture': pin(capture_path), 'capture_receipt': pin(receipt_path),
            'source': pin(SOURCE), 'truth': pin(TRUTH), 'asset': pin(ASSET),
            'historical_public_receipt': pin(old), 'expected_public': public,
            'qualification': qualification,
            'query': read(TRUTH)['requests_A'][0]['arguments']['query'],
            'arms': {arm: installation(arm) for arm in ('032','r3')},
            'orders': [['032','r3'] if i % 2 == 0 else ['r3','032'] for i in range(7)],
            'phase_orders': [['plain','substages'] if i % 2 == 0 else ['substages','plain'] for i in range(7)],
            'reads_per_phase': ['first','repeat'], 'request_budget_s': 30.0,
            'scope': 'offline original selective service+projection replay, identical restored packet, fresh product process per arm and pair; no GUI or socket',
            'not_measured': ['native acquisition', 'native queue', 'real TCP', 'production stdio write'],
            'host_read': 'original service host_read stage receives frozen JSON decode; historical native host_capture stages are carried provenance only, never added',
            'observer': 'substages temporarily wraps only source_region.measure_surface_proximity and _witness_sources with entry/return clocks; plain has neither wrapper',
            'additivity': 'within each request outer differences only; task_measurement contains solver and witness membership, never summed with their children',
            'sources': {p.name: pin(p) for p in HERE.glob('*.py')}}
    dump(output, plan)
    return pin(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', default=str(RAW/'capture_01/CAPTURE.json'))
    parser.add_argument('--receipt', default=str(RAW/'capture_01/RECEIPT.json'))
    parser.add_argument('--output', default=str(RAW/'PLAN.json'))
    args = parser.parse_args()
    print(freeze(args.capture, args.receipt, args.output))
