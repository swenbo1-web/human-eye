"""Independently bind both zero-model qualifications to the originals and admit the formal pair."""

import argparse
from fractions import Fraction
import itertools
import hashlib
import io
import json
import math
from pathlib import Path
import sys

from diagnostic import NS, V, diagnostic_plan, legacy


RUN = Path('D:/he_m4_cross_scale_assembly_transfer_001')
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
PRODUCT = V / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE = 'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7'
PIXELS = legacy('_assembly_qualification_formal_pixels', FORMAL / 'scoring/formal.py')
TYPED = legacy('_assembly_qualification_typed_content', FORMAL / 'checks/typed_diagnostic.py')
CLI = legacy('_assembly_qualification_cli', V / 'm4_cross_scale_live_task_recovery_001/qualify.py')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def vec(value):
    return tuple(map(Fraction, value))


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def wire(slot, ordinal, frozen_row, expected):
    directory = slot / 'client' / f'call_{ordinal:02d}'
    owner = slot / 'owner' / f'tool_{ordinal:02d}'
    index = frozen_row['transport_index']
    rpc = slot / 'client/transport' / f'rpc_{index:02d}'
    thin, = (slot / 'client/attachments').glob(f'bridge_*/{index:03d}')
    request_path, response_path = directory / 'REQUEST.json', directory / 'RESPONSE.json'
    request, response = read(request_path), read(response_path)
    require(request['params'] == expected and request['id'] == response['id'] and
            frozen_row['request_sha256'] == sha(request_path) and frozen_row['response_sha256'] == sha(response_path) and
            frozen_row['tool_error'] is False, 'original_qualification_business_receipt_changed')
    for direction, name, data in (('TX', 'REQUEST.json', request), ('RX', 'RESPONSE.json', response)):
        raw = (rpc / f'{direction}.bin').read_bytes()
        require(raw == (thin / f'{direction}.bin').read_bytes() == (owner / name).read_bytes() and
                json.loads(raw) == data, 'owner_thin_and_client_diagnostic_wire_differ/' + direction)
    meter = read(rpc / 'RECEIPT.json')
    bridge = read(thin / 'RECEIPT.json')
    receipt = read(owner / 'RECEIPT.json')
    require(meter == read(directory / 'RECEIPT.json') and meter['error'] is None and
            meter['RX_sha256'] == sha(rpc / 'RX.bin') and
            meter['RX_bytes'] == bridge['response_bytes'] == receipt['response_bytes'] and
            meter['TX_bytes'] == bridge['request_bytes'] and bridge['origin'] == 'owner' and
            request['id'] == bridge['RPC_id'] == receipt['RPC_id'] == meter['id'] and
            receipt['status'] == 'returned' and receipt['is_error'] is False,
            'original_transport_receipt_identity_unbound')
    require(frozen_row['readback_sha256'] == sha(directory / 'delivered/READBACK.json'),
            'typed_readback_artifact_changed')
    contract = 'active_region_task' if expected['name'] == 'human_eye_scene_observe' else 'ordinary'
    fact, texts, images = TYPED.verify_content(response, contract=contract, fact_index=0)
    require(len(images) == frozen_row['images'] and sum(row['UTF8_bytes'] for row in texts) ==
            frozen_row['text_UTF8_bytes'] and sum(len(raw) for _, raw in images) ==
            frozen_row['delivered_PNG_bytes'], 'typed_consumer_byte_counts_changed')
    return response, fact, images, receipt


def ordinary_geometry(slot, answer, terminal):
    require((answer['objects'], answer['vertices'], answer['triangles']) == (28, 416, 744),
            'current_ordinary_scene_denominator_changed')
    ledger = read(slot / 'DEVICE_EVIDENCE.json')
    receipt, = [row for row in ledger['sources'] if not row['terminal'] and row['source_ref'] == answer['source_ref']]
    require(receipt['status'] == 'complete' and receipt['worker']['pid'] == terminal['source']['pid'],
            'ordinary_capture_does_not_match_current_worker')
    packet = json.loads(PIXELS.verified(receipt['path'], receipt['sha256'], slot))
    expected = {entry['name']: entry for entry in terminal['objects']}
    names = {mesh['name'] for mesh in packet['objects']}
    require(names == expected.keys() and len(names) == len(packet['objects']), 'ordinary_current_object_roster_changed')
    for mesh in packet['objects']:
        ref = expected[mesh['name']]
        require(mesh['object_id'] == ref['object_id'] and mesh['instance_id'] == ref['instance_id'] and
                mesh['visible_get'] == ref['visible_get'] and
                [vec(p) for p in mesh['vertices']] == [vec(p) for p in ref['evaluated']['vertices_world_m']] and
                mesh['triangles'] == ref['evaluated']['triangles'], 'ordinary_ordered_world_geometry_differs/' + mesh['name'])
    return {'source_ref': answer['source_ref'], 'ordered_world_geometry': True, 'source_sha256': receipt['sha256']}


