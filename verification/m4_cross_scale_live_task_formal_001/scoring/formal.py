"""Verify sealed formal evidence and record the nine independent answer grades."""

import argparse
import base64
from decimal import Decimal
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ROOT = NS.parents[1]
RUNTIME = Path('D:/he_m4_cross_scale_live_task_formal_001')
RECOVERY_RUNTIME = Path('D:/he_m4_cross_scale_live_task_recovery_001')
RECOVERY = ROOT / 'verification/m4_cross_scale_live_task_recovery_001'
SLOTS = ('N1', 'P1')
GATES = ('roster', 'geometry_M02', 'geometry_M06', 'geometry_M09', 'witness_M02', 'witness_M09',
         'finite_pool_unknown_M06', 'read_only_current_identity', 'no_contradictory_claim')
TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
PRODUCT_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'
PREVIOUS_FREEZE_SHA = 'dc10bc7ed44e5b3afe8a329cbe3ee031fba957954c828b4c8463f390293fd883'
PREVIOUS_QUALIFICATION_SHA = '8d15434785b3da2fda42bc48f71147efba331260b4284c1ee606054a103a2560'
ASSET = NS / 'fixture/ASSET_BINDING.json'
ASSET_BINDING_SHA = '3ce45a266d52e79be8b0147c4328b860ccd9e7a54a6ff5c371c25a6205fb5a46'
OWNED_WORKER = ROOT / 'verification/m4_global_local_qualification_001/harness/reused/owned_native.py'
DETAILED_SCHEMA = 'm4-live-source-region-terminal-source-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def verified(path, sha256, expected_parent):
    path = Path(path).resolve()
    require(path.is_relative_to(expected_parent.resolve()), 'evidence_outside_original_slot')
    raw = path.read_bytes()
    require(digest(raw) == sha256, 'bound_evidence_hash_mismatch/' + path.name)
    return raw


def truth():
    path = NS / 'fixture/CURRENT_TRUTH.json'
    raw = path.read_bytes()
    require(digest(raw) == TRUTH_SHA, 'frozen_current_truth_changed')
    value = json.loads(raw)
    require(value['current_blender_evaluated_readback'] is True, 'Blender_evaluated_truth_required')
    return value


def admission(expected):
    path = NS / 'ADMISSION.json'
    raw = path.read_bytes()
    permit = json.loads(raw)
    freeze_digest = digest((NS / 'FROZEN.json').read_bytes())
    require(type(permit['passed']) is bool and permit['slots'] == list(SLOTS) and
            permit['asset_sha256'] == expected['asset_sha256'] and permit['product_source_sha256'] == PRODUCT_SHA and
            permit['freeze_sha256'] == freeze_digest and
            permit['previous_freeze_sha256'] == PREVIOUS_FREEZE_SHA == digest((RECOVERY / 'FROZEN.json').read_bytes()),
            'formal_admission_freeze_task_or_product_differs')
    frozen_qualification = verified(RECOVERY / 'QUALIFICATION.json', PREVIOUS_QUALIFICATION_SHA, RECOVERY)
    old_gate = json.loads(frozen_qualification)
    require(permit['previous_qualification_sha256'] == PREVIOUS_QUALIFICATION_SHA and old_gate['passed'] is False and
            old_gate['freeze_sha256'] == PREVIOUS_FREEZE_SHA and old_gate['formal_denominator'] == list(SLOTS),
            'original_recovery_gate_or_denominator_differs')
    require([(r['label'], r['passed'], r['original_status']) for r in old_gate['slots']] ==
            [('QN', False, 'failed'), ('QP', True, 'completed')], 'original_qualification_statuses_changed')
    if permit['passed']:
        evidence_record = permit['evidence']
        evidence_path = Path(evidence_record['path']).resolve()
        require(evidence_path.is_relative_to(NS.resolve()) or evidence_path.is_relative_to(RUNTIME.resolve()),
                'derived_admission_evidence_outside_batch')
        evidence_bytes = evidence_path.read_bytes()
        require(len(evidence_bytes) == evidence_record['bytes'] and digest(evidence_bytes) == evidence_record['sha256'] and
                json.loads(evidence_bytes)['passed'] is True, 'derived_admission_evidence_mismatch')
        seals = permit['qualification_seals']
        require([r['label'] for r in seals] == ['QN', 'QP'], 'derived_admission_original_qualification_roster_differs')
        for seal, old_row in zip(seals, old_gate['slots'], strict=True):
            old_slot = RECOVERY_RUNTIME / 'slots' / seal['label']
            result = json.loads(verified(old_slot / 'SLOT_RESULT.json', seal['result_sha256'], old_slot))
            publication = read(old_slot / 'SLOT_PUBLICATION.json')
            reply = old_slot / 'client/call_01/RESPONSE.json'
            verified(reply, seal['response_sha256'], old_slot)
            require(seal['result_sha256'] == old_row['result_sha256'] == publication['result_sha256'] and
                    publication['status'] == old_row['original_status'] == result['status'] and
                    result['freeze_sha256'] == PREVIOUS_FREEZE_SHA and result['asset_sha256'] == expected['asset_sha256'] and
                    result['diagnostic_calls'][0]['response_sha256'] == seal['response_sha256'],
                    'derived_admission_original_raw_slot_differs/' + seal['label'])
    return permit, digest(raw), freeze_digest


