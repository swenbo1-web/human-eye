"""Score the assembly transfer against exact geometry and original live evidence."""

import argparse
from fractions import Fraction
import io
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m4_cross_scale_assembly_transfer_001')
FORMAL = V / 'm4_cross_scale_live_task_formal_001/scoring/formal.py'
ASSET = NS / 'fixture/ASSET_BINDING.json'
ASSET_RECORD_SHA = '232b9a7db673c5645b16fab31cf4dbeab6c766923e56fbb825530fed2110b3ff'
TRUTH = NS / 'fixture/CURRENT_TRUTH.json'
TRUTH_SHA = 'da4a27ac2cf278709a3f1a7de691af416fc2c1b21d2846a21a1d38732ddbbd71'
PRODUCT_BINDING = V / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
SLOTS = ('N1', 'P1')
GATES = ('roster', 'geometry_N10', 'geometry_N11', 'geometry_N22', 'witness_N22', 'outcome_N10',
         'finite_pool_unknown_N11', 'read_only_current_identity', 'no_contradictory_claim')
formal = runpy.run_path(str(FORMAL))
digest, read, require, verified, write = (formal[key] for key in ('digest', 'read', 'require', 'verified', 'write'))


def bound_terminal(slot, result, asset_sha):
    """Re-check the fresh owned worker, then compare its arrays to the archived assembly."""
    slot = Path(slot)
    asset = read(ASSET)
    require(digest(ASSET.read_bytes()) == ASSET_RECORD_SHA and asset['asset_sha256'] == asset_sha,
            'fixed_assembly_asset_binding_changed')
    original = Path(asset['asset_path']).resolve()
    deadline = result['owned_deadline_ns']
    startup, ready, closed = formal['generic_process'](slot, original, (slot / 'native/input.blend').resolve(),
                                                       asset_sha, deadline)
    pid = startup['pid']
    begin, end = result['initial_source'], result['terminal_source']
    first = formal['read_capture'](slot, slot / 'initial_capture/TERMINAL_SOURCE.json', begin, pid, asset_sha)
    last = formal['read_capture'](slot, slot / 'TERMINAL_SOURCE.json', end, pid, asset_sha)
    require(startup['created_after_ns'] <= first['started_ns'] <= begin['worker']['file_closed_ns'] <=
            result['ready_ns'] <= result['cleanup_started_ns'] <= last['started_ns'] <=
            end['worker']['file_closed_ns'] <= closed['closed_ns'] <= deadline,
            'current_assembly_read_does_not_bracket_task')
    for key in ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'display_scope',
                'display_read', 'layer_collections', 'scene_cameras'):
        require(first.get(key) == last.get(key), 'current_assembly_changed_before_readback/' + key)
    archived = asset['archived_terminal']
    previous_path = Path(archived['path'])
    raw = verified(previous_path, archived['sha256'], original.parents[1])
    require(len(raw) == archived['bytes'], 'original_assembly_terminal_changed')
    previous = json.loads(raw)
    require(len(last['objects']) == len(previous['objects']) == asset['counts']['objects'] and
            last['source']['view_layer'] == previous['source']['view_layer'] and
            last['source']['unit_settings'] == previous['source']['unit_settings'] and
            last['source']['scene'] == previous['source']['scene'] and
            all(last[field] == previous[field] for field in ('source_face_offsets', 'display_object_mask',
                                                             'display_scope', 'display_read')),
            'archived_assembly_scope_or_ordered_offsets_differ')
    object_fields = ('name', 'mesh_name', 'parent', 'native_matrix_world', 'matrix_world', 'modifiers',
                     'display', 'visible_get', 'evaluated', 'native')
    for old, new in zip(previous['objects'], last['objects'], strict=True):
        require(all(old[key] == new[key] for key in object_fields),
                'saved_assembly_current_ordered_geometry_or_visibility_differs/' + old['name'])
    return last, {'source_ref': end['source_ref'], 'sha256': end['sha256'],
                  'verified_object_count': len(last['objects']), 'asset_copy': str(slot / 'native/input.blend'),
                  'initial_capture_sha256': begin['sha256'], 'fixture_readback_sha256': archived['sha256'],
                  'unchanged_geometry_fingerprint': ready['initial_fingerprint']}