def current_frame(slot, frame, terminal, target, truth):
    import numpy as np
    from PIL import Image

    raw = PIXELS.verified(frame['PNG'], frame['PNG_sha256'], slot)
    archive = PIXELS.verified(frame['NPZ'], frame['NPZ_sha256'], slot)
    with Image.open(io.BytesIO(raw)) as png, np.load(io.BytesIO(archive), allow_pickle=False) as arrays:
        require(png.format == 'PNG' and png.size == (512, 512) and
                np.array_equal(np.asarray(png.convert('RGB')), arrays['color'][:, :, :3]),
                'actual_frame_PNG_and_NPZ_color_differ')
        surface, boundary, points = PIXELS.pixels(frame, target, terminal, arrays)
    view = frame['view']
    require(frame['direction_rational'] == truth['directions'][view]
            and PIXELS.in_frame(frame['pose'], points, truth['directions'][view]), 'qualification_camera_or_framing_changed')
    return {'ref': frame['ref'], 'frame_identity': frame['frame_identity'], 'direction': view,
            'surface_pixels': surface, 'contrasting_boundary_pixels': boundary,
            'qualifies': view in target['eligible_complete_views'] and surface >= 16 and boundary >= 4,
            'PNG_sha256': frame['PNG_sha256'], 'NPZ_sha256': frame['NPZ_sha256']}, raw


def native(slot, truth, terminal, fact, image_blocks, owner):
    answer = json.loads(fact['stdout'])
    geometry = ordinary_geometry(slot, answer, terminal)
    expected = {row['object_name']: row for row in truth['eligible']}
    rows = {row['object_name']: row for row in answer['regions']}
    require(set(rows) == set(expected) and len(rows) == len(answer['regions']), 'ordinary_region_roster_changed')
    frames = {frame['ref']: frame for frame in read(slot / 'DEVICE_EVIDENCE.json')['frames']}
    originals = {entry['ref']: raw for entry, raw in image_blocks}
    require([entry['ref'] for entry, _ in image_blocks] == [item['ref'] for item in owner['image_attachments']]
            and all(item['delivery_ready'] and hashlib.sha256(originals[item['ref']]).hexdigest() == item['PNG_sha256']
                    for item in owner['image_attachments']), 'ordinary_attachment_and_caption_binding_changed')
    details, seen = {}, set()
    for name, row in rows.items():
        target = expected[name]
        require(row['triangles'] == target['source_triangle_indices'] and
                all(math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-7) for a, b in
                    zip(vec(row['center_world_m']), vec(target['center_world_m']), strict=True)) and
                math.isclose(row['area_m2'], target['area_m2'], rel_tol=0, abs_tol=1e-9) and
                all(math.isclose(a, b, rel_tol=0, abs_tol=1e-9) for a, b in
                    zip(row['unit_normal'], target['unit_normal'], strict=True)), 'ordinary_numeric_truth_changed/' + name)
        clear = set(target['eligible_complete_views'])
        require(set(row['directions']) == set(truth['directions']) and
                {k for k, v in row['directions'].items() if v == 'complete_geometry'} == clear,
                'ordinary_geometric_direction_list_changed/' + name)
        for view, verdict in row['directions'].items():
            if view in clear:
                continue
            parts = verdict.split('/')
            require(len(parts) == 3 and parts[0] == 'positive_area_front_occluder' and any(
                item['object_name'] == parts[1] and str(item['source_triangle_index']) == parts[2] and
                Fraction(item['rectangle_overlap_fraction']) > 0
                for item in target['finite_direction_proofs'][view]['positive_area_occluders']),
                'ordinary_positive_area_source_unverified/' + name + '/' + view)
        probes = []
        for probe in row['probes']:
            frame = frames[probe['ref']]
            require(frame['source_ref'] == answer['source_ref'], 'ordinary_frame_wrong_current_capture')
            measured, raw = current_frame(slot, frame, terminal, target, truth)
            require(all(measured[k] == v for k, v in probe.items()) and measured['direction'] in clear,
                    'ordinary_reported_measured_pixels_differ/' + name)
            probes.append(measured)
            if measured['qualifies']:
                require(originals.get(frame['ref']) == raw and row['witness'] == probe and
                        row['status'] == 'covered' and row['reason'] == 'observed_readable',
                        'ordinary_witness_not_delivered/' + name)
                seen.add(frame['ref'])
        if name == 'N22':
            require(any(p['qualifies'] for p in probes), 'N22_complete_native_witness_missing')
        elif name == 'N10':
            require(len(probes) == 1 and probes[0]['direction'] == 'TOP', 'N10_native_TOP_actual_probe_missing')
            if not probes[0]['qualifies']:
                require(row['status'] == 'unknown' and row['witness'] is None and probes[0]['contrasting_boundary_pixels'] < 4
                        and probes[0]['surface_pixels'] >= 16 and row['reason'] == 'pixel_evidence_insufficient',
                        'N10_native_actual_contrast_shortfall_unexplained')
        else:
            require(not probes and row['status'] == 'unknown' and row['witness'] is None and
                    row['reason'] == 'positive_area_occlusion_all_front_views', 'N11_native_occlusion_scope_changed')
        details[name] = {**row, 'probes': probes}
    require(seen == set(originals), 'ordinary_received_extra_or_missing_PNG')
    return {'regions': details, 'ordinary_capture': geometry}