def read_capture(slot, capture_path, receipt, pid, asset_sha):
    require(receipt.get('status') == 'complete' and receipt.get('terminal') is True and
            Path(receipt['path']).resolve() == capture_path.resolve(), 'no_bound_detailed_source/' + capture_path.name)
    raw = verified(receipt['path'], receipt['sha256'], slot)
    worker = receipt['worker']
    require(len(raw) == receipt['bytes'] == worker['bytes'] and worker['sha256'] == receipt['sha256'] and
            worker['pid'] == pid, 'detailed_source_worker_mismatch')
    packet = json.loads(raw)
    source = packet['source']
    require(packet.get('schema') == DETAILED_SCHEMA and source['pid'] == pid and
            Path(source['asset_copy']).resolve() == (slot / 'native/input.blend').resolve()
            and source['asset_sha256'] == asset_sha and source['frame'] == 1 and source['subframe'] == 0
            and source['scale_length'] == 1, 'source_asset_frame_units_or_schema_mismatch')
    require(packet['started_ns'] == worker['started_ns'] and
            packet['started_ns'] <= packet['display_read_closed_ns'] <= packet['geometry_read_closed_ns']
            <= worker['file_closed_ns'], 'detailed_source_clock_mismatch')
    return packet


def ordered_arrays(mesh):
    return {'vertices_local': mesh['vertices'], 'vertices_world': mesh['vertices_world_m'],
            'polygons': mesh['polygons'], 'triangle_polygon_indices': mesh['triangle_polygons'],
            'triangles': mesh['triangles']}


def verified_arrays(initial, final, baseline):
    for key in ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'display_scope',
                'display_read', 'layer_collections', 'scene_cameras'):
        require(initial[key] == final[key], 'before_after_detailed_scene_changed/' + key)
    expected = {row['name']: row for row in baseline['objects']}
    observed = {row['name']: row for row in final['objects']}
    require(len(expected) == len(observed) == len(final['objects']) and expected.keys() == observed.keys(),
            'detailed_scene_roster_mismatch')
    require(final['source']['view_layer'] == baseline['display_layer'] and
            final['source']['unit_settings']['system'] == baseline['unit_system'] and
            final['display_object_mask'] == [mesh['visible_get'] for mesh in final['objects']],
            'fixture_display_layer_or_order_changed')
    offsets = [0]
    for mesh in final['objects']:
        name = mesh['name']
        ref = expected[name]
        expected_visibility = {**ref['visibility']}
        require(mesh['visible_get'] == expected_visibility.pop('viewport') and
                all(mesh['display'][k] == v for k, v in expected_visibility.items()) and
                mesh['matrix_world'] == ref['evaluated_matrix_world'] and
                mesh['native_matrix_world'] == ref['matrix_world'] and mesh['parent'] == ref['parent'] and
                mesh['modifiers'] == ref['modifiers'] and mesh['mesh_name'] == ref['mesh_name'],
                'current_display_transform_or_mesh_identity_differs/' + name)
        for domain in ('native', 'evaluated'):
            arrays = mesh[domain]
            require(ordered_arrays(arrays) == ref[domain] and arrays['polygon_count'] == len(ref[domain]['polygons']),
                    'ordered_mesh_arrays_differs/' + name + '/' + domain)
        offsets.append(offsets[-1] + len(mesh['evaluated']['triangles']))
    require(final['source_face_offsets'] == offsets, 'current_source_face_offsets_differ')
    return len(observed)


