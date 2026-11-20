"""Score the dense Blender answers against source-bound original tool evidence."""

import argparse
import base64
from collections import Counter
from fractions import Fraction
import io
import json
from pathlib import Path
import re
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m4_dense_panel_sweep_formal_001')
DENSE = V / 'm4_dense_panel_sweep_001'
BRIEF = V / 'm4_dense_region_brief_001'
TRUTH = DENSE / 'truth/CURRENT_TRUTH.json'
BINDING = BRIEF / 'install/PRODUCT_RUN_BINDING.json'
FROZEN_TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
SLOTS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
CAPTION = re.compile(r'((?:active-host-image|native-image):[0-9a-f]{64}) \(512x512, image/png\)')

original = runpy.run_path(str(DENSE / 'checks/qualify_product.py'))
schema = runpy.run_path(str(BRIEF / 'checks/brief_schema.py'))
audit_source = runpy.run_path(str(V / 'm4_cross_scale_live_task_formal_001/checks/review_actual_tools.py'))
assembly = runpy.run_path(str(V / 'm4_cross_scale_assembly_transfer_001/checks/review_tools.py'))
digest, read, require, verified, write = (original[key] for key in (
    'digest', 'read', 'require', 'verified', 'write'))
capture_check = original['capture_check']


def dense_truth():
    value = json.loads(verified(TRUTH, FROZEN_TRUTH_SHA, DENSE))
    require(value['passed'] is True and value['counts'] == {'objects': 14, 'triangles': 6148, 'vertices': 3478}
            and len({region_key(row) for row in value['eligible']}) == len(value['eligible']) == 13,
            'independent_dense_truth_is_incomplete')
    return value


def region_key(row):
    return row['object_name'], tuple(row['source_triangle_indices'])


def region_label(key):
    return original['region_label'](key)


def full_or_brief(result):
    content = result['content']
    body = audit_source['facts_from_first'](content)
    if body.get('schema') == schema['V2']:
        body, images = schema['verify_brief'](result)
        return body, body['region_task']['rows'], {
            item['content_index']: item['ref'] for item, _ in images}
    task = body.get('facts', {}).get('region_task', {})
    frames = body.get('frames', [])
    selected = {}
    if type(frames) is list:
        originals = [frame for frame in frames if 'image_ref' in frame and 'image_sha256' in frame]
        content_images = [(i, digest(base64.b64decode(block['data'], validate=True)))
                          for i, block in enumerate(content) if block['type'] == 'image']
        if len(originals) == len(content_images):
            for frame, (index, checksum) in zip(originals, content_images, strict=True):
                if frame['image_sha256'] == checksum:
                    selected[index] = frame['image_ref']
    return body, task.get('rows', []), selected


def clip_fit(frame, points, direction):
    # Use the established orientation check and exact binary-value NDC planes.
    pose = frame['pose']
    if frame['direction_rational'] != direction or not original['FORMAL']['in_frame'](pose, points, direction):
        return False
    view, proj = (tuple(tuple(Fraction(x) for x in axis) for axis in pose[name])
                  for name in ('view_matrix', 'projection_matrix'))
    for point in points:
        world = (*map(Fraction, point), Fraction(1))
        viewed = tuple(sum(a*b for a, b in zip(axis, world, strict=True)) for axis in view)
        clip = tuple(sum(a*b for a, b in zip(axis, viewed, strict=True)) for axis in proj)
        if clip[3] <= 0 or any(abs(coord) > clip[3] for coord in clip[:3]):
            return False
    return True