def installed(slot, truth, terminal, response, public, image_blocks):
    identity = read(slot / 'MCP_IDENTITY.json')
    require(identity['source_sha256'] == SOURCE and identity['source_file_count'] == 143 and
            identity['source_kind'] == 'installed_distribution', 'installed_product_source_unbound')
    call, = [json.loads(line) for line in (slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
    owner = slot / 'owner/tool_01'
    wire_dir = slot / 'mcp' / f"rpc_{call['receipt']['index']:02d}"
    tx, rx = ((wire_dir / (d + '.bin')).read_bytes() for d in ('TX', 'RX'))
    require(json.loads(tx) == read(owner / 'PRODUCT_REQUEST.json') == call['request'] and
            json.loads(rx) == read(owner / 'PRODUCT_RESPONSE.json') == call['response'] and
            read(wire_dir / 'RECEIPT.json') == call['receipt'] and hashlib.sha256(rx).hexdigest() ==
            call['receipt']['RX_sha256'] and call['request']['params'] == diagnostic_plan('P')[0] and
            call['response']['result'] == response['result'], 'installed_and_original_diagnostic_business_wire_differ')
    archive = call['producer_archive']
    product = json.loads(PIXELS.verified(archive['path'], archive['sha256'], slot))
    checker = legacy('_assembly_qualification_capture_binding',
                     V / 'm4_cross_scale_discovery_001/oracle/check_saved.py')
    audit = checker.Audit()
    captures, _ = checker.decode_captures(slot, read(PRODUCT), audit)
    binding = product['binding']
    capture = checker.current_capture(captures, binding, audit)
    checker.source_binding_checks(capture, binding, read(PRODUCT), audit)
    objects = {item['name']: item for item in terminal['objects']}
    require(len(objects) == len(capture['meshes']) == 28 and {m['name'] for m in capture['meshes']} == objects.keys()
            and all(item['visible_get'] for item in objects.values()), 'installed_current_mesh_roster_or_visibility_changed')
    for mesh in capture['meshes']:
        orig = objects[mesh['name']]
        require(orig['object_id'] == mesh['object_id'] and orig['instance_id'] ==
                capture['host_identity']['object_instances'][mesh['object_id']] and
                [vec(p) for p in mesh['vertices']] == [vec(p) for p in orig['evaluated']['vertices_world_m']]
                and mesh['faces'] == orig['evaluated']['triangles'], 'installed_source_geometry_unbound/' + mesh['name'])
    require(public['schema'] == 'active-observation-region-task-brief-v1' and public['read_only'] is True and
            public['execution_authority'] is False and public['binding'] ==
            {k: v for k, v in binding.items() if k not in ('schema', 'objects', 'camera_policy', 'camera_specification')},
            'public_region_task_source_and_read_only_contract_changed')
    expected = {row['object_name']: row for row in truth['eligible']}
    shown = {row['object_name']: row for row in public['region_task']['rows']}
    original = {row['object_name']: row for row in product['facts']['region_task']['rows']}
    require(set(expected) == set(shown) == set(original) and len(shown) == len(public['region_task']['rows']) ==
            len(product['facts']['region_task']['rows']), 'installed_region_roster_changed')
    scopes = {scope['scope_id']: scope for scope in product['scopes']}
    by_ref = {img['ref']: (img, raw) for img, raw in image_blocks}
    require(list(by_ref) == [frame['image_ref'] for frame in product['frames']],
            'installed_returned_images_differ_from_original_selection')
    details = {}
    for name, target in expected.items():
        row = original[name]
        projection = dict(shown[name])
        witness = projection['complete_witness']
        if witness is not None:
            projection['complete_witness'] = {k: v for k, v in witness.items() if k != 'native_content_block_index'}
        require(projection == row and row['source'] == checker.source_row(target, capture, binding),
                'installed_region_row_or_source_differs/' + name)
        obj = objects[name]
        center, u, v, front = [vec(row[key]) for key in ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m',
                                                        'front_direction_world')]
        corners = {tuple(c + i*x + j*y for c, x, y in zip(center, u, v)) for i, j in itertools.product((-1, 1), repeat=2)}
        require(center == vec(target['center_world_m']) and corners ==
                {vec(obj['evaluated']['vertices_world_m'][i]) for i in target['boundary_loops'][0]} and
                front[:2] == (0, 0) and front[2] > 0 and row['source_triangle_indices'] == target['source_triangle_indices'],
                'installed_exact_geometry_or_orientation_changed/' + name)
        eligible = set(target['eligible_complete_views'])
        probes = []
        for frame in product['constructed_frames']:
            if frame['view_name'] not in eligible or not (name == 'N10' or
                    witness is not None and frame['image_ref'] == witness['image_ref']):
                continue
            scope = scopes[frame['scope_id']]
            source = scope['binding']
            if scope['scope_id'] != 'global' and source['region_source'] != row['source']:
                continue
            if scope['scope_id'] != 'global':
                checker.local_binding_checks(scope, binding, row['source'], audit)
            require(frame['host_binding_sha256'] == source['binding_sha256'] and
                    frame['camera_identity'] == source['camera_identity'] and
                    frame['source_revision'] == source['scene_revision'], 'producer_artifact_current_scope_changed')
            names = [obj['object_name'] for obj in source['objects']]
            offsets = [0, *itertools.accumulate(len(objects[key]['evaluated']['triangles']) for key in names)]
            shape = {'PNG': frame['image_path'], 'NPZ': frame['arrays_path'],
                'PNG_sha256': frame['image_sha256'], 'NPZ_sha256': frame['arrays_sha256'], 'ref': frame['image_ref'],
                'frame_identity': frame['frame_identity'], 'view': frame['view_name'], 'pose': frame['pose'],
                'direction_rational': frame['pose']['direction_rational'], 'object_names': names,
                'object_ids': [obj['host_id'] for obj in source['objects']],
                'object_instance_ids': [obj['instance_id'] for obj in source['objects']],
                'display_object_mask': [True] * len(names), 'source_face_offsets': offsets}
            measured, raw = current_frame(slot, shape, terminal, target, truth)
            observation, = [o for o in scope['facts']['observations'] if o['frame_identity'] == frame['frame_identity']]
            pixel, = [p for p in observation['pixel_rows'] if p['roi_id'] == row['roi_id']]
            require(pixel['visible_surface_pixels'] == measured['surface_pixels'] and
                    pixel['contrasting_boundary_pixels'] == measured['contrasting_boundary_pixels'],
                    'installed_pixel_witness_or_shortfall_differ/' + name)
            probes.append(measured)
            if witness is not None and witness['image_ref'] == frame['image_ref']:
                img, bytes_ = by_ref[frame['image_ref']]
                require(raw == bytes_ and measured['qualifies'] and
                        img['content_index'] == witness['native_content_block_index'] and
                        measured['direction'] == witness['view_name'] and
                        measured['frame_identity'] == witness['frame_identity'], 'installed_selected_witness_unbound/' + name)
        if name == 'N22':
            require(row['status'] == 'covered' and witness is not None and any(p['qualifies'] for p in probes),
                    'N22_complete_installed_witness_missing')
        elif name == 'N10':
            require(any(p['direction'] == 'TOP' for p in probes), 'N10_installed_actual_TOP_probe_missing')
            if witness is None:
                require(row['status'] == 'unknown' and row['reason'] == 'pixel_evidence_insufficient' and any(
                    p['surface_pixels'] >= 16 and p['contrasting_boundary_pixels'] < 4 for p in probes)
                    and not any(p['qualifies'] for p in probes), 'N10_installed_actual_contrast_shortfall_unexplained')
            else:
                require(row['status'] == 'covered' and any(p['qualifies'] and p['ref'] == witness['image_ref'] for p in probes),
                        'N10_installed_bad_witness_acceptance')
        else:
            require(row['status'] == 'unknown' and witness is None and
                    row['reason'] == 'positive_area_occlusion_all_front_views' and
                    set(row['view_reasons']['positive_area_occlusion']) == set(truth['directions']),
                    'N11_installed_unknown_wrong_scope')
        details[name] = {'status': row['status'], 'reason': row['reason'], 'witness': witness, 'probes': probes}
    return {'regions': details, 'product_source_sha256': SOURCE, 'producer_archive_sha256': archive['sha256'],
            'product_wire_sha256': call['receipt']['RX_sha256'], 'checks': len(audit.checks)}


def assess_slot(label, freeze, truth):
    slot = RUN / 'slots' / label
    path = slot / 'SLOT_RESULT.json'
    result = read(path)
    publication = read(slot / 'SLOT_PUBLICATION.json')
    require(result['status'] == publication['status'] == 'completed' and publication['result_sha256'] == sha(path) and
            result['freeze_sha256'] == freeze and result['asset_sha256'] == ASSET and result['model_consumers'] == 0 and
            result['paid_API_calls'] == 0 and result['diagnostic_close']['confirmed'] and result['owner_close']['confirmed'] and
            result['closure_verification']['passed'] and result['independent_before_after']['passed'] and
            publication['owned_budget_passed'] and len(result['diagnostic_calls']) == 2,
            'actual_zero_model_current_slot_or_close_failed')
    scorer = legacy('_assembly_qualification_bound_terminal', NS / 'scoring/score.py')
    terminal, current = scorer.bound_terminal(slot, result, ASSET)
    one, two = [wire(slot, row, result['diagnostic_calls'][row-1], expected)
                for row, expected in enumerate(diagnostic_plan(label[1]), 1)]
    response, fact, images, owner = one
    buyback = ordinary_geometry(slot, json.loads(two[1]['stdout']), terminal)
    if label == 'QN':
        details = native(slot, truth, terminal, fact, images, owner)
        required = {'ordinary_stdout_geometry': response['result']['content'][0]['text']}
        required.update({name: caption['text'] for name, caption in enumerate(response['result']['content'])
                         if caption['type'] == 'text' and name})
    else:
        details = installed(slot, truth, terminal, response, fact, images)
        features = ('binding', 'region_task', 'images', 'witness_pixels')
        required = {name: compact(fact[name]) for name in features}
    cli = CLI.consumer_budget(response['result'], required)
    require(cli['passed'], 'necessary_actual_cli_body_or_PNG_truncated/' + compact(cli))
    return {'label': label, 'passed': True, 'result_sha256': sha(path), 'publication_sha256': sha(slot / 'SLOT_PUBLICATION.json'),
            'actual_models': result['model_consumers'], 'same_stage_readback': buyback,
            'current_closure': current, 'details': details, 'CLI_reconstruction': cli,
            'images': [img for img, _ in images], 'calls': result['diagnostic_calls']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=NS / 'QUALIFICATION.json')
    args = parser.parse_args()
    binding = read(PRODUCT)
    sys.path.insert(0, binding['dependency_root'])
    shared = read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path.insert(1, shared['dependency_root'])
    freeze = sha(NS / 'FROZEN.json')
    truth = read(NS / 'fixture/CURRENT_TRUTH.json')
    assessed = []
    for label in ('QN', 'QP'):
        path = RUN / 'slots' / label / 'SLOT_RESULT.json'
        try:
            assessed.append(assess_slot(label, freeze, truth))
        except Exception as error:
            assessed.append({'label': label, 'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                             'result_sha256': sha(path) if path.is_file() else None,
                             'original_status': read(path)['status'] if path.is_file() else 'unrun'})
    fairness = False
    if all(row['passed'] for row in assessed):
        ordinary, product = [read(RUN / 'slots' / label / 'client/TOOLS.json')['result']['tools'] for label in ('QN', 'QP')]
        fairness = ordinary == [tool for tool in product if tool['name'] != 'human_eye_scene_observe'] and len(product) == len(ordinary) + 1
    report = {'schema': 'm4-cross-scale-assembly-paired-qualification-v1',
              'passed': fairness and all(row['passed'] for row in assessed), 'freeze_sha256': freeze,
              'exact_common_tool_catalogue': fairness, 'actual_models': 0, 'slots': assessed}
    PIXELS.write(args.output, report)
    print(compact({'passed': report['passed'], 'fairness': fairness,
                   'slots': [{k: row[k] for k in ('label', 'passed', 'error') if k in row} for row in assessed]}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