def generic_process(slot, original, copied, asset_sha, deadline):
    startup = read(slot / 'native/SPAWN.json')
    ready = read(slot / 'native/READY.json')
    closed = read(slot / 'native/WORKER_CLOSED.json')
    config = read(slot / 'native/CONFIG.json')
    pid = startup['pid']
    command = startup['command']
    require(digest(original.read_bytes()) == digest(copied.read_bytes()) == asset_sha ==
            startup['asset_sha256'] == config['asset_sha256'] and
            Path(config['asset']).resolve() == original and Path(config['asset_copy']).resolve() == copied,
            'original_or_owned_copy_file_changed')
    require(Path(command[command.index('--python') + 1]).resolve() == OWNED_WORKER.resolve() and
            digest(OWNED_WORKER.read_bytes()) == startup['helper_sha256'] == ready['helper_sha256'] == config['helper_sha256'] and
            'qa_vertex_patch' not in config and 'qa_patch_applied' not in closed and
            startup['original_deadline_ns'] == ready['deadline_ns'] == closed['original_deadline_ns'] == config['deadline_ns'] == deadline and
            pid == ready['pid'] == closed['pid'], 'generic_worker_identity_or_read_only_mode_mismatch')
    closure = read(slot / 'RUNTIME_CLOSE.json')
    guard = closure['Blender_status']
    proof = closure['Blender_exit']
    close = closure['Blender_close']
    require(guard['ready'] == ready and guard['closed'] == closed and closed['poisoned'] is False and
            ready['initial_fingerprint'] == closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint'] and
            close['pid'] == pid and close['exit_code'] == 0 and close['process_reaped'] and
            proof['confirmed'] and proof['exited'] and proof['handle_closed'] and proof['exit_code'] == 0 and
            close['source_file_unchanged'] and close['protected_files_unchanged'] and
            guard['source_file_unchanged'] and guard['protected_files_unchanged'], 'generic_read_only_final_guard_failed')
    return startup, ready, closed


def terminal(slot, result, asset_sha):
    asset_binding = json.loads(verified(ASSET, ASSET_BINDING_SHA, NS))
    require(asset_sha == asset_binding['asset_sha256'], 'asset_binding_and_truth_differ')
    original = Path(asset_binding['asset_path']).resolve()
    copied = (slot / 'native/input.blend').resolve()
    deadline = result['owned_deadline_ns']
    startup, ready, closed = generic_process(slot, original, copied, asset_sha, deadline)
    pid = startup['pid']
    begin, end = result['initial_source'], result['terminal_source']
    initial = read_capture(slot, slot / 'initial_capture/TERMINAL_SOURCE.json', begin, pid, asset_sha)
    final = read_capture(slot, slot / 'TERMINAL_SOURCE.json', end, pid, asset_sha)
    require(startup['created_after_ns'] <= initial['started_ns'] <= begin['worker']['file_closed_ns'] <=
            result['ready_ns'] <= result['cleanup_started_ns'] <= final['started_ns'] <=
            end['worker']['file_closed_ns'] <= closed['closed_ns'] <= deadline, 'detailed_read_order_does_not_bracket_task')
    fixture_receipt = asset_binding['readback_after_reload']
    baseline = json.loads(verified(fixture_receipt['path'], fixture_receipt['sha256'], original.parent))
    count = verified_arrays(initial, final, baseline)
    return final, {'source_ref': end['source_ref'], 'sha256': end['sha256'], 'verified_object_count': count,
                   'asset_copy': str(copied), 'initial_capture_sha256': begin['sha256'],
                   'fixture_readback_sha256': fixture_receipt['sha256'],
                   'scope': 'Independent before/after display, source pointers, ordered native/evaluated arrays and generic worker closure.',
                   'unchanged_geometry_fingerprint': ready['initial_fingerprint']}


