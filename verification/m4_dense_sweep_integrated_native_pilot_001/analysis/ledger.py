"""Read-only costing and task evidence attribution for the fixed native/product pair."""

import argparse
from pathlib import Path
from runpy import run_path
import json


HERE = Path(__file__).resolve().parent
NS, V = HERE.parent, HERE.parents[1]
ROOT = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
F = run_path(str(HERE / 'formal.py'))
C = run_path(str(V / 'perf050_readonly_product_pilot_001/consumer/costs.py'))
S = run_path(str(HERE / 'score.py'))
require, read, pin = (F[key] for key in ('require', 'read', 'pin'))
LABELS = ('N1', 'P1')
NOTE_CLASSES = {'first_required_source', 'setup', 'required_followup', 'independent_check',
                'repeat_evidence', 'new_task_fact', 'other'}


def geometry_counters(source, *, product):
    objects = source['meshes'] if product else source['objects']
    meshes = objects if product else [row['evaluated'] for row in objects]
    return {'objects': len(objects),
            'vertices': sum(len(row['vertices' if product else 'vertices_world_m']) for row in meshes),
            'triangles': sum(len(row['faces' if product else 'triangles']) for row in meshes)}


def raster_charges(slot):
    claims = slot.parent.parent / 'budget/claims'
    receipts = slot.parent.parent / 'budget/settlements'
    require(claims.is_dir() and receipts.is_dir(), 'raster_claim_and_settlement_roster_missing')
    rows = []
    for path in sorted(claims.glob('*.json')):
        claim = read(path)
        if claim['label'] != slot.name or claim['kind'] != 'raster_attempt':
            continue
        settle = receipts / path.name
        row = {'claim': pin(path), 'reserved': claim['reserved_upper_bound'], 'settlement': None, 'actual': None}
        if settle.is_file():
            result = read(settle)
            require(result['token'] == claim['token'] and result['claim_sha256'] == row['claim']['sha256'],
                    'raster_charge_detached_from_original_budget_claim')
            row.update(settlement=pin(settle), actual=result['actual_attempts'],
                       confirmed_lower_bound=result.get('confirmed_attempts_lower_bound'), outcome=result.get('outcome'))
        rows.append(row)
    return {'registered': len(rows), 'rows': rows, 'actual': sum(row['actual'] for row in rows)
            if all(type(row['actual']) is int for row in rows) else None}


def product_work(slot, source, installed, attempts):
    if not any(row.get('product') for row in attempts):
        return {'product_calls': 0, 'captures': [], 'service_observations': [], 'trace_spans': {}}
    audit = C['lines'](slot / 'product_audit.jsonl')
    observations = [row for row in audit if row.get('event') == 'observe']
    traces = [row['trace'] for row in audit if row.get('event') == 'request_trace']
    grouped = {}
    for trace in traces:
        for span in trace.get('spans', []):
            grouped.setdefault(span['name'], []).append(span['duration_ns'])
    capture_rows = []
    try:
        _, _, captures, commands = F['source_captures'](slot, installed, source)
        selected = [row for row in commands if row['command']['command'] in ('capture', 'capture_scene', 'capture_task')]
        require(len(selected) == len(captures), 'product_capture_commands_do_not_identify_all_successful_geometry')
        for command, capture in zip(selected, captures, strict=True):
            capture_rows.append({'wire_sequence': command['wire_sequence'], 'command': command['command']['command'],
                                 'capture_scope': capture.get('capture_scope', 'complete_scene_meshes'),
                                 **geometry_counters(capture, product=True)})
    except F['ERRORS'] as error:
        capture_rows = None
        capture_issue = str(error)
    return {'product_calls': sum(bool(row.get('product')) for row in attempts),
            'captures': capture_rows, 'capture_audit_issue': capture_issue if capture_rows is None else None,
            'service_observations': [{'mode': row.get('observation_mode'), 'status': row.get('status'),
                                      'task_work': row.get('task_work')} for row in observations],
            'trace_spans': {key: {'count': len(times), 'total_ms': sum(times)/1e6}
                            for key, times in sorted(grouped.items())}}


