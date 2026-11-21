"""Verify the actual P1 target-scoped images against the complete Blender source."""

import argparse
import base64
from hashlib import sha256
from io import BytesIO
from itertools import accumulate
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evidence import INSTALL_PATH, NS, ORACLE, V, checked, frame_geometry, library, pin, read, same_geometry
from review import P3, RUN, actual


DECODER = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
TRUTH = NS / 'truth/TRUTH.json'
FROZEN_REVIEW = HERE / 'EVIDENCE.json'
SCOPE = 'target_observation_meshes'
OBJECTS = ['M09', 'M05', 'M03']
APPENDED = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(data.encode('utf8')).hexdigest()


def verify_capture(capture, binding, terminal, install):
    meta = capture['observation_target']
    identity = capture['host_identity']
    source = terminal['source']
    by_id = {row['object_id']: row for row in terminal['objects']}
    checked(capture['capture_scope'] == identity['capture_scope'] == binding['capture_scope'] == SCOPE,
            'expected_target_observation_scope')
    checked(capture['capture_state'] == binding['capture_state'] and capture['revision'] == binding['scene_revision']
            and identity['document_epoch'] == binding['document_epoch'] == meta['full_scene_identity']['document_epoch']
            and binding['runtime_source_sha256'] == install['source_sha256'] and
            binding['source_status'] == 'loaded_generation', 'capture_generation_or_document_mismatch')
    checked(meta['source_frame'] == {name: source[name] for name in ('frame', 'subframe', 'scale_length')}
            and source['asset_sha256'] == ORACLE['ASSET_SHA']
            and capture['unit'] == binding['unit'] == 'm' and capture['coordinate_frame'] == binding['coordinate_frame']
            == 'world', 'source_frame_asset_or_units_mismatch')
    checked(meta['full_scene_identity']['capture_scope'] == 'complete_scene_meshes'
            and meta['full_scene_identity']['object_instances'] ==
                {key: row['instance_id'] for key, row in by_id.items()}, 'complete_parent_scene_identity_mismatch')
    retained = [row['object_id'] for row in capture['meshes']]
    omitted = meta['excluded_object_ids']
    directory = meta['scene_directory']
    checked(retained == meta['retained_object_ids'] and len(retained) == 3 and len(omitted) == 18
            and len(set(retained) | set(omitted)) == len(by_id) == len(directory) == 21
            and set(retained + omitted) == by_id.keys()
            and [row['object_id'] for row in directory] == list(by_id)
            and digest(directory) == meta['directory_sha256'], 'retained_excluded_partition_or_directory_mismatch')
    target = binding['observation_target']
    checked(all(meta[key] == value for key, value in target.items() if key != 'camera_plan_sha256') and
            digest(meta['camera_plan']) == target['camera_plan_sha256'] and
            meta['camera_plan'] == binding['camera_specification'],
            'observation_target_or_camera_plan_binding_mismatch')
    for obj in directory:
        current = by_id[obj['object_id']]
        checked(all(obj[key] == current[key] for key in ('name', 'instance_id', 'matrix_world'))
                and obj['vertex_count'] == len(current['evaluated']['vertices_world_m'])
                and obj['triangle_budget_upper'] == len(current['evaluated']['triangles']),
                'source_directory_differs_from_current_terminal_geometry')
    checked([by_id[key]['name'] for key in retained] == OBJECTS and meta['selector'] == {'name': 'M09'}
            and meta['target_object_index'] == 0 and retained[0] == meta['target_object_id']
            and meta['target_instance_id'] == by_id[retained[0]]['instance_id']
            and identity['object_instances'] == {key: by_id[key]['instance_id'] for key in retained},
            'retained_geometry_or_instance_identity_mismatch')
    objects = [{'object_index': i, 'host_id': key, 'object_name': by_id[key]['name'],
                'instance_id': by_id[key]['instance_id']} for i, key in enumerate(retained)]
    checked(binding['objects'] == objects, 'producer_source_roster_mismatch')
    camera_extra = {'camera_specification', 'geometry_identity', 'camera_identity', 'source_binding_sha256'}
    base = {key: value for key, value in binding.items() if key not in APPENDED | {'binding_sha256'}}
    checked(digest(base) == binding['binding_sha256'] and
            digest({key: value for key, value in base.items() if key not in camera_extra}) ==
                binding['source_binding_sha256'], 'producer_scope_digest_mismatch')
    same_geometry(capture, terminal)
    return by_id