def delivered_images(slot):
    wire_root = slot / 'consumer/attachments'
    ledger = read(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')
    contracts = {row['attempt']: row for row in ledger['result_contracts']}
    images = {}
    for path in wire_root.glob('bridge_*/*/RX.bin'):
        receipt = read(path.with_name('RECEIPT.json'))
        attempt = receipt.get('attempt')
        if not attempt or attempt not in contracts:
            continue
        contract = contracts[attempt]
        if not contract.get('matched') or contract.get('reason') != 'content_and_envelope_match':
            continue
        raw = verified(path, contract['RX_sha256'], wire_root)
        reply = json.loads(raw)
        owner = slot / 'owner' / f'tool_{attempt:02d}'
        require(reply == read(owner / 'RESPONSE.json'), 'stdio_and_owner_response_differ')
        result = reply['result']
        if result['isError']:
            continue
        item_images = [(index, block) for index, block in enumerate(result['content']) if block['type'] == 'image']
        require(len(item_images) == contract['CLI_images'], 'CLI_image_count_does_not_match_original_stdio')
        if not item_images:
            continue
        if (owner / 'PRODUCT_RECEIPT.json').is_file():
            require(read(owner / 'PRODUCT_RESPONSE.json')['result'] == result, 'installed_product_images_differ_from_owner')
            producer = read(owner / 'PRODUCT_RECEIPT.json')['producer_archive']
            packet = json.loads(verified(producer['path'], producer['sha256'], slot))
            bindings = [(frame['image_ref'], frame['image_sha256'], frame['PNG_bytes'], frame['frame_identity'])
                        for frame in packet['frames']]
        else:
            attachments = read(owner / 'RECEIPT.json')['image_attachments']
            require(all(row['delivery_ready'] is True for row in attachments), 'ordinary_image_attachment_not_ready')
            bindings = [(row['ref'], row['PNG_sha256'], row['PNG_bytes_read'], None) for row in attachments]
        for (index, block), (ref, sha256, length, frame_identity) in zip(item_images, bindings, strict=True):
            require(block['mimeType'] == 'image/png', 'scheduled_witness_is_not_PNG')
            original = base64.b64decode(block['data'], validate=True)
            require(digest(original) == sha256 and len(original) == length and isinstance(ref, str) and ref,
                    'actual_image_bytes_and_frame_reference_differ')
            images.setdefault(ref, []).append({'attempt': attempt, 'MCP_content_block': index,
                'CLI_received_ns': contract['CLI_received_ns'], 'PNG_bytes': len(original),
                'PNG_sha256': sha256, 'frame_identity': frame_identity,
                'stdio_response_sha256': contract['RX_sha256']})
    return images


def pixels(frame, region, packet, arrays):
    import numpy as np

    names = frame['object_names']
    terminal_rows = {row['name']: row for row in packet['objects']}
    require(len(names) == len(terminal_rows) and set(names) == set(terminal_rows) and
            frame['display_object_mask'] == [terminal_rows[name]['visible_get'] for name in names],
            'frame_complete_display_domain_unbound')
    index = names.index(region['object_name'])
    counts = [len(terminal_rows[name]['evaluated']['triangles']) for name in names]
    source_offsets = [0, *[int(v) for v in np.cumsum(counts)]]
    require(source_offsets == frame['source_face_offsets'] and frame['object_ids'] ==
            [terminal_rows[name]['object_id'] for name in names] and frame['object_instance_ids'] ==
            [terminal_rows[name]['instance_id'] for name in names], 'source_triangle_frame_address_mismatch')
    wanted = [source_offsets[index] + i for i in region['source_triangle_indices']]
    owners, ids, color, depth = (arrays[key] for key in ('owners', 'triangle_ids', 'color', 'depth'))
    require(owners.shape == ids.shape == depth.shape == (512, 512) and color.shape[:2] == (512, 512),
            'frame_arrays_have_wrong_size')
    mask = (owners == index) & np.isin(ids, wanted)
    require(np.isfinite(depth[mask]).all(), 'target_owner_depth_not_finite')
    rgb = color[:, :, :3].astype(np.int32)
    boundary = np.zeros(mask.shape, dtype=bool)
    for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                 (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
        estimate = rgb[a] - rgb[b]
        boundary[a] |= mask[a] & ~mask[b] & (np.sum(estimate * estimate, axis=2) >= 24**2)
    points = [terminal_rows[names[index]]['evaluated']['vertices_world_m'][v] for v in region['vertex_indices']]
    return int(np.count_nonzero(mask)), int(np.count_nonzero(boundary)), points


def in_frame(pose, points, direction):
    import numpy as np

    view, proj = np.asarray(pose['view_matrix']), np.asarray(pose['projection_matrix'])
    direction = np.asarray(direction, dtype=float)
    expected_normal = direction / np.linalg.norm(direction)
    if pose['projection'] != 'orthographic' or not np.allclose(view[2, :3], expected_normal, atol=1e-8, rtol=0):
        return False
    original = np.asarray([[*x, 1.] for x in points])
    clip = original @ view.T @ proj.T
    return bool(np.isfinite(clip).all() and np.all(clip[:, 3] > 0) and
                np.all(np.abs(clip[:, :3] / clip[:, 3, None]) <= 1.0 + 1e-8))


def frame_checks(slot, packet, expected):
    import numpy as np
    from PIL import Image

    displayed = delivered_images(slot)
    ledger = read(slot / 'DEVICE_EVIDENCE.json')
    checked = {}
    for frame in ledger['frames']:
        ref = frame['ref']
        require(ref not in checked, 'frame_reference_repeated_in_ledger')
        occurrences = displayed.get(ref, [])
        if not occurrences:
            continue
        try:
            require(all(row['PNG_sha256'] == frame['PNG_sha256'] and
                        row['frame_identity'] in (None, frame['frame_identity']) for row in occurrences),
                    'delivered_reference_does_not_bind_this_frame')
            png = verified(frame['PNG'], frame['PNG_sha256'], slot)
            npz = verified(frame['NPZ'], frame['NPZ_sha256'], slot)
            with Image.open(io.BytesIO(png)) as image, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
                require(image.format == 'PNG' and image.size == (512, 512), 'original_PNG_format_or_dimensions')
                require(np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]),
                        'original_PNG_RGB_does_not_match_owners_archive')
                view = frame['view']
                witnesses = {}
                for region in expected['eligible']:
                    count, contrast, points = pixels(frame, region, packet, arrays)
                    qualifies = (view in region['eligible_complete_views'] and count >= 16 and contrast >= 4 and
                                 frame['direction_rational'] == expected['directions'][view] and
                                 in_frame(frame['pose'], points, expected['directions'][view]))
                    witnesses[region['object_name']] = {'qualifies': qualifies, 'surface_pixels': count,
                                                       'contrasting_boundary_pixels': contrast}
            checked[ref] = {'frame_identity': frame['frame_identity'], 'scope': frame['scope_id'], 'view': view,
                            'PNG_sha256': frame['PNG_sha256'], 'NPZ_sha256': frame['NPZ_sha256'],
                            'delivery': occurrences, 'witnesses': witnesses}
        except Exception as error:
            checked[ref] = {'error': str(error), 'delivery': occurrences}
    return checked