def inspect_frame(slot, frame, packet, expected):
    """Recompute a native frame's pixel witnesses even when its image was not attached."""
    import numpy as np
    from PIL import Image

    png = verified(frame['PNG'], frame['PNG_sha256'], slot)
    npz = verified(frame['NPZ'], frame['NPZ_sha256'], slot)
    view = frame['view']
    require(view in expected['directions'] and frame['direction_rational'] == expected['directions'][view],
            'native_frame_direction_mismatch')
    with Image.open(io.BytesIO(png)) as image, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
        require(image.format == 'PNG' and image.size == (512, 512) and
                np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]),
                'native_PNG_differs_from_its_source_arrays')
        witnesses = {}
        for region in expected['eligible']:
            count, contrast, points = formal['pixels'](frame, region, packet, arrays)
            fitted = formal['in_frame'](frame['pose'], points, expected['directions'][view])
            clear = fitted and view in region['eligible_complete_views']
            witnesses[region['object_name']] = {'surface_pixels': count, 'contrasting_boundary_pixels': contrast,
                                                'in_frame': fitted, 'geometrically_clear': clear,
                                                'qualifies': clear and count >= 16 and contrast >= 4}
    return {'view': view, 'frame_identity': frame['frame_identity'], 'PNG_sha256': frame['PNG_sha256'],
            'NPZ_sha256': frame['NPZ_sha256'], 'witnesses': witnesses}


