"""Read-only technical review of the two closed qualification originals."""

import base64
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import runpy

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SLOTS = Path('D:/he_m4_rail_blocker_consumption_001/slots')
TRUTH_SHA = 'd4daeb84945dddb0b1d511dd0931dc38adcbaae7eb2e7c68080fd068a972ebe0'
PIXELS = REPO / 'verification/m4_cross_scale_live_task_formal_001/scoring/formal.py'
GEOMETRY = REPO / 'verification/m4_bound_blocker_evidence_001/checks/geometry_controls.py'
INITIAL_SCENE = Path('D:/he_m4_cross_scale_cold_frustum_001/slots/B1/TERMINAL_SOURCE.json')


def require(value, error):
    if not value:
        raise ValueError(error)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def table(value):
    return [dict(zip(value['columns'], row, strict=True)) for row in value['rows']]


def replay_wire(slot, entry):
    call = slot / 'client/call_01'
    index = entry['transport_index']
    transport = slot / 'client/transport' / f'rpc_{index:02d}'
    owner = slot / 'owner/tool_01'
    relay, = (slot / 'client/attachments').glob(f'bridge_*/{index:03d}')
    receipt = read(transport / 'RECEIPT.json')
    inputs = {}
    for key, filename in (('TX', 'REQUEST.json'), ('RX', 'RESPONSE.json')):
        raw = (transport / f'{key}.bin').read_bytes()
        require(len(raw) == receipt[f'{key}_bytes'] and raw == (owner / filename).read_bytes()
                == (relay / f'{key}.bin').read_bytes() and json.loads(raw) == read(call / filename),
                f'original_stdio_mismatch/{key}')
        inputs[key] = raw
    rx_sha = digest(inputs['RX'])
    require(rx_sha == receipt['RX_sha256'] and read(call / 'RECEIPT.json') == receipt
            and not receipt['error'] and 'TX_sha256' not in receipt, 'unexpected_original_transport_contract')
    response = json.loads(inputs['RX'])
    require(response['id'] == json.loads(inputs['TX'])['id'] == receipt['id'] and response['result']['isError'] is False,
            'original_wire_id_or_result_mismatch')
    return response['result']['content'], {'derived_TX_sha256': digest(inputs['TX']), 'receipt_RX_sha256': rx_sha,
           'TX_bytes': receipt['TX_bytes'], 'RX_bytes': receipt['RX_bytes'], 'receipt_has_TX_sha256': False}


def verify_pixels(slot, frames, rendered, witnesses, targets, objects, scopes, content, terminal, helpers):
    result = {}
    for witness in witnesses:
        index = witness['region_index']
        region = targets[index]
        original = objects[index]
        frame = frames[witness['frame_index']]
        record, = (item for item in rendered if item['ref'] == frame['image_ref'])
        require(record['origin'] == 'product' and record['view'] == frame['view_name'] == 'SCENE'
                and record['direction_rational'] == [4, -4, 3] and record['frame_identity'] == frame['frame_identity']
                and record['scope_id'] == scopes[frame['scope_index']]['scope_id'] != 'global', 'local_product_frame_unbound')
        block = frame['native_content_block_index']
        png, npz = (Path(record[key]).read_bytes() for key in ('PNG', 'NPZ'))
        require(digest(png) == record['PNG_sha256'] == frame['image_sha256'] and digest(npz) == record['NPZ_sha256']
                and len(png) == record['PNG_bytes'] and len(npz) == record['NPZ_bytes']
                and content[block]['type'] == 'image' and content[block]['mimeType'] == 'image/png'
                and png == base64.b64decode(content[block]['data'], validate=True)
                == (slot / 'client/call_01/delivered' / f'block_{block:02d}.png').read_bytes(), 'original_png_npz_unbound')
        with Image.open(BytesIO(png)) as image, np.load(BytesIO(npz), allow_pickle=False) as arrays:
            require(np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]),
                    'original_PNG_rgb_differs_from_matching_NPZ')
            surface, boundary, points = helpers['pixels'](record, original, terminal, arrays)
            require(helpers['in_frame'](record['pose'], points, (4, -4, 3)) and surface >= 16 and boundary >= 4
                    and (surface, boundary) == (witness['visible_surface_pixels'], witness['contrasting_boundary_pixels'])
                    and region['status'] == 'covered' and 'SCENE' in original['eligible_complete_views'], 'local_visibility_mismatch')
        result[original['object_name']] = {'source_triangle_indices': original['source_triangle_indices'],
            'image_ref': frame['image_ref'], 'frame_identity': frame['frame_identity'], 'PNG_sha256': digest(png),
            'NPZ_sha256': digest(npz), 'actual_MCP_block': block, 'surface_pixels': surface, 'contrast_boundary_pixels': boundary}
    return result