def evidence():
    expected = truth()
    permit, permit_sha, freeze_sha = admission(expected)
    result = {'admission_passed': permit['passed'], 'admission_sha256': permit_sha, 'freeze_sha256': freeze_sha,
              'previous_qualification_sha256': PREVIOUS_QUALIFICATION_SHA, 'independent_truth_sha256': TRUTH_SHA,
              'slots': []}
    if not permit['passed']:
        for label in SLOTS:
            require(not (RUNTIME / 'slots' / label / 'SLOT_STARTED.json').is_file(), 'formal_admission_despite_failed_gate')
            result['slots'].append({'slot': label, 'status': 'unrun', 'reason': 'derived_admission_failed'})
        return result
    seal_path = NS / 'ANSWERS_SEALED.json'
    seal = read(seal_path)
    require([r['slot'] for r in seal['answers']] == list(SLOTS), 'answer_original_denominator_changed')
    result['answers_sealed_sha256'] = digest(seal_path.read_bytes())
    binding_file = ROOT / 'verification/m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
    sys.path.insert(0, read(binding_file)['dependency_root'])
    for row in seal['answers']:
        slot = RUNTIME / 'slots' / row['slot']
        record = {'slot': row['slot'], 'status': row['status'], 'answer_sha256': row.get('sha256')}
        result['slots'].append(record)
        if not (slot / 'SLOT_STARTED.json').exists():
            require(row['status'] == 'unrun' and not row.get('path'), 'seal_claims_unstarted_slot_ran')
            continue
        started = read(slot / 'SLOT_STARTED.json')
        raw = (slot / 'SLOT_RESULT.json').read_bytes()
        outcome = json.loads(raw)
        publication = read(slot / 'SLOT_PUBLICATION.json')
        require(digest(raw) == publication['result_sha256'] == row['slot_result_sha256'] and
                publication['status'] == outcome['status'] == row['status'] and
                all(event['admission_sha256'] == permit_sha and event['freeze_sha256'] == freeze_sha
                    for event in (started, outcome)), 'sealed_slot_result_or_formal_admission_mismatch')
        record['slot_result_sha256'] = row['slot_result_sha256']
        if not row.get('path'):
            continue
        answer = verified(row['path'], row['sha256'], NS)
        require(len(answer) == row['bytes'], 'sealed_answer_length_changed')
        try:
            native, receipt = terminal(slot, outcome, expected['asset_sha256'])
            record.update(current_read_only=receipt, frames=frame_checks(slot, native, expected))
        except Exception as error:
            record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return result


