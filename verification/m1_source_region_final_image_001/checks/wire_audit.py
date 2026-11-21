"""Bind the explicitly selected P2 original PNG through its archived live wire."""

import argparse
import base64
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
P2 = V / 'perf050_source_region_active_view_p2'
PILOT = V / 'perf050_readonly_product_pilot_001'
P2_RUN = Path('D:/he_perf050_source_region_active_view_p2')
PILOT_RUN = Path('D:/he_perf050_readonly_product_pilot_001')
LOCAL_SHA = 'a0b1aa30a722c519252224c8645084c92b08a514762e07e61e24f1b8e8225dbe'
GLOBAL_SHA = '6087f235e7bc1d21cee40cece7405e0445af76e401403f0c53a190e155979367'
P2_ARCHIVE_SHA = 'befd9d28399e6a2a06b89626d221684433050fda01422d1552a7b05eafde4aa5'
PILOT_ARCHIVE_SHA = 'd138efe19891843244f1049e0fab61ea5b6f2d4b923742d632516743ff1a7e71'
N1_SHA = 'fe10dba31a2f76b4a5513e36403f4734fc8f474b3d9256a3990293edbbd13824'
SOURCE = '2ad989728b7229934d164cf4c763eeb89b28e86d6fbfe7b90bace82055b2683c'
PRODUCT = '30c9cfc121bbdee72b61afda59cbcf23e9080b67'
WHEEL = '706cab599faafe0ec31a1625cbc8035530342824dbfd34afe3835e0d4ebcf100'


previous = run_path(str(P2 / 'checks/review.py'))
Originals = previous['Originals']
read, pin, digest, require = (previous[key] for key in ('read', 'pin', 'digest', 'require'))


