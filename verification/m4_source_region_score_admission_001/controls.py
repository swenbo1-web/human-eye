"""Exercise the real scorer CLI against scoped mutations of archived inputs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m4_source_region_score_admission_001')
ARCHIVES = {
    'assembly': Path('D:/he_m4_assembly_cross_asset_product_native_001'),
    'yanyite': Path('D:/he_m4_yanyite_opposite_direction_product_native_001'),
}
CASE_NAMES = ('wrong-direction', 'wrong-path', 'wrong-pixel', 'cross-slot-same-png',
              'wrong-capture', 'wrong-sha', 'duplicate-claim', 'missing-claim', 'unexpected-claim')
CASES = {name: ('assembly', 'P1') for name in CASE_NAMES}
CASES.update({'wrong-path': ('yanyite', 'N1'), 'wrong-direction': ('yanyite', 'N1')})


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def pin(path):
    return {'path': str(path.resolve(strict=True)), **digest(path.read_bytes())}


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def control_input(case, archive, slot, original_claims):
    """Return modified claims, exact-path overlays, and provenance."""
    table = json.loads(original_claims.read_bytes())
    claims = table['claims']
    overlays = {}
    provenance = {}
    expectation = {}
    replacement = None
    if case == 'wrong-direction':
        key = 'negative_y.direction'
        require(claims[key]['world_unit_direction'] == [0, -1, 0], 'original_direction_changed')
        claims[key]['world_unit_direction'] = [0, 1, 0]
        expectation.update(criterion=key, reason='world_direction_reversed_or_invalid')
    elif case == 'wrong-path':
        key = 'negative_y.image'
        original = claims[key]['local_image_path']
        claims[key] = claims['positive_y.image']
        require(original != claims[key]['local_image_path'], 'two_fixture_paths_not_distinct')
        provenance['wrong_image'] = pin(Path(claims[key]['local_image_path']))
        expectation.update(criterion=key, reason='final_path_not_one_verified_current_original_PNG')
    elif case == 'wrong-pixel':
        key = 'N19.pixel'
        p = claims[key]
        require(p['pixel_rc'] == [23, 254] and p['current_object_local_triangle'] == 15, 'original_pixel_changed')
        # Both coordinates still occur verbatim in the quote. The NPZ check
        # must reject their swapped positions on the same source face.
        p['pixel_rc'] = [254, 23]
        expectation.update(criterion=key, reason='claimed_pixel_not_its_reported_current_source_triangle')
    elif case in ('cross-slot-same-png', 'wrong-capture', 'wrong-sha'):
        device_path = (slot/'DEVICE_EVIDENCE.json').resolve(strict=True)
        device = json.loads(device_path.read_bytes())
        original_png = Path(claims['N19.image']['local_image_path']).resolve(strict=True)
        frame, = [row for row in device['frames'] if Path(row['PNG']).resolve(strict=True) == original_png]
        provenance['original_png'] = pin(original_png)
        require(provenance['original_png']['sha256'] == frame['PNG_sha256'], 'original_image_digest_changed')
        expectation.update(criterion='N19.image', frame_ref=frame['ref'])
        if case == 'cross-slot-same-png':
            # Use the actual prior preflight's independently produced PNG,
            # which is byte-identical yet outside this formal slot.
            index_path = archive/'sealed/RAW_INDEX.json'
            index = json.loads(index_path.read_bytes())['members']
            aliases = [archive/path for path,row in index.items()
                       if path.startswith('preflight/product/') and row['sha256'] == frame['PNG_sha256']]
            alias, = aliases
            require(not alias.resolve(strict=True).is_relative_to(slot)
                    and alias.read_bytes() == original_png.read_bytes(), 'cross_slot_fixture_not_identical_bytes')
            provenance['foreign_png'] = pin(alias)
            frame['PNG'] = str(alias.resolve(strict=True))
            expectation['frame_reason'] = 'artifact_not_original_same_slot/'
        elif case == 'wrong-capture':
            producer_path = Path(frame['full_result']['path']).resolve(strict=True)
            original_pin = pin(producer_path)
            require(original_pin['sha256'] == frame['full_result']['sha256'], 'original_producer_digest_changed')
            producer = json.loads(producer_path.read_bytes())
            foreign = archive/'preflight/product/product_full/call_001/SERVICE_RESULT.json'
            prior = json.loads(foreign.read_bytes())
            prior_revision = prior['binding']['scene_revision']
            require(prior_revision != producer['binding']['scene_revision']
                    and prior['binding']['capture_state']['instance_id'] != producer['binding']['capture_state']['instance_id']
                    and prior['frames'][0]['image_sha256'] == frame['PNG_sha256'], 'fixture_is_not_a_distinct_real_capture')
            provenance.update(original_producer=original_pin, foreign_producer=pin(foreign),
                              replaced_scene_revision=producer['binding']['scene_revision'],
                              foreign_scene_revision=prior_revision)
            # Rebind the changed JSON digest so this reaches capture binding,
            # rather than failing immediately on a stale outer checksum.
            producer['binding']['scene_revision'] = prior_revision
            overrides = encoded(producer)
            frame['full_result'].update(digest(overrides))
            overlays[producer_path] = overrides
            expectation['frame_reason'] = 'product_image_capture_or_upper_region_binding_changed'
        else:
            other, = [row for row in device['frames'] if row is not frame]
            require(other['PNG_sha256'] != frame['PNG_sha256'], 'wrong_digest_fixture_not_distinct')
            frame['PNG_sha256'] = other['PNG_sha256']
            expectation['frame_reason'] = 'artifact_not_original_same_slot/'
        overlays[device_path] = encoded(device)
    elif case == 'duplicate-claim':
        key = 'N19.counts'
        claim_json = json.dumps(claims, ensure_ascii=False, allow_nan=False)
        duplicated = '{' + json.dumps(key) + ': ' + json.dumps(claims[key], ensure_ascii=False) + ', ' + claim_json[1:]
        header = {k: v for k,v in table.items() if k != 'claims'}
        replacement = (json.dumps(header, ensure_ascii=False)[:-1] + ', "claims": ' + duplicated + '}\n').encode('utf-8')
        require(json.loads(replacement) == table, 'duplicate_fixture_changes_under_lenient_JSON_parser')
        expectation.update(shape='duplicate', criterion=key)
    elif case == 'missing-claim':
        key = 'N19.scope'
        del claims[key]
        expectation.update(shape='missing', criterion=key)
    else:
        require(case == 'unexpected-claim', 'unknown_control')
        key = 'N19.scope'
        substituted = 'N19.unregistered'
        claims[substituted] = claims.pop(key)
        expectation.update(shape='unexpected', criterion=key, substituted=substituted)
    return replacement if replacement is not None else encoded(table), overlays, provenance, expectation


def expected_rejection(verdict, expectation):
    if verdict.get('quality_complete') is not False:
        return False
    criterion = expectation['criterion']
    row = (verdict.get('criteria') or {}).get(criterion, {})
    error_message = str(verdict.get('error', ''))
    if expectation.get('shape') == 'duplicate':
        return error_message == 'duplicate_claim_JSON_key/'+criterion
    if expectation.get('shape') == 'missing':
        return error_message == 'missing_required_claim_items/'+criterion
    if expectation.get('shape') == 'unexpected':
        return error_message == 'unexpected_claim_items/'+expectation['substituted']
    if 'frame_reason' in expectation:
        return row.get('status') == 'failure' and any(
            entry.get('ref') == expectation['frame_ref'] and entry.get('region') == 'N19'
            and expectation['frame_reason'] in entry.get('reason', '') for entry in verdict.get('unusable_frames', []))
    return row.get('status') == 'failure' and row.get('reason') == expectation['reason']


def dispatch(case, output):
    asset, label = CASES[case]
    archive = ARCHIVES[asset].resolve(strict=True)
    slot = (archive/'slots'/label).resolve(strict=True)
    claims_source = archive/'score'/f'{label}_CLAIMS.json'
    output = output.resolve()
    require(RUN in output.parents and not output.exists(), 'control_requires_a_new_output_under_new_evidence_root')
    output.parent.mkdir(parents=True, exist_ok=True)
    stem = output.with_suffix('')
    claims = stem.with_name(stem.name+'.claims.json')
    candidate_output = stem.with_name(stem.name+'.candidate.json')
    candidate = HERE/'score.py'
    raw_claims, overlays, provenance, expectation = control_input(case, archive, slot, claims_source)
    input_pins = [pin(path) for path in [claims_source,*overlays]]
    write_new(claims, raw_claims)
    argv = sys.argv
    read_bytes = Path.read_bytes
    patched_reads = Counter()

    def staged_read(path):
        if path in overlays:
            patched_reads[str(path)] += 1
            return overlays[path]
        return read_bytes(path)

    started = time.perf_counter_ns()
    try:
        sys.argv = [str(candidate), '--asset', asset, '--slot', str(slot), '--claims', str(claims),
                    '--output', str(candidate_output)]
        with patch.object(Path, 'read_bytes', staged_read):
            try:
                run_path(str(candidate), run_name='__main__')
                code = 0
            except SystemExit as exited:
                code = exited.code
    finally:
        sys.argv = argv
    require(all(pin(Path(item['path'])) == item for item in input_pins), 'archived_control_inputs_changed')
    verdict = json.loads(candidate_output.read_bytes()) if candidate_output.is_file() else {}
    passed = (type(code) is int and code != 0 and expected_rejection(verdict, expectation)
              and all(patched_reads[str(path)] > 0 for path in overlays))
    receipt = {'passed': passed, 'case': case, 'asset': asset, 'slot': label, 'candidate_exit_code': code,
               'candidate_entry': pin(candidate), 'candidate_receipt': pin(candidate_output) if verdict else None,
               'claim_fixture': pin(claims), 'original_inputs': input_pins, 'provenance': provenance,
               'expectation': expectation, 'overlay_reads': dict(patched_reads),
               'virtual_inputs': {str(path): digest(data) for path,data in overlays.items()},
               'started_ns': started, 'closed_ns': time.perf_counter_ns()}
    receipt['elapsed_ns'] = receipt['closed_ns'] - receipt['started_ns']
    write_new(output, encoded(receipt))
    return 0 if passed else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASE_NAMES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(dispatch(args.case, args.output))