def rounded(claim, value):
    decimal = Decimal(claim)
    require(decimal.is_finite(), 'nonfinite_graded_quantity')
    half_step = Fraction(10) ** decimal.as_tuple().exponent / 2
    return abs(Fraction(decimal) - Fraction(value)) <= max(Fraction(1, 10**6), half_step)


def grade(original, claims):
    current_truth = truth()
    expected = {r['object_name']: r for r in current_truth['eligible']}
    permit, permit_sha, freeze_sha = admission(current_truth)
    require(original['admission_passed'] is permit['passed'] and original['admission_sha256'] == permit_sha and
            original['freeze_sha256'] == freeze_sha, 'formal_grades_do_not_bind_admitted_pair')
    report = {'formal_denominator': 2, 'criteria_per_slot': len(GATES), 'admission_passed': permit['passed'],
              'admission_sha256': permit_sha, 'freeze_sha256': freeze_sha, 'slots': []}
    seals = read(NS / 'ANSWERS_SEALED.json')['answers'] if permit['passed'] else []
    if permit['passed']:
        require(digest((NS / 'ANSWERS_SEALED.json').read_bytes()) == original['answers_sealed_sha256'],
                'formal_evidence_answer_seal_changed')
    for source in original['slots']:
        label = source['slot']
        if not source.get('answer_sha256'):
            gates = {name: {'status': 'unrun', 'reason': source.get('reason', 'original_has_no_sealed_answer')} for name in GATES}
        else:
            annotation = claims[label]
            require(annotation['answer_sha256'] == source['answer_sha256'], 'graded_answer_changed')
            sealed = next(r for r in seals if r['slot'] == label)
            answer = verified(sealed['path'], sealed['sha256'], NS).decode('utf8')
            gates = annotation['gates']
            require(set(gates) == set(GATES), 'grading_criterion_set_changed')
            for key, row in gates.items():
                state = row['status']
                require(state in {'pass', 'fail', 'unverified'}, 'grade_status_invalid')
                if state != 'pass':
                    require(bool(row.get('reason')), 'negative_grade_requires_reason')
                    continue
                require(bool(row['quote']) and row['quote'] in answer, 'positive_grade_requires_verbatim_answer_quote')
                if key == 'roster':
                    require(sorted(row['objects']) == sorted(expected), 'claimed_region_set_differs')
                elif key.startswith('geometry_'):
                    expected_row = expected[key.split('_', 1)[1]]
                    require(row['triangles'] == expected_row['source_triangle_indices'] and
                            rounded(row['area_m2'], expected_row['area_m2']) and
                            all(rounded(a, b) for a, b in zip(row['center_world_m'], expected_row['center_world_m'], strict=True)) and
                            all(rounded(a, b) for a, b in zip(row['unit_normal'], expected_row['unit_normal'], strict=True)),
                            'claimed_geometry_differs_from_exact_current_truth')
                elif key.startswith('witness_'):
                    frame = source['frames'][row['resolved_delivered_ref']]
                    witness = frame['witnesses'][key.split('_', 1)[1]]
                    require(witness['qualifies'] and row['direction'] == frame['view'], 'cited_delivered_frame_does_not_qualify')
                elif key == 'read_only_current_identity':
                    require(bool(source.get('current_read_only')), 'current_read_only_source_not_verified')
        report['slots'].append({'slot': label, 'runtime_status': source['status'], 'answer_sha256': source.get('answer_sha256'),
             'passed': sum(row['status'] == 'pass' for row in gates.values()), 'denominator': len(GATES), 'criteria': gates})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims) if args.claims else {}))