def delivery(slot, attempt, pins):
    archive = read(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')
    contract, = [row for row in archive['result_contracts'] if row['attempt'] == attempt]
    origin, = [path for path in (slot / 'consumer/attachments').glob('bridge_*/*/RX.bin')
               if read(path.with_name('RECEIPT.json')).get('attempt') == attempt]
    owner = slot / 'owner' / f'tool_{attempt:02}'
    tx, rx = (origin.with_name(name) for name in ('TX.bin', 'RX.bin'))
    request, response = read(tx), read(rx)
    stdout = slot / 'consumer/stdout.raw.bin'
    item_id = contract['caller_identity']['CLI_event_item_id']
    item, = [row['item'] for row in P3['lines'](stdout) if row.get('type') == 'item.completed'
             and row.get('item', {}).get('id') == item_id]
    checked(contract['matched'] and contract['reason'] == 'content_and_envelope_match'
            and pin(tx)['sha256'] == contract['TX_sha256'] and pin(rx)['sha256'] == contract['RX_sha256']
            and request == read(owner / 'REQUEST.json') and response == read(owner / 'RESPONSE.json')
            and request['params']['arguments'] == item['arguments'] and request['params']['name'] == item['tool']
            and response['result']['content'] == item['result']['content'] and not response['result']['isError'],
            f'actual_attempt_{attempt}_consumer_content_unbound')
    pins.extend([tx, rx, stdout, origin.with_name('RECEIPT.json'), owner / 'REQUEST.json',
                 owner / 'RESPONSE.json', owner / 'RECEIPT.json', slot / 'consumer/BUSINESS_SOURCE_BINDING.json'])
    return owner, request, response['result'], contract


def frame_checks(frame, log, binding, subset, truth, content, image, paths, slot):
    import numpy as np

    current = subset['objects']
    counts = (len(row['evaluated']['triangles']) for row in current)
    offsets = [0, *accumulate(counts)]
    pose, = [row for row in binding['camera_specification']['views'] if row['name'] == frame['view_name']]
    checked(log['origin'] == 'product' and log['producer'] == frame
            and log['source_ref'] == 'product-binding:' + binding['binding_sha256']
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['source_revision'] == binding['scene_revision']
            and log['ref'] == image['image_ref'] == frame['image_ref']
            and log['view'] == image['view_name'] == frame['view_name']
            and log['direction_rational'] == pose['direction_rational']
            and log['pose'] == frame['pose'] == pose and log['frame_identity'] == frame['frame_identity']
            and image['patch_mapping_identity'] == frame['patch_mapping_identity']
            and log['source_face_offsets'] == offsets and offsets == [0, 2, 10, 24]
            and (frame['all_object_count'], frame['all_triangle_count']) == (3, 24)
            and log['display_object_mask'] == [row['visible_get'] for row in current] == [True] * 3,
            'frame_scoped_source_binding_mismatch')
    checked(log['PNG'] == frame['image_path'] and log['NPZ'] == frame['arrays_path'],
            'frame_original_artifact_paths_changed')
    png, raw = actual(log['PNG'], image['image_sha256'], slot)
    npz, arrays = actual(log['NPZ'], frame['arrays_sha256'], slot)
    checked(png['sha256'] == log['PNG_sha256'] == frame['image_sha256']
            and png['bytes'] == log['PNG_bytes'] == frame['PNG_bytes']
            and npz['sha256'] == log['NPZ_sha256'] and npz['bytes'] == log['NPZ_bytes']
            and content['type'] == 'image' and content['mimeType'] == 'image/png'
            and raw == base64.b64decode(content['data'], validate=True), 'frame_wire_png_not_original')
    with np.load(BytesIO(arrays), allow_pickle=False) as values:
        owners, triangles = values['owners'], values['triangle_ids']
        occupied = owners >= 0
        checked(values['face_patch_offsets'].tolist() == offsets
                and values['owner_mapping_identity'].item() == frame['owner_mapping_identity']
                and values['patch_mapping_identity'].item() == frame['patch_mapping_identity']
                and values['triangle_id_scope'].item() == frame['triangle_id_scope']
                and np.all(owners[occupied] < len(current))
                and np.all(triangles[~occupied] == -1)
                and np.isfinite(values['depth'][occupied]).all(), 'scoped_arrays_owner_identity_invalid')
        for index, (lo, hi) in enumerate(zip(offsets, offsets[1:])):
            checked(np.all((triangles[owners == index] >= lo) & (triangles[owners == index] < hi)),
                    'scoped_triangle_wrong_owner')
    paths.extend([Path(log['PNG']), Path(log['NPZ'])])
    return {'PNG': png, 'NPZ': npz, 'ref': log['ref'], 'frame_identity': log['frame_identity'],
            'image_block': image['native_content_block_index'], **frame_geometry(log, subset, raw, arrays, truth)}


def check_negative(function, reason):
    try:
        function()
    except ValueError as error:
        checked(str(error) == reason, 'negative_control_rejected_for_unrelated_reason')
        return reason
    raise ValueError('negative_control_was_accepted/' + reason)


def audit(run):
    slot = (run / 'slots/P1').resolve()
    paths = [Path(__file__), DECODER, INSTALL_PATH, TRUTH, FROZEN_REVIEW, HERE / 'evidence.py', HERE / 'review.py']
    install = library()
    decoder = runpy.run_path(str(DECODER))
    captures, commands = decoder['decode_captures'](slot, install, decoder['Audit']())
    native, = [row for row in commands if row['command']['command'] == 'capture_active_observation']
    native_path = slot / 'native/WIRE' / f"{native['wire_sequence']:03d}"
    paths.extend(sorted((slot / 'native/WIRE').glob('*/REQUEST.bin')))
    paths.extend(sorted((slot / 'native/WIRE').glob('*/RESPONSE.bin')))
    paths.extend([slot / name for name in ('DEVICE_EVIDENCE.json', 'SLOT_RESULT.json', 'TERMINAL_SOURCE.json',
                                          'initial_capture/TERMINAL_SOURCE.json', 'SLOT_PUBLICATION.json')])
    terminal, initial = (read(slot / name) for name in ('TERMINAL_SOURCE.json', 'initial_capture/TERMINAL_SOURCE.json'))
    result = read(slot / 'SLOT_RESULT.json')
    closed = result['closure_verification']
    checked(closed['passed'] and closed['status'] == 'ready_closed' and
            result['independent_before_after']['passed'] and terminal['objects'] == initial['objects']
            and terminal['display_object_mask'] == initial['display_object_mask'] == [True] * 21,
            'production_slot_not_closed_or_scene_modified')
    argument = {'mode': 'active_observation', 'objects': [{'name': 'M09'}], 'task_query': {
        'mode': 'task', 'objects': [{'name': 'M09'}, {'name': 'M03'}], 'requested_facts': ['surface_proximity']}}
    owner2, tx2, rx2, cli2 = delivery(slot, 2, paths)
    owner3, tx3, rx3, cli3 = delivery(slot, 3, paths)
    checked(tx2['params']['arguments'] == {'query': argument, 'response_detail': 'brief', 'include_image': True}
            and tx2['params']['name'] == 'human_eye_scene_observe' and tx3['params']['name'] == 'read_images'
            and cli2['CLI_images'] == 2 and cli3['CLI_images'] == 1, 'original_attempt_selection_changed')
    owner_product = owner2 / 'PRODUCT_RECEIPT.json'
    public_record = read(owner_product)
    producer_archive = public_record['producer_archive']
    producer_path = Path(producer_archive['path'])
    _, producer = actual(producer_path, producer_archive['sha256'], slot)
    producer = json.loads(producer)
    binding = producer['binding']
    wire = slot / 'mcp' / f"rpc_{public_record['receipt']['index']:02d}"
    product_tx, product_rx = (read(wire / file) for file in ('TX.bin', 'RX.bin'))
    checked(product_tx['params']['arguments'] == tx2['params']['arguments'] and
            product_tx == read(owner2 / 'PRODUCT_REQUEST.json')
            and rx2 == read(owner2 / 'PRODUCT_RESPONSE.json')['result'] == product_rx['result']
            and pin(wire / 'RX.bin')['sha256'] == public_record['receipt']['RX_sha256'],
            'public_product_response_not_original_attempt_2')
    paths.extend([owner_product, producer_path, wire / 'TX.bin', wire / 'RX.bin',
                  owner2 / 'PRODUCT_REQUEST.json', owner2 / 'PRODUCT_RESPONSE.json'])
    capture, = [row for row in captures if row['capture_state'] == binding['capture_state']]
    by_id = verify_capture(capture, binding, terminal, install)
    subset = {'objects': [by_id[key] for key in capture['observation_target']['retained_object_ids']]}
    brief = json.loads(rx2['content'][0]['text'])
    brief_binding = brief['binding']
    condensed_target = brief_binding['observation_target']
    checked(producer['result_kind'] == 'active_observation' and producer['read_only'] is True and
            producer['execution_authority'] is False and brief['schema'] == 'active-observation-brief-v5'
            and all(binding[key] == value for key, value in brief_binding.items()
                    if key not in ('capture_state', 'observation_target'))
            and brief_binding['capture_state'] ==
                {key: binding['capture_state'][key] for key in ('instance_id', 'epoch', 'revision')}
            and all(binding['observation_target'][key] == value for key, value in condensed_target.items()
                    if key != 'full_scene_identity_sha256')
            and condensed_target['full_scene_identity_sha256'] ==
                digest(binding['observation_target']['full_scene_identity']) and
            brief['scope']['capture_object_count'] == 3 and brief['scope']['observation_scope'] ==
                {'kind': 'target', 'target_object_index': 0, 'target_object_count': 1,
                 'occluder_only_object_count': 2, 'full_scene_object_count': 21, 'excluded_object_count': 18},
            'original_brief_scope_or_binding_mismatch')

    truth = read(TRUTH)
    meshes = sorted(ORACLE['coordinates'](terminal['objects']), key=lambda row: row['name'])
    kept = [row for row in meshes if row['name'] in OBJECTS]
    old = runpy.run_path(str(ORACLE['OLDER'] / 'oracle.py'))
    _, geom = old['helpers']()
    ledger = read(slot / 'DEVICE_EVIDENCE.json')
    frames = []
    public_images = [dict(zip(brief['images']['columns'], row, strict=True)) for row in brief['images']['rows']]
    checked([row['view_name'] for row in producer['frames']] == ['SCENE', 'LEFT'], 'actual_producer_frame_order_changed')
    for frame, image in zip(producer['frames'], public_images, strict=True):
        log, = [row for row in ledger['frames'] if row['ref'] == frame['image_ref']]
        record = frame_checks(frame, log, binding, subset, truth,
                              rx2['content'][image['native_content_block_index']], image, paths, slot)
        direction = log['direction_rational']
        hits = old['occluders'](meshes, truth['region'], direction, geom)
        kept_hits = old['occluders'](kept, truth['region'], direction, geom)
        frozen = truth['region']['finite_direction_proofs'][record['camera']]
        checked(hits == kept_hits == frozen['positive_area_occluders'],
                'scoped_culling_omitted_a_positive_area_full_scene_blocker')
        record.update(all_21_objects_recomputed=True, full_scene_tested_other_triangles=182,
                      retained_tested_other_triangles=22, positive_area_occluders=hits)
        frames.append(record)
    scene, left = frames
    checked(not scene['qualifies'] and scene['surface_pixels'] == scene['contrasting_boundary_pixels'] == 0
            and [(r['object_name'], r['source_triangle_index'], r['rectangle_overlap_fraction'])
                 for r in scene['positive_area_occluders']] == [('M03', 12, '1')]
            and left['qualifies'] and left['source_triangles'] == [0, 1] and left['all_corners_in_frame']
            and (left['surface_pixels'], left['contrasting_boundary_pixels']) == (146797, 1530),
            'actual_SCENE_failure_or_LEFT_complete_witness_changed')

    caption, repeat = rx3['content']
    heading, image_path = caption['text'].splitlines()
    exposed = json.loads(image_path)
    ordinary, = read(owner3 / 'RECEIPT.json')['local_image_delivery']
    checked(repeat == rx2['content'][left['image_block']] and tx3['params']['arguments'] == {'refs': [left['ref']]}
            and heading.startswith(left['ref'] + ' ') and exposed == {'local_image_path': left['PNG']['path'],
            'image_sha256': left['PNG']['sha256']} and ordinary == {'ref': left['ref'], **exposed},
            'read_images_did_not_expose_the_same_actual_LEFT_file')
    raster_path = slot / 'product_audit.jsonl'
    paths.append(raster_path)
    raster_events = [row for row in P3['lines'](raster_path) if row['event'] == 'active_observation_render_attempt']
    cache_events = [row for row in ledger['events'] if row.get('event') == 'frame_cache_hit' and
                    row.get('ref') == left['ref'] and row.get('requested_by') == 'image_specification']
    raster_binding = digest({key: value for key, value in binding.items() if key not in APPENDED |
                             {'binding_sha256', 'camera_specification', 'geometry_identity', 'camera_identity'}})
    checked(result['budget']['slots']['P1']['raster_actual'] == 2
            and producer['work']['raster_completed'] == len(raster_events) == 2 and
            [row['view_name'] for row in raster_events] == ['SCENE', 'LEFT'] and
            all(row['binding_digest'] == raster_binding for row in raster_events) and cache_events,
            'read_images_reconstructed_a_frame_or_raster_ledger_changed')

    answer, final, attachments = P3['final_item'](slot)
    paths.extend([slot / 'consumer/PUBLIC_FINAL.txt', slot / 'consumer/events.jsonl'])
    refs = P3['final_reference_kinds'](answer, [row['PNG']['path'] for row in frames])
    frozen_row, = [row for row in read(FROZEN_REVIEW)['slots'] if row['label'] == 'P1']
    checked(not refs and not attachments and not frozen_row['reopen_candidates']
            and [row['error'] for row in frozen_row['frames']] == ['frame_complete_display_domain_unbound'] * 2,
            'original_unlinked_answer_or_frozen_reviewer_changed')
    wrong_scope = check_negative(lambda: verify_capture(capture, {**binding, 'capture_scope': 'complete_scene_meshes'},
                                                       terminal, install), 'expected_target_observation_scope')
    wrong_epoch = check_negative(lambda: verify_capture(capture, {**binding, 'document_epoch': '0' * 64},
                                                       terminal, install), 'capture_generation_or_document_mismatch')
    return {'schema': 'perf050-transfer-P1-scoped-active-observation-audit-v1', 'passed': True, 'slot': 'P1',
            'source_pins': [pin(path) for path in sorted(set(paths))],
            'source': {'asset_sha256': ORACLE['ASSET_SHA'], 'capture_scope': SCOPE, 'retained_objects': OBJECTS,
                       'retained_triangles': 24, 'complete_scene_objects': 21, 'complete_scene_triangles': 184,
                       'excluded_object_count': 18, 'native_capture_receipt': pin(native_path / 'RESPONSE.bin'),
                       'binding_sha256': binding['binding_sha256'], 'source_binding_sha256': binding['source_binding_sha256'],
                       'all_21_terminal_displayed_before_and_after': True},
            'attempt_2': {'CLI_item': cli2['caller_identity']['CLI_event_item_id'], 'CLI_RX_sha256': cli2['RX_sha256'],
                          'producer': pin(producer_path), 'frames': frames},
            'attempt_3': {'CLI_item': cli3['caller_identity']['CLI_event_item_id'], 'CLI_RX_sha256': cli3['RX_sha256'],
                          'same_LEFT_PNG_bytes': True, 'delivered_path': exposed, 'new_raster_attempts': 0,
                          'frame_cache_events': len(cache_events)},
            'negative_controls': {'wrong_capture_scope': wrong_scope, 'wrong_document_binding': wrong_epoch},
            'final': {'original': final, 'authored_references': refs, 'structured_attachments': attachments,
                      'authored_reference_file_reopen': 'unrun_no_authored_reference', 'human_click': 'unobserved'},
            'scope_limit': 'Target-scoped raster. Full-scene geometry independently verifies just these two directions and this target. '
                           'The retained PNG and buffers describe its local viewport only.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'SCOPED_ACTIVE_OBSERVATION.json')
    args = parser.parse_args()
    output = audit(args.runtime)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