def actual_probes(slot, packet, expected):
    """Check all actual TOP frames, including unselected product constructions."""
    import numpy as np

    ledger_path = slot / 'DEVICE_EVIDENCE.json'
    native = {}
    for frame in read(ledger_path)['frames'] if ledger_path.exists() else []:
        if frame['view'] == 'TOP':
            native[frame['ref']] = inspect_frame(slot, frame, packet, expected)

    contracts = {row['attempt']: row for row in read(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']}
    original = {}
    wire_root = slot / 'consumer/attachments'
    for path in wire_root.glob('bridge_*/*/RX.bin'):
        monitor = read(path.with_name('RECEIPT.json'))
        number = monitor.get('attempt')
        if number not in contracts:
            continue
        row = contracts[number]
        producer_receipt = slot / 'owner' / f'tool_{number:02d}/PRODUCT_RECEIPT.json'
        if not producer_receipt.is_file() or not row.get('matched') or row.get('reason') != 'content_and_envelope_match':
            continue
        producer = read(producer_receipt).get('producer_archive')
        if producer is None:
            continue
        reply = json.loads(verified(path, row['RX_sha256'], wire_root))
        owner = producer_receipt.parent
        require(reply == read(owner / 'RESPONSE.json') and reply['result'] == read(owner / 'PRODUCT_RESPONSE.json')['result'],
                'actual_probe_not_bound_to_original_consumer_and_installed_response')
        if reply['result']['isError']:
            continue
        full = json.loads(verified(producer['path'], producer['sha256'], slot))
        scopes = {item['scope_id']: item['binding'] for item in full.get('scopes', [])}
        for frame in full.get('constructed_frames', []):
            if frame['view_name'] != 'TOP':
                continue
            binding = scopes.get(frame['scope_id'], full['binding'])
            require(frame['host_binding_sha256'] == binding['binding_sha256'] and
                    frame['camera_identity'] == binding['camera_identity'] and
                    frame['source_revision'] == binding['scene_revision'] and
                    frame['scene_identity'] == binding['geometry_identity'],
                    'product_probe_generation_or_scope_changed')
            data = verified(frame['arrays_path'], frame['arrays_sha256'], slot)
            objects = binding['objects']
            with np.load(io.BytesIO(data), allow_pickle=False) as arrays:
                offsets = arrays['face_patch_offsets'].tolist()
                mask = arrays['display_object_mask'].tolist() if 'display_object_mask' in arrays else [True] * len(objects)
            product_frame = {'view': frame['view_name'], 'direction_rational': frame['pose']['direction_rational'],
                             'pose': frame['pose'], 'frame_identity': frame['frame_identity'],
                             'PNG': frame['image_path'], 'PNG_sha256': frame['image_sha256'],
                             'NPZ': frame['arrays_path'], 'NPZ_sha256': frame['arrays_sha256'],
                             'object_names': [obj['object_name'] for obj in objects],
                             'object_ids': [obj['host_id'] for obj in objects],
                             'object_instance_ids': [obj['instance_id'] for obj in objects],
                             'source_face_offsets': offsets, 'display_object_mask': mask}
            ref = frame['image_ref']
            checked = inspect_frame(slot, product_frame, packet, expected)
            entry = original.setdefault(ref, {'independent': checked, 'delivery_attempts': []})
            require(entry['independent'] == checked, 'actual_probe_ref_reused_for_different_image')
            entry['delivery_attempts'].append(number)
    return {'native': native, 'product': original}


def frozen_truth():
    path = NS / 'FROZEN.json'
    freeze = read(path)
    pins = {Path(row['path']).resolve(): row for row in freeze['direct_inputs']}
    for source in (Path(__file__), FORMAL, ASSET, TRUTH):
        raw = source.read_bytes()
        row = pins.get(source.resolve(), {})
        require(row.get('bytes') == len(raw) and row.get('sha256') == digest(raw),
                'unbound_formal_scoring_input/' + source.name)
    truth = read(TRUTH)
    require(digest(TRUTH.read_bytes()) == TRUTH_SHA and truth['current_blender_evaluated_readback'] is True,
            'frozen_exact_assembly_truth_changed')
    return truth, digest(path.read_bytes())


def evidence():
    truth, freeze_sha = frozen_truth()
    qualification_path = NS / 'QUALIFICATION.json'
    gate = read(qualification_path)
    qualification_sha = digest(qualification_path.read_bytes())
    require(type(gate['passed']) is bool and gate['freeze_sha256'] == freeze_sha and
            [row['label'] for row in gate['slots']] == ['QN', 'QP'], 'qualification_does_not_bind_this_batch')
    if gate['passed']:
        for row in gate['slots']:
            owned = RUN / 'slots' / row['label']
            raw = verified(owned / 'SLOT_RESULT.json', row['result_sha256'], owned)
            proof = read(owned / 'SLOT_PUBLICATION.json')
            require(json.loads(raw)['freeze_sha256'] == freeze_sha and
                    proof['result_sha256'] == row['result_sha256'] and proof['status'] == 'completed',
                    'qualification_receipt_detached_from_original_owned_slot')
    sys.path.insert(0, read(PRODUCT_BINDING)['dependency_root'])
    result = {'admission_passed': gate['passed'], 'freeze_sha256': freeze_sha,
              'qualification_sha256': qualification_sha, 'independent_truth_sha256': TRUTH_SHA,
              'formal_denominator': 2, 'slots': []}
    if not gate['passed']:
        for label in SLOTS:
            require(not (RUN / 'slots' / label / 'SLOT_STARTED.json').exists(), 'formal_slot_started_after_failed_qualification')
            result['slots'].append({'slot': label, 'status': 'unrun', 'reason': 'qualification_failed'})
        return result
    seal_path = NS / 'ANSWERS_SEALED.json'
    seals = read(seal_path)['answers']
    require([row['slot'] for row in seals] == list(SLOTS), 'original_answer_denominator_changed')
    result['answers_sealed_sha256'] = digest(seal_path.read_bytes())
    for row in seals:
        label = row['slot']
        slot = RUN / 'slots' / label
        record = {'slot': label, 'status': row['status'], 'answer_sha256': row.get('sha256')}
        result['slots'].append(record)
        if not (slot / 'SLOT_STARTED.json').exists():
            require(row['status'] == 'unrun' and not row.get('path'), 'sealed_unstarted_slot_claimed_run')
            continue
        result_path = slot / 'SLOT_RESULT.json'
        started, outcome, publication = (read(path) for path in
                                         (slot / 'SLOT_STARTED.json', result_path, slot / 'SLOT_PUBLICATION.json'))
        require(all(event['label'] == label for event in (started, outcome, publication)) and
                publication['status'] == outcome['status'] == row['status'] and
                publication['published_ns'] == row['published_ns'] and
                publication['result_sha256'] == digest(result_path.read_bytes()) == row['slot_result_sha256'] and
                all(event['freeze_sha256'] == freeze_sha and event['qualification_sha256'] == qualification_sha
                    and event['asset_sha256'] == truth['asset_sha256'] for event in (started, outcome)),
                'formal_slot_seal_or_qualification_mismatch')
        record['slot_result_sha256'] = row['slot_result_sha256']
        if row.get('path'):
            answer = verified(row['path'], row['sha256'], NS)
            native_answer = verified(slot / 'consumer/PUBLIC_FINAL.txt', row['sha256'], slot)
            require(answer == native_answer and len(answer) == row['bytes'], 'original_answer_has_changed')
            try:
                packet, current = bound_terminal(slot, outcome, truth['asset_sha256'])
                record['current_read_only'] = current
                record['frames'] = formal['frame_checks'](slot, packet, truth)
                record['TOP_probes'] = actual_probes(slot, packet, truth)
            except Exception as error:
                record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return result


def witness(source, region, claim):
    frame = source['frames'][claim['resolved_delivered_ref']]
    measured = frame['witnesses'][region]
    require(frame['view'] == claim['direction'] and measured['qualifies'], 'cited_delivered_original_does_not_qualify')
    for key in ('surface_pixels', 'contrasting_boundary_pixels'):
        require(key not in claim or claim[key] == measured[key], 'incorrect_frame_measurement/' + key)


def grade_pass(key, claim, truth, source):
    rounded = formal['rounded']
    if key == 'roster':
        require(sorted(claim['objects']) == sorted(truth), 'wrong_exact_region_roster')
    elif key.startswith('geometry_'):
        expected = truth[key.split('_', 1)[1]]
        require(claim['triangles'] == expected['source_triangle_indices'] and
                Fraction(claim['area_m2']) > 0 and rounded(claim['area_m2'], expected['area_m2']) and
                all(rounded(a, b) for a, b in zip(claim['center_world_m'], expected['center_world_m'], strict=True)) and
                all(rounded(a, b) for a, b in zip(claim['unit_normal'], expected['unit_normal'], strict=True)),
                'wrong_current_triangle_indices_or_geometry/' + key)
    elif key == 'witness_N22':
        witness(source, 'N22', claim)
    elif key == 'outcome_N10':
        require(claim['direction'] == 'TOP', 'N10_other_direction_falsely_claimed_complete')
        if claim['outcome'] == 'complete':
            witness(source, 'N10', claim)
        else:
            require(claim['outcome'] == 'contrast_insufficient', 'N10_requires_actual_contrast_shortfall')
            require(not any(frame.get('witnesses', {}).get('N10', {}).get('qualifies')
                            for frame in source['frames'].values()), 'N10_ignored_a_qualifying_delivered_witness')
            actual = source['TOP_probes']
            candidates = {**actual['native'], **{ref: entry['independent'] for ref, entry in actual['product'].items()}}
            ref = claim.get('resolved_measured_ref')
            if ref is not None:
                candidates = {ref: candidates[ref]}
            wanted = [f['witnesses']['N10'] for f in candidates.values() if f['view'] == 'TOP']
            require(any(row['geometrically_clear'] and row['surface_pixels'] >= 16 and
                        row['contrasting_boundary_pixels'] < 4 and
                        all(name not in claim or row[name] == claim[name] for name in
                            ('surface_pixels', 'contrasting_boundary_pixels')) for row in wanted),
                    'N10_reported_contrast_failure_is_unmeasured')
    elif key == 'finite_pool_unknown_N11':
        expected = truth['N11']['finite_direction_proofs']
        require(claim['reason_kind'] == 'positive_area_occlusion_all_front_views' and
                len(expected) == 6 and all(Fraction(row['union_blocked_area_fraction']) > 0 for row in expected.values()) and
                not claim.get('claims_all_hidden'), 'N11_needs_positive_area_with_incomplete_witness_only')
        blockers = claim.get('blockers_by_direction', {})
        if claim.get('blocker'):
            blockers = {name: [claim['blocker'], *blockers.get(name, [])] for name in expected}
        require(set(blockers) <= set(expected) and all(isinstance(names, list) and names and
                set(names) <= {row['object_name'] for row in expected[direction]['positive_area_occluders']}
                for direction, names in blockers.items()), 'N11_named_occluder_not_independently_established')
    elif key == 'read_only_current_identity':
        require(bool(source.get('current_read_only')), 'current_assembly_and_closure_not_verified')


def grade(sealed, claims):
    require(sealed == evidence(), 'scoring_evidence_does_not_match_originals')
    truth = {row['object_name']: row for row in read(TRUTH)['eligible']}
    labels = {row['slot'] for row in sealed['slots'] if row.get('answer_sha256')}
    require(set(claims) == labels, 'claims_must_match_original_answers')
    results = []
    for source in sealed['slots']:
        label = source['slot']
        answer_sha = source.get('answer_sha256')
        if answer_sha is None:
            gates = {key: {'status': 'unrun', 'reason': source.get('reason', 'original_has_no_sealed_answer')} for key in GATES}
        else:
            record = claims[label]
            require(record['answer_sha256'] == answer_sha and set(record['gates']) == set(GATES),
                    'claim_does_not_bind_answer_and_exact_rubric')
            answer = verified(NS / f'answers/{label}.txt', answer_sha, NS).decode('utf8')
            gates = record['gates']
            for key, claim in gates.items():
                status = claim['status']
                require(status in ('pass', 'fail', 'unverified'), 'invalid_criterion_status')
                if status == 'pass':
                    require(bool(claim['quote']) and claim['quote'] in answer, 'missing_verbatim_evidence/' + key)
                    grade_pass(key, claim, truth, source)
                else:
                    require(bool(claim.get('reason')), 'unexplained_failed_or_unknown_criterion/' + key)
        results.append({'slot': label, 'runtime_status': source['status'], 'answer_sha256': answer_sha,
                        'passed': sum(row['status'] == 'pass' for row in gates.values()),
                        'denominator': len(GATES), 'criteria': gates})
    return {'freeze_sha256': sealed['freeze_sha256'], 'qualification_sha256': sealed['qualification_sha256'],
            'admission_passed': sealed['admission_passed'], 'formal_denominator': 2, 'criteria_per_slot': len(GATES),
            'formal_evidence_sha256': digest((HERE / 'FORMAL_EVIDENCE.json').read_bytes()), 'slots': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims) if args.claims else {}))
