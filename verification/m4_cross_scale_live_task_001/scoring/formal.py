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
RUNTIME = Path('D:/he_m4_cross_scale_live_task_001')
SLOTS = ('N1', 'P1')
GATES = ('roster', 'geometry_M02', 'geometry_M06', 'geometry_M09', 'witness_M02', 'witness_M09',
         'finite_pool_unknown_M06', 'read_only_current_identity', 'no_contradictory_claim')
TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
ASSET = HERE.parent / 'fixture/ASSET_BINDING.json'


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


def terminal(slot, result, asset_sha):
    receipt = result.get('terminal_source') or {}
    require(receipt.get('status') == 'complete' and receipt['terminal'], 'no_bound_terminal_readback')
    packet = json.loads(verified(receipt['path'], receipt['sha256'], slot))
    source = packet['source']
    require(source['asset_sha256'] == asset_sha and source['frame'] == 1 and source['subframe'] == 0
            and source['scale_length'] == 1, 'terminal_asset_frame_or_units_mismatch')
    original = Path(source['asset_copy']).resolve()
    require(original.is_relative_to(slot.resolve()) and digest(original.read_bytes()) == asset_sha,
            'owned_copy_file_changed')
    expected = {m['name']: m for m in read(NS / 'fixture/GEOMETRY.json')['objects']}
    observed = {m['name']: m for m in packet['objects']}
    require(len(expected) == len(observed) == len(packet['objects']) and set(expected) == set(observed),
            'terminal_scene_roster_mismatch')
    for name, mesh in observed.items():
        ref = expected[name]
        require(mesh['matrix_world'] == mesh['native_matrix_world'] == ref['matrix_world'] and
                mesh['visible_get'] and mesh['native'] == mesh['evaluated'] and not mesh['modifiers'] and
                mesh['parent'] is None, 'terminal_display_or_transform_changed/' + name)
        evaluated = mesh['evaluated']
        require(evaluated['triangles'] == ref['triangles'] and evaluated['vertices_world_m'] ==
                [[float(Fraction(v)) for v in p] for p in ref['vertices_world_m']], 'ordered_mesh_mismatch/' + name)
    closure = read(slot / 'RUNTIME_CLOSE.json')
    guard = closure['Blender_status']['closed']
    require(not guard['poisoned'] and guard['display_restored'] and
            guard['initial_geometry_fingerprint'] == guard['final_geometry_fingerprint'] and
            closure['Blender_close']['protected_files_unchanged'], 'read_only_final_guard_failed')
    return packet, {'source_ref': receipt['source_ref'], 'sha256': receipt['sha256'],
                    'verified_object_count': len(observed), 'asset_copy': str(original),
                    'unchanged_geometry_fingerprint': guard['initial_geometry_fingerprint']}


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
        require(reply == read(slot / 'owner' / f'tool_{attempt:02d}' / 'RESPONSE.json'),
                'stdio_and_owner_response_differ')
        result = reply['result']
        if result['isError']:
            continue
        item_images = [(index, block) for index, block in enumerate(result['content']) if block['type'] == 'image']
        require(len(item_images) == contract['CLI_images'], 'CLI_image_count_does_not_match_original_stdio')
        for index, block in item_images:
            require(block['mimeType'] == 'image/png', 'scheduled_witness_is_not_PNG')
            original = base64.b64decode(block['data'], validate=True)
            images.setdefault(digest(original), []).append({'attempt': attempt, 'MCP_content_block': index,
                'CLI_received_ns': contract['CLI_received_ns'], 'PNG_bytes': len(original),
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
        occurrences = displayed.get(frame['PNG_sha256'], [])
        if not occurrences:
            continue
        try:
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
    qual = read(NS / 'QUALIFICATION.json')
    require(qual['formal_denominator'] == list(SLOTS), 'formal_denominator_changed')
    result = {'qualification_passed': qual['passed'], 'qualification_sha256': digest((NS / 'QUALIFICATION.json').read_bytes()),
              'independent_truth_sha256': TRUTH_SHA, 'slots': []}
    if not qual['passed']:
        for label in SLOTS:
            require(not (RUNTIME / 'slots' / label / 'SLOT_STARTED.json').is_file(), 'formal_admission_despite_failed_gate')
            result['slots'].append({'slot': label, 'status': 'unrun', 'reason': 'qualification_failed'})
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
        if not row.get('path'):
            continue
        answer = verified(row['path'], row['sha256'], NS)
        require(len(answer) == row['bytes'], 'sealed_answer_length_changed')
        raw = (slot / 'SLOT_RESULT.json').read_bytes()
        require(digest(raw) == read(slot / 'SLOT_PUBLICATION.json')['result_sha256'] == row['slot_result_sha256'],
                'sealed_slot_result_mismatch')
        try:
            native, receipt = terminal(slot, json.loads(raw), expected['asset_sha256'])
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
    expected = {r['object_name']: r for r in truth()['eligible']}
    report = {'formal_denominator': 2, 'criteria_per_slot': len(GATES), 'qualification_passed': original['qualification_passed'],
              'qualification_sha256': original['qualification_sha256'], 'slots': []}
    seals = read(NS / 'ANSWERS_SEALED.json')['answers'] if original['qualification_passed'] else []
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