def verify_blockers(body, producer, source, regions, oracle, helpers):
    binding, compact = producer['binding'], body['blocker_evidence']
    original = producer['facts']['region_task']['blocker_evidence']
    scope = table(body['scopes'])[compact['scope_index']]
    require(scope['scope_id'] == original['scope_id'] == 'global' and all(
        scope[key] == original[key] == binding[key] for key in ('camera_identity', 'binding_sha256'))
        and original['source_binding_sha256'] == binding['source_binding_sha256'], 'blocker_scope_unbound')
    poses = {pose['name']: pose for pose in binding['camera_specification']['views']}
    result = {}
    objects = table(body['objects'])
    for row, evidence in zip(table(compact), original['rows'], strict=True):
        index, view, oi, ti = (row[key] for key in ('region_index', 'view_name', 'blocker_object_index', 'source_triangle_index'))
        kind = 'positive_area_occlusion_all_front_views'
        candidate = oracle[index]
        obj = objects[oi]
        name = obj['object_name']
        mesh = source[name]['evaluated']
        triangle = [mesh['vertices_world_m'][j] for j in mesh['triangles'][ti]]
        require(name == 'M12' and ti == 10 and view == 'LEFT' and poses[view]['direction_rational'] == [-1, 0, 1]
                and source[name]['visible_get'] and obj == binding['objects'][oi]
                and obj['host_id'] == evidence['blocker_host_id'] == source[name]['object_id']
                and obj['instance_id'] == evidence['blocker_instance_id'] == source[name]['instance_id']
                and (evidence['roi_id'], evidence['view_name'], evidence['blocker_object_index'], evidence['source_triangle_index'])
                == (regions[index]['roi_id'], view, oi, ti) and regions[index]['reason'] == kind
                and candidate['expected_unknown_reason'] == kind, 'current_blocker_object_or_triangle_mismatch')
        chart, screen = helpers['independent_overlap'](triangle, candidate['corners_world_m'], poses[view])
        true_row, = (item for item in candidate['finite_direction_proofs'][view]['positive_area_occluders']
                     if item['object_name'] == name and item['source_triangle_index'] == ti)
        require(chart / 4 == Fraction(true_row['projected_target_plane_area_m2_exact']) > 0
                and screen == Fraction(evidence['overlap_area_screen_exact']) > 0, 'current_blocker_exact_area_mismatch')
        result[candidate['object_name']] = {'blocker_object_name': name, 'source_triangle_index': ti, 'view': view,
                                             'projected_target_plane_area_m2_exact': str(chart / 4),
                                             'screen_overlap_exact': str(screen)}
    return result