def original_source_work(slot, source):
    receipt = {}
    for path in sorted((slot / 'terminal_sources').glob('live-source-*.json')):
        doc = read(path)
        require(doc['source']['asset_sha256'] == source['source']['asset_sha256'],
                'ordinary_source_geometry_belongs_to_different_asset')
        receipt[path.stem] = {**pin(path, slot), **geometry_counters(doc, product=False)}
    return {'retained_live_sources': receipt, 'ordinary_nonterminal_worker_calls':
            [row for row in C['lines'](slot / 'NATIVE_CALLS.jsonl') if row['terminal'] is False]}


def verified_notes(notes, attempts):
    checked = set()
    by_attempt = {row['attempt']: row for row in attempts}
    for note in notes:
        index = note['attempt']
        row = by_attempt[index]
        reply = read(row['RX']['path'])
        text = [part['text'] for part in reply['result']['content'] if part['type'] == 'text']
        quote = note['public_quote']
        require(index not in checked and row['model_visible_as_public_CLI_tool_result']
                and note['kind'] in NOTE_CLASSES and type(quote) is str and quote.strip()
                and any(quote in body for body in text) and type(note['reason']) is str and note['reason'].strip(),
                'trace_note_not_bound_to_unique_actual_visible_reply')
        checked.add(index)
    return {row['attempt']: row for row in notes}


def picture_transfers(slot, attempts, discoveries=()):
    """A repeated digest alone does not establish another delivery of the same frame."""
    device = read(slot / 'DEVICE_EVIDENCE.json')
    delivery = F['D']['frame_deliveries'](slot, device['frames'], {'attempts': attempts})
    proof_paths = {(row['attempt'], path['image_ref']) for row in discoveries
                   for path in (row.get('public_witnesses') or {}).get('paths', [])}
    by_attempt = {row['attempt']: [] for row in attempts}
    for ref, matches in delivery.items():
        disclosed_path = False
        for i, match in enumerate(matches):
            has_path = match['named_local_path'] or (match['attempt'], ref) in proof_paths
            by_attempt[match['attempt']].append({'image_ref': ref, 'block_index': match['block_index'],
                                                'repeat_same_ref_and_PNG': i > 0,
                                                'named_local_path_in_declaration': has_path,
                                                'first_named_path_for_ref_in_declaration': has_path and not disclosed_path})
            disclosed_path |= has_path
    return by_attempt


def adoptions(item, score, notes):
    answer = item['answer']['text']
    checks = dict(discovery='all_scene_candidates', occlusion='occluded_target_six_direction_unknown',
                  measurement='exact_surface_distance_direction_and_points')
    results = []
    for note in notes:
        kind = note['kind']
        require(score['checks'][checks[kind]]['passed'] and note['quote'] in answer
                and isinstance(note['quote'], str) and note['quote'].strip(), 'adoption_annotation_not_in_original_answer')
        fact = [fact for fact in item['verified_product_facts'] if
                fact['kind'] == kind and fact['attempt'] == note['attempt']]
        require(len(fact) == 1, 'adoption_annotation_missing_source_bound_actual_tool_fact')
        if kind == 'measurement':
            answer_pair = score['checks'][checks[kind]]['verified']['point_pair']
            require(all(F['E']['nearby'](left, right) for left, right in
                        zip(answer_pair, fact[0]['proof']['point_pair'], strict=True)),
                    'answer_uses_different_equivalent_surface_pair')
        results.append({**note, 'fact': fact[0]})
    images = []
    for role in ('R', 'Q'):
        check = score['checks']['original_image_' + role]
        if check['passed']:
            for proof in check['verified']:
                frame = item['link_frames'].get(proof['reference_spelling']) or item['available_frames'].get(proof['reference_spelling'])
                if frame and frame['origin'] == 'product':
                    images.append({'role': role, 'original_frame': frame['frame_ref'],
                                   'actual_deliveries': frame['actual_deliveries']})
    return {'verified_text_adoption': results, 'confirmed_product_image_use': images}


