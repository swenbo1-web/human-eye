"""Use the admitted source-region CLI scorer for the fixed rail holdout."""

import argparse
from fractions import Fraction
from math import sqrt
from pathlib import Path
import re
from runpy import run_path
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m4_rail_source_region_product_native_001')
OFFLINE_SLOTS = RUN / 'preflight/score_replay/slots'
BASE_PATH = V / 'm4_source_region_score_admission_001/score.py'
CLOSE_PATH = V / 'm4_dense_panel_sweep_formal_001/harness/closure.py'
BASE = SimpleNamespace(**run_path(str(BASE_PATH)))
ASSEMBLY = BASE.ASSEMBLY
replace = BASE.OLD.with_replacements
load, pin, require, write = BASE.load, BASE.pin, BASE.require, BASE.write
ready_closure = run_path(str(CLOSE_PATH))['ready_closure']
ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
TERMINAL_SHA = 'c93e4f8629e13bf8912b56d073bde4a6b17ea73dfb98747cdbd79c9d11acc5be'
SOURCE_ROOT = Path('D:/he_perf050_readonly_product_transfer_001/slots/P1')
CAPTURE_ROOT = Path('D:/he_m4_rail_blocker_consumption_formal_001/slots/B1')
CAPTURE_SHA = '3d356d6be536055337c6c20d54515a0e0792c5bfe9b51d85c2311abeef4dae3d'
BOXES = {'M19': ((20.4, -3.2, 3.2), (22.1, -.8, 4.8)),
         'M21': ((31.49, 1.99, 2.99), (33.1, 4.01, 3.01))}
REFERENCES = {'M19': 'M14', 'M21': 'M13'}
ROWS = {'M19': [0, 3, 8, 9, 10, 11], 'M21': [2, 3]}
COUNTS = {'M19': 6, 'M21': 4}
SQUARED = {'M19': Fraction(117, 64), 'M21': Fraction(1, 4)}
THRESHOLD = Fraction(1)
THRESHOLD_KEY = 'at_least_1_0_m'
PRODUCT_SOURCES = ASSEMBLY.PRODUCT_SOURCES
REQUIRED = tuple(f'{region}.{criterion}' for region in BOXES for criterion in BASE.OLD.REGIONAL_ITEMS) + ('nearer',)
region_truth = replace(ASSEMBLY.region_truth, EXPECTED={key: (rows, sqrt(SQUARED[key])) for key, rows in ROWS.items()},
                       REFERENCES=REFERENCES, THRESHOLD=THRESHOLD)


def scene_truth(terminal):
    context = terminal['source']
    require(context['asset_sha256'] == ASSET and context['kind'] == 'actual_owned_Blender_evaluated_mesh'
            and context['scale_length'] == 1 and context['source_index_domain'] == ASSEMBLY.ORACLE.INDEX_DOMAIN,
            'unexpected_rail_asset_or_source_domain')
    objects = terminal['objects']
    roster = {row['name']: row['evaluated'] for row in objects}
    offsets = [0]
    for row in objects:
        offsets.append(offsets[-1] + len(row['evaluated']['triangles']))
    require(len(roster) == len(objects) == 21 and offsets[-1] == 184
            and sum(len(row['vertices_world_m']) for row in roster.values()) == 148
            and offsets == terminal['source_face_offsets']
            and [row['visible_get'] for row in objects] == terminal['display_object_mask'],
            'rail_evaluated_mesh_order_or_display_changed')
    regions = {}
    for name, box in BOXES.items():
        source = roster[name]
        lo, hi = [tuple(Fraction(str(value)) for value in corner) for corner in box]
        vertices = [tuple(map(Fraction, row)) for row in source['vertices_world_m']]
        selected = [i for i, face in enumerate(source['triangles']) if all(
            all(a <= x <= b for a, x, b in zip(lo, vertices[v], hi, strict=True)) for v in face)]
        result = region_truth(source, roster[REFERENCES[name]], box, name)
        require(selected == result['triangle_ids'] == ROWS[name] and result['vertex_count'] == COUNTS[name]
                and Fraction(*result['distance_squared_exact']) == SQUARED[name],
                'rail_closed_box_source_order_or_lower_bound_changed/' + name)
        result[THRESHOLD_KEY] = result.pop('at_least_0_35_m')
        regions[name] = result
    require(regions['M19'][THRESHOLD_KEY] is True and regions['M21'][THRESHOLD_KEY] is False
            and SQUARED['M21'] < SQUARED['M19'], 'rail_threshold_or_order_changed')
    return {'source': context, 'meshes': [{key: row[key] for key in ('name', 'object_id', 'instance_id', 'visible_get')}
                                         for row in objects], 'source_face_offsets': offsets,
            'regions': regions, 'nearer': 'M21'}