def check(label, truth, pixel_helpers, geometry):
    slot = SLOTS / label
    published = read(slot / 'SLOT_PUBLICATION.json')
    result_path = slot / 'SLOT_RESULT.json'
    require(digest(result_path.read_bytes()) == published['result_sha256'], 'result_changed_since_publication')
    result = read(result_path)
    require(result['status'] == 'completed' and result['closure_verification']['passed'] and result['model_consumers'] == 0,
            'owned_host_not_closed')
    terminal_path = slot / 'TERMINAL_SOURCE.json'
    sealed = read(INITIAL_SCENE)
    require(digest(INITIAL_SCENE.read_bytes()) == truth['terminal_sha256'] and
            digest(terminal_path.read_bytes()) == result['terminal_source']['sha256'], 'terminal_capture_unbound')
    terminal = read(terminal_path)
    require(terminal['source']['asset_sha256'] == sealed['source']['asset_sha256'] == truth['asset_sha256'], 'asset_mismatch')
    maps = [{row['name']: row for row in source['objects']} for source in (terminal, sealed)]
    require(maps[0].keys() == maps[1].keys() and all(
        maps[0][name]['evaluated'] == maps[1][name]['evaluated'] and maps[0][name]['visible_get'] == maps[1][name]['visible_get']
        for name in maps[0]), 'closed_slot_geometry_differs_from_frozen_truth_source')
    content, wire = replay_wire(slot, result['diagnostic_calls'][0])
    body = json.loads(content[0]['text'])
    require(body['read_only'] and body['execution_authority'] is False, 'unexpected_authority')
    targets, objs = table(body['region_task']), table(body['objects'])
    expected = {(row['object_name'], tuple(row['source_triangle_indices'])): row for row in truth['eligible']}
    keys = [(objs[row['object_index']]['object_name'], tuple(i for lo, hi in row['source_triangle_index_ranges']
                                                           for i in range(lo, hi + 1))) for row in targets]
    require(len(keys) == len(set(keys)) == 4 and set(keys) == set(expected), 'public_roster_differs')
    oracle = [expected[key] for key in keys]
    require(all(row['center_world_m'] == item['center_world_m'] and row['front_direction_world'] == item['unit_normal']
                for row, item in zip(targets, oracle, strict=True)), 'public_geometry_differs')
    require(all(row['status'] == 'unknown' and row['reason'] == item['expected_unknown_reason']
                and row['view_reasons']['positive_area_occlusion'] == ['LEFT']
                for row, item in zip(targets, oracle, strict=True) if item['unit_normal'] == [-1, 0, 0]),
            'public_negative_endface_reason_differs')
    device = read(slot / 'DEVICE_EVIDENCE.json')
    require(device['terminal_source']['sha256'] == result['terminal_source']['sha256'], 'device_ledger_terminal_mismatch')
    pixels = verify_pixels(slot, table(body['frames']), device['frames'], table(body['witnesses']), targets, oracle,
                           table(body['scopes']), content, terminal, pixel_helpers)
    require(set(pixels) == {'M17', 'M18'} and len(device['frames']) == 3, 'missing_actual_originals')
    blocked = {}
    if label == 'QA':
        require('blocker_evidence' not in body, 'baseline_unexpected_blocker_field')
    else:
        receipt = read(slot / 'owner/tool_01/PRODUCT_RECEIPT.json')['producer_archive']
        raw = Path(receipt['path']).read_bytes()
        require(receipt['new_observations_for_archive'] == 0 and digest(raw) == receipt['sha256'], 'producer_archive_mismatch')
        blocked = verify_blockers(body, json.loads(raw), maps[0], targets, oracle, geometry)
        require(set(blocked) == {'M17', 'M18'}, 'missing_current_blocker_evidence')
    return {'label': label, 'published_result_sha256': published['result_sha256'], 'wire': wire,
            'actual_frames': len(device['frames']), 'local_SCENE': pixels, 'blocker_evidence': blocked}


def main():
    path = HERE / 'CURRENT_TRUTH.json'
    require(digest(path.read_bytes()) == TRUTH_SHA, 'frozen_truth_mismatch')
    truth, pixel_helpers, geometry = read(path), runpy.run_path(str(PIXELS)), runpy.run_path(str(GEOMETRY))
    review = [check(label, truth, pixel_helpers, geometry) for label in ('QA', 'QB')]
    for name in ('M17', 'M18'):
        values = (row['local_SCENE'][name] for row in review)
        a, b = ({key: value for key, value in row.items() if key != 'image_ref'} for row in values)
        require(a == b, 'paired_witness_drift/' + name)
    original = read(HERE.parent / 'QUALIFICATION.json')
    require(original['passed'] is False, 'original_gate_must_remain_false')
    print(json.dumps({'schema': 'm4-rail-qualification-originals-forensic-review-v1',
                      'verified_local_images_and_blockers': True, 'original_gate_passed': original['passed'],
                      'truth_sha256': TRUTH_SHA, 'closed_slots': review}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
