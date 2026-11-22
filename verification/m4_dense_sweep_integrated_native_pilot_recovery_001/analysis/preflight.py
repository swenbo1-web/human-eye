"""Replay the retained seven-item scorer and actual wire/image ledger."""

import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
ORIGINAL = V / 'm4_dense_sweep_integrated_native_pilot_001'
OLD_ROOT = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
HISTORICAL = run_path(str(ORIGINAL / 'analysis/preflight.py'))
require, read, pin = (HISTORICAL[key] for key in ('require', 'read', 'pin'))


def current_qp_scope_control():
    slot = OLD_ROOT / 'slots/QP'
    wire = slot / 'client/transport/rpc_05/RX.bin'
    producer_path = slot / 'product_full/call_001/SERVICE_RESULT.json'
    index = read(ORIGINAL / 'RAW_INDEX.json')
    archive = ORIGINAL / index['archive']['name']
    archive_pin = pin(archive)
    require(archive_pin['bytes'] == index['archive']['bytes']
            and archive_pin['sha256'] == index['archive']['sha256'],
            'original_integrated_archive_changed')
    paths = [
        wire, producer_path, slot / 'client/call_02/RECEIPT.json',
        slot / 'DEVICE_EVIDENCE.json', slot / 'RUNTIME_CLOSE.json',
        slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json',
    ]
    images = {frame['ref']: pin(Path(frame['PNG']), slot)
              for frame in read(slot / 'DEVICE_EVIDENCE.json')['frames']}
    paths.extend(Path(row['path']) for row in images.values())
    pins = [pin(ORIGINAL / 'RAW_INDEX.json'), archive_pin]
    with ZipFile(archive) as z:
        for path in paths:
            member = 'runtime/' + path.relative_to(OLD_ROOT).as_posix()
            entry = pin(path)
            require({key: value for key, value in entry.items() if key != 'path'} == index['members'][member]
                    and path.read_bytes() == z.read(member), 'archive_member_changed/' + member)
            pins.append(entry)
    receipt = read(slot / 'client/call_02/RECEIPT.json')
    require(receipt['index'] == 5 and receipt['RX_sha256'] == pin(wire)['sha256']
            and receipt['RX_bytes'] == pin(wire)['bytes'], 'held_current_wire_receipt_changed')
    result = read(slot / 'SLOT_RESULT.json')
    publication = read(slot / 'SLOT_PUBLICATION.json')
    require(result['model_consumers'] == 0 and result['closure_verification']['passed']
            and publication['result_sha256'] == pin(slot / 'SLOT_RESULT.json')['sha256'],
            'scope_control_does_not_belong_to_closed_original_slot')

    raw = wire.read_bytes()
    producer = read(producer_path)
    witness_api = HISTORICAL['F']['W']
    verify = witness_api['verify_public_witnesses']
    options = {'slot': slot, 'authoritative_paths': images, 'require_paths': True}
    positive = verify(json.loads(raw), producer, **options)
    require(len(positive['paths']) == len(positive['public_witnesses']) == 2,
            'held_raster_witnesses_or_paths_missing')
    controls_path = V / 'm1_region_task_witness_image_path_001/checks/controls.py'
    controls = run_path(str(controls_path))
    mutation, offset = controls['mutate_frame_index'](raw, positive)
    try:
        verify(json.loads(mutation), producer, **options)
    except ValueError as error:
        require(str(error) == witness_api['WITNESS_BINDING_ERROR'], 'wrong_frame_failed_unrelated_gate')
        rejected_for = str(error)
    else:
        raise ValueError('same_named_global_view_accepted_for_local_witness')
    pins.append(pin(controls_path))
    return {'bytes': len(raw), 'mutated_bytes': len(mutation), 'changed_byte_offset': offset,
            'rejected_for': rejected_for, 'accepted_original': positive}, pins


def verify():
    previous = HISTORICAL['verify']()
    qp_scope, source_pins = current_qp_scope_control()
    dependencies = (Path(__file__), *(ORIGINAL / 'analysis' / name for name in
                    ('preflight.py', 'formal.py', 'score.py', 'ledger.py', 'ANALYSIS_PREFLIGHT.json')))
    pins = {Path(row['path']).resolve(): row
            for row in (*previous['source_pins'], *source_pins, *(pin(path) for path in dependencies))}
    previous['source_pins'] = list(pins.values())
    previous['current_old_QP_equal_length_scope_control'] = qp_scope
    previous['actual_formal_entry'] = 'original analysis/ledger.py with explicit --runtime and --freeze'
    return previous


if __name__ == '__main__':
    receipt = verify()
    path = HERE / 'ANALYSIS_PREFLIGHT.json'
    with path.open('x', encoding='utf8', newline='\n') as out:
        json.dump(receipt, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({'passed': receipt['passed'], 'pins': len(receipt['source_pins'])}))