def records(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def same_slot_member(original, stem, path):
    path = Path(path).resolve()
    require(path.is_relative_to(original.root / stem), 'path_must_bind_own_closed_slot')
    return original.member(path.relative_to(original.root).as_posix())


def image_blocks(content):
    return {index: base64.b64decode(row['data'], validate=True)
            for index, row in enumerate(content) if row['type'] == 'image' and row['mimeType'] == 'image/png'}


def close_state(original, stem, label):
    result_path = stem + '/SLOT_RESULT.json'
    result_bytes = original.member(result_path)
    result = json.loads(result_bytes)
    publication = original.json(stem + '/SLOT_PUBLICATION.json')
    owner = original.json(stem + '/owner/CLOSE.json')
    close = original.json(stem + '/RUNTIME_CLOSE.json')
    consumer = original.json(stem + '/consumer/CONSUMER.json')
    require(result['label'] == publication['label'] == label and result['status'] == publication['status'] == 'completed'
            and publication['result_sha256'] == digest(result_bytes) and publication['owned_budget_passed'] is True
            and result['closure_verification']['passed'] is True and result['independent_before_after']['passed'] is True
            and owner['confirmed'] is True and not owner['errors'] and not owner['transport_errors']
            and close['Blender_exit']['exited'] is True and close['Blender_exit']['exit_code'] == 0
            and (label != 'P2' or close['public_MCP_exit']['exited'] is True and close['public_MCP_exit']['exit_code'] == 0)
            and consumer['valid_completion'] is True and consumer['exit_code'] == 0
            and consumer['runtime_exit']['confirmed'] is True and consumer['runtime_exit']['exited'] is True
            and consumer['runtime_exit']['handle_closed'] is True and consumer['process_reaped'] is True
            and owner['closed_ns'] <= close['closed_ns'] <= publication['published_ns'],
            'original_owner_consumer_and_runtime_close_required')
    return result, publication, consumer


def verified_wire(original, stem, attempt, *, business, public, stdout, events):
    contract, = (row for row in business['result_contracts'] if row['attempt'] == attempt)
    tool = stem + f'/owner/tool_{attempt:02d}'
    packet = stem + f'/owner/rpc_{attempt + 2:03d}'
    owner_tx, owner_rx = (original.json(tool + f'/{name}.json') for name in ('REQUEST', 'RESPONSE'))
    actual_tx, actual_rx = (original.json(packet + f'/TCP_{name}.bin') for name in ('TX', 'RX'))
    require(actual_tx['args']['message'] == owner_tx and actual_tx['args']['attempt'] == attempt
            and actual_rx['result'] == owner_rx and actual_rx['request_id'] == actual_tx['request_id']
            and actual_rx['ok'] is True, 'original_forwarding_attempt_or_wire_changed')

    attachment, = (key.removesuffix('/RX.bin') for key, row in original.files.items()
                   if key.startswith(stem + '/consumer/attachments/') and key.endswith('/RX.bin')
                   and row['sha256'] == contract['RX_sha256'])
    cli_tx, cli_rx = (original.member(attachment + f'/{name}.bin') for name in ('TX', 'RX'))
    receipt = original.json(attachment + '/RECEIPT.json')
    caller = contract['caller_identity']
    cli_event, = (row for row in events if row['event']['type'] == 'item.completed'
                  and row['event']['item'].get('id') == caller['CLI_event_item_id'])
    cli_item = cli_event['event']['item']
    require(contract['matched'] is True and contract['reason'] == 'content_and_envelope_match'
            and contract['receipt'] == receipt and receipt['attempt'] == attempt
            and receipt['sequence'] == attempt + 3 and receipt['RPC_id'] == owner_tx['id'] == owner_rx['id']
            and json.loads(cli_tx) == owner_tx and json.loads(cli_rx) == owner_rx
            and digest(cli_tx) == contract['TX_sha256'] and digest(cli_rx) == contract['RX_sha256']
            and cli_event['event'] in stdout and cli_event['perf_ns'] == contract['CLI_received_ns']
            and cli_item['tool'] == contract['tool'] == owner_tx['params']['name']
            and cli_item['arguments'] == owner_tx['params']['arguments']
            and cli_item['result']['content'] == owner_rx['result']['content']
            and cli_item['status'] == 'completed' and cli_item['error'] is None
            and len(image_blocks(cli_item['result']['content'])) == contract['CLI_images'],
            'original_consumer_transport_or_public_event_changed')

    producer_tx, producer_rx = (original.json(tool + f'/PRODUCT_{name}.json') for name in ('REQUEST', 'RESPONSE'))
    session, = (row for row in public if row['index'] == attempt)
    product_receipt = session['receipt']
    rpc = stem + f"/mcp/rpc_{product_receipt['index']:02d}"
    stdio_tx, stdio_rx = (original.member(rpc + f'/{name}.bin') for name in ('TX', 'RX'))
    archive = session['producer_archive']
    producer_bytes = same_slot_member(original, stem, archive['path'])
    same_slot_member(original, stem, archive['read_context'])
    require(producer_tx == session['request'] == json.loads(stdio_tx)
            and producer_rx == session['response'] == json.loads(stdio_rx)
            and producer_tx['params']['name'] == 'human_eye_scene_observe'
            and producer_tx['params']['arguments'] == owner_tx['params']['arguments']
            and producer_rx['result'] == owner_rx['result']
            and product_receipt['error'] is None and product_receipt['RX_sha256'] == digest(stdio_rx)
            and original.json(tool + '/PRODUCT_RECEIPT.json')['producer_archive'] == archive
            and digest(producer_bytes) == archive['sha256'] and archive['new_observations_for_archive'] == 0,
            'live_product_to_public_wire_changed')
    content = owner_rx['result']['content']
    return (json.loads(producer_bytes), json.loads(content[0]['text']), image_blocks(content),
            {'attempt': attempt, 'owner_attempt': actual_tx['args']['attempt'], 'CLI_event_item': cli_item['id'],
             'CLI_event_received_ns': cli_event['perf_ns'], 'public_rpc_index': product_receipt['index'],
             'public_stdio_TX_sha256': digest(stdio_tx), 'public_stdio_RX_sha256': digest(stdio_rx),
             'CLI_stdio_TX_sha256': digest(cli_tx), 'CLI_stdio_RX_sha256': digest(cli_rx),
             'producer_source': archive['path'], 'producer_source_sha256': archive['sha256'],
             'public_text_bytes': len(content[0]['text'].encode('utf-8')), 'image_blocks': contract['CLI_images']})


def complete_local(original, stem, producer, body, images, wire):
    selected, = producer['frames']
    witness = producer['facts']['visibility']['complete_witness']
    region, binding = producer['region_ref'], producer['binding']
    body_witness = body.get('visibility', body.get('facts', {}).get('visibility', {}))['complete_witness']
    require(region == body['region_ref'] and region['source_triangle_indices'] == [20, 21]
            and producer['facts']['region']['object_name'] == 'N15'
            and producer['result_kind'] == 'source_region' and producer['status'] == 'complete'
            and producer['observation_status'] == 'locally_observed' and producer['read_only'] is True
            and binding['runtime_source_sha256'] == SOURCE and region['document_epoch'] == binding['document_epoch']
            and region['ordered_geometry_sha256'] == binding['ordered_geometry_sha256']
            and all(binding['capture_state'][key] == value for key, value in region['capture_generation'].items())
            and witness == body_witness and witness['geometry_status'] == 'complete'
            and (witness['selected_surface_pixels'], witness['contrasting_boundary_pixels']) == (86955, 1300)
            and all(witness[key] == selected[key] for key in ('frame_identity', 'image_ref', 'view_name'))
            and selected['view_name'] == 'RIGHT' and selected['host_binding_sha256'] == binding['binding_sha256']
            and selected['display_identity'] == binding['display_identity'] == binding['image_scope']['identity']
            and selected['image_scope'] == binding['image_scope'],
            'source_region_witness_or_binding_changed')
    image_identity = json.dumps((region['region_id'], selected['frame_identity'], selected['image_sha256']),
                                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    require(witness['image_ref'] == 'source-region-image:' + digest(image_identity),
            'region_frame_PNG_ref_fingerprint_changed')
    require(list(images) == [1], 'selected_original_must_be_sole_actual_image_block')
    if wire['attempt'] == 6:
        brief_image, = body['images']
        require(body['schema'] == 'source-region-brief-v3' and brief_image['image_block_index'] == 1
                and all(brief_image[key] == selected[key] for key in ('image_ref', 'frame_identity', 'image_sha256',
                                                                    'host_binding_sha256'))
                and 'image_path' not in brief_image and 'local_file' not in brief_image,
                'original_hot_brief_has_unexpected_delivery_fields')
        require(previous['display_rows'](body) == binding['image_scope'], 'display_directory_lossless_proof_failed')
    else:
        full_frame, = body['frames']
        require(all(full_frame[key] == selected[key] for key in ('image_ref', 'frame_identity', 'image_sha256', 'image_path')),
                'full_original_path_or_identity_changed')
    started = perf_counter_ns()
    png = same_slot_member(original, stem, selected['image_path'])
    elapsed = perf_counter_ns() - started
    npz = same_slot_member(original, stem, selected['arrays_path'])
    require(png == images[1] and len(png) == selected['PNG_bytes'] == 2870
            and digest(png) == selected['image_sha256'] == LOCAL_SHA and digest(npz) == selected['arrays_sha256']
            and png[:8] == bytes.fromhex('89504e470d0a1a0a') and png[16:24] == bytes.fromhex('0000020000000200'),
            'selected_PNG_or_NPZ_must_be_actual_bound_payload')
    return {
        **wire, 'image_path': selected['image_path'], 'image_sha256': LOCAL_SHA, 'image_bytes': len(png),
        'NPZ_path': selected['arrays_path'], 'NPZ_sha256': selected['arrays_sha256'],
        'source_region_id': region['region_id'], 'source_triangle_indices': region['source_triangle_indices'],
        'binding_sha256': binding['binding_sha256'], 'capture_generation': region['capture_generation'],
        'witness': witness, 'raster_attempts': producer['work']['raster_attempts'],
        'frame_reuses': producer['work']['frame_reuses'], 'archival_check_including_file_read_ns': elapsed,
    }


def audit_p2(original):
    stem = 'slots/P2'
    result, publication, consumer = close_state(original, stem, 'P2')
    quality_path, frozen_path = (P2 / name for name in ('QUALITY.json', 'FROZEN.json'))
    historical = read(quality_path)
    binding_path = previous['INSTALL']
    install = read(binding_path)
    require(install['preparation_git'] == PRODUCT and install['source_sha256'] == SOURCE
            and install['wheel_sha256'] == WHEEL and len(install['source_manifest']) == 143
            and pin(frozen_path)['sha256'] == result['freeze_sha256'] == historical['freeze_sha256']
            and pin(binding_path)['sha256'] == result['product_binding_sha256']
            and result['product_source_sha256'] == SOURCE
            and historical['actual_slot']['quality_earned'] == 4 and historical['actual_slot']['quality_possible'] == 5
            and historical['actual_slot']['result_sha256'] == publication['result_sha256'],
            'old_product_or_four_point_historical_grade_changed')
    events = records(original.member(stem + '/consumer/events.jsonl'))
    stdout = records(original.member(stem + '/consumer/stdout.raw.bin'))
    public = records(original.member(stem + '/PUBLIC_REQUESTS.jsonl'))
    business = original.json(stem + '/consumer/BUSINESS_SOURCE_BINDING.json')
    observations = {i: verified_wire(original, stem, i, business=business, public=public, stdout=stdout, events=events)
                    for i in (3, 4, 6)}
    local = [complete_local(original, stem, *observations[i]) for i in (4, 6)]
    require(all(local[0][key] == local[1][key] for key in ('image_path', 'image_sha256', 'witness', 'binding_sha256',
                                                          'NPZ_sha256', 'capture_generation'))
            and (local[0]['raster_attempts'], local[1]['raster_attempts'], local[1]['frame_reuses']) == (2, 0, 1),
            'cold_and_hot_must_be_exact_same_original')
    global_producer, _, global_images, global_wire = observations[3]
    global_frame, = (row for row in global_producer['frames'] if row['scope_id'] == 'global' and row['view_name'] == 'RIGHT')
    global_png = same_slot_member(original, stem, global_frame['image_path'])
    require(global_producer['result_kind'] == 'active_observation' and digest(global_png) == GLOBAL_SHA
            and global_frame['image_sha256'] == GLOBAL_SHA and global_png in global_images.values()
            and global_frame['image_ref'] != local[0]['witness']['image_ref'],
            'same_named_global_RIGHT_must_be_different_original')
    device = original.json(stem + '/DEVICE_EVIDENCE.json')
    target_frame, = (row for row in device['frames'] if row['ref'] == local[0]['witness']['image_ref'])
    sys.path.insert(0, install['dependency_root'])
    truth_path, image_oracle_path, geometry_oracle_path = (
        PILOT / name for name in ('truth/TRUTH.json', 'quality_images.py', 'truth/oracle.py'))
    image_oracle, geometry_oracle = (run_path(str(path)) for path in (image_oracle_path, geometry_oracle_path))
    inspected = image_oracle['inspect_frame'](original.root / stem, target_frame, read(truth_path),
                                              {LOCAL_SHA: [4, 6]}, geometry_oracle)
    require(inspected['qualifies'] and inspected['all_four_corners_inside_clip']
            and (inspected['surface_pixels'], inspected['contrasting_boundary_pixels']) == (86955, 1300)
            and inspected['native_PNG'] == str(Path(local[0]['image_path']).resolve()),
            'actual_current_geometry_and_pixel_truth_disagree')
    public_final = original.member(stem + '/consumer/PUBLIC_FINAL.txt')
    final_event = [x['event']['item'] for x in events
                   if x['event']['type'] == 'item.completed' and x['event']['item']['type'] == 'agent_message'][-1]
    require(len(public_final) == 1031 and digest(public_final) == historical['actual_slot']['answer_sha256']
            and original.member(stem + '/consumer/final.txt') == public_final
            and public_final == (P2 / 'answers/P2.txt').read_bytes()
            and consumer['final'].encode('utf-8') == final_event['text'].encode('utf-8') == public_final
            and set(final_event) == {'id', 'type', 'text'}
            and not any(row['ref'].encode('utf-8') in public_final for row in device['frames']),
            'historical_plain_text_final_must_be_unchanged_without_explicit_frame_reference')
    source_pins = [pin(path) for path in (quality_path, frozen_path, binding_path, truth_path, image_oracle_path,
                                         geometry_oracle_path, P2 / 'checks/review.py', P2 / 'answers/P2.txt')]
    return {'historical_score': [4, 5], 'historical_slot_completed': True, 'historical_final_bytes': len(public_final),
            'historical_final_sha256': digest(public_final), 'historical_final_plain_text_without_frame_ref': True,
            'original_owner_consumer_and_Blender_closed': True, 'published_original_result_sha256': publication['result_sha256'],
            'consumer_CLI_Popen_exit_code': consumer['exit_code'],
            'consumer_retained_runtime_handle_exit_code': consumer['runtime_exit']['exit_code'],
            'explicit_selection': {'attempt': 6, 'image_ref': local[1]['witness']['image_ref'],
                                   'frame_identity': local[1]['witness']['frame_identity'],
                                   'original_file_path': local[1]['image_path'], 'image_sha256': LOCAL_SHA,
                                   'selection_basis': 'explicit frozen attempt, source region and bound complete witness'},
            'local_cold_hot_attempts': local,
            'different_same_named_global_RIGHT': {**global_wire, 'image_ref': global_frame['image_ref'],
                                                   'image_path': global_frame['image_path'], 'image_sha256': GLOBAL_SHA},
            'independent_pixel_geometry_check': inspected}, source_pins


def audit_n1(original):
    stem = 'slots/N1'
    result, publication, _ = close_state(original, stem, 'N1')
    final = original.member(stem + '/consumer/PUBLIC_FINAL.txt')
    asset_frame, = (row for row in original.json(stem + '/DEVICE_EVIDENCE.json')['frames']
                    if row['view_name'] == 'RIGHT' and row['ref'].encode('utf-8') in final)
    raw = same_slot_member(original, stem, asset_frame['PNG'])
    image, = original.json(stem + '/owner/tool_09/RECEIPT.json')['image_attachments']
    reply = original.json(stem + '/owner/tool_09/RESPONSE.json')
    require(asset_frame['ref'] == image['ref'] and image['PNG_sha256'] == asset_frame['PNG_sha256'] == digest(raw) == N1_SHA
            and raw in image_blocks(reply['result']['content']).values() and digest(final) == result['answer']['sha256'],
            'historical_native_alias_no_longer_resolves_to_original')
    return {'historical_alias': asset_frame['ref'], 'same_slot_verified_PNG': asset_frame['PNG'],
            'PNG_sha256': N1_SHA, 'PNG_bytes': len(raw), 'historical_final_sha256': digest(final),
            'original_result_sha256': publication['result_sha256'],
            'resolution_scope': 'sealed original registry and actual historical wire',
            'current_native_alias_host_open_tested_here': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'WIRE_AUDIT.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_isolated_interpreter')
    original = Originals(P2_RUN, P2 / 'RUNTIME_INDEX.json', P2_ARCHIVE_SHA, 338)
    comparison = Originals(PILOT_RUN, PILOT / 'RUNTIME_INDEX.json', PILOT_ARCHIVE_SHA, 555)
    try:
        p2, pins = audit_p2(original)
        n1 = audit_n1(comparison)
    finally:
        original.close()
        comparison.close()
    distinct = {row['path']: row for row in (pin(Path(__file__)), *original.pins, *comparison.pins, *pins)}
    receipt = {
        'schema': 'm1-source-region-final-image-wire-audit-v1', 'passed': True,
        'original_runtime_P2_zip_entries': 338, 'historical_N1_P1_zip_entries': 555,
        'P2': p2, 'N1': n1, 'current_app_display_attempts': 0, 'natural_model_final_attachment_attempts': 0,
        'Blender_starts': 0, 'model_calls': 0, 'new_rasters': 0, 'paid_API_calls': 0,
        'source_pins': list(distinct.values()),
    }
    with args.output.open('x', encoding='utf-8', newline=chr(10)) as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write(chr(10))
    print('Original P2 #4/#6, distinct #3 and historical N1 alias verified', pin(args.output)['sha256'])


if __name__ == '__main__':
    main()