def inspect_frame(slot, frame, packet, truth):
    import numpy as np
    from PIL import Image

    view = frame['view']
    require(view in truth['directions'] and frame['direction_rational'] == truth['directions'][view],
            'frame_not_in_frozen_camera_pool')
    png = verified(frame['PNG'], frame['PNG_sha256'], slot)
    npz = verified(frame['NPZ'], frame['NPZ_sha256'], slot)
    witnesses = {}
    with Image.open(io.BytesIO(png)) as image, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
        require(image.format == 'PNG' and image.size == (512, 512) and
                np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]),
                'frame_png_rgb_and_native_owner_array_do_not_match')
        for region in truth['eligible']:
            count, contrast, points = original['FORMAL']['pixels'](frame, region, packet, arrays)
            fitted = clip_fit(frame, points, truth['directions'][view])
            clear = fitted and view in region['eligible_complete_views']
            witnesses[region_label(region_key(region))] = {
                'surface_pixels': count, 'contrasting_boundary_pixels': contrast,
                'in_frame': fitted, 'geometrically_clear': clear,
                'qualifies': clear and count >= 16 and contrast >= 4,
            }
    return {'view': view, 'scope': frame['scope_id'], 'frame_identity': frame['frame_identity'],
            'origin': frame['origin'], 'PNG_sha256': frame['PNG_sha256'], 'NPZ_sha256': frame['NPZ_sha256'],
            'witnesses': witnesses, 'delivery': []}


def product_probe(frame, scopes, binding, slot):
    import numpy as np

    scope = scopes.get(frame['scope_id'], binding)
    require(frame['host_binding_sha256'] == scope['binding_sha256'] and
            frame['camera_identity'] == scope['camera_identity'] and
            frame['source_revision'] == scope['scene_revision'] and
            frame['scene_identity'] == scope['geometry_identity'], 'product_frame_scope_or_generation_changed')
    objects = scope['objects']
    arrays = verified(frame['arrays_path'], frame['arrays_sha256'], slot)
    with np.load(io.BytesIO(arrays), allow_pickle=False) as archive:
        offsets = archive['face_patch_offsets'].tolist()
        mask = (archive['display_object_mask'].tolist() if 'display_object_mask' in archive
                else [True] * len(objects))
    return {'ref': frame['image_ref'], 'view': frame['view_name'], 'scope_id': frame['scope_id'],
            'direction_rational': frame['pose']['direction_rational'], 'pose': frame['pose'],
            'origin': 'product', 'frame_identity': frame['frame_identity'],
            'PNG': frame['image_path'], 'PNG_sha256': frame['image_sha256'],
            'NPZ': frame['arrays_path'], 'NPZ_sha256': frame['arrays_sha256'],
            'object_names': [obj['object_name'] for obj in objects],
            'object_ids': [obj['host_id'] for obj in objects],
            'object_instance_ids': [obj['instance_id'] for obj in objects],
            'source_face_offsets': offsets, 'display_object_mask': mask}


def validated_rows(slot, installed, packet, truth_by_key, body, rows, producer, captures):
    if not rows:
        return []
    binding, support = producer['binding'], producer['facts']['region_task']
    source_audit = capture_check['Audit']()
    capture = capture_check['current_capture'](captures, binding, source_audit)
    capture_check['source_binding_checks'](capture, binding, installed, source_audit)
    terminal = {row['name']: row for row in packet['objects']}
    require({mesh['name'] for mesh in capture['meshes']} == terminal.keys() and
            len(capture['meshes']) == len(terminal), 'ordinary_and_product_scene_roster_differ')
    for mesh in capture['meshes']:
        native = terminal[mesh['name']]
        require(mesh['object_id'] == native['object_id'] and
                capture['host_identity']['object_instances'][mesh['object_id']] == native['instance_id'] and
                mesh['faces'] == native['evaluated']['triangles'] and
                mesh['vertices'] == native['evaluated']['vertices_world_m'], 'product_not_bound_to_current_ordinary_source')
    keys = [region_key(row) for row in rows]
    require(keys == [region_key(row) for row in support['rows']] and len(set(keys)) == len(keys),
            'product_region_binding_or_order_changed')
    require(body['binding']['binding_sha256'] == binding['binding_sha256'] and
            body['binding']['source_binding_sha256'] == binding['source_binding_sha256'],
            'public_product_parent_binding_changed')
    result = []
    for row, same in zip(rows, support['rows'], strict=True):
        key = region_key(row)
        if key not in truth_by_key:
            continue
        baseline = truth_by_key[key]
        require(row['source'] == same['source'] == capture_check['source_row'](baseline, capture, binding) and
                all(row[field] == same[field] for field in ('center_world_m', 'status', 'reason', 'view_reasons', 'roi_id')),
                'product_row_not_bound_to_current_source_and_facts')
        original['prior']['same_geometry'](row, baseline, terminal[key[0]], binding)
        result.append({'region': region_label(key), 'object_name': row['object_name'],
                       'source_triangle_indices': row['source_triangle_indices'],
                       'roi_id': row['roi_id'], 'center_world_m': row['center_world_m'],
                       'status': row['status'], 'reason': row['reason'], 'view_reasons': row['view_reasons']})
    return result


