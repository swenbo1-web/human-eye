"""Test frozen scorer against genuine dense product and ordinary native originals."""

from copy import deepcopy
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score


def original_product():
    root = Path('D:/he_m4_dense_region_brief_001/slots/QP')
    receipt = score.read(score.BRIEF / 'checks/LIVE_REVIEW.json')
    response = score.read(root / 'mcp/rpc_04/RX.bin')['result']
    body, rows, picked = score.full_or_brief(response)
    product = score.read(root / 'product_full/call_001/SERVICE_RESULT.json')
    slot_result = score.read(root / 'SLOT_RESULT.json')
    truth = score.dense_truth()
    installed = score.read(score.BINDING)
    sys.path.insert(0, installed['dependency_root'])
    terminal, source = score.original['current_source'](root, slot_result)
    captures, _ = score.capture_check['decode_captures'](root, installed, score.capture_check['Audit']())
    rows = score.validated_rows(root, installed, terminal, {score.region_key(row): row for row in truth['eligible']},
                                body, rows, product, captures)
    frames = {}
    scopes = {scope['scope_id']: scope['binding'] for scope in product['scopes']}
    for index, ref in picked.items():
        raw, = [frame for frame in product['frames'] if frame['image_ref'] == ref]
        frame = score.product_probe(raw, scopes, product['binding'], root)
        frames[ref] = score.inspect_frame(root, frame, terminal, truth)
        frames[ref]['delivery'].append({'attempt': 1, 'MCP_content_block': index, 'origin': 'product'})
    approvals = {key for frame in frames.values() for key, pixel in frame['witnesses'].items() if pixel['qualifies']}
    score.require(len(rows) == 13 and len(approvals) == 11 and len(frames) == 2 and
                  receipt['passed'] is True and
                  score.schema['cli_stages'](response)['passed'] is True, 'published_dense_replay_differs')
    return {'body_bytes': receipt['wire']['body_UTF8_bytes'], 'exact_roster': len(rows),
            'complete': len(approvals), 'geometric_unknown': len(rows) - len(approvals),
            'fixed_CLI_complete': True, 'images': [f['PNG_sha256'] for f in frames.values()],
            'PNGs_and_source': source}, frames, rows, terminal, truth


def original_native():
    batch = score.V / 'm4_cross_scale_assembly_transfer_001'
    runtime = Path('D:/he_m4_cross_scale_assembly_transfer_001')
    root = runtime / 'slots/N1'
    prior = runpy.run_path(str(batch / 'scoring/score_live.py'))
    truth = score.read(batch / 'fixture/CURRENT_TRUTH.json')
    terminal, _ = prior['bound_terminal'](root, score.read(root / 'SLOT_RESULT.json'), truth['asset_sha256'])
    seal, = [row for row in score.read(batch / 'ANSWERS_SEALED.json')['answers'] if row['slot'] == 'N1']
    frames, ledger = score.audit_slot(root, seal, terminal, truth, score.read(score.BINDING), evidence_root=batch)
    score.require(len(ledger['attempts']) == 8 and all('evidence_error' not in row for row in ledger['attempts']),
                  'archived_ordinary_public_wire_review_failed')
    verified = {ref: sorted(label for label, observed in frame['witnesses'].items() if observed['qualifies'])
                for ref, frame in frames.items() if frame['delivery']}
    score.require(any(any(key.startswith('N22[') for key in values) for values in verified.values()),
                  'ordinary_source_bound_complete_native_N22_lost')
    return {'archived_business_attempts': len(ledger['attempts']),
            'completed_original_deliveries': len(verified), 'verified_witnesses': verified}


def scorer_controls(frames, rows, terminal, truth):
    # The support records are actual. These answer transcriptions are offline controls.
    answer_parts, answers = [], []
    for region in truth['eligible']:
        label = score.region_label(score.region_key(region))
        quote = 'Current exact source keys and center for ' + label
        answer = {'object_name': region['object_name'], 'quote': quote,
                  'source_triangle_index_ranges': region['source_triangle_id_ranges'],
                  'center_world_m': region['center_world_m']}
        witnessed = [(ref, frame['view']) for ref, frame in frames.items() if frame['witnesses'][label]['qualifies']]
        if witnessed:
            ref, direction = witnessed[0]
            outcome = {'kind': 'witness', 'direction': direction, 'ref': ref, 'quote': f'{label} original {ref} {direction}'}
        else:
            outcome = {'kind': 'geometric_occlusion', 'direction': 'LEFT',
                       'quote': f'{label} is blocked on its sole forward direction LEFT'}
        answer['outcome'] = outcome
        answer_parts.extend((quote, outcome['quote']))
        answers.append(answer)
    answer = '\n'.join(answer_parts)
    digest = score.digest(answer.encode())
    transcribed = {'answer_sha256': digest, 'rows': answers, 'extra_assertions': []}
    record = {'slot': 'P1', 'status': 'completed', 'answer_sha256': digest,
              'current_read_only': {'passed': True}, 'frames': frames,
              'tools': {'attempts': [{'attempt': 1, 'regions': rows, 'fixed_CLI_whole_content': True}]}}
    sizes = {row['name']: len(row['evaluated']['triangles']) for row in terminal['objects']}
    good = score.grade_slot(record, transcribed, answer, truth, sizes)
    score.require(good['passed_quality'] and good['plugin_facts_adopted'], 'complete_association_or_product_adoption_failed')
    cases = ('same_object_other_region_copied', 'drop_region', 'use_other_image', 'outside_center_tolerance',
             'false_all_pixels_hidden', 'irreconcilable_extra_count')
    for case in cases:
        changed = deepcopy(transcribed)
        edits = changed['rows']
        if case == 'same_object_other_region_copied':
            top = next(item for item in edits if item['source_triangle_index_ranges'] == [[512, 513]])
            top['source_triangle_index_ranges'] = [[0, 511]]
        elif case == 'drop_region':
            edits.pop()
        elif case == 'use_other_image':
            witnessed = next(item['outcome'] for item in edits if item['outcome']['kind'] == 'witness')
            witnessed['ref'] = next(ref for ref in frames if ref != witnessed['ref'])
        elif case == 'outside_center_tolerance':
            edits[0]['center_world_m'][0] += .001
        elif case == 'false_all_pixels_hidden':
            next(item['outcome'] for item in edits if item['outcome']['kind'] == 'geometric_occlusion')[
                'claims_all_pixels_hidden'] = True
        elif case == 'irreconcilable_extra_count':
            changed['extra_assertions'] = [{'quote': changed['rows'][0]['quote'], 'issue': 'unsupported claim control'}]
        score.require(not score.grade_slot(record, changed, answer, truth, sizes)['passed_quality'],
                      'mutated_answer_incorrectly_accepted/' + case)
    return {'same_object_two_eligible_rows_preserved': True, 'product_witness_adoption': True,
            'negative_controls_passed': list(cases)}


if __name__ == '__main__':
    product, frames, rows, terminal, truth = original_product()
    native = original_native()
    grade = scorer_controls(frames, rows, terminal, truth)
    score.write(HERE / 'SCORER_PREFLIGHT.json', {'passed': True, 'product_original_replay': product,
        'native_original_replay': native, 'grading_controls': grade, 'real_Blender_or_model_runs': 0})
    print('Dense formal scoring genuine originals and answer controls passed')