def historical_truth():
    source, asset, replay = (pin(path) for path in (SOURCE_ROOT / 'TERMINAL_SOURCE.json',
          SOURCE_ROOT / 'native/input.blend', CAPTURE_ROOT / 'native/WIRE/002/RESPONSE.bin'))
    require((source['sha256'], asset['sha256'], replay['sha256']) == (TERMINAL_SHA, ASSET, CAPTURE_SHA),
            'fixed_rail_source_asset_or_native_replay_wire_changed')
    terminal = load(Path(source['path']))
    truth = scene_truth(terminal)
    for row in truth['regions'].values():
        ASSEMBLY.numeric_pair(row['distance_m'], row['direction_world'], row['source_point_world_m'],
                              row['reference_point_world_m'], row)
    return terminal, {**truth, 'source': source, 'asset': asset, 'replay_source_wire': replay,
                      'asset_sha256': ASSET, 'passed': True, 'threshold_m': float(THRESHOLD),
                      'coordinate_frame': 'world', 'unit': 'm', 'actual_Blender_starts': 0, 'actual_models': 0,
                      'source_pins': [source, asset, replay, *[pin(path) for path in (Path(__file__), BASE_PATH, CLOSE_PATH)]]}


checked_scene = replace(ASSEMBLY.checked_scene, scene_truth=scene_truth)
closed_source = replace(ASSEMBLY.ORACLE.verify_closed_source, verify_terminal=checked_scene, ASSET=ASSET)


def verify_runtime_close(slot, terminal, result):
    try:
        path = slot / 'RUNTIME_CLOSE.json'
        receipt = load(path)
        if slot.parent == OFFLINE_SLOTS.resolve():
            offline = load(slot / 'OFFLINE_FIXTURE.json')
            require(offline['offline_fixture'] is True and offline['actual_Blender_starts'] == 0 and offline['passed'] is True,
                    'offline_closure_receipt_unmarked')
            history = slot / 'historical_capture'
            historical_pair = {history / name: CAPTURE_ROOT / name
                               for name in ('RUNTIME_CLOSE.json', 'NATIVE_RUNTIME_PROOF.json')}
            files = {'runtime': path, 'owner': slot / 'owner/BRIDGE_RESULT.json',
                     'thin': slot / 'client_wire/CLOSE.json', 'historical_close': history / 'RUNTIME_CLOSE.json',
                     'historical_native': history / 'NATIVE_RUNTIME_PROOF.json'}
            pins = offline['source_pins']
            paths = {Path(row['path']): row for row in pins}
            require(len(paths) == len(pins) and all(paths[name] == pin(name) == offline['closure'][key]
                    for key, name in files.items())
                    and all(row == pin(row['path']) for row in pins),
                    'offline_close_sources_not_current_replay_receipts')
            require(all((pin(local)['sha256'], pin(local)['bytes']) == (pin(original)['sha256'], pin(original)['bytes'])
                        for local, original in historical_pair.items()), 'historical_capture_close_bytes_changed')
            inherited = ready_closure(load(history / 'RUNTIME_CLOSE.json'), 'P', load(history / 'NATIVE_RUNTIME_PROOF.json'))
            require(inherited['pid'] == terminal['source']['pid'] and result['closure_verification']['passed'] is True,
                    'historical_capture_close_pid_changed')
            thin, owner = load(files['thin']), load(files['owner'])
            require(not receipt['errors'] and 'Blender_close' not in receipt and
                    all(thin[k] is True for k in ('confirmed', 'reader_stopped', 'process_handle_closed'))
                    and thin['exit_code'] == 0 and thin.get('forced_kill', False) is False and not thin['errors']
                    and not owner['protocol_errors'] and not owner['transport_errors'], 'offline_owner_or_thin_close_failed')
            if slot.name == 'P1':
                close = receipt['public_MCP_close']
                held = load(slot / 'mcp/HELD_CLOSE.json')
                require(paths[slot / 'mcp/HELD_CLOSE.json'] == pin(slot / 'mcp/HELD_CLOSE.json')
                        and close == held and held['confirmed'] is True and held['exit_code'] == 0
                        and held['production_eof_and_exit_verified'] is True, 'offline_production_MCP_close_failed')
        else:
            require('offline_fixture' not in receipt and not (slot / 'OFFLINE_FIXTURE.json').exists(),
                    'offline_closure_substituted_for_live')
            observed = ready_closure(receipt, slot.name[0], load(slot / 'NATIVE_RUNTIME_PROOF.json'))
            require(observed == result['closure_verification'] and observed['pid'] == terminal['source']['pid']
                    and observed['deadline_ns'] == result['owned_deadline_ns'], 'actual_close_not_bound_to_slot')
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError('rail_runtime_close_evidence_mismatch/' + str(error)) from error


