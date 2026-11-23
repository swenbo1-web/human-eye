"""Run the formal source-region scorer against targeted offline mutations."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m4_rail_source_region_product_native_001')
PREFLIGHT = RUN / 'preflight'
CONTROL_ROOT = PREFLIGHT / 'controls'
QUALIFIED = CONTROL_ROOT / 'qualified'
SCORE_SLOTS = PREFLIGHT / 'score_replay/slots'
SCORE = HERE / 'score.py'
CASES = (
    'wrong-direction',
    'wrong-image',
    'wrong-pixel',
    'wrong-range',
    'cross-slot-same-png',
    'wrong-sha',
    'missing-claim',
    'wrong-close',
)
ARMS = {'wrong-direction': 'N1', 'wrong-image': 'N1'}
CLAIM_EXPECTATIONS = {
    'wrong-direction': ('M19.direction', 'world_direction_reversed_or_invalid'),
    'wrong-image': ('M19.image', 'final_path_not_one_verified_current_original_PNG'),
    'wrong-pixel': ('M19.pixel', 'claimed_pixel_not_its_reported_current_source_triangle'),
}
FRAME_EXPECTATIONS = {
    'wrong-range': 'product_image_capture_or_upper_region_binding_changed',
    'cross-slot-same-png': 'artifact_not_original_same_slot/',
    'wrong-sha': 'artifact_not_original_same_slot/',
}
SLOT_ERRORS = {
    'missing-claim': 'missing_required_claim_items/M19.scope',
    'wrong-close': 'rail_runtime_close_evidence_mismatch/offline_production_MCP_close_failed',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def encoded(document):
    return (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf8')


def digest(payload):
    return {'bytes': len(payload), 'sha256': sha256(payload).hexdigest()}


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), **digest(path.read_bytes())}


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def match_frame(device, region, claims):
    original = pin(claims[region + '.image']['local_image_path'])
    path = Path(original['path'])
    frame, = [row for row in device['frames'] if Path(row['PNG']).resolve(strict=True) == path]
    require(original['sha256'] == frame['PNG_sha256'] and original['bytes'] == frame['PNG_bytes'],
            'offline_control_original_PNG_pin_changed')
    return frame, original


def expectation(case, frame_ref=None):
    if case in CLAIM_EXPECTATIONS:
        criterion, reason = CLAIM_EXPECTATIONS[case]
        return {'criterion': criterion, 'reason': reason}
    if case in SLOT_ERRORS:
        return {'error': SLOT_ERRORS[case]}
    return {'criterion': 'M19.image', 'frame_ref': frame_ref, 'frame_reason': FRAME_EXPECTATIONS[case]}


def prepare(case, slot, source_claims, folder):
    table = json.loads(source_claims.read_bytes())
    claims = table['claims']
    overlays, provenance = {}, {}
    frame_ref = None

    if case == 'wrong-direction':
        key = 'M19.direction'
        direction = claims[key]['world_unit_direction']
        require(direction[0] == 0 and direction[1] > 0 and direction[2] < 0,
                'offline_direction_fixture_not_the_original_slanted_direction')
        claims[key]['world_unit_direction'] = [-value for value in direction]
    elif case == 'wrong-image':
        key = 'M19.image'
        original = pin(claims[key]['local_image_path'])
        other = pin(claims['M21.image']['local_image_path'])
        require(original['path'] != other['path'] and all(Path(row['path']).is_relative_to(slot)
                for row in (original, other)), 'offline_control_images_must_be_distinct_and_same_slot')
        claims[key] = claims['M21.image']
        provenance.update(original_png=original, other_region_png=other)
    elif case == 'wrong-pixel':
        key = 'M19.pixel'
        row, col = claims[key]['pixel_rc']
        require(row != col, 'offline_pixel_fixture_must_be_non_diagonal')
        claims[key]['pixel_rc'] = [col, row]
    elif case == 'missing-claim':
        key = 'M19.scope'
        del claims[key]
    elif case == 'wrong-close':
        close_path = (slot / 'RUNTIME_CLOSE.json').resolve(strict=True)
        close = json.loads(close_path.read_bytes())
        require(close['public_MCP_close']['production_eof_and_exit_verified'] is True,
                'offline_control_original_MCP_close_not_clean')
        close['public_MCP_close']['production_eof_and_exit_verified'] = False
        overlays[close_path] = encoded(close)
    else:
        device_path = (slot / 'DEVICE_EVIDENCE.json').resolve(strict=True)
        device = json.loads(device_path.read_bytes())
        frame, original = match_frame(device, 'M19', claims)
        frame_ref = frame['ref']
        provenance['original_png'] = original
        if case == 'wrong-range':
            producer_path = Path(frame['full_result']['path']).resolve(strict=True)
            producer_pin = pin(producer_path)
            require(producer_pin['sha256'] == frame['full_result']['sha256'],
                    'offline_control_original_producer_pin_changed')
            producer = json.loads(producer_path.read_bytes())
            old_rows = producer['region_ref']['source_triangle_indices']
            require(old_rows == [0, 3, 8, 9, 10, 11] and len(producer['frames']) == 1
                    and producer['frames'][0]['image_ref'] == frame['ref'],
                    'offline_control_producer_not_the_M19_selected_frame')
            # Keep the object, capture, image, and legal row cardinality; only
            # the source region now covers a different subset of that object.
            new_rows = [1, *old_rows[1:]]
            producer['region_ref']['source_triangle_indices'] = new_rows
            payload = encoded(producer)
            frame['full_result'].update(digest(payload))
            overlays[producer_path] = payload
            provenance.update(original_producer=producer_pin, original_rows=old_rows, replaced_rows=new_rows)
        elif case == 'cross-slot-same-png':
            alias = folder / 'foreign.png'
            raw = Path(original['path']).read_bytes()
            write_new(alias, raw)
            foreign = pin(alias)
            require(not Path(foreign['path']).is_relative_to(slot) and foreign['sha256'] == original['sha256'],
                    'offline_foreign_png_must_be_byte_identical_and_outside_slot')
            provenance['foreign_png'] = foreign
            frame['PNG'] = foreign['path']
        else:
            require(case == 'wrong-sha', 'unknown_control')
            _, other = match_frame(device, 'M21', claims)
            require(other['sha256'] != original['sha256'], 'offline_wrong_digest_not_distinct')
            provenance['other_region_png'] = other
            frame['PNG_sha256'] = other['sha256']
        overlays[device_path] = encoded(device)

    if overlays:
        # Rebind changed pins in the offline envelope so controls reach the
        # semantic check. Production receipts and original bytes stay fixed.
        fixture_path = (slot / 'OFFLINE_FIXTURE.json').resolve(strict=True)
        fixture = json.loads(fixture_path.read_bytes())
        rebound = []
        for original in (*fixture['source_pins'], *fixture['closure'].values()):
            original_path = Path(original['path'])
            if original_path in overlays:
                require(original == pin(original_path), 'offline_control_original_fixture_pin_changed')
                original.update(digest(overlays[original_path]))
                rebound.append(original_path)
        if case == 'wrong-close':
            require(rebound.count(close_path) == 2, 'offline_control_close_not_bound_in_both_original_tables')
        if rebound:
            overlays[fixture_path] = encoded(fixture)

    return encoded(table), overlays, provenance, expectation(case, frame_ref)


def expected_rejection(verdict, expected):
    if verdict.get('quality_complete') is not False:
        return False
    if 'error' in expected:
        return verdict.get('error') == expected['error']
    row = verdict.get('criteria', {}).get(expected['criterion'], {})
    if row.get('status') != 'failure':
        return False
    if 'frame_reason' in expected:
        return any(
            frame.get('ref') == expected['frame_ref'] and frame.get('region') == 'M19'
            and str(frame.get('reason', '')).startswith(expected['frame_reason'])
            for frame in verdict.get('unusable_frames', ())
        )
    return row.get('reason') == expected['reason']


def dispatch(case, output):
    arm = ARMS.get(case, 'P1')
    slot = (SCORE_SLOTS / arm).resolve(strict=True)
    source_claims = (PREFLIGHT / (arm + '_CLAIMS.json')).resolve(strict=True)
    output = output.resolve()
    require(output.is_relative_to(CONTROL_ROOT.resolve()) and not output.exists(),
            'control_output_must_be_new_and_within_preflight_controls')
    if case == 'cross-slot-same-png':
        require(not (output.parent / 'foreign.png').exists(), 'control_foreign_png_already_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    claims_path = output.with_suffix('.claims.json')
    verdict_path = output.with_suffix('.candidate.json')
    require(not claims_path.exists() and not verdict_path.exists(), 'control_outputs_are_single_use')
    raw_claims, overlays, provenance, expected = prepare(case, slot, source_claims, output.parent)
    originals = [pin(path) for path in (source_claims, *overlays)]
    write_new(claims_path, raw_claims)
    argv = sys.argv
    read_bytes = Path.read_bytes
    reads = Counter()

    def read_with_overlay(path):
        if path in overlays:
            reads[str(path)] += 1
            return overlays[path]
        return read_bytes(path)

    wall_start = time.perf_counter_ns()
    try:
        sys.argv = [str(SCORE), '--offline-fixture', '--slot', str(slot),
                    '--claims', str(claims_path), '--output', str(verdict_path)]
        actual_argv = sys.argv[:]
        with patch.object(Path, 'read_bytes', read_with_overlay):
            try:
                run_path(str(SCORE), run_name='__main__')
                code = 0
            except SystemExit as exit_status:
                code = exit_status.code
    finally:
        sys.argv = argv

    wall_end = time.perf_counter_ns()
    require(all(pin(item['path']) == item for item in originals), 'offline_control_originals_changed')
    verdict = json.loads(verdict_path.read_bytes()) if verdict_path.is_file() else {}
    passed = (type(code) is int and code != 0 and expected_rejection(verdict, expected)
              and all(reads[str(path)] > 0 for path in overlays))
    receipt = {
        'passed': passed,
        'offline_synthetic_control': True,
        'name': case,
        'arm': arm,
        'pid': os.getpid(),
        'score_argv': actual_argv,
        'candidate_exit_code': code,
        'candidate_entry': pin(SCORE),
        'candidate_receipt': pin(verdict_path) if verdict else None,
        'claim_fixture': pin(claims_path),
        'original_inputs': originals,
        'provenance': provenance,
        'expectation': expected,
        'overlay_reads': dict(reads),
        'virtual_inputs': {str(path): digest(data) for path, data in overlays.items()},
        'started_ns': wall_start,
        'closed_ns': wall_end,
        'elapsed_ns': wall_end - wall_start,
    }
    write_new(output, encoded(receipt))
    return 0 if passed else 1


def summarize(output):
    output = output.resolve()
    require(output == CONTROL_ROOT.resolve() / 'SUMMARY.json' and not output.exists(),
            'summary_requires_new_fixed_path')
    result = {}
    source_pins = {}
    for case in CASES:
        path = QUALIFIED / case / 'RESULT.json'
        trace_path = path.with_name('TRACE.json')
        report = json.loads(path.read_bytes())
        trace = json.loads(trace_path.read_bytes())
        arm = ARMS.get(case, 'P1')
        slot = (SCORE_SLOTS / arm).resolve(strict=True)
        frame_ref = None
        if case in FRAME_EXPECTATIONS:
            claims = json.loads((PREFLIGHT / (arm + '_CLAIMS.json')).read_bytes())['claims']
            frame, _ = match_frame(json.loads((slot / 'DEVICE_EVIDENCE.json').read_bytes()), 'M19', claims)
            frame_ref = frame['ref']
        expected = expectation(case, frame_ref)
        require(report['name'] == case and report['offline_synthetic_control'] is True
                and report['arm'] == arm and report['expectation'] == expected
                and type(report['candidate_exit_code']) is int and report['candidate_exit_code'] != 0
                and report['candidate_entry'] == pin(SCORE), 'control_receipt_not_current/' + case)
        require(trace['entry'] == str(Path(__file__).resolve()) and trace['pid'] == report['pid']
                and trace['entry_return_code'] == 0 and trace['entry_exception'] is None
                and trace['new_Blender'] == trace['new_models'] == trace['new_rasters'] == 0
                and any(row == report['candidate_entry'] for row in trace['source_pins']),
                'control_missing_cold_actual_cli_trace/' + case)
        verdict = json.loads(Path(report['candidate_receipt']['path']).read_bytes())
        require(report['passed'] is True and expected_rejection(verdict, expected)
                and set(report['overlay_reads']) == set(report['virtual_inputs'])
                and all(n > 0 for n in report['overlay_reads'].values()),
                'required_control_rejection_missing/' + case)
        inputs = [pin(path), pin(trace_path), report['candidate_entry'], report['candidate_receipt'],
                  report['claim_fixture'], *report['original_inputs'], *trace['source_pins']]
        inputs.extend(item for item in report['provenance'].values()
                      if isinstance(item, dict) and 'path' in item)
        for item in inputs:
            require(pin(item['path']) == item, 'control_bound_file_changed/' + item['path'])
            source_pins[item['path']] = item
        result[case] = {
            'arm': report['arm'],
            'candidate_exit_code': report['candidate_exit_code'],
            'exact_rejection': expected,
            'receipt': pin(path),
            'trace': pin(trace_path),
            'candidate_receipt': report['candidate_receipt'],
        }
    write_new(output, encoded({
        'passed': True,
        'case_count': len(CASES),
        'cases': result,
        'source_pins': list(source_pins.values()),
        'new_Blender': 0,
        'new_models': 0,
    }))
    return 0


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--case', choices=CASES)
    mode.add_argument('--summarize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(summarize(args.output) if args.summarize else dispatch(args.case, args.output))