def audit_slot(slot, seal, packet, truth, installed, *, evidence_root=NS):
    prev = audit_source['audit_slot']
    prev.__globals__.update(NS=evidence_root, RUNTIME=slot.parent.parent,
                            product_evidence=assembly['product_binder'](audit_source))
    ledger, _ = prev(seal)
    truth_by_key = {region_key(row): row for row in truth['eligible']}
    device = read(slot / 'DEVICE_EVIDENCE.json')
    raw_frames = {row['ref']: row for row in device['frames']}
    require(len(raw_frames) == len(device['frames']), 'duplicate_device_frame_ref')
    checked = {}

    def bind_frame(ref, frame):
        if ref not in checked:
            try:
                checked[ref] = inspect_frame(slot, frame, packet, truth)
            except Exception as error:
                checked[ref] = {'frame_identity': frame['frame_identity'], 'error': str(error), 'delivery': []}
        require(checked[ref]['frame_identity'] == frame['frame_identity'], 'frame_ref_changed_actual_frame')
        return checked[ref]

    for ref, frame in raw_frames.items():
        bind_frame(ref, frame)
    captures = None
    helpers, limits = original['POLICY']['budget_helpers']()
    for attempt in ledger['attempts']:
        attempt['regions'] = []
        attempt['requested_detail'] = read(attempt['TX']['path'])['params']['arguments'].get('response_detail')
        attempt['images'] = []
        if attempt['is_error'] or attempt['CLI_match'] != 'content_and_envelope_match':
            continue
        try:
            wire = json.loads(verified(attempt['RX']['path'], attempt['RX']['sha256'], slot))['result']
            content = wire['content']
            body, rows, picked = full_or_brief(wire)
            delivery = attempt['product']
            model_items = helpers['model_items'](wire, '100.0000')
            first = helpers['truncate_items'](model_items, limits['MCP_bytes'])
            second = helpers['truncate_items'](first, limits['history_approximate_tokens'], token_mode=True)
            attempt['fixed_CLI_whole_content'] = model_items == first == second
            attempt['fixed_CLI_text'] = [item['text'] for item in second[1:] if item['type'] == 'input_text']
            if delivery and delivery['producer_delivery']:
                archive = delivery['producer_delivery']['path']
                producer = json.loads(verified(archive['path'], archive['sha256'], slot))
                scopes = {scope['scope_id']: scope['binding'] for scope in producer.get('scopes', [])}
                for frame in producer.get('constructed_frames', []):
                    ref = frame['image_ref']
                    if ref not in raw_frames and ref not in checked:
                        bind_frame(ref, product_probe(frame, scopes, producer['binding'], slot))
                if rows and captures is None:
                    captures, _ = capture_check['decode_captures'](slot, installed, capture_check['Audit']())
                attempt['regions'] = validated_rows(slot, installed, packet, truth_by_key, body, rows, producer, captures)
            receipt = (slot / 'owner' / f"tool_{attempt['attempt']:02d}" / 'RECEIPT.json')
            attachments = read(receipt).get('image_attachments', []) if receipt.is_file() else []
            for image in attempt['image_blocks']:
                block = image['content_index']
                ref = picked.get(block)
                if ref is None and block and content[block-1]['type'] == 'text':
                    match = CAPTION.fullmatch(content[block-1]['text'])
                    if match:
                        ref = match[1]
                if ref is None and not delivery:
                    refs = {row['ref'] for row in attachments if row['PNG_sha256'] == image['sha256']
                            and row['delivery_ready'] is True}
                    if len(refs) == 1:
                        ref, = refs
                if not ref:
                    continue
                bound = checked.get(ref)
                require(bound is not None and (bound.get('error') or bound['PNG_sha256'] == image['sha256']),
                        'raw_tool_image_missing_same_slot_reference')
                occurrence = {'attempt': attempt['attempt'], 'MCP_content_block': block,
                              'PNG_sha256': image['sha256'], 'origin': 'product' if delivery else 'ordinary'}
                bound['delivery'].append(occurrence)
                attempt['images'].append({'ref': ref, **occurrence})
        except Exception as error:
            attempt['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return checked, ledger


def evidence():
    truth = dense_truth()
    freeze_path = NS / 'FROZEN.json'
    freeze = digest(freeze_path.read_bytes())
    sealed = read(freeze_path)
    pins = {Path(row['path']).resolve(): row['sha256'] for row in sealed['direct_inputs']}
    for path in (HERE / 'score.py', HERE / 'RUBRIC.md', TRUTH, BINDING):
        require(pins.get(path.resolve()) == digest(path.read_bytes()), 'unfrozen_formal_scoring_input/' + path.name)
    qualification_path = NS / 'QUALIFICATION.json'
    qualification = read(qualification_path)
    qualified = qualification['passed'] is True
    require(qualification['freeze_sha256'] == freeze and
            [row['label'] for row in qualification['slots']] == ['QN', 'QP'] and
            qualification['external_QP_reused'] is True, 'formal_qualification_contract_changed')
    gate = digest(qualification_path.read_bytes())
    seals = read(NS / 'ANSWERS_SEALED.json')['answers']
    require(tuple(row['slot'] for row in seals) == SLOTS, 'sealed_formal_denominator_changed')
    installed = read(BINDING)
    sys.path.insert(0, installed['dependency_root'])
    records = []
    for seal in seals:
        label = seal['slot']
        slot = RUN / 'slots' / label
        record = {'slot': label, 'status': seal['status'], 'answer_sha256': seal['sha256']}
        records.append(record)
        if seal['status'] == 'unrun':
            require(not slot.exists() and seal['path'] is None, 'unrun_slot_has_actual_original/' + label)
            continue
        require(qualified, 'formal_slot_has_run_despite_qualification_gate')
        try:
            outcome_path = slot / 'SLOT_RESULT.json'
            outcome, publication = (read(path) for path in (outcome_path, slot / 'SLOT_PUBLICATION.json'))
            require(outcome['label'] == publication['label'] == label and
                    publication['result_sha256'] == seal['slot_result_sha256'] == digest(outcome_path.read_bytes()) and
                    publication['published_ns'] == seal['published_ns'] and publication['status'] == seal['status'] and
                    outcome['freeze_sha256'] == freeze and outcome['qualification_sha256'] == gate and
                    outcome['asset_sha256'] == truth['asset_sha256'] and outcome['group'] == label[0] and
                    outcome['phase'] == 'formal' and outcome['paid_API_calls'] == 0,
                    'sealed_answer_is_not_current_slot_publication')
            if seal['path'] is None:
                continue
            packet, read_only = original['current_source'](slot, outcome)
            record['current_read_only'] = read_only
            record['frames'], record['tools'] = audit_slot(slot, seal, packet, truth, installed)
            attempts = [row['attempt'] for row in record['tools']['attempts']]
            require(attempts == list(range(1, len(attempts) + 1)), 'formal_attempt_sequence_has_gaps')
        except (KeyError, OSError, TypeError, ValueError) as error:
            record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return {'schema': 'm4-dense-panel-formal-evidence-v1', 'freeze_sha256': freeze,
            'qualification_sha256': gate, 'qualification_passed': qualified,
            'answers_sealed_sha256': digest((NS / 'ANSWERS_SEALED.json').read_bytes()),
            'independent_truth_sha256': FROZEN_TRUTH_SHA, 'formal_denominator': len(SLOTS), 'slots': records}


def quoted(answer, phrase):
    require(type(phrase) is str and bool(phrase.strip()) and phrase in answer, 'missing_verbatim_answer_quote')


def parse_source(claim, region_attempts, size_by_object):
    name = claim['object_name']
    size = size_by_object.get(name, 0)
    choices = {'source_triangle_index_ranges', 'source_triangle_indices', 'source_roi_id'} & claim.keys()
    require(len(choices) == 1, 'one_actual_source_expression_required')
    if 'source_roi_id' in claim:
        groups = {tuple(item['source_triangle_indices']) for item in region_attempts
                  if item['object_name'] == name and item['roi_id'] == claim['source_roi_id']}
        require(len(groups) == 1, 'source_ref_not_resolvable_under_same_object_and_actual_tool_output')
        indices, = groups
    elif 'source_triangle_indices' in claim:
        indices = claim['source_triangle_indices']
    else:
        indices = []
        for first, last in claim['source_triangle_index_ranges']:
            require(type(first) is int and type(last) is int and 0 <= first <= last < size,
                    'bad_zero_based_inclusive_source_range')
            indices.extend(range(first, last + 1))
    require(indices and all(type(index) is int and 0 <= index < size for index in indices) and
            len(set(indices)) == len(indices), 'source_triangle_indices_outside_current_or_repeated')
    return name, tuple(sorted(indices))


def close_number(a, b):
    return type(a) in (int, float, str) and abs(Fraction(str(a)) - Fraction(str(b))) <= Fraction(1, 10**6)


def measured_outcome(region, reference, claim, frames):
    kind, direction = claim['kind'], claim.get('direction')
    if kind == 'geometric_occlusion':
        proofs = region['finite_direction_proofs']
        blocked = {name for name, proof in proofs.items() if proof['status'] == 'positive_area_occlusion'}
        facing = {name for name, proof in proofs.items() if Fraction(proof['normal_dot_direction']) > 0}
        named = {name: set(names) for name, names in claim.get('blockers_by_direction', {}).items()}
        require(not region['eligible_complete_views'] and facing == blocked and blocked and
                (direction is None or direction in blocked) and
                (not claim.get('directions') or set(claim['directions']) == blocked) and
                not claim.get('claims_all_pixels_hidden') and set(named) <= blocked and
                all(names <= {item['object_name'] for item in proofs[name]['positive_area_occluders']}
                    for name, names in named.items()), 'geometric_occlusion_not_supported')
        return []
    probes = {ref: frame for ref, frame in frames.items() if 'witnesses' in frame}
    if kind == 'witness':
        ref = claim['ref']
        frame = probes[ref]
        pixel = frame['witnesses'][reference]
        require(direction == frame['view'] and pixel['qualifies'] and frame['delivery'],
                'cited_same_slot_image_is_not_a_complete_delivered_witness')
        require(all(key not in claim or claim[key] == pixel[key]
                    for key in ('surface_pixels', 'contrasting_boundary_pixels')),
                'reported_witness_pixels_differ')
        return frame['delivery']
    require(kind == 'pixel_shortfall' and direction in region['eligible_complete_views'] and
            not any(frame['delivery'] and frame['witnesses'][reference]['qualifies'] for frame in probes.values()),
            'pixel_shortfall_conflates_geometry_or_ignores_existing_delivery')
    if claim.get('ref'):
        probes = {claim['ref']: probes[claim['ref']]}
    fields = ('surface_pixels', 'contrasting_boundary_pixels')
    require(any(key in claim for key in fields), 'pixel_shortfall_requires_specific_measured_evidence')
    require(any(frame['view'] == direction and pixel['geometrically_clear'] and not pixel['qualifies'] and
                all(key not in claim or claim[key] == pixel[key] for key in fields)
                for frame in probes.values() for pixel in (frame['witnesses'][reference],)),
            'reported_pixel_shortfall_not_measured_for_region_and_view')
    return []


def grade_slot(record, claim, answer, truth, sizes):
    require(claim['answer_sha256'] == record['answer_sha256'] == digest(answer.encode()),
            'manual_transcription_not_bound_to_original_reply')
    targets = {region_key(row): row for row in truth['eligible']}
    attempts = {call['attempt']: call for call in record.get('tools', {}).get('attempts', [])}
    routes = [row for attempt in attempts.values() if attempt.get('fixed_CLI_whole_content') and
              not attempt.get('evidence_error') for row in attempt['regions']]
    rows, seen, adopted = [], Counter(), set()
    for row in claim['rows']:
        checked = {'object_name': row['object_name'], 'geometry_passed': False, 'evidence_passed': False}
        rows.append(checked)
        try:
            quoted(answer, row['quote'])
            key = parse_source(row, routes, sizes)
            name = region_label(key)
            checked['region'] = name
            seen[key] += 1
            target = targets[key]
            require(all(close_number(a, b) for a, b in zip(row['center_world_m'], target['center_world_m'], strict=True)),
                    'center_outside_fixed_world_tolerance')
            checked['geometry_passed'] = True
            outcome = row['outcome']
            quoted(answer, outcome['quote'])
            occurrence = measured_outcome(target, name, outcome, record.get('frames', {}))
            if outcome['kind'] == 'witness':
                quoted(answer, outcome['ref'])
            checked['evidence_passed'] = True
            for proof in occurrence:
                attempt = attempts[proof['attempt']]
                if proof['origin'] == 'product' and not attempt.get('evidence_error') and any(
                        candidate['region'] == name for candidate in attempt['regions']):
                    adopted.add(proof['attempt'])
            if 'adoption' in row:
                attribution = row['adoption']
                quoted(answer, attribution['answer_quote'])
                attempt = attempts[attribution['attempt']]
                anchor = attribution['response_quote']
                require(bool(anchor) and any(anchor in text for text in attempt.get('fixed_CLI_text', [])) and
                        not attempt.get('evidence_error') and any(item['region'] == name for item in attempt['regions']),
                        'explicit_product_adoption_quote_or_current_region_missing')
                adopted.add(attribution['attempt'])
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            checked['issue'] = str(error)
    contradictions = claim['extra_assertions']
    for issue in contradictions:
        quoted(answer, issue['quote'])
        require(type(issue['issue']) is str and issue['issue'], 'unsupported_assertion_requires_assessment')
    complete = (record['status'] == 'completed' and bool(record.get('current_read_only')) and
                not record.get('evidence_error') and set(seen) == targets.keys() and
                all(value == 1 for value in seen.values()) and not contradictions and
                all(row['geometry_passed'] and row['evidence_passed'] and 'issue' not in row for row in rows))
    return {'slot': record['slot'], 'status': record['status'], 'answer_sha256': record['answer_sha256'],
            'passed_quality': bool(complete), 'plugin_facts_adopted': bool(adopted), 'adopted_product_attempts': sorted(adopted),
            'missing_regions': sorted(region_label(key) for key in targets.keys() - seen.keys()),
            'duplicates': sorted(region_label(key) for key, count in seen.items() if count > 1),
            'contradictions': contradictions, 'rows': rows}


def grade(evidence_record, claims):
    require(evidence_record == evidence(), 'formal_evidence_does_not_match_originals')
    truth = dense_truth()
    geometry = json.loads(verified(original['GEOMETRY'], original['GEOMETRY_SHA'], original['ASSET'].parent))
    sizes = {row['name']: len(row['source_triangles']) for row in geometry['objects']}
    seals = {row['slot']: row for row in read(NS / 'ANSWERS_SEALED.json')['answers']}
    expected = {label for label, seal in seals.items() if seal['path'] is not None}
    require(claims.keys() == expected, 'manual_claims_must_cover_the_actual_original_answers')
    outputs = []
    for record in evidence_record['slots']:
        label = record['slot']
        if label not in expected:
            outputs.append({'slot': label, 'status': record['status'], 'passed_quality': False,
                            'plugin_facts_adopted': False, 'reason': 'no_sealed_answer', 'rows': []})
            continue
        seal = seals[label]
        answer = verified(seal['path'], seal['sha256'], NS).decode()
        outputs.append(grade_slot(record, claims[label], answer, truth, sizes))
    return {'schema': 'm4-dense-panel-formal-quality-v1', 'formal_denominator': len(SLOTS),
            'answers_sealed_sha256': evidence_record['answers_sealed_sha256'],
            'evidence_sha256': digest((HERE / 'FORMAL_EVIDENCE.json').read_bytes()),
            'independent_truth_sha256': FROZEN_TRUTH_SHA, 'slots': outputs,
            'complete_counts': {arm: sum(row['passed_quality'] for row in outputs if row['slot'][0] == arm)
                                for arm in ('N', 'P')},
            'product_adoption_count': sum(row['plugin_facts_adopted'] for row in outputs if row['slot'][0] == 'P')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        require(args.claims is not None, 'sealed_manual_claim_transcriptions_required')
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims)))