def summarize(slot, frozen, truth, binding_path, claims, judgments):
    ledger = C['summarize'](slot, frozen)
    ledger['formal_created'] = slot.is_dir()
    ledger['evidence_error'] = None
    if ledger['status'] != 'completed':
        return ledger
    try:
        item = F['load_slot'](slot, truth, binding_path=binding_path)
        original = read(slot / 'SLOT_RESULT.json')
        require(original['freeze_sha256'] == frozen and ledger['cost_evidence_verified'],
                'closed_formal_slot_and_costs_have_no_common_verified_identity')
        attempts = item['actual_attempts']
        require(len(attempts) == len(ledger['actual_requests']), 'raw_attempt_totals_not_common')
        for wire, cost in zip(attempts, ledger['actual_requests'], strict=True):
            require(wire['attempt'] == cost['attempt'] and wire['RX']['sha256'] == cost['stdio_RX']['sha256'],
                    'actual_cost_attachment_differs_from_evidence_attachment')
        ledger.update(packet_issues=item['packet_issues'], closed_source=item['closed_source'],
                      first_discovery=item['first_matching_task'], verified_product_facts=item['verified_product_facts'],
                      scene_population=geometry_counters(item['source'], product=False),
                      native_work=original_source_work(slot, item['source']),
                      product_work=product_work(slot, item['source'], read(binding_path), attempts),
                      real_raster_budget=raster_charges(slot))
        notes = verified_notes(judgments.get('attempts', []), attempts)
        ledger['notes'] = notes
        ledger['classified_coverage'] = {'noted': len(notes), 'all_attempts': len(attempts),
                                         'actual_rejections': [row['attempt'] for row in attempts if row['is_error']]}
        ledger['original_PNG_transfers'] = picture_transfers(slot, attempts, item['matching_task_requests'])
        use = ledger.get('raw_CLI_usage') or []
        usage = use[0] if len(use) == 1 and isinstance(use[0], dict) else {}
        count = [usage.get(key) for key in ('input_tokens', 'cached_input_tokens', 'output_tokens')]
        ledger['CLI_uncached_plus_output_tokens'] = (count[0] - count[1] + count[2]
            if all(type(item) is int and item >= 0 for item in count) and count[0] >= count[1] else None)
        ledger['physical_outer_TX_bytes'] = sum(row['TX']['bytes'] for row in attempts)
        ledger['physical_outer_RX_bytes'] = sum(row['RX']['bytes'] for row in attempts)
        if claims is not None:
            ledger['quality'] = S['score_answer'](item, claims)
            ledger['adoption'] = adoptions(item, ledger['quality'], judgments.get('adoptions', []))
        else:
            ledger['quality'] = None
            ledger['adoption'] = None
    except F['ERRORS'] as error:
        ledger['evidence_error'] = str(error)
    return ledger


def analyze(runtime, freeze, truth, binding, claims, judgments):
    frozen = pin(freeze)
    rows = {label: summarize(runtime / 'slots' / label, frozen['sha256'], truth, binding,
                             claims.get(label), judgments.get(label, {})) for label in LABELS}
    n, p = (rows[label] for label in LABELS)
    comparable = (all(row['status'] == 'completed' and row.get('evidence_error') is None
                      and (row.get('quality') or {}).get('all_quality_passed') for row in rows.values())
                  and n.get('thread_id') != p.get('thread_id') and n.get('initial_prompt_sha256') == p.get('initial_prompt_sha256'))
    adopted = bool((p.get('adoption') or {}).get('verified_text_adoption')
                   or (p.get('adoption') or {}).get('confirmed_product_image_use'))
    return {'schema': 'm4-dense-integrated-closed-formal-ledger-v1', 'freeze': frozen,
            'slots': rows, 'complete_same_quality_pair': bool(comparable),
            'actual_product_task_evidence_adopted': adopted, 'provider_internal_timings': None,
            'actual_cash_costs': None, 'human_clicked_final_links': None,
            'denominator': {'planned': 2, 'actual_created': sum(row['formal_created'] for row in rows.values()),
                            'completed': sum(row['status'] == 'completed' for row in rows.values()),
                            'unrun': sum(row['status'] == 'unrun' for row in rows.values()),
                            'actual_model_launches': sum(row['model_consumers_launched'] for row in rows.values())}}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--runtime', type=Path, default=ROOT)
    cli.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    cli.add_argument('--truth', type=Path, default=F['ORIGINAL'] / 'fixture/TRUTH.json')
    cli.add_argument('--binding', type=Path, default=F['BINDING'])
    cli.add_argument('--claims', type=Path)
    cli.add_argument('--judgments', type=Path)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    result = analyze(args.runtime, args.freeze, args.truth, args.binding,
                     read(args.claims) if args.claims else {}, read(args.judgments) if args.judgments else {})
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