def verify_closed_source(slot, historical, expected):
    geometry, terminal, device = closed_source(slot, historical, expected)
    verify_runtime_close(slot, terminal, load(slot / 'SLOT_RESULT.json'))
    return geometry, terminal, device


frame_source_binding = replace(ASSEMBLY.frame_source_binding, REFERENCES=REFERENCES, load=BASE.load_producer)
qualify_frames = replace(ASSEMBLY.qualify_frames, BOXES=BOXES, frame_source_binding=frame_source_binding)
verify_product_measurements = replace(ASSEMBLY.verify_product_measurements, REFERENCES=REFERENCES)
exposure_verifier = replace(ASSEMBLY.exposure_verifier, BOXES=BOXES, requested_region=ASSEMBLY.requested_region)


def check_claim(item, row, answer, geometry, frames, claims):
    name, _, criterion = item.partition('.')
    quote = row['quote']
    require(isinstance(quote, str) and quote.strip() and quote in answer, 'claim_quote_absent_from_actual_final')
    truth = geometry['regions'][name]
    if criterion == 'threshold':
        require(row[THRESHOLD_KEY] is truth[THRESHOLD_KEY], 'incorrect_threshold_classification')
    elif criterion == 'distance':
        value, allowance = ASSEMBLY.OPPOSITE.distance_in_metres(row)
        literal = re.escape(row['distance_literal'])
        require(re.search(r'(?<![\d.])' + literal + r'(?![\d.])', quote)
                and abs(value - truth['distance_m']) <= min(allowance, .000500001)
                and (value >= float(THRESHOLD)) is truth[THRESHOLD_KEY],
                'distance_rounding_incorrect_or_does_not_resolve_threshold')
    elif criterion == 'nearest_pair':
        a, b = row['selected_point_world_m'], row['reference_point_world_m']
        require({*a, *b} <= BASE.OLD.literal_numbers(quote), 'nearest_point_coordinates_absent_from_original_claim')
        ASSEMBLY.numeric_pair(truth['distance_m'], truth['direction_world'], a, b, truth)
    else:
        raise ValueError('unexpected_rail_claim_criterion')
    return None


domain = SimpleNamespace(BOXES=BOXES, PRODUCT_SOURCES=PRODUCT_SOURCES, REQUIRED=REQUIRED,
    historical_truth=historical_truth, verify_closed_source=verify_closed_source, qualify_frames=qualify_frames,
    verify_product_measurements=verify_product_measurements, check_claim=check_claim,
    score_slot=replace(ASSEMBLY.score_slot, score_exposure=exposure_verifier()))
_admitted_score = replace(BASE.score_slot, DOMAINS={**BASE.DOMAINS, 'rail': domain})


def score_slot(slot, claims, *, offline_fixture=False):
    slot = Path(slot).resolve(strict=True)
    root = OFFLINE_SLOTS if offline_fixture else RUN / 'slots'
    require(slot.parent == root.resolve() and slot.name in PRODUCT_SOURCES, 'wrong_rail_live_or_offline_slot_root')
    score = _admitted_score('rail', slot, claims)
    return {**score, 'score_source': 'offline_replay_fixture' if offline_fixture else 'closed_live_Pro_slot'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', type=Path)
    mode.add_argument('--slot', type=Path)
    parser.add_argument('--claims', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--offline-fixture', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    require(args.preflight is not None or args.output is not None, 'score_output_required')
    output = (args.preflight or args.output).resolve()
    require(output.is_relative_to(RUN.resolve()) and output != RUN.resolve(), 'score_output_outside_new_evidence_root')
    if args.preflight:
        require(not args.offline_fixture and args.claims is None and args.output is None, 'truth_preflight_options_invalid')
        write(output, historical_truth()[1])
        return 0
    require(args.claims is not None, 'literal_claims_required')
    try:
        verdict = score_slot(args.slot, args.claims, offline_fixture=args.offline_fixture)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError) as error:
        verdict = {'asset': 'rail', 'slot': args.slot.name, 'quality_complete': False, 'passed_items': 0,
                   'total_items': len(REQUIRED), 'error': str(error), 'adoption': None,
                   'score_source': 'offline_replay_fixture' if args.offline_fixture else 'closed_live_Pro_slot'}
    write(output, verdict)
    print({key: verdict[key] for key in ('asset', 'slot', 'quality_complete', 'passed_items', 'total_items', 'error')
           if key in verdict}, flush=True)
    return 0 if verdict['quality_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
